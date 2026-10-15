import pytest

import app.services.template_manager as template_manager


@pytest.fixture(autouse=True)
def _no_shipped_templates(tmp_path, monkeypatch):
    """Tests see only the templates they create, not the ones in assets/."""
    monkeypatch.setattr(template_manager, "BUILTIN_TEMPLATES_DIR", str(tmp_path / "no-builtin"))


def test_list_templates_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(template_manager, "TEMPLATES_DIR", str(tmp_path / "templates"))
    assert template_manager.list_templates() == []


def test_save_and_load_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(template_manager, "TEMPLATES_DIR", str(tmp_path / "templates"))
    wizard_data = {"type": "Paper", "version": "1.21.1", "ram": 4096, "name": "myserver", "location": "C:/x"}
    template_manager.save_template("my-template", wizard_data, description="Test template")

    loaded = template_manager.load_template("my-template")
    assert loaded["type"] == "Paper"
    assert loaded["version"] == "1.21.1"
    assert loaded["ram"] == 4096
    assert "name" not in loaded
    assert "location" not in loaded
    assert loaded["_description"] == "Test template"


def test_list_templates_returns_summary(tmp_path, monkeypatch):
    monkeypatch.setattr(template_manager, "TEMPLATES_DIR", str(tmp_path / "templates"))
    template_manager.save_template("t1", {"type": "Fabric", "version": "1.20.1"}, description="desc1")

    templates = template_manager.list_templates()
    assert len(templates) == 1
    assert templates[0]["name"] == "t1"
    assert templates[0]["engine"] == "Fabric"
    assert templates[0]["description"] == "desc1"


def test_delete_template(tmp_path, monkeypatch):
    monkeypatch.setattr(template_manager, "TEMPLATES_DIR", str(tmp_path / "templates"))
    template_manager.save_template("temp", {"type": "Vanilla"})
    template_manager.delete_template("temp")
    assert template_manager.load_template("temp") is None


def test_load_template_missing_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(template_manager, "TEMPLATES_DIR", str(tmp_path / "templates"))
    assert template_manager.load_template("nonexistent") is None


# ----------------------------------------------------------------------
# Built-in templates ship inside assets/ (bundled into the exe); before
# this they lived in config/templates and never reached a packaged build.
# ----------------------------------------------------------------------
import json
from pathlib import Path

from app.core import resources


@pytest.fixture
def dirs(tmp_path, monkeypatch):
    user, builtin = tmp_path / "templates", tmp_path / "builtin"
    builtin.mkdir()
    monkeypatch.setattr(template_manager, "TEMPLATES_DIR", str(user))
    monkeypatch.setattr(template_manager, "BUILTIN_TEMPLATES_DIR", str(builtin))
    return user, builtin


def _write(folder: Path, name: str, data: dict):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.json").write_text(json.dumps(data), encoding="utf-8")


def test_builtin_templates_are_listed_on_a_fresh_install(dirs):
    _, builtin = dirs
    _write(builtin, "lite-smp", {"type": "Paper", "_description": "Small SMP"})
    assert template_manager.list_templates() == [
        {"name": "lite-smp", "engine": "Paper", "version": "", "description": "Small SMP"}]
    assert template_manager.load_template("lite-smp")["type"] == "Paper"


def test_user_template_overrides_a_builtin_with_the_same_name(dirs):
    user, builtin = dirs
    _write(builtin, "lite-smp", {"type": "Paper"})
    _write(user, "lite-smp", {"type": "Fabric"})
    _write(user, "mine", {"type": "Vanilla"})
    listed = {t["name"]: t["engine"] for t in template_manager.list_templates()}
    assert listed == {"lite-smp": "Fabric", "mine": "Vanilla"}
    assert template_manager.load_template("lite-smp")["type"] == "Fabric"


def test_builtin_templates_cannot_be_deleted(dirs):
    _, builtin = dirs
    _write(builtin, "lite-smp", {"type": "Paper"})
    template_manager.delete_template("lite-smp")
    assert (builtin / "lite-smp.json").exists()


def test_shipped_builtin_templates_are_valid():
    shipped = sorted((resources.assets_dir() / "templates").glob("*.json"))
    assert len(shipped) >= 4
    for path in shipped:
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["type"] in {"Vanilla", "Paper", "Purpur", "Fabric", "Forge", "NeoForge"}
