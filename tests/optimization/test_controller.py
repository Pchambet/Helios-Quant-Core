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
    scaler = PriceScaler((-1, 1))
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
    prices = np.random.normal(50, 10, 24)
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
    # Simulating 5 scenarios of 24h prices
    # We create a volatile environment with positive and negative spikes
    historical_scenarios = np.random.normal(50, 15, size=(5, 24))

    # We add one massive extreme scenario (e.g. system stress)
    historical_scenarios[4, 18] = 500.0

    scaler.fit(historical_scenarios)
    mpc = BatteryMPC(battery, scaler)

    # Test strict Wasserstein boundary condition (epsilon = 0.1)
    # The prices are sealed into [-1, 1], so an eps of 0.1 is substantial distance padding
    p_ch, p_dis, status = mpc.solve_robust(historical_scenarios, epsilon=0.1)

    # Assert LP Dual Formulation Tractability
    assert status == "optimal"

    # Physical adherence overrides mathematical formulation
    assert np.all(p_ch >= 0)
    assert np.all(p_dis >= 0)
    assert np.max(p_ch) <= battery.max_charge_mw + 1e-4
    assert np.max(p_dis) <= battery.max_discharge_mw + 1e-4

    # When epsilon is immense (> 24, as the 24h sum can counteract epsilon penalty),
    # the optimizer becomes paranoid and shuts down completely.
    p_ch_paranoid, p_dis_paranoid, status_paranoid = mpc.solve_robust(historical_scenarios, epsilon=100.0)

    assert status_paranoid == "optimal"
    assert np.allclose(p_ch_paranoid, 0, atol=1e-3)
    assert np.allclose(p_dis_paranoid, 0, atol=1e-3)
