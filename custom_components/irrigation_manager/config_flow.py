"""Config and options flows for Irrigation Manager.

One config entry per schedule. Both flows walk the same steps — zones, run
time, frequency, start time, conditions, AI reports — through
ScheduleFlowMixin. The config flow starts with a menu: create manually, import
the legacy helpers, import a B-Hyve program, or describe the schedule to an AI
task. Imports and descriptions only fill in defaults; every value still goes
through the normal steps, and nothing is saved until the flow finishes.

Only the keys for the chosen frequency, start mode and conditions are stored.
Settings that mean "off" (a zero, an unticked box) are left out rather than
stored, so a config without them behaves exactly as before they existed.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from copy import deepcopy
import math
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.selector import (
    BooleanSelector,
    ConfigEntrySelector,
    ConfigEntrySelectorConfig,
    DateSelector,
    EntityFilterSelectorConfig,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TimeSelector,
)
from homeassistant.util import dt as dt_util

from . import ai, migration
from .conditions import resolve_rain_sensors, resolve_weather_entities
from .const import (
    CONF_AI_CAMERA,
    CONF_AI_LLMVISION_PROVIDER,
    CONF_AI_NOTIFY_SERVICE,
    CONF_AI_REPORT_TIME,
    CONF_AI_REPORT_WEEKDAY,
    CONF_AI_TASK_ENTITY,
    CONF_ANCHOR,
    CONF_FORECAST_AMOUNT,
    CONF_FORECAST_HOURS,
    CONF_FORECAST_MODE,
    CONF_FORECAST_PROBABILITY,
    CONF_FORECAST_QUORUM,
    CONF_FREQUENCY,
    CONF_INTERVAL_DAYS,
    CONF_INTERVAL_HOURS,
    CONF_MOISTURE_MODE,
    CONF_MOISTURE_SENSORS,
    CONF_MOISTURE_THRESHOLD,
    CONF_MOISTURE_UNAVAILABLE,
    CONF_NAME,
    CONF_OCCUPANCY_ACTION,
    CONF_OCCUPANCY_ENTITIES,
    CONF_OCCUPANCY_MAX_DELAY,
    CONF_OCCUPANCY_STOP_DURING_RUN,
    CONF_RAIN_AGGREGATE,
    CONF_RAIN_DELAY_AUTO_HOURS,
    CONF_RAIN_DELAY_MIRROR,
    CONF_RAIN_HOURS,
    CONF_RAIN_MAX_HOURS,
    CONF_RAIN_QUORUM,
    CONF_RAIN_SENSOR,
    CONF_RAIN_SENSORS,
    CONF_RAIN_STOP_AMOUNT,
    CONF_RAIN_STOP_DURING_RUN,
    CONF_RAIN_THRESHOLD,
    CONF_RAIN_WINDOW,
    CONF_SKIP_CONDITIONS,
    CONF_STALE_HOURS,
    CONF_START_MODE,
    CONF_START_TIME,
    CONF_SUN_OFFSET,
    CONF_TEMPERATURE_FORECAST_HOURS,
    CONF_TEMPERATURE_MAX,
    CONF_TEMPERATURE_MIN,
    CONF_TEMPERATURE_SENSOR,
    CONF_WEATHER_ENTITIES,
    CONF_WEATHER_ENTITY,
    CONF_WEEKDAYS,
    CONF_WIND_MAX,
    CONF_WIND_MINUTES,
    CONF_WIND_SENSOR,
    CONF_WINDOW_END,
    CONF_WINDOW_START,
    CONF_ZONE_ENTITY,
    CONF_ZONE_MINUTES,
    CONF_ZONE_MODE,
    CONF_ZONES,
    DEFAULT_FORECAST_HOURS,
    DEFAULT_FORECAST_PROBABILITY,
    DEFAULT_FORECAST_QUORUM,
    DEFAULT_INTERVAL_HOURS,
    DEFAULT_MOISTURE_MODE,
    DEFAULT_MOISTURE_THRESHOLD,
    DEFAULT_OCCUPANCY_MAX_DELAY,
    DEFAULT_RAIN_HOURS,
    DEFAULT_RAIN_MAX_HOURS,
    DEFAULT_RAIN_QUORUM,
    DEFAULT_RAIN_STOP_AMOUNT,
    DEFAULT_RAIN_THRESHOLD,
    DEFAULT_SUN_OFFSET,
    DEFAULT_TEMPERATURE_FORECAST_HOURS,
    DEFAULT_WIND_MINUTES,
    DEFAULT_WINDOW_END,
    DEFAULT_WINDOW_START,
    DEFAULT_ZONE_MINUTES,
    DOMAIN,
    MAX_INTERVAL_DAYS,
    MAX_INTERVAL_HOURS,
    MAX_RAIN_DELAY_HOURS,
    MAX_SUN_OFFSET,
    MAX_ZONE_MINUTES,
    MIN_INTERVAL_DAYS,
    MIN_INTERVAL_HOURS,
    MIN_SUN_OFFSET,
    MIN_ZONE_MINUTES,
    ForecastMode,
    MoistureMode,
    MoistureUnavailable,
    OccupancyAction,
    RainAggregate,
    RainWindow,
    SkipCondition,
    merged_config,
    zone_entity_ids,
)
from .scheduler import Frequency, StartMode, ZoneMode

DEFAULT_START_TIME = "06:00:00"
# conditions.py skips when total >= threshold, so 0 would skip every run.
MIN_RAIN_THRESHOLD = 0.01
# conditions.py skips when max probability >= threshold, so 0% would skip every run.
MIN_FORECAST_PROBABILITY = 1
# conditions.py counts dry as lowest reading < threshold, so 0 is never dry.
MIN_MOISTURE_THRESHOLD = 1
# A zero forecast amount would skip every run; a zero rise would stop every run.
MIN_FORECAST_AMOUNT = 0.01
MIN_RAIN_STOP_AMOUNT = 0.01
# conditions.py skips when average wind >= max, so 0 would skip every run.
MIN_WIND_MAX = 0.1

MAX_RAIN_AMOUNT = 1000
MAX_RAIN_HOURS = 72
MAX_RAIN_WINDOW_HOURS = 720
MAX_RAIN_QUORUM = 20
MAX_FORECAST_HOURS = 48
MAX_FORECAST_QUORUM = 10
MAX_STALE_HOURS = 168
TEMPERATURE_RANGE = (-100, 200)  # either unit; the sensor's unit decides
MAX_TEMPERATURE_FORECAST_HOURS = 48
MAX_WIND = 500
MAX_WIND_MINUTES = 180
MAX_OCCUPANCY_DELAY = 240
DEFAULT_OCCUPANCY_STOP_DURING_RUN = True

AI_TASK_DOMAIN = "ai_task"
NOTIFY_DOMAIN = "notify"
LLMVISION_DOMAIN = "llmvision"
PERSISTENT_NOTIFICATION_SERVICE = "persistent_notification.create"

# Fields that exist only in the import and describe steps.
FIELD_PROGRAM = "program"
FIELD_DESCRIPTION = "description"
FIELD_DISABLE_PROGRAM = "disable_program"

# Keys owned by each choice; choosing one drops the keys of the others.
_FREQUENCY_KEYS: dict[str, tuple[str, ...]] = {
    Frequency.INTERVAL: (CONF_INTERVAL_DAYS, CONF_ANCHOR),
    Frequency.WEEKDAYS: (CONF_WEEKDAYS,),
    Frequency.HOURLY: (CONF_INTERVAL_HOURS, CONF_WINDOW_START, CONF_WINDOW_END),
}
_START_KEYS: dict[str, tuple[str, ...]] = {
    StartMode.TIME: (CONF_START_TIME,),
    StartMode.SUNRISE: (CONF_SUN_OFFSET,),
    StartMode.SUNSET: (CONF_SUN_OFFSET,),
}
_WEATHER_KEYS = (CONF_WEATHER_ENTITY, CONF_WEATHER_ENTITIES)
# Every key a condition can store, v0.1 single keys included. Temperature
# shares the weather entities with forecast (they feed its forecast low).
_CONDITION_KEYS: dict[SkipCondition, tuple[str, ...]] = {
    SkipCondition.RAIN: (
        CONF_RAIN_SENSOR,
        CONF_RAIN_SENSORS,
        CONF_RAIN_THRESHOLD,
        CONF_RAIN_HOURS,
        CONF_RAIN_AGGREGATE,
        CONF_RAIN_QUORUM,
        CONF_RAIN_WINDOW,
        CONF_RAIN_MAX_HOURS,
        CONF_RAIN_DELAY_AUTO_HOURS,
        CONF_RAIN_DELAY_MIRROR,
        CONF_RAIN_STOP_DURING_RUN,
        CONF_RAIN_STOP_AMOUNT,
    ),
    SkipCondition.FORECAST: (
        *_WEATHER_KEYS,
        CONF_FORECAST_PROBABILITY,
        CONF_FORECAST_HOURS,
        CONF_FORECAST_MODE,
        CONF_FORECAST_AMOUNT,
        CONF_FORECAST_QUORUM,
    ),
    SkipCondition.MOISTURE: (
        CONF_MOISTURE_SENSORS,
        CONF_MOISTURE_THRESHOLD,
        CONF_MOISTURE_MODE,
        CONF_MOISTURE_UNAVAILABLE,
    ),
    SkipCondition.TEMPERATURE: (
        CONF_TEMPERATURE_SENSOR,
        CONF_TEMPERATURE_MIN,
        CONF_TEMPERATURE_MAX,
        CONF_TEMPERATURE_FORECAST_HOURS,
        *_WEATHER_KEYS,
    ),
    SkipCondition.WIND: (CONF_WIND_SENSOR, CONF_WIND_MAX, CONF_WIND_MINUTES),
    SkipCondition.OCCUPANCY: (
        CONF_OCCUPANCY_ENTITIES,
        CONF_OCCUPANCY_ACTION,
        CONF_OCCUPANCY_MAX_DELAY,
        CONF_OCCUPANCY_STOP_DURING_RUN,
    ),
}
_AI_KEYS = (
    CONF_AI_TASK_ENTITY,
    CONF_AI_NOTIFY_SERVICE,
    CONF_AI_REPORT_WEEKDAY,
    CONF_AI_REPORT_TIME,
    CONF_AI_CAMERA,
    CONF_AI_LLMVISION_PROVIDER,
)


def _required(key: str, default: Any) -> vol.Required:
    """vol.Required with a default only when there is one."""
    if default is None:
        return vol.Required(key)
    return vol.Required(key, default=default)


def _optional(key: str, suggested: Any) -> vol.Optional:
    """vol.Optional pre-filled with `suggested`, which the user can clear."""
    if suggested is None:
        return vol.Optional(key)
    return vol.Optional(key, description={"suggested_value": suggested})


def _in_range(value: float, minimum: float, maximum: float) -> bool:
    """Finite and within bounds. Selectors check bounds, but NaN passes them."""
    return math.isfinite(value) and minimum <= value <= maximum


def _whole(
    user_input: Mapping[str, Any], key: str, errors: dict[str, str]
) -> int | None:
    """A number field as int; NaN or infinity sets a form error instead."""
    value = float(user_input[key])
    if not math.isfinite(value):
        errors[key] = "number_invalid"
        return None
    return int(value)


def _unique(values: Iterable[str] | None) -> list[str]:
    return list(dict.fromkeys(value for value in values or [] if value))


def _entity_selector(
    domain: str | list[str], device_class: str | None = None, multiple: bool = False
) -> EntitySelector:
    entity_filter = EntityFilterSelectorConfig(domain=domain)
    if device_class is not None:
        entity_filter["device_class"] = device_class
    return EntitySelector(EntitySelectorConfig(filter=entity_filter, multiple=multiple))


def _number_selector(
    minimum: float, maximum: float, step: float = 1, unit: str | None = None
) -> NumberSelector:
    config = NumberSelectorConfig(
        min=minimum, max=maximum, step=step, mode=NumberSelectorMode.BOX
    )
    if unit is not None:
        config["unit_of_measurement"] = unit
    return NumberSelector(config)


def _select_selector(
    options: list[str], translation_key: str, multiple: bool = False
) -> SelectSelector:
    return SelectSelector(
        SelectSelectorConfig(
            options=options,
            translation_key=translation_key,
            multiple=multiple,
            mode=SelectSelectorMode.LIST,
        )
    )


def _name_schema(default: str | None) -> vol.Schema:
    return vol.Schema({_required(CONF_NAME, default): TextSelector()})


def _name_errors(
    hass: HomeAssistant, name: str, exclude_entry_id: str | None
) -> dict[str, str]:
    """Blank or duplicate (case-insensitive) schedule names."""
    if not name:
        return {CONF_NAME: "name_required"}
    folded = name.casefold()
    for entry in hass.config_entries.async_entries(DOMAIN):
        if entry.entry_id != exclude_entry_id and entry.title.casefold() == folded:
            return {CONF_NAME: "name_exists"}
    return {}


def _bullets(lines: Iterable[str]) -> str:
    return "\n".join(f"- {line}" for line in lines)


class ScheduleFlowMixin:
    """Steps shared by the config and options flows, from zones onward.

    The name step fills self._config[CONF_NAME] and continues with
    async_step_zones; after the last condition step comes the AI step, then
    _async_finish.
    """

    hass: HomeAssistant

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._config: dict[str, Any] = {}
        # Imported values offered as defaults without being part of the config
        # (e.g. a legacy rain threshold whose condition isn't turned on).
        self._prefill: dict[str, Any] = {}
        self._zone_minutes_default = DEFAULT_ZONE_MINUTES
        self._zone_ids: list[str] = []
        self._pending_conditions: list[SkipCondition] = []

    async def _async_finish(self) -> ConfigFlowResult:
        raise NotImplementedError

    def _default(self, key: str, fallback: Any = None) -> Any:
        """Current value, else an imported default, else `fallback`."""
        if key in self._config:
            return self._config[key]
        return self._prefill.get(key, fallback)

    def _set(self, key: str, value: Any) -> None:
        """Store `value`, or drop the key when it is None."""
        if value is None:
            self._config.pop(key, None)
        else:
            self._config[key] = value

    def _set_choice(
        self, key_map: Mapping[str, tuple[str, ...]], conf_key: str, choice: str
    ) -> None:
        """Record `choice` under `conf_key` and drop keys only other choices use."""
        keep = set(key_map[choice])
        for other, keys in key_map.items():
            if other != choice:
                for key in keys:
                    if key not in keep:
                        self._config.pop(key, None)
        self._config[conf_key] = str(choice)

    def _condition_selected(self, condition: SkipCondition) -> bool:
        return condition.value in (self._config.get(CONF_SKIP_CONDITIONS) or [])

    # --- zones --------------------------------------------------------------

    async def async_step_zones(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            entity_ids = _unique(user_input.get(CONF_ZONES))
            if entity_ids:
                self._zone_ids = entity_ids
                return await self.async_step_zone_minutes()
            errors[CONF_ZONES] = "no_zones"

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_ZONES, default=zone_entity_ids(self._config)
                ): _entity_selector(["valve", "switch"], multiple=True)
            }
        )
        return self.async_show_form(step_id="zones", data_schema=schema, errors=errors)

    async def async_step_zone_minutes(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        multiple = len(self._zone_ids) > 1
        errors: dict[str, str] = {}
        if user_input is not None:
            minutes = {entity_id: _whole(user_input, entity_id, errors) for entity_id in self._zone_ids}
            if not errors:
                self._config[CONF_ZONES] = [
                    {CONF_ZONE_ENTITY: entity_id, CONF_ZONE_MINUTES: minutes[entity_id]}
                    for entity_id in self._zone_ids
                ]
                mode = user_input.get(CONF_ZONE_MODE) if multiple else None
                self._config[CONF_ZONE_MODE] = ZoneMode(mode or ZoneMode.SEQUENTIAL).value
                return await self.async_step_frequency()

        current = {
            zone[CONF_ZONE_ENTITY]: zone[CONF_ZONE_MINUTES]
            for zone in self._config.get(CONF_ZONES, [])
        }
        fields: dict[Any, Any] = {
            vol.Required(
                entity_id, default=current.get(entity_id, self._zone_minutes_default)
            ): _number_selector(MIN_ZONE_MINUTES, MAX_ZONE_MINUTES, unit="min")
            for entity_id in self._zone_ids
        }
        if multiple:
            fields[
                vol.Required(
                    CONF_ZONE_MODE,
                    default=self._config.get(CONF_ZONE_MODE, ZoneMode.SEQUENTIAL.value),
                )
            ] = _select_selector([mode.value for mode in ZoneMode], CONF_ZONE_MODE)

        return self.async_show_form(
            step_id="zone_minutes",
            data_schema=vol.Schema(fields),
            errors=errors,
            description_placeholders={"zones": self._zone_list()},
        )

    def _zone_list(self) -> str:
        lines = []
        for entity_id in self._zone_ids:
            state = self.hass.states.get(entity_id)
            name = state.name if state else entity_id
            lines.append(f"- {name} ({entity_id})")
        return "\n".join(lines)

    # --- frequency ----------------------------------------------------------

    async def async_step_frequency(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="frequency",
            menu_options=[
                Frequency.INTERVAL.value,
                Frequency.WEEKDAYS.value,
                Frequency.HOURLY.value,
            ],
        )

    async def async_step_interval(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            days = _whole(user_input, CONF_INTERVAL_DAYS, errors)
            if not errors:
                self._set_choice(_FREQUENCY_KEYS, CONF_FREQUENCY, Frequency.INTERVAL)
                self._config[CONF_INTERVAL_DAYS] = days
                self._config[CONF_ANCHOR] = cv.date(user_input[CONF_ANCHOR]).isoformat()
                return await self.async_step_start()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_INTERVAL_DAYS,
                    default=self._default(CONF_INTERVAL_DAYS, MIN_INTERVAL_DAYS),
                ): _number_selector(MIN_INTERVAL_DAYS, MAX_INTERVAL_DAYS, unit="d"),
                vol.Required(
                    CONF_ANCHOR,
                    default=self._default(CONF_ANCHOR, dt_util.now().date().isoformat()),
                ): DateSelector(),
            }
        )
        return self.async_show_form(step_id="interval", data_schema=schema, errors=errors)

    async def async_step_weekdays(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            days = sorted({int(day) for day in user_input.get(CONF_WEEKDAYS) or []})
            if days:
                self._set_choice(_FREQUENCY_KEYS, CONF_FREQUENCY, Frequency.WEEKDAYS)
                self._config[CONF_WEEKDAYS] = days
                return await self.async_step_start()
            errors[CONF_WEEKDAYS] = "no_weekdays"

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_WEEKDAYS,
                    default=[str(day) for day in self._default(CONF_WEEKDAYS, [])],
                ): _select_selector(
                    [str(day) for day in range(7)], CONF_WEEKDAYS, multiple=True
                )
            }
        )
        return self.async_show_form(
            step_id="weekdays", data_schema=schema, errors=errors
        )

    async def async_step_hourly(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            hours = _whole(user_input, CONF_INTERVAL_HOURS, errors)
            window_start = cv.time(user_input[CONF_WINDOW_START])
            window_end = cv.time(user_input[CONF_WINDOW_END])
            if window_end <= window_start:
                # The window can't cross midnight.
                errors[CONF_WINDOW_END] = "window_invalid"
            if not errors:
                start = window_start.strftime("%H:%M:%S")
                self._set_choice(_FREQUENCY_KEYS, CONF_FREQUENCY, Frequency.HOURLY)
                self._config[CONF_INTERVAL_HOURS] = hours
                self._config[CONF_WINDOW_START] = start
                self._config[CONF_WINDOW_END] = window_end.strftime("%H:%M:%S")
                # Runs start at the window start and repeat from there, so the
                # start-time step is skipped: store it as a fixed-time schedule.
                self._set_choice(_START_KEYS, CONF_START_MODE, StartMode.TIME)
                self._config[CONF_START_TIME] = start
                return await self.async_step_conditions()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_INTERVAL_HOURS,
                    default=self._default(CONF_INTERVAL_HOURS, DEFAULT_INTERVAL_HOURS),
                ): _number_selector(MIN_INTERVAL_HOURS, MAX_INTERVAL_HOURS, unit="h"),
                vol.Required(
                    CONF_WINDOW_START,
                    default=self._default(CONF_WINDOW_START, DEFAULT_WINDOW_START),
                ): TimeSelector(),
                vol.Required(
                    CONF_WINDOW_END,
                    default=self._default(CONF_WINDOW_END, DEFAULT_WINDOW_END),
                ): TimeSelector(),
            }
        )
        return self.async_show_form(step_id="hourly", data_schema=schema, errors=errors)

    # --- start time ---------------------------------------------------------

    async def async_step_start(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return self.async_show_menu(
            step_id="start",
            menu_options=["start_time", "start_sunrise", "start_sunset"],
        )

    async def async_step_start_time(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            self._set_choice(_START_KEYS, CONF_START_MODE, StartMode.TIME)
            self._config[CONF_START_TIME] = cv.time(
                user_input[CONF_START_TIME]
            ).strftime("%H:%M:%S")
            return await self.async_step_conditions()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_START_TIME,
                    default=self._default(CONF_START_TIME, DEFAULT_START_TIME),
                ): TimeSelector()
            }
        )
        return self.async_show_form(step_id="start_time", data_schema=schema)

    async def async_step_start_sunrise(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._async_step_sun(StartMode.SUNRISE, user_input)

    async def async_step_start_sunset(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self._async_step_sun(StartMode.SUNSET, user_input)

    async def _async_step_sun(
        self, mode: StartMode, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            offset = _whole(user_input, CONF_SUN_OFFSET, errors)
            if not errors:
                self._set_choice(_START_KEYS, CONF_START_MODE, mode)
                self._config[CONF_SUN_OFFSET] = offset
                return await self.async_step_conditions()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SUN_OFFSET,
                    default=self._default(CONF_SUN_OFFSET, DEFAULT_SUN_OFFSET),
                ): _number_selector(MIN_SUN_OFFSET, MAX_SUN_OFFSET, unit="min")
            }
        )
        return self.async_show_form(
            step_id=f"start_{mode.value}", data_schema=schema, errors=errors
        )

    # --- conditions ---------------------------------------------------------

    async def async_step_conditions(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            stale = _whole(user_input, CONF_STALE_HOURS, errors)
            if not errors:
                chosen = {
                    SkipCondition(value)
                    for value in user_input.get(CONF_SKIP_CONDITIONS) or []
                }
                # Enum order fixes the sub-step order.
                ordered = [condition for condition in SkipCondition if condition in chosen]
                keep = {key for condition in ordered for key in _CONDITION_KEYS[condition]}
                for keys in _CONDITION_KEYS.values():
                    for key in keys:
                        if key not in keep:
                            self._config.pop(key, None)
                self._config[CONF_SKIP_CONDITIONS] = [condition.value for condition in ordered]
                self._set(CONF_STALE_HOURS, stale or None)
                self._pending_conditions = ordered
                return await self._async_next_condition()

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_SKIP_CONDITIONS,
                    default=list(self._default(CONF_SKIP_CONDITIONS, [])),
                ): _select_selector(
                    [condition.value for condition in SkipCondition],
                    CONF_SKIP_CONDITIONS,
                    multiple=True,
                ),
                vol.Required(
                    CONF_STALE_HOURS, default=self._default(CONF_STALE_HOURS, 0)
                ): _number_selector(0, MAX_STALE_HOURS, unit="h"),
            }
        )
        return self.async_show_form(step_id="conditions", data_schema=schema, errors=errors)

    async def _async_next_condition(self) -> ConfigFlowResult:
        if not self._pending_conditions:
            return await self.async_step_ai()
        condition = self._pending_conditions.pop(0)
        steps = {
            SkipCondition.RAIN: self.async_step_rain,
            SkipCondition.FORECAST: self.async_step_forecast,
            SkipCondition.MOISTURE: self.async_step_moisture,
            SkipCondition.TEMPERATURE: self.async_step_temperature,
            SkipCondition.WIND: self.async_step_wind,
            SkipCondition.OCCUPANCY: self.async_step_occupancy,
        }
        return await steps[condition]()

    async def async_step_rain(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            sensors = _unique(user_input.get(CONF_RAIN_SENSORS))
            threshold = float(user_input[CONF_RAIN_THRESHOLD])
            aggregate = RainAggregate(user_input[CONF_RAIN_AGGREGATE])
            window = RainWindow(user_input[CONF_RAIN_WINDOW])
            quorum = float(user_input[CONF_RAIN_QUORUM])
            stop = bool(user_input[CONF_RAIN_STOP_DURING_RUN])
            stop_amount = float(user_input[CONF_RAIN_STOP_AMOUNT])
            hours = _whole(user_input, CONF_RAIN_HOURS, errors)
            max_hours = _whole(user_input, CONF_RAIN_MAX_HOURS, errors)
            auto_hours = _whole(user_input, CONF_RAIN_DELAY_AUTO_HOURS, errors)
            if not sensors:
                errors[CONF_RAIN_SENSORS] = "no_rain_sensors"
            # The selector enforces the minimum, but NaN passes its range check.
            if not _in_range(threshold, MIN_RAIN_THRESHOLD, MAX_RAIN_AMOUNT):
                errors[CONF_RAIN_THRESHOLD] = "rain_threshold_invalid"
            if aggregate is RainAggregate.QUORUM and not _in_range(quorum, 1, MAX_RAIN_QUORUM):
                errors[CONF_RAIN_QUORUM] = "rain_quorum_invalid"
            if stop and not _in_range(stop_amount, MIN_RAIN_STOP_AMOUNT, MAX_RAIN_AMOUNT):
                errors[CONF_RAIN_STOP_AMOUNT] = "rain_stop_amount_invalid"
            if not errors:
                self._config.pop(CONF_RAIN_SENSOR, None)
                self._config[CONF_RAIN_SENSORS] = sensors
                self._config[CONF_RAIN_THRESHOLD] = threshold
                self._config[CONF_RAIN_HOURS] = hours
                self._config[CONF_RAIN_AGGREGATE] = aggregate.value
                self._set(
                    CONF_RAIN_QUORUM,
                    int(quorum) if aggregate is RainAggregate.QUORUM else None,
                )
                self._config[CONF_RAIN_WINDOW] = window.value
                self._set(
                    CONF_RAIN_MAX_HOURS,
                    max_hours if window is RainWindow.SINCE_LAST_WATERING else None,
                )
                self._set(CONF_RAIN_DELAY_AUTO_HOURS, auto_hours or None)
                self._set(
                    CONF_RAIN_DELAY_MIRROR,
                    True if user_input[CONF_RAIN_DELAY_MIRROR] else None,
                )
                self._set(CONF_RAIN_STOP_DURING_RUN, True if stop else None)
                self._set(CONF_RAIN_STOP_AMOUNT, stop_amount if stop else None)
                return await self._async_next_condition()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_RAIN_SENSORS, default=resolve_rain_sensors(self._config)
                ): _entity_selector("sensor", device_class="precipitation", multiple=True),
                vol.Required(
                    CONF_RAIN_THRESHOLD,
                    default=self._default(CONF_RAIN_THRESHOLD, DEFAULT_RAIN_THRESHOLD),
                ): _number_selector(MIN_RAIN_THRESHOLD, MAX_RAIN_AMOUNT, step=0.01),
                vol.Required(
                    CONF_RAIN_HOURS,
                    default=self._default(CONF_RAIN_HOURS, DEFAULT_RAIN_HOURS),
                ): _number_selector(1, MAX_RAIN_HOURS, unit="h"),
                vol.Required(
                    CONF_RAIN_AGGREGATE,
                    default=self._default(CONF_RAIN_AGGREGATE, RainAggregate.MAX.value),
                ): _select_selector([item.value for item in RainAggregate], CONF_RAIN_AGGREGATE),
                vol.Required(
                    CONF_RAIN_QUORUM,
                    default=self._default(CONF_RAIN_QUORUM, DEFAULT_RAIN_QUORUM),
                ): _number_selector(1, MAX_RAIN_QUORUM),
                vol.Required(
                    CONF_RAIN_WINDOW,
                    default=self._default(CONF_RAIN_WINDOW, RainWindow.HOURS.value),
                ): _select_selector([item.value for item in RainWindow], CONF_RAIN_WINDOW),
                vol.Required(
                    CONF_RAIN_MAX_HOURS,
                    default=self._default(CONF_RAIN_MAX_HOURS, DEFAULT_RAIN_MAX_HOURS),
                ): _number_selector(1, MAX_RAIN_WINDOW_HOURS, unit="h"),
                vol.Required(
                    CONF_RAIN_DELAY_AUTO_HOURS,
                    default=self._default(CONF_RAIN_DELAY_AUTO_HOURS, 0),
                ): _number_selector(0, MAX_RAIN_DELAY_HOURS, unit="h"),
                vol.Required(
                    CONF_RAIN_DELAY_MIRROR,
                    default=self._default(CONF_RAIN_DELAY_MIRROR, False),
                ): BooleanSelector(),
                vol.Required(
                    CONF_RAIN_STOP_DURING_RUN,
                    default=self._default(CONF_RAIN_STOP_DURING_RUN, False),
                ): BooleanSelector(),
                vol.Required(
                    CONF_RAIN_STOP_AMOUNT,
                    default=self._default(CONF_RAIN_STOP_AMOUNT, DEFAULT_RAIN_STOP_AMOUNT),
                ): _number_selector(0, MAX_RAIN_AMOUNT, step=0.01),
            }
        )
        return self.async_show_form(step_id="rain", data_schema=schema, errors=errors)

    async def async_step_forecast(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            entities = _unique(user_input.get(CONF_WEATHER_ENTITIES))
            mode = ForecastMode(user_input[CONF_FORECAST_MODE])
            probability = float(user_input[CONF_FORECAST_PROBABILITY])
            amount = float(user_input[CONF_FORECAST_AMOUNT])
            quorum = float(user_input[CONF_FORECAST_QUORUM])
            hours = _whole(user_input, CONF_FORECAST_HOURS, errors)
            if not entities:
                errors[CONF_WEATHER_ENTITIES] = "no_weather_entities"
            elif not _in_range(quorum, 1, len(entities)):
                errors[CONF_FORECAST_QUORUM] = "forecast_quorum_invalid"
            if mode is not ForecastMode.AMOUNT and not _in_range(
                probability, MIN_FORECAST_PROBABILITY, 100
            ):
                errors[CONF_FORECAST_PROBABILITY] = "forecast_probability_invalid"
            if mode is not ForecastMode.PROBABILITY and not _in_range(
                amount, MIN_FORECAST_AMOUNT, MAX_RAIN_AMOUNT
            ):
                errors[CONF_FORECAST_AMOUNT] = "forecast_amount_invalid"
            if not errors:
                self._config.pop(CONF_WEATHER_ENTITY, None)
                self._config[CONF_WEATHER_ENTITIES] = entities
                self._config[CONF_FORECAST_MODE] = mode.value
                self._set(
                    CONF_FORECAST_PROBABILITY,
                    int(probability) if mode is not ForecastMode.AMOUNT else None,
                )
                self._set(
                    CONF_FORECAST_AMOUNT,
                    amount if mode is not ForecastMode.PROBABILITY else None,
                )
                self._config[CONF_FORECAST_HOURS] = hours
                self._set(CONF_FORECAST_QUORUM, int(quorum) if quorum > 1 else None)
                return await self._async_next_condition()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_WEATHER_ENTITIES, default=resolve_weather_entities(self._config)
                ): _entity_selector("weather", multiple=True),
                vol.Required(
                    CONF_FORECAST_MODE,
                    default=self._default(CONF_FORECAST_MODE, ForecastMode.PROBABILITY.value),
                ): _select_selector([item.value for item in ForecastMode], CONF_FORECAST_MODE),
                vol.Required(
                    CONF_FORECAST_PROBABILITY,
                    default=self._default(
                        CONF_FORECAST_PROBABILITY, DEFAULT_FORECAST_PROBABILITY
                    ),
                ): _number_selector(MIN_FORECAST_PROBABILITY, 100, unit="%"),
                vol.Required(
                    CONF_FORECAST_AMOUNT, default=self._default(CONF_FORECAST_AMOUNT, 0)
                ): _number_selector(
                    0,
                    MAX_RAIN_AMOUNT,
                    step=0.01,
                    # `accumulated_precipitation` (no suffix) is a converter method.
                    unit=self.hass.config.units.accumulated_precipitation_unit,
                ),
                vol.Required(
                    CONF_FORECAST_HOURS,
                    default=self._default(CONF_FORECAST_HOURS, DEFAULT_FORECAST_HOURS),
                ): _number_selector(1, MAX_FORECAST_HOURS, unit="h"),
                vol.Required(
                    CONF_FORECAST_QUORUM,
                    default=self._default(CONF_FORECAST_QUORUM, DEFAULT_FORECAST_QUORUM),
                ): _number_selector(1, MAX_FORECAST_QUORUM),
            }
        )
        return self.async_show_form(step_id="forecast", data_schema=schema, errors=errors)

    async def async_step_moisture(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            sensors = _unique(user_input.get(CONF_MOISTURE_SENSORS))
            threshold = float(user_input[CONF_MOISTURE_THRESHOLD])
            mode = MoistureMode(user_input[CONF_MOISTURE_MODE])
            if not sensors:
                errors[CONF_MOISTURE_SENSORS] = "no_moisture_sensors"
            if not _in_range(threshold, MIN_MOISTURE_THRESHOLD, 100):
                errors[CONF_MOISTURE_THRESHOLD] = "moisture_threshold_invalid"
            if (
                mode is MoistureMode.TRIGGER
                and self._config.get(CONF_FREQUENCY) == Frequency.HOURLY
            ):
                # Trigger mode adds runs on non-schedule days, and every day is
                # a schedule day for an hourly schedule.
                errors[CONF_MOISTURE_MODE] = "moisture_trigger_hourly"
            if not errors:
                self._config[CONF_MOISTURE_SENSORS] = sensors
                self._config[CONF_MOISTURE_THRESHOLD] = threshold
                self._config[CONF_MOISTURE_MODE] = mode.value
                self._config[CONF_MOISTURE_UNAVAILABLE] = MoistureUnavailable(
                    user_input[CONF_MOISTURE_UNAVAILABLE]
                ).value
                return await self._async_next_condition()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_MOISTURE_SENSORS,
                    default=list(self._default(CONF_MOISTURE_SENSORS, [])),
                ): _entity_selector("sensor", device_class="moisture", multiple=True),
                vol.Required(
                    CONF_MOISTURE_THRESHOLD,
                    default=self._default(CONF_MOISTURE_THRESHOLD, DEFAULT_MOISTURE_THRESHOLD),
                ): _number_selector(MIN_MOISTURE_THRESHOLD, 100, step=0.1, unit="%"),
                vol.Required(
                    CONF_MOISTURE_MODE,
                    default=self._default(CONF_MOISTURE_MODE, DEFAULT_MOISTURE_MODE.value),
                ): _select_selector([mode.value for mode in MoistureMode], CONF_MOISTURE_MODE),
                vol.Required(
                    CONF_MOISTURE_UNAVAILABLE,
                    default=self._default(
                        CONF_MOISTURE_UNAVAILABLE, MoistureUnavailable.WATER.value
                    ),
                ): _select_selector(
                    [choice.value for choice in MoistureUnavailable],
                    CONF_MOISTURE_UNAVAILABLE,
                ),
            }
        )
        return self.async_show_form(step_id="moisture", data_schema=schema, errors=errors)

    async def async_step_temperature(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        # With the forecast condition on, its weather entities feed the forecast
        # low; otherwise this step asks for them.
        ask_weather = not self._condition_selected(SkipCondition.FORECAST)
        if user_input is not None:
            sensor = user_input.get(CONF_TEMPERATURE_SENSOR) or None
            low = user_input.get(CONF_TEMPERATURE_MIN)
            high = user_input.get(CONF_TEMPERATURE_MAX)
            hours = _whole(user_input, CONF_TEMPERATURE_FORECAST_HOURS, errors)
            entities = (
                _unique(user_input.get(CONF_WEATHER_ENTITIES))
                if ask_weather
                else resolve_weather_entities(self._config)
            )
            for key, value in ((CONF_TEMPERATURE_MIN, low), (CONF_TEMPERATURE_MAX, high)):
                if value is not None and not _in_range(float(value), *TEMPERATURE_RANGE):
                    errors[key] = "temperature_invalid"
            if low is None and high is None:
                errors["base"] = "temperature_limit_required"
            elif (
                low is not None
                and high is not None
                and not errors
                and float(low) >= float(high)
            ):
                errors["base"] = "temperature_range_invalid"
            if high is not None and sensor is None:
                # The heat skip only compares the current reading.
                errors[CONF_TEMPERATURE_SENSOR] = "temperature_max_needs_sensor"
            if "base" not in errors and sensor is None and not (entities and hours):
                errors["base"] = "temperature_source_required"
            if not errors:
                self._set(CONF_TEMPERATURE_SENSOR, sensor)
                self._set(CONF_TEMPERATURE_MIN, float(low) if low is not None else None)
                self._set(CONF_TEMPERATURE_MAX, float(high) if high is not None else None)
                self._config[CONF_TEMPERATURE_FORECAST_HOURS] = hours
                if ask_weather:
                    self._config.pop(CONF_WEATHER_ENTITY, None)
                    self._set(CONF_WEATHER_ENTITIES, entities or None)
                return await self._async_next_condition()

        fields: dict[Any, Any] = {
            _optional(
                CONF_TEMPERATURE_SENSOR, self._default(CONF_TEMPERATURE_SENSOR)
            ): _entity_selector("sensor", device_class="temperature"),
            _optional(CONF_TEMPERATURE_MIN, self._default(CONF_TEMPERATURE_MIN)): _number_selector(
                *TEMPERATURE_RANGE, step=0.5
            ),
            _optional(CONF_TEMPERATURE_MAX, self._default(CONF_TEMPERATURE_MAX)): _number_selector(
                *TEMPERATURE_RANGE, step=0.5
            ),
            vol.Required(
                CONF_TEMPERATURE_FORECAST_HOURS,
                default=self._default(
                    CONF_TEMPERATURE_FORECAST_HOURS, DEFAULT_TEMPERATURE_FORECAST_HOURS
                ),
            ): _number_selector(0, MAX_TEMPERATURE_FORECAST_HOURS, unit="h"),
        }
        if ask_weather:
            fields[
                _optional(CONF_WEATHER_ENTITIES, resolve_weather_entities(self._config) or None)
            ] = _entity_selector("weather", multiple=True)
        return self.async_show_form(
            step_id="temperature", data_schema=vol.Schema(fields), errors=errors
        )

    async def async_step_wind(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            wind_max = float(user_input[CONF_WIND_MAX])
            minutes = _whole(user_input, CONF_WIND_MINUTES, errors)
            if not _in_range(wind_max, MIN_WIND_MAX, MAX_WIND):
                errors[CONF_WIND_MAX] = "wind_max_invalid"
            if not errors:
                self._config[CONF_WIND_SENSOR] = user_input[CONF_WIND_SENSOR]
                self._config[CONF_WIND_MAX] = wind_max
                self._config[CONF_WIND_MINUTES] = minutes
                return await self._async_next_condition()

        schema = vol.Schema(
            {
                _required(
                    CONF_WIND_SENSOR, self._default(CONF_WIND_SENSOR)
                ): _entity_selector("sensor", device_class="wind_speed"),
                _required(CONF_WIND_MAX, self._default(CONF_WIND_MAX)): _number_selector(
                    MIN_WIND_MAX, MAX_WIND, step=0.1
                ),
                vol.Required(
                    CONF_WIND_MINUTES, default=self._default(CONF_WIND_MINUTES, DEFAULT_WIND_MINUTES)
                ): _number_selector(0, MAX_WIND_MINUTES, unit="min"),
            }
        )
        return self.async_show_form(step_id="wind", data_schema=schema, errors=errors)

    async def async_step_occupancy(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            entities = _unique(user_input.get(CONF_OCCUPANCY_ENTITIES))
            action = OccupancyAction(user_input[CONF_OCCUPANCY_ACTION])
            max_delay = _whole(user_input, CONF_OCCUPANCY_MAX_DELAY, errors)
            if not entities:
                errors[CONF_OCCUPANCY_ENTITIES] = "no_occupancy_entities"
            if not errors:
                self._config[CONF_OCCUPANCY_ENTITIES] = entities
                self._config[CONF_OCCUPANCY_ACTION] = action.value
                self._set(
                    CONF_OCCUPANCY_MAX_DELAY,
                    max_delay if action is OccupancyAction.DELAY else None,
                )
                self._set(
                    CONF_OCCUPANCY_STOP_DURING_RUN,
                    True if user_input[CONF_OCCUPANCY_STOP_DURING_RUN] else None,
                )
                return await self._async_next_condition()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_OCCUPANCY_ENTITIES,
                    default=list(self._default(CONF_OCCUPANCY_ENTITIES, [])),
                ): _entity_selector(["binary_sensor", "input_boolean", "switch"], multiple=True),
                vol.Required(
                    CONF_OCCUPANCY_ACTION,
                    default=self._default(CONF_OCCUPANCY_ACTION, OccupancyAction.DELAY.value),
                ): _select_selector(
                    [item.value for item in OccupancyAction], CONF_OCCUPANCY_ACTION
                ),
                vol.Required(
                    CONF_OCCUPANCY_MAX_DELAY,
                    default=self._default(CONF_OCCUPANCY_MAX_DELAY, DEFAULT_OCCUPANCY_MAX_DELAY),
                ): _number_selector(1, MAX_OCCUPANCY_DELAY, unit="min"),
                vol.Required(
                    CONF_OCCUPANCY_STOP_DURING_RUN,
                    default=(
                        self._default(CONF_OCCUPANCY_STOP_DURING_RUN, False)
                        if CONF_OCCUPANCY_ENTITIES in self._config
                        else DEFAULT_OCCUPANCY_STOP_DURING_RUN
                    ),
                ): BooleanSelector(),
            }
        )
        return self.async_show_form(step_id="occupancy", data_schema=schema, errors=errors)

    # --- AI -----------------------------------------------------------------

    async def async_step_ai(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if not self.hass.states.async_entity_ids(AI_TASK_DOMAIN):
            # Nothing to pick. Existing AI settings are kept, in case the AI
            # task integration is only temporarily not loaded.
            return await self._async_finish()

        errors: dict[str, str] = {}
        if user_input is not None:
            entity = user_input.get(CONF_AI_TASK_ENTITY) or None
            if entity is None:
                for key in _AI_KEYS:
                    self._config.pop(key, None)
                return await self._async_finish()
            weekday = user_input.get(CONF_AI_REPORT_WEEKDAY)
            report_time = user_input.get(CONF_AI_REPORT_TIME)
            camera = user_input.get(CONF_AI_CAMERA) or None
            provider = user_input.get(CONF_AI_LLMVISION_PROVIDER) or None
            if (weekday in (None, "")) != (report_time in (None, "")):
                errors["base"] = "ai_report_incomplete"
            if camera and not provider:
                errors[CONF_AI_LLMVISION_PROVIDER] = "ai_provider_required"
            if not errors:
                has_report = weekday not in (None, "")
                self._config[CONF_AI_TASK_ENTITY] = entity
                self._set(CONF_AI_NOTIFY_SERVICE, user_input.get(CONF_AI_NOTIFY_SERVICE) or None)
                self._set(CONF_AI_REPORT_WEEKDAY, int(weekday) if has_report else None)
                self._set(
                    CONF_AI_REPORT_TIME,
                    cv.time(report_time).strftime("%H:%M:%S") if has_report else None,
                )
                self._set(CONF_AI_CAMERA, camera)
                self._set(CONF_AI_LLMVISION_PROVIDER, provider if camera else None)
                return await self._async_finish()

        weekday = self._default(CONF_AI_REPORT_WEEKDAY)
        schema = vol.Schema(
            {
                _optional(
                    CONF_AI_TASK_ENTITY, self._default(CONF_AI_TASK_ENTITY)
                ): _entity_selector(AI_TASK_DOMAIN),
                _optional(
                    CONF_AI_NOTIFY_SERVICE, self._default(CONF_AI_NOTIFY_SERVICE)
                ): SelectSelector(
                    SelectSelectorConfig(
                        options=self._notify_services(),
                        mode=SelectSelectorMode.DROPDOWN,
                    )
                ),
                _optional(
                    CONF_AI_REPORT_WEEKDAY, str(weekday) if weekday is not None else None
                ): _select_selector([str(day) for day in range(7)], CONF_WEEKDAYS),
                _optional(CONF_AI_REPORT_TIME, self._default(CONF_AI_REPORT_TIME)): TimeSelector(),
                _optional(CONF_AI_CAMERA, self._default(CONF_AI_CAMERA)): _entity_selector(
                    "camera"
                ),
                _optional(
                    CONF_AI_LLMVISION_PROVIDER, self._default(CONF_AI_LLMVISION_PROVIDER)
                ): ConfigEntrySelector(ConfigEntrySelectorConfig(integration=LLMVISION_DOMAIN)),
            }
        )
        return self.async_show_form(step_id="ai", data_schema=schema, errors=errors)

    def _notify_services(self) -> list[str]:
        services = [PERSISTENT_NOTIFICATION_SERVICE]
        services += sorted(
            f"{NOTIFY_DOMAIN}.{service}"
            for service in self.hass.services.async_services_for_domain(NOTIFY_DOMAIN)
        )
        # Keep a stored service selectable even if it's no longer registered.
        if (current := self._config.get(CONF_AI_NOTIFY_SERVICE)) and current not in services:
            services.append(current)
        return services


class IrrigationManagerConfigFlow(ScheduleFlowMixin, ConfigFlow, domain=DOMAIN):
    """Create a schedule."""

    VERSION = 1

    def __init__(self) -> None:
        super().__init__()
        self._notes: list[str] = []
        self._bhyve_candidates: list[dict[str, Any]] | None = None
        self._bhyve_switch: str | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        options = ["create", "import_legacy", "import_bhyve"]
        if self.hass.states.async_entity_ids(AI_TASK_DOMAIN):
            options.append("describe")
        return self.async_show_menu(step_id="user", menu_options=options)

    async def async_step_create(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        return await self.async_step_name()

    async def async_step_name(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            name = user_input[CONF_NAME].strip()
            errors = _name_errors(self.hass, name, exclude_entry_id=None)
            if not errors:
                self._config[CONF_NAME] = name
                return await self.async_step_zones()

        notes = f"\n\nNotes:\n{_bullets(self._notes)}" if self._notes else ""
        return self.async_show_form(
            step_id="name",
            data_schema=_name_schema(self._config.get(CONF_NAME)),
            errors=errors,
            description_placeholders={"notes": notes},
        )

    # --- imports ------------------------------------------------------------

    async def async_step_import_legacy(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        found = migration.async_read_legacy_helpers(self.hass)
        if not found["config"] and found["zone_minutes"] is None:
            return self.async_abort(reason="no_legacy_helpers")

        other_notes = [
            f"{candidate['config'].get(CONF_NAME, 'Other helper')} (not imported): {note}"
            for candidate in found["candidates"]
            for note in candidate["notes"]
        ]
        if user_input is None:
            return self.async_show_form(
                step_id="import_legacy",
                data_schema=vol.Schema({}),
                description_placeholders={
                    "found": _bullets(found["found"]) or "None.",
                    "notes": _bullets([*found["notes"], *other_notes]) or "None.",
                },
            )

        config = dict(found["config"])
        # A threshold without a rain sensor can't turn the rain condition on;
        # it only becomes the rain step's default.
        if (threshold := config.pop(CONF_RAIN_THRESHOLD, None)) is not None:
            self._prefill[CONF_RAIN_THRESHOLD] = threshold
        self._config.update(config)
        if found["zone_minutes"] is not None:
            self._zone_minutes_default = int(found["zone_minutes"])
        self._notes = [*found["notes"], *other_notes]
        return await self.async_step_name()

    async def async_step_import_bhyve(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if self._bhyve_candidates is None:
            self._bhyve_candidates = migration.async_read_bhyve_programs(self.hass)
        supported = [candidate for candidate in self._bhyve_candidates if candidate["supported"]]
        unsupported = [
            candidate for candidate in self._bhyve_candidates if not candidate["supported"]
        ]
        if not supported:
            return self.async_abort(
                reason="no_bhyve_programs",
                description_placeholders={
                    "programs": self._candidate_notes(unsupported) or "No programs were found."
                },
            )

        if user_input is not None:
            candidate = supported[int(user_input[FIELD_PROGRAM])]
            self._config.update(deepcopy(candidate["config"]))
            self._bhyve_switch = candidate["program_switch"]
            self._notes = list(candidate["notes"])
            return await self.async_step_name()

        options = [
            SelectOptionDict(value=str(index), label=self._candidate_label(candidate))
            for index, candidate in enumerate(supported)
        ]
        schema = vol.Schema(
            {
                vol.Required(FIELD_PROGRAM, default="0"): SelectSelector(
                    SelectSelectorConfig(options=options, mode=SelectSelectorMode.LIST)
                )
            }
        )
        return self.async_show_form(
            step_id="import_bhyve",
            data_schema=schema,
            description_placeholders={
                "unsupported": self._candidate_notes(unsupported) or "None."
            },
        )

    @staticmethod
    def _candidate_label(candidate: Mapping[str, Any]) -> str:
        name = candidate["config"].get(CONF_NAME) or candidate["source"]
        label = f"{name} (program {candidate['slot']})"
        return label if candidate.get("enabled") else f"{label}, off on the device"

    @staticmethod
    def _candidate_notes(candidates: Iterable[Mapping[str, Any]]) -> str:
        lines = [
            f"{candidate['config'].get(CONF_NAME) or candidate['source']}: {'; '.join(candidate['notes'])}"
            for candidate in candidates
        ]
        return _bullets(lines)

    async def async_step_describe(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        placeholders = {"error": ""}
        if user_input is not None:
            entity = user_input[CONF_AI_TASK_ENTITY]
            try:
                result = await ai.async_parse_schedule_description(
                    self.hass, entity, user_input[FIELD_DESCRIPTION]
                )
            except HomeAssistantError as err:
                errors["base"] = "describe_failed"
                placeholders["error"] = str(err)
            else:
                self._config.update(deepcopy(result["config"]))
                self._prefill[CONF_AI_TASK_ENTITY] = entity
                self._notes = list(result["warnings"])
                return await self.async_step_name()

        entities = sorted(self.hass.states.async_entity_ids(AI_TASK_DOMAIN))
        schema = vol.Schema(
            {
                _required(
                    CONF_AI_TASK_ENTITY,
                    (user_input or {}).get(CONF_AI_TASK_ENTITY) or (entities[0] if entities else None),
                ): _entity_selector(AI_TASK_DOMAIN),
                _required(
                    FIELD_DESCRIPTION, (user_input or {}).get(FIELD_DESCRIPTION)
                ): TextSelector(TextSelectorConfig(multiline=True)),
            }
        )
        return self.async_show_form(
            step_id="describe",
            data_schema=schema,
            errors=errors,
            description_placeholders=placeholders,
        )

    # --- saving -------------------------------------------------------------

    async def _async_finish(self) -> ConfigFlowResult:
        if self._bhyve_switch is not None:
            return await self.async_step_bhyve_disable()
        return self.async_create_entry(title=self._config[CONF_NAME], data=self._config)

    async def async_step_bhyve_disable(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        placeholders = {"switch": self._bhyve_switch or "", "error": ""}
        if user_input is not None:
            # Only an explicit tick changes the device.
            if user_input.get(FIELD_DISABLE_PROGRAM) and self._bhyve_switch is not None:
                try:
                    await migration.async_disable_bhyve_program(self.hass, self._bhyve_switch)
                except HomeAssistantError as err:
                    errors["base"] = "disable_failed"
                    placeholders["error"] = str(err)
            if not errors:
                return self.async_create_entry(
                    title=self._config[CONF_NAME], data=self._config
                )

        schema = vol.Schema(
            {vol.Required(FIELD_DISABLE_PROGRAM, default=False): BooleanSelector()}
        )
        return self.async_show_form(
            step_id="bhyve_disable",
            data_schema=schema,
            errors=errors,
            description_placeholders=placeholders,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> IrrigationManagerOptionsFlow:
        return IrrigationManagerOptionsFlow()


class IrrigationManagerOptionsFlow(ScheduleFlowMixin, OptionsFlow):
    """Edit a schedule. Saves the full config to entry.options."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is None:
            self._config = deepcopy(merged_config(self.config_entry))
        else:
            name = user_input[CONF_NAME].strip()
            errors = _name_errors(
                self.hass, name, exclude_entry_id=self.config_entry.entry_id
            )
            if not errors:
                self._config[CONF_NAME] = name
                return await self.async_step_zones()

        return self.async_show_form(
            step_id="init",
            data_schema=_name_schema(
                self._config.get(CONF_NAME, self.config_entry.title)
            ),
            errors=errors,
        )

    async def _async_finish(self) -> ConfigFlowResult:
        if self.config_entry.title != self._config[CONF_NAME]:
            self.hass.config_entries.async_update_entry(
                self.config_entry, title=self._config[CONF_NAME]
            )
        return self.async_create_entry(data=self._config)
