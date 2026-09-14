"""AI helper tests.

Every ai_task / llmvision / notify service is a mock registered on the test
hass — no model is ever called. ai_task isn't part of the HA 2025.1.4 test
package, so its generate_data service only exists as these mocks. Runners are
fakes: the report code reads only snapshot(), history(), config, entry and
async_add_listener.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
import json
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from pytest_homeassistant_custom_component.common import (
    async_fire_time_changed,
    async_mock_service,
)

from custom_components.irrigation_manager import ai
from custom_components.irrigation_manager.const import (
    CONF_AI_CAMERA,
    CONF_AI_LLMVISION_PROVIDER,
    CONF_AI_NOTIFY_SERVICE,
    CONF_AI_REPORT_TIME,
    CONF_AI_REPORT_WEEKDAY,
    CONF_AI_TASK_ENTITY,
)

TZ = ZoneInfo("America/New_York")
AI_ENTITY = "ai_task.claude_ai_task"
REPORT_TEXT = "Watered 3 times."

BASE_CONFIG: dict[str, Any] = {
    "name": "Garden Bed",
    "zones": [{"entity_id": "valve.garden_irrigation_zone", "minutes": 30}],
    "zone_mode": "sequential",
    "frequency": "interval",
    "interval_days": 2,
    "anchor": "2026-09-13",
    "start_mode": "time",
    "start_time": "06:00:00",
    "skip_conditions": [],
    CONF_AI_TASK_ENTITY: AI_ENTITY,
    CONF_AI_NOTIFY_SERVICE: "notify.iphone",
}


def local(y: int, mo: int, d: int, h: int = 0, mi: int = 0, s: int = 0) -> datetime:
    return datetime(y, mo, d, h, mi, s, tzinfo=TZ)


class FakeRunner:
    """Just enough of ScheduleRunner for ai.py."""

    def __init__(
        self,
        hass: HomeAssistant,
        config: dict[str, Any] | None = None,
        history: list[dict[str, Any]] | None = None,
        status: str = "idle",
    ) -> None:
        self.hass = hass
        self.entry = SimpleNamespace(entry_id="entry1", title="Garden Bed")
        self.config = dict(BASE_CONFIG if config is None else config)
        self._history = list(history or [])
        self._listeners: list[Callable[[], None]] = []
        self.status = status

    def snapshot(self) -> dict[str, Any]:
        return {
            "entry_id": self.entry.entry_id,
            "name": self.entry.title,
            "enabled": True,
            "status": self.status,
            "next_run": "2026-09-22T06:00:00-04:00",
            "next_run_scheduled": True,
            "last_status_at": "2026-09-19T06:00:00-04:00",
            "last_details": {"rain": {"total": 0.4, "threshold": 0.1}},
            "config": dict(self.config),
        }

    def history(self, limit: int | None = None) -> list[dict[str, Any]]:
        return self._history[:limit] if limit else list(self._history)

    def async_add_listener(self, update_callback: Callable[[], None]) -> Callable[[], None]:
        self._listeners.append(update_callback)
        return lambda: self._listeners.remove(update_callback)

    def update_config(self, config: dict[str, Any]) -> None:
        self.config = dict(config)
        for update_callback in list(self._listeners):
            update_callback()


class LegacyRunner(FakeRunner):
    """A runner from before run history existed."""

    history = None  # type: ignore[assignment]


HISTORY = [
    {"at": "2026-09-19T06:00:00-04:00", "type": "run", "status": "idle",
     "manual": False, "zones": [], "total_minutes": 30.0, "details": {}},
    {"at": "2026-09-17T06:00:00-04:00", "type": "skip", "status": "skipped_rain",
     "manual": False, "zones": [], "total_minutes": 0,
     "details": {"rain": {"total": 0.42, "threshold": 0.1, "unit": "in"}}},
    {"at": "2026-09-01T06:00:00-04:00", "type": "run", "status": "idle",
     "manual": False, "zones": [], "total_minutes": 30.0, "details": {}},
]


@pytest.fixture(autouse=True)
async def setup_env(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    await hass.config.async_set_time_zone("America/New_York")
    freezer.move_to(local(2026, 9, 20, 12))
    hass.states.async_set("valve.garden_irrigation_zone", "closed", {"friendly_name": "Garden irrigation"})


@pytest.fixture
def generate(hass: HomeAssistant) -> list:
    return async_mock_service(
        hass, "ai_task", "generate_data",
        response={"conversation_id": "c1", "data": REPORT_TEXT},
        supports_response=SupportsResponse.ONLY,
    )


def prompt_data(call) -> dict[str, Any]:
    return json.loads(call.data["instructions"].split(ai.DATA_MARKER, 1)[1])


async def advance_to(hass: HomeAssistant, freezer: FrozenDateTimeFactory, when: datetime) -> None:
    freezer.move_to(when)
    async_fire_time_changed(hass, when)
    await hass.async_block_till_done()


# --- report -------------------------------------------------------------------


async def test_report_calls_ai_task_with_context(hass: HomeAssistant, generate: list) -> None:
    runner = FakeRunner(hass, history=HISTORY)

    assert await ai.async_generate_report(hass, runner) == REPORT_TEXT

    assert len(generate) == 1
    call = generate[0]
    assert call.data["entity_id"] == AI_ENTITY
    assert call.data["task_name"] == "Garden Bed watering report"
    assert "structure" not in call.data
    context = prompt_data(call)
    assert context["schedule"] == "Garden Bed"
    assert context["period_days"] == 7
    assert [record["at"][:10] for record in context["history"]] == ["2026-09-19", "2026-09-17"]
    assert not any(key.startswith("ai_") for key in context["config"])
    assert context["zone_names"] == {"valve.garden_irrigation_zone": "Garden irrigation"}
    assert context["state"]["next_run"] == "2026-09-22T06:00:00-04:00"
    assert "lawn_camera" not in context


async def test_report_days_widens_history(hass: HomeAssistant, generate: list) -> None:
    await ai.async_generate_report(hass, FakeRunner(hass, history=HISTORY), days=30)
    assert len(prompt_data(generate[0])["history"]) == 3


async def test_report_on_runner_without_history(hass: HomeAssistant, generate: list) -> None:
    runner = LegacyRunner(hass, status="skipped_rain")
    await ai.async_generate_report(hass, runner)
    history = prompt_data(generate[0])["history"]
    assert history == [{
        "at": "2026-09-19T06:00:00-04:00",
        "type": "skip",
        "status": "skipped_rain",
        "details": {"rain": {"total": 0.4, "threshold": 0.1}},
    }]


async def test_report_requires_ai_entity(hass: HomeAssistant, generate: list) -> None:
    config = {**BASE_CONFIG}
    config.pop(CONF_AI_TASK_ENTITY)
    with pytest.raises(ai.AiNotConfigured):
        await ai.async_generate_report(hass, FakeRunner(hass, config))
    assert generate == []


async def test_report_without_ai_task_service(hass: HomeAssistant) -> None:
    with pytest.raises(HomeAssistantError, match="not available"):
        await ai.async_generate_report(hass, FakeRunner(hass))


async def test_report_with_no_data_raises(hass: HomeAssistant) -> None:
    async_mock_service(
        hass, "ai_task", "generate_data",
        response={"conversation_id": "c1", "data": None},
        supports_response=SupportsResponse.ONLY,
    )
    with pytest.raises(HomeAssistantError, match="no data"):
        await ai.async_generate_report(hass, FakeRunner(hass))


async def test_report_includes_lawn_camera(hass: HomeAssistant, generate: list) -> None:
    vision = async_mock_service(
        hass, "llmvision", "image_analyzer",
        response={"response_text": "Brown patches near the fence."},
        supports_response=SupportsResponse.ONLY,
    )
    config = {**BASE_CONFIG, CONF_AI_CAMERA: "camera.back_yard_camera",
              CONF_AI_LLMVISION_PROVIDER: "provider1"}

    await ai.async_generate_report(hass, FakeRunner(hass, config))

    assert len(vision) == 1
    assert vision[0].data == {
        "provider": "provider1",
        "message": ai.LAWN_PROMPT,
        "image_entity": ["camera.back_yard_camera"],
        "include_filename": False,
        "store_in_timeline": False,
    }
    assert prompt_data(generate[0])["lawn_camera"] == {
        "camera": "camera.back_yard_camera",
        "observations": "Brown patches near the fence.",
    }


async def test_lawn_camera_failure_still_reports(hass: HomeAssistant, generate: list) -> None:
    async_mock_service(
        hass, "llmvision", "image_analyzer",
        supports_response=SupportsResponse.ONLY,
        raise_exception=HomeAssistantError("provider down"),
    )
    config = {**BASE_CONFIG, CONF_AI_CAMERA: "camera.back_yard_camera",
              CONF_AI_LLMVISION_PROVIDER: "provider1"}

    assert await ai.async_generate_report(hass, FakeRunner(hass, config)) == REPORT_TEXT
    assert prompt_data(generate[0])["lawn_camera"]["error"] == "camera analysis failed"


async def test_lawn_camera_without_provider_skips_llmvision(
    hass: HomeAssistant, generate: list
) -> None:
    vision = async_mock_service(
        hass, "llmvision", "image_analyzer",
        response={"response_text": "x"}, supports_response=SupportsResponse.ONLY,
    )
    config = {**BASE_CONFIG, CONF_AI_CAMERA: "camera.back_yard_camera"}

    await ai.async_generate_report(hass, FakeRunner(hass, config))

    assert vision == []
    assert prompt_data(generate[0])["lawn_camera"]["error"] == "no LLM Vision provider configured"


async def test_report_with_rain_condition_and_no_recorder(
    hass: HomeAssistant, generate: list
) -> None:
    config = {**BASE_CONFIG, "skip_conditions": ["rain"],
              "rain_sensor": "sensor.weather_station_rain_in", "rain_threshold": 0.1}

    assert await ai.async_generate_report(hass, FakeRunner(hass, config)) == REPORT_TEXT
    assert "current_conditions" in prompt_data(generate[0])


# --- explain skips ------------------------------------------------------------


async def test_explain_skips_without_skips_makes_no_call(
    hass: HomeAssistant, generate: list
) -> None:
    runs_only = [record for record in HISTORY if record["type"] == "run"]
    text = await ai.async_explain_skips(hass, FakeRunner(hass, history=runs_only))
    assert text == "No runs of Garden Bed were skipped in the last 7 days."
    assert generate == []


async def test_explain_skips_sends_only_skips(hass: HomeAssistant, generate: list) -> None:
    text = await ai.async_explain_skips(hass, FakeRunner(hass, history=HISTORY))

    assert text == REPORT_TEXT
    call = generate[0]
    assert call.data["task_name"] == "Garden Bed skip explanation"
    skips = prompt_data(call)["skips"]
    assert [record["status"] for record in skips] == ["skipped_rain"]


# --- parse description --------------------------------------------------------


@pytest.fixture
def parse_states(hass: HomeAssistant) -> None:
    hass.states.async_set("switch.front_yard_sprinkler", "off", {"friendly_name": "Front yard"})
    hass.states.async_set(
        "sensor.weather_station_rain_in", "69.2",
        {"device_class": "precipitation", "friendly_name": "Weather Station Rain"},
    )
    hass.states.async_set(
        "sensor.0d0c22_moisture", "30",
        {"device_class": "moisture", "friendly_name": "Aloe Vera Moisture"},
    )
    hass.states.async_set("weather.krdu_daynight", "sunny", {"friendly_name": "KRDU"})
    hass.states.async_set("light.kitchen", "off")


def mock_parse(hass: HomeAssistant, data: Any) -> list:
    return async_mock_service(
        hass, "ai_task", "generate_data",
        response={"conversation_id": "c1", "data": data},
        supports_response=SupportsResponse.ONLY,
    )


VALID_PARSE = {
    "name": "Garden",
    "zones": [{"entity_id": "valve.garden_irrigation_zone", "minutes": 20}],
    "zone_mode": "sequential",
    "frequency": "weekdays",
    "weekdays": ["0", "2", "4"],
    "start_mode": "sunrise",
    "sun_offset_minutes": 15,
    "skip_conditions": ["rain", "forecast", "moisture"],
    "rain_sensor": "sensor.weather_station_rain_in",
    "rain_threshold": 0.25,
    "rain_hours": 24,
    "weather_entity": "weather.krdu_daynight",
    "forecast_probability": 70,
    "forecast_hours": 12,
    "moisture_sensors": ["sensor.0d0c22_moisture"],
    "moisture_threshold": 35,
    "moisture_mode": "trigger",
}


async def test_parse_description_valid(hass: HomeAssistant, parse_states: None) -> None:
    calls = mock_parse(hass, VALID_PARSE)

    result = await ai.async_parse_schedule_description(
        hass, AI_ENTITY, "Water the garden Mon/Wed/Fri for 20 minutes before sunrise"
    )

    assert result["warnings"] == []
    assert result["config"] == {**VALID_PARSE, "weekdays": [0, 2, 4]}
    call = calls[0]
    assert call.data["entity_id"] == AI_ENTITY
    assert set(call.data["structure"]) >= {"zones", "frequency", "start_mode", "skip_conditions"}
    instructions = call.data["instructions"]
    assert instructions.endswith("Water the garden Mon/Wed/Fri for 20 minutes before sunrise")
    candidates = json.loads(
        instructions.split(ai.CANDIDATES_MARKER, 1)[1].split("\n\n" + ai.DESCRIPTION_MARKER, 1)[0]
    )
    assert "valve.garden_irrigation_zone" in candidates["zones"]
    assert "switch.front_yard_sprinkler" in candidates["zones"]
    assert "sensor.weather_station_rain_in" in candidates["rain_sensors"]
    assert "sensor.0d0c22_moisture" in candidates["moisture_sensors"]
    assert "weather.krdu_daynight" in candidates["weather"]
    assert "light.kitchen" not in json.dumps(candidates)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("forecast_probability", 0),
        ("rain_threshold", 0),
        ("rain_threshold", float("nan")),
        ("moisture_threshold", 0),
        ("rain_hours", 0),
        ("forecast_hours", 49),
        ("sun_offset_minutes", 1000),
        ("zone_mode", "sideways"),
        ("rain_sensor", "sensor.nope"),
        ("weather_entity", "sensor.weather_station_rain_in"),
        ("moisture_mode", "sometimes"),
        ("name", 42),
    ],
)
async def test_parse_rejects_out_of_range_values(
    hass: HomeAssistant, parse_states: None, key: str, value: Any
) -> None:
    mock_parse(hass, {**VALID_PARSE, key: value})

    result = await ai.async_parse_schedule_description(hass, AI_ENTITY, "text")

    assert key not in result["config"]
    assert any(warning.startswith(f"{key}:") for warning in result["warnings"])
    # Everything else survives.
    assert result["config"]["zones"] == VALID_PARSE["zones"]


@pytest.mark.parametrize(
    ("key", "value"),
    [("interval_days", 40), ("interval_days", 2.5), ("anchor", "2026-02-30")],
)
async def test_parse_rejects_bad_interval_values(
    hass: HomeAssistant, parse_states: None, key: str, value: Any
) -> None:
    data = {**VALID_PARSE, "frequency": "interval", "interval_days": 3,
            "anchor": "2026-09-21", key: value}
    data.pop("weekdays")
    mock_parse(hass, data)

    result = await ai.async_parse_schedule_description(hass, AI_ENTITY, "text")

    assert key not in result["config"]
    assert any(warning.startswith(f"{key}:") for warning in result["warnings"])


async def test_parse_rejects_bad_start_time(hass: HomeAssistant, parse_states: None) -> None:
    data = {**VALID_PARSE, "start_mode": "time", "start_time": "25:00"}
    data.pop("sun_offset_minutes")
    mock_parse(hass, data)

    result = await ai.async_parse_schedule_description(hass, AI_ENTITY, "text")

    assert "start_time" not in result["config"]
    assert result["config"]["start_mode"] == "time"


HOURLY_PARSE = {
    **{key: value for key, value in VALID_PARSE.items() if key not in ("weekdays", "sun_offset_minutes")},
    "frequency": "hourly",
    "interval_hours": 3,
    "window_start": "06:00",
    "window_end": "18:00",
    "start_mode": "time",
    "start_time": "06:00",
}


async def test_parse_hourly_description(hass: HomeAssistant, parse_states: None) -> None:
    calls = mock_parse(hass, HOURLY_PARSE)

    result = await ai.async_parse_schedule_description(
        hass, AI_ENTITY, "Water every 3 hours from 6am to 6pm"
    )

    assert result["warnings"] == []
    assert result["config"] == {
        **HOURLY_PARSE,
        "window_start": "06:00:00",
        "window_end": "18:00:00",
        "start_time": "06:00:00",
    }
    assert {"interval_hours", "window_start", "window_end"} <= set(calls[0].data["structure"])


@pytest.mark.parametrize(
    ("key", "value"),
    [("interval_hours", 0), ("interval_hours", 24), ("interval_hours", 2.5), ("window_start", "25:00")],
)
async def test_parse_rejects_bad_hourly_values(
    hass: HomeAssistant, parse_states: None, key: str, value: Any
) -> None:
    mock_parse(hass, {**HOURLY_PARSE, key: value})

    result = await ai.async_parse_schedule_description(hass, AI_ENTITY, "text")

    assert key not in result["config"]
    assert any(warning.startswith(f"{key}:") for warning in result["warnings"])
    assert result["config"]["frequency"] == "hourly"


async def test_parse_hourly_window_end_before_start_drops_frequency(
    hass: HomeAssistant, parse_states: None
) -> None:
    mock_parse(hass, {**HOURLY_PARSE, "window_end": "05:00"})

    result = await ai.async_parse_schedule_description(hass, AI_ENTITY, "text")

    assert not {"frequency", "interval_hours", "window_start", "window_end"} & result["config"].keys()
    assert any(warning.startswith("frequency:") for warning in result["warnings"])


async def test_parse_hourly_drops_day_and_sun_keys(hass: HomeAssistant, parse_states: None) -> None:
    mock_parse(
        hass,
        {**HOURLY_PARSE, "weekdays": ["1"], "interval_days": 2, "start_mode": "sunrise",
         "sun_offset_minutes": 10},
    )

    result = await ai.async_parse_schedule_description(hass, AI_ENTITY, "text")

    config = result["config"]
    assert config["frequency"] == "hourly"
    assert config["interval_hours"] == 3
    assert not {"weekdays", "interval_days", "start_mode", "sun_offset_minutes"} & config.keys()


async def test_parse_drops_hourly_keys_for_other_frequencies(
    hass: HomeAssistant, parse_states: None
) -> None:
    mock_parse(hass, {**VALID_PARSE, "interval_hours": 3, "window_start": "06:00"})

    result = await ai.async_parse_schedule_description(hass, AI_ENTITY, "text")

    assert result["config"]["frequency"] == "weekdays"
    assert not {"interval_hours", "window_start"} & result["config"].keys()


async def test_parse_drops_invalid_zones_only(hass: HomeAssistant, parse_states: None) -> None:
    zones = [
        {"entity_id": "valve.garden_irrigation_zone", "minutes": 500},
        {"entity_id": "light.kitchen", "minutes": 10},
        {"entity_id": "valve.missing", "minutes": 10},
        {"entity_id": "switch.front_yard_sprinkler", "minutes": 15},
        {"entity_id": "switch.front_yard_sprinkler", "minutes": 20},
    ]
    mock_parse(hass, {**VALID_PARSE, "zones": zones})

    result = await ai.async_parse_schedule_description(hass, AI_ENTITY, "text")

    assert result["config"]["zones"] == [{"entity_id": "switch.front_yard_sprinkler", "minutes": 15}]
    assert sum(warning.startswith("zones:") for warning in result["warnings"]) == 3


async def test_parse_drops_keys_for_unselected_conditions(
    hass: HomeAssistant, parse_states: None
) -> None:
    mock_parse(hass, {**VALID_PARSE, "skip_conditions": ["forecast", "flood"]})

    result = await ai.async_parse_schedule_description(hass, AI_ENTITY, "text")

    config = result["config"]
    assert config["skip_conditions"] == ["forecast"]
    for key in ("rain_sensor", "rain_threshold", "rain_hours", "moisture_sensors",
                "moisture_threshold", "moisture_mode"):
        assert key not in config
    assert "forecast_probability" in config
    assert any("flood" in warning for warning in result["warnings"])


async def test_parse_drops_keys_the_modes_dont_use(hass: HomeAssistant, parse_states: None) -> None:
    mock_parse(hass, {**VALID_PARSE, "frequency": "interval", "interval_days": 2,
                      "start_mode": "time", "start_time": "06:30"})

    result = await ai.async_parse_schedule_description(hass, AI_ENTITY, "text")

    config = result["config"]
    assert "weekdays" not in config
    assert "sun_offset_minutes" not in config
    assert config["start_time"] == "06:30:00"
    assert config["interval_days"] == 2


async def test_parse_drops_frequency_without_valid_weekdays(
    hass: HomeAssistant, parse_states: None
) -> None:
    mock_parse(hass, {**VALID_PARSE, "weekdays": ["funday"]})

    result = await ai.async_parse_schedule_description(hass, AI_ENTITY, "text")

    assert "frequency" not in result["config"]
    assert "weekdays" not in result["config"]
    assert any(warning.startswith("frequency:") for warning in result["warnings"])


async def test_parse_accepts_weekday_names(hass: HomeAssistant, parse_states: None) -> None:
    mock_parse(hass, {**VALID_PARSE, "weekdays": ["Monday", "fri", 6]})
    result = await ai.async_parse_schedule_description(hass, AI_ENTITY, "text")
    assert result["config"]["weekdays"] == [0, 4, 6]


async def test_parse_temperature_min_must_be_below_max(
    hass: HomeAssistant, parse_states: None
) -> None:
    mock_parse(hass, {**VALID_PARSE, "skip_conditions": ["temperature"],
                      "temperature_min": 90, "temperature_max": 35})
    result = await ai.async_parse_schedule_description(hass, AI_ENTITY, "text")
    assert "temperature_min" not in result["config"]
    assert "temperature_max" not in result["config"]


async def test_parse_unknown_keys_are_warned(hass: HomeAssistant, parse_states: None) -> None:
    mock_parse(hass, {**VALID_PARSE, "fertilizer": True})
    result = await ai.async_parse_schedule_description(hass, AI_ENTITY, "text")
    assert "fertilizer" not in result["config"]
    assert "fertilizer: ignored, not a schedule setting" in result["warnings"]


async def test_parse_non_structured_response(hass: HomeAssistant, parse_states: None) -> None:
    mock_parse(hass, "every day at 6")
    result = await ai.async_parse_schedule_description(hass, AI_ENTITY, "text")
    assert result["config"] == {}
    assert result["warnings"]


async def test_parse_requires_text_and_entity(hass: HomeAssistant, parse_states: None) -> None:
    calls = mock_parse(hass, VALID_PARSE)
    with pytest.raises(HomeAssistantError):
        await ai.async_parse_schedule_description(hass, AI_ENTITY, "   ")
    with pytest.raises(ai.AiNotConfigured):
        await ai.async_parse_schedule_description(hass, "", "text")
    assert calls == []


# --- notifications --------------------------------------------------------------


async def test_notification_defaults_to_persistent_notification(hass: HomeAssistant) -> None:
    calls = async_mock_service(hass, "persistent_notification", "create")
    await ai.async_send_notification(hass, None, title="T", message="M", notification_id="n1")
    assert calls[0].data == {"title": "T", "message": "M", "notification_id": "n1"}


async def test_notification_rejects_other_services(hass: HomeAssistant) -> None:
    async_mock_service(hass, "light", "turn_on")
    with pytest.raises(HomeAssistantError, match="Unsupported"):
        await ai.async_send_notification(hass, "light.turn_on", title="T", message="M", notification_id="n")


# --- weekly report --------------------------------------------------------------


def weekly_config(weekday: int, at: str) -> dict[str, Any]:
    return {**BASE_CONFIG, CONF_AI_REPORT_WEEKDAY: weekday, CONF_AI_REPORT_TIME: at}


@pytest.fixture
def weekly(hass: HomeAssistant):
    """Set up weekly reports and cancel them at teardown, so no timer lingers."""
    cancels: list[Callable[[], None]] = []

    def setup(runner: FakeRunner) -> Callable[[], None]:
        cancel = ai.async_setup_weekly_report(hass, runner)
        cancels.append(cancel)
        return cancel

    yield setup
    for cancel in cancels:
        cancel()


async def test_weekly_report_fires_on_its_weekday_only(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, generate: list, weekly
) -> None:
    notify = async_mock_service(hass, "notify", "iphone")
    runner = FakeRunner(hass, weekly_config(0, "07:00:00"))  # Monday
    cancel = weekly(runner)

    await advance_to(hass, freezer, local(2026, 9, 21, 7))  # Monday
    assert len(notify) == 1
    assert notify[0].data == {"title": "Garden Bed watering report", "message": REPORT_TEXT}

    await advance_to(hass, freezer, local(2026, 9, 22, 7))  # Tuesday
    assert len(notify) == 1

    await advance_to(hass, freezer, local(2026, 9, 28, 7))  # next Monday
    assert len(notify) == 2

    cancel()
    await advance_to(hass, freezer, local(2026, 10, 5, 7))
    assert len(notify) == 2


async def test_weekly_report_keeps_local_time_across_dst(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, generate: list, weekly
) -> None:
    notify = async_mock_service(hass, "notify", "iphone")
    freezer.move_to(local(2026, 3, 1, 12))
    weekly(FakeRunner(hass, weekly_config(6, "07:00:00")))  # Sunday

    # Walk the week a day at a time, like a real clock.
    for day in range(2, 8):
        await advance_to(hass, freezer, local(2026, 3, day, 7))
    assert notify == []

    # DST starts at 02:00 on 2026-03-08. The report goes out at 07:00 EDT
    # (11:00 UTC), not at 07:00 EST (12:00 UTC).
    await advance_to(hass, freezer, datetime(2026, 3, 8, 11, 0, tzinfo=ZoneInfo("UTC")))
    assert len(notify) == 1

    for day in range(9, 16):
        await advance_to(hass, freezer, local(2026, 3, day, 7))
    assert len(notify) == 2


async def test_weekly_report_sends_once_on_repeated_fall_back_hour(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, generate: list, weekly
) -> None:
    notify = async_mock_service(hass, "notify", "iphone")
    freezer.move_to(local(2026, 10, 31, 12))
    weekly(FakeRunner(hass, weekly_config(6, "01:30:00")))  # Sunday

    first = datetime(2026, 11, 1, 5, 30, tzinfo=ZoneInfo("UTC"))  # 01:30 EDT
    second = datetime(2026, 11, 1, 6, 30, tzinfo=ZoneInfo("UTC"))  # 01:30 EST
    await advance_to(hass, freezer, first)
    await advance_to(hass, freezer, second)
    assert len(notify) == 1


async def test_weekly_report_errors_are_logged(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
    weekly,
) -> None:
    async_mock_service(
        hass, "ai_task", "generate_data",
        supports_response=SupportsResponse.ONLY,
        raise_exception=HomeAssistantError("model offline"),
    )
    notify = async_mock_service(hass, "notify", "iphone")
    weekly(FakeRunner(hass, weekly_config(0, "07:00:00")))

    await advance_to(hass, freezer, local(2026, 9, 21, 7))

    assert notify == []
    assert "sending the weekly AI report failed" in caplog.text


async def test_weekly_report_off_without_settings(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, generate: list, weekly
) -> None:
    config = {**BASE_CONFIG, CONF_AI_REPORT_TIME: "07:00:00"}  # no weekday
    weekly(FakeRunner(hass, config))
    for day in range(21, 28):
        await advance_to(hass, freezer, local(2026, 9, day, 7))
    assert generate == []


async def test_weekly_report_follows_config_changes(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, generate: list, weekly
) -> None:
    notify = async_mock_service(hass, "notify", "iphone")
    runner = FakeRunner(hass, weekly_config(0, "07:00:00"))
    weekly(runner)

    runner.update_config(weekly_config(0, "09:00:00"))
    await advance_to(hass, freezer, local(2026, 9, 21, 7))
    assert notify == []
    await advance_to(hass, freezer, local(2026, 9, 21, 9))
    assert len(notify) == 1

    runner.update_config({**BASE_CONFIG})  # report turned off
    await advance_to(hass, freezer, local(2026, 9, 28, 9))
    assert len(notify) == 1
