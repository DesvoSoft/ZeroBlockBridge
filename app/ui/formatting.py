"""Small pure text formatters for live UI readouts (headless-testable)."""


def format_duration(seconds: float) -> str:
    """Compact elapsed time: '45s', '12m', '1h 20m', '2d 3h'."""
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    hours, minutes = divmod(minutes, 60)
    if hours < 24:
        return f"{hours}h {minutes}m"
    days, hours = divmod(hours, 24)
    return f"{days}d {hours}h"


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


def format_memory(used_bytes: int) -> str:
    """'RAM 2.3 GB' — resident memory of the server process."""
    return f"RAM {used_bytes / (1024 ** 3):.1f} GB"


def memory_tooltip(limit_mb: int) -> str:
    """Why the readout can exceed the allocation: -Xmx only caps the Java heap."""
    return (f"Memory used by the server process.\n"
            f"Java heap is capped at {limit_mb / 1024:.1f} GB (the server's RAM setting); "
            f"total usage runs higher because Java also needs memory outside the heap.")
