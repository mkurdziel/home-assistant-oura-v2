from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.oura.config_flow import OAuth2FlowHandler, OuraOptionsFlow
from custom_components.oura.const import DOMAIN

TOKEN = {
    "token": {
        "access_token": "synthetic-token",
        "refresh_token": "synthetic-refresh",
        "expires_at": 9999999999,
        "expires_in": 86400,
    },
    "auth_implementation": "test-app",
}


def flow(hass, entry=None):
    result = OAuth2FlowHandler()
    result.hass = hass
    result.flow_id = "test-flow"
    result.handler = DOMAIN
    result.context = {"source": config_entries.SOURCE_USER}
    if entry:
        result.context = {"source": config_entries.SOURCE_REAUTH, "entry_id": entry.entry_id}
    return result


async def test_create_identifies_account_without_oauth_session(hass, response):
    instance = flow(hass)
    with patch(
        "custom_components.oura.config_flow.config_entry_oauth2_flow.async_oauth2_request",
        AsyncMock(return_value=response(body={"id": "account-1"})),
    ) as request:
        result = await instance.async_oauth_create_entry(TOKEN)
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["data"]["user_id"] == "account-1"
    assert instance.unique_id == "account-1"
    assert request.call_args.args[1] == TOKEN["token"]
    assert "heart_health" in instance.extra_authorize_data["scope"].split()


async def test_duplicate_account_aborts(hass, response):
    entry = MockConfigEntry(domain=DOMAIN, unique_id="account-1", data=TOKEN)
    entry.add_to_hass(hass)
    from homeassistant.data_entry_flow import AbortFlow

    with (
        patch(
            "custom_components.oura.config_flow.config_entry_oauth2_flow.async_oauth2_request",
            AsyncMock(return_value=response(body={"id": "account-1"})),
        ),
        pytest.raises(AbortFlow) as caught,
    ):
        await flow(hass).async_oauth_create_entry(TOKEN)
    assert caught.value.reason == "already_configured"


@pytest.mark.parametrize(
    ("reply", "reason"), [(403, "missing_personal_permission"), (401, "oauth_unauthorized")]
)
async def test_identity_request_errors(hass, response, reply, reason):
    with patch(
        "custom_components.oura.config_flow.config_entry_oauth2_flow.async_oauth2_request",
        AsyncMock(return_value=response(reply)),
    ):
        result = await flow(hass).async_oauth_create_entry(TOKEN)
    assert result["reason"] == reason


async def test_reauth_updates_original_entry(hass, response):
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="account-1", data={**TOKEN, "keep": "original"}
    )
    entry.add_to_hass(hass)
    instance = flow(hass, entry)
    assert (await instance.async_step_reauth(entry.data))["step_id"] == "reauth_confirm"
    replacement = {**TOKEN, "token": {**TOKEN["token"], "access_token": "new-synthetic-token"}}
    with (
        patch(
            "custom_components.oura.config_flow.config_entry_oauth2_flow.async_oauth2_request",
            AsyncMock(return_value=response(body={"id": "account-1"})),
        ),
        patch.object(hass.config_entries, "async_reload", AsyncMock()) as reload,
    ):
        result = await instance.async_oauth_create_entry(replacement)
        await hass.async_block_till_done()
    assert result["reason"] == "reauth_successful"
    assert entry.data["token"]["access_token"] == "new-synthetic-token"
    assert entry.data["keep"] == "original"
    assert len(hass.config_entries.async_entries(DOMAIN)) == 1
    reload.assert_awaited_once_with(entry.entry_id)


async def test_reauth_wrong_account_is_rejected(hass, response):
    entry = MockConfigEntry(domain=DOMAIN, unique_id="account-1", data=TOKEN)
    entry.add_to_hass(hass)
    instance = flow(hass, entry)
    await instance.async_step_reauth(entry.data)
    with patch(
        "custom_components.oura.config_flow.config_entry_oauth2_flow.async_oauth2_request",
        AsyncMock(return_value=response(body={"id": "other-account"})),
    ):
        result = await instance.async_oauth_create_entry(TOKEN)
    assert result["reason"] == "wrong_account"
    assert entry.data == TOKEN


async def test_options_reject_short_polling(hass):
    entry = MockConfigEntry(domain=DOMAIN, data=TOKEN)
    entry.add_to_hass(hass)
    instance = OuraOptionsFlow()
    instance.hass = hass
    instance.handler = entry.entry_id
    result = await instance.async_step_init()
    import voluptuous as vol

    with pytest.raises(vol.Invalid):
        result["data_schema"]({"scan_interval": 0})
