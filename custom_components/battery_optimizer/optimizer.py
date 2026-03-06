"""LP optimizer for battery charge/discharge/export scheduling.

Formulation
-----------
Decision variables per slot t (6 * n_slots total):
  x[IDX_EXPORT + t]        = kWh exported from battery to grid
  x[IDX_HOME_DIS + t]      = kWh discharged from battery to cover home load
  x[IDX_CHARGE_SOLAR + t]  = kWh charged into battery from solar surplus
  x[IDX_CHARGE_GRID + t]   = kWh charged into battery from grid (optional)
  x[IDX_GRID_IMPORT + t]   = kWh imported from grid to cover deficit not met by battery
  x[IDX_SOC + t]            = battery SOC (kWh) at end of slot t

Objective (minimise negative revenue):
  min Σ_t [ -export[t]*export_rate[t]
            + grid_import[t]*import_rate[t]
            + charge_grid[t]*import_rate[t]
            - (1-aggressiveness)*soc_weight*soc[t] ]

Constraints:
  SOC dynamics (equality, T equations):
    soc[0] = initial_soc + charge_solar[0] + charge_grid[0] - export[0] - home_dis[0]
    soc[t] = soc[t-1] + charge_solar[t] + charge_grid[t] - export[t] - home_dis[t]  (t>0)

  Physical limits (inequality):
    export[t] + home_dis[t]          <= max_discharge_kwh_per_slot
    charge_solar[t] + charge_grid[t] <= max_charge_kwh_per_slot
    charge_solar[t]                  <= solar_surplus[t]
    -home_dis[t] - grid_import[t]    <= -deficit[t]        (deficit coverage)
    export[t]                        <= max_export_kwh_per_slot
    charge_grid[t]                   <= 0  (if not in grid-charge window)

  Bounds:
    soc[t]          in [min_soc_kwh, capacity_kwh]
    all others      >= 0
"""
from __future__ import annotations

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

import numpy as np

from homeassistant.core import HomeAssistant

from .const import (
    ACTION_CHARGE,
    ACTION_DISCHARGE,
    ACTION_EXPORT,
    ACTION_HOLD,
    CONF_AGGRESSIVENESS,
    CONF_BATTERY_CAPACITY_KWH,
    CONF_BRIDGE_TO_FALLBACK_TIME,
    CONF_EXPORT_BONUS_END,
    CONF_EXPORT_BONUS_RATE,
    CONF_EXPORT_BONUS_START,
    CONF_FREE_IMPORT_END,
    CONF_FREE_IMPORT_START,
    CONF_GRID_CHARGING_ENABLED,
    CONF_LOOKAHEAD_HOURS,
    CONF_MAX_CHARGE_RATE_KW,
    CONF_MAX_DISCHARGE_RATE_KW,
    CONF_MAX_EXPORT_LIMIT_KW,
    CONF_MIN_SOC_FLOOR_PERCENT,
    CONF_PEAK_IMPORT_END,
    CONF_PEAK_IMPORT_RATE,
    CONF_PEAK_IMPORT_START,
    CONF_SLOT_GRANULARITY_MINUTES,
    CONF_SOLVER_TIMEOUT_SECONDS,
    CONF_STANDARD_EXPORT_RATE,
    CONF_STANDARD_IMPORT_RATE,
    DEFAULT_AGGRESSIVENESS,
    DEFAULT_LOOKAHEAD_HOURS,
    DEFAULT_MAX_CHARGE_RATE_KW,
    DEFAULT_MAX_DISCHARGE_RATE_KW,
    DEFAULT_MAX_EXPORT_LIMIT_KW,
    DEFAULT_MIN_SOC_FLOOR_PERCENT,
    DEFAULT_SLOT_GRANULARITY_MINUTES,
    DEFAULT_SOLVER_TIMEOUT_SECONDS,
    DEFAULT_STANDARD_EXPORT_RATE,
    DEFAULT_STANDARD_IMPORT_RATE,
    DEFAULT_BRIDGE_TO_FALLBACK_TIME,
)

_LOGGER = logging.getLogger(__name__)

_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="battery_optimizer_lp")

# Variable index offsets
IDX_EXPORT = 0
IDX_HOME_DIS = 1
IDX_CHARGE_SOLAR = 2
IDX_CHARGE_GRID = 3
IDX_GRID_IMPORT = 4
IDX_SOC = 5
N_VARS_PER_SLOT = 6


