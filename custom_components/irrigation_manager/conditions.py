"""Skip/trigger conditions evaluated at each schedule occurrence.

Each check reads its sources — rain sensors' recorded totals, weather entities'
forecasts, temperature/wind/moisture sensor states, occupancy entities — and
never raises: a source that can't be read comes back ``available=False``.
``decide`` is pure and applies the rules; ``async_decide`` runs only the checks
an occurrence needs and hands the results to it.

A config without the v0.2 keys behaves exactly as v0.1: one rain sensor, one
weather entity, probability only.

CONF_STALE_HOURS applies to the temperature sensor only. Core MQTT entities
don't write a state whose value and attributes are unchanged
(homeassistant/components/mqtt/entity.py, ``_attrs_have_changed``, unless
force_update is set), so ``last_reported`` stops advancing on a steady rain
gauge, moisture probe or calm wind sensor that is still working.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
import logging
import math
from statistics import median
from typing import Any, Final

from homeassistant.components.recorder import get_instance, history, statistics
from homeassistant.components.weather import (
    ATTR_FORECAST_PRECIPITATION,
    ATTR_FORECAST_PRECIPITATION_PROBABILITY,
    ATTR_FORECAST_TEMP,
    ATTR_FORECAST_TEMP_LOW,
    ATTR_FORECAST_TIME,
    ATTR_WEATHER_PRECIPITATION_UNIT,
    ATTR_WEATHER_TEMPERATURE_UNIT,
    DOMAIN as WEATHER_DOMAIN,
    SERVICE_GET_FORECASTS,
    WeatherEntityFeature,
)
from homeassistant.const import (
    ATTR_SUPPORTED_FEATURES,
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant, State, callback
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import DistanceConverter, TemperatureConverter

from .const import (
    CONF_FORECAST_AMOUNT,
    CONF_FORECAST_HOURS,
    CONF_FORECAST_MODE,
    CONF_FORECAST_PROBABILITY,
    CONF_FORECAST_QUORUM,
    CONF_MOISTURE_MODE,
    CONF_MOISTURE_SENSORS,
    CONF_MOISTURE_THRESHOLD,
    CONF_MOISTURE_UNAVAILABLE,
    CONF_OCCUPANCY_ACTION,
    CONF_OCCUPANCY_ENTITIES,
    CONF_RAIN_AGGREGATE,
    CONF_RAIN_HOURS,
    CONF_RAIN_MAX_HOURS,
    CONF_RAIN_QUORUM,
    CONF_RAIN_SENSOR,
    CONF_RAIN_SENSORS,
    CONF_RAIN_THRESHOLD,
    CONF_RAIN_WINDOW,
    CONF_SKIP_CONDITIONS,
    CONF_STALE_HOURS,
    CONF_TEMPERATURE_FORECAST_HOURS,
    CONF_TEMPERATURE_MAX,
    CONF_TEMPERATURE_MIN,
    CONF_TEMPERATURE_SENSOR,
    CONF_WEATHER_ENTITIES,
    CONF_WEATHER_ENTITY,
    CONF_WIND_MAX,
    CONF_WIND_MINUTES,
    CONF_WIND_SENSOR,
    DEFAULT_FORECAST_HOURS,
    DEFAULT_FORECAST_PROBABILITY,
    DEFAULT_FORECAST_QUORUM,
    DEFAULT_MOISTURE_MODE,
    DEFAULT_MOISTURE_THRESHOLD,
    DEFAULT_RAIN_HOURS,
    DEFAULT_RAIN_MAX_HOURS,
    DEFAULT_RAIN_QUORUM,
    DEFAULT_RAIN_THRESHOLD,
    DEFAULT_TEMPERATURE_FORECAST_HOURS,
    DEFAULT_WIND_MINUTES,
    ForecastMode,
    MoistureMode,
    MoistureUnavailable,
    OccupancyAction,
    RainAggregate,
    RainWindow,
    SkipCondition,
    Status,
)

_LOGGER = logging.getLogger(__name__)

# Length of one forecast entry by forecast type.
FORECAST_PERIODS: Final[dict[str, timedelta]] = {
    "hourly": timedelta(hours=1),
    "twice_daily": timedelta(hours=12),
    "daily": timedelta(days=1),
}
# Forecast types to request, finest first; the first one the entity supports wins.
_FORECAST_PREFERENCE = (
    ("hourly", WeatherEntityFeature.FORECAST_HOURLY),
    ("twice_daily", WeatherEntityFeature.FORECAST_TWICE_DAILY),
    ("daily", WeatherEntityFeature.FORECAST_DAILY),
)

# Skip conditions in priority order: the first that triggers sets the status.
# Moisture (SKIP mode) is applied after these.
_SKIP_PRIORITY: Final = (
    (SkipCondition.RAIN, Status.SKIPPED_RAIN),
    (SkipCondition.FORECAST, Status.SKIPPED_FORECAST),
    (SkipCondition.TEMPERATURE, Status.SKIPPED_TEMPERATURE),
    (SkipCondition.WIND, Status.SKIPPED_WIND),
    (SkipCondition.OCCUPANCY, Status.SKIPPED_OCCUPANCY),
)

_SHORT_TERM = timedelta(minutes=5)
_HOUR = timedelta(hours=1)

# Forecast responses keyed by (entity_id, forecast type), shared by the forecast
# and temperature checks within one async_decide call.
ForecastCache = dict[tuple[str, str], list[dict[str, Any]]]


@dataclass(frozen=True, slots=True)
class CheckResult:
    """One condition's reading.

    triggered: rain, forecast, temperature or wind at/over its limit; for
      moisture, dry (lowest reading below the threshold); for occupancy, an
      occupancy entity is on.
    available: False when the source couldn't be read; triggered is then False
      and details carries a "reason".
    details: JSON-serializable measurements for status attributes and the panel.
    """

    condition: SkipCondition
    triggered: bool
    available: bool
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Decision:
    """Outcome of evaluating a schedule's conditions for one occurrence.

    water: whether to run.
    status: SKIPPED_RAIN / SKIPPED_FORECAST / SKIPPED_MOISTURE when an
      occurrence is skipped; None when watering, or for a quiet no-op (a
      non-schedule day in moisture TRIGGER mode that isn't dry).
    details: JSON-serializable measurements keyed by SkipCondition value.
    retry: True when the skip may clear soon (occupancy DELAY) — the runner
      re-evaluates every OCCUPANCY_RETRY_SECONDS up to the max delay.
    """

    water: bool
    status: Status | None = None
    details: dict[str, Any] = field(default_factory=dict)
    retry: bool = False


def configured_conditions(config: Mapping[str, Any]) -> set[SkipCondition]:
    """Conditions enabled in the config; unknown values are ignored."""
    conditions: set[SkipCondition] = set()
    for value in config.get(CONF_SKIP_CONDITIONS) or []:
        try:
            conditions.add(SkipCondition(value))
        except ValueError:
            _LOGGER.warning("Ignoring unknown skip condition %r", value)
    return conditions


def decide(
    config: Mapping[str, Any],
    scheduled: bool,
    results: Mapping[SkipCondition, CheckResult],
) -> Decision:
    """Apply the watering rules to check results for one occurrence.

    Non-schedule days only water in moisture TRIGGER mode when dry. Any day that
    could water is skipped for rain, forecast, temperature, wind, occupancy, then
    (SKIP mode, schedule days only) moisture — the first match sets the status.
    Results for conditions that aren't configured are reported in details but
    ignored.
    """
    conditions = configured_conditions(config)
    mode = _moisture_mode(config)
    details = {cond.value: dict(result.details) for cond, result in results.items()}
    moisture = results.get(SkipCondition.MOISTURE)

    if not scheduled:
        if SkipCondition.MOISTURE not in conditions or mode is not MoistureMode.TRIGGER:
            return Decision(False, None, details)
        if moisture is None or not (moisture.available and moisture.triggered):
            return Decision(False, None, details)

    for condition, status in _SKIP_PRIORITY:
        if _skips(condition, conditions, results):
            retry = (
                condition is SkipCondition.OCCUPANCY
                and _occupancy_action(config) is OccupancyAction.DELAY
            )
            return Decision(False, status, details, retry)

    if (
        scheduled
        and SkipCondition.MOISTURE in conditions
        and mode is MoistureMode.SKIP
        and moisture is not None
    ):
        if moisture.available and not moisture.triggered:
            return Decision(False, Status.SKIPPED_MOISTURE, details)
        if not moisture.available and _moisture_unavailable(config) is MoistureUnavailable.SKIP:
            details[SkipCondition.MOISTURE.value]["unavailable"] = True
            return Decision(False, Status.SKIPPED_MOISTURE, details)

    return Decision(True, None, details)


async def async_decide(
    hass: HomeAssistant,
    config: Mapping[str, Any],
    now: datetime,
    *,
    scheduled: bool,
    last_watering_end: datetime | None = None,
) -> Decision:
    """Evaluate the configured conditions for an occurrence at `now`.

    `last_watering_end` is the end of the last run that watered, used by the
    rain SINCE_LAST_WATERING window.
    """
    conditions = configured_conditions(config)
    mode = _moisture_mode(config)
    results: dict[SkipCondition, CheckResult] = {}

    if not scheduled:
        # A non-schedule day can only water when TRIGGER mode finds it dry;
        # don't query rain/forecast for an occurrence that can't water.
        if SkipCondition.MOISTURE not in conditions or mode is not MoistureMode.TRIGGER:
            return Decision(False)
        moisture = check_moisture(hass, config)
        results[SkipCondition.MOISTURE] = moisture
        if not (moisture.available and moisture.triggered):
            return decide(config, scheduled, results)
    elif SkipCondition.MOISTURE in conditions and mode is MoistureMode.SKIP:
        results[SkipCondition.MOISTURE] = check_moisture(hass, config)

    if SkipCondition.RAIN in conditions:
        if _enum(RainWindow, config.get(CONF_RAIN_WINDOW), RainWindow.HOURS) is (
            RainWindow.SINCE_LAST_WATERING
        ):
            results[SkipCondition.RAIN] = await async_check_rain(
                hass, config, now, last_watering_end=last_watering_end
            )
        else:
            results[SkipCondition.RAIN] = await async_check_rain(hass, config, now)
    cache: ForecastCache = {}
    if SkipCondition.FORECAST in conditions:
        results[SkipCondition.FORECAST] = await async_check_forecast(
            hass, config, now, cache=cache
        )
    if SkipCondition.TEMPERATURE in conditions:
        results[SkipCondition.TEMPERATURE] = await async_check_temperature(
            hass, config, now, cache=cache
        )
    if SkipCondition.WIND in conditions:
        results[SkipCondition.WIND] = await async_check_wind(hass, config, now)
    if SkipCondition.OCCUPANCY in conditions:
        results[SkipCondition.OCCUPANCY] = check_occupancy(hass, config)
    return decide(config, scheduled, results)


# --- Rain -------------------------------------------------------------------


@callback
def resolve_rain_sensors(config: Mapping[str, Any]) -> list[str]:
    """Configured rain sensors: CONF_RAIN_SENSORS, else the v0.1 single sensor."""
    sensors = [sensor for sensor in config.get(CONF_RAIN_SENSORS) or [] if sensor]
    if sensors:
        return list(dict.fromkeys(sensors))
    single = config.get(CONF_RAIN_SENSOR)
    return [single] if single else []


async def async_station_rain_totals(
    hass: HomeAssistant, entity_ids: list[str], start: datetime, end: datetime
) -> dict[str, float | None]:
    """Rain recorded by each sensor over [start, end); None where there's no data.

    Never raises. Totals are rounded to 4 decimals.
    """
    readings = await _async_station_readings(
        hass, entity_ids, dt_util.as_utc(start), dt_util.as_utc(end)
    )
    return {entity_id: total for entity_id, (total, _source) in readings.items()}


async def async_check_rain(
    hass: HomeAssistant,
    config: Mapping[str, Any],
    now: datetime,
    *,
    last_watering_end: datetime | None = None,
) -> CheckResult:
    """Rain recorded by the rain sensor(s) over the look-back window.

    With several sensors the per-station totals are combined by CONF_RAIN_AGGREGATE.
    Stale protection doesn't apply here: rain gauges only report when rain falls
    (MQTT sensors don't rewrite unchanged values), so an old report isn't a fault.
    """
    sensors = resolve_rain_sensors(config)
    details: dict[str, Any] = {
        "entity_id": sensors[0] if sensors else None,
        "total": None,
        "threshold": None,
        "unit": None,
        "hours": None,
        "source": None,
    }
    try:
        threshold = float(config.get(CONF_RAIN_THRESHOLD, DEFAULT_RAIN_THRESHOLD))
        hours = int(config.get(CONF_RAIN_HOURS, DEFAULT_RAIN_HOURS))
        details.update(threshold=threshold, hours=hours, unit=_unit(hass, details["entity_id"]))
        if not _threshold_ok(threshold):
            return _unavailable(SkipCondition.RAIN, details, "invalid threshold")
        if not sensors:
            return _unavailable(SkipCondition.RAIN, details, "no rain sensor configured")
        if "recorder" not in hass.config.components:
            return _unavailable(SkipCondition.RAIN, details, "recorder not loaded")

        end = dt_util.as_utc(now)
        start = _rain_window_start(config, end, hours, last_watering_end, details)
        readings = await _async_station_readings(hass, sensors, start, end)
    except Exception:  # noqa: BLE001 — a check must never break the run
        _LOGGER.exception("Rain check failed for %s", sensors)
        return _unavailable(SkipCondition.RAIN, details, "error reading rain sensor")

    totals = {eid: total for eid, (total, _source) in readings.items() if total is not None}
    if not totals:
        errored = any(source == "error" for _total, source in readings.values())
        reason = "error reading rain sensor" if errored else "no recorded data"
        return _unavailable(SkipCondition.RAIN, details, reason)

    if len(sensors) == 1:
        total, source = readings[sensors[0]]
        details.update(total=total, source=source)
        return CheckResult(SkipCondition.RAIN, total >= threshold, True, details)

    aggregate = _enum(RainAggregate, config.get(CONF_RAIN_AGGREGATE), RainAggregate.MAX)
    values = list(totals.values())
    over = sum(1 for value in values if value >= threshold)
    details.update(
        aggregate=aggregate.value,
        stations={
            eid: {"total": _num(total), "source": source}
            for eid, (total, source) in readings.items()
        },
        stations_reporting=len(values),
        stations_over=over,
        source=",".join(sorted({src for total, src in readings.values() if total is not None})),
    )
    if aggregate is RainAggregate.MEDIAN:
        total = round(median(values), 4)
        triggered = total >= threshold
    elif aggregate is RainAggregate.QUORUM:
        quorum = max(1, int(config.get(CONF_RAIN_QUORUM, DEFAULT_RAIN_QUORUM)))
        total = max(values)
        details["quorum"] = quorum
        triggered = over >= quorum
    else:
        total = max(values)
        triggered = total >= threshold
    details["total"] = total
    return CheckResult(SkipCondition.RAIN, triggered, True, details)


def _rain_window_start(
    config: Mapping[str, Any],
    end: datetime,
    hours: int,
    last_watering_end: datetime | None,
    details: dict[str, Any],
) -> datetime:
    """Start of the rain look-back window; notes the window in details."""
    window = _enum(RainWindow, config.get(CONF_RAIN_WINDOW), RainWindow.HOURS)
    if window is not RainWindow.SINCE_LAST_WATERING:
        return end - timedelta(hours=hours)

    max_hours = int(config.get(CONF_RAIN_MAX_HOURS, DEFAULT_RAIN_MAX_HOURS))
    details.update(window=window.value, max_hours=max_hours)
    if last_watering_end is None:
        # Nothing has watered yet: fall back to the fixed look-back.
        details["window_fallback"] = True
        start = end - timedelta(hours=hours)
    else:
        start = max(dt_util.as_utc(last_watering_end), end - timedelta(hours=max_hours))
        start = min(start, end)
    details["window_start"] = start.isoformat()
    return start


async def _async_station_readings(
    hass: HomeAssistant, entity_ids: list[str], start: datetime, end: datetime
) -> dict[str, tuple[float | None, str | None]]:
    """(total, source) per sensor; source is "statistics", "history", "error" or None."""
    if "recorder" not in hass.config.components:
        return {entity_id: (None, None) for entity_id in entity_ids}
    instance = get_instance(hass)
    readings: dict[str, tuple[float | None, str | None]] = {}
    for entity_id in entity_ids:
        try:
            total = await instance.async_add_executor_job(
                _statistics_total, hass, entity_id, start, end
            )
            source = "statistics"
            if total is None:
                total = await instance.async_add_executor_job(
                    _history_total, hass, entity_id, start, end
                )
                source = "history"
        except Exception:  # noqa: BLE001 — one bad station mustn't hide the others
            _LOGGER.exception("Reading rain from %s failed", entity_id)
            readings[entity_id] = (None, "error")
            continue
        # Recorder sums are floats; rounding keeps 0.1 + 0.2 from missing a 0.3 threshold.
        readings[entity_id] = (round(total, 4), source) if total is not None else (None, None)
    return readings


def _statistics_total(
    hass: HomeAssistant, entity_id: str, start: datetime, end: datetime
) -> float | None:
    """Sum of statistic changes over [start, end), or None if there are none.

    Runs in the recorder executor. Full hours come from hourly statistics; the
    partial hour at each edge — and any recent hour whose hourly row hasn't
    been compiled yet — come from 5-minute statistics. The leading edge is
    widened to its 5-minute bucket; the 5-minute bucket still in progress at
    `end` isn't compiled yet and so isn't counted.
    """
    found = False
    total = 0.0

    def add(period: str, seg_start: datetime, seg_end: datetime) -> datetime | None:
        """Add a segment's changes; return the end of its last row."""
        nonlocal found, total
        if seg_start >= seg_end:
            return None
        rows = statistics.statistics_during_period(
            hass, seg_start, seg_end, {entity_id}, period, None, {"change"}
        ).get(entity_id, [])
        last_end = None
        for row in rows:
            found = True
            total += row.get("change") or 0.0
            last_end = dt_util.utc_from_timestamp(row["end"])
        return last_end

    start = _floor(start, _SHORT_TERM)
    first_hour = _ceil(start, _HOUR)
    last_hour = _floor(end, _HOUR)
    if first_hour >= last_hour:
        add("5minute", start, end)
    else:
        add("5minute", start, first_hour)
        hourly_end = add("hour", first_hour, last_hour)
        add("5minute", hourly_end or first_hour, end)
    return total if found else None


def _history_total(
    hass: HomeAssistant, entity_id: str, start: datetime, end: datetime
) -> float | None:
    """Sum of increases in recorded states over the window, or None if none are numeric.

    For sensors without statistics. Runs in the recorder executor. A drop is a
    meter reset: the new value counts as rain since the reset.
    """
    states = history.state_changes_during_period(
        hass, start, end, entity_id, no_attributes=True, include_start_time_state=True
    ).get(entity_id, [])
    previous: float | None = None
    total = 0.0
    for state in states:
        value = _as_float(state.state)
        if value is None:
            continue
        if previous is not None:
            total += value - previous if value >= previous else value
        previous = value
    return total if previous is not None else None


# --- Forecast ---------------------------------------------------------------


class _ForecastUnavailable(Exception):
    """A weather entity can't provide a forecast; `reason` says why."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class _EntityForecast:
    available: bool
    triggered: bool
    details: dict[str, Any]


@callback
def resolve_weather_entities(config: Mapping[str, Any]) -> list[str]:
    """Configured weather entities: CONF_WEATHER_ENTITIES, else the v0.1 single entity."""
    entities = [entity for entity in config.get(CONF_WEATHER_ENTITIES) or [] if entity]
    if entities:
        return list(dict.fromkeys(entities))
    single = config.get(CONF_WEATHER_ENTITY)
    return [single] if single else []


async def async_check_forecast(
    hass: HomeAssistant,
    config: Mapping[str, Any],
    now: datetime,
    *,
    cache: ForecastCache | None = None,
) -> CheckResult:
    """Precipitation forecast over the look-ahead window.

    Per weather entity, CONF_FORECAST_MODE decides whether the probability, the
    rain amount, either or both must reach their thresholds. The check triggers
    when at least CONF_FORECAST_QUORUM entities trigger. The amount threshold is
    in Home Assistant's configured precipitation unit.
    """
    entities = resolve_weather_entities(config)
    details: dict[str, Any] = {
        "entity_id": entities[0] if entities else None,
        "max_probability": None,
        "threshold": None,
        "hours": None,
        "forecast_type": None,
        "at": None,
    }
    try:
        threshold = float(config.get(CONF_FORECAST_PROBABILITY, DEFAULT_FORECAST_PROBABILITY))
        hours = int(config.get(CONF_FORECAST_HOURS, DEFAULT_FORECAST_HOURS))
        mode = _enum(ForecastMode, config.get(CONF_FORECAST_MODE), ForecastMode.PROBABILITY)
        details.update(threshold=_num(threshold), hours=hours)
        amount_threshold = math.nan
        if mode is not ForecastMode.PROBABILITY:
            amount_threshold = _as_float(config.get(CONF_FORECAST_AMOUNT)) or math.nan
            details.update(
                mode=mode.value,
                amount_threshold=_num(amount_threshold) if math.isfinite(amount_threshold) else None,
                amount_unit=hass.config.units.accumulated_precipitation_unit,
            )
            if not _threshold_ok(amount_threshold):
                return _unavailable(SkipCondition.FORECAST, details, "invalid threshold")
        if mode is not ForecastMode.AMOUNT and not _threshold_ok(threshold):
            return _unavailable(SkipCondition.FORECAST, details, "invalid threshold")
        if not entities:
            return _unavailable(SkipCondition.FORECAST, details, "no weather entity configured")

        window_start = dt_util.as_utc(now)
        window_end = window_start + timedelta(hours=hours)
        readings = [
            await _async_entity_forecast(
                hass, entity_id, mode, threshold, amount_threshold,
                window_start, window_end, cache,
            )
            for entity_id in entities
        ]
    except Exception:  # noqa: BLE001 — a check must never break the run
        _LOGGER.exception("Forecast check failed for %s", entities)
        return _unavailable(SkipCondition.FORECAST, details, "error reading forecast")

    if len(readings) == 1:
        reading = readings[0]
        details.update(reading.details)
        return CheckResult(SkipCondition.FORECAST, reading.triggered, reading.available, details)

    available = [reading for reading in readings if reading.available]
    triggering = [reading for reading in available if reading.triggered]
    # A quorum larger than the entity count could never be met.
    quorum = min(
        max(1, int(config.get(CONF_FORECAST_QUORUM, DEFAULT_FORECAST_QUORUM))), len(readings)
    )
    probabilities = [
        r.details["max_probability"] for r in available if r.details.get("max_probability") is not None
    ]
    amounts = [r.details["amount"] for r in available if r.details.get("amount") is not None]
    details.update(
        entity_id=None,
        entities={r.details["entity_id"]: r.details for r in readings},
        quorum=quorum,
        entities_available=len(available),
        entities_triggering=len(triggering),
        max_probability=max(probabilities) if probabilities else None,
    )
    if amounts:
        details["amount"] = max(amounts)
    if not available:
        return _unavailable(SkipCondition.FORECAST, details, "no forecast available")
    return CheckResult(SkipCondition.FORECAST, len(triggering) >= quorum, True, details)


async def _async_entity_forecast(
    hass: HomeAssistant,
    entity_id: str,
    mode: ForecastMode,
    probability_threshold: float,
    amount_threshold: float,
    window_start: datetime,
    window_end: datetime,
    cache: ForecastCache | None,
) -> _EntityForecast:
    """One weather entity's reading for the forecast check."""
    details: dict[str, Any] = {
        "entity_id": entity_id,
        "forecast_type": None,
        "max_probability": None,
        "at": None,
    }
    try:
        forecast_type, entries = await _async_get_forecast(hass, entity_id, cache)
    except _ForecastUnavailable as err:
        return _EntityForecast(False, False, {**details, "reason": err.reason})
    except Exception:  # noqa: BLE001 — a check must never break the run
        _LOGGER.exception("Forecast check failed for %s", entity_id)
        return _EntityForecast(False, False, {**details, "reason": "error reading forecast"})

    details["forecast_type"] = forecast_type
    period = FORECAST_PERIODS[forecast_type]
    state = hass.states.get(entity_id)
    from_unit = state.attributes.get(ATTR_WEATHER_PRECIPITATION_UNIT) if state else None
    to_unit = hass.config.units.accumulated_precipitation_unit

    best: tuple[float, datetime] | None = None
    amount: float | None = None
    for entry in entries:
        begins = _parse_time(entry.get(ATTR_FORECAST_TIME))
        if begins is None:
            continue
        overlap = min(begins + period, window_end) - max(begins, window_start)
        if overlap <= timedelta(0):
            continue
        probability = _as_float(entry.get(ATTR_FORECAST_PRECIPITATION_PROBABILITY))
        if probability is not None and (best is None or probability > best[0]):
            best = (probability, begins)
        precipitation = _as_float(entry.get(ATTR_FORECAST_PRECIPITATION))
        if precipitation is not None:
            # A period partly inside the window counts pro rata.
            share = precipitation * (overlap / period)
            amount = (amount or 0.0) + _convert(DistanceConverter, share, from_unit, to_unit)

    if best is not None:
        details.update(max_probability=_num(best[0]), at=best[1].isoformat())
    if amount is not None:
        # Pro-rated floats; rounding keeps 0.6 + 0.2 from missing a 0.8 threshold.
        amount = round(amount, 4)
    probability_available = best is not None
    probability_hit = probability_available and best[0] >= probability_threshold
    amount_available = amount is not None
    amount_hit = amount_available and amount >= amount_threshold
    if mode is not ForecastMode.PROBABILITY:
        details.update(amount=_num(amount), amount_unit=to_unit)

    if mode is ForecastMode.PROBABILITY:
        available, triggered = probability_available, probability_hit
        reason = "no precipitation probability in forecast window"
    elif mode is ForecastMode.AMOUNT:
        available, triggered = amount_available, amount_hit
        reason = "no precipitation amount in forecast window"
    elif mode is ForecastMode.EITHER:
        available = probability_available or amount_available
        triggered = probability_hit or amount_hit
        reason = "no precipitation forecast in window"
    else:
        available = probability_available and amount_available
        triggered = probability_hit and amount_hit
        reason = (
            "no precipitation amount in forecast window"
            if probability_available
            else "no precipitation probability in forecast window"
        )
    if not available:
        details["reason"] = reason
    return _EntityForecast(available, bool(triggered), details)


async def _async_get_forecast(
    hass: HomeAssistant, entity_id: str, cache: ForecastCache | None
) -> tuple[str, list[dict[str, Any]]]:
    """(forecast type, entries) from weather.get_forecasts, finest type first.

    Raises _ForecastUnavailable when the entity is missing or has no forecasts;
    service errors propagate.
    """
    if (state := hass.states.get(entity_id)) is None:
        raise _ForecastUnavailable("weather entity not found")
    features = int(state.attributes.get(ATTR_SUPPORTED_FEATURES) or 0)
    forecast_type = next(
        (name for name, flag in _FORECAST_PREFERENCE if features & flag), None
    )
    if forecast_type is None:
        raise _ForecastUnavailable("weather entity has no forecasts")

    key = (entity_id, forecast_type)
    if cache is not None and key in cache:
        return forecast_type, cache[key]
    response = await hass.services.async_call(
        WEATHER_DOMAIN,
        SERVICE_GET_FORECASTS,
        {"type": forecast_type},
        target={"entity_id": entity_id},
        blocking=True,
        return_response=True,
    )
    forecast = ((response or {}).get(entity_id) or {}).get("forecast") or []
    if cache is not None:
        cache[key] = forecast
    return forecast_type, forecast


# --- Temperature ------------------------------------------------------------


async def async_check_temperature(
    hass: HomeAssistant,
    config: Mapping[str, Any],
    now: datetime,
    *,
    cache: ForecastCache | None = None,
) -> CheckResult:
    """Freeze and heat limits.

    Triggers when the current temperature or the forecast low over the next
    CONF_TEMPERATURE_FORECAST_HOURS is at/below the min, or the current
    temperature is at/above the max. Values are compared in the sensor's unit
    (Home Assistant's temperature unit when there is no sensor); forecast
    temperatures are converted from each weather entity's unit.
    """
    sensor = config.get(CONF_TEMPERATURE_SENSOR)
    minimum = _as_float(config.get(CONF_TEMPERATURE_MIN))
    maximum = _as_float(config.get(CONF_TEMPERATURE_MAX))
    unit = _unit(hass, sensor) or hass.config.units.temperature_unit
    details: dict[str, Any] = {
        "entity_id": sensor,
        "current": None,
        "unit": unit,
        "min": _num(minimum),
        "max": _num(maximum),
        "forecast_low": None,
        "forecast_hours": None,
        "trigger": None,
    }
    current: float | None = None
    forecast_low: float | None = None
    try:
        hours = int(
            config.get(CONF_TEMPERATURE_FORECAST_HOURS, DEFAULT_TEMPERATURE_FORECAST_HOURS)
        )
        details["forecast_hours"] = hours
        if minimum is None and maximum is None:
            return _unavailable(
                SkipCondition.TEMPERATURE, details, "no temperature limits configured"
            )

        if sensor:
            state = hass.states.get(sensor)
            if state is None:
                details["sensor_reason"] = "sensor not found"
            elif _is_stale(state, config, now):
                details["sensor_reason"] = "stale"
            elif (current := _as_float(state.state)) is None:
                details["sensor_reason"] = "no reading"

        entities = resolve_weather_entities(config)
        if minimum is not None and hours > 0 and entities:
            start = dt_util.as_utc(now)
            end = start + timedelta(hours=hours)
            lows: dict[str, Any] = {}
            for entity_id in entities:
                low, reason = await _async_forecast_low(hass, entity_id, start, end, unit, cache)
                lows[entity_id] = {"low": _num(low), "reason": reason}
                if low is not None:
                    forecast_low = low if forecast_low is None else min(forecast_low, low)
            details["forecast"] = lows
    except Exception:  # noqa: BLE001 — a check must never break the run
        _LOGGER.exception("Temperature check failed")
        return _unavailable(SkipCondition.TEMPERATURE, details, "error reading temperature")

    details.update(current=_num(current), forecast_low=_num(forecast_low))
    if current is None and forecast_low is None:
        return _unavailable(SkipCondition.TEMPERATURE, details, "no temperature reading")

    trigger = None
    if minimum is not None and current is not None and current <= minimum:
        trigger = "freeze"
    elif minimum is not None and forecast_low is not None and forecast_low <= minimum:
        trigger = "freeze_forecast"
    elif maximum is not None and current is not None and current >= maximum:
        trigger = "heat"
    details["trigger"] = trigger
    return CheckResult(SkipCondition.TEMPERATURE, trigger is not None, True, details)


async def _async_forecast_low(
    hass: HomeAssistant,
    entity_id: str,
    start: datetime,
    end: datetime,
    unit: str,
    cache: ForecastCache | None,
) -> tuple[float | None, str | None]:
    """Lowest forecast temperature overlapping [start, end) in `unit`, or (None, reason).

    Uses an entry's `templow` when present, else its `temperature` — hourly
    entries and NWS twice_daily night periods only carry `temperature`.
    """
    try:
        forecast_type, entries = await _async_get_forecast(hass, entity_id, cache)
    except _ForecastUnavailable as err:
        return None, err.reason
    except Exception:  # noqa: BLE001 — a check must never break the run
        _LOGGER.exception("Temperature forecast failed for %s", entity_id)
        return None, "error reading forecast"

    state = hass.states.get(entity_id)
    from_unit = state.attributes.get(ATTR_WEATHER_TEMPERATURE_UNIT) if state else None
    period = FORECAST_PERIODS[forecast_type]
    low: float | None = None
    for entry in entries:
        begins = _parse_time(entry.get(ATTR_FORECAST_TIME))
        if begins is None or begins >= end or begins + period <= start:
            continue
        value = _as_float(entry.get(ATTR_FORECAST_TEMP_LOW))
        if value is None:
            value = _as_float(entry.get(ATTR_FORECAST_TEMP))
        if value is None:
            continue
        value = _convert(TemperatureConverter, value, from_unit, unit)
        low = value if low is None else min(low, value)
    if low is None:
        return None, "no temperature in forecast window"
    return round(low, 2), None


# --- Wind -------------------------------------------------------------------


async def async_check_wind(
    hass: HomeAssistant, config: Mapping[str, Any], now: datetime
) -> CheckResult:
    """Average wind over the last CONF_WIND_MINUTES at/above CONF_WIND_MAX.

    The average comes from 5-minute statistics means; a sensor without them
    (or a window with no compiled rows yet) falls back to its current state.
    """
    sensor = config.get(CONF_WIND_SENSOR)
    details: dict[str, Any] = {
        "entity_id": sensor,
        "average": None,
        "max": None,
        "unit": _unit(hass, sensor),
        "minutes": None,
        "source": None,
    }
    average: float | None = None
    source: str | None = None
    try:
        maximum = _as_float(config.get(CONF_WIND_MAX))
        minutes = int(config.get(CONF_WIND_MINUTES, DEFAULT_WIND_MINUTES))
        details.update(max=_num(maximum), minutes=minutes)
        if maximum is None or not _threshold_ok(maximum):
            return _unavailable(SkipCondition.WIND, details, "invalid threshold")
        if not sensor:
            return _unavailable(SkipCondition.WIND, details, "no wind sensor configured")
        # No stale check: a calm MQTT wind sensor stops updating last_reported.
        state = hass.states.get(sensor)

        if "recorder" in hass.config.components and minutes > 0:
            end = dt_util.as_utc(now)
            average = await get_instance(hass).async_add_executor_job(
                _statistics_mean, hass, sensor, end - timedelta(minutes=minutes), end
            )
            source = "statistics"
        if average is None and state is not None:
            average = _as_float(state.state)
            source = "state"
    except Exception:  # noqa: BLE001 — a check must never break the run
        _LOGGER.exception("Wind check failed for %s", sensor)
        return _unavailable(SkipCondition.WIND, details, "error reading wind sensor")

    if average is None:
        return _unavailable(SkipCondition.WIND, details, "no wind reading")
    average = round(average, 2)
    details.update(average=_num(average), source=source)
    return CheckResult(SkipCondition.WIND, average >= maximum, True, details)


def _statistics_mean(
    hass: HomeAssistant, entity_id: str, start: datetime, end: datetime
) -> float | None:
    """Mean of 5-minute statistic means over [start, end), or None. Recorder executor."""
    rows = statistics.statistics_during_period(
        hass, _floor(start, _SHORT_TERM), end, {entity_id}, "5minute", None, {"mean"}
    ).get(entity_id, [])
    means = [row["mean"] for row in rows if row.get("mean") is not None]
    return sum(means) / len(means) if means else None


# --- Occupancy --------------------------------------------------------------


@callback
def occupied_entities(hass: HomeAssistant, config: Mapping[str, Any]) -> list[str]:
    """Configured occupancy entities that are currently on."""
    return [
        entity_id
        for entity_id in _occupancy_entities(config)
        if (state := hass.states.get(entity_id)) is not None and state.state == STATE_ON
    ]


@callback
def check_occupancy(hass: HomeAssistant, config: Mapping[str, Any]) -> CheckResult:
    """Triggers when any occupancy entity is on.

    Entities that are unknown or unavailable don't count as occupied; with no
    readable entity at all the check is unavailable.
    """
    entities = _occupancy_entities(config)
    details: dict[str, Any] = {
        "entities": {},
        "occupied": [],
        "action": _occupancy_action(config).value,
    }
    if not entities:
        return _unavailable(SkipCondition.OCCUPANCY, details, "no occupancy entities configured")
    states = {
        entity_id: state.state if (state := hass.states.get(entity_id)) else None
        for entity_id in entities
    }
    occupied = [entity_id for entity_id, value in states.items() if value == STATE_ON]
    details.update(entities=states, occupied=occupied)
    if all(value in (None, STATE_UNKNOWN, STATE_UNAVAILABLE) for value in states.values()):
        return _unavailable(SkipCondition.OCCUPANCY, details, "no occupancy reading")
    return CheckResult(SkipCondition.OCCUPANCY, bool(occupied), True, details)


def _occupancy_entities(config: Mapping[str, Any]) -> list[str]:
    return list(dict.fromkeys(entity for entity in config.get(CONF_OCCUPANCY_ENTITIES) or [] if entity))


# --- Moisture ---------------------------------------------------------------


@callback
def check_moisture(hass: HomeAssistant, config: Mapping[str, Any]) -> CheckResult:
    """Lowest reading across the moisture sensors; dry when it's below the threshold.

    CONF_STALE_HOURS is not applied: a steady MQTT moisture probe stops updating
    last_reported while it still works (see the module docstring).
    """
    details: dict[str, Any] = {
        "readings": {},
        "lowest": None,
        "lowest_entity": None,
        "threshold": None,
        "unavailable_entities": [],
    }
    try:
        threshold = float(config.get(CONF_MOISTURE_THRESHOLD, DEFAULT_MOISTURE_THRESHOLD))
        details["threshold"] = _num(threshold)
        if not _threshold_ok(threshold):
            return _unavailable(SkipCondition.MOISTURE, details, "invalid threshold")
        readings: dict[str, float | None] = {}
        for entity_id in config.get(CONF_MOISTURE_SENSORS) or []:
            state = hass.states.get(entity_id)
            readings[entity_id] = _as_float(state.state) if state else None
        details["readings"] = {eid: _num(value) for eid, value in readings.items()}
        details["unavailable_entities"] = [eid for eid, value in readings.items() if value is None]

        numeric = {eid: value for eid, value in readings.items() if value is not None}
        if not numeric:
            return _unavailable(SkipCondition.MOISTURE, details, "no moisture reading")
        lowest_entity = min(numeric, key=numeric.__getitem__)
        lowest = numeric[lowest_entity]
    except Exception:  # noqa: BLE001 — a check must never break the run
        _LOGGER.exception("Moisture check failed")
        return _unavailable(SkipCondition.MOISTURE, details, "error reading moisture sensors")

    details.update(lowest=_num(lowest), lowest_entity=lowest_entity)
    return CheckResult(SkipCondition.MOISTURE, lowest < threshold, True, details)


# --- Helpers ----------------------------------------------------------------


def _skips(
    condition: SkipCondition,
    conditions: set[SkipCondition],
    results: Mapping[SkipCondition, CheckResult],
) -> bool:
    result = results.get(condition)
    return (
        condition in conditions
        and result is not None
        and result.available
        and result.triggered
    )


def _enum[E: StrEnum](enum_cls: type[E], value: Any, default: E) -> E:
    """`value` as `enum_cls`, or `default` when it's missing or unknown."""
    if value is None:
        return default
    try:
        return enum_cls(value)
    except ValueError:
        return default


def _moisture_mode(config: Mapping[str, Any]) -> MoistureMode:
    try:
        return MoistureMode(config.get(CONF_MOISTURE_MODE, DEFAULT_MOISTURE_MODE))
    except ValueError:
        return MoistureMode(DEFAULT_MOISTURE_MODE)


def _moisture_unavailable(config: Mapping[str, Any]) -> MoistureUnavailable:
    try:
        return MoistureUnavailable(
            config.get(CONF_MOISTURE_UNAVAILABLE, MoistureUnavailable.WATER)
        )
    except ValueError:
        return MoistureUnavailable.WATER


def _occupancy_action(config: Mapping[str, Any]) -> OccupancyAction:
    return _enum(OccupancyAction, config.get(CONF_OCCUPANCY_ACTION), OccupancyAction.DELAY)


def _is_stale(state: State, config: Mapping[str, Any], now: datetime) -> bool:
    """Whether `state` hasn't been reported within CONF_STALE_HOURS (0/absent = never).

    Temperature sensor only; MQTT sensors with unchanged values don't advance
    last_reported (see the module docstring).
    """
    hours = _as_float(config.get(CONF_STALE_HOURS)) or 0
    if hours <= 0:
        return False
    reported = getattr(state, "last_reported", None) or state.last_updated
    return dt_util.as_utc(now) - reported > timedelta(hours=hours)


def _unavailable(
    condition: SkipCondition, details: dict[str, Any], reason: str
) -> CheckResult:
    return CheckResult(condition, False, False, {**details, "reason": reason})


def _threshold_ok(threshold: float) -> bool:
    """False for a threshold <= 0 or not finite, which makes a check always or never match.

    The wizard enforces a minimum; configs saved before it did may still hold one.
    """
    return math.isfinite(threshold) and threshold > 0


def _convert(converter: Any, value: float, from_unit: str | None, to_unit: str | None) -> float:
    """Convert with a HA unit converter; unknown or equal units pass through."""
    if not from_unit or not to_unit or from_unit == to_unit:
        return value
    try:
        return converter.convert(value, from_unit, to_unit)
    except Exception:  # noqa: BLE001 — an unexpected unit shouldn't break the check
        _LOGGER.warning("Can't convert %s from %s to %s", value, from_unit, to_unit)
        return value


def _unit(hass: HomeAssistant, entity_id: str | None) -> str | None:
    if entity_id and (state := hass.states.get(entity_id)):
        return state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
    return None


def _as_float(value: Any) -> float | None:
    """Finite float from a state or attribute value, else None."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _num(value: float | None) -> float | int | None:
    """Whole floats as ints, so details read 60 rather than 60.0."""
    if value is not None and float(value).is_integer():
        return int(value)
    return value


def _parse_time(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed: datetime | None = value
    elif isinstance(value, str):
        parsed = dt_util.parse_datetime(value)
    else:
        return None
    if parsed is None:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return dt_util.as_utc(parsed)


def _floor(moment: datetime, step: timedelta) -> datetime:
    """Round down to a UTC-aligned multiple of `step`."""
    timestamp = moment.timestamp()
    return dt_util.utc_from_timestamp(timestamp - timestamp % step.total_seconds())


def _ceil(moment: datetime, step: timedelta) -> datetime:
    floored = _floor(moment, step)
    return floored if floored == moment else floored + step
