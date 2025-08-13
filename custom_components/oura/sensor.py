
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional
from datetime import datetime, timezone

from homeassistant.components.sensor import SensorEntity, SensorStateClass, SensorEntityDescription, SensorDeviceClass
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

def _last_by_time(items, start_key="start_datetime"):
    best = None
    best_ts = None
    for i in items or []:
        if not isinstance(i, dict):
            continue
        ts = _iso_parse(i.get(start_key)) or _iso_parse(i.get("timestamp") or "")
        if ts and (best_ts is None or ts > best_ts):
            best, best_ts = i, ts
    return best

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
    for i in items or []:
        if not isinstance(i, dict):
            continue
        mins = _duration_minutes(i.get(start_key), i.get(end_key))
        if mins is not None:
            total += mins
            any_val = True
    return (total if any_val else None)

@dataclass
class OuraCalculatedSensorDescription(SensorEntityDescription):
    value_fn: Callable[[OuraData], Any] | None = None
    attr_fn: Callable[[OuraData], Dict[str, Any]] | None = None

def _sleep_latest(d: OuraData):
    arr = (d.payloads.get("sleep", {}) or {}).get("data")
    if not isinstance(arr, list) or not arr:
        return None
    return _last_by_time(arr, start_key="bedtime_start") or arr[-1]

def _daily_first(payloads: dict, key: str):
    return _first_item(payloads.get(key, {}).get("data", [])) or {}

def _min_from_seconds(val):
    try:
        return round((val or 0) / 60, 2)
    except Exception:
        return None