@dataclass
class TariffSchedule:
    """Per-slot tariff rates."""
    export_rate: list[float]   # $/kWh earned for each export slot
    import_rate: list[float]   # $/kWh paid for each import slot
    grid_charge_allowed: list[bool]  # Whether grid charging is allowed in each slot


@dataclass
class OptimizationInput:
    """All inputs required for the LP optimizer."""
    n_slots: int
    slot_hours: float            # Duration of each slot in hours
    initial_soc_kwh: float       # Current battery SOC in kWh
    capacity_kwh: float          # Usable battery capacity in kWh
    min_soc_kwh: float           # Hard SOC floor in kWh
    max_charge_kwh: float        # Max charge energy per slot (kW * slot_hours)
    max_discharge_kwh: float     # Max discharge energy per slot
    max_export_kwh: float        # Max export energy per slot (grid export limit)
    solar_kwh: list[float]       # Expected solar generation per slot (kWh)
    load_kwh: list[float]        # Expected home consumption per slot (kWh)
    tariff: TariffSchedule
    aggressiveness: float        # 0.0-1.0
    solver_timeout: float        # seconds
    bridge_slot: int             # Slot index where energy security is restored
    energy_needed_kwh: float     # Energy needed at bridge point


@dataclass
class SlotResult:
    """Optimizer output for a single time slot."""
    start: str           # ISO datetime string
    end: str
    action: str          # charge | discharge | hold | export
    power_kw: float      # Recommended power (kW), positive = charge, negative = discharge
    projected_soc: float # Battery SOC at end of slot (%)
    expected_solar_kwh: float
    expected_consumption_kwh: float
    net_energy_kwh: float   # net energy in/out of battery
    is_historical: bool = False
    is_override: bool = False
    actual_soc: float | None = None
    actual_solar_kwh: float | None = None
    actual_consumption_kwh: float | None = None


@dataclass
class OptimizationResult:
    """Full optimization output."""
    slots: list[SlotResult]
    estimated_export_revenue: float
    energy_security_score: float
    forecast_confidence: float
    solve_time_ms: float
    problem_size: int          # Number of LP decision variables
    objective_value: float
    success: bool
    message: str


def _parse_time_to_minutes(time_str: str) -> int:
    """Convert HH:MM to minutes since midnight."""
    try:
        h, m = map(int, time_str.split(":"))
        return h * 60 + m
    except (ValueError, AttributeError):
        return 0


def build_tariff_schedule(
    config: dict,
    start_dt: datetime,
    n_slots: int,
    slot_minutes: int,
) -> TariffSchedule:
    """Build per-slot tariff rates from config."""
    export_rate = []
    import_rate = []
    grid_charge_allowed = []

    standard_export = config.get(CONF_STANDARD_EXPORT_RATE, DEFAULT_STANDARD_EXPORT_RATE)
    standard_import = config.get(CONF_STANDARD_IMPORT_RATE, DEFAULT_STANDARD_IMPORT_RATE)
    bonus_rate = config.get(CONF_EXPORT_BONUS_RATE, 0.0)

    # Parse bonus window
    bonus_start_min = _parse_time_to_minutes(config.get(CONF_EXPORT_BONUS_START, "18:00"))
    bonus_end_min = _parse_time_to_minutes(config.get(CONF_EXPORT_BONUS_END, "20:00"))

    # Parse free import window
    free_start_min = _parse_time_to_minutes(config.get(CONF_FREE_IMPORT_START, "")) if config.get(CONF_FREE_IMPORT_START) else None
    free_end_min = _parse_time_to_minutes(config.get(CONF_FREE_IMPORT_END, "")) if config.get(CONF_FREE_IMPORT_END) else None

    # Parse peak import window
    peak_start_min = _parse_time_to_minutes(config.get(CONF_PEAK_IMPORT_START, "")) if config.get(CONF_PEAK_IMPORT_START) else None
    peak_end_min = _parse_time_to_minutes(config.get(CONF_PEAK_IMPORT_END, "")) if config.get(CONF_PEAK_IMPORT_END) else None
    peak_rate = config.get(CONF_PEAK_IMPORT_RATE, standard_import)

    grid_charging_enabled = config.get(CONF_GRID_CHARGING_ENABLED, False)

    for i in range(n_slots):
        slot_dt = start_dt + timedelta(minutes=slot_minutes * i)
        slot_min = slot_dt.hour * 60 + slot_dt.minute

        # Export rate
        if bonus_start_min <= slot_min < bonus_end_min:
            slot_export_rate = bonus_rate
        else:
            slot_export_rate = standard_export

        # Import rate
        if free_start_min is not None and free_end_min is not None:
            if free_start_min <= slot_min < free_end_min:
                slot_import_rate = 0.0
            elif peak_start_min is not None and peak_start_min <= slot_min < peak_end_min:
                slot_import_rate = peak_rate
            else:
                slot_import_rate = standard_import
        elif peak_start_min is not None and peak_end_min is not None and peak_start_min <= slot_min < peak_end_min:
            slot_import_rate = peak_rate
        else:
            slot_import_rate = standard_import

        # Grid charging: only allowed during free/cheap import window
        slot_grid_charge = False
        if grid_charging_enabled:
            if free_start_min is not None and free_end_min is not None:
                slot_grid_charge = free_start_min <= slot_min < free_end_min

        export_rate.append(slot_export_rate)
        import_rate.append(slot_import_rate)
        grid_charge_allowed.append(slot_grid_charge)

    return TariffSchedule(
        export_rate=export_rate,
        import_rate=import_rate,
        grid_charge_allowed=grid_charge_allowed,
    )


