"""
Tear Sheet post-mortem du Paper Trading.

Instrumentation clinique pour mesurer la dérive du modèle :
1. Erreur Out-of-Sample (CVE réel) : prévision vs prix réels
2. Hit Ratio Zone Morte : opportunités captées vs manquées
3. Télémétrie d'exécution : intégrité de la série temporelle

Usage:
  uv run python run_paper_tear_sheet.py
  uv run python run_paper_tear_sheet.py --min-days 5  # Exiger 5 jours minimum
"""
from __future__ import annotations

import argparse
import json
import logging

import pandas as pd

from helios_core.paper_trading.config import PNL_LOG_PATH, TRADES_LOG_PATH
from helios_core.utils.paths import ensure_reports_dir

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

HURDLE_RATE_EUR_MWH = 34.0  # LCOS 15 + Fees 2×2 + marge


def load_trades_log() -> pd.DataFrame:
    """Charge trades_log.csv. Retourne DataFrame vide si absent."""
    if not TRADES_LOG_PATH.exists():
        logger.warning(f"{TRADES_LOG_PATH} introuvable.")
        return pd.DataFrame()

    df = pd.read_csv(TRADES_LOG_PATH)
    df["target_date"] = pd.to_datetime(df["target_date"]).dt.date
    return df


def load_pnl_log() -> pd.DataFrame:
    """Charge paper_pnl_log.csv. Retourne DataFrame vide si absent."""
    if not PNL_LOG_PATH.exists():
        logger.warning(f"{PNL_LOG_PATH} introuvable.")
        return pd.DataFrame()

    df = pd.read_csv(PNL_LOG_PATH)
    df["target_date"] = pd.to_datetime(df["target_date"]).dt.date
    return df


def compute_oos_error(trades: pd.DataFrame, pnl: pd.DataFrame) -> dict:
    """
    Erreur Out-of-Sample : RMSE(forecast, actual) / mean(|actual|).
    Nécessite forecast_prices_array (trades) et actual_prices_array (pnl).
    """
    if "forecast_prices_array" not in trades.columns or "actual_prices_array" not in pnl.columns:
        return {
            "oos_rmse": None,
            "oos_cve": None,
            "n_days": 0,
            "message": "Colonnes forecast_prices_array / actual_prices_array manquantes (données anciennes).",
        }

    merged = trades.merge(
        pnl[["target_date", "actual_prices_array"]],
        on="target_date",
        how="inner",
    )
    if len(merged) == 0:
        return {"oos_rmse": None, "oos_cve": None, "n_days": 0, "message": "Aucune journée commune."}

    all_errors = []
    all_actuals = []
    for _, row in merged.iterrows():
        try:
            forecast = json.loads(row["forecast_prices_array"])
            actual = json.loads(row["actual_prices_array"])
        except (json.JSONDecodeError, KeyError, TypeError):
            continue
        if len(forecast) != 24 or len(actual) != 24:
            continue
        for h in range(24):
            all_errors.append((float(forecast[h]) - float(actual[h])) ** 2)
            all_actuals.append(abs(float(actual[h])))

    if not all_errors:
        return {"oos_rmse": None, "oos_cve": None, "n_days": len(merged), "message": "Données invalides."}

    rmse = (sum(all_errors) / len(all_errors)) ** 0.5
    mean_abs = sum(all_actuals) / len(all_actuals)
    cve = rmse / mean_abs if mean_abs > 1e-6 else 0.0

    return {
        "oos_rmse": rmse,
        "oos_cve": cve,
        "n_days": len(merged),
        "message": None,
    }


