import pytest
import numpy as np
import pandas as pd
from helios_core.stochastic.config import StochasticConfig
from helios_core.stochastic.generator import ScenarioGenerator


def test_scenario_generator_valid_output() -> None:
    # 10 days of hourly data (240 hours)
    historical_data = pd.Series(np.random.normal(50, 10, 240))
    config = StochasticConfig(n_scenarios=5, horizon_hours=24, noise_multiplier=0.0)
    generator = ScenarioGenerator(config)

    scenarios = generator.fit_transform(historical_data, seed=42)

    assert scenarios.shape == (5, 24)
    assert not np.isnan(scenarios).any()


def test_scenario_generator_with_nan() -> None:
    historical_data = pd.Series([50.0] * 50)
    historical_data.iloc[10] = np.nan
    config = StochasticConfig(n_scenarios=2, horizon_hours=24)
    generator = ScenarioGenerator(config)

    with pytest.raises(ValueError, match="NaN"):
        generator.fit_transform(historical_data)


def test_scenario_generator_insufficient_data() -> None:
    # Only 20 hours of data, but horizon requires 24
    historical_data = pd.Series(np.random.normal(50, 10, 20))
    config = StochasticConfig(n_scenarios=2, horizon_hours=24)
    generator = ScenarioGenerator(config)

    with pytest.raises(ValueError, match="Need at least 24 points"):
        generator.fit_transform(historical_data)


def test_scenario_generator_insufficient_windows() -> None:
    # 30 hours of data. This allows 30 - 24 + 1 = 7 possible windows.
    historical_data = pd.Series(np.random.normal(50, 10, 30))
    config = StochasticConfig(n_scenarios=10, horizon_hours=24)  # Asking for 10 windows
    generator = ScenarioGenerator(config)

    with pytest.raises(ValueError, match="history only allows 7"):
        generator.fit_transform(historical_data)


def test_scenario_generator_noise_addition() -> None:
    # 10 days of data
    historical_data = pd.Series(np.array([50.0] * 240))
    config = StochasticConfig(n_scenarios=1, horizon_hours=24, noise_multiplier=1.0)
    generator = ScenarioGenerator(config)

    scenarios = generator.fit_transform(historical_data, seed=42)

    # Since prices are constant at 50, standard deviation is 0.
    # Therefore, adding 1.0 multiplier of 0 stdev should not change the prices.
    assert np.all(scenarios == 50.0)
