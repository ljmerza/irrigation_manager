"""Per-zone run time numbers.

Writing a value updates the entry options through the runner, which applies it
immediately — no reload, and an active run keeps the times it started with.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.number import DOMAIN as NUMBER_DOMAIN, NumberEntity, NumberMode
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .const import (
    CONF_ZONE_ENTITY,
    CONF_ZONE_MINUTES,
    CONF_ZONES,
    MAX_ZONE_MINUTES,
    MIN_ZONE_MINUTES,
    zone_entity_ids,
)
from .entity import IrrigationEntity, zone_name
from .runner import ScheduleRunner

if TYPE_CHECKING:
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import IrrigationConfigEntry


def _unique_id(entry_id: str, zone_entity_id: str) -> str:
    return f"{entry_id}_{zone_entity_id}_minutes"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IrrigationConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runner = entry.runtime_data
    zones = zone_entity_ids(runner.config)

    # The entry reloads when its zone set changes; drop numbers for zones that
    # are no longer part of the schedule.
    wanted = {_unique_id(entry.entry_id, entity_id) for entity_id in zones}
    registry = er.async_get(hass)
    for registry_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if registry_entry.domain == NUMBER_DOMAIN and registry_entry.unique_id not in wanted:
            registry.async_remove(registry_entry.entity_id)

    async_add_entities(
        ZoneMinutesNumber(runner, entity_id, zone_name(hass, entity_id))
        for entity_id in zones
    )


class ZoneMinutesNumber(IrrigationEntity, NumberEntity):
    """Run time in minutes for one zone of the schedule."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_mode = NumberMode.BOX
    _attr_native_min_value = MIN_ZONE_MINUTES
    _attr_native_max_value = MAX_ZONE_MINUTES
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES

    def __init__(self, runner: ScheduleRunner, zone_entity_id: str, name: str) -> None:
        super().__init__(runner, "zone_minutes")
        self.zone_entity_id = zone_entity_id
        self._attr_unique_id = _unique_id(runner.entry.entry_id, zone_entity_id)
        self._attr_translation_placeholders = {"zone": name}
        self._attr_extra_state_attributes = {"zone_entity_id": zone_entity_id}

    @property
    def native_value(self) -> float | None:
        for zone in self.runner.config.get(CONF_ZONES) or []:
            if zone[CONF_ZONE_ENTITY] == self.zone_entity_id:
                return float(zone[CONF_ZONE_MINUTES])
        return None

    async def async_set_native_value(self, value: float) -> None:
        await self.runner.async_set_zone_minutes(self.zone_entity_id, value)
