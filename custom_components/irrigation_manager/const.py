"""Constants and the shared config/runtime contract for Irrigation Manager.

One config entry per schedule; the entry title is the schedule name. The config
flow stores the schedule in entry.data and the options flow writes the full set
to entry.options. Read the effective config with ``merged_config(entry)``.

Modules may append constants at the end of this file under a comment naming the
module. Don't change existing names or values — other modules depend on them.
"""
from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

DOMAIN: Final = "irrigation_manager"

# --- Config entry keys ------------------------------------------------------

CONF_NAME: Final = "name"

# list[{"entity_id": str, "minutes": int}] — valve.* or switch.* entities.
CONF_ZONES: Final = "zones"
CONF_ZONE_ENTITY: Final = "entity_id"
CONF_ZONE_MINUTES: Final = "minutes"
CONF_ZONE_MODE: Final = "zone_mode"  # scheduler.ZoneMode value

CONF_FREQUENCY: Final = "frequency"  # scheduler.Frequency value
CONF_INTERVAL_DAYS: Final = "interval_days"  # int, MIN/MAX_INTERVAL_DAYS
CONF_ANCHOR: Final = "anchor"  # ISO date "YYYY-MM-DD" — first run date
CONF_WEEKDAYS: Final = "weekdays"  # list[int], 0=Mon .. 6=Sun

CONF_START_MODE: Final = "start_mode"  # scheduler.StartMode value
CONF_START_TIME: Final = "start_time"  # "HH:MM:SS" local wall clock
CONF_SUN_OFFSET: Final = "sun_offset_minutes"  # int; finish this long before the event

# list[SkipCondition value]. Despite the name, MOISTURE in TRIGGER mode adds
# runs rather than skipping them.
CONF_SKIP_CONDITIONS: Final = "skip_conditions"

CONF_RAIN_SENSOR: Final = "rain_sensor"  # sensor.* precipitation total
CONF_RAIN_THRESHOLD: Final = "rain_threshold"  # float, in the sensor's unit
CONF_RAIN_HOURS: Final = "rain_hours"  # int, look-back window

CONF_WEATHER_ENTITY: Final = "weather_entity"  # weather.*
CONF_FORECAST_PROBABILITY: Final = "forecast_probability"  # int %
CONF_FORECAST_HOURS: Final = "forecast_hours"  # int, look-ahead window

CONF_MOISTURE_SENSORS: Final = "moisture_sensors"  # list[str] sensor.*
CONF_MOISTURE_THRESHOLD: Final = "moisture_threshold"  # float %
CONF_MOISTURE_MODE: Final = "moisture_mode"  # MoistureMode value
CONF_MOISTURE_UNAVAILABLE: Final = "moisture_unavailable"  # MoistureUnavailable value


class SkipCondition(StrEnum):
    """Optional conditions checked at each occurrence."""

    RAIN = "rain"  # rain sensor total over the last CONF_RAIN_HOURS >= threshold -> skip
    FORECAST = "forecast"  # max hourly precip probability over next CONF_FORECAST_HOURS >= threshold -> skip
    # "Dry" = ANY moisture sensor reads below CONF_MOISTURE_THRESHOLD
    # (i.e. the lowest reading is below it). Effect depends on MoistureMode.
    MOISTURE = "moisture"
    # v0.2
    TEMPERATURE = "temperature"  # freeze (min) / heat (max) skip
    WIND = "wind"  # average wind at/above max -> skip
    OCCUPANCY = "occupancy"  # an occupancy entity is on -> delay or skip


class MoistureMode(StrEnum):
    """How soil moisture affects watering."""

    # Schedule days water only when dry; otherwise skipped (SKIPPED_MOISTURE).
    SKIP = "skip"
    # Schedule days water as usual. Every other day is also checked at the start
    # time and waters when dry ("every X days OR moisture under X%"). Rain and
    # forecast conditions still apply to those extra runs. A non-dry or
    # unreadable check on a non-schedule day is a quiet no-op, not a skip.
    TRIGGER = "trigger"


