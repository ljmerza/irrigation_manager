// Irrigation Manager sidebar panel: live status and controls for every schedule.
// Adding and editing schedules go through Home Assistant's own config/options
// flows; this panel links to them.

import { LitElement, html, nothing, type PropertyValues, type TemplateResult } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { repeat } from "lit/directives/repeat.js";

import {
  conditionLines,
  countdown,
  detailLines,
  entityName,
  evaluationLines,
  formatDateTime,
  formatNumber,
  formatTime,
  frequencySummary,
  historyTitle,
  relativeTime,
  startSummary,
  statusLabel,
  statusTone,
  zoneModeText,
} from "./format";
import { icons, svgIcon } from "./icons";
import { panelStyles } from "./styles";
import type {
  ActiveZone,
  AiTextMessage,
  Evaluation,
  HassConnection,
  HistoryMessage,
  HomeAssistant,
  HistoryRecord,
  Schedule,
  SchedulesMessage,
  ZoneConfig,
} from "./types";

const DOMAIN = "irrigation_manager";
// After a failed subscribe (e.g. the integration is still loading), wait this
// long before retrying on the next hass update.
const RETRY_SUBSCRIBE_MS = 30_000;
const RAIN_DELAY_PRESETS = [24, 48, 72];
const MAX_ZONE_MINUTES = 180;
// The snapshot carries the last 10 records; "Show more" fetches up to this many.
const SNAPSHOT_HISTORY = 10;
const FULL_HISTORY = 100;

type GlobalAction = "pause_all" | "resume_all" | "stop_all";
type AiAction = "generate_report" | "explain_skips";

interface DialogContent {
  title: string;
  text: string;
}

const errorMessage = (err: unknown): string => {
  if (err && typeof err === "object" && "message" in err) {
    return String((err as { message: unknown }).message);
  }
  return String(err);
};

const without = <T>(record: Record<string, T>, key: string): Record<string, T> => {
  const { [key]: _removed, ...rest } = record;
  return rest;
};

// Same as the HA frontend's navigate(): push the URL and tell the app router.
const navigate = (path: string): void => {
  history.pushState(null, "", path);
  window.dispatchEvent(new CustomEvent("location-changed", { detail: { replace: false } }));
};

@customElement("irrigation-manager-panel")
export class IrrigationManagerPanel extends LitElement {
  @property({ attribute: false }) public hass?: HomeAssistant;

  @property({ type: Boolean, reflect: true }) public narrow = false;

  @property({ attribute: false }) public route?: unknown;

  @property({ attribute: false }) public panel?: unknown;

  @state() private _schedules?: Schedule[];

  @state() private _loadError?: string;

  /** Pending per-schedule action name, keyed by entry id. */
  @state() private _pending: Record<string, string> = {};

  @state() private _actionErrors: Record<string, string> = {};

  @state() private _evaluations: Record<string, Evaluation> = {};

  /** Full history fetched by "Show more", keyed by entry id. */
  @state() private _histories: Record<string, HistoryRecord[]> = {};

  @state() private _globalPending?: GlobalAction;

  @state() private _globalError?: string;

  @state() private _dialog?: DialogContent;

  @state() private _now = Date.now();

  private _connection?: HassConnection;

  private _unsubscribe?: Promise<() => Promise<void>>;

  private _subscribeFailedAt = 0;

  private _timer?: number;

  static styles = panelStyles;

  connectedCallback(): void {
    super.connectedCallback();
    this._subscribe();
    this._timer = window.setInterval(() => this._tick(), 1000);
    window.addEventListener("keydown", this._handleKeydown);
  }

  disconnectedCallback(): void {
    super.disconnectedCallback();
    window.clearInterval(this._timer);
    this._timer = undefined;
    window.removeEventListener("keydown", this._handleKeydown);
    this._unsubscribeAll();
  }

