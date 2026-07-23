import app.services.template_manager as template_manager


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
