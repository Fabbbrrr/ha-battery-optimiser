/**
 * Battery Optimiser — Sidebar Panel
 * Registered automatically by the integration. No manual configuration needed.
 * Entities are auto-discovered from hass.states.
 */

const PREFIX = 'sensor.battery_optimizer';
const ENTITIES = {
  schedule:  `${PREFIX}_schedule`,
  health:    `${PREFIX}_health`,
  state:     `${PREFIX}_optimizer_state`,
  learning:  `${PREFIX}_learning_status`,
  power:     `${PREFIX}_current_power`,
  projSoc:   `${PREFIX}_projected_soc`,
  confidence:`${PREFIX}_forecast_confidence`,
  security:  `${PREFIX}_energy_security_score`,
  revenue:   `${PREFIX}_estimated_export_revenue`,
  nextAction:`${PREFIX}_next_action`,
  socAtCharge:`${PREFIX}_soc_at_free_charge_start`,
};

const ACTION_COLORS = {
  charge:    '#4caf50',
  discharge: '#ff9800',
  export:    '#2196f3',
  hold:      '#9e9e9e',
};

const ACTION_ICONS = {
  charge:    '⚡',
  discharge: '🔋',
  export:    '↗',
  hold:      '⏸',
};

const STYLES = `
  :host {
    display: block;
    height: 100%;
    background: var(--primary-background-color);
    overflow-y: auto;
    font-family: var(--paper-font-body1_-_font-family, sans-serif);
  }
  .panel-header {
    background: var(--app-header-background-color, var(--primary-color));
    color: var(--app-header-text-color, white);
    padding: 0 24px;
    height: 64px;
    display: flex;
    align-items: center;
    gap: 16px;
    position: sticky;
    top: 0;
    z-index: 10;
    box-shadow: 0 2px 6px rgba(0,0,0,0.25);
  }
  .panel-title {
    margin: 0;
    font-size: 20px;
    font-weight: 400;
    flex: 1;
    letter-spacing: 0.01em;
  }
  .header-right {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .action-badge {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 5px 12px;
    border-radius: 16px;
    font-size: 13px;
    font-weight: 600;
    background: rgba(255,255,255,0.18);
    color: white;
    text-transform: capitalize;
    letter-spacing: 0.03em;
  }
  .soc-value {
    font-size: 26px;
    font-weight: 300;
    color: white;
    min-width: 60px;
    text-align: right;
  }
  .tabs {
    display: flex;
    background: var(--card-background-color);
    border-bottom: 1px solid var(--divider-color);
    position: sticky;
    top: 64px;
    z-index: 9;
  }
  .tab {
    flex: 1;
    padding: 14px 8px;
    text-align: center;
    cursor: pointer;
    font-size: 12px;
    font-weight: 600;
    color: var(--secondary-text-color);
    border-bottom: 3px solid transparent;
    transition: color 0.15s, border-color 0.15s;
    text-transform: uppercase;
    letter-spacing: 0.06em;
  }
  .tab.active {
    color: var(--primary-color);
    border-bottom-color: var(--primary-color);
  }
  .content {
    padding: 16px;
    max-width: 960px;
    margin: 0 auto;
  }
  .card {
    background: var(--card-background-color);
    border-radius: 12px;
    padding: 16px;
    margin-bottom: 14px;
    box-shadow: var(--ha-card-box-shadow, 0 1px 4px rgba(0,0,0,0.1));
  }
  .card-title {
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    color: var(--secondary-text-color);
    margin: 0 0 12px;
  }
  .kv-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 14px;
  }
  .kv-item .label {
    font-size: 11px;
    color: var(--secondary-text-color);
    text-transform: uppercase;
    letter-spacing: 0.04em;
    margin-bottom: 2px;
  }
  .kv-item .value {
    font-size: 20px;
    font-weight: 500;
    color: var(--primary-text-color);
  }
  .kv-item .value.sm {
    font-size: 14px;
  }
  .timeline {
    display: flex;
    gap: 4px;
    flex-wrap: wrap;
    align-items: flex-end;
  }
  .slot-wrap {
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 2px;
  }
  .slot-bar {
    width: 38px;
    height: 30px;
    border-radius: 5px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 13px;
    color: white;
    position: relative;
  }
  .slot-bar.current {
    outline: 2px solid var(--primary-color);
    outline-offset: 2px;
  }
  .slot-time {
    font-size: 9px;
    color: var(--secondary-text-color);
  }
  .stat-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 9px 0;
    border-bottom: 1px solid var(--divider-color);
    font-size: 13px;
  }
  .stat-row:last-child { border-bottom: none; }
  .stat-label { color: var(--secondary-text-color); }
  .stat-value { font-weight: 500; text-align: right; }
  .dot {
    display: inline-block;
    width: 8px;
    height: 8px;
    border-radius: 50%;
    margin-right: 5px;
    vertical-align: middle;
  }
  .dot-ok    { background: #4caf50; }
  .dot-warn  { background: #ff9800; }
  .dot-error { background: #f44336; }
  .alert {
    display: flex;
    align-items: flex-start;
    gap: 8px;
    padding: 10px 14px;
    border-radius: 8px;
    margin-bottom: 12px;
    font-size: 13px;
    line-height: 1.4;
  }
  .alert-warn  { background: #fff3e0; color: #bf360c; border: 1px solid #ffb74d; }
  .alert-error { background: #ffebee; color: #b71c1c; border: 1px solid #ef9a9a; }
  .btn-row {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
    margin-top: 14px;
  }
  button {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 8px 16px;
    border: none;
    border-radius: 8px;
    cursor: pointer;
    font-size: 13px;
    font-weight: 500;
    transition: opacity 0.15s;
    font-family: inherit;
  }
  button:hover { opacity: 0.8; }
  button:active { opacity: 0.6; }
  .btn-primary   { background: var(--primary-color); color: white; }
  .btn-secondary { background: var(--secondary-background-color); color: var(--primary-text-color); border: 1px solid var(--divider-color); }
  .aggressiveness-row {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-top: 12px;
  }
  .aggressiveness-row label {
    font-size: 12px;
    color: var(--secondary-text-color);
    white-space: nowrap;
  }
  input[type=range] {
    flex: 1;
    accent-color: var(--primary-color);
  }
  .aggr-value {
    font-size: 13px;
    font-weight: 600;
    min-width: 32px;
    text-align: right;
  }
  .no-data {
    color: var(--secondary-text-color);
    font-size: 13px;
    padding: 8px 0;
  }
`;

class BatteryOptimizerPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: 'open' });
    this._hass = null;
    this._activeTab = 'schedule';
    this._initialized = false;
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._initialized) {
      this._init();
    } else {
      this._updateHeader();
      this._updateContent();
    }
  }

  // HA sets this when the panel is loaded
  set panel(_) {}

  _st(entityId) {
    return this._hass?.states?.[entityId];
  }

  _val(entityId, fallback = '—') {
    const s = this._st(entityId);
    if (!s || s.state == null || ['unavailable','unknown','none'].includes(s.state)) return fallback;
    return s.state;
  }

  _numVal(entityId, digits = 1, fallback = '—') {
    const v = this._val(entityId, null);
    if (v === null) return fallback;
    const n = parseFloat(v);
    return isNaN(n) ? fallback : n.toFixed(digits);
  }

  _slots() {
    return this._st(ENTITIES.schedule)?.attributes?.slots || [];
  }

  _futureSlots(max = 24) {
    return this._slots().filter(s => !s.is_historical).slice(0, max);
  }

  _currentSlot() {
    return this._futureSlots(1)[0] || null;
  }

  _callService(domain, service, data = {}) {
    this._hass.callService(domain, service, data);
  }

  _init() {
    this._initialized = true;
    const root = this.shadowRoot;
    root.innerHTML = `
      <style>${STYLES}</style>
      <div class="panel-header">
        <h1 class="panel-title">Battery Optimiser</h1>
        <div class="header-right">
          <span class="action-badge" id="hdr-action">—</span>
          <span class="soc-value" id="hdr-soc">—</span>
        </div>
      </div>
      <div class="tabs" id="tabs">
        <div class="tab active" data-tab="schedule">Schedule</div>
        <div class="tab" data-tab="analytics">Analytics</div>
        <div class="tab" data-tab="config">Config</div>
      </div>
      <div class="content" id="content"></div>
    `;

    root.getElementById('tabs').addEventListener('click', e => {
      const tab = e.target.closest('[data-tab]');
      if (!tab) return;
      this._activeTab = tab.dataset.tab;
      root.querySelectorAll('.tab').forEach(t => t.classList.toggle('active', t === tab));
      this._updateContent();
    });

    this._updateHeader();
    this._updateContent();
  }

  _updateHeader() {
    const slot = this._currentSlot();
    const action = slot?.action || '—';
    const soc = this._numVal(ENTITIES.projSoc, 0, null);
    const optState = this._val(ENTITIES.state, 'unknown');

    const hdrAction = this.shadowRoot.getElementById('hdr-action');
    const hdrSoc = this.shadowRoot.getElementById('hdr-soc');
    if (!hdrAction) return;

    const icon = ACTION_ICONS[action] || '●';
    hdrAction.textContent = `${icon} ${action}`;
    const color = ACTION_COLORS[action];
    hdrAction.style.background = color ? `${color}55` : 'rgba(255,255,255,0.18)';

    hdrSoc.textContent = soc !== null ? `${soc}%` : '—';
  }

  _updateContent() {
    const content = this.shadowRoot.getElementById('content');
    if (!content) return;
    if (this._activeTab === 'schedule')   content.innerHTML = this._renderSchedule();
    else if (this._activeTab === 'analytics') content.innerHTML = this._renderAnalytics();
    else content.innerHTML = this._renderConfig();
    this._bindContentEvents();
  }

  // ── Alerts ────────────────────────────────────────────────────────────────

  _renderAlerts() {
    const health = this._st(ENTITIES.health)?.attributes || {};
    const optState = this._val(ENTITIES.state);
    const learn = this._val(ENTITIES.learning);
    const out = [];

    if (optState === 'fallback' || health.fallback_mode_active) {
      out.push(`<div class="alert alert-warn">⚠ Optimizer running in fallback mode — check <strong>solver_status</strong> in the Analytics tab.</div>`);
    }
    if (health.soc_sensor_available === false) {
      out.push(`<div class="alert alert-error">✖ SOC sensor unavailable — verify your battery entity in Settings → Devices &amp; Services → Battery Optimiser → Configure.</div>`);
    }
    if (learn === 'not_started') {
      out.push(`<div class="alert alert-warn">⚠ Consumption learner not started — add a consumption entity in the setup wizard (Step 5).</div>`);
    }
    return out.join('');
  }

  // ── Schedule tab ──────────────────────────────────────────────────────────

  _renderSchedule() {
    const future = this._futureSlots(24);
    const current = this._currentSlot();
    const optState = this._val(ENTITIES.state, 'unknown');
    const isPaused = optState === 'paused';

    const timeline = future.length
      ? future.map((slot, i) => {
          const color = ACTION_COLORS[slot.action] || '#9e9e9e';
          const icon  = ACTION_ICONS[slot.action]  || '●';
          const time  = slot.start ? slot.start.substring(11, 16) : '';
          const title = `${slot.action}  ${slot.power_kw != null ? slot.power_kw.toFixed(1) + ' kW' : ''}  ${time}`;
          return `
            <div class="slot-wrap" title="${title}">
              <div class="slot-bar${i === 0 ? ' current' : ''}" style="background:${color}">${icon}</div>
              <div class="slot-time">${time}</div>
            </div>`;
        }).join('')
      : '<p class="no-data">No schedule slots available yet.</p>';

    const action = current?.action || '—';
    const power  = this._numVal(ENTITIES.power, 1);
    const projSoc = this._numVal(ENTITIES.projSoc, 0);
    const secScore = this._numVal(ENTITIES.security, 0);
    const revenue  = this._numVal(ENTITIES.revenue, 4);
    const nextAct  = this._val(ENTITIES.nextAction);
    const aggr = this._st(ENTITIES.schedule)?.attributes?.aggressiveness;
    const aggrPct = aggr != null ? Math.round(aggr * 100) : null;

    return `
      ${this._renderAlerts()}

      <div class="card">
        <p class="card-title">Current slot</p>
        <div class="kv-grid">
          <div class="kv-item">
            <div class="label">Action</div>
            <div class="value" style="color:${ACTION_COLORS[action] || 'inherit'}">${action}</div>
          </div>
          <div class="kv-item">
            <div class="label">Power</div>
            <div class="value">${power !== '—' ? power + ' kW' : '—'}</div>
          </div>
          <div class="kv-item">
            <div class="label">Projected SOC</div>
            <div class="value">${projSoc !== '—' ? projSoc + '%' : '—'}</div>
          </div>
          <div class="kv-item">
            <div class="label">Next action</div>
            <div class="value sm">${nextAct}</div>
          </div>
        </div>
      </div>

      <div class="card">
        <p class="card-title">Schedule — next ${future.length} slots</p>
        <div class="timeline">${timeline}</div>
      </div>

      <div class="card">
        <p class="card-title">Plan health</p>
        <div class="kv-grid">
          <div class="kv-item">
            <div class="label">Security score</div>
            <div class="value">${secScore !== '—' ? secScore + '%' : '—'}</div>
          </div>
          <div class="kv-item">
            <div class="label">Est. revenue</div>
            <div class="value sm">${revenue}</div>
          </div>
        </div>
      </div>

      <div class="card">
        <p class="card-title">Controls</p>
        ${aggrPct != null ? `
        <div class="aggressiveness-row">
          <label>Reserve &nbsp;←&nbsp; Aggressiveness</label>
          <input type="range" id="aggr-slider" min="0" max="100" value="${aggrPct}">
          <span class="aggr-value" id="aggr-val">${aggrPct}%</span>
        </div>` : ''}
        <div class="btn-row">
          <button class="btn-primary" id="btn-recalc">↻ Recalculate</button>
          <button class="btn-secondary" id="btn-pause">${isPaused ? '▶ Resume' : '⏸ Pause'}</button>
        </div>
      </div>
    `;
  }

  // ── Analytics tab ─────────────────────────────────────────────────────────

  _renderAnalytics() {
    const h = this._st(ENTITIES.health)?.attributes || {};
    const learn = this._st(ENTITIES.learning);
    const la = learn?.attributes || {};
    const learnState = learn?.state || 'not_started';

    const solverOk = h.solver_status === 'ok';
    const solverDot = solverOk ? 'dot-ok' : 'dot-error';

    const learnDot = learnState === 'trained' ? 'dot-ok'
                   : learnState === 'learning' ? 'dot-warn' : 'dot-error';

    const lastRecalc = h.last_recalculation
      ? new Date(h.last_recalculation).toLocaleString()
      : '—';

    const confidence = h.forecast_confidence != null
      ? `${(h.forecast_confidence * 100).toFixed(0)}%` : '—';
    const secScore = h.energy_security_score != null
      ? `${(h.energy_security_score * 100).toFixed(0)}%` : '—';
    const bridge = h.bridge_to_time
      ? `${h.bridge_to_time.substring(11, 16)} (${h.bridge_to_source || '?'})` : '—';

    // Planned vs actual accuracy from historical slots
    const histSlots = this._slots().filter(s => s.is_historical && s.actual_soc != null && s.projected_soc != null);
    let accuracyLine = '<p class="no-data">No planned vs actual data yet — available after the first slot boundary has passed.</p>';
    if (histSlots.length > 0) {
      const errors = histSlots.map(s => Math.abs(s.actual_soc - s.projected_soc));
      const mae = errors.reduce((a, b) => a + b, 0) / errors.length;
      accuracyLine = `<div class="stat-row"><span class="stat-label">SOC prediction error (MAE)</span><span class="stat-value">${mae.toFixed(1)} pp (${histSlots.length} slots)</span></div>`;
    }

    return `
      <div class="card">
        <p class="card-title">Solver health</p>
        <div class="stat-row">
          <span class="stat-label">Status</span>
          <span class="stat-value"><span class="dot ${solverDot}"></span>${h.solver_status || '—'}</span>
        </div>
        <div class="stat-row">
          <span class="stat-label">Solve time</span>
          <span class="stat-value">${h.solver_duration_ms != null ? h.solver_duration_ms + ' ms' : '—'}</span>
        </div>
        <div class="stat-row">
          <span class="stat-label">Last recalculation</span>
          <span class="stat-value">${lastRecalc}</span>
        </div>
        <div class="stat-row">
          <span class="stat-label">Forecast confidence</span>
          <span class="stat-value">${confidence}</span>
        </div>
        <div class="stat-row">
          <span class="stat-label">Energy security score</span>
          <span class="stat-value">${secScore}</span>
        </div>
        <div class="stat-row">
          <span class="stat-label">Bridge-to point</span>
          <span class="stat-value">${bridge}</span>
        </div>
        <div class="stat-row">
          <span class="stat-label">Fallback active</span>
          <span class="stat-value">${h.fallback_mode_active ? '⚠ Yes' : 'No'}</span>
        </div>
      </div>

      <div class="card">
        <p class="card-title">Planned vs actual accuracy</p>
        ${accuracyLine}
      </div>

      <div class="card">
        <p class="card-title">Consumption learning</p>
        <div class="stat-row">
          <span class="stat-label">Status</span>
          <span class="stat-value"><span class="dot ${learnDot}"></span>${learnState}</span>
        </div>
        ${la.observation_count != null ? `<div class="stat-row"><span class="stat-label">Observations</span><span class="stat-value">${la.observation_count}</span></div>` : ''}
        ${la.days_covered != null ? `<div class="stat-row"><span class="stat-label">Days covered</span><span class="stat-value">${parseFloat(la.days_covered).toFixed(1)}</span></div>` : ''}
        ${la.profile_types ? `<div class="stat-row"><span class="stat-label">Profile type</span><span class="stat-value">${la.profile_types}</span></div>` : ''}
        ${la.has_temperature_model != null ? `<div class="stat-row"><span class="stat-label">Temperature model</span><span class="stat-value">${la.has_temperature_model ? 'Active' : 'Not trained'}</span></div>` : ''}
        ${la.baseline_kw != null ? `<div class="stat-row"><span class="stat-label">Baseline fallback</span><span class="stat-value">${la.baseline_kw} kW</span></div>` : ''}
        <div class="btn-row">
          <button class="btn-secondary" id="btn-retrain">🧠 Retrain Now</button>
        </div>
      </div>
    `;
  }

  // ── Config tab ────────────────────────────────────────────────────────────

  _renderConfig() {
    const schedAttrs = this._st(ENTITIES.schedule)?.attributes || {};
    const health = this._st(ENTITIES.health)?.attributes || {};
    const aggr = schedAttrs.aggressiveness;
    const aggrPct = aggr != null ? `${Math.round(aggr * 100)}%` : '—';

    const confidence = this._numVal(ENTITIES.confidence, 0);
    const security   = this._numVal(ENTITIES.security, 0);
    const socAtCharge = this._numVal(ENTITIES.socAtCharge, 0);

    return `
      <div class="card">
        <p class="card-title">Key readings</p>
        <div class="kv-grid">
          <div class="kv-item">
            <div class="label">Forecast confidence</div>
            <div class="value">${confidence !== '—' ? confidence + '%' : '—'}</div>
          </div>
          <div class="kv-item">
            <div class="label">Energy security</div>
            <div class="value">${security !== '—' ? security + '%' : '—'}</div>
          </div>
          <div class="kv-item">
            <div class="label">SOC at charge window</div>
            <div class="value">${socAtCharge !== '—' ? socAtCharge + '%' : '—'}</div>
          </div>
          <div class="kv-item">
            <div class="label">Aggressiveness</div>
            <div class="value">${aggrPct}</div>
          </div>
        </div>
      </div>

      <div class="card">
        <p class="card-title">Optimizer status</p>
        <div class="stat-row">
          <span class="stat-label">Optimizer state</span>
          <span class="stat-value">${schedAttrs.state || '—'}</span>
        </div>
        <div class="stat-row">
          <span class="stat-label">Solver status</span>
          <span class="stat-value">${health.solver_status || '—'}</span>
        </div>
        <div class="stat-row">
          <span class="stat-label">SOC sensor</span>
          <span class="stat-value">
            <span class="dot ${health.soc_sensor_available ? 'dot-ok' : 'dot-error'}"></span>
            ${health.soc_sensor_available ? 'Available' : 'Unavailable'}
          </span>
        </div>
        <div class="stat-row">
          <span class="stat-label">Fallback active</span>
          <span class="stat-value">${health.fallback_mode_active ? '⚠ Yes' : 'No'}</span>
        </div>
        <div class="stat-row">
          <span class="stat-label">Forecast staleness</span>
          <span class="stat-value">${health.forecast_staleness_seconds != null ? health.forecast_staleness_seconds + 's' : '—'}</span>
        </div>
      </div>

      <div class="card">
        <p class="card-title">Reconfigure</p>
        <p style="font-size:13px;color:var(--secondary-text-color);margin:0 0 10px">
          Tariff settings, entity mappings, inverter limits, and advanced options are in the
          integration configuration.
        </p>
        <div class="btn-row">
          <button class="btn-primary" id="btn-open-config">Open Integration Settings</button>
        </div>
      </div>
    `;
  }

  // ── Event binding ─────────────────────────────────────────────────────────

  _bindContentEvents() {
    const root = this.shadowRoot;
    const optState = this._val(ENTITIES.state, 'unknown');
    const isPaused = optState === 'paused';

    const bind = (id, fn) => {
      const el = root.getElementById(id);
      if (el) el.addEventListener('click', fn);
    };

    bind('btn-recalc', () => this._callService('battery_optimizer', 'recalculate_now'));
    bind('btn-pause',  () => this._callService('battery_optimizer', isPaused ? 'resume' : 'pause'));
    bind('btn-retrain', () => this._callService('battery_optimizer', 'retrain_learner'));

    bind('btn-open-config', () => {
      window.history.pushState(null, '', '/config/integrations');
      window.dispatchEvent(new PopStateEvent('popstate'));
    });

    const slider = root.getElementById('aggr-slider');
    const aggrVal = root.getElementById('aggr-val');
    if (slider) {
      slider.addEventListener('input', () => {
        if (aggrVal) aggrVal.textContent = slider.value + '%';
      });
      slider.addEventListener('change', () => {
        this._callService('battery_optimizer', 'set_aggressiveness', {
          aggressiveness: parseFloat(slider.value) / 100,
        });
      });
    }
  }
}

customElements.define('battery-optimizer-panel', BatteryOptimizerPanel);
