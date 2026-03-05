import pandas as pd
import numpy as np
from typing import Protocol, Tuple, Any
from helios_core.optimization.controller import BatteryMPC

class TradingAgent(Protocol):
    """Protocol for all Backtester Agents."""
    def act(
        self,
        current_soc: float,
        price_forecast: np.ndarray,
        past_data: pd.DataFrame | None = None,
        forecast_weather: pd.DataFrame | None = None
    ) -> Tuple[np.ndarray, np.ndarray, float]:
        """
        Takes the current SoC and a price forecast for the horizon.
        Optionally takes historical multi-variate data and the 48h weather forecast.
        Returns:
            p_ch (charge vector)
            p_dis (discharge vector)
            expected_profit (the internal belief of profit)
        Note: The backtester only executes the very first step [0] of the vectors.
        """
        ...


class NaiveHeuristicAgent:
    """
    The baseline industrial strategy:
    Charges at night (03:00 to 05:00)
    Discharges at evening peak (18:00 to 20:00).
    Ignores quantitative forecasting.
    """
    def __init__(self, max_charge: float, max_discharge: float):
        self.max_charge = max_charge
        self.max_discharge = max_discharge

    def act(
        self,
        current_soc: float,
        price_forecast: np.ndarray,
        past_data: pd.DataFrame | None = None,
        forecast_weather: pd.DataFrame | None = None
    ) -> Tuple[np.ndarray, np.ndarray, float]:
        horizon = len(price_forecast)
        p_ch = np.zeros(horizon)
        p_dis = np.zeros(horizon)

        # The Naive agent is structurally blind to J+2 (the proxy).
        # It operates strictly on the 24h Day-Ahead market.
        da_prices = price_forecast[:24]

        min_idx = int(np.argmin(da_prices))
        max_idx = int(np.argmax(da_prices))

        p_ch[min_idx] = self.max_charge
        p_dis[max_idx] = self.max_discharge

        expected_profit = p_dis[max_idx] * da_prices[max_idx] - p_ch[min_idx] * da_prices[min_idx]
        return p_ch, p_dis, float(expected_profit)


class DeterministicMPCAgent:
    """
    Solves the LP assuming the expected mean forecast is 100% correct.
    Aggressive. Highly exposed to variance.
    """
    def __init__(self, mpc: BatteryMPC):
        self.mpc = mpc

    def act(
        self,
        current_soc: float,
        price_forecast: np.ndarray,
        past_data: pd.DataFrame | None = None,
        forecast_weather: pd.DataFrame | None = None
    ) -> Tuple[np.ndarray, np.ndarray, float]:
        self.mpc.battery.soc_mwh = current_soc  # Sync Digital Twin
        self.mpc.scaler.fit(price_forecast)

        p_ch, p_dis, status = self.mpc.solve_deterministic(price_forecast)
        profit = float(np.sum(p_dis * price_forecast - p_ch * price_forecast))
        return p_ch, p_dis, profit


class RobustDROAgent:
    """
    The Risk Manager.
    Uses Wasserstein DRO to optimize for the worst-case distribution.

    Post-Audit V4: Full pipeline — RegimeDetector → KNN → Epsilon → DRO.
    """
    def __init__(self, mpc: BatteryMPC, epsilon: float = 50.0, generator: Any = None,
                 risk_manager: Any = None, regime_detector: Any = None):
        self.mpc = mpc
        self.epsilon = epsilon  # Static fallback
        self.generator = generator
        self.risk_manager = risk_manager  # DynamicEpsilonManager instance
        self.regime_detector = regime_detector  # RegimeDetector instance (HMM)

    def act(
        self,
        current_soc: float,
        price_forecast: np.ndarray,
        past_data: pd.DataFrame | None = None,
        forecast_weather: pd.DataFrame | None = None
    ) -> Tuple[np.ndarray, np.ndarray, float]:
        self.mpc.battery.soc_mwh = current_soc

        if self.generator is not None and past_data is not None and len(past_data) >= 48:
            # Post-Audit V4: Compute regime mask to filter KNN by market state
            regime_mask = None
            if self.regime_detector is not None and 'Price_EUR_MWh' in past_data.columns:
                regime_mask = self.regime_detector.get_regime_mask(past_data['Price_EUR_MWh'])

            # Physics-Informed execution with regime-filtered KNN
            scenarios = self.generator.fit_transform(
                past_data, forecast_weather=forecast_weather, regime_mask=regime_mask
            )
        else:
            # Fallback naive simulation
            N = 10
            base = np.tile(price_forecast, (N, 1))
            noise = np.random.normal(0, np.abs(price_forecast) * 0.2, (N, len(price_forecast)))
            scenarios = np.maximum(base + noise, -50.0)

        # Post-Audit V3 (Faille 2.3): Fit scaler on the UNION of forecast + scenarios
        all_prices = np.concatenate([price_forecast.reshape(1, -1), scenarios])
        self.mpc.scaler.fit(all_prices)

        # Post-Audit V2: Compute epsilon from intra-cluster dispersion (coherent with KNN)
        if self.risk_manager is not None:
            self.epsilon = self.risk_manager.compute_epsilon_from_scenarios(scenarios)

        p_ch, p_dis, status = self.mpc.solve_robust(scenarios, self.epsilon)
        profit = float(np.sum(p_dis * price_forecast - p_ch * price_forecast))
        return p_ch, p_dis, profit
