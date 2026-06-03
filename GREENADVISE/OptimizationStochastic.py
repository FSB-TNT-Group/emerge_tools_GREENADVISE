import numpy as np

from PyQt5.QtCore import QThread, pyqtSignal, Qt, QTimer
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QProgressBar, QPushButton,
    QMessageBox, QLabel, QFrame, QSizePolicy, QSpacerItem, QWidget
)
import pyomo.environ as pye
from cbc_path_resolver import get_cbc_executable_path
import traceback


class OptimizationInputPreparator:
    unmet_penalty = 10000

    def __init__(self, selected_inputs):
        self.inputs = selected_inputs
        self.required_length = 8760
        self._check_required_inputs()
        self._initialize_defaults()
        self._unpack_inputs()

    def get_scenarios(self):
        stoch = self.inputs.get("stochastic", {})
        if not stoch:
            # nema stohastike -> 1 scenarij iz determinističkih inputa
            scenario = {}
            for k in ["Price Data", "PV Generation", "Wind Generation",
                      "Solar Collector Generation", "Electricity Demand",
                      "Sell Price", "Thermal Price"]:
                if k in self.inputs:
                    scenario[k] = self.inputs[k]
            if "Thermal Demand" in self.inputs:
                td = self.inputs["Thermal Demand"]
                scenario["Thermal Demand"] = {
                    "heating": td.get("heating"),
                    "cooling": td.get("cooling"),
                }
            return [scenario], [1.0]

        # Odredi broj scenarija iz prve liste koju nađemo (ili iz pod-liste u dictu)
        n_scenarios = None
        for key, val in stoch.items():
            if isinstance(val, list):
                n_scenarios = len(val)
                break
            elif isinstance(val, dict):
                for subk, subv in val.items():
                    if isinstance(subv, list):
                        n_scenarios = len(subv)
                        break
            if n_scenarios is not None:
                break
        if n_scenarios is None:
            raise ValueError("Invalid 'stochastic' structure: no list-of-scenarios found.")

        scenarios = []
        for s in range(n_scenarios):
            sc = {}
            for key, val in stoch.items():
                if isinstance(val, list):
                    sc[key] = val[s]
                elif isinstance(val, dict):
                    sub = {}
                    for subk, subv in val.items():
                        if isinstance(subv, list):
                            sub[subk] = subv[s]
                        else:
                            sub[subk] = subv
                    sc[key] = sub
                else:
                    sc[key] = val

            # deterministički fallback za ključeve koji nisu u 'stochastic'
            for k in ["Price Data", "PV Generation", "Wind Generation",
                      "Solar Collector Generation", "Electricity Demand",
                      "Sell Price", "Thermal Price"]:
                if k not in sc and k in self.inputs:
                    sc[k] = self.inputs[k]
            if "Thermal Demand" not in sc and "Thermal Demand" in self.inputs:
                td = self.inputs["Thermal Demand"]
                sc["Thermal Demand"] = {
                    "heating": td.get("heating"),
                    "cooling": td.get("cooling"),
                }

            scenarios.append(sc)

        # Use Heitsch-Römisch probabilities from scenario generator when available,
        # otherwise fall back to equal weights.
        hr_probs = self.inputs.get("stochastic_probabilities")
        if hr_probs and len(hr_probs) == n_scenarios:
            probs = list(hr_probs)
        else:
            probs = [1.0 / n_scenarios] * n_scenarios
        return scenarios, probs

    def _check_required_inputs(self):
        if "Price Data" not in self.inputs:
            raise ValueError("Missing 'Price Data' input.")

        if not any(k in self.inputs for k in ["Electricity Demand", "Thermal Demand", "Thermal + Electricity Demand"]):
            raise ValueError("At least one type of demand is required.")

    def _initialize_defaults(self):
        self.pv_generation = np.zeros(self.required_length)
        self.wind_generation = np.zeros(self.required_length)
        self.pv_capacity = 0
        self.wind_capacity = 0

        self.battery_capacity = self.battery_efficiency = self.battery_rated_power = None
        self.buffer_capacity = self.buffer_rated_power = self.buffer_retention = None

        self.heat_pump_cop = 1
        self.heat_pump_eer = 1
        self.heat_pump_heating_capacity = self.heat_pump_cooling_capacity = None

        self.heating_demand = np.zeros(self.required_length)
        self.cooling_demand = np.zeros(self.required_length)
        self.electricity_demand = np.zeros(self.required_length)

        self.buy_price = np.zeros(self.required_length)
        self.sell_price = np.zeros(self.required_length)
        self.thermal_price = np.zeros(self.required_length)

        self.grid_limit = float('inf')
        self.solar_collector_generation = np.zeros(self.required_length)

        # NOVO: buyback faktor (ako je konstantan)
        self.buyback_factor = None

    def _to_float_array(self, val):
        arr = np.array(val, dtype=float)
        if arr.shape[0] != self.required_length:
            raise ValueError(f"Expected array of length {self.required_length}, got {arr.shape[0]}")
        return arr

    def _unpack_inputs(self):
        try:
           self.grid_limit = float(self.inputs["Grid Power Limit"])
        except ValueError:
           raise ValueError(f"Invalid grid power limit: {self.grid_limit}")

        price_data = self.inputs["Price Data"]
        self.buy_price = self._to_float_array(price_data)

        price_inputs = self.inputs.get("Price Data Inputs", {})
        buyback_str = price_inputs.get("buyback")
        emissions = self.inputs.get("CO₂ Emissions", {})
        thermal_emission = emissions.get("Thermal Emission Inputs", {})

        if "Thermal Demand" in self.inputs:
            fuel_price_raw = thermal_emission.get("fuel_price", 0)
            try:
                thermal_price = float(fuel_price_raw)
            except (ValueError, TypeError):
                thermal_price = 0.0
            self.thermal_price = np.ones(self.required_length) * thermal_price
        else:
            self.thermal_price = np.zeros(self.required_length)

        if buyback_str is not None:
            try:
                self.buyback_factor = float(buyback_str)
                self.sell_price = self.buy_price * self.buyback_factor
            except (ValueError, TypeError):
                raise ValueError(f"Invalid buyback factor: {buyback_str}")
        # ako nema buyback-a, sell_price ostaje što jest (npr. 0) ili ga daješ kroz scenarije

        skip_thermal = "Thermal + Electricity Demand" in self.inputs

        if skip_thermal:
            self.electricity_demand = self._to_float_array(self.inputs["Thermal + Electricity Demand"])
        else:
            td = self.inputs.get("Thermal Demand", {})
            if "heating" in td:
                self.heating_demand = self._to_float_array(td["heating"])
            if "cooling" in td:
                self.cooling_demand = self._to_float_array(td["cooling"])

            if "Electricity Demand" in self.inputs:
                self.electricity_demand = self._to_float_array(self.inputs["Electricity Demand"])

        if "PV Generation" in self.inputs:
            self.pv_generation = self._to_float_array(self.inputs["PV Generation"])
            self.pv_capacity = self.pv_generation.max()

        if "Wind Generation" in self.inputs:
            self.wind_generation = self._to_float_array(self.inputs["Wind Generation"])
            self.wind_capacity = self.wind_generation.max()

        if "Solar Collector Generation" in self.inputs:
            self.solar_collector_generation = self._to_float_array(self.inputs["Solar Collector Generation"])

        if "Battery Inputs" in self.inputs:
            b = self.inputs["Battery Inputs"]
            self.battery_capacity = float(b.get("capacity", 0))
            self.battery_efficiency = float(b.get("efficiency", 100)) / 100.0
            self.battery_rated_power = float(b.get("rated_power", 0))

        if not skip_thermal:
            if "Buffer Tank Inputs" in self.inputs:
                buf = self.inputs["Buffer Tank Inputs"]
                self.buffer_capacity = float(buf.get("capacity", 0))
                self.buffer_rated_power = float(buf.get("rated power", 0))
                self.buffer_retention = float(buf.get("retention factor", 100)) / 100.0

            if "Heat Pump Inputs" in self.inputs:
                hp = self.inputs["Heat Pump Inputs"]
                self.heat_pump_cop = float(hp.get("cop", 1))
                self.heat_pump_eer = float(hp.get("eer", 1))
                self.heat_pump_heating_capacity = float(hp.get("heating_capacity", 0))
                self.heat_pump_cooling_capacity = float(hp.get("cooling_capacity", 0))


    def create_model_variables(self, model, preparator):
        import pyomo.environ as pye
    
        scenarios, probs = self.get_scenarios()
        S = range(len(scenarios))
        T = range(1, 8761)
    
        model = pye.ConcreteModel()
        model.T = pye.Set(initialize=T, ordered=True)
        model.S = pye.Set(initialize=S, ordered=True)
    
        # PV
        if preparator.pv_generation.any():
            model.pv_to_load = pye.Var(model.T, model.S, domain=pye.NonNegativeReals)
            model.pv_to_grid = pye.Var(model.T, model.S, domain=pye.NonNegativeReals)
            if preparator.battery_capacity:
                model.pv_to_batt = pye.Var(model.T, model.S, domain=pye.NonNegativeReals)
            if preparator.heat_pump_heating_capacity:
                model.pv_to_hp_heat = pye.Var(model.T, model.S, domain=pye.NonNegativeReals)
            if preparator.heat_pump_cooling_capacity:
                model.pv_to_hp_cool = pye.Var(model.T, model.S, domain=pye.NonNegativeReals)
            if preparator.electricity_demand.any():
                model.pv_lost = pye.Var(model.T, model.S, domain=pye.NonNegativeReals)
    
        # WIND
        if preparator.wind_generation.any():
            model.wind_to_load = pye.Var(model.T, model.S, domain=pye.NonNegativeReals)
            model.wind_to_grid = pye.Var(model.T, model.S, domain=pye.NonNegativeReals)
            if preparator.battery_capacity:
                model.wind_to_batt = pye.Var(model.T, model.S, domain=pye.NonNegativeReals)
            if preparator.heat_pump_heating_capacity:
                model.wind_to_hp_heat = pye.Var(model.T, model.S, domain=pye.NonNegativeReals)
            if preparator.heat_pump_cooling_capacity:
                model.wind_to_hp_cool = pye.Var(model.T, model.S, domain=pye.NonNegativeReals)
            if preparator.electricity_demand.any():
                model.wind_lost = pye.Var(model.T, model.S, domain=pye.NonNegativeReals)
    
        # BATT
        if preparator.battery_capacity:
            if preparator.heat_pump_heating_capacity:
                model.batt_to_hp_heat = pye.Var(model.T, model.S, domain=pye.NonNegativeReals)
            if preparator.heat_pump_cooling_capacity:
                model.batt_to_hp_cool = pye.Var(model.T, model.S, domain=pye.NonNegativeReals)
    
            model.grid_to_batt = pye.Var(model.T, model.S, domain=pye.NonNegativeReals)
            model.batt_to_load = pye.Var(model.T, model.S, domain=pye.NonNegativeReals)
            model.batt_to_grid = pye.Var(model.T, model.S, domain=pye.NonNegativeReals)
            model.charge = pye.Var(model.T, model.S, domain=pye.NonNegativeReals)
            model.discharge = pye.Var(model.T, model.S, domain=pye.NonNegativeReals)
            model.batt_soe = pye.Var(range(0, 8761), model.S, domain=pye.NonNegativeReals,
                                     bounds=(0, preparator.battery_capacity))
            for s in S:
                model.batt_soe[0, s].fix(0)
    
        # GRID
        # (samo potrošnja na load + unmet; NE definiramo grid_to_hp_* ovdje!)
        if preparator.electricity_demand.any():
            model.grid_to_load = pye.Var(model.T, model.S, domain=pye.NonNegativeReals)
            model.unmet_electricity_demand = pye.Var(model.T, model.S, domain=pye.NonNegativeReals)
    
        # THERMAL UNMET
        if preparator.heating_demand.any() and preparator.cooling_demand.any():
            model.unmet_heating_demand = pye.Var(model.T, model.S, domain=pye.NonNegativeReals)
            model.unmet_cooling_demand = pye.Var(model.T, model.S, domain=pye.NonNegativeReals)
        elif preparator.heating_demand.any():
            model.unmet_heating_demand = pye.Var(model.T, model.S, domain=pye.NonNegativeReals)
        else:
            model.unmet_cooling_demand = pye.Var(model.T, model.S, domain=pye.NonNegativeReals)
    
        # HP
        if preparator.heat_pump_heating_capacity or preparator.heat_pump_cooling_capacity:
            if preparator.heat_pump_heating_capacity:
                model.electricity_to_hp_heat = pye.Var(model.T, model.S, domain=pye.NonNegativeReals)
                model.hp_heat_to_load = pye.Var(
                    model.T, model.S, domain=pye.NonNegativeReals,
                    bounds=(0, preparator.heat_pump_heating_capacity)
                )
                # Moved here: grid_to_hp_heat uvijek postoji kad postoji HP heating
                model.grid_to_hp_heat = pye.Var(model.T, model.S, domain=pye.NonNegativeReals)
    
            if preparator.heat_pump_cooling_capacity:
                model.electricity_to_hp_cool = pye.Var(model.T, model.S, domain=pye.NonNegativeReals)
                model.hp_cool_to_load = pye.Var(
                    model.T, model.S, domain=pye.NonNegativeReals,
                    bounds=(0, preparator.heat_pump_cooling_capacity)
                )
                # Moved here: grid_to_hp_cool uvijek postoji kad postoji HP cooling
                model.grid_to_hp_cool = pye.Var(model.T, model.S, domain=pye.NonNegativeReals)
    
            if preparator.buffer_capacity:
                model.hp_to_buffer = pye.Var(model.T, model.S, domain=pye.NonNegativeReals)
    
        # SC
        if preparator.solar_collector_generation.any():
            model.solar_to_buffer = pye.Var(model.T, model.S, domain=pye.NonNegativeReals)
            model.solar_curtail = pye.Var(model.T, model.S, domain=pye.NonNegativeReals)
    
        # BT
        if preparator.buffer_capacity:
            model.buffer_to_load = pye.Var(model.T, model.S, domain=pye.NonNegativeReals)
            model.buffer_charge = pye.Var(model.T, model.S, domain=pye.NonNegativeReals)
            model.buffer_discharge = pye.Var(model.T, model.S, domain=pye.NonNegativeReals)
            model.buffer_soe = pye.Var(range(0, 8761), model.S, domain=pye.NonNegativeReals,
                                       bounds=(0, preparator.buffer_capacity))
            for s in S:
                model.buffer_soe[0, s].fix(0)
    
        return model


    def add_constraints_and_objective(self, model):
        import pyomo.environ as pye
        T = model.T
        S = model.S
        scenarios, probs = self.get_scenarios()

        # GRID POWER LIMIT
        if (hasattr(model, "grid_to_load") 
            or hasattr(model, "grid_to_batt")
            or hasattr(model, "grid_to_hp")
            or hasattr(model, "pv_to_grid") 
            or hasattr(model, "wind_to_grid") 
            or hasattr(model, "batt_to_grid")):

            def grid_power_limit(m, t, s):
                limit = 0
                if hasattr(m, "grid_to_load"):      limit += m.grid_to_load[t, s]
                if hasattr(m, "grid_to_batt"):      limit += m.grid_to_batt[t, s]
                if hasattr(m, "grid_to_hp_heat"):   limit += m.grid_to_hp_heat[t, s]
                if hasattr(m, "grid_to_hp_cool"):   limit += m.grid_to_hp_cool[t, s]
                if hasattr(m, "pv_to_grid"):        limit += m.pv_to_grid[t, s]
                if hasattr(m, "wind_to_grid"):      limit += m.wind_to_grid[t, s]
                if hasattr(m, "batt_to_grid"):      limit += m.batt_to_grid[t, s]
                return limit <= self.grid_limit
            model.grid_power_limit = pye.Constraint(T, S, rule=grid_power_limit)

        # POWER BALLANCE
        if (hasattr(model, "pv_to_load") 
            or hasattr(model, "batt_to_load") 
            or hasattr(model, "grid_to_load") 
            or hasattr(model, "wind_to_load")):

            def power_balance(m, t, s):
                scenario = scenarios[s]
                supply = 0
                if hasattr(m, "pv_to_load"):
                    supply += m.pv_to_load[t, s]
                if hasattr(m, "batt_to_load"):
                    supply += m.batt_to_load[t, s]
                if hasattr(m, "grid_to_load"):
                    supply += m.grid_to_load[t, s]
                if hasattr(m, "wind_to_load"):
                    supply += m.wind_to_load[t, s]
                if hasattr(m, "unmet_electricity_demand"):
                    supply += m.unmet_electricity_demand[t, s]
                return supply == scenario["Electricity Demand"][t - 1]
            model.power_balance = pye.Constraint(T, S, rule=power_balance)

        # PV ALLOCATION
        if hasattr(model, "pv_to_load"):
            def pv_allocation(m, t, s):
                scenario = scenarios[s]
                total = m.pv_to_load[t, s]
                if hasattr(m, "pv_to_batt"): total += m.pv_to_batt[t, s]
                if hasattr(m, "pv_to_grid"): total += m.pv_to_grid[t, s]
                if hasattr(m, "pv_to_hp_heat"): total += m.pv_to_hp_heat[t, s]
                if hasattr(m, "pv_to_hp_cool"): total += m.pv_to_hp_cool[t, s]
                if hasattr(m, "pv_lost"): total += m.pv_lost[t, s]
                return total == scenario.get("PV Generation", np.zeros(self.required_length))[t - 1]
            model.pv_allocation = pye.Constraint(T, S, rule=pv_allocation)

        # WIND ALLOCATION
        if hasattr(model, "wind_to_load"):
            def wind_allocation(m, t, s):
                scenario = scenarios[s]
                total = m.wind_to_load[t, s]
                if hasattr(m, "wind_to_batt"): total += m.wind_to_batt[t, s]
                if hasattr(m, "wind_to_grid"): total += m.wind_to_grid[t, s]
                if hasattr(m, "wind_to_hp_heat"): total += m.wind_to_hp_heat[t, s]
                if hasattr(m, "wind_to_hp_cool"): total += m.wind_to_hp_cool[t, s]
                if hasattr(m, "wind_lost"): total += m.wind_lost[t, s]
                return total == scenario.get("Wind Generation", np.zeros(self.required_length))[t - 1]
            model.wind_allocation = pye.Constraint(T, S, rule=wind_allocation)

        # BATT CHARGE LINK
        if hasattr(model, "charge"):
            def battery_charge_link(m, t, s):
                total = 0
                if hasattr(m, "pv_to_batt"): total += m.pv_to_batt[t, s]
                if hasattr(m, "grid_to_batt"): total += m.grid_to_batt[t, s]
                if hasattr(m, "wind_to_batt"): total += m.wind_to_batt[t, s]
                return m.charge[t, s] == total
            model.charge_link = pye.Constraint(T, S, rule=battery_charge_link)

        # BATT DISCHARGE LINK
        if hasattr(model, "discharge"):
            def battery_discharge_link(m, t, s):
                total = 0
                if hasattr(m, "batt_to_load"): total += m.batt_to_load[t, s]
                if hasattr(m, "batt_to_grid"): total += m.batt_to_grid[t, s]
                if hasattr(m, "batt_to_hp_heat"): total += m.batt_to_hp_heat[t, s]
                if hasattr(m, "batt_to_hp_cool"): total += m.batt_to_hp_cool[t, s]
                return m.discharge[t, s] == total
            model.discharge_link = pye.Constraint(T, S, rule=battery_discharge_link)

        # BATT SOE BALLANCE
        if hasattr(model, "batt_soe"):
            def soe_balance(m, t, s):
                return m.batt_soe[t, s] == m.batt_soe[t - 1, s] + m.charge[t, s] * self.battery_efficiency - m.discharge[t, s] / self.battery_efficiency
            model.soe_balance = pye.Constraint(T, S, rule=soe_balance)

        if hasattr(model, "charge"):
            model.charge_limit = pye.Constraint(T, S, rule=lambda m, t, s: m.charge[t, s] <= self.battery_rated_power)
            model.discharge_limit = pye.Constraint(T, S, rule=lambda m, t, s: m.discharge[t, s] <= self.battery_rated_power)
            model.no_simul_batt = pye.Constraint(T, S, rule=lambda m, t, s: m.charge[t, s] + m.discharge[t, s] <= self.battery_rated_power)

        # HP ALLOCATION
        if hasattr(model, "electricity_to_hp_heat"):
            def heat_output_rule(m, t, s):
                return m.hp_heat_to_load[t, s] == self.heat_pump_cop * m.electricity_to_hp_heat[t, s]
            model.heat_output_eq_heat = pye.Constraint(T, S, rule=heat_output_rule)

        if hasattr(model, "electricity_to_hp_cool"):
            def cool_output_rule(m, t, s):
                return m.hp_cool_to_load[t, s] == self.heat_pump_eer * m.electricity_to_hp_cool[t, s]
            model.heat_output_eq_cool = pye.Constraint(T, S, rule=cool_output_rule)

        # HEATING DEMAND BALLANCE
        if np.sum(self.heating_demand) > 0:
            def heat_balance_rule(m, t, s):
                scenario = scenarios[s]
                hp_output = m.hp_heat_to_load[t, s] if hasattr(m, "hp_heat_to_load") else 0
                buffer_out = m.buffer_to_load[t, s] if hasattr(m, "buffer_to_load") else 0
                buffer_in = m.hp_to_buffer[t, s] if hasattr(m, "hp_to_buffer") else 0
                unmet = m.unmet_heating_demand[t, s] if hasattr(m, "unmet_heating_demand") else 0
                demand = scenario.get("Thermal Demand", {}).get("heating", np.zeros(self.required_length))[t - 1]
                return hp_output + buffer_out + unmet == demand + buffer_in
            model.heat_balance = pye.Constraint(T, S, rule=heat_balance_rule)

        # COOLING DEMAND BALLANCE
        if np.sum(self.cooling_demand) > 0:
            def cool_balance_rule(m, t, s):
                scenario = scenarios[s]
                hp_output = m.hp_cool_to_load[t, s] if hasattr(m, "hp_cool_to_load") else 0
                unmet = m.unmet_cooling_demand[t, s] if hasattr(m, "unmet_cooling_demand") else 0
                demand = scenario.get("Thermal Demand", {}).get("cooling", np.zeros(self.required_length))[t - 1]
                return hp_output + unmet == demand
            model.cool_balance = pye.Constraint(T, S, rule=cool_balance_rule)

        # SC ALLOCATION
        if hasattr(model, "solar_to_buffer"):
            def solar_rule(m, t, s):
                scenario = scenarios[s]
                generation = scenario.get("Solar Collector Generation", np.zeros(self.required_length))[t - 1]
                return generation == m.solar_to_buffer[t, s] + m.solar_curtail[t, s]
            model.solar_allocation = pye.Constraint(T, S, rule=solar_rule)

        # BUFFER TANK SOE BALLANCE
        if hasattr(model, "buffer_soe"):
            def heat_soe_dynamics_rule(m, t, s):
                hp_buf = m.hp_to_buffer[t, s] if hasattr(m, "hp_to_buffer") else 0
                solar_buf = m.solar_to_buffer[t, s] if hasattr(m, "solar_to_buffer") else 0
                return m.buffer_soe[t, s] == self.buffer_retention * m.buffer_soe[t - 1, s] + hp_buf + solar_buf - m.buffer_to_load[t, s]
            model.heat_soe_balance = pye.Constraint(T, S, rule=heat_soe_dynamics_rule)

        # BT CHARGE LIMIT: total power flowing INTO the buffer must not exceed rated charge rate.
        # solar_to_buffer is the portion of collector output that actually enters the buffer.
        # solar_curtail is wasted solar (not going to buffer).  Do NOT subtract curtailment from
        # the inflow -- that was a sign-error leading to an under-constrained buffer charge.
        if hasattr(model, "hp_to_buffer") or hasattr(model, "solar_to_buffer"):
            def heat_charge_limit_rule(m, t, s):
                hp  = m.hp_to_buffer[t, s]     if hasattr(m, "hp_to_buffer")     else 0
                sol = m.solar_to_buffer[t, s]  if hasattr(m, "solar_to_buffer")  else 0
                return hp + sol <= self.buffer_rated_power
            model.heat_ch_limit = pye.Constraint(T, S, rule=heat_charge_limit_rule)

        # BT DISCHARGE LIMIT
        if hasattr(model, "buffer_to_load"):
            def heat_discharge_limit_rule(m, t, s):
                return m.buffer_to_load[t, s] <= self.buffer_rated_power
            model.heat_dch_limit = pye.Constraint(T, S, rule=heat_discharge_limit_rule)

        # HP ELECTRICAL BOUNDS
        if hasattr(model, "electricity_to_hp_heat"):
            def elec_bound_rule_heat(m, t, s):
                return m.electricity_to_hp_heat[t, s] <= self.heat_pump_heating_capacity / self.heat_pump_cop
            model.elec_bound_heat = pye.Constraint(T, S, rule=elec_bound_rule_heat)

        if hasattr(model, "electricity_to_hp_cool"):
            def elec_bound_rule_cool(m, t, s):
                return m.electricity_to_hp_cool[t, s] <= self.heat_pump_cooling_capacity / self.heat_pump_eer
            model.elec_bound_cool = pye.Constraint(T, S, rule=elec_bound_rule_cool)

        # HP HEATING ELECTRICITY BOUND
        if (hasattr(model, "electricity_to_hp_heat") and
            (hasattr(model, "grid_to_hp_heat") or hasattr(model, "pv_to_hp_heat")
             or hasattr(model, "wind_to_hp_heat") or hasattr(model, "batt_to_hp_heat"))):
        
            def hp_heat_power_allocation_rule(m, t, s):
                total = 0
                if hasattr(m, "grid_to_hp_heat"): total += m.grid_to_hp_heat[t, s]
                if hasattr(m, "pv_to_hp_heat"):   total += m.pv_to_hp_heat[t, s]
                if hasattr(m, "wind_to_hp_heat"): total += m.wind_to_hp_heat[t, s]
                if hasattr(m, "batt_to_hp_heat"): total += m.batt_to_hp_heat[t, s]
                return m.electricity_to_hp_heat[t, s] == total
            model.hp_heat_allocation = pye.Constraint(T, S, rule=hp_heat_power_allocation_rule)

        # HP COOLING ELECTRICITY BOUND
        if (hasattr(model, "electricity_to_hp_cool") and
            (hasattr(model, "grid_to_hp_cool") or hasattr(model, "pv_to_hp_cool")
             or hasattr(model, "wind_to_hp_cool") or hasattr(model, "batt_to_hp_cool"))):

            def hp_cool_power_allocation_rule(m, t, s):
                total = 0
                if hasattr(m, "grid_to_hp_cool"): total += m.grid_to_hp_cool[t, s]
                if hasattr(m, "pv_to_hp_cool"):   total += m.pv_to_hp_cool[t, s]
                if hasattr(m, "wind_to_hp_cool"): total += m.wind_to_hp_cool[t, s]
                if hasattr(m, "batt_to_hp_cool"): total += m.batt_to_hp_cool[t, s]
                return m.electricity_to_hp_cool[t, s] == total
            model.hp_cool_allocation = pye.Constraint(T, S, rule=hp_cool_power_allocation_rule)

        # Update Objective
        def objective_rule(m):
            total_profit = 0
            scenarios, probs = self.get_scenarios()

            for s in m.S:
                scenario = scenarios[s]
                profit = 0

                for t in m.T:
                    buy = scenario["Price Data"][t - 1]
                    sell = self.sell_price[t - 1]  # moze poslije stohastika
                    thermal_price = self.thermal_price[t - 1]  # isto scenario-based

                    # REVENUE
                    if hasattr(m, "pv_to_grid"):
                        profit += m.pv_to_grid[t, s] * sell
                    if hasattr(m, "batt_to_grid"):
                        profit += m.batt_to_grid[t, s] * sell
                    if hasattr(m, "wind_to_grid"):
                        profit += m.wind_to_grid[t, s] * sell

                    if hasattr(m, "pv_to_load"):        profit += m.pv_to_load[t, s] * buy
                    if hasattr(m, "pv_to_hp_heat"):     profit += m.pv_to_hp_heat[t, s] * buy
                    if hasattr(m, "pv_to_hp_cool"):     profit += m.pv_to_hp_cool[t, s] * buy
                    if hasattr(m, "wind_to_load"):      profit += m.wind_to_load[t, s] * buy
                    if hasattr(m, "wind_to_hp_heat"):   profit += m.wind_to_hp_heat[t, s] * buy
                    if hasattr(m, "wind_to_hp_cool"):   profit += m.wind_to_hp_cool[t, s] * buy
                    if hasattr(m, "batt_to_load"):      profit += m.batt_to_load[t, s] * buy
                    if hasattr(m, "batt_to_hp_heat"):   profit += m.batt_to_hp_heat[t, s] * buy
                    if hasattr(m, "batt_to_hp_cool"):   profit += m.batt_to_hp_cool[t, s] * buy
                    if hasattr(m, "solar_to_buffer"):   profit += m.solar_to_buffer[t, s] * thermal_price

                    # COST
                    if hasattr(m, "grid_to_load"):      profit -= m.grid_to_load[t, s] * buy
                    if hasattr(m, "grid_to_batt"):      profit -= m.grid_to_batt[t, s] * buy
                    if hasattr(m, "grid_to_hp_heat"):   profit -= m.grid_to_hp_heat[t, s] * buy
                    if hasattr(m, "grid_to_hp_cool"):   profit -= m.grid_to_hp_cool[t, s] * buy

                    # UNMET PENALITIES
                    if hasattr(m, "unmet_electricity_demand"):
                        profit -= self.unmet_penalty * m.unmet_electricity_demand[t, s]
                    if hasattr(m, "unmet_heating_demand"):
                        profit -= self.unmet_penalty * m.unmet_heating_demand[t, s]
                    if hasattr(m, "unmet_cooling_demand"):
                        profit -= self.unmet_penalty * m.unmet_cooling_demand[t, s]
                    if hasattr(m, "pv_lost"):
                        profit -= self.unmet_penalty * m.pv_lost[t, s]
                    if hasattr(m, "wind_lost"):
                        profit -= self.unmet_penalty * m.wind_lost[t, s]

                total_profit += probs[s] * profit

            return total_profit

        model.obj = pye.Objective(rule=objective_rule, sense=pye.maximize)
        return model

    def _compute_stoch_stats(self, model):
        """Per-scenario profits read directly from the LP's per-scenario decision variables.

        Each scenario in the stochastic LP has its own independently optimised dispatch
        (no non-anticipativity constraints on operation), so the correct SS is the
        probability-weighted sum of each scenario's actual LP profit — not a forward
        simulation with the averaged schedule, which would be suboptimal for every scenario.
        """
        import pyomo.environ as pye
        scenarios, probs = self.get_scenarios()
        T_range = range(1, 8761)

        def v(var_name, t, s):
            if not hasattr(model, var_name):
                return 0.0
            try:
                val = pye.value(getattr(model, var_name)[t, s])
                return float(val) if val is not None else 0.0
            except Exception:
                return 0.0

        per_profits = []
        for s_idx, sc in enumerate(scenarios):
            buy_p = np.array(sc.get("Price Data", np.zeros(8760)), dtype=float)
            if "Sell Price" in sc:
                sell_p = np.array(sc["Sell Price"], dtype=float)
            elif self.buyback_factor is not None:
                sell_p = buy_p * self.buyback_factor
            else:
                sell_p = np.zeros(8760)
            thermal_p = self.thermal_price

            profit = 0.0
            for t in T_range:
                b  = buy_p[t - 1]
                sp = sell_p[t - 1]
                tp = thermal_p[t - 1]

                # Revenue (exports to grid)
                profit += v("pv_to_grid",   t, s_idx) * sp
                profit += v("wind_to_grid", t, s_idx) * sp
                profit += v("batt_to_grid", t, s_idx) * sp

                # Savings (self-consumption at avoided import price)
                profit += v("pv_to_load",      t, s_idx) * b
                profit += v("pv_to_hp_heat",   t, s_idx) * b
                profit += v("pv_to_hp_cool",   t, s_idx) * b
                profit += v("wind_to_load",    t, s_idx) * b
                profit += v("wind_to_hp_heat", t, s_idx) * b
                profit += v("wind_to_hp_cool", t, s_idx) * b
                profit += v("batt_to_load",    t, s_idx) * b
                profit += v("batt_to_hp_heat", t, s_idx) * b
                profit += v("batt_to_hp_cool", t, s_idx) * b
                profit += v("solar_to_buffer", t, s_idx) * tp

                # Cost (imports from grid)
                profit -= v("grid_to_load",     t, s_idx) * b
                profit -= v("grid_to_batt",     t, s_idx) * b
                profit -= v("grid_to_hp_heat",  t, s_idx) * b
                profit -= v("grid_to_hp_cool",  t, s_idx) * b

            per_profits.append(profit)

        ss = sum(probs[s] * per_profits[s] for s in range(len(scenarios)))
        return {
            "stoch_profit_expected": ss,
            "stoch_profit_min":      min(per_profits),
            "stoch_profit_max":      max(per_profits),
            "stoch_profit_p10":      float(np.percentile(per_profits, 10)),
            "stoch_profit_p90":      float(np.percentile(per_profits, 90)),
            "stoch_n_scenarios":     len(scenarios),
            "stoch_per_profits":     per_profits,
            "stoch_probs":           probs,
        }

    def extract_results(self, model):
        import pyomo.environ as pye
        results = {}

        T_range = range(1, 8761)
        scenarios, probs = self.get_scenarios()
        S_range = range(len(scenarios))
    
        # helperi za scenarijski prosjek
        def _scen_avg_simple(key):
            try:
                arrays = []
                for s, sc in enumerate(scenarios):
                    if key not in sc:
                        return None
                    arr = np.array(sc[key], dtype=float)
                    if arr.shape[0] != self.required_length:
                        return None
                    arrays.append(arr * probs[s])
                return sum(arrays)
            except Exception:
                return None
    
        def _scen_avg_thermal(subkey):
            try:
                arrays = []
                found_any = False
                for s, sc in enumerate(scenarios):
                    td = sc.get("Thermal Demand")
                    if not isinstance(td, dict) or subkey not in td:
                        # dopuštamo scenarije bez tog subkeya, ali tada nema doprinosa
                        continue
                    arr = np.array(td[subkey], dtype=float)
                    if arr.shape[0] != self.required_length:
                        return None
                    arrays.append(arr * probs[s])
                    found_any = True
                return sum(arrays) if found_any else None
            except Exception:
                return None
    
        def _scen_avg_electricity():
            out = _scen_avg_simple("Electricity Demand")
            if out is not None:
                return out

    
        # Pyomo varijable -> očekivanja
        def get_series(var):
            if not hasattr(model, var):
                return None
            var_obj = getattr(model, var)
            try:
                return np.array([
                    sum(pye.value(var_obj[t, s]) * probs[s] for s in S_range)
                    for t in T_range
                ])
            except:
                return None
    
        def arr(name):
            a = results.get(name)
            return a if isinstance(a, np.ndarray) else np.zeros(self.required_length)
    
        # Ulazne serije (scenarijski prosjek)
        pv_gen = _scen_avg_simple("PV Generation")
        wind_gen = _scen_avg_simple("Wind Generation")
        sc_gen = _scen_avg_simple("Solar Collector Generation")
    
        if pv_gen is None and np.any(self.pv_generation): pv_gen = self.pv_generation
        if wind_gen is None and np.any(self.wind_generation): wind_gen = self.wind_generation
        if sc_gen is None and np.any(self.solar_collector_generation): sc_gen = self.solar_collector_generation
    
        if pv_gen is not None and np.any(pv_gen): results["PV Generation"] = pv_gen
        if wind_gen is not None and np.any(wind_gen): results["Wind Generation"] = wind_gen
        if sc_gen is not None and np.any(sc_gen): results["Solar Collector Generation"] = sc_gen
    
        elec_dem = _scen_avg_electricity()
        heat_dem = _scen_avg_thermal("heating")
        cool_dem = _scen_avg_thermal("cooling")

        if elec_dem is None and np.any(self.electricity_demand): elec_dem = self.electricity_demand
        if heat_dem is None and np.any(self.heating_demand): heat_dem = self.heating_demand
        if cool_dem is None and np.any(self.cooling_demand): cool_dem = self.cooling_demand

        if elec_dem is not None and np.any(elec_dem): results["Electricity Demand"] = elec_dem
        if heat_dem is not None and np.any(heat_dem): results["Heating Demand"] = heat_dem
        if cool_dem is not None and np.any(cool_dem): results["Cooling Demand"] = cool_dem

        # Cijene: Buy kao E[Price Data]; Sell preferira E[Sell Price], inače buyback * E[Buy]; Thermal E[Thermal Price]
        results["Buy Price"] = np.array([
            sum(scenarios[s]["Price Data"][t] * probs[s] for s in S_range)
            for t in range(self.required_length)
        ])
    
        sell_avg = _scen_avg_simple("Sell Price")
        if sell_avg is not None:
            results["Sell Price"] = sell_avg
        elif self.buyback_factor is not None:
            results["Sell Price"] = results["Buy Price"] * self.buyback_factor
        else:
            results["Sell Price"] = self.sell_price
    
        thermal_avg = _scen_avg_simple("Thermal Price")
        results["Thermal Price"] = thermal_avg if thermal_avg is not None else self.thermal_price
    
        # Transferi (očekivanja varijabli)
        results["PV → Load"] = get_series("pv_to_load")
        results["PV → Grid"] = get_series("pv_to_grid")
        results["PV → Battery"] = get_series("pv_to_batt")
        results["PV → Heat Pump (heating)"] = get_series("pv_to_hp_heat")
        results["PV → Heat Pump (cooling)"] = get_series("pv_to_hp_cool")
    
        results["Wind → Load"] = get_series("wind_to_load")
        results["Wind → Grid"] = get_series("wind_to_grid")
        results["Wind → Battery"] = get_series("wind_to_batt")
        results["Wind → Heat Pump (heating)"] = get_series("wind_to_hp_heat")
        results["Wind → Heat Pump (cooling)"] = get_series("wind_to_hp_cool")
    
        results["Grid → Load"] = get_series("grid_to_load")
        results["Grid → Battery"] = get_series("grid_to_batt")
        results["Grid → Heat Pump (heating)"] = get_series("grid_to_hp_heat")
        results["Grid → Heat Pump (cooling)"] = get_series("grid_to_hp_cool")
    
        results["Battery → Load"] = get_series("batt_to_load")
        results["Battery → Grid"] = get_series("batt_to_grid")
        results["Battery → Heat Pump (heating)"] = get_series("batt_to_hp_heat")
        results["Battery → Heat Pump (cooling)"] = get_series("batt_to_hp_cool")
        results["Battery charge"] = get_series("charge")
        results["Battery discharge"] = get_series("discharge")
        results["Battery SOE"] = get_series("batt_soe")
    
        if self.buffer_capacity:
            results["Heat Pump → Heating Load + Buffer Tank"] = get_series("hp_heat_to_load")
        else:
            results["Heat Pump → Heating Load"] = get_series("hp_heat_to_load")
        results["Heat Pump → Cooling Load"] = get_series("hp_cool_to_load")
        results["Heat Pump → Buffer Tank"] = get_series("hp_to_buffer")
    
        results["Buffer Tank → Heating Load"] = get_series("buffer_to_load")
        results["Buffer Tank SOE"] = get_series("buffer_soe")
    
        results["Solar Collector → Buffer Tank"] = get_series("solar_to_buffer")
        results["Unmet Solar Collector → Buffer Tank"] = get_series("solar_curtail")
    
        results["Unmet Electricity Demand"] = get_series("unmet_electricity_demand")
        results["Unmet Heating Demand"] = get_series("unmet_heating_demand")
        results["Unmet Cooling Demand"] = get_series("unmet_cooling_demand")
        results["PV Lost"] = get_series("pv_lost")
        results["Wind Lost"] = get_series("wind_lost")
    
        # Financije
        results["Revenue"] = (
            arr("PV → Grid") +
            arr("Wind → Grid") +
            arr("Battery → Grid")
        ) * results["Sell Price"]
    
        results["Cost"] = (
            arr("Grid → Load") +
            arr("Grid → Battery") +
            arr("Grid → Heat Pump (heating)") +
            arr("Grid → Heat Pump (cooling)")
        ) * results["Buy Price"]
    
        results["Savings"] = (
            (
                arr("PV → Load") +
                arr("PV → Heat Pump (heating)") +
                arr("PV → Heat Pump (cooling)") +
                arr("Battery → Load") +
                arr("Battery → Heat Pump (heating)") +
                arr("Battery → Heat Pump (cooling)") +
                arr("Wind → Load") +
                arr("Wind → Heat Pump (heating)") +
                arr("Wind → Heat Pump (cooling)")
            ) * results["Buy Price"]
            + arr("Solar Collector → Buffer Tank") * results["Thermal Price"]
        )
    
        results["Net profit"] = results["Revenue"] - results["Cost"]
    
        # makni prazne nizove
        results = {k: v for k, v in results.items() if not isinstance(v, np.ndarray) or np.any(v)}
        return results


