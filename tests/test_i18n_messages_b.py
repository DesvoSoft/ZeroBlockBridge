"""User-facing messages of provisioning, ZBBManager, ServerRunner and the
orchestrators: Spanish output, plus the English mod auto-install summary."""

import threading
from contextlib import ExitStack
from unittest.mock import MagicMock, patch

import pytest

from app.core import i18n
from app.core.core import ServerExistsError, ZBBManager
from app.core.logic import ServerRunner, ServerStartError, create_server_directory, download_server
from app.core.orchestrators import BackupOrchestrator, ServerOrchestrator
from app.core.server_events import EventBus, ServerEvent
from app.services import content_import
from tests.conftest import FakeEmitter
from tests.test_content_import import _pack_zip
from tests.test_provisioning import _Env


@pytest.fixture
def spanish():
    assert i18n.set_language("es") == "es"


# ----------------------------------------------------------------------
# Provisioning
# ----------------------------------------------------------------------

def _provision(env, texts, **overrides):
    config = {"name": "srv", "version": "1.20.4", "type": "Vanilla", "location": str(env.servers_dir)}
    config.update(overrides)
    return env.provisioner.provision(config, lambda value, text=None: texts.append(text))


def test_progress_texts_in_spanish(tmp_path, spanish):
    texts = []
    with ExitStack() as stack:
        env = _Env(tmp_path, stack, java_cached=False)
        result = _provision(env, texts, icon_path="icon.png")
    assert result.ok
    for expected in ("Descargando el jar del servidor Vanilla 1.20.4...",
                     "Aplicando el icono del servidor...",
                     "Configurando el entorno del servidor...",
                     "Analizando los requisitos de Java del jar del servidor...",
                     "Instalando Temurin 17.0.9+9...",
                     "Configurando el túnel de Playit...",
                     "¡Servidor listo!"):
        assert expected in texts, expected


def test_existing_server_error_in_spanish(tmp_path, spanish):
    with ExitStack() as stack:
        env = _Env(tmp_path, stack)
        (env.servers_dir / "srv").mkdir()
        assert _provision(env, []).error == "El servidor 'srv' ya existe."


def test_download_failure_error_in_spanish(tmp_path, spanish):
    with ExitStack() as stack:
        env = _Env(tmp_path, stack, download_ok=False)
        assert _provision(env, []).error == (
            "No se pudo crear el servidor 'srv'. Revise el registro para ver los detalles.")


def test_junction_failure_in_spanish(tmp_path, spanish):
    with ExitStack() as stack:
        env = _Env(tmp_path, stack)
        env.junction.side_effect = OSError("mklink /J failed")
        result = _provision(env, [], location=str(tmp_path / "elsewhere"))
    assert result.error == "No se pudo vincular la ubicación personalizada: mklink /J failed"


def test_tunnel_warning_in_spanish(tmp_path, spanish):
    with ExitStack() as stack:
        env = _Env(tmp_path, stack)
        env.provisioner._create_tunnel = MagicMock(side_effect=RuntimeError("playit down"))
        result = _provision(env, [])
    assert result.ok
    assert result.warnings == [
        "No se pudo configurar el túnel de Playit (playit down). Inícielo desde el panel Tunnel."]


@pytest.mark.parametrize("failed, expected", [
    (1, "No se pudo descargar 1 mod del modpack"),
    (2, "No se pudieron descargar 2 mods del modpack"),
])
def test_modpack_failed_mods_warning_plural_in_spanish(tmp_path, spanish, failed, expected):
    texts = []
    with ExitStack() as stack:
        env = _Env(tmp_path, stack)
        stack.enter_context(patch("app.services.content_import.install_modpack",
                                  return_value=content_import.ModpackInstall("1 mods installed", failed=failed)))
        result = _provision(env, texts, type="Forge", version="1.20.1", modpack_path=_pack_zip(tmp_path))
    assert result.ok
    assert result.warnings[0].startswith(expected)
    assert any(t and t.startswith("Instalando el modpack ") for t in texts)


@pytest.mark.parametrize("failed, expected", [
    (1, "1 mod from the modpack couldn't be downloaded"),
    (2, "2 mods from the modpack couldn't be downloaded"),
])
def test_modpack_failed_mods_warning_plural_in_english(tmp_path, failed, expected):
    with ExitStack() as stack:
        env = _Env(tmp_path, stack)
        stack.enter_context(patch("app.services.content_import.install_modpack",
                                  return_value=content_import.ModpackInstall("1 mods installed", failed=failed)))
        result = _provision(env, [], type="Forge", version="1.20.1", modpack_path=_pack_zip(tmp_path))
    assert result.warnings[0].startswith(expected)


