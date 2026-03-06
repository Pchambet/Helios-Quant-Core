import pytest
import numpy as np
import pandas as pd
from helios_core.stochastic.config import StochasticConfig
from helios_core.stochastic.generator import ScenarioGenerator


def test_scenario_generator_valid_output() -> None:
    rng = np.random.default_rng(42)
    historical_data = pd.Series(rng.normal(50, 10, 240))
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
    rng = np.random.default_rng(42)
    historical_data = pd.Series(rng.normal(50, 10, 20))
    config = StochasticConfig(n_scenarios=2, horizon_hours=24)
    generator = ScenarioGenerator(config)

    with pytest.raises(ValueError, match="Need at least 24 points"):
        generator.fit_transform(historical_data)


def test_scenario_generator_insufficient_windows() -> None:
    rng = np.random.default_rng(42)
    historical_data = pd.Series(rng.normal(50, 10, 30))
    config = StochasticConfig(n_scenarios=10, horizon_hours=24)  # Asking for 10 windows
    generator = ScenarioGenerator(config)

    scenarios = generator.fit_transform(historical_data)
    assert scenarios.shape == (10, 24), "Generator must fallback to bootstrap with replacement"


def test_scenario_generator_noise_addition() -> None:
    # 10 days of data
    historical_data = pd.Series(np.array([50.0] * 240))
    # Use 10 scenarios with noise=0 to test tail injection behavior.
    # When noise=0 and prices are constant, empirical scenarios must be 50.0.
    # Tail-injected scenarios must be synthetic stress (NOT 50.0).
    config = StochasticConfig(n_scenarios=10, horizon_hours=24, noise_multiplier=0.0)
    generator = ScenarioGenerator(config)

    scenarios = generator.fit_transform(historical_data, seed=42)

    n_tail = max(1, int(10 * generator.TAIL_INJECTION_RATIO))
    n_empirical = 10 - n_tail
    assert np.all(scenarios[:n_empirical] == 50.0), "Empirical scenarios should be constant"
    # Tail injection MUST be different from constant 50
    assert not np.all(scenarios[n_empirical:] == 50.0), "Tail scenarios should be synthetic stress"
