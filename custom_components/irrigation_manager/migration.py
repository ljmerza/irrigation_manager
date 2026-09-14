"""Import an existing watering setup into Irrigation Manager.

Two sources, both read from Home Assistant state:

- the legacy input_* helpers that drove the old drip and grass automations, and
- B-Hyve on-device programs (orbit_bhyve "Program A–D" summary sensors).

Readers return partial schedule configs using const.py keys, plus notes for the
config flow to show. They never create config entries. The flow fills in what
the sources can't tell (zones for the helpers, a first run date, a rain sensor)
and the user confirms. async_disable_bhyve_program is the only function that
changes anything; the flow calls it after explicit confirmation.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, time, timedelta
import math
import re
from typing import Any

from homeassistant.const import (
    ATTR_ENTITY_ID,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant, State, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import dt as dt_util

from .const import (
    CONF_ANCHOR,
    CONF_FREQUENCY,
    CONF_INTERVAL_DAYS,
    CONF_NAME,
    CONF_RAIN_THRESHOLD,
    CONF_START_MODE,
    CONF_START_TIME,
    CONF_WEEKDAYS,
    CONF_ZONE_ENTITY,
    CONF_ZONE_MINUTES,
    CONF_ZONE_MODE,
    CONF_ZONES,
    MAX_INTERVAL_DAYS,
    MAX_ZONE_MINUTES,
    MIN_INTERVAL_DAYS,
    MIN_ZONE_MINUTES,
)
from .scheduler import Frequency, StartMode, ZoneMode

# Legacy helpers. Ids and values were checked in this install's registry and
# restore state on 2026-09-13. The drip helpers aren't in the entity registry
# (YAML helpers), so they're only reachable through hass.states.
LEGACY_SCHEDULE = "input_text.drip_irrigation_schedule"  # e.g. "06:00 2d 30m"
LEGACY_LAST_RUN = "input_datetime.drip_irrigation_last_run"
LEGACY_ENABLED = "input_boolean.drip_irrigation"
LEGACY_RAIN_THRESHOLD = "input_number.rain_threshold"
LEGACY_GRASS_INTERVAL = "input_number.last_rain_interval"  # "Grass Watering Interval", days
LEGACY_LAST_RAIN = "input_text.last_rain"  # "MM/DD/YYYY"
LEGACY_HELPERS = (
    LEGACY_SCHEDULE,
    LEGACY_LAST_RUN,
    LEGACY_ENABLED,
    LEGACY_RAIN_THRESHOLD,
    LEGACY_GRASS_INTERVAL,
    LEGACY_LAST_RAIN,
)
# Related helpers with no schedule equivalent; reported, not imported.
LEGACY_NOT_IMPORTED = (
    "input_boolean.grass_watering_sprinkler_automation",
    "input_boolean.moisture_automation",
    "input_text.setup_irrigation_date",
    "input_boolean.setup_irrigation_chore",
)

LEGACY_SCHEDULE_NAME = "Drip irrigation"
LEGACY_GRASS_NAME = "Grass watering"

# config_flow.py rejects rain thresholds below this (0 would skip every run);
# kept in step so an import never pre-fills a value the flow refuses.
MIN_RAIN_THRESHOLD = 0.01

BHYVE_PLATFORM = "orbit_bhyve"
_PROGRAM_SENSOR_UID = re.compile(r"(?P<device>.+)_program_(?P<slot>[a-d])")
_PROGRAM_SWITCH_UID = re.compile(r".+_program_[a-d]_enable")
# orbit_bhyve's sensor._fmt_days names weekdays Sun..Sat; the scheduler uses 0=Mon.
_BHYVE_WEEKDAYS = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}
_BHYVE_EVERY_N_DAYS = re.compile(r"Every ([0-9]+) days(?: from ([0-9]{4}-[0-9]{2}-[0-9]{2}))?")
_BHYVE_UNSUPPORTED_DAYS = {
    "Odd days": "Odd-day programs have no equivalent here (every 2 days drifts after 31-day months); not imported.",
    "Even days": "Even-day programs have no equivalent here (every 2 days drifts after 31-day months); not imported.",
    "Once": "One-time programs aren't imported.",
    "(none)": "The program has no weekdays selected; not imported.",
}

_TIME_TOKEN = re.compile(r"([0-9]{1,2}):([0-9]{2})")
_DAYS_TOKEN = re.compile(r"([0-9]+)d")
_MINUTES_TOKEN = re.compile(r"([0-9]+)m")


# --- Legacy helpers ---------------------------------------------------------


def parse_legacy_schedule(text: str) -> dict[str, Any]:
    """Parse a legacy schedule string like "06:00 2d 30m".

    Tokens are a start time "HH:MM", an interval "<N>d" and a run time "<N>m",
    each exactly once, in any order. Unknown tokens, duplicates, missing tokens
    and out-of-range values are errors.

    Returns {"config", "zone_minutes", "errors"}. config (frequency, interval,
    start time) and zone_minutes are only filled when there are no errors; the
    caller adds the zones and a first run date.
    """
    tokens = (text or "").split()
    if not tokens:
        return {"config": {}, "zone_minutes": None, "errors": ["schedule is empty"]}

    errors: list[str] = []
    values: dict[str, Any] = {}
    for token in tokens:
        if match := _TIME_TOKEN.fullmatch(token):
            kind = "time"
            hour, minute = int(match[1]), int(match[2])
            value: Any = time(hour, minute) if hour <= 23 and minute <= 59 else None
        elif match := _DAYS_TOKEN.fullmatch(token):
            kind = "days"
            number = int(match[1])
            value = number if MIN_INTERVAL_DAYS <= number <= MAX_INTERVAL_DAYS else None
        elif match := _MINUTES_TOKEN.fullmatch(token):
            kind = "minutes"
            number = int(match[1])
            value = number if MIN_ZONE_MINUTES <= number <= MAX_ZONE_MINUTES else None
        else:
            errors.append(f"unknown token {token!r}")
            continue

        if kind in values:
            errors.append(f"duplicate {kind} token {token!r}")
        elif value is None:
            errors.append(f"{kind} out of range: {token!r}")
            values[kind] = None  # seen, so it isn't also reported missing
        else:
            values[kind] = value

    errors.extend(
        f"missing {kind} token" for kind in ("time", "days", "minutes") if kind not in values
    )
    if errors:
        return {"config": {}, "zone_minutes": None, "errors": errors}
    return {
        "config": {
            CONF_FREQUENCY: Frequency.INTERVAL.value,
            CONF_INTERVAL_DAYS: values["days"],
            CONF_START_MODE: StartMode.TIME.value,
            CONF_START_TIME: values["time"].strftime("%H:%M:%S"),
        },
        "zone_minutes": values["minutes"],
        "errors": [],
    }


@callback
def async_read_legacy_helpers(hass: HomeAssistant) -> dict[str, Any]:
    """Partial config from the legacy drip and grass helpers.

    Returns:
      config: the drip schedule (name, frequency, interval, first run date,
        start time) and the rain threshold, as far as the helpers allow.
      zone_minutes: run time per zone from the schedule string, or None.
      candidates: other schedules to offer, each {"config", "notes",
        "supported", "approximate"} — currently the grass watering interval.
      notes: what was imported, what wasn't, and what still has to be chosen.
      found: helper entity ids that have a usable state.
    """
    notes: list[str] = []
    config: dict[str, Any] = {}
    zone_minutes: int | None = None
    found = [entity_id for entity_id in LEGACY_HELPERS if _usable(hass.states.get(entity_id))]

    schedule = hass.states.get(LEGACY_SCHEDULE)
    if not _usable(schedule):
        notes.append(f"{LEGACY_SCHEDULE} not found; there is no drip schedule to import.")
    else:
        assert schedule is not None
        parsed = parse_legacy_schedule(schedule.state)
        if parsed["errors"]:
            notes.append(
                f"{LEGACY_SCHEDULE} ({schedule.state!r}) could not be parsed: "
                f"{'; '.join(parsed['errors'])}."
            )
        else:
            config = {CONF_NAME: LEGACY_SCHEDULE_NAME, **parsed["config"]}
            zone_minutes = parsed["zone_minutes"]
            notes.append(
                "The helpers don't record which valves the drip schedule controlled; choose the zones."
            )
            last_run = _state_date(hass.states.get(LEGACY_LAST_RUN))
            if last_run is None:
                notes.append("No last drip run date was found; choose the first run date.")
            else:
                config[CONF_ANCHOR] = last_run.isoformat()
                notes.append(
                    f"The every-{config[CONF_INTERVAL_DAYS]}-days cadence continues from the "
                    f"last drip run on {last_run.isoformat()}."
                )

    threshold = _state_float(hass.states.get(LEGACY_RAIN_THRESHOLD))
    if threshold is None:
        notes.append(f"{LEGACY_RAIN_THRESHOLD} not found; no rain threshold imported.")
    elif threshold < MIN_RAIN_THRESHOLD:
        notes.append(
            f"{LEGACY_RAIN_THRESHOLD} is {threshold:g}, below the minimum {MIN_RAIN_THRESHOLD:g}; "
            "not imported."
        )
    else:
        config[CONF_RAIN_THRESHOLD] = threshold
        notes.append(
            f"Rain threshold {threshold:g} imported; pick a rain sensor to turn on the rain condition."
        )

    enabled = hass.states.get(LEGACY_ENABLED)
    if _usable(enabled):
        assert enabled is not None
        if enabled.state == STATE_ON:
            notes.append(
                f"{LEGACY_ENABLED} is on. Turn it off, and the flows that use it, once the new "
                "schedule exists, or both will water."
            )
        else:
            notes.append(f"{LEGACY_ENABLED} is {enabled.state}; the legacy drip automation looks off.")

    candidates: list[dict[str, Any]] = []
    interval = _state_float(hass.states.get(LEGACY_GRASS_INTERVAL))
    if interval is not None:
        candidates.append(
            _grass_candidate(interval, _state_date(hass.states.get(LEGACY_LAST_RAIN)))
        )

    present = [entity_id for entity_id in LEGACY_NOT_IMPORTED if hass.states.get(entity_id)]
    if present:
        notes.append(f"Not imported (no schedule equivalent): {', '.join(present)}.")

    return {
        "config": config,
        "zone_minutes": zone_minutes,
        "candidates": candidates,
        "notes": notes,
        "found": found,
    }


def _grass_candidate(interval: float, last_rain: date | None) -> dict[str, Any]:
    """Every-N-days schedule approximating the legacy grass watering interval."""
    notes = [
        f"{LEGACY_GRASS_INTERVAL} (Grass Watering Interval) is {interval:g} days. The old "
        "automation appears to water that many days after the last rain (unverified: its "
        "Node-RED flow wasn't inspected). A fixed every-N-days schedule only approximates "
        "that: it keeps its cadence when it rains.",
        "Choose the zones, the start time and a rain sensor.",
    ]
    days = int(interval)
    if interval != days or not MIN_INTERVAL_DAYS <= days <= MAX_INTERVAL_DAYS:
        notes.append(
            f"An interval of {interval:g} days can't be used "
            f"(whole days {MIN_INTERVAL_DAYS}–{MAX_INTERVAL_DAYS}); not imported."
        )
        return {
            "config": {CONF_NAME: LEGACY_GRASS_NAME},
            "notes": notes,
            "supported": False,
            "approximate": True,
        }

    config: dict[str, Any] = {
        CONF_NAME: LEGACY_GRASS_NAME,
        CONF_FREQUENCY: Frequency.INTERVAL.value,
        CONF_INTERVAL_DAYS: days,
    }
    if last_rain is None:
        notes.append("No last rain date was found; choose the first run date.")
    else:
        first = last_rain + timedelta(days=days)
        config[CONF_ANCHOR] = first.isoformat()
        notes.append(
            f"First run date set to {days} days after the last recorded rain "
            f"({last_rain.isoformat()})."
        )
    return {"config": config, "notes": notes, "supported": True, "approximate": True}


# --- B-Hyve programs --------------------------------------------------------


@callback
def async_read_bhyve_programs(hass: HomeAssistant) -> list[dict[str, Any]]:
    """Candidate schedules from B-Hyve on-device programs.

    One candidate per program start time, since a schedule has a single start
    time. Each is {"source", "slot", "device", "program_switch", "enabled",
    "supported", "config", "notes"}. Programs this integration can't express
    (odd/even days, once, no start time, no mappable zone) come back with
    supported=False and a note instead of a wrong schedule. Empty slots are
    left out.
    """
    registry = er.async_get(hass)
    devices = dr.async_get(hass)
    candidates: list[dict[str, Any]] = []
    for entry in sorted(registry.entities.values(), key=lambda item: item.entity_id):
        if entry.platform != BHYVE_PLATFORM or entry.domain != "sensor":
            continue
        if (match := _PROGRAM_SENSOR_UID.fullmatch(entry.unique_id)) is None:
            continue
        candidates.extend(
            _program_candidates(
                hass, registry, devices, entry, match["device"], match["slot"].upper()
            )
        )
    return candidates


def _program_candidates(
    hass: HomeAssistant,
    registry: er.EntityRegistry,
    devices: dr.DeviceRegistry,
    entry: er.RegistryEntry,
    device_uid: str,
    slot: str,
) -> list[dict[str, Any]]:
    device = devices.async_get(entry.device_id) if entry.device_id else None
    device_name = (device.name_by_user or device.name) if device else None
    base: dict[str, Any] = {
        "source": entry.entity_id,
        "slot": slot,
        "device": device_name,
        "program_switch": registry.async_get_entity_id(
            "switch", BHYVE_PLATFORM, f"{device_uid}_program_{slot.lower()}_enable"
        ),
        "enabled": None,
    }

    state = hass.states.get(entry.entity_id)
    if not _usable(state):
        return [
            {
                **base,
                "supported": False,
                "config": {},
                "notes": [
                    f"{entry.entity_id} has no reading yet; B-Hyve programs load on the "
                    "device's idle poll."
                ],
            }
        ]
    assert state is not None
    attributes = state.attributes
    if state.state == "empty" or attributes.get("empty"):
        return []

    notes: list[str] = []
    base["enabled"] = state.state == "enabled"
    if not base["enabled"]:
        notes.append(f"Program {slot} is disabled on the device.")

    name = attributes.get("name") or f"{device_name or entry.entity_id} program {slot}"
    config: dict[str, Any] = {CONF_NAME: name}

    frequency, frequency_notes = _bhyve_frequency(attributes.get("days"))
    notes.extend(frequency_notes)
    zones, zone_notes = _bhyve_zones(registry, device_uid, attributes.get("zones"))
    notes.extend(zone_notes)
    if zones:
        config[CONF_ZONES] = zones
        config[CONF_ZONE_MODE] = ZoneMode.SEQUENTIAL.value
        if len(zones) > 1:
            notes.append(
                "Zones import as sequential (unverified: assumes the device runs a "
                "program's zones one at a time)."
            )
    budget = attributes.get("budget")
    if budget is not None and budget != 100:
        notes.append(
            f"The program's seasonal budget is {budget}%; run times are imported as stored, "
            "not scaled."
        )
    start_times, time_notes = _bhyve_start_times(attributes.get("start_times"))
    notes.extend(time_notes)
    if frequency is not None:
        config.update(frequency)

    if frequency is None or not zones or not start_times:
        return [{**base, "supported": False, "config": config, "notes": notes}]

    if len(start_times) > 1:
        notes.append(
            f"Program {slot} has {len(start_times)} start times; each becomes its own schedule."
        )
    candidates = []
    for start in start_times:
        candidate = deepcopy(config)
        candidate[CONF_START_MODE] = StartMode.TIME.value
        candidate[CONF_START_TIME] = start.strftime("%H:%M:%S")
        if len(start_times) > 1:
            candidate[CONF_NAME] = f"{name} {start.strftime('%H:%M')}"
        candidates.append({**base, "supported": True, "config": candidate, "notes": list(notes)})
    return candidates


def _bhyve_frequency(days: Any) -> tuple[dict[str, Any] | None, list[str]]:
    """Frequency keys from orbit_bhyve's day summary text (sensor._fmt_days)."""
    if not isinstance(days, str) or not days.strip():
        return None, ["The program has no day summary; not imported."]
    text = days.strip()
    if text in _BHYVE_UNSUPPORTED_DAYS:
        return None, [_BHYVE_UNSUPPORTED_DAYS[text]]
    if text == "Every day":
        return {CONF_FREQUENCY: Frequency.WEEKDAYS.value, CONF_WEEKDAYS: list(range(7))}, []

    if match := _BHYVE_EVERY_N_DAYS.fullmatch(text):
        interval = int(match[1])
        if not MIN_INTERVAL_DAYS <= interval <= MAX_INTERVAL_DAYS:
            return None, [
                f"An interval of {interval} days is outside "
                f"{MIN_INTERVAL_DAYS}–{MAX_INTERVAL_DAYS}; not imported."
            ]
        config: dict[str, Any] = {
            CONF_FREQUENCY: Frequency.INTERVAL.value,
            CONF_INTERVAL_DAYS: interval,
        }
        if match[2] is None:
            return config, ["The program has no interval start date; choose the first run date."]
        try:
            config[CONF_ANCHOR] = date.fromisoformat(match[2]).isoformat()
        except ValueError:
            return config, [
                f"Interval start date {match[2]!r} is invalid; choose the first run date."
            ]
        return config, []

    names = [part.strip() for part in text.split(",")]
    if all(part in _BHYVE_WEEKDAYS for part in names):
        return {
            CONF_FREQUENCY: Frequency.WEEKDAYS.value,
            CONF_WEEKDAYS: sorted({_BHYVE_WEEKDAYS[part] for part in names}),
        }, []
    return None, [f"Unrecognised day summary {text!r}; not imported."]


