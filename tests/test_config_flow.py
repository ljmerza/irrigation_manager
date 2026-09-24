"""Config and options flow tests.

Runs against the pytest-homeassistant-custom-component `hass` fixture. Setup is
patched out — these tests cover the wizard, the stored config shape, the import
and describe paths, and that every step, error, service and device automation
has a string.
"""
from __future__ import annotations

from collections.abc import Generator
from copy import deepcopy
from datetime import date, datetime, time, timedelta
import json
from pathlib import Path
import re
from typing import Any
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest
import yaml
from homeassistant import config_entries
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.data_entry_flow import FlowResultType, InvalidData
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.selector import SelectSelector
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.irrigation_manager import ai, config_flow
from custom_components.irrigation_manager.conditions import (
    resolve_rain_sensors,
    resolve_weather_entities,
)
from custom_components.irrigation_manager.const import DOMAIN, Status
from custom_components.irrigation_manager.device_condition import CONDITION_TYPES
from custom_components.irrigation_manager.device_trigger import TRIGGER_TYPES
from custom_components.irrigation_manager.runner import schedule_from_config
from custom_components.irrigation_manager.scheduler import Schedule, next_run

PACKAGE = Path(config_flow.__file__).parent
STRINGS: dict[str, Any] = json.loads((PACKAGE / "strings.json").read_text())

READ_LEGACY = "custom_components.irrigation_manager.migration.async_read_legacy_helpers"
READ_BHYVE = "custom_components.irrigation_manager.migration.async_read_bhyve_programs"
DISABLE_BHYVE = "custom_components.irrigation_manager.migration.async_disable_bhyve_program"
PARSE_DESCRIPTION = "custom_components.irrigation_manager.ai.async_parse_schedule_description"

TZ_DATE = date(2026, 9, 13)
AI_TASK = "ai_task.claude_ai_task"

# v0.1 stored shape (single rain sensor and weather entity).
FULL_CONFIG: dict[str, Any] = {
    "name": "Front lawn",
    "zones": [
        {"entity_id": "valve.deck_zone", "minutes": 10},
        {"entity_id": "switch.front_yard", "minutes": 20},
    ],
    "zone_mode": "concurrent",
    "frequency": "weekdays",
    "weekdays": [0, 2, 4],
    "start_mode": "sunrise",
    "sun_offset_minutes": -15,
    "skip_conditions": ["rain", "forecast", "moisture"],
    "rain_sensor": "sensor.weather_station_rain_in",
    "rain_threshold": 0.25,
    "rain_hours": 24,
    "weather_entity": "weather.home",
    "forecast_probability": 70,
    "forecast_hours": 12,
    "moisture_sensors": ["sensor.a_moisture", "sensor.b_moisture"],
    "moisture_threshold": 35.0,
    "moisture_mode": "trigger",
    "moisture_unavailable": "skip",
}

# Every v0.2 setting in use.
V02_CONFIG: dict[str, Any] = {
    "name": "Front lawn",
    "zones": FULL_CONFIG["zones"],
    "zone_mode": "concurrent",
    "frequency": "weekdays",
    "weekdays": [0, 2, 4],
    "start_mode": "sunrise",
    "sun_offset_minutes": -15,
    "skip_conditions": ["rain", "forecast", "moisture", "temperature", "wind", "occupancy"],
    "stale_hours": 6,
    "rain_sensors": [
        "sensor.weather_station_rain_in",
        "sensor.neighbor_weather_station_rain_in",
        "sensor.neighbor_weather_station_2_rain_in",
    ],
    "rain_threshold": 0.25,
    "rain_hours": 24,
    "rain_aggregate": "quorum",
    "rain_quorum": 2,
    "rain_window": "since_last_watering",
    "rain_max_hours": 96,
    "rain_delay_auto_hours": 48,
    "rain_stop_during_run": True,
    "rain_stop_amount": 0.05,
    "weather_entities": ["weather.krdu_daynight", "weather.openweathermap"],
    "forecast_mode": "both",
    "forecast_probability": 70,
    "forecast_amount": 0.2,
    "forecast_hours": 12,
    "forecast_quorum": 2,
    "moisture_sensors": ["sensor.a_moisture", "sensor.b_moisture"],
    "moisture_threshold": 35.0,
    "moisture_mode": "trigger",
    "moisture_unavailable": "skip",
    "temperature_sensor": "sensor.weather_station_temperature_f",
    "temperature_min": 34.0,
    "temperature_max": 95.0,
    "temperature_forecast_hours": 12,
    "wind_sensor": "sensor.weather_station_wind_avg",
    "wind_max": 15.0,
    "wind_minutes": 30,
    "occupancy_entities": ["binary_sensor.back_yard_person_occupancy"],
    "occupancy_action": "delay",
    "occupancy_max_delay_minutes": 45,
    "occupancy_stop_during_run": True,
}

# The live "Garden Bed" entry's stored shape (v0.1 keys).
GARDEN_BED: dict[str, Any] = {
    "name": "Garden Bed",
    "zones": [{"entity_id": "valve.garden_irrigation_zone", "minutes": 30}],
    "zone_mode": "sequential",
    "frequency": "interval",
    "interval_days": 2,
    "anchor": "2026-09-13",
    "start_mode": "time",
    "start_time": "06:00:00",
    "skip_conditions": ["rain", "forecast"],
    "rain_sensor": "sensor.weather_station_rain_in",
    "rain_threshold": 0.1,
    "rain_hours": 24,
    "weather_entity": "weather.krdu_daynight",
    "forecast_probability": 75,
    "forecast_hours": 12,
}

BASIC_CONFIG: dict[str, Any] = {
    "name": "Beds",
    "zones": [{"entity_id": "valve.deck_zone", "minutes": 10}],
    "zone_mode": "sequential",
    "frequency": "interval",
    "interval_days": 2,
    "anchor": "2026-09-13",
    "start_mode": "time",
    "start_time": "06:00:00",
    "skip_conditions": [],
}

AI_SETTINGS: dict[str, Any] = {
    "ai_task_entity": AI_TASK,
    "ai_notify_service": "notify.iphone",
    "ai_report_weekday": 6,
    "ai_report_time": "18:30:00",
    "ai_camera_entity": "camera.back_yard_camera",
    "ai_llmvision_provider": "llmvision_entry",
}

# Minimal step inputs; the step schemas fill in the other defaults.
CONDITION_INPUT: dict[str, dict[str, Any]] = {
    "rain": {"rain_sensors": ["sensor.daily_rain"], "rain_threshold": 0.1, "rain_hours": 24},
    "forecast": {"weather_entities": ["weather.home"], "forecast_hours": 12},
    "moisture": {
        "moisture_sensors": ["sensor.a_moisture"],
        "moisture_threshold": 40,
        "moisture_mode": "skip",
        "moisture_unavailable": "water",
    },
    "temperature": {
        "temperature_sensor": "sensor.outdoor_temperature",
        "temperature_min": 2,
        "temperature_forecast_hours": 12,
    },
    "wind": {"wind_sensor": "sensor.wind_speed", "wind_max": 15},
    "occupancy": {"occupancy_entities": ["binary_sensor.yard_person"]},
}

# Keys ai.validate_partial_config checks; the flow's output must pass it.
AI_VALIDATED_KEYS = {
    "name",
    "zones",
    "zone_mode",
    "frequency",
    "interval_days",
    "anchor",
    "weekdays",
    "interval_hours",
    "window_start",
    "window_end",
    "start_mode",
    "start_time",
    "sun_offset_minutes",
    "skip_conditions",
    "rain_sensor",
    "rain_threshold",
    "rain_hours",
    "weather_entity",
    "forecast_probability",
    "forecast_hours",
    "moisture_sensors",
    "moisture_threshold",
    "moisture_mode",
    "temperature_min",
    "temperature_max",
    "wind_max",
}

LEGACY: dict[str, Any] = {
    "config": {
        "name": "Drip irrigation",
        "frequency": "interval",
        "interval_days": 2,
        "start_mode": "time",
        "start_time": "06:00:00",
        "anchor": "2026-09-13",
        "rain_threshold": 0.1,
    },
    "zone_minutes": 30,
    "candidates": [
        {
            "config": {"name": "Grass watering", "frequency": "interval", "interval_days": 5},
            "notes": ["Grass watering is only approximated."],
            "supported": True,
            "approximate": True,
        }
    ],
    "notes": ["The helpers don't record which valves the drip schedule controlled; choose the zones."],
    "found": ["input_text.drip_irrigation_schedule", "input_number.rain_threshold"],
}

