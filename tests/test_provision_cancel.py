"""Cancelling a server creation stops it for real and leaves nothing behind.

Regression: Cancel used to only close the progress dialog while provisioning
kept running, so the server showed up a while later anyway.
"""
import subprocess
import sys
import threading
import time
from contextlib import ExitStack
from unittest.mock import patch

import pytest

from app.core import logic
from tests.test_provisioning import _Env


def _env(tmp_path, stack, cancel):
    env = _Env(tmp_path, stack)
    env.provisioner._cancel_event = cancel
    return env


def test_cancel_before_start_creates_nothing(tmp_path):
    cancel = threading.Event()
    cancel.set()
    with ExitStack() as stack:
        env = _env(tmp_path, stack, cancel)
        result = env.run()
    assert result.cancelled and not result.ok and result.error == "Cancelled"
    env.download.assert_not_called()
    assert list(env.servers_dir.iterdir()) == []


def test_cancel_during_jar_download_rolls_back(tmp_path):
    cancel = threading.Event()
    with ExitStack() as stack:
        env = _env(tmp_path, stack, cancel)

        def download_then_cancel(name, engine, version, progress_cb):
            (env.servers_dir / name / "server.jar.part").write_bytes(b"half")
            cancel.set()          # user clicks Cancel mid-download...
            progress_cb(0.5)      # ...the next chunk's progress report stops it
            pytest.fail("download continued after cancel")
        env.download.side_effect = download_then_cancel
        result = env.run()

    assert result.cancelled and result.rolled_back
    assert not (env.servers_dir / "srv").exists()
    env.scaffold.assert_not_called()
    assert env.tunnels == []
    assert any("Creation of 'srv' cancelled" in line for line in env.lines)


def test_cancel_after_a_step_stops_before_the_next(tmp_path):
    cancel = threading.Event()
    with ExitStack() as stack:
        env = _env(tmp_path, stack, cancel)
        original = env.download.side_effect

        def download_ok_then_cancel(*args):
            out = original(*args)
            cancel.set()
            return out
        env.download.side_effect = download_ok_then_cancel
        result = env.run()
    assert result.cancelled
    env.scaffold.assert_not_called()
    assert not (env.servers_dir / "srv").exists()


def test_cancel_in_existing_custom_folder_removes_only_our_files(tmp_path):
    custom = tmp_path / "elsewhere"
    (custom / "srv").mkdir(parents=True)
    (custom / "srv" / "mine.txt").write_text("user data")
    cancel = threading.Event()
    with ExitStack() as stack:
        env = _env(tmp_path, stack, cancel)

        def download_into_target(name, engine, version, progress_cb):
            (custom / "srv" / "server.jar.part").write_bytes(b"half")
            (custom / "srv" / "libraries").mkdir()
            cancel.set()
            progress_cb(0.5)
        env.download.side_effect = download_into_target
        result = env.run(location=str(custom))

    assert result.cancelled
    assert sorted(p.name for p in (custom / "srv").iterdir()) == ["mine.txt"]
    assert (custom / "srv" / "mine.txt").read_text() == "user data"


def test_failed_creation_in_existing_custom_folder_also_cleans_its_additions(tmp_path):
    custom = tmp_path / "elsewhere"
    (custom / "srv").mkdir(parents=True)
    (custom / "srv" / "mine.txt").write_text("user data")
    with ExitStack() as stack:
        env = _Env(tmp_path, stack)

        def partial_then_fail(name, engine, version, progress_cb):
            (custom / "srv" / "server.jar").write_bytes(b"x")
            return None
        env.download.side_effect = partial_then_fail
        result = env.run(location=str(custom))
    assert not result.ok and not result.cancelled
    assert sorted(p.name for p in (custom / "srv").iterdir()) == ["mine.txt"]


def test_cancelled_installer_is_reported_as_cancel(tmp_path):
    cancel = threading.Event()
    with ExitStack() as stack:
        env = _env(tmp_path, stack, cancel)
        seen = {}

        def killed_installer(name, version, progress_cb, java_bin="java", cancel_event=None):
            seen["cancel_event"] = cancel_event
            (env.servers_dir / name).mkdir(exist_ok=True)
            cancel.set()
            return None  # what install_forge returns once its process was killed
        env.install_forge.side_effect = killed_installer
        result = env.run(type="Forge", version="1.20.1")
    assert seen["cancel_event"] is cancel
    assert result.cancelled and not (env.servers_dir / "srv").exists()


