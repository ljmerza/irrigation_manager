"""Next-run scheduling tests.

Pure date/time math — no Home Assistant. The sun is faked with fixed local
times so results are exact; HA supplies the real astral calculation at runtime.
"""
from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from irrigation_manager.scheduler import (
    Frequency,
    Occurrence,
    Schedule,
    StartMode,
    ZoneMode,
    next_occurrence,
    next_run,
    runs_on,
    scheduled_start,
    total_run_duration,
)

TZ = ZoneInfo("America/New_York")
MON, TUE, WED, THU, FRI, SAT, SUN = range(7)

# 2026-09-13 is a Sunday; tests below lean on that.
SUNDAY = date(2026, 9, 13)


def local(y, mo, d, h=0, mi=0, s=0) -> datetime:
    return datetime(y, mo, d, h, mi, s, tzinfo=TZ)


def fake_sun(
    sunrise: time = time(6, 30),
    sunset: time = time(19, 45),
    missing: frozenset[date] = frozenset(),
    utc: bool = False,
):
    """Sun at the same local time every day; `missing` dates have no event."""

    def sun_fn(event: str, day: date) -> datetime | None:
        if day in missing:
            return None
        at = datetime.combine(day, sunrise if event == "sunrise" else sunset, tzinfo=TZ)
        return at.astimezone(UTC) if utc else at

    return sun_fn


def weekly(days, at=time(6, 0)) -> Schedule:
    return Schedule(Frequency.WEEKDAYS, StartMode.TIME, weekdays=frozenset(days), start_time=at)


def test_calendar_assumptions():
    assert SUNDAY.weekday() == SUN
    assert date(2026, 3, 8).weekday() == SUN  # US DST starts
    assert date(2026, 11, 1).weekday() == SUN  # US DST ends


# --- total_run_duration ---------------------------------------------------


def test_total_run_duration_sequential_sums():
    zones = [timedelta(minutes=10), timedelta(minutes=15)]
    assert total_run_duration(zones, ZoneMode.SEQUENTIAL) == timedelta(minutes=25)


def test_total_run_duration_concurrent_takes_longest():
    zones = [timedelta(minutes=10), timedelta(minutes=15)]
    assert total_run_duration(zones, ZoneMode.CONCURRENT) == timedelta(minutes=15)


def test_total_run_duration_accepts_stored_string_mode():
    assert total_run_duration([timedelta(minutes=5)] * 2, "concurrent") == timedelta(minutes=5)


def test_total_run_duration_empty_is_zero():
    assert total_run_duration([], ZoneMode.SEQUENTIAL) == timedelta(0)


# --- Schedule validation --------------------------------------------------


@pytest.mark.parametrize(
    "kwargs",
    [
        {"frequency": "interval", "start_mode": "time", "interval_days": 0,
         "anchor": SUNDAY, "start_time": time(6)},
        {"frequency": "interval", "start_mode": "time", "start_time": time(6)},
        {"frequency": "weekdays", "start_mode": "time", "start_time": time(6)},
        {"frequency": "weekdays", "start_mode": "time", "weekdays": {7},
         "start_time": time(6)},
        {"frequency": "weekdays", "start_mode": "time", "weekdays": {MON}},
        {"frequency": "monthly", "start_mode": "time", "start_time": time(6)},
        {"frequency": "weekdays", "start_mode": "noon", "weekdays": {MON}},
    ],
    ids=["interval-zero", "interval-no-anchor", "no-weekdays", "weekday-7",
         "time-no-start", "bad-frequency", "bad-start-mode"],
)
def test_schedule_rejects_invalid(kwargs):
    with pytest.raises(ValueError):
        Schedule(**kwargs)


def test_schedule_coerces_stored_values():
    schedule = Schedule(frequency="weekdays", start_mode="sunrise", weekdays=[MON, WED])
    assert schedule.frequency is Frequency.WEEKDAYS
    assert schedule.start_mode is StartMode.SUNRISE
    assert schedule.weekdays == frozenset({MON, WED})
    assert schedule.uses_sun


