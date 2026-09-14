"""Problem binary sensor: a zone couldn't be closed, or the last run errored."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant

from .const import Status
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
    async_add_entities([IrrigationProblemBinarySensor(entry.runtime_data)])


class IrrigationProblemBinarySensor(IrrigationEntity, BinarySensorEntity):
    """On while a zone is still open after a failed close, or the status is error."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, runner: ScheduleRunner) -> None:
        super().__init__(runner, "problem")

    @property
    def is_on(self) -> bool:
        return bool(self.runner.unclosed_zones) or self.runner.status is Status.ERROR

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "unclosed_zones": self.runner.unclosed_zones,
            "zone_errors": [
                {"entity_id": result["entity_id"], "error": result["error"]}
                for result in self.runner.zone_results
                if result.get("error")
            ],
        }
