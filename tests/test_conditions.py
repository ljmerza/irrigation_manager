"""Skip/trigger condition tests.

`decide` rules are table-tested with synthetic results. The checks run against a
test hass: moisture from states, forecast from a mocked weather.get_forecasts
service, rain from a real recorder (imported statistics and recorded states).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components.recorder.db_schema import StatisticsShortTerm
from homeassistant.components.recorder.statistics import async_import_statistics
from homeassistant.components.recorder import get_instance
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)

from custom_components.irrigation_manager import conditions
from custom_components.irrigation_manager.conditions import (
    CheckResult,
    async_check_forecast,
    async_check_rain,
    async_check_temperature,
    async_check_wind,
    async_decide,
    async_station_rain_totals,
    check_moisture,
    check_occupancy,
    decide,
    occupied_entities,
    resolve_rain_sensors,
    resolve_weather_entities,
)
from custom_components.irrigation_manager.const import (
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
    SkipCondition,
    Status,
)

RAIN = SkipCondition.RAIN
FORECAST = SkipCondition.FORECAST
MOISTURE = SkipCondition.MOISTURE

NOW = datetime(2026, 9, 13, 10, 32, tzinfo=UTC)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let the test hass load integrations from custom_components/."""
    return


# --- decide -------------------------------------------------------------------


def res(condition: SkipCondition, triggered: bool = False, available: bool = True) -> CheckResult:
    return CheckResult(condition, triggered, available, {"marker": condition.value})


RAIN_WET = res(RAIN, triggered=True)
RAIN_DRY = res(RAIN)
RAIN_NA = res(RAIN, available=False)
FC_HIGH = res(FORECAST, triggered=True)
FC_LOW = res(FORECAST)
FC_NA = res(FORECAST, available=False)
DRY = res(MOISTURE, triggered=True)
MOIST = res(MOISTURE)
M_NA = res(MOISTURE, available=False)


def cfg(*enabled: SkipCondition, mode: str = "skip", unavailable: str = "water") -> dict[str, Any]:
    return {
        CONF_SKIP_CONDITIONS: [c.value for c in enabled],
        CONF_MOISTURE_MODE: mode,
        CONF_MOISTURE_UNAVAILABLE: unavailable,
    }


DECIDE_CASES = [
    # id, config, scheduled, results, water, status
    ("sched-no-conditions", cfg(), True, [], True, None),
    ("unsched-no-conditions", cfg(), False, [], False, None),
    ("unsched-moisture-skip-mode-dry", cfg(MOISTURE), False, [DRY], False, None),
    ("unsched-trigger-moist", cfg(MOISTURE, mode="trigger"), False, [MOIST], False, None),
    ("unsched-trigger-unavailable", cfg(MOISTURE, mode="trigger"), False, [M_NA], False, None),
    ("unsched-trigger-missing-result", cfg(MOISTURE, mode="trigger"), False, [], False, None),
    ("unsched-trigger-dry", cfg(MOISTURE, mode="trigger"), False, [DRY], True, None),
    ("unsched-trigger-dry-rain", cfg(MOISTURE, RAIN, mode="trigger"), False,
     [DRY, RAIN_WET], False, Status.SKIPPED_RAIN),
    ("unsched-trigger-dry-forecast", cfg(MOISTURE, FORECAST, mode="trigger"), False,
     [DRY, FC_HIGH], False, Status.SKIPPED_FORECAST),
    ("unsched-trigger-dry-rain-dry", cfg(MOISTURE, RAIN, mode="trigger"), False,
     [DRY, RAIN_DRY], True, None),
    ("sched-skip-moist", cfg(MOISTURE), True, [MOIST], False, Status.SKIPPED_MOISTURE),
    ("sched-skip-dry", cfg(MOISTURE), True, [DRY], True, None),
    ("sched-skip-unavailable-water", cfg(MOISTURE), True, [M_NA], True, None),
    ("sched-skip-unavailable-skip", cfg(MOISTURE, unavailable="skip"), True, [M_NA],
     False, Status.SKIPPED_MOISTURE),
    ("sched-trigger-moist-ignored", cfg(MOISTURE, mode="trigger"), True, [MOIST], True, None),
    ("sched-rain-wet", cfg(RAIN), True, [RAIN_WET], False, Status.SKIPPED_RAIN),
    ("sched-rain-dry", cfg(RAIN), True, [RAIN_DRY], True, None),
    ("sched-rain-unavailable", cfg(RAIN), True, [RAIN_NA], True, None),
    ("sched-forecast-high", cfg(FORECAST), True, [FC_HIGH], False, Status.SKIPPED_FORECAST),
    ("sched-forecast-low", cfg(FORECAST), True, [FC_LOW], True, None),
    ("sched-forecast-unavailable", cfg(FORECAST), True, [FC_NA], True, None),
    ("priority-rain-first", cfg(RAIN, FORECAST, MOISTURE), True,
     [RAIN_WET, FC_HIGH, MOIST], False, Status.SKIPPED_RAIN),
    ("priority-forecast-before-moisture", cfg(RAIN, FORECAST, MOISTURE), True,
     [RAIN_DRY, FC_HIGH, MOIST], False, Status.SKIPPED_FORECAST),
    ("unconfigured-result-ignored", cfg(), True, [RAIN_WET, FC_HIGH], True, None),
]


@pytest.mark.parametrize(
    ("config", "scheduled", "results", "water", "status"),
    [case[1:] for case in DECIDE_CASES],
    ids=[case[0] for case in DECIDE_CASES],
)
async def test_decide(config, scheduled, results, water, status) -> None:
    decision = decide(config, scheduled, {r.condition: r for r in results})
    assert decision.water is water
    assert decision.status == status
    assert set(decision.details) == {r.condition.value for r in results}


async def test_decide_marks_moisture_unavailable_skip() -> None:
    decision = decide(cfg(MOISTURE, unavailable="skip"), True, {MOISTURE: M_NA})
    assert decision.details["moisture"]["unavailable"] is True
    # The frozen check result itself is not mutated.
    assert "unavailable" not in M_NA.details


async def test_decide_ignores_unknown_condition_values() -> None:
    config = {CONF_SKIP_CONDITIONS: ["rain", "hail"]}
    assert decide(config, True, {RAIN: RAIN_WET}).status == Status.SKIPPED_RAIN


# --- async_decide: which checks run -------------------------------------------


@pytest.fixture
def mocked_checks():
    rain = AsyncMock(return_value=RAIN_DRY)
    forecast = AsyncMock(return_value=FC_LOW)
    moisture = MagicMock(return_value=DRY)
    with (
        patch.object(conditions, "async_check_rain", rain),
        patch.object(conditions, "async_check_forecast", forecast),
        patch.object(conditions, "check_moisture", moisture),
    ):
        yield rain, forecast, moisture


ALL = (RAIN, FORECAST, MOISTURE)


async def test_async_decide_unscheduled_without_trigger_queries_nothing(hass, mocked_checks) -> None:
    rain, forecast, moisture = mocked_checks
    decision = await async_decide(hass, cfg(*ALL), NOW, scheduled=False)
    assert decision == conditions.Decision(False)
    rain.assert_not_called()
    forecast.assert_not_called()
    moisture.assert_not_called()


async def test_async_decide_unscheduled_not_dry_skips_weather_queries(hass, mocked_checks) -> None:
    rain, forecast, moisture = mocked_checks
    moisture.return_value = MOIST
    decision = await async_decide(hass, cfg(*ALL, mode="trigger"), NOW, scheduled=False)
    assert (decision.water, decision.status) == (False, None)
    assert set(decision.details) == {"moisture"}
    moisture.assert_called_once()
    rain.assert_not_called()
    forecast.assert_not_called()


