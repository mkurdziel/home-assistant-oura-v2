"""Rest mode and ring charging state."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.const import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .data import latest_battery, rest_mode


async def async_setup_entry(hass, entry, async_add_entities):
    runtime = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [OuraBinarySensor(runtime, key) for key in ("rest_mode", "charging", "in_charger")]
    )


class OuraBinarySensor(CoordinatorEntity, BinarySensorEntity):
    def __init__(self, runtime, key):
        super().__init__(runtime["coordinator"])
        self.key = key
        self.collection = "rest_mode_period" if key == "rest_mode" else "ring_battery_level"
        self._attr_unique_id = f"{runtime['uid_prefix']}_{key}"
        self._attr_device_info = runtime["device_info"]
        self._attr_name = f"Oura V2 {key.replace('_', ' ').title()}"
        if key == "charging":
            self._attr_device_class = BinarySensorDeviceClass.BATTERY_CHARGING
        if key != "rest_mode":
            self._attr_entity_category = EntityCategory.DIAGNOSTIC

    @property
    def available(self):
        data = self.coordinator.data
        return (
            super().available
            and data is not None
            and self.collection in data.payloads
            and self.collection not in data.unavailable
            and self.is_on is not None
        )

    @property
    def is_on(self):
        if self.coordinator.data is None:
            return None
        return (
            rest_mode(self.coordinator.data)
            if self.key == "rest_mode"
            else latest_battery(self.coordinator.data).get(self.key)
        )
