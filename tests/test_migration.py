"""Migration import tests: legacy helper parsing, B-Hyve program candidates, program disable.

Legacy states use this install's values (restore state, 2026-09-13). B-Hyve
fixtures use this install's unique ids and the attribute format orbit_bhyve's
BHyveProgramSummarySensor writes (projects/hass/orbit-bhyve-ble sensor.py).
"""
from __future__ import annotations

from datetime import date, time
from typing import Any

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_mock_service

from custom_components.irrigation_manager.migration import (
    LEGACY_ENABLED,
    LEGACY_GRASS_INTERVAL,
    LEGACY_HELPERS,
    LEGACY_LAST_RAIN,
    LEGACY_LAST_RUN,
    LEGACY_RAIN_THRESHOLD,
    LEGACY_SCHEDULE,
    async_disable_bhyve_program,
    async_read_bhyve_programs,
    async_read_legacy_helpers,
    parse_legacy_schedule,
)
from custom_components.irrigation_manager.scheduler import Schedule

LIVE_LEGACY_STATES = {
    LEGACY_SCHEDULE: "06:00 2d 30m",
    LEGACY_LAST_RUN: "2026-09-13 06:00:09",
    LEGACY_ENABLED: "off",
    LEGACY_RAIN_THRESHOLD: "0.1",
    LEGACY_GRASS_INTERVAL: "5.0",
    LEGACY_LAST_RAIN: "09/13/2026",
    "input_boolean.grass_watering_sprinkler_automation": "off",
    "input_boolean.moisture_automation": "on",
    "input_text.setup_irrigation_date": "04/01/2026 (Next: 05/01/2026)",
    "input_boolean.setup_irrigation_chore": "off",
}

DEVICE_UID = "orbit_bhyve_4467551c49fc"  # this install's Garden Irrigation timer


def build_schedule(config: dict[str, Any], **fill: Any) -> Schedule:
    """Config -> scheduler.Schedule after the caller fills missing fields (`fill`)."""
    merged = {**fill, **config}
    anchor = merged.get("anchor")
    start = merged.get("start_time")
    return Schedule(
        frequency=merged["frequency"],
        start_mode=merged.get("start_mode", "time"),
        interval_days=int(merged.get("interval_days", 1)),
        anchor=date.fromisoformat(anchor) if anchor else None,
        weekdays=frozenset(merged.get("weekdays", [])),
        start_time=time.fromisoformat(start) if start else None,
    )


def set_states(hass: HomeAssistant, states: dict[str, str]) -> None:
    for entity_id, value in states.items():
        hass.states.async_set(entity_id, value)


def summary(
    days: str,
    start_times: list[str],
    zones: list[dict[str, Any]],
    name: str | None = None,
    budget: int | None = 100,
) -> dict[str, Any]:
    """Attributes as BHyveProgramSummarySensor.extra_state_attributes writes them."""
    return {
        "empty": False,
        "name": name,
        "days": days,
        "start_times": start_times,
        "zones": zones,
        "budget": budget,
    }


@pytest.fixture
def bhyve(hass: HomeAssistant) -> dict[str, str]:
    """Garden Irrigation registry entries as orbit_bhyve creates them; all slots empty."""
    config_entry = MockConfigEntry(domain="orbit_bhyve")
    config_entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={("orbit_bhyve", "garden-cloud-id")},
        name="Garden Irrigation",
    )
    registry = er.async_get(hass)

    def create(domain: str, unique_id: str, object_id: str) -> str:
        return registry.async_get_or_create(
            domain,
            "orbit_bhyve",
            unique_id,
            suggested_object_id=object_id,
            config_entry=config_entry,
            device_id=device.id,
        ).entity_id

    ids = {"valve": create("valve", f"{DEVICE_UID}_zone", "garden_irrigation_zone")}
    for slot in "abcd":
        ids[f"sensor_{slot}"] = create(
            "sensor", f"{DEVICE_UID}_program_{slot}", f"garden_irrigation_program_{slot}"
        )
        ids[f"switch_{slot}"] = create(
            "switch", f"{DEVICE_UID}_program_{slot}_enable", f"garden_irrigation_program_{slot}"
        )
        hass.states.async_set(ids[f"sensor_{slot}"], "empty", {"empty": True})
    return ids


# --- parse_legacy_schedule --------------------------------------------------


def test_parse_real_legacy_schedule() -> None:
    assert parse_legacy_schedule("06:00 2d 30m") == {
        "config": {
            "frequency": "interval",
            "interval_days": 2,
            "start_mode": "time",
            "start_time": "06:00:00",
        },
        "zone_minutes": 30,
        "errors": [],
    }


