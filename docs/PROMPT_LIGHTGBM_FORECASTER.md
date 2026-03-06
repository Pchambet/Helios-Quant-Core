# Prompt : Implémentation LightGBMPriceForecaster

---

## Contexte

Nous remplaçons la chaîne SeasonalARMA + EMA par un forecaster LightGBM tabulaire pour améliorer la prévision des prix jour-ahead. L'objectif est de réduire l'erreur de prévision afin que le DRO ait moins besoin de se couvrir et puisse capturer plus d'opportunités.

## Tâches

### 1. Dépendance

Dans `pyproject.toml`, ajouter `lightgbm>=4.0.0` dans la liste `dependencies`.

### 2. Nouveau module `src/helios_core/stochastic/price_forecaster.py`

Créer une classe `LightGBMPriceForecaster` avec :

- **`__init__(self, lookback_days: int = 56)`**
  - `lookback_days` : nombre de jours d'historique pour l'entraînement (défaut 56 = 8 semaines).

- **`forecast(self, past_data: pd.DataFrame, horizon: int = 48) -> np.ndarray`**
  - `past_data` : DataFrame avec `Price_EUR_MWh` et optionnellement `Load_Forecast`, `Wind_Forecast`, `Solar_Forecast`, `Nuclear_Generation`.
  - `horizon` : nombre d'heures à prévoir (48 pour D+1 et D+2).
  - Retourne un array de forme `(horizon,)` avec les prix prévus.

### 3. Construction des features (strictement causales)

Pour chaque heure `t` à prévoir, les features sont :

- `hour` = t % 24 (ou sin/cos pour cyclicité)
- `day_of_week` = jour de la semaine (0-6)
- `price_lag_1` = dernier prix connu (ou dernière prédiction si récursif)
- `price_lag_24` = prix à la même heure la veille
- `price_lag_48` = prix à la même heure il y a 2 jours
- `price_roll_mean_24` = moyenne des 24 dernières heures connues

Si les colonnes physiques existent dans `past_data` :

- `load_lag_24`, `wind_lag_24`, `solar_lag_24`, `nuclear_lag_24`

Pour la prévision **récursive** : à l’étape k (prédire l’heure k), utiliser la prédiction de l’heure k-1 comme `price_lag_1` si k > 0.

### 4. Logique d’entraînement et de prédiction

1. Extraire la fenêtre `history = past_data.tail(lookback_days * 24)`.
2. Construire la matrice X (features) et y (Price_EUR_MWh) pour chaque ligne de `history` à partir de laquelle les lags sont disponibles (minimum 48h de passé).
3. Entraîner un `lgb.LGBMRegressor` sur (X, y) avec `random_state=42`, paramètres par défaut ou légèrement régularisés (max_depth=5, n_estimators=100).
4. Pour la prédiction récursive :
   - Initialiser avec les derniers lags connus.
   - Pour h = 0..horizon-1 : construire la ligne de features, prédire, insérer la prédiction comme `price_lag_1` pour l’étape suivante.
5. Si `len(past_data) < 168` (7 jours) : fallback vers persistance (dernières 24h répétées) ou `SeasonalARMAForecaster` si disponible.

### 5. Intégration dans le Backtester

Dans `src/helios_core/simulate/backtester.py` :

- Remplacer `SeasonalARMAForecaster` par `LightGBMPriceForecaster` (ou ajouter un paramètre `forecaster_type`).
- Remplacer la logique actuelle :
  - `price_forecast_d1 = self.forecaster.forecast(past_prices, horizon=24)`
  - `proxy_forecast_d2 = ...` (EMA)
  - `full_forecast = np.concatenate(...)`
- Par un seul appel : `full_forecast = self.forecaster.forecast(past_data, horizon=48)` où `past_data = self.data.iloc[:t]`.

Le forecaster doit accepter un DataFrame (pas seulement un array de prix) pour exploiter les features physiques.

### 6. Fallback

Si `past_data` n’a pas assez de lignes (< 168), ou si LightGBM lève une exception : utiliser la persistance (répéter les dernières 24h sur 48h) et logger un warning.

### 7. Tests

- Ajouter `tests/stochastic/test_price_forecaster.py` :
  - Test que la sortie a la bonne forme `(horizon,)`.
  - Test que les prédictions sont bornées (ex: entre -500 et 3000).
  - Test fallback quand `len(past_data) < 168`.

## Contraintes

- Aucun look-ahead : les features ne doivent jamais utiliser de données futures.
- Utiliser uniquement `past_data` pour construire features et target.
- La sortie doit être un `np.ndarray` de dtype float.
