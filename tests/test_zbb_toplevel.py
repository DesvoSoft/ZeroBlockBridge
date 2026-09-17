"""ZBBToplevel reveals once drawn (after CTk's titlebar re-show) and hides before teardown."""

import time
import tkinter as tk

import pytest

ctk = pytest.importorskip("customtkinter")

from app.ui.ui_components import ZBBToplevel  # noqa: E402


@pytest.fixture
def root():
    try:
        win = ctk.CTk()
    except tk.TclError as e:
        pytest.skip(f"no display: {e}")
    win.geometry("300x200")
    yield win
    win.destroy()


def _pump_until(root, condition, timeout=3.0):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        root.update()
        if condition():
            return True
    return False


def test_window_becomes_opaque_after_resizable_refresh(root):
    win = ZBBToplevel(root)
    ctk.CTkLabel(win, text="hello").pack()
    win.resizable(False, False)
    assert float(win.attributes("-alpha")) == 0.0

    assert _pump_until(root, lambda: float(win.attributes("-alpha")) >= 1.0)
    assert win.winfo_ismapped()
    assert win._titlebar_settled()
    win.destroy()


def test_destroy_withdraws_first(root):
    win = ZBBToplevel(root)
    states = []
    original = win.withdraw
    win.withdraw = lambda: (states.append("withdrawn"), original())
    win.destroy()
    assert states == ["withdrawn"]