def test_parse_accepts_any_token_order_and_extra_spaces() -> None:
    assert parse_legacy_schedule("  30m   6:05 3d ")["config"] == {
        "frequency": "interval",
        "interval_days": 3,
        "start_mode": "time",
        "start_time": "06:05:00",
    }


@pytest.mark.parametrize(
    ("text", "error"),
    [
        ("06:00 2d 30m x", "unknown token 'x'"),
        ("06:00 2w 30m", "unknown token '2w'"),
        ("06:00 2D 30m", "unknown token '2D'"),
        ("06:00 2.5d 30m", "unknown token '2.5d'"),
        ("06:00 -2d 30m", "unknown token '-2d'"),
        ("6am 2d 30m", "unknown token '6am'"),
        ("06:00 2d", "missing minutes token"),
        ("2d 30m", "missing time token"),
        ("06:00 2d 3d 30m", "duplicate days token '3d'"),
        ("25:00 2d 30m", "time out of range: '25:00'"),
        ("06:60 2d 30m", "time out of range: '06:60'"),
        ("06:00 0d 30m", "days out of range: '0d'"),
        ("06:00 32d 30m", "days out of range: '32d'"),
        ("06:00 2d 0m", "minutes out of range: '0m'"),
        ("06:00 2d 181m", "minutes out of range: '181m'"),
        ("", "schedule is empty"),
    ],
)
def test_parse_rejects_invalid(text: str, error: str) -> None:
    result = parse_legacy_schedule(text)
    assert result["config"] == {}
    assert result["zone_minutes"] is None
    assert error in result["errors"]


def test_out_of_range_token_is_not_also_reported_missing() -> None:
    assert parse_legacy_schedule("06:00 0d 30m")["errors"] == ["days out of range: '0d'"]


def test_parsed_schedule_builds_once_anchor_filled() -> None:
    config = parse_legacy_schedule("06:00 2d 30m")["config"]
    schedule = build_schedule(config, anchor="2026-09-13")
    assert schedule.interval_days == 2
    assert schedule.start_time == time(6, 0)


# --- async_read_legacy_helpers ----------------------------------------------


async def test_read_legacy_helpers_live_values(hass: HomeAssistant) -> None:
    set_states(hass, LIVE_LEGACY_STATES)

    result = async_read_legacy_helpers(hass)

    assert result["config"] == {
        "name": "Drip irrigation",
        "frequency": "interval",
        "interval_days": 2,
        "start_mode": "time",
        "start_time": "06:00:00",
        "anchor": "2026-09-13",
        "rain_threshold": 0.1,
    }
    assert result["zone_minutes"] == 30
    assert result["found"] == list(LEGACY_HELPERS)
    notes = " ".join(result["notes"])
    assert "choose the zones" in notes
    assert "last drip run on 2026-09-13" in notes
    assert "pick a rain sensor" in notes
    assert f"{LEGACY_ENABLED} is off" in notes
    assert "input_boolean.moisture_automation" in notes  # reported as not imported

    schedule = build_schedule(result["config"])
    assert schedule.anchor == date(2026, 9, 13)

    (grass,) = result["candidates"]
    assert grass["supported"] and grass["approximate"]
    assert grass["config"] == {
        "name": "Grass watering",
        "frequency": "interval",
        "interval_days": 5,
        "anchor": "2026-09-18",
    }
    assert "unverified" in grass["notes"][0]
    assert build_schedule(grass["config"], start_time="07:00:00").interval_days == 5


async def test_read_legacy_helpers_none_present(hass: HomeAssistant) -> None:
    result = async_read_legacy_helpers(hass)
    assert result["config"] == {}
    assert result["zone_minutes"] is None
    assert result["candidates"] == []
    assert result["found"] == []
    notes = " ".join(result["notes"])
    assert f"{LEGACY_SCHEDULE} not found" in notes
    assert f"{LEGACY_RAIN_THRESHOLD} not found" in notes


async def test_unparseable_schedule_still_imports_threshold(hass: HomeAssistant) -> None:
    set_states(hass, {LEGACY_SCHEDULE: "06:00 every other day", LEGACY_RAIN_THRESHOLD: "0.25"})
    result = async_read_legacy_helpers(hass)
    assert result["config"] == {"rain_threshold": 0.25}
    assert result["zone_minutes"] is None
    assert any("could not be parsed" in note for note in result["notes"])


async def test_zero_rain_threshold_not_imported(hass: HomeAssistant) -> None:
    set_states(hass, {LEGACY_RAIN_THRESHOLD: "0.0"})
    result = async_read_legacy_helpers(hass)
    assert "rain_threshold" not in result["config"]
    assert any("below the minimum" in note for note in result["notes"])


