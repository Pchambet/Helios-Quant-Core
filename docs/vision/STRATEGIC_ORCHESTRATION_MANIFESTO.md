# Manifeste Helios : De l'Actif Isolé à l'Orchestration Systémique

**Document de vision stratégique — Nord de la boussole du projet.**

---

## 1. La Thèse : L'Énergie est une Information

La valeur de ce projet ne réside pas dans la spéculation sur le prix du MWh, mais dans la **réduction de l'asymétrie d'information**. Le prix n'est que le symptôme d'une réalité physique sous-jacente dictée par le climat et la géopolitique.

- **Le Micro-Expert** : Gère la thermodynamique et le profit d'une cellule de batterie.
- **Le Macro-Cerveau** : Décode le système nerveux de l'Europe pour anticiper les tensions avant qu'elles ne se traduisent en volatilité de marché.

---

## 2. La Feuille de Route : Micro → Méso → Macro


| Niveau    | Chantier                                                               | Validation                                             |
| --------- | ---------------------------------------------------------------------- | ------------------------------------------------------ |
| **Micro** | Une batterie, un point. MPC + LCOS + Paper Trading.                    | Baseline CVE, Tear Sheet, PnL honnête.                 |
| **Méso**  | Analogues météo (KNN), ScenarioGenerator. Explicabilité des décisions. | Comparaison v1.0 vs v2.0, visualisation des "jumeaux". |
| **Macro** | Maillage Europe, données matricielles, flux transfrontaliers.          | Multi-asset, VPP, placement géographique.              |


**Principe** : Ne pas passer au niveau supérieur sans avoir validé le précédent. Le succès du Macro dépend de la rentabilité du Micro.

---

## 3. Le Chantier Météo : Du Ponctuel au Maillage

L'approche par API ponctuelle est une première étape. La vision cible est une **retranscription dynamique** du continent.

- **Phase actuelle** : Open-Meteo (3 stations), ENTSO-E (fondamentaux). LightGBM avec features météo (lag_24).
- **Phase Méso** : Analogues historiques — "Jumeaux météorologiques" pour prédire les conséquences sur le prix et les pics énergétiques.
- **Phase Macro** : **Données Matricielles (Gridded Data)** — Intégration de flux type Copernicus pour transformer l'Europe en une grille de pixels météo-énergétiques. Causalité locale : comprendre comment une tempête en Mer du Nord sature les interconnexions et propage l'impact.

---

## 4. Géopolitique et Dynamiques de Flux

L'énergie est l'instrument de puissance par excellence. Le système doit intégrer la lecture des tensions :

- **Flux Transfrontaliers** : L'arbitrage n'est plus seulement temporel (jour/nuit) mais géographique (export/import).
- **Dualité Publique/Privé** : Anticiper comment les acteurs privés (producteurs EnR) réagissent aux contraintes des acteurs publics (régulateurs, TSO) pour stabiliser le réseau.
- **Lien Météo → Prix** : Le vent, le soleil et la température dictent la production et la demande. Comprendre localement pour prédire globalement.

---

## 5. Gestion de Parc (VPP) vs Spéculation

La priorité stratégique est la **gestion d'actifs**, pas la spéculation.

- **L'Asset Management** : Maximiser la durée de vie et l'utilité d'une infrastructure réelle. LCOS et stress penalty ne sont pas des options — ils sont la signature du projet.
- **La Souveraineté** : Créer un outil capable d'aider les agrégateurs et les États à piloter la transition énergétique par la donnée, et non par l'intuition.

---

## 6. Le "Moat" : L'Avantage Défensif

L'avantage compétitif d'Helios repose sur trois piliers :

1. **L'Honnêteté Physique** : Respect absolu de la dégradation matérielle (LCOS). Le PnL ne ment pas sur l'usure.
2. **L'Intelligence des Analogues** : Utiliser l'histoire climatique pour prédire le futur énergétique. Explicabilité : "Je décharge parce que ce pattern ressemble au 12 janvier 2024."
3. **La Vision Transversale** : Relier la micro-thermodynamique à la macro-géopolitique. Un seul code, une seule physique, des échelles multiples.

