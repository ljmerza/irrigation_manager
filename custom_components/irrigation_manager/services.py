"""Domain services, addressed by config entry ID.

Per-schedule services act on one loaded schedule, and the ones that change it
optionally return its updated snapshot. The *_all services act on every loaded
schedule. The AI services load ai.py on demand.
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import (
    HomeAssistant,
    ServiceCall,
    ServiceResponse,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import config_validation as cv, device_registry as dr

from .const import (
    ATTR_CONFIG_ENTRY_ID,
    ATTR_DAYS,
    ATTR_ENABLED,
    ATTR_HOURS,
    ATTR_LIMIT,
    ATTR_MINUTES,
    ATTR_SKIP,
    ATTR_ZONE,
    CONF_AI_TASK_ENTITY,
    CONF_ZONE_ENTITY,
    CONF_ZONE_MINUTES,
    CONF_ZONES,
    DOMAIN,
    HISTORY_LIMIT,
    MAX_RAIN_DELAY_HOURS,
    MAX_ZONE_MINUTES,
    MIN_ZONE_MINUTES,
    SERVICE_EVALUATE,
    SERVICE_EXPLAIN_SKIPS,
    SERVICE_GENERATE_REPORT,
    SERVICE_GET_HISTORY,
    SERVICE_PAUSE_ALL,
    SERVICE_RESUME_ALL,
    SERVICE_RUN_NOW,
    SERVICE_RUN_ZONE,
    SERVICE_SET_ENABLED,
    SERVICE_SET_RAIN_DELAY,
    SERVICE_SKIP_NEXT,
    SERVICE_STOP,
    SERVICE_STOP_ALL,
)

if TYPE_CHECKING:
    from .runner import ScheduleRunner

DEFAULT_REPORT_DAYS = 7
MAX_REPORT_DAYS = 90


def _finite(value: float) -> float:
    # vol.Range lets NaN through: every comparison with NaN is False.
    if not math.isfinite(value):
        raise vol.Invalid("must be a finite number")
    return value


_ENTRY_ID = {vol.Required(ATTR_CONFIG_ENTRY_ID): cv.string}
_MINUTES = vol.All(vol.Coerce(int), vol.Range(min=MIN_ZONE_MINUTES, max=MAX_ZONE_MINUTES))

RUN_NOW_SCHEMA = vol.Schema({**_ENTRY_ID, vol.Optional(ATTR_MINUTES): _MINUTES})
SKIP_NEXT_SCHEMA = vol.Schema(
    {**_ENTRY_ID, vol.Optional(ATTR_SKIP, default=True): cv.boolean}
)
STOP_SCHEMA = vol.Schema(_ENTRY_ID)
SET_RAIN_DELAY_SCHEMA = vol.Schema(
    {
        **_ENTRY_ID,
        vol.Required(ATTR_HOURS): vol.All(
            vol.Coerce(float), _finite, vol.Range(min=0, max=MAX_RAIN_DELAY_HOURS)
        ),
    }
)
RUN_ZONE_SCHEMA = vol.Schema(
    {
        **_ENTRY_ID,
        vol.Required(ATTR_ZONE): cv.entity_id,
        vol.Optional(ATTR_MINUTES): _MINUTES,
    }
)
SET_ENABLED_SCHEMA = vol.Schema({**_ENTRY_ID, vol.Required(ATTR_ENABLED): cv.boolean})
EVALUATE_SCHEMA = vol.Schema(_ENTRY_ID)
GET_HISTORY_SCHEMA = vol.Schema(
    {
        **_ENTRY_ID,
        vol.Optional(ATTR_LIMIT): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=HISTORY_LIMIT)
        ),
    }
)
ALL_SCHEDULES_SCHEMA = vol.Schema({})
AI_SCHEMA = vol.Schema(
    {
        **_ENTRY_ID,
        vol.Optional(ATTR_DAYS, default=DEFAULT_REPORT_DAYS): vol.All(
            vol.Coerce(int), vol.Range(min=1, max=MAX_REPORT_DAYS)
        ),
    }
)


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the domain services once; they serve every schedule."""
    if hass.services.has_service(DOMAIN, SERVICE_RUN_NOW):
        return

    async def _run_now(call: ServiceCall) -> ServiceResponse:
        runner = _runner_for_call(hass, call)
        await async_run_now(runner, call.data.get(ATTR_MINUTES))
        return runner.snapshot()

    async def _skip_next(call: ServiceCall) -> ServiceResponse:
        runner = _runner_for_call(hass, call)
        await runner.async_set_skip_next(call.data[ATTR_SKIP])
        return runner.snapshot()

    async def _stop(call: ServiceCall) -> ServiceResponse:
        runner = _runner_for_call(hass, call)
        await runner.async_stop_run()
        return runner.snapshot()

    async def _set_rain_delay(call: ServiceCall) -> ServiceResponse:
        runner = _runner_for_call(hass, call)
        await runner.async_set_rain_delay(call.data[ATTR_HOURS])
        return runner.snapshot()

    async def _run_zone(call: ServiceCall) -> ServiceResponse:
        runner = _runner_for_call(hass, call)
        zone = call.data[ATTR_ZONE]
        configured = {
            item[CONF_ZONE_ENTITY]: item[CONF_ZONE_MINUTES]
            for item in runner.config.get(CONF_ZONES) or []
        }
        if zone not in configured:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="zone_not_in_schedule",
                translation_placeholders={"zone": zone, "name": runner.entry.title},
            )
        _raise_if_running(runner)
        minutes = call.data.get(ATTR_MINUTES, configured[zone])
        await runner.async_run_zone(zone, int(minutes))
        return runner.snapshot()

    async def _set_enabled(call: ServiceCall) -> ServiceResponse:
        runner = _runner_for_call(hass, call)
        await runner.async_set_enabled(call.data[ATTR_ENABLED])
        return runner.snapshot()

    async def _evaluate(call: ServiceCall) -> ServiceResponse:
        return await _runner_for_call(hass, call).async_evaluate()

    async def _get_history(call: ServiceCall) -> ServiceResponse:
        runner = _runner_for_call(hass, call)
        return {"history": runner.history(call.data.get(ATTR_LIMIT))}

    async def _pause_all(call: ServiceCall) -> None:
        for runner in async_loaded_runners(hass):
            await runner.async_set_paused(True)

    async def _resume_all(call: ServiceCall) -> None:
        for runner in async_loaded_runners(hass):
            await runner.async_set_paused(False)

    async def _stop_all(call: ServiceCall) -> None:
        for runner in async_loaded_runners(hass):
            await runner.async_stop_run()

    async def _generate_report(call: ServiceCall) -> ServiceResponse:
        runner = _ai_runner_for_call(hass, call)
        from . import ai  # noqa: PLC0415 — only needed when AI is configured

        return {"text": await ai.async_generate_report(hass, runner, days=call.data[ATTR_DAYS])}

    async def _explain_skips(call: ServiceCall) -> ServiceResponse:
        runner = _ai_runner_for_call(hass, call)
        from . import ai  # noqa: PLC0415 — only needed when AI is configured

        return {"text": await ai.async_explain_skips(hass, runner, days=call.data[ATTR_DAYS])}

    optional = SupportsResponse.OPTIONAL
    services: tuple[tuple[str, Any, vol.Schema, SupportsResponse], ...] = (
        (SERVICE_RUN_NOW, _run_now, RUN_NOW_SCHEMA, optional),
        (SERVICE_SKIP_NEXT, _skip_next, SKIP_NEXT_SCHEMA, optional),
        (SERVICE_STOP, _stop, STOP_SCHEMA, optional),
        (SERVICE_SET_RAIN_DELAY, _set_rain_delay, SET_RAIN_DELAY_SCHEMA, optional),
        (SERVICE_RUN_ZONE, _run_zone, RUN_ZONE_SCHEMA, optional),
        (SERVICE_SET_ENABLED, _set_enabled, SET_ENABLED_SCHEMA, optional),
        (SERVICE_EVALUATE, _evaluate, EVALUATE_SCHEMA, SupportsResponse.ONLY),
        (SERVICE_GET_HISTORY, _get_history, GET_HISTORY_SCHEMA, SupportsResponse.ONLY),
        (SERVICE_PAUSE_ALL, _pause_all, ALL_SCHEDULES_SCHEMA, SupportsResponse.NONE),
        (SERVICE_RESUME_ALL, _resume_all, ALL_SCHEDULES_SCHEMA, SupportsResponse.NONE),
        (SERVICE_STOP_ALL, _stop_all, ALL_SCHEDULES_SCHEMA, SupportsResponse.NONE),
        (SERVICE_GENERATE_REPORT, _generate_report, AI_SCHEMA, optional),
        (SERVICE_EXPLAIN_SKIPS, _explain_skips, AI_SCHEMA, optional),
    )
    for name, handler, schema, supports_response in services:
        hass.services.async_register(
            DOMAIN, name, handler, schema=schema, supports_response=supports_response
        )


