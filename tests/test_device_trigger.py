"""Device trigger tests: listing, and automations firing on irrigation events."""
from __future__ import annotations

from typing import Any

import pytest
import voluptuous as vol
from homeassistant.components.device_automation import DeviceAutomationType
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import device_registry as dr
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_get_device_automations,
    async_mock_service,
)

from custom_components.irrigation_manager.const import DOMAIN, EVENT_IRRIGATION, EventType
from custom_components.irrigation_manager.device_trigger import (
    TRIGGER_SCHEMA,
    async_get_triggers,
)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let the test hass load integrations from custom_components/."""
    return


def schedule_device(hass: HomeAssistant, title: str = "Garden Bed") -> dr.DeviceEntry:
    entry = MockConfigEntry(domain=DOMAIN, title=title)
    entry.add_to_hass(hass)
    return dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={(DOMAIN, entry.entry_id)}, name=title
    )


@pytest.fixture
def automation_calls(hass: HomeAssistant) -> list[ServiceCall]:
    return async_mock_service(hass, "test", "automation")


async def setup_automation(hass: HomeAssistant, device_id: str, trigger_type: str) -> None:
    assert await async_setup_component(
        hass,
        "automation",
        {
            "automation": [
                {
                    "triggers": [
                        {
                            "trigger": "device",
                            "domain": DOMAIN,
                            "device_id": device_id,
                            "type": trigger_type,
                        }
                    ],
                    "actions": [
                        {
                            "action": "test.automation",
                            "data": {
                                "type": "{{ trigger.event.data.type }}",
                                "status": "{{ trigger.event.data.status }}",
                            },
                        }
                    ],
                }
            ]
        },
    )


def fire(hass: HomeAssistant, device_id: str, event_type: str, **extra: Any) -> None:
    hass.bus.async_fire(
        EVENT_IRRIGATION,
        {"entry_id": "x", "device_id": device_id, "name": "Garden Bed", "type": event_type, **extra},
    )


async def test_get_triggers_lists_every_event_type(hass: HomeAssistant) -> None:
    device = schedule_device(hass)

    triggers = await async_get_device_automations(hass, DeviceAutomationType.TRIGGER, device.id)

    ours = [trigger for trigger in triggers if trigger["domain"] == DOMAIN]
    assert sorted(trigger["type"] for trigger in ours) == sorted(e.value for e in EventType)
    assert all(t["device_id"] == device.id and t["platform"] == "device" for t in ours)


async def test_non_schedule_device_has_no_triggers(hass: HomeAssistant) -> None:
    other_entry = MockConfigEntry(domain="test")
    other_entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=other_entry.entry_id, identifiers={("test", "abc")}
    )

    assert await async_get_triggers(hass, device.id) == []


def test_trigger_schema_rejects_unknown_type() -> None:
    with pytest.raises(vol.Invalid):
        TRIGGER_SCHEMA(
            {"platform": "device", "domain": DOMAIN, "device_id": "abc", "type": "exploded"}
        )


async def test_trigger_fires_for_matching_device_and_type(
    hass: HomeAssistant, automation_calls: list[ServiceCall]
) -> None:
    device = schedule_device(hass)
    await setup_automation(hass, device.id, EventType.SKIPPED)

    fire(hass, device.id, EventType.SKIPPED, status="skipped_rain")
    await hass.async_block_till_done()

    assert len(automation_calls) == 1
    assert automation_calls[0].data == {"type": "skipped", "status": "skipped_rain"}


async def test_trigger_ignores_other_devices(
    hass: HomeAssistant, automation_calls: list[ServiceCall]
) -> None:
    device = schedule_device(hass)
    other = schedule_device(hass, "Front Lawn")
    await setup_automation(hass, device.id, EventType.RUN_FINISHED)

    fire(hass, other.id, EventType.RUN_FINISHED, status="idle")
    await hass.async_block_till_done()

    assert automation_calls == []


async def test_trigger_ignores_other_event_types(
    hass: HomeAssistant, automation_calls: list[ServiceCall]
) -> None:
    device = schedule_device(hass)
    await setup_automation(hass, device.id, EventType.RUN_STARTED)

    fire(hass, device.id, EventType.ZONE_STARTED)
    fire(hass, device.id, EventType.RUN_FINISHED, status="idle")
    await hass.async_block_till_done()
    assert automation_calls == []

    fire(hass, device.id, EventType.RUN_STARTED)
    await hass.async_block_till_done()
    assert len(automation_calls) == 1
