"""Domain service tests.

The v0.1 services (run_now, skip_next, stop) run against a fully set up
schedule. The v0.2 services run against fake runners on loaded entries, since
their runner methods come from the runner workstream.
"""
from __future__ import annotations

import asyncio
from collections.abc import Generator
from datetime import datetime
import sys
import types
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from zoneinfo import ZoneInfo

import pytest
import voluptuous as vol
from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.setup import async_setup_component
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    async_mock_service,
)

import custom_components.irrigation_manager as integration
from custom_components.irrigation_manager.conditions import Decision
from custom_components.irrigation_manager.const import (
    ATTR_CONFIG_ENTRY_ID,
    ATTR_DAYS,
    ATTR_ENABLED,
    ATTR_HOURS,
    ATTR_LIMIT,
    ATTR_MINUTES,
    ATTR_SKIP,
    ATTR_ZONE,
    CONF_AI_TASK_ENTITY,
    CONF_FREQUENCY,
    CONF_NAME,
    CONF_SKIP_CONDITIONS,
    CONF_START_MODE,
    CONF_START_TIME,
    CONF_WEEKDAYS,
    CONF_ZONE_ENTITY,
    CONF_ZONE_MINUTES,
    CONF_ZONE_MODE,
    CONF_ZONES,
    DOMAIN,
    HISTORY_LIMIT,
    MAX_RAIN_DELAY_HOURS,
    MAX_ZONE_MINUTES,
    SERVICE_EVALUATE,
    SERVICE_EXPLAIN_SKIPS,
    SERVICE_GENERATE_REPORT,
    SERVICE_GET_HISTORY,
    SERVICE_PAUSE_ALL,
    SERVICE_RESUME_ALL,
    SERVICE_RUN_NOW,
    SERVICE_RUN_ZONE,
    SERVICE_SET_ENABLED,
    SERVICE_SET_RAIN_DELAY,
    SERVICE_SKIP_NEXT,
    SERVICE_STOP,
    SERVICE_STOP_ALL,
)
from custom_components.irrigation_manager.services import async_setup_services

TZ = ZoneInfo("America/New_York")
ZONE_A = "valve.zone_a"
ZONE_B = "switch.zone_b"


def local(y: int, mo: int, d: int, h: int = 0, mi: int = 0) -> datetime:
    return datetime(y, mo, d, h, mi, tzinfo=TZ)


def make_config(**overrides: Any) -> dict[str, Any]:
    """Daily at 06:00, zone A 10 min then zone B 5 min."""
    config: dict[str, Any] = {
        CONF_NAME: "Front lawn",
        CONF_ZONES: [
            {CONF_ZONE_ENTITY: ZONE_A, CONF_ZONE_MINUTES: 10},
            {CONF_ZONE_ENTITY: ZONE_B, CONF_ZONE_MINUTES: 5},
        ],
        CONF_ZONE_MODE: "sequential",
        CONF_FREQUENCY: "weekdays",
        CONF_WEEKDAYS: list(range(7)),
        CONF_START_MODE: "time",
        CONF_START_TIME: "06:00:00",
        CONF_SKIP_CONDITIONS: [],
    }
    config.update(overrides)
    return config


async def settle(hass: HomeAssistant) -> None:
    """Let background run tasks and blocking service calls progress."""
    for _ in range(20):
        await hass.async_block_till_done()
        await asyncio.sleep(0)


async def setup_entry(
    hass: HomeAssistant, config: dict[str, Any] | None = None, title: str = "Front lawn"
) -> MockConfigEntry:
    entry = MockConfigEntry(domain=DOMAIN, title=title, data=config or make_config())
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await settle(hass)
    return entry


