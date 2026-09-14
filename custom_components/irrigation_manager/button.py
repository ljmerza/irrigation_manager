"""Schedule buttons: run now, skip next run, stop, clear rain delay."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant

from .entity import IrrigationEntity
from .runner import ScheduleRunner
from .services import async_run_now

if TYPE_CHECKING:
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import IrrigationConfigEntry


@dataclass(frozen=True, kw_only=True)
class IrrigationButtonDescription(ButtonEntityDescription):
    press_fn: Callable[[ScheduleRunner], Awaitable[None]]


BUTTONS: tuple[IrrigationButtonDescription, ...] = (
    # Ignores conditions and a pending skip, like the run_now service.
    IrrigationButtonDescription(key="run_now", press_fn=async_run_now),
    IrrigationButtonDescription(
        key="skip_next", press_fn=lambda runner: runner.async_set_skip_next(True)
    ),
    IrrigationButtonDescription(key="stop", press_fn=lambda runner: runner.async_stop_run()),
    IrrigationButtonDescription(
        key="clear_rain_delay", press_fn=lambda runner: runner.async_set_rain_delay(0)
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IrrigationConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runner = entry.runtime_data
    async_add_entities(IrrigationButton(runner, description) for description in BUTTONS)


class IrrigationButton(IrrigationEntity, ButtonEntity):
    entity_description: IrrigationButtonDescription

    def __init__(
        self, runner: ScheduleRunner, description: IrrigationButtonDescription
    ) -> None:
        super().__init__(runner, description.key)
        self.entity_description = description

    async def async_press(self) -> None:
        await self.entity_description.press_fn(self.runner)
