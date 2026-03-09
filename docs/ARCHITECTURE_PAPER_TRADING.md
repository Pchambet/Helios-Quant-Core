# Architecture : Module Paper Trading

**Objectif :** Passer de la simulation du passé à l'exécution sur le présent. S'interfacer avec la réalité asynchrone des marchés de gros européens.

**Principe :** Le backtest est mathématiquement clos et physiquement honnête. Le Paper Trading valide le pipeline complet (données live → inférence → ordre → réconciliation) sans risque financier.

---

## 1. Vue d'ensemble

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                         CRON (ex: 11h30 UTC quotidien)                           │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  ORCHESTRATEUR (paper_trader.py)                                                 │
│  • Charge données live (prix, météo, fondamentaux)                                │
│  • Inférence LightGBM + MPC                                                      │
│  • Écrit trades_log.csv (ordres J+1)                                             │
└─────────────────────────────────────────────────────────────────────────────────┘
                                        │
                                        ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  RÉCONCILIATEUR (reconciler.py) — CRON 14h00 UTC                                 │
│  • Récupère prix réels EPEX (fixing day-ahead)                                   │
│  • Croise avec ordres générés à 11h30                                            │
│  • Calcule PnL réel (frictions incluses)                                        │
│  • Met à jour paper_pnl_log.csv                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Structure des fichiers

```
Helios-Quant-Core/
├── src/helios_core/paper_trading/   # Phase 1 ✓
│   ├── __init__.py
│   ├── config.py            # Paramètres (timezone, chemins, Gate Closure)
│   ├── live_data.py         # LiveDataFetcher + LiveMeteoForecastLoader ✓
│   ├── orchestrator.py      # Pipeline principal (données → ordre) [Phase 2]
│   └── reconciler.py        # Croisement ordres / prix réels → PnL [Phase 3]
├── data/
│   └── paper/
│       ├── trades_log.csv       # Ordres générés (date, heure, p_ch, p_dis, soc)
│       ├── paper_pnl_log.csv    # PnL réconcilié (date, pnl_eur, cycles, ...)
│       └── live_cache/          # Cache des appels API (optionnel)
├── models/                    # Modèle LightGBM persisté (à créer)
│   └── price_forecaster_lgbm.pkl
├── run_paper_trader.py        # CLI : python run_paper_trader.py [--dry-run]
└── run_reconciler.py         # CLI : python run_reconciler.py [--date YYYY-MM-DD]
```

---

## 3. Responsabilités par composant

### 3.1. `live_data.py` — Pipeline de données live

| Méthode / Classe | Rôle | API cible |
|------------------|------|-----------|
| `LiveDataFetcher` | Agrège toutes les sources en un DataFrame horaire | — |
| `fetch_prices_past_N_days(N)` | Prix EPEX historiques (pour LightGBM lookback) | ENTSO-E Transparency API |
| `fetch_fundamentals_past_N_days(N)` | Load, Wind, Solar, Nuclear (pour features) | ENTSO-E Transparency API |
| `fetch_meteo_forecast(hours=48)` | Météo D+1 et D+2 (pour KNN / persistance) | Open-Meteo Forecast API |
| `fetch_fundamentals_forecast(hours=48)` | Prévisions Load/Wind/Solar (si dispo) | ENTSO-E ou fallback persistance |

**APIs cibles :**

| Source | Endpoint | Données | Clé |
|--------|----------|---------|-----|
| **Open-Meteo Forecast** | `https://api.open-meteo.com/v1/forecast` | Température, vent, rayonnement (16 jours) | Gratuit, pas de clé |
| **ENTSO-E Transparency** | `https://web-api.tp.entsoe.eu/api` | Prix day-ahead, Load, Wind, Solar, Nuclear | `ENTSOE_API_KEY` (déjà utilisé) |

**Note :** L'API ENTSO-E fournit les prix *day-ahead* après le fixing (~12h-13h). Pour l'orchestrateur à 11h30, on utilise les **derniers prix connus** (D-1 réalisés ou D-0 intraday) + prévisions LightGBM pour D+1. Le réconciliateur à 14h récupère les prix D+1 réels une fois publiés.

### 3.2. `orchestrator.py` — Le Cerveau en production

