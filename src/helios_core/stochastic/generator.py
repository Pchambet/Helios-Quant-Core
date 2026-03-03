import numpy as np
import pandas as pd
from typing import Optional
from helios_core.stochastic.config import StochasticConfig

class ScenarioGenerator:
    """
    Transforms 1D historical price data into an (N, Horizon) robust matrix
    for the Distributionally Robust Controller.
    """

    def __init__(self, config: StochasticConfig):
        self.config = config
        self.n_scenarios = self.config.n_scenarios
        self.horizon = self.config.horizon_hours
        self.noise = self.config.noise_multiplier

    def fit_transform(self, historical_prices: pd.Series, seed: Optional[int] = None) -> np.ndarray:
        """
        Takes a continuous pandas Series of prices.
        Outputs an array of shape (N, Horizon).
        Raises ValueError if data is corrupted or contains NaNs.
        """
        if historical_prices.isnull().any():
            raise ValueError("Historical data contains NaN values. Clean data before passing to generator.")

        if len(historical_prices) < self.horizon:
            raise ValueError(f"Not enough data. Need at least {self.horizon} points, got {len(historical_prices)}.")

        # For Day-Ahead markets (24h chunks), we can slice the series into independent rolling windows
        n_available_windows = len(historical_prices) - self.horizon + 1

        if n_available_windows < self.n_scenarios:
            raise ValueError(
                f"Requested {self.n_scenarios} scenarios but history only allows {n_available_windows}."
            )

        # Bootstrapping: Randomly select N starting indices from the available history
        if seed is not None:
            np.random.seed(seed)

        start_indices = np.random.choice(n_available_windows, size=self.n_scenarios, replace=False)

        # Build the (N, 24) matrix
        price_array = historical_prices.values
        scenarios = np.zeros((self.n_scenarios, self.horizon))

        for i, start_idx in enumerate(start_indices):
            scenarios[i, :] = price_array[start_idx : start_idx + self.horizon]

        # Optional: Add Gaussian noise to emulate out-of-distribution shocks
        if self.noise > 0.0:
            volatility = np.std(scenarios, axis=0) * self.noise
            shock = np.random.normal(0, volatility, size=(self.n_scenarios, self.horizon))
            scenarios += shock

        return scenarios
