"""AI helpers: weekly watering report, skip explanations, schedule parsing.

These call other integrations' services — ``ai_task.generate_data`` and,
optionally, ``llmvision.image_analyzer`` — and return text or a proposed
config. Nothing here writes config entries or changes a schedule: a parsed
description only pre-fills the config flow, which validates it again.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, time, timedelta
import json
import logging
import math
from typing import TYPE_CHECKING, Any, Final

from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.event import async_track_time_change
from homeassistant.util import dt as dt_util

from . import conditions
from .const import (
    CONF_AI_CAMERA,
    CONF_AI_LLMVISION_PROVIDER,
    CONF_AI_NOTIFY_SERVICE,
    CONF_AI_REPORT_TIME,
    CONF_AI_REPORT_WEEKDAY,
    CONF_AI_TASK_ENTITY,
    CONF_ANCHOR,
    CONF_FORECAST_HOURS,
    CONF_FORECAST_PROBABILITY,
    CONF_FREQUENCY,
    CONF_INTERVAL_DAYS,
    CONF_INTERVAL_HOURS,
    CONF_MOISTURE_MODE,
    CONF_MOISTURE_SENSORS,
    CONF_MOISTURE_THRESHOLD,
    CONF_NAME,
    CONF_RAIN_HOURS,
    CONF_RAIN_SENSOR,
    CONF_RAIN_THRESHOLD,
    CONF_RAIN_WINDOW,
    CONF_SKIP_CONDITIONS,
    CONF_START_MODE,
    CONF_START_TIME,
    CONF_SUN_OFFSET,
    CONF_TEMPERATURE_MAX,
    CONF_TEMPERATURE_MIN,
    CONF_WEATHER_ENTITY,
    CONF_WEEKDAYS,
    CONF_WIND_MAX,
    CONF_WINDOW_END,
    CONF_WINDOW_START,
    CONF_ZONE_ENTITY,
    CONF_ZONE_MINUTES,
    CONF_ZONE_MODE,
    CONF_ZONES,
    DEFAULT_WINDOW_END,
    DEFAULT_WINDOW_START,
    DOMAIN,
    MAX_INTERVAL_DAYS,
    MAX_INTERVAL_HOURS,
    MAX_SUN_OFFSET,
    MAX_ZONE_MINUTES,
    MIN_INTERVAL_DAYS,
    MIN_INTERVAL_HOURS,
    MIN_SUN_OFFSET,
    MIN_ZONE_MINUTES,
    MoistureMode,
    RainWindow,
    SkipCondition,
    zone_entity_ids,
)
from .scheduler import Frequency, Schedule, StartMode, ZoneMode

if TYPE_CHECKING:
    from .runner import ScheduleRunner

_LOGGER = logging.getLogger(__name__)

AI_TASK_DOMAIN: Final = "ai_task"
SERVICE_AI_GENERATE_DATA: Final = "generate_data"
LLMVISION_DOMAIN: Final = "llmvision"
SERVICE_IMAGE_ANALYZER: Final = "image_analyzer"
PERSISTENT_NOTIFICATION_SERVICE: Final = "persistent_notification.create"

MIN_REPORT_DAYS: Final = 1
MAX_REPORT_DAYS: Final = 60
# Cap per candidate group so a large install doesn't flood the prompt.
MAX_CANDIDATES: Final = 150

DATA_MARKER: Final = "Data (JSON):\n"
CANDIDATES_MARKER: Final = "Candidate entities (JSON):\n"
DESCRIPTION_MARKER: Final = "Description:\n"

REPORT_INSTRUCTIONS: Final = (
    "You are reviewing an automated irrigation schedule in Home Assistant. Using "
    "only the JSON data below, write a short plain-text report covering the last "
    "{days} days: how often it watered and for how long, which runs were skipped "
    "and why (quote the measured values), anything that looks wrong (errors, "
    "interrupted runs, zones that failed), and at most three concrete suggestions "
    "such as changing a run time, the frequency or a threshold. If lawn_camera is "
    "present, include its observations. Do not invent data that is not in the "
    "JSON. Plain text, no tables, under 250 words."
)
EXPLAIN_INSTRUCTIONS: Final = (
    "Explain in plain language why the irrigation schedule below skipped these "
    "runs in the last {days} days. For each skip give the date and the measured "
    "values against the thresholds from the JSON. Group repeated reasons. Do not "
    "invent data that is not in the JSON. Plain text, under 150 words."
)
PARSE_INSTRUCTIONS: Final = (
    "Convert the irrigation schedule description into the requested fields. Only "
    "fill fields the description states or clearly implies; leave the rest empty. "
    "Use entity ids exactly as listed in the candidate entities. Weekdays are "
    "numbers, 0 = Monday through 6 = Sunday. For sunrise or sunset starts, "
    "sun_offset_minutes is how many minutes before the event watering finishes. "
    "For every N hours between two times each day, use frequency hourly with "
    "interval_hours, window_start and window_end, and start_mode time."
)
LAWN_PROMPT: Final = (
    "This is a photo of a yard. Describe visible signs of under-watering (brown or "
    "dry patches, wilting) or over-watering (standing water, soggy or yellowing "
    "areas). Say if the image is too dark or unclear to judge. Under 80 words."
)

# Ranges the config flow enforces; the flow's own minimums are imported lazily
# in validate_partial_config because config_flow may import this module.
_RAIN_THRESHOLD_MAX: Final = 1000
_RAIN_HOURS_RANGE: Final = (1, 72)
_FORECAST_HOURS_RANGE: Final = (1, 48)
_PERCENT_MAX: Final = 100
_TEMPERATURE_RANGE: Final = (-100, 200)  # either unit; the sensor decides
_WIND_MAX_LIMIT: Final = 500

_WEEKDAY_NAMES: Final = {
    name: index
    for index, names in enumerate(
        (
            ("monday", "mon"),
            ("tuesday", "tue"),
            ("wednesday", "wed"),
            ("thursday", "thu"),
            ("friday", "fri"),
            ("saturday", "sat"),
            ("sunday", "sun"),
        )
    )
    for name in names
}

# Keys each condition owns in a parsed description.
_PARSE_CONDITION_KEYS: Final[dict[SkipCondition, tuple[str, ...]]] = {
    SkipCondition.RAIN: (CONF_RAIN_SENSOR, CONF_RAIN_THRESHOLD, CONF_RAIN_HOURS),
    SkipCondition.FORECAST: (
        CONF_WEATHER_ENTITY,
        CONF_FORECAST_PROBABILITY,
        CONF_FORECAST_HOURS,
    ),
    SkipCondition.MOISTURE: (
        CONF_MOISTURE_SENSORS,
        CONF_MOISTURE_THRESHOLD,
        CONF_MOISTURE_MODE,
    ),
    SkipCondition.TEMPERATURE: (CONF_TEMPERATURE_MIN, CONF_TEMPERATURE_MAX),
    SkipCondition.WIND: (CONF_WIND_MAX,),
}


class AiNotConfigured(HomeAssistantError):
    """The schedule has no AI task entity configured."""


# --- Report and explanations ------------------------------------------------


async def async_generate_report(
    hass: HomeAssistant, runner: ScheduleRunner, *, days: int = 7
) -> str:
    """Plain-text report on the schedule's last `days` days, written by the AI task."""
    entity_id = _ai_task_entity(runner)
    days = _clamp_days(days)
    context = await async_build_context(hass, runner, days=days, now=dt_util.now())
    if (lawn := await _async_lawn_analysis(hass, runner.config)) is not None:
        context["lawn_camera"] = lawn
    instructions = (
        f"{REPORT_INSTRUCTIONS.format(days=days)}\n\n{DATA_MARKER}{_dumps(context)}"
    )
    data = await _async_generate_data(
        hass, entity_id, f"{runner.entry.title} watering report", instructions
    )
    return data if isinstance(data, str) else _dumps(data)


