# Audit Clinique : ScenarioGenerator

**Contexte :** Le DRO sous-performe significativement vs le MPC déterministe (7 902 € vs 25 695 € en crise). Hypothèse : la distribution $\hat{\mathbb{P}}_N$ contient des trajectoires pathologiques.

**Fichier audité :** `src/helios_core/stochastic/generator.py`

---

## 1. MARKET PHYSICS (Bornes EPEX)

### Constat

| Zone | Lignes | Comportement |
|------|--------|--------------|
| Bootstrap | 136-141 | Prix historiques → bornés par construction (si historique propre). |
| Tail type 0 | 151-152 | `rng.uniform(-100, -20)` → borné [-100, -20] ✓ |
| Tail type 1 | 154-156 | `np.clip(..., 50, 180)` → borné [50, 180] ✓ |
| Tail type 2 | 159-162 | **NON BORNÉ** : `base = rng.normal(mean_price, mean_price*0.2)` puis spike à `mean_price*5`. Aucun clip. En crise (mean≈400), spike≈2000 mais le reste peut être négatif ou >3000. |
| Noise | 164-168 | **NON BORNÉ** : `scenarios += rng.normal(0, volatility)`. Bruit gaussien non clipé. Peut sortir de [-500, 3000]. |
| Sortie | 171 | **Aucun clip final** sur l’ensemble des scénarios. |

### Verdict : VIOLATION

Aucun clip explicite aux limites EPEX (-500 à 3000 €/MWh). Les scénarios peuvent contenir des prix hors bornes physiques, surtout après tail type 2 et si `noise_multiplier > 0`. En prod actuelle (`noise_multiplier=0`), le risque vient principalement du tail type 2.

---

## 2. TEMPORAL STRUCTURE (Autocorrélation)

### Constat

| Zone | Lignes | Comportement |
|------|--------|--------------|
| Bootstrap | 139-141 | Fenêtres contiguës de 48h → **autocorrélation préservée** ✓ |
| Tail type 0 | 152 | `rng.uniform(-100, -20, horizon)` → **IID par heure**. Pas de structure temporelle. |
| Tail type 1 | 155-156 | `rng.normal(180, 20, horizon)` → **IID par heure**. |
| Tail type 2 | 160-162 | `rng.normal(mean_price, 0.2*mean_price, horizon)` → **IID**, puis 6h constantes. Le reste reste IID. |
| Noise | 165-168 | `rng.normal(0, volatility, (N, T))` → **IID par heure et par scénario**. Corrompt l’autocorrélation des scénarios bootstrap. |

### Verdict : VIOLATION

Le bruit est IID et détruit la structure temporelle. Les scénarios tail sont entièrement IID (pas de mean-reversion, pas de corrélation horaire). En cas de `noise > 0`, même les bonnes fenêtres bootstrap sont dégradées en trajectoires “en dents de scie” physiquement peu plausibles.

---

## 3. KNN FEATURE SCALING (Distance)

### Constat

| Zone | Lignes | Comportement |
|------|--------|--------------|
| Features | 80, 94-95 | `physical_cols = ["Load_Forecast", "Solar_Forecast", "Wind_Forecast", "Nuclear_Generation"]` |
| Scaling | 103-104 | `StandardScaler().fit_transform(X_hist)` puis `transform(X_forecast)` ✓ |
| Poids | 109-114 | `base_weights = [1.0, 0.5, 0.5, 1.0]` appliqués après standardisation. |

### Verdict : OK

Les features sont standardisées avant la distance euclidienne. Les poids après scaling sont cohérents. Pas de domination d’une variable par échelle (ex. GW vs °C).

---

## 4. NOISE CALIBRATION (Hétéroskédasticité)

### Constat

| Critère | Lignes | Comportement |
|---------|--------|--------------|
| Volatilité par heure | 165 | `volatility = np.std(scenarios, axis=0) * noise_multiplier` → dépend de la dispersion entre scénarios à chaque heure. |
| Horizon | — | Pas de facteur croissant avec l’horizon. Même traitement pour t+1 et t+48 alors que l’incertitude devrait augmenter. |
| Niveau de prix | — | Pas de lien explicite `σ ∝ price`. La dispersion reflète indirectement la variabilité, mais pas une règle du type “10% du prix”. |

### Verdict : VIOLATION PARTIELLE

- Pas de scaling par horizon.
- Pas d’hétéroskédasticité explicite en fonction du niveau de prix.
- En prod (`noise_multiplier=0`), ce bloc n’est pas exécuté, donc impact limité actuellement.

---

## Synthèse des vecteurs de dégradation

| Vecteur | Statut | Gravité |
|---------|--------|---------|
| 1. Bornes marché | VIOLATION | Haute |
| 2. Structure temporelle | VIOLATION | Haute |
| 3. Scaling KNN | OK | — |
| 4. Calibration du bruit | VIOLATION PARTIELLE | Moyenne (surtout si noise > 0) |

---

## Conclusion

Le `ScenarioGenerator` génère des trajectoires pathologiques via :

1. **Tail type 2** : non bornées et IID.
2. **Bruit IID** : destruction de l’autocorrélation si `noise > 0`.
3. **Absence de clip final** : des prix hors [-500, 3000] peuvent apparaître.

Le DRO optimise donc contre une distribution $\hat{\mathbb{P}}_N$ qui contient des scénarios irréalistes (dents de scie, prix hors bornes). La prime de robustesse excessive du DRO est en partie expliquée par cette représentation déformée du marché.
