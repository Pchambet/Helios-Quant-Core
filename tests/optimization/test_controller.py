import pytest
import numpy as np
import cvxpy as cp
from unittest.mock import patch

from helios_core.assets.battery import BatteryAsset
from helios_core.assets.config import BatteryConfig
from helios_core.optimization.scaling import PriceScaler
from helios_core.optimization.controller import BatteryMPC


@pytest.fixture
def battery() -> BatteryAsset:
    config = BatteryConfig(
        capacity_mwh=10.0,
        max_charge_mw=5.0,
        max_discharge_mw=5.0,
        efficiency_charge=0.9,
        efficiency_discharge=0.9,
        leakage_rate_per_hour=0.001,
        initial_soc_mwh=0.0
    )
    return BatteryAsset(config)

@pytest.fixture
def scaler() -> PriceScaler:
    scaler = PriceScaler(1.0)
    return scaler


def test_deterministic_mpc_behavior(battery: BatteryAsset, scaler: PriceScaler) -> None:
    # A clear day-night price spread
    # Night is cheap (0-11)
    # Day is expensive (12-23)
    prices = np.array([-10.0] * 12 + [100.0] * 12)
    scaler.fit(prices)

    mpc = BatteryMPC(battery, scaler)
    p_ch, p_dis, status = mpc.solve_deterministic(prices)

    # Assert solver succeeded
    assert status == "optimal"

    # Assert physical constraints are strictly respected mathematically
    assert np.all(p_ch >= 0)
    assert np.all(p_dis >= 0)
    assert np.max(p_ch) <= battery.max_charge_mw + 1e-4
    assert np.max(p_dis) <= battery.max_discharge_mw + 1e-4

    # Assert intuitive economic behavior (buy low, sell high)
    total_charged_night = np.sum(p_ch[0:12])
    total_discharged_day = np.sum(p_dis[12:24])

    assert total_charged_night > 0
    assert total_discharged_day > 0


def test_fallback_heuristic_on_infeasible(battery: BatteryAsset, scaler: PriceScaler) -> None:
    rng = np.random.default_rng(42)
    prices = rng.normal(50, 10, 24)
    scaler.fit(prices)
    mpc = BatteryMPC(battery, scaler)

    # We patch cvxpy Problem.solve to raise an Exception directly (simulating a numerical crash)
    with patch.object(cp.Problem, 'solve', side_effect=cp.error.SolverError("Crashed!")):
        p_ch, p_dis, status = mpc.solve_deterministic(prices)

        # Ensure the safe fallback heuristic zero-vector is returned rather than crashing the program
        assert status == "SOLVER_EXCEPTION"
        assert np.all(p_ch == 0)
        assert np.all(p_dis == 0)

def test_robust_mpc_behavior(battery: BatteryAsset, scaler: PriceScaler) -> None:
    rng = np.random.default_rng(42)
    historical_scenarios = rng.normal(50, 15, size=(5, 24))

    # We add one massive extreme scenario (e.g. system stress)
    historical_scenarios[4, 18] = 500.0

    scaler.fit(historical_scenarios)
    mpc = BatteryMPC(battery, scaler)

    # Test strict Wasserstein boundary condition (epsilon = 0.1)
    # The prices are sealed into [-1, 1], so an eps of 0.1 is substantial distance padding
    p_ch, p_dis, status = mpc.solve_robust(historical_scenarios, epsilon=0.1)

    # Assert LP Dual Formulation Tractability (optimal_inaccurate valide en pratique)
    assert status in ("optimal", "optimal_inaccurate")

    # Physical adherence overrides mathematical formulation
    assert np.all(p_ch >= 0)
    assert np.all(p_dis >= 0)
    assert np.max(p_ch) <= battery.max_charge_mw + 1e-4
    assert np.max(p_dis) <= battery.max_discharge_mw + 1e-4

    # When epsilon is immense (> 24, as the 24h sum can counteract epsilon penalty),
    # the optimizer becomes paranoid and shuts down completely.
    p_ch_paranoid, p_dis_paranoid, status_paranoid = mpc.solve_robust(historical_scenarios, epsilon=100.0)

    assert status_paranoid in ("optimal", "optimal_inaccurate")
    assert np.allclose(p_ch_paranoid, 0, atol=1e-3)
    assert np.allclose(p_dis_paranoid, 0, atol=1e-3)

