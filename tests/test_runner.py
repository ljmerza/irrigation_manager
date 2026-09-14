"""ScheduleRunner tests: timing, condition handling, zone sequencing, state.

Conditions are mocked (runner.async_decide); zones are plain valve/switch
entities with mocked services. Time is driven with freezer +
async_fire_time_changed, never real sleeps.
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable
from datetime import date, datetime, time, timedelta
import itertools
from typing import Any
from unittest.mock import AsyncMock, patch
from zoneinfo import ZoneInfo

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.const import EVENT_CORE_CONFIG_UPDATE, EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState, HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er, event as event_helper
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
    async_fire_time_changed,
    async_mock_service,
)

from custom_components.irrigation_manager.conditions import Decision
from custom_components.irrigation_manager.const import (
    CONF_ANCHOR,
    CONF_FREQUENCY,
    CONF_INTERVAL_DAYS,
    CONF_INTERVAL_HOURS,
    CONF_MOISTURE_MODE,
    CONF_NAME,
    CONF_OCCUPANCY_ENTITIES,
    CONF_OCCUPANCY_MAX_DELAY,
    CONF_OCCUPANCY_STOP_DURING_RUN,
    CONF_RAIN_DELAY_AUTO_HOURS,
    CONF_RAIN_DELAY_MIRROR,
    CONF_RAIN_SENSOR,
    CONF_RAIN_SENSORS,
    CONF_RAIN_STOP_AMOUNT,
    CONF_RAIN_STOP_DURING_RUN,
    EVENT_IRRIGATION,
    MAX_RAIN_DELAY_HOURS,
    CONF_SKIP_CONDITIONS,
    CONF_START_MODE,
    CONF_START_TIME,
    CONF_SUN_OFFSET,
    CONF_WEEKDAYS,
    CONF_WINDOW_END,
    CONF_WINDOW_START,
    CONF_ZONE_ENTITY,
    CONF_ZONE_MINUTES,
    CONF_ZONE_MODE,
    CONF_ZONES,
    DOMAIN,
    MAX_ZONE_MINUTES,
    SIGNAL_SCHEDULES_CHANGED,
    STORAGE_KEY_FMT,
    STORAGE_VERSION,
    Status,
    merged_config,
)
from custom_components.irrigation_manager.runner import (
    ScheduleRunner,
    schedule_from_config,
    zone_durations,
)

TZ = ZoneInfo("America/New_York")
ZONE_A = "valve.zone_a"
ZONE_B = "switch.zone_b"


def local(y: int, mo: int, d: int, h: int = 0, mi: int = 0, sec: int = 0) -> datetime:
    return datetime(y, mo, d, h, mi, sec, tzinfo=TZ)


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
    for _ in range(40):
        await hass.async_block_till_done()
        await asyncio.sleep(0)


async def advance_to(hass: HomeAssistant, freezer: FrozenDateTimeFactory, when: datetime) -> None:
    freezer.move_to(when)
    async_fire_time_changed(hass)
    await settle(hass)


def storage_key(entry: MockConfigEntry) -> str:
    return STORAGE_KEY_FMT.format(entry_id=entry.entry_id)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let the test hass load integrations from custom_components/."""
    return


