
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional
from datetime import datetime, timezone

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass, SensorEntityDescription
from homeassistant.const import PERCENTAGE, UnitOfTemperature, UnitOfLength
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import OuraDataUpdateCoordinator, OuraData

def _find_first(data: dict, path: list[str], default=None):
    cur = data
    for p in path:
        if not isinstance(cur, dict) or p not in cur:
            return default
        cur = cur[p]
    return cur

def _first_item(lst):
    if isinstance(lst, list) and lst:
        return lst[0]
    return None

def _iso_parse(dt_str):
    try:
        if not dt_str:
            return None
        ds = dt_str.replace('Z', '+00:00')
        return datetime.fromisoformat(ds)
    except Exception:
        try:
            return datetime.fromisoformat(dt_str)
        except Exception:
            return None

def _last_by_time(items, start_key="start_datetime"):
    best = None
    best_ts = None
    for i in items or []:
        if not isinstance(i, dict):
            continue
        ts = _iso_parse(i.get(start_key) or i.get("timestamp") or "")
        if ts and (best_ts is None or ts > best_ts):
            best, best_ts = i, ts
    return best

def _today_iso():
    return datetime.now(timezone.utc).astimezone().date().isoformat()

def _filter_by_day(items, day_key="day", day=None):
    day = day or _today_iso()
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
    for i in items or []:
        if not isinstance(i, dict):
            continue
        mins = _duration_minutes(i.get(start_key), i.get(end_key))
        if mins is not None:
            total += mins
            any_val = True
    return total if any_val else None

def _sleep_latest(d: OuraData):
    arr = (d.payloads.get("sleep", {}) or {}).get("data")
    if not isinstance(arr, list) or not arr:
        return None
    return _last_by_time(arr, start_key="bedtime_start") or arr[-1]

def _daily_first(payloads: dict, key: str):
    return _first_item((payloads.get(key, {}) or {}).get("data", [])) or {}

def _min_from_seconds(val):
    try:
        return round((val or 0) / 60, 2)
    except Exception:
        return None

@dataclass
class OuraCalculatedSensorDescription(SensorEntityDescription):
    value_fn: Callable[[OuraData], Any] | None = None
    attr_fn: Callable[[OuraData], Dict[str, Any]] | None = None

SENSORS: list[OuraCalculatedSensorDescription] = []

def add(desc): SENSORS.append(desc)

# Scores
add(OuraCalculatedSensorDescription(
    key="readiness_score", name="Oura Readiness Score", icon="mdi:arm-flex",
    native_unit_of_measurement=PERCENTAGE,
    value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_readiness"), ["score"]),
    attr_fn=lambda d: _daily_first(d.payloads, "daily_readiness").get("contributors", {}) or {},
    state_class=SensorStateClass.MEASUREMENT,
))
add(OuraCalculatedSensorDescription(
    key="sleep_score", name="Oura Sleep Score", icon="mdi:sleep",
    native_unit_of_measurement=PERCENTAGE,
    value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_sleep"), ["score"]),
    attr_fn=lambda d: _daily_first(d.payloads, "daily_sleep").get("contributors", {}) or {},
    state_class=SensorStateClass.MEASUREMENT,
))
add(OuraCalculatedSensorDescription(
    key="activity_score", name="Oura Activity Score", icon="mdi:run",
    native_unit_of_measurement=PERCENTAGE,
    value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_activity"), ["score"]),
    state_class=SensorStateClass.MEASUREMENT,
))

# Activity totals
add(OuraCalculatedSensorDescription(
    key="steps", name="Oura Steps", icon="mdi:walk",
    value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_activity"), ["steps"]),
    state_class=SensorStateClass.TOTAL,
))
add(OuraCalculatedSensorDescription(
    key="total_calories", name="Oura Total Calories", icon="mdi:fire",
    value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_activity"), ["total_calories"]),
    state_class=SensorStateClass.TOTAL,
))

# SpO2 daily
add(OuraCalculatedSensorDescription(
    key="spo2_avg", name="Oura SpO2 Average", icon="mdi:blood-bag",
    native_unit_of_measurement=PERCENTAGE,
    value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_spo2"), ["spo2_percentage"]),
    state_class=SensorStateClass.MEASUREMENT,
))

