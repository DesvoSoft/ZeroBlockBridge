"""Spanish output of the Playit toasts, player-management results and backup messages."""

import zipfile
from unittest.mock import MagicMock, patch

import pytest

from app.core import i18n
from app.core import players as pl
from app.core.playit_manager import PlayitManager
from app.services.backup_manager import BackupManager
from app.services.player_identity import PlayerIdentity


@pytest.fixture
def spanish():
    assert i18n.set_language("es") == "es"


# ------------------------------------------------------------------ Playit toasts
@pytest.fixture
def playit():
    with patch("app.core.playit_manager.PlayitApiClient") as mock_api_cls:
        api = MagicMock()
        api.load_secret_key.return_value = True
        api.secret_rejected.return_value = False
        api.consecutive_auth_failures = 0
        api.list_account_tunnels.return_value = []
        mock_api_cls.return_value = api
        notify = MagicMock()
        m = PlayitManager(console_callback=MagicMock(), status_callback=MagicMock(),
                          notification_callback=notify)
        yield m, api, notify


def _toast(notify):
    return notify.call_args[0][0]


def test_pending_tunnel_toast(spanish, playit):
    m, api, notify = playit
    api.list_tunnels.return_value = []
    api.create_tunnel.return_value = {"id": "pending"}
    api.get_tunnel_address.return_value = None
    m.get_or_create_tunnel(25565)
    assert _toast(notify) == "Túnel pendiente: no hay puertos disponibles. Revise el panel de playit.gg."


def test_read_only_toast(spanish, playit):
    from app.services.playit_api import PlayitApiException
    m, api, notify = playit
    api.list_tunnels.side_effect = PlayitApiException("NotAllowedWithReadOnly: Account is in Guest mode")
    m.get_or_create_tunnel(25565)
    assert _toast(notify) == ("La cuenta de Playit es de solo lectura. "
                              "Use un código de configuración para vincularla.")


def test_invalid_setup_code_toast(spanish, playit):
    m, _api, notify = playit
    assert m.link_manually("abc") is False
    assert _toast(notify) == "Código de configuración no válido."


def test_link_failed_toast_embeds_error(spanish, playit):
    m, api, notify = playit
    api.link_account.side_effect = RuntimeError("boom")
    with patch.object(m, "ensure_binary"):
        assert m.link_manually("ABCDEFGH12") is False
    assert _toast(notify) == "No se pudo vincular: boom"


def test_secret_invalid_toast(spanish, playit):
    m, _api, notify = playit
    m._handle_auth_failure("Agent secret invalid")
    assert _toast(notify) == ("El secreto de Playit no es válido. "
                              "Use 'Restablecer túnel' para volver a vincular.")


def test_tunnel_online_toast(spanish, playit):
    m, _api, notify = playit
    m._parse_line("tunnel running at abc.ply.gg:12345")
    assert _toast(notify) == "Túnel en línea: abc.ply.gg:12345"


def test_reset_toasts(spanish, playit, tmp_path):
    m, api, notify = playit
    api.list_tunnels.return_value = []
    api.delete_agent.return_value = True
    with patch.object(m, "stop"):
        m.reset(mode="tunnel")
        assert _toast(notify) == ("Túneles eliminados. Haga clic en Iniciar túnel "
                                  "para crear un túnel nuevo.")
        with patch.object(m, "toml_path", str(tmp_path / "playit.toml")):
            m.reset(mode="full")
        assert _toast(notify) == "Cuenta de Playit desvinculada y restablecida."


def test_console_lines_stay_english(spanish, playit):
    m, _api, _notify = playit
    m.link_manually("abc")
    assert m.console_callback.call_args[0][0].startswith("[Playit] Invalid setup code.")


# ------------------------------------------------------------------ player results
@pytest.fixture
def orch():
    props = {"online-mode": "true", "op-permission-level": "2", "white-list": "false"}
    manager = MagicMock()
    manager.current_server = "srv"
    manager.is_running.return_value = False
    manager.server_runner = None
    with patch.object(pl, "add_entry"), patch.object(pl, "remove_entry"), \
         patch.object(pl, "load_server_properties", return_value=props), \
         patch.object(pl, "save_server_properties"), \
         patch.object(pl, "resolve_player", return_value=PlayerIdentity("Steve", "uuid-1", "mojang")):
        yield pl.PlayerOrchestrator(manager), manager


def _live(manager):
    manager.is_running.return_value = True
    manager.server_runner = MagicMock(connected_players=set())


def test_whitelist_toggle_is_two_sentences(spanish, orch):
    o, _m = orch
    assert o.set_whitelist_enabled("srv", True).message == "Lista blanca activada."
    assert o.set_whitelist_enabled("srv", False).message == "Lista blanca desactivada."


