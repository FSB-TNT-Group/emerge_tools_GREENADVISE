import numpy as np

from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QProgressBar, QPushButton, QMessageBox, QHBoxLayout, QSizePolicy, QSpacerItem
from PyQt5.QtCore import Qt
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
        if  "Thermal Demand" in self.inputs:
            fuel_price_raw = thermal_emission.get("fuel_price", 0)
            try:
                thermal_price = float(fuel_price_raw)
            except (ValueError, TypeError):
                thermal_price = 0.0
            self.thermal_price = np.ones(self.required_length) * thermal_price
        else:
            self.thermal_price = np.zeros(self.required_length)

        if buyback_str:
            try:
                self.sell_price = self.buy_price * float(buyback_str)
            except ValueError:
                raise ValueError(f"Invalid buyback factor: {buyback_str} or Invalid thermal_price: {thermal_price}")

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
        T = range(1, 8761)
        model = pye.ConcreteModel()
        model.T = pye.Set(initialize = T, ordered=True)

        # PV
        if preparator.pv_generation.any():
            model.pv_to_load = pye.Var(model.T, domain=pye.NonNegativeReals)
            model.pv_to_grid = pye.Var(model.T, domain=pye.NonNegativeReals)
            if preparator.battery_capacity:
                model.pv_to_batt = pye.Var(model.T, domain=pye.NonNegativeReals)
            if preparator.heat_pump_heating_capacity:
                model.pv_to_hp_heat = pye.Var(model.T, domain=pye.NonNegativeReals)
                model.pv_to_hp_cool = pye.Var(model.T, domain=pye.NonNegativeReals)
            if preparator.electricity_demand.any():
                model.pv_lost = pye.Var(model.T, domain=pye.NonNegativeReals)

        # Wind
        if preparator.wind_generation.any():
            model.wind_to_load = pye.Var(model.T, domain=pye.NonNegativeReals)
            model.wind_to_grid = pye.Var(model.T, domain=pye.NonNegativeReals)
            if preparator.battery_capacity:
                model.wind_to_batt = pye.Var(model.T, domain=pye.NonNegativeReals)
            if preparator.heat_pump_heating_capacity:
                model.wind_to_hp_heat = pye.Var(model.T, domain=pye.NonNegativeReals)
                model.wind_to_hp_cool = pye.Var(model.T, domain=pye.NonNegativeReals)
            if preparator.electricity_demand.any():
                model.wind_lost = pye.Var(model.T, domain=pye.NonNegativeReals)

        # Battery
        if preparator.battery_capacity:
            if preparator.heat_pump_heating_capacity or preparator.heat_pump_cooling_capacity:
                model.batt_to_hp_heat = pye.Var(model.T, domain=pye.NonNegativeReals)
                model.batt_to_hp_cool = pye.Var(model.T, domain=pye.NonNegativeReals)

            model.grid_to_batt = pye.Var(model.T, domain=pye.NonNegativeReals)
            model.batt_to_load = pye.Var(model.T, domain=pye.NonNegativeReals)
            model.batt_to_grid = pye.Var(model.T, domain=pye.NonNegativeReals)

            model.charge = pye.Var(model.T, domain=pye.NonNegativeReals)
            model.discharge = pye.Var(model.T, domain=pye.NonNegativeReals)
            model.batt_soe = pye.Var(range(0, 8761), domain=pye.NonNegativeReals, bounds=(0, preparator.battery_capacity))
            model.x = pye.Var(model.T, bounds=(0, 1))
            model.batt_soe[0].fix(0)

        # Grid
        if preparator.electricity_demand.any():
            model.grid_to_load = pye.Var(model.T, domain=pye.NonNegativeReals)
            model.unmet_electricity_demand = pye.Var(model.T, domain=pye.NonNegativeReals)

        # Thermal
        if preparator.heating_demand.any() and preparator.cooling_demand.any():
            model.unmet_heating_demand = pye.Var(model.T, domain=pye.NonNegativeReals)
            model.unmet_cooling_demand = pye.Var(model.T, domain=pye.NonNegativeReals)
        elif preparator.heating_demand.any():
            model.unmet_heating_demand = pye.Var(model.T, domain=pye.NonNegativeReals)
        else:
            model.unmet_cooling_demand = pye.Var(model.T, domain=pye.NonNegativeReals)

        # Heat pump
        if preparator.heat_pump_heating_capacity or preparator.heat_pump_cooling_capacity:
            model.electricity_to_hp_heat = pye.Var(model.T, domain=pye.NonNegativeReals)
            model.electricity_to_hp_cool = pye.Var(model.T, domain=pye.NonNegativeReals)
            model.grid_to_hp_heat = pye.Var(model.T, domain=pye.NonNegativeReals)
            model.grid_to_hp_cool = pye.Var(model.T, domain=pye.NonNegativeReals)
            model.hp_heat_to_load = pye.Var(model.T, domain=pye.NonNegativeReals, bounds=(0, preparator.heat_pump_heating_capacity))
            model.hp_cool_to_load = pye.Var(model.T, domain=pye.NonNegativeReals, bounds=(0, preparator.heat_pump_cooling_capacity))
            if preparator.buffer_capacity:
                model.hp_to_buffer = pye.Var(model.T, domain=pye.NonNegativeReals)

        # Solar collector
        if preparator.solar_collector_generation.any():
            model.solar_to_buffer = pye.Var(model.T, domain=pye.NonNegativeReals)
            model.solar_curtail =  pye.Var(model.T, domain=pye.NonNegativeReals)

        # Buffer tank
        if preparator.buffer_capacity:
            model.buffer_to_load = pye.Var(model.T, domain=pye.NonNegativeReals)
            model.buffer_charge = pye.Var(model.T, domain=pye.NonNegativeReals)
            model.buffer_discharge = pye.Var(model.T, domain=pye.NonNegativeReals)
            model.buffer_soe = pye.Var(range(0, 8761), domain=pye.NonNegativeReals, bounds=(0, preparator.buffer_capacity))
            model.buffer_soe[0].fix(0)

            model.buffer_x = pye.Var(model.T, bounds=(0, 1))
        return model

    def add_constraints_and_objective(self, model):
        import pyomo.environ as pye
        T = model.T

        if (hasattr(model, "grid_to_load") 
            or hasattr(model, "grid_to_batt")
            or hasattr(model, "grid_to_hp_heat")
            or hasattr(model, "grid_to_hp_cool")
            or hasattr(model, "pv_to_grid") 
            or hasattr(model, "wind_to_grid") 
            or hasattr(model, "batt_to_grid")):

            def grid_power_limit(m, t):
                limit = 0
                if hasattr(m, "grid_to_load"):
                    limit += m.grid_to_load[t]
                if hasattr(m, "grid_to_batt"):
                    limit += m.grid_to_batt[t]
                if hasattr(m, "grid_to_hp_heat"):
                    limit += m.grid_to_hp_heat[t]
                if hasattr(m, "grid_to_hp_cool"):
                    limit += m.grid_to_hp_cool[t]
                if hasattr(m, "pv_to_grid"):
                    limit += m.pv_to_grid[t]
                if hasattr(m, "wind_to_grid"):
                    limit += m.wind_to_grid[t]
                if hasattr(m, "batt_to_grid"):
                    limit += m.batt_to_grid[t]
                return limit <= self.grid_limit
            model.grid_power_limit = pye.Constraint(T, rule=grid_power_limit)

        # Electricity balance
        if (hasattr(model, "pv_to_load") 
            or hasattr(model, "batt_to_load") 
            or hasattr(model, "grid_to_load") 
            or hasattr(model, "wind_to_load")):

            def power_balance(m, t):
                supply = 0
                if hasattr(m, "pv_to_load"):
                    supply += m.pv_to_load[t]
                if hasattr(m, "batt_to_load"):
                    supply += m.batt_to_load[t]
                if hasattr(m, "grid_to_load"):
                    supply += m.grid_to_load[t]
                if hasattr(m, "wind_to_load"):
                    supply += m.wind_to_load[t]
                if hasattr(m, "unmet_electricity_demand"):
                    supply += m.unmet_electricity_demand[t]
                return supply == self.electricity_demand[t-1]
            model.power_balance = pye.Constraint(T, rule=power_balance)

        # PV allocation
        if hasattr(model, "pv_to_load"):
            def pv_allocation(m, t):
                total = m.pv_to_load[t]
                if hasattr(m, "pv_to_batt"): total += m.pv_to_batt[t]
                if hasattr(m, "pv_to_grid"): total += m.pv_to_grid[t]
                if hasattr(m, "pv_to_hp_heat"): total += m.pv_to_hp_heat[t]
                if hasattr(m, "pv_to_hp_cool"): total += m.pv_to_hp_cool[t]
                if hasattr(m, "pv_lost"): total += m.pv_lost[t]
                return total == self.pv_generation[t-1]
            model.pv_allocation = pye.Constraint(T, rule=pv_allocation)

        # Wind allocation
        if hasattr(model, "wind_to_load"):
            def wind_allocation(m, t):
                total = m.wind_to_load[t]
                if hasattr(m, "wind_to_batt"): total += m.wind_to_batt[t]
                if hasattr(m, "wind_to_grid"): total += m.wind_to_grid[t]
                if hasattr(m, "wind_to_hp_heat"): total += m.wind_to_hp_heat[t]
                if hasattr(m, "wind_to_hp_cool"): total += m.wind_to_hp_cool[t]
                if hasattr(m, "wind_lost"): total += m.wind_lost[t]
                return total == self.wind_generation[t-1]
            model.wind_allocation = pye.Constraint(T, rule=wind_allocation)

        # Battery Charge/Discharge link
        if hasattr(model, "charge"):
            def battery_charge_link(m, t):
                total = 0
                if hasattr(m, "pv_to_batt"): total += m.pv_to_batt[t]
                if hasattr(m, "grid_to_batt"): total += m.grid_to_batt[t]
                if hasattr(m, "wind_to_batt"): total += m.wind_to_batt[t]
                return m.charge[t] == total
            model.charge_link = pye.Constraint(T, rule=battery_charge_link)

        if hasattr(model, "discharge"):
            def battery_discharge_link(m, t):
                total = 0
                if hasattr(m, "batt_to_load"): total += m.batt_to_load[t]
                if hasattr(m, "batt_to_grid"): total += m.batt_to_grid[t]
                if hasattr(m, "batt_to_hp_heat"): total += m.batt_to_hp_heat[t]
                if hasattr(m, "batt_to_hp_cool"): total += m.batt_to_hp_cool[t]
                return m.discharge[t] == total
            model.discharge_link = pye.Constraint(T, rule=battery_discharge_link)

        # Battery SoE balance
        if hasattr(model, "batt_soe"):
            def soe_balance(m, t):
                return m.batt_soe[t] == m.batt_soe[t - 1] + m.charge[t] * self.battery_efficiency - m.discharge[t] / self.battery_efficiency
            model.soe_balance = pye.Constraint(model.T, rule=soe_balance)

        if hasattr(model, "x"):
            model.charge_limit = pye.Constraint(T, rule=lambda m, t: m.charge[t] <= self.battery_rated_power * m.x[t])
            model.discharge_limit = pye.Constraint(T, rule=lambda m, t: m.discharge[t] <= self.battery_rated_power * (1 - m.x[t]))

        # Heat pump and buffer tank constraints
        if hasattr(model, "electricity_to_hp_heat"):
            def heat_output_rule(m, t):
                return m.hp_heat_to_load[t] == self.heat_pump_cop * m.electricity_to_hp_heat[t]
            model.heat_output_eq_heat = pye.Constraint(T, rule=heat_output_rule)

        if hasattr(model, "electricity_to_hp_cool"):
            def cool_output_rule(m, t):
                return m.hp_cool_to_load[t] == self.heat_pump_eer * m.electricity_to_hp_cool[t]
            model.heat_output_eq_cool= pye.Constraint(T, rule=cool_output_rule)

        if np.sum(self.heating_demand) > 0:
            def heat_balance_rule(m, t):
                hp_output_heat = m.hp_heat_to_load[t] if hasattr(m, "hp_heat_to_load") else 0
                buffer_discharge = m.buffer_to_load[t] if hasattr(m, "buffer_to_load") else 0
                buffer_charge = m.hp_to_buffer[t] if hasattr(m, "hp_to_buffer") else 0
                unmet_heating_demand = m.unmet_heating_demand[t] if hasattr(m, "unmet_heating_demand") else 0
                return hp_output_heat + buffer_discharge + unmet_heating_demand == self.heating_demand[t-1] + buffer_charge
            model.heat_balance = pye.Constraint(T, rule=heat_balance_rule)

        if np.sum(self.cooling_demand) > 0:
            def cool_balance_rule(m, t):
                hp_output_cool = m.hp_cool_to_load[t] if hasattr(m, "hp_cool_to_load") else 0
                unmet_cooling_demand = m.unmet_cooling_demand[t] if hasattr(m, "unmet_cooling_demand") else 0
                return hp_output_cool + unmet_cooling_demand == self.cooling_demand[t-1]
            model.cool_balance = pye.Constraint(T, rule=cool_balance_rule)

        if hasattr(model, "solar_to_buffer"):
            def solar_rule(m, t):
                return self.solar_collector_generation[t-1] == m.solar_to_buffer[t] + m.solar_curtail[t]
            model.solar_allocation = pye.Constraint(model.T, rule=solar_rule)

        # Buffer SoE balance
        if hasattr(model, "buffer_soe"):
            def heat_soe_dynamics_rule(m, t):
                hp_to_buf = m.hp_to_buffer[t] if hasattr(m, "hp_to_buffer") else 0
                solar_to_buf = m.solar_to_buffer[t] if hasattr(m, "solar_to_buffer") else 0
                return m.buffer_soe[t] == self.buffer_retention * m.buffer_soe[t - 1] + hp_to_buf + solar_to_buf - m.buffer_to_load[t]
            model.heat_soe_balance = pye.Constraint(model.T, rule=heat_soe_dynamics_rule)

        # Heat charge limit rule: total power into buffer ≤ rated charge rate.
        if hasattr(model, "hp_to_buffer") or hasattr(model, "solar_to_buffer"):
            def heat_charge_limit_rule(m, t):
                hp  = m.hp_to_buffer[t]    if hasattr(m, "hp_to_buffer")    else 0
                sol = m.solar_to_buffer[t] if hasattr(m, "solar_to_buffer") else 0
                return hp + sol <= self.buffer_rated_power
            model.heat_ch_limit = pye.Constraint(model.T, rule=heat_charge_limit_rule)

        # Heat discharge limit rule
        if hasattr(model, "buffer_to_load"):
            def heat_discharge_limit_rule(m, t):
                return m.buffer_to_load[t] <= self.buffer_rated_power
            model.heat_dch_limit = pye.Constraint(model.T, rule=heat_discharge_limit_rule)

        if hasattr(model, "electricity_to_hp_heat"):
            def elec_bound_rule_heat(m, t):
                return m.electricity_to_hp_heat[t] <= self.heat_pump_heating_capacity / self.heat_pump_cop
            model.elec_bound_heat = pye.Constraint(T, rule=elec_bound_rule_heat)

        if hasattr(model, "electricity_to_hp_cool"):
            def elec_bound_rule_cool(m, t):
                return m.electricity_to_hp_cool[t] <= self.heat_pump_cooling_capacity / self.heat_pump_eer
            model.elec_bound_cool = pye.Constraint(T, rule=elec_bound_rule_cool)

        # Heating heat pump allocation
        if (hasattr(model, "grid_to_hp_heat") 
            or hasattr(model, "pv_to_hp_heat") 
            or hasattr(model, "wind_to_hp_heat") 
            or hasattr(model, "batt_to_hp_heat")):

            def hp_heat_power_allocation_rule(m, t):
                total = 0
                if hasattr(m, "grid_to_hp_heat"): total += m.grid_to_hp_heat[t]
                if hasattr(m, "pv_to_hp_heat"): total += m.pv_to_hp_heat[t]
                if hasattr(m, "wind_to_hp_heat"): total += m.wind_to_hp_heat[t]
                if hasattr(m, "batt_to_hp_heat"): total += m.batt_to_hp_heat[t]
                return m.electricity_to_hp_heat[t] == total
            model.hp_heat_allocation = pye.Constraint(T, rule=hp_heat_power_allocation_rule)

        # Cooling heat pump allocation
        if (hasattr(model, "grid_to_hp_cool") 
            or hasattr(model, "pv_to_hp_cool") 
            or hasattr(model, "wind_to_hp_cool") 
            or hasattr(model, "batt_to_hp_cool")):

            def hp_cool_power_allocation_rule(m, t):
                total = 0
                if hasattr(m, "grid_to_hp_cool"): total += m.grid_to_hp_cool[t]
                if hasattr(m, "pv_to_hp_cool"): total += m.pv_to_hp_cool[t]
                if hasattr(m, "wind_to_hp_cool"): total += m.wind_to_hp_cool[t]
                if hasattr(m, "batt_to_hp_cool"): total += m.batt_to_hp_cool[t]
                return m.electricity_to_hp_cool[t] == total
            model.hp_cool_allocation = pye.Constraint(T, rule=hp_cool_power_allocation_rule)

        # Updated Objective
        def objective_rule(m):
            revenue = 0
            cost = 0
            for t in m.T:
                buy = self.buy_price[t-1]
                sell = self.sell_price[t-1]
                thermal_price = self.thermal_price[t-1]
                #SELLING
                if hasattr(m, "pv_to_grid"):
                    revenue += m.pv_to_grid[t] * sell
                if hasattr(m, "batt_to_grid"):
                    revenue += m.batt_to_grid[t] * sell
                if hasattr(m, "wind_to_grid"):
                    revenue += m.wind_to_grid[t] * sell

                #USAGE OF RENEWABLES
                if hasattr(m, "pv_to_load"):
                    revenue += m.pv_to_load[t] * buy
                if hasattr(m, "pv_to_hp_heat"):
                    revenue += m.pv_to_hp_heat[t] * buy
                if hasattr(m, "pv_to_hp_cool"):
                    revenue += m.pv_to_hp_cool[t] * buy
                # if hasattr(m, "pv_to_batt"):
                 #   revenue += m.pv_to_batt[t] * buy
                # if hasattr(m, "hp_to_buffer"):
                #     revenue += m.hp_to_buffer[t] * self.thermal_price
                if hasattr(m, "solar_to_buffer"):
                    revenue += m.solar_to_buffer[t] * thermal_price
                if hasattr(m, "batt_to_load"):
                    revenue += m.batt_to_load[t] * buy
                if hasattr(m, "batt_to_hp_heat"):
                    revenue += m.batt_to_hp_heat[t] * buy
                if hasattr(m, "batt_to_hp_cool"):
                    revenue += m.batt_to_hp_cool[t] * buy
                if hasattr(m, "wind_to_load"):
                    revenue += m.wind_to_load[t] * buy
                if hasattr(m, "wind_to_hp_heat"):
                    revenue += m.wind_to_hp_heat[t] * buy
                if hasattr(m, "wind_to_hp_cool"):
                    revenue += m.wind_to_hp_cool[t] * buy
                #if hasattr(m, "wind_to_batt"):
                    #revenue += m.wind_to_batt[t] * buy

                #COST
                if hasattr(m, "grid_to_load"):
                    cost += m.grid_to_load[t] * buy
                if hasattr(m, "grid_to_batt"):
                    cost += m.grid_to_batt[t] * buy
                if hasattr(m, "grid_to_hp_heat"):
                    cost += m.grid_to_hp_heat[t] * buy
                if hasattr(m, "grid_to_hp_cool"):
                    cost += m.grid_to_hp_cool[t] * buy

                #UNMET
                if hasattr(m, "unmet_electricity_demand"):
                    cost += self.unmet_penalty*m.unmet_electricity_demand[t]
                if hasattr(m, "unmet_heating_demand"):
                    cost += self.unmet_penalty*m.unmet_heating_demand[t]
                if hasattr(m, "unmet_cooling_demand"):
                    cost += self.unmet_penalty*m.unmet_cooling_demand[t]
                if hasattr(m, "pv_lost"):
                    cost += self.unmet_penalty*m.pv_lost[t]
                if hasattr(m, "wind_lost"):
                    cost += self.unmet_penalty*m.wind_lost[t]

            return revenue - cost
        model.obj = pye.Objective(rule=objective_rule, sense=pye.maximize)
        return model


    def extract_results(self, model):
        import pyomo.environ as pye
        results = {}

        T_range = range(1, 8761)

        def get_series(var):
            if hasattr(model, var):
                var_obj = getattr(model, var)
                try:
                    return np.array([pye.value(var_obj[t]) for t in T_range])
                except:
                    return None
            return None

        def get_scalar_sum(var):
            if hasattr(model, var):
                return sum(pye.value(getattr(model, var)[t]) for t in T_range)
            return 0

        def arr(name):
            arr = results.get(name)
            return arr if isinstance(arr, np.ndarray) else np.zeros(self.required_length)

        # Energy transfers

        if self.pv_generation is not None and np.sum(self.pv_generation) > 0:
            results["PV Generation"] = self.pv_generation

        results["PV → Load"] = get_series("pv_to_load")
        results["PV → Grid"] = get_series("pv_to_grid")
        results["PV → Battery"] = get_series("pv_to_batt")
        results["PV → Heat Pump (heating)"] = get_series("pv_to_hp_heat")
        results["PV → Heat Pump (cooling)"] = get_series("pv_to_hp_cool")


        if self.wind_generation is not None and np.sum(self.wind_generation) > 0:
            results["Wind Generation"] = self.wind_generation

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


        if self.solar_collector_generation is not None and np.sum(self.solar_collector_generation) > 0:
            results["Solar Collector Generation"] = self.solar_collector_generation

        results["Solar Collector → Buffer Tank"] = get_series("solar_to_buffer")
        results["Unmet Solar Collector → Buffer Tank"] = get_series("solar_curtail")


        results["Unmet Electricity Demand"] = get_series("unmet_electricity_demand")
        results["Unmet Heating Demand"] = get_series("unmet_heating_demand")
        results["Unmet Cooling Demand"] = get_series("unmet_cooling_demand")
        results["PV Lost"] = get_series("pv_lost")
        results["Wind Lost"] = get_series("wind_lost")

        # Include input data
        if self.electricity_demand is not None and np.sum(self.electricity_demand) > 0:
            results["Electricity Demand"] = self.electricity_demand

        if self.heating_demand is not None and np.sum(self.heating_demand) > 0:
            results["Heating Demand"] = self.heating_demand

        if self.cooling_demand is not None and np.sum(self.cooling_demand) > 0:
            results["Cooling Demand"] = self.cooling_demand

        if self.buy_price is not None and np.sum(self.buy_price) > 0:
            results["Buy Price"] = self.buy_price

        if self.sell_price is not None and np.sum(self.sell_price) > 0:
            results["Sell Price"] = self.sell_price

        # if self.thermal_price is not None and np.sum(self.thermal_price) > 0:
        results["Thermal Price"] = self.thermal_price


        # Revenue: exported electricity
        results["Revenue"] = (
            arr("PV → Grid") +
            arr("Wind → Grid") +
            arr("Battery → Grid")
        ) * results["Sell Price"]

        # Cost: imported electricity
        results["Cost"] = (
            arr("Grid → Load") +
            arr("Grid → Battery") +
            arr("Grid → Heat Pump (heating)") +
            arr("Grid → Heat Pump (cooling)")
        ) * results["Buy Price"]

        results["Savings"] = ((
            arr("PV → Load") +
            arr("PV → Heat Pump (heating)") +
            arr("PV → Heat Pump (cooling)") +
            arr("Battery → Load") +
            arr("Battery → Heat Pump (heating)") +
            arr("Battery → Heat Pump (cooling)") +
            arr("Wind → Load") +
            arr("Wind → Heat Pump (heating)") +
            arr("Wind → Heat Pump (cooling)")
            ) * results["Buy Price"] +
                                (
            arr("Solar Collector → Buffer Tank")
            ) * results["Thermal Price"])

        results["Net profit"] = results["Revenue"] - results["Cost"]

        #FILTER OUT VARIABLES WITH ALL ZEROS
        results = {
            k: v for k, v in results.items()
            if not isinstance(v, np.ndarray) or np.any(v)
        }

        return results

