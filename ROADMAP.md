# Helios-Quant-Core: Implementation Plan

## Phase 0: Project Foundation
- [x] Initialize `pyproject.toml` with `ruff`, `mypy`, `pytest`
- [x] Set up minimal directory structure (`src/helios_core/`, `tests/`)
- [x] Set up Professional Infrastructure (`Makefile`, `pre-commit`, `ci.yml`)

## Phase 1: The Digital Twin (Battery Asset)
- [x] Create `BatteryAsset` class ensuring strict physical constraints (capacity, max power, efficiency)
- [x] Write punitive unit tests checking constraint violations
- [x] Migrate `BatteryAsset` configuration to `pydantic`.

## Phase 2: Theoretical Foundation & Formulation
- [x] Write `THEORY.md` whitepaper bridging DRO, Physics-Informed Optimization, and Algorithmic Tractability.

## Phase 3: The Stochastic Generator
- [x] Construct $\hat{\mathbb{P}}_N$ from empirical robust sampling (ENTSO-E/Open-Meteo)
- [x] Define the ambiguity bounds computationally.

## Phase 4: The Quantitative Core & Solvers
- [x] Develop `scaling.py` for numerical armoring
- [x] Implement `controller.py` with CVXPY MPC basic formulation and Fallback Heuristics
- [x] Implement Wasserstein DRO Dual Exact Convex formulation mapping

## Phase 5: The Real-World Confrontation (Crisis Backtest)
- [x] Define Industrial Limits and Strategy Metrics  (`01_model_limits_and_assumptions.md`, `02_investor_faq.md`)
- [x] Connect historic real-world ENTSO-E datasets (targeting the Aug 2022 severity crisis)
- [x] Implement Backtesting Engine orchestrating the `BatteryMPC` rolling horizon.
- [x] Render Comparative Dashboards (DRO vs Naïve/Deterministic PnL and Exposure)

## Phase 6: Advanced Industrial Modeling
- [ ] Dynamic $\epsilon$ adjustment based on GARCH / Historical Variance Regimes
- [x] LCOS (Levelized Cost of Storage) Non-Linear Battery Degradation penalization
- [ ] Market Impact / Slippage penalty on EPEX SPOT orders

## Phase 7: Production Deployment (Paper Trading)
- [x] Live Data Connectors (ENTSO-E live hourly feed)
- [ ] Asynchronous Engine scheduler (cron / APScheduler)
- [ ] Telegram/Slack execution heartbeat reporting
