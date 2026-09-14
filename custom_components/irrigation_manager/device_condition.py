"""Device conditions for a schedule's device: running, enabled, paused, rain delay."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.const import CONF_CONDITION, CONF_DEVICE_ID, CONF_DOMAIN, CONF_TYPE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import condition
from homeassistant.helpers.config_validation import DEVICE_CONDITION_BASE_SCHEMA
from homeassistant.helpers.typing import ConfigType, TemplateVarsType
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .services import async_is_schedule_device, async_runner_for_device

CONDITION_IS_RUNNING = "is_running"
CONDITION_IS_ENABLED = "is_enabled"
CONDITION_IS_PAUSED = "is_paused"
CONDITION_RAIN_DELAY_ACTIVE = "rain_delay_active"

CONDITION_TYPES = (
    CONDITION_IS_RUNNING,
    CONDITION_IS_ENABLED,
    CONDITION_IS_PAUSED,
    CONDITION_RAIN_DELAY_ACTIVE,
)

CONDITION_SCHEMA = DEVICE_CONDITION_BASE_SCHEMA.extend(
    {vol.Required(CONF_TYPE): vol.In(CONDITION_TYPES)}
)


async def async_get_conditions(
    hass: HomeAssistant, device_id: str
) -> list[dict[str, Any]]:
    """List the conditions for a schedule's device."""
    if not async_is_schedule_device(hass, device_id):
        return []
    return [
        {
            CONF_CONDITION: "device",
            CONF_DEVICE_ID: device_id,
            CONF_DOMAIN: DOMAIN,
            CONF_TYPE: condition_type,
        }
        for condition_type in CONDITION_TYPES
    ]


@callback
def async_condition_from_config(
    hass: HomeAssistant, config: ConfigType
) -> condition.ConditionCheckerType:
    """Checker for one condition. A schedule that isn't loaded tests False."""
    device_id = config[CONF_DEVICE_ID]
    condition_type = config[CONF_TYPE]

    def test(hass: HomeAssistant, variables: TemplateVarsType = None) -> bool:
        runner = async_runner_for_device(hass, device_id)
        if runner is None:
            return False
        if condition_type == CONDITION_IS_RUNNING:
            return bool(runner.running)
        if condition_type == CONDITION_IS_ENABLED:
            return bool(runner.enabled)
        if condition_type == CONDITION_IS_PAUSED:
            return bool(runner.paused)
        until = runner.rain_delay_until
        return until is not None and until > dt_util.utcnow()

    return test
