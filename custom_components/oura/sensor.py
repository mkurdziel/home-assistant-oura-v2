
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass, SensorEntityDescription
from homeassistant.const import PERCENTAGE, UnitOfTime
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, CONF_ENABLE_PACK_SLEEP, CONF_ENABLE_PACK_READINESS, CONF_ENABLE_PACK_ACTIVITY, CONF_ENABLE_PACK_VITALS
from .coordinator import OuraDataUpdateCoordinator, OuraData

def _find_first(data: dict, path: list[str], default=None):
    cur = data
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur

def _first_item(lst):
    if isinstance(lst, tuple):
        lst = list(lst)
    if isinstance(lst, list) and lst:
        return lst[0]
    return None

def _latest_daily(data: OuraData, key: str) -> dict:
    return _first_item((data.payloads.get(key, {}) or {}).get("data", [])) or {}

def _latest_sleep_record(data: OuraData) -> dict:
    return _first_item((data.payloads.get("sleep", {}) or {}).get("data", [])) or {}

def _to_minutes(value):
    try:
        if value is None:
            return None
        v = float(value)
        return round(v / 60) if v > 600 else round(v)
    except Exception:
        return None

def _km_from_m(value):
    try:
        if value is None:
            return None
        v = float(value)
        return round(v / 1000, 3) if v > 100 else round(v, 3)
    except Exception:
        return None

@dataclass
class OuraCalculatedSensorDescription(SensorEntityDescription):
    value_fn: Callable[[OuraData], Any] | None = None
    attr_fn: Callable[[OuraData], Dict[str, Any]] | None = None