async def async_explain_skips(
    hass: HomeAssistant, runner: ScheduleRunner, *, days: int = 7
) -> str:
    """Plain-language explanation of the schedule's skips in the last `days` days."""
    entity_id = _ai_task_entity(runner)
    days = _clamp_days(days)
    now = dt_util.now()
    skips = [
        record for record in _history(runner, days, now) if record.get("type") == "skip"
    ]
    if not skips:
        # Nothing to explain; don't spend a model call on it.
        return f"No runs of {runner.entry.title} were skipped in the last {days} days."

    context = {
        "schedule": runner.entry.title,
        "period_days": days,
        "config": _report_config(runner.config),
        "skips": skips,
    }
    instructions = (
        f"{EXPLAIN_INSTRUCTIONS.format(days=days)}\n\n{DATA_MARKER}{_dumps(context)}"
    )
    data = await _async_generate_data(
        hass, entity_id, f"{runner.entry.title} skip explanation", instructions
    )
    return data if isinstance(data, str) else _dumps(data)


async def async_build_context(
    hass: HomeAssistant, runner: ScheduleRunner, *, days: int, now: datetime
) -> dict[str, Any]:
    """JSON-serializable summary of the schedule for a prompt."""
    snapshot = runner.snapshot()
    config = snapshot.get("config") or dict(runner.config)
    state_keys = (
        "enabled",
        "paused",
        "status",
        "next_run",
        "next_run_scheduled",
        "rain_delay_until",
        "last_run_start",
        "last_run_end",
        "last_run_total_minutes",
        "last_watering_end",
        "last_status_at",
        "last_details",
    )
    return {
        "schedule": snapshot.get("name") or runner.entry.title,
        "generated_at": now.isoformat(),
        "period_days": days,
        "config": _report_config(config),
        "zone_names": {
            entity_id: _friendly_name(hass, entity_id)
            for entity_id in zone_entity_ids(config)
        },
        "state": {key: snapshot.get(key) for key in state_keys if key in snapshot},
        "history": _history(runner, days, now),
        "current_conditions": await _async_current_conditions(hass, config, days, now),
    }


