"""Unit tests for ModrinthClient.get_required_dependencies (app/services/modrinth.py)."""

from unittest.mock import patch

from app.services.modrinth import ModrinthClient


class TestGetRequiredDependencies:
    def _make_client(self):
        return ModrinthClient()

    @patch("app.services.modrinth.ModrinthClient.get_versions")
    @patch("app.services.modrinth.ModrinthClient.get_project")
    def test_required_dependency_resolved(self, mock_project, mock_versions):
        mock_project.return_value = {"id": "fabric-api", "slug": "fabric-api", "title": "Fabric API"}
        mock_versions.return_value = [{"id": "v1", "version_number": "0.90.0"}]
        version = {
            "dependencies": [
                {"dependency_type": "required", "project_id": "fabric-api"},
            ]
        }
        client = self._make_client()
        result = client.get_required_dependencies(version, "1.20.1", "fabric", installed_slugs=set())

        assert len(result["required"]) == 1
        assert result["required"][0]["project"]["slug"] == "fabric-api"
        assert result["incompatible"] == []

    @patch("app.services.modrinth.ModrinthClient.get_versions")
    @patch("app.services.modrinth.ModrinthClient.get_project")
    def test_already_installed_required_dep_skipped(self, mock_project, mock_versions):
        mock_project.return_value = {"id": "fabric-api", "slug": "fabric-api", "title": "Fabric API"}
        version = {
            "dependencies": [
                {"dependency_type": "required", "project_id": "fabric-api"},
            ]
        }
        client = self._make_client()
        result = client.get_required_dependencies(
            version, "1.20.1", "fabric", installed_slugs={"fabric-api"})

        assert result["required"] == []
        mock_versions.assert_not_called()

    @patch("app.services.modrinth.ModrinthClient.get_project")
    def test_incompatible_dependency_surfaced_separately(self, mock_project):
        mock_project.return_value = {"id": "optifine", "slug": "optifine", "title": "OptiFine"}
        version = {
            "dependencies": [
                {"dependency_type": "incompatible", "project_id": "optifine"},
            ]
        }
        client = self._make_client()
        result = client.get_required_dependencies(version, "1.20.1", "fabric", installed_slugs=set())

        assert result["required"] == []
        assert len(result["incompatible"]) == 1
        assert result["incompatible"][0]["project"]["slug"] == "optifine"

    @patch("app.services.modrinth.ModrinthClient.get_project")
    def test_optional_and_embedded_ignored(self, mock_project):
        version = {
            "dependencies": [
                {"dependency_type": "optional", "project_id": "cloth-config"},
                {"dependency_type": "embedded", "project_id": "some-lib"},
            ]
        }
        client = self._make_client()
        result = client.get_required_dependencies(version, "1.20.1", "fabric", installed_slugs=set())

        assert result["required"] == []
        assert result["incompatible"] == []
        mock_project.assert_not_called()
