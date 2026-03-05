import numpy as np
from helios_core.optimization.scaling import PriceScaler


def test_scaler_fit_includes_scenarios() -> None:
    """Verifies that fitting the scaler on forecast+scenarios covers the full range."""
    scaler = PriceScaler()

    # Scenario with extreme crisis prices (up to 2000 EUR)
    forecast = np.array([50.0] * 24)
    scenarios = np.array([
        [50.0] * 24,
        [2000.0] * 24,  # Crisis spike
        [-50.0] * 24,   # Negative prices
    ])

    # Fit on union of forecast + scenarios
    all_prices = np.concatenate([forecast.reshape(1, -1), scenarios])
    scaler.fit(all_prices)

    # Transform should keep extreme values within [-1, 1] range
    scaled_scenarios = scaler.transform(scenarios)
    assert np.all(scaled_scenarios >= -1.1), f"Min scaled: {np.min(scaled_scenarios):.2f}"
    assert np.all(scaled_scenarios <= 1.1), f"Max scaled: {np.max(scaled_scenarios):.2f}"
