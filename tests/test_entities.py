"""Entity tests: states and attributes follow the runner; controls call it.

Conditions are mocked (runner.async_decide) and zones are plain valve/switch
entities with mocked services. Time is driven with freezer +
async_fire_time_changed.
"""
from __future__ import annotations

import asyncio
from collections.abc import Generator
from datetime import datetime
from typing import Any
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    async_mock_service,
)

from custom_components.irrigation_manager.conditions import Decision
from custom_components.irrigation_manager.const import (
    CONF_ANCHOR,
    CONF_FREQUENCY,
    CONF_INTERVAL_DAYS,
    CONF_MOISTURE_MODE,
    CONF_MOISTURE_SENSORS,
    CONF_MOISTURE_THRESHOLD,
    CONF_NAME,
    CONF_SKIP_CONDITIONS,
    CONF_START_MODE,
    CONF_START_TIME,
    CONF_WEEKDAYS,
    CONF_ZONE_ENTITY,
    CONF_ZONE_MINUTES,
    CONF_ZONE_MODE,
    CONF_ZONES,
    DOMAIN,
    Status,
)

TZ = ZoneInfo("America/New_York")
ZONE_A = "valve.zone_a"
ZONE_B = "switch.zone_b"

ENABLED = "switch.front_lawn_enabled"
STATUS = "sensor.front_lawn_status"
NEXT_RUN = "sensor.front_lawn_next_run"
LAST_RUN = "sensor.front_lawn_last_run"
LAST_RUN_TOTAL = "sensor.front_lawn_last_run_total"
CURRENT_ZONE = "sensor.front_lawn_current_zone"
ZONE_A_MINUTES = "number.front_lawn_zone_a_run_time"
ZONE_B_MINUTES = "number.front_lawn_zone_b_run_time"
RUN_NOW = "button.front_lawn_run_now"
SKIP_NEXT = "button.front_lawn_skip_next_run"
STOP = "button.front_lawn_stop"
RAIN_DELAY = "sensor.front_lawn_rain_delay"
PROBLEM = "binary_sensor.front_lawn_problem"
CLEAR_RAIN_DELAY = "button.front_lawn_clear_rain_delay"


def local(y: int, mo: int, d: int, h: int = 0, mi: int = 0) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=TZ)


def make_config(**overrides: Any) -> dict[str, Any]:
    """Daily at 06:00, zone A 10 min then zone B 5 min."""
    config: dict[str, Any] = {
        CONF_NAME: "Front lawn",
        CONF_ZONES: [
            {CONF_ZONE_ENTITY: ZONE_A, CONF_ZONE_MINUTES: 10},
            {CONF_ZONE_ENTITY: ZONE_B, CONF_ZONE_MINUTES: 5},
        ],
        CONF_ZONE_MODE: "sequential",
        CONF_FREQUENCY: "weekdays",
        CONF_WEEKDAYS: list(range(7)),
        CONF_START_MODE: "time",
        CONF_START_TIME: "06:00:00",
        CONF_SKIP_CONDITIONS: [],
    }
    config.update(overrides)
    return config


async def settle(hass: HomeAssistant) -> None:
    """Let background run tasks and blocking service calls progress."""
    for _ in range(20):
        await hass.async_block_till_done()
        await asyncio.sleep(0)


async def advance_to(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, when: datetime
) -> None:
    freezer.move_to(when)
    async_fire_time_changed(hass)
    await settle(hass)


async def setup_entry(
    hass: HomeAssistant, config: dict[str, Any] | None = None
) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, title="Front lawn", data=config or make_config())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await settle(hass)
    return entry


async def press(hass: HomeAssistant, entity_id: str) -> None:
    await hass.services.async_call(
        "button", "press", {"entity_id": entity_id}, blocking=True
    )
    await settle(hass)


