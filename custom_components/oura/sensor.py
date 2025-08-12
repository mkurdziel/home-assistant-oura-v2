
from __future__ import annotations

from typing import Any, Callable
import logging

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers import config_entry_oauth2_flow

from .const import DOMAIN
from .coordinator import OuraCoordinator
from .ouraclient import OuraClient

_LOGGER = logging.getLogger(__name__)


def _last_record(dic: dict[str, Any]) -> dict[str, Any] | None:
    if isinstance(dic, dict):
        data = dic.get("data") or []
        if data:
            return data[-1]
    return None


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up Oura sensors for a config entry."""
    implementation = await config_entry_oauth2_flow.async_get_config_entry_implementation(hass, entry.data)
    session = config_entry_oauth2_flow.OAuth2Session(hass, entry.data, implementation)
    client = OuraClient(hass, session)

    user = await client.async_get_personal_info()
    uid = user.get("id") or user.get("user_id") or "oura"
    owner = user.get("email") or user.get("name") or "Oura User"

    coordinator = OuraCoordinator(hass, entry, session, bearer_token=None)
    await coordinator.async_config_entry_first_refresh()

    entities: list[SensorEntity] = []

    def add_simple(name: str, key: str, unit: str = "", device_class: SensorDeviceClass | None = None):
        entities.append(
            OuraComputedSensor(
                coordinator,
                uid,
                owner,
                name,
                key,
                unit=unit,
                device_class=device_class,
                state_class=SensorStateClass.MEASUREMENT,
                compute=lambda data: data.get(key),
            )
        )

    # Readiness
    def readiness_compute(field: str) -> Callable[[dict[str, Any]], Any]:
        def inner(data: dict[str, Any]) -> Any:
            rec = _last_record(data.get("daily_readiness", {}))
            return None if rec is None else rec.get(field)
        return inner

    entities.append(
        OuraComputedSensor(coordinator, uid, owner, "Readiness Score", "readiness_score", state_class=SensorStateClass.MEASUREMENT,
                           compute=readiness_compute("score"))
    )
    entities.append(
        OuraComputedSensor(coordinator, uid, owner, "Temperature Deviation", "temperature_deviation", unit="°C",
                           device_class=SensorDeviceClass.TEMPERATURE, state_class=SensorStateClass.MEASUREMENT,
                           compute=readiness_compute("temperature_deviation"))
    )
    entities.append(
        OuraComputedSensor(coordinator, uid, owner, "Temperature Trend Deviation", "temperature_trend_deviation", unit="°C",
                           device_class=SensorDeviceClass.TEMPERATURE, state_class=SensorStateClass.MEASUREMENT,
                           compute=readiness_compute("temperature_trend_deviation"))
    )

    # Daily Sleep
    def sleep_compute(field: str) -> Callable[[dict[str, Any]], Any]:
        def inner(data: dict[str, Any]) -> Any:
            rec = _last_record(data.get("daily_sleep", {}))
            return None if rec is None else rec.get(field)
        return inner

    entities.append(
        OuraComputedSensor(coordinator, uid, owner, "Sleep Score", "sleep_score", state_class=SensorStateClass.MEASUREMENT,
                           compute=sleep_compute("score"))
    )

    for field, friendly, unit in [
        ("total_sleep_duration", "Total Sleep (min)", "min"),
        ("time_in_bed", "Time In Bed (min)", "min"),
        ("deep_sleep_duration", "Deep Sleep (min)", "min"),
        ("rem_sleep_duration", "REM Sleep (min)", "min"),
        ("light_sleep_duration", "Light Sleep (min)", "min"),
        ("awake_time", "Awake Time (min)", "min"),
        ("sleep_latency", "Sleep Latency (min)", "min"),
        ("sleep_efficiency", "Sleep Efficiency", ""),
        ("average_respiratory_rate", "Respiratory Rate", "breaths/min"),
        ("average_hrv", "HRV (RMSSD)", "ms"),
        ("lowest_heart_rate", "Resting HR (lowest)", "bpm"),
    ]:
        entities.append(
            OuraComputedSensor(coordinator, uid, owner, friendly, field, unit=unit,
                               state_class=SensorStateClass.MEASUREMENT, compute=sleep_compute(field))
        )

    # Daily Activity
    def act_compute(field: str) -> Callable[[dict[str, Any]], Any]:
        def inner(data: dict[str, Any]) -> Any:
            rec = _last_record(data.get("daily_activity", {}))
            return None if rec is None else rec.get(field)
        return inner

    for field, friendly, unit in [
        ("score", "Activity Score", ""),
        ("steps", "Steps", "steps"),
        ("cal_total", "Calories (total)", "kcal"),
        ("cal_active", "Calories (active)", "kcal"),
        ("met_min_inactive", "MET min (inactive)", "min"),
        ("met_min_low", "MET min (low)", "min"),
        ("met_min_medium", "MET min (medium)", "min"),
        ("met_min_high", "MET min (high)", "min"),
        ("daily_movement", "Daily Movement", ""),
        ("sedentary_time", "Sedentary Time (min)", "min"),
        ("non_wear_time", "Non-wear Time (min)", "min"),
        ("target_calories", "Target Calories", "kcal"),
    ]:
        entities.append(
            OuraComputedSensor(coordinator, uid, owner, friendly, field, unit=unit,
                               state_class=SensorStateClass.MEASUREMENT, compute=act_compute(field))
        )

    # Daily SpO2
    def spo2_compute(field: str) -> Callable[[dict[str, Any]], Any]:
        def inner(data: dict[str, Any]) -> Any:
            rec = _last_record(data.get("daily_spo2", {}))
            return None if rec is None else rec.get(field)
        return inner

    entities.append(
        OuraComputedSensor(coordinator, uid, owner, "SpO2 (avg)", "average_saturation", unit="%", 
                           state_class=SensorStateClass.MEASUREMENT, compute=spo2_compute("average_saturation"))
    )

    # Latest Heart Rate
    entities.append(
        OuraComputedSensor(coordinator, uid, owner, "Heart Rate (latest)", "latest_hr_bpm", unit="bpm",
                           state_class=SensorStateClass.MEASUREMENT, compute=lambda data: data.get("latest_hr_bpm"))
    )

    async_add_entities(entities)


class OuraComputedSensor(CoordinatorEntity[OuraCoordinator], SensorEntity):
    """A coordinator-bound sensor with a compute function to derive value."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: OuraCoordinator,
        user_id: str,
        owner: str,
        name: str,
        key: str,
        unit: str = "",
        device_class: SensorDeviceClass | None = None,
        state_class: SensorStateClass | None = SensorStateClass.MEASUREMENT,
        compute: Callable[[dict[str, Any]], Any] | None = None,
    ) -> None:
        super().__init__(coordinator)
        self._user_id = user_id
        self._owner = owner
        self._key = key
        self._attr_name = name
        self._attr_unique_id = f"{user_id}_{key}"
        self._attr_native_unit_of_measurement = unit or None
        self._attr_device_class = device_class
        self._attr_state_class = state_class
        self._compute = compute or (lambda data: None)

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._user_id)},
            "name": f"Oura Ring ({self._owner})",
            "manufacturer": "Oura",
            "model": "Ring",
        }

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    @property
    def native_value(self) -> Any:
        return self._compute(self.coordinator.data)