def compute_hit_ratio_dead_zone(trades: pd.DataFrame, pnl: pd.DataFrame) -> dict:
    """
    Hit Ratio Zone Morte :
    - Hit : agent a tradé ET spread réel > 34 €/MWh
    - Miss : agent n'a pas tradé ET spread réel > 34 €/MWh (coût d'opportunité)
    - Correct pass : agent n'a pas tradé ET spread réel <= 34 €/MWh
    """
    if "actual_prices_array" not in pnl.columns:
        return {
            "hits": 0,
            "misses": 0,
            "correct_passes": 0,
            "hit_ratio": None,
            "opportunity_cost_days": 0,
            "message": "Colonne actual_prices_array manquante.",
        }

    merged = trades.merge(
        pnl[["target_date", "actual_prices_array", "daily_pnl_eur"]],
        on="target_date",
        how="inner",
    )
    if len(merged) == 0:
        return {"hits": 0, "misses": 0, "correct_passes": 0, "hit_ratio": None, "opportunity_cost_days": 0}

    hits = 0
    misses = 0
    correct_passes = 0

    for _, row in merged.iterrows():
        try:
            actual = json.loads(row["actual_prices_array"])
        except (json.JSONDecodeError, KeyError, TypeError):
            continue
        if len(actual) != 24:
            continue

        real_spread = max(actual) - min(actual)
        traded = False
        if "p_ch_array" in row and "p_dis_array" in row:
            try:
                p_ch = json.loads(row["p_ch_array"])
                p_dis = json.loads(row["p_dis_array"])
                throughput = sum(p_ch) + sum(p_dis)
                traded = throughput > 1e-6
            except (json.JSONDecodeError, KeyError, TypeError):
                pass

        spread_above_hurdle = real_spread > HURDLE_RATE_EUR_MWH

        if traded and spread_above_hurdle:
            hits += 1
        elif not traded and spread_above_hurdle:
            misses += 1
        elif not traded and not spread_above_hurdle:
            correct_passes += 1
        # traded + spread <= hurdle : rare (agent a mal anticipé), on compte comme hit négatif ou autre

    hit_ratio = hits / (hits + misses) if (hits + misses) > 0 else None

    return {
        "hits": hits,
        "misses": misses,
        "correct_passes": correct_passes,
        "hit_ratio": hit_ratio,
        "opportunity_cost_days": misses,
        "n_days": len(merged),
    }


def compute_execution_telemetry(trades: pd.DataFrame, pnl: pd.DataFrame) -> dict:
    """
    Télémétrie : trous dans la série, NaN, cohérence orchestrateur/réconciliateur.
    """
    if len(trades) == 0:
        return {
            "trades_count": 0,
            "pnl_count": 0,
            "missing_reconciliations": 0,
            "missing_orders": 0,
            "nan_in_trades": False,
            "date_range": None,
        }

    trades_dates = set(trades["target_date"].dropna().astype(str))
    pnl_dates = set(pnl["target_date"].dropna().astype(str))

    missing_recon = len(trades_dates - pnl_dates)
    missing_orders = len(pnl_dates - trades_dates)

    nan_trades = trades.isna().any().any()
    nan_pnl = pnl.isna().any().any()

    all_dates = sorted(trades_dates | pnl_dates)
    date_range = f"{all_dates[0]} → {all_dates[-1]}" if all_dates else None

    return {
        "trades_count": len(trades),
        "pnl_count": len(pnl),
        "missing_reconciliations": missing_recon,
        "missing_orders": missing_orders,
        "nan_in_trades": bool(nan_trades),
        "nan_in_pnl": bool(nan_pnl),
        "date_range": date_range,
    }


