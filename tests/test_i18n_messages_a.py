"""Translated messages of the world/modpack import services
(content_import, mrpack_installer)."""

import json
import zipfile

import pytest

from app.core import i18n
from app.services import content_import
from app.services import mrpack_installer as m
from app.services.content_import import (
    ContentImportError,
    ModpackInfo,
    WorldInfo,
    inspect_modpack,
    inspect_world,
    modpack_mismatch,
    supported_loaders_text,
    world_version_check,
)


@pytest.fixture
def spanish():
    assert i18n.set_language("es") == "es"


def _zip(path, entries):
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
    return str(path)


def _manifest(entries, mc="1.20.1"):
    return {"formatVersion": 1, "game": "minecraft", "name": "Pack",
            "dependencies": {"minecraft": mc, "fabric-loader": "0.15.7"}, "files": entries}


def _install(tmp_path, monkeypatch, entries):
    """Run install_mrpack with every download failing; returns the progress texts."""
    monkeypatch.setattr(m, "download_with_verification", lambda url, dest, expected_sha1=None: (False, None, "x"))
    pack = _zip(tmp_path / "p.mrpack", {"modrinth.index.json": json.dumps(_manifest(entries)),
                                        "overrides/config/a.toml": "a"})
    server = tmp_path / "srv"
    server.mkdir()
    seen = []
    m.install_mrpack(pack, "srv", progress_callback=seen.append, server_dir=str(server))
    return seen


def _entries(server, client):
    out = [{"path": f"mods/s{i}.jar", "downloads": ["https://x/s"], "env": {"server": "required"}}
           for i in range(server)]
    out += [{"path": f"mods/c{i}.jar", "downloads": ["https://x/c"], "env": {"server": "unsupported"}}
            for i in range(client)]
    return out


# ----------------------------------------------------------------------
# English (source text, plural forms)
# ----------------------------------------------------------------------
def test_install_progress_counts_in_english(tmp_path, monkeypatch):
    seen = _install(tmp_path, monkeypatch, _entries(server=1, client=1))
    assert seen[1] == "Found 2 files in the modpack."
    assert seen[-2] == "Copying 1 file from overrides…"
    assert seen[-1] == ("Modpack installed: 0 mods. 1 client-only mod skipped. "
                        "1 mod failed to download.")


def test_install_progress_plural_in_english(tmp_path, monkeypatch):
    seen = _install(tmp_path, monkeypatch, _entries(server=2, client=2))
    assert seen[-1] == ("Modpack installed: 0 mods. 2 client-only mods skipped. "
                        "2 mods failed to download.")


def test_describe_singular_mod():
    assert ModpackInfo(path="p", kind="mrpack", name="n", mod_count=1).describe() == "1 mod"


def test_supported_loaders_text_english():
    assert supported_loaders_text() == "Fabric, Forge or NeoForge"


# ----------------------------------------------------------------------
# Spanish
# ----------------------------------------------------------------------
def test_supported_loaders_and_mismatch_spanish(spanish):
    assert supported_loaders_text() == "Fabric, Forge o NeoForge"
    info = ModpackInfo(path="p", kind="mrpack", name="n", loader="Fabric", mc_version="1.20.1")
    assert modpack_mismatch(info, "Paper", "1.20.1") == \
        "Los modpacks necesitan un servidor Fabric, Forge o NeoForge, no Paper."
    assert modpack_mismatch(info, "Forge", "1.20.1") == "Este modpack necesita un servidor Fabric, no Forge."
    assert modpack_mismatch(info, "Fabric", "1.21") == "Este modpack necesita Minecraft 1.20.1, no 1.21."


def test_describe_spanish_plural(spanish):
    one = ModpackInfo(path="p", kind="mrpack", name="n", mod_count=1)
    two = ModpackInfo(path="p", kind="mrpack", name="n", loader="Fabric", loader_version="0.15.7",
                      mc_version="1.20.1", mod_count=2)
    assert one.describe() == "1 mod"
    assert two.describe() == "Fabric 0.15.7 · Minecraft 1.20.1 · 2 mods"