SENSORS: list[OuraCalculatedSensorDescription] = [
    # Scores
    OuraCalculatedSensorDescription(
        key="readiness_score",
        name="Oura Readiness Score",
        icon="mdi:arm-flex",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda d: _find_first(_first_item(d.payloads.get("daily_readiness", {}).get("data", [])) or {}, ["score"]),
        attr_fn=lambda d: (_first_item(d.payloads.get("daily_readiness", {}).get("data", [])) or {}).get("contributors", {}),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="sleep_score",
        name="Oura Sleep Score",
        icon="mdi:sleep",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda d: _find_first(_first_item(d.payloads.get("daily_sleep", {}).get("data", [])) or {}, ["score"]),
        attr_fn=lambda d: (_first_item(d.payloads.get("daily_sleep", {}).get("data", [])) or {}).get("contributors", {}),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="activity_score",
        name="Oura Activity Score",
        icon="mdi:run",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda d: _find_first(_first_item(d.payloads.get("daily_activity", {}).get("data", [])) or {}, ["score"]),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Activity totals (today)
    OuraCalculatedSensorDescription(
        key="steps",
        name="Oura Steps",
        icon="mdi:walk",
        value_fn=lambda d: _find_first(_first_item(d.payloads.get("daily_activity", {}).get("data", [])) or {}, ["steps"]),
        state_class=SensorStateClass.TOTAL,
    ),
    OuraCalculatedSensorDescription(
        key="total_calories",
        name="Oura Total Calories",
        icon="mdi:fire",
        value_fn=lambda d: _find_first(_first_item(d.payloads.get("daily_activity", {}).get("data", [])) or {}, ["total_calories"]),
        state_class=SensorStateClass.TOTAL,
    ),
    # SpO2 avg (daily)
    OuraCalculatedSensorDescription(
        key="spo2_avg",
        name="Oura SpO2 Average",
        icon="mdi:blood-bag",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda d: _find_first(_first_item(d.payloads.get("daily_spo2", {}).get("data", [])) or {}, ["spo2_percentage"]),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Resting HR (from readiness contributors)
    OuraCalculatedSensorDescription(
        key="resting_heart_rate",
        name="Oura Resting Heart Rate",
        icon="mdi:heart",
        value_fn=lambda d: _find_first(_first_item(d.payloads.get("daily_readiness", {}).get("data", [])) or {}, ["contributors","resting_heart_rate"]),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # HR timeseries (today)
    OuraCalculatedSensorDescription(
        key="hr_latest",
        name="Oura Heart Rate (Latest)",
        icon="mdi:heart-pulse",
        value_fn=lambda d: (lambda items: (items[-1] if items and isinstance(items[-1], (int, float)) else (items[-1].get("bpm") if items and isinstance(items[-1], dict) else None)) )(((_first_item(d.payloads.get("heartrate", {}).get("data", [])) or {}).get("items"))),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="hr_min",
        name="Oura Heart Rate (Min)",
        icon="mdi:heart-outline",
        value_fn=lambda d: (lambda items: min(([i for i in items if isinstance(i, (int, float))] or [i.get("bpm") for i in items if isinstance(i, dict) and "bpm" in i]), default=None))(((_first_item(d.payloads.get("heartrate", {}).get("data", [])) or {}).get("items"))),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="hr_max",
        name="Oura Heart Rate (Max)",
        icon="mdi:heart-off",
        value_fn=lambda d: (lambda items: max(([i for i in items if isinstance(i, (int, float))] or [i.get("bpm") for i in items if isinstance(i, dict) and "bpm" in i]), default=None))(((_first_item(d.payloads.get("heartrate", {}).get("data", [])) or {}).get("items"))),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Stress/Resilience
    OuraCalculatedSensorDescription(
        key="stress_recovery_high",
        name="Oura Recovery High (Daily)",
        icon="mdi:meditation",
        value_fn=lambda d: _find_first(_first_item(d.payloads.get("daily_stress", {}).get("data", [])) or {}, ["recovery_high"]),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="resilience_level",
        name="Oura Resilience Level",
        icon="mdi:shield-heart",
        value_fn=lambda d: _find_first(_first_item(d.payloads.get("daily_resilience", {}).get("data", [])) or {}, ["level"]),
    ),
]

# Sleep details
SENSORS.extend([
    OuraCalculatedSensorDescription(key="sleep_total_duration_min", name="Oura Sleep Total Duration", icon="mdi:sleep", native_unit_of_measurement="min", value_fn=lambda d: _min_from_seconds((_sleep_latest(d) or {}).get("total_sleep_duration")), state_class=SensorStateClass.MEASUREMENT),
    OuraCalculatedSensorDescription(key="sleep_time_in_bed_min", name="Oura Time In Bed", icon="mdi:bed", native_unit_of_measurement="min", value_fn=lambda d: _min_from_seconds((_sleep_latest(d) or {}).get("time_in_bed")), state_class=SensorStateClass.MEASUREMENT),
    OuraCalculatedSensorDescription(key="sleep_deep_min", name="Oura Deep Sleep", icon="mdi:moon-waning-crescent", native_unit_of_measurement="min", value_fn=lambda d: _min_from_seconds((_sleep_latest(d) or {}).get("deep_sleep_duration")), state_class=SensorStateClass.MEASUREMENT),
    OuraCalculatedSensorDescription(key="sleep_rem_min", name="Oura REM Sleep", icon="mdi:moon-waxing-crescent", native_unit_of_measurement="min", value_fn=lambda d: _min_from_seconds((_sleep_latest(d) or {}).get("rem_sleep_duration")), state_class=SensorStateClass.MEASUREMENT),
    OuraCalculatedSensorDescription(key="sleep_light_min", name="Oura Light Sleep", icon="mdi:weather-night", native_unit_of_measurement="min", value_fn=lambda d: _min_from_seconds((_sleep_latest(d) or {}).get("light_sleep_duration")), state_class=SensorStateClass.MEASUREMENT),
    OuraCalculatedSensorDescription(key="sleep_awake_min", name="Oura Awake Time", icon="mdi:alarm", native_unit_of_measurement="min", value_fn=lambda d: _min_from_seconds((_sleep_latest(d) or {}).get("awake_time")), state_class=SensorStateClass.MEASUREMENT),
    OuraCalculatedSensorDescription(key="sleep_latency_min", name="Oura Sleep Latency", icon="mdi:speedometer-slow", native_unit_of_measurement="min", value_fn=lambda d: _find_first((_sleep_latest(d) or {}), ["latency"]), state_class=SensorStateClass.MEASUREMENT),
    OuraCalculatedSensorDescription(key="sleep_efficiency", name="Oura Sleep Efficiency", icon="mdi:gauge", native_unit_of_measurement=PERCENTAGE, value_fn=lambda d: _find_first((_sleep_latest(d) or {}), ["efficiency"]), state_class=SensorStateClass.MEASUREMENT),
    OuraCalculatedSensorDescription(key="sleep_avg_breath", name="Oura Respiratory Rate (Night)", icon="mdi:lungs", native_unit_of_measurement="breaths/min", value_fn=lambda d: _find_first((_sleep_latest(d) or {}), ["average_breath"]), state_class=SensorStateClass.MEASUREMENT),
    OuraCalculatedSensorDescription(key="sleep_avg_hr", name="Oura Avg HR (Night)", icon="mdi:heart", native_unit_of_measurement="bpm", value_fn=lambda d: _find_first((_sleep_latest(d) or {}), ["average_heart_rate"]), state_class=SensorStateClass.MEASUREMENT),
    OuraCalculatedSensorDescription(key="sleep_lowest_hr", name="Oura Lowest HR (Night)", icon="mdi:heart-outline", native_unit_of_measurement="bpm", value_fn=lambda d: _find_first((_sleep_latest(d) or {}), ["lowest_heart_rate"]), state_class=SensorStateClass.MEASUREMENT),
    OuraCalculatedSensorDescription(key="sleep_avg_hrv", name="Oura HRV RMSSD (Night)", icon="mdi:heart-pulse", native_unit_of_measurement="ms", value_fn=lambda d: _find_first((_sleep_latest(d) or {}), ["average_hrv"]), state_class=SensorStateClass.MEASUREMENT),
    OuraCalculatedSensorDescription(key="sleep_restless_periods", name="Oura Restless Periods", icon="mdi:weather-windy", value_fn=lambda d: _find_first((_sleep_latest(d) or {}), ["restless_periods"]), state_class=SensorStateClass.MEASUREMENT),
    OuraCalculatedSensorDescription(key="sleep_bedtime_start", name="Oura Bedtime Start", icon="mdi:clock-start", value_fn=lambda d: _find_first((_sleep_latest(d) or {}), ["bedtime_start"]), device_class=SensorDeviceClass.TIMESTAMP),
    OuraCalculatedSensorDescription(key="sleep_bedtime_end", name="Oura Bedtime End", icon="mdi:clock-end", value_fn=lambda d: _find_first((_sleep_latest(d) or {}), ["bedtime_end"]), device_class=SensorDeviceClass.TIMESTAMP),
])

# Readiness contributors & temps
SENSORS.extend([
    OuraCalculatedSensorDescription(key="readiness_temp_deviation", name="Oura Temperature Deviation", icon="mdi:thermometer", native_unit_of_measurement=UnitOfTemperature.CELSIUS, value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_readiness"), ["temperature_deviation"]), state_class=SensorStateClass.MEASUREMENT),
    OuraCalculatedSensorDescription(key="readiness_temp_trend_deviation", name="Oura Temperature Trend Deviation", icon="mdi:thermometer-lines", native_unit_of_measurement=UnitOfTemperature.CELSIUS, value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_readiness"), ["temperature_trend_deviation"]), state_class=SensorStateClass.MEASUREMENT),
    OuraCalculatedSensorDescription(key="readiness_hrv_balance", name="Oura Readiness HRV Balance", icon="mdi:heart-pulse", value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_readiness"), ["contributors","hrv_balance"]), state_class=SensorStateClass.MEASUREMENT),
    OuraCalculatedSensorDescription(key="readiness_sleep_balance", name="Oura Readiness Sleep Balance", icon="mdi:sleep", value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_readiness"), ["contributors","sleep_balance"]), state_class=SensorStateClass.MEASUREMENT),
    OuraCalculatedSensorDescription(key="readiness_activity_balance", name="Oura Readiness Activity Balance", icon="mdi:run", value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_readiness"), ["contributors","activity_balance"]), state_class=SensorStateClass.MEASUREMENT),
    OuraCalculatedSensorDescription(key="readiness_previous_day_activity", name="Oura Readiness Previous Day Activity", icon="mdi:walk", value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_readiness"), ["contributors","previous_day_activity"]), state_class=SensorStateClass.MEASUREMENT),
    OuraCalculatedSensorDescription(key="readiness_previous_night", name="Oura Readiness Previous Night", icon="mdi:weather-night", value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_readiness"), ["contributors","previous_night"]), state_class=SensorStateClass.MEASUREMENT),
    OuraCalculatedSensorDescription(key="readiness_recovery_index", name="Oura Readiness Recovery Index", icon="mdi:calendar-refresh", value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_readiness"), ["contributors","recovery_index"]), state_class=SensorStateClass.MEASUREMENT),
    OuraCalculatedSensorDescription(key="readiness_body_temperature_contrib", name="Oura Readiness Body Temperature (Contributor)", icon="mdi:thermometer", value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_readiness"), ["contributors","body_temperature"]), state_class=SensorStateClass.MEASUREMENT),
])

# Activity details
SENSORS.extend([
    OuraCalculatedSensorDescription(key="activity_active_calories", name="Oura Active Calories", icon="mdi:fire", value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_activity"), ["active_calories"]), state_class=SensorStateClass.TOTAL),
    OuraCalculatedSensorDescription(key="activity_average_met_minutes", name="Oura Average MET Minutes", icon="mdi:clock-outline", native_unit_of_measurement="min", value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_activity"), ["average_met_minutes"]), state_class=SensorStateClass.MEASUREMENT),
    OuraCalculatedSensorDescription(key="activity_equivalent_walking_distance_m", name="Oura Equivalent Walking Distance", icon="mdi:map-marker-distance", native_unit_of_measurement=UnitOfLength.METERS, value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_activity"), ["equivalent_walking_distance"]), state_class=SensorStateClass.MEASUREMENT),
    OuraCalculatedSensorDescription(key="activity_high_activity_met_minutes", name="Oura High Activity MET Minutes", icon="mdi:lightning-bolt", native_unit_of_measurement="min", value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_activity"), ["high_activity_met_minutes"]), state_class=SensorStateClass.MEASUREMENT),
    OuraCalculatedSensorDescription(key="activity_high_activity_time_min", name="Oura High Activity Time", icon="mdi:timer", native_unit_of_measurement="min", value_fn=lambda d: _min_from_seconds(_find_first(_daily_first(d.payloads, "daily_activity"), ["high_activity_time"])), state_class=SensorStateClass.MEASUREMENT),
    OuraCalculatedSensorDescription(key="activity_inactivity_alerts", name="Oura Inactivity Alerts", icon="mdi:bell-alert", value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_activity"), ["inactivity_alerts"]), state_class=SensorStateClass.MEASUREMENT),
    OuraCalculatedSensorDescription(key="activity_low_activity_met_minutes", name="Oura Low Activity MET Minutes", icon="mdi:chevron-down", native_unit_of_measurement="min", value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_activity"), ["low_activity_met_minutes"]), state_class=SensorStateClass.MEASUREMENT),
    OuraCalculatedSensorDescription(key="activity_low_activity_time_min", name="Oura Low Activity Time", icon="mdi:timer-sand", native_unit_of_measurement="min", value_fn=lambda d: _min_from_seconds(_find_first(_daily_first(d.payloads, "daily_activity"), ["low_activity_time"])), state_class=SensorStateClass.MEASUREMENT),
    OuraCalculatedSensorDescription(key="activity_medium_activity_met_minutes", name="Oura Medium Activity MET Minutes", icon="mdi:swap-vertical", native_unit_of_measurement="min", value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_activity"), ["medium_activity_met_minutes"]), state_class=SensorStateClass.MEASUREMENT),
    OuraCalculatedSensorDescription(key="activity_medium_activity_time_min", name="Oura Medium Activity Time", icon="mdi:timer-outline", native_unit_of_measurement="min", value_fn=lambda d: _min_from_seconds(_find_first(_daily_first(d.payloads, "daily_activity"), ["medium_activity_time"])), state_class=SensorStateClass.MEASUREMENT),
    OuraCalculatedSensorDescription(key="activity_meters_to_target", name="Oura Meters To Target", icon="mdi:target-variant", native_unit_of_measurement=UnitOfLength.METERS, value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_activity"), ["meters_to_target"]), state_class=SensorStateClass.MEASUREMENT),
    OuraCalculatedSensorDescription(key="activity_non_wear_time_min", name="Oura Non-wear Time", icon="mdi:ring", native_unit_of_measurement="min", value_fn=lambda d: _min_from_seconds(_find_first(_daily_first(d.payloads, "daily_activity"), ["non_wear_time"])), state_class=SensorStateClass.MEASUREMENT),
    OuraCalculatedSensorDescription(key="activity_resting_time_min", name="Oura Resting Time", icon="mdi:sleep", native_unit_of_measurement="min", value_fn=lambda d: _min_from_seconds(_find_first(_daily_first(d.payloads, "daily_activity"), ["resting_time"])), state_class=SensorStateClass.MEASUREMENT),
    OuraCalculatedSensorDescription(key="activity_sedentary_met_minutes", name="Oura Sedentary MET Minutes", icon="mdi:chair-rolling", native_unit_of_measurement="min", value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_activity"), ["sedentary_met_minutes"]), state_class=SensorStateClass.MEASUREMENT),
    OuraCalculatedSensorDescription(key="activity_sedentary_time_min", name="Oura Sedentary Time", icon="mdi:sofa", native_unit_of_measurement="min", value_fn=lambda d: _min_from_seconds(_find_first(_daily_first(d.payloads, "daily_activity"), ["sedentary_time"])), state_class=SensorStateClass.MEASUREMENT),
    OuraCalculatedSensorDescription(key="activity_target_calories", name="Oura Target Calories", icon="mdi:bullseye", value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_activity"), ["target_calories"]), state_class=SensorStateClass.MEASUREMENT),
    OuraCalculatedSensorDescription(key="activity_target_meters", name="Oura Target Meters", icon="mdi:bullseye-arrow", native_unit_of_measurement=UnitOfLength.METERS, value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_activity"), ["target_meters"]), state_class=SensorStateClass.MEASUREMENT),
    # Contributors
    OuraCalculatedSensorDescription(key="activity_contrib_meet_daily_targets", name="Oura Activity Contributor: Meet Daily Targets", icon="mdi:target", value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_activity"), ["contributors","meet_daily_targets"]), state_class=SensorStateClass.MEASUREMENT),
    OuraCalculatedSensorDescription(key="activity_contrib_move_every_hour", name="Oura Activity Contributor: Move Every Hour", icon="mdi:timer-cog", value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_activity"), ["contributors","move_every_hour"]), state_class=SensorStateClass.MEASUREMENT),
    OuraCalculatedSensorDescription(key="activity_contrib_recovery_time", name="Oura Activity Contributor: Recovery Time", icon="mdi:progress-clock", value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_activity"), ["contributors","recovery_time"]), state_class=SensorStateClass.MEASUREMENT),
    OuraCalculatedSensorDescription(key="activity_contrib_stay_active", name="Oura Activity Contributor: Stay Active", icon="mdi:run-fast", value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_activity"), ["contributors","stay_active"]), state_class=SensorStateClass.MEASUREMENT),
    OuraCalculatedSensorDescription(key="activity_contrib_training_frequency", name="Oura Activity Contributor: Training Frequency", icon="mdi:calendar-check", value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_activity"), ["contributors","training_frequency"]), state_class=SensorStateClass.MEASUREMENT),
    OuraCalculatedSensorDescription(key="activity_contrib_training_volume", name="Oura Activity Contributor: Training Volume", icon="mdi:dumbbell", value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_activity"), ["contributors","training_volume"]), state_class=SensorStateClass.MEASUREMENT),
])

# Vitals, stress/resilience, vo2/cardio age
SENSORS.extend([
    OuraCalculatedSensorDescription(key="spo2_breathing_disturbance_index", name="Oura Breathing Disturbance Index", icon="mdi:lungs", value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_spo2"), ["breathing_disturbance_index"]), state_class=SensorStateClass.MEASUREMENT),
    OuraCalculatedSensorDescription(key="stress_high", name="Oura Stress High (Daily)", icon="mdi:chart-timeline-variant", value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_stress"), ["stress_high"]), state_class=SensorStateClass.MEASUREMENT),
    OuraCalculatedSensorDescription(key="resilience_level_text", name="Oura Resilience Level", icon="mdi:shield-half-full", value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_resilience"), ["level"])),
    OuraCalculatedSensorDescription(key="vo2_max", name="Oura VO2 Max", icon="mdi:lungs", value_fn=lambda d: _find_first(_daily_first(d.payloads, "vo2max"), ["vo2_max"]), state_class=SensorStateClass.MEASUREMENT),
    OuraCalculatedSensorDescription(key="cardiovascular_age", name="Oura Cardiovascular Age", icon="mdi:heart-cog", value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_cardiovascular_age"), ["vascular_age"]), state_class=SensorStateClass.MEASUREMENT),
])

# Workout & session summaries
SENSORS.extend([
    OuraCalculatedSensorDescription(key="workouts_today_count", name="Oura Workouts Today", icon="mdi:arm-flex", value_fn=lambda d: (lambda arr: len(_filter_by_day(arr))) ( (d.payloads.get("workout", {}) or {}).get("data") ), state_class=SensorStateClass.MEASUREMENT),
    OuraCalculatedSensorDescription(key="workouts_today_duration_min", name="Oura Workouts Duration Today", icon="mdi:timer", native_unit_of_measurement="min", value_fn=lambda d: (lambda arr: _sum_duration_minutes(_filter_by_day(arr))) ( (d.payloads.get("workout", {}) or {}).get("data") ), state_class=SensorStateClass.MEASUREMENT),
    OuraCalculatedSensorDescription(key="workouts_today_calories", name="Oura Workouts Calories Today", icon="mdi:fire", value_fn=lambda d: (lambda arr: (sum((i.get('calories', 0) for i in _filter_by_day(arr) if isinstance(i, dict)), 0) if isinstance(arr, list) else None)) ( (d.payloads.get("workout", {}) or {}).get("data") ), state_class=SensorStateClass.TOTAL),
    OuraCalculatedSensorDescription(
        key="last_workout", name="Oura Last Workout", icon="mdi:run",
        value_fn=lambda d: (lambda arr: (_last_by_time(arr) or {}).get("activity"))( (d.payloads.get("workout", {}) or {}).get("data") ),
        attr_fn=lambda d: (lambda w: ({ "activity": w.get("activity"), "label": w.get("label"), "intensity": w.get("intensity"), "calories": w.get("calories"), "distance": w.get("distance"), "source": w.get("source"), "start": w.get("start_datetime"), "end": w.get("end_datetime"), "duration_min": _duration_minutes(w.get("start_datetime"), w.get("end_datetime")), "day": w.get("day"), "id": w.get("id") } if isinstance(w, dict) else {}))(_last_by_time( (d.payloads.get("workout", {}) or {}).get("data") ))
    ),
    OuraCalculatedSensorDescription(key="sessions_today_count", name="Oura Sessions Today", icon="mdi:meditation", value_fn=lambda d: (lambda arr: len(_filter_by_day(arr))) ( (d.payloads.get("session", {}) or {}).get("data") ), state_class=SensorStateClass.MEASUREMENT),
    OuraCalculatedSensorDescription(key="sessions_today_duration_min", name="Oura Sessions Duration Today", icon="mdi:timer-outline", native_unit_of_measurement="min", value_fn=lambda d: (lambda arr: _sum_duration_minutes(_filter_by_day(arr))) ( (d.payloads.get("session", {}) or {}).get("data") ), state_class=SensorStateClass.MEASUREMENT),
    OuraCalculatedSensorDescription(
        key="last_session", name="Oura Last Session", icon="mdi:meditation",
        value_fn=lambda d: (lambda arr: (_last_by_time(arr) or {}).get("type"))( (d.payloads.get("session", {}) or {}).get("data") ),
        attr_fn=lambda d: (lambda s: ({ "type": s.get("type"), "mood": s.get("mood"), "start": s.get("start_datetime"), "end": s.get("end_datetime"), "duration_min": _duration_minutes(s.get("start_datetime"), s.get("end_datetime")), "day": s.get("day"), "id": s.get("id") } if isinstance(s, dict) else {}))(_last_by_time( (d.payloads.get("session", {}) or {}).get("data") ))
    ),
])

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
            return self.entity_description.value_fn(self.coordinator.data)
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
