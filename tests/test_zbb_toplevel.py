"""ZBBToplevel reveals once drawn (after CTk's titlebar re-show) and hides before teardown."""

import time
import tkinter as tk

import pytest

ctk = pytest.importorskip("customtkinter")

from unittest.mock import MagicMock  # noqa: E402

from app.ui.ui_components import ZBBToplevel, _FocusIfAlive  # noqa: E402


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


# ----------------------------------------------------------------------
# Deferred focus after a titlebar re-theme. CTk focuses the previously
# focused widget 10ms after re-showing the window; found testing the
# packaged exe, closing the wizard inside that window logged a TclError.
# ----------------------------------------------------------------------
def test_focus_goes_to_a_live_widget():
    widget = MagicMock()
    widget.winfo_exists.return_value = True
    _FocusIfAlive(widget).focus()
    widget.focus_set.assert_called_once()


def test_focus_on_a_destroyed_widget_is_dropped():
    widget = MagicMock()
    widget.winfo_exists.return_value = False
    _FocusIfAlive(widget).focus()
    widget.focus_set.assert_not_called()


def test_focus_error_from_tk_is_swallowed():
    widget = MagicMock()
    widget.winfo_exists.side_effect = tk.TclError('bad window path name ".!serverwizard"')
    _FocusIfAlive(widget).focus()  # must not raise


def test_titlebar_retheme_hands_ctk_a_guarded_focus(monkeypatch):
    seen = {}

    def fake_parent_retheme(self, color_mode):
        seen["focus"] = self.focus_get()

    monkeypatch.setattr(ctk.CTkToplevel, "_windows_set_titlebar_color", fake_parent_retheme)
    monkeypatch.setattr(ctk.CTkToplevel, "focus_get", lambda self: "button")
    window = ZBBToplevel.__new__(ZBBToplevel)
    ZBBToplevel._windows_set_titlebar_color(window, "dark")
    assert isinstance(seen["focus"], _FocusIfAlive)
    assert "focus_get" not in vars(window)  # the override is removed again


def test_titlebar_retheme_survives_reentry(monkeypatch):
    """CTk's re-theme calls update(), which can run another re-theme of the
    same window; the inner one must not break the outer one's cleanup."""
    calls = []

    def fake_parent_retheme(self, color_mode):
        calls.append(color_mode)
        if len(calls) == 1:
            ZBBToplevel._windows_set_titlebar_color(self, "light")

    monkeypatch.setattr(ctk.CTkToplevel, "_windows_set_titlebar_color", fake_parent_retheme)
    window = ZBBToplevel.__new__(ZBBToplevel)
    ZBBToplevel._windows_set_titlebar_color(window, "dark")  # must not raise
    assert calls == ["dark", "light"] and "focus_get" not in vars(window)
