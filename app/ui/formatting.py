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


def format_memory(used_bytes: int, limit_mb: int) -> str:
    """'RAM 1.2 / 2.0 GB' — used resident memory against the configured -Xmx."""
    used_gb = used_bytes / (1024 ** 3)
    limit_gb = limit_mb / 1024
    return f"RAM {used_gb:.1f} / {limit_gb:.1f} GB"
