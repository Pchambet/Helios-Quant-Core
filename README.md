# Helios-Quant-Core

![Tests](https://img.shields.io/badge/tests-passing-success)
![Mypy](https://img.shields.io/badge/mypy-strict-blue)
![Ruff](https://img.shields.io/badge/linter-ruff-black)
![License](https://img.shields.io/badge/license-GPL--3.0-blue)
![Python](https://img.shields.io/badge/python-3.14-blue)

**Distributionally Robust Optimization engine for microgrid energy arbitrage.**

Helios-Quant-Core formulates the day-ahead battery scheduling problem as a Wasserstein Distributionally Robust Optimization (DRO) program embedded inside a receding-horizon Model Predictive Control (MPC) loop. The goal: maximize arbitrage revenue while remaining mathematically robust to the worst-case price distribution within a data-driven ambiguity set.

## Mission & Vision

Designed as an industrial-grade bridge between advanced operations research and production-ready Python engineering. The engine emphasizes **Numerical Tractability**, **Physical Adherence**, and **Duality Scaling**.

Rather than relying on naive stochastic programming which falls apart under distributional shifts (weather anomalies, geopolitical shocks, grid topology changes), Helios hedges mathematically against unpredictability. It explicitly computes the worst-case expected cost within an $L_1$ Wasserstein ball centered around empirical observations from EPEX SPOT and Open-Meteo.

---

## Architecture Overview

The system is built on strictly decoupled layers ensuring physical safety precedes algorithmic intelligence:

### 1. The Digital Twin (`BatteryAsset`)
A heavily constrained, purely physical simulator built with `pydantic`.
- Strictly enforces physical bounds: `max_charge_mw`, `max_discharge_mw`, `capacity_mwh`.
- Implements linear dynamics for efficiency losses (`efficiency_charge`, `efficiency_discharge`) and degradation (`leakage_rate_per_hour`).
- **Safety First:** Punitive unit tests guarantee it is mathematically impossible for any solver to command actions that violate the laws of thermodynamics.

### 2. The Stochastic Generator (`ScenarioGenerator`)
- Ingests empirical rolling historical observations.
- Uses exact bootstrapping to synthesize multi-dimensional $N \times 24$ scenario matrices.
- Prepares the discrete empirical measure $\hat{\mathbb{P}}_N$ required to center the Wasserstein ball.

### 3. The Quantitative Solvers (`BatteryMPC`)
Powered by `cvxpy`, this layer translates infinite-dimensional min-max robust problems into finite, highly-tractable exact linear/conic structures.
- **Kantorovich-Rubinstein Duality:** Transforms the intractable supremum over probability measures into a deterministic dual LP mapping using $L_1$ and $L_\infty$ distance relations.
- **Numerical Armoring:** Automatic price scaling isolates the solver from raw market spikes (e.g., -500€ to 9000€), anchoring the condition number $\kappa \approx 1$.
- **Operational Fallback Heuristic:** The factory never crashes. If the solver hits mathematical ill-conditioning (`INFEASIBLE` / `UNBOUNDED`), the MPC gracefully catches the exception, engages a safety mechanism, and returns zero-actions.

---

## Quick Start & Reproducibility

### Setup
We enforce a rigorous `.pre-commit` pipeline with `Ruff` and `Mypy` to ensure an industrial monolithic standard.

```bash
git clone https://github.com/Pchambet/Helios-Quant-Core
cd Helios-Quant-Core

# Create the environment and explicitly install cvxpy / pytest dev dependencies
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Install Git Hooks (typing and formatting)
pre-commit install
```

### Validation
Run the full continuous integration suite locally:
```bash
make format    # Formats with ruff
make check     # Lints with ruff and strictly type-checks with mypy
make test      # Runs all Pytest unit tests (Digital twin, Stochastic, Covariance, Solvers)
```

---

## Theory & Mathematical Formulation

For a deeper dive into the specific mapping of the $L_1$ formulation and why we actively rejected the Wasserstein $L_2$ Second-Order Cone Program (SOCP) mapping in favor of a faster LP dual paradigm, please read the internal documentation:
- [`THEORY.md`](THEORY.md): The core mathematical whitepaper supporting the codebase.

## Tech Stack

- **Python** (Strict typing via `mypy` and `pydantic`)
- **Optimization:** `CVXPY`, solving with `ECOS`, `OSQP` or `SCS`.
- **Compute:** `NumPy`
- **Linting:** `Ruff`, `pytest`

## License

GPL-3.0 — see [LICENSE](LICENSE).
