import numpy as np
import pandas as pd
import logging

logger = logging.getLogger(__name__)


class RegimeDetector:
    """
    Hidden Markov Model (HMM) for detecting market regimes in electricity prices.

    Post-Audit V3 (Faille 4.2): Detects structural market regimes so the KNN
    scenario generator only selects historical days from the SAME regime as today.

    States:
        0 = Normal (moderate prices, low volatility)
        1 = Crisis (high prices, high volatility)
        2 = Structural (very low/negative prices, renewable surplus)
    """

    def __init__(self, n_regimes: int = 3, lookback_days: int = 7):
        self.n_regimes = n_regimes
        self.lookback_days = lookback_days
        self.model = None
        self._is_fitted = False

    def fit(self, prices: pd.Series) -> None:
        """
        Fits the HMM on historical price data using daily returns and realized volatility.

        Args:
            prices: Hourly price series (must have at least 48 observations).
        """
        try:
            from hmmlearn.hmm import GaussianHMM  # type: ignore
        except ImportError:
            logger.warning("hmmlearn not installed. Regime detection disabled.")
            return

        if len(prices) < 48:
            logger.warning("Not enough data to fit HMM. Need >= 48 hourly observations.")
            return

        # Build daily feature matrix: [mean_price, std_price, max_price]
        price_array = prices.to_numpy(dtype=float)
        n_days = len(price_array) // 24

        if n_days < 5:
            logger.warning(f"Only {n_days} days available. Need >= 5 for HMM.")
            return

        features = np.zeros((n_days, 3))
        for d in range(n_days):
            day_prices = price_array[d * 24: (d + 1) * 24]
            features[d, 0] = np.mean(day_prices)
            features[d, 1] = np.std(day_prices)
            features[d, 2] = np.max(day_prices)

        # Fit Gaussian HMM
        self.model = GaussianHMM(
            n_components=self.n_regimes,
            covariance_type="diag",
            n_iter=100,
            random_state=42
        )

        if self.model is not None:
            try:
                self.model.fit(features)
                self._is_fitted = True
                logger.info(f"HMM fitted with {self.n_regimes} regimes on {n_days} days.")
            except Exception as e:
                logger.error(f"HMM fitting failed: {e}")
                self._is_fitted = False

    def predict_regime(self, prices: pd.Series) -> int:
        """
        Predicts the current market regime from recent price data.
        Uses the last `lookback_days` of hourly prices.

        Returns:
            Integer regime label (0, 1, or 2). Returns -1 if not fitted.
        """
        if not self._is_fitted or self.model is None:
            return -1

        price_array = prices.to_numpy(dtype=float)
        n_hours = min(len(price_array), self.lookback_days * 24)
        recent = price_array[-n_hours:]

        n_days = n_hours // 24
        if n_days < 1:
            return -1

        features = np.zeros((n_days, 3))
        for d in range(n_days):
            day_prices = recent[d * 24: (d + 1) * 24]
            features[d, 0] = np.mean(day_prices)
            features[d, 1] = np.std(day_prices)
            features[d, 2] = np.max(day_prices)

        states = self.model.predict(features)
        # Return the most recent day's regime
        return int(states[-1])

    def get_regime_mask(self, prices: pd.Series) -> np.ndarray:
        """
        Returns a boolean mask over all 24h windows, True if the window belongs
        to the same regime as the current (most recent) window.

        Args:
            prices: Full historical hourly price series.

        Returns:
            Boolean array of shape (n_available_windows,) where n_windows = len(prices) - 24 + 1,
            True for windows in the same regime as the latest.
        """
        if not self._is_fitted or self.model is None:
            return np.ones(max(1, len(prices) - 23), dtype=bool)

        price_array = prices.to_numpy(dtype=float)
        n_days = len(price_array) // 24

        if n_days < 2:
            return np.ones(max(1, len(price_array) - 23), dtype=bool)

        # Build daily features and predict regimes
        features = np.zeros((n_days, 3))
        for d in range(n_days):
            day_prices = price_array[d * 24: (d + 1) * 24]
            features[d, 0] = np.mean(day_prices)
            features[d, 1] = np.std(day_prices)
            features[d, 2] = np.max(day_prices)

        daily_regimes = self.model.predict(features)
        current_regime = daily_regimes[-1]

        # Expand daily regime labels to hourly windows
        n_windows = len(price_array) - 23  # sliding window count for horizon=24
        window_mask = np.ones(n_windows, dtype=bool)

        for w in range(n_windows):
            # Which day does this window primarily belong to?
            day_idx = min(w // 24, n_days - 1)
            window_mask[w] = (daily_regimes[day_idx] == current_regime)

        return window_mask