def print_tear_sheet(
    oos: dict,
    hit: dict,
    telemetry: dict,
    pnl: pd.DataFrame,
) -> None:
    """Affiche le tear sheet en console."""
    print("\n" + "=" * 70)
    print(" HELIOS PAPER TRADING — TEAR SHEET POST-MORTEM ")
    print("=" * 70)

    print("\n--- 1. Erreur Out-of-Sample (CVE réel LightGBM) ---")
    if oos["message"]:
        print(f"  {oos['message']}")
    else:
        print(f"  RMSE (€/MWh)     : {oos['oos_rmse']:.2f}")
        print(f"  CVE (ratio)      : {oos['oos_cve']:.4f}")
        print(f"  Jours analysés   : {oos['n_days']}")

    print("\n--- 2. Hit Ratio Zone Morte (34 €/MWh) ---")
    if hit.get("message"):
        print(f"  {hit['message']}")
    else:
        print(f"  Hits (tradé + spread>34)   : {hit['hits']}")
        print(f"  Misses (pas tradé + spread>34) : {hit['misses']}")
        print(f"  Correct pass (pas tradé + spread≤34) : {hit['correct_passes']}")
        if hit["hit_ratio"] is not None:
            print(f"  Hit Ratio : {hit['hit_ratio']:.1%}")
        print(f"  Jours opportunité manquée : {hit['opportunity_cost_days']}")

    print("\n--- 3. Télémétrie d'exécution ---")
    print(f"  Ordres (trades_log)    : {telemetry['trades_count']}")
    print(f"  Réconciliations (pnl) : {telemetry['pnl_count']}")
    print(f"  Ordres sans réconciliation : {telemetry['missing_reconciliations']}")
    print(f"  Réconciliations sans ordre : {telemetry['missing_orders']}")
    print(f"  NaN dans les logs      : trades={telemetry['nan_in_trades']}, pnl={telemetry.get('nan_in_pnl', False)}")
    if telemetry["date_range"]:
        print(f"  Période                : {telemetry['date_range']}")

    if len(pnl) > 0 and "daily_pnl_eur" in pnl.columns:
        total_pnl = pnl["daily_pnl_eur"].sum()
        print("\n--- 4. PnL cumulé ---")
        print(f"  Total (€) : {total_pnl:.2f}")

    print("\n" + "=" * 70 + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Tear Sheet post-mortem du Paper Trading"
    )
    parser.add_argument(
        "--min-days",
        type=int,
        default=1,
        help="Nombre minimum de jours pour considérer l'analyse valide.",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=None,
        help="Chemin du rapport PNG (défaut: reports/paper_tear_sheet.png)",
    )
    args = parser.parse_args()

    trades = load_trades_log()
    pnl = load_pnl_log()

    if len(trades) < args.min_days and len(pnl) < args.min_days:
        logger.warning(
            f"Données insuffisantes (min {args.min_days} jours). "
            f"trades={len(trades)}, pnl={len(pnl)}"
        )
        return

    oos = compute_oos_error(trades, pnl)
    hit = compute_hit_ratio_dead_zone(trades, pnl)
    telemetry = compute_execution_telemetry(trades, pnl)

    print_tear_sheet(oos, hit, telemetry, pnl)

    if args.output or True:
        out_path = args.output or (ensure_reports_dir() / "paper_tear_sheet.png")
        try:
            _export_visual(trades, pnl, oos, hit, telemetry, str(out_path))
            logger.info(f"Rapport visuel exporté : {out_path}")
        except Exception as e:
            logger.warning(f"Export visuel ignoré : {e}")


def _export_visual(
    trades: pd.DataFrame,
    pnl: pd.DataFrame,
    oos: dict,
    hit: dict,
    telemetry: dict,
    path: str,
) -> None:
    """Exporte un graphique résumé (optionnel)."""
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(2, 1, figsize=(10, 8), sharex=False)

    if len(pnl) > 0 and "daily_pnl_eur" in pnl.columns:
        pnl_sorted = pnl.sort_values("target_date")
        pnl_sorted["cumulative_pnl"] = pnl_sorted["daily_pnl_eur"].cumsum()
        axes[0].bar(
            range(len(pnl_sorted)),
            pnl_sorted["daily_pnl_eur"],
            color=["green" if x >= 0 else "red" for x in pnl_sorted["daily_pnl_eur"]],
            alpha=0.8,
        )
        axes[0].set_ylabel("PnL journalier (€)")
        axes[0].set_title("PnL par jour")
        axes[0].axhline(0, color="black", linewidth=0.5)

        ax2 = axes[0].twinx()
        ax2.plot(
            range(len(pnl_sorted)),
            pnl_sorted["cumulative_pnl"],
            color="cyan",
            linewidth=2,
            label="Cumul",
        )
        ax2.set_ylabel("PnL cumulé (€)")
        ax2.legend(loc="upper right")

    axes[1].axis("off")
    text = []
    if oos.get("oos_cve") is not None:
        text.append(f"CVE OOS: {oos['oos_cve']:.4f}")
    if hit.get("hit_ratio") is not None:
        text.append(f"Hit Ratio: {hit['hit_ratio']:.1%}")
    text.append(f"Trades: {telemetry['trades_count']} | PnL: {telemetry['pnl_count']}")
    axes[1].text(0.5, 0.5, "\n".join(text), fontsize=12, ha="center", va="center")

    plt.tight_layout()
    fig.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()


if __name__ == "__main__":
    main()
