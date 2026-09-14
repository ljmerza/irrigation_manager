// Text for the panel: dates in the user's HA locale/time zone, and plain-English
// summaries of schedule config, status and condition details.

import type { Evaluation, HistoryRecord, HomeAssistant, Schedule, ScheduleConfig } from "./types";

export type Tone = "ok" | "info" | "warn" | "error" | "muted";

export interface DetailLine {
  text: string;
  tone?: Tone;
}

type Details = Record<string, any> | undefined;

const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]; // backend: 0=Mon

const STATUS: Record<string, { label: string; tone: Tone }> = {
  idle: { label: "Idle", tone: "muted" },
  running: { label: "Running", tone: "info" },
  disabled: { label: "Disabled", tone: "muted" },
  paused: { label: "Paused", tone: "muted" },
  skipped_rain: { label: "Skipped: rain", tone: "warn" },
  skipped_forecast: { label: "Skipped: forecast", tone: "warn" },
  skipped_temperature: { label: "Skipped: temperature", tone: "warn" },
  skipped_wind: { label: "Skipped: wind", tone: "warn" },
  skipped_occupancy: { label: "Skipped: occupied", tone: "warn" },
  skipped_moisture: { label: "Skipped: soil moisture", tone: "warn" },
  skipped_rain_delay: { label: "Skipped: rain delay", tone: "warn" },
  skipped_manual: { label: "Skipped: manual", tone: "warn" },
  skipped_busy: { label: "Skipped: still running", tone: "warn" },
  stopped_rain: { label: "Stopped: rain started", tone: "warn" },
  stopped_occupancy: { label: "Stopped: occupied", tone: "warn" },
  interrupted: { label: "Interrupted", tone: "error" },
  error: { label: "Error", tone: "error" },
};

export const statusLabel = (status: string): string => STATUS[status]?.label ?? status;
export const statusTone = (status: string): Tone => STATUS[status]?.tone ?? "muted";

export const entityName = (hass: HomeAssistant, entityId: string | null | undefined): string => {
  if (!entityId) {
    return "";
  }
  return hass.states[entityId]?.attributes.friendly_name ?? entityId;
};

const names = (hass: HomeAssistant, entityIds: string[]): string =>
  entityIds.map((id) => entityName(hass, id)).join(", ");

/** " in" style unit suffix from an entity's unit_of_measurement, or "". */
const unitSuffix = (hass: HomeAssistant, entityId: string | undefined): string => {
  const unit = hass.states[entityId ?? ""]?.attributes.unit_of_measurement;
  return unit ? ` ${unit}` : "";
};

const language = (hass: HomeAssistant): string => hass.locale?.language ?? hass.language ?? "en";

const timeOptions = (hass: HomeAssistant): Intl.DateTimeFormatOptions => {
  const options: Intl.DateTimeFormatOptions = {};
  if (hass.locale?.time_zone !== "local" && hass.config?.time_zone) {
    options.timeZone = hass.config.time_zone;
  }
  if (hass.locale?.time_format === "12") {
    options.hour12 = true;
  } else if (hass.locale?.time_format === "24") {
    options.hour12 = false;
  }
  return options;
};

export const formatNumber = (hass: HomeAssistant, value: number, digits = 2): string =>
  Number(value).toLocaleString(language(hass), { maximumFractionDigits: digits });

export const formatDateTime = (hass: HomeAssistant, iso: string): string =>
  new Date(iso).toLocaleString(language(hass), {
    ...timeOptions(hass),
    weekday: "short",
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });

export const formatTime = (hass: HomeAssistant, iso: string): string =>
  new Date(iso).toLocaleTimeString(language(hass), {
    ...timeOptions(hass),
    hour: "numeric",
    minute: "2-digit",
  });

/** "YYYY-MM-DD" as a calendar date, without shifting it through a time zone. */
export const formatDate = (hass: HomeAssistant, isoDate: string): string => {
  const [year, month, day] = isoDate.split("-").map(Number);
  if (!year || !month || !day) {
    return isoDate;
  }
  return new Date(year, month - 1, day).toLocaleDateString(language(hass), {
    weekday: "short",
    month: "short",
    day: "numeric",
    year: "numeric",
  });
};