def _solve_lp(opt_input: OptimizationInput) -> OptimizationResult:
    """Run the LP solver in a thread (blocking scipy call)."""
    try:
        from scipy.optimize import linprog
    except ImportError:
        return OptimizationResult(
            slots=[],
            estimated_export_revenue=0.0,
            energy_security_score=0.0,
            forecast_confidence=0.0,
            solve_time_ms=0.0,
            problem_size=0,
            objective_value=0.0,
            success=False,
            message="scipy not installed — run: pip install scipy",
        )

    t_start = time.monotonic()

    T = opt_input.n_slots
    n_vars = N_VARS_PER_SLOT * T

    # ------------------------------------------------------------------
    # Objective: minimize c @ x
    # ------------------------------------------------------------------
    c = np.zeros(n_vars)
    soc_weight = 0.01  # small weight to prefer holding charge

    for t in range(T):
        base = t
        # Export earns revenue → negative cost
        c[IDX_EXPORT * T + t] = -opt_input.tariff.export_rate[t]
        # Grid import costs money
        c[IDX_GRID_IMPORT * T + t] = opt_input.tariff.import_rate[t]
        # Grid charging costs money
        c[IDX_CHARGE_GRID * T + t] = opt_input.tariff.import_rate[t]
        # Soft SOC preference (conservatism): reward holding higher SOC
        c[IDX_SOC * T + t] = -(1.0 - opt_input.aggressiveness) * soc_weight

    # ------------------------------------------------------------------
    # Variable bounds
    # ------------------------------------------------------------------
    bounds = []

    for t in range(T):
        # export[t]
        bounds.append((0.0, opt_input.max_export_kwh))
    for t in range(T):
        # home_discharge[t]
        bounds.append((0.0, opt_input.max_discharge_kwh))
    for t in range(T):
        # charge_solar[t]
        solar_surplus = max(0.0, opt_input.solar_kwh[t] - opt_input.load_kwh[t])
        bounds.append((0.0, solar_surplus))
    for t in range(T):
        # charge_grid[t]
        max_grid = opt_input.max_charge_kwh if opt_input.tariff.grid_charge_allowed[t] else 0.0
        bounds.append((0.0, max_grid))
    for t in range(T):
        # grid_import[t]
        bounds.append((0.0, None))
    for t in range(T):
        # soc[t]
        bounds.append((opt_input.min_soc_kwh, opt_input.capacity_kwh))

    # ------------------------------------------------------------------
    # Equality constraints: SOC dynamics
    # A_eq @ x = b_eq  (T equations)
    # ------------------------------------------------------------------
    A_eq = np.zeros((T, n_vars))
    b_eq = np.zeros(T)

    for t in range(T):
        # soc[t] - charge_solar[t] - charge_grid[t] + export[t] + home_dis[t] = prev_soc
        A_eq[t, IDX_SOC * T + t] = 1.0
        A_eq[t, IDX_CHARGE_SOLAR * T + t] = -1.0
        A_eq[t, IDX_CHARGE_GRID * T + t] = -1.0
        A_eq[t, IDX_EXPORT * T + t] = 1.0
        A_eq[t, IDX_HOME_DIS * T + t] = 1.0
        if t == 0:
            b_eq[t] = opt_input.initial_soc_kwh
        else:
            A_eq[t, IDX_SOC * T + (t - 1)] = -1.0
            b_eq[t] = 0.0

    # ------------------------------------------------------------------
    # Inequality constraints: A_ub @ x <= b_ub
    # ------------------------------------------------------------------
    ineq_rows = []
    ineq_rhs = []

    for t in range(T):
        row = np.zeros(n_vars)
        # 1. Total discharge limit: export[t] + home_dis[t] <= max_discharge
        row[IDX_EXPORT * T + t] = 1.0
        row[IDX_HOME_DIS * T + t] = 1.0
        ineq_rows.append(row)
        ineq_rhs.append(opt_input.max_discharge_kwh)

        # 2. Total charge limit: charge_solar[t] + charge_grid[t] <= max_charge
        row = np.zeros(n_vars)
        row[IDX_CHARGE_SOLAR * T + t] = 1.0
        row[IDX_CHARGE_GRID * T + t] = 1.0
        ineq_rows.append(row)
        ineq_rhs.append(opt_input.max_charge_kwh)

        # 3. Deficit coverage: -home_dis[t] - grid_import[t] <= -deficit
        deficit = max(0.0, opt_input.load_kwh[t] - opt_input.solar_kwh[t])
        if deficit > 0:
            row = np.zeros(n_vars)
            row[IDX_HOME_DIS * T + t] = -1.0
            row[IDX_GRID_IMPORT * T + t] = -1.0
            ineq_rows.append(row)
            ineq_rhs.append(-deficit)

    # 4. Energy security constraint at bridge point:
    #    soc[bridge_slot] >= energy_needed
    #    → -soc[bridge_slot] <= -energy_needed
    bridge = min(opt_input.bridge_slot, T - 1)
    energy_needed = min(opt_input.energy_needed_kwh, opt_input.capacity_kwh)
    if energy_needed > opt_input.min_soc_kwh:
        row = np.zeros(n_vars)
        row[IDX_SOC * T + bridge] = -1.0
        ineq_rows.append(row)
        ineq_rhs.append(-energy_needed)

    A_ub = np.array(ineq_rows) if ineq_rows else None
    b_ub = np.array(ineq_rhs) if ineq_rows else None

    # ------------------------------------------------------------------
    # Solve
    # ------------------------------------------------------------------
    options = {
        "time_limit": opt_input.solver_timeout,
        "disp": False,
    }

    result = linprog(
        c,
        A_ub=A_ub,
        b_ub=b_ub,
        A_eq=A_eq,
        b_eq=b_eq,
        bounds=bounds,
        method="highs",
        options=options,
    )

    solve_ms = (time.monotonic() - t_start) * 1000

    if not result.success:
        _LOGGER.warning("LP solver did not converge: %s", result.message)
        return OptimizationResult(
            slots=[],
            estimated_export_revenue=0.0,
            energy_security_score=0.0,
            forecast_confidence=1.0,
            solve_time_ms=solve_ms,
            problem_size=n_vars,
            objective_value=0.0,
            success=False,
            message=result.message,
        )

    x = result.x

    # ------------------------------------------------------------------
    # Extract slots from solution
    # ------------------------------------------------------------------
    slots = []
    total_revenue = 0.0

    for t in range(T):
        exp_kwh = x[IDX_EXPORT * T + t]
        home_dis_kwh = x[IDX_HOME_DIS * T + t]
        charge_solar_kwh = x[IDX_CHARGE_SOLAR * T + t]
        charge_grid_kwh = x[IDX_CHARGE_GRID * T + t]
        grid_import_kwh = x[IDX_GRID_IMPORT * T + t]
        soc_kwh = x[IDX_SOC * T + t]

        soc_pct = (soc_kwh / opt_input.capacity_kwh) * 100.0
        net_kwh = (charge_solar_kwh + charge_grid_kwh) - (exp_kwh + home_dis_kwh)

        total_charge = charge_solar_kwh + charge_grid_kwh
        total_discharge = exp_kwh + home_dis_kwh
        threshold = 0.02  # kWh threshold to determine action

        if exp_kwh >= threshold:
            action = ACTION_EXPORT
            power_kw = exp_kwh / opt_input.slot_hours
        elif total_discharge >= threshold:
            action = ACTION_DISCHARGE
            power_kw = -total_discharge / opt_input.slot_hours
        elif total_charge >= threshold:
            action = ACTION_CHARGE
            power_kw = total_charge / opt_input.slot_hours
        else:
            action = ACTION_HOLD
            power_kw = 0.0

        slot_revenue = (
            exp_kwh * opt_input.tariff.export_rate[t]
            - grid_import_kwh * opt_input.tariff.import_rate[t]
            - charge_grid_kwh * opt_input.tariff.import_rate[t]
        )
        total_revenue += slot_revenue

        slots.append(SlotResult(
            start="",  # Filled in by coordinator with actual datetimes
            end="",
            action=action,
            power_kw=round(power_kw, 3),
            projected_soc=round(soc_pct, 1),
            expected_solar_kwh=round(opt_input.solar_kwh[t], 3),
            expected_consumption_kwh=round(opt_input.load_kwh[t], 3),
            net_energy_kwh=round(net_kwh, 3),
        ))

    # Energy security score: SOC at bridge point vs needed
    bridge = min(opt_input.bridge_slot, T - 1)
    bridge_soc_kwh = x[IDX_SOC * T + bridge]
    available = bridge_soc_kwh - opt_input.min_soc_kwh
    needed = max(0.0, opt_input.energy_needed_kwh - opt_input.min_soc_kwh)
    security_score = min(1.0, available / needed) if needed > 0 else 1.0

    return OptimizationResult(
        slots=slots,
        estimated_export_revenue=round(total_revenue, 4),
        energy_security_score=round(security_score, 3),
        forecast_confidence=1.0,  # Set by caller after weather modifier applied
        solve_time_ms=round(solve_ms, 1),
        problem_size=n_vars,
        objective_value=round(float(result.fun), 4),
        success=True,
        message="ok",
    )


