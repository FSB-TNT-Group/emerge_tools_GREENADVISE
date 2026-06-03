import numpy as np
from PyQt5.QtWidgets import QMessageBox

class ElectricityDemandSimulator:
    @staticmethod
    def get_base_daily_curve():
        raw_curve = [
            0.0254, 0.0193, 0.0203, 0.0229, 0.0208, 0.0239,
            0.0452, 0.0645, 0.0559, 0.0432, 0.0335, 0.0345,
            0.034,  0.0335, 0.0325, 0.0416, 0.0498, 0.0625,
            0.0681, 0.0579, 0.0584, 0.0833, 0.0467, 0.0223
        ]
        total = sum(raw_curve)
        return [v / total for v in raw_curve]

    def __init__(self, parent=None):
        self.parent = parent
        self.profile = None
        self.BASE_DAILY_CURVE = self.get_base_daily_curve()

    def _notify(self, title, message):
        if self.parent:
            QMessageBox.critical(self.parent, title, message)
            raise ValueError(title, message)
        else:
            print(f"{title}: {message}")

    def _daily_load_profile(self, hour_of_day, peak1, peak2, dip):
        return (
            0.6 +
            0.25 * np.exp(-((hour_of_day - peak1) / 2) ** 2) +
            0.4 * np.exp(-((hour_of_day - peak2) / 2.5) ** 2) -
            0.2 * np.exp(-((hour_of_day - dip) / 2) ** 2)
        )

    def simulate_yearly(self, yearly_inputs, use_base_curve=False, noise=False):
        try:
            annual_demand = float(yearly_inputs["annual_demand"])
            hours = 8760

            if use_base_curve:
                daily_pattern = np.array(self.BASE_DAILY_CURVE * 365)
                if noise:
                    daily_pattern += np.random.normal(0, 0.02, size=daily_pattern.shape)
                    daily_pattern = np.clip(daily_pattern, 0.0001, None)

                profile = daily_pattern / daily_pattern.sum() * annual_demand
            else:
                morning_peak = int(float(yearly_inputs["morning_peak"]))
                evening_peak = int(float(yearly_inputs["evening_peak"]))
                dip_hour = int(float(yearly_inputs["dip_hour"]))

                hour_of_day = np.arange(hours) % 24
                day_of_year = np.arange(hours) // 24

                daily_profile = self._daily_load_profile(hour_of_day, morning_peak, evening_peak, dip_hour)
                seasonal_effect = 1 + 0.1 * np.cos(2 * np.pi * (day_of_year - 20) / 365)

                raw_profile = daily_profile * seasonal_effect

                if noise:
                    raw_profile += np.random.normal(0, 0.02, size=raw_profile.shape)
                    raw_profile = np.clip(raw_profile, 0.001, None)

                normalized = raw_profile / raw_profile.sum()
                profile = normalized * annual_demand

            self.profile = profile
            return self.profile

        except Exception as e:
            self._notify("Simulation Error", f"Invalid input: {str(e)}")
            return

    def simulate_monthly(self, monthly_inputs, use_base_curve=False, noise=False):
        try:
            hours = 8760
            profile = np.zeros(hours)
            month_days = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
            month_start = 0

            if use_base_curve:
                for i, days_in_month in enumerate(month_days):
                    _raw = monthly_inputs.get(f"month_{i+1}", "") or ""
                    month_kwh = float(_raw) if _raw.strip() else 0.0
                    base_daily = np.array(self.BASE_DAILY_CURVE * days_in_month)
                    if noise:
                        base_daily += np.random.normal(0, 0.02, size=base_daily.shape)
                        base_daily = np.clip(base_daily, 0.001, None)
                    base_month = base_daily / base_daily.sum() * month_kwh
                    profile[month_start:month_start + days_in_month * 24] = base_month
                    month_start += days_in_month * 24
            else:
                morning_peak = int(float(monthly_inputs["morning_peak"]))
                evening_peak = int(float(monthly_inputs["evening_peak"]))
                dip_hour = int(float(monthly_inputs["dip_hour"]))

                hour_of_day = np.arange(hours) % 24
                day_of_year = np.arange(hours) // 24

                daily_profile = self._daily_load_profile(hour_of_day, morning_peak, evening_peak, dip_hour)
                seasonal_effect = 1 + 0.1 * np.cos(2 * np.pi * (day_of_year - 20) / 365)

                raw_profile = daily_profile * seasonal_effect
                if noise:
                    raw_profile += np.random.normal(0, 0.02, size=raw_profile.shape)
                    raw_profile = np.clip(raw_profile, 0.001, None)

                for month_idx, days_in_month in enumerate(month_days):
                    month_hours = days_in_month * 24
                    month_end = month_start + month_hours

                    monthly_slice = raw_profile[month_start:month_end]
                    normalized_month = monthly_slice / monthly_slice.sum()
                    _raw = monthly_inputs.get(f"month_{month_idx+1}", "") or ""
                    month_kwh = float(_raw) if _raw.strip() else 0.0
                    profile[month_start:month_end] = normalized_month * month_kwh

                    month_start = month_end

            self.profile = profile
            return self.profile

        except Exception as e:
            self._notify("Simulation Error", f"Invalid input: {str(e)}")
            return



if __name__ == "__main__":
    print("ElectricityDemandSimulator is a supporting file.")
