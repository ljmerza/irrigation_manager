"""Websocket API tests for the sidebar panel.

Runners are real ScheduleRunners on MockConfigEntry entries marked LOADED; they
aren't set up (no timers), which snapshot() and the actions don't need.
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_send
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.irrigation_manager import websocket_api as im_websocket
from custom_components.irrigation_manager.const import DOMAIN, SIGNAL_SCHEDULES_CHANGED
from custom_components.irrigation_manager.runner import ScheduleRunner

CONFIG: dict[str, Any] = {
    "name": "Front lawn",
    "zones": [{"entity_id": "valve.deck_zone", "minutes": 10}],
    "zone_mode": "sequential",
    "frequency": "weekdays",
    "weekdays": [0, 2, 4],
    "start_mode": "time",
    "start_time": "06:00:00",
    "skip_conditions": [],
}


@pytest.fixture(autouse=True, scope="module")
def start_pycares_shutdown_thread() -> None:
    """Start pycares' channel-shutdown thread before any test's thread snapshot.

    The websocket test client closes an aiohttp session with the aiodns
    resolver; pycares starts a process-wide daemon thread the first time that
    happens, and phacc's cleanup check fails whichever test starts it.
    """
    try:
        import pycares  # noqa: PLC0415
    except ImportError:
        return
    manager = getattr(pycares, "_shutdown_manager", None)
    if manager is not None and hasattr(manager, "start"):
        manager.start()


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let the test hass load integrations from custom_components/."""
    return


@pytest.fixture(autouse=True)
def register_commands(hass: HomeAssistant) -> None:
    im_websocket.async_setup(hass)


def add_schedule(
    hass: HomeAssistant,
    title: str,
    *,
    state: ConfigEntryState = ConfigEntryState.LOADED,
    domain: str = DOMAIN,
    **config: Any,
) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=domain, title=title, data={**CONFIG, "name": title, **config}, state=state
    )
    entry.add_to_hass(hass)
    entry.runtime_data = ScheduleRunner(hass, entry)
    return entry


async def test_schedules_lists_loaded_snapshots_sorted(hass: HomeAssistant, hass_ws_client) -> None:
    add_schedule(hass, "backyard")
    first = add_schedule(hass, "Aloe beds")
    add_schedule(hass, "Not loaded", state=ConfigEntryState.NOT_LOADED)

    client = await hass_ws_client(hass)
    await client.send_json_auto_id({"type": f"{DOMAIN}/schedules"})
    msg = await client.receive_json()

    assert msg["success"], msg
    schedules = msg["result"]["schedules"]
    assert [schedule["name"] for schedule in schedules] == ["Aloe beds", "backyard"]
    assert schedules[0] == first.runtime_data.snapshot()


async def test_subscribe_sends_list_then_updates(hass: HomeAssistant, hass_ws_client) -> None:
    entry = add_schedule(hass, "Front lawn")
    client = await hass_ws_client(hass)

    await client.send_json_auto_id({"type": f"{DOMAIN}/subscribe"})
    result = await client.receive_json()
    assert result["success"], result
    subscription = result["id"]

    initial = await client.receive_json()
    assert initial["type"] == "event"
    assert initial["id"] == subscription
    assert initial["event"]["schedules"][0]["skip_next"] is False

    await entry.runtime_data.async_set_skip_next(True)
    update = await client.receive_json()
    assert update["event"]["schedules"][0]["skip_next"] is True

    await client.send_json_auto_id({"type": "unsubscribe_events", "subscription": subscription})
    assert (await client.receive_json())["success"]

    async_dispatcher_send(hass, SIGNAL_SCHEDULES_CHANGED)
    with pytest.raises(TimeoutError):
        await asyncio.wait_for(client.receive_json(), 0.1)


