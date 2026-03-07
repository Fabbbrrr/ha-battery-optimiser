# Battery Optimiser for Home Assistant

LP-optimized battery charge/discharge/export scheduling. Maximizes export revenue
during peak tariff windows while guaranteeing your battery has enough energy to last
overnight — accounting for solar forecasts, weather, learned consumption patterns,
and multi-day lookahead.

**Works with any inverter** that exposes sensors in Home Assistant (Solis, Huawei,
Enphase, SunGrow, Fronius, GoodWe, etc.).

---

## How does it work?

> **Within 1–2 minutes of installation you have a working schedule.** The optimizer runs immediately, using your tariff configuration and a consumption baseline. It then trains on your HA recorder history in the background — once trained, every recalculation uses your real weekday/weekend usage patterns.

The core loop every 30 minutes:

```
Read SOC + Solar forecast + Weather → Run LP solver → Update schedule sensors
```

**→ [Full explanation: docs/how-it-works.md](docs/how-it-works.md)**

Covers the startup sequence, the learning timeline (when to expect what), what the schedule action states mean, how to read the logs, and how to troubleshoot common problems.

---

## Features

- **LP optimizer** (scipy) — mathematically optimal schedules, not heuristics
- **Inverter-agnostic** — map any HA sensor entities; no hardcoded hardware support
- **Multi-period TOU tariffs** — export bonus windows, free import, peak rates, optional grid charging
- **Multi-day lookahead** — conserves battery when 2+ rainy days ahead
- **Forecast-adaptive SOC floor** — hard minimum + dynamic overnight reserve calculation
- **Bridge-to logic** — targets whichever rescue arrives first: solar generation or free import window
- **Learned consumption profiles** — weekday/weekend patterns from HA recorder history
- **Weather confidence modifier** — cloud cover, precipitation, and temperature all adjust the model
- **Planned-vs-actual tracking** — records real SOC/solar/consumption at each slot boundary
- **Interactive Lovelace card** — timeline, SOC curve, slot override dialog, aggressiveness slider
- **Schedule-changed events** — fire when imminent slots change, so automations react instantly

---

## Requirements

