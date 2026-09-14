"""Config entry diagnostics: config, runner state, history and zone drivers."""
from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import HomeAssistant

from .const import CONF_AI_NOTIFY_SERVICE, merged_config, zone_entity_ids
from .drivers import async_get_driver

# Notify service names usually carry a person's or phone's name.
TO_REDACT = {CONF_AI_NOTIFY_SERVICE}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Diagnostics for one schedule."""
    config = merged_config(entry)
    data: dict[str, Any] = {
        "entry": {
            "title": entry.title,
            "version": entry.version,
            "state": entry.state.value,
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": async_redact_data(dict(entry.options), TO_REDACT),
        },
        "zones": {},
        "snapshot": None,
        "history": [],
    }

    for entity_id in zone_entity_ids(config):
        driver = async_get_driver(hass, entity_id)
        state = hass.states.get(entity_id)
        data["zones"][entity_id] = {
            "driver": type(driver).__name__,
            "native_duration": driver.native_duration,
            "state": state.state if state is not None else None,
        }

    if entry.state is ConfigEntryState.LOADED:
        runner = entry.runtime_data
        data["snapshot"] = async_redact_data(runner.snapshot(), TO_REDACT)
        data["history"] = async_redact_data(runner.history(), TO_REDACT)

    return data
