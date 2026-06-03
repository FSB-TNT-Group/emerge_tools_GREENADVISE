import pandas as pd
from PyQt5.QtWidgets import QMessageBox

class DataUpload:
    def __init__(self, parent=None):
        self.parent = parent

    def upload_pv_data_stochastic(self, filepath):
        cols = [f"pv_generation{i}" for i in range(1, 6)]
        return self._read_multi_columns_csv(filepath, cols)

    def upload_wind_data_stochastic(self, filepath):
        cols = [f"wind_generation{i}" for i in range(1, 6)]
        return self._read_multi_columns_csv(filepath, cols)

    def upload_electricity_data_stochastic(self, filepath):
        cols = [f"electricity_demand{i}" for i in range(1, 6)]
        return self._read_multi_columns_csv(filepath, cols)

    def upload_price_data_stochastic(self, filepath):
        cols = [f"buy_price{i}" for i in range(1, 6)]
        return self._read_multi_columns_csv(filepath, cols)

    def upload_thermal_demand_data_stochastic(self, filepath):
        cols = (
            [f"heating_demand{i}" for i in range(1, 6)] +
            [f"cooling_demand{i}" for i in range(1, 6)]
        )
        return self._read_multi_columns_csv(filepath, cols)

    def upload_pv_data(self, filepath):
        return self._read_single_column_csv(filepath, 'pv_generation')

    def upload_wind_data(self, filepath):
        return self._read_single_column_csv(filepath, 'wind_generation')

    def upload_electricity_data(self, filepath):
        return self._read_single_column_csv(filepath, 'electricity_demand')

    def upload_price_data(self, filepath):
        return self._read_single_column_csv(filepath, 'buy_price')

    def upload_thermal_demand_data(self, filepath):
        if not filepath or not filepath.endswith(".csv"):
            self._notify("File is not a valid .csv file.")
            return

        try:
            df = pd.read_csv(filepath, sep=";")

            if 'heating_demand' not in df.columns or 'cooling_demand' not in df.columns:
                self._notify("CSV must have 'heating_demand' and 'cooling_demand' columns.")
                return

            for col in ['heating_demand', 'cooling_demand']:
                df[col] = (
                    df[col]
                    .astype(str)
                    .str.replace(',', '.', regex=False)
                    .pipe(pd.to_numeric, errors='coerce')
                )

            df = df.dropna(subset=['heating_demand', 'cooling_demand'])

            if len(df) != 8760:
                self._notify(f"After cleaning, CSV must still have exactly 8760 valid rows. Found: {len(df)}")
                return

            return df['heating_demand'].to_numpy(), df['cooling_demand'].to_numpy()

        except Exception as e:
            raise ValueError(f"Error reading file: {e}")

    def _read_single_column_csv(self, filepath, column_name):
        if not filepath or not filepath.endswith(".csv"):
            self._notify("File is not a valid .csv file.")
            return

        try:
            df = pd.read_csv(filepath, sep=";")

            if column_name not in df.columns:
                self._notify(f"CSV must contain column: '{column_name}'")
                return

            df[column_name] = df[column_name].astype(str).str.replace(',', '.', regex=False)

            df[column_name] = pd.to_numeric(df[column_name], errors='coerce')

            df = df.dropna(subset=[column_name])

            if len(df) != 8760:
                self._notify(f"After cleaning, CSV must have exactly 8760 valid rows. Found: {len(df)}")
                return

            return df[column_name].to_numpy()

        except Exception as e:
            raise ValueError(f"Error reading file: {e}")

    def _read_multi_columns_csv(self, filepath, column_names):
        """
        Reads a CSV with multiple required columns, cleans decimals, validates 8760 rows,
        and returns a dict {col_name: numpy_array}.
        """
        if not filepath or not filepath.endswith(".csv"):
            self._notify("File is not a valid .csv file.")
            return

        try:
            df = pd.read_csv(filepath, sep=";")

            missing = [c for c in column_names if c not in df.columns]
            if missing:
                self._notify("CSV missing required columns: " + ", ".join(missing))
                return

            for col in column_names:
                df[col] = (
                    df[col]
                    .astype(str)
                    .str.replace(',', '.', regex=False)
                    .pipe(pd.to_numeric, errors='coerce')
                )

            df = df.dropna(subset=column_names)

            if len(df) != 8760:
                self._notify(f"After cleaning, CSV must have exactly 8760 valid rows. Found: {len(df)}")
                return

            return [df[col].to_numpy() for col in column_names]

        except Exception as e:
            raise ValueError(f"Error reading file: {e}")

    def _notify(self, message):
        if self.parent:
            QMessageBox.warning(self.parent, "File Upload Error", message)
            raise ValueError("File Upload Error", message)
        else:
            print("[Upload Error]", message)


