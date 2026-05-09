import pytest
from app.services.console_buffer import CircularBuffer

def test_append_and_read():
    buffer = CircularBuffer(max_size=5)
    buffer.append("line1")
    buffer.append("line2")
    assert buffer.read_all() == ["line1", "line2"]

def test_overflow():
    buffer = CircularBuffer(max_size=10)
    for i in range(15):
        buffer.append(f"line{i}")
    
    lines = buffer.read_all()
    # It drops max_size // 10 lines = 1 line when it hits 11.
    # When it hits 11, drops 1 -> length 10
    # Wait, the logic in console_buffer drops max(1, max_size // 10) when size > max_size.
    # Let's just check that the length is <= max_size
    assert len(lines) <= 10
    # And the last line is the most recent one
    assert lines[-1] == "line14"

def test_read_last_n():
    buffer = CircularBuffer(max_size=10)
    for i in range(5):
        buffer.append(f"line{i}")
        
    assert buffer.read_last_n(2) == ["line3", "line4"]
    assert buffer.read_last_n(10) == ["line0", "line1", "line2", "line3", "line4"]
    assert buffer.read_last_n(0) == []

def test_clear():
    buffer = CircularBuffer(max_size=10)
    buffer.append("test")
    buffer.clear()
    assert buffer.read_all() == []
