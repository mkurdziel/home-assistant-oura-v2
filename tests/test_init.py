from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import ServiceValidationError
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.oura.const import DOMAIN
from custom_components.oura.diagnostics import async_get_config_entry_diagnostics


@pytest.fixture
def setup_entry(hass):
    async def fetch(collection, **params):
        if collection == "personal_info":
            return {"id": "account-1", "email": "private@example.invalid"}
        if collection == "ring_configuration":
            return {
                "data": [
                    {
                        "id": "ring-1",
                        "hardware_type": "gen4",
                        "firmware_version": "1.2.3",
                        "set_up_at": "2026-01-01T00:00:00Z",
                    }
                ]
            }
        if collection == "ring_battery_level":
            return {
                "data": [
                    {
                        "timestamp": "2026-10-21T12:00:00Z",
                        "level": 0,
                        "charging": False,
                        "in_charger": True,
                    }
                ]
            }
        return {"data": []}

    client = MagicMock(
        async_ensure_token_valid=AsyncMock(), async_get_collection=AsyncMock(side_effect=fetch)
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=None,
        data={
            "auth_implementation": "test-app",
            "token": {
                "access_token": "synthetic-token",
                "refresh_token": "synthetic-refresh",
                "expires_at": 9999999999,
            },
        },
    )
    entry.add_to_hass(hass)
    implementation = MagicMock(client_id="synthetic-client", client_secret="synthetic-secret")
    with (
        patch(
            "custom_components.oura.config_entry_oauth2_flow.async_get_config_entry_implementation",
            AsyncMock(return_value=implementation),
        ),
        patch("custom_components.oura.OuraApiClient", return_value=client),
    ):
        yield entry, client


async def test_setup_creates_entities_without_outbound_webhooks(hass, setup_entry):
    entry, client = setup_entry
    with patch(
        "custom_components.oura.webhooks.OuraWebhooks._request", AsyncMock()
    ) as webhook_request:
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    webhook_request.assert_not_called()
    assert entry.unique_id == "account-1"
    assert entry.data["user_id"] == "account-1"
    assert hass.states.get("sensor.oura_v2_ring_battery").state == "0"
    assert hass.states.get("binary_sensor.oura_v2_charging").state == "off"
    assert hass.states.get("binary_sensor.oura_v2_in_charger").state == "on"
    assert hass.states.get("binary_sensor.oura_v2_rest_mode").state == "off"
    assert hass.states.get("sensor.oura_v2_sleep_total_duration").state == "unknown"
    assert hass.states.get("sensor.oura_v2_workouts_today").state == "0"
    from homeassistant.helpers import device_registry as dr

    device = next(iter(dr.async_entries_for_config_entry(dr.async_get(hass), entry.entry_id)))
    assert device.model == "gen4" and device.sw_version == "1.2.3"


async def test_refresh_service_and_unload(hass, setup_entry):
    entry, _ = setup_entry
    assert await hass.config_entries.async_setup(entry.entry_id)
    runtime = hass.data[DOMAIN][entry.entry_id]
    with patch.object(runtime["coordinator"], "async_request_refresh", AsyncMock()) as refresh:
        await hass.services.async_call(
            DOMAIN, "request_refresh", {"entry_id": entry.entry_id}, blocking=True
        )
        refresh.assert_awaited_once()
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN, "request_refresh", {"entry_id": "unknown"}, blocking=True
        )
    assert await hass.config_entries.async_unload(entry.entry_id)
    assert entry.entry_id not in hass.data[DOMAIN]


async def test_diagnostics_exclude_account_and_biometric_data(hass, setup_entry):
    entry, _ = setup_entry
    assert await hass.config_entries.async_setup(entry.entry_id)
    result = await async_get_config_entry_diagnostics(hass, entry)
    import json

    text = json.dumps(result)
    for secret in (
        "synthetic-token",
        "synthetic-refresh",
        "private@example.invalid",
        "account-1",
        "ring-1",
    ):
        assert secret not in text
    assert result["loaded"]
    assert result["collections"]["ring_configuration"]["records"] == 1


async def test_options_reload_and_validation(hass, setup_entry):
    entry, _ = setup_entry
    assert await hass.config_entries.async_setup(entry.entry_id)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == "form"
    with patch.object(hass.config_entries, "async_reload", AsyncMock(return_value=True)) as reload:
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], user_input={"scan_interval": 3600, "use_webhooks": False}
        )
        await hass.async_block_till_done()
        assert result["type"] == "create_entry"
        reload.assert_awaited_once_with(entry.entry_id)
    assert entry.options["scan_interval"] == 3600
