import numpy as np
import pandas as pd
from typing import Tuple

from helios_core.simulate.metrics import RiskMetrics
from helios_core.simulate.backtester import WalkForwardBacktester
from helios_core.simulate.agents import TradingAgent

class DummyAgent(TradingAgent):
    """
    An agent that performs exactly 1 cycle per 24h horizon
    Charge 1MW at t=0, discharge 1MW at t=1.
    """
    def act(self, current_soc: float, price_forecast: np.ndarray) -> Tuple[np.ndarray, np.ndarray, float]:
        horizon = len(price_forecast)
        p_ch = np.zeros(horizon)
        p_dis = np.zeros(horizon)

        # Charge 1 at index 0, Discharge 1 at index 1
        if horizon > 1:
            p_ch[0] = 1.0
            p_dis[1] = 1.0

        return p_ch, p_dis, 0.0

def test_risk_metrics_calculation() -> None:
    # CAPEX: 300,000 EUR
    # Cycles: 5000
    # Capacity: 10 MWh
    # LCOS Marginal: 300,000 / (5000 * 10 * 2) = 3 EUR / MWh throughput
    metrics = RiskMetrics(capex_eur=300000.0, cycle_life=5000, capacity_mwh=10.0)

    assert np.isclose(metrics.marginal_lcos, 3.0)

    # Simulate a run with 20 MWh throughput (1 full equivalent cycle)
    efc = metrics.calculate_efc(20.0)
    assert np.isclose(efc, 1.0)

    # Simulate netting 100 EUR
    # Degradation Cost = 1.0 cycle * 3 EUR * 20 MWh throughput?
    # Actually, the formula in implementation says:
    # degradation_cost = efc * marginal_lcos * (capacity_mwh * 2.0)
    # 1.0 * 3.0 * 20.0 = 60 EUR
    rodc = metrics.calculate_rodc(100.0, efc)
    assert np.isclose(rodc, 100.0 / 60.0)

def test_backtester_no_leakage() -> None:
    # 3 days of data = 72 hours
    idx = pd.date_range("2022-08-01", periods=72, freq="h")
    prices = np.linspace(100, 200, 72)
    df = pd.DataFrame({'Price_EUR_MWh': prices}, index=idx)

    agent = DummyAgent()
    metrics = RiskMetrics(capex_eur=300000.0, cycle_life=5000, capacity_mwh=10.0)

    backtester = WalkForwardBacktester(df, agent, metrics, horizon=24)
    # It should iterate 72 - 24 = 48 times exactly.

    report = backtester.run()

    assert len(backtester.history) == 48

    # Checking EFC
    # The dummy agent charges 1.0 MW at t=0 (step 0 of forecast).
    # Since backtester strictly executes step 0, it will ONLY ever execute p_ch[0] = 1.0
    # Thus throughput is 1.0 MWh per step.
    # Total throughput = 48 steps * 1.0 MWh = 48 MWh.
    # EFC = 48 / (10 * 2) = 2.4 cycles.
    assert np.isclose(report["EFC (Cycles)"], 2.4)