---

## 7. Méthodologie de Recherche

Pour franchir les limites mathématiques et informatiques, le projet s'appuie sur une **veille académique structurée** :

- **Sources** : Papiers (arXiv, IEEE, journals énergie), cours (masters énergie/ML), thèses, rapports TSO (RTE, ENTSO-E).
- **Domaines clés** : Analog forecasting, gridded data, MPC batteries, DRO, Big Data pour séries spatio-temporelles.
- **Approche** : Ne pas réinventer — recomposer les briques existantes pour le cas énergie-météo-marché.

Les contraintes (MacBook, données, temps) sont des paramètres d'exécution, pas des limites à la vision. La littérature fournit les méthodes ; l'ingénierie les adapte.

---

## 8. Clients et Produit


| Segment                      | Besoin                                      | Ce qu'Helios apporte                              |
| ---------------------------- | ------------------------------------------- | ------------------------------------------------- |
| **Propriétaire de batterie** | Rentabilité sans détruire l'actif.          | MPC + LCOS, PnL honnête.                          |
| **Agrégateur VPP**           | Coordination de milliers d'actifs.          | Système nerveux météo-sensible, scalable.         |
| **Producteur EnR**           | "Vendre maintenant ou garder pour le pic ?" | Anticipation des Duck Curves, stress énergétique. |
| **Site industriel / Data Center IA** | Arbitrer chaleur, H2, calcul et électricité. | Moteur Multi-Commodités : Peak Shaving, arbitrage Spot, aFRR. |
| **TSO / État**               | Transparence sur un marché chaotique.       | Vision macro, retranscription des flux.           |


---

## 9. Rappel Opérationnel

Ce document fixe le Nord. L'exécution reste séquentielle :

1. Valider le Micro (baseline v1.0, tear sheet).
2. Merger v2.0 (météo), comparer CVE.
3. Réactiver les Analogues (Méso).
4. Envisager le Multi-Asset (Macro).

**Le succès de la grande carte européenne dépend des 4,83 € de la batterie aujourd'hui.**

---

## 10. Ruptures et Opportunités 2025-2026

Pour passer d'un projet "academiquement brillant" à une machine à cash capable de devancer les géants, il faut identifier les **failles structurelles du marché européen** et les ruptures technologiques exploitables.

### Vision 1 : Le Pivot "Grid-Maker" (Inertie Synthétique)