- Home Assistant 2024.1.0 or newer
- Python dependency: `scipy` (installed automatically by HA)
- A solar forecast integration: [Forecast.Solar](https://www.home-assistant.io/integrations/forecast_solar/) or [Solcast](https://github.com/BJReplay/ha-solcast-solar) (auto-detected), or any sensor exposing daily kWh
- A battery/inverter exposing a SOC sensor in HA

---

## Installation

### Option A — HACS (Recommended)

1. Open HACS in your Home Assistant sidebar
2. Go to **Integrations** → click the **⋮** menu → **Custom repositories**
3. Add `https://github.com/Fabbbrrr/ha-battery-optimiser` as an **Integration**
4. Search for **Battery Optimizer** and click **Download**
5. Restart Home Assistant
6. Go to **Settings → Devices & Services → Add Integration** → search **Battery Optimizer**

### Option B — Manual Installation

1. Download or clone this repository
2. Copy the `custom_components/battery_optimizer/` directory into your HA
   `config/custom_components/` directory:
   ```
   config/
   └── custom_components/
       └── battery_optimizer/      ← copy this whole folder here
           ├── __init__.py
           ├── manifest.json
           ├── config_flow.py
           ├── coordinator.py
           ├── optimizer.py
           ├── forecast_parser.py
           ├── bridge_calculator.py
           ├── weather_modifier.py
           ├── consumption_learner.py
           ├── events.py
           ├── tracker.py
           ├── sensor.py
           ├── services.py
           ├── services.yaml
           ├── const.py
           ├── translations/
           │   └── en.json
           └── www/
               └── battery-optimizer-card.js
   ```
3. Restart Home Assistant
4. Go to **Settings → Devices & Services → Add Integration** → search **Battery Optimizer**

### Installing on a local HA instance (WSL / development)

If your HA config directory is accessible from your dev machine (e.g. via Samba share,
SSH, or direct filesystem access in WSL):

```bash
# Adjust this path to your HA config directory
HA_CONFIG="/mnt/c/Users/yourname/homeassistant"   # WSL example
# or
HA_CONFIG="/home/pi/homeassistant"                  # Raspberry Pi SSH

# Copy the integration
cp -r /home/oicir/workspace/custom_components/battery_optimizer \
      "$HA_CONFIG/custom_components/"

# Restart HA (if running as a service)
ssh pi@homeassistant.local "ha core restart"
# or via the HA UI: Settings → System → Restart
```

---

## Setup Wizard

The integration uses a guided multi-step wizard. Required fields are minimal — you
can skip optional steps and configure them later via **Options**.

### Step 1 — Battery (required)
| Field | Description |
|-------|-------------|
| Battery SOC sensor | The HA entity reporting your battery's state of charge (%) |
| Battery capacity (kWh) | Usable energy capacity of your battery |
| Minimum SOC floor (%) | The optimizer will **never** let the battery drop below this |

### Step 2 — Export Window (required)
| Field | Description |
|-------|-------------|
| Export bonus start / end | Your retailer's bonus export window (e.g. 18:00–20:00) |
| Export bonus rate ($/kWh) | The premium rate paid during the bonus window |
| Standard export rate | Rate paid outside the bonus window (can be 0) |
| Standard import rate | What you pay for grid electricity |

### Step 3 — Solar Forecast (required)
Select the HA sensor providing your solar forecast. **Forecast.Solar** and **Solcast**
formats are auto-detected. Any other sensor exposing a daily kWh value also works.

### Step 4 — Additional Tariffs (optional)
Configure free import windows (e.g. 11:00–14:00 at $0/kWh), peak import rates,
and enable optional grid-charging during cheap windows.

### Step 5 — Home Consumption (optional)
Select a home energy sensor for HA recorder-based load learning. Without this,
the optimizer uses your configured baseline consumption rate.

### Step 6 — Weather (optional)
Select a weather entity. Improves accuracy by adjusting solar confidence based on
cloud cover, precipitation, and temperature-driven load changes.

### Step 7 — Inverter Rate Limits (optional)
Set max charge, discharge, and export power limits for your inverter.
Defaults to 5 kW (suitable for most residential inverters including Solis).

---

## Configuration Options

All settings are accessible after setup via **Settings → Devices & Services →
Battery Optimizer → Configure**.

| Option | Default | Description |
|--------|---------|-------------|
| Aggressiveness | 0.7 | 0 = maximize battery reserve, 1 = maximize export revenue |
| Slot granularity | 30 min | Time resolution of the schedule (15 / 30 / 60 min) |
| Lookahead | 48 hours | Rolling optimization window length |
| Recalculation interval | 30 min | How often to re-optimize |
| Bridge-to fallback time | 11:00 | Target time if solar forecast can't determine when rescue arrives |
| Fallback mode | Conservative hold | Behaviour when data is unavailable |
| Solver timeout | 30 s | Max time for the LP solver (reduce on slow hardware) |
| Data retention | 90 days | How long planned-vs-actual records are kept |

---

## Entities Created

### Core sensors

| Entity | State | Description |
|--------|-------|-------------|
| `sensor.battery_optimizer_schedule` | `charge` / `discharge` / `hold` / `export` | Current recommended action. Full 48-slot schedule in attributes. |
| `sensor.battery_optimizer_health` | `ok` / `degraded` / `error` | Solver metrics, revenue estimate, security score in attributes. |
| `sensor.battery_optimizer_optimizer_state` | `running` / `paused` / `error` / `fallback` | Overall optimizer state. |

### Scalar sensors (graphable, automation-friendly)

| Entity | Unit | Description |
|--------|------|-------------|
| `sensor.battery_optimizer_current_power` | kW | Power command for the current slot (+ = charge, − = discharge) |
| `sensor.battery_optimizer_projected_soc` | % | Expected battery SOC at end of the current slot |
| `sensor.battery_optimizer_forecast_confidence` | % | Weather-adjusted confidence in the solar forecast |
| `sensor.battery_optimizer_energy_security_score` | % | How well the plan covers the energy-security bridge point |
| `sensor.battery_optimizer_estimated_export_revenue` | — | Estimated revenue from this optimization cycle |
| `sensor.battery_optimizer_next_action` | text | What the next schedule slot plans to do |
| `sensor.battery_optimizer_soc_at_free_charge_start` | % | Projected SOC when your cheap/free import window begins |
| `sensor.battery_optimizer_learning_status` | `trained` / `learning` / `not_started` | Consumption learner status. Attributes include observation count, days covered, profile types. |

### Button entity

| Entity | Description |
|--------|-------------|
| `button.battery_optimizer_retrain_learning_data` | Triggers a full re-train from recorder history |

### Schedule sensor attributes

```yaml
slots:
  - start: "2025-01-15T18:00:00+11:00"
    end:   "2025-01-15T18:30:00+11:00"
    action: export          # charge | discharge | hold | export
    power_kw: 3.2           # recommended power level
    projected_soc: 72.4     # % at end of slot
    expected_solar_kwh: 0.0
    expected_consumption_kwh: 0.25
    net_energy_kwh: -1.6
    is_override: false
    is_historical: false
aggressiveness: 0.5
state: running
```

Historical slots also include:
```yaml
    is_historical: true
    actual_soc: 69.8
    actual_solar_kwh: 0.0
    actual_consumption_kwh: 0.31
```

---

## Services

| Service | Description |
|---------|-------------|
| `battery_optimizer.recalculate_now` | Force an immediate schedule recalculation |
| `battery_optimizer.set_aggressiveness` | Change aggressiveness at runtime (`aggressiveness: 0.0–1.0`) |
| `battery_optimizer.override_slot` | Force a specific action for a duration (`action`, `duration_minutes`, optional `power_kw`, optional `start`) |
| `battery_optimizer.pause` | Pause optimizer — all slots set to hold, state persists across restart |
| `battery_optimizer.resume` | Resume from paused state |
| `battery_optimizer.retrain_learner` | Re-train consumption model from full recorder history, then recalculate |

---

## Events

### `battery_optimizer_schedule_changed`
Fired when any slot within the **next 2 hours** changes its recommended action or power.

```yaml
event_data:
  slot_start: "2025-01-15T18:00:00+11:00"
  slot_end:   "2025-01-15T18:30:00+11:00"
  old_action: "hold"
  new_action: "export"
  old_power_kw: 0.0
  new_power_kw: 3.2
  projected_soc: 72.4
  reason: "action_changed_hold_to_export"
```

---

## Lovelace Card

The integration includes a custom interactive card. Register it after installation:

### Register the card resource

In **Settings → Dashboards → ⋮ → Resources**, add:

| URL | Type |
|-----|------|
| `/battery_optimizer_static/battery-optimizer-card.js` | JavaScript Module |

Or add to your `configuration.yaml`:

```yaml
lovelace:
  resources:
    - url: /battery_optimizer_static/battery-optimizer-card.js
      type: module
```

Restart HA after adding the resource.

### Add to your dashboard

```yaml
type: custom:battery-optimizer-card
entity: sensor.battery_optimizer_schedule
health_entity: sensor.battery_optimizer_health
state_entity: sensor.battery_optimizer_optimizer_state
learning_entity: sensor.battery_optimizer_learning_status
title: Battery Optimiser
show_slots: 24    # number of slots to display in timeline
```

### Card features

The card has **3 tabs**:

**Schedule** — color-coded timeline, SOC curve (planned vs actual), aggressiveness slider, Recalculate and Pause/Resume controls. Tap any slot to open the override dialog.

**Analytics** — planned vs actual SOC accuracy chart, solver health metrics, consumption learning status (observation count, days covered, profiles, temperature model), and a **Retrain Now** button.

**Config** — key readings (forecast confidence, energy security score, SOC at charge window start), optimizer settings summary, and learning configuration.

An **alerts bar** at the top flags problems immediately: fallback mode active, SOC sensor unavailable, or learning not yet trained.

---

## Example Automations

See [`docs/example_automations.md`](docs/example_automations.md) for copy-paste automation
YAML for:

- Energy security risk push notification
- Stale forecast alert
- Setting Solis inverter export limit from schedule
- Reacting to `battery_optimizer_schedule_changed` event
- EV plug-in triggering recalculation
- Forcing hold during peak load events
- Morning daily summary notification

---

## Troubleshooting

### Optimizer stays in fallback mode
- Check `sensor.battery_optimizer_health` attributes for `solver_status`
- Ensure `scipy` is installed: in HA, go to **Developer Tools → Template** and run `{{ integration_loaded('battery_optimizer') }}`
- Increase `solver_timeout_seconds` in Options if on slow hardware (Raspberry Pi)

### No schedule slots appearing
- Verify the SOC entity is available and returning a numeric value
- Verify the solar forecast entity is not `unavailable`
- Check HA logs for `battery_optimizer` errors: **Settings → System → Logs**

### Forecast.Solar not auto-detected
- Ensure your Forecast.Solar entity has `watts` or `wh_period` in its attributes
- If not, set `solar_forecast_format: forecast_solar` manually in Options

### Solcast not auto-detected
- Ensure your Solcast entity has `detailedForecast` or `forecasts` in its attributes
- Latest Solcast HA integration versions use `detailedForecast`

### Card not showing
- Ensure the resource URL is exactly `/battery_optimizer_static/battery-optimizer-card.js`
- Clear your browser cache after adding the resource
- Check the browser console for JS errors

---

## Architecture

```
coordinator.py          ← orchestrates everything, DataUpdateCoordinator
├── forecast_parser.py  ← Forecast.Solar / Solcast / generic kWh parsers
├── bridge_calculator.py← dynamic bridge-to-point + energy security score
├── weather_modifier.py ← solar confidence + temperature load adjustment
├── consumption_learner.py ← HA recorder history + exponential decay profiles
├── optimizer.py        ← scipy LP formulation + async execution
├── tracker.py          ← planned-vs-actual polls at slot boundaries
├── events.py           ← schedule_changed event detection + firing
├── services.py         ← HA service handlers
└── sensor.py           ← 3 sensor entities (schedule / health / state)
```

---

## Contributing

Issues and PRs welcome. When reporting a bug please include:
- HA version
- Integration version
- Contents of `sensor.battery_optimizer_health` attributes
- Relevant lines from HA logs (search for `battery_optimizer`)
