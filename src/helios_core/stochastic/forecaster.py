import numpy as np
import logging
from typing import cast

logger = logging.getLogger(__name__)


class SeasonalARMAForecaster:
    """
    Causal Day-Ahead price forecaster based on decomposition + ARMA(1,1).

    Strategy:
    1. Extract hourly seasonal component via rolling mean (7-day per hour)
    2. Fit ARMA(1,1) on the deseasonalized residuals
    3. Forecast = seasonal_component + ARMA residual forecast

    This replaces the naive persistence model (P_hat = P_{t-24}) with a
    statistically sound model that captures both:
    - Intraday seasonality (hourly pattern)
    - Short-term autoregressive dynamics (momentum/mean-reversion in residuals)
    """

    def __init__(self, lookback_days: int = 14, arma_order: tuple = (1, 0, 1)):
        """
        Args:
            lookback_days: Days of history to use for seasonal estimation.
            arma_order: (p, d, q) order for the ARIMA model on residuals.
        """
        self.lookback_days = lookback_days
        self.arma_order = arma_order

    def forecast(self, prices: np.ndarray, horizon: int = 24) -> np.ndarray:
        """
        Produces a causal forecast of length `horizon` using only past data.

        Args:
            prices: Historical hourly prices up to time t (the agent's information set).
            horizon: Number of hours to forecast (default 24 for Day-Ahead).

        Returns:
            (horizon,) array of forecasted prices.
        """
        n = len(prices)
        lookback_hours = self.lookback_days * 24

        if n < 48:
            # Not enough data — fall back to persistence
            if n >= 24:
                return cast(np.ndarray, prices[-24:].copy().astype(np.float64))
            return cast(np.ndarray, np.full(horizon, np.mean(prices)).astype(np.float64))

        # Use the most recent lookback window
        history = prices[max(0, n - lookback_hours):]

        # Step 1: Extract hourly seasonal component
        # For each hour h in [0..23], compute the mean of that hour over available days
        seasonal = np.zeros(24)
        n_hist = len(history)
        for h in range(24):
            hour_vals = history[h::24]  # Every 24th value starting at h
            if len(hour_vals) > 0:
                seasonal[h] = np.mean(hour_vals)
            else:
                seasonal[h] = np.mean(history)

        # Step 2: Deseasonalize
        n_full_days = n_hist // 24
        seasonal_tiled = np.tile(seasonal, n_full_days)
        trimmed_history = history[:n_full_days * 24]
        residuals = trimmed_history - seasonal_tiled

        # Step 3: Fit ARMA on residuals
        residual_forecast = self._fit_arma_residuals(residuals, horizon)

        # Step 4: Recompose forecast = seasonal + residual forecast
        seasonal_forecast = np.tile(seasonal, (horizon // 24) + 1)[:horizon]
        forecast = seasonal_forecast + residual_forecast

        return cast(np.ndarray, forecast.astype(np.float64))

    def _fit_arma_residuals(self, residuals: np.ndarray, horizon: int) -> np.ndarray:
        """
        Fits ARIMA on residuals and produces a forecast.
        Falls back to exponential decay toward 0 if statsmodels fails.
        """
        try:
            from statsmodels.tsa.arima.model import ARIMA  # type: ignore

            # Use recent residuals to avoid fitting on too much noisy data
            fit_data = residuals[-min(len(residuals), 336):]  # Max 14 days

            model = ARIMA(fit_data, order=self.arma_order)
            fitted = model.fit(method_kwargs={"maxiter": 50})

            fc = fitted.forecast(steps=horizon)
            return np.array(fc)

        except Exception as e:
            logger.warning(f"ARMA fit failed: {e}. Falling back to exponential decay.")
            # Exponential decay toward zero (conservative fallback)
            last_residual = residuals[-1] if len(residuals) > 0 else 0.0
            decay = np.array([last_residual * (0.9 ** t) for t in range(horizon)])
            return decay
