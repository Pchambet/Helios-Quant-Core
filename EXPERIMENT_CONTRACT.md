# Helios-Quant-Core Experiment Contract (Sprint 1 mois)

## 1) But du contrat

Ce document fige le minimum experimental pour eviter:
- les comparaisons injustes;
- les conclusions floues;
- les promesses non defendables.

Il est volontairement simple: il doit accelerer les decisions, pas ralentir la recherche.

## 2) Cible (scope fixe)

- Domaine: arbitrage microgrid batterie sur marche day-ahead.
- Marche: prix spot Europe (EPEX ou equivalent).
- Granularite: horaire.
- Variable cible: rendement arbitrage (ou PnL simule net de couts).
- Horizon: MPC receding-horizon, fenetre a definir (ex: 24h-72h).

## 3) Metriques officielles

### Metrique principale (north star)
- **Rendement ajuste du risque** ou **PnL OOS** sur backtest.
- Alternative: **worst-case cost** ou **tail risk** selon formulation DRO.

### Metriques secondaires
- Robustesse: ecart performance nominal vs worst-case dans ball.
- Reproducibilite: meme seed, meme donnees, meme resultat.

Regle: aucun claim externe sans metrique OOS documentee.

## 4) Baselines de reference (obligatoires)

Chaque experience est comparee aux niveaux suivants:

1. **Baseline naive**
   - politique simple (ex: charge pleine aux heures creuses, decharge aux heures pleines) ou equivalent.
2. **Baseline MPC deterministe**
   - MPC classique avec prix forecasts point (moyenne ou dernier prix connu).
3. **Baseline DRO (notre modele)**
   - MPC + formulation DRO Wasserstein avec parametres documentes.

Regle: un nouveau modele n'est valide que s'il bat au moins la baseline 2 sur metrique principale OOS.

## 5) Protocole d'evaluation (minimum acceptable)

- Split: walk-forward out-of-sample ou rolling backtest.
- Pas de fuite temporelle (look-ahead interdit).
- Meme fenetre temporelle pour tous les modeles compares.
- Meme pipeline de preprocessing et meme jeu de donnees prix.
- Rerun obligatoire avec seed fixee pour verifier reproductibilite.

## 6) Definition d'un gain "robuste"

Un gain est dit robuste si:
- metrique principale OOS amelioree vs baseline de reference;
- amelioration observee sur plusieurs periodes (pas une seule);
- pas de degradation majeure sur tail risk ou worst-case.

Regle de prudence sprint: prioriser stabilite du gain avant amplitude maximale.

## 7) Template de reporting obligatoire

Chaque test/model doit produire une fiche courte:

- Nom experience:
- Date:
- Donnees utilisees (marche, periode):
- Baselines comparees:
- Metrique principale OOS (par periode + global):
- Metriques secondaires:
- Delta vs baseline 2 (%):
- Hypothese testee:
- Resultat: passe / echoue / inconclusif:
- Prochaine action:

Sans cette fiche, l'experience n'existe pas pour la decision.

## 8) Claims autorises / interdits

### Autorises
- "Le modele X ameliore la metrique Y de Z% vs baseline W sur periode P."
- "Le gain est observe sur N periodes avec protocole walk-forward."

### Interdits
- "On bat le marche" sans cadre de reference explicite.
- "1% = millions" sans hypothese economique documentee.
- Toute promesse live/prod sans validation operationnelle.

## 9) Decision gates (sprint 1 mois)

### Gate A - validite technique
- pipeline executable de bout en bout;
- resultats reproductibles;
- pas de fuite temporelle detectee.

### Gate B - validite scientifique
- baseline claire;
- gain defendable;
- analyse d'ablation disponible.

### Gate C - validite de narration metier
- claim simple, verifiable, non exagere;
- limites explicites;
- valeur potentielle formulee en scenario, pas en certitude.

Si une gate echoue: stop ou pivot explicite.

## 10) Roles et cadence

- Owner A:
- Owner B:
- Revue hebdo (45 min): oui/non
- Date de debut contrat:
- Date de fin sprint:

Ce contrat peut evoluer apres le sprint, mais jamais retroactivement sur des resultats deja annonces.
