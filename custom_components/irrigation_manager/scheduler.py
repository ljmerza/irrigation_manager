"""Next-run math for irrigation schedules.

Pure date/time logic with no Home Assistant imports, so it can be unit tested
directly. Home Assistant supplies the sun calculation through ``SunFn`` — a thin
wrapper around ``homeassistant.helpers.sun.get_astral_event_date``, which takes
(event, date) and returns an aware datetime or None when the event does not
occur that day.

Skipping is not handled here: after a run or a skip the runner simply asks for
the next occurrence after the one it just handled, so skips never shift the
cadence. With ``check_every_day`` (moisture "trigger" mode) every day at the
start time is an occurrence, flagged by whether it is a schedule day; the runner
decides whether an unscheduled day waters.
"""
from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, tzinfo
from enum import StrEnum

# (event, local date) -> aware event datetime, or None if the event does not
# occur on that date. Event strings match homeassistant.const.SUN_EVENT_*.
SunFn = Callable[[str, date], datetime | None]

# Days to scan past the start point before giving up. Interval schedules repeat
# at most every 31 days, so this only runs out when the sun event never occurs.
MAX_SEARCH_DAYS = 400


class Frequency(StrEnum):
    """How schedule days are chosen."""

    INTERVAL = "interval"
    WEEKDAYS = "weekdays"


class StartMode(StrEnum):
    """What the start time is based on. Sun values match SUN_EVENT_*."""

    TIME = "time"
    SUNRISE = "sunrise"
    SUNSET = "sunset"


class ZoneMode(StrEnum):
    """Whether a schedule's zones run one after another or together."""

    SEQUENTIAL = "sequential"
    CONCURRENT = "concurrent"


@dataclass(frozen=True, slots=True)
class Schedule:
    """Timing portion of a schedule's config.

    interval_days/anchor apply to INTERVAL: runs on anchor and every
    interval_days after it, never before anchor.
    weekdays applies to WEEKDAYS, using date.weekday() numbering (0=Mon..6=Sun).
    start_time applies to TIME and is a local wall-clock time.
    sun_offset applies to SUNRISE/SUNSET: watering finishes this long before
    the event (negative = after it).
    check_every_day makes every day an occurrence; see next_occurrence.
    """

    frequency: Frequency
    start_mode: StartMode
    interval_days: int = 1
    anchor: date | None = None
    weekdays: frozenset[int] = frozenset()
    start_time: time | None = None
    sun_offset: timedelta = timedelta(0)
    check_every_day: bool = False

    def __post_init__(self) -> None:
        # Config entries store plain strings/lists; coerce so callers can pass
        # stored values straight through.
        object.__setattr__(self, "frequency", Frequency(self.frequency))
        object.__setattr__(self, "start_mode", StartMode(self.start_mode))
        object.__setattr__(self, "weekdays", frozenset(self.weekdays))

        if self.frequency is Frequency.INTERVAL:
            if self.interval_days < 1:
                raise ValueError("interval_days must be >= 1")
            if self.anchor is None:
                raise ValueError("interval schedules need an anchor date")
        else:
            if not self.weekdays:
                raise ValueError("weekday schedules need at least one weekday")
            if not all(0 <= day <= 6 for day in self.weekdays):
                raise ValueError("weekdays must be 0 (Mon) through 6 (Sun)")

        if self.start_mode is StartMode.TIME and self.start_time is None:
            raise ValueError("time schedules need a start_time")

    @property
    def uses_sun(self) -> bool:
        return self.start_mode is not StartMode.TIME


@dataclass(frozen=True, slots=True)
class Occurrence:
    """A start time and whether its day is a schedule day."""

    start: datetime
    scheduled: bool


def total_run_duration(
    zone_durations: Iterable[timedelta], mode: ZoneMode
) -> timedelta:
    """Wall-clock length of one run: sum of zones, or the longest if concurrent."""
    durations = list(zone_durations)
    if not durations:
        return timedelta(0)
    if ZoneMode(mode) is ZoneMode.CONCURRENT:
        return max(durations)
    return sum(durations, timedelta(0))


