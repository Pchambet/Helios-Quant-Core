"""
Paper Tear Sheet — Instrumentation clinique du Paper Trading.

Métriques systémiques pour auditer la dérive du modèle :
1. Erreur Out-of-Sample (CVE réel)
2. Hit Ratio sur la Zone Morte (34 €/MWh)
3. Télémétrie d'exécution (gaps, NaN)
"""

from __future__ import annotations

import json
import logging

import numpy as np
import pandas as pd

from helios_core.paper_trading.config import PNL_LOG_PATH, TRADES_LOG_PATH

logger = logging.getLogger(__name__)

HURDLE_RATE_EUR_MWH = 34.0  # LCOS + Fees


def load_trades_log() -> pd.DataFrame:
    """Charge trades_log.csv. Retourne DataFrame vide si absent."""
    if not TRADES_LOG_PATH.exists():
        return pd.DataFrame()
    df = pd.read_csv(TRADES_LOG_PATH)
    df["target_date"] = pd.to_datetime(df["target_date"]).dt.date
    return df


def load_pnl_log() -> pd.DataFrame:
    """Charge paper_pnl_log.csv. Retourne DataFrame vide si absent."""
    if not PNL_LOG_PATH.exists():
        return pd.DataFrame()
    df = pd.read_csv(PNL_LOG_PATH)
    df["target_date"] = pd.to_datetime(df["target_date"]).dt.date
    return df


def compute_oos_error(
    trades: pd.DataFrame, pnl: pd.DataFrame
) -> dict[str, float] | None:
    """
    Erreur Out-of-Sample : compare forecast (10h30) vs actual (13h00).
    Nécessite forecast_prices_array (trades) et actual_prices_array (pnl).
    """
    if "forecast_prices_array" not in trades.columns or "actual_prices_array" not in pnl.columns:
        logger.warning("OOS Error: forecast_prices_array ou actual_prices_array manquant.")
        return None

    merged = trades.merge(
        pnl[["target_date", "actual_prices_array"]],
        on="target_date",
        how="inner",
    )
    if len(merged) == 0:
        return None

    errors: list[float] = []
    for _, row in merged.iterrows():
        try:
            pred = np.array(json.loads(row["forecast_prices_array"]))
            actual = np.array(json.loads(row["actual_prices_array"]))
        except (json.JSONDecodeError, KeyError):
            continue
        if len(pred) != 24 or len(actual) != 24:
            continue
        errors.extend((pred - actual).tolist())

    if not errors:
        return None

    err_arr = np.array(errors)
    rmse = float(np.sqrt(np.mean(err_arr**2)))
    mean_abs = float(np.mean(np.abs(err_arr)))
    cve = rmse / mean_abs if mean_abs > 1e-6 else 0.0

    return {"rmse_eur_mwh": rmse, "cve_oos": cve, "n_hours": len(errors)}


def compute_hit_ratio_dead_zone(
    trades: pd.DataFrame, pnl: pd.DataFrame
) -> dict | None:
    """
    Hit Ratio Zone Morte : agent bouge + spread réel > 34 = hit.
    Agent figé + spread réel > 34 = opportunité manquée.
    """
    if "actual_prices_array" not in pnl.columns:
        logger.warning("Hit Ratio: actual_prices_array manquant dans pnl_log.")
        return None

    merged = trades.merge(
        pnl[["target_date", "actual_prices_array", "daily_pnl_eur"]],
        on="target_date",
        how="inner",
    )
    if len(merged) == 0:
        return None

    hits = 0
    misses = 0
    correct_stays = 0
    missed_opportunities = 0

    for _, row in merged.iterrows():
        try:
            p_ch = np.array(json.loads(row["p_ch_array"]))
            p_dis = np.array(json.loads(row["p_dis_array"]))
            actual = np.array(json.loads(row["actual_prices_array"]))
        except (json.JSONDecodeError, KeyError):
            continue

        if len(actual) != 24:
            continue

        spread_real = float(np.max(actual) - np.min(actual))
        traded = np.sum(p_ch) + np.sum(p_dis) > 1e-6

        if traded and spread_real >= HURDLE_RATE_EUR_MWH:
            hits += 1
        elif traded and spread_real < HURDLE_RATE_EUR_MWH:
            misses += 1
        elif not traded and spread_real < HURDLE_RATE_EUR_MWH:
            correct_stays += 1
        else:
            missed_opportunities += 1

    total = hits + misses + correct_stays + missed_opportunities
    if total == 0:
        return None

    return {
        "hits": hits,
        "misses": misses,
        "correct_stays": correct_stays,
        "missed_opportunities": missed_opportunities,
        "hit_ratio": hits / (hits + misses) if (hits + misses) > 0 else 0.0,
        "opportunity_cost_days": missed_opportunities,
    }


