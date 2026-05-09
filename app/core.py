import logging
import threading
import time
import os
from typing import Optional

from app.server_events import EventBus, ServerEvent
from app.logic import ServerRunner, load_config, save_config, BackupManager, Scheduler
from app.services.watchdog import Watchdog
from app.services.lag_monitor import LagMonitor
from app.services.heartbeat import HeartbeatMonitor
from app.playit_manager import PlayitManager
from app.scheduler_service import SchedulerService
from app.services.console_buffer import CircularBuffer
from app.app_config import AppConfig

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
        self.restart_warnings_sent = set()
        
        # Buffers
        self.console_buffer = CircularBuffer(max_size=1000)
        self.tunnel_buffer = CircularBuffer(max_size=1000)
        
        # External Services
        self.playit_manager = PlayitManager(
            console_callback=lambda txt: self.events.emit(ServerEvent.TUNNEL_CONSOLE_LINE, txt),
            status_callback=self._on_playit_status,
            claim_callback=lambda url: self.events.emit(ServerEvent.PLAYIT_CLAIM, url),
            on_ready_callback=lambda: self.events.emit(ServerEvent.READY)
        )
        
        # Internal Subscriptions
        self.events.subscribe(ServerEvent.REQUEST_RESTART, self._handle_restart_request)
        self.events.subscribe(ServerEvent.CONSOLE_LINE, lambda line: self.console_buffer.append(line))
        self.events.subscribe(ServerEvent.TUNNEL_CONSOLE_LINE, lambda line: self.tunnel_buffer.append(line))

    def _on_playit_status(self, status, ip):
        display_ip = ip
        config = self.get_config()
        if status == "Online" and config.get("playit_dns"):
            display_ip = config["playit_dns"]
        self.events.emit(ServerEvent.TUNNEL_STATUS, {"status": status, "ip": display_ip})

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
        """Initializes non-blocking services on app startup."""
        logger.info("[ZBBManager] Bootstrapping core services...")
        self._start_scheduler_loop()

    def select_server(self, server_name: str):
        self.current_server = server_name

    def start_server(self):
        if not self.current_server:
            return False
        
        if self.server_runner and self.server_runner.running:
            self.events.emit(ServerEvent.CONSOLE_LINE, "[Error] A server is already running.")
            return False
            
        self._stop_monitors()
        
        config = self.get_config()
        ram = config.get("ram_allocation", "2G")
        
        self.server_runner = ServerRunner(self.current_server, ram, self.events)
        
        # Subscriptions moved from UI
        # (EventBus fan-out handles the UI now, we just pass the events bus)
        
        self._setup_monitors(config)
        self.server_runner.start()
        
        # Let UI know
        self.events.emit(ServerEvent.STARTING)
        return True

    def stop_server(self):
        if self.server_runner:
            self.server_runner.stop()

    def send_command(self, cmd: str):
        if self.server_runner and self.server_runner.running:
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
        from app.logic import read_properties
        from app.constants import SERVERS_DIR
        path = os.path.join(SERVERS_DIR, target, "server.properties")
        if os.path.exists(path):
            props = read_properties(path)
            return int(props.get("server-port", 25565))
        return 25565

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
        self.playit_manager.stop()

    def reset_tunnel(self):
        self.playit_manager.reset()
        self.remove_config_key("playit_dns")

    def get_tunnel_ip(self):
        return self.playit_manager.current_address

    # --- Scheduler & Lifecycle ---
    def _start_scheduler_loop(self):
        if self._scheduler_running: return
        self._scheduler_running = True
        
        def _loop():
            while self._scheduler_running:
                time.sleep(AppConfig.SCHEDULER_CHECK_INTERVAL)
                if not (self.server_runner and self.server_runner.running and self.current_server):
                    continue
                
                service = SchedulerService(self.current_server)
                status = service.get_status()
                if not status: continue

                key, message = service.get_warning_message(status["remaining_seconds"], self.restart_warnings_sent)
                if key:
                    self._send_system_message(message)
                    self.restart_warnings_sent.add(key)
                
                if status["is_due"]:
                    self.events.emit(ServerEvent.CONSOLE_LINE, "[System] Scheduled restart due. Initiating final countdown...")
                    self.events.emit(ServerEvent.REQUEST_RESTART, {"reason": "scheduled"})
                    service.scheduler.update_last_run()
                    self.restart_warnings_sent.clear()

        self._scheduler_thread = threading.Thread(target=_loop, daemon=True)
        self._scheduler_thread.start()

    def _send_system_message(self, message):
        """Sends a message to the console and in-game."""
        if self.server_runner and self.server_runner.running:
            self.events.emit(ServerEvent.CONSOLE_LINE, f"[System] {message}")
            self.server_runner.send_command(f"say {message}")

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
                self.events.emit(ServerEvent.CONSOLE_LINE, "[System] Performing auto-backup before restart...")
                self._send_system_message("Performing auto-backup...")
                manager = BackupManager(self.current_server)
                path, error = manager.create_backup()
                if path:
                    self.events.emit(ServerEvent.CONSOLE_LINE, f"[System] Auto-backup created: {os.path.basename(path)}")
                else:
                    self.events.emit(ServerEvent.CONSOLE_LINE, f"[Error] Auto-backup failed: {error}")
            
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
                    self.events.emit(ServerEvent.CONSOLE_LINE, "[System] ✓ Scheduled restart completed successfully! Server is back online.")
                else:
                    self.events.emit(ServerEvent.CONSOLE_LINE, "[System] ✗ ERROR: Server failed to restart automatically. Please check logs.")
            
        threading.Thread(target=_restart, daemon=True).start()

    def shutdown(self):
        """Cleanly stops all services on app exit."""
        self._scheduler_running = False
        self.stop_server()
        self._stop_monitors()
        if self.playit_manager:
            self.playit_manager.stop()
