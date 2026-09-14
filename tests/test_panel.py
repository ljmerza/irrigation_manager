"""Sidebar panel registration tests.

hass.http is mocked (the http component isn't set up); panel_custom and the
frontend panel registry run for real — they only touch hass.data.
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.components import frontend
from homeassistant.core import HomeAssistant

from custom_components.irrigation_manager import panel
from custom_components.irrigation_manager.const import (
    PANEL_FRONTEND_PATH,
    PANEL_ICON,
    PANEL_STATIC_URL,
    PANEL_TITLE,
    PANEL_WEBCOMPONENT,
)


VERSION = json.loads(Path(panel.__file__).with_name("manifest.json").read_text())["version"]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let the test hass load integrations from custom_components/."""
    return


@pytest.fixture
def mock_http(hass: HomeAssistant) -> MagicMock:
    http = MagicMock()
    http.async_register_static_paths = AsyncMock()
    hass.http = http
    return http


def registered_panel(hass: HomeAssistant):
    return hass.data.get(frontend.DATA_PANELS, {}).get(PANEL_FRONTEND_PATH)


async def test_register_serves_bundle_and_adds_admin_panel(
    hass: HomeAssistant, mock_http: MagicMock
) -> None:
    await panel.async_register_panel(hass)

    mock_http.async_register_static_paths.assert_awaited_once()
    (configs,) = mock_http.async_register_static_paths.await_args.args
    assert len(configs) == 1
    assert configs[0].url_path == PANEL_STATIC_URL
    assert Path(configs[0].path) == panel.PANEL_FILE
    assert configs[0].cache_headers is False

    registered = registered_panel(hass)
    assert registered is not None
    assert registered.sidebar_title == PANEL_TITLE
    assert registered.sidebar_icon == PANEL_ICON
    assert registered.require_admin is True
    custom = registered.config["_panel_custom"]
    assert custom["name"] == PANEL_WEBCOMPONENT
    assert custom["embed_iframe"] is False
    assert custom["module_url"].startswith(f"{PANEL_STATIC_URL}?v={VERSION}&m=")


async def test_module_url_busts_cache_on_bundle_mtime(
    hass: HomeAssistant, mock_http: MagicMock, tmp_path: Path
) -> None:
    bundle = tmp_path / "irrigation-manager-panel.js"
    bundle.write_text("export {};")
    os.utime(bundle, (1_700_000_000, 1_700_000_000))

    with patch.object(panel, "PANEL_FILE", bundle):
        await panel.async_register_panel(hass)

    custom = registered_panel(hass).config["_panel_custom"]
    assert custom["module_url"] == f"{PANEL_STATIC_URL}?v={VERSION}&m=1700000000"


async def test_missing_bundle_still_registers(
    hass: HomeAssistant, mock_http: MagicMock, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with patch.object(panel, "PANEL_FILE", tmp_path / "missing.js"):
        await panel.async_register_panel(hass)

    assert registered_panel(hass).config["_panel_custom"]["module_url"].endswith("&m=0")
    assert "bundle is missing" in caplog.text


async def test_register_is_idempotent(hass: HomeAssistant, mock_http: MagicMock) -> None:
    await panel.async_register_panel(hass)
    await panel.async_register_panel(hass)

    assert mock_http.async_register_static_paths.await_count == 1
    assert registered_panel(hass) is not None


async def test_concurrent_registration_registers_once(
    hass: HomeAssistant, mock_http: MagicMock
) -> None:
    await asyncio.gather(*(panel.async_register_panel(hass) for _ in range(3)))

    assert mock_http.async_register_static_paths.await_count == 1
    assert registered_panel(hass) is not None


async def test_unregister_keeps_static_path(hass: HomeAssistant, mock_http: MagicMock) -> None:
    await panel.async_register_panel(hass)
    panel.async_unregister_panel(hass)
    assert registered_panel(hass) is None

    await panel.async_register_panel(hass)
    assert registered_panel(hass) is not None
    assert mock_http.async_register_static_paths.await_count == 1


async def test_failed_static_registration_is_retried(
    hass: HomeAssistant, mock_http: MagicMock
) -> None:
    mock_http.async_register_static_paths.side_effect = [RuntimeError("boom"), None]

    with pytest.raises(RuntimeError):
        await panel.async_register_panel(hass)
    assert registered_panel(hass) is None

    await panel.async_register_panel(hass)
    assert mock_http.async_register_static_paths.await_count == 2
    assert registered_panel(hass) is not None


def test_built_bundle_defines_panel_element() -> None:
    # Guards against serving a missing or stale build: rebuild with
    # `npm run build` in frontend/.
    assert panel.PANEL_FILE.is_file()
    assert f'"{PANEL_WEBCOMPONENT}"' in panel.PANEL_FILE.read_text(encoding="utf-8")


async def test_unregister_without_panel_is_quiet(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture
) -> None:
    panel.async_unregister_panel(hass)
    assert "Removing unknown panel" not in caplog.text
