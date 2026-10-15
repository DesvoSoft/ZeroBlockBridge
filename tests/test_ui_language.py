"""Language handling in UI code, driven without Tk (STANDARDS §5)."""
import datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.core import i18n
from app.ui.first_run_dialog import _SetupDialog
from app.ui.players_panel import PlayersPanel


def _setup_dialog(busy: bool):
    dialog = MagicMock()
    dialog._busy = busy
    dialog._choice.get.return_value = "install"
    dialog._data_dir = Path("data")
    return dialog


def test_language_pick_rebuilds_the_setup_page():
    dialog = _setup_dialog(busy=False)

    _SetupDialog._on_language(dialog, "Español")

    assert i18n.get_language() == "es"
    dialog._build_choice_page.assert_called_once()
    dialog.set_title.assert_called_once_with("Instalación")


def test_language_pick_ignored_while_installing():
    """A rebuilt page would re-enable Install while the copy runs, and a
    second click started a second install over the same files."""
    dialog = _setup_dialog(busy=True)

    _SetupDialog._on_language(dialog, "Español")

    assert i18n.get_language() == "en"
    dialog._build_choice_page.assert_not_called()
    dialog._language_menu.set.assert_called_once_with("English")


def test_option_pick_ignored_while_installing():
    dialog = _setup_dialog(busy=True)

    _SetupDialog._on_pick(dialog, "portable")

    dialog._refresh_button.assert_not_called()
    dialog._error.configure.assert_not_called()


def test_confirm_ignored_while_installing():
    dialog = _setup_dialog(busy=True)

    _SetupDialog._confirm(dialog)

    dialog.run_in_background.assert_not_called()
    dialog._btn_continue.configure.assert_not_called()


def _player(**overrides):
    player = {"banned": False, "ban_reason": "", "online": False, "last_seen": None, "playtime_seconds": 0}
    player.update(overrides)
    return player


@pytest.mark.parametrize("player, en, es", [
    (_player(banned=True, ban_reason="griefing"), "Banned: griefing", "Baneado: griefing"),
    (_player(online=True), "Online now", "En línea ahora"),
    (_player(playtime_seconds=4800), "1h 20m played", "1 h 20 min jugado"),
    (_player(), "Hasn't joined since ZBB started tracking", "No ha entrado desde que ZBB lleva el registro"),
])
def test_player_detail_is_one_language(player, en, es):
    """No 'Last seen hace 5 min': the sentence around a formatted value is
    translated with it."""
    assert PlayersPanel._detail(player)[0] == en
    i18n.set_language("es")
    assert PlayersPanel._detail(player)[0] == es


def test_player_last_seen_is_one_language():
    five_min_ago = (datetime.datetime.now() - datetime.timedelta(minutes=5, seconds=10)).isoformat()
    i18n.set_language("es")
    assert PlayersPanel._detail(_player(last_seen=five_min_ago))[0] == "Visto por última vez hace 5 min"
