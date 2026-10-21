from custom_components.oura.coordinator import OuraData
from custom_components.oura.data import bedtime, rest_mode, tag_label, today_calories, today_count


def test_declined_data_differs_from_empty():
    denied = OuraData({"workout": {"data": []}}, unavailable={"workout": "permissions"})
    assert today_count(denied, "workout") is None
    assert today_count(OuraData({"workout": {"data": []}}), "workout") == 0


def test_unknown_calories_do_not_become_zero():
    data = OuraData(
        {"workout": {"data": [{"day": "2026-10-21", "calories": None}]}}, today="2026-10-21"
    )
    assert today_calories(data) is None


def test_long_tags_fit_home_assistant_state_limit():
    data = OuraData({"tag": {"data": [{"timestamp": "2026-10-21T12:00:00Z", "text": "a" * 500}]}})
    assert len(tag_label(data)) == 255


def test_enhanced_tag_fields():
    data = OuraData(
        {
            "enhanced_tag": {
                "data": [
                    {
                        "start_time": "2026-10-21T12:00:00Z",
                        "custom_name": "Travel",
                        "tag_type_code": "custom",
                    }
                ]
            }
        }
    )
    assert tag_label(data, True) == "Travel"


def test_invalid_bedtime_is_missing(sample_data):
    sample_data.payloads["sleep_time"]["data"][0]["optimal_bedtime"] = None
    assert bedtime(sample_data, "start") is None


def test_active_rest_mode_and_ended_period(freezer):
    freezer.move_to("2026-10-21T12:00:00Z")
    data = OuraData(
        {"rest_mode_period": {"data": [{"start_day": "2026-10-01", "end_day": None}]}},
        today="2026-10-21",
    )
    assert rest_mode(data) is True
    data.payloads["rest_mode_period"]["data"][0].update(
        end_day="2026-10-21", end_time="2026-10-21T08:00:00Z"
    )
    assert rest_mode(data) is False
