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

    def test_plain_line_untagged(self):
        assert ConsoleWidget._line_tag("[System] Loaded 2 servers.") is None
