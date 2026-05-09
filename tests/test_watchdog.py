import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.services.watchdog import Watchdog, _make_crash_payload


class FakeRunner:
    def __init__(self):
        self.started = False
        self.running = False

    def start(self):
        self.started = True
        self.running = True


class FakeEmitter:
    def __init__(self):
        self.events = []

    def on(self, event, callback):
        pass

    def emit(self, event, data=None):
        self.events.append((event, data))


class TestWatchdogCrashClassification:
    def _make_watchdog(self, min_uptime=5):
        self.log = []
        self.notifications = []
        runner = FakeRunner()
        emitter = FakeEmitter()
        w = Watchdog(
            runner, lambda msg: self.log.append(msg), emitter,
            notification_callback=lambda msg, color: self.notifications.append((msg, color)),
            max_retries=3, backoff_base=1, min_uptime_for_retry=min_uptime,
        )
        w._listening = True
        return w, emitter

    def test_boot_crash(self):
        w, emitter = self._make_watchdog()
        w._on_stopped({"exit_code": 1, "uptime": 2, "stderr": ""})
        assert w._crash_reason == "boot_crash"

    def test_runtime_crash(self):
        w, _ = self._make_watchdog()
        w._on_stopped({"exit_code": 1, "uptime": 30, "stderr": ""})
        assert w._crash_reason == "runtime_crash"

    def test_oom_kill_exit_137(self):
        w, _ = self._make_watchdog()
        w._on_stopped({"exit_code": 137, "uptime": 60, "stderr": ""})
        assert w._crash_reason == "oom_kill"

    def test_oom_kill_exit_neg9(self):
        w, _ = self._make_watchdog()
        w._on_stopped({"exit_code": -9, "uptime": 60, "stderr": ""})
        assert w._crash_reason == "oom_kill"

    def test_jvm_config_error(self):
        w, _ = self._make_watchdog()
        w._on_stopped({
            "exit_code": 1, "uptime": 1, "stderr": "Error: A JNI error has occurred",
        })
        assert w._crash_reason == "jvm_config_error"

    def test_unsupported_class_version(self):
        w, _ = self._make_watchdog()
        w._on_stopped({
            "exit_code": 1, "uptime": 1,
            "stderr": "java.lang.UnsupportedClassVersionError: org/bukkit/craftbukkit/Main has been compiled by a more recent version of the Java Runtime",
        })
        assert w._crash_reason == "jvm_config_error"

    def test_out_of_memory_stderr(self):
        w, _ = self._make_watchdog()
        w._on_stopped({
            "exit_code": 1, "uptime": 120,
            "stderr": "java.lang.OutOfMemoryError: Java heap space",
        })
        assert w._crash_reason == "out_of_memory"

    def test_signal_segfault(self):
        w, _ = self._make_watchdog()
        w._on_stopped({"exit_code": -11, "uptime": 60, "stderr": ""})
        assert w._crash_reason == "signal_11"

    def test_exit_0_no_crash(self):
        w, emitter = self._make_watchdog()
        w.retry_count = 2
        w._on_stopped({"exit_code": 0, "uptime": 300, "stderr": ""})
        assert w.retry_count == 0

    def test_unknown_exit_code(self):
        w, _ = self._make_watchdog()
        w._on_stopped({"exit_code": 64, "uptime": 10, "stderr": ""})
        assert w._crash_reason == "exit_64"


class TestWatchdogRetryLogic:
    def _make_watchdog(self, max_retries=3):
        self.log = []
        runner = FakeRunner()
        emitter = FakeEmitter()
        w = Watchdog(
            runner, lambda msg: self.log.append(msg), emitter,
            max_retries=max_retries, backoff_base=1,
        )
        w._listening = True
        return w, runner, emitter

    def test_max_retries_exhausted(self):
        w, runner, emitter = self._make_watchdog(max_retries=2)
        w.retry_count = 2
        w._trigger_restart("crash")
        assert "Max retries" in self.log[-1]

    def test_retry_exhausted_after_crashes(self):
        w, runner, emitter = self._make_watchdog(max_retries=2)
        w.retry_count = 0
        w._on_stopped({"exit_code": 1, "uptime": 2, "stderr": ""})
        assert w.retry_count == 1
        w._on_stopped({"exit_code": 1, "uptime": 2, "stderr": ""})
        assert w.retry_count == 2
        w._on_stopped({"exit_code": 1, "uptime": 2, "stderr": ""})
        assert w.retry_count == 2

    def test_stability_reset(self):
        w, runner, emitter = self._make_watchdog()
        w.retry_count = 2
        w._stable_since = 0
        import time
        w._on_ready(None)
        assert w._stable_since > 0

    def test_zombie_restart(self):
        w, runner, emitter = self._make_watchdog()
        w.retry_count = 0
        w._on_zombie({"silence_seconds": 300})
        assert w.retry_count == 1

    def test_crashed_payload_shape(self):
        _, runner, emitter = self._make_watchdog()
        payload = _make_crash_payload(
            reason="boot_crash", exit_code=1, uptime=2, retry=1,
        )
        assert payload["reason"] == "boot_crash"
        assert payload["exit_code"] == 1
        assert payload["uptime"] == 2
        assert payload["retry"] == 1
        assert "silence_seconds" in payload
        assert "context" in payload

    def test_zombie_payload_shape(self):
        _, runner, emitter = self._make_watchdog()
        payload = _make_crash_payload(
            reason="zombie", silence_seconds=300, retry=1, context="zombie",
        )
        assert payload["reason"] == "zombie"
        assert payload["silence_seconds"] == 300
        assert payload["retry"] == 1
        assert payload["context"] == "zombie"
