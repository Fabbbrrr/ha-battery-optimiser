/**
 * Battery Optimiser Card v0.1.0
 * Interactive Lovelace card for the Battery Optimiser HA integration.
 *
 * Features:
 *   - Timeline with color-coded slots (charge/discharge/hold/export)
 *   - Projected SOC curve + planned-vs-actual overlay
 *   - Tap slot → override_slot dialog
 *   - Aggressiveness slider
 *   - Recalculate Now button
 *   - Pause / Resume toggle
 */

const CARD_VERSION = "0.1.0";

const COLORS = {
  export:    "#22c55e",   // green
  charge:    "#3b82f6",   // blue
  discharge: "#f97316",   // orange
  hold:      "#6b7280",   // grey
  soc_line:  "#a855f7",   // purple
  soc_actual:"#ec4899",   // pink
  grid_line: "#374151",
  bg:        "var(--card-background-color, #1f2937)",
  text:      "var(--primary-text-color, #f9fafb)",
  subtext:   "var(--secondary-text-color, #9ca3af)",
  border:    "var(--divider-color, #374151)",
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
  }

  static getConfigElement() {
    return document.createElement("battery-optimizer-card-editor");
  }

  static getStubConfig() {
    return {
      entity: "sensor.battery_optimizer_schedule",
      health_entity: "sensor.battery_optimizer_health",
      state_entity: "sensor.battery_optimizer_optimizer_state",
      title: "Battery Optimiser",
      show_slots: 24,
    };
  }

  setConfig(config) {
    if (!config.entity) {
      throw new Error("Battery Optimiser Card: 'entity' is required");
    }
    this._config = {
      title: "Battery Optimiser",
      show_slots: 24,
      ...config,
    };
  }

  set hass(hass) {
    this._hass = hass;
    this._render();
  }

  _getScheduleData() {
    const state = this._hass?.states[this._config.entity];
    if (!state) return null;
    return {
      slots: state.attributes?.slots || [],
      aggressiveness: state.attributes?.aggressiveness ?? 0.7,
      state: state.attributes?.state || state.state,
    };
  }

  _getHealthData() {
    const entity = this._config.health_entity;
    if (!entity) return null;
    const state = this._hass?.states[entity];
    if (!state) return null;
    return state.attributes || {};
  }

  _getOptimizerState() {
    const entity = this._config.state_entity;
    if (!entity) return "unknown";
    return this._hass?.states[entity]?.state || "unknown";
  }

  _render() {
    if (!this._hass) return;

    const data = this._getScheduleData();
    const health = this._getHealthData();
    const optimizerState = this._getOptimizerState();
    const isPaused = optimizerState === "paused";

    const slots = (data?.slots || []).slice(0, this._config.show_slots);
    const aggressiveness = data?.aggressiveness ?? 0.7;
    const currency = this._hass.config?.currency || "$";

    this.shadowRoot.innerHTML = `
      <style>
        :host { display: block; }
        .card {
          background: ${COLORS.bg};
          border-radius: 12px;
          padding: 16px;
          color: ${COLORS.text};
          font-family: var(--paper-font-body1_-_font-family, sans-serif);
        }
        .header {
          display: flex;
          align-items: center;
          justify-content: space-between;
          margin-bottom: 12px;
          flex-wrap: wrap;
          gap: 8px;
        }
        .title { font-size: 1.1em; font-weight: 600; }
        .state-badge {
          padding: 2px 8px;
          border-radius: 999px;
          font-size: 0.75em;
          font-weight: 600;
          background: ${isPaused ? "#6b7280" : optimizerState === "error" ? "#ef4444" : "#22c55e"};
          color: #fff;
        }
        .controls {
          display: flex;
          gap: 8px;
          align-items: center;
        }
        button {
          padding: 6px 12px;
          border-radius: 6px;
          border: none;
          cursor: pointer;
          font-size: 0.8em;
          font-weight: 600;
          transition: opacity 0.15s;
        }
        button:hover { opacity: 0.85; }
        .btn-recalc { background: #3b82f6; color: #fff; }
        .btn-pause  { background: ${isPaused ? "#22c55e" : "#f59e0b"}; color: #fff; }

        /* Health bar */
        .health-row {
          display: flex;
          gap: 16px;
          margin-bottom: 12px;
          font-size: 0.78em;
          color: ${COLORS.subtext};
          flex-wrap: wrap;
        }
        .health-item { display: flex; flex-direction: column; }
        .health-value { font-size: 1em; font-weight: 600; color: ${COLORS.text}; }

        /* Timeline */
        .timeline-wrap { overflow-x: auto; margin-bottom: 8px; }
        .timeline {
          display: flex;
          gap: 2px;
          min-width: ${Math.max(slots.length * 24, 300)}px;
        }
        .slot {
          flex: 1;
          min-width: 20px;
          border-radius: 4px;
          cursor: pointer;
          position: relative;
          transition: filter 0.15s;
          display: flex;
          flex-direction: column;
          align-items: center;
          padding-top: 4px;
        }
        .slot:hover { filter: brightness(1.2); }
        .slot.is-override { outline: 2px solid #fbbf24; outline-offset: -2px; }
        .slot-bar {
          width: 100%;
          border-radius: 3px;
        }
        .slot-time {
          font-size: 0.6em;
          color: ${COLORS.subtext};
          margin-top: 2px;
          white-space: nowrap;
          overflow: hidden;
        }

        /* SOC chart */
        .chart-wrap { margin-bottom: 12px; }
        svg text { font-family: inherit; }

        /* Aggressiveness slider */
        .slider-row {
          display: flex;
          align-items: center;
          gap: 10px;
          margin-bottom: 12px;
          font-size: 0.82em;
        }
        .slider-label { color: ${COLORS.subtext}; min-width: 90px; }
        input[type=range] {
          flex: 1;
          accent-color: #a855f7;
          height: 4px;
        }
        .slider-value { min-width: 36px; text-align: right; font-weight: 600; }

        /* Legend */
        .legend {
          display: flex;
          gap: 12px;
          flex-wrap: wrap;
          font-size: 0.75em;
          color: ${COLORS.subtext};
          margin-bottom: 8px;
        }
        .legend-item { display: flex; align-items: center; gap: 4px; }
        .legend-dot { width: 10px; height: 10px; border-radius: 2px; }

        /* Override dialog */
        .dialog-overlay {
          position: fixed;
          inset: 0;
          background: rgba(0,0,0,0.6);
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 1000;
        }
        .dialog {
          background: var(--card-background-color, #1f2937);
          border-radius: 12px;
          padding: 20px;
          min-width: 280px;
          max-width: 360px;
          width: 90%;
          box-shadow: 0 20px 60px rgba(0,0,0,0.5);
        }
        .dialog h3 { margin: 0 0 16px; font-size: 1em; }
        .dialog label { display: block; font-size: 0.82em; color: ${COLORS.subtext}; margin-bottom: 4px; }
        .dialog select, .dialog input {
          width: 100%;
          padding: 8px;
          border-radius: 6px;
          border: 1px solid ${COLORS.border};
          background: rgba(255,255,255,0.05);
          color: ${COLORS.text};
          font-size: 0.9em;
          margin-bottom: 12px;
          box-sizing: border-box;
        }
        .dialog-buttons { display: flex; gap: 8px; justify-content: flex-end; }
        .btn-cancel { background: rgba(255,255,255,0.1); color: ${COLORS.text}; }
        .btn-apply  { background: #3b82f6; color: #fff; }
        .slot-detail {
          font-size: 0.75em;
          color: ${COLORS.subtext};
          background: rgba(255,255,255,0.05);
          border-radius: 6px;
          padding: 8px;
          margin-bottom: 12px;
        }
        .slot-detail .row { display: flex; justify-content: space-between; padding: 2px 0; }
        .slot-detail .val { color: ${COLORS.text}; font-weight: 500; }
      </style>

      <div class="card">
        <!-- Header -->
        <div class="header">
          <div style="display:flex;align-items:center;gap:8px;">
            <span class="title">${this._config.title}</span>
            <span class="state-badge">${optimizerState}</span>
          </div>
          <div class="controls">
            <button class="btn-recalc" id="btn-recalc">↺ Recalculate</button>
            <button class="btn-pause" id="btn-pause">${isPaused ? "▶ Resume" : "⏸ Pause"}</button>
          </div>
        </div>

        <!-- Health summary -->
        ${this._renderHealth(health, currency)}

        <!-- Timeline -->
        <div class="timeline-wrap">
          <div class="timeline" id="timeline">
            ${this._renderSlots(slots)}
          </div>
        </div>

        <!-- SOC chart -->
        <div class="chart-wrap">
          ${this._renderSOCChart(slots)}
        </div>

        <!-- Legend -->
        <div class="legend">
          ${Object.entries(ACTION_LABELS).map(([k, v]) =>
            `<div class="legend-item">
              <div class="legend-dot" style="background:${COLORS[k]}"></div>
              <span>${v}</span>
            </div>`
          ).join("")}
          <div class="legend-item">
            <div class="legend-dot" style="background:${COLORS.soc_line};border-radius:50%"></div>
            <span>Planned SOC</span>
          </div>
          <div class="legend-item">
            <div class="legend-dot" style="background:${COLORS.soc_actual};border-radius:50%"></div>
            <span>Actual SOC</span>
          </div>
        </div>

        <!-- Aggressiveness slider -->
        <div class="slider-row">
          <span class="slider-label">Aggressiveness</span>
          <input type="range" id="aggr-slider" min="0" max="1" step="0.05"
            value="${aggressiveness}" />
          <span class="slider-value" id="aggr-val">${Math.round(aggressiveness * 100)}%</span>
        </div>

        <!-- Override dialog (conditionally rendered) -->
        ${this._overrideDialogOpen && this._selectedSlot ? this._renderOverrideDialog() : ""}
      </div>
    `;

    this._attachListeners(slots, aggressiveness);
  }

  _renderHealth(health, currency) {
    if (!health) return "";
    const revenue = health.estimated_export_revenue;
    const security = health.energy_security_score;
    const confidence = health.forecast_confidence;
    const solveMs = health.solver_duration_ms;

    return `
      <div class="health-row">
        ${revenue !== undefined ? `<div class="health-item">
          <span>Est. Revenue</span>
          <span class="health-value">${currency}${Number(revenue).toFixed(2)}</span>
        </div>` : ""}
        ${security !== undefined ? `<div class="health-item">
          <span>Security</span>
          <span class="health-value" style="color:${security >= 0.8 ? '#22c55e' : security >= 0.5 ? '#f59e0b' : '#ef4444'}">
            ${Math.round(security * 100)}%
          </span>
        </div>` : ""}
        ${confidence !== undefined ? `<div class="health-item">
          <span>Forecast Confidence</span>
          <span class="health-value">${Math.round(confidence * 100)}%</span>
        </div>` : ""}
        ${health.bridge_to_time ? `<div class="health-item">
          <span>Bridge to</span>
          <span class="health-value">${this._formatTime(health.bridge_to_time)} <small style="font-weight:400;font-size:0.8em">(${health.bridge_to_source?.replace("_", " ") || ""})</small></span>
        </div>` : ""}
        ${health.last_recalculation ? `<div class="health-item">
          <span>Last calc</span>
          <span class="health-value">${this._formatRelativeTime(health.last_recalculation)}</span>
        </div>` : ""}
        ${solveMs ? `<div class="health-item">
          <span>Solve time</span>
          <span class="health-value">${Math.round(solveMs)}ms</span>
        </div>` : ""}
        ${health.fallback_mode_active ? `<div class="health-item">
          <span style="color:#ef4444;font-weight:600">⚠ Fallback active</span>
        </div>` : ""}
      </div>
    `;
  }

  _renderSlots(slots) {
    if (!slots.length) return `<div style="color:${COLORS.subtext};font-size:0.85em;padding:16px;">No schedule data yet. Check entity and configuration.</div>`;

    const maxBarH = 48;
    return slots.map((slot, i) => {
      const color = COLORS[slot.action] || COLORS.hold;
      const power = Math.abs(slot.power_kw || 0);
      const maxPow = 5;
      const barH = Math.max(8, Math.round((power / maxPow) * maxBarH));
      const time = this._formatTime(slot.start);
      const isHistorical = slot.is_historical;
      const isOverride = slot.is_override;

      return `
        <div class="slot${isOverride ? " is-override" : ""}"
             data-index="${i}"
             style="opacity:${isHistorical ? 0.5 : 1};"
             title="${ACTION_LABELS[slot.action] || slot.action} ${power.toFixed(1)}kW @ ${time}">
          <div class="slot-bar" style="height:${barH}px;background:${color};"></div>
          ${i % 4 === 0 ? `<div class="slot-time">${time}</div>` : ""}
        </div>
      `;
    }).join("");
  }

  _renderSOCChart(slots) {
    if (!slots.length) return "";

    const W = 560, H = 80;
    const padL = 32, padR = 8, padT = 8, padB = 20;
    const chartW = W - padL - padR;
    const chartH = H - padT - padB;

    const socValues = slots.map(s => s.projected_soc ?? null);
    const actualSoc = slots.map(s => s.actual_soc ?? null);

    const toX = i => padL + (i / (slots.length - 1 || 1)) * chartW;
    const toY = v => padT + chartH - (v / 100) * chartH;

    // Grid lines at 20%, 50%, 80%
    const gridLines = [20, 50, 80].map(pct => {
      const y = toY(pct);
      return `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}"
                stroke="${COLORS.grid_line}" stroke-width="0.5" stroke-dasharray="3,3"/>
              <text x="${padL - 2}" y="${y + 3}" text-anchor="end"
                fill="${COLORS.subtext}" font-size="8">${pct}%</text>`;
    }).join("");

    // Planned SOC path
    const socPoints = socValues
      .map((v, i) => v !== null ? `${toX(i)},${toY(v)}` : null)
      .filter(Boolean);
    const socPath = socPoints.length > 1
      ? `<polyline points="${socPoints.join(" ")}"
           fill="none" stroke="${COLORS.soc_line}" stroke-width="2"
           stroke-linejoin="round" />`
      : "";

    // Actual SOC path (historical only)
    const actualPoints = actualSoc
      .map((v, i) => v !== null ? `${toX(i)},${toY(v)}` : null)
      .filter(Boolean);
    const actualPath = actualPoints.length > 1
      ? `<polyline points="${actualPoints.join(" ")}"
           fill="none" stroke="${COLORS.soc_actual}" stroke-width="1.5"
           stroke-dasharray="4,2" stroke-linejoin="round" />`
      : "";

    // Time axis labels
    const timeLabels = slots
      .filter((_, i) => i % Math.max(1, Math.floor(slots.length / 6)) === 0)
      .map((s, idx, arr) => {
        const i = slots.indexOf(s);
        return `<text x="${toX(i)}" y="${H - 2}" text-anchor="middle"
                  fill="${COLORS.subtext}" font-size="7">${this._formatTime(s.start)}</text>`;
      }).join("");

    return `
      <svg viewBox="0 0 ${W} ${H}" style="width:100%;height:auto;display:block;">
        ${gridLines}
        ${socPath}
        ${actualPath}
        ${timeLabels}
      </svg>
    `;
  }

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
            <button class="btn-apply" id="override-apply">Apply Override</button>
          </div>
        </div>
      </div>
    `;
  }

  _attachListeners(slots, aggressiveness) {
    // Recalculate
    this.shadowRoot.getElementById("btn-recalc")?.addEventListener("click", () => {
      this._callService("battery_optimizer", "recalculate_now", {});
    });

    // Pause / Resume
    this.shadowRoot.getElementById("btn-pause")?.addEventListener("click", () => {
      const optimizerState = this._getOptimizerState();
      const service = optimizerState === "paused" ? "resume" : "pause";
      this._callService("battery_optimizer", service, {});
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
        this._overrideDialogOpen = false;
        this._selectedSlot = null;
        this._render();
      });

      this.shadowRoot.getElementById("override-overlay")?.addEventListener("click", (e) => {
        if (e.target.id === "override-overlay") {
          this._overrideDialogOpen = false;
          this._selectedSlot = null;
          this._render();
        }
      });

      this.shadowRoot.getElementById("override-apply")?.addEventListener("click", () => {
        const action = this.shadowRoot.getElementById("override-action").value;
        const powerVal = this.shadowRoot.getElementById("override-power").value;
        const duration = parseInt(this.shadowRoot.getElementById("override-duration").value) || 60;

        const serviceData = {
          action,
          duration_minutes: duration,
          start: this._selectedSlot?.start,
        };
        if (powerVal !== "") {
          serviceData.power_kw = parseFloat(powerVal);
        }

        this._callService("battery_optimizer", "override_slot", serviceData);
        this._overrideDialogOpen = false;
        this._selectedSlot = null;
        this._render();
      });
    }
  }

  _callService(domain, service, data) {
    this._hass?.callService(domain, service, data);
  }

  _formatTime(isoStr) {
    if (!isoStr) return "";
    try {
      const d = new Date(isoStr);
      return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    } catch {
      return isoStr.slice(11, 16) || "";
    }
  }

  _formatRelativeTime(isoStr) {
    if (!isoStr) return "";
    try {
      const diff = Math.round((Date.now() - new Date(isoStr)) / 1000);
      if (diff < 60) return `${diff}s ago`;
      if (diff < 3600) return `${Math.round(diff / 60)}m ago`;
      return `${Math.round(diff / 3600)}h ago`;
    } catch {
      return "";
    }
  }

  getCardSize() {
    return 5;
  }
}

customElements.define("battery-optimizer-card", BatteryOptimizerCard);

// Register with HACS / Lovelace custom card picker
window.customCards = window.customCards || [];
window.customCards.push({
  type: "battery-optimizer-card",
  name: "Battery Optimiser",
  description: "Interactive schedule, SOC curve, and controls for the Battery Optimiser integration",
  preview: false,
  documentationURL: "https://github.com/Fabbbrrr/ha-battery-optimiser",
});

console.info(
  `%c BATTERY-OPTIMIZER-CARD %c v${CARD_VERSION} `,
  "color:#fff;background:#a855f7;padding:2px 4px;border-radius:3px 0 0 3px;font-weight:bold",
  "color:#a855f7;background:#1f2937;padding:2px 4px;border-radius:0 3px 3px 0",
);