# ---- Additional helpers for per-metric extraction ----
def _ds_first(d: OuraData) -> dict:
    return _first_item(d.payloads.get("daily_sleep", {}).get("data", [])) or {}

def _slp_first(d: OuraData) -> dict:
    # raw sleep (may include richer timing)
    return _first_item(d.payloads.get("sleep", {}).get("data", [])) or {}

def _dr_first(d: OuraData) -> dict:
    return _first_item(d.payloads.get("daily_readiness", {}).get("data", [])) or {}

def _da_first(d: OuraData) -> dict:
    return _first_item(d.payloads.get("daily_activity", {}).get("data", [])) or {}

def _readiness_contrib(d: OuraData) -> dict:
    dr = _dr_first(d)
    return dr.get("contributors") or {}

def _pick(*vals):
    for v in vals:
        if v is not None:
            return v
    return None

def _minutes_from_value(val):
    # Oura sometimes returns seconds, sometimes minutes in various endpoints; be lenient.
    try:
        v = float(val)
    except Exception:
        return None
    # Heuristic: if value looks like seconds (> 300), convert to minutes.
    return (v / 60.0) if v > 300 else v

def _sleep_duration_field(d: OuraData, *keys):
    # Try daily_sleep, then raw sleep
    ds = _ds_first(d)
    sl = _slp_first(d)
    v = None
    for k in keys:
        if k in ds:
            v = ds.get(k)
            break
        if k in sl:
            v = sl.get(k)
            break
    return _minutes_from_value(v)

def _sleep_int_field(d: OuraData, *keys):
    ds = _ds_first(d); sl = _slp_first(d)
    for k in keys:
        if k in ds:
            return ds.get(k)
        if k in sl:
            return sl.get(k)
    return None

def _sleep_time_field(d: OuraData, *keys):
    ds = _ds_first(d); sl = _slp_first(d)
    for k in keys:
        if k in ds and ds.get(k):
            return ds.get(k)
        if k in sl and sl.get(k):
            return sl.get(k)
    return None

