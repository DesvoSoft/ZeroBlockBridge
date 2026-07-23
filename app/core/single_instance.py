import atexit
import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)


class SingleInstanceLock:
    """Single-instance lock using atomic PID lockfile creation.

    Uses O_CREAT | O_EXCL on both Unix and Windows (Python 3) for
    atomic create-or-fail semantics, eliminating the TOCTOU race.
    """

    def __init__(self, lockfile_path: Path):
        self._lockfile = lockfile_path
        self._is_owner = False

    def try_acquire(self) -> bool:
        try:
            self._lockfile.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(str(self._lockfile), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
            try:
                os.write(fd, str(os.getpid()).encode())
            finally:
                os.close(fd)
            self._is_owner = True
            atexit.register(self.release)
            return True
        except FileExistsError:
            return self._check_existing()
        except OSError:
            return False

    def release(self) -> None:
        if self._is_owner and self._lockfile.exists():
            try:
                self._lockfile.unlink(missing_ok=True)
            except OSError as e:
                logger.debug("Lockfile unlink ignored: %s", e)
            self._is_owner = False

    def _check_existing(self) -> bool:
        try:
            pid_str = self._lockfile.read_text().strip()
            if pid_str and self._is_pid_alive(int(pid_str)):
                return False
        except (ValueError, OSError):
            logger.debug("Stale lockfile detected, removing")
        try:
            self._lockfile.unlink(missing_ok=True)
        except OSError as e:
            logger.warning("Failed to remove stale lockfile: %s", e)
        return self.try_acquire()

    @staticmethod
    def _is_pid_alive(pid: int) -> bool:
        if sys.platform == "win32":
            try:
                import ctypes
                kernel32 = ctypes.windll.kernel32
                handle = kernel32.OpenProcess(0x400, False, pid)
                if not handle:
                    return False
                try:
                    exit_code = ctypes.c_uint32()
                    result = kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
                    return bool(result) and exit_code.value == 259
                finally:
                    kernel32.CloseHandle(handle)
            except Exception as e:
                logger.debug("PID check error: %s", e)
                return False
        else:
            try:
                os.kill(pid, 0)
                return True
            except OSError:
                return False