async def call(hass: HomeAssistant, service: str, **data: Any) -> None:
    await hass.services.async_call(DOMAIN, service, data, blocking=True)
    await settle(hass)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let the test hass load integrations from custom_components/."""
    return


@pytest.fixture(autouse=True)
async def setup_env(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, skip_manifest_dependencies
) -> None:
    """Monday 2026-09-14 05:00 New York, zones present."""
    await hass.config.async_set_time_zone("America/New_York")
    freezer.move_to(local(2026, 9, 14, 5, 0))
    # Set up the switch component first: when this integration's switch
    # platform loads it later, it would replace the zone service mocks.
    assert await async_setup_component(hass, "switch", {})
    hass.states.async_set(ZONE_A, "closed", {"friendly_name": "Zone A"})
    hass.states.async_set(ZONE_B, "off", {"friendly_name": "Zone B"})


@pytest.fixture(autouse=True)
def decide() -> Generator[AsyncMock]:
    mock = AsyncMock(return_value=Decision(water=True))
    with patch("custom_components.irrigation_manager.runner.async_decide", mock):
        yield mock


@pytest.fixture(autouse=True)
def shared() -> Generator[None]:
    with (
        patch(
            "custom_components.irrigation_manager.panel.async_register_panel",
            new_callable=AsyncMock,
        ),
        patch("custom_components.irrigation_manager.panel.async_unregister_panel"),
        patch("custom_components.irrigation_manager.websocket_api.async_setup"),
    ):
        yield


@pytest.fixture
def calls(hass: HomeAssistant, setup_env: None) -> dict[str, list[ServiceCall]]:
    return {
        "open": async_mock_service(hass, "valve", "open_valve"),
        "close": async_mock_service(hass, "valve", "close_valve"),
        "on": async_mock_service(hass, "switch", "turn_on"),
        "off": async_mock_service(hass, "switch", "turn_off"),
    }


async def test_run_now_uses_configured_run_times(
    hass: HomeAssistant, calls: dict[str, list[ServiceCall]]
) -> None:
    entry = await setup_entry(hass)

    await call(hass, SERVICE_RUN_NOW, **{ATTR_CONFIG_ENTRY_ID: entry.entry_id})

    runner = entry.runtime_data
    assert runner.running
    assert runner.current_zone == ZONE_A
    assert runner.current_zone_ends_at == local(2026, 9, 14, 5, 10)
    assert [c.data["entity_id"] for c in calls["open"]] == [ZONE_A]


async def test_run_now_minutes_override_every_zone(
    hass: HomeAssistant,
    freezer: FrozenDateTimeFactory,
    calls: dict[str, list[ServiceCall]],
) -> None:
    entry = await setup_entry(hass)
    runner = entry.runtime_data

    await call(hass, SERVICE_RUN_NOW, **{ATTR_CONFIG_ENTRY_ID: entry.entry_id, ATTR_MINUTES: 3})
    assert runner.current_zone_ends_at == local(2026, 9, 14, 5, 3)

    freezer.move_to(local(2026, 9, 14, 5, 3))
    async_fire_time_changed(hass)
    await settle(hass)
    assert runner.current_zone == ZONE_B
    assert runner.current_zone_ends_at == local(2026, 9, 14, 5, 6)


async def test_run_now_while_running_raises(
    hass: HomeAssistant, calls: dict[str, list[ServiceCall]]
) -> None:
    entry = await setup_entry(hass)
    await call(hass, SERVICE_RUN_NOW, **{ATTR_CONFIG_ENTRY_ID: entry.entry_id})

    with pytest.raises(HomeAssistantError) as err:
        await call(hass, SERVICE_RUN_NOW, **{ATTR_CONFIG_ENTRY_ID: entry.entry_id})
    assert err.value.translation_key == "already_running"


async def test_run_now_without_zones_raises(hass: HomeAssistant) -> None:
    entry = await setup_entry(hass, make_config(**{CONF_ZONES: []}))

    with pytest.raises(HomeAssistantError) as err:
        await call(hass, SERVICE_RUN_NOW, **{ATTR_CONFIG_ENTRY_ID: entry.entry_id})
    assert err.value.translation_key == "no_zones"
    assert not entry.runtime_data.running


async def test_run_now_minutes_out_of_range_rejected(hass: HomeAssistant) -> None:
    entry = await setup_entry(hass)

    with pytest.raises((vol.Invalid, ServiceValidationError)):
        await call(
            hass,
            SERVICE_RUN_NOW,
            **{ATTR_CONFIG_ENTRY_ID: entry.entry_id, ATTR_MINUTES: MAX_ZONE_MINUTES + 1},
        )
    assert not entry.runtime_data.running


async def test_skip_next_sets_by_default_and_clears(hass: HomeAssistant) -> None:
    entry = await setup_entry(hass)

    await call(hass, SERVICE_SKIP_NEXT, **{ATTR_CONFIG_ENTRY_ID: entry.entry_id})
    assert entry.runtime_data.skip_next is True

    await call(hass, SERVICE_SKIP_NEXT, **{ATTR_CONFIG_ENTRY_ID: entry.entry_id, ATTR_SKIP: False})
    assert entry.runtime_data.skip_next is False


async def test_stop_stops_active_run(
    hass: HomeAssistant, calls: dict[str, list[ServiceCall]]
) -> None:
    entry = await setup_entry(hass)
    await call(hass, SERVICE_RUN_NOW, **{ATTR_CONFIG_ENTRY_ID: entry.entry_id})

    await call(hass, SERVICE_STOP, **{ATTR_CONFIG_ENTRY_ID: entry.entry_id})

    assert not entry.runtime_data.running
    assert [c.data["entity_id"] for c in calls["close"]] == [ZONE_A]
    assert not calls["on"]


async def test_unknown_entry_id_raises_validation_error(hass: HomeAssistant) -> None:
    await setup_entry(hass)

    with pytest.raises(ServiceValidationError) as err:
        await call(hass, SERVICE_STOP, **{ATTR_CONFIG_ENTRY_ID: "missing"})
    assert err.value.translation_domain == DOMAIN
    assert err.value.translation_key == "entry_not_found"
    assert err.value.translation_placeholders == {"config_entry_id": "missing"}


async def test_other_integration_entry_is_not_found(hass: HomeAssistant) -> None:
    await setup_entry(hass)
    other = MockConfigEntry(domain="sun", title="Sun")
    other.add_to_hass(hass)

    with pytest.raises(ServiceValidationError) as err:
        await call(hass, SERVICE_SKIP_NEXT, **{ATTR_CONFIG_ENTRY_ID: other.entry_id})
    assert err.value.translation_key == "entry_not_found"


async def test_unloaded_entry_raises_not_loaded(hass: HomeAssistant) -> None:
    await setup_entry(hass)
    back_yard = await setup_entry(hass, make_config(**{CONF_NAME: "Back yard"}), "Back yard")
    assert await hass.config_entries.async_unload(back_yard.entry_id)
    await settle(hass)

    with pytest.raises(ServiceValidationError) as err:
        await call(hass, SERVICE_RUN_NOW, **{ATTR_CONFIG_ENTRY_ID: back_yard.entry_id})
    assert err.value.translation_key == "entry_not_loaded"
    assert err.value.translation_placeholders == {"name": "Back yard"}


# --- responses from the v0.1 services ---------------------------------------


async def call_for_response(hass: HomeAssistant, service: str, **data: Any) -> Any:
    response = await hass.services.async_call(
        DOMAIN, service, data, blocking=True, return_response=True
    )
    await settle(hass)
    return response


async def test_run_now_returns_snapshot_when_asked(
    hass: HomeAssistant, calls: dict[str, list[ServiceCall]]
) -> None:
    entry = await setup_entry(hass)

    response = await call_for_response(
        hass, SERVICE_RUN_NOW, **{ATTR_CONFIG_ENTRY_ID: entry.entry_id}
    )

    assert response["entry_id"] == entry.entry_id
    assert response["name"] == "Front lawn"
    assert response["running"] is True


async def test_skip_next_returns_snapshot_when_asked(hass: HomeAssistant) -> None:
    entry = await setup_entry(hass)

    response = await call_for_response(
        hass, SERVICE_SKIP_NEXT, **{ATTR_CONFIG_ENTRY_ID: entry.entry_id}
    )

    assert response["skip_next"] is True


async def test_stop_returns_snapshot_after_stopping(
    hass: HomeAssistant, calls: dict[str, list[ServiceCall]]
) -> None:
    entry = await setup_entry(hass)
    await call(hass, SERVICE_RUN_NOW, **{ATTR_CONFIG_ENTRY_ID: entry.entry_id})

    response = await call_for_response(
        hass, SERVICE_STOP, **{ATTR_CONFIG_ENTRY_ID: entry.entry_id}
    )

    assert response["running"] is False


# --- v0.2 services against fake runners --------------------------------------


def fake_runner(title: str = "Garden Bed", **config_overrides: Any) -> MagicMock:
    """A runner with the contract's methods, all mocked."""
    runner = MagicMock()
    runner.entry = SimpleNamespace(title=title)
    runner.config = make_config(**{CONF_NAME: title, **config_overrides})
    runner.running = False
    runner.snapshot = MagicMock(return_value={"name": title})
    for method in (
        "async_unload",
        "async_run_now",
        "async_stop_run",
        "async_set_skip_next",
        "async_set_rain_delay",
        "async_run_zone",
        "async_set_enabled",
        "async_set_paused",
    ):
        setattr(runner, method, AsyncMock())
    runner.async_evaluate = AsyncMock(return_value={"decision": {"water": True}})
    runner.history = MagicMock(return_value=[{"type": "run", "status": "idle"}])
    return runner


