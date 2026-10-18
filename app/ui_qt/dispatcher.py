"""Run API callbacks on the Qt GUI thread.

``AppApi`` emits events and task callbacks on worker threads and hands each
one to a *dispatcher*. This one emits a signal connected with
``Qt.QueuedConnection``: the call is posted to the event loop of the thread
the dispatcher lives in (the GUI thread), also when emitted from that
thread -- the same "later, on the UI thread" contract as Tk's ``after(0)``.
"""

from __future__ import annotations

import logging
from typing import Callable

from PySide6.QtCore import QObject, Qt, Signal, Slot

logger = logging.getLogger(__name__)


class QtDispatcher(QObject):
    _posted = Signal(object)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._posted.connect(self._run, Qt.ConnectionType.QueuedConnection)

    def __call__(self, fn: Callable[[], None]) -> None:
        try:
            self._posted.emit(fn)
        except RuntimeError:
            # The C++ object is gone (the app is quitting): drop the call,
            # like Tk's after() on a destroyed root.
            logger.debug("Dispatcher gone; dropped %r", fn)

    @Slot(object)
    def _run(self, fn: Callable[[], None]) -> None:
        try:
            fn()
        except Exception:  # noqa: BLE001 - one bad handler must not stop the loop
            logger.exception("UI callback failed")