def _activity_field(d: OuraData, *keys):
    da = _da_first(d)
    for k in keys:
        if k in da:
            return da.get(k)
    return None


# ---- Per-metric sensors: Sleep details ----
SENSORS.extend([
    # Durations (minutes)
    OuraCalculatedSensorDescription(
        key="sleep_total_duration_min",
        name="Oura Sleep Total Duration",
        icon="mdi:sleep",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        value_fn=lambda d: _sleep_duration_field(d, "total_sleep_duration", "duration", "total_sleep_time"),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="sleep_time_in_bed_min",
        name="Oura Sleep Time In Bed",
        icon="mdi:bed",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        value_fn=lambda d: _sleep_duration_field(d, "time_in_bed", "bedtime_duration"),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="sleep_deep_min",
        name="Oura Sleep Deep",
        icon="mdi:water-opacity",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        value_fn=lambda d: _sleep_duration_field(d, "deep_sleep_duration", "deep"),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="sleep_rem_min",
        name="Oura Sleep REM",
        icon="mdi:brain",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        value_fn=lambda d: _sleep_duration_field(d, "rem_sleep_duration", "rem"),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="sleep_light_min",
        name="Oura Sleep Light",
        icon="mdi:weather-sunset-down",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        value_fn=lambda d: _sleep_duration_field(d, "light_sleep_duration", "light"),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="sleep_awake_min",
        name="Oura Sleep Awake",
        icon="mdi:weather-sunny",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        value_fn=lambda d: _sleep_duration_field(d, "awake_time", "awake_duration"),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Efficiency / latency / timing score
    OuraCalculatedSensorDescription(
        key="sleep_efficiency",
        name="Oura Sleep Efficiency",
        icon="mdi:percent-outline",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda d: _sleep_int_field(d, "efficiency"),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="sleep_latency_min",
        name="Oura Sleep Latency",
        icon="mdi:timer-sand",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        value_fn=lambda d: _minutes_from_value(_sleep_int_field(d, "latency")),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="sleep_timing_score",
        name="Oura Sleep Timing Score",
        icon="mdi:clock-outline",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda d: (_readiness_contrib(d).get("sleep_timing") or _ds_first(d).get("contributors", {}).get("timing")),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Bedtime start/end
    OuraCalculatedSensorDescription(
        key="sleep_bedtime_start",
        name="Oura Sleep Bedtime Start",
        icon="mdi:bed-clock",
        value_fn=lambda d: _sleep_time_field(d, "bedtime_start", "start", "start_datetime"),
    ),
    OuraCalculatedSensorDescription(
        key="sleep_bedtime_end",
        name="Oura Sleep Bedtime End",
        icon="mdi:bed-clock",
        value_fn=lambda d: _sleep_time_field(d, "bedtime_end", "end", "end_datetime"),
    ),
])

# ---- Per-metric sensors: Readiness contributors ----
SENSORS.extend([
    OuraCalculatedSensorDescription(
        key="readiness_hrv_balance",
        name="Oura Readiness HRV Balance",
        icon="mdi:heart-pulse",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda d: _readiness_contrib(d).get("hrv_balance"),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="readiness_temperature_deviation",
        name="Oura Readiness Temperature Deviation",
        icon="mdi:thermometer",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda d: _readiness_contrib(d).get("temperature_deviation"),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="readiness_temperature_trend_deviation",
        name="Oura Readiness Temp Trend Deviation",
        icon="mdi:thermometer-lines",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda d: _readiness_contrib(d).get("temperature_trend_deviation"),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="readiness_recovery_index_min",
        name="Oura Readiness Recovery Index",
        icon="mdi:timer",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        value_fn=lambda d: _readiness_contrib(d).get("recovery_index"),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="readiness_sleep_balance",
        name="Oura Readiness Sleep Balance",
        icon="mdi:sleep",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda d: _readiness_contrib(d).get("sleep_balance"),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="readiness_activity_balance",
        name="Oura Readiness Activity Balance",
        icon="mdi:run",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda d: _readiness_contrib(d).get("activity_balance"),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="readiness_previous_day_activity",
        name="Oura Readiness Previous Day Activity",
        icon="mdi:shoe-print",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda d: _readiness_contrib(d).get("previous_day_activity"),
        state_class=SensorStateClass.MEASUREMENT,
    ),
])

# ---- Per-metric sensors: Activity details (daily) ----
SENSORS.extend([
    OuraCalculatedSensorDescription(
        key="activity_active_calories",
        name="Oura Active Calories",
        icon="mdi:fire",
        value_fn=lambda d: _activity_field(d, "active_calories"),
        state_class=SensorStateClass.TOTAL,
    ),
    OuraCalculatedSensorDescription(
        key="activity_inactive_time_min",
        name="Oura Inactive Time",
        icon="mdi:seat-recline-normal",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        value_fn=lambda d: _minutes_from_value(_activity_field(d, "inactivity_time", "inactive_time", "sedentary_time")),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="activity_non_wear_time_min",
        name="Oura Non-wear Time",
        icon="mdi:watch-off",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        value_fn=lambda d: _minutes_from_value(_activity_field(d, "non_wear_time")),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="activity_distance_km",
        name="Oura Equivalent Walking Distance",
        icon="mdi:map-marker-distance",
        native_unit_of_measurement=UnitOfLength.KILOMETERS,
        value_fn=lambda d: _activity_field(d, "equivalent_walking_distance", "distance"),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="activity_low_activity_min",
        name="Oura Low Activity Minutes",
        icon="mdi:walk",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        value_fn=lambda d: _minutes_from_value(_activity_field(d, "low_activity_minutes", "low")),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="activity_moderate_activity_min",
        name="Oura Moderate Activity Minutes",
        icon="mdi:run",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        value_fn=lambda d: _minutes_from_value(_activity_field(d, "moderate_activity_minutes", "medium")),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="activity_high_activity_min",
        name="Oura High Activity Minutes",
        icon="mdi:run-fast",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        value_fn=lambda d: _minutes_from_value(_activity_field(d, "high_activity_minutes", "vigorous")),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    # Activity contributors (scores)
    OuraCalculatedSensorDescription(
        key="activity_meet_daily_targets",
        name="Oura Activity Meet Daily Targets",
        icon="mdi:target",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda d: _da_first(d).get("contributors", {}).get("meet_daily_targets"),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="activity_move_every_hour",
        name="Oura Activity Move Every Hour",
        icon="mdi:clock-time-eight-outline",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda d: _da_first(d).get("contributors", {}).get("move_every_hour"),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="activity_stay_active",
        name="Oura Activity Stay Active",
        icon="mdi:run",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda d: _da_first(d).get("contributors", {}).get("stay_active"),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="activity_training_frequency",
        name="Oura Activity Training Frequency",
        icon="mdi:calendar-clock",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda d: _da_first(d).get("contributors", {}).get("training_frequency"),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="activity_training_volume",
        name="Oura Activity Training Volume",
        icon="mdi:chart-bar",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda d: _da_first(d).get("contributors", {}).get("training_volume"),
        state_class=SensorStateClass.MEASUREMENT,
    ),
])

# ---- Per-metric sensors: Nightly vitals ----
SENSORS.extend([
    OuraCalculatedSensorDescription(
        key="vitals_respiratory_rate",
        name="Oura Respiratory Rate",
        icon="mdi:weather-windy",
        native_unit_of_measurement="breaths/min",
        value_fn=lambda d: _pick(_sleep_int_field(d, "respiratory_rate", "average_breath", "breath_average"), _ds_first(d).get("respiratory_rate")),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="vitals_hrv_rmssd",
        name="Oura HRV (RMSSD)",
        icon="mdi:chart-bell-curve",
        native_unit_of_measurement="ms",
        value_fn=lambda d: _pick(_sleep_int_field(d, "rmssd", "hrv", "average_hrv", "hrv_rmssd"), _dr_first(d).get("rmssd")),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="vitals_lowest_heart_rate",
        name="Oura Lowest Heart Rate",
        icon="mdi:heart-minus",
        value_fn=lambda d: _sleep_int_field(d, "lowest_heart_rate", "lowest_hr"),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="vitals_average_heart_rate",
        name="Oura Average Heart Rate",
        icon="mdi:heart",
        value_fn=lambda d: _sleep_int_field(d, "average_heart_rate", "avg_hr"),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="vitals_temperature_deviation",
        name="Oura Temperature Deviation",
        icon="mdi:thermometer",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda d: _pick(_ds_first(d).get("temperature_deviation"), _readiness_contrib(d).get("temperature_deviation")),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="vitals_temperature_trend_deviation",
        name="Oura Temp Trend Deviation",
        icon="mdi:thermometer-lines",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        value_fn=lambda d: _pick(_ds_first(d).get("temperature_trend_deviation"), _readiness_contrib(d).get("temperature_trend_deviation")),
        state_class=SensorStateClass.MEASUREMENT,
    ),
    OuraCalculatedSensorDescription(
        key="vitals_spo2_lowest",
        name="Oura SpO2 Lowest",
        icon="mdi:blood-bag",
        native_unit_of_measurement=PERCENTAGE,
        value_fn=lambda d: _first_item(d.payloads.get("daily_spo2", {}).get("data", [])) or {}.get("spo2_percentage_lowest"),
        state_class=SensorStateClass.MEASUREMENT,
    ),
])
