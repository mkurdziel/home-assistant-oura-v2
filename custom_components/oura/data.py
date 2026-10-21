"""Pure Oura record selection and value conversion helpers."""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Any

from homeassistant.util import dt as dt_util

from .coordinator import OuraData


def iso_parse(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else None
    except ValueError:
        return None


def collection_items(data: OuraData, key: str) -> list[dict[str, Any]] | None:
    if key in data.unavailable or key not in data.payloads:
        return None
    items = data.payloads[key].get("data")
    return items if isinstance(items, list) else None


def last_by_time(items, start_key="start_datetime") -> dict[str, Any] | None:
    valid = [
        (iso_parse(item.get(start_key) or item.get("timestamp")), item)
        for item in items or []
        if isinstance(item, dict)
    ]
    return max(
        (pair for pair in valid if pair[0] is not None),
        key=lambda pair: pair[0],
        default=(None, None),
    )[1]


def daily_latest(data: OuraData, key: str) -> dict[str, Any]:
    records = [
        item
        for item in collection_items(data, key) or []
        if isinstance(item.get("day"), str) and item["day"] <= data.today
    ]
    return max(records, key=lambda item: (item["day"], item.get("timestamp") or ""), default={})


def sleep_latest(data: OuraData) -> dict[str, Any] | None:
    records = [
        item
        for item in collection_items(data, "sleep") or []
        if item.get("day", data.today) <= data.today
        and (
            item.get("type") == "long_sleep"
            or (
                item.get("type") in (None, "sleep")
                and (item.get("total_sleep_duration") or 0) >= 10800
            )
        )
    ]
    return max(
        records,
        key=lambda item: (
            item.get("day", ""),
            item.get("total_sleep_duration") or 0,
            item.get("bedtime_end") or "",
        ),
        default=None,
    )


def today_items(data: OuraData, key: str, day_key="day") -> list[dict[str, Any]] | None:
    items = collection_items(data, key)
    return None if items is None else [item for item in items if item.get(day_key) == data.today]


def today_count(data: OuraData, key: str, day_key="day") -> int | None:
    items = today_items(data, key, day_key)
    return None if items is None else len(items)


def duration_minutes(start, end) -> float | None:
    first, last = iso_parse(start), iso_parse(end)
    return max(0, (last - first).total_seconds() / 60) if first and last else None


def today_duration(data: OuraData, key: str) -> float | None:
    items = today_items(data, key)
    if items is None:
        return None
    values = [
        duration_minutes(item.get("start_datetime"), item.get("end_datetime")) for item in items
    ]
    return None if any(value is None for value in values) else sum(values)


def today_calories(data: OuraData) -> float | None:
    items = today_items(data, "workout")
    if items is None or any(not isinstance(item.get("calories"), (int, float)) for item in items):
        return None
    return sum(item["calories"] for item in items)


def bedtime(data: OuraData, edge: str) -> datetime | None:
    record = daily_latest(data, "sleep_time")
    window = record.get("optimal_bedtime")
    if not isinstance(window, dict):
        return None
    try:
        zone = timezone(timedelta(seconds=window["day_tz"]))
        midnight = datetime.combine(datetime.fromisoformat(record["day"]).date(), time(), zone)
        return midnight + timedelta(seconds=window[f"{edge}_offset"])
    except (KeyError, TypeError, ValueError, OverflowError):
        return None


def latest_tag(data: OuraData, enhanced=False) -> dict[str, Any]:
    key = "enhanced_tag" if enhanced else "tag"
    return (
        last_by_time(collection_items(data, key), "start_time" if enhanced else "timestamp") or {}
    )


def tag_label(data: OuraData, enhanced=False) -> str | None:
    item = latest_tag(data, enhanced)
    label = (
        (item.get("custom_name") or item.get("comment") or item.get("tag_type_code"))
        if enhanced
        else (item.get("text") or ", ".join(item.get("tags") or []))
    )
    return str(label)[:255] if label else None


def latest_battery(data: OuraData) -> dict[str, Any]:
    return last_by_time(collection_items(data, "ring_battery_level"), "timestamp") or {}


def latest_ring(data: OuraData) -> dict[str, Any]:
    return last_by_time(collection_items(data, "ring_configuration"), "set_up_at") or next(
        iter(collection_items(data, "ring_configuration") or []), {}
    )


def rest_mode(data: OuraData) -> bool | None:
    items = collection_items(data, "rest_mode_period")
    if items is None:
        return None
    now = dt_util.now()
    for item in items:
        if item.get("start_day", "9999") > data.today:
            continue
        if (start := iso_parse(item.get("start_time"))) and start > now:
            continue
        end = iso_parse(item.get("end_time"))
        if (end and end > now) or (
            end is None and (item.get("end_day") is None or item["end_day"] > data.today)
        ):
            return True
    return False
