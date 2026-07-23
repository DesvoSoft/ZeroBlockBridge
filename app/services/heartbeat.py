import logging
import time
import threading
from collections.abc import Callable
from typing import Optional

from app.core.server_events import ServerEvent
from app.core.protocols import EventEmitterProtocol, ServerRunnerProtocol

logger = logging.getLogger(__name__)

PLAYER_LIST_PATTERNS = [
    "players online",
    "There are",
    "No players online",
]


class HeartbeatMonitor:
    """Periodically checks server responsiveness by sending `list` and awaiting a reply.

    If the server is silent for `suspect_after` seconds, sends a probe.
    If the probe gets no response within `probe_timeout` seconds, classifies the
    server as a zombie and emits ZOMBIE_DETECTED.

    Call observe_line(line) from the console callback to feed lines in.
    """

    def __init__(self, event_emitter: EventEmitterProtocol, server_runner_getter: Callable[[], Optional[ServerRunnerProtocol]],
                 check_interval: int = 60, suspect_after: int = 300, probe_timeout: int = 15):
        self._events = event_emitter
        self._get_runner = server_runner_getter
        self._check_interval = check_interval
        self._suspect_after = suspect_after
        self._probe_timeout = probe_timeout
        self._lock = threading.Lock()
        self._last_output = time.time()
        self._last_probe = 0.0
        self._last_response = 0.0
        self._last_check = 0.0
        self._running = False
        self._waiting_for_probe = False

        self._events.subscribe(ServerEvent.CONSOLE_LINE, self.observe_line)

    def start(self) -> None:
        self._running = True

    def stop(self) -> None:
        self._running = False
        self._events.unsubscribe(ServerEvent.CONSOLE_LINE, self.observe_line)

    def observe_line(self, line: str) -> None:
        with self._lock:
            if not self._running: return
            self._last_output = time.time()
            if any(p in line for p in PLAYER_LIST_PATTERNS):
                self._last_response = time.time()
                self._waiting_for_probe = False

    def tick(self, now: float) -> None:
        # Decide under the lock; emit/send_command outside it. send_command echoes
        # the command as CONSOLE_LINE, which re-enters observe_line -> self._lock
        # (non-reentrant) and deadlocks the tick thread, then freezes any thread
        # that later emits CONSOLE_LINE (e.g. UI stop button).
        probe_silence = None
        zombie_silence = None
        runner = None
        with self._lock:
            if not self._running:
                return

            runner = self._get_runner()
            if not runner or not runner.running:
                return

            if self._waiting_for_probe:
                if now - self._last_probe >= self._probe_timeout:
                    if self._last_response < self._last_probe:
                        zombie_silence = now - self._last_output
                    self._waiting_for_probe = False
            elif now - self._last_check >= self._check_interval:
                self._last_check = now
                silence = now - self._last_output
                if silence >= self._suspect_after:
                    probe_silence = silence
                    self._last_probe = now
                    self._waiting_for_probe = True

        if zombie_silence is not None:
            logger.warning("Heartbeat: zombie detected (no response to probe)")
            self._events.emit(ServerEvent.ZOMBIE_DETECTED, {"silence_seconds": zombie_silence})
        if probe_silence is not None:
            logger.info("Heartbeat: server silent for %.0fs, sending probe", probe_silence)
            runner.send_command("list")