def _history(runner: Any, days: int, now: datetime) -> list[dict[str, Any]]:
    """History records within `days`, newest first.

    Runners without run history fall back to the last recorded skip, if any.
    """
    history_fn = getattr(runner, "history", None)
    if callable(history_fn):
        records = history_fn()
    else:
        snapshot = runner.snapshot()
        records = snapshot.get("history")
        if records is None:
            records = []
            status = str(snapshot.get("status") or "")
            if status.startswith("skipped_"):
                records.append(
                    {
                        "at": snapshot.get("last_status_at"),
                        "type": "skip",
                        "status": status,
                        "details": snapshot.get("last_details") or {},
                    }
                )

    cutoff = now - timedelta(days=days)
    recent = []
    for record in records or []:
        at = _parse_datetime(record.get("at"))
        if at is not None and at >= cutoff:
            recent.append(dict(record))
    return recent


async def _async_current_conditions(
    hass: HomeAssistant, config: Mapping[str, Any], days: int, now: datetime
) -> dict[str, Any]:
    """Rain over the report period and current moisture, when configured."""
    enabled = {str(value) for value in config.get(CONF_SKIP_CONDITIONS) or []}
    current: dict[str, Any] = {}
    if SkipCondition.RAIN in enabled:
        period = {
            **config,
            CONF_RAIN_HOURS: days * 24,
            CONF_RAIN_WINDOW: RainWindow.HOURS.value,
        }
        try:
            rain = await conditions.async_check_rain(hass, period, now)
            current["rain_over_period"] = rain.details
        except Exception:  # noqa: BLE001 — context is best effort
            _LOGGER.exception("Reading rain for the AI report failed")
    if SkipCondition.MOISTURE in enabled:
        try:
            current["moisture_now"] = conditions.check_moisture(hass, config).details
        except Exception:  # noqa: BLE001 — context is best effort
            _LOGGER.exception("Reading moisture for the AI report failed")
    return current


async def _async_lawn_analysis(
    hass: HomeAssistant, config: Mapping[str, Any]
) -> dict[str, Any] | None:
    """LLM Vision observations of the yard camera, or None if no camera is set."""
    camera = config.get(CONF_AI_CAMERA)
    if not camera:
        return None
    provider = config.get(CONF_AI_LLMVISION_PROVIDER)
    if not provider:
        return {"camera": camera, "error": "no LLM Vision provider configured"}
    if not hass.services.has_service(LLMVISION_DOMAIN, SERVICE_IMAGE_ANALYZER):
        return {"camera": camera, "error": "llmvision.image_analyzer is not available"}
    try:
        response = await hass.services.async_call(
            LLMVISION_DOMAIN,
            SERVICE_IMAGE_ANALYZER,
            {
                "provider": provider,
                "message": LAWN_PROMPT,
                "image_entity": [camera],
                "include_filename": False,
                "store_in_timeline": False,
            },
            blocking=True,
            return_response=True,
        )
    except Exception:  # noqa: BLE001 — the report goes out without it
        _LOGGER.warning("Camera analysis of %s failed", camera, exc_info=True)
        return {"camera": camera, "error": "camera analysis failed"}
    text = (response or {}).get("response_text")
    if not text:
        return {"camera": camera, "error": "camera analysis returned no text"}
    return {"camera": camera, "observations": text}