class OptimizationRunner(QThread):
    finished = pyqtSignal(dict, dict, dict)
    failed = pyqtSignal(str)

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
        solver.options.update({"seconds": 300, "ratio": 0.01})
        return solver

    def run(self):
        try:
            if self._stop_requested:
                self.failed.emit("Optimization cancelled by user.")
                return

            model = pye.ConcreteModel()
            model = self.preparator.create_model_variables(model, self.preparator)
            model = self.preparator.add_constraints_and_objective(model)

            result = self._setup_solver().solve(model, tee=False)

            if self._stop_requested:
                self.failed.emit("Optimization cancelled by user.")
                return

            if result.solver.status != pye.SolverStatus.ok:
                self.failed.emit("Optimization failed or was infeasible.")
                return

            results = self.preparator.extract_results(model)
            self.finished.emit(results, self.input_metadata, self.selected_inputs)

        except Exception as e:
            self.failed.emit(str(e))

class OptimizationPopup(QDialog):
    style = ("""
         QPushButton {
            background-color: white;
            color: black;
            font-weight: bold;
            font-size: 12px;
            border: 2px solid black;
            padding: 4px 12px;
        }
        QPushButton:hover {
            background-color: #f0f0f0;
        }
    """)
    def __init__(self, parent, preparator):
        super().__init__(parent)
        self.setWindowTitle("Optimization in Progress")
        self.setModal(True)
        self.setFixedSize(300, 100)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(10)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("Running optimization...")
        self.progress_bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.progress_bar.setMinimumHeight(25)
        self.progress_bar.setMinimumWidth(300)
        layout.addWidget(self.progress_bar, alignment=Qt.AlignCenter)

        layout.addStretch()

        button_row = QHBoxLayout()
        button_row.addStretch()

        self.stop_button = QPushButton("Stop")
        self.stop_button.setStyleSheet(self.style)
        self.stop_button.setFixedWidth(80)
        self.stop_button.clicked.connect(self.stop_optimization)
        button_row.addWidget(self.stop_button, alignment=Qt.AlignBottom)

        layout.addLayout(button_row)

        self.runner_thread = OptimizationRunner(preparator, parent.input_metadata, parent.selected_inputs)
        self.runner_thread.finished.connect(self.on_finished)
        self.runner_thread.failed.connect(self.on_failed)
        self.runner_thread.start()

    def stop_optimization(self):
        self.runner_thread.request_stop()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(1)
        self.progress_bar.setFormat("Stopping optimization...")
        self.stop_button.setDisabled(True)

    def on_finished(self, results_dict, metadata, selected_inputs):
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
        self.reject()
        QMessageBox.critical(self, "Optimization Failed", message)