"""Home Assistant test harness check: the custom integration is discoverable.

HA-level tests use pytest-homeassistant-custom-component's `hass` fixture and
import the integration as `custom_components.irrigation_manager...`. Pure tests
(no hass) import `irrigation_manager...` via the namespace in conftest.py —
don't mix the two in one test module, they are separate module objects.
"""
from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.loader import async_get_integration

from custom_components.irrigation_manager.const import DOMAIN


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let the test hass load integrations from custom_components/."""
    return


async def test_integration_manifest_loads(hass: HomeAssistant) -> None:
    integration = await async_get_integration(hass, DOMAIN)
    assert integration.domain == DOMAIN
    assert integration.config_flow