async def test_async_decide_unscheduled_dry_checks_everything(hass, mocked_checks) -> None:
    rain, forecast, moisture = mocked_checks
    decision = await async_decide(hass, cfg(*ALL, mode="trigger"), NOW, scheduled=False)
    assert decision.water is True
    assert set(decision.details) == {"rain", "forecast", "moisture"}
    rain.assert_awaited_once_with(hass, cfg(*ALL, mode="trigger"), NOW)
    forecast.assert_awaited_once()


async def test_async_decide_scheduled_trigger_mode_skips_moisture(hass, mocked_checks) -> None:
    rain, forecast, moisture = mocked_checks
    decision = await async_decide(hass, cfg(*ALL, mode="trigger"), NOW, scheduled=True)
    assert decision.water is True
    moisture.assert_not_called()
    rain.assert_awaited_once()
    forecast.assert_awaited_once()


async def test_async_decide_scheduled_skip_mode_checks_all(hass, mocked_checks) -> None:
    rain, forecast, moisture = mocked_checks
    rain.return_value = RAIN_WET
    decision = await async_decide(hass, cfg(*ALL), NOW, scheduled=True)
    assert decision.status == Status.SKIPPED_RAIN
    # Details are complete even though rain alone decides.
    assert set(decision.details) == {"rain", "forecast", "moisture"}
    moisture.assert_called_once()


async def test_async_decide_only_configured_checks(hass, mocked_checks) -> None:
    rain, forecast, moisture = mocked_checks
    await async_decide(hass, cfg(FORECAST), NOW, scheduled=True)
    rain.assert_not_called()
    moisture.assert_not_called()
    forecast.assert_awaited_once()


# --- moisture ---------------------------------------------------------------


def moisture_cfg(*sensors: str, threshold: float = 30) -> dict[str, Any]:
    return {CONF_MOISTURE_SENSORS: list(sensors), CONF_MOISTURE_THRESHOLD: threshold}