@pytest.fixture(autouse=True)
async def setup_env(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    """Monday 2026-09-14 05:00 New York, both zones present."""
    await hass.config.async_set_time_zone("America/New_York")
    freezer.move_to(local(2026, 9, 14, 5, 0))
    hass.states.async_set(ZONE_A, "closed")
    hass.states.async_set(ZONE_B, "off")


@pytest.fixture
def calls(hass: HomeAssistant) -> dict[str, list[ServiceCall]]:
    return {
        "open": async_mock_service(hass, "valve", "open_valve"),
        "close": async_mock_service(hass, "valve", "close_valve"),
        "on": async_mock_service(hass, "switch", "turn_on"),
        "off": async_mock_service(hass, "switch", "turn_off"),
    }


@pytest.fixture
def decide() -> AsyncMock:
    mock = AsyncMock(return_value=Decision(water=True))
    with patch("custom_components.irrigation_manager.runner.async_decide", mock):
        yield mock


@pytest.fixture
async def make_runner(
    hass: HomeAssistant,
) -> AsyncGenerator[Callable[..., Awaitable[ScheduleRunner]]]:
    created: list[ScheduleRunner] = []

    async def _make(
        config: dict[str, Any] | None = None, *, entry: MockConfigEntry | None = None
    ) -> ScheduleRunner:
        if entry is None:
            entry = MockConfigEntry(domain=DOMAIN, title="Front lawn", data=config or make_config())
            entry.add_to_hass(hass)
        runner = ScheduleRunner(hass, entry)
        await runner.async_setup()
        await settle(hass)
        created.append(runner)
        return runner

    yield _make
    for runner in created:
        await runner.async_unload()


# --- config helpers -----------------------------------------------------------


async def test_schedule_from_config_converts_stored_values() -> None:
    config = make_config(
        **{
            CONF_FREQUENCY: "interval",
            CONF_INTERVAL_DAYS: 2,
            CONF_ANCHOR: "2026-09-13",
            CONF_START_MODE: "sunrise",
            CONF_SUN_OFFSET: 15,
            CONF_SKIP_CONDITIONS: ["moisture"],
            CONF_MOISTURE_MODE: "trigger",
        }
    )
    schedule = schedule_from_config(config)
    assert schedule.frequency == "interval"
    assert schedule.interval_days == 2
    assert schedule.anchor == date(2026, 9, 13)
    assert schedule.start_mode == "sunrise"
    assert schedule.start_time == time(6)
    assert schedule.sun_offset == timedelta(minutes=15)
    assert schedule.check_every_day

    skip_mode = make_config(**{CONF_SKIP_CONDITIONS: ["moisture"], CONF_MOISTURE_MODE: "skip"})
    assert not schedule_from_config(skip_mode).check_every_day
    assert schedule_from_config(make_config()).weekdays == frozenset(range(7))


async def test_zone_durations() -> None:
    assert zone_durations(make_config()) == [
        (ZONE_A, timedelta(minutes=10)),
        (ZONE_B, timedelta(minutes=5)),
    ]


# --- hourly -----------------------------------------------------------------------


def hourly_config(**overrides: Any) -> dict[str, Any]:
    """Every hour from 06:00 to 08:00, zone A 10 min then zone B 5 min."""
    config = make_config(
        **{
            CONF_FREQUENCY: "hourly",
            CONF_INTERVAL_HOURS: 1,
            CONF_WINDOW_START: "06:00:00",
            CONF_WINDOW_END: "08:00:00",
        },
        **overrides,
    )
    config.pop(CONF_WEEKDAYS)
    return config


async def test_schedule_from_config_builds_hourly() -> None:
    schedule = schedule_from_config(hourly_config())
    assert schedule.frequency == "hourly"
    assert schedule.interval_hours == 1
    assert (schedule.window_start, schedule.window_end) == (time(6), time(8))
    assert schedule.start_time == time(6)


async def test_hourly_schedule_runs_at_every_slot(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls, decide, make_runner
) -> None:
    runner = await make_runner(hourly_config())
    assert runner.snapshot()["next_run"] == local(2026, 9, 14, 6).isoformat()

    for hour in (6, 7, 8):
        await advance_to(hass, freezer, local(2026, 9, 14, hour))
        assert runner.running
        await advance_to(hass, freezer, local(2026, 9, 14, hour, 10))
        await advance_to(hass, freezer, local(2026, 9, 14, hour, 15))
        assert not runner.running

    assert decide.await_count == 3
    assert len(calls["open"]) == 3
    assert len(calls["on"]) == 3
    assert runner.snapshot()["next_run"] == local(2026, 9, 15, 6).isoformat()


async def test_hourly_run_overlapping_next_slot_is_skipped_busy(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls, decide, make_runner
) -> None:
    runner = await make_runner(
        hourly_config(**{CONF_ZONES: [{CONF_ZONE_ENTITY: ZONE_A, CONF_ZONE_MINUTES: 70}]})
    )

    await advance_to(hass, freezer, local(2026, 9, 14, 6))
    assert runner.running
    await advance_to(hass, freezer, local(2026, 9, 14, 7))
    assert runner.running
    assert decide.await_count == 1  # the 07:00 start found the 06:00 run still going

    await advance_to(hass, freezer, local(2026, 9, 14, 7, 10))
    assert not runner.running
    assert runner.status is Status.SKIPPED_BUSY
    assert runner.last_details["skipped_busy_at"] == local(2026, 9, 14, 7).isoformat()
    assert runner.snapshot()["next_run"] == local(2026, 9, 14, 8).isoformat()

    await advance_to(hass, freezer, local(2026, 9, 14, 8))
    assert runner.running
    assert decide.await_count == 2


# --- runs -----------------------------------------------------------------------


async def test_sequential_run_waters_each_zone_in_turn(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls, decide, make_runner
) -> None:
    runner = await make_runner()
    assert runner.snapshot()["next_run"] == local(2026, 9, 14, 6).isoformat()
    assert runner.snapshot()["next_run_scheduled"] is True

    await advance_to(hass, freezer, local(2026, 9, 14, 6))
    decide.assert_awaited_once()
    assert decide.await_args.kwargs["scheduled"] is True
    assert runner.running
    assert runner.status is Status.RUNNING
    assert [call.data["entity_id"] for call in calls["open"]] == [ZONE_A]
    assert runner.current_zone == ZONE_A
    assert not calls["on"]

    await advance_to(hass, freezer, local(2026, 9, 14, 6, 10))
    assert len(calls["close"]) == 1
    assert [call.data["entity_id"] for call in calls["on"]] == [ZONE_B]
    assert runner.current_zone == ZONE_B

    await advance_to(hass, freezer, local(2026, 9, 14, 6, 15))
    assert len(calls["off"]) == 1
    assert not runner.running
    assert runner.status is Status.IDLE
    assert runner.last_run_start == local(2026, 9, 14, 6)
    assert runner.last_run_end == local(2026, 9, 14, 6, 15)
    assert runner.last_run_total_minutes == 15.0
    assert runner.zone_results == [
        {"entity_id": ZONE_A, "minutes": 10.0, "error": None, "stopped_by": "manager"},
        {"entity_id": ZONE_B, "minutes": 5.0, "error": None, "stopped_by": "manager"},
    ]
    assert runner.snapshot()["next_run"] == local(2026, 9, 15, 6).isoformat()


async def test_concurrent_run_starts_all_zones_and_stops_each_on_time(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls, decide, make_runner
) -> None:
    runner = await make_runner(make_config(**{CONF_ZONE_MODE: "concurrent"}))

    await advance_to(hass, freezer, local(2026, 9, 14, 6))
    assert len(calls["open"]) == 1
    assert len(calls["on"]) == 1

    await advance_to(hass, freezer, local(2026, 9, 14, 6, 5))
    assert len(calls["off"]) == 1
    assert not calls["close"]
    assert runner.running
    assert runner.current_zone == ZONE_A

    await advance_to(hass, freezer, local(2026, 9, 14, 6, 10))
    assert len(calls["close"]) == 1
    assert not runner.running
    assert runner.status is Status.IDLE
    assert runner.last_run_total_minutes == 15.0


async def test_active_run_is_persisted_while_watering(
    hass: HomeAssistant, hass_storage: dict[str, Any], calls, decide, make_runner
) -> None:
    runner = await make_runner()
    await runner.async_run_now()
    await settle(hass)

    active = hass_storage[storage_key(runner.entry)]["data"]["active_run"]
    assert active == {
        "started": local(2026, 9, 14, 5).isoformat(),
        "zones": [
            {"entity_id": ZONE_A, "ends_at": (dt_util.utcnow() + timedelta(minutes=10)).isoformat()}
        ],
    }
    snapshot = runner.snapshot()
    assert snapshot["running"] is True
    assert snapshot["current_zone"] == ZONE_A
    assert snapshot["active_zones"] == [
        {"entity_id": ZONE_A, "ends_at": (dt_util.utcnow() + timedelta(minutes=10)).isoformat()}
    ]


# --- conditions ---------------------------------------------------------------


@pytest.mark.parametrize(
    "status", [Status.SKIPPED_RAIN, Status.SKIPPED_FORECAST, Status.SKIPPED_MOISTURE]
)
async def test_condition_skip_records_status_and_waters_nothing(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls, decide, make_runner, status: Status
) -> None:
    details = {"rain": {"total": 0.5, "threshold": 0.1}}
    decide.return_value = Decision(water=False, status=status, details=details)
    runner = await make_runner()

    await advance_to(hass, freezer, local(2026, 9, 14, 6))
    assert runner.status is status
    assert runner.last_details == details
    assert runner.last_status_at == local(2026, 9, 14, 6)
    assert not any(calls.values())
    assert runner.snapshot()["next_run"] == local(2026, 9, 15, 6).isoformat()


async def test_quiet_noop_keeps_status_but_stores_details(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls, decide, make_runner
) -> None:
    decide.return_value = Decision(water=False, status=None, details={"moisture": {"lowest": 55}})
    runner = await make_runner()

    await advance_to(hass, freezer, local(2026, 9, 14, 6))
    assert runner.status is Status.IDLE
    assert runner.last_status_at is None
    assert runner.last_details == {"moisture": {"lowest": 55}}
    assert not any(calls.values())


async def test_moisture_trigger_checks_off_schedule_days(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls, decide, make_runner
) -> None:
    config = make_config(
        **{
            CONF_FREQUENCY: "interval",
            CONF_INTERVAL_DAYS: 3,
            CONF_ANCHOR: "2026-09-13",
            CONF_SKIP_CONDITIONS: ["moisture"],
            CONF_MOISTURE_MODE: "trigger",
        }
    )
    config.pop(CONF_WEEKDAYS)
    decide.return_value = Decision(water=False)
    runner = await make_runner(config)
    assert runner.snapshot()["next_run_scheduled"] is False

    await advance_to(hass, freezer, local(2026, 9, 14, 6))
    assert decide.await_args.kwargs["scheduled"] is False
    await advance_to(hass, freezer, local(2026, 9, 15, 6))
    assert decide.await_args.kwargs["scheduled"] is False
    await advance_to(hass, freezer, local(2026, 9, 16, 6))
    assert decide.await_args.kwargs["scheduled"] is True
    assert decide.await_count == 3

    # A dry off-schedule day waters.
    decide.return_value = Decision(water=True, details={"moisture": {"lowest": 20}})
    await advance_to(hass, freezer, local(2026, 9, 17, 6))
    assert decide.await_args.kwargs["scheduled"] is False
    assert len(calls["open"]) == 1


async def test_condition_check_error_still_waters_schedule_day(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls, decide, make_runner
) -> None:
    decide.side_effect = RuntimeError("bad sensor code")
    runner = await make_runner()

    await advance_to(hass, freezer, local(2026, 9, 14, 6))
    assert len(calls["open"]) == 1
    assert runner.last_details == {"error": "condition check failed"}


async def test_skip_next_is_consumed_only_by_an_occurrence_that_would_water(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls, decide, make_runner
) -> None:
    runner = await make_runner()
    await runner.async_set_skip_next(True)

    decide.return_value = Decision(water=False, status=Status.SKIPPED_RAIN)
    await advance_to(hass, freezer, local(2026, 9, 14, 6))
    assert runner.skip_next is True
    assert runner.status is Status.SKIPPED_RAIN

    decide.return_value = Decision(water=True)
    await advance_to(hass, freezer, local(2026, 9, 15, 6))
    assert runner.skip_next is False
    assert runner.status is Status.SKIPPED_MANUAL
    assert not any(calls.values())

    await advance_to(hass, freezer, local(2026, 9, 16, 6))
    assert len(calls["open"]) == 1


async def test_occurrence_during_run_is_skipped_busy(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls, decide, make_runner
) -> None:
    runner = await make_runner()
    await runner.async_run_now(minutes=90)  # 05:00-06:30 zone A, 06:30-08:00 zone B
    await settle(hass)

    await advance_to(hass, freezer, local(2026, 9, 14, 6))
    decide.assert_not_awaited()
    assert runner.status is Status.RUNNING

    await advance_to(hass, freezer, local(2026, 9, 14, 6, 30))
    await advance_to(hass, freezer, local(2026, 9, 14, 8))
    assert not runner.running
    assert runner.status is Status.SKIPPED_BUSY
    assert runner.last_details["skipped_busy_at"] == local(2026, 9, 14, 6).isoformat()
    assert runner.snapshot()["next_run"] == local(2026, 9, 15, 6).isoformat()


async def test_disabled_schedule_does_nothing_until_enabled(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls, decide, make_runner
) -> None:
    runner = await make_runner()
    await runner.async_set_enabled(False)
    assert runner.status is Status.DISABLED
    assert runner.snapshot()["next_run"] is None

    await advance_to(hass, freezer, local(2026, 9, 14, 6))
    decide.assert_not_awaited()
    assert not any(calls.values())

    await runner.async_set_enabled(True)
    assert runner.status is Status.IDLE
    assert runner.snapshot()["next_run"] == local(2026, 9, 15, 6).isoformat()


# --- manual control -------------------------------------------------------------


async def test_run_now_ignores_skip_next_and_clamps_override(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls, decide, make_runner
) -> None:
    runner = await make_runner()
    await runner.async_set_skip_next(True)

    await runner.async_run_now(minutes=500)
    await settle(hass)
    decide.assert_not_awaited()
    assert runner.skip_next is True
    assert runner.current_zone == ZONE_A
    assert runner.current_zone_ends_at == dt_util.utcnow() + timedelta(minutes=MAX_ZONE_MINUTES)
    assert runner.last_details == {"manual": True}

    with pytest.raises(HomeAssistantError, match="already running"):
        await runner.async_run_now()


async def test_stop_mid_run_closes_zone_and_skips_the_rest(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls, decide, make_runner
) -> None:
    runner = await make_runner()
    await runner.async_run_now()
    await settle(hass)

    await advance_to(hass, freezer, local(2026, 9, 14, 5, 3))
    await runner.async_stop_run()
    await settle(hass)

    assert len(calls["close"]) == 1
    assert not calls["on"]
    assert not runner.running
    assert runner.status is Status.IDLE
    assert runner.last_run_total_minutes == 3.0
    assert runner.zone_results == [
        {"entity_id": ZONE_A, "minutes": 3.0, "error": None, "stopped_by": "manager"}
    ]
    assert runner.snapshot()["next_run"] == local(2026, 9, 14, 6).isoformat()


async def test_zone_start_failure_moves_on_and_ends_in_error(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, decide, make_runner
) -> None:
    opened = async_mock_service(hass, "valve", "open_valve", raise_exception=HomeAssistantError("boom"))
    closed = flaky_service(hass, "valve", "close_valve", 0, sets="closed")
    on = async_mock_service(hass, "switch", "turn_on")
    off = async_mock_service(hass, "switch", "turn_off")
    hass.states.async_set(ZONE_A, "open")  # the failed start reached the device

    runner = await make_runner()
    await runner.async_run_now()
    await settle(hass)

    assert len(opened) == 1
    assert len(closed) == 1  # best-effort close after the failed open
    assert [call.data["entity_id"] for call in on] == [ZONE_B]  # no wait

    await advance_to(hass, freezer, local(2026, 9, 14, 5, 5))
    assert len(off) == 1
    assert runner.status is Status.ERROR
    first = runner.zone_results[0]
    assert first["entity_id"] == ZONE_A
    assert first["minutes"] == 0.0
    assert "boom" in first["error"]
    assert runner.last_run_total_minutes == 5.0


async def test_zone_stop_failure_ends_in_error(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, decide, make_runner
) -> None:
    async_mock_service(hass, "valve", "open_valve")
    async_mock_service(hass, "valve", "close_valve", raise_exception=HomeAssistantError("stuck"))
    async_mock_service(hass, "switch", "turn_on")
    async_mock_service(hass, "switch", "turn_off")

    runner = await make_runner()
    await runner.async_run_now()
    await settle(hass)
    await advance_to(hass, freezer, local(2026, 9, 14, 5, 10))
    await advance_to(hass, freezer, local(2026, 9, 14, 5, 15))

    assert runner.status is Status.ERROR
    assert "stuck" in runner.zone_results[0]["error"]
    assert runner.zone_results[1]["error"] is None


async def test_set_zone_minutes_writes_entry_options(
    hass: HomeAssistant, calls, decide, make_runner
) -> None:
    runner = await make_runner()

    await runner.async_set_zone_minutes(ZONE_B, 12)
    await settle(hass)
    assert merged_config(runner.entry)[CONF_ZONES][1] == {CONF_ZONE_ENTITY: ZONE_B, CONF_ZONE_MINUTES: 12}
    assert runner.config == merged_config(runner.entry)

    await runner.async_set_zone_minutes(ZONE_A, 999)
    assert merged_config(runner.entry)[CONF_ZONES][0][CONF_ZONE_MINUTES] == MAX_ZONE_MINUTES

    with pytest.raises(HomeAssistantError, match="not a zone"):
        await runner.async_set_zone_minutes("switch.other", 5)


async def test_update_config_reschedules(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls, decide, make_runner
) -> None:
    runner = await make_runner()
    await runner.async_update_config(make_config(**{CONF_START_TIME: "07:30:00"}))
    assert runner.snapshot()["next_run"] == local(2026, 9, 14, 7, 30).isoformat()

    await advance_to(hass, freezer, local(2026, 9, 14, 6))
    decide.assert_not_awaited()
    await advance_to(hass, freezer, local(2026, 9, 14, 7, 30))
    decide.assert_awaited_once()


async def test_core_config_update_reschedules(
    hass: HomeAssistant, calls, decide, make_runner
) -> None:
    runner = await make_runner()
    await hass.config.async_set_time_zone("America/Los_Angeles")
    hass.bus.async_fire(EVENT_CORE_CONFIG_UPDATE)
    await settle(hass)
    # 05:00 New York is 02:00 Los Angeles; 06:00 is now Pacific time.
    assert runner.next_occurrence is not None
    assert runner.next_occurrence.start == datetime(2026, 9, 14, 6, tzinfo=ZoneInfo("America/Los_Angeles"))


async def test_listeners_and_dispatcher_signal_fire_on_changes(
    hass: HomeAssistant, calls, decide, make_runner
) -> None:
    runner = await make_runner()
    listener_calls: list[int] = []
    signal_calls: list[int] = []

    @callback
    def _on_signal() -> None:
        signal_calls.append(1)

    unsub_listener = runner.async_add_listener(lambda: listener_calls.append(1))
    unsub_signal = async_dispatcher_connect(hass, SIGNAL_SCHEDULES_CHANGED, _on_signal)

    await runner.async_set_skip_next(True)
    await settle(hass)
    assert listener_calls
    assert signal_calls

    unsub_listener()
    count = len(listener_calls)
    await runner.async_set_skip_next(False)
    assert len(listener_calls) == count
    unsub_signal()


# --- restart, unload, persistence ---------------------------------------------


def seed_active_run(hass_storage: dict[str, Any], entry: MockConfigEntry, zones: list[str]) -> None:
    hass_storage[storage_key(entry)] = {
        "version": STORAGE_VERSION,
        "minor_version": 1,
        "key": storage_key(entry),
        "data": {
            "enabled": True,
            "status": "running",
            "active_run": {
                "started": local(2026, 9, 14, 4, 50).isoformat(),
                "zones": [{"entity_id": entity_id, "ends_at": None} for entity_id in zones],
            },
        },
    }


async def test_restart_recovery_closes_open_zones(
    hass: HomeAssistant, hass_storage: dict[str, Any], decide, make_runner
) -> None:
    closes = flaky_service(hass, "valve", "close_valve", 0, sets="closed")
    offs = flaky_service(hass, "switch", "turn_off", 0, sets="off")
    hass.states.async_set(ZONE_A, "open")
    hass.states.async_set(ZONE_B, "on")
    entry = MockConfigEntry(domain=DOMAIN, title="Front lawn", data=make_config())
    entry.add_to_hass(hass)
    seed_active_run(hass_storage, entry, [ZONE_A, ZONE_B])

    runner = await make_runner(entry=entry)

    assert [call.data["entity_id"] for call in closes] == [ZONE_A]
    assert [call.data["entity_id"] for call in offs] == [ZONE_B]
    assert runner.status is Status.INTERRUPTED
    assert not runner.running
    assert runner.last_run_start == local(2026, 9, 14, 4, 50)
    stored = hass_storage[storage_key(entry)]["data"]
    assert stored["active_run"] is None
    assert stored["status"] == "interrupted"
    assert runner.snapshot()["next_run"] == local(2026, 9, 14, 6).isoformat()


async def test_restart_recovery_sends_nothing_to_zones_that_read_off(
    hass: HomeAssistant, hass_storage: dict[str, Any], calls, decide, make_runner
) -> None:
    entry = MockConfigEntry(domain=DOMAIN, title="Front lawn", data=make_config())
    entry.add_to_hass(hass)
    seed_active_run(hass_storage, entry, [ZONE_A, ZONE_B])  # both read closed/off

    runner = await make_runner(entry=entry)

    assert not calls["close"]
    assert not calls["off"]
    assert runner.status is Status.INTERRUPTED
    assert runner.unclosed_zones == []
    assert hass_storage[storage_key(entry)]["data"]["active_run"] is None


async def test_recovery_retries_once_home_assistant_has_started(
    hass: HomeAssistant, hass_storage: dict[str, Any], decide, make_runner
) -> None:
    closes = flaky_service(hass, "valve", "close_valve", 0, sets="closed")
    entry = MockConfigEntry(domain=DOMAIN, title="Front lawn", data=make_config())
    entry.add_to_hass(hass)
    seed_active_run(hass_storage, entry, [ZONE_A])
    hass.states.async_remove(ZONE_A)  # zone integration not loaded yet
    hass.set_state(CoreState.starting)

    runner = await make_runner(entry=entry)
    assert not closes
    assert hass_storage[storage_key(entry)]["data"]["active_run"] is not None

    hass.states.async_set(ZONE_A, "open")
    hass.set_state(CoreState.running)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    await settle(hass)

    assert len(closes) == 1
    assert "unclosed_zones" not in runner.last_details
    assert hass_storage[storage_key(entry)]["data"]["active_run"] is None


async def test_unload_mid_run_stops_zone_and_marks_interrupted(
    hass: HomeAssistant, hass_storage: dict[str, Any], freezer: FrozenDateTimeFactory, calls, decide, make_runner
) -> None:
    runner = await make_runner()
    await runner.async_run_now()
    await settle(hass)
    await advance_to(hass, freezer, local(2026, 9, 14, 5, 2))

    await runner.async_unload()
    assert len(calls["close"]) == 1
    assert runner.status is Status.INTERRUPTED
    assert not runner.running
    stored = hass_storage[storage_key(runner.entry)]["data"]
    assert stored["active_run"] is None
    assert stored["status"] == "interrupted"

    await advance_to(hass, freezer, local(2026, 9, 14, 6))
    decide.assert_not_awaited()
    assert not calls["on"]


async def test_state_persists_across_runner_instances(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls, decide, make_runner
) -> None:
    runner = await make_runner()
    await runner.async_run_now()
    await settle(hass)
    await advance_to(hass, freezer, local(2026, 9, 14, 5, 10))
    await advance_to(hass, freezer, local(2026, 9, 14, 5, 15))
    await runner.async_set_skip_next(True)
    await runner.async_set_enabled(False)
    await runner.async_unload()

    restored = await make_runner(entry=runner.entry)
    assert restored.enabled is False
    assert restored.skip_next is True
    assert restored.status is Status.DISABLED
    assert restored.last_run_start == local(2026, 9, 14, 5)
    assert restored.last_run_end == local(2026, 9, 14, 5, 15)
    assert restored.last_run_total_minutes == 15.0
    assert restored.zone_results == runner.zone_results
    assert restored.snapshot()["next_run"] is None


# === v0.2 ======================================================================

RAIN = "sensor.rain_gauge"
PERSON = "binary_sensor.yard_person"
OCCUPIED = Decision(
    water=False,
    status=Status.SKIPPED_OCCUPANCY,
    details={"occupancy": {"on": [PERSON]}},
    retry=True,
)


@pytest.fixture
def subscriptions() -> dict[int, list[str]]:
    """State-change subscriptions the runner made that are still active."""
    active: dict[int, list[str]] = {}
    counter = itertools.count()
    real = event_helper.async_track_state_change_event

    def _track(hass: HomeAssistant, entity_ids: Any, action: Any) -> Callable[[], None]:
        key = next(counter)
        unsub = real(hass, entity_ids, action)
        active[key] = [entity_ids] if isinstance(entity_ids, str) else list(entity_ids)

        def _remove() -> None:
            active.pop(key, None)
            unsub()

        return _remove

    with patch("custom_components.irrigation_manager.runner.async_track_state_change_event", _track):
        yield active


def event_types(events: list) -> list[str]:
    return [event.data["type"] for event in events]


# --- rain delay -----------------------------------------------------------------


async def test_rain_delay_skips_scheduled_occurrences_until_it_ends(
    hass: HomeAssistant, hass_storage: dict[str, Any], freezer: FrozenDateTimeFactory, calls, decide, make_runner
) -> None:
    runner = await make_runner()
    events = async_capture_events(hass, EVENT_IRRIGATION)

    await runner.async_set_rain_delay(26)  # until Tue 07:00
    until = local(2026, 9, 15, 7)
    assert runner.rain_delay_until == until
    assert runner.snapshot()["rain_delay_until"] == until.isoformat()
    assert events[-1].data["type"] == "rain_delay_set"
    assert events[-1].data["rain_delay_until"] == until.isoformat()
    assert hass_storage[storage_key(runner.entry)]["data"]["rain_delay_until"] == until.isoformat()

    await advance_to(hass, freezer, local(2026, 9, 14, 6))
    decide.assert_not_awaited()
    assert runner.status is Status.SKIPPED_RAIN_DELAY
    assert runner.last_details == {"rain_delay_until": until.isoformat()}
    assert runner.history()[0]["status"] == "skipped_rain_delay"
    assert events[-1].data["type"] == "skipped"
    assert events[-1].data["status"] == "skipped_rain_delay"

    await advance_to(hass, freezer, local(2026, 9, 15, 6))
    decide.assert_not_awaited()

    await advance_to(hass, freezer, local(2026, 9, 15, 7))
    assert runner.rain_delay_until is None
    assert hass_storage[storage_key(runner.entry)]["data"]["rain_delay_until"] is None

    await advance_to(hass, freezer, local(2026, 9, 16, 6))
    decide.assert_awaited_once()
    assert len(calls["open"]) == 1


async def test_rain_delay_clears_clamps_and_rejects_nan(
    hass: HomeAssistant, calls, decide, make_runner
) -> None:
    runner = await make_runner()
    await runner.async_set_rain_delay(10_000)
    assert runner.rain_delay_until == dt_util.now() + timedelta(hours=MAX_RAIN_DELAY_HOURS)

    await runner.async_set_rain_delay(0)
    assert runner.rain_delay_until is None

    with pytest.raises(HomeAssistantError):
        await runner.async_set_rain_delay(float("nan"))


async def test_rain_delay_survives_restart(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls, decide, make_runner
) -> None:
    runner = await make_runner()
    await runner.async_set_rain_delay(3)
    await runner.async_unload()

    restored = await make_runner(entry=runner.entry)
    assert restored.rain_delay_until == local(2026, 9, 14, 8)
    await advance_to(hass, freezer, local(2026, 9, 14, 6))
    decide.assert_not_awaited()
    assert restored.status is Status.SKIPPED_RAIN_DELAY


async def test_rain_delay_is_quiet_on_moisture_check_days(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls, decide, make_runner
) -> None:
    config = make_config(
        **{
            CONF_FREQUENCY: "interval",
            CONF_INTERVAL_DAYS: 3,
            CONF_ANCHOR: "2026-09-13",
            CONF_SKIP_CONDITIONS: ["moisture"],
            CONF_MOISTURE_MODE: "trigger",
        }
    )
    config.pop(CONF_WEEKDAYS)
    runner = await make_runner(config)
    await runner.async_set_rain_delay(12)

    await advance_to(hass, freezer, local(2026, 9, 14, 6))  # not a schedule day
    decide.assert_not_awaited()
    assert runner.status is Status.IDLE
    assert runner.history() == []


async def test_rain_skip_starts_automatic_rain_delay(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls, decide, make_runner
) -> None:
    decide.return_value = Decision(water=False, status=Status.SKIPPED_RAIN, details={"rain": {"total": 0.4}})
    runner = await make_runner(make_config(**{CONF_RAIN_DELAY_AUTO_HOURS: 48}))

    await advance_to(hass, freezer, local(2026, 9, 14, 6))
    assert runner.status is Status.SKIPPED_RAIN
    assert runner.rain_delay_until == local(2026, 9, 16, 6)


async def test_forecast_skip_does_not_start_automatic_rain_delay(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls, decide, make_runner
) -> None:
    decide.return_value = Decision(water=False, status=Status.SKIPPED_FORECAST)
    runner = await make_runner(make_config(**{CONF_RAIN_DELAY_AUTO_HOURS: 48}))
    await advance_to(hass, freezer, local(2026, 9, 14, 6))
    assert runner.rain_delay_until is None


async def test_rain_delay_is_copied_to_zone_drivers_only_when_enabled(
    hass: HomeAssistant, calls, decide, make_runner
) -> None:
    mirror = AsyncMock()
    with patch("custom_components.irrigation_manager.drivers.ZoneDriver.async_set_rain_delay", mirror):
        plain = await make_runner()
        await plain.async_set_rain_delay(24)
        mirror.assert_not_awaited()

        entry = MockConfigEntry(domain=DOMAIN, title="Mirrored", data=make_config(**{CONF_RAIN_DELAY_MIRROR: True}))
        entry.add_to_hass(hass)
        mirrored = await make_runner(entry=entry)
        await mirrored.async_set_rain_delay(24)
        await mirrored.async_set_rain_delay(0)

    assert [call.args for call in mirror.await_args_list] == [(24.0,), (24.0,), (0.0,), (0.0,)]


async def test_rain_delay_copy_failure_is_logged_not_raised(
    hass: HomeAssistant, calls, decide, make_runner, caplog: pytest.LogCaptureFixture
) -> None:
    mirror = AsyncMock(side_effect=HomeAssistantError("device offline"))
    with patch("custom_components.irrigation_manager.drivers.ZoneDriver.async_set_rain_delay", mirror):
        runner = await make_runner(make_config(**{CONF_RAIN_DELAY_MIRROR: True}))
        await runner.async_set_rain_delay(24)
    assert runner.rain_delay_until is not None
    assert "device offline" in caplog.text


# --- stop during run --------------------------------------------------------------


async def test_rain_during_run_stops_it(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls, decide, make_runner, subscriptions
) -> None:
    hass.states.async_set(RAIN, "1.00")
    runner = await make_runner(
        make_config(**{CONF_RAIN_STOP_DURING_RUN: True, CONF_RAIN_SENSORS: [RAIN], CONF_RAIN_STOP_AMOUNT: 0.05})
    )
    events = async_capture_events(hass, EVENT_IRRIGATION)
    await runner.async_run_now()
    await settle(hass)
    assert len(subscriptions) == 1

    hass.states.async_set(RAIN, "1.03")
    await settle(hass)
    assert runner.running

    hass.states.async_set(RAIN, "1.06")
    await settle(hass)
    assert not runner.running
    assert runner.status is Status.STOPPED_RAIN
    assert len(calls["close"]) == 1
    assert not calls["on"]
    assert runner.last_details["rain_stop"] == {"entity_id": RAIN, "rise": 0.06, "amount": 0.05}
    assert runner.history()[0]["status"] == "stopped_rain"
    assert events[-1].data["type"] == "run_finished"
    assert events[-1].data["status"] == "stopped_rain"
    assert not subscriptions


async def test_rain_stop_handles_meter_reset_and_late_baseline(
    hass: HomeAssistant, calls, decide, make_runner, subscriptions
) -> None:
    hass.states.async_set(RAIN, "unavailable")
    # v0.1 single-sensor key.
    runner = await make_runner(
        make_config(**{CONF_RAIN_STOP_DURING_RUN: True, CONF_RAIN_SENSOR: RAIN, CONF_RAIN_STOP_AMOUNT: 0.05})
    )
    await runner.async_run_now()
    await settle(hass)

    for value in ("0.98", "0.00", "0.02", "0.04"):  # baseline, reset, +0.02, +0.02
        hass.states.async_set(RAIN, value)
        await settle(hass)
        assert runner.running, value

    hass.states.async_set(RAIN, "0.05")
    await settle(hass)
    assert runner.status is Status.STOPPED_RAIN
    assert runner.last_details["rain_stop"]["rise"] == 0.05


async def test_zero_rain_stop_amount_does_not_watch(
    hass: HomeAssistant, calls, decide, make_runner, subscriptions
) -> None:
    hass.states.async_set(RAIN, "1.00")
    runner = await make_runner(
        make_config(**{CONF_RAIN_STOP_DURING_RUN: True, CONF_RAIN_SENSORS: [RAIN], CONF_RAIN_STOP_AMOUNT: 0})
    )
    await runner.async_run_now()
    await settle(hass)
    assert not subscriptions
    hass.states.async_set(RAIN, "1.00", {"updated": True})
    await settle(hass)
    assert runner.running


async def test_occupancy_during_run_stops_it(
    hass: HomeAssistant, calls, decide, make_runner, subscriptions
) -> None:
    hass.states.async_set(PERSON, "off")
    runner = await make_runner(
        make_config(**{CONF_OCCUPANCY_STOP_DURING_RUN: True, CONF_OCCUPANCY_ENTITIES: [PERSON]})
    )
    await runner.async_run_now()
    await settle(hass)

    hass.states.async_set(PERSON, "on")
    await settle(hass)
    assert not runner.running
    assert runner.status is Status.STOPPED_OCCUPANCY
    assert runner.last_details["occupancy_stop"] == {"entity_id": PERSON}
    assert len(calls["close"]) == 1
    assert not subscriptions


async def test_manual_stop_keeps_an_earlier_rain_stop_reason(
    hass: HomeAssistant, calls, decide, make_runner, subscriptions
) -> None:
    hass.states.async_set(RAIN, "1.00")
    runner = await make_runner(
        make_config(**{CONF_RAIN_STOP_DURING_RUN: True, CONF_RAIN_SENSORS: [RAIN], CONF_RAIN_STOP_AMOUNT: 0.05})
    )
    await runner.async_run_now()
    await settle(hass)
    runner._signal_stop(Status.STOPPED_RAIN, {"rain_stop": {"entity_id": RAIN}})  # noqa: SLF001
    await runner.async_stop_run()
    await settle(hass)
    assert runner.status is Status.STOPPED_RAIN


@pytest.mark.parametrize("how", ["stop", "unload", "config", "finish"])
async def test_run_watchers_are_removed(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls, decide, make_runner, subscriptions, how: str
) -> None:
    hass.states.async_set(RAIN, "1.00")
    hass.states.async_set(PERSON, "off")
    config = make_config(
        **{
            CONF_RAIN_STOP_DURING_RUN: True,
            CONF_RAIN_SENSORS: [RAIN],
            CONF_OCCUPANCY_STOP_DURING_RUN: True,
            CONF_OCCUPANCY_ENTITIES: [PERSON],
        }
    )
    runner = await make_runner(config)
    await runner.async_run_now()
    await settle(hass)
    assert len(subscriptions) == 2

    if how == "stop":
        await runner.async_stop_run()
    elif how == "unload":
        await runner.async_unload()
    elif how == "config":
        await runner.async_update_config(make_config())
    else:
        await advance_to(hass, freezer, local(2026, 9, 14, 5, 10))
        await advance_to(hass, freezer, local(2026, 9, 14, 5, 15))
    await settle(hass)
    assert not subscriptions

    if how == "config":
        # The run continues and no longer reacts to rain or people.
        hass.states.async_set(RAIN, "2.00")
        hass.states.async_set(PERSON, "on")
        await settle(hass)
        assert runner.running


async def test_config_change_mid_run_keeps_rain_counted_so_far(
    hass: HomeAssistant, calls, decide, make_runner
) -> None:
    hass.states.async_set(RAIN, "1.00")
    runner = await make_runner(
        make_config(**{CONF_RAIN_STOP_DURING_RUN: True, CONF_RAIN_SENSORS: [RAIN], CONF_RAIN_STOP_AMOUNT: 0.05})
    )
    await runner.async_run_now()
    await settle(hass)

    hass.states.async_set(RAIN, "1.04")
    await settle(hass)
    await runner.async_set_zone_minutes(ZONE_A, 20)  # restarts the watchers
    await settle(hass)
    assert runner.running

    hass.states.async_set(RAIN, "1.06")
    await settle(hass)
    assert runner.status is Status.STOPPED_RAIN
    assert runner.last_details["rain_stop"]["rise"] == 0.06


# --- zones whose close failed ----------------------------------------------------

ONE_ZONE = {CONF_ZONES: [{CONF_ZONE_ENTITY: ZONE_A, CONF_ZONE_MINUTES: 10}]}


def flaky_service(
    hass: HomeAssistant, domain: str, service: str, failures: int, sets: str | None = None
) -> list[ServiceCall]:
    """A service that raises HomeAssistantError for its first `failures` calls.

    `sets` is the state the targeted entities take when a call succeeds (what
    a real integration does after the device confirms); the mocked services
    from the `calls` fixture never change state.
    """
    received: list[ServiceCall] = []

    async def _handle(call: ServiceCall) -> None:
        received.append(call)
        if len(received) <= failures:
            raise HomeAssistantError("stuck")
        if sets is not None:
            ids = call.data["entity_id"]
            for entity_id in ids if isinstance(ids, list) else [ids]:
                hass.states.async_set(entity_id, sets)

    hass.services.async_register(domain, service, _handle)
    return received


NATIVE = "valve.native_zone"
NATIVE_ZONE = {CONF_ZONES: [{CONF_ZONE_ENTITY: NATIVE, CONF_ZONE_MINUTES: 10}]}


def native_zone(hass: HomeAssistant) -> None:
    """NATIVE registered under orbit_bhyve (a native-duration driver), reading closed.

    orbit_bhyve.start_watering marks it open; valve.close_valve is registered
    by each test with the behaviour it needs.
    """
    entry = er.async_get(hass).async_get_or_create(
        "valve", "orbit_bhyve", "orbit_bhyve-native", suggested_object_id="native_zone"
    )
    assert entry.entity_id == NATIVE
    hass.states.async_set(NATIVE, "closed")
    flaky_service(hass, "orbit_bhyve", "start_watering", 0, sets="open")


def device_reads(hass: HomeAssistant, device: dict[str, str]) -> list[ServiceCall]:
    """homeassistant.update_entity that copies the real device state (`device`,
    mutable) into the entity, like an integration's fresh device read."""
    received: list[ServiceCall] = []

    async def _handle(call: ServiceCall) -> None:
        received.append(call)
        for entity_id in call.data["entity_id"]:
            if entity_id in device:
                hass.states.async_set(entity_id, device[entity_id])

    hass.services.async_register("homeassistant", "update_entity", _handle)
    return received


def seed_store(hass_storage: dict[str, Any], entry: MockConfigEntry, data: dict[str, Any]) -> None:
    hass_storage[storage_key(entry)] = {
        "version": STORAGE_VERSION,
        "minor_version": 1,
        "key": storage_key(entry),
        "data": data,
    }


async def test_failed_zone_close_is_retried_until_it_closes(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    freezer: FrozenDateTimeFactory,
    decide,
    make_runner,
    subscriptions,
    caplog: pytest.LogCaptureFixture,
) -> None:
    flaky_service(hass, "valve", "open_valve", 0, sets="open")
    closes = flaky_service(hass, "valve", "close_valve", failures=2, sets="closed")

    runner = await make_runner(make_config(**ONE_ZONE))
    await runner.async_run_now()
    await settle(hass)
    await advance_to(hass, freezer, local(2026, 9, 14, 5, 10))

    assert len(closes) == 1
    assert not runner.running
    assert runner.status is Status.ERROR
    assert runner.unclosed_zones == [ZONE_A]
    assert runner.snapshot()["unclosed_zones"] == [ZONE_A]
    assert runner.last_details["unclosed_zones"] == [ZONE_A]
    assert hass_storage[storage_key(runner.entry)]["data"]["unclosed_zones"] == [ZONE_A]
    assert f"could not close {ZONE_A}" in caplog.text
    assert [ZONE_A] in subscriptions.values()  # watching for the entity to come back

    await advance_to(hass, freezer, local(2026, 9, 14, 5, 11))  # 1 min: fails again
    assert len(closes) == 2
    assert runner.unclosed_zones == [ZONE_A]
    assert "closing it failed again" in caplog.text

    await advance_to(hass, freezer, local(2026, 9, 14, 5, 15))  # next wait is 5 min
    assert len(closes) == 2
    await advance_to(hass, freezer, local(2026, 9, 14, 5, 16))
    assert len(closes) == 3
    assert runner.unclosed_zones == []
    assert "unclosed_zones" not in runner.last_details
    assert hass_storage[storage_key(runner.entry)]["data"]["unclosed_zones"] == []
    assert not subscriptions

    await advance_to(hass, freezer, local(2026, 9, 14, 5, 45))
    assert len(closes) == 3


async def test_unclosed_zone_is_closed_when_its_entity_comes_back(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, decide, make_runner, subscriptions
) -> None:
    async_mock_service(hass, "valve", "open_valve")
    closes = flaky_service(hass, "valve", "close_valve", 0, sets="closed")

    runner = await make_runner(make_config(**ONE_ZONE))
    await runner.async_run_now()
    await settle(hass)
    hass.states.async_set(ZONE_A, "unavailable")  # drops off before its close
    await advance_to(hass, freezer, local(2026, 9, 14, 5, 10))

    assert not closes  # drivers refuse an unavailable entity
    assert runner.unclosed_zones == [ZONE_A]

    await advance_to(hass, freezer, local(2026, 9, 14, 5, 10, 30))
    hass.states.async_set(ZONE_A, "open")  # back, well before the 1 min retry
    await settle(hass)
    assert len(closes) == 1
    assert runner.unclosed_zones == []
    assert not subscriptions


async def test_unclosed_zones_survive_a_restart(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    freezer: FrozenDateTimeFactory,
    decide,
    make_runner,
) -> None:
    flaky_service(hass, "valve", "open_valve", 0, sets="open")
    closes = flaky_service(hass, "valve", "close_valve", failures=2, sets="closed")
    entry = MockConfigEntry(domain=DOMAIN, title="Front lawn", data=make_config(**ONE_ZONE))
    entry.add_to_hass(hass)

    first = await make_runner(entry=entry)
    await first.async_run_now()
    await settle(hass)
    await advance_to(hass, freezer, local(2026, 9, 14, 5, 10))
    await first.async_unload()  # one more try on the way out, still failing

    assert len(closes) == 2
    stored = hass_storage[storage_key(entry)]["data"]
    assert (stored["unclosed_zones"], stored["active_run"]) == ([ZONE_A], None)

    second = await make_runner(entry=entry)  # the next start retries right away
    assert len(closes) == 3
    assert second.unclosed_zones == []
    assert hass_storage[storage_key(entry)]["data"]["unclosed_zones"] == []


async def test_v01_unclosed_zones_in_details_are_retried(
    hass: HomeAssistant, hass_storage: dict[str, Any], decide, make_runner
) -> None:
    offs = flaky_service(hass, "switch", "turn_off", 0, sets="off")
    hass.states.async_set(ZONE_B, "on")
    entry = MockConfigEntry(domain=DOMAIN, title="Front lawn", data=make_config())
    entry.add_to_hass(hass)
    seed_store(
        hass_storage,
        entry,
        {"enabled": True, "status": "interrupted", "last_details": {"unclosed_zones": [ZONE_B]}},
    )

    runner = await make_runner(entry=entry)

    assert [call.data["entity_id"] for call in offs] == [ZONE_B]
    assert runner.unclosed_zones == []
    assert "unclosed_zones" not in runner.last_details


async def test_unload_cancels_unclosed_zone_retries(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, decide, make_runner, subscriptions
) -> None:
    flaky_service(hass, "valve", "open_valve", 0, sets="open")
    closes = flaky_service(hass, "valve", "close_valve", failures=100)

    runner = await make_runner(make_config(**ONE_ZONE))
    await runner.async_run_now()
    await settle(hass)
    await advance_to(hass, freezer, local(2026, 9, 14, 5, 10))
    assert len(closes) == 1

    await runner.async_unload()
    assert len(closes) == 2  # the last try on unload
    assert not subscriptions

    hass.states.async_set(ZONE_A, "open", {"came_back": True})
    await advance_to(hass, freezer, local(2026, 9, 14, 5, 45))
    assert len(closes) == 2


@pytest.mark.parametrize("still_stuck", [True, False])
async def test_run_closes_an_unclosed_zone_before_watering_it(
    hass: HomeAssistant,
    hass_storage: dict[str, Any],
    decide,
    make_runner,
    still_stuck: bool,
) -> None:
    opens = async_mock_service(hass, "valve", "open_valve")
    # Fails the startup retry; then fails again or succeeds before watering.
    closes = flaky_service(
        hass, "valve", "close_valve", failures=100 if still_stuck else 1, sets="closed"
    )
    ons = async_mock_service(hass, "switch", "turn_on")
    async_mock_service(hass, "switch", "turn_off")
    hass.states.async_set(ZONE_A, "open")  # left open by the earlier failure
    entry = MockConfigEntry(domain=DOMAIN, title="Front lawn", data=make_config())
    entry.add_to_hass(hass)
    seed_store(hass_storage, entry, {"enabled": True, "unclosed_zones": [ZONE_A]})

    runner = await make_runner(entry=entry)
    assert len(closes) == 1

    await runner.async_run_now()
    await settle(hass)

    assert len(closes) == 2  # tried again before opening it
    if still_stuck:
        assert not opens
        assert [call.data["entity_id"] for call in ons] == [ZONE_B]  # moved on
        assert runner.zone_results[0]["entity_id"] == ZONE_A
        assert "can't be closed" in runner.zone_results[0]["error"]
        assert runner.unclosed_zones == [ZONE_A]
    else:
        assert [call.data["entity_id"] for call in opens] == [ZONE_A]
        assert runner.unclosed_zones == []
        assert not ons  # zone B waits for zone A


async def test_recovery_does_not_close_a_zone_a_new_run_opened(
    hass: HomeAssistant, hass_storage: dict[str, Any], calls, decide, make_runner
) -> None:
    entry = MockConfigEntry(domain=DOMAIN, title="Front lawn", data=make_config())
    entry.add_to_hass(hass)
    seed_active_run(hass_storage, entry, [ZONE_A])
    hass.states.async_remove(ZONE_A)  # zone integration not loaded yet
    hass.set_state(CoreState.starting)

    runner = await make_runner(entry=entry)
    assert not calls["close"]

    hass.states.async_set(ZONE_A, "closed")
    await runner.async_run_now()  # a new run opens the valve before startup finishes
    await settle(hass)
    assert [call.data["entity_id"] for call in calls["open"]] == [ZONE_A]

    hass.set_state(CoreState.running)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    await settle(hass)

    assert not calls["close"]  # the run owns the valve now
    assert runner.running
    assert runner.unclosed_zones == []
    assert hass_storage[storage_key(entry)]["data"]["active_run"]["zones"][0]["entity_id"] == ZONE_A


# --- occupancy delay ----------------------------------------------------------------


async def test_occupancy_delay_retries_until_clear(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls, decide, make_runner
) -> None:
    decide.side_effect = [OCCUPIED, OCCUPIED, Decision(water=True)]
    runner = await make_runner(make_config(**{CONF_OCCUPANCY_MAX_DELAY: 10}))

    await advance_to(hass, freezer, local(2026, 9, 14, 6))
    assert decide.await_count == 1
    assert not runner.running
    assert runner.status is Status.IDLE
    assert runner.last_details["occupancy_delay_until"] == local(2026, 9, 14, 6, 10).isoformat()

    await advance_to(hass, freezer, local(2026, 9, 14, 6, 2))
    assert decide.await_count == 2
    await advance_to(hass, freezer, local(2026, 9, 14, 6, 4))
    assert decide.await_count == 3
    assert runner.running
    assert len(calls["open"]) == 1
    assert runner.history() == []


async def test_occupancy_delay_gives_up_after_max_delay(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls, decide, make_runner
) -> None:
    decide.return_value = OCCUPIED
    runner = await make_runner(make_config(**{CONF_OCCUPANCY_MAX_DELAY: 3}))

    await advance_to(hass, freezer, local(2026, 9, 14, 6))
    assert decide.await_count == 1
    await advance_to(hass, freezer, local(2026, 9, 14, 6, 2))
    assert decide.await_count == 2
    assert runner.status is Status.SKIPPED_OCCUPANCY
    assert [record["status"] for record in runner.history()] == ["skipped_occupancy"]

    await advance_to(hass, freezer, local(2026, 9, 14, 6, 4))
    assert decide.await_count == 2
    assert not any(calls.values())


@pytest.mark.parametrize("how", ["stop", "unload", "config", "disable", "pause"])
async def test_pending_occupancy_retry_is_cancelled(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls, decide, make_runner, how: str
) -> None:
    decide.return_value = OCCUPIED
    runner = await make_runner(make_config(**{CONF_OCCUPANCY_MAX_DELAY: 30}))
    await advance_to(hass, freezer, local(2026, 9, 14, 6))
    assert decide.await_count == 1

    if how == "stop":
        await runner.async_stop_run()
    elif how == "unload":
        await runner.async_unload()
    elif how == "config":
        await runner.async_update_config(make_config(**{CONF_OCCUPANCY_MAX_DELAY: 30}))
    elif how == "disable":
        await runner.async_set_enabled(False)
    else:
        await runner.async_set_paused(True)

    await advance_to(hass, freezer, local(2026, 9, 14, 6, 2))
    await advance_to(hass, freezer, local(2026, 9, 14, 6, 4))
    assert decide.await_count == 1
    assert not any(calls.values())


# --- pause ------------------------------------------------------------------------


async def test_pause_skips_quietly_and_resume_restores(
    hass: HomeAssistant, hass_storage: dict[str, Any], freezer: FrozenDateTimeFactory, calls, decide, make_runner
) -> None:
    runner = await make_runner()
    events = async_capture_events(hass, EVENT_IRRIGATION)

    await runner.async_set_paused(True)
    assert runner.paused
    assert runner.status is Status.PAUSED
    assert runner.snapshot()["paused"] is True
    assert runner.snapshot()["next_run"] == local(2026, 9, 14, 6).isoformat()
    assert hass_storage[storage_key(runner.entry)]["data"]["paused"] is True
    assert event_types(events) == ["paused"]

    await advance_to(hass, freezer, local(2026, 9, 14, 6))
    decide.assert_not_awaited()
    assert not any(calls.values())
    assert runner.status is Status.PAUSED
    assert runner.history() == []

    await runner.async_set_paused(False)
    assert runner.status is Status.IDLE
    assert event_types(events) == ["paused", "resumed"]

    await advance_to(hass, freezer, local(2026, 9, 15, 6))
    decide.assert_awaited_once()


async def test_pause_does_not_stop_an_active_run(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls, decide, make_runner
) -> None:
    runner = await make_runner()
    await runner.async_run_now()
    await settle(hass)

    await runner.async_set_paused(True)
    assert runner.running
    assert runner.status is Status.RUNNING

    await advance_to(hass, freezer, local(2026, 9, 14, 5, 10))
    await advance_to(hass, freezer, local(2026, 9, 14, 5, 15))
    assert not runner.running
    assert runner.status is Status.PAUSED


async def test_pause_while_disabled_keeps_disabled_status(
    hass: HomeAssistant, calls, decide, make_runner
) -> None:
    runner = await make_runner()
    await runner.async_set_enabled(False)
    await runner.async_set_paused(True)
    assert runner.status is Status.DISABLED
    await runner.async_set_enabled(True)
    assert runner.status is Status.PAUSED


# --- run_zone, evaluate -------------------------------------------------------------


async def test_run_zone_waters_one_zone(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls, decide, make_runner
) -> None:
    runner = await make_runner()
    events = async_capture_events(hass, EVENT_IRRIGATION)

    with pytest.raises(HomeAssistantError, match="not a zone"):
        await runner.async_run_zone("switch.other", 5)

    await runner.async_run_zone(ZONE_B, 3)
    await settle(hass)
    decide.assert_not_awaited()
    assert [call.data["entity_id"] for call in calls["on"]] == [ZONE_B]
    assert not calls["open"]
    assert events[0].data["manual"] is True
    assert events[0].data["zones"] == [ZONE_B]

    with pytest.raises(HomeAssistantError, match="already running"):
        await runner.async_run_zone(ZONE_A, 3)

    await advance_to(hass, freezer, local(2026, 9, 14, 5, 3))
    assert len(calls["off"]) == 1
    assert not runner.running
    record = runner.history()[0]
    assert record["manual"] is True
    assert record["zones"] == [
        {"entity_id": ZONE_B, "minutes": 3.0, "error": None, "stopped_by": "manager"}
    ]


async def test_evaluate_reports_decision_without_side_effects(
    hass: HomeAssistant, calls, decide, make_runner
) -> None:
    details = {"rain": {"total": 0.4, "threshold": 0.1}}
    decide.return_value = Decision(water=False, status=Status.SKIPPED_RAIN, details=details)
    runner = await make_runner()
    await runner.async_set_rain_delay(1)

    result = await runner.async_evaluate()
    assert result == {
        "at": local(2026, 9, 14, 5).isoformat(),
        "scheduled": True,
        "rain_delay_until": local(2026, 9, 14, 6).isoformat(),
        "paused": False,
        "enabled": True,
        "decision": {"water": False, "status": "skipped_rain", "details": details, "retry": False},
    }
    assert decide.await_args.kwargs["scheduled"] is True
    assert runner.status is Status.IDLE
    assert runner.last_details == {}
    assert runner.history() == []
    assert not any(calls.values())

    decide.side_effect = RuntimeError("boom")
    result = await runner.async_evaluate()
    assert result["decision"] == {
        "water": True,
        "status": None,
        "details": {"error": "condition check failed"},
        "retry": False,
    }


# --- history, last watering, events ---------------------------------------------


async def test_history_records_runs_and_skips_and_persists(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls, decide, make_runner
) -> None:
    runner = await make_runner()
    await runner.async_run_now()
    await settle(hass)
    await advance_to(hass, freezer, local(2026, 9, 14, 5, 10))
    await advance_to(hass, freezer, local(2026, 9, 14, 5, 15))

    skip_details = {"rain": {"total": 0.4}}
    decide.return_value = Decision(water=False, status=Status.SKIPPED_RAIN, details=skip_details)
    await advance_to(hass, freezer, local(2026, 9, 14, 6))

    history = runner.history()
    assert history == [
        {
            "at": local(2026, 9, 14, 6).isoformat(),
            "type": "skip",
            "status": "skipped_rain",
            "manual": False,
            "started": None,
            "zones": [],
            "total_minutes": 0.0,
            "details": skip_details,
        },
        {
            "at": local(2026, 9, 14, 5, 15).isoformat(),
            "type": "run",
            "status": "idle",
            "manual": True,
            "started": local(2026, 9, 14, 5).isoformat(),
            "zones": [
                {"entity_id": ZONE_A, "minutes": 10.0, "error": None, "stopped_by": "manager"},
                {"entity_id": ZONE_B, "minutes": 5.0, "error": None, "stopped_by": "manager"},
            ],
            "total_minutes": 15.0,
            "details": {"manual": True},
        },
    ]
    assert runner.history(limit=1) == history[:1]
    assert runner.snapshot()["history"] == history

    await runner.async_unload()
    restored = await make_runner(entry=runner.entry)
    assert restored.history() == history


async def test_history_is_capped(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls, decide, make_runner
) -> None:
    with patch("custom_components.irrigation_manager.runner.HISTORY_LIMIT", 3):
        runner = await make_runner()
        await runner.async_set_rain_delay(MAX_RAIN_DELAY_HOURS)
        for day in range(14, 19):
            await advance_to(hass, freezer, local(2026, 9, day, 6))
        history = runner.history()
    assert len(history) == 3
    assert [record["at"] for record in history] == [
        local(2026, 9, day, 6).isoformat() for day in (18, 17, 16)
    ]


async def test_last_watering_end_is_passed_to_conditions(
    hass: HomeAssistant, hass_storage: dict[str, Any], freezer: FrozenDateTimeFactory, calls, decide, make_runner
) -> None:
    runner = await make_runner()
    # A run stopped before any time passed doesn't count as watering.
    await runner.async_run_now()
    await settle(hass)
    await runner.async_stop_run()
    await settle(hass)
    assert runner.last_watering_end is None

    await runner.async_run_now()
    await settle(hass)
    await advance_to(hass, freezer, local(2026, 9, 14, 5, 10))
    await advance_to(hass, freezer, local(2026, 9, 14, 5, 15))
    assert runner.last_watering_end == local(2026, 9, 14, 5, 15)
    assert runner.snapshot()["last_watering_end"] == local(2026, 9, 14, 5, 15).isoformat()
    assert hass_storage[storage_key(runner.entry)]["data"]["last_watering_end"] == local(2026, 9, 14, 5, 15).isoformat()

    decide.return_value = Decision(water=False, status=Status.SKIPPED_RAIN)
    await advance_to(hass, freezer, local(2026, 9, 14, 6))
    assert decide.await_args.kwargs["last_watering_end"] == local(2026, 9, 14, 5, 15)


async def test_events_for_a_scheduled_run(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls, decide, make_runner
) -> None:
    entry = MockConfigEntry(domain=DOMAIN, title="Front lawn", data=make_config())
    entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, entry.entry_id)}
    )
    events = async_capture_events(hass, EVENT_IRRIGATION)
    await make_runner(entry=entry)

    await advance_to(hass, freezer, local(2026, 9, 14, 6))
    await advance_to(hass, freezer, local(2026, 9, 14, 6, 10))
    await advance_to(hass, freezer, local(2026, 9, 14, 6, 15))

    assert event_types(events) == [
        "run_started", "zone_started", "zone_finished", "zone_started", "zone_finished", "run_finished",
    ]
    assert events[0].data == {
        "entry_id": entry.entry_id,
        "device_id": device.id,
        "name": "Front lawn",
        "type": "run_started",
        "manual": False,
        "zones": [ZONE_A, ZONE_B],
    }
    assert events[1].data["zone"] == ZONE_A
    assert dt_util.parse_datetime(events[1].data["ends_at"]) == local(2026, 9, 14, 6, 10)
    assert events[2].data["zone"] == ZONE_A
    assert events[2].data["minutes"] == 10.0
    assert events[2].data["error"] is None
    assert events[-1].data["status"] == "idle"
    assert events[-1].data["total_minutes"] == 15.0


