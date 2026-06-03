from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QWidget, QCheckBox, QGroupBox, QMessageBox, QLineEdit, QApplication
)
from PyQt5.QtCore import QThread, pyqtSignal, Qt
from config_loader import get_ninja_api_key, _config_path
import numpy as np
from Scrape_from_Ninja import NinjaScraper
from Stochastic_scraper import ScenarioGenerator


class _ScenarioWorker(QThread):
    done = pyqtSignal(object, str)  # (result_or_None, error_message)

    def __init__(self, fn):
        super().__init__()
        self._fn = fn

    def run(self):
        try:
            result = self._fn()
            self.done.emit(result, "")
        except Exception as e:
            self.done.emit(None, str(e))


class PrepareData:
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

    def __init__(self, workspace_manager):
        self.workspace_manager = workspace_manager
        self.dialog = None
        self.model_type_flag = {"is_deterministic": True}
        
        api_key = get_ninja_api_key()
        if not api_key:
            actual_path = _config_path()
            QMessageBox.warning(
                self.parent,
                "Missing API key",
                f"Please set your Renewables.ninja API key in:\n\n{actual_path}\n\nunder 'ninja_api_key'."
                )


        self.scraper = NinjaScraper(
            api_key=api_key,
            lat=None,
            lon=None,
            pv_inputs={},             
            wind_inputs={},           
            demand_inputs={},         
            temperature_inputs={},    
            parent=None               
        )

    def should_show_key(self, key, is_deterministic):
        if "Fetch Data" in key or "Simulate Data" in key or "Yearly" in key or "Monthly" in key or "Single" in key or "Country" in key or "Dual" in key or "Emission" in key or "External" in key:
            return True
        if is_deterministic:
            return "stochastic" not in key and "Stochastic" not in key
        else:
            return "stochastic" in key or "Stochastic" in key

    def run_input_selection_flow(self, parent):
        self.workspace = self.workspace_manager.get_workspace_data()


        self.scraper.parent = parent

        self.dialog = QDialog(parent)
        self.dialog.setWindowTitle("Select Inputs for Optimization")
        self.dialog.setMinimumSize(500, 600)

        layout = QVBoxLayout(self.dialog)
        self.dialog.setStyleSheet("""
            QCheckBox {
                background-color: white;
                font-size: 12px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
            }
            QCheckBox::indicator:unchecked {
                background-color: white;
                border: 1px solid black;
            }
            QCheckBox::indicator:checked {
                background-color: #b0b0b0;
                border: 1px solid black;
            }
            QCheckBox::indicator:hover {
                background-color: #e0e0e0;
            }
        """)

        model_group = QGroupBox("Optimization Model Type")
        model_group.setStyleSheet("QGroupBox { font-weight: bold; }")
        model_layout = QVBoxLayout()
        model_group.setLayout(model_layout)

        deterministic_cb = QCheckBox("Deterministic Model")
        two_stage_cb = QCheckBox("Two-Stage Stochastic Model  (LSTM-VAE)")

        model_layout.addWidget(deterministic_cb)
        model_layout.addWidget(two_stage_cb)
        layout.addWidget(model_group)

        model_checkboxes = [deterministic_cb, two_stage_cb]
        deterministic_cb.setChecked(True)

        def on_model_change(active_cb):
            for cb in model_checkboxes:
                cb.blockSignals(True)
                cb.setChecked(cb == active_cb)
                cb.blockSignals(False)

            self.model_type_flag["is_deterministic"] = deterministic_cb.isChecked()
            refresh_input_checkboxes()

        for cb in model_checkboxes:
            cb.clicked.connect(lambda _, c=cb: on_model_change(c))

        grid_group = QGroupBox("Grid Power Limit")
        grid_group.setStyleSheet("QGroupBox { font-weight: bold; }")
        grid_layout = QHBoxLayout()
        grid_group.setLayout(grid_layout)
        grid_label = QLabel("Grid Power Limit (kW):")
        grid_input = QLineEdit("inf")
        grid_input.setToolTip("Enter grid connection limit in kW (e.g. 0 or 'inf' for unlimited)")
        grid_layout.addWidget(grid_label)
        grid_layout.addWidget(grid_input)
        layout.addWidget(grid_group)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: 2px solid black; }")
        layout.addWidget(scroll)

        self.container = QWidget()
        self.container_layout = QVBoxLayout(self.container)
        scroll.setWidget(self.container)

        self.categories = {
            "PV Generation": ["PV"],
            "Wind Generation": ["Wind"],
            "Thermal Demand": ["Heating", "Cooling", "Thermal"],
            "Electricity Demand": ["Electricity"],
            "Price Data": ["Price", "Tariff"],
            "CO₂ Emissions": ["Emission Inputs", "Thermal Emission Inputs"],
            "External Cost": ["External Cost Inputs", "Thermal External Cost Inputs"],
        }

        self.groups = {}
        self.tech_inputs = ["Heat Pump", "Solar Collector", "Battery", "Buffer Tank"]
        self.tech_checks = []

        def create_checkbox(label, mapped_keys):
            checkbox = QCheckBox(label)
            checkbox._mapped_keys = mapped_keys
            return checkbox

        def refresh_input_checkboxes():
            for i in reversed(range(self.container_layout.count())):
                widget = self.container_layout.itemAt(i).widget()
                if widget:
                    widget.setParent(None)
            self.groups.clear()
            for label, keywords in self.categories.items():
                make_group(label, keywords)
            build_tech_inputs()

        def build_tech_inputs():
            tech_box = QGroupBox("Technology Inputs")
            tech_box.setStyleSheet("QGroupBox { font-weight: bold; }")
            tech_layout = QVBoxLayout()
            self.tech_checks.clear()

            for tech in self.tech_inputs:
                key = f"Input: {tech} Inputs"
                if key in self.workspace:
                    cb = QCheckBox(key)
                    cb.setChecked(True)
                    tech_layout.addWidget(cb)
                    self.tech_checks.append(cb)

            if not self.tech_checks:
                tech_layout.addWidget(QLabel("No data found."))

            tech_box.setLayout(tech_layout)
            self.container_layout.addWidget(tech_box)

        def on_checkbox_change(category, changed_cb):
            if category not in ["CO₂ Emissions", "External Cost"]:
                for cb in self.groups.get(category, []):
                    if cb != changed_cb:
                        cb.setChecked(False)

        def make_group(label, keywords):
            group_box = QGroupBox(label)
            group_box.setStyleSheet("QGroupBox { font-weight: bold; }")
            vbox = QVBoxLayout()
            checkboxes = []
            added = set()
            is_deterministic = self.model_type_flag["is_deterministic"]

            if label == "Thermal Demand":
                grouped = {}
                for key in self.workspace:
                    if not key.startswith("Data:") or key in added:
                        continue
                    if not self.should_show_key(key, is_deterministic):
                        continue
                    if "Thermal+Electricity" in key:
                        continue
                    if any(word in key for word in keywords):
                        base_key = key.replace(" Heating", "").replace(" Cooling", "")
                        if base_key not in grouped:
                            grouped[base_key] = []
                        grouped[base_key].append(key)

                for base_key, full_keys in grouped.items():
                    if "Uploaded" in base_key and "Stochastic" not in base_key and "stochastic" not in base_key and is_deterministic:
                        label_text = "Data: Uploaded Thermal Data"
                    elif "Uploaded" in base_key and (("Stochastic" in base_key) or ("stochastic" in base_key)) and not is_deterministic:
                        label_text = "Data: Uploaded Thermal Data (stochastic)"
                    elif "Yearly" in base_key:
                        label_text = "Data: Yearly Thermal Data"
                    elif "Monthly" in base_key:
                        label_text = "Data: Monthly Thermal Data"
                    else:
                        label_text = base_key

                    cb = create_checkbox(label_text, full_keys)
                    vbox.addWidget(cb)
                    checkboxes.append(cb)
                    added.update(full_keys)

            else:
                for key in self.workspace:
                    if label in ["CO₂ Emissions", "External Cost"]:
                        if not key.startswith("Input:") or key in added:
                            continue
                    else:
                        if not key.startswith("Data:") or key in added:
                            continue
                    if not self.should_show_key(key, is_deterministic):
                        continue
                    if label in ["Thermal Demand", "Electricity Demand"] and "Thermal+Electricity" in key:
                        continue
                    if any(word in key for word in keywords):
                        cb = create_checkbox(key, [key])
                        vbox.addWidget(cb)
                        checkboxes.append(cb)
                        added.add(key)

            for cb in checkboxes:
                cb.stateChanged.connect(lambda _, c=cb, cat=label: on_checkbox_change(cat, c))

            exclusive_groups = ["PV Generation", "Wind Generation", "Thermal Demand", "Electricity Demand", "Price Data"]

            if label in exclusive_groups:
                def on_exclusive_checkbox_clicked(checked, clicked_cb):
                    if checked:
                        for cb in checkboxes:
                            if cb != clicked_cb:
                                cb.blockSignals(True)
                                cb.setChecked(False)
                                cb.blockSignals(False)
                    else:
                        clicked_cb.setChecked(False)

                for cb in checkboxes:
                    cb.clicked.connect(lambda checked, c=cb: on_exclusive_checkbox_clicked(checked, c))

            # Auto-select on open: first item for exclusive groups, all for multi-select
            if checkboxes:
                if label in exclusive_groups:
                    checkboxes[0].blockSignals(True)
                    checkboxes[0].setChecked(True)
                    checkboxes[0].blockSignals(False)
                else:
                    for cb in checkboxes:
                        cb.blockSignals(True)
                        cb.setChecked(True)
                        cb.blockSignals(False)

            if not checkboxes:
                vbox.addWidget(QLabel("No data found."))

            group_box.setLayout(vbox)
            self.container_layout.addWidget(group_box)
            self.groups[label] = checkboxes

        refresh_input_checkboxes()

        btn_layout = QHBoxLayout()
        continue_btn = QPushButton("Continue")
        continue_btn.setStyleSheet(PrepareData.style)
        cancel_btn = QPushButton("Stop optimization")
        cancel_btn.setStyleSheet(PrepareData.style)
        btn_layout.addWidget(cancel_btn)
        btn_layout.addWidget(continue_btn)
        layout.addLayout(btn_layout)

        def accept():
            selected = {}
            input_metadata = {}
            is_deterministic = deterministic_cb.isChecked()

            try:
                grid_limit_str = grid_input.text().strip().lower()
                selected["Grid Power Limit"] = float("inf") if "inf" in grid_limit_str else float(grid_limit_str)
            except ValueError:
                QMessageBox.warning(self.dialog, "Invalid Grid Limit", "Grid power limit must be a number or 'inf'.")
                return

            for group_label, checkboxes in self.groups.items():
                for cb in checkboxes:
                    if cb.isChecked():
                        selected_key = cb._mapped_keys[0]

                        if group_label in ["PV Generation", "Wind Generation", "Thermal Demand", "Electricity Demand", "Price Data"]:
                            data, meta = self.handle_group_selection(group_label, selected_key, is_deterministic, self.workspace)
                            input_metadata.update(meta)

                            if group_label == "Thermal Demand":
                                heat_key = next((k for k in cb._mapped_keys if "Heating" in k), None)
                                cool_key = next((k for k in cb._mapped_keys if "Cooling" in k), None)
                                selected[group_label] = {
                                    "heating": self.workspace.get(heat_key),
                                    "cooling": self.workspace.get(cool_key),
                                }
                            else:
                                selected[group_label] = data

                        elif group_label == "CO₂ Emissions":
                            for key in cb._mapped_keys:
                                clean = key.replace("Input: ", "").strip()
                                selected.setdefault("CO₂ Emissions", {})[clean] = self.workspace[key]

                        elif group_label == "External Cost":
                            for key in cb._mapped_keys:
                                clean = key.replace("Input: ", "").strip()
                                selected.setdefault("External Cost", {})[clean] = self.workspace[key]

            for cb in self.tech_checks:
                if cb.isChecked():
                    tech_key = cb.text()  
                    tech_name = tech_key.replace("Input: ", "").replace("Inputs", "").strip()

                    tech_payload = self.workspace.get(tech_key, {})

                    selected[f"{tech_name} Inputs"] = tech_payload
                    input_metadata[f"{tech_name} Inputs"] = tech_payload


                    if tech_name == "Solar Collector" and "Data: Solar Collector Data" in self.workspace:
                        selected["Solar Collector Generation"] = self.workspace["Data: Solar Collector Data"]


            if "CO₂ Emissions" in selected:
                input_metadata["CO₂ Emissions"] = {
                    k: (v.copy() if isinstance(v, dict) else v)
                    for k, v in selected["CO₂ Emissions"].items()
                }

            if "External Cost" in selected:
                input_metadata["External Cost"] = {
                    k: (v.copy() if isinstance(v, dict) else v)
                    for k, v in selected["External Cost"].items()
                }

            if deterministic_cb.isChecked():
                input_metadata["model_type"] = "deterministic"
            elif two_stage_cb.isChecked():
                input_metadata["model_type"] = "two_stage_stochastic"
            else:
                QMessageBox.warning(self.dialog, "Model Selection", "Please select a model type.")
                return
            
            if not PrepareData.validate_selected_inputs(self.dialog, selected):
                return
            
            if input_metadata.get("model_type") == "two_stage_stochastic":
                # Configure scraper coordinates/inputs on the main thread before the worker starts
                self.scraper.parent = None  # prevent unsafe QMessageBox calls from worker thread
                self.stochastic_scraping(input_metadata, selected)

                # LSTM-VAE path produces 10 scenarios; legacy path uses 4
                pv_type   = input_metadata.get("PV Generation Type", "")
                wind_type = input_metadata.get("Wind Generation Type", "")
                _use_lstm = pv_type in ("simulate_scrape_pv", "fetch_scrape_pv",
                                         "simulate", "fetch") or \
                             wind_type in ("simulate_scrape_wind", "fetch_scrape_wind",
                                           "simulate", "fetch")
                n_scenarios = 10 if _use_lstm else 4
                _selected = selected
                _meta = input_metadata

                continue_btn.setEnabled(False)
                cancel_btn.setEnabled(False)
                lstm_note = " (LSTM-VAE, ~5 min)" if _use_lstm else ""
                continue_btn.setText(f"Generating {n_scenarios} scenarios{lstm_note}, please wait...")
                QApplication.setOverrideCursor(Qt.WaitCursor)

                def do_generate():
                    return self.materialize_two_stage_stochastic(_selected, _meta, n_scenarios)

                def on_done(result, err):
                    QApplication.restoreOverrideCursor()
                    continue_btn.setEnabled(True)
                    cancel_btn.setEnabled(True)
                    continue_btn.setText("Continue")
                    if result is None:
                        QMessageBox.critical(
                            self.dialog, "Stochastic Setup Failed",
                            err or "Scenario generation failed."
                        )
                        return
                    result['Price Data Inputs'] = _meta.get('Price Data Inputs', {})
                    self.dialog.selected_inputs = result
                    self.dialog.input_metadata = _meta
                    self.dialog.accept()

                self._stochastic_worker = _ScenarioWorker(do_generate)
                self._stochastic_worker.done.connect(on_done)
                self._stochastic_worker.start()
                return  # dialog stays open until worker calls dialog.accept()

            selected['Price Data Inputs'] = input_metadata['Price Data Inputs']

            self.dialog.selected_inputs = selected
            self.dialog.input_metadata = input_metadata
            self.dialog.accept()

        def reject():
            self.dialog.reject()

        continue_btn.clicked.connect(accept)
        cancel_btn.clicked.connect(reject)

        if self.dialog.exec_() != QDialog.Accepted:
            return None

        return {
            "selected_inputs": getattr(self.dialog, "selected_inputs", None),
            "input_metadata": getattr(self.dialog, "input_metadata", None)
        }

    @staticmethod
    def validate_selected_inputs(parent, selected_inputs):
        def decision_box(message):
            box = QMessageBox(parent)
            box.setIcon(QMessageBox.Warning)
            box.setWindowTitle("Input Conflict")
            box.setText(message)
            box.setStandardButtons(QMessageBox.Retry | QMessageBox.Ignore)
            box.button(QMessageBox.Retry).setText("Return to Selection")
            box.button(QMessageBox.Ignore).setText("Continue Without")
            return box.exec_()

        def warning(message):
            QMessageBox.warning(parent, "Input Warning", message)

        def pop_inputs(keys):
            for key in keys:
                selected_inputs.pop(key, None)

        demand_keys = ["Thermal + Electricity Demand", "Thermal Demand", "Electricity Demand"]
        has_any_demand = any(k in selected_inputs for k in demand_keys)
        has_price = "Price Data" in selected_inputs

        if not has_any_demand or not has_price:
            msg = "You must select at least one type of demand (Thermal + Electricity, Thermal, or Electricity) AND Price Data.\n\n"
            if not has_any_demand:
                msg += "- No demand selected.\n"
            if not has_price:
                msg += "- No price data selected.\n"
            warning(msg)
            return False

        elec_related = ["PV Generation", "Wind Generation", "Battery Inputs"]
        has_elec_demand = any(k in selected_inputs for k in ["Electricity Demand", "Thermal + Electricity Demand"])
        has_elec_gen_or_stor = any(k in selected_inputs for k in elec_related)

        if has_elec_gen_or_stor and not has_elec_demand:
            msg = (
                "You selected electricity generation or storage (PV, Wind, or Battery) "
                "but did not provide any electricity demand.\n"
                "These components will be ignored unless you go back and add electricity demand.\n\n"
            )
            if decision_box(msg) == QMessageBox.Retry:
                return False
            pop_inputs(elec_related)

        thermal_related = ["Heat Pump Inputs", "Solar Collector Inputs"]
        has_thermal_demand = "Thermal Demand" in selected_inputs
        has_thermal_gen = any(k in selected_inputs for k in thermal_related)
        has_thermal_storage = "Buffer Tank Inputs" in selected_inputs

        if has_thermal_demand and not has_thermal_gen:
            msg = (
                "You selected Thermal Demand but did not select any thermal generation technologies "
                "(Heat Pump or Solar Collector).\n"
                "Thermal demand will be ignored unless you go back and add generation.\n\n"
            )
            if decision_box(msg) == QMessageBox.Retry:
                return False
            pop_inputs(["Thermal Demand"])

        if (has_thermal_gen or has_thermal_storage) and not has_thermal_demand:
            msg = (
                "You selected thermal generation/storage but did not provide any Thermal Demand.\n"
                "Thermal generation and storage will be ignored unless you go back and add demand.\n\n"
            )
            if decision_box(msg) == QMessageBox.Retry:
                return False
            pop_inputs(thermal_related + ["Buffer Tank Inputs"])

        if "Thermal + Electricity Demand" in selected_inputs:
            conflicts = [k for k in ["Heat Pump Inputs", "Solar Collector Inputs", "Buffer Tank Inputs"] if k in selected_inputs]
            if conflicts:
                msg = (
                    "You selected Thermal + Electricity Demand which already includes thermal load in electrical form (kWh).\n"
                    "The following technologies will be ignored:\n- " + "\n- ".join(conflicts) + "\n\n"
                    "You may continue, but they will not be used."
                )
                warning(msg)
                pop_inputs(conflicts)

        if "Solar Collector Inputs" in selected_inputs and "Buffer Tank Inputs" not in selected_inputs:
            msg = (
                "You selected a Solar Collector but did not include a Buffer Tank.\n"
                "The collector requires thermal storage to function.\n\n"
            )
            warning(msg)
            pop_inputs(["Solar Collector Inputs"])
            return False

        return True

    def handle_group_selection(self, group_label, selected_key, is_deterministic, workspace):
        """
        Handles selection logic for PV, Wind, Thermal, Electricity, Price based on model type and input name.
        Returns tuple: (selected_data, input_metadata)
        """
        selected_data = workspace[selected_key]
        input_metadata = {}

        base_label = selected_key.replace("Data: ", "").strip()
        base_label = base_label.replace(" (stochastic)", "").replace(" (stochastic)", "").strip()

        if group_label == "PV Generation":
            if is_deterministic:
                if "Fetch" in selected_key:
                    input_metadata["PV Generation Type"] = "fetch"
                    input_metadata[group_label] = workspace.get("Input: PV Fetch Inputs", {})
                elif "Simulate" in selected_key:
                    input_metadata["PV Generation Type"] = "simulate"
                    input_metadata[group_label] = workspace.get("Input: PV Simulate Inputs", {})
                elif "Upload" in selected_key:
                    input_metadata["PV Generation Type"] = "upload"
                    input_metadata[group_label] = workspace.get("Input: PV Upload Inputs", {})
            else:
                if "Upload" in selected_key and ("Stochastic" in selected_key or "stochastic" in selected_key):
                    input_metadata["PV Generation Type"] = "upload_stochastic"
                    input_metadata[group_label] = workspace.get("Input: PV Upload Inputs (stochastic)", {}) or workspace.get("Input: PV Upload Inputs (stochastic)", {})
                else:
                    if "Fetch" in selected_key:
                        input_metadata["PV Generation Type"] = "fetch_scrape_pv"
                        input_metadata[group_label] = workspace.get("Input: PV Fetch Inputs", {})
                    elif "Simulate" in selected_key:
                        input_metadata["PV Generation Type"] = "simulate_scrape_pv"
                        input_metadata[group_label] = workspace.get("Input: PV Simulate Inputs", {})

        elif group_label == "Wind Generation":
            if is_deterministic:
                if "Fetch" in selected_key:
                    input_metadata["Wind Generation Type"] = "fetch"
                    input_metadata[group_label] = workspace.get("Input: Wind Fetch Inputs", {})
                elif "Simulate" in selected_key:
                    input_metadata["Wind Generation Type"] = "simulate"
                    input_metadata[group_label] = workspace.get("Input: Wind Simulate Inputs", {})
                elif "Upload" in selected_key:
                    input_metadata["Wind Generation Type"] = "upload"
                    input_metadata[group_label] = workspace.get("Input: Wind Upload Inputs", {})
            else:
                if "Upload" in selected_key and ("Stochastic" in selected_key or "stochastic" in selected_key):
                    input_metadata["Wind Generation Type"] = "upload_stochastic"
                    input_metadata[group_label] = workspace.get("Input: Wind Upload Inputs (stochastic)", {}) or workspace.get("Input: Wind Upload Inputs (stochastic)", {})
                else:
                    if "Fetch" in selected_key:
                        input_metadata["Wind Generation Type"] = "fetch_scrape_wind"
                        input_metadata[group_label] = workspace.get("Input: Wind Fetch Inputs", {})
                    elif "Simulate" in selected_key:
                        input_metadata["Wind Generation Type"] = "simulate_scrape_wind"
                        input_metadata[group_label] = workspace.get("Input: Wind Simulate Inputs", {})

        elif group_label == "Thermal Demand":
            if is_deterministic:
                if "Yearly" in selected_key:
                    input_metadata["Thermal Demand Type"] = "simulate_yearly"
                    input_metadata[group_label] = workspace.get("Input: Yearly Thermal Inputs", {})
                elif "Monthly" in selected_key:
                    input_metadata["Thermal Demand Type"] = "simulate_monthly"
                    input_metadata[group_label] = workspace.get("Input: Monthly Thermal Inputs", {})
                elif "Upload" in selected_key:
                    input_metadata["Thermal Demand Type"] = "upload"
                    input_metadata[group_label] = workspace.get("Input: Thermal Upload Inputs", {})
            else:
                if "Upload" in selected_key and ("Stochastic" in selected_key or "stochastic" in selected_key):
                    input_metadata["Thermal Demand Type"] = "upload_stochastic"
                    input_metadata[group_label] = workspace.get("Input: Thermal Upload Inputs (stochastic)", {}) or workspace.get("Input: Thermal Upload Inputs (stochastic)", {})
                else:
                    if "Yearly" in selected_key:
                        input_metadata["Thermal Demand Type"] = "yearly_scrape_thermal"
                        input_metadata[group_label] = workspace.get("Input: Yearly Thermal Inputs", {})
                    elif "Monthly" in selected_key:
                        input_metadata["Thermal Demand Type"] = "monthly_scrape_thermal"
                        input_metadata[group_label] = workspace.get("Input: Monthly Thermal Inputs", {})

        elif group_label == "Electricity Demand":
            if is_deterministic:
                if "Yearly" in selected_key:
                    input_metadata[group_label] = workspace.get("Input: Yearly Electricity Inputs", {})
                    if "morning_peak" in input_metadata[group_label]:
                        input_metadata["Electricity Demand Type"] = "simulate_yearly"
                    else:
                        input_metadata["Electricity Demand Type"] = "simulate_yearly_base"
                elif "Monthly" in selected_key:
                    input_metadata[group_label] = workspace.get("Input: Monthly Electricity Inputs", {})
                    if "morning_peak" in input_metadata[group_label]:
                        input_metadata["Electricity Demand Type"] = "simulate_monthly"
                    else:
                        input_metadata["Electricity Demand Type"] = "simulate_monthly_base"
                elif "Upload" in selected_key:
                    input_metadata["Electricity Demand Type"] = "upload"
                    input_metadata[group_label] = workspace.get("Input: Electricity Upload Inputs", {})
            else:
                if "Upload" in selected_key and ("Stochastic" in selected_key or "stochastic" in selected_key):
                    input_metadata["Electricity Demand Type"] = "upload_stochastic"
                    input_metadata[group_label] = workspace.get("Input: Electricity Upload Inputs (stochastic)", {}) or workspace.get("Input: Electricity Upload Inputs (stochastic)", {})
                else:
                    if "Yearly" in selected_key:
                        input_metadata["Electricity Demand Type"] = "yearly_scrape_electricity"
                        input_metadata[group_label] = workspace.get("Input: Yearly Electricity Inputs", {})
                    elif "Monthly" in selected_key:
                        input_metadata["Electricity Demand Type"] = "monthly_scrape_electricity"
                        input_metadata[group_label] = workspace.get("Input: Monthly Electricity Inputs", {})

        elif group_label == "Price Data":
            if is_deterministic:
                if "Single" in selected_key:
                    input_metadata["Price Type"] = "single"
                    input_metadata["Price Data Inputs"] = workspace.get("Input: Single Tariff Inputs", {})
                elif "Dual" in selected_key:
                    input_metadata["Price Type"] = "dual"
                    input_metadata["Price Data Inputs"] = workspace.get("Input: Dual Tariff Inputs", {})
                elif "Country" in selected_key:
                    input_metadata["Price Type"] = "country"
                    input_metadata["Price Data Inputs"] = workspace.get("Input: Country Price Inputs", {})
                elif "Upload" in selected_key:
                    input_metadata["Price Type"] = "upload"
                    input_metadata["Price Data Inputs"] = workspace.get("Input: Uploaded Price Inputs", {})
            else:
                if "Upload" in selected_key and ("Stochastic" in selected_key or "stochastic" in selected_key):
                    input_metadata["Price Type"] = "upload_stochastic"
                    input_metadata["Price Data Inputs"] = workspace.get("Input: Uploaded Price Inputs (stochastic)", {}) or workspace.get("Input: Uploaded Price Inputs (stochastic)", {})
                else:
                    if "Single" in selected_key:
                        input_metadata["Price Type"] = "single_scrape_price"
                        input_metadata["Price Data Inputs"] = workspace.get("Input: Single Tariff Inputs", {})
                    elif "Dual" in selected_key:
                        input_metadata["Price Type"] = "dual_scrape_price"
                        input_metadata["Price Data Inputs"] = workspace.get("Input: Dual Tariff Inputs", {})
                    elif "Country" in selected_key:
                        input_metadata["Price Type"] = "country_scrape_price"
                        input_metadata["Price Data Inputs"] = workspace.get("Input: Country Price Inputs", {})

        return selected_data, input_metadata

    def stochastic_scraping(self, input_metadata: dict, selected: dict) -> None:
        """
        Populate self.scraper.* safely using provided metadata/selected.
        No UI changes; no access to self.dialog.
        """
        meta = input_metadata or {}

        pv_meta      = meta.get("PV Generation", {}) or {}
        solar_meta   = meta.get("Solar Collector Inputs", {}) or {}
        wind_meta    = meta.get("Wind Generation", {}) or {}
        thermal_meta = meta.get("Thermal Demand", {}) or {}
        elec_meta    = meta.get("Electricity Demand", {}) or {}

        def _first_coord(metas, key, default):
            for m in metas:
                v = m.get(key)
                if v not in (None, ""):
                    try:
                        return float(v)
                    except Exception:
                        pass
            return default

        lat = _first_coord([pv_meta, wind_meta, thermal_meta, solar_meta, elec_meta], "latitude", 45.815)
        lon = _first_coord([pv_meta, wind_meta, thermal_meta, solar_meta, elec_meta], "longitude", 15.9819)

        self.scraper.lat = lat
        self.scraper.lon = lon

        def _merge(cur_dict, new_dict):
            cur = cur_dict or {}
            new = (new_dict or {}).copy()
            cur.update(new)
            return cur

        if pv_meta:
            self.scraper.pv_inputs = _merge(self.scraper.pv_inputs, pv_meta)
        elif solar_meta:
            self.scraper.pv_inputs = _merge(self.scraper.pv_inputs, solar_meta)
        if wind_meta:
            self.scraper.wind_inputs = _merge(self.scraper.wind_inputs, wind_meta)
        if thermal_meta:
            self.scraper.temperature_inputs = _merge(self.scraper.temperature_inputs, thermal_meta)

    def materialize_two_stage_stochastic(self, selected: dict, input_metadata: dict, n_scenarios: int = 4) -> dict:
        meta_for_gen = dict(input_metadata)

        if "Solar Collector Inputs" in selected:
            meta_for_gen["Solar Collector Inputs"] = selected["Solar Collector Inputs"]

        self._normalize_stochastic_types_for_generator(meta_for_gen, selected)

        pv_type   = meta_for_gen.get("PV Generation Type", "")
        wind_type = meta_for_gen.get("Wind Generation Type", "")

        # ── LSTM-VAE + Bootstrap + Heitsch-Römisch path ───────────────────────
        # Used when PV or wind data comes from the Renewables.ninja API.
        # Fetches 20 historical years, trains the LSTM-VAE, generates 1000
        # bootstrap scenarios, reduces to 10 with Heitsch-Römisch, then
        # solves the two-stage stochastic LP with the H-R probabilities.
        if pv_type in ("simulate", "fetch") or wind_type in ("simulate", "fetch"):
            return self._materialize_lstm_vae(selected, meta_for_gen)

        # ── Fallback: legacy ScenarioGenerator (upload / manual paths) ────────

        def _pick_base_year(meta):
            for k in ["Thermal Demand", "PV Generation", "Wind Generation", "Solar Collector Inputs", "Electricity Demand"]:
                y = (meta.get(k) or {}).get("year")
                if y:
                    try:
                        return int(y)
                    except Exception:
                        pass
            return 2023

        base_year_workspace = _pick_base_year(meta_for_gen)
        gen = ScenarioGenerator(
            selected_inputs=selected,
            input_metadata=meta_for_gen,
            scraper=self.scraper,
            base_year=base_year_workspace - 1,   
            steps=n_scenarios                    
        )
    
        selected["stochastic"] = {}
    
        def assign_scenario(name, scenarios):   
            selected["stochastic"][name] = scenarios
            if name not in selected:
                selected[name] = scenarios[0]

        stochastic_upload_map = {
            "PV Generation": ("PV Generation Type", "upload_stochastic"),
            "Wind Generation": ("Wind Generation Type", "upload_stochastic"),
            "Electricity Demand": ("Electricity Demand Type", "upload_stochastic"),
            "Thermal Demand": ("Thermal Demand Type", "upload_stochastic"),
            "Price Data": ("Price Type", "upload_stochastic"),
        }

        for key, (meta_key, expected_type) in stochastic_upload_map.items():
            if meta_for_gen.get(meta_key) == expected_type and key in selected:
                value = selected[key]

                if isinstance(value, list) and all(hasattr(arr, "__len__") for arr in value):
                    selected.setdefault("stochastic", {})[key] = value
                    selected[key] = value[0]

                elif (
                    key == "Thermal Demand" and
                    isinstance(value, dict) and
                    "heating" in value and "cooling" in value and
                    isinstance(value["heating"], list) and isinstance(value["cooling"], list)
                ):
                    selected.setdefault("stochastic", {})["Thermal Demand"] = {
                        "heating": value["heating"],
                        "cooling": value["cooling"],
                    }
                    selected["Thermal Demand"] = {
                        "heating": value["heating"][0],
                        "cooling": value["cooling"][0],
                    }

        price_type = meta_for_gen.get("Price Type", "")
        if price_type in ("single", "dual", "country"):
            assign_scenario("Price Data", gen.stochastic_price(n_scenarios))
    
        ed_type = meta_for_gen.get("Electricity Demand Type", "")
        if ed_type.startswith("simulate"):
            assign_scenario("Electricity Demand", gen.stochastic_electricity_demand(n_scenarios))
    
        th_type = meta_for_gen.get("Thermal Demand Type", "")
        if th_type in ("simulate_yearly", "simulate_monthly"):
            thermal_scenarios = gen.stochastic_thermal_demand(n_scenarios)
        
            heat_list = None
            cool_list = None
        
            if isinstance(thermal_scenarios, dict):
                if "heating" in thermal_scenarios and "cooling" in thermal_scenarios:
                    heat_list = thermal_scenarios["heating"]
                    cool_list = thermal_scenarios["cooling"]
                else:
                    if "Heating Demand Yearly Stochastic" in thermal_scenarios:
                        heat_list = thermal_scenarios["Heating Demand Yearly Stochastic"]
                        cool_list = thermal_scenarios["Cooling Demand Yearly Stochastic"]
                    if "Heating Demand Monthly Stochastic" in thermal_scenarios:
                        heat_list = thermal_scenarios["Heating Demand Monthly Stochastic"]
                        cool_list = thermal_scenarios["Cooling Demand Monthly Stochastic"]
        
            if heat_list is not None and cool_list is not None:
                selected["stochastic"]["Thermal Demand"] = {
                    "heating": heat_list,
                    "cooling": cool_list,
                }

                for k in [
                    "Heating Demand Yearly Stochastic",
                    "Cooling Demand Yearly Stochastic",
                    "Heating Demand Monthly Stochastic",
                    "Cooling Demand Monthly Stochastic",
                ]:
                    selected["stochastic"].pop(k, None)

    

        pv_type = meta_for_gen.get("PV Generation Type", "")
        if pv_type in ("simulate", "fetch"):
            assign_scenario("PV Generation", gen.stochastic_pv(n_scenarios))
    

        wind_type = meta_for_gen.get("Wind Generation Type", "")
        if wind_type in ("simulate", "fetch"):
            assign_scenario("Wind Generation", gen.stochastic_wind(n_scenarios))
    

        if meta_for_gen.get("Solar Collector Inputs"):
            assign_scenario("Solar Collector Generation", gen.stochastic_solar_collector(n_scenarios))

        self._prepend_base_into_stochastic(selected, n_scenarios)
        return selected

    # ─────────────────────────────────────────────────────────────────────────
    def _materialize_lstm_vae(self, selected: dict, meta_for_gen: dict) -> dict:
        """
        Generate stochastic scenarios using the LSTM-VAE + historical bootstrap
        + Heitsch-Römisch reduction pipeline (V1.1 engine).

        Fetches 20 historical years from Renewables.ninja, trains (or loads) the
        LSTM-VAE, generates 1000 bootstrap scenarios, and reduces to 10
        representative scenarios with Heitsch-Römisch probabilities.

        PV and wind are replaced by the 10 LSTM-VAE scenarios.
        Price, demand, and other inputs are replicated across all scenarios
        (their uncertainty is not modelled by the weather pipeline).
        """
        from scenario_generator import generate_scenarios
        from ninja_api import fetch_all_historical_years

        N_SCEN = 10

        api_key = get_ninja_api_key()
        lat     = self.scraper.lat  or 45.815
        lon     = self.scraper.lon  or 15.982

        pv_inp  = self.scraper.pv_inputs  or {}
        w_inp   = self.scraper.wind_inputs or {}

        pv_cap   = float(pv_inp.get("capacity", pv_inp.get("Pmax", 0)) or 0)
        pv_tilt  = float(pv_inp.get("tilt",      35) or 35)
        pv_azim  = float(pv_inp.get("azimuth",  180) or 180)
        _pv_track_raw = pv_inp.get("tracking", 0)
        pv_track = {"None": 0, "Single-axis": 1, "Dual-axis": 2}.get(
            str(_pv_track_raw), int(_pv_track_raw or 0) if str(_pv_track_raw or "0").isdigit() else 0
        )

        wind_cap    = float(w_inp.get("capacity", w_inp.get("rated_power", 0)) or 0)
        hub_height  = float(w_inp.get("hub_height", 80) or 80)
        turbine     = w_inp.get("turbine_model", "Vestas V80 2000") or "Vestas V80 2000"

        # Fetch 20 historical years (cached after first run).
        # On first run for a new location this costs ~40 API calls.
        # Results are cached to disk, so subsequent runs are free.
        import requests as _req
        _fetch_errors = []

        def _fetch_progress(msg):
            if msg.startswith("  Skipped"):
                _fetch_errors.append(msg)

        try:
            historical_years = fetch_all_historical_years(
                api_key, lat, lon,
                pv_capacity      = pv_cap,
                wind_capacity    = wind_cap,
                hub_height       = hub_height,
                turbine          = turbine,
                pv_tracking      = pv_track,
                pv_tilt          = pv_tilt,
                pv_azimuth       = pv_azim,
                progress_callback = _fetch_progress,
            )
        except _req.HTTPError as e:
            # Re-raise with a user-friendly message (already formatted in _ninja_get)
            raise RuntimeError(str(e)) from e

        # If all years failed, surface the real error
        if len(historical_years) == 0 and _fetch_errors:
            first_err = _fetch_errors[0].replace("  Skipped year ", "").strip()
            raise RuntimeError(
                f"Could not fetch historical weather data from Renewables.ninja.\n\n"
                f"Error: {first_err}\n\n"
                f"Tip: once successfully fetched, data is cached and this step "
                f"is skipped on all future runs for the same location."
            )

        # Run LSTM-VAE + bootstrap + Heitsch-Römisch → 10 scenarios + probabilities
        scenarios_raw, probabilities = generate_scenarios(
            historical_years,
            n_reduced = N_SCEN,
            lat       = lat,
            lon       = lon,
        )

        # ── Build V1 stochastic dict ──────────────────────────────────────
        selected["stochastic"] = {}

        pv_type   = meta_for_gen.get("PV Generation Type", "")
        wind_type = meta_for_gen.get("Wind Generation Type", "")

        if pv_type in ("simulate", "fetch"):
            pv_lists = [np.asarray(s["pv"], dtype=float) for s in scenarios_raw]
            selected["stochastic"]["PV Generation"] = pv_lists
            selected["PV Generation"] = pv_lists[0]

        if wind_type in ("simulate", "fetch"):
            wind_lists = [np.asarray(s["wind"], dtype=float) for s in scenarios_raw]
            selected["stochastic"]["Wind Generation"] = wind_lists
            selected["Wind Generation"] = wind_lists[0]

        # Replicate deterministic inputs across all scenarios for non-weather quantities
        for key in ("Price Data", "Electricity Demand", "Solar Collector Generation"):
            if key in selected and key not in selected["stochastic"]:
                base = selected[key]
                selected["stochastic"][key] = [
                    np.asarray(base, dtype=float) for _ in range(N_SCEN)
                ]

        if "Thermal Demand" in selected and "Thermal Demand" not in selected["stochastic"]:
            td = selected["Thermal Demand"]
            if isinstance(td, dict):
                selected["stochastic"]["Thermal Demand"] = {
                    "heating": [np.asarray(td["heating"], dtype=float) for _ in range(N_SCEN)],
                    "cooling": [np.asarray(td["cooling"], dtype=float) for _ in range(N_SCEN)],
                }

        # Store H-R probabilities — OptimizationStochastic reads these
        selected["stochastic_probabilities"] = probabilities

        return selected

    # ─────────────────────────────────────────────────────────────────────────
    def _normalize_stochastic_types_for_generator(self, meta_for_gen: dict, selected: dict) -> None:
        """
        Map your UI selection tags to ScenarioGenerator's expected types.
        - Price: *_scrape_price -> single/dual/country
        - PV/Wind: simulate_scrape_* -> simulate; fetch_scrape_* -> fetch
        - Thermal: yearly_scrape_thermal -> simulate_yearly; monthly_scrape_thermal -> simulate_monthly
        - Electricity: decide base vs non-base by presence of 'morning_peak'
        """

        pt = meta_for_gen.get("Price Type", "")
        if pt.endswith("_scrape_price"):
            if pt.startswith("single"):
                meta_for_gen["Price Type"] = "single"
            elif pt.startswith("dual"):
                meta_for_gen["Price Type"] = "dual"
            elif pt.startswith("country"):
                meta_for_gen["Price Type"] = "country"


        pvt = meta_for_gen.get("PV Generation Type", "")
        if pvt == "simulate_scrape_pv":
            meta_for_gen["PV Generation Type"] = "simulate"
        elif pvt == "fetch_scrape_pv":
            meta_for_gen["PV Generation Type"] = "fetch"


        wvt = meta_for_gen.get("Wind Generation Type", "")
        if wvt == "simulate_scrape_wind":
            meta_for_gen["Wind Generation Type"] = "simulate"
        elif wvt == "fetch_scrape_wind":
            meta_for_gen["Wind Generation Type"] = "fetch"


        tht = meta_for_gen.get("Thermal Demand Type", "")
        if tht == "yearly_scrape_thermal":
            meta_for_gen["Thermal Demand Type"] = "simulate_yearly"
        elif tht == "monthly_scrape_thermal":
            meta_for_gen["Thermal Demand Type"] = "simulate_monthly"


        et = meta_for_gen.get("Electricity Demand Type", "")
        elec_inputs = meta_for_gen.get("Electricity Demand", {}) or selected.get("Electricity Demand", {}) or {}
        
        if isinstance(elec_inputs, dict):
            raw_inputs = {
                k: float(v) if isinstance(v, str) and v.replace('.', '', 1).isdigit() else v
                for k, v in elec_inputs.items()
            }
        else:
            raw_inputs = {}  
        use_base = "morning_peak" not in raw_inputs

        if et == "yearly_scrape_electricity":
            meta_for_gen["Electricity Demand Type"] = "simulate_base" if use_base else "simulate"
            meta_for_gen["Electricity Demand"] = elec_inputs
        elif et == "monthly_scrape_electricity":
            meta_for_gen["Electricity Demand Type"] = "simulate_monthly_base" if use_base else "simulate_monthly"
            meta_for_gen["Electricity Demand"] = elec_inputs

    def _prepend_base_into_stochastic(self, selected: dict, n_scenarios: int = 4) -> None:
        """
        Ensure selected['stochastic'] lists start with the top-level base array(s),
        so each list has base + n_scenarios entries. Works for:
          - Price Data
          - Electricity Demand
          - PV Generation
          - Wind Generation
          - Solar Collector Generation
          - Thermal Demand {'heating','cooling'}
        """

        sto = selected.get("stochastic", {})
        if not isinstance(sto, dict):
            return
    
        def _same(a, b):
            try:
                aa = np.asarray(a, dtype=float)
                bb = np.asarray(b, dtype=float)
                if aa.shape != bb.shape:
                    return False
                return np.allclose(aa, bb, equal_nan=True)
            except Exception:
                return a is b  # fallback
    
        def prepend_simple(key: str):
            if key in selected and key in sto and isinstance(sto[key], list):
                base_arr = selected[key]
                if len(sto[key]) == n_scenarios:
                    if len(sto[key]) > 0 and _same(sto[key][0], base_arr):
                        sto[key][0] = base_arr
                    else:
                        sto[key] = [base_arr] + sto[key]
    
        for key in ["Price Data", "Electricity Demand", "PV Generation", "Wind Generation", "Solar Collector Generation"]:
            prepend_simple(key)
    
        if "Thermal Demand" in selected and "Thermal Demand" in sto:
            td = selected["Thermal Demand"]
            std = sto["Thermal Demand"]
            if isinstance(td, dict) and isinstance(std, dict):
                for comp in ["heating", "cooling"]:
                    if comp in td and comp in std and isinstance(std[comp], list):
                        base_arr = td[comp]
                        if len(std[comp]) == n_scenarios:
                            if len(std[comp]) > 0 and _same(std[comp][0], base_arr):
                                std[comp][0] = base_arr
                            else:
                                std[comp] = [base_arr] + std[comp]

        selected["stochastic"] = sto
