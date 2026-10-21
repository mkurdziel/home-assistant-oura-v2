"""Coordinate Oura collections while preserving endpoint failure information."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    COLLECTION_PATHS,
    OuraApiClient,
    OuraApiError,
    OuraAuthError,
    OuraPermissionError,
    OuraRateLimitError,
)

_LOGGER = logging.getLogger(__name__)
SCOPES = {
    "heartrate": "heartrate",
    "workout": "workout",
    "session": "session",
    "tag": "tag",
    "enhanced_tag": "tag",
    "daily_spo2": "spo2",
}
DAILY = {key for key in COLLECTION_PATHS if key.startswith("daily_")} | {"sleep", "sleep_time"}


@dataclass
class OuraData:
    """Latest payloads and their availability; successful empty lists are valid."""

    payloads: dict[str, Any]
    unavailable: dict[str, str] = field(default_factory=dict)
    today: str = field(default_factory=lambda: dt_util.now().date().isoformat())
    updated_at: datetime | None = None


class OuraDataUpdateCoordinator(DataUpdateCoordinator[OuraData]):
    def __init__(
        self,
        hass: HomeAssistant,
        client: OuraApiClient,
        update_interval: timedelta,
        title: str,
        entry_id: str,
        *,
        scopes: set[str] | None = None,
    ) -> None:
        super().__init__(hass, _LOGGER, name=title, update_interval=update_interval)
        self.client = client
        self.entry_id = entry_id
        self.scopes = scopes
        self._refresh_lock = asyncio.Lock()

    async def _async_update_data(self) -> OuraData:
        async with self._refresh_lock:
            return await self._async_fetch_data()

    async def _async_fetch_data(self) -> OuraData:
        now = dt_util.now()
        today = now.date().isoformat()
        payloads = dict(self.data.payloads) if self.data else {}
        unavailable: dict[str, str] = {}
        success: set[str] = set()
        try:
            await self.client.async_ensure_token_valid()
        except OuraAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except OuraApiError as err:
            raise UpdateFailed(str(err)) from err

        async def fetch(key: str) -> None:
            scope = SCOPES.get(key)
            if self.scopes is not None and scope is not None and scope not in self.scopes:
                unavailable[key] = "permissions"
                return
            if (
                self.scopes is not None
                and key in DAILY
                and not self.scopes.intersection({"daily", "heart_health"})
            ):
                unavailable[key] = "permissions"
                return
            params: dict[str, Any] = {}
            if key in {"heartrate", "ring_battery_level"}:
                params = {
                    "start_datetime": (now - timedelta(hours=30)).isoformat(),
                    "end_datetime": now.isoformat(),
                }
                if key == "ring_battery_level":
                    params["latest"] = "true"
            elif key not in {"personal_info", "ring_configuration"}:
                days = 7 if key in DAILY else 90
                start = (
                    "2000-01-01"
                    if key == "rest_mode_period"
                    else (now.date() - timedelta(days=days)).isoformat()
                )
                params = {"start_date": start, "end_date": today}
            try:
                payloads[key] = await self.client.async_get_collection(key, **params)
                success.add(key)
            except OuraAuthError as err:
                raise ConfigEntryAuthFailed(str(err)) from err
            except OuraPermissionError as err:
                unavailable[key] = err.reason
                payloads.pop(key, None)
            except OuraRateLimitError:
                unavailable[key] = "rate_limited"
            except OuraApiError as err:
                unavailable[key] = "unsupported" if err.status == 404 else "connection"
                _LOGGER.debug("Oura collection %s unavailable: %s", key, err)

        # Await every task even when authentication fails: no requests escape teardown.
        results = await asyncio.gather(
            *(fetch(key) for key in COLLECTION_PATHS), return_exceptions=True
        )
        for result in results:
            if isinstance(result, BaseException):
                raise result
        if not success.difference({"personal_info", "ring_configuration"}):
            reasons = ", ".join(sorted(set(unavailable.values()))) or "no collections available"
            raise UpdateFailed(f"Oura data unavailable ({reasons})")
        return OuraData(payloads, unavailable, today, dt_util.utcnow())

    async def async_process_event(self, collection: str, document_id: str, event: str) -> None:
        """Merge one webhook document without refetching unrelated collections."""
        needs_refresh = False
        async with self._refresh_lock:
            if self.data is None:
                return
            try:
                document = (
                    None
                    if event == "delete"
                    else await self.client.async_get_document(collection, document_id)
                )
            except OuraApiError:
                needs_refresh = True
            else:
                payloads = dict(self.data.payloads)
                items = list(payloads.get(collection, {}).get("data", []))
                items = [item for item in items if item.get("id") != document_id]
                if document is not None:
                    if document.get("id") != document_id:
                        return
                    items.append(document)
                payloads[collection] = {"data": items, "next_token": None}
                unavailable = dict(self.data.unavailable)
                if not self.last_update_success:
                    for key in payloads:
                        unavailable.setdefault(key, "connection")
                unavailable.pop(collection, None)
                self.async_set_updated_data(
                    OuraData(
                        payloads, unavailable, dt_util.now().date().isoformat(), dt_util.utcnow()
                    )
                )
        # Refresh uses the same lock; request it only after releasing that lock.
        if needs_refresh:
            await self.async_request_refresh()