async def test_busy_skip_is_recorded_as_event_and_history(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, calls, decide, make_runner
) -> None:
    runner = await make_runner()
    events = async_capture_events(hass, EVENT_IRRIGATION)
    await runner.async_run_now(minutes=90)
    await settle(hass)

    await advance_to(hass, freezer, local(2026, 9, 14, 6))
    skipped = [event.data for event in events if event.data["type"] == "skipped"]
    assert skipped[0]["status"] == "skipped_busy"
    assert runner.history()[0]["status"] == "skipped_busy"


# --- end of zone: devices that stop themselves --------------------------------------


async def test_native_zone_closed_by_device_gets_no_stop(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, decide, make_runner
) -> None:
    """The device closes itself at its end; the fresh read 10 s later sees that."""
    native_zone(hass)
    closes = flaky_service(hass, "valve", "close_valve", 0, sets="closed")
    device = {NATIVE: "open"}
    reads = device_reads(hass, device)

    runner = await make_runner(make_config(**NATIVE_ZONE))
    await runner.async_run_now()
    await settle(hass)
    assert hass.states.get(NATIVE).state == "open"

    await advance_to(hass, freezer, local(2026, 9, 14, 5, 10))
    assert runner.running
    assert not reads and not closes
    device[NATIVE] = "closed"  # closed itself; the cached state still reads open
    await advance_to(hass, freezer, local(2026, 9, 14, 5, 10, 10))

    assert not runner.running
    assert [call.data["entity_id"] for call in reads] == [[NATIVE]]
    assert not closes
    assert runner.status is Status.IDLE
    assert runner.zone_results == [
        {"entity_id": NATIVE, "minutes": 10.2, "error": None, "stopped_by": "device"}
    ]
    assert runner.last_run_total_minutes == 10.2


