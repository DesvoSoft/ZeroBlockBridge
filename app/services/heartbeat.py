import logging
import threading
import time
from collections.abc import Callable
from typing import Any

from app.core.server_events import ServerEvent

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

    def __init__(self, event_emitter: Any, server_runner_getter: Callable[[], Any],
                 check_interval: int = 60, suspect_after: int = 300, probe_timeout: int = 15):
        self._events = event_emitter
        self._get_runner = server_runner_getter
        self._check_interval = check_interval
        self._suspect_after = suspect_after
        self._probe_timeout = probe_timeout
        self._last_output = time.time()
        self._last_probe = 0.0
        self._last_response = 0.0
        self._running = False
        self._stop_ev = threading.Event()

        self._events.subscribe(ServerEvent.CONSOLE_LINE, self.observe_line)

    def start(self) -> None:
        self._running = True
        self._stop_ev.clear()
        threading.Thread(target=self._loop, daemon=True).start()

    def stop(self) -> None:
        self._running = False
        self._stop_ev.set()

    def observe_line(self, line: str) -> None:
        if not self._running: return
        self._last_output = time.time()
        if any(p in line for p in PLAYER_LIST_PATTERNS):
            self._last_response = time.time()

    def _loop(self):
        while self._running:
            runner = self._get_runner()
            if runner and runner.running:
                now = time.time()
                silence = now - self._last_output

                if silence >= self._suspect_after:
                    logger.info("Heartbeat: server silent for %.0fs, sending probe", silence)
                    runner.send_command("list")
                    self._last_probe = now
                    if self._stop_ev.wait(timeout=self._probe_timeout):
                        return

                    if self._last_response < self._last_probe:
                        logger.warning("Heartbeat: zombie detected (no response to probe)")
                        self._events.emit(ServerEvent.ZOMBIE_DETECTED, {
                            "silence_seconds": silence,
                        })

            if self._stop_ev.wait(timeout=self._check_interval):
                return