class OptimizationRunner(QThread):
    finished = pyqtSignal(dict, dict, dict)
    failed = pyqtSignal(str)
    progress = pyqtSignal(int, str)

    def __init__(self, preparator, metadata, selected_inputs):
        super().__init__()
        self.preparator = preparator
        self.input_metadata = metadata
        self.selected_inputs = selected_inputs
        self._stop_requested = False

    def request_stop(self):
        self._stop_requested = True

    def _setup_solver(self):
        cbc_path = get_cbc_executable_path()
        solver = pye.SolverFactory('cbc', executable=cbc_path)
        # scaling=3: full geometric scaling improves numerical stability for large LPs.
        # primalSimplex: forces primal simplex which maintains primal feasibility at every
        #   iteration -- if the solver is aborted (seconds or maxIt), the returned solution
        #   is always primal feasible (constraints satisfied), preventing energy-balance errors.
        # maxIt caps LP simplex iterations so the solver never runs indefinitely.
        solver.options.update({"seconds": 1800, "ratio": 0.01,
                               "scaling": 3, "maxIt": 10000000,
                               "primalSimplex": ""})
        return solver
    
    def run(self):
        try:
            if self._stop_requested:
                self.failed.emit("Optimization cancelled by user.")
                return

            self.progress.emit(5, "Building model variables…")
            model = pye.ConcreteModel()
            model = self.preparator.create_model_variables(model, self.preparator)

            self.progress.emit(20, "Adding constraints & objective function…")
            model = self.preparator.add_constraints_and_objective(model)

            scenarios, _ = self.preparator.get_scenarios()
            n_sc = len(scenarios)
            self.progress.emit(28, f"Solving LP ({n_sc} scenario{'s' if n_sc != 1 else ''})…")
            result = self._setup_solver().solve(model, tee=False)

            if self._stop_requested:
                self.failed.emit("Optimization cancelled by user.")
                return

            ok_statuses = {pye.SolverStatus.ok, pye.SolverStatus.aborted}
            if result.solver.status not in ok_statuses:
                self.failed.emit("Optimization failed or was infeasible.")
                return

            self.progress.emit(82, "Extracting results…")
            results = self.preparator.extract_results(model)

            # Guard: detect zero-solution (solver aborted without feasible solution)
            energy_keys = ["PV → Load", "Wind → Load", "Grid → Load", "Battery → Load"]
            has_energy = any(
                isinstance(results.get(k), np.ndarray) and np.any(results[k])
                for k in energy_keys
            )
            if not has_energy:
                self.failed.emit(
                    "Stochastic optimization returned a zero-valued solution.\n\n"
                    "The solver could not produce a valid dispatch within the time limit.\n"
                    "Please try running the stochastic optimization again."
                )
                return

            # Per-scenario stats: read profits directly from LP per-scenario variables
            self.progress.emit(92, "Computing per-scenario statistics…")
            try:
                stoch_stats = self.preparator._compute_stoch_stats(model)
                results.update(stoch_stats)

                self.progress.emit(97, "Computing Value of Stochastic Solution (VSS)…")
                vss_stats = self._compute_vss(stoch_stats)
                results.update(vss_stats)
            except Exception as e:
                results["_stoch_stats_warning"] = str(e)

            self.progress.emit(100, "Complete!")
            self.finished.emit(results, self.input_metadata, self.selected_inputs)

        except Exception as e:
            tb = traceback.format_exc()
            self.failed.emit(f"{str(e)}\n\nTraceback:\n{tb}")

    def _compute_vss(self, stoch_stats):
        """Compute True VSS = SS - EEV.

        EV policy: deterministic LP solved on the probability-weighted mean scenario.
        EEV: forward-simulate that battery/HP policy on each stochastic scenario.
        """
        try:
            import OptimizationDeterministic as OptDet

            scenarios, probs = self.preparator.get_scenarios()
            n_sc = len(scenarios)
            if n_sc <= 1:
                return {}

            # --- Build mean scenario inputs ---
            mean_inputs = {k: v for k, v in self.selected_inputs.items()
                           if k not in ("stochastic", "stochastic_probabilities")}

            for key in ("PV Generation", "Wind Generation", "Electricity Demand",
                        "Solar Collector Generation", "Price Data"):
                arrays = [np.array(sc[key], dtype=float)
                          for sc in scenarios if key in sc]
                if arrays:
                    mean_inputs[key] = sum(probs[s] * np.array(sc[key], dtype=float)
                                           for s, sc in enumerate(scenarios) if key in sc)

            if any("Thermal Demand" in sc for sc in scenarios):
                mean_heat = sum(probs[s] * np.array(sc["Thermal Demand"]["heating"], dtype=float)
                                for s, sc in enumerate(scenarios) if "Thermal Demand" in sc)
                mean_cool = sum(probs[s] * np.array(sc["Thermal Demand"]["cooling"], dtype=float)
                                for s, sc in enumerate(scenarios) if "Thermal Demand" in sc)
                mean_inputs["Thermal Demand"] = {"heating": mean_heat, "cooling": mean_cool}

            # --- Solve mean-scenario deterministic LP (EV solution) ---
            ev_prep = OptDet.OptimizationInputPreparator(mean_inputs)
            ev_model = pye.ConcreteModel()
            ev_model = ev_prep.create_model_variables(ev_model, ev_prep)
            ev_model = ev_prep.add_constraints_and_objective(ev_model)
            ev_result = self._setup_solver().solve(ev_model, tee=False)

            if ev_result.solver.status != pye.SolverStatus.ok:
                return {}

            ev_profit_on_mean = self._eval_det_profit(ev_model, ev_prep)

            # --- Forward-simulate EV policy on each stochastic scenario ---
            T_range = range(1, 8761)

            ev_charge = np.zeros(8760)
            ev_discharge = np.zeros(8760)
            if hasattr(ev_model, "charge"):
                ev_charge = np.array([pye.value(ev_model.charge[t]) or 0.0 for t in T_range])
                ev_discharge = np.array([pye.value(ev_model.discharge[t]) or 0.0 for t in T_range])

            ev_hp_heat_elec = np.zeros(8760)
            ev_hp_cool_elec = np.zeros(8760)
            if hasattr(ev_model, "electricity_to_hp_heat"):
                ev_hp_heat_elec = np.array([pye.value(ev_model.electricity_to_hp_heat[t]) or 0.0 for t in T_range])
            if hasattr(ev_model, "electricity_to_hp_cool"):
                ev_hp_cool_elec = np.array([pye.value(ev_model.electricity_to_hp_cool[t]) or 0.0 for t in T_range])

            bat_cap = self.preparator.battery_capacity or 0.0
            bat_eff = self.preparator.battery_efficiency or 1.0

            eev_profits = []
            for s_idx, sc in enumerate(scenarios):
                buy_p = np.array(sc.get("Price Data", np.zeros(8760)), dtype=float)
                if "Sell Price" in sc:
                    sell_p = np.array(sc["Sell Price"], dtype=float)
                elif self.preparator.buyback_factor is not None:
                    sell_p = buy_p * self.preparator.buyback_factor
                else:
                    sell_p = np.zeros(8760)

                pv_arr   = np.array(sc.get("PV Generation",   np.zeros(8760)), dtype=float)
                wind_arr = np.array(sc.get("Wind Generation", np.zeros(8760)), dtype=float)
                elec_dem = np.array(sc.get("Electricity Demand", np.zeros(8760)), dtype=float)
                hp_elec  = ev_hp_heat_elec + ev_hp_cool_elec
                total_dem = elec_dem + hp_elec

                bat_soe = 0.0
                profit = 0.0
                for t in range(8760):
                    # Clip EV battery schedule to current feasibility
                    max_chg_soc = (bat_cap - bat_soe) / bat_eff if bat_eff > 0 else 0.0
                    actual_charge = max(0.0, min(ev_charge[t], max_chg_soc))
                    actual_discharge = max(0.0, min(ev_discharge[t], bat_soe))
                    bat_soe += actual_charge * bat_eff - actual_discharge
                    bat_soe = max(0.0, min(bat_cap, bat_soe))

                    net = pv_arr[t] + wind_arr[t] + actual_discharge - actual_charge
                    demand_t = total_dem[t]
                    if net >= demand_t:
                        profit += demand_t * buy_p[t] + (net - demand_t) * sell_p[t]
                    else:
                        self_cons = max(0.0, net)
                        profit += self_cons * buy_p[t] - (demand_t - self_cons) * buy_p[t]

                eev_profits.append(profit)

            eev = sum(probs[s] * eev_profits[s] for s in range(n_sc))
            ss  = stoch_stats["stoch_profit_expected"]
            true_vss = ss - eev

            return {
                "stoch_ev_profit_mean": ev_profit_on_mean,
                "stoch_eev":            eev,
                "stoch_true_vss":       true_vss,
            }

        except Exception:
            return {}

    def _eval_det_profit(self, ev_model, ev_prep):
        """Compute annual profit from a solved deterministic model."""
        T_range = range(1, 8761)

        def get_arr(var_name):
            if not hasattr(ev_model, var_name):
                return np.zeros(8760)
            var_obj = getattr(ev_model, var_name)
            try:
                return np.array([pye.value(var_obj[t]) or 0.0 for t in T_range])
            except Exception:
                return np.zeros(8760)

        sell_p = ev_prep.sell_price
        buy_p  = ev_prep.buy_price
        thermal_p = ev_prep.thermal_price

        exports = get_arr("pv_to_grid") + get_arr("wind_to_grid") + get_arr("batt_to_grid")
        self_cons = (get_arr("pv_to_load") + get_arr("pv_to_hp_heat") + get_arr("pv_to_hp_cool") +
                     get_arr("wind_to_load") + get_arr("wind_to_hp_heat") + get_arr("wind_to_hp_cool") +
                     get_arr("batt_to_load") + get_arr("batt_to_hp_heat") + get_arr("batt_to_hp_cool"))
        imports = (get_arr("grid_to_load") + get_arr("grid_to_batt") +
                   get_arr("grid_to_hp_heat") + get_arr("grid_to_hp_cool"))

        return float(np.sum(exports * sell_p) +
                     np.sum(self_cons * buy_p) +
                     np.sum(get_arr("solar_to_buffer") * thermal_p) -
                     np.sum(imports * buy_p))

