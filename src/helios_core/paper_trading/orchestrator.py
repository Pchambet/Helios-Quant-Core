"""
PaperTraderOrchestrator — Le cerveau opérationnel du Paper Trader.

Course contre la montre : à 10h30 Paris, il doit produire les ordres J+1
avant la Gate Closure de 12h00 CET.
"""

from __future__ import annotations

import json
import logging
from datetime import date

import numpy as np
import pandas as pd

from helios_core.assets.battery import BatteryAsset
from helios_core.assets.config import BatteryConfig
from helios_core.optimization.controller import BatteryMPC
from helios_core.optimization.scaling import PriceScaler
from helios_core.paper_trading.config import TRADES_LOG_PATH, ensure_paper_data_dir
from helios_core.paper_trading.live_data import LiveDataFetcher

logger = logging.getLogger(__name__)

# Constantes Twin (alignées avec BenchmarkRunner)
CAPACITY_MWH = 10.0
MAX_CHARGE_MW = 5.0
MAX_DISCHARGE_MW = 5.0
EFFICIENCY = 0.95
LOOKBACK_DAYS = 56
HORIZON_HOURS = 24


def _ensure_lightgbm() -> None:
    """Fail-fast si LightGBM absent. Pas de fallback pour le Paper Trading."""
    try:
        import lightgbm  # noqa: F401
    except ImportError as e:
        logger.error(
            "LightGBM est requis pour le Paper Trading. "
            "Installez via: uv pip install lightgbm"
        )
        raise SystemExit(1) from e


def _build_mock_dataset(target_date: date, lookback_days: int) -> pd.DataFrame:
    """Génère un DataFrame synthétique pour tester le pipeline sans API."""
    rng = np.random.default_rng(42)
    start = pd.Timestamp(target_date, tz="UTC") - pd.Timedelta(days=lookback_days)
    hours = lookback_days * 24
    idx = pd.date_range(start=start, periods=hours, freq="h", tz="UTC")

    # Prix type crise (base + saisonnalité + chocs)
    base = 80 + 20 * np.sin(2 * np.pi * np.arange(hours) / 168)
    prices = np.clip(base + rng.normal(0, 15, hours), -50, 500)

    df = pd.DataFrame(
        {
            "Price_EUR_MWh": prices,
            "Load_Forecast": 50000 + rng.normal(0, 3000, hours),
            "Wind_Forecast": 8000 + 3000 * np.sin(2 * np.pi * np.arange(hours) % 24 / 24),
            "Solar_Forecast": np.maximum(0, 4000 * np.sin(np.pi * (np.arange(hours) % 24 - 6) / 12)),
            "Nuclear_Generation": 40000 + rng.normal(0, 1000, hours),
        },
        index=idx,
    )
    return df.ffill().bfill()


def _compute_soc_trajectory(
    p_ch: np.ndarray,
    p_dis: np.ndarray,
    soc_init: float,
    eff_ch: float,
    eff_dis: float,
    leakage: float,
) -> np.ndarray:
    """Calcule la trajectoire SoC à partir des puissances optimales."""
    T = len(p_ch)
    soc = np.zeros(T + 1)
    soc[0] = soc_init
    for t in range(T):
        soc[t + 1] = (
            soc[t] * (1.0 - leakage)
            + p_ch[t] * eff_ch
            - p_dis[t] / eff_dis
        )
    return soc