async def _async_generate_data(
    hass: HomeAssistant,
    entity_id: str,
    task_name: str,
    instructions: str,
    structure: dict[str, Any] | None = None,
) -> Any:
    """Call ai_task.generate_data and return its `data`."""
    if not hass.services.has_service(AI_TASK_DOMAIN, SERVICE_AI_GENERATE_DATA):
        raise HomeAssistantError("ai_task.generate_data is not available")
    payload: dict[str, Any] = {
        "task_name": task_name,
        "instructions": instructions,
        "entity_id": entity_id,
    }
    if structure is not None:
        payload["structure"] = structure
    try:
        response = await hass.services.async_call(
            AI_TASK_DOMAIN,
            SERVICE_AI_GENERATE_DATA,
            payload,
            blocking=True,
            return_response=True,
        )
    except HomeAssistantError:
        raise
    except Exception as err:  # noqa: BLE001 — surface as a HA error
        raise HomeAssistantError(f"ai_task.generate_data failed: {err}") from err
    data = (response or {}).get("data")
    if data is None:
        raise HomeAssistantError("ai_task.generate_data returned no data")
    return data


# --- Notifications and the weekly report ------------------------------------


async def async_send_notification(
    hass: HomeAssistant,
    service: str | None,
    *,
    title: str,
    message: str,
    notification_id: str,
) -> None:
    """Send via `notify.<target>` or `persistent_notification.create` (default)."""
    service = service or PERSISTENT_NOTIFICATION_SERVICE
    domain, _, name = service.partition(".")
    if service == PERSISTENT_NOTIFICATION_SERVICE:
        data = {"title": title, "message": message, "notification_id": notification_id}
    elif domain == "notify" and name:
        data = {"title": title, "message": message}
    else:
        raise HomeAssistantError(f"Unsupported notification service {service}")
    if not hass.services.has_service(domain, name):
        raise HomeAssistantError(f"Service {service} is not available")
    await hass.services.async_call(domain, name, data, blocking=True)


async def async_send_weekly_report(hass: HomeAssistant, runner: ScheduleRunner) -> None:
    """Generate and send the report. Errors are logged, never raised."""
    title = f"{runner.entry.title} watering report"
    try:
        report = await async_generate_report(hass, runner)
        await async_send_notification(
            hass,
            runner.config.get(CONF_AI_NOTIFY_SERVICE),
            title=title,
            message=report,
            notification_id=f"{DOMAIN}_{runner.entry.entry_id}_report",
        )
    except Exception:  # noqa: BLE001 — a timer callback must not raise
        _LOGGER.exception("%s: sending the weekly AI report failed", runner.entry.title)


@callback
def async_setup_weekly_report(
    hass: HomeAssistant, runner: ScheduleRunner
) -> CALLBACK_TYPE:
    """Send the AI report weekly at the configured local weekday and time.

    Follows the runner's config: the timer is re-registered when the AI report
    settings change. The returned callback cancels everything.
    """
    unsub_timer: CALLBACK_TYPE | None = None
    settings: tuple[int, time] | None = None
    last_sent: date | None = None

    async def _async_fire(now: datetime) -> None:
        nonlocal last_sent
        if settings is None:
            return
        local_now = dt_util.as_local(now)
        # The time listener matches the local clock every day; the repeated
        # hour on a fall-back day can match twice.
        if local_now.weekday() != settings[0] or last_sent == local_now.date():
            return
        last_sent = local_now.date()
        await async_send_weekly_report(hass, runner)

    @callback
    def _refresh() -> None:
        nonlocal unsub_timer, settings
        new_settings = _report_settings(runner.config)
        if new_settings == settings:
            return
        if unsub_timer is not None:
            unsub_timer()
            unsub_timer = None
        settings = new_settings
        if settings is not None:
            at = settings[1]
            unsub_timer = async_track_time_change(
                hass, _async_fire, hour=at.hour, minute=at.minute, second=at.second
            )

    _refresh()
    add_listener = getattr(runner, "async_add_listener", None)
    unsub_listener = add_listener(_refresh) if callable(add_listener) else None

    @callback
    def _cancel() -> None:
        nonlocal unsub_timer, unsub_listener
        if unsub_timer is not None:
            unsub_timer()
            unsub_timer = None
        if unsub_listener is not None:
            unsub_listener()
            unsub_listener = None

    return _cancel


def _report_settings(config: Mapping[str, Any]) -> tuple[int, time] | None:
    """(weekday, local time) for the weekly report, or None when it's off or invalid."""
    weekday = config.get(CONF_AI_REPORT_WEEKDAY)
    at = config.get(CONF_AI_REPORT_TIME)
    if weekday is None or not at or not config.get(CONF_AI_TASK_ENTITY):
        return None
    try:
        weekday = _int_in(weekday, 0, 6)
        return weekday, time.fromisoformat(str(at)).replace(microsecond=0)
    except ValueError:
        _LOGGER.warning("Ignoring invalid AI report weekday/time %r %r", weekday, at)
        return None


