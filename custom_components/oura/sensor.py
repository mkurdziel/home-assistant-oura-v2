from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Dict, Optional

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfLength, UnitOfTemperature
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import OuraData
from .data import (
    bedtime,
    collection_items,
    latest_battery,
    latest_ring,
    latest_tag,
    tag_label,
    today_calories,
    today_count,
    today_duration,
)
from .data import (
    daily_latest as _daily_latest,
)
from .data import (
    duration_minutes as _duration_minutes,
)
from .data import (
    iso_parse as _iso_parse,
)
from .data import (
    last_by_time as _last_by_time,
)
from .data import (
    sleep_latest as _sleep_latest,
)


def _find_first(data, path, default=None):
    for key in path:
        if not isinstance(data, dict) or key not in data:
            return default
        data = data[key]
    return data


def _min_from_seconds(value):
    return round(value / 60, 2) if isinstance(value, (int, float)) else None


# ---------- entity description ----------
@dataclass(frozen=True, kw_only=True)
class OuraCalculatedSensorDescription(SensorEntityDescription):
    collection: str = ""
    value_fn: Callable[[OuraData], Any] | None = None
    attr_fn: Callable[[OuraData], Dict[str, Any]] | None = None


SENSORS: list[OuraCalculatedSensorDescription] = [
    # Scores
    OuraCalculatedSensorDescription(
        key="readiness_score",
        name="Oura V2 Readiness Score",
        icon="mdi:arm-flex",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda d: _find_first(_daily_latest(d, "daily_readiness"), ["score"]),
        attr_fn=lambda d: _daily_latest(d, "daily_readiness").get("contributors", {}),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="sleep_score",
        name="Oura V2 Sleep Score",
        icon="mdi:sleep",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda d: _find_first(_daily_latest(d, "daily_sleep"), ["score"]),
        attr_fn=lambda d: _daily_latest(d, "daily_sleep").get("contributors", {}),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="activity_score",
        name="Oura V2 Activity Score",
        icon="mdi:run",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda d: _find_first(_daily_latest(d, "daily_activity"), ["score"]),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Activity totals
    OuraCalculatedSensorDescription(
        key="steps",
        name="Oura V2 Steps",
        icon="mdi:walk",
        value_fn=lambda d: _find_first(_daily_latest(d, "daily_activity"), ["steps"]),
        state_class=SensorStateClass.TOTAL,
    ),
    OuraCalculatedSensorDescription(
        key="total_calories",
        native_unit_of_measurement="kcal",
        name="Oura V2 Total Calories",
        icon="mdi:fire",
        value_fn=lambda d: _find_first(_daily_latest(d, "daily_activity"), ["total_calories"]),
        state_class=SensorStateClass.TOTAL,
    ),
    # SpO2
    OuraCalculatedSensorDescription(
        key="spo2_avg",
        name="Oura V2 SpO2 Average",
        icon="mdi:blood-bag",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda d: _find_first(
            _daily_latest(d, "daily_spo2"), ["spo2_percentage", "average"]
        ),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # HR (resting mapped to nightly lowest)
    OuraCalculatedSensorDescription(
        key="resting_heart_rate",
        native_unit_of_measurement="bpm",
        name="Oura V2 Resting Heart Rate",
        icon="mdi:heart",
        value_fn=lambda d: _find_first((_sleep_latest(d) or {}), ["lowest_heart_rate"]),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # HR time-series
    OuraCalculatedSensorDescription(
        key="hr_latest",
        native_unit_of_measurement="bpm",
        name="Oura V2 Heart Rate (Latest)",
        icon="mdi:heart-pulse",
        value_fn=lambda d: (_last_by_time(collection_items(d, "heartrate"), "timestamp") or {}).get(
            "bpm"
        ),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="hr_min",
        native_unit_of_measurement="bpm",
        name="Oura V2 Heart Rate (Min)",
        icon="mdi:heart-outline",
        value_fn=lambda d: min(
            (
                x["bpm"]
                for x in collection_items(d, "heartrate") or []
                if isinstance(x.get("bpm"), (int, float))
            ),
            default=None,
        ),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="hr_max",
        native_unit_of_measurement="bpm",
        name="Oura V2 Heart Rate (Max)",
        icon="mdi:heart-off",
        value_fn=lambda d: max(
            (
                x["bpm"]
                for x in collection_items(d, "heartrate") or []
                if isinstance(x.get("bpm"), (int, float))
            ),
            default=None,
        ),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Stress / resilience
    OuraCalculatedSensorDescription(
        key="stress_recovery_high",
        name="Oura V2 Recovery High (Daily)",
        icon="mdi:meditation",
        native_unit_of_measurement="min",
        value_fn=lambda d: _min_from_seconds(
            _find_first(_daily_latest(d, "daily_stress"), ["recovery_high"])
        ),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="stress_high",
        name="Oura V2 Stress High (Daily)",
        icon="mdi:chart-timeline-variant",
        native_unit_of_measurement="min",
        value_fn=lambda d: _min_from_seconds(
            _find_first(_daily_latest(d, "daily_stress"), ["stress_high"])
        ),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="resilience_level",
        name="Oura V2 Resilience Level",
        icon="mdi:shield-heart",
        value_fn=lambda d: _find_first(_daily_latest(d, "daily_resilience"), ["level"]),
    ),
]

# Sleep details
SENSORS.extend(
    [
        OuraCalculatedSensorDescription(
            key="sleep_total_duration_min",
            name="Oura V2 Sleep Total Duration",
            icon="mdi:sleep",
            native_unit_of_measurement="min",
            value_fn=lambda d: _min_from_seconds(
                (_sleep_latest(d) or {}).get("total_sleep_duration")
            ),
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
            value_fn=lambda d: _min_from_seconds(
                (_sleep_latest(d) or {}).get("deep_sleep_duration")
            ),
            state_class=SensorStateClass.MEASUREMENT,
        ),
        OuraCalculatedSensorDescription(
            key="sleep_rem_min",
            name="Oura V2 REM Sleep",
            icon="mdi:moon-waxing-crescent",
            native_unit_of_measurement="min",
            value_fn=lambda d: _min_from_seconds(
                (_sleep_latest(d) or {}).get("rem_sleep_duration")
            ),
            state_class=SensorStateClass.MEASUREMENT,
        ),
        OuraCalculatedSensorDescription(
            key="sleep_light_min",
            name="Oura V2 Light Sleep",
            icon="mdi:weather-night",
            native_unit_of_measurement="min",
            value_fn=lambda d: _min_from_seconds(
                (_sleep_latest(d) or {}).get("light_sleep_duration")
            ),
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
    ]
)

# Readiness contributors & temperatures
SENSORS.extend(
    [
        OuraCalculatedSensorDescription(
            key="readiness_temp_deviation",
            name="Oura V2 Temperature Deviation",
            icon="mdi:thermometer",
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            value_fn=lambda d: _find_first(
                _daily_latest(d, "daily_readiness"), ["temperature_deviation"]
            ),
            state_class=SensorStateClass.MEASUREMENT,
        ),
        OuraCalculatedSensorDescription(
            key="readiness_temp_trend_deviation",
            name="Oura V2 Temperature Trend Deviation",
            icon="mdi:thermometer-lines",
            native_unit_of_measurement=UnitOfTemperature.CELSIUS,
            value_fn=lambda d: _find_first(
                _daily_latest(d, "daily_readiness"), ["temperature_trend_deviation"]
            ),
            state_class=SensorStateClass.MEASUREMENT,
        ),
        OuraCalculatedSensorDescription(
            key="readiness_hrv_balance",
            name="Oura V2 Readiness HRV Balance",
            icon="mdi:heart-pulse",
            value_fn=lambda d: _find_first(
                _daily_latest(d, "daily_readiness"), ["contributors", "hrv_balance"]
            ),
            state_class=SensorStateClass.MEASUREMENT,
        ),
        OuraCalculatedSensorDescription(
            key="readiness_sleep_balance",
            name="Oura V2 Readiness Sleep Balance",
            icon="mdi:sleep",
            value_fn=lambda d: _find_first(
                _daily_latest(d, "daily_readiness"), ["contributors", "sleep_balance"]
            ),
            state_class=SensorStateClass.MEASUREMENT,
        ),
        OuraCalculatedSensorDescription(
            key="readiness_activity_balance",
            name="Oura V2 Readiness Activity Balance",
            icon="mdi:run",
            value_fn=lambda d: _find_first(
                _daily_latest(d, "daily_readiness"), ["contributors", "activity_balance"]
            ),
            state_class=SensorStateClass.MEASUREMENT,
        ),
        OuraCalculatedSensorDescription(
            key="readiness_previous_day_activity",
            name="Oura V2 Readiness Previous Day Activity",
            icon="mdi:walk",
            value_fn=lambda d: _find_first(
                _daily_latest(d, "daily_readiness"), ["contributors", "previous_day_activity"]
            ),
            state_class=SensorStateClass.MEASUREMENT,
        ),
        OuraCalculatedSensorDescription(
            key="readiness_previous_night",
            name="Oura V2 Readiness Previous Night",
            icon="mdi:weather-night",
            value_fn=lambda d: _find_first(
                _daily_latest(d, "daily_readiness"), ["contributors", "previous_night"]
            ),
            state_class=SensorStateClass.MEASUREMENT,
        ),
        OuraCalculatedSensorDescription(
            key="readiness_recovery_index",
            name="Oura V2 Readiness Recovery Index",
            icon="mdi:calendar-refresh",
            value_fn=lambda d: _find_first(
                _daily_latest(d, "daily_readiness"), ["contributors", "recovery_index"]
            ),
            state_class=SensorStateClass.MEASUREMENT,
        ),
        OuraCalculatedSensorDescription(
            key="readiness_body_temperature_contrib",
            name="Oura V2 Readiness Body Temperature (Contributor)",
            icon="mdi:thermometer",
            value_fn=lambda d: _find_first(
                _daily_latest(d, "daily_readiness"), ["contributors", "body_temperature"]
            ),
            state_class=SensorStateClass.MEASUREMENT,
        ),
    ]
)

# Activity details & contributors
SENSORS.extend(
    [
        OuraCalculatedSensorDescription(
            key="activity_active_calories",
            native_unit_of_measurement="kcal",
            name="Oura V2 Active Calories",
            icon="mdi:fire",
            value_fn=lambda d: _find_first(_daily_latest(d, "daily_activity"), ["active_calories"]),
            state_class=SensorStateClass.TOTAL,
        ),
        OuraCalculatedSensorDescription(
            key="activity_average_met_minutes",
            name="Oura V2 Average MET Minutes",
            icon="mdi:clock-outline",
            native_unit_of_measurement="min",
            value_fn=lambda d: _find_first(
                _daily_latest(d, "daily_activity"), ["average_met_minutes"]
            ),
            state_class=SensorStateClass.MEASUREMENT,
        ),
        OuraCalculatedSensorDescription(
            key="activity_equivalent_walking_distance_m",
            name="Oura V2 Equivalent Walking Distance",
            icon="mdi:map-marker-distance",
            native_unit_of_measurement=UnitOfLength.METERS,
            value_fn=lambda d: _find_first(
                _daily_latest(d, "daily_activity"), ["equivalent_walking_distance"]
            ),
            state_class=SensorStateClass.MEASUREMENT,
        ),
        OuraCalculatedSensorDescription(
            key="activity_high_activity_met_minutes",
            name="Oura V2 High Activity MET Minutes",
            icon="mdi:lightning-bolt",
            native_unit_of_measurement="min",
            value_fn=lambda d: _find_first(
                _daily_latest(d, "daily_activity"), ["high_activity_met_minutes"]
            ),
            state_class=SensorStateClass.MEASUREMENT,
        ),
        OuraCalculatedSensorDescription(
            key="activity_high_activity_time_min",
            name="Oura V2 High Activity Time",
            icon="mdi:timer",
            native_unit_of_measurement="min",
            value_fn=lambda d: _min_from_seconds(
                _find_first(_daily_latest(d, "daily_activity"), ["high_activity_time"])
            ),
            state_class=SensorStateClass.MEASUREMENT,
        ),
        OuraCalculatedSensorDescription(
            key="activity_inactivity_alerts",
            name="Oura V2 Inactivity Alerts",
            icon="mdi:bell-alert",
            value_fn=lambda d: _find_first(
                _daily_latest(d, "daily_activity"), ["inactivity_alerts"]
            ),
            state_class=SensorStateClass.MEASUREMENT,
        ),
        OuraCalculatedSensorDescription(
            key="activity_low_activity_met_minutes",
            name="Oura V2 Low Activity MET Minutes",
            icon="mdi:chevron-down",
            native_unit_of_measurement="min",
            value_fn=lambda d: _find_first(
                _daily_latest(d, "daily_activity"), ["low_activity_met_minutes"]
            ),
            state_class=SensorStateClass.MEASUREMENT,
        ),
        OuraCalculatedSensorDescription(
            key="activity_low_activity_time_min",
            name="Oura V2 Low Activity Time",
            icon="mdi:timer-sand",
            native_unit_of_measurement="min",
            value_fn=lambda d: _min_from_seconds(
                _find_first(_daily_latest(d, "daily_activity"), ["low_activity_time"])
            ),
            state_class=SensorStateClass.MEASUREMENT,
        ),
        OuraCalculatedSensorDescription(
            key="activity_medium_activity_met_minutes",
            name="Oura V2 Medium Activity MET Minutes",
            icon="mdi:swap-vertical",
            native_unit_of_measurement="min",
            value_fn=lambda d: _find_first(
                _daily_latest(d, "daily_activity"), ["medium_activity_met_minutes"]
            ),
            state_class=SensorStateClass.MEASUREMENT,
        ),
        OuraCalculatedSensorDescription(
            key="activity_medium_activity_time_min",
            name="Oura V2 Medium Activity Time",
            icon="mdi:timer-outline",
            native_unit_of_measurement="min",
            value_fn=lambda d: _min_from_seconds(
                _find_first(_daily_latest(d, "daily_activity"), ["medium_activity_time"])
            ),
            state_class=SensorStateClass.MEASUREMENT,
        ),
        OuraCalculatedSensorDescription(
            key="activity_meters_to_target",
            name="Oura V2 Meters To Target",
            icon="mdi:target-variant",
            native_unit_of_measurement=UnitOfLength.METERS,
            value_fn=lambda d: _find_first(
                _daily_latest(d, "daily_activity"), ["meters_to_target"]
            ),
            state_class=SensorStateClass.MEASUREMENT,
        ),
        OuraCalculatedSensorDescription(
            key="activity_non_wear_time_min",
            name="Oura V2 Non-wear Time",
            icon="mdi:ring",
            native_unit_of_measurement="min",
            value_fn=lambda d: _min_from_seconds(
                _find_first(_daily_latest(d, "daily_activity"), ["non_wear_time"])
            ),
            state_class=SensorStateClass.MEASUREMENT,
        ),
        OuraCalculatedSensorDescription(
            key="activity_resting_time_min",
            name="Oura V2 Resting Time",
            icon="mdi:sleep",
            native_unit_of_measurement="min",
            value_fn=lambda d: _min_from_seconds(
                _find_first(_daily_latest(d, "daily_activity"), ["resting_time"])
            ),
            state_class=SensorStateClass.MEASUREMENT,
        ),
        OuraCalculatedSensorDescription(
            key="activity_sedentary_met_minutes",
            name="Oura V2 Sedentary MET Minutes",
            icon="mdi:chair-rolling",
            native_unit_of_measurement="min",
            value_fn=lambda d: _find_first(
                _daily_latest(d, "daily_activity"), ["sedentary_met_minutes"]
            ),
            state_class=SensorStateClass.MEASUREMENT,
        ),
        OuraCalculatedSensorDescription(
            key="activity_sedentary_time_min",
            name="Oura V2 Sedentary Time",
            icon="mdi:sofa",
            native_unit_of_measurement="min",
            value_fn=lambda d: _min_from_seconds(
                _find_first(_daily_latest(d, "daily_activity"), ["sedentary_time"])
            ),
            state_class=SensorStateClass.MEASUREMENT,
        ),
        OuraCalculatedSensorDescription(
            key="activity_target_calories",
            native_unit_of_measurement="kcal",
            name="Oura V2 Target Calories",
            icon="mdi:bullseye",
            value_fn=lambda d: _find_first(_daily_latest(d, "daily_activity"), ["target_calories"]),
            state_class=SensorStateClass.MEASUREMENT,
        ),
        OuraCalculatedSensorDescription(
            key="activity_target_meters",
            name="Oura V2 Target Meters",
            icon="mdi:bullseye-arrow",
            native_unit_of_measurement=UnitOfLength.METERS,
            value_fn=lambda d: _find_first(_daily_latest(d, "daily_activity"), ["target_meters"]),
            state_class=SensorStateClass.MEASUREMENT,
        ),
        # Contributors
        OuraCalculatedSensorDescription(
            key="activity_contrib_meet_daily_targets",
            name="Oura V2 Activity Contributor: Meet Daily Targets",
            icon="mdi:target",
            value_fn=lambda d: _find_first(
                _daily_latest(d, "daily_activity"), ["contributors", "meet_daily_targets"]
            ),
            state_class=SensorStateClass.MEASUREMENT,
        ),
        OuraCalculatedSensorDescription(
            key="activity_contrib_move_every_hour",
            name="Oura V2 Activity Contributor: Move Every Hour",
            icon="mdi:timer-cog",
            value_fn=lambda d: _find_first(
                _daily_latest(d, "daily_activity"), ["contributors", "move_every_hour"]
            ),
            state_class=SensorStateClass.MEASUREMENT,
        ),
        OuraCalculatedSensorDescription(
            key="activity_contrib_recovery_time",
            name="Oura V2 Activity Contributor: Recovery Time",
            icon="mdi:progress-clock",
            value_fn=lambda d: _find_first(
                _daily_latest(d, "daily_activity"), ["contributors", "recovery_time"]
            ),
            state_class=SensorStateClass.MEASUREMENT,
        ),
        OuraCalculatedSensorDescription(
            key="activity_contrib_stay_active",
            name="Oura V2 Activity Contributor: Stay Active",
            icon="mdi:run-fast",
            value_fn=lambda d: _find_first(
                _daily_latest(d, "daily_activity"), ["contributors", "stay_active"]
            ),
            state_class=SensorStateClass.MEASUREMENT,
        ),
        OuraCalculatedSensorDescription(
            key="activity_contrib_training_frequency",
            name="Oura V2 Activity Contributor: Training Frequency",
            icon="mdi:calendar-check",
            value_fn=lambda d: _find_first(
                _daily_latest(d, "daily_activity"), ["contributors", "training_frequency"]
            ),
            state_class=SensorStateClass.MEASUREMENT,
        ),
        OuraCalculatedSensorDescription(
            key="activity_contrib_training_volume",
            name="Oura V2 Activity Contributor: Training Volume",
            icon="mdi:dumbbell",
            value_fn=lambda d: _find_first(
                _daily_latest(d, "daily_activity"), ["contributors", "training_volume"]
            ),
            state_class=SensorStateClass.MEASUREMENT,
        ),
    ]
)

# Vitals
SENSORS.extend(
    [
        OuraCalculatedSensorDescription(
            key="spo2_breathing_disturbance_index",
            name="Oura V2 Breathing Disturbance Index",
            icon="mdi:lungs",
            value_fn=lambda d: _find_first(
                _daily_latest(d, "daily_spo2"), ["breathing_disturbance_index"]
            ),
            state_class=SensorStateClass.MEASUREMENT,
        ),
    ]
)

# Optional extras
SENSORS.extend(
    [
        OuraCalculatedSensorDescription(
            key="vo2_max",
            name="Oura V2 VO2 Max",
            icon="mdi:lungs",
            value_fn=lambda d: _find_first(_daily_latest(d, "vo2max"), ["vo2_max"]),
            state_class=SensorStateClass.MEASUREMENT,
        ),
        OuraCalculatedSensorDescription(
            key="cardiovascular_age",
            name="Oura V2 Cardiovascular Age",
            icon="mdi:heart-cog",
            value_fn=lambda d: _find_first(
                _daily_latest(d, "daily_cardiovascular_age"), ["vascular_age"]
            ),
            state_class=SensorStateClass.MEASUREMENT,
        ),
    ]
)

# Workouts & Sessions summaries
SENSORS.extend(
    [
        OuraCalculatedSensorDescription(
            key="workouts_today_count",
            name="Oura V2 Workouts Today",
            icon="mdi:arm-flex",
            value_fn=lambda d: today_count(d, "workout"),
            state_class=SensorStateClass.MEASUREMENT,
        ),
        OuraCalculatedSensorDescription(
            key="workouts_today_duration_min",
            name="Oura V2 Workouts Duration Today",
            icon="mdi:timer",
            native_unit_of_measurement="min",
            value_fn=lambda d: today_duration(d, "workout"),
            state_class=SensorStateClass.MEASUREMENT,
        ),
        OuraCalculatedSensorDescription(
            key="workouts_today_calories",
            native_unit_of_measurement="kcal",
            name="Oura V2 Workouts Calories Today",
            icon="mdi:fire",
            value_fn=lambda d: today_calories(d),
            state_class=SensorStateClass.TOTAL,
        ),
        OuraCalculatedSensorDescription(
            key="last_workout",
            name="Oura V2 Last Workout",
            icon="mdi:run",
            value_fn=lambda d: (lambda w: (w or {}).get("activity"))(
                _last_by_time(((d.payloads.get("workout", {}) or {}).get("data")))
            ),
            attr_fn=lambda d: (
                lambda w: (
                    {
                        "activity": w.get("activity"),
                        "label": w.get("label"),
                        "intensity": w.get("intensity"),
                        "calories": w.get("calories"),
                        "distance": w.get("distance"),
                        "source": w.get("source"),
                        "start": w.get("start_datetime"),
                        "end": w.get("end_datetime"),
                        "duration_min": _duration_minutes(
                            w.get("start_datetime"), w.get("end_datetime")
                        ),
                        "day": w.get("day"),
                        "id": w.get("id"),
                    }
                    if isinstance(w, dict)
                    else {}
                )
            )(_last_by_time(((d.payloads.get("workout", {}) or {}).get("data")))),
        ),
        OuraCalculatedSensorDescription(
            key="sessions_today_count",
            name="Oura V2 Sessions Today",
            icon="mdi:meditation",
            value_fn=lambda d: today_count(d, "session"),
            state_class=SensorStateClass.MEASUREMENT,
        ),
        OuraCalculatedSensorDescription(
            key="sessions_today_duration_min",
            name="Oura V2 Sessions Duration Today",
            icon="mdi:timer-outline",
            native_unit_of_measurement="min",
            value_fn=lambda d: today_duration(d, "session"),
            state_class=SensorStateClass.MEASUREMENT,
        ),
        OuraCalculatedSensorDescription(
            key="last_session",
            name="Oura V2 Last Session",
            icon="mdi:meditation",
            value_fn=lambda d: (lambda s: (s or {}).get("type"))(
                _last_by_time(((d.payloads.get("session", {}) or {}).get("data")))
            ),
            attr_fn=lambda d: (
                lambda s: (
                    {
                        "type": s.get("type"),
                        "mood": s.get("mood"),
                        "start": s.get("start_datetime"),
                        "end": s.get("end_datetime"),
                        "duration_min": _duration_minutes(
                            s.get("start_datetime"), s.get("end_datetime")
                        ),
                        "day": s.get("day"),
                        "id": s.get("id"),
                    }
                    if isinstance(s, dict)
                    else {}
                )
            )(_last_by_time(((d.payloads.get("session", {}) or {}).get("data")))),
        ),
    ]
)

# Sleep time recommendations and simple tags
SENSORS.extend(
    [
        OuraCalculatedSensorDescription(
            key="optimal_bedtime_start",
            name="Oura V2 Optimal Bedtime Start",
            icon="mdi:bed-clock",
            device_class=SensorDeviceClass.TIMESTAMP,
            value_fn=lambda d: bedtime(d, "start"),
            attr_fn=lambda d: _daily_latest(d, "sleep_time").get("optimal_bedtime", {}),
        ),
        OuraCalculatedSensorDescription(
            key="optimal_bedtime_end",
            name="Oura V2 Optimal Bedtime End",
            icon="mdi:bed-clock-outline",
            device_class=SensorDeviceClass.TIMESTAMP,
            value_fn=lambda d: bedtime(d, "end"),
        ),
        OuraCalculatedSensorDescription(
            key="bedtime_recommendation_status",
            name="Oura V2 Bedtime Recommendation Status",
            icon="mdi:check-circle",
            value_fn=lambda d: _find_first(_daily_latest(d, "sleep_time"), ["status"]),
        ),
        OuraCalculatedSensorDescription(
            key="latest_tag",
            name="Oura V2 Latest Tag",
            icon="mdi:tag-text",
            value_fn=lambda d: tag_label(d),
            attr_fn=lambda d: latest_tag(d),
        ),
        OuraCalculatedSensorDescription(
            key="today_tags_count",
            name="Oura V2 Tags Today Count",
            icon="mdi:tag-multiple",
            value_fn=lambda d: today_count(d, "tag"),
            state_class=SensorStateClass.MEASUREMENT,
        ),
    ]
)

# These are additional entities; established entity keys are deliberately retained.
SENSORS.extend(
    [
        OuraCalculatedSensorDescription(
            key="ring_battery",
            name="Oura V2 Ring Battery",
            collection="ring_battery_level",
            device_class=SensorDeviceClass.BATTERY,
            native_unit_of_measurement=PERCENTAGE,
            state_class=SensorStateClass.MEASUREMENT,
            value_fn=lambda d: latest_battery(d).get("level"),
            attr_fn=lambda d: {"sample_time": latest_battery(d).get("timestamp")},
        ),
        OuraCalculatedSensorDescription(
            key="latest_enhanced_tag",
            name="Oura V2 Latest Enhanced Tag",
            collection="enhanced_tag",
            icon="mdi:tag-text",
            value_fn=lambda d: tag_label(d, True),
            attr_fn=lambda d: latest_tag(d, True),
        ),
        OuraCalculatedSensorDescription(
            key="enhanced_tags_today_count",
            name="Oura V2 Enhanced Tags Today",
            collection="enhanced_tag",
            icon="mdi:tag-multiple",
            value_fn=lambda d: today_count(d, "enhanced_tag", "start_day"),
            state_class=SensorStateClass.MEASUREMENT,
        ),
        OuraCalculatedSensorDescription(
            key="ring_firmware",
            name="Oura V2 Ring Firmware",
            collection="ring_configuration",
            icon="mdi:chip",
            value_fn=lambda d: latest_ring(d).get("firmware_version"),
            entity_category=EntityCategory.DIAGNOSTIC,
            attr_fn=lambda d: {
                key: latest_ring(d).get(key)
                for key in ("hardware_type", "color", "design", "size", "set_up_at")
            },
        ),
        OuraCalculatedSensorDescription(
            key="readiness_sleep_regularity",
            name="Oura V2 Readiness Sleep Regularity",
            collection="daily_readiness",
            icon="mdi:sleep",
            value_fn=lambda d: _find_first(
                _daily_latest(d, "daily_readiness"), ["contributors", "sleep_regularity"]
            ),
            state_class=SensorStateClass.MEASUREMENT,
        ),
    ]
)


def _collection_for(key: str) -> str:
    exact = {
        "readiness_score": "daily_readiness",
        "sleep_score": "daily_sleep",
        "activity_score": "daily_activity",
        "steps": "daily_activity",
        "total_calories": "daily_activity",
        "resting_heart_rate": "sleep",
        "vo2_max": "vo2max",
        "cardiovascular_age": "daily_cardiovascular_age",
        "optimal_bedtime_start": "sleep_time",
        "optimal_bedtime_end": "sleep_time",
        "bedtime_recommendation_status": "sleep_time",
        "latest_tag": "tag",
        "today_tags_count": "tag",
        "last_workout": "workout",
        "last_session": "session",
    }
    if key in exact:
        return exact[key]
    for prefix, collection in (
        ("sleep_", "sleep"),
        ("readiness_", "daily_readiness"),
        ("activity_", "daily_activity"),
        ("spo2_", "daily_spo2"),
        ("hr_", "heartrate"),
        ("stress_", "daily_stress"),
        ("resilience_", "daily_resilience"),
        ("workouts_", "workout"),
        ("sessions_", "session"),
    ):
        if key.startswith(prefix):
            return collection
    raise ValueError(f"No Oura collection for {key}")


async def async_setup_entry(hass, entry, async_add_entities):
    runtime = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            OuraCalculatedSensor(
                runtime["coordinator"], desc, runtime["device_info"], runtime["uid_prefix"]
            )
            for desc in SENSORS
        ]
    )


class OuraCalculatedSensor(CoordinatorEntity[OuraData], SensorEntity):
    entity_description: OuraCalculatedSensorDescription

    def __init__(self, coordinator, description, device_info, uid_prefix):
        super().__init__(coordinator)
        self.entity_description = description
        self.collection = description.collection or _collection_for(description.key)
        self._attr_unique_id = f"{uid_prefix}_{description.key}"
        self._attr_device_info = device_info

    @property
    def available(self):
        data = self.coordinator.data
        return (
            super().available
            and data is not None
            and self.collection in data.payloads
            and self.collection not in data.unavailable
        )

    @property
    def native_value(self):
        if self.available and self.entity_description.value_fn:
            return self.entity_description.value_fn(self.coordinator.data)
        return None

    @property
    def extra_state_attributes(self) -> Optional[Dict[str, Any]]:
        if not self.available:
            return {}
        data = self.coordinator.data
        attrs = self.entity_description.attr_fn(data) if self.entity_description.attr_fn else {}
        attrs = dict(attrs or {})
        record = (
            _sleep_latest(data)
            if self.collection == "sleep"
            else _daily_latest(data, self.collection)
        )
        if record and record.get("day"):
            attrs["source_day"] = record["day"]
        if self.collection == "heartrate":
            attrs["sample_time"] = (
                _last_by_time(collection_items(data, "heartrate"), "timestamp") or {}
            ).get("timestamp")
        return attrs
