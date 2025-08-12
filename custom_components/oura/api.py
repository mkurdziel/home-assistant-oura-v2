
from __future__ import annotations
from typing import Any, Dict, Optional

from homeassistant.helpers.config_entry_oauth2_flow import OAuth2Session

from .const import API_BASE, SANDBOX_API_BASE

class OuraApiError(Exception):
    pass

class OuraApiClient:
    def __init__(self, session: OAuth2Session, *, use_sandbox: bool = False) -> None:
        self._session = session
        self._api_base = SANDBOX_API_BASE if use_sandbox else API_BASE

    async def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        url = f"{self._api_base}{path}"
        resp = await self._session.async_request("get", url, params=params)
        if resp.status >= 400:
            text = await resp.text()
            raise OuraApiError(f"GET {url} -> {resp.status}: {text}")
        return await resp.json()

    async def personal_info(self) -> Dict[str, Any]:
        return await self._get("/usercollection/personal_info")

    async def ring_configuration(self) -> Dict[str, Any]:
        return await self._get("/usercollection/ring_configuration")

    async def rest_mode_period(self, start_date: str, end_date: str) -> Dict[str, Any]:
        return await self._get("/usercollection/rest_mode_period", {"start_date": start_date, "end_date": end_date})

    async def daily_readiness(self, start_date: str, end_date: str) -> Dict[str, Any]:
        return await self._get("/usercollection/daily_readiness", {"start_date": start_date, "end_date": end_date})

    async def daily_sleep(self, start_date: str, end_date: str) -> Dict[str, Any]:
        return await self._get("/usercollection/daily_sleep", {"start_date": start_date, "end_date": end_date})

    async def daily_activity(self, start_date: str, end_date: str) -> Dict[str, Any]:
        return await self._get("/usercollection/daily_activity", {"start_date": start_date, "end_date": end_date})

    async def daily_spo2(self, start_date: str, end_date: str) -> Dict[str, Any]:
        return await self._get("/usercollection/daily_spo2", {"start_date": start_date, "end_date": end_date})

    async def daily_stress(self, start_date: str, end_date: str) -> Dict[str, Any]:
        return await self._get("/usercollection/daily_stress", {"start_date": start_date, "end_date": end_date})

    async def daily_resilience(self, start_date: str, end_date: str) -> Dict[str, Any]:
        return await self._get("/usercollection/daily_resilience", {"start_date": start_date, "end_date": end_date})

    async def heartrate(self, start_datetime: str, end_datetime: str) -> Dict[str, Any]:
        return await self._get("/usercollection/heartrate", {"start_datetime": start_datetime, "end_datetime": end_datetime})

    async def workout(self, start_date: str, end_date: str) -> Dict[str, Any]:
        return await self._get("/usercollection/workout", {"start_date": start_date, "end_date": end_date})

    async def session(self, start_date: str, end_date: str) -> Dict[str, Any]:
        return await self._get("/usercollection/session", {"start_date": start_date, "end_date": end_date})

    async def sleep(self, start_date: str, end_date: str) -> Dict[str, Any]:
        return await self._get("/usercollection/sleep", {"start_date": start_date, "end_date": end_date})

    async def enhanced_tag(self, start_date: str, end_date: str) -> Dict[str, Any]:
        return await self._get("/usercollection/enhanced_tag", {"start_date": start_date, "end_date": end_date})

    async def vo2max(self, start_date: str, end_date: str) -> Dict[str, Any]:
        return await self._get("/usercollection/vo2max", {"start_date": start_date, "end_date": end_date})

    async def daily_cardiovascular_age(self, start_date: str, end_date: str) -> Dict[str, Any]:
        return await self._get("/usercollection/daily_cardiovascular_age", {"start_date": start_date, "end_date": end_date})
