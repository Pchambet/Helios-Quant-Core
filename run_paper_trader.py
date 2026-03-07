"""
CLI pour l'Orchestrateur Paper Trading.

Usage:
  uv run python run_paper_trader.py                  # Ordre pour demain (écrit trades_log)
  uv run python run_paper_trader.py --dry-run        # Pipeline sans écriture
  uv run python run_paper_trader.py --target-date 2025-03-10  # Date cible explicite

Requis: ENTSOE_API_KEY dans .env ou l'environnement.
"""
import argparse
import logging
from datetime import date, timedelta

from dotenv import load_dotenv

from helios_core.paper_trading.orchestrator import PaperTraderOrchestrator

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Helios Paper Trader — Génère les ordres J+1 avant la Gate Closure 12h00 CET"
    )
    parser.add_argument(
        "--target-date",
        type=str,
        default=None,
        help="Date cible (YYYY-MM-DD). Défaut: demain.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Exécute le pipeline sans écrire dans trades_log.csv",
    )
    parser.add_argument(
        "--mock",
        action="store_true",
        help="Utilise des données synthétiques (HistoricalCrisisLoader mock) pour tester sans API.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    if args.target_date:
        target = date.fromisoformat(args.target_date)
    else:
        target = date.today() + timedelta(days=1)

    orchestrator = PaperTraderOrchestrator()
    orchestrator.run(
        target_date=target,
        dry_run=args.dry_run,
        mock=args.mock,
    )


if __name__ == "__main__":
    main()
