from helios_core.assets.config import BatteryConfig

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

        if config.initial_soc_mwh > config.capacity_mwh:
            raise PhysicalConstraintError(f"Initial SoC {config.initial_soc_mwh} exceeds capacity {config.capacity_mwh}.")
        self.soc_mwh = config.initial_soc_mwh

    def step(self, power_mw: float, duration_hours: float) -> None:
        """
        Updates the state of charge (SoC) applying a constant power over a duration.
        - power_mw > 0 : Charging
        - power_mw < 0 : Discharging
        Raises PhysicalConstraintError if the command violates constraints.
        """
        if duration_hours <= 0:
            raise ValueError("Duration must be strictly positive.")

        # 1. Check Power Constraints (MW)
        if power_mw > 0 and power_mw > self.max_charge_mw:
            raise PhysicalConstraintError(
                f"Requested charge {power_mw} MW exceeds max {self.max_charge_mw} MW."
            )
        if power_mw < 0 and abs(power_mw) > self.max_discharge_mw:
            raise PhysicalConstraintError(
                f"Requested discharge {abs(power_mw)} MW exceeds max {self.max_discharge_mw} MW."
            )

        # 2. Account for internal leakage over the duration
        self.soc_mwh = self.soc_mwh * ((1 - self.leakage_rate) ** duration_hours)

        # 3. Calculate internal Energy Change (MWh) accounting for efficiency
        if power_mw > 0:
            energy_change_internal = power_mw * duration_hours * self.efficiency_charge
        else:
            # Power is negative. To deliver X MWh to grid, we need to extract X/eff from battery.
            energy_change_internal = (power_mw * duration_hours) / self.efficiency_discharge

        new_soc = self.soc_mwh + energy_change_internal

        # 4. Check Energy Constraints (MWh)
        if new_soc > self.capacity_mwh + 1e-9:  # Float tolerance
            raise PhysicalConstraintError(
                f"Attempt to charge beyond capacity. Requested SoC: {new_soc:.3f}, Max: {self.capacity_mwh}"
            )
        if new_soc < -1e-9:
             raise PhysicalConstraintError(
                f"Attempt to over-discharge. Requested SoC: {new_soc:.3f}, Min: 0.0"
            )

        # 5. Commit state change
        self.soc_mwh = max(0.0, min(self.capacity_mwh, new_soc))
