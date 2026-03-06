import numpy as np
import pandas as pd
from helios_core.stochastic.price_forecaster import LightGBMPriceForecaster


def test_forecast_shape_and_bounds() -> None:
    """Sortie (horizon,) avec valeurs bornées EPEX."""
    rng = np.random.default_rng(42)
    n = 336  # 14 jours
    dates = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
    prices = rng.uniform(20, 80, n)
    df = pd.DataFrame({"Price_EUR_MWh": prices}, index=dates)
    for col in ["Load_Forecast", "Wind_Forecast", "Solar_Forecast", "Nuclear_Generation"]:
        df[col] = rng.uniform(0, 100, n)

    fc = LightGBMPriceForecaster(lookback_days=14)
    prices, cve = fc.forecast(df, horizon=48)

    assert prices.shape == (48,)
    assert np.all(prices >= -500) and np.all(prices <= 3000)
    assert isinstance(cve, (int, float)) and cve >= 0


def test_fallback_when_insufficient_data() -> None:
    """Fallback persistance si < 168h."""
    rng = np.random.default_rng(42)
    n = 100
    dates = pd.date_range("2024-01-01", periods=n, freq="h", tz="UTC")
    df = pd.DataFrame({"Price_EUR_MWh": rng.uniform(30, 70, n)}, index=dates)

    fc = LightGBMPriceForecaster()
    prices, cve = fc.forecast(df, horizon=48)

    assert prices.shape == (48,)
    assert np.all(np.isfinite(prices))
    assert cve == 0.0  # fallback: pas de métrique instrumentale
