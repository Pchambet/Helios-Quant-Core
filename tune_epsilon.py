import os
import logging
import matplotlib.pyplot as plt

from helios_core.data.entsoe_loader import HistoricalCrisisLoader
from helios_core.assets.config import BatteryConfig
from helios_core.assets.battery import BatteryAsset
from helios_core.optimization.scaling import PriceScaler
from helios_core.optimization.controller import BatteryMPC
from helios_core.simulate.metrics import RiskMetrics
from helios_core.simulate.backtester import WalkForwardBacktester
from helios_core.simulate.agents import RobustDROAgent

logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

def main() -> None:
    print("\n" + "="*80)
    print(" HELIOS-QUANT-CORE : EPSILON CALIBRATION (EFFICIENT FRONTIER) ")
    print("="*80 + "\n")

    loader = HistoricalCrisisLoader(start_date="2022-08-01", end_date="2022-08-31")
    df = loader.fetch_data()

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

    # We will test a log-linear grid of epsilon values within the [-1, 1] scaled domain.
    # An epsilon of 1.0 means the distribution can shift by half the total market width.
    epsilons = [0.0, 0.01, 0.05, 0.1, 0.25, 0.5]

    results = []

    print(f"{'EPSILON':<10} | {'NET PNL (€)':<12} | {'CYCLES (EFC)':<12} | {'RoDC (Ratio)':<12}")
    print("-" * 55)

    for eps in epsilons:
        scaler = PriceScaler()
        mpc = BatteryMPC(BatteryAsset(config), scaler)
        agent = RobustDROAgent(mpc, epsilon=eps)

        tester = WalkForwardBacktester(df, agent, metrics)
        report = tester.run()

        net_pnl = report["Net Adjusted PnL (EUR)"]
        efc = report["EFC (Cycles)"]
        rodc = report["RoDC (Ratio)"]

        print(f"{eps:<10.2f} | {net_pnl:<12.2f} | {efc:<12.2f} | {rodc:<12.2f}")

        results.append({
            "Epsilon": eps,
            "Net PnL": net_pnl,
            "EFC": efc,
            "RoDC": rodc
        })

    # Plot Efficient Frontier
    plot_efficient_frontier(results)

def plot_efficient_frontier(results: list[dict[str, float]]) -> None:
    os.makedirs("reports", exist_ok=True)

    epsilons = [r["Epsilon"] for r in results]
    pnls = [r["Net PnL"] for r in results]
    rodcs = [r["RoDC"] for r in results]

    plt.style.use('dark_background')
    fig, ax1 = plt.subplots(figsize=(10, 6))

    color = 'tab:cyan'
    ax1.set_xlabel('Ambiguity Radius (Epsilon)', fontsize=12)
    ax1.set_ylabel('Net Adjusted PnL (€)', color=color, fontsize=12)
    ax1.plot(epsilons, pnls, marker='o', color=color, linewidth=2, label='Net PnL')
    ax1.tick_params(axis='y', labelcolor=color)
    ax1.grid(True, alpha=0.2)

    ax2 = ax1.twinx()
    color2 = 'tab:orange'
    ax2.set_ylabel('RoDC (Return on Degraded Capital)', color=color2, fontsize=12)
    ax2.plot(epsilons, rodcs, marker='s', color=color2, linewidth=2, linestyle='--', label='RoDC')
    ax2.tick_params(axis='y', labelcolor=color2)

    # Highlight Epsilon = 0 (Deterministic Equivalent)
    ax1.axvline(x=0.0, color='red', linestyle=':', alpha=0.5, label='Deterministic Anchor')

    plt.title('DRO Efficient Frontier: Asset Return vs Ambiguity Risk', fontsize=14, pad=15)

    fig.tight_layout()
    out_path = "reports/epsilon_calibration.png"
    plt.savefig(out_path, dpi=300, bbox_inches='tight')
    print(f"\n[EXPORT] Calibration Tear Sheet saved to {out_path}")

if __name__ == "__main__":
    main()
