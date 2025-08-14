
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional
from datetime import datetime, timezone

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfTemperature, UnitOfLength
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import OuraDataUpdateCoordinator, OuraData

# ---------- helpers ----------
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
        return datetime.fromisoformat(dt_str.replace("Z", "+00:00"))
    except Exception:
        return None

def _min_from_seconds(val):
    try:
        return round((val or 0) / 60, 2)
    except Exception:
        return None

def _sleep_latest(d: OuraData):
    arr = (d.payloads.get("sleep", {}) or {}).get("data")
    if not isinstance(arr, list) or not arr:
        return None
    def _key(x):
        return _iso_parse(x.get("bedtime_start") or x.get("timestamp") or "")
    arr2 = [i for i in arr if isinstance(i, dict)]
    arr2.sort(key=lambda x: _key(x) or datetime.min.replace(tzinfo=timezone.utc))
    return arr2[-1] if arr2 else None

def _daily_first(payloads: dict, key: str):
    return _first_item((payloads.get(key, {}) or {}).get("data", [])) or {}

# Workouts / Sessions helpers
def _filter_by_day(items, day_key="day", day=None):
    if day is None:
        day = datetime.now(timezone.utc).astimezone().date().isoformat()
    if not isinstance(items, list):
        return []
    return [i for i in items if isinstance(i, dict) and i.get(day_key) == day]

def _duration_minutes(start_str, end_str):
    s = _iso_parse(start_str); e = _iso_parse(end_str)
    if s and e:
        return max(0, (e - s).total_seconds()/60.0)
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
    return total if any_val else 0

def _last_by_time(items, start_key="start_datetime"):
    best = None
    best_ts = None
    for i in items or []:
        if not isinstance(i, dict):
            continue
        ts = _iso_parse(i.get(start_key) or i.get("timestamp"))
        if ts and (best_ts is None or ts > best_ts):
            best, best_ts = i, ts
    return best

# ---------- entity description ----------
@dataclass
class OuraCalculatedSensorDescription(SensorEntityDescription):
    value_fn: Callable[[OuraData], Any] | None = None
    attr_fn: Callable[[OuraData], Dict[str, Any]] | None = None

SENSORS: list[OuraCalculatedSensorDescription] = [
    # Scores
    OuraCalculatedSensorDescription(
        key="readiness_score",
        name="Oura V2 Readiness Score",
        icon="mdi:arm-flex",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_readiness"), ["score"]),
        attr_fn=lambda d: _daily_first(d.payloads, "daily_readiness").get("contributors", {}),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="sleep_score",
        name="Oura V2 Sleep Score",
        icon="mdi:sleep",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_sleep"), ["score"]),
        attr_fn=lambda d: _daily_first(d.payloads, "daily_sleep").get("contributors", {}),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="activity_score",
        name="Oura V2 Activity Score",
        icon="mdi:run",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_activity"), ["score"]),
        state_class=SensorStateClass.MEASUREMENT,
    ),

    # Activity totals
    OuraCalculatedSensorDescription(
        key="steps",
        name="Oura V2 Steps",
        icon="mdi:walk",
        value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_activity"), ["steps"]),
        state_class=SensorStateClass.TOTAL,
    ),
    OuraCalculatedSensorDescription(
        key="total_calories",
        name="Oura V2 Total Calories",
        icon="mdi:fire",
        value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_activity"), ["total_calories"]),
        state_class=SensorStateClass.TOTAL,
    ),

    # SpO2
    OuraCalculatedSensorDescription(
        key="spo2_avg",
        name="Oura V2 SpO2 Average",
        icon="mdi:blood-bag",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_spo2"), ["spo2_percentage"]),
        state_class=SensorStateClass.MEASUREMENT,
    ),

    # HR (resting mapped to nightly lowest)
    OuraCalculatedSensorDescription(
        key="resting_heart_rate",
        name="Oura V2 Resting Heart Rate",
        icon="mdi:heart",
        value_fn=lambda d: _find_first((_sleep_latest(d) or {}), ["lowest_heart_rate"]),
        state_class=SensorStateClass.MEASUREMENT,
    ),

    # HR time-series
    OuraCalculatedSensorDescription(
        key="hr_latest",
        name="Oura V2 Heart Rate (Latest)",
        icon="mdi:heart-pulse",
        value_fn=lambda d: (
            (lambda arr: (arr[-1].get("bpm") if isinstance(arr, list) and arr and isinstance(arr[-1], dict) else None))
            ((d.payloads.get("heartrate", {}) or {}).get("data"))
        ),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="hr_min",
        name="Oura V2 Heart Rate (Min)",
        icon="mdi:heart-outline",
        value_fn=lambda d: (
            (lambda arr: (min((x.get("bpm") for x in arr if isinstance(x, dict) and "bpm" in x), default=None)
                          if isinstance(arr, list) else None))
            ((d.payloads.get("heartrate", {}) or {}).get("data"))
        ),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="hr_max",
        name="Oura V2 Heart Rate (Max)",
        icon="mdi:heart-off",
        value_fn=lambda d: (
            (lambda arr: (max((x.get("bpm") for x in arr if isinstance(x, dict) and "bpm" in x), default=None)
                          if isinstance(arr, list) else None))
            ((d.payloads.get("heartrate", {}) or {}).get("data"))
        ),
        state_class=SensorStateClass.MEASUREMENT,
    ),

    # Stress / resilience
    OuraCalculatedSensorDescription(
        key="stress_recovery_high",
        name="Oura V2 Recovery High (Daily)",
        icon="mdi:meditation",
        native_unit_of_measurement="min",
        value_fn=lambda d: _min_from_seconds(_find_first(_daily_first(d.payloads, "daily_stress"), ["recovery_high"])),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="stress_high",
        name="Oura V2 Stress High (Daily)",
        icon="mdi:chart-timeline-variant",
        native_unit_of_measurement="min",
        value_fn=lambda d: _min_from_seconds(_find_first(_daily_first(d.payloads, "daily_stress"), ["stress_high"])),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="resilience_level",
        name="Oura V2 Resilience Level",
        icon="mdi:shield-heart",
        value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_resilience"), ["level"]),
    ),
]