def add_entry(
    hass: HomeAssistant,
    runner: MagicMock,
    state: ConfigEntryState = ConfigEntryState.LOADED,
) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN, title=runner.entry.title, data=runner.config, state=state
    )
    entry.add_to_hass(hass)
    entry.runtime_data = runner
    return entry


@pytest.fixture
def services(hass: HomeAssistant) -> Generator[None]:
    async_setup_services(hass)
    yield
    # Fake entries were never set up; stop teardown from unloading their
    # platforms (the switch component raises "never loaded").
    for entry in hass.config_entries.async_entries(DOMAIN):
        if isinstance(getattr(entry, "runtime_data", None), MagicMock):
            entry.mock_state(hass, ConfigEntryState.NOT_LOADED)


async def test_setup_services_is_idempotent(hass: HomeAssistant, services: None) -> None:
    before = dict(hass.services.async_services()[DOMAIN])

    async_setup_services(hass)

    after = hass.services.async_services()[DOMAIN]
    assert after.keys() == before.keys()
    assert all(after[name] is service for name, service in before.items())


async def test_set_rain_delay_calls_runner_and_returns_snapshot(
    hass: HomeAssistant, services: None
) -> None:
    runner = fake_runner()
    entry = add_entry(hass, runner)

    response = await call_for_response(
        hass, SERVICE_SET_RAIN_DELAY, **{ATTR_CONFIG_ENTRY_ID: entry.entry_id, ATTR_HOURS: "24"}
    )

    runner.async_set_rain_delay.assert_awaited_once_with(24.0)
    assert response == {"name": "Garden Bed"}


