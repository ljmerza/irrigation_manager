"""Base entity for a schedule's device."""
from __future__ import annotations

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .runner import ScheduleRunner


class IrrigationEntity(Entity):
    """Entity on a schedule's device, written whenever the runner's state changes."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, runner: ScheduleRunner, key: str) -> None:
        self.runner = runner
        entry = runner.entry
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.title,
            entry_type=DeviceEntryType.SERVICE,
            manufacturer="Irrigation Manager",
            model="Schedule",
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self.runner.async_add_listener(self._handle_runner_update))

    @callback
    def _handle_runner_update(self) -> None:
        self.async_write_ha_state()


@callback
def zone_name(hass: HomeAssistant, entity_id: str) -> str:
    """Friendly name of a zone entity, falling back to its entity_id."""
    if (state := hass.states.get(entity_id)) is not None:
        return state.name
    if (registry_entry := er.async_get(hass).async_get(entity_id)) is not None:
        return registry_entry.name or registry_entry.original_name or entity_id
    return entity_id