@pytest.mark.parametrize(
    ("command", "extra", "method", "args"),
    [
        ("run_now", {}, "async_run_now", (None,)),
        ("run_now", {"minutes": 5}, "async_run_now", (5,)),
        ("stop", {}, "async_stop_run", ()),
        ("skip_next", {}, "async_set_skip_next", (True,)),
        ("skip_next", {"skip": False}, "async_set_skip_next", (False,)),
        ("set_enabled", {"enabled": False}, "async_set_enabled", (False,)),
        ("set_rain_delay", {"hours": 24}, "async_set_rain_delay", (24.0,)),
        ("set_rain_delay", {"hours": 0}, "async_set_rain_delay", (0.0,)),
        ("run_zone", {"zone": "valve.deck_zone"}, "async_run_zone", ("valve.deck_zone", 10)),
        (
            "run_zone",
            {"zone": "valve.deck_zone", "minutes": 3},
            "async_run_zone",
            ("valve.deck_zone", 3),
        ),
    ],
)
async def test_actions_call_runner(
    hass: HomeAssistant,
    hass_ws_client,
    command: str,
    extra: dict[str, Any],
    method: str,
    args: tuple[Any, ...],
) -> None:
    entry = add_schedule(hass, "Front lawn")
    client = await hass_ws_client(hass)

    with patch.object(ScheduleRunner, method, autospec=True) as mocked:
        await client.send_json_auto_id(
            {"type": f"{DOMAIN}/{command}", "entry_id": entry.entry_id, **extra}
        )
        msg = await client.receive_json()

    assert msg["success"], msg
    mocked.assert_awaited_once_with(entry.runtime_data, *args)
    assert msg["result"]["entry_id"] == entry.entry_id


async def test_set_enabled_returns_updated_snapshot(hass: HomeAssistant, hass_ws_client) -> None:
    entry = add_schedule(hass, "Front lawn")
    client = await hass_ws_client(hass)

    await client.send_json_auto_id(
        {"type": f"{DOMAIN}/set_enabled", "entry_id": entry.entry_id, "enabled": False}
    )
    msg = await client.receive_json()

    assert msg["success"], msg
    assert msg["result"]["enabled"] is False
    assert msg["result"]["status"] == "disabled"


async def test_runner_error_is_reported(hass: HomeAssistant, hass_ws_client) -> None:
    entry = add_schedule(hass, "Empty", zones=[])
    client = await hass_ws_client(hass)

    await client.send_json_auto_id({"type": f"{DOMAIN}/run_now", "entry_id": entry.entry_id})
    msg = await client.receive_json()

    assert not msg["success"]
    assert msg["error"]["code"] == "home_assistant_error"
    assert "has no zones" in msg["error"]["message"]


async def test_run_now_minutes_validated(hass: HomeAssistant, hass_ws_client) -> None:
    entry = add_schedule(hass, "Front lawn")
    client = await hass_ws_client(hass)

    await client.send_json_auto_id(
        {"type": f"{DOMAIN}/run_now", "entry_id": entry.entry_id, "minutes": 0}
    )
    msg = await client.receive_json()

    assert not msg["success"]
    assert msg["error"]["code"] == "invalid_format"


@pytest.mark.parametrize("case", ["unknown", "not_loaded", "other_domain"])
async def test_action_on_missing_schedule_is_not_found(
    hass: HomeAssistant, hass_ws_client, case: str
) -> None:
    if case == "unknown":
        entry_id = "does-not-exist"
    elif case == "not_loaded":
        entry_id = add_schedule(hass, "Idle", state=ConfigEntryState.NOT_LOADED).entry_id
    else:
        entry_id = add_schedule(hass, "Other", domain="other_domain").entry_id
    client = await hass_ws_client(hass)

    await client.send_json_auto_id({"type": f"{DOMAIN}/stop", "entry_id": entry_id})
    msg = await client.receive_json()

    assert not msg["success"]
    assert msg["error"]["code"] == "not_found"


