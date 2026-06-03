from PyQt5.QtWidgets import QMessageBox


class Technology:
    def __init__(self, parent=None):
        self.parent = parent

    def _notify(self, title, message):
        if self.parent:
            QMessageBox.critical(self.parent, title, message)
            raise ValueError(f"{title}: {message}")
        else:
            print("[Error]", message)

    def _validate_numeric_dict(self, inputs, context_name):
        validated = {}
        for key, val in inputs.items():
            try:
                cleaned = str(val).strip().replace(",", ".")
                validated[key] = float(cleaned)
            except (ValueError, TypeError):
                self._notify(f"{context_name} Input Error", f"'{key}' must be a number (int or float).")
        return validated

    def validate_heat_pump(self, hp_inputs):
        return self._validate_numeric_dict(hp_inputs, "Heat Pump")

    def validate_solar_collector(self, sc_inputs):
        return self._validate_numeric_dict(sc_inputs, "Solar Collector")

    def validate_battery(self, battery_inputs):
        return self._validate_numeric_dict(battery_inputs, "Battery")

    def validate_buffer_tank(self, buffer_inputs):
        return self._validate_numeric_dict(buffer_inputs, "Buffer Tank")

    def validate_emissions(self, emissions_inputs):
        return self._validate_numeric_dict(emissions_inputs, "Emissions")

if __name__ == "__main__":
    print("This is a helper script for validating technology inputs.")