# --- Natural-language schedule parsing --------------------------------------


async def async_parse_schedule_description(
    hass: HomeAssistant, ai_task_entity: str, text: str
) -> dict[str, Any]:
    """Proposed partial config from a free-text description.

    Returns {"config": {...}, "warnings": [...]}. Values outside the config
    flow's limits, unknown entities and keys that don't apply are dropped with a
    warning. Nothing is saved; the config flow uses the result as defaults.
    """
    text = (text or "").strip()
    if not text:
        raise HomeAssistantError("The schedule description is empty")
    if not ai_task_entity:
        raise AiNotConfigured("No AI task entity selected")

    instructions = (
        f"{PARSE_INSTRUCTIONS}\n\n{CANDIDATES_MARKER}"
        f"{_dumps(_entity_candidates(hass))}\n\n{DESCRIPTION_MARKER}{text}"
    )
    data = await _async_generate_data(
        hass, ai_task_entity, "irrigation schedule from description", instructions,
        structure=_parse_structure(),
    )
    if not isinstance(data, Mapping):
        return {
            "config": {},
            "warnings": ["The AI response was not structured data; nothing was filled in."],
        }
    config, warnings = validate_partial_config(hass, data, today=dt_util.now().date())
    return {"config": config, "warnings": warnings}


def validate_partial_config(
    hass: HomeAssistant, data: Mapping[str, Any], *, today: date
) -> tuple[dict[str, Any], list[str]]:
    """Keep only values the config flow would accept. Returns (config, warnings)."""
    # Lazy: config_flow may import this module for its describe step.
    from .config_flow import (  # noqa: PLC0415
        MIN_FORECAST_PROBABILITY,
        MIN_MOISTURE_THRESHOLD,
        MIN_RAIN_THRESHOLD,
    )

    validators: dict[str, Any] = {
        CONF_NAME: _valid_name,
        CONF_ZONE_MODE: lambda value: ZoneMode(value).value,
        CONF_FREQUENCY: lambda value: Frequency(value).value,
        CONF_INTERVAL_DAYS: lambda value: _int_in(value, MIN_INTERVAL_DAYS, MAX_INTERVAL_DAYS),
        CONF_ANCHOR: lambda value: date.fromisoformat(str(value)).isoformat(),
        CONF_WEEKDAYS: _valid_weekdays,
        CONF_INTERVAL_HOURS: lambda value: _int_in(value, MIN_INTERVAL_HOURS, MAX_INTERVAL_HOURS),
        CONF_WINDOW_START: _valid_clock,
        CONF_WINDOW_END: _valid_clock,
        CONF_START_MODE: lambda value: StartMode(value).value,
        CONF_START_TIME: lambda value: time.fromisoformat(str(value)).strftime("%H:%M:%S"),
        CONF_SUN_OFFSET: lambda value: _int_in(value, MIN_SUN_OFFSET, MAX_SUN_OFFSET),
        CONF_RAIN_SENSOR: lambda value: _valid_entity(hass, value, "sensor"),
        CONF_RAIN_THRESHOLD: lambda value: _float_in(
            value, MIN_RAIN_THRESHOLD, _RAIN_THRESHOLD_MAX
        ),
        CONF_RAIN_HOURS: lambda value: _int_in(value, *_RAIN_HOURS_RANGE),
        CONF_WEATHER_ENTITY: lambda value: _valid_entity(hass, value, "weather"),
        CONF_FORECAST_PROBABILITY: lambda value: _int_in(
            value, MIN_FORECAST_PROBABILITY, _PERCENT_MAX
        ),
        CONF_FORECAST_HOURS: lambda value: _int_in(value, *_FORECAST_HOURS_RANGE),
        CONF_MOISTURE_SENSORS: lambda value: _valid_entities(hass, value, "sensor"),
        CONF_MOISTURE_THRESHOLD: lambda value: _float_in(
            value, MIN_MOISTURE_THRESHOLD, _PERCENT_MAX
        ),
        CONF_MOISTURE_MODE: lambda value: MoistureMode(value).value,
        CONF_TEMPERATURE_MIN: lambda value: _float_in(value, *_TEMPERATURE_RANGE),
        CONF_TEMPERATURE_MAX: lambda value: _float_in(value, *_TEMPERATURE_RANGE),
        CONF_WIND_MAX: lambda value: _float_in(value, 0, _WIND_MAX_LIMIT, low_open=True),
    }

    config: dict[str, Any] = {}
    warnings: list[str] = []

    for key, value in data.items():
        if value is None or value == "" or value == [] or value == {}:
            continue
        if key == CONF_ZONES:
            zones = _valid_zones(hass, value, warnings)
            if zones:
                config[CONF_ZONES] = zones
            continue
        if key == CONF_SKIP_CONDITIONS:
            config[CONF_SKIP_CONDITIONS] = _valid_conditions(value, warnings)
            continue
        if key not in validators:
            warnings.append(f"{key}: ignored, not a schedule setting")
            continue
        try:
            config[key] = validators[key](value)
        except (TypeError, ValueError) as err:
            warnings.append(f"{key}: {value!r} ignored ({_reason(err)})")

    _drop_unused_keys(config, warnings)
    _check_timing(config, warnings, today)
    return config, warnings


