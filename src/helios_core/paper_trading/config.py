"""
Configuration centralisée du module Paper Trading.
Gate Closure EPEX SPOT Day-Ahead : 12h00 CET (Paris).
"""

from pathlib import Path

# Ancrage : helios_core/paper_trading/config.py → projet racine
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

PAPER_DATA_DIR = _PROJECT_ROOT / "data" / "paper"
TRADES_LOG_PATH = PAPER_DATA_DIR / "trades_log.csv"
PNL_LOG_PATH = PAPER_DATA_DIR / "paper_pnl_log.csv"

# Timezone marché EPEX
MARKET_TZ = "Europe/Paris"

# Gate Closure : 12h00 CET — Orchestrateur doit tourner avant
# 10h30 Paris = 09h30 UTC (hiver) / 08h30 UTC (été)
# Cron conservateur : 09h30 UTC (10h30 Paris hiver, 11h30 Paris été)
ORCHESTRATOR_HOUR_UTC = 9
ORCHESTRATOR_MINUTE_UTC = 30

# Réconciliateur : 14h00 Paris — prix day-ahead publiés sur ENTSO-E
# 14h00 Paris = 13h00 UTC (hiver) / 12h00 UTC (été)
RECONCILER_HOUR_UTC = 13
RECONCILER_MINUTE_UTC = 0


def ensure_paper_data_dir() -> Path:
    """Crée data/paper/ si absent."""
    PAPER_DATA_DIR.mkdir(parents=True, exist_ok=True)
    return PAPER_DATA_DIR
