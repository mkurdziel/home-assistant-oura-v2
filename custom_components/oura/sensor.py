
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from homeassistant.components.sensor import SensorEntity, SensorStateClass, SensorEntityDescription
from homeassistant.const import PERCENTAGE
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, CONF_ENABLE_WORKOUT_SUMMARY, CONF_ENABLE_SESSION_SUMMARY
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

# ---- Extra helpers for per-metric sensors ----
from datetime import datetime, timezone, timedelta

def _sec_to_min(val):
    try:
        return round(float(val) / 60.0, 2) if val is not None else None
    except Exception:
        return None

def _m_to_km(val):
    try:
        return round(float(val) / 1000.0, 3) if val is not None else None
    except Exception:
        return None

def _pick_main_sleep(sleep_items: list | None) -> dict | None:
    """Choose the 'main' sleep from a list: prefer type 'long_sleep' or max total_sleep_duration."""
    if not isinstance(sleep_items, list) or not sleep_items:
        return None
    best = None
    best_score = -1
    for it in sleep_items:
        if not isinstance(it, dict):
            continue
        dur = it.get("total_sleep_duration") or 0
        typ = it.get("type") or ""
        score = (2 if typ == "long_sleep" else 1 if typ == "sleep" else 0) * 10_000 + int(dur or 0)
        if score > best_score:
            best_score = score
            best = it
    return best

# ---- Workouts & Sessions helpers ----
from datetime import datetime

def _items_from_payload(data: OuraData, key: str) -> list[dict]:
    payload = data.payloads.get(key, {}) if data and data.payloads else {}
    arr = payload.get("data", [])
    return arr if isinstance(arr, list) else []

def _parse_iso(dt: str) -> datetime | None:
    if not isinstance(dt, str):
        return None
    try:
        if dt.endswith("Z"):
            dt = dt[:-1] + "+00:00"
        return datetime.fromisoformat(dt)
    except Exception:
        return None

def _duration_minutes(item: dict) -> float | None:
    for k in ("duration", "duration_seconds", "duration_min", "duration_minutes"):
        if k in item and isinstance(item[k], (int, float)):
            if "min" in k:
                return float(item[k])
            return float(item[k]) / 60.0
    sd = _parse_iso(item.get("start_datetime"))
    ed = _parse_iso(item.get("end_datetime"))
    if sd and ed:
        return max((ed - sd).total_seconds() / 60.0, 0.0)
    return None

def _sum_calories(items: list[dict]) -> float | None:
    total = 0.0
    found = False
    for it in items:
        for k in ("calories", "total_calories", "kcal", "energy_burned_kcal"):
            if k in it and isinstance(it[k], (int, float)):
                total += float(it[k])
                found = True
                break
    return total if found else None

def _sum_duration_minutes(items: list[dict]) -> float | None:
    mins = 0.0
    found = False
    for it in items:
        dm = _duration_minutes(it)
        if isinstance(dm, (int, float)):
            mins += float(dm)
            found = True
    return mins if found else None

def _last_by_start(items: list[dict]) -> dict | None:
    if not items:
        return None
    try:
        return max(items, key=lambda i: i.get("start_datetime", ""))
    except Exception:
        return items[-1]

@dataclass
class OuraCalculatedSensorDescription(SensorEntityDescription):
    value_fn: Callable[[OuraData], Any] | None = None
    attr_fn: Callable[[OuraData], Dict[str, Any]] | None = None
    group: str | None = None

