"""
CLI unifiée pour les benchmarks Helios-Quant-Core.
Usage:
  python run_benchmark.py                  # défaut: crise août 2022
  python run_benchmark.py --mode normal    # mai 2023
  python run_benchmark.py --mode custom --start 2023-01-01 --end 2023-01-31
  python run_benchmark.py --mock          # données synthétiques
"""
import argparse
import logging

from helios_core.benchmark.runner import BenchmarkRunner

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Helios-Quant-Core: benchmark comparatif Naive / MPC déterministe / Robust DRO"
    )
    p.add_argument(
        "--mode",
        choices=["crisis", "normal", "custom"],
        default="crisis",
        help="crisis: août 2022 | normal: mai 2023 | custom: utilise --start/--end",
    )
    p.add_argument("--start", help="YYYY-MM-DD (requis si --mode custom)")
    p.add_argument("--end", help="YYYY-MM-DD (requis si --mode custom)")
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--mock", action="store_true", help="Données synthétiques si pas d'API/cache")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    preset = "custom" if args.mode == "custom" else args.mode
    runner = BenchmarkRunner(
        preset=preset,
        start_date=args.start,
        end_date=args.end,
        seed=args.seed,
        mock=args.mock,
    )
    runner.run()


if __name__ == "__main__":
    main()