async def test_native_zone_off_at_the_second_read_gets_no_stop(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, decide, make_runner
) -> None:
    native_zone(hass)
    closes = flaky_service(hass, "valve", "close_valve", 0, sets="closed")
    device = {NATIVE: "open"}
    reads = device_reads(hass, device)

    runner = await make_runner(make_config(**NATIVE_ZONE))
    await runner.async_run_now()
    await settle(hass)
    await advance_to(hass, freezer, local(2026, 9, 14, 5, 10))
    await advance_to(hass, freezer, local(2026, 9, 14, 5, 10, 10))
    assert len(reads) == 1
    assert runner.running
    device[NATIVE] = "closed"
    await advance_to(hass, freezer, local(2026, 9, 14, 5, 10, 20))

    assert len(reads) == 2
    assert not closes
    assert not runner.running
    assert runner.zone_results[0]["stopped_by"] == "device"
    assert runner.zone_results[0]["minutes"] == 10.3


async def test_native_zone_still_on_after_both_reads_gets_one_verified_stop(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, decide, make_runner
) -> None:
    native_zone(hass)
    device = {NATIVE: "open"}
    reads = device_reads(hass, device)

    async def _close(call: ServiceCall) -> None:
        device[NATIVE] = "closed"  # the device confirms; the read reflects it

    closes = async_mock_service(hass, "valve", "close_valve")
    hass.services.async_register("valve", "close_valve", _close)

    runner = await make_runner(make_config(**NATIVE_ZONE))
    await runner.async_run_now()
    await settle(hass)
    await advance_to(hass, freezer, local(2026, 9, 14, 5, 10))
    await advance_to(hass, freezer, local(2026, 9, 14, 5, 10, 10))
    await advance_to(hass, freezer, local(2026, 9, 14, 5, 10, 20))

    assert device[NATIVE] == "closed"  # exactly one stop went out
    assert len(reads) == 3  # two end-of-zone reads, one after the stop
    assert not runner.running
    assert runner.status is Status.IDLE
    assert runner.zone_results == [
        {"entity_id": NATIVE, "minutes": 10.3, "error": None, "stopped_by": "manager"}
    ]
    del closes