SENSORS: list[OuraCalculatedSensorDescription] = [
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
    OuraCalculatedSensorDescription(
        key="steps",
        name="Oura Steps",
        icon="mdi:walk",
        value_fn=lambda d: _find_first(_first_item(d.payloads.get("daily_activity", {}).get("data", [])) or {}, ["steps"]),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="total_calories",
        name="Oura Total Calories",
        icon="mdi:fire",
        value_fn=lambda d: _find_first(_first_item(d.payloads.get("daily_activity", {}).get("data", [])) or {}, ["total_calories"]),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="spo2_avg",
        name="Oura SpO2 Average",
        icon="mdi:blood-bag",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda d: _find_first(_first_item(d.payloads.get("daily_spo2", {}).get("data", [])) or {}, ["spo2_percentage"]),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="resting_heart_rate",
        name="Oura Resting Heart Rate",
        icon="mdi:heart",
        value_fn=lambda d: _find_first(_first_item(d.payloads.get("daily_readiness", {}).get("data", [])) or {}, ["contributors","resting_heart_rate"]),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="hr_latest",
        name="Oura Heart Rate (Latest)",
        icon="mdi:heart-pulse",
        value_fn=lambda d: (
            (lambda items: (items[-1] if items and isinstance(items[-1], (int, float)) else (items[-1].get("bpm") if items and isinstance(items[-1], dict) else None)))
            (((_first_item(d.payloads.get("heartrate", {}).get("data", [])) or {}).get("items")))
        ),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="hr_min",
        name="Oura Heart Rate (Min)",
        icon="mdi:heart-outline",
        value_fn=lambda d: (
            (lambda items: min(([i for i in items if isinstance(i, (int, float))] or [i.get("bpm") for i in items if isinstance(i, dict) and "bpm" in i]), default=None))
            (((_first_item(d.payloads.get("heartrate", {}).get("data", [])) or {}).get("items")))
        ),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="hr_max",
        name="Oura Heart Rate (Max)",
        icon="mdi:heart-off",
        value_fn=lambda d: (
            (lambda items: max(([i for i in items if isinstance(i, (int, float))] or [i.get("bpm") for i in items if isinstance(i, dict) and "bpm" in i]), default=None))
            (((_first_item(d.payloads.get("heartrate", {}).get("data", [])) or {}).get("items")))
        ),
        state_class=SensorStateClass.MEASUREMENT,
    ),

    # ---- Workout summary sensors ----
    OuraCalculatedSensorDescription(
        key="workouts_today_count",
        name="Oura Workouts (Today)",
        icon="mdi:run-fast",
        value_fn=lambda d: len(_items_from_payload(d, "workout")),
        group="workout",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="workouts_today_calories",
        name="Oura Workouts Calories (Today)",
        icon="mdi:fire",
        value_fn=lambda d: _sum_calories(_items_from_payload(d, "workout")),
        group="workout",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="kcal",
    ),
    OuraCalculatedSensorDescription(
        key="workout_last_type",
        name="Oura Last Workout Type",
        icon="mdi:weight-lifter",
        value_fn=lambda d: (_last_by_start(_items_from_payload(d, "workout")) or {}).get("type"),
        group="workout",
    ),
    OuraCalculatedSensorDescription(
        key="workout_last_duration_min",
        name="Oura Last Workout Duration",
        icon="mdi:timer-outline",
        value_fn=lambda d: _duration_minutes(_last_by_start(_items_from_payload(d, "workout")) or {}) if _last_by_start(_items_from_payload(d, "workout")) else None,
        group="workout",
        native_unit_of_measurement="min",
        state_class=SensorStateClass.MEASUREMENT,
    ),

    # ---- Session summary sensors ----
    OuraCalculatedSensorDescription(
        key="sessions_today_count",
        name="Oura Sessions (Today)",
        icon="mdi:meditation",
        value_fn=lambda d: len(_items_from_payload(d, "session")),
        group="session",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="sessions_total_duration_min",
        name="Oura Sessions Duration (Today)",
        icon="mdi:timer-sand",
        value_fn=lambda d: _sum_duration_minutes(_items_from_payload(d, "session")),
        group="session",
        native_unit_of_measurement="min",
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="session_last_type",
        name="Oura Last Session Type",
        icon="mdi:head-cog-outline",
        value_fn=lambda d: (_last_by_start(_items_from_payload(d, "session")) or {}).get("type"),
        group="session",
    ),
    OuraCalculatedSensorDescription(
        key="session_last_duration_min",
        name="Oura Last Session Duration",
        icon="mdi:timer-outline",
        value_fn=lambda d: _duration_minutes(_last_by_start(_items_from_payload(d, "session")) or {}) if _last_by_start(_items_from_payload(d, "session")) else None,
        group="session",
        native_unit_of_measurement="min",
        state_class=SensorStateClass.MEASUREMENT,
    ),
]

