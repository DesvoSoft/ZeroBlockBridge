"""Server console: a capped QPlainTextEdit fed in batches.

Lines arrive one event at a time (possibly thousands per second during a
modpack start); appending each one would relayout per line. They are queued
and flushed every ``FLUSH_MS`` as one block, and the view follows the end
only while the user hasn't scrolled up.
"""

from __future__ import annotations

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QPlainTextEdit

MAX_LINES = 1000
FLUSH_MS = 50


class ConsoleView(QPlainTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("console")
        self.setReadOnly(True)
        self.setMaximumBlockCount(MAX_LINES)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.setUndoRedoEnabled(False)
        self._pending: list[str] = []
        self.lines_shown = 0  # appended since start (the burst test reads it)
        self._timer = QTimer(self, interval=FLUSH_MS, singleShot=True)
        self._timer.timeout.connect(self.flush)

    def log(self, line: str) -> None:
        self._pending.append(line.rstrip("\n"))
        if not self._timer.isActive():
            self._timer.start()

    def flush(self) -> None:
        if not self._pending:
            return
        # Only the last MAX_LINES survive the cap anyway.
        pending, self._pending = self._pending, []
        bar = self.verticalScrollBar()
        follow = bar.value() >= bar.maximum() - 4
        self.appendPlainText("\n".join(pending[-MAX_LINES:]))
        self.lines_shown += len(pending)
        if follow:
            bar.setValue(bar.maximum())
