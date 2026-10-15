"""Spanish output of the user-facing messages in migration, java_installer,
modrinth, playit_api and player_identity."""

import io
import json
import os
import tarfile
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from app.core import i18n
from app.services import java_installer as ji
from app.services import migration
from app.services import player_identity as pi
from app.services.modrinth import ModrinthClient, ModrinthException
from app.services.playit_api import PlayitApiClient, PlayitApiException


@pytest.fixture
def spanish():
    assert i18n.set_language("es") == "es"


# ---------------------------------------------------------------------------
# migration
# ---------------------------------------------------------------------------

def _server(servers, name="srv"):
    server_dir = servers / name
    (server_dir / "world").mkdir(parents=True)
    (server_dir / "world" / "level.dat").write_text("data", encoding="utf-8")
    (server_dir / "metadata.json").write_text(json.dumps({"type": "Paper"}), encoding="utf-8")
    return server_dir


def test_migration_export_missing_server(spanish, tmp_path, monkeypatch):
    monkeypatch.setattr(migration, "SERVERS_DIR", str(tmp_path))
    with pytest.raises(migration.MigrationError) as exc:
        migration.export_server("nope", str(tmp_path / "out.zbbpack"))
    assert str(exc.value) == "El servidor 'nope' no existe"


def test_migration_progress_texts(spanish, tmp_path, monkeypatch):
    servers = tmp_path / "servers"
    _server(servers)
    monkeypatch.setattr(migration, "SERVERS_DIR", str(servers))
    pack = str(tmp_path / "out.zbbpack")
    exported = []
    migration.export_server("srv", pack, progress_callback=exported.append)
    assert exported == [f"Archivando {os.path.join('world', 'level.dat')}"]

    imported = []
    migration.import_server(pack, "copy", progress_callback=imported.append)
    assert "Extrayendo world/level.dat" in imported


def test_migration_import_errors(spanish, tmp_path, monkeypatch):
    servers = tmp_path / "servers"
    _server(servers)
    monkeypatch.setattr(migration, "SERVERS_DIR", str(servers))

    with pytest.raises(migration.MigrationError) as exc:
        migration.import_server("x.zbbpack", "srv")
    assert str(exc.value) == "El servidor 'srv' ya existe"

    not_zip = tmp_path / "bad.zbbpack"
    not_zip.write_text("nope", encoding="utf-8")
    with pytest.raises(migration.MigrationError) as exc:
        migration.import_server(str(not_zip), "new")
    assert str(exc.value) == "No es un archivo .zbbpack válido"

    no_meta = tmp_path / "nometa.zbbpack"
    with zipfile.ZipFile(no_meta, "w") as zf:
        zf.writestr("server.properties", "x")
    with pytest.raises(migration.MigrationError) as exc:
        migration.import_server(str(no_meta), "new")
    assert str(exc.value) == "Al archivo le falta metadata.json"

    evil = tmp_path / "evil.zbbpack"
    with zipfile.ZipFile(evil, "w") as zf:
        zf.writestr("metadata.json", "{}")
        zf.writestr("../evil.txt", "x")
    with pytest.raises(migration.MigrationError) as exc:
        migration.import_server(str(evil), "new")
    assert str(exc.value) == "Ruta no segura en el archivo comprimido: ../evil.txt"


def test_migration_disk_space(spanish, tmp_path, monkeypatch):
    servers = tmp_path / "servers"
    _server(servers)
    monkeypatch.setattr(migration, "SERVERS_DIR", str(servers))
    pack = str(tmp_path / "out.zbbpack")
    migration.export_server("srv", pack)
    monkeypatch.setattr(migration, "check_disk_space", lambda **_kw: False)
    with pytest.raises(migration.MigrationError) as exc:
        migration.import_server(pack, "copy")
    assert str(exc.value).startswith("No hay suficiente espacio en disco para importar (se necesitan ~")
    assert str(exc.value).endswith(" GB libres)")


# ---------------------------------------------------------------------------
# java_installer
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("error, expected", [
    (requests.ConnectionError(), "Sin conexión a internet: no se puede descargar el JDK"),
    (requests.Timeout(), "Se agotó el tiempo de espera de la API de Adoptium"),
    (requests.RequestException("boom"), "Falló la solicitud a la API de Adoptium: boom"),
])
def test_jdk_adoptium_errors(spanish, error, expected):
    with patch("app.services.java_installer.requests.get", side_effect=error):
        with pytest.raises(ji.JdkDownloadError) as exc:
            ji._query_assets(17, "jre")
    assert str(exc.value) == expected


def test_jdk_no_asset(spanish):
    with patch("app.services.java_installer._query_assets", return_value=None), \
         patch("app.services.java_installer._platform_os", return_value="windows"), \
         patch("app.services.java_installer._platform_arch", return_value="x64"):
        with pytest.raises(ji.JdkDownloadError) as exc:
            ji._fetch_asset_info(99)
    assert str(exc.value) == "No se encontró el JDK 99 para windows/x64"


