"""Enabled switch: turns a schedule's automatic runs on or off."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant

from .entity import IrrigationEntity
from .runner import ScheduleRunner

if TYPE_CHECKING:
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import IrrigationConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IrrigationConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([IrrigationEnabledSwitch(entry.runtime_data)])


class IrrigationEnabledSwitch(IrrigationEntity, SwitchEntity):
    """Off stops automatic runs; manual runs still work. Doesn't stop an active run."""

    def __init__(self, runner: ScheduleRunner) -> None:
        super().__init__(runner, "enabled")

    @property
    def is_on(self) -> bool:
        return self.runner.enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self.runner.async_set_enabled(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self.runner.async_set_enabled(False)
