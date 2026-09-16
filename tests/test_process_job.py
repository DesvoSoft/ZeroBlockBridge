"""Tests for app/core/process_job.py (orphan prevention helpers)."""

import subprocess
import sys

import pytest

from app.core import process_job


class _FakeLibc:
    def __init__(self):
        self.calls = []

    def prctl(self, *args):
        self.calls.append(args)


def test_assign_to_job_is_noop_off_windows(monkeypatch):
    monkeypatch.setattr(process_job.platform, "system", lambda: "Linux")
    before = list(process_job._handles)
    process_job.assign_to_job(1234)
    assert process_job._handles == before


def test_assign_to_job_skips_non_int_pid(monkeypatch):
    monkeypatch.setattr(process_job.platform, "system", lambda: "Windows")
    before = list(process_job._handles)
    process_job.assign_to_job("1234")
    assert process_job._handles == before


@pytest.mark.skipif(sys.platform != "win32", reason="Job Objects are Windows-only")
def test_assign_to_job_keeps_job_handle_alive():
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        before = len(process_job._handles)
        process_job.assign_to_job(child.pid)
        assert len(process_job._handles) == before + 1
    finally:
        child.kill()
        child.wait(timeout=10)


@pytest.mark.skipif(sys.platform == "win32", reason="signal.SIGKILL does not exist on Windows")
def test_linux_preexec_sets_pdeathsig_and_keeps_running(monkeypatch):
    libc = _FakeLibc()
    monkeypatch.setattr(process_job, "_libc", libc)
    monkeypatch.setattr(process_job.os, "getppid", lambda: 4242)
    monkeypatch.setattr(process_job.os, "_exit", lambda code: pytest.fail("must not exit"))
    process_job.linux_preexec()
    assert libc.calls and libc.calls[0][0] == process_job._PR_SET_PDEATHSIG


def test_linux_preexec_exits_when_already_orphaned(monkeypatch):
    exits = []
    monkeypatch.setattr(process_job, "_libc", None)
    monkeypatch.setattr(process_job.os, "getppid", lambda: 1)
    monkeypatch.setattr(process_job.os, "_exit", exits.append)
    process_job.linux_preexec()
    assert exits == [1]
