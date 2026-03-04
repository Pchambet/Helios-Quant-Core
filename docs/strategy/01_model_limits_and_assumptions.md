# Helios-Quant-Core: Model Limits and Assumptions

## Limitation : Le Biais de Troncature du Marché Day-Ahead (T=24)

L'algorithme MPC opère sur la fenêtre de publication stricte de l'EPEX SPOT (24h). En l'absence de prévisions déterministes à 48h (Receding Horizon complet), le modèle souffre d'un biais de troncature à minuit.

Bien qu'une Soft Terminal Constraint asymétrique (pénalité indexée sur le prix maximum) ait été implémentée pour forcer la rétention de charge nocturne, un agent naïf hard-codé sur un cycle inter-journalier peut mathématiquement capturer un meilleur spread overnight brut. Le système Helios assume cette légère perte de rendement inter-jours en échange d'une extraction optimale et dynamique de la volatilité intra-jour et d'une protection stricte du LCOS, inaccessibles à l'agent naïf.
