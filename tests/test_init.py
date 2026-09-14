"""Integration setup tests: lifecycle, panel registration, update listener, shutdown.

Conditions are mocked (runner.async_decide) and zones are plain valve/switch
entities with mocked services. The panel and websocket modules are patched;
their own tests cover them.
"""
from __future__ import annotations

import asyncio
from collections.abc import Generator
from datetime import datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import EVENT_HOMEASSISTANT_STOP
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.irrigation_manager import _async_update_listener
from custom_components.irrigation_manager.conditions import Decision
from custom_components.irrigation_manager.const import (
    CONF_FREQUENCY,
    CONF_MOISTURE_MODE,
    CONF_MOISTURE_SENSORS,
    CONF_MOISTURE_THRESHOLD,
    CONF_MOISTURE_UNAVAILABLE,
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
    SERVICE_RUN_NOW,
    SERVICE_SKIP_NEXT,
    SERVICE_STOP,
    SIGNAL_SCHEDULES_CHANGED,
    STORAGE_KEY_FMT,
    Status,
)
from custom_components.irrigation_manager.runner import ScheduleRunner

TZ = ZoneInfo("America/New_York")
ZONE_A = "valve.zone_a"
ZONE_B = "switch.zone_b"
ZONE_C = "valve.zone_c"


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


async def setup_entry(
    hass: HomeAssistant, config: dict[str, Any] | None = None, title: str = "Front lawn"
) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, title=title, data=config or make_config())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await settle(hass)
    return entry


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
    freezer.move_to(datetime(2026, 9, 14, 5, 0, tzinfo=TZ))
    # Set up the switch component first: when this integration's switch
    # platform loads it later, it would replace the zone service mocks.
    assert await async_setup_component(hass, "switch", {})
    hass.states.async_set(ZONE_A, "closed", {"friendly_name": "Zone A"})
    hass.states.async_set(ZONE_B, "off", {"friendly_name": "Zone B"})
    hass.states.async_set(ZONE_C, "closed", {"friendly_name": "Zone C"})


@pytest.fixture(autouse=True)
def decide() -> Generator[AsyncMock]:
    mock = AsyncMock(return_value=Decision(water=True))
    with patch("custom_components.irrigation_manager.runner.async_decide", mock):
        yield mock


@pytest.fixture(autouse=True)
def shared() -> Generator[SimpleNamespace]:
    with (
        patch(
            "custom_components.irrigation_manager.panel.async_register_panel",
            new_callable=AsyncMock,
        ) as register,
        patch(
            "custom_components.irrigation_manager.panel.async_unregister_panel"
        ) as unregister,
        patch("custom_components.irrigation_manager.websocket_api.async_setup") as websocket,
    ):
        yield SimpleNamespace(register=register, unregister=unregister, websocket=websocket)


@pytest.fixture
def calls(hass: HomeAssistant, setup_env: None) -> dict[str, list[ServiceCall]]:
    return {
        "open": async_mock_service(hass, "valve", "open_valve"),
        "close": async_mock_service(hass, "valve", "close_valve"),
        "on": async_mock_service(hass, "switch", "turn_on"),
        "off": async_mock_service(hass, "switch", "turn_off"),
    }


# --- lifecycle ------------------------------------------------------------------


async def test_setup_creates_runner_entities_and_registers_panel(
    hass: HomeAssistant, shared: SimpleNamespace
) -> None:
    entry = await setup_entry(hass)

    assert entry.state is ConfigEntryState.LOADED
    assert isinstance(entry.runtime_data, ScheduleRunner)
    # Entity ids come from the translated names on the schedule's device.
    for entity_id in (
        "switch.front_lawn_enabled",
        "sensor.front_lawn_status",
        "sensor.front_lawn_next_run",
        "sensor.front_lawn_last_run",
        "sensor.front_lawn_last_run_total",
        "sensor.front_lawn_current_zone",
        "number.front_lawn_zone_a_run_time",
        "number.front_lawn_zone_b_run_time",
        "button.front_lawn_run_now",
        "button.front_lawn_skip_next_run",
        "button.front_lawn_stop",
        "button.front_lawn_clear_rain_delay",
        "sensor.front_lawn_rain_delay",
        "binary_sensor.front_lawn_problem",
    ):
        assert hass.states.get(entity_id) is not None, entity_id

    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    assert device is not None
    assert device.name == "Front lawn"
    assert device.entry_type is dr.DeviceEntryType.SERVICE

    shared.register.assert_awaited_once_with(hass)
    shared.websocket.assert_called_once_with(hass)
    for service in (SERVICE_RUN_NOW, SERVICE_SKIP_NEXT, SERVICE_STOP):
        assert hass.services.has_service(DOMAIN, service)


