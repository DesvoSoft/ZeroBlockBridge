import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from app.services.sanitizer import is_safe_command


class TestSanitizerAllowlisted:
    def test_op_command(self):
        safe, reason = is_safe_command("op PlayerName")
        assert safe
        assert reason == ""

    def test_say_command(self):
        safe, _ = is_safe_command("say Hello world")
        assert safe

    def test_gamemode_command(self):
        safe, _ = is_safe_command("gamemode creative PlayerName")
        assert safe

    def test_stop_command(self):
        safe, _ = is_safe_command("stop")
        assert safe

    def test_slash_prefix(self):
        safe, _ = is_safe_command("/op PlayerName")
        assert safe

    def test_list_command(self):
        safe, _ = is_safe_command("list")
        assert safe

    def test_kick_command(self):
        safe, _ = is_safe_command("kick PlayerName reason")
        assert safe

    def test_whitelist_command(self):
        safe, _ = is_safe_command("whitelist add PlayerName")
        assert safe

    def test_tp_command(self):
        safe, _ = is_safe_command("tp PlayerName 100 64 100")
        assert safe

    def test_give_command(self):
        safe, _ = is_safe_command("give PlayerName minecraft:diamond 64")
        assert safe

    def test_help_command(self):
        safe, _ = is_safe_command("help")
        assert safe

    def test_function_command(self):
        safe, _ = is_safe_command("function namespace:my_function")
        assert safe

    def test_scoreboard_command(self):
        safe, _ = is_safe_command("scoreboard objectives add kills deathCount")
        assert safe

    def test_reload_command(self):
        safe, _ = is_safe_command("reload")
        assert safe

    def test_save_all_command(self):
        safe, _ = is_safe_command("save-all")
        assert safe


class TestSanitizerBlocked:
    def test_semicolon_injection(self):
        safe, reason = is_safe_command("op PlayerName; rm -rf /")
        assert not safe

    def test_pipe_injection(self):
        safe, reason = is_safe_command("list | grep something")
        assert not safe

    def test_dollar_paren_injection(self):
        safe, _ = is_safe_command("say $(whoami)")
        assert not safe

    def test_backtick_injection(self):
        safe, _ = is_safe_command("say `whoami`")
        assert not safe

    def test_dollar_brace_injection(self):
        safe, _ = is_safe_command("say ${HOME}")
        assert not safe

    def test_ampersand_chain(self):
        safe, _ = is_safe_command("op PlayerName && rm -rf /")
        assert not safe

    def test_newline_injection(self):
        safe, _ = is_safe_command("op PlayerName\nstop")
        assert not safe

    def test_double_redirect(self):
        safe, _ = is_safe_command("list >> /etc/passwd")
        assert not safe

    def test_percent_in_path(self):
        safe, _ = is_safe_command("op %USERNAME%")
        assert not safe


class TestSanitizerUnknown:
    def test_unknown_simple_command(self):
        safe, _ = is_safe_command("myplugin:mycommand arg1 arg2")
        assert safe

    def test_unknown_with_dots_and_slashes(self):
        safe, _ = is_safe_command("namespace:sub command arg1 arg2")
        assert safe

    def test_unknown_with_numbers(self):
        safe, _ = is_safe_command("cmd123 some_arg")
        assert safe

    def test_unknown_with_at_symbol(self):
        safe, _ = is_safe_command("tell @a hello")
        assert safe

    def test_unknown_with_quotes(self):
        safe, _ = is_safe_command("mycommand 'arg with spaces'")
        assert safe

    def test_unknown_with_equals(self):
        safe, _ = is_safe_command("mycommand key=value")
        assert safe

    def test_empty_command(self):
        safe, reason = is_safe_command("")
        assert not safe
        assert "empty" in reason


class TestSanitizerEdgeCases:
    def test_whitespace_prefix(self):
        safe, _ = is_safe_command("  op PlayerName")
        assert safe

    def test_case_sensitivity(self):
        safe, _ = is_safe_command("OP PlayerName")
        assert safe

    def test_mixed_case(self):
        safe, _ = is_safe_command("GameMode creative PlayerName")
        assert safe
