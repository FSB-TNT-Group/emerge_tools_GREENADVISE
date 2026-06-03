import numpy as np
from PyQt5.QtWidgets import QMessageBox
from Scrape_from_Ninja import NinjaScraper

class TechnologySimulator:
    def __init__(self, parent=None):
        self.parent = parent

    def _notify(self, title, message):
        if self.parent:
            QMessageBox.critical(self.parent, title, message)
            raise ValueError(title, message)
        else:
            print(f"{title}: {message}")

    def solar_collector_simulator(self, solar_collector_inputs, radiance_and_temp):
        try:
            area = float(solar_collector_inputs["area"])
            direct = radiance_and_temp["direct"]
            diffuse = radiance_and_temp["diffuse"]

            G_total_kW = direct + diffuse  # in kW/m²
            G_total_BTU = G_total_kW * 317.1  # in BTU/hr/ft²

            G_total_BTU = np.array(G_total_BTU, dtype=np.float64)
            G_total_BTU[G_total_BTU == 0] = float('inf')

            # Efficiency calculation
            ni_raw = (0.8 - 0.7 * (20 / G_total_BTU))
            ni_raw = np.nan_to_num(ni_raw)  # Replace NaNs with 0
            ni_clipped = np.clip(ni_raw, 0, 1)

            # Thermal output
            G_total_BTU[G_total_BTU == float('inf')] = 0
            Q_BTU_clipped = ni_clipped * G_total_BTU
            Q_kW_clipped = (Q_BTU_clipped * 3.1546 * area) / 1000

            return Q_kW_clipped

        except Exception as e:
            self._notify("Simulation Error", f"Solar collector simulation failed: {str(e)}")
            return None

    def pv_simulator(self, pv_simulate_inputs, radiance_and_temp):
        PR  = 0.9
        try:
            Pmax = float(pv_simulate_inputs["Pmax"])
            NOCT = float(pv_simulate_inputs["NOCT"])
            gama = float(pv_simulate_inputs["γ"])
            direct = radiance_and_temp["direct"]
            diffuse = radiance_and_temp["diffuse"]
            temp = radiance_and_temp["temperature"]

            P = Pmax * 1000

            G_total_kW = (direct + diffuse) * 1000
            T_cell = temp + ((NOCT-20)/800) * G_total_kW
            P_calac_adj = P *(G_total_kW / 1000) *(1 + (gama / 100) * (T_cell - 25)) * PR / 1000  # convert W to kW

            return P_calac_adj

        except Exception as e:
            self._notify("Simulation Error", f"PV simulation failed: {str(e)}")
            return None

    def wind_simulator(self, wind_simulate_inputs, wind_speed):

        air_density = 1.225
        efficiency = 0.4
        P_calc = np.zeros(8760)
        try:
            P_rated = float(wind_simulate_inputs['rated_power'])
            rotor_radius = float(wind_simulate_inputs['rotor_radius'])
            cut_in_ws = float(wind_simulate_inputs['cut_in_wind_speed'])
            rated_ws = float(wind_simulate_inputs['rated_wind_speed'])
            cut_off = float(wind_simulate_inputs['cut_off_wind_speed'])

            swept_area = np.pi * rotor_radius ** 2

            P_raw = (0.5 * air_density * swept_area * (wind_speed ** 3) * efficiency) / 1000

            P_calc = np.where(
            (wind_speed < cut_in_ws) | (wind_speed >= cut_off),
            0,
            np.where(
                wind_speed < rated_ws,
                np.minimum(P_raw, P_rated),
                P_rated
                )
            )

            return P_calc

        except Exception as e:
            self._notify("Simulation Error", f"Wind simulation failed: {str(e)}")
            return None