def test_installer_gets_no_cancel_kwarg_without_an_event(tmp_path):
    with ExitStack() as stack:
        env = _Env(tmp_path, stack)  # fake installers have fixed signatures
        result = env.run(type="Fabric", version="1.20.1")
    assert result.ok and not result.cancelled


# ----------------------------------------------------------------------
# A running installer process is killed, not waited for
# ----------------------------------------------------------------------
@pytest.fixture
def spawned(monkeypatch):
    procs = []
    real_popen = subprocess.Popen

    def recording_popen(*args, **kwargs):
        proc = real_popen(*args, **kwargs)
        procs.append(proc)
        return proc
    monkeypatch.setattr(logic.subprocess, "Popen", recording_popen)
    return procs


def test_cancel_kills_a_running_installer_quickly(tmp_path, spawned):
    cancel = threading.Event()
    threading.Timer(0.5, cancel.set).start()
    start = time.monotonic()
    finished = logic._spawn_installer([sys.executable, "-c", "import time; time.sleep(60)"], str(tmp_path), cancel)
    assert finished is False
    assert time.monotonic() - start < 10
    assert spawned and spawned[0].poll() is not None  # the child is dead, not orphaned


@pytest.mark.skipif(sys.platform != "win32", reason="process-tree kill uses taskkill /T")
def test_cancel_kills_the_whole_process_tree(tmp_path, spawned):
    import psutil
    pid_file = tmp_path / "grandchild.pid"
    code = (
        "import subprocess, sys, time\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        f"open(r'{pid_file}', 'w').write(str(child.pid))\n"
        "time.sleep(60)\n"
    )
    cancel = threading.Event()
    thread = threading.Thread(target=lambda: logic._spawn_installer([sys.executable, "-c", code],
                                                                     str(tmp_path), cancel))
    thread.start()
    for _ in range(100):
        if pid_file.exists() and pid_file.read_text():
            break
        time.sleep(0.1)
    grandchild = int(pid_file.read_text())
    cancel.set()
    thread.join(timeout=15)
    assert not thread.is_alive()
    for _ in range(50):  # taskkill /T returns before Windows finishes tearing down
        if not psutil.pid_exists(grandchild):
            break
        time.sleep(0.1)
    assert not psutil.pid_exists(grandchild)


def test_cancellable_run_reports_success_and_failure(tmp_path):
    cancel = threading.Event()
    ok = logic._run_cancellable([sys.executable, "-c", "print('done')"], str(tmp_path), cancel)
    assert ok.returncode == 0 and "done" in ok.stdout
    with pytest.raises(subprocess.CalledProcessError):
        logic._run_cancellable([sys.executable, "-c", "import sys; sys.exit(3)"], str(tmp_path), cancel)


def test_spawn_retries_transient_lock_then_runs(tmp_path):
    cancel = threading.Event()
    calls = []

    def flaky(cmd, cwd, event, poll_interval=0.25):
        calls.append(1)
        if len(calls) == 1:
            err = OSError("locked")
            err.winerror = 32
            raise err
        return subprocess.CompletedProcess(cmd, 0, "", "")
    with patch.object(logic, "_run_cancellable", side_effect=flaky), patch.object(logic.time, "sleep"):
        assert logic._spawn_installer(["x"], str(tmp_path), cancel) is True
    assert len(calls) == 2


def test_run_installer_skips_spawn_when_already_cancelled(tmp_path):
    cancel = threading.Event()
    cancel.set()
    with patch.object(logic, "create_server_directory", return_value=str(tmp_path)), \
            patch.object(logic, "VersionManager") as vm, \
            patch.object(logic, "stream_to_file"), \
            patch.object(logic, "_spawn_installer") as spawn:
        vm.return_value.get_download_url.return_value = "https://example/installer.jar"
        assert logic._run_installer("srv", "Forge", "1.20.1", "forge-installer.jar", [],
                                    cancel_event=cancel) is None
    spawn.assert_not_called()
