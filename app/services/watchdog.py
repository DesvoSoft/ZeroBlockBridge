import logging
import re
import threading
import time
from typing import Any

from app.core.server_events import ServerEvent

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

MOD_ERROR_PATTERNS = [
    "Incompatible mods found!",
    "net.fabricmc.loader.impl.FormattedException",
    "missing a mandatory dependency",
]


def _make_crash_payload(reason, exit_code=None, uptime=None, retry=None, silence_seconds=None, context=None,
                         detail=None, missing_mod_ids=None):
    return {
        "reason": reason,
        "exit_code": exit_code,
        "uptime": uptime,
        "retry": retry,
        "silence_seconds": silence_seconds,
        "context": context,
        "detail": detail,
        "missing_mod_ids": missing_mod_ids or [],
    }


class Watchdog:
    def __init__(self, server_runner: Any, event_emitter: Any,
                 max_retries: int = 3,
                 backoff_base: int = 5, stability_window: int = 600, min_uptime_for_retry: int = 5):
        self._runner = server_runner
        self._events = event_emitter
        self.max_retries = max_retries
        self._backoff_base = backoff_base
        self._stability_window = stability_window
        self._min_uptime = min_uptime_for_retry
        self.retry_count = 0
        self._stable_since = 0.0
        self._listening = False
        self._crash_reason = None
        self._crash_detail = None
        self._crash_missing_mod_ids = []
        self._restart_thread = None

    @property
    def is_retry_exhausted(self) -> bool:
        return self.retry_count >= self.max_retries

    def _reset_retry_if_stable(self):
        if self._stable_since and (time.time() - self._stable_since) >= self._stability_window:
            self.retry_count = 0
            logger.info("Watchdog: retry counter reset (stable for %ds)", self._stability_window)

    def listen(self) -> None:
        self._listening = True
        self._events.subscribe(ServerEvent.STOPPED, self._on_stopped)
        self._events.subscribe(ServerEvent.READY, self._on_ready)
        self._events.subscribe(ServerEvent.STARTING, self._on_starting)
        self._events.subscribe(ServerEvent.ZOMBIE_DETECTED, self._on_zombie)

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
        console = data.get("console", "")

        if exit_code == 0:
            self._events.emit(ServerEvent.CONSOLE_LINE, "[Watchdog] Server stopped normally (exit code 0).")
            self.retry_count = 0
            return

        self._classify_crash(exit_code, uptime, stderr, console)
        next_retry = self.retry_count + 1
        msg = (
            f"[Watchdog] Server crashed (exit {exit_code}, {self._crash_reason}). "
            f"Retry {next_retry}/{self.max_retries}"
        )
        if self._crash_detail:
            msg += f" -- {self._crash_detail}"
        self._events.emit(ServerEvent.CONSOLE_LINE, msg)
        self._events.emit(ServerEvent.CRASHED, _make_crash_payload(
            reason=self._crash_reason, exit_code=exit_code,
            uptime=uptime, retry=next_retry, detail=self._crash_detail,
            missing_mod_ids=self._crash_missing_mod_ids,
        ))

        self._trigger_restart("crash")

    def _on_zombie(self, data=None):
        if not self._listening:
            return
        silence = (data or {}).get("silence_seconds", 0)
        next_retry = self.retry_count + 1
        self._events.emit(ServerEvent.CONSOLE_LINE, f"[Watchdog] Zombie server detected (silent {silence:.0f}s). Restarting...")
        self._events.emit(ServerEvent.CRASHED, _make_crash_payload(
            reason="zombie", silence_seconds=silence, retry=next_retry, context="zombie",
        ))
        self._trigger_restart("zombie")

    def _trigger_restart(self, context):
        if self.retry_count >= self.max_retries:
            self._events.emit(ServerEvent.CONSOLE_LINE, f"[Watchdog] Max retries ({self.max_retries}) reached. Will not auto-restart.")
            logger.warning("Watchdog: max retries (%d) exhausted (%s)", self.max_retries, context)
            return

        self.retry_count += 1
        backoff = self._compute_backoff()
        self._events.emit(ServerEvent.CONSOLE_LINE, f"[Watchdog] Auto-restart in {backoff:.0f}s (attempt {self.retry_count}/{self.max_retries})...")
        self._restart_thread = threading.Thread(
            target=self._do_restart, args=(context, backoff), daemon=True
        )
        self._restart_thread.start()

    def _do_restart(self, context, backoff):
        time.sleep(backoff)
        if not self._listening or not self._runner or self._runner.running:
            return
        self._runner.start()
        self._events.emit(ServerEvent.RESTARTED, {"retry": self.retry_count, "context": context})

    def _classify_crash(self, exit_code, uptime, stderr="", console=""):
        self._crash_detail = None
        self._crash_missing_mod_ids = []
        if self._match_stderr(stderr, JVM_ERROR_PATTERNS):
            self._crash_reason = "jvm_config_error"
        elif self._match_stderr(console, MOD_ERROR_PATTERNS):
            self._crash_reason = "mod_dependency_error"
            self._crash_detail = self._extract_mod_error_detail(console)
            self._crash_missing_mod_ids = self._extract_missing_mod_ids(console)
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
    def _extract_mod_error_detail(console):
        lines = console.splitlines()
        missing = [
            ln.split("] main/INFO]: ", 1)[-1].strip() if "] main/INFO]: " in ln else ln.strip()
            for ln in lines if "requires any version of" in ln
        ]
        if missing:
            return "; ".join(missing[:4])
        for ln in lines:
            if ln.strip().startswith("- Install "):
                return ln.strip()
        return None

    _FIX_ADD_LINE_RE = re.compile(r"Fix:\s*add\s*\[(.*?)\]\s*,\s*remove")
    _FIX_ADD_TOKEN_RE = re.compile(r"add:([A-Za-z0-9_\-\.]+)\s+")

    @staticmethod
    def _extract_missing_mod_ids(console):
        ids = []
        for line in console.splitlines():
            m = Watchdog._FIX_ADD_LINE_RE.search(line)
            if not m:
                continue
            for tok in Watchdog._FIX_ADD_TOKEN_RE.findall(m.group(1)):
                if tok not in ids:
                    ids.append(tok)
        return ids

    @staticmethod
    def _match_stderr(stderr, patterns):
        for p in patterns:
            if p.lower() in stderr.lower():
                return True
        return False

    def _compute_backoff(self):
        delay = self._backoff_base * (2 ** (self.retry_count - 1))
        return min(delay, 3600)  # cap at 1 hour

    def stop(self) -> None:
        self._listening = False
        self._events.unsubscribe(ServerEvent.STOPPED, self._on_stopped)
        self._events.unsubscribe(ServerEvent.READY, self._on_ready)
        self._events.unsubscribe(ServerEvent.STARTING, self._on_starting)
        self._events.unsubscribe(ServerEvent.ZOMBIE_DETECTED, self._on_zombie)
