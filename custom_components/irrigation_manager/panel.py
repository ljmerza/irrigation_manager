"""Sidebar panel registration.

Serves the built Lit bundle from www/ and adds one admin-only sidebar entry that
loads it as a custom element. Not an iframe: an iframe document doesn't inherit
HA's theme CSS. One panel serves every schedule entry; __init__.py registers it
when an entry loads and removes it when the last one unloads.
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from homeassistant.components import frontend, panel_custom
from homeassistant.components.http import StaticPathConfig
from homeassistant.core import HomeAssistant, callback
from homeassistant.loader import async_get_integration

from .const import (
    DOMAIN,
    PANEL_FRONTEND_PATH,
    PANEL_ICON,
    PANEL_STATIC_URL,
    PANEL_TITLE,
    PANEL_WEBCOMPONENT,
)

_LOGGER = logging.getLogger(__name__)

PANEL_FILE = Path(__file__).parent / "www" / "irrigation-manager-panel.js"

DATA_PANEL_LOCK = f"{DOMAIN}_panel_lock"
DATA_STATIC_REGISTERED = f"{DOMAIN}_panel_static_registered"


async def async_register_panel(hass: HomeAssistant) -> None:
    """Serve the panel JS and add the sidebar entry. Safe to call repeatedly."""
    # Schedule entries set up concurrently; registering the same panel twice
    # raises, so serialize.
    async with hass.data.setdefault(DATA_PANEL_LOCK, asyncio.Lock()):
        # aiohttp can't remove a route, so the bundle is served once per HA run,
        # even across unregister/register cycles from entry reloads.
        if not hass.data.get(DATA_STATIC_REGISTERED):
            await hass.http.async_register_static_paths(
                [StaticPathConfig(PANEL_STATIC_URL, str(PANEL_FILE), cache_headers=False)]
            )
            hass.data[DATA_STATIC_REGISTERED] = True

        if _panel_registered(hass):
            return

        integration = await async_get_integration(hass, DOMAIN)
        mtime = await hass.async_add_executor_job(_bundle_mtime, PANEL_FILE)
        await panel_custom.async_register_panel(
            hass,
            frontend_url_path=PANEL_FRONTEND_PATH,
            webcomponent_name=PANEL_WEBCOMPONENT,
            sidebar_title=PANEL_TITLE,
            sidebar_icon=PANEL_ICON,
            # Cache-bust on integration upgrades and on rebuilds of the bundle.
            module_url=f"{PANEL_STATIC_URL}?v={integration.version}&m={mtime}",
            require_admin=True,
            config={},
        )


@callback
def async_unregister_panel(hass: HomeAssistant) -> None:
    """Remove the sidebar entry. The static path stays registered (aiohttp can't remove it)."""
    if _panel_registered(hass):
        frontend.async_remove_panel(hass, PANEL_FRONTEND_PATH)


@callback
def _panel_registered(hass: HomeAssistant) -> bool:
    return PANEL_FRONTEND_PATH in hass.data.get(frontend.DATA_PANELS, {})


def _bundle_mtime(path: Path) -> int:
    try:
        return int(path.stat().st_mtime)
    except OSError:
        _LOGGER.warning("Irrigation Manager panel bundle is missing at %s", path)
        return 0