# Resting HR (night)
add(OuraCalculatedSensorDescription(
    key="resting_heart_rate", name="Oura Resting Heart Rate", icon="mdi:heart",
    value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_readiness"), ["contributors","resting_heart_rate"]),
    state_class=SensorStateClass.MEASUREMENT,
))

# HR time series (today)
add(OuraCalculatedSensorDescription(
    key="hr_latest", name="Oura Heart Rate (Latest)", icon="mdi:heart-pulse",
    value_fn=lambda d: (lambda items: (items[-1] if items and isinstance(items[-1], (int, float)) else (items[-1].get("bpm") if items and isinstance(items[-1], dict) else None)))(_first_item((d.payloads.get("heartrate", {}) or {}).get("data", [])) or {}.get("items")),
    state_class=SensorStateClass.MEASUREMENT,
))
add(OuraCalculatedSensorDescription(
    key="hr_min", name="Oura Heart Rate (Min)", icon="mdi:heart-outline",
    value_fn=lambda d: (lambda items: min(([i for i in items if isinstance(i, (int, float))] or [i.get("bpm") for i in items if isinstance(i, dict) and "bpm" in i]), default=None))((_first_item((d.payloads.get("heartrate", {}) or {}).get("data", [])) or {}).get("items")),
    state_class=SensorStateClass.MEASUREMENT,
))
add(OuraCalculatedSensorDescription(
    key="hr_max", name="Oura Heart Rate (Max)", icon="mdi:heart-off",
    value_fn=lambda d: (lambda items: max(([i for i in items if isinstance(i, (int, float))] or [i.get("bpm") for i in items if isinstance(i, dict) and "bpm" in i]), default=None))((_first_item((d.payloads.get("heartrate", {}) or {}).get("data", [])) or {}).get("items")),
    state_class=SensorStateClass.MEASUREMENT,
))

# Workouts & Sessions
add(OuraCalculatedSensorDescription(
    key="workouts_today_count", name="Oura Workouts Today", icon="mdi:arm-flex",
    value_fn=lambda d: len(_filter_by_day(((d.payloads.get("workout", {}) or {}).get("data")))),
    state_class=SensorStateClass.MEASUREMENT,
))
add(OuraCalculatedSensorDescription(
    key="workouts_today_duration_min", name="Oura Workouts Duration Today", icon="mdi:timer",
    native_unit_of_measurement="min",
    value_fn=lambda d: _sum_duration_minutes(_filter_by_day(((d.payloads.get("workout", {}) or {}).get("data")))),
    state_class=SensorStateClass.MEASUREMENT,
))
add(OuraCalculatedSensorDescription(
    key="workouts_today_calories", name="Oura Workouts Calories Today", icon="mdi:fire",
    value_fn=lambda d: (lambda arr: (sum((i.get("calories", 0) for i in arr if isinstance(i, dict)), 0) if isinstance(arr, list) else None))(_filter_by_day(((d.payloads.get("workout", {}) or {}).get("data")))),
    state_class=SensorStateClass.TOTAL,
))
add(OuraCalculatedSensorDescription(
    key="last_workout", name="Oura Last Workout", icon="mdi:run",
    value_fn=lambda d: (lambda w: w.get("activity") if isinstance(w, dict) else None)(_last_by_time(((d.payloads.get("workout", {}) or {}).get("data")), "start_datetime")),
    attr_fn=lambda d: (lambda w: ({
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
    } if isinstance(w, dict) else {}))(_last_by_time(((d.payloads.get("workout", {}) or {}).get("data")), "start_datetime")),
))