async def test_native_zone_stop_that_leaves_it_on_is_retried_only_when_it_reads_on(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    decide,
    make_runner,
    caplog: pytest.LogCaptureFixture,
) -> None:
    native_zone(hass)
    device = {NATIVE: "open"}
    device_reads(hass, device)
    closes = async_mock_service(hass, "valve", "close_valve")  # never closes it

    runner = await make_runner(make_config(**NATIVE_ZONE))
    await runner.async_run_now()
    await settle(hass)
    await advance_to(hass, freezer, local(2026, 9, 14, 5, 10))
    await advance_to(hass, freezer, local(2026, 9, 14, 5, 10, 10))
    await advance_to(hass, freezer, local(2026, 9, 14, 5, 10, 20))
    assert len(closes) == 1
    assert runner.running  # verifying the stop
    hass.states.async_set(NATIVE, "open", {"poked": True})  # a state event mid-settle
    await settle(hass)
    assert len(closes) == 1

    await advance_to(hass, freezer, local(2026, 9, 14, 5, 10, 40))  # settle time is up
    assert not runner.running
    assert len(closes) == 1
    assert runner.status is Status.ERROR
    assert runner.unclosed_zones == [NATIVE]
    assert runner.zone_results[0]["error"] == "still on after stop"
    assert runner.zone_results[0]["stopped_by"] is None

    device[NATIVE] = "closed"
    hass.states.async_set(NATIVE, "closed")  # a routine poll caught up meanwhile
    await advance_to(hass, freezer, local(2026, 9, 14, 5, 11, 40))  # the 1 min retry
    assert len(closes) == 1  # reads off: cleared without a command
    assert runner.unclosed_zones == []
    assert f"{NATIVE} closed on its own" in caplog.text


