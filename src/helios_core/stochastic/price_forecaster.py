"""
LightGBMPriceForecaster — Capteur amélioré (Minimalisme Structurel).

Priorité aux features physiques. Zéro tuning. Robustesse d'abord.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

MIN_TRAIN_HOURS = 168  # 7 jours
PHYSICAL_COLS = ["Load_Forecast", "Wind_Forecast", "Solar_Forecast", "Nuclear_Generation"]


def _build_train_features(df: pd.DataFrame, idx: int) -> dict[str, float]:
    """Features causales pour entraînement (idx dans df)."""
    prices = df["Price_EUR_MWh"].values
    ts = df.index[idx]
    feat = {
        "hour_sin": np.sin(2 * np.pi * ts.hour / 24),
        "hour_cos": np.cos(2 * np.pi * ts.hour / 24),
        "dow_sin": np.sin(2 * np.pi * ts.dayofweek / 7),
        "dow_cos": np.cos(2 * np.pi * ts.dayofweek / 7),
        "price_lag_1": float(prices[idx - 1]) if idx >= 1 else float(prices[0]),
        "price_lag_24": float(prices[idx - 24]) if idx >= 24 else float(prices[max(0, idx - 1)]),
        "price_lag_48": float(prices[idx - 48]) if idx >= 48 else float(prices[max(0, idx - 24)]),
        "price_roll_mean_24": float(np.mean(prices[max(0, idx - 24) : idx])),
    }
    for col in PHYSICAL_COLS:
        key = col.lower() + "_lag_24"
        feat[key] = float(df[col].iloc[idx - 24]) if col in df.columns and idx >= 24 else 0.0
    return feat


def _build_pred_features(
    past_data: pd.DataFrame,
    n: int,
    h: int,
    pred_so_far: np.ndarray,
) -> dict[str, float]:
    """Features pour prédiction récursive de l'heure h."""
    prices = past_data["Price_EUR_MWh"].values
    ts = past_data.index[-1] + pd.Timedelta(hours=h + 1)
    feat = {
        "hour_sin": np.sin(2 * np.pi * ts.hour / 24),
        "hour_cos": np.cos(2 * np.pi * ts.hour / 24),
        "dow_sin": np.sin(2 * np.pi * ts.dayofweek / 7),
        "dow_cos": np.cos(2 * np.pi * ts.dayofweek / 7),
        "price_lag_1": pred_so_far[h - 1] if h >= 1 else float(prices[-1]),
        "price_lag_24": pred_so_far[h - 24] if h >= 24 else (float(prices[n - 24 + h]) if n - 24 + h >= 0 else float(prices[-1])),
        "price_lag_48": (pred_so_far[h - 48] if h >= 48 else float(prices[n - 48 + h]) if n - 48 + h >= 0 else float(prices[-1])),
    }
    if h >= 24:
        feat["price_roll_mean_24"] = float(np.mean(pred_so_far[h - 24 : h]))
    else:
        vals = list(prices[n - 24 + h : n]) + list(pred_so_far[:h]) if n - 24 + h < n else list(prices[n - 24 + h : n])
        feat["price_roll_mean_24"] = float(np.mean(vals)) if vals else feat["price_lag_1"]
    for col in PHYSICAL_COLS:
        key = col.lower() + "_lag_24"
        lag_idx = n - 24 + h if h < 24 else n - 24  # Persistance pour h>=24
        if col in past_data.columns and 0 <= lag_idx < n:
            feat[key] = float(past_data[col].iloc[lag_idx])
        else:
            feat[key] = float(past_data[col].iloc[-1]) if col in past_data.columns else 0.0
    return feat


ERROR_BUFFER_HOURS = 168  # 7 jours pour CVE glissant


