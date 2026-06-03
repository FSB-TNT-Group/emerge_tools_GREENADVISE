import time
from PyQt5.QtWidgets import QMessageBox

from Technology_Simulator import TechnologySimulator
from Thermal_simulator import ThermalDemandSimulator
from Electricity_simulator import ElectricityDemandSimulator
from Price_simulator import PriceGenerator


class ScenarioGenerator:
    def __init__(self, selected_inputs, input_metadata, scraper, base_year=2022, steps=4):
        self.input_metadata = input_metadata or {}
        self.scraper = scraper

        self.simulator = TechnologySimulator()
        self.thermal_simulator = ThermalDemandSimulator()      
        self.electricity_simulator = ElectricityDemandSimulator()
        self.price_generator = PriceGenerator()

        self.years = [int(base_year) - i for i in range(int(steps))]

        self.outputs = {}

    def _append_out(self, key, value):
        self.outputs.setdefault(key, [])
        self.outputs[key].append(value)

    def stochastic_price(self, n_scenarios: int = 4):
        key = "Price Data Stochastic"
        res_list = []
        price_type = self.input_metadata.get("Price Type", "")
        price_inputs = self.input_metadata.get("Price Data Inputs", {}) or {}

        for i in range(int(n_scenarios)):
            try:
                if price_type == "country":
                    prices = self.price_generator.generate_price_country(price_inputs, noise=True)
                elif price_type == "dual":
                    prices = self.price_generator.generate_price_dual_tariff(price_inputs, noise=True)
                elif price_type == "single":
                    prices = self.price_generator.generate_price_single_tariff(price_inputs, noise=True)
                else:
                    prices = None

                self._append_out(key, prices)
                res_list.append(prices)
                print(f"💶 Stochastic price scenario {i+1}/{n_scenarios} generated.")
            except Exception as e:
                self._append_out(key, None)
                res_list.append(None)
                print(f"⚠️ Stochastic price generation failed (scenario {i+1}): {e}")

        return res_list

    def stochastic_electricity_demand(self, n_scenarios: int = 4):
        key = "Electricity Demand Stochastic"
        res_list = []

        demand_type = self.input_metadata.get("Electricity Demand Type", "simulate_base")
        raw_inputs = {
            k: float(v) if isinstance(v, str) and v.replace('.', '', 1).isdigit() else v
            for k, v in (self.input_metadata.get("Electricity Demand", {}) or {}).copy().items()
        }

        for i in range(int(n_scenarios)):
            try:
                if demand_type == "simulate":
                    demand = self.electricity_simulator.simulate_yearly(raw_inputs, use_base_curve=False, noise=True)
                elif demand_type == "simulate_base":
                    demand = self.electricity_simulator.simulate_yearly(raw_inputs, use_base_curve=True, noise=True)
                elif demand_type == "simulate_monthly":
                    demand = self.electricity_simulator.simulate_monthly(raw_inputs, use_base_curve=False, noise=True)
                elif demand_type == "simulate_monthly_base":
                    demand = self.electricity_simulator.simulate_monthly(raw_inputs, use_base_curve=True, noise=True)
                else:
                    demand = None

                self._append_out(key, demand)
                res_list.append(demand)
                print(f"⚡ Stochastic electricity scenario {i+1}/{n_scenarios} generated.")
            except Exception as e:
                self._append_out(key, None)
                res_list.append(None)
                print(f"⚠️ Stochastic electricity generation failed (scenario {i+1}): {e}")

        return res_list

    def stochastic_pv(self, n_scenarios: int = 4):
        key = "PV Generation Stochastic"
        res_list = []

        pv_meta = self.input_metadata.get("PV Generation", {}) or {}
        pv_type = self.input_metadata.get("PV Generation Type")

        for i in range(int(n_scenarios)):
            year = str(self.years[i % len(self.years)])
            try:
                inputs = pv_meta.copy()
                inputs["year"] = year
                if hasattr(self.scraper, "pv_inputs") and self.scraper.pv_inputs is not None:
                    self.scraper.pv_inputs.update(inputs)

                if pv_type == "simulate":
                    pv_radiance = self.scraper.fetch_radiance()
                    pv_output = self.simulator.pv_simulator(inputs, pv_radiance)
                else:
                    pv_output = self.scraper.fetch_pv()

                self._append_out(key, pv_output)
                res_list.append(pv_output)
                print(f"🔋 Stochastic PV scenario {i+1}/{n_scenarios} (year {year}) generated.")
            except Exception as e:
                self._append_out(key, None)
                res_list.append(None)
                print(f"⚠️ Stochastic PV generation failed (scenario {i+1}, year {year}): {e}")

            time.sleep(4)

        return res_list

    def stochastic_solar_collector(self, n_scenarios: int = 4):
        key = "Solar Collector Generation Stochastic"
        res_list = []

        meta = self.input_metadata.get("Solar Collector Inputs", {}) or {}

        for i in range(int(n_scenarios)):
            year = str(self.years[i % len(self.years)])
            try:
                inputs = meta.copy()
                inputs["year"] = year
                if hasattr(self.scraper, "pv_inputs") and self.scraper.pv_inputs is not None:
                    self.scraper.pv_inputs.update(inputs)

                pv_radiance = self.scraper.fetch_radiance()
                sc_output = self.simulator.solar_collector_simulator(inputs, pv_radiance)

                self._append_out(key, sc_output)
                res_list.append(sc_output)
                print(f"🌞 Stochastic solar collector scenario {i+1}/{n_scenarios} (year {year}) generated.")
            except Exception as e:
                self._append_out(key, None)
                res_list.append(None)
                print(f"⚠️ Stochastic solar collector generation failed (scenario {i+1}, year {year}): {e}")

            time.sleep(4)

        return res_list

    def stochastic_wind(self, n_scenarios: int = 4):
        key = "Wind Generation Stochastic"
        res_list = []

        wind_meta = self.input_metadata.get("Wind Generation", {}) or {}
        wind_type = self.input_metadata.get("Wind Generation Type")

        for i in range(int(n_scenarios)):
            year = str(self.years[i % len(self.years)])
            try:
                inputs = wind_meta.copy()
                inputs["year"] = year
                if hasattr(self.scraper, "wind_inputs") and self.scraper.wind_inputs is not None:
                    self.scraper.wind_inputs.update(inputs)

                if wind_type == "simulate":
                    wind_speed = self.scraper.fetch_speed()
                    wind_output = self.simulator.wind_simulator(inputs, wind_speed)
                else:
                    wind_output = self.scraper.fetch_wind()

                self._append_out(key, wind_output)
                res_list.append(wind_output)
                print(f"🌬️ Stochastic wind scenario {i+1}/{n_scenarios} (year {year}) generated.")
            except Exception as e:
                self._append_out(key, None)
                res_list.append(None)
                print(f"⚠️ Stochastic wind generation failed (scenario {i+1}, year {year}): {e}")

            time.sleep(4)

        return res_list

    def stochastic_thermal_demand(self, n_scenarios: int = 4):
        sim_type = self.input_metadata.get("Thermal Demand Type", "simulate_yearly")
        meta = self.input_metadata.get("Thermal Demand", {}) or {}
    
        res_heat, res_cool = [], []
    
        self.thermal_simulator.lat = getattr(self.scraper, "lat", None)
        self.thermal_simulator.lon = getattr(self.scraper, "lon", None)
    
        for i in range(int(n_scenarios)):
            year = str(self.years[i % len(self.years)])
            try:
                inputs = meta.copy()
                inputs["year"] = year
                inputs["dataset"] = "merra2"
                inputs["latitude"] = getattr(self.scraper, "lat", None)
                inputs["longitude"] = getattr(self.scraper, "lon", None)
    
                if sim_type == "simulate_monthly":
                    h, c = self.thermal_simulator.simulate_monthly(inputs)
                    print(f"🔥 Stochastic monthly thermal scenario {i+1}/{n_scenarios} (year {year}) generated.")
                else:
                    h, c = self.thermal_simulator.simulate_yearly(inputs)
                    print(f"🔥 Stochastic yearly thermal scenario {i+1}/{n_scenarios} (year {year}) generated.")
    
                res_heat.append(h)
                res_cool.append(c)
    
            except Exception as e:
                res_heat.append(None)
                res_cool.append(None)
                print(f"⚠️ Stochastic thermal demand failed (scenario {i+1}, year {year}): {e}")

            time.sleep(4)

        return {"heating": res_heat, "cooling": res_cool}

    def get_outputs(self):
        return self.outputs