def compute_execution_telemetry(
    trades: pd.DataFrame, pnl: pd.DataFrame
) -> dict:
    """
    Télémétrie : gaps de dates, NaN, intégrité.
    """
    trades_dates = set(trades["target_date"].dropna().tolist()) if len(trades) > 0 else set()
    pnl_dates = set(pnl["target_date"].dropna().tolist()) if len(pnl) > 0 else set()

    # Ordres sans réconciliation
    orders_without_recon = trades_dates - pnl_dates
    # Réconciliations sans ordre (anormal)
    recon_without_order = pnl_dates - trades_dates

    # NaN dans les colonnes critiques
    nan_counts = {}
    for col in ["p_ch_array", "p_dis_array", "status"]:
        if col in trades.columns:
            nan_counts[f"trades_{col}"] = int(trades[col].isna().sum())
    for col in ["daily_pnl_eur", "daily_cycles"]:
        if col in pnl.columns:
            nan_counts[f"pnl_{col}"] = int(pnl[col].isna().sum())

    # Série temporelle : dates attendues (jours ouvrés) vs observés
    if len(trades) > 0:
        min_d = min(trades_dates) if trades_dates else None
        max_d = max(trades_dates) if trades_dates else None
        if min_d and max_d:
            expected_days = (max_d - min_d).days + 1
            observed_days = len(trades_dates)
            gap_days = expected_days - observed_days
        else:
            expected_days = observed_days = gap_days = 0
    else:
        expected_days = observed_days = gap_days = 0

    return {
        "n_orders": len(trades),
        "n_reconciliations": len(pnl),
        "orders_without_recon": list(orders_without_recon),
        "recon_without_order": list(recon_without_order),
        "nan_counts": nan_counts,
        "expected_days": expected_days,
        "observed_days": observed_days,
        "gap_days": gap_days,
    }


def run_tear_sheet() -> dict:
    """
    Exécute l'analyse complète et retourne un rapport.
    """
    trades = load_trades_log()
    pnl = load_pnl_log()

    report: dict = {
        "oos_error": None,
        "hit_ratio": None,
        "telemetry": {},
        "summary": {},
    }

    report["oos_error"] = compute_oos_error(trades, pnl)
    report["hit_ratio"] = compute_hit_ratio_dead_zone(trades, pnl)
    report["telemetry"] = compute_execution_telemetry(trades, pnl)

    # Résumé PnL
    if len(pnl) > 0 and "daily_pnl_eur" in pnl.columns:
        report["summary"] = {
            "cumulative_pnl_eur": float(pnl["daily_pnl_eur"].sum()),
            "mean_daily_pnl_eur": float(pnl["daily_pnl_eur"].mean()),
            "n_days": len(pnl),
        }

    return report


def print_tear_sheet(report: dict) -> None:
    """Affiche le rapport en console."""
    print("\n" + "=" * 60)
    print(" HELIOS PAPER TEAR SHEET — Audit du réel")
    print("=" * 60)

    print("\n[1] Erreur Out-of-Sample (CVE réel)")
    if report["oos_error"]:
        oos = report["oos_error"]
        print(f"  RMSE: {oos['rmse_eur_mwh']:.2f} €/MWh")
        print(f"  CVE OOS: {oos['cve_oos']:.4f}")
        print(f"  Heures analysées: {oos['n_hours']}")
    else:
        print("  (Données insuffisantes — forecast/actual manquants)")

    print("\n[2] Hit Ratio Zone Morte (34 €/MWh)")
    if report["hit_ratio"]:
        hr = report["hit_ratio"]
        print(f"  Hits (trade + spread>34): {hr['hits']}")
        print(f"  Misses (trade + spread<34): {hr['misses']}")
        print(f"  Correct stays (figé + spread<34): {hr['correct_stays']}")
        print(f"  Opportunités manquées (figé + spread>34): {hr['missed_opportunities']}")
        print(f"  Hit Ratio: {hr['hit_ratio']:.2%}")
    else:
        print("  (Données insuffisantes)")

    print("\n[3] Télémétrie d'exécution")
    tel = report["telemetry"]
    print(f"  Ordres: {tel.get('n_orders', 0)} | Réconciliations: {tel.get('n_reconciliations', 0)}")
    print(f"  Ordres sans recon: {len(tel.get('orders_without_recon', []))}")
    print(f"  Jours manquants (gaps): {tel.get('gap_days', 0)}")
    if tel.get("nan_counts"):
        print(f"  NaN: {tel['nan_counts']}")

    print("\n[4] Résumé PnL")
    if report["summary"]:
        s = report["summary"]
        print(f"  PnL cumulé: {s['cumulative_pnl_eur']:.2f} €")
        print(f"  PnL moyen/jour: {s['mean_daily_pnl_eur']:.2f} €")
        print(f"  Jours: {s['n_days']}")
    else:
        print("  (Aucune réconciliation)")

    print("=" * 60 + "\n")
