// Shapes shared with the backend. Schedule mirrors ScheduleRunner.snapshot().

export interface HassEntity {
  entity_id: string;
  state: string;
  attributes: Record<string, any>;
}

export interface HassConnection {
  subscribeMessage<T>(
    callback: (message: T) => void,
    subscribeMessage: Record<string, unknown>
  ): Promise<() => Promise<void>>;
  addEventListener(event: string, listener: (...args: any[]) => void): void;
  removeEventListener(event: string, listener: (...args: any[]) => void): void;
}

export interface HassLocale {
  language: string;
  time_format?: string; // "language" | "system" | "12" | "24"
  time_zone?: string; // "local" | "server"
}

export interface HomeAssistant {
  connection: HassConnection;
  states: Record<string, HassEntity>;
  callWS<T>(message: Record<string, unknown>): Promise<T>;
  language: string;
  locale?: HassLocale;
  config: { time_zone: string };
  dockedSidebar?: string;
}

export interface ZoneConfig {
  entity_id: string;
  minutes: number;
}

export interface ScheduleConfig {
  name?: string;
  zones?: ZoneConfig[];
  zone_mode?: "sequential" | "concurrent";
  frequency?: "interval" | "weekdays" | "hourly";
  interval_days?: number;
  anchor?: string;
  weekdays?: number[];
  interval_hours?: number;
  window_start?: string;
  window_end?: string;
  start_mode?: "time" | "sunrise" | "sunset";
  start_time?: string;
  sun_offset_minutes?: number;
  skip_conditions?: string[];
  stale_hours?: number;
  // Rain (v0.1 single sensor, v0.2 list)
  rain_sensor?: string;
  rain_sensors?: string[];
  rain_threshold?: number;
  rain_hours?: number;
  rain_aggregate?: "max" | "median" | "quorum";
  rain_quorum?: number;
  rain_window?: "hours" | "since_last_watering";
  rain_max_hours?: number;
  rain_stop_during_run?: boolean;
  rain_stop_amount?: number;
  rain_delay_auto_hours?: number;
  // Forecast (v0.1 single entity, v0.2 list)
  weather_entity?: string;
  weather_entities?: string[];
  forecast_probability?: number;
  forecast_hours?: number;
  forecast_mode?: "probability" | "amount" | "either" | "both";
  forecast_amount?: number;
  forecast_quorum?: number;
  // Temperature and wind
  temperature_sensor?: string;
  temperature_min?: number;
  temperature_max?: number;
  temperature_forecast_hours?: number;
  wind_sensor?: string;
  wind_max?: number;
  wind_minutes?: number;
  // Occupancy
  occupancy_entities?: string[];
  occupancy_action?: "delay" | "skip";
  occupancy_max_delay_minutes?: number;
  occupancy_stop_during_run?: boolean;
  // Moisture
  moisture_sensors?: string[];
  moisture_threshold?: number;
  moisture_mode?: "skip" | "trigger";
  moisture_unavailable?: "water" | "skip";
  // AI
  ai_task_entity?: string;
  ai_notify_service?: string;
  ai_report_weekday?: number;
  ai_report_time?: string;
  ai_camera_entity?: string;
}

export interface ZoneResult {
  entity_id: string;
  minutes: number;
  error: string | null;
}

export interface ActiveZone {
  entity_id: string;
  ends_at: string | null;
}

export interface HistoryRecord {
  at: string;
  type: "run" | "skip";
  status: string;
  manual?: boolean;
  started?: string | null;
  zones?: ZoneResult[];
  total_minutes?: number;
  details?: Record<string, any>;
}

export interface Schedule {
  entry_id: string;
  name: string;
  enabled: boolean;
  paused?: boolean;
  status: string;
  running: boolean;
  skip_next: boolean;
  next_run: string | null;
  next_run_scheduled: boolean | null;
  rain_delay_until?: string | null;
  current_zone: string | null;
  current_zone_ends_at: string | null;
  active_zones?: ActiveZone[];
  unclosed_zones?: string[];
  last_run_start: string | null;
  last_run_end: string | null;
  last_run_total_minutes: number | null;
  last_watering_end?: string | null;
  last_status_at: string | null;
  last_details: Record<string, any>;
  zone_results: ZoneResult[];
  history?: HistoryRecord[];
  config: ScheduleConfig;
}

export interface SchedulesMessage {
  schedules: Schedule[];
}

export interface Evaluation {
  at: string;
  scheduled: boolean;
  rain_delay_until: string | null;
  paused: boolean;
  enabled: boolean;
  decision: {
    water: boolean;
    status: string | null;
    details: Record<string, any>;
    retry: boolean;
  };
}

export interface HistoryMessage {
  history: HistoryRecord[];
}

export interface AiTextMessage {
  text: string;
}
