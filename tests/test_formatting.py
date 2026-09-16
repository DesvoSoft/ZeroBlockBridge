from app.ui.formatting import format_duration, format_memory, memory_tooltip


def test_format_duration_seconds():
    assert format_duration(0) == "0s"
    assert format_duration(45.9) == "45s"


def test_format_duration_minutes_and_hours():
    assert format_duration(60) == "1m"
    assert format_duration(59 * 60 + 59) == "59m"
    assert format_duration(3600) == "1h 0m"
    assert format_duration(4800) == "1h 20m"


def test_format_duration_days():
    assert format_duration(2 * 86400 + 3 * 3600 + 120) == "2d 3h"


def test_format_duration_negative_clamps_to_zero():
    assert format_duration(-5) == "0s"


def test_format_memory():
    assert format_memory(int(2.34 * 1024 ** 3)) == "RAM 2.3 GB"


def test_memory_tooltip_names_heap_cap():
    assert "2.0 GB" in memory_tooltip(2048)


def _measure(text):
    return len(text) * 10  # 10px per character


def test_clamp_lines_short_text_untouched():
    from app.ui.formatting import clamp_lines
    assert clamp_lines("fits on one line", _measure, 200) == "fits on one line"


def test_clamp_lines_cuts_to_two_lines_with_ellipsis():
    from app.ui.formatting import clamp_lines
    text = "aaaa bbbb cccc dddd eeee ffff"  # 3 lines at 100px (two words per line)
    result = clamp_lines(text, _measure, 100, max_lines=2)
    assert result.endswith("…")
    assert result.startswith("aaaa bbbb cccc")
    assert "eeee" not in result
    # the last kept line plus the ellipsis still fits the width
    assert _measure(result.split("bbbb ")[1]) <= 100
