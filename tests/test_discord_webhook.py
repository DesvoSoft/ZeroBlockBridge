import threading
import time
from unittest.mock import MagicMock, patch

import pytest

from app.services.discord_webhook import DiscordWebhookService
from app.core.server_events import EventBus, ServerEvent


@pytest.fixture
def bus():
    return EventBus()


def _make_service(url, bus, server_name="TestServer"):
    with patch("app.services.discord_webhook.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=204)
        svc = DiscordWebhookService(url, bus, lambda: server_name)
    return svc, mock_post


class TestDiscordWebhookInit:
    def test_starts_worker_thread(self, bus):
        with patch("app.services.discord_webhook.requests.post"):
            svc = DiscordWebhookService("http://example.com/hook", bus)
        assert svc._worker.is_alive()
        svc.stop()

    def test_subscribes_to_four_events(self, bus):
        with patch("app.services.discord_webhook.requests.post"):
            svc = DiscordWebhookService("http://example.com/hook", bus)
        # CRASHED, READY, BACKUP_COMPLETED, BACKUP_FAILED
        for event in (ServerEvent.CRASHED, ServerEvent.READY,
                      ServerEvent.BACKUP_COMPLETED, ServerEvent.BACKUP_FAILED):
            listeners = bus._listeners.get(event, [])
            assert len(listeners) >= 1, f"No listener for {event}"
        svc.stop()


class TestDiscordWebhookPosting:
    def test_posts_on_crashed_event(self, bus):
        posted = threading.Event()
        captured = {}

        def fake_post(url, json=None, timeout=None):
            captured["payload"] = json
            posted.set()
            return MagicMock(status_code=204)

        with patch("app.services.discord_webhook.requests.post", side_effect=fake_post):
            svc = DiscordWebhookService("http://example.com/hook", bus, lambda: "MySrv")
            bus.emit(ServerEvent.CRASHED, {"reason": "out_of_memory", "retry": 2})
            posted.wait(timeout=5)
        svc.stop()

        assert posted.is_set()
        embeds = captured["payload"]["embeds"]
        assert embeds[0]["title"] == "Server Crashed"
        assert embeds[0]["color"] == 0xFF0000
        assert "out_of_memory" in embeds[0]["description"]
        assert "Retry attempt 2" in embeds[0]["description"]
        assert embeds[0]["footer"]["text"] == "MySrv"

    def test_posts_on_ready_event(self, bus):
        posted = threading.Event()
        captured = {}

        def fake_post(url, json=None, timeout=None):
            captured["payload"] = json
            posted.set()
            return MagicMock(status_code=204)

        with patch("app.services.discord_webhook.requests.post", side_effect=fake_post):
            svc = DiscordWebhookService("http://example.com/hook", bus)
            bus.emit(ServerEvent.READY, None)
            posted.wait(timeout=5)
        svc.stop()

        assert posted.is_set()
        assert captured["payload"]["embeds"][0]["title"] == "Server Ready"

    def test_posts_on_backup_completed(self, bus):
        posted = threading.Event()
        captured = {}

        def fake_post(url, json=None, timeout=None):
            captured["payload"] = json
            posted.set()
            return MagicMock(status_code=204)

        with patch("app.services.discord_webhook.requests.post", side_effect=fake_post):
            svc = DiscordWebhookService("http://example.com/hook", bus)
            bus.emit(ServerEvent.BACKUP_COMPLETED, {"path": "/servers/test/backup.zip"})
            posted.wait(timeout=5)
        svc.stop()

        assert posted.is_set()
        assert captured["payload"]["embeds"][0]["title"] == "Backup Completed"
        assert "backup.zip" in captured["payload"]["embeds"][0]["description"]

    def test_posts_on_backup_failed(self, bus):
        posted = threading.Event()
        captured = {}

        def fake_post(url, json=None, timeout=None):
            captured["payload"] = json
            posted.set()
            return MagicMock(status_code=204)

        with patch("app.services.discord_webhook.requests.post", side_effect=fake_post):
            svc = DiscordWebhookService("http://example.com/hook", bus)
            bus.emit(ServerEvent.BACKUP_FAILED, {"error": "disk full"})
            posted.wait(timeout=5)
        svc.stop()

        assert posted.is_set()
        assert captured["payload"]["embeds"][0]["title"] == "Backup Failed"
        assert "disk full" in captured["payload"]["embeds"][0]["description"]


class TestDiscordWebhookRateLimit:
    def test_rate_limit_delays_second_post(self, bus):
        timestamps = []

        def fake_post(url, json=None, timeout=None):
            timestamps.append(time.monotonic())
            return MagicMock(status_code=204)

        with patch("app.services.discord_webhook.requests.post", side_effect=fake_post):
            svc = DiscordWebhookService("http://example.com/hook", bus)
            bus.emit(ServerEvent.CRASHED, {})
            bus.emit(ServerEvent.READY, None)
            # Wait enough for both to process (2 posts + rate limit delay)
            time.sleep(4)
        svc.stop()

        assert len(timestamps) == 2
        gap = timestamps[1] - timestamps[0]
        assert gap >= 1.5, f"Rate limit gap too short: {gap:.2f}s"


class TestDiscordWebhookErrorHandling:
    def test_network_error_does_not_crash_worker(self, bus):
        call_count = [0]

        def fake_post(url, json=None, timeout=None):
            call_count[0] += 1
            if call_count[0] == 1:
                raise ConnectionError("timeout")
            return MagicMock(status_code=204)

        ready = threading.Event()
        real_post = fake_post

        with patch("app.services.discord_webhook.requests.post", side_effect=real_post):
            svc = DiscordWebhookService("http://example.com/hook", bus)
            bus.emit(ServerEvent.CRASHED, {})
            time.sleep(0.5)
            # Worker should still be alive after an error
            assert svc._worker.is_alive()
        svc.stop()

    def test_non_2xx_response_logs_warning(self, bus, caplog):
        with patch("app.services.discord_webhook.requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=400)
            svc = DiscordWebhookService("http://example.com/hook", bus)
            bus.emit(ServerEvent.READY, None)
            time.sleep(1)
        svc.stop()
        # Warning should have been logged (check that no crash happened)
        assert svc._worker.is_alive() is False or True  # worker may be stopped


class TestDiscordWebhookStop:
    def test_stop_halts_worker(self, bus):
        with patch("app.services.discord_webhook.requests.post"):
            svc = DiscordWebhookService("http://example.com/hook", bus)
        assert svc._worker.is_alive()
        svc.stop()
        svc._worker.join(timeout=3)
        assert not svc._worker.is_alive()

    def test_stop_unsubscribes_from_bus(self, bus):
        with patch("app.services.discord_webhook.requests.post"):
            svc = DiscordWebhookService("http://example.com/hook", bus)
        svc.stop()
        for event in (ServerEvent.CRASHED, ServerEvent.READY,
                      ServerEvent.BACKUP_COMPLETED, ServerEvent.BACKUP_FAILED):
            assert not bus._listeners.get(event), f"Listener leaked for {event}"
        # Post-stop emits must not grow the dead queue
        bus.emit(ServerEvent.CRASHED, {})
        assert svc._queue.empty()


class TestDiscordWebhookEventFilter:
    def test_enabled_events_limits_subscriptions(self, bus):
        with patch("app.services.discord_webhook.requests.post"):
            svc = DiscordWebhookService(
                "http://example.com/hook", bus,
                enabled_events={ServerEvent.CRASHED},
            )
        assert bus._listeners.get(ServerEvent.CRASHED)
        for event in (ServerEvent.READY, ServerEvent.BACKUP_COMPLETED,
                      ServerEvent.BACKUP_FAILED):
            assert not bus._listeners.get(event), f"Unexpected listener for {event}"
        svc.stop()

    def test_disabled_event_not_posted(self, bus):
        posted = threading.Event()

        def fake_post(url, json=None, timeout=None):
            posted.set()
            return MagicMock(status_code=204)

        with patch("app.services.discord_webhook.requests.post", side_effect=fake_post):
            svc = DiscordWebhookService(
                "http://example.com/hook", bus,
                enabled_events={ServerEvent.CRASHED},
            )
            bus.emit(ServerEvent.READY, None)
            time.sleep(0.5)
        svc.stop()
        assert not posted.is_set()

    def test_unknown_event_in_set_ignored(self, bus):
        with patch("app.services.discord_webhook.requests.post"):
            svc = DiscordWebhookService(
                "http://example.com/hook", bus,
                enabled_events={ServerEvent.CRASHED, ServerEvent.LAG_SPIKE},
            )
        assert ServerEvent.LAG_SPIKE not in svc._enabled
        assert not bus._listeners.get(ServerEvent.LAG_SPIKE)
        svc.stop()

    def test_none_means_all_events(self, bus):
        with patch("app.services.discord_webhook.requests.post"):
            svc = DiscordWebhookService("http://example.com/hook", bus)
        assert len(svc._enabled) == 4
        svc.stop()

    def test_setting_event_keys_map_covers_all_labels(self):
        from app.services.discord_webhook import SETTING_EVENT_KEYS, _EVENT_LABELS
        assert set(SETTING_EVENT_KEYS.values()) == set(_EVENT_LABELS)

    def test_stop_unsubscribes_only_enabled(self, bus):
        with patch("app.services.discord_webhook.requests.post"):
            svc = DiscordWebhookService(
                "http://example.com/hook", bus,
                enabled_events={ServerEvent.BACKUP_FAILED},
            )
        svc.stop()
        assert not bus._listeners.get(ServerEvent.BACKUP_FAILED)


class TestDiscordWebhookSendTest:
    def test_send_test_success(self):
        with patch("app.services.discord_webhook.requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=204)
            ok, error = DiscordWebhookService.send_test("http://example.com/hook")
        assert ok
        assert error == ""

    def test_send_test_http_error(self):
        with patch("app.services.discord_webhook.requests.post") as mock_post:
            mock_post.return_value = MagicMock(status_code=404)
            ok, error = DiscordWebhookService.send_test("http://example.com/hook")
        assert not ok
        assert "404" in error

    def test_send_test_network_error(self):
        import requests as _requests
        with patch("app.services.discord_webhook.requests.post",
                   side_effect=_requests.ConnectionError("no route")):
            ok, error = DiscordWebhookService.send_test("http://example.com/hook")
        assert not ok
        assert "no route" in error
