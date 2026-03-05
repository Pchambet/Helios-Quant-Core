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
    def __init__(self, battery: BatteryAsset, scaler: PriceScaler, alpha_slippage: float = 1.0, margin_funding_rate: float = 5e-6):
        self.battery = battery
        self.scaler = scaler
        self.alpha_slippage = alpha_slippage
        # FVA/MVA: hourly funding rate for margin posted to ECC
        # Default ~50 bps annualized = 0.005 / (365*24) ≈ 5.7e-7, scaled up for significance
        self.margin_funding_rate = margin_funding_rate

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
        # Post-Audit V3: Convex LCOS + TURPE grid tariff
        scaled_kappa_0 = self.scaler.scale_difference(self.battery.lcos_kappa_0)
        scaled_kappa_1 = self.scaler.scale_difference(self.battery.lcos_kappa_1)
        scaled_grid_tariff = self.scaler.scale_difference(self.battery.grid_tariff_eur_mwh)
        scaled_alpha = self.scaler.scale_difference(self.alpha_slippage)

        profit = p_dis @ scaled_prices - p_ch @ scaled_prices

        # Convex LCOS: κ₀ * throughput (linear) + κ₁ * Σpower^1.5 (superlinear DoD penalty)
        # cp.power(x, 1.5) is convex for x >= 0, preserving DCP compliance.
        wear_linear = scaled_kappa_0 * cp.sum(p_ch + p_dis)  # type: ignore
        wear_convex = scaled_kappa_1 * cp.sum(  # type: ignore
            cp.power(p_ch, 1.5) + cp.power(p_dis, 1.5)  # type: ignore
        )

        # TURPE: fixed network access cost per MWh throughput
        grid_cost = scaled_grid_tariff * cp.sum(p_ch + p_dis)  # type: ignore

        slippage = scaled_alpha * cp.sum(cp.square(p_ch) + cp.square(p_dis))  # type: ignore

        # FVA/MVA: Margin funding cost on net position (Audit Faille 3.2)
        scaled_margin_rate = self.scaler.scale_difference(self.margin_funding_rate)
        margin_cost = scaled_margin_rate * cp.sum(cp.abs(p_dis - p_ch))  # type: ignore

        objective = cp.Maximize(profit - wear_linear - wear_convex - grid_cost - slippage - margin_cost)

        # 4. Physical Constraints (Linearized Digital Twin)
        constraints = []

        # Initial State
        constraints.append(soc[0] == self.battery.soc_mwh)

        # Precompute physical constants outside loop
        interlock_limit = max(self.battery.max_charge_mw, self.battery.max_discharge_mw)
        leakage_factor = 1.0 - self.battery.leakage_rate
        ch_eff = self.battery.efficiency_charge
        dis_eff = self.battery.efficiency_discharge

        for t in range(T):
            # Power Limits
            constraints.append(p_ch[t] <= self.battery.max_charge_mw)
            constraints.append(p_dis[t] <= self.battery.max_discharge_mw)

            # Physical Interlock: a single inverter cannot charge AND discharge simultaneously.
            # This linear constraint is DCP-compliant and preserves Kantorovich duality.
            constraints.append(p_ch[t] + p_dis[t] <= interlock_limit)

            # SOC Dynamics (efficiency & leakage)
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
        # Post-Audit V3: Convex LCOS + TURPE grid tariff (same as deterministic)
        scaled_kappa_0 = self.scaler.scale_difference(self.battery.lcos_kappa_0)
        scaled_kappa_1 = self.scaler.scale_difference(self.battery.lcos_kappa_1)
        scaled_grid_tariff = self.scaler.scale_difference(self.battery.grid_tariff_eur_mwh)
        scaled_alpha = self.scaler.scale_difference(self.alpha_slippage)

        wear_linear = scaled_kappa_0 * cp.sum(p_ch + p_dis)  # type: ignore
        wear_convex = scaled_kappa_1 * cp.sum(  # type: ignore
            cp.power(p_ch, 1.5) + cp.power(p_dis, 1.5)  # type: ignore
        )
        grid_cost = scaled_grid_tariff * cp.sum(p_ch + p_dis)  # type: ignore
        slippage_base = scaled_alpha * cp.sum(cp.square(p_ch) + cp.square(p_dis))  # type: ignore

        # FVA/MVA: Margin funding cost on net position (Audit Faille 3.2)
        scaled_margin_rate = self.scaler.scale_difference(self.margin_funding_rate)
        margin_cost = scaled_margin_rate * cp.sum(cp.abs(p_dis - p_ch))  # type: ignore

        # We want to maximize worst-case profit.
        # By strong duality, max_{Q} E_Q[Profit] = min_{lam, s} lam*eps + (1/N) sum(s)
        # Therefore, the objective of the overall problem is to Maximize this lower bound.
        # Loss L(u, xi) = (p_ch @ xi - p_dis @ xi) + costs
        # Primal: min_u max_Q E_Q[ L(u, xi) ]
        # Dual: min_{u, lam, s} lam * eps + 1/N * sum(s)

        objective = cp.Minimize(lam * epsilon + (1/N) * cp.sum(s))  # type: ignore
        constraints = []

        # Robust Dual Constraints with scenario-aware slippage (Audit Faille 2.1)
        # The slippage amplifier is proportional to each scenario's price deviation
        # from the mean, capturing liquidity co-movement with extreme prices.
        mean_scenario = np.mean(scaled_scenarios, axis=0)

        for i in range(N):
            # Per-scenario price deviation amplifies the slippage (capped at 2x)
            price_dev = np.sum(np.abs(scaled_scenarios[i] - mean_scenario))
            slippage_amplifier = min(2.0, 1.0 + 0.15 * price_dev)
            scenario_slippage = slippage_amplifier * slippage_base

            empirical_loss = (
                (p_ch @ scaled_scenarios[i] - p_dis @ scaled_scenarios[i])
                + wear_linear + wear_convex + grid_cost + scenario_slippage + margin_cost
            )
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
        interlock_limit = max(self.battery.max_charge_mw, self.battery.max_discharge_mw)
        leakage_factor = 1.0 - self.battery.leakage_rate
        ch_eff = self.battery.efficiency_charge
        dis_eff = self.battery.efficiency_discharge

        for t in range(T):
            constraints.append(p_ch[t] <= self.battery.max_charge_mw)
            constraints.append(p_dis[t] <= self.battery.max_discharge_mw)

            # Physical Interlock: prevent simultaneous charge + discharge
            constraints.append(p_ch[t] + p_dis[t] <= interlock_limit)

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
