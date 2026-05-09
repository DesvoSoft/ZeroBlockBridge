import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.services.lag_monitor import LagMonitor


class TestLagMonitor:
    def _make_monitor(self, threshold=3, window_minutes=1):
        self.emitted = []
        m = LagMonitor(
            event_emitter=type("E", (), {"emit": lambda self, e, d: emitted.append((e, d))})(),
            threshold=threshold, window_minutes=window_minutes,
        )
        emitted = self.emitted
        return m

    def test_no_spike_on_normal_line(self):
        emitted = []
        m = LagMonitor(
            event_emitter=type("E", (), {"emit": lambda self, e, d: emitted.append((e, d))})(),
            threshold=3, window_minutes=1,
        )
        m.observe_line("Some normal server output")
        assert len(emitted) == 0

    def test_cant_keep_up_detected(self):
        emitted = []
        m = LagMonitor(
            event_emitter=type("E", (), {"emit": lambda self, e, d: emitted.append((e, d))})(),
            threshold=1, window_minutes=1,
        )
        m.observe_line("[Server thread/WARN] Can't keep up! Is the server overloaded?")
        assert len(emitted) == 1

    def test_warning_tps_detected(self):
        emitted = []
        m = LagMonitor(
            event_emitter=type("E", (), {"emit": lambda self, e, d: emitted.append((e, d))})(),
            threshold=1, window_minutes=1,
        )
        m.observe_line("[Server thread/WARN] Warning: TPS is low")
        assert len(emitted) == 1

    def test_threshold_not_exceeded(self):
        emitted = []
        m = LagMonitor(
            event_emitter=type("E", (), {"emit": lambda self, e, d: emitted.append((e, d))})(),
            threshold=5, window_minutes=1,
        )
        for _ in range(3):
            m.observe_line("Can't keep up!")
        assert len(emitted) == 0

    def test_threshold_exceeded(self):
        emitted = []
        m = LagMonitor(
            event_emitter=type("E", (), {"emit": lambda self, e, d: emitted.append((e, d))})(),
            threshold=3, window_minutes=60,
        )
        for _ in range(3):
            m.observe_line("Can't keep up!")
        assert len(emitted) == 1

    def test_spikes_reset_after_emit(self):
        emitted = []
        m = LagMonitor(
            event_emitter=type("E", (), {"emit": lambda self, e, d: emitted.append((e, d))})(),
            threshold=2, window_minutes=60,
        )
        m.observe_line("Can't keep up!")
        m.observe_line("Can't keep up!")
        assert len(emitted) == 1
        m.observe_line("Can't keep up!")
        m.observe_line("Can't keep up!")
        assert len(emitted) == 2

    def test_no_spike_on_unrelated_warning(self):
        emitted = []
        m = LagMonitor(
            event_emitter=type("E", (), {"emit": lambda self, e, d: emitted.append((e, d))})(),
            threshold=1, window_minutes=1,
        )
        m.observe_line("[Server thread/WARN] Chunk load task took 123ms")
        assert len(emitted) == 0
