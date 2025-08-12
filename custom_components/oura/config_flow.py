
from __future__ import annotations

from typing import Any
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers import config_entry_oauth2_flow

from .const import DOMAIN, OAUTH_SCOPES


class OuraOAuth2FlowHandler(config_entry_oauth2_flow.AbstractOAuth2FlowHandler, domain=DOMAIN):
    """Config flow for Oura using OAuth2."""

    DOMAIN = DOMAIN
    VERSION = 1

    @property
    def extra_authorize_data(self) -> dict[str, Any]:
        # Request broad scopes. The user may toggle on Oura side.
        return {"scope": " ".join(OAUTH_SCOPES)}

    async def async_oauth_create_entry(self, data: dict) -> config_entries.ConfigEntry:
        # Create the entry; sensors will fetch profile and set names.
        return self.async_create_entry(title="Oura Ring", data=data)

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> config_entries.FlowResult:
        """Perform reauth when tokens are invalid."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None):
        if user_input is None:
            return self.async_show_form(step_id="reauth_confirm", data_schema=vol.Schema({}))
        return await self.async_step_user()