class MoistureUnavailable(StrEnum):
    """SKIP mode only: what to do when no moisture sensor has a usable reading."""

    WATER = "water"
    SKIP = "skip"


# --- Limits and defaults ----------------------------------------------------

MIN_ZONE_MINUTES: Final = 1
# Rachio's cloud API caps a manual run at 3 hours; one limit for every driver.
MAX_ZONE_MINUTES: Final = 180
MIN_INTERVAL_DAYS: Final = 1
MAX_INTERVAL_DAYS: Final = 31
MIN_SUN_OFFSET: Final = -720
MAX_SUN_OFFSET: Final = 720

DEFAULT_ZONE_MINUTES: Final = 10
DEFAULT_RAIN_THRESHOLD: Final = 0.1
DEFAULT_RAIN_HOURS: Final = 24
DEFAULT_FORECAST_PROBABILITY: Final = 60
DEFAULT_FORECAST_HOURS: Final = 12
DEFAULT_MOISTURE_THRESHOLD: Final = 40.0
DEFAULT_MOISTURE_MODE: Final = MoistureMode.SKIP
DEFAULT_SUN_OFFSET: Final = 0

# --- Runtime ----------------------------------------------------------------


class Status(StrEnum):
    """Schedule status shown by the status sensor and the panel."""

    IDLE = "idle"
    RUNNING = "running"
    DISABLED = "disabled"
    SKIPPED_RAIN = "skipped_rain"
    SKIPPED_FORECAST = "skipped_forecast"
    SKIPPED_MOISTURE = "skipped_moisture"
    SKIPPED_MANUAL = "skipped_manual"  # skip_next was set
    SKIPPED_BUSY = "skipped_busy"  # previous run still active at start time
    INTERRUPTED = "interrupted"  # HA restarted or entry unloaded mid-run
    ERROR = "error"  # one or more zones failed to start/stop
    # v0.2
    SKIPPED_RAIN_DELAY = "skipped_rain_delay"  # occurrence fell inside a rain delay
    SKIPPED_TEMPERATURE = "skipped_temperature"
    SKIPPED_WIND = "skipped_wind"
    SKIPPED_OCCUPANCY = "skipped_occupancy"  # still occupied after the max delay, or action=skip
    STOPPED_RAIN = "stopped_rain"  # rain started during the run
    STOPPED_OCCUPANCY = "stopped_occupancy"  # occupancy detected during the run
    PAUSED = "paused"  # pause_all is active and no run is active


STORAGE_VERSION: Final = 1
STORAGE_KEY_FMT: Final = f"{DOMAIN}.{{entry_id}}"

# Dispatcher signal fired (no args) whenever any schedule's state or the set of
# loaded schedules changes. The panel's websocket subscription listens to it.
SIGNAL_SCHEDULES_CHANGED: Final = f"{DOMAIN}_schedules_changed"

# --- Services -----------------------------------------------------------------

SERVICE_RUN_NOW: Final = "run_now"
SERVICE_SKIP_NEXT: Final = "skip_next"
SERVICE_STOP: Final = "stop"

ATTR_CONFIG_ENTRY_ID: Final = "config_entry_id"
ATTR_MINUTES: Final = "minutes"  # optional per-zone override for run_now
ATTR_SKIP: Final = "skip"  # skip_next: true sets, false clears

# --- Panel --------------------------------------------------------------------

PANEL_FRONTEND_PATH: Final = "irrigation-manager"
PANEL_TITLE: Final = "Irrigation"
PANEL_ICON: Final = "mdi:sprinkler-variant"
PANEL_WEBCOMPONENT: Final = "irrigation-manager-panel"
PANEL_STATIC_URL: Final = f"/{DOMAIN}_static/irrigation-manager-panel.js"


def merged_config(entry: ConfigEntry) -> dict[str, Any]:
    """Effective schedule config: options override data."""
    return {**entry.data, **entry.options}


