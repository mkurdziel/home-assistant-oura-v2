from homeassistant.components.application_credentials import ClientCredential
from yarl import URL

from custom_components.oura.application_credentials import (
    async_get_auth_implementation,
    async_get_authorization_server,
    async_get_description_placeholders,
)
from custom_components.oura.config_flow import OAuth2FlowHandler


async def test_authorization_has_scopes_and_preserves_pkce_when_available(hass):
    hass.config.components.add("my")
    implementation = await async_get_auth_implementation(
        hass, "test-app", ClientCredential("synthetic-client", "synthetic-secret")
    )
    flow = OAuth2FlowHandler()
    flow.hass = hass
    flow.flow_id = "test-flow"
    flow.flow_impl = implementation
    query = URL(await flow.async_generate_authorize_url()).query
    assert query["client_id"] == "synthetic-client"
    assert query["redirect_uri"] == "https://my.home-assistant.io/redirect/oauth"
    assert set(query["scope"].split()) >= {"personal", "daily", "heart_health"}
    assert query["state"]
    if hasattr(implementation, "code_verifier"):
        assert query["code_challenge_method"] == "S256"
        assert query["code_challenge"]
    assert implementation.client_secret == "synthetic-secret"
    server = await async_get_authorization_server(hass)
    assert server.token_url == "https://api.ouraring.com/oauth/token"
    assert (await async_get_description_placeholders(hass))["oauth_redirect_url"].startswith(
        "https://"
    )
