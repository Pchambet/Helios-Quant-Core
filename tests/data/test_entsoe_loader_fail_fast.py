"""Tests for Fail Fast behavior of the data ingestion layer."""

import pytest
from unittest.mock import patch

from helios_core.data.entsoe_loader import HistoricalCrisisLoader
from helios_core.exceptions import DataIngestionError


def test_fetch_data_raises_when_no_api_key_and_no_parquet_and_mock_false() -> None:
    """Without API key, without cached data, and mock=False, must raise."""
    with patch(
        "helios_core.data.entsoe_loader.os.getenv", return_value=None
    ):
        loader = HistoricalCrisisLoader(
            start_date="2099-01-01", end_date="2099-01-02"
        )
        with pytest.raises(DataIngestionError, match="No ENTSOE_API_KEY"):
            loader.fetch_data(mock=False)


def test_fetch_data_mock_true_returns_synthetic() -> None:
    """With mock=True, synthetic data is returned even without API key."""
    with patch(
        "helios_core.data.entsoe_loader.os.getenv", return_value=None
    ):
        loader = HistoricalCrisisLoader(
            start_date="2099-01-01", end_date="2099-01-02"
        )
        df = loader.fetch_data(mock=True)
    assert "Price_EUR_MWh" in df.columns
    assert "synthetic" in df.columns
    assert "Load_Forecast" in df.columns
    assert "Temperature_C" in df.columns
    assert len(df) > 0
