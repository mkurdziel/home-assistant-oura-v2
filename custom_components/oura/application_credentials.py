
from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.components.application_credentials import (
    AuthorizationServer,
    ClientCredential,
    AuthImplementation,
)
from homeassistant.helpers.config_entry_oauth2_flow import (
    AbstractOAuth2Implementation,
    LocalOAuth2ImplementationWithPkce,
)

from .const import DOMAIN, OAUTH_AUTHORIZE_URL, OAUTH_TOKEN_URL

async def async_get_authorization_server(hass: HomeAssistant) -> AuthorizationServer:
    return AuthorizationServer(authorize_url=OAUTH_AUTHORIZE_URL, token_url=OAUTH_TOKEN_URL)

async def async_get_auth_implementation(
    hass: HomeAssistant, auth_domain: str, credential: ClientCredential
) -> AbstractOAuth2Implementation | AuthImplementation:
    return _LocalImpl(
        hass,
        auth_domain,
        credential.client_id,
        authorize_url=OAUTH_AUTHORIZE_URL,
        token_url=OAUTH_TOKEN_URL,
        client_secret=credential.client_secret or "",
    )


async def async_get_description_placeholders(hass):
    """Return description placeholders for the credentials dialog."""
    # Oura developer console for creating OAuth apps
    return {
        "console_url": "https://cloud.ouraring.com",
    }
