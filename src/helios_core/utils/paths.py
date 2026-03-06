"""
Centralized, CWD-invariant path management.
Paths are anchored to the project root (location of pyproject.toml).
"""

from pathlib import Path

# Ancrage spatial : racine du projet (parent de src/)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

DATA_DIR = _PROJECT_ROOT / "data"
REPORTS_DIR = _PROJECT_ROOT / "reports"


def ensure_data_dir() -> Path:
    """Crée data/ si absent. Retourne le chemin absolu."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR


def ensure_reports_dir() -> Path:
    """Crée reports/ si absent. Retourne le chemin absolu."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    return REPORTS_DIR
