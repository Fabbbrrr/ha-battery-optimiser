# Battery Optimizer — Example Automations

These ready-to-use automation YAML snippets show how to wire the Battery Optimizer
sensors and events into Home Assistant automations for notifications and inverter control.

---

## 1. Energy Security Risk Notification

Fires a mobile push when the optimizer's energy security score drops below 60%
(i.e., the battery may not have enough charge to last until the next solar/import window).

```yaml
alias: "Battery Optimizer — Low Energy Security Alert"
trigger:
  - platform: template
    value_template: >
      {{ state_attr('sensor.battery_optimizer_health', 'energy_security_score') | float(1) < 0.6 }}
condition:
  - condition: state
    entity_id: sensor.battery_optimizer_optimizer_state
    state: running
action:
  - service: notify.mobile_app_your_phone
    data:
      title: "⚠ Battery Security Risk"
      message: >
        Energy security score is
        {{ (state_attr('sensor.battery_optimizer_health', 'energy_security_score') | float * 100) | round }}%.
        Bridge target: {{ state_attr('sensor.battery_optimizer_health', 'bridge_to_time') }}.
mode: single
```

---

## 2. Stale Forecast Data Notification

Alerts when the solar forecast hasn't updated in over 2 hours.

```yaml
alias: "Battery Optimizer — Stale Forecast Alert"
trigger:
  - platform: template
    value_template: >
      {{ state_attr('sensor.battery_optimizer_health', 'forecast_staleness_seconds') | int(0) > 7200 }}
action:
  - service: notify.mobile_app_your_phone
    data:
      title: "☁ Forecast Data Stale"
      message: >
        Solar forecast hasn't updated in
        {{ (state_attr('sensor.battery_optimizer_health', 'forecast_staleness_seconds') | int / 3600) | round(1) }} hours.
        Optimizer is running in fallback mode.
mode: single
```

---

## 3. Set Inverter Export Limit from Schedule (Solis / SolisModbus)

Reads the current slot's recommended power and sets the Solis inverter export limit
accordingly. Run this on a time-based trigger aligned to your slot size (e.g. every 30 min).

```yaml
alias: "Battery Optimizer — Apply Export Limit to Solis"
trigger:
  - platform: time_pattern
    minutes: "/30"
condition:
  - condition: template
    value_template: >
      {{ state_attr('sensor.battery_optimizer_schedule', 'slots') | length > 0 }}
  - condition: state
    entity_id: sensor.battery_optimizer_optimizer_state
    state: running
action:
  - variables:
      current_slot: >
        {% set slots = state_attr('sensor.battery_optimizer_schedule', 'slots') %}
        {% set now = now().isoformat() %}
        {% for slot in slots %}
          {% if slot.start <= now < slot.end %}
            {{ slot }}
          {% endif %}
        {% endfor %}
      action: "{{ current_slot.action | default('hold') }}"
      power_kw: "{{ current_slot.power_kw | default(0) | abs }}"

  # Set Solis export limit (replace with your actual Solis entity)
  - choose:
      - conditions:
          - condition: template
            value_template: "{{ action == 'export' }}"
        sequence:
          - service: number.set_value
            target:
              entity_id: number.solis_export_power_limit  # adjust to your entity
            data:
              value: "{{ [power_kw * 1000, 5000] | min | int }}"  # watts, cap at 5kW

      - conditions:
          - condition: template
            value_template: "{{ action in ['hold', 'discharge'] }}"
        sequence:
          - service: number.set_value
            target:
              entity_id: number.solis_export_power_limit
            data:
              value: 0
mode: single
```

---

## 4. React to Schedule Changed Event

Triggers whenever the optimizer changes its recommendation for an imminent slot
(next 2 hours). Useful for immediately applying the new export limit.

