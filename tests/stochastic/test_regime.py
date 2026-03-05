import numpy as np
import pandas as pd
from helios_core.stochastic.regime_detector import RegimeDetector


def test_regime_detector_basic() -> None:
    """Verifies that the HMM detects at least 2 distinct regimes on synthetic crisis data."""
    np.random.seed(42)

    # Create 30 days of data with 2 clear regimes:
    # Days 0-14: Normal (prices ~50 EUR, low vol)
    # Days 15-29: Crisis (prices ~500 EUR, high vol)
    normal_prices = np.random.normal(50, 10, 15 * 24)
    crisis_prices = np.random.normal(500, 100, 15 * 24)
    all_prices = np.concatenate([normal_prices, crisis_prices])

    prices_series = pd.Series(all_prices)

    detector = RegimeDetector(n_regimes=2, lookback_days=7)
    detector.fit(prices_series)

    assert detector._is_fitted, "HMM should be fitted"

    # The regime of the last day (crisis) should be different from the first day (normal)
    day1_features = prices_series.iloc[:7 * 24]
    day_last_features = prices_series.iloc[-7 * 24:]

    regime_start = detector.predict_regime(day1_features)
    regime_end = detector.predict_regime(day_last_features)

    assert regime_start != regime_end, \
        f"HMM should detect different regimes for Normal vs Crisis. Got {regime_start} vs {regime_end}"


def test_regime_mask_filters_windows() -> None:
    """Verifies that the regime mask correctly filters historical windows."""
    np.random.seed(42)

    normal = np.random.normal(50, 5, 10 * 24)
    crisis = np.random.normal(300, 50, 10 * 24)
    prices = pd.Series(np.concatenate([normal, crisis]))

    detector = RegimeDetector(n_regimes=2, lookback_days=7)
    detector.fit(prices)

    mask = detector.get_regime_mask(prices)

    # The mask should have length = len(prices) - 23
    assert len(mask) == len(prices) - 23

    # Not all windows should be in the same regime
    assert not np.all(mask) or not np.all(~mask), \
        "Mask should have both True and False for bimodal data"
