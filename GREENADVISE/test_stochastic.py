"""
Standalone test: run stochastic optimization for 5 configurations.
Bypasses the Qt GUI. Saves per-scenario profit results to text files.
"""

import sys, os, math, traceback
import numpy as np

# Make sure V1/GREENADVISE modules are importable
HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

# PyQt5 must be importable (OptimizationStochastic imports it at top-level).
# We don't create any Qt objects, we just need the import to succeed.
try:
    from PyQt5.QtWidgets import QApplication
    _qapp = QApplication.instance() or QApplication(sys.argv)
except Exception as e:
    print(f"WARNING: PyQt5 unavailable ({e}). Continuing anyway.")

import pyomo.environ as pye
from cbc_path_resolver import get_cbc_executable_path
from OptimizationStochastic import OptimizationInputPreparator

# ─── helpers ────────────────────────────────────────────────────────────────

N_HOURS = 8760
T_RANGE = range(8760)

def make_price_profile(base=0.15, amplitude=0.08):
    """Sinusoidal electricity price: high midday, low night."""
    hours = np.arange(N_HOURS)
    day_h = hours % 24
    price = base + amplitude * np.sin(np.pi * day_h / 12 - np.pi / 2)
    price = np.clip(price, 0.03, 0.35)
    return price

def make_pv_profile(capacity_kw, scale=1.0):
    """Simple solar profile: zero at night, sine peak during day, seasonal variation."""
    hours = np.arange(N_HOURS)
    day_of_year = (hours // 24) % 365
    hour_of_day = hours % 24
    # Sunrise ~6h, sunset ~18h in summer; narrower in winter
    season_len = 6.0 + 6.0 * np.sin(2 * np.pi * (day_of_year - 80) / 365)
    peak_hour = 12.0
    sunrise = peak_hour - season_len / 2
    sunset  = peak_hour + season_len / 2
    daylight = (hour_of_day > sunrise) & (hour_of_day < sunset)
    profile = np.zeros(N_HOURS)
    profile[daylight] = np.sin(
        np.pi * (hour_of_day[daylight] - sunrise[daylight]) /
        (sunset[daylight] - sunrise[daylight])
    )
    # Seasonal amplitude
    season_amp = 0.6 + 0.4 * np.sin(2 * np.pi * (day_of_year - 80) / 365)
    profile *= season_amp * scale * capacity_kw
    return np.clip(profile, 0, None)

def make_wind_profile(capacity_kw, scale=1.0, seed=0):
    """Simple wind profile with random variation and seasonal trend."""
    rng = np.random.default_rng(seed)
    hours = np.arange(N_HOURS)
    day_of_year = (hours // 24) % 365
    # Higher wind in winter
    season = 0.6 + 0.4 * np.cos(2 * np.pi * day_of_year / 365)
    # Random hourly noise
    noise = rng.uniform(0.0, 1.0, N_HOURS)
    cf = 0.3 * season * noise * scale
    return np.clip(cf * capacity_kw, 0, capacity_kw)

def make_demand_profile(base_kw, peak_factor=1.5):
    """Flat demand with morning/evening peaks."""
    hours = np.arange(N_HOURS)
    h = hours % 24
    demand = np.ones(N_HOURS) * base_kw
    demand[(h >= 7) & (h <= 9)]   *= peak_factor
    demand[(h >= 18) & (h <= 21)] *= peak_factor * 0.9
    return demand

def build_pv_scenarios(capacity_kw, n=10):
    """10 PV scenarios with capacity-factor scales from 0.6 to 1.4."""
    scales = np.linspace(0.60, 1.40, n)
    return [make_pv_profile(capacity_kw, s) for s in scales]

def build_wind_scenarios(capacity_kw, n=10):
    """10 wind scenarios from different random seeds."""
    scales = np.linspace(0.50, 1.50, n)
    return [make_wind_profile(capacity_kw, s, seed=i) for i, s in enumerate(scales)]

def make_selected_inputs(
    price, elec_demand,
    pv_scenarios=None, wind_scenarios=None,
    battery_cap=0, battery_eff=0.9, battery_rp=0,
    buyback=0.5,
    grid_limit=1e9,
):
    """Build the selected_inputs dict expected by OptimizationInputPreparator."""
    n = len(pv_scenarios or wind_scenarios or [])
    if n == 0:
        raise ValueError("Need at least one list of scenarios")

    stoch = {}
    pv_base = np.zeros(N_HOURS)
    wind_base = np.zeros(N_HOURS)

    if pv_scenarios:
        stoch["PV Generation"] = [np.asarray(s) for s in pv_scenarios]
        pv_base = pv_scenarios[n // 2]     # median scenario as deterministic base

    if wind_scenarios:
        stoch["Wind Generation"] = [np.asarray(s) for s in wind_scenarios]
        wind_base = wind_scenarios[n // 2]

    stoch["Price Data"]          = [np.asarray(price)] * n
    stoch["Electricity Demand"]  = [np.asarray(elec_demand)] * n

    probs = [1.0 / n] * n   # equal weights

    inp = {
        "Price Data":              np.asarray(price),
        "Electricity Demand":      np.asarray(elec_demand),
        "Grid Power Limit":        str(grid_limit),
        "Price Data Inputs":       {"buyback": str(buyback)},
        "stochastic":              stoch,
        "stochastic_probabilities": probs,
    }
    if pv_base.any():
        inp["PV Generation"] = pv_base
    if wind_base.any():
        inp["Wind Generation"] = wind_base

    if battery_cap > 0:
        inp["Battery Inputs"] = {
            "capacity":    battery_cap,
            "efficiency":  battery_eff * 100,
            "rated_power": battery_rp or battery_cap,
        }

    return inp


def run_config(name, selected_inputs, results_dir):
    """Solve the stochastic LP and return (stats, ok)."""
    print(f"\n{'='*60}")
    print(f"CONFIG: {name}")
    print(f"{'='*60}")

    try:
        prep  = OptimizationInputPreparator(selected_inputs)
        model = pye.ConcreteModel()
        model = prep.create_model_variables(model, prep)
        model = prep.add_constraints_and_objective(model)

        cbc_path = get_cbc_executable_path()
        solver   = pye.SolverFactory('cbc', executable=cbc_path)
        solver.options.update({"seconds": 900, "ratio": 0.02})

        print("  Solving LP ...")
        res = solver.solve(model, tee=False)

        # Accept aborted-with-solution (CBC time limit but feasible solution found)
        ok_statuses = {pye.SolverStatus.ok, pye.SolverStatus.aborted}
        if res.solver.status not in ok_statuses:
            print("  SOLVER STATUS:", res.solver.status)
            return None, False

        results = prep.extract_results(model)
        stats   = prep._compute_stoch_stats(results)
        results.update(stats)

        # Print summary
        per = stats["stoch_per_profits"]
        prbs = stats["stoch_probs"]
        print(f"  Scenarios  : {stats['stoch_n_scenarios']}")
        print(f"  Expected   : €{stats['stoch_profit_expected']:,.0f}")
        print(f"  Min        : €{stats['stoch_profit_min']:,.0f}")
        print(f"  Max        : €{stats['stoch_profit_max']:,.0f}")
        print(f"  P10 – P90  : €{stats['stoch_profit_p10']:,.0f} – €{stats['stoch_profit_p90']:,.0f}")
        print(f"  Spread     : €{stats['stoch_profit_max'] - stats['stoch_profit_min']:,.0f}")
        print(f"  Per-scenario profits:")
        for i, (p, pr) in enumerate(zip(per, prbs)):
            print(f"    Scenario {i+1:2d}  prob={pr:.3f}  profit=€{p:,.0f}")

        # Save to file
        os.makedirs(results_dir, exist_ok=True)
        fname = os.path.join(results_dir, f"{name.replace(' ', '_')}.txt")
        with open(fname, "w", encoding="utf-8") as f:
            f.write(f"Config: {name}\n")
            f.write("="*60 + "\n")
            f.write(f"Scenarios         : {stats['stoch_n_scenarios']}\n")
            f.write(f"Expected profit   : €{stats['stoch_profit_expected']:,.2f}\n")
            f.write(f"Min profit        : €{stats['stoch_profit_min']:,.2f}\n")
            f.write(f"Max profit        : €{stats['stoch_profit_max']:,.2f}\n")
            f.write(f"P10               : €{stats['stoch_profit_p10']:,.2f}\n")
            f.write(f"P90               : €{stats['stoch_profit_p90']:,.2f}\n")
            f.write(f"Spread (max-min)  : €{stats['stoch_profit_max']-stats['stoch_profit_min']:,.2f}\n")
            f.write("\nPer-scenario profits:\n")
            for i, (p, pr) in enumerate(zip(per, prbs)):
                f.write(f"  Scenario {i+1:2d}  prob={pr:.4f}  profit=€{p:,.2f}\n")
            f.write("\nKey inputs summary:\n")
            scens, _ = prep.get_scenarios()
            pv_totals   = [np.sum(sc.get("PV Generation",   np.zeros(N_HOURS))) for sc in scens]
            wind_totals = [np.sum(sc.get("Wind Generation", np.zeros(N_HOURS))) for sc in scens]
            f.write(f"  PV total per scenario   (kWh): {[f'{v:,.0f}' for v in pv_totals]}\n")
            f.write(f"  Wind total per scenario (kWh): {[f'{v:,.0f}' for v in wind_totals]}\n")
        print(f"  Saved -> {fname}")
        return stats, True

    except Exception as e:
        print(f"  ERROR: {e}")
        traceback.print_exc()
        return None, False


# ─── Five configurations ─────────────────────────────────────────────────────

def main():
    results_dir = os.path.join(HERE, "test_results")
    price    = make_price_profile(base=0.18, amplitude=0.10)
    demand_2kw = make_demand_profile(2.0, peak_factor=1.8)
    demand_4kw = make_demand_profile(4.0, peak_factor=1.6)

    configs = []

    # ── Config 1: PV 5 kW + Battery 10 kWh, moderate demand ──────────────────
    pv5_scens = build_pv_scenarios(5.0)
    configs.append((
        "Config1_PV5kW_Bat10kWh_Dem2kW",
        make_selected_inputs(
            price, demand_2kw,
            pv_scenarios=pv5_scens,
            battery_cap=10.0, battery_eff=0.92, battery_rp=5.0,
            buyback=0.4,
        ),
    ))

    # ── Config 2: PV 5 kW + Battery 10 kWh, high demand (often imports) ──────
    configs.append((
        "Config2_PV5kW_Bat10kWh_Dem4kW",
        make_selected_inputs(
            price, demand_4kw,
            pv_scenarios=pv5_scens,
            battery_cap=10.0, battery_eff=0.92, battery_rp=5.0,
            buyback=0.4,
        ),
    ))

    # ── Config 3: Wind 3 kW + Battery 6 kWh, moderate demand ─────────────────
    wind3_scens = build_wind_scenarios(3.0)
    configs.append((
        "Config3_Wind3kW_Bat6kWh_Dem2kW",
        make_selected_inputs(
            price, demand_2kw,
            wind_scenarios=wind3_scens,
            battery_cap=6.0, battery_eff=0.90, battery_rp=3.0,
            buyback=0.35,
        ),
    ))

    # ── Config 4: PV 3 kW + Wind 3 kW + Battery 8 kWh ────────────────────────
    pv3_scens   = build_pv_scenarios(3.0)
    wind3b_scens = build_wind_scenarios(3.0, n=10)
    # Build combined scenarios: PV and Wind vary independently
    configs.append((
        "Config4_PV3kW_Wind3kW_Bat8kWh_Dem3kW",
        make_selected_inputs(
            price, make_demand_profile(3.0),
            pv_scenarios=pv3_scens,
            wind_scenarios=wind3b_scens,
            battery_cap=8.0, battery_eff=0.91, battery_rp=4.0,
            buyback=0.38,
        ),
    ))

    # ── Config 5: PV 8 kW, no battery, moderate demand ────────────────────────
    pv8_scens = build_pv_scenarios(8.0)
    configs.append((
        "Config5_PV8kW_NoBattery_Dem2kW",
        make_selected_inputs(
            price, demand_2kw,
            pv_scenarios=pv8_scens,
            buyback=0.45,
        ),
    ))

    # ─── Run all configs ────────────────────────────────────────────────────
    all_stats = {}
    for name, inp in configs:
        stats, ok = run_config(name, inp, results_dir)
        if ok:
            all_stats[name] = stats

    # ─── Summary table ───────────────────────────────────────────────────────
    print("\n" + "="*70)
    print("SUMMARY TABLE")
    print("="*70)
    print(f"{'Config':<45} {'Expected':>10} {'Min':>10} {'Max':>10} {'Spread':>10}")
    print("-"*70)
    for name, s in all_stats.items():
        spread = s["stoch_profit_max"] - s["stoch_profit_min"]
        print(f"{name:<45} {s['stoch_profit_expected']:>10,.0f} {s['stoch_profit_min']:>10,.0f} "
              f"{s['stoch_profit_max']:>10,.0f} {spread:>10,.0f}")

    os.makedirs(results_dir, exist_ok=True)
    summary_path = os.path.join(results_dir, "SUMMARY.txt")
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write("STOCHASTIC OPTIMIZATION TEST SUMMARY\n")
        f.write("="*70 + "\n")
        f.write(f"{'Config':<45} {'Expected':>10} {'Min':>10} {'Max':>10} {'Spread':>10}\n")
        f.write("-"*70 + "\n")
        for name, s in all_stats.items():
            spread = s["stoch_profit_max"] - s["stoch_profit_min"]
            f.write(f"{name:<45} {s['stoch_profit_expected']:>10,.0f} "
                    f"{s['stoch_profit_min']:>10,.0f} {s['stoch_profit_max']:>10,.0f} "
                    f"{spread:>10,.0f}\n")
    print(f"\nSummary saved -> {summary_path}")


if __name__ == "__main__":
    main()