# --- runs_on --------------------------------------------------------------


def test_runs_on_interval_counts_from_anchor_only():
    schedule = Schedule(Frequency.INTERVAL, StartMode.TIME, interval_days=3,
                        anchor=SUNDAY, start_time=time(7))
    assert runs_on(schedule, SUNDAY)
    assert runs_on(schedule, SUNDAY + timedelta(days=3))
    assert not runs_on(schedule, SUNDAY + timedelta(days=1))
    # On-cadence but before the first run date.
    assert not runs_on(schedule, SUNDAY - timedelta(days=3))


def test_runs_on_weekdays():
    schedule = weekly({MON, WED, FRI})
    assert runs_on(schedule, SUNDAY + timedelta(days=1))
    assert not runs_on(schedule, SUNDAY)


# --- next_run: fixed time -------------------------------------------------


def test_weekdays_fixed_time_next_matching_day():
    schedule = weekly({MON, WED, FRI})
    after = local(2026, 9, 13, 12)
    assert next_run(schedule, after, timedelta(0), TZ, fake_sun()) == local(2026, 9, 14, 6)


def test_same_day_start_still_ahead():
    schedule = weekly({MON, WED, FRI})
    after = local(2026, 9, 14, 5)
    assert next_run(schedule, after, timedelta(0), TZ, fake_sun()) == local(2026, 9, 14, 6)


def test_next_run_is_strictly_after():
    schedule = weekly({MON, WED, FRI})
    after = local(2026, 9, 14, 6)
    assert next_run(schedule, after, timedelta(0), TZ, fake_sun()) == local(2026, 9, 16, 6)


def test_interval_fixed_time_keeps_cadence():
    schedule = Schedule(Frequency.INTERVAL, StartMode.TIME, interval_days=3,
                        anchor=SUNDAY, start_time=time(7))
    after = local(2026, 9, 13, 8)
    assert next_run(schedule, after, timedelta(0), TZ, fake_sun()) == local(2026, 9, 16, 7)


def test_interval_before_anchor_returns_anchor():
    schedule = Schedule(Frequency.INTERVAL, StartMode.TIME, interval_days=3,
                        anchor=SUNDAY, start_time=time(7))
    after = local(2026, 9, 1)
    assert next_run(schedule, after, timedelta(0), TZ, fake_sun()) == local(2026, 9, 13, 7)


def test_interval_anchor_far_ahead_is_found():
    anchor = SUNDAY + timedelta(days=300)
    schedule = Schedule(Frequency.INTERVAL, StartMode.TIME, interval_days=31,
                        anchor=anchor, start_time=time(7))
    result = next_run(schedule, local(2026, 9, 13), timedelta(0), TZ, fake_sun())
    assert result == datetime.combine(anchor, time(7), tzinfo=TZ)


def test_utc_after_uses_local_wall_clock():
    schedule = weekly({MON})
    after = local(2026, 9, 13, 12).astimezone(UTC)
    result = next_run(schedule, after, timedelta(0), TZ, fake_sun())
    assert result == local(2026, 9, 14, 6)
    assert result.tzinfo is TZ


def test_naive_after_rejected():
    with pytest.raises(ValueError):
        next_run(weekly({MON}), datetime(2026, 9, 13), timedelta(0), TZ, fake_sun())


# --- next_run: sun, finish-by ---------------------------------------------


def test_sunrise_finishes_by_event_minus_offset():
    schedule = Schedule(Frequency.WEEKDAYS, StartMode.SUNRISE,
                        weekdays=frozenset({MON}), sun_offset=timedelta(minutes=5))
    run = total_run_duration([timedelta(minutes=10), timedelta(minutes=15)], ZoneMode.SEQUENTIAL)
    # sunrise 06:30 - 25 min run - 5 min offset
    assert next_run(schedule, local(2026, 9, 13, 12), run, TZ, fake_sun()) == local(2026, 9, 14, 6, 0)


