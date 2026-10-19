# Migrating to Irrigation Manager

Irrigation Manager can pre-fill new schedules from two existing sources: the legacy `input_*` helpers behind the old drip and grass automations, and B-Hyve on-device programs. Import never creates a schedule on its own — the setup wizard shows what was read, you fill in what's missing and confirm. Code: `custom_components/irrigation_manager/migration.py`.

## Legacy helpers

The setup menu offers **Import legacy helpers** only when at least one of these helpers exists. They come from an earlier helper-and-automation watering setup. If you never had it, the option doesn't appear.

| Helper | Example value | Imported as |
|---|---|---|
| `input_text.drip_irrigation_schedule` | `06:00 2d 30m` | Schedule "Drip irrigation": every 2 days at 06:00, 30 min per zone |
| `input_datetime.drip_irrigation_last_run` | `2026-09-13 06:00:09` | First run date (the every-N-days cadence continues from the last run) |
| `input_boolean.drip_irrigation` | `off` | Not imported; the wizard warns if it's on (both would water) |
| `input_number.rain_threshold` | `0.1` | Rain threshold (you still pick the rain sensor) |
| `input_number.last_rain_interval` ("Grass Watering Interval") | `5` | Optional "Grass watering" schedule: every 5 days |
| `input_text.last_rain` | `09/13/2026` | First run date of the grass schedule: 5 days after the last rain |

Schedule string format: a start time `HH:MM`, an interval `<N>d` (1–31) and a run time `<N>m` (1–180), each exactly once, any order. Anything else is rejected with an error rather than guessed.

What the helpers can't tell, so you choose it in the wizard:

- **Zones.** No helper records which valves the old automation opened.
- **Rain sensor** for the imported threshold.
- **Grass schedule start time, zones and rain sensor.** The grass schedule is an approximation: an every-N-days schedule keeps its cadence when it rains, while the old setup appears to water N days after the last rain (unverified).

Not imported (no schedule equivalent): `input_boolean.grass_watering_sprinkler_automation`, `input_boolean.moisture_automation`, `input_text.setup_irrigation_date`, `input_boolean.setup_irrigation_chore`.

Helpers are read from their current states, so YAML helpers that aren't in the entity registry are found too. A helper that is unavailable at import time is reported as not found.

## B-Hyve on-device programs

The setup menu offers **Import B-Hyve program** only when an orbit_bhyve device has program sensors.

Source: the orbit_bhyve "Program A–D" sensors, e.g. `sensor.garden_irrigation_program_a`. State is `enabled`, `disabled` or `empty`; attributes are `name`, `days`, `start_times` (`HH:MM`), `zones` (`[{zone, minutes}]`, zone 1-indexed) and `budget` (%). Programs load on the device's idle poll, so a sensor with no reading yet is reported, not imported.

Mapping:

| Program | Schedule |
|---|---|
| `Every day` | Days of week, all 7 |
| `Mon, Wed, Fri` | Days of week |
| `Every N days from YYYY-MM-DD` | Every N days from that date (no date: you choose the first run date) |
| `Odd days`, `Even days` | Not imported — every 2 days drifts after 31-day months |
| `Once` | Not imported |
| Several start times | One schedule per start time |
| Zone N | The device's valve for station N (`valve.<device>_zone` on one-station timers) |
| Run time | Whole minutes, rounded half up, limited to 1–180 |
| Budget ≠ 100 % | Run times imported as stored, not scaled; the wizard notes the budget |

Imported zones run sequentially (unverified: assumes the device runs a program's zones one at a time).

**Turn the device program off after importing**, or the device and Irrigation Manager will both water. The wizard can do it for you (it turns off the program's `switch.<device>_program_<x>` switch) only after you confirm. You can also do it from the device page.

## Retiring the old automations

Whatever drove the old setup (automations, scripts or Node-RED flows) keeps running until you turn it off. Switch over in this order so nothing waters twice and nothing is lost:

1. Find the automations or flows that use the helpers above, and any that call a service on the zone valves you imported.
2. Create the new schedules (import or wizard) and leave them enabled.
3. Disable the old automations or flows. Don't delete them yet.
4. Turn off `input_boolean.drip_irrigation` and `input_boolean.grass_watering_sprinkler_automation` if you have them.
5. Let at least one full cycle run (for an every-2-days schedule, two days). Check the schedule's status and last run in the Irrigation panel, and that nothing else opened the valves.
6. Delete the disabled automations or flows, then remove the helpers.
