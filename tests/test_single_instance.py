import os
import sys
import pytest
from unittest.mock import patch, MagicMock
from app.core.single_instance import SingleInstanceLock


@pytest.fixture
def lock_path(tmp_path):
    return tmp_path / "test.lock"


class TestSingleInstanceLock:
    def test_acquire_creates_lockfile(self, lock_path):
        lock = SingleInstanceLock(lock_path)
        assert lock.try_acquire() is True
        assert lock._is_owner is True
        assert lock_path.exists()

    def test_acquire_writes_pid(self, lock_path):
        lock = SingleInstanceLock(lock_path)
        lock.try_acquire()
        content = lock_path.read_text().strip()
        assert content == str(os.getpid())

    def test_second_instance_fails(self, lock_path):
        lock1 = SingleInstanceLock(lock_path)
        lock1.try_acquire()
        lock2 = SingleInstanceLock(lock_path)
        assert lock2.try_acquire() is False
        assert lock2._is_owner is False

    def test_release_removes_lockfile(self, lock_path):
        lock = SingleInstanceLock(lock_path)
        lock.try_acquire()
        lock.release()
        assert lock_path.exists() is False
        assert lock._is_owner is False

    def test_release_noop_if_not_owner(self, lock_path):
        lock = SingleInstanceLock(lock_path)
        lock.release()
        assert lock_path.exists() is False

    def test_stale_lockfile_replaced(self, lock_path):
        lock_path.write_text("99999")
        lock = SingleInstanceLock(lock_path)
        with patch.object(lock, "_is_pid_alive", return_value=False):
            assert lock.try_acquire() is True
            assert lock._is_owner is True
            assert lock_path.exists()

    def test_active_lockfile_rejected(self, lock_path):
        lock_path.write_text("99999")
        lock = SingleInstanceLock(lock_path)
        with patch.object(lock, "_is_pid_alive", return_value=True):
            assert lock.try_acquire() is False

    def test_missing_ok_unlink(self, lock_path):
        lock = SingleInstanceLock(lock_path)
        lock._is_owner = True
        lock.release()

    def test_lockfile_parent_created(self, tmp_path):
        nested = tmp_path / "subdir" / "nested" / "app.lock"
        lock = SingleInstanceLock(nested)
        assert lock.try_acquire() is True
        assert nested.exists()

    def test_corrupt_lockfile_treated_as_stale(self, lock_path):
        lock_path.write_text("not_a_number")
        lock = SingleInstanceLock(lock_path)
        assert lock.try_acquire() is True

    def test_double_release_safe(self, lock_path):
        lock = SingleInstanceLock(lock_path)
        lock.try_acquire()
        lock.release()
        lock.release()
        assert lock._is_owner is False


class TestIsPidAlive:
    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific test")
    def test_windows_dead(self):
        with patch("ctypes.windll.kernel32.OpenProcess", return_value=0):
            result = SingleInstanceLock._is_pid_alive(99999)
            assert result is False

    def test_linux_alive(self):
        with patch.object(sys, "platform", "linux"):
            with patch("os.kill", return_value=None):
                result = SingleInstanceLock._is_pid_alive(1)
                assert result is True

    def test_linux_dead(self):
        with patch.object(sys, "platform", "linux"):
            with patch("os.kill", side_effect=OSError):
                result = SingleInstanceLock._is_pid_alive(99999)
                assert result is False

    @pytest.mark.skipif(sys.platform != "win32", reason="Windows-specific test")
    def test_windows_exception_fallback(self):
        with patch("ctypes.windll.kernel32.OpenProcess", side_effect=Exception("access denied")):
            result = SingleInstanceLock._is_pid_alive(1234)
            assert result is False
