import requests
import csv
import io
import numpy as np
from PyQt5.QtWidgets import QMessageBox

def trim_leap_day(array, target=8760):
    """Vrati niz duljine 8760. Ako je dulji -> odreži na 8760.
    (Ako je kraći, samo ga vrati nepromijenjenog.)"""
    if array is None:
        return None
    if isinstance(array, (list, np.ndarray)):
        arr = np.asarray(array, dtype=float).reshape(-1)
        if arr.size > target:
            return arr[:target]
        return arr
    return array

class NinjaScraper:
    def __init__(self, api_key, lat, lon,
                 pv_inputs=None, wind_inputs=None,
                 demand_inputs=None, temperature_inputs=None, parent=None):
        self.api_key = '58fb4d9b99edac5fdb9f82deb3d73adaad3baafe'
        self.headers = {'Authorization': f'Token {self.api_key}'}
        self.lat = lat
        self.lon = lon
        self.pv_inputs = pv_inputs
        self.wind_inputs = wind_inputs
        self.demand_inputs = demand_inputs
        self.temperature_inputs = temperature_inputs
        self.parent = parent

    def _has_none(self, d, ignore_keys=None):
        if d is None:
            return True
        ignore_keys = ignore_keys or []
        return any(v is None for k, v in d.items() if k not in ignore_keys)

    def _notify(self, title, message):
        if self.parent:
            QMessageBox.critical(self.parent, title, message)
            raise ValueError(title, message)
        else:
            print(f"{title}: {message}")

    def _get_data(self, url, params, target_column):
        try:
            response = requests.get(url, headers=self.headers, params=params)
            if response.status_code == 200:
                csv_reader = csv.reader(io.StringIO(response.text))
                data = [row for row in csv_reader if not row[0].startswith('#')]
                header = data[0]

                if target_column is None:
                    import pandas as pd
                    rows = data[1:]
                    df = pd.DataFrame(rows, columns=header)
                    expected_numeric = ['irradiance_direct', 'irradiance_diffuse', 'temperature', 'wind_speed']
                    for col in expected_numeric:
                        if col in df.columns:
                            df[col] = pd.to_numeric(df[col], errors='coerce')  
                    return df

                else:
                    def safe_float(value):
                        try:
                            return float(value)
                        except:
                            return 0
                    index = header.index(target_column)
                    return np.array([safe_float(row[index]) for row in data[1:]], dtype=object)
            else:
                self._notify("API Error", f"Failed to retrieve data (status code {response.status_code}).")
                return
        except Exception as e:
            self._notify("Connection Error", f"Error during API request: {str(e)}")
            return

    def fetch_pv(self):
        if self._has_none(self.pv_inputs, ignore_keys=["tracking"]):
            self._notify("Missing Input", "Skipping PV fetch due to incomplete inputs.")
            return

        print("Fetching PV data...")

        tracking_map = {
            "None": 0,
            "Single-axis": 1,
            "Dual-axis": 2,
             None: "none"
        }

        params = {
            'lat': self.lat,
            'lon': self.lon,
            'date_from': f"{self.pv_inputs['year']}-01-01",
            'date_to': f"{self.pv_inputs['year']}-12-31",
            'dataset': "merra2",
            'capacity': self.pv_inputs['capacity'],
            'system_loss': self.pv_inputs['loss'],
            'tracking': tracking_map[self.pv_inputs['tracking']],
            'tilt': self.pv_inputs['tilt'],
            'azim': self.pv_inputs['azimuth'],
            'format': 'csv'
        }

        return trim_leap_day(self._get_data("https://www.renewables.ninja/api/data/pv", params, "electricity"))

    def fetch_radiance(self):
        if self._has_none(self.pv_inputs, ignore_keys=["tracking"]):
            self._notify("Missing Input", "Skipping Radinance due to incomplete inputs.")
            return

        print("Fetching Radinace data...")

        tracking_map = {
            "None": 0,
            "Single-axis": 1,
            "Dual-axis": 2,
            None: "none"
        }

        params = {
            'lat': self.lat,
            'lon': self.lon,
            'date_from': f"{self.pv_inputs['year']}-01-01",
            'date_to': f"{self.pv_inputs['year']}-12-31",
            'dataset': "merra2",
            'capacity': self.pv_inputs.get('capacity',"1"),
            'system_loss': self.pv_inputs.get('loss', "0.1"),
            'tracking': tracking_map[self.pv_inputs.get('tracking',"None")],
            'tilt': self.pv_inputs['tilt'],
            'azim': self.pv_inputs['azimuth'],
            'format': 'csv',
            'raw': 'true'
        }

        df =  self._get_data("https://www.renewables.ninja/api/data/pv", params, None)

        if df is not None:
            direct = trim_leap_day(df['irradiance_direct'].to_numpy())
            diffuse = trim_leap_day(df['irradiance_diffuse'].to_numpy())
            temperature = trim_leap_day(df['temperature'].to_numpy())

            return {
                'direct': direct,
                'diffuse': diffuse,
                'temperature':temperature
            }

        return None

    def fetch_speed(self):
        if self._has_none(self.wind_inputs):
            self._notify("Missing Input", "Skipping Wind speed due to incomplete inputs.")
            return

        print("Fetching Wind speed...")

        params = {
            'lat': self.lat,
            'lon': self.lon,
            'date_from': f"{self.wind_inputs['year']}-01-01",
            'date_to': f"{self.wind_inputs['year']}-12-31",
            'dataset': "merra2",
            'height': self.wind_inputs.get('hub_height',"80"),
            'capacity': self.wind_inputs.get('capacity',"1"),
            'turbine': self.wind_inputs.get('turbine_model',"Vestas V90 2000"),
            'format': 'csv',
            'raw': 'true'
        }

        return trim_leap_day(self._get_data("https://www.renewables.ninja/api/data/wind", params, 'wind_speed'))

    def fetch_wind(self):
        if self._has_none(self.wind_inputs):
            self._notify("Missing Input", "Skipping Wind fetch due to incomplete inputs.")
            return

        print("Fetching Wind data...")

        params = {
            'lat': self.lat,
            'lon': self.lon,
            'date_from': f"{self.wind_inputs['year']}-01-01",
            'date_to': f"{self.wind_inputs['year']}-12-31",
            'dataset': "merra2",
            'height': self.wind_inputs['hub_height'],
            'capacity': self.wind_inputs['capacity'],
            'turbine': self.wind_inputs['turbine_model'],
            'format': 'csv'
        }

        return trim_leap_day(self._get_data("https://www.renewables.ninja/api/data/wind", params, "electricity"))

    def fetch_demand(self):
        if self._has_none(self.demand_inputs):
            self._notify("Missing Input", "Skipping Demand fetch due to incomplete inputs.")
            return

        print("Fetching Demand data...")

        params = {
            'lat': self.lat,
            'lon': self.lon,
            'date_from': f"{self.demand_inputs['year']}-01-01",
            'date_to': f"{self.demand_inputs['year']}-12-31",
            'dataset': "merra2",
            'heating_threshold': self.demand_inputs['heating_threshold'],
            'cooling_threshold': self.demand_inputs['cooling_threshold'],
            'base_power': self.demand_inputs['base_power'],
            'heating_power': self.demand_inputs['heating_power'],
            'cooling_power': self.demand_inputs['cooling_power'],
            'smoothing': self.demand_inputs['smoothing'],
            'solar_gains': self.demand_inputs['solar_gains'],
            'wind_chill': self.demand_inputs['wind_chill'],
            'humidity_discomfort': self.demand_inputs['humidity_discomfort'],
            'use_diurnal_profile': True,
            'local_time': True,
            'header': True,
            'format': 'csv'
        }

        return trim_leap_day(self._get_data("https://www.renewables.ninja/api/data/demand", params, "total_demand"))

    def fetch_temperature(self):
        if self._has_none(self.temperature_inputs):
            self._notify("Missing Input", "Skipping Temperature fetch due to incomplete temperature inputs.")
            return

        if "year" not in self.temperature_inputs or "dataset" not in self.temperature_inputs:
            self._notify("Missing Input", "Temperature inputs must include 'year' and 'dataset'.")
            return

        print("Fetching Temperature data...")

        params = {
            'lat': self.lat,
            'lon': self.lon,
            'date_from': f"{self.temperature_inputs['year']}-01-01",
            'date_to': f"{self.temperature_inputs['year']}-12-31",
            'dataset': "merra2",
            'format': 'csv',
            'header': True,
            'local_time': True,
            'var_t2m': True
        }

        try:
            response = requests.get("https://www.renewables.ninja/api/data/weather",
                                    headers=self.headers, params=params)

            if response.status_code == 200:
                csv_reader = csv.reader(io.StringIO(response.text))
                data = [row for row in csv_reader if not row[0].startswith('#')]
                header = data[0]
                t2m_index = header.index('t2m')
                raw_temp = np.array([float(row[t2m_index]) for row in data[1:]], dtype=float)
                return trim_leap_day(raw_temp)
            else:
                self._notify("API Error", f"Failed to retrieve temperature (status code {response.status_code}).")
                return
        except Exception as e:
            self._notify("Connection Error", f"Error fetching temperature: {str(e)}")
            return