def _bhyve_zones(
    registry: er.EntityRegistry, device_uid: str, zones: Any
) -> tuple[list[dict[str, Any]], list[str]]:
    """Map the program's 1-indexed zones to the device's valve entities."""
    if not isinstance(zones, list) or not zones:
        return [], ["The program has no zones; not imported."]
    result: list[dict[str, Any]] = []
    notes: list[str] = []
    for item in zones:
        try:
            station = int(item["zone"])
            minutes = float(item["minutes"])
        except (KeyError, TypeError, ValueError):
            notes.append(f"Skipped an unreadable zone entry {item!r}.")
            continue
        entity_id = _bhyve_station_valve(registry, device_uid, station)
        if entity_id is None:
            notes.append(f"Zone {station} has no matching valve entity; skipped.")
            continue
        if not math.isfinite(minutes) or minutes <= 0:
            notes.append(f"Zone {station} has no run time; skipped.")
            continue
        # Round half up (12.5 -> 13), then clamp to the integration's limits.
        whole = max(MIN_ZONE_MINUTES, min(MAX_ZONE_MINUTES, math.floor(minutes + 0.5)))
        if whole != minutes:
            notes.append(f"Zone {station} run time {minutes:g} min imported as {whole} min.")
        result.append({CONF_ZONE_ENTITY: entity_id, CONF_ZONE_MINUTES: whole})
    if not result:
        notes.append("No zone could be mapped to a valve; not imported.")
    return result, notes