  protected shouldUpdate(changed: PropertyValues<this>): boolean {
    // hass is replaced on every state change anywhere in HA. Keep the
    // subscription on its current connection, but only re-render when
    // something this panel shows has changed.
    this._subscribe();
    if (changed.size !== 1 || !changed.has("hass")) {
      return true;
    }
    const previous = changed.get("hass") as HomeAssistant | undefined;
    const hass = this.hass;
    if (!previous || !hass || !this._schedules) {
      return true;
    }
    if (
      previous.locale !== hass.locale ||
      previous.language !== hass.language ||
      previous.config !== hass.config ||
      previous.dockedSidebar !== hass.dockedSidebar
    ) {
      return true;
    }
    return this._watchedEntities().some((id) => previous.states[id] !== hass.states[id]);
  }

  protected render(): TemplateResult {
    const hass = this.hass;
    const showMenu = this.narrow || hass?.dockedSidebar === "always_hidden";
    return html`
      <div class="toolbar">
        ${showMenu
          ? html`<button class="icon-button" aria-label="Show sidebar" @click=${this._toggleMenu}>
              ${svgIcon(icons.menu)}
            </button>`
          : nothing}
        <div class="title">Irrigation</div>
        <button class="toolbar-button" @click=${this._addSchedule}>
          ${svgIcon(icons.plus)}<span>Add schedule</span>
        </button>
      </div>
      <main class="content">
        ${this._loadError
          ? html`<div class="banner error" role="alert">${this._loadError}</div>`
          : nothing}
        ${this._renderGlobal()}
        ${this._renderBody(hass)}
      </main>
      ${this._renderDialog()}
    `;
  }

  private _renderGlobal(): TemplateResult | typeof nothing {
    const schedules = this._schedules ?? [];
    if (!schedules.length) {
      return nothing;
    }
    const paused = schedules.filter((schedule) => schedule.paused).length;
    const running = schedules.some((schedule) => schedule.running);
    const pending = this._globalPending !== undefined;
    return html`
      ${paused
        ? html`<div class="banner warn" role="status">
            ${svgIcon(icons.pause)}${paused === schedules.length
              ? "All schedules are paused. Scheduled runs do nothing until you resume."
              : `${paused} of ${schedules.length} schedules are paused.`}
          </div>`
        : nothing}
      ${this._globalError
        ? html`<div class="banner error" role="alert">${this._globalError}</div>`
        : nothing}
      <div class="global-actions">
        ${paused < schedules.length
          ? html`<button
              class="action"
              ?disabled=${pending}
              @click=${() => this._globalAction("pause_all")}
            >
              ${svgIcon(icons.pause)}Pause all
            </button>`
          : nothing}
        ${paused
          ? html`<button
              class="action"
              ?disabled=${pending}
              @click=${() => this._globalAction("resume_all")}
            >
              ${svgIcon(icons.play)}Resume all
            </button>`
          : nothing}
        ${running
          ? html`<button
              class="action danger"
              ?disabled=${pending}
              @click=${() => this._globalAction("stop_all")}
            >
              ${svgIcon(icons.stop)}Stop all
            </button>`
          : nothing}
      </div>
    `;
  }

  private _renderBody(hass: HomeAssistant | undefined): TemplateResult | typeof nothing {
    if (!hass || this._schedules === undefined) {
      return this._loadError ? nothing : html`<div class="empty">Loading schedules…</div>`;
    }
    if (this._schedules.length === 0) {
      return html`
        <div class="empty">
          <div class="empty-icon">${svgIcon(icons.water)}</div>
          <h2>No schedules yet</h2>
          <p>
            Add a schedule to choose valves or switches, set when they water, and pick
            rain, forecast, temperature, wind, occupancy or soil moisture conditions.
          </p>
          <button class="action filled" @click=${this._addSchedule}>
            ${svgIcon(icons.plus)}Add schedule
          </button>
        </div>
      `;
    }
    return html`
      <div class="grid">
        ${repeat(
          this._schedules,
          (schedule) => schedule.entry_id,
          (schedule) => this._renderSchedule(hass, schedule)
        )}
      </div>
    `;
  }

