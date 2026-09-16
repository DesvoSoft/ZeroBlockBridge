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


def format_memory(used_bytes: int) -> str:
    """'RAM 2.3 GB' — resident memory of the server process."""
    return f"RAM {used_bytes / (1024 ** 3):.1f} GB"


def memory_tooltip(limit_mb: int) -> str:
    """Why the readout can exceed the allocation: -Xmx only caps the Java heap."""
    return (f"Memory used by the server process.\n"
            f"Java heap is capped at {limit_mb / 1024:.1f} GB (the server's RAM setting); "
            f"total usage runs higher because Java also needs memory outside the heap.")