Plutôt que de se battre sur le marché saturé du FCR (dont les prix s'effondrent à cause de la cannibalisation par les batteries standard), Helios-Quant pourrait pivoter vers le **Grid-Forming (GFM)**.

- **Concept** : Utiliser des onduleurs avancés capables de créer leur propre tension et fréquence, au lieu de simplement suivre celle du réseau (Grid-Following).
- **Opportunité** : L'Allemagne lance des enchères dédiées à l'inertie synthétique et aux services de Black Start dès 2026. Ces services sont beaucoup mieux rémunérés car ils exigent une technologie que 90 % des batteries installées ne possèdent pas encore.
- **Alpha stratégique** : Devenir un "architecte du réseau" plutôt qu'un "parasite du prix".

### Vision 2 : L'Avantage Computationnel via les PINNs

La limite actuelle de l'arbitrage macro est le temps de résolution des équations de flux (AC-OPF).

- **Pépite technologique** : Les PINNs (Physics-Informed Neural Networks, ex. PINCO) intègrent les lois de Kirchhoff directement dans la fonction de perte du réseau de neurones.
- **Gain** : Un solveur classique (Gurobi/IPM) prend secondes ou minutes ; un PINN fournit une solution quasi-optimale en moins de 0,7 ms.
- **Impact** : HFT sur l'Intraday, capture des opportunités de congestion avant que le marché ne les affiche. Gain de revenus estimé à 58 % vs optimisation horaire.

### Vision 3 : L'Arbitrage "Redispatch 2.0"

En Allemagne et dans le Core region, le coût de la gestion des congestions (Redispatch) explose (4,2 milliards € en 2022).

- **Paradigme actuel** : Les batteries réagissent à un prix national unique, ignorant les goulots d'étranglement locaux.
- **Stratégie** : Un "Digital Twin" localisé identifie les nœuds où le TSO sera forcé de payer une batterie pour s'arrêter de charger (Redispatch vers le bas) ou forcer une décharge.
- **Potentiel** : 3 € à 6 € par kW de capacité par an en revenus additionnels, sans utiliser les cycles pour le marché de gros.

### Vision 4 : Le Marché 15 Minutes (Juin 2025)

Le basculement de la granularité Day-Ahead de 60 à 15 minutes en juin 2025 est une **rupture majeure**.

- **Risque pour les autres** : La plupart des modèles ne sont pas dimensionnés pour l'explosion du nombre de variables.
- **Opportunité Helios-Quant** : Solveurs comme Linopy (optimisés pour variables N-dimensionnelles) permettent de capturer la volatilité des rampes solaire/éolien à l'échelle du quart d'heure, là où les acteurs traditionnels subiront des erreurs de prévision massives.

### Priorisation et Synergies


| Vision               | Horizon              | Dépendance                  | Synergie avec le Moat                  |
| -------------------- | -------------------- | --------------------------- | -------------------------------------- |
| **15-min Market**    | Juin 2025 (imminent) | Logiciel uniquement         | Vision transversale, scalabilité       |
| **Redispatch 2.0**   | 2025-2026            | Digital Twin, données TSO   | Honnêteté physique, localisation       |
| **PINNs**            | R&D 2025+            | Littérature, implémentation | Honnêteté physique (lois de Kirchhoff) |
| **Grid-Maker (GFM)** | 2026                 | Matériel (onduleurs GFM)    | Architecte du réseau, souveraineté     |


**Principe** : Le 15-min market est une opportunité immédiate et logicielle. Les autres visions nécessitent soit du R&D (PINNs), soit des données TSO (Redispatch), soit du hardware (GFM). Ne pas disperser — valider le Micro, puis choisir une rupture à exploiter en priorité.

---

## 11. Sources et Références

*(À compléter — placeholders pour les citations [1,2,3,4])*

- [1] Cannibalisation FCR / batteries
- [2] Effondrement prix FCR
- [3] PINNs, PINCO, gain 58 % HFT Intraday
- [4] Linopy, optimisation N-dimensionnelle


---

## 12. Choix d'Architecture et Trajectoire

**Décision stratégique** : La trajectoire prioritaire d'Helios est le **SaaS Multi-Commodités** (B2B industrie, Data Centers IA, Pompes à Chaleur), et non le Prop Shop (Hedge Fund) Intraday.

### Trajectoire retenue : SaaS Multi-Énergies

- **Alignement** : Cohérent avec la priorité "gestion d'actifs" (section 5) et le segment "Site industriel / Data Center IA" (section 8).
- **Abstraction technique** : Introduction d'une classe mère `FlexibleAsset` avec méthodes génériques (`get_constraints()`, `get_cost_function()`). `BatteryAsset`, `ThermalAsset` (pompe à chaleur) et `DataCenterAsset` en héritent. Le MPC optimise toute combinaison d'actifs sans réécrire le cœur.
- **Métaphore physique** : Une pompe à chaleur = "batterie thermique" (température au lieu de SOC). Un Data Center IA = "batterie de calcul" (buffer de tâches). Même ADN mathématique que le BESS.

### Prop Shop écarté (pour l'instant)

Le trading Intraday continu (CID) n'est pas un problème de mathématiques, c'est un **problème d'infrastructure** : latence, LOB en temps réel, programmation dynamique, colocation. Le code actuel (Python, CVXPY, cron) est conçu pour l'intelligence, pas pour la vitesse. Le Prop Shop serait un tout autre métier — on conserve l'avantage compétitif (optimisation thermodynamique complexe) plutôt que de se battre sur le terrain de la latence.

### Prochaine étape d'architecture

Valider le Micro (baseline v1.0, tear sheet), puis introduire l'abstraction `FlexibleAsset` pour préparer l'extension vers `ThermalAsset` et `DataCenterAsset` dès qu'un premier client B2B est identifié.