  private _renderSchedule(hass: HomeAssistant, schedule: Schedule): TemplateResult {
    const config = schedule.config ?? {};
    const id = schedule.entry_id;
    const pendingAction = this._pending[id];
    const pending = pendingAction !== undefined;
    const actionError = this._actionErrors[id];
    const conditions = conditionLines(hass, config);
    const details = detailLines(hass, schedule);
    const unclosed = schedule.unclosed_zones ?? [];
    const evaluation = this._evaluations[id];

    return html`
      <section class="card ${schedule.enabled ? "" : "is-disabled"}">
        <header class="card-header">
          <div class="heading">
            <h2>${schedule.name}</h2>
            <span class="badge ${statusTone(schedule.status)}">${statusLabel(schedule.status)}</span>
            ${schedule.paused && schedule.status !== "paused"
              ? html`<span class="chip warn">paused</span>`
              : nothing}
          </div>
          <label class="switch" title=${schedule.enabled ? "Turn schedule off" : "Turn schedule on"}>
            <input
              type="checkbox"
              role="switch"
              aria-label="Schedule on"
              .checked=${schedule.enabled}
              ?disabled=${pending}
              @change=${(ev: Event) => this._toggleEnabled(schedule, ev)}
            />
            <span class="track"><span class="thumb"></span></span>
          </label>
        </header>

        ${unclosed.length
          ? html`<div class="banner error card-banner" role="alert">
              ${svgIcon(icons.alert)}Could not close
              ${unclosed.map((zone) => entityName(hass, zone)).join(", ")}. Closing is being
              retried — check the valve.
            </div>`
          : nothing}

        ${schedule.running ? this._renderRunning(hass, schedule) : nothing}

        <dl class="rows">
          <dt>Next run</dt>
          <dd>${this._renderNextRun(hass, schedule)}</dd>

          <dt>Rain delay</dt>
          <dd>${this._renderRainDelay(hass, schedule, pending)}</dd>

          <dt>Schedule</dt>
          <dd>
            <div>${frequencySummary(hass, config)}</div>
            <div class="muted">${startSummary(hass, config)}</div>
          </dd>

          <dt>Zones</dt>
          <dd>${this._renderZones(hass, schedule, pending)}</dd>

          <dt>Conditions</dt>
          <dd>
            ${conditions.length
              ? conditions.map((line) => html`<div>${line}</div>`)
              : html`<span class="muted">None</span>`}
          </dd>

          <dt>Last run</dt>
          <dd>${this._renderLastRun(hass, schedule)}</dd>

          ${schedule.last_status_at
            ? html`
                <dt>Last status</dt>
                <dd>
                  <div>
                    ${statusLabel(schedule.status)}
                    <span class="muted">· ${formatDateTime(hass, schedule.last_status_at)}</span>
                  </div>
                  ${details.map(
                    (line) => html`<div class="detail ${line.tone ?? ""}">${line.text}</div>`
                  )}
                </dd>
              `
            : nothing}

          <dt>History</dt>
          <dd>${this._renderHistory(hass, schedule, pending)}</dd>
        </dl>

        ${evaluation ? this._renderEvaluation(hass, schedule, evaluation) : nothing}

        ${actionError
          ? html`<div class="banner error card-banner" role="alert">${actionError}</div>`
          : nothing}

        <footer class="actions">
          ${schedule.running
            ? html`<button
                class="action danger"
                ?disabled=${pending}
                @click=${() => this._action(schedule, "stop")}
              >
                ${svgIcon(icons.stop)}Stop
              </button>`
            : html`<button
                class="action filled"
                ?disabled=${pending}
                @click=${() => this._action(schedule, "run_now")}
              >
                ${svgIcon(icons.play)}Run now
              </button>`}
          <button
            class="action"
            ?disabled=${pending}
            @click=${() => this._action(schedule, "skip_next", { skip: !schedule.skip_next })}
          >
            ${schedule.skip_next
              ? html`${svgIcon(icons.undo)}Cancel skip`
              : html`${svgIcon(icons.skip)}Skip next`}
          </button>
          <button class="action" ?disabled=${pending} @click=${() => this._evaluate(schedule)}>
            ${svgIcon(icons.check)}${pendingAction === "evaluate" ? "Checking…" : "Check now"}
          </button>
          ${config.ai_task_entity
            ? html`
                <button
                  class="action"
                  ?disabled=${pending}
                  @click=${() => this._aiText(schedule, "generate_report")}
                >
                  ${svgIcon(icons.robot)}${pendingAction === "generate_report"
                    ? "Writing report…"
                    : "Weekly report"}
                </button>
                <button
                  class="action"
                  ?disabled=${pending}
                  @click=${() => this._aiText(schedule, "explain_skips")}
                >
                  ${svgIcon(icons.robot)}${pendingAction === "explain_skips"
                    ? "Explaining…"
                    : "Explain skips"}
                </button>
              `
            : nothing}
          <span class="spacer"></span>
          <button class="action" @click=${() => this._editSchedule(schedule)}>
            ${svgIcon(icons.pencil)}Edit
          </button>
        </footer>
      </section>
    `;
  }

