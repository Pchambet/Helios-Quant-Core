import os
import matplotlib.pyplot as plt
import pandas as pd
import logging

from helios_core.data.entsoe_loader import HistoricalCrisisLoader
from helios_core.assets.config import BatteryConfig
from helios_core.assets.battery import BatteryAsset
from helios_core.optimization.scaling import PriceScaler
from helios_core.optimization.controller import BatteryMPC
from helios_core.simulate.metrics import RiskMetrics
from helios_core.simulate.backtester import WalkForwardBacktester
from helios_core.simulate.agents import NaiveHeuristicAgent, DeterministicMPCAgent, RobustDROAgent
from helios_core.stochastic.risk_manager import DynamicEpsilonManager
from helios_core.stochastic.generator import ScenarioGenerator
from helios_core.stochastic.config import StochasticConfig

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

def main() -> None:
    print("\n============================================================")
    print(" HELIOS-QUANT-CORE : EPOCH 2023 NORMAL BENCHMARK ")
    print("============================================================\n")

    # 1. Load the immutable dataset
    loader = HistoricalCrisisLoader(start_date="2023-05-01", end_date="2023-05-31")
    df = loader.fetch_data()
    print(f"[DATA] Loaded {len(df)} hourly observations from {df.index[0]} to {df.index[-1]}.")
    print(f"[DATA] Maximum Extreme Price observed: {df['Price_EUR_MWh'].max():.2f} EUR/MWh\n")

    # 2. Institutional Digital Twin Setup
    capex = 300_000.0
    cycles = 5000
    capacity = 10.0

    config = BatteryConfig(
        capacity_mwh=capacity,
        max_charge_mw=5.0,
        max_discharge_mw=5.0,
        efficiency_charge=0.95,
        efficiency_discharge=0.95,
        capex_eur=capex,
        cycle_life=cycles
    )

    metrics = RiskMetrics(capex_eur=capex, cycle_life=cycles, capacity_mwh=capacity)
    print(f"[Twin] Marginal Levelized Cost of Storage: {metrics.marginal_lcos:.2f} EUR/MWh throughput.\n")

    # 3. Instantiate Gladiators
    print("[INIT] Booting Walk-Forward Engines (Horizon: 24h)...")

    # - Naive
    naive_agent = NaiveHeuristicAgent(max_charge=5.0, max_discharge=5.0)

    # - Deterministic
    det_scaler = PriceScaler()
    det_mpc = BatteryMPC(BatteryAsset(config), det_scaler, alpha_slippage=5.0)
    det_agent = DeterministicMPCAgent(det_mpc)

    # - Robust DRO
    stoch_config = StochasticConfig(n_scenarios=30, horizon_hours=48, noise_multiplier=0.0)
    dro_generator = ScenarioGenerator(stoch_config)

    dro_scaler = PriceScaler()
    dro_mpc = BatteryMPC(BatteryAsset(config), dro_scaler, alpha_slippage=1.5, margin_funding_rate=5e-7)

    # Post-Audit V4: Epsilon bounds recalibrated for intra-cluster dispersion (10-150)
    dynamic_risk_manager = DynamicEpsilonManager(
        eps_min=0.02,
        eps_max=0.30,
        vol_min_expected=10.0,
        vol_max_expected=80.0
    )

    # Post-Audit V4: RegimeDetector for KNN filtering by market state
    from helios_core.stochastic.regime_detector import RegimeDetector
    regime_detector = RegimeDetector(n_regimes=3, lookback_days=7)
    regime_detector.fit(df['Price_EUR_MWh'])

    dro_agent = RobustDROAgent(
        dro_mpc, epsilon=0.5, generator=dro_generator,
        risk_manager=dynamic_risk_manager, regime_detector=regime_detector
    )

    # 4. Run Backtests
    results = {}
    history_dfs = {}

    from helios_core.simulate.agents import TradingAgent
    agents: dict[str, TradingAgent] = {
        "Naive Heuristic": naive_agent,
        "Deterministic MPC": det_agent,
        "Robust DRO (L1)": dro_agent
    }

    for name, agent in agents.items():
        logging.info(f"Running {name}...")

        tester = WalkForwardBacktester(df, agent, metrics)
        report = tester.run()
        results[name] = report
        history_dfs[name] = pd.DataFrame(tester.history).set_index("time")

    # 5. Print Terminal Tear Sheet
    print("\n" + "="*80)
    print(f"{'AGENT':<25} | {'NET PNL (€)':<12} | {'CYCLES (EFC)':<12} | {'RoDC (Ratio)':<12}")
    print("-" * 80)
    for name, res in results.items():
        net = res["Net Adjusted PnL (EUR)"]
        efc = res["EFC (Cycles)"]
        rodc = res["RoDC (Ratio)"]
        print(f"{name:<25} | {net:<12.2f} | {efc:<12.2f} | {rodc:<12.2f}")
    print("="*80 + "\n")

    # 6. Generate the Visual Tear Sheet
    generate_tear_sheet(df, history_dfs)


