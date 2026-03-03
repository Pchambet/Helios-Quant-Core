from pydantic import BaseModel, Field

class BatteryConfig(BaseModel):
    """Strict configuration model for a Battery Asset."""
    capacity_mwh: float = Field(..., gt=0, description="Maximum energy capacity.")
    max_charge_mw: float = Field(..., ge=0, description="Max charging power.")
    max_discharge_mw: float = Field(..., ge=0, description="Max discharging power.")
    efficiency_charge: float = Field(default=0.95, gt=0, le=1.0, description="Charging efficiency.")
    efficiency_discharge: float = Field(default=0.95, gt=0, le=1.0, description="Discharging efficiency.")
    leakage_rate_per_hour: float = Field(default=0.001, ge=0, description="Energy lost per idle hour.")
    initial_soc_mwh: float = Field(default=0.0, ge=0, description="Initial state of charge.")
