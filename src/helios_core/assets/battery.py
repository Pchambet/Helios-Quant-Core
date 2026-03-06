from helios_core.assets.config import BatteryConfig

# Tolérance numérique pour absorber les imprécisions du solveur CVXPY (OSQP/ECOS).
# En deçà : écrêtage silencieux. Au-delà : PhysicalConstraintError (faille logique).
TOLERANCE_SOC_MWH = 1e-4
TOLERANCE_POWER_MW = 1e-4


class PhysicalConstraintError(Exception):
    """Exception raised when an action violates the physical laws of the asset."""
    pass

class BatteryAsset:
    """
    Digital Twin of a Battery Storage System.
    Enforces strict physical limits (Energy, Power, Efficiency, Leakage).
    """

    def __init__(self, config: BatteryConfig):
        self.capacity_mwh = config.capacity_mwh
        self.max_charge_mw = config.max_charge_mw
        self.max_discharge_mw = config.max_discharge_mw
        self.efficiency_charge = config.efficiency_charge
        self.efficiency_discharge = config.efficiency_discharge
        self.leakage_rate = config.leakage_rate_per_hour

        self.capex_eur = config.capex_eur
        self.cycle_life = config.cycle_life
        self.grid_tariff_eur_mwh = config.grid_tariff_eur_mwh

        if config.initial_soc_mwh > config.capacity_mwh:
            raise PhysicalConstraintError(f"Initial SoC {config.initial_soc_mwh} exceeds capacity {config.capacity_mwh}.")
        self.soc_mwh = config.initial_soc_mwh

    @property
    def marginal_wear_cost_per_mwh(self) -> float:
        """
        Calculates the Levelized Cost of Storage (LCOS) for marginal degradation.
        A full cycle represents 1 MWh charged and 1 MWh discharged (throughput = 2 MWh).
        Returns the EUR cost strictly linear to the energy throughput.
        """
        total_throughput_mwh = self.cycle_life * self.capacity_mwh * 2.0
        return self.capex_eur / total_throughput_mwh

    @property
    def lcos_kappa_0(self) -> float:
        """Base linear wear cost (EUR/MWh throughput). ~85% of total LCOS."""
        return self.marginal_wear_cost_per_mwh * 0.85

    @property
    def lcos_kappa_1(self) -> float:
        """Superlinear DoD-dependent wear cost coefficient (EUR/MW^1.5). ~15% of total LCOS."""
        return self.marginal_wear_cost_per_mwh * 0.15

    def step(
        self, power_mw: float, duration_hours: float
    ) -> tuple[float, float]:
        """
        Updates the state of charge (SoC) applying a constant power over a duration.

        - power_mw > 0 : Charging
        - power_mw < 0 : Discharging

        Tolérance numérique : écrêtage silencieux si violation < TOLERANCE_*
        (imprécisions solveur CVXPY). PhysicalConstraintError si violation > tolérance.

        Dégradation gracieuse : si le plan MPC diverge (ex. open-loop drift), on écrête
        la puissance au maximum physiquement réalisable au lieu de crasher.

        Returns:
            (p_ch_executed, p_dis_executed) en MW pour PnL correct.
        """
        if duration_hours <= 0:
            raise ValueError("Duration must be strictly positive.")

        # 1. Écrêtage puissance (solveur peut retourner 5.0000001 quand max=5)
        if power_mw > 0:
            if power_mw > self.max_charge_mw + TOLERANCE_POWER_MW:
                raise PhysicalConstraintError(
                    f"Requested charge {power_mw:.4f} MW exceeds max {self.max_charge_mw} MW."
                )
            power_mw = min(power_mw, self.max_charge_mw)
        elif power_mw < 0:
            abs_p = abs(power_mw)
            if abs_p > self.max_discharge_mw + TOLERANCE_POWER_MW:
                raise PhysicalConstraintError(
                    f"Requested discharge {abs_p:.4f} MW exceeds max {self.max_discharge_mw} MW."
                )
            power_mw = -min(abs_p, self.max_discharge_mw)

        # 2. Account for internal leakage over the duration
        self.soc_mwh = self.soc_mwh * ((1 - self.leakage_rate) ** duration_hours)

        # 3. Calculate internal Energy Change (MWh) — cohérent avec _build_physical_constraints
        if power_mw > 0:
            energy_change_internal = power_mw * duration_hours * self.efficiency_charge
        else:
            energy_change_internal = (power_mw * duration_hours) / self.efficiency_discharge

        new_soc = self.soc_mwh + energy_change_internal

        # 4. Contraintes énergie : écrêtage silencieux (< tolérance) ou dégradation gracieuse
        if new_soc > self.capacity_mwh + TOLERANCE_SOC_MWH:
            raise PhysicalConstraintError(
                f"Attempt to charge beyond capacity. Requested SoC: {new_soc:.3f}, Max: {self.capacity_mwh}"
            )

        if new_soc < -TOLERANCE_SOC_MWH:
            # Dégradation gracieuse : divergence MPC open-loop vs physique réelle.
            # On écrête au max extractible (SoC → 0) au lieu de crasher.
            max_extract_mwh = self.soc_mwh
            max_discharge_mw = max_extract_mwh * self.efficiency_discharge / duration_hours
            max_discharge_mw = min(max_discharge_mw, self.max_discharge_mw)
            power_mw = -max_discharge_mw
            new_soc = 0.0

        elif new_soc > self.capacity_mwh:
            # Sur-charge (bande tolérance ou dégradation) : écrêtage au max storable
            max_store_mwh = self.capacity_mwh - self.soc_mwh
            max_charge_mw = max_store_mwh / (duration_hours * self.efficiency_charge)
            max_charge_mw = min(max_charge_mw, self.max_charge_mw)
            power_mw = max_charge_mw
            new_soc = self.capacity_mwh

        # 5. Commit state change
        self.soc_mwh = max(0.0, min(self.capacity_mwh, new_soc))

        # 6. Retour pour PnL (backtester utilise les MW effectivement exécutés)
        if power_mw >= 0:
            return (power_mw, 0.0)
        return (0.0, abs(power_mw))
