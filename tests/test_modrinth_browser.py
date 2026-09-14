"""Unit tests for pure-logic helpers in app/ui/modrinth_browser.py (F8)."""

from pathlib import Path

from app.ui.modrinth_browser import _filter_updates_for_selection, _snapshot_then_apply


class TestSnapshotThenApply:
    def test_snapshot_failure_applies_nothing(self):
        applied = []
        error, updated, failed = _snapshot_then_apply(
            lambda _name: (None, "disk full"), "srv", [{"filename": "a.jar"}], applied.append)
        assert error == "disk full"
        assert (updated, failed) == (0, 0)
        assert applied == []

    def test_missing_snapshot_service_applies_nothing(self):
        applied = []
        error, _, _ = _snapshot_then_apply(None, "srv", [{"filename": "a.jar"}], applied.append)
        assert error
        assert applied == []

    def test_snapshot_before_any_update(self):
        calls = []

        def snapshot(name):
            calls.append(("snapshot", name))
            return Path("snap.zip"), None

        def apply_one(u):
            calls.append(("apply", u["filename"]))
            return True

        error, updated, failed = _snapshot_then_apply(
            snapshot, "srv", [{"filename": "a.jar"}, {"filename": "b.jar"}], apply_one)
        assert error is None
        assert (updated, failed) == (2, 0)
        assert calls == [("snapshot", "srv"), ("apply", "a.jar"), ("apply", "b.jar")]

    def test_counts_failures_and_exceptions(self):
        def apply_one(u):
            if u["filename"] == "boom.jar":
                raise RuntimeError("network")
            return u["filename"] == "ok.jar"

        error, updated, failed = _snapshot_then_apply(
            lambda _n: (Path("snap.zip"), None), "srv",
            [{"filename": "ok.jar"}, {"filename": "bad.jar"}, {"filename": "boom.jar"}], apply_one)
        assert error is None
        assert (updated, failed) == (1, 2)


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