async def async_setup_entry(hass, entry, async_add_entities):
    coordinator: OuraDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
    device_info = hass.data[DOMAIN][entry.entry_id]["device_info"]
    options = hass.data[DOMAIN][entry.entry_id].get("options", {})
    enable_workout = options.get(CONF_ENABLE_WORKOUT_SUMMARY, True)
    enable_session = options.get(CONF_ENABLE_SESSION_SUMMARY, True)

    def _enabled(desc: OuraCalculatedSensorDescription) -> bool:
        if desc.group == "workout" and not enable_workout:
            return False
        if desc.group == "session" and not enable_session:
            return False
        return True

    descriptions = [d for d in SENSORS if _enabled(d)]
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


# ---- Sleep details (from /usercollection/sleep main period) ----
SENSORS.extend([
    OuraCalculatedSensorDescription(
        key="sleep_total_duration_min",
        name="Oura Sleep Total Duration",
        icon="mdi:sleep",
        native_unit_of_measurement="min",
        value_fn=lambda d: (
            _sec_to_min((_pick_main_sleep((d.payloads.get("sleep", {}) or {}).get("data")) or {}).get("total_sleep_duration"))
        ),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="sleep_time_in_bed_min",
        name="Oura Sleep Time In Bed",
        icon="mdi:bed",
        native_unit_of_measurement="min",
        value_fn=lambda d: (
            _sec_to_min((_pick_main_sleep((d.payloads.get("sleep", {}) or {}).get("data")) or {}).get("time_in_bed"))
        ),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="sleep_latency_min",
        name="Oura Sleep Latency",
        icon="mdi:timer-sand",
        native_unit_of_measurement="min",
        value_fn=lambda d: (
            _sec_to_min((_pick_main_sleep((d.payloads.get("sleep", {}) or {}).get("data")) or {}).get("latency"))
        ),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="sleep_efficiency",
        name="Oura Sleep Efficiency",
        icon="mdi:gauge",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda d: (
            (_pick_main_sleep((d.payloads.get("sleep", {}) or {}).get("data")) or {}).get("efficiency")
        ),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="sleep_deep_duration_min",
        name="Oura Sleep Deep Duration",
        icon="mdi:weather-night",
        native_unit_of_measurement="min",
        value_fn=lambda d: (
            _sec_to_min((_pick_main_sleep((d.payloads.get("sleep", {}) or {}).get("data")) or {}).get("deep_sleep_duration"))
        ),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="sleep_rem_duration_min",
        name="Oura Sleep REM Duration",
        icon="mdi:brain",
        native_unit_of_measurement="min",
        value_fn=lambda d: (
            _sec_to_min((_pick_main_sleep((d.payloads.get("sleep", {}) or {}).get("data")) or {}).get("rem_sleep_duration"))
        ),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="sleep_light_duration_min",
        name="Oura Sleep Light Duration",
        icon="mdi:weather-sunny",
        native_unit_of_measurement="min",
        value_fn=lambda d: (
            _sec_to_min((_pick_main_sleep((d.payloads.get("sleep", {}) or {}).get("data")) or {}).get("light_sleep_duration"))
        ),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="sleep_awake_time_min",
        name="Oura Sleep Awake Time",
        icon="mdi:bell-sleep-outline",
        native_unit_of_measurement="min",
        value_fn=lambda d: (
            _sec_to_min((_pick_main_sleep((d.payloads.get("sleep", {}) or {}).get("data")) or {}).get("awake_time"))
        ),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="sleep_avg_hr",
        name="Oura Sleep Avg HR",
        icon="mdi:heart",
        value_fn=lambda d: (
            (_pick_main_sleep((d.payloads.get("sleep", {}) or {}).get("data")) or {}).get("average_heart_rate")
        ),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="sleep_lowest_hr",
        name="Oura Sleep Lowest HR",
        icon="mdi:heart-outline",
        value_fn=lambda d: (
            (_pick_main_sleep((d.payloads.get("sleep", {}) or {}).get("data")) or {}).get("lowest_heart_rate")
        ),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="sleep_avg_hrv_ms",
        name="Oura Sleep Avg HRV (RMSSD)",
        icon="mdi:waveform",
        native_unit_of_measurement="ms",
        value_fn=lambda d: (
            (_pick_main_sleep((d.payloads.get("sleep", {}) or {}).get("data")) or {}).get("average_hrv")
        ),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="respiratory_rate",
        name="Oura Respiratory Rate",
        icon="mdi:lungs",
        native_unit_of_measurement="breaths/min",
        value_fn=lambda d: (
            (lambda brps: round(brps * 60.0, 2) if isinstance(brps, (int, float)) else None)
            ( (_pick_main_sleep((d.payloads.get("sleep", {}) or {}).get("data")) or {}).get("average_breath") )
        ),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="sleep_restless_periods",
        name="Oura Sleep Restless Periods",
        icon="mdi:sleep-off",
        value_fn=lambda d: (
            (_pick_main_sleep((d.payloads.get("sleep", {}) or {}).get("data")) or {}).get("restless_periods")
        ),
        state_class=SensorStateClass.MEASUREMENT,
    ),
])