/** "HH:MM:SS" wall-clock time in the user's 12/24 h preference. */
export const formatClock = (hass: HomeAssistant, clock: string): string => {
  const [hour, minute] = clock.split(":").map(Number);
  if (Number.isNaN(hour) || Number.isNaN(minute)) {
    return clock;
  }
  const { hour12 } = timeOptions(hass);
  return new Date(2000, 0, 1, hour, minute).toLocaleTimeString(language(hass), {
    hour: "numeric",
    minute: "2-digit",
    ...(hour12 === undefined ? {} : { hour12 }),
  });
};

const plural = (count: number, unit: string): string => `${count} ${unit}${count === 1 ? "" : "s"}`;

const durationText = (totalMinutes: number): string => {
  const days = Math.floor(totalMinutes / 1440);
  const hours = Math.floor((totalMinutes % 1440) / 60);
  const minutes = totalMinutes % 60;
  if (days > 0) {
    return hours > 0 ? `${days} d ${hours} h` : `${days} d`;
  }
  if (hours > 0) {
    return minutes > 0 ? `${hours} h ${minutes} min` : `${hours} h`;
  }
  return `${minutes} min`;
};

/** "in 3 h 20 min" / "5 min ago" / "now". */
export const relativeTime = (iso: string, now: number): string => {
  const diffMinutes = Math.round((new Date(iso).getTime() - now) / 60000);
  if (diffMinutes === 0) {
    return "now";
  }
  return diffMinutes > 0
    ? `in ${durationText(diffMinutes)}`
    : `${durationText(-diffMinutes)} ago`;
};

/** Remaining time as m:ss or h:mm:ss. */
export const countdown = (iso: string, now: number): string => {
  const seconds = Math.max(0, Math.round((new Date(iso).getTime() - now) / 1000));
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  const pad = (value: number) => String(value).padStart(2, "0");
  return h > 0 ? `${h}:${pad(m)}:${pad(s)}` : `${m}:${pad(s)}`;
};

export const frequencySummary = (hass: HomeAssistant, config: ScheduleConfig): string => {
  if (config.frequency === "interval") {
    const days = config.interval_days ?? 1;
    const every = days === 1 ? "Every day" : `Every ${days} days`;
    return config.anchor ? `${every} from ${formatDate(hass, config.anchor)}` : every;
  }
  const days = [...(config.weekdays ?? [])].sort((a, b) => a - b);
  if (days.length === 7) {
    return "Every day";
  }
  return days.length ? days.map((day) => WEEKDAYS[day] ?? String(day)).join(", ") : "No days";
};

export const startSummary = (hass: HomeAssistant, config: ScheduleConfig): string => {
  if (config.start_mode === "time") {
    return config.start_time ? `Starts at ${formatClock(hass, config.start_time)}` : "Fixed time";
  }
  const event = config.start_mode === "sunset" ? "sunset" : "sunrise";
  const offset = config.sun_offset_minutes ?? 0;
  if (offset === 0) {
    return `Finishes at ${event}`;
  }
  return offset > 0
    ? `Finishes ${durationText(offset)} before ${event}`
    : `Finishes ${durationText(-offset)} after ${event}`;
};

export const zoneModeText = (config: ScheduleConfig): string =>
  config.zone_mode === "concurrent" ? "All zones at once" : "One zone at a time";

/** v0.2 list keys win; v0.1 single keys are the fallback. */
const rainSensors = (config: ScheduleConfig): string[] =>
  config.rain_sensors?.length ? config.rain_sensors : config.rain_sensor ? [config.rain_sensor] : [];

const weatherEntities = (config: ScheduleConfig): string[] =>
  config.weather_entities?.length
    ? config.weather_entities
    : config.weather_entity
      ? [config.weather_entity]
      : [];

const isSet = (value: number | null | undefined): value is number =>
  value !== null && value !== undefined;