  private _renderNextRun(hass: HomeAssistant, schedule: Schedule): TemplateResult {
    if (!schedule.enabled) {
      return html`<span class="muted">Schedule is off</span>`;
    }
    if (!schedule.next_run) {
      return html`<span class="muted">Nothing scheduled</span>`;
    }
    return html`
      ${formatDateTime(hass, schedule.next_run)}
      <span class="muted">(${relativeTime(schedule.next_run, this._now)})</span>
      ${schedule.next_run_scheduled === false
        ? html`<span class="chip" title="Waters only if a moisture sensor reads below the threshold"
            >moisture check</span
          >`
        : nothing}
      ${schedule.skip_next ? html`<span class="chip warn">next watering skipped</span>` : nothing}
      ${schedule.paused ? html`<span class="chip warn">paused</span>` : nothing}
    `;
  }

  private _renderRainDelay(
    hass: HomeAssistant,
    schedule: Schedule,
    pending: boolean
  ): TemplateResult {
    const until = schedule.rain_delay_until;
    return html`
      ${until
        ? html`<div>
            Until ${formatDateTime(hass, until)}
            <span class="muted">(${relativeTime(until, this._now)})</span>
          </div>`
        : html`<div class="muted">None</div>`}
      <div class="inline-actions">
        ${RAIN_DELAY_PRESETS.map(
          (hours) => html`<button
            class="mini"
            title=${`Skip scheduled runs for the next ${hours} hours`}
            ?disabled=${pending}
            @click=${() => this._action(schedule, "set_rain_delay", { hours })}
          >
            ${hours} h
          </button>`
        )}
        ${until
          ? html`<button
              class="mini"
              ?disabled=${pending}
              @click=${() => this._action(schedule, "set_rain_delay", { hours: 0 })}
            >
              Clear
            </button>`
          : nothing}
      </div>
    `;
  }

  private _renderZones(hass: HomeAssistant, schedule: Schedule, pending: boolean): TemplateResult {
    const config = schedule.config ?? {};
    const zones = config.zones ?? [];
    if (!zones.length) {
      return html`<span class="muted">No zones</span>`;
    }
    return html`
      <ul class="zone-list">
        ${zones.map(
          (zone) => html`<li>
            <span>${entityName(hass, zone.entity_id)}</span>
            <span class="zone-controls">
              <span class="muted">${zone.minutes} min</span>
              <button
                class="mini"
                title="Run only this zone"
                ?disabled=${pending || schedule.running}
                @click=${() => this._runZone(hass, schedule, zone)}
              >
                Run
              </button>
            </span>
          </li>`
        )}
      </ul>
      ${zones.length > 1 ? html`<div class="muted">${zoneModeText(config)}</div>` : nothing}
    `;
  }

  private _renderRunning(hass: HomeAssistant, schedule: Schedule): TemplateResult {
    let active: ActiveZone[] = schedule.active_zones ?? [];
    if (!active.length && schedule.current_zone) {
      active = [{ entity_id: schedule.current_zone, ends_at: schedule.current_zone_ends_at }];
    }
    return html`
      <div class="running-block">
        <div class="running-title">${svgIcon(icons.water)}Watering</div>
        ${active.length
          ? active.map(
              (zone) => html`<div class="running-zone">
                <span>${entityName(hass, zone.entity_id)}</span>
                <span class="countdown">
                  ${zone.ends_at ? `${countdown(zone.ends_at, this._now)} left` : "starting…"}
                </span>
              </div>`
            )
          : html`<div class="muted">Starting…</div>`}
      </div>
    `;
  }

