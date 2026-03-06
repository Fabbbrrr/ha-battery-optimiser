"""Tests for the pure-Python LP solver (_linprog) and battery optimizer.

These tests validate the simplex solver independently of Home Assistant,
then test the full battery scheduling LP formulation.
"""
import numpy as np
import pytest

# conftest.py handles mocking homeassistant so we can import the optimizer
from battery_optimizer.optimizer import (
    _linprog,
    _LPResult,
    _solve_lp,
    OptimizationInput,
    TariffSchedule,
    SlotResult,
    IDX_EXPORT,
    IDX_HOME_DIS,
    IDX_CHARGE_SOLAR,
    IDX_CHARGE_GRID,
    IDX_GRID_IMPORT,
    IDX_SOC,
    N_VARS_PER_SLOT,
)


# -----------------------------------------------------------------------
# _linprog solver tests
# -----------------------------------------------------------------------

class TestLinprogBasic:
    """Basic LP problems with known analytical solutions."""

    def test_simple_2var(self):
        """min -x - 2y s.t. x + y <= 4, x <= 3, y <= 3, x,y >= 0.
        Optimal: x=1, y=3, obj=-7.
        """
        c = np.array([-1.0, -2.0])
        A_ub = np.array([[1.0, 1.0], [1.0, 0.0], [0.0, 1.0]])
        b_ub = np.array([4.0, 3.0, 3.0])
        bounds = [(0, None), (0, None)]

        result = _linprog(c, A_ub=A_ub, b_ub=b_ub, bounds=bounds)

        assert result.success
        assert abs(result.fun - (-7.0)) < 1e-6
        assert abs(result.x[0] - 1.0) < 1e-6
        assert abs(result.x[1] - 3.0) < 1e-6

    def test_equality_constraint(self):
        """min x + y s.t. x + y = 10, x >= 2, y >= 3."""
        c = np.array([1.0, 1.0])
        A_eq = np.array([[1.0, 1.0]])
        b_eq = np.array([10.0])
        bounds = [(2, None), (3, None)]

        result = _linprog(c, A_eq=A_eq, b_eq=b_eq, bounds=bounds)

        assert result.success
        assert abs(result.fun - 10.0) < 1e-6
        assert abs(result.x[0] + result.x[1] - 10.0) < 1e-6

    def test_bounds_only(self):
        """min -3x - 5y with 0 <= x <= 4, 0 <= y <= 6.
        Optimal: x=4, y=6, obj=-42.
        """
        c = np.array([-3.0, -5.0])
        bounds = [(0, 4), (0, 6)]

        result = _linprog(c, bounds=bounds)

        assert result.success
        assert abs(result.fun - (-42.0)) < 1e-6
        assert abs(result.x[0] - 4.0) < 1e-6
        assert abs(result.x[1] - 6.0) < 1e-6

    def test_mixed_constraints(self):
        """min -x - y s.t. x + 2y <= 14, 3x + 2y <= 18, x,y >= 0.
        Optimal: x=2, y=6, obj=-8.
        """
        c = np.array([-1.0, -1.0])
        A_ub = np.array([[1.0, 2.0], [3.0, 2.0]])
        b_ub = np.array([14.0, 18.0])
        bounds = [(0, None), (0, None)]

        result = _linprog(c, A_ub=A_ub, b_ub=b_ub, bounds=bounds)

        assert result.success
        assert abs(result.fun - (-8.0)) < 1e-6

    def test_infeasible(self):
        """x + y = 10 and x + y = 5 is infeasible."""
        c = np.array([1.0, 1.0])
        A_eq = np.array([[1.0, 1.0], [1.0, 1.0]])
        b_eq = np.array([10.0, 5.0])
        bounds = [(0, None), (0, None)]

        result = _linprog(c, A_eq=A_eq, b_eq=b_eq, bounds=bounds)
        assert not result.success

    def test_nonzero_lower_bounds(self):
        """min x + y s.t. x >= 5, y >= 3, x + y <= 20.
        Optimal: x=5, y=3, obj=8.
        """
        c = np.array([1.0, 1.0])
        A_ub = np.array([[1.0, 1.0]])
        b_ub = np.array([20.0])
        bounds = [(5, None), (3, None)]

        result = _linprog(c, A_ub=A_ub, b_ub=b_ub, bounds=bounds)

        assert result.success
        assert abs(result.fun - 8.0) < 1e-6
        assert result.x[0] >= 5.0 - 1e-6
        assert result.x[1] >= 3.0 - 1e-6

    def test_negative_rhs_inequality(self):
        """Constraints with negative RHS (deficit coverage in battery LP).
        min x + y s.t. -x - y <= -5, x,y >= 0.
        Equivalent to: x + y >= 5.
        """
        c = np.array([1.0, 1.0])
        A_ub = np.array([[-1.0, -1.0]])
        b_ub = np.array([-5.0])
        bounds = [(0, None), (0, None)]

        result = _linprog(c, A_ub=A_ub, b_ub=b_ub, bounds=bounds)

        assert result.success
        assert abs(result.fun - 5.0) < 1e-6

    def test_single_variable(self):
        """min -x s.t. x <= 10, x >= 0. Optimal: x=10, obj=-10."""
        c = np.array([-1.0])
        bounds = [(0, 10)]

        result = _linprog(c, bounds=bounds)

        assert result.success
        assert abs(result.fun - (-10.0)) < 1e-6

    def test_zero_objective(self):
        """Feasibility check: min 0 s.t. x + y = 1, x,y >= 0."""
        c = np.array([0.0, 0.0])
        A_eq = np.array([[1.0, 1.0]])
        b_eq = np.array([1.0])
        bounds = [(0, None), (0, None)]

        result = _linprog(c, A_eq=A_eq, b_eq=b_eq, bounds=bounds)

        assert result.success
        assert abs(result.x[0] + result.x[1] - 1.0) < 1e-6