def test_jdk_no_binary_after_extract(spanish, tmp_path):
    manager = ji.JdkManager()
    with patch.object(manager, "get_java_path", return_value=None), \
         patch.object(manager, "_download_and_install", return_value=str(tmp_path / "jdk")), \
         patch("app.services.java_installer._find_java_binary", return_value=None):
        with pytest.raises(ji.JdkError) as exc:
            manager.ensure_java(17)
    assert str(exc.value) == (
        f"Se extrajo el JDK 17, pero no se encontró el ejecutable de java en {tmp_path / 'jdk'}")


def test_jdk_retries_exhausted(spanish, tmp_path):
    manager = ji.JdkManager()
    info = {"url": "https://x/jdk.zip", "checksum": "", "version": "17", "image_type": "jre"}
    with patch("app.services.java_installer._fetch_asset_info", return_value=info), \
         patch("app.services.java_installer._JDK_CACHE_DIR", tmp_path), \
         patch.object(manager, "_download_file", side_effect=OSError("disk")), \
         patch("time.sleep"):
        with pytest.raises(ji.JdkDownloadError) as exc:
            manager._download_and_install(17)
    assert str(exc.value) == f"La descarga del JDK falló tras {ji.MAX_RETRIES} intentos: disk"


def test_jdk_checksum_mismatch(spanish, tmp_path):
    archive = tmp_path / "jdk.zip"
    archive.write_bytes(b"x")
    with pytest.raises(ji.JdkIntegrityError) as exc:
        ji.JdkManager._verify_archive(archive, "00" * 32, 17)
    assert str(exc.value) == "La suma de verificación del JDK 17 no coincide"


@pytest.mark.parametrize("error, expected", [
    (requests.ConnectionError(), "Se perdió la conexión a internet durante la descarga del JDK"),
    (requests.Timeout(), "Se agotó el tiempo de espera de la descarga del JDK"),
    (requests.RequestException("boom"), "La descarga del JDK falló: boom"),
])
def test_jdk_download_errors(spanish, tmp_path, error, expected):
    with patch("app.services.java_installer.stream_to_file", side_effect=error):
        with pytest.raises(ji.JdkDownloadError) as exc:
            ji.JdkManager()._download_file("https://x", tmp_path / "jdk.zip")
    assert str(exc.value) == expected


def test_jdk_download_permission_denied(spanish, tmp_path):
    dest = tmp_path / "jdk.zip"
    with patch("app.services.java_installer.stream_to_file", side_effect=PermissionError("locked")):
        with pytest.raises(ji.JdkDownloadError) as exc:
            ji.JdkManager()._download_file("https://x", dest)
    assert str(exc.value) == f"No se puede escribir {dest}: permiso denegado (locked)"


def test_jdk_download_cancelled(spanish, tmp_path):
    cancel = MagicMock()
    cancel.is_set.return_value = True

    def fake_stream(_url, _dest, timeout, progress_callback):
        progress_callback(0.5)

    with patch("app.services.java_installer.stream_to_file", side_effect=fake_stream):
        with pytest.raises(ji.JdkCancelled) as exc:
            ji.JdkManager()._download_file("https://x", tmp_path / "jdk.zip", cancel)
    assert str(exc.value) == "Descarga del JDK cancelada"


def test_jdk_unsafe_zip_member(spanish, tmp_path):
    archive = tmp_path / "jdk.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("jdk-17/bin/java", "x")
        zf.writestr("jdk-17/../../evil.sh", "x")
    with pytest.raises(ji.JdkIntegrityError) as exc:
        ji.JdkManager()._extract_archive(archive, tmp_path / "dest")
    assert str(exc.value) == "Ruta no segura en el archivo zip: jdk-17/../../evil.sh"


def test_jdk_unsafe_tar_member(spanish, tmp_path):
    archive = tmp_path / "jdk.tar.gz"
    with tarfile.open(archive, "w:gz") as tf:
        for name in ("jdk-17/bin/java", "jdk-17/../../evil.sh"):
            info = tarfile.TarInfo(name=name)
            info.size = 1
            tf.addfile(info, io.BytesIO(b"x"))
    with pytest.raises(ji.JdkIntegrityError) as exc:
        ji.JdkManager()._extract_archive(archive, tmp_path / "dest")
    assert str(exc.value) == "Ruta no segura en el archivo tar: jdk-17/../../evil.sh"


# ---------------------------------------------------------------------------
# modrinth
# ---------------------------------------------------------------------------

def _modrinth_response(status, text="", json_error=False):
    resp = MagicMock(status_code=status, text=text, headers={"X-Ratelimit-Reset": "0"})
    if json_error:
        resp.json.side_effect = ValueError
    return resp