class LightGBMPriceForecaster:
    """
    Forecaster tabulaire LightGBM (Minimalisme Structurel).
    Capture les corrélations physiques que la persistance ignore.

    Double Bouclier: expose CVE (Coefficient de Variation de l'Erreur) pour
    calibration dynamique de ε dans le Risk Manager.
    """
    def __init__(self, lookback_days: int = 56, error_buffer_hours: int = ERROR_BUFFER_HOURS):
        self.lookback_days = lookback_days
        self.error_buffer_hours = error_buffer_hours
        self._model: Any = None
        self._feature_names: Optional[list[str]] = None
        self._last_forecast: Optional[np.ndarray] = None
        self._error_buffer: list[tuple[float, float]] = []  # (pred, real)
        self._last_cve: float = 0.0

    def _compute_cve(self) -> float:
        """CVE = RMSE / mean(|y|) sur le buffer. 0 si buffer insuffisant."""
        if len(self._error_buffer) < 24:
            return 0.0
        preds = np.array([p for p, _ in self._error_buffer])
        reals = np.array([r for _, r in self._error_buffer])
        rmse = float(np.sqrt(np.mean((preds - reals) ** 2)))
        mean_abs_y = float(np.mean(np.abs(reals)))
        if mean_abs_y < 1e-6:
            return 0.0
        return rmse / mean_abs_y

    def _observe_realized(self, past_data: pd.DataFrame) -> None:
        """Compare la dernière prévision (24h) aux prix réalisés. Zéro look-ahead."""
        if self._last_forecast is None or len(past_data) < 24:
            return
        pred = self._last_forecast[:24]
        real = past_data["Price_EUR_MWh"].iloc[-24:].values
        for i in range(24):
            self._error_buffer.append((float(pred[i]), float(real[i])))
        max_len = self.error_buffer_hours
        if len(self._error_buffer) > max_len:
            self._error_buffer = self._error_buffer[-max_len:]

    def forecast(self, past_data: pd.DataFrame, horizon: int = 48) -> tuple[np.ndarray, float]:
        """Prévision causale sur horizon heures. Retourne (prices, cve)."""
        if "Price_EUR_MWh" not in past_data.columns:
            raise ValueError("past_data must contain 'Price_EUR_MWh'")

        n = len(past_data)
        # Double Bouclier: mise à jour causale du buffer (prédictions vs réalité)
        # Look-ahead safe: on compare la dernière prévision (24h) aux prix réalisés
        self._observe_realized(past_data)
        cve = self._compute_cve()

        if n < MIN_TRAIN_HOURS:
            return self._fallback_persistence(past_data, horizon)

        try:
            import lightgbm as lgb  # type: ignore
        except ImportError:
            logger.warning("lightgbm not installed. Fallback to persistence.")
            return self._fallback_persistence(past_data, horizon)

        lookback = self.lookback_days * 24
        start = max(0, n - lookback)
        history = past_data.iloc[start:].copy()

        X_list, y_list = [], []
        for i in range(48, len(history)):
            feats = _build_train_features(history, i)  # i = position dans history
            X_list.append(feats)
            y_list.append(history["Price_EUR_MWh"].iloc[i])

        if len(X_list) < 24:
            return self._fallback_persistence(past_data, horizon)

        X_train = pd.DataFrame(X_list)
        y_train = np.array(y_list)
        self._feature_names = list(X_train.columns)

        try:
            fitted_model = lgb.LGBMRegressor(
                n_estimators=80,
                max_depth=5,
                learning_rate=0.1,
                random_state=42,
                verbose=-1,
            )
            fitted_model.fit(X_train, y_train)
            self._model = fitted_model
        except Exception as e:
            logger.warning(f"LightGBM fit failed: {e}. Fallback to persistence.")
            return self._fallback_persistence(past_data, horizon)

        predictions = np.zeros(horizon)
        for h in range(horizon):
            feats = _build_pred_features(past_data, n, h, predictions)
            row = pd.DataFrame([feats])
            for c in self._feature_names:
                if c not in row.columns:
                    row[c] = 0.0
            pred = self._model.predict(row[self._feature_names])[0]
            predictions[h] = np.clip(float(pred), -500.0, 3000.0)

        self._last_forecast = predictions.copy()
        self._last_cve = cve
        return predictions.astype(np.float64), cve

    def _fallback_persistence(self, past_data: pd.DataFrame, horizon: int) -> tuple[np.ndarray, float]:
        """Répète les dernières 24h. CVE=0 (pas de métrique instrumentale)."""
        prices = past_data["Price_EUR_MWh"].values
        if len(prices) >= 24:
            last = prices[-24:]
        else:
            arr_prices = np.asarray(prices, dtype=np.float64)
            last = np.full(24, float(np.mean(arr_prices)) if len(arr_prices) > 0 else 50.0)
        arr = np.tile(last, (horizon // 24) + 1)[:horizon].astype(np.float64)
        self._last_forecast = arr.copy()
        self._last_cve = 0.0
        return arr, 0.0