def test_sunset_with_utc_sun_fn_returns_local():
    schedule = Schedule(Frequency.WEEKDAYS, StartMode.SUNSET, weekdays=frozenset({SUN}))
    result = next_run(schedule, local(2026, 9, 13, 8), timedelta(minutes=20), TZ, fake_sun(utc=True))
    assert result == local(2026, 9, 13, 19, 25)
    assert result.tzinfo is TZ


def test_negative_offset_finishes_after_event():
    schedule = Schedule(Frequency.WEEKDAYS, StartMode.SUNRISE,
                        weekdays=frozenset({MON}), sun_offset=timedelta(minutes=-30))
    result = next_run(schedule, local(2026, 9, 13, 12), timedelta(minutes=10), TZ, fake_sun())
    assert result == local(2026, 9, 14, 6, 50)


def test_large_negative_offset_start_lags_past_schedule_day():
    # Sunday schedule finishing 54 h after sunset: Sun 19:45 + 54 h - 10 min run
    # -> starts Wed 01:35, three calendar days after its schedule day.
    schedule = Schedule(Frequency.WEEKDAYS, StartMode.SUNSET, weekdays=frozenset({SUN}),
                        sun_offset=timedelta(hours=-54))
    result = next_run(schedule, local(2026, 9, 16, 1, 0), timedelta(minutes=10), TZ, fake_sun())
    assert result == local(2026, 9, 16, 1, 35)


def test_sun_start_rounds_down_to_minute():
    schedule = Schedule(Frequency.WEEKDAYS, StartMode.SUNRISE, weekdays=frozenset({MON}))
    sun = fake_sun(sunrise=time(6, 30, 45, 123456))
    result = next_run(schedule, local(2026, 9, 13, 12), timedelta(minutes=10), TZ, sun)
    assert result == local(2026, 9, 14, 6, 20)


def test_long_run_starts_previous_evening():
    # Tuesday schedule, 8 h run finishing by 06:30 sunrise -> starts Mon 22:30.
    schedule = Schedule(Frequency.WEEKDAYS, StartMode.SUNRISE, weekdays=frozenset({TUE}))
    result = next_run(schedule, local(2026, 9, 14, 21), timedelta(hours=8), TZ, fake_sun())
    assert result == local(2026, 9, 14, 22, 30)


def test_long_run_already_started_moves_to_next_week():
    schedule = Schedule(Frequency.WEEKDAYS, StartMode.SUNRISE, weekdays=frozenset({TUE}))
    result = next_run(schedule, local(2026, 9, 14, 23), timedelta(hours=8), TZ, fake_sun())
    assert result == local(2026, 9, 21, 22, 30)


def test_scheduled_start_belongs_to_finish_day():
    schedule = Schedule(Frequency.WEEKDAYS, StartMode.SUNRISE, weekdays=frozenset({TUE}))
    start = scheduled_start(schedule, date(2026, 9, 15), timedelta(hours=8), TZ, fake_sun())
    assert start == local(2026, 9, 14, 22, 30)


def test_missing_sun_event_skips_that_day():
    schedule = Schedule(Frequency.WEEKDAYS, StartMode.SUNRISE, weekdays=frozenset({MON, TUE}))
    sun = fake_sun(missing=frozenset({date(2026, 9, 14)}))
    result = next_run(schedule, local(2026, 9, 13, 12), timedelta(minutes=10), TZ, sun)
    assert result == local(2026, 9, 15, 6, 20)


def test_sun_never_occurs_returns_none():
    schedule = Schedule(Frequency.WEEKDAYS, StartMode.SUNRISE, weekdays=frozenset(range(7)))
    assert next_run(schedule, local(2026, 9, 13), timedelta(minutes=10), TZ, lambda e, d: None) is None