async def async_run_now(runner: ScheduleRunner, minutes: int | None = None) -> None:
    """Start a manual run, raising translated errors for the runner's refusals."""
    _raise_if_running(runner)
    if not runner.config.get(CONF_ZONES):
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="no_zones",
            translation_placeholders={"name": runner.entry.title},
        )
    await runner.async_run_now(minutes)


@callback
def async_loaded_runners(hass: HomeAssistant) -> list[ScheduleRunner]:
    """Runners of every loaded schedule."""
    return [
        entry.runtime_data
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.state is ConfigEntryState.LOADED
    ]


@callback
def async_is_schedule_device(hass: HomeAssistant, device_id: str) -> bool:
    """Whether the device registry device is a schedule's device."""
    device = dr.async_get(hass).async_get(device_id)
    return device is not None and any(
        domain == DOMAIN for domain, _ in device.identifiers
    )


@callback
def async_runner_for_device(
    hass: HomeAssistant, device_id: str
) -> ScheduleRunner | None:
    """The loaded schedule behind a device, or None."""
    device = dr.async_get(hass).async_get(device_id)
    if device is None:
        return None
    for domain, entry_id in device.identifiers:
        if domain != DOMAIN:
            continue
        entry = hass.config_entries.async_get_entry(entry_id)
        if (
            entry is not None
            and entry.domain == DOMAIN
            and entry.state is ConfigEntryState.LOADED
        ):
            return entry.runtime_data
    return None


def _raise_if_running(runner: ScheduleRunner) -> None:
    if runner.running:
        raise HomeAssistantError(
            translation_domain=DOMAIN,
            translation_key="already_running",
            translation_placeholders={"name": runner.entry.title},
        )


@callback
def _runner_for_call(hass: HomeAssistant, call: ServiceCall) -> ScheduleRunner:
    entry_id = call.data[ATTR_CONFIG_ENTRY_ID]
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="entry_not_found",
            translation_placeholders={"config_entry_id": entry_id},
        )
    if entry.state is not ConfigEntryState.LOADED:
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="entry_not_loaded",
            translation_placeholders={"name": entry.title},
        )
    return entry.runtime_data


@callback
def _ai_runner_for_call(hass: HomeAssistant, call: ServiceCall) -> ScheduleRunner:
    runner = _runner_for_call(hass, call)
    if not runner.config.get(CONF_AI_TASK_ENTITY):
        raise ServiceValidationError(
            translation_domain=DOMAIN,
            translation_key="ai_not_configured",
            translation_placeholders={"name": runner.entry.title},
        )
    return runner