async def test_moisture_any_sensor_below_threshold_is_dry(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.bed_a", "45")
    hass.states.async_set("sensor.bed_b", "22.5")
    hass.states.async_set("sensor.bed_c", "60")
    result = check_moisture(hass, moisture_cfg("sensor.bed_a", "sensor.bed_b", "sensor.bed_c"))
    assert (result.triggered, result.available) == (True, True)
    assert result.details["lowest"] == 22.5
    assert result.details["lowest_entity"] == "sensor.bed_b"
    assert result.details["readings"] == {"sensor.bed_a": 45, "sensor.bed_b": 22.5, "sensor.bed_c": 60}


async def test_moisture_all_at_or_above_threshold_is_not_dry(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.bed_a", "30")
    hass.states.async_set("sensor.bed_b", "55")
    result = check_moisture(hass, moisture_cfg("sensor.bed_a", "sensor.bed_b"))
    assert (result.triggered, result.available) == (False, True)
    assert result.details["lowest"] == 30


async def test_moisture_ignores_unusable_readings(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.bed_a", "unavailable")
    hass.states.async_set("sensor.bed_b", "nan")
    hass.states.async_set("sensor.bed_c", "41")
    result = check_moisture(
        hass, moisture_cfg("sensor.bed_a", "sensor.bed_b", "sensor.bed_c", "sensor.missing")
    )
    assert (result.triggered, result.available) == (False, True)
    assert result.details["unavailable_entities"] == ["sensor.bed_a", "sensor.bed_b", "sensor.missing"]
    assert result.details["readings"]["sensor.missing"] is None


async def test_moisture_no_readings_is_unavailable(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.bed_a", "unknown")
    result = check_moisture(hass, moisture_cfg("sensor.bed_a"))
    assert (result.triggered, result.available) == (False, False)
    assert result.details["reason"] == "no moisture reading"


@pytest.mark.parametrize("threshold", [0, float("nan")], ids=["zero", "nan"])
async def test_moisture_invalid_threshold_is_unavailable(hass: HomeAssistant, threshold) -> None:
    hass.states.async_set("sensor.bed_a", "20")
    result = check_moisture(hass, moisture_cfg("sensor.bed_a", threshold=threshold))
    assert (result.triggered, result.available) == (False, False)
    assert result.details["reason"] == "invalid threshold"
    # Follows the moisture_unavailable rule: water by default, skip when set.
    assert decide(cfg(MOISTURE), True, {MOISTURE: result}).water is True
    skipped = decide(cfg(MOISTURE, unavailable="skip"), True, {MOISTURE: result})
    assert (skipped.water, skipped.status) == (False, Status.SKIPPED_MOISTURE)


# --- forecast -----------------------------------------------------------------

WEATHER = "weather.home"
HOURLY_AND_TWICE = 2 | 4
TWICE_DAILY = 4


def forecast_cfg(threshold: int = 60, hours: int = 12) -> dict[str, Any]:
    return {
        CONF_WEATHER_ENTITY: WEATHER,
        CONF_FORECAST_PROBABILITY: threshold,
        CONF_FORECAST_HOURS: hours,
    }


def entry(offset_hours: float, probability: Any) -> dict[str, Any]:
    item: dict[str, Any] = {"datetime": (NOW + timedelta(hours=offset_hours)).isoformat()}
    if probability is not None:
        item["precipitation_probability"] = probability
    return item


@pytest.fixture
def weather(hass: HomeAssistant):
    """Mock weather.get_forecasts; set `forecasts[type]` and `features` per test."""
    calls: list[str] = []
    forecasts: dict[str, list[dict[str, Any]]] = {}

    async def handler(call: ServiceCall):
        calls.append(call.data["type"])
        return {WEATHER: {"forecast": forecasts.get(call.data["type"], [])}}

    hass.services.async_register(
        "weather", "get_forecasts", handler, supports_response=SupportsResponse.ONLY
    )

    def set_features(features: int) -> None:
        hass.states.async_set(WEATHER, "rainy", {"supported_features": features})

    return calls, forecasts, set_features


async def test_forecast_prefers_hourly_and_takes_window_max(hass, weather) -> None:
    calls, forecasts, set_features = weather
    set_features(HOURLY_AND_TWICE)
    forecasts["hourly"] = [
        entry(-1, 99),  # ended exactly at now
        entry(-0.5, 20),  # in progress at now
        entry(3, 70),
        entry(11.5, 40),  # starts inside the window
        entry(12, 100),  # starts exactly at window end
    ]
    result = await async_check_forecast(hass, forecast_cfg(threshold=70), NOW)
    assert calls == ["hourly"]
    assert (result.triggered, result.available) == (True, True)
    assert result.details["max_probability"] == 70
    assert result.details["forecast_type"] == "hourly"
    assert result.details["at"] == (NOW + timedelta(hours=3)).isoformat()


async def test_forecast_below_threshold(hass, weather) -> None:
    _, forecasts, set_features = weather
    set_features(HOURLY_AND_TWICE)
    forecasts["hourly"] = [entry(1, 59), entry(2, 10)]
    result = await async_check_forecast(hass, forecast_cfg(threshold=60), NOW)
    assert (result.triggered, result.available) == (False, True)
    assert result.details["max_probability"] == 59


async def test_forecast_falls_back_to_twice_daily(hass, weather) -> None:
    calls, forecasts, set_features = weather
    set_features(TWICE_DAILY)
    forecasts["twice_daily"] = [
        entry(-12, 95),  # ended at now
        entry(-6, 80),  # 12 h period still running
        entry(18, 90),  # beyond the 12 h window
    ]
    result = await async_check_forecast(hass, forecast_cfg(), NOW)
    assert calls == ["twice_daily"]
    assert (result.triggered, result.available) == (True, True)
    assert result.details["max_probability"] == 80


async def test_forecast_without_probability_is_unavailable(hass, weather) -> None:
    _, forecasts, set_features = weather
    set_features(HOURLY_AND_TWICE)
    forecasts["hourly"] = [entry(1, None), entry(2, None)]
    result = await async_check_forecast(hass, forecast_cfg(), NOW)
    assert (result.triggered, result.available) == (False, False)
    assert "reason" in result.details


async def test_forecast_unsupported_or_missing_entity_is_unavailable(hass, weather) -> None:
    calls, _, set_features = weather
    result = await async_check_forecast(hass, forecast_cfg(), NOW)
    assert result.details["reason"] == "weather entity not found"
    set_features(0)
    result = await async_check_forecast(hass, forecast_cfg(), NOW)
    assert (result.available, result.details["reason"]) == (False, "weather entity has no forecasts")
    assert calls == []


async def test_forecast_service_error_is_unavailable(hass, weather) -> None:
    _, _, set_features = weather
    set_features(HOURLY_AND_TWICE)

    async def failing(call: ServiceCall):
        raise HomeAssistantError("forecast provider down")

    hass.services.async_register(
        "weather", "get_forecasts", failing, supports_response=SupportsResponse.ONLY
    )
    result = await async_check_forecast(hass, forecast_cfg(), NOW)
    assert (result.triggered, result.available) == (False, False)
    assert result.details["reason"] == "error reading forecast"


@pytest.mark.parametrize("threshold", [0, float("nan")], ids=["zero", "nan"])
async def test_forecast_invalid_threshold_is_unavailable(hass, weather, threshold) -> None:
    calls, forecasts, set_features = weather
    set_features(HOURLY_AND_TWICE)
    forecasts["hourly"] = [entry(1, 0), entry(2, 5)]
    result = await async_check_forecast(hass, forecast_cfg(threshold=threshold), NOW)
    assert (result.triggered, result.available) == (False, False)
    assert result.details["reason"] == "invalid threshold"
    assert calls == []
    assert decide(cfg(FORECAST), True, {FORECAST: result}).water is True


# --- rain ---------------------------------------------------------------------

RAIN_SENSOR = "sensor.rain_total"


def rain_cfg(threshold: float = 0.25, hours: int = 24) -> dict[str, Any]:
    return {CONF_RAIN_SENSOR: RAIN_SENSOR, CONF_RAIN_THRESHOLD: threshold, CONF_RAIN_HOURS: hours}


def import_rain(
    hass: HomeAssistant,
    rain: dict[datetime, float],
    first: datetime,
    last_bucket: datetime,
    *,
    skip_hours: set[datetime] = frozenset(),
    sensor: str = RAIN_SENSOR,
) -> None:
    """Import consistent short-term and hourly statistics.

    `rain` maps 5-minute bucket start -> rain in that bucket. Short-term rows
    cover [first, last_bucket]; hourly rows cover every hour fully before
    last_bucket's hour, minus `skip_hours` (not compiled yet).
    """
    metadata = {
        "has_mean": False,
        "has_sum": True,
        "name": None,
        "source": "recorder",
        "statistic_id": sensor,
        "unit_of_measurement": "in",
    }
    step = timedelta(minutes=5)
    cumulative = 0.0
    short_term = []
    sum_at_end: dict[datetime, float] = {}
    bucket = first
    while bucket <= last_bucket:
        cumulative += rain.get(bucket, 0.0)
        short_term.append({"start": bucket, "state": cumulative, "sum": cumulative})
        sum_at_end[bucket + step] = cumulative
        bucket += step

    hourly = []
    hour = first
    while hour + timedelta(hours=1) <= last_bucket:
        if hour not in skip_hours:
            end_sum = sum_at_end[hour + timedelta(hours=1)]
            hourly.append({"start": hour, "state": end_sum, "sum": end_sum})
        hour += timedelta(hours=1)

    get_instance(hass).async_import_statistics(metadata, short_term, StatisticsShortTerm)
    async_import_statistics(hass, metadata, hourly)


class TestRainWithRecorder:
    """Rain checks against a real test recorder.

    phacc requires the recorder before hass, so this class overrides the
    module autouse fixture to request recorder_mock first.
    """

    @pytest.fixture(autouse=True)
    def auto_enable_custom_integrations(self, recorder_mock, enable_custom_integrations):
        return

    async def test_rain_statistics_hours_plus_partial_edges(self, hass: HomeAssistant) -> None:
        # Window: 2026-09-12 10:32 -> 2026-09-13 10:32 (leading edge widened to 10:30).
        hass.states.async_set(RAIN_SENSOR, "3.0", {"unit_of_measurement": "in"})
        rain = {
            datetime(2026, 9, 12, 10, 0, tzinfo=UTC): 0.5,  # before window
            datetime(2026, 9, 12, 10, 25, tzinfo=UTC): 0.2,  # bucket just before the widened edge
            datetime(2026, 9, 12, 10, 35, tzinfo=UTC): 0.1,  # leading partial hour
            datetime(2026, 9, 12, 15, 20, tzinfo=UTC): 0.3,  # full hour
            datetime(2026, 9, 13, 10, 15, tzinfo=UTC): 0.05,  # trailing partial hour
        }
        import_rain(
            hass, rain, datetime(2026, 9, 12, 9, 0, tzinfo=UTC), datetime(2026, 9, 13, 10, 25, tzinfo=UTC)
        )
        await async_wait_recording_done(hass)

        result = await async_check_rain(hass, rain_cfg(threshold=0.45), NOW)
        assert result.available is True
        assert result.details["source"] == "statistics"
        assert result.details["total"] == pytest.approx(0.45)
        assert result.details["unit"] == "in"
        assert result.triggered is True

        below = await async_check_rain(hass, rain_cfg(threshold=0.46), NOW)
        assert below.triggered is False


    @pytest.mark.parametrize("threshold", [0, float("nan")], ids=["zero", "nan"])
    async def test_rain_invalid_threshold_is_unavailable(self, hass: HomeAssistant, threshold) -> None:
        # Recorded data with no rain: without the guard, 0 >= 0 would skip.
        hass.states.async_set(RAIN_SENSOR, "0", {"unit_of_measurement": "in"})
        import_rain(
            hass, {}, datetime(2026, 9, 12, 9, 0, tzinfo=UTC), datetime(2026, 9, 13, 10, 25, tzinfo=UTC)
        )
        await async_wait_recording_done(hass)

        result = await async_check_rain(hass, rain_cfg(threshold=threshold), NOW)
        assert (result.triggered, result.available) == (False, False)
        assert result.details["reason"] == "invalid threshold"
        assert decide(cfg(RAIN), True, {RAIN: result}).water is True

    async def test_rain_statistics_fill_uncompiled_hour_from_short_term(self, hass: HomeAssistant) -> None:
        rain = {
            datetime(2026, 9, 12, 15, 20, tzinfo=UTC): 0.3,
            datetime(2026, 9, 13, 9, 40, tzinfo=UTC): 0.07,  # in the hour not compiled yet
        }
        import_rain(
            hass,
            rain,
            datetime(2026, 9, 12, 9, 0, tzinfo=UTC),
            datetime(2026, 9, 13, 10, 25, tzinfo=UTC),
            skip_hours={datetime(2026, 9, 13, 9, 0, tzinfo=UTC)},
        )
        await async_wait_recording_done(hass)

        result = await async_check_rain(hass, rain_cfg(), NOW)
        assert result.details["source"] == "statistics"
        assert result.details["total"] == pytest.approx(0.37)


    async def test_rain_short_window_uses_only_short_term(self, hass: HomeAssistant) -> None:
        rain = {
            datetime(2026, 9, 13, 9, 25, tzinfo=UTC): 0.4,  # before 1 h window (edge widens to 9:30)
            datetime(2026, 9, 13, 9, 45, tzinfo=UTC): 0.12,
            datetime(2026, 9, 13, 10, 5, tzinfo=UTC): 0.08,
        }
        import_rain(
            hass, rain, datetime(2026, 9, 13, 8, 0, tzinfo=UTC), datetime(2026, 9, 13, 10, 25, tzinfo=UTC)
        )
        await async_wait_recording_done(hass)

        result = await async_check_rain(hass, rain_cfg(hours=1), NOW)
        assert result.details["total"] == pytest.approx(0.2)


    async def test_rain_history_fallback_counts_resets(self, hass: HomeAssistant) -> None:
        sensor = "sensor.daily_rain_no_stats"

        def at(*args: int) -> float:
            return datetime(*args, tzinfo=UTC).timestamp()

        for value, timestamp in [
            ("5.0", at(2026, 9, 12, 9, 0)),  # before window: baseline via start-time state
            ("5.2", at(2026, 9, 12, 12, 0)),
            ("0.0", at(2026, 9, 13, 0, 0)),  # daily reset
            ("0.3", at(2026, 9, 13, 1, 0)),
            ("unavailable", at(2026, 9, 13, 2, 0)),
            ("0.35", at(2026, 9, 13, 3, 0)),
        ]:
            hass.states.async_set(sensor, value, {"unit_of_measurement": "in"}, timestamp=timestamp)
            await async_wait_recording_done(hass)

        config = {CONF_RAIN_SENSOR: sensor, CONF_RAIN_THRESHOLD: 0.5, CONF_RAIN_HOURS: 24}
        result = await async_check_rain(hass, config, NOW)
        assert result.details["source"] == "history"
        assert result.details["total"] == pytest.approx(0.55)
        assert result.triggered is True


    async def test_rain_no_data_is_unavailable(self, hass: HomeAssistant) -> None:
        result = await async_check_rain(hass, rain_cfg(), NOW)
        assert (result.triggered, result.available) == (False, False)
        assert result.details["reason"] == "no recorded data"

    async def test_rain_recorder_error_is_unavailable(self, hass: HomeAssistant) -> None:
        with patch.object(conditions, "_statistics_total", side_effect=RuntimeError("db gone")):
            result = await async_check_rain(hass, rain_cfg(), NOW)
        assert (result.triggered, result.available) == (False, False)
        assert result.details["reason"] == "error reading rain sensor"


async def test_rain_without_recorder_is_unavailable(hass: HomeAssistant) -> None:
    result = await async_check_rain(hass, rain_cfg(), NOW)
    assert (result.available, result.details["reason"]) == (False, "recorder not loaded")


# --- v0.2: decide priority and retry ------------------------------------------

TEMPERATURE = SkipCondition.TEMPERATURE
WIND = SkipCondition.WIND
OCCUPANCY = SkipCondition.OCCUPANCY

TEMP_HIT = res(TEMPERATURE, triggered=True)
TEMP_OK = res(TEMPERATURE)
WIND_HIT = res(WIND, triggered=True)
WIND_OK = res(WIND)
OCC_HIT = res(OCCUPANCY, triggered=True)
OCC_OK = res(OCCUPANCY)
OCC_NA = res(OCCUPANCY, available=False)

V2_DECIDE_CASES = [
    ("temperature", cfg(TEMPERATURE), True, [TEMP_HIT], False, Status.SKIPPED_TEMPERATURE),
    ("temperature-ok", cfg(TEMPERATURE), True, [TEMP_OK], True, None),
    ("wind", cfg(WIND), True, [WIND_HIT], False, Status.SKIPPED_WIND),
    ("occupancy", cfg(OCCUPANCY), True, [OCC_HIT], False, Status.SKIPPED_OCCUPANCY),
    ("occupancy-unavailable-waters", cfg(OCCUPANCY), True, [OCC_NA], True, None),
    ("forecast-before-temperature", cfg(FORECAST, TEMPERATURE), True,
     [FC_HIGH, TEMP_HIT], False, Status.SKIPPED_FORECAST),
    ("temperature-before-wind", cfg(TEMPERATURE, WIND, OCCUPANCY), True,
     [TEMP_HIT, WIND_HIT, OCC_HIT], False, Status.SKIPPED_TEMPERATURE),
    ("wind-before-occupancy", cfg(WIND, OCCUPANCY, MOISTURE), True,
     [WIND_HIT, OCC_HIT, MOIST], False, Status.SKIPPED_WIND),
    ("occupancy-before-moisture", cfg(OCCUPANCY, MOISTURE), True,
     [OCC_HIT, MOIST], False, Status.SKIPPED_OCCUPANCY),
    ("moisture-after-clear-v2", cfg(TEMPERATURE, WIND, OCCUPANCY, MOISTURE), True,
     [TEMP_OK, WIND_OK, OCC_OK, MOIST], False, Status.SKIPPED_MOISTURE),
    ("unsched-trigger-dry-wind", cfg(MOISTURE, WIND, mode="trigger"), False,
     [DRY, WIND_HIT], False, Status.SKIPPED_WIND),
    ("unsched-trigger-moist-temperature", cfg(MOISTURE, TEMPERATURE, mode="trigger"), False,
     [MOIST, TEMP_HIT], False, None),
    ("unconfigured-v2-ignored", cfg(), True, [TEMP_HIT, WIND_HIT, OCC_HIT], True, None),
]


@pytest.mark.parametrize(
    ("config", "scheduled", "results", "water", "status"),
    [case[1:] for case in V2_DECIDE_CASES],
    ids=[case[0] for case in V2_DECIDE_CASES],
)
async def test_decide_v2(config, scheduled, results, water, status) -> None:
    decision = decide(config, scheduled, {r.condition: r for r in results})
    assert decision.water is water
    assert decision.status == status
    assert set(decision.details) == {r.condition.value for r in results}


@pytest.mark.parametrize(
    ("action", "retry"), [(None, True), ("delay", True), ("skip", False), ("bogus", True)]
)
async def test_decide_occupancy_retry_follows_action(action, retry) -> None:
    config = cfg(OCCUPANCY)
    if action is not None:
        config[CONF_OCCUPANCY_ACTION] = action
    decision = decide(config, True, {OCCUPANCY: OCC_HIT})
    assert (decision.status, decision.retry) == (Status.SKIPPED_OCCUPANCY, retry)


async def test_decide_retry_only_when_occupancy_decides() -> None:
    decision = decide(cfg(RAIN, OCCUPANCY), True, {RAIN: RAIN_WET, OCCUPANCY: OCC_HIT})
    assert (decision.status, decision.retry) == (Status.SKIPPED_RAIN, False)


async def test_resolve_sources_prefer_lists_and_fall_back() -> None:
    assert resolve_rain_sensors({CONF_RAIN_SENSOR: "sensor.a"}) == ["sensor.a"]
    assert resolve_rain_sensors(
        {CONF_RAIN_SENSOR: "sensor.a", CONF_RAIN_SENSORS: ["sensor.b", "sensor.b", "sensor.c"]}
    ) == ["sensor.b", "sensor.c"]
    assert resolve_rain_sensors({CONF_RAIN_SENSORS: []}) == []
    assert resolve_weather_entities({CONF_WEATHER_ENTITY: "weather.a"}) == ["weather.a"]
    assert resolve_weather_entities(
        {CONF_WEATHER_ENTITY: "weather.a", CONF_WEATHER_ENTITIES: ["weather.b"]}
    ) == ["weather.b"]


# --- v0.2: async_decide wiring ------------------------------------------------


async def test_async_decide_runs_only_configured_v2_checks(hass, mocked_checks) -> None:
    temperature = AsyncMock(return_value=TEMP_OK)
    wind = AsyncMock(return_value=WIND_OK)
    occupancy = MagicMock(return_value=OCC_OK)
    with (
        patch.object(conditions, "async_check_temperature", temperature),
        patch.object(conditions, "async_check_wind", wind),
        patch.object(conditions, "check_occupancy", occupancy),
    ):
        await async_decide(hass, cfg(RAIN), NOW, scheduled=True)
        temperature.assert_not_called()
        wind.assert_not_called()
        occupancy.assert_not_called()
        decision = await async_decide(hass, cfg(TEMPERATURE, WIND, OCCUPANCY), NOW, scheduled=True)
    assert decision.water is True
    assert set(decision.details) == {"temperature", "wind", "occupancy"}
    temperature.assert_awaited_once()
    wind.assert_awaited_once()
    occupancy.assert_called_once()


async def test_async_decide_passes_last_watering_end_for_since_window(hass, mocked_checks) -> None:
    rain, _, _ = mocked_checks
    config = {**cfg(RAIN), CONF_RAIN_WINDOW: "since_last_watering"}
    last = NOW - timedelta(hours=30)
    await async_decide(hass, config, NOW, scheduled=True, last_watering_end=last)
    rain.assert_awaited_once_with(hass, config, NOW, last_watering_end=last)


async def test_async_decide_occupancy_delay_sets_retry(hass: HomeAssistant) -> None:
    hass.states.async_set("binary_sensor.yard_person", "on")
    config = {**cfg(OCCUPANCY), CONF_OCCUPANCY_ENTITIES: ["binary_sensor.yard_person"]}
    decision = await async_decide(hass, config, NOW, scheduled=True)
    assert (decision.water, decision.status, decision.retry) == (
        False, Status.SKIPPED_OCCUPANCY, True
    )
    assert decision.details["occupancy"]["occupied"] == ["binary_sensor.yard_person"]


# --- v0.2: occupancy ----------------------------------------------------------


async def test_occupancy_any_on_is_occupied(hass: HomeAssistant) -> None:
    hass.states.async_set("binary_sensor.front", "off")
    hass.states.async_set("binary_sensor.back", "on")
    config = {
        CONF_OCCUPANCY_ENTITIES: ["binary_sensor.front", "binary_sensor.back", "binary_sensor.missing"]
    }
    result = check_occupancy(hass, config)
    assert (result.triggered, result.available) == (True, True)
    assert result.details["occupied"] == ["binary_sensor.back"]
    assert result.details["entities"]["binary_sensor.missing"] is None
    assert result.details["action"] == "delay"
    assert occupied_entities(hass, config) == ["binary_sensor.back"]


async def test_occupancy_all_off_is_not_occupied(hass: HomeAssistant) -> None:
    hass.states.async_set("binary_sensor.front", "off")
    result = check_occupancy(hass, {CONF_OCCUPANCY_ENTITIES: ["binary_sensor.front"]})
    assert (result.triggered, result.available) == (False, True)
    assert occupied_entities(hass, {CONF_OCCUPANCY_ENTITIES: ["binary_sensor.front"]}) == []


async def test_occupancy_unreadable_or_unconfigured_is_unavailable(hass: HomeAssistant) -> None:
    hass.states.async_set("binary_sensor.front", "unavailable")
    result = check_occupancy(
        hass, {CONF_OCCUPANCY_ENTITIES: ["binary_sensor.front", "binary_sensor.missing"]}
    )
    assert (result.available, result.details["reason"]) == (False, "no occupancy reading")
    assert check_occupancy(hass, {}).details["reason"] == "no occupancy entities configured"


# --- v0.2: stale_hours doesn't apply to moisture ----------------------------------


async def test_moisture_ignores_stale_hours(hass: HomeAssistant) -> None:
    # A steady MQTT probe doesn't advance last_reported (core skips writing
    # unchanged states), so a 9 h old reading is still a real reading.
    old = (dt_util.utcnow() - timedelta(hours=9)).timestamp()
    hass.states.async_set("sensor.bed_a", "10", timestamp=old)
    hass.states.async_set("sensor.bed_b", "50")
    config = {**moisture_cfg("sensor.bed_a", "sensor.bed_b"), CONF_STALE_HOURS: 6}
    result = check_moisture(hass, config)
    assert (result.triggered, result.available) == (True, True)
    assert result.details["lowest_entity"] == "sensor.bed_a"
    assert "stale_entities" not in result.details

    only_old = check_moisture(hass, {**moisture_cfg("sensor.bed_a"), CONF_STALE_HOURS: 6})
    assert (only_old.available, only_old.triggered) == (True, True)


# --- v0.2: forecast amount, modes and quorum ----------------------------------

HOURLY = 2
DAILY = 1


def fc(offset_hours: float, base: datetime = NOW, **fields: Any) -> dict[str, Any]:
    return {"datetime": (base + timedelta(hours=offset_hours)).isoformat(), **fields}


@pytest.fixture
def weathers(hass: HomeAssistant):
    """Mock weather.get_forecasts for several entities.

    `add(entity_id, features, {type: entries}, **state_attributes)`; `calls`
    records (entity_id, type) per request.
    """
    calls: list[tuple[str, str]] = []
    data: dict[str, dict[str, list[dict[str, Any]]]] = {}

    async def handler(call: ServiceCall):
        entity_ids = call.data["entity_id"]
        if isinstance(entity_ids, str):
            entity_ids = [entity_ids]
        calls.extend((entity_id, call.data["type"]) for entity_id in entity_ids)
        return {
            entity_id: {"forecast": data.get(entity_id, {}).get(call.data["type"], [])}
            for entity_id in entity_ids
        }

    hass.services.async_register(
        "weather", "get_forecasts", handler, supports_response=SupportsResponse.ONLY
    )

    def add(entity_id: str, features: int, forecasts: dict[str, list], **attributes: Any) -> None:
        data[entity_id] = forecasts
        hass.states.async_set(entity_id, "cloudy", {"supported_features": features, **attributes})

    return calls, add


async def test_forecast_amount_sums_window_and_converts_units(hass, weathers) -> None:
    _, add = weathers
    assert hass.config.units.accumulated_precipitation_unit == "mm"
    add(
        "weather.owm",
        HOURLY,
        {"hourly": [fc(-2, precipitation=9), fc(1, precipitation=0.1),
                    fc(3, precipitation=0.2), fc(13, precipitation=5)]},
        precipitation_unit="in",
    )
    config = {
        CONF_WEATHER_ENTITY: "weather.owm",
        CONF_FORECAST_MODE: "amount",
        CONF_FORECAST_AMOUNT: 7.5,
        CONF_FORECAST_HOURS: 12,
    }
    result = await async_check_forecast(hass, config, NOW)
    assert (result.triggered, result.available) == (True, True)
    # 0.3 in -> 7.62 mm; the entries outside the window don't count.
    assert result.details["amount"] == pytest.approx(7.62)
    assert result.details["amount_unit"] == "mm"
    higher = await async_check_forecast(hass, {**config, CONF_FORECAST_AMOUNT: 7.7}, NOW)
    assert higher.triggered is False


async def test_forecast_amount_pro_rates_partial_periods(hass, weathers) -> None:
    _, add = weathers
    add(
        "weather.twice",
        TWICE_DAILY,
        {"twice_daily": [fc(-6, precipitation=1.2), fc(6, precipitation=0.4), fc(18, precipitation=3)]},
    )
    config = {
        CONF_WEATHER_ENTITY: "weather.twice",
        CONF_FORECAST_MODE: "amount",
        CONF_FORECAST_AMOUNT: 0.8,
        CONF_FORECAST_HOURS: 12,
    }
    result = await async_check_forecast(hass, config, NOW)
    # Each 12 h period overlaps the 12 h window by half: 1.2 / 2 + 0.4 / 2.
    assert result.details["amount"] == pytest.approx(0.8)
    assert result.triggered is True


@pytest.mark.parametrize(
    ("mode", "probability", "amount", "triggered"),
    [
        ("either", 10, 2.0, True),
        ("either", 80, 0.1, True),
        ("either", 10, 0.1, False),
        ("both", 80, 0.1, False),
        ("both", 10, 2.0, False),
        ("both", 80, 2.0, True),
        ("probability", 10, 2.0, False),
        ("amount", 10, 2.0, True),
    ],
)
async def test_forecast_modes(hass, weathers, mode, probability, amount, triggered) -> None:
    _, add = weathers
    add("weather.owm", HOURLY,
        {"hourly": [fc(1, precipitation_probability=probability, precipitation=amount)]})
    config = {
        CONF_WEATHER_ENTITY: "weather.owm",
        CONF_FORECAST_MODE: mode,
        CONF_FORECAST_PROBABILITY: 60,
        CONF_FORECAST_AMOUNT: 1.0,
    }
    result = await async_check_forecast(hass, config, NOW)
    assert (result.triggered, result.available) == (triggered, True)


async def test_forecast_both_without_amount_is_unavailable(hass, weathers) -> None:
    _, add = weathers
    # NWS forecasts carry probability but no amount.
    add("weather.krdu", HOURLY, {"hourly": [fc(1, precipitation_probability=90)]})
    config = {CONF_WEATHER_ENTITY: "weather.krdu", CONF_FORECAST_MODE: "both", CONF_FORECAST_AMOUNT: 1.0}
    result = await async_check_forecast(hass, config, NOW)
    assert (result.triggered, result.available) == (False, False)
    assert result.details["reason"] == "no precipitation amount in forecast window"
    either = await async_check_forecast(hass, {**config, CONF_FORECAST_MODE: "either"}, NOW)
    assert (either.triggered, either.available) == (True, True)


async def test_forecast_amount_mode_needs_amount_threshold(hass, weathers) -> None:
    calls, add = weathers
    add("weather.owm", HOURLY, {"hourly": [fc(1, precipitation=5)]})
    for amount in (None, 0):
        config = {CONF_WEATHER_ENTITY: "weather.owm", CONF_FORECAST_MODE: "amount", CONF_FORECAST_AMOUNT: amount}
        result = await async_check_forecast(hass, config, NOW)
        assert (result.available, result.details["reason"]) == (False, "invalid threshold")
    assert calls == []


async def test_forecast_quorum_across_entities(hass, weathers) -> None:
    _, add = weathers
    add("weather.nws", HOURLY, {"hourly": [fc(1, precipitation_probability=80)]})
    add("weather.owm", HOURLY, {"hourly": [fc(1, precipitation_probability=20)]})
    add("weather.tomorrow", HOURLY, {"hourly": [fc(2, precipitation_probability=70)]})
    entities = ["weather.nws", "weather.owm", "weather.tomorrow"]
    base = {CONF_WEATHER_ENTITIES: entities, CONF_FORECAST_PROBABILITY: 60}

    two = await async_check_forecast(hass, {**base, CONF_FORECAST_QUORUM: 2}, NOW)
    assert (two.triggered, two.available) == (True, True)
    assert (two.details["entities_triggering"], two.details["quorum"]) == (2, 2)
    assert two.details["max_probability"] == 80
    assert set(two.details["entities"]) == set(entities)

    three = await async_check_forecast(hass, {**base, CONF_FORECAST_QUORUM: 3}, NOW)
    assert (three.triggered, three.available) == (False, True)
    default = await async_check_forecast(hass, base, NOW)
    assert (default.triggered, default.details["quorum"]) == (True, 1)


async def test_forecast_quorum_ignores_unavailable_and_clamps(hass, weathers) -> None:
    _, add = weathers
    add("weather.nws", HOURLY, {"hourly": [fc(1, precipitation_probability=80)]})
    config = {
        CONF_WEATHER_ENTITIES: ["weather.nws", "weather.gone"],
        CONF_FORECAST_PROBABILITY: 60,
        CONF_FORECAST_QUORUM: 5,
    }
    result = await async_check_forecast(hass, config, NOW)
    # Quorum clamps to the 2 entities; the missing one can't trigger.
    assert (result.triggered, result.available, result.details["quorum"]) == (False, True, 2)
    assert result.details["entities"]["weather.gone"]["reason"] == "weather entity not found"
    one = await async_check_forecast(hass, {**config, CONF_FORECAST_QUORUM: 1}, NOW)
    assert one.triggered is True


async def test_forecast_all_entities_unavailable(hass, weathers) -> None:
    config = {CONF_WEATHER_ENTITIES: ["weather.a", "weather.b"]}
    result = await async_check_forecast(hass, config, NOW)
    assert (result.available, result.details["reason"]) == (False, "no forecast available")


async def test_decide_shares_forecast_between_forecast_and_temperature(hass, weathers) -> None:
    calls, add = weathers
    add("weather.owm", HOURLY,
        {"hourly": [fc(1, precipitation_probability=10, temperature=20)]},
        temperature_unit="°C")
    config = {**cfg(FORECAST, TEMPERATURE), CONF_WEATHER_ENTITY: "weather.owm", CONF_TEMPERATURE_MIN: 2}
    decision = await async_decide(hass, config, NOW, scheduled=True)
    assert decision.water is True
    assert decision.details["temperature"]["forecast_low"] == 20
    assert calls == [("weather.owm", "hourly")]


# --- v0.2: temperature --------------------------------------------------------


async def test_temperature_current_freeze_and_heat(hass: HomeAssistant) -> None:
    config = {
        CONF_TEMPERATURE_SENSOR: "sensor.station_temp",
        CONF_TEMPERATURE_MIN: 32,
        CONF_TEMPERATURE_MAX: 90,
    }
    hass.states.async_set("sensor.station_temp", "31", {"unit_of_measurement": "°F"})
    freeze = await async_check_temperature(hass, config, NOW)
    assert (freeze.triggered, freeze.available, freeze.details["trigger"]) == (True, True, "freeze")
    assert (freeze.details["current"], freeze.details["unit"]) == (31, "°F")

    hass.states.async_set("sensor.station_temp", "32", {"unit_of_measurement": "°F"})
    at_min = await async_check_temperature(hass, config, NOW)
    assert at_min.details["trigger"] == "freeze"

    hass.states.async_set("sensor.station_temp", "95", {"unit_of_measurement": "°F"})
    heat = await async_check_temperature(hass, config, NOW)
    assert (heat.triggered, heat.details["trigger"]) == (True, "heat")

    hass.states.async_set("sensor.station_temp", "70", {"unit_of_measurement": "°F"})
    mild = await async_check_temperature(hass, config, NOW)
    assert (mild.triggered, mild.available, mild.details["trigger"]) == (False, True, None)


async def test_temperature_forecast_low_converted_to_sensor_unit(hass, weathers) -> None:
    _, add = weathers
    hass.states.async_set("sensor.station_temp", "45", {"unit_of_measurement": "°F"})
    add("weather.owm", HOURLY,
        {"hourly": [fc(1, temperature=5), fc(6, temperature=-1), fc(20, temperature=-10)]},
        temperature_unit="°C")
    config = {
        CONF_TEMPERATURE_SENSOR: "sensor.station_temp",
        CONF_TEMPERATURE_MIN: 32,
        CONF_WEATHER_ENTITY: "weather.owm",
        CONF_TEMPERATURE_FORECAST_HOURS: 12,
    }
    result = await async_check_temperature(hass, config, NOW)
    # -1 °C = 30.2 °F within 12 h; the -10 °C entry is beyond the window.
    assert (result.triggered, result.details["trigger"]) == (True, "freeze_forecast")
    assert result.details["forecast_low"] == pytest.approx(30.2)
    colder_limit = await async_check_temperature(hass, {**config, CONF_TEMPERATURE_MIN: 30}, NOW)
    assert colder_limit.triggered is False
    current_only = await async_check_temperature(
        hass, {**config, CONF_TEMPERATURE_FORECAST_HOURS: 0}, NOW
    )
    assert (current_only.triggered, current_only.details["forecast_low"]) == (False, None)


async def test_temperature_forecast_uses_night_periods_and_templow(hass, weathers) -> None:
    _, add = weathers
    add("weather.krdu", TWICE_DAILY,
        {"twice_daily": [fc(-3, temperature=61, is_daytime=True), fc(9, temperature=28, is_daytime=False)]},
        temperature_unit="°F")
    add("weather.tomorrow", DAILY,
        {"daily": [fc(-10, temperature=60, templow=35)]},
        temperature_unit="°F")
    # No sensor: limits are in Home Assistant's unit (°C in tests).
    config = {CONF_TEMPERATURE_MIN: 0, CONF_WEATHER_ENTITIES: ["weather.krdu", "weather.tomorrow"]}
    result = await async_check_temperature(hass, config, NOW)
    assert result.details["unit"] == "°C"
    assert result.details["forecast"]["weather.krdu"]["low"] == pytest.approx(-2.22)
    assert result.details["forecast"]["weather.tomorrow"]["low"] == pytest.approx(1.67)
    assert (result.triggered, result.details["trigger"]) == (True, "freeze_forecast")


async def test_temperature_unavailable_cases(hass, weathers) -> None:
    no_limits = await async_check_temperature(hass, {CONF_TEMPERATURE_SENSOR: "sensor.x"}, NOW)
    assert no_limits.details["reason"] == "no temperature limits configured"

    missing = await async_check_temperature(
        hass, {CONF_TEMPERATURE_SENSOR: "sensor.x", CONF_TEMPERATURE_MIN: 32}, NOW
    )
    assert (missing.available, missing.details["reason"]) == (False, "no temperature reading")
    assert missing.details["sensor_reason"] == "sensor not found"

    # Heat uses the current reading only: forecast temperatures don't count.
    _, add = weathers
    add("weather.owm", HOURLY, {"hourly": [fc(1, temperature=40)]})
    heat_only = await async_check_temperature(
        hass, {CONF_TEMPERATURE_MAX: 30, CONF_WEATHER_ENTITY: "weather.owm"}, NOW
    )
    assert (heat_only.available, heat_only.details["reason"]) == (False, "no temperature reading")


async def test_temperature_stale_sensor_falls_back_to_forecast(hass, weathers) -> None:
    _, add = weathers
    now = dt_util.utcnow()
    old = (now - timedelta(hours=10)).timestamp()
    hass.states.async_set("sensor.station_temp", "-5", {"unit_of_measurement": "°C"}, timestamp=old)
    add("weather.owm", HOURLY, {"hourly": [fc(1, base=now, temperature=8)]})
    config = {
        CONF_TEMPERATURE_SENSOR: "sensor.station_temp",
        CONF_TEMPERATURE_MIN: 1,
        CONF_WEATHER_ENTITY: "weather.owm",
        CONF_STALE_HOURS: 6,
    }
    result = await async_check_temperature(hass, config, now)
    # The stale -5 °C reading is ignored instead of triggering a freeze skip.
    assert result.details["sensor_reason"] == "stale"
    assert (result.details["current"], result.details["forecast_low"]) == (None, 8)
    assert (result.available, result.triggered) == (True, False)


# --- v0.2: wind without recorder ----------------------------------------------


async def test_wind_without_recorder_uses_state_and_validates(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.station_wind", "3", {"unit_of_measurement": "mph"})
    config = {CONF_WIND_SENSOR: "sensor.station_wind", CONF_WIND_MAX: 10}
    result = await async_check_wind(hass, config, NOW)
    assert (result.available, result.triggered, result.details["source"]) == (True, False, "state")
    assert result.details["unit"] == "mph"

    no_max = await async_check_wind(hass, {CONF_WIND_SENSOR: "sensor.station_wind"}, NOW)
    assert no_max.details["reason"] == "invalid threshold"
    no_sensor = await async_check_wind(hass, {CONF_WIND_MAX: 10}, NOW)
    assert no_sensor.details["reason"] == "no wind sensor configured"
    missing = await async_check_wind(hass, {CONF_WIND_SENSOR: "sensor.none", CONF_WIND_MAX: 10}, NOW)
    assert missing.details["reason"] == "no wind reading"


async def test_wind_ignores_stale_hours(hass: HomeAssistant) -> None:
    # A wind sensor stuck at one value (calm, MQTT) doesn't advance last_reported;
    # stale_hours must not turn its reading into "unavailable".
    now = dt_util.utcnow()
    old = (now - timedelta(hours=8)).timestamp()
    hass.states.async_set("sensor.station_wind", "25", {"unit_of_measurement": "mph"}, timestamp=old)
    config = {CONF_WIND_SENSOR: "sensor.station_wind", CONF_WIND_MAX: 10, CONF_STALE_HOURS: 6}
    result = await async_check_wind(hass, config, now)
    assert (result.available, result.triggered) == (True, True)
    assert "reason" not in result.details


# --- v0.2: recorder-backed rain stations and wind -----------------------------


def import_short_term_means(
    hass: HomeAssistant, sensor: str, means: dict[datetime, float], unit: str = "mph"
) -> None:
    metadata = {
        "has_mean": True,
        "has_sum": False,
        "name": None,
        "source": "recorder",
        "statistic_id": sensor,
        "unit_of_measurement": unit,
    }
    rows = [
        {"start": start, "mean": value, "min": value, "max": value}
        for start, value in means.items()
    ]
    get_instance(hass).async_import_statistics(metadata, rows, StatisticsShortTerm)


STATIONS = {"sensor.station_1": 0.1, "sensor.station_2": 0.5, "sensor.station_3": 0.35}


class TestV2WithRecorder:
    """Multi-station rain, rain windows and wind averages against a real recorder."""

    @pytest.fixture(autouse=True)
    def auto_enable_custom_integrations(self, recorder_mock, enable_custom_integrations):
        return

    @staticmethod
    async def stations(hass: HomeAssistant, totals: dict[str, float]) -> None:
        first = datetime(2026, 9, 12, 9, 0, tzinfo=UTC)
        last = datetime(2026, 9, 13, 10, 25, tzinfo=UTC)
        for sensor, amount in totals.items():
            hass.states.async_set(sensor, "1", {"unit_of_measurement": "in"})
            import_rain(hass, {datetime(2026, 9, 13, 8, 0, tzinfo=UTC): amount}, first, last, sensor=sensor)
        await async_wait_recording_done(hass)

    @pytest.mark.parametrize(
        ("aggregate", "extra", "threshold", "total", "triggered"),
        [
            (None, {}, 0.3, 0.5, True),
            ("max", {}, 0.3, 0.5, True),
            ("max", {}, 0.6, 0.5, False),
            ("median", {}, 0.3, 0.35, True),
            ("median", {}, 0.4, 0.35, False),
            ("quorum", {CONF_RAIN_QUORUM: 2}, 0.3, 0.5, True),
            ("quorum", {CONF_RAIN_QUORUM: 3}, 0.3, 0.5, False),
            ("quorum", {}, 0.3, 0.5, True),  # default quorum 2
        ],
        ids=["default-max", "max", "max-below", "median", "median-below",
             "quorum-2", "quorum-3", "quorum-default"],
    )
    async def test_rain_station_aggregates(
        self, hass: HomeAssistant, aggregate, extra, threshold, total, triggered
    ) -> None:
        await self.stations(hass, STATIONS)
        config = {
            CONF_RAIN_SENSORS: list(STATIONS),
            CONF_RAIN_AGGREGATE: aggregate,
            CONF_RAIN_THRESHOLD: threshold,
            CONF_RAIN_HOURS: 24,
            **extra,
        }
        result = await async_check_rain(hass, config, NOW)
        assert result.available is True
        assert result.details["total"] == pytest.approx(total)
        assert result.triggered is triggered
        assert result.details["stations"]["sensor.station_2"]["total"] == pytest.approx(0.5)
        assert result.details["stations_reporting"] == 3
        assert result.details["source"] == "statistics"

    async def test_rain_stations_without_data_are_excluded(self, hass: HomeAssistant) -> None:
        await self.stations(hass, {"sensor.station_1": 0.4})
        config = {
            CONF_RAIN_SENSORS: ["sensor.station_1", "sensor.station_dead"],
            CONF_RAIN_AGGREGATE: "quorum",
            CONF_RAIN_QUORUM: 2,
            CONF_RAIN_THRESHOLD: 0.3,
        }
        result = await async_check_rain(hass, config, NOW)
        assert (result.available, result.triggered) == (True, False)
        assert result.details["stations"]["sensor.station_dead"] == {"total": None, "source": None}
        assert (result.details["stations_reporting"], result.details["stations_over"]) == (1, 1)

        totals = await async_station_rain_totals(
            hass, ["sensor.station_1", "sensor.station_dead"], NOW - timedelta(hours=24), NOW
        )
        assert totals == {"sensor.station_1": pytest.approx(0.4), "sensor.station_dead": None}

    async def test_rain_all_stations_without_data_is_unavailable(self, hass: HomeAssistant) -> None:
        config = {CONF_RAIN_SENSORS: ["sensor.a", "sensor.b"], CONF_RAIN_THRESHOLD: 0.1}
        result = await async_check_rain(hass, config, NOW)
        assert (result.available, result.details["reason"]) == (False, "no recorded data")

    async def test_rain_since_last_watering_window(self, hass: HomeAssistant) -> None:
        hass.states.async_set(RAIN_SENSOR, "1", {"unit_of_measurement": "in"})
        rain = {
            datetime(2026, 9, 12, 20, 0, tzinfo=UTC): 0.4,
            datetime(2026, 9, 13, 8, 0, tzinfo=UTC): 0.1,
        }
        import_rain(hass, rain, datetime(2026, 9, 12, 0, 0, tzinfo=UTC), datetime(2026, 9, 13, 10, 25, tzinfo=UTC))
        await async_wait_recording_done(hass)
        base = {
            CONF_RAIN_SENSOR: RAIN_SENSOR,
            CONF_RAIN_THRESHOLD: 0.3,
            CONF_RAIN_HOURS: 6,
            CONF_RAIN_WINDOW: "since_last_watering",
        }

        since = await async_check_rain(
            hass, {**base, CONF_RAIN_MAX_HOURS: 168}, NOW,
            last_watering_end=datetime(2026, 9, 13, 6, 0, tzinfo=UTC),
        )
        assert since.details["total"] == pytest.approx(0.1)
        assert since.details["window_start"] == "2026-09-13T06:00:00+00:00"
        assert since.triggered is False

        capped = await async_check_rain(
            hass, {**base, CONF_RAIN_MAX_HOURS: 24}, NOW, last_watering_end=NOW - timedelta(days=3)
        )
        assert capped.details["total"] == pytest.approx(0.5)
        assert capped.triggered is True

        fallback = await async_check_rain(hass, base, NOW)
        # Nothing watered yet: the 6 h look-back sees only the 08:00 rain.
        assert fallback.details["window_fallback"] is True
        assert fallback.details["total"] == pytest.approx(0.1)

    async def test_rain_ignores_stale_hours(self, hass: HomeAssistant) -> None:
        # Rain gauges only report when it rains, so stale_hours doesn't apply.
        old = (dt_util.utcnow() - timedelta(days=5)).timestamp()
        hass.states.async_set(RAIN_SENSOR, "2.0", {"unit_of_measurement": "in"}, timestamp=old)
        import_rain(
            hass, {datetime(2026, 9, 13, 8, 0, tzinfo=UTC): 0.3},
            datetime(2026, 9, 12, 9, 0, tzinfo=UTC), datetime(2026, 9, 13, 10, 25, tzinfo=UTC),
        )
        await async_wait_recording_done(hass)
        result = await async_check_rain(hass, {**rain_cfg(), CONF_STALE_HOURS: 1}, NOW)
        assert (result.available, result.details["total"]) == (True, pytest.approx(0.3))

    async def test_wind_average_from_statistics(self, hass: HomeAssistant) -> None:
        sensor = "sensor.station_wind"
        hass.states.async_set(sensor, "2", {"unit_of_measurement": "mph"})
        base = datetime(2026, 9, 13, 10, 0, tzinfo=UTC)
        means = {base - timedelta(minutes=5): 100.0}  # before the 30 min window
        means.update(
            {base + timedelta(minutes=5 * i): value for i, value in enumerate([10, 20, 30, 12, 18, 30])}
        )
        import_short_term_means(hass, sensor, means)
        await async_wait_recording_done(hass)

        config = {CONF_WIND_SENSOR: sensor, CONF_WIND_MAX: 20, CONF_WIND_MINUTES: 30}
        result = await async_check_wind(hass, config, NOW)
        assert (result.details["source"], result.details["average"]) == ("statistics", 20)
        assert (result.triggered, result.details["unit"]) == (True, "mph")
        calmer = await async_check_wind(hass, {**config, CONF_WIND_MAX: 21}, NOW)
        assert calmer.triggered is False

    async def test_wind_falls_back_to_state_without_statistics(self, hass: HomeAssistant) -> None:
        hass.states.async_set("sensor.station_wind", "7.5", {"unit_of_measurement": "mph"})
        config = {CONF_WIND_SENSOR: "sensor.station_wind", CONF_WIND_MAX: 7}
        result = await async_check_wind(hass, config, NOW)
        assert (result.details["source"], result.details["average"], result.triggered) == (
            "state", 7.5, True
        )
