#!/usr/bin/env python3
"""
Santé du Système Paper Trading — Vérification rapide des logs.

Usage:
  uv run python run_paper_health_check.py

Vérifie :
  - Présence et intégrité de trades_log.csv et paper_pnl_log.csv
  - Ordres sans réconciliation (orchestrateur a tourné, réconciliateur non)
  - Réconciliations orphelines (ordre manquant)
  - Structure des données (colonnes, JSON valides)
  - Derniers timestamps (Cron s'est-il réveillé ?)
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, cast

# Ancrage projet (avant import helios_core)
_PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_PROJECT_ROOT))

from helios_core.paper_trading.config import PNL_LOG_PATH, TRADES_LOG_PATH  # noqa: E402


def _load_trades() -> list[dict[str, Any]] | None:
    """Charge trades_log ou None si absent/invalide."""
    if not TRADES_LOG_PATH.exists():
        return None
    try:
        import pandas as pd

        df = pd.read_csv(TRADES_LOG_PATH)
        if "target_date" not in df.columns:
            return None
        return cast(list[dict[str, Any]], df.to_dict("records"))
    except Exception:
        return None


def _load_pnl() -> list[dict[str, Any]] | None:
    """Charge paper_pnl_log ou None si absent/invalide."""
    if not PNL_LOG_PATH.exists():
        return None
    try:
        import pandas as pd

        df = pd.read_csv(PNL_LOG_PATH)
        if "target_date" not in df.columns:
            return None
        return cast(list[dict[str, Any]], df.to_dict("records"))
    except Exception:
        return None


def _validate_json_array(val: Any, name: str) -> bool:
    """Vérifie qu'une valeur est un JSON array de 24 floats."""
    if val is None or (isinstance(val, float) and str(val) == "nan"):
        return False
    try:
        arr = json.loads(val) if isinstance(val, str) else val
        return isinstance(arr, list) and len(arr) == 24
    except (json.JSONDecodeError, TypeError):
        return False


def run_health_check() -> int:
    """Retourne 0 si OK, 1 si attention, 2 si erreur critique."""
    trades = _load_trades()
    pnl = _load_pnl()

    issues: list[str] = []
    warnings: list[str] = []

    # 1. Fichiers existants
    if trades is None:
        if not TRADES_LOG_PATH.exists():
            issues.append(f"trades_log absent : {TRADES_LOG_PATH}")
        else:
            issues.append("trades_log illisible ou invalide")
    else:
        trades_dates = sorted(set(str(r.get("target_date", "")) for r in trades if r.get("target_date")))
        last_trade = trades[-1] if trades else {}
        last_ts = last_trade.get("generated_at", "?")
        if len(trades_dates) > 0:
            print(f"  ✓ trades_log : {len(trades)} ordre(s), {len(trades_dates)} date(s) cible(s)")
            print(f"    Dernier : {trades_dates[-1]} (généré {last_ts})")

    if pnl is None:
        if not PNL_LOG_PATH.exists():
            warnings.append(f"paper_pnl_log absent : {PNL_LOG_PATH}")
        else:
            issues.append("paper_pnl_log illisible ou invalide")
    else:
        pnl_dates = sorted(set(str(r.get("target_date", "")) for r in pnl if r.get("target_date")))
        last_pnl = pnl[-1] if pnl else {}
        last_ts = last_pnl.get("reconciled_at", "?")
        if len(pnl_dates) > 0:
            print(f"  ✓ paper_pnl_log : {len(pnl)} réconciliation(s), {len(pnl_dates)} date(s)")
            print(f"    Dernier : {pnl_dates[-1]} (réconcilié {last_ts})")

    # 2. Cohérence ordres / réconciliations
    if trades is not None and pnl is not None:
        trades_set = set(str(r.get("target_date", "")) for r in trades if r.get("target_date"))
        pnl_set = set(str(r.get("target_date", "")) for r in pnl if r.get("target_date"))

        missing_recon = trades_set - pnl_set
        orphan_recon = pnl_set - trades_set

        if missing_recon:
            warnings.append(f"Ordres sans réconciliation : {sorted(missing_recon)}")
        if orphan_recon:
            warnings.append(f"Réconciliations sans ordre : {sorted(orphan_recon)}")

    # 3. Structure (dernier ordre)
    if trades:
        last = trades[-1]
        for col in ["p_ch_array", "p_dis_array"]:
            if not _validate_json_array(last.get(col), col):
                warnings.append(f"Structure : {col} invalide ou != 24h (dernier ordre)")

    # 4. Fraîcheur des runs (Cron s'est-il réveillé ?)
    try:
        now = datetime.now(timezone.utc)
        if trades:
            last_ts = trades[-1].get("generated_at", "")
            if last_ts and last_ts != "?":
                try:
                    dt = datetime.fromisoformat(str(last_ts).replace("Z", "+00:00"))
                    age_h = (now - dt).total_seconds() / 3600
                    if age_h > 48:
                        warnings.append(f"Dernier ordre il y a {int(age_h)}h — Cron 10h30 a-t-il tourné ?")
                except (ValueError, TypeError):
                    pass
        if pnl:
            last_ts = pnl[-1].get("reconciled_at", "")
            if last_ts and last_ts != "?":
                try:
                    dt = datetime.fromisoformat(str(last_ts).replace("Z", "+00:00"))
                    age_h = (now - dt).total_seconds() / 3600
                    if age_h > 48:
                        warnings.append(f"Dernière réconciliation il y a {int(age_h)}h — Cron 14h a-t-il tourné ?")
                except (ValueError, TypeError):
                    pass
    except ImportError:
        pass

    # Résumé
    print()
    if issues:
        print("  ⛔ ERREURS :")
        for m in issues:
            print(f"    - {m}")
    if warnings:
        print("  ⚠️  ATTENTIONS :")
        for m in warnings:
            print(f"    - {m}")

    if issues:
        print("\n→ Vérifier les Cron, ENTSOE_API_KEY, et les logs d'erreur.")
        return 2
    if warnings:
        print("\n→ Système opérationnel avec écarts mineurs.")
        return 1
    print("\n→ Santé OK. Les logs sont cohérents.")
    return 0


def main() -> int:
    print("Helios Paper Trading — Santé du Système")
    print("=" * 50)
    return run_health_check()


if __name__ == "__main__":
    sys.exit(main())