def test_modrinth_network_errors(spanish):
    client = ModrinthClient()
    with patch.object(client.session, "request", side_effect=requests.ConnectionError("down")):
        with pytest.raises(ModrinthException) as exc:
            client._request("GET", "/search")
    assert str(exc.value) == "Error de red: down"

    with patch.object(client.session, "request",
                      side_effect=[_modrinth_response(429), requests.ConnectionError("down")]), \
         patch("app.services.modrinth.time.sleep"):
        with pytest.raises(ModrinthException) as exc:
            client._request("GET", "/search")
    assert str(exc.value) == "Error de red al reintentar: down"


def test_modrinth_api_errors(spanish):
    client = ModrinthClient()
    with patch.object(client.session, "request", return_value=_modrinth_response(404, "Not found")):
        with pytest.raises(ModrinthException) as exc:
            client._request("GET", "/project/x")
    assert str(exc.value) == "Error 404 de la API de Modrinth: Not found"

    with patch.object(client.session, "request", return_value=_modrinth_response(200, json_error=True)):
        with pytest.raises(ModrinthException) as exc:
            client._request("GET", "/project/x")
    assert str(exc.value) == "JSON no válido de la API de Modrinth"


# ---------------------------------------------------------------------------
# playit_api
# ---------------------------------------------------------------------------

@pytest.fixture
def playit(tmp_path):
    toml = tmp_path / "playit.toml"
    toml.write_text("secret_key='test-secret-key'", encoding="utf-8")
    client = PlayitApiClient()
    client.toml_path = str(toml)
    return client


def _playit_response(status, body=None, text=None):
    resp = MagicMock(status_code=status)
    if body is None:
        resp.json.side_effect = ValueError
    else:
        resp.json.return_value = body
    resp.text = text if text is not None else json.dumps(body or {})
    return resp


def test_playit_no_secret(spanish, tmp_path):
    client = PlayitApiClient()
    client.toml_path = str(tmp_path / "missing.toml")
    with pytest.raises(PlayitApiException) as exc:
        client._request("agents/rundata")
    assert str(exc.value) == "No hay una clave secreta cargada. No se puede autenticar."


def test_playit_network_error(spanish, playit):
    with patch.object(playit.session, "request", side_effect=requests.ConnectionError("down")):
        with pytest.raises(PlayitApiException) as exc:
            playit._request("agents/rundata")
    assert str(exc.value) == "Error de red al comunicarse con la API de Playit: down"


@pytest.mark.parametrize("text, expected", [
    ("AgentDisabledOverLimit",
     "AgentDisabledOverLimit: Se alcanzó el límite de agentes. Elimine los agentes antiguos en "
     "playit.gg/dashboard"),
    ("NotAllowedWithReadOnly",
     "NotAllowedWithReadOnly: La cuenta está en modo invitado (solo lectura). "
     "Use la CLI para administrar túneles."),
    ("", "La API de Playit devolvió HTTP 500: Error desconocido de la API"),
])
def test_playit_http_errors(spanish, playit, text, expected):
    with patch.object(playit.session, "request", return_value=_playit_response(500, text=text)):
        with pytest.raises(PlayitApiException) as exc:
            playit._request("tunnels/create")
    assert str(exc.value) == expected


def test_playit_read_only_keeps_matchable_token(spanish, playit):
    """playit_manager branches on the untranslated code in the message."""
    with patch.object(playit.session, "request",
                      return_value=_playit_response(403, text="NotAllowedWithReadOnly")):
        with pytest.raises(PlayitApiException) as exc:
            playit._request("tunnels/create")
    assert "NotAllowedWithReadOnly" in str(exc.value)


def test_playit_invalid_json(spanish, playit):
    with patch.object(playit.session, "request", return_value=_playit_response(200, text="<html>")):
        with pytest.raises(PlayitApiException) as exc:
            playit._request("agents/rundata")
    assert str(exc.value) == "Respuesta JSON no válida de la API de Playit (HTTP 200)"


def test_playit_bridge_errors(spanish, playit):
    with patch("requests.post", side_effect=requests.ConnectionError("down")):
        with pytest.raises(PlayitApiException) as exc:
            playit.link_account("code")
    assert str(exc.value) == "No se pudo conectar con el puente: down"

    with patch("requests.post", return_value=_playit_response(502, text="bad gateway")):
        with pytest.raises(PlayitApiException) as exc:
            playit.link_account("code")
    assert str(exc.value) == "JSON no válido del puente (HTTP 502): bad gateway"

    with patch("requests.post", return_value=_playit_response(400, {"status": "fail"}, text="nope")):
        with pytest.raises(PlayitApiException) as exc:
            playit.link_account("code")
    assert str(exc.value) == "Falló el intercambio con el puente (HTTP 400): nope"

    with patch("requests.post", return_value=_playit_response(200, {"status": "success"})):
        with pytest.raises(PlayitApiException) as exc:
            playit.link_account("code")
    assert str(exc.value) == "El puente no devolvió una clave secreta: {'status': 'success'}"