class OptimizationPopup(QDialog):
    # Solve stage boundaries (progress %)
    _SOLVE_START = 28
    _SOLVE_END   = 82

    _BTN_STYLE = """
        QPushButton {
            background-color: white;
            color: black;
            font-weight: bold;
            font-size: 12px;
            border: 2px solid black;
            padding: 4px 14px;
        }
        QPushButton:hover  { background-color: #f0f0f0; }
        QPushButton:disabled { color: #aaa; border-color: #aaa; }
    """

    def __init__(self, parent, preparator):
        super().__init__(parent)
        self.setWindowTitle("Optimization in Progress")
        self.setModal(True)
        self.setFixedSize(460, 190)
        self.setStyleSheet("background-color: white;")

        self._current_pct   = 0
        self._solving       = False
        self._solve_elapsed = 0.0   # seconds spent in the solve stage
        self._elapsed_secs  = 0

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 18)
        root.setSpacing(0)

        # ── title bar strip ──────────────────────────────────────────────────
        title_bar = QWidget()
        title_bar.setFixedHeight(28)
        title_bar.setStyleSheet("background-color: #1b3a2d; border-radius: 3px;")
        tb_layout = QHBoxLayout(title_bar)
        tb_layout.setContentsMargins(10, 0, 10, 0)
        title_lbl = QLabel("STOCHASTIC OPTIMIZATION")
        title_lbl.setStyleSheet(
            "color: white; font-size: 9px; font-weight: bold;"
            " letter-spacing: 1.5px; background: transparent;"
        )
        tb_layout.addWidget(title_lbl)
        root.addWidget(title_bar)
        root.addSpacing(14)

        # ── stage label ──────────────────────────────────────────────────────
        self.stage_label = QLabel("Initialising…")
        self.stage_label.setStyleSheet(
            "color: #1a1a2e; font-size: 12px; font-weight: bold;"
        )
        root.addWidget(self.stage_label)
        root.addSpacing(8)

        # ── progress bar ─────────────────────────────────────────────────────
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(22)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                border: 1px solid #c8c8c8;
                border-radius: 4px;
                background-color: #f0f0f0;
                text-align: center;
                font-size: 11px;
                color: #333;
            }
            QProgressBar::chunk {
                background-color: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #2e7d32, stop:1 #43a047
                );
                border-radius: 3px;
            }
        """)
        root.addWidget(self.progress_bar)
        root.addSpacing(10)

        # ── bottom row: elapsed | estimated | stop ───────────────────────────
        bottom = QHBoxLayout()
        bottom.setSpacing(0)

        self.elapsed_label = QLabel("Elapsed:  0:00")
        self.elapsed_label.setStyleSheet("color: #555; font-size: 11px;")
        bottom.addWidget(self.elapsed_label)

        self.eta_label = QLabel("")
        self.eta_label.setStyleSheet("color: #777; font-size: 11px; margin-left: 14px;")
        bottom.addWidget(self.eta_label)

        bottom.addStretch()

        self.stop_button = QPushButton("Stop")
        self.stop_button.setStyleSheet(self._BTN_STYLE)
        self.stop_button.setFixedWidth(72)
        self.stop_button.clicked.connect(self.stop_optimization)
        bottom.addWidget(self.stop_button)

        root.addLayout(bottom)

        # ── timers ───────────────────────────────────────────────────────────
        # 1-second wall-clock for elapsed display
        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.timeout.connect(self._tick_elapsed)
        self._elapsed_timer.start(1000)

        # 200 ms smooth-fill during the LP solve stage
        self._solve_timer = QTimer(self)
        self._solve_timer.timeout.connect(self._tick_solve)

        # ── optimization thread ───────────────────────────────────────────────
        self.runner_thread = OptimizationRunner(
            preparator, parent.input_metadata, parent.selected_inputs
        )
        self.runner_thread.progress.connect(self._on_progress)
        self.runner_thread.finished.connect(self.on_finished)
        self.runner_thread.failed.connect(self.on_failed)
        self.runner_thread.start()

    # ── timer callbacks ───────────────────────────────────────────────────────

    def _tick_elapsed(self):
        self._elapsed_secs += 1
        m, s = divmod(self._elapsed_secs, 60)
        self.elapsed_label.setText(f"Elapsed:  {m}:{s:02d}")

    def _tick_solve(self):
        """Smoothly advance the bar during the black-box LP solve."""
        self._solve_elapsed += 0.2
        # Asymptotic curve: reaches ~63 % of range after 60 s, ~86 % after 120 s
        span = self._SOLVE_END - self._SOLVE_START - 2
        frac = 1.0 - 2.71828 ** (-self._solve_elapsed / 80.0)
        target = int(self._SOLVE_START + frac * span)
        if target > self._current_pct:
            self._current_pct = target
            self.progress_bar.setValue(target)
            # Show ETA once we have enough data (≥ 10 s into solving)
            if self._solve_elapsed >= 10:
                pct_done = (target - self._SOLVE_START) / max(span, 1)
                if pct_done > 0.01:
                    total_est = self._solve_elapsed / pct_done
                    remaining = max(0, total_est - self._solve_elapsed)
                    rm, rs = divmod(int(remaining), 60)
                    self.eta_label.setText(f"·  Est. remaining:  {rm}:{rs:02d}")

    # ── progress signal handler ───────────────────────────────────────────────

    def _on_progress(self, pct, msg):
        self._current_pct = pct
        self.progress_bar.setValue(pct)
        self.stage_label.setText(msg)

        if pct == self._SOLVE_START:
            # Entering LP solve — start smooth fill
            self._solving = True
            self._solve_elapsed = 0.0
            self._solve_timer.start(200)

        elif self._solving and pct > self._SOLVE_START:
            # Leaving LP solve — snap bar and stop smooth fill
            self._solve_timer.stop()
            self._solving = False
            self.eta_label.setText("")

    # ── button ────────────────────────────────────────────────────────────────

    def stop_optimization(self):
        self.runner_thread.request_stop()
        self.stage_label.setText("Stopping — waiting for solver to finish…")
        self.stop_button.setDisabled(True)

    # ── completion handlers ───────────────────────────────────────────────────

    def on_finished(self, results_dict, metadata, selected_inputs):
        self._elapsed_timer.stop()
        self._solve_timer.stop()
        self.accept()
        QMessageBox.information(self, "Optimization Completed", "Optimization finished successfully.")

        index = self.parent().output_workspace.tabs.count() + 1

        self.parent().output_workspace.add_optimization_results(
            f"Optimization {index}", results_dict, selected_inputs
        )

        self.parent().financial_workspace.add_financial_summary(
            f"Optimization {index} ", results_dict, metadata, selected_inputs
        )
        financial_summary = self.parent().financial_workspace.financial_data[-1]

        self.parent().emissions_workspace.add_emissions_summary(
            f"Optimization {index} ", results_dict, metadata, selected_inputs
        )
        emissions_summary = self.parent().emissions_workspace.emission_data[-1]

        self.parent().text_analysis_workspace.add_analysis(
            f"Optimization {index} ", selected_inputs, results_dict, financial_summary, emissions_summary
        )

    def on_failed(self, message):
        self._elapsed_timer.stop()
        self._solve_timer.stop()
        self.reject()
        QMessageBox.critical(self, "Optimization Failed", message)