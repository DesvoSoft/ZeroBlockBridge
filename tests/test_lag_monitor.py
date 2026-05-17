from app.services.lag_monitor import LagMonitor
from conftest import FakeEmitter


class TestLagMonitor:
    def _make_monitor(self, threshold=3, window_minutes=1):
        self.emitted = []
        emitter = FakeEmitter()
        emitter.subscribe("lag_spike", lambda d: self.emitted.append(("lag_spike", d)))
        m = LagMonitor(
            event_emitter=emitter,
            threshold=threshold, window_minutes=window_minutes,
        )
        return m

    def test_no_spike_on_normal_line(self):
        m = self._make_monitor(threshold=3, window_minutes=1)
        m.observe_line("Some normal server output")
        assert len(self.emitted) == 0

    def test_cant_keep_up_detected(self):
        m = self._make_monitor(threshold=1, window_minutes=1)
        m.observe_line("[Server thread/WARN] Can't keep up! Is the server overloaded?")
        assert len(self.emitted) == 1

    def test_warning_tps_detected(self):
        m = self._make_monitor(threshold=1, window_minutes=1)
        m.observe_line("[Server thread/WARN] Warning: TPS is low")
        assert len(self.emitted) == 1

    def test_threshold_not_exceeded(self):
        m = self._make_monitor(threshold=5, window_minutes=1)
        for _ in range(3):
            m.observe_line("Can't keep up!")
        assert len(self.emitted) == 0

    def test_threshold_exceeded(self):
        m = self._make_monitor(threshold=3, window_minutes=60)
        for _ in range(3):
            m.observe_line("Can't keep up!")
        assert len(self.emitted) == 1

    def test_spikes_reset_after_emit(self):
        m = self._make_monitor(threshold=2, window_minutes=60)
        m.observe_line("Can't keep up!")
        m.observe_line("Can't keep up!")
        assert len(self.emitted) == 1
        m.observe_line("Can't keep up!")
        m.observe_line("Can't keep up!")
        assert len(self.emitted) == 2

    def test_no_spike_on_unrelated_warning(self):
        m = self._make_monitor(threshold=1, window_minutes=1)
        m.observe_line("[Server thread/WARN] Chunk load task took 123ms")
        assert len(self.emitted) == 0