def runs_on(schedule: Schedule, day: date) -> bool:
    """Whether `day` (local date) is a schedule day."""
    if schedule.frequency is Frequency.INTERVAL:
        assert schedule.anchor is not None
        elapsed = (day - schedule.anchor).days
        return elapsed >= 0 and elapsed % schedule.interval_days == 0
    return day.weekday() in schedule.weekdays


def scheduled_start(
    schedule: Schedule,
    day: date,
    run_duration: timedelta,
    tz: tzinfo,
    sun_fn: SunFn,
) -> datetime | None:
    """Start time for the run belonging to `day`, or None if there isn't one.

    A sun-based start can fall on an earlier calendar day than `day` when the
    run is long — `day` is the day watering finishes. Does not check runs_on.
    """
    if schedule.start_mode is StartMode.TIME:
        assert schedule.start_time is not None
        return _localize(datetime.combine(day, schedule.start_time), tz)

    event = sun_fn(schedule.start_mode.value, day)
    if event is None:
        return None
    start = (event - run_duration - schedule.sun_offset).astimezone(tz)
    # Round down to the minute: tidier times, and still finishes by the event.
    return start.replace(second=0, microsecond=0)


def next_occurrence(
    schedule: Schedule,
    after: datetime,
    run_duration: timedelta,
    tz: tzinfo,
    sun_fn: SunFn,
) -> Occurrence | None:
    """First occurrence strictly after `after`, in `tz`.

    Without check_every_day this is the next scheduled run. With it, every day
    is an occurrence and `scheduled` says whether that day is a schedule day.
    Returns None if nothing is found within MAX_SEARCH_DAYS (only possible when
    the sun event never occurs at this location).
    """
    return _scan(
        schedule, after, run_duration, tz, sun_fn, every_day=schedule.check_every_day
    )


def next_run(
    schedule: Schedule,
    after: datetime,
    run_duration: timedelta,
    tz: tzinfo,
    sun_fn: SunFn,
) -> datetime | None:
    """First scheduled start strictly after `after`, in `tz`.

    Ignores check_every_day. Returns None under the same conditions as
    next_occurrence.
    """
    occurrence = _scan(schedule, after, run_duration, tz, sun_fn, every_day=False)
    return occurrence.start if occurrence else None


def _scan(
    schedule: Schedule,
    after: datetime,
    run_duration: timedelta,
    tz: tzinfo,
    sun_fn: SunFn,
    *,
    every_day: bool,
) -> Occurrence | None:
    if after.tzinfo is None:
        raise ValueError("after must be timezone-aware")

    # A sun start is event - (run + offset). A normal finish-by start falls on
    # or before its schedule day, which the forward scan reaches anyway. A large
    # negative offset pushes the start past its schedule day, so scan back that
    # far (plus a margin for DST/date edges) to catch a run whose day has passed
    # but whose start hasn't. Starts only move forward day to day, so the first
    # hit is the earliest.
    lag = timedelta(0)
    if schedule.uses_sun:
        lag = max(timedelta(0), -(run_duration + schedule.sun_offset))
    day = (after - lag).astimezone(tz).date() - timedelta(days=2)

    for _ in range(MAX_SEARCH_DAYS + lag.days + 3):
        scheduled = runs_on(schedule, day)
        if scheduled or every_day:
            start = scheduled_start(schedule, day, run_duration, tz, sun_fn)
            if start is not None and start > after:
                return Occurrence(start, scheduled)
        day += timedelta(days=1)
    return None


def _localize(naive: datetime, tz: tzinfo) -> datetime:
    """Attach `tz` to a wall-clock time, resolving DST gaps.

    A time skipped by spring-forward (02:30) moves to the real instant after
    the jump (03:30); a repeated fall-back time (01:30) uses its first
    occurrence.
    """
    return naive.replace(tzinfo=tz).astimezone(UTC).astimezone(tz)