export const conditionLines = (hass: HomeAssistant, config: ScheduleConfig): string[] => {
  const conditions = config.skip_conditions ?? [];
  const lines: string[] = [];

  if (conditions.includes("rain")) {
    const sensors = rainSensors(config);
    const unit = unitSuffix(hass, sensors[0]);
    const window =
      config.rain_window === "since_last_watering"
        ? `since the last watering (at most ${plural(config.rain_max_hours ?? 168, "hour")})`
        : `in the last ${plural(config.rain_hours ?? 24, "hour")}`;
    let source: string;
    if (sensors.length <= 1) {
      source = entityName(hass, sensors[0]);
    } else if (config.rain_aggregate === "median") {
      source = `median of ${sensors.length} stations`;
    } else if (config.rain_aggregate === "quorum") {
      source = `at least ${config.rain_quorum ?? 2} of ${sensors.length} stations`;
    } else {
      source = `any of ${sensors.length} stations`;
    }
    lines.push(
      `Skip if ≥ ${formatNumber(hass, config.rain_threshold ?? 0)}${unit} of rain ${window} (${source})`
    );
    const autoHours = config.rain_delay_auto_hours ?? 0;
    if (autoHours > 0) {
      lines.push(
        `After a rain skip, delay watering ${plural(autoHours, "hour")}` +
          (config.rain_delay_mirror ? " (also on B-Hyve devices)" : "")
      );
    } else if (config.rain_delay_mirror) {
      lines.push("Rain delays are also set on B-Hyve devices");
    }
    if (config.rain_stop_during_run) {
      lines.push(
        `Stop a run when ${formatNumber(hass, config.rain_stop_amount ?? 0.05)}${unit} of new rain falls`
      );
    }
  }

  if (conditions.includes("forecast")) {
    const entities = weatherEntities(config);
    const chance = `the rain chance is ≥ ${config.forecast_probability ?? 0}%`;
    const amount = `the forecast rain is ≥ ${formatNumber(hass, config.forecast_amount ?? 0)}`;
    const mode = config.forecast_mode ?? "probability";
    const test =
      mode === "amount"
        ? amount
        : mode === "either"
          ? `${chance} or ${amount}`
          : mode === "both"
            ? `${chance} and ${amount}`
            : chance;
    const quorum = Math.min(config.forecast_quorum ?? 1, Math.max(entities.length, 1));
    const source =
      entities.length <= 1
        ? entityName(hass, entities[0])
        : quorum <= 1
          ? `any of ${entities.length} forecasts`
          : `${quorum} of ${entities.length} forecasts`;
    lines.push(
      `Skip if ${test} in the next ${plural(config.forecast_hours ?? 12, "hour")} (${source})`
    );
  }

  if (conditions.includes("temperature")) {
    const unit = hass.states[config.temperature_sensor ?? ""]?.attributes.unit_of_measurement ?? "°";
    const hoursAhead = config.temperature_forecast_hours ?? 12;
    const parts: string[] = [];
    if (isSet(config.temperature_min)) {
      const forecast =
        hoursAhead > 0 && weatherEntities(config).length
          ? ` (or the forecast low in the next ${plural(hoursAhead, "hour")})`
          : "";
      parts.push(`at or below ${formatNumber(hass, config.temperature_min, 1)}${unit}${forecast}`);
    }
    if (isSet(config.temperature_max)) {
      parts.push(`at or above ${formatNumber(hass, config.temperature_max, 1)}${unit}`);
    }
    if (parts.length) {
      const source = config.temperature_sensor
        ? ` (${entityName(hass, config.temperature_sensor)})`
        : "";
      lines.push(`Skip if the temperature is ${parts.join(" or ")}${source}`);
    }
    if ((config.stale_hours ?? 0) > 0) {
      lines.push(
        `Ignore a temperature reading older than ${plural(config.stale_hours ?? 0, "hour")}`
      );
    }
  }

  if (conditions.includes("wind")) {
    lines.push(
      `Skip if the average wind over ${config.wind_minutes ?? 30} min is ≥ ` +
        `${formatNumber(hass, config.wind_max ?? 0, 1)}${unitSuffix(hass, config.wind_sensor)} ` +
        `(${entityName(hass, config.wind_sensor)})`
    );
  }

  if (conditions.includes("occupancy")) {
    const who = names(hass, config.occupancy_entities ?? []) || "an occupancy entity";
    lines.push(
      config.occupancy_action === "skip"
        ? `Skip while ${who} is on`
        : `Wait up to ${config.occupancy_max_delay_minutes ?? 60} min while ${who} is on, then skip`
    );
    if (config.occupancy_stop_during_run) {
      lines.push("Stop a run when an occupancy entity turns on");
    }
  }

  if (conditions.includes("moisture")) {
    const sensors = config.moisture_sensors ?? [];
    const which =
      sensors.length === 1 ? entityName(hass, sensors[0]) : `any of ${sensors.length} sensors`;
    const threshold = formatNumber(hass, config.moisture_threshold ?? 0, 1);
    if (config.moisture_mode === "trigger") {
      lines.push(`Also waters on other days when ${which} reads below ${threshold}%`);
    } else {
      const fallback = config.moisture_unavailable === "skip" ? "skip" : "water anyway";
      lines.push(`Only waters when ${which} reads below ${threshold}% (no readings: ${fallback})`);
    }
  }
  return lines;
};

