from app.services.watchdog import Watchdog, _make_crash_payload
from app.core.server_events import ServerEvent
from conftest import FakeRunner, FakeEmitter


class TestWatchdogCrashClassification:
    def _make_watchdog(self, min_uptime=5):
        self.log = []
        self.notifications = []
        runner = FakeRunner()
        emitter = FakeEmitter()
        
        # Subscribe to simulate the old callbacks
        emitter.subscribe(ServerEvent.CONSOLE_LINE, lambda msg: self.log.append(msg))
        emitter.subscribe(ServerEvent.NOTIFICATION, lambda d: self.notifications.append((d.get("msg"), d.get("color"))))
        
        w = Watchdog(
            runner, emitter,
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

    def test_mod_dependency_error_populates_missing_mod_ids(self):
        w, emitter = self._make_watchdog()
        console = (
            "[main/INFO]: Fix: add [add:fabric-api-base 1 ([(-inf,inf)]), "
            "add:fabric-command-api-v2 1 ([(-inf,inf)]), "
            "add:fabric-lifecycle-events-v1 1 ([(-inf,inf)])], remove [], replace []\n"
            "[main/ERROR]: Incompatible mods found!"
        )
        payloads = []
        emitter.subscribe(ServerEvent.CRASHED, lambda d: payloads.append(d))
        w._on_stopped({"exit_code": 1, "uptime": 0.7, "stderr": "", "console": console})
        assert w._crash_reason == "mod_dependency_error"
        assert w._crash_missing_mod_ids == [
            "fabric-api-base", "fabric-command-api-v2", "fabric-lifecycle-events-v1",
        ]
        assert payloads[-1]["missing_mod_ids"] == [
            "fabric-api-base", "fabric-command-api-v2", "fabric-lifecycle-events-v1",
        ]

    def test_missing_mod_ids_reset_on_non_mod_crash(self):
        w, emitter = self._make_watchdog()
        console = "[main/INFO]: Fix: add [add:fabric-api-base 1 (...)], remove [], replace []\nIncompatible mods found!"
        w._on_stopped({"exit_code": 1, "uptime": 0.5, "stderr": "", "console": console})
        assert w._crash_missing_mod_ids == ["fabric-api-base"]
        w._on_stopped({"exit_code": 1, "uptime": 2, "stderr": "", "console": ""})
        assert w._crash_reason == "boot_crash"
        assert w._crash_missing_mod_ids == []


class TestExtractMissingModIds:
    def test_single_id(self):
        console = "[main/INFO]: Fix: add [add:fabric-api-base 1 ([(-inf,inf)])], remove [], replace []"
        assert Watchdog._extract_missing_mod_ids(console) == ["fabric-api-base"]

    def test_multiple_ids(self):
        console = (
            "[main/INFO]: Fix: add [add:fabric-api-base 1 (...), add:fabric-command-api-v2 1 (...)], "
            "remove [], replace []"
        )
        assert Watchdog._extract_missing_mod_ids(console) == [
            "fabric-api-base", "fabric-command-api-v2",
        ]

    def test_no_fix_line(self):
        console = "Incompatible mods found!\nSome unrelated log line"
        assert Watchdog._extract_missing_mod_ids(console) == []

    def test_empty_add_bracket(self):
        console = "[main/INFO]: Fix: add [], remove [], replace []"
        assert Watchdog._extract_missing_mod_ids(console) == []

    def test_empty_console(self):
        assert Watchdog._extract_missing_mod_ids("") == []

    def test_dedup(self):
        console = "[main/INFO]: Fix: add [add:fabric-api-base 1 (...), add:fabric-api-base 1 (...)], remove [], replace []"
        assert Watchdog._extract_missing_mod_ids(console) == ["fabric-api-base"]


class TestWatchdogRetryLogic:
    def _make_watchdog(self, max_retries=3):
        self.log = []
        runner = FakeRunner()
        emitter = FakeEmitter()
        
        emitter.subscribe(ServerEvent.CONSOLE_LINE, lambda msg: self.log.append(msg))
        
        w = Watchdog(
            runner, emitter,
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

    def test_zombie_kill_alive_process_then_restart(self):
        # Zombie = process alive but hung. _do_restart must kill it and start fresh.
        w, runner, emitter = self._make_watchdog()
        runner.running = True
        w.retry_count = 1
        w._do_restart("zombie", backoff=0)
        assert runner.stopped
        assert runner.started

    def test_crash_restart_aborts_if_process_alive(self):
        # Non-zombie context: process alive during backoff means a manual start
        # won the race — watchdog must not touch it.
        w, runner, emitter = self._make_watchdog()
        runner.running = True
        w.retry_count = 1
        w._do_restart("crash", backoff=0)
        assert not runner.stopped
        assert not runner.started

    def test_zombie_kill_stopped_event_swallowed(self):
        # The STOPPED caused by our own zombie kill must not be classified as
        # a new crash nor increment the retry counter.
        w, runner, emitter = self._make_watchdog()
        w.retry_count = 1
        w._zombie_kill_pending = True
        w._on_stopped({"exit_code": 1, "uptime": 500, "stderr": ""})
        assert w.retry_count == 1
        assert not w._zombie_kill_pending

    def test_retry_display_capped_at_max(self):
        w, runner, emitter = self._make_watchdog(max_retries=2)
        w.retry_count = 2
        payloads = []
        emitter.subscribe(ServerEvent.CRASHED, lambda d: payloads.append(d))
        w._on_stopped({"exit_code": 1, "uptime": 2, "stderr": ""})
        assert payloads[-1]["retry"] == 2

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
