"""Oura Cloud v2 integration setup and lifecycle."""

from __future__ import annotations

import logging
from datetime import timedelta

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_SCAN_INTERVAL, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryError, ServiceValidationError
from homeassistant.helpers import config_entry_oauth2_flow, device_registry
from homeassistant.helpers import config_validation as cv

from .api import OuraApiClient, OuraApiError
from .config_flow import OPTIONS_AUTO_RELOAD
from .const import CONF_USE_SANDBOX, CONF_USE_WEBHOOKS, DEFAULT_UPDATE_INTERVAL_MIN, DOMAIN
from .coordinator import OuraDataUpdateCoordinator
from .data import latest_ring
from .webhooks import WEBHOOK_STATE, OuraWebhooks

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS = [Platform.SENSOR, Platform.BUTTON, Platform.BINARY_SENSOR]
_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config) -> bool:
    """Register actions independently of an account's connection state."""

    async def refresh(call: ServiceCall):
        entry_id = call.data.get("entry_id")
        entries = hass.data.get(DOMAIN, {})
        if entry_id is not None and entry_id not in entries:
            raise ServiceValidationError("The requested Oura config entry is not loaded")
        targets = [entries[entry_id]] if entry_id is not None else list(entries.values())
        for runtime in targets:
            await runtime["coordinator"].async_request_refresh()

    hass.services.async_register(
        DOMAIN, "request_refresh", refresh, schema=vol.Schema({vol.Optional("entry_id"): str})
    )
    return True


def _token_scopes(token):
    scopes = token.get("scope")
    if isinstance(scopes, str):
        scopes = scopes.split()
    if isinstance(scopes, list):
        # Oura token responses namespace grants; authorization requests do not.
        return {scope.removeprefix("extapi:") for scope in scopes}
    return None  # Older tokens may not report grants; let the API decide.


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    implementation = await config_entry_oauth2_flow.async_get_config_entry_implementation(
        hass, entry
    )
    session = config_entry_oauth2_flow.OAuth2Session(hass, entry, implementation)
    client = OuraApiClient(session, use_sandbox=entry.options.get(CONF_USE_SANDBOX, False))
    interval = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_UPDATE_INTERVAL_MIN * 60)
    if not isinstance(interval, int) or not 300 <= interval <= 86400:
        interval = DEFAULT_UPDATE_INTERVAL_MIN * 60
    coordinator = OuraDataUpdateCoordinator(
        hass,
        client=client,
        update_interval=timedelta(seconds=interval),
        title=f"oura_{entry.entry_id}",
        entry_id=entry.entry_id,
        scopes=_token_scopes(session.token),
    )
    await coordinator.async_config_entry_first_refresh()
    personal = coordinator.data.payloads.get("personal_info", {})
    user = personal.get("id") or entry.data.get("user_id") or entry.unique_id
    if not user:
        raise ConfigEntryError(
            "Oura account identity is unavailable; allow personal information access"
        )
    user = str(user).lower()
    if entry.unique_id and entry.unique_id != user:
        raise ConfigEntryError("The Oura account does not match this integration entry")
    if any(
        other.entry_id != entry.entry_id and other.unique_id == user
        for other in hass.config_entries.async_entries(DOMAIN)
    ):
        raise ConfigEntryError("This Oura account is already configured")
    # Adopt legacy entries without changing entry IDs or entity unique IDs.
    if entry.unique_id is None or entry.data.get("user_id") != user:
        hass.config_entries.async_update_entry(
            entry, unique_id=user, data={**entry.data, "user_id": user}
        )

    device_info = {
        "identifiers": {(DOMAIN, user)},
        "manufacturer": "Oura",
        "name": "Oura V2",
        "configuration_url": "https://cloud.ouraring.com/",
    }
    ring = latest_ring(coordinator.data)
    if ring.get("hardware_type"):
        device_info["model"] = ring["hardware_type"]
    if ring.get("firmware_version"):
        device_info["sw_version"] = ring["firmware_version"]
    manager = OuraWebhooks(hass, entry, coordinator, implementation)
    if entry.options.get(CONF_USE_WEBHOOKS, False):
        if entry.options.get(CONF_USE_SANDBOX, False):
            raise ConfigEntryError("Webhooks cannot be enabled in sandbox mode")
        await manager.async_start()
    elif manager.state.get("subscriptions") or manager.state.get("callback_url"):
        try:
            await manager.async_cleanup()
        except OuraApiError:
            _LOGGER.warning(
                "Oura webhook cleanup failed; it will be retried when the entry is loaded"
            )

    runtime = {
        "coordinator": coordinator,
        "client": client,
        "webhooks": manager,
        "device_info": device_info,
        "uid_prefix": entry.entry_id,
        "options": dict(entry.options),
    }
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = runtime

    def update_device():
        registry = device_registry.async_get(hass)
        device = next(
            (
                device
                for device in device_registry.async_entries_for_config_entry(
                    registry, entry.entry_id
                )
                if device_info["identifiers"].intersection(device.identifiers)
            ),
            None,
        )
        if device is None or not coordinator.data:
            return
        latest = latest_ring(coordinator.data)
        changes = {
            target: latest[source]
            for target, source in (("model", "hardware_type"), ("sw_version", "firmware_version"))
            if latest.get(source)
        }
        if changes:
            registry.async_update_device(device.id, **changes)

    entry.async_on_unload(coordinator.async_add_listener(update_device))
    if not OPTIONS_AUTO_RELOAD:
        # Home Assistant 2024.9 has no OptionsFlowWithReload.
        entry.async_on_unload(entry.add_update_listener(_async_update_options))
    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except BaseException:
        manager.async_stop()
        hass.data[DOMAIN].pop(entry.entry_id, None)
        raise
    return True


async def _async_update_options(hass, entry):
    runtime = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if runtime and runtime["options"] != dict(entry.options):
        await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    runtime = hass.data.get(DOMAIN, {}).pop(entry.entry_id, None)
    if runtime:
        runtime["webhooks"].async_stop()
    return True


async def async_remove_entry(hass, entry):
    """Remove only this account's subscriptions when the user removes the entry."""
    state = entry.data.get(WEBHOOK_STATE, {})
    if not state.get("subscriptions") and not state.get("callback_url"):
        return
    implementation = await config_entry_oauth2_flow.async_get_config_entry_implementation(
        hass, entry
    )
    try:
        await OuraWebhooks(hass, entry, None, implementation).async_cleanup()
    except OuraApiError:
        _LOGGER.warning(
            "Could not remove Oura webhook subscriptions; they will expire automatically"
        )
