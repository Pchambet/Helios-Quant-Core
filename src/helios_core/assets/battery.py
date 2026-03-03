class PhysicalConstraintError(Exception):
    """Exception raised when an action violates the physical laws of the asset."""
    pass

class BatteryAsset:
    """
    Digital Twin of a Battery Storage System.
    Enforces strict physical limits (Energy, Power, Efficiency, Leakage).
    """

    def __init__(
        self,
        capacity_mwh: float,
        max_charge_mw: float,
        max_discharge_mw: float,
        efficiency_charge: float = 0.95,
        efficiency_discharge: float = 0.95,
        leakage_rate_per_hour: float = 0.001,
        initial_soc_mwh: float = 0.0,
    ):
        if capacity_mwh <= 0:
            raise ValueError("Battery capacity must be strictly positive.")
        if max_charge_mw < 0 or max_discharge_mw < 0:
            raise ValueError("Power limits must be non-negative.")
        if not (0 < efficiency_charge <= 1) or not (0 < efficiency_discharge <= 1):
            raise ValueError("Efficiency must be in (0, 1].")

        self.capacity_mwh = capacity_mwh
        self.max_charge_mw = max_charge_mw
        self.max_discharge_mw = max_discharge_mw
        self.efficiency_charge = efficiency_charge
        self.efficiency_discharge = efficiency_discharge
        self.leakage_rate = leakage_rate_per_hour
        
        if initial_soc_mwh < 0 or initial_soc_mwh > capacity_mwh:
            raise ValueError("Initial SoC must be within [0, capacity].")
        self.soc_mwh = initial_soc_mwh

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
