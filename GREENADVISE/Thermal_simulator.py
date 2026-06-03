import numpy as np
from PyQt5.QtWidgets import QMessageBox
from Scrape_from_Ninja import NinjaScraper
from config_loader import get_ninja_api_key, _config_path

class ThermalDemandSimulator:
    def __init__(self, parent=None, lat=None, lon=None):
        self.parent = parent
        self.lat = lat
        self.lon = lon

    def _notify(self, title, message):
        if self.parent:
            QMessageBox.critical(self.parent, title, message)
            raise ValueError(title, message)
        else:
            print(f"{title}: {message}")

    def simulate_yearly(self, yearly_inputs):
        try:
            heating_threshold = float(yearly_inputs["heating_threshold"])
            cooling_threshold = float(yearly_inputs["cooling_threshold"])
            annual_heating = float(yearly_inputs["annual_heating"])
            annual_cooling = float(yearly_inputs["annual_cooling"])
            year = yearly_inputs["year"]
            
            api_key = get_ninja_api_key()
            if not api_key:
                actual_path = _config_path()  
                QMessageBox.warning(
                    self.parent,
                    "Missing API key",
                    f"Please set your Renewables.ninja API key in:\n\n{actual_path}\n\nunder 'ninja_api_key'."
                )
                return


            scraper = NinjaScraper(
                api_key=api_key,
                lat=self.lat,
                lon=self.lon,
                temperature_inputs={"year": year, "dataset": "merra2"},
                parent=self.parent
            )
            
            temperatures = scraper.fetch_temperature()

            if len(temperatures) != 8760:
                self._notify("Temperature Fetch Error", "Temperature data is incomplete.")
                return

            heating_degree_hour = np.clip(heating_threshold - temperatures, a_min=0, a_max=None)
            cooling_degree_hour = np.clip(temperatures - cooling_threshold, a_min=0, a_max=None)

            total_heating_dh = heating_degree_hour.sum()
            total_cooling_dh = cooling_degree_hour.sum()

            if total_heating_dh > 0:
                heating_demand = heating_degree_hour * (annual_heating / total_heating_dh)
            else:
                heating_demand = np.zeros_like(heating_degree_hour)

            if total_cooling_dh > 0:
                cooling_demand = cooling_degree_hour * (annual_cooling / total_cooling_dh)
            else:
                cooling_demand = np.zeros_like(cooling_degree_hour)

            return heating_demand, cooling_demand

        except Exception as e:
            self._notify("Simulation Error", str(e))
            return

    def simulate_monthly(self, monthly_inputs):
        try:
            heating_threshold = float(monthly_inputs["heating_threshold"])
            cooling_threshold = float(monthly_inputs["cooling_threshold"])
            year = monthly_inputs["year"]
            
            api_key = get_ninja_api_key()
            if not api_key:
                actual_path = _config_path()  
                QMessageBox.warning(
                    self.parent,
                    "Missing API key",
                    f"Please set your Renewables.ninja API key in:\n\n{actual_path}\n\nunder 'ninja_api_key'."
                )
                return

            scraper = NinjaScraper(
                api_key=api_key,
                lat=self.lat,
                lon=self.lon,
                temperature_inputs={"year": year, "dataset": 'merra2'},
                parent=self.parent
            )
            temperatures = scraper.fetch_temperature()

            if len(temperatures) != 8760:
                self._notify("Temperature Fetch Error", "Temperature data is incomplete.")
                return

            heating_degree_hour = np.clip(heating_threshold - temperatures, a_min=0, a_max=None)
            cooling_degree_hour = np.clip(temperatures - cooling_threshold, a_min=0, a_max=None)

            heating_demand = np.zeros(8760)
            cooling_demand = np.zeros(8760)

            month_starts = [0, 744, 1416, 2160, 2880, 3624, 4344, 5088, 5832, 6552, 7296, 8016]
            month_lengths = [744, 672, 744, 720, 744, 720, 744, 744, 720, 744, 720, 744]

            for month in range(1, 13):
                _rh = monthly_inputs.get(f"month_{month}_heating", "") or ""
                _rc = monthly_inputs.get(f"month_{month}_cooling", "") or ""
                heating_total = float(_rh) if str(_rh).strip() else 0.0
                cooling_total = float(_rc) if str(_rc).strip() else 0.0

                start = month_starts[month - 1]
                end = start + month_lengths[month - 1]

                month_heating_dh = heating_degree_hour[start:end]
                month_cooling_dh = cooling_degree_hour[start:end]

                total_heating_dh = month_heating_dh.sum()
                total_cooling_dh = month_cooling_dh.sum()

                if total_heating_dh > 0:
                    heating_demand[start:end] = month_heating_dh * (heating_total / total_heating_dh)
                if total_cooling_dh > 0:
                    cooling_demand[start:end] = month_cooling_dh * (cooling_total / total_cooling_dh)

            return heating_demand, cooling_demand

        except Exception as e:
            self._notify("Monthly Simulation Error", str(e))
            return

if __name__ == "__main__":
    print("This is a supporting file for thermal demand simulation.")