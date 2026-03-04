import pandas as pd
from helios_core.optimization.controller import BatteryMPC
from helios_core.assets.battery import BatteryAsset
from helios_core.assets.config import BatteryConfig
from helios_core.optimization.scaling import PriceScaler

def main() -> None:
    # 1. Load Data
    df = pd.read_parquet("data/epex_2022_crisis.parquet")

    # 2. Extract a single day (Aug 15 2022 - a highly volatile day)
    day_df = df.loc["2022-08-15 00:00:00+00:00":"2022-08-15 23:00:00+00:00"].copy() # type: ignore
    if len(day_df) != 24:
        # Fallback to pure slicing if indices differ slightly
        day_df = df.iloc[500:524].copy()

    real_prices = day_df["Price_EUR_MWh"].values

    # 3. Setup Components
    config = BatteryConfig(
        capacity_mwh=10.0,
        max_charge_mw=5.0,
        max_discharge_mw=5.0,
        efficiency_charge=0.90,
        efficiency_discharge=0.90,
        leakage_rate_per_hour=0.001,
        initial_soc_mwh=0.0,
        capex_eur=300000.0,
        cycle_life=10000
    )
    battery = BatteryAsset(config)

    # Using the exact same scaler setup as the backtest
    scaler = PriceScaler()
    # In backtester, the scaler is fit on the whole known history. Let's fit it on 30 days of data
    history_df = df.iloc[:day_df.index.get_loc(day_df.index[0])].copy()
    if len(history_df) == 0:
         scaler.fit(real_prices)
    else:
         scaler.fit(history_df["Price_EUR_MWh"].values)

    scaled_prices = scaler.transform(real_prices)

    mpc = BatteryMPC(battery, scaler)

    # 4. Run Deterministic MPC
    p_ch, p_dis, status = mpc.solve_deterministic(real_prices)

    print(f"Solver Status: {status}")
    print("="*80)
    print(f"{'Hour':<6} | {'Real Price (€)':<15} | {'Scaled Price':<15} | {'Charge (MW)':<12} | {'Discharge (MW)':<15} | {'Net Action (MW)':<15}")
    print("-" * 80)

    for t in range(24):
        ch = p_ch[t] if p_ch is not None else 0.0
        dis = p_dis[t] if p_dis is not None else 0.0
        net = ch - dis
        print(f"{t:<6} | {real_prices[t]:<15.2f} | {scaled_prices[t]:<15.4f} | {ch:<12.2f} | {dis:<15.2f} | {net:<15.2f}")

if __name__ == "__main__":
    main()