const unavailable = (label: string, details: Record<string, any>): DetailLine => ({
  text: `${label}: no data${details.reason ? ` (${details.reason})` : ""}`,
  tone: "muted",
});

const rainLines = (hass: HomeAssistant, rain: Details): DetailLine[] => {
  if (!rain) {
    return [];
  }
  if (!isSet(rain.total)) {
    return [unavailable("Rain", rain)];
  }
  const unit = rain.unit ? ` ${rain.unit}` : "";
  const threshold = `${formatNumber(hass, rain.threshold ?? 0)}${unit}`;
  const window =
    rain.window === "since_last_watering" && rain.window_start
      ? `since ${formatDateTime(hass, rain.window_start)}`
      : `in the last ${plural(rain.hours ?? 0, "hour")}`;
  const stations: Record<string, { total: number | null }> | undefined = rain.stations;
  const lines: DetailLine[] = [];

  if (stations && rain.aggregate === "quorum") {
    const hit = (rain.stations_over ?? 0) >= (rain.quorum ?? 1);
    lines.push({
      text:
        `Rain ${window}: ${rain.stations_over ?? 0} of ${rain.stations_reporting ?? 0} stations ` +
        `≥ ${threshold} (need ${rain.quorum ?? 1})`,
      tone: hit ? "warn" : undefined,
    });
  } else {
    const label = !stations ? "Rain" : rain.aggregate === "median" ? "Median rain" : "Most rain";
    const over = isSet(rain.threshold) && rain.total >= rain.threshold;
    lines.push({
      text: `${label} ${formatNumber(hass, rain.total)}${unit} ${window} ${over ? "≥" : "<"} ${threshold}`,
      tone: over ? "warn" : undefined,
    });
  }
  if (stations) {
    lines.push({
      text: Object.entries(stations)
        .map(
          ([id, station]) =>
            `${entityName(hass, id)}: ${
              isSet(station.total) ? `${formatNumber(hass, station.total)}${unit}` : "no data"
            }`
        )
        .join(" · "),
      tone: "muted",
    });
  }
  return lines;
};

