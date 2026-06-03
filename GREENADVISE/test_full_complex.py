"""
Full-complexity headless test for the stochastic optimization.
Tests: PV + Wind + Battery + Heat Pump + Buffer Tank + Solar Collector
       + Thermal Demand + Electricity Demand.
Saves detailed logs to test_results_full/.
"""

import sys, os, traceback, time
import numpy as np

# Force UTF-8 on Windows to avoid cp1252 crashes with any stray unicode
import io
if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

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
from OptimizationStochastic import OptimizationInputPreparator as StochPrep

RESULTS_DIR = os.path.join(HERE, "test_results_full")
os.makedirs(RESULTS_DIR, exist_ok=True)

N = 8760
WEEK = 168

# --- Synthetic data generators -----------------------------------------------

def _tile(arr, n=N):
    return np.tile(arr, -(-n // len(arr)))[:n]

def make_price(base=0.20, amp=0.12):
    h = np.arange(WEEK) % 24
    p = base + amp * np.sin(np.pi * h / 12 - np.pi / 2)
    return _tile(np.clip(p, 0.04, 0.38))

def make_pv(cap_kw=5.0, scale=1.0):
    h = np.arange(WEEK) % 24
    profile = np.where((h > 6) & (h < 20),
                       np.clip(np.sin(np.pi * (h - 6) / 14), 0, None), 0.0)
    return _tile(profile * scale * cap_kw)

def make_wind(cap_kw=3.0, scale=1.0, seed=0):
    rng = np.random.default_rng(seed)
    cf = rng.uniform(0.05, 0.55, WEEK) * scale
    return _tile(np.clip(cf * cap_kw, 0, cap_kw))

def make_solar_collector(area_m2=10.0, scale=1.0):
    h = np.arange(WEEK) % 24
    irr = np.where((h > 6) & (h < 19),
                   np.clip(np.sin(np.pi * (h - 6) / 13), 0, None) * 0.8, 0.0)
    return _tile(irr * area_m2 * 0.55 * scale)

def make_elec_demand(base_kw=2.5):
    h = np.arange(WEEK) % 24
    d = np.ones(WEEK) * base_kw
    d[(h >= 7) & (h <= 9)]   *= 1.8
    d[(h >= 18) & (h <= 22)] *= 2.0
    d[(h >= 0)  & (h <= 5)]  *= 0.5
    return _tile(d)

def make_heat_demand(base_kw=3.0):
    d = np.arange(N)
    seasonal = 1.0 + 0.6 * np.cos(2 * np.pi * d / N)
    h_of_day = d % 24
    diurnal  = 0.8 + 0.4 * (h_of_day < 8).astype(float)
    return np.clip(base_kw * seasonal * diurnal, 0.3, 6.0)

def make_cool_demand(base_kw=1.5):
    d = np.arange(N)
    seasonal = 1.0 - 0.6 * np.cos(2 * np.pi * d / N)
    h_of_day = d % 24
    diurnal  = np.where((h_of_day >= 10) & (h_of_day <= 18), 1.5, 0.3)
    return np.clip(base_kw * seasonal * diurnal, 0.0, 4.0)

# --- Build stochastic inputs --------------------------------------------------

def build_stoch_inputs(n_sc=10, with_battery=True, with_thermal=True):
    price = make_price()
    edem  = make_elec_demand()
    heat  = make_heat_demand()
    cool  = make_cool_demand()

    pv_scales   = np.linspace(0.55, 1.45, n_sc)
    wind_scales = np.linspace(0.40, 1.60, n_sc)
    sc_scales   = np.linspace(0.60, 1.40, n_sc)

    stoch = {
        "PV Generation":      [make_pv(5.0, s)   for s in pv_scales],
        "Wind Generation":    [make_wind(3.0, s, seed=i) for i, s in enumerate(wind_scales)],
        "Price Data":         [price] * n_sc,
        "Electricity Demand": [edem]  * n_sc,
    }
    if with_thermal:
        stoch["Solar Collector Generation"] = [make_solar_collector(10.0, s) for s in sc_scales]
        stoch["Thermal Demand"] = [{"heating": heat, "cooling": cool}] * n_sc

    selected = {
        "Price Data":             price,
        "Electricity Demand":     edem,
        "PV Generation":          make_pv(5.0),
        "Wind Generation":        make_wind(3.0),
        "Grid Power Limit":       "1e9",
        "Price Data Inputs":      {"buyback": "0.40"},
        "stochastic":             stoch,
        "stochastic_probabilities": [1.0 / n_sc] * n_sc,
    }
    if with_battery:
        selected["Battery Inputs"] = {
            "capacity":    10.0,
            "efficiency":  92,
            "rated_power": 5.0,
        }
    if with_thermal:
        selected["Thermal Demand"]              = {"heating": heat, "cooling": cool}
        selected["Solar Collector Generation"]  = make_solar_collector(10.0)
        selected["Buffer Tank Inputs"] = {
            "capacity":         50.0,
            "rated power":      8.0,
            "retention factor": 97,
        }
        selected["Heat Pump Inputs"] = {
            "cop":               3.5,
            "eer":               3.0,
            "heating_capacity":  8.0,
            "cooling_capacity":  6.0,
        }
        selected["CO₂ Emissions"] = {
            "Thermal Emission Inputs": {"fuel_price": 0.08}
        }
    return selected

# --- Solver -------------------------------------------------------------------

def make_solver(seconds=300):
    cbc = get_cbc_executable_path()
    s = pye.SolverFactory("cbc", executable=cbc)
    s.options.update({
        "seconds":       seconds,
        "ratio":         0.01,
        "scaling":       3,        # full geometric scaling
        "maxIt":         8000000,  # cap LP simplex iterations
        "primalSimplex": "",       # primal simplex maintains primal feasibility if aborted
    })
    return s

# --- Run one optimization ----------------------------------------------------

def run_and_log(name, selected_inputs, solver_seconds=300, log=None):
    if log is None:
        log = []

    def L(msg):
        log.append(msg)
        print(msg)

    sep = "=" * 72
    L(f"\n{sep}")
    L(f"OPTIMIZATION: {name}")
    L(sep)

    try:
        t0   = time.time()
        prep = StochPrep(selected_inputs)
        scenarios, probs = prep.get_scenarios()
        n_sc = len(scenarios)
        L(f"  Scenarios : {n_sc}  (probs sum={sum(probs):.4f})")
        L("  Components present:")
        L(f"    PV           : {np.sum(prep.pv_generation):.0f} kWh/yr (mean scenario)")
        L(f"    Wind         : {np.sum(prep.wind_generation):.0f} kWh/yr (mean scenario)")
        L(f"    Solar Coll   : {np.sum(prep.solar_collector_generation):.0f} kWh-th/yr (mean)")
        L(f"    Elec Demand  : {np.sum(prep.electricity_demand):.0f} kWh/yr")
        L(f"    Heat Demand  : {np.sum(prep.heating_demand):.0f} kWh-th/yr")
        L(f"    Cool Demand  : {np.sum(prep.cooling_demand):.0f} kWh-th/yr")
        L(f"    Battery      : cap={prep.battery_capacity} kWh  eff={prep.battery_efficiency}  rp={prep.battery_rated_power} kW")
        L(f"    Buffer Tank  : cap={prep.buffer_capacity} kWh  rp={prep.buffer_rated_power} kW")
        L(f"    Heat Pump    : COP={prep.heat_pump_cop}  EER={prep.heat_pump_eer}"
          f"  heat_cap={prep.heat_pump_heating_capacity} kW  cool_cap={prep.heat_pump_cooling_capacity} kW")

        L("\n  Building model...")
        model = pye.ConcreteModel()
        model = prep.create_model_variables(model, prep)
        model = prep.add_constraints_and_objective(model)

        n_vars = sum(1 for _ in model.component_data_objects(pye.Var, active=True))
        n_cons = sum(1 for _ in model.component_data_objects(pye.Constraint, active=True))
        L(f"  Model vars  : {n_vars:,}")
        L(f"  Model cons  : {n_cons:,}")

        binary_vars = [v.name for v in model.component_data_objects(pye.Var, active=True)
                       if v.is_binary()]
        if binary_vars:
            L(f"  *** WARNING: {len(binary_vars)} Binary variables -- model is MILP! ***")
            L(f"       First 5: {binary_vars[:5]}")
        else:
            L("  Model type  : Pure LP (no binary variables) -- GOOD")

        L(f"\n  Solving (time limit={solver_seconds}s)...")
        t_solve = time.time()
        result  = make_solver(solver_seconds).solve(model, tee=False)
        elapsed = time.time() - t_solve
        L(f"  Solver time : {elapsed:.1f}s")
        L(f"  Status      : {result.solver.status}")
        L(f"  Termination : {result.solver.termination_condition}")

        ok_statuses = {pye.SolverStatus.ok, pye.SolverStatus.aborted}
        if result.solver.status not in ok_statuses:
            L("  FAILED -- no results.")
            return None, log

        # Extract results
        L("\n  Extracting results...")
        results = prep.extract_results(model)

        # Zero-solution guard
        energy_keys = ["PV -> Load", "Wind -> Load", "Grid -> Load", "Battery -> Load"]
        # results dict uses actual key names with Unicode arrows -- use original keys
        en_total = sum(
            np.sum(v) for k, v in results.items()
            if isinstance(v, np.ndarray) and any(tag in k for tag in
               ["PV", "Wind", "Grid", "Battery"])
               and "Load" in k and "->" not in k
        )
        # Actually check the raw result keys present
        energy_present = any(
            isinstance(results.get(k), np.ndarray) and np.any(results[k])
            for k in results
            if isinstance(k, str) and "Load" in k
        )
        if not energy_present:
            L("  *** ZERO SOLUTION -- all energy flows are zero! ***")
            return None, log

        # Per-scenario stats
        L("\n  Computing per-scenario statistics...")
        stoch_stats = prep._compute_stoch_stats(model)
        results.update(stoch_stats)

        t_total = time.time() - t0
        L(f"\n  --- RESULTS --- (total time: {t_total:.1f}s)")

        # Energy performance
        elec_dem_total = np.sum(prep.electricity_demand)
        # find own-gen and grid-import keys
        def rget(substr_a, substr_b=None):
            for k, v in results.items():
                if not isinstance(v, np.ndarray): continue
                if substr_a in k and (substr_b is None or substr_b in k):
                    return v
            return np.zeros(N)

        pv_load   = rget("PV",      "Load")
        wind_load = rget("Wind",    "Load")
        batt_load = rget("Battery", "Load")
        grid_load = rget("Grid",    "Load")
        own_gen   = np.sum(pv_load) + np.sum(wind_load) + np.sum(batt_load)
        grid_imp  = np.sum(grid_load)

        L(f"\n  ENERGY PERFORMANCE")
        L(f"    Elec demand total : {elec_dem_total:.0f} kWh")
        L(f"    Own generation    : {own_gen:.0f} kWh  ({100*own_gen/max(elec_dem_total,1):.1f}%)")
        L(f"    Grid import       : {grid_imp:.0f} kWh  ({100*grid_imp/max(elec_dem_total,1):.1f}%)")
        L(f"    PV to load        : {np.sum(pv_load):.0f} kWh")
        L(f"    Wind to load      : {np.sum(wind_load):.0f} kWh")
        L(f"    Battery to load   : {np.sum(batt_load):.0f} kWh")

        pv_grid   = rget("PV",   "Grid")
        wind_grid = rget("Wind", "Grid")
        batt_grid = rget("Battery", "Grid")
        L(f"    PV exported       : {np.sum(pv_grid):.0f} kWh")
        L(f"    Wind exported     : {np.sum(wind_grid):.0f} kWh")
        L(f"    Battery exported  : {np.sum(batt_grid):.0f} kWh")

        unmet_e = np.sum(rget("Unmet Electricity", ""))
        unmet_h = np.sum(rget("Unmet Heating",     ""))
        unmet_c = np.sum(rget("Unmet Cooling",      ""))
        L(f"    Unmet electricity : {unmet_e:.1f} kWh")
        L(f"    Unmet heating     : {unmet_h:.1f} kWh-th")
        L(f"    Unmet cooling     : {unmet_c:.1f} kWh-th")

        # Financial
        revenue_arr  = results.get("Revenue",    np.zeros(N))
        savings_arr  = results.get("Savings",    np.zeros(N))
        cost_arr     = results.get("Cost",       np.zeros(N))
        if not isinstance(revenue_arr, np.ndarray): revenue_arr = np.zeros(N)
        if not isinstance(savings_arr, np.ndarray): savings_arr = np.zeros(N)
        if not isinstance(cost_arr,    np.ndarray): cost_arr    = np.zeros(N)
        revenue = float(np.sum(revenue_arr))
        savings = float(np.sum(savings_arr))
        cost    = float(np.sum(cost_arr))
        net     = revenue + savings - cost

        L(f"\n  FINANCIAL (mean-scenario proxy)")
        L(f"    Revenue (export)  : EUR {revenue:.2f}")
        L(f"    Savings (self)    : EUR {savings:.2f}")
        L(f"    Cost (import)     : EUR {cost:.2f}")
        L(f"    Net annual        : EUR {net:.2f}")

        # Stochastic stats
        ss    = stoch_stats["stoch_profit_expected"]
        smin  = stoch_stats["stoch_profit_min"]
        smax  = stoch_stats["stoch_profit_max"]
        p10   = stoch_stats["stoch_profit_p10"]
        p90   = stoch_stats["stoch_profit_p90"]
        spread = smax - smin

        L(f"\n  STOCHASTIC STATS (probability-weighted from LP variables)")
        L(f"    Expected (SS)     : EUR {ss:.2f}")
        L(f"    Min / Max         : EUR {smin:.2f} / EUR {smax:.2f}")
        L(f"    P10 / P90         : EUR {p10:.2f} / EUR {p90:.2f}")
        L(f"    Spread (max-min)  : EUR {spread:.2f}")
        if spread < 1.0:
            L("    *** WARNING: near-zero spread -- scenarios may be degenerate ***")

        L(f"\n  PER-SCENARIO PROFITS:")
        per      = stoch_stats["stoch_per_profits"]
        pv_sums  = [np.sum(sc.get("PV Generation",  np.zeros(N))) for sc in scenarios]
        wnd_sums = [np.sum(sc.get("Wind Generation", np.zeros(N))) for sc in scenarios]
        for i, (p, pr, pv, wd) in enumerate(zip(per, probs, pv_sums, wnd_sums)):
            flag = "  *** ANOMALOUS ***" if abs(p) > abs(ss) * 20 + 1000 else ""
            L(f"    s{i+1:02d} prob={pr:.3f}  pv={pv:,.0f}kWh  wind={wd:,.0f}kWh  "
              f"profit=EUR {p:,.2f}{flag}")

        # --- Sanity checks ---
        L(f"\n  SANITY CHECKS")

        # 1. All scenarios should have non-trivial profit
        zero_profit_scens = [i+1 for i, p in enumerate(per) if abs(p) < 1.0]
        if zero_profit_scens:
            L(f"    FAIL: Scenarios with ~zero profit: {zero_profit_scens}")
        else:
            L("    PASS: All scenarios have non-zero profit")

        # 2. Simultaneous charge+discharge in expected value
        # NOTE: This check is on the EXPECTED VALUE (probability-weighted average across scenarios).
        # In a multi-scenario LP, scenario A may charge at hour t while scenario B discharges --
        # the average will show both non-zero. This is correct stochastic behavior, NOT a bug.
        charge_k    = next((k for k in results if "Battery charge" == k), None)
        discharge_k = next((k for k in results if "Battery discharge" == k), None)
        if charge_k and discharge_k:
            chg = results[charge_k]
            dch = results[discharge_k]
            simul = int(np.sum((chg > 0.01) & (dch > 0.01)))
            L(f"    INFO: Expected-value simultaneous charge+discharge at {simul} timesteps "
              f"(normal for multi-scenario LP -- different scenarios act differently)")
        else:
            L("    SKIP: No battery in this config")

        # 3. Electricity balance
        unmet_arr = rget("Unmet Electricity", "")
        supply    = pv_load + wind_load + batt_load + grid_load + unmet_arr
        bal_err   = float(np.max(np.abs(supply - prep.electricity_demand)))
        if bal_err > 0.1:
            L(f"    FAIL: Max electricity balance error = {bal_err:.4f} kWh")
        else:
            L(f"    PASS: Electricity balance holds (max error={bal_err:.2e} kWh)")

        # 4. Spread should be >0 when scenarios have different PV/wind
        pv_spread  = max(pv_sums) - min(pv_sums)
        wnd_spread = max(wnd_sums) - min(wnd_sums)
        if pv_spread > 100 or wnd_spread > 100:
            if spread < 10:
                L(f"    FAIL: Scenario generation spread (PV:{pv_spread:.0f}kWh, "
                  f"Wind:{wnd_spread:.0f}kWh) but profit spread only EUR {spread:.2f}")
            else:
                L(f"    PASS: Profit spread EUR {spread:.2f} reflects renewable variability")

        # 5. Per-scenario profit sign consistency
        if ss > 0 and smin < -abs(ss) * 2:
            L(f"    WARN: Expected profit is EUR {ss:.2f} but min scenario is EUR {smin:.2f} -- large downside")
        elif ss < 0:
            L(f"    WARN: Expected profit is NEGATIVE (EUR {ss:.2f})")

        return results, log

    except Exception as e:
        log.append(f"  EXCEPTION: {e}")
        log.append(traceback.format_exc())
        print(f"  EXCEPTION: {e}")
        traceback.print_exc()
        return None, log


# --- Main -------------------------------------------------------------------

def main():
    all_logs = []

    configs = [
        # Start simple, build up complexity
        ("C1_PV_Wind_Bat_4sc",
         build_stoch_inputs(n_sc=4, with_battery=True, with_thermal=False), 120),

        ("C2_PV_Wind_Bat_HP_Buf_SC_4sc",
         build_stoch_inputs(n_sc=4, with_battery=True, with_thermal=True), 180),

        ("C3_PV_Wind_Bat_10sc",
         build_stoch_inputs(n_sc=10, with_battery=True, with_thermal=False), 240),

        ("C4_Full_HP_Buf_SC_10sc",
         build_stoch_inputs(n_sc=10, with_battery=True, with_thermal=True), 600),
    ]

    summary_rows = []

    for cfg_name, inp, sec in configs:
        log = []
        results, log = run_and_log(cfg_name, inp, solver_seconds=sec, log=log)
        all_logs.extend(log)

        log_path = os.path.join(RESULTS_DIR, f"{cfg_name}.log")
        with open(log_path, "w", encoding="utf-8") as f:
            f.write("\n".join(log))
        print(f"\n  Log -> {log_path}")

        if results and "stoch_profit_expected" in results:
            ss   = results["stoch_profit_expected"]
            smin = results.get("stoch_profit_min", float("nan"))
            smax = results.get("stoch_profit_max", float("nan"))
            summary_rows.append((cfg_name, ss, smin, smax, smax - smin))
        else:
            summary_rows.append((cfg_name, float("nan"), float("nan"), float("nan"), float("nan")))

    # Summary
    print("\n" + "=" * 80)
    print(f"{'Config':<40} {'SS':>14} {'Min':>10} {'Max':>10} {'Spread':>10}")
    print("-" * 80)
    for row in summary_rows:
        name, ss, mn, mx, sp = row
        mark = "  *** ZERO/NaN ***" if (abs(ss) < 1.0 or (ss != ss)) else ""
        print(f"{name:<40} {ss:>14.2f} {mn:>10.2f} {mx:>10.2f} {sp:>10.2f}{mark}")

    summary_path = os.path.join(RESULTS_DIR, "SUMMARY.txt")
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write("FULL-COMPLEXITY STOCHASTIC TEST -- SUMMARY\n")
        f.write("=" * 80 + "\n")
        f.write(f"{'Config':<40} {'SS':>14} {'Min':>10} {'Max':>10} {'Spread':>10}\n")
        f.write("-" * 80 + "\n")
        for row in summary_rows:
            name, ss, mn, mx, sp = row
            f.write(f"{name:<40} {ss:>14.2f} {mn:>10.2f} {mx:>10.2f} {sp:>10.2f}\n")
        f.write("\n\nFULL LOGS:\n")
        f.write("\n".join(all_logs))
    print(f"\nSummary -> {summary_path}")


if __name__ == "__main__":
    main()
