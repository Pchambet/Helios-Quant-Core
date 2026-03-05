import pandas as pd
import numpy as np
import logging
from typing import Any, Dict, List, Optional
from helios_core.simulate.agents import TradingAgent
from helios_core.simulate.metrics import RiskMetrics
from helios_core.stochastic.risk_manager import DynamicEpsilonManager
from helios_core.stochastic.forecaster import SeasonalARMAForecaster

logger = logging.getLogger(__name__)

class WalkForwardBacktester:
    """
    Industrial Backtesting Engine for the Day-Ahead Market.
    Implements a 48h Receding Horizon with ARMA(1,1) seasonal forecast + EMA(3) proxy.
    Executes trades in 24h blocks to mirror actual EPEX SPOT market mechanics.
    """
    def __init__(
        self,
        data: pd.DataFrame,
        agent: TradingAgent,
        metrics: RiskMetrics,
        risk_manager: Optional[DynamicEpsilonManager] = None
    ):
        self.data = data
        self.agent = agent
        self.metrics = metrics
        self.risk_manager = risk_manager
        self.forecaster = SeasonalARMAForecaster(lookback_days=14, arma_order=(1, 0, 1))

        # State Tracking
        self.current_soc = 0.0
        self.history: List[Dict[str, Any]] = []

    def run(self) -> dict[str, float]:
        prices = self.data['Price_EUR_MWh'].to_numpy(dtype=float)
        total_steps = len(prices)

        gross_revenue = 0.0
        gross_cost = 0.0
        throughput = 0.0

        # ENTSO-E physical forecast error standard deviations (calibrated MW)
        PHYSICAL_NOISE_STD = {
            'Load_Forecast': 1000.0,       # ~1000 MW RMSE at 24-48h lead
            'Wind_Forecast': 500.0,        # ~500 MW RMSE at 24-48h lead
            'Solar_Forecast': 500.0,       # ~500 MW RMSE at 24-48h lead
            'Nuclear_Generation': 0.0      # Nuclear availability is known exactly Day-Ahead
        }

        # Step by 24h blocks (Day-Ahead Clearing)
        for t in range(0, total_steps, 24):
            # Post-Audit V2 (Faille 1.1): STRICT INFORMATION BARRIER
            realized_prices = prices[t: t + 24]  # Only used for PnL execution

            if len(realized_prices) < 24:
                # Discard incomplete final day
                break

            # D+1 Forecast: ARMA(1,1) seasonal model (Post-Audit V4)
            # Uses only prices[:t] — strictly causal, no look-ahead.
            past_prices = prices[:t]
            price_forecast_d1 = self.forecaster.forecast(past_prices, horizon=24)

            # D+2 Forecast: EMA(3) proxy (Post-Audit V3, Faille 1.2)
            # EMA captures 63% of a trend shift in 3 days vs ~50% in 7 for SMA.
            # α = 2/(span+1) = 2/4 = 0.5
            ema_alpha = 0.5
            proxy_forecast_d2 = np.zeros(24)
            for h in range(24):
                # Collect past daily prices at hour h (up to 7 days back)
                past_vals = []
                for d in range(1, 8):
                    past_idx = t + h - 24 * d
                    if past_idx >= 0:
                        past_vals.append(prices[past_idx])

                if past_vals:
                    # Compute EMA: most recent value first (past_vals[0] = yesterday)
                    ema = past_vals[0]
                    for v in past_vals[1:]:
                        ema = ema_alpha * ema + (1 - ema_alpha) * v
                    proxy_forecast_d2[h] = ema
                else:
                    proxy_forecast_d2[h] = price_forecast_d1[h]

            # The 48h Extended Horizon (fully causal — no future data)
            full_forecast = np.concatenate([price_forecast_d1, proxy_forecast_d2])

            # NOTE: Dynamic Epsilon is now managed internally by RobustDROAgent
            # (Post-Audit V2: epsilon computed from intra-KNN cluster variance)

            # 3. Agent Decision (Plans on 48h)
            past_data = self.data.iloc[:t]

            # Post-Audit V2 (Faille 1.3): Inject ECMWF noise on weather forecast
            # to prevent meteo look-ahead bias. Real observations are corrupted with
            # calibrated Gaussian noise to simulate operational forecast uncertainty.
            if t + 48 <= len(self.data):
                forecast_weather = self.data.iloc[t : t + 48].copy()
            else:
                forecast_weather = self.data.iloc[t:].copy()

            for col, sigma in PHYSICAL_NOISE_STD.items():
                if col in forecast_weather.columns and sigma > 0.0:
                    noise = np.random.normal(0, sigma, len(forecast_weather))
                    forecast_weather[col] = np.maximum(0, forecast_weather[col] + noise)

            p_ch_vec, p_dis_vec, _ = self.agent.act(
                current_soc=self.current_soc,
                price_forecast=full_forecast,
                past_data=past_data,
                forecast_weather=forecast_weather
            )

            # 4. Partial Execution (We ONLY execute the 24h truthful Market day, throwing away the proxy)
            for i in range(24):
                p_ch_now = p_ch_vec[i]
                p_dis_now = p_dis_vec[i]
                current_price = realized_prices[i]

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
