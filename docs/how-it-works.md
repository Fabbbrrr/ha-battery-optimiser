# How Battery Optimiser Works

This document explains the full lifecycle of the integration — from the moment you install it, through its learning phase, to its steady-state operation. It also covers what to expect at each stage and how to diagnose problems using the logs.

---

## Table of contents

- [The startup sequence](#the-startup-sequence)
- [The optimization cycle](#the-optimization-cycle)
- [The learning timeline](#the-learning-timeline)
- [What the schedule actually means](#what-the-schedule-actually-means)
- [Reading the logs](#reading-the-logs)
- [Troubleshooting common problems](#troubleshooting-common-problems)

---

## The startup sequence

When Home Assistant loads the integration (on HA start, or after you install/reload it), the following happens in order:

```
1. Coordinator initializes
   └── Restores saved state from .storage/ (aggressiveness, optimizer state, learned profiles)

2. async_setup() runs
   ├── Sets up entity trackers for SOC and forecast sensors
   ├── Kicks off background task: train consumption learner from recorder history
   └── Triggers the first optimization immediately

3. First optimization completes (within ~30–60 seconds)
   └── Sensors are populated, card shows a schedule

4. Background: consumption learner finishes training
   └── Learning Status sensor flips to "trained"
   └── Next recalculation uses real usage patterns instead of baseline
```

**You have a working schedule within 1–2 minutes of installation.** It uses your configured baseline consumption rate until the learner finishes training — usually a few seconds if you have recorder history, or gradually as data accumulates if you're starting fresh.

---

## The optimization cycle

Every 30 minutes (configurable), or whenever the solar forecast entity changes, the coordinator runs a full optimization:

```
① Read inputs
   ├── SOC: read from your configured sensor (fallback: 50% if unavailable)
   ├── Solar forecast: parse Forecast.Solar / Solcast / generic kWh sensor
   ├── Weather forecast: adjust solar confidence, temperature load modifier
   └── Consumption profile: learned hourly patterns, or flat baseline

② Compute the bridge point
   └── "When is the next energy rescue?" — solar generation or free import window
       The optimizer must ensure enough charge to reach this point.

③ Build the tariff schedule
   └── Per-slot import and export rates based on your configured windows

④ Run the LP solver
   └── Finds the mathematically optimal sequence of charge/discharge/hold/export
       across the full lookahead window (default: 48 hours)

⑤ Post-process
   ├── Stamp slot datetimes (ISO, timezone-aware)
   ├── Apply any active manual overrides
   ├── Enrich historical slots with actual SOC/solar/consumption readings
   ├── Fire schedule_changed events for imminent slot changes
   └── Schedule planned-vs-actual polls at each slot boundary

⑥ Update all sensors
   └── Schedule, Health, Optimizer State, and all scalar sensors refresh
```

**Triggers that cause an early recalculation** (don't wait 30 minutes):
- The solar forecast entity changes state (Solcast and Forecast.Solar push updates)
- You press "Recalculate Now" in the card or call `battery_optimizer.recalculate_now`

---

## The learning timeline

The consumption learner builds time-of-day profiles from your recorder history. Here's what to expect:

| Time since install | Learning status | What the optimizer uses |
|---|---|---|
| 0–2 min | `not_started` | Your configured baseline kW (flat, all hours) |
| 2–10 min | `learning` or `trained` | Historical recorder data (whatever HA has) |
| 7+ days of data | `trained` | Weekday vs weekend hourly profiles |
| 30+ days of data | `trained` | Stable profiles + temperature model (if weather entity configured) |
| 90+ days of data | `trained` | Seasonal patterns captured in the model |

**The tariff optimisation is fully functional from minute one.** Even on baseline consumption, the optimizer correctly schedules charging, holding, and exporting around your tariff windows. The learning phase improves *how much* energy is predicted to be needed in each slot — it doesn't affect *when* to export or *when* to charge.

### Manually triggering a retrain

Hit the **Retrain Learning Data** button in the Analytics tab of the Lovelace card, or call:

```yaml
service: battery_optimizer.retrain_learner
```

Do this after:
- Adding a consumption sensor after initial setup
- A long gap where the recorder wasn't collecting data
- Significantly changing your home's energy profile (new appliance, EV, heat pump)

---

## What the schedule actually means

The `sensor.battery_optimizer_schedule` state is the **recommended action for the current time slot**:

| State | Meaning |
|---|---|
| `charge` | Charge the battery now (from solar surplus or grid if grid-charging enabled) |
| `discharge` | Discharge the battery to cover home load |
| `export` | Discharge the battery to export power to the grid (bonus window) |
| `hold` | Do nothing — maintain current SOC |

The `power_kw` attribute in each slot is the **recommended power level** for your inverter. Your automation reads `sensor.battery_optimizer_schedule` and the current slot's `power_kw` to set the inverter mode.

See [`example_automations.md`](example_automations.md) for copy-paste automation YAML.

### Energy security score

The **Energy Security Score** (0–100%) answers: *"If we follow this plan, will the battery have enough charge to reach the next rescue point?"*

- **80–100%** — plan is solid, battery will have ample reserve
- **50–79%** — moderate risk, consider increasing aggressiveness or SOC floor
- **< 50%** — battery may run low before solar generation or cheap import arrives

The "bridge-to" point shown in the card is the target time the optimizer is defending: whichever comes first from the current slot — the start of your free import window, or the next solar generation window.

---

## Reading the logs

The integration logs all significant events at `INFO` and `WARNING` level under the logger name `custom_components.battery_optimizer`.

### Enable debug logging (optional)

Add to your `configuration.yaml` for full diagnostic output:

```yaml
logger:
  default: warning
  logs:
    custom_components.battery_optimizer: debug
```

Restart HA after adding this. Remove it once you've diagnosed your issue — debug logging is verbose.

### What each log line means

**On each optimization run, the integration logs a diagnostic summary at INFO level:**

```
battery_optimizer: Optimization starting — SOC: 74.2% (sensor.battery_soc ✓)
battery_optimizer: Solar: 48 slots parsed from sensor.solcast_pv_forecast_today (solcast format)
battery_optimizer: Consumption: learned profile (weekday_weekend, 847 observations, 29.4 days)
battery_optimizer: Weather: weather.home ✓ — forecast confidence: 78%
battery_optimizer: Bridge-to: 06:30 (next_solar) — energy needed: 3.2 kWh
battery_optimizer: Schedule: 48 slots, solve 23ms — action=export, SOC 72%→68%
```

**Warning-level messages indicate something that needs attention:**

| Log message | What it means | How to fix |
|---|---|---|
| `SOC sensor unavailable — using 50% fallback` | Your SOC entity is `unavailable` or `unknown` in HA | Check the entity in Developer Tools → Template: `{{ states('your_entity') }}` |
| `Solar forecast entity not configured` | No forecast entity was set in the wizard | Add it under Settings → Configure |
| `No slots parsed from forecast entity` | Forecast entity exists but has no forecast data in attributes | Check the entity's attributes in Developer Tools → States |
| `Consumption learner not trained — using baseline X kW` | No recorder history or no consumption entity | Hit Retrain Now in the card's Analytics tab |
| `No recorder stats for entity — using baseline` | HA recorder has no statistics for your consumption sensor | Ensure the entity is set up as an energy sensor with long-term statistics enabled |
| `Optimization failed: <error>` | LP solver or data preparation threw an exception | Full error follows — check the next log line |
| `Fallback mode active: <mode>` | The optimizer entered fallback due to the error above | See the `solver_status` in the Health sensor attributes |
| `LP solver did not converge: <reason>` | The optimizer can't find a valid schedule | Usually caused by conflicting constraints — check SOC floor vs capacity |

### View logs in Home Assistant

1. Go to **Settings → System → Logs**
2. Click **Load full logs**
3. Search for `battery_optimizer` in the log viewer

Or from the terminal:

```bash
# Tail logs on a Raspberry Pi / HA OS
journalctl -f -u homeassistant | grep battery_optimizer

# Or read the log file directly
grep battery_optimizer /config/home-assistant.log | tail -50
```

### What the Health sensor tells you

The `sensor.battery_optimizer_health` entity's **attributes** are the fastest way to see what's wrong without digging through logs:

```yaml
solver_status: "ok"              # or "error: <message>" or "paused"
soc_sensor_available: true       # false = SOC entity is unavailable
forecast_staleness_seconds: 120  # how old the last forecast data was
fallback_mode_active: false      # true = something failed, using fallback
energy_security_score: 0.87      # 0–1, how well the plan covers bridge point
forecast_confidence: 0.72        # 0–1, weather-adjusted solar trust
last_recalculation: "2025-01-15T18:30:00+11:00"
solver_duration_ms: 23
```

The state of `sensor.battery_optimizer_health` is a quick summary:
- `ok` — all good
- `degraded` — running in fallback mode (last known good schedule or conservative hold)
- `error` — optimization failed, check `solver_status` attribute

---

## Troubleshooting common problems

### "All sensors show unavailable"

The integration is in fallback/error mode. In order of likelihood:

1. **Reload the integration** — especially after an update. Go to Settings → Devices & Services → Battery Optimiser → ⋮ → Reload.
2. **Check the SOC sensor** — run `{{ states('your_soc_entity') }}` in Developer Tools → Template. Must return a number, not `unavailable`.
3. **Check `solver_status`** in the Health sensor attributes — this contains the exact error message from the last failed run.
4. **Check HA logs** — search for `battery_optimizer` to find the root cause.

### "Learning Status is 'not_started' or 'not_trained'"

1. Ensure a consumption entity is configured in the wizard (Step 5 → or Options → Entity Mappings)
2. Ensure the consumption entity has **long-term statistics enabled** in HA (it needs to be an energy sensor, not just a state sensor)
3. Check logs for `No recorder stats for entity` — the entity may not have statistics in the recorder yet
4. Hit **Retrain Now** in the card's Analytics tab
5. Check logs for `ConsumptionLearner trained on X hourly observations` — if X is 0, the recorder has no data for that entity

### "SOC at Charge Window Start shows unavailable"

This sensor requires both:
- A free import window configured in your tariff settings (Options → Tariff & Rates)
- The optimizer to have a scheduled slot that starts at exactly that time

If your slot granularity is 30 minutes and your free import starts at 23:30, the sensor will find the slot. If it starts at 23:45 and you have 30-minute slots, the nearest slot may be 23:30 or 00:00 — configure the start time to align with slot boundaries.

### "Forecast confidence is always 100%"

No weather entity is configured, so no weather-based confidence adjustment is applied. This is not an error — the optimizer still works. Configure a weather entity in Options → Entity Mappings for improved accuracy on cloudy days.

### "Energy security score is 0%"

The LP solver can't guarantee enough charge to reach the bridge point. Possible causes:
- Battery is already low and can't be charged in time
- Solar forecast predicts nothing until very late in the day
- SOC floor is set so high the optimizer has little room to work with

Check the `bridge_to_time` and `bridge_to_source` attributes on the Health sensor to understand what point the optimizer is targeting.
