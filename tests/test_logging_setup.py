"""Tests for app/core/logging_setup.py (file logging + uncaught-exception hooks)."""

import logging
import sys
import threading
from logging.handlers import RotatingFileHandler

import pytest

from app.core import logging_setup
from app.core.logging_setup import (
    LOG_FILENAME,
    configure_logging,
    log_tk_callback_exception,
)


@pytest.fixture(autouse=True)
def restore_logging_state():
    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_level = root.level
    saved_excepthook = sys.excepthook
    saved_thread_hook = threading.excepthook
    yield
    for h in list(root.handlers):
        if h not in saved_handlers:
            root.removeHandler(h)
            h.close()
    root.setLevel(saved_level)
    sys.excepthook = saved_excepthook
    threading.excepthook = saved_thread_hook


def _flush_root():
    for h in logging.getLogger().handlers:
        h.flush()


def _zbb_file_handlers():
    return [h for h in logging.getLogger().handlers
            if isinstance(h, RotatingFileHandler) and getattr(h, logging_setup._HANDLER_TAG, False)]


def test_creates_log_file_in_given_dir(tmp_path):
    log_dir = tmp_path / "logs"
    path = configure_logging(log_dir)

    assert path == log_dir / LOG_FILENAME
    logging.getLogger("zbb.test").info("hello file")
    _flush_root()
    assert "hello file" in path.read_text(encoding="utf-8")


def test_rotation_limits_configured(tmp_path):
    configure_logging(tmp_path)
    (handler,) = _zbb_file_handlers()
    assert handler.maxBytes == logging_setup.LOG_MAX_BYTES
    assert handler.backupCount == logging_setup.LOG_BACKUP_COUNT


def test_reconfigure_does_not_duplicate_handlers(tmp_path):
    configure_logging(tmp_path)
    configure_logging(tmp_path)
    assert len(_zbb_file_handlers()) == 1


def test_no_stream_handler_without_console(tmp_path, monkeypatch):
    # Windowed PyInstaller build: sys.stderr is None.
    monkeypatch.setattr(sys, "stderr", None)
    configure_logging(tmp_path)
    stream_handlers = [h for h in logging.getLogger().handlers
                       if getattr(h, logging_setup._HANDLER_TAG, False)
                       and not isinstance(h, RotatingFileHandler)]
    assert stream_handlers == []


def test_unwritable_log_dir_returns_none(tmp_path, monkeypatch):
    def _fail(*args, **kwargs):
        raise PermissionError("read-only")
    monkeypatch.setattr(logging_setup, "RotatingFileHandler", _fail)
    assert configure_logging(tmp_path) is None


def test_main_thread_uncaught_exception_is_logged(tmp_path):
    path = configure_logging(tmp_path)
    try:
        raise ValueError("boom-main")
    except ValueError:
        sys.excepthook(*sys.exc_info())
    _flush_root()
    text = path.read_text(encoding="utf-8")
    assert "Uncaught exception" in text
    assert "boom-main" in text


def test_worker_thread_uncaught_exception_is_logged(tmp_path):
    path = configure_logging(tmp_path)

    def _worker():
        raise RuntimeError("boom-thread")

    t = threading.Thread(target=_worker, name="WorkerX")
    t.start()
    t.join()
    _flush_root()
    text = path.read_text(encoding="utf-8")
    assert "Uncaught exception in thread WorkerX" in text
    assert "boom-thread" in text


def test_tk_callback_exception_is_logged(tmp_path):
    path = configure_logging(tmp_path)
    try:
        raise KeyError("boom-tk")
    except KeyError:
        log_tk_callback_exception(*sys.exc_info())
    _flush_root()
    assert "boom-tk" in path.read_text(encoding="utf-8")
