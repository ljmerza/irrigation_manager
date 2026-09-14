"""Device condition tests against fake runners on loaded entries."""
from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
import voluptuous as vol
from homeassistant.components.device_automation import DeviceAutomationType
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import device_registry as dr
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_get_device_automations,
    async_mock_service,
)

from custom_components.irrigation_manager.const import DOMAIN
from custom_components.irrigation_manager.device_condition import (
    CONDITION_SCHEMA,
    CONDITION_TYPES,
    async_condition_from_config,
)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let the test hass load integrations from custom_components/."""
    return


def fake_runner(**state: Any) -> SimpleNamespace:
    defaults = {"running": False, "enabled": True, "paused": False, "rain_delay_until": None}
    # async_unload: the test hass unloads LOADED entries at teardown.
    return SimpleNamespace(**{**defaults, **state}, async_unload=AsyncMock())


def schedule(
    hass: HomeAssistant,
    runner: SimpleNamespace | None,
    state: ConfigEntryState = ConfigEntryState.LOADED,
) -> tuple[MockConfigEntry, dr.DeviceEntry]:
    entry = MockConfigEntry(domain=DOMAIN, title="Garden Bed", state=state)
    entry.add_to_hass(hass)
    entry.runtime_data = runner
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, entry.entry_id)}
    )
    return entry, device


def checker(hass: HomeAssistant, device_id: str, condition_type: str):
    config = CONDITION_SCHEMA(
        {"condition": "device", "device_id": device_id, "domain": DOMAIN, "type": condition_type}
    )
    return async_condition_from_config(hass, config)


async def test_get_conditions_lists_every_type(hass: HomeAssistant) -> None:
    _, device = schedule(hass, fake_runner())

    conditions = await async_get_device_automations(
        hass, DeviceAutomationType.CONDITION, device.id
    )

    ours = [condition for condition in conditions if condition["domain"] == DOMAIN]
    assert sorted(condition["type"] for condition in ours) == sorted(CONDITION_TYPES)


def test_condition_schema_rejects_unknown_type() -> None:
    with pytest.raises(vol.Invalid):
        CONDITION_SCHEMA(
            {"condition": "device", "device_id": "abc", "domain": DOMAIN, "type": "is_wet"}
        )


@pytest.mark.parametrize(
    ("condition_type", "state", "expected"),
    [
        ("is_running", {"running": True}, True),
        ("is_running", {"running": False}, False),
        ("is_enabled", {"enabled": True}, True),
        ("is_enabled", {"enabled": False}, False),
        ("is_paused", {"paused": True}, True),
        ("is_paused", {"paused": False}, False),
        ("rain_delay_active", {"rain_delay_until": "future"}, True),
        ("rain_delay_active", {"rain_delay_until": "past"}, False),
        ("rain_delay_active", {"rain_delay_until": None}, False),
    ],
)
async def test_condition_reads_runner_state(
    hass: HomeAssistant, condition_type: str, state: dict[str, Any], expected: bool
) -> None:
    offsets = {"future": timedelta(hours=2), "past": -timedelta(minutes=1)}
    if state.get("rain_delay_until") in offsets:
        state = {"rain_delay_until": dt_util.utcnow() + offsets[state["rain_delay_until"]]}
    _, device = schedule(hass, fake_runner(**state))

    assert checker(hass, device.id, condition_type)(hass, {}) is expected


async def test_condition_false_when_schedule_not_loaded(hass: HomeAssistant) -> None:
    _, device = schedule(hass, fake_runner(running=True), ConfigEntryState.NOT_LOADED)

    assert checker(hass, device.id, "is_running")(hass, {}) is False


async def test_condition_reads_current_runner_after_reload(hass: HomeAssistant) -> None:
    entry, device = schedule(hass, fake_runner(running=False))
    check = checker(hass, device.id, "is_running")

    entry.runtime_data = fake_runner(running=True)

    assert check(hass, {}) is True


async def test_condition_in_automation(hass: HomeAssistant) -> None:
    entry, device = schedule(hass, fake_runner(running=False))
    calls: list[ServiceCall] = async_mock_service(hass, "test", "automation")
    assert await async_setup_component(
        hass,
        "automation",
        {
            "automation": [
                {
                    "triggers": [{"trigger": "event", "event_type": "test_event"}],
                    "conditions": [
                        {
                            "condition": "device",
                            "domain": DOMAIN,
                            "device_id": device.id,
                            "type": "is_running",
                        }
                    ],
                    "actions": [{"action": "test.automation"}],
                }
            ]
        },
    )

    hass.bus.async_fire("test_event")
    await hass.async_block_till_done()
    assert calls == []

    entry.runtime_data.running = True
    hass.bus.async_fire("test_event")
    await hass.async_block_till_done()
    assert len(calls) == 1