def test_playit_link_cannot_write_toml(spanish, playit, tmp_path):
    playit.toml_path = str(tmp_path / "dir" / "playit.toml")
    ok = _playit_response(200, {"data": {"agent_secret_key": "k", "agent_id": "a"}})
    with patch("requests.post", return_value=ok), \
         patch("builtins.open", side_effect=OSError("locked")):
        with pytest.raises(PlayitApiException) as exc:
            playit.link_account("code")
    assert str(exc.value) == (
        f"Se vinculó correctamente, pero no se pudo escribir {playit.toml_path}: locked. "
        "Cierre cualquier programa que use este archivo e inténtelo de nuevo.")


def test_playit_rundata_and_tunnel_errors(spanish, playit):
    with patch.object(playit, "_request", return_value={"status": "fail"}):
        with pytest.raises(PlayitApiException) as exc:
            playit.get_agent_rundata()
    assert str(exc.value) == "No se pudieron obtener los datos del agente: {'status': 'fail'}"

    with patch.object(playit, "get_agent_id", return_value=None):
        with pytest.raises(PlayitApiException) as exc:
            playit.create_tunnel()
    assert str(exc.value) == ("No se puede crear el túnel: no hay un agent_id disponible. "
                              "Asegúrese de que Playit esté vinculado.")

    with patch.object(playit, "get_agent_id", return_value="agent"), \
         patch.object(playit, "_request", return_value={"status": "fail"}):
        with pytest.raises(PlayitApiException) as exc:
            playit.create_tunnel()
    assert str(exc.value) == "No se pudo crear el túnel: {'status': 'fail'}"

    with patch.object(playit, "get_agent_id", return_value="agent"), \
         patch.object(playit, "_request", return_value={"status": "success", "data": {}}):
        with pytest.raises(PlayitApiException) as exc:
            playit.create_tunnel()
    assert str(exc.value) == "La creación del túnel se completó, pero no devolvió un ID."


def test_playit_create_tunnel_polls_for_address(playit):
    created = {"status": "success", "data": {"id": "t1"}}
    with patch.object(playit, "get_agent_id", return_value="agent"), \
         patch.object(playit, "_request", return_value=created), \
         patch.object(playit, "get_tunnel_address", side_effect=[None, "x.playit.gg:1"]), \
         patch.object(playit, "list_tunnels", return_value=[{"id": "t1"}]), \
         patch("app.services.playit_api.time.sleep"):
        tunnel = playit.create_tunnel()
    assert tunnel["id"] == "t1"


# ---------------------------------------------------------------------------
# player_identity
# ---------------------------------------------------------------------------

@pytest.fixture
def server(tmp_path):
    (tmp_path / "srv").mkdir()
    with patch.object(pi, "SERVERS_DIR", str(tmp_path)):
        yield


def test_player_invalid_name(spanish, server):
    with pytest.raises(pi.PlayerLookupError) as exc:
        pi.resolve_player("srv", "ab", True)
    assert str(exc.value) == "'ab' no es un nombre de jugador válido (3-16 letras, números o _)."


def test_player_bedrock_not_joined(spanish, server):
    with pytest.raises(pi.PlayerLookupError) as exc:
        pi.resolve_player("srv", ".Bedrock", True)
    assert str(exc.value) == (
        "El jugador de Bedrock '.Bedrock' aún no ha entrado a este servidor: pídale que entre una vez primero.")


def test_player_mojang_offline(spanish, server):
    with patch.object(pi, "mojang_profile", side_effect=requests.ConnectionError()):
        with pytest.raises(pi.PlayerLookupError) as exc:
            pi.resolve_player("srv", "Steve", True)
    assert str(exc.value) == (
        "No se pudo buscar a 'Steve' (sin conexión con Mojang). Inténtelo de nuevo o agréguelo mientras "
        "el servidor está en ejecución.")


def test_player_unknown_account(spanish, server):
    with patch.object(pi, "mojang_profile", return_value=None):
        with pytest.raises(pi.PlayerLookupError) as exc:
            pi.resolve_player("srv", "Nobody123", True)
    assert str(exc.value) == "No existe ninguna cuenta de Minecraft llamada 'Nobody123'."


def test_messages_stay_english_by_default(tmp_path, monkeypatch):
    monkeypatch.setattr(migration, "SERVERS_DIR", str(tmp_path))
    with pytest.raises(migration.MigrationError, match="Server 'nope' does not exist"):
        migration.export_server("nope", str(tmp_path / "out.zbbpack"))
    assert Path(tmp_path).is_dir()