async def test_missing_last_run_leaves_anchor_to_caller(hass: HomeAssistant) -> None:
    set_states(
        hass,
        {LEGACY_SCHEDULE: "06:00 2d 30m", LEGACY_LAST_RUN: "unavailable", LEGACY_ENABLED: "on"},
    )
    result = async_read_legacy_helpers(hass)
    assert "anchor" not in result["config"]
    notes = " ".join(result["notes"])
    assert "choose the first run date" in notes
    assert f"{LEGACY_ENABLED} is on" in notes
    assert build_schedule(result["config"], anchor="2026-09-14").anchor == date(2026, 9, 14)


async def test_fractional_grass_interval_unsupported(hass: HomeAssistant) -> None:
    set_states(hass, {LEGACY_GRASS_INTERVAL: "2.5", LEGACY_LAST_RAIN: "09/13/2026"})
    (grass,) = async_read_legacy_helpers(hass)["candidates"]
    assert not grass["supported"]
    assert "frequency" not in grass["config"]
    assert any("can't be used" in note for note in grass["notes"])


# --- async_read_bhyve_programs ----------------------------------------------


async def test_weekday_program_with_two_start_times(
    hass: HomeAssistant, bhyve: dict[str, str]
) -> None:
    hass.states.async_set(
        bhyve["sensor_a"],
        "enabled",
        summary("Mon, Wed, Fri", ["06:00", "18:30"], [{"zone": 1, "minutes": 12.5}], name="Garden beds"),
    )

    candidates = async_read_bhyve_programs(hass)

    assert [c["config"]["start_time"] for c in candidates] == ["06:00:00", "18:30:00"]
    first = candidates[0]
    assert {key: first[key] for key in ("source", "slot", "device", "program_switch", "enabled", "supported")} == {
        "source": bhyve["sensor_a"],
        "slot": "A",
        "device": "Garden Irrigation",
        "program_switch": bhyve["switch_a"],
        "enabled": True,
        "supported": True,
    }
    assert first["config"] == {
        "name": "Garden beds 06:00",
        "zones": [{"entity_id": bhyve["valve"], "minutes": 13}],
        "zone_mode": "sequential",
        "frequency": "weekdays",
        "weekdays": [0, 2, 4],
        "start_mode": "time",
        "start_time": "06:00:00",
    }
    notes = " ".join(first["notes"])
    assert "12.5 min imported as 13 min" in notes
    assert "2 start times" in notes
    # Candidates don't share mutable config.
    assert first["config"]["zones"] is not candidates[1]["config"]["zones"]
    for candidate in candidates:
        assert build_schedule(candidate["config"]).weekdays == frozenset({0, 2, 4})


async def test_interval_program_disabled_with_budget(
    hass: HomeAssistant, bhyve: dict[str, str]
) -> None:
    hass.states.async_set(
        bhyve["sensor_b"],
        "disabled",
        summary("Every 3 days from 2026-09-01", ["05:15"], [{"zone": 1, "minutes": 20.0}], budget=80),
    )

    (candidate,) = async_read_bhyve_programs(hass)

    assert candidate["supported"]
    assert candidate["enabled"] is False
    assert candidate["config"] == {
        "name": "Garden Irrigation program B",
        "zones": [{"entity_id": bhyve["valve"], "minutes": 20}],
        "zone_mode": "sequential",
        "frequency": "interval",
        "interval_days": 3,
        "anchor": "2026-09-01",
        "start_mode": "time",
        "start_time": "05:15:00",
    }
    notes = " ".join(candidate["notes"])
    assert "disabled on the device" in notes
    assert "budget is 80%" in notes
    assert "min imported as" not in notes  # 20.0 is already whole
    assert build_schedule(candidate["config"]).anchor == date(2026, 9, 1)


async def test_every_day_and_unanchored_interval(hass: HomeAssistant, bhyve: dict[str, str]) -> None:
    hass.states.async_set(bhyve["sensor_a"], "enabled", summary("Every day", ["06:00"], [{"zone": 1, "minutes": 5}]))
    hass.states.async_set(bhyve["sensor_c"], "enabled", summary("Every 2 days", ["07:00"], [{"zone": 1, "minutes": 5}]))

    every_day, unanchored = async_read_bhyve_programs(hass)

    assert every_day["config"]["weekdays"] == [0, 1, 2, 3, 4, 5, 6]
    assert unanchored["supported"]
    assert "anchor" not in unanchored["config"]
    assert any("choose the first run date" in note for note in unanchored["notes"])
    assert build_schedule(unanchored["config"], anchor="2026-09-14").interval_days == 2


