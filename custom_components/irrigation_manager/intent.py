"""Assist intents: run, skip, stop and ask about a schedule by name.

Schedules are matched by title, case-insensitively; a single partial match also
works. The handlers are restricted to the valve and switch platforms, so the
Assist LLM API only offers them as tools to an agent that has at least one valve
or switch exposed (helpers/llm.py filters `platforms` by exposed domains;
nothing else in core reads it). Run now also refuses when none of the
schedule's own zones is exposed to the calling assistant. The built-in
conversation agent only uses them with custom sentences (docs/assist.md).
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

import voluptuous as vol

from homeassistant.components.homeassistant.exposed_entities import async_should_expose
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv, intent
from homeassistant.util import dt as dt_util

from .const import (
    CONF_ZONES,
    DOMAIN,
    MAX_ZONE_MINUTES,
    MIN_ZONE_MINUTES,
    Status,
    zone_entity_ids,
)
from .entity import zone_name
from .services import async_loaded_runners, async_run_now

if TYPE_CHECKING:
    from .runner import ScheduleRunner

INTENT_RUN_NOW = "IrrigationRunNow"
INTENT_SKIP_NEXT = "IrrigationSkipNext"
INTENT_STOP = "IrrigationStop"
INTENT_STATUS = "IrrigationStatus"

SLOT_NAME = "name"
SLOT_MINUTES = "minutes"

DATA_INTENTS_REGISTERED = f"{DOMAIN}_intents_registered"


async def async_setup_intents(hass: HomeAssistant) -> None:
    """Register the intent handlers once per Home Assistant run."""
    if hass.data.get(DATA_INTENTS_REGISTERED):
        return
    hass.data[DATA_INTENTS_REGISTERED] = True
    for handler in (
        RunNowIntentHandler(),
        SkipNextIntentHandler(),
        StopIntentHandler(),
        StatusIntentHandler(),
    ):
        intent.async_register(hass, handler)


class _ScheduleIntentHandler(intent.IntentHandler):
    """Resolves the `name` slot to a loaded schedule, then acts on it."""

    # Offered to LLM agents only when a valve or switch is exposed to them.
    platforms = {"valve", "switch"}

    @property
    def slot_schema(self) -> dict | None:
        return {vol.Required(SLOT_NAME): cv.string}

    async def async_handle(self, intent_obj: intent.Intent) -> intent.IntentResponse:
        hass = intent_obj.hass
        slots = self.async_validate_slots(intent_obj.slots)
        runner = _async_match_schedule(hass, slots[SLOT_NAME]["value"])
        self._async_check_allowed(intent_obj, runner)
        try:
            speech = await self._async_act(hass, runner, slots)
        except intent.IntentError:
            raise
        except HomeAssistantError as err:
            raise intent.IntentHandleError(
                f"{runner.entry.title}: {err or 'request failed'}"
            ) from err
        response = intent_obj.create_response()
        response.async_set_speech(speech)
        return response

    @callback
    def _async_check_allowed(
        self, intent_obj: intent.Intent, runner: ScheduleRunner
    ) -> None:
        """Raise IntentHandleError when the calling assistant may not do this."""

    async def _async_act(
        self, hass: HomeAssistant, runner: ScheduleRunner, slots: dict[str, Any]
    ) -> str:
        raise NotImplementedError


class RunNowIntentHandler(_ScheduleIntentHandler):
    intent_type = INTENT_RUN_NOW
    description = (
        "Starts watering an irrigation schedule now, ignoring rain, forecast and "
        "moisture checks. Optional minutes sets the run time of every zone."
    )

    @callback
    def _async_check_allowed(
        self, intent_obj: intent.Intent, runner: ScheduleRunner
    ) -> None:
        # Starting water is the one action that opens valves: require that the
        # assistant can see at least one of this schedule's zones.
        assistant = intent_obj.assistant
        if assistant is None:
            return
        try:
            exposed = any(
                async_should_expose(intent_obj.hass, assistant, entity_id)
                for entity_id in zone_entity_ids(runner.config)
            )
        except KeyError:  # exposed-entities store not set up; nothing to enforce
            return
        if not exposed:
            raise intent.IntentHandleError(
                f"None of {runner.entry.title}'s zones are exposed to {assistant}"
            )

    @property
    def slot_schema(self) -> dict | None:
        return {
            vol.Required(SLOT_NAME): cv.string,
            vol.Optional(SLOT_MINUTES): vol.All(
                vol.Coerce(int), vol.Range(min=MIN_ZONE_MINUTES, max=MAX_ZONE_MINUTES)
            ),
        }

    async def _async_act(
        self, hass: HomeAssistant, runner: ScheduleRunner, slots: dict[str, Any]
    ) -> str:
        title = runner.entry.title
        if runner.running:
            return f"{title} is already watering."
        if not runner.config.get(CONF_ZONES):
            return f"{title} has no zones."
        minutes = slots.get(SLOT_MINUTES, {}).get("value")
        await async_run_now(runner, minutes)
        if minutes is None:
            return f"Started watering {title}."
        return f"Watering {title} for {minutes} minutes per zone."


class SkipNextIntentHandler(_ScheduleIntentHandler):
    intent_type = INTENT_SKIP_NEXT
    description = "Skips the next scheduled run of an irrigation schedule."

    async def _async_act(
        self, hass: HomeAssistant, runner: ScheduleRunner, slots: dict[str, Any]
    ) -> str:
        await runner.async_set_skip_next(True)
        title = runner.entry.title
        occurrence = runner.next_occurrence
        if occurrence is None:
            return f"{title} will skip its next run."
        return f"{title} will skip its run {_when(occurrence.start)}."


class StopIntentHandler(_ScheduleIntentHandler):
    intent_type = INTENT_STOP
    description = "Stops an irrigation schedule that is watering now."

    async def _async_act(
        self, hass: HomeAssistant, runner: ScheduleRunner, slots: dict[str, Any]
    ) -> str:
        title = runner.entry.title
        if not runner.running:
            return f"{title} is not watering."
        await runner.async_stop_run()
        return f"Stopped watering {title}."


class StatusIntentHandler(_ScheduleIntentHandler):
    intent_type = INTENT_STATUS
    description = (
        "Reports whether an irrigation schedule is watering, its last result, any "
        "rain delay, and its next run."
    )

    async def _async_act(
        self, hass: HomeAssistant, runner: ScheduleRunner, slots: dict[str, Any]
    ) -> str:
        title = runner.entry.title
        if runner.running:
            text = f"{title} is watering"
            if (zone := runner.current_zone) is not None:
                text += f" {zone_name(hass, zone)}"
            if (ends_at := runner.current_zone_ends_at) is not None:
                text += f" until {dt_util.as_local(ends_at):%H:%M}"
            parts = [f"{text}."]
        else:
            parts = [f"{title} is {_status_phrase(runner.status)}."]

        until = runner.rain_delay_until
        if until is not None and until > dt_util.utcnow():
            parts.append(f"Rain delay until {_when(until)}.")
        if (occurrence := runner.next_occurrence) is not None:
            parts.append(f"Next run {_when(occurrence.start)}.")
        return " ".join(parts)


@callback
def _async_match_schedule(hass: HomeAssistant, name: str) -> ScheduleRunner:
    """The loaded schedule called `name`; raises when none or several match."""
    wanted = name.strip().casefold()
    runners = async_loaded_runners(hass)
    matches = [runner for runner in runners if runner.entry.title.casefold() == wanted]
    if not matches and wanted:
        matches = [
            runner
            for runner in runners
            if wanted in runner.entry.title.casefold()
            or runner.entry.title.casefold() in wanted
        ]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        raise intent.IntentHandleError(f"No irrigation schedule named {name}")
    names = ", ".join(sorted(runner.entry.title for runner in matches))
    raise intent.IntentHandleError(
        f"More than one irrigation schedule matches {name}: {names}"
    )


_STATUS_PHRASES: dict[Status, str] = {
    Status.IDLE: "idle",
    Status.RUNNING: "watering",
    Status.DISABLED: "turned off",
    Status.PAUSED: "paused",
    Status.INTERRUPTED: "idle; its last run was interrupted",
    Status.ERROR: "idle; its last run had an error",
}


def _status_phrase(status: Status) -> str:
    if status in _STATUS_PHRASES:
        return _STATUS_PHRASES[status]
    value = str(status)
    for prefix, verb in (("skipped_", "skipped"), ("stopped_", "stopped")):
        if value.startswith(prefix):
            reason = value.removeprefix(prefix).replace("_", " ")
            return f"idle; its last run was {verb} ({reason})"
    return value.replace("_", " ")


def _when(moment: datetime) -> str:
    """'today at 06:00', 'tomorrow at 06:00', 'Friday at 06:00' or 'on 2 October at 06:00'."""
    local = dt_util.as_local(moment)
    days = (local.date() - dt_util.now().date()).days
    clock = f"{local:%H:%M}"
    if days == 0:
        return f"today at {clock}"
    if days == 1:
        return f"tomorrow at {clock}"
    if 1 < days < 7:
        return f"{local:%A} at {clock}"
    return f"on {local.day} {local:%B} at {clock}"
