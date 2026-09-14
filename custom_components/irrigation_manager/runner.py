"""Run engine for one irrigation schedule.

One ScheduleRunner per config entry. It schedules the next occurrence, asks
conditions.async_decide whether to water, runs the zones through their drivers,
and persists state so a Home Assistant restart mid-run closes any zone that was
left open. Every zone gets an explicit stop at the end of its time, even when
the device was also given a native duration.

It also owns the schedule's rain delay, pause flag, run/skip history and the
irrigation_manager_event bus events, retries an occurrence while an occupancy
entity is on, and stops a run early when rain starts or someone walks into the
yard (both optional).
"""
from __future__ import annotations

import asyncio
import copy
import logging
import math
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from functools import partial
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    EVENT_CORE_CONFIG_UPDATE,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import (
    async_track_point_in_time,
    async_track_state_change_event,
)
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.storage import Store
from homeassistant.helpers.sun import get_astral_event_date
from homeassistant.util import dt as dt_util

from .conditions import Decision, async_decide
from .const import (
    CONF_ANCHOR,
    CONF_FREQUENCY,
    CONF_INTERVAL_DAYS,
    CONF_INTERVAL_HOURS,
    CONF_MOISTURE_MODE,
    CONF_OCCUPANCY_ENTITIES,
    CONF_OCCUPANCY_MAX_DELAY,
    CONF_OCCUPANCY_STOP_DURING_RUN,
    CONF_RAIN_DELAY_AUTO_HOURS,
    CONF_RAIN_DELAY_MIRROR,
    CONF_RAIN_SENSOR,
    CONF_RAIN_SENSORS,
    CONF_RAIN_STOP_AMOUNT,
    CONF_RAIN_STOP_DURING_RUN,
    CONF_SKIP_CONDITIONS,
    CONF_START_MODE,
    CONF_START_TIME,
    CONF_SUN_OFFSET,
    CONF_WEEKDAYS,
    CONF_WINDOW_END,
    CONF_WINDOW_START,
    CONF_ZONE_ENTITY,
    CONF_ZONE_MINUTES,
    CONF_ZONE_MODE,
    CONF_ZONES,
    DEFAULT_MOISTURE_MODE,
    DEFAULT_OCCUPANCY_MAX_DELAY,
    DEFAULT_RAIN_STOP_AMOUNT,
    DEFAULT_SUN_OFFSET,
    DOMAIN,
    EVENT_IRRIGATION,
    HISTORY_LIMIT,
    MAX_RAIN_DELAY_HOURS,
    MAX_ZONE_MINUTES,
    MIN_ZONE_MINUTES,
    OCCUPANCY_RETRY_SECONDS,
    SIGNAL_SCHEDULES_CHANGED,
    STORAGE_KEY_FMT,
    STORAGE_VERSION,
    EventType,
    MoistureMode,
    SkipCondition,
    Status,
    merged_config,
    zone_entity_ids,
)
from .drivers import ZoneDriver, async_get_driver
from .scheduler import (
    Occurrence,
    Schedule,
    ZoneMode,
    next_occurrence,
    total_run_duration,
)

_LOGGER = logging.getLogger(__name__)

# History records included in snapshot(); history() returns up to HISTORY_LIMIT.
SNAPSHOT_HISTORY = 10

# Early stops that end a run with their own status.
_STOP_STATUSES = (Status.STOPPED_RAIN, Status.STOPPED_OCCUPANCY)

# Delays between retries for a zone whose close failed; the last one repeats.
UNCLOSED_RETRY_DELAYS = (
    timedelta(minutes=1),
    timedelta(minutes=5),
    timedelta(minutes=15),
)


def schedule_from_config(config: Mapping[str, Any]) -> Schedule:
    """Build the scheduler's Schedule from stored config values."""
    anchor = config.get(CONF_ANCHOR)
    start_time = config.get(CONF_START_TIME)
    window_start = config.get(CONF_WINDOW_START)
    window_end = config.get(CONF_WINDOW_END)
    conditions = config.get(CONF_SKIP_CONDITIONS) or []
    moisture_mode = config.get(CONF_MOISTURE_MODE, DEFAULT_MOISTURE_MODE)
    return Schedule(
        frequency=config[CONF_FREQUENCY],
        start_mode=config[CONF_START_MODE],
        interval_days=int(config.get(CONF_INTERVAL_DAYS, 1)),
        anchor=date.fromisoformat(anchor) if anchor else None,
        weekdays=frozenset(int(day) for day in config.get(CONF_WEEKDAYS) or []),
        start_time=time.fromisoformat(start_time) if start_time else None,
        sun_offset=timedelta(
            minutes=float(config.get(CONF_SUN_OFFSET, DEFAULT_SUN_OFFSET))
        ),
        check_every_day=(
            SkipCondition.MOISTURE in conditions
            and moisture_mode == MoistureMode.TRIGGER
        ),
        interval_hours=int(config.get(CONF_INTERVAL_HOURS, 1)),
        window_start=time.fromisoformat(window_start) if window_start else None,
        window_end=time.fromisoformat(window_end) if window_end else None,
    )


def zone_durations(config: Mapping[str, Any]) -> list[tuple[str, timedelta]]:
    """(entity_id, run time) per zone, in configured order."""
    return [
        (zone[CONF_ZONE_ENTITY], timedelta(minutes=float(zone[CONF_ZONE_MINUTES])))
        for zone in config.get(CONF_ZONES) or []
    ]


@dataclass(slots=True)
class _ActiveZone:
    driver: ZoneDriver
    duration: timedelta
    started: datetime | None = None  # None until the start call returns
    ends_at: datetime | None = None