class PaperTraderOrchestrator:
    """
    Orchestrateur du Paper Trading.
    Regarde le passé (ENTSO-E), l'avenir (météo), réfléchit (LightGBM + MPC), agit (trades_log).
    """

    def __init__(self, country_code: str = "FR", mock: bool = False):
        _ensure_lightgbm()
        self.mock = mock
        self.fetcher = LiveDataFetcher(country_code=country_code)
        ensure_paper_data_dir()

    def run(
        self,
        target_date: date,
        dry_run: bool = False,
        mock: bool = False,
    ) -> dict:
        """
        Exécute le pipeline complet pour la date cible (généralement demain).

        mock: si True, utilise HistoricalCrisisLoader (données synthétiques) pour tester sans API.

        Returns:
            Dict avec status, forecast_cve, p_ch, p_dis, soc, etc.
        """
        from helios_core.stochastic.price_forecaster import LightGBMPriceForecaster

        target_str = target_date.isoformat()
        logger.info(
            f"PaperTraderOrchestrator.run(target_date={target_str}, dry_run={dry_run}, mock={mock})"
        )

        # 1. Données : passé 56 jours + météo 48h (ou mock)
        if mock:
            df = _build_mock_dataset(target_date, LOOKBACK_DAYS)
        else:
            df = self.fetcher.build_full_dataset_for_forecast(
                lookback_days=LOOKBACK_DAYS,
                meteo_hours=48,
            )
        # Exclure les lignes futures (target_date et au-delà) pour le forecaster
        df = df[df.index < pd.Timestamp(target_date, tz="UTC")]

        # 2. Vérifier suffisamment de données (min 168h pour LightGBM)
        if len(df) < 168:
            raise ValueError(
                f"Données insuffisantes pour le forecaster (min 168h). "
                f"Reçu {len(df)} heures."
            )

        # 3. Inférence LightGBM
        forecaster = LightGBMPriceForecaster(lookback_days=LOOKBACK_DAYS)
        predicted_prices, forecast_cve = forecaster.forecast(
            past_data=df,
            horizon=HORIZON_HOURS,
        )
        predicted_prices = np.asarray(predicted_prices, dtype=float)
        if len(predicted_prices) != HORIZON_HOURS:
            predicted_prices = np.resize(
                predicted_prices,
                (HORIZON_HOURS,),
            )

        # 4. BatteryConfig frictionné (Brouillard de la Guerre)
        config = BatteryConfig(
            capacity_mwh=CAPACITY_MWH,
            max_charge_mw=MAX_CHARGE_MW,
            max_discharge_mw=MAX_DISCHARGE_MW,
            efficiency_charge=EFFICIENCY,
            efficiency_discharge=EFFICIENCY,
            marginal_cost_eur_per_mwh=15.0,
            grid_fee_buy_eur_per_mwh=2.0,
            grid_fee_sell_eur_per_mwh=2.0,
            stress_penalty_lambda=30.0,
        )

        # 5. MPC
        battery = BatteryAsset(config)
        scaler = PriceScaler()
        scaler.fit(np.concatenate([df["Price_EUR_MWh"].values, predicted_prices]))
        mpc = BatteryMPC(battery, scaler, alpha_slippage=5.0)

        p_ch, p_dis, status = mpc.solve_deterministic(predicted_prices)

        p_ch = np.asarray(p_ch, dtype=float)
        p_dis = np.asarray(p_dis, dtype=float)

        soc = _compute_soc_trajectory(
            p_ch, p_dis,
            soc_init=battery.soc_mwh,
            eff_ch=battery.efficiency_charge,
            eff_dis=battery.efficiency_discharge,
            leakage=battery.leakage_rate,
        )

        result = {
            "target_date": target_str,
            "status": str(status),
            "forecast_cve": float(forecast_cve),
            "forecast_prices": predicted_prices,
            "p_ch": p_ch,
            "p_dis": p_dis,
            "soc": soc,
        }

        # 6. Écriture (sauf dry-run)
        if not dry_run:
            self._append_to_trades_log(result)

        logger.info(
            f"Ordre généré pour {target_str} | status={status} | "
            f"CVE={forecast_cve:.4f} | sum(p_ch)={p_ch.sum():.2f} | sum(p_dis)={p_dis.sum():.2f}"
        )
        return result

    def _append_to_trades_log(self, result: dict) -> None:
        """Append une ligne au trades_log.csv (format JSON pour les vecteurs)."""
        import datetime as dt

        row = {
            "generated_at": dt.datetime.now(tz=dt.timezone.utc).isoformat(),
            "target_date": result["target_date"],
            "status": result["status"],
            "forecast_cve": result["forecast_cve"],
            "forecast_prices_array": json.dumps([float(x) for x in result["forecast_prices"]]),
            "p_ch_array": json.dumps([float(x) for x in result["p_ch"]]),
            "p_dis_array": json.dumps([float(x) for x in result["p_dis"]]),
            "soc_array": json.dumps([float(x) for x in result["soc"]]),
        }

        df_row = pd.DataFrame([row])
        write_header = not TRADES_LOG_PATH.exists()
        df_row.to_csv(
            TRADES_LOG_PATH,
            mode="a",
            header=write_header,
            index=False,
        )
        logger.info(f"Ordre enregistré dans {TRADES_LOG_PATH}")