BHYVE_SUPPORTED: dict[str, Any] = {
    "source": "sensor.garden_irrigation_program_a",
    "slot": "A",
    "device": "Garden Irrigation",
    "program_switch": "switch.garden_irrigation_program_a",
    "enabled": True,
    "supported": True,
    "config": {
        "name": "Garden beds 06:00",
        "zones": [{"entity_id": "valve.deck_zone", "minutes": 13}],
        "zone_mode": "sequential",
        "frequency": "weekdays",
        "weekdays": [0, 2, 4],
        "start_mode": "time",
        "start_time": "06:00:00",
    },
    "notes": ["Zone 1 runs 12.5 minutes on the device; rounded to 13."],
}
BHYVE_UNSUPPORTED: dict[str, Any] = {
    "source": "sensor.garden_irrigation_program_b",
    "slot": "B",
    "device": "Garden Irrigation",
    "program_switch": "switch.garden_irrigation_program_b",
    "enabled": True,
    "supported": False,
    "config": {"name": "Odd days"},
    "notes": ["Odd-day programs can't be expressed as a schedule."],
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let the test hass load integrations from custom_components/."""
    return


@pytest.fixture(autouse=True)
def skip_manifest_dependencies(hass: HomeAssistant) -> None:
    """Mark manifest dependencies as loaded.

    frontend needs the hass_frontend package, which isn't installed in the test
    environment, and the flow doesn't use any of these.
    """
    for component in ("http", "frontend", "panel_custom", "websocket_api"):
        hass.config.components.add(component)


@pytest.fixture(autouse=True)
def mock_setup_entry() -> Generator[None]:
    with patch(
        "custom_components.irrigation_manager.async_setup_entry", return_value=True
    ):
        yield


@pytest.fixture(autouse=True)
def entity_states(hass: HomeAssistant) -> None:
    hass.states.async_set("valve.deck_zone", "closed", {"friendly_name": "Deck zone"})
    hass.states.async_set("switch.front_yard", "off", {"friendly_name": "Front yard"})
    hass.states.async_set("valve.garden_irrigation_zone", "closed")
    hass.states.async_set("sensor.a_moisture", "30")
    hass.states.async_set("sensor.b_moisture", "50")


def assert_config_valid(hass: HomeAssistant, config: dict[str, Any]) -> None:
    """The runner can build a schedule, and the AI validator accepts every key it covers."""
    assert isinstance(schedule_from_config(config), Schedule)
    # The validator skips empty values (e.g. no conditions) rather than keeping them.
    covered = {
        key: value
        for key, value in config.items()
        if key in AI_VALIDATED_KEYS and value not in (None, "", [], {})
    }
    validated, warnings = ai.validate_partial_config(hass, covered, today=TZ_DATE)
    assert warnings == []
    assert validated == covered


def schema_keys(result: dict[str, Any]) -> list[str]:
    return [str(key) for key in result["data_schema"].schema]


def schema_default(result: dict[str, Any], name: str) -> Any:
    for key in result["data_schema"].schema:
        if str(key) == name:
            return key.default()
    raise KeyError(name)


def schema_suggested(result: dict[str, Any], name: str) -> Any:
    for key in result["data_schema"].schema:
        if str(key) == name:
            return (key.description or {}).get("suggested_value")
    raise KeyError(name)


def schema_selector(result: dict[str, Any], name: str) -> Any:
    return next(
        value for key, value in result["data_schema"].schema.items() if str(key) == name
    )


async def start_flow(hass: HomeAssistant) -> dict[str, Any]:
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )


async def configure(hass: HomeAssistant, result: dict[str, Any], data: dict[str, Any]):
    return await hass.config_entries.flow.async_configure(result["flow_id"], data)


async def menu(hass: HomeAssistant, result: dict[str, Any], option: str):
    assert result["type"] is FlowResultType.MENU
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": option}
    )


async def start_create(hass: HomeAssistant) -> dict[str, Any]:
    result = await menu(hass, await start_flow(hass), "create")
    assert result["step_id"] == "name"
    return result


async def setup_entry(hass: HomeAssistant, **kwargs: Any) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, **kwargs)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def options_configure(hass: HomeAssistant, result: dict[str, Any], data: dict[str, Any]):
    return await hass.config_entries.options.async_configure(result["flow_id"], data)


async def options_menu(hass: HomeAssistant, result: dict[str, Any], option: str):
    assert result["type"] is FlowResultType.MENU
    return await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": option}
    )


async def skip_notifications(
    hass: HomeAssistant, result: dict[str, Any], submit: Any = configure
) -> dict[str, Any]:
    """Accept the notifications step's defaults: no notifications."""
    assert result["step_id"] == "notifications", result.get("errors")
    return await submit(hass, result, {})


async def walk_to_conditions(
    hass: HomeAssistant,
    result: dict[str, Any],
    submit: Any,
    pick: Any,
    zones: tuple[str, ...] = ("valve.deck_zone",),
) -> dict[str, Any]:
    """From the zones step to the conditions step: every 2 days at 05:00."""
    result = await submit(hass, result, {"zones": list(zones)})
    result = await submit(hass, result, {zone: 10 for zone in zones})
    result = await pick(hass, result, "interval")
    result = await submit(hass, result, {"interval_days": 2, "anchor": "2026-09-13"})
    result = await pick(hass, result, "start_time")
    result = await submit(hass, result, {"start_time": "05:00:00"})
    assert result["step_id"] == "conditions"
    return result


async def options_walk_defaults(
    hass: HomeAssistant, entry: MockConfigEntry, frequency: str, start: str
) -> dict[str, Any]:
    """Options flow up to the conditions step, accepting every default."""
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await options_configure(hass, result, {})
    result = await options_configure(hass, result, {})
    result = await options_configure(hass, result, {})
    result = await options_menu(hass, result, frequency)
    result = await options_configure(hass, result, {})
    result = await options_menu(hass, result, start)
    result = await options_configure(hass, result, {})
    assert result["step_id"] == "conditions"
    return result


async def to_condition_step(
    hass: HomeAssistant, flow: str, condition: str
) -> tuple[dict[str, Any], Any]:
    """Walk the config or options flow to `condition`'s step.

    Returns the step result and the matching submit function.
    """
    if flow == "config":
        result = await start_create(hass)
        result = await configure(hass, result, {"name": "Front lawn"})
        submit, pick = configure, menu
    else:
        entry = await setup_entry(hass, title="Front lawn", data=FULL_CONFIG)
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await options_configure(hass, result, {"name": "Front lawn"})
        submit, pick = options_configure, options_menu
    result = await walk_to_conditions(hass, result, submit, pick)
    result = await submit(hass, result, {"skip_conditions": [condition]})
    assert result["step_id"] == condition
    return result, submit


# --- config flow: menu and manual setup ---------------------------------------


async def test_user_menu_without_ai_task(hass: HomeAssistant) -> None:
    result = await start_flow(hass)
    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "user"
    assert result["menu_options"] == ["create", "import_legacy", "import_bhyve"]


async def test_user_menu_offers_describe_with_ai_task(hass: HomeAssistant) -> None:
    hass.states.async_set(AI_TASK, "unknown")
    result = await start_flow(hass)
    assert result["menu_options"] == ["create", "import_legacy", "import_bhyve", "describe"]


async def test_interval_fixed_time_single_zone(hass: HomeAssistant) -> None:
    result = await start_create(hass)
    assert result["description_placeholders"] == {"notes": ""}

    result = await configure(hass, result, {"name": "  Front lawn "})
    assert result["step_id"] == "zones"

    result = await configure(hass, result, {"zones": ["valve.deck_zone"]})
    assert result["step_id"] == "zone_minutes"
    assert schema_keys(result) == ["valve.deck_zone"]  # no zone_mode for one zone
    assert "Deck zone (valve.deck_zone)" in result["description_placeholders"]["zones"]

    result = await configure(hass, result, {"valve.deck_zone": 15})
    assert result["type"] is FlowResultType.MENU
    assert result["step_id"] == "frequency"
    assert result["menu_options"] == ["interval", "weekdays", "hourly"]

    result = await menu(hass, result, "interval")
    assert result["step_id"] == "interval"
    result = await configure(hass, result, {"interval_days": 3, "anchor": "2026-09-13"})
    assert result["step_id"] == "start"
    assert result["menu_options"] == ["start_time", "start_sunrise", "start_sunset"]

    result = await menu(hass, result, "start_time")
    result = await configure(hass, result, {"start_time": "06:30"})
    assert result["step_id"] == "conditions"
    assert schema_default(result, "stale_hours") == 0

    # No ai_task entity: the AI step is skipped.
    result = await configure(hass, result, {"skip_conditions": []})
    result = await skip_notifications(hass, result, configure)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Front lawn"
    assert result["data"] == {
        "name": "Front lawn",
        "zones": [{"entity_id": "valve.deck_zone", "minutes": 15}],
        "zone_mode": "sequential",
        "frequency": "interval",
        "interval_days": 3,
        "anchor": "2026-09-13",
        "start_mode": "time",
        "start_time": "06:30:00",
        "skip_conditions": [],
    }
    assert isinstance(result["data"]["zones"][0]["minutes"], int)

    schedule = schedule_from_config(result["data"])
    assert schedule.anchor == TZ_DATE
    assert schedule.start_time == time(6, 30)
    assert_config_valid(hass, result["data"])


async def to_hourly_step(hass: HomeAssistant) -> dict[str, Any]:
    result = await start_create(hass)
    result = await configure(hass, result, {"name": "Beds"})
    result = await configure(hass, result, {"zones": ["valve.deck_zone"]})
    result = await configure(hass, result, {"valve.deck_zone": 10})
    result = await menu(hass, result, "hourly")
    assert result["step_id"] == "hourly"
    return result


async def test_hourly_window_skips_start_menu(hass: HomeAssistant) -> None:
    result = await to_hourly_step(hass)
    assert (
        schema_default(result, "interval_hours"),
        schema_default(result, "window_start"),
        schema_default(result, "window_end"),
    ) == (3, "06:00:00", "18:00:00")

    result = await configure(
        hass, result, {"interval_hours": 3, "window_start": "06:00", "window_end": "18:00"}
    )
    assert result["step_id"] == "conditions"  # no start-time menu
    result = await configure(hass, result, {"skip_conditions": []})
    result = await skip_notifications(hass, result, configure)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        "name": "Beds",
        "zones": [{"entity_id": "valve.deck_zone", "minutes": 10}],
        "zone_mode": "sequential",
        "frequency": "hourly",
        "interval_hours": 3,
        "window_start": "06:00:00",
        "window_end": "18:00:00",
        "start_mode": "time",
        "start_time": "06:00:00",
        "skip_conditions": [],
    }
    assert_config_valid(hass, result["data"])

    tz = ZoneInfo("America/New_York")
    schedule = schedule_from_config(result["data"])
    after = datetime(2026, 9, 14, 0, 0, tzinfo=tz)
    hours = []
    for _ in range(6):
        after = next_run(schedule, after, timedelta(minutes=10), tz, lambda event, day: None)
        hours.append(after.hour)
    assert hours == [6, 9, 12, 15, 18, 6]