def zone_entity_ids(config: Mapping[str, Any]) -> list[str]:
    return [zone[CONF_ZONE_ENTITY] for zone in config.get(CONF_ZONES, [])]


# --- v0.2 -------------------------------------------------------------------
# Every key below is optional; an absent key keeps v0.1 behaviour. No stored
# config is migrated: list keys supersede the v0.1 single keys when present.

# Rain
CONF_RAIN_SENSORS: Final = "rain_sensors"  # list[str]; else [CONF_RAIN_SENSOR]
CONF_RAIN_AGGREGATE: Final = "rain_aggregate"  # RainAggregate value
CONF_RAIN_QUORUM: Final = "rain_quorum"  # int, stations at/over threshold (QUORUM)
CONF_RAIN_WINDOW: Final = "rain_window"  # RainWindow value
CONF_RAIN_MAX_HOURS: Final = "rain_max_hours"  # int, cap for SINCE_LAST_WATERING
CONF_RAIN_STOP_DURING_RUN: Final = "rain_stop_during_run"  # bool
CONF_RAIN_STOP_AMOUNT: Final = "rain_stop_amount"  # float, sensor unit, rise since run start
CONF_RAIN_DELAY_AUTO_HOURS: Final = "rain_delay_auto_hours"  # int; after SKIPPED_RAIN; 0 = off
CONF_RAIN_DELAY_MIRROR: Final = "rain_delay_mirror"  # bool; copy delays to devices

# Forecast
CONF_WEATHER_ENTITIES: Final = "weather_entities"  # list[str]; else [CONF_WEATHER_ENTITY]
CONF_FORECAST_QUORUM: Final = "forecast_quorum"  # int, entities that must trigger
CONF_FORECAST_MODE: Final = "forecast_mode"  # ForecastMode value
CONF_FORECAST_AMOUNT: Final = "forecast_amount"  # float, entity's precipitation_unit

# Temperature
CONF_TEMPERATURE_SENSOR: Final = "temperature_sensor"  # sensor.*, optional
CONF_TEMPERATURE_MIN: Final = "temperature_min"  # float|None: skip at/below
CONF_TEMPERATURE_MAX: Final = "temperature_max"  # float|None: skip at/above
CONF_TEMPERATURE_FORECAST_HOURS: Final = "temperature_forecast_hours"  # int; 0 = current only

# Wind
CONF_WIND_SENSOR: Final = "wind_sensor"  # sensor.*
CONF_WIND_MAX: Final = "wind_max"  # float, sensor unit
CONF_WIND_MINUTES: Final = "wind_minutes"  # int, averaging window

# Stale sensor protection — temperature sensor only (MQTT sensors don't report
# unchanged values, so rain/wind/moisture would look stale while still valid)
CONF_STALE_HOURS: Final = "stale_hours"  # int; 0/absent = off

# Occupancy
CONF_OCCUPANCY_ENTITIES: Final = "occupancy_entities"  # list[str]; state "on" = occupied
CONF_OCCUPANCY_ACTION: Final = "occupancy_action"  # OccupancyAction value
CONF_OCCUPANCY_MAX_DELAY: Final = "occupancy_max_delay_minutes"  # int
CONF_OCCUPANCY_STOP_DURING_RUN: Final = "occupancy_stop_during_run"  # bool

# AI (per schedule)
CONF_AI_TASK_ENTITY: Final = "ai_task_entity"  # ai_task.*
CONF_AI_NOTIFY_SERVICE: Final = "ai_notify_service"  # "notify.x" or "persistent_notification.create"
CONF_AI_REPORT_WEEKDAY: Final = "ai_report_weekday"  # int 0=Mon..6; absent = no weekly report
CONF_AI_REPORT_TIME: Final = "ai_report_time"  # "HH:MM:SS"
CONF_AI_CAMERA: Final = "ai_camera_entity"  # camera.*, optional
CONF_AI_LLMVISION_PROVIDER: Final = "ai_llmvision_provider"  # llmvision config entry id, optional


