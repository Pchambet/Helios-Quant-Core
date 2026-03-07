import pandas as pd
import numpy as np
import logging
from typing import TYPE_CHECKING, Any, Dict, List, Optional
from helios_core.assets.battery import BatteryAsset
from helios_core.simulate.agents import TradingAgent
from helios_core.simulate.metrics import RiskMetrics
from helios_core.stochastic.risk_manager import DynamicEpsilonManager
from helios_core.stochastic.price_forecaster import LightGBMPriceForecaster

if TYPE_CHECKING:
    from helios_core.stochastic.regime_detector import RegimeDetector

logger = logging.getLogger(__name__)

class WalkForwardBacktester:
    """
    Industrial Backtesting Engine for the Day-Ahead Market.
    Implements a 48h Receding Horizon with LightGBM tabular forecaster (Minimalisme Structurel).
    Executes trades in 24h blocks to mirror actual EPEX SPOT market mechanics.
    """
    def __init__(
        self,
        data: pd.DataFrame,
        agent: TradingAgent,
        metrics: RiskMetrics,
        physical_asset: BatteryAsset,
        risk_manager: Optional[DynamicEpsilonManager] = None,
        regime_detector: Optional["RegimeDetector"] = None,
        seed: Optional[int] = None,
    ):
        self.data = data
        self.agent = agent
        self.metrics = metrics
        self.physical_asset = physical_asset
        self.risk_manager = risk_manager
        self.regime_detector = regime_detector
        self.forecaster = LightGBMPriceForecaster(lookback_days=56)
        self.rng = np.random.default_rng(seed)

        # Causal RegimeDetector: fit par le backtester, jamais par le script externe
        self._regime_fitted_once = False
        self.burn_in_period = 168  # 7 jours minimum pour convergence HMM décente

        # State: SoC détenu par le physical_asset (SSOT — Points 6 & 11)
        self.history: List[Dict[str, Any]] = []

    def _build_causal_weather_forecast(self, t: int, horizon: int = 48) -> pd.DataFrame:
        """
        Construit un forecast météo par persistance (100% causal).
        Utilise exclusivement la fenêtre [t - horizon : t].
        """
        if t >= horizon:
            # On prend les 'horizon' dernières heures connues
            causal_forecast = self.data.iloc[t - horizon : t].copy()
        else:
            # Fallback pour le début du backtest (t < horizon)
            # On prend ce qui est disponible [0:t] et on le répète (tiling) pour atteindre l'horizon
            if t == 0:
                # Cas limite : t=0, on duplique la toute première ligne
                causal_forecast = pd.concat([self.data.iloc[[0]]] * horizon, ignore_index=False)
            else:
                available_data = self.data.iloc[0:t]
                repeats = (horizon // len(available_data)) + 1
                causal_forecast = pd.concat([available_data] * repeats, ignore_index=False).iloc[:horizon].copy()

        # Étape cruciale : On réindexe pour simuler une projection future [t : t + horizon]
        # Cela maintient la compatibilité avec la logique des agents (ex: RobustDROAgent)
        if (t + horizon) <= len(self.data):
            causal_forecast.index = self.data.index[t : t + horizon].copy()
        else:
            causal_forecast.index = pd.date_range(
                start=self.data.index[t], periods=horizon, freq="h"
            )

        return causal_forecast

    def run(self) -> dict[str, float]:
        prices = self.data['Price_EUR_MWh'].to_numpy(dtype=float)
        total_steps = len(prices)

        gross_revenue = 0.0
        gross_cost = 0.0
        throughput = 0.0

        # Phase 1 frictions (Brouillard de la Guerre) — coûts réels, pas la stress_penalty
        fee_buy = self.physical_asset.grid_fee_buy_eur_per_mwh
        fee_sell = self.physical_asset.grid_fee_sell_eur_per_mwh
        marginal_cost = self.physical_asset.marginal_cost_eur_per_mwh
        eta_dis = self.physical_asset.efficiency_discharge

        # ENTSO-E physical forecast error standard deviations (calibrated MW)
        PHYSICAL_NOISE_STD = {
            'Load_Forecast': 1000.0,       # ~1000 MW RMSE at 24-48h lead
            'Wind_Forecast': 500.0,        # ~500 MW RMSE at 24-48h lead
            'Solar_Forecast': 500.0,       # ~500 MW RMSE at 24-48h lead
            'Nuclear_Generation': 0.0      # Nuclear availability is known exactly Day-Ahead
        }

        # Step by 24h blocks (Day-Ahead Clearing)
        for t in range(0, total_steps, 24):
            # -- GESTION CAUSALE DU REGIME DETECTOR (Faille 4.2) --
            if self.regime_detector is not None and not self._regime_fitted_once:
                if t >= self.burn_in_period:
                    past_prices = self.data["Price_EUR_MWh"].iloc[:t]
                    logger.info(
                        f"Fitting RegimeDetector at t={t} with {len(past_prices)} past observations."
                    )
                    self.regime_detector.fit(past_prices)
                    self._regime_fitted_once = True

            # Post-Audit V2 (Faille 1.1): STRICT INFORMATION BARRIER
            realized_prices = prices[t : t + 24]  # Only used for PnL execution

            if len(realized_prices) < 24:
                # Discard incomplete final day
                break

            # Price forecast 48h (LightGBM — causal, features physiques)
            # Double Bouclier: forecast retourne (prices, cve) pour calibration ε dynamique
            past_data = self.data.iloc[:t]
            full_forecast, forecast_cve = self.forecaster.forecast(past_data, horizon=48)

            # 3. Agent Decision (Plans on 48h)
            # Causal forecast: persistance (Faille 1.3 — élimination du look-ahead).
            # Utilise uniquement [t - 48 : t], réindexé pour compatibilité agents.
            forecast_weather = self._build_causal_weather_forecast(t, horizon=48)

            # Application du bruit physique sur le forecast causal (erreur ECMWF simulée)
            for col, sigma in PHYSICAL_NOISE_STD.items():
                if col in forecast_weather.columns and sigma > 0.0:
                    noise = self.rng.normal(0, sigma, len(forecast_weather))
                    forecast_weather[col] = np.maximum(0, forecast_weather[col] + noise)

            # current_soc lu depuis le physical_asset (SSOT)
            current_soc = self.physical_asset.soc_mwh
            p_ch_vec, p_dis_vec, _ = self.agent.act(
                current_soc=current_soc,
                price_forecast=full_forecast,
                past_data=past_data,
                forecast_weather=forecast_weather,
                model_error=forecast_cve,
            )

            # 4. Partial Execution — le backtester applique les actions via BatteryAsset.step()
            for i in range(24):
                p_ch_req = p_ch_vec[i]
                p_dis_req = p_dis_vec[i]
                current_price = realized_prices[i]

                # Physique appliquée par BatteryAsset.step() — retourne (p_ch, p_dis) exécutés
                net_power = float(p_ch_req - p_dis_req)
                p_ch_now, p_dis_now = self.physical_asset.step(net_power, 1.0)

                # PnL sur puissances exécutées (fees asymétriques + usure linéaire)
                # stress_penalty_lambda : régularisation mathématique uniquement, pas de flux financier
                if p_ch_now > 0:
                    cost = p_ch_now * (current_price + fee_buy)
                    gross_cost += cost
                if p_dis_now > 0:
                    rev = p_dis_now * (current_price - fee_sell) * eta_dis
                    gross_revenue += rev

                wear_cost_t = (p_ch_now + p_dis_now) * marginal_cost
                gross_cost += wear_cost_t

                throughput += (p_ch_now + p_dis_now)

                # Log (valeurs exécutées pour cohérence PnL/SoC)
                self.history.append({
                    "time": self.data.index[t + i],
                    "price": current_price,
                    "p_ch": p_ch_now,
                    "p_dis": p_dis_now,
                    "soc": self.physical_asset.soc_mwh
                })

            if t % (24 * 10) == 0:
                logger.info(f"Backtesting Day {t//24}/{total_steps//24} completed.")

        return self.metrics.generate_report(gross_revenue, gross_cost, throughput)
