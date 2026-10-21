"""Oura authorization, identity verification, and options."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol
from aiohttp import ClientError
from homeassistant import config_entries
from homeassistant.const import CONF_SCAN_INTERVAL
from homeassistant.core import callback
from homeassistant.helpers import config_entry_oauth2_flow, device_registry

from .const import (
    API_BASE,
    CONF_USE_WEBHOOKS,
    DEFAULT_UPDATE_INTERVAL_MIN,
    DOMAIN,
    OAUTH_SCOPES_DEFAULT,
)

_LOGGER = logging.getLogger(__name__)
OPTIONS_AUTO_RELOAD = hasattr(config_entries, "OptionsFlowWithReload")
OptionsBase = getattr(config_entries, "OptionsFlowWithReload", config_entries.OptionsFlow)


class OAuth2FlowHandler(config_entry_oauth2_flow.AbstractOAuth2FlowHandler, domain=DOMAIN):
    """Authorize before entry creation; reauthentication preserves existing entities."""

    DOMAIN = DOMAIN
    VERSION = 1
    MINOR_VERSION = 1
    _reauth_user_id: str | None = None

    @property
    def logger(self) -> logging.Logger:
        return _LOGGER

    @property
    def extra_authorize_data(self) -> dict[str, str]:
        return {"scope": " ".join(OAUTH_SCOPES_DEFAULT)}

    async def async_oauth_create_entry(self, data: dict[str, Any]):
        response = None
        try:
            async with asyncio.timeout(30):
                # OAuth2Session requires a stored ConfigEntry. During this step we
                # only have the newly issued token, so use the token request helper.
                response = await config_entry_oauth2_flow.async_oauth2_request(
                    self.hass,
                    data["token"],
                    "get",
                    f"{API_BASE}/usercollection/personal_info",
                )
                if response.status == 403:
                    return self.async_abort(reason="missing_personal_permission")
                if response.status == 401:
                    return self.async_abort(reason="oauth_unauthorized")
                response.raise_for_status()
                personal = await response.json()
                user_id = personal.get("id") if isinstance(personal, dict) else None
                if not isinstance(user_id, str) or not user_id:
                    return self.async_abort(reason="cannot_identify_account")
        except (ClientError, TimeoutError, ValueError):
            return self.async_abort(reason="cannot_connect")
        finally:
            if response is not None:
                response.release()
        user_id = user_id.lower()
        data = {**data, "user_id": user_id}
        if self.source == config_entries.SOURCE_REAUTH:
            entry = self._reauth_config_entry()
            if user_id != self._reauth_user_id:
                return self.async_abort(reason="wrong_account")
            return self.async_update_reload_and_abort(
                entry, unique_id=user_id, data={**entry.data, **data}
            )
        await self.async_set_unique_id(user_id)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title="Oura V2", data=data)

    def _reauth_config_entry(self):
        # This lookup also works on HA 2024.9, before _get_reauth_entry existed.
        return self.hass.config_entries.async_get_entry(self.context["entry_id"])

    async def async_step_reauth(self, entry_data: dict[str, Any]):
        entry = self._reauth_config_entry()
        self._reauth_user_id = entry.unique_id or entry.data.get("user_id")
        if self._reauth_user_id is None:
            # Legacy entries did not store identity, but their account device did.
            registry = device_registry.async_get(self.hass)
            for device in device_registry.async_entries_for_config_entry(registry, entry.entry_id):
                for domain, identifier in device.identifiers:
                    if domain == DOMAIN and identifier != entry.entry_id:
                        self._reauth_user_id = identifier.lower()
                        break
        if self._reauth_user_id is None:
            return self.async_abort(reason="reauth_identity_unknown")
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        if user_input is None:
            return self.async_show_form(step_id="reauth_confirm", data_schema=vol.Schema({}))
        self.flow_impl = await config_entry_oauth2_flow.async_get_config_entry_implementation(
            self.hass, self._reauth_config_entry()
        )
        return await self.async_step_auth()

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OuraOptionsFlow()


class OuraOptionsFlow(OptionsBase):
    """Keep options validation identical in the UI and setup."""

    @property
    def _entry(self):
        return self.hass.config_entries.async_get_entry(self.handler)

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data={**self._entry.options, **user_input})
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_SCAN_INTERVAL,
                        default=self._entry.options.get(
                            CONF_SCAN_INTERVAL, DEFAULT_UPDATE_INTERVAL_MIN * 60
                        ),
                    ): vol.All(vol.Coerce(int), vol.Range(min=300, max=86400)),
                    vol.Optional(
                        CONF_USE_WEBHOOKS,
                        default=self._entry.options.get(CONF_USE_WEBHOOKS, False),
                    ): bool,
                }
            ),
        )
