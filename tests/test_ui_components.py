"""Unit tests for pure-logic helpers in app/ui/ui_components.py."""

from app.ui.ui_components import ConsoleWidget


class TestConsoleLineTag:
    def test_security_line_tagged(self):
        line = "[Security] Blocked `op x; rm -rf /`: contains shell metacharacters"
        assert ConsoleWidget._line_tag(line) == "line_security"

    def test_security_beats_error_keyword(self):
        assert ConsoleWidget._line_tag("[Security] ERROR-like text") == "line_security"

    def test_player_chat_cannot_spoof_security_tag(self):
        line = "[12:00:00] [Server thread/INFO]: <Steve> [Security] Blocked everything"
        assert ConsoleWidget._line_tag(line) != "line_security"

    def test_plain_line_gets_plain_tag(self):
        # "line_plain" (not None) so the category filter can also hide/show
        # untagged lines via Tk's elide option.
        assert ConsoleWidget._line_tag("[System] Loaded 2 servers.") == "line_plain"


class TestConsoleFilterElideMap:
    """_elide_map is the pure logic behind set_category_filter, kept Tk-free
    (same reasoning as _line_tag being a @staticmethod) so it's testable
    without a live display — this codebase has no GUI tests anywhere since
    CI's ubuntu-latest runner has none."""

    def test_errors_only_shows_error_tag(self):
        m = ConsoleWidget._elide_map("errors")
        assert m["line_error"] is False
        assert m["line_plain"] is True
        assert m["line_warn"] is True
        assert m["line_join"] is True

    def test_players_shows_join_and_leave(self):
        m = ConsoleWidget._elide_map("players")
        assert m["line_join"] is False
        assert m["line_leave"] is False
        assert m["line_error"] is True

    def test_all_hides_nothing(self):
        for category in (None, "all"):
            m = ConsoleWidget._elide_map(category)
            assert all(hidden is False for hidden in m.values())

    def test_unknown_category_falls_back_to_all(self):
        m = ConsoleWidget._elide_map("nonsense")
        assert all(hidden is False for hidden in m.values())
