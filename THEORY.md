# THEORY: Distributionally Robust Control & Physics-Informed Optimization

This document outlines the state-of-the-art mathematical architecture for `Helios-Quant-Core`.

Our objective is to construct a **Model Predictive Control (MPC)** engine for a Battery Energy Storage System (BESS) participating in the Day-Ahead wholesale market (EPEX SPOT). The engine must guarantee non-failure and robust minimum profit under severe uncertainty (worst-case scenario), while strictly respecting the non-linear degradation physics of the lithium-ion asset.

## 1. The Core Paradigm: Why not Stochastic Programming?

Traditional Stochastic Programming (SP) relies on knowing the exact probability distribution $\mathbb{P}$ of future electricity prices (e.g., assuming a Gaussian distribution or relying purely on an empirical finite sample).
**The flaw:** On power markets, extreme price spikes (chocs climatiques, pannes de centrales) are poorly represented in historical distributions (Out-of-Sample). If the assumed distribution $\mathbb{P}$ is wrong, the SP optimizer creates a brittle policy that shatters in production (the "Optimizer's Curse").

**The Solution:** Distributionally Robust Optimization (DRO).
Instead of optimizing for one assumed distribution $\mathbb{P}$, we optimize for the *worst possible* distribution $\mathbb{Q}$ that resides within an "ambiguity set" $\mathcal{P}$. This guarantees safety against severe Out-of-Sample distribution shifts.

## 2. The Ambiguity Set: The Wasserstein Metric

We define the ambiguity set $\mathcal{P}(\epsilon)$ using the Wasserstein distance ($W_p$), rooted in Optimal Transport theory.
Given an empirical distribution of prices $\hat{\mathbb{P}}_N$ (observed from ENTSO-E data), the set of all plausible true distributions $\mathbb{Q}$ is a "ball" of radius $\epsilon$:

$$ \mathcal{P}(\epsilon) = \{ \mathbb{Q} \in \mathcal{M}(\Xi) : W_p(\mathbb{Q}, \hat{\mathbb{P}}_N) \le \epsilon \} $$

- **$W_p$ (Wasserstein metric):** Measures the minimum "cost" to reshape distribution $\mathbb{Q}$ into $\hat{\mathbb{P}}_N$.
- **$\epsilon$ (Radius):** The degree of robustness. If $\epsilon = 0$, we fall back to pure Stochastic Programming (overfitting). If $\epsilon \to \infty$, the algorithm becomes overly paranoid and does nothing. Tuning $\epsilon$ is our main "Alpha".

## 3. The Objective: Infinite Min-Max Formulation

Let $x$ be our vector of decisions (charge/discharge profile over 24h).
Let $\xi$ be the uncertain future prices.
Let $L(x, \xi)$ be the loss function (negative profit) of our BESS.

The DRO objective is an infinite-dimensional Min-Max problem:

$$ \min_{x \in \mathcal{X}} \max_{\mathbb{Q} \in \mathcal{P}(\epsilon)} \mathbb{E}_{\mathbb{Q}} [L(x, \xi)] $$

*Translation:* "Find the physical actions $x$ that minimize our loss, assuming the market $\mathbb{Q}$ will do the absolute worst thing possible within the bounds of realism $\epsilon$."

## 4. Tractability: The Duality Trick

Solving a supremum over an infinite space of probability measures $\mathcal{P}(\epsilon)$ is impossible for a computer.
The fundamental breakthrough (Esfahani & Kuhn, 2018; Blanchet & Murthy, 2019) is applying **Strong Duality** (via the Kantorovich-Rubinstein theorem).

If the loss function $L(x, \xi)$ is convex in $x$ and concave/linear in $\xi$, the infinite Min-Max problem can be perfectly reformulated as a standard, finite-dimensional convex optimization problem:

$$ \min_{x \in \mathcal{X}, \lambda \ge 0} \left( \lambda \epsilon + \frac{1}{N} \sum_{i=1}^N \sup_{\xi \in \Xi} \left[ L(x, \xi) - \lambda \| \xi - \hat{\xi}_i \| \right] \right) $$

**Why this is magic:**
1. We only iterate over the $N$ historical samples $\hat{\xi}_i$.
2. $\lambda$ acts as a shadow price for robustness.
3. `CVXPY` and commercial solvers (Gurobi, Mosek) can solve this exact convex formulation in milliseconds. This makes it viable for real-time Day-Ahead gate closures.

## 5. Physics-Informed Constraints (The Digital Twin in Math)

The decision vector $x_t$ (Power in MW) is constrained by physical reality $\mathcal{X}$. The constraints must remain linear or convex to preserve the solver's speed.

### A. Power Limits (Linear)
$$ -P_{max}^{discharge} \le x_t \le P_{max}^{charge} $$

### B. State of Charge (Linear Dynamics)
Let $S_t$ be the energy (MWh) in the battery at hour $t$.
$$ S_{t+1} = S_t (1 - \text{leakage}) + \eta_{charge} x_t^+ - \frac{1}{\eta_{discharge}} x_t^- $$
To keep this linear in `CVXPY`, we split $x_t$ into two positive variables: $x_t = P_t^{charge} - P_t^{discharge}$, where both $P \ge 0$.

### C. Cycle Degradation (Convex Relaxation)
Batteries degrade non-linearly. To penalize micro-cycling without breaking convexity, we add an absolute cost $\kappa$ to the objective function for the total energy throughput:
$$ \text{Degradation Penalty} = \kappa \sum_{t=1}^{24} (P_t^{charge} + P_t^{discharge}) $$
This forces the DRO solver to only trade if the expected market spread covers both the efficiency loss *and* the chemical aging cost of the lithium-ion cells.

---
## Summary of the Architecture
Our engine will fetch ENTSO-E data, construct $\hat{\mathbb{P}}_N$, formulate the Dual Wasserstein Convex problem integrating the physical constraints, and output a 24-hour action vector $x^*$ guaranteed to be structurally optimal.