class ScheduleRunner:
    """Scheduling, conditions, zone sequencing and state for one schedule."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.config: dict[str, Any] = merged_config(entry)
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, STORAGE_KEY_FMT.format(entry_id=entry.entry_id)
        )
        self._listeners: list[Callable[[], None]] = []
        self._unsub_timer: CALLBACK_TYPE | None = None
        self._unsub_core_config: CALLBACK_TYPE | None = None
        self._unsub_retry: CALLBACK_TYPE | None = None
        self._unsub_rain_delay: CALLBACK_TYPE | None = None
        self._next: Occurrence | None = None
        self._unloading = False

        # Active run
        self._run_task: asyncio.Task[None] | None = None
        self._run_started: datetime | None = None
        self._run_manual = False
        self._active_zones: dict[str, _ActiveZone] = {}
        self._waiters: set[asyncio.Future[bool]] = set()
        self._stop_reason: Status | None = None
        self._stop_details: dict[str, Any] = {}
        self._busy_skipped = False
        self._recovering_run: dict[str, Any] | None = None
        self._recovery_task: asyncio.Task[None] | None = None
        self._unsub_watchers: list[CALLBACK_TYPE] = []
        self._rain_amount = DEFAULT_RAIN_STOP_AMOUNT
        self._rain_last: dict[str, float | None] = {}
        self._rain_rise: dict[str, float] = {}

        # Zones whose close failed (_unclosed, persisted) are retried on a
        # backoff timer and whenever the entity comes back.
        self._unclosed_attempt = 0
        self._unsub_unclosed_timer: CALLBACK_TYPE | None = None
        self._unsub_unclosed_state: CALLBACK_TYPE | None = None
        self._unclosed_task: asyncio.Task[None] | None = None
        self._closing: set[str] = set()

        # Persisted
        self._enabled = True
        self._paused = False
        self._skip_next = False
        self._status = Status.IDLE
        self._last_status_at: datetime | None = None
        self._last_details: dict[str, Any] = {}
        self._last_run_start: datetime | None = None
        self._last_run_end: datetime | None = None
        self._last_run_total_minutes: float | None = None
        self._last_watering_end: datetime | None = None
        self._zone_results: list[dict[str, Any]] = []
        self._rain_delay_until: datetime | None = None
        self._history: list[dict[str, Any]] = []
        self._unclosed: set[str] = set()

    # --- lifecycle ------------------------------------------------------------

    async def async_setup(self) -> None:
        """Restore state, recover an interrupted run, schedule the next occurrence."""
        data = await self._store.async_load() or {}
        self._restore(data)

        if active_run := data.get("active_run"):
            self._recovering_run = active_run
            self._set_status(
                Status.INTERRUPTED,
                {"interrupted_run_started": active_run.get("started")},
            )
            self._last_run_start = (
                _parse(active_run.get("started")) or self._last_run_start
            )
            self._recovery_task = self.hass.async_create_background_task(
                self._async_recover(active_run),
                name=f"{DOMAIN} recover {self.entry.entry_id}",
            )
        elif not self._enabled:
            self._status = Status.DISABLED

        if self._unclosed:
            # A previous run couldn't close these: try now, then keep retrying.
            self._unclosed_task = self.hass.async_create_background_task(
                self._async_close_unclosed(sorted(self._unclosed)),
                name=f"{DOMAIN} close {self.entry.entry_id}",
            )

        self._unsub_core_config = self.hass.bus.async_listen(
            EVENT_CORE_CONFIG_UPDATE, self._handle_core_config_update
        )
        self._schedule_rain_delay_expiry()
        self._schedule_next(dt_util.now())
        self._notify()

    async def async_unload(self) -> None:
        """Cancel timers; stop an active run and record it as interrupted."""
        self._unloading = True
        self._cancel_timer()
        self._cancel_retry()
        self._cancel_rain_delay_timer()
        self._next = None
        if self._unsub_core_config is not None:
            self._unsub_core_config()
            self._unsub_core_config = None
        if self._recovery_task is not None and not self._recovery_task.done():
            # The stored active_run is kept, so the next setup retries.
            self._recovery_task.cancel()
        if self.running:
            await self._async_request_stop(Status.INTERRUPTED)
        if self.running:
            # The run task was cancelled (Home Assistant cancels background
            # tasks on shutdown) or died before closing its zones. Close them
            # here and finish the run; _unloading blocks rescheduling.
            self._stop_reason = Status.INTERRUPTED
            for entity_id in list(self._active_zones):
                await self._async_stop_zone(entity_id)
            await self._async_finish_run(failed=False)
        self._stop_watchers()
        if self._unclosed_task is not None and not self._unclosed_task.done():
            self._unclosed_task.cancel()
        self._cancel_unclosed_retry()
        if self._unclosed:
            # One more try; zones that still fail stay persisted for the next start.
            await self._async_close_unclosed(sorted(self._unclosed))
        self._listeners.clear()

    async def _async_recover(self, active_run: Mapping[str, Any]) -> None:
        """Close zones left open by a run that Home Assistant restarted during."""
        entity_ids = [
            zone["entity_id"]
            for zone in active_run.get("zones", [])
            if zone.get("entity_id")
        ]
        remaining = await self._async_close(entity_ids)
        if remaining:
            # Zone integrations may still be loading at startup; retry once
            # Home Assistant has started (immediately if it already has).
            started = asyncio.Event()

            @callback
            def _started(_hass: HomeAssistant) -> None:
                started.set()

            unsub = async_at_started(self.hass, _started)
            try:
                await started.wait()
            finally:
                unsub()
            remaining = await self._async_close(remaining)

        if remaining:
            # Keep trying until they close; persisted separately from active_run.
            self._add_unclosed(remaining)
        self._recovering_run = None
        self._recovery_task = None
        await self._async_save()
        self._notify()

    async def _async_close(self, entity_ids: list[str]) -> list[str]:
        """Stop each zone; return the ones that failed.

        Zones a run has opened since are skipped: that run closes them itself.
        """
        failed: list[str] = []
        for entity_id in entity_ids:
            if entity_id in self._active_zones:
                continue
            try:
                await async_get_driver(self.hass, entity_id).async_stop()
            except HomeAssistantError as err:
                _LOGGER.warning("Stopping %s failed: %s", entity_id, err)
                failed.append(entity_id)
        return failed

    # --- scheduling -----------------------------------------------------------

    @callback
    def _schedule_next(self, after: datetime) -> None:
        self._cancel_timer()
        self._next = None
        if not self._enabled or self._unloading:
            return
        try:
            schedule = schedule_from_config(self.config)
            run_duration = total_run_duration(
                (duration for _, duration in zone_durations(self.config)),
                self.config.get(CONF_ZONE_MODE, ZoneMode.SEQUENTIAL),
            )
        except (KeyError, TypeError, ValueError) as err:
            _LOGGER.error("%s: invalid schedule config: %s", self.entry.title, err)
            return

        self._next = next_occurrence(
            schedule, after, run_duration, dt_util.get_default_time_zone(), self._sun
        )
        if self._next is None:
            _LOGGER.warning("%s: no upcoming occurrence", self.entry.title)
            return
        self._unsub_timer = async_track_point_in_time(
            self.hass, partial(self._async_fire, self._next), self._next.start
        )

    @callback
    def _cancel_timer(self) -> None:
        if self._unsub_timer is not None:
            self._unsub_timer()
            self._unsub_timer = None

    @callback
    def _cancel_retry(self) -> None:
        if self._unsub_retry is not None:
            self._unsub_retry()
            self._unsub_retry = None

    @callback
    def _sun(self, event: str, day: date) -> datetime | None:
        return get_astral_event_date(self.hass, event, day)

    @callback
    def _handle_core_config_update(self, _event: Event) -> None:
        # Time zone or location changed: clock times and sun times move.
        self._schedule_next(dt_util.now())
        self._notify()

    async def _async_fire(self, occurrence: Occurrence, _now: datetime) -> None:
        self._unsub_timer = None
        # Queue the following occurrence first so a slow condition check can't
        # lose it.
        self._schedule_next(occurrence.start)
        try:
            await self._async_handle_occurrence(occurrence)
        finally:
            self._notify()

    async def _async_retry(self, occurrence: Occurrence, _now: datetime) -> None:
        self._unsub_retry = None
        try:
            await self._async_handle_occurrence(occurrence)
        finally:
            self._notify()

    async def _async_handle_occurrence(self, occurrence: Occurrence) -> None:
        # A newer occurrence (or this retry) replaces any pending retry.
        self._cancel_retry()
        if not self._enabled or self._unloading or self._paused:
            return
        if self.running:
            self._note_busy(occurrence)
            return
        if (rain_delay_until := self.rain_delay_until) is not None:
            if occurrence.scheduled:
                await self._async_record_skip(
                    Status.SKIPPED_RAIN_DELAY, {"rain_delay_until": _iso(rain_delay_until)}
                )
            return

        decision = await self._async_decide(occurrence.scheduled)

        if not self._enabled or self._unloading or self._paused:
            return
        if self.running:  # a manual run started while conditions were checked
            self._note_busy(occurrence)
            return

        if not decision.water:
            if getattr(decision, "retry", False) and self._schedule_retry(
                occurrence, decision
            ):
                await self._async_save()
                return
            if decision.status is not None:
                await self._async_record_skip(decision.status, decision.details)
                if decision.status is Status.SKIPPED_RAIN:
                    await self._async_auto_rain_delay()
            else:
                self._last_details = dict(decision.details)
                await self._async_save()
            return

        if self._skip_next:
            self._skip_next = False
            await self._async_record_skip(Status.SKIPPED_MANUAL, decision.details)
            return

        self._start_run(zone_durations(self.config), decision.details, manual=False)

    async def _async_decide(self, scheduled: bool) -> Decision:
        try:
            return await async_decide(
                self.hass,
                self.config,
                dt_util.now(),
                scheduled=scheduled,
                last_watering_end=self._last_watering_end,
            )
        except Exception:  # noqa: BLE001
            _LOGGER.exception("%s: checking conditions failed", self.entry.title)
            # Water on schedule days rather than silently never watering; a
            # non-schedule day only waters on a positive moisture check.
            return Decision(water=scheduled, details={"error": "condition check failed"})

    @callback
    def _schedule_retry(self, occurrence: Occurrence, decision: Decision) -> bool:
        """Re-check the occurrence later while occupied; False once the delay is used up."""
        minutes = _as_float(self.config.get(CONF_OCCUPANCY_MAX_DELAY))
        if minutes is None:
            minutes = DEFAULT_OCCUPANCY_MAX_DELAY
        deadline = occurrence.start + timedelta(minutes=max(0.0, minutes))
        retry_at = dt_util.now() + timedelta(seconds=OCCUPANCY_RETRY_SECONDS)
        if retry_at > deadline:
            return False
        self._last_details = {**decision.details, "occupancy_delay_until": _iso(deadline)}
        self._unsub_retry = async_track_point_in_time(
            self.hass, partial(self._async_retry, occurrence), retry_at
        )
        return True

    @callback
    def _note_busy(self, occurrence: Occurrence) -> None:
        if not occurrence.scheduled:
            return
        _LOGGER.info(
            "%s: skipping %s, previous run still active",
            self.entry.title,
            occurrence.start,
        )
        # Status stays RUNNING; it becomes SKIPPED_BUSY when the run ends.
        self._busy_skipped = True
        self._last_details = {
            **self._last_details,
            "skipped_busy_at": _iso(occurrence.start),
        }
        details = {"skipped_busy_at": _iso(occurrence.start)}
        self._add_history(_skip_record(Status.SKIPPED_BUSY, details))
        self._fire(EventType.SKIPPED, status=Status.SKIPPED_BUSY.value, details=details)

    async def _async_record_skip(
        self, status: Status, details: Mapping[str, Any]
    ) -> None:
        self._set_status(status, details)
        self._add_history(_skip_record(status, details))
        self._fire(EventType.SKIPPED, status=status.value, details=copy.deepcopy(dict(details)))
        await self._async_save()

    # --- running --------------------------------------------------------------

    @callback
    def _start_run(
        self,
        zones: list[tuple[str, timedelta]],
        details: Mapping[str, Any],
        *,
        manual: bool,
    ) -> None:
        now = dt_util.now()
        self._cancel_retry()
        self._run_started = now
        self._run_manual = manual
        self._last_run_start = now
        self._zone_results = []
        self._active_zones = {}
        self._stop_reason = None
        self._stop_details = {}
        self._busy_skipped = False
        self._set_status(Status.RUNNING, details)
        concurrent = (
            ZoneMode(self.config.get(CONF_ZONE_MODE, ZoneMode.SEQUENTIAL))
            is ZoneMode.CONCURRENT
        )
        self._start_watchers()
        self._fire(
            EventType.RUN_STARTED,
            manual=manual,
            zones=[entity_id for entity_id, _ in zones],
        )
        self._run_task = self.hass.async_create_background_task(
            self._async_run(zones, concurrent),
            name=f"{DOMAIN} run {self.entry.entry_id}",
        )
        self._notify()

    async def _async_run(
        self, zones: list[tuple[str, timedelta]], concurrent: bool
    ) -> None:
        failed = False
        try:
            if concurrent:
                results = await asyncio.gather(
                    *(self._async_run_zone(entity_id, d) for entity_id, d in zones),
                    return_exceptions=True,
                )
                for result in results:
                    if isinstance(result, Exception):
                        _LOGGER.error(
                            "%s: zone run failed",
                            self.entry.title,
                            exc_info=result,
                        )
                        failed = True
            else:
                for entity_id, duration in zones:
                    if self._stop_reason is not None:
                        break
                    await self._async_run_zone(entity_id, duration)
        except Exception:  # noqa: BLE001
            _LOGGER.exception("%s: run failed", self.entry.title)
            failed = True
        # CancelledError (HA shutting down) skips this on purpose: the stored
        # active_run makes the next startup close the zones.

        for entity_id in list(self._active_zones):
            await self._async_stop_zone(entity_id)
        await self._async_finish_run(failed)

    async def _async_run_zone(self, entity_id: str, duration: timedelta) -> None:
        if self._stop_reason is not None:
            return
        if entity_id in self._unclosed:
            # Left open by an earlier failure: close it first, and don't open a
            # valve that can't be closed.
            await self._async_close_unclosed([entity_id])
            if entity_id in self._unclosed:
                error = "left open earlier and still can't be closed; not started"
                self._zone_results.append(_zone_result(entity_id, 0.0, error))
                self._fire(EventType.ZONE_FINISHED, zone=entity_id, minutes=0.0, error=error)
                await self._async_save()
                self._notify()
                return
        driver = async_get_driver(self.hass, entity_id)
        zone = _ActiveZone(driver, duration)
        # Record the zone before starting it so a crash mid-start still closes
        # it on recovery.
        self._active_zones[entity_id] = zone
        await self._async_save()

        try:
            await driver.async_start(duration)
        except HomeAssistantError as err:
            _LOGGER.warning("Starting %s failed: %s", entity_id, err)
            self._active_zones.pop(entity_id, None)
            self._zone_results.append(_zone_result(entity_id, 0.0, str(err)))
            self._fire(EventType.ZONE_FINISHED, zone=entity_id, minutes=0.0, error=str(err))
            # A failed or timed-out start may still have opened it.
            try:
                await driver.async_stop()
            except HomeAssistantError:
                if _is_available(self.hass, entity_id):
                    # The start reached the device; keep retrying the close.
                    self._add_unclosed([entity_id])
            await self._async_save()
            self._notify()
            return

        zone.started = dt_util.utcnow()
        zone.ends_at = zone.started + duration
        self._fire(EventType.ZONE_STARTED, zone=entity_id, ends_at=_iso(zone.ends_at))
        await self._async_save()
        self._notify()

        await self._async_wait_until(zone.ends_at)
        await self._async_stop_zone(entity_id)

    async def _async_wait_until(self, when: datetime) -> bool:
        """Wait until `when`; return False early if the run is being stopped."""
        if self._stop_reason is not None:
            return False
        waiter: asyncio.Future[bool] = self.hass.loop.create_future()

        @callback
        def _reached(_now: datetime) -> None:
            if not waiter.done():
                waiter.set_result(True)

        unsub = async_track_point_in_time(self.hass, _reached, when)
        self._waiters.add(waiter)
        try:
            return await waiter
        finally:
            unsub()
            self._waiters.discard(waiter)

    async def _async_stop_zone(self, entity_id: str) -> None:
        zone = self._active_zones.get(entity_id)
        if zone is None:
            return
        error: str | None = None
        try:
            await zone.driver.async_stop()
        except HomeAssistantError as err:
            _LOGGER.error("Stopping %s failed: %s", entity_id, err)
            error = str(err)
        # Only forget the zone once the stop was attempted, so a crash during
        # the stop call still closes it on recovery. A failed stop hands the
        # zone to the unclosed-zone retries, which are persisted too.
        self._active_zones.pop(entity_id, None)
        if error is not None:
            self._add_unclosed([entity_id])
        minutes = 0.0
        if zone.started is not None:
            minutes = round((dt_util.utcnow() - zone.started).total_seconds() / 60, 1)
        self._zone_results.append(_zone_result(entity_id, minutes, error))
        self._fire(EventType.ZONE_FINISHED, zone=entity_id, minutes=minutes, error=error)
        await self._async_save()
        self._notify()

    async def _async_finish_run(self, failed: bool) -> None:
        self._stop_watchers()
        errored = failed or any(result["error"] for result in self._zone_results)
        if self._stop_reason is Status.INTERRUPTED:
            outcome = Status.INTERRUPTED
        elif self._stop_reason in _STOP_STATUSES:
            outcome = self._stop_reason
        elif errored:
            outcome = Status.ERROR
        else:
            outcome = Status.IDLE

        if outcome is not Status.IDLE:
            status = outcome
        elif self._busy_skipped:
            status = Status.SKIPPED_BUSY
        else:
            status = self._idle_status()
        if self._unclosed:
            status = Status.ERROR  # a zone may still be open

        details = {**self._last_details, **self._stop_details} if self._stop_details else None
        self._set_status(status, details)
        end = dt_util.now()
        total = round(sum(result["minutes"] for result in self._zone_results), 1)
        self._last_run_end = end
        self._last_run_total_minutes = total
        if total > 0:
            self._last_watering_end = end
        self._add_history(
            {
                "at": _iso(end),
                "type": "run",
                "status": outcome.value,
                "manual": self._run_manual,
                "started": _iso(self._run_started),
                "zones": self.zone_results,
                "total_minutes": total,
                "details": copy.deepcopy(self._last_details),
            }
        )
        self._fire(EventType.RUN_FINISHED, status=outcome.value, total_minutes=total)

        self._run_started = None
        self._run_task = None
        self._run_manual = False
        self._stop_reason = None
        self._stop_details = {}
        self._busy_skipped = False
        await self._async_save()
        self._schedule_next(dt_util.now())
        self._notify()

    async def _async_request_stop(self, reason: Status) -> None:
        self._signal_stop(reason)
        task = self._run_task
        if task is not None and not task.done() and task is not asyncio.current_task():
            await asyncio.wait([task])

    @callback
    def _signal_stop(
        self, reason: Status, details: Mapping[str, Any] | None = None
    ) -> None:
        """Wake the run so it closes its zones. The first early stop reason wins;
        only an unload (INTERRUPTED) replaces it."""
        if self._stop_reason is None or reason is Status.INTERRUPTED:
            self._stop_reason = reason
            if details:
                self._stop_details = dict(details)
        for waiter in list(self._waiters):
            if not waiter.done():
                waiter.set_result(False)

    # --- run watchers (rain, occupancy) ---------------------------------------

    @callback
    def _start_watchers(self, *, keep_progress: bool = False) -> None:
        """Watch rain and occupancy for the active run.

        keep_progress (a config change mid-run) keeps the rain already counted
        for sensors that are still configured; new sensors start from now.
        """
        previous_last, previous_rise = self._rain_last, self._rain_rise
        self._stop_watchers()
        config = self.config
        if config.get(CONF_RAIN_STOP_DURING_RUN):
            sensors = _rain_sensors(config)
            amount = _as_float(config.get(CONF_RAIN_STOP_AMOUNT, DEFAULT_RAIN_STOP_AMOUNT))
            if sensors and amount is not None and amount > 0:
                self._rain_amount = amount
                self._rain_last = {
                    entity_id: (
                        previous_last[entity_id]
                        if keep_progress and entity_id in previous_last
                        else _state_float(self.hass, entity_id)
                    )
                    for entity_id in sensors
                }
                self._rain_rise = {
                    entity_id: previous_rise.get(entity_id, 0.0) if keep_progress else 0.0
                    for entity_id in sensors
                }
                self._unsub_watchers.append(
                    async_track_state_change_event(
                        self.hass, sensors, self._handle_rain_change
                    )
                )
            elif sensors:
                _LOGGER.warning(
                    "%s: rain stop amount must be above 0; not watching rain",
                    self.entry.title,
                )
        if config.get(CONF_OCCUPANCY_STOP_DURING_RUN):
            entities = [entity_id for entity_id in config.get(CONF_OCCUPANCY_ENTITIES) or [] if entity_id]
            if entities:
                self._unsub_watchers.append(
                    async_track_state_change_event(
                        self.hass, entities, self._handle_occupancy_change
                    )
                )

    @callback
    def _stop_watchers(self) -> None:
        for unsub in self._unsub_watchers:
            unsub()
        self._unsub_watchers.clear()
        self._rain_last = {}
        self._rain_rise = {}

    @callback
    def _handle_rain_change(self, event: Event) -> None:
        if not self.running or self._stop_reason is not None:
            return
        entity_id: str = event.data["entity_id"]
        new_state = event.data.get("new_state")
        value = _as_float(new_state.state) if new_state is not None else None
        if value is None:
            return
        last = self._rain_last.get(entity_id)
        self._rain_last[entity_id] = value
        if last is None:
            # First numeric reading since the run started becomes the baseline.
            return
        # Compare the sensor only with itself; a drop is a meter reset.
        rise = value - last if value >= last else value
        total = round(self._rain_rise.get(entity_id, 0.0) + rise, 4)
        self._rain_rise[entity_id] = total
        if total >= self._rain_amount:
            _LOGGER.info(
                "%s: stopping, %s rose %s since the run started",
                self.entry.title,
                entity_id,
                total,
            )
            self._signal_stop(
                Status.STOPPED_RAIN,
                {"rain_stop": {"entity_id": entity_id, "rise": total, "amount": self._rain_amount}},
            )

    @callback
    def _handle_occupancy_change(self, event: Event) -> None:
        if not self.running or self._stop_reason is not None:
            return
        new_state = event.data.get("new_state")
        old_state = event.data.get("old_state")
        if new_state is None or new_state.state != STATE_ON:
            return
        if old_state is not None and old_state.state == STATE_ON:
            return
        _LOGGER.info("%s: stopping, %s is on", self.entry.title, event.data["entity_id"])
        self._signal_stop(
            Status.STOPPED_OCCUPANCY,
            {"occupancy_stop": {"entity_id": event.data["entity_id"]}},
        )

    # --- zones left open ------------------------------------------------------

    @callback
    def _add_unclosed(self, entity_ids: Iterable[str]) -> None:
        """Track zones whose close failed; they're retried until they close."""
        new = sorted(set(entity_ids) - self._unclosed)
        if not new:
            return
        if not self._unclosed:
            self._unclosed_attempt = 0
        self._unclosed.update(new)
        _LOGGER.error(
            "%s: could not close %s; retrying until it closes",
            self.entry.title,
            ", ".join(new),
        )
        if not self.running:
            self._set_status(Status.ERROR)
        self._arm_unclosed_retry()

    @callback
    def _arm_unclosed_retry(self) -> None:
        """(Re)arm the backoff timer and the state watcher for unclosed zones."""
        self._cancel_unclosed_retry()
        if not self._unclosed or self._unloading:
            return
        delay = UNCLOSED_RETRY_DELAYS[
            min(self._unclosed_attempt, len(UNCLOSED_RETRY_DELAYS) - 1)
        ]
        self._unsub_unclosed_timer = async_track_point_in_time(
            self.hass, self._async_unclosed_timer, dt_util.utcnow() + delay
        )
        self._unsub_unclosed_state = async_track_state_change_event(
            self.hass, sorted(self._unclosed), self._handle_unclosed_state
        )

    @callback
    def _cancel_unclosed_retry(self) -> None:
        if self._unsub_unclosed_timer is not None:
            self._unsub_unclosed_timer()
            self._unsub_unclosed_timer = None
        if self._unsub_unclosed_state is not None:
            self._unsub_unclosed_state()
            self._unsub_unclosed_state = None

    async def _async_unclosed_timer(self, _now: datetime) -> None:
        self._unsub_unclosed_timer = None
        self._unclosed_attempt += 1
        await self._async_close_unclosed(sorted(self._unclosed))

    @callback
    def _handle_unclosed_state(self, event: Event) -> None:
        """Retry right away when an unclosed zone's entity comes back."""
        if self._unloading:
            return
        entity_id: str = event.data["entity_id"]
        new_state = event.data.get("new_state")
        if (
            entity_id not in self._unclosed
            or entity_id in self._closing
            or new_state is None
            or new_state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN)
        ):
            return
        self.hass.async_create_background_task(
            self._async_close_unclosed([entity_id]),
            name=f"{DOMAIN} close {entity_id}",
        )

    async def _async_close_unclosed(self, entity_ids: list[str]) -> None:
        """Try again to close zones left open; re-arm retries for any still open."""
        closed: list[str] = []
        for entity_id in entity_ids:
            if (
                entity_id not in self._unclosed
                or entity_id in self._closing
                or entity_id in self._active_zones
            ):
                continue
            self._closing.add(entity_id)
            try:
                await async_get_driver(self.hass, entity_id).async_stop()
            except HomeAssistantError as err:
                _LOGGER.error(
                    "%s: %s may still be open; closing it failed again: %s",
                    self.entry.title,
                    entity_id,
                    err,
                )
            else:
                closed.append(entity_id)
            finally:
                self._closing.discard(entity_id)
        if closed:
            self._unclosed.difference_update(closed)
            _LOGGER.info("%s: closed %s", self.entry.title, ", ".join(closed))
            if not self._unclosed:
                self._unclosed_attempt = 0
        self._arm_unclosed_retry()
        await self._async_save()
        self._notify()

    # --- rain delay -----------------------------------------------------------

    @callback
    def _cancel_rain_delay_timer(self) -> None:
        if self._unsub_rain_delay is not None:
            self._unsub_rain_delay()
            self._unsub_rain_delay = None

    @callback
    def _schedule_rain_delay_expiry(self) -> None:
        self._cancel_rain_delay_timer()
        if self._rain_delay_until is None:
            return
        if self._rain_delay_until <= dt_util.now():
            self._rain_delay_until = None
            return
        self._unsub_rain_delay = async_track_point_in_time(
            self.hass, self._async_rain_delay_expired, self._rain_delay_until
        )

    async def _async_rain_delay_expired(self, _now: datetime) -> None:
        self._unsub_rain_delay = None
        self._rain_delay_until = None
        await self._async_save()
        self._notify()

    async def _async_auto_rain_delay(self) -> None:
        """After a rain skip, start the configured automatic rain delay."""
        hours = _as_float(self.config.get(CONF_RAIN_DELAY_AUTO_HOURS))
        if hours is None or hours <= 0:
            return
        hours = min(hours, float(MAX_RAIN_DELAY_HOURS))
        current = self.rain_delay_until
        if current is not None and current >= dt_util.now() + timedelta(hours=hours):
            return  # never shorten a longer delay
        await self.async_set_rain_delay(hours)

    async def _async_mirror_rain_delay(self, hours: float) -> None:
        for entity_id in zone_entity_ids(self.config):
            try:
                await async_get_driver(self.hass, entity_id).async_set_rain_delay(hours)
            except HomeAssistantError as err:
                _LOGGER.warning(
                    "%s: copying the rain delay to %s failed: %s",
                    self.entry.title,
                    entity_id,
                    err,
                )

    # --- public API -----------------------------------------------------------

    async def async_run_now(self, minutes: int | None = None) -> None:
        """Start a run now, ignoring conditions and skip_next.

        `minutes` overrides every zone's run time.
        """
        if self.running:
            raise HomeAssistantError(f"{self.entry.title} is already running")
        zones = zone_durations(self.config)
        if not zones:
            raise HomeAssistantError(f"{self.entry.title} has no zones")
        if minutes is not None:
            override = timedelta(
                minutes=max(MIN_ZONE_MINUTES, min(MAX_ZONE_MINUTES, int(minutes)))
            )
            zones = [(entity_id, override) for entity_id, _ in zones]
        self._start_run(zones, {"manual": True}, manual=True)

    async def async_run_zone(self, entity_id: str, minutes: int) -> None:
        """Water one of this schedule's zones now, ignoring conditions and skip_next."""
        if self.running:
            raise HomeAssistantError(f"{self.entry.title} is already running")
        if entity_id not in zone_entity_ids(self.config):
            raise HomeAssistantError(f"{entity_id} is not a zone of {self.entry.title}")
        duration = timedelta(minutes=max(MIN_ZONE_MINUTES, min(MAX_ZONE_MINUTES, int(minutes))))
        self._start_run([(entity_id, duration)], {"manual": True, "zone": entity_id}, manual=True)

    async def async_stop_run(self) -> None:
        """Stop the active run, and drop an occurrence waiting on occupancy."""
        self._cancel_retry()
        if self.running:
            await self._async_request_stop(Status.IDLE)
        else:
            self._notify()

    async def async_set_skip_next(self, skip: bool) -> None:
        self._skip_next = bool(skip)
        await self._async_save()
        self._notify()

    async def async_set_enabled(self, enabled: bool) -> None:
        """Enable or disable scheduling. Disabling doesn't stop an active run."""
        enabled = bool(enabled)
        if enabled == self._enabled:
            return
        self._enabled = enabled
        if enabled:
            if self._status is Status.DISABLED:
                self._set_status(self._idle_status())
            self._schedule_next(dt_util.now())
        else:
            self._cancel_timer()
            self._cancel_retry()
            self._next = None
            if not self.running:
                self._set_status(Status.DISABLED)
        await self._async_save()
        self._notify()

    async def async_set_paused(self, paused: bool) -> None:
        """Pause or resume automatic runs (pause_all / resume_all).

        Occurrences keep being scheduled but do nothing while paused. An active
        run is not stopped.
        """
        paused = bool(paused)
        if paused == self._paused:
            return
        self._paused = paused
        if paused:
            self._cancel_retry()
            if not self.running and self._enabled:
                self._set_status(Status.PAUSED)
        elif self._status is Status.PAUSED:
            self._set_status(self._idle_status())
        self._fire(EventType.PAUSED if paused else EventType.RESUMED)
        await self._async_save()
        self._notify()

    async def async_set_rain_delay(self, hours: float) -> None:
        """Skip scheduled occurrences for `hours` from now; 0 clears the delay."""
        try:
            value = float(hours)
        except (TypeError, ValueError) as err:
            raise HomeAssistantError(f"Invalid rain delay: {hours!r}") from err
        if not math.isfinite(value):
            raise HomeAssistantError(f"Invalid rain delay: {hours!r}")
        value = max(0.0, min(float(MAX_RAIN_DELAY_HOURS), value))

        self._cancel_rain_delay_timer()
        if value <= 0:
            self._rain_delay_until = None
        else:
            self._rain_delay_until = dt_util.now() + timedelta(hours=value)
            self._schedule_rain_delay_expiry()
        self._fire(EventType.RAIN_DELAY_SET, rain_delay_until=_iso(self._rain_delay_until))
        await self._async_save()
        self._notify()
        if self.config.get(CONF_RAIN_DELAY_MIRROR):
            await self._async_mirror_rain_delay(value)

    async def async_evaluate(self) -> dict[str, Any]:
        """What the conditions say right now, without running or recording anything."""
        now = dt_util.now()
        occurrence = self._next
        scheduled = occurrence.scheduled if occurrence is not None else True
        decision = await self._async_decide(scheduled)
        return {
            "at": _iso(now),
            "scheduled": scheduled,
            "rain_delay_until": _iso(self.rain_delay_until),
            "paused": self._paused,
            "enabled": self._enabled,
            "decision": {
                "water": decision.water,
                "status": decision.status.value if decision.status is not None else None,
                "details": copy.deepcopy(decision.details),
                "retry": bool(getattr(decision, "retry", False)),
            },
        }

    async def async_update_config(self, config: Mapping[str, Any]) -> None:
        """Apply new config and reschedule.

        An active run keeps the zones and zone mode it started with; its rain
        and occupancy watchers follow the new config.
        """
        self.config = dict(config)
        self._cancel_retry()
        if self.running:
            self._start_watchers(keep_progress=True)
        self._schedule_next(dt_util.now())
        self._notify()

    async def async_set_zone_minutes(self, entity_id: str, minutes: float) -> None:
        """Change one zone's run time and persist it to the entry options."""
        value = max(MIN_ZONE_MINUTES, min(MAX_ZONE_MINUTES, int(minutes)))
        current = merged_config(self.entry)
        zones = [dict(zone) for zone in current.get(CONF_ZONES) or []]
        for zone in zones:
            if zone[CONF_ZONE_ENTITY] == entity_id:
                zone[CONF_ZONE_MINUTES] = value
                break
        else:
            raise HomeAssistantError(f"{entity_id} is not a zone of {self.entry.title}")

        new_config = {**current, CONF_ZONES: zones}
        # Update the runner first so the entry update listener sees matching
        # config and skips a reload.
        await self.async_update_config(new_config)
        self.hass.config_entries.async_update_entry(self.entry, options=new_config)

    @callback
    def async_add_listener(self, update_callback: Callable[[], None]) -> CALLBACK_TYPE:
        """Call `update_callback` on every state change. Returns an unsubscribe."""
        self._listeners.append(update_callback)

        @callback
        def remove_listener() -> None:
            if update_callback in self._listeners:
                self._listeners.remove(update_callback)

        return remove_listener

    def history(self, limit: int | None = None) -> list[dict[str, Any]]:
        """Run and skip records, newest first."""
        records = self._history if limit is None else self._history[: max(0, int(limit))]
        return copy.deepcopy(records)

    # --- state ----------------------------------------------------------------

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def paused(self) -> bool:
        return self._paused

    @property
    def status(self) -> Status:
        return self._status

    @property
    def running(self) -> bool:
        return self._run_started is not None

    @property
    def skip_next(self) -> bool:
        return self._skip_next

    @property
    def rain_delay_until(self) -> datetime | None:
        """End of the active rain delay, or None when there is none."""
        until = self._rain_delay_until
        if until is None or until <= dt_util.now():
            return None
        return until

    @property
    def next_occurrence(self) -> Occurrence | None:
        return self._next

    @property
    def current_zone(self) -> str | None:
        return next(iter(self._active_zones), None)

    @property
    def current_zone_ends_at(self) -> datetime | None:
        zone = next(iter(self._active_zones.values()), None)
        return zone.ends_at if zone is not None else None

    @property
    def last_run_start(self) -> datetime | None:
        return self._last_run_start

    @property
    def last_run_end(self) -> datetime | None:
        return self._last_run_end

    @property
    def last_run_total_minutes(self) -> float | None:
        return self._last_run_total_minutes

    @property
    def last_watering_end(self) -> datetime | None:
        """End of the last run that watered for more than 0 minutes."""
        return self._last_watering_end

    @property
    def unclosed_zones(self) -> list[str]:
        """Zones whose close failed and are still being retried."""
        return sorted(self._unclosed)

    @property
    def last_status_at(self) -> datetime | None:
        return self._last_status_at

    @property
    def last_details(self) -> dict[str, Any]:
        return self._details()

    @property
    def zone_results(self) -> list[dict[str, Any]]:
        return [dict(result) for result in self._zone_results]

    def snapshot(self) -> dict[str, Any]:
        """JSON-serializable state for the websocket API and panel."""
        occurrence = self._next
        return {
            "entry_id": self.entry.entry_id,
            "name": self.entry.title,
            "enabled": self._enabled,
            "paused": self._paused,
            "status": self._status.value,
            "running": self.running,
            "skip_next": self._skip_next,
            "next_run": _iso(occurrence.start) if occurrence else None,
            "next_run_scheduled": occurrence.scheduled if occurrence else None,
            "rain_delay_until": _iso(self.rain_delay_until),
            "current_zone": self.current_zone,
            "current_zone_ends_at": _iso(self.current_zone_ends_at),
            "active_zones": [
                {"entity_id": entity_id, "ends_at": _iso(zone.ends_at)}
                for entity_id, zone in self._active_zones.items()
            ],
            "unclosed_zones": sorted(self._unclosed),
            "last_run_start": _iso(self._last_run_start),
            "last_run_end": _iso(self._last_run_end),
            "last_run_total_minutes": self._last_run_total_minutes,
            "last_watering_end": _iso(self._last_watering_end),
            "last_status_at": _iso(self._last_status_at),
            "last_details": self._details(),
            "zone_results": self.zone_results,
            "history": self.history(SNAPSHOT_HISTORY),
            "config": copy.deepcopy(self.config),
        }

    def _details(self) -> dict[str, Any]:
        """Last details, with the zones still being closed (the panel shows them)."""
        details = copy.deepcopy(self._last_details)
        if self._unclosed:
            details["unclosed_zones"] = sorted(self._unclosed)
        return details

    @callback
    def _idle_status(self) -> Status:
        if not self._enabled:
            return Status.DISABLED
        if self._paused:
            return Status.PAUSED
        return Status.IDLE

    @callback
    def _set_status(
        self, status: Status, details: Mapping[str, Any] | None = None
    ) -> None:
        self._status = status
        self._last_status_at = dt_util.now()
        if details is not None:
            self._last_details = dict(details)

    @callback
    def _add_history(self, record: dict[str, Any]) -> None:
        self._history.insert(0, record)
        del self._history[HISTORY_LIMIT:]

    @callback
    def _fire(self, event_type: EventType, **data: Any) -> None:
        device = dr.async_get(self.hass).async_get_device(
            identifiers={(DOMAIN, self.entry.entry_id)}
        )
        self.hass.bus.async_fire(
            EVENT_IRRIGATION,
            {
                "entry_id": self.entry.entry_id,
                "device_id": device.id if device is not None else None,
                "name": self.entry.title,
                "type": event_type.value,
                **data,
            },
        )

    @callback
    def _notify(self) -> None:
        for update_callback in list(self._listeners):
            update_callback()
        async_dispatcher_send(self.hass, SIGNAL_SCHEDULES_CHANGED)

    # --- persistence ----------------------------------------------------------

    def _active_run_data(self) -> dict[str, Any] | None:
        if self._run_started is not None:
            return {
                "started": _iso(self._run_started),
                "zones": [
                    {"entity_id": entity_id, "ends_at": _iso(zone.ends_at)}
                    for entity_id, zone in self._active_zones.items()
                ],
            }
        # Keep an unrecovered run on disk until its zones are closed.
        return self._recovering_run

    def _stored_data(self) -> dict[str, Any]:
        return {
            "enabled": self._enabled,
            "paused": self._paused,
            "skip_next": self._skip_next,
            "status": self._status.value,
            "last_status_at": _iso(self._last_status_at),
            "last_details": copy.deepcopy(self._last_details),
            "last_run_start": _iso(self._last_run_start),
            "last_run_end": _iso(self._last_run_end),
            "last_run_total_minutes": self._last_run_total_minutes,
            "last_watering_end": _iso(self._last_watering_end),
            "zone_results": self.zone_results,
            "rain_delay_until": _iso(self._rain_delay_until),
            "history": copy.deepcopy(self._history),
            "unclosed_zones": sorted(self._unclosed),
            "active_run": copy.deepcopy(self._active_run_data()),
        }

    @callback
    def _restore(self, data: Mapping[str, Any]) -> None:
        self._enabled = bool(data.get("enabled", True))
        self._paused = bool(data.get("paused", False))
        self._skip_next = bool(data.get("skip_next", False))
        try:
            status = Status(data.get("status", Status.IDLE))
        except ValueError:
            status = Status.IDLE
        self._status = Status.IDLE if status is Status.RUNNING else status
        self._last_status_at = _parse(data.get("last_status_at"))
        details = dict(data.get("last_details") or {})
        # v0.1 kept failed recovery closes only in details; retry those too.
        legacy_unclosed = details.pop("unclosed_zones", None) or []
        self._last_details = details
        self._last_run_start = _parse(data.get("last_run_start"))
        self._last_run_end = _parse(data.get("last_run_end"))
        total = data.get("last_run_total_minutes")
        self._last_run_total_minutes = float(total) if total is not None else None
        self._last_watering_end = _parse(data.get("last_watering_end"))
        self._zone_results = [dict(result) for result in data.get("zone_results") or []]
        self._rain_delay_until = _parse(data.get("rain_delay_until"))
        self._history = [
            dict(record)
            for record in data.get("history") or []
            if isinstance(record, Mapping)
        ][:HISTORY_LIMIT]
        self._unclosed = {
            entity_id
            for entity_id in [*(data.get("unclosed_zones") or []), *legacy_unclosed]
            if isinstance(entity_id, str) and entity_id
        }

    async def _async_save(self) -> None:
        await self._store.async_save(self._stored_data())


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def _parse(value: Any) -> datetime | None:
    return dt_util.parse_datetime(value) if isinstance(value, str) else None


