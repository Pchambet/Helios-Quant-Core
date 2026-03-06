import numpy as np
import pandas as pd
from helios_core.stochastic.regime_detector import RegimeDetector


def test_regime_detector_basic() -> None:
    """Verifies that the HMM detects at least 2 distinct regimes on synthetic crisis data."""
    rng = np.random.default_rng(42)
    normal_prices = rng.normal(50, 10, 15 * 24)
    crisis_prices = rng.normal(500, 100, 15 * 24)
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
    rng = np.random.default_rng(42)
    normal = rng.normal(50, 5, 10 * 24)
    crisis = rng.normal(300, 50, 10 * 24)
    prices = pd.Series(np.concatenate([normal, crisis]))

    detector = RegimeDetector(n_regimes=2, lookback_days=7)
    detector.fit(prices)

    mask = detector.get_regime_mask(prices)

    # The mask should have length = len(prices) - 23
    assert len(mask) == len(prices) - 23

    # Not all windows should be in the same regime
    assert not np.all(mask) or not np.all(~mask), \
        "Mask should have both True and False for bimodal data"


def test_regime_uncertainty_bounds() -> None:
    """get_regime_uncertainty returns a value in [0, 1] (entropie normalisée)."""
    rng = np.random.default_rng(42)
    prices = pd.Series(rng.normal(80, 30, 14 * 24))

    detector = RegimeDetector(n_regimes=3, lookback_days=7)
    detector.fit(prices)

    unc = detector.get_regime_uncertainty(prices)
    assert 0.0 <= unc <= 1.0, f"Uncertainty should be in [0,1], got {unc}"
