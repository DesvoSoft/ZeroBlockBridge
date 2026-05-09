import logging
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

JVM_ERROR_PATTERNS = [
    "Error: Could not find or load main class",
    "Error: A JNI error has occurred",
    "UnsupportedClassVersionError",
    "java.lang.UnsupportedClassVersionError",
    "Unrecognized option",
    "Unrecognized VM option",
    "Could not reserve enough space",
    "java.lang.NoClassDefFoundError",
]

BOOT_CRASH_THRESHOLD = 5.0


class Watchdog:
    def __init__(self, server_runner, console_callback, event_emitter,
                 notification_callback=None, max_retries=3,
                 backoff_base=5, stability_window=600, min_uptime_for_retry=10):
        self._runner = server_runner
        self._console = console_callback
        self._events = event_emitter
        self._notify = notification_callback
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
        self._events.on(ServerEvent.ZOMBIE_DETECTED, self._on_zombie)

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
        stderr = data.get("stderr", "")

        if exit_code == 0:
            self._console("[Watchdog] Server stopped normally (exit code 0).")
            self.retry_count = 0
            return

        self._classify_crash(exit_code, uptime, stderr)
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
        if self._notify:
            self._notify(
                f"Server crashed: {self._crash_reason}",
                color="red"
            )

        self._trigger_restart("crash")

    def _on_zombie(self, data=None):
        if not self._listening:
            return
        silence = (data or {}).get("silence_seconds", 0)
        self._console(f"[Watchdog] Zombie server detected (silent {silence:.0f}s). Restarting...")
        self._events.emit(ServerEvent.CRASHED, {
            "reason": "zombie",
            "silence_seconds": silence,
        })
        if self._notify:
            self._notify("Server unresponsive (zombie). Restarting...", color="orange")
        self._trigger_restart("zombie")

    def _trigger_restart(self, context):
        if self.retry_count >= self.max_retries:
            self._console(f"[Watchdog] Max retries ({self.max_retries}) reached. Will not auto-restart.")
            logger.warning("Watchdog: max retries (%d) exhausted (%s)", self.max_retries, context)
            if self._notify:
                self._notify("Max retries reached. Server will not restart.", color="red")
            return

        self.retry_count += 1
        backoff = self._compute_backoff()
        self._console(f"[Watchdog] Auto-restart in {backoff:.0f}s (attempt {self.retry_count}/{self.max_retries})...")
        time.sleep(backoff)
        self._runner.start()
        self._events.emit(ServerEvent.RESTARTED, {"retry": self.retry_count, "context": context})
        if self._notify:
            self._notify(
                f"Server restarting (attempt {self.retry_count}/{self.max_retries})",
                color="orange"
            )

    def _classify_crash(self, exit_code, uptime, stderr=""):
        if self._match_stderr(stderr, JVM_ERROR_PATTERNS):
            self._crash_reason = "jvm_config_error"
        elif self._match_stderr(stderr, OOM_PATTERNS):
            self._crash_reason = "out_of_memory"
        elif exit_code == 137 or exit_code == -9:
            self._crash_reason = "oom_kill"
        elif exit_code == 1 and uptime < self._min_uptime:
            self._crash_reason = "boot_crash"
        elif exit_code == 1 and uptime >= self._min_uptime:
            self._crash_reason = "runtime_crash"
        elif exit_code < 0:
            self._crash_reason = f"signal_{abs(exit_code)}"
        else:
            self._crash_reason = f"exit_{exit_code}"

    @staticmethod
    def _match_stderr(stderr, patterns):
        for p in patterns:
            if p.lower() in stderr.lower():
                return True
        return False

    def _compute_backoff(self):
        return self._backoff_base * (2 ** (self.retry_count - 1))

    def stop(self):
        self._listening = False
