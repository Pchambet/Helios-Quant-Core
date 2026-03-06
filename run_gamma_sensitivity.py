"""
Analyse de sensibilité sur γ (model_gamma) — Double Bouclier.

Lance 3 benchmarks crise avec γ ∈ {0.1, 0.5, 1.0} pour mesurer l'impact
du poids de l'erreur modèle (CVE) sur le PnL et la robustesse du DRO.

Fail-fast: requiert LightGBM. Sans lui, le CVE reste à 0 et γ n'a aucun effet.
"""
try:
    import lightgbm  # noqa: F401
except ImportError:
    raise RuntimeError(
        "L'analyse de sensibilité sur gamma requiert le LightGBMPriceForecaster. "
        "Installez la dépendance via 'uv pip install lightgbm' avant d'exécuter ce script."
    )

import logging

from helios_core.benchmark.runner import BenchmarkRunner

logging.basicConfig(level=logging.WARNING)  # Réduire le bruit


def main() -> None:
    gammas = [0.1, 0.5, 1.0]
    results_by_gamma: dict[float, dict[str, dict[str, float]]] = {}

    print("\n" + "=" * 70)
    print(" HELIOS-QUANT-CORE : SENSIBILITÉ γ (model_gamma) — CRISE AOÛT 2022 ")
    print("=" * 70)
    print("\nε_adaptatif = ε_base × (1 + β×H) × (1 + γ×CVE)")
    print("γ = poids de l'erreur instrumentale (CVE) dans le Risk Manager.\n")

    for gamma in gammas:
        print(f"[RUN] γ = {gamma} ...")
        runner = BenchmarkRunner(
            preset="crisis",
            seed=42,
            mock=False,
            model_gamma=gamma,
        )
        results_by_gamma[gamma] = runner.run()

    # Tableau comparatif (DRO uniquement, Naive/MPC identiques pour tous les γ)
    print("\n" + "=" * 70)
    print(" RÉSULTATS : ROBUST DRO PAR VALEUR DE γ ")
    print("=" * 70)
    print(f"\n{'γ':<8} | {'NET PNL (€)':<12} | {'CYCLES (EFC)':<12} | {'RoDC (Ratio)':<12}")
    print("-" * 50)

    baseline = results_by_gamma[0.5]  # Référence pour Naive/MPC
    for gamma in gammas:
        r = results_by_gamma[gamma]["Robust DRO (L1)"]
        net = r["Net Adjusted PnL (EUR)"]
        efc = r["EFC (Cycles)"]
        rodc = r["RoDC (Ratio)"]
        print(f"{gamma:<8} | {net:<12.2f} | {efc:<12.2f} | {rodc:<12.2f}")

    print("-" * 50)
    print(f"\n[REF] Naive: {baseline['Naive Heuristic']['Net Adjusted PnL (EUR)']:.2f} €")
    print(f"[REF] MPC:  {baseline['Deterministic MPC']['Net Adjusted PnL (EUR)']:.2f} €")
    print("\n" + "=" * 70 + "\n")


if __name__ == "__main__":
    main()
