# Assist / voice control

Irrigation Manager registers four intents. Each takes the schedule's name (its config entry title) in the `name` slot. Matching ignores case, and a partial name works when it matches exactly one schedule.

| Intent | Slots | What it does |
|---|---|---|
| `IrrigationRunNow` | `name`, optional `minutes` (1–180) | Starts a manual run, ignoring conditions. `minutes` sets every zone's run time. |
| `IrrigationSkipNext` | `name` | Sets "skip next run". |
| `IrrigationStop` | `name` | Stops an active run. |
| `IrrigationStatus` | `name` | Says whether it is watering (zone and end time), its last result, any rain delay, and the next run. |

Replies are English only.

## How the intents get registered

Home Assistant's `intent` integration loads `intent.py` from every loaded integration and calls its `async_setup_intents` (checked in core `components/intent/__init__.py`, in both 2025.1 and 2026.x). `intent` is loaded whenever `conversation` is (it is a dependency), which `default_config` includes. No configuration is needed.

## LLM conversation agents (Claude, OpenAI, Ollama)

When a conversation agent is set to control Home Assistant with the **Assist** API, Home Assistant offers every registered intent handler as a tool unless it is on a short ignore list. Handlers with no platform restriction are included (checked in core `helpers/llm.py`, `AssistAPI._async_get_tools`). These handlers have no platform restriction and carry a description, so the agent can call them directly, for example after "skip watering the garden bed tomorrow". Tool names are the slugified intent names, e.g. `irrigationrunnow`.

## Built-in conversation agent: custom sentences

The built-in agent only matches sentences it knows. Add a custom sentences file to your Home Assistant config at `config/custom_sentences/en/irrigation_manager.yaml`, then restart:

```yaml
language: "en"
intents:
  IrrigationRunNow:
    data:
      - sentences:
          - "(water|run|start) [the] {irrigation_schedule:name} for {irrigation_minutes:minutes} minute[s]"
          - "(water|run|start watering) [the] {irrigation_schedule:name} [now]"
  IrrigationSkipNext:
    data:
      - sentences:
          - "skip [the] next [watering|run] [for|of] [the] {irrigation_schedule:name}"
          - "skip watering [the] {irrigation_schedule:name}"
  IrrigationStop:
    data:
      - sentences:
          - "stop watering [the] {irrigation_schedule:name}"
          - "stop [the] {irrigation_schedule:name}"
  IrrigationStatus:
    data:
      - sentences:
          - "(is|when is) [the] {irrigation_schedule:name} [watering|running|going to water]"
          - "[what is the] status of [the] {irrigation_schedule:name}"
lists:
  irrigation_schedule:
    wildcard: true
  irrigation_minutes:
    range:
      from: 1
      to: 180
```

Unverified:
- The `{list_name:slot_name}` syntax maps a list to the `name` slot. It is used here to avoid clashing with the built-in `name` list of entity names; it was not tested against the live conversation agent.
- A wildcard list followed by more words ("water the garden bed for 10 minutes") may match loosely. If it doesn't match reliably, use sentences where the schedule name comes last.

Example sentences once installed:

- "Water the garden bed for 10 minutes"
- "Skip the next watering for the front lawn"
- "Stop watering the garden bed"
- "What is the status of the garden bed"
