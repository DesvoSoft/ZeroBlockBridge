import logging
import threading
import time
import os
from typing import Optional, Any, Protocol
from concurrent.futures import ThreadPoolExecutor

from app.core.server_events import EventBus, ServerEvent
from app.core.constants import ServerState
from app.services.backup_manager import BackupManager
from app.core.logic import ServerRunner, load_config, save_config, Scheduler, BackupScheduler
from app.services.watchdog import Watchdog
from app.services.lag_monitor import LagMonitor
from app.services.heartbeat import HeartbeatMonitor
from app.core.playit_manager import PlayitManager

from app.services.console_buffer import CircularBuffer
from app.core.app_config import AppConfig
from app.core.version_manager import VersionManager
from app.services.java_installer import JdkManagerInstance
from app.services.java_detector import JavaDetector, get_required_java
from app.services.bytecode_analyzer import analyze_jar_bytecode

logger = logging.getLogger(__name__)

from app.core.orchestrators import ServerOrchestrator, BackupOrchestrator, TunnelOrchestrator, SchedulerOrchestrator
from app.core.protocols import ServerOrchestratorProtocol, BackupOrchestratorProtocol, TunnelOrchestratorProtocol, SchedulerOrchestratorProtocol

class ZBBManager(ServerOrchestratorProtocol, BackupOrchestratorProtocol, TunnelOrchestratorProtocol, SchedulerOrchestratorProtocol):
    """
    Central orchestrator for ZeroBlockBridge logic.
    Decouples UI from the server lifecycle, background monitors, and tunneling.
    """
    def __init__(self, event_bus: EventBus) -> None:
        self.events = event_bus
        self.current_server: Optional[str] = None
        self.server_runner: Optional[ServerRunner] = None
        self.state: ServerState = ServerState.OFFLINE
        self.executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="ZBB_Worker")
        
        # Monitors
        self._watchdog: Optional[Watchdog] = None
        self._lag_monitor: Optional[LagMonitor] = None
        self._heartbeat: Optional[HeartbeatMonitor] = None
        
        # Scheduler State
        self._tick_thread: Optional[threading.Thread] = None
        self._tick_running = False
        
        # Start lock -- prevents concurrent start_server calls and protects _jdk_source
        self._start_lock = threading.Lock()
        self._restart_lock = threading.Lock()
        self._jdk_source: str = "unknown"
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

        self.events.subscribe(ServerEvent.READY, self._on_server_ready)

        # Orchestrators
        self.server_orchestrator = ServerOrchestrator(self)
        self.backup_orchestrator = BackupOrchestrator(self)
        self.tunnel_orchestrator = TunnelOrchestrator(self)
        self.scheduler_orchestrator = SchedulerOrchestrator(self)

    def _on_server_ready(self, data: Any = None) -> None:
        self.state = ServerState.ONLINE

    def _on_playit_status(self, status: str, ip: str) -> None:
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

    def _save_jdk_metadata(self, required_java: int, jdk_source: str) -> None:
        from app.core.logic import update_server_meta
        if not self.current_server:
            return
        from app.core.constants import SERVERS_DIR
        if not os.path.exists(os.path.join(SERVERS_DIR, self.current_server, "metadata.json")):
            return
        update_server_meta(self.current_server, {"required_java": required_java, "jdk_source": jdk_source})

    # --- Configuration ---
    def get_config(self) -> dict:
        return load_config()

    def update_config(self, key: str, value: Any) -> dict:
        config = load_config()
        config[key] = value
        save_config(config)
        return config

    # --- Core Server Operations ---
    def bootstrap(self) -> None:
        logger.info("[ZBBManager] Bootstrapping core services...")
        self._start_tick_loop()

    def select_server(self, server_name: str) -> None:
        self.current_server = server_name
        from app.core.logic import invalidate_meta_cache
        invalidate_meta_cache(server_name)

    def _auto_install_java(self, required_java: int) -> Optional[str]:
        try:
            java_bin = JdkManagerInstance.ensure_java(required_java)
            self._jdk_source = "portable"
            self._save_jdk_metadata(required_java, "portable")
            self.events.emit(ServerEvent.CONSOLE_LINE, f"[System] Using auto-installed JDK {required_java} at {java_bin}")
            self.events.emit(ServerEvent.STARTING, {"jdk_source": "portable", "required_java": required_java})
            return java_bin
        except Exception as e:
            logger.error("Auto-install failed: %s", e)
            return None

    def _launch_server(self, ram: str, java_bin: str, use_aikars: bool, required_java: int, config: dict) -> bool:
        self.server_runner = ServerRunner(self.current_server, ram, self.events, java_bin=java_bin, use_aikars=use_aikars)
        self._setup_monitors(config)
        self.server_runner.start()
        self._save_jdk_metadata(required_java, self._jdk_source)
        self.events.emit(ServerEvent.STARTING, {"jdk_source": self._jdk_source, "required_java": required_java})
        return True

    def _resolve_java_bin(self, server_dir: str, mc_version: str,
                          required_java_cached: Optional[int],
                          auto_install_jdk: bool) -> Optional[tuple[str, int]]:
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

    def start_server(self) -> bool:
        return self.server_orchestrator.start_server()



    def load_server_manually(self, folder_path: str) -> bool:
        """Imports an existing server by creating a link in the servers directory."""
        import os, json
        from app.core.constants import SERVERS_DIR
        from app.core.logic import create_junction
        
        server_name = os.path.basename(folder_path.rstrip("\\/"))
        link_path = os.path.join(SERVERS_DIR, server_name)
        
        if os.path.exists(link_path):
            raise Exception(f"A server named '{server_name}' already exists.")
            
        try:
            create_junction(folder_path, link_path)
                
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

    def stop_server(self) -> None:
        self.server_orchestrator.stop_server()

    def send_command(self, cmd: str) -> None:
        self.server_orchestrator.send_command(cmd)

    def is_running(self) -> bool:
        return self.server_orchestrator.is_running()

    # --- Monitors ---
    def _setup_monitors(self, config: dict) -> None:
        self._lag_monitor = LagMonitor(event_emitter=self.events)
        self._heartbeat = HeartbeatMonitor(
            event_emitter=self.events,
            server_runner_getter=lambda: self.server_runner,
        )
        self._heartbeat.start()
        max_retries = config.get("watchdog_max_retries", 3)
        self._watchdog = Watchdog(self.server_runner, self.events, max_retries=max_retries)
        self._watchdog.listen()

    def _stop_monitors(self) -> None:
        if self._heartbeat: self._heartbeat.stop()
        if self._watchdog: self._watchdog.stop()
        if self._lag_monitor: self._lag_monitor.stop()

    # --- Tunnel Management ---
    def get_server_port(self, server_name: Optional[str] = None) -> int:
        target = server_name or self.current_server
        if not target: return 25565
        from app.services.server_properties import load_server_properties
        props = load_server_properties(target)
        return int(props.get("server-port", 25565))

    def create_tunnel_for_server(self, server_name: str) -> None:
        self.tunnel_orchestrator.create_tunnel_for_server(server_name)

    def start_tunnel(self) -> None:
        self.tunnel_orchestrator.start_tunnel()

    def stop_tunnel(self) -> None:
        self.tunnel_orchestrator.stop_tunnel()

    def reset_tunnel(self, mode: str = "full") -> None:
        self.tunnel_orchestrator.reset_tunnel(mode)

    def get_tunnel_ip(self) -> Optional[str]:
        return self.tunnel_orchestrator.get_tunnel_ip()

    def link_playit_manually(self, setup_code: str) -> bool:
        """Link the account manually using a setup code."""
        return self.playit_manager.link_manually(setup_code)

    # --- Scheduler & Lifecycle ---
    def _start_tick_loop(self) -> None:
        self.scheduler_orchestrator._start_tick_loop()

    def _send_system_message(self, message: str) -> None:
        """Sends a message to the console and in-game via CommandSanitizer."""
        if self.server_runner and self.server_runner.running:
            self.events.emit(ServerEvent.CONSOLE_LINE, f"[System] {message}")
            self.send_command(f"say {message}")

    def _handle_restart_request(self, data: Optional[dict] = None) -> None:
        """Handles internal requests to restart the server gracefully."""
        def _restart():
            if not self._restart_lock.acquire(blocking=False):
                logger.warning("[ZBBManager] Restart already in progress, ignoring duplicate request.")
                return
            try:
                reason = (data or {}).get("reason", "manual")
                self.events.emit(ServerEvent.CONSOLE_LINE, f"[ZBBManager] Handling restart request (reason: {reason})...")

                for i in [5, 4, 3, 2]:
                    self._send_system_message(f"Restarting in {i}...")
                    time.sleep(1)

                self._send_system_message("Restarting NOW!")

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

                    future = self.executor.submit(_do_backup)
                    try:
                        future.result(timeout=300)
                    except Exception as e:
                        logger.error("Backup during restart failed or timed out: %s", e)
                    time.sleep(1)

                self.stop_server()

                timeout = AppConfig.SERVER_STOP_TIMEOUT
                while timeout > 0:
                    if not self.server_runner or not self.server_runner.running: break
                    time.sleep(1)
                    timeout -= 1

                time.sleep(5)
                if self.start_server():
                    time.sleep(AppConfig.SERVER_START_WAIT)
                    if self.is_running():
                        self.events.emit(ServerEvent.CONSOLE_LINE, "[System] OK - Scheduled restart completed successfully! Server is back online.")
                    else:
                        self.events.emit(ServerEvent.CONSOLE_LINE, "[System] ERROR: Server failed to restart automatically. Please check logs.")
            finally:
                self._restart_lock.release()

        self.executor.submit(_restart)

    def shutdown(self) -> None:
        """Cleanly stops all services on app exit.

        Independent subsystems (monitors, tunnel, tick-loop) are stopped
        concurrently while the Minecraft server gracefully drains, so the
        overall wall-clock time is dominated by the server stop rather
        than the sum of all timeouts.
        """
        # 1. Signal the tick loop to exit (non-blocking flag flip)
        self._tick_running = False

        # 2. Stop monitors immediately (they are just event listeners)
        self._stop_monitors()

        # 3. Stop tunnel and server concurrently — they are independent.
        #    NOTE: Do NOT set _shutdown_done = True here. The flag is set only
        #    after the tunnel thread completes. If join() times out before
        #    stop() finishes, the atexit backstop in PlayitManager will still
        #    fire the by-name taskkill to guarantee no orphaned playit.exe.
        tunnel_thread = threading.Thread(
            target=self._safe_stop_tunnel, daemon=True, name="ShutdownTunnel"
        )
        tunnel_thread.start()

        # Server stop (sends 'stop' command, waits for graceful exit)
        self.stop_server()
        if self.server_runner and self.server_runner.process:
            try:
                self.server_runner.process.wait(timeout=5)
            except Exception as e:
                logger.debug("Error waiting for server process: %s", e)

        # 4. Wait for tick thread — short timeout since it runs at 100ms
        if self._tick_thread and self._tick_thread.is_alive():
            self._tick_thread.join(timeout=2.0)

        # 5. Wait for tunnel teardown to finish (stop() blocks until process
        #    is confirmed dead, so this join is almost always instant).
        tunnel_thread.join(timeout=5.0)

        # 6. Mark playit as done AFTER the tunnel is confirmed stopped, so
        #    the atexit backstop doesn't skip the by-name kill prematurely.
        self.playit_manager._shutdown_done = True

        # 7. Drain the thread pool (15s max). wait=True can hang if a task
        #    is stuck (e.g., playit exponential-backoff sleep). Instead,
        #    shutdown(wait=False) and manually join with timeout.
        try:
            self.executor.shutdown(wait=False)
            for t in getattr(self.executor, '_threads', []):
                t.join(timeout=15.0)
        except Exception as e:
            logger.debug("Error shutting down executor: %s", e)

    def _safe_stop_tunnel(self) -> None:
        """Stop tunnel in a background thread, swallowing exceptions."""
        try:
            self.stop_tunnel()
        except Exception as e:
            logger.debug("Tunnel stop during shutdown: %s", e)
