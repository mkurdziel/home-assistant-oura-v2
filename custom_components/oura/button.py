
from __future__ import annotations

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import OuraDataUpdateCoordinator, OuraData

BUTTON_DESCRIPTION = ButtonEntityDescription(
    key="refresh_now",
    name="Oura V2 Refresh Now",
    icon="mdi:refresh",
)

async def async_setup_entry(hass, entry, async_add_entities):
    coordinator: OuraDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    device_info = hass.data[DOMAIN][entry.entry_id]["device_info"]
    uid_prefix = hass.data[DOMAIN][entry.entry_id]["uid_prefix"]
    async_add_entities([OuraRefreshButton(coordinator, device_info, uid_prefix)])

class OuraRefreshButton(CoordinatorEntity[OuraData], ButtonEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator: OuraDataUpdateCoordinator, device_info: dict, uid_prefix: str):
        super().__init__(coordinator)
        self.entity_description = BUTTON_DESCRIPTION
        self._attr_unique_id = f"{uid_prefix}_refresh_now"
        self._attr_device_info = device_info

    async def async_press(self) -> None:
        await self.coordinator.async_request_refresh()
