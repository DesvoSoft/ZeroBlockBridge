import logging
import threading
import time
from collections import deque

from app.core.server_events import ServerEvent

logger = logging.getLogger(__name__)


class LagMonitor:
    """Observes console lines for lag spikes using a sliding window counter.

    When the spike count exceeds the threshold within the time window,
    emits a LAG_SPIKE event and resets the counter.

    Call observe_line(line) from the console callback to feed lines in.
    """

    def __init__(self, event_emitter, threshold=5, window_minutes=5):
        self._events = event_emitter
        self._threshold = threshold
        self._window = window_minutes * 60.0
        self._spikes = deque()
        # CONSOLE_LINE is emitted synchronously from whatever thread calls
        # EventBus.emit (reader thread, watchdog restart thread, tick thread's
        # send_command echo) — no thread affinity, so this deque needs the
        # same lock CircularBuffer already has for the identical reason.
        self._spikes_lock = threading.Lock()

        self._events.subscribe(ServerEvent.CONSOLE_LINE, self.observe_line)

    def observe_line(self, line: str):
        if self._is_spike(line):
            self._record_spike()

    def _is_spike(self, line: str) -> bool:
        return "Can't keep up!" in line or "Warning: TPS" in line

    def _record_spike(self):
        now = time.time()
        with self._spikes_lock:
            self._spikes.append(now)
            cutoff = now - self._window
            while self._spikes and self._spikes[0] <= cutoff:
                self._spikes.popleft()
            count = len(self._spikes)
            if count >= self._threshold:
                self._spikes.clear()
        if count >= self._threshold:
            logger.warning("Lag threshold exceeded: %d spikes in %.0fs", count, self._window)
            self._events.emit(ServerEvent.LAG_SPIKE, {
                "count": count,
                "window_seconds": self._window,
            })

    def stop(self) -> None:
        self._events.unsubscribe(ServerEvent.CONSOLE_LINE, self.observe_line)