async def test_hourly_validation(hass: HomeAssistant) -> None:
    result = await to_hourly_step(hass)

    for end in ("06:00", "05:00"):
        result = await configure(
            hass, result, {"interval_hours": 3, "window_start": "06:00", "window_end": end}
        )
        assert result["step_id"] == "hourly"
        assert result["errors"] == {"window_end": "window_invalid"}

    result = await configure(
        hass,
        result,
        {"interval_hours": float("nan"), "window_start": "06:00", "window_end": "18:00"},
    )
    assert result["errors"] == {"interval_hours": "number_invalid"}

    for hours in (0, 24):
        with pytest.raises(InvalidData):
            await configure(
                hass,
                result,
                {"interval_hours": hours, "window_start": "06:00", "window_end": "18:00"},
            )


def without_conditions(config: dict[str, Any], *keep: str) -> dict[str, Any]:
    prefixes = tuple(
        prefix for prefix in ("rain_", "weather_", "forecast_", "moisture_") if prefix not in keep
    )
    data = {key: value for key, value in config.items() if not key.startswith(prefixes)}
    data["skip_conditions"] = [prefix.rstrip("_") for prefix in keep]
    return data


async def test_options_switch_to_hourly_and_back(hass: HomeAssistant) -> None:
    entry = await setup_entry(hass, title="Front lawn", data=without_conditions(FULL_CONFIG))

    result = await hass.config_entries.options.async_init(entry.entry_id)
    for _ in range(3):  # name, zones, run times: keep the defaults
        result = await options_configure(hass, result, {})
    result = await options_menu(hass, result, "hourly")
    result = await options_configure(
        hass, result, {"interval_hours": 2, "window_start": "07:00", "window_end": "19:00"}
    )
    assert result["step_id"] == "conditions"
    result = await options_configure(hass, result, {})
    result = await skip_notifications(hass, result, options_configure)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    # Weekdays and the sunrise offset are gone.
    assert entry.options == {
        "name": "Front lawn",
        "zones": FULL_CONFIG["zones"],
        "zone_mode": "concurrent",
        "frequency": "hourly",
        "interval_hours": 2,
        "window_start": "07:00:00",
        "window_end": "19:00:00",
        "start_mode": "time",
        "start_time": "07:00:00",
        "skip_conditions": [],
    }

    result = await hass.config_entries.options.async_init(entry.entry_id)
    for _ in range(3):
        result = await options_configure(hass, result, {})
    result = await options_menu(hass, result, "interval")
    result = await options_configure(hass, result, {"interval_days": 2, "anchor": "2026-09-14"})
    result = await options_menu(hass, result, "start_time")
    assert schema_default(result, "start_time") == "07:00:00"
    result = await options_configure(hass, result, {})
    result = await options_configure(hass, result, {})
    result = await skip_notifications(hass, result, options_configure)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    # The hourly keys are gone.
    assert entry.options == {
        "name": "Front lawn",
        "zones": FULL_CONFIG["zones"],
        "zone_mode": "concurrent",
        "frequency": "interval",
        "interval_days": 2,
        "anchor": "2026-09-14",
        "start_mode": "time",
        "start_time": "07:00:00",
        "skip_conditions": [],
    }


async def test_hourly_rejects_moisture_trigger_mode(hass: HomeAssistant) -> None:
    data = without_conditions(FULL_CONFIG, "moisture_")
    assert data["moisture_mode"] == "trigger"
    entry = await setup_entry(hass, title="Front lawn", data=data)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    for _ in range(3):
        result = await options_configure(hass, result, {})
    result = await options_menu(hass, result, "hourly")
    result = await options_configure(hass, result, {})
    assert result["step_id"] == "conditions"
    result = await options_configure(hass, result, {})
    assert result["step_id"] == "moisture"

    result = await options_configure(hass, result, {})
    assert result["step_id"] == "moisture"
    assert result["errors"] == {"moisture_mode": "moisture_trigger_hourly"}

    result = await options_configure(hass, result, {"moisture_mode": "skip"})
    result = await skip_notifications(hass, result, options_configure)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["frequency"] == "hourly"
    assert entry.options["moisture_mode"] == "skip"


async def test_every_v02_setting(hass: HomeAssistant) -> None:
    result = await start_create(hass)
    result = await configure(hass, result, {"name": "Front lawn"})
    result = await configure(
        hass, result, {"zones": ["valve.deck_zone", "switch.front_yard"]}
    )
    assert schema_keys(result) == ["valve.deck_zone", "switch.front_yard", "zone_mode"]
    result = await configure(
        hass,
        result,
        {"valve.deck_zone": 10, "switch.front_yard": 20, "zone_mode": "concurrent"},
    )
    result = await menu(hass, result, "weekdays")
    result = await configure(hass, result, {"weekdays": ["4", "0", "2"]})
    result = await menu(hass, result, "start_sunrise")
    result = await configure(hass, result, {"sun_offset_minutes": -15})

    # Selection order doesn't matter; sub-steps follow the SkipCondition order.
    result = await configure(
        hass,
        result,
        {
            "skip_conditions": ["occupancy", "wind", "temperature", "moisture", "forecast", "rain"],
            "stale_hours": 6,
        },
    )
    assert result["step_id"] == "rain"
    assert schema_default(result, "rain_aggregate") == "max"
    assert schema_default(result, "rain_window") == "hours"
    result = await configure(
        hass,
        result,
        {
            "rain_sensors": V02_CONFIG["rain_sensors"],
            "rain_threshold": 0.25,
            "rain_hours": 24,
            "rain_aggregate": "quorum",
            "rain_quorum": 2,
            "rain_window": "since_last_watering",
            "rain_max_hours": 96,
            "rain_delay_auto_hours": 48,
            "rain_stop_during_run": True,
            "rain_stop_amount": 0.05,
        },
    )
    assert result["step_id"] == "forecast"
    result = await configure(
        hass,
        result,
        {
            "weather_entities": V02_CONFIG["weather_entities"],
            "forecast_mode": "both",
            "forecast_probability": 70,
            "forecast_amount": 0.2,
            "forecast_hours": 12,
            "forecast_quorum": 2,
        },
    )
    assert result["step_id"] == "moisture"
    result = await configure(
        hass,
        result,
        {
            "moisture_sensors": ["sensor.a_moisture", "sensor.b_moisture"],
            "moisture_threshold": 35,
            "moisture_mode": "trigger",
            "moisture_unavailable": "skip",
        },
    )
    assert result["step_id"] == "temperature"
    # Forecast is on, so its weather entities feed the forecast low.
    assert "weather_entities" not in schema_keys(result)
    result = await configure(
        hass,
        result,
        {
            "temperature_sensor": "sensor.weather_station_temperature_f",
            "temperature_min": 34,
            "temperature_max": 95,
            "temperature_forecast_hours": 12,
        },
    )
    assert result["step_id"] == "wind"
    result = await configure(
        hass, result, {"wind_sensor": "sensor.weather_station_wind_avg", "wind_max": 15}
    )
    assert result["step_id"] == "occupancy"
    assert schema_default(result, "occupancy_stop_during_run") is True
    result = await configure(
        hass,
        result,
        {
            "occupancy_entities": ["binary_sensor.back_yard_person_occupancy"],
            "occupancy_action": "delay",
            "occupancy_max_delay_minutes": 45,
        },
    )
    result = await skip_notifications(hass, result, configure)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == V02_CONFIG

    schedule = schedule_from_config(result["data"])
    assert schedule.weekdays == frozenset({0, 2, 4})
    assert schedule.check_every_day
    assert_config_valid(hass, result["data"])


async def test_condition_steps_skip_unselected(hass: HomeAssistant) -> None:
    result = await start_create(hass)
    result = await configure(hass, result, {"name": "Beds"})
    result = await configure(hass, result, {"zones": ["valve.deck_zone"]})
    result = await configure(hass, result, {"valve.deck_zone": 5})
    result = await menu(hass, result, "weekdays")
    result = await configure(hass, result, {"weekdays": ["6"]})
    result = await menu(hass, result, "start_sunset")
    result = await configure(hass, result, {"sun_offset_minutes": 30})
    result = await configure(hass, result, {"skip_conditions": ["moisture", "rain"]})
    assert result["step_id"] == "rain"
    result = await configure(hass, result, CONDITION_INPUT["rain"])
    assert result["step_id"] == "moisture"
    result = await configure(hass, result, CONDITION_INPUT["moisture"])
    result = await skip_notifications(hass, result, configure)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    data = result["data"]
    assert data["skip_conditions"] == ["rain", "moisture"]
    assert data["start_mode"] == "sunset"
    # Off-by-default rain settings are left out of the stored config.
    assert {key for key in data if key.startswith("rain_")} == {
        "rain_sensors",
        "rain_threshold",
        "rain_hours",
        "rain_aggregate",
        "rain_window",
    }
    assert not {"weather_entity", "weather_entities", "forecast_probability", "stale_hours"} & data.keys()
    assert not schedule_from_config(data).check_every_day
    assert_config_valid(hass, data)


# --- config flow: validation --------------------------------------------------


async def test_duplicate_name_rejected_case_insensitive(hass: HomeAssistant) -> None:
    MockConfigEntry(domain=DOMAIN, title="Front Lawn", data={}).add_to_hass(hass)
    result = await start_create(hass)
    result = await configure(hass, result, {"name": "front lawn"})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "name"
    assert result["errors"] == {"name": "name_exists"}


async def test_blank_name_rejected(hass: HomeAssistant) -> None:
    result = await start_create(hass)
    result = await configure(hass, result, {"name": "   "})
    assert result["errors"] == {"name": "name_required"}


async def test_no_zones_rejected(hass: HomeAssistant) -> None:
    result = await start_create(hass)
    result = await configure(hass, result, {"name": "Front lawn"})
    result = await configure(hass, result, {"zones": []})
    assert result["step_id"] == "zones"
    assert result["errors"] == {"zones": "no_zones"}


async def test_nan_zone_minutes_rejected(hass: HomeAssistant) -> None:
    result = await start_create(hass)
    result = await configure(hass, result, {"name": "Front lawn"})
    result = await configure(hass, result, {"zones": ["valve.deck_zone"]})
    result = await configure(hass, result, {"valve.deck_zone": float("nan")})
    assert result["step_id"] == "zone_minutes"
    assert result["errors"] == {"valve.deck_zone": "number_invalid"}