def test_world_version_messages_spanish(spanish):
    newer = world_version_check(WorldInfo("w", "w", False, "w", mc_version="1.21.4"), "1.20.1")
    assert newer == ("error", "Este mundo se guardó con Minecraft 1.21.4, más reciente que este servidor "
                              "(1.20.1). Una versión anterior puede dañarlo: elija Minecraft "
                              "1.21.4 o posterior en el paso Motor y versión.")
    same = world_version_check(WorldInfo("w", "w", False, "w", mc_version="1.20.1"), "1.20.1")
    assert same == ("info", "Guardado con Minecraft 1.20.1, la misma versión que este servidor.")
    snap = world_version_check(WorldInfo("w", "w", False, "w", mc_version="24w14a", snapshot=True), "1.20.4")
    assert snap[1].startswith("Este mundo se guardó con la snapshot 24w14a.")


def test_import_errors_spanish(spanish, tmp_path):
    with pytest.raises(ContentImportError) as e:
        inspect_world(str(tmp_path / "missing"))
    assert str(e.value) == "Ese archivo o carpeta del mundo no existe."
    with pytest.raises(ContentImportError) as e:
        inspect_modpack(str(tmp_path / "missing.zip"))
    assert str(e.value) == "Ese archivo de modpack no existe."
    bad = tmp_path / "bad.zip"
    bad.write_text("not a zip")
    with pytest.raises(ContentImportError) as e:
        inspect_modpack(str(bad))
    assert str(e.value) == "Ese archivo no es un .zip válido."


def test_disk_space_error_spanish(spanish, tmp_path, monkeypatch):
    monkeypatch.setattr(content_import.shutil, "disk_usage", lambda p: type("U", (), {"free": 0})())
    archive = _zip(tmp_path / "w.zip", {"level.dat": "x"})
    with pytest.raises(ContentImportError) as e:
        content_import.validate_world(inspect_world(archive), str(tmp_path))
    assert str(e.value).startswith("No hay suficiente espacio en disco: el archivo comprimido necesita ")


def test_install_progress_spanish_singular(spanish, tmp_path, monkeypatch):
    seen = _install(tmp_path, monkeypatch, _entries(server=1, client=0))
    assert seen[0] == "Leyendo el manifiesto del modpack…"
    assert seen[1] == "Se encontró 1 archivo en el modpack."
    assert seen[2] == "Descargando mods 1/1…"
    assert seen[-2] == "Copiando 1 archivo de overrides…"
    assert seen[-1] == "Modpack instalado: 0 mods. No se pudo descargar 1 mod."


def test_install_progress_spanish_plural(spanish, tmp_path, monkeypatch):
    seen = _install(tmp_path, monkeypatch, _entries(server=2, client=2))
    assert seen[1] == "Se encontraron 4 archivos en el modpack."
    assert seen[-1] == ("Modpack instalado: 0 mods. Se omitieron 2 mods solo para cliente. "
                        "No se pudieron descargar 2 mods.")


def test_compatibility_errors_spanish(spanish):
    manifest = _manifest([])
    with pytest.raises(m.MrpackCompatibilityError) as e:
        m._check_compatibility(manifest, server_type="Paper", mc_version="1.20.1")
    assert str(e.value) == ("Este modpack requiere un servidor Fabric, pero 'Paper' no puede cargar sus mods. "
                            "Cree un servidor Fabric para usar este modpack.")
    with pytest.raises(m.MrpackCompatibilityError) as e:
        m._check_compatibility(manifest, server_type="Fabric", mc_version="1.19.4")
    assert str(e.value) == ("Este modpack es para Minecraft 1.20.1, pero el servidor usa 1.19.4. "
                            "Las versiones deben coincidir exactamente.")


def test_manifest_errors_spanish(spanish):
    with pytest.raises(ValueError) as e:
        m._validate_manifest({"formatVersion": 2, "files": []})
    assert str(e.value) == "Versión de formato mrpack no compatible: 2"
    with pytest.raises(ValueError) as e:
        m._validate_manifest({"formatVersion": 1})
    assert str(e.value) == "A modrinth.index.json le falta la clave 'files'."
