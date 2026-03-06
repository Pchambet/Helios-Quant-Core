import requests  # type: ignore
import pandas as pd
import logging
from typing import Dict, Any, List, Tuple

from helios_core.exceptions import DataIngestionError
from helios_core.utils.paths import ensure_data_dir

logger = logging.getLogger(__name__)

HTTP_TIMEOUT = 15

class HistoricalMeteoLoader:
    """
    Connects to the Open-Meteo Historical API (Free Tier) to extract physical
    weather variables that dictate energy prices via the Merit Order Curve.

    Post-Audit V3 (Faille 4.3): Multi-point météo weighted by regional
    installed capacity (Paris=demand, Dunkerque=wind, Montpellier=solar).
    """

    # Stations weighted by their influence on the EPEX SPOT FR merit order
    STATIONS: List[Tuple[str, float, float, float]] = [
        # (name, latitude, longitude, weight)
        ("Paris",       48.8566, 2.3522, 0.50),  # Demand proxy (heating/cooling)
        ("Dunkerque",   51.0343, 2.3767, 0.30),  # Offshore wind proxy (Nord)
        ("Montpellier", 43.6108, 3.8767, 0.20),  # Solar PV proxy (Sud)
    ]

    def __init__(self, start_date: str = "2022-08-01", end_date: str = "2022-08-31"):
        self.start_date = start_date
        self.end_date = end_date
        self.api_url = "https://archive-api.open-meteo.com/v1/archive"

    def _fetch_station(self, name: str, lat: float, lon: float) -> pd.DataFrame:
        """Fetches hourly weather data for a single station."""
        params: Dict[str, Any] = {
            "latitude": lat,
            "longitude": lon,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "hourly": "temperature_2m,wind_speed_10m,direct_radiation",
            "timezone": "UTC"
        }

        response = requests.get(self.api_url, params=params, timeout=HTTP_TIMEOUT)
        response.raise_for_status()
        data = response.json()

        hourly_data = data.get("hourly", {})
        if not hourly_data:
            raise ValueError(f"Open-Meteo returned empty data for {name}.")

        df = pd.DataFrame({
            "time": pd.to_datetime(hourly_data["time"]),
            "temperature_2m": hourly_data["temperature_2m"],
            "wind_speed_10m": hourly_data["wind_speed_10m"],
            "direct_radiation": hourly_data["direct_radiation"]
        })
        df["time"] = df["time"].dt.tz_localize("UTC")
        df.set_index("time", inplace=True)
        df = df.ffill().bfill()
        return df  # type: ignore

    def fetch_data(self) -> pd.DataFrame:
        """
        Extracts hourly weather data from multiple stations and computes
        capacity-weighted averages. Returns a timezone-aware (UTC) DataFrame.
        """
        logger.info(f"Fetching Multi-Point Weather ({self.start_date} to {self.end_date})...")

        dfs = []
        weights = []

        for name, lat, lon, weight in self.STATIONS:
            try:
                df = self._fetch_station(name, lat, lon)
                dfs.append(df)
                weights.append(weight)
                logger.info(f"  ✓ {name} ({lat}, {lon}) — weight {weight}")
            except (requests.exceptions.RequestException, ValueError) as e:
                logger.warning(f"  ✗ {name} failed: {e}. Skipping station.")
            except Exception as e:
                raise DataIngestionError(
                    f"Weather station {name} failed: {e!s}"
                ) from e

        if not dfs:
            raise DataIngestionError("No weather stations returned data.")

        # Normalize weights in case some stations failed
        total_weight = sum(weights)
        weights = [w / total_weight for w in weights]

        # Compute weighted average across stations
        result = dfs[0] * weights[0]
        for df, w in zip(dfs[1:], weights[1:]):
            # Align indices before adding
            common_idx = result.index.intersection(df.index)
            result = result.loc[common_idx] + df.loc[common_idx] * w

        # Standardize physical column names
        result.rename(columns={
            "temperature_2m": "Temperature_C",
            "wind_speed_10m": "WindSpeed_kmh",
            "direct_radiation": "SolarIrradiance_WM2"
        }, inplace=True)

        logger.info(f"Multi-Point Weather Data: {len(result)} hourly observations ({len(dfs)} stations).")
        return result  # type: ignore

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    loader = HistoricalMeteoLoader()
    df_meteo = loader.fetch_data()

    out_path = ensure_data_dir() / "epex_2022_weather.parquet"
    df_meteo.to_parquet(out_path)
    logger.info(f"Immutable Weather Corpus saved to {out_path}")