# ----------------------------------------------------------------------
# ZBBManager
# ----------------------------------------------------------------------

@pytest.fixture
def manager():
    with patch("app.core.playit_manager.PlayitManager"):
        m = ZBBManager(EventBus())
    notes = []
    m.events.subscribe(ServerEvent.NOTIFICATION, notes.append)
    m.notes = notes
    return m


def _java(major):
    j = MagicMock(major=major, is_jdk=True, path=f"/java{major}", source="PATH")
    return j


def _resolve(manager, javas, auto_install):
    with patch.object(manager, "_required_java_for_launch", return_value=17), \
         patch.object(manager, "_auto_install_java", return_value=None), \
         patch("app.core.core.JavaDetector") as det:
        det.return_value.detect_all.return_value = javas
        return manager._resolve_java_bin("dir", "1.20.4", None, auto_install)


@pytest.mark.parametrize("javas, auto_install, expected", [
    ([], False, "No se encontró ninguna instalación de Java y la instalación automática está desactivada "
                "en la configuración del servidor."),
    ([], True, "No se encontró Java y falló la instalación automática del JDK 17."),
    ([26], False, "Se detectó Java 26 (experimental). La instalación automática está desactivada. "
                  "Instale Java 17 manualmente."),
    ([26], True, "Se detectó Java 26 (experimental). Este servidor necesita Java 17 y la instalación "
                 "automática falló."),
    ([8], False, "Java 8 es demasiado antiguo. La instalación automática está desactivada. "
                 "Instale Java 17 manualmente."),
    ([8], True, "La versión de Java es demasiado antigua. Se requiere Java 17 y se detectó Java 8. "
                "La instalación automática falló."),
])
def test_java_launch_errors_in_spanish(manager, spanish, javas, auto_install, expected):
    assert _resolve(manager, [_java(v) for v in javas], auto_install) is None
    assert manager.notes[-1] == {"msg": expected, "type": "error"}


def test_newer_java_warning_in_spanish(manager, spanish):
    assert _resolve(manager, [_java(21)], False) == ("/java21", 17)
    assert manager.notes[-1] == {"msg": "Ejecutando con Java 21. Recomendado: Java 17.", "type": "warning"}


def test_server_exists_error_in_spanish(spanish, tmp_path):
    (tmp_path / "srv").mkdir()
    with patch("app.core.playit_manager.PlayitManager"):
        m = ZBBManager(EventBus())
    with patch("app.core.core.SERVERS_DIR", str(tmp_path)), \
         pytest.raises(ServerExistsError, match="^Ya existe un servidor llamado 'srv'.$"):
        m.load_server_manually(str(tmp_path / "elsewhere" / "srv"))


def _install_mods(manager, server_type="Fabric", installed=(), failed=(), unresolved=()):
    manager.executor = MagicMock()
    manager.executor.submit.side_effect = lambda fn: fn()
    result = {"installed": list(installed), "failed": list(failed), "unresolved": list(unresolved)}
    with patch("app.core.core.get_server_meta", return_value={"type": server_type, "version": "1.20.1"}), \
         patch("app.services.modrinth.ModrinthClient"), \
         patch("app.services.modrinth.install_missing_mods", return_value=result):
        manager._handle_mod_install_request({"missing_mod_ids": ["a"], "server_name": "srv"})
    return manager.notes[-1]


def test_mod_install_summary_english_sentences(manager):
    note = _install_mods(manager, installed=["a", "b"], failed=["c"], unresolved=["d", "e"])
    assert note == {"msg": "2 mods were installed. 1 mod failed to install. "
                           "2 mods were not found on Modrinth.", "type": "warning"}
    note = _install_mods(manager, installed=["a"])
    assert note == {"msg": "1 mod was installed.", "type": "success"}
    note = _install_mods(manager)
    assert note == {"msg": "No mods were installed.", "type": "error"}