async def test_commands_require_admin(
    hass: HomeAssistant, hass_ws_client, hass_read_only_access_token: str
) -> None:
    entry = add_schedule(hass, "Front lawn")
    client = await hass_ws_client(hass, hass_read_only_access_token)

    payloads = [
        {"type": f"{DOMAIN}/schedules"},
        {"type": f"{DOMAIN}/subscribe"},
        {"type": f"{DOMAIN}/run_now", "entry_id": entry.entry_id},
        {"type": f"{DOMAIN}/stop", "entry_id": entry.entry_id},
        {"type": f"{DOMAIN}/skip_next", "entry_id": entry.entry_id},
        {"type": f"{DOMAIN}/set_enabled", "entry_id": entry.entry_id, "enabled": False},
        {"type": f"{DOMAIN}/set_rain_delay", "entry_id": entry.entry_id, "hours": 24},
        {"type": f"{DOMAIN}/run_zone", "entry_id": entry.entry_id, "zone": "valve.deck_zone"},
        {"type": f"{DOMAIN}/evaluate", "entry_id": entry.entry_id},
        {"type": f"{DOMAIN}/history", "entry_id": entry.entry_id},
        {"type": f"{DOMAIN}/pause_all"},
        {"type": f"{DOMAIN}/resume_all"},
        {"type": f"{DOMAIN}/stop_all"},
        {"type": f"{DOMAIN}/generate_report", "entry_id": entry.entry_id},
        {"type": f"{DOMAIN}/explain_skips", "entry_id": entry.entry_id},
    ]
    for payload in payloads:
        await client.send_json_auto_id(payload)
        msg = await client.receive_json()
        assert not msg["success"], payload
        assert msg["error"]["code"] == "unauthorized", payload

    assert entry.runtime_data.enabled is True
    assert entry.runtime_data.paused is False
    assert entry.runtime_data.rain_delay_until is None


async def test_async_setup_registers_commands_once(hass: HomeAssistant) -> None:
    hass.data.pop(im_websocket.DATA_WEBSOCKET_REGISTERED, None)
    with patch.object(im_websocket.websocket_api, "async_register_command") as register:
        im_websocket.async_setup(hass)
        im_websocket.async_setup(hass)

    assert register.call_count == 15


# --- v0.2 commands ----------------------------------------------------------------


async def send(client, payload: dict[str, Any]) -> dict[str, Any]:
    await client.send_json_auto_id(payload)
    return await client.receive_json()


async def test_set_rain_delay_returns_snapshot_with_delay(
    hass: HomeAssistant, hass_ws_client
) -> None:
    entry = add_schedule(hass, "Front lawn")
    client = await hass_ws_client(hass)

    msg = await send(
        client, {"type": f"{DOMAIN}/set_rain_delay", "entry_id": entry.entry_id, "hours": 24}
    )
    assert msg["success"], msg
    assert msg["result"]["rain_delay_until"] is not None

    msg = await send(
        client, {"type": f"{DOMAIN}/set_rain_delay", "entry_id": entry.entry_id, "hours": 0}
    )
    assert msg["success"], msg
    assert msg["result"]["rain_delay_until"] is None


# "nan" as a string: a bare NaN isn't valid JSON and the websocket closes on it.
@pytest.mark.parametrize("hours", ["nan", -1, 400])
async def test_set_rain_delay_hours_validated(
    hass: HomeAssistant, hass_ws_client, hours: Any
) -> None:
    entry = add_schedule(hass, "Front lawn")
    client = await hass_ws_client(hass)

    with patch.object(ScheduleRunner, "async_set_rain_delay", autospec=True) as mocked:
        msg = await send(
            client,
            {"type": f"{DOMAIN}/set_rain_delay", "entry_id": entry.entry_id, "hours": hours},
        )

    assert not msg["success"]
    assert msg["error"]["code"] == "invalid_format"
    mocked.assert_not_called()


