"""Zone drivers: start a valve or switch for a duration, and stop it.

Core `valve.open_valve` and `switch.turn_on` take no duration, so integrations
that support one expose their own service. A driver is picked per entity from
its entity registry platform. Native-duration devices shut off on their own at
the end of the duration; the runner waits for that before sending a stop of
its own, and reads the entity state (is_on) to verify every stop.

Drivers can also copy a schedule's rain delay to devices that have one.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from homeassistant.const import ATTR_ENTITY_ID, STATE_OFF, STATE_ON, STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

_LOGGER = logging.getLogger(__name__)

# orbit_bhyve.start_watering accepts 1..65535 seconds.
ORBIT_BHYVE_MAX_SECONDS = 65535
# orbit_bhyve's rain delay number (hours, 0 clears) has unique_id "<device>_rain_delay".
ORBIT_BHYVE_RAIN_DELAY_SUFFIX = "_rain_delay"

# Valve states (homeassistant.components.valve.ValveState) as plain strings so
# the driver doesn't import the valve component.
_VALVE_ON_STATES = ("open", "opening")
_VALVE_OFF_STATES = ("closed", "closing")


class ZoneDriver:
    """Plain on/off control; the runner times the zone."""

    native_duration = False

    def __init__(self, hass: HomeAssistant, entity_id: str) -> None:
        self.hass = hass
        self.entity_id = entity_id
        self.domain = entity_id.partition(".")[0]

    async def async_start(self, duration: timedelta) -> None:
        """Turn the zone on. Plain drivers ignore `duration`."""
        service = "open_valve" if self.domain == "valve" else "turn_on"
        await self._async_call(self.domain, service)

    async def async_stop(self) -> None:
        """Turn the zone off."""
        service = "close_valve" if self.domain == "valve" else "turn_off"
        await self._async_call(self.domain, service)

    @property
    def can_refresh(self) -> bool:
        """Whether homeassistant.update_entity is available for a fresh device read."""
        return self.hass.services.has_service("homeassistant", "update_entity")

    async def async_refresh(self) -> None:
        """Ask the entity's integration for a fresh device read, when HA offers it.

        Native-duration devices are polled slowly, so the cached state can lag
        the device by a minute; a read makes is_on() reflect the device now.
        Failures are logged and ignored — the cached state is used instead.
        """
        if not self.can_refresh:
            return
        try:
            await self.hass.services.async_call(
                "homeassistant",
                "update_entity",
                {ATTR_ENTITY_ID: [self.entity_id]},
                blocking=True,
            )
        except Exception as err:  # noqa: BLE001 — best effort
            _LOGGER.debug("%s: update_entity failed: %s", self.entity_id, err)

    @callback
    def is_on(self) -> bool | None:
        """Whether the entity currently reads on/open; None when it can't be read."""
        state = self.hass.states.get(self.entity_id)
        if state is None:
            return None
        if self.domain == "valve":
            if state.state in _VALVE_ON_STATES:
                return True
            if state.state in _VALVE_OFF_STATES:
                return False
            return None
        if state.state == STATE_ON:
            return True
        if state.state == STATE_OFF:
            return False
        return None

    async def async_set_rain_delay(self, hours: float) -> None:
        """Copy a schedule rain delay to the device; 0 clears it.

        Plain valves and switches have no rain delay, so this does nothing.
        """

    async def _async_call(
        self,
        domain: str,
        service: str,
        data: dict[str, Any] | None = None,
        *,
        target_entity: bool = True,
        entity_id: str | None = None,
    ) -> None:
        entity_id = entity_id or self.entity_id
        state = self.hass.states.get(entity_id)
        if state is None or state.state == STATE_UNAVAILABLE:
            # Entity services silently skip unavailable entities; fail loudly.
            raise HomeAssistantError(f"{entity_id} is not available")
        if not self.hass.services.has_service(domain, service):
            raise HomeAssistantError(f"Service {domain}.{service} is not available")

        payload = dict(data or {})
        if target_entity:
            payload[ATTR_ENTITY_ID] = entity_id
        try:
            await self.hass.services.async_call(domain, service, payload, blocking=True)
        except Exception as err:  # noqa: BLE001 — handlers raise anything
            raise HomeAssistantError(
                f"{domain}.{service} failed for {entity_id}: {err}"
            ) from err

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.entity_id})"


