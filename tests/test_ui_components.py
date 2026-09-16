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


class TestTunnelLogCategories:
    def test_agent_output_vs_zbb_messages(self):
        from app.ui.ui_components import TunnelLogWidget as T
        assert T._line_tag("[Playit] 2026-09-16T20:00:00.123Z  INFO playitd::agent: tunnel ready") == "line_agent"
        assert T._line_tag("[Playit] DEBUG connecting to control") == "line_agent"
        assert T._line_tag("[Playit] Tunnel created: friends.joinmc.link") == "line_tunnel"
        assert T._line_tag("[System] Clearing tunnels...") == "line_tunnel"

    def test_errors_and_warnings_win(self):
        from app.ui.ui_components import TunnelLogWidget as T
        assert T._line_tag("[Playit] Download failed: timeout") == "line_error"
        assert T._line_tag("[Playit] 2026-09-16T20:00:00Z ERROR playitd: lost connection") == "line_error"
        assert T._line_tag("[Playit] 2026-09-16T20:00:00Z  WARN playitd: slow ping") == "line_warn"

    def test_filters_have_no_player_or_security_categories(self):
        from app.ui.ui_components import TunnelLogWidget as T
        keys = {key for _, key in T.FILTERS}
        assert keys == {None, "errors", "warnings", "tunnel", "agent"}
        m = T._elide_map("agent")
        assert m["line_agent"] is False and m["line_tunnel"] is True