```yaml
alias: "Battery Optimizer — Apply Schedule on Change"
trigger:
  - platform: event
    event_type: battery_optimizer_schedule_changed
condition: []
action:
  - variables:
      new_action: "{{ trigger.event.data.new_action }}"
      new_power: "{{ trigger.event.data.new_power_kw | float }}"
      slot_start: "{{ trigger.event.data.slot_start }}"
      reason: "{{ trigger.event.data.reason }}"

  - service: notify.mobile_app_your_phone
    data:
      title: "Battery Schedule Updated"
      message: >
        {{ slot_start[11:16] }}: {{ trigger.event.data.old_action }} → {{ new_action }}
        ({{ new_power | round(1) }} kW) — {{ reason }}

  # Re-apply the new export limit immediately
  - service: automation.trigger
    target:
      entity_id: automation.battery_optimizer_apply_export_limit_to_solis
mode: queued
max: 3
```

---

## 5. EV Plug-In → Force Recalculate

When your EV starts charging, the home load changes significantly. This triggers an
immediate schedule recalculation so the optimizer accounts for the extra demand.

```yaml
alias: "Battery Optimizer — Recalculate on EV Plug-In"
trigger:
  - platform: state
    entity_id: sensor.ev_charger_status  # adjust to your EV charger entity
    to: "charging"
action:
  - service: battery_optimizer.recalculate_now
mode: single
```

---

## 6. Override to Hold During Peak Load Events

During known high-consumption events (e.g., oven + AC running), force the battery to
hold and not export so it's available to cover the spike.

```yaml
alias: "Battery Optimizer — Hold During Peak Load"
trigger:
  - platform: numeric_state
    entity_id: sensor.grid_power  # your grid power sensor
    above: 4000                   # watts — adjust threshold
    for:
      minutes: 5
action:
  - service: battery_optimizer.override_slot
    data:
      action: hold
      duration_minutes: 60
      # power_kw omitted — optimizer sets to 0
mode: single
```

---

## 7. Morning Summary Notification

Each morning, send a summary of the optimizer's plan for the day including
estimated revenue and the bridge-to time.

```yaml
alias: "Battery Optimizer — Morning Summary"
trigger:
  - platform: time
    at: "07:00:00"
condition:
  - condition: state
    entity_id: sensor.battery_optimizer_optimizer_state
    state: running
action:
  - service: notify.mobile_app_your_phone
    data:
      title: "Battery Plan for Today"
      message: >
        Est. export revenue: ${{ state_attr('sensor.battery_optimizer_health', 'estimated_export_revenue') | round(2) }}
        Security: {{ (state_attr('sensor.battery_optimizer_health', 'energy_security_score') | float * 100) | round }}%
        Bridge target: {{ state_attr('sensor.battery_optimizer_health', 'bridge_to_time') | default('N/A') }}
        Forecast confidence: {{ (state_attr('sensor.battery_optimizer_health', 'forecast_confidence') | float * 100) | round }}%
mode: single
```

---

## Available Sensors Reference

| Entity | State | Key Attributes |
|--------|-------|----------------|
| `sensor.battery_optimizer_schedule` | Current slot action | `slots[]` (full schedule), `aggressiveness` |
| `sensor.battery_optimizer_health` | `ok` / `degraded` / `error` | `estimated_export_revenue`, `energy_security_score`, `forecast_confidence`, `bridge_to_time`, `bridge_to_source`, `solver_duration_ms`, `last_recalculation`, `fallback_mode_active` |
| `sensor.battery_optimizer_optimizer_state` | `running` / `paused` / `error` / `fallback` | — |

## Slot Attributes

Each item in `state_attr('sensor.battery_optimizer_schedule', 'slots')`:

| Key | Type | Description |
|-----|------|-------------|
| `start` | ISO datetime | Slot start time |
| `end` | ISO datetime | Slot end time |
| `action` | string | `charge` / `discharge` / `hold` / `export` |
| `power_kw` | float | Recommended power (kW) |
| `projected_soc` | float | Battery SOC at end of slot (%) |
| `expected_solar_kwh` | float | Solar forecast for this slot |
| `expected_consumption_kwh` | float | Load estimate for this slot |
| `net_energy_kwh` | float | Net battery energy change |
| `is_historical` | bool | True for past slots |
| `is_override` | bool | True when manually overridden |
| `actual_soc` | float\|null | Recorded actual SOC (historical only) |
| `actual_solar_kwh` | float\|null | Recorded actual solar (historical only) |
| `actual_consumption_kwh` | float\|null | Recorded actual consumption (historical only) |
