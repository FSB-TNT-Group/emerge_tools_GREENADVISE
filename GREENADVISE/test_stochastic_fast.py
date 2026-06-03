"""
Fast standalone test: stochastic optimization with 5 configurations.
Arrays tile a 168-hour (1-week) pattern to fill the required 8760 hours.
Per-scenario spread is validated — genuine differences expected across the 10 scenarios.
"""

import sys, os, traceback
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

try:
    from PyQt5.QtWidgets import QApplication
    _qapp = QApplication.instance() or QApplication(sys.argv)
except Exception:
    pass

import pyomo.environ as pye
from cbc_path_resolver import get_cbc_executable_path
from OptimizationStochastic import OptimizationInputPreparator

N_HOURS = 8760

# ─── Synthetic data: tile a 1-week pattern to 8760 hours ──────────────────

WEEK = 168

def _tile(arr, n=N_HOURS):
    reps = -(-n // len(arr))      # ceil division
    return np.tile(arr, reps)[:n]

def make_price(base=0.18, amp=0.10):
    h = np.arange(WEEK) % 24
    p = base + amp * np.sin(np.pi * h / 12 - np.pi / 2)
    return _tile(np.clip(p, 0.03, 0.35))

def make_pv(cap_kw, scale=1.0):
    h = np.arange(WEEK) % 24
    profile = np.where((h > 6) & (h < 20),
                       np.sin(np.pi * (h - 6) / 14), 0.0)
    return _tile(profile * scale * cap_kw)

def make_wind(cap_kw, scale=1.0, seed=0):
    rng = np.random.default_rng(seed)
    cf = rng.uniform(0.0, 0.6, WEEK) * scale
    return _tile(np.clip(cf * cap_kw, 0, cap_kw))

def make_demand(base_kw, peak=1.8):
    h = np.arange(WEEK) % 24
    d = np.ones(WEEK) * base_kw
    d[(h >= 7) & (h <= 9)]   *= peak
    d[(h >= 18) & (h <= 21)] *= peak * 0.9
    return _tile(d)

def build_selected(price, demand,
                   pv_scens=None, wind_scens=None,
                   bat_cap=0, bat_eff=0.9, bat_rp=0, buyback=0.4):
    n = len(pv_scens or wind_scens)
    stoch = {}
    if pv_scens:
        stoch["PV Generation"] = [np.asarray(s) for s in pv_scens]
    if wind_scens:
        stoch["Wind Generation"] = [np.asarray(s) for s in wind_scens]
    stoch["Price Data"]         = [np.asarray(price)] * n
    stoch["Electricity Demand"] = [np.asarray(demand)] * n

    inp = {
        "Price Data":               np.asarray(price),
        "Electricity Demand":       np.asarray(demand),
        "Grid Power Limit":         "1e9",
        "Price Data Inputs":        {"buyback": str(buyback)},
        "stochastic":               stoch,
        "stochastic_probabilities": [1.0 / n] * n,
    }
    if pv_scens:
        inp["PV Generation"] = pv_scens[n // 2]
    if wind_scens:
        inp["Wind Generation"] = wind_scens[n // 2]
    if bat_cap > 0:
        inp["Battery Inputs"] = {
            "capacity":    bat_cap,
            "efficiency":  bat_eff * 100,
            "rated_power": bat_rp or bat_cap,
        }
    return inp

# ─── Run one config ──────────────────────────────────────────────────────────

def run_config(name, inp, results_dir):
    print(f"\n{'='*60}")
    print(f"CONFIG: {name}")
    print(f"{'='*60}")
    try:
        prep  = OptimizationInputPreparator(inp)
        model = pye.ConcreteModel()
        model = prep.create_model_variables(model, prep)
        model = prep.add_constraints_and_objective(model)
        print("  Model built. Solving…")

        solver = pye.SolverFactory('cbc', executable=get_cbc_executable_path())
        solver.options.update({"seconds": 120, "ratio": 0.01})
        res = solver.solve(model, tee=False)

        if res.solver.status != pye.SolverStatus.ok:
            print(f"  SOLVER FAILED: {res.solver.status}")
            return None

        results = prep.extract_results(model)
        stats   = prep._compute_stoch_stats(model)  # must pass model, not results dict

        per    = stats["stoch_per_profits"]
        prbs   = stats["stoch_probs"]
        spread = stats["stoch_profit_max"] - stats["stoch_profit_min"]

        print(f"  Expected : €{stats['stoch_profit_expected']:,.2f}")
        print(f"  Min/Max  : €{stats['stoch_profit_min']:,.2f} / €{stats['stoch_profit_max']:,.2f}")
        print(f"  Spread   : €{spread:,.2f}")
        if spread == 0:
            print("  *** WARNING: zero spread — all scenarios identical ***")
        print("  Per-scenario:")
        for i, (p, pr) in enumerate(zip(per, prbs)):
            print(f"    s{i+1:02d} prob={pr:.3f}  €{p:,.2f}")

        os.makedirs(results_dir, exist_ok=True)
        fname = os.path.join(results_dir, f"{name}.txt")
        with open(fname, "w") as f:
            f.write(f"Config: {name}\n{'='*60}\n")
            f.write(f"Expected profit : €{stats['stoch_profit_expected']:,.2f}\n")
            f.write(f"Min profit      : €{stats['stoch_profit_min']:,.2f}\n")
            f.write(f"Max profit      : €{stats['stoch_profit_max']:,.2f}\n")
            f.write(f"P10             : €{stats['stoch_profit_p10']:,.2f}\n")
            f.write(f"P90             : €{stats['stoch_profit_p90']:,.2f}\n")
            f.write(f"Spread (max-min): €{spread:,.2f}\n")
            f.write("\nPer-scenario profits:\n")
            scens, _ = prep.get_scenarios()
            pv_totals   = [np.sum(sc.get("PV Generation",   np.zeros(N_HOURS))) for sc in scens]
            wind_totals = [np.sum(sc.get("Wind Generation", np.zeros(N_HOURS))) for sc in scens]
            for i, (p, pr) in enumerate(zip(per, prbs)):
                f.write(f"  s{i+1:02d}  prob={pr:.4f}  "
                        f"pv={pv_totals[i]:,.0f}kWh  wind={wind_totals[i]:,.0f}kWh  "
                        f"profit=€{p:,.2f}\n")
        print(f"  Saved → {fname}")
        return stats

    except Exception as e:
        print(f"  ERROR: {e}")
        traceback.print_exc()
        return None

# ─── Five configurations ────────────────────────────────────────────────────

def main():
    results_dir = os.path.join(HERE, "test_results_fast")
    price  = make_price()
    dem2kw = make_demand(2.0)
    dem4kw = make_demand(4.0)

    N_SC = 10
    pv_scales   = np.linspace(0.60, 1.40, N_SC)
    wind_scales = np.linspace(0.50, 1.50, N_SC)

    configs = [
        ("C1_PV5kW_Bat10kWh_Dem2kW",
         build_selected(price, dem2kw,
                        pv_scens=[make_pv(5.0, s) for s in pv_scales],
                        bat_cap=10, bat_eff=0.92, bat_rp=5, buyback=0.4)),

        ("C2_PV5kW_Bat10kWh_Dem4kW",
         build_selected(price, dem4kw,
                        pv_scens=[make_pv(5.0, s) for s in pv_scales],
                        bat_cap=10, bat_eff=0.92, bat_rp=5, buyback=0.4)),

        ("C3_Wind3kW_Bat6kWh_Dem2kW",
         build_selected(price, dem2kw,
                        wind_scens=[make_wind(3.0, s, seed=i)
                                    for i, s in enumerate(wind_scales)],
                        bat_cap=6, bat_eff=0.90, bat_rp=3, buyback=0.35)),

        ("C4_PV3kW_Wind3kW_Bat8kWh_Dem3kW",
         build_selected(price, make_demand(3.0),
                        pv_scens=[make_pv(3.0, s) for s in pv_scales],
                        wind_scens=[make_wind(3.0, s, seed=i)
                                    for i, s in enumerate(wind_scales)],
                        bat_cap=8, bat_eff=0.91, bat_rp=4, buyback=0.38)),

        ("C5_PV8kW_NoBattery_Dem2kW",
         build_selected(price, dem2kw,
                        pv_scens=[make_pv(8.0, s) for s in pv_scales],
                        buyback=0.45)),
    ]

    all_stats = {}
    for cname, inp in configs:
        s = run_config(cname, inp, results_dir)
        if s:
            all_stats[cname] = s

    print("\n" + "="*72)
    print(f"{'Config':<42} {'Expected':>10} {'Min':>10} {'Max':>10} {'Spread':>8}")
    print("-"*72)
    for cname, s in all_stats.items():
        spread = s["stoch_profit_max"] - s["stoch_profit_min"]
        mark = "  *** ZERO SPREAD ***" if spread == 0 else ""
        print(f"{cname:<42} {s['stoch_profit_expected']:>10.2f} {s['stoch_profit_min']:>10.2f} "
              f"{s['stoch_profit_max']:>10.2f} {spread:>8.2f}{mark}")

    summary_path = os.path.join(results_dir, "SUMMARY.txt")
    with open(summary_path, "w") as f:
        f.write("STOCHASTIC OPTIMIZATION TEST — SUMMARY\n")
        f.write(f"{'='*72}\n")
        f.write(f"{'Config':<42} {'Expected':>10} {'Min':>10} {'Max':>10} {'Spread':>8}\n")
        f.write("-"*72 + "\n")
        for cname, s in all_stats.items():
            spread = s["stoch_profit_max"] - s["stoch_profit_min"]
            f.write(f"{cname:<42} {s['stoch_profit_expected']:>10.2f} "
                    f"{s['stoch_profit_min']:>10.2f} {s['stoch_profit_max']:>10.2f} "
                    f"{spread:>8.2f}\n")
    print(f"\nSummary → {summary_path}")


if __name__ == "__main__":
    main()