async def test_run_zone_rejects_zone_outside_schedule(
    hass: HomeAssistant, hass_ws_client
) -> None:
    entry = add_schedule(hass, "Front lawn")
    client = await hass_ws_client(hass)

    with patch.object(ScheduleRunner, "async_run_zone", autospec=True) as mocked:
        msg = await send(
            client,
            {"type": f"{DOMAIN}/run_zone", "entry_id": entry.entry_id, "zone": "valve.other"},
        )

    assert not msg["success"]
    assert msg["error"]["code"] == "zone_not_in_schedule"
    assert "valve.other" in msg["error"]["message"]
    mocked.assert_not_called()


async def test_run_zone_runner_error_is_reported(hass: HomeAssistant, hass_ws_client) -> None:
    entry = add_schedule(hass, "Front lawn")
    client = await hass_ws_client(hass)

    with patch.object(
        ScheduleRunner,
        "async_run_zone",
        autospec=True,
        side_effect=HomeAssistantError("Front lawn is already running"),
    ):
        msg = await send(
            client,
            {"type": f"{DOMAIN}/run_zone", "entry_id": entry.entry_id, "zone": "valve.deck_zone"},
        )

    assert not msg["success"]
    assert msg["error"]["code"] == "home_assistant_error"
    assert "already running" in msg["error"]["message"]


async def test_evaluate_returns_runner_evaluation(hass: HomeAssistant, hass_ws_client) -> None:
    entry = add_schedule(hass, "Front lawn")
    client = await hass_ws_client(hass)
    evaluation = {
        "at": "2026-09-14T05:00:00-04:00",
        "scheduled": True,
        "rain_delay_until": None,
        "paused": False,
        "enabled": True,
        "decision": {"water": False, "status": "skipped_rain", "details": {}, "retry": False},
    }

    with patch.object(
        ScheduleRunner, "async_evaluate", autospec=True, return_value=evaluation
    ) as mocked:
        msg = await send(client, {"type": f"{DOMAIN}/evaluate", "entry_id": entry.entry_id})

    assert msg["success"], msg
    assert msg["result"] == evaluation
    mocked.assert_awaited_once_with(entry.runtime_data)


async def test_history_passes_limit(hass: HomeAssistant, hass_ws_client) -> None:
    entry = add_schedule(hass, "Front lawn")
    client = await hass_ws_client(hass)

    msg = await send(client, {"type": f"{DOMAIN}/history", "entry_id": entry.entry_id})
    assert msg["success"], msg
    assert msg["result"] == {"history": []}

    records = [{"type": "run", "status": "idle"}]
    with patch.object(ScheduleRunner, "history", autospec=True, return_value=records) as mocked:
        msg = await send(
            client, {"type": f"{DOMAIN}/history", "entry_id": entry.entry_id, "limit": 5}
        )

    assert msg["success"], msg
    assert msg["result"] == {"history": records}
    mocked.assert_called_once_with(entry.runtime_data, 5)

    msg = await send(
        client, {"type": f"{DOMAIN}/history", "entry_id": entry.entry_id, "limit": 0}
    )
    assert msg["error"]["code"] == "invalid_format"


async def test_pause_resume_all_update_every_schedule(
    hass: HomeAssistant, hass_ws_client
) -> None:
    first = add_schedule(hass, "Back yard")
    second = add_schedule(hass, "Front lawn")
    idle = add_schedule(hass, "Not loaded", state=ConfigEntryState.NOT_LOADED)
    client = await hass_ws_client(hass)

    msg = await send(client, {"type": f"{DOMAIN}/pause_all"})
    assert msg["success"], msg
    assert [schedule["paused"] for schedule in msg["result"]["schedules"]] == [True, True]
    assert first.runtime_data.paused and second.runtime_data.paused
    assert idle.runtime_data.paused is False

    msg = await send(client, {"type": f"{DOMAIN}/resume_all"})
    assert msg["success"], msg
    assert [schedule["paused"] for schedule in msg["result"]["schedules"]] == [False, False]


