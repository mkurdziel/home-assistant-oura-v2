"""Opt-in Oura subscriptions with verified, account-scoped event delivery."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import secrets
import time
from collections import OrderedDict
from copy import deepcopy
from datetime import timedelta
from urllib.parse import quote, urlsplit

from aiohttp import ClientError, web
from homeassistant.components import webhook
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.network import NoURLAvailableError
from homeassistant.util import dt as dt_util

from .api import API_BASE, COLLECTION_PATHS, OuraApiError, OuraRateLimitError, retry_seconds
from .const import DOMAIN
from .data import iso_parse

_LOGGER = logging.getLogger(__name__)
WEBHOOK_STATE = "webhooks"
WEBHOOK_TYPES = {
    ("vo2_max" if key == "vo2max" else key): key
    for key in COLLECTION_PATHS
    if key not in {"personal_info", "heartrate", "ring_battery_level"}
}
EVENT_TYPES = ("create", "update", "delete")


class OuraWebhooks:
    """Own only subscriptions stored by this entry, never other app subscriptions."""

    def __init__(self, hass, entry, coordinator, implementation):
        self.hass = hass
        self.entry = entry
        self.coordinator = coordinator
        self.client_id = getattr(implementation, "client_id", None)
        self.client_secret = getattr(implementation, "client_secret", None)
        self.state = deepcopy(entry.data.get(WEBHOOK_STATE, {}))
        self._unsubscribe = None
        self._registered = False
        self.last_error: str | None = None
        self._events: OrderedDict[tuple[str, str], tuple[str, str]] = OrderedDict()
        self._subscription_lock = asyncio.Lock()

    def _save(self):
        self.hass.config_entries.async_update_entry(
            self.entry, data={**self.entry.data, WEBHOOK_STATE: deepcopy(self.state)}
        )

    async def _request(self, method: str, path="", payload=None):
        if not self.client_id or not self.client_secret:
            raise ConfigEntryError("Oura webhooks require local OAuth application credentials")
        remaining = self.state.get("retry_at", 0) - time.time()
        if remaining > 0:
            raise OuraRateLimitError(remaining)
        response = None
        try:
            async with asyncio.timeout(30):
                response = await async_get_clientsession(self.hass).request(
                    method,
                    f"{API_BASE}/webhook/subscription{path}",
                    headers={"x-client-id": self.client_id, "x-client-secret": self.client_secret},
                    json=payload,
                )
                if response.status == 429:
                    delay = retry_seconds(response.headers)
                    self.state["retry_at"] = time.time() + delay
                    self._save()
                    raise OuraRateLimitError(delay)
                if method == "delete" and response.status in (403, 404):
                    return None  # Oura also uses 403 for an already removed subscription.
                if response.status >= 400:
                    raise OuraApiError(
                        f"Oura webhook request failed (HTTP {response.status})",
                        status=response.status,
                    )
                if response.status == 204:
                    return None
                result = await response.json()
                if method == "get" and not path:
                    if not isinstance(result, list) or any(
                        not isinstance(item, dict) for item in result
                    ):
                        raise OuraApiError("Oura returned an invalid webhook subscription list")
                elif not isinstance(result, dict):
                    raise OuraApiError("Oura returned an invalid webhook subscription")
                return result
        except (ClientError, TimeoutError, ValueError) as err:
            raise OuraApiError("Cannot manage Oura webhook subscriptions") from err
        finally:
            if response is not None:
                response.release()

    async def async_start(self):
        """Register verification before creating remote subscriptions."""
        if not self.client_secret or not self.client_id:
            raise ConfigEntryError("Oura webhooks require local OAuth application credentials")
        self.state.setdefault("id", webhook.async_generate_id())
        self.state.setdefault("verification_token", secrets.token_hex(32))
        try:
            url = webhook.async_generate_url(self.hass, self.state["id"], allow_internal=False)
        except NoURLAvailableError as err:
            raise ConfigEntryError(
                "Set an external HTTPS Home Assistant URL before enabling Oura webhooks"
            ) from err
        if urlsplit(url).scheme != "https":
            raise ConfigEntryError("Oura webhooks require an external HTTPS Home Assistant URL")
        webhook.async_register(
            self.hass,
            DOMAIN,
            "Oura updates",
            self.state["id"],
            self._handle,
            local_only=False,
            allowed_methods=["GET", "POST"],
        )
        self._registered = True
        self.state["callback_url"] = url
        self._save()
        try:
            await self.async_reconcile(url)
        except OuraApiError as err:
            self.last_error = str(err)
            _LOGGER.warning(
                "Oura webhook setup incomplete; polling remains active and subscriptions will be retried"
            )
        except BaseException:
            self.async_stop()
            raise
        self._unsubscribe = async_track_time_interval(
            self.hass, self._async_renew, timedelta(hours=1)
        )
        self.entry.async_on_unload(self.async_stop)

    def _desired_pairs(self):
        scopes = self.coordinator.scopes
        for data_type, collection in WEBHOOK_TYPES.items():
            from .coordinator import DAILY, SCOPES

            required = SCOPES.get(collection)
            if scopes is not None and required is not None and required not in scopes:
                continue
            if (
                scopes is not None
                and collection in DAILY
                and not scopes.intersection({"daily", "heart_health"})
            ):
                continue
            for event in EVENT_TYPES:
                yield data_type, event

    async def async_reconcile(self, url):
        """Renew expiring subscriptions and repair partial setup across restarts."""
        async with self._subscription_lock:
            desired = set(self._desired_pairs())
            known_ids = {item["id"] for item in self.state.get("subscriptions", [])}
            # Recover unknown POST outcomes and externally deleted subscriptions.
            # Never adopt or modify another callback's subscriptions.
            remote = await self._request("get")
            subscriptions = [
                dict(item)
                for item in remote
                if item.get("callback_url") == url or item.get("id") in known_ids
            ]
            self.state["subscriptions"] = list(subscriptions)
            self._save()
            for subscription in list(subscriptions):
                pair = subscription.get("data_type"), subscription.get("event_type")
                expiration = iso_parse(subscription.get("expiration_time"))
                if (
                    pair not in desired
                    or subscription.get("callback_url") != url
                    or expiration is None
                    or expiration <= dt_util.utcnow()
                ):
                    await self._request("delete", f"/{quote(subscription['id'], safe='')}")
                    subscriptions.remove(subscription)
                    self.state["subscriptions"] = list(subscriptions)
                    self._save()
                elif expiration < dt_util.utcnow() + timedelta(hours=6):
                    renewed = await self._request(
                        "put", f"/renew/{quote(subscription['id'], safe='')}"
                    )
                    subscription.update(self._validate_subscription(renewed, url, *pair))
                    self.state["subscriptions"] = list(subscriptions)
                    self._save()
            existing = {(item["data_type"], item["event_type"]) for item in subscriptions}
            for data_type, event in sorted(desired - existing):
                result = await self._request(
                    "post",
                    payload={
                        "callback_url": url,
                        "verification_token": self.state["verification_token"],
                        "event_type": event,
                        "data_type": data_type,
                    },
                )
                subscriptions.append(self._validate_subscription(result, url, data_type, event))
                # Save every successful creation so a retry never duplicates it.
                self.state["subscriptions"] = list(subscriptions)
                self._save()

    @staticmethod
    def _validate_subscription(result, url, data_type, event):
        if (
            not isinstance(result, dict)
            or not isinstance(result.get("id"), str)
            or iso_parse(result.get("expiration_time")) is None
        ):
            raise OuraApiError("Oura returned an invalid webhook subscription")
        return {
            "id": result["id"],
            "expiration_time": result["expiration_time"],
            "callback_url": url,
            "data_type": data_type,
            "event_type": event,
        }

    async def _async_renew(self, _now):
        try:
            await self.async_reconcile(
                webhook.async_generate_url(self.hass, self.state["id"], allow_internal=False)
            )
            self.last_error = None
        except (OuraApiError, NoURLAvailableError) as err:
            self.last_error = (
                str(err) if isinstance(err, OuraApiError) else "External URL unavailable"
            )
            _LOGGER.warning("Oura webhook renewal failed; polling remains active")

    async def async_cleanup(self):
        """Remove only IDs owned by this config entry; retain failures for retry."""
        async with self._subscription_lock:
            subscriptions = list(self.state.get("subscriptions", []))
            if self.state.get("callback_url"):
                known_ids = {item["id"] for item in subscriptions}
                subscriptions = [
                    dict(item)
                    for item in await self._request("get")
                    if item.get("callback_url") == self.state["callback_url"]
                    or item.get("id") in known_ids
                ]
            for subscription in list(subscriptions):
                await self._request("delete", f"/{quote(subscription['id'], safe='')}")
                subscriptions.remove(subscription)
                self.state["subscriptions"] = list(subscriptions)
                self._save()
            self.state.pop("callback_url", None)
            self.state["subscriptions"] = []
            self._save()
        self.async_stop()

    def async_stop(self):
        if self._registered:
            webhook.async_unregister(self.hass, self.state["id"])
            self._registered = False
        if self._unsubscribe is not None:
            self._unsubscribe()
            self._unsubscribe = None

    async def _handle(self, hass, webhook_id, request):
        if request.method == "GET":
            if not secrets.compare_digest(
                request.query.get("verification_token", "").encode(),
                self.state["verification_token"].encode(),
            ):
                return web.Response(status=401)
            challenge = request.query.get("challenge")
            return (
                web.json_response({"challenge": challenge})
                if challenge
                else web.Response(status=400)
            )
        timestamp = request.headers.get("x-oura-timestamp", "")
        signature = request.headers.get("x-oura-signature", "")
        try:
            if abs(time.time() - int(timestamp)) > 300:
                return web.Response(status=401)
        except ValueError:
            return web.Response(status=401)
        body = bytearray()
        try:
            async with asyncio.timeout(5):
                while chunk := await request.content.read(65537 - len(body)):
                    body.extend(chunk)
                    if len(body) > 65536:
                        return web.Response(status=413)
        except TimeoutError:
            return web.Response(status=408)
        body = bytes(body)
        expected = (
            hmac.new(self.client_secret.encode(), timestamp.encode() + body, hashlib.sha256)
            .hexdigest()
            .upper()
        )
        if (
            len(signature) != 64
            or not signature.isascii()
            or not hmac.compare_digest(signature, expected)
        ):
            return web.Response(status=401)
        try:
            event = json.loads(body)
        except (ValueError, UnicodeDecodeError):
            return web.Response(status=400)
        if not isinstance(event, dict):
            return web.Response(status=400)
        data_type = event.get("data_type")
        collection = WEBHOOK_TYPES.get(data_type) if isinstance(data_type, str) else None
        kind, identifier = event.get("event_type"), event.get("object_id")
        event_time = event.get("event_time")
        if event.get("user_id") != self.entry.data.get("user_id", self.entry.unique_id):
            # App-level subscriptions can deliver other consenting users' events.
            # Acknowledge without routing so Oura doesn't retry expected broadcasts.
            return web.Response(status=200)
        if (
            collection is None
            or kind not in EVENT_TYPES
            or not isinstance(identifier, str)
            or not identifier
            or len(identifier) > 256
            or iso_parse(event_time) is None
        ):
            return web.Response(status=400)
        key = collection, identifier
        previous = self._events.get(key)
        if previous and iso_parse(previous[0]) >= iso_parse(event_time):
            return web.Response(status=200)
        self._events[key] = (event_time, kind)
        self._events.move_to_end(key)
        if len(self._events) > 1024:
            self._events.popitem(last=False)
        self.entry.async_create_task(
            hass,
            self.coordinator.async_process_event(collection, identifier, kind),
            "Oura webhook update",
        )
        return web.Response(status=200)
