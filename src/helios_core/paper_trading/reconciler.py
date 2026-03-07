"""
PaperTraderReconciler — Le Back-Office du Paper Trader.

Comptabilité implacable : croise les ordres (trades_log) avec les prix réels EPEX,
calcule le PnL verrouillé (frictions incluses). Aucune optimisation CVXPY.
"""

from __future__ import annotations

import json
import logging
from datetime import date

import numpy as np
import pandas as pd

from helios_core.exceptions import DataIngestionError
from helios_core.paper_trading.config import (
    PNL_LOG_PATH,
    TRADES_LOG_PATH,
    append_csv_with_lock,
    ensure_paper_data_dir,
)
from helios_core.paper_trading.live_data import LiveDataFetcher

logger = logging.getLogger(__name__)

# Frictions (alignées avec l'orchestrateur — stress_penalty ignoré pour la comptabilité)
MARGINAL_COST_EUR_PER_MWH = 15.0
FEE_BUY_EUR_PER_MWH = 2.0
FEE_SELL_EUR_PER_MWH = 2.0
CAPACITY_MWH = 10.0


class PaperTraderReconciler:
    """
    Réconciliateur : croise ordres et prix réels, calcule le PnL verrouillé.
    Strictement comptable — pas d'optimisation.
    """

    def __init__(self, country_code: str = "FR"):
        self.fetcher = LiveDataFetcher(country_code=country_code)
        ensure_paper_data_dir()

    def run(
        self,
        target_date: date,
        dry_run: bool = False,
        mock: bool = False,
    ) -> dict | None:
        """
        Réconcilie l'ordre du target_date avec les prix réels EPEX.

        mock: si True, utilise des prix synthétiques (pour tester sans API).

        Returns:
            Dict avec daily_pnl_eur, daily_cycles, etc. ou None si ordre/prix manquants.
        """
        target_str = target_date.isoformat()
        logger.info(
            f"PaperTraderReconciler.run(target_date={target_str}, dry_run={dry_run}, mock={mock})"
        )

        # 1. Lire trades_log et trouver l'ordre
        order_row = self._find_order(target_date)
        if order_row is None:
            logger.warning(f"Aucun ordre trouvé pour {target_str} dans {TRADES_LOG_PATH}")
            return None

        p_ch = json.loads(order_row["p_ch_array"])
        p_dis = json.loads(order_row["p_dis_array"])

        if len(p_ch) != 24 or len(p_dis) != 24:
            logger.error(
                f"Ordre invalide : p_ch/p_dis doivent avoir 24 éléments. "
                f"Reçu {len(p_ch)}, {len(p_dis)}."
            )
            return None

        # 2. Récupérer les prix (réels ou mock)
        if mock:
            prices = self._mock_prices()
        else:
            try:
                df_prices = self.fetcher.fetch_day_ahead_prices(target_str)
            except DataIngestionError as e:
                logger.error(
                    f"Impossible de récupérer les prix EPEX pour {target_str}. "
                    f"Les prix sont-ils déjà publiés ? {e}"
                )
                return None

            raw_prices = self._align_prices_to_hours(df_prices, target_date)
            prices = raw_prices  # type: ignore[assignment]

        if prices is None or len(prices) != 24:
            logger.error(
                f"Prix EPEX insuffisants pour {target_str}. "
                f"Attendu 24 heures, reçu {len(prices) if prices is not None else 0}."
            )
            return None

        assert prices is not None  # Narrow type for mypy
        # 4. Calcul du PnL horaire (frictions incluses)
        daily_pnl = 0.0
        for h in range(24):
            revenue = p_dis[h] * (prices[h] - FEE_SELL_EUR_PER_MWH)
            cost = p_ch[h] * (prices[h] + FEE_BUY_EUR_PER_MWH)
            wear = (p_ch[h] + p_dis[h]) * MARGINAL_COST_EUR_PER_MWH
            daily_pnl += revenue - cost - wear

        # 5. Cycles équivalents complets
        throughput = sum(p_ch[h] + p_dis[h] for h in range(24))
        daily_cycles = throughput / (2.0 * CAPACITY_MWH)

        result = {
            "target_date": target_str,
            "daily_pnl_eur": daily_pnl,
            "daily_cycles": daily_cycles,
            "actual_prices": prices,
        }

        # 6. Écriture (sauf dry-run)
        if not dry_run:
            self._append_to_pnl_log(result)

        logger.info(
            f"PnL réconcilié pour {target_str} | "
            f"daily_pnl={daily_pnl:.2f} € | cycles={daily_cycles:.4f}"
        )
        return result

    def _find_order(self, target_date: date) -> pd.Series | None:
        """Trouve la ligne de trades_log pour target_date."""
        if not TRADES_LOG_PATH.exists():
            return None

        df = pd.read_csv(TRADES_LOG_PATH)
        if "target_date" not in df.columns:
            return None

        target_str = target_date.isoformat()
        mask = df["target_date"] == target_str
        matches = df[mask]
        if len(matches) == 0:
            return None

        return matches.iloc[-1]  # Dernier ordre si doublons

    def _align_prices_to_hours(
        self, df_prices: pd.DataFrame, target_date: date
    ) -> list[float] | None:
        """
        Extrait 24 prix horaires pour target_date.
        Gère les résolutions 15min (96 points) ou 1h (24 points).
        """
        df = df_prices.copy()
        df.index = pd.to_datetime(df.index, utc=True)

        # Filtrer sur target_date (calendrier Paris)
        start_paris = pd.Timestamp(target_date, tz="Europe/Paris")
        end_paris = start_paris + pd.Timedelta(days=1)
        start_utc = start_paris.tz_convert("UTC")
        end_utc = end_paris.tz_convert("UTC")
        mask = (df.index >= start_utc) & (df.index < end_utc)
        df_day = df.loc[mask].sort_index()

        if len(df_day) == 0:
            return None

        # Resample à l'heure si > 24 points (ex: résolution 15min)
        if len(df_day) > 24:
            df_day = df_day.resample("1h").mean().ffill().bfill()

        prices = df_day["Price_EUR_MWh"].iloc[:24].tolist()
        nan_count = sum(1 for p in prices if pd.isna(p))
        if nan_count > 0:
            raise DataIngestionError(
                f"Prix EPEX : {nan_count} heures avec NaN pour {target_date}. "
                "Refuser de remplacer par 0 (Fail-Fast)."
            )
        prices = [float(p) for p in prices]

        while len(prices) < 24:
            prices.append(prices[-1] if prices else 0.0)

        return [float(x) for x in prices[:24]]

    def _mock_prices(self) -> list[float]:
        """Prix synthétiques pour tester sans API (profil type journée)."""
        rng = np.random.default_rng(42)
        base = 80 + 30 * np.sin(2 * np.pi * np.arange(24) / 24)
        prices = np.clip(base + rng.normal(0, 10, 24), 10, 200)
        return [float(p) for p in prices]

    def _append_to_pnl_log(self, result: dict) -> None:
        """Append une ligne à paper_pnl_log.csv."""
        import datetime as dt

        row = {
            "reconciled_at": dt.datetime.now(tz=dt.timezone.utc).isoformat(),
            "target_date": result["target_date"],
            "daily_pnl_eur": result["daily_pnl_eur"],
            "daily_cycles": result["daily_cycles"],
            "actual_prices_array": json.dumps([float(p) for p in result["actual_prices"]]),
        }

        df_row = pd.DataFrame([row])
        write_header = not PNL_LOG_PATH.exists()
        append_csv_with_lock(PNL_LOG_PATH, df_row, write_header)
        logger.info(f"PnL enregistré dans {PNL_LOG_PATH}")
