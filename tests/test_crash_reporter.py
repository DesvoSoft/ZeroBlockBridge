import json
import threading
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.services.crash_reporter import CrashReporter
from app.services.console_buffer import CircularBuffer
from app.core.server_events import ServerEvent


class FakeEmitter:
    def __init__(self):
        self._subs = {}

    def subscribe(self, event, cb):
        self._subs.setdefault(event, []).append(cb)

    def unsubscribe(self, event, cb):
        self._subs.get(event, []).remove(cb)

    def emit(self, event, data=None):
        for cb in list(self._subs.get(event, [])):
            cb(data)


def _make_reporter(tmp_path, server_name="TestServer", meta=None, config=None, stderr=None):
    buf = CircularBuffer(max_size=200)
    for i in range(10):
        buf.append(f"[Server] line {i}")

    runner = MagicMock()
    stderr_lines = stderr or ["java.lang.OutOfMemoryError", "at server.Main.run()"]
    runner._stderr_buffer = stderr_lines
    runner.get_stderr_tail = lambda n: list(stderr_lines)[-n:] if n > 0 else []

    events = FakeEmitter()

    with patch("app.core.constants.SERVERS_DIR", str(tmp_path)):
        reporter = CrashReporter(
            events=events,
            server_name_getter=lambda: server_name,
            console_buffer_getter=lambda: buf,
            server_runner_getter=lambda: runner,
            config_getter=lambda: config or {"ram_allocation": "2G", "watchdog_max_retries": 3},
        )
    return reporter, events, buf, tmp_path