const forecastLines = (hass: HomeAssistant, forecast: Details): DetailLine[] => {
  if (!forecast) {
    return [];
  }
  const hasProbability = isSet(forecast.max_probability);
  const hasAmount = isSet(forecast.amount);
  if (!hasProbability && !hasAmount) {
    return [unavailable("Forecast", forecast)];
  }
  const mode = forecast.mode ?? "probability";
  const lines: DetailLine[] = [];
  if (hasProbability && mode !== "amount") {
    const over = isSet(forecast.threshold) && forecast.max_probability >= forecast.threshold;
    const when = forecast.at ? ` at ${formatDateTime(hass, forecast.at)}` : "";
    lines.push({
      text:
        `Forecast ${forecast.max_probability}% rain chance${when} ` +
        `${over ? "≥" : "<"} ${forecast.threshold}%` +
        (forecast.forecast_type ? ` (${String(forecast.forecast_type).replace("_", " ")})` : ""),
      tone: over ? "warn" : undefined,
    });
  }
  if (hasAmount && mode !== "probability") {
    const unit = forecast.amount_unit ? ` ${forecast.amount_unit}` : "";
    const over = isSet(forecast.amount_threshold) && forecast.amount >= forecast.amount_threshold;
    lines.push({
      text:
        `Forecast rain ${formatNumber(hass, forecast.amount)}${unit} in the next ` +
        `${plural(forecast.hours ?? 0, "hour")} ${over ? "≥" : "<"} ` +
        `${formatNumber(hass, forecast.amount_threshold ?? 0)}${unit}`,
      tone: over ? "warn" : undefined,
    });
  }
  if (forecast.entities) {
    const hit = (forecast.entities_triggering ?? 0) >= (forecast.quorum ?? 1);
    lines.push({
      text:
        `${forecast.entities_triggering ?? 0} of ${forecast.entities_available ?? 0} forecasts ` +
        `reached the limit (need ${forecast.quorum ?? 1})`,
      tone: hit ? "warn" : "muted",
    });
  }
  return lines;
};

const temperatureLines = (hass: HomeAssistant, temperature: Details): DetailLine[] => {
  if (!temperature) {
    return [];
  }
  const hasCurrent = isSet(temperature.current);
  const hasLow = isSet(temperature.forecast_low);
  if (!hasCurrent && !hasLow) {
    return [unavailable("Temperature", temperature)];
  }
  const unit = temperature.unit ?? "";
  const readings: string[] = [];
  if (hasCurrent) {
    readings.push(`${formatNumber(hass, temperature.current, 1)}${unit} now`);
  }
  if (hasLow) {
    readings.push(`forecast low ${formatNumber(hass, temperature.forecast_low, 1)}${unit}`);
  }
  const limits: string[] = [];
  if (isSet(temperature.min)) {
    limits.push(`min ${formatNumber(hass, temperature.min, 1)}${unit}`);
  }
  if (isSet(temperature.max)) {
    limits.push(`max ${formatNumber(hass, temperature.max, 1)}${unit}`);
  }
  const trigger: Record<string, string> = {
    freeze: " — at or below the minimum",
    freeze_forecast: " — forecast low at or below the minimum",
    heat: " — at or above the maximum",
  };
  const lines: DetailLine[] = [
    {
      text:
        `Temperature ${readings.join(", ")}` +
        (limits.length ? ` (${limits.join(", ")})` : "") +
        (trigger[temperature.trigger] ?? ""),
      tone: temperature.trigger ? "warn" : undefined,
    },
  ];
  if (temperature.sensor_reason) {
    lines.push({ text: `Temperature sensor: ${temperature.sensor_reason}`, tone: "muted" });
  }
  return lines;
};

const windLines = (hass: HomeAssistant, wind: Details): DetailLine[] => {
  if (!wind) {
    return [];
  }
  if (!isSet(wind.average)) {
    return [unavailable("Wind", wind)];
  }
  const unit = wind.unit ? ` ${wind.unit}` : "";
  const over = isSet(wind.max) && wind.average >= wind.max;
  return [
    {
      text:
        `Wind ${formatNumber(hass, wind.average, 1)}${unit} average over ${wind.minutes ?? 0} min ` +
        `${over ? "≥" : "<"} ${formatNumber(hass, wind.max ?? 0, 1)}${unit}`,
      tone: over ? "warn" : undefined,
    },
  ];
};

const occupancyLines = (hass: HomeAssistant, occupancy: Details): DetailLine[] => {
  if (!occupancy) {
    return [];
  }
  if (occupancy.reason) {
    return [unavailable("Occupancy", occupancy)];
  }
  const occupied: string[] = occupancy.occupied ?? [];
  return occupied.length
    ? [{ text: `Occupied: ${names(hass, occupied)}`, tone: "warn" }]
    : [{ text: "Not occupied", tone: "muted" }];
};

