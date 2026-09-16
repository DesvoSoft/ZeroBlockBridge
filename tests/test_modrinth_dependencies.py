"""Unit tests for ModrinthClient.get_required_dependencies (app/services/modrinth.py)."""

from unittest.mock import patch

from app.services.modrinth import ModrinthClient, ModrinthException


class TestGetRequiredDependencies:
    def _make_client(self):
        return ModrinthClient()

    @patch("app.services.modrinth.ModrinthClient.get_versions")
    @patch("app.services.modrinth.ModrinthClient.get_projects")
    def test_required_dependency_resolved(self, mock_projects, mock_versions):
        mock_projects.return_value = [{"id": "fabric-api", "slug": "fabric-api", "title": "Fabric API"}]
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
    @patch("app.services.modrinth.ModrinthClient.get_projects")
    def test_already_installed_required_dep_skipped(self, mock_projects, mock_versions):
        mock_projects.return_value = [{"id": "fabric-api", "slug": "fabric-api", "title": "Fabric API"}]
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

    @patch("app.services.modrinth.ModrinthClient.get_projects")
    def test_incompatible_dependency_surfaced_separately(self, mock_projects):
        mock_projects.return_value = [{"id": "optifine", "slug": "optifine", "title": "OptiFine"}]
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

    @patch("app.services.modrinth.ModrinthClient.get_projects")
    def test_optional_and_embedded_ignored(self, mock_projects):
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
        mock_projects.assert_not_called()

    @patch("app.services.modrinth.ModrinthClient.get_versions")
    @patch("app.services.modrinth.ModrinthClient.get_versions_by_ids")
    @patch("app.services.modrinth.ModrinthClient.get_projects")
    def test_many_dependencies_fetched_in_bulk(self, mock_projects, mock_versions_by_ids, mock_versions):
        mock_projects.return_value = [
            {"id": "a", "slug": "lib-a", "title": "A"},
            {"id": "b", "slug": "lib-b", "title": "B"},
            {"id": "c", "slug": "lib-c", "title": "C"},
            {"id": "x", "slug": "bad-x", "title": "X"},
        ]
        mock_versions_by_ids.return_value = [{"id": "va"}, {"id": "vb"}]
        mock_versions.return_value = [{"id": "vc"}]
        version = {
            "dependencies": [
                {"dependency_type": "required", "project_id": "a", "version_id": "va"},
                {"dependency_type": "required", "project_id": "b", "version_id": "vb"},
                {"dependency_type": "required", "project_id": "c"},
                {"dependency_type": "required", "project_id": "a", "version_id": "va"},
                {"dependency_type": "incompatible", "project_id": "x"},
            ]
        }
        client = self._make_client()
        result = client.get_required_dependencies(version, "1.20.1", "fabric", installed_slugs=set())

        mock_projects.assert_called_once_with(["a", "b", "c", "x"])
        mock_versions_by_ids.assert_called_once_with(["va", "vb"])
        mock_versions.assert_called_once_with("c", mc_version="1.20.1", loader="fabric")
        assert [d["version"]["id"] for d in result["required"]] == ["va", "vb", "vc"]
        assert [d["project"]["slug"] for d in result["incompatible"]] == ["bad-x"]

    @patch("app.services.modrinth.ModrinthClient.get_projects")
    def test_missing_project_skipped(self, mock_projects):
        mock_projects.return_value = []
        version = {"dependencies": [{"dependency_type": "required", "project_id": "gone"}]}
        client = self._make_client()
        result = client.get_required_dependencies(version, "1.20.1", "fabric", installed_slugs=set())

        assert result == {"required": [], "incompatible": []}

    @patch("app.services.modrinth.ModrinthClient.get_projects")
    def test_bulk_project_failure_returns_empty(self, mock_projects):
        mock_projects.side_effect = ModrinthException("Network error")
        version = {"dependencies": [{"dependency_type": "required", "project_id": "a"}]}
        client = self._make_client()
        result = client.get_required_dependencies(version, "1.20.1", "fabric", installed_slugs=set())

        assert result == {"required": [], "incompatible": []}