def generate_tear_sheet(df: pd.DataFrame, history_dfs: dict[str, pd.DataFrame]) -> None:
    """Plots the industrial Tear Sheet proving the DRO safety mechanisms."""
    plt.style.use('dark_background')
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(14, 12), sharex=True, gridspec_kw={'height_ratios': [2, 2, 1.5]})

    # A. Price Volatility
    ax1.plot(df.index, df['Price_EUR_MWh'], color='cyan', linewidth=1, alpha=0.9, label='EPEX SPOT (May 2023)')
    ax1.set_title("Market Environment: May 2023 (Normal Conditions)", fontsize=14, pad=15)
    ax1.set_ylabel("Price (€ / MWh)")
    ax1.grid(True, alpha=0.2)
    ax1.legend(loc="upper left")

    # B. Cumulative PnL Evolution
    colors = {"Naive Heuristic": "gray", "Deterministic MPC": "red", "Robust DRO (L1)": "green"}
    for name, hist in history_dfs.items():
        # Compute exact step-by-step net PNL
        # p_dis * price * 0.95 (rev) - p_ch * price (cost) - wear_cost
        marginal_lcos = 300_000.0 / (5000 * 10 * 2.0)

        hist['gross_rev'] = hist['p_dis'] * hist['price'] * 0.95
        hist['gross_cost'] = hist['p_ch'] * hist['price']
        throughput = hist['p_ch'] + hist['p_dis']
        hist['wear'] = throughput * marginal_lcos

        hist['net_step_pnl'] = hist['gross_rev'] - hist['gross_cost'] - hist['wear']
        hist['cum_pnl'] = hist['net_step_pnl'].cumsum()

        ax2.plot(hist.index, hist['cum_pnl'], color=colors[name], linewidth=2, label=name)

    ax2.set_title("Cumulative Net Adjusted PnL (Post-LCOS Degradation)", fontsize=14)
    ax2.set_ylabel("Cumulative €")
    ax2.grid(True, alpha=0.2)
    ax2.legend(loc="upper left")

    # C. State of Charge (The Safety Evidence)
    ax3.plot(history_dfs["Deterministic MPC"].index, history_dfs["Deterministic MPC"]['soc'],
             color='red', linewidth=1, alpha=0.7, label='Deterministic SoC')
    ax3.plot(history_dfs["Robust DRO (L1)"].index, history_dfs["Robust DRO (L1)"]['soc'],
             color='green', linewidth=1.5, alpha=0.9, label='DRO SoC')

    ax3.set_title("Asset Preservation: Deterministic Frantic Cycling vs DRO Discipline", fontsize=12)
    ax3.set_ylabel("SoC (MWh)")
    ax3.set_xlabel("Time (Hourly Walk-Forward)")
    ax3.grid(True, alpha=0.2)
    ax3.legend(loc="upper left")

    plt.tight_layout()

    os.makedirs("reports", exist_ok=True)
    fig.savefig("reports/benchmark_may_2023.png", dpi=300, bbox_inches='tight')
    logging.info("Visual Tear Sheet exported successfully to reports/benchmark_may_2023.png")


if __name__ == "__main__":
    main()