def _drop_unused_keys(config: dict[str, Any], warnings: list[str]) -> None:
    """Remove keys the chosen frequency, start mode or conditions don't use."""
    unused: list[str] = []
    frequency = config.get(CONF_FREQUENCY)
    hourly_keys = [CONF_INTERVAL_HOURS, CONF_WINDOW_START, CONF_WINDOW_END]
    if frequency == Frequency.INTERVAL:
        unused += [CONF_WEEKDAYS, *hourly_keys]
    elif frequency == Frequency.WEEKDAYS:
        unused += [CONF_INTERVAL_DAYS, CONF_ANCHOR, *hourly_keys]
    elif frequency == Frequency.HOURLY:
        unused += [CONF_INTERVAL_DAYS, CONF_ANCHOR, CONF_WEEKDAYS, CONF_SUN_OFFSET]
        # Hourly runs start at the window start; a sun start doesn't apply.
        if config.get(CONF_START_MODE) in (StartMode.SUNRISE, StartMode.SUNSET):
            unused.append(CONF_START_MODE)

    start_mode = config.get(CONF_START_MODE)
    if start_mode == StartMode.TIME:
        unused.append(CONF_SUN_OFFSET)
    elif start_mode in (StartMode.SUNRISE, StartMode.SUNSET):
        unused.append(CONF_START_TIME)

    selected = set(config.get(CONF_SKIP_CONDITIONS) or [])
    for condition, keys in _PARSE_CONDITION_KEYS.items():
        if condition.value not in selected:
            unused += list(keys)

    for key in unused:
        if key in config:
            config.pop(key)
            warnings.append(f"{key}: ignored, not used by the chosen settings")

    if (
        CONF_TEMPERATURE_MIN in config
        and CONF_TEMPERATURE_MAX in config
        and config[CONF_TEMPERATURE_MIN] >= config[CONF_TEMPERATURE_MAX]
    ):
        config.pop(CONF_TEMPERATURE_MIN)
        config.pop(CONF_TEMPERATURE_MAX)
        warnings.append("temperature_min/temperature_max: ignored, min is not below max")


def _check_timing(config: dict[str, Any], warnings: list[str], today: date) -> None:
    """Drop the frequency if it can't form a valid schedule with flow defaults."""
    if CONF_FREQUENCY not in config:
        return
    try:
        # Missing anchor/start time get the flow's defaults, so only the
        # frequency's own values are tested here.
        Schedule(
            frequency=config[CONF_FREQUENCY],
            start_mode=StartMode.TIME,
            interval_days=config.get(CONF_INTERVAL_DAYS, MIN_INTERVAL_DAYS),
            anchor=date.fromisoformat(config[CONF_ANCHOR]) if CONF_ANCHOR in config else today,
            weekdays=config.get(CONF_WEEKDAYS, []),
            start_time=time(6),
            interval_hours=config.get(CONF_INTERVAL_HOURS, MIN_INTERVAL_HOURS),
            window_start=time.fromisoformat(config.get(CONF_WINDOW_START, DEFAULT_WINDOW_START)),
            window_end=time.fromisoformat(config.get(CONF_WINDOW_END, DEFAULT_WINDOW_END)),
        )
    except ValueError as err:
        for key in (
            CONF_FREQUENCY,
            CONF_INTERVAL_DAYS,
            CONF_ANCHOR,
            CONF_WEEKDAYS,
            CONF_INTERVAL_HOURS,
            CONF_WINDOW_START,
            CONF_WINDOW_END,
        ):
            config.pop(key, None)
        warnings.append(f"frequency: ignored ({err})")


