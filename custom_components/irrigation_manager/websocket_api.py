"""Websocket commands for the sidebar panel.

Every command is admin-only, matching the panel's require_admin. Schedules are
the loaded config entries of this domain; each entry's runtime_data is its
ScheduleRunner. The list and the subscription return runner snapshots sorted by
name. Per-schedule actions return the updated snapshot; the *_all actions return
the updated list.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable
import math
from typing import TYPE_CHECKING, Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import (
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
    SIGNAL_SCHEDULES_CHANGED,
)
from .services import DEFAULT_REPORT_DAYS, MAX_REPORT_DAYS

if TYPE_CHECKING:
    from .runner import ScheduleRunner

DATA_WEBSOCKET_REGISTERED = f"{DOMAIN}_websocket_registered"

ATTR_ENTRY_ID = "entry_id"

ERR_ZONE_NOT_IN_SCHEDULE = "zone_not_in_schedule"
ERR_AI_NOT_CONFIGURED = "ai_not_configured"


def _finite(value: float) -> float:
    # vol.Range lets NaN through: every comparison with NaN is False.
    if not math.isfinite(value):
        raise vol.Invalid("must be a finite number")
    return value


_MINUTES = vol.All(vol.Coerce(int), vol.Range(min=MIN_ZONE_MINUTES, max=MAX_ZONE_MINUTES))
_DAYS = vol.All(vol.Coerce(int), vol.Range(min=1, max=MAX_REPORT_DAYS))


@callback
def async_setup(hass: HomeAssistant) -> None:
    """Register websocket commands. Safe to call repeatedly."""
    if hass.data.get(DATA_WEBSOCKET_REGISTERED):
        return
    hass.data[DATA_WEBSOCKET_REGISTERED] = True
    for handler in (
        ws_schedules,
        ws_subscribe,
        ws_run_now,
        ws_stop,
        ws_skip_next,
        ws_set_enabled,
        ws_set_rain_delay,
        ws_run_zone,
        ws_evaluate,
        ws_history,
        ws_pause_all,
        ws_resume_all,
        ws_stop_all,
        ws_generate_report,
        ws_explain_skips,
    ):
        websocket_api.async_register_command(hass, handler)


@callback
def _runners(hass: HomeAssistant) -> list[ScheduleRunner]:
    runners = [
        entry.runtime_data
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.state is ConfigEntryState.LOADED
        and getattr(entry, "runtime_data", None) is not None
    ]
    return sorted(runners, key=lambda runner: (runner.entry.title.casefold(), runner.entry.entry_id))


@callback
def _schedules(hass: HomeAssistant) -> dict[str, Any]:
    return {"schedules": [runner.snapshot() for runner in _runners(hass)]}


@callback
def _get_runner(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> ScheduleRunner | None:
    """The schedule's runner, or None after sending not_found."""
    entry = hass.config_entries.async_get_entry(msg[ATTR_ENTRY_ID])
    if (
        entry is None
        or entry.domain != DOMAIN
        or entry.state is not ConfigEntryState.LOADED
        or getattr(entry, "runtime_data", None) is None
    ):
        connection.send_error(
            msg["id"], websocket_api.ERR_NOT_FOUND, "Schedule not found or not loaded"
        )
        return None
    return entry.runtime_data


async def _async_action(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    action: Callable[[ScheduleRunner], Awaitable[None]],
) -> None:
    if (runner := _get_runner(hass, connection, msg)) is None:
        return
    await _async_run_action(connection, msg, runner, action)


async def _async_run_action(
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    runner: ScheduleRunner,
    action: Callable[[ScheduleRunner], Awaitable[None]],
) -> None:
    try:
        await action(runner)
    except HomeAssistantError as err:
        connection.send_error(msg["id"], websocket_api.ERR_HOME_ASSISTANT_ERROR, str(err))
        return
    connection.send_result(msg["id"], runner.snapshot())


async def _async_all(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    action: Callable[[ScheduleRunner], Awaitable[None]],
) -> None:
    try:
        for runner in _runners(hass):
            await action(runner)
    except HomeAssistantError as err:
        connection.send_error(msg["id"], websocket_api.ERR_HOME_ASSISTANT_ERROR, str(err))
        return
    connection.send_result(msg["id"], _schedules(hass))


async def _async_ai_text(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
    generate: Callable[..., Awaitable[str]],
) -> None:
    from . import ai  # noqa: PLC0415 — only needed when AI is configured

    if (runner := _get_runner(hass, connection, msg)) is None:
        return
    if not runner.config.get(CONF_AI_TASK_ENTITY):
        connection.send_error(
            msg["id"],
            ERR_AI_NOT_CONFIGURED,
            f"{runner.entry.title} has no AI task entity configured",
        )
        return
    try:
        text = await generate(hass, runner, days=msg[ATTR_DAYS])
    except ai.AiNotConfigured as err:
        connection.send_error(msg["id"], ERR_AI_NOT_CONFIGURED, str(err))
        return
    except HomeAssistantError as err:
        connection.send_error(msg["id"], websocket_api.ERR_HOME_ASSISTANT_ERROR, str(err))
        return
    connection.send_result(msg["id"], {"text": text})