async def test_panel_unregistered_only_after_last_schedule_unloads(
    hass: HomeAssistant, shared: SimpleNamespace
) -> None:
    first = await setup_entry(hass)
    second = await setup_entry(hass, make_config(**{CONF_NAME: "Back yard"}), "Back yard")
    assert shared.register.await_count == 2

    assert await hass.config_entries.async_unload(first.entry_id)
    await settle(hass)
    shared.unregister.assert_not_called()

    assert await hass.config_entries.async_unload(second.entry_id)
    await settle(hass)
    shared.unregister.assert_called_once_with(hass)
    # Domain-level setup ran once for both schedules.
    shared.websocket.assert_called_once_with(hass)


async def test_unload_stops_active_run(
    hass: HomeAssistant, calls: dict[str, list[ServiceCall]]
) -> None:
    entry = await setup_entry(hass)
    runner = entry.runtime_data
    await runner.async_run_now()
    await settle(hass)
    assert [call.data["entity_id"] for call in calls["open"]] == [ZONE_A]

    assert await hass.config_entries.async_unload(entry.entry_id)
    await settle(hass)

    assert entry.state is ConfigEntryState.NOT_LOADED
    assert [call.data["entity_id"] for call in calls["close"]] == [ZONE_A]
    assert not calls["on"]
    assert not runner.running
    assert runner.status is Status.INTERRUPTED


async def test_shutdown_closes_active_zones(
    hass: HomeAssistant,
    calls: dict[str, list[ServiceCall]],
    hass_storage: dict[str, Any],
) -> None:
    entry = await setup_entry(hass)
    runner = entry.runtime_data
    await runner.async_run_now()
    await settle(hass)
    assert runner.running

    @callback
    def _zone_integrations_stop(_event: Any) -> None:
        # Zone integrations tear down on EVENT_HOMEASSISTANT_STOP; closing a
        # zone after that point fails.
        hass.services.async_remove("valve", "close_valve")
        hass.services.async_remove("switch", "turn_off")

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, _zone_integrations_stop)

    # Real shutdown order: shutdown jobs, then background tasks (the run) are
    # cancelled, then EVENT_HOMEASSISTANT_STOP.
    await hass.async_stop(force=True)

    assert [call.data["entity_id"] for call in calls["close"]] == [ZONE_A]
    assert not calls["on"]  # zone B never started
    assert not runner.running
    assert runner.status is Status.INTERRUPTED
    stored = hass_storage[STORAGE_KEY_FMT.format(entry_id=entry.entry_id)]["data"]
    assert stored["status"] == Status.INTERRUPTED.value
    assert stored["active_run"] is None


async def test_unload_closes_zones_after_run_task_cancelled(
    hass: HomeAssistant,
    calls: dict[str, list[ServiceCall]],
    hass_storage: dict[str, Any],
) -> None:
    entry = await setup_entry(hass)
    runner = entry.runtime_data
    await runner.async_run_now()
    await settle(hass)
    task = runner._run_task
    assert task is not None

    task.cancel()
    await settle(hass)
    assert task.cancelled()
    assert runner.running  # the cancelled task skipped closing its zone
    assert not calls["close"]

    await runner.async_unload()
    await settle(hass)

    assert [call.data["entity_id"] for call in calls["close"]] == [ZONE_A]
    assert not calls["on"]
    assert not runner.running
    assert runner.status is Status.INTERRUPTED
    assert runner.next_occurrence is None
    assert [result["entity_id"] for result in runner.zone_results] == [ZONE_A]
    stored = hass_storage[STORAGE_KEY_FMT.format(entry_id=entry.entry_id)]["data"]
    assert stored["status"] == Status.INTERRUPTED.value
    assert stored["active_run"] is None


async def test_schedules_changed_signal_sent_after_state_changes(
    hass: HomeAssistant,
) -> None:
    entry = MockConfigEntry(domain=DOMAIN, title="Front lawn", data=make_config())
    entry.add_to_hass(hass)
    seen: list[ConfigEntryState] = []

    @callback
    def _changed() -> None:
        seen.append(entry.state)

    unsub = async_dispatcher_connect(hass, SIGNAL_SCHEDULES_CHANGED, _changed)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await settle(hass)
    assert seen[-1] is ConfigEntryState.LOADED

    assert await hass.config_entries.async_unload(entry.entry_id)
    await settle(hass)
    assert seen[-1] is ConfigEntryState.NOT_LOADED
    unsub()


# --- update listener ------------------------------------------------------------


async def test_minutes_change_applies_without_reload(hass: HomeAssistant) -> None:
    entry = await setup_entry(hass)
    runner = entry.runtime_data
    config = make_config(
        **{
            CONF_ZONES: [
                {CONF_ZONE_ENTITY: ZONE_A, CONF_ZONE_MINUTES: 20},
                {CONF_ZONE_ENTITY: ZONE_B, CONF_ZONE_MINUTES: 5},
            ]
        }
    )

    hass.config_entries.async_update_entry(entry, options=config)
    await settle(hass)

    assert entry.runtime_data is runner
    assert runner.config == config
    assert float(hass.states.get("number.front_lawn_zone_a_run_time").state) == 20


