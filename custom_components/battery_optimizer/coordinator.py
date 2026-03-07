"""DataUpdateCoordinator for Battery Optimizer."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval, async_track_state_change_event
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    CONF_RECALCULATION_INTERVAL_MINUTES,
    CONF_SOLAR_FORECAST_ENTITY,
    CONF_SOLAR_FORECAST_FORMAT,
    CONF_BATTERY_SOC_ENTITY,
    CONF_BATTERY_CAPACITY_KWH,
    CONF_MIN_SOC_FLOOR_PERCENT,
    CONF_CONSUMPTION_ENTITY,
    CONF_CONSUMPTION_BASELINE_KW,
    CONF_EXPORT_BONUS_START,
    CONF_EXPORT_BONUS_END,
    CONF_WEATHER_ENTITY,
    CONF_SLOT_GRANULARITY_MINUTES,
    CONF_LOOKAHEAD_HOURS,
    CONF_BRIDGE_TO_FALLBACK_TIME,
    CONF_FREE_IMPORT_START,
    CONF_FREE_IMPORT_END,
    FORECAST_FORMAT_AUTO,
    CONF_FALLBACK_MODE,
    CONF_AGGRESSIVENESS,
    DEFAULT_RECALCULATION_INTERVAL_MINUTES,
    DEFAULT_AGGRESSIVENESS,
    DEFAULT_FALLBACK_MODE,
    DEFAULT_SLOT_GRANULARITY_MINUTES,
    DEFAULT_LOOKAHEAD_HOURS,
    DEFAULT_CONSUMPTION_BASELINE_KW,
    DEFAULT_MIN_SOC_FLOOR_PERCENT,
    DEFAULT_BRIDGE_TO_FALLBACK_TIME,
    STATE_RUNNING,
    STATE_PAUSED,
    STATE_ERROR,
    STATE_FALLBACK,
    FALLBACK_CONSERVATIVE_HOLD,
    FALLBACK_LAST_KNOWN_GOOD,
    STORAGE_KEY_OPTIMIZER_STATE,
    STORAGE_VERSION,
    ATTR_SLOTS,
)
from .bridge_calculator import compute_bridge_point
from .consumption_learner import ConsumptionLearner
from .events import detect_and_fire_schedule_changes
from .forecast_parser import parse_forecast
from .optimizer import (
    OptimizationResult,
    async_optimize,
    build_optimization_input,
    build_tariff_schedule,
)
from .tracker import PlannedVsActualTracker
from .weather_modifier import (
    apply_temperature_load_adjustment,
    apply_weather_to_forecast,
    async_get_weather_forecast_points,
)

_LOGGER = logging.getLogger(__name__)


class BatteryOptimizerCoordinator(DataUpdateCoordinator):
    """Manages schedule optimization, state, and entity tracking."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.entry = entry
        self._optimizer_state = STATE_RUNNING
        self._current_schedule: list[dict[str, Any]] = []
        self._last_schedule: list[dict[str, Any]] = []
        self._aggressiveness: float = entry.options.get(
            CONF_AGGRESSIVENESS,
            entry.data.get(CONF_AGGRESSIVENESS, DEFAULT_AGGRESSIVENESS),
        )
        self._active_override: dict[str, Any] | None = None
        self._unsub_interval = None
        self._unsub_forecast_change = None
        self._unsub_soc_change = None
        self._storage = None
        self._learner_storage = None
        self._tracker_storage = None
        self._tracker: PlannedVsActualTracker | None = None

        cfg = entry.data
        opts = entry.options
        from .const import (
            CONF_CONSUMPTION_PROFILE_GRANULARITY,
            CONF_CONSUMPTION_LOOKBACK_DAYS,
            CONF_DATA_RETENTION_DAYS,
            DEFAULT_CONSUMPTION_PROFILE_GRANULARITY,
            DEFAULT_CONSUMPTION_LOOKBACK_DAYS,
            DEFAULT_DATA_RETENTION_DAYS,
        )
        self._learner = ConsumptionLearner(
            baseline_kw=float(opts.get(CONF_CONSUMPTION_BASELINE_KW, cfg.get(CONF_CONSUMPTION_BASELINE_KW, DEFAULT_CONSUMPTION_BASELINE_KW))),
            granularity=opts.get(CONF_CONSUMPTION_PROFILE_GRANULARITY, cfg.get(CONF_CONSUMPTION_PROFILE_GRANULARITY, DEFAULT_CONSUMPTION_PROFILE_GRANULARITY)),
            lookback_days=int(opts.get(CONF_CONSUMPTION_LOOKBACK_DAYS, cfg.get(CONF_CONSUMPTION_LOOKBACK_DAYS, DEFAULT_CONSUMPTION_LOOKBACK_DAYS))),
            retention_days=int(opts.get(CONF_DATA_RETENTION_DAYS, cfg.get(CONF_DATA_RETENTION_DAYS, DEFAULT_DATA_RETENTION_DAYS))),
        )

        interval_minutes = entry.options.get(
            CONF_RECALCULATION_INTERVAL_MINUTES,
            entry.data.get(CONF_RECALCULATION_INTERVAL_MINUTES, DEFAULT_RECALCULATION_INTERVAL_MINUTES),
        )

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(minutes=interval_minutes),
        )

    async def async_setup(self) -> None:
        """Initialize storage, restore persisted state, and set up listeners."""
        from homeassistant.helpers.storage import Store
        from .const import STORAGE_KEY_LEARNED_PROFILES, STORAGE_KEY_PLANNED_VS_ACTUAL

        self._storage = Store(self.hass, STORAGE_VERSION, STORAGE_KEY_OPTIMIZER_STATE)
        self._learner_storage = Store(self.hass, STORAGE_VERSION, STORAGE_KEY_LEARNED_PROFILES)
        self._tracker_storage = Store(self.hass, STORAGE_VERSION, STORAGE_KEY_PLANNED_VS_ACTUAL)

        stored = await self._storage.async_load()
        if stored:
            self._optimizer_state = stored.get("state", STATE_RUNNING)
            self._aggressiveness = stored.get("aggressiveness", self._aggressiveness)
            _LOGGER.debug("Restored optimizer state: %s", self._optimizer_state)

        learner_stored = await self._learner_storage.async_load()
        if learner_stored:
            self._learner.load_from_storage(learner_stored)

        # Set up planned-vs-actual tracker
        cfg = {**self.entry.data, **self.entry.options}
        from .const import CONF_MAX_EXPORT_LIMIT_KW, DEFAULT_MAX_EXPORT_LIMIT_KW, DEFAULT_DATA_RETENTION_DAYS, CONF_DATA_RETENTION_DAYS
        self._tracker = PlannedVsActualTracker(
            hass=self.hass,
            soc_entity=cfg.get(CONF_BATTERY_SOC_ENTITY, ""),
            solar_entity=cfg.get(CONF_SOLAR_FORECAST_ENTITY),
            consumption_entity=cfg.get(CONF_CONSUMPTION_ENTITY),
            capacity_kwh=float(cfg.get(CONF_BATTERY_CAPACITY_KWH, 10.0)),
            retention_days=int(cfg.get(CONF_DATA_RETENTION_DAYS, DEFAULT_DATA_RETENTION_DAYS)),
        )
        tracker_stored = await self._tracker_storage.async_load()
        if tracker_stored:
            self._tracker.load_from_storage(tracker_stored)

        # Kick off initial recorder training in background, then persist the result
        consumption_entity = cfg.get(CONF_CONSUMPTION_ENTITY)
        if consumption_entity:
            _LOGGER.info("Consumption learner: scheduling startup training for '%s'", consumption_entity)
            async def _train_and_persist() -> None:
                try:
                    await self._learner.async_train_from_recorder(self.hass, consumption_entity)
                    status = self._learner.get_learning_status()
                    _LOGGER.info(
                        "Consumption learner startup training complete — trained=%s, observations=%d",
                        status.get("is_trained"),
                        status.get("observation_count", 0),
                    )
                    if self._learner_storage:
                        await self._learner_storage.async_save(self._learner.to_storage())
                        _LOGGER.debug("Consumption learner state persisted")
                except Exception as err:
                    _LOGGER.error("Consumption learner startup training failed: %s", err, exc_info=True)
            self.hass.async_create_task(_train_and_persist())

        self._setup_forecast_listener()
        self._setup_soc_listener()

    def _setup_forecast_listener(self) -> None:
        """Track forecast entity state changes and trigger recalculation."""
        forecast_entity = self.entry.data.get(CONF_SOLAR_FORECAST_ENTITY)
        if not forecast_entity:
            return

        @callback
        def _on_forecast_change(event):
            if self._optimizer_state != STATE_PAUSED:
                self.hass.async_create_task(self.async_refresh())

        self._unsub_forecast_change = async_track_state_change_event(
            self.hass, [forecast_entity], _on_forecast_change
        )

    def _setup_soc_listener(self) -> None:
        """Track SOC sensor availability."""
        soc_entity = self.entry.data.get(CONF_BATTERY_SOC_ENTITY)
        if not soc_entity:
            return

        @callback
        def _on_soc_change(event):
            # SOC changes just update availability tracking, not full recalc
            pass

        self._unsub_soc_change = async_track_state_change_event(
            self.hass, [soc_entity], _on_soc_change
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data and run optimization. Called by the coordinator update loop."""
        if self._optimizer_state == STATE_PAUSED:
            return self._build_paused_data()

        try:
            return await self._async_run_optimization()
        except Exception as err:
            _LOGGER.error("Optimization failed: %s", err)
            fallback_mode = self.entry.data.get(CONF_FALLBACK_MODE, DEFAULT_FALLBACK_MODE)
            return self._build_fallback_data(fallback_mode, str(err))

    async def _async_run_optimization(self) -> dict[str, Any]:
        """Fetch all inputs, run the LP optimizer, and return schedule data."""
        cfg = self.entry.data
        opts = self.entry.options
        merged = {**cfg, **opts}

        now = dt_util.now()
        slot_minutes = int(merged.get(CONF_SLOT_GRANULARITY_MINUTES, DEFAULT_SLOT_GRANULARITY_MINUTES))
        lookahead_hours = int(merged.get(CONF_LOOKAHEAD_HOURS, DEFAULT_LOOKAHEAD_HOURS))
        n_slots = (lookahead_hours * 60) // slot_minutes
        slot_hours = slot_minutes / 60.0

        # --- Read current SOC ---
        soc_entity = merged.get(CONF_BATTERY_SOC_ENTITY)
        soc_state = self.hass.states.get(soc_entity) if soc_entity else None
        soc_available = soc_state is not None and soc_state.state not in ("unavailable", "unknown", "none")

        if soc_available:
            try:
                initial_soc_pct = float(soc_state.state)
            except (ValueError, TypeError):
                initial_soc_pct = 50.0
                soc_available = False
        else:
            initial_soc_pct = 50.0

        if soc_available:
            _LOGGER.info(
                "Optimization starting — SOC: %.1f%% (%s ✓)",
                initial_soc_pct,
                soc_entity,
            )
        else:
            _LOGGER.warning(
                "SOC sensor unavailable — using 50%% fallback (entity: %s, state: %s)",
                soc_entity or "not configured",
                soc_state.state if soc_state else "not found",
            )

        # --- Read dynamic export limit ---
        max_export_entity = merged.get("max_export_limit_entity")
        if max_export_entity:
            exp_state = self.hass.states.get(max_export_entity)
            if exp_state and exp_state.state not in ("unavailable", "unknown"):
                try:
                    merged = dict(merged)
                    merged["max_export_limit_kw"] = float(exp_state.state)
                except (ValueError, TypeError):
                    pass

        # --- Parse solar forecast ---
        forecast_entity = merged.get(CONF_SOLAR_FORECAST_ENTITY)
        forecast_format = merged.get(CONF_SOLAR_FORECAST_FORMAT, FORECAST_FORMAT_AUTO)
        _diag_solar_nonzero = 0
        if not forecast_entity:
            _LOGGER.warning(
                "Solar forecast entity not configured — using zero solar for all slots. "
                "Add a forecast entity under Settings → Configure."
            )
        solar_kwh = parse_forecast(
            self.hass,
            forecast_entity,
            forecast_format,
            slot_minutes,
            n_slots,
            now,
        ) if forecast_entity else [0.0] * n_slots

        if forecast_entity:
            n_nonzero = sum(1 for v in solar_kwh if v > 0)
            _diag_solar_nonzero = n_nonzero
            if n_nonzero == 0:
                _LOGGER.warning(
                    "No slots parsed from forecast entity %s — "
                    "check entity attributes in Developer Tools → States",
                    forecast_entity,
                )
            else:
                _LOGGER.info(
                    "Solar: %d non-zero slots from %s (%s format, total %.2f kWh)",
                    n_nonzero,
                    forecast_entity,
                    forecast_format,
                    sum(solar_kwh),
                )

        # --- Load profile from learned consumption ---
        load_kwh = self._learner.get_load_profile(now, n_slots, slot_minutes)
        learning_status = self._learner.get_learning_status()
        if learning_status.get("is_trained"):
            _LOGGER.info(
                "Consumption: learned profile (%s, %d observations, %.1f days)",
                learning_status.get("profile_types", "unknown"),
                learning_status.get("observation_count", 0),
                learning_status.get("days_covered", 0.0),
            )
        else:
            consumption_entity = merged.get(CONF_CONSUMPTION_ENTITY)
            if not consumption_entity:
                _LOGGER.warning(
                    "Consumption learner not trained — using baseline %.2f kW. "
                    "Add a consumption entity under Settings → Configure → Step 5.",
                    learning_status.get("baseline_kw", 0.3),
                )
            else:
                _LOGGER.warning(
                    "Consumption learner not trained — using baseline %.2f kW "
                    "(entity: %s). Hit 'Retrain Now' in the Analytics tab if recorder has data.",
                    learning_status.get("baseline_kw", 0.3),
                    consumption_entity,
                )

        # --- Weather modifier: confidence + temperature load adjustment ---
        weather_entity = merged.get(CONF_WEATHER_ENTITY)
        forecast_confidence = 1.0
        if weather_entity:
            weather_points = await async_get_weather_forecast_points(
                self.hass, weather_entity, now, n_slots, slot_minutes
            )
            if weather_points:
                solar_kwh, forecast_confidence = apply_weather_to_forecast(solar_kwh, weather_points)
                temp_coeffs = self._learner.get_temperature_coefficients()
                if temp_coeffs:
                    load_kwh = apply_temperature_load_adjustment(
                        load_kwh, weather_points, temp_coeffs, slot_hours
                    )
                _LOGGER.info(
                    "Weather: %s ✓ — forecast confidence: %d%%",
                    weather_entity,
                    int(forecast_confidence * 100),
                )
            else:
                _LOGGER.warning(
                    "Weather entity %s returned no forecast points — "
                    "solar confidence not adjusted",
                    weather_entity,
                )
        else:
            _LOGGER.debug(
                "No weather entity configured — forecast confidence at 100%%. "
                "Add one under Settings → Configure for improved accuracy."
            )

        # --- Build tariff schedule ---
        tariff = build_tariff_schedule(merged, now, n_slots, slot_minutes)

        # --- Compute bridge point ---
        capacity_kwh = float(merged.get(CONF_BATTERY_CAPACITY_KWH, 10.0))
        min_soc_pct = float(merged.get(CONF_MIN_SOC_FLOOR_PERCENT, DEFAULT_MIN_SOC_FLOOR_PERCENT))
        min_soc_kwh = (min_soc_pct / 100.0) * capacity_kwh

        bridge = compute_bridge_point(
            self.hass,
            now,
            slot_minutes,
            n_slots,
            solar_kwh,
            load_kwh,
            min_soc_kwh,
            merged.get(CONF_FREE_IMPORT_START),
            merged.get(CONF_FREE_IMPORT_END),
            merged.get(CONF_BRIDGE_TO_FALLBACK_TIME, DEFAULT_BRIDGE_TO_FALLBACK_TIME),
        )

        _LOGGER.info(
            "Bridge-to: %s (%s) — energy needed: %.2f kWh",
            bridge.dt.strftime("%H:%M"),
            bridge.source,
            bridge.energy_needed_kwh,
        )

        # --- Build optimizer input and run LP ---
        opt_input = build_optimization_input(
            config=cfg,
            options=opts,
            initial_soc_pct=initial_soc_pct,
            solar_kwh_per_slot=solar_kwh,
            load_kwh_per_slot=load_kwh,
            tariff=tariff,
            bridge_slot=bridge.slot_index,
            energy_needed_kwh=bridge.energy_needed_kwh,
            start_dt=now,
        )

        result: OptimizationResult = await async_optimize(self.hass, opt_input)

        if not result.success:
            raise RuntimeError(result.message)

        # --- Stamp slot datetimes and apply active overrides ---
        slot_delta = timedelta(minutes=slot_minutes)
        slots_out = []
        for i, slot in enumerate(result.slots):
            slot_start = now + slot_delta * i
            slot_end = slot_start + slot_delta
            s = slot.__dict__.copy()
            s["start"] = slot_start.isoformat()
            s["end"] = slot_end.isoformat()

            # Apply override if active and covers this slot
            if self._active_override:
                override_start = self._active_override.get("start")
                if override_start and slot_start.isoformat().startswith(override_start[:16]):
                    s["action"] = self._active_override["action"]
                    if self._active_override.get("power_kw") is not None:
                        s["power_kw"] = self._active_override["power_kw"]
                    s["is_override"] = True

            slots_out.append(s)

        # --- Enrich historical slots with actual values from tracker ---
        if self._tracker:
            slots_out = self._tracker.enrich_historical_slots(slots_out)

        # --- Fire schedule-changed events for imminent slot changes ---
        prev_slots = self._last_schedule or []
        detect_and_fire_schedule_changes(self.hass, prev_slots, slots_out, now)

        # --- Schedule planned-vs-actual polls at slot boundaries ---
        if self._tracker:
            self._tracker.schedule_slot_polls(slots_out)

        # Save current schedule as last-known-good for fallback
        self._last_schedule = slots_out

        # --- Log optimization summary ---
        if slots_out:
            first_slot = slots_out[0]
            soc_start = initial_soc_pct
            soc_end = first_slot.get("projected_soc", soc_start)
            _LOGGER.info(
                "Schedule: %d slots, solve %dms — action=%s, SOC %.0f%%→%.0f%%, "
                "security=%.0f%%, revenue=%.4f",
                len(slots_out),
                result.solve_time_ms,
                first_slot.get("action", "unknown"),
                soc_start,
                soc_end,
                result.energy_security_score * 100,
                result.estimated_export_revenue,
            )

        def _entity_diag(entity_id: str | None) -> dict:
            if not entity_id:
                return {"id": None, "state": "not_configured", "ok": False}
            st = self.hass.states.get(entity_id)
            if st is None:
                return {"id": entity_id, "state": "not_found_in_ha", "ok": False}
            is_ok = st.state not in ("unavailable", "unknown", "none")
            return {"id": entity_id, "state": st.state, "ok": is_ok}

        consumption_entity = merged.get(CONF_CONSUMPTION_ENTITY)
        load_avg_kw = round(
            (sum(load_kwh) / len(load_kwh)) / (slot_minutes / 60.0), 3
        ) if load_kwh else 0.0

        diagnostics = {
            "entities": {
                "soc": _entity_diag(soc_entity),
                "solar_forecast": _entity_diag(forecast_entity),
                "consumption": _entity_diag(consumption_entity),
                "weather": _entity_diag(weather_entity if weather_entity else None),
            },
            "inputs": {
                "initial_soc_pct": round(initial_soc_pct, 2),
                "n_slots": n_slots,
                "slot_minutes": slot_minutes,
                "lookahead_hours": lookahead_hours,
                "solar_total_kwh": round(sum(solar_kwh), 3),
                "solar_nonzero_slots": _diag_solar_nonzero,
                "load_avg_kw": load_avg_kw,
                "capacity_kwh": capacity_kwh,
                "min_soc_pct": min_soc_pct,
                "forecast_format": forecast_format,
                "aggressiveness": self._aggressiveness,
            },
            "config": {
                "free_import_start": merged.get(CONF_FREE_IMPORT_START),
                "free_import_end": merged.get(CONF_FREE_IMPORT_END),
                "bridge_fallback_time": merged.get(CONF_BRIDGE_TO_FALLBACK_TIME, DEFAULT_BRIDGE_TO_FALLBACK_TIME),
                "fallback_mode": merged.get(CONF_FALLBACK_MODE, DEFAULT_FALLBACK_MODE),
            },
        }

        schedule_analysis = self._analyze_schedule(slots_out, solar_kwh, merged, slot_minutes)

        # Persist learner state so profiles survive restarts
        if self._learner_storage and self._learner.get_learning_status().get("is_trained"):
            await self._learner_storage.async_save(self._learner.to_storage())

        return {
            "state": STATE_RUNNING,
            "slots": slots_out,
            "learning": self._learner.get_learning_status(),
            "schedule_analysis": schedule_analysis,
            "health": {
                "solver_status": "ok",
                "forecast_staleness_seconds": 0,
                "soc_sensor_available": soc_available,
                "last_recalculation": now.isoformat(),
                "solver_duration_ms": result.solve_time_ms,
                "problem_size": result.problem_size,
                "fallback_mode_active": False,
                "estimated_export_revenue": result.estimated_export_revenue,
                "energy_security_score": result.energy_security_score,
                "forecast_confidence": forecast_confidence,
                "bridge_to_time": bridge.dt.isoformat(),
                "bridge_to_source": bridge.source,
                "diagnostics": diagnostics,
            },
            "aggressiveness": self._aggressiveness,
        }

    def _analyze_schedule(
        self,
        slots: list[dict[str, Any]],
        solar_kwh: list[float],
        merged: dict[str, Any],
        slot_minutes: int,
    ) -> dict[str, Any]:
        """Compute export recommendation and charge window projections from the schedule."""

        def _hhmm_to_minutes(hhmm: str | None) -> int | None:
            if not hhmm:
                return None
            try:
                h, m = map(int, str(hhmm)[:5].split(":"))
                return h * 60 + m
            except (ValueError, AttributeError):
                return None

        def _slot_start_minutes(slot: dict) -> int | None:
            s = slot.get("start", "")
            if len(s) < 16:
                return None
            try:
                return int(s[11:13]) * 60 + int(s[14:16])
            except (ValueError, IndexError):
                return None

        def _slot_in_window(slot: dict, win_start_min: int, win_end_min: int) -> bool:
            sm = _slot_start_minutes(slot)
            if sm is None:
                return False
            # Handle overnight windows (e.g. 23:30 → 06:00)
            if win_end_min <= win_start_min:
                return sm >= win_start_min or sm < win_end_min
            return win_start_min <= sm < win_end_min

        def _slot_date_offset(slot: dict) -> int | None:
            """Return how many calendar days after today this slot falls on (0=today, 1=tomorrow…)."""
            s = slot.get("start", "")
            if len(s) < 10:
                return None
            try:
                from datetime import date
                slot_date = date.fromisoformat(s[:10])
                today = dt_util.now().date()
                return (slot_date - today).days
            except (ValueError, TypeError):
                return None

        def _first_occurrence(all_slots: list[dict]) -> list[dict]:
            """From a list of window-matched slots spanning multiple days, return only
            the earliest day's slots (the next upcoming window occurrence)."""
            if not all_slots:
                return []
            offsets = [_slot_date_offset(s) for s in all_slots]
            valid_offsets = [o for o in offsets if o is not None]
            if not valid_offsets:
                return all_slots
            first = min(valid_offsets)
            return [s for s, o in zip(all_slots, offsets) if o == first]

        future_slots = [s for s in slots if not s.get("is_historical")]

        # --- Export window analysis ---
        exp_start_min = _hhmm_to_minutes(merged.get(CONF_EXPORT_BONUS_START))
        exp_end_min = _hhmm_to_minutes(merged.get(CONF_EXPORT_BONUS_END))
        export_slots = []
        if exp_start_min is not None and exp_end_min is not None:
            export_slots = _first_occurrence(
                [s for s in future_slots if _slot_in_window(s, exp_start_min, exp_end_min)]
            )

        exporting = [s for s in export_slots if s.get("action") == "export"]
        avg_export_power = (
            sum(s.get("power_kw", 0) for s in exporting) / len(exporting)
            if exporting else 0.0
        )
        total_export_kwh = sum(s.get("power_kw", 0) * (slot_minutes / 60.0) for s in exporting)
        soc_at_export_start = export_slots[0].get("projected_soc") if export_slots else None
        soc_at_export_end = export_slots[-1].get("projected_soc") if export_slots else None

        if not exp_start_min:
            export_recommendation = "not_configured"
            reasoning = ["Export bonus window not configured"]
        elif not export_slots:
            export_recommendation = "hold"
            reasoning = ["No schedule slots found in export window"]
        elif len(exporting) == len(export_slots):
            export_recommendation = "full_export"
            reasoning = ["All export window slots scheduled for export"]
        elif exporting:
            export_recommendation = "partial_export"
            reasoning = [f"{len(exporting)}/{len(export_slots)} export window slots scheduled for export"]
        else:
            export_recommendation = "hold"
            reasoning = ["Optimizer chose to hold battery during export window"]

        # Add reasoning factors
        health_score = None
        if hasattr(self, 'data') and self.data:
            health_score = self.data.get("health", {}).get("energy_security_score")
        if health_score is not None and health_score < 0.5:
            reasoning.append(f"Low energy security score ({health_score:.0%}) — battery may not reach charge window")

        # --- Daily solar totals ---
        slots_per_day = (24 * 60) // slot_minutes
        daily_solar = []
        for day in range(3):
            start_i = day * slots_per_day
            end_i = start_i + slots_per_day
            day_total = sum(solar_kwh[start_i:end_i]) if len(solar_kwh) > start_i else 0.0
            daily_solar.append(round(day_total, 2))

        low_solar_threshold_kwh = 2.0
        days_low_solar = sum(1 for d in daily_solar if d < low_solar_threshold_kwh)
        if days_low_solar >= 2:
            reasoning.append(f"{days_low_solar} days of low solar ahead — conservative export recommended")

        # --- Charge window analysis ---
        charge_start_min = _hhmm_to_minutes(merged.get(CONF_FREE_IMPORT_START))
        charge_end_min = _hhmm_to_minutes(merged.get(CONF_FREE_IMPORT_END))
        # Charge window: only the NEXT single occurrence (first date's slots).
        charge_slots = []
        if charge_start_min is not None and charge_end_min is not None:
            charge_slots = _first_occurrence(
                [s for s in future_slots if _slot_in_window(s, charge_start_min, charge_end_min)]
            )

        soc_at_charge_start = charge_slots[0].get("projected_soc") if charge_slots else None
        soc_at_charge_end = charge_slots[-1].get("projected_soc") if charge_slots else None
        soc_gain_in_charge_window = (
            round(soc_at_charge_end - soc_at_charge_start, 1)
            if soc_at_charge_start is not None and soc_at_charge_end is not None
            else None
        )

        # --- Tomorrow and day-after SOC projections (charge and export windows) ---
        soc_at_tomorrow_charge_end = None
        soc_at_day_after_charge_end = None
        if charge_start_min is not None and charge_end_min is not None:
            for day_offset, attr_name in [(1, "tomorrow"), (2, "day_after")]:
                day_slots = [
                    s for s in future_slots
                    if _slot_date_offset(s) == day_offset
                    and _slot_in_window(s, charge_start_min, charge_end_min)
                ]
                if day_slots:
                    soc_val = day_slots[-1].get("projected_soc")
                    if attr_name == "tomorrow":
                        soc_at_tomorrow_charge_end = soc_val
                    else:
                        soc_at_day_after_charge_end = soc_val

        soc_at_tomorrow_export_start = None
        soc_at_tomorrow_export_end = None
        soc_at_day_after_export_start = None
        soc_at_day_after_export_end = None
        if exp_start_min is not None and exp_end_min is not None:
            for day_offset, prefix in [(1, "tomorrow"), (2, "day_after")]:
                day_slots = [
                    s for s in future_slots
                    if _slot_date_offset(s) == day_offset
                    and _slot_in_window(s, exp_start_min, exp_end_min)
                ]
                if day_slots:
                    if prefix == "tomorrow":
                        soc_at_tomorrow_export_start = day_slots[0].get("projected_soc")
                        soc_at_tomorrow_export_end = day_slots[-1].get("projected_soc")
                    else:
                        soc_at_day_after_export_start = day_slots[0].get("projected_soc")
                        soc_at_day_after_export_end = day_slots[-1].get("projected_soc")

        return {
            "export_recommendation": export_recommendation,
            "export_recommended_power_kw": round(avg_export_power, 2),
            "export_slots_total": len(export_slots),
            "export_slots_active": len(exporting),
            "total_export_kwh": round(total_export_kwh, 2),
            "soc_at_export_start": soc_at_export_start,
            "soc_at_export_end": soc_at_export_end,
            "soc_at_charge_start": soc_at_charge_start,
            "soc_at_charge_end": soc_at_charge_end,
            "soc_gain_in_charge_window": soc_gain_in_charge_window,
            "soc_at_tomorrow_charge_end": soc_at_tomorrow_charge_end,
            "soc_at_day_after_charge_end": soc_at_day_after_charge_end,
            "soc_at_tomorrow_export_start": soc_at_tomorrow_export_start,
            "soc_at_tomorrow_export_end": soc_at_tomorrow_export_end,
            "soc_at_day_after_export_start": soc_at_day_after_export_start,
            "soc_at_day_after_export_end": soc_at_day_after_export_end,
            "daily_solar_kwh": daily_solar,
            "days_low_solar_ahead": days_low_solar,
            "reasoning": reasoning,
            "export_window_start": merged.get(CONF_EXPORT_BONUS_START),
            "export_window_end": merged.get(CONF_EXPORT_BONUS_END),
            "charge_window_start": merged.get(CONF_FREE_IMPORT_START),
            "charge_window_end": merged.get(CONF_FREE_IMPORT_END),
        }

    def _build_paused_data(self) -> dict[str, Any]:
        """Return hold-everything data when optimizer is paused."""
        return {
            "state": STATE_PAUSED,
            "slots": [],
            "learning": self._learner.get_learning_status(),
            "schedule_analysis": {},
            "health": {
                "solver_status": "paused",
                "forecast_staleness_seconds": 0,
                "soc_sensor_available": True,
                "last_recalculation": None,
                "solver_duration_ms": 0,
                "problem_size": 0,
                "fallback_mode_active": False,
                "estimated_export_revenue": 0.0,
                "energy_security_score": 1.0,
                "forecast_confidence": 0.0,
                "bridge_to_time": None,
                "bridge_to_source": None,
            },
            "aggressiveness": self._aggressiveness,
        }

    def _build_fallback_data(self, fallback_mode: str, error: str) -> dict[str, Any]:
        """Return data in fallback mode when optimization fails."""
        if fallback_mode == FALLBACK_LAST_KNOWN_GOOD and self._last_schedule:
            slots = self._last_schedule
            state = STATE_FALLBACK
        else:
            slots = []
            state = STATE_ERROR if fallback_mode == "error_state" else STATE_FALLBACK

        return {
            "state": state,
            "slots": slots,
            "learning": self._learner.get_learning_status(),
            "schedule_analysis": {},
            "health": {
                "solver_status": f"error: {error}",
                "forecast_staleness_seconds": 0,
                "soc_sensor_available": False,
                "last_recalculation": None,
                "solver_duration_ms": 0,
                "problem_size": 0,
                "fallback_mode_active": True,
                "estimated_export_revenue": 0.0,
                "energy_security_score": 0.0,
                "forecast_confidence": 0.0,
                "bridge_to_time": None,
                "bridge_to_source": None,
            },
            "aggressiveness": self._aggressiveness,
        }

    async def async_pause(self) -> None:
        """Pause the optimizer and persist state."""
        self._optimizer_state = STATE_PAUSED
        await self._persist_state()
        await self.async_refresh()

    async def async_resume(self) -> None:
        """Resume the optimizer and trigger recalculation."""
        self._optimizer_state = STATE_RUNNING
        await self._persist_state()
        await self.async_refresh()

    async def async_set_aggressiveness(self, value: float) -> None:
        """Update aggressiveness and trigger recalculation."""
        self._aggressiveness = max(0.0, min(1.0, value))
        await self._persist_state()
        if self._optimizer_state == STATE_RUNNING:
            await self.async_refresh()

    async def async_override_slot(self, start: str, action: str, power_kw: float | None, duration_minutes: int) -> None:
        """Apply a manual slot override and schedule auto-recalculation on expiry."""
        self._active_override = {
            "start": start,
            "action": action,
            "power_kw": power_kw,
            "duration_minutes": duration_minutes,
            "expires_at": (dt_util.now() + timedelta(minutes=duration_minutes)).isoformat(),
        }

        async def _on_override_expiry(_now):
            self._active_override = None
            if self._optimizer_state == STATE_RUNNING:
                await self.async_refresh()

        from homeassistant.helpers.event import async_call_later
        async_call_later(
            self.hass, duration_minutes * 60, _on_override_expiry
        )
        await self.async_refresh()

    async def _persist_state(self) -> None:
        """Save optimizer state and learned profiles to .storage/."""
        if self._storage:
            await self._storage.async_save({
                "state": self._optimizer_state,
                "aggressiveness": self._aggressiveness,
            })
        if self._learner_storage:
            await self._learner_storage.async_save(self._learner.to_storage())
        if self._tracker_storage and self._tracker:
            await self._tracker_storage.async_save(self._tracker.to_storage())

    async def async_retrain_learner(self) -> None:
        """Re-train consumption learner from recorder history and persist."""
        consumption_entity = (
            self.entry.options.get(CONF_CONSUMPTION_ENTITY)
            or self.entry.data.get(CONF_CONSUMPTION_ENTITY)
        )
        if consumption_entity:
            await self._learner.async_train_from_recorder(self.hass, consumption_entity)
            if self._learner_storage:
                await self._learner_storage.async_save(self._learner.to_storage())

    async def async_shutdown(self) -> None:
        """Clean up listeners and scheduled polls on unload."""
        if self._unsub_interval:
            self._unsub_interval()
        if self._unsub_forecast_change:
            self._unsub_forecast_change()
        if self._unsub_soc_change:
            self._unsub_soc_change()
        if self._tracker:
            self._tracker.cancel_all()

    @property
    def optimizer_state(self) -> str:
        return self._optimizer_state

    @property
    def aggressiveness(self) -> float:
        return self._aggressiveness