def test_mod_install_summary_in_spanish(manager, spanish):
    note = _install_mods(manager, installed=["a"], failed=["b", "c"], unresolved=["d"])
    assert note["msg"] == ("Se instaló 1 mod. No se pudieron instalar 2 mods. "
                           "No se encontró 1 mod en Modrinth.")
    note = _install_mods(manager, installed=["a", "b"], failed=["c"], unresolved=["d", "e"])
    assert note["msg"] == ("Se instalaron 2 mods. No se pudo instalar 1 mod. "
                           "No se encontraron 2 mods en Modrinth.")
    assert _install_mods(manager)["msg"] == "No se instaló ningún mod."


def test_mod_install_needs_modded_server_in_spanish(manager, spanish):
    note = _install_mods(manager, server_type="Vanilla")
    assert note == {"msg": "No se pueden instalar mods automáticamente: el servidor no es Fabric, "
                           "Forge ni NeoForge.", "type": "error"}


# ----------------------------------------------------------------------
# logic: ServerRunner / server creation
# ----------------------------------------------------------------------

def _runner(tmp_path):
    (tmp_path / "srv").mkdir(exist_ok=True)
    return ServerRunner("srv", "1024M", MagicMock())


def test_server_runner_errors_in_spanish(tmp_path, spanish):
    runner = _runner(tmp_path)
    with patch("app.core.logic.SERVERS_DIR", str(tmp_path)):
        with pytest.raises(ServerStartError, match="^No se encontró el jar del servidor: server.jar$"):
            runner._resolve_launch_target(str(tmp_path / "srv"))
        with patch("app.core.logic._port_in_use", return_value=True), \
             patch("app.services.server_properties.load_server_properties", return_value={"server-port": "25570"}), \
             pytest.raises(ServerStartError, match="^El puerto 25570 ya está en uso por otro proceso. "
                                                   "Ciérrelo e inténtelo de nuevo.$"):
            runner._preflight_port()
        with patch("app.core.logic.subprocess.Popen", side_effect=FileNotFoundError("java")), \
             pytest.raises(ServerStartError, match="^No se pudo iniciar el servidor: java$"):
            runner._spawn(["java"], str(tmp_path / "srv"))


def test_download_and_directory_errors_in_spanish(tmp_path, spanish):
    with patch("app.core.logic.VersionManager") as vm, \
         patch("app.core.logic.create_server_directory"), \
         pytest.raises(ValueError, match="^No se encontró la URL para Paper 1.20.1$"):
        vm.return_value.get_download_url.return_value = None
        download_server("srv", "Paper", "1.20.1")
    with patch("app.core.logic.SERVERS_DIR", str(tmp_path)), \
         patch("app.core.logic.os.makedirs", side_effect=PermissionError("denied")), \
         pytest.raises(PermissionError, match="permiso denegado"):
        create_server_directory("srv")


# ----------------------------------------------------------------------
# Orchestrators
# ----------------------------------------------------------------------

def _orch_manager(**overrides):
    m = MagicMock()
    m.events = FakeEmitter()
    m.current_server = "test_srv"
    m._start_lock = threading.Lock()
    m._backup_lock = threading.Lock()
    m._backup_in_progress = False
    for k, v in overrides.items():
        setattr(m, k, v)
    return m


def _notes(m):
    return [e[1]["msg"] for e in m.events.events if e[0] == ServerEvent.NOTIFICATION]


def test_low_disk_space_in_spanish(spanish):
    m = _orch_manager()
    with patch("app.core.orchestrators.check_disk_space", return_value=False):
        assert ServerOrchestrator(m).start_server() is False
    assert _notes(m) == ["No hay suficiente espacio en disco para iniciar el servidor (se requiere más de 1 GB)."]


def test_auto_backup_crash_in_spanish(spanish):
    m = _orch_manager(_backup_in_progress=True)
    with patch("app.core.orchestrators.BackupManager", side_effect=RuntimeError("boom")), \
         patch("app.core.orchestrators.BackupScheduler"):
        BackupOrchestrator(m)._run_auto_backup()
    assert _notes(m) == ["La copia de seguridad automática falló de forma inesperada: boom"]


def test_pre_update_snapshot_errors_in_spanish(spanish):
    m = _orch_manager()
    m.is_running.return_value = True
    assert BackupOrchestrator(m).create_pre_update_snapshot("test_srv") == (
        None, "Detenga el servidor antes de actualizar los mods (el servidor en ejecución bloquea los archivos).")
    m = _orch_manager(_backup_in_progress=True)
    m.is_running.return_value = False
    assert BackupOrchestrator(m).create_pre_update_snapshot("test_srv") == (
        None, "Ya hay otra copia de seguridad en curso. Inténtelo de nuevo en unos momentos.")