# --- list and subscription ----------------------------------------------------


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/schedules"})
@callback
def ws_schedules(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Return every loaded schedule's snapshot."""
    connection.send_result(msg["id"], _schedules(hass))


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/subscribe"})
@callback
def ws_subscribe(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Send the schedule list now and again whenever any schedule changes."""
    msg_id = msg["id"]

    @callback
    def forward() -> None:
        connection.send_message(websocket_api.event_message(msg_id, _schedules(hass)))

    connection.subscriptions[msg_id] = async_dispatcher_connect(
        hass, SIGNAL_SCHEDULES_CHANGED, forward
    )
    connection.send_result(msg_id)
    forward()


# --- per-schedule actions -----------------------------------------------------


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/run_now",
        vol.Required(ATTR_ENTRY_ID): str,
        vol.Optional(ATTR_MINUTES): _MINUTES,
    }
)
@websocket_api.async_response
async def ws_run_now(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Start a run now; `minutes` overrides every zone."""
    await _async_action(
        hass, connection, msg, lambda runner: runner.async_run_now(msg.get(ATTR_MINUTES))
    )


@websocket_api.require_admin
@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/stop", vol.Required(ATTR_ENTRY_ID): str}
)
@websocket_api.async_response
async def ws_stop(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Stop the active run."""
    await _async_action(hass, connection, msg, lambda runner: runner.async_stop_run())


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/skip_next",
        vol.Required(ATTR_ENTRY_ID): str,
        vol.Optional(ATTR_SKIP, default=True): bool,
    }
)
@websocket_api.async_response
async def ws_skip_next(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Set or clear skip-next."""
    await _async_action(
        hass, connection, msg, lambda runner: runner.async_set_skip_next(msg[ATTR_SKIP])
    )


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/set_enabled",
        vol.Required(ATTR_ENTRY_ID): str,
        vol.Required(ATTR_ENABLED): bool,
    }
)
@websocket_api.async_response
async def ws_set_enabled(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Enable or disable the schedule."""
    await _async_action(
        hass, connection, msg, lambda runner: runner.async_set_enabled(msg[ATTR_ENABLED])
    )


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/set_rain_delay",
        vol.Required(ATTR_ENTRY_ID): str,
        vol.Required(ATTR_HOURS): vol.All(
            vol.Coerce(float), _finite, vol.Range(min=0, max=MAX_RAIN_DELAY_HOURS)
        ),
    }
)
@websocket_api.async_response
async def ws_set_rain_delay(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Skip scheduled runs for `hours` from now; 0 clears the delay."""
    await _async_action(
        hass, connection, msg, lambda runner: runner.async_set_rain_delay(msg[ATTR_HOURS])
    )


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/run_zone",
        vol.Required(ATTR_ENTRY_ID): str,
        vol.Required(ATTR_ZONE): str,
        vol.Optional(ATTR_MINUTES): _MINUTES,
    }
)
@websocket_api.async_response
async def ws_run_zone(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Run one zone of the schedule; minutes default to the zone's configured time."""
    if (runner := _get_runner(hass, connection, msg)) is None:
        return
    zones = {
        zone[CONF_ZONE_ENTITY]: zone[CONF_ZONE_MINUTES]
        for zone in runner.config.get(CONF_ZONES) or []
    }
    zone = msg[ATTR_ZONE]
    if zone not in zones:
        connection.send_error(
            msg["id"],
            ERR_ZONE_NOT_IN_SCHEDULE,
            f"{zone} is not a zone of {runner.entry.title}",
        )
        return
    minutes = int(msg.get(ATTR_MINUTES, zones[zone]))
    await _async_run_action(
        connection, msg, runner, lambda runner: runner.async_run_zone(zone, minutes)
    )


@websocket_api.require_admin
@websocket_api.websocket_command(
    {vol.Required("type"): f"{DOMAIN}/evaluate", vol.Required(ATTR_ENTRY_ID): str}
)
@websocket_api.async_response
async def ws_evaluate(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """What the conditions say right now, without running anything."""
    if (runner := _get_runner(hass, connection, msg)) is None:
        return
    try:
        result = await runner.async_evaluate()
    except HomeAssistantError as err:
        connection.send_error(msg["id"], websocket_api.ERR_HOME_ASSISTANT_ERROR, str(err))
        return
    connection.send_result(msg["id"], result)


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/history",
        vol.Required(ATTR_ENTRY_ID): str,
        vol.Optional(ATTR_LIMIT): vol.All(vol.Coerce(int), vol.Range(min=1, max=HISTORY_LIMIT)),
    }
)
@callback
def ws_history(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Run and skip records, newest first."""
    if (runner := _get_runner(hass, connection, msg)) is None:
        return
    connection.send_result(msg["id"], {"history": runner.history(msg.get(ATTR_LIMIT))})


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/generate_report",
        vol.Required(ATTR_ENTRY_ID): str,
        vol.Optional(ATTR_DAYS, default=DEFAULT_REPORT_DAYS): _DAYS,
    }
)
@websocket_api.async_response
async def ws_generate_report(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """AI report on the schedule's last `days` days."""
    from . import ai  # noqa: PLC0415 — only needed when AI is configured

    await _async_ai_text(hass, connection, msg, ai.async_generate_report)


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/explain_skips",
        vol.Required(ATTR_ENTRY_ID): str,
        vol.Optional(ATTR_DAYS, default=DEFAULT_REPORT_DAYS): _DAYS,
    }
)
@websocket_api.async_response
async def ws_explain_skips(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """AI explanation of the schedule's skips in the last `days` days."""
    from . import ai  # noqa: PLC0415 — only needed when AI is configured

    await _async_ai_text(hass, connection, msg, ai.async_explain_skips)


# --- every schedule -----------------------------------------------------------


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/pause_all"})
@websocket_api.async_response
async def ws_pause_all(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Pause every loaded schedule. Active runs keep going."""
    await _async_all(hass, connection, msg, lambda runner: runner.async_set_paused(True))


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/resume_all"})
@websocket_api.async_response
async def ws_resume_all(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Resume every loaded schedule."""
    await _async_all(hass, connection, msg, lambda runner: runner.async_set_paused(False))


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/stop_all"})
@websocket_api.async_response
async def ws_stop_all(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Stop every active run."""
    await _async_all(hass, connection, msg, lambda runner: runner.async_stop_run())