def _bhyve_station_valve(
    registry: er.EntityRegistry, device_uid: str, station: int
) -> str | None:
    """orbit_bhyve valve unique ids: "<device>_zone_<n>", or "<device>_zone" on one-station devices."""
    unique_ids = [f"{device_uid}_zone_{station}"]
    if station == 1:
        unique_ids.append(f"{device_uid}_zone")
    for unique_id in unique_ids:
        if entity_id := registry.async_get_entity_id("valve", BHYVE_PLATFORM, unique_id):
            return entity_id
    return None


def _bhyve_start_times(values: Any) -> tuple[list[time], list[str]]:
    if not isinstance(values, list) or not values:
        return [], ["The program has no start time; not imported."]
    times: list[time] = []
    notes: list[str] = []
    for value in values:
        match = _TIME_TOKEN.fullmatch(value) if isinstance(value, str) else None
        if match is None or int(match[1]) > 23 or int(match[2]) > 59:
            notes.append(f"Skipped unreadable start time {value!r}.")
            continue
        start = time(int(match[1]), int(match[2]))
        if start not in times:
            times.append(start)
    if not times:
        notes.append("No start time could be read; not imported.")
    return times, notes


async def async_disable_bhyve_program(
    hass: HomeAssistant, program_switch_entity_id: str
) -> None:
    """Turn off a B-Hyve on-device program. Call only after the user confirms."""
    entry = er.async_get(hass).async_get(program_switch_entity_id)
    if (
        entry is None
        or entry.platform != BHYVE_PLATFORM
        or entry.domain != "switch"
        or not _PROGRAM_SWITCH_UID.fullmatch(entry.unique_id)
    ):
        raise HomeAssistantError(f"{program_switch_entity_id} is not a B-Hyve program switch")
    await hass.services.async_call(
        "switch", "turn_off", {ATTR_ENTITY_ID: program_switch_entity_id}, blocking=True
    )


# --- Helpers ----------------------------------------------------------------


def _usable(state: State | None) -> bool:
    return state is not None and state.state not in (STATE_UNKNOWN, STATE_UNAVAILABLE, "")


def _state_float(state: State | None) -> float | None:
    if not _usable(state):
        return None
    assert state is not None
    try:
        value = float(state.state)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


def _state_date(state: State | None) -> date | None:
    """Date from an input_datetime ("YYYY-MM-DD[ HH:MM:SS]") or text ("MM/DD/YYYY" or ISO)."""
    if not _usable(state):
        return None
    assert state is not None
    value = state.state.strip()
    if (parsed := dt_util.parse_datetime(value)) is not None:
        return parsed.date()
    try:
        return date.fromisoformat(value)
    except ValueError:
        pass
    try:
        return datetime.strptime(value, "%m/%d/%Y").date()
    except ValueError:
        return None