async def test_stop_all_stops_every_loaded_schedule(hass: HomeAssistant, hass_ws_client) -> None:
    first = add_schedule(hass, "Back yard")
    second = add_schedule(hass, "Front lawn")
    add_schedule(hass, "Not loaded", state=ConfigEntryState.NOT_LOADED)
    client = await hass_ws_client(hass)

    with patch.object(ScheduleRunner, "async_stop_run", autospec=True) as mocked:
        msg = await send(client, {"type": f"{DOMAIN}/stop_all"})

    assert msg["success"], msg
    assert {call.args[0] for call in mocked.await_args_list} == {
        first.runtime_data,
        second.runtime_data,
    }
    assert len(msg["result"]["schedules"]) == 2


@pytest.mark.parametrize(
    ("command", "function"),
    [("generate_report", "async_generate_report"), ("explain_skips", "async_explain_skips")],
)
async def test_ai_commands_return_text(
    hass: HomeAssistant, hass_ws_client, command: str, function: str
) -> None:
    entry = add_schedule(hass, "Front lawn", ai_task_entity="ai_task.claude_ai_task")
    client = await hass_ws_client(hass)

    with patch(
        f"custom_components.irrigation_manager.ai.{function}",
        new_callable=AsyncMock,
        return_value="Watered twice.",
    ) as mocked:
        msg = await send(client, {"type": f"{DOMAIN}/{command}", "entry_id": entry.entry_id})
        assert msg["success"], msg
        assert msg["result"] == {"text": "Watered twice."}
        mocked.assert_awaited_once_with(hass, entry.runtime_data, days=7)

        msg = await send(
            client, {"type": f"{DOMAIN}/{command}", "entry_id": entry.entry_id, "days": 3}
        )
        assert msg["success"], msg
        assert mocked.await_args.kwargs == {"days": 3}


@pytest.mark.parametrize("command", ["generate_report", "explain_skips"])
async def test_ai_commands_require_ai_task_entity(
    hass: HomeAssistant, hass_ws_client, command: str
) -> None:
    entry = add_schedule(hass, "Front lawn")
    client = await hass_ws_client(hass)

    msg = await send(client, {"type": f"{DOMAIN}/{command}", "entry_id": entry.entry_id})

    assert not msg["success"]
    assert msg["error"]["code"] == "ai_not_configured"


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (HomeAssistantError("ai_task.generate_data failed"), "home_assistant_error"),
        ("not_configured", "ai_not_configured"),
    ],
)
async def test_ai_command_errors_are_reported(
    hass: HomeAssistant, hass_ws_client, error: Any, code: str
) -> None:
    from custom_components.irrigation_manager import ai  # noqa: PLC0415

    if error == "not_configured":
        error = ai.AiNotConfigured("Front lawn has no AI task entity")
    entry = add_schedule(hass, "Front lawn", ai_task_entity="ai_task.claude_ai_task")
    client = await hass_ws_client(hass)

    with patch(
        "custom_components.irrigation_manager.ai.async_generate_report",
        new_callable=AsyncMock,
        side_effect=error,
    ):
        msg = await send(
            client, {"type": f"{DOMAIN}/generate_report", "entry_id": entry.entry_id}
        )

    assert not msg["success"]
    assert msg["error"]["code"] == code


@pytest.mark.parametrize(
    "payload",
    [
        {"type": f"{DOMAIN}/set_rain_delay", "hours": 1},
        {"type": f"{DOMAIN}/run_zone", "zone": "valve.deck_zone"},
        {"type": f"{DOMAIN}/evaluate"},
        {"type": f"{DOMAIN}/history"},
        {"type": f"{DOMAIN}/generate_report"},
        {"type": f"{DOMAIN}/explain_skips"},
    ],
    ids=lambda payload: payload["type"].split("/")[1],
)
async def test_v02_commands_on_missing_schedule_are_not_found(
    hass: HomeAssistant, hass_ws_client, payload: dict[str, Any]
) -> None:
    add_schedule(hass, "Front lawn", ai_task_entity="ai_task.claude_ai_task")
    client = await hass_ws_client(hass)

    msg = await send(client, {**payload, "entry_id": "does-not-exist"})

    assert not msg["success"]
    assert msg["error"]["code"] == "not_found"