| Étape | Action |
|-------|--------|
| 1 | `LiveDataFetcher.fetch_prices_past_N_days(56)` + fundamentals |
| 2 | `LiveDataFetcher.fetch_meteo_forecast(48)` |
| 3 | Construire DataFrame `df` avec colonnes : `Price_EUR_MWh`, `Load_Forecast`, `Wind_Forecast`, `Solar_Forecast`, `Nuclear_Generation`, `Temperature_C`, `WindSpeed_kmh`, `SolarIrradiance_WM2` |
| 4 | Charger ou entraîner `LightGBMPriceForecaster` sur `df` (lookback 56 jours) |
| 5 | `forecaster.forecast(past_data=df, horizon=24)` → `(prices_24h, cve)` |
| 6 | Construire `weather_forecast` (météo D+1) pour compatibilité ScenarioGenerator |
| 7 | Instancier `BatteryMPC` avec `BatteryConfig` frictionné (LCOS 15, fees 2, λ=30) |
| 8 | `mpc.solve_deterministic(expected_prices=prices_24h)` → `(p_ch, p_dis, status)` |
| 9 | Écrire dans `trades_log.csv` : `date, hour_0..hour_23, p_ch_0..p_ch_23, p_dis_0..p_dis_23, soc_0..soc_24` |

**Agent cible :** MPC déterministe uniquement (le DRO est paralysé par les frictions en mode live).

### 3.3. `reconciler.py` — La Comptabilité réelle

| Étape | Action |
|-------|--------|
| 1 | Lire `trades_log.csv` pour la date cible (ex: D-1 si on réconcilie le lendemain) |
| 2 | `LiveDataFetcher.fetch_day_ahead_prices(date)` → prix réels EPEX pour cette date |
| 3 | Pour chaque heure h : `pnl_h = p_dis[h] * (price_real[h] - fee_sell) - p_ch[h] * (price_real[h] + fee_buy) - wear_h` |
| 4 | Agréger : `pnl_day = sum(pnl_h)`, `cycles_day = sum(p_ch + p_dis) / (2 * capacity)` |
| 5 | Append dans `paper_pnl_log.csv` : `date, pnl_eur, cycles, cumulative_pnl` |

**Frictions appliquées :** Identiques au backtester (fee_buy=2, fee_sell=2, marginal_cost=15). Pas de stress_penalty dans le PnL (régularisation uniquement).

### 3.4. `config.py` — Paramètres centralisés

```python
# paper_trading/config.py
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent  # paper_trading/ → project root
PAPER_DATA_DIR = PROJECT_ROOT / "data" / "paper"
TRADES_LOG_PATH = PAPER_DATA_DIR / "trades_log.csv"
PNL_LOG_PATH = PAPER_DATA_DIR / "paper_pnl_log.csv"

# Timezone marché EPEX (Europe/Paris = UTC+1/UTC+2)
MARKET_TZ = "Europe/Paris"

# Gate Closure EPEX SPOT Day-Ahead : 12h00 CET (Paris)
# Orchestrateur : 10h30 Paris = 09h30 UTC (hiver) / 08h30 UTC (été) — 1h30 avant clôture
# Réconciliateur : 14h00 Paris = 13h00 UTC (hiver) / 12h00 UTC (été) — prix publiés
ORCHESTRATOR_HOUR_UTC = 9   # 10h30 CET en hiver ; ajuster manuellement en été
ORCHESTRATOR_MINUTE_UTC = 30
RECONCILER_HOUR_UTC = 13    # 14h00 CET en hiver ; ajuster manuellement en été
RECONCILER_MINUTE_UTC = 0
```

---

## 4. Format des registres

### 4.1. `trades_log.csv`

| Colonne | Type | Description |
|---------|------|-------------|
| `generated_at` | ISO8601 | Timestamp de génération (10h30 Paris) |
| `target_date` | YYYY-MM-DD | Date des ordres (J+1) |
| `p_ch_00` .. `p_ch_23` | float | Puissance charge (MW) par heure |
| `p_dis_00` .. `p_dis_23` | float | Puissance décharge (MW) par heure |
| `soc_00` .. `soc_24` | float | État de charge (MWh) |
| `forecast_cve` | float | CVE du forecaster au moment de l'inférence |
| `solver_status` | str | Statut CVXPY (optimal, optimal_inaccurate, ...) |

### 4.2. `paper_pnl_log.csv`

| Colonne | Type | Description |
|---------|------|-------------|
| `date` | YYYY-MM-DD | Date réconciliée |
| `pnl_eur` | float | PnL net du jour (frictions incluses) |
| `cycles_efc` | float | Cycles équivalents complets |
| `cumulative_pnl_eur` | float | PnL cumulé depuis le début du paper trading |
| `reconciled_at` | ISO8601 | Timestamp de réconciliation |

---

## 5. Intégration avec l'existant

