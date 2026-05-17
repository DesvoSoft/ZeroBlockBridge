import logging
import threading
import time
import os
from typing import Optional

from app.core.server_events import EventBus, ServerEvent
from app.services.backup_manager import BackupManager
from app.core.logic import ServerRunner, load_config, save_config, Scheduler, BackupScheduler
from app.services.watchdog import Watchdog
from app.services.lag_monitor import LagMonitor
from app.services.heartbeat import HeartbeatMonitor
from app.core.playit_manager import PlayitManager

from app.services.console_buffer import CircularBuffer
from app.core.app_config import AppConfig
from app.core.version_manager import VersionManager

logger = logging.getLogger(__name__)

class ZBBManager:
    """
    Central orchestrator for ZeroBlockBridge logic.
    Decouples UI from the server lifecycle, background monitors, and tunneling.
    """
    def __init__(self, event_bus: EventBus):
        self.events = event_bus
        self.current_server: Optional[str] = None
        self.server_runner: Optional[ServerRunner] = None
        
        # Monitors
        self._watchdog: Optional[Watchdog] = None
        self._lag_monitor: Optional[LagMonitor] = None
        self._heartbeat: Optional[HeartbeatMonitor] = None
        
        # Scheduler State
        self._scheduler_thread: Optional[threading.Thread] = None
        self._scheduler_running = False
        self.restart_warnings_sent: set = set()
        self._restart_warnings_lock = threading.Lock()
        self._backup_in_progress = False
        self._backup_lock = threading.Lock()
        
        # Buffers
        self.console_buffer = CircularBuffer(max_size=1000)
        self.tunnel_buffer = CircularBuffer(max_size=1000)
        
        # External Services
        self.version_manager = VersionManager()
        self.playit_manager = PlayitManager(
            console_callback=lambda line: self.events.emit(ServerEvent.TUNNEL_CONSOLE_LINE, line),
            status_callback=self._on_playit_status,
            notification_callback=lambda msg, t_type: self.events.emit(ServerEvent.NOTIFICATION, {"msg": msg, "type": t_type})
        )
        
        # Internal Subscriptions
        self.events.subscribe(ServerEvent.REQUEST_RESTART, self._handle_restart_request)
        self.events.subscribe(ServerEvent.CONSOLE_LINE, lambda line: self.console_buffer.append(line))
        self.events.subscribe(ServerEvent.TUNNEL_CONSOLE_LINE, lambda line: self.tunnel_buffer.append(line))

    def _on_playit_status(self, status, ip):
        config = self.get_config()
        display_ip = ip
        dns = None
        if ip:
            domain_suffixes = (".ply.gg", ".playit.gg", ".joinmc.link")
            if any(s in ip for s in domain_suffixes):
                dns = ip
                display_ip = ""
        # Saved DNS from config is the last-resort fallback, not the override
        if status == "Online" and not dns and config.get("playit_dns"):
            dns = config["playit_dns"]
            display_ip = config["playit_dns"]
        
        is_guest = self.playit_manager.api_client.is_read_only
        self.events.emit(ServerEvent.TUNNEL_STATUS, {"status": status, "ip": display_ip, "dns": dns, "is_guest": is_guest})

    def _save_jdk_metadata(self, required_java: int, jdk_source: str):
        from app.core.logic import update_server_meta
        if not self.current_server:
            return
        from app.core.constants import SERVERS_DIR
        if not os.path.exists(os.path.join(SERVERS_DIR, self.current_server, "metadata.json")):
            return
        update_server_meta(self.current_server, {"required_java": required_java, "jdk_source": jdk_source})

    # --- Configuration ---
    def get_config(self):
        return load_config()

    def update_config(self, key: str, value: any):
        config = load_config()
        config[key] = value
        save_config(config)
        return config

    def remove_config_key(self, key: str):
        config = load_config()
        if key in config:
            del config[key]
            save_config(config)
            return True
        return False

    # --- Core Server Operations ---
    def bootstrap(self):
        logger.info("[ZBBManager] Bootstrapping core services...")
        self._start_scheduler_loop()

    def select_server(self, server_name: str):
        self.current_server = server_name

    def _auto_install_java(self, required_java: int) -> Optional[str]:
        from app.services.java_installer import JdkManagerInstance
        try:
            java_bin = JdkManagerInstance.ensure_java(required_java)
            self._jdk_source = "portable"
            self._save_jdk_metadata(required_java, "portable")
            self.events.emit(ServerEvent.CONSOLE_LINE, f"[System] Using auto-installed JDK {required_java} at {java_bin}")
            self.events.emit(ServerEvent.STARTING, {"jdk_source": "portable", "required_java": required_java})
            return java_bin
        except Exception:
            return None

    def _launch_server(self, ram: str, java_bin: str, use_aikars: bool, required_java: int, config: dict) -> bool:
        self.server_runner = ServerRunner(self.current_server, ram, self.events, java_bin=java_bin, use_aikars=use_aikars)
        self._setup_monitors(config)
        self.server_runner.start()
        self._save_jdk_metadata(required_java, self._jdk_source)
        self.events.emit(ServerEvent.STARTING, {"jdk_source": self._jdk_source, "required_java": required_java})
        return True

    def _resolve_java_bin(self, server_dir: str, mc_version: str,
                          required_java_cached: int | None,
                          auto_install_jdk: bool) -> tuple[str, int] | None:
        from app.services.java_detector import JavaDetector, get_required_java
        from app.services.bytecode_analyzer import analyze_jar_bytecode

        if required_java_cached:
            required_java = required_java_cached
            source = "cached-metadata"
        else:
            self.events.emit(ServerEvent.CONSOLE_LINE, "[System] Analyzing Java requirements from server jar...")
            jar_path = os.path.join(server_dir, "server.jar")
            bytecode_java = None
            for _ in range(10):
                if os.path.exists(jar_path) and os.path.getsize(jar_path) > 0:
                    break
                time.sleep(0.5)

            if os.path.exists(jar_path) and os.path.getsize(jar_path) > 0:
                try:
                    bytecode_java = analyze_jar_bytecode(jar_path)
                except Exception as e:
                    self.events.emit(ServerEvent.CONSOLE_LINE, f"[Warning] Bytecode analysis crashed: {e}")

            required_java = bytecode_java if bytecode_java else get_required_java(mc_version)
            source = "bytecode" if bytecode_java else "version-map"

            from app.core.logic import update_server_meta
            update_server_meta(self.current_server, {"required_java": required_java})

        self.events.emit(ServerEvent.CONSOLE_LINE, f"[System] Java {required_java} required (source: {source})")

        detector = JavaDetector()
        all_javas = detector.detect_all()

        if not all_javas:
            if not auto_install_jdk:
                msg = "No Java installation found and auto-install is disabled in server settings."
                self.events.emit(ServerEvent.NOTIFICATION, {"msg": msg, "type": "error"})
                self.events.emit(ServerEvent.CONSOLE_LINE, f"[Error] {msg}")
                return None
            self.events.emit(ServerEvent.CONSOLE_LINE, f"[System] No Java installation found. Attempting to auto-install JDK {required_java}...")
            java_bin = self._auto_install_java(required_java)
            if not java_bin:
                self.events.emit(ServerEvent.NOTIFICATION, {"msg": f"Error: No Java found and auto-install JDK {required_java} failed.", "type": "error"})
                self.events.emit(ServerEvent.CONSOLE_LINE, f"[Error] No Java found and auto-install JDK {required_java} failed.")
                return None
            self._jdk_source = "portable"
            return (java_bin, required_java)

        exact = [j for j in all_javas if j.major == required_java]
        if exact:
            exact.sort(key=lambda j: j.is_jdk, reverse=True)
            self._jdk_source = "system"
            self.events.emit(ServerEvent.CONSOLE_LINE, f"[System] Using Java {exact[0].major} ({exact[0].source})")
            return (exact[0].path, required_java)

        best = sorted(all_javas, key=lambda j: j.major, reverse=True)[0]

        if best.major > required_java and best.major <= 21:
            self._jdk_source = "system"
            msg = f"Running with Java {best.major}. Recommended: Java {required_java}."
            self.events.emit(ServerEvent.NOTIFICATION, {"msg": msg, "type": "warning"})
            self.events.emit(ServerEvent.CONSOLE_LINE, f"[Warning] {msg}")
            return (best.path, required_java)

        if best.major > 21:
            if not auto_install_jdk:
                msg = f"Java {best.major} detected (experimental). Auto-install disabled. Install Java {required_java} manually."
                self.events.emit(ServerEvent.NOTIFICATION, {"msg": msg, "type": "error"})
                self.events.emit(ServerEvent.CONSOLE_LINE, f"[Error] {msg}")
                return None
            self.events.emit(ServerEvent.CONSOLE_LINE, f"[System] Java {best.major} detected but unstable. Attempting to auto-install JDK {required_java}...")
            java_bin = self._auto_install_java(required_java)
            if not java_bin:
                msg = f"Java {best.major} detected (experimental). ZBB supports up to Java 21. Auto-install JDK {required_java} failed."
                self.events.emit(ServerEvent.NOTIFICATION, {"msg": msg, "type": "error"})
                self.events.emit(ServerEvent.CONSOLE_LINE, f"[Error] {msg}")
                return None
            self._jdk_source = "portable"
            return (java_bin, required_java)

        if not auto_install_jdk:
            msg = f"Java {best.major} too low. Auto-install disabled. Install Java {required_java} manually."
            self.events.emit(ServerEvent.NOTIFICATION, {"msg": msg, "type": "error"})
            self.events.emit(ServerEvent.CONSOLE_LINE, f"[Error] {msg}")
            return None
        self.events.emit(ServerEvent.CONSOLE_LINE, f"[System] Java {best.major} too low. Attempting to auto-install JDK {required_java}...")
        java_bin = self._auto_install_java(required_java)
        if not java_bin:
            msg = f"Java version too low. Required Java {required_java}, detected Java {best.major}. Auto-install failed."
            self.events.emit(ServerEvent.NOTIFICATION, {"msg": msg, "type": "error"})
            self.events.emit(ServerEvent.CONSOLE_LINE, f"[Error] {msg}")
            return None
        self._jdk_source = "portable"
        return (java_bin, required_java)

    def start_server(self):
        if not self.current_server:
            return False
        
        if self.server_runner and self.server_runner.running:
            self.events.emit(ServerEvent.CONSOLE_LINE, "[Error] A server is already running.")
            return False
            
        self._stop_monitors()

        config = self.get_config()
        ram = config.get("ram_allocation", "2G")

        from app.core.constants import SERVERS_DIR
        from app.core.logic import get_server_meta
        server_dir = os.path.join(SERVERS_DIR, self.current_server)
        mc_version = "1.20.1"
        java_path = "auto"
        use_aikars = True
        required_java_cached = None
        required_java = 21
        auto_install_jdk = True
        self._jdk_source = "unknown"
        try:
            meta = get_server_meta(self.current_server)
            if meta:
                mc_version = meta.get("version", "1.20.1")
                required_java_cached = meta.get("required_java")
                self._jdk_source = meta.get("jdk_source", "system")
                auto_install_jdk = meta.get("auto_install_jdk", True)
                if meta.get("advanced_mode", False):
                    java_path = meta.get("java_path", "auto")
                    use_aikars = meta.get("use_aikars", True)
        except Exception as e:
            logger.error("Failed to read metadata: %s", e)

        from app.services.scaffolder import pre_boot_scaffold
        port = self.get_server_port(self.current_server)
        pre_boot_scaffold(server_dir, port=port, eula_accepted=True)

        if java_path == "auto":
            result = self._resolve_java_bin(server_dir, mc_version, required_java_cached, auto_install_jdk)
            if result is None:
                return False
            java_bin, required_java = result
        else:
            java_bin = java_path

        return self._launch_server(ram, java_bin, use_aikars, required_java, config)

    def load_server_manually(self, folder_path: str) -> bool:
        """Imports an existing server by creating a link in the servers directory."""
        import os, sys, json
        from app.core.constants import SERVERS_DIR
        
        server_name = os.path.basename(folder_path.rstrip("\\/"))
        link_path = os.path.join(SERVERS_DIR, server_name)
        
        if os.path.exists(link_path):
            raise Exception(f"A server named '{server_name}' already exists.")
            
        try:
            # Create the link (junction on windows)
            if sys.platform == "win32":
                import _winapi
                _winapi.CreateJunction(folder_path, link_path)
            else:
                os.symlink(folder_path, link_path)
                
            # Create a default metadata.json if missing
            if not os.path.exists(os.path.join(link_path, "metadata.json")):
                jar_name = "server.jar"
                if not os.path.exists(os.path.join(link_path, jar_name)):
                    jars = [f for f in os.listdir(link_path) if f.endswith(".jar")]
                    if jars: jar_name = jars[0]
                from app.core.logic import update_server_meta
                update_server_meta(server_name, {
                    "name": server_name,
                    "type": "Vanilla",
                    "version": "Unknown",
                    "java_path": "auto",
                    "advanced_mode": False,
                    "use_aikars": True,
                    "custom_jar": jar_name
                })
            
            return True
        except Exception as e:
            if os.path.exists(link_path):
                try:
                    os.rmdir(link_path)
                except OSError as cleanup_err:
                    logger.warning("Failed to cleanup link dir after error: %s", cleanup_err)
            raise e

    def stop_server(self):
        if self.server_runner:
            self.server_runner.stop()

    def send_command(self, cmd: str):
        if self.server_runner and self.server_runner.running:
            from app.services.sanitizer import is_safe_command
            safe, reason = is_safe_command(cmd)
            if not safe:
                logger.warning(f"Blocked unsafe command: '{cmd}' - Reason: {reason}")
                self.events.emit(ServerEvent.CONSOLE_LINE, f"[Security] Blocked unsafe command: {reason}")
                return
            self.server_runner.send_command(cmd)

    def is_running(self):
        return self.server_runner and self.server_runner.running

    # --- Monitors ---
    def _setup_monitors(self, config):
        self._lag_monitor = LagMonitor(event_emitter=self.events)
        self._heartbeat = HeartbeatMonitor(
            event_emitter=self.events,
            server_runner_getter=lambda: self.server_runner,
        )
        self._heartbeat.start()
        max_retries = config.get("watchdog_max_retries", 3)
        self._watchdog = Watchdog(self.server_runner, self.events, max_retries=max_retries)
        self._watchdog.listen()

    def _stop_monitors(self):
        if self._heartbeat: self._heartbeat.stop()
        if self._watchdog: self._watchdog.stop()

    # --- Tunnel Management ---
    def get_server_port(self, server_name: str = None) -> int:
        target = server_name or self.current_server
        if not target: return 25565
        from app.services.server_properties import load_server_properties
        props = load_server_properties(target)
        return int(props.get("server-port", 25565))

    def create_tunnel_for_server(self, server_name: str):
        """Automatically creates a tunnel for a newly created server (if playit is linked)."""
        port = self.get_server_port(server_name)
        # We run this in a thread because API polling can take 15 seconds
        def _create():
            try:
                self.playit_manager.get_or_create_tunnel(port)
            except Exception as e:
                logger.error(f"Auto-tunnel creation failed for {server_name}: {e}")
        threading.Thread(target=_create, daemon=True).start()

    def start_tunnel(self):
        port = self.get_server_port()
        threading.Thread(target=self.playit_manager.start, args=(port,), daemon=True).start()

    def stop_tunnel(self):
        self.playit_manager.stop(force=True)

    def stop_all(self):
        """Stops all running services (Server, Tunnel, etc.). Used for app exit."""
        self.stop_server()
        self.stop_tunnel()

    def reset_tunnel(self, mode="full"):
        self.playit_manager.reset(mode)

    def get_tunnel_ip(self):
        return self.playit_manager.current_address

    def link_playit_manually(self, setup_code: str):
        """Link the account manually using a setup code."""
        return self.playit_manager.link_manually(setup_code)

    # --- Scheduler & Lifecycle ---
    def _start_scheduler_loop(self):
        if self._scheduler_running: return
        self._scheduler_running = True
        
        def _loop():
            while self._scheduler_running:
                time.sleep(AppConfig.SCHEDULER_CHECK_INTERVAL)
                if not (self.server_runner and self.server_runner.running and self.current_server):
                    continue
                
                service = Scheduler(self.current_server)
                status = service.get_status()
                if not status: continue

                with self._restart_warnings_lock:
                    key, message = Scheduler.get_warning_message(status["remaining_seconds"], self.restart_warnings_sent)
                    if key:
                        self._send_system_message(message)
                        self.restart_warnings_sent.add(key)
                
                if status["is_due"]:
                    self.events.emit(ServerEvent.CONSOLE_LINE, "[System] Scheduled restart due. Initiating final countdown...")
                    self.events.emit(ServerEvent.REQUEST_RESTART, {"reason": "scheduled"})
                    service.update_last_run()
                    with self._restart_warnings_lock:
                        self.restart_warnings_sent.clear()

                self._check_auto_backup()

        self._scheduler_thread = threading.Thread(target=_loop, daemon=True)
        self._scheduler_thread.start()

    def _check_auto_backup(self):
        if not self.current_server:
            return
        with self._backup_lock:
            if self._backup_in_progress:
                return
            backup_sched = BackupScheduler(self.current_server)
            if not backup_sched.is_due():
                return
            self._backup_in_progress = True
        self.events.emit(ServerEvent.CONSOLE_LINE, "[System] Auto-backup due. Starting...")
        threading.Thread(target=self._run_auto_backup, daemon=True).start()

    def _run_auto_backup(self):
        try:
            bm = BackupManager(self.current_server)
            config = BackupScheduler(self.current_server).get_config()
            path, error = bm.create_backup(retention_count=config.get("retention_count"))
            if path:
                self.events.emit(ServerEvent.CONSOLE_LINE, f"[System] Auto-backup completed: {path.name}")
                self.events.emit(ServerEvent.BACKUP_COMPLETED, {"path": str(path), "server": self.current_server})
            else:
                self.events.emit(ServerEvent.CONSOLE_LINE, f"[Error] Auto-backup failed: {error}")
                self.events.emit(ServerEvent.BACKUP_FAILED, {"error": error, "server": self.current_server})
            BackupScheduler(self.current_server).mark_run()
        finally:
            with self._backup_lock:
                self._backup_in_progress = False

    def _send_system_message(self, message):
        """Sends a message to the console and in-game via CommandSanitizer."""
        if self.server_runner and self.server_runner.running:
            self.events.emit(ServerEvent.CONSOLE_LINE, f"[System] {message}")
            self.send_command(f"say {message}")

    def _handle_restart_request(self, data=None):
        """Handles internal requests to restart the server gracefully."""
        reason = (data or {}).get("reason", "manual")
        self.events.emit(ServerEvent.CONSOLE_LINE, f"[ZBBManager] Handling restart request (reason: {reason})...")
        
        def _restart():
            for i in [5, 4, 3, 2]:
                self._send_system_message(f"Restarting in {i}...")
                time.sleep(1)
            
            self._send_system_message("Restarting NOW!")
            
            # Auto-Backup Check
            scheduler = Scheduler(self.current_server)
            schedule = scheduler.get_schedule()
            if schedule and schedule.get("backup_on_restart", False):
                self.events.emit(ServerEvent.CONSOLE_LINE, "[System] Initiating async auto-backup before restart...")
                
                def _do_backup():
                    manager = BackupManager(self.current_server)
                    path, error = manager.create_backup()
                    if path:
                        self.events.emit(ServerEvent.CONSOLE_LINE, f"[System] Auto-backup completed: {os.path.basename(path)}")
                    else:
                        self.events.emit(ServerEvent.CONSOLE_LINE, f"[Error] Auto-backup failed: {error}")
                
                threading.Thread(target=_do_backup, daemon=True).start()
                # Give it a second to start archiving before we shut down the JVM
                time.sleep(1)
            
            self.stop_server()
            
            timeout = AppConfig.SERVER_STOP_TIMEOUT
            while timeout > 0:
                if not self.server_runner or not self.server_runner.running: break
                time.sleep(1)
                timeout -= 1
            
            time.sleep(5)
            # Re-start
            if self.start_server():
                # Wait briefly then report success
                time.sleep(AppConfig.SERVER_START_WAIT)
                if self.is_running():
                    self.events.emit(ServerEvent.CONSOLE_LINE, "[System] OK - Scheduled restart completed successfully! Server is back online.")
                else:
                    self.events.emit(ServerEvent.CONSOLE_LINE, "[System] ERROR: Server failed to restart automatically. Please check logs.")
            
        threading.Thread(target=_restart, daemon=True).start()

    def shutdown(self):
        """Cleanly stops all services on app exit."""
        self._scheduler_running = False
        self.stop_server()
        self._stop_monitors()
        self.stop_tunnel()
