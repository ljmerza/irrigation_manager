"""Assist intent tests against fake runners on loaded entries."""
from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.homeassistant.exposed_entities import async_expose_entity
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import intent
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.irrigation_manager.const import CONF_ZONES, DOMAIN, Status
from custom_components.irrigation_manager.intent import (
    INTENT_RUN_NOW,
    INTENT_SKIP_NEXT,
    INTENT_STATUS,
    INTENT_STOP,
    async_setup_intents,
)
from custom_components.irrigation_manager.scheduler import Occurrence

TZ = ZoneInfo("America/New_York")


def local(y: int, mo: int, d: int, h: int = 0, mi: int = 0) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=TZ)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let the test hass load integrations from custom_components/."""
    return


@pytest.fixture(autouse=True)
async def setup(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    """Monday 2026-09-14 12:00 New York, intents registered."""
    await hass.config.async_set_time_zone("America/New_York")
    freezer.move_to(local(2026, 9, 14, 12, 0))
    await async_setup_intents(hass)


def add_schedule(hass: HomeAssistant, title: str, **state: Any) -> MagicMock:
    runner = MagicMock()
    runner.entry = SimpleNamespace(title=title)
    runner.config = {CONF_ZONES: [{"entity_id": "valve.zone_a", "minutes": 10}]}
    defaults: dict[str, Any] = {
        "running": False,
        "status": Status.IDLE,
        "enabled": True,
        "paused": False,
        "rain_delay_until": None,
        "next_occurrence": None,
        "current_zone": None,
        "current_zone_ends_at": None,
    }
    for key, value in {**defaults, **state}.items():
        setattr(runner, key, value)
    runner.async_run_now = AsyncMock()
    runner.async_set_skip_next = AsyncMock()
    runner.async_stop_run = AsyncMock()
    runner.async_unload = AsyncMock()  # the test hass unloads LOADED entries at teardown
    entry = MockConfigEntry(domain=DOMAIN, title=title, state=ConfigEntryState.LOADED)
    entry.add_to_hass(hass)
    entry.runtime_data = runner
    return runner


async def handle(hass: HomeAssistant, intent_type: str, **slots: Any) -> str:
    response = await intent.async_handle(
        hass, "test", intent_type, {key: {"value": value} for key, value in slots.items()}
    )
    return response.speech["plain"]["speech"]


async def test_run_now_with_minutes(hass: HomeAssistant) -> None:
    runner = add_schedule(hass, "Garden Bed")

    speech = await handle(hass, INTENT_RUN_NOW, name="garden bed", minutes=10)

    runner.async_run_now.assert_awaited_once_with(10)
    assert speech == "Watering Garden Bed for 10 minutes per zone."


async def test_run_now_without_minutes(hass: HomeAssistant) -> None:
    runner = add_schedule(hass, "Garden Bed")

    speech = await handle(hass, INTENT_RUN_NOW, name="Garden Bed")

    runner.async_run_now.assert_awaited_once_with(None)
    assert speech == "Started watering Garden Bed."


async def test_run_now_when_already_running(hass: HomeAssistant) -> None:
    runner = add_schedule(hass, "Garden Bed", running=True)

    speech = await handle(hass, INTENT_RUN_NOW, name="Garden Bed")

    runner.async_run_now.assert_not_awaited()
    assert speech == "Garden Bed is already watering."


async def test_run_now_minutes_out_of_range(hass: HomeAssistant) -> None:
    runner = add_schedule(hass, "Garden Bed")

    with pytest.raises(intent.InvalidSlotInfo):
        await handle(hass, INTENT_RUN_NOW, name="Garden Bed", minutes=500)
    runner.async_run_now.assert_not_awaited()


async def test_partial_name_matches_single_schedule(hass: HomeAssistant) -> None:
    garden = add_schedule(hass, "Garden Bed")
    lawn = add_schedule(hass, "Front Lawn")

    await handle(hass, INTENT_STOP, name="lawn", )
    await handle(hass, INTENT_RUN_NOW, name="the garden bed schedule")

    lawn.async_stop_run.assert_not_awaited()  # not running
    garden.async_run_now.assert_awaited_once()


async def test_ambiguous_name_raises(hass: HomeAssistant) -> None:
    add_schedule(hass, "Garden Bed")
    add_schedule(hass, "Flower Bed")

    with pytest.raises(intent.IntentHandleError, match="Flower Bed, Garden Bed"):
        await handle(hass, INTENT_STATUS, name="bed")


async def test_unknown_name_raises(hass: HomeAssistant) -> None:
    add_schedule(hass, "Garden Bed")

    with pytest.raises(intent.IntentHandleError, match="No irrigation schedule named porch"):
        await handle(hass, INTENT_STATUS, name="porch")


async def test_unloaded_schedule_is_not_matched(hass: HomeAssistant) -> None:
    runner = add_schedule(hass, "Garden Bed")
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    entry.mock_state(hass, ConfigEntryState.NOT_LOADED)

    with pytest.raises(intent.IntentHandleError):
        await handle(hass, INTENT_RUN_NOW, name="Garden Bed")
    runner.async_run_now.assert_not_awaited()


async def test_skip_next_names_the_run(hass: HomeAssistant) -> None:
    runner = add_schedule(
        hass, "Garden Bed", next_occurrence=Occurrence(local(2026, 9, 15, 6, 0), True)
    )

    speech = await handle(hass, INTENT_SKIP_NEXT, name="Garden Bed")

    runner.async_set_skip_next.assert_awaited_once_with(True)
    assert speech == "Garden Bed will skip its run tomorrow at 06:00."


async def test_skip_next_without_upcoming_run(hass: HomeAssistant) -> None:
    add_schedule(hass, "Garden Bed")

    assert await handle(hass, INTENT_SKIP_NEXT, name="Garden Bed") == "Garden Bed will skip its next run."


async def test_stop_running_schedule(hass: HomeAssistant) -> None:
    runner = add_schedule(hass, "Garden Bed", running=True)

    speech = await handle(hass, INTENT_STOP, name="Garden Bed")

    runner.async_stop_run.assert_awaited_once_with()
    assert speech == "Stopped watering Garden Bed."


async def test_stop_idle_schedule(hass: HomeAssistant) -> None:
    runner = add_schedule(hass, "Garden Bed")

    assert await handle(hass, INTENT_STOP, name="Garden Bed") == "Garden Bed is not watering."
    runner.async_stop_run.assert_not_awaited()


async def test_status_while_running(hass: HomeAssistant) -> None:
    hass.states.async_set("valve.zone_a", "open", {"friendly_name": "Zone A"})
    add_schedule(
        hass,
        "Garden Bed",
        running=True,
        status=Status.RUNNING,
        current_zone="valve.zone_a",
        current_zone_ends_at=local(2026, 9, 14, 12, 10),
    )

    assert await handle(hass, INTENT_STATUS, name="Garden Bed") == (
        "Garden Bed is watering Zone A until 12:10."
    )


async def test_status_idle_with_next_run(hass: HomeAssistant) -> None:
    add_schedule(hass, "Garden Bed", next_occurrence=Occurrence(local(2026, 9, 14, 18, 0), True))

    assert await handle(hass, INTENT_STATUS, name="Garden Bed") == (
        "Garden Bed is idle. Next run today at 18:00."
    )


async def test_status_after_rain_skip_with_rain_delay(hass: HomeAssistant) -> None:
    add_schedule(
        hass,
        "Garden Bed",
        status=Status.SKIPPED_RAIN,
        rain_delay_until=local(2026, 9, 16, 12, 0),
        next_occurrence=Occurrence(local(2026, 9, 25, 6, 0), True),
    )

    assert await handle(hass, INTENT_STATUS, name="Garden Bed") == (
        "Garden Bed is idle; its last run was skipped (rain). "
        "Rain delay until Wednesday at 12:00. Next run on 25 September at 06:00."
    )


async def test_status_ignores_expired_rain_delay(hass: HomeAssistant) -> None:
    add_schedule(
        hass, "Garden Bed", status=Status.STOPPED_RAIN, rain_delay_until=local(2026, 9, 14, 11, 0)
    )

    assert await handle(hass, INTENT_STATUS, name="Garden Bed") == (
        "Garden Bed is idle; its last run was stopped (rain)."
    )


async def test_setup_registers_once(hass: HomeAssistant) -> None:
    registered = {handler.intent_type for handler in intent.async_get(hass)}
    assert {INTENT_RUN_NOW, INTENT_SKIP_NEXT, INTENT_STOP, INTENT_STATUS} <= registered

    with patch("homeassistant.helpers.intent.async_register") as register:
        await async_setup_intents(hass)
    register.assert_not_called()


async def test_handlers_are_limited_to_valve_and_switch_platforms(hass: HomeAssistant) -> None:
    """helpers/llm.py only offers a handler with `platforms` to an agent that has one
    of those domains exposed; descriptions become the tool text."""
    ours = [
        handler
        for handler in intent.async_get(hass)
        if handler.intent_type in {INTENT_RUN_NOW, INTENT_SKIP_NEXT, INTENT_STOP, INTENT_STATUS}
    ]
    assert len(ours) == 4
    assert all(handler.platforms == {"valve", "switch"} for handler in ours)
    assert all(handler.description for handler in ours)
    # The LLM API's filter: offered only when a valve or switch is exposed.
    assert all(not (handler.platforms & {"light", "sensor"}) for handler in ours)
    assert all(handler.platforms & {"light", "valve"} for handler in ours)


async def test_run_now_refuses_when_no_zone_is_exposed_to_the_assistant(
    hass: HomeAssistant,
) -> None:
    assert await async_setup_component(hass, "homeassistant", {})
    runner = add_schedule(hass, "Garden Bed")  # zone valve.zone_a
    slots = {"name": {"value": "Garden Bed"}}
    async_expose_entity(hass, "conversation", "valve.zone_a", False)

    with pytest.raises(intent.IntentHandleError, match="exposed to conversation"):
        await intent.async_handle(
            hass, "conversation", INTENT_RUN_NOW, slots, assistant="conversation"
        )
    runner.async_run_now.assert_not_awaited()

    async_expose_entity(hass, "conversation", "valve.zone_a", True)
    await intent.async_handle(hass, "conversation", INTENT_RUN_NOW, slots, assistant="conversation")
    runner.async_run_now.assert_awaited_once_with(None)


async def test_exposure_check_applies_only_to_run_now(hass: HomeAssistant) -> None:
    assert await async_setup_component(hass, "homeassistant", {})
    runner = add_schedule(hass, "Garden Bed", running=True)
    async_expose_entity(hass, "conversation", "valve.zone_a", False)

    response = await intent.async_handle(
        hass, "conversation", INTENT_STOP, {"name": {"value": "Garden Bed"}},
        assistant="conversation",
    )

    runner.async_stop_run.assert_awaited_once_with()
    assert response.speech["plain"]["speech"] == "Stopped watering Garden Bed."
