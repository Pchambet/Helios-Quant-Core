"""
BenchmarkRunner: orchestration unifiée des backtests comparatifs.
Élimine la duplication entre run_benchmark.py et run_normal_benchmark.py (Point 9).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import matplotlib.pyplot as plt
import pandas as pd

from helios_core.assets.battery import BatteryAsset
from helios_core.assets.config import BatteryConfig
from helios_core.data.entsoe_loader import HistoricalCrisisLoader
from helios_core.optimization.controller import BatteryMPC
from helios_core.optimization.scaling import PriceScaler
from helios_core.simulate.agents import (
    DeterministicMPCAgent,
    NaiveHeuristicAgent,
    RobustDROAgent,
)
from helios_core.simulate.backtester import WalkForwardBacktester
from helios_core.simulate.metrics import RiskMetrics
from helios_core.stochastic.config import StochasticConfig
from helios_core.stochastic.generator import ScenarioGenerator
from helios_core.stochastic.regime_detector import RegimeDetector
from helios_core.stochastic.risk_manager import DynamicEpsilonManager
from helios_core.utils.paths import ensure_reports_dir

if TYPE_CHECKING:
    from helios_core.simulate.agents import TradingAgent

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BenchmarkPreset:
    """Préréglage de benchmark (crise, normal, custom)."""

    start_date: str
    end_date: str
    title: str
    price_label: str
    market_subtitle: str
    output_filename: str


PRESETS: dict[str, BenchmarkPreset] = {
    "crisis": BenchmarkPreset(
        start_date="2022-08-01",
        end_date="2022-08-31",
        title="EPOCH 2022 CRISIS BENCHMARK",
        price_label="EPEX SPOT (Aug 2022 Crisis)",
        market_subtitle="The August 2022 Energy Shock",
        output_filename="benchmark_august_2022.png",
    ),
    "normal": BenchmarkPreset(
        start_date="2023-05-01",
        end_date="2023-05-31",
        title="EPOCH 2023 NORMAL BENCHMARK",
        price_label="EPEX SPOT (May 2023)",
        market_subtitle="May 2023 (Normal Conditions)",
        output_filename="benchmark_may_2023.png",
    ),
}


# Constantes partagées (Twin physique)
CAPEX = 300_000.0
CYCLES = 5000
CAPACITY = 10.0
MARGINAL_LCOS = CAPEX / (CYCLES * CAPACITY * 2.0)


class BenchmarkRunner:
    """
    Exécute un benchmark comparatif Naive / Deterministic MPC / Robust DRO.
    Paramétrable par preset (crisis, normal) ou dates custom.
    """

    def __init__(
        self,
        preset: str = "crisis",
        start_date: str | None = None,
        end_date: str | None = None,
        seed: int = 42,
        mock: bool = False,
        model_gamma: float = 0.5,
        use_frictions: bool = False,
    ) -> None:
        if preset in PRESETS:
            p = PRESETS[preset]
            self.start_date = p.start_date
            self.end_date = p.end_date
            self.title = p.title
            self.price_label = p.price_label
            self.market_subtitle = p.market_subtitle
            self.output_filename = p.output_filename
        else:
            if not start_date or not end_date:
                raise ValueError(
                    f"Unknown preset '{preset}'. Use --start and --end for custom."
                )
            self.start_date = start_date
            self.end_date = end_date
            self.title = f"BENCHMARK {start_date} — {end_date}"
            self.price_label = f"EPEX SPOT ({start_date})"
            self.market_subtitle = f"{start_date} — {end_date}"
            self.output_filename = f"benchmark_{start_date}_{end_date}.png"

        self.seed = seed
        self.mock = mock
        self.model_gamma = model_gamma
        self.use_frictions = use_frictions

    def run(self) -> dict[str, dict[str, float]]:
        """Exécute le benchmark et retourne les résultats par agent."""
        print(f"\n{'='*60}")
        title_suffix = " [FRICTIONNÉ]" if self.use_frictions else ""
        print(f" HELIOS-QUANT-CORE : {self.title}{title_suffix} ")
        print(f"{'='*60}\n")

        # 1. Chargement
        loader = HistoricalCrisisLoader(
            start_date=self.start_date, end_date=self.end_date
        )
        df = loader.fetch_data(mock=self.mock)
        print(
            f"[DATA] Loaded {len(df)} hourly observations "
            f"from {df.index[0]} to {df.index[-1]}."
        )
        print(f"[DATA] Maximum Extreme Price: {df['Price_EUR_MWh'].max():.2f} EUR/MWh\n")

        # 2. Twin & métriques
        if self.use_frictions:
            config = BatteryConfig(
                capacity_mwh=CAPACITY,
                max_charge_mw=5.0,
                max_discharge_mw=5.0,
                efficiency_charge=0.95,
                efficiency_discharge=0.95,
                capex_eur=CAPEX,
                cycle_life=CYCLES,
                marginal_cost_eur_per_mwh=15.0,
                grid_fee_buy_eur_per_mwh=2.0,
                grid_fee_sell_eur_per_mwh=2.0,
                stress_penalty_lambda=30.0,
            )
            print("[Twin] Frictions activées: LCOS 15 €/MWh, Frais 2 €/MWh, λ_stress=30 (Brouillard de la Guerre)\n")
        else:
            config = BatteryConfig(
                capacity_mwh=CAPACITY,
                max_charge_mw=5.0,
                max_discharge_mw=5.0,
                efficiency_charge=0.95,
                efficiency_discharge=0.95,
                capex_eur=CAPEX,
                cycle_life=CYCLES,
            )
        metrics = RiskMetrics(
            capex_eur=CAPEX, cycle_life=CYCLES, capacity_mwh=CAPACITY
        )
        print(f"[Twin] Marginal LCOS: {metrics.marginal_lcos:.2f} EUR/MWh throughput.\n")

        # 3. Agents
        print("[INIT] Booting Walk-Forward Engines (Horizon: 24h)...")
        naive_agent = NaiveHeuristicAgent(max_charge=5.0, max_discharge=5.0)

        det_scaler = PriceScaler()
        det_mpc = BatteryMPC(BatteryAsset(config), det_scaler, alpha_slippage=5.0)
        det_agent = DeterministicMPCAgent(det_mpc)

        stoch_config = StochasticConfig(
            n_scenarios=30, horizon_hours=48, noise_multiplier=0.0
        )
        dro_generator = ScenarioGenerator(stoch_config, seed=self.seed)
        dro_scaler = PriceScaler()
        dro_mpc = BatteryMPC(
            BatteryAsset(config), dro_scaler,
            alpha_slippage=1.5, margin_funding_rate=5e-7
        )
        dynamic_risk_manager = DynamicEpsilonManager(
            eps_min=0.02, eps_max=0.30,
            eps_nominal=0.12, eps_n_ref=30,
            entropy_beta=0.5,
            model_gamma=self.model_gamma,
        )
        regime_detector = RegimeDetector(n_regimes=3, lookback_days=7)
        dro_agent = RobustDROAgent(
            dro_mpc, epsilon=0.5, generator=dro_generator,
            risk_manager=dynamic_risk_manager, regime_detector=regime_detector,
            seed=self.seed
        )

        agents: dict[str, TradingAgent] = {
            "Naive Heuristic": naive_agent,
            "Deterministic MPC": det_agent,
            "Robust DRO (L1)": dro_agent,
        }
        physical_assets = {
            "Naive Heuristic": BatteryAsset(config),
            "Deterministic MPC": det_mpc.battery,
            "Robust DRO (L1)": dro_mpc.battery,
        }

        # 4. Backtests
        results: dict[str, dict[str, float]] = {}
        history_dfs: dict[str, pd.DataFrame] = {}

        for name, agent in agents.items():
            logger.info(f"Running {name}...")
            regime_det = regime_detector if isinstance(agent, RobustDROAgent) else None
            tester = WalkForwardBacktester(
                df, agent, metrics,
                physical_asset=physical_assets[name],
                regime_detector=regime_det,
                seed=self.seed,
            )
            report = tester.run()
            results[name] = report
            history_dfs[name] = pd.DataFrame(tester.history).set_index("time")

        # 5. Tear sheet console
        self._print_tear_sheet(results)

        # 6. Tear sheet visuel
        self._generate_visual_tear_sheet(df, history_dfs)

        return results

    def _print_tear_sheet(self, results: dict[str, dict[str, float]]) -> None:
        print("\n" + "="*80)
        print(f"{'AGENT':<25} | {'NET PNL (€)':<12} | {'CYCLES (EFC)':<12} | {'RoDC (Ratio)':<12}")
        print("-" * 80)
        for name, res in results.items():
            net = res["Net Adjusted PnL (EUR)"]
            efc = res["EFC (Cycles)"]
            rodc = res["RoDC (Ratio)"]
            print(f"{name:<25} | {net:<12.2f} | {efc:<12.2f} | {rodc:<12.2f}")
        print("="*80 + "\n")

    def _generate_visual_tear_sheet(
        self, df: pd.DataFrame, history_dfs: dict[str, pd.DataFrame]
    ) -> None:
        plt.style.use("dark_background")
        fig, (ax1, ax2, ax3) = plt.subplots(
            3, 1, figsize=(14, 12), sharex=True,
            gridspec_kw={"height_ratios": [2, 2, 1.5]}
        )

        ax1.plot(
            df.index, df["Price_EUR_MWh"],
            color="cyan", linewidth=1, alpha=0.9, label=self.price_label
        )
        ax1.set_title(f"Market Environment: {self.market_subtitle}", fontsize=14, pad=15)
        ax1.set_ylabel("Price (€ / MWh)")
        ax1.grid(True, alpha=0.2)
        ax1.legend(loc="upper left")

        colors = {
            "Naive Heuristic": "gray",
            "Deterministic MPC": "red",
            "Robust DRO (L1)": "green",
        }
        for name, hist in history_dfs.items():
            hist = hist.copy()
            hist["gross_rev"] = hist["p_dis"] * hist["price"] * 0.95
            hist["gross_cost"] = hist["p_ch"] * hist["price"]
            throughput = hist["p_ch"] + hist["p_dis"]
            hist["wear"] = throughput * MARGINAL_LCOS
            hist["net_step_pnl"] = hist["gross_rev"] - hist["gross_cost"] - hist["wear"]
            hist["cum_pnl"] = hist["net_step_pnl"].cumsum()
            ax2.plot(
                hist.index, hist["cum_pnl"],
                color=colors[name], linewidth=2, label=name
            )

        ax2.set_title("Cumulative Net Adjusted PnL (Post-LCOS Degradation)", fontsize=14)
        ax2.set_ylabel("Cumulative €")
        ax2.grid(True, alpha=0.2)
        ax2.legend(loc="upper left")

        ax3.plot(
            history_dfs["Deterministic MPC"].index,
            history_dfs["Deterministic MPC"]["soc"],
            color="red", linewidth=1, alpha=0.7, label="Deterministic SoC"
        )
        ax3.plot(
            history_dfs["Robust DRO (L1)"].index,
            history_dfs["Robust DRO (L1)"]["soc"],
            color="green", linewidth=1.5, alpha=0.9, label="DRO SoC"
        )
        ax3.set_title(
            "Asset Preservation: Deterministic vs DRO Discipline", fontsize=12
        )
        ax3.set_ylabel("SoC (MWh)")
        ax3.set_xlabel("Time (Hourly Walk-Forward)")
        ax3.grid(True, alpha=0.2)
        ax3.legend(loc="upper left")

        plt.tight_layout()
        out_path = ensure_reports_dir() / self.output_filename
        fig.savefig(out_path, dpi=300, bbox_inches="tight")
        logger.info(f"Visual Tear Sheet exported to {out_path}")
