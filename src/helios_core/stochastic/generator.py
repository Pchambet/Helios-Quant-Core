import numpy as np
import pandas as pd
from typing import Optional, Union
from helios_core.stochastic.config import StochasticConfig

class ScenarioGenerator:
    """
    Transforms historical multi-variate data into an (N, Horizon) robust matrix
    for the Distributionally Robust Controller. Conditioned by KNN on physical weather if provided.

    Post-Audit V3: Supports regime filtering and tail injection (Faille 4.2).
    """

    # Fraction of scenarios reserved for synthetic tail stress tests
    # Fraction of scenarios reserved for synthetic tail stress tests
    TAIL_INJECTION_RATIO = 0.03

    def __init__(self, config: StochasticConfig):
        self.config = config
        self.n_scenarios = self.config.n_scenarios
        self.horizon = self.config.horizon_hours
        self.noise = self.config.noise_multiplier

    def fit_transform(
        self,
        historical_data: Union[pd.DataFrame, pd.Series],
        forecast_weather: Optional[pd.DataFrame] = None,
        regime_mask: Optional[np.ndarray] = None,
        seed: Optional[int] = None
    ) -> np.ndarray:
        """
        Takes a continuous pandas DataFrame of historical prices and weather.
        Outputs an array of shape (N, Horizon).

        Args:
            historical_data: DataFrame with 'Price_EUR_MWh' and optionally weather columns.
            forecast_weather: 48h weather forecast DataFrame for KNN matching.
            regime_mask: Boolean array from RegimeDetector, filtering windows by market regime.
            seed: Random seed for reproducibility.
        """
        if isinstance(historical_data, pd.Series):
            historical_data = historical_data.to_frame(name="Price_EUR_MWh")

        if "Price_EUR_MWh" not in historical_data.columns:
            raise ValueError("historical_data must contain 'Price_EUR_MWh'.")

        if historical_data['Price_EUR_MWh'].isnull().any():
            raise ValueError("Historical data contains NaN values. Clean data before passing to generator.")

        if len(historical_data) < self.horizon:
            raise ValueError(f"Not enough data. Need at least {self.horizon} points, got {len(historical_data)}.")

        # For Day-Ahead markets (24h chunks), we can slice the series into independent rolling windows
        n_available_windows = len(historical_data) - self.horizon + 1

        if seed is not None:
            np.random.seed(seed)

        # Reserve slots for tail injection (Audit Faille 4.2)
        n_tail = max(1, int(self.n_scenarios * self.TAIL_INJECTION_RATIO))
        n_empirical = self.n_scenarios - n_tail

        # Apply regime mask to filter candidate windows (Audit Faille 4.2)
        if regime_mask is not None and len(regime_mask) >= n_available_windows:
            valid_indices = np.where(regime_mask[:n_available_windows])[0]
            if len(valid_indices) < 5:
                # Not enough windows in this regime, fall back to all
                valid_indices = np.arange(n_available_windows)
        else:
            valid_indices = np.arange(n_available_windows)

        physical_cols = ["Load_Forecast", "Solar_Forecast", "Wind_Forecast", "Nuclear_Generation"]
        use_knn = (
            forecast_weather is not None and
            len(forecast_weather) >= self.horizon and
            all(c in historical_data.columns for c in physical_cols) and
            all(c in forecast_weather.columns for c in physical_cols)
        )

        if use_knn and forecast_weather is not None:
            from sklearn.neighbors import NearestNeighbors # type: ignore
            from sklearn.preprocessing import StandardScaler # type: ignore

            # Build Historical Feature Matrix (only from valid regime windows)
            features_array = historical_data[physical_cols].values
            X_hist = np.zeros((len(valid_indices), self.horizon * len(physical_cols)))
            for idx, i in enumerate(valid_indices):
                X_hist[idx, :] = features_array[i : i + self.horizon].flatten()

            # Build Target Forecast Vector
            X_forecast = forecast_weather[physical_cols].iloc[:self.horizon].values.flatten().reshape(1, -1)

            # CRITICAL: Scale dimensions so Irradiance (0-1000) does not crush Temperature (0-40)
            scaler = StandardScaler()
            X_hist_scaled = scaler.fit_transform(X_hist)
            X_forecast_scaled = scaler.transform(X_forecast)

            # Post-Audit Phase 6: Dimensionality Curse Mitigation
            # Weight the standardized features: Load and Nuclear availability are
            # the primary price drivers, Renewables are secondary.
            base_weights = np.array([1.0, 0.5, 0.5, 1.0]) # Load, Solar, Wind, Nuclear
            # Repeat weights for each hour in the horizon
            weights_horizon = np.tile(base_weights, self.horizon)

            X_hist_scaled *= weights_horizon
            X_forecast_scaled *= weights_horizon

            # Find the MOST identical days using the normalized Euclidean distance
            # Post-Audit Phase 6 Fix: We MUST NOT ask for n_empirical (e.g. 29) neighbors if we want strict similarity.
            # Instead, we ask for the Top-K (e.g. 5) most physically identical days, and bootstrap from them.
            n_strict_matches = min(5, len(valid_indices))
            nn = NearestNeighbors(n_neighbors=n_strict_matches, metric='euclidean')
            nn.fit(X_hist_scaled)
            _, knn_indices = nn.kneighbors(X_forecast_scaled)

            # Map back knn indices to original window indices
            strict_indices = valid_indices[knn_indices[0]]

            # Bootstrap from the strict physical matches to fill the empirical scenario quota
            start_indices = np.random.choice(strict_indices, size=n_empirical, replace=True)
        else:
            # Bootstrapping from valid windows only
            start_indices = valid_indices[np.random.choice(
                len(valid_indices),
                size=n_empirical,
                replace=True
            )]

        # Build the empirical (N_empirical, Horizon) matrix
        price_array = historical_data['Price_EUR_MWh'].to_numpy(dtype=float)
        scenarios = np.zeros((self.n_scenarios, self.horizon))

        for i, start_idx in enumerate(start_indices[:n_empirical]):
            scenarios[i, :] = price_array[start_idx : start_idx + self.horizon] # type: ignore

        # Tail Injection: Synthetic stress scenarios (Audit Faille 4.2)
        # These cover black swans the history may not contain.
        mean_price = np.mean(price_array)
        for j in range(n_tail):
            tail_idx = n_empirical + j
            stress_type = j % 3  # Cycle through 3 stress types

            if stress_type == 0:
                # Prolonged negative prices (renewable surplus)
                scenarios[tail_idx, :] = np.random.uniform(-100, -20, self.horizon)
            elif stress_type == 1:
                # Price cap scenario (regulatory intervention, e.g., 180 EUR/MWh)
                scenarios[tail_idx, :] = np.clip(
                    np.random.normal(180, 20, self.horizon), 50, 180
                )
            else:
                # Extreme spike (5x mean price for 6 consecutive hours)
                base = np.random.normal(mean_price, mean_price * 0.2, self.horizon)
                spike_start = np.random.randint(0, max(1, self.horizon - 6))
                base[spike_start:spike_start + 6] = mean_price * 5.0
                scenarios[tail_idx, :] = base

        # Optional: Add Gaussian noise to emulate out-of-distribution shocks
        if self.noise > 0.0:
            volatility = np.std(scenarios, axis=0) * self.noise
            shock = np.random.normal(0, volatility, size=(self.n_scenarios, self.horizon))
            scenarios += shock

        return scenarios
