import logging
import time
import os
import threading
from app.core.server_events import ServerEvent
from app.core.logic import Scheduler, BackupScheduler, get_server_meta
from app.services.backup_manager import BackupManager
from app.core.app_config import AppConfig
from app.core.constants import check_disk_space, SERVERS_DIR
from app.services.scaffolder import pre_boot_scaffold
from app.services.sanitizer import is_safe_command

logger = logging.getLogger(__name__)

class ServerOrchestrator:
    def __init__(self, manager):
        self.manager = manager

    def start_server(self) -> bool:
        if not check_disk_space(min_gb=1):
            self.manager.events.emit(ServerEvent.NOTIFICATION, {"msg": "Not enough disk space to start server (>1GB required).", "type": "error"})
            self.manager.events.emit(ServerEvent.CONSOLE_LINE, "[Error] Not enough disk space to start server.")
            return False

        with self.manager._start_lock:
            if not self.manager.current_server:
                return False

            if self.manager.server_runner and self.manager.server_runner.running:
                self.manager.events.emit(ServerEvent.CONSOLE_LINE, "[Error] A server is already running.")
                return False

            self.manager._stop_monitors()
            from app.core.core import ServerState
            self.manager.state = ServerState.STARTING

            config = self.manager.get_config()
            ram = config.get("ram_allocation", "2G")

            server_dir = os.path.join(SERVERS_DIR, self.manager.current_server)
            mc_version = "1.20.1"
            java_path = "auto"
            use_aikars = True
            required_java_cached = None
            required_java = 21
            auto_install_jdk = True
            self.manager._jdk_source = "unknown"
            try:
                meta = get_server_meta(self.manager.current_server)
                if meta:
                    mc_version = meta.get("version", "1.20.1")
                    required_java_cached = meta.get("required_java")
                    self.manager._jdk_source = meta.get("jdk_source", "system")
                    auto_install_jdk = meta.get("auto_install_jdk", True)
                    if meta.get("advanced_mode", False):
                        java_path = meta.get("java_path", "auto")
                        use_aikars = meta.get("use_aikars", True)
            except Exception as e:
                logger.error("Failed to read metadata: %s", e)

            port = self.manager.get_server_port(self.manager.current_server)
            pre_boot_scaffold(server_dir, port=port, eula_accepted=True)

            if java_path == "auto":
                result = self.manager._resolve_java_bin(server_dir, mc_version, required_java_cached, auto_install_jdk)
                if result is None:
                    return False
                java_bin, required_java = result
            else:
                java_bin = java_path

            return self.manager._launch_server(ram, java_bin, use_aikars, required_java, config)

    def stop_server(self) -> None:
        from app.core.core import ServerState
        self.manager.state = ServerState.STOPPING
        if self.manager.server_runner:
            self.manager.server_runner.stop()
        self.manager.state = ServerState.OFFLINE

    def is_running(self) -> bool:
        return self.manager.server_runner is not None and self.manager.server_runner.running

    def send_command(self, cmd: str) -> None:
        if self.manager.server_runner and self.manager.server_runner.running:
            safe, reason = is_safe_command(cmd)
            if not safe:
                logger.warning("Blocked unsafe command: '%s' - Reason: %s", cmd, reason)
                self.manager.events.emit(ServerEvent.CONSOLE_LINE, f"[Security] Blocked unsafe command: {reason}")
                return
            self.manager.server_runner.send_command(cmd)


class TunnelOrchestrator:
    def __init__(self, manager):
        self.manager = manager

    def start_tunnel(self) -> None:
        port = self.manager.get_server_port()
        self.manager.executor.submit(self.manager.playit_manager.start, port)

    def stop_tunnel(self) -> None:
        self.manager.playit_manager.stop(force=True)

    def reset_tunnel(self, mode: str = "full") -> None:
        self.manager.playit_manager.reset(mode)

    def get_tunnel_ip(self) -> str | None:
        return self.manager.playit_manager.current_address

    def create_tunnel_for_server(self, server_name: str) -> None:
        port = self.manager.get_server_port(server_name)
        def _create():
            try:
                self.manager.playit_manager.get_or_create_tunnel(port)
            except Exception as e:
                logger.error("Auto-tunnel creation failed for %s: %s", server_name, e)
        self.manager.executor.submit(_create)


