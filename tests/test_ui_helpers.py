"""Unit tests for pure display helpers in the server editor and wizard."""

from app.ui.server_properties_editor import TAB_LAYOUTS, property_label
from app.ui.server_wizard import java_summary, summary_value


class TestPropertyLabel:
    def test_acronyms_keep_their_casing(self):
        assert property_label("spawn-npcs") == "Spawn NPCs"
        assert property_label("server-ip") == "Server IP"
        assert property_label("log-ips") == "Log IPs"
        assert property_label("pvp") == "PvP"

    def test_dotted_keys(self):
        assert property_label("rcon.password") == "RCON Password"
        assert property_label("enable-rcon") == "Enable RCON"

    def test_readable_words(self):
        assert property_label("white-list") == "Whitelist"
        assert property_label("broadcast-console-to-ops") == "Broadcast Console to Operators"
        assert property_label("op-permission-level") == "Operator Permission Level"

    def test_every_layout_key_gets_a_capitalized_label(self):
        for sections in TAB_LAYOUTS.values():
            for keys in sections.values():
                for key in keys:
                    label = property_label(key)
                    assert label and label[0].isupper(), key


class TestWizardSummary:
    def test_bools_render_as_yes_no(self):
        assert summary_value(True) == "Yes"
        assert summary_value(False) == "No"

    def test_other_values_render_as_text(self):
        assert summary_value(20) == "20"
        assert summary_value("survival") == "survival"

    def test_auto_java_names_the_version_it_will_fetch(self):
        assert java_summary("auto", "26.2") == "Auto (Java 25)"
        assert java_summary("auto", "1.20.1") == "Auto (Java 17)"

    def test_explicit_java_path_is_shown_as_is(self):
        assert java_summary("C:/jdk-21/bin/java.exe", "1.21") == "C:/jdk-21/bin/java.exe"