| Composant Helios | Réutilisation | Adaptation |
|------------------|---------------|------------|
| `LightGBMPriceForecaster` | Directe | Persister le modèle après fit (pickle/joblib) ou refit quotidien |
| `BatteryMPC` | Directe | Utiliser `BatteryConfig` frictionné |
| `PriceScaler` | Directe | Fit sur les 56 derniers jours de prix |
| `ScenarioGenerator` | Non utilisé | MPC déterministe suffit pour le paper trading |
| `RegimeDetector` | Non utilisé | Simplification volontaire |
| `entsoe_loader` | Partielle | Extraire la logique `_fetch_entsoe` pour appels ciblés |
| `meteo_loader` | Nouveau | Créer `LiveMeteoForecastLoader` (API forecast, pas archive) |

---

## 6. Cron (MacBook / Linux) — Gate Closure EPEX

**Reality Check :** La Gate Closure de l'enchère Day-Ahead EPEX SPOT est à **12h00 CET** (Paris). Tout ordre soumis après cette heure est rejeté. L'orchestrateur doit tourner **avant** la fermeture.

**Recommandé :** Utiliser `TZ=Europe/Paris` pour éviter le décalage CET/CEST. Voir `scripts/crontab.example` :

```cron
# scripts/crontab.example — Copier dans crontab -e
PROJECT_ROOT=/chemin/vers/Helios-Quant-Core
30 10 * * * cd $PROJECT_ROOT && TZ=Europe/Paris uv run python run_paper_trader.py
0 14 * * * cd $PROJECT_ROOT && TZ=Europe/Paris uv run python run_reconciler.py
```

**Alternative UTC figé** (déconseillé en été) :
```cron
30 9 * * * cd /chemin/vers/projet && uv run python run_paper_trader.py   # 10h30 Paris hiver, 11h30 été
0 13 * * * cd /chemin/vers/projet && uv run python run_reconciler.py    # 14h Paris hiver, 15h été
```

**Note :** Avec TZ=Europe/Paris, 10h30 et 14h00 restent corrects toute l'année (CET/CEST géré automatiquement).

### GitHub Actions (alternative au cron local)

Les workflows `.github/workflows/paper-orchestrator.yml` et `paper-reconciler.yml` exécutent le pipeline sans machine locale allumée.

1. **Secrets** : `Settings → Secrets and variables → Actions → New repository secret`
   - Nom : `ENTSOE_API_KEY`
   - Valeur : ta clé API ENTSO-E Transparency

2. **Heures** : 09:30 UTC (10h30 Paris hiver) et 13:00 UTC (14h Paris hiver). En été (CEST) décalage de ~1h.

3. **Persistance** : Les fichiers `data/paper/trades_log.csv` et `paper_pnl_log.csv` sont committés après chaque run.

4. **Premier run** : S'assurer que `data/paper/` existe et contient les CSV (ou les créer via un run local). Le `.gitignore` exclut `/data/` sauf ces deux fichiers.

---

## 7. Gestion des erreurs

| Situation | Comportement |
|-----------|--------------|
| API ENTSO-E indisponible | Fail-fast, log erreur, pas d'écriture dans trades_log |
| API Open-Meteo indisponible | Fallback persistance météo (dernières 48h connues) |
| LightGBM échoue (< 168h de données) | Fallback persistance prix (dernier jour répété) |
| Solveur CVXPY infeasible | Log warning, écrire ordres à zéro (pas de trade ce jour-là) |
| Pas d'ordre pour la date (orchestrateur non exécuté) | Réconciliateur : skip ou PnL = 0 avec flag `order_missing` |

---

## 8. Phases d'implémentation

| Phase | Livrable | Estimation |
|-------|----------|------------|
| **1. Live Data** | `live_data.py` + `LiveMeteoForecastLoader` | 1-2 jours |
| **2. Orchestrateur** | `orchestrator.py` + `run_paper_trader.py` | 1 jour |
| **3. Réconciliateur** | `reconciler.py` + `run_reconciler.py` | 0.5 jour |
| **4. Cron & Tests** | Scripts cron, test dry-run | 0.5 jour |

**Total :** ~3-4 jours de développement.

---

## 9. Alternatives / Extensions

| Option | Description |
|--------|-------------|
| **Données EPEX alternatives** | Si ENTSO-E latence : RTE Data Portal, EEX Transparency, ou fournisseur commercial (Montel, etc.) |
| **Multi-zone** | Étendre à DE, NL, BE (codes EIC différents) |
| **Intraday** | Ajouter un module pour le marché intraday (fixing 15min) — complexité supérieure |
| **Alerting** | Intégration Slack/Email si PnL journalier < seuil ou erreur API |

---

## Conclusion

Cette architecture préserve la séparation des responsabilités : l'orchestrateur produit des ordres, le réconciliateur mesure le résultat. Aucun flux de trésorerie réel ; chaque euro de `paper_pnl_log.csv` est un euro qui aurait été gagné ou perdu en conditions réelles, net des frictions.

Le modèle physique est clos. L'épreuve du feu peut commencer.