async def test_condition_change_applies_without_reload(hass: HomeAssistant) -> None:
    entry = await setup_entry(hass)
    runner = entry.runtime_data
    config = make_config(
        **{
            CONF_SKIP_CONDITIONS: ["moisture"],
            CONF_MOISTURE_SENSORS: ["sensor.bed_moisture"],
            CONF_MOISTURE_THRESHOLD: 30.0,
            CONF_MOISTURE_MODE: "skip",
            CONF_MOISTURE_UNAVAILABLE: "water",
        }
    )

    hass.config_entries.async_update_entry(entry, options=config)
    await settle(hass)

    assert entry.runtime_data is runner
    assert runner.config == config


async def test_zone_set_change_reloads_and_replaces_numbers(hass: HomeAssistant) -> None:
    entry = await setup_entry(hass)
    runner = entry.runtime_data
    registry = er.async_get(hass)
    zone_b_number = registry.async_get_entity_id(
        "number", DOMAIN, f"{entry.entry_id}_{ZONE_B}_minutes"
    )
    assert zone_b_number is not None

    hass.config_entries.async_update_entry(
        entry,
        options=make_config(
            **{
                CONF_ZONES: [
                    {CONF_ZONE_ENTITY: ZONE_A, CONF_ZONE_MINUTES: 10},
                    {CONF_ZONE_ENTITY: ZONE_C, CONF_ZONE_MINUTES: 7},
                ]
            }
        ),
    )
    await settle(hass)

    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data is not runner
    assert registry.async_get(zone_b_number) is None
    assert hass.states.get(zone_b_number) is None
    zone_c_number = registry.async_get_entity_id(
        "number", DOMAIN, f"{entry.entry_id}_{ZONE_C}_minutes"
    )
    assert zone_c_number is not None
    assert float(hass.states.get(zone_c_number).state) == 7


async def test_rename_updates_device_and_repeat_fires_are_harmless(
    hass: HomeAssistant, shared: SimpleNamespace
) -> None:
    entry = await setup_entry(hass)
    runner = entry.runtime_data
    renamed = make_config(**{CONF_NAME: "Back lawn"})

    # The options flow updates the title first, then the options.
    hass.config_entries.async_update_entry(entry, title="Back lawn")
    await settle(hass)
    hass.config_entries.async_update_entry(entry, options=renamed)
    await settle(hass)

    device = dr.async_get(hass).async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    assert device is not None
    assert device.name == "Back lawn"
    assert entry.runtime_data is runner
    assert runner.config == renamed
    assert runner.snapshot()["name"] == "Back lawn"

    await _async_update_listener(hass, entry)
    await _async_update_listener(hass, entry)
    await settle(hass)
    assert entry.runtime_data is runner
    assert entry.state is ConfigEntryState.LOADED
    shared.register.assert_awaited_once_with(hass)


async def test_v02_settings_change_applies_without_reload(hass: HomeAssistant) -> None:
    entry = await setup_entry(hass)
    runner = entry.runtime_data
    config = make_config(
        **{
            CONF_SKIP_CONDITIONS: ["rain", "occupancy"],
            "rain_sensors": ["sensor.rain_a", "sensor.rain_b"],
            "rain_threshold": 0.2,
            "rain_hours": 24,
            "rain_aggregate": "quorum",
            "rain_quorum": 2,
            "rain_window": "hours",
            "rain_delay_auto_hours": 24,
            "rain_delay_mirror": True,
            "occupancy_entities": ["binary_sensor.yard_person"],
            "occupancy_action": "delay",
            "occupancy_max_delay_minutes": 30,
            "ai_task_entity": "ai_task.claude_ai_task",
            "ai_report_weekday": 0,
            "ai_report_time": "07:00:00",
        }
    )

    hass.config_entries.async_update_entry(entry, options=config)
    await settle(hass)

    assert entry.runtime_data is runner
    assert runner.config == config


# --- weekly AI report -------------------------------------------------------------


async def test_weekly_report_timer_follows_entry_lifecycle(hass: HomeAssistant) -> None:
    cancel = MagicMock()
    with patch(
        "custom_components.irrigation_manager.ai.async_setup_weekly_report",
        return_value=cancel,
    ) as setup_report:
        entry = await setup_entry(hass)

        setup_report.assert_called_once_with(hass, entry.runtime_data)
        cancel.assert_not_called()

        assert await hass.config_entries.async_unload(entry.entry_id)
        await settle(hass)

    cancel.assert_called_once_with()
