# Helios-Quant-Core

**Distributionally Robust Optimization engine for microgrid energy arbitrage.**

Helios-Quant-Core formulates the day-ahead battery scheduling problem as a Wasserstein DRO program embedded inside a receding-horizon Model Predictive Control loop. The goal: maximise arbitrage revenue while remaining robust to the worst-case price distribution within a data-driven ambiguity set.

> **Status — active development.** The mathematical framework is defined; implementation is in progress.

---

## Approach

| Layer | Method |
|---|---|
| **Uncertainty model** | Wasserstein ambiguity set calibrated on historical spot prices |
| **Core formulation** | Min-max (DRO) linear/conic program for worst-case expected cost |
| **Control loop** | Receding-horizon MPC with rolling re-optimization |
| **Solver back-end** | CVXPY + Mosek / SCS |

### Why DRO over stochastic programming?

Classical stochastic optimization assumes the true distribution is known or can be sampled from. In energy markets, price distributions shift with weather, policy changes, and grid topology. DRO hedges against distributional shift by optimizing over a ball of plausible distributions centered on the empirical measure, providing finite-sample performance guarantees.

## Planned Architecture

```
helios/
├── data/           # price loaders, feature engineering
├── ambiguity/      # Wasserstein ball construction, radius selection
├── optim/          # DRO formulation, MPC controller
├── simulate/       # backtesting engine, scenario generation
├── visualize/      # dispatch plots, P&L curves
└── config/         # YAML-based experiment configs
```

## Key References

- Mohajerin Esfahani & Kuhn, *Data-driven distributionally robust optimization using the Wasserstein metric*, Mathematical Programming (2018)
- Blanchet & Murthy, *Quantifying distributional model risk via optimal transport*, Mathematics of Operations Research (2019)
- Rawlings, Mayne & Diehl, *Model Predictive Control: Theory, Computation, and Design* (2017)

## Tech Stack

Python · CVXPY · NumPy · pandas · Matplotlib · Mosek

## License

GPL-3.0 — see [LICENSE](LICENSE).
