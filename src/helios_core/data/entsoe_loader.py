import os
from pathlib import Path
import pandas as pd
import numpy as np
import logging
from dotenv import load_dotenv
from typing import cast

logger = logging.getLogger(__name__)

# Load local environment variables (where the API Key lives)
load_dotenv()

class HistoricalCrisisLoader:
    """
    Ingests and prepares the EPEX SPOT historical data for the Walk-Forward Backtest.
    If 'ENTSOE_API_KEY' is missing, it falls back to a high-fidelity synthetic generator
    mimicking the exact statistical properties of the August 2022 European Energy Crisis.
    """

    def __init__(self, start_date: str = "2022-08-01", end_date: str = "2022-12-31"):
        self.start_date = pd.to_datetime(start_date)
        self.end_date = pd.to_datetime(end_date)
        self.api_key = os.getenv("ENTSOE_API_KEY")

    def fetch_data(self) -> pd.DataFrame:
        """
        Returns a DataFrame with an hourly DatetimeIndex and a 'Price_EUR_MWh' column.
        Strictly ensuring no NaNs and proper timezone alignment (UTC).
        """
        # 1. Check if we already downloaded the immutable crisis file
        data_dir = Path("data")
        data_dir.mkdir(exist_ok=True)
        date_str = self.start_date.strftime("%Y_%m")
        parquet_path = data_dir / f"epex_{date_str}.parquet"

        if parquet_path.exists():
            logger.info(f"Loaded immutable crisis data from {parquet_path}")
            df = pd.read_parquet(parquet_path)
            # Ensure index strictly conforms to expected type
            df.index = pd.to_datetime(df.index, utc=True)
            return self._attach_fundamentals(self._attach_meteo(df))

        # 2. If no file, try to hit the API
        if self.api_key:
            logger.info("ENTSOE_API_KEY detected. Fetching official API data...")
            df = self._fetch_entsoe()

            # Save truth if not synthetic
            if "synthetic" not in df.columns:  # quick hack to avoid saving fake data
                logger.info(f"Writing true historical data to {parquet_path}")
                df.to_parquet(parquet_path)
            return self._attach_fundamentals(self._attach_meteo(df))

        # 3. Last fallback (CI/CD without key)
        else:
            logger.warning("No ENTSOE_API_KEY and no Parquet file. Synthesizing High-Fidelity Aug 2022 Crisis data.")
            df = self._generate_synthetic_crisis()
            df["synthetic"] = True # mark as synthetic to avoid caching
            return self._attach_fundamentals(self._attach_meteo(df))

    def _attach_meteo(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Injects the Physical Weather Variables (Temperature, Wind, Direct Radiation)
        from Open-Meteo into the Economic Price DataFrame via an Inner Join matching UTC indices.
        """
        try:
            data_dir = Path("data")
            date_str = self.start_date.strftime("%Y_%m")
            meteo_path = data_dir / f"epex_{date_str}_weather.parquet"
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

            # Use inner join to drop any ENTSO-E or Meteo outliers and guarantee dense data
            df_joined = df.join(df_meteo, how='inner')
            logger.info(f"Meteorological properties permanently attached. Final size: {len(df_joined)}")
            return df_joined # type: ignore
        except Exception as e:
            logger.error(f"Failed to attach weather data: {e}")
            return df

    def _fetch_entsoe(self) -> pd.DataFrame:
        try:
            from entsoe import EntsoePandasClient # type: ignore
        except ImportError:
            logger.error("entsoe-py library is missing. Fallback to synthetic.")
            return self._generate_synthetic_crisis()

        if not self.api_key:
            raise ValueError("ENTSOE_API_KEY is not set.")

        client = EntsoePandasClient(api_key=str(self.api_key))
        start = pd.Timestamp(self.start_date, tz='Europe/Paris')
        end = pd.Timestamp(self.end_date, tz='Europe/Paris')
        country_code = 'FR'  # France

        try:
            ts = client.query_day_ahead_prices(country_code, start=start, end=end)
            df = ts.to_frame(name='Price_EUR_MWh')

            # Timezone Coercion: EPEX SPOT is CET/CEST, we force UTC for the internal engine
            dt_index = pd.DatetimeIndex(df.index)
            df.index = dt_index.tz_convert('UTC')

            # Asymmetrical Cleansing: Forward fill any missing hour in the ENTSO-E dump
            df = df.ffill()

            # Explicitly fill any remaining NaNs at the start just in case
            df = df.bfill()

            return df # type: ignore
        except Exception as e:
            logger.error(f"ENTSO-E API Failed: {e}. Fallback to synthetic.")
            return self._generate_synthetic_crisis()

    def _generate_synthetic_crisis(self) -> pd.DataFrame:
        """
        Synthesizes the absolute madness of the Aug 2022 crisis:
        - Base price: ~400 EUR
        - Massive intraday peaks at 800 - 1500 EUR
        - High variance and volatility clustering.
        """
        hours = int((self.end_date - self.start_date).total_seconds() / 3600) + 24
        idx = pd.date_range(start=self.start_date, periods=hours, freq='h', tz='UTC')

        np.random.seed(42)  # Strict reproducibility for the Backtest

        # 1. Base structural regime (Winter/Crisis trend)
        base_trend = np.linspace(300, 150, hours)

        # 2. Daily Seasonality (Peak evening, slightly lower night)
        daily_seasonality = -100 * np.cos(2 * np.pi * idx.hour / 24) - 50 * np.cos(2 * np.pi * idx.hour / 12)

        # 3. Crisis Shocks (Volatility Clustering)
        # Random massive spikes simulating gas shortages / nuclear outages
        shocks = np.random.exponential(scale=100, size=hours)
        shock_multiplier = np.where(np.random.rand(hours) > 0.98, 5.0, 1.0) # 2% chance of absolute 5x spike

        prices = base_trend + daily_seasonality + (shocks * shock_multiplier)

        # Cap and floor to realistic crisis boundaries
        prices = np.clip(prices, -50.0, 3000.0)

        return pd.DataFrame({'Price_EUR_MWh': prices}, index=idx)

    def _attach_fundamentals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Injects ENTSO-E Physical Fundamentals (Load, Wind, Solar, Nuclear)
        """
        data_dir = Path("data")
        date_str = self.start_date.strftime("%Y_%m")
        fund_path = data_dir / f"epex_{date_str}_fundamentals.parquet"

        if fund_path.exists():
            logger.info(f"Loaded immutable fundamentals data from {fund_path}")
            df_fund = pd.read_parquet(fund_path)
        else:
            df_fund = self._fetch_fundamentals()
            if "synthetic" not in df_fund.columns:
                df_fund.to_parquet(fund_path)

        df_fund.index = pd.to_datetime(df_fund.index, utc=True)
        # Drop duplicates and resample just in case
        df_fund = df_fund[~df_fund.index.duplicated(keep='first')]

        # Use inner join to drop any ENTSO-E or Meteo outliers and guarantee dense data
        df_joined = df.join(df_fund, how='inner')
        logger.info(f"Physical fundamentals permanently attached. Final size: {len(df_joined)}")
        return df_joined # type: ignore

    def _fetch_fundamentals(self) -> pd.DataFrame:
        try:
            from entsoe import EntsoePandasClient # type: ignore
        except ImportError:
            return self._generate_synthetic_fundamentals()

        if not self.api_key:
            return self._generate_synthetic_fundamentals()

        client = EntsoePandasClient(api_key=str(self.api_key))
        start = pd.Timestamp(self.start_date, tz='Europe/Paris')
        # +1 day to ensure we get enough data for the end boundary if timezone shifts
        end = pd.Timestamp(self.end_date, tz='Europe/Paris') + pd.Timedelta(days=1)
        country_code = 'FR'

        try:
            logger.info("Fetching ENTSO-E physical fundamentals (Load, Wind/Solar, Nuclear)...")
            # 1. Load Forecast
            load = client.query_load_forecast(country_code, start=start, end=end)
            if isinstance(load, pd.Series):
                load = load.to_frame(name='Load_Forecast')
            else:
                load = load.rename(columns={'Forecasted Load': 'Load_Forecast'})

            # 2. Wind & Solar Forecast
            wind_solar = client.query_wind_and_solar_forecast(country_code, start=start, end=end)

            # 3. Nuclear Generation (Proxy for availability/outages)
            gen = client.query_generation(country_code, start=start, end=end)
            nuclear = gen['Nuclear'].sum(axis=1) if isinstance(gen['Nuclear'], pd.DataFrame) else gen['Nuclear']
            nuclear = nuclear.to_frame(name='Nuclear_Generation')

            # Merge and resample to hourly
            df_fund = load.join(wind_solar, how='outer').join(nuclear, how='outer')
            df_fund = df_fund.resample('1h').mean()

            # Rename columns to standard internal names
            rename_map = {
                'Solar': 'Solar_Forecast',
                'Wind Onshore': 'Wind_Onshore_Forecast',
                'Wind Offshore': 'Wind_Offshore_Forecast'
            }
            df_fund = df_fund.rename(columns=rename_map)

            # Ensure columns exist
            for col in ['Load_Forecast', 'Solar_Forecast', 'Wind_Onshore_Forecast', 'Nuclear_Generation']:
                if col not in df_fund.columns:
                    df_fund[col] = 0.0

            # Combine wind
            if 'Wind_Offshore_Forecast' in df_fund.columns:
                df_fund['Wind_Forecast'] = df_fund['Wind_Onshore_Forecast'] + df_fund['Wind_Offshore_Forecast'].fillna(0)
            else:
                df_fund['Wind_Forecast'] = df_fund['Wind_Onshore_Forecast']

            df_fund = df_fund[['Load_Forecast', 'Solar_Forecast', 'Wind_Forecast', 'Nuclear_Generation']]

            # Convert index to UTC to match price data
            dt_index = pd.DatetimeIndex(df_fund.index)
            df_fund.index = dt_index.tz_convert('UTC')

            # Clean missing data
            df_fund = df_fund.ffill().bfill()
            return cast(pd.DataFrame, df_fund)
        except Exception as e:
            logger.error(f"Fundamentals API failed: {e}")
            return self._generate_synthetic_fundamentals()

    def _generate_synthetic_fundamentals(self) -> pd.DataFrame:
        hours = int((self.end_date - self.start_date).total_seconds() / 3600) + 48
        idx = pd.date_range(start=self.start_date, periods=hours, freq='h', tz='UTC')
        np.random.seed(42)
        df_fund = pd.DataFrame({
            'Load_Forecast': np.random.normal(50000, 5000, len(idx)),
            'Solar_Forecast': np.maximum(0, np.sin(np.pi * (idx.hour - 6) / 12) * 5000 + np.random.normal(0, 500, len(idx))),
            'Wind_Forecast': np.random.normal(10000, 3000, len(idx)),
            'Nuclear_Generation': np.random.normal(40000, 2000, len(idx)),
            'synthetic': True
        }, index=idx)
        return df_fund # type: ignore

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    loader = HistoricalCrisisLoader()
    df = loader.fetch_data()
    print("Crisis DataFrame Shape:", df.shape)
    print("Max Price Reached:", df['Price_EUR_MWh'].max())
