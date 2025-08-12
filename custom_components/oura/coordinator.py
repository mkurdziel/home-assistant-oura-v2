
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .api import OuraApiClient, OuraApiError

_LOGGER = logging.getLogger(__name__)

@dataclass
class OuraData:
    payloads: Dict[str, Any]

def _today_dates():
    now = datetime.now(timezone.utc).astimezone()
    today = now.date()
    yesterday = today - timedelta(days=1)
    return yesterday.isoformat(), today.isoformat(), now

class OuraDataUpdateCoordinator(DataUpdateCoordinator[OuraData]):
    def __init__(
        self,
        hass: HomeAssistant,
        client: OuraApiClient,
        update_interval: timedelta,
        title: str,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=title,
            update_interval=update_interval,
        )
        self._client = client

    async def _async_update_data(self) -> OuraData:
        start_date, end_date, now = _today_dates()
        start_dt = f"{start_date}T00:00:00{now.strftime('%z')}"
        end_dt = now.isoformat(timespec="seconds")

        async def _fetch_safely(coro, key: str) -> Optional[Dict[str, Any]]:
            try:
                return await coro
            except OuraApiError as err:
                _LOGGER.debug("Endpoint %s unavailable: %s", key, err)
                return None
            except Exception as err:
                _LOGGER.warning("Unexpected error fetching %s: %s", key, err)
                return None

        results = await asyncio.gather(
            _fetch_safely(self._client.personal_info(), "personal_info"),
            _fetch_safely(self._client.ring_configuration(), "ring_configuration"),
            _fetch_safely(self._client.rest_mode_period(start_date, end_date), "rest_mode_period"),
            _fetch_safely(self._client.daily_readiness(start_date, end_date), "daily_readiness"),
            _fetch_safely(self._client.daily_sleep(start_date, end_date), "daily_sleep"),
            _fetch_safely(self._client.daily_activity(start_date, end_date), "daily_activity"),
            _fetch_safely(self._client.daily_spo2(start_date, end_date), "daily_spo2"),
            _fetch_safely(self._client.daily_stress(start_date, end_date), "daily_stress"),
            _fetch_safely(self._client.daily_resilience(start_date, end_date), "daily_resilience"),
            _fetch_safely(self._client.heartrate(start_dt, end_dt), "heartrate"),
            _fetch_safely(self._client.workout(start_date, end_date), "workout"),
            _fetch_safely(self._client.session(start_date, end_date), "session"),
            _fetch_safely(self._client.sleep(start_date, end_date), "sleep"),
            _fetch_safely(self._client.enhanced_tag(start_date, end_date), "enhanced_tag"),
        )
        keys = [
            "personal_info","ring_configuration","rest_mode_period",
            "daily_readiness","daily_sleep","daily_activity","daily_spo2",
            "daily_stress","daily_resilience","heartrate","workout","session",
            "sleep","enhanced_tag",
        ]
        payloads = {k: v for k, v in zip(keys, results) if v is not None}
        return OuraData(payloads=payloads)