@pytest.mark.parametrize("hours", [-1, MAX_RAIN_DELAY_HOURS + 1, "nan"])
async def test_set_rain_delay_rejects_bad_hours(
    hass: HomeAssistant, services: None, hours: Any
) -> None:
    runner = fake_runner()
    entry = add_entry(hass, runner)

    with pytest.raises((vol.Invalid, ServiceValidationError)):
        await call(hass, SERVICE_SET_RAIN_DELAY, **{ATTR_CONFIG_ENTRY_ID: entry.entry_id, ATTR_HOURS: hours})
    runner.async_set_rain_delay.assert_not_awaited()


async def test_set_rain_delay_zero_clears(hass: HomeAssistant, services: None) -> None:
    runner = fake_runner()
    entry = add_entry(hass, runner)

    await call(hass, SERVICE_SET_RAIN_DELAY, **{ATTR_CONFIG_ENTRY_ID: entry.entry_id, ATTR_HOURS: 0})

    runner.async_set_rain_delay.assert_awaited_once_with(0.0)


async def test_run_zone_defaults_to_configured_minutes(
    hass: HomeAssistant, services: None
) -> None:
    runner = fake_runner()
    entry = add_entry(hass, runner)

    await call(hass, SERVICE_RUN_ZONE, **{ATTR_CONFIG_ENTRY_ID: entry.entry_id, ATTR_ZONE: ZONE_B})

    runner.async_run_zone.assert_awaited_once_with(ZONE_B, 5)


