import pytest
import numpy as np
from helios_core.optimization.scaling import PriceScaler

def test_scaling_translation() -> None:
    scaler = PriceScaler(1.0)
    # Synthetic array mimicking EPEX extreme negative to massive positive shock
    raw_prices = np.array([
        [-500.0, 100.0, 50.0],
        [0.0, 3000.0, 9000.0]
    ])

    scaled = scaler.fit_transform(raw_prices)

    # Assert bounds are respected safely.
    assert np.max(np.abs(scaled)) == 1.0

    # Assert structural integrity shape
    assert scaled.shape == (2, 3)

def test_fit_transform() -> None:
    scaler = PriceScaler(target_max=1.0)
    prices = np.array([100.0, 200.0, 500.0])

    scaled = scaler.fit_transform(prices)
    inverted = scaler.inverse_transform(scaled)

    # Assert the mathematical inversion yields the original floats without precision loss
    np.testing.assert_almost_equal(inverted, prices, decimal=5)

def test_scaling_unfitted_transform() -> None:
    scaler = PriceScaler()
    raw = np.array([10.0, 20.0])

    with pytest.raises(ValueError, match="Scaler must be fit"):
        scaler.transform(raw)

def test_scaling_constant_prices() -> None:
    # If a day has exactly the same price everywhere, ensure we don't divide by zero.
    scaler = PriceScaler(1.0)
    raw_prices = np.array([50.0, 50.0, 50.0])

    scaled = scaler.fit_transform(raw_prices)
    inverted = scaler.inverse_transform(scaled)

    # Should safely invert back to ~50
    np.testing.assert_almost_equal(inverted, raw_prices, decimal=3)
