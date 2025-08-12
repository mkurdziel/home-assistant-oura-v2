
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers import config_entry_oauth2_flow

from .const import (
    DOMAIN,
    DEFAULT_POLL_INTERVAL_MIN,
    DEFAULT_ENABLE_LIVE_HR,
    DEFAULT_HR_POLL_INTERVAL_MIN,
    DEFAULT_HR_LOOKBACK_MIN,
)
from .ouraclient import OuraClient

_LOGGER = logging.getLogger(__name__)


class OuraCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator to fetch daily summaries and optional live HR."""

    def __init__(self, hass: HomeAssistant, entry, oauth_session: config_entry_oauth2_flow.OAuth2Session, bearer_token: str | None):
        super().__init__(
            hass,
            _LOGGER,
            name=f"OuraCoordinator:{entry.title}",
            update_interval=timedelta(minutes=DEFAULT_POLL_INTERVAL_MIN),
        )
        self.entry = entry
        self._client = OuraClient(hass, oauth_session, bearer_token=bearer_token)

        self.enable_live_hr = self.entry.options.get("enable_live_hr", DEFAULT_ENABLE_LIVE_HR)
        self.hr_lookback_min = self.entry.options.get("hr_lookback_min", DEFAULT_HR_LOOKBACK_MIN)
        self._last_hr_update = None
        self._latest_hr: int | None = None

    async def _async_update_data(self) -> dict[str, Any]:
        try:
            today = datetime.now(timezone.utc).date()
            start = datetime(today.year, today.month, today.day) - timedelta(days=1)
            end = datetime(today.year, today.month, today.day)

            # Fetch summaries (yesterday -> today)
            readiness = await self._client.async_get_daily_readiness(start, end)
            sleep = await self._client.async_get_daily_sleep(start, end)
            activity = await self._client.async_get_daily_activity(start, end)
            spo2 = await self._client.async_get_daily_spo2(start, end)
            # Optional: deeper sleep periods
            sleep_periods = await self._client.async_get_sleep_periods(start, end)

            data: dict[str, Any] = {
                "daily_readiness": readiness,
                "daily_sleep": sleep,
                "daily_activity": activity,
                "daily_spo2": spo2,
                "sleep": sleep_periods,
            }

            # Live HR (handled at most every DEFAULT_HR_POLL_INTERVAL_MIN minutes)
            if self.enable_live_hr:
                now = datetime.now(timezone.utc)
                need = (
                    self._last_hr_update is None
                    or (now - self._last_hr_update) >= timedelta(minutes=DEFAULT_HR_POLL_INTERVAL_MIN)
                )
                if need:
                    self._latest_hr = await self._client.async_get_heartrate_latest(self.hr_lookback_min)
                    self._last_hr_update = now
                data["latest_hr_bpm"] = self._latest_hr

            return data

        except ConfigEntryAuthFailed as err:
            raise
        except Exception as err:
            raise UpdateFailed(str(err)) from err