  private _renderLastRun(hass: HomeAssistant, schedule: Schedule): TemplateResult {
    if (!schedule.last_run_start) {
      return html`<span class="muted">Never</span>`;
    }
    const total = schedule.last_run_total_minutes;
    const results = schedule.zone_results ?? [];
    return html`
      <div>
        ${formatDateTime(hass, schedule.last_run_start)}${schedule.last_run_end
          ? ` – ${formatTime(hass, schedule.last_run_end)}`
          : ""}
      </div>
      ${total !== null && total !== undefined
        ? html`<div class="muted">${formatNumber(hass, total, 1)} min total</div>`
        : nothing}
      ${results.length
        ? html`<ul class="zone-list">
            ${results.map(
              (result) => html`<li class=${result.error ? "error" : ""}>
                <span>
                  ${entityName(hass, result.entity_id)}
                  ${result.error ? html`<span class="zone-error">${result.error}</span>` : nothing}
                </span>
                <span class=${result.error ? "" : "muted"}>${formatNumber(hass, result.minutes, 1)} min</span>
              </li>`
            )}
          </ul>`
        : nothing}
    `;
  }

  private _renderHistory(hass: HomeAssistant, schedule: Schedule, pending: boolean): TemplateResult {
    const expanded = this._histories[schedule.entry_id];
    const records = expanded ?? schedule.history ?? [];
    if (!records.length) {
      return html`<span class="muted">No runs or skips yet</span>`;
    }
    return html`
      <ul class="history-list">
        ${records.map((record) => {
          const failed = record.status === "error" || (record.zones ?? []).some((zone) => zone.error);
          return html`<li class=${failed ? "error" : ""}>
            <span>${historyTitle(hass, record)}</span>
            <span class=${failed ? "" : "muted"}>
              ${record.type === "run"
                ? `${formatNumber(hass, record.total_minutes ?? 0, 1)} min`
                : "skip"}
            </span>
          </li>`;
        })}
      </ul>
      ${expanded
        ? html`<button
            class="mini"
            @click=${() => (this._histories = without(this._histories, schedule.entry_id))}
          >
            Show less
          </button>`
        : records.length >= SNAPSHOT_HISTORY
          ? html`<button class="mini" ?disabled=${pending} @click=${() => this._loadHistory(schedule)}>
              Show more
            </button>`
          : nothing}
    `;
  }

  private _renderEvaluation(
    hass: HomeAssistant,
    schedule: Schedule,
    evaluation: Evaluation
  ): TemplateResult {
    return html`
      <div class="check-block">
        <div class="check-title">
          <span>Check at ${formatTime(hass, evaluation.at)}</span>
          <button
            class="icon-button small"
            aria-label="Close check result"
            @click=${() => (this._evaluations = without(this._evaluations, schedule.entry_id))}
          >
            ${svgIcon(icons.close)}
          </button>
        </div>
        ${evaluationLines(hass, evaluation).map(
          (line) => html`<div class="detail ${line.tone ?? ""}">${line.text}</div>`
        )}
      </div>
    `;
  }

  private _renderDialog(): TemplateResult | typeof nothing {
    const dialog = this._dialog;
    if (!dialog) {
      return nothing;
    }
    return html`
      <div class="dialog-backdrop" @click=${this._closeDialog}>
        <div
          class="dialog"
          role="dialog"
          aria-modal="true"
          aria-label=${dialog.title}
          @click=${(ev: Event) => ev.stopPropagation()}
        >
          <h2>${dialog.title}</h2>
          <div class="dialog-text">${dialog.text}</div>
          <div class="dialog-actions">
            <button class="action filled" @click=${this._closeDialog}>Close</button>
          </div>
        </div>
      </div>
    `;
  }

