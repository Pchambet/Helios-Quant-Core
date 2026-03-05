# Helios-Quant-Core ⚡

![Tests](https://img.shields.io/badge/audit-passed--28/28-success)
![Mypy](https://img.shields.io/badge/mypy-strict-blue)
![API](https://img.shields.io/badge/oracle-ENTSO--E-orange)
![License](https://img.shields.io/badge/license-GPL--3.0-blue)

**Trading the physics of the grid, not the noise of the market.**

Helios-Quant-Core is an industrial-grade Energy Management System (EMS) designed to operate massive Battery Energy Storage Systems (BESS) on the European power markets.

But it doesn't work like a standard trading bot. Here is the story of why we built it, and how it solves the most critical flaw in modern energy trading.

---

## 📖 The Problem: The Grid is Changing, but Trading Algorithms Aren't

Historically, electricity prices were predictable. You could train a Machine Learning model on past data, and it would tell you when to buy cheap night power and sell it during the evening peak.

Today, the European grid is flooded with intermittent renewables (wind and solar) and exposed to geopolitical shocks. This creates unprecedented chaos: prices can plummet to -500€/MWh on a sunny Sunday, or skyrocket to +3,000€/MWh when a nuclear plant fails unexpectedly.

**The standard industry approach is broken:**
Most energy funds and aggregators still rely on "predictive" AI. They try to guess the exact price of electricity tomorrow.
1. When the market behaves normally, they make a small profit.
2. When a crisis hits (a "Black Swan"), their predictive models hallucinate, make the wrong trades, and lose millions.
3. Even worse, to chase small profits, they constantly cycle the battery, destroying the physical chemistry of a multi-million dollar asset (wear and tear).

---

## 💡 The Helios Paradigm: The "Physical Oracle"

We rebuilt battery trading from the ground up. Instead of playing a guessing game with prices, **Helios-Quant-Core reads the laws of physics.**

We shifted from a speculative *Financial algorithm* to a *Thermodynamic controller*.

### 1. The Eyes: Reading the Grid, Not the Ticker
Instead of looking at past price noise, Helios connects directly to the European transmission system (ENTSO-E). Every morning, it looks at the physical reality of the continent:
- *How much wind is blowing?*
- *How much sun is shining?*
- *How many nuclear reactors are online?*
- *What is the total human power demand?*

By finding past days that share the **exact same physical signature**, Helios creates a realistic set of scenarios for tomorrow.

### 2. The Brain: Paranoia as a Superpower (Distributionally Robust Optimization)
Once Helios knows the physical state of the grid, it doesn't just calculate the "average" expected price. It uses advanced Operations Research mathematics (Distributionally Robust Optimization) to prepare for the **worst-case scenario**.
- If the grid is stable (lots of wind, nuclear is running), Helios lowers its shield and trades aggressively, capturing normal margins.
- If the grid is scarce (nuclear outages, gas crisis), Helios expands its mathematical shield. It stops chasing pennies, refuses to wear out the battery, and waits like a sniper to capture massive crisis price spikes.

### 3. The Body: Protecting the Battery
Helios incorporates a "Digital Twin" of the battery. It mathematically knows that cycling a battery degrades its lifespan (Levelized Cost of Storage - LCOS). It also pays the real-world grid fees (TURPE) in its simulation. It will never make a trade if the financial profit is lower than the chemical damage inflicted on the battery.

---

## 🚀 The Results: Peacetime vs. Wartime

We backtested Helios-Quant-Core against the two extremes of the European market.

**1. Normal Conditions (May 2023)**
*The grid is calm. Prices peak at 160 €.*
- Standard AI Models: ~6,800 €
- Helios-Quant-Core: **7,488 €**
*(Helios makes the exact same money as highly aggressive algorithms, but with fewer cycles, saving the battery's lifespan.)*

**2. The Ultimate Crisis (August 2022)**
*The Russian gas crisis and French nuclear outages. Extreme volatility.*
- "Blind" Mathematical Models: ~6,500 € (They get terrified by volatility and freeze).
- Helios-Quant-Core: **17,381 €** (A **2.6x increase** in profit).
*(Because Helios read the ENTSO-E physical data, it understood the nuclear scarcity. It lowered its standard trading, armed its robust shield, and perfectly captured the 1000€/MWh price dislocations).*

---

## 🛡️ Built for Institutional Trust

For an energy aggregator or an infrastructure fund, an algorithm must be auditable. You cannot put a €20M battery in the hands of a "black-box" AI.

Helios-Quant-Core is entirely transparent and mathematically provable.
- **No Free Lunches:** We ran extensive "Poison Tests". If we give Helios fake physical data, it loses money. It genuinely relies on physical intelligence, not data leakage or cheats.
- **Strictly Safe:** It solves an exact mathematical optimization problem (Linear Programming). It will never output an action that violates physical laws.

---

## 🚦 Quick Start for Engineers

For the technical implementation, mathematical proofs ($L_1$ Wasserstein Duality), and reproducibility setup:

### Setup & Play
```bash
git clone https://github.com/Pchambet/Helios-Quant-Core
cd Helios-Quant-Core

# Setup environment
python3 -m venv .venv
source .venv/bin/activate
pip install -e "."

# Run the peacetime benchmark
python run_normal_benchmark.py
```

### Deep Dives
- [Mathematical Whitepaper (THEORY.md)](THEORY.md)
- [Industrial Audit Trail (walkthrough.md)](brain/walkthrough.md)

---
*Helios-Quant-Core v1.0.0-PRODUCTION. Uniting the laws of thermodynamics with quantitative finance.*