async def test_no_weekdays_rejected(hass: HomeAssistant) -> None:
    result = await start_create(hass)
    result = await configure(hass, result, {"name": "Front lawn"})
    result = await configure(hass, result, {"zones": ["valve.deck_zone"]})
    result = await configure(hass, result, {"valve.deck_zone": 10})
    result = await menu(hass, result, "weekdays")
    result = await configure(hass, result, {"weekdays": []})
    assert result["step_id"] == "weekdays"
    assert result["errors"] == {"weekdays": "no_weekdays"}


async def test_nan_stale_hours_rejected(hass: HomeAssistant) -> None:
    result = await start_create(hass)
    result = await configure(hass, result, {"name": "Front lawn"})
    result = await walk_to_conditions(hass, result, configure, menu)
    result = await configure(hass, result, {"skip_conditions": [], "stale_hours": float("nan")})
    assert result["step_id"] == "conditions"
    assert result["errors"] == {"stale_hours": "number_invalid"}


async def test_no_moisture_sensors_rejected(hass: HomeAssistant) -> None:
    result, _ = await to_condition_step(hass, "config", "moisture")
    result = await configure(
        hass, result, {**CONDITION_INPUT["moisture"], "moisture_sensors": []}
    )
    assert result["step_id"] == "moisture"
    assert result["errors"] == {"moisture_sensors": "no_moisture_sensors"}


def rain_input(threshold: float) -> dict[str, Any]:
    return {**CONDITION_INPUT["rain"], "rain_threshold": threshold}


async def test_rain_threshold_zero_rejected_by_selector(hass: HomeAssistant) -> None:
    result, _ = await to_condition_step(hass, "config", "rain")
    selector = schema_selector(result, "rain_threshold")
    assert selector.config["min"] == 0.01
    assert selector.config["step"] == 0.01
    with pytest.raises(InvalidData):
        await configure(hass, result, rain_input(0))


async def test_rain_threshold_nan_rejected_then_minimum_accepted(hass: HomeAssistant) -> None:
    result, _ = await to_condition_step(hass, "config", "rain")
    # NaN passes the selector's range check; the step rejects it.
    result = await configure(hass, result, rain_input(float("nan")))
    assert result["step_id"] == "rain"
    assert result["errors"] == {"rain_threshold": "rain_threshold_invalid"}

    result = await configure(hass, result, rain_input(0.01))
    result = await skip_notifications(hass, result, configure)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["rain_threshold"] == 0.01


async def test_rain_validation_branches(hass: HomeAssistant) -> None:
    result, _ = await to_condition_step(hass, "config", "rain")

    result = await configure(hass, result, {**CONDITION_INPUT["rain"], "rain_sensors": []})
    assert result["errors"] == {"rain_sensors": "no_rain_sensors"}

    result = await configure(
        hass,
        result,
        {**CONDITION_INPUT["rain"], "rain_aggregate": "quorum", "rain_quorum": float("nan")},
    )
    assert result["errors"] == {"rain_quorum": "rain_quorum_invalid"}

    result = await configure(
        hass,
        result,
        {**CONDITION_INPUT["rain"], "rain_stop_during_run": True, "rain_stop_amount": 0},
    )
    assert result["errors"] == {"rain_stop_amount": "rain_stop_amount_invalid"}

    result = await configure(
        hass, result, {**CONDITION_INPUT["rain"], "rain_hours": float("nan")}
    )
    assert result["errors"] == {"rain_hours": "number_invalid"}

    # Quorum and stop amount are only checked when they're used.
    result = await configure(
        hass,
        result,
        {
            **CONDITION_INPUT["rain"],
            "rain_aggregate": "median",
            "rain_quorum": float("nan"),
            "rain_stop_amount": 0,
        },
    )
    result = await skip_notifications(hass, result, configure)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    data = result["data"]
    assert data["rain_aggregate"] == "median"
    assert not {"rain_quorum", "rain_stop_amount", "rain_stop_during_run", "rain_max_hours"} & data.keys()


# field, error key, other inputs for the step, selector step
THRESHOLD_STEPS: dict[str, tuple[str, str, dict[str, Any], float]] = {
    "forecast": (
        "forecast_probability",
        "forecast_probability_invalid",
        {"weather_entities": ["weather.home"], "forecast_hours": 12},
        1,
    ),
    "moisture": (
        "moisture_threshold",
        "moisture_threshold_invalid",
        {
            "moisture_sensors": ["sensor.a_moisture"],
            "moisture_mode": "skip",
            "moisture_unavailable": "water",
        },
        0.1,
    ),
}


@pytest.mark.parametrize("flow", ["config", "options"])
@pytest.mark.parametrize("condition", ["forecast", "moisture"])
async def test_threshold_minimum_enforced(hass: HomeAssistant, flow: str, condition: str) -> None:
    field, error, other, step = THRESHOLD_STEPS[condition]
    result, submit = await to_condition_step(hass, flow, condition)
    selector = schema_selector(result, field)
    assert (selector.config["min"], selector.config["max"]) == (1, 100)
    assert selector.config["step"] == step

    with pytest.raises(InvalidData):
        await submit(hass, result, {**other, field: 0})

    # NaN passes the selector's range check; the step rejects it.
    result = await submit(hass, result, {**other, field: float("nan")})
    assert result["step_id"] == condition
    assert result["errors"] == {field: error}

    result = await submit(hass, result, {**other, field: 1})
    result = await skip_notifications(hass, result, submit)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][field] == 1
    assert result["data"]["skip_conditions"] == [condition]


async def test_forecast_validation_branches(hass: HomeAssistant) -> None:
    result, _ = await to_condition_step(hass, "config", "forecast")
    assert schema_default(result, "forecast_mode") == "probability"
    assert (
        schema_selector(result, "forecast_amount").config["unit_of_measurement"]
        == hass.config.units.accumulated_precipitation_unit
    )

    result = await configure(hass, result, {"weather_entities": [], "forecast_hours": 12})
    assert result["errors"] == {"weather_entities": "no_weather_entities"}

    result = await configure(hass, result, {**CONDITION_INPUT["forecast"], "forecast_quorum": 2})
    assert result["errors"] == {"forecast_quorum": "forecast_quorum_invalid"}

    result = await configure(
        hass,
        result,
        {**CONDITION_INPUT["forecast"], "forecast_mode": "amount", "forecast_amount": 0},
    )
    assert result["errors"] == {"forecast_amount": "forecast_amount_invalid"}

    # Amount only: the probability isn't checked or stored.
    result = await configure(
        hass,
        result,
        {
            **CONDITION_INPUT["forecast"],
            "forecast_mode": "amount",
            "forecast_probability": float("nan"),
            "forecast_amount": 0.3,
        },
    )
    result = await skip_notifications(hass, result, configure)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    data = result["data"]
    assert data["forecast_mode"] == "amount"
    assert data["forecast_amount"] == 0.3
    assert not {"forecast_probability", "forecast_quorum", "weather_entity"} & data.keys()


async def test_temperature_validation_branches(hass: HomeAssistant) -> None:
    result, _ = await to_condition_step(hass, "config", "temperature")
    # Forecast is off, so the step asks for weather entities itself.
    assert "weather_entities" in schema_keys(result)

    result = await configure(hass, result, {"temperature_forecast_hours": 12})
    assert result["errors"] == {"base": "temperature_limit_required"}

    sensor = {"temperature_sensor": "sensor.outdoor_temperature"}
    result = await configure(hass, result, {**sensor, "temperature_min": 10, "temperature_max": 5})
    assert result["errors"] == {"base": "temperature_range_invalid"}

    result = await configure(hass, result, {**sensor, "temperature_min": float("nan")})
    assert result["errors"] == {"temperature_min": "temperature_invalid"}

    result = await configure(
        hass,
        result,
        {"temperature_max": 90, "weather_entities": ["weather.home"], "temperature_forecast_hours": 12},
    )
    assert result["errors"] == {"temperature_sensor": "temperature_max_needs_sensor"}

    result = await configure(hass, result, {"temperature_min": 2})
    assert result["errors"] == {"base": "temperature_source_required"}

    result = await configure(
        hass,
        result,
        {"temperature_min": 2, "weather_entities": ["weather.home"], "temperature_forecast_hours": 0},
    )
    assert result["errors"] == {"base": "temperature_source_required"}

    result = await configure(
        hass,
        result,
        {"temperature_min": 2, "weather_entities": ["weather.home"], "temperature_forecast_hours": 12},
    )
    result = await skip_notifications(hass, result, configure)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    data = result["data"]
    assert data["temperature_min"] == 2.0
    assert data["temperature_forecast_hours"] == 12
    assert data["weather_entities"] == ["weather.home"]
    assert not {"temperature_sensor", "temperature_max"} & data.keys()


async def test_wind_validation(hass: HomeAssistant) -> None:
    result, _ = await to_condition_step(hass, "config", "wind")
    with pytest.raises(InvalidData):
        await configure(hass, result, {**CONDITION_INPUT["wind"], "wind_max": 0})

    result = await configure(hass, result, {**CONDITION_INPUT["wind"], "wind_max": float("nan")})
    assert result["errors"] == {"wind_max": "wind_max_invalid"}

    result = await configure(hass, result, CONDITION_INPUT["wind"])
    result = await skip_notifications(hass, result, configure)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert {key: result["data"][key] for key in ("wind_sensor", "wind_max", "wind_minutes")} == {
        "wind_sensor": "sensor.wind_speed",
        "wind_max": 15.0,
        "wind_minutes": 30,
    }


async def test_occupancy_validation_and_skip_action(hass: HomeAssistant) -> None:
    result, _ = await to_condition_step(hass, "config", "occupancy")
    result = await configure(hass, result, {"occupancy_entities": []})
    assert result["errors"] == {"occupancy_entities": "no_occupancy_entities"}

    result = await configure(
        hass,
        result,
        {
            **CONDITION_INPUT["occupancy"],
            "occupancy_action": "skip",
            "occupancy_stop_during_run": False,
        },
    )
    result = await skip_notifications(hass, result, configure)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    data = result["data"]
    assert data["occupancy_action"] == "skip"
    assert not {"occupancy_max_delay_minutes", "occupancy_stop_during_run"} & data.keys()


