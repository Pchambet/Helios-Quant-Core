# Architecture : PriceForecaster LightGBM

**Objectif :** Remplacer la chaîne SeasonalARMA + EMA par un modèle tabulaire LightGBM pour réduire l'erreur de prévision et lever le Plafond de Verre Informationnel.

---

## Note Stratégique (Minimalisme Structurel)

Ce forecaster n'est pas conçu pour prédire le prix exact (Oracle), mais pour capturer les corrélations physiques évidentes (Solaire → Baisse de prix) que la persistance ignore.

1. **Priorité aux Features :** On gagne sur les données d'entrée, pas sur la profondeur des arbres.
2. **Zéro Tuning :** On utilise les hyperparamètres par défaut de LightGBM (ou très proches). Si le modèle échoue, on regarde les données, pas le taux d'apprentissage.
3. **Robustesse d'abord :** Le succès se mesure à la réduction des "erreurs bêtes" dans le benchmark, pas au R².

---

## 1. Contexte actuel

| Composant | Implémentation | Limites |
|-----------|----------------|---------|
| D+1 (24h) | SeasonalARMAForecaster | Décomposition saisonnière + ARMA sur résidus. Pas de features physiques. |
| D+2 (24h) | EMA(3) par heure | Proxy naïf : moyenne mobile des 7 derniers jours à l'heure h. |
| Météo (48h) | Persistance | Répétition des 48h précédentes pour KNN du ScenarioGenerator. |

Le MPC surperforme car il prend des risques massifs sur une prévision médiocre. Le DRO se couvre car il sait que la prévision est médiocre. Améliorer le signal bénéficie aux deux.

---

## 2. Architecture cible

### 2.1. Module `LightGBMPriceForecaster`

- **Emplacement :** `src/helios_core/stochastic/price_forecaster.py`
- **Interface :** Compatible avec `SeasonalARMAForecaster` pour swap transparent dans le backtester.

```python
def forecast(
    self,
    past_data: pd.DataFrame,  # Prix + Load, Wind, Solar, Nuclear
    horizon: int = 24,
) -> np.ndarray:
    """Retourne (horizon,) array de prix prévus."""
```

### 2.2. Features (strictement causales)

| Feature | Description | Exemple |
|---------|-------------|---------|
| `hour` | Heure du jour [0-23] | Cyclique (sin/cos) |
| `day_of_week` | Jour [0-6] | Cyclique |
| `price_lag_1` | Prix à t-1 | MWh |
| `price_lag_24` | Prix à t-24 (même heure hier) | MWh |
| `price_lag_48` | Prix à t-48 | MWh |
| `price_roll_mean_24` | Moyenne glissante 24h (t-24 à t-1) | MWh |
| `load_lag_24` | Load à t-24 | MW (si colonne disponible) |
| `wind_lag_24` | Wind à t-24 | MW |
| `solar_lag_24` | Solar à t-24 | MW |
| `nuclear_lag_24` | Nuclear à t-24 | MW |

Tous les lags sont calculés à partir de données passées uniquement.

### 2.3. Stratégie de prévision multi-step

**Option A : Direct (1 modèle par horizon)** — Complexe, 24 modèles pour 24h.
**Option B : Récursive** — Prédire t+1, alimenter le lag pour t+2, etc. Propagation d'erreur.
**Option C : Multi-output** — Un seul modèle qui prédit (y_1, ..., y_24) en une fois.

**Recommandation :** Option B (récursive) pour simplicité. Chaque pas utilise les prédictions précédentes comme `price_lag_1` pour le pas suivant.

### 2.4. Rolling fit (causal)

- À chaque pas de temps `t` du backtest (tous les 24h), le forecaster est **refitté** sur `past_data = data.iloc[:t]`.
- Fenêtre d'entraînement : `lookback_days` (ex: 56 jours = 8 semaines).
- Pas de fuite de données futures : `fit(X_train)` où `X_train` n'utilise que des lignes avec index < t.

### 2.5. Intégration dans le Backtester

1. Remplacer `SeasonalARMAForecaster` par `LightGBMPriceForecaster` (ou garder les deux avec un flag).
2. Supprimer la logique EMA(3) pour D+2 : le LightGBM prédit directement 48h (horizon=48) ou deux appels de 24h.
3. `_build_causal_weather_forecast` : optionnellement, un `LightGBMWeatherForecaster` plus tard. Pour l'instant, garder la persistance météo (le gain principal vient du prix).

---

## 3. Dépendance

Ajouter `lightgbm` dans `pyproject.toml` :

```toml
dependencies = [
    ...
    "lightgbm>=4.0.0",
]
```

---

## 4. Contraintes de rigueur

1. **Aucun look-ahead** : Toutes les features sont construites à partir de `past_data.iloc[:t]`.
2. **Réentraînement causal** : Le modèle est fitté à chaque bloc de 24h (ou moins souvent pour perf, ex: tous les 7 jours si acceptable).
3. **Fallback** : Si LightGBM échoue ou données insuffisantes (< 168h), retomber sur `SeasonalARMAForecaster`.
4. **Reproductibilité** : `random_state` fixe dans LightGBM.

---

## 5. Prompt d'implémentation (Cursor)

Voir `PROMPT_LIGHTGBM_FORECASTER.md` pour le détail exécutable.