class OrbitBhyveDriver(ZoneDriver):
    """orbit_bhyve valves: the device closes itself after the duration."""

    native_duration = True

    async def async_start(self, duration: timedelta) -> None:
        seconds = min(ORBIT_BHYVE_MAX_SECONDS, max(1, round(duration.total_seconds())))
        # A domain service that takes entity ids in its data, not a target.
        await self._async_call(
            "orbit_bhyve",
            "start_watering",
            {ATTR_ENTITY_ID: [self.entity_id], "duration": seconds},
            target_entity=False,
        )

    async def async_set_rain_delay(self, hours: float) -> None:
        """Set the device's rain delay number (whole hours, clamped to its max)."""
        number_id = device_entity(
            self.hass, self.entity_id, "number", "orbit_bhyve", ORBIT_BHYVE_RAIN_DELAY_SUFFIX
        )
        if number_id is None:
            # HT25 hose timers have no rain delay entity.
            _LOGGER.debug("%s: device has no rain delay entity", self.entity_id)
            return
        value = max(0.0, hours)
        state = self.hass.states.get(number_id)
        maximum = _as_float(state.attributes.get("max")) if state is not None else None
        if maximum is not None:
            value = min(value, maximum)
        await self._async_call(
            "number", "set_value", {"value": int(round(value))}, entity_id=number_id
        )


class RachioDriver(ZoneDriver):
    """Core rachio zones and hose timers: duration in whole minutes.

    No rain delay copy: core rachio registers pause_watering only for
    non-Gen-1 controllers (not hose timers), addressed by controller name, with
    a 60-minute UI limit, so it can't express a multi-hour schedule delay.
    """

    native_duration = True

    async def async_start(self, duration: timedelta) -> None:
        minutes = max(1, math.ceil(duration.total_seconds() / 60))
        await self._async_call("rachio", "start_watering", {"duration": minutes})


class RachioLocalDriver(ZoneDriver):
    """rachio_local custom integration: turn_on with a duration in seconds."""

    native_duration = True

    async def async_start(self, duration: timedelta) -> None:
        seconds = max(1, round(duration.total_seconds()))
        await self._async_call("rachio_local", "turn_on", {"duration": seconds})


@dataclass(frozen=True, slots=True)
class _NativeDriver:
    cls: type[ZoneDriver]
    entity_domain: str
    service_domain: str
    service: str


NATIVE_DRIVERS: dict[str, _NativeDriver] = {
    "orbit_bhyve": _NativeDriver(OrbitBhyveDriver, "valve", "orbit_bhyve", "start_watering"),
    "rachio": _NativeDriver(RachioDriver, "switch", "rachio", "start_watering"),
    "rachio_local": _NativeDriver(RachioLocalDriver, "switch", "rachio_local", "turn_on"),
}


@callback
def async_get_driver(hass: HomeAssistant, entity_id: str) -> ZoneDriver:
    """Driver for `entity_id`: native when its platform's service exists."""
    entry = er.async_get(hass).async_get(entity_id)
    native = NATIVE_DRIVERS.get(entry.platform) if entry is not None else None
    if (
        native is not None
        and entity_id.startswith(f"{native.entity_domain}.")
        and hass.services.has_service(native.service_domain, native.service)
    ):
        return native.cls(hass, entity_id)
    if native is not None:
        _LOGGER.debug(
            "%s: %s.%s unavailable, using plain on/off",
            entity_id,
            native.service_domain,
            native.service,
        )
    return ZoneDriver(hass, entity_id)


@callback
def device_entity(
    hass: HomeAssistant,
    entity_id: str,
    domain: str,
    platform: str,
    unique_id_suffix: str,
) -> str | None:
    """Enabled entity on `entity_id`'s device matching domain, platform and unique_id suffix."""
    registry = er.async_get(hass)
    entry = registry.async_get(entity_id)
    if entry is None or entry.device_id is None:
        return None
    for candidate in er.async_entries_for_device(registry, entry.device_id):
        if (
            candidate.domain == domain
            and candidate.platform == platform
            and candidate.unique_id.endswith(unique_id_suffix)
        ):
            return candidate.entity_id
    return None


def _as_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None
