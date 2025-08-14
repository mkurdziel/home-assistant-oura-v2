
from __future__ import annotations

from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.const import Platform, CONF_SCAN_INTERVAL
from homeassistant.helpers import config_entry_oauth2_flow

from .const import DOMAIN, CONF_USE_SANDBOX, DEFAULT_UPDATE_INTERVAL_MIN
from .coordinator import OuraDataUpdateCoordinator
from .api import OuraApiClient

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BUTTON]
_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    implementation = await config_entry_oauth2_flow.async_get_config_entry_implementation(hass, entry)
    session = config_entry_oauth2_flow.OAuth2Session(hass, entry, implementation)
    use_sandbox = entry.options.get(CONF_USE_SANDBOX, False)
    client = OuraApiClient(session, use_sandbox=use_sandbox)

    scan_interval_sec = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_UPDATE_INTERVAL_MIN * 60)
    coordinator = OuraDataUpdateCoordinator(
        hass,
        client=client,
        update_interval=timedelta(seconds=scan_interval_sec),
        title=f"oura_{entry.entry_id}",
        entry_id=entry.entry_id,
    )
    await coordinator.async_config_entry_first_refresh()

    pi = (coordinator.data.payloads.get("personal_info", {}) if coordinator.data else {}) or {}
    user = pi.get("id") or pi.get("email") or entry.unique_id or entry.entry_id
    device_info = {
        "identifiers": {(DOMAIN, str(user))},
        "manufacturer": "Oura",
        "name": "Oura V2",
        "configuration_url": "https://cloud.ouraring.com/",
    }

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {
        "coordinator": coordinator,
        "client": client,
        "device_info": device_info,
        "uid_prefix": f"{entry.entry_id}",
    }

    # Register refresh service once
    if not hass.data[DOMAIN].get("_service_registered"):
        async def _handle_request_refresh(call: ServiceCall):
            entry_id = call.data.get("entry_id")
            targets = []
            if entry_id:
                data = hass.data.get(DOMAIN, {}).get(entry_id)
                if data:
                    targets.append(data["coordinator"])
            else:
                for k, v in hass.data.get(DOMAIN, {}).items():
                    if k.startswith("_"):
                        continue
                    targets.append(v["coordinator"])
            for coord in targets:
                await coord.async_request_refresh()

        hass.services.async_register(DOMAIN, "request_refresh", _handle_request_refresh)
        hass.data[DOMAIN]["_service_registered"] = True

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok and entry.entry_id in hass.data.get(DOMAIN, {}):
        hass.data[DOMAIN].pop(entry.entry_id)
    return unload_ok