# Sleep details
SENSORS.extend([
    OuraCalculatedSensorDescription(
        key="sleep_total_duration_min",
        name="Oura V2 Sleep Total Duration",
        icon="mdi:sleep",
        native_unit_of_measurement="min",
        value_fn=lambda d: _min_from_seconds((_sleep_latest(d) or {}).get("total_sleep_duration")),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="sleep_time_in_bed_min",
        name="Oura V2 Time In Bed",
        icon="mdi:bed",
        native_unit_of_measurement="min",
        value_fn=lambda d: _min_from_seconds((_sleep_latest(d) or {}).get("time_in_bed")),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="sleep_deep_min",
        name="Oura V2 Deep Sleep",
        icon="mdi:moon-waning-crescent",
        native_unit_of_measurement="min",
        value_fn=lambda d: _min_from_seconds((_sleep_latest(d) or {}).get("deep_sleep_duration")),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="sleep_rem_min",
        name="Oura V2 REM Sleep",
        icon="mdi:moon-waxing-crescent",
        native_unit_of_measurement="min",
        value_fn=lambda d: _min_from_seconds((_sleep_latest(d) or {}).get("rem_sleep_duration")),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="sleep_light_min",
        name="Oura V2 Light Sleep",
        icon="mdi:weather-night",
        native_unit_of_measurement="min",
        value_fn=lambda d: _min_from_seconds((_sleep_latest(d) or {}).get("light_sleep_duration")),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="sleep_awake_min",
        name="Oura V2 Awake Time",
        icon="mdi:alarm",
        native_unit_of_measurement="min",
        value_fn=lambda d: _min_from_seconds((_sleep_latest(d) or {}).get("awake_time")),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="sleep_latency_min",
        name="Oura V2 Sleep Latency",
        icon="mdi:speedometer-slow",
        native_unit_of_measurement="min",
        value_fn=lambda d: _min_from_seconds((_sleep_latest(d) or {}).get("latency")),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="sleep_efficiency",
        name="Oura V2 Sleep Efficiency",
        icon="mdi:gauge",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda d: _find_first((_sleep_latest(d) or {}), ["efficiency"]),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="sleep_avg_breath",
        name="Oura V2 Respiratory Rate (Night)",
        icon="mdi:lungs",
        native_unit_of_measurement="breaths/min",
        value_fn=lambda d: _find_first((_sleep_latest(d) or {}), ["average_breath"]),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="sleep_avg_hr",
        name="Oura V2 Avg HR (Night)",
        icon="mdi:heart",
        native_unit_of_measurement="bpm",
        value_fn=lambda d: _find_first((_sleep_latest(d) or {}), ["average_heart_rate"]),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="sleep_lowest_hr",
        name="Oura V2 Lowest HR (Night)",
        icon="mdi:heart-outline",
        native_unit_of_measurement="bpm",
        value_fn=lambda d: _find_first((_sleep_latest(d) or {}), ["lowest_heart_rate"]),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="sleep_avg_hrv",
        name="Oura V2 HRV RMSSD (Night)",
        icon="mdi:heart-pulse",
        native_unit_of_measurement="ms",
        value_fn=lambda d: _find_first((_sleep_latest(d) or {}), ["average_hrv"]),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="sleep_restless_periods",
        name="Oura V2 Restless Periods",
        icon="mdi:weather-windy",
        value_fn=lambda d: _find_first((_sleep_latest(d) or {}), ["restless_periods"]),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="sleep_bedtime_start",
        name="Oura V2 Bedtime Start",
        icon="mdi:clock-start",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: _iso_parse(_find_first((_sleep_latest(d) or {}), ["bedtime_start"])),
    ),
    OuraCalculatedSensorDescription(
        key="sleep_bedtime_end",
        name="Oura V2 Bedtime End",
        icon="mdi:clock-end",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda d: _iso_parse(_find_first((_sleep_latest(d) or {}), ["bedtime_end"])),
    ),
])

