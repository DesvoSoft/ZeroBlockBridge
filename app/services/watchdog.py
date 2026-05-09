import logging
import threading
import time

from app.server_events import ServerEvent

logger = logging.getLogger(__name__)

OOM_PATTERNS = [
    "OutOfMemoryError",
    "java.lang.OutOfMemoryError",
    "Unable to create native thread",
    "Metaspace",
    "GC overhead limit exceeded",
]

BOOT_CRASH_THRESHOLD = 5.0


class Watchdog:
    def __init__(self, server_runner, console_callback, event_emitter, max_retries=3,
                 backoff_base=5, stability_window=600, min_uptime_for_retry=10):
        self._runner = server_runner
        self._console = console_callback
        self._events = event_emitter
        self.max_retries = max_retries
        self._backoff_base = backoff_base
        self._stability_window = stability_window
        self._min_uptime = min_uptime_for_retry
        self.retry_count = 0
        self._stable_since = 0.0
        self._listening = False
        self._crash_reason = None

    @property
    def is_retry_exhausted(self):
        return self.retry_count >= self.max_retries

    def _reset_retry_if_stable(self):
        if self._stable_since and (time.time() - self._stable_since) >= self._stability_window:
            old = self.retry_count
            self.retry_count = 0
            logger.info("Watchdog: retry counter reset (stable for %ds)", self._stability_window)

    def listen(self):
        self._listening = True
        self._events.on(ServerEvent.STOPPED, self._on_stopped)
        self._events.on(ServerEvent.READY, self._on_ready)
        self._events.on(ServerEvent.STARTING, self._on_starting)

    def _on_starting(self, data=None):
        self._crash_reason = None

    def _on_ready(self, data=None):
        self._stable_since = time.time()
        self._reset_retry_if_stable()

    def _on_stopped(self, data=None):
        if not self._listening:
            return
        if data is None:
            data = {}
        exit_code = data.get("exit_code", -1)
        uptime = data.get("uptime", 0)

        if exit_code == 0:
            self._console("[Watchdog] Server stopped normally (exit code 0).")
            self.retry_count = 0
            return

        self._classify_crash(exit_code, uptime)
        self._console(
            f"[Watchdog] Server crashed (exit {exit_code}, {self._crash_reason}). "
            f"Retry {self.retry_count + 1}/{self.max_retries}"
        )
        self._events.emit(ServerEvent.CRASHED, {
            "exit_code": exit_code,
            "reason": self._crash_reason,
            "uptime": uptime,
            "retry": self.retry_count + 1,
        })

        if self.retry_count >= self.max_retries:
            self._console("[Watchdog] Max retries reached. Server will not auto-restart.")
            logger.warning("Watchdog: max retries (%d) exhausted for server", self.max_retries)
            return

        self.retry_count += 1
        backoff = self._compute_backoff()
        self._console(f"[Watchdog] Auto-restart in {backoff:.0f}s...")
        time.sleep(backoff)
        self._runner.start()
        self._events.emit(ServerEvent.RESTARTED, {"retry": self.retry_count})

    def _classify_crash(self, exit_code, uptime):
        if exit_code == 1 and uptime < self._min_uptime:
            self._crash_reason = "boot_crash"
        elif exit_code == 1 and uptime >= self._min_uptime:
            self._crash_reason = "runtime_crash"
        elif exit_code == 137 or exit_code == -9:
            self._crash_reason = "oom_kill"
        elif exit_code < 0:
            self._crash_reason = f"signal_{abs(exit_code)}"
        else:
            self._crash_reason = f"exit_{exit_code}"

    def _compute_backoff(self):
        return self._backoff_base * (2 ** (self.retry_count - 1))

    def stop(self):
        self._listening = False
