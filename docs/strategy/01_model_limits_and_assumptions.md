# Helios-Quant-Core: Model Limits & Industrial Assumptions

Un algorithme robuste en laboratoire est dangereux en production s'il ignore ses propres angles morts. Ce document référence les hypothèses (Assumptions) prises par l'optimiseur mathématique et les limites strictes (Limits) du modèle qui doivent être connues par les opérateurs de marché et les gestionnaires des risques.

## 1. Liquidity & Market Impact (Price-Taker vs Price-Maker)
**Assumption:** Le modèle agit actuellement en tant que pur *Price-Taker*. Il présume qu'il peut injecter ou soutirer la capacité maximale de l'actif (ex: 5 MW) au prix SPOT exact, sans subir aucun slippage (glissement de prix).
**Industrial Limit:** Dans la réalité de l'EPEX SPOT, le carnet d'ordres n'est pas infiniment profond. Si un actif massif (ex: 100 MW) s'active brusquement, il déplace le prix d'équilibre contre lui-même.
**Future Roadmap:** Implémenter une fonction de pénalité de liquidité quadratique ou linéaire (Market Impact) dans la fonction objectif du `CVXPY`.

## 2. Dynamic Volatility & The Constant Epsilon ($\epsilon$)
**Assumption:** Actuellement, le rayon d'ambiguïté de Wasserstein $\epsilon$ est fourni statiquement lors de l'appel à `solve_robust()`.
**Industrial Limit:** Le marché de l'électricité connaît des changements de régimes colossaux (Été stable vs Hiver sous tension, chocs géopolitiques). Un $\epsilon$ fixe force l'algorithme à être soit trop agressif en hiver, soit trop terrorisé (et donc inactif) en été.
**Future Roadmap:** Paramétriser $\epsilon$ de manière dynamique via un modèle GARCH ou HMM (Hidden Markov Model) filtrant la variance historique court terme.

## 3. LCOS (Levelized Cost of Storage) & Non-Linear Degradation
**Assumption:** Le programme impose une pénalité de cyclage minimaliste (`cyclic_penalty = 1e-4`) simplement pour briser les symétries algorithmiques (éviter les ping-pongs de charge/décharge à T et T+1).
**Industrial Limit:** Une cellule Lithium-Ion subit une dégradation exponentielle lors des cycles de décharge profonds (0-10% SoC ou 90-100% SoC). Le modèle actuel poursuivra un gain de 50€ même si cela inflige 100€ de "Mort Chimique" à la batterie.
**Future Roadmap:** Intégrer une courbe de coût marginal de dégradation non-linéaire (ou affinée par morceaux pour conserver la convexité LP) dans la fonction `wear`.

## 4. Perfect Foresight Illusion
**Assumption:** Le `Expected_Prices` array représente l'espérance mathématique des prix du jour J+1.
**Industrial Limit:** Toute erreur magistrale du modèle stochastique sous-jacent (qui génère ces scénarios) condamnera l'optimisation, peu importe à quel point la dualité est robuste. Le DRO protège de la variance sur la distribution, pas d'une erreur de pôle.