# --- Base sensors (scores + core metrics) ---
SENSORS: list[OuraCalculatedSensorDescription] = [
    OuraCalculatedSensorDescription(
        key="readiness_score",
        name="Oura Readiness Score",
        icon="mdi:arm-flex",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda d: _find_first(_latest_daily(d, "daily_readiness"), ["score"]),
        attr_fn=lambda d: _latest_daily(d, "daily_readiness").get("contributors", {}),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="sleep_score",
        name="Oura Sleep Score",
        icon="mdi:sleep",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda d: _find_first(_latest_daily(d, "daily_sleep"), ["score"]),
        attr_fn=lambda d: _latest_daily(d, "daily_sleep").get("contributors", {}),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="activity_score",
        name="Oura Activity Score",
        icon="mdi:run",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda d: _find_first(_latest_daily(d, "daily_activity"), ["score"]),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="steps",
        name="Oura Steps",
        icon="mdi:walk",
        value_fn=lambda d: _find_first(_latest_daily(d, "daily_activity"), ["steps"]),
        state_class=SensorStateClass.TOTAL,
    ),
    OuraCalculatedSensorDescription(
        key="total_calories",
        name="Oura Total Calories",
        icon="mdi:fire",
        value_fn=lambda d: _find_first(_latest_daily(d, "daily_activity"), ["total_calories"]),
        state_class=SensorStateClass.TOTAL,
    ),
    OuraCalculatedSensorDescription(
        key="spo2_avg",
        name="Oura SpO2 Average",
        icon="mdi:blood-bag",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda d: _find_first(_latest_daily(d, "daily_spo2"), ["spo2_percentage"]),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="resting_heart_rate",
        name="Oura Resting Heart Rate",
        icon="mdi:heart",
        value_fn=lambda d: _find_first(_latest_daily(d, "daily_readiness"), ["contributors","resting_heart_rate"]),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # HR time-series: latest/min/max for the last window
    OuraCalculatedSensorDescription(
        key="hr_latest",
        name="Oura Heart Rate (Latest)",
        icon="mdi:heart-pulse",
        value_fn=lambda d: (lambda items: (items[-1] if items and isinstance(items[-1], (int, float)) else (items[-1].get("bpm") if items and isinstance(items[-1], dict) else None)))(_latest_daily(d, "heartrate").get("items") if isinstance(_latest_daily(d, "heartrate"), dict) else None),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="hr_min",
        name="Oura Heart Rate (Min)",
        icon="mdi:heart-outline",
        value_fn=lambda d: (lambda items: min(([i for i in items if isinstance(i, (int, float))] or [i.get("bpm") for i in items if isinstance(i, dict) and "bpm" in i]), default=None))(_latest_daily(d, "heartrate").get("items") if isinstance(_latest_daily(d, "heartrate"), dict) else None),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="hr_max",
        name="Oura Heart Rate (Max)",
        icon="mdi:heart-off",
        value_fn=lambda d: (lambda items: max(([i for i in items if isinstance(i, (int, float))] or [i.get("bpm") for i in items if isinstance(i, dict) and "bpm" in i]), default=None))(_latest_daily(d, "heartrate").get("items") if isinstance(_latest_daily(d, "heartrate"), dict) else None),
        state_class=SensorStateClass.MEASUREMENT,
    ),
]

# --- Packs ---
def _pack_sleep() -> list[OuraCalculatedSensorDescription]:
    return [
        OuraCalculatedSensorDescription(
            key="sleep_total_duration_min",
            name="Oura Sleep Total Duration",
            icon="mdi:sleep",
            native_unit_of_measurement=UnitOfTime.MINUTES,
            value_fn=lambda d: _to_minutes(_find_first(_latest_daily(d, "daily_sleep"), ["total_sleep_duration"]) or _find_first(_latest_sleep_record(d), ["duration"])),
            state_class=SensorStateClass.MEASUREMENT,
        ),
        OuraCalculatedSensorDescription(
            key="sleep_deep_duration_min",
            name="Oura Sleep Deep Duration",
            icon="mdi:sleep",
            native_unit_of_measurement=UnitOfTime.MINUTES,
            value_fn=lambda d: _to_minutes(_find_first(_latest_daily(d, "daily_sleep"), ["deep_sleep_duration"])),
            state_class=SensorStateClass.MEASUREMENT,
        ),
        OuraCalculatedSensorDescription(
            key="sleep_rem_duration_min",
            name="Oura Sleep REM Duration",
            icon="mdi:sleep",
            native_unit_of_measurement=UnitOfTime.MINUTES,
            value_fn=lambda d: _to_minutes(_find_first(_latest_daily(d, "daily_sleep"), ["rem_sleep_duration"])),
            state_class=SensorStateClass.MEASUREMENT,
        ),
        OuraCalculatedSensorDescription(
            key="sleep_light_duration_min",
            name="Oura Sleep Light Duration",
            icon="mdi:sleep",
            native_unit_of_measurement=UnitOfTime.MINUTES,
            value_fn=lambda d: _to_minutes(_find_first(_latest_daily(d, "daily_sleep"), ["light_sleep_duration"])),
            state_class=SensorStateClass.MEASUREMENT,
        ),
        OuraCalculatedSensorDescription(
            key="sleep_efficiency",
            name="Oura Sleep Efficiency",
            icon="mdi:sleep",
            native_unit_of_measurement=PERCENTAGE,
            value_fn=lambda d: _find_first(_latest_daily(d, "daily_sleep"), ["efficiency"]),
            state_class=SensorStateClass.MEASUREMENT,
        ),
        OuraCalculatedSensorDescription(
            key="sleep_latency_min",
            name="Oura Sleep Latency",
            icon="mdi:timer-sand",
            native_unit_of_measurement=UnitOfTime.MINUTES,
            value_fn=lambda d: _to_minutes(_find_first(_latest_daily(d, "daily_sleep"), ["latency"])),
            state_class=SensorStateClass.MEASUREMENT,
        ),
        OuraCalculatedSensorDescription(
            key="sleep_bedtime_start",
            name="Oura Bedtime Start",
            icon="mdi:clock-start",
            device_class=SensorDeviceClass.TIMESTAMP,
            value_fn=lambda d: _find_first(_latest_sleep_record(d), ["bedtime_start"]),
        ),
        OuraCalculatedSensorDescription(
            key="sleep_bedtime_end",
            name="Oura Bedtime End",
            icon="mdi:clock-end",
            device_class=SensorDeviceClass.TIMESTAMP,
            value_fn=lambda d: _find_first(_latest_sleep_record(d), ["bedtime_end"]),
        ),
    ]

def _pack_readiness() -> list[OuraCalculatedSensorDescription]:
    return [
        OuraCalculatedSensorDescription(
            key="readiness_hrv_balance",
            name="Oura Readiness HRV Balance",
            icon="mdi:heart-flash",
            native_unit_of_measurement=PERCENTAGE,
            value_fn=lambda d: _find_first(_latest_daily(d, "daily_readiness"), ["contributors","hrv_balance"]),
            state_class=SensorStateClass.MEASUREMENT,
        ),
        OuraCalculatedSensorDescription(
            key="readiness_temperature_deviation_c",
            name="Oura Temperature Deviation",
            icon="mdi:thermometer",
            native_unit_of_measurement="°C",
            value_fn=lambda d: _find_first(_latest_daily(d, "daily_readiness"), ["contributors","temperature_deviation"]),
            state_class=SensorStateClass.MEASUREMENT,
        ),
        OuraCalculatedSensorDescription(
            key="readiness_recovery_index_min",
            name="Oura Recovery Index",
            icon="mdi:progress-clock",
            native_unit_of_measurement=UnitOfTime.MINUTES,
            value_fn=lambda d: _to_minutes(_find_first(_latest_daily(d, "daily_readiness"), ["contributors","recovery_index"])),
            state_class=SensorStateClass.MEASUREMENT,
        ),
        OuraCalculatedSensorDescription(
            key="readiness_sleep_balance",
            name="Oura Sleep Balance",
            icon="mdi:sleep",
            native_unit_of_measurement=PERCENTAGE,
            value_fn=lambda d: _find_first(_latest_daily(d, "daily_readiness"), ["contributors","sleep_balance"]),
            state_class=SensorStateClass.MEASUREMENT,
        ),
        OuraCalculatedSensorDescription(
            key="readiness_activity_balance",
            name="Oura Activity Balance",
            icon="mdi:run",
            native_unit_of_measurement=PERCENTAGE,
            value_fn=lambda d: _find_first(_latest_daily(d, "daily_readiness"), ["contributors","activity_balance"]),
            state_class=SensorStateClass.MEASUREMENT,
        ),
    ]

def _pack_activity() -> list[OuraCalculatedSensorDescription]:
    return [
        OuraCalculatedSensorDescription(
            key="active_calories",
            name="Oura Active Calories",
            icon="mdi:fire",
            value_fn=lambda d: _find_first(_latest_daily(d, "daily_activity"), ["active_calories"]),
            state_class=SensorStateClass.TOTAL,
        ),
        OuraCalculatedSensorDescription(
            key="equivalent_walking_distance_km",
            name="Oura Eq. Walking Distance",
            icon="mdi:map-marker-distance",
            value_fn=lambda d: _km_from_m(_find_first(_latest_daily(d, "daily_activity"), ["equivalent_walking_distance"])),
            state_class=SensorStateClass.MEASUREMENT,
        ),
        OuraCalculatedSensorDescription(
            key="inactive_time_min",
            name="Oura Inactive Time",
            icon="mdi:seat-recline-normal",
            native_unit_of_measurement=UnitOfTime.MINUTES,
            value_fn=lambda d: _to_minutes(_find_first(_latest_daily(d, "daily_activity"), ["inactivity_time"])),
            state_class=SensorStateClass.MEASUREMENT,
        ),
        OuraCalculatedSensorDescription(
            key="non_wear_time_min",
            name="Oura Non-wear Time",
            icon="mdi:watch-off",
            native_unit_of_measurement=UnitOfTime.MINUTES,
            value_fn=lambda d: _to_minutes(_find_first(_latest_daily(d, "daily_activity"), ["non_wear_time"])),
            state_class=SensorStateClass.MEASUREMENT,
        ),
        OuraCalculatedSensorDescription(
            key="activity_meet_daily_targets",
            name="Oura Activity: Meet Daily Targets",
            icon="mdi:target",
            native_unit_of_measurement=PERCENTAGE,
            value_fn=lambda d: _find_first(_latest_daily(d, "daily_activity"), ["contributors","meet_daily_targets"]),
            state_class=SensorStateClass.MEASUREMENT,
        ),
        OuraCalculatedSensorDescription(
            key="activity_move_every_hour",
            name="Oura Activity: Move Every Hour",
            icon="mdi:timer-outline",
            native_unit_of_measurement=PERCENTAGE,
            value_fn=lambda d: _find_first(_latest_daily(d, "daily_activity"), ["contributors","move_every_hour"]),
            state_class=SensorStateClass.MEASUREMENT,
        ),
        OuraCalculatedSensorDescription(
            key="activity_stay_active",
            name="Oura Activity: Stay Active",
            icon="mdi:run-fast",
            native_unit_of_measurement=PERCENTAGE,
            value_fn=lambda d: _find_first(_latest_daily(d, "daily_activity"), ["contributors","stay_active"]),
            state_class=SensorStateClass.MEASUREMENT,
        ),
        OuraCalculatedSensorDescription(
            key="activity_training_frequency",
            name="Oura Activity: Training Frequency",
            icon="mdi:calendar-clock",
            native_unit_of_measurement=PERCENTAGE,
            value_fn=lambda d: _find_first(_latest_daily(d, "daily_activity"), ["contributors","training_frequency"]),
            state_class=SensorStateClass.MEASUREMENT,
        ),
        OuraCalculatedSensorDescription(
            key="activity_training_volume",
            name="Oura Activity: Training Volume",
            icon="mdi:dumbbell",
            native_unit_of_measurement=PERCENTAGE,
            value_fn=lambda d: _find_first(_latest_daily(d, "daily_activity"), ["contributors","training_volume"]),
            state_class=SensorStateClass.MEASUREMENT,
        ),
        OuraCalculatedSensorDescription(
            key="activity_recovery_time",
            name="Oura Activity: Recovery Time",
            icon="mdi:heart-plus",
            native_unit_of_measurement=PERCENTAGE,
            value_fn=lambda d: _find_first(_latest_daily(d, "daily_activity"), ["contributors","recovery_time"]),
            state_class=SensorStateClass.MEASUREMENT,
        ),
    ]

def _pack_vitals() -> list[OuraCalculatedSensorDescription]:
    return [
        OuraCalculatedSensorDescription(
            key="respiratory_rate",
            name="Oura Respiratory Rate",
            icon="mdi:lungs",
            value_fn=lambda d: _find_first(_latest_daily(d, "daily_sleep"), ["respiratory_rate"]),
            state_class=SensorStateClass.MEASUREMENT,
        ),
        OuraCalculatedSensorDescription(
            key="hrv_rmssd",
            name="Oura HRV (RMSSD)",
            icon="mdi:heart-cog",
            value_fn=lambda d: _find_first(_latest_sleep_record(d), ["rmssd"]) or _find_first(_latest_daily(d, "daily_sleep"), ["rmssd"]),
            state_class=SensorStateClass.MEASUREMENT,
        ),
    ]

def _build_sensors(options: dict | None) -> list[OuraCalculatedSensorDescription]:
    base = SENSORS.copy()
    if not options:
        return base + _pack_sleep() + _pack_readiness() + _pack_activity() + _pack_vitals()
    def _opt(name: str, default: bool) -> bool:
        return bool(options.get(name, default))
    if _opt(CONF_ENABLE_PACK_SLEEP, True):
        base += _pack_sleep()
    if _opt(CONF_ENABLE_PACK_READINESS, True):
        base += _pack_readiness()
    if _opt(CONF_ENABLE_PACK_ACTIVITY, True):
        base += _pack_activity()
    if _opt(CONF_ENABLE_PACK_VITALS, True):
        base += _pack_vitals()
    return base

async def async_setup_entry(hass, entry, async_add_entities):
    coordinator: OuraDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    device_info = hass.data[DOMAIN][entry.entry_id]["device_info"]
    options = hass.data[DOMAIN][entry.entry_id].get("options") or {}
    descriptions = _build_sensors(options)
    entities = [OuraCalculatedSensor(coordinator, desc, device_info) for desc in descriptions]
    async_add_entities(entities)

class OuraCalculatedSensor(CoordinatorEntity[OuraData], SensorEntity):
    entity_description: OuraCalculatedSensorDescription

    def __init__(self, coordinator: OuraDataUpdateCoordinator, description: OuraCalculatedSensorDescription, device_info: dict):
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.name}_{description.key}"
        self._attr_device_info = device_info

    @property
    def native_value(self):
        if self.entity_description.value_fn:
            return self.entity_description.value_fn(self.coordinator.data) if self.coordinator.data else None
        return None

    @property
    def extra_state_attributes(self) -> Optional[Dict[str, Any]]:
        if self.entity_description.attr_fn and self.coordinator.data:
            try:
                attrs = self.entity_description.attr_fn(self.coordinator.data) or {}
                return attrs if isinstance(attrs, dict) else {}
            except Exception:
                return {}
        return {}


