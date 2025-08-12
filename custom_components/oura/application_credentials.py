from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.components.application_credentials import (
    AuthorizationServer,
    ClientCredential,
    AuthImplementation,
)
from homeassistant.helpers.config_entry_oauth2_flow import (
    AbstractOAuth2Implementation,
)

# Try PKCE impl if available (HA 2025.3+), else fall back to LocalOAuth2Implementation
try:
    from homeassistant.helpers.config_entry_oauth2_flow import LocalOAuth2ImplementationWithPkce as _LocalImpl
except Exception:  # older HA
    from homeassistant.helpers.config_entry_oauth2_flow import LocalOAuth2Implementation as _LocalImpl  # type: ignore

from .const import DOMAIN, OAUTH_AUTHORIZE_URL, OAUTH_TOKEN_URL

async def async_get_authorization_server(hass: HomeAssistant) -> AuthorizationServer:
    return AuthorizationServer(
        authorize_url=OAUTH_AUTHORIZE_URL,
        token_url=OAUTH_TOKEN_URL,
    )

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