def timestamp(hass: HomeAssistant, entity_id: str) -> datetime | None:
    return dt_util.parse_datetime(hass.states.get(entity_id).state)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let the test hass load integrations from custom_components/."""
    return


@pytest.fixture(autouse=True)
async def setup_env(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, skip_manifest_dependencies
) -> None:
    """Monday 2026-09-14 05:00 New York, zones present."""
    await hass.config.async_set_time_zone("America/New_York")
    freezer.move_to(local(2026, 9, 14, 5, 0))
    # Set up the switch component first: when this integration's switch
    # platform loads it later, it would replace the zone service mocks.
    assert await async_setup_component(hass, "switch", {})
    hass.states.async_set(ZONE_A, "closed", {"friendly_name": "Zone A"})
    hass.states.async_set(ZONE_B, "off", {"friendly_name": "Zone B"})


@pytest.fixture(autouse=True)
def decide() -> Generator[AsyncMock]:
    mock = AsyncMock(return_value=Decision(water=True))
    with patch("custom_components.irrigation_manager.runner.async_decide", mock):
        yield mock


@pytest.fixture(autouse=True)
def shared() -> Generator[None]:
    with (
        patch(
            "custom_components.irrigation_manager.panel.async_register_panel",
            new_callable=AsyncMock,
        ),
        patch("custom_components.irrigation_manager.panel.async_unregister_panel"),
        patch("custom_components.irrigation_manager.websocket_api.async_setup"),
    ):
        yield


@pytest.fixture
def calls(hass: HomeAssistant, setup_env: None) -> dict[str, list[ServiceCall]]:
    return {
        "open": async_mock_service(hass, "valve", "open_valve"),
        "close": async_mock_service(hass, "valve", "close_valve"),
        "on": async_mock_service(hass, "switch", "turn_on"),
        "off": async_mock_service(hass, "switch", "turn_off"),
    }


async def test_initial_states(hass: HomeAssistant) -> None:
    await setup_entry(hass)

    assert hass.states.get(ENABLED).state == "on"

    status = hass.states.get(STATUS)
    assert status.state == Status.IDLE.value
    assert status.attributes["options"] == [s.value for s in Status]
    assert status.attributes["skip_next"] is False
    assert status.attributes["details"] == {}

    assert timestamp(hass, NEXT_RUN) == local(2026, 9, 14, 6, 0)
    assert hass.states.get(NEXT_RUN).attributes["scheduled"] is True

    for entity_id in (LAST_RUN, LAST_RUN_TOTAL, CURRENT_ZONE):
        assert hass.states.get(entity_id).state == "unknown", entity_id

    zone_a = hass.states.get(ZONE_A_MINUTES)
    assert float(zone_a.state) == 10
    assert zone_a.attributes["zone_entity_id"] == ZONE_A
    assert zone_a.attributes["friendly_name"] == "Front lawn Zone A run time"
    assert zone_a.attributes["unit_of_measurement"] == "min"
    assert float(hass.states.get(ZONE_B_MINUTES).state) == 5


async def test_next_run_marks_moisture_check_days(hass: HomeAssistant) -> None:
    # Every 3 days from Sunday, plus daily moisture checks: Monday is a check day.
    await setup_entry(
        hass,
        make_config(
            **{
                CONF_FREQUENCY: "interval",
                CONF_INTERVAL_DAYS: 3,
                CONF_ANCHOR: "2026-09-13",
                CONF_SKIP_CONDITIONS: ["moisture"],
                CONF_MOISTURE_SENSORS: ["sensor.bed_moisture"],
                CONF_MOISTURE_THRESHOLD: 30.0,
                CONF_MOISTURE_MODE: "trigger",
            }
        ),
    )

    assert timestamp(hass, NEXT_RUN) == local(2026, 9, 14, 6, 0)
    assert hass.states.get(NEXT_RUN).attributes["scheduled"] is False


async def test_enabled_switch_toggles_scheduling(hass: HomeAssistant) -> None:
    entry = await setup_entry(hass)

    await hass.services.async_call("switch", "turn_off", {"entity_id": ENABLED}, blocking=True)
    await settle(hass)
    assert entry.runtime_data.enabled is False
    assert hass.states.get(ENABLED).state == "off"
    assert hass.states.get(STATUS).state == Status.DISABLED.value
    assert hass.states.get(NEXT_RUN).state == "unknown"

    await hass.services.async_call("switch", "turn_on", {"entity_id": ENABLED}, blocking=True)
    await settle(hass)
    assert entry.runtime_data.enabled is True
    assert hass.states.get(STATUS).state == Status.IDLE.value
    assert timestamp(hass, NEXT_RUN) == local(2026, 9, 14, 6, 0)


async def test_zone_number_writes_options_without_reload(hass: HomeAssistant) -> None:
    entry = await setup_entry(hass)
    runner = entry.runtime_data

    await hass.services.async_call(
        "number", "set_value", {"entity_id": ZONE_A_MINUTES, "value": 25}, blocking=True
    )
    await settle(hass)

    assert entry.runtime_data is runner
    assert entry.options[CONF_ZONES] == [
        {CONF_ZONE_ENTITY: ZONE_A, CONF_ZONE_MINUTES: 25},
        {CONF_ZONE_ENTITY: ZONE_B, CONF_ZONE_MINUTES: 5},
    ]
    assert runner.config[CONF_ZONES][0][CONF_ZONE_MINUTES] == 25
    assert float(hass.states.get(ZONE_A_MINUTES).state) == 25


async def test_run_now_button_drives_run_sensors(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    calls: dict[str, list[ServiceCall]],
) -> None:
    await setup_entry(hass)

    await press(hass, RUN_NOW)
    assert hass.states.get(STATUS).state == Status.RUNNING.value
    current = hass.states.get(CURRENT_ZONE)
    assert current.state == "Zone A"
    assert current.attributes["entity_id"] == ZONE_A
    assert dt_util.parse_datetime(current.attributes["ends_at"]) == local(2026, 9, 14, 5, 10)
    assert [zone["entity_id"] for zone in current.attributes["active_zones"]] == [ZONE_A]

    await advance_to(hass, freezer, local(2026, 9, 14, 5, 10))
    assert hass.states.get(CURRENT_ZONE).state == "Zone B"
    assert [call.data["entity_id"] for call in calls["close"]] == [ZONE_A]
    assert [call.data["entity_id"] for call in calls["on"]] == [ZONE_B]

    await advance_to(hass, freezer, local(2026, 9, 14, 5, 15))
    assert hass.states.get(STATUS).state == Status.IDLE.value
    assert hass.states.get(CURRENT_ZONE).state == "unknown"
    assert float(hass.states.get(LAST_RUN_TOTAL).state) == 15.0
    assert timestamp(hass, LAST_RUN) == local(2026, 9, 14, 5, 0)
    last_run = hass.states.get(LAST_RUN)
    assert dt_util.parse_datetime(last_run.attributes["last_run_end"]) == local(2026, 9, 14, 5, 15)
    assert last_run.attributes["zone_results"] == [
        {"entity_id": ZONE_A, "minutes": 10.0, "error": None, "stopped_by": "manager"},
        {"entity_id": ZONE_B, "minutes": 5.0, "error": None, "stopped_by": "manager"},
    ]


async def test_skip_next_and_stop_buttons(
    hass: HomeAssistant, calls: dict[str, list[ServiceCall]]
) -> None:
    entry = await setup_entry(hass)

    await press(hass, SKIP_NEXT)
    assert entry.runtime_data.skip_next is True
    assert hass.states.get(STATUS).attributes["skip_next"] is True

    await press(hass, RUN_NOW)
    assert entry.runtime_data.running
    await press(hass, STOP)

    assert not entry.runtime_data.running
    assert hass.states.get(STATUS).state == Status.IDLE.value
    assert [call.data["entity_id"] for call in calls["close"]] == [ZONE_A]
    assert not calls["on"]


async def test_run_now_button_while_running_raises_translated_error(
    hass: HomeAssistant, calls: dict[str, list[ServiceCall]]
) -> None:
    await setup_entry(hass)
    await press(hass, RUN_NOW)

    with pytest.raises(HomeAssistantError) as err:
        await press(hass, RUN_NOW)
    assert err.value.translation_domain == DOMAIN
    assert err.value.translation_key == "already_running"
    assert err.value.translation_placeholders == {"name": "Front lawn"}


async def test_status_sensor_reports_condition_skip(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, decide: AsyncMock
) -> None:
    details = {"rain": {"total": 0.4, "threshold": 0.1}}
    decide.return_value = Decision(water=False, status=Status.SKIPPED_RAIN, details=details)
    await setup_entry(hass)

    await advance_to(hass, freezer, local(2026, 9, 14, 6, 0))

    status = hass.states.get(STATUS)
    assert status.state == Status.SKIPPED_RAIN.value
    assert status.attributes["details"] == details
    assert dt_util.parse_datetime(status.attributes["last_status_at"]) == local(2026, 9, 14, 6, 0)
    assert timestamp(hass, NEXT_RUN) == local(2026, 9, 15, 6, 0)


# --- v0.2 entities ----------------------------------------------------------------


async def test_v02_entities_initial_states(hass: HomeAssistant) -> None:
    await setup_entry(hass)

    rain_delay = hass.states.get(RAIN_DELAY)
    assert rain_delay.state == "unknown"
    assert rain_delay.attributes["device_class"] == "timestamp"
    assert rain_delay.attributes["friendly_name"] == "Front lawn Rain delay"

    problem = hass.states.get(PROBLEM)
    assert problem.state == "off"
    assert problem.attributes["device_class"] == "problem"
    assert problem.attributes["unclosed_zones"] == []
    assert problem.attributes["zone_errors"] == []

    clear = hass.states.get(CLEAR_RAIN_DELAY)
    assert clear is not None
    assert clear.state != "unavailable"
    assert clear.attributes["friendly_name"] == "Front lawn Clear rain delay"

    status = hass.states.get(STATUS)
    assert status.attributes["paused"] is False
    assert status.attributes["rain_delay_until"] is None
    assert status.attributes["unclosed_zones"] == []


async def test_rain_delay_sensor_and_clear_button(hass: HomeAssistant) -> None:
    entry = await setup_entry(hass)
    runner = entry.runtime_data

    await runner.async_set_rain_delay(24)
    await settle(hass)

    assert timestamp(hass, RAIN_DELAY) == local(2026, 9, 15, 5, 0)
    assert dt_util.parse_datetime(
        hass.states.get(STATUS).attributes["rain_delay_until"]
    ) == local(2026, 9, 15, 5, 0)

    await press(hass, CLEAR_RAIN_DELAY)

    assert runner.rain_delay_until is None
    assert hass.states.get(RAIN_DELAY).state == "unknown"
    assert hass.states.get(STATUS).attributes["rain_delay_until"] is None


async def test_status_sensor_reports_paused(hass: HomeAssistant) -> None:
    entry = await setup_entry(hass)

    await entry.runtime_data.async_set_paused(True)
    await settle(hass)

    status = hass.states.get(STATUS)
    assert status.state == Status.PAUSED.value
    assert status.attributes["paused"] is True


async def test_problem_sensor_on_while_a_zone_could_not_be_closed(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    calls: dict[str, list[ServiceCall]],
) -> None:
    await setup_entry(hass)
    await press(hass, RUN_NOW)
    assert hass.states.get(PROBLEM).state == "off"

    # Zone A's close fails when its time is up; zone B then runs.
    hass.services.async_remove("valve", "close_valve")
    await advance_to(hass, freezer, local(2026, 9, 14, 5, 10))

    # Still running zone B: the problem comes from the unclosed zone, not the status.
    assert hass.states.get(STATUS).state == Status.RUNNING.value
    problem = hass.states.get(PROBLEM)
    assert problem.state == "on"
    assert problem.attributes["unclosed_zones"] == [ZONE_A]
    assert hass.states.get(STATUS).attributes["unclosed_zones"] == [ZONE_A]


async def test_problem_sensor_on_after_a_run_error(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    calls: dict[str, list[ServiceCall]],
) -> None:
    await setup_entry(hass)
    # Zone A can't start; zone B runs its 5 minutes.
    hass.states.async_set(ZONE_A, "unavailable")

    await press(hass, RUN_NOW)
    await advance_to(hass, freezer, local(2026, 9, 14, 5, 5))

    assert hass.states.get(STATUS).state == Status.ERROR.value
    problem = hass.states.get(PROBLEM)
    assert problem.state == "on"
    assert ZONE_A in [error["entity_id"] for error in problem.attributes["zone_errors"]]