class TestLinprogMedium:
    """Medium-sized problems closer to the battery LP structure."""

    def test_chain_equality_constraints(self):
        """SOC-like chain: soc[t] = soc[t-1] + charge[t] - discharge[t].
        5 slots, initial SOC=5, capacity=10, must end at SOC=5.
        """
        T = 5
        n = 3 * T  # [charge(T), discharge(T), soc(T)]
        c = np.zeros(n)
        # Minimise total discharge
        for t in range(T):
            c[T + t] = 1.0  # discharge cost

        # SOC dynamics
        A_eq = np.zeros((T + 1, n))
        b_eq = np.zeros(T + 1)

        for t in range(T):
            A_eq[t, 2 * T + t] = 1.0       # soc[t]
            A_eq[t, t] = -1.0               # -charge[t]
            A_eq[t, T + t] = 1.0            # +discharge[t]
            if t == 0:
                b_eq[t] = 5.0  # initial SOC
            else:
                A_eq[t, 2 * T + t - 1] = -1.0  # -soc[t-1]

        # Final SOC >= 5 (as equality for test)
        A_eq[T, 2 * T + T - 1] = 1.0
        b_eq[T] = 5.0

        bounds = []
        for t in range(T):
            bounds.append((0.0, 2.0))  # charge
        for t in range(T):
            bounds.append((0.0, 2.0))  # discharge
        for t in range(T):
            bounds.append((0.0, 10.0))  # soc

        result = _linprog(c, A_eq=A_eq, b_eq=b_eq, bounds=bounds)

        assert result.success
        # No need to discharge if charge available and SOC stays at 5
        soc_final = result.x[2 * T + T - 1]
        assert abs(soc_final - 5.0) < 1e-4

    def test_20var_problem(self):
        """20-variable LP to test solver on slightly larger problems."""
        n = 20
        np.random.seed(42)
        c = np.random.randn(n)
        A_ub = np.random.randn(10, n)
        b_ub = np.abs(np.random.randn(10)) * 5
        bounds = [(0, 10) for _ in range(n)]

        result = _linprog(c, A_ub=A_ub, b_ub=b_ub, bounds=bounds)

        assert result.success
        # Check feasibility
        x = result.x
        assert np.all(x >= -1e-6)
        assert np.all(x <= 10 + 1e-6)
        assert np.all(A_ub @ x <= b_ub + 1e-6)


# -----------------------------------------------------------------------
# Battery optimizer (_solve_lp) tests
# -----------------------------------------------------------------------