async def test_unclosed_zone_that_still_reads_on_gets_another_stop_at_the_retry(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, decide, make_runner
) -> None:
    native_zone(hass)
    device = {NATIVE: "open"}
    device_reads(hass, device)
    closes = async_mock_service(hass, "valve", "close_valve")

    runner = await make_runner(make_config(**NATIVE_ZONE))
    await runner.async_run_now()
    await settle(hass)
    for when in ((5, 10), (5, 10, 10), (5, 10, 20), (5, 10, 40)):
        await advance_to(hass, freezer, local(2026, 9, 14, *when))
    assert len(closes) == 1
    assert runner.unclosed_zones == [NATIVE]

    await advance_to(hass, freezer, local(2026, 9, 14, 5, 11, 40))
    assert len(closes) == 2  # still on: one more stop
    await advance_to(hass, freezer, local(2026, 9, 14, 5, 12))
    assert len(closes) == 2  # and nothing more until the next retry
    assert runner.unclosed_zones == [NATIVE]


async def test_manual_stop_on_native_zone_sends_one_verified_stop(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, decide, make_runner
) -> None:
    native_zone(hass)
    device = {NATIVE: "open"}
    reads = device_reads(hass, device)

    async def _close(call: ServiceCall) -> None:
        device[NATIVE] = "closed"

    closes = async_mock_service(hass, "valve", "close_valve")
    hass.services.async_register("valve", "close_valve", _close)

    runner = await make_runner(make_config(**NATIVE_ZONE))
    await runner.async_run_now()
    await settle(hass)
    await advance_to(hass, freezer, local(2026, 9, 14, 5, 3))
    await runner.async_stop_run()
    await settle(hass)

    assert device[NATIVE] == "closed"  # exactly one stop went out
    assert len(reads) == 1  # the verification read
    assert not runner.running
    assert runner.zone_results == [
        {"entity_id": NATIVE, "minutes": 3.0, "error": None, "stopped_by": "manager"}
    ]
    del closes


