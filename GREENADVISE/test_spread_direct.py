"""
Direct test of _compute_stoch_stats: verifies genuine per-scenario spread
WITHOUT running the LP. We inject a fixed battery schedule (as if returned
by extract_results) and vary PV/wind across the 10 scenarios.

This is the fastest way to prove the spread fix works.
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

from OptimizationStochastic import OptimizationInputPreparator

N = 8760
WEEK = 168

def _tile(arr, n=N):
    return np.tile(arr, -(-n // len(arr)))[:n]

def make_price(base=0.18, amp=0.10):
    h = np.arange(WEEK) % 24
    return _tile(np.clip(base + amp * np.sin(np.pi * h / 12 - np.pi / 2), 0.03, 0.35))

def make_pv(cap_kw, scale=1.0):
    h = np.arange(WEEK) % 24
    profile = np.where((h > 6) & (h < 20), np.sin(np.pi * (h - 6) / 14), 0.0)
    return _tile(profile * scale * cap_kw)

def make_wind(cap_kw, scale=1.0, seed=0):
    rng = np.random.default_rng(seed)
    cf  = rng.uniform(0.0, 0.6, WEEK) * scale
    return _tile(np.clip(cf * cap_kw, 0, cap_kw))

def make_demand(base_kw, peak=1.8):
    h = np.arange(WEEK) % 24
    d = np.ones(WEEK) * base_kw
    d[(h >= 7) & (h <= 9)]   *= peak
    d[(h >= 18) & (h <= 21)] *= peak * 0.9
    return _tile(d)

def build_inputs(price, demand, pv_scens=None, wind_scens=None,
                 bat_cap=0, bat_eff=0.9, bat_rp=0, buyback=0.4):
    n_sc = len(pv_scens or wind_scens)
    stoch = {
        "Price Data":         [np.asarray(price)] * n_sc,
        "Electricity Demand": [np.asarray(demand)] * n_sc,
    }
    if pv_scens:
        stoch["PV Generation"] = [np.asarray(s) for s in pv_scens]
    if wind_scens:
        stoch["Wind Generation"] = [np.asarray(s) for s in wind_scens]

    inp = {
        "Price Data":               np.asarray(price),
        "Electricity Demand":       np.asarray(demand),
        "Grid Power Limit":         "1e9",
        "Price Data Inputs":        {"buyback": str(buyback)},
        "stochastic":               stoch,
        "stochastic_probabilities": [1.0 / n_sc] * n_sc,
    }
    if pv_scens:
        inp["PV Generation"] = pv_scens[n_sc // 2]
    if wind_scens:
        inp["Wind Generation"] = wind_scens[n_sc // 2]
    if bat_cap > 0:
        inp["Battery Inputs"] = {
            "capacity":    bat_cap,
            "efficiency":  bat_eff * 100,
            "rated_power": bat_rp or bat_cap,
        }
    return inp

def make_battery_schedule(bat_cap, bat_rp, price):
    """
    Simple heuristic battery schedule: charge during cheap hours,
    discharge during expensive hours. Simulates what LP would produce.
    """
    charge    = np.zeros(N)
    discharge = np.zeros(N)
    threshold = np.median(price)
    for t in range(N):
        if price[t] < threshold * 0.85:
            charge[t]    = min(bat_rp, bat_cap * 0.1)  # charge rate
        elif price[t] > threshold * 1.15:
            discharge[t] = min(bat_rp, bat_cap * 0.1)  # discharge rate
    return charge, discharge

def run_test(name, inp, bat_charge, bat_discharge, results_dir):
    print(f"\n{'='*60}")
    print(f"CONFIG: {name}")
    print(f"{'='*60}")
    try:
        prep = OptimizationInputPreparator(inp)

        # Simulated LP result: battery schedule + no other flows
        # (we only need "Battery charge" and "Battery discharge" for _compute_stoch_stats)
        fake_results = {
            "Battery charge":    bat_charge,
            "Battery discharge": bat_discharge,
        }

        stats = prep._compute_stoch_stats(fake_results)

        per    = stats["stoch_per_profits"]
        prbs   = stats["stoch_probs"]
        spread = stats["stoch_profit_max"] - stats["stoch_profit_min"]

        print(f"  Expected : €{stats['stoch_profit_expected']:,.2f}")
        print(f"  Min/Max  : €{stats['stoch_profit_min']:,.2f} / €{stats['stoch_profit_max']:,.2f}")
        print(f"  Spread   : €{spread:,.2f}")
        if spread == 0.0:
            print("  *** PROBLEM: zero spread — all scenarios identical ***")
        else:
            print(f"  OK: genuine spread of €{spread:,.2f}")

        print("  Per-scenario:")
        scens, _ = prep.get_scenarios()
        pv_totals   = [np.sum(sc.get("PV Generation",   np.zeros(N))) for sc in scens]
        wind_totals = [np.sum(sc.get("Wind Generation", np.zeros(N))) for sc in scens]
        for i, (p, pr) in enumerate(zip(per, prbs)):
            print(f"    s{i+1:02d} pv={pv_totals[i]:6,.0f}kWh  wind={wind_totals[i]:6,.0f}kWh  "
                  f"profit=€{p:,.2f}")

        os.makedirs(results_dir, exist_ok=True)
        fname = os.path.join(results_dir, f"{name}.txt")
        with open(fname, "w") as f:
            f.write(f"Config: {name}\n{'='*60}\n")
            f.write(f"TEST METHOD : direct _compute_stoch_stats (no LP)\n")
            f.write(f"Expected profit : €{stats['stoch_profit_expected']:,.2f}\n")
            f.write(f"Min profit      : €{stats['stoch_profit_min']:,.2f}\n")
            f.write(f"Max profit      : €{stats['stoch_profit_max']:,.2f}\n")
            f.write(f"P10             : €{stats['stoch_profit_p10']:,.2f}\n")
            f.write(f"P90             : €{stats['stoch_profit_p90']:,.2f}\n")
            f.write(f"Spread (max-min): €{spread:,.2f}\n")
            f.write(f"PASS            : {'YES' if spread > 0 else 'NO — ZERO SPREAD'}\n")
            f.write("\nPer-scenario profits:\n")
            for i, (p, pr) in enumerate(zip(per, prbs)):
                f.write(f"  s{i+1:02d}  prob={pr:.4f}  "
                        f"pv={pv_totals[i]:,.0f}kWh  wind={wind_totals[i]:,.0f}kWh  "
                        f"profit=€{p:,.2f}\n")
        print(f"  Saved -> {fname}")
        return stats

    except Exception as e:
        print(f"  ERROR: {e}")
        traceback.print_exc()
        return None


def main():
    results_dir = os.path.join(HERE, "test_results_direct")
    price  = make_price()
    dem2kw = make_demand(2.0)
    dem4kw = make_demand(4.0)
    dem3kw = make_demand(3.0)

    N_SC = 10
    pv_scales   = np.linspace(0.60, 1.40, N_SC)
    wind_scales = np.linspace(0.50, 1.50, N_SC)

    all_stats = {}

    # ── Config 1: PV 5 kW + Battery 10 kWh, moderate demand ─────────────────
    inp1 = build_inputs(price, dem2kw,
                        pv_scens=[make_pv(5.0, s) for s in pv_scales],
                        bat_cap=10, bat_eff=0.92, bat_rp=5, buyback=0.4)
    bat_c1, bat_d1 = make_battery_schedule(10, 5, price)
    s1 = run_test("C1_PV5kW_Bat10kWh_Dem2kW", inp1, bat_c1, bat_d1, results_dir)
    if s1: all_stats["C1_PV5kW_Bat10kWh_Dem2kW"] = s1

    # ── Config 2: PV 5 kW + Battery 10 kWh, high demand ────────────────────
    inp2 = build_inputs(price, dem4kw,
                        pv_scens=[make_pv(5.0, s) for s in pv_scales],
                        bat_cap=10, bat_eff=0.92, bat_rp=5, buyback=0.4)
    s2 = run_test("C2_PV5kW_Bat10kWh_Dem4kW", inp2, bat_c1, bat_d1, results_dir)
    if s2: all_stats["C2_PV5kW_Bat10kWh_Dem4kW"] = s2

    # ── Config 3: Wind 3 kW + Battery 6 kWh ────────────────────────────────
    inp3 = build_inputs(price, dem2kw,
                        wind_scens=[make_wind(3.0, s, seed=i)
                                    for i, s in enumerate(wind_scales)],
                        bat_cap=6, bat_eff=0.90, bat_rp=3, buyback=0.35)
    bat_c3, bat_d3 = make_battery_schedule(6, 3, price)
    s3 = run_test("C3_Wind3kW_Bat6kWh_Dem2kW", inp3, bat_c3, bat_d3, results_dir)
    if s3: all_stats["C3_Wind3kW_Bat6kWh_Dem2kW"] = s3

    # ── Config 4: PV 3 kW + Wind 3 kW + Battery 8 kWh ──────────────────────
    inp4 = build_inputs(price, dem3kw,
                        pv_scens=[make_pv(3.0, s) for s in pv_scales],
                        wind_scens=[make_wind(3.0, s, seed=i)
                                    for i, s in enumerate(wind_scales)],
                        bat_cap=8, bat_eff=0.91, bat_rp=4, buyback=0.38)
    bat_c4, bat_d4 = make_battery_schedule(8, 4, price)
    s4 = run_test("C4_PV3kW_Wind3kW_Bat8kWh", inp4, bat_c4, bat_d4, results_dir)
    if s4: all_stats["C4_PV3kW_Wind3kW_Bat8kWh"] = s4

    # ── Config 5: PV 8 kW, no battery ───────────────────────────────────────
    inp5 = build_inputs(price, dem2kw,
                        pv_scens=[make_pv(8.0, s) for s in pv_scales],
                        buyback=0.45)
    zero_bat = np.zeros(N)
    s5 = run_test("C5_PV8kW_NoBattery_Dem2kW", inp5, zero_bat, zero_bat, results_dir)
    if s5: all_stats["C5_PV8kW_NoBattery_Dem2kW"] = s5

    # ── Summary ──────────────────────────────────────────────────────────────
    print("\n" + "="*74)
    print(f"{'Config':<44} {'Expected':>10} {'Spread':>10} {'PASS':>6}")
    print("-"*74)
    all_pass = True
    for cname, s in all_stats.items():
        spread = s["stoch_profit_max"] - s["stoch_profit_min"]
        ok = spread > 0
        all_pass = all_pass and ok
        print(f"{cname:<44} {s['stoch_profit_expected']:>10.2f} {spread:>10.2f} {'YES' if ok else 'NO':>6}")

    print("-"*74)
    print(f"Overall: {'ALL PASS' if all_pass else 'SOME FAILED'}")

    summary_path = os.path.join(results_dir, "SUMMARY.txt")
    os.makedirs(results_dir, exist_ok=True)
    with open(summary_path, "w") as f:
        f.write("DIRECT STOCHASTIC SPREAD TEST — SUMMARY\n")
        f.write("(Tests _compute_stoch_stats without running the LP)\n")
        f.write("="*74 + "\n")
        f.write(f"{'Config':<44} {'Expected':>10} {'Spread':>10} {'PASS':>6}\n")
        f.write("-"*74 + "\n")
        for cname, s in all_stats.items():
            spread = s["stoch_profit_max"] - s["stoch_profit_min"]
            ok = spread > 0
            f.write(f"{cname:<44} {s['stoch_profit_expected']:>10.2f} "
                    f"{spread:>10.2f} {'YES' if ok else 'NO':>6}\n")
        f.write("-"*74 + "\n")
        f.write(f"Overall: {'ALL PASS' if all_pass else 'SOME FAILED'}\n")
    print(f"\nSummary -> {summary_path}")


if __name__ == "__main__":
    main()