# ---- Helpers for workouts & sessions summaries ----
from datetime import datetime, timezone
from datetime import datetime

def _iso_parse(dt_str):
    try:
        if not dt_str:
            return None
        # Normalize 'Z' to '+00:00' for Python's fromisoformat
        ds = dt_str.replace('Z', '+00:00')
        return datetime.fromisoformat(ds)
    except Exception:
        try:
            # Some fields may be date-only
            return datetime.fromisoformat(dt_str)
        except Exception:
            return None

def _today_iso():
    return datetime.now(timezone.utc).astimezone().date().isoformat()

def _filter_by_day(items, day_key="day", day=None):
    if day is None:
        day = _today_iso()
    if not isinstance(items, list):
        return []
    return [i for i in items if isinstance(i, dict) and i.get(day_key) == day]

def _duration_minutes(start_str, end_str):
    sd = _iso_parse(start_str)
    ed = _iso_parse(end_str)
    if sd and ed:
        return max(0, (ed - sd).total_seconds() / 60.0)
    return None

def _sum_duration_minutes(items, start_key="start_datetime", end_key="end_datetime"):
    total = 0.0
    any_val = False
    for i in items:
        if not isinstance(i, dict):
            continue
        mins = _duration_minutes(i.get(start_key), i.get(end_key))
        if mins is not None:
            total += mins
            any_val = True
    return (total if any_val else None)