# Readiness contributors & temperatures
SENSORS.extend([
    OuraCalculatedSensorDescription(
        key="readiness_temp_deviation",
        name="Oura V2 Temperature Deviation",
        icon="mdi:thermometer",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_readiness"), ["temperature_deviation"]),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="readiness_temp_trend_deviation",
        name="Oura V2 Temperature Trend Deviation",
        icon="mdi:thermometer-lines",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_readiness"), ["temperature_trend_deviation"]),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="readiness_hrv_balance",
        name="Oura V2 Readiness HRV Balance",
        icon="mdi:heart-pulse",
        value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_readiness"), ["contributors","hrv_balance"]),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="readiness_sleep_balance",
        name="Oura V2 Readiness Sleep Balance",
        icon="mdi:sleep",
        value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_readiness"), ["contributors","sleep_balance"]),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="readiness_activity_balance",
        name="Oura V2 Readiness Activity Balance",
        icon="mdi:run",
        value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_readiness"), ["contributors","activity_balance"]),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="readiness_previous_day_activity",
        name="Oura V2 Readiness Previous Day Activity",
        icon="mdi:walk",
        value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_readiness"), ["contributors","previous_day_activity"]),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="readiness_previous_night",
        name="Oura V2 Readiness Previous Night",
        icon="mdi:weather-night",
        value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_readiness"), ["contributors","previous_night"]),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="readiness_recovery_index",
        name="Oura V2 Readiness Recovery Index",
        icon="mdi:calendar-refresh",
        value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_readiness"), ["contributors","recovery_index"]),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="readiness_body_temperature_contrib",
        name="Oura V2 Readiness Body Temperature (Contributor)",
        icon="mdi:thermometer",
        value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_readiness"), ["contributors","body_temperature"]),
        state_class=SensorStateClass.MEASUREMENT,
    ),
])

