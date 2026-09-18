"""Run notifications for one schedule.

The runner calls async_send_run_notification when a run starts, ends or is
skipped. The schedule's config picks the events (CONF_NOTIFY_EVENTS) and the
targets: notify services such as `notify.mobile_app_phone` or
`persistent_notification.create` (CONF_NOTIFY_SERVICES), and notify entities,
sent with `notify.send_message` (CONF_NOTIFY_ENTITIES). A target that fails is
logged and the others are still sent; nothing here raises.

(Not named notify.py: Home Assistant would load that as a notify platform.)
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
import logging
from typing import Any

from homeassistant.core import HomeAssistant

from .ai import async_send_notification
from .const import (
    CONF_NOTIFY_ENTITIES,
    CONF_NOTIFY_EVENTS,
    CONF_NOTIFY_SERVICES,
    DOMAIN,
    NotifyEvent,
    Status,
)

_LOGGER = logging.getLogger(__name__)

NOTIFY_DOMAIN = "notify"
SERVICE_SEND_MESSAGE = "send_message"

_SKIP_REASONS = {
    Status.SKIPPED_RAIN: "recent rain",
    Status.SKIPPED_FORECAST: "rain in the forecast",
    Status.SKIPPED_MOISTURE: "soil moisture",
    Status.SKIPPED_TEMPERATURE: "temperature",
    Status.SKIPPED_WIND: "wind",
    Status.SKIPPED_OCCUPANCY: "an occupancy entity is on",
    Status.SKIPPED_RAIN_DELAY: "rain delay",
    Status.SKIPPED_MANUAL: "skip next was set",
    Status.SKIPPED_BUSY: "the previous run was still going",
}

_STOP_REASONS = {
    Status.STOPPED_RAIN: "rain started",
    Status.STOPPED_OCCUPANCY: "an occupancy entity turned on",
}


def notify_enabled(config: Mapping[str, Any], event: NotifyEvent) -> bool:
    return event.value in (config.get(CONF_NOTIFY_EVENTS) or [])


def _name(hass: HomeAssistant, entity_id: str) -> str:
    state = hass.states.get(entity_id)
    return state.name if state is not None else entity_id


def _names(hass: HomeAssistant, entity_ids: Iterable[str]) -> str:
    return ", ".join(_name(hass, entity_id) for entity_id in entity_ids)


def _minutes(value: float) -> str:
    return f"{value:g} min"


def started_message(hass: HomeAssistant, zones: Iterable[str], *, manual: bool) -> str:
    message = f"Started watering {_names(hass, zones)}"
    return f"{message} (manual run)." if manual else f"{message}."


def skipped_message(status: Status) -> str:
    reason = _SKIP_REASONS.get(status) or status.value.removeprefix("skipped_").replace("_", " ")
    return f"Skipped watering ({reason})."


def ended_message(
    hass: HomeAssistant,
    event: NotifyEvent,
    outcome: Status,
    zone_results: Iterable[Mapping[str, Any]],
    unclosed: Iterable[str],
    total_minutes: float,
) -> str:
    """Message for RUN_FINISHED, RUN_STOPPED or RUN_ERROR."""
    if event is NotifyEvent.RUN_FINISHED:
        return f"Finished watering after {_minutes(total_minutes)}."
    if event is NotifyEvent.RUN_STOPPED:
        reason = _STOP_REASONS.get(outcome, "stopped manually")
        return f"Stopped watering early ({reason}) after {_minutes(total_minutes)}."

    lines = ["Watering error."]
    if outcome is Status.INTERRUPTED:
        lines.append(
            f"The run was interrupted by a Home Assistant restart or reload after "
            f"{_minutes(total_minutes)}."
        )
    elif outcome in _STOP_REASONS:
        lines.append(f"The run stopped early ({_STOP_REASONS[outcome]}).")
    lines.extend(
        f"{_name(hass, result['entity_id'])}: {result['error']}"
        for result in zone_results
        if result.get("error")
    )
    if unclosed := list(unclosed):
        lines.append(f"May still be open: {_names(hass, unclosed)}.")
    return "\n".join(lines)


async def async_send_run_notification(
    hass: HomeAssistant,
    config: Mapping[str, Any],
    entry_id: str,
    *,
    title: str,
    message: str,
) -> None:
    """Send `message` to every configured target."""
    for service in config.get(CONF_NOTIFY_SERVICES) or []:
        try:
            await async_send_notification(
                hass,
                service,
                title=title,
                message=message,
                notification_id=f"{DOMAIN}_{entry_id}_run",
            )
        except Exception as err:  # noqa: BLE001 — one target must not block the others
            _LOGGER.warning("%s: notification via %s failed: %s", title, service, err)

    for entity_id in config.get(CONF_NOTIFY_ENTITIES) or []:
        try:
            await hass.services.async_call(
                NOTIFY_DOMAIN,
                SERVICE_SEND_MESSAGE,
                {"entity_id": entity_id, "title": title, "message": message},
                blocking=True,
            )
        except Exception as err:  # noqa: BLE001 — one target must not block the others
            _LOGGER.warning("%s: notification to %s failed: %s", title, entity_id, err)
