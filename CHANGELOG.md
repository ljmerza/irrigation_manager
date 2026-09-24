# Changelog

Notable changes to Irrigation Manager. Versions follow semantic versioning; the release workflow sets `manifest.json`'s version from the release tag.

## [0.4.0] — 2026-09-24

Adds copying a schedule.

### Added
- Copy a schedule: **Copy an existing schedule** in the setup menu pre-fills every step from the chosen schedule, zones included, with the name defaulting to `<name> (copy)`. Schedule cards in the panel have a **Copy** button that opens the setup menu.

### Changed
- The schedule's device is looked up with `async_get_device_by_identifier` on Home Assistant 2026.9 and later, where `async_get_device` is deprecated; older versions keep the old lookup.

## [0.3.0] — 2026-09-19

Adds run notifications.

### Added
- Run notifications, per schedule: a new **Notifications** step picks which events to notify about (watering starts, finishes, is stopped early, has an error, or is skipped for any reason) and who gets them: `notify.*` services, `persistent_notification.create` and `notify.*` entities.

### Fixed
- The AI report's notification list no longer offers `notify.send_message`, which needs a notify entity target and failed when picked.
- Diagnostics now redact the notification services and entities, as they already did for the AI report's notification service.

## [0.2.0] — 2026-09-15

Adds rain and weather conditions, automations and API, AI reports, and migration from existing setups.

### Added
- Every N hours frequency: runs every day every N hours between a first and last run time (for example every 3 hours from 06:00 to 18:00).
- Rain and weather:
  - Several rain sensors per schedule, combined by max, median or quorum.
  - Rain window "since the last watering", capped at a maximum number of hours.
  - Rain delay: set from the panel, a button or the `set_rain_delay` service, or automatically after a rain skip.
  - Stop an active run when rain starts.
  - Forecast rain amount (alone, or with the rain chance as either/both) and agreement across several weather entities.
  - Temperature condition: freeze skip from the current reading or forecast low, heat skip from the current reading.
  - Wind condition from a sensor's recent average.
  - Stale sensor hours for the temperature sensor.
- Occupancy condition: delay or skip while an entity is on, and stop an active run when one turns on.
- Runs: pause and resume all schedules, run a single zone, "check now" condition evaluation, persisted run and skip history.
- Automations and API:
  - `irrigation_manager_event` bus events, device triggers (8 event types) and device conditions (running, enabled, paused, rain delay active).
  - Services `set_rain_delay`, `run_zone`, `set_enabled`, `evaluate`, `get_history`, `pause_all`, `resume_all`, `stop_all`, `generate_report`, `explain_skips`; `run_now`, `skip_next` and `stop` can return the schedule's state.
  - Blueprints: notify on skip or error, stop while an entity is on, skip next when an entity is on.
  - Diagnostics download.
  - Assist intents: run now, skip next, stop, status.
- AI (opt-in, per schedule): weekly report through an `ai_task` entity sent as a notification, optional camera analysis through LLM Vision, skip explanations, and "describe in words" to pre-fill a new schedule.
- Migration: import from the legacy watering helpers and from B-Hyve programs (with an optional, unticked-by-default step to turn the device program off); migration guide.
- Entities: rain delay sensor, problem binary sensor, clear rain delay button; the status sensor gains `paused`, `rain_delay_until` and `unclosed_zones` attributes.
- Panel: pause/resume/stop all, rain delay presets, unclosed-zone banner, check now, history, run a single zone, AI report and skip explanation dialogs, text for every new status.
- HACS readiness: brand icon, validate / tests / release workflows, issue templates, submission checklist.

### Changed
- Rain delays are no longer copied to the device's own rain delay (the B-Hyve rain delay number). A delay applies to this integration's schedules only; the `rain_delay_mirror` option is gone and is ignored on existing schedules.
- **Add integration** opens a menu: create manually, import legacy helpers, import a B-Hyve program, or describe in words.
- Saving a schedule from the options flow stores `rain_sensors` / `weather_entities` lists in place of the single `rain_sensor` / `weather_entity`. Schedules that aren't edited keep working unchanged.

### Fixed
- A zone on a device that stops itself (B-Hyve, Rachio) was also sent a close when its time was up. On B-Hyve HT25A fw0098 that close starts a new 30-minute run, so a 30-minute schedule watered for an hour. The close is now sent only if a fresh device read still shows the zone open 10 and 20 seconds after its end; every close is verified against the entity state, and retries for a zone left open read the entity first and never send two closes within 15 seconds.
- A zone whose close failed at the end of its time was forgotten and never closed again. It is now kept on a persisted list and retried until it closes.
- Entering a non-number in a whole-number setup field crashed the step; it now shows an error.

## [0.1.0]

Initial version.

### Added
- One config entry per schedule: zones (valves/switches) with per-zone minutes, sequential or concurrent.
- Every N days or chosen weekdays; fixed time, or finish by sunrise/sunset.
- Conditions: rain total over a look-back window, forecast precipitation probability, soil moisture (skip and trigger modes).
- Native run-time drivers for `orbit_bhyve`, `rachio` and `rachio_local`; plain on/off for other valves and switches.
- Entities, `run_now` / `skip_next` / `stop` services, and an admin sidebar panel.
- Zones are closed on shutdown and after a restart that interrupted a run.

### Fixed
- Forecast probability and moisture threshold now require at least 1 %; a threshold of 0 made every run skip.
