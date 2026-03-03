import pytest
from helios_core.assets.battery import BatteryAsset, PhysicalConstraintError


def test_battery_initialization() -> None:
    # Valid
    battery = BatteryAsset(capacity_mwh=10, max_charge_mw=5, max_discharge_mw=5)
    assert battery.capacity_mwh == 10
    assert battery.soc_mwh == 0.0

    # Invalid Negative Capacity
    with pytest.raises(ValueError, match="strictly positive"):
        BatteryAsset(capacity_mwh=-5, max_charge_mw=5, max_discharge_mw=5)

    # Invalid efficiency
    with pytest.raises(ValueError, match="Efficiency"):
        BatteryAsset(capacity_mwh=10, max_charge_mw=5, max_discharge_mw=5, efficiency_charge=1.2)


def test_charge_within_limits() -> None:
    battery = BatteryAsset(capacity_mwh=10, max_charge_mw=5, max_discharge_mw=5, efficiency_charge=0.9)
    # Charge at 5MW for 1 hour -> 5MWh delivered to battery. Internal SoC increase = 5 * 0.9 = 4.5 MWh
    battery.step(power_mw=5.0, duration_hours=1.0)
    assert battery.soc_mwh == 4.5


def test_discharge_within_limits() -> None:
    battery = BatteryAsset(capacity_mwh=10, max_charge_mw=5, max_discharge_mw=5, efficiency_discharge=0.9, initial_soc_mwh=10.0)
    # Discharge at 4.5MW for 1 hour -> 4.5MWh delivered to grid.
    # Leakage is applied first: 10 * (1 - 0.001) = 9.99
    # Then discharge 5 MWh. So 9.99 - 5.0 = 4.99
    battery.step(power_mw=-4.5, duration_hours=1.0)
    assert round(battery.soc_mwh, 3) == 4.99



def test_power_constraint_violation() -> None:
    battery = BatteryAsset(capacity_mwh=10, max_charge_mw=5, max_discharge_mw=5)

    # Exceeding Charge Power
    with pytest.raises(PhysicalConstraintError, match="exceeds max"):
        battery.step(power_mw=6.0, duration_hours=1.0)

    # Exceeding Discharge Power
    with pytest.raises(PhysicalConstraintError, match="exceeds max"):
        battery.step(power_mw=-6.0, duration_hours=1.0)


def test_energy_constraint_violation_overcharge() -> None:
    battery = BatteryAsset(capacity_mwh=10, max_charge_mw=15, max_discharge_mw=15, efficiency_charge=1.0)

    # Charging 12 MWh when capacity is 10 MWh
    with pytest.raises(PhysicalConstraintError, match="Attempt to charge beyond capacity"):
        battery.step(power_mw=12.0, duration_hours=1.0)

def test_energy_constraint_violation_overdischarge() -> None:
    battery = BatteryAsset(capacity_mwh=10, max_charge_mw=15, max_discharge_mw=15, efficiency_discharge=1.0, initial_soc_mwh=5.0)

    # Discharging 6 MWh when SoC is only 5 MWh
    with pytest.raises(PhysicalConstraintError, match="Attempt to over-discharge"):
        battery.step(power_mw=-6.0, duration_hours=1.0)

def test_leakage() -> None:
    battery = BatteryAsset(capacity_mwh=10, max_charge_mw=5, max_discharge_mw=5, leakage_rate_per_hour=0.01, initial_soc_mwh=10.0)
    # Idle for 1 hour
    battery.step(power_mw=0.0, duration_hours=1.0)
    assert battery.soc_mwh == 9.9