def _parse_structure() -> dict[str, Any]:
    """ai_task structure for a schedule description.

    Number fields carry no min/max: out-of-range answers are dropped with a
    warning by validate_partial_config instead of failing the whole task.
    """

    def field(description: str, selector: dict[str, Any]) -> dict[str, Any]:
        return {"description": description, "selector": selector}

    def select(options: list[str], multiple: bool = False) -> dict[str, Any]:
        return {"select": {"options": options, "multiple": multiple}}

    number = {"number": {"mode": "box", "step": "any"}}
    text = {"text": {}}
    return {
        CONF_NAME: field("Short schedule name", text),
        CONF_ZONES: field(
            'Zones as a list of {"entity_id": "<valve or switch entity id from the '
            'candidates>", "minutes": <run time in minutes>}',
            {"object": {}},
        ),
        CONF_ZONE_MODE: field(
            "sequential = one zone after another, concurrent = all at once",
            select([mode.value for mode in ZoneMode]),
        ),
        CONF_FREQUENCY: field(
            "interval = every N days, weekdays = specific days of the week, "
            "hourly = every N hours between window_start and window_end each day",
            select([frequency.value for frequency in Frequency]),
        ),
        CONF_INTERVAL_DAYS: field("For interval: water every this many days", number),
        CONF_ANCHOR: field("For interval: first run date, YYYY-MM-DD", {"date": {}}),
        CONF_WEEKDAYS: field(
            "For weekdays: day numbers, 0 = Monday ... 6 = Sunday",
            select([str(day) for day in range(7)], multiple=True),
        ),
        CONF_INTERVAL_HOURS: field("For hourly: water every this many hours", number),
        CONF_WINDOW_START: field("For hourly: local time of the first run each day", {"time": {}}),
        CONF_WINDOW_END: field("For hourly: no run starts after this local time", {"time": {}}),
        CONF_START_MODE: field(
            "time = fixed clock time; sunrise/sunset = finish watering before the event",
            select([mode.value for mode in StartMode]),
        ),
        CONF_START_TIME: field("For time: local start time", {"time": {}}),
        CONF_SUN_OFFSET: field(
            "For sunrise/sunset: finish this many minutes before the event "
            "(negative = after)",
            number,
        ),
        CONF_SKIP_CONDITIONS: field(
            "Conditions that can skip a run",
            select([condition.value for condition in SkipCondition], multiple=True),
        ),
        CONF_RAIN_SENSOR: field("Rain gauge sensor entity id from the candidates", text),
        CONF_RAIN_THRESHOLD: field("Skip if at least this much rain fell", number),
        CONF_RAIN_HOURS: field("Rain look-back window in hours", number),
        CONF_WEATHER_ENTITY: field("Weather entity id from the candidates", text),
        CONF_FORECAST_PROBABILITY: field(
            "Skip if the forecast chance of rain is at least this percent", number
        ),
        CONF_FORECAST_HOURS: field("Forecast look-ahead window in hours", number),
        CONF_MOISTURE_SENSORS: field(
            "Soil moisture sensor entity ids from the candidates, as a list",
            {"object": {}},
        ),
        CONF_MOISTURE_THRESHOLD: field("Moisture percent that counts as dry below", number),
        CONF_MOISTURE_MODE: field(
            "skip = water on schedule days only when dry; trigger = also water on "
            "other days when dry",
            select([mode.value for mode in MoistureMode]),
        ),
        CONF_TEMPERATURE_MIN: field("Skip at or below this temperature", number),
        CONF_TEMPERATURE_MAX: field("Skip at or above this temperature", number),
        CONF_WIND_MAX: field("Skip at or above this wind speed", number),
    }


@callback
def _entity_candidates(hass: HomeAssistant) -> dict[str, dict[str, str]]:
    """Entity ids and names the model may use, grouped by purpose."""
    groups: dict[str, dict[str, str]] = {
        "zones": {},
        "rain_sensors": {},
        "weather": {},
        "moisture_sensors": {},
        "temperature_sensors": {},
        "wind_sensors": {},
    }
    device_class_groups = {
        "precipitation": "rain_sensors",
        "moisture": "moisture_sensors",
        "temperature": "temperature_sensors",
        "wind_speed": "wind_sensors",
    }
    # Valves first so they aren't crowded out by the many plain switches.
    states = sorted(hass.states.async_all(), key=lambda state: state.domain != "valve")
    for state in states:
        group = None
        if state.domain in ("valve", "switch"):
            group = "zones"
        elif state.domain == "weather":
            group = "weather"
        elif state.domain == "sensor":
            group = device_class_groups.get(state.attributes.get("device_class"))
        if group is not None and len(groups[group]) < MAX_CANDIDATES:
            groups[group][state.entity_id] = state.name
    return groups


