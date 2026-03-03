# Helios-Quant-Core: Institution / Investor F.A.Q.

Ce document rassemble les questions "brutales" et réalistes que posent les experts de l'industrie (Fonds Quant, Traders Énergie, Asset Managers Neoen/Total) lors de l'audit d'une stratégie de trading sur batterie, accompagnées de nos réponses quantitatives strictes.

---

### Q1. "Es-tu un Price-Taker ou un Price-Maker ? Quel est ton Market Impact ?"
**Notre Réponse:** Le modèle backtesté est purement Price-Taker jusqu'à son seuil de puissance nominale. Pour un actif de petite taille (ex: 5-10 MW), l'impact sur l'EPEX SPOT est négligeable car la liquidité journalière est suffisamment profonde en France/Allemagne. Cependant, pour des méga-batteries (> 100 MW), le modèle mathématique surestimera les gains en ignorant le slippage (écrasement du prix). Dans nos prochaines itérations d'industrialisation avancée, le solveur `cvxpy` basculera d'un pur LP (Linear Program) vers un QP (Quadratic Program) pour pénaliser quadratiquement les volumes monstrueux afin de simuler la profondeur du carnet d'ordres.

### Q2. "Comment pilotes-tu le rayon d'ambiguïté de Wasserstein $\epsilon$ ? Est-il dynamique ?"
**Notre Réponse:** Pour la V1 du noyau mathématique, $\epsilon$ sert de garde-fou macro-analytique testable. Nous prouvons que le modèle peut s'éteindre sous une incertitude massive ($\epsilon > 24$). Dans la réalité de l'exploitation en production, $\epsilon$ ne doit jamais être statique. L'Axe de Modélisation Avancée (Phase 6) du projet prévoit d'insérer un filtre dynamique qui recalibre $\epsilon$ de manière exogène chaque matin en fonction du clustering de volatilité (ex: Modèle GARCH sur les prix des 7 derniers jours).

### Q3. "Le PnL net couvre-t-il la mort chimique de l'actif (Levelized Cost of Storage) ?"
**Notre Réponse:** Actuellement, le `Digital Twin` modélise l'efficacité énergétique de la batterie (pertes thermiques lors des cycles de charge/décharge) et les fuites passives. Le contrôleur intègre également un coût d'usure minimaliste `cyclic_penalty`. Toutefois, la dégradation non-linéaire du Lithium-Ion n'est pas encore modélisée financièrement. Le pipeline de maturation prévoit d'incorporer le LCOS dans la matrice d'optimisation via des tranches affines additives pénalisant les pires profondeurs de décharge (ex: interdire les paliers de 5% à 15%). Les PnL bruts de nos rapports actuels doivent donc être relus comme des "Gains Bruts pré-LCOS".

### Q4. "Ton solveur survit-il aux vraies crises ? (Exemple: Août 2022)"
**Notre Réponse:** C'est l'essence même de l'approche DRO. Contrairement à une programmation stochastique classique (qui suppose que l'avenir s'échantillonnera selon une cloche de Gauss "normale"), notre optimisation par Minimisation du Pire Cas (Min-Max Dual) ne parie pas sur la continuité. Lors de la phase de test **"Axe Historique" (Phase 5)**, le système est confronté in vitro aux données réelles de l'EPEX SPOT d'Août 2022 (Crise Énergétique Européenne). Le but est de garantir, graphiques à l'appui, que notre module agit comme un hedge robuste, verrouillant le risque de destruction du capital face à des sauts de prix irrationnels de +3000€.

---
*Ce document de R&D est la preuve que l'équipe d'ingénierie Quantitative maintient une lucidité absolue sur les différences entre un gain in vitro (laboratoire) et in vivo (salle des marchés).*
