#!/bin/bash
# Helios Paper Trading — Pré-vol avant "Silence Radio"
# Lance ce script avant de partir. Il vérifie tout ce qui peut l'être.

set -e
cd "$(dirname "$0")"
PROJECT_ROOT="$(pwd)"

echo "=============================================="
echo " Helios Paper Trading — Pré-vol"
echo "=============================================="
echo ""

# 1. Cron installé ?
echo "[1] Cron"
if crontab -l 2>/dev/null | grep -q "run_paper_trader"; then
    echo "  ✓ Cron installé (orchestrateur + réconciliateur)"
    crontab -l | grep -E "run_paper|run_reconciler" || true
else
    echo "  ✗ Cron NON installé"
    echo ""
    echo "  → Installe-le maintenant :"
    echo "    crontab $PROJECT_ROOT/scripts/crontab.example"
    echo ""
fi

# 2. Health check
echo "[2] Santé des logs"
uv run python run_paper_health_check.py
HC=$?
echo ""

# 3. .env / ENTSOE_API_KEY
echo "[3] Configuration"
if [ -f .env ] && grep -q "ENTSOE_API_KEY" .env; then
    echo "  ✓ .env présent avec ENTSOE_API_KEY"
else
    echo "  ⚠ Vérifie que ENTSOE_API_KEY est défini (.env ou export)"
fi
echo ""

# 4. Rappel final
echo "=============================================="
echo " Avant de partir :"
echo "  • Branche le Mac sur secteur"
echo "  • Luminosité à zéro"
echo "  • Lance : caffeinate -d"
echo "  • Ne ferme pas le capot"
echo "=============================================="
