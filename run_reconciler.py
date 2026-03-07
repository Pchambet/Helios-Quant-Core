"""
CLI pour le Réconciliateur Paper Trading (Back-Office).

Usage:
  uv run python run_reconciler.py                  # Réconcilie demain (14h Paris)
  uv run python run_reconciler.py --dry-run       # Calcule sans écrire
  uv run python run_reconciler.py --target-date 2025-04-01  # Date cible explicite
"""
import argparse
import logging
import sys
from datetime import date, timedelta

from dotenv import load_dotenv

from helios_core.paper_trading.reconciler import PaperTraderReconciler

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Helios Reconciler — Calcule le PnL réel (ordres × prix EPEX) à 14h Paris"
    )
    parser.add_argument(
        "--target-date",
        type=str,
        default=None,
        help="Date à réconcilier (YYYY-MM-DD). Défaut: demain (D+1).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Calcule le PnL sans écrire dans paper_pnl_log.csv",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Utilise des prix synthétiques pour tester sans API.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()

    if args.target_date:
        target = date.fromisoformat(args.target_date)
    else:
        target = date.today() + timedelta(days=1)

    reconciler = PaperTraderReconciler()
    result = reconciler.run(
        target_date=target,
        dry_run=args.dry_run,
        mock=args.mock,
    )

    if result is None:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
