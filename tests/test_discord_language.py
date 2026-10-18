"""Language of the Discord webhook messages: independent of the UI language."""
from unittest.mock import MagicMock, patch

import pytest

from app.core import i18n
from app.core.server_events import EventBus, ServerEvent
from app.services.discord_webhook import DiscordWebhookService, _fmt_duration


@pytest.fixture
def app_language():
    """Set the app (UI) language inside a test; English again afterwards."""
    yield i18n.set_language
    i18n.set_language("en")


def _render(event, data, language="auto", templates=None, server="Srv"):
    """The embed the service would post for one event."""
    sent = []

    def fake_post(url, json=None, timeout=None):
        sent.append(json)
        return MagicMock(status_code=204)

    with patch("app.services.discord_webhook.requests.post", side_effect=fake_post):
        svc = DiscordWebhookService("http://example.com/hook", EventBus(), lambda: server,
                                    templates=templates, language=language)
        svc.stop()
        svc._post(event, data)
    return sent[0]["embeds"][0]


class TestMessageLanguage:
    def test_english_defaults(self):
        e = _render(ServerEvent.CRASHED, {"reason": "oom", "retry": 2}, language="en")
        assert e["title"] == "Server Crashed"
        assert e["description"] == "Reason: `oom` — Retry attempt 2"

    def test_spanish_override_ignores_english_ui(self, app_language):
        app_language("en")
        e = _render(ServerEvent.CRASHED, {"reason": "oom", "retry": 2}, language="es")
        assert e["title"] == "Servidor caído"
        assert e["description"] == "Motivo: `oom` — Intento de reintento 2"

    def test_english_override_ignores_spanish_ui(self, app_language):
        app_language("es")
        assert _render(ServerEvent.READY, {}, language="en")["title"] == "Server Ready"

    def test_auto_follows_app_language(self, app_language):
        app_language("es")
        assert _render(ServerEvent.READY, {}, language="auto")["title"] == "Servidor listo"
        app_language("en")
        assert _render(ServerEvent.READY, {}, language="auto")["title"] == "Server Ready"

    def test_unknown_value_behaves_like_auto(self, app_language):
        app_language("es")
        assert _render(ServerEvent.READY, {}, language="fr")["title"] == "Servidor listo"

    def test_rendering_does_not_change_the_app_language(self, app_language):
        app_language("en")
        _render(ServerEvent.READY, {}, language="es")
        assert i18n.get_language() == "en"
        assert i18n._("Server Ready") == "Server Ready"

    @pytest.mark.parametrize("event,data", [
        (ServerEvent.STOPPED, {"uptime": 3700}),
        (ServerEvent.STOPPED, {}),
        (ServerEvent.RESTARTED, {"retry": 1, "context": "crash"}),
        (ServerEvent.ZOMBIE_DETECTED, {"silence_seconds": 90}),
        (ServerEvent.LAG_SPIKE, {"count": 4, "window_seconds": 300}),
        (ServerEvent.TUNNEL_STATUS, {"dns": "a.b.c"}),
        (ServerEvent.BACKUP_COMPLETED, {"path": "x.zip"}),
        (ServerEvent.BACKUP_COMPLETED, {}),
        (ServerEvent.BACKUP_FAILED, {"error": "disk full"}),
        (ServerEvent.CRASHED, {"reason": "oom", "retry": 1}),
        (ServerEvent.READY, {}),
    ])
    def test_every_default_is_translated(self, event, data):
        en = _render(event, data, language="en")
        es = _render(event, data, language="es")
        assert es["title"] != en["title"]
        if en["description"] and event != ServerEvent.BACKUP_FAILED:  # "Error: ..." reads the same
            assert es["description"] != en["description"]

    def test_players_flush_is_translated_and_plural(self):
        flush = {"joined": ["Ana"], "left": ["Luis", "Eva"], "online": 3}
        es = _render("_players_flush", flush, language="es")
        assert es["title"] == "Jugadores"
        assert es["description"] == "Se unió: **Ana**\nSalieron: **Luis**, **Eva**\nEn línea ahora: **3**"
        en = _render("_players_flush", flush, language="en")
        assert en["description"] == "Joined: **Ana**\nLeft: **Luis**, **Eva**\nOnline now: **3**"

    def test_lag_spike_plural(self):
        def lag(count, language):
            return _render(ServerEvent.LAG_SPIKE, {"count": count, "window_seconds": 300},
                           language=language)["description"]
        assert lag(1, "es").startswith("1 advertencia de TPS")
        assert lag(5, "es").startswith("5 advertencias de TPS")
        assert lag(1, "en").startswith("1 TPS warning in")
        assert lag(5, "en").startswith("5 TPS warnings in")

    def test_durations_are_locale_aware(self):
        assert _fmt_duration(3700, "en") == "1h 1m"
        assert _fmt_duration(3700, "es") == "1 h 1 min"
        assert _fmt_duration(125, "es") == "2 min 5 s"
        assert _fmt_duration(7, "es") == "7 s"
        assert _fmt_duration(7) == "7s"
        e = _render(ServerEvent.STOPPED, {"uptime": 3700}, language="es")
        assert e["description"] == "Apagado normal tras 1 h 1 min."


class TestCustomTemplatesUntouched:
    TEMPLATES = {"crashed": "{server} crashed: {reason} (try {retry})", "stopped": "up {uptime}"}

    def test_template_is_posted_as_written_in_any_language(self, app_language):
        app_language("es")
        for lang in ("auto", "en", "es"):
            e = _render(ServerEvent.CRASHED, {"reason": "oom", "retry": 2},
                        language=lang, templates=self.TEMPLATES)
            assert e["description"] == "Srv crashed: oom (try 2)"

    def test_placeholder_values_stay_english(self):
        e = _render(ServerEvent.STOPPED, {"uptime": 3700}, language="es", templates=self.TEMPLATES)
        assert e["description"] == "up 1h 1m"


class TestTestMessage:
    @staticmethod
    def _send(language):
        with patch("app.services.discord_webhook.requests.post") as post:
            post.return_value = MagicMock(status_code=204)
            assert DiscordWebhookService.send_test("http://x", language=language) == (True, "")
        return post.call_args.kwargs["json"]["embeds"][0]["description"]

    def test_english_and_spanish(self):
        assert self._send("en") == "Webhook test successful. Notifications will appear here."
        assert self._send("es").startswith("La prueba del webhook fue exitosa")

    def test_auto_follows_app_language(self, app_language):
        app_language("es")
        assert self._send("auto").startswith("La prueba")
        assert self._send("en").startswith("Webhook test")


def test_default_setting_is_auto():
    from app.services.settings_manager import SettingsManager
    assert SettingsManager()._get_defaults()["discord_language"] == "auto"


class TestCatalogForAnotherLanguage:
    def test_catalog_is_independent_of_the_app_language(self, app_language):
        app_language("en")
        assert i18n.catalog("es").gettext("Players") == "Jugadores"
        assert i18n.catalog("en").gettext("Players") == "Players"
        assert i18n.catalog("xx").gettext("Players") == "Players"
        assert i18n.format_number(2.5, 1, language="es") == "2,5"
        assert i18n.format_number(2.5, 1) == "2.5"

    def test_resolve_language(self, app_language):
        app_language("es")
        assert i18n.resolve_language("auto") == "es"
        assert i18n.resolve_language("en") == "en"
        assert i18n.resolve_language(None) == "es"


def test_missing_retry_count_does_not_break_the_message():
    e = _render(ServerEvent.CRASHED, {"reason": "x", "retry": None}, language="es")
    assert e["description"].endswith("reintento 0")