# --- next_occurrence: daily moisture checks ---------------------------------


def test_occurrence_without_daily_check_is_next_scheduled_run():
    schedule = weekly({MON, WED, FRI})
    occurrence = next_occurrence(schedule, local(2026, 9, 13, 12), timedelta(0), TZ, fake_sun())
    assert occurrence == Occurrence(local(2026, 9, 14, 6), scheduled=True)


def test_daily_check_flags_off_schedule_days():
    schedule = Schedule(Frequency.INTERVAL, StartMode.TIME, interval_days=3,
                        anchor=SUNDAY, start_time=time(7), check_every_day=True)
    first = next_occurrence(schedule, local(2026, 9, 13, 8), timedelta(0), TZ, fake_sun())
    second = next_occurrence(schedule, first.start, timedelta(0), TZ, fake_sun())
    third = next_occurrence(schedule, second.start, timedelta(0), TZ, fake_sun())
    assert first == Occurrence(local(2026, 9, 14, 7), scheduled=False)
    assert second == Occurrence(local(2026, 9, 15, 7), scheduled=False)
    assert third == Occurrence(local(2026, 9, 16, 7), scheduled=True)


def test_next_run_ignores_daily_check():
    schedule = Schedule(Frequency.INTERVAL, StartMode.TIME, interval_days=3,
                        anchor=SUNDAY, start_time=time(7), check_every_day=True)
    assert next_run(schedule, local(2026, 9, 13, 8), timedelta(0), TZ, fake_sun()) == local(2026, 9, 16, 7)


def test_daily_check_with_sun_start():
    schedule = Schedule(Frequency.WEEKDAYS, StartMode.SUNRISE, weekdays=frozenset({FRI}),
                        check_every_day=True)
    occurrence = next_occurrence(schedule, local(2026, 9, 13, 12), timedelta(minutes=10), TZ, fake_sun())
    assert occurrence == Occurrence(local(2026, 9, 14, 6, 20), scheduled=False)


# --- DST --------------------------------------------------------------------


def test_spring_forward_gap_time_moves_past_jump():
    schedule = Schedule(Frequency.INTERVAL, StartMode.TIME, interval_days=1,
                        anchor=date(2026, 3, 1), start_time=time(2, 30))
    result = next_run(schedule, local(2026, 3, 8, 0), timedelta(0), TZ, fake_sun())
    assert result.astimezone(UTC) == datetime(2026, 3, 8, 7, 30, tzinfo=UTC)
    # The instant is the same either way; the wall clock must not show 02:30.
    assert (result.hour, result.minute) == (3, 30)
    assert result.utcoffset() == timedelta(hours=-4)


def test_fall_back_repeated_time_uses_first_occurrence():
    schedule = Schedule(Frequency.INTERVAL, StartMode.TIME, interval_days=1,
                        anchor=date(2026, 10, 1), start_time=time(1, 30))
    result = next_run(schedule, local(2026, 11, 1, 0), timedelta(0), TZ, fake_sun())
    assert result.astimezone(UTC) == datetime(2026, 11, 1, 5, 30, tzinfo=UTC)  # 01:30 EDT


def test_daily_across_spring_forward_keeps_wall_clock():
    schedule = Schedule(Frequency.INTERVAL, StartMode.TIME, interval_days=1,
                        anchor=date(2026, 3, 1), start_time=time(6))
    first = next_run(schedule, local(2026, 3, 7, 5), timedelta(0), TZ, fake_sun())
    second = next_run(schedule, first, timedelta(0), TZ, fake_sun())
    assert first == local(2026, 3, 7, 6)  # EST
    assert second == local(2026, 3, 8, 6)  # EDT
    assert (second.hour, second.minute) == (6, 0)
    # Same wall-clock time, but only 23 real hours apart.
    assert second.astimezone(UTC) - first.astimezone(UTC) == timedelta(hours=23)
