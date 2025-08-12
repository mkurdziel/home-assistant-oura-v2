
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from aiohttp import ClientResponseError
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers import config_entry_oauth2_flow

from .const import API_BASE

_LOGGER = logging.getLogger(__name__)

ISO_DATE = "%Y-%m-%d"
ISO_DATETIME = "%Y-%m-%dT%H:%M:%SZ"


class OuraClient:
    """Thin async client around Home Assistant OAuth2Session for Oura API v2."""

    def __init__(self, hass, oauth_session: config_entry_oauth2_flow.OAuth2Session | None, bearer_token: str | None = None):
        self.hass = hass
        self._session = oauth_session
        self._bearer = bearer_token  # personal access token (optional)

    async def _request(self, method: str, url: str, **kwargs) -> Any:
        headers = kwargs.pop("headers", {})
        if self._bearer:
            headers["Authorization"] = f"Bearer {self._bearer}"
            from homeassistant.helpers.aiohttp_client import async_get_clientsession
            session = async_get_clientsession(self.hass)
            async with session.request(method, url, headers=headers, **kwargs) as resp:
                resp.raise_for_status()
                return await resp.json(content_type=None)
        else:
            try:
                return await self._session.async_request(method, url, headers=headers, **kwargs)
            except ClientResponseError as err:
                if err.status == 401:
                    raise ConfigEntryAuthFailed from err
                raise

    async def async_get_personal_info(self) -> dict[str, Any]:
        url = f"{API_BASE}/personal_info"
        data = await self._request("GET", url)
        # For convenience, flatten
        if isinstance(data, dict) and "data" in data and isinstance(data["data"], list):
            # personal_info returns a single record list
            if data["data"]:
                return data["data"][0]
        return data

    async def async_get_daily_readiness(self, start: datetime, end: datetime) -> dict:
        url = f"{API_BASE}/daily_readiness?start_date={start.strftime(ISO_DATE)}&end_date={end.strftime(ISO_DATE)}"
        return await self._request("GET", url)

    async def async_get_daily_sleep(self, start: datetime, end: datetime) -> dict:
        url = f"{API_BASE}/daily_sleep?start_date={start.strftime(ISO_DATE)}&end_date={end.strftime(ISO_DATE)}"
        return await self._request("GET", url)

    async def async_get_daily_activity(self, start: datetime, end: datetime) -> dict:
        url = f"{API_BASE}/daily_activity?start_date={start.strftime(ISO_DATE)}&end_date={end.strftime(ISO_DATE)}"
        return await self._request("GET", url)

    async def async_get_daily_spo2(self, start: datetime, end: datetime) -> dict:
        url = f"{API_BASE}/daily_spo2?start_date={start.strftime(ISO_DATE)}&end_date={end.strftime(ISO_DATE)}"
        return await self._request("GET", url)

    async def async_get_sleep_periods(self, start: datetime, end: datetime) -> dict:
        url = f"{API_BASE}/sleep?start_date={start.strftime(ISO_DATE)}&end_date={end.strftime(ISO_DATE)}"
        return await self._request("GET", url)

    async def async_get_heartrate_latest(self, lookback_minutes: int = 180) -> int | None:
        """Fetch recent heart rate points and return the most recent value (bpm)."""
        end_dt = datetime.now(timezone.utc)
        start_dt = end_dt - timedelta(minutes=lookback_minutes)
        url = f"{API_BASE}/heartrate?start_datetime={start_dt.strftime(ISO_DATETIME)}&end_datetime={end_dt.strftime(ISO_DATETIME)}"
        data = await self._request("GET", url)
        # Expect {"data": [{"bpm": 62, "timestamp": "..."} ...]}
        latest = None
        if isinstance(data, dict):
            entries = data.get("data") or []
            if entries:
                last = entries[-1]
                latest = last.get("bpm")
        return latest
