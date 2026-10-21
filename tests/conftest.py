"""Tests use an isolated Home Assistant instance and synthetic data only."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.oura.coordinator import OuraData


@pytest.fixture(autouse=True)
def custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def api_session():
    session = MagicMock()
    session.async_request = AsyncMock()
    session.async_ensure_token_valid = AsyncMock()
    return session


@pytest.fixture
def response():
    def make(status=200, body=None, headers=None):
        result = MagicMock()
        result.status = status
        result.headers = headers or {}
        result.json = AsyncMock(
            return_value=body if body is not None else {"data": [], "next_token": None}
        )
        result.text = AsyncMock(return_value=str(body or ""))
        return result

    return make


@pytest.fixture
def sample_data():
    return OuraData(
        {
            "daily_readiness": {
                "data": [
                    {"id": "old", "day": "2026-10-20", "score": 60},
                    {"id": "new", "day": "2026-10-21", "score": 90},
                ]
            },
            "daily_spo2": {
                "data": [{"id": "spo2", "day": "2026-10-21", "spo2_percentage": {"average": 97.5}}]
            },
            "sleep": {
                "data": [
                    {
                        "id": "night",
                        "day": "2026-10-21",
                        "type": "long_sleep",
                        "total_sleep_duration": 25200,
                        "lowest_heart_rate": 50,
                        "bedtime_start": "2026-10-20T23:00:00-07:00",
                        "bedtime_end": "2026-10-21T07:00:00-07:00",
                    },
                    {
                        "id": "nap",
                        "day": "2026-10-21",
                        "type": "sleep",
                        "total_sleep_duration": 1800,
                        "lowest_heart_rate": 65,
                        "bedtime_start": "2026-10-21T13:00:00-07:00",
                    },
                    {
                        "id": "deleted",
                        "day": "2026-10-21",
                        "type": "deleted",
                        "total_sleep_duration": 36000,
                        "bedtime_start": "2026-10-21T15:00:00-07:00",
                    },
                ]
            },
            "sleep_time": {
                "data": [
                    {
                        "id": "bedtime",
                        "day": "2026-10-21",
                        "optimal_bedtime": {
                            "day_tz": -25200,
                            "start_offset": -3600,
                            "end_offset": 0,
                        },
                    }
                ]
            },
            "tag": {
                "data": [
                    {
                        "id": "tag",
                        "day": "2026-10-21",
                        "timestamp": "2026-10-21T12:00:00Z",
                        "text": "Walk",
                        "tags": ["tag_walk"],
                    }
                ]
            },
            "heartrate": {
                "data": [
                    {"timestamp": "2026-10-21T12:00:00Z", "bpm": 70},
                    {"timestamp": "2026-10-21T11:00:00Z", "bpm": None},
                    {"timestamp": "2026-10-21T10:00:00Z", "bpm": 60},
                ]
            },
            "workout": {"data": []},
            "session": {"data": []},
        },
        today="2026-10-21",
    )
