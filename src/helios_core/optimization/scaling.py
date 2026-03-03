import numpy as np
from typing import Optional

class PriceScaler:
    """
    Transforms and inverse-transforms empirical price arrays.
    Crucial for solver Numerical Armoring: Maps raw [-500, 9000] euro prices
    into a stable [-1, 1] range to avoid cvxpy INFEASIBLE or UNBOUNDED condition errors.
    """
    def __init__(self, target_range: tuple[float, float] = (-1.0, 1.0)):
        self.target_min, self.target_max = target_range
        self.data_min: Optional[float] = None
        self.data_max: Optional[float] = None

    def fit(self, X: np.ndarray) -> None:
        """
        Stores the absolute global min and max of the historical dataset.
        X shape: (N, Horizon) or (Horizon,)
        """
        self.data_min = float(np.min(X))
        self.data_max = float(np.max(X))

        if self.data_min == self.data_max:
            # Prevent pure zero division if prices are perfectly constant
            self.data_max += 1e-6

    def transform(self, X: np.ndarray) -> np.ndarray:
        """Applies the linear Min-Max mapping to target range."""
        if self.data_min is None or self.data_max is None:
            raise ValueError("Scaler must be fit before calling transform.")

        std_scale = (X - self.data_min) / (self.data_max - self.data_min)
        scaled_X = std_scale * (self.target_max - self.target_min) + self.target_min
        return scaled_X

    def fit_transform(self, X: np.ndarray) -> np.ndarray:
        self.fit(X)
        return self.transform(X)

    def inverse_transform(self, X_scaled: np.ndarray) -> np.ndarray:
        """Returns the scaled model outputs (like expected profit) back to absolute Euros."""
        if self.data_min is None or self.data_max is None:
            raise ValueError("Scaler must be fit before calling inverse_transform.")

        std_scale = (X_scaled - self.target_min) / (self.target_max - self.target_min)
        original_X = std_scale * (self.data_max - self.data_min) + self.data_min
        return original_X

    def scale_difference(self, diff: float) -> float:
        """
        Scales a pure difference (like a spread or a cost) into the scaled domain.
        Since scaled_X = (X - min)/(max - min) * (target_max - target_min) + target_min,
        the difference scaling is strictly linear without the affine offset.
        """
        if self.data_min is None or self.data_max is None:
            raise ValueError("Scaler must be fit before calling scale_difference.")

        scale_factor = (self.target_max - self.target_min) / (self.data_max - self.data_min)
        return float(diff * scale_factor)
