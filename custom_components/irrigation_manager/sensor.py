"""Schedule sensors: status, next run, rain delay, last run, last run total, current zone."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import StateType

from .const import Status
from .entity import IrrigationEntity, zone_name
from .runner import ScheduleRunner

if TYPE_CHECKING:
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

    from . import IrrigationConfigEntry


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


@dataclass(frozen=True, kw_only=True)
class IrrigationSensorDescription(SensorEntityDescription):
    value_fn: Callable[[ScheduleRunner], StateType | datetime]
    attrs_fn: Callable[[ScheduleRunner], dict[str, Any]] = lambda _runner: {}


def _next_run(runner: ScheduleRunner) -> datetime | None:
    occurrence = runner.next_occurrence
    return occurrence.start if occurrence is not None else None


def _next_run_attrs(runner: ScheduleRunner) -> dict[str, Any]:
    occurrence = runner.next_occurrence
    # False: a moisture check day, which only waters when the soil is dry.
    return {"scheduled": occurrence.scheduled if occurrence is not None else None}


def _current_zone(runner: ScheduleRunner) -> str | None:
    entity_id = runner.current_zone
    return zone_name(runner.hass, entity_id) if entity_id is not None else None


def _current_zone_attrs(runner: ScheduleRunner) -> dict[str, Any]:
    return {
        "entity_id": runner.current_zone,
        "ends_at": _iso(runner.current_zone_ends_at),
        "active_zones": runner.snapshot()["active_zones"],
    }


SENSORS: tuple[IrrigationSensorDescription, ...] = (
    IrrigationSensorDescription(
        key="status",
        device_class=SensorDeviceClass.ENUM,
        options=[status.value for status in Status],
        value_fn=lambda runner: runner.status.value,
        attrs_fn=lambda runner: {
            "last_status_at": _iso(runner.last_status_at),
            "skip_next": runner.skip_next,
            "paused": runner.paused,
            "rain_delay_until": _iso(runner.rain_delay_until),
            "unclosed_zones": runner.unclosed_zones,
            "details": runner.last_details,
        },
    ),
    IrrigationSensorDescription(
        key="next_run",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=_next_run,
        attrs_fn=_next_run_attrs,
    ),
    IrrigationSensorDescription(
        key="rain_delay",
        device_class=SensorDeviceClass.TIMESTAMP,
        # None (unknown) when no rain delay is active.
        value_fn=lambda runner: runner.rain_delay_until,
    ),
    IrrigationSensorDescription(
        key="last_run",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda runner: runner.last_run_start,
        attrs_fn=lambda runner: {
            "last_run_end": _iso(runner.last_run_end),
            "zone_results": runner.zone_results,
        },
    ),
    IrrigationSensorDescription(
        key="last_run_total",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        suggested_display_precision=1,
        value_fn=lambda runner: runner.last_run_total_minutes,
    ),
    IrrigationSensorDescription(
        key="current_zone",
        value_fn=_current_zone,
        attrs_fn=_current_zone_attrs,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: IrrigationConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    runner = entry.runtime_data
    async_add_entities(IrrigationSensor(runner, description) for description in SENSORS)


class IrrigationSensor(IrrigationEntity, SensorEntity):
    """A sensor whose value and attributes are read from the runner."""

    entity_description: IrrigationSensorDescription
    # Large and frequently changing; keep them out of the recorder.
    _unrecorded_attributes = frozenset({"details", "zone_results", "active_zones"})

    def __init__(
        self, runner: ScheduleRunner, description: IrrigationSensorDescription
    ) -> None:
        super().__init__(runner, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> StateType | datetime:
        return self.entity_description.value_fn(self.runner)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return self.entity_description.attrs_fn(self.runner)
