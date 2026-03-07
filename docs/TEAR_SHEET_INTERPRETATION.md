# Guide d'interprétation — Tear Sheet Paper Trading

**Usage :** Consulter ce document après avoir lancé `uv run python run_paper_tear_sheet.py` (idéalement mercredi ou jeudi, après 3–5 jours de données).

---

## 1. Erreur Out-of-Sample (CVE réel)

**Ce que c'est :** Le LightGBM prévoit les prix à 10h30 (D-1). À 14h, on compare avec les prix réels publiés par ENTSO-E. Le CVE = RMSE / mean(|actual|) mesure l’erreur relative.

| CVE OOS | Interprétation | Action |
|---------|----------------|--------|
| **< 0,15** | Modèle aligné avec le backtest | ✅ Rien à faire |
| **0,15 – 0,25** | Légère dérive, acceptable | Surveiller les prochains runs |
| **0,25 – 0,35** | Dérive notable | Vérifier features, météo, régime de marché |
| **> 0,35** | Dérive forte | Recalibrer le modèle ou enrichir les features |

**RMSE (€/MWh) :** Sur EPEX France, les prix typiques sont 20–150 €/MWh. Un RMSE < 15 €/MWh est correct ; > 25 €/MWh suggère un problème.

**⚠️ Avec 3–5 jours :** Le CVE peut être instable. Un seul jour extrême (crise, pic) peut le faire monter. Attendre 7–10 jours pour une lecture plus fiable.

---

## 2. Hit Ratio Zone Morte (34 €/MWh)

**Ce que c'est :** L’agent ne trade que si le spread prévu dépasse 34 €/MWh (LCOS + fees). On compare sa décision (trader ou rester figé) au spread réel observé.

| Métrique | Signification |
|----------|---------------|
| **Hits** | A tradé ET spread réel > 34 → bonne décision |
| **Misses** | N’a pas tradé ET spread réel > 34 → opportunité manquée |
| **Correct pass** | N’a pas tradé ET spread réel ≤ 34 → bonne abstention |
| **Hit Ratio** | hits / (hits + misses) — précision quand il décide de bouger |

| Hit Ratio | Interprétation | Action |
|-----------|-----------------|--------|
| **> 60 %** | Bonne anticipation des spreads | ✅ OK |
| **40 – 60 %** | Moyen, coût d’opportunité modéré | Surveiller |
| **< 40 %** | Beaucoup de faux positifs ou faux négatifs | Revoir seuil 34 ou modèle |

**Opportunités manquées (Misses) :** Chaque miss = un jour où le marché offrait un spread > 34 mais l’agent est resté figé. C’est le coût d’opportunité. Avec peu de jours, 1–2 misses peuvent être normaux.

**⚠️ Avec 3–5 jours :** Si hits + misses = 0, le Hit Ratio est vide (aucun jour avec spread > 34). C’est possible en période calme. Ne pas conclure trop vite.

---

## 3. Télémétrie d’exécution

| Indicateur | OK | À investiguer |
|------------|-----|---------------|
| **Ordres sans réconciliation** | 0 | > 0 : Cron 14h a peut‑être sauté ou API ENTSO-E down |
| **Réconciliations sans ordre** | 0 | > 0 : Anomalie (ordre manquant ou doublon) |
| **NaN dans les logs** | Aucun | Présence de NaN : échec API ou parsing |

**Gaps (jours manquants) :** Si le Cron a tourné tous les jours, `expected_days ≈ observed_days`. Un écart > 1 suggère des runs manqués.

---

## 4. PnL cumulé

Le PnL seul ne suffit pas à juger. Un PnL positif avec un CVE élevé peut être de la chance ; un PnL négatif avec un CVE bas peut être un mauvais timing. Utiliser le PnL en complément du CVE et du Hit Ratio.

---

## Grille de lecture rapide (premier tear sheet)

| Situation | Verdict |
|-----------|---------|
| CVE < 0,25, Hit Ratio > 50 %, télémétrie propre | **Vert** — Système cohérent avec le backtest |
| CVE 0,25–0,35 ou Hit Ratio 40–50 % | **Orange** — Surveiller, pas d’action immédiate |
| CVE > 0,35 ou Hit Ratio < 40 % ou télémétrie dégradée | **Rouge** — Investiguer (Cron, API, modèle) |

---

## Commande

```bash
uv run python run_paper_tear_sheet.py
```

Le rapport visuel est exporté dans `reports/paper_tear_sheet.png`.
