import datetime
from unittest.mock import patch

import pytest

from app.core.server_events import ServerEvent
from app.services import player_history as ph
from tests.conftest import FakeEmitter

T0 = datetime.datetime(2026, 9, 16, 20, 0, 0)


class Clock:
    def __init__(self):
        self.now = T0

    def __call__(self):
        return self.now

    def advance(self, **kw):
        self.now += datetime.timedelta(**kw)


@pytest.fixture
def env(tmp_path):
    (tmp_path / "srv").mkdir()
    with patch.object(ph, "SERVERS_DIR", str(tmp_path)):
        bus, clock = FakeEmitter(), Clock()
        tracker = ph.PlayerHistoryTracker(bus, lambda: "srv", clock=clock)
        yield bus, clock, tracker


def test_join_leave_accumulates_playtime(env):
    bus, clock, _ = env
    bus.emit(ServerEvent.PLAYER_LIST, ["Steve"])
    clock.advance(minutes=30)
    bus.emit(ServerEvent.PLAYER_LIST, [])
    clock.advance(hours=1)
    bus.emit(ServerEvent.PLAYER_LIST, ["Steve"])
    clock.advance(minutes=15)
    bus.emit(ServerEvent.PLAYER_LIST, [])

    record = ph.load_history("srv")["Steve"]
    assert record["playtime_seconds"] == 45 * 60
    assert record["first_seen"] == "2026-09-16T20:00:00"
    assert record["last_seen"] == "2026-09-16T21:45:00"


def test_stop_closes_open_sessions(env):
    bus, clock, _ = env
    bus.emit(ServerEvent.PLAYER_LIST, ["Steve", "Alex"])
    clock.advance(minutes=10)
    bus.emit(ServerEvent.STOPPED, {"exit_code": 1})

    history = ph.load_history("srv")
    assert history["Steve"]["playtime_seconds"] == 600
    assert history["Alex"]["playtime_seconds"] == 600


def test_history_persists_across_trackers(env, tmp_path):
    bus, clock, tracker = env
    bus.emit(ServerEvent.PLAYER_LIST, ["Steve"])
    clock.advance(minutes=5)
    tracker.stop()

    bus2, clock2 = FakeEmitter(), Clock()
    clock2.now = T0 + datetime.timedelta(days=1)
    ph.PlayerHistoryTracker(bus2, lambda: "srv", clock=clock2)
    bus2.emit(ServerEvent.PLAYER_LIST, ["Steve"])
    clock2.advance(minutes=5)
    bus2.emit(ServerEvent.PLAYER_LIST, [])

    record = ph.load_history("srv")["Steve"]
    assert record["playtime_seconds"] == 600
    assert record["first_seen"] == "2026-09-16T20:00:00"


def test_no_server_selected_is_ignored(tmp_path):
    with patch.object(ph, "SERVERS_DIR", str(tmp_path)):
        bus = FakeEmitter()
        ph.PlayerHistoryTracker(bus, lambda: None)
        bus.emit(ServerEvent.PLAYER_LIST, ["Steve"])
    assert list(tmp_path.iterdir()) == []


def test_stop_unsubscribes(env):
    bus, clock, tracker = env
    tracker.stop()
    bus.emit(ServerEvent.PLAYER_LIST, ["Steve"])
    assert ph.load_history("srv") == {}
