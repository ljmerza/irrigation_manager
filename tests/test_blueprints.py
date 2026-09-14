"""The shipped blueprints parse, their inputs are valid, and they build valid automations."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from homeassistant.components.automation.config import async_validate_config_item
from homeassistant.components.blueprint.models import Blueprint, BlueprintInputs
from homeassistant.components.blueprint.schemas import BLUEPRINT_SCHEMA
from homeassistant.core import HomeAssistant
from homeassistant.util import yaml as yaml_util

BLUEPRINT_DIR = (
    Path(__file__).resolve().parent.parent / "blueprints" / "automation" / "irrigation_manager"
)

SAMPLE_INPUTS: dict[str, dict[str, Any]] = {
    "notify_on_skip_or_error.yaml": {"schedule": "0123456789abcdef"},
    "stop_while_entity_on.yaml": {
        "schedule": "01J0000000000000000000000",
        "watched_entity": "binary_sensor.back_yard_person_occupancy",
    },
    "skip_next_when_entity_on.yaml": {
        "schedule": "01J0000000000000000000000",
        "watched_entity": "input_boolean.lawn_treated",
    },
}


def test_every_blueprint_has_sample_inputs() -> None:
    assert sorted(path.name for path in BLUEPRINT_DIR.glob("*.yaml")) == sorted(SAMPLE_INPUTS)


@pytest.mark.parametrize("filename", sorted(SAMPLE_INPUTS))
async def test_blueprint_builds_valid_automation(hass: HomeAssistant, filename: str) -> None:
    path = BLUEPRINT_DIR / filename
    data = await hass.async_add_executor_job(yaml_util.load_yaml, str(path))

    blueprint = Blueprint(data, expected_domain="automation", schema=BLUEPRINT_SCHEMA)
    assert blueprint.validate() is None

    inputs = BlueprintInputs(
        blueprint, {"use_blueprint": {"path": filename, "input": SAMPLE_INPUTS[filename]}}
    )
    inputs.validate()
    config = inputs.async_substitute()

    # Raises on any invalid trigger, condition or action.
    assert await async_validate_config_item(hass, filename, config) is not None


async def test_stop_blueprint_turns_schedule_back_on_after_restart_or_reload(
    hass: HomeAssistant,
) -> None:
    filename = "stop_while_entity_on.yaml"
    data = await hass.async_add_executor_job(yaml_util.load_yaml, str(BLUEPRINT_DIR / filename))
    blueprint = Blueprint(data, expected_domain="automation", schema=BLUEPRINT_SCHEMA)
    inputs = BlueprintInputs(
        blueprint, {"use_blueprint": {"path": filename, "input": SAMPLE_INPUTS[filename]}}
    )
    config = inputs.async_substitute()
    watched = SAMPLE_INPUTS[filename]["watched_entity"]

    resume_triggers = [t for t in config["triggers"] if t.get("id") == "resume_check"]
    assert {"trigger": "homeassistant", "event": "start", "id": "resume_check"} in resume_triggers
    assert {
        "trigger": "event",
        "event_type": "automation_reloaded",
        "id": "resume_check",
    } in resume_triggers

    branch = next(
        option
        for option in config["actions"][0]["choose"]
        if option["conditions"][0].get("id") == "resume_check"
    )
    off = {"condition": "state", "entity_id": watched, "state": "off"}
    assert branch["conditions"][1] == off
    assert branch["sequence"][0] == {"delay": {"minutes": 10}}  # the input default
    assert branch["sequence"][1] == off  # still off after the wait
    assert branch["sequence"][2]["action"] == "irrigation_manager.set_enabled"
    assert branch["sequence"][2]["data"]["enabled"] is True
    assert config["mode"] == "restart"  # an "on" trigger cancels the wait
    assert "even if you had turned it off" in blueprint.metadata["description"]

    assert await async_validate_config_item(hass, filename, config) is not None


async def test_notify_blueprint_default_action_uses_message(hass: HomeAssistant) -> None:
    data = await hass.async_add_executor_job(
        yaml_util.load_yaml, str(BLUEPRINT_DIR / "notify_on_skip_or_error.yaml")
    )
    blueprint = Blueprint(data, expected_domain="automation", schema=BLUEPRINT_SCHEMA)

    default = blueprint.inputs["notify_actions"]["default"]
    assert default[0]["data"]["message"] == "{{ message }}"
