import hashlib
import hmac
import json
import time
from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import ConfigEntryError
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.oura.api import OuraApiError
from custom_components.oura.webhooks import OuraWebhooks


@pytest.fixture
def manager(hass):
    entry = MockConfigEntry(domain="oura", unique_id="account-1", data={"user_id": "account-1"})
    entry.add_to_hass(hass)
    coordinator = MagicMock(scopes={"daily"}, async_process_event=AsyncMock())
    implementation = MagicMock(client_id="test-client", client_secret="test-secret")
    instance = OuraWebhooks(hass, entry, coordinator, implementation)
    instance.state = {
        "id": "test-webhook-id",
        "verification_token": "test-verification",
        "subscriptions": [],
    }
    yield instance
    instance.async_stop()


def event_request(manager, payload=None, *, timestamp=None, signature=None, raw=None):
    event = {
        "user_id": "account-1",
        "data_type": "daily_sleep",
        "event_type": "update",
        "object_id": "document-1",
        "event_time": "2026-10-21T12:00:00Z",
    }
    event.update(payload or {})
    body = raw if raw is not None else json.dumps(event).encode()
    timestamp = str(int(time.time())) if timestamp is None else str(timestamp)
    if signature is None:
        signature = (
            hmac.new(manager.client_secret.encode(), timestamp.encode() + body, hashlib.sha256)
            .hexdigest()
            .upper()
        )
    return MagicMock(
        method="POST",
        headers={"x-oura-timestamp": timestamp, "x-oura-signature": signature},
        content=MagicMock(read=AsyncMock(side_effect=[body, b""])),
    )


async def test_verification_challenge(manager, hass):
    request = MagicMock(
        method="GET", query={"verification_token": "test-verification", "challenge": "challenge"}
    )
    result = await manager._handle(hass, "test-webhook-id", request)
    assert result.status == 200
    assert json.loads(result.text) == {"challenge": "challenge"}
    request.query["verification_token"] = "wrong"
    assert (await manager._handle(hass, "test-webhook-id", request)).status == 401


async def test_verified_event_routes_to_correct_account_and_deduplicates(manager, hass):
    for _ in range(2):
        result = await manager._handle(hass, "test-webhook-id", event_request(manager))
        assert result.status == 200
        await hass.async_block_till_done()
    manager.coordinator.async_process_event.assert_awaited_once_with(
        "daily_sleep", "document-1", "update"
    )


@pytest.mark.parametrize(
    ("arguments", "status"),
    [
        ({"signature": "invalid"}, 401),
        ({"timestamp": 0}, 401),
        ({"payload": {"user_id": "other-account"}}, 200),
        ({"payload": {"data_type": "unknown"}}, 400),
        ({"payload": {"event_type": "unknown"}}, 400),
        ({"payload": {"event_time": None}}, 400),
        ({"raw": b"not json"}, 400),
        ({"raw": b"x" * 65537}, 413),
    ],
)
async def test_invalid_webhooks_never_fetch_data(manager, hass, arguments, status):
    result = await manager._handle(hass, "test-webhook-id", event_request(manager, **arguments))
    assert result.status == status
    manager.coordinator.async_process_event.assert_not_called()


async def test_older_event_is_ignored(manager, hass):
    await manager._handle(hass, "test-webhook-id", event_request(manager))
    await manager._handle(
        hass,
        "test-webhook-id",
        event_request(manager, {"event_time": "2026-10-20T12:00:00Z", "event_type": "delete"}),
    )
    await hass.async_block_till_done()
    assert manager.coordinator.async_process_event.await_count == 1


async def test_external_https_is_required(manager):
    with (
        patch(
            "custom_components.oura.webhooks.webhook.async_generate_url",
            return_value="http://ha.example.invalid/api/webhook/test",
        ),
        pytest.raises(ConfigEntryError, match="HTTPS"),
    ):
        await manager.async_start()


async def test_subscriptions_are_persisted_and_not_duplicated(manager):
    url = "https://ha.example.invalid/api/webhook/test-webhook-id"
    expires = (dt_util.utcnow() + timedelta(days=2)).isoformat()
    remote = []

    async def create(method, path="", payload=None):
        if method == "get":
            return list(remote)
        assert method == "post"
        subscription = {**payload, "id": payload["event_type"], "expiration_time": expires}
        remote.append(subscription)
        return subscription

    with (
        patch("custom_components.oura.webhooks.WEBHOOK_TYPES", {"daily_sleep": "daily_sleep"}),
        patch.object(manager, "_request", AsyncMock(side_effect=create)) as request,
    ):
        await manager.async_reconcile(url)
        assert len(remote) == 3
        assert len(manager.entry.data["webhooks"]["subscriptions"]) == 3
        await manager.async_reconcile(url)
        assert len(remote) == 3
        assert request.await_count == 5  # Two inventories and three creations.


async def test_partial_setup_is_resumable(manager):
    url = "https://ha.example.invalid/api/webhook/test-webhook-id"
    expires = (dt_util.utcnow() + timedelta(days=2)).isoformat()
    with (
        patch("custom_components.oura.webhooks.WEBHOOK_TYPES", {"daily_sleep": "daily_sleep"}),
        patch.object(
            manager,
            "_request",
            AsyncMock(
                side_effect=[
                    [],
                    {"id": "first", "expiration_time": expires},
                    OuraApiError("offline"),
                ]
            ),
        ),
    ):
        with pytest.raises(OuraApiError):
            await manager.async_reconcile(url)
    assert len(manager.entry.data["webhooks"]["subscriptions"]) == 1


