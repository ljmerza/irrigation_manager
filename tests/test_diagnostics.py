"""Config entry diagnostics tests."""
from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from homeassistant.components.diagnostics import REDACTED
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from custom_components.irrigation_manager.const import (
    CONF_AI_NOTIFY_SERVICE,
    CONF_AI_TASK_ENTITY,
    CONF_ZONES,
    DOMAIN,
)
from custom_components.irrigation_manager.diagnostics import (
    async_get_config_entry_diagnostics,
)

ZONE_PLAIN = "valve.zone_a"
ZONE_BHYVE = "valve.garden_irrigation_zone"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let the test hass load integrations from custom_components/."""
    return


def make_config() -> dict[str, Any]:
    return {
        "name": "Garden Bed",
        CONF_ZONES: [
            {"entity_id": ZONE_PLAIN, "minutes": 10},
            {"entity_id": ZONE_BHYVE, "minutes": 30},
        ],
        CONF_AI_TASK_ENTITY: "ai_task.claude_ai_task",
        CONF_AI_NOTIFY_SERVICE: "notify.mobile_app_personal_phone",
    }


async def test_diagnostics_for_loaded_schedule(hass: HomeAssistant) -> None:
    config = make_config()
    entry = MockConfigEntry(
        domain=DOMAIN, title="Garden Bed", data=config, state=ConfigEntryState.LOADED
    )
    entry.add_to_hass(hass)
    entry.runtime_data = SimpleNamespace(
        snapshot=lambda: {"name": "Garden Bed", "config": dict(config)},
        history=lambda limit=None: [{"type": "run", "status": "idle", "total_minutes": 40}],
        async_unload=AsyncMock(),
    )
    # Register before setting state, or the registry picks a _2 entity id.
    er.async_get(hass).async_get_or_create(
        "valve", "orbit_bhyve", "garden_zone", suggested_object_id="garden_irrigation_zone"
    )
    hass.states.async_set(ZONE_PLAIN, "closed")
    hass.states.async_set(ZONE_BHYVE, "open")
    async_mock_service(hass, "orbit_bhyve", "start_watering")

    data = await async_get_config_entry_diagnostics(hass, entry)

    assert data["entry"]["title"] == "Garden Bed"
    assert data["entry"]["state"] == "loaded"
    assert data["entry"]["data"][CONF_AI_NOTIFY_SERVICE] == REDACTED
    assert data["entry"]["data"][CONF_AI_TASK_ENTITY] == "ai_task.claude_ai_task"
    assert data["snapshot"]["config"][CONF_AI_NOTIFY_SERVICE] == REDACTED
    assert data["history"] == [{"type": "run", "status": "idle", "total_minutes": 40}]
    assert data["zones"] == {
        ZONE_PLAIN: {"driver": "ZoneDriver", "native_duration": False, "state": "closed"},
        ZONE_BHYVE: {"driver": "OrbitBhyveDriver", "native_duration": True, "state": "open"},
    }
    json.dumps(data)


async def test_diagnostics_for_unloaded_schedule(hass: HomeAssistant) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, title="Garden Bed", data=make_config(), state=ConfigEntryState.NOT_LOADED
    )
    entry.add_to_hass(hass)

    data = await async_get_config_entry_diagnostics(hass, entry)

    assert data["snapshot"] is None
    assert data["history"] == []
    assert data["zones"][ZONE_PLAIN]["state"] is None
    assert data["entry"]["options"] == {}