def _zone_result(entity_id: str, minutes: float, error: str | None) -> dict[str, Any]:
    return {"entity_id": entity_id, "minutes": minutes, "error": error}


def _skip_record(status: Status, details: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "at": _iso(dt_util.now()),
        "type": "skip",
        "status": status.value,
        "manual": False,
        "started": None,
        "zones": [],
        "total_minutes": 0.0,
        "details": copy.deepcopy(dict(details)),
    }


def _rain_sensors(config: Mapping[str, Any]) -> list[str]:
    """Rain sensors from config: rain_sensors, else the v0.1 single rain_sensor."""
    try:
        from .conditions import resolve_rain_sensors  # noqa: PLC0415 — v0.2 helper
    except ImportError:
        sensors = config.get(CONF_RAIN_SENSORS) or (
            [config[CONF_RAIN_SENSOR]] if config.get(CONF_RAIN_SENSOR) else []
        )
        return [entity_id for entity_id in sensors if entity_id]
    return list(resolve_rain_sensors(config))


def _as_float(value: Any) -> float | None:
    """Finite float, else None."""
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _state_float(hass: HomeAssistant, entity_id: str) -> float | None:
    state = hass.states.get(entity_id)
    return _as_float(state.state) if state is not None else None


def _is_available(hass: HomeAssistant, entity_id: str) -> bool:
    """Whether a driver call could have reached the entity (drivers refuse otherwise)."""
    state = hass.states.get(entity_id)
    return state is not None and state.state != STATE_UNAVAILABLE