class BackupOrchestrator:
    def __init__(self, manager):
        self.manager = manager

    def _check_auto_backup(self) -> None:
        if not self.manager.current_server:
            return
        with self.manager._backup_lock:
            if self.manager._backup_in_progress:
                return
            backup_sched = BackupScheduler(self.manager.current_server)
            if not backup_sched.is_due():
                return
            self.manager._backup_in_progress = True
        self.manager.events.emit(ServerEvent.CONSOLE_LINE, "[System] Auto-backup due. Starting...")
        self.manager.executor.submit(self._run_auto_backup)

    def _run_auto_backup(self) -> None:
        try:
            bm = BackupManager(self.manager.current_server)
            config = BackupScheduler(self.manager.current_server).get_config()
            path, error = bm.create_backup(retention_count=config.get("retention_count"))
            if path:
                self.manager.events.emit(ServerEvent.CONSOLE_LINE, f"[System] Auto-backup completed: {path.name}")
                self.manager.events.emit(ServerEvent.BACKUP_COMPLETED, {"path": str(path), "server": self.manager.current_server})
            else:
                self.manager.events.emit(ServerEvent.CONSOLE_LINE, f"[Error] Auto-backup failed: {error}")
                self.manager.events.emit(ServerEvent.BACKUP_FAILED, {"error": error, "server": self.manager.current_server})
            BackupScheduler(self.manager.current_server).mark_run()
        finally:
            with self.manager._backup_lock:
                self.manager._backup_in_progress = False


class SchedulerOrchestrator:
    def __init__(self, manager):
        self.manager = manager

    def _start_tick_loop(self) -> None:
        if self.manager._tick_running: return
        self.manager._tick_running = True
        
        def _loop():
            last_time = time.time()
            last_sched_check = 0.0
            
            while self.manager._tick_running:
                now = time.time()
                dt = now - last_time
                last_time = now
                
                if self.manager.server_runner and self.manager.server_runner.running:
                    if dt > 0:
                        self.manager.events.emit(ServerEvent.TPS_UPDATE, 1.0 / dt)
                else:
                    self.manager.events.emit(ServerEvent.TPS_UPDATE, 0.0)

                if getattr(self.manager, "_heartbeat", None):
                    self.manager._heartbeat.tick(now)
                    
                # Player Sync
                if self.manager.server_runner and self.manager.server_runner.running:
                    self.manager.events.emit(ServerEvent.PLAYER_COUNT, self.manager.server_runner.player_count)

                if now - last_sched_check >= AppConfig.SCHEDULER_CHECK_INTERVAL:
                    last_sched_check = now
                    if self.manager.server_runner and self.manager.server_runner.running and self.manager.current_server:
                        service = Scheduler(self.manager.current_server)
                        status = service.get_status()
                        if status:
                            with self.manager._restart_warnings_lock:
                                key, message = Scheduler.get_warning_message(status["remaining_seconds"], self.manager.restart_warnings_sent)
                                if key:
                                    self.manager._send_system_message(message)
                                    self.manager.restart_warnings_sent.add(key)
                            
                            if status["is_due"]:
                                self.manager.events.emit(ServerEvent.CONSOLE_LINE, "[System] Scheduled restart due. Initiating final countdown...")
                                self.manager.events.emit(ServerEvent.REQUEST_RESTART, {"reason": "scheduled"})
                                service.update_last_run()
                                with self.manager._restart_warnings_lock:
                                    self.manager.restart_warnings_sent.clear()
                            
                            self.manager.backup_orchestrator._check_auto_backup()
                
                elapsed = time.time() - now
                sleep_time = max(0.0, 0.05 - elapsed)
                time.sleep(sleep_time)

        self.manager._tick_thread = threading.Thread(target=_loop, daemon=True, name="ServerTickThread")
        self.manager._tick_thread.start()
