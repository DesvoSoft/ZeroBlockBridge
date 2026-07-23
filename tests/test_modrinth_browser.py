"""Unit tests for pure-logic helpers in app/ui/modrinth_browser.py (F8)."""

from app.ui.modrinth_browser import _filter_updates_for_selection


class TestFilterUpdatesForSelection:
    def test_matches_selected_filenames(self):
        updates = [
            {"filename": "sodium-0.5.jar", "update_url": "https://x/sodium-0.6.jar"},
            {"filename": "lithium-0.1.jar", "update_url": "https://x/lithium-0.2.jar"},
        ]
        result = _filter_updates_for_selection(updates, {"sodium-0.5.jar"})
        assert len(result) == 1
        assert result[0]["filename"] == "sodium-0.5.jar"

    def test_empty_selection_returns_empty(self):
        updates = [{"filename": "sodium-0.5.jar"}]
        assert _filter_updates_for_selection(updates, set()) == []

    def test_no_match_returns_empty(self):
        updates = [{"filename": "sodium-0.5.jar"}]
        assert _filter_updates_for_selection(updates, {"other.jar"}) == []

    def test_empty_updates_returns_empty(self):
        assert _filter_updates_for_selection([], {"sodium-0.5.jar"}) == []
