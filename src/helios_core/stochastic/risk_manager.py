import pandas as pd

class DynamicEpsilonManager:
    """
    Risk Manager for the Robust DRO Agent.
    Monitors market volatility over a rolling window and dynamically
    re-calibrates the ambiguity set size (epsilon) to avoid static paranoia.
    """
    def __init__(
        self,
        lookback_window_hours: int = 168,  # 7 days
        eps_min: float = 0.05,
        eps_max: float = 0.50,
        vol_min_expected: float = 50.0,
        vol_max_expected: float = 300.0
    ):
        self.lookback = lookback_window_hours
        self.eps_min = eps_min
        self.eps_max = eps_max
        self.vol_min = vol_min_expected
        self.vol_max = vol_max_expected

    def compute_epsilon(self, historical_prices: pd.Series) -> float:
        """
        Maps historical price volatility to a robust epsilon value.
        """
        if len(historical_prices) < self.lookback:
            # Fallback to a safe, moderately robust epsilon during the burn-in period
            return (self.eps_min + self.eps_max) / 2.0

        # Extract the relevant rolling window
        window = historical_prices.iloc[-self.lookback:]

        # We use absolute standard deviation of prices as our stress metric
        current_vol = float(window.std())

        # Linear mapping with clipping
        if current_vol <= self.vol_min:
            return self.eps_min
        elif current_vol >= self.vol_max:
            return self.eps_max
        else:
            # Interpolation
            ratio = (current_vol - self.vol_min) / (self.vol_max - self.vol_min)
            eps = self.eps_min + ratio * (self.eps_max - self.eps_min)
            return float(eps)
