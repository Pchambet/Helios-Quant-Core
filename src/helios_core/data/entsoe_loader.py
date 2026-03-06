import os
import pandas as pd
import numpy as np
import logging
from dotenv import load_dotenv
from typing import cast

from helios_core.exceptions import DataIngestionError
from helios_core.utils.paths import DATA_DIR, ensure_data_dir

logger = logging.getLogger(__name__)

_DEFAULT_SYNTHETIC_SEED = 42

# Load local environment variables (where the API Key lives)
load_dotenv()


class HistoricalCrisisLoader:
    """
    Ingests and prepares the EPEX SPOT historical data for the Walk-Forward Backtest.
    By default, requires ENTSOE_API_KEY or cached Parquet files. Use mock=True for
    synthetic data (CI/CD, development without API access).
    """

    def __init__(
        self,
        start_date: str = "2022-08-01",
        end_date: str = "2022-12-31",
        seed: int | None = _DEFAULT_SYNTHETIC_SEED,
    ):
        self.start_date = pd.to_datetime(start_date)
        self.end_date = pd.to_datetime(end_date)
        self.api_key = os.getenv("ENTSOE_API_KEY")
        self._rng = np.random.default_rng(seed)

    def fetch_data(self, mock: bool = False) -> pd.DataFrame:
        """
        Returns a DataFrame with an hourly DatetimeIndex and a 'Price_EUR_MWh' column.
        Strictly ensuring no NaNs and proper timezone alignment (UTC).
        """
        # 1. Check if we already downloaded the immutable crisis file
        ensure_data_dir()
        date_str = self.start_date.strftime("%Y_%m")
        parquet_path = DATA_DIR / f"epex_{date_str}.parquet"

        if parquet_path.exists():
            logger.info(f"Loaded immutable crisis data from {parquet_path}")
            df = pd.read_parquet(parquet_path)
            df.index = pd.to_datetime(df.index, utc=True)
            return self._attach_fundamentals(self._attach_meteo(df), mock=False)

        # 2. If no file, try to hit the API
        if self.api_key:
            logger.info("ENTSOE_API_KEY detected. Fetching official API data...")
            df = self._fetch_entsoe()

            if "synthetic" not in df.columns:
                logger.info(f"Writing true historical data to {parquet_path}")
                df.to_parquet(parquet_path)
            return self._attach_fundamentals(self._attach_meteo(df), mock=False)

        # 3. No API key — mock or fail
        if mock:
            logger.warning(
                "No ENTSOE_API_KEY and no Parquet file. Using synthetic data (mock=True)."
            )
            df = self._generate_synthetic_crisis()
            df["synthetic"] = True  # type: ignore
            return self._attach_fundamentals(
                self._attach_meteo(df, mock=True), mock=True
            )
        raise DataIngestionError(
            "No ENTSOE_API_KEY and no cached Parquet file. "
            f"Provide API key, add data to {DATA_DIR}/, or use fetch_data(mock=True)."
        )

    def _attach_meteo(self, df: pd.DataFrame, mock: bool = False) -> pd.DataFrame:
        """
        Injects the Physical Weather Variables (Temperature, Wind, Direct Radiation)
        from Open-Meteo into the Economic Price DataFrame via an Inner Join matching UTC indices.
        Fails loud if meteo cannot be fetched or attached (no silent degradation).
        Use mock=True only when in full synthetic mode (fetch_data(mock=True)).
        """
        try:
            if mock:
                df_meteo = self._generate_synthetic_meteo(df.index)
            else:
                ensure_data_dir()
                date_str = self.start_date.strftime("%Y_%m")
                meteo_path = DATA_DIR / f"epex_{date_str}_weather.parquet"
                if meteo_path.exists():
                    logger.info(f"Loaded immutable meteo data from {meteo_path}")
                    df_meteo = pd.read_parquet(meteo_path)
                else:
                    from helios_core.data.meteo_loader import HistoricalMeteoLoader
                    loader = HistoricalMeteoLoader(
                        start_date=self.start_date.strftime("%Y-%m-%d"),
                        end_date=self.end_date.strftime("%Y-%m-%d")
                    )
                    df_meteo = loader.fetch_data()
                    df_meteo.to_parquet(meteo_path)

            df_meteo.index = pd.to_datetime(df_meteo.index, utc=True)
            df_joined = df.join(df_meteo, how='inner')
            logger.info(
                f"Meteorological properties permanently attached. Final size: {len(df_joined)}"
            )
            return df_joined  # type: ignore
        except (DataIngestionError, ValueError) as e:
            raise DataIngestionError(
                f"Failed to attach weather data: {e!s}"
            ) from e
        except Exception as e:
            raise DataIngestionError(
                f"Failed to attach weather data: {e!s}"
            ) from e

    def _fetch_entsoe(self) -> pd.DataFrame:
        try:
            from entsoe import EntsoePandasClient  # type: ignore
        except ImportError as e:
            raise DataIngestionError(
                "entsoe-py library is not installed. Install with: pip install entsoe-py"
            ) from e

        if not self.api_key:
            raise DataIngestionError("ENTSOE_API_KEY is not set.")

        client = EntsoePandasClient(api_key=str(self.api_key))
        start = pd.Timestamp(self.start_date, tz='Europe/Paris')
        end = pd.Timestamp(self.end_date, tz='Europe/Paris')
        country_code = 'FR'

        try:
            ts = client.query_day_ahead_prices(country_code, start=start, end=end)
            df = ts.to_frame(name='Price_EUR_MWh')

            dt_index = pd.DatetimeIndex(df.index)
            df.index = dt_index.tz_convert('UTC')
            df = df.ffill().bfill()
            return df  # type: ignore
        except Exception as e:
            raise DataIngestionError(f"ENTSO-E API failed: {e!s}") from e

    def _generate_synthetic_meteo(self, index: pd.DatetimeIndex) -> pd.DataFrame:
        """Synthetic weather for mock mode. Aligned with price index."""
        rng = self._rng
        n = len(index)
        return pd.DataFrame(
            {
                "Temperature_C": np.clip(
                    np.sin(2 * np.pi * np.arange(n) / 24) * 10 + 15
                    + rng.normal(0, 2, n),
                    -10,
                    40,
                ),
                "WindSpeed_kmh": np.maximum(0, rng.normal(15, 5, n)),
                "SolarIrradiance_WM2": np.maximum(
                    0,
                    np.sin(np.pi * (np.arange(n) % 24 - 6) / 12) * 400
                    + rng.normal(0, 50, n),
                ),
            },
            index=index,
        )

    def _generate_synthetic_crisis(self) -> pd.DataFrame:
        """
        Synthesizes the absolute madness of the Aug 2022 crisis:
        - Base price: ~400 EUR
        - Massive intraday peaks at 800 - 1500 EUR
        - High variance and volatility clustering.
        """
        hours = int((self.end_date - self.start_date).total_seconds() / 3600) + 24
        idx = pd.date_range(start=self.start_date, periods=hours, freq='h', tz='UTC')
        rng = self._rng

        # 1. Base structural regime (Winter/Crisis trend)
        base_trend = np.linspace(300, 150, hours)

        # 2. Daily Seasonality (Peak evening, slightly lower night)
        daily_seasonality = -100 * np.cos(2 * np.pi * idx.hour / 24) - 50 * np.cos(2 * np.pi * idx.hour / 12)

        # 3. Crisis Shocks (Volatility Clustering)
        shocks = rng.exponential(scale=100, size=hours)
        shock_multiplier = np.where(rng.random(hours) > 0.98, 5.0, 1.0)

        prices = base_trend + daily_seasonality + (shocks * shock_multiplier)

        # Cap and floor to realistic crisis boundaries
        prices = np.clip(prices, -50.0, 3000.0)

        return pd.DataFrame({'Price_EUR_MWh': prices}, index=idx)

    def _attach_fundamentals(self, df: pd.DataFrame, mock: bool = False) -> pd.DataFrame:
        """
        Injects ENTSO-E Physical Fundamentals (Load, Wind, Solar, Nuclear).
        Fails loud if fundamentals cannot be fetched (unless mock=True for synthetic).
        """
        ensure_data_dir()
        date_str = self.start_date.strftime("%Y_%m")
        fund_path = DATA_DIR / f"epex_{date_str}_fundamentals.parquet"

        if fund_path.exists():
            logger.info(f"Loaded immutable fundamentals data from {fund_path}")
            df_fund = pd.read_parquet(fund_path)
        else:
            df_fund = self._fetch_fundamentals(mock=mock)
            if "synthetic" not in df_fund.columns:
                df_fund.to_parquet(fund_path)

        df_fund.index = pd.to_datetime(df_fund.index, utc=True)
        df_fund = df_fund[~df_fund.index.duplicated(keep='first')]
        # Keep only physical columns (drop 'synthetic' if present to avoid join overlap)
        fund_cols = [
            'Load_Forecast', 'Solar_Forecast', 'Wind_Forecast', 'Nuclear_Generation'
        ]
        df_fund = df_fund[[c for c in fund_cols if c in df_fund.columns]]
        df_joined = df.join(df_fund, how='inner')
        logger.info(
            f"Physical fundamentals permanently attached. Final size: {len(df_joined)}"
        )
        return df_joined  # type: ignore

    def _fetch_fundamentals(self, mock: bool = False) -> pd.DataFrame:
        try:
            from entsoe import EntsoePandasClient  # type: ignore
        except ImportError as e:
            if mock:
                return self._generate_synthetic_fundamentals()
            raise DataIngestionError(
                "entsoe-py library is not installed. Install with: pip install entsoe-py"
            ) from e

        if not self.api_key:
            if mock:
                return self._generate_synthetic_fundamentals()
            raise DataIngestionError("ENTSOE_API_KEY is not set.")

        client = EntsoePandasClient(api_key=str(self.api_key))
        start = pd.Timestamp(self.start_date, tz='Europe/Paris')
        end = pd.Timestamp(self.end_date, tz='Europe/Paris') + pd.Timedelta(days=1)
        country_code = 'FR'

        try:
            logger.info(
                "Fetching ENTSO-E physical fundamentals (Load, Wind/Solar, Nuclear)..."
            )
            load = client.query_load_forecast(country_code, start=start, end=end)
            if isinstance(load, pd.Series):
                load = load.to_frame(name='Load_Forecast')
            else:
                load = load.rename(columns={'Forecasted Load': 'Load_Forecast'})

            wind_solar = client.query_wind_and_solar_forecast(
                country_code, start=start, end=end
            )
            gen = client.query_generation(country_code, start=start, end=end)
            nuclear = (
                gen['Nuclear'].sum(axis=1)
                if isinstance(gen['Nuclear'], pd.DataFrame)
                else gen['Nuclear']
            )
            nuclear = nuclear.to_frame(name='Nuclear_Generation')

            df_fund = load.join(wind_solar, how='outer').join(nuclear, how='outer')
            df_fund = df_fund.resample('1h').mean()

            rename_map = {
                'Solar': 'Solar_Forecast',
                'Wind Onshore': 'Wind_Onshore_Forecast',
                'Wind Offshore': 'Wind_Offshore_Forecast'
            }
            df_fund = df_fund.rename(columns=rename_map)

            for col in [
                'Load_Forecast',
                'Solar_Forecast',
                'Wind_Onshore_Forecast',
                'Nuclear_Generation'
            ]:
                if col not in df_fund.columns:
                    df_fund[col] = 0.0

            if 'Wind_Offshore_Forecast' in df_fund.columns:
                df_fund['Wind_Forecast'] = (
                    df_fund['Wind_Onshore_Forecast']
                    + df_fund['Wind_Offshore_Forecast'].fillna(0)
                )
            else:
                df_fund['Wind_Forecast'] = df_fund['Wind_Onshore_Forecast']

            df_fund = df_fund[
                ['Load_Forecast', 'Solar_Forecast', 'Wind_Forecast', 'Nuclear_Generation']
            ]

            dt_index = pd.DatetimeIndex(df_fund.index)
            df_fund.index = dt_index.tz_convert('UTC')
            df_fund = df_fund.ffill().bfill()
            return cast(pd.DataFrame, df_fund)
        except Exception as e:
            if mock:
                logger.warning(f"Fundamentals API failed: {e}. Using synthetic (mock=True).")
                return self._generate_synthetic_fundamentals()
            raise DataIngestionError(f"Fundamentals API failed: {e!s}") from e

    def _generate_synthetic_fundamentals(self) -> pd.DataFrame:
        hours = int((self.end_date - self.start_date).total_seconds() / 3600) + 48
        idx = pd.date_range(start=self.start_date, periods=hours, freq='h', tz='UTC')
        rng = self._rng
        n = len(idx)
        df_fund = pd.DataFrame(
            {
                'Load_Forecast': rng.normal(50000, 5000, n),
                'Solar_Forecast': np.maximum(
                    0,
                    np.sin(np.pi * (idx.hour - 6) / 12) * 5000
                    + rng.normal(0, 500, n),
                ),
                'Wind_Forecast': rng.normal(10000, 3000, n),
                'Nuclear_Generation': rng.normal(40000, 2000, n),
                'synthetic': True
            },
            index=idx,
        )
        return df_fund  # type: ignore

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    loader = HistoricalCrisisLoader()
    df = loader.fetch_data()
    print("Crisis DataFrame Shape:", df.shape)
    print("Max Price Reached:", df['Price_EUR_MWh'].max())
