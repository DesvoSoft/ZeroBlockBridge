"""Small pure text formatters for live UI readouts (headless-testable)."""

import datetime

from app.core.i18n import _, format_number


def format_duration(seconds: float) -> str:
    """Compact elapsed time: '45s', '12m', '1h 20m', '2d 3h'."""
    seconds = max(0, int(seconds))
    if seconds < 60:
        return _("{seconds}s").format(seconds=seconds)
    minutes = seconds // 60
    if minutes < 60:
        return _("{minutes}m").format(minutes=minutes)
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return _("{hours}h {minutes}m").format(hours=hours, minutes=minutes)
    days, hours = divmod(hours, 24)
    return _("{days}d {hours}h").format(days=days, hours=hours)


def clamp_lines(text: str, measure, width: int, max_lines: int = 2, ellipsis: str = "…") -> str:
    """Trim text so a greedy word wrap at `width` px fits in max_lines.

    measure(str) -> px width in the label's font. Mirrors how Tk wraps a label
    at its wraplength (break at spaces), so the label never grows a 3rd line.
    """
    words = text.split()
    lines, current = [], []
    for word in words:
        candidate = " ".join(current + [word])
        if current and measure(candidate) > width:
            lines.append(current)
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(current)
    if len(lines) <= max_lines:
        return text
    kept = lines[:max_lines]
    last = kept[-1]
    while last and measure(" ".join(last) + ellipsis) > width:
        last = last[:-1]
    kept[-1] = last
    return " ".join(w for line in kept for w in line) + ellipsis


def format_relative(iso_timestamp, now) -> str:
    """'just now', '5m ago', '3h ago', '2d ago', or the date for older times."""
    try:
        then = datetime.datetime.fromisoformat(iso_timestamp)
    except (TypeError, ValueError):
        return ""
    seconds = (now - then).total_seconds()
    if seconds < 60:
        return _("just now")
    if seconds < 3600:
        return _("{minutes}m ago").format(minutes=int(seconds // 60))
    if seconds < 86400:
        return _("{hours}h ago").format(hours=int(seconds // 3600))
    if seconds < 30 * 86400:
        return _("{days}d ago").format(days=int(seconds // 86400))
    return then.strftime("%Y-%m-%d")


def format_memory(used_bytes: int) -> str:
    """'RAM 2.3 GB' — resident memory of the server process."""
    return _("RAM {value} GB").format(value=format_number(used_bytes / (1024 ** 3), 1))


def memory_tooltip(limit_mb: int) -> str:
    """Why the readout can exceed the allocation: -Xmx only caps the Java heap."""
    return (f"Memory used by the server process.\n"
            f"Java heap is capped at {limit_mb / 1024:.1f} GB (the server's RAM setting); "
            f"total usage runs higher because Java also needs memory outside the heap.")


# Engines whose display name isn't plain title case.
_ENGINE_NAMES = {"neoforge": "NeoForge"}


def engine_name(server_type) -> str:
    """Display name of a server's engine from its metadata type. Older
    metadata stored lowercase types ("vanilla"); "NeoForge".title() would
    give "Neoforge", so known names are looked up first."""
    raw = str(server_type or "vanilla")
    return _ENGINE_NAMES.get(raw.lower(), raw if raw[:1].isupper() else raw.title())
