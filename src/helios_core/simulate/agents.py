import numpy as np
from typing import Protocol, Tuple
from helios_core.optimization.controller import BatteryMPC

class TradingAgent(Protocol):
    """Protocol for all Backtester Agents."""
    def act(self, current_soc: float, price_forecast: np.ndarray) -> Tuple[np.ndarray, np.ndarray, float]:
        """
        Takes the current SoC and a price forecast for the horizon.
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

    def act(self, current_soc: float, price_forecast: np.ndarray) -> Tuple[np.ndarray, np.ndarray, float]:
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

    def act(self, current_soc: float, price_forecast: np.ndarray) -> Tuple[np.ndarray, np.ndarray, float]:
        self.mpc.battery.soc_mwh = current_soc  # Sync Digital Twin
        self.mpc.scaler.fit(price_forecast)

        p_ch, p_dis, status = self.mpc.solve_deterministic(price_forecast)
        profit = float(np.sum(p_dis * price_forecast - p_ch * price_forecast))
        return p_ch, p_dis, profit


class RobustDROAgent:
    """
    The Risk Manager.
    Uses Wasserstein DRO to optimize for the worst-case distribution.
    Protects against massive negative shocks and LCOS degradation.
    """
    def __init__(self, mpc: BatteryMPC, epsilon: float = 50.0):
        self.mpc = mpc
        self.epsilon = epsilon

    def act(self, current_soc: float, price_forecast: np.ndarray) -> Tuple[np.ndarray, np.ndarray, float]:
        self.mpc.battery.soc_mwh = current_soc
        self.mpc.scaler.fit(price_forecast)

        # We need N scenarios for DRO. Here we just duplicate the forecast with shocks.
        # In a real pipeline, the ScenarioGenerator supplies this.
        # For the standalone agent, we simulate N=10 bounds around the forecast.
        N = 10
        base = np.tile(price_forecast, (N, 1))
        # Add normal noise proportional to price to create plausible ambiguity
        noise = np.random.normal(0, np.abs(price_forecast) * 0.2, (N, len(price_forecast)))
        scenarios = np.maximum(base + noise, -50.0) # Floor at -50

        p_ch, p_dis, status = self.mpc.solve_robust(scenarios, self.epsilon)
        profit = float(np.sum(p_dis * price_forecast - p_ch * price_forecast))
        return p_ch, p_dis, profit