@pytest.mark.parametrize(
    ("days", "fragment"),
    [
        ("Odd days", "Odd-day programs"),
        ("Even days", "Even-day programs"),
        ("Once", "One-time programs"),
        ("(none)", "no weekdays selected"),
        ("None", "Unrecognised day summary"),
        ("Mon, Funday", "Unrecognised day summary"),
        ("", "no day summary"),
    ],
)
async def test_unsupported_day_modes_become_notes(
    hass: HomeAssistant, bhyve: dict[str, str], days: str, fragment: str
) -> None:
    hass.states.async_set(bhyve["sensor_a"], "enabled", summary(days, ["06:00"], [{"zone": 1, "minutes": 10}]))

    (candidate,) = async_read_bhyve_programs(hass)

    assert candidate["supported"] is False
    assert "frequency" not in candidate["config"]
    assert "start_time" not in candidate["config"]
    assert any(fragment in note for note in candidate["notes"])


async def test_unmapped_zone_and_missing_start_time(hass: HomeAssistant, bhyve: dict[str, str]) -> None:
    hass.states.async_set(bhyve["sensor_a"], "enabled", summary("Every day", [], [{"zone": 2, "minutes": 10}]))

    (candidate,) = async_read_bhyve_programs(hass)

    assert candidate["supported"] is False
    assert "zones" not in candidate["config"]
    notes = " ".join(candidate["notes"])
    assert "Zone 2 has no matching valve entity" in notes
    assert "no start time" in notes


async def test_multi_station_device_maps_each_zone(hass: HomeAssistant) -> None:
    registry = er.async_get(hass)
    uid = "orbit_bhyve_aaaaaaaaaaaa"
    valves = [
        registry.async_get_or_create("valve", "orbit_bhyve", f"{uid}_zone_{n}", suggested_object_id=f"yard_zone_{n}").entity_id
        for n in (1, 2)
    ]
    sensor = registry.async_get_or_create("sensor", "orbit_bhyve", f"{uid}_program_a", suggested_object_id="yard_program_a").entity_id
    hass.states.async_set(
        sensor,
        "enabled",
        summary("Sat", ["06:00"], [{"zone": 1, "minutes": 400}, {"zone": 2, "minutes": 7}]),
    )

    (candidate,) = async_read_bhyve_programs(hass)

    assert candidate["config"]["zones"] == [
        {"entity_id": valves[0], "minutes": 180},
        {"entity_id": valves[1], "minutes": 7},
    ]
    assert candidate["device"] is None
    notes = " ".join(candidate["notes"])
    assert "400 min imported as 180 min" in notes
    assert "sequential" in notes
    assert candidate["program_switch"] is None


async def test_unavailable_program_sensor(hass: HomeAssistant, bhyve: dict[str, str]) -> None:
    hass.states.async_set(bhyve["sensor_d"], "unavailable")

    (candidate,) = async_read_bhyve_programs(hass)

    assert candidate["slot"] == "D"
    assert candidate["supported"] is False
    assert candidate["config"] == {}
    assert "no reading yet" in candidate["notes"][0]


async def test_empty_slots_and_other_platforms_ignored(hass: HomeAssistant, bhyve: dict[str, str]) -> None:
    other = er.async_get(hass).async_get_or_create(
        "sensor", "some_other", f"{DEVICE_UID}_program_a", suggested_object_id="other_program_a"
    )
    hass.states.async_set(other.entity_id, "enabled", summary("Every day", ["06:00"], [{"zone": 1, "minutes": 5}]))

    assert async_read_bhyve_programs(hass) == []


# --- async_disable_bhyve_program --------------------------------------------


async def test_disable_program_turns_switch_off(hass: HomeAssistant, bhyve: dict[str, str]) -> None:
    calls = async_mock_service(hass, "switch", "turn_off")

    await async_disable_bhyve_program(hass, bhyve["switch_b"])

    assert len(calls) == 1
    assert calls[0].data == {"entity_id": bhyve["switch_b"]}


@pytest.mark.parametrize("target", ["sensor_a", "valve", "switch.not_registered", "rachio"])
async def test_disable_rejects_non_program_switch(
    hass: HomeAssistant, bhyve: dict[str, str], target: str
) -> None:
    if target == "rachio":
        entity_id = er.async_get(hass).async_get_or_create(
            "switch", "rachio", "zone-1", suggested_object_id="front_yard_sprinkler"
        ).entity_id
    else:
        entity_id = bhyve.get(target, target)
    calls = async_mock_service(hass, "switch", "turn_off")

    with pytest.raises(HomeAssistantError):
        await async_disable_bhyve_program(hass, entity_id)
    assert calls == []
