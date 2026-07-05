import time
import threading
from unittest.mock import MagicMock, patch
from app.services.heartbeat import HeartbeatMonitor
from app.core.server_events import ServerEvent
from conftest import FakeEmitter, FakeRunner


class TestHeartbeatMonitor:
    def _make(self, check_interval=60, suspect_after=300, probe_timeout=15):
        self.emitter = FakeEmitter()
        self.runner = FakeRunner()
        self.runner.running = True
        self.runner.send_command = MagicMock()
        hb = HeartbeatMonitor(
            event_emitter=self.emitter,
            server_runner_getter=lambda: self.runner,
            check_interval=check_interval,
            suspect_after=suspect_after,
            probe_timeout=probe_timeout,
        )
        return hb

    def test_init_subscribes_to_console(self):
        hb = self._make()
        assert ServerEvent.CONSOLE_LINE in self.emitter._listeners
        assert hb.observe_line in self.emitter._listeners[ServerEvent.CONSOLE_LINE]

    def test_start_stop(self):
        hb = self._make()
        hb.start()
        assert hb._running is True
        hb.stop()
        assert hb._running is False

    def test_observe_line_updates_timestamp(self, monkeypatch):
        t = 1000.0
        monkeypatch.setattr(time, "time", lambda: t)
        hb = self._make()
        hb._running = True
        hb.observe_line("some console output")
        assert hb._last_output == t

    def test_player_list_pattern_updates_response(self, monkeypatch):
        t = 2000.0
        monkeypatch.setattr(time, "time", lambda: t)
        hb = self._make()
        hb._running = True
        hb.observe_line("There are 3 players online:")
        assert hb._last_response == t

    def test_ignored_when_not_running(self):
        hb = self._make()
        hb._running = False
        hb.observe_line("some line")
        last = hb._last_output
        hb.observe_line("another line")
        assert hb._last_output == last

    def test_loop_sends_probe_on_silence(self, monkeypatch):
        hb = self._make(suspect_after=10, probe_timeout=1, check_interval=60)
        hb._last_output = 0.0
        hb._last_check = 0.0
        hb._running = True
        
        # Advance time so silence > suspect_after and check_interval
        hb.tick(100.0)
        self.runner.send_command.assert_called_with("list")

    def test_zombie_detected_after_probe_timeout(self, monkeypatch):
        hb = self._make(suspect_after=10, probe_timeout=0.05, check_interval=60)
        hb._last_output = 0.0
        hb._last_check = 0.0
        hb._running = True
        
        hb.tick(100.0) # sends probe
        hb.tick(100.1) # waits, probe_timeout exceeded
        
        zombie_events = [e for e in self.emitter.events if e[0] == ServerEvent.ZOMBIE_DETECTED]
        assert len(zombie_events) == 1

    def test_no_zombie_when_response_received(self, monkeypatch):
        hb = self._make(suspect_after=10, probe_timeout=0.2, check_interval=60)
        hb._last_output = 0.0
        hb._last_check = 0.0
        hb._last_response = 0.0
        hb._running = True
        
        hb.tick(100.0) # sends probe
        
        # simulate response
        monkeypatch.setattr(time, "time", lambda: 100.1)
        hb.observe_line("There are 0 players online")
        
        hb.tick(100.1) # should not trigger zombie since waiting_for_probe was cleared
        hb.tick(100.3)
        
        zombie_events = [e for e in self.emitter.events if e[0] == ServerEvent.ZOMBIE_DETECTED]
        assert len(zombie_events) == 0

    def test_no_probe_if_runner_not_running(self):
        hb = self._make(check_interval=0.01)
        self.runner.running = False
        hb._running = True

        hb.tick(100.0)
        self.runner.send_command.assert_not_called()

    def test_probe_does_not_deadlock_on_console_echo(self):
        # Regression: ServerRunner.send_command emits CONSOLE_LINE ("> list"),
        # which synchronously re-enters observe_line. Old tick() held the
        # non-reentrant lock across send_command -> self-deadlock.
        hb = self._make(suspect_after=10, probe_timeout=1, check_interval=60)
        hb._last_output = 0.0
        hb._last_check = 0.0
        hb._running = True

        self.runner.send_command = MagicMock(
            side_effect=lambda cmd: hb.observe_line(f"> {cmd}")
        )

        t = threading.Thread(target=hb.tick, args=(100.0,), daemon=True)
        t.start()
        t.join(timeout=5)
        assert not t.is_alive(), "tick() deadlocked when send_command echoed CONSOLE_LINE"
        self.runner.send_command.assert_called_with("list")

    def test_zombie_emit_does_not_deadlock_on_reentrant_subscriber(self):
        # Same hazard for ZOMBIE_DETECTED: a subscriber that emits CONSOLE_LINE
        # (or otherwise re-enters observe_line) must not deadlock tick().
        hb = self._make(suspect_after=10, probe_timeout=0.05, check_interval=60)
        hb._last_output = 0.0
        hb._last_check = 0.0
        hb._running = True

        self.emitter.subscribe(
            ServerEvent.ZOMBIE_DETECTED,
            lambda data: hb.observe_line("subscriber side effect line"),
        )

        hb.tick(100.0)  # sends probe

        t = threading.Thread(target=hb.tick, args=(100.1,), daemon=True)
        t.start()
        t.join(timeout=5)
        assert not t.is_alive(), "tick() deadlocked emitting ZOMBIE_DETECTED under lock"
        zombie_events = [e for e in self.emitter.events if e[0] == ServerEvent.ZOMBIE_DETECTED]
        assert len(zombie_events) == 1
