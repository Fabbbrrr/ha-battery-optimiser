/**
 * Battery Optimiser Card v0.2.0
 * Interactive Lovelace card for the Battery Optimiser HA integration.
 *
 * Tabs:
 *   Schedule  — Timeline, SOC curve, aggressiveness slider, controls
 *   Analytics — Planned vs actual accuracy, learning status, retrain button
 *   Config    — Current configuration summary
 */

const CARD_VERSION = "0.2.0";

const COLORS = {
  export:    "#22c55e",
  charge:    "#3b82f6",
  discharge: "#f97316",
  hold:      "#6b7280",
  soc_line:  "#a855f7",
  soc_actual:"#ec4899",
  grid_line: "#374151",
  bg:        "var(--card-background-color, #1f2937)",
  text:      "var(--primary-text-color, #f9fafb)",
  subtext:   "var(--secondary-text-color, #9ca3af)",
  border:    "var(--divider-color, #374151)",
  tab_active:"#a855f7",
};

const ACTION_LABELS = {
  export:    "Export",
  charge:    "Charge",
  discharge: "Discharge",
  hold:      "Hold",
};

class BatteryOptimizerCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._config = {};
    this._hass = null;
    this._selectedSlot = null;
    this._overrideDialogOpen = false;
    this._activeTab = "schedule";
  }

  static getConfigElement() {
    return document.createElement("battery-optimizer-card-editor");
  }

  static getStubConfig() {
    return {
      entity: "sensor.battery_optimizer_schedule",
      health_entity: "sensor.battery_optimizer_health",
      state_entity: "sensor.battery_optimizer_optimizer_state",
      learning_entity: "sensor.battery_optimizer_learning_status",
      title: "Battery Optimiser",
      show_slots: 24,
    };
  }

  setConfig(config) {
    if (!config.entity) throw new Error("Battery Optimiser Card: 'entity' is required");
    this._config = { title: "Battery Optimiser", show_slots: 24, ...config };
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  // ── Data helpers ──────────────────────────────────────────────────────────

  _getScheduleData() {
    const s = this._hass?.states[this._config.entity];
    if (!s) return null;
    return {
      slots: s.attributes?.slots || [],
      aggressiveness: s.attributes?.aggressiveness ?? 0.5,
      state: s.attributes?.state || s.state,
    };
  }

  _getHealthData() {
    const s = this._hass?.states[this._config.health_entity];
    return s?.attributes || null;
  }

  _getOptimizerState() {
    return this._hass?.states[this._config.state_entity]?.state || "unknown";
  }

  _getLearningData() {
    const s = this._hass?.states[this._config.learning_entity];
    if (!s) return null;
    return { state: s.state, ...s.attributes };
  }

  _getScalar(entitySuffix) {
    // Helper: read a scalar sensor by suffix, e.g. "forecast_confidence"
    const base = this._config.entity?.replace("_schedule", "");
    const id = `${base}_${entitySuffix}`;
    return this._hass?.states[id]?.state ?? null;
  }

  // ── CSS ───────────────────────────────────────────────────────────────────

  _styles(isPaused, optimizerState) {
    return `
      :host { display: block; }
      .card {
        background: ${COLORS.bg};
        border-radius: 12px;
        padding: 16px;
        color: ${COLORS.text};
        font-family: var(--paper-font-body1_-_font-family, sans-serif);
      }
      .header {
        display: flex; align-items: center; justify-content: space-between;
        margin-bottom: 10px; flex-wrap: wrap; gap: 8px;
      }
      .title { font-size: 1.1em; font-weight: 600; }
      .state-badge {
        padding: 2px 8px; border-radius: 999px; font-size: 0.75em; font-weight: 600;
        background: ${isPaused ? "#6b7280" : optimizerState === "error" ? "#ef4444" : optimizerState === "fallback" ? "#f59e0b" : "#22c55e"};
        color: #fff;
      }
      .controls { display: flex; gap: 8px; align-items: center; }
      button {
        padding: 6px 12px; border-radius: 6px; border: none; cursor: pointer;
        font-size: 0.8em; font-weight: 600; transition: opacity 0.15s;
      }
      button:hover { opacity: 0.85; }
      button:disabled { opacity: 0.4; cursor: default; }
      .btn-recalc  { background: #3b82f6; color: #fff; }
      .btn-pause   { background: ${isPaused ? "#22c55e" : "#f59e0b"}; color: #fff; }
      .btn-retrain { background: #8b5cf6; color: #fff; }
      .btn-danger  { background: #ef4444; color: #fff; }

      /* Tabs */
      .tabs {
        display: flex; gap: 2px; margin-bottom: 14px;
        border-bottom: 1px solid ${COLORS.border};
      }
      .tab {
        padding: 6px 14px; font-size: 0.82em; font-weight: 600;
        color: ${COLORS.subtext}; cursor: pointer; border-radius: 6px 6px 0 0;
        border-bottom: 2px solid transparent; transition: color 0.15s, border-color 0.15s;
      }
      .tab.active { color: ${COLORS.tab_active}; border-bottom-color: ${COLORS.tab_active}; }
      .tab-content { display: none; }
      .tab-content.active { display: block; }

      /* Health row */
      .health-row {
        display: flex; gap: 16px; margin-bottom: 12px; font-size: 0.78em;
        color: ${COLORS.subtext}; flex-wrap: wrap;
      }
      .health-item { display: flex; flex-direction: column; }
      .health-value { font-size: 1em; font-weight: 600; color: ${COLORS.text}; }

      /* Timeline */
      .timeline-wrap { overflow-x: auto; margin-bottom: 8px; }
      .timeline { display: flex; gap: 2px; }
      .slot {
        flex: 1; min-width: 20px; border-radius: 4px; cursor: pointer; position: relative;
        transition: filter 0.15s; display: flex; flex-direction: column;
        align-items: center; padding-top: 4px;
      }
      .slot:hover { filter: brightness(1.2); }
      .slot.is-override { outline: 2px solid #fbbf24; outline-offset: -2px; }
      .slot-bar { width: 100%; border-radius: 3px; }
      .slot-time {
        font-size: 0.6em; color: ${COLORS.subtext}; margin-top: 2px;
        white-space: nowrap; overflow: hidden;
      }
      .chart-wrap { margin-bottom: 12px; }
      svg text { font-family: inherit; }

      /* Slider */
      .slider-row {
        display: flex; align-items: center; gap: 10px; margin-bottom: 12px; font-size: 0.82em;
      }
      .slider-label { color: ${COLORS.subtext}; min-width: 90px; }
      input[type=range] { flex: 1; accent-color: #a855f7; height: 4px; }
      .slider-value { min-width: 36px; text-align: right; font-weight: 600; }

      /* Legend */
      .legend {
        display: flex; gap: 12px; flex-wrap: wrap; font-size: 0.75em;
        color: ${COLORS.subtext}; margin-bottom: 8px;
      }
      .legend-item { display: flex; align-items: center; gap: 4px; }
      .legend-dot { width: 10px; height: 10px; border-radius: 2px; }

      /* Override dialog */
      .dialog-overlay {
        position: fixed; inset: 0; background: rgba(0,0,0,0.6);
        display: flex; align-items: center; justify-content: center; z-index: 1000;
      }
      .dialog {
        background: var(--card-background-color, #1f2937); border-radius: 12px;
        padding: 20px; min-width: 280px; max-width: 360px; width: 90%;
        box-shadow: 0 20px 60px rgba(0,0,0,0.5);
      }
      .dialog h3 { margin: 0 0 16px; font-size: 1em; }
      .dialog label { display: block; font-size: 0.82em; color: ${COLORS.subtext}; margin-bottom: 4px; }
      .dialog select, .dialog input {
        width: 100%; padding: 8px; border-radius: 6px; border: 1px solid ${COLORS.border};
        background: rgba(255,255,255,0.05); color: ${COLORS.text}; font-size: 0.9em;
        margin-bottom: 12px; box-sizing: border-box;
      }
      .dialog-buttons { display: flex; gap: 8px; justify-content: flex-end; }
      .btn-cancel { background: rgba(255,255,255,0.1); color: ${COLORS.text}; }
      .btn-apply  { background: #3b82f6; color: #fff; }
      .slot-detail {
        font-size: 0.75em; color: ${COLORS.subtext}; background: rgba(255,255,255,0.05);
        border-radius: 6px; padding: 8px; margin-bottom: 12px;
      }
      .slot-detail .row { display: flex; justify-content: space-between; padding: 2px 0; }
      .slot-detail .val { color: ${COLORS.text}; font-weight: 500; }

      /* Analytics & Config sections */
      .section { margin-bottom: 16px; }
      .section-title {
        font-size: 0.78em; font-weight: 700; color: ${COLORS.subtext};
        text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 8px;
      }
      .kv-grid {
        display: grid; grid-template-columns: 1fr 1fr; gap: 6px 16px; font-size: 0.82em;
      }
      .kv-grid.cols3 { grid-template-columns: 1fr 1fr 1fr; }
      .kv-label { color: ${COLORS.subtext}; }
      .kv-value { font-weight: 600; color: ${COLORS.text}; }
      .accuracy-bar-wrap {
        height: 8px; background: rgba(255,255,255,0.08); border-radius: 4px;
        overflow: hidden; margin-top: 4px;
      }
      .accuracy-bar { height: 100%; border-radius: 4px; transition: width 0.3s; }
      .badge {
        display: inline-block; padding: 2px 8px; border-radius: 999px;
        font-size: 0.72em; font-weight: 700;
      }
      .badge-green  { background: rgba(34,197,94,0.2);  color: #22c55e; }
      .badge-yellow { background: rgba(245,158,11,0.2); color: #f59e0b; }
      .badge-red    { background: rgba(239,68,68,0.2);  color: #ef4444; }
      .badge-grey   { background: rgba(107,114,128,0.2);color: #9ca3af; }
      .alert {
        padding: 8px 12px; border-radius: 6px; font-size: 0.8em;
        margin-bottom: 8px; display: flex; align-items: center; gap: 8px;
      }
      .alert-warn { background: rgba(245,158,11,0.15); border-left: 3px solid #f59e0b; }
      .alert-error { background: rgba(239,68,68,0.15); border-left: 3px solid #ef4444; }
      .alert-ok    { background: rgba(34,197,94,0.12); border-left: 3px solid #22c55e; }
      .divider { height: 1px; background: ${COLORS.border}; margin: 12px 0; }
      .retrain-row {
        display: flex; align-items: center; justify-content: space-between;
        gap: 12px; flex-wrap: wrap;
      }
      .retrain-info { font-size: 0.8em; color: ${COLORS.subtext}; flex: 1; }
    `;
  }

  // ── Main render ───────────────────────────────────────────────────────────

  _render() {
    if (!this._hass) return;

    const data       = this._getScheduleData();
    const health     = this._getHealthData();
    const learning   = this._getLearningData();
    const optState   = this._getOptimizerState();
    const isPaused   = optState === "paused";
    const slots      = (data?.slots || []).slice(0, this._config.show_slots);
    const aggressiveness = data?.aggressiveness ?? 0.5;
    const currency   = this._hass.config?.currency || "";

    this.shadowRoot.innerHTML = `
      <style>${this._styles(isPaused, optState)}</style>
      <div class="card">
        <div class="header">
          <div style="display:flex;align-items:center;gap:8px;">
            <span class="title">${this._config.title}</span>
            <span class="state-badge">${optState}</span>
          </div>
          <div class="controls">
            <button class="btn-recalc" id="btn-recalc">↺ Recalculate</button>
            <button class="btn-pause"  id="btn-pause">${isPaused ? "▶ Resume" : "⏸ Pause"}</button>
          </div>
        </div>

        ${this._renderAlerts(health, learning)}

        <!-- Tabs -->
        <div class="tabs">
          <div class="tab${this._activeTab === "schedule"  ? " active" : ""}" data-tab="schedule">Schedule</div>
          <div class="tab${this._activeTab === "analytics" ? " active" : ""}" data-tab="analytics">Analytics</div>
          <div class="tab${this._activeTab === "config"    ? " active" : ""}" data-tab="config">Config</div>
        </div>

        <!-- Schedule tab -->
        <div class="tab-content${this._activeTab === "schedule" ? " active" : ""}">
          ${this._renderHealth(health, currency)}
          <div class="timeline-wrap">
            <div class="timeline" id="timeline">${this._renderSlots(slots)}</div>
          </div>
          <div class="chart-wrap">${this._renderSOCChart(slots)}</div>
          <div class="legend">
            ${Object.entries(ACTION_LABELS).map(([k, v]) =>
              `<div class="legend-item">
                <div class="legend-dot" style="background:${COLORS[k]}"></div>
                <span>${v}</span>
              </div>`).join("")}
            <div class="legend-item">
              <div class="legend-dot" style="background:${COLORS.soc_line};border-radius:50%"></div>
              <span>Planned SOC</span>
            </div>
            <div class="legend-item">
              <div class="legend-dot" style="background:${COLORS.soc_actual};border-radius:50%"></div>
              <span>Actual SOC</span>
            </div>
          </div>
          <div class="slider-row">
            <span class="slider-label">Aggressiveness</span>
            <input type="range" id="aggr-slider" min="0" max="1" step="0.05" value="${aggressiveness}" />
            <span class="slider-value" id="aggr-val">${Math.round(aggressiveness * 100)}%</span>
          </div>
        </div>

        <!-- Analytics tab -->
        <div class="tab-content${this._activeTab === "analytics" ? " active" : ""}">
          ${this._renderAnalyticsTab(slots, learning, health)}
        </div>

        <!-- Config tab -->
        <div class="tab-content${this._activeTab === "config" ? " active" : ""}">
          ${this._renderConfigTab(health, learning, aggressiveness, currency)}
        </div>

        ${this._overrideDialogOpen && this._selectedSlot ? this._renderOverrideDialog() : ""}
      </div>
    `;

    this._attachListeners(slots, aggressiveness);
  }

  // ── Alerts (shown on all tabs) ────────────────────────────────────────────

  _renderAlerts(health, learning) {
    const alerts = [];
    if (!health) return "";

    if (health.fallback_mode_active) {
      const err = health.solver_status || "unknown error";
      alerts.push(`<div class="alert alert-error">⚠ Fallback mode active — ${err}</div>`);
    }
    if (health.soc_sensor_available === false) {
      alerts.push(`<div class="alert alert-warn">⚡ SOC sensor unavailable — optimizer using estimated 50% SOC</div>`);
    }
    if (learning && !learning.is_trained && learning.state !== "unavailable") {
      alerts.push(`<div class="alert alert-warn">📚 Consumption learning not yet trained — using baseline. Press Retrain in Analytics tab.</div>`);
    }
    return alerts.join("");
  }

  // ── Schedule tab ──────────────────────────────────────────────────────────

  _renderHealth(health, currency) {
    if (!health) return "";
    const rev      = health.estimated_export_revenue;
    const security = health.energy_security_score;
    const conf     = health.forecast_confidence;
    const solveMs  = health.solver_duration_ms;

    return `<div class="health-row">
      ${rev !== undefined ? `<div class="health-item">
        <span>Est. Revenue</span>
        <span class="health-value">${currency}${Number(rev).toFixed(2)}</span>
      </div>` : ""}
      ${security !== undefined ? `<div class="health-item">
        <span>Security</span>
        <span class="health-value" style="color:${security >= 0.8 ? "#22c55e" : security >= 0.5 ? "#f59e0b" : "#ef4444"}">
          ${Math.round(security * 100)}%
        </span>
      </div>` : ""}
      ${conf !== undefined ? `<div class="health-item">
        <span>Solar Confidence</span>
        <span class="health-value">${Math.round(conf * 100)}%</span>
      </div>` : ""}
      ${health.bridge_to_time ? `<div class="health-item">
        <span>Bridge to</span>
        <span class="health-value">${this._formatTime(health.bridge_to_time)}
          <small style="font-weight:400;font-size:0.8em">(${(health.bridge_to_source || "").replace("_", " ")})</small>
        </span>
      </div>` : ""}
      ${health.last_recalculation ? `<div class="health-item">
        <span>Last calc</span>
        <span class="health-value">${this._formatRelativeTime(health.last_recalculation)}</span>
      </div>` : ""}
      ${solveMs ? `<div class="health-item">
        <span>Solve time</span>
        <span class="health-value">${Math.round(solveMs)}ms</span>
      </div>` : ""}
    </div>`;
  }

  _renderSlots(slots) {
    if (!slots.length) return `<div style="color:${COLORS.subtext};font-size:0.85em;padding:16px;">No schedule data — check entity and configuration.</div>`;
    const maxBarH = 48, maxPow = 5;
    return slots.map((slot, i) => {
      const color  = COLORS[slot.action] || COLORS.hold;
      const barH   = Math.max(8, Math.round((Math.abs(slot.power_kw || 0) / maxPow) * maxBarH));
      const time   = this._formatTime(slot.start);
      return `
        <div class="slot${slot.is_override ? " is-override" : ""}"
             data-index="${i}"
             style="opacity:${slot.is_historical ? 0.5 : 1}"
             title="${ACTION_LABELS[slot.action] || slot.action} ${Math.abs(slot.power_kw || 0).toFixed(1)}kW @ ${time}">
          <div class="slot-bar" style="height:${barH}px;background:${color}"></div>
          ${i % 4 === 0 ? `<div class="slot-time">${time}</div>` : ""}
        </div>`;
    }).join("");
  }

  _renderSOCChart(slots) {
    if (!slots.length) return "";
    const W = 560, H = 80, padL = 32, padR = 8, padT = 8, padB = 20;
    const chartW = W - padL - padR, chartH = H - padT - padB;
    const toX = i => padL + (i / (slots.length - 1 || 1)) * chartW;
    const toY = v => padT + chartH - (v / 100) * chartH;

    const gridLines = [20, 50, 80].map(pct => {
      const y = toY(pct);
      return `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}"
                stroke="${COLORS.grid_line}" stroke-width="0.5" stroke-dasharray="3,3"/>
              <text x="${padL - 2}" y="${y + 3}" text-anchor="end"
                fill="${COLORS.subtext}" font-size="8">${pct}%</text>`;
    }).join("");

    const socPts = slots.map((s, i) => s.projected_soc != null ? `${toX(i)},${toY(s.projected_soc)}` : null).filter(Boolean);
    const actPts = slots.map((s, i) => s.actual_soc != null ? `${toX(i)},${toY(s.actual_soc)}` : null).filter(Boolean);

    const timeLabels = slots
      .filter((_, i) => i % Math.max(1, Math.floor(slots.length / 6)) === 0)
      .map(s => {
        const i = slots.indexOf(s);
        return `<text x="${toX(i)}" y="${H - 2}" text-anchor="middle" fill="${COLORS.subtext}" font-size="7">${this._formatTime(s.start)}</text>`;
      }).join("");

    return `<svg viewBox="0 0 ${W} ${H}" style="width:100%;height:auto;display:block;">
      ${gridLines}
      ${socPts.length > 1 ? `<polyline points="${socPts.join(" ")}" fill="none" stroke="${COLORS.soc_line}" stroke-width="2" stroke-linejoin="round"/>` : ""}
      ${actPts.length > 1 ? `<polyline points="${actPts.join(" ")}" fill="none" stroke="${COLORS.soc_actual}" stroke-width="1.5" stroke-dasharray="4,2" stroke-linejoin="round"/>` : ""}
      ${timeLabels}
    </svg>`;
  }

  // ── Analytics tab ─────────────────────────────────────────────────────────

  _renderAnalyticsTab(slots, learning, health) {
    const histSlots = slots.filter(s => s.is_historical && s.actual_soc != null && s.projected_soc != null);

    // SOC accuracy: avg |actual - planned|
    let avgError = null, maxError = null, accuracyPct = null;
    if (histSlots.length) {
      const errors = histSlots.map(s => Math.abs((s.actual_soc || 0) - (s.projected_soc || 0)));
      avgError = errors.reduce((a, b) => a + b, 0) / errors.length;
      maxError = Math.max(...errors);
      accuracyPct = Math.max(0, 100 - avgError);
    }

    // Mini sparkline of planned vs actual SOC for historical slots
    const sparkHTML = this._renderAccuracySparkline(histSlots);

    // Learning status
    const learnHTML = this._renderLearningSection(learning);

    // Solver health
    const solverOk = health && !health.fallback_mode_active && health.solver_status === "ok";

    return `
      <div class="section">
        <div class="section-title">Forecast Accuracy — Planned vs Actual SOC</div>
        ${histSlots.length === 0
          ? `<div style="color:${COLORS.subtext};font-size:0.82em">No historical data yet — accuracy tracking starts after the first completed slot.</div>`
          : `<div class="kv-grid" style="margin-bottom:10px;">
              <div>
                <div class="kv-label">Avg SOC error</div>
                <div class="kv-value">${avgError != null ? avgError.toFixed(1) + "%" : "—"}</div>
              </div>
              <div>
                <div class="kv-label">Max SOC error</div>
                <div class="kv-value">${maxError != null ? maxError.toFixed(1) + "%" : "—"}</div>
              </div>
              <div>
                <div class="kv-label">Accuracy score</div>
                <div class="kv-value" style="color:${accuracyPct >= 90 ? "#22c55e" : accuracyPct >= 75 ? "#f59e0b" : "#ef4444"}">
                  ${accuracyPct != null ? accuracyPct.toFixed(0) + "%" : "—"}
                </div>
              </div>
              <div>
                <div class="kv-label">Slots tracked</div>
                <div class="kv-value">${histSlots.length}</div>
              </div>
            </div>
            ${accuracyPct != null ? `
              <div class="kv-label" style="margin-bottom:4px">Forecast accuracy</div>
              <div class="accuracy-bar-wrap">
                <div class="accuracy-bar" style="width:${accuracyPct}%;background:${accuracyPct >= 90 ? "#22c55e" : accuracyPct >= 75 ? "#f59e0b" : "#ef4444"}"></div>
              </div>` : ""}
            ${sparkHTML}`
        }
      </div>

      <div class="divider"></div>

      <div class="section">
        <div class="section-title">Solver Health</div>
        <div class="kv-grid">
          <div>
            <div class="kv-label">Status</div>
            <div class="kv-value">
              <span class="badge ${solverOk ? "badge-green" : "badge-red"}">
                ${health?.solver_status || "unknown"}
              </span>
            </div>
          </div>
          <div>
            <div class="kv-label">Solve time</div>
            <div class="kv-value">${health?.solver_duration_ms != null ? Math.round(health.solver_duration_ms) + " ms" : "—"}</div>
          </div>
          <div>
            <div class="kv-label">Problem size</div>
            <div class="kv-value">${health?.problem_size != null ? health.problem_size + " vars" : "—"}</div>
          </div>
          <div>
            <div class="kv-label">Fallback active</div>
            <div class="kv-value">
              <span class="badge ${health?.fallback_mode_active ? "badge-red" : "badge-green"}">
                ${health?.fallback_mode_active ? "yes" : "no"}
              </span>
            </div>
          </div>
        </div>
      </div>

      <div class="divider"></div>

      ${learnHTML}
    `;
  }

  _renderAccuracySparkline(histSlots) {
    if (histSlots.length < 2) return "";
    const W = 560, H = 50, padL = 32, padR = 8, padT = 4, padB = 16;
    const chartW = W - padL - padR, chartH = H - padT - padB;
    const toX = i => padL + (i / (histSlots.length - 1)) * chartW;
    const toY = v => padT + chartH - (v / 100) * chartH;

    const planPts = histSlots.map((s, i) => `${toX(i)},${toY(s.projected_soc)}`).join(" ");
    const actPts  = histSlots.map((s, i) => `${toX(i)},${toY(s.actual_soc)}`).join(" ");
    const timeLabels = histSlots
      .filter((_, i) => i === 0 || i === histSlots.length - 1 || i % Math.max(1, Math.floor(histSlots.length / 4)) === 0)
      .map(s => {
        const i = histSlots.indexOf(s);
        return `<text x="${toX(i)}" y="${H - 1}" text-anchor="middle" fill="${COLORS.subtext}" font-size="7">${this._formatTime(s.start)}</text>`;
      }).join("");

    return `
      <div style="margin-top:10px;">
        <div class="kv-label" style="margin-bottom:4px">Recent planned (purple) vs actual (pink) SOC</div>
        <svg viewBox="0 0 ${W} ${H}" style="width:100%;height:auto;display:block;">
          <polyline points="${planPts}" fill="none" stroke="${COLORS.soc_line}" stroke-width="1.5" stroke-linejoin="round"/>
          <polyline points="${actPts}"  fill="none" stroke="${COLORS.soc_actual}" stroke-width="1.5" stroke-dasharray="3,2" stroke-linejoin="round"/>
          ${timeLabels}
        </svg>
      </div>`;
  }

  _renderLearningSection(learning) {
    const trained = learning?.is_trained;
    const count   = learning?.observation_count ?? 0;
    const days    = learning?.days_covered ?? 0;
    const profiles = (learning?.profile_types || []).join(", ") || "none";
    const hasTemp  = learning?.has_temperature_model;
    const lastTrain = learning?.last_trained ? this._formatRelativeTime(learning.last_trained) : "never";

    const statusBadge = trained
      ? `<span class="badge badge-green">trained</span>`
      : count > 0
        ? `<span class="badge badge-yellow">learning</span>`
        : `<span class="badge badge-grey">not started</span>`;

    return `
      <div class="section">
        <div class="section-title">Consumption Learning</div>
        <div class="kv-grid" style="margin-bottom:12px;">
          <div>
            <div class="kv-label">Status</div>
            <div class="kv-value">${statusBadge}</div>
          </div>
          <div>
            <div class="kv-label">Observations</div>
            <div class="kv-value">${count.toLocaleString()}</div>
          </div>
          <div>
            <div class="kv-label">Days covered</div>
            <div class="kv-value">${days > 0 ? days.toFixed(1) + " days" : "—"}</div>
          </div>
          <div>
            <div class="kv-label">Profiles learned</div>
            <div class="kv-value">${profiles}</div>
          </div>
          <div>
            <div class="kv-label">Temperature model</div>
            <div class="kv-value">
              <span class="badge ${hasTemp ? "badge-green" : "badge-grey"}">${hasTemp ? "active" : "not yet"}</span>
            </div>
          </div>
          <div>
            <div class="kv-label">Last trained</div>
            <div class="kv-value">${lastTrain}</div>
          </div>
        </div>
        <div class="retrain-row">
          <div class="retrain-info">
            Re-train pulls the full recorder history and rebuilds the consumption model.
            Do this after adding a consumption sensor or after a long data gap.
          </div>
          <button class="btn-retrain" id="btn-retrain">🧠 Retrain Now</button>
        </div>
      </div>`;
  }

  // ── Config tab ────────────────────────────────────────────────────────────

  _renderConfigTab(health, learning, aggressiveness, currency) {
    // Read config values surfaced through the learning status sensor attributes
    const baseline = learning?.baseline_kw != null ? learning.baseline_kw + " kW" : "—";
    const granularity = learning?.granularity || "—";
    const lookback = learning?.lookback_days != null ? learning.lookback_days + " days" : "—";

    // Bridge info from health
    const bridgeTime   = health?.bridge_to_time   ? this._formatTime(health.bridge_to_time)   : "—";
    const bridgeSrc    = health?.bridge_to_source  ? (health.bridge_to_source.replace(/_/g, " ")) : "—";
    const lastCalc     = health?.last_recalculation ? this._formatRelativeTime(health.last_recalculation) : "—";
    const solverStatus = health?.solver_status || "—";

    // Read individual scalar sensors for richer config display
    const forecConf  = this._getScalar("forecast_confidence");
    const secScore   = this._getScalar("energy_security_score");
    const socAtCharge = this._getScalar("soc_at_free_charge_start");
    const nextAction  = this._getScalar("next_action");

    return `
      <div class="section">
        <div class="section-title">Optimizer</div>
        <div class="kv-grid cols3">
          <div><div class="kv-label">Aggressiveness</div><div class="kv-value">${Math.round(aggressiveness * 100)}%</div></div>
          <div><div class="kv-label">Solver</div><div class="kv-value">${solverStatus}</div></div>
          <div><div class="kv-label">Last calc</div><div class="kv-value">${lastCalc}</div></div>
          <div><div class="kv-label">Bridge to</div><div class="kv-value">${bridgeTime}</div></div>
          <div><div class="kv-label">Bridge source</div><div class="kv-value">${bridgeSrc}</div></div>
          <div><div class="kv-label">Next action</div><div class="kv-value">${nextAction ?? "—"}</div></div>
        </div>
      </div>

      <div class="divider"></div>

      <div class="section">
        <div class="section-title">Key Readings</div>
        <div class="kv-grid cols3">
          <div>
            <div class="kv-label">Solar confidence</div>
            <div class="kv-value">${forecConf != null ? (parseFloat(forecConf)).toFixed(0) + "%" : "—"}</div>
          </div>
          <div>
            <div class="kv-label">Energy security</div>
            <div class="kv-value" style="color:${secScore != null && parseFloat(secScore) >= 80 ? "#22c55e" : "#f59e0b"}">
              ${secScore != null ? parseFloat(secScore).toFixed(0) + "%" : "—"}
            </div>
          </div>
          <div>
            <div class="kv-label">SOC @ charge start</div>
            <div class="kv-value">${socAtCharge != null ? parseFloat(socAtCharge).toFixed(1) + "%" : "—"}</div>
          </div>
        </div>
      </div>

      <div class="divider"></div>

      <div class="section">
        <div class="section-title">Consumption Learning Config</div>
        <div class="kv-grid cols3">
          <div><div class="kv-label">Baseline power</div><div class="kv-value">${baseline}</div></div>
          <div><div class="kv-label">Profile type</div><div class="kv-value">${granularity.replace(/_/g, " ")}</div></div>
          <div><div class="kv-label">Lookback window</div><div class="kv-value">${lookback}</div></div>
        </div>
      </div>

      <div class="divider"></div>

      <div style="font-size:0.75em;color:${COLORS.subtext};margin-top:4px;">
        To change battery capacity, tariff rates, SOC limits, or entity mappings — go to
        <strong>Settings → Devices &amp; Services → Battery Optimiser → Configure</strong>.
      </div>
    `;
  }

  // ── Override dialog ───────────────────────────────────────────────────────

  _renderOverrideDialog() {
    const slot = this._selectedSlot;
    const time = this._formatTime(slot.start);
    return `
      <div class="dialog-overlay" id="override-overlay">
        <div class="dialog">
          <h3>Override Slot — ${time}</h3>
          <div class="slot-detail">
            <div class="row"><span>Current action</span><span class="val">${ACTION_LABELS[slot.action] || slot.action}</span></div>
            <div class="row"><span>Power</span><span class="val">${(slot.power_kw || 0).toFixed(2)} kW</span></div>
            <div class="row"><span>Projected SOC</span><span class="val">${(slot.projected_soc || 0).toFixed(1)}%</span></div>
            <div class="row"><span>Solar</span><span class="val">${((slot.expected_solar_kwh || 0) * 1000).toFixed(0)} Wh</span></div>
            <div class="row"><span>Consumption</span><span class="val">${((slot.expected_consumption_kwh || 0) * 1000).toFixed(0)} Wh</span></div>
          </div>
          <label>Override action</label>
          <select id="override-action">
            ${Object.entries(ACTION_LABELS).map(([k, v]) =>
              `<option value="${k}" ${k === slot.action ? "selected" : ""}>${v}</option>`
            ).join("")}
          </select>
          <label>Power override (kW, optional)</label>
          <input type="number" id="override-power" min="0" max="50" step="0.1"
            placeholder="Leave blank to use optimizer value"
            value="${slot.power_kw ? Math.abs(slot.power_kw).toFixed(1) : ""}" />
          <label>Duration (minutes)</label>
          <input type="number" id="override-duration" min="5" max="480" step="5" value="60" />
          <div class="dialog-buttons">
            <button class="btn-cancel" id="override-cancel">Cancel</button>
            <button class="btn-apply"  id="override-apply">Apply Override</button>
          </div>
        </div>
      </div>`;
  }

  // ── Event listeners ───────────────────────────────────────────────────────

  _attachListeners(slots, aggressiveness) {
    // Tab switching
    this.shadowRoot.querySelectorAll(".tab").forEach(el => {
      el.addEventListener("click", () => {
        this._activeTab = el.dataset.tab;
        this._render();
      });
    });

    // Recalculate
    this.shadowRoot.getElementById("btn-recalc")?.addEventListener("click", () => {
      this._callService("battery_optimizer", "recalculate_now", {});
    });

    // Pause / Resume
    this.shadowRoot.getElementById("btn-pause")?.addEventListener("click", () => {
      const service = this._getOptimizerState() === "paused" ? "resume" : "pause";
      this._callService("battery_optimizer", service, {});
    });

    // Retrain
    this.shadowRoot.getElementById("btn-retrain")?.addEventListener("click", async (e) => {
      const btn = e.target;
      btn.disabled = true;
      btn.textContent = "⏳ Training…";
      this._callService("battery_optimizer", "retrain_learner", {});
      setTimeout(() => { btn.disabled = false; btn.textContent = "🧠 Retrain Now"; }, 8000);
    });

    // Slot taps → override dialog
    this.shadowRoot.querySelectorAll(".slot").forEach(el => {
      el.addEventListener("click", () => {
        const idx = parseInt(el.dataset.index);
        this._selectedSlot = slots[idx];
        this._overrideDialogOpen = true;
        this._render();
      });
    });

    // Aggressiveness slider
    const slider = this.shadowRoot.getElementById("aggr-slider");
    const valDisplay = this.shadowRoot.getElementById("aggr-val");
    if (slider) {
      slider.addEventListener("input", () => {
        valDisplay.textContent = `${Math.round(slider.value * 100)}%`;
      });
      slider.addEventListener("change", () => {
        this._callService("battery_optimizer", "set_aggressiveness", {
          aggressiveness: parseFloat(slider.value),
        });
      });
    }

    // Override dialog
    if (this._overrideDialogOpen) {
      this.shadowRoot.getElementById("override-cancel")?.addEventListener("click", () => {
        this._overrideDialogOpen = false; this._selectedSlot = null; this._render();
      });
      this.shadowRoot.getElementById("override-overlay")?.addEventListener("click", e => {
        if (e.target.id === "override-overlay") {
          this._overrideDialogOpen = false; this._selectedSlot = null; this._render();
        }
      });
      this.shadowRoot.getElementById("override-apply")?.addEventListener("click", () => {
        const action   = this.shadowRoot.getElementById("override-action").value;
        const powerVal = this.shadowRoot.getElementById("override-power").value;
        const duration = parseInt(this.shadowRoot.getElementById("override-duration").value) || 60;
        const data     = { action, duration_minutes: duration, start: this._selectedSlot?.start };
        if (powerVal !== "") data.power_kw = parseFloat(powerVal);
        this._callService("battery_optimizer", "override_slot", data);
        this._overrideDialogOpen = false; this._selectedSlot = null; this._render();
      });
    }
  }

  // ── Utilities ─────────────────────────────────────────────────────────────

  _callService(domain, service, data) {
    this._hass?.callService(domain, service, data);
  }

  _formatTime(isoStr) {
    if (!isoStr) return "";
    try {
      return new Date(isoStr).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    } catch { return isoStr.slice(11, 16) || ""; }
  }

  _formatRelativeTime(isoStr) {
    if (!isoStr) return "";
    try {
      const diff = Math.round((Date.now() - new Date(isoStr)) / 1000);
      if (diff < 60) return `${diff}s ago`;
      if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
      return `${Math.round(diff / 3600)}h ago`;
    } catch { return ""; }
  }

  getCardSize() { return 6; }
}

customElements.define("battery-optimizer-card", BatteryOptimizerCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: "battery-optimizer-card",
  name: "Battery Optimiser",
  description: "Schedule timeline, SOC curve, analytics, and configuration for the Battery Optimiser integration",
  preview: false,
  documentationURL: "https://github.com/Fabbbrrr/ha-battery-optimiser",
});

console.info(
  `%c BATTERY-OPTIMIZER-CARD %c v${CARD_VERSION} `,
  "color:#fff;background:#a855f7;padding:2px 4px;border-radius:3px 0 0 3px;font-weight:bold",
  "color:#a855f7;background:#1f2937;padding:2px 4px;border-radius:0 3px 3px 0",
);