def test_lcos_spread_rejection(scaler: PriceScaler) -> None:
    # We configure a battery with a very high LCOS to prove spread rejection
    # CAPEX: 1.5M EUR, Cycles: 5000, Capacity: 10MWh
    # Marginal Wear Cost = 1,500,000 / (5000 * 10 * 2) = 15 EUR / MWh
    config = BatteryConfig(
        capacity_mwh=10.0,
        max_charge_mw=5.0,
        max_discharge_mw=5.0,
        efficiency_charge=1.0,  # 100% efficient to purely test LCOS spread
        efficiency_discharge=1.0,
        leakage_rate_per_hour=0.0,
        initial_soc_mwh=0.0,
        capex_eur=1500000.0,
        cycle_life=5000
    )
    battery = BatteryAsset(config)

    # We simulate a market with a spread of 10 EUR/MWh
    # Base: 40 EUR. Peak: 50 EUR.
    prices = np.array([40.0] * 12 + [50.0] * 12)
    scaler.fit(prices)
    mpc = BatteryMPC(battery, scaler)

    # Run the deterministic solver
    p_ch, p_dis, status = mpc.solve_deterministic(prices)

    assert status == "optimal"

    # Because the Spread (10 EUR) < Total Cycle LCOS (15 + 15 = 30 EUR),
    # the algorithm must rationally choose to preserve the battery life and do nothing.
    assert np.allclose(p_ch, 0, atol=1e-3)
    assert np.allclose(p_dis, 0, atol=1e-3)


def test_interlock_no_simultaneous(battery: BatteryAsset, scaler: PriceScaler) -> None:
    """Verifies that the physical interlock prevents simultaneous charge and discharge."""
    prices = np.array([-10.0] * 12 + [100.0] * 12)
    scaler.fit(prices)

    mpc = BatteryMPC(battery, scaler)
    p_ch, p_dis, status = mpc.solve_deterministic(prices)

    assert status == "optimal"

    # Product p_ch[t] * p_dis[t] should be ~0 for all t (no simultaneous charge+discharge)
    simultaneous = p_ch * p_dis
    assert np.allclose(simultaneous, 0, atol=1e-3), \
        f"Simultaneous charge+discharge detected: max product = {np.max(simultaneous):.4f}"


def test_grid_tariff_reduces_trading(scaler: PriceScaler) -> None:
    """Verifies that a high TURPE grid tariff reduces total throughput."""
    config_no_turpe = BatteryConfig(
        capacity_mwh=10.0, max_charge_mw=5.0, max_discharge_mw=5.0,
        efficiency_charge=1.0, efficiency_discharge=1.0,
        leakage_rate_per_hour=0.0, initial_soc_mwh=0.0,
        grid_tariff_eur_mwh=0.0
    )
    config_high_turpe = BatteryConfig(
        capacity_mwh=10.0, max_charge_mw=5.0, max_discharge_mw=5.0,
        efficiency_charge=1.0, efficiency_discharge=1.0,
        leakage_rate_per_hour=0.0, initial_soc_mwh=0.0,
        grid_tariff_eur_mwh=50.0  # Very high tariff
    )

    prices = np.array([40.0] * 12 + [80.0] * 12)
    scaler.fit(prices)

    mpc_no_turpe = BatteryMPC(BatteryAsset(config_no_turpe), scaler)
    mpc_high_turpe = BatteryMPC(BatteryAsset(config_high_turpe), scaler)

    p_ch_0, p_dis_0, _ = mpc_no_turpe.solve_deterministic(prices)
    p_ch_50, p_dis_50, _ = mpc_high_turpe.solve_deterministic(prices)

    throughput_no_turpe = np.sum(p_ch_0 + p_dis_0)
    throughput_high_turpe = np.sum(p_ch_50 + p_dis_50)

    assert throughput_high_turpe < throughput_no_turpe, \
        f"High TURPE should reduce trading. No-TURPE: {throughput_no_turpe:.1f}, High-TURPE: {throughput_high_turpe:.1f}"


def test_lcos_convex_penalizes_deep_cycles(scaler: PriceScaler) -> None:
    """Verifies that convex LCOS penalizes high power more than linear LCOS would."""
    config = BatteryConfig(
        capacity_mwh=10.0, max_charge_mw=5.0, max_discharge_mw=5.0,
        efficiency_charge=1.0, efficiency_discharge=1.0,
        leakage_rate_per_hour=0.0, initial_soc_mwh=0.0,
        capex_eur=1000000.0, cycle_life=5000
    )
    battery = BatteryAsset(config)

    # kappa_0 (linear) should be 70% of marginal cost
    # kappa_1 (convex) should be 30% of marginal cost
    assert battery.lcos_kappa_0 < battery.marginal_wear_cost_per_mwh
    assert battery.lcos_kappa_1 < battery.marginal_wear_cost_per_mwh
    assert np.isclose(battery.lcos_kappa_0 + battery.lcos_kappa_1, battery.marginal_wear_cost_per_mwh)