class TestCrashReporterWritesReport:
    def test_report_created_on_crashed_event(self, tmp_path):
        reporter, events, buf, base = _make_reporter(tmp_path)
        payload = {"reason": "oom", "exit_code": 1, "retry": 1, "uptime": 42.0}

        with patch("app.core.constants.SERVERS_DIR", str(base)), \
             patch("app.core.logic.get_server_meta", return_value={"version": "1.20.1", "type": "Fabric"}):
            events.emit(ServerEvent.CRASHED, payload)

        reports = list((base / "TestServer" / "crash_reports").glob("*.json"))
        assert len(reports) == 1

    def test_report_schema_version(self, tmp_path):
        reporter, events, buf, base = _make_reporter(tmp_path)
        with patch("app.core.constants.SERVERS_DIR", str(base)), \
             patch("app.core.logic.get_server_meta", return_value={}):
            events.emit(ServerEvent.CRASHED, {"reason": "crash"})

        report = json.loads(list((base / "TestServer" / "crash_reports").glob("*.json"))[0].read_text(encoding="utf-8"))
        assert report["schema_version"] == 1

    def test_report_contains_crash_fields(self, tmp_path):
        reporter, events, buf, base = _make_reporter(tmp_path)
        payload = {"reason": "oom", "exit_code": 137, "retry": 2, "uptime": 120.5}
        with patch("app.core.constants.SERVERS_DIR", str(base)), \
             patch("app.core.logic.get_server_meta", return_value={}):
            events.emit(ServerEvent.CRASHED, payload)

        report = json.loads(list((base / "TestServer" / "crash_reports").glob("*.json"))[0].read_text(encoding="utf-8"))
        assert report["crash"]["reason"] == "oom"
        assert report["crash"]["exit_code"] == 137
        assert report["crash"]["retry_attempt"] == 2
        assert report["crash"]["uptime_seconds"] == 120.5

    def test_report_contains_console_tail(self, tmp_path):
        reporter, events, buf, base = _make_reporter(tmp_path)
        with patch("app.core.constants.SERVERS_DIR", str(base)), \
             patch("app.core.logic.get_server_meta", return_value={}):
            events.emit(ServerEvent.CRASHED, {})

        report = json.loads(list((base / "TestServer" / "crash_reports").glob("*.json"))[0].read_text(encoding="utf-8"))
        assert isinstance(report["console_tail"], list)
        assert any("line" in l for l in report["console_tail"])

    def test_report_contains_stderr_tail(self, tmp_path):
        reporter, events, buf, base = _make_reporter(tmp_path, stderr=["OutOfMemoryError", "at Main.run()"])
        with patch("app.core.constants.SERVERS_DIR", str(base)), \
             patch("app.core.logic.get_server_meta", return_value={}):
            events.emit(ServerEvent.CRASHED, {})

        report = json.loads(list((base / "TestServer" / "crash_reports").glob("*.json"))[0].read_text(encoding="utf-8"))
        assert "OutOfMemoryError" in report["stderr_tail"]

    def test_report_contains_system_info(self, tmp_path):
        reporter, events, buf, base = _make_reporter(tmp_path)
        with patch("app.core.constants.SERVERS_DIR", str(base)), \
             patch("app.core.logic.get_server_meta", return_value={}):
            events.emit(ServerEvent.CRASHED, {})

        report = json.loads(list((base / "TestServer" / "crash_reports").glob("*.json"))[0].read_text(encoding="utf-8"))
        assert "os" in report["system_info"]
        assert "cpu_count" in report["system_info"]
        assert "ram_gb" in report["system_info"]

    def test_report_contains_server_info(self, tmp_path):
        reporter, events, buf, base = _make_reporter(tmp_path)
        with patch("app.core.constants.SERVERS_DIR", str(base)), \
             patch("app.core.logic.get_server_meta", return_value={"version": "1.21", "type": "Paper"}):
            events.emit(ServerEvent.CRASHED, {})

        report = json.loads(list((base / "TestServer" / "crash_reports").glob("*.json"))[0].read_text(encoding="utf-8"))
        assert report["server"]["name"] == "TestServer"
        assert report["server"]["version"] == "1.21"
        assert report["server"]["type"] == "Paper"

    def test_crash_reports_dir_created_automatically(self, tmp_path):
        reporter, events, buf, base = _make_reporter(tmp_path)
        reports_dir = base / "TestServer" / "crash_reports"
        assert not reports_dir.exists()

        with patch("app.core.constants.SERVERS_DIR", str(base)), \
             patch("app.core.logic.get_server_meta", return_value={}):
            events.emit(ServerEvent.CRASHED, {})

        assert reports_dir.is_dir()

    def test_no_crash_when_server_name_none(self, tmp_path):
        buf = CircularBuffer()
        events = FakeEmitter()
        with patch("app.core.constants.SERVERS_DIR", str(tmp_path)):
            reporter = CrashReporter(
                events=events,
                server_name_getter=lambda: None,
                console_buffer_getter=lambda: buf,
                server_runner_getter=lambda: None,
                config_getter=lambda: {},
            )
        with patch("app.core.constants.SERVERS_DIR", str(tmp_path)):
            events.emit(ServerEvent.CRASHED, {})

        assert not list(tmp_path.glob("**/*.json"))

    def test_stop_unsubscribes(self, tmp_path):
        reporter, events, buf, base = _make_reporter(tmp_path)
        reporter.stop()

        with patch("app.core.constants.SERVERS_DIR", str(base)), \
             patch("app.core.logic.get_server_meta", return_value={}):
            events.emit(ServerEvent.CRASHED, {})

        assert not list((base / "TestServer").glob("crash_reports/*.json"))


class TestCrashReporterRotation:
    def test_rotation_keeps_max_50(self, tmp_path):
        reporter, events, buf, base = _make_reporter(tmp_path)
        reports_dir = base / "TestServer" / "crash_reports"
        reports_dir.mkdir(parents=True, exist_ok=True)

        # Pre-populate 52 fake reports
        for i in range(52):
            p = reports_dir / f"2026-01-{i+1:02d}_00-00-00.json"
            p.write_text("{}", encoding="utf-8")

        reporter._rotate_reports(reports_dir)

        remaining = list(reports_dir.glob("*.json"))
        assert len(remaining) == 50
