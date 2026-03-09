# Helios-Quant-Core ⚡

[![CI](https://github.com/Pchambet/Helios-Quant-Core/actions/workflows/ci.yml/badge.svg)](https://github.com/Pchambet/Helios-Quant-Core/actions/workflows/ci.yml)
[![Mypy](https://img.shields.io/badge/mypy-strict-blue)](/)
[![License](https://img.shields.io/badge/license-GPL--3.0-blue)](/)

**Piloter la physique du réseau, pas le bruit du marché.**

Helios-Quant-Core est un EMS (Energy Management System) pour batteries sur les marchés électriques européens. Il combine **MPC** (pilotage par optimisation), **DRO** (optimisation robuste sous incertitude) et **LCOS** (coût de dégradation) pour arbitrer le Day-Ahead (enchères du lendemain) en préservant l’actif physique.

---

## En bref : le pourquoi du comment

### Ce qui rend Helios unique

**1. On lit la physique, pas le ticket.** Le prix du MWh n'est qu'un symptôme. Ce qui compte : vent, soleil, nucléaire en ligne, demande. On cherche dans l'historique des journées « jumelles » (même signature physique) pour construire des scénarios crédibles. On ne parie pas sur le marché ; on lit le réseau.

**2. Le PnL est honnête.** Une batterie se dégrade à chaque cycle. Le LCOS (Levelized Cost of Storage = coût de dégradation sur la durée de vie) est intégré dans chaque décision. Si le spread net ne couvre pas ce coût, on ne trade pas. Pas de profit apparent en détruisant l'actif.

**3. On se prépare au pire.** La DRO (Distributionally Robust Optimization = optimisation robuste sous incertitude) ne parie pas sur « la moyenne ». Elle se prépare au pire scénario plausible. En régime calme, on arbitre ; en tension, on réduit l'exposition et on attend les vrais pics. Le bouclier s'adapte à la confiance qu'on a dans la prévision (CVE = Coefficient de Variation de l'Erreur, une mesure d'erreur du modèle).

**4. Un seul code, plusieurs échelles.** Une batterie, une pompe à chaleur, un data center IA : ce sont des « buffers » de flux. Même logique physique. La vision va du Micro (une cellule) au Macro (maillage Europe, flux transfrontaliers).

### Pourquoi c'est le bon moment

- **Juin 2025** : le marché européen passe de 24 à 96 créneaux par jour (granularité 15 min). La plupart des modèles existants ne sont pas prêts. Helios peut capter cette volatilité là où d'autres subiront des erreurs massives.

- **Le FCR (régulation de fréquence)** s'effondre : trop de batteries sur ce segment, les prix chutent. La valeur se déplace vers l'arbitrage et la gestion d'actif — le terrain d'Helios.

- **Données et outils sont mûrs** : ENTSO-E (plateforme européenne des données du réseau électrique), Open-Meteo (météo gratuite), Copernicus (imagerie continentale). Les briques existent ; il faut les assembler.

- **Fenêtre courte** : les acteurs établis (Tesla, agrégateurs) ont le capital mais pas toujours la finesse physique. Un outil SaaS pour ceux qui *ont* l'actif peut se glisser avant que le marché ne se verrouille.

---

## Le récit en 5 minutes

*Comme si je te racontais le projet face à face.*

**Ce que je ne suis pas.** Je ne fais pas du trading. Je ne veux pas être trader. Et je sais que je serais perdant : premièrement, je n'ai pas accès au marché moi-même — ni l'argent ni les connexions pour entrer sur ce marché. Donc le trading, je m'en fous, c'est hors sujet. Deuxièmement, les traders déjà installés prédisent le prix du MWh infiniment mieux que moi. Ce n'est pas la bataille que je vise.

**Ce que j'apporte.** La différence, c'est l'Oracle Physique. Pas « deviner le prix demain » — mais lire la *physique* du réseau : vent, soleil, nucléaire, demande. Ensuite, une batterie n'est pas un ticker. Elle se dégrade. Les traders optimisent le PnL brut ; moi j'intègre le LCOS. Chaque cycle a un coût chimique. Si le spread net est sous ce coût, je ne trade pas. L'outil que je construis s'adresse à ceux qui *ont* l'actif : propriétaires de batterie, agrégateurs, TSO (gestionnaires de réseau). Eux ont besoin d'un cerveau qui lit la physique et qui préserve l'actif — pas d'un spéculateur de plus.

**Le problème.** Les algos existants prédisent le prix avec du ML. Ils marchent bien… jusqu'au jour où le marché part en vrille. Août 2022 : gaz russe, nucléaire au tapis, prix à 1000 €/MWh. Ces modèles se plantent. Et pour gratter quelques euros, ils font tourner la batterie en roue libre. Chaque cycle use la chimie. Tu détruis un actif de plusieurs millions pour des marges de centimes.

**L'intuition.** Le prix n'est pas le signal. Le prix est le *symptôme*. Ce qui compte, c'est la réalité physique. Si tu lis ça, tu peux trouver dans l'historique des journées « jumelles » — même signature physique — et en déduire des scénarios crédibles. Tu lis le réseau.

**Les maths.** Je fais de la DRO : Distributionally Robust Optimization. Je me prépare au *pire cas* dans un ensemble de distributions plausibles. En régime calme, le bouclier se baisse. En tension, il se lève. Et j'intègre le LCOS à chaque décision. Le PnL est honnête.

**L'exécution.** J'ai construit ça couche par couche. D'abord le Micro : une batterie, un point, MPC (pilotage par optimisation) + LCOS + paper trading live. LightGBM (modèle de prévision) pour la prévision, ENTSO-E (données réseau européen) et Open-Meteo (météo) pour les données. Ça tourne. Le tear sheet (rapport de performance) valide le CVE (erreur du modèle), le Hit Ratio (bonnes décisions vs opportunités manquées). Ensuite viendra le Méso : les analogues KNN (situations historiques similaires), l'explicabilité (« je décharge parce que ça ressemble au 12 janvier 2024 »). Puis le Macro : maillage Europe, flux transfrontaliers.

---

## Le paradigme : l'« Oracle Physique »

Au lieu de prédire le prix exact, Helios s’appuie sur la **réalité physique du réseau** :

1. **Les yeux** — Données ENTSO-E (charge, vent, soleil, nucléaire) + météo (Open-Meteo). Analogues historiques pour construire des scénarios crédibles.

2. **Le cerveau** — DRO (optimisation robuste) avec bouclier adaptatif. En régime calme : arbitrage agressif. En tension : repli, attente des pics.

3. **Le corps** — LCOS (coût de dégradation) intégré. Aucun cycle si le profit net est inférieur au coût de dégradation.

---

## État actuel : Micro validé

| Niveau | Statut | Contenu |
|--------|--------|---------|
| **Micro** | ✅ | MPC + LCOS + Paper Trading live (LightGBM, Double Bouclier = bouclier adaptatif) |
| **Méso** | 🔜 | Analogues KNN (situations historiques similaires), explicabilité |
| **Macro** | 📋 | Maillage Europe, flux transfrontaliers |

Le paper trading tourne en continu via **GitHub Actions** (orchestrateur 10h30 Paris, réconciliateur 14h Paris).

---

## Quick Start

```bash
git clone https://github.com/Pchambet/Helios-Quant-Core
cd Helios-Quant-Core

# Installation (uv recommandé)
uv sync

# Clé API ENTSO-E (requise pour le live)
# Copier .env.example → .env et remplir ENTSOE_API_KEY
```

### Backtest

```bash
uv run python run_benchmark.py                    # Crise août 2022 (défaut)
uv run python run_normal_benchmark.py           # Mai 2023 (peacetime)
uv run python run_benchmark.py --mode custom --start 2023-01-01 --end 2023-01-31
```

### Paper Trading

```bash
uv run python run_paper_trader.py                # Génère ordre J+1
uv run python run_reconciler.py                 # Calcule PnL réel
uv run python run_paper_health_check.py         # Santé du pipeline
uv run python run_paper_tear_sheet.py            # Rapport post-mortem (CVE, Hit Ratio)
```

### Sensibilité & Audit

```bash
uv run python run_gamma_sensitivity.py           # Impact du CVE sur ε DRO
uv run python run_audit_meteo.py                # Audit météo
```

---

## Structure

```
Helios-Quant-Core/
├── src/helios_core/
│   ├── assets/           # Modèle batterie (LCOS, contraintes)
│   ├── optimization/     # MPC / DRO (CVXPY)
│   ├── stochastic/       # Forecaster LightGBM, ScenarioGenerator, Risk Manager
│   ├── paper_trading/    # Orchestrateur, Réconciliateur, Live Data
│   ├── simulate/         # Backtester, métriques
│   └── data/             # Loaders ENTSO-E, météo
├── data/paper/           # trades_log.csv, paper_pnl_log.csv
├── docs/                 # Architecture, audits, vision
└── .github/workflows/    # CI, Paper Orchestrator, Paper Reconciler
```

---

## Documentation

| Document | Contenu |
|----------|---------|
| [THEORY.md](THEORY.md) | Fondements mathématiques (DRO, Wasserstein, dualité) |
| [docs/ARCHITECTURE_PAPER_TRADING.md](docs/ARCHITECTURE_PAPER_TRADING.md) | Pipeline paper trading, cron, GitHub Actions |
| [docs/TEAR_SHEET_INTERPRETATION.md](docs/TEAR_SHEET_INTERPRETATION.md) | Lecture CVE, Hit Ratio, télémétrie |
| [docs/vision/STRATEGIC_ORCHESTRATION_MANIFESTO.md](docs/vision/STRATEGIC_ORCHESTRATION_MANIFESTO.md) | Vision Micro → Méso → Macro |
| [docs/AUDIT_HELIOS_QUANT_CORE.md](docs/AUDIT_HELIOS_QUANT_CORE.md) | Audit technique complet |

---

## Résultats backtest

*PnL net (LCOS inclus) — runs actuels, batterie 1 MWh, config par défaut. Walk-forward 24h, pas de look-ahead bias.*

| Régime | Contexte | Naive | MPC | DRO (robuste) |
|--------|----------|-------|-----|---------------|
| **Crise** | Août 2022, gaz russe, nucléaire FR | 19 495 € | **33 314 €** | 16 582 € |
| **Peacetime** | Mai 2023, prix < 160 € | 5 405 € | **6 538 €** | 4 822 € |

### Constat

MPC performe le mieux sur ces périodes. Le DRO, orienté robustesse (préparation au pire cas), est plus conservateur et sous-performe en PnL — il réduit l'exposition en période incertaine, au prix d'opportunités manquées.

### Explications

- **MPC déterministe** : fait confiance à la prévision (LightGBM ou heuristique). Quand la prévision est raisonnablement bonne, il exploite chaque opportunité. Dans un backtest, les prix sont connus ex-post — on mesure la capacité à « bien jouer » la courbe prévue.

- **DRO Wasserstein** : minimise la perte dans le *pire cas* sur une boule de distributions (rayon ε). Il hedge contre un déplacement adverse de la distribution. En replay historique, ce pire cas ne se réalise pas ; l’hedge coûte donc des opportunités sans compensation observable en PnL. La valeur du DRO est théoriquement **hors échantillon** (distribution shift, crise non vue) et sur des métriques de risque (drawdown, RoDC, worst-case), pas sur le PnL moyen.

- **ε dynamique** : le `DynamicEpsilonManager` recalcule ε à chaque pas : ε_base ∝ 1/√N (scénarios), × (1 + β×entropie régime) × (1 + γ×CVE). Si CVE ou l’entropie régime sont élevés, ε monte → DRO devient plus conservateur. Les bornes actuelles (eps_min=0.02, eps_max=0.30) peuvent être sous/sur-calibrées selon le régime.

### Pistes d’investigation

1. **Métriques complémentaires** : RoDC (rendement par cycle), EFC (équivalent cycles complets), drawdown max, CVaR. Un DRO « perdant » en PnL peut être gagnant en RoDC ou en protection du downside.
2. **Tuning ε** : grid search ε fixe vs ε dynamique ; comparer avec `run_gamma_sensitivity.py` (impact du CVE sur ε). Un ancien calibrage (voir `docs/strategy/03_investment_memorandum.md`) suggérait ε≈0.5 optimal sur une config différente — à réévaluer.
3. **Régimes cibles** : tester des phases de transition (sortie de crise, entrée en tension) où la prévision se dégrade. C’est là que le hedge DRO devrait théoriquement briller.
4. **Scénarios** : le `ScenarioGenerator` (KNN + régime) alimente le DRO. Si les scénarios sont trop étroits ou trop bruités, ε ne compense pas — enrichir ou filtrer les analogues pourrait changer la donne.
5. **Comparaison ε=0** : forcer ε=0 dans le DRO pour vérifier qu’on retrouve un comportement proche du MPC (sanity check du pipeline).

---

## Licence

GPL-3.0. Voir [LICENSE](LICENSE).
