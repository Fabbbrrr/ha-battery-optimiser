/**
 * Battery Optimiser — Sidebar Panel v0.0.32
 * Registered automatically by the integration. No manual configuration needed.
 * Entities are auto-discovered from hass.states.
 *
 * Changes in v0.0.32:
 * - Fixed Fetch Logs button: use fetchWithAuth instead of callApi for plain-text /api/error_log
 */

const PREFIX = 'sensor.battery_optimiser';
const ENTITIES = {
  schedule:       `${PREFIX}_schedule`,
  health:         `${PREFIX}_health`,
  state:          `${PREFIX}_optimizer_state`,
  learning:       `${PREFIX}_learning_status`,
  power:          `${PREFIX}_current_power`,
  projSoc:        `${PREFIX}_projected_soc`,
  confidence:     `${PREFIX}_forecast_confidence`,
  security:       `${PREFIX}_energy_security_score`,
  revenue:        `${PREFIX}_estimated_export_revenue`,
  nextAction:     `${PREFIX}_next_action`,
  socAtCharge:    `${PREFIX}_soc_at_free_charge_start`,
  exportRec:      `${PREFIX}_export_recommendation`,
  exportPower:    `${PREFIX}_export_recommended_power`,
  socGain:        `${PREFIX}_soc_gain_in_charge_window`,
  daysLowSolar:   `${PREFIX}_days_low_solar_ahead`,
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
  button:disabled { opacity: 0.4; cursor: default; }
  .btn-primary   { background: var(--primary-color); color: white; }
  .btn-secondary { background: var(--secondary-background-color); color: var(--primary-text-color); border: 1px solid var(--divider-color); }
  .btn-danger    { background: #f44336; color: white; }
  .debug-entity {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 10px 0;
    border-bottom: 1px solid var(--divider-color);
    font-size: 13px;
  }
  .debug-entity:last-child { border-bottom: none; }
  .debug-entity-id {
    font-family: monospace;
    font-size: 12px;
    color: var(--secondary-text-color);
    flex: 1;
    word-break: break-all;
  }
  .debug-entity-state {
    font-family: monospace;
    font-size: 12px;
    font-weight: 600;
    padding: 2px 8px;
    border-radius: 10px;
    white-space: nowrap;
  }
  .state-ok    { background: #e8f5e9; color: #2e7d32; }
  .state-warn  { background: #fff3e0; color: #bf360c; }
  .state-error { background: #ffebee; color: #b71c1c; }
  .debug-label { font-size: 11px; color: var(--secondary-text-color); min-width: 80px; }
  code {
    font-family: monospace;
    font-size: 11px;
    background: var(--secondary-background-color);
    padding: 1px 5px;
    border-radius: 4px;
  }
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

  /* ── Status banner ─────────────────────────────────────────────────────── */
  .status-banner {
    display: flex;
    align-items: center;
    gap: 16px;
    flex-wrap: wrap;
  }
  .banner-left {
    flex: 1;
    min-width: 120px;
  }
  .banner-action-label {
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    color: var(--secondary-text-color);
    margin-bottom: 4px;
  }
  .banner-action-text {
    font-size: 24px;
    font-weight: 700;
    letter-spacing: 0.03em;
  }
  .banner-action-icon {
    font-size: 20px;
    margin-right: 4px;
  }
  .banner-center {
    display: flex;
    flex-direction: column;
    align-items: center;
  }
  .banner-right {
    flex: 1;
    min-width: 120px;
    text-align: right;
  }
  .banner-next-label {
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    color: var(--secondary-text-color);
    margin-bottom: 4px;
  }
  .banner-next-val {
    font-size: 14px;
    font-weight: 600;
  }
  .banner-sub {
    display: flex;
    gap: 20px;
    margin-top: 14px;
    padding-top: 12px;
    border-top: 1px solid var(--divider-color);
    flex-wrap: wrap;
  }
  .banner-sub-item {
    display: flex;
    flex-direction: column;
    gap: 2px;
  }
  .banner-sub-label {
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--secondary-text-color);
  }
  .banner-sub-val {
    font-size: 15px;
    font-weight: 600;
  }

  /* ── Slot rows ─────────────────────────────────────────────────────────── */
  .slot-row {
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 8px 4px;
    border-bottom: 1px solid var(--divider-color);
    font-size: 13px;
  }
  .slot-row:last-child { border-bottom: none; }
  .slot-stripe {
    width: 4px;
    height: 36px;
    border-radius: 2px;
    flex-shrink: 0;
  }
  .slot-action-badge {
    font-weight: 700;
    font-size: 11px;
    min-width: 90px;
    text-transform: uppercase;
    letter-spacing: 0.03em;
  }
  .slot-time {
    color: var(--secondary-text-color);
    font-size: 12px;
    min-width: 95px;
    font-variant-numeric: tabular-nums;
  }
  .slot-power {
    font-weight: 500;
    font-size: 13px;
    min-width: 55px;
  }
  .slot-soc {
    color: var(--secondary-text-color);
    font-size: 12px;
    font-variant-numeric: tabular-nums;
  }

  /* ── Accuracy grid ─────────────────────────────────────────────────────── */
  .accuracy-grid {
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 10px;
  }
  .accuracy-item {
    text-align: center;
    padding: 10px 8px;
    background: var(--secondary-background-color);
    border-radius: 8px;
  }
  .accuracy-label {
    font-size: 11px;
    color: var(--secondary-text-color);
    margin-bottom: 4px;
  }
  .accuracy-value {
    font-size: 18px;
    font-weight: 600;
    color: var(--primary-text-color);
  }
  .accuracy-note {
    font-size: 10px;
    color: var(--secondary-text-color);
    margin-top: 2px;
  }

  /* ── Status pill ───────────────────────────────────────────────────────── */
  .status-pill {
    display: inline-block;
    padding: 2px 10px;
    border-radius: 10px;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
  }
  .pill-ok    { background: #e8f5e9; color: #2e7d32; }
  .pill-warn  { background: #fff3e0; color: #bf360c; }
  .pill-error { background: #ffebee; color: #b71c1c; }

  /* ── Progress bar ──────────────────────────────────────────────────────── */
  .progress-wrap {
    display: flex;
    align-items: center;
    gap: 8px;
    margin: 6px 0;
  }
  .progress-bar {
    flex: 1;
    height: 6px;
    background: var(--divider-color);
    border-radius: 3px;
    overflow: hidden;
  }
  .progress-fill {
    height: 100%;
    background: var(--primary-color);
    border-radius: 3px;
  }
  .progress-label {
    font-size: 11px;
    color: var(--secondary-text-color);
    white-space: nowrap;
  }

  /* ── Confidence bar ────────────────────────────────────────────────────── */
  .conf-bar-wrap {
    margin-top: 10px;
  }
  .conf-bar-label {
    font-size: 11px;
    color: var(--secondary-text-color);
    margin-bottom: 4px;
    display: flex;
    justify-content: space-between;
  }
  .conf-bar-track {
    height: 8px;
    background: var(--divider-color);
    border-radius: 4px;
    overflow: hidden;
  }
  .conf-bar-fill {
    height: 100%;
    border-radius: 4px;
  }

  /* ── Entity health grid ────────────────────────────────────────────────── */
  .entity-health-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 8px;
  }
  .entity-health-item {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 8px 10px;
    background: var(--secondary-background-color);
    border-radius: 8px;
  }
  .entity-health-info {
    flex: 1;
    min-width: 0;
  }
  .entity-health-id {
    font-size: 10px;
    font-family: monospace;
    color: var(--secondary-text-color);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }
  .entity-health-state {
    font-size: 13px;
    font-weight: 600;
    color: var(--primary-text-color);
  }
  .entity-health-name {
    font-size: 11px;
    color: var(--secondary-text-color);
    margin-bottom: 2px;
  }

  /* ── Stat chips ────────────────────────────────────────────────────────── */
  .stat-chips {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin: 12px 0 4px;
  }
  .chip {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 4px 10px;
    background: var(--secondary-background-color);
    border-radius: 16px;
    font-size: 12px;
    color: var(--primary-text-color);
    border: 1px solid var(--divider-color);
  }

  /* ── Log viewer ────────────────────────────────────────────────────────── */
  .log-pre {
    max-height: 300px;
    overflow-y: auto;
    background: #1e1e1e;
    color: #d4d4d4;
    font-family: monospace;
    font-size: 11px;
    padding: 10px;
    border-radius: 8px;
    margin: 8px 0 0;
    white-space: pre-wrap;
    word-break: break-all;
    line-height: 1.5;
  }
  .log-error { color: #f44336; }
  .log-warn  { color: #ff9800; }
  .log-info  { color: #64b5f6; }
  .log-debug { color: #9e9e9e; }

  /* ── Raw JSON ──────────────────────────────────────────────────────────── */
  details summary {
    cursor: pointer;
    font-size: 13px;
    font-weight: 500;
    padding: 4px 0;
    color: var(--primary-text-color);
    user-select: none;
  }
  .raw-pre {
    max-height: 400px;
    overflow: auto;
    background: var(--secondary-background-color);
    font-family: monospace;
    font-size: 10px;
    padding: 10px;
    border-radius: 8px;
    white-space: pre;
    margin-top: 8px;
    line-height: 1.5;
  }

  /* ── Solver stat grid ──────────────────────────────────────────────────── */
  .solver-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 6px;
  }
  .solver-stat {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 7px 10px;
    background: var(--secondary-background-color);
    border-radius: 6px;
    font-size: 12px;
  }
  .solver-stat-label { color: var(--secondary-text-color); }
  .solver-stat-value { font-weight: 600; }
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

  _futureSlots(max = 48) {
    return this._slots().filter(s => !s.is_historical).slice(0, max);
  }

  _decisionSlots() {
    const attrs = this._st(ENTITIES.schedule)?.attributes;
    // If decision_slots key is present (even empty), respect it — windows may be configured
    // but we're currently outside them. Only fall back to all future slots when the key
    // is absent entirely (old firmware / optimizer not yet run).
    if (attrs && 'decision_slots' in attrs) {
      return (attrs.decision_slots || []).filter(s => !s.is_historical);
    }
    return this._futureSlots(24);
  }

  _currentSlot() {
    return this._futureSlots(1)[0] || null;
  }

  _callService(domain, service, data = {}) {
    this._hass.callService(domain, service, data);
  }

  _escHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  _timeInWindow(slotStart, winStart, winEnd) {
    if (!winStart || !winEnd || !slotStart) return false;
    const hhmm = slotStart.substring(11, 16);
    if (winStart <= winEnd) {
      return hhmm >= winStart && hhmm < winEnd;
    }
    // Overnight window
    return hhmm >= winStart || hhmm < winEnd;
  }

  _nextEvent() {
    const future = this._futureSlots(24);
    if (future.length < 2) return null;
    const curAction = future[0]?.action;
    const next = future.slice(1).find(s => s.action !== curAction) || future[1];
    if (!next) return null;
    const diff = new Date(next.start).getTime() - Date.now();
    if (diff <= 0) return null;
    const h = Math.floor(diff / 3600000);
    const m = Math.floor((diff % 3600000) / 60000);
    const icon = ACTION_ICONS[next.action] || '●';
    const timeStr = h > 0 ? `${h}h ${m}m` : `${m}m`;
    return { text: `${icon} ${next.action} in ${timeStr}`, action: next.action };
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
        <div class="tab" data-tab="history">History</div>
        <div class="tab" data-tab="config">Config</div>
        <div class="tab" data-tab="debug">Debug</div>
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
    if (this._activeTab === 'schedule')       content.innerHTML = this._renderSchedule();
    else if (this._activeTab === 'analytics') content.innerHTML = this._renderAnalytics();
    else if (this._activeTab === 'history')   content.innerHTML = this._renderHistory();
    else if (this._activeTab === 'config')    content.innerHTML = this._renderConfig();
    else                                      content.innerHTML = this._renderDebug();
    this._bindContentEvents();
  }

  // ── Alerts ──────────────────────────────────────────────────────────────

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

  // ── SVG helpers ──────────────────────────────────────────────────────────

  /**
   * Renders an SVG area+line chart from [{x, y}] point arrays.
   * opts: { W, H, padL, padR, padT, padB, yMin, yMax, lineColor, areaColor, strokeWidth }
   */
  _svgLine(points, opts = {}) {
    const {
      W = 600, H = 200,
      padL = 40, padR = 10, padT = 10, padB = 30,
      yMin = 0, yMax = 100,
      lineColor = '#2196f3',
      areaColor = 'rgba(33,150,243,0.12)',
      strokeWidth = 2,
      dashed = false,
    } = opts;
    if (!points || points.length < 2) return '';
    const cW = W - padL - padR;
    const cH = H - padT - padB;
    const bottom = padT + cH;
    const pts = points.map(p => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ');
    const area = `M${points[0].x.toFixed(1)},${bottom} ` +
      points.map(p => `L${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ') +
      ` L${points[points.length - 1].x.toFixed(1)},${bottom} Z`;
    const dashAttr = dashed ? 'stroke-dasharray="6,4"' : '';
    return `
      <path d="${area}" fill="${areaColor}" stroke="none"/>
      <polyline points="${pts}" fill="none" stroke="${lineColor}" stroke-width="${strokeWidth}" stroke-linejoin="round" stroke-linecap="round" ${dashAttr}/>
    `;
  }

  // ── Schedule tab ─────────────────────────────────────────────────────────

  _renderSchedule() {
    const allFuture = this._futureSlots(48);
    const decSlots  = this._decisionSlots();
    const optState  = this._val(ENTITIES.state, 'unknown');
    const isPaused  = optState === 'paused';
    const aggr      = this._st(ENTITIES.schedule)?.attributes?.aggressiveness;
    const aggrPct   = aggr != null ? Math.round(aggr * 100) : null;

    return `
      ${this._renderAlerts()}
      ${this._renderStatusBanner()}

      <div class="card">
        <p class="card-title">SOC projection</p>
        ${this._renderSOCChart(allFuture)}
        ${this._renderEnergyBars(allFuture)}
      </div>

      <div class="card">
        <p class="card-title">Decision windows — ${decSlots.length} slot${decSlots.length !== 1 ? 's' : ''}</p>
        ${this._renderDecisionWindowContent(decSlots)}
      </div>

      ${this._renderExportCard()}

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

  _renderStatusBanner() {
    const slot    = this._currentSlot();
    const action  = slot?.action || 'unknown';
    const color   = ACTION_COLORS[action] || '#9e9e9e';
    const icon    = ACTION_ICONS[action]  || '●';
    const soc     = parseFloat(this._val(ENTITIES.projSoc, null));
    const power   = this._numVal(ENTITIES.power, 1);
    const sec     = this._numVal(ENTITIES.security, 0);
    const conf    = this._numVal(ENTITIES.confidence, 0);
    const nextEv  = this._nextEvent();

    // Donut gauge
    const R = 32;
    const C = 2 * Math.PI * R;
    const socNum = isNaN(soc) ? 0 : Math.max(0, Math.min(100, soc));
    const dash   = ((socNum / 100) * C).toFixed(1);
    const gap    = (C - parseFloat(dash)).toFixed(1);
    const socDisplay = isNaN(soc) ? '—' : `${Math.round(soc)}%`;

    const gauge = `
      <svg viewBox="0 0 80 80" width="80" height="80">
        <circle cx="40" cy="40" r="${R}" fill="none" stroke="var(--divider-color)" stroke-width="8"/>
        <circle cx="40" cy="40" r="${R}" fill="none" stroke="${color}" stroke-width="8"
          stroke-dasharray="${dash} ${gap}" stroke-linecap="round"
          transform="rotate(-90 40 40)"/>
        <text x="40" y="44" text-anchor="middle" font-size="15" font-weight="700"
          fill="var(--primary-text-color)">${socDisplay}</text>
      </svg>`;

    const nextHtml = nextEv
      ? `<div class="banner-next-val">${this._escHtml(nextEv.text)}</div>`
      : `<div class="banner-next-val" style="color:var(--secondary-text-color)">—</div>`;

    return `
      <div class="card">
        <div class="status-banner">
          <div class="banner-left">
            <div class="banner-action-label">Current action</div>
            <div class="banner-action-text" style="color:${color}">
              <span class="banner-action-icon">${icon}</span>${action.toUpperCase()}
            </div>
          </div>
          <div class="banner-center">
            ${gauge}
          </div>
          <div class="banner-right">
            <div class="banner-next-label">Next event</div>
            ${nextHtml}
          </div>
        </div>
        <div class="banner-sub">
          <div class="banner-sub-item">
            <span class="banner-sub-label">Power</span>
            <span class="banner-sub-val">${power !== '—' ? power + ' kW' : '—'}</span>
          </div>
          <div class="banner-sub-item">
            <span class="banner-sub-label">Security</span>
            <span class="banner-sub-val">${sec !== '—' ? sec + '%' : '—'}</span>
          </div>
          <div class="banner-sub-item">
            <span class="banner-sub-label">Confidence</span>
            <span class="banner-sub-val">${conf !== '—' ? conf + '%' : '—'}</span>
          </div>
        </div>
      </div>`;
  }

  _renderSOCChart(slots) {
    if (!slots || slots.length < 2) {
      return '<p class="no-data">No SOC projection data yet.</p>';
    }

    const W = 600, H = 200;
    const padL = 38, padR = 8, padT = 10, padB = 28;
    const cW = W - padL - padR;
    const cH = H - padT - padB;

    const times = slots.map(s => new Date(s.start).getTime());
    const minT  = times[0];
    const maxT  = times[times.length - 1];
    const tRange = maxT - minT || 1;

    const toX = t  => padL + ((t - minT) / tRange) * cW;
    const toY = soc => padT + cH - Math.min(1, Math.max(0, soc / 100)) * cH;

    // SOC line points
    const socPoints = slots
      .filter(s => s.projected_soc != null)
      .map(s => ({ x: toX(new Date(s.start).getTime()), y: toY(s.projected_soc) }));

    // Window zones from config
    const cfg = this._st(ENTITIES.health)?.attributes?.diagnostics?.config || {};
    const zoneBands = [];
    const windowDefs = [
      { start: cfg.free_import_start, end: cfg.free_import_end, color: 'rgba(76,175,80,0.12)', label: 'Charge' },
      { start: cfg.export_bonus_start, end: cfg.export_bonus_end, color: 'rgba(33,150,243,0.12)', label: 'Export' },
    ];

    for (const wd of windowDefs) {
      if (!wd.start || !wd.end) continue;
      // Find contiguous groups of slots within this window
      let inZone = false;
      let zoneStartX = 0;
      for (let i = 0; i < slots.length; i++) {
        const inW = this._timeInWindow(slots[i].start, wd.start, wd.end);
        const slotX = toX(times[i]);
        // Width to next slot (or end)
        const nextX = i + 1 < slots.length ? toX(times[i + 1]) : W - padR;
        if (inW && !inZone) { inZone = true; zoneStartX = slotX; }
        if (!inW && inZone) {
          zoneBands.push(`<rect x="${zoneStartX.toFixed(1)}" y="${padT}" width="${(slotX - zoneStartX).toFixed(1)}" height="${cH}" fill="${wd.color}"/>`);
          inZone = false;
        }
        if (inW && i === slots.length - 1) {
          zoneBands.push(`<rect x="${zoneStartX.toFixed(1)}" y="${padT}" width="${(nextX - zoneStartX).toFixed(1)}" height="${cH}" fill="${wd.color}"/>`);
        }
      }
    }

    // Y gridlines
    const gridY = [20, 40, 60, 80].map(pct => {
      const y = toY(pct).toFixed(1);
      return `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="var(--divider-color)" stroke-width="1" stroke-dasharray="3,3"/>
              <text x="${padL - 4}" y="${(parseFloat(y) + 4).toFixed(1)}" font-size="9" fill="var(--secondary-text-color)" text-anchor="end">${pct}</text>`;
    }).join('');

    // X axis labels at 2-hour intervals
    const xLabels = slots.filter(s => {
      const d = new Date(s.start);
      return d.getMinutes() === 0 && d.getHours() % 2 === 0;
    }).map(s => {
      const x = toX(new Date(s.start).getTime()).toFixed(1);
      const d = new Date(s.start);
      const label = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });
      return `<text x="${x}" y="${H - 4}" font-size="9" fill="var(--secondary-text-color)" text-anchor="middle">${label}</text>`;
    }).join('');

    // Now marker
    const nowT = Date.now();
    const nowLine = nowT >= minT && nowT <= maxT
      ? `<line x1="${toX(nowT).toFixed(1)}" y1="${padT}" x2="${toX(nowT).toFixed(1)}" y2="${padT + cH}" stroke="#9e9e9e" stroke-width="1.5" stroke-dasharray="4,4"/>`
      : '';

    // Floor line from inputs
    const minSoc = this._st(ENTITIES.health)?.attributes?.diagnostics?.inputs?.min_soc_pct;
    const floorLine = minSoc != null
      ? `<line x1="${padL}" y1="${toY(minSoc).toFixed(1)}" x2="${W - padR}" y2="${toY(minSoc).toFixed(1)}" stroke="#f44336" stroke-width="1.5" stroke-dasharray="6,3"/>
         <text x="${padL + 3}" y="${(toY(minSoc) - 3).toFixed(1)}" font-size="8" fill="#f44336">floor ${minSoc}%</text>`
      : '';

    const lineHtml = this._svgLine(socPoints, {
      W, H, padL, padR, padT, padB,
      lineColor: '#2196f3',
      areaColor: 'rgba(33,150,243,0.10)',
      strokeWidth: 2.5,
    });

    return `
      <svg viewBox="0 0 ${W} ${H}" style="width:100%;display:block;overflow:visible">
        ${zoneBands.join('')}
        ${gridY}
        <line x1="${padL}" y1="${padT}" x2="${padL}" y2="${padT + cH}" stroke="var(--divider-color)" stroke-width="1"/>
        <line x1="${padL}" y1="${padT + cH}" x2="${W - padR}" y2="${padT + cH}" stroke="var(--divider-color)" stroke-width="1"/>
        ${floorLine}
        ${lineHtml}
        ${nowLine}
        ${xLabels}
        <text x="${padL - 4}" y="${toY(0) + 4}" font-size="9" fill="var(--secondary-text-color)" text-anchor="end">0</text>
        <text x="${padL - 4}" y="${padT + 4}" font-size="9" fill="var(--secondary-text-color)" text-anchor="end">100</text>
      </svg>`;
  }

  _renderEnergyBars(slots) {
    const hasSolar = slots.some(s => s.expected_solar_kwh != null && s.expected_solar_kwh > 0);
    const hasCons  = slots.some(s => s.expected_consumption_kwh != null && s.expected_consumption_kwh > 0);
    if (!hasSolar && !hasCons) return '';

    const W = 600, H = 130;
    const padL = 38, padR = 8, padT = 10, padB = 22;
    const cW = W - padL - padR;
    const cH = H - padT - padB;

    const times    = slots.map(s => new Date(s.start).getTime());
    const minT     = times[0];
    const maxT     = times[times.length - 1];
    const tRange   = maxT - minT || 1;

    const solarVals = slots.map(s => s.expected_solar_kwh || 0);
    const consVals  = slots.map(s => s.expected_consumption_kwh || 0);
    // Scale each series independently so low values still show variation
    const solarMax = Math.max(...solarVals, 0.1);
    const consMax  = Math.max(...consVals,  0.1);
    const sharedMax = Math.max(solarMax, consMax);

    const toX   = t   => padL + ((t - minT) / tRange) * cW;
    const toY   = val => padT + cH - Math.min(1, val / sharedMax) * cH;

    const solarPoints = slots.map((s, i) => ({
      x: toX(times[i]),
      y: toY(solarVals[i]),
      tip: `Solar: ${solarVals[i].toFixed(2)} kWh`,
    }));
    const consPoints = slots.map((s, i) => ({
      x: toX(times[i]),
      y: toY(consVals[i]),
      tip: `Load: ${consVals[i].toFixed(2)} kWh`,
    }));

    const solarLine = hasSolar ? this._svgLine(solarPoints, {
      W, H, padL, padR, padT, padB,
      lineColor: '#43a047', areaColor: 'rgba(67,160,71,0.15)', strokeWidth: 2,
    }) : '';
    const consLine = hasCons ? this._svgLine(consPoints, {
      W, H, padL, padR, padT, padB,
      lineColor: '#ef5350', areaColor: 'rgba(239,83,80,0.10)', strokeWidth: 2,
    }) : '';

    // Y gridlines at 50% and 100% of sharedMax
    const gridY = [0.5, 1.0].map(frac => {
      const y   = (padT + cH - frac * cH).toFixed(1);
      const val = (frac * sharedMax).toFixed(2);
      return `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="var(--divider-color)" stroke-width="1" stroke-dasharray="3,3"/>
              <text x="${padL - 4}" y="${(parseFloat(y) + 4).toFixed(1)}" font-size="9" fill="var(--secondary-text-color)" text-anchor="end">${val}</text>`;
    }).join('');

    const legendY = H - 4;
    return `
      <svg viewBox="0 0 ${W} ${H}" style="width:100%;display:block;margin-top:4px;overflow:visible">
        ${gridY}
        <line x1="${padL}" y1="${padT}" x2="${padL}" y2="${padT + cH}" stroke="var(--divider-color)" stroke-width="1"/>
        <line x1="${padL}" y1="${padT + cH}" x2="${W - padR}" y2="${padT + cH}" stroke="var(--divider-color)" stroke-width="1"/>
        <text x="${padL - 4}" y="${(padT + cH + 4).toFixed(1)}" font-size="9" fill="var(--secondary-text-color)" text-anchor="end">0</text>
        ${solarLine}
        ${consLine}
        <circle cx="${padL + 5}" cy="${legendY - 3}" r="3.5" fill="#43a047"/>
        <text x="${padL + 13}" y="${legendY}" font-size="9" fill="#43a047">Solar (kWh)</text>
        <circle cx="${padL + 80}" cy="${legendY - 3}" r="3.5" fill="#ef5350"/>
        <text x="${padL + 88}" y="${legendY}" font-size="9" fill="#ef5350">Load (kWh)</text>
      </svg>`;
  }

  _renderDecisionWindowContent(decSlots) {
    if (decSlots.length > 0) return this._renderSlotsList(decSlots);
    // Empty — check if windows are configured to give a useful message
    const cfg = this._st(ENTITIES.health)?.attributes?.diagnostics?.config || {};
    const hasChargeWin  = cfg.free_import_start && cfg.free_import_end;
    const hasExportWin  = cfg.export_bonus_start && cfg.export_bonus_end;
    const attrs = this._st(ENTITIES.schedule)?.attributes;
    const windowsKnown  = attrs && 'decision_slots' in attrs;

    if (!windowsKnown) {
      return '<p class="no-data">No decision slots yet — the optimizer has not run.</p>';
    }
    if (!hasChargeWin && !hasExportWin) {
      return this._renderSlotsList(this._futureSlots(24));
    }
    const parts = [];
    if (hasChargeWin)  parts.push(`free import ${cfg.free_import_start}–${cfg.free_import_end}`);
    if (hasExportWin) parts.push(`export bonus ${cfg.export_bonus_start}–${cfg.export_bonus_end}`);
    return `<p class="no-data">Outside decision windows (${parts.join(', ')}) — no action required right now.</p>`;
  }

  _renderSlotsList(slots) {
    if (!slots || slots.length === 0) {
      return '<p class="no-data">No decision slots yet — the optimizer has not run.</p>';
    }

    const liveSoc = parseFloat(this._val(ENTITIES.projSoc, null));

    return slots.map((slot, i) => {
      const color   = ACTION_COLORS[slot.action] || '#9e9e9e';
      const icon    = ACTION_ICONS[slot.action]  || '●';
      const tStart  = slot.start ? slot.start.substring(11, 16) : '?';
      const tEnd    = slot.end   ? slot.end.substring(11, 16)   : '?';
      const timeStr = `${tStart}–${tEnd}`;
      const power   = slot.power_kw != null ? `${slot.power_kw.toFixed(1)} kW` : '—';

      // SOC at end of this slot
      const socEnd = slot.projected_soc != null ? Math.round(slot.projected_soc) : null;
      // SOC at start: previous slot's projected_soc or live sensor
      let socStart = null;
      if (i === 0) {
        if (!isNaN(liveSoc)) socStart = Math.round(liveSoc);
      } else {
        const prev = slots[i - 1];
        if (prev.projected_soc != null) socStart = Math.round(prev.projected_soc);
      }

      const socHtml = (socStart != null || socEnd != null)
        ? `<div class="slot-soc">${socStart != null ? socStart + '%' : '?'} → ${socEnd != null ? socEnd + '%' : '?'}</div>`
        : '';

      return `
        <div class="slot-row">
          <div class="slot-stripe" style="background:${color}"></div>
          <div class="slot-action-badge" style="color:${color}">${icon} ${(slot.action || '—').toUpperCase()}</div>
          <div class="slot-time">${timeStr}</div>
          <div class="slot-power">${power}</div>
          ${socHtml}
        </div>`;
    }).join('');
  }

  // ── Export recommendation card ───────────────────────────────────────────

  _renderExportCard() {
    const rec = this._val(ENTITIES.exportRec, null);
    if (rec === null) return '';

    const power   = this._numVal(ENTITIES.exportPower, 1, '—');
    const socGain = this._numVal(ENTITIES.socGain, 1, '—');
    const daysLow = this._val(ENTITIES.daysLowSolar, '—');

    const recColors = {
      full_export:    '#2196f3',
      partial_export: '#ff9800',
      hold:           '#9e9e9e',
      not_configured: '#9e9e9e',
    };
    const recLabels = {
      full_export:    'Full export recommended',
      partial_export: 'Partial export recommended',
      hold:           'Hold — do not export',
      not_configured: 'Export window not configured',
    };
    const color = recColors[rec] || '#9e9e9e';
    const label = recLabels[rec] || rec;

    const recAttrs  = this._st(ENTITIES.exportRec)?.attributes || {};
    const reasoning = (recAttrs.reasoning || []).map(r => `<li>${this._escHtml(r)}</li>`).join('');
    const totalKwh  = recAttrs.total_export_kwh != null ? `, ${recAttrs.total_export_kwh} kWh total` : '';
    const winStart  = recAttrs.export_window_start || '—';
    const winEnd    = recAttrs.export_window_end   || '—';

    // Confidence bar: export_slots_active / export_slots_total
    let confBar = '';
    if (recAttrs.export_slots_active != null && recAttrs.export_slots_total != null && recAttrs.export_slots_total > 0) {
      const pct = Math.round((recAttrs.export_slots_active / recAttrs.export_slots_total) * 100);
      confBar = `
        <div class="conf-bar-wrap">
          <div class="conf-bar-label">
            <span>Exporting slots</span>
            <span>${recAttrs.export_slots_active} / ${recAttrs.export_slots_total}${totalKwh}</span>
          </div>
          <div class="conf-bar-track">
            <div class="conf-bar-fill" style="width:${pct}%;background:${color}"></div>
          </div>
        </div>`;
    }

    return `
      <div class="card" style="border-left: 4px solid ${color}">
        <p class="card-title">Export window recommendation</p>
        <div style="display:flex;align-items:center;gap:10px;margin-bottom:12px">
          <span style="font-size:18px;font-weight:600;color:${color}">${label}</span>
        </div>
        <div class="kv-grid">
          <div class="kv-item">
            <div class="label">Window</div>
            <div class="value sm">${winStart} – ${winEnd}</div>
          </div>
          <div class="kv-item">
            <div class="label">Recommended power</div>
            <div class="value">${power !== '—' ? power + ' kW' : '—'}</div>
          </div>
          <div class="kv-item">
            <div class="label">Charge window SOC gain</div>
            <div class="value">${socGain !== '—' ? socGain + ' pp' : '—'}</div>
          </div>
          <div class="kv-item">
            <div class="label">Low solar days ahead</div>
            <div class="value">${daysLow}</div>
          </div>
        </div>
        ${confBar}
        ${reasoning ? `<ul style="font-size:12px;color:var(--secondary-text-color);margin:10px 0 0;padding-left:16px">${reasoning}</ul>` : ''}
      </div>`;
  }

  // ── Analytics tab ────────────────────────────────────────────────────────

  _renderAnalytics() {
    const h        = this._st(ENTITIES.health)?.attributes || {};
    const learn    = this._st(ENTITIES.learning);
    const la       = learn?.attributes || {};
    const learnState = learn?.state || 'not_started';

    const learnPill = learnState === 'trained'  ? '<span class="status-pill pill-ok">Trained</span>'
                    : learnState === 'learning' ? '<span class="status-pill pill-warn">Learning</span>'
                                                : '<span class="status-pill pill-error">Not started</span>';

    const daysCovered  = la.days_covered  != null ? parseFloat(la.days_covered)  : 0;
    const lookbackDays = la.lookback_days != null ? parseFloat(la.lookback_days) : null;
    const progressPct  = lookbackDays && lookbackDays > 0
      ? Math.min(100, Math.round((daysCovered / lookbackDays) * 100)) : 0;
    const progressBar  = lookbackDays != null ? `
      <div class="progress-wrap">
        <div class="progress-bar"><div class="progress-fill" style="width:${progressPct}%"></div></div>
        <span class="progress-label">${daysCovered.toFixed(1)} / ${lookbackDays} days</span>
      </div>` : '';

    const solverOk = h.solver_status === 'ok';
    const lastRecalc = h.last_recalculation ? new Date(h.last_recalculation).toLocaleString() : '—';
    const bridge = h.bridge_to_time
      ? `${h.bridge_to_time.substring(11, 16)} (${h.bridge_to_source || '?'})` : '—';

    const solverStats = [
      ['Status',      `<span class="dot ${solverOk ? 'dot-ok' : 'dot-error'}"></span>${h.solver_status || '—'}`],
      ['Solve time',  h.solver_duration_ms != null ? `${h.solver_duration_ms} ms${h.solver_duration_ms > 5000 ? ' ⚠' : ''}` : '—'],
      ['Last recalc', lastRecalc],
      ['Confidence',  h.forecast_confidence != null ? `${(h.forecast_confidence * 100).toFixed(0)}%` : '—'],
      ['Security',    h.energy_security_score != null ? `${(h.energy_security_score * 100).toFixed(0)}%` : '—'],
      ['Bridge-to',   bridge],
      ['Fallback',    h.fallback_mode_active ? '⚠ Active' : 'No'],
      ['Staleness',   h.forecast_staleness_seconds != null ? `${h.forecast_staleness_seconds}s` : '—'],
    ].map(([k, v]) => `
      <div class="solver-stat">
        <span class="solver-stat-label">${k}</span>
        <span class="solver-stat-value">${v}</span>
      </div>`).join('');

    return `
      <div class="card">
        <p class="card-title">3-day solar forecast</p>
        ${this._renderSolarForecastChart()}
      </div>

      <div class="card">
        <p class="card-title">Planned vs actual SOC</p>
        ${this._renderPlannedVsActualChart()}
      </div>

      ${this._renderAccuracyStats()}

      <div class="card">
        <p class="card-title">Consumption learning</p>
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
          <span style="font-size:13px;font-weight:500">${learnState}</span>
          ${learnPill}
        </div>
        ${progressBar}
        ${la.observation_count != null ? `<div class="stat-row"><span class="stat-label">Observations</span><span class="stat-value">${la.observation_count}</span></div>` : ''}
        ${la.profile_types ? `<div class="stat-row"><span class="stat-label">Profile type</span><span class="stat-value">${la.profile_types}</span></div>` : ''}
        ${la.has_temperature_model != null ? `<div class="stat-row"><span class="stat-label">Temperature model</span><span class="stat-value">${la.has_temperature_model ? 'Active' : 'Not trained'}</span></div>` : ''}
        ${la.baseline_kw != null ? `<div class="stat-row"><span class="stat-label">Baseline fallback</span><span class="stat-value">${la.baseline_kw} kW</span></div>` : ''}
        <div class="btn-row">
          <button class="btn-secondary" id="btn-retrain">Retrain Now</button>
        </div>
      </div>

      <div class="card">
        <p class="card-title">Solver health</p>
        <div class="solver-grid">
          ${solverStats}
        </div>
      </div>
    `;
  }

  _renderSolarForecastChart() {
    const recAttrs = this._st(ENTITIES.exportRec)?.attributes || {};
    const daily    = recAttrs.daily_solar_kwh;
    if (!daily || daily.length === 0) {
      return '<p class="no-data">No 3-day solar forecast data — export recommendation sensor not available.</p>';
    }

    const W = 400, H = 160;
    const padL = 36, padR = 8, padT = 20, padB = 28;
    const cW = W - padL - padR;
    const cH = H - padT - padB;
    const n   = daily.length;
    const maxVal = Math.max(...daily, 0.1);

    // Good solar threshold — 3 kWh as a rough "worth exporting" line
    const threshold = 3;
    const threshY = padT + cH - (Math.min(threshold, maxVal) / maxVal) * cH;

    const labels = ['Today', 'Tomorrow', 'Day+2'];
    const barW   = (cW / n) * 0.55;
    const barGap = cW / n;

    const bars = daily.map((kwh, i) => {
      const x = padL + i * barGap + (barGap - barW) / 2;
      const h = (kwh / maxVal) * cH;
      const y = padT + cH - h;
      const barColor = kwh >= threshold ? '#4caf50' : '#90a4ae';
      return `
        <rect x="${x.toFixed(1)}" y="${y.toFixed(1)}" width="${barW.toFixed(1)}" height="${h.toFixed(1)}" fill="${barColor}" rx="3"/>
        <text x="${(x + barW / 2).toFixed(1)}" y="${(y - 4).toFixed(1)}" text-anchor="middle" font-size="10" fill="${barColor}" font-weight="600">${kwh.toFixed(1)}</text>
        <text x="${(x + barW / 2).toFixed(1)}" y="${H - 6}" text-anchor="middle" font-size="9" fill="var(--secondary-text-color)">${labels[i] || ''}</text>`;
    }).join('');

    // Y gridlines
    const yGridLines = [0.25, 0.5, 0.75, 1.0].map(frac => {
      const y = padT + cH - frac * cH;
      const val = (frac * maxVal).toFixed(1);
      return `<line x1="${padL}" y1="${y.toFixed(1)}" x2="${W - padR}" y2="${y.toFixed(1)}" stroke="var(--divider-color)" stroke-width="1" stroke-dasharray="3,3"/>
              <text x="${padL - 4}" y="${(y + 4).toFixed(1)}" font-size="9" fill="var(--secondary-text-color)" text-anchor="end">${val}</text>`;
    }).join('');

    const threshLine = threshold <= maxVal
      ? `<line x1="${padL}" y1="${threshY.toFixed(1)}" x2="${W - padR}" y2="${threshY.toFixed(1)}" stroke="#ff9800" stroke-width="1" stroke-dasharray="4,3"/>
         <text x="${W - padR - 2}" y="${(threshY - 3).toFixed(1)}" font-size="8" fill="#ff9800" text-anchor="end">3 kWh</text>`
      : '';

    return `
      <svg viewBox="0 0 ${W} ${H}" style="width:100%;max-width:420px;display:block">
        ${yGridLines}
        <line x1="${padL}" y1="${padT}" x2="${padL}" y2="${padT + cH}" stroke="var(--divider-color)" stroke-width="1"/>
        <line x1="${padL}" y1="${padT + cH}" x2="${W - padR}" y2="${padT + cH}" stroke="var(--divider-color)" stroke-width="1"/>
        <text x="${padL - 4}" y="${padT + cH + 4}" font-size="9" fill="var(--secondary-text-color)" text-anchor="end">0</text>
        ${bars}
        ${threshLine}
      </svg>
      <p style="font-size:11px;color:var(--secondary-text-color);margin:4px 0 0">kWh per day &mdash; green if &ge; 3 kWh</p>`;
  }

  _renderPlannedVsActualChart() {
    const histSlots = this._slots().filter(s => s.is_historical);
    if (histSlots.length === 0) {
      return '<p class="no-data">No historical data yet — builds up after the first slot boundary passes.</p>';
    }

    const W = 600, H = 180;
    const padL = 38, padR = 8, padT = 10, padB = 28;
    const cW = W - padL - padR;
    const cH = H - padT - padB;

    const times  = histSlots.map(s => new Date(s.start).getTime());
    const minT   = times[0];
    const maxT   = times[times.length - 1];
    const tRange = maxT - minT || 1;

    const toX = t   => padL + ((t - minT) / tRange) * cW;
    const toY = soc => padT + cH - Math.min(1, Math.max(0, soc / 100)) * cH;

    const plannedPts = histSlots
      .filter(s => s.projected_soc != null)
      .map(s => ({ x: toX(new Date(s.start).getTime()), y: toY(s.projected_soc) }));

    const actualPts = histSlots
      .filter(s => s.actual_soc != null)
      .map(s => ({ x: toX(new Date(s.start).getTime()), y: toY(s.actual_soc) }));

    const gridY = [25, 50, 75].map(pct => {
      const y = toY(pct).toFixed(1);
      return `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="var(--divider-color)" stroke-width="1" stroke-dasharray="3,3"/>
              <text x="${padL - 4}" y="${(parseFloat(y) + 4).toFixed(1)}" font-size="9" fill="var(--secondary-text-color)" text-anchor="end">${pct}</text>`;
    }).join('');

    const xLabels = histSlots.filter((s, i) => i % Math.max(1, Math.floor(histSlots.length / 6)) === 0).map(s => {
      const x = toX(new Date(s.start).getTime()).toFixed(1);
      const d = new Date(s.start);
      const label = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });
      return `<text x="${x}" y="${H - 4}" font-size="9" fill="var(--secondary-text-color)" text-anchor="middle">${label}</text>`;
    }).join('');

    const plannedLine = this._svgLine(plannedPts, {
      W, H, padL, padR, padT, padB,
      lineColor: '#2196f3', areaColor: 'rgba(33,150,243,0.08)', strokeWidth: 2,
    });
    const actualLine = this._svgLine(actualPts, {
      W, H, padL, padR, padT, padB,
      lineColor: '#ff9800', areaColor: 'transparent', strokeWidth: 2,
    });

    return `
      <svg viewBox="0 0 ${W} ${H}" style="width:100%;display:block">
        ${gridY}
        <line x1="${padL}" y1="${padT}" x2="${padL}" y2="${padT + cH}" stroke="var(--divider-color)" stroke-width="1"/>
        <line x1="${padL}" y1="${padT + cH}" x2="${W - padR}" y2="${padT + cH}" stroke="var(--divider-color)" stroke-width="1"/>
        ${plannedLine}
        ${actualLine}
        ${xLabels}
        <circle cx="${padL + 4}" cy="${H - 16}" r="4" fill="#2196f3"/>
        <text x="${padL + 12}" y="${H - 12}" font-size="9" fill="#2196f3">Planned</text>
        <circle cx="${padL + 58}" cy="${H - 16}" r="4" fill="#ff9800"/>
        <text x="${padL + 66}" y="${H - 12}" font-size="9" fill="#ff9800">Actual</text>
      </svg>`;
  }

  _renderAccuracyStats() {
    const histSlots = this._slots().filter(s => s.is_historical);
    if (histSlots.length === 0) return '';

    const socSlots = histSlots.filter(s => s.actual_soc != null && s.projected_soc != null);
    const socMAE   = socSlots.length > 0
      ? (socSlots.reduce((a, s) => a + Math.abs(s.actual_soc - s.projected_soc), 0) / socSlots.length).toFixed(1)
      : null;

    const solarSlots = histSlots.filter(s => s.actual_solar_kwh != null && s.expected_solar_kwh > 0);
    const solarAcc   = solarSlots.length > 0
      ? (solarSlots.reduce((a, s) => a + s.actual_solar_kwh / s.expected_solar_kwh, 0) / solarSlots.length * 100).toFixed(0)
      : null;

    const consSlots = histSlots.filter(s => s.actual_consumption_kwh != null && s.expected_consumption_kwh > 0);
    const consAcc   = consSlots.length > 0
      ? (consSlots.reduce((a, s) => a + s.actual_consumption_kwh / s.expected_consumption_kwh, 0) / consSlots.length * 100).toFixed(0)
      : null;

    const items = [
      { label: 'Solar forecast', value: solarAcc != null ? `${solarAcc}%` : '—', note: `${solarSlots.length} slots` },
      { label: 'Consumption',    value: consAcc  != null ? `${consAcc}%`  : '—', note: `${consSlots.length} slots` },
      { label: 'SOC accuracy',   value: socMAE   != null ? `\u00b1${socMAE} pp` : '—', note: `${socSlots.length} slots` },
    ];

    return `
      <div class="card">
        <p class="card-title">Forecast accuracy</p>
        <div class="accuracy-grid">
          ${items.map(it => `
            <div class="accuracy-item">
              <div class="accuracy-label">${it.label}</div>
              <div class="accuracy-value">${it.value}</div>
              <div class="accuracy-note">${it.note}</div>
            </div>`).join('')}
        </div>
      </div>`;
  }

  // ── History tab ──────────────────────────────────────────────────────────

  _renderHistory() {
    const histSlots = this._slots().filter(s => s.is_historical);
    const corrections = (this._st(ENTITIES.health)?.attributes?.diagnostics || {}).corrections || {};

    return `
      <div class="card">
        <p class="card-title">Planned vs actual SOC</p>
        ${this._renderHistorySOCChart(histSlots)}
      </div>

      <div class="card">
        <p class="card-title">Solar: actual vs predicted</p>
        ${this._renderHistorySolarChart(histSlots)}
      </div>

      <div class="card">
        <p class="card-title">Load: actual vs predicted</p>
        ${this._renderHistoryLoadChart(histSlots)}
      </div>

      <div class="card">
        <p class="card-title">Correction factors (24-hour heatmap)</p>
        ${this._renderCorrectionHeatmap(corrections)}
      </div>

      <div class="card">
        <p class="card-title">Forecast corrections</p>
        ${this._renderCorrectionsCard(corrections)}
      </div>
    `;
  }

  _renderHistorySOCChart(histSlots) {
    if (histSlots.length === 0) {
      return '<p class="no-data">No historical data yet — builds up after the first slot boundary passes.</p>';
    }

    const W = 600, H = 220;
    const padL = 38, padR = 8, padT = 10, padB = 28;
    const cW = W - padL - padR;
    const cH = H - padT - padB;

    const times  = histSlots.map(s => new Date(s.start).getTime());
    const minT   = times[0];
    const maxT   = times[times.length - 1];
    const tRange = maxT - minT || 1;

    const toX = t   => padL + ((t - minT) / tRange) * cW;
    const toY = soc => padT + cH - Math.min(1, Math.max(0, soc / 100)) * cH;

    const plannedPts = histSlots
      .filter(s => s.projected_soc != null)
      .map(s => ({ x: toX(new Date(s.start).getTime()), y: toY(s.projected_soc) }));

    const actualPts = histSlots
      .filter(s => s.actual_soc != null)
      .map(s => ({ x: toX(new Date(s.start).getTime()), y: toY(s.actual_soc) }));

    const gridY = [25, 50, 75].map(pct => {
      const y = toY(pct).toFixed(1);
      return `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="var(--divider-color)" stroke-width="1" stroke-dasharray="3,3"/>
              <text x="${padL - 4}" y="${(parseFloat(y) + 4).toFixed(1)}" font-size="9" fill="var(--secondary-text-color)" text-anchor="end">${pct}</text>`;
    }).join('');

    const xLabels = histSlots.filter((s, i) => i % Math.max(1, Math.floor(histSlots.length / 6)) === 0).map(s => {
      const x = toX(new Date(s.start).getTime()).toFixed(1);
      const d = new Date(s.start);
      const label = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });
      return `<text x="${x}" y="${H - 4}" font-size="9" fill="var(--secondary-text-color)" text-anchor="middle">${label}</text>`;
    }).join('');

    const plannedLine = this._svgLine(plannedPts, { W, H, padL, padR, padT, padB, lineColor: '#2196f3', areaColor: 'rgba(33,150,243,0.08)', strokeWidth: 2 });
    const actualLine  = this._svgLine(actualPts,  { W, H, padL, padR, padT, padB, lineColor: '#ff9800', areaColor: 'transparent', strokeWidth: 2 });

    const socPairs = histSlots.filter(s => s.actual_soc != null && s.projected_soc != null);
    const mae = socPairs.length > 0
      ? (socPairs.reduce((a, s) => a + Math.abs(s.actual_soc - s.projected_soc), 0) / socPairs.length).toFixed(1)
      : null;
    const maeTip = mae != null ? `<p style="font-size:11px;color:var(--secondary-text-color);margin:4px 0 0">MAE: \u00b1${mae} pp over ${socPairs.length} slots</p>` : '';

    return `
      <svg viewBox="0 0 ${W} ${H}" style="width:100%;display:block">
        ${gridY}
        <line x1="${padL}" y1="${padT}" x2="${padL}" y2="${padT + cH}" stroke="var(--divider-color)" stroke-width="1"/>
        <line x1="${padL}" y1="${padT + cH}" x2="${W - padR}" y2="${padT + cH}" stroke="var(--divider-color)" stroke-width="1"/>
        ${plannedLine}${actualLine}${xLabels}
        <circle cx="${padL + 4}" cy="${H - 16}" r="4" fill="#2196f3"/>
        <text x="${padL + 12}" y="${H - 12}" font-size="9" fill="#2196f3">Planned</text>
        <circle cx="${padL + 58}" cy="${H - 16}" r="4" fill="#ff9800"/>
        <text x="${padL + 66}" y="${H - 12}" font-size="9" fill="#ff9800">Actual</text>
      </svg>${maeTip}`;
  }

  _renderHistorySolarChart(histSlots) {
    const withSolar = histSlots.filter(s => s.expected_solar_kwh != null && s.expected_solar_kwh > 0);
    const withActual = histSlots.filter(s => s.actual_solar_kwh != null || s.actual_generation_kwh != null);

    if (withSolar.length === 0) {
      return '<p class="no-data">No solar forecast data in history yet.</p>';
    }

    const W = 600, H = 160;
    const padL = 38, padR = 8, padT = 10, padB = 28;
    const cW = W - padL - padR;
    const cH = H - padT - padB;

    const times = histSlots.map(s => new Date(s.start).getTime());
    const minT  = times[0];
    const maxT  = times[times.length - 1];
    const tRange = maxT - minT || 1;

    const allVals = [
      ...histSlots.map(s => s.expected_solar_kwh || 0),
      ...histSlots.map(s => s.actual_generation_kwh ?? s.actual_solar_kwh ?? 0),
    ];
    const maxVal = Math.max(...allVals, 0.1);

    const toX = t   => padL + ((t - minT) / tRange) * cW;
    const toY = kwh => padT + cH - Math.min(1, Math.max(0, kwh / maxVal)) * cH;

    const plannedPts = histSlots
      .filter(s => s.expected_solar_kwh != null)
      .map(s => ({ x: toX(new Date(s.start).getTime()), y: toY(s.expected_solar_kwh) }));

    const actualPts = histSlots
      .filter(s => s.actual_generation_kwh != null || s.actual_solar_kwh != null)
      .map(s => ({ x: toX(new Date(s.start).getTime()), y: toY(s.actual_generation_kwh ?? s.actual_solar_kwh) }));

    const gridY = [0.25, 0.5, 0.75, 1.0].map(frac => {
      const y = (padT + cH - frac * cH).toFixed(1);
      return `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="var(--divider-color)" stroke-width="1" stroke-dasharray="3,3"/>
              <text x="${padL - 4}" y="${(parseFloat(y) + 4).toFixed(1)}" font-size="9" fill="var(--secondary-text-color)" text-anchor="end">${(frac * maxVal).toFixed(2)}</text>`;
    }).join('');

    const xLabels = histSlots.filter((s, i) => i % Math.max(1, Math.floor(histSlots.length / 6)) === 0).map(s => {
      const x = toX(new Date(s.start).getTime()).toFixed(1);
      const label = new Date(s.start).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });
      return `<text x="${x}" y="${H - 4}" font-size="9" fill="var(--secondary-text-color)" text-anchor="middle">${label}</text>`;
    }).join('');

    const plannedLine = this._svgLine(plannedPts, { W, H, padL, padR, padT, padB, lineColor: '#2196f3', areaColor: 'rgba(33,150,243,0.08)', strokeWidth: 2 });
    const actualLine  = actualPts.length > 0
      ? this._svgLine(actualPts, { W, H, padL, padR, padT, padB, lineColor: '#ffa726', areaColor: 'transparent', strokeWidth: 2 })
      : `<text x="${W / 2}" y="${padT + cH / 2}" font-size="10" fill="var(--secondary-text-color)" text-anchor="middle">Configure a solar generation meter in Config for actual tracking</text>`;

    return `
      <svg viewBox="0 0 ${W} ${H}" style="width:100%;display:block">
        ${gridY}
        <line x1="${padL}" y1="${padT}" x2="${padL}" y2="${padT + cH}" stroke="var(--divider-color)" stroke-width="1"/>
        <line x1="${padL}" y1="${padT + cH}" x2="${W - padR}" y2="${padT + cH}" stroke="var(--divider-color)" stroke-width="1"/>
        ${plannedLine}${actualLine}${xLabels}
        <circle cx="${padL + 4}" cy="${H - 16}" r="4" fill="#2196f3"/>
        <text x="${padL + 12}" y="${H - 12}" font-size="9" fill="#2196f3">Predicted</text>
        ${actualPts.length > 0 ? `<circle cx="${padL + 62}" cy="${H - 16}" r="4" fill="#ffa726"/><text x="${padL + 70}" y="${H - 12}" font-size="9" fill="#ffa726">Actual</text>` : ''}
      </svg>
      <p style="font-size:11px;color:var(--secondary-text-color);margin:4px 0 0">kWh per slot</p>`;
  }

  _renderHistoryLoadChart(histSlots) {
    const withLoad = histSlots.filter(s => s.expected_consumption_kwh != null && s.expected_consumption_kwh > 0);
    if (withLoad.length === 0) {
      return '<p class="no-data">No consumption data in history yet.</p>';
    }

    const W = 600, H = 160;
    const padL = 38, padR = 8, padT = 10, padB = 28;
    const cW = W - padL - padR;
    const cH = H - padT - padB;

    const times  = histSlots.map(s => new Date(s.start).getTime());
    const minT   = times[0];
    const maxT   = times[times.length - 1];
    const tRange = maxT - minT || 1;

    const allVals = [
      ...histSlots.map(s => s.expected_consumption_kwh || 0),
      ...histSlots.map(s => s.actual_consumption_kwh   || 0),
    ];
    const maxVal = Math.max(...allVals, 0.1);

    const toX = t   => padL + ((t - minT) / tRange) * cW;
    const toY = kwh => padT + cH - Math.min(1, Math.max(0, kwh / maxVal)) * cH;

    const plannedPts = histSlots
      .filter(s => s.expected_consumption_kwh != null)
      .map(s => ({ x: toX(new Date(s.start).getTime()), y: toY(s.expected_consumption_kwh) }));

    const actualPts = histSlots
      .filter(s => s.actual_consumption_kwh != null)
      .map(s => ({ x: toX(new Date(s.start).getTime()), y: toY(s.actual_consumption_kwh) }));

    const gridY = [0.25, 0.5, 0.75, 1.0].map(frac => {
      const y = (padT + cH - frac * cH).toFixed(1);
      return `<line x1="${padL}" y1="${y}" x2="${W - padR}" y2="${y}" stroke="var(--divider-color)" stroke-width="1" stroke-dasharray="3,3"/>
              <text x="${padL - 4}" y="${(parseFloat(y) + 4).toFixed(1)}" font-size="9" fill="var(--secondary-text-color)" text-anchor="end">${(frac * maxVal).toFixed(2)}</text>`;
    }).join('');

    const xLabels = histSlots.filter((s, i) => i % Math.max(1, Math.floor(histSlots.length / 6)) === 0).map(s => {
      const x = toX(new Date(s.start).getTime()).toFixed(1);
      const label = new Date(s.start).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', hour12: false });
      return `<text x="${x}" y="${H - 4}" font-size="9" fill="var(--secondary-text-color)" text-anchor="middle">${label}</text>`;
    }).join('');

    const plannedLine = this._svgLine(plannedPts, { W, H, padL, padR, padT, padB, lineColor: '#2196f3', areaColor: 'rgba(33,150,243,0.08)', strokeWidth: 2 });
    const actualLine  = actualPts.length > 0
      ? this._svgLine(actualPts, { W, H, padL, padR, padT, padB, lineColor: '#ef5350', areaColor: 'transparent', strokeWidth: 2 })
      : '';

    return `
      <svg viewBox="0 0 ${W} ${H}" style="width:100%;display:block">
        ${gridY}
        <line x1="${padL}" y1="${padT}" x2="${padL}" y2="${padT + cH}" stroke="var(--divider-color)" stroke-width="1"/>
        <line x1="${padL}" y1="${padT + cH}" x2="${W - padR}" y2="${padT + cH}" stroke="var(--divider-color)" stroke-width="1"/>
        ${plannedLine}${actualLine}${xLabels}
        <circle cx="${padL + 4}" cy="${H - 16}" r="4" fill="#2196f3"/>
        <text x="${padL + 12}" y="${H - 12}" font-size="9" fill="#2196f3">Predicted</text>
        ${actualPts.length > 0 ? `<circle cx="${padL + 62}" cy="${H - 16}" r="4" fill="#ef5350"/><text x="${padL + 70}" y="${H - 12}" font-size="9" fill="#ef5350">Actual</text>` : ''}
      </svg>
      <p style="font-size:11px;color:var(--secondary-text-color);margin:4px 0 0">kWh per slot</p>`;
  }

  _renderCorrectionHeatmap(corrections) {
    if (!corrections || !corrections.solar_ratios) {
      return '<p class="no-data">No correction data yet — builds up after several slot boundaries pass.</p>';
    }

    const minObs      = corrections.min_obs_threshold || 5;
    const solarRatios = corrections.solar_ratios    || Array(24).fill(1.0);
    const solarCounts = corrections.solar_counts    || Array(24).fill(0);
    const loadRatios  = corrections.load_ratios_weekday || Array(24).fill(1.0);
    const loadCounts  = corrections.load_counts_weekday || Array(24).fill(0);

    const W = 600, cellH = 30, labelW = 60, cellW = (W - labelW) / 24;

    const ratioColor = r => {
      // < 1 (overshoots) → red, = 1 → grey, > 1 (undershoots) → green
      if (r < 1) {
        const t = Math.min(1, (1 - r) / 0.5);
        const g = Math.round(165 * (1 - t));
        return `rgb(220,${g},${g})`;
      } else {
        const t = Math.min(1, (r - 1) / 0.5);
        const r2 = Math.round(165 * (1 - t));
        return `rgb(${r2},220,${r2})`;
      }
    };

    const makeRow = (label, ratios, counts) => {
      const cells = Array.from({ length: 24 }, (_, h) => {
        const x = labelW + h * cellW;
        const count = counts[h] || 0;
        const ratio = ratios[h] || 1.0;
        const active = count >= minObs;
        const fill   = active ? ratioColor(ratio) : '#555';
        const txt    = active ? ratio.toFixed(2) : '?';
        const txtCol = active ? '#000' : '#aaa';
        const tip    = active ? `Hour ${h}:00 — ratio ${ratio.toFixed(3)} (${count} obs)` : `Hour ${h}:00 — fewer than ${minObs} observations`;
        return `<g><title>${tip}</title>
          <rect x="${x.toFixed(1)}" y="0" width="${cellW.toFixed(1)}" height="${cellH}" fill="${fill}" rx="2" stroke="var(--card-background-color)" stroke-width="1"/>
          ${cellW > 18 ? `<text x="${(x + cellW / 2).toFixed(1)}" y="${cellH / 2 + 4}" font-size="8" text-anchor="middle" fill="${txtCol}">${txt}</text>` : ''}
        </g>`;
      }).join('');

      const hourLabels = [0, 6, 12, 18, 23].map(h => {
        const x = labelW + h * cellW + cellW / 2;
        return `<text x="${x.toFixed(1)}" y="${cellH + 12}" font-size="8" text-anchor="middle" fill="var(--secondary-text-color)">${String(h).padStart(2, '0')}h</text>`;
      }).join('');

      return `<g transform="translate(0,0)">
        <text x="${labelW - 4}" y="${cellH / 2 + 4}" font-size="9" text-anchor="end" fill="var(--secondary-text-color)">${label}</text>
        ${cells}
        ${hourLabels}
      </g>`;
    };

    const svgH = cellH * 2 + 28;
    return `
      <svg viewBox="0 0 ${W} ${svgH}" style="width:100%;display:block">
        ${makeRow('Solar', solarRatios, solarCounts)}
        <g transform="translate(0,${cellH + 2})">
          ${makeRow('Load', loadRatios, loadCounts).replace(/<g transform="translate\(0,0\)">/, '<g>')}
        </g>
      </svg>
      <p style="font-size:11px;color:var(--secondary-text-color);margin:6px 0 0">&lt; 1.0 = forecast overshoots &nbsp;|&nbsp; &gt; 1.0 = forecast undershoots &nbsp;|&nbsp; grey = learning (fewer than ${minObs} obs)</p>`;
  }

  _renderCorrectionsCard(corrections) {
    const active = corrections.active;
    const pill = active === true  ? '<span class="status-pill pill-ok">Active</span>'
               : active === false ? '<span class="status-pill pill-warn">Learning</span>'
               :                    '<span class="status-pill pill-error">No data</span>';

    const fmt = v => v != null ? v.toFixed(3) : '—';
    const fmtPct = v => v != null ? `${((v - 1) * 100).toFixed(1)}%` : null;

    const solarRatio = corrections.solar_mean_ratio;
    const solarNote  = solarRatio != null
      ? (solarRatio < 1 ? `overshoots by ${fmtPct(1/solarRatio)}` : `undershoots by ${fmtPct(solarRatio)}`)
      : null;

    const wdRatio = corrections.load_mean_ratio_weekday;
    const weRatio = corrections.load_mean_ratio_weekend;
    const drift   = corrections.soc_drift_pp;

    const rows = [
      ['Solar ratio',         solarRatio != null ? `${fmt(solarRatio)}${solarNote ? ` — forecast ${solarNote}` : ''}` : '—'],
      ['Load ratio (weekday)',wdRatio != null ? fmt(wdRatio) : '—'],
      ['Load ratio (weekend)',weRatio != null ? fmt(weRatio) : '—'],
      ['SOC drift',           drift   != null ? `${drift > 0 ? '+' : ''}${drift.toFixed(1)} pp` : '—'],
      ['Solar observations',  corrections.solar_obs_total != null ? String(corrections.solar_obs_total) : '—'],
      ['Load observations',   corrections.load_obs_total  != null ? String(corrections.load_obs_total)  : '—'],
    ];

    const driftNote = drift != null
      ? (Math.abs(drift) > 3
          ? `<p style="font-size:11px;color:#ff9800;margin:0 0 8px">SOC drift ${drift > 0 ? '+' : ''}${drift.toFixed(1)} pp — battery charges ${drift > 0 ? 'faster' : 'slower'} than projected</p>`
          : '')
      : '';

    return `
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
        <span style="font-size:13px;font-weight:500">Status</span>${pill}
      </div>
      ${driftNote}
      ${rows.map(([k, v]) => `<div class="stat-row"><span class="stat-label">${k}</span><span class="stat-value">${v}</span></div>`).join('')}
      <div class="btn-row" style="margin-top:12px">
        <button class="btn-secondary" id="btn-reset-corrections">Reset corrections</button>
      </div>`;
  }

  // ── Config tab ───────────────────────────────────────────────────────────

  _renderConfig() {
    const health   = this._st(ENTITIES.health)?.attributes || {};
    const diag     = health.diagnostics || {};
    const entities = diag.entities || {};
    const inputs   = diag.inputs   || {};
    const schedAttrs = this._st(ENTITIES.schedule)?.attributes || {};

    // Entity health grid
    const entityDefs = [
      { label: 'SOC sensor',     key: 'soc'            },
      { label: 'Solar forecast', key: 'solar_forecast' },
      { label: 'Consumption',    key: 'consumption'    },
      { label: 'Weather',        key: 'weather'        },
    ];

    const entityGrid = entityDefs.map(({ label, key }) => {
      const e = entities[key];
      if (!e) return `
        <div class="entity-health-item">
          <span class="dot dot-warn"></span>
          <div class="entity-health-info">
            <div class="entity-health-name">${label}</div>
            <div class="entity-health-id">no data</div>
          </div>
        </div>`;
      const dotCls = e.ok ? 'dot-ok' : e.id ? 'dot-error' : 'dot-warn';
      return `
        <div class="entity-health-item">
          <span class="dot ${dotCls}"></span>
          <div class="entity-health-info">
            <div class="entity-health-name">${label}</div>
            <div class="entity-health-id">${e.id || 'not configured'}</div>
            <div class="entity-health-state">${e.state || '—'}</div>
          </div>
        </div>`;
    }).join('');

    // Stat chips
    const chips = [
      inputs.capacity_kwh    != null ? `<span class="chip">&#9889; ${inputs.capacity_kwh} kWh</span>` : '',
      inputs.min_soc_pct     != null ? `<span class="chip">&#128267; Min ${inputs.min_soc_pct}%</span>` : '',
      inputs.lookahead_hours != null ? `<span class="chip">&#9200; ${inputs.lookahead_hours}h ahead</span>` : '',
      inputs.slot_minutes    != null ? `<span class="chip">&#128197; ${inputs.slot_minutes}min slots</span>` : '',
    ].filter(Boolean).join('');

    const aggr = schedAttrs.aggressiveness;
    const aggrPct = aggr != null ? `${Math.round(aggr * 100)}%` : '—';

    return `
      <div class="card">
        <p class="card-title">Configured entities</p>
        <div class="entity-health-grid">
          ${entityGrid || '<p class="no-data">Run the optimizer first to populate entity health.</p>'}
        </div>
        ${chips ? `<div class="stat-chips">${chips}</div>` : ''}
      </div>

      <div class="card">
        <p class="card-title">Optimizer status</p>
        <div class="stat-row">
          <span class="stat-label">State</span>
          <span class="stat-value">${schedAttrs.state || '—'}</span>
        </div>
        <div class="stat-row">
          <span class="stat-label">Solver</span>
          <span class="stat-value">
            <span class="dot ${health.solver_status === 'ok' ? 'dot-ok' : 'dot-error'}"></span>${health.solver_status || '—'}
          </span>
        </div>
        <div class="stat-row">
          <span class="stat-label">SOC sensor</span>
          <span class="stat-value">
            <span class="dot ${health.soc_sensor_available ? 'dot-ok' : 'dot-error'}"></span>
            ${health.soc_sensor_available ? 'Available' : 'Unavailable'}
          </span>
        </div>
        <div class="stat-row">
          <span class="stat-label">Aggressiveness</span>
          <span class="stat-value">${aggrPct}</span>
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

  // ── Debug tab ────────────────────────────────────────────────────────────

  _renderDebug() {
    const health   = this._st(ENTITIES.health)?.attributes || {};
    const diag     = health.diagnostics || {};
    const entities = diag.entities || {};
    const inputs   = diag.inputs   || {};
    const cfg      = diag.config   || {};

    const entityRows = Object.entries({
      'SOC sensor':     entities.soc,
      'Solar forecast': entities.solar_forecast,
      'Consumption':    entities.consumption,
      'Weather':        entities.weather,
    }).map(([label, e]) => {
      if (!e) return `<div class="debug-entity"><span class="debug-label">${label}</span><span class="debug-entity-id">no data — reload integration</span></div>`;
      const notConfigured = !e.id;
      const dotCls   = e.ok ? 'dot-ok' : notConfigured ? 'dot-warn' : 'dot-error';
      const stateCls = e.ok ? 'state-ok' : notConfigured ? 'state-warn' : 'state-error';
      return `
        <div class="debug-entity">
          <span class="dot ${dotCls}"></span>
          <span class="debug-label">${label}</span>
          <span class="debug-entity-id">${e.id || 'not configured'}</span>
          <span class="debug-entity-state ${stateCls}">${e.state}</span>
        </div>`;
    }).join('');

    const liveRows = Object.entries({
      'SOC sensor':     entities.soc?.id,
      'Solar forecast': entities.solar_forecast?.id,
      'Consumption':    entities.consumption?.id,
      'Weather':        entities.weather?.id,
    }).filter(([, id]) => id).map(([label, entityId]) => {
      const live = this._st(entityId);
      const liveState = live ? live.state : 'not found in hass.states';
      const liveOk = live && !['unavailable','unknown','none'].includes(live.state);
      const attrs = live ? Object.entries(live.attributes).slice(0, 5)
        .map(([k, v]) => `${k}: ${typeof v === 'object' ? '(object)' : v}`).join(', ') : '';
      return `
        <div class="debug-entity">
          <span class="dot ${liveOk ? 'dot-ok' : 'dot-error'}"></span>
          <span class="debug-label">${label}</span>
          <div style="flex:1;min-width:0">
            <div style="font-size:12px;color:var(--primary-text-color);font-weight:600">${liveState}</div>
            ${attrs ? `<div style="font-size:10px;color:var(--secondary-text-color);word-break:break-all">${attrs}</div>` : ''}
          </div>
        </div>`;
    }).join('');

    const inputRows = Object.entries({
      'Initial SOC':     inputs.initial_soc_pct    != null ? `${inputs.initial_soc_pct}%` : '—',
      'Slots':           inputs.n_slots             != null ? `${inputs.n_slots} × ${inputs.slot_minutes} min` : '—',
      'Lookahead':       inputs.lookahead_hours     != null ? `${inputs.lookahead_hours} h` : '—',
      'Solar total':     inputs.solar_total_kwh     != null ? `${inputs.solar_total_kwh} kWh (${inputs.solar_nonzero_slots} non-zero slots)` : '—',
      'Load avg':        inputs.load_avg_kw         != null ? `${inputs.load_avg_kw} kW` : '—',
      'Capacity':        inputs.capacity_kwh        != null ? `${inputs.capacity_kwh} kWh` : '—',
      'Min SOC floor':   inputs.min_soc_pct         != null ? `${inputs.min_soc_pct}%` : '—',
      'Forecast format': inputs.forecast_format || '—',
      'Aggressiveness':  inputs.aggressiveness      != null ? `${Math.round(inputs.aggressiveness * 100)}%` : '—',
      'Objective value': inputs.objective_value     != null ? inputs.objective_value.toFixed(4) : '—',
      'Problem size':    inputs.problem_size        != null ? `${inputs.problem_size} vars` : '—',
      'Solve time':      (() => {
        const ms = inputs.solve_time_ms ?? health.solver_duration_ms;
        return ms != null ? `${ms} ms${ms > 5000 ? ' ⚠ SLOW' : ''}` : '—';
      })(),
    }).map(([k, v]) => `
      <div class="stat-row">
        <span class="stat-label">${k}</span>
        <span class="stat-value"><code>${this._escHtml(String(v))}</code></span>
      </div>`).join('');

    const fallbackLabels = {
      conservative_hold: 'Conservative hold (recommended)',
      last_known_good:   'Last known good schedule',
      error_state:       'Error state (raise error on failure)',
    };
    const cfgRows = Object.entries({
      'Free import start':   cfg.free_import_start  || 'not set',
      'Free import end':     cfg.free_import_end    || 'not set',
      'Export bonus start':  cfg.export_bonus_start || 'not set',
      'Export bonus end':    cfg.export_bonus_end   || 'not set',
      'Bridge fallback':     cfg.bridge_fallback_time || '—',
      'Fallback mode':       cfg.fallback_mode ? (fallbackLabels[cfg.fallback_mode] || cfg.fallback_mode) : '—',
    }).map(([k, v]) => `
      <div class="stat-row">
        <span class="stat-label">${k}</span>
        <span class="stat-value"><code>${this._escHtml(String(v))}</code></span>
      </div>`).join('');

    const allEntities = Object.entries(this._hass?.states || {})
      .filter(([id]) => id.startsWith('sensor.battery_optimiser') || id.startsWith('button.battery_optimiser'))
      .map(([id, st]) => {
        const ok = !['unavailable','unknown','none'].includes(st.state);
        return `
          <div class="debug-entity">
            <span class="dot ${ok ? 'dot-ok' : 'dot-error'}"></span>
            <span class="debug-entity-id">${id}</span>
            <span class="debug-entity-state ${ok ? 'state-ok' : 'state-error'}">${st.state}</span>
          </div>`;
      }).join('') || '<p class="no-data">No battery_optimizer entities found in hass.states.</p>';

    const noData = !diag.entities;

    return `
      ${noData ? `<div class="alert alert-warn">⚠ No diagnostic data yet — the optimizer has not completed a run.</div>` : ''}

      <div class="card">
        <p class="card-title">Configured entity health</p>
        <p style="font-size:12px;color:var(--secondary-text-color);margin:0 0 8px">
          Each entity is checked at the start of every optimization run.
          <strong>not_found_in_ha</strong> means the entity ID is wrong or the device is offline.
          <strong>unavailable</strong> means HA found the entity but the device isn't responding.
        </p>
        ${entityRows || '<p class="no-data">No entity data — run an optimization first.</p>'}
      </div>

      <div class="card">
        <p class="card-title">Live entity states (from hass.states)</p>
        ${liveRows || '<p class="no-data">No configured entity IDs found.</p>'}
      </div>

      <div class="card">
        <p class="card-title">Last optimization inputs</p>
        ${inputRows || '<p class="no-data">No input data — optimization has not run yet.</p>'}
      </div>

      <div class="card">
        <p class="card-title">Tariff configuration</p>
        ${cfgRows}
      </div>

      <div class="card">
        <p class="card-title">All battery_optimizer entities</p>
        ${allEntities}
      </div>

      ${this._renderLogViewer()}
      ${this._renderRawSchedule()}
    `;
  }

  _renderLogViewer() {
    return `
      <div class="card">
        <p class="card-title">HA log viewer</p>
        <p style="font-size:12px;color:var(--secondary-text-color);margin:0 0 10px">
          Fetches <code>/api/error_log</code> and filters for <code>battery_optimis</code> entries. Shows last 100 matching lines.
        </p>
        <div class="btn-row" style="margin-top:0">
          <button class="btn-secondary" id="btn-fetch-logs">Fetch Logs</button>
          <button class="btn-secondary" id="btn-copy-logs">Copy</button>
        </div>
        <pre class="log-pre" id="log-pre" style="display:none"></pre>
      </div>`;
  }

  _renderRawSchedule() {
    const schedule = this._st(ENTITIES.schedule);
    const allSlots = schedule?.attributes?.slots || [];
    const decSlots = schedule?.attributes?.decision_slots || [];
    const summary  = `${decSlots.length} decision slots, ${allSlots.length} total slots`;

    return `
      <div class="card">
        <p class="card-title">Raw schedule JSON</p>
        <p style="font-size:12px;color:var(--secondary-text-color);margin:0 0 8px">${summary}</p>
        <div class="btn-row" style="margin-top:0;margin-bottom:8px">
          <button class="btn-secondary" id="btn-copy-raw">Copy JSON</button>
        </div>
        <details>
          <summary>Show full schedule attributes</summary>
          <pre class="raw-pre" id="raw-schedule-pre">${this._escHtml(JSON.stringify(schedule?.attributes || {}, null, 2))}</pre>
        </details>
      </div>`;
  }

  // ── Event binding ────────────────────────────────────────────────────────

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
    bind('btn-reset-corrections', () => this._callService('battery_optimizer', 'reset_corrections'));

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

    // Log viewer - Helper function to fetch and format logs
    const fetchLogs = async () => {
      const btn = root.getElementById('btn-fetch-logs');
      const pre = root.getElementById('log-pre');
      if (!btn || !pre) return;

      btn.disabled = true;
      btn.textContent = 'Fetching...';
      pre.style.display = 'block';
      pre.textContent = 'Loading...';

      try {
        // /api/error_log returns plain text — use fetchWithAuth to avoid JSON parse errors
        const resp = await this._hass.fetchWithAuth('/api/error_log');
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const text = await resp.text();
        const lines = text.split('\n').filter(l => l.trim());

        // Filter for battery_optimizer entries (case-insensitive)
        const filteredLines = lines.filter(l => 
          String(l).toLowerCase().includes('battery_optimis')
        );

        if (filteredLines.length === 0) {
          pre.innerHTML = '<span style="color:var(--secondary-text-color)">No battery_optimizer log entries found.</span>';
        } else {
          const last100 = filteredLines.slice(-100);
          pre.innerHTML = last100.map(line => {
            let cls = 'log-debug';
            const str = String(line).toUpperCase();
            if (str.includes('ERROR') || str.includes('EXCEPTION'))   cls = 'log-error';
            else if (str.includes('WARNING') || str.includes('WARN')) cls = 'log-warn';
            else if (str.includes('INFO'))    cls = 'log-info';
            return `<span class="${cls}">${this._escHtml(line)}</span>`;
          }).join('\n');
          pre.scrollTop = pre.scrollHeight;
        }

        btn.textContent = `Refresh (${filteredLines.length} lines)`;
      } catch (e) {
        const errorMsg = e.message || String(e);
        pre.innerHTML = `<span class="log-error">Error fetching logs: ${this._escHtml(errorMsg)}<br><small>Make sure the integration is loaded and HA has write permissions for log files.</small></span>`;
        btn.textContent = 'Fetch Logs';
      }

      btn.disabled = false;
    };

    bind('btn-fetch-logs', fetchLogs);

    bind('btn-copy-logs', () => {
      const pre = root.getElementById('log-pre');
      if (pre && navigator.clipboard) navigator.clipboard.writeText(pre.textContent);
    });

    bind('btn-copy-raw', () => {
      const pre = root.getElementById('raw-schedule-pre');
      if (pre && navigator.clipboard) navigator.clipboard.writeText(pre.textContent);
    });
  }
}

customElements.define('battery-optimizer-panel', BatteryOptimizerPanel);
