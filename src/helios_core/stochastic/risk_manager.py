from __future__ import annotations

import numpy as np
import pandas as pd
from typing import Optional


class DynamicEpsilonManager:
    """
    Risk Manager for the Robust DRO Agent.

    Risque (variance) ≠ Incertitude (ε). La variance est DÉJÀ dans les scénarios.
    ε = rayon d'ambiguïté (confiance dans la distribution empirique).

    Post-Refonte: ε_base ancré théoriquement O(1/√N), indépendant de la volatilité.
    L'entropie régime (HMM hésite) gonfle ε pour robustesse en phase de transition.
    """
    def __init__(
        self,
        eps_min: float = 0.05,
        eps_max: float = 0.50,
        eps_nominal: float = 0.15,
        eps_n_ref: int = 30,
        entropy_beta: float = 0.5,
        model_gamma: float = 0.5,
    ):
        self.eps_min = eps_min
        self.eps_max = eps_max
        self.eps_nominal = eps_nominal
        self.eps_n_ref = eps_n_ref
        self.entropy_beta = entropy_beta
        self.model_gamma = model_gamma

    def compute_epsilon_from_scenarios(
        self,
        scenarios: np.ndarray,
        regime_uncertainty: Optional[float] = None,
        model_error: Optional[float] = None,
    ) -> float:
        """
        ε_base = eps_nominal * √(n_ref/N) — décroissance théorique O(1/√N).
        La volatilité des prix n'intervient plus : elle est déjà dans les scénarios.

        regime_uncertainty: Entropie [0,1]. Si fournie : eps *= (1 + beta * H).
        model_error: CVE (RMSE/mean|y|). Si fournie : eps *= (1 + gamma * CVE).
        Double Bouclier: monde (régime) × capteur (modèle).
        """
        N = scenarios.shape[0]
        if N < 2:
            return (self.eps_min + self.eps_max) / 2.0

        eps_base = self.eps_nominal * np.sqrt(self.eps_n_ref / N)

        if regime_uncertainty is not None and self.entropy_beta > 0:
            eps_base *= 1.0 + self.entropy_beta * float(np.clip(regime_uncertainty, 0.0, 1.0))

        if model_error is not None and self.model_gamma > 0:
            eps_base *= 1.0 + self.model_gamma * float(np.clip(model_error, 0.0, 2.0))

        return float(np.clip(eps_base, self.eps_min, self.eps_max))

    def compute_epsilon(self, historical_prices: pd.Series) -> float:
        """
        Legacy: retourne eps_nominal (appel sans scénarios).
        Remplacé par compute_epsilon_from_scenarios() en production.
        """
        return float(np.clip(self.eps_nominal, self.eps_min, self.eps_max))