# --- config flow: AI step -------------------------------------------------------


async def test_ai_step_validation_and_save(hass: HomeAssistant) -> None:
    hass.states.async_set(AI_TASK, "unknown")

    async def _notify(call: ServiceCall) -> None:
        return None

    hass.services.async_register("notify", "iphone", _notify)
    hass.services.async_register("notify", "send_message", _notify)

    result = await start_create(hass)
    result = await configure(hass, result, {"name": "Beds"})
    result = await walk_to_conditions(hass, result, configure, menu)
    result = await configure(hass, result, {"skip_conditions": []})
    assert result["step_id"] == "ai"
    assert schema_selector(result, "ai_notify_service").config["options"] == [
        "persistent_notification.create",
        "notify.iphone",
    ]

    base = {"ai_task_entity": AI_TASK}
    result = await configure(hass, result, {**base, "ai_report_weekday": "6"})
    assert result["errors"] == {"base": "ai_report_incomplete"}

    result = await configure(hass, result, {**base, "ai_camera_entity": "camera.back_yard_camera"})
    assert result["errors"] == {"ai_llmvision_provider": "ai_provider_required"}

    result = await configure(
        hass,
        result,
        {
            **base,
            "ai_notify_service": "notify.iphone",
            "ai_report_weekday": "6",
            "ai_report_time": "18:30",
            "ai_camera_entity": "camera.back_yard_camera",
            "ai_llmvision_provider": "llmvision_entry",
        },
    )
    result = await skip_notifications(hass, result, configure)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert {key: value for key, value in result["data"].items() if key.startswith("ai_")} == AI_SETTINGS


async def test_options_empty_ai_task_removes_ai_settings(hass: HomeAssistant) -> None:
    hass.states.async_set(AI_TASK, "unknown")
    entry = await setup_entry(hass, title="Beds", data={**BASIC_CONFIG, **AI_SETTINGS})
    result = await options_walk_defaults(hass, entry, "interval", "start_time")
    result = await options_configure(hass, result, {})
    assert result["step_id"] == "ai"
    assert schema_suggested(result, "ai_task_entity") == AI_TASK
    assert schema_suggested(result, "ai_report_weekday") == "6"
    # A stored notify service stays selectable even though it isn't registered.
    assert "notify.iphone" in schema_selector(result, "ai_notify_service").config["options"]

    result = await options_configure(hass, result, {})
    result = await skip_notifications(hass, result, options_configure)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == BASIC_CONFIG


async def test_options_without_ai_task_keeps_ai_settings(hass: HomeAssistant) -> None:
    entry = await setup_entry(hass, title="Beds", data={**BASIC_CONFIG, **AI_SETTINGS})
    result = await options_walk_defaults(hass, entry, "interval", "start_time")
    result = await options_configure(hass, result, {})
    result = await skip_notifications(hass, result, options_configure)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {**BASIC_CONFIG, **AI_SETTINGS}


# --- config flow: imports and describe -----------------------------------------


async def test_import_legacy_helpers_prefills_steps(hass: HomeAssistant) -> None:
    with patch(READ_LEGACY, return_value=deepcopy(LEGACY)):
        result = await menu(hass, await start_flow(hass), "import_legacy")
        assert result["step_id"] == "import_legacy"
        placeholders = result["description_placeholders"]
        assert "input_text.drip_irrigation_schedule" in placeholders["found"]
        assert "choose the zones" in placeholders["notes"]
        assert "Grass watering (not imported)" in placeholders["notes"]

        result = await configure(hass, result, {})
        assert result["step_id"] == "name"
        assert schema_default(result, "name") == "Drip irrigation"
        assert "choose the zones" in result["description_placeholders"]["notes"]

        result = await configure(hass, result, {})
        assert schema_default(result, "zones") == []
        result = await configure(hass, result, {"zones": ["valve.deck_zone"]})
        assert schema_default(result, "valve.deck_zone") == 30
        result = await configure(hass, result, {})
        result = await menu(hass, result, "interval")
        assert schema_default(result, "interval_days") == 2
        assert schema_default(result, "anchor") == "2026-09-13"
        result = await configure(hass, result, {})
        result = await menu(hass, result, "start_time")
        assert schema_default(result, "start_time") == "06:00:00"
        result = await configure(hass, result, {})
        # The imported threshold has no sensor, so rain isn't turned on...
        assert schema_default(result, "skip_conditions") == []
        result = await configure(hass, result, {"skip_conditions": ["rain"]})
        # ...but it is the rain step's default.
        assert schema_default(result, "rain_threshold") == 0.1
        result = await configure(hass, result, {"rain_sensors": ["sensor.weather_station_rain_in"]})

    result = await skip_notifications(hass, result, configure)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == {
        "name": "Drip irrigation",
        "zones": [{"entity_id": "valve.deck_zone", "minutes": 30}],
        "zone_mode": "sequential",
        "frequency": "interval",
        "interval_days": 2,
        "anchor": "2026-09-13",
        "start_mode": "time",
        "start_time": "06:00:00",
        "skip_conditions": ["rain"],
        "rain_sensors": ["sensor.weather_station_rain_in"],
        "rain_threshold": 0.1,
        "rain_hours": 24,
        "rain_aggregate": "max",
        "rain_window": "hours",
    }
    assert_config_valid(hass, result["data"])


async def test_import_legacy_threshold_not_stored_without_rain(hass: HomeAssistant) -> None:
    with patch(READ_LEGACY, return_value=deepcopy(LEGACY)):
        result = await menu(hass, await start_flow(hass), "import_legacy")
        result = await configure(hass, result, {})
        result = await configure(hass, result, {})
        result = await walk_to_conditions(hass, result, configure, menu)
        result = await configure(hass, result, {"skip_conditions": []})
    result = await skip_notifications(hass, result, configure)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert "rain_threshold" not in result["data"]


async def test_import_legacy_nothing_found_aborts(hass: HomeAssistant) -> None:
    empty = {"config": {}, "zone_minutes": None, "candidates": [], "notes": ["none"], "found": []}
    with patch(READ_LEGACY, return_value=empty):
        result = await menu(hass, await start_flow(hass), "import_legacy")
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_legacy_helpers"


async def bhyve_to_final_step(
    hass: HomeAssistant, candidates: list[dict[str, Any]]
) -> dict[str, Any]:
    """Copy the first supported candidate and accept every default."""
    with patch(READ_BHYVE, return_value=deepcopy(candidates)):
        result = await menu(hass, await start_flow(hass), "import_bhyve")
        assert result["step_id"] == "import_bhyve"
        result = await configure(hass, result, {"program": "0"})
    assert result["step_id"] == "name"
    assert schema_default(result, "name") == "Garden beds 06:00"
    assert "rounded to 13" in result["description_placeholders"]["notes"]
    result = await configure(hass, result, {})
    assert schema_default(result, "zones") == ["valve.deck_zone"]
    result = await configure(hass, result, {})
    assert schema_default(result, "valve.deck_zone") == 13
    result = await configure(hass, result, {})
    result = await menu(hass, result, "weekdays")
    assert schema_default(result, "weekdays") == ["0", "2", "4"]
    result = await configure(hass, result, {})
    result = await menu(hass, result, "start_time")
    result = await configure(hass, result, {})
    result = await configure(hass, result, {"skip_conditions": []})
    if result.get("step_id") == "ai":  # only shown when an ai_task entity exists
        result = await configure(hass, result, {})
    return await skip_notifications(hass, result)


BHYVE_DATA = {**BHYVE_SUPPORTED["config"], "skip_conditions": []}


async def test_import_bhyve_lists_programs(hass: HomeAssistant) -> None:
    with patch(READ_BHYVE, return_value=[deepcopy(BHYVE_UNSUPPORTED), deepcopy(BHYVE_SUPPORTED)]):
        result = await menu(hass, await start_flow(hass), "import_bhyve")
    assert schema_selector(result, "program").config["options"] == [
        {"value": "0", "label": "Garden beds 06:00 (program A)"}
    ]
    assert "Odd-day programs" in result["description_placeholders"]["unsupported"]


