"""AppSettingsDialog notification logic, tested without a display.

Handlers run on a stand-in `self` so validation and persistence can be
checked without building the Tk dialog.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.ui.app_settings import AppSettingsDialog

VALID_URL = "https://discord.com/api/webhooks/123/abc"


def _entry(value=""):
    return MagicMock(get=MagicMock(return_value=value))


def _dialog(url=VALID_URL, role="", name="ZBB", avatar="", templates=None, template_text="", event_label=None):
    d = SimpleNamespace(
        entry_webhook=_entry(url),
        entry_webhook_role=_entry(role),
        entry_webhook_name=_entry(name),
        entry_webhook_avatar=_entry(avatar),
        entry_template=_entry(template_text),
        opt_template_event=_entry(event_label or "Server crashed"),
        _event_vars={"crashed": MagicMock(get=MagicMock(return_value=True)),
                     "ready": MagicMock(get=MagicMock(return_value=False))},
        _webhook_templates=dict(templates or {}),
        _settings=MagicMock(),
        zbb_manager=MagicMock(),
    )
    d._current_url = lambda: AppSettingsDialog._current_url(d)
    d._validate = lambda u: AppSettingsDialog._validate(d, u)
    d._current_template_key = lambda: AppSettingsDialog._current_template_key(d)
    return d


@pytest.fixture
def ui():
    with patch("app.ui.app_settings.ZBBDialog.info") as info, \
         patch("app.ui.app_settings.Toast.show") as toast:
        yield SimpleNamespace(info=info, toast=toast)


class TestSaveNotifications:
    def test_valid_settings_are_persisted_and_webhook_reloaded(self, ui):
        d = _dialog(role="987654321")
        AppSettingsDialog._save_notifications(d)

        saved = {c.args[0]: c.args[1] for c in d._settings.set.call_args_list}
        assert saved["discord_webhook_url"] == VALID_URL
        assert saved["webhook_events"] == {"crashed": True, "ready": False}
        assert saved["webhook_crash_mention_role"] == "987654321"
        d.zbb_manager.reload_discord_webhook.assert_called_once()
        assert ui.toast.call_args.kwargs["toast_type"] == "success"

    def test_empty_url_disables_notifications(self, ui):
        d = _dialog(url="")
        AppSettingsDialog._save_notifications(d)
        d.zbb_manager.reload_discord_webhook.assert_called_once()
        assert ui.toast.call_args.kwargs["toast_type"] == "info"

    @pytest.mark.parametrize("url", ["http://discord.com/api/webhooks/1/x", "https://example.com/hook"])
    def test_non_discord_url_is_rejected(self, ui, url):
        d = _dialog(url=url)
        AppSettingsDialog._save_notifications(d)
        d._settings.set.assert_not_called()
        assert ui.info.call_args.args[1] == "Invalid Webhook URL"

    def test_non_numeric_role_is_rejected(self, ui):
        d = _dialog(role="@admins")
        AppSettingsDialog._save_notifications(d)
        d._settings.set.assert_not_called()
        assert ui.info.call_args.args[1] == "Invalid Role ID"

    def test_legacy_discordapp_domain_is_accepted(self, ui):
        d = _dialog(url="https://discordapp.com/api/webhooks/1/x")
        AppSettingsDialog._save_notifications(d)
        d._settings.set.assert_any_call("discord_webhook_url", "https://discordapp.com/api/webhooks/1/x")


class TestTemplates:
    def test_valid_template_is_stored(self, ui):
        d = _dialog(template_text="{server} crashed: {reason}")
        with patch.object(AppSettingsDialog, "_current_template_key", return_value="crashed"):
            AppSettingsDialog._apply_template(d)
        assert d._webhook_templates == {"crashed": "{server} crashed: {reason}"}

    def test_unknown_placeholder_is_rejected(self, ui):
        d = _dialog(template_text="{server} has {players}")
        with patch.object(AppSettingsDialog, "_current_template_key", return_value="crashed"):
            AppSettingsDialog._apply_template(d)
        assert d._webhook_templates == {}
        assert ui.info.call_args.args[1] == "Invalid Template"

    def test_empty_template_removes_override(self, ui):
        d = _dialog(template_text="", templates={"crashed": "old"})
        with patch.object(AppSettingsDialog, "_current_template_key", return_value="crashed"):
            AppSettingsDialog._apply_template(d)
        assert "crashed" not in d._webhook_templates
