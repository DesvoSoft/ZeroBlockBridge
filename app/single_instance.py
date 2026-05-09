import atexit
import os
import sys
from pathlib import Path


class SingleInstanceLock:
    """Single-instance lock using a PID lockfile.

    On Windows uses OpenProcess/GetExitCodeProcess for PID-alive checks.
    On Unix uses os.kill(pid, 0). Falls back gracefully on errors.
    """

    def __init__(self, lockfile_path: Path):
        self._lockfile = lockfile_path
        self._is_owner = False

    def try_acquire(self) -> bool:
        """Try to acquire the lock. Returns True if acquired, False if another instance is running."""
        if self._check_existing():
            return False

        try:
            self._lockfile.parent.mkdir(parents=True, exist_ok=True)
            self._lockfile.write_text(str(os.getpid()))
            self._is_owner = True
            atexit.register(self.release)
            return True
        except OSError:
            return False

    def release(self):
        if self._is_owner and self._lockfile.exists():
            try:
                self._lockfile.unlink(missing_ok=True)
            except OSError:
                pass
            self._is_owner = False

    def _check_existing(self) -> bool:
        if not self._lockfile.exists():
            return False
        try:
            pid_str = self._lockfile.read_text().strip()
            if pid_str and self._is_pid_alive(int(pid_str)):
                return True
        except (ValueError, OSError):
            pass
        try:
            self._lockfile.unlink(missing_ok=True)
        except OSError:
            pass
        return False

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
            except Exception:
                return False
        else:
            try:
                os.kill(pid, 0)
                return True
            except OSError:
                return False