# Activity details & contributors
SENSORS.extend([
    OuraCalculatedSensorDescription(
        key="activity_active_calories",
        name="Oura V2 Active Calories",
        icon="mdi:fire",
        value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_activity"), ["active_calories"]),
        state_class=SensorStateClass.TOTAL,
    ),
    OuraCalculatedSensorDescription(
        key="activity_average_met_minutes",
        name="Oura V2 Average MET Minutes",
        icon="mdi:clock-outline",
        native_unit_of_measurement="min",
        value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_activity"), ["average_met_minutes"]),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="activity_equivalent_walking_distance_m",
        name="Oura V2 Equivalent Walking Distance",
        icon="mdi:map-marker-distance",
        native_unit_of_measurement=UnitOfLength.METERS,
        value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_activity"), ["equivalent_walking_distance"]),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="activity_high_activity_met_minutes",
        name="Oura V2 High Activity MET Minutes",
        icon="mdi:lightning-bolt",
        native_unit_of_measurement="min",
        value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_activity"), ["high_activity_met_minutes"]),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="activity_high_activity_time_min",
        name="Oura V2 High Activity Time",
        icon="mdi:timer",
        native_unit_of_measurement="min",
        value_fn=lambda d: _min_from_seconds(_find_first(_daily_first(d.payloads, "daily_activity"), ["high_activity_time"])),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="activity_inactivity_alerts",
        name="Oura V2 Inactivity Alerts",
        icon="mdi:bell-alert",
        value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_activity"), ["inactivity_alerts"]),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="activity_low_activity_met_minutes",
        name="Oura V2 Low Activity MET Minutes",
        icon="mdi:chevron-down",
        native_unit_of_measurement="min",
        value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_activity"), ["low_activity_met_minutes"]),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="activity_low_activity_time_min",
        name="Oura V2 Low Activity Time",
        icon="mdi:timer-sand",
        native_unit_of_measurement="min",
        value_fn=lambda d: _min_from_seconds(_find_first(_daily_first(d.payloads, "daily_activity"), ["low_activity_time"])),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="activity_medium_activity_met_minutes",
        name="Oura V2 Medium Activity MET Minutes",
        icon="mdi:swap-vertical",
        native_unit_of_measurement="min",
        value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_activity"), ["medium_activity_met_minutes"]),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="activity_medium_activity_time_min",
        name="Oura V2 Medium Activity Time",
        icon="mdi:timer-outline",
        native_unit_of_measurement="min",
        value_fn=lambda d: _min_from_seconds(_find_first(_daily_first(d.payloads, "daily_activity"), ["medium_activity_time"])),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="activity_meters_to_target",
        name="Oura V2 Meters To Target",
        icon="mdi:target-variant",
        native_unit_of_measurement=UnitOfLength.METERS,
        value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_activity"), ["meters_to_target"]),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="activity_non_wear_time_min",
        name="Oura V2 Non-wear Time",
        icon="mdi:ring",
        native_unit_of_measurement="min",
        value_fn=lambda d: _min_from_seconds(_find_first(_daily_first(d.payloads, "daily_activity"), ["non_wear_time"])),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="activity_resting_time_min",
        name="Oura V2 Resting Time",
        icon="mdi:sleep",
        native_unit_of_measurement="min",
        value_fn=lambda d: _min_from_seconds(_find_first(_daily_first(d.payloads, "daily_activity"), ["resting_time"])),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="activity_sedentary_met_minutes",
        name="Oura V2 Sedentary MET Minutes",
        icon="mdi:chair-rolling",
        native_unit_of_measurement="min",
        value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_activity"), ["sedentary_met_minutes"]),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="activity_sedentary_time_min",
        name="Oura V2 Sedentary Time",
        icon="mdi:sofa",
        native_unit_of_measurement="min",
        value_fn=lambda d: _min_from_seconds(_find_first(_daily_first(d.payloads, "daily_activity"), ["sedentary_time"])),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="activity_target_calories",
        name="Oura V2 Target Calories",
        icon="mdi:bullseye",
        value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_activity"), ["target_calories"]),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="activity_target_meters",
        name="Oura V2 Target Meters",
        icon="mdi:bullseye-arrow",
        native_unit_of_measurement=UnitOfLength.METERS,
        value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_activity"), ["target_meters"]),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Contributors
    OuraCalculatedSensorDescription(
        key="activity_contrib_meet_daily_targets",
        name="Oura V2 Activity Contributor: Meet Daily Targets",
        icon="mdi:target",
        value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_activity"), ["contributors","meet_daily_targets"]),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="activity_contrib_move_every_hour",
        name="Oura V2 Activity Contributor: Move Every Hour",
        icon="mdi:timer-cog",
        value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_activity"), ["contributors","move_every_hour"]),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="activity_contrib_recovery_time",
        name="Oura V2 Activity Contributor: Recovery Time",
        icon="mdi:progress-clock",
        value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_activity"), ["contributors","recovery_time"]),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="activity_contrib_stay_active",
        name="Oura V2 Activity Contributor: Stay Active",
        icon="mdi:run-fast",
        value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_activity"), ["contributors","stay_active"]),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="activity_contrib_training_frequency",
        name="Oura V2 Activity Contributor: Training Frequency",
        icon="mdi:calendar-check",
        value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_activity"), ["contributors","training_frequency"]),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="activity_contrib_training_volume",
        name="Oura V2 Activity Contributor: Training Volume",
        icon="mdi:dumbbell",
        value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_activity"), ["contributors","training_volume"]),
        state_class=SensorStateClass.MEASUREMENT,
    ),
])

# Vitals
SENSORS.extend([
    OuraCalculatedSensorDescription(
        key="spo2_breathing_disturbance_index",
        name="Oura V2 Breathing Disturbance Index",
        icon="mdi:lungs",
        value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_spo2"), ["breathing_disturbance_index"]),
        state_class=SensorStateClass.MEASUREMENT,
    ),
])

# Optional extras
SENSORS.extend([
    OuraCalculatedSensorDescription(
        key="vo2_max",
        name="Oura V2 VO2 Max",
        icon="mdi:lungs",
        value_fn=lambda d: _find_first(_daily_first(d.payloads, "vo2max"), ["vo2_max"]),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="cardiovascular_age",
        name="Oura V2 Cardiovascular Age",
        icon="mdi:heart-cog",
        value_fn=lambda d: _find_first(_daily_first(d.payloads, "daily_cardiovascular_age"), ["vascular_age"]),
        state_class=SensorStateClass.MEASUREMENT,
    ),
])

# Workouts & Sessions summaries
SENSORS.extend([
    OuraCalculatedSensorDescription(
        key="workouts_today_count",
        name="Oura V2 Workouts Today",
        icon="mdi:arm-flex",
        value_fn=lambda d: (lambda arr: len(_filter_by_day(arr)))(((d.payloads.get("workout", {}) or {}).get("data"))),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="workouts_today_duration_min",
        name="Oura V2 Workouts Duration Today",
        icon="mdi:timer",
        native_unit_of_measurement="min",
        value_fn=lambda d: (lambda arr: _sum_duration_minutes(_filter_by_day(arr)))(((d.payloads.get("workout", {}) or {}).get("data"))),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="workouts_today_calories",
        name="Oura V2 Workouts Calories Today",
        icon="mdi:fire",
        value_fn=lambda d: (lambda arr: (sum((i.get("calories", 0) for i in _filter_by_day(arr) if isinstance(i, dict)), 0) if isinstance(arr, list) else 0))(((d.payloads.get("workout", {}) or {}).get("data"))),
        state_class=SensorStateClass.TOTAL,
    ),
    OuraCalculatedSensorDescription(
        key="last_workout",
        name="Oura V2 Last Workout",
        icon="mdi:run",
        value_fn=lambda d: (lambda w: (w or {}).get("activity"))(_last_by_time(((d.payloads.get("workout", {}) or {}).get("data")))),
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
            } if isinstance(w, dict) else {}))(_last_by_time(((d.payloads.get("workout", {}) or {}).get("data"))))
        ),
    ),
    OuraCalculatedSensorDescription(
        key="sessions_today_count",
        name="Oura V2 Sessions Today",
        icon="mdi:meditation",
        value_fn=lambda d: (lambda arr: len(_filter_by_day(arr)))(((d.payloads.get("session", {}) or {}).get("data"))),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="sessions_today_duration_min",
        name="Oura V2 Sessions Duration Today",
        icon="mdi:timer-outline",
        native_unit_of_measurement="min",
        value_fn=lambda d: (lambda arr: _sum_duration_minutes(_filter_by_day(arr)))(((d.payloads.get("session", {}) or {}).get("data"))),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="last_session",
        name="Oura V2 Last Session",
        icon="mdi:meditation",
        value_fn=lambda d: (lambda s: (s or {}).get("type"))(_last_by_time(((d.payloads.get("session", {}) or {}).get("data")))),
        attr_fn=lambda d: (
            (lambda s: ({
                "type": s.get("type"),
                "mood": s.get("mood"),
                "start": s.get("start_datetime"),
                "end": s.get("end_datetime"),
                "duration_min": _duration_minutes(s.get("start_datetime"), s.get("end_datetime")),
                "day": s.get("day"),
                "id": s.get("id"),
            } if isinstance(s, dict) else {}))(_last_by_time(((d.payloads.get("session", {}) or {}).get("data"))))
        ),
    ),
])

async def async_setup_entry(hass, entry, async_add_entities):
    coordinator: OuraDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    device_info = hass.data[DOMAIN][entry.entry_id]["device_info"]
    uid_prefix = hass.data[DOMAIN][entry.entry_id]["uid_prefix"]
    entities = [OuraCalculatedSensor(coordinator, desc, device_info, uid_prefix) for desc in SENSORS]
    async_add_entities(entities)

class OuraCalculatedSensor(CoordinatorEntity[OuraData], SensorEntity):
    entity_description: OuraCalculatedSensorDescription

    def __init__(self, coordinator: OuraDataUpdateCoordinator, description: OuraCalculatedSensorDescription, device_info: dict, uid_prefix: str):
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{uid_prefix}_{description.key}"
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
