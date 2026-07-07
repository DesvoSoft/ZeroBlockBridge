import datetime
import json
import logging
import os
import platform
from pathlib import Path
from typing import Any, Callable, Optional

from app.core.server_events import ServerEvent

logger = logging.getLogger(__name__)

_MAX_REPORTS = 50
_CONSOLE_TAIL = 50
_STDERR_TAIL = 30
_SCHEMA_VERSION = 1


class CrashReporter:
    """Subscribes to CRASHED events and writes a JSON diagnostic report."""

    def __init__(
        self,
        events,
        server_name_getter: Callable[[], Optional[str]],
        console_buffer_getter: Callable[[], Any],
        server_runner_getter: Callable[[], Any],
        config_getter: Callable[[], dict],
    ) -> None:
        self._events = events
        self._get_server_name = server_name_getter
        self._get_console_buffer = console_buffer_getter
        self._get_server_runner = server_runner_getter
        self._get_config = config_getter
        self._events.subscribe(ServerEvent.CRASHED, self._on_crashed)

    def stop(self) -> None:
        self._events.unsubscribe(ServerEvent.CRASHED, self._on_crashed)

    def _on_crashed(self, payload: dict = None) -> None:
        payload = payload or {}
        try:
            self._write_report(payload)
        except Exception as e:
            logger.error("CrashReporter failed to write report: %s", e)

    def _write_report(self, payload: dict) -> None:
        from app.core.constants import SERVERS_DIR
        server_name = self._get_server_name()
        if not server_name:
            return

        reports_dir = Path(SERVERS_DIR) / server_name / "crash_reports"
        reports_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.datetime.now()
        filename = timestamp.strftime("%Y-%m-%d_%H-%M-%S") + ".json"
        report_path = reports_dir / filename

        server_meta = self._build_server_meta(server_name)
        console_tail = self._get_console_buffer().read_last_n(_CONSOLE_TAIL)
        stderr_tail = self._get_stderr_tail()

        watchdog_retries = payload.get("retry")
        config = self._get_config()

        report = {
            "schema_version": _SCHEMA_VERSION,
            "timestamp": timestamp.isoformat(timespec="seconds"),
            "server": server_meta,
            "crash": {
                "reason": payload.get("reason", "unknown"),
                "exit_code": payload.get("exit_code"),
                "retry_attempt": watchdog_retries,
                "uptime_seconds": payload.get("uptime"),
                "context": payload.get("context"),
                "detail": payload.get("detail"),
            },
            "stderr_tail": stderr_tail,
            "console_tail": console_tail,
            "system_info": {
                "os": platform.platform(),
                "python": platform.python_version(),
                "ram_gb": round(self._total_ram_gb(), 1),
                "cpu_count": os.cpu_count(),
            },
            "watchdog_state": {
                "max_retries": config.get("watchdog_max_retries", 3),
                "retry_attempt": watchdog_retries,
            },
        }

        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        logger.info("Crash report written: %s", report_path)
        self._rotate_reports(reports_dir)

    def _build_server_meta(self, server_name: str) -> dict:
        try:
            from app.core.logic import get_server_meta
            meta = get_server_meta(server_name) or {}
        except Exception:
            meta = {}
        config = self._get_config()
        return {
            "name": server_name,
            "version": meta.get("version", "unknown"),
            "type": meta.get("type", "unknown"),
            "ram": config.get("ram_allocation", "unknown"),
        }

    def _get_stderr_tail(self) -> list:
        try:
            runner = self._get_server_runner()
            if runner and hasattr(runner, "get_stderr_tail"):
                return runner.get_stderr_tail(_STDERR_TAIL)
        except Exception as e:
            logger.debug("CrashReporter: stderr tail unavailable: %s", e)
        return []

    def _total_ram_gb(self) -> float:
        try:
            import psutil
            return psutil.virtual_memory().total / (1024 ** 3)
        except Exception:
            return 0.0

    def _rotate_reports(self, reports_dir: Path) -> None:
        try:
            reports = sorted(reports_dir.glob("*.json"), key=lambda p: p.stat().st_mtime)
            for old in reports[:-_MAX_REPORTS]:
                old.unlink(missing_ok=True)
        except Exception as e:
            logger.warning("Failed to rotate crash reports: %s", e)