def _make_input(
    n_slots: int = 4,
    slot_hours: float = 0.5,
    initial_soc_kwh: float = 5.0,
    capacity_kwh: float = 10.0,
    min_soc_kwh: float = 1.0,
    max_charge_kwh: float = 2.5,
    max_discharge_kwh: float = 2.5,
    max_export_kwh: float = 2.5,
    solar_kwh: list[float] | None = None,
    load_kwh: list[float] | None = None,
    export_rate: list[float] | None = None,
    import_rate: list[float] | None = None,
    grid_charge_allowed: list[bool] | None = None,
    aggressiveness: float = 0.5,
    bridge_slot: int = 0,
    energy_needed_kwh: float = 0.0,
) -> OptimizationInput:
    """Helper to build OptimizationInput for tests."""
    if solar_kwh is None:
        solar_kwh = [0.0] * n_slots
    if load_kwh is None:
        load_kwh = [0.5] * n_slots
    if export_rate is None:
        export_rate = [0.05] * n_slots
    if import_rate is None:
        import_rate = [0.30] * n_slots
    if grid_charge_allowed is None:
        grid_charge_allowed = [False] * n_slots

    return OptimizationInput(
        n_slots=n_slots,
        slot_hours=slot_hours,
        initial_soc_kwh=initial_soc_kwh,
        capacity_kwh=capacity_kwh,
        min_soc_kwh=min_soc_kwh,
        max_charge_kwh=max_charge_kwh,
        max_discharge_kwh=max_discharge_kwh,
        max_export_kwh=max_export_kwh,
        solar_kwh=solar_kwh,
        load_kwh=load_kwh,
        tariff=TariffSchedule(
            export_rate=export_rate,
            import_rate=import_rate,
            grid_charge_allowed=grid_charge_allowed,
        ),
        aggressiveness=aggressiveness,
        solver_timeout=30.0,
        bridge_slot=bridge_slot,
        energy_needed_kwh=energy_needed_kwh,
    )