def _last_by_time(items, start_key="start_datetime"):
    # Return most recent by start time
    best = None
    best_ts = None
    for i in items or []:
        if not isinstance(i, dict):
            continue
        ts = _iso_parse(i.get(start_key)) or _iso_parse(i.get("timestamp") or "")
        if ts and (best_ts is None or ts > best_ts):
            best, best_ts = i, ts
    return best

# ---- Append Workout & Session summary sensors ----
SENSORS.extend([
    # Workouts: count today
    OuraCalculatedSensorDescription(
        key="workouts_today_count",
        name="Oura Workouts Today",
        icon="mdi:arm-flex",
        value_fn=lambda d: (
            (lambda arr: len(_filter_by_day(arr))) ( (d.payloads.get("workout", {}) or {}).get("data") )
        ),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Workouts: total duration today (minutes)
    OuraCalculatedSensorDescription(
        key="workouts_today_duration_min",
        name="Oura Workouts Duration Today",
        icon="mdi:timer",
        native_unit_of_measurement="min",
        value_fn=lambda d: (
            (lambda arr: _sum_duration_minutes(_filter_by_day(arr))) ( (d.payloads.get("workout", {}) or {}).get("data") )
        ),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Workouts: total calories today
    OuraCalculatedSensorDescription(
        key="workouts_today_calories",
        name="Oura Workouts Calories Today",
        icon="mdi:fire",
        value_fn=lambda d: (
            (lambda arr: (sum((i.get("calories", 0) for i in _filter_by_day(arr) if isinstance(i, dict)), 0) if isinstance(arr, list) else None))
            ( (d.payloads.get("workout", {}) or {}).get("data") )
        ),
        state_class=SensorStateClass.TOTAL,
    ),
    # Last workout summary
    OuraCalculatedSensorDescription(
        key="last_workout",
        name="Oura Last Workout",
        icon="mdi:run",
        value_fn=lambda d: (
            (lambda arr: (_last_by_time(arr) or {}).get("activity"))
            ( (d.payloads.get("workout", {}) or {}).get("data") )
        ),
        attr_fn=lambda d: (
            (lambda w: ({
                "activity": w.get("activity"),
                "label": w.get("label"),
                "intensity": w.get("intensity"),
                "calories": w.get("calories"),
                "distance": w.get("distance"),
                "source": w.get("source"),
                "start": w.get("start_datetime"),
                "end": w.get("end_datetime"),
                "duration_min": _duration_minutes(w.get("start_datetime"), w.get("end_datetime")),
                "day": w.get("day"),
                "id": w.get("id"),
            } if isinstance(w, dict) else {}))
            (_last_by_time( (d.payloads.get("workout", {}) or {}).get("data") ))
        ),
    ),
    # Sessions: count today
    OuraCalculatedSensorDescription(
        key="sessions_today_count",
        name="Oura Sessions Today",
        icon="mdi:meditation",
        value_fn=lambda d: (
            (lambda arr: len(_filter_by_day(arr))) ( (d.payloads.get("session", {}) or {}).get("data") )
        ),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Sessions: total duration today (minutes)
    OuraCalculatedSensorDescription(
        key="sessions_today_duration_min",
        name="Oura Sessions Duration Today",
        icon="mdi:timer-outline",
        native_unit_of_measurement="min",
        value_fn=lambda d: (
            (lambda arr: _sum_duration_minutes(_filter_by_day(arr))) ( (d.payloads.get("session", {}) or {}).get("data") )
        ),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Last session summary
    OuraCalculatedSensorDescription(
        key="last_session",
        name="Oura Last Session",
        icon="mdi:meditation",
        value_fn=lambda d: (
            (lambda arr: (_last_by_time(arr) or {}).get("type"))
            ( (d.payloads.get("session", {}) or {}).get("data") )
        ),
        attr_fn=lambda d: (
            (lambda s: ({
                "type": s.get("type"),
                "mood": s.get("mood"),
                "start": s.get("start_datetime"),
                "end": s.get("end_datetime"),
                "duration_min": _duration_minutes(s.get("start_datetime"), s.get("end_datetime")),
                "day": s.get("day"),
                "id": s.get("id"),
            } if isinstance(s, dict) else {}))
            (_last_by_time( (d.payloads.get("session", {}) or {}).get("data") ))
        ),
    ),
])
