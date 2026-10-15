"""Event subscriptions for UIs, on top of the core EventBus.

The core emits on whatever thread did the work. A UI may only touch its
widgets from its own thread, so every subscription goes through a
*dispatcher*: a callable that takes a zero-argument function and runs it
where the UI wants it. CustomTkinter passes ``lambda fn: root.after(0, fn)``,
a Qt UI a queued signal; tests and headless callers use ``direct``.
"""

import logging
import threading
from typing import Any, Callable, Optional

from app.core.server_events import EventBus

logger = logging.getLogger(__name__)

Dispatcher = Callable[[Callable[[], None]], None]


def direct(fn: Callable[[], None]) -> None:
    """Run on the emitting thread (headless use, tests)."""
    fn()


class Subscription:
    """One handler on one event. ``cancel()`` stops delivery at once, also
    for calls a dispatcher has queued but not run yet."""

    def __init__(self, bus: EventBus, event: str, handler: Callable[[Any], None], dispatcher: Dispatcher):
        self.event = event
        self._bus = bus
        self._handler = handler
        self._dispatcher = dispatcher
        self._active = True

    @property
    def active(self) -> bool:
        return self._active

    def _deliver(self, data: Any) -> None:
        if not self._active:
            return

        def run():
            if self._active:
                self._handler(data)

        self._dispatcher(run)

    def cancel(self) -> None:
        if not self._active:
            return
        self._active = False
        self._bus.unsubscribe(self.event, self._deliver)


class EventHub:
    """Subscribe to core events with a dispatcher (see the module docstring)."""

    def __init__(self, bus: EventBus, dispatcher: Dispatcher = direct):
        self.bus = bus
        self._dispatcher = dispatcher
        self._subscriptions: list[Subscription] = []
        self._lock = threading.Lock()

    @property
    def dispatcher(self) -> Dispatcher:
        return self._dispatcher

    def set_dispatcher(self, dispatcher: Dispatcher) -> None:
        """Default for subscriptions made from now on (the UI sets it once
        its main loop object exists)."""
        self._dispatcher = dispatcher

    def subscribe(self, event: str, handler: Callable[[Any], None],
                  dispatcher: Optional[Dispatcher] = None) -> Subscription:
        sub = Subscription(self.bus, event, handler, dispatcher or self._dispatcher)
        with self._lock:
            self._subscriptions = [s for s in self._subscriptions if s.active]
            self._subscriptions.append(sub)
        self.bus.subscribe(event, sub._deliver)
        return sub

    def close(self) -> None:
        """Cancel every subscription made through this hub."""
        with self._lock:
            subs, self._subscriptions = self._subscriptions, []
        for sub in subs:
            sub.cancel()
