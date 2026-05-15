import logging
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

        self._events.subscribe(ServerEvent.CONSOLE_LINE, self.observe_line)

    def observe_line(self, line: str):
        if self._is_spike(line):
            self._record_spike()

    def _is_spike(self, line: str) -> bool:
        return "Can't keep up!" in line or "Warning: TPS" in line

    def _record_spike(self):
        now = time.time()
        self._spikes.append(now)
        cutoff = now - self._window
        while self._spikes and self._spikes[0] <= cutoff:
            self._spikes.popleft()
        if len(self._spikes) >= self._threshold:
            logger.warning("Lag threshold exceeded: %d spikes in %.0fs", len(self._spikes), self._window)
            self._events.emit(ServerEvent.LAG_SPIKE, {
                "count": len(self._spikes),
                "window_seconds": self._window,
            })
            self._spikes.clear()
