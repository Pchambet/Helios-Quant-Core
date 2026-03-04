import numpy as np
from typing import Optional

class PriceScaler:
    """
    Transforms and inverse-transforms empirical price arrays.
    Crucial for solver Numerical Armoring: Maps raw [-500, 9000] euro prices
    into a stable [-1, 1] range to avoid cvxpy INFEASIBLE or UNBOUNDED condition errors.
    Uses MaxAbs scaling to strictly preserve the "zero" crossing (preventing phantom objective rewards).
    """
    def __init__(self, target_max: float = 1.0):
        self.target_max = target_max
        self.data_max_abs: Optional[float] = None

    def fit(self, X: np.ndarray) -> None:
        """
        Stores the absolute global max of the historical dataset.
        X shape: (N, Horizon) or (Horizon,)
        """
        self.data_max_abs = float(np.max(np.abs(X)))

        if self.data_max_abs < 1e-6:
            # Prevent pure zero division if prices are perfectly constant zero
            self.data_max_abs = 1e-6

    def transform(self, X: np.ndarray) -> np.ndarray:
        """Applies the linear MaxAbs mapping."""
        if self.data_max_abs is None:
            raise ValueError("Scaler must be fit before calling transform.")

        return X * (self.target_max / self.data_max_abs)

    def fit_transform(self, X: np.ndarray) -> np.ndarray:
        self.fit(X)
        return self.transform(X)

    def inverse_transform(self, X_scaled: np.ndarray) -> np.ndarray:
        """Returns the scaled model outputs (like expected profit) back to absolute Euros."""
        if self.data_max_abs is None:
            raise ValueError("Scaler must be fit before calling inverse_transform.")

        return X_scaled * (self.data_max_abs / self.target_max)

    def scale_difference(self, diff: float) -> float:
        """
        Scales a pure difference (like a spread or a cost) into the scaled domain.
        """
        if self.data_max_abs is None:
            raise ValueError("Scaler must be fit before calling scale_difference.")

        return float(diff * (self.target_max / self.data_max_abs))
