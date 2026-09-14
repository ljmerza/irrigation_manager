"""Test bootstrap.

The integration's package __init__ pulls in Home Assistant, which we don't want
to require just to exercise pure scheduling logic. Register a lightweight
`irrigation_manager` namespace package whose __path__ points at the real source
dir, so submodules import without executing the HA-heavy __init__.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

_CC = Path(__file__).resolve().parent.parent / "custom_components"

if "irrigation_manager" not in sys.modules:
    pkg = types.ModuleType("irrigation_manager")
    pkg.__path__ = [str(_CC / "irrigation_manager")]
    sys.modules["irrigation_manager"] = pkg


@pytest.fixture
def skip_manifest_dependencies(hass):
    """Mark the manifest's dependencies as loaded without setting them up.

    frontend needs the hass_frontend package, which isn't installed in the test
    environment. Request this in HA tests that set up the integration; tests of
    the panel itself should mock hass.http / panel_custom instead.
    """
    for component in ("http", "frontend", "panel_custom", "websocket_api"):
        hass.config.components.add(component)
