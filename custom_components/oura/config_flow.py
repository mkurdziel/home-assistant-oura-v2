
from __future__ import annotations

import logging
from typing import Any

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import config_entry_oauth2_flow

from .const import DOMAIN as OURA_DOMAIN, OAUTH_SCOPES_DEFAULT

_LOGGER = logging.getLogger(__name__)

class OAuth2FlowHandler(config_entry_oauth2_flow.AbstractOAuth2FlowHandler, domain=OURA_DOMAIN):
    """Config flow to handle Oura OAuth2."""

    DOMAIN = OURA_DOMAIN
    SCOPES = OAUTH_SCOPES_DEFAULT

    VERSION = 1
    MINOR_VERSION = 1
    reauth_entry = None

    @property
    def logger(self) -> logging.Logger:
        return _LOGGER

    async def async_oauth_create_entry(self, data: dict[str, Any]) -> config_entries.ConfigEntry:
        implementation = await config_entry_oauth2_flow.async_get_config_entry_implementation(self.hass, data)
        session = config_entry_oauth2_flow.OAuth2Session(self.hass, data, implementation)

        title = "Oura Account"
        unique_id: str | None = None
        try:
            resp = await session.async_request("get", "https://api.ouraring.com/v2/usercollection/personal_info")
            js = await resp.json()
            email = js.get("email")
            uid = js.get("id") or email
            if email:
                title = f"Oura: {email}"
            if uid:
                unique_id = str(uid).lower()
        except Exception:
            pass

        if unique_id:
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

        return self.async_create_entry(title=title, data=data)

    async def async_step_reauth(self, user_input: dict[str, Any] | None = None):
        self.reauth_entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        return await super().async_step_reauth(user_input)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        return OuraOptionsFlow(config_entry)


class OuraOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, entry: config_entries.ConfigEntry) -> None:
        self._entry = entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None):
        import voluptuous as vol
        from homeassistant.const import CONF_SCAN_INTERVAL

        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        options = self._entry.options
        schema = vol.Schema({
            vol.Optional(CONF_SCAN_INTERVAL, default=options.get(CONF_SCAN_INTERVAL, 1800)): int,
        })
        return self.async_show_form(step_id="init", data_schema=schema)


class OuraOAuth2FlowHandler(OAuth2FlowHandler):
    """Backward compatibility alias for some HA cores."""
    pass