add(OuraCalculatedSensorDescription(
    key="sessions_today_count", name="Oura Sessions Today", icon="mdi:meditation",
    value_fn=lambda d: len(_filter_by_day(((d.payloads.get("session", {}) or {}).get("data")))),
    state_class=SensorStateClass.MEASUREMENT,
))
add(OuraCalculatedSensorDescription(
    key="sessions_today_duration_min", name="Oura Sessions Duration Today", icon="mdi:timer-outline",
    native_unit_of_measurement="min",
    value_fn=lambda d: _sum_duration_minutes(_filter_by_day(((d.payloads.get("session", {}) or {}).get("data")))),
    state_class=SensorStateClass.MEASUREMENT,
))
add(OuraCalculatedSensorDescription(
    key="last_session", name="Oura Last Session", icon="mdi:meditation",
    value_fn=lambda d: (lambda s: s.get("type") if isinstance(s, dict) else None)(_last_by_time(((d.payloads.get("session", {}) or {}).get("data")), "start_datetime")),
    attr_fn=lambda d: (lambda s: ({
        "type": s.get("type"),
        "mood": s.get("mood"),
        "start": s.get("start_datetime"),
        "end": s.get("end_datetime"),
        "duration_min": _duration_minutes(s.get("start_datetime"), s.get("end_datetime")),
        "day": s.get("day"),
        "id": s.get("id"),
    } if isinstance(s, dict) else {}))(_last_by_time(((d.payloads.get("session", {}) or {}).get("data")), "start_datetime")),
))

# Sleep details
for key, name, field in [
    ("sleep_total_duration_min", "Oura Sleep Total Duration", "total_sleep_duration"),
    ("sleep_time_in_bed_min", "Oura Time In Bed", "time_in_bed"),
    ("sleep_deep_min", "Oura Deep Sleep", "deep_sleep_duration"),
    ("sleep_rem_min", "Oura REM Sleep", "rem_sleep_duration"),
    ("sleep_light_min", "Oura Light Sleep", "light_sleep_duration"),
    ("sleep_awake_min", "Oura Awake Time", "awake_time"),
]:
    add(OuraCalculatedSensorDescription(
        key=key, name=name, icon="mdi:sleep", native_unit_of_measurement="min",
        value_fn=lambda d, f=field: _min_from_seconds((_sleep_latest(d) or {}).get(f)),
        state_class=SensorStateClass.MEASUREMENT,
    ))
add(OuraCalculatedSensorDescription(
    key="sleep_latency_min", name="Oura Sleep Latency", icon="mdi:speedometer-slow",
    native_unit_of_measurement="min",
    value_fn=lambda d: (_sleep_latest(d) or {}).get("latency"),
    state_class=SensorStateClass.MEASUREMENT,
))
add(OuraCalculatedSensorDescription(
    key="sleep_efficiency", name="Oura Sleep Efficiency", icon="mdi:gauge",
    native_unit_of_measurement=PERCENTAGE,
    value_fn=lambda d: (_sleep_latest(d) or {}).get("efficiency"),
    state_class=SensorStateClass.MEASUREMENT,
))
add(OuraCalculatedSensorDescription(
    key="sleep_avg_breath", name="Oura Respiratory Rate (Night)", icon="mdi:lungs",
    native_unit_of_measurement="breaths/min",
    value_fn=lambda d: (_sleep_latest(d) or {}).get("average_breath"),
    state_class=SensorStateClass.MEASUREMENT,
))
add(OuraCalculatedSensorDescription(
    key="sleep_avg_hr", name="Oura Avg HR (Night)", icon="mdi:heart", native_unit_of_measurement="bpm",
    value_fn=lambda d: (_sleep_latest(d) or {}).get("average_heart_rate"),
    state_class=SensorStateClass.MEASUREMENT,
))
add(OuraCalculatedSensorDescription(
    key="sleep_lowest_hr", name="Oura Lowest HR (Night)", icon="mdi:heart-outline",
    native_unit_of_measurement="bpm",
    value_fn=lambda d: (_sleep_latest(d) or {}).get("lowest_heart_rate"),
    state_class=SensorStateClass.MEASUREMENT,
))
add(OuraCalculatedSensorDescription(
    key="sleep_avg_hrv", name="Oura HRV RMSSD (Night)", icon="mdi:heart-pulse",
    native_unit_of_measurement="ms",
    value_fn=lambda d: (_sleep_latest(d) or {}).get("average_hrv"),
    state_class=SensorStateClass.MEASUREMENT,
))
add(OuraCalculatedSensorDescription(
    key="sleep_restless_periods", name="Oura Restless Periods", icon="mdi:weather-windy",
    value_fn=lambda d: (_sleep_latest(d) or {}).get("restless_periods"),
    state_class=SensorStateClass.MEASUREMENT,
))
add(OuraCalculatedSensorDescription(
    key="sleep_bedtime_start", name="Oura Bedtime Start", icon="mdi:clock-start",
    value_fn=lambda d: (_sleep_latest(d) or {}).get("bedtime_start"),
    device_class=SensorDeviceClass.TIMESTAMP,
))
add(OuraCalculatedSensorDescription(
    key="sleep_bedtime_end", name="Oura Bedtime End", icon="mdi:clock-end",
    value_fn=lambda d: (_sleep_latest(d) or {}).get("bedtime_end"),
    device_class=SensorDeviceClass.TIMESTAMP,
))