async def test_run_zone_minutes_override(hass: HomeAssistant, services: None) -> None:
    runner = fake_runner()
    entry = add_entry(hass, runner)

    response = await call_for_response(
        hass,
        SERVICE_RUN_ZONE,
        **{ATTR_CONFIG_ENTRY_ID: entry.entry_id, ATTR_ZONE: ZONE_A, ATTR_MINUTES: 3},
    )

    runner.async_run_zone.assert_awaited_once_with(ZONE_A, 3)
    assert response == {"name": "Garden Bed"}


async def test_run_zone_rejects_zone_outside_schedule(
    hass: HomeAssistant, services: None
) -> None:
    runner = fake_runner()
    entry = add_entry(hass, runner)

    with pytest.raises(ServiceValidationError) as err:
        await call(hass, SERVICE_RUN_ZONE, **{ATTR_CONFIG_ENTRY_ID: entry.entry_id, ATTR_ZONE: "valve.other"})

    assert err.value.translation_key == "zone_not_in_schedule"
    assert err.value.translation_placeholders == {"zone": "valve.other", "name": "Garden Bed"}
    runner.async_run_zone.assert_not_awaited()


async def test_run_zone_while_running_raises(hass: HomeAssistant, services: None) -> None:
    runner = fake_runner()
    runner.running = True
    entry = add_entry(hass, runner)

    with pytest.raises(HomeAssistantError) as err:
        await call(hass, SERVICE_RUN_ZONE, **{ATTR_CONFIG_ENTRY_ID: entry.entry_id, ATTR_ZONE: ZONE_A})

    assert err.value.translation_key == "already_running"
    runner.async_run_zone.assert_not_awaited()


async def test_set_enabled(hass: HomeAssistant, services: None) -> None:
    runner = fake_runner()
    entry = add_entry(hass, runner)

    await call(hass, SERVICE_SET_ENABLED, **{ATTR_CONFIG_ENTRY_ID: entry.entry_id, ATTR_ENABLED: "off"})

    runner.async_set_enabled.assert_awaited_once_with(False)


async def test_evaluate_returns_runner_result(hass: HomeAssistant, services: None) -> None:
    runner = fake_runner()
    entry = add_entry(hass, runner)

    response = await call_for_response(hass, SERVICE_EVALUATE, **{ATTR_CONFIG_ENTRY_ID: entry.entry_id})

    assert response == {"decision": {"water": True}}
    runner.async_evaluate.assert_awaited_once_with()


async def test_evaluate_requires_response(hass: HomeAssistant, services: None) -> None:
    entry = add_entry(hass, fake_runner())

    with pytest.raises(ServiceValidationError):
        await call(hass, SERVICE_EVALUATE, **{ATTR_CONFIG_ENTRY_ID: entry.entry_id})


async def test_get_history_passes_limit(hass: HomeAssistant, services: None) -> None:
    runner = fake_runner()
    entry = add_entry(hass, runner)

    limited = await call_for_response(
        hass, SERVICE_GET_HISTORY, **{ATTR_CONFIG_ENTRY_ID: entry.entry_id, ATTR_LIMIT: 5}
    )
    everything = await call_for_response(
        hass, SERVICE_GET_HISTORY, **{ATTR_CONFIG_ENTRY_ID: entry.entry_id}
    )

    assert limited == {"history": [{"type": "run", "status": "idle"}]}
    assert everything == limited
    assert [c.args for c in runner.history.call_args_list] == [(5,), (None,)]


async def test_get_history_limit_bounded(hass: HomeAssistant, services: None) -> None:
    entry = add_entry(hass, fake_runner())

    with pytest.raises((vol.Invalid, ServiceValidationError)):
        await call_for_response(
            hass,
            SERVICE_GET_HISTORY,
            **{ATTR_CONFIG_ENTRY_ID: entry.entry_id, ATTR_LIMIT: HISTORY_LIMIT + 1},
        )


