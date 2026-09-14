"""Irrigation Manager: scheduled watering for valve and switch entities.

One config entry per schedule. Each entry gets a ScheduleRunner (stored as
entry.runtime_data), a weekly AI report timer, and binary_sensor/button/number/
sensor/switch entities on one device. The domain services, the panel's websocket
commands and the sidebar panel are shared by every schedule. Home Assistant
loads the intent, device_trigger, device_condition and diagnostics platforms
itself.
"""
from __future__ import annotations

from homeassistant.config_entries import (
    SIGNAL_CONFIG_ENTRY_CHANGED,
    ConfigEntry,
    ConfigEntryChange,
)
from homeassistant.const import Platform
from homeassistant.core import HassJob, HomeAssistant, callback
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.dispatcher import (
    async_dispatcher_connect,
    async_dispatcher_send,
)
from homeassistant.helpers.typing import ConfigType

from . import panel, websocket_api
from .const import DOMAIN, SIGNAL_SCHEDULES_CHANGED, merged_config, zone_entity_ids
from .runner import ScheduleRunner
from .services import async_setup_services

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SENSOR,
    Platform.SWITCH,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type IrrigationConfigEntry = ConfigEntry[ScheduleRunner]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register what every schedule shares: services and websocket commands."""
    async_setup_services(hass)
    websocket_api.async_setup(hass)

    @callback
    def _entry_changed(change: ConfigEntryChange, entry: ConfigEntry) -> None:
        # Sent after an entry's state changes (loaded, unloaded, removed), so a
        # panel re-listing schedules sees the new state.
        if entry.domain == DOMAIN:
            async_dispatcher_send(hass, SIGNAL_SCHEDULES_CHANGED)

    async_dispatcher_connect(hass, SIGNAL_CONFIG_ENTRY_CHANGED, _entry_changed)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: IrrigationConfigEntry) -> bool:
    """Set up a schedule from a config entry."""
    runner = ScheduleRunner(hass, entry)
    await runner.async_setup()
    entry.runtime_data = runner

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    from . import ai  # noqa: PLC0415 — keeps the AI module out of import-time setup

    # Follows the runner's config; does nothing until a report weekday and time
    # are set.
    entry.async_on_unload(ai.async_setup_weekly_report(hass, runner))

    async def _async_shutdown() -> None:
        # Home Assistant doesn't unload entries on shutdown. Close active zones
        # in a shutdown job: those run before background tasks (the run) are
        # cancelled and before EVENT_HOMEASSISTANT_STOP, while the zones'
        # integrations are still up. Otherwise a plain switch stays on until
        # the next start.
        await runner.async_unload()

    entry.async_on_unload(hass.async_add_shutdown_job(HassJob(_async_shutdown)))

    await panel.async_register_panel(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: IrrigationConfigEntry) -> bool:
    """Unload a schedule; remove the sidebar panel with the last one."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    await entry.runtime_data.async_unload()

    # This entry still counts as loaded until unload returns.
    if not any(
        other.entry_id != entry.entry_id
        for other in hass.config_entries.async_loaded_entries(DOMAIN)
    ):
        panel.async_unregister_panel(hass)
    return True


async def _async_update_listener(
    hass: HomeAssistant, entry: IrrigationConfigEntry
) -> None:
    """Apply an options change or rename, reloading only when zones change.

    Idempotent: an options-flow rename fires this twice (title, then options).
    """
    runner = entry.runtime_data
    config = merged_config(entry)
    if set(zone_entity_ids(config)) != set(zone_entity_ids(runner.config)):
        # The per-zone number entities follow the zone set.
        hass.config_entries.async_schedule_reload(entry.entry_id)
        return
    if config != runner.config:
        await runner.async_update_config(config)

    device_registry = dr.async_get(hass)
    device = device_registry.async_get_device(identifiers={(DOMAIN, entry.entry_id)})
    if device is not None and device.name != entry.title:
        device_registry.async_update_device(device.id, name=entry.title)
    async_dispatcher_send(hass, SIGNAL_SCHEDULES_CHANGED)