const moistureLines = (hass: HomeAssistant, moisture: Details): DetailLine[] => {
  if (!moisture) {
    return [];
  }
  const lines: DetailLine[] = [];
  if (!isSet(moisture.lowest)) {
    lines.push(unavailable("Soil moisture", moisture));
  } else {
    const dry = isSet(moisture.threshold) && moisture.lowest < moisture.threshold;
    lines.push({
      text:
        `Lowest moisture ${formatNumber(hass, moisture.lowest, 1)}% ` +
        `(${entityName(hass, moisture.lowest_entity)}) ${dry ? "<" : "≥"} ` +
        `${formatNumber(hass, moisture.threshold ?? 0, 1)}%`,
    });
  }
  const missing: string[] = moisture.unavailable_entities ?? [];
  if (missing.length) {
    lines.push({ text: `No reading from ${names(hass, missing)}`, tone: "muted" });
  }
  return lines;
};

/** Readable lines for a details object: what a check measured and why. */
export const detailLinesFor = (hass: HomeAssistant, details: Details): DetailLine[] => {
  const d = details ?? {};
  const lines: DetailLine[] = [];
  if (d.manual) {
    lines.push({ text: "Started manually" });
  }
  lines.push(
    ...rainLines(hass, d.rain),
    ...forecastLines(hass, d.forecast),
    ...temperatureLines(hass, d.temperature),
    ...windLines(hass, d.wind),
    ...occupancyLines(hass, d.occupancy),
    ...moistureLines(hass, d.moisture)
  );
  if (d.occupancy_delay_until) {
    lines.push({
      text: `Waiting for occupancy to clear, up to ${formatDateTime(hass, d.occupancy_delay_until)}`,
      tone: "info",
    });
  }
  if (d.skipped_busy_at) {
    lines.push({
      text: `Skipped a start at ${formatDateTime(hass, d.skipped_busy_at)} because a run was still going`,
      tone: "warn",
    });
  }
  if (d.error) {
    lines.push({ text: String(d.error), tone: "error" });
  }
  return lines;
};

/** Last status details. Unclosed zones are shown in their own banner. */
export const detailLines = (hass: HomeAssistant, schedule: Schedule): DetailLine[] =>
  detailLinesFor(hass, schedule.last_details);

/** "Check now" result: the decision, what would block a scheduled run, then the readings. */
export const evaluationLines = (hass: HomeAssistant, evaluation: Evaluation): DetailLine[] => {
  const { decision } = evaluation;
  const lines: DetailLine[] = [];
  if (decision.water) {
    lines.push({ text: "Conditions allow watering now", tone: "ok" });
  } else if (decision.status) {
    lines.push({ text: `Would skip: ${statusLabel(decision.status)}`, tone: "warn" });
  } else {
    lines.push({ text: "Would not water: not a schedule day and no sensor is dry", tone: "muted" });
  }
  if (decision.retry) {
    lines.push({ text: "Would re-check every 2 min until the maximum delay", tone: "info" });
  }
  if (!evaluation.scheduled) {
    lines.push({ text: "Checked as a moisture check day", tone: "muted" });
  }
  if (evaluation.rain_delay_until) {
    lines.push({
      text: `Rain delay until ${formatDateTime(hass, evaluation.rain_delay_until)}: scheduled runs are skipped`,
      tone: "warn",
    });
  }
  if (evaluation.paused) {
    lines.push({ text: "Paused: scheduled runs do nothing", tone: "warn" });
  }
  if (!evaluation.enabled) {
    lines.push({ text: "Schedule is off", tone: "muted" });
  }
  return [...lines, ...detailLinesFor(hass, decision.details)];
};

export const historyTitle = (hass: HomeAssistant, record: HistoryRecord): string =>
  `${formatDateTime(hass, record.at)} · ${statusLabel(record.status)}${record.manual ? " (manual)" : ""}`;
