"""Display labels vs internal keys: switching the language changes what is
shown, never what is stored, compared or sent to another component."""

import pytest

from app.core import i18n
from app.core.i18n import N_
from app.core.playit_manager import TunnelStatus, tunnel_status_label
from app.services.java_detector import JavaInstallation, dropdown_labels
from app.services.sanitizer import BlockedReason, describe_blocked, is_safe_command
from app.services.watchdog import crash_reason_label

CHOICES = (("Dark", N_("Dark")), ("Light", N_("Light")), ("System", N_("System")))


@pytest.fixture
def spanish():
    assert i18n.set_language("es") == "es"


# ----------------------------------------------------------------------
# Choice helpers
# ----------------------------------------------------------------------
def test_choice_round_trip_in_english():
    assert i18n.choice_labels(CHOICES) == ["Dark", "Light", "System"]
    assert i18n.choice_label(CHOICES, "Light") == "Light"
    assert i18n.choice_key(CHOICES, "Light") == "Light"


def test_translated_label_maps_back_to_the_same_key(spanish):
    assert i18n.choice_labels(CHOICES) == ["Oscuro", "Claro", "Sistema"]
    assert i18n.choice_label(CHOICES, "Light") == "Claro"
    assert i18n.choice_key(CHOICES, "Claro") == "Light"


def test_english_label_is_not_a_key_in_spanish(spanish):
    # A stale English label (e.g. from before a language switch) must not
    # silently pass for a key.
    assert i18n.choice_key(CHOICES, "Light") is None
    assert i18n.choice_key(CHOICES, "Light", "Dark") == "Dark"


def test_unknown_key_shows_the_first_label():
    assert i18n.choice_label(CHOICES, "Neon") == "Dark"


@pytest.mark.parametrize("module, attr", [
    ("app.ui.app_settings", "AppSettingsDialog._THEMES"),
    ("app.ui.app_settings", "AppSettingsDialog._TABS"),
    ("app.ui.players_panel", "_FILTERS"),
    ("app.ui.modrinth_browser", "ModrinthBrowser._SORT_OPTIONS"),
    ("app.ui.server_properties_editor", "_SCHEDULE_MODES"),
])
def test_ui_choices_round_trip_in_spanish(spanish, module, attr):
    import importlib
    owner = importlib.import_module(module)
    for part in attr.split("."):
        owner = getattr(owner, part)
    keys = [key for key, _label in owner]
    labels = i18n.choice_labels(owner)
    assert len(set(labels)) == len(labels)
    assert [i18n.choice_key(owner, label) for label in labels] == keys


def test_theme_keys_are_what_ctk_accepts():
    from app.ui.app_settings import AppSettingsDialog
    assert [key for key, _label in AppSettingsDialog._THEMES] == ["Dark", "Light", "System"]


def test_players_filter_keys_select_the_right_players(spanish):
    from app.ui.players_panel import _FILTER_TESTS, _FILTERS
    player = {"online": True, "op_level": None, "whitelisted": False, "banned": False}
    shown = {key: _FILTER_TESTS[key](player) for key, _label in _FILTERS}
    assert shown == {"all": True, "online": True, "ops": False, "whitelisted": False, "banned": False}


def test_console_tab_keys_stay_english(spanish):
    from app.ui.main import MCTunnelApp
    assert set(MCTunnelApp._TAB_LABELS) == set(MCTunnelApp._TAB_ICONS)
    assert i18n._(MCTunnelApp._TAB_LABELS["Tunnel Log"]) == "Registro del túnel"


def test_impact_keys_have_labels():
    from app.ui.server_properties_editor import SETTINGS_METADATA, _IMPACT_LABELS
    impacts = {meta["impact"] for meta in SETTINGS_METADATA.values() if "impact" in meta}
    assert impacts <= set(_IMPACT_LABELS)


# ----------------------------------------------------------------------
# Tunnel status
# ----------------------------------------------------------------------
def test_tunnel_status_keys_are_stable(spanish):
    # core.py and main.py compare these; the values never follow the language.
    assert TunnelStatus.ONLINE == "Online"
    assert TunnelStatus.STARTING == "Starting..."
    assert str(TunnelStatus.OFFLINE) == "Offline"


def test_tunnel_status_label_is_translated(spanish):
    assert tunnel_status_label(TunnelStatus.ONLINE) == "En línea"
    assert tunnel_status_label("Starting...") == "Iniciando..."
    assert tunnel_status_label("garbage") == "Desconectado"


def test_tunnel_status_label_in_english():
    assert tunnel_status_label(TunnelStatus.ERROR) == "Error"


# ----------------------------------------------------------------------
# Sanitizer
# ----------------------------------------------------------------------
def test_blocked_reason_values_stay_english(spanish):
    assert is_safe_command("op x; rm -rf /")[1].value == "contains shell metacharacters"


def test_describe_blocked_in_spanish(spanish):
    msg = describe_blocked("op x; rm -rf /", BlockedReason.SHELL_METACHARACTERS)
    assert msg == "Bloqueado `op x; rm -rf /`: contiene metacaracteres de shell"
    assert describe_blocked("", BlockedReason.EMPTY) == "Bloqueado: comando vacío"


# ----------------------------------------------------------------------
# Crash reasons
# ----------------------------------------------------------------------
@pytest.mark.parametrize("code, english", [
    ("out_of_memory", "out of memory"),
    ("zombie", "it stopped responding"),
    ("signal_9", "ended by signal 9"),
    ("exit_3", "exited with code 3"),
    ("exit_-1", "exited with code -1"),
    ("unknown", "unknown cause"),
    ("something_new", "unknown cause"),
    (None, "unknown cause"),
])
def test_crash_reason_label(code, english):
    assert crash_reason_label(code) == english


def test_crash_reason_label_in_spanish(spanish):
    assert crash_reason_label("boot_crash") == "se detuvo durante el arranque"
    assert crash_reason_label("exit_2") == "salió con el código 2"


# ----------------------------------------------------------------------
# Java dropdown
# ----------------------------------------------------------------------
def _java(path, major=17, source="PATH", jdk=True):
    return JavaInstallation(path=path, version_string=str(major), major=major, source=source, is_jdk=jdk)


def test_java_dropdown_labels_are_unique():
    javas = [_java("C:/a/java.exe"), _java("C:/b/java.exe"), _java("C:/c/java.exe", major=21)]
    labels = dropdown_labels(javas)
    assert len(set(labels)) == 3
    assert labels[0].endswith("C:/a/java.exe") and labels[1].endswith("C:/b/java.exe")
    assert labels[2] == "Java 21 (JDK) — PATH"


def test_java_dropdown_labels_map_back_in_spanish(spanish):
    javas = [_java("C:/a/java.exe"), _java("C:/b/java.exe")]
    by_label = dict(zip(dropdown_labels(javas), (j.path for j in javas)))
    assert list(by_label.values()) == ["C:/a/java.exe", "C:/b/java.exe"]
