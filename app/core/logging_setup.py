"""Application logging: rotating log file + hooks for uncaught exceptions.

The packaged Windows build runs with console=False, so sys.stderr is None
and a stderr-only handler silently drops every record. The log file is the
only diagnostic a user can send back.
"""

import logging
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG_FILENAME = "zbb.log"
LOG_MAX_BYTES = 2 * 1024 * 1024
LOG_BACKUP_COUNT = 3
LOG_FORMAT = "[%(asctime)s] [%(levelname)s] [%(threadName)s] [%(name)s] %(message)s"
LOG_DATEFMT = "%Y-%m-%d %H:%M:%S"

# Marks handlers installed here so a second configure_logging() call
# replaces them instead of duplicating every line.
_HANDLER_TAG = "_zbb_handler"

logger = logging.getLogger(__name__)


def configure_logging(log_dir: Path, level: int = logging.INFO) -> Path | None:
    """Attach a rotating file handler (and a stderr handler when a console
    exists) to the root logger and install uncaught-exception hooks.

    Returns the log file path, or None if the file could not be opened
    (read-only data dir) -- logging then falls back to stderr only.
    """
    root = logging.getLogger()
    root.setLevel(level)
    for handler in [h for h in root.handlers if getattr(h, _HANDLER_TAG, False)]:
        root.removeHandler(handler)
        handler.close()

    formatter = logging.Formatter(LOG_FORMAT, LOG_DATEFMT)
    log_path = Path(log_dir) / LOG_FILENAME
    file_ok = True
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_path, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT, encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        setattr(file_handler, _HANDLER_TAG, True)
        root.addHandler(file_handler)
    except OSError:
        file_ok = False

    if sys.stderr is not None:
        stream_handler = logging.StreamHandler(sys.stderr)
        stream_handler.setFormatter(formatter)
        setattr(stream_handler, _HANDLER_TAG, True)
        root.addHandler(stream_handler)

    install_exception_hooks()
    if not file_ok:
        logger.warning("Could not open log file %s; logging to console only", log_path)
        return None
    return log_path


def _log_uncaught(exc_type, exc_value, exc_tb) -> None:
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    logger.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_tb))


def _log_uncaught_thread(args: threading.ExceptHookArgs) -> None:
    if args.exc_type is SystemExit:
        return
    thread_name = args.thread.name if args.thread is not None else "unknown"
    logger.critical(
        "Uncaught exception in thread %s", thread_name,
        exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
    )


def install_exception_hooks() -> None:
    """Route uncaught exceptions (main thread and worker threads) to the log.
    Tk callback errors are handled by the root window's
    report_callback_exception, which Tk calls instead of sys.excepthook."""
    sys.excepthook = _log_uncaught
    threading.excepthook = _log_uncaught_thread


def log_tk_callback_exception(exc_type, exc_value, exc_tb) -> None:
    """Drop-in body for Tk.report_callback_exception."""
    logger.error("Unhandled exception in UI callback", exc_info=(exc_type, exc_value, exc_tb))
