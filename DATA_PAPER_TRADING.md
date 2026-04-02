# Donnees finalisees — Paper Trading (Helios-Quant-Core)

## Ce qui est deja disponible localement / dans le repo

Le paper trader genere et conserve ses artefacts dans `data/paper/` :

- `data/paper/trades_log.csv`
  - Un ordre par `target_date`
  - Colonnes principales : `target_date`, `status`, `forecast_cve`, `forecast_prices_array`, `p_ch_array`, `p_dis_array`, `soc_array`
- `data/paper/paper_pnl_log.csv`
  - Une reconciliation par `target_date`
  - Colonnes principales : `target_date`, `daily_pnl_eur`, `daily_cycles`, `actual_prices_array`
- `data/paper/last_meteo_forecast.parquet`
  - Cache meteo pour eviter une interruption si Open-Meteo est indisponible sur le run suivant

Les sorties “visuelles” sont exportees dans `reports/` :

- `reports/paper_tear_sheet.png`

## Comment exploiter ces donnees (3 etapes)

### 1) Regenerer/mettre a jour le tear sheet

Commande (il relit `trades_log.csv` et `paper_pnl_log.csv`) :

```bash
uv run python run_paper_tear_sheet.py --min-days 5
```

Le tear sheet calcule :
- **OOS error** : RMSE forecast vs prix reele (CVE) via `forecast_prices_array` vs `actual_prices_array`
- **Hit ratio zone morte** (seuil 34 €/MWh) via `p_ch_array` + `p_dis_array` et la dispersion reel `actual_prices_array`
- **Telemetrie** : gaps, integrity (pas d’ordres sans reconciliation, pas de recon sans ordre)
- **PnL cumule** : somme des `daily_pnl_eur`

### 2) Diagnostiquer pourquoi on “rate” des opportunites

Pratique rapide :
- filtrer `trades_log.csv` sur `status` (ex: `optimal_inaccurate`)
- identifier les jours ou le spread reel `max(actual_prices_array)-min(actual_prices_array)` est > 34
- comparer “miss” (aucun trade) vs “hit” (trade) pour comprendre si le MPC est trop timide (parametres) ou si la prevision est trop bruitée (qualite forecaster)

Le document `docs/TEAR_SHEET_INTERPRETATION.md` explique comment interpreter `misses`, `hit_ratio` et les thresholds.

### 3) Calibrer le controleur (offline, sans cron)

Objectif : ajuster des parametres MPC (ex: `alpha_slippage`) en relisant les forecasts deja logs.

Approche :
- re-simuler le MPC sur les `forecast_prices_array` (meme horizon 24h)
- tester plusieurs valeurs de parametres (seed fixee si applicable)
- garder la configuration qui optimise le compromis : **hit ratio + PnL + stabilite**

Un exemple de tuning existe dans `tune_epsilon.py` (pour la couche epsilon / robustesse). Pour la calibration “decision layer” via MPC deterministe, on peut suivre la meme logique.

## Note operationnelle : cron desactivé

Les workflows suivants ont ete modifies pour supprimer le declenchement quotidien :
- `.github/workflows/paper-orchestrator.yml` (suppression de `on.schedule`)
- `.github/workflows/paper-reconciler.yml` (suppression de `on.schedule`)

Ils restent utilisables via `workflow_dispatch` (declenchement manuel).

## Lancer “en vrai” (si ENTSOE_API_KEY est defini)

1) Orchestration (ordres J+1) :

```bash
uv run python run_paper_trader.py --target-date YYYY-MM-DD
```

2) Reconciliation (PnL reel) :

```bash
uv run python run_reconciler.py --target-date YYYY-MM-DD
```
