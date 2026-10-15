"""Console text that carries its own kind.

The consoles color ZBB's own error lines red. That used to be decided by
looking for words like "Error" or "failed" in the text, which breaks as
soon as the text is translated. A `ConsoleLine` states its kind instead;
it is still a plain `str` everywhere else (event payloads, buffers, tests).
"""

from enum import Enum


class LineKind(str, Enum):
    ERROR = "error"
    WARNING = "warning"


class ConsoleLine(str):
    kind: LineKind | None

    def __new__(cls, text: str, kind: LineKind | None = None):
        line = super().__new__(cls, text)
        line.kind = kind
        return line


def error_line(text: str) -> ConsoleLine:
    return ConsoleLine(text, LineKind.ERROR)


def warning_line(text: str) -> ConsoleLine:
    return ConsoleLine(text, LineKind.WARNING)


def kind_of(line) -> LineKind | None:
    """The kind a line was emitted with; None for plain text (process output)."""
    return getattr(line, "kind", None)
