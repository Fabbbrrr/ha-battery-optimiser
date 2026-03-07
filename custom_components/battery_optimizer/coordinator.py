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

        # Kick off initial recorder training in background
        consumption_entity = cfg.get(CONF_CONSUMPTION_ENTITY)
        if consumption_entity:
            self.hass.async_create_task(
                self._learner.async_train_from_recorder(self.hass, consumption_entity)
            )

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
        solar_kwh = parse_forecast(
            self.hass,
            forecast_entity,
            forecast_format,
            slot_minutes,
            n_slots,
            now,
        ) if forecast_entity else [0.0] * n_slots

        # --- Load profile from learned consumption ---
        load_kwh = self._learner.get_load_profile(now, n_slots, slot_minutes)

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

        return {
            "state": STATE_RUNNING,
            "slots": slots_out,
            "learning": self._learner.get_learning_status(),
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
            },
            "aggressiveness": self._aggressiveness,
        }

    def _build_paused_data(self) -> dict[str, Any]:
        """Return hold-everything data when optimizer is paused."""
        return {
            "state": STATE_PAUSED,
            "slots": [],
            "learning": self._learner.get_learning_status(),
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