class TestBatteryOptimizer:
    """End-to-end tests for the battery scheduling LP."""

    def test_basic_solve(self):
        """Solver produces a valid schedule with correct number of slots."""
        inp = _make_input(n_slots=4)
        result = _solve_lp(inp)

        assert result.success
        assert len(result.slots) == 4
        assert result.solve_time_ms > 0

    def test_soc_never_below_floor(self):
        """SOC should never go below min_soc_kwh."""
        inp = _make_input(
            n_slots=8,
            initial_soc_kwh=3.0,
            min_soc_kwh=2.0,
            load_kwh=[1.0] * 8,
            solar_kwh=[0.0] * 8,
        )
        result = _solve_lp(inp)

        assert result.success
        for slot in result.slots:
            soc_kwh = (slot.projected_soc / 100.0) * inp.capacity_kwh
            assert soc_kwh >= inp.min_soc_kwh - 0.1, (
                f"SOC {soc_kwh:.2f} kWh below floor {inp.min_soc_kwh}"
            )

    def test_soc_never_above_capacity(self):
        """SOC should never exceed battery capacity."""
        inp = _make_input(
            n_slots=4,
            initial_soc_kwh=9.0,
            capacity_kwh=10.0,
            solar_kwh=[5.0, 5.0, 5.0, 5.0],
            load_kwh=[0.5, 0.5, 0.5, 0.5],
        )
        result = _solve_lp(inp)

        assert result.success
        for slot in result.slots:
            soc_kwh = (slot.projected_soc / 100.0) * inp.capacity_kwh
            assert soc_kwh <= inp.capacity_kwh + 0.1

    def test_exports_during_bonus_window(self):
        """With high export rates, optimizer should prefer exporting."""
        inp = _make_input(
            n_slots=4,
            initial_soc_kwh=8.0,
            aggressiveness=1.0,
            export_rate=[0.05, 0.05, 0.50, 0.50],  # bonus in slots 2-3
            load_kwh=[0.1, 0.1, 0.1, 0.1],
            solar_kwh=[0.0, 0.0, 0.0, 0.0],
        )
        result = _solve_lp(inp)

        assert result.success
        # At least one slot during bonus should export
        bonus_slots = result.slots[2:4]
        has_export = any(s.action == "export" for s in bonus_slots)
        assert has_export, "Expected export during bonus window"

    def test_charges_from_solar_surplus(self):
        """Battery should charge when solar exceeds load."""
        inp = _make_input(
            n_slots=4,
            initial_soc_kwh=3.0,
            solar_kwh=[3.0, 3.0, 0.0, 0.0],
            load_kwh=[0.5, 0.5, 0.5, 0.5],
        )
        result = _solve_lp(inp)

        assert result.success
        # SOC should increase in solar slots
        assert result.slots[0].projected_soc > 30.0 or result.slots[1].projected_soc > 30.0

    def test_grid_import_covers_deficit(self):
        """When battery is empty and no solar, grid import covers load."""
        inp = _make_input(
            n_slots=4,
            initial_soc_kwh=1.0,
            min_soc_kwh=1.0,
            solar_kwh=[0.0] * 4,
            load_kwh=[2.0] * 4,
        )
        result = _solve_lp(inp)

        assert result.success
        # Should hold at min SOC - can't discharge below floor
        for slot in result.slots:
            soc_kwh = (slot.projected_soc / 100.0) * inp.capacity_kwh
            assert soc_kwh >= inp.min_soc_kwh - 0.1

    def test_bridge_point_energy_security(self):
        """Bridge constraint ensures enough energy at specified slot."""
        inp = _make_input(
            n_slots=8,
            initial_soc_kwh=5.0,
            bridge_slot=6,
            energy_needed_kwh=4.0,
            solar_kwh=[0.0] * 8,
            load_kwh=[0.3] * 8,
            export_rate=[0.50] * 8,
            aggressiveness=1.0,
        )
        result = _solve_lp(inp)

        assert result.success
        assert result.energy_security_score >= 0.9

    def test_grid_charging_in_free_window(self):
        """Battery charges from grid during free import windows."""
        inp = _make_input(
            n_slots=4,
            initial_soc_kwh=2.0,
            solar_kwh=[0.0] * 4,
            load_kwh=[0.1] * 4,
            import_rate=[0.0, 0.0, 0.30, 0.30],  # free in slots 0-1
            grid_charge_allowed=[True, True, False, False],
        )
        result = _solve_lp(inp)

        assert result.success
        # SOC should increase during free grid charging
        assert result.slots[1].projected_soc > 20.0

    def test_realistic_24h_schedule(self):
        """Full 24h simulation at 30-min slots (48 slots)."""
        n = 48
        # Simulate typical solar bell curve (peak at noon)
        solar = [0.0] * 12  # midnight-6am
        solar += [0.2, 0.5, 1.0, 1.5, 2.5, 3.0, 3.5, 3.5, 3.0, 2.5, 1.5, 1.0]  # 6am-noon
        solar += [0.5, 0.2] + [0.0] * 10  # noon-6pm trailing off
        solar += [0.0] * 12 + [0.0] * 2   # evening to midnight
        solar = solar[:n]

        # Typical load: higher morning + evening
        load = [0.3] * 12  # midnight-6am (12)
        load += [0.5, 0.6, 0.6, 0.5, 0.4, 0.3, 0.3, 0.3, 0.4, 0.5, 0.6, 0.7]  # 6am-noon (12)
        load += [0.7, 0.6, 0.5, 0.5, 0.5, 0.5, 0.7, 0.8, 0.9, 0.9, 0.8, 0.7]  # noon-6pm (12)
        load += [0.5, 0.4, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3, 0.3]  # 6pm-midnight (12)
        load = load[:n]

        # Export bonus 6pm-8pm (slots 36-39)
        export_rate = [0.05] * 36 + [0.45] * 4 + [0.05] * 8
        import_rate = [0.30] * n

        inp = _make_input(
            n_slots=n,
            initial_soc_kwh=5.0,
            solar_kwh=solar,
            load_kwh=load,
            export_rate=export_rate,
            import_rate=import_rate,
        )
        result = _solve_lp(inp)

        assert result.success
        assert len(result.slots) == n
        assert result.solve_time_ms < 30000  # Should solve well within 30s

    def test_empty_solar_no_crash(self):
        """Zero solar and zero load should still produce a valid schedule."""
        inp = _make_input(
            n_slots=4,
            solar_kwh=[0.0] * 4,
            load_kwh=[0.0] * 4,
        )
        result = _solve_lp(inp)

        assert result.success
        assert len(result.slots) == 4

    def test_estimated_revenue_nonnegative_with_export(self):
        """When exporting at a positive rate, revenue should be non-negative."""
        inp = _make_input(
            n_slots=4,
            initial_soc_kwh=8.0,
            aggressiveness=1.0,
            export_rate=[0.50] * 4,
            import_rate=[0.30] * 4,
            load_kwh=[0.0] * 4,
        )
        result = _solve_lp(inp)

        assert result.success
        assert result.estimated_export_revenue >= 0.0
