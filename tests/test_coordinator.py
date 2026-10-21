from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

from custom_components.oura.api import OuraApiError, OuraAuthError, OuraPermissionError
from custom_components.oura.coordinator import OuraData, OuraDataUpdateCoordinator


def coordinator(hass, client, scopes=None):
    return OuraDataUpdateCoordinator(
        hass, client, timedelta(minutes=30), "test", "test-entry", scopes=scopes
    )


async def test_complete_outage_raises(hass):
    client = MagicMock(
        async_ensure_token_valid=AsyncMock(),
        async_get_collection=AsyncMock(side_effect=OuraApiError("offline")),
    )
    with pytest.raises(UpdateFailed):
        await coordinator(hass, client)._async_update_data()


async def test_partial_failure_preserves_status_not_false_success(hass):
    async def fetch(key, **kwargs):
        if key == "daily_spo2":
            raise OuraApiError("offline")
        return {"data": []}

    client = MagicMock(
        async_ensure_token_valid=AsyncMock(), async_get_collection=AsyncMock(side_effect=fetch)
    )
    instance = coordinator(hass, client)
    instance.async_set_updated_data(OuraData({"daily_spo2": {"data": [{"id": "cached"}]}}))
    data = await instance._async_update_data()
    assert data.unavailable["daily_spo2"] == "connection"
    assert data.payloads["daily_spo2"]["data"][0]["id"] == "cached"
    assert data.payloads["sleep"]["data"] == []


async def test_membership_is_not_reauthentication(hass):
    client = MagicMock(
        async_ensure_token_valid=AsyncMock(),
        async_get_collection=AsyncMock(side_effect=OuraPermissionError("membership")),
    )
    with pytest.raises(UpdateFailed, match="membership"):
        await coordinator(hass, client)._async_update_data()


async def test_auth_failure_propagates(hass):
    client = MagicMock(async_ensure_token_valid=AsyncMock(side_effect=OuraAuthError("expired")))
    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator(hass, client)._async_update_data()


async def test_declined_scopes_skip_optional_requests(hass):
    client = MagicMock(
        async_ensure_token_valid=AsyncMock(),
        async_get_collection=AsyncMock(return_value={"data": []}),
    )
    data = await coordinator(hass, client, {"personal", "daily"})._async_update_data()
    requested = {call.args[0] for call in client.async_get_collection.call_args_list}
    assert "workout" not in requested
    assert "heartrate" not in requested
    assert "daily_spo2" not in requested
    assert data.unavailable["workout"] == "permissions"
    assert "sleep" in requested


async def test_home_assistant_timezone_and_sparse_lookback(hass, freezer):
    from homeassistant.util import dt as dt_util

    dt_util.set_default_time_zone(dt_util.get_time_zone("America/Los_Angeles"))
    freezer.move_to("2026-10-22T02:00:00Z")
    client = MagicMock(
        async_ensure_token_valid=AsyncMock(),
        async_get_collection=AsyncMock(return_value={"data": []}),
    )
    data = await coordinator(hass, client)._async_update_data()
    assert data.today == "2026-10-21"
    requests = {call.args[0]: call.kwargs for call in client.async_get_collection.call_args_list}
    assert requests["vo2max"]["start_date"] == "2026-07-23"
    assert requests["sleep"]["end_date"] == "2026-10-21"
    assert requests["ring_battery_level"]["latest"] == "true"


async def test_webhook_updates_and_deletes_one_collection(hass):
    client = MagicMock(
        async_get_document=AsyncMock(return_value={"id": "new", "day": "2026-10-21", "score": 88})
    )
    instance = coordinator(hass, client)
    instance.async_set_updated_data(
        OuraData({"daily_sleep": {"data": [{"id": "old", "score": 50}]}, "workout": {"data": []}})
    )
    await instance.async_process_event("daily_sleep", "new", "update")
    assert {row["id"] for row in instance.data.payloads["daily_sleep"]["data"]} == {"old", "new"}
    assert instance.data.payloads["workout"] == {"data": []}
    await instance.async_process_event("daily_sleep", "new", "delete")
    assert instance.data.payloads["daily_sleep"]["data"] == [{"id": "old", "score": 50}]
    assert client.async_get_document.await_count == 1


async def test_failed_webhook_fetch_requests_refresh_without_deadlock(hass):
    import asyncio

    client = MagicMock(async_get_document=AsyncMock(side_effect=OuraApiError("offline")))
    instance = coordinator(hass, client)
    instance.async_set_updated_data(OuraData({"sleep": {"data": []}}))

    async def refresh():
        async with instance._refresh_lock:
            pass

    instance.async_request_refresh = AsyncMock(side_effect=refresh)
    await asyncio.wait_for(instance.async_process_event("sleep", "doc", "update"), timeout=1)
    instance.async_request_refresh.assert_awaited_once()


async def test_webhook_does_not_restore_unrelated_stale_collections(hass):
    client = MagicMock(
        async_get_document=AsyncMock(return_value={"id": "doc", "day": "2026-10-21"})
    )
    instance = coordinator(hass, client)
    instance.async_set_updated_data(
        OuraData({"daily_sleep": {"data": []}, "daily_readiness": {"data": [{"id": "old"}]}})
    )
    instance.last_update_success = False
    await instance.async_process_event("daily_sleep", "doc", "update")
    assert "daily_sleep" not in instance.data.unavailable
    assert instance.data.unavailable["daily_readiness"] == "connection"
