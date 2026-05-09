import logging
import threading
from typing import Optional

from app.server_events import EventBus, ServerEvent
from app.logic import ServerRunner, load_config
from app.services.watchdog import Watchdog
from app.services.lag_monitor import LagMonitor
from app.services.heartbeat import HeartbeatMonitor
from app.playit_manager import PlayitManager

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
        
        # External Services
        # Note: PlayitManager still uses callbacks. To be refactored to EventBus in ECO-04.
        self.playit_manager = PlayitManager(
            console_callback=lambda txt: self.events.emit(ServerEvent.TUNNEL_CONSOLE_LINE, txt),
            status_callback=lambda status, ip: self.events.emit(ServerEvent.TUNNEL_STATUS, {"status": status, "ip": ip}),
            claim_callback=lambda url: self.events.emit(ServerEvent.PLAYIT_CLAIM, url),
            on_ready_callback=lambda: self.events.emit(ServerEvent.READY) # Re-use ready or create specific
        )
        
        # Internal Subscriptions
        self.events.subscribe(ServerEvent.REQUEST_RESTART, self._handle_restart_request)

    def bootstrap(self):
        """Initializes non-blocking services on app startup."""
        logger.info("[ZBBManager] Bootstrapping core services...")
        # Future: Pre-warm cache (REND-01), Java Check
        pass

    def select_server(self, server_name: str):
        self.current_server = server_name

    def start_server(self):
        if not self.current_server:
            return False
        
        if self.server_runner and self.server_runner.running:
            self.events.emit(ServerEvent.CONSOLE_LINE, "[Error] A server is already running.")
            return False
            
        self._stop_monitors()
        
        config = load_config()
        ram = config.get("ram_allocation", "2G")
        
        self.server_runner = ServerRunner(self.current_server, ram, self.events)
        
        # Re-initialize monitors for the new runner
        self._setup_monitors(config)
        
        self.server_runner.start()
        return True

    def stop_server(self):
        if self.server_runner:
            self.server_runner.stop()

    def send_command(self, cmd: str):
        if self.server_runner and self.server_runner.running:
            self.server_runner.send_command(cmd)
            
    def _setup_monitors(self, config):
        self._lag_monitor = LagMonitor(event_emitter=self.events)
        
        self._heartbeat = HeartbeatMonitor(
            event_emitter=self.events,
            server_runner_getter=lambda: self.server_runner,
        )
        self._heartbeat.start()
        
        max_retries = config.get("watchdog_max_retries", 3)
        self._watchdog = Watchdog(
            self.server_runner, self.events,
            max_retries=max_retries,
        )
        self._watchdog.listen()

    def _stop_monitors(self):
        if self._heartbeat: self._heartbeat.stop()
        if self._watchdog: self._watchdog.stop()

    def _handle_restart_request(self, data):
        """Handles internal requests to restart the server gracefully."""
        self.events.emit(ServerEvent.CONSOLE_LINE, "[ZBBManager] Handling internal restart request...")
        # Graceful restart logic to be extracted from main.py's restart_server_sequence
        pass

    def shutdown(self):
        """Cleanly stops all services on app exit."""
        self.stop_server()
        self._stop_monitors()
        if self.playit_manager:
            self.playit_manager.stop()