async def test_native_zone_with_unreadable_state_gets_one_unverified_stop(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    decide,
    make_runner,
    caplog: pytest.LogCaptureFixture,
) -> None:
    native_zone(hass)
    device = {NATIVE: "unknown"}
    device_reads(hass, device)
    closes = async_mock_service(hass, "valve", "close_valve")

    runner = await make_runner(make_config(**NATIVE_ZONE))
    await runner.async_run_now()
    await settle(hass)
    for when in ((5, 10), (5, 10, 10), (5, 10, 20)):
        await advance_to(hass, freezer, local(2026, 9, 14, *when))
    assert len(closes) == 1
    assert "can't be read after its run time" in caplog.text
    await advance_to(hass, freezer, local(2026, 9, 14, 5, 10, 40))

    assert len(closes) == 1
    assert not runner.running
    assert runner.status is Status.IDLE
    assert runner.unclosed_zones == []
    assert runner.zone_results[0]["error"] is None
    assert runner.zone_results[0]["stopped_by"] == "unverified"
    assert "assuming it closed" in caplog.text


async def test_native_zone_without_update_entity_polls_the_cached_state(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, decide, make_runner
) -> None:
    native_zone(hass)  # no homeassistant.update_entity registered
    closes = flaky_service(hass, "valve", "close_valve", 0, sets="closed")

    runner = await make_runner(make_config(**NATIVE_ZONE))
    await runner.async_run_now()
    await settle(hass)
    await advance_to(hass, freezer, local(2026, 9, 14, 5, 10))
    await advance_to(hass, freezer, local(2026, 9, 14, 5, 10, 5))
    assert runner.running and not closes
    hass.states.async_set(NATIVE, "closed")  # a poll of the integration caught the close
    await advance_to(hass, freezer, local(2026, 9, 14, 5, 10, 12))

    assert not runner.running
    assert not closes
    assert runner.zone_results[0]["stopped_by"] == "device"
    assert runner.zone_results[0]["minutes"] == 10.2


async def test_native_zone_without_update_entity_stops_after_the_grace(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, decide, make_runner
) -> None:
    native_zone(hass)
    closes = flaky_service(hass, "valve", "close_valve", 0, sets="closed")

    runner = await make_runner(make_config(**NATIVE_ZONE))
    await runner.async_run_now()
    await settle(hass)
    for sec in range(0, 30, 5):
        await advance_to(hass, freezer, local(2026, 9, 14, 5, 10, sec))
        assert runner.running and not closes
    await advance_to(hass, freezer, local(2026, 9, 14, 5, 10, 30))

    assert len(closes) == 1
    assert not runner.running
    assert runner.zone_results[0]["stopped_by"] == "manager"
    assert runner.zone_results[0]["minutes"] == 10.5