def test_whitelist_toggle_english(orch):
    o, _m = orch
    assert o.set_whitelist_enabled("srv", True).message == "Whitelist enabled."
    assert o.set_whitelist_enabled("srv", False).message == "Whitelist disabled."


def test_stopped_server_results(spanish, orch):
    o, _m = orch
    assert o.whitelist_add("srv", "Steve").message == "Se agregó a Steve a la lista blanca."
    assert o.whitelist_remove("srv", "Steve").message == "Se quitó a Steve de la lista blanca."
    assert o.op("srv", "Steve", 3).message == "Steve ahora es operador (nivel 3)."
    assert o.op("srv", "Steve", 9).message == "El nivel de operador debe ser de 1 a 4, no 9."
    assert o.deop("srv", "Steve").message == "Steve ya no es operador."
    assert o.ban("srv", "Steve").message == "Se baneó a Steve."
    assert o.pardon("srv", "Steve").message == "Se desbaneó a Steve."
    assert o.kick("srv", "Steve").message == "El servidor no está en ejecución."
    assert o.whitelist_add("srv", "a!").message == (
        "'a!' no es un nombre de jugador válido (3-16 letras, números o _).")
    assert o.ban("srv", "Steve", "bad<reason>").message == (
        "Use letras, números y puntuación básica en el motivo (máx. 100).")


def test_live_server_results(spanish, orch):
    o, m = orch
    _live(m)
    assert o.whitelist_add("srv", "Steve").message == "Se agregó a Steve a la lista blanca."
    assert o.op("srv", "Steve", 2).message == "Steve ahora es operador."
    assert o.op("srv", "Steve", 4).message == (
        "Steve ahora es operador (nivel 2, el op-permission-level del servidor; "
        "detenga el servidor para asignar el nivel 4).")
    assert o.kick("srv", "Steve").message == "Se expulsó a Steve."
    assert o.kick("srv", "Steve", "bad<reason>").message == (
        "Use letras, números y puntuación básica en el motivo (máx. 100).")
    # The command sent to Minecraft stays English.
    assert m.send_command.call_args_list[0].args[0] == "whitelist add Steve"


def test_live_op_english(orch):
    o, m = orch
    _live(m)
    assert o.op("srv", "Steve", 2).message == "Made Steve an operator."
    assert o.op("srv", "Steve", 4).message == (
        "Made Steve an operator (level 2, the server's op-permission-level; stop the server to set level 4).")


# ------------------------------------------------------------------ backups
def test_backup_disk_space_error(spanish, tmp_path):
    bm = BackupManager("test_server")
    with patch.object(bm, "backup_dir", tmp_path), \
         patch("app.core.constants.check_disk_space", return_value=False):
        assert bm.create_backup() == (None, "No hay suficiente espacio en disco para crear la copia de "
                                            "seguridad (se requiere más de 1 GB).")


def test_delete_backup_refusal(spanish, tmp_path):
    bm = BackupManager("test_server")
    outside = tmp_path / "world.zip"
    outside.touch()
    with patch.object(bm, "backup_dir", tmp_path / "backups"):
        assert bm.delete_backup(str(outside)) == (False, "No es una copia de seguridad de este servidor.")


def _backup_with_locked(tmp_path, locked):
    server, backups = tmp_path / "srv", tmp_path / "backups"
    server.mkdir()
    backups.mkdir()
    for i in range(locked):
        (server / f"locked{i}.txt").write_text("x")
    (server / "ok.txt").write_text("x")
    real_write = zipfile.ZipFile.write

    def write(self, filename, arcname=None, *args, **kwargs):
        if str(arcname).startswith("locked"):
            raise PermissionError(13, "locked")
        return real_write(self, filename, arcname, *args, **kwargs)

    bm = BackupManager("test_server")
    with patch.object(bm, "backup_dir", backups), patch.object(bm, "server_path", server), \
         patch.object(zipfile.ZipFile, "write", write):
        return bm.create_backup()[1]


@pytest.mark.parametrize("count, expected", [
    (1, "Copia de seguridad creada con advertencias. Se omitió 1 archivo bloqueado."),
    (2, "Copia de seguridad creada con advertencias. Se omitieron 2 archivos bloqueados."),
])
def test_skipped_locked_files_plural_es(spanish, tmp_path, count, expected):
    assert _backup_with_locked(tmp_path, count) == expected


@pytest.mark.parametrize("count, expected", [
    (1, "Backup created with warnings. Skipped 1 locked file."),
    (2, "Backup created with warnings. Skipped 2 locked files."),
])
def test_skipped_locked_files_plural_en(tmp_path, count, expected):
    assert _backup_with_locked(tmp_path, count) == expected
