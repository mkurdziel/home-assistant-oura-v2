
from __future__ import annotations
from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.const import Platform, CONF_SCAN_INTERVAL
from homeassistant.helpers import config_entry_oauth2_flow

from .const import DOMAIN, DEFAULT_UPDATE_INTERVAL_MIN
from .coordinator import OuraDataUpdateCoordinator
from .api import OuraApiClient

PLATFORMS: list[Platform] = [Platform.SENSOR]
_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    implementation = await config_entry_oauth2_flow.async_get_config_entry_implementation(hass, entry.data)
    session = config_entry_oauth2_flow.OAuth2Session(hass, entry.data, implementation)

    client = OuraApiClient(session, use_sandbox=entry.options.get("use_sandbox", False))
    scan_interval_sec = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_UPDATE_INTERVAL_MIN * 60)
    coordinator = OuraDataUpdateCoordinator(hass, client=client, update_interval=timedelta(seconds=scan_interval_sec), title=f"Oura {entry.title}")
    await coordinator.async_config_entry_first_refresh()

    pi = coordinator.data.payloads.get("personal_info", {}) if coordinator.data else {}
    user = pi.get("id") or pi.get("email") or entry.unique_id or entry.title

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": coordinator,
        "client": client,
        "device_info": {
            "identifiers": {(DOMAIN, str(user))},
            "manufacturer": "Oura",
            "name": entry.title or "Oura Account",
            "configuration_url": "https://cloud.ouraring.com/",
        },
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok and entry.entry_id in hass.data.get(DOMAIN, {}):
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
