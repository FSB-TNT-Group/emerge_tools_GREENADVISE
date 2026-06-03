import os
import numpy as np
import pandas as pd
import csv
from PyQt5.QtWidgets import QMessageBox

class PriceGenerator:
    def __init__(self, parent=None):
        self.parent = parent
        self.folder_path = os.path.join(os.path.dirname(__file__), "ENTOSE-price_data")

    def _notify(self, title, message):
        if self.parent:
            QMessageBox.critical(self.parent, title, message)
            raise ValueError(title, message)
        else:
            print(f"{title}: {message}")

    def generate_price_country(self, country_price_inputs, noise=False):
        try:
            selected_country = country_price_inputs["selected_country"]
            filename = f"{selected_country}-day_price2023-24.csv"
            file_path = os.path.join(self.folder_path, filename)

            if not os.path.exists(file_path):
                raise FileNotFoundError(f"Price file for {selected_country} not found at:\n{file_path}")

            with open(file_path, encoding="utf-8") as f:
                reader = csv.reader(f, delimiter=',')
                next(reader)  
                prices = []
                for row in reader:
                    try:
                        price = float(row[1])
                        prices.append(price)
                    except (IndexError, ValueError):
                        continue

            if len(prices) < 8760:
                self._notify(f"Only {len(prices)} prices found, expected 8760.")

            prices_array = np.array(prices[:8760]) / 1000

            if noise:
                prices_array += np.random.normal(0, 0.005, size=prices_array.shape)
                prices_array = np.clip(prices_array, 0, 1.0) 

            return prices_array

        except Exception as e:
            self._notify("Country Price Load Error", str(e))
            return

    def generate_price_dual_tariff(self, dual_price_inputs, noise=False):
        try:
            daily_price = float(dual_price_inputs["dual_day"])
            night_price = float(dual_price_inputs["dual_night"])
            start_hour = int(dual_price_inputs["dual_start"])
            end_hour = int(dual_price_inputs["dual_end"])
            year = 2023

            times = pd.date_range(f"{year}-01-01 00:00", f"{year+1}-01-01 00:00", freq="h")[:-1]

            def is_day(hour):
                return start_hour <= hour < end_hour if start_hour <= end_hour else hour >= start_hour or hour < end_hour

            prices = np.array([
                daily_price if is_day(ts.hour) else night_price
                for ts in times
            ])

            if noise:
                prices += np.random.normal(0, 0.005, size=prices.shape)
                prices = np.clip(prices, 0, None)

            return prices

        except Exception as e:
            self._notify("Dual Tariff Error", str(e))
            return

    def generate_price_single_tariff(self, single_price_inputs, noise=False):
        try:
            one_tariff = float(single_price_inputs["one_tariff"])
            prices = np.full(8760, one_tariff)

            if noise:
                prices += np.random.normal(0, 0.005, size=prices.shape)
                prices = np.clip(prices, 0, None)

            return prices

        except Exception as e:
            self._notify("Single Tariff Error", str(e))
            return


if __name__ == "__main__":
    print("This is a supporting file for price array generation.")