  // --- data -------------------------------------------------------------------

  private _subscribe(): void {
    const hass = this.hass;
    if (!hass || !this.isConnected) {
      return;
    }
    if (this._connection === hass.connection) {
      if (this._unsubscribe || Date.now() - this._subscribeFailedAt < RETRY_SUBSCRIBE_MS) {
        return;
      }
    }
    this._unsubscribeAll();

    const connection = hass.connection;
    this._connection = connection;
    connection.addEventListener("ready", this._handleReconnect);
    const unsubscribe = connection.subscribeMessage<SchedulesMessage>(
      (message) => {
        this._schedules = message.schedules;
        this._loadError = undefined;
      },
      { type: `${DOMAIN}/subscribe` }
    );
    this._unsubscribe = unsubscribe;
    unsubscribe.catch((err) => {
      if (this._unsubscribe !== unsubscribe) {
        return;
      }
      this._unsubscribe = undefined;
      this._subscribeFailedAt = Date.now();
      this._loadError = `Could not load schedules: ${errorMessage(err)}`;
    });
  }

  private _unsubscribeAll(): void {
    this._connection?.removeEventListener("ready", this._handleReconnect);
    this._connection = undefined;
    const unsubscribe = this._unsubscribe;
    this._unsubscribe = undefined;
    unsubscribe?.then((unsub) => unsub()).catch(() => undefined);
  }

  private _handleReconnect = (): void => {
    if (!this._unsubscribe) {
      // The first subscribe failed; try again now that the connection is back.
      this._subscribeFailedAt = 0;
      this._subscribe();
      return;
    }
    // The websocket library re-sends subscriptions after a reconnect; refetch as
    // well so the list is current even if that resubscription lags.
    void this._refresh();
  };

  private async _refresh(): Promise<void> {
    if (!this.hass) {
      return;
    }
    try {
      const result = await this.hass.callWS<SchedulesMessage>({ type: `${DOMAIN}/schedules` });
      this._schedules = result.schedules;
      this._loadError = undefined;
    } catch (_err) {
      // Load errors surface through the subscription.
    }
  }

  private _watchedEntities(): string[] {
    const ids = new Set<string>();
    const add = (id: string | null | undefined) => {
      if (id) ids.add(id);
    };
    for (const schedule of this._schedules ?? []) {
      const config = schedule.config ?? {};
      config.zones?.forEach((zone) => add(zone.entity_id));
      config.moisture_sensors?.forEach(add);
      config.rain_sensors?.forEach(add);
      config.weather_entities?.forEach(add);
      config.occupancy_entities?.forEach(add);
      add(config.rain_sensor);
      add(config.weather_entity);
      add(config.temperature_sensor);
      add(config.wind_sensor);
      const details = schedule.last_details ?? {};
      add(details.moisture?.lowest_entity);
      (details.moisture?.unavailable_entities ?? []).forEach(add);
      (details.occupancy?.occupied ?? []).forEach(add);
      Object.keys(details.rain?.stations ?? {}).forEach(add);
      schedule.unclosed_zones?.forEach(add);
      schedule.zone_results?.forEach((result) => add(result.entity_id));
      schedule.active_zones?.forEach((zone) => add(zone.entity_id));
    }
    return [...ids];
  }

  private _tick(): void {
    const now = Date.now();
    // Countdowns need every second; relative "in 3 h" text only every 30 s.
    if (this._schedules?.some((schedule) => schedule.running) || now - this._now >= 30_000) {
      this._now = now;
    }
  }

  // --- actions ----------------------------------------------------------------

  /** Send a per-schedule command; errors are shown on the card. */
  private async _request<T>(
    schedule: Schedule,
    action: string,
    data: Record<string, unknown> = {}
  ): Promise<T | undefined> {
    const hass = this.hass;
    const id = schedule.entry_id;
    if (!hass || this._pending[id] !== undefined) {
      return undefined;
    }
    this._pending = { ...this._pending, [id]: action };
    this._actionErrors = without(this._actionErrors, id);
    try {
      return await hass.callWS<T>({ type: `${DOMAIN}/${action}`, entry_id: id, ...data });
    } catch (err) {
      this._actionErrors = { ...this._actionErrors, [id]: errorMessage(err) };
      return undefined;
    } finally {
      this._pending = without(this._pending, id);
    }
  }

