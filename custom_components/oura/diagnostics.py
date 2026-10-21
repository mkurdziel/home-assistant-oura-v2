"""Diagnostics expose connection health, never tokens or biometric payloads."""

from .const import DOMAIN


async def async_get_config_entry_diagnostics(hass, entry):
    runtime = hass.data.get(DOMAIN, {}).get(entry.entry_id)
    if runtime is None:
        return {"loaded": False}
    coordinator = runtime["coordinator"]
    data = coordinator.data
    return {
        "loaded": True,
        "last_update_success": coordinator.last_update_success,
        "update_interval_seconds": coordinator.update_interval.total_seconds(),
        "collections": {
            key: {
                "available": key not in data.unavailable,
                "records": len(value.get("data", []))
                if isinstance(value, dict) and isinstance(value.get("data"), list)
                else None,
            }
            for key, value in data.payloads.items()
        }
        if data
        else {},
        "unavailable": dict(data.unavailable) if data else {},
        "webhooks_enabled": entry.options.get("use_webhooks", False),
        "webhook_error": runtime["webhooks"].last_error,
        "webhook_subscriptions": len(runtime["webhooks"].state.get("subscriptions", [])),
    }
