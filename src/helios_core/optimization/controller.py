import cvxpy as cp
import numpy as np
import logging
from typing import Tuple

from helios_core.assets.battery import BatteryAsset
from helios_core.optimization.scaling import PriceScaler

# Configure basic logging for solver failures
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BatteryMPC:
    """
    Model Predictive Controller integrating the Battery Digital Twin with CVXPY.
    """
    def __init__(self, battery: BatteryAsset, scaler: PriceScaler):
        self.battery = battery
        self.scaler = scaler

    def solve_deterministic(self, expected_prices: np.ndarray) -> Tuple[np.ndarray, np.ndarray, str]:
        """
        Solves the basic deterministic problem over a 24h horizon.

        Args:
            expected_prices: (24,) array of expected wholesale prices (unscaled).

        Returns:
            p_charge: (24,) array of optimal charging powers (MW)
            p_discharge: (24,) array of optimal discharging powers (MW)
            status: solver status string
        """
        T = len(expected_prices)

        # 1. Armoring: Scale prices to preserve matrix conditioning
        try:
            scaled_prices = self.scaler.transform(expected_prices)
        except ValueError:
            # Auto-fit if uninitialized (should usually be done beforehand on history)
            scaled_prices = self.scaler.fit_transform(expected_prices)

        # 2. Decision Variables
        p_ch = cp.Variable(T, nonneg=True)
        p_dis = cp.Variable(T, nonneg=True)
        soc = cp.Variable(T + 1, nonneg=True)

        # 3. Objective: Maximize Profit (Minimize Negative Profit)
        # Note: scaled_prices are passed in. The optimal policy (x) is scale-invariant,
        # but the objective value (profit) will need inverse scaling later if evaluated.
        # We replace the naive cyclic_penalty with the formal Levelized Cost of Storage (LCOS).
        # Since expected_prices are scaled, the marginal wear cost must be equally scaled linearly.
        marginal_lcos_eur = self.battery.marginal_wear_cost_per_mwh
        scaled_wear_penalty = self.scaler.scale_difference(marginal_lcos_eur)

        profit = p_dis @ scaled_prices - p_ch @ scaled_prices
        wear = scaled_wear_penalty * cp.sum(p_ch + p_dis)  # type: ignore

        objective = cp.Maximize(profit - wear)

        # 4. Physical Constraints (Linearized Digital Twin)
        constraints = []

        # Initial State
        constraints.append(soc[0] == self.battery.soc_mwh)

        for t in range(T):
            # Power Limits
            constraints.append(p_ch[t] <= self.battery.max_charge_mw)
            constraints.append(p_dis[t] <= self.battery.max_discharge_mw)

            # SOC Dynamics (efficiency & leakage)
            leakage_factor = 1.0 - self.battery.leakage_rate
            ch_eff = self.battery.efficiency_charge
            dis_eff = self.battery.efficiency_discharge

            # Explicit constraint: SOC_{t+1} = SOC_t * (1-leakage) + charge*eff - discharge/eff
            # Note: CVXPY requires linear operations. This is perfectly linear.
            constraints.append(
                soc[t+1] == soc[t] * leakage_factor + p_ch[t] * ch_eff - p_dis[t] / dis_eff
            )

            # Energy Limits
            constraints.append(soc[t+1] <= self.battery.capacity_mwh)

        # 5. Solving Form
        prob = cp.Problem(objective, constraints)

        try:
            # We use the default modern solver (CLARABEL or OSQP) gracefully.
            prob.solve()  # type: ignore
        except Exception as e:
            logger.error(f"Solver crashed with exception: {e}")
            p_ch_fb, p_dis_fb = self._fallback_heuristic(T)
            return p_ch_fb, p_dis_fb, "SOLVER_EXCEPTION"

        # 6. Fallback Operational Safety Nets
        if prob.status not in ["optimal", "optimal_inaccurate"]:
            logger.warning(f"Solver returned unsafe status: {prob.status}. Triggering Fallback.")
            p_ch_fb, p_dis_fb = self._fallback_heuristic(T)
            return p_ch_fb, p_dis_fb, prob.status

        if p_ch.value is None or p_dis.value is None:
            logger.error("Solver returned None values despite optimal status.")
            p_ch_fb, p_dis_fb = self._fallback_heuristic(T)
            return p_ch_fb, p_dis_fb, "SOLVER_ERROR"

        return p_ch.value, p_dis.value, prob.status

    def solve_robust(self, historical_scenarios: np.ndarray, epsilon: float) -> Tuple[np.ndarray, np.ndarray, str]:
        """
        Solves the Wasserstein Distributionally Robust problem exactly (LP).

        Args:
            historical_scenarios: (N, 24) empirical matrix of prices.
            epsilon: The scaled ambiguity radius (must be scaled alongside prices).

        Returns:
            p_charge, p_discharge, status
        """
        N, T = historical_scenarios.shape

        # 1. Armoring
        try:
            scaled_scenarios = self.scaler.transform(historical_scenarios)
        except ValueError:
            scaled_scenarios = self.scaler.fit_transform(historical_scenarios)

        # 2. Base DVs
        p_ch = cp.Variable(T, nonneg=True)
        p_dis = cp.Variable(T, nonneg=True)
        soc = cp.Variable(T + 1, nonneg=True)

        # 3. Dual Variables for Wasserstein Reformulation
        # We are minimizing the Worst-Case Negative Profit (meaning Maximizing Worst-Case Profit).
        # Standard form: min lambda * epsilon + (1/N) * sum_i s_i
        lam = cp.Variable(nonneg=True)
        s = cp.Variable(N)

        # 4. Objective (Min-Min Dual form)
        marginal_lcos_eur = self.battery.marginal_wear_cost_per_mwh
        scaled_wear_penalty = self.scaler.scale_difference(marginal_lcos_eur)
        wear = scaled_wear_penalty * cp.sum(p_ch + p_dis)  # type: ignore

        # We want to maximize worst-case profit.
        # By strong duality, max_{Q} E_Q[Profit] = min_{lam, s} lam*eps + (1/N) sum(s)
        # Therefore, the objective of the overall problem is to Maximize this lower bound.
        # Wait, standard DRO minimizes Loss (where Loss = Cost - Revenue).
        # Loss L(u, xi) = (p_ch @ xi - p_dis @ xi) + wear
        # Primal: min_u max_Q E_Q[ L(u, xi) ]
        # Dual: min_{u, lam, s} lam * eps + 1/N * sum(s)
        # Subject to: s_i >= L(u, xi_i) + lam ||xi - xi_i|| for all xi.
        # This translates exactly into our code as a global minimization.

        objective = cp.Minimize(lam * epsilon + (1/N) * cp.sum(s))  # type: ignore
        constraints = []

        # Robust Dual Constraints (The L1 norm trick to keep it LP)
        # Because we only have linear dependence in xi, the supremum condition simplifies to bounding the dual norm.
        # For L1 primal distance metric, the dual norm is L_inf.
        # s_i >= (p_ch @ xi_i - p_dis @ xi_i) + wear

        for i in range(N):
            empirical_loss = (p_ch @ scaled_scenarios[i] - p_dis @ scaled_scenarios[i]) + wear
            constraints.append(s[i] >= empirical_loss)

        # The dual norm constraint ensuring the supremum over ALL xi is bounded
        # For L1 distance, we must bound the gradient of the loss function by lam.
        # The gradient of the Loss w.r.t xi is exactly: (p_ch - p_dis)
        # So we need || (p_ch - p_dis) ||_inf <= lam
        # Which means for every t: -lam <= (p_ch[t] - p_dis[t]) <= lam
        # Therefore:
        for t in range(T):
            constraints.append(lam >= p_ch[t] - p_dis[t])
            constraints.append(lam >= -(p_ch[t] - p_dis[t]))

        # 5. Physical Constraints (Identical to Deterministic)
        constraints.append(soc[0] == self.battery.soc_mwh)
        for t in range(T):
            constraints.append(p_ch[t] <= self.battery.max_charge_mw)
            constraints.append(p_dis[t] <= self.battery.max_discharge_mw)

            leakage_factor = 1.0 - self.battery.leakage_rate
            ch_eff = self.battery.efficiency_charge
            dis_eff = self.battery.efficiency_discharge
            constraints.append(
                soc[t+1] == soc[t] * leakage_factor + p_ch[t] * ch_eff - p_dis[t] / dis_eff
            )
            constraints.append(soc[t+1] <= self.battery.capacity_mwh)

        # 6. Solving form
        prob = cp.Problem(objective, constraints)
        try:
            prob.solve()  # type: ignore
        except Exception as e:
            logger.error(f"DRO Solver crashed with exception: {e}")
            p_ch_fb, p_dis_fb = self._fallback_heuristic(T)
            return p_ch_fb, p_dis_fb, "SOLVER_EXCEPTION"

        if prob.status not in ["optimal", "optimal_inaccurate"]:
            logger.warning(f"DRO Solver returned unsafe status: {prob.status}. Triggering Fallback.")
            p_ch_fb, p_dis_fb = self._fallback_heuristic(T)
            return p_ch_fb, p_dis_fb, prob.status

        if p_ch.value is None or p_dis.value is None:
            logger.error("DRO Solver returned None values.")
            p_ch_fb, p_dis_fb = self._fallback_heuristic(T)
            return p_ch_fb, p_dis_fb, "SOLVER_ERROR"

        return p_ch.value, p_dis.value, prob.status

    def _fallback_heuristic(self, T: int) -> Tuple[np.ndarray, np.ndarray]:
        """
        Operational Safety Net: If the solver is infeasible or unbounded,
        we do not blow up the plant. We shut down operations (return 0).
        Future versions could implement a naive night-charge heuristic here.
        """
        return np.zeros(T), np.zeros(T)
