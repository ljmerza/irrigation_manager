"""Zone driver tests: platform selection, service calls and units, errors."""
from __future__ import annotations

from datetime import timedelta

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from custom_components.irrigation_manager.drivers import (
    ORBIT_BHYVE_MAX_SECONDS,
    OrbitBhyveDriver,
    RachioDriver,
    RachioLocalDriver,
    ZoneDriver,
    async_get_driver,
)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let the test hass load integrations from custom_components/."""
    return


def register(hass: HomeAssistant, domain: str, platform: str, object_id: str, state: str = "off") -> str:
    """Create an entity registry entry for `platform` and give it a state."""
    entry = er.async_get(hass).async_get_or_create(
        domain, platform, f"{platform}-{object_id}", suggested_object_id=object_id
    )
    hass.states.async_set(entry.entity_id, state)
    return entry.entity_id


# --- native drivers ---------------------------------------------------------


async def test_orbit_bhyve_starts_with_seconds_and_closes_valve(hass: HomeAssistant) -> None:
    entity_id = register(hass, "valve", "orbit_bhyve", "deck", "closed")
    start = async_mock_service(hass, "orbit_bhyve", "start_watering")
    close = async_mock_service(hass, "valve", "close_valve")

    driver = async_get_driver(hass, entity_id)
    assert isinstance(driver, OrbitBhyveDriver)
    assert driver.native_duration

    await driver.async_start(timedelta(minutes=10))
    assert len(start) == 1
    # Domain service: entity ids travel in data as a list.
    assert start[0].data == {"entity_id": [entity_id], "duration": 600}

    await driver.async_stop()
    assert len(close) == 1
    assert close[0].data == {"entity_id": entity_id}


@pytest.mark.parametrize(
    ("duration", "seconds"),
    [(timedelta(hours=20), ORBIT_BHYVE_MAX_SECONDS), (timedelta(milliseconds=100), 1)],
    ids=["clamped-max", "clamped-min"],
)
async def test_orbit_bhyve_clamps_seconds(hass: HomeAssistant, duration: timedelta, seconds: int) -> None:
    entity_id = register(hass, "valve", "orbit_bhyve", "hill", "closed")
    start = async_mock_service(hass, "orbit_bhyve", "start_watering")
    await async_get_driver(hass, entity_id).async_start(duration)
    assert start[0].data["duration"] == seconds


@pytest.mark.parametrize(
    ("duration", "minutes"),
    [(timedelta(minutes=10), 10), (timedelta(seconds=90), 2), (timedelta(seconds=5), 1)],
    ids=["whole", "rounds-up", "minimum"],
)
async def test_rachio_starts_with_whole_minutes(hass: HomeAssistant, duration: timedelta, minutes: int) -> None:
    entity_id = register(hass, "switch", "rachio", "front_yard_sprinkler")
    start = async_mock_service(hass, "rachio", "start_watering")
    off = async_mock_service(hass, "switch", "turn_off")

    driver = async_get_driver(hass, entity_id)
    assert isinstance(driver, RachioDriver)
    assert driver.native_duration

    await driver.async_start(duration)
    assert start[0].data == {"entity_id": entity_id, "duration": minutes}

    await driver.async_stop()
    assert off[0].data == {"entity_id": entity_id}


async def test_rachio_local_starts_with_seconds(hass: HomeAssistant) -> None:
    entity_id = register(hass, "switch", "rachio_local", "back_zone")
    start = async_mock_service(hass, "rachio_local", "turn_on")
    off = async_mock_service(hass, "switch", "turn_off")

    driver = async_get_driver(hass, entity_id)
    assert isinstance(driver, RachioLocalDriver)

    await driver.async_start(timedelta(minutes=7, seconds=30))
    assert start[0].data == {"entity_id": entity_id, "duration": 450}

    await driver.async_stop()
    assert off[0].data == {"entity_id": entity_id}


# --- selection fallbacks ------------------------------------------------------


async def test_native_platform_without_service_falls_back_to_plain(hass: HomeAssistant) -> None:
    entity_id = register(hass, "switch", "rachio", "front")
    driver = async_get_driver(hass, entity_id)
    assert type(driver) is ZoneDriver
    assert not driver.native_duration


async def test_native_platform_wrong_entity_domain_falls_back_to_plain(hass: HomeAssistant) -> None:
    # orbit_bhyve also has switch entities (flow measurement) — not zones.
    entity_id = register(hass, "switch", "orbit_bhyve", "flow_measurement")
    async_mock_service(hass, "orbit_bhyve", "start_watering")
    assert type(async_get_driver(hass, entity_id)) is ZoneDriver


async def test_unregistered_entity_uses_plain_driver(hass: HomeAssistant) -> None:
    hass.states.async_set("switch.template_pump", "off")
    assert type(async_get_driver(hass, "switch.template_pump")) is ZoneDriver


async def test_other_platform_uses_plain_driver(hass: HomeAssistant) -> None:
    entity_id = register(hass, "valve", "zwave_js", "drip", "closed")
    assert type(async_get_driver(hass, entity_id)) is ZoneDriver


# --- plain driver -------------------------------------------------------------


async def test_plain_valve_opens_and_closes(hass: HomeAssistant) -> None:
    hass.states.async_set("valve.drip", "closed")
    opened = async_mock_service(hass, "valve", "open_valve")
    closed = async_mock_service(hass, "valve", "close_valve")

    driver = async_get_driver(hass, "valve.drip")
    await driver.async_start(timedelta(minutes=5))
    await driver.async_stop()

    assert [call.data for call in opened] == [{"entity_id": "valve.drip"}]
    assert [call.data for call in closed] == [{"entity_id": "valve.drip"}]


async def test_plain_switch_turns_on_and_off(hass: HomeAssistant) -> None:
    hass.states.async_set("switch.relay", "off")
    on = async_mock_service(hass, "switch", "turn_on")
    off = async_mock_service(hass, "switch", "turn_off")

    driver = async_get_driver(hass, "switch.relay")
    await driver.async_start(timedelta(minutes=5))
    await driver.async_stop()

    assert [call.data for call in on] == [{"entity_id": "switch.relay"}]
    assert [call.data for call in off] == [{"entity_id": "switch.relay"}]


# --- errors -------------------------------------------------------------------


async def test_unavailable_entity_raises(hass: HomeAssistant) -> None:
    hass.states.async_set("switch.relay", "unavailable")
    on = async_mock_service(hass, "switch", "turn_on")
    with pytest.raises(HomeAssistantError, match="not available"):
        await ZoneDriver(hass, "switch.relay").async_start(timedelta(minutes=1))
    assert not on


async def test_missing_entity_raises(hass: HomeAssistant) -> None:
    async_mock_service(hass, "valve", "close_valve")
    with pytest.raises(HomeAssistantError, match="not available"):
        await ZoneDriver(hass, "valve.gone").async_stop()


async def test_missing_service_raises(hass: HomeAssistant) -> None:
    hass.states.async_set("valve.drip", "closed")
    with pytest.raises(HomeAssistantError, match="valve.open_valve"):
        await ZoneDriver(hass, "valve.drip").async_start(timedelta(minutes=1))


async def test_service_error_is_wrapped(hass: HomeAssistant) -> None:
    hass.states.async_set("switch.relay", "off")
    async_mock_service(hass, "switch", "turn_on", raise_exception=ValueError("relay jammed"))
    with pytest.raises(HomeAssistantError, match="relay jammed"):
        await ZoneDriver(hass, "switch.relay").async_start(timedelta(minutes=1))


# --- entity state reads -------------------------------------------------------------


@pytest.mark.parametrize(
    ("domain", "state", "expected"),
    [
        ("valve", "open", True),
        ("valve", "opening", True),
        ("valve", "closed", False),
        ("valve", "closing", False),
        ("valve", "unknown", None),
        ("valve", "unavailable", None),
        ("switch", "on", True),
        ("switch", "off", False),
        ("switch", "unavailable", None),
    ],
)
async def test_is_on_reads_the_entity_state(
    hass: HomeAssistant, domain: str, state: str, expected: bool | None
) -> None:
    hass.states.async_set(f"{domain}.zone", state)
    assert async_get_driver(hass, f"{domain}.zone").is_on() is expected


async def test_is_on_is_none_for_a_missing_entity(hass: HomeAssistant) -> None:
    assert async_get_driver(hass, "valve.missing").is_on() is None


async def test_refresh_asks_home_assistant_for_a_fresh_read(hass: HomeAssistant) -> None:
    hass.states.async_set("valve.zone", "open")
    driver = async_get_driver(hass, "valve.zone")
    assert not driver.can_refresh
    await driver.async_refresh()  # no-op without the service

    updates = async_mock_service(hass, "homeassistant", "update_entity")
    assert driver.can_refresh
    await driver.async_refresh()
    assert [call.data for call in updates] == [{"entity_id": ["valve.zone"]}]


async def test_refresh_failure_is_ignored(hass: HomeAssistant) -> None:
    hass.states.async_set("valve.zone", "open")
    async_mock_service(
        hass, "homeassistant", "update_entity", raise_exception=HomeAssistantError("busy")
    )
    await async_get_driver(hass, "valve.zone").async_refresh()  # does not raise
