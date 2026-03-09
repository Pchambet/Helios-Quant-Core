"""
LiveDataFetcher — Système nerveux du Paper Trader.

Agrège les données live depuis Open-Meteo (forecast) et ENTSO-E Transparency.
Fail-fast sur ENTSO-E ; fallback persistance sur Open-Meteo.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import pandas as pd
import requests

from helios_core.exceptions import DataIngestionError
from helios_core.paper_trading.config import PAPER_DATA_DIR

logger = logging.getLogger(__name__)

HTTP_TIMEOUT = 15

# Stations météo pondérées (alignées avec HistoricalMeteoLoader)
METEO_STATIONS: list[tuple[str, float, float, float]] = [
    ("Paris", 48.8566, 2.3522, 0.50),
    ("Dunkerque", 51.0343, 2.3767, 0.30),
    ("Montpellier", 43.6108, 3.8767, 0.20),
]


class LiveMeteoForecastLoader:
    """
    Charge la météo D+1/D+2 depuis l'API Open-Meteo Forecast (pas archive).
    Fallback : persistance des 48 dernières heures si API indisponible.
    """

    def __init__(self, fallback_past_hours: int = 48):
        self.api_url = "https://api.open-meteo.com/v1/forecast"
        self.fallback_past_hours = fallback_past_hours

    def fetch_forecast(self, hours: int = 48) -> pd.DataFrame:
        """
        Retourne un DataFrame horaire UTC avec Temperature_C, WindSpeed_kmh, SolarIrradiance_WM2.
        forecast_days=2 donne 48h.
        """
        forecast_days = max(1, (hours + 23) // 24)
        dfs: list[pd.DataFrame] = []
        weights: list[float] = []

        for name, lat, lon, weight in METEO_STATIONS:
            try:
                df = self._fetch_station(lat, lon, forecast_days)
                dfs.append(df)
                weights.append(weight)
                logger.info(f"  ✓ {name} forecast ({forecast_days}d)")
            except (requests.exceptions.RequestException, ValueError) as e:
                logger.warning(f"  ✗ {name} forecast failed: {e}. Skipping.")
            except Exception as e:
                raise DataIngestionError(
                    f"Open-Meteo forecast failed for {name}: {e!s}"
                ) from e

        if not dfs:
            raise DataIngestionError("No weather stations returned forecast data.")

        total_weight = sum(weights)
        weights = [w / total_weight for w in weights]
        result = dfs[0] * weights[0]
        for df, w in zip(dfs[1:], weights[1:]):
            common_idx = result.index.intersection(df.index)
            result = result.loc[common_idx] + df.loc[common_idx] * w

        result.rename(
            columns={
                "temperature_2m": "Temperature_C",
                "wind_speed_10m": "WindSpeed_kmh",
                "direct_radiation": "SolarIrradiance_WM2",
            },
            inplace=True,
        )
        result = result.ffill().bfill()
        return result.iloc[:hours]  # type: ignore

    def _fetch_station(self, lat: float, lon: float, forecast_days: int) -> pd.DataFrame:
        params: dict[str, Any] = {
            "latitude": lat,
            "longitude": lon,
            "hourly": "temperature_2m,wind_speed_10m,direct_radiation",
            "forecast_days": forecast_days,
            "timezone": "UTC",
        }
        resp = requests.get(self.api_url, params=params, timeout=HTTP_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        hourly = data.get("hourly", {})
        if not hourly:
            raise ValueError("Open-Meteo returned empty hourly data.")
        df = pd.DataFrame(
            {
                "time": pd.to_datetime(hourly["time"]),
                "temperature_2m": hourly["temperature_2m"],
                "wind_speed_10m": hourly["wind_speed_10m"],
                "direct_radiation": hourly["direct_radiation"],
            }
        )
        df["time"] = pd.to_datetime(df["time"], utc=True)
        df.set_index("time", inplace=True)
        return df  # type: ignore


class LiveDataFetcher:
    """
    Agrège prix, fondamentaux et météo pour le Paper Trader.
    ENTSO-E : fail-fast (pas de fallback silencieux).
    Open-Meteo : fallback persistance si indisponible.
    """

    def __init__(self, country_code: str = "FR"):
        self.api_key = os.getenv("ENTSOE_API_KEY")
        self.country_code = country_code
        self.meteo_loader = LiveMeteoForecastLoader()
        PAPER_DATA_DIR.mkdir(parents=True, exist_ok=True)

    def fetch_prices_past_N_days(self, n_days: int) -> pd.DataFrame:
        """
        Prix day-ahead EPEX des N derniers jours (pour LightGBM lookback).
        Fail-fast si ENTSO-E indisponible.
        """
        self._require_entsoe_key()
        end = pd.Timestamp.now(tz="UTC")
        start = end - pd.Timedelta(days=n_days)
        return self._fetch_entsoe_prices(start, end)

    def fetch_fundamentals_past_N_days(self, n_days: int) -> pd.DataFrame:
        """
        Load, Wind, Solar, Nuclear des N derniers jours.
        Fail-fast si ENTSO-E indisponible.
        """
        self._require_entsoe_key()
        end = pd.Timestamp.now(tz="UTC")
        start = end - pd.Timedelta(days=n_days)
        return self._fetch_entsoe_fundamentals(start, end)

    def fetch_meteo_forecast(self, hours: int = 48) -> pd.DataFrame:
        """
        Météo D+1/D+2 depuis Open-Meteo Forecast.
        Persiste le résultat pour fallback si API down au prochain run.
        """
        df = self.meteo_loader.fetch_forecast(hours=hours)
        path = PAPER_DATA_DIR / "last_meteo_forecast.parquet"
        try:
            df[["Temperature_C", "WindSpeed_kmh", "SolarIrradiance_WM2"]].to_parquet(path)
        except OSError as e:
            logger.warning(f"Could not persist meteo fallback: {e}")
        return df

    def fetch_day_ahead_prices(self, target_date: str) -> pd.DataFrame:
        """
        Prix day-ahead réels pour une date donnée (pour le réconciliateur).
        target_date : YYYY-MM-DD.
        """
        self._require_entsoe_key()
        start = pd.Timestamp(target_date, tz="Europe/Paris")
        end = start + pd.Timedelta(days=1)
        return self._fetch_entsoe_prices(start, end)

    def build_full_dataset_for_forecast(
        self,
        lookback_days: int = 56,
        meteo_hours: int = 48,
        meteo_fallback_from: pd.DataFrame | None = None,
    ) -> pd.DataFrame:
        """
        Construit le DataFrame complet pour l'orchestrateur :
        Price_EUR_MWh, Load_Forecast, Wind_Forecast, Solar_Forecast, Nuclear_Generation,
        Temperature_C, WindSpeed_kmh, SolarIrradiance_WM2.

        meteo_fallback_from : si Open-Meteo échoue, utiliser les 48h de ce DataFrame
        pour persistance (dernières colonnes météo).
        """
        df_prices = self.fetch_prices_past_N_days(lookback_days)
        df_fund = self.fetch_fundamentals_past_N_days(lookback_days)

        df = df_prices.join(df_fund, how="inner")
        df = df.ffill().bfill()

        try:
            df_meteo = self.fetch_meteo_forecast(hours=meteo_hours)
        except DataIngestionError:
            # Essayer fallback persistance (dernier run réussi)
            if meteo_fallback_from is None:
                fallback_path = PAPER_DATA_DIR / "last_meteo_forecast.parquet"
                if fallback_path.exists():
                    try:
                        meteo_fallback_from = pd.read_parquet(fallback_path)
                    except Exception as e:
                        logger.warning(f"Could not load meteo fallback: {e}")
            if meteo_fallback_from is not None and "Temperature_C" in meteo_fallback_from.columns:
                logger.warning("Using meteo persistence fallback (last 48h of past data).")
                last_n = min(meteo_hours, len(meteo_fallback_from))
                df_meteo = meteo_fallback_from.iloc[-last_n:][
                    ["Temperature_C", "WindSpeed_kmh", "SolarIrradiance_WM2"]
                ].copy()
                # Réindexer sur le futur (D+1) pour compatibilité
                last_ts = df.index[-1]
                df_meteo.index = pd.date_range(
                    start=last_ts + pd.Timedelta(hours=1),
                    periods=len(df_meteo),
                    freq="h",
                    tz="UTC",
                )
            else:
                raise DataIngestionError(
                    "Open-Meteo forecast failed and no fallback DataFrame provided."
                )

        # Pour le forecaster, on a besoin des colonnes météo sur tout le lookback.
        # La météo forecast ne couvre que D+1. On utilise la persistance pour le passé :
        # les dernières 48h du passé = les 48h de "forecast" pour le backtester.
        # Ici, on attache la météo forecast aux dernières heures du df (pour D+1).
        # Le LightGBM utilise les lags (lag_24) donc il a besoin de météo sur le passé.
        # Le HistoricalCrisisLoader attache la météo historique (archive) au passé.
        # Pour le live : on n'a pas de météo "passée" en temps réel sauf si on a
        # un cache. Pour simplifier Phase 1 : on suppose que df a déjà les colonnes
        # météo du passé (via un run précédent ou données archivées).
        # Si df n'a pas Temperature_C, on crée des colonnes vides et on remplit
        # avec la forecast pour les heures futures.
        if "Temperature_C" not in df.columns:
            df["Temperature_C"] = float("nan")
            df["WindSpeed_kmh"] = float("nan")
            df["SolarIrradiance_WM2"] = float("nan")

        # Aligner la forecast sur les dernières heures du df
        overlap = df.index.intersection(df_meteo.index)
        if len(overlap) > 0:
            df.loc[overlap, "Temperature_C"] = df_meteo.loc[overlap, "Temperature_C"]
            df.loc[overlap, "WindSpeed_kmh"] = df_meteo.loc[overlap, "WindSpeed_kmh"]
            df.loc[overlap, "SolarIrradiance_WM2"] = df_meteo.loc[overlap, "SolarIrradiance_WM2"]

        # Étendre df avec les heures D+1 si la forecast dépasse
        future_idx = df_meteo.index.difference(df.index)
        if len(future_idx) > 0:
            df_future = pd.DataFrame(
                index=future_idx,
                columns=df.columns,
                data=float("nan"),
            )
            df_future["Temperature_C"] = df_meteo.loc[future_idx, "Temperature_C"]
            df_future["WindSpeed_kmh"] = df_meteo.loc[future_idx, "WindSpeed_kmh"]
            df_future["SolarIrradiance_WM2"] = df_meteo.loc[future_idx, "SolarIrradiance_WM2"]
            df_future["Price_EUR_MWh"] = df["Price_EUR_MWh"].iloc[-1]  # persistance prix
            for col in ["Load_Forecast", "Wind_Forecast", "Solar_Forecast", "Nuclear_Generation"]:
                if col in df.columns:
                    df_future[col] = df[col].iloc[-1]
            df = pd.concat([df, df_future]).sort_index()

        df = df.ffill().bfill()
        return df  # type: ignore[no-any-return]

    def _require_entsoe_key(self) -> None:
        if not self.api_key:
            raise DataIngestionError(
                "ENTSOE_API_KEY is not set. Required for live price/fundamental data."
            )

    def _fetch_entsoe_prices(
        self, start: pd.Timestamp, end: pd.Timestamp
    ) -> pd.DataFrame:
        try:
            from entsoe import EntsoePandasClient  # type: ignore
        except ImportError as e:
            raise DataIngestionError(
                "entsoe-py is not installed. pip install entsoe-py"
            ) from e

        client = EntsoePandasClient(api_key=str(self.api_key))
        ts = client.query_day_ahead_prices(self.country_code, start=start, end=end)
        df = ts.to_frame(name="Price_EUR_MWh")
        df.index = pd.DatetimeIndex(df.index).tz_convert("UTC")
        nan_count = df["Price_EUR_MWh"].isna().sum()
        if nan_count > 6:
            raise DataIngestionError(
                f"ENTSO-E returned {int(nan_count)} NaN hours in prices. "
                "Refusing to ffill silently."
            )
        return df.ffill().bfill()  # type: ignore

    def _fetch_entsoe_fundamentals(
        self, start: pd.Timestamp, end: pd.Timestamp
    ) -> pd.DataFrame:
        try:
            from entsoe import EntsoePandasClient  # type: ignore
        except ImportError as e:
            raise DataIngestionError(
                "entsoe-py is not installed. pip install entsoe-py"
            ) from e

        client = EntsoePandasClient(api_key=str(self.api_key))
        start_ts = pd.Timestamp(start).tz_convert("Europe/Paris")
        end_ts = pd.Timestamp(end).tz_convert("Europe/Paris") + pd.Timedelta(days=1)

        load = client.query_load_forecast(
            self.country_code, start=start_ts, end=end_ts
        )
        if isinstance(load, pd.Series):
            load = load.to_frame(name="Load_Forecast")
        else:
            load = load.rename(columns={"Forecasted Load": "Load_Forecast"})

        wind_solar = client.query_wind_and_solar_forecast(
            self.country_code, start=start_ts, end=end_ts
        )
        gen = client.query_generation(
            self.country_code, start=start_ts, end=end_ts
        )
        nuclear = (
            gen["Nuclear"].sum(axis=1)
            if isinstance(gen["Nuclear"], pd.DataFrame)
            else gen["Nuclear"]
        )
        nuclear = nuclear.to_frame(name="Nuclear_Generation")

        df = load.join(wind_solar, how="outer").join(nuclear, how="outer")
        df = df.resample("1h").mean()

        rename_map = {
            "Solar": "Solar_Forecast",
            "Wind Onshore": "Wind_Onshore_Forecast",
            "Wind Offshore": "Wind_Offshore_Forecast",
        }
        df = df.rename(columns=rename_map)

        for col in [
            "Load_Forecast",
            "Solar_Forecast",
            "Wind_Onshore_Forecast",
            "Nuclear_Generation",
        ]:
            if col not in df.columns:
                df[col] = 0.0

        if "Wind_Offshore_Forecast" in df.columns:
            df["Wind_Forecast"] = (
                df["Wind_Onshore_Forecast"]
                + df["Wind_Offshore_Forecast"].fillna(0)
            )
        else:
            df["Wind_Forecast"] = df["Wind_Onshore_Forecast"]

        df = df[
            [
                "Load_Forecast",
                "Solar_Forecast",
                "Wind_Forecast",
                "Nuclear_Generation",
            ]
        ]
        df.index = pd.DatetimeIndex(df.index).tz_convert("UTC")
        return df.ffill().bfill()  # type: ignore