  /** Commands that reply with the updated schedule snapshot. */
  private async _action(
    schedule: Schedule,
    action: string,
    data: Record<string, unknown> = {}
  ): Promise<void> {
    const updated = await this._request<Schedule>(schedule, action, data);
    if (updated && this._schedules) {
      this._schedules = this._schedules.map((item) =>
        item.entry_id === schedule.entry_id ? updated : item
      );
    }
  }

  private async _evaluate(schedule: Schedule): Promise<void> {
    const result = await this._request<Evaluation>(schedule, "evaluate");
    if (result) {
      this._evaluations = { ...this._evaluations, [schedule.entry_id]: result };
    }
  }

  private async _loadHistory(schedule: Schedule): Promise<void> {
    const result = await this._request<HistoryMessage>(schedule, "history", {
      limit: FULL_HISTORY,
    });
    if (result) {
      this._histories = { ...this._histories, [schedule.entry_id]: result.history };
    }
  }

  private async _aiText(schedule: Schedule, action: AiAction): Promise<void> {
    const result = await this._request<AiTextMessage>(schedule, action);
    if (result) {
      this._dialog = {
        title:
          action === "generate_report"
            ? `${schedule.name}: weekly report`
            : `${schedule.name}: skipped runs`,
        text: result.text,
      };
    }
  }

  private _runZone(hass: HomeAssistant, schedule: Schedule, zone: ZoneConfig): void {
    const answer = window.prompt(
      `Run ${entityName(hass, zone.entity_id)} for how many minutes?`,
      String(zone.minutes)
    );
    if (answer === null) {
      return;
    }
    const minutes = Number(answer.trim());
    if (!Number.isInteger(minutes) || minutes < 1 || minutes > MAX_ZONE_MINUTES) {
      this._actionErrors = {
        ...this._actionErrors,
        [schedule.entry_id]: `Enter whole minutes from 1 to ${MAX_ZONE_MINUTES}.`,
      };
      return;
    }
    void this._action(schedule, "run_zone", { zone: zone.entity_id, minutes });
  }

  private async _globalAction(action: GlobalAction): Promise<void> {
    const hass = this.hass;
    if (!hass || this._globalPending !== undefined) {
      return;
    }
    if (action === "stop_all" && !window.confirm("Stop every active run?")) {
      return;
    }
    this._globalPending = action;
    this._globalError = undefined;
    try {
      const result = await hass.callWS<SchedulesMessage>({ type: `${DOMAIN}/${action}` });
      if (result?.schedules) {
        this._schedules = result.schedules;
      }
    } catch (err) {
      this._globalError = errorMessage(err);
    } finally {
      this._globalPending = undefined;
    }
  }

  private _toggleEnabled(schedule: Schedule, ev: Event): void {
    const input = ev.target as HTMLInputElement;
    const enabled = input.checked;
    // Show the backend's state until it confirms; the reply re-renders the switch.
    input.checked = schedule.enabled;
    void this._action(schedule, "set_enabled", { enabled });
  }

  private _closeDialog = (): void => {
    this._dialog = undefined;
  };

  private _handleKeydown = (ev: KeyboardEvent): void => {
    if (ev.key === "Escape" && this._dialog) {
      this._dialog = undefined;
    }
  };

  private _toggleMenu(): void {
    this.dispatchEvent(new CustomEvent("hass-toggle-menu", { bubbles: true, composed: true }));
  }

  private _addSchedule(): void {
    navigate(`/_my_redirect/config_flow_start?domain=${DOMAIN}`);
  }

  private _editSchedule(schedule: Schedule): void {
    navigate(`/config/integrations/integration/${DOMAIN}#config_entry=${schedule.entry_id}`);
  }
}

declare global {
  interface HTMLElementTagNameMap {
    "irrigation-manager-panel": IrrigationManagerPanel;
  }
}
