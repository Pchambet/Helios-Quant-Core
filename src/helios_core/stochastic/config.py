from pydantic import BaseModel, Field

class StochasticConfig(BaseModel):
    """Configuration model for generating empirical scenarios."""
    n_scenarios: int = Field(default=100, gt=0, description="Total number of historical scenarios to sample.")
    horizon_hours: int = Field(default=24, gt=0, description="Length of each scenario in hours.")
    noise_multiplier: float = Field(default=0.0, ge=0.0, description="Gaussian noise multiplier to emulate shocks on top of history (0.0 = pure empirical).")