class RainAggregate(StrEnum):
    MAX = "max"  # skip if any station total >= threshold
    MEDIAN = "median"  # skip if the median station total >= threshold
    QUORUM = "quorum"  # skip if >= CONF_RAIN_QUORUM stations are >= threshold


class RainWindow(StrEnum):
    HOURS = "hours"  # last CONF_RAIN_HOURS
    SINCE_LAST_WATERING = "since_last_watering"  # capped at CONF_RAIN_MAX_HOURS


class ForecastMode(StrEnum):
    PROBABILITY = "probability"
    AMOUNT = "amount"
    EITHER = "either"
    BOTH = "both"


class OccupancyAction(StrEnum):
    DELAY = "delay"  # re-check every OCCUPANCY_RETRY_SECONDS up to the max delay, then skip
    SKIP = "skip"


class EventType(StrEnum):
    """`type` field of EVENT_IRRIGATION."""

    RUN_STARTED = "run_started"
    RUN_FINISHED = "run_finished"  # includes status: idle/error/stopped_*/interrupted
    ZONE_STARTED = "zone_started"
    ZONE_FINISHED = "zone_finished"
    SKIPPED = "skipped"  # includes status: skipped_*
    RAIN_DELAY_SET = "rain_delay_set"  # includes rain_delay_until (None = cleared)
    PAUSED = "paused"
    RESUMED = "resumed"


EVENT_IRRIGATION: Final = f"{DOMAIN}_event"
HISTORY_LIMIT: Final = 100
OCCUPANCY_RETRY_SECONDS: Final = 120

DEFAULT_RAIN_QUORUM: Final = 2
DEFAULT_RAIN_MAX_HOURS: Final = 168
DEFAULT_RAIN_STOP_AMOUNT: Final = 0.05
DEFAULT_FORECAST_QUORUM: Final = 1
DEFAULT_TEMPERATURE_FORECAST_HOURS: Final = 12
DEFAULT_WIND_MINUTES: Final = 30
DEFAULT_OCCUPANCY_MAX_DELAY: Final = 60
MAX_RAIN_DELAY_HOURS: Final = 336

SERVICE_SET_RAIN_DELAY: Final = "set_rain_delay"
SERVICE_RUN_ZONE: Final = "run_zone"
SERVICE_SET_ENABLED: Final = "set_enabled"
SERVICE_EVALUATE: Final = "evaluate"
SERVICE_GET_HISTORY: Final = "get_history"
SERVICE_PAUSE_ALL: Final = "pause_all"
SERVICE_RESUME_ALL: Final = "resume_all"
SERVICE_STOP_ALL: Final = "stop_all"
SERVICE_GENERATE_REPORT: Final = "generate_report"
SERVICE_EXPLAIN_SKIPS: Final = "explain_skips"

ATTR_HOURS: Final = "hours"
ATTR_ZONE: Final = "zone"  # zone entity_id for run_zone
ATTR_ENABLED: Final = "enabled"
ATTR_LIMIT: Final = "limit"
ATTR_DAYS: Final = "days"

# --- hourly ---------------------------------------------------------------
# Frequency HOURLY: every day, every CONF_INTERVAL_HOURS from CONF_WINDOW_START
# while the start is no later than CONF_WINDOW_END. Stored with start_mode
# "time" and start_time equal to the window start.
CONF_INTERVAL_HOURS: Final = "interval_hours"  # int, MIN/MAX_INTERVAL_HOURS
CONF_WINDOW_START: Final = "window_start"  # "HH:MM:SS" local
CONF_WINDOW_END: Final = "window_end"  # "HH:MM:SS" local, after the window start
MIN_INTERVAL_HOURS: Final = 1
MAX_INTERVAL_HOURS: Final = 23
DEFAULT_INTERVAL_HOURS: Final = 3
DEFAULT_WINDOW_START: Final = "06:00:00"
DEFAULT_WINDOW_END: Final = "18:00:00"
