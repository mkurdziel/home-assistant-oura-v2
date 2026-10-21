"""Bounded, paginated access to the Oura Cloud API."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any

from aiohttp import ClientError, ClientResponseError

from .const import API_BASE, SANDBOX_API_BASE

COLLECTION_PATHS = {
    name: name
    for name in (
        "personal_info",
        "ring_configuration",
        "rest_mode_period",
        "daily_readiness",
        "daily_sleep",
        "daily_activity",
        "daily_spo2",
        "daily_stress",
        "daily_resilience",
        "heartrate",
        "workout",
        "session",
        "sleep",
        "enhanced_tag",
        "daily_cardiovascular_age",
        "sleep_time",
        "tag",
        "ring_battery_level",
    )
}
COLLECTION_PATHS["vo2max"] = "vO2_max"
REQUEST_TIMEOUT = 30
MAX_PAGES = 100


class OuraApiError(Exception):
    """An API failure, containing no response bodies or credentials."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class OuraAuthError(OuraApiError):
    """The OAuth credentials are no longer usable."""


class OuraPermissionError(OuraApiError):
    """Consent or membership prevents access, rather than an invalid token."""

    def __init__(self, reason: str) -> None:
        super().__init__(f"Oura access denied ({reason})", status=403)
        self.reason = reason


class OuraRateLimitError(OuraApiError):
    """Requests must pause until Oura's retry deadline."""

    def __init__(self, retry_after: float) -> None:
        super().__init__("Oura rate limit exceeded", status=429)
        self.retry_after = retry_after


def retry_seconds(headers: Any) -> float:
    """Interpret Retry-After without trusting an unbounded delay."""
    value = headers.get("Retry-After", "60")
    try:
        seconds = float(value)
    except (ValueError, TypeError):
        try:
            seconds = (parsedate_to_datetime(value) - datetime.now(timezone.utc)).total_seconds()
        except (ValueError, TypeError, OverflowError):
            seconds = 60
    return max(1, min(seconds, 86400))


class OuraApiClient:
    """Use Home Assistant's shared OAuth session and token refresh lock."""

    def __init__(self, session: Any, *, use_sandbox: bool = False) -> None:
        self._session = session
        self._api_base = SANDBOX_API_BASE if use_sandbox else API_BASE
        self._retry_at = 0.0

    async def async_ensure_token_valid(self) -> None:
        """Validate once before fan-out, so revoked refresh tokens aren't retried."""
        try:
            async with asyncio.timeout(REQUEST_TIMEOUT):
                await self._session.async_ensure_token_valid()
        except ClientResponseError as err:
            if err.status in (400, 401, 403):
                raise OuraAuthError("Oura token refresh requires reauthentication") from err
            if err.status == 429:
                delay = retry_seconds(err.headers or {})
                self._retry_at = asyncio.get_running_loop().time() + delay
                raise OuraRateLimitError(delay) from err
            raise OuraApiError("Oura token refresh failed", status=err.status) from err
        except (ClientError, TimeoutError) as err:
            raise OuraApiError("Cannot connect to Oura to refresh credentials") from err

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Fetch one page, with one bounded retry for transient failures."""
        for attempt in range(2):
            remaining = self._retry_at - asyncio.get_running_loop().time()
            if remaining > 0:
                raise OuraRateLimitError(remaining)
            response = None
            try:
                async with asyncio.timeout(REQUEST_TIMEOUT):
                    response = await self._session.async_request(
                        "get",
                        f"{self._api_base}{path}",
                        params=params,
                    )
                    if response.status == 401:
                        raise OuraAuthError("Oura access token is invalid", status=401)
                    if response.status == 403:
                        body = (await response.text()).lower()
                        reason = (
                            "membership"
                            if any(word in body for word in ("subscription", "membership"))
                            else "permissions"
                        )
                        raise OuraPermissionError(reason)
                    if response.status == 429:
                        delay = retry_seconds(response.headers)
                        self._retry_at = asyncio.get_running_loop().time() + delay
                        raise OuraRateLimitError(delay)
                    if response.status >= 400:
                        raise OuraApiError(
                            f"Oura request failed (HTTP {response.status})", status=response.status
                        )
                    result = await response.json()
                    if not isinstance(result, dict):
                        raise OuraApiError("Oura returned an invalid response")
                    return result
            except (OuraAuthError, OuraPermissionError, OuraRateLimitError):
                raise
            except ClientResponseError as err:
                # These can also originate in OAuth2Session's token refresh.
                if err.status in (400, 401, 403):
                    raise OuraAuthError("Oura credentials require reauthentication") from err
                failure = OuraApiError("Oura request failed", status=err.status)
            except (ClientError, TimeoutError, ValueError) as err:
                failure = OuraApiError("Cannot read data from Oura")
                failure.__cause__ = err
            except OuraApiError as err:
                if err.status is None or err.status < 500:
                    raise
                failure = err
            finally:
                if response is not None:
                    response.release()
            if attempt == 1:
                raise failure
            await asyncio.sleep(0.5)
        raise AssertionError("Unreachable")

    async def async_get_collection(self, collection: str, **params: Any) -> dict[str, Any]:
        """Read every page, refusing malformed or cycling pagination tokens."""
        path = f"/usercollection/{COLLECTION_PATHS[collection]}"
        if collection == "personal_info":
            return await self._get(path)
        items: list[dict[str, Any]] = []
        tokens: set[str] = set()
        query = dict(params)
        for _ in range(MAX_PAGES):
            page = await self._get(path, query)
            data = page.get("data")
            if not isinstance(data, list) or any(not isinstance(item, dict) for item in data):
                raise OuraApiError("Oura returned an invalid collection")
            items.extend(data)
            token = page.get("next_token")
            if token is None:
                return {"data": items, "next_token": None}
            if not isinstance(token, str) or not token or token in tokens:
                raise OuraApiError("Oura returned an invalid pagination token")
            tokens.add(token)
            query["next_token"] = token
        raise OuraApiError("Oura pagination exceeded the safety limit")

    async def async_get_document(self, collection: str, document_id: str) -> dict[str, Any]:
        """Fetch a document identified by a verified webhook."""
        from urllib.parse import quote

        return await self._get(
            f"/usercollection/{COLLECTION_PATHS[collection]}/{quote(document_id, safe='')}"
        )