class CO2DataLoader:
    @staticmethod
    def get_co2_by_country(filepath):
        df = pd.read_excel(filepath)
        df.columns = df.columns.str.strip()  
        df = df.rename(columns={df.columns[0]: "Country"})
        return {
            row["Country"]: {
                "Intermittent Gen (kgCO₂/kWh)": row[df.columns[1]]*10**-3,#gCO2/kWh to kgCO2/kWH
                "Firm Gen/Consumption (kgCO₂/kWh)": row[df.columns[2]]*10**-3,
                "HV Grid Loss (kgCO₂/kWh)": row[df.columns[3]]*10**-3,
                "MV Grid Loss (kgCO₂/kWh)": row[df.columns[4]]*10**-3,
                "LV Grid Loss (kgCO₂/kWh)": row[df.columns[5]]*10**-3,
            }
            for _, row in df.iterrows()
        }

    @staticmethod
    def get_co2_by_fuel(filepath):
        df = pd.read_excel(filepath)
        df.columns = df.columns.str.strip()  
    
        tj_dict = {}
        unit_dict = {}
    
        expected_cols = ["kg CO2", "kg CH4", "kg N2O", "kg CO2e", "kg CO2e incl, unox, carbon"]
        for col in expected_cols:
            if col not in df.columns:
                df[col] = None  
    
        for _, row in df.iterrows():
            fuel = str(row.get("Fuel Name", "")).strip()
            unit = str(row.get("Units", "")).strip()

            if not fuel or not unit:
                continue  

            if unit == 'TJ':

                fuel_data = {
                    "unit": unit,
                    "kg_CO2": row["kg CO2"]/((10**12)/(1000*3.6*10**6)),#TJ to kWh
                    "kg_CH4": row["kg CH4"],
                    "kg_N2O": row["kg N2O"],
                    "kg_CO2e": row["kg CO2e"]/((10**12)/(1000*3.6*10**6)),
                    "kg_CO2e_incl_unox": row["kg CO2e incl, unox, carbon"]/((10**12)/(1000*3.6*10**6)),
                }
            else:
                fuel_data = {
                    "unit": unit,
                    "kg_CO2": row["kg CO2"],
                    "kg_CH4": row["kg CH4"],
                    "kg_N2O": row["kg N2O"],
                    "kg_CO2e": row["kg CO2e"],
                    "kg_CO2e_incl_unox": row["kg CO2e incl, unox, carbon"],
                }

            if unit == "TJ":
                tj_dict[fuel] = fuel_data
            elif unit in ["cubic metre (m3)", "metric tonne (t)", "litres (l)"]:
                unit_dict[fuel] = fuel_data

        return tj_dict, unit_dict


    @staticmethod
    def get_co2_by_production_type(filepath):
        df = pd.read_excel(filepath)
        df.columns = df.columns.str.strip()

        if "Unit type" in df.columns:
            df["Unit type"] = df["Unit type"].ffill()

        def to_float_or_none(x):
            try:
                return float(x) if pd.notna(x) else None
            except Exception:
                return None

        records = []
        for _, row in df.iterrows():
            if pd.isna(row.get("Fuel")):
                continue

            ef_kwh = row.get("Emissions Factor tCO2e /GWh")
            ef_kwh = to_float_or_none(ef_kwh)
            if ef_kwh is not None:
                ef_kwh = ef_kwh / 1_000  # if your column is in g/kWh, convert to kg/kWh

            records.append({
                "unit_type": (None if pd.isna(row.get("Unit type")) else str(row.get("Unit type")).strip()),
                "fuel": str(row.get("Fuel")).strip(),
                "efficiency": to_float_or_none(row.get("Generation Efficiency")),  
                "EF_tCO2e_per_TJ": to_float_or_none(row.get("Emissions Factor t CO2e/TJ")),
                "oxidised_combustion": to_float_or_none(row.get("oxidised combustio n")),
                "EF_kgCO2e_per_kWh": ef_kwh,
            })

        return records

class ExternalCostDataLoader:

    @staticmethod
    def get_external_cost_by_country(filepath):
        df = pd.read_excel(filepath)
        df.columns = df.columns.str.strip()  
        df = df.rename(columns={df.columns[0]: "Country"})

        return {
            row["Country"]: {
                col: row[col] / 1000  
                for col in df.columns[1:]
            }
            for _, row in df.iterrows()
        }

    @staticmethod
    def get_external_cost_by_fuel_type(filepath):
        df = pd.read_excel(filepath)
        df.columns = df.columns.str.strip()
        df = df.rename(columns={df.columns[0]: "Technology", df.columns[1]: "Region"})

        return [
            {
                "fuel": row["Technology"],
                "region": row["Region"],
                **{col: row[col] / 1000 for col in df.columns[2:]}  
            }
            for _, row in df.iterrows()
        ]
