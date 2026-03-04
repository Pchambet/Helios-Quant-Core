import pandas as pd
import numpy as np
import logging
from typing import Any, Dict, List
from helios_core.simulate.agents import TradingAgent
from helios_core.simulate.metrics import RiskMetrics

logger = logging.getLogger(__name__)

class WalkForwardBacktester:
    """
    Industrial Backtesting Engine for the Day-Ahead Market.
    Implements a 48h Receding Horizon using a Seasonal 7-Day SMA Proxy.
    Executes trades in 24h blocks to mirror actual EPEX SPOT market mechanics.
    """
    def __init__(self, data: pd.DataFrame, agent: TradingAgent, metrics: RiskMetrics):
        self.data = data
        self.agent = agent
        self.metrics = metrics

        # State Tracking
        self.current_soc = 0.0
        self.history: List[Dict[str, Any]] = []

    def run(self) -> dict[str, float]:
        prices = self.data['Price_EUR_MWh'].values
        total_steps = len(prices)

        gross_revenue = 0.0
        gross_cost = 0.0
        throughput = 0.0

        # Step by 24h blocks (Day-Ahead Clearing)
        for t in range(0, total_steps, 24):
            # 1. State Isolation: The agent sees the true next 24 hours.
            real_forecast = prices[t: t + 24]

            if len(real_forecast) < 24:
                # Discard incomplete final day
                break

            # 2. Proxy Hallucination: 7-Days SMA for the T+25 to T+48 horizon
            proxy_forecast = np.zeros(24)
            for h in range(24):
                past_vals = []
                for d in range(1, 8):
                    past_idx = t + h - 24 * d
                    if past_idx >= 0:
                        past_vals.append(prices[past_idx])

                if past_vals:
                    proxy_forecast[h] = np.mean(past_vals)
                else:
                    proxy_forecast[h] = real_forecast[h] # Fallback to persistence if no history

            # The 48h Extended Horizon
            full_forecast = np.concatenate([real_forecast, proxy_forecast])

            # 3. Agent Decision (Plans on 48h)
            p_ch_vec, p_dis_vec, _ = self.agent.act(self.current_soc, full_forecast)

            # 4. Partial Execution (We ONLY execute the 24h truthful Market day, throwing away the proxy)
            for i in range(24):
                p_ch_now = p_ch_vec[i]
                p_dis_now = p_dis_vec[i]
                current_price = real_forecast[i]

                if p_ch_now > 0:
                    cost = p_ch_now * current_price
                    gross_cost += cost
                if p_dis_now > 0:
                    rev = p_dis_now * current_price * 0.95
                    gross_revenue += rev

                throughput += (p_ch_now + p_dis_now)

                # Update true physical SoC state
                self.current_soc += (p_ch_now * 0.95) - (p_dis_now / 0.95)
                self.current_soc = np.clip(self.current_soc, 0.0, self.metrics.capacity_mwh)

                # Log
                self.history.append({
                    "time": self.data.index[t + i],
                    "price": current_price,
                    "p_ch": p_ch_now,
                    "p_dis": p_dis_now,
                    "soc": self.current_soc
                })

            if t % (24 * 10) == 0:
                logger.info(f"Backtesting Day {t//24}/{total_steps//24} completed.")

        return self.metrics.generate_report(gross_revenue, gross_cost, throughput)