# ---- Sleep timestamps (TIMESTAMP device class) ----
SENSORS.extend([
    OuraCalculatedSensorDescription(
        key="bedtime_start",
        name="Oura Bedtime Start",
        icon="mdi:clock-start",
        value_fn=lambda d: (
            (_pick_main_sleep((d.payloads.get("sleep", {}) or {}).get("data")) or {}).get("bedtime_start")
        ),
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
    OuraCalculatedSensorDescription(
        key="bedtime_end",
        name="Oura Bedtime End",
        icon="mdi:clock-end",
        value_fn=lambda d: (
            (_pick_main_sleep((d.payloads.get("sleep", {}) or {}).get("data")) or {}).get("bedtime_end")
        ),
        device_class=SensorDeviceClass.TIMESTAMP,
    ),
])

# ---- Readiness contributors & temperature deviations ----
SENSORS.extend([
    OuraCalculatedSensorDescription(
        key="temperature_deviation_c",
        name="Oura Temperature Deviation",
        icon="mdi:thermometer",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda d: _find_first(_first_item(d.payloads.get("daily_readiness", {}).get("data", [])) or {}, ["temperature_deviation"]),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="temperature_trend_deviation_c",
        name="Oura Temperature Trend Deviation",
        icon="mdi:thermometer-lines",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda d: _find_first(_first_item(d.payloads.get("daily_readiness", {}).get("data", [])) or {}, ["temperature_trend_deviation"]),
        state_class=SensorStateClass.MEASUREMENT,
    ),
])

# Map of readiness contributor keys -> (friendly name, icon)
_readiness_contrib_map = {
    "activity_balance": ("Oura Readiness Activity Balance", "mdi:run"),
    "body_temperature": ("Oura Readiness Body Temperature", "mdi:thermometer"),
    "hrv_balance": ("Oura Readiness HRV Balance", "mdi:heart-pulse"),
    "previous_day_activity": ("Oura Readiness Previous Day Activity", "mdi:history"),
    "previous_night": ("Oura Readiness Previous Night", "mdi:sleep"),
    "recovery_index": ("Oura Readiness Recovery Index", "mdi:battery-heart-variant"),
    "resting_heart_rate": ("Oura Readiness Resting HR (Score)", "mdi:heart"),
    "sleep_balance": ("Oura Readiness Sleep Balance", "mdi:sleep"),
}
for key, (nm, ic) in _readiness_contrib_map.items():
    SENSORS.append(
        OuraCalculatedSensorDescription(
            key=f"readiness_{key}",
            name=nm,
            icon=ic,
            native_unit_of_measurement=PERCENTAGE,
            value_fn=lambda d, k=key: (
                _find_first(_first_item(d.payloads.get("daily_readiness", {}).get("data", [])) or {}, ["contributors", k])
            ),
            state_class=SensorStateClass.MEASUREMENT,
        )
    )

# ---- Sleep contributors (scores 1-100) ----
_sleep_contrib_map = {
    "deep_sleep": ("Oura Sleep Contributor: Deep", "mdi:weather-night"),
    "efficiency": ("Oura Sleep Contributor: Efficiency", "mdi:gauge"),
    "latency": ("Oura Sleep Contributor: Latency", "mdi:timer-sand"),
    "rem_sleep": ("Oura Sleep Contributor: REM", "mdi:brain"),
    "restfulness": ("Oura Sleep Contributor: Restfulness", "mdi:sleep"),
    "timing": ("Oura Sleep Contributor: Timing", "mdi:clock-outline"),
    "total_sleep": ("Oura Sleep Contributor: Total Sleep", "mdi:sleep"),
}
for key, (nm, ic) in _sleep_contrib_map.items():
    SENSORS.append(
        OuraCalculatedSensorDescription(
            key=f"sleep_contrib_{key}",
            name=nm,
            icon=ic,
            native_unit_of_measurement=PERCENTAGE,
            value_fn=lambda d, k=key: (
                _find_first(_first_item(d.payloads.get("daily_sleep", {}).get("data", [])) or {}, ["contributors", k])
            ),
            state_class=SensorStateClass.MEASUREMENT,
        )
    )

# ---- Activity details (from daily_activity) ----
SENSORS.extend([
    OuraCalculatedSensorDescription(
        key="active_calories",
        name="Oura Active Calories",
        icon="mdi:fire",
        native_unit_of_measurement="kcal",
        value_fn=lambda d: _find_first(_first_item(d.payloads.get("daily_activity", {}).get("data", [])) or {}, ["active_calories"]),
        state_class=SensorStateClass.TOTAL,
    ),
    OuraCalculatedSensorDescription(
        key="equivalent_walking_distance_km",
        name="Oura Eq. Walking Distance",
        icon="mdi:walk",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        value_fn=lambda d: _m_to_km(_find_first(_first_item(d.payloads.get("daily_activity", {}).get("data", [])) or {}, ["equivalent_walking_distance"])),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="inactivity_alerts",
        name="Oura Inactivity Alerts",
        icon="mdi:bell",
        value_fn=lambda d: _find_first(_first_item(d.payloads.get("daily_activity", {}).get("data", [])) or {}, ["inactivity_alerts"]),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="non_wear_time_min",
        name="Oura Non-wear Time",
        icon="mdi:watch-off",
        native_unit_of_measurement="min",
        value_fn=lambda d: _sec_to_min(_find_first(_first_item(d.payloads.get("daily_activity", {}).get("data", [])) or {}, ["non_wear_time"])),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="resting_time_min",
        name="Oura Resting Time",
        icon="mdi:sleep",
        native_unit_of_measurement="min",
        value_fn=lambda d: _sec_to_min(_find_first(_first_item(d.payloads.get("daily_activity", {}).get("data", [])) or {}, ["resting_time"])),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="sedentary_time_min",
        name="Oura Sedentary Time",
        icon="mdi:seat-outline",
        native_unit_of_measurement="min",
        value_fn=lambda d: _sec_to_min(_find_first(_first_item(d.payloads.get("daily_activity", {}).get("data", [])) or {}, ["sedentary_time"])),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="average_met_minutes",
        name="Oura Average MET Minutes",
        icon="mdi:chart-line",
        native_unit_of_measurement="min",
        value_fn=lambda d: _find_first(_first_item(d.payloads.get("daily_activity", {}).get("data", [])) or {}, ["average_met_minutes"]),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="low_activity_met_minutes",
        name="Oura Low Activity MET Minutes",
        icon="mdi:walk",
        native_unit_of_measurement="min",
        value_fn=lambda d: _find_first(_first_item(d.payloads.get("daily_activity", {}).get("data", [])) or {}, ["low_activity_met_minutes"]),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="medium_activity_met_minutes",
        name="Oura Medium Activity MET Minutes",
        icon="mdi:run",
        native_unit_of_measurement="min",
        value_fn=lambda d: _find_first(_first_item(d.payloads.get("daily_activity", {}).get("data", [])) or {}, ["medium_activity_met_minutes"]),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="high_activity_met_minutes",
        name="Oura High Activity MET Minutes",
        icon="mdi:run-fast",
        native_unit_of_measurement="min",
        value_fn=lambda d: _find_first(_first_item(d.payloads.get("daily_activity", {}).get("data", [])) or {}, ["high_activity_met_minutes"]),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="low_activity_time_min",
        name="Oura Low Activity Time",
        icon="mdi:walk",
        native_unit_of_measurement="min",
        value_fn=lambda d: _sec_to_min(_find_first(_first_item(d.payloads.get("daily_activity", {}).get("data", [])) or {}, ["low_activity_time"])),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="medium_activity_time_min",
        name="Oura Medium Activity Time",
        icon="mdi:run",
        native_unit_of_measurement="min",
        value_fn=lambda d: _sec_to_min(_find_first(_first_item(d.payloads.get("daily_activity", {}).get("data", [])) or {}, ["medium_activity_time"])),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="high_activity_time_min",
        name="Oura High Activity Time",
        icon="mdi:run-fast",
        native_unit_of_measurement="min",
        value_fn=lambda d: _sec_to_min(_find_first(_first_item(d.payloads.get("daily_activity", {}).get("data", [])) or {}, ["high_activity_time"])),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="target_calories",
        name="Oura Target Calories",
        icon="mdi:target",
        native_unit_of_measurement="kcal",
        value_fn=lambda d: _find_first(_first_item(d.payloads.get("daily_activity", {}).get("data", [])) or {}, ["target_calories"]),
    ),
    OuraCalculatedSensorDescription(
        key="target_meters",
        name="Oura Target Distance",
        icon="mdi:map-marker-distance",
        native_unit_of_measurement="m",
        value_fn=lambda d: _find_first(_first_item(d.payloads.get("daily_activity", {}).get("data", [])) or {}, ["target_meters"]),
    ),
    OuraCalculatedSensorDescription(
        key="meters_to_target",
        name="Oura Meters to Target",
        icon="mdi:map-marker-distance",
        native_unit_of_measurement="m",
        value_fn=lambda d: _find_first(_first_item(d.payloads.get("daily_activity", {}).get("data", [])) or {}, ["meters_to_target"]),
    ),
])

# ---- Activity contributors (scores 1-100) ----
_activity_contrib_map = {
    "meet_daily_targets": ("Oura Activity: Meet Daily Targets", "mdi:target-account"),
    "move_every_hour": ("Oura Activity: Move Every Hour", "mdi:run-fast"),
    "recovery_time": ("Oura Activity: Recovery Time", "mdi:bed-clock"),
    "stay_active": ("Oura Activity: Stay Active", "mdi:walk"),
    "training_frequency": ("Oura Activity: Training Frequency", "mdi:calendar-clock"),
    "training_volume": ("Oura Activity: Training Volume", "mdi:weight-lifter"),
}
for key, (nm, ic) in _activity_contrib_map.items():
    SENSORS.append(
        OuraCalculatedSensorDescription(
            key=f"activity_contrib_{key}",
            name=nm,
            icon=ic,
            native_unit_of_measurement=PERCENTAGE,
            value_fn=lambda d, k=key: (
                _find_first(_first_item(d.payloads.get("daily_activity", {}).get("data", [])) or {}, ["contributors", k])
            ),
            state_class=SensorStateClass.MEASUREMENT,
        )
    )

# ---- SpO2 (make sure we read nested .spo2_percentage.average if present) ----
SENSORS.append(
    OuraCalculatedSensorDescription(
        key="spo2_avg_nightly",
        name="Oura SpO2 Average (Night)",
        icon="mdi:blood-bag",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda d: (
            (lambda obj: (obj.get("average") if isinstance(obj, dict) else obj))
            (_find_first(_first_item(d.payloads.get("daily_spo2", {}).get("data", [])) or {}, ["spo2_percentage"]))
        ),
        state_class=SensorStateClass.MEASUREMENT,
    )
)
