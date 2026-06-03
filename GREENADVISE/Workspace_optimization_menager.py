from PyQt5.QtWidgets import (
    QWidget, QListWidget, QVBoxLayout, QTabWidget, QPushButton, QHBoxLayout,
    QListWidgetItem, QMenu, QFileDialog, QMessageBox, QFrame, QLabel, QSizePolicy,
    QTextEdit, QStackedWidget
)
from PyQt5.QtCore import Qt, QEvent
import numpy as np
from Ploting_handler import PlottingHandler


class OptimizationWorkspaceManager(QWidget):
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

    def __init__(self, parent=None):
        super().__init__(parent)
        self.optimizations, self.result_lists = [], []
        self.selected_inputs_list = []
        self._build_ui()

    def _build_ui(self):
        self.tabs = QTabWidget(documentMode=True, tabPosition=QTabWidget.North)
        self.tabs.setMinimumHeight(40)
        self.tabs.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tabs.customContextMenuRequested.connect(self._show_tab_context_menu)

        plot_combined_button = QPushButton("Plot on Same Graph")
        plot_combined_button.setStyleSheet(OptimizationWorkspaceManager.style)
        plot_combined_button.setToolTip("Select items in the list above, then click to overlay them on one chart")
        plot_combined_button.clicked.connect(self._plot_selected_combined)

        plot_separate_button = QPushButton("Plot Separately")
        plot_separate_button.setStyleSheet(OptimizationWorkspaceManager.style)
        plot_separate_button.setToolTip("Select items in the list above, then click to show each in its own chart")
        plot_separate_button.clicked.connect(self._plot_selected_separate)

        container = QWidget()
        container.setObjectName("LeftTopBottomBorder")
        container.setStyleSheet("""
            #LeftTopBottomBorder {
                border-left: 1px solid black;
                border-top: 2px solid black;
                border-bottom: 2px solid black;
                border-right: 2px solid black;
                background-color: white;
            }
        """)

        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        # ── panel title ──
        _tb = QWidget()
        _tb.setFixedHeight(26)
        _tb.setStyleSheet("background-color: #2c2c2c; border: none;")
        _tl = QHBoxLayout(_tb)
        _tl.setContentsMargins(8, 0, 8, 0)
        _tlbl = QLabel("OPTIMIZATION RESULTS")
        _tlbl.setStyleSheet(
            "color: #ffffff; font-size: 9px; font-weight: bold;"
            " letter-spacing: 1.5px; background: transparent; border: none;"
        )
        _tl.addWidget(_tlbl)
        container_layout.addWidget(_tb)

        # ── content stack: page 0 = placeholder, page 1 = tabs + buttons ──
        self._content_stack = QStackedWidget()

        _ph = QLabel(
            "No optimization results yet.\n\n"
            "To run the optimization:\n\n"
            "  1.  Configure your system inputs using the\n"
            "       toolbar buttons (Generation, Storage,\n"
            "       Demand, Prices, Emissions).\n\n"
            "  2.  Click  ▶ Start Optimization  in the toolbar.\n\n"
            "Results will appear here as tabs — one tab\n"
            "per optimization run.\n\n"
            "Select items and use the plot buttons below\n"
            "to visualize time-series results."
        )
        _ph.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        _ph.setWordWrap(True)
        _ph.setStyleSheet(
            "QLabel { color: #b0b0b0; font-size: 11px; font-family: Arial;"
            " background: white; padding: 12px; border: none; }"
        )
        self._content_stack.addWidget(_ph)

        _inner = QWidget()
        _inner.setStyleSheet("background: white;")
        _il = QVBoxLayout(_inner)
        _il.setContentsMargins(6, 6, 6, 6)
        _il.setSpacing(4)
        _il.addWidget(self.tabs)

        _hint = QLabel("Click one or more items in the list above to select them, then plot.")
        _hint.setStyleSheet(
            "QLabel { color: #888888; font-size: 10px; font-style: italic;"
            " background: white; border: none; padding: 2px 0; }"
        )
        _il.addWidget(_hint)

        _btn_row = QHBoxLayout()
        _btn_row.addWidget(plot_combined_button)
        _btn_row.addWidget(plot_separate_button)
        _il.addLayout(_btn_row)
        self._content_stack.addWidget(_inner)

        container_layout.addWidget(self._content_stack, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(container)
        layout.setStretch(0, 1)

        self.setStyleSheet(self._style())
        self.installEventFilter(self)

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def setup_layout(self):
        self.setStyleSheet(self._style())

    def _style(self):
        return """
            QTabWidget::pane {
                border: none;
                top: -1px;
            }
            QTabBar::tab {
                min-width: 120px;
                font-size: 13px;
                font-weight: bold;
                font-family: Arial;
                padding: 6px 12px;
                background-color: #ffffff;
                border: 2px solid black;
                border-bottom: none;
                margin-right: 4px;
            }
            QTabBar::tab:selected {
                background-color: #f0f0f0;
                border-color: black;
            }
            QTabBar::tab:hover {
                background-color: #e6e6e6;
            }
            QListWidget {
                background-color: white;
                font-size: 12px;
                font-family: Arial;
                border: none;
                outline: none;
            }
            QListWidget::item {
                padding: 6px 10px;
                margin: 4px;
                background-color: white;
                border: none;
                border-radius: 4px;
                outline: none;
            }
            QListWidget::item:selected {
                background-color: #e0e0e0;
                color: black;
                border: none;
                outline: none;
            }
            QListWidget::item:focus {
                outline: none;
            }
        """

    def create_section_label(self, text):
        label = QLabel(text)
        label.setStyleSheet("""
            QLabel {
                font-size: 12px;
                font-weight: bold;
                padding: 4px;
                background-color: white;
                border: none;
            }
        """)
        return label

    def add_optimization_results(self, name, optimization_results, selected_inputs):
        if self._content_stack.currentIndex() == 0:
            self._content_stack.setCurrentIndex(1)
        filtered = {k: v for k, v in optimization_results.items() if v is not None and hasattr(v, '__len__') and len(v) > 0}
        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        tab.setStyleSheet("background-color: white;")
        tab_layout.setContentsMargins(0, 0, 0, 0)
    
        result_list = QListWidget()
        result_list.setSelectionMode(QListWidget.MultiSelection)
        result_list.itemDoubleClicked.connect(lambda item: PlottingHandler.show_workspace_item_details(self, item))
        result_list.setContextMenuPolicy(Qt.CustomContextMenu)
        result_list.customContextMenuRequested.connect(lambda pos: self._show_context_menu(result_list, pos))
        result_list.installEventFilter(self)
    
        for key, val in filtered.items():
            item = QListWidgetItem(str(key))
            item.setData(Qt.UserRole, val)
            result_list.addItem(item)

        tab_layout.addWidget(result_list)
        self.tabs.addTab(tab, name)

        self.optimizations.append(filtered)
        self.result_lists.append(result_list)

        if not hasattr(self, 'selected_inputs_list'):
            self.selected_inputs_list = []  
        self.selected_inputs_list.append(selected_inputs.copy() if selected_inputs else {})

    def get_selected_inputs(self, index=None):
        if index is None:
            index = self.tabs.currentIndex()
        if 0 <= index < len(self.selected_inputs_list):
            return self.selected_inputs_list[index]
        return {}

    def _get_current_tab_results(self):
        index = self.tabs.currentIndex()
        if index < 0 or index >= len(self.result_lists):
            return None, None
        return self.result_lists[index], self.optimizations[index]

    def _get_selected_data(self):
        result_list, _ = self._get_current_tab_results()
        if not result_list:
            return {}
        return {item.text(): item.data(Qt.UserRole) for item in result_list.selectedItems()}

    def _close_tab(self, index):
        if 0 <= index < len(self.optimizations):
            self.optimizations.pop(index)
            self.result_lists.pop(index)
            self.selected_inputs_list.pop(index)
            self.tabs.removeTab(index)

    def _show_tab_context_menu(self, pos):
        index = self.tabs.tabBar().tabAt(pos)
        if index >= 0:
            menu = QMenu(self)
            delete_action = menu.addAction("Delete Optimization Tab")
            if menu.exec_(self.tabs.mapToGlobal(pos)) == delete_action:
                self._close_tab(index)

    def _show_context_menu(self, list_widget, pos):
        item = list_widget.itemAt(pos)
        if item:
            menu = QMenu(self)
            delete_action = menu.addAction("Delete")
            if menu.exec_(list_widget.mapToGlobal(pos)) == delete_action:
                list_widget.takeItem(list_widget.row(item))

    def _plot_selected_combined(self):
        selected_data = self._get_selected_data()
        if not selected_data:
            QMessageBox.warning(self, "No Selection", "Please select results to plot.")
            return
        PlottingHandler._show_multi_series_popup(self, selected_data)

    def _plot_selected_separate(self):
        selected_data = self._get_selected_data()
        if not selected_data:
            QMessageBox.warning(self, "No Selection", "Please select results to plot separately.")
            return
        PlottingHandler.show_multi_series_separate_popup(self, selected_data)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonPress:
            for lst in self.result_lists:
                if not lst.geometry().contains(lst.mapFromGlobal(event.globalPos())):
                    lst.clearSelection()
        elif event.type() == QEvent.KeyPress and isinstance(obj, QListWidget) and event.key() == Qt.Key_Delete:
            item = obj.currentItem()
            if item:
                obj.takeItem(obj.row(item))
                return True
        return super().eventFilter(obj, event)


class FinancialWorkspaceManager(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.financial_data = []
        self.metadata_list = []
        self._build_ui()

    def _build_ui(self):
        self.tabs = QTabWidget(documentMode=True, tabPosition=QTabWidget.North)
        self.tabs.setMinimumHeight(40)

        container = QWidget()
        container.setObjectName("LeftTopBottomBorder")
        container.setStyleSheet("""
            #LeftTopBottomBorder {
                border-left: 2px solid black;
                border-top: 2px solid black;
                border-bottom: 2px solid black;
                border-right: None;
                background-color: white;
            }
        """)

        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        # ── panel title ──
        _tb = QWidget()
        _tb.setFixedHeight(26)
        _tb.setStyleSheet("background-color: #2c2c2c; border: none;")
        _tl = QHBoxLayout(_tb)
        _tl.setContentsMargins(8, 0, 8, 0)
        _tlbl = QLabel("FINANCIAL ANALYSIS")
        _tlbl.setStyleSheet(
            "color: #ffffff; font-size: 9px; font-weight: bold;"
            " letter-spacing: 1.5px; background: transparent; border: none;"
        )
        _tl.addWidget(_tlbl)
        container_layout.addWidget(_tb)

        # ── content stack: page 0 = placeholder, page 1 = tabs ──
        self._content_stack = QStackedWidget()

        _ph = QLabel(
            "Financial results will appear here\nafter running the optimization.\n\n"
            "This panel shows per run:\n\n"
            "  •  Total CAPEX & OPEX\n"
            "  •  Net profit and savings\n"
            "  •  Return on investment (ROI)\n"
            "  •  Payback period\n\n"
            "Results are calculated over a 20-year period."
        )
        _ph.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        _ph.setWordWrap(True)
        _ph.setStyleSheet(
            "QLabel { color: #b0b0b0; font-size: 11px; font-family: Arial;"
            " background: white; padding: 12px; border: none; }"
        )
        self._content_stack.addWidget(_ph)

        _inner = QWidget()
        _inner.setStyleSheet("background: white;")
        _il = QVBoxLayout(_inner)
        _il.setContentsMargins(6, 6, 6, 6)
        _il.addWidget(self.tabs)
        self._content_stack.addWidget(_inner)

        container_layout.addWidget(self._content_stack, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(container)
        layout.setStretch(0, 1)

        self.setStyleSheet(self._style())

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def setup_layout(self):
        self.setStyleSheet(self._style())

    def _style(self):
        return """
            QTabWidget::pane {
                border: none;
                top: -1px;
            }
            QTabBar::tab {
                min-width: 120px;
                font-size: 13px;
                font-weight: bold;
                font-family: Arial;
                padding: 6px 12px;
                background-color: #ffffff;
                border: 2px solid black;
                border-bottom: none;
                margin-right: 4px;
            }
            QTabBar::tab:selected {
                background-color: #f0f0f0;
                border-color: black;
            }
            QTabBar::tab:hover {
                background-color: #e6e6e6;
            }
            QListWidget {
                background-color: white;
                font-size: 12px;
                font-family: Arial;
                border: none;
                outline: none;
            }
            QListWidget::item {
                padding: 6px 10px;
                margin: 4px;
                background-color: white;
                border: none;
                border-radius: 4px;
                outline: none;
            }
            QListWidget::item:selected {
                background-color: #e0e0e0;
                color: black;
                border: none;
                outline: none;
            }
            QListWidget::item:focus {
                outline: none;
            }
        """

    def create_section_label(self, text):
        label = QLabel(text)
        label.setStyleSheet("""
            QLabel {
                font-size: 12px;
                font-weight: bold;
                padding: 4px;
                background-color: white;
                border: none;
            }
        """)
        return label

    def add_financial_summary(self, name, optimization_results, metadata, selected_inputs):
        if self._content_stack.currentIndex() == 0:
            self._content_stack.setCurrentIndex(1)
        roi_dict = self._calculate_financials(optimization_results, metadata, selected_inputs)

        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)

        list_widget = QListWidget()
        for key, val in roi_dict.items():
            if str(key).startswith("_"):      
                continue
            display = f"{key}: {val:.2f}" if isinstance(val, float) else f"{key}: {val}"
            item = QListWidgetItem(display)
            list_widget.addItem(item)

        tab_layout.addWidget(list_widget)
        self.tabs.addTab(tab, name)
        self.financial_data.append(roi_dict)
        self.metadata_list.append(metadata)

    def _calculate_financials(self, optimization_results, metadata, selected_inputs):
        battery_replacements = 2
    
        def safe_array(key):
            """Return a 8760-length float array; fall back to zeros if key missing/None/wrong shape."""
            v = optimization_results.get(key, None)
            if v is None:
                return np.zeros(8760, dtype=float)
            arr = np.asarray(v, dtype=float)
            if arr.shape == (8760,):
                return arr
            if arr.ndim == 0:
                return np.full(8760, float(arr), dtype=float)
            return np.zeros(8760, dtype=float)

        def buy_price_array():
            for k in ("Buy Price",):
                arr = safe_array(k)
                if np.any(arr): 
                    return arr
            return np.zeros(8760, dtype=float)

        tech_key_map = {
            "PV": "PV Generation",
            "Wind": "Wind Generation",
            "Heat Pump": "Heat Pump Inputs",
            "Thermal Storage": "Buffer Tank Inputs",
            "Battery": "Battery Inputs",
            "Solar Collector": "Solar Collector Inputs"
        }


        emissions = selected_inputs.get("CO₂ Emissions", {})
        thermal_emissions = emissions.get('Thermal Emission Inputs', {})
        mode = thermal_emissions.get('mode', '')
        fuel_price = float(thermal_emissions.get('fuel_price', 0) or 0)
        system_efficiancy = float(thermal_emissions.get('system_efficiency', 1) or 1)

        heating_demand = float(np.sum(safe_array("Heating Demand")))

        if mode == 'yearly fuel consumption':
            fuel_consumption = float(thermal_emissions.get('fuel_consumption', 0) or 0)
            old_thermal_cost = fuel_consumption * fuel_price
        else:
            eff = system_efficiancy if system_efficiancy > 0 else 1.0
            old_thermal_cost = heating_demand * fuel_price / eff

        used_techs = {tech: key in metadata for tech, key in tech_key_map.items()}

        capex = 0.0
        opex_annual = 0.0

        for tech, used in used_techs.items():
            if not used:
                continue

            meta_key = tech_key_map[tech]
            tech_meta = metadata.get(meta_key, {})

            try:
                capex_value = float(tech_meta.get("capex", 0) or 0)
                opex_value = float(tech_meta.get("opex", 0) or 0)
            except (TypeError, ValueError):
                raise ValueError(f"Invalid capex/opex format for {tech} in metadata: {tech_meta}")

            if tech == "Battery":
                capex += capex_value * battery_replacements
            else:
                capex += capex_value
                opex_annual += opex_value

        grid_to_hp_heat = safe_array("Grid → Heat Pump (heating)")
        price_series = buy_price_array()
        new_thermal_cost = float(np.sum(grid_to_hp_heat * price_series))


        diff_thermal_cost = max(old_thermal_cost - new_thermal_cost, 0.0)

        # 20-year totals
        opex = opex_annual * 20.0
        total_cost = capex + opex

        net_profit = float(np.sum(safe_array("Net profit")))
        savings_electricity = float(np.sum(safe_array("Savings")))
        savings = savings_electricity
        sum_net_profit = net_profit + savings + diff_thermal_cost

        total_sum_net_profit = sum_net_profit * 20.0
        total_sum_net_profit_minus_opex = total_sum_net_profit - opex

        roi_percent = ((total_sum_net_profit_minus_opex - capex) / capex) * 100.0 if capex > 0 else 0.0
        payback_time = (capex / (sum_net_profit - opex_annual)
                        if (sum_net_profit - opex_annual) > 0 else float("inf"))

        results = {
            "Technologies Used": ", ".join([k for k, v in used_techs.items() if v]),
            "Total CAPEX [€]": round(capex, 2),
            "Total OPEX (20 years) [€]": round(opex, 2),
            "Total Cost [€]": round(total_cost, 2),
            "Net profit + Saved Profit [€]": round(sum_net_profit, 2),
            "Total Profit (20 years) [€]": round(total_sum_net_profit, 2),
            "Net Profit - OPEX (20 years) [€]": round(total_sum_net_profit_minus_opex, 2),
            "ROI (20 years) [%]": round(roi_percent, 2),
            "Payback Time [years]": round(payback_time, 2) if payback_time != float("inf") else "∞"
        }
        
        results["_old_thermal_cost"] = old_thermal_cost
        results["_new_thermal_cost"] = new_thermal_cost
        results["_diff_thermal_cost"] = diff_thermal_cost
        return results

class EmissionsWorkspaceManager(QWidget):
    el_emission_dict = {
        "\nThe following data refers only to": "",
        "\nCO₂ emission before optimization [kg]": 0,
        "CO₂ emission after optimization [kg]": 0,
        "Saved emission after optimization [kg]": 0,
        "Saved emission after optimization [€]": 0,
        "Emission reduction [%]": 0,

        "\nExternal cost before optimization [€]": 0,

        "External cost breakdown before optimization [€]":
        "\n  • Climate Change - 0"
        "\n  • Particulate Matter - 0"
        "\n  • Toxicity - 0",

        "\nExternal cost after optimization [€]": 0,

        "External cost breakdown after optimization [€]":
        "\n  • Climate Change - 0"
        "\n  • Particulate Matter - 0"
        "\n  • Toxicity - 0",

        "Saved external cost after optimization [€]": 0,
        "External cost reduction [%]": 0,
    }

    th_emission_dict = el_emission_dict.copy()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.emission_data = []
        self.metadata_list = []
        self._build_ui()

    def _build_ui(self):
        self.tabs = QTabWidget(documentMode=True, tabPosition=QTabWidget.North)
        self.tabs.setMinimumHeight(40)

        container = QWidget()
        container.setObjectName("LeftTopBottomBorder")
        container.setStyleSheet("""
            #LeftTopBottomBorder {
                border-left: 2px solid black;
                border-top: None;
                border-bottom: 2px solid black;
                border-right: None;
                background-color: white;
            }
        """)

        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        # ── panel title ──
        _tb = QWidget()
        _tb.setFixedHeight(26)
        _tb.setStyleSheet("background-color: #2c2c2c; border: none;")
        _tl = QHBoxLayout(_tb)
        _tl.setContentsMargins(8, 0, 8, 0)
        _tlbl = QLabel("CO₂ EMISSIONS ANALYSIS")
        _tlbl.setStyleSheet(
            "color: #ffffff; font-size: 9px; font-weight: bold;"
            " letter-spacing: 1.5px; background: transparent; border: none;"
        )
        _tl.addWidget(_tlbl)
        container_layout.addWidget(_tb)

        # ── content stack: page 0 = placeholder, page 1 = tabs ──
        self._content_stack = QStackedWidget()

        _ph = QLabel(
            "Emissions analysis will appear here\nafter running the optimization.\n\n"
            "This panel shows per run:\n\n"
            "  •  CO₂ emissions before & after optimization\n"
            "  •  Emission reduction [%]\n"
            "  •  External costs (health & environment)\n"
            "  •  Electricity and thermal emission breakdown\n\n"
            "Make sure to configure CO₂ Emissions\n"
            "in the toolbar before running."
        )
        _ph.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        _ph.setWordWrap(True)
        _ph.setStyleSheet(
            "QLabel { color: #b0b0b0; font-size: 11px; font-family: Arial;"
            " background: white; padding: 12px; border: none; }"
        )
        self._content_stack.addWidget(_ph)

        _inner = QWidget()
        _inner.setStyleSheet("background: white;")
        _il = QVBoxLayout(_inner)
        _il.setContentsMargins(6, 6, 6, 6)
        _il.addWidget(self.tabs)
        self._content_stack.addWidget(_inner)

        container_layout.addWidget(self._content_stack, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(container)
        layout.setStretch(0, 1)

        self.setStyleSheet(self._style())

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def setup_layout(self):
        self.setStyleSheet(self._style())

    def _style(self):
        return """
            QTabWidget::pane {
                border: none;
                top: -1px;
            }
            QTabBar::tab {
                min-width: 120px;
                font-size: 13px;
                font-weight: bold;
                font-family: Arial;
                padding: 6px 12px;
                background-color: #ffffff;
                border: 2px solid black;
                border-bottom: none;
                margin-right: 4px;
            }
            QTabBar::tab:selected {
                background-color: #f0f0f0;
                border-color: black;
            }
            QTabBar::tab:hover {
                background-color: #e6e6e6;
            }
            QListWidget {
                background-color: white;
                font-size: 12px;
                font-family: Arial;
                border: none;
                outline: none;
            }
            QListWidget::item {
                padding: 6px 10px;
                margin: 4px;
                background-color: white;
                border: none;
                border-radius: 4px;
                outline: none;
            }
            QListWidget::item:selected {
                background-color: #e0e0e0;
                color: black;
                border: none;
                outline: none;
            }
            QListWidget::item:focus {
                outline: none;
            }
        """

    def create_section_label(self, text):
        label = QLabel(text)
        label.setStyleSheet("""
            QLabel {
                font-size: 12px;
                font-weight: bold;
                padding: 4px;
                background-color: white;
                border: none;
            }
        """)
        return label

    def add_emissions_summary(self, name, optimization_results, metadata, selected_inputs):
        if self._content_stack.currentIndex() == 0:
            self._content_stack.setCurrentIndex(1)

        emissions_report = self._calculate_emissions(optimization_results, metadata, selected_inputs)

        tab = QWidget()
        tab_layout = QVBoxLayout(tab)
        tab_layout.setContentsMargins(0, 0, 0, 0)

        list_widget = QListWidget()
        for key, val in emissions_report.items():
            display = f"{key}: {val:.2f}" if isinstance(val, float) else f"{key}: {val}"
            item = QListWidgetItem(display)
            list_widget.addItem(item)

        tab_layout.addWidget(list_widget)
        self.tabs.addTab(tab, name)
        self.emission_data.append(emissions_report)
        self.metadata_list.append(metadata)

    def _calculate_emissions(self, optimization_results, metadata, selected_inputs):
        import numpy as np
    
        def safe_array(key):
            v = optimization_results.get(key, None)
            if v is None:
                return np.zeros(8760, dtype=float)
            arr = np.asarray(v, dtype=float)
            if arr.shape == (8760,):
                return arr
            if arr.ndim == 0:
                return np.full(8760, float(arr), dtype=float)
            return np.zeros(8760, dtype=float)
    
        def to_float(x, default=0.0):
            try:
                if x is None:
                    return default
                if isinstance(x, str) and x.strip() == "":
                    return default
                return float(x)
            except (TypeError, ValueError):
                return default
    
        # reset dicts to avoid stari podaci
        self.el_emission_dict = {}
        self.th_emission_dict = {}
    
        saved_emissions = None
        saved_emissions_eur = None
        saved_emissions_th = None
        saved_emissions_th_eur = None
        saved_external_cost = None
        saved_external_cost_th = None
    
        CO2_electric = 0.0
        CO2_thermal = 0.0
    
        electricity_demand = float(np.sum(safe_array("Electricity Demand")))
    
        emissions = selected_inputs.get("CO₂ Emissions", {})
        emissions_inputs = emissions.get('Emission Inputs', {})
        CO2_price = to_float(emissions_inputs.get("emission_price"), 0.0)
        CO2_emission_value = to_float(emissions_inputs.get("emission_value"), 0.0)
        system_efficiency = to_float(emissions_inputs.get("system_efficiency"), 1.0)
        yearly_fuel_consumption = to_float(emissions_inputs.get("fuel_consumption"), 0.0)
        mode = emissions_inputs.get("mode", '')
    
        if mode == 'yearly fuel consumption':
            CO2_electric = yearly_fuel_consumption * CO2_emission_value
        else:
            eff = system_efficiency if 0 < system_efficiency < 1 else 1.0
            CO2_electric = CO2_emission_value / eff
    

        external_cost = selected_inputs.get("External Cost", {})
        external_cost_inputs = external_cost.get("External Cost Inputs", {})
        mode_ex_c = external_cost_inputs.get("mode", '')
        external_health_price_el = to_float(external_cost_inputs.get("external_ht_cost"), 0.0)
        external_particulate_price_el = to_float(external_cost_inputs.get("external_pm_cost"), 0.0)
        if mode_ex_c == 'External cost manual':
            eff = system_efficiency if system_efficiency > 0 else 1.0
            external_health_price_el /= eff
            external_particulate_price_el /= eff
    
        if electricity_demand != 0:
            if CO2_electric == 0:
                self.el_emission_dict["\nThe following data refers only to"] = "Electricity"
            else:
                base_electricity_emissions = electricity_demand * CO2_electric
    
                base_external_cost_climate_change = CO2_electric * electricity_demand * CO2_price
                base_external_cost_particulate_matter = external_particulate_price_el * electricity_demand
                base_external_cost_toxicity = external_health_price_el * electricity_demand
                base_external_cost = (base_external_cost_climate_change +
                                      base_external_cost_particulate_matter +
                                      base_external_cost_toxicity)
    
                electricity_import_after_optimization = float(np.sum(safe_array("Grid → Load")))
                electricity_emissions_after_optimization = electricity_import_after_optimization * CO2_electric
    
                saved_emissions = base_electricity_emissions - electricity_emissions_after_optimization
                saved_emissions_eur = saved_emissions * CO2_price
                saved_emission_pct = (100 * saved_emissions / base_electricity_emissions
                                      if base_electricity_emissions > 0 else 0.0)
    
                after_external_cost_climate_change = CO2_electric * electricity_import_after_optimization * CO2_price
                after_external_cost_particulate_matter = external_particulate_price_el * electricity_import_after_optimization
                after_external_cost_toxicity = external_health_price_el * electricity_import_after_optimization
                electricity_external_cost_after_optimization = (after_external_cost_climate_change +
                                                                after_external_cost_particulate_matter +
                                                                after_external_cost_toxicity)
    
                saved_external_cost = base_external_cost - electricity_external_cost_after_optimization
                saved_external_cost_pct = (100 * saved_external_cost / base_external_cost
                                           if base_external_cost > 0 else 0.0)
    
                self.el_emission_dict = {
                    "\nThe following data refers only to": "Electricity",
                    "CO₂ emission before optimization [kg]": base_electricity_emissions,
                    "CO₂ emission after optimization [kg]": electricity_emissions_after_optimization,
                    "Saved emission after optimization [kg]": saved_emissions,
                    "Saved emission after optimization [€]": saved_emissions_eur,
                    "Emission reduction [%]": saved_emission_pct,
                    "External cost before optimization [€]": base_external_cost,
                    "External cost breakdown before optimization [€]":
                        f"\n  • Climate Change - {base_external_cost_climate_change:.2f}"
                        f"\n  • Particulate Matter - {base_external_cost_particulate_matter:.2f}"
                        f"\n  • Toxicity - {base_external_cost_toxicity:.2f}",
                    "External cost after optimization [€]": electricity_external_cost_after_optimization,
                    "External cost breakdown after optimization [€]":
                        f"\n  • Climate Change - {after_external_cost_climate_change:.2f}"
                        f"\n  • Particulate Matter - {after_external_cost_particulate_matter:.2f}"
                        f"\n  • Toxicity - {after_external_cost_toxicity:.2f}",
                    "Saved external cost after optimization [€]": saved_external_cost,
                    "External cost reduction [%]": saved_external_cost_pct,
                }
        else:
            self.el_emission_dict["\nThe following data refers only to"] = "Electricity"
    
        heating_demand = float(np.sum(safe_array("Heating Demand")))
        if heating_demand != 0:
            emissions_th = selected_inputs.get("CO₂ Emissions", {})
            emissions_inputs_th = emissions_th.get('Thermal Emission Inputs', {})
            CO2_price_th = to_float(emissions_inputs_th.get("emission_price"), 0.0)
            CO2_emission_value_th = to_float(emissions_inputs_th.get("emission_value"), 0.0)
            system_efficiency_th = to_float(emissions_inputs_th.get("system_efficiency"), 1.0)
            yearly_fuel_consumption_th = to_float(emissions_inputs_th.get("fuel_consumption"), 0.0)
            mode_th = emissions_inputs_th.get("mode", '')
    
            if mode_th == 'yearly fuel consumption':
                CO2_thermal = yearly_fuel_consumption_th * CO2_emission_value_th
            else:
                eff_th = system_efficiency_th if 0 < system_efficiency_th < 1 else 1.0
                CO2_thermal = CO2_emission_value_th / eff_th
    
            external_cost_inputs_th = selected_inputs.get("External Cost", {}) \
                                                  .get("Thermal External Cost Inputs", {})
            mode_ex_c_th = external_cost_inputs_th.get("mode", '')
            external_health_price_th = to_float(external_cost_inputs_th.get("external_ht_cost"), 0.0)
            external_particulate_price_th = to_float(external_cost_inputs_th.get("external_pm_cost"), 0.0)
            if mode_ex_c_th == 'External cost manual':
                eff_th = system_efficiency_th if system_efficiency_th > 0 else 1.0
                external_health_price_th /= eff_th
                external_particulate_price_th /= eff_th
    
            if CO2_thermal == 0:
                self.th_emission_dict["\nThe following data refers only to"] = 'Thermal'
            else:
                base_thermal_emissions = heating_demand * CO2_thermal
    
                base_external_cost_climate_change_th = CO2_thermal * heating_demand * CO2_price_th
                base_external_cost_particulate_matter_th = external_particulate_price_th * heating_demand
                base_external_cost_toxicity_th = external_health_price_th * heating_demand
                base_external_cost_th = (base_external_cost_climate_change_th +
                                         base_external_cost_particulate_matter_th +
                                         base_external_cost_toxicity_th)
    
                hp_heating_after_optimization = float(np.sum(safe_array("Grid → Heat Pump (heating)")))
                hp_cooling_after_optimization = float(np.sum(safe_array("Grid → Heat Pump (cooling)")))
    
                if hp_heating_after_optimization > 0 or hp_cooling_after_optimization > 0:
                    # HP koristi STRUJU -> koristi EL koeficijente za "external cost"
                    thermal_import_after_optimization = hp_heating_after_optimization + hp_cooling_after_optimization
                    thermal_emissions_after_optimization = thermal_import_after_optimization * CO2_electric
    
                    saved_emissions_th = base_thermal_emissions - thermal_emissions_after_optimization
                    saved_emissions_th_eur = saved_emissions_th * CO2_price_th
                    saved_emission_pct_th = (100 * saved_emissions_th / base_thermal_emissions
                                             if base_thermal_emissions > 0 else 0.0)
    
                    after_external_cost_climate_change_th = CO2_electric * thermal_import_after_optimization * CO2_price
                    after_external_cost_particulate_matter_th = external_particulate_price_el * thermal_import_after_optimization
                    after_external_cost_toxicity_th = external_health_price_el * thermal_import_after_optimization
    
                    thermal_external_cost_after_optimization = (after_external_cost_climate_change_th +
                                                                after_external_cost_particulate_matter_th +
                                                                after_external_cost_toxicity_th)
                else:
                    thermal_import_after_optimization = 0.0
                    thermal_emissions_after_optimization = 0.0
    
                    saved_emissions_th = base_thermal_emissions - thermal_emissions_after_optimization
                    saved_emissions_th_eur = saved_emissions_th * CO2_price_th
                    saved_emission_pct_th = (100 * saved_emissions_th / base_thermal_emissions
                                             if base_thermal_emissions > 0 else 0.0)
    
                    after_external_cost_climate_change_th = CO2_thermal * thermal_import_after_optimization * CO2_price_th
                    after_external_cost_particulate_matter_th = external_particulate_price_th * thermal_import_after_optimization
                    after_external_cost_toxicity_th = external_health_price_th * thermal_import_after_optimization
    
                    thermal_external_cost_after_optimization = (after_external_cost_climate_change_th +
                                                                after_external_cost_particulate_matter_th +
                                                                after_external_cost_toxicity_th)
    
                saved_external_cost_th = base_external_cost_th - thermal_external_cost_after_optimization
                saved_external_cost_pct_th = (100 * saved_external_cost_th / base_external_cost_th
                                              if base_external_cost_th > 0 else 0.0)
    
                self.th_emission_dict = {
                    "\nThe following data refers only to": 'Thermal',
                    "CO₂ emission before optimization [kg]": base_thermal_emissions,
                    "CO₂ emission after optimization [kg]": thermal_emissions_after_optimization,
                    "Saved emission after optimization [kg]": saved_emissions_th,
                    "Saved emission after optimization [€]": saved_emissions_th_eur,
                    "Emission reduction [%]": saved_emission_pct_th,
                    "Thermal External cost before optimization [€]": base_external_cost_th,
                    "Thermal External cost breakdown before optimization [€]":
                        f"\n  • Climate Change - {base_external_cost_climate_change_th:.2f}"
                        f"\n  • Particulate Matter - {base_external_cost_particulate_matter_th:.2f}"
                        f"\n  • Toxicity - {base_external_cost_toxicity_th:.2f}",
                    "External cost after optimization [€]": thermal_external_cost_after_optimization,
                    "External cost breakdown after optimization [€]":
                        f"\n  • Climate Change - {after_external_cost_climate_change_th:.2f}"
                        f"\n  • Particulate Matter - {after_external_cost_particulate_matter_th:.2f}"
                        f"\n  • Toxicity - {after_external_cost_toxicity_th:.2f}",
                    "Saved external cost after optimization [€]": saved_external_cost_th,
                    "External cost reduction [%]": saved_external_cost_pct_th,
                }
        else:
            self.th_emission_dict["\nThe following data refers only to"] = "Thermal"
    
        def prefix_keys(d, prefix):
            return {f"{prefix} {k.strip()}": v for k, v in d.items()}
    
        result = {}
        if saved_emissions is not None:
            result.update(prefix_keys(self.el_emission_dict, "[Electricity]"))
        if saved_emissions_th is not None:
            result.update(prefix_keys(self.th_emission_dict, "[Thermal]"))
    
        total_saved_em_eur = 0.0
        if saved_emissions_eur is not None:
            total_saved_em_eur += saved_emissions_eur
        if saved_emissions_th_eur is not None:
            total_saved_em_eur += saved_emissions_th_eur
        result["Total saved on Emissions [€]"] = total_saved_em_eur

        total_saved_ext_eur = 0.0
        if saved_external_cost is not None:
            total_saved_ext_eur += saved_external_cost
        if saved_external_cost_th is not None:
            total_saved_ext_eur += saved_external_cost_th
        result["Total saved on External costs [€]"] = total_saved_ext_eur

        return result


class OptimizationTextAnalysisManager(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self):
        self.tabs = QTabWidget(documentMode=True, tabPosition=QTabWidget.North)
        self.tabs.setMinimumHeight(40)

        container = QWidget()
        container.setObjectName("LeftTopBottomBorder")
        container.setStyleSheet("""
            #LeftTopBottomBorder {
                border-left: None;
                border-top: None;
                border-bottom: 4px solid black;
                border-right: None;
                background-color: white;
            }
        """)

        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        # ── panel title ──
        _tb = QWidget()
        _tb.setFixedHeight(26)
        _tb.setStyleSheet("background-color: #2c2c2c; border: none;")
        _tl = QHBoxLayout(_tb)
        _tl.setContentsMargins(8, 0, 8, 0)
        _tlbl = QLabel("ANALYSIS REPORT")
        _tlbl.setStyleSheet(
            "color: #ffffff; font-size: 9px; font-weight: bold;"
            " letter-spacing: 1.5px; background: transparent; border: none;"
        )
        _tl.addWidget(_tlbl)
        container_layout.addWidget(_tb)

        # ── content stack: page 0 = placeholder, page 1 = tabs ──
        self._content_stack = QStackedWidget()

        _ph = QLabel(
            "The analysis report will appear here\nafter running the optimization.\n\n"
            "This section includes:\n\n"
            "  •  Profitability assessment\n"
            "  •  Self-consumption vs. grid import\n"
            "  •  Revenue, savings, and electricity cost\n"
            "  •  CO₂ savings and emission reduction\n"
            "  •  External cost analysis\n"
            "  •  Thermal demand coverage\n"
            "  •  Energy charts (pie charts)\n\n"
            "One report tab is generated per optimization run."
        )
        _ph.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        _ph.setWordWrap(True)
        _ph.setStyleSheet(
            "QLabel { color: #b0b0b0; font-size: 11px; font-family: Arial;"
            " background: white; padding: 12px; border: none; }"
        )
        self._content_stack.addWidget(_ph)

        _inner = QWidget()
        _inner.setStyleSheet("background: white;")
        _il = QVBoxLayout(_inner)
        _il.setContentsMargins(6, 6, 6, 6)
        _il.addWidget(self.tabs)
        self._content_stack.addWidget(_inner)

        container_layout.addWidget(self._content_stack, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(container)
        layout.setStretch(0, 1)

        self.setStyleSheet(self._style())

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        container.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def setup_layout(self):
        self.setStyleSheet(self._style())

    def _style(self):
        return """
            QTabWidget::pane {
                border: none;
                top: -1px;
            }
            QTabBar::tab {
                min-width: 120px;
                font-size: 13px;
                font-weight: bold;
                font-family: Arial;
                padding: 6px 12px;
                background-color: #ffffff;
                border: 2px solid black;
                border-bottom: none;
                margin-right: 4px;
            }
            QTabBar::tab:selected {
                background-color: #f0f0f0;
                border-color: black;
            }
            QTabBar::tab:hover {
                background-color: #e6e6e6;
            }
            QListWidget {
                background-color: white;
                font-size: 12px;
                font-family: Arial;
                border: none;
                outline: none;
            }
            QListWidget::item {
                padding: 6px 10px;
                margin: 4px;
                background-color: white;
                border: none;
                border-radius: 4px;
                outline: none;
            }
            QListWidget::item:selected {
                background-color: #e0e0e0;
                color: black;
                border: none;
                outline: none;
            }
            QListWidget::item:focus {
                outline: none;
            }
        """

    def create_section_label(self, text):
        label = QLabel(text)
        label.setStyleSheet("""
            QLabel {
                font-size: 12px;
                font-weight: bold;
                padding: 4px;
                background-color: white;
                border: none;
            }
        """)
        return label

    def add_analysis(self, name, selected_inputs, optimization_results, financial_summary, emissions_summary):
        if self._content_stack.currentIndex() == 0:
            self._content_stack.setCurrentIndex(1)
        text = self._generate_text_analysis(financial_summary, emissions_summary, optimization_results, name)

        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)


        charts_widget = PlottingHandler.create_three_pie_charts_widget( 
            selected_inputs, optimization_results, financial_summary, emissions_summary
        )
        layout.addWidget(charts_widget)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        layout.addWidget(line)  

        text_widget = QTextEdit()
        text_widget.setReadOnly(True)
        text_widget.setStyleSheet("""
            QTextEdit {
                background-color: white;
                font-family: Arial;
                font-size: 12px;
                border: none;
            }
        """)
        text_widget.setHtml(text)

        layout.addWidget(text_widget)
        self.tabs.addTab(tab, name)

    def _generate_text_analysis(self, financial, emissions, optimization_results, tab_name="this optimization"):

        def safe_array(key):
            val = optimization_results.get(key)
            return val if isinstance(val, np.ndarray) and val.shape == (8760,) else np.zeros(8760)

        capex = financial.get("Total CAPEX [€]", 0)
        opex = financial.get("Total OPEX (20 years) [€]", 0)
        total_cost = financial.get("Total Cost [€]", 0)
        payback = financial.get("Payback Time [years]", "∞")
        old_thermal_cost = financial.get("_old_thermal_cost", 0)
        new_thermal_cost = financial.get("_new_thermal_cost", 0)
        diff_thermal_cost = financial.get("_diff_thermal_cost", 0)

        electricity_demand = np.sum(safe_array("Electricity Demand"))
        heating_demand = np.sum(safe_array("Heating Demand"))
        cooling_demand = np.sum(safe_array("Cooling Demand"))

        # Self-consumption = energy reaching the load from own generation (not from grid).
        # Battery→Load counted once (own storage reaching load).  No double-counting of
        # renewable→battery charges.
        usage_of_renewables = (
            safe_array("PV → Load") +
            safe_array("Wind → Load") +
            safe_array("PV → Heat Pump (heating)") +
            safe_array("PV → Heat Pump (cooling)") +
            safe_array("Wind → Heat Pump (heating)") +
            safe_array("Wind → Heat Pump (cooling)") +
            safe_array("Battery → Load") +
            safe_array("Battery → Heat Pump (heating)") +
            safe_array("Battery → Heat Pump (cooling)")
        )
        self_consumption = float(np.sum(usage_of_renewables))

        imported_from_grid = (
            safe_array("Grid → Load") +
            safe_array("Grid → Heat Pump (heating)") +
            safe_array("Grid → Heat Pump (cooling)")
        )
        grid_import = float(np.sum(imported_from_grid))

        total_supply = self_consumption + grid_import
        if total_supply > 0:
            self_consumption_pct = 100.0 * self_consumption / total_supply
            grid_import_pct      = 100.0 * grid_import      / total_supply
        else:
            self_consumption_pct = 0.0
            grid_import_pct      = 0.0

        revenue     = np.sum(safe_array("Revenue"))
        savings     = np.sum(safe_array("Savings"))
        cost        = np.sum(safe_array("Cost"))
        net_profit  = revenue + savings - cost
        unmet_elec  = np.sum(safe_array("Unmet Electricity Demand"))
        unmet_heat  = np.sum(safe_array("Unmet Heating Demand"))
        unmet_cool  = np.sum(safe_array("Unmet Cooling Demand"))
        pv_lost     = np.sum(safe_array("PV Lost"))
        wind_lost   = np.sum(safe_array("Wind Lost"))
        unmet_buffer = np.sum(safe_array("Unmet Solar Collector → Buffer Tank"))

        co2_base          = emissions.get("[Electricity] CO₂ emission before optimization [kg]", 0)
        co2_saved         = emissions.get("[Electricity] Saved emission after optimization [kg]", 0)
        co2_pct           = emissions.get("[Electricity] Emission reduction [%]", 0)
        co2_emitted_pct   = 100 - co2_pct if co2_base > 0 else 0
        base_ext_cost     = emissions.get("[Electricity] External cost before optimization [€]", 0)
        optimized_ext_cost = emissions.get("[Electricity] External cost after optimization [€]", 0)
        ext_cost_saved    = emissions.get("[Electricity] Saved external cost after optimization [€]", 0)
        ext_cost_saved_pct = emissions.get("[Electricity] External cost reduction [%]", 0)

        # ── HTML helpers ──────────────────────────────────────────────────────
        def section(title):
            return (
                f"<div style='margin:18px 0 6px 0; padding:5px 10px; "
                f"background-color:#f5f7fa; border-left:4px solid #2e7d32; "
                f"font-size:12px; font-weight:bold; color:#1b3a2d; "
                f"letter-spacing:0.4px;'>{title}</div>"
            )

        def badge(text, color):
            bg = {"green": "#e8f5e9", "red": "#ffebee", "blue": "#e3f2fd",
                  "orange": "#fff3e0", "grey": "#f5f5f5"}.get(color, "#f5f5f5")
            fg = {"green": "#1b5e20", "red": "#b71c1c", "blue": "#0d47a1",
                  "orange": "#e65100", "grey": "#555"}.get(color, "#333")
            return (f"<span style='background-color:{bg}; color:{fg}; "
                    f"font-weight:bold; padding:1px 6px; border-radius:3px;'>{text}</span>")

        def warn(text):
            return (f"<div style='margin:4px 0; padding:5px 10px; "
                    f"background-color:#fff8e1; border-left:3px solid #f9a825; "
                    f"color:#4a3800; font-size:12px;'>{text}</div>")

        def alert(text):
            return (f"<div style='margin:4px 0; padding:5px 10px; "
                    f"background-color:#ffebee; border-left:3px solid #c62828; "
                    f"color:#7f0000; font-size:12px;'>{text}</div>")

        def ok(text):
            return (f"<div style='margin:4px 0; padding:5px 10px; "
                    f"background-color:#e8f5e9; border-left:3px solid #2e7d32; "
                    f"color:#1b5e20; font-size:12px;'>{text}</div>")

        def row(label, value_html, note=""):
            note_td = (f"<td style='padding:3px 6px; color:#777; font-size:11px;'>{note}</td>"
                       if note else "")
            return (f"<tr>"
                    f"<td style='padding:3px 16px 3px 0; color:#444; white-space:nowrap;'>{label}</td>"
                    f"<td style='padding:3px 16px 3px 0; font-weight:bold;'>{value_html}</td>"
                    f"{note_td}</tr>")

        tbl_open  = "<table style='border-collapse:collapse; margin:6px 0 6px 8px;'>"
        tbl_close = "</table>"
        p = "<p style='margin:5px 0 5px 8px; font-size:12px; color:#333;'>"

        # ── Build HTML ────────────────────────────────────────────────────────
        html = ("<html><body style='font-family:Arial,sans-serif; font-size:12px; "
                "color:#222; line-height:1.55; margin:8px 12px;'>")

        # ── 1. INVESTMENT & PROFITABILITY ─────────────────────────────────────
        html += section("1 · INVESTMENT &amp; PROFITABILITY")

        if isinstance(payback, (int, float)) and payback <= 20:
            html += ok(f"<b>{tab_name}</b> — total investment of "
                       f"<b>€{total_cost:,.2f}</b> is profitable within a 20-year period.")
        else:
            html += alert(f"<b>{tab_name}</b> — total investment of <b>€{total_cost:,.2f}</b> "
                          f"is <b>not profitable within 20 years.</b> "
                          f"Try lowering technology costs, adjusting demand, or resizing capacities.")

        html += tbl_open
        pb_color = "green" if isinstance(payback, (int, float)) and payback <= 20 else "red"
        pb_str = f"{payback:.1f} yrs" if isinstance(payback, (int, float)) else "∞ (not recovered)"
        html += row("Capital Expenditure (CAPEX)", badge(f"€{capex:,.2f}", "blue"))
        html += row("Total Operating Expenses (20 yr)", badge(f"€{opex:,.2f}", "blue"))
        html += row("Payback Period", badge(pb_str, pb_color))
        html += tbl_close

        # ── 2. ENERGY PERFORMANCE ─────────────────────────────────────────────
        if electricity_demand > 0:
            html += section("2 · ENERGY PERFORMANCE")
            html += tbl_open
            html += row("Electricity demand covered by own generation",
                        badge(f"{self_consumption_pct:.1f}%", "green"))
            html += row("Remaining demand imported from grid",
                        badge(f"{grid_import_pct:.1f}%",
                              "blue" if grid_import_pct < 60 else "orange"))
            if diff_thermal_cost > 0:
                html += row("Annual heating cost saving (electrification)",
                            badge(f"€{diff_thermal_cost:,.2f}", "green"),
                            f"was €{old_thermal_cost:,.2f} → now €{new_thermal_cost:,.2f}")
            html += tbl_close

        # ── 3. SYSTEM DIAGNOSTICS ─────────────────────────────────────────────
        html += section("3 · SYSTEM DIAGNOSTICS")

        # Electricity
        if unmet_elec == 0:
            html += ok("All electricity demand is met — electricity capacities are well dimensioned.")
        else:
            html += alert(f"Unmet electricity demand: <b>{unmet_elec:,.1f} kWh</b>. "
                          f"Consider expanding technology capacities or increasing the grid limit.")

        # Thermal
        if heating_demand != 0 or cooling_demand != 0:
            if unmet_heat == 0 and unmet_cool == 0:
                html += ok("All thermal demand is met — heating and cooling capacities are well sized.")
            else:
                parts = []
                if unmet_heat != 0:
                    parts.append(f"unmet heating: <b>{unmet_heat:,.1f} kWh-th</b>")
                if unmet_cool != 0:
                    parts.append(f"unmet cooling: <b>{unmet_cool:,.1f} kWh-th</b>")
                html += alert(f"{', '.join(parts).capitalize()}. "
                              f"Consider expanding thermal technology capacities.")
            if unmet_buffer != 0:
                html += warn(f"Lost heat generation from collector: <b>{unmet_buffer:,.1f} kWh-th</b> "
                             f"due to undersized buffer tank. Consider increasing thermal storage "
                             f"or reducing solar collector area.")

        # PV / Wind curtailment
        if pv_lost != 0 or wind_lost != 0:
            parts = []
            if pv_lost != 0:
                parts.append(f"PV: <b>{pv_lost:,.1f} kWh</b>")
            if wind_lost != 0:
                parts.append(f"wind: <b>{wind_lost:,.1f} kWh</b>")
            html += warn(f"Curtailed generation — {', '.join(parts)} lost due to grid export limit, "
                         f"full battery, or fully met demand. Consider increasing storage or grid limit.")

        # ── 4. FINANCIAL SUMMARY ──────────────────────────────────────────────
        html += section("4 · ANNUAL FINANCIAL SUMMARY")
        html += tbl_open
        html += row("Revenue (grid exports &amp; arbitrage)",
                    badge(f"€{revenue:,.2f}", "green"),
                    "selling surplus energy at high prices")
        html += row("Savings (self-consumption)",
                    badge(f"€{savings:,.2f}", "green"),
                    "avoided grid purchases from own generation")
        html += row("Cost (grid electricity purchases)",
                    badge(f"€{cost:,.2f}", "orange"),
                    "imports at low prices &amp; unmet demand from grid")
        net_color = "green" if net_profit >= 0 else "red"
        html += row("Net Annual Profit",
                    badge(f"€{net_profit:,.2f}", net_color))
        html += tbl_close

        # ── 5. STOCHASTIC SCENARIO ANALYSIS ───────────────────────────────────
        ss_exp = optimization_results.get("stoch_profit_expected")
        if ss_exp is not None:
            ss_min   = optimization_results.get("stoch_profit_min", ss_exp)
            ss_max   = optimization_results.get("stoch_profit_max", ss_exp)
            ss_p10   = optimization_results.get("stoch_profit_p10", ss_exp)
            ss_p90   = optimization_results.get("stoch_profit_p90", ss_exp)
            n_sc     = optimization_results.get("stoch_n_scenarios", 0)
            true_vss = optimization_results.get("stoch_true_vss")
            eev      = optimization_results.get("stoch_eev")
            ev_mean  = optimization_results.get("stoch_ev_profit_mean")
            spread   = ss_max - ss_min

            sc_label = f"{n_sc} scenarios, LSTM-VAE bootstrap" if n_sc else "scenarios"
            html += section(f"5 · STOCHASTIC SCENARIO ANALYSIS  ({sc_label})")

            html += tbl_open
            html += row("Expected annual profit (SS)",
                        badge(f"€{ss_exp:,.0f}", "green" if ss_exp >= 0 else "red"))
            html += row("Best-case scenario",
                        badge(f"€{ss_max:,.0f}", "green"))
            html += row("Worst-case scenario",
                        badge(f"€{ss_min:,.0f}", "red" if ss_min < 0 else "green"))
            html += row("Central 80% range (P10 – P90)",
                        f"€{ss_p10:,.0f} &nbsp;–&nbsp; €{ss_p90:,.0f}")
            if spread > 0:
                html += row("Year-to-year spread (max – min)",
                            badge(f"€{spread:,.0f}", "blue"))
            html += tbl_close

            if spread > 0:
                html += (f"{p}Depending on the weather year, your annual profit could range from "
                         f"{badge(f'€{ss_min:,.0f}', 'red' if ss_min < 0 else 'green')} to "
                         f"{badge(f'€{ss_max:,.0f}', 'green')}. "
                         f"In <b>8 out of 10</b> likely weather years the profit will fall between "
                         f"<b>€{ss_p10:,.0f}</b> and <b>€{ss_p90:,.0f}</b>.</p>")

            if true_vss is not None and eev is not None:
                vss_color = "green" if true_vss >= 0 else "orange"
                html += (f"<div style='margin:10px 0 4px 0; padding:5px 10px; "
                         f"background-color:#f9fbe7; border-left:4px solid #827717; "
                         f"font-size:12px; font-weight:bold; color:#33290a;'>"
                         f"Value of Stochastic Solution (VSS = SS − EEV)</div>")
                html += tbl_open
                if ev_mean is not None:
                    html += row("EV solution profit on mean year",
                                badge(f"€{ev_mean:,.0f}", "blue"),
                                "deterministic optimum for average weather")
                html += row("EEV — mean-year policy on all scenarios",
                            badge(f"€{eev:,.0f}", "orange" if eev < 0 else "blue"),
                            "fixed schedule applied to variable weather")
                html += row("SS — stochastic expected profit",
                            badge(f"€{ss_exp:,.0f}", "green" if ss_exp >= 0 else "red"),
                            "scenario-aware schedule")
                html += row("True VSS = SS − EEV",
                            badge(f"€{true_vss:+,.0f}/yr", vss_color),
                            "value of planning for uncertainty")
                html += tbl_close

                if true_vss > 50:
                    html += ok(
                        f"The stochastic policy outperforms the fixed mean-year policy by "
                        f"<b>€{true_vss:,.0f}/yr</b>. Planning for weather uncertainty — rather than "
                        f"optimising for a single average year — genuinely improves financial outcomes."
                    )
                elif true_vss >= -50:
                    html += ok(
                        "The stochastic and mean-year policies perform very similarly for this "
                        "configuration. The stochastic model confirms robustness: the optimal "
                        "dispatch is not sensitive to weather variability in this case."
                    )
                else:
                    html += warn(
                        f"Note: the mean-year policy slightly outperforms the stochastic policy "
                        f"in this run (VSS = €{true_vss:,.0f}). The stochastic solution remains "
                        f"the recommended policy as it is explicitly optimised for robustness."
                    )

        # ── 6. ENVIRONMENTAL IMPACT ───────────────────────────────────────────
        if base_ext_cost != 0 or co2_saved != 0:
            html += section("6 · ENVIRONMENTAL &amp; HEALTH IMPACT")
            html += tbl_open
            if co2_saved != 0:
                html += row("CO₂ emissions avoided",
                            badge(f"{co2_saved:,.2f} kg", "green"),
                            f"{co2_pct:.1f}% of total footprint saved; "
                            f"{co2_emitted_pct:.1f}% still from grid imports")
            if base_ext_cost != 0:
                html += row("External cost before optimization",
                            badge(f"€{base_ext_cost:,.2f}", "orange"),
                            "hidden health &amp; environmental damages")
                html += row("External cost after optimization",
                            badge(f"€{optimized_ext_cost:,.2f}", "green"))
                html += row("External cost saved",
                            badge(f"€{ext_cost_saved:,.2f}  ({ext_cost_saved_pct:.1f}%)", "green"),
                            "reduced pressure on healthcare &amp; environment")
            if heating_demand != 0 or cooling_demand != 0:
                html += row("Thermal CO₂ emissions",
                            badge("Zero", "green"),
                            "thermal system fully electrified")
            html += tbl_close

            if base_ext_cost != 0:
                html += (f"{p}External costs represent hidden economic damages from pollution — "
                         f"health care expenses, environmental degradation, and premature deaths. "
                         f"By reducing emissions, you save society approximately "
                         f"<b>€{ext_cost_saved:,.2f}</b> in such costs every year.</p>")

            html += (f"{p}By producing your own clean energy, you reduce pollution, protect local "
                     f"health, lower electricity costs, and contribute to a more resilient, "
                     f"affordable energy system for everyone.</p>")

        html += "</body></html>"
        return html
