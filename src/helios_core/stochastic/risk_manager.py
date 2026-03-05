import numpy as np
import pandas as pd

class DynamicEpsilonManager:
    """
    Risk Manager for the Robust DRO Agent.

    Post-Audit V2: Epsilon is now calibrated on the INTRA-CLUSTER variance
    of the KNN-selected scenarios, not on global market volatility.
    This fixes the measure-space incoherence (Audit Faille 2.2):
    epsilon must live in the same space as the filtered empirical distribution.
    """
    def __init__(
        self,
        eps_min: float = 0.05,
        eps_max: float = 0.50,
        vol_min_expected: float = 10.0,
        vol_max_expected: float = 80.0
    ):
        # Post-Audit V4: Bounds recalibrated for INTRA-CLUSTER dispersion.
        # KNN-filtered scenarios have typical std ~10-150 EUR/MWh per hour,
        # vs 50-300 for global market volatility. The old bounds were way too high,
        # making epsilon always stick at eps_min (hyper-conservative).
        self.eps_min = eps_min
        self.eps_max = eps_max
        self.vol_min = vol_min_expected
        self.vol_max = vol_max_expected

    def compute_epsilon_from_scenarios(self, scenarios: np.ndarray) -> float:
        """
        Calibrates epsilon from the intra-cluster dispersion of the KNN-selected
        scenario matrix. This ensures the ambiguity radius is coherent with the
        filtered empirical distribution.

        Args:
            scenarios: (N, T) matrix of price scenarios output by the KNN generator.

        Returns:
            Epsilon value scaled to the intra-cluster volatility.
        """
        if scenarios.shape[0] < 2:
            return (self.eps_min + self.eps_max) / 2.0

        # Intra-cluster volatility: mean of per-hour std across scenarios
        intra_vol = float(np.mean(np.std(scenarios, axis=0)))

        # Linear mapping with clipping (same logic, coherent input)
        if intra_vol <= self.vol_min:
            return self.eps_min
        elif intra_vol >= self.vol_max:
            return self.eps_max
        else:
            ratio = (intra_vol - self.vol_min) / (self.vol_max - self.vol_min)
            eps = self.eps_min + ratio * (self.eps_max - self.eps_min)
            return float(eps)

    def compute_epsilon(self, historical_prices: pd.Series) -> float:
        """
        Legacy method: Maps global price volatility to epsilon.
        Kept for backward compatibility but should be replaced by
        compute_epsilon_from_scenarios() in production flows.
        """
        lookback = 168
        if len(historical_prices) < lookback:
            return (self.eps_min + self.eps_max) / 2.0

        window = historical_prices.iloc[-lookback:]
        current_vol = float(window.std())

        if current_vol <= self.vol_min:
            return self.eps_min
        elif current_vol >= self.vol_max:
            return self.eps_max
        else:
            ratio = (current_vol - self.vol_min) / (self.vol_max - self.vol_min)
            eps = self.eps_min + ratio * (self.eps_max - self.eps_min)
            return float(eps)
