from unittest.mock import MagicMock

import pytest

from custom_components.oura.coordinator import OuraData
from custom_components.oura.sensor import SENSORS, OuraCalculatedSensor, _collection_for


def sensor(key, data):
    coordinator = MagicMock(data=data, last_update_success=True)
    description = next(item for item in SENSORS if item.key == key)
    return OuraCalculatedSensor(coordinator, description, {}, "existing-entry")


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("spo2_avg", 97.5),
        ("readiness_score", 90),
        ("resting_heart_rate", 50),
        ("sleep_total_duration_min", 420),
        ("latest_tag", "Walk"),
        ("hr_latest", 70),
        ("hr_min", 60),
        ("hr_max", 70),
        ("workouts_today_count", 0),
        ("workouts_today_duration_min", 0),
        ("workouts_today_calories", 0),
    ],
)
def test_schema_values(sample_data, key, expected):
    assert sensor(key, sample_data).native_value == expected


def test_bedtime_offsets(sample_data):
    assert (
        sensor("optimal_bedtime_start", sample_data).native_value.isoformat()
        == "2026-10-20T23:00:00-07:00"
    )
    assert (
        sensor("optimal_bedtime_end", sample_data).native_value.isoformat()
        == "2026-10-21T00:00:00-07:00"
    )


@pytest.mark.parametrize(
    "key", ["sleep_total_duration_min", "workouts_today_count", "workouts_today_calories"]
)
def test_missing_is_not_zero(key):
    entity = sensor(key, OuraData({}))
    assert entity.native_value is None
    assert not entity.available


def test_endpoint_failure_does_not_expose_cached_value(sample_data):
    sample_data.unavailable["daily_spo2"] = "permissions"
    entity = sensor("spo2_avg", sample_data)
    assert not entity.available
    assert entity.native_value is None
    assert entity.extra_state_attributes == {}


def test_unchanged_identity_and_source_day(sample_data):
    entity = sensor("readiness_score", sample_data)
    assert entity.unique_id == "existing-entry_readiness_score"
    assert entity.extra_state_attributes["source_day"] == "2026-10-21"


def test_every_sensor_has_collection():
    assert len({item.key for item in SENSORS}) == len(SENSORS)
    assert all(item.collection or _collection_for(item.key) for item in SENSORS)
