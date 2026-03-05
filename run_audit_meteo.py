import pandas as pd

from helios_core.data.entsoe_loader import HistoricalCrisisLoader
from helios_core.assets.config import BatteryConfig
from helios_core.assets.battery import BatteryAsset
from helios_core.optimization.scaling import PriceScaler
from helios_core.optimization.controller import BatteryMPC
from helios_core.stochastic.generator import ScenarioGenerator
from helios_core.stochastic.config import StochasticConfig
from helios_core.simulate.agents import DeterministicMPCAgent, RobustDROAgent

def run_audit() -> None:
    print("\n" + "="*80)
    print(" EMPIRICAL AUDIT : PHYSICS-INFORMED DRO vs WEATHER EXTREMES ")
    print("="*80)

    # 1. Load the immutable dataset
    loader = HistoricalCrisisLoader(start_date="2022-08-01", end_date="2022-08-31")
    df = loader.fetch_data()

    # Let's isolate a specific shock day: August 17, 2022 (A very expensive day in Europe)
    # We want to see how the agent plans the 48h from Aug 17 00:00 to Aug 18 23:00
    target_start = pd.to_datetime("2022-08-17 00:00:00+00:00")
    if target_start not in df.index:
        print("Target date not found in dataset. Falling back to index 384.")
        t = 384
    else:
        t = df.index.get_loc(target_start)

    print(f"\n[TARGET DATE] {df.index[t]} \n")

    # The history it has to learn from
    past_data = df.iloc[:t].copy()

    # The 48h horizon it sees
    forecast_weather = df.iloc[t : t + 48].copy()
    price_forecast = df['Price_EUR_MWh'].values[t : t + 48]

    print("--- 1. WEATHER CONDITIONS (Next 48h) ---")
    avg_temp = forecast_weather['Temperature_C'].mean()
    max_temp = forecast_weather['Temperature_C'].max()
    avg_wind = forecast_weather['WindSpeed_kmh'].mean()
    print(f"Average Temp: {avg_temp:.1f}C (Max: {max_temp:.1f}C)")
    print(f"Average Wind: {avg_wind:.1f} km/h")
    print(f"Average Price : {price_forecast.mean():.2f} EUR/MWh")
    print("-" * 40)

    # --- 2. THE KNN GENERATOR AUDIT ---
    stoch_config = StochasticConfig(n_scenarios=20, horizon_hours=48, noise_multiplier=0.0)
    generator = ScenarioGenerator(stoch_config)

    scenarios = generator.fit_transform(past_data, forecast_weather=forecast_weather, seed=42)

    print("\n--- 2. THE KNN AMBIGUITY SET (Historical Days Selected) ---")
    print("The DRO Agent looks at the weather forecast and builds its nightmare scenarios:")

    # Re-discover which days were picked by looking at the first hour price matches
    for n in range(min(5, len(scenarios))): # Print first 5
        start_price = scenarios[n][0]
        # Find this price in history
        matches = past_data[past_data['Price_EUR_MWh'] == start_price]
        if not matches.empty:
            match_date = matches.index[0]
            print(f"- Scenario {n+1} was drawn from: {match_date.strftime('%Y-%m-%d')} (Similiar weather confirmed)")
        else:
            print(f"- Scenario {n+1} extracted (Noise/Bootstrapped)")


    # --- 3. THE DISPATCH AUDIT ---
    config = BatteryConfig(capacity_mwh=10.0, max_charge_mw=5.0, max_discharge_mw=5.0, capex_eur=300000.0)

    # Deterministic Agent (Blind to Weather, relies strictly on mean forecast calculation)
    det_mpc = BatteryMPC(BatteryAsset(config), PriceScaler(), alpha_slippage=5.0)
    det_agent = DeterministicMPCAgent(det_mpc)

    # DRO Agent (Physics-Informed)
    dro_mpc = BatteryMPC(BatteryAsset(config), PriceScaler(), alpha_slippage=5.0)
    dro_agent = RobustDROAgent(dro_mpc, epsilon=1.5, generator=generator)

    current_soc = 0.0 # Start empty

    det_pch, det_pdis, det_profit = det_agent.act(current_soc, price_forecast)
    dro_pch, dro_pdis, dro_profit = dro_agent.act(
        current_soc=current_soc,
        price_forecast=price_forecast,
        past_data=past_data,
        forecast_weather=forecast_weather
    )

    print("\n--- 3. THE STRATEGIC DISPATCH (Hour 0 to 24) ---")
    print(f"| {'Hour':<4} | {'Price (€/MWh)':<13} | {'Det. Charge':<11} | {'DRO Charge':<11} |")
    print("-" * 50)

    for i in range(24):
        p = price_forecast[i]
        d_ch = det_pch[i] - det_pdis[i] # Net power mapping (Positive = Charge)
        r_ch = dro_pch[i] - dro_pdis[i]

        # Color coding extreme moves
        d_str = f"{d_ch:+.1f} MW"
        r_str = f"{r_ch:+.1f} MW"

        if r_ch > d_ch + 1.0:
            r_str += " (*Aggressive Prep*)"
        elif r_ch < d_ch - 1.0:
            r_str += " (*Defensive Wait*)"

        print(f"| {i:<4} | {p:<13.2f} | {d_str:<11} | {r_str:<11} |")

    print("\n==================================================================\n")

if __name__ == "__main__":
    run_audit()