@pytest.mark.parametrize(
    ("service", "method", "args"),
    [
        (SERVICE_PAUSE_ALL, "async_set_paused", (True,)),
        (SERVICE_RESUME_ALL, "async_set_paused", (False,)),
        (SERVICE_STOP_ALL, "async_stop_run", ()),
    ],
)
async def test_all_services_act_on_every_loaded_schedule(
    hass: HomeAssistant, services: None, service: str, method: str, args: tuple
) -> None:
    garden = fake_runner("Garden Bed")
    lawn = fake_runner("Front Lawn")
    unloaded = fake_runner("Old")
    add_entry(hass, garden)
    add_entry(hass, lawn)
    add_entry(hass, unloaded, ConfigEntryState.NOT_LOADED)

    await call(hass, service)

    getattr(garden, method).assert_awaited_once_with(*args)
    getattr(lawn, method).assert_awaited_once_with(*args)
    getattr(unloaded, method).assert_not_awaited()


async def test_v02_services_validate_entry_state(hass: HomeAssistant, services: None) -> None:
    runner = fake_runner()
    entry = add_entry(hass, runner, ConfigEntryState.NOT_LOADED)

    with pytest.raises(ServiceValidationError) as err:
        await call(hass, SERVICE_SET_RAIN_DELAY, **{ATTR_CONFIG_ENTRY_ID: entry.entry_id, ATTR_HOURS: 4})

    assert err.value.translation_key == "entry_not_loaded"
    runner.async_set_rain_delay.assert_not_awaited()


@pytest.fixture
def fake_ai() -> Generator[types.ModuleType]:
    """Stand-in for ai.py, whichever of it or the real module gets imported."""
    module = types.ModuleType("custom_components.irrigation_manager.ai")
    module.async_generate_report = AsyncMock(return_value="Weekly report")
    module.async_explain_skips = AsyncMock(return_value="Skipped twice for rain")
    with (
        patch.dict(sys.modules, {"custom_components.irrigation_manager.ai": module}),
        patch.object(integration, "ai", module, create=True),
    ):
        yield module


@pytest.mark.parametrize(
    ("service", "function", "text"),
    [
        (SERVICE_GENERATE_REPORT, "async_generate_report", "Weekly report"),
        (SERVICE_EXPLAIN_SKIPS, "async_explain_skips", "Skipped twice for rain"),
    ],
)
async def test_ai_services_return_text(
    hass: HomeAssistant,
    services: None,
    fake_ai: types.ModuleType,
    service: str,
    function: str,
    text: str,
) -> None:
    runner = fake_runner(**{CONF_AI_TASK_ENTITY: "ai_task.claude_ai_task"})
    entry = add_entry(hass, runner)

    default_days = await call_for_response(hass, service, **{ATTR_CONFIG_ENTRY_ID: entry.entry_id})
    three_days = await call_for_response(
        hass, service, **{ATTR_CONFIG_ENTRY_ID: entry.entry_id, ATTR_DAYS: 3}
    )

    assert default_days == three_days == {"text": text}
    ai_function = getattr(fake_ai, function)
    assert [c.kwargs for c in ai_function.await_args_list] == [{"days": 7}, {"days": 3}]
    assert all(c.args == (hass, runner) for c in ai_function.await_args_list)


@pytest.mark.parametrize("service", [SERVICE_GENERATE_REPORT, SERVICE_EXPLAIN_SKIPS])
async def test_ai_services_require_ai_task_entity(
    hass: HomeAssistant, services: None, fake_ai: types.ModuleType, service: str
) -> None:
    entry = add_entry(hass, fake_runner())

    with pytest.raises(ServiceValidationError) as err:
        await call_for_response(hass, service, **{ATTR_CONFIG_ENTRY_ID: entry.entry_id})

    assert err.value.translation_key == "ai_not_configured"
    fake_ai.async_generate_report.assert_not_awaited()
    fake_ai.async_explain_skips.assert_not_awaited()