async def async_optimize(
    hass: HomeAssistant,
    opt_input: OptimizationInput,
) -> OptimizationResult:
    """Run the LP solver asynchronously in a thread pool executor."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(_executor, _solve_lp, opt_input)


def build_optimization_input(
    config: dict,
    options: dict,
    initial_soc_pct: float,
    solar_kwh_per_slot: list[float],
    load_kwh_per_slot: list[float],
    tariff: TariffSchedule,
    bridge_slot: int,
    energy_needed_kwh: float,
    start_dt: datetime,
) -> OptimizationInput:
    """Build OptimizationInput from HA config entry data and runtime inputs."""

    # Merge config and options (options override config)
    cfg = {**config, **options}

    slot_minutes = int(cfg.get(CONF_SLOT_GRANULARITY_MINUTES, DEFAULT_SLOT_GRANULARITY_MINUTES))
    lookahead_hours = int(cfg.get(CONF_LOOKAHEAD_HOURS, DEFAULT_LOOKAHEAD_HOURS))
    n_slots = (lookahead_hours * 60) // slot_minutes
    slot_hours = slot_minutes / 60.0

    capacity_kwh = float(cfg.get(CONF_BATTERY_CAPACITY_KWH, 10.0))
    min_soc_pct = float(cfg.get(CONF_MIN_SOC_FLOOR_PERCENT, DEFAULT_MIN_SOC_FLOOR_PERCENT))
    min_soc_kwh = (min_soc_pct / 100.0) * capacity_kwh

    initial_soc_kwh = (initial_soc_pct / 100.0) * capacity_kwh

    max_charge_kw = float(cfg.get(CONF_MAX_CHARGE_RATE_KW, DEFAULT_MAX_CHARGE_RATE_KW))
    max_discharge_kw = float(cfg.get(CONF_MAX_DISCHARGE_RATE_KW, DEFAULT_MAX_DISCHARGE_RATE_KW))
    max_export_kw = float(cfg.get(CONF_MAX_EXPORT_LIMIT_KW, DEFAULT_MAX_EXPORT_LIMIT_KW))

    aggressiveness = float(cfg.get(CONF_AGGRESSIVENESS, DEFAULT_AGGRESSIVENESS))
    solver_timeout = float(cfg.get(CONF_SOLVER_TIMEOUT_SECONDS, DEFAULT_SOLVER_TIMEOUT_SECONDS))

    # Truncate lists to n_slots
    solar = (solar_kwh_per_slot + [0.0] * n_slots)[:n_slots]
    load = (load_kwh_per_slot + [0.5 * slot_hours] * n_slots)[:n_slots]

    return OptimizationInput(
        n_slots=n_slots,
        slot_hours=slot_hours,
        initial_soc_kwh=initial_soc_kwh,
        capacity_kwh=capacity_kwh,
        min_soc_kwh=min_soc_kwh,
        max_charge_kwh=max_charge_kw * slot_hours,
        max_discharge_kwh=max_discharge_kw * slot_hours,
        max_export_kwh=max_export_kw * slot_hours,
        solar_kwh=solar,
        load_kwh=load,
        tariff=tariff,
        aggressiveness=aggressiveness,
        solver_timeout=solver_timeout,
        bridge_slot=bridge_slot,
        energy_needed_kwh=energy_needed_kwh,
    )
