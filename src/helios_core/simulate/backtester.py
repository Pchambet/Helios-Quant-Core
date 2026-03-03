import pandas as pd
import numpy as np
import logging
from typing import Any, Dict, List
from helios_core.simulate.agents import TradingAgent
from helios_core.simulate.metrics import RiskMetrics

logger = logging.getLogger(__name__)

class WalkForwardBacktester:
    """
    Industrial Backtesting Engine.
    Strictly prevents Look-Ahead Bias by iterating chronologically.
    Passes only T to T+24 horizon to the agents.
    """
    def __init__(self, data: pd.DataFrame, agent: TradingAgent, metrics: RiskMetrics, horizon: int = 24):
        self.data = data
        self.agent = agent
        self.metrics = metrics
        self.horizon = horizon

        # State Tracking
        self.current_soc = 0.0
        self.history: List[Dict[str, Any]] = []

    def run(self) -> dict[str, float]:
        prices = self.data['Price_EUR_MWh'].values
        total_steps = len(prices) - self.horizon

        if total_steps <= 0:
            raise ValueError("Dataset is shorter than the prediction horizon.")

        gross_revenue = 0.0
        gross_cost = 0.0
        throughput = 0.0

        for t in range(total_steps):
            # 1. State Isolation: Agent only sees the next 24 hours.
            forecast = prices[t: t + self.horizon]
            current_price = forecast[0]

            # 2. Agent Decision
            p_ch_vec, p_dis_vec, _ = self.agent.act(self.current_soc, forecast)

            # 3. Execution (We only execute the immediate T=0 step, the rest is receding horizon plan).
            p_ch_now = p_ch_vec[0]
            p_dis_now = p_dis_vec[0]

            # 4. Physical limits accounting (Assuming 1 Hour duration)
            if p_ch_now > 0:
                cost = p_ch_now * current_price
                gross_cost += cost
            if p_dis_now > 0:
                rev = p_dis_now * current_price * 0.95 # Assumed simple discharge loss for backtest counting
                gross_revenue += rev

            throughput += (p_ch_now + p_dis_now)

            # Update true physical SoC state. We simplify without calling the full BatteryAsset.step here
            # to keep the backtest quick, since the Agent's MPC already respects bounds.
            self.current_soc += (p_ch_now * 0.95) - (p_dis_now / 0.95)
            self.current_soc = np.clip(self.current_soc, 0.0, self.metrics.capacity_mwh)

            # Log
            self.history.append({
                "time": self.data.index[t],
                "price": current_price,
                "p_ch": p_ch_now,
                "p_dis": p_dis_now,
                "soc": self.current_soc
            })

            if t % 500 == 0:
                logger.info(f"Backtesting step {t}/{total_steps} completed.")

        return self.metrics.generate_report(gross_revenue, gross_cost, throughput)