async def test_cleanup_only_deletes_owned_subscriptions(manager):
    manager.state["subscriptions"] = [{"id": "owned"}]
    with patch.object(manager, "_request", AsyncMock()) as request:
        await manager.async_cleanup()
    request.assert_awaited_once_with("delete", "/owned")
    assert manager.entry.data["webhooks"]["subscriptions"] == []


async def test_cleanup_failure_preserves_remote_id(manager):
    manager.state["subscriptions"] = [{"id": "owned"}]
    with (
        patch.object(manager, "_request", AsyncMock(side_effect=OuraApiError("offline"))),
        pytest.raises(OuraApiError),
    ):
        await manager.async_cleanup()
    assert manager.state["subscriptions"] == [{"id": "owned"}]


async def test_expiring_subscription_is_renewed(manager):
    url = "https://ha.example.invalid/api/webhook/test-webhook-id"
    manager.state["subscriptions"] = [
        {
            "id": "owned",
            "data_type": "daily_sleep",
            "event_type": "update",
            "callback_url": url,
            "expiration_time": (dt_util.utcnow() + timedelta(hours=1)).isoformat(),
        }
    ]
    with (
        patch.object(manager, "_desired_pairs", return_value=[("daily_sleep", "update")]),
        patch.object(
            manager,
            "_request",
            AsyncMock(
                side_effect=[
                    manager.state["subscriptions"],
                    {
                        "id": "owned",
                        "expiration_time": (dt_util.utcnow() + timedelta(days=2)).isoformat(),
                    },
                ]
            ),
        ) as request,
    ):
        await manager.async_reconcile(url)
    assert request.call_args.args == ("put", "/renew/owned")


async def test_start_registers_get_and_post_and_unloads(manager):
    with (
        patch(
            "custom_components.oura.webhooks.webhook.async_generate_url",
            return_value="https://ha.example.invalid/api/webhook/test-webhook-id",
        ),
        patch("custom_components.oura.webhooks.webhook.async_register") as register,
        patch("custom_components.oura.webhooks.webhook.async_unregister") as unregister,
        patch.object(manager, "async_reconcile", AsyncMock()),
    ):
        await manager.async_start()
        assert register.call_args.kwargs["allowed_methods"] == ["GET", "POST"]
        assert register.call_args.kwargs["local_only"] is False
        manager.async_stop()
        unregister.assert_called_once()


async def test_failed_subscription_setup_keeps_polling_and_schedules_retry(manager):
    with (
        patch(
            "custom_components.oura.webhooks.webhook.async_generate_url",
            return_value="https://ha.example.invalid/api/webhook/test-webhook-id",
        ),
        patch.object(manager, "async_reconcile", AsyncMock(side_effect=OuraApiError("offline"))),
    ):
        await manager.async_start()
    assert manager._registered
    assert manager._unsubscribe is not None
    assert manager.last_error == "offline"


async def test_untrusted_header_and_type_are_rejected(manager, hass):
    for request in (
        event_request(manager, signature="é" * 64),
        event_request(manager, {"data_type": ["daily_sleep"]}),
    ):
        assert (await manager._handle(hass, "test-webhook-id", request)).status in (400, 401)
    manager.coordinator.async_process_event.assert_not_called()


async def test_signature_uses_complete_chunked_body(manager, hass):
    request = event_request(manager)
    body = json.dumps(
        {
            "user_id": "account-1",
            "data_type": "daily_sleep",
            "event_type": "update",
            "object_id": "document-1",
            "event_time": "2026-10-21T12:00:00Z",
        }
    ).encode()
    request.content.read = AsyncMock(side_effect=[body[:10], body[10:50], body[50:], b""])
    result = await manager._handle(hass, "test-webhook-id", request)
    assert result.status == 200
    await hass.async_block_till_done()
    manager.coordinator.async_process_event.assert_awaited_once()


async def test_reconcile_recovers_unknown_creation_outcome_without_touching_other_callbacks(
    manager,
):
    url = "https://ha.example.invalid/api/webhook/test-webhook-id"
    remote = [
        {
            "id": "owned-but-not-saved",
            "data_type": "daily_sleep",
            "event_type": "update",
            "callback_url": url,
            "expiration_time": (dt_util.utcnow() + timedelta(days=2)).isoformat(),
        },
        {
            "id": "someone-elses",
            "data_type": "daily_sleep",
            "event_type": "update",
            "callback_url": "https://other.example.invalid/hook",
            "expiration_time": (dt_util.utcnow() + timedelta(days=2)).isoformat(),
        },
    ]
    with (
        patch.object(manager, "_desired_pairs", return_value=[("daily_sleep", "update")]),
        patch.object(manager, "_request", AsyncMock(return_value=remote)) as request,
    ):
        await manager.async_reconcile(url)
    request.assert_awaited_once_with("get")
    assert [item["id"] for item in manager.state["subscriptions"]] == ["owned-but-not-saved"]


async def test_subscription_api_uses_app_credentials_and_honors_rate_limit(manager, response):
    from custom_components.oura.api import OuraRateLimitError

    client = MagicMock(
        request=AsyncMock(return_value=response(429, headers={"Retry-After": "120"}))
    )
    with patch("custom_components.oura.webhooks.async_get_clientsession", return_value=client):
        for _ in range(2):
            with pytest.raises(OuraRateLimitError):
                await manager._request("get")
    assert client.request.await_count == 1
    assert client.request.call_args.kwargs["headers"] == {
        "x-client-id": "test-client",
        "x-client-secret": "test-secret",
    }
    assert manager.entry.data["webhooks"]["retry_at"] > time.time()