async def test_import_bhyve_disable_unticked_leaves_device_alone(hass: HomeAssistant) -> None:
    with patch(DISABLE_BHYVE, new=AsyncMock()) as disable:
        result = await bhyve_to_final_step(hass, [BHYVE_UNSUPPORTED, BHYVE_SUPPORTED])
        assert result["step_id"] == "bhyve_disable"
        assert result["description_placeholders"]["switch"] == "switch.garden_irrigation_program_a"
        assert schema_default(result, "disable_program") is False
        result = await configure(hass, result, {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == BHYVE_DATA
    disable.assert_not_awaited()
    assert_config_valid(hass, result["data"])


async def test_import_bhyve_disable_ticked_turns_program_off(hass: HomeAssistant) -> None:
    with patch(
        DISABLE_BHYVE, new=AsyncMock(side_effect=[HomeAssistantError("device offline"), None])
    ) as disable:
        result = await bhyve_to_final_step(hass, [BHYVE_SUPPORTED])
        result = await configure(hass, result, {"disable_program": True})
        assert result["step_id"] == "bhyve_disable"
        assert result["errors"] == {"base": "disable_failed"}
        assert result["description_placeholders"]["error"] == "device offline"

        result = await configure(hass, result, {"disable_program": True})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == BHYVE_DATA
    assert disable.await_count == 2
    disable.assert_awaited_with(hass, "switch.garden_irrigation_program_a")


async def test_import_bhyve_without_program_switch_skips_disable_step(hass: HomeAssistant) -> None:
    candidate = {**deepcopy(BHYVE_SUPPORTED), "program_switch": None}
    with patch(DISABLE_BHYVE, new=AsyncMock()) as disable:
        result = await bhyve_to_final_step(hass, [candidate])
    assert result["type"] is FlowResultType.CREATE_ENTRY
    disable.assert_not_awaited()


async def test_import_bhyve_nothing_supported_aborts(hass: HomeAssistant) -> None:
    with patch(READ_BHYVE, return_value=[deepcopy(BHYVE_UNSUPPORTED)]):
        result = await menu(hass, await start_flow(hass), "import_bhyve")
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_bhyve_programs"
    assert "Odd-day programs" in result["description_placeholders"]["programs"]


PARSED = {
    "config": {
        "name": "Garden",
        "zones": [{"entity_id": "valve.deck_zone", "minutes": 20}],
        "frequency": "weekdays",
        "weekdays": [0, 3],
        "start_mode": "time",
        "start_time": "06:00:00",
        "skip_conditions": ["rain"],
        "rain_sensor": "sensor.weather_station_rain_in",
        "rain_threshold": 0.2,
    },
    "warnings": ["rain_hours: 500 ignored (must be between 1 and 72)"],
}


async def test_describe_prefills_steps_and_shows_warnings(hass: HomeAssistant) -> None:
    hass.states.async_set(AI_TASK, "unknown")
    text = "water the deck zone 20 minutes Monday and Thursday at 6, skip after rain"
    with patch(PARSE_DESCRIPTION, new=AsyncMock(return_value=deepcopy(PARSED))) as parse:
        result = await menu(hass, await start_flow(hass), "describe")
        assert result["step_id"] == "describe"
        assert schema_default(result, "ai_task_entity") == AI_TASK
        result = await configure(hass, result, {"ai_task_entity": AI_TASK, "description": text})
    parse.assert_awaited_once_with(hass, AI_TASK, text)

    assert result["step_id"] == "name"
    assert schema_default(result, "name") == "Garden"
    assert "rain_hours: 500 ignored" in result["description_placeholders"]["notes"]
    result = await configure(hass, result, {})
    result = await configure(hass, result, {})
    assert schema_default(result, "valve.deck_zone") == 20
    result = await configure(hass, result, {})
    result = await menu(hass, result, "weekdays")
    assert schema_default(result, "weekdays") == ["0", "3"]
    result = await configure(hass, result, {})
    result = await menu(hass, result, "start_time")
    result = await configure(hass, result, {})
    assert schema_default(result, "skip_conditions") == ["rain"]
    result = await configure(hass, result, {})
    assert schema_default(result, "rain_sensors") == ["sensor.weather_station_rain_in"]
    assert schema_default(result, "rain_threshold") == 0.2
    result = await configure(hass, result, {})
    assert result["step_id"] == "ai"
    # The AI task used for the description is offered, not saved.
    assert schema_suggested(result, "ai_task_entity") == AI_TASK
    result = await configure(hass, result, {})
    result = await skip_notifications(hass, result, configure)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    data = result["data"]
    assert data["rain_sensors"] == ["sensor.weather_station_rain_in"]
    assert "rain_sensor" not in data
    assert not {key for key in data if key.startswith("ai_")}
    assert_config_valid(hass, data)


async def test_describe_error_shown_on_form(hass: HomeAssistant) -> None:
    hass.states.async_set(AI_TASK, "unknown")
    with patch(PARSE_DESCRIPTION, new=AsyncMock(side_effect=HomeAssistantError("model offline"))):
        result = await menu(hass, await start_flow(hass), "describe")
        result = await configure(hass, result, {"ai_task_entity": AI_TASK, "description": "water"})
    assert result["step_id"] == "describe"
    assert result["errors"] == {"base": "describe_failed"}
    assert result["description_placeholders"] == {"error": "model offline"}
    assert schema_default(result, "description") == "water"


# --- config flow: copy a schedule ---------------------------------------------


async def test_user_menu_offers_copy_with_a_schedule(hass: HomeAssistant) -> None:
    await setup_entry(hass, title="Front lawn", data=V02_CONFIG)
    result = await start_flow(hass)
    assert result["menu_options"] == ["create", "copy", "import_legacy", "import_bhyve"]


async def test_copy_prefills_every_step(hass: HomeAssistant) -> None:
    result = await start_create(hass)
    result = await configure(hass, result, {"name": "Front lawn"})
    result = await walk_to_conditions(
        hass, result, configure, menu, zones=("valve.deck_zone", "switch.front_yard")
    )
    result = await configure(hass, result, {"skip_conditions": ["rain", "moisture"]})
    result = await configure(hass, result, CONDITION_INPUT["rain"])
    result = await configure(hass, result, CONDITION_INPUT["moisture"])
    result = await skip_notifications(hass, result)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    source = hass.config_entries.async_entries(DOMAIN)[0]

    result = await menu(hass, await start_flow(hass), "copy")
    assert result["step_id"] == "copy"
    assert schema_selector(result, "schedule").config["options"] == [
        {"value": source.entry_id, "label": "Front lawn"}
    ]
    result = await configure(hass, result, {"schedule": source.entry_id})
    assert result["step_id"] == "name"
    assert schema_default(result, "name") == "Front lawn (copy)"
    result = await configure(hass, result, {})
    assert schema_default(result, "zones") == ["valve.deck_zone", "switch.front_yard"]
    result = await configure(hass, result, {})
    result = await configure(hass, result, {})
    result = await menu(hass, result, "interval")
    result = await configure(hass, result, {})
    result = await menu(hass, result, "start_time")
    result = await configure(hass, result, {})
    assert schema_default(result, "skip_conditions") == ["rain", "moisture"]
    result = await configure(hass, result, {})
    result = await configure(hass, result, {})
    result = await configure(hass, result, {})
    result = await skip_notifications(hass, result)

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Front lawn (copy)"
    assert result["data"] == {**source.data, "name": "Front lawn (copy)"}
    assert_config_valid(hass, result["data"])


async def test_copy_reads_options_and_numbers_taken_names(hass: HomeAssistant) -> None:
    await setup_entry(hass, title="Front lawn (copy)", data=FULL_CONFIG)
    edited = {**FULL_CONFIG, "zones": [{"entity_id": "valve.deck_zone", "minutes": 25}]}
    source = await setup_entry(
        hass, title="Front lawn", data=FULL_CONFIG, options=edited
    )

    result = await menu(hass, await start_flow(hass), "copy")
    # Listed by name, the first one picked by default.
    assert [option["label"] for option in schema_selector(result, "schedule").config["options"]] == [
        "Front lawn",
        "Front lawn (copy)",
    ]
    assert schema_default(result, "schedule") == source.entry_id
    result = await configure(hass, result, {})
    assert schema_default(result, "name") == "Front lawn (copy 2)"
    result = await configure(hass, result, {})
    assert schema_default(result, "zones") == ["valve.deck_zone"]
    result = await configure(hass, result, {})
    assert schema_default(result, "valve.deck_zone") == 25


async def test_copy_deleted_schedule_shows_the_form_again(hass: HomeAssistant) -> None:
    MockConfigEntry(domain=DOMAIN, title="Back yard", data=FULL_CONFIG).add_to_hass(hass)
    source = MockConfigEntry(domain=DOMAIN, title="Front lawn", data=FULL_CONFIG)
    source.add_to_hass(hass)
    result = await menu(hass, await start_flow(hass), "copy")
    await hass.config_entries.async_remove(source.entry_id)
    result = await configure(hass, result, {"schedule": source.entry_id})
    assert result["step_id"] == "copy"
    assert [option["label"] for option in schema_selector(result, "schedule").config["options"]] == [
        "Back yard"
    ]


async def test_copy_without_schedules_aborts(hass: HomeAssistant) -> None:
    flow = config_flow.IrrigationManagerConfigFlow()
    flow.hass = hass
    result = await flow.async_step_copy()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_schedules"


# --- options flow -------------------------------------------------------------


async def test_options_change_frequency_drop_condition_rename(hass: HomeAssistant) -> None:
    entry = await setup_entry(hass, title="Front lawn", data=FULL_CONFIG)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"
    assert schema_default(result, "name") == "Front lawn"

    result = await options_configure(hass, result, {"name": "Back lawn"})
    assert result["step_id"] == "zones"
    assert schema_default(result, "zones") == ["valve.deck_zone", "switch.front_yard"]

    result = await options_configure(hass, result, {"zones": ["valve.deck_zone"]})
    assert schema_default(result, "valve.deck_zone") == 10  # existing minutes kept
    result = await options_configure(hass, result, {"valve.deck_zone": 12})

    result = await options_menu(hass, result, "interval")
    result = await options_configure(
        hass, result, {"interval_days": 2, "anchor": "2026-09-14"}
    )
    result = await options_menu(hass, result, "start_time")
    result = await options_configure(hass, result, {"start_time": "05:45:00"})

    assert schema_default(result, "skip_conditions") == ["rain", "forecast", "moisture"]
    result = await options_configure(hass, result, {"skip_conditions": ["moisture"]})
    assert result["step_id"] == "moisture"
    assert schema_default(result, "moisture_mode") == "trigger"
    assert schema_default(result, "moisture_sensors") == [
        "sensor.a_moisture",
        "sensor.b_moisture",
    ]
    result = await options_configure(
        hass,
        result,
        {
            "moisture_sensors": ["sensor.a_moisture"],
            "moisture_threshold": 30,
            "moisture_mode": "skip",
            "moisture_unavailable": "water",
        },
    )
    result = await skip_notifications(hass, result, options_configure)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    assert entry.title == "Back lawn"
    assert entry.options == {
        "name": "Back lawn",
        "zones": [{"entity_id": "valve.deck_zone", "minutes": 12}],
        "zone_mode": "sequential",
        "frequency": "interval",
        "interval_days": 2,
        "anchor": "2026-09-14",
        "start_mode": "time",
        "start_time": "05:45:00",
        "skip_conditions": ["moisture"],
        "moisture_sensors": ["sensor.a_moisture"],
        "moisture_threshold": 30.0,
        "moisture_mode": "skip",
        "moisture_unavailable": "water",
    }
    # entry.data is untouched; options override it.
    assert entry.data == FULL_CONFIG

    tz = ZoneInfo("America/New_York")
    start = next_run(
        schedule_from_config(entry.options),
        datetime(2026, 9, 14, 0, 0, tzinfo=tz),
        timedelta(minutes=12),
        tz,
        lambda event, day: None,
    )
    assert start == datetime(2026, 9, 14, 5, 45, tzinfo=tz)


async def test_options_switch_start_mode_drops_other_keys(hass: HomeAssistant) -> None:
    entry = await setup_entry(hass, title="Front lawn", data=FULL_CONFIG)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await options_configure(hass, result, {"name": "Front lawn"})
    result = await options_configure(
        hass, result, {"zones": ["valve.deck_zone", "switch.front_yard"]}
    )
    assert schema_default(result, "zone_mode") == "concurrent"
    result = await options_configure(
        hass,
        result,
        {"valve.deck_zone": 10, "switch.front_yard": 20, "zone_mode": "concurrent"},
    )
    result = await options_menu(hass, result, "weekdays")
    assert schema_default(result, "weekdays") == ["0", "2", "4"]
    result = await options_configure(hass, result, {"weekdays": ["0", "2", "4"]})
    result = await options_menu(hass, result, "start_sunset")
    assert schema_default(result, "sun_offset_minutes") == -15
    result = await options_configure(hass, result, {"sun_offset_minutes": 0})
    result = await options_configure(hass, result, {"skip_conditions": []})
    result = await skip_notifications(hass, result, options_configure)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.title == "Front lawn"
    assert entry.options == {
        "name": "Front lawn",
        "zones": FULL_CONFIG["zones"],
        "zone_mode": "concurrent",
        "frequency": "weekdays",
        "weekdays": [0, 2, 4],
        "start_mode": "sunset",
        "sun_offset_minutes": 0,
        "skip_conditions": [],
    }


async def test_options_rename_to_existing_name_rejected(hass: HomeAssistant) -> None:
    MockConfigEntry(domain=DOMAIN, title="Garden", data={}).add_to_hass(hass)
    entry = await setup_entry(hass, title="Front lawn", data=FULL_CONFIG)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await options_configure(hass, result, {"name": "garden"})
    assert result["step_id"] == "init"
    assert result["errors"] == {"name": "name_exists"}

    # Its own name (any case) is fine.
    result = await options_configure(hass, result, {"name": "FRONT LAWN"})
    assert result["step_id"] == "zones"


async def test_garden_bed_v01_config_round_trips(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.weather_station_rain_in", "69.22")
    hass.states.async_set("weather.krdu_daynight", "cloudy")
    entry = await setup_entry(hass, title="Garden Bed", data=GARDEN_BED)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert schema_default(result, "name") == "Garden Bed"
    result = await options_configure(hass, result, {})
    assert schema_default(result, "zones") == ["valve.garden_irrigation_zone"]
    result = await options_configure(hass, result, {})
    assert schema_default(result, "valve.garden_irrigation_zone") == 30
    result = await options_configure(hass, result, {})
    result = await options_menu(hass, result, "interval")
    assert (schema_default(result, "interval_days"), schema_default(result, "anchor")) == (
        2,
        "2026-09-13",
    )
    result = await options_configure(hass, result, {})
    result = await options_menu(hass, result, "start_time")
    assert schema_default(result, "start_time") == "06:00:00"
    result = await options_configure(hass, result, {})
    assert schema_default(result, "skip_conditions") == ["rain", "forecast"]
    result = await options_configure(hass, result, {})

    assert result["step_id"] == "rain"
    assert {
        name: schema_default(result, name)
        for name in (
            "rain_sensors",
            "rain_threshold",
            "rain_hours",
            "rain_aggregate",
            "rain_window",
            "rain_delay_auto_hours",
            "rain_stop_during_run",
        )
    } == {
        "rain_sensors": ["sensor.weather_station_rain_in"],
        "rain_threshold": 0.1,
        "rain_hours": 24,
        "rain_aggregate": "max",
        "rain_window": "hours",
        "rain_delay_auto_hours": 0,
        "rain_stop_during_run": False,
    }
    result = await options_configure(hass, result, {})

    assert result["step_id"] == "forecast"
    assert {
        name: schema_default(result, name)
        for name in (
            "weather_entities",
            "forecast_mode",
            "forecast_probability",
            "forecast_hours",
            "forecast_quorum",
        )
    } == {
        "weather_entities": ["weather.krdu_daynight"],
        "forecast_mode": "probability",
        "forecast_probability": 75,
        "forecast_hours": 12,
        "forecast_quorum": 1,
    }
    result = await options_configure(hass, result, {})
    result = await skip_notifications(hass, result, options_configure)
    assert result["type"] is FlowResultType.CREATE_ENTRY

    expected = {
        key: value
        for key, value in GARDEN_BED.items()
        if key not in ("rain_sensor", "weather_entity")
    }
    expected.update(
        rain_sensors=["sensor.weather_station_rain_in"],
        rain_aggregate="max",
        rain_window="hours",
        weather_entities=["weather.krdu_daynight"],
        forecast_mode="probability",
    )
    assert entry.options == expected
    # The checks and the scheduler read the same values as from the v0.1 config.
    assert resolve_rain_sensors(entry.options) == resolve_rain_sensors(GARDEN_BED)
    assert resolve_weather_entities(entry.options) == resolve_weather_entities(GARDEN_BED)
    assert schedule_from_config(entry.options) == schedule_from_config(GARDEN_BED)
    assert_config_valid(hass, GARDEN_BED)
    assert_config_valid(hass, entry.options)


async def test_options_deselect_removes_every_condition_key(hass: HomeAssistant) -> None:
    data = {
        **V02_CONFIG,
        "rain_sensor": "sensor.weather_station_rain_in",
        "weather_entity": "weather.krdu_daynight",
    }
    entry = await setup_entry(hass, title="Front lawn", data=data)
    result = await options_walk_defaults(hass, entry, "weekdays", "start_sunrise")
    result = await options_configure(
        hass, result, {"skip_conditions": ["moisture"], "stale_hours": 0}
    )
    assert result["step_id"] == "moisture"
    result = await options_configure(hass, result, {})
    result = await skip_notifications(hass, result, options_configure)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {
        "name": "Front lawn",
        "zones": V02_CONFIG["zones"],
        "zone_mode": "concurrent",
        "frequency": "weekdays",
        "weekdays": [0, 2, 4],
        "start_mode": "sunrise",
        "sun_offset_minutes": -15,
        "skip_conditions": ["moisture"],
        "moisture_sensors": ["sensor.a_moisture", "sensor.b_moisture"],
        "moisture_threshold": 35.0,
        "moisture_mode": "trigger",
        "moisture_unavailable": "skip",
    }


async def test_options_temperature_keeps_weather_entities_when_forecast_dropped(
    hass: HomeAssistant,
) -> None:
    entry = await setup_entry(hass, title="Front lawn", data=V02_CONFIG)
    result = await options_walk_defaults(hass, entry, "weekdays", "start_sunrise")
    result = await options_configure(hass, result, {"skip_conditions": ["temperature"]})
    assert result["step_id"] == "temperature"
    assert schema_suggested(result, "weather_entities") == V02_CONFIG["weather_entities"]
    assert schema_suggested(result, "temperature_min") == 34.0
    result = await options_configure(
        hass,
        result,
        {
            "temperature_sensor": "sensor.weather_station_temperature_f",
            "temperature_min": 34,
            "temperature_forecast_hours": 12,
            "weather_entities": V02_CONFIG["weather_entities"],
        },
    )
    result = await skip_notifications(hass, result, options_configure)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options["weather_entities"] == V02_CONFIG["weather_entities"]
    assert not {"forecast_mode", "forecast_probability", "temperature_max"} & entry.options.keys()


# --- notifications step ------------------------------------------------------------

NOTIFY_SETTINGS: dict[str, Any] = {
    "notify_events": ["run_started", "run_stopped", "run_error"],
    "notify_services": ["notify.iphone"],
    "notify_entities": ["notify.kitchen_display"],
}


async def test_notifications_step_validation_and_save(hass: HomeAssistant) -> None:
    async def _service(call: ServiceCall) -> None:
        return None

    hass.services.async_register("notify", "iphone", _service)
    hass.services.async_register("notify", "send_message", _service)

    result = await start_create(hass)
    result = await configure(hass, result, {"name": "Beds"})
    result = await walk_to_conditions(hass, result, configure, menu)
    result = await configure(hass, result, {"skip_conditions": []})
    assert result["step_id"] == "notifications"
    # send_message needs an entity target, so it's not offered as a service.
    assert schema_selector(result, "notify_services").config["options"] == [
        "persistent_notification.create",
        "notify.iphone",
    ]

    result = await configure(hass, result, {"notify_events": ["run_error"]})
    assert result["errors"] == {"base": "notify_target_required"}

    # Events are stored in NotifyEvent order, whatever order they were picked in.
    result = await configure(
        hass,
        result,
        {**NOTIFY_SETTINGS, "notify_events": ["run_error", "run_started", "run_stopped"]},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert {key: value for key, value in result["data"].items() if key.startswith("notify_")} == NOTIFY_SETTINGS


async def test_options_notifications_prefill_and_clear(hass: HomeAssistant) -> None:
    entry = await setup_entry(hass, title="Beds", data={**BASIC_CONFIG, **NOTIFY_SETTINGS})
    result = await options_walk_defaults(hass, entry, "interval", "start_time")
    result = await options_configure(hass, result, {})
    assert result["step_id"] == "notifications"
    assert schema_default(result, "notify_events") == NOTIFY_SETTINGS["notify_events"]
    assert schema_suggested(result, "notify_entities") == ["notify.kitchen_display"]
    # A stored notify service stays selectable even though it isn't registered.
    assert "notify.iphone" in schema_selector(result, "notify_services").config["options"]

    # No events turns notifications off and drops the targets too.
    result = await options_configure(
        hass, result, {"notify_events": [], "notify_services": ["notify.iphone"]}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == BASIC_CONFIG


# --- strings ------------------------------------------------------------------


def test_translations_match_strings() -> None:
    assert (PACKAGE / "translations" / "en.json").read_text() == (
        PACKAGE / "strings.json"
    ).read_text()


def _own_steps(flow_class: type) -> set[str]:
    return {
        name.removeprefix("async_step_")
        for name in dir(flow_class)
        if name.startswith("async_step_")
        and getattr(getattr(flow_class, name), "__module__", None) == config_flow.__name__
    }


def test_every_step_method_has_strings() -> None:
    # "create" only redirects to the name step and is never shown.
    config_steps = _own_steps(config_flow.IrrigationManagerConfigFlow) - {"create"}
    options_steps = _own_steps(config_flow.IrrigationManagerOptionsFlow)
    assert config_steps - STRINGS["config"]["step"].keys() == set()
    assert options_steps - STRINGS["options"]["step"].keys() == set()


def test_every_error_and_abort_has_strings() -> None:
    source = Path(config_flow.__file__).read_text()
    errors = set(re.findall(r'errors\[[^\]]+\] = "([a-z_]+)"', source))
    errors |= set(re.findall(r'\{CONF_NAME: "([a-z_]+)"\}', source))
    assert {"name_exists", "number_invalid", "temperature_source_required", "disable_failed"} <= errors
    config_only = {"describe_failed", "disable_failed"}
    assert errors - STRINGS["config"]["error"].keys() == set()
    assert errors - config_only - STRINGS["options"]["error"].keys() == set()

    aborts = set(re.findall(r'async_abort\(\s*reason="([a-z_]+)"', source))
    assert aborts == {"no_schedules", "no_legacy_helpers", "no_bhyve_programs"}
    assert aborts - STRINGS["config"]["abort"].keys() == set()


def assert_result_strings(section: str, result: dict[str, Any]) -> None:
    if result["type"] is FlowResultType.ABORT:
        assert result["reason"] in STRINGS[section]["abort"]
        return
    if result["type"] is FlowResultType.CREATE_ENTRY:
        return
    step_id = result["step_id"]
    step = STRINGS[section]["step"][step_id]
    assert step.get("title"), step_id
    description = step.get("description", "")
    for placeholder in re.findall(r"\{(\w+)\}", description):
        assert placeholder in (result.get("description_placeholders") or {}), (step_id, placeholder)
    if result["type"] is FlowResultType.MENU:
        for option in result["menu_options"]:
            assert option in step["menu_options"], (step_id, option)
        return
    for key, selector in result["data_schema"].schema.items():
        name = str(key)
        if "." in name:  # per-zone run time fields are labelled by entity id
            continue
        assert name in step.get("data", {}), (step_id, name)
        if isinstance(selector, SelectSelector) and (
            translation_key := selector.config.get("translation_key")
        ):
            labels = STRINGS["selector"][translation_key]["options"]
            for option in selector.config["options"]:
                value = option["value"] if isinstance(option, dict) else option
                assert value in labels, (translation_key, value)
    for error in (result.get("errors") or {}).values():
        assert error in STRINGS[section]["error"], (step_id, error)


async def test_strings_cover_every_shown_step(hass: HomeAssistant) -> None:
    hass.states.async_set(AI_TASK, "unknown")
    seen: list[tuple[str, dict[str, Any]]] = []

    async def c(result: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
        result = await configure(hass, result, data)
        seen.append(("config", result))
        return result

    async def m(result: dict[str, Any], option: str) -> dict[str, Any]:
        result = await menu(hass, result, option)
        seen.append(("config", result))
        return result

    result = await start_flow(hass)
    seen.append(("config", result))
    result = await m(result, "create")
    result = await c(result, {"name": "Every step"})
    result = await c(result, {"zones": ["valve.deck_zone", "switch.front_yard"]})
    result = await c(result, {"valve.deck_zone": float("nan"), "switch.front_yard": 5})
    result = await c(result, {"valve.deck_zone": 10, "switch.front_yard": 5})
    result = await m(result, "weekdays")
    result = await c(result, {"weekdays": ["1"]})
    result = await m(result, "start_sunset")
    result = await c(result, {"sun_offset_minutes": 0})
    result = await c(
        result, {"skip_conditions": ["rain", "moisture", "temperature", "wind", "occupancy"]}
    )
    result = await c(result, {**CONDITION_INPUT["rain"], "rain_sensors": []})
    result = await c(result, CONDITION_INPUT["rain"])
    result = await c(result, CONDITION_INPUT["moisture"])
    result = await c(result, {"temperature_forecast_hours": 12})
    result = await c(result, CONDITION_INPUT["temperature"])
    result = await c(result, CONDITION_INPUT["wind"])
    result = await c(result, CONDITION_INPUT["occupancy"])
    assert result["step_id"] == "ai"
    result = await c(result, {"ai_task_entity": AI_TASK, "ai_report_weekday": "1"})
    result = await c(result, {})
    assert result["step_id"] == "notifications"
    result = await c(result, {"notify_events": ["run_started"]})
    assert result["errors"] == {"base": "notify_target_required"}
    result = await c(result, {})
    assert result["type"] is FlowResultType.CREATE_ENTRY

    result = await m(await start_flow(hass), "create")
    result = await c(result, {"name": "Second"})
    result = await walk_to_conditions(
        hass, result, lambda _hass, r, d: c(r, d), lambda _hass, r, o: m(r, o)
    )
    result = await c(result, {"skip_conditions": ["forecast"]})
    result = await c(result, CONDITION_INPUT["forecast"])
    assert result["step_id"] == "ai"

    result = await m(await start_flow(hass), "create")
    result = await c(result, {"name": "Third"})
    result = await c(result, {"zones": ["valve.deck_zone"]})
    result = await c(result, {"valve.deck_zone": 10})
    result = await m(result, "interval")
    result = await m(await c(result, {"interval_days": 1, "anchor": "2026-09-13"}), "start_sunrise")
    assert result["step_id"] == "start_sunrise"

    result = await m(await start_flow(hass), "create")
    result = await c(result, {"name": "Fourth"})
    result = await c(result, {"zones": ["valve.deck_zone"]})
    result = await c(result, {"valve.deck_zone": 10})
    result = await m(result, "hourly")
    result = await c(result, {"interval_hours": 3, "window_start": "06:00", "window_end": "05:00"})
    assert result["errors"] == {"window_end": "window_invalid"}
    result = await c(result, {"interval_hours": 3, "window_start": "06:00", "window_end": "18:00"})
    assert result["step_id"] == "conditions"

    with patch(READ_LEGACY, return_value=deepcopy(LEGACY)):
        result = await m(await start_flow(hass), "import_legacy")
        assert result["step_id"] == "import_legacy"
    with patch(READ_BHYVE, return_value=[deepcopy(BHYVE_UNSUPPORTED)]):
        await m(await start_flow(hass), "import_bhyve")
    with patch(PARSE_DESCRIPTION, new=AsyncMock(side_effect=HomeAssistantError("x"))):
        result = await m(await start_flow(hass), "describe")
        await c(result, {"ai_task_entity": AI_TASK, "description": "water"})
    with patch(DISABLE_BHYVE, new=AsyncMock()):
        result = await bhyve_to_final_step(hass, [BHYVE_SUPPORTED])
        seen.append(("config", result))
        with patch(READ_BHYVE, return_value=[deepcopy(BHYVE_SUPPORTED)]):
            seen.append(("config", await menu(hass, await start_flow(hass), "import_bhyve")))

    entry = await setup_entry(hass, title="Front lawn", data=V02_CONFIG)
    result = await m(await start_flow(hass), "copy")
    await c(result, {"schedule": entry.entry_id})
    result = await hass.config_entries.options.async_init(entry.entry_id)
    seen.append(("options", result))
    seen.append(("options", await options_configure(hass, result, {"name": "Garden"})))

    shown = {(section, result.get("step_id")) for section, result in seen}
    assert {
        ("config", step)
        for step in (
            "user", "name", "zones", "zone_minutes", "frequency", "weekdays", "interval",
            "start", "start_time", "start_sunset", "start_sunrise", "conditions", "rain",
            "forecast", "moisture", "temperature", "wind", "occupancy", "ai",
            "notifications", "import_legacy", "import_bhyve", "describe", "bhyve_disable", "hourly",
            "copy",
        )
    } <= shown
    assert ("config", "no_bhyve_programs") not in shown  # aborts carry reason, not step_id
    for section, result in seen:
        assert_result_strings(section, result)


def test_services_exceptions_device_automation_and_states_have_strings() -> None:
    services = yaml.safe_load((PACKAGE / "services.yaml").read_text())
    assert len(services) == 13
    for service, definition in services.items():
        strings = STRINGS["services"][service]
        assert strings["name"] and strings["description"], service
        for field in (definition or {}).get("fields", {}):
            assert strings["fields"][field]["name"], (service, field)
            assert strings["fields"][field]["description"], (service, field)

    keys: set[str] = set()
    for path in PACKAGE.glob("*.py"):
        keys |= set(re.findall(r'translation_key="([a-z_]+)"', path.read_text()))
    assert {"zone_not_in_schedule", "ai_not_configured"} <= keys
    assert keys - STRINGS["exceptions"].keys() == set()
    assert "{zone}" in STRINGS["exceptions"]["zone_not_in_schedule"]["message"]
    assert "{name}" in STRINGS["exceptions"]["zone_not_in_schedule"]["message"]
    assert "{name}" in STRINGS["exceptions"]["ai_not_configured"]["message"]

    assert set(TRIGGER_TYPES) - STRINGS["device_automation"]["trigger_type"].keys() == set()
    assert set(CONDITION_TYPES) - STRINGS["device_automation"]["condition_type"].keys() == set()
    assert {status.value for status in Status} - STRINGS["entity"]["sensor"]["status"][
        "state"
    ].keys() == set()
