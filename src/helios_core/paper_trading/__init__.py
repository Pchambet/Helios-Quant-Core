"""
Module Paper Trading — Exécution live-ready sur EPEX SPOT.
Orchestrateur (ordres J+1) et Réconciliateur (PnL réel) séparés (Front-Office vs Back-Office).
"""

from helios_core.paper_trading.live_data import LiveDataFetcher

__all__ = ["LiveDataFetcher"]