# Readiness contributors + temps
add(OuraCalculatedSensorDescription(
    key="readiness_temp_deviation", name="Oura Temperature Deviation", icon="mdi:thermometer",
    native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    value_fn=lambda d: _daily_first(d.payloads, "daily_readiness").get("temperature_deviation"),
    state_class=SensorStateClass.MEASUREMENT,
))
add(OuraCalculatedSensorDescription(
    key="readiness_temp_trend_deviation", name="Oura Temperature Trend Deviation", icon="mdi:thermometer-lines",
    native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    value_fn=lambda d: _daily_first(d.payloads, "daily_readiness").get("temperature_trend_deviation"),
    state_class=SensorStateClass.MEASUREMENT,
))
for k, nm in [
    ("hrv_balance","HRV Balance"),
    ("sleep_balance","Sleep Balance"),
    ("activity_balance","Activity Balance"),
    ("previous_day_activity","Previous Day Activity"),
    ("previous_night","Previous Night"),
    ("recovery_index","Recovery Index"),
    ("body_temperature","Body Temperature (Contributor)"),
]:
    add(OuraCalculatedSensorDescription(
        key="readiness_" + k.replace(" ", "_"), name="Oura Readiness " + nm, icon="mdi:chart-line",
        value_fn=lambda d, key=k: _find_first(_daily_first(d.payloads, "daily_readiness"), ["contributors", key]),
        state_class=SensorStateClass.MEASUREMENT,
    ))

# Vitals/optional
add(OuraCalculatedSensorDescription(
    key="spo2_breathing_disturbance_index", name="Oura Breathing Disturbance Index", icon="mdi:lungs",
    value_fn=lambda d: _daily_first(d.payloads, "daily_spo2").get("breathing_disturbance_index"),
    state_class=SensorStateClass.MEASUREMENT,
))
add(OuraCalculatedSensorDescription(
    key="resilience_level_text", name="Oura Resilience Level", icon="mdi:shield-half-full",
    value_fn=lambda d: _daily_first(d.payloads, "daily_resilience").get("level"),
))
add(OuraCalculatedSensorDescription(
    key="stress_high", name="Oura Stress High (Daily)", icon="mdi:chart-timeline-variant",
    value_fn=lambda d: _daily_first(d.payloads, "daily_stress").get("stress_high"),
    state_class=SensorStateClass.MEASUREMENT,
))
add(OuraCalculatedSensorDescription(
    key="vo2_max", name="Oura VO2 Max", icon="mdi:lungs",
    value_fn=lambda d: _daily_first(d.payloads, "vo2max").get("vo2_max"),
    state_class=SensorStateClass.MEASUREMENT,
))
add(OuraCalculatedSensorDescription(
    key="cardiovascular_age", name="Oura Cardiovascular Age", icon="mdi:heart-cog",
    value_fn=lambda d: _daily_first(d.payloads, "daily_cardiovascular_age").get("vascular_age"),
    state_class=SensorStateClass.MEASUREMENT,
))

async def async_setup_entry(hass, entry, async_add_entities):
    coordinator: OuraDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    device_info = hass.data[DOMAIN][entry.entry_id]["device_info"]
    entities = [OuraCalculatedSensor(coordinator, desc, device_info) for desc in SENSORS]
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
        if self.entity_description.value_fn and self.coordinator.data:
            try:
                return self.entity_description.value_fn(self.coordinator.data)
            except Exception:
                return None
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