# --- Validation helpers -----------------------------------------------------


def _valid_name(value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("must be text")
    return value.strip()[:100]


def _valid_zones(
    hass: HomeAssistant, value: Any, warnings: list[str]
) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        warnings.append(f"{CONF_ZONES}: {value!r} ignored (must be a list)")
        return []
    zones: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in value:
        try:
            if not isinstance(item, Mapping):
                raise ValueError("each zone needs entity_id and minutes")
            entity_id = _valid_entity(hass, item.get(CONF_ZONE_ENTITY), "valve", "switch")
            minutes = _int_in(item.get(CONF_ZONE_MINUTES), MIN_ZONE_MINUTES, MAX_ZONE_MINUTES)
        except (TypeError, ValueError) as err:
            warnings.append(f"{CONF_ZONES}: {item!r} ignored ({_reason(err)})")
            continue
        if entity_id in seen:
            continue
        seen.add(entity_id)
        zones.append({CONF_ZONE_ENTITY: entity_id, CONF_ZONE_MINUTES: minutes})
    return zones


def _valid_conditions(value: Any, warnings: list[str]) -> list[str]:
    values = value if isinstance(value, list) else [value]
    chosen: set[SkipCondition] = set()
    for item in values:
        try:
            chosen.add(SkipCondition(item))
        except ValueError:
            warnings.append(f"{CONF_SKIP_CONDITIONS}: {item!r} ignored (unknown condition)")
    return [condition.value for condition in SkipCondition if condition in chosen]


def _valid_weekdays(value: Any) -> list[int]:
    values = value if isinstance(value, list) else [value]
    days: set[int] = set()
    for item in values:
        if isinstance(item, str) and item.strip().casefold() in _WEEKDAY_NAMES:
            days.add(_WEEKDAY_NAMES[item.strip().casefold()])
        else:
            days.add(_int_in(item, 0, 6))
    if not days:
        raise ValueError("no weekdays")
    return sorted(days)


def _valid_clock(value: Any) -> str:
    return time.fromisoformat(str(value)).strftime("%H:%M:%S")


def _valid_entity(hass: HomeAssistant, value: Any, *domains: str) -> str:
    if not isinstance(value, str) or value.partition(".")[0] not in domains:
        raise ValueError(f"must be a {'/'.join(domains)} entity id")
    if hass.states.get(value) is None:
        raise ValueError("entity not found")
    return value


def _valid_entities(hass: HomeAssistant, value: Any, *domains: str) -> list[str]:
    values = value if isinstance(value, list) else [value]
    entities = list(dict.fromkeys(_valid_entity(hass, item, *domains) for item in values))
    if not entities:
        raise ValueError("no entities")
    return entities


def _int_in(value: Any, low: int, high: int) -> int:
    number = _number(value)
    if not number.is_integer():
        raise ValueError("must be a whole number")
    if not low <= number <= high:
        raise ValueError(f"must be between {low} and {high}")
    return int(number)


def _float_in(value: Any, low: float, high: float, *, low_open: bool = False) -> float:
    number = _number(value)
    if (number <= low if low_open else number < low) or number > high:
        raise ValueError(f"must be between {low} and {high}")
    return int(number) if number.is_integer() else number


def _number(value: Any) -> float:
    if isinstance(value, bool) or value is None:
        raise ValueError("must be a number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("must be a finite number")
    return number


def _reason(err: Exception) -> str:
    return str(err) or type(err).__name__


# --- Small helpers ----------------------------------------------------------


def _ai_task_entity(runner: ScheduleRunner) -> str:
    entity_id = runner.config.get(CONF_AI_TASK_ENTITY)
    if not entity_id:
        raise AiNotConfigured(f"{runner.entry.title} has no AI task entity configured")
    return entity_id


def _report_config(config: Mapping[str, Any]) -> dict[str, Any]:
    """Schedule config for a prompt, without the AI/notification settings."""
    return {key: value for key, value in config.items() if not key.startswith("ai_")}


def _clamp_days(days: Any) -> int:
    try:
        return max(MIN_REPORT_DAYS, min(MAX_REPORT_DAYS, int(days)))
    except (TypeError, ValueError):
        return 7


def _friendly_name(hass: HomeAssistant, entity_id: str) -> str:
    state = hass.states.get(entity_id)
    return state.name if state is not None else entity_id


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return dt_util.parse_datetime(value)
    return None


def _dumps(value: Any) -> str:
    return json.dumps(value, default=str, ensure_ascii=False)
