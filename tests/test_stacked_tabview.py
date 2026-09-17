"""StackedTabview switches tabs by restacking, never by unmapping them."""

import tkinter as tk

import pytest

ctk = pytest.importorskip("customtkinter")

from app.ui.ui_components import StackedTabview  # noqa: E402


@pytest.fixture
def root():
    try:
        win = ctk.CTk()
    except tk.TclError as e:
        pytest.skip(f"no display: {e}")
    win.geometry("400x300")
    yield win
    win.destroy()


def _stacking(tabview):
    """Tab frames in stacking order, bottom to top."""
    tabs = {str(f): name for name, f in tabview._tab_dict.items()}
    order = tabview.tk.splitlist(tabview.tk.call("winfo", "children", tabview._w))
    return [tabs[w] for w in order if w in tabs]


def _select(tabview, name):
    tabview._segmented_button.set(name)
    tabview._segmented_button_callback(name)


def test_selected_tab_is_on_top_and_others_stay_placed(root):
    tabview = StackedTabview(root)
    tabview.pack(fill="both", expand=True)
    for name in ("A", "B", "C"):
        tabview.add(name)
    root.update()

    _select(tabview, "C")
    _select(tabview, "B")
    root.update_idletasks()

    assert tabview.get() == "B"
    assert _stacking(tabview)[-1] == "B"
    for name in ("A", "B", "C"):
        assert tabview.tab(name).winfo_manager() == "place"


def test_hidden_tab_keeps_its_size_when_the_window_resizes(root):
    tabview = StackedTabview(root)
    tabview.pack(fill="both", expand=True)
    tabview.add("A")
    tabview.add("B")
    root.update()
    size = (tabview.tab("A").winfo_width(), tabview.tab("A").winfo_height())

    _select(tabview, "B")
    root.geometry("600x450")
    root.update()

    assert (tabview.tab("A").winfo_width(), tabview.tab("A").winfo_height()) == size
    assert tabview.tab("B").winfo_width() > size[0]


def test_command_builds_the_new_tab_before_it_is_raised(root):
    seen = []
    tabview = StackedTabview(root)
    tabview.pack(fill="both", expand=True)
    tabview.add("A")
    tabview.add("B")
    tabview.configure(command=lambda: seen.append((tabview.get(), _stacking(tabview)[-1])))
    root.update()

    _select(tabview, "B")

    assert seen == [("B", "A")]
    assert _stacking(tabview)[-1] == "B"


def test_programmatic_set_shows_the_tab(root):
    tabview = StackedTabview(root)
    tabview.pack(fill="both", expand=True)
    for name in ("A", "B"):
        tabview.add(name)
    tabview.set("B")
    root.update()

    assert _stacking(tabview)[-1] == "B"
    assert tabview.tab("A").winfo_manager() == "place"
