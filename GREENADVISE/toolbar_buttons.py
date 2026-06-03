import os
from PyQt5.QtWidgets import (QApplication, QComboBox, QDialog, QFileDialog, QLabel, QLineEdit,
                             QPushButton, QVBoxLayout, QHBoxLayout, QFormLayout, QFrame,
                             QListWidget, QScrollArea, QWidget, QCheckBox, QGridLayout,
                             QStyleFactory, QGroupBox, QMessageBox, QListWidgetItem, QButtonGroup)
from PyQt5.QtCore import Qt, QPoint, QThread, pyqtSignal
from PyQt5.QtGui import QIcon, QIntValidator, QFont, QDoubleValidator

from Scrape_from_Ninja import NinjaScraper
from Upload_data import (DataUpload, CO2DataLoader, ExternalCostDataLoader)
from Electricity_simulator import ElectricityDemandSimulator
from Thermal_simulator import ThermalDemandSimulator
from Price_simulator import PriceGenerator
from Technology import Technology
from Technology_Simulator import TechnologySimulator
from config_loader import get_ninja_api_key, _config_path
from resources import resource_path
import os

class _FetchWorker(QThread):
    """Runs a blocking API fetch on a background thread."""
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


def lock_combobox(cb: QComboBox):
    cb.setEnabled(False)
    cb.setFocusPolicy(Qt.NoFocus)
    cb.setStyleSheet("""
        QComboBox {
            background-color: #f5f5f5;
            color: #444;
            padding: 4px 8px;
            border: 1px solid #aaa;
            border-radius: 3px;
        }
        QComboBox::drop-down { border: 0px; width: 0px; }
    """)
    return cb




def remove_qt_help_button(d: QDialog):
    d.setWindowFlags(d.windowFlags() & ~Qt.WindowContextHelpButtonHint)

class GenerationPopupHandler:

    last_pv_simulate_inputs = {
        "dataset": "MEERA-2 (global)",
        "year": "2023",
        "Pmax": "1",
        "tilt": "30",
        "azimuth": "180",
        "NOCT": "47",
        "γ": "-0.4",
        "capex": '1000', "opex": "200"
        }

    last_pv_fetch_inputs = {
        "dataset": "MEERA-2 (global)", "year": "2023",
        "capacity": "1", "loss": "0.1",
        "tracking": "None", "tilt": "30", "azimuth": "180",
        "capex": '1000', "opex": "200"
    }

    last_pv_upload_inputs = {
        "capex": "1000",
        "opex": "200"
        }

    last_wind_simulate_inputs = {
        "rated_power": "1",
        "dataset": "MEERA-2 (global)",
        "year": "2023",
        "rotor_radius":"15",
        "hub_height": "80",
        "cut_in_wind_speed": "2",
        "rated_wind_speed": "13",
        "cut_off_wind_speed": "25",
        "capex": '1000', "opex": "200"
        }

    last_wind_fetch_inputs = {
        "dataset": "MEERA-2 (global)",
        "year": "2023",
        "capacity": "1",
        "hub_height": "80",
        "turbine_model": "Vestas V90 2000",
        "capex": '1000', "opex": "200"
        }

    last_wind_upload_inputs = {
        "capex": "1000",
        "opex": "200"
        }

    last_heatpump_inputs = {
        "heating_capacity": "1",
        "cooling_capacity": "1",
        "cop": "3",
        "eer": "3",
        "capex": '1000', "opex": "200"
    }

    last_solar_collector_inputs = {
        "dataset": "MEERA-2 (global)",
        "year": "2023",
        "area": "1",
        "loss": "0.1",
        "tracking": "None",
        "tilt": "30",
        "azimuth": "180",
        "capex": '1000', "opex": "200"
        }

    combo_style = """
            QComboBox {
                background-color: white;
                color: black;
                font-weight: bold;
                font-size: 12px;
                border: 2px solid black;
            }
            QComboBox:hover {
                background-color: #f0f0f0;
            }
            QComboBox QAbstractItemView {
                background-color: white;
                selection-background-color: #f0f0f0;
                selection-color: black;
                font-size: 12px;
            }
        """

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

    check_style = ("""
    QCheckBox {
        background-color: white;
        color: black;
        font-weight: bold;
        font-size: 12px;
        border: 2px solid black;
        padding: 4px 12px;
    }
    QCheckBox::indicator {
        width: 0px;   /* hide the default square checkbox */
        height: 0px;
    }
    QCheckBox:hover {
        background-color: #f0f0f0;
    }
    QCheckBox:checked {
        background-color: #d0d0d0;  /* visually distinct when checked */
    }
""")

    def __init__(self, parent, toolbar, lat, lon, workspace_manager):
        self.parent = parent
        self.toolbar = toolbar
        self.lat = lat
        self.lon = lon
        self.workspace_manager = workspace_manager
        
        api_key = get_ninja_api_key()
        if not api_key:
            actual_path = _config_path()  # this returns a Path object
            QMessageBox.warning(
                self.parent,
                "Missing API key",
                f"Please set your Renewables.ninja API key in:\n\n{actual_path}\n\nunder 'ninja_api_key'."
            )
            return


        self.scraper = NinjaScraper(
            api_key=api_key,
            lat=lat,
            lon=lon,
            pv_inputs=self.last_pv_fetch_inputs,
            wind_inputs=self.last_wind_fetch_inputs,
            parent=self.parent
        )
        self.validate = Technology(self.parent)
        self.pv_fetch_data = None
        self.wind_fetch_data = None

        self.uploader = DataUpload(self.parent)
        self.pv_uploaded_data = None
        self.wind_uploaded_data = None

        self.simulator = TechnologySimulator(self.parent)

    _menu_style = """
        QFrame { background: #ffffff; border: 1px solid #d0d0d0; }
        QPushButton {
            background: transparent; color: #222;
            font-size: 12px; font-weight: bold;
            border: none; border-bottom: 1px solid #eeeeee;
            padding: 9px 14px; text-align: left;
        }
        QPushButton:hover { background: #f0f7f3; color: #1a7f3c; }
        QLabel {
            color: #999; font-size: 9px; font-weight: bold;
            letter-spacing: 1px;
            padding: 5px 14px 3px 14px;
            background: #fafafa;
            border-bottom: 1px solid #eeeeee;
        }
    """

    def show_popup(self, pos=None):
        self._popup_pos = pos
        popup = QFrame(self.parent)
        popup.setWindowFlags(Qt.Popup)
        popup.setFixedWidth(230)
        popup.setStyleSheet(GenerationPopupHandler._menu_style)
        layout = QVBoxLayout(popup)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(QLabel("ELECTRICITY GENERATION"))
        pv_btn   = QPushButton("PV")
        wind_btn = QPushButton("Wind Turbine")
        layout.addWidget(pv_btn)
        layout.addWidget(wind_btn)

        layout.addWidget(QLabel("THERMAL GENERATION"))
        hp_btn = QPushButton("Heat Pump")
        sc_btn = QPushButton("Solar Collector")
        layout.addWidget(hp_btn)
        layout.addWidget(sc_btn)

        popup.adjustSize()
        if pos:
            popup.move(pos)

        popup.show()

        pv_btn.clicked.connect(lambda: (popup.close(), self._show_pv_method_popup()))
        wind_btn.clicked.connect(lambda: (popup.close(), self._show_wind_method_popup()))
        hp_btn.clicked.connect(lambda: (popup.close(), self.show_heatpump_popup()))
        sc_btn.clicked.connect(lambda: (popup.close(), self._show_solar_collector_popup()))

    def _show_pv_method_popup(self):
        popup = QFrame(self.parent)
        popup.setWindowFlags(Qt.Popup)
        popup.setFixedWidth(230)
        popup.setStyleSheet(GenerationPopupHandler._menu_style)
        layout = QVBoxLayout(popup)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        from PyQt5.QtWidgets import QLabel as _L
        layout.addWidget(_L("PV  —  DATA SOURCE"))
        simulate_btn = QPushButton("Simulate")
        upload_btn   = QPushButton("Upload CSV")
        fetch_btn    = QPushButton("Fetch from Renewables.ninja")
        for b in [simulate_btn, upload_btn, fetch_btn]:
            layout.addWidget(b)

        simulate_btn.clicked.connect(lambda: (popup.close(), self._show_pv_simulate_popup()))
        upload_btn.clicked.connect(lambda: (popup.close(), self._show_pv_upload_popup()))
        fetch_btn.clicked.connect(lambda: (popup.close(), self._show_pv_fetch_popup()))

        popup.adjustSize()
        if self._popup_pos:
            popup.move(self._popup_pos)
        popup.show()

    def _show_wind_method_popup(self):
        popup = QFrame(self.parent)
        popup.setWindowFlags(Qt.Popup)
        popup.setFixedWidth(230)
        popup.setStyleSheet(GenerationPopupHandler._menu_style)
        layout = QVBoxLayout(popup)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        from PyQt5.QtWidgets import QLabel as _L
        layout.addWidget(_L("WIND TURBINE  —  DATA SOURCE"))
        simulate_btn = QPushButton("Simulate")
        upload_btn   = QPushButton("Upload CSV")
        fetch_btn    = QPushButton("Fetch from Renewables.ninja")
        for b in [simulate_btn, upload_btn, fetch_btn]:
            layout.addWidget(b)

        simulate_btn.clicked.connect(lambda: (popup.close(), self._show_wind_simulate_popup()))
        upload_btn.clicked.connect(lambda: (popup.close(), self._show_wind_upload_popup()))
        fetch_btn.clicked.connect(lambda: (popup.close(), self._show_wind_fetch_popup()))

        popup.adjustSize()
        if self._popup_pos:
            popup.move(self._popup_pos)
        popup.show()

    def _show_pv_simulate_popup(self):
        dialog = QDialog(self.parent)
        remove_qt_help_button(dialog)
        dialog.setWindowTitle("Simulate PV Input")
        dialog.setFixedSize(400, 440)
        dialog.setModal(True)

        main_layout = QVBoxLayout(dialog)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.addStretch()
        help_btn = QPushButton("?")
        help_btn.setFixedSize(35, 35)
        help_btn.setStyleSheet(GenerationPopupHandler.style)
        help_btn.clicked.connect(lambda: self.show_pv_simulate_help(dialog))
        top_row.addWidget(help_btn)
        main_layout.addLayout(top_row)

        input_frame = QFrame()
        input_frame.setStyleSheet("""
        QFrame {border: 2px solid black; background-color: white;}
        QLabel {border: none; font-size: 12px; font-weight: bold;}
        
        QLineEdit {min-height: 28px;}
        QComboBox {min-height: 28px; padding-left: 6px;}
        """)

        input_layout = QVBoxLayout(input_frame)
        input_layout.setContentsMargins(12, 12, 12, 12)

        form_layout = QFormLayout()

        dataset = lock_combobox(QComboBox())
        dataset.addItem(self.last_pv_fetch_inputs["dataset"])
        
        year = lock_combobox(QComboBox())
        year.addItem(self.last_pv_fetch_inputs["year"])

        Pmax = QLineEdit(self.last_pv_simulate_inputs["Pmax"])
        tilt = QLineEdit(self.last_pv_simulate_inputs["tilt"])
        azimuth = QLineEdit(self.last_pv_simulate_inputs["azimuth"])
        NOCT = QLineEdit(self.last_pv_simulate_inputs["NOCT"])
        gama = QLineEdit(self.last_pv_simulate_inputs["γ"])

        form_layout.addRow("Dataset", dataset)
        form_layout.addRow("Year", year)
        form_layout.addRow("Pmax (kW)", Pmax)
        form_layout.addRow("Tilt (°)", tilt)
        form_layout.addRow("Azimuth (°)", azimuth)
        form_layout.addRow("NOCT °C", NOCT)
        form_layout.addRow("γ %/°C", gama)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        form_layout.addRow(line)

        capex = QLineEdit(self.last_pv_simulate_inputs["capex"])
        opex = QLineEdit(self.last_pv_simulate_inputs["opex"])

        form_layout.addRow("CapEX (€)", capex)
        form_layout.addRow("OpEX (€/year)", opex)

        input_layout.addLayout(form_layout)
        main_layout.addWidget(input_frame)

        save_btn = QPushButton("Save")
        save_btn.setStyleSheet(GenerationPopupHandler.style)
        save_btn.setFixedWidth(80)
        save_btn.clicked.connect(lambda: self._save_pv_simulate_inputs(
                            dialog, dataset, year,
                            Pmax, tilt, azimuth,
                            NOCT, gama, capex, opex))
        main_layout.addWidget(save_btn, alignment=Qt.AlignRight)
        dialog.exec()

    def _save_pv_simulate_inputs(self, dialog, dataset, year, Pmax, tilt, azimuth, NOCT, gama, capex, opex):
        self.last_pv_simulate_inputs.update({
            "dataset": dataset.currentText(),
            "year": year.currentText(),
            "Pmax": Pmax.text(),
            "tilt": tilt.text(),
            "azimuth": azimuth.text(),
            "NOCT": NOCT.text(),
            "γ": gama.text(),
            "capex": capex.text(),
            "opex": opex.text()
        })

        fetch_inputs = {
            "dataset": dataset.currentText(),
            "year": year.currentText(),
            "capacity": "1",
            "loss": "0.1",
            "tracking": "None",
            "tilt": tilt.text(),
            "azimuth": azimuth.text(),
        }

        last_pv_simulate_inputs = self.last_pv_simulate_inputs.copy()
        last_pv_simulate_inputs.update({
            "latitude": str(self.lat),
            "longitude": str(self.lon),
            "capex": capex.text(),
            "opex": opex.text()
        })

        self.scraper.pv_inputs.update(fetch_inputs)
        dialog.setEnabled(False)
        QApplication.setOverrideCursor(Qt.WaitCursor)

        saved_parent = self.scraper.parent
        self.scraper.parent = None

        def do_fetch():
            return self.scraper.fetch_radiance()

        def on_done(data, err):
            self.scraper.parent = saved_parent
            QApplication.restoreOverrideCursor()
            dialog.setEnabled(True)
            if data is None:
                QMessageBox.critical(dialog, "Fetch Error",
                    "Failed to fetch solar irradiance data from Renewables.ninja.\n"
                    "Check your API key and internet connection.")
                return
            self.solar_radiance_data = data
            self.simualte_pv_data = self.simulator.pv_simulator(last_pv_simulate_inputs, data)
            self.workspace_manager.update("Input", "PV Simulate Inputs", last_pv_simulate_inputs)
            self.workspace_manager.update("Data", "PV Simulate Data", self.simualte_pv_data)
            self.workspace_manager.show_success("PV Simulate inputs and data saved successfully!")
            dialog.accept()

        self._worker = _FetchWorker(do_fetch)
        self._worker.done.connect(on_done)
        self._worker.start()

    def show_pv_simulate_help(self, parent):
        dlg = QDialog(parent)
        remove_qt_help_button(dlg)
        dlg.setWindowTitle("Simulate PV - Input Help")
        dlg.setFixedSize(350, 300)

        layout = QVBoxLayout(dlg)
        text = QLabel("""
            <b>Simulate PV - Input Help</b><br><br>
            <b>Dataset:</b> Source of solar irradiance data.<br>
            <b>Year:</b> Simulation year matching dataset.<br>
            <b>Pmax</b> Output rated power by standard test conditions (read tehnical data sheet).<br>
            <b>Tilt / Azimuth:</b> Orientation angles of the PV system.<br>
            <b>NOCT:</b> Temperature reached by open circuited cells in a module (read tehnical data sheet).<br>
            <b>γ:</b> Power reduction factor depending on temperature (read tehnical data sheet)<br>
            <b>CapEx / OpEx:</b> Purchase of long-term assets / ongoing, day-to-day operational costs<br>
        """)
        text.setWordWrap(True)
        layout.addWidget(text)

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(GenerationPopupHandler.style)
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)

        dlg.exec()

    def _show_wind_simulate_popup(self):
        dialog = QDialog(self.parent)
        remove_qt_help_button(dialog)
        dialog.setWindowTitle("Simulate Wind Input")
        dialog.setFixedSize(400, 470)
        dialog.setModal(True)

        main_layout = QVBoxLayout(dialog)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.addStretch()
        help_btn = QPushButton("?")
        help_btn.setStyleSheet(GenerationPopupHandler.style)
        help_btn.setFixedSize(35, 35)
        help_btn.clicked.connect(lambda: self.show_wind_simulate_help(dialog))
        top_row.addWidget(help_btn)
        main_layout.addLayout(top_row)

        input_frame = QFrame()
        input_frame.setStyleSheet("""
        QFrame {border: 2px solid black; background-color: white;}
        QLabel {border: none; font-size: 12px; font-weight: bold;}
        
        QLineEdit {min-height: 28px;}
        QComboBox {min-height: 28px; padding-left: 6px;}
        """)

        input_layout = QVBoxLayout(input_frame)
        input_layout.setContentsMargins(12, 12, 12, 12)

        form_layout = QFormLayout()

        dataset = lock_combobox(QComboBox())
        dataset.addItem("MEERA-2 (global)")
        
        year = lock_combobox(QComboBox())
        year.addItem("2023")

        rotor_radius = QLineEdit(self.last_wind_simulate_inputs["rotor_radius"])

        hub_height = QLineEdit(self.last_wind_simulate_inputs["hub_height"])
        hub_height.setValidator(QIntValidator(10, 150))
        hub_height.setToolTip("Enter a hub height between 10 and 150 meters.")

        rated_power = QLineEdit(self.last_wind_simulate_inputs["rated_power"])
        cut_in_wind_speed = QLineEdit(self.last_wind_simulate_inputs["cut_in_wind_speed"])
        rated_wind_speed = QLineEdit(self.last_wind_simulate_inputs["rated_wind_speed"])
        cut_off_wind_speed = QLineEdit(self.last_wind_simulate_inputs["cut_off_wind_speed"])

        form_layout.addRow("Dataset", dataset)
        form_layout.addRow("Year", year)
        form_layout.addRow("Rated power (kW)", rated_power)
        form_layout.addRow("Rotor radius (m)", rotor_radius)
        form_layout.addRow("Hub height (m)", hub_height)
        form_layout.addRow("Cut-in speed (m/s)", cut_in_wind_speed)
        form_layout.addRow("Rated wind speed (m/s)", rated_wind_speed)
        form_layout.addRow("Cut-off wind speed (m/s)", cut_off_wind_speed)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        form_layout.addRow(line)

        capex = QLineEdit(self.last_wind_simulate_inputs.get("capex", ""))
        opex = QLineEdit(self.last_wind_simulate_inputs.get("opex", ""))
        form_layout.addRow("CapEX (€)", capex)
        form_layout.addRow("OpEX (€/year)", opex)

        input_layout.addLayout(form_layout)
        main_layout.addWidget(input_frame)

        save_btn = QPushButton("Save")
        save_btn.setStyleSheet(GenerationPopupHandler.style)
        save_btn.setFixedWidth(80)
        save_btn.clicked.connect(lambda: self._save_wind_simulate_inputs(
                            dialog, dataset, year,
                            rated_power, rotor_radius, hub_height,
                            cut_in_wind_speed,rated_wind_speed,cut_off_wind_speed,
                            capex, opex))
        main_layout.addWidget(save_btn, alignment=Qt.AlignRight)
        dialog.exec()

    def _save_wind_simulate_inputs(self, dialog, dataset, year, rated_power, rotor_radius, hub_height, cut_in_wind_speed,rated_wind_speed,cut_off_wind_speed, capex, opex):
        if not hub_height.hasAcceptableInput():
            QMessageBox.warning(
                dialog,
                "Invalid hub height",
                "Hub height must be between 10 and 150 meters."
            )
            return
        
        self.last_wind_simulate_inputs.update({
            "rated_power": rated_power.text(),
            "dataset": dataset.currentText(),
            "year": year.currentText(),
            "rotor_radius":rotor_radius.text(),
            "hub_height": hub_height.text(),
            "cut_in_wind_speed": cut_in_wind_speed.text() ,
            "rated_wind_speed": rated_wind_speed.text() ,
            "cut_off_wind_speed": cut_off_wind_speed.text() ,
            "capex": capex.text(), "opex": opex.text()
            })

        fetch_inputs = {
            "dataset": dataset.currentText(),
            "year": year.currentText(),
            "capacity": "1",
            "hub_height": hub_height.text(),
            "turbine_model": "Vestas V90 2000",
            }

        last_wind_simulate_inputs = self.last_wind_simulate_inputs.copy()
        last_wind_simulate_inputs.update({
            "latitude": str(self.lat),
            "longitude": str(self.lon),
            "capex": capex.text(),
            "opex": opex.text()
        })

        self.scraper.wind_inputs.update(fetch_inputs)
        dialog.setEnabled(False)
        QApplication.setOverrideCursor(Qt.WaitCursor)

        saved_parent = self.scraper.parent
        self.scraper.parent = None

        def do_fetch():
            return self.scraper.fetch_speed()

        def on_done(data, err):
            self.scraper.parent = saved_parent
            QApplication.restoreOverrideCursor()
            dialog.setEnabled(True)
            if data is None:
                QMessageBox.critical(dialog, "Fetch Error",
                    "Failed to fetch wind speed data from Renewables.ninja.\n"
                    "Check your API key and internet connection.")
                return
            self.wind_speed_data = data
            self.simulate_wind_data = self.simulator.wind_simulator(last_wind_simulate_inputs, data)
            self.workspace_manager.update("Input", "Wind Simulate Inputs", last_wind_simulate_inputs)
            self.workspace_manager.update("Data", "Wind Simulate Data", self.simulate_wind_data)
            self.workspace_manager.show_success("Wind Simulate inputs and data saved successfully!")
            dialog.accept()

        self._worker = _FetchWorker(do_fetch)
        self._worker.done.connect(on_done)
        self._worker.start()

    def show_wind_simulate_help(self, parent):
        dlg = QDialog(parent)
        remove_qt_help_button(dlg)
        dlg.setWindowTitle("Simulate Wind - Input Help")
        dlg.setFixedSize(350, 300)

        layout = QVBoxLayout(dlg)
        text = QLabel("""
            <b>Simualte Wind - Input Help</b><br><br>
            <b>Dataset:</b> Select the meteorological dataset used for wind speeds.<br>
            <b>Year:</b> Choose the year corresponding to available weather data.<br>
            <b>Rated power:</b> Standard wind turbine output power.<br>
            <b>Rotor radius:</b> Radius of the rotor blades.<br>
            <b>Hub height:</b> Height above ground at which the rotor is mounted. Enter values between 10-150 meters.<br>
            <b>Cut-in wind speed:</b> Speed on which wind turbines turn on.<br>
            <b>Rated wind speed:</b> Speed on which wind turbines give rated power.<br>
            <b>Cut-off wind speed:</b> Speed on which wind turbines turn off.<br>
            <b>CapEx / OpEx:</b> Purchase of long-term assets / ongoing, day-to-day operational costs<br>
        """)
        text.setWordWrap(True)
        layout.addWidget(text)

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(GenerationPopupHandler.style)
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)

        dlg.exec()


    def _show_pv_upload_popup(self):
        dialog = QDialog(self.parent)
        remove_qt_help_button(dialog)
        dialog.setWindowTitle("Upload PV Generation - CSV")
        dialog.setFixedSize(360, 360)
        dialog.setModal(True)

        main_layout = QVBoxLayout(dialog)

        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                border: 2px solid black;
                background-color: white;
            }
            QLabel {
                font-size: 12px;
                font-weight: bold;
                border: none;
            }
        """)
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(12, 12, 12, 12)
        frame_layout.setSpacing(10)

        label = QLabel("""
            <b>CSV Format:</b><br>
            - 8760 rows representing hourly PV output.<br>
            - <u>Deterministic:</u> Single column named <i>pv_generation</i> in kWh (decimal “123.45” or “123,45”).<br>
            - <u>Stochastic:</u> 5 columns placed side-by-side named <i>pv_generation1</i>, <i>pv_generation2</i>, <i>pv_generation3</i>, <i>pv_generation4</i>, <i>pv_generation5</i> (each 8760 values).<br>
        """)
        label.setWordWrap(True)
        frame_layout.addWidget(label)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        frame_layout.addWidget(line)

        mode_layout = QHBoxLayout()
        deterministic_cb = QCheckBox("Deterministic")
        stochastic_cb = QCheckBox("Stochastic")
        deterministic_cb.setChecked(True if self.last_pv_upload_inputs.get("mode", "deterministic") == "deterministic" else False)
        stochastic_cb.setChecked(True if self.last_pv_upload_inputs.get("mode", "deterministic") == "stochastic" else False)

        deterministic_cb.setStyleSheet(self.check_style)
        stochastic_cb.setStyleSheet(self.check_style)

        mode_group = QButtonGroup(dialog)
        mode_group.setExclusive(True)
        mode_group.addButton(deterministic_cb)
        mode_group.addButton(stochastic_cb)

        mode_layout.addWidget(deterministic_cb)
        mode_layout.addWidget(stochastic_cb)
        frame_layout.addLayout(mode_layout)

        form_layout = QFormLayout()
        capex = QLineEdit(self.last_pv_upload_inputs.get("capex", ""))
        opex = QLineEdit(self.last_pv_upload_inputs.get("opex", ""))
        form_layout.addRow("CapEX (€)", capex)
        form_layout.addRow("OpEX (€/year)", opex)
        frame_layout.addLayout(form_layout)

        main_layout.addWidget(frame)

        upload_btn = QPushButton("Select CSV File")
        upload_btn.setStyleSheet(GenerationPopupHandler.style)
        main_layout.addWidget(upload_btn, alignment=Qt.AlignRight)

        def pv_file_upload():
            selected_mode = "stochastic" if stochastic_cb.isChecked() else "deterministic"

            file_path, _ = QFileDialog.getOpenFileName(dialog, "Select PV CSV File", "", "CSV Files (*.csv)")
            if file_path:
                if selected_mode == "deterministic":
                    self.pv_uploaded_data = self.uploader.upload_pv_data(file_path)
                else:  
                    self.pv_uploaded_data = self.uploader.upload_pv_data_stochastic(file_path)

                self.last_pv_upload_inputs.update({
                    "capex": capex.text(),
                    "opex": opex.text(),
                    "mode": selected_mode
                })

                if selected_mode == "deterministic":
                    self.workspace_manager.update("Data", "PV Uploaded Data", self.pv_uploaded_data)
                    self.workspace_manager.update("Input", "PV Upload Inputs", self.last_pv_upload_inputs, coordinates=False)
                else:
                    self.workspace_manager.update("Data", "PV Uploaded Data (stochastic)", self.pv_uploaded_data)
                    self.workspace_manager.update("Input", "PV Upload Inputs (stochastic)", self.last_pv_upload_inputs, coordinates=False)

                self.workspace_manager.show_success("Uploaded PV data and economic inputs saved successfully!")
                dialog.accept()

        upload_btn.clicked.connect(pv_file_upload)

        dialog.exec()


    def _show_wind_upload_popup(self):
        dialog = QDialog(self.parent)
        remove_qt_help_button(dialog)
        dialog.setWindowTitle("Upload Wind Generation - CSV")
        dialog.setFixedSize(360, 360)
        dialog.setModal(True)

        main_layout = QVBoxLayout(dialog)

        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                border: 2px solid black;
                background-color: white;
            }
            QLabel {
                font-size: 12px;
                font-weight: bold;
                border: none;
            }
        """)
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(12, 12, 12, 12)
        frame_layout.setSpacing(10)

        label = QLabel("""
            <b>CSV Format:</b><br>
            - 8760 rows representing hourly wind turbine output.<br>
            - <u>Deterministic:</u> Single column named <i>wind_generation</i> in kWh (decimal “123.45” or “123,45”).<br>
            - <u>Stochastic:</u> 5 columns side-by-side named <i>wind_generation1</i>, <i>wind_generation2</i>, <i>wind_generation3</i>, <i>wind_generation4</i>, <i>wind_generation5</i>.<br>
        """)
        label.setWordWrap(True)
        frame_layout.addWidget(label)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        frame_layout.addWidget(line)

        mode_layout = QHBoxLayout()
        deterministic_cb = QCheckBox("Deterministic")
        stochastic_cb = QCheckBox("Stochastic")
    
        deterministic_cb.setChecked(self.last_wind_upload_inputs.get("mode", "deterministic") == "deterministic")
        stochastic_cb.setChecked(self.last_wind_upload_inputs.get("mode", "deterministic") == "stochastic")
    
        deterministic_cb.setStyleSheet(self.check_style)
        stochastic_cb.setStyleSheet(self.check_style)

        mode_group = QButtonGroup(dialog)
        mode_group.setExclusive(True)
        mode_group.addButton(deterministic_cb)
        mode_group.addButton(stochastic_cb)

        mode_layout.addWidget(deterministic_cb)
        mode_layout.addWidget(stochastic_cb)
        frame_layout.addLayout(mode_layout)

        form_layout = QFormLayout()
        capex = QLineEdit(self.last_wind_upload_inputs.get("capex", ""))
        opex = QLineEdit(self.last_wind_upload_inputs.get("opex", ""))
        form_layout.addRow("CapEX (€)", capex)
        form_layout.addRow("OpEX (€/year)", opex)
        frame_layout.addLayout(form_layout)

        main_layout.addWidget(frame)

        upload_btn = QPushButton("Select CSV File")
        upload_btn.setStyleSheet(GenerationPopupHandler.style)
        main_layout.addWidget(upload_btn, alignment=Qt.AlignRight)

        def wind_file_upload():
            selected_mode = "stochastic" if stochastic_cb.isChecked() else "deterministic"

            file_path, _ = QFileDialog.getOpenFileName(dialog, "Select Wind CSV File", "", "CSV Files (*.csv)")
            if file_path:
                if selected_mode == "deterministic":
                    self.wind_uploaded_data = self.uploader.upload_wind_data(file_path)
                else:
                    self.wind_uploaded_data = self.uploader.upload_wind_data_stochastic(file_path)

                self.last_wind_upload_inputs.update({
                    "capex": capex.text(),
                    "opex": opex.text(),
                    "mode": selected_mode
                })

                if selected_mode == "deterministic":
                    self.workspace_manager.update("Data", "Wind Upload Data", self.wind_uploaded_data)
                    self.workspace_manager.update("Input", "Wind Upload Inputs", self.last_wind_upload_inputs, coordinates=False)
                else:
                    self.workspace_manager.update("Data", "Wind Upload Data (stochastic)", self.wind_uploaded_data)
                    self.workspace_manager.update("Input", "Wind Upload Inputs (stochastic)", self.last_wind_upload_inputs, coordinates=False)
                
                self.workspace_manager.show_success("Uploaded Wind data and economic inputs saved successfully!")
                dialog.accept()

        upload_btn.clicked.connect(wind_file_upload)
        dialog.exec()


    def _show_pv_fetch_popup(self):
            dialog = QDialog(self.parent)
            remove_qt_help_button(dialog)
            dialog.setWindowTitle("Fetch PV Input")
            dialog.setFixedSize(400, 420)
            dialog.setModal(True)
    
            main_layout = QVBoxLayout(dialog)
    
            # Help button row
            top_row = QHBoxLayout()
            top_row.setContentsMargins(0, 0, 0, 0)
            top_row.addStretch()
            help_btn = QPushButton("?")
            help_btn.setFixedSize(35, 35)
            help_btn.setStyleSheet(GenerationPopupHandler.style)
            help_btn.clicked.connect(lambda: self.show_pv_fetch_help(dialog))
            top_row.addWidget(help_btn)
            main_layout.addLayout(top_row)
    
            # Form layout
            input_frame = QFrame()
            input_frame.setStyleSheet("""
            QFrame {border: 2px solid black; background-color: white;}
            QLabel {border: none; font-size: 12px; font-weight: bold;}
            
            QLineEdit {
                min-height: 28px;
            }
            
            QComboBox {
                min-height: 28px;
                padding-left: 6px;
            }
            """)


            input_layout = QVBoxLayout(input_frame)
            input_layout.setContentsMargins(12, 12, 12, 12)
    
            form_layout = QFormLayout()
    
            # PV System Inputs
            dataset = lock_combobox(QComboBox())
            dataset.addItem(self.last_pv_fetch_inputs["dataset"])
            
            year = lock_combobox(QComboBox())
            year.addItem(self.last_pv_fetch_inputs["year"])
            capacity = QLineEdit(self.last_pv_fetch_inputs["capacity"])
            loss = QLineEdit(self.last_pv_fetch_inputs["loss"])
            tracking = QComboBox()
            tracking.addItems(["None", "Single-axis", "Dual-axis"])
            tracking.setCurrentText(self.last_pv_fetch_inputs["tracking"])
            tilt = QLineEdit(self.last_pv_fetch_inputs["tilt"])
            azimuth = QLineEdit(self.last_pv_fetch_inputs["azimuth"])
    
            form_layout.addRow("Dataset", dataset)
            form_layout.addRow("Year", year)
            form_layout.addRow("Capacity (kW)", capacity)
            form_layout.addRow("System loss (fraction)", loss)
            form_layout.addRow("Tracking", tracking)
            form_layout.addRow("Tilt (°)", tilt)
            form_layout.addRow("Azimuth (°)", azimuth)
    
            # Separator Line
            line = QFrame()
            line.setFrameShape(QFrame.HLine)
            line.setFrameShadow(QFrame.Sunken)
            form_layout.addRow(line)
    
            capex = QLineEdit(self.last_pv_fetch_inputs["capex"])
            opex = QLineEdit(self.last_pv_fetch_inputs["opex"])
    
            form_layout.addRow("CapEX (€)", capex)
            form_layout.addRow("OpEX (€/year)", opex)
    
            input_layout.addLayout(form_layout)
            main_layout.addWidget(input_frame)
    
            last_pv_fetch_inputs = self.last_pv_fetch_inputs.copy()
    
            # Save Button
            save_btn = QPushButton("Save")
            save_btn.setStyleSheet(GenerationPopupHandler.style)
            save_btn.setFixedWidth(80)
            save_btn.clicked.connect(lambda: (
                self.last_pv_fetch_inputs.update({
                    "dataset": dataset.currentText(),
                    "year": year.currentText(),
                    "capacity": capacity.text(),
                    "loss": loss.text(),
                    "tracking": tracking.currentText(),
                    "tilt": tilt.text(),
                    "azimuth": azimuth.text(),
                    "capex": capex.text(),
                    "opex": opex.text()
                }),
                last_pv_fetch_inputs.update(self.last_pv_fetch_inputs),
                last_pv_fetch_inputs.update({
                    "latitude": str(self.lat),
                    "longitude": str(self.lon),
                    "capex": capex.text(),
                    "opex": opex.text()
                }),
                self.scraper.pv_inputs.update(self.last_pv_fetch_inputs),
                setattr(self, 'pv_fetch_data', self.scraper.fetch_pv()),
                self.workspace_manager.update("Input", "PV Fetch Inputs", last_pv_fetch_inputs),
                self.workspace_manager.update("Data", "PV Fetch Data", self.pv_fetch_data),
                self.workspace_manager.show_success("PV fetch inputs and data saved successfully!"),
                dialog.accept()
            ))
            main_layout.addWidget(save_btn, alignment=Qt.AlignRight)
            dialog.exec()
        

    def show_pv_fetch_help(self, parent):
        dlg = QDialog(parent)
        remove_qt_help_button(dlg)
        dlg.setWindowTitle("Fetch PV - Input Help")
        dlg.setFixedSize(350, 260)

        layout = QVBoxLayout(dlg)
        text = QLabel("""
            <b>Fetch PV - Input Help</b><br><br>
            <b>Dataset:</b> Source of solar irradiance data.<br>
            <b>Year:</b> Simulation year matching dataset.<br>
            <b>Capacity:</b> Installed PV capacity in kW.<br>
            <b>System loss:</b> Fractional loss in the system (e.g. due to wiring, inverter).<br>
            <b>Tracking:</b> Type of PV panel tracking (None, Single, Dual-axis).<br>
            <b>Tilt / Azimuth:</b> Orientation angles of the PV system.<br>
            <b>CapEx / OpEx:</b> Purchase of long-term assets / ongoing, day-to-day operational costs<br>
        """)
        text.setWordWrap(True)
        layout.addWidget(text)

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(GenerationPopupHandler.style)
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)

        dlg.exec()

    def _show_wind_fetch_popup(self):
        dialog = QDialog(self.parent)
        remove_qt_help_button(dialog)
        dialog.setWindowTitle("Fetch Wind Input")
        dialog.setFixedSize(400, 390)
        dialog.setModal(True)

        main_layout = QVBoxLayout(dialog)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.addStretch()
        help_btn = QPushButton("?")
        help_btn.setStyleSheet(GenerationPopupHandler.style)
        help_btn.setFixedSize(35, 35)
        help_btn.clicked.connect(lambda: self.show_wind_fetch_help(dialog))
        top_row.addWidget(help_btn)
        main_layout.addLayout(top_row)

        input_frame = QFrame()
        input_frame.setStyleSheet("""
        QFrame {border: 2px solid black; background-color: white;}
        QLabel {border: none; font-size: 12px; font-weight: bold;}
        
        QLineEdit {min-height: 28px;}
        QComboBox {min-height: 28px; padding-left: 6px;}
        """)

        input_layout = QVBoxLayout(input_frame)
        input_layout.setContentsMargins(12, 12, 12, 12)

        form_layout = QFormLayout()

        dataset = lock_combobox(QComboBox())
        dataset.addItem("MEERA-2 (global)")
        
        year = lock_combobox(QComboBox())
        year.addItem("2023")

        capacity = QLineEdit(self.last_wind_fetch_inputs["capacity"])
        hub_height = QLineEdit(self.last_wind_fetch_inputs["hub_height"])
        hub_height.setValidator(QIntValidator(10, 150))
        hub_height.setToolTip("Enter a hub height between 10 and 150 meters.")


        form_layout.addRow("Dataset", dataset)
        form_layout.addRow("Year", year)
        form_layout.addRow("Capacity (kW)", capacity)
        form_layout.addRow("Hub height (m)", hub_height)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        form_layout.addRow(line)

        capex = QLineEdit(self.last_wind_fetch_inputs.get("capex", ""))
        opex = QLineEdit(self.last_wind_fetch_inputs.get("opex", ""))
        form_layout.addRow("CapEX (€)", capex)
        form_layout.addRow("OpEX (€/year)", opex)

        input_layout.addLayout(form_layout)
        main_layout.addWidget(input_frame)

        last_wind_fetch_inputs = self.last_wind_fetch_inputs.copy()

        save_btn = QPushButton("Save")
        save_btn.setStyleSheet(GenerationPopupHandler.style)
        save_btn.setFixedWidth(80)
        save_btn.clicked.connect(lambda: (
            self.last_wind_fetch_inputs.update({
                "dataset": dataset.currentText(),
                "year": year.currentText(),
                "capacity": capacity.text(),
                "hub_height": hub_height.text(),
                "turbine_model": self.last_wind_fetch_inputs.get("turbine_model", "Vestas V90 2000"),

                "capex": capex.text(),
                "opex": opex.text()
            }),
            last_wind_fetch_inputs.update(self.last_wind_fetch_inputs),
            last_wind_fetch_inputs.update({
                "latitude": str(self.lat),
                "longitude": str(self.lon)
            }),
            self.scraper.wind_inputs.update(last_wind_fetch_inputs),
            setattr(self, 'wind_fetch_data', self.scraper.fetch_wind()),
            self.workspace_manager.update("Input", "Wind Fetch Inputs", self.last_wind_fetch_inputs),
            self.workspace_manager.update("Data", "Wind Fetch Data", self.wind_fetch_data),
            self.workspace_manager.show_success("Wind inputs and data saved successfully!"),
            dialog.accept()
        ))
        main_layout.addWidget(save_btn, alignment=Qt.AlignRight)
        dialog.exec()

    def show_wind_fetch_help(self, parent):
        dlg = QDialog(parent)
        remove_qt_help_button(dlg)
        dlg.setWindowTitle("Fetch Wind - Input Help")
        dlg.setFixedSize(350, 300)

        layout = QVBoxLayout(dlg)
        text = QLabel("""
            <b>Fetch Wind - Input Help</b><br><br>
            <b>Dataset:</b> Select the meteorological dataset used for wind speeds.<br>
            <b>Year:</b> Choose the year corresponding to available weather data.<br>
            <b>Capacity:</b> Rated power output of the wind turbine.<br>
            <b>Hub height:</b> Height above ground at which the rotor is mounted. Enter values between 10-150 meters.<br>
            <b>Turbine model:</b> Select a predefined wind turbine model for simulation.<br>
            <b>CapEx / OpEx:</b> Purchase of long-term assets / ongoing, day-to-day operational costs<br>
        """)
        text.setWordWrap(True)
        layout.addWidget(text)

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(GenerationPopupHandler.style)
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)

        dlg.exec()


    def show_heatpump_popup(self):
        dialog = QDialog(self.parent)
        remove_qt_help_button(dialog)
        dialog.setWindowTitle("Heat Pump Input")
        dialog.setFixedSize(400, 330)
        dialog.setModal(True)

        main_layout = QVBoxLayout(dialog)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.addStretch()
        help_btn = QPushButton("?")
        help_btn.setStyleSheet(GenerationPopupHandler.style)
        help_btn.setFixedSize(35, 35)
        help_btn.clicked.connect(lambda: self.show_heatpump_help(dialog))
        top_row.addWidget(help_btn)
        main_layout.addLayout(top_row)

        input_frame = QFrame()
        input_frame.setStyleSheet("""QFrame {border: 2px solid black;background-color: white;} QLabel {border: none; font-size: 12px; font-weight: bold;}""")
        input_layout = QVBoxLayout(input_frame)
        input_layout.setContentsMargins(12, 12, 12, 12)

        form_layout = QFormLayout()

        heating_capacity = QLineEdit(self.last_heatpump_inputs["heating_capacity"])
        cooling_capacity = QLineEdit(self.last_heatpump_inputs["cooling_capacity"])
        cop = QLineEdit(self.last_heatpump_inputs["cop"])
        eer = QLineEdit(self.last_heatpump_inputs["eer"])

        form_layout.addRow("Heating Capacity (kW)", heating_capacity)
        form_layout.addRow("Cooling Capacity (kW)", cooling_capacity)
        form_layout.addRow("COP", cop)
        form_layout.addRow("EER", eer)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        form_layout.addRow(line)

        capex = QLineEdit(self.last_heatpump_inputs.get("capex", ""))
        opex = QLineEdit(self.last_heatpump_inputs.get("opex", ""))
        form_layout.addRow("CapEX (€)", capex)
        form_layout.addRow("OpEX (€/year)", opex)

        input_layout.addLayout(form_layout)
        main_layout.addWidget(input_frame)

        save_btn = QPushButton("Save")
        save_btn.setStyleSheet(GenerationPopupHandler.style)
        save_btn.setFixedWidth(80)
        save_btn.clicked.connect(lambda: self._save_heatpump_data(
            heating_capacity, cooling_capacity, cop, eer, capex, opex, dialog
        ))
        main_layout.addWidget(save_btn, alignment=Qt.AlignRight)

        dialog.exec()

    def _save_heatpump_data(self, heating_capacity, cooling_capacity, cop, eer, capex, opex, dialog):
        fields = {
            "Heating Capacity (kW)": heating_capacity.text(),
            "Cooling Capacity (kW)": cooling_capacity.text(),
            "COP": cop.text(),
            "EER": eer.text(),
            "capex": capex.text(),
            "opex": opex.text()
        }

        self.validate.validate_heat_pump(fields)

        self.last_heatpump_inputs.update({
            "heating_capacity": heating_capacity.text(),
            "cooling_capacity": cooling_capacity.text(),
            "cop": cop.text(),
            "eer": eer.text(),
            "capex": capex.text(),
            "opex": opex.text()
        })

        self.workspace_manager.update("Input", "Heat Pump Inputs", self.last_heatpump_inputs, coordinates= False)
        self.workspace_manager.show_success("Heat pump inputs saved successfully!")
        dialog.accept()

    def show_heatpump_help(self, parent):
        dlg = QDialog(parent)
        remove_qt_help_button(dlg)
        dlg.setWindowTitle("Heat Pump Input - Help")
        dlg.setFixedSize(350, 260)

        layout = QVBoxLayout(dlg)
        text = QLabel("""
            <b>Heat Pump - Input Help</b><br><br>
            <b>Heating capacity:</b> Maximum output when heating.<br>
            <b>Cooling capacity:</b> Maximum output when cooling.<br>
            <b>COP:</b> Efficiency during heating (Coefficient of Performance).<br>
            <b>EER:</b> Efficiency during cooling (Energy Efficiency Ratio).<br>
            <b>CapEx / OpEx:</b> Purchase of long-term assets / ongoing, day-to-day operational costs<br>
        """)
        text.setWordWrap(True)
        layout.addWidget(text)

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(GenerationPopupHandler.style)
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)
        dlg.exec()

    def _show_solar_collector_popup(self):
        dialog = QDialog(self.parent)
        remove_qt_help_button(dialog)
        dialog.setWindowTitle("Solar Collector Input")
        dialog.setFixedSize(400, 460)
        dialog.setModal(True)

        main_layout = QVBoxLayout(dialog)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.addStretch()
        help_btn = QPushButton("?")
        help_btn.setStyleSheet(GenerationPopupHandler.style)
        help_btn.setFixedSize(35, 35)
        help_btn.clicked.connect(lambda: self.show_solar_collector_help(dialog))
        top_row.addWidget(help_btn)
        main_layout.addLayout(top_row)

        input_frame = QFrame()
        input_frame.setStyleSheet("""
        QFrame {border: 2px solid black; background-color: white;}
        QLabel {border: none; font-size: 12px; font-weight: bold;}
        
        QLineEdit {min-height: 28px;}
        QComboBox {min-height: 28px; padding-left: 6px;}
        """)
        input_layout = QVBoxLayout(input_frame)
        input_layout.setContentsMargins(12, 12, 12, 12)

        form_layout = QFormLayout()

        dataset = QComboBox()
        dataset.addItem(self.last_solar_collector_inputs["dataset"])
        lock_combobox(dataset)
        
        year = QComboBox()
        year.addItem(self.last_solar_collector_inputs["year"])
        lock_combobox(year)

        area = QLineEdit(self.last_solar_collector_inputs["area"])
        loss = QLineEdit(self.last_solar_collector_inputs["loss"])
        tracking = QComboBox()
        tracking.addItems(["None", "Single-axis", "Dual-axis"])
        tracking.setCurrentText(self.last_solar_collector_inputs["tracking"])
        tilt = QLineEdit(self.last_solar_collector_inputs["tilt"])
        azimuth = QLineEdit(self.last_solar_collector_inputs["azimuth"])
        
        form_layout.addRow("Dataset", dataset)
        form_layout.addRow("Year", year)
        form_layout.addRow("Area (m\u00b2)", area)
        form_layout.addRow("System loss (fraction)", loss)
        form_layout.addRow("Tracking", tracking)
        form_layout.addRow("Tilt (°)", tilt)
        form_layout.addRow("Azimuth (°)", azimuth)
        
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        form_layout.addRow(line)
        
        capex = QLineEdit(self.last_solar_collector_inputs["capex"])
        opex = QLineEdit(self.last_solar_collector_inputs["opex"])
        
        form_layout.addRow("CapEX (€)", capex)
        form_layout.addRow("OpEX (€/year)", opex)
        
        input_layout.addLayout(form_layout)
        main_layout.addWidget(input_frame)

        save_btn = QPushButton("Save")
        save_btn.setStyleSheet(GenerationPopupHandler.style)
        save_btn.setFixedWidth(80)
        save_btn.clicked.connect(lambda: self._save_solar_collector_inputs(
                            dialog, dataset, year,
                            area, loss, tracking,
                            tilt, azimuth, capex, opex))
        main_layout.addWidget(save_btn, alignment=Qt.AlignRight)
        dialog.exec()

    def _save_solar_collector_inputs(self, dialog, dataset, year, area, loss, tracking, tilt, azimuth, capex, opex):
        self.last_solar_collector_inputs.update({
            "dataset": dataset.currentText(),
            "year": year.currentText(),
            "area": area.text(),
            "loss": loss.text(),
            "tracking": tracking.currentText(),
            "tilt": tilt.text(),
            "azimuth": azimuth.text(),
            "capex": capex.text(),
            "opex": opex.text()
        })

        last_solar_collector_inputs = self.last_solar_collector_inputs.copy()
        last_solar_collector_inputs.update({
            "latitude": str(self.lat),
            "longitude": str(self.lon),
            "capex": capex.text(),
            "opex": opex.text()
        })

        self.scraper.pv_inputs.update(self.last_solar_collector_inputs)
        dialog.setEnabled(False)
        QApplication.setOverrideCursor(Qt.WaitCursor)

        saved_parent = self.scraper.parent
        self.scraper.parent = None

        def do_fetch():
            return self.scraper.fetch_radiance()

        def on_done(data, err):
            self.scraper.parent = saved_parent
            QApplication.restoreOverrideCursor()
            dialog.setEnabled(True)
            if data is None:
                QMessageBox.critical(dialog, "Fetch Error",
                    "Failed to fetch solar irradiance data from Renewables.ninja.\n"
                    "Check your API key and internet connection.")
                return
            self.solar_radiance_data = data
            self.solar_collector_data = self.simulator.solar_collector_simulator(
                last_solar_collector_inputs, data)
            self.workspace_manager.update("Input", "Solar Collector Inputs", last_solar_collector_inputs)
            self.workspace_manager.update("Data", "Solar Collector Data", self.solar_collector_data)
            self.workspace_manager.show_success("Solar Collector inputs and data saved successfully!")
            dialog.accept()

        self._worker = _FetchWorker(do_fetch)
        self._worker.done.connect(on_done)
        self._worker.start()

    def show_solar_collector_help(self, parent):
        dlg = QDialog(parent)
        remove_qt_help_button(dlg)
        dlg.setWindowTitle("Solar Collecotr - Input Help")
        dlg.setFixedSize(350, 260)

        layout = QVBoxLayout(dlg)
        text = QLabel("""
            <b>Solar Collecotr - Input Help</b><br><br>
            <b>Area:</b> Area of solar collector.<br>
            <b>System loss:</b> Fractional loss in the system (e.g. due to wiring, inverter).<br>
            <b>Tracking:</b> Type of PV panel tracking (None, Single, Dual-axis).<br>
            <b>Tilt / Azimuth:</b> Orientation angles of the PV system.<br>
            <b>CapEx / OpEx:</b> Purchase of long-term assets / ongoing, day-to-day operational costs<br>
        """)
        text.setWordWrap(True)
        layout.addWidget(text)

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(GenerationPopupHandler.style)
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)
        dlg.exec()


class StoragePopupHandler:
    last_battery_inputs = {
        "capacity": "1",
        "efficiency": "90",
        "rated_power": "0.5",
        "capex": "1000"
    }

    last_buffer_tank_inputs = {
        "capacity": "1",
        "rated power": "1",
        "retention factor": "98",
        "capex": "1000",
        "opex": "200"
        }

    combo_style = """
            QComboBox {
                background-color: white;
                color: black;
                font-weight: bold;
                font-size: 12px;
                border: 2px solid black;
            }
            QComboBox:hover {
                background-color: #f0f0f0;
            }
            QComboBox QAbstractItemView {
                background-color: white;
                selection-background-color: #f0f0f0;
                selection-color: black;
                font-size: 12px;
            }
        """

    def __init__(self, parent, toolbar, workspace_manager):
        self.parent = parent
        self.toolbar = toolbar
        self.validate = Technology(self.parent)
        self.workspace_manager = workspace_manager

    _menu_style = """
        QFrame { background: #ffffff; border: 1px solid #d0d0d0; }
        QPushButton {
            background: transparent; color: #222;
            font-size: 12px; font-weight: bold;
            border: none; border-bottom: 1px solid #eeeeee;
            padding: 9px 14px; text-align: left;
        }
        QPushButton:hover { background: #f0f7f3; color: #1a7f3c; }
        QLabel {
            color: #999; font-size: 9px; font-weight: bold;
            letter-spacing: 1px;
            padding: 5px 14px 3px 14px;
            background: #fafafa;
            border-bottom: 1px solid #eeeeee;
        }
    """

    def show_popup(self, pos=None):
        popup = QFrame(self.parent)
        popup.setWindowFlags(Qt.Popup)
        popup.setFixedWidth(230)
        popup.setStyleSheet(StoragePopupHandler._menu_style)
        layout = QVBoxLayout(popup)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(QLabel("ELECTRICITY STORAGE"))
        bat_btn = QPushButton("Battery")
        layout.addWidget(bat_btn)

        layout.addWidget(QLabel("THERMAL STORAGE"))
        buf_btn = QPushButton("Buffer Tank")
        layout.addWidget(buf_btn)

        popup.adjustSize()
        if pos:
            popup.move(pos)
        popup.show()

        bat_btn.clicked.connect(lambda: (popup.close(), self._show_battery_popup()))
        buf_btn.clicked.connect(lambda: (popup.close(), self._show_buffer_tank_popup()))

    def _show_battery_popup(self):
        dialog = QDialog(self.parent)
        remove_qt_help_button(dialog)
        dialog.setWindowTitle("Battery Input")
        dialog.setFixedSize(400, 270)
        dialog.setModal(True)

        main_layout = QVBoxLayout(dialog)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.addStretch()
        help_btn = QPushButton("?")
        help_btn.setFixedSize(35, 35)
        help_btn.setStyleSheet(GenerationPopupHandler.style)
        help_btn.clicked.connect(lambda: self._show_battery_help(dialog))
        top_row.addWidget(help_btn)
        main_layout.addLayout(top_row)

        input_frame = QFrame()
        input_frame.setStyleSheet("""QFrame {border: 2px solid black;background-color: white;} QLabel {border: none; font-size: 12px; font-weight: bold;}""")
        input_layout = QVBoxLayout(input_frame)
        input_layout.setContentsMargins(12, 12, 12, 12)

        form_layout = QFormLayout()

        capacity = QLineEdit(self.last_battery_inputs["capacity"])
        efficiency = QLineEdit(self.last_battery_inputs["efficiency"])
        rated_power = QLineEdit(self.last_battery_inputs["rated_power"])

        form_layout.addRow("Capacity (kWh)", capacity)
        form_layout.addRow("Efficiency (%)", efficiency)
        form_layout.addRow("Rated Power (kW)", rated_power)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        form_layout.addRow(line)

        capex = QLineEdit(self.last_battery_inputs.get("capex", ""))
        form_layout.addRow("CapEX (€)", capex)

        input_layout.addLayout(form_layout)
        main_layout.addWidget(input_frame)

        save_btn = QPushButton("Save")
        save_btn.setFixedWidth(80)
        save_btn.setStyleSheet(GenerationPopupHandler.style)
        save_btn.clicked.connect(lambda: (
            self._save_battery_data(capacity, efficiency, rated_power, capex, dialog)
        ))
        main_layout.addWidget(save_btn, alignment=Qt.AlignRight)

        dialog.exec()

    def _save_battery_data(self, capacity, efficiency, rated_power, capex, dialog):
        fields = {
            "Capacity (kWh)": capacity.text(),
            "Efficiency (%)": efficiency.text(),
            "Rated Power (kW)": rated_power.text(),
            "CapEX (€)": capex.text()
        }

        self.validate.validate_battery(fields)

        self.last_battery_inputs.update({
            "capacity": capacity.text(),
            "efficiency": efficiency.text(),
            "rated_power": rated_power.text(),
            "capex": capex.text()
        })

        self.workspace_manager.update("Input", "Battery Inputs", self.last_battery_inputs, coordinates=False)
        self.workspace_manager.show_success("Battery inputs saved successfully!")
        dialog.accept()

    def _show_battery_help(self, parent):
        dlg = QDialog(parent)
        remove_qt_help_button(dlg)
        dlg.setWindowTitle("Battery - Input Help")
        dlg.setFixedSize(350, 260)

        layout = QVBoxLayout(dlg)
        text = QLabel("""
            <b>Battery - Input Help</b><br><br>
            <b>Capacity:</b> Total energy the battery can store.<br>
            <b>Efficiency:</b> Round-trip efficiency percentage.<br>
            <b>Rated Power:</b> Maximum charge/discharge power.<br>
            <b>CapEx:</b> Purchase of long-term assets.<br>
            <br>
            <b>Battery CapEx is counted double due to lifespan!</b><br>
        """)
        text.setWordWrap(True)
        layout.addWidget(text)

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(GenerationPopupHandler.style)
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)

        dlg.exec()

    def _show_buffer_tank_popup(self):
        dialog = QDialog(self.parent)
        remove_qt_help_button(dialog)
        dialog.setWindowTitle("Buffer Tank Input")
        dialog.setFixedSize(400, 310)
        dialog.setModal(True)

        main_layout = QVBoxLayout(dialog)

        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.addStretch()
        help_btn = QPushButton("?")
        help_btn.setFixedSize(35, 35)
        help_btn.setStyleSheet(GenerationPopupHandler.style)
        help_btn.clicked.connect(lambda: self._show_buffer_help(dialog))
        top_row.addWidget(help_btn)
        main_layout.addLayout(top_row)

        input_frame = QFrame()
        input_frame.setStyleSheet("""QFrame {border: 2px solid black;background-color: white;} QLabel {border: none; font-size: 12px; font-weight: bold;}""")
        input_layout = QVBoxLayout(input_frame)
        input_layout.setContentsMargins(12, 12, 12, 12)

        form_layout = QFormLayout()

        capacity = QLineEdit(self.last_buffer_tank_inputs["capacity"])
        retention = QLineEdit(self.last_buffer_tank_inputs["retention factor"])
        rated_power = QLineEdit(self.last_buffer_tank_inputs["rated power"])

        form_layout.addRow("Capacity (kWh)", capacity)
        form_layout.addRow("Rated Power (kW-thermal)", rated_power)
        form_layout.addRow("Retention Factor %/h", retention)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        form_layout.addRow(line)

        capex = QLineEdit(self.last_buffer_tank_inputs.get("capex", ""))
        opex = QLineEdit(self.last_buffer_tank_inputs.get("opex", ""))
        form_layout.addRow("CapEX (€)", capex)
        form_layout.addRow("OpEX (€/year)", opex)

        input_layout.addLayout(form_layout)
        main_layout.addWidget(input_frame)

        save_btn = QPushButton("Save")
        save_btn.setFixedWidth(80)
        save_btn.setStyleSheet(GenerationPopupHandler.style)
        save_btn.clicked.connect(lambda: self._save_buffer_data(capacity, rated_power, retention, capex, opex, dialog))
        main_layout.addWidget(save_btn, alignment=Qt.AlignRight)

        dialog.exec()

    def _save_buffer_data(self, capacity, rated_power, retention, capex, opex, dialog):
        fields = {
            "Capacity (kWh)": capacity.text(),
            "Rated Power (kW-thermal)": rated_power.text(),
            "Retention Factor %/h": retention.text(),
            "CapEX (€)": capex.text(),
            "OpEX (€/year)": opex.text()
        }

        self.validate.validate_buffer_tank(fields)

        self.last_buffer_tank_inputs.update({
            "capacity": capacity.text(),
            "rated power": rated_power.text(),
            "retention factor": retention.text(),
            "capex": capex.text(),
            "opex": opex.text()
        })

        self.workspace_manager.update("Input", "Buffer Tank Inputs", self.last_buffer_tank_inputs, coordinates=False)
        self.workspace_manager.show_success("Buffer tank inputs saved successfully!")
        dialog.accept()

    def _show_buffer_help(self, parent):
        dlg = QDialog(parent)
        remove_qt_help_button(dlg)
        dlg.setWindowTitle("Buffer Tank - Input Help")
        dlg.setFixedSize(350, 260)

        layout = QVBoxLayout(dlg)
        text = QLabel("""
            <b>Buffer Tank - Input Help</b><br><br>
            <b>Capacity:</b> Thermal energy capacity of the buffer tank.<br>
            <b>Rated Power:</b> Maximum thermal charge/discharge rate.<br>
            <b>Retention Factor:</b> How much heat is retained per hour (e.g. 98 means 2% heat loss per hour).<br>
            <b>CapEx / OpEx:</b> Purchase of long-term assets / ongoing, day-to-day operational costs<br>
        """)
        text.setWordWrap(True)
        layout.addWidget(text)

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(GenerationPopupHandler.style)
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)

        dlg.exec()



class ThermalElectricityDemandPopupHandler:

    last_thermal_and_electricity_demand_inputs = {
        "year": "2023", "heating_threshold": "14", "cooling_threshold": "20",
        "base_power": "0", "heating_power": "0.3", "cooling_power": "0.15",
        "smoothing": "0.5", "solar_gains": "0.012", "wind_chill": "-0.2", "humidity_discomfort": "0.05"
    }

    def __init__(self, parent, lat, lon, workspace_manager):
        self.parent = parent
        self.lat = lat
        self.lon = lon
        api_key = get_ninja_api_key()
        if not api_key:
            actual_path = _config_path()  # this returns a Path object
            QMessageBox.warning(
                self.parent,
                "Missing API key",
                f"Please set your Renewables.ninja API key in:\n\n{actual_path}\n\nunder 'ninja_api_key'."
            )
            return

        
        self.scraper = NinjaScraper(
            api_key=api_key,
            lat=self.lat,
            lon=self.lon,
            demand_inputs = self.last_thermal_and_electricity_demand_inputs,
            parent=self.parent
        )
        self.thermal_and_electricity_data = None
        self.workspace_manager = workspace_manager

    def show_popup(self, pos=None):
        dialog = QDialog(self.parent)
        remove_qt_help_button(dialog)
        dialog.setWindowTitle("Heating and Cooling + Electricity Demand Input")
        dialog.setWindowIcon(QIcon("Ninja_renewables.png"))
        dialog.setFixedSize(400, 460)
        dialog.setModal(True)

        main_layout = QVBoxLayout(dialog)
        top_row = QHBoxLayout()
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.addStretch()
        help_btn = QPushButton("?")
        help_btn.setFixedSize(35, 35)
        help_btn.setStyleSheet(GenerationPopupHandler.style)
        help_btn.clicked.connect(lambda: self.show_help(dialog))
        top_row.addWidget(help_btn)
        main_layout.addLayout(top_row)

        # Form layout
        input_frame = QFrame()
        input_frame.setStyleSheet("""QFrame {border: 2px solid black;background-color: white;} QLabel {border: none; font-size: 12px; font-weight: bold;}""")
        input_layout = QVBoxLayout(input_frame)
        input_layout.setContentsMargins(12, 12, 12, 12)

        form_layout = QFormLayout()

        dataset = QComboBox(); dataset.addItem("MEERA-2 (global)")
        year = QComboBox(); year.addItem("2023"); year.setCurrentText(self.last_thermal_and_electricity_demand_inputs["year"])
        heating = QLineEdit(self.last_thermal_and_electricity_demand_inputs["heating_threshold"])
        cooling = QLineEdit(self.last_thermal_and_electricity_demand_inputs["cooling_threshold"])
        base = QLineEdit(self.last_thermal_and_electricity_demand_inputs["base_power"])
        heat_pow = QLineEdit(self.last_thermal_and_electricity_demand_inputs["heating_power"])
        cool_pow = QLineEdit(self.last_thermal_and_electricity_demand_inputs["cooling_power"])
        smoothing = QLineEdit(self.last_thermal_and_electricity_demand_inputs["smoothing"])
        solar = QLineEdit(self.last_thermal_and_electricity_demand_inputs["solar_gains"])
        wind = QLineEdit(self.last_thermal_and_electricity_demand_inputs["wind_chill"])
        humidity = QLineEdit(self.last_thermal_and_electricity_demand_inputs["humidity_discomfort"])

        form_layout.addRow("Dataset", dataset)
        form_layout.addRow("Year", year)
        form_layout.addRow("Heating threshold (°C)", heating)
        form_layout.addRow("Cooling threshold (°C)", cooling)
        form_layout.addRow("Base Power (kW)", base)
        form_layout.addRow("Heating Power (kW/°C)", heat_pow)
        form_layout.addRow("Cooling Power (kW/°C)", cool_pow)
        form_layout.addRow("Smoothing (1/days)", smoothing)
        form_layout.addRow("Solar gains (°C per W/m²)", solar)
        form_layout.addRow("Wind chill (°C per m/s)", wind)
        form_layout.addRow("Humidity discomfort (°C per g/kg)", humidity)

        input_layout.addLayout(form_layout)
        main_layout.addWidget(input_frame)

        last_thermal_and_electricity_demand_inputs = self.last_thermal_and_electricity_demand_inputs.copy()

        save_btn = QPushButton("Save")
        save_btn.setStyleSheet(GenerationPopupHandler.style)
        save_btn.clicked.connect(lambda: (
            self.last_thermal_and_electricity_demand_inputs.update({
                "year": year.currentText(),
                "heating_threshold": heating.text(),
                "cooling_threshold": cooling.text(),
                "base_power": base.text(),
                "heating_power": heat_pow.text(),
                "cooling_power": cool_pow.text(),
                "smoothing": smoothing.text(),
                "solar_gains": solar.text(),
                "wind_chill": wind.text(),
                "humidity_discomfort": humidity.text()
            }),
            last_thermal_and_electricity_demand_inputs.update(self.last_thermal_and_electricity_demand_inputs),
            last_thermal_and_electricity_demand_inputs.update({
                "latitude": str(self.lat),
                "longitude": str(self.lon)
            }),
            self.scraper.demand_inputs.update(self.last_thermal_and_electricity_demand_inputs),
            setattr(self, 'thermal_and_electricity_data', self.scraper.fetch_demand()),

            self.workspace_manager.update("Input", "Thermal+Electricity Demand Inputs",last_thermal_and_electricity_demand_inputs),
            self.workspace_manager.update("Data", "Thermal+Electricity Demand Data", self.thermal_and_electricity_data),
            self.workspace_manager.show_success("Heating, cooling and electricity demand inputs and data saved!"),
            dialog.accept()
        ))
        main_layout.addWidget(save_btn, alignment=Qt.AlignRight)
        dialog.exec()

    def show_help(self, parent):
        dlg = QDialog(parent) 
        remove_qt_help_button(dlg)
        dlg.setWindowTitle("Heating and Cooling + Electricity Demand - Input Help")
        dlg.setFixedSize(350, 300)
        layout = QVBoxLayout(dlg)
        text = QLabel("""
            <b>Heating and cooling + electricity demand Input Help</b><br><br>
            <b>Dataset:</b> Source of weather data.<br>
            <b>Year:</b> Simulation year (must match dataset availability).<br>
            <b>Heating/Cooling threshold:</b> Temperature below/above which demand is triggered.<br>
            <b>Base Power:</b> Constant demand regardless of temperature.<br>
            <b>Heating/Cooling Power:</b> Additional demand per degree difference from threshold.<br>
            <b>Smoothing:</b> How fast the system responds (higher = slower).<br>
            <b>Solar gains:</b> How much the sun heats the building.<br>
            <b>Wind chill:</b> Cooling effect of wind.<br>
            <b>Humidity discomfort:</b> Perceived temperature increase per unit humidity.<br>
        """)
        text.setWordWrap(True)
        layout.addWidget(text)

        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(GenerationPopupHandler.style)
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignRight); dlg.exec()


class ThermalDemandPopupHandler:
    last_yearly_thermal_demand_inputs = {
        "year": "2023", "heating_threshold": "20", "cooling_threshold": "25",
        "annual_heating": "2000", "annual_cooling": "1000"
    }

    last_monthly_thermal_demand_inputs = {
        "dataset": "MEERA-2 (global)", "year": "2023",
        "heating_threshold": "20", "cooling_threshold": "25"
    }
    for i in range(1, 13):
        last_monthly_thermal_demand_inputs[f"month_{i}_heating"] = ""
        last_monthly_thermal_demand_inputs[f"month_{i}_cooling"] = ""

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

    def __init__(self, parent, toolbar, lat, lon, workspace_manager):
        self.parent = parent
        self.toolbar = toolbar
        self.lat = lat
        self.lon = lon
        self.uploader = DataUpload(parent)
        self.thermal_uploaded_data = None
        self.thermal_simulator = ThermalDemandSimulator(parent=self.parent, lat=self.lat, lon=self.lon)
        self.heating_demand_data_yearly = None
        self.cooling_demand_data_yearly = None
        self.heating_demand_data_monthly = None
        self.cooling_demand_data_monthly = None
        self.workspace_manager = workspace_manager

    def show_popup(self, pos=None):
        popup = QFrame(self.parent)
        popup.setWindowFlags(Qt.Popup)
        popup.setFixedSize(280, 150)
        popup.setStyleSheet("background-color: white; border: 1px solid #ccc;")
        layout = QVBoxLayout(popup)

        simulate_btn = QPushButton("Simulate \n  heating and cooling demand")
        simulate_btn.setStyleSheet(""" QPushButton {padding: 10px; font-size: 14px;} QPushButton:hover {background-color: #f0f0f0;}""")
        simulate_btn.clicked.connect(lambda: (popup.close(), self._show_input_method_popup()))
        layout.addWidget(simulate_btn)

        upload_btn = QPushButton("Upload heating and cooling demand")
        upload_btn.setStyleSheet(""" QPushButton {padding: 10px; font-size: 14px;} QPushButton:hover {background-color: #f0f0f0;}""")
        upload_btn.clicked.connect(lambda: (popup.close(), self.show_upload_popup()))
        layout.addWidget(upload_btn)

        if pos:
            popup.move(pos)

        QApplication.instance().installEventFilter(self.parent)
        popup.show()

    def _show_input_method_popup(self):
        dialog = QDialog(self.parent)
        remove_qt_help_button(dialog)
        dialog.setWindowTitle("Heating and Cooling Demand Input Method")
        dialog.setFixedSize(250, 150)
        layout = QVBoxLayout(dialog)

        yearly_btn = QPushButton("Yearly input")
        yearly_btn.setStyleSheet(ThermalDemandPopupHandler.style)
        monthly_btn = QPushButton("Monthly input")
        monthly_btn.setStyleSheet(ThermalDemandPopupHandler.style)

        yearly_btn.clicked.connect(lambda: (dialog.close(), self.show_yearly_input()))
        monthly_btn.clicked.connect(lambda: (dialog.close(), self.show_monthly_input()))

        layout.addWidget(yearly_btn)
        layout.addWidget(monthly_btn)

        dialog.exec()

    def show_yearly_input(self):
        dialog = QDialog(self.parent)
        remove_qt_help_button(dialog)
        dialog.setWindowTitle("Simulate Yearly Heating and Cooling Input")
        dialog.setFixedSize(400, 370)
        dialog.setModal(True)

        layout = QVBoxLayout(dialog)
        top_row = QHBoxLayout()
        top_row.addStretch()
        help_btn = QPushButton("?")
        help_btn.setFixedSize(35, 35)
        help_btn.setStyleSheet(GenerationPopupHandler.style)
        help_btn.clicked.connect(lambda: self.show_help_popup(dialog))
        top_row.addWidget(help_btn)
        layout.addLayout(top_row)

        # Form layout
        input_frame = QFrame()
        input_frame.setStyleSheet("""
        QFrame {border: 2px solid black; background-color: white;}
        QLabel {border: none; font-size: 12px; font-weight: bold;}
        
        QLineEdit {min-height: 28px;}
        QComboBox {min-height: 28px; padding-left: 6px;}
        """)

        
        input_layout = QVBoxLayout(input_frame)
        input_layout.setContentsMargins(12, 12, 12, 12)

        form_layout = QFormLayout()

        dataset_combo = QComboBox(); dataset_combo.addItem("MEERA-2 (global)")
        lock_combobox(dataset_combo)
        
        year_combo = QComboBox(); year_combo.addItem("2023")
        year_combo.setCurrentText(self.last_yearly_thermal_demand_inputs["year"])
        lock_combobox(year_combo)

        heating_input = QLineEdit(self.last_yearly_thermal_demand_inputs["heating_threshold"])
        cooling_input = QLineEdit(self.last_yearly_thermal_demand_inputs["cooling_threshold"])
        annual_heating = QLineEdit(self.last_yearly_thermal_demand_inputs["annual_heating"])
        annual_cooling = QLineEdit(self.last_yearly_thermal_demand_inputs["annual_cooling"])

        form_layout.addRow("Dataset", dataset_combo)
        form_layout.addRow("Year", year_combo)
        form_layout.addRow("Heating threshold (°C)", heating_input)
        form_layout.addRow("Cooling threshold (°C)", cooling_input)
        form_layout.addRow("Annual heating (kWh)", annual_heating)
        form_layout.addRow("Annual cooling (kWh)", annual_cooling)


        input_layout.addLayout(form_layout)
        layout.addWidget(input_frame)

        save_btn = QPushButton("Save")
        save_btn.setStyleSheet(GenerationPopupHandler.style)
        save_btn.clicked.connect(lambda: self._save_yearly(
            year_combo.currentText(), heating_input.text(), cooling_input.text(),
            annual_heating.text(), annual_cooling.text(), dialog
        ))
        layout.addWidget(save_btn, alignment=Qt.AlignRight)
        dialog.exec()

    def _save_yearly(self, year, heating, cooling, annual_heat, annual_cool, dialog):
        self.last_yearly_thermal_demand_inputs.update({
            "year": year,
            "heating_threshold": heating,
            "cooling_threshold": cooling,
            "annual_heating": annual_heat,
            "annual_cooling": annual_cool
        })
        last_yearly_thermal_demand_inputs = self.last_yearly_thermal_demand_inputs.copy()
        last_yearly_thermal_demand_inputs.update({
            "latitude": str(self.lat),
            "longitude": str(self.lon)
        })
        self.heating_demand_data_yearly, self.cooling_demand_data_yearly = self.thermal_simulator.simulate_yearly(
            self.last_yearly_thermal_demand_inputs
        )

        self.workspace_manager.update("Input", "Yearly Thermal Inputs", last_yearly_thermal_demand_inputs)
        self.workspace_manager.update("Data", "Yearly Heating Data", self.heating_demand_data_yearly)
        self.workspace_manager.update("Data", "Yearly Cooling Data", self.cooling_demand_data_yearly)
        self.workspace_manager.show_success("Yearly heating/cooling inputs and data saved successfully!")

        dialog.accept()

    def show_monthly_input(self):
        dialog = QDialog(self.parent)
        remove_qt_help_button(dialog)
        dialog.setWindowTitle("Simulate Monthly Heating and Cooling Input")
        dialog.setFixedSize(400, 500)
        dialog.setModal(True)

        layout = QVBoxLayout(dialog)
        top_row = QHBoxLayout()
        top_row.addStretch()
        help_btn = QPushButton("?")
        help_btn.setFixedSize(35, 35)
        help_btn.setStyleSheet(GenerationPopupHandler.style)
        help_btn.clicked.connect(lambda: self._show_monthly_help(dialog))
        top_row.addWidget(help_btn)
        layout.addLayout(top_row)

        # Form layout
        input_frame = QFrame()
        input_frame.setStyleSheet("""QFrame {border: 2px solid black;background-color: white;} QLabel {border: none; font-size: 12px; font-weight: bold;}""")
        input_layout = QVBoxLayout(input_frame)
        input_layout.setContentsMargins(12, 12, 12, 12)

        form_layout = QFormLayout()

        dataset_combo = QComboBox()
        dataset_combo.addItem("MEERA-2 (global)")
        dataset_combo.setCurrentText(self.last_monthly_thermal_demand_inputs.get("dataset", "MEERA-2 (global)"))
        lock_combobox(dataset_combo)
        
        year_combo = QComboBox()
        year_combo.addItem("2023")
        year_combo.setCurrentText(self.last_monthly_thermal_demand_inputs.get("year", "2023"))
        lock_combobox(year_combo)


        heating_threshold = QLineEdit(self.last_monthly_thermal_demand_inputs.get("heating_threshold"))
        cooling_threshold = QLineEdit(self.last_monthly_thermal_demand_inputs.get("cooling_threshold"))

        form_layout.addRow("Dataset", dataset_combo)
        form_layout.addRow("Year", year_combo)
        form_layout.addRow("Heating threshold (°C)", heating_threshold)
        form_layout.addRow("Cooling threshold (°C)", cooling_threshold)

        input_layout.addLayout(form_layout)
        layout.addWidget(input_frame)

        scroll_content = QWidget()
        scroll_form = QFormLayout(scroll_content)

        self.monthly_inputs = {}
        for i in range(12):
            m = i + 1
            h_key = f"month_{m}_heating"
            c_key = f"month_{m}_cooling"
            h_field = QLineEdit(self.last_monthly_thermal_demand_inputs.get(h_key, ""))
            c_field = QLineEdit(self.last_monthly_thermal_demand_inputs.get(c_key, ""))
            self.monthly_inputs[h_key] = h_field
            self.monthly_inputs[c_key] = c_field
            scroll_form.addRow(f"Month {m} - Heating (kWh)", h_field)
            scroll_form.addRow(f"Month {m} - Cooling (kWh)", c_field)

        scroll_frame = QFrame()
        scroll_frame.setStyleSheet("""
            QFrame {
                border: 1px solid black;
                background-color: white;
            }
            QLabel {
                font-size: 12px;
                font-weight: bold;
                border: none;
            }
        """)

        scroll_frame_layout = QVBoxLayout(scroll_frame)
        scroll_frame_layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(scroll_content)
        scroll.setStyleSheet("background-color: white;")
        scroll_frame_layout.addWidget(scroll)
        
        layout.addWidget(scroll_frame)

        save_btn = QPushButton("Save")
        save_btn.setStyleSheet(GenerationPopupHandler.style)
        save_btn.clicked.connect(lambda: self._save_monthly(
            dataset_combo.currentText(), year_combo.currentText(),
            heating_threshold.text(), cooling_threshold.text(), dialog
        ))
        layout.addWidget(save_btn, alignment=Qt.AlignRight)

        dialog.setLayout(layout)
        dialog.exec()

    def _save_monthly(self, dataset, year, heating_thr, cooling_thr, dialog):
        self.last_monthly_thermal_demand_inputs.update({
            "dataset": dataset,
            "year": year,
            "heating_threshold": heating_thr,
            "cooling_threshold": cooling_thr
        })


        for key, widget in self.monthly_inputs.items():
            self.last_monthly_thermal_demand_inputs[key] = widget.text()

        last_monthly_thermal_demand_inputs = self.last_monthly_thermal_demand_inputs
        last_monthly_thermal_demand_inputs.update({
            "latitude": str(self.lat),
            "longitude": str(self.lon)
        })

        # Validate API key on main thread before going async
        from config_loader import get_ninja_api_key, _config_path as _cp
        if not get_ninja_api_key():
            QMessageBox.warning(dialog, "Missing API Key",
                f"Please set your Renewables.ninja API key in:\n\n{_cp()}\n\nunder 'ninja_api_key'.")
            return

        dialog.setEnabled(False)
        QApplication.setOverrideCursor(Qt.WaitCursor)

        inputs_snapshot = last_monthly_thermal_demand_inputs

        def do_fetch():
            return self.thermal_simulator.simulate_monthly(self.last_monthly_thermal_demand_inputs)

        def on_done(result, err):
            QApplication.restoreOverrideCursor()
            dialog.setEnabled(True)
            if result is None:
                QMessageBox.critical(dialog, "Fetch Error",
                    "Failed to fetch temperature data from Renewables.ninja.\n"
                    "Check your API key and internet connection.")
                return
            self.heating_demand_data_monthly, self.cooling_demand_data_monthly = result
            self.workspace_manager.update("Input", "Monthly Thermal Inputs", inputs_snapshot)
            self.workspace_manager.update("Data", "Monthly Heating Data", self.heating_demand_data_monthly)
            self.workspace_manager.update("Data", "Monthly Cooling Data", self.cooling_demand_data_monthly)
            self.workspace_manager.show_success("Monthly heating/cooling inputs and data saved successfully!")
            dialog.accept()

        self._worker = _FetchWorker(do_fetch)
        self._worker.done.connect(on_done)
        self._worker.start()

    def show_upload_popup(self):
        dialog = QDialog(self.parent)
        remove_qt_help_button(dialog)
        dialog.setWindowTitle("Upload Thermal Demand - CSV")
        dialog.setFixedSize(360, 360)

        main_layout = QVBoxLayout(dialog)

        # Framed section (instructions + form)
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                border: 2px solid black;
                background-color: white;
            }
            QLabel {
                font-size: 12px;
                font-weight: bold;
                border: none;
            }
        """)
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(12, 12, 12, 12)
        frame_layout.setSpacing(10)

        # Instruction label (deterministic + stochastic)
        description = QLabel("""
            <b>CSV Format:</b><br>
            - 8760 rows representing hourly thermal demand.<br>
            - <u>Deterministic:</u> Two columns named <i>heating_demand</i> and <i>cooling_demand</i> in kWh (decimal “123.45” or “123,45”).<br>
            - <u>Stochastic:</u> 10 columns side-by-side named
              <i>heating_demand1</i> … <i>heating_demand5</i> and
              <i>cooling_demand1</i> … <i>cooling_demand5</i> (each column has 8760 values).<br>
        """)
        description.setWordWrap(True)
        frame_layout.addWidget(description)

        # Separator line
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        frame_layout.addWidget(line)

        # Mode selection: Deterministic vs Stochastic
        mode_layout = QHBoxLayout()
        deterministic_cb = QCheckBox("Deterministic")
        stochastic_cb = QCheckBox("Stochastic")

        if not hasattr(self, "last_thermal_upload_inputs") or self.last_thermal_upload_inputs is None:
            self.last_thermal_upload_inputs = {}

        deterministic_cb.setChecked(self.last_thermal_upload_inputs.get("mode", "deterministic") == "deterministic")
        stochastic_cb.setChecked(self.last_thermal_upload_inputs.get("mode", "deterministic") == "stochastic")

        deterministic_cb.setStyleSheet(GenerationPopupHandler.check_style)
        stochastic_cb.setStyleSheet(GenerationPopupHandler.check_style)

        mode_group = QButtonGroup(dialog)
        mode_group.setExclusive(True)
        mode_group.addButton(deterministic_cb)
        mode_group.addButton(stochastic_cb)

        mode_layout.addWidget(deterministic_cb)
        mode_layout.addWidget(stochastic_cb)
        frame_layout.addLayout(mode_layout)

        main_layout.addWidget(frame)

        upload_btn = QPushButton("Select CSV File")
        upload_btn.setStyleSheet(GenerationPopupHandler.style)
        main_layout.addWidget(upload_btn, alignment=Qt.AlignRight)

        def thermal_file_upload():
            selected_mode = "stochastic" if stochastic_cb.isChecked() else "deterministic"

            file_path, _ = QFileDialog.getOpenFileName(dialog, "Select CSV", "", "CSV Files (*.csv)")
            if file_path:
                # Call correct uploader based on mode
                if selected_mode == "deterministic":
                    self.thermal_uploaded_data = self.uploader.upload_thermal_demand_data(file_path)
                    # Expecting 2 columns -> split into heating/cooling like before
                    self.heating_uploaded_data = self.thermal_uploaded_data[0]
                    self.cooling_uploaded_data = self.thermal_uploaded_data[1]
                else:
                    self.thermal_uploaded_data = self.uploader.upload_thermal_demand_data_stochastic(file_path)

                    self.heating_uploaded_data = self.thermal_uploaded_data[0:5]
                    self.cooling_uploaded_data = self.thermal_uploaded_data[5:]

                # Save last inputs including mode
                self.last_thermal_upload_inputs.update({
                    "mode": selected_mode
                })

                # Workspace updates
                if selected_mode == "deterministic":
                    self.workspace_manager.update("Data", "Uploaded Heating Data", self.heating_uploaded_data)
                    self.workspace_manager.update("Data", "Uploaded Cooling Data", self.cooling_uploaded_data)
                    self.workspace_manager.update("Input", "Thermal Upload Inputs", self.last_thermal_upload_inputs, coordinates=False)
                else:
                    self.workspace_manager.update("Data", "Uploaded Heating Data (stochastic)",self.heating_uploaded_data)
                    self.workspace_manager.update("Data", "Uploaded Cooling Data (stochastic)", self.cooling_uploaded_data)
                    self.workspace_manager.update("Input", "Thermal Upload Inputs (stochastic)", self.last_thermal_upload_inputs, coordinates=False)

                self.workspace_manager.show_success("Uploaded Thermal data saved successfully!")
                dialog.accept()

        upload_btn.clicked.connect(thermal_file_upload)
        dialog.exec()


    def show_help_popup(self, parent):
        dlg = QDialog(parent)
        remove_qt_help_button(dlg)
        dlg.setWindowTitle("Simulate Yearly Heating and Cooling Demand Input - Help")
        dlg.setFixedSize(350, 300)
        layout = QVBoxLayout(dlg)
        help_text = QLabel("""
            <b>Simulate heating and cooling demand – Input Help</b><br><br>
            <b>Dataset:</b> The weather dataset used for simulation.<br>
            <b>Year:</b> The simulation year (must match dataset availability).<br>
            <b>Heating threshold:</b> Outdoor temperature below which heating is needed.<br>
            <b>Cooling threshold:</b> Outdoor temperature above which cooling is needed.<br>
            <b>Annual heating:</b> Estimated annual heating energy demand.<br>
            <b>Annual cooling:</b> Estimated annual cooling energy demand.<br>
        """)
        help_text.setWordWrap(True)
        layout.addWidget(help_text)
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(GenerationPopupHandler.style)
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)
        dlg.exec()

    def _show_monthly_help(self, parent):
        dlg = QDialog(parent)
        remove_qt_help_button(dlg)
        dlg.setWindowTitle("Simulate Monthly Heating and Cooling Demand Input - Help")
        dlg.setFixedSize(350, 260)
        layout = QVBoxLayout(dlg)
        help_text = QLabel("""
            <b>Simulate heating and cooling demand – Input Help</b><br><br>
            <b>Dataset:</b> The weather dataset used for simulation.<br>
            <b>Year:</b> The simulation year (must match dataset availability).<br>
            <b>Heating threshold:</b> Outdoor temperature below which heating is needed.<br>
            <b>Cooling threshold:</b> Outdoor temperature above which cooling is needed.<br>
            Enter estimated heating and cooling demand for each month.<br>
        """)
        help_text.setWordWrap(True)
        layout.addWidget(help_text)
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(GenerationPopupHandler.style)
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)
        dlg.exec()


class ElectricityDemandPopupHandler:
    last_yearly_electricity_demand_inputs = {
        "annual_demand": "3000", "morning_peak": "7", "evening_peak": "19", "dip_hour": "14"
    }

    last_monthly_electricity_demand_inputs = {
        "morning_peak": "7",
        "evening_peak": "19",
        "dip_hour": "14",
        **{f"month_{i+1}": "" for i in range(12)}
    }

    last_yearly_base_electricity_demand_inputs = {
        "annual_demand": "3000"}

    last_monthly_base_electricity_demand_inputs = {
        **{f"month_{i+1}": "" for i in range(12)}
        }

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

    def __init__(self, parent, toolbar, workspace_manager):
        self.parent = parent
        self.toolbar = toolbar
        self.electricity_simulator = ElectricityDemandSimulator(self.parent)
        self.electricity_uploaded_data = None
        self.electricity_demand_data_yearly = None
        self.electricity_demand_data_monthly = None
        self.uploader = DataUpload(parent)
        self.workspace_manager = workspace_manager

    def show_popup(self, pos=None):
        popup = QFrame(self.parent)
        popup.setWindowFlags(Qt.Popup)
        popup.setFixedSize(280, 200)
        popup.setStyleSheet("background-color: white; border: 1px solid #ccc;")

        layout = QVBoxLayout(popup)
        sim_btn = QPushButton("Simulate \n  electricity demand")
        sim_btn.setStyleSheet(""" QPushButton {padding: 10px; font-size: 14px;} QPushButton:hover {background-color: #f0f0f0;}""")
        upload_btn = QPushButton("Upload electricity demand")
        upload_btn.setStyleSheet(""" QPushButton {padding: 10px; font-size: 14px;} QPushButton:hover {background-color: #f0f0f0;}""")
        sim_btn.clicked.connect(lambda: (popup.close(), self._show_input_method_popup()))
        upload_btn.clicked.connect(lambda: (popup.close(), self.show_upload_popup()))
        layout.addWidget(sim_btn)
        layout.addWidget(upload_btn)

        if pos:
            popup.move(pos)

        QApplication.instance().installEventFilter(self.parent)
        popup.show()

    def _show_input_method_popup(self):
        dialog = QDialog(self.parent)
        remove_qt_help_button(dialog)
        dialog.setWindowTitle("Electricity Demand Input Method")
        dialog.setFixedSize(250, 150)
        layout = QVBoxLayout(dialog)

        yearly_btn = QPushButton("Yearly input")
        yearly_btn.setStyleSheet(ElectricityDemandPopupHandler.style)
        monthly_btn = QPushButton("Monthly input")
        monthly_btn.setStyleSheet(ElectricityDemandPopupHandler.style)

        yearly_btn.clicked.connect(lambda: (dialog.close(), self.show_yearly_input()))
        monthly_btn.clicked.connect(lambda: (dialog.close(), self.show_monthly_input()))

        layout.addWidget(yearly_btn)
        layout.addWidget(monthly_btn)
        dialog.exec()

    def show_yearly_input(self):
        dialog = QDialog(self.parent)
        remove_qt_help_button(dialog)
        dialog.setWindowTitle("Simulate Yearly Electricity Demand Input")
        dialog.setFixedSize(400, 300)
        dialog.setModal(True)
    
        layout = QVBoxLayout(dialog)
    
        # Top-right help button
        top_row = QHBoxLayout()
        top_row.addStretch()
        help_btn = QPushButton("?")
        help_btn.setFixedSize(35, 35)
        help_btn.setStyleSheet(GenerationPopupHandler.style)
        help_btn.clicked.connect(lambda: self._show_yearly_help(dialog))
        top_row.addWidget(help_btn)
        layout.addLayout(top_row)
    
        # Framed Section with Checkboxes + Form
        input_frame = QFrame()
        input_frame.setStyleSheet("""
        QFrame {
            border: 2px solid black;
            background-color: white;
        }
        QLabel {
            border: none;
            font-size: 12px;
            font-weight: bold;
        }
        QCheckBox {
            font-size: 12px;
            spacing: 8px;
        }
        QCheckBox::indicator {
            width: 16px;
            height: 16px;
            background-color: white;
            border: 1px solid black;
        }
        QCheckBox::indicator:checked {
            background-color: #c0c0c0;
            border: 1px solid black;
        }
    """)
        input_layout = QVBoxLayout(input_frame)
        input_layout.setContentsMargins(12, 12, 12, 12)
    
        # Checkboxes row (inside frame)
        checkbox_row = QHBoxLayout()
        simulate_checkbox = QCheckBox("Simulate base curve")
        base_curve_checkbox = QCheckBox("Built in base curve")
        simulate_checkbox.setChecked(True)
        checkbox_row.addWidget(simulate_checkbox)
        checkbox_row.addWidget(base_curve_checkbox)
        input_layout.addLayout(checkbox_row)
    
        # Form layout
        form_layout = QFormLayout()
    
        annual = QLineEdit(self.last_yearly_electricity_demand_inputs["annual_demand"])
        morning_label = QLabel("Morning peak hour")
        morning = QLineEdit(self.last_yearly_electricity_demand_inputs["morning_peak"])
        evening_label = QLabel("Evening peak hour")
        evening = QLineEdit(self.last_yearly_electricity_demand_inputs["evening_peak"])
        dip_label = QLabel("Dip hour")
        dip = QLineEdit(self.last_yearly_electricity_demand_inputs["dip_hour"])
    
        form_layout.addRow("Annual electricity demand (kWh)", annual)
        form_layout.addRow(morning_label, morning)
        form_layout.addRow(evening_label, evening)
        form_layout.addRow(dip_label, dip)
        input_layout.addLayout(form_layout)

        layout.addWidget(input_frame)

        # Toggle logic
        def toggle_checkboxes(source):
            if source == "simulate":
                simulate_checkbox.setChecked(True)
                base_curve_checkbox.setChecked(False)
                morning_label.show()
                morning.show()
                evening_label.show()
                evening.show()
                dip_label.show()
                dip.show()
            else:
                base_curve_checkbox.setChecked(True)
                simulate_checkbox.setChecked(False)
                morning_label.hide()
                morning.hide()
                evening_label.hide()
                evening.hide()
                dip_label.hide()
                dip.hide()

        simulate_checkbox.clicked.connect(lambda: toggle_checkboxes("simulate"))
        base_curve_checkbox.clicked.connect(lambda: toggle_checkboxes("base"))

        # Save button
        save_btn = QPushButton("Save")
        save_btn.setStyleSheet(GenerationPopupHandler.style)
        save_btn.clicked.connect(lambda: (
            self._save_yearly(
                annual.text(),
                morning.text(),
                evening.text(),
                dip.text(),
                simulate_checkbox.isChecked(),
                dialog
            )
        ))
        layout.addWidget(save_btn, alignment=Qt.AlignRight)

        dialog.exec()

    def _save_yearly(self, annual, morning, evening, dip, simulate_enabled, dialog):
        if simulate_enabled:
            self.last_yearly_electricity_demand_inputs.update({
                "annual_demand": annual,
                "morning_peak": morning,
                "evening_peak": evening,
                "dip_hour": dip
            })
            self.electricity_demand_data_yearly = self.electricity_simulator.simulate_yearly(self.last_yearly_electricity_demand_inputs,
                                                                                             noise = False)
            self.workspace_manager.update("Data", "Yearly Electricity Data", self.electricity_demand_data_yearly)
            self.workspace_manager.update("Input", "Yearly Electricity Inputs", self.last_yearly_electricity_demand_inputs)
            self.workspace_manager.show_success("Yearly electricity inputs and data saved successfully!")
            dialog.accept()
        else:
            self.last_yearly_base_electricity_demand_inputs.update({
                "annual_demand": annual
            })
            self.electricity_demand_data_yearly = self.electricity_simulator.simulate_yearly(
                self.last_yearly_base_electricity_demand_inputs,
                use_base_curve= True,
                noise = False)
            self.workspace_manager.update("Data", "Yearly Electricity Data", self.electricity_demand_data_yearly)
            self.workspace_manager.update("Input", "Yearly Electricity Inputs", self.last_yearly_base_electricity_demand_inputs)
            self.workspace_manager.show_success("Yearly electricity inputs saved (base curve mode).")
            dialog.accept()

    def show_monthly_input(self):
        dialog = QDialog(self.parent)
        remove_qt_help_button(dialog)
        dialog.setWindowTitle("Simulate Monthly Electricity Demand Input")
        dialog.setFixedSize(400, 540)
        dialog.setModal(True)

        layout = QVBoxLayout(dialog)

        # Top row with help button
        top_row = QHBoxLayout()
        top_row.addStretch()
        help_btn = QPushButton("?")
        help_btn.setFixedSize(35, 35)
        help_btn.setStyleSheet(GenerationPopupHandler.style)
        help_btn.clicked.connect(lambda: self._show_monthly_help(dialog))
        top_row.addWidget(help_btn)
        layout.addLayout(top_row)

        # Input + checkbox frame
        input_frame = QFrame()
        input_frame.setStyleSheet("""
            QFrame {
                border: 2px solid black;
                background-color: white;
            }
            QLabel {
                border: none;
                font-size: 12px;
                font-weight: bold;
            }
            QCheckBox {
                font-size: 12px;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                background-color: white;
                border: 1px solid black;
            }
            QCheckBox::indicator:checked {
                background-color: #c0c0c0;
                border: 1px solid black;
            }
        """)
        input_layout = QVBoxLayout(input_frame)
        input_layout.setContentsMargins(12, 12, 12, 12)

        # Checkboxes inside input_frame
        checkbox_row = QHBoxLayout()
        simulate_checkbox = QCheckBox("Simulate base curve")
        base_curve_checkbox = QCheckBox("Built in base curve")
        simulate_checkbox.setChecked(True)
        checkbox_row.addWidget(simulate_checkbox)
        checkbox_row.addWidget(base_curve_checkbox)
        input_layout.addLayout(checkbox_row)

        # Toggleable form inside frame
        self.meta_input_widget = QWidget()
        meta_form_layout = QFormLayout(self.meta_input_widget)
        morning = QLineEdit(self.last_monthly_electricity_demand_inputs.get("morning_peak", "7"))
        evening = QLineEdit(self.last_monthly_electricity_demand_inputs.get("evening_peak", "19"))
        dip = QLineEdit(self.last_monthly_electricity_demand_inputs.get("dip_hour", "14"))
        meta_form_layout.addRow("Morning peak hour", morning)
        meta_form_layout.addRow("Evening peak hour", evening)
        meta_form_layout.addRow("Dip hour", dip)
        input_layout.addWidget(self.meta_input_widget)

        layout.addWidget(input_frame)

        # Checkbox toggle logic
        def toggle_checkboxes(source):
            if source == "simulate":
                simulate_checkbox.setChecked(True)
                base_curve_checkbox.setChecked(False)
                self.meta_input_widget.show()
            else:
                base_curve_checkbox.setChecked(True)
                simulate_checkbox.setChecked(False)
                self.meta_input_widget.hide()

        simulate_checkbox.clicked.connect(lambda: toggle_checkboxes("simulate"))
        base_curve_checkbox.clicked.connect(lambda: toggle_checkboxes("base"))

        # Scroll for monthly inputs
        scroll_content = QWidget()
        scroll_form = QFormLayout(scroll_content)

        self.monthly_inputs = {}

        for i in range(12):
            m = i + 1
            key = f"month_{m}"
            field = QLineEdit(self.last_monthly_electricity_demand_inputs.get(key, ""))
            self.monthly_inputs[key] = field
            scroll_form.addRow(f"Month {m} - Electricity (kWh)", field)


        scroll_frame = QFrame()
        scroll_frame.setStyleSheet("""
            QFrame {
                border: 1px solid black;
                background-color: white;
            }
            QLabel {
                font-size: 12px;
                font-weight: bold;
                border: none;
            }
        """)
       
        scroll_frame_layout = QVBoxLayout(scroll_frame)
        scroll_frame_layout.setContentsMargins(0, 0, 0, 0)
       
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(scroll_content)
        scroll.setStyleSheet("background-color: white;")
        scroll_frame_layout.addWidget(scroll)
        
        layout.addWidget(scroll_frame)

        # Save button
        save_btn = QPushButton("Save")
        save_btn.setStyleSheet(GenerationPopupHandler.style)
        save_btn.clicked.connect(lambda: (
            self._save_monthly(
                morning.text(),
                evening.text(),
                dip.text(),
                simulate_checkbox.isChecked(),
                dialog
            )
        ))
        layout.addWidget(save_btn, alignment=Qt.AlignRight)

        dialog.exec()

    def _save_monthly(self, morning, evening, dip, simulate_enabled, dialog):
        if simulate_enabled:
            self.last_monthly_electricity_demand_inputs["morning_peak"] = morning
            self.last_monthly_electricity_demand_inputs["evening_peak"] = evening
            self.last_monthly_electricity_demand_inputs["dip_hour"] = dip

            for key, widget in self.monthly_inputs.items():
                self.last_monthly_electricity_demand_inputs[key] = widget.text()

            self.electricity_demand_data_monthly = self.electricity_simulator.simulate_monthly(self.last_monthly_electricity_demand_inputs,
                                                                                               noise=False)
            self.workspace_manager.update("Data", "Monthly Electricity Data", self.electricity_demand_data_monthly)
            self.workspace_manager.update("Input", "Monthly Electricity Inputs", self.last_monthly_electricity_demand_inputs)
            self.workspace_manager.show_success("Monthly electricity inputs and data saved successfully!")
            dialog.accept()
        else:
            for key, widget in self.monthly_inputs.items():
                self.last_monthly_base_electricity_demand_inputs[key] = widget.text()

            self.electricity_demand_data_monthly = self.electricity_simulator.simulate_monthly(
                self.last_monthly_base_electricity_demand_inputs,
                use_base_curve= True,
                noise = False)
            self.workspace_manager.update("Data", "Monthly Electricity Data", self.electricity_demand_data_monthly)
            self.workspace_manager.update("Input", "Monthly Electricity Inputs", self.last_monthly_base_electricity_demand_inputs)
            self.workspace_manager.show_success("Monthly electricity inputs saved (base curve mode).")
            dialog.accept()

    def show_upload_popup(self):
        dialog = QDialog(self.parent)
        remove_qt_help_button(dialog)
        dialog.setWindowTitle("Upload Electricity Demand - CSV")
        dialog.setFixedSize(360, 360)

        main_layout = QVBoxLayout(dialog)

        # Framed section (instructions + mode)
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                border: 2px solid black;
                background-color: white;
            }
            QLabel {
                font-size: 12px;
                font-weight: bold;
                border: none;
            }
        """)
        frame_layout = QVBoxLayout(frame)
        frame_layout.setContentsMargins(12, 12, 12, 12)
        frame_layout.setSpacing(10)

        # Instruction label (deterministic + stochastic)
        description = QLabel("""
            <b>CSV Format:</b><br>
            - 8760 rows representing hourly electricity demand.<br>
            - <u>Deterministic:</u> Single column named <i>electricity_demand</i> in kWh (decimal “123.45” or “123,45”).<br>
            - <u>Stochastic:</u> 5 columns side-by-side named
              <i>electricity_demand1</i>, <i>electricity_demand2</i>, <i>electricity_demand3</i>, <i>electricity_demand4</i>, <i>electricity_demand5</i> (each 8760 values).<br>
        """)
        description.setWordWrap(True)
        frame_layout.addWidget(description)

        # Separator line
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        frame_layout.addWidget(line)

        # Mode selection: Deterministic vs Stochastic
        mode_layout = QHBoxLayout()
        deterministic_cb = QCheckBox("Deterministic")
        stochastic_cb = QCheckBox("Stochastic")

        # Ensure memory dict exists
        if not hasattr(self, "last_electricity_upload_inputs") or self.last_electricity_upload_inputs is None:
            self.last_electricity_upload_inputs = {}

        # Restore last selected mode (default deterministic)
        deterministic_cb.setChecked(self.last_electricity_upload_inputs.get("mode", "deterministic") == "deterministic")
        stochastic_cb.setChecked(self.last_electricity_upload_inputs.get("mode", "deterministic") == "stochastic")

        deterministic_cb.setStyleSheet(GenerationPopupHandler.check_style)
        stochastic_cb.setStyleSheet(GenerationPopupHandler.check_style)

        # Exclusive group so only one can be active
        mode_group = QButtonGroup(dialog)
        mode_group.setExclusive(True)
        mode_group.addButton(deterministic_cb)
        mode_group.addButton(stochastic_cb)

        mode_layout.addWidget(deterministic_cb)
        mode_layout.addWidget(stochastic_cb)
        frame_layout.addLayout(mode_layout)

        # Add the full frame to the main layout
        main_layout.addWidget(frame)

        # Upload button (outside the frame)
        upload_btn = QPushButton("Select CSV File")
        upload_btn.setStyleSheet(GenerationPopupHandler.style)
        main_layout.addWidget(upload_btn, alignment=Qt.AlignRight)

        def electricity_file_upload():
            selected_mode = "stochastic" if stochastic_cb.isChecked() else "deterministic"

            file_path, _ = QFileDialog.getOpenFileName(dialog, "Select CSV File", "", "CSV Files (*.csv)")
            if file_path:
                # Call correct uploader based on mode
                if selected_mode == "deterministic":
                    self.electricity_uploaded_data = self.uploader.upload_electricity_data(file_path)
                    self.workspace_manager.update("Data", "Uploaded Electricity Data", self.electricity_uploaded_data)
                    self.workspace_manager.update("Input", "Electricity Upload Inputs", self.last_electricity_upload_inputs, coordinates=False)
                else:
                    self.electricity_uploaded_data = self.uploader.upload_electricity_data_stochastic(file_path)
                    self.workspace_manager.update("Data", "Uploaded Electricity Data (stochastic)", self.electricity_uploaded_data)
                    self.workspace_manager.update("Input", "Electricity Upload Inputs (stochastic)", self.last_electricity_upload_inputs, coordinates=False)

                # Save last inputs including mode
                self.last_electricity_upload_inputs.update({
                    "mode": selected_mode
                })

                # Workspace updates
                self.workspace_manager.show_success("Uploaded Electricity data saved successfully!")
                dialog.accept()

        upload_btn.clicked.connect(electricity_file_upload)
        dialog.exec()


    def _show_yearly_help(self, parent):
        dlg = QDialog(parent)
        remove_qt_help_button(dlg)
        dlg.setWindowTitle("Simulate Yearly Electricity Demand Input - Help")
        dlg.setFixedSize(350, 320)
        layout = QVBoxLayout(dlg)
        text = QLabel("""
            <b>Simulate yearly electricity demand – Input Help</b><br><br>
            <b>Simulate base curve</b><br><br>
            <b>Annual electricity demand:</b> Total electricity consumption over the year.<br>
            <b>Morning peak hour:</b> Hour of highest usage in the morning.<br>
            <b>Evening peak hour:</b> Evening highest usage hour.<br>
            <b>Dip hour:</b> Time when usage is lowest.</b><br><br>
            <b>Built in base curve</b><br><br>
            <b>Annual electricity demand:</b> Total electricity consumption over the year.<br>
            <b>Uses predifined daily consumption curve.<br>
        """)
        text.setWordWrap(True)
        layout.addWidget(text)
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(GenerationPopupHandler.style)
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)
        dlg.exec()

    def _show_monthly_help(self, parent):
        dlg = QDialog(parent)
        remove_qt_help_button(dlg)
        dlg.setWindowTitle("Simulate Monthly Electricity Demand Input - Help")
        dlg.setFixedSize(350, 320)
        layout = QVBoxLayout(dlg)
        msg = QLabel("""
            <b>Simulate monthly electricity demand – Input Help</b><br><br>
            <b>Simulate base curve</b><br><br>
            <b>Morning peak hour:</b> Hour of highest usage in the morning.<br>
            <b>Evening peak hour:</b> Evening highest usage hour.<br>
            <b>Dip hour:</b> Time when usage is lowest.<br>
            <b>Enter estimated electricity demand for each month.</b><br><br>
            <b>Built in base curve</b><br><br>
            <b>Uses predifined daily consumption curve.<br>
            <b>Enter estimated electricity demand for each month.<br>
             """)
        msg.setWordWrap(True)
        layout.addWidget(msg)
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(GenerationPopupHandler.style)
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)
        dlg.exec()


class PricePopupHandler:
    last_price_inputs_country = {
        "buyback": "0.6",
        "selected_country": "Croatia"
    }
    last_price_inputs_dual = {
        "buyback": "0.6",
        "dual_day": "0.2",
        "dual_night": "0.1",
        "dual_start": "7",
        "dual_end": "22"
    }
    last_price_inputs_single = {
        "buyback": "0.6",
        "one_tariff": "0.15"
    }

    last_price_inputs_upload = {
        "buyback": "0.6",
        }

    def __init__(self, parent, toolbar, workspace_manager):
        self.parent = parent
        self.toolbar = toolbar
        self.price_generator = PriceGenerator(self.parent)
        self.price_data_country = None
        self.price_data_dual = None
        self.price_data_single = None
        self.workspace_manager = workspace_manager
        self.uploader = DataUpload(parent)

    def show_popup(self, pos=None):
        popup = QFrame(self.parent)
        popup.setWindowFlags(Qt.Popup)
        popup.setFixedSize(280, 220)
        popup.setStyleSheet("background-color: white; border: 1px solid #ccc;")

        layout = QVBoxLayout(popup)

        country_btn = QPushButton("Price select by country")
        dual_btn = QPushButton("Dual tariff")
        one_btn = QPushButton("Single tariff")
        upload_btn = QPushButton("Upload Price Data")

        for btn in [country_btn, dual_btn, one_btn, upload_btn]:
            btn.setStyleSheet(""" QPushButton {padding: 10px; font-size: 14px;} QPushButton:hover {background-color: #f0f0f0;}""")

        country_btn.clicked.connect(lambda: (popup.close(), self.show_country_price_popup()))
        dual_btn.clicked.connect(lambda: (popup.close(), self.show_dual_tariff_popup()))
        one_btn.clicked.connect(lambda: (popup.close(), self.show_one_tariff_popup()))
        upload_btn.clicked.connect(lambda: (popup.close(), self.show_upload_popup()))

        layout.addWidget(country_btn)
        layout.addWidget(dual_btn)
        layout.addWidget(one_btn)
        layout.addWidget(upload_btn)

        if pos:
            popup.move(pos)

        QApplication.instance().installEventFilter(self.parent)
        popup.show()

    def show_upload_popup(self):
        dialog = QDialog(self.parent)
        remove_qt_help_button(dialog)
        dialog.setWindowTitle("Upload Price Data - CSV")
        dialog.setFixedSize(360, 360)

        main_layout = QVBoxLayout(dialog)

        # Framed section (instructions + form)
        frame = QFrame()
        frame.setStyleSheet("""
            QFrame {
                border: 2px solid black;
                background-color: white;
            }
            QLabel {
                font-size: 12px;
                font-weight: bold;
                border: none;
            }
        """)
        frame_layout = QFormLayout(frame)
        frame_layout.setContentsMargins(12, 12, 12, 12)
        frame_layout.setSpacing(10)

        # Instruction label (deterministic + stochastic)
        description = QLabel("""
            <b>CSV Format:</b><br>
            - 8760 rows representing hourly buy price data.<br>
            - <u>Deterministic:</u> Single column named <i>buy_price</i> in €/kWh (decimal “123.45” or “123,45”).<br>
            - <u>Stochastic:</u> 5 columns side-by-side named
              <i>buy_price1</i>, <i>buy_price2</i>, <i>buy_price3</i>, <i>buy_price4</i>, <i>buy_price5</i>.<br>
        """)
        description.setWordWrap(True)
        frame_layout.addRow(description)

        # Separator line
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        frame_layout.addRow(line)

        # Mode selection: Deterministic vs Stochastic
        mode_layout = QHBoxLayout()
        deterministic_cb = QCheckBox("Deterministic")
        stochastic_cb = QCheckBox("Stochastic")

        # Ensure dict exists
        if not hasattr(self, "last_price_inputs_upload") or self.last_price_inputs_upload is None:
            self.last_price_inputs_upload = {}

        # Restore last selected mode (default deterministic)
        deterministic_cb.setChecked(self.last_price_inputs_upload.get("mode", "deterministic") == "deterministic")
        stochastic_cb.setChecked(self.last_price_inputs_upload.get("mode", "deterministic") == "stochastic")

        deterministic_cb.setStyleSheet(GenerationPopupHandler.check_style)
        stochastic_cb.setStyleSheet(GenerationPopupHandler.check_style)

        # Exclusive group
        mode_group = QButtonGroup(dialog)
        mode_group.setExclusive(True)
        mode_group.addButton(deterministic_cb)
        mode_group.addButton(stochastic_cb)

        mode_layout.addWidget(deterministic_cb)
        mode_layout.addWidget(stochastic_cb)
        frame_layout.addRow(mode_layout)

        # Buy-back factor input
        buyback_input = QLineEdit(self.last_price_inputs_upload.get("buyback", ""))
        frame_layout.addRow("Buy-back factor:", buyback_input)

        # Add the full frame
        main_layout.addWidget(frame)

        # Upload button
        upload_btn = QPushButton("Select CSV File")
        upload_btn.setStyleSheet(GenerationPopupHandler.style)
        main_layout.addWidget(upload_btn, alignment=Qt.AlignRight)

        def price_file_upload(buyback):
            selected_mode = "stochastic" if stochastic_cb.isChecked() else "deterministic"

            file_path, _ = QFileDialog.getOpenFileName(dialog, "Select CSV File", "", "CSV Files (*.csv)")
            if file_path:
                # Save inputs
                self.last_price_inputs_upload.update({
                    "buyback": buyback,
                    "mode": selected_mode
                })

                # Call correct uploader
                if selected_mode == "deterministic":
                    self.price_uploaded_data = self.uploader.upload_price_data(file_path)
                    self.workspace_manager.update("Data", "Uploaded Price Data", self.price_uploaded_data)
                    self.workspace_manager.update("Input", "Uploaded Price Inputs", self.last_price_inputs_upload)

                else:
                    self.price_uploaded_data = self.uploader.upload_price_data_stochastic(file_path)
                    self.workspace_manager.update("Data", "Uploaded Price Data (stochastic)", self.price_uploaded_data)
                    self.workspace_manager.update("Input", "Uploaded Price Inputs (stochastic)", self.last_price_inputs_upload)

                # Workspace updates
                self.workspace_manager.show_success("Uploaded Price data saved successfully!")
                dialog.accept()

        upload_btn.clicked.connect(lambda: price_file_upload(buyback_input.text()))
        dialog.exec()


    def show_country_price_popup(self):
        dialog = QDialog(self.parent)
        remove_qt_help_button(dialog)
        dialog.setWindowTitle("Price Data Country Input")
        dialog.setFixedSize(400, 330)
        dialog.setModal(True)
        main_layout = QVBoxLayout(dialog)

        top_row = QHBoxLayout()
        top_row.addStretch()
        help_btn = QPushButton("?")
        help_btn.setFixedSize(35, 35)
        help_btn.setStyleSheet(GenerationPopupHandler.style)
        help_btn.clicked.connect(lambda: self.show_country_help(dialog))
        top_row.addWidget(help_btn)
        main_layout.addLayout(top_row)

        # Form layout
        input_frame = QFrame()
        input_frame.setStyleSheet("""QFrame {border: 2px solid black;background-color: white;} QLabel {border: none; font-size: 12px; font-weight: bold;}""")
        input_layout = QVBoxLayout(input_frame)
        input_layout.setContentsMargins(12, 12, 12, 12)

        form_layout = QFormLayout()

        buyback_input = QLineEdit(self.last_price_inputs_country["buyback"])
        form_layout.addRow("Buy-back factor:", buyback_input)

        # Separator line
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        form_layout.addRow(line)

        country_list = QListWidget()
        country_list.setStyleSheet("""
                    QListWidget {
                        background-color: white;
                        font-size: 12px;
                        font-weight: bold;
                        border: 1px solid black;
                        padding: 4px;
                        outline: none;
                    }
                    QListWidget::item {
                        padding: 6px;
                    }
                    QListWidget::item:hover {
                        background-color: #e0e0e0; /* light gray on hover */
                        outline: none;
                    }
                    QListWidget::item:selected {
                        background-color: #c0c0c0; /* darker gray when selected */
                        color: black;
                        outline: none;
                    }
                """)
        country_list.addItems(["Croatia", "Spain", "Italy", "Germany", "Hungary"])
        country_list.setCurrentRow(0)

        form_layout.addRow("Select country:", country_list)

        input_layout.addLayout(form_layout)
        main_layout.addWidget(input_frame)

        save_btn = QPushButton("Save")
        save_btn.setStyleSheet(GenerationPopupHandler.style)
        save_btn.clicked.connect(lambda: (
            self._save_country(buyback_input.text(), country_list.currentItem().text(), dialog)
        ))
        main_layout.addWidget(save_btn, alignment=Qt.AlignRight)
        dialog.exec()

    def _save_country(self, buyback, country, dialog):
        self.last_price_inputs_country.update({
            "buyback": buyback,
            "selected_country": country
        })

        self.price_data_country = self.price_generator.generate_price_country(self.last_price_inputs_country, noise = False)

        self.workspace_manager.update("Input", "Country Price Inputs", self.last_price_inputs_country, coordinates=False)
        self.workspace_manager.update("Data", "Country Price Data", self.price_data_country)
        self.workspace_manager.show_success("Country price inputs and data saved successfully!")

        dialog.accept()


    def show_dual_tariff_popup(self):
        dialog = QDialog(self.parent)
        remove_qt_help_button(dialog)
        dialog.setWindowTitle("Price Data Dual Tariff Input")
        dialog.setFixedSize(400, 320)
        dialog.setModal(True)
        main_layout = QVBoxLayout(dialog)

        top_row = QHBoxLayout()
        top_row.addStretch()
        help_btn = QPushButton("?")
        help_btn.setFixedSize(35, 35)
        help_btn.setStyleSheet(GenerationPopupHandler.style)
        help_btn.clicked.connect(lambda: self.show_dual_help(dialog))
        top_row.addWidget(help_btn)
        main_layout.addLayout(top_row)

        # Form layout
        input_frame = QFrame()
        input_frame.setStyleSheet("""QFrame {border: 2px solid black;background-color: white;} QLabel {border: none; font-size: 12px; font-weight: bold;}""")
        input_layout = QVBoxLayout(input_frame)
        input_layout.setContentsMargins(12, 12, 12, 12)

        form_layout = QFormLayout()

        buyback_input = QLineEdit(self.last_price_inputs_dual["buyback"])
        form_layout.addRow("Buy-back Factor:", buyback_input)

        # Separator line
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        form_layout.addRow(line)

        day = QLineEdit(self.last_price_inputs_dual["dual_day"])
        night = QLineEdit(self.last_price_inputs_dual["dual_night"])
        start = QLineEdit(self.last_price_inputs_dual["dual_start"])
        end = QLineEdit(self.last_price_inputs_dual["dual_end"])

        form_layout.addRow("Daily tariff (€/kWh):", day)
        form_layout.addRow("Nightly tariff (€/kWh):", night)
        form_layout.addRow("Daily tariff start hour:", start)
        form_layout.addRow("Daily tariff end hour:", end)

        input_layout.addLayout(form_layout)
        main_layout.addWidget(input_frame)

        save_btn = QPushButton("Save")
        save_btn.setStyleSheet(GenerationPopupHandler.style)
        save_btn.clicked.connect(lambda: (
            self._save_dual(
                buyback_input.text(), day.text(), night.text(), start.text(), end.text(), dialog
            )
        ))
        main_layout.addWidget(save_btn, alignment=Qt.AlignRight)
        dialog.exec()

    def _save_dual(self, buyback,  day, night, start, end, dialog):
        self.last_price_inputs_dual.update({
            "buyback": buyback,
            "dual_day": day,
            "dual_night": night,
            "dual_start": start,
            "dual_end": end
        })

        self.price_data_dual = self.price_generator.generate_price_dual_tariff(self.last_price_inputs_dual, noise = False)

        self.workspace_manager.update("Input", "Dual Tariff Inputs", self.last_price_inputs_dual, coordinates=False)
        self.workspace_manager.update("Data", "Dual Tariff Data", self.price_data_dual)
        self.workspace_manager.show_success("Dual tariff price inputs and data saved successfully!")

        dialog.accept()

    def show_one_tariff_popup(self):
        dialog = QDialog(self.parent)
        remove_qt_help_button(dialog)
        dialog.setWindowTitle("Price Data Single Tariff Input")
        dialog.setFixedSize(400, 230)
        dialog.setModal(True)
        main_layout = QVBoxLayout(dialog)

        top_row = QHBoxLayout()
        top_row.addStretch()
        help_btn = QPushButton("?")
        help_btn.setFixedSize(35, 35)
        help_btn.setStyleSheet(GenerationPopupHandler.style)
        help_btn.clicked.connect(lambda: self.show_one_tariff_help(dialog))
        top_row.addWidget(help_btn)
        main_layout.addLayout(top_row)

        # Form layout
        input_frame = QFrame()
        input_frame.setStyleSheet("""QFrame {border: 2px solid black;background-color: white;} QLabel {border: none; font-size: 12px; font-weight: bold;}""")
        input_layout = QVBoxLayout(input_frame)
        input_layout.setContentsMargins(12, 12, 12, 12)

        form_layout = QFormLayout()

        buyback_input = QLineEdit(self.last_price_inputs_single["buyback"])
        form_layout.addRow("Buy-back Factor:", buyback_input)

        # Separator line
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        form_layout.addRow(line)

        flat = QLineEdit(self.last_price_inputs_single["one_tariff"])

        form_layout.addRow("Single tariff (€/kWh):", flat)

        input_layout.addLayout(form_layout)
        main_layout.addWidget(input_frame)

        save_btn = QPushButton("Save")
        save_btn.setStyleSheet(GenerationPopupHandler.style)
        save_btn.clicked.connect(lambda: (
            self._save_single(
                buyback_input.text(), flat.text(), dialog
            )
        ))
        main_layout.addWidget(save_btn, alignment=Qt.AlignRight)
        dialog.exec()

    def _save_single(self, buyback, flat, dialog):
        self.last_price_inputs_single.update({
            "buyback": buyback,
            "one_tariff": flat
        })

        self.price_data_single = self.price_generator.generate_price_single_tariff(self.last_price_inputs_single, noise = False)

        self.workspace_manager.update("Input", "Single Tariff Inputs", self.last_price_inputs_single, coordinates=False)
        self.workspace_manager.update("Data", "Single Tariff Data", self.price_data_single)
        self.workspace_manager.show_success("Single tariff price inputs and data saved successfully!")

        dialog.accept()

    def show_country_help(self, parent):
        dlg = QDialog(parent)
        remove_qt_help_button(dlg)
        dlg.setWindowTitle("Price Data Country Input - Help")
        dlg.setFixedSize(350, 260)
        layout = QVBoxLayout(dlg)
        msg = QLabel("""
            <b>Price Data Country – Input Help</b><br><br>
            <b>Buy-back Factor:</b> Proportion of price at which excess electricity is sold back to grid. Ranges 0 to 1<br><br>
            <b>Select by Country:</b> Load predefined electricity prices from ENTSO-E for selected country for representative year 2023.
        """)
        msg.setWordWrap(True)
        layout.addWidget(msg)
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(GenerationPopupHandler.style)
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)
        dlg.exec()

    def show_dual_help(self, parent):
        dlg = QDialog(parent)
        remove_qt_help_button(dlg)
        dlg.setWindowTitle("Price Data Dual Tariff Input - Help")
        dlg.setFixedSize(350, 300)
        layout = QVBoxLayout(dlg)
        msg = QLabel("""
            <b>Price Data Dual Tariff – Input Help</b><br><br>
            <b>Buy-back Factor:</b> Proportion of price at which excess electricity is sold back to grid. Ranges 0 to 1<br><br>
            <b>Daily tariff:</b> Electricity price for daytime.<br>
            <b>Nightly tariff:</b> Electricity price for nighttime.<br>
            <b>Daily tariff start hour:</b> Starting hour of daily tariff.<br>
            <b>Daily tariff end hour:</b> Starting hour of nightly tariff.<br>
        """)
        msg.setWordWrap(True)
        layout.addWidget(msg)
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(GenerationPopupHandler.style)
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)
        dlg.exec()

    def show_one_tariff_help(self, parent):
        dlg = QDialog(parent)
        remove_qt_help_button(dlg)
        dlg.setWindowTitle("Price Data Single Tariff Input - Help")
        dlg.setFixedSize(350, 260)
        layout = QVBoxLayout(dlg)
        msg = QLabel("""
            <b>Price Data Single Tariff – Input Help</b><br><br>
            <b>Buy-back Factor:</b> Proportion of price at which excess electricity is sold back to grid. Ranges 0 to 1<br><br>
            <b>Single tariff:</b> A fixed electricity price is used for the entire day, without any changes.<br>
        """)
        msg.setWordWrap(True)
        layout.addWidget(msg)
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(GenerationPopupHandler.style)
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)
        dlg.exec()

class EmissionsPopupHandler:
    checkbox_style = """
        QCheckBox {
            font-weight: bold;
            font-size: 12px;
        }
    """

    last_emission_fuel_inputs = {
        'emission_price': '0.07',
        'fuel_name': '',
        'emission_metric': '',
        'emission_value': '',
        'system_efficiency': '',
        "fuel_consumption": '',
        'mode': '',
    }

    last_emission_country_inputs = {
        'emission_price': '0.07',
        'emission_metric': '',
        'emission_value': '',
        'mode': 'country',
    }

    last_emission_system_inputs = {
        'emission_price': '',
        'fuel_name': '',
        'emission_metric': "",
        'emission_value': '',
        'system_efficiency': '',
        'mode': 'system',
    }

    last_emission_custom_inputs = {
        'emission_price': '',
        'emission_metric': "",
        'emission_value': '',
        'system_efficiency':'',
        'mode': 'custom',
    }

    last_external_cost_country_inputs = {
        'mode': 'External cost country',
        'country': '',
        'external_pm_cost': '',
        'external_ht_cost': ''
    }

    last_external_cost_fuel_inputs = {
        'mode': 'External cost production',
        'fuel': '',
        'region':'',
        'external_pm_cost':'',
        'external_ht_cost': ''
    }

    last_external_cost_manual_inputs = {
        'mode': 'External cost manual',
        'external_pm_cost': '',
        'external_ht_cost': ''
    }

    def __init__(self, parent, toolbar, workspace_manager):
        self.parent = parent
        self.toolbar = toolbar
        self.workspace_manager = workspace_manager
        self.validate = Technology(self.parent)

        self.co2_loader = CO2DataLoader()
        base_dir = "Co2"
        
        co2_country_path = resource_path(os.path.join(base_dir, "co2_country.xlsx"))
        co2_fuels_path   = resource_path(os.path.join(base_dir, "co2_fules.xlsx"))
        co2_prod_path    = resource_path(os.path.join(base_dir, "co2_production_type.xlsx"))
        
        self.co2_by_country = self.co2_loader.get_co2_by_country(co2_country_path)
        self.co2_fuels_tj, self.co2_fuels_units = self.co2_loader.get_co2_by_fuel(co2_fuels_path)
        self.co2_by_production = self.co2_loader.get_co2_by_production_type(co2_prod_path)
        
        self.external_cost_loader = ExternalCostDataLoader()
        ext_country_path = resource_path(os.path.join(base_dir, "External_cost_country_electricity.xlsx"))
        ext_fuel_path    = resource_path(os.path.join(base_dir, "External_cost_production_type_electricity.xlsx"))
        
        self.external_cost_country = self.external_cost_loader.get_external_cost_by_country(ext_country_path)
        self.external_cost_fuel_type = self.external_cost_loader.get_external_cost_by_fuel_type(ext_fuel_path)

        self.last_co2_price = self.last_emission_fuel_inputs.get('emission_price', '0.07')

    # Top-level popup
    def show_popup(self, pos=None):
        dialog = QDialog(self.parent)
        remove_qt_help_button(dialog)
        dialog.setWindowTitle("Emission Inputs")
        dialog.setFixedSize(550, 350)
        dialog.setModal(True)

        dialog.setStyleSheet("""
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
            QGroupBox {
                font-weight: bold;
            }
            QScrollArea {
                border: 2px solid black;
            }
        """)

        layout = QVBoxLayout(dialog)

        # Help button for the main emissions popup
        top_row = QHBoxLayout()
        top_row.addStretch()
        help_btn = QPushButton("?")
        help_btn.setFixedSize(35, 35)
        help_btn.setStyleSheet(GenerationPopupHandler.style)
        help_btn.clicked.connect(lambda: self.show_emissions_main_help(dialog))
        top_row.addWidget(help_btn)
        layout.addLayout(top_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        layout.addWidget(scroll)

        container = QWidget()
        container_layout = QVBoxLayout(container)
        scroll.setWidget(container)

        group_box = QGroupBox("Emissions by Electricity consumption from Grid")
        group_layout = QVBoxLayout(group_box)

        # CO2 Price Input inside group box
        co2_price_row = QHBoxLayout()
        co2_price_label = QLabel("CO₂ emissions price (€/kgCO₂):")
        co2_price_label.setStyleSheet("font-weight: bold; font-size: 12px;")

        self.co2_price_input = QLineEdit()
        self.co2_price_input.setText(self.last_emission_fuel_inputs['emission_price'])
        self.co2_price_input.setAlignment(Qt.AlignLeft)

        co2_price_row.addWidget(co2_price_label)
        co2_price_row.addWidget(self.co2_price_input)
        group_layout.addLayout(co2_price_row)

        self.fuel_check = QCheckBox("Emissions by Electricity generation based on fuel type")
        self.country_check = QCheckBox("Emissions by Electricity generation based on country")
        self.system_check = QCheckBox("Emissions by Electricity generation based on system type")
        self.custom_check = QCheckBox("Emissions by Electricity generation with custom input")

        self.fuel_tj_check = QCheckBox("Fuels in (kgCO₂/kWh)")
        self.fuel_unit_check = QCheckBox("Fuels in (kgCO₂/physical units)")

        for box in [self.fuel_tj_check, self.fuel_unit_check]:
            box.hide()

        # Child indent
        indent_layout = QVBoxLayout()
        indent_layout.setContentsMargins(25, 0, 0, 0)
        indent_layout.addWidget(self.fuel_tj_check)
        indent_layout.addWidget(self.fuel_unit_check)

        # Top-level group logic
        self.fuel_check.stateChanged.connect(lambda state: self.handle_check('fuel', state))
        self.country_check.stateChanged.connect(lambda state: self.handle_check('country', state))
        self.system_check.stateChanged.connect(lambda state: self.handle_check('system', state))
        self.custom_check.stateChanged.connect(lambda state: self.handle_check('custom', state))

        # Subcheck logic
        self.fuel_tj_check.stateChanged.connect(lambda state, sender=self.fuel_tj_check: self._subcheck_changed(state, sender))
        self.fuel_unit_check.stateChanged.connect(lambda state, sender=self.fuel_unit_check: self._subcheck_changed(state, sender))

        group_layout.addWidget(self.fuel_check)
        group_layout.addLayout(indent_layout)
        group_layout.addWidget(self.country_check)
        group_layout.addWidget(self.system_check)
        group_layout.addWidget(self.custom_check)
        container_layout.addWidget(group_box)

        # External Costs Group
        external_group = QGroupBox("External costs by Electricity consumption from Grid")
        external_layout = QVBoxLayout(external_group)

        self.external_country_check = QCheckBox("External cost based on country")
        self.external_fuel_check = QCheckBox("External cost based on fuel type")
        self.external_manual_check = QCheckBox("External cost with custom input")

        external_layout.addWidget(self.external_country_check)
        external_layout.addWidget(self.external_fuel_check)
        external_layout.addWidget(self.external_manual_check)
        container_layout.addWidget(external_group)

        # Behave like radio buttons
        self.external_country_check.stateChanged.connect(lambda state: self.handle_external_check("country", state))
        self.external_fuel_check.stateChanged.connect(lambda state: self.handle_external_check("production", state))
        self.external_manual_check.stateChanged.connect(lambda state: self.handle_external_check("manual", state))

        # Close button
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(GenerationPopupHandler.style)
        close_btn.clicked.connect(lambda: self._save_and_close_price(dialog))
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

        dialog.exec_()

    # Toggle handlers
    def handle_check(self, selected, state):
        if state != Qt.Checked:
            return

        box_map = {
            'fuel': self.fuel_check,
            'country': self.country_check,
            'system': self.system_check,
            'custom': self.custom_check,
        }
        for key, box in box_map.items():
            box.blockSignals(True)
            box.setChecked(key == selected)
            box.blockSignals(False)

        # Toggle sub-checkboxes for fuel
        if selected == 'fuel':
            self.fuel_tj_check.show()
            self.fuel_unit_check.show()
        else:
            self.fuel_tj_check.hide()
            self.fuel_unit_check.hide()
            self.fuel_tj_check.setChecked(False)
            self.fuel_unit_check.setChecked(False)

        # Branch to sub-popups
        if selected == 'country':
            self.show_country_popup()
        elif selected == 'system':
            self.show_production_popup()
        elif selected == 'custom':
            self.show_custom_popup()

    def _subcheck_changed(self, state, sender):
        if state != Qt.Checked:
            return
        if sender == self.fuel_tj_check:
            self.fuel_unit_check.blockSignals(True)
            self.fuel_unit_check.setChecked(False)
            self.fuel_unit_check.blockSignals(False)
            self.show_fuel_popup("tj")
        elif sender == self.fuel_unit_check:
            self.fuel_tj_check.blockSignals(True)
            self.fuel_tj_check.setChecked(False)
            self.fuel_tj_check.blockSignals(False)
            self.show_fuel_popup("unit")

    def handle_external_check(self, selected, state):
        if state != Qt.Checked:
            return

        box_map = {
            'country': self.external_country_check,
            'production': self.external_fuel_check,
            'manual': self.external_manual_check,
        }
        for key, box in box_map.items():
            box.blockSignals(True)
            box.setChecked(key == selected)
            box.blockSignals(False)

        if selected == 'country':
            self.show_external_country_popup()  
        elif selected == 'production':
            self.show_external_production_popup()  
        elif selected == 'manual':
            self.show_external_manual_popup()  

    # Shared helpers
    def _parse_and_store_price(self, parent_dialog=None):
        """Parse CO2 price and store into all last_* dicts."""
        val = self.co2_price_input.text()
        if not val:
            return True
        try:
            parsed = float(val)
            self.last_co2_price = f"{parsed:.5f}"
            self.last_emission_fuel_inputs['emission_price'] = self.last_co2_price
            self.last_emission_country_inputs['emission_price'] = self.last_co2_price
            self.last_emission_system_inputs['emission_price'] = self.last_co2_price
            self.last_emission_custom_inputs['emission_price'] = self.last_co2_price
            return True
        except ValueError:
            QMessageBox.warning(parent_dialog or self.parent, "Invalid Emission price Input", "Please enter a valid number.")
            return False

    def _save_and_close_price(self, dialog):
        if self._parse_and_store_price(dialog):
            dialog.accept()

    # Fuel popup
    def show_fuel_popup(self, mode="tj"):
        """
        Shows a popup listing fuels with emissions:
        'tj' -> kgCO₂/kWh, 'unit' -> kgCO₂ per physical units (consumption-based).
        """
        import pandas as pd
        data = self.co2_fuels_tj if mode == "tj" else self.co2_fuels_units
        title = "Fuels in (kgCO₂/kWh)" if mode == "tj" else "Fuels in (kgCO₂/physical units)"

        dialog = QDialog(self.parent)

        remove_qt_help_button(dialog)
        dialog.setWindowTitle(title)
        dialog.setFixedSize(400, 380)
        dialog.setModal(True)

        layout = QVBoxLayout(dialog)

        # Help
        top_row = QHBoxLayout()
        top_row.addStretch()
        help_btn = QPushButton("?")
        help_btn.setFixedSize(35, 35)
        help_btn.setStyleSheet(GenerationPopupHandler.style)
        help_btn.clicked.connect(lambda: self.show_emissions_fuel_help(dialog, mode))
        top_row.addWidget(help_btn)
        layout.addLayout(top_row)

        # Input field
        input_row = QHBoxLayout()
        input_label = QLabel("System Efficiency:" if mode == "tj" else "Yearly fuel consumption (liters or tons):")
        input_label.setStyleSheet("font-weight: bold; font-size: 12px;")

        input_field = QLineEdit()
        input_field.setPlaceholderText("e.g. 0.85" if mode == "tj" else "e.g. 1500")
        input_field.setAlignment(Qt.AlignLeft)

        if mode == "tj":
            validator = QDoubleValidator(0.0, 1.0, 4, input_field)
            validator.setNotation(QDoubleValidator.StandardNotation)
            input_field.setValidator(validator)

        if mode == "tj" and self.last_emission_fuel_inputs.get("system_efficiency"):
            input_field.setText(str(self.last_emission_fuel_inputs["system_efficiency"]))
        elif mode != "tj" and self.last_emission_fuel_inputs.get("fuel_consumption"):
            input_field.setText(str(self.last_emission_fuel_inputs["fuel_consumption"]))

        input_row.addWidget(input_label)
        input_row.addWidget(input_field)
        layout.addLayout(input_row)

        # Metric selector
        metric_label = QLabel("Select emission metric:")
        metric_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        metric_selector = QComboBox()
        metric_selector.setFixedWidth(150)
        metric_selector.setStyleSheet(GenerationPopupHandler.combo_style)
        metric_selector.addItems(["kg CO2", "kg CO2e", "kg CO2e incl, unox, carbon"])
        layout.addWidget(metric_label)
        layout.addWidget(metric_selector)

        # Fuel list
        fuel_list = QListWidget()
        fuel_list.setStyleSheet("""
            QListWidget {
                background-color: white;
                font-size: 12px;
                font-weight: bold;
                border: 1px solid black;
                padding: 4px;
                outline: none;
            }
            QListWidget::item { padding: 6px; }
            QListWidget::item:hover { background-color: #e0e0e0; }
            QListWidget::item:selected { background-color: #c0c0c0; color: black; }
        """)

        input_frame = QFrame()
        input_frame.setStyleSheet("""
            QFrame {border: 2px solid black; background-color: white;}
            QLabel {font-weight: bold;}
        """)
        input_layout = QVBoxLayout(input_frame)
        input_layout.addWidget(fuel_list)
        layout.addWidget(input_frame)

        metric_map = {
            "kg CO2": "kg_CO2",
            "kg CO2e": "kg_CO2e",
            "kg CO2e incl, unox, carbon": "kg_CO2e_incl_unox"
        }

        def update_fuel_list():
            fuel_list.clear()
            selected_metric = metric_map[metric_selector.currentText()]
            for fuel, values in data.items():
                val = values.get(selected_metric)
                display = f"{fuel} — {'N/A' if pd.isna(val) else f'{val:.5f}'}"
                fuel_list.addItem(display)

        metric_selector.currentTextChanged.connect(update_fuel_list)
        update_fuel_list()

        # Save
        save_btn = QPushButton("Save")
        save_btn.setStyleSheet(GenerationPopupHandler.style)
        save_btn.clicked.connect(lambda: self._save_fuel_emissions(dialog, fuel_list, input_field, metric_selector, mode))
        layout.addWidget(save_btn, alignment=Qt.AlignRight)

        dialog.exec_()

    def _save_fuel_emissions(self, dialog, fuel_list, input_field, metric_selector, mode):
        selected_item = fuel_list.currentItem()
        input_value = input_field.text()

        if not selected_item or not input_value:
            QMessageBox.warning(dialog, "Missing Input", "Please select a fuel and provide input.")
            return

        # Validate numeric fields
        try:
            numeric_value = float(input_value)
        except ValueError:
            QMessageBox.warning(dialog, "Invalid Input", "Please enter a valid number.")
            return

        # enforce 0–1 for efficiency when mode == "tj"
        if mode == "tj" and not (0.0 <= numeric_value <= 1.0):
            QMessageBox.warning(dialog, "Invalid Efficiency", "System efficiency must be between 0 and 1.")
            return


        if not self._parse_and_store_price(dialog):
            return

        fuel_text = selected_item.text().split(" — ")[0]
        try:
            emission_value = float(selected_item.text().split(" — ")[1])
        except (IndexError, ValueError):
            emission_value = None

        metric_label_str = metric_selector.currentText()

        # Store and update last dict
        if mode == "tj":
            self.last_emission_fuel_inputs["system_efficiency"] = numeric_value
            self.last_emission_fuel_inputs["fuel_consumption"] = ''
        else:
            self.last_emission_fuel_inputs["fuel_consumption"] = numeric_value
            self.last_emission_fuel_inputs["system_efficiency"] = ''

        self.last_emission_fuel_inputs = {
            'emission_price': self.last_co2_price,
            'fuel_name': fuel_text,
            'emission_metric': metric_label_str,
            'emission_value': emission_value,
            'system_efficiency': numeric_value if mode == 'tj' else '',
            'fuel_consumption': '' if mode == 'tj' else numeric_value,
            'mode': 'fuels in kWh' if mode == 'tj' else 'yearly fuel consumption',
        }

        self.workspace_manager.update("Input", "Emission Inputs", self.last_emission_fuel_inputs, coordinates=False)
        self.workspace_manager.show_success("Fuel emissions input saved successfully.")
        dialog.accept()

    # Country popup
    def show_country_popup(self):
        dialog = QDialog(self.parent)
        remove_qt_help_button(dialog)
        dialog.setWindowTitle("Emissions by Country")
        dialog.setFixedSize(400, 360)
        dialog.setModal(True)

        layout = QVBoxLayout(dialog)

        # Help
        top_row = QHBoxLayout()
        top_row.addStretch()
        help_btn = QPushButton("?")
        help_btn.setFixedSize(35, 35)
        help_btn.setStyleSheet(GenerationPopupHandler.style)
        help_btn.clicked.connect(lambda: self.show_emissions_country_help(dialog))
        top_row.addWidget(help_btn)
        layout.addLayout(top_row)

        # Metric selector
        metric_label = QLabel("Select emission metric:")
        metric_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        metric_selector = QComboBox()
        metric_selector.setFixedWidth(150)
        metric_selector.setStyleSheet(GenerationPopupHandler.combo_style)
        metric_selector.addItems([
            "Intermittent Gen",
            "Firm Gen/Consumption",
            "HV Grid Loss",
            "MV Grid Loss",
            "LV Grid Loss"
        ])
        layout.addWidget(metric_label)
        layout.addWidget(metric_selector)

        metric_key_map = {
            "Intermittent Gen": "Intermittent Gen (kgCO₂/kWh)",
            "Firm Gen/Consumption": "Firm Gen/Consumption (kgCO₂/kWh)",
            "HV Grid Loss": "HV Grid Loss (kgCO₂/kWh)",
            "MV Grid Loss": "MV Grid Loss (kgCO₂/kWh)",
            "LV Grid Loss": "LV Grid Loss (kgCO₂/kWh)",
        }

        # Country list
        country_list = QListWidget()
        country_list.setStyleSheet("""
            QListWidget {
                background-color: white;
                font-size: 12px;
                font-weight: bold;
                border: 1px solid black;
                padding: 4px;
                outline: none;
            }
            QListWidget::item { padding: 6px; }
            QListWidget::item:hover { background-color: #e0e0e0; }
            QListWidget::item:selected { background-color: #c0c0c0; color: black; }
        """)

        input_frame = QFrame()
        input_frame.setStyleSheet("""
            QFrame {border: 2px solid black; background-color: white;}
            QLabel {font-weight: bold;}
        """)
        input_layout = QVBoxLayout(input_frame)
        input_layout.addWidget(country_list)
        layout.addWidget(input_frame)

        def update_country_list():
            selected_label = metric_selector.currentText()
            full_key = metric_key_map.get(selected_label, "")
            country_list.clear()
            for country, values in self.co2_by_country.items():
                val = values.get(full_key, None)
                if isinstance(val, (float, int)):
                    display = f"{country} — {val:.5f}"
                else:
                    display = f"{country} — N/A"
                country_list.addItem(display)

        metric_selector.currentIndexChanged.connect(update_country_list)
        update_country_list()

        # Save
        save_btn = QPushButton("Save")
        save_btn.setStyleSheet(GenerationPopupHandler.style)
        save_btn.clicked.connect(lambda: self._save_country_emissions(dialog, country_list, metric_selector, metric_key_map))
        layout.addWidget(save_btn, alignment=Qt.AlignRight)

        dialog.exec_()

    def _save_country_emissions(self, dialog, country_list, metric_selector, metric_key_map):
        selected = country_list.currentItem()
        if not selected:
            QMessageBox.warning(dialog, "Missing Selection", "Please select a country.")
            return

        if not self._parse_and_store_price(dialog):
            return

        metric_label_str = metric_selector.currentText()
        full_key = metric_key_map.get(metric_label_str, "")
        country_text = selected.text().split(" — ")[0]
        try:
            emission_value = float(selected.text().split(" — ")[1])
        except (IndexError, ValueError):
            emission_value = None

        self.last_emission_country_inputs = {
            'emission_price': self.last_co2_price,
            'emission_metric': full_key,
            'emission_value': emission_value,
            'mode': 'country',
            'country': country_text
        }

        self.workspace_manager.update("Input", "Emission Inputs", self.last_emission_country_inputs, coordinates=False)
        self.workspace_manager.show_success("Country emissions input saved successfully.")
        dialog.accept()

    # System/production popup
    def show_production_popup(self):
        dialog = QDialog(self.parent)
        remove_qt_help_button(dialog)
        dialog.setWindowTitle("Emission Factors by Generation Technology")
        dialog.setFixedSize(400, 360)
        dialog.setModal(True)

        layout = QVBoxLayout(dialog)

        # Help
        top_row = QHBoxLayout()
        top_row.addStretch()
        help_btn = QPushButton("?")
        help_btn.setFixedSize(35, 35)
        help_btn.setStyleSheet(GenerationPopupHandler.style)
        help_btn.clicked.connect(lambda: self.show_emissions_system_help(dialog))
        top_row.addWidget(help_btn)
        layout.addLayout(top_row)

        # Efficiency input
        input_row = QHBoxLayout()
        input_label = QLabel("System Efficiency:")
        input_label.setStyleSheet("font-weight: bold; font-size: 12px;")

        efficiency_input = QLineEdit()
        efficiency_input.setPlaceholderText("e.g. 0.85")
        efficiency_input.setAlignment(Qt.AlignLeft)

        validator = QDoubleValidator(0.0, 1.0, 4, efficiency_input)
        validator.setNotation(QDoubleValidator.StandardNotation)
        efficiency_input.setValidator(validator)

        input_row.addWidget(input_label)
        input_row.addWidget(efficiency_input)
        layout.addLayout(input_row)

        # Tech list
        production_list = QListWidget()
        production_list.setStyleSheet("""
            QListWidget {
                background-color: white;
                font-size: 12px;
                font-weight: bold;
                border: 1px solid black;
                padding: 4px;
                outline: none;
            }
            QListWidget::item { padding: 6px; }
            QListWidget::item:hover { background-color: #e0e0e0; }
            QListWidget::item:selected { background-color: #c0c0c0; color: black; }
        """)

        input_frame = QFrame()
        input_frame.setStyleSheet("""
            QFrame {border: 2px solid black; background-color: white;}
            QLabel {font-weight: bold;}
        """)
        input_layout = QVBoxLayout(input_frame)
        input_layout.addWidget(production_list)
        layout.addWidget(input_frame)

        for entry in self.co2_by_production:
            unit = entry.get("unit_type", "Unknown")
            ef = entry.get("EF_kgCO2e_per_kWh", None)
            fuel = entry.get("fuel", "Unknown")
            display = f"{unit} / {fuel} — {'N/A' if ef is None else f'{ef:.5f}'}"
            production_list.addItem(display)

        def on_item_selected():
            current_index = production_list.currentRow()
            if current_index >= 0:
                data = self.co2_by_production[current_index]
                eff = data.get("efficiency", "")
                efficiency_input.setText(str(eff))

        production_list.currentRowChanged.connect(on_item_selected)

        # Save
        save_btn = QPushButton("Save")
        save_btn.setStyleSheet(GenerationPopupHandler.style)
        save_btn.clicked.connect(lambda: self._save_system_emissions(dialog, production_list, efficiency_input))
        layout.addWidget(save_btn, alignment=Qt.AlignRight)

        dialog.exec_()

    def _save_system_emissions(self, dialog, production_list, efficiency_input):
        selected_item = production_list.currentItem()
        eff_text = efficiency_input.text()

        if not selected_item or not eff_text:
            QMessageBox.warning(dialog, "Missing Input", "Please select a generation unit and provide efficiency.")
            return

        try:
            efficiency = float(eff_text)
        except ValueError:
            QMessageBox.warning(dialog, "Invalid Efficiency", "Please enter a valid number between 0 and 1.")
            return

        # enforce 0–1
        if not (0.0 <= efficiency <= 1.0):
            QMessageBox.warning(dialog, "Invalid Efficiency", "System efficiency must be between 0 and 1.")
            return

        if not self._parse_and_store_price(dialog):
            return

        unit_name = selected_item.text().split(" — ")[0]
        try:
            emission_value = float(selected_item.text().split(" — ")[1])
        except (IndexError, ValueError):
            emission_value = None

        self.last_emission_system_inputs = {
            'emission_price': self.last_co2_price,
            'system_name': unit_name,
            'emission_metric': "kgCO₂e/kWh",
            'emission_value': emission_value,
            'system_efficiency': efficiency,
            'mode': 'System type',
        }

        self.workspace_manager.update("Input", "Emission Inputs", self.last_emission_system_inputs, coordinates=False)
        self.workspace_manager.show_success("Generation emission input saved successfully.")
        dialog.accept()

    # Custom popup
    def show_custom_popup(self):
        dialog = QDialog(self.parent)
        remove_qt_help_button(dialog)
        dialog.setWindowTitle("Emission factors custom Input")
        dialog.setFixedSize(300, 200)
        dialog.setModal(True)

        layout = QVBoxLayout(dialog)

        # Help
        top_row = QHBoxLayout()
        top_row.addStretch()
        help_btn = QPushButton("?")
        help_btn.setFixedSize(35, 35)
        help_btn.setStyleSheet(GenerationPopupHandler.style)
        help_btn.clicked.connect(lambda: self.show_emissions_custom_help(dialog))
        top_row.addWidget(help_btn)
        layout.addLayout(top_row)

        # Efficiency
        eff_row = QHBoxLayout()
        eff_label = QLabel("System Efficiency:")
        eff_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        eff_input = QLineEdit()
        eff_input.setPlaceholderText("e.g. 0.85")
        eff_input.setAlignment(Qt.AlignLeft)
        validator = QDoubleValidator(0.0, 1.0, 4, eff_input)
        validator.setNotation(QDoubleValidator.StandardNotation)
        eff_input.setValidator(validator)
        eff_row.addWidget(eff_label)
        eff_row.addWidget(eff_input)
        layout.addLayout(eff_row)

        # Emission factor
        ef_row = QHBoxLayout()
        ef_label = QLabel("Emission Factor (kgCO₂/kWh):")
        ef_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        ef_input = QLineEdit()
        ef_input.setPlaceholderText("e.g. 0.300")
        ef_input.setAlignment(Qt.AlignLeft)
        ef_row.addWidget(ef_label)
        ef_row.addWidget(ef_input)
        layout.addLayout(ef_row)

        save_btn = QPushButton("Save")
        save_btn.setStyleSheet(GenerationPopupHandler.style)
        save_btn.clicked.connect(lambda: self._save_custom_emissions(dialog, eff_input, ef_input))
        layout.addWidget(save_btn, alignment=Qt.AlignRight)

        dialog.exec_()

    def _save_custom_emissions(self, dialog, eff_input, ef_input):
        eff_val = eff_input.text()
        ef_val = ef_input.text()

        if not eff_val or not ef_val:
            QMessageBox.warning(dialog, "Missing Input", "Please enter both efficiency and emission factor.")
            return

        try:
            eff = float(eff_val)
            ef = float(ef_val)
        except ValueError:
            QMessageBox.warning(dialog, "Invalid Input", "Please enter valid numbers.")
            return

        # enforce 0–1
        if not (0.0 <= eff <= 1.0):
            QMessageBox.warning(dialog, "Invalid Efficiency", "System efficiency must be between 0 and 1.")
            return


        if not self._parse_and_store_price(dialog):
            return

        self.last_emission_custom_inputs = {
            'emission_price': self.last_co2_price,
            'emission_metric': "kgCO₂/kWh",
            'emission_value': ef,
            'system_efficiency': eff,
            'mode': 'custom',
        }

        self.workspace_manager.update("Input", "Emission Inputs", self.last_emission_custom_inputs, coordinates=False)
        self.workspace_manager.show_success("Custom emission input saved successfully.")
        dialog.accept()

    # Help dialogs
    def show_emissions_main_help(self, parent):
        dlg = QDialog(parent)
        remove_qt_help_button(dlg)
        dlg.setWindowTitle("Emissions Input – Help")
        dlg.setFixedSize(380, 320)
        layout = QVBoxLayout(dlg)
        msg = QLabel("""
            <b>Emissions – Input Help</b><br><br>
            <b>CO₂ emissions price:</b> Monetary value per kg of CO₂ used to compute externalized cost of emissions.<br><br>
            <b>Fuel-based:</b> Select a fuel and an emission metric. Provide either system efficiency (kgCO₂/kWh mode) or yearly consumption (physical units mode).<br><br>
            <b>Country-based:</b> Choose a country and grid category (intermittent/firm or grid losses).<br><br>
            <b>System-based:</b> Select technology (unit/fuel pair), optionally adjust efficiency.<br><br>
            <b>Custom:</b> Provide your own emission factor and efficiency.
        """)
        msg.setWordWrap(True)
        layout.addWidget(msg)
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(GenerationPopupHandler.style)
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)
        dlg.exec()

    def show_emissions_fuel_help(self, parent, mode):
        dlg = QDialog(parent)
        remove_qt_help_button(dlg)
        dlg.setWindowTitle("Fuel-based Emissions – Help")
        dlg.setFixedSize(380, 280)
        layout = QVBoxLayout(dlg)
        mode_text = "kgCO₂/kWh with <i>system efficiency</i>" if mode == "tj" \
            else "kgCO₂ per <i>physical units</i> with <i>yearly consumption</i>"
        msg = QLabel(f"""
            <b>Fuel-based Emissions</b><br><br>
            Select an emission metric and a fuel. This dialog operates in:<br>
            - <b>{mode_text}</b>.<br><br>
            <br>System efficiency input is in the range of <b>(0 – 1).</b>
            <br>For yearly fuel consumption input is needed in liters on tons.<br>
            <br>Make sure to provide a valid numeric input. Click <b>Save</b> to record the selection.
        """)
        msg.setWordWrap(True)
        layout.addWidget(msg)
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(GenerationPopupHandler.style)
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)
        dlg.exec()

    def show_emissions_country_help(self, parent):
        dlg = QDialog(parent)
        remove_qt_help_button(dlg)
        dlg.setWindowTitle("Country-based Emissions – Help")
        dlg.setFixedSize(380, 260)
        layout = QVBoxLayout(dlg)
        msg = QLabel("""
            <b>Country-based Emissions</b><br><br>
            Choose the grid category and then select a country. The value is expressed in kgCO₂/kWh.
        """)
        msg.setWordWrap(True)
        layout.addWidget(msg)
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(GenerationPopupHandler.style)
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)
        dlg.exec()

    def show_emissions_system_help(self, parent):
        dlg = QDialog(parent)
        remove_qt_help_button(dlg)
        dlg.setWindowTitle("System-based Emissions – Help")
        dlg.setFixedSize(380, 280)
        layout = QVBoxLayout(dlg)
        msg = QLabel("""
            <b>System-based Emissions</b><br><br>
            Select a generation technology (unit/fuel). Emission factors are in kgCO₂e/kWh.
            You can enter or adjust <b>system efficiency</b> (0–1). Click <b>Save</b> to record.
        """)
        msg.setWordWrap(True)
        layout.addWidget(msg)
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(GenerationPopupHandler.style)
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)
        dlg.exec()

    def show_emissions_custom_help(self, parent):
        dlg = QDialog(parent)
        remove_qt_help_button(dlg)
        dlg.setWindowTitle("Custom Emissions – Help")
        dlg.setFixedSize(380, 260)
        layout = QVBoxLayout(dlg)
        msg = QLabel("""
            <b>Custom Emissions</b><br><br>
            Provide your own emission factor (kgCO₂/kWh) and system efficiency (0–1).
        """)
        msg.setWordWrap(True)
        layout.addWidget(msg)
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(GenerationPopupHandler.style)
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)
        dlg.exec()

    # External cost popups (refactored like PricePopupHandler)
    def show_external_country_popup(self):
        """
        Displays a popup showing external costs by country.
        """
        dialog = QDialog(self.parent)
        remove_qt_help_button(dialog)
        dialog.setWindowTitle("External Cost by Country")
        dialog.setFixedSize(400, 350)
        dialog.setModal(True)

        layout = QVBoxLayout(dialog)

        # Help Button
        top_row = QHBoxLayout()
        top_row.addStretch()
        help_btn = QPushButton("?")
        help_btn.setFixedSize(35, 35)
        help_btn.setStyleSheet(GenerationPopupHandler.style)
        help_btn.clicked.connect(lambda: self.show_external_country_help(dialog))
        top_row.addWidget(help_btn)
        layout.addLayout(top_row)

        self.external_country_list = QListWidget()
        self.external_country_list.setStyleSheet("""
            QListWidget {
                background-color: white;
                font-size: 12px;
                font-weight: bold;
                border: 1px solid black;
                padding: 4px;
                outline: none;
            }
            QListWidget::item { padding: 6px; }
            QListWidget::item:hover { background-color: #e0e0e0; }
            QListWidget::item:selected { background-color: #c0c0c0; color: black; }
        """)
        layout.addWidget(self.external_country_list)

        # Populate list
        for country, impacts in self.external_cost_country.items():
            try:
                pm = impacts.get("Particulate matter", 0)
                ht = impacts.get("Human Toxicity", 0)
                display = f"{country} — Particualte Matter: {pm:.5f}, Health toxicity: {ht:.5f}"
                self.external_country_list.addItem(display)
            except Exception as e:
                print(f"Error loading country {country}: {e}")

        # Save Button
        save_btn = QPushButton("Save")
        save_btn.setStyleSheet(GenerationPopupHandler.style)
        save_btn.clicked.connect(lambda: self._save_external_country(dialog))
        layout.addWidget(save_btn, alignment=Qt.AlignRight)

        dialog.exec_()

    def _save_external_country(self, dialog):
        selected_item = self.external_country_list.currentItem()
        if not selected_item:
            QMessageBox.warning(dialog, "No Selection", "Please select a country from the list.")
            return

        country_name = selected_item.text().split(" — ")[0]
        try:
            data = self.external_cost_country.get(country_name, {})
            pm = round(float(data.get("Particulate matter", 0)), 4)
            ht = round(float(data.get("Human Toxicity", 0)), 4)
        except Exception as e:
            QMessageBox.warning(dialog, "Error", f"Could not parse selected country data.\n{e}")
            return

        self.last_external_cost_country_inputs = {
            'mode': 'External cost country',
            'country': country_name,
            'external_pm_cost': f'{pm:.4f}',
            'external_ht_cost': f'{ht:.4f}',
        }

        self.workspace_manager.update("Input", "External Cost Inputs", self.last_external_cost_country_inputs, coordinates=False)
        self.workspace_manager.show_success("External cost by country saved successfully.")
        dialog.accept()


    def show_external_production_popup(self):
        """
        Displays a popup showing external costs by production type.
        """
        dialog = QDialog(self.parent)
        remove_qt_help_button(dialog)
        dialog.setWindowTitle("External Cost by Production Type")
        dialog.setFixedSize(400, 350)
        dialog.setModal(True)

        layout = QVBoxLayout(dialog)

        # Help Button
        top_row = QHBoxLayout()
        top_row.addStretch()
        help_btn = QPushButton("?")
        help_btn.setFixedSize(35, 35)
        help_btn.setStyleSheet(GenerationPopupHandler.style)
        help_btn.clicked.connect(lambda: self.show_external_production_help(dialog))
        top_row.addWidget(help_btn)
        layout.addLayout(top_row)

        self.external_fuel_list = QListWidget()
        self.external_fuel_list.setStyleSheet("""
            QListWidget {
                background-color: white;
                font-size: 12px;
                font-weight: bold;
                border: 1px solid black;
                padding: 4px;
                outline: none;
            }
            QListWidget::item { padding: 6px; }
            QListWidget::item:hover { background-color: #e0e0e0; }
            QListWidget::item:selected { background-color: #c0c0c0; color: black; }
        """)
        layout.addWidget(self.external_fuel_list)

        # Populate list and attach the full entry as item data (avoid string parsing)
        for entry in self.external_cost_fuel_type:
            try:
                fuel   = entry.get("fuel",  entry.get("Technology", "Unknown"))
                region = entry.get("region", entry.get("Region", ""))
                pm     = entry.get("Particulate matter", 0)
                ht     = entry.get("Human Toxicity", 0)

                text = f"{fuel} ({region}) — Particulate Matter: {pm:.5f}, Health toxicity: {ht:.5f}"
                item = QListWidgetItem(text)
                item.setData(Qt.UserRole, entry)           # <-- stash raw dict/row here
                self.external_fuel_list.addItem(item)
            except Exception as e:
                print(f"Error loading fuel entry: {e}")

        save_btn = QPushButton("Save")
        save_btn.setStyleSheet(GenerationPopupHandler.style)
        save_btn.clicked.connect(lambda: self._save_external_production(dialog))
        layout.addWidget(save_btn, alignment=Qt.AlignRight)

        dialog.exec_()


    def _save_external_production(self, dialog):
        item = self.external_fuel_list.currentItem()
        if not item:
            QMessageBox.warning(dialog, "No Selection", "Please select a fuel/region from the list.")
            return

        # Retrieve the original data instead of parsing the label text
        entry = item.data(Qt.UserRole)
        try:
            fuel   = entry.get("fuel", entry.get("Technology", "Unknown"))
            region = entry.get("region", entry.get("Region", ""))
            pm = round(float(entry.get("Particulate matter", 0)), 4)
            ht = round(float(entry.get("Human Toxicity", 0)), 4)

            self.last_external_cost_fuel_inputs = {
                'mode': 'External cost fuel',
                'fuel': fuel,
                'region': region,
                'external_pm_cost': f'{pm:.4f}',
                'external_ht_cost': f'{ht:.4f}',
            }

            self.workspace_manager.update("Input", "External Cost Inputs", self.last_external_cost_fuel_inputs, coordinates=False)
            self.workspace_manager.show_success("External cost by fuel type saved successfully.")
            dialog.accept()

        except Exception as e:
            QMessageBox.warning(dialog, "Error", f"Could not parse selected fuel entry.\n{e}")



    def show_external_manual_popup(self):
        """
        Popup for user to manually input external cost (€/kWh).
        """
        dialog = QDialog(self.parent)
        remove_qt_help_button(dialog)
        dialog.setWindowTitle("Custom External Cost Input")
        dialog.setFixedSize(300, 160)
        dialog.setModal(True)

        layout = QVBoxLayout(dialog)

        # Help Button
        top_row = QHBoxLayout()
        top_row.addStretch()
        help_btn = QPushButton("?")
        help_btn.setFixedSize(35, 35)
        help_btn.setStyleSheet(GenerationPopupHandler.style)
        help_btn.clicked.connect(lambda: self.show_external_manual_help(dialog))
        top_row.addWidget(help_btn)
        layout.addLayout(top_row)

        # Input 1: Particulate Matter
        row1 = QHBoxLayout()
        label1 = QLabel("Particulate Matter (€/kWh):")
        label1.setStyleSheet("font-weight: bold; font-size: 12px;")
        self.manual_pm_input = QLineEdit()
        self.manual_pm_input.setPlaceholderText("e.g. 0.015")
        row1.addWidget(label1)
        row1.addWidget(self.manual_pm_input)
        layout.addLayout(row1)

        # Input 2: Human Toxicity
        row2 = QHBoxLayout()
        label2 = QLabel("Human Toxicity (€/kWh):")
        label2.setStyleSheet("font-weight: bold; font-size: 12px;")
        self.manual_ht_input = QLineEdit()
        self.manual_ht_input.setPlaceholderText("e.g. 0.030")
        row2.addWidget(label2)
        row2.addWidget(self.manual_ht_input)
        layout.addLayout(row2)

        # Save Button
        save_btn = QPushButton("Save")
        save_btn.setStyleSheet(GenerationPopupHandler.style)
        save_btn.clicked.connect(lambda: self._save_external_manual(dialog))
        layout.addWidget(save_btn, alignment=Qt.AlignRight)

        dialog.exec_()

    def _save_external_manual(self, dialog):
        val_pm = self.manual_pm_input.text()
        val_ht = self.manual_ht_input.text()
        try:
            parsed_pm = round(float(val_pm), 4)
            parsed_ht = round(float(val_ht), 4)

            self.last_external_cost_manual_inputs = {
                'mode': 'External cost manual',
                'external_pm_cost': parsed_pm,
                'external_ht_cost': parsed_ht
            }

            self.workspace_manager.update("Input", "External Cost Inputs", self.last_external_cost_manual_inputs, coordinates=False)
            self.workspace_manager.show_success("Manual external cost saved successfully.")
            dialog.accept()

        except ValueError:
            QMessageBox.warning(dialog, "Invalid Input", "Please enter valid numbers for both fields.")


    # Help dialogs for external costs
    def show_external_country_help(self, parent):
        dlg = QDialog(parent)
        remove_qt_help_button(dlg)
        dlg.setWindowTitle("External Cost by Country – Help")
        dlg.setFixedSize(380, 260)
        layout = QVBoxLayout(dlg)
        msg = QLabel("""
            <b>External Cost by Country</b><br><br>
            Select a country to use its aggregated external cost factors (€/kWh), including:<br>
            • <b>Particulate matter</b><br>
            • <b>Human toxicity</b><br><br>
            Click <b>Save</b> to record your selection.
        """)
        msg.setWordWrap(True)
        layout.addWidget(msg)
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(GenerationPopupHandler.style)
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)
        dlg.exec()

    def show_external_production_help(self, parent):
        dlg = QDialog(parent)
        remove_qt_help_button(dlg)
        dlg.setWindowTitle("External Cost by Production Type – Help")
        dlg.setFixedSize(380, 280)
        layout = QVBoxLayout(dlg)
        msg = QLabel("""
            <b>External Cost by Production Type</b><br><br>
            Choose a fuel/technology and its region. Each entry lists external cost factors in €/kWh:<br>
            • <b>Particulate matter</b><br>
            • <b>Human toxicity</b><br><br>
            Click <b>Save</b> to record your selection.
        """)
        msg.setWordWrap(True)
        layout.addWidget(msg)
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(GenerationPopupHandler.style)
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)
        dlg.exec()

    def show_external_manual_help(self, parent):
        dlg = QDialog(parent)
        remove_qt_help_button(dlg)
        dlg.setWindowTitle("Custom External Cost – Help")
        dlg.setFixedSize(380, 240)
        layout = QVBoxLayout(dlg)
        msg = QLabel("""
            <b>Custom External Cost</b><br><br>
            Enter your own external cost values in €/kWh for:<br>
            • <b>Particulate matter</b><br>
            • <b>Human toxicity</b><br><br>
            Use decimals (e.g., 0.0250). Click <b>Save</b> to apply.
        """)
        msg.setWordWrap(True)
        layout.addWidget(msg)
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(GenerationPopupHandler.style)
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)
        dlg.exec()


class ThermalEmissionsPopupHandler:
    checkbox_style = """
        QCheckBox {
            font-weight: bold;
            font-size: 12px;
        }
    """

    last_emission_fuel_inputs = {
        'emission_price': '0.07',
        'fuel_name': '',
        'fuel_price': '',
        'emission_metric': '',
        'emission_value': '',
        'system_efficiency': '',
        "fuel_consumption": '',
        'mode': '',
    }

    last_emission_system_inputs = {
        'emission_price': '',
        'fuel_name': '',
        'fuel_price': '',
        'emission_metric': "",
        'emission_value': '',
        'system_efficiency': '',
        'mode': 'system',
    }

    last_emission_custom_inputs = {
        'emission_price': '',
        'fuel_price': '',
        'emission_metric': "",
        'emission_value': '',
        'system_efficiency':'',
        'mode': 'custom',
    }

    last_external_cost_country_inputs = {
        'mode': 'External cost country',
        'country': '',
        'external_pm_cost': '',
        'external_ht_cost': ''
    }

    last_external_cost_fuel_inputs = {
        'mode': 'External cost production',
        'fuel': '',
        'region':'',
        'external_pm_cost':'',
        'external_ht_cost': ''
    }

    last_external_cost_manual_inputs = {
        'mode': 'External cost manual',
        'external_pm_cost': '',
        'external_ht_cost': ''
    }

    def __init__(self, parent, toolbar, workspace_manager):
        self.parent = parent
        self.toolbar = toolbar
        self.workspace_manager = workspace_manager
        self.validate = Technology(self.parent)

        self.co2_loader = CO2DataLoader()
        base_dir = "Co2"
        
        co2_fuels_path = resource_path(os.path.join(base_dir, "co2_fules.xlsx"))
        co2_heat_prod_path = resource_path(os.path.join(base_dir, "co2_heating_production_type.xlsx"))
        
        self.co2_fuels_tj, self.co2_fuels_units = self.co2_loader.get_co2_by_fuel(co2_fuels_path)
        self.co2_by_production = self.co2_loader.get_co2_by_production_type(co2_heat_prod_path)
        
        self.external_cost_loader = ExternalCostDataLoader()
        ext_country_heat_path = resource_path(os.path.join(base_dir, "External_cost_country_heating.xlsx"))
        ext_prod_heat_path    = resource_path(os.path.join(base_dir, "External_cost_production_type_heating.xlsx"))
        
        self.external_cost_country = self.external_cost_loader.get_external_cost_by_country(ext_country_heat_path)
        self.external_cost_fuel_type = self.external_cost_loader.get_external_cost_by_fuel_type(ext_prod_heat_path)

        self.last_co2_price = self.last_emission_fuel_inputs.get('emission_price', '0.07')

    # Top-level popup
    def show_popup(self, pos=None):
        dialog = QDialog(self.parent)
        remove_qt_help_button(dialog)
        dialog.setWindowTitle("Thermal Emission Inputs")
        dialog.setFixedSize(550, 350)
        dialog.setModal(True)

        dialog.setStyleSheet("""
            QCheckBox { background-color: white; font-size: 12px; }
            QCheckBox::indicator { width: 16px; height: 16px; }
            QCheckBox::indicator:unchecked { background-color: white; border: 1px solid black; }
            QCheckBox::indicator:checked { background-color: #b0b0b0; border: 1px solid black; }
            QCheckBox::indicator:hover { background-color: #e0e0e0; }
            QGroupBox { font-weight: bold; }
            QScrollArea { border: 2px solid black; }
        """)

        layout = QVBoxLayout(dialog)

        # Help
        top_row = QHBoxLayout()
        top_row.addStretch()
        help_btn = QPushButton("?")
        help_btn.setFixedSize(35, 35)
        help_btn.setStyleSheet(GenerationPopupHandler.style)
        help_btn.clicked.connect(lambda: self.show_thermal_main_help(dialog))
        top_row.addWidget(help_btn)
        layout.addLayout(top_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        layout.addWidget(scroll)

        container = QWidget()
        container_layout = QVBoxLayout(container)
        scroll.setWidget(container)

        group_box = QGroupBox("Emissions by Previous Thermal System")
        group_layout = QVBoxLayout(group_box)

        # CO2 price
        co2_price_row = QHBoxLayout()
        co2_price_label = QLabel("CO₂ emissions price (€/kgCO₂):")
        co2_price_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        self.co2_price_input = QLineEdit()
        self.co2_price_input.setText(self.last_emission_fuel_inputs['emission_price'])
        self.co2_price_input.setAlignment(Qt.AlignLeft)
        co2_price_row.addWidget(co2_price_label)
        co2_price_row.addWidget(self.co2_price_input)
        group_layout.addLayout(co2_price_row)

        self.fuel_check = QCheckBox("Emissions by Thermal system based on fuel type")
        self.system_check = QCheckBox("Emissions by Thermal system based on system type")
        self.custom_check = QCheckBox("Emissions by Thermal system with custom input")

        self.fuel_tj_check = QCheckBox("Fuels in (kgCO₂/kWh)")
        self.fuel_unit_check = QCheckBox("Fuels in (kgCO₂/physical units)")
        for box in [self.fuel_tj_check, self.fuel_unit_check]:
            box.hide()

        indent_layout = QVBoxLayout()
        indent_layout.setContentsMargins(25, 0, 0, 0)
        indent_layout.addWidget(self.fuel_tj_check)
        indent_layout.addWidget(self.fuel_unit_check)

        self.fuel_check.stateChanged.connect(lambda s: self.handle_check('fuel', s))
        self.system_check.stateChanged.connect(lambda s: self.handle_check('system', s))
        self.custom_check.stateChanged.connect(lambda s: self.handle_check('custom', s))

        self.fuel_tj_check.stateChanged.connect(lambda s, sender=self.fuel_tj_check: self._subcheck_changed(s, sender))
        self.fuel_unit_check.stateChanged.connect(lambda s, sender=self.fuel_unit_check: self._subcheck_changed(s, sender))

        group_layout.addWidget(self.fuel_check)
        group_layout.addLayout(indent_layout)
        group_layout.addWidget(self.system_check)
        group_layout.addWidget(self.custom_check)
        container_layout.addWidget(group_box)

        # External costs group
        external_group = QGroupBox("External costs by Previous Thermal System")
        external_layout = QVBoxLayout(external_group)

        self.external_country_check = QCheckBox("External cost based on country")
        self.external_fuel_check = QCheckBox("External cost based on fuel type")
        self.external_manual_check = QCheckBox("External cost with custom input")

        external_layout.addWidget(self.external_country_check)
        external_layout.addWidget(self.external_fuel_check)
        external_layout.addWidget(self.external_manual_check)
        container_layout.addWidget(external_group)

        self.external_country_check.stateChanged.connect(lambda s: self.handle_external_check("country", s))
        self.external_fuel_check.stateChanged.connect(lambda s: self.handle_external_check("production", s))
        self.external_manual_check.stateChanged.connect(lambda s: self.handle_external_check("manual", s))

        # Close
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(GenerationPopupHandler.style)
        close_btn.clicked.connect(lambda: self._save_and_close_price(dialog))
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

        dialog.exec_()

    # Toggle handlers 
    def handle_check(self, selected, state):
        if state != Qt.Checked:
            return
        box_map = {'fuel': self.fuel_check, 'system': self.system_check, 'custom': self.custom_check}
        for key, box in box_map.items():
            box.blockSignals(True)
            box.setChecked(key == selected)
            box.blockSignals(False)

        if selected == 'fuel':
            self.fuel_tj_check.show()
            self.fuel_unit_check.show()
        else:
            self.fuel_tj_check.hide()
            self.fuel_unit_check.hide()
            self.fuel_tj_check.setChecked(False)
            self.fuel_unit_check.setChecked(False)

        if selected == 'system':
            self.show_production_popup()
        elif selected == 'custom':
            self.show_custom_popup()

    def _subcheck_changed(self, state, sender):
        if state != Qt.Checked:
            return
        if sender == self.fuel_tj_check:
            self.fuel_unit_check.blockSignals(True)
            self.fuel_unit_check.setChecked(False)
            self.fuel_unit_check.blockSignals(False)
            self.show_fuel_popup("tj")
        elif sender == self.fuel_unit_check:
            self.fuel_tj_check.blockSignals(True)
            self.fuel_tj_check.setChecked(False)
            self.fuel_tj_check.blockSignals(False)
            self.show_fuel_popup("unit")

    def handle_external_check(self, selected, state):
        if state != Qt.Checked:
            return
        box_map = {'country': self.external_country_check, 'production': self.external_fuel_check, 'manual': self.external_manual_check}
        for key, box in box_map.items():
            box.blockSignals(True)
            box.setChecked(key == selected)
            box.blockSignals(False)

        if selected == 'country':
            self.show_external_country_popup()
        elif selected == 'production':
            self.show_external_production_popup()
        elif selected == 'manual':
            self.show_external_manual_popup()

    # Shared helpers
    def _parse_and_store_price(self, parent_dialog=None):
        val = self.co2_price_input.text()
        if not val:
            return True
        try:
            parsed = float(val)
            self.last_co2_price = f"{parsed:.5f}"
            self.last_emission_fuel_inputs['emission_price'] = self.last_co2_price
            self.last_emission_system_inputs['emission_price'] = self.last_co2_price
            self.last_emission_custom_inputs['emission_price'] = self.last_co2_price
            return True
        except ValueError:
            QMessageBox.warning(parent_dialog or self.parent, "Invalid Emission price Input", "Please enter a valid number.")
            return False

    def _save_and_close_price(self, dialog):
        if self._parse_and_store_price(dialog):
            dialog.accept()

    # Fuel popup
    def show_fuel_popup(self, mode="tj"):
        import pandas as pd
        data = self.co2_fuels_tj if mode == "tj" else self.co2_fuels_units
        title = "Fuels in (kgCO₂/kWh)" if mode == "tj" else "Fuels in (kgCO₂/physical units)"

        dialog = QDialog(self.parent)

        remove_qt_help_button(dialog)
        dialog.setWindowTitle(title)
        dialog.setFixedSize(400, 380)
        dialog.setModal(True)

        layout = QVBoxLayout(dialog)

        # Help
        top_row = QHBoxLayout()
        top_row.addStretch()
        help_btn = QPushButton("?")
        help_btn.setFixedSize(35, 35)
        help_btn.setStyleSheet(GenerationPopupHandler.style)
        help_btn.clicked.connect(lambda: self.show_thermal_fuel_help(dialog, mode))
        top_row.addWidget(help_btn)
        layout.addLayout(top_row)

        # Inputs (efficiency/consumption + fuel price)
        input_container = QVBoxLayout()

        row1 = QHBoxLayout()
        input_label = QLabel("System Efficiency:" if mode == "tj" else "Yearly fuel consumption (liters or tons):")
        input_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        input_field = QLineEdit()
        input_field.setPlaceholderText("e.g. 0.85" if mode == "tj" else "e.g. 1500")
        input_field.setAlignment(Qt.AlignLeft)
        row1.addWidget(input_label)
        row1.addWidget(input_field)

        row2 = QHBoxLayout()
        input_label_price = QLabel("Fuel price (€/kWh):" if mode == "tj" else "Fuel price (€/tons or liters):")
        input_label_price.setStyleSheet("font-weight: bold; font-size: 12px;")
        input_field_price = QLineEdit()
        input_field_price.setAlignment(Qt.AlignLeft)
        row2.addWidget(input_label_price)
        row2.addWidget(input_field_price)

        if mode == "tj":
            validator = QDoubleValidator(0.0, 1.0, 4, input_field)
            validator.setNotation(QDoubleValidator.StandardNotation)
            input_field.setValidator(validator)

        if mode == "tj" and self.last_emission_fuel_inputs.get("system_efficiency"):
            input_field.setText(str(self.last_emission_fuel_inputs["system_efficiency"]))
        elif mode != "tj" and self.last_emission_fuel_inputs.get("fuel_consumption"):
            input_field.setText(str(self.last_emission_fuel_inputs["fuel_consumption"]))
        if self.last_emission_fuel_inputs.get("fuel_price"):
            input_field_price.setText(str(self.last_emission_fuel_inputs["fuel_price"]))

        input_container.addLayout(row1)
        input_container.addLayout(row2)
        layout.addLayout(input_container)

        # Metric selector
        metric_label = QLabel("Select emission metric:")
        metric_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        metric_selector = QComboBox()
        metric_selector.setFixedWidth(150)
        metric_selector.setStyleSheet(GenerationPopupHandler.combo_style)
        metric_selector.addItems(["kg CO2", "kg CO2e", "kg CO2e incl, unox, carbon"])
        layout.addWidget(metric_label)
        layout.addWidget(metric_selector)

        # Fuel list
        fuel_list = QListWidget()
        fuel_list.setStyleSheet("""
            QListWidget { background-color: white; font-size: 12px; font-weight: bold; border: 1px solid black; padding: 4px; outline: none; }
            QListWidget::item { padding: 6px; }
            QListWidget::item:hover { background-color: #e0e0e0; }
            QListWidget::item:selected { background-color: #c0c0c0; color: black; }
        """)

        input_frame = QFrame()
        input_frame.setStyleSheet("QFrame {border: 2px solid black; background-color: white;} QLabel {font-weight: bold;}")
        input_layout = QVBoxLayout(input_frame)
        input_layout.addWidget(fuel_list)
        layout.addWidget(input_frame)

        metric_map = {"kg CO2": "kg_CO2", "kg CO2e": "kg_CO2e", "kg CO2e incl, unox, carbon": "kg_CO2e_incl_unox"}

        def update_fuel_list():
            fuel_list.clear()
            selected_metric = metric_map[metric_selector.currentText()]
            for fuel, values in data.items():
                val = values.get(selected_metric)
                display = f"{fuel} — {'N/A' if pd.isna(val) else f'{val:.5f}'}"
                fuel_list.addItem(display)

        metric_selector.currentTextChanged.connect(update_fuel_list)
        update_fuel_list()

        save_btn = QPushButton("Save")
        save_btn.setStyleSheet(GenerationPopupHandler.style)
        save_btn.clicked.connect(lambda: self._save_fuel_emissions(dialog, fuel_list, input_field, input_field_price, metric_selector, mode))
        layout.addWidget(save_btn, alignment=Qt.AlignRight)

        dialog.exec_()

    def _save_fuel_emissions(self, dialog, fuel_list, input_field, input_field_price, metric_selector, mode):
        selected_item = fuel_list.currentItem()
        input_value = input_field.text()
        input_value_price = input_field_price.text()

        if not selected_item or not input_value:
            QMessageBox.warning(dialog, "Missing Input", "Please select a fuel and provide input.")
            return

        try:
            numeric_value = float(input_value)
            numeric_value_price = float(input_value_price)
        except ValueError:
            QMessageBox.warning(dialog, "Invalid Input", "Please enter a valid number.")
            return
        
        # Enforce 0–1 for efficiency when mode == "tj"
        if mode == "tj" and not (0.0 <= numeric_value <= 1.0):
            QMessageBox.warning(dialog, "Invalid Efficiency", "System efficiency must be between 0 and 1.")
            return

        if not self._parse_and_store_price(dialog):
            return

        fuel_text = selected_item.text().split(" — ")[0]
        try:
            emission_value = float(selected_item.text().split(" — ")[1])
        except (IndexError, ValueError):
            emission_value = None
        metric_label_str = metric_selector.currentText()

        if mode == "tj":
            self.last_emission_fuel_inputs["system_efficiency"] = numeric_value
            self.last_emission_fuel_inputs["fuel_consumption"] = ''
        else:
            self.last_emission_fuel_inputs["fuel_consumption"] = numeric_value
            self.last_emission_fuel_inputs["system_efficiency"] = ''
        self.last_emission_fuel_inputs["fuel_price"] = numeric_value_price

        self.last_emission_fuel_inputs = {
            'emission_price': self.last_co2_price,
            'fuel_name': fuel_text,
            'fuel_price': numeric_value_price,
            'emission_metric': metric_label_str,
            'emission_value': emission_value,
            'system_efficiency': numeric_value if mode == 'tj' else '',
            'fuel_consumption': '' if mode == 'tj' else numeric_value,
            'mode': 'fuels in kWh' if mode == 'tj' else 'yearly fuel consumption',
        }

        self.workspace_manager.update("Input", "Thermal Emission Inputs", self.last_emission_fuel_inputs, coordinates=False)
        self.workspace_manager.show_success("Fuel emissions input saved successfully.")
        dialog.accept()

    # Production popup
    def show_production_popup(self):
        """
        Thermal production popup: clicking a list item fills the System Efficiency field.
        """
        dialog = QDialog(self.parent)
        remove_qt_help_button(dialog)
        dialog.setWindowTitle("Emission Factors by Generation Technology")
        dialog.setFixedSize(400, 360)
        dialog.setModal(True)

        layout = QVBoxLayout(dialog)

        # Help Button
        top_row = QHBoxLayout()
        top_row.addStretch()
        help_btn = QPushButton("?")
        help_btn.setFixedSize(35, 35)
        help_btn.setStyleSheet(GenerationPopupHandler.style)
        help_btn.clicked.connect(lambda: self.show_thermal_system_help(dialog))
        top_row.addWidget(help_btn)
        layout.addLayout(top_row)

        # Inputs (efficiency + optional fuel price)
        input_container = QVBoxLayout()

        row1 = QHBoxLayout()
        eff_label = QLabel("System Efficiency:")
        eff_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        efficiency_input = QLineEdit()
        efficiency_input.setAlignment(Qt.AlignLeft)
        # EXACTLY two decimals allowed, range 0..1
        eff_validator = QDoubleValidator(0.0, 1.0, 3, efficiency_input)
        eff_validator.setNotation(QDoubleValidator.StandardNotation)
        efficiency_input.setValidator(eff_validator)
        row1.addWidget(eff_label)
        row1.addWidget(efficiency_input)

        row2 = QHBoxLayout()
        price_label = QLabel("Fuel price (€/kWh):")
        price_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        price_input = QLineEdit()
        price_input.setAlignment(Qt.AlignLeft)
        row2.addWidget(price_label)
        row2.addWidget(price_input)

        input_container.addLayout(row1)
        input_container.addLayout(row2)
        layout.addLayout(input_container)

        # List of technologies
        production_list = QListWidget()
        production_list.setStyleSheet("""
            QListWidget {
                background-color: white;
                font-size: 12px;
                font-weight: bold;
                border: 1px solid black;
                padding: 4px;
                outline: none;
            }
            QListWidget::item { padding: 6px; }
            QListWidget::item:hover { background-color: #e0e0e0; }
            QListWidget::item:selected { background-color: #c0c0c0; color: black; }
        """)

        frame = QFrame()
        frame.setStyleSheet("QFrame {border: 2px solid black; background-color: white;} QLabel {font-weight: bold;}")
        fl = QVBoxLayout(frame)
        fl.addWidget(production_list)
        layout.addWidget(frame)

        # Helper to read likely column names
        def _get(entry, key, default=None):
            val = entry.get(key)
            return default if val is None else val

        # Build list items; show EF if present, otherwise price; format to 2 decimals
        for entry in self.co2_by_production:
            unit  = _get(entry, "unit_type", "Unknown")
            fuel  = _get(entry, "fuel", "Unknown")
            ef    = _get(entry, "EF_kgCO2e_per_kWh", None)
            price = _get(entry, "fuel_price", None)

            def _fmt2(val):
                try:
                    return f"{float(val):.2f}"
                except Exception:
                    return "N/A"

            right_val = _fmt2(ef) if ef is not None else (_fmt2(price) if price is not None else "N/A")
            text = f"{unit} / {fuel} — {right_val}"
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, entry)   
            production_list.addItem(item)

        # On select: fill efficiency if available; else clear. Also prefill price if present.
        def on_item_selected():
            item = production_list.currentItem()
            if not item:
                return
            entry = item.data(Qt.UserRole) or {}

            def to_float_or_none(v):
                try:
                    f = float(v)
                    # NaN check: NaN != NaN
                    return None if f != f else f
                except Exception:
                    s = str(v).strip().lower()
                    return None if s in {"", "na", "n/a", "none", "null", "-"} else None

            eff_f = to_float_or_none(entry.get("efficiency"))
            if eff_f is None:
                efficiency_input.clear()        # leave blank if missing
            else:
                efficiency_input.setText(f"{eff_f:.2f}")

            price_val = entry.get("fuel_price")
            if price_val is not None and not price_input.text().strip():
                try:
                    price_input.setText(f"{float(price_val):.2f}")
                except Exception:
                    price_input.setText(str(price_val))

        production_list.currentRowChanged.connect(lambda _: on_item_selected())
        production_list.itemClicked.connect(lambda _: on_item_selected())


        # Save button
        save_btn = QPushButton("Save")
        save_btn.setStyleSheet(GenerationPopupHandler.style)
        save_btn.clicked.connect(lambda: self._save_system_emissions(dialog, production_list, efficiency_input, price_input))
        layout.addWidget(save_btn, alignment=Qt.AlignRight)

        dialog.exec_()

    def _save_system_emissions(self, dialog, production_list, efficiency_input, price_input):
        item = production_list.currentItem()
        eff_text = efficiency_input.text()
        price_text = price_input.text()

        if not item or not eff_text:
            QMessageBox.warning(dialog, "Missing Input", "Please select a generation unit and provide efficiency.")
            return

        # Validate numbers
        try:
            efficiency = float(eff_text)
            price = float(price_text) if price_text.strip() else 0.0
        except ValueError:
            QMessageBox.warning(dialog, "Invalid Input", "Please enter valid numeric values.")
            return

        # Enforce 0–1
        if not (0.0 <= efficiency <= 1.0):
            QMessageBox.warning(dialog, "Invalid Efficiency", "System efficiency must be between 0 and 1.")
            return

        # Store CO2 price
        val = self.co2_price_input.text()
        if val:
            try:
                parsed = float(val)
                self.last_co2_price = f"{parsed:.5f}"
                self.last_emission_fuel_inputs['emission_price'] = self.last_co2_price
                self.last_emission_system_inputs['emission_price'] = self.last_co2_price
            except ValueError:
                QMessageBox.warning(dialog, "Invalid Emission price Input", "Please enter a valid number.")
                return

        entry = item.data(Qt.UserRole) or {}
        unit = entry.get("unit_type") or entry.get("Unit") or "Unknown"
        fuel = entry.get("fuel") or entry.get("Fuel") or "Unknown"
        display_name = f"{unit} / {fuel}"

        ef = entry.get("EF_kgCO2e_per_kWh") or entry.get("EF_kgCO2_per_kWh")
        try:
            emission_value = float(ef) if ef is not None else None
        except Exception:
            emission_value = None

        self.last_emission_system_inputs = {
            'emission_price': self.last_co2_price,
            'fuel_price': price,
            'system_name': display_name,
            'emission_metric': "kgCO₂e/kWh",
            'emission_value': emission_value,
            'system_efficiency': efficiency,
            'mode': 'System type',
        }

        self.workspace_manager.update("Input", "Thermal Emission Inputs", self.last_emission_system_inputs, coordinates=False)
        self.workspace_manager.show_success("Generation emission input saved successfully.")
        dialog.accept()

    # Custom popup
    def show_custom_popup(self):
        dialog = QDialog(self.parent)
        remove_qt_help_button(dialog)
        dialog.setWindowTitle("Emission factors custom Input")
        dialog.setFixedSize(300, 200)
        dialog.setModal(True)

        layout = QVBoxLayout(dialog)

        top_row = QHBoxLayout()
        top_row.addStretch()
        help_btn = QPushButton("?")
        help_btn.setFixedSize(35, 35)
        help_btn.setStyleSheet(GenerationPopupHandler.style)
        help_btn.clicked.connect(lambda: self.show_thermal_custom_help(dialog))
        top_row.addWidget(help_btn)
        layout.addLayout(top_row)

        input_container = QVBoxLayout()

        row1 = QHBoxLayout()
        input_label = QLabel("System Efficiency:")
        input_label.setStyleSheet("font-weight: bold; font-size: 12px;")
        input_field = QLineEdit()
        input_field.setPlaceholderText("e.g. 0.85")
        input_field.setAlignment(Qt.AlignLeft)
        validator = QDoubleValidator(0.0, 1.0, 4, input_field)
        validator.setNotation(QDoubleValidator.StandardNotation)
        input_field.setValidator(validator)
        row1.addWidget(input_label)
        row1.addWidget(input_field)

        row2 = QHBoxLayout()
        input_label_price = QLabel("Fuel price (€/kWh):")
        input_label_price.setStyleSheet("font-weight: bold; font-size: 12px;")
        input_field_price = QLineEdit()
        input_field_price.setAlignment(Qt.AlignLeft)
        row2.addWidget(input_label_price)
        row2.addWidget(input_field_price)

        row3 = QHBoxLayout()
        input_label_emission = QLabel("Emission Factor (kgCO₂/kWh):")
        input_label_emission.setStyleSheet("font-weight: bold; font-size: 12px;")
        input_field_emission = QLineEdit()
        input_field_emission.setPlaceholderText("e.g. 0.300")
        input_field_emission.setAlignment(Qt.AlignLeft)
        row3.addWidget(input_label_emission)
        row3.addWidget(input_field_emission)

        input_container.addLayout(row1)
        input_container.addLayout(row2)
        input_container.addLayout(row3)
        layout.addLayout(input_container)

        save_btn = QPushButton("Save")
        save_btn.setStyleSheet(GenerationPopupHandler.style)
        save_btn.clicked.connect(lambda: self._save_custom_emissions(dialog, input_field, input_field_price, input_field_emission))
        layout.addWidget(save_btn, alignment=Qt.AlignRight)

        dialog.exec_()

    def _save_custom_emissions(self, dialog, input_field, input_field_price, input_field_emission):
        eff_val = input_field.text()
        price_val = input_field_price.text()
        ef_val = input_field_emission.text()

        if not eff_val or not ef_val or not price_val:
            QMessageBox.warning(dialog, "Missing Input", "Please enter both efficiency and emission factor.")
            return

        try:
            eff = float(eff_val)
            ef = float(ef_val)
            price = float(price_val)
        except ValueError:
            QMessageBox.warning(dialog, "Invalid Input", "Please enter valid numbers.")
            return
        
        # Enforce 0–1
        if not (0.0 <= eff <= 1.0):
            QMessageBox.warning(dialog, "Invalid Efficiency", "System efficiency must be between 0 and 1.")
            return

        if not self._parse_and_store_price(dialog):
            return

        self.last_emission_custom_inputs = {
            'emission_price': self.last_co2_price,
            "fuel_price": price,
            'emission_metric': "kgCO₂/kWh",
            'emission_value': ef,
            'system_efficiency': eff,
            'mode': 'custom',
        }

        self.workspace_manager.update("Input", "Thermal Emission Inputs", self.last_emission_custom_inputs, coordinates=False)
        self.workspace_manager.show_success("Custom emission input saved successfully.")
        dialog.accept()

    # External costs (country)
    def show_external_country_popup(self):
        dialog = QDialog(self.parent)
        remove_qt_help_button(dialog)
        dialog.setWindowTitle("External Cost by Country")
        dialog.setFixedSize(400, 350)
        dialog.setModal(True)

        layout = QVBoxLayout(dialog)

        top_row = QHBoxLayout()
        top_row.addStretch()
        help_btn = QPushButton("?")
        help_btn.setFixedSize(35, 35)
        help_btn.setStyleSheet(GenerationPopupHandler.style)
        help_btn.clicked.connect(lambda: self.show_thermal_external_country_help(dialog))
        top_row.addWidget(help_btn)
        layout.addLayout(top_row)

        self.external_country_list = QListWidget()
        self.external_country_list.setStyleSheet("""
            QListWidget { background-color: white; font-size: 12px; font-weight: bold; border: 1px solid black; padding: 4px; outline: none; }
            QListWidget::item { padding: 6px; }
            QListWidget::item:hover { background-color: #e0e0e0; }
            QListWidget::item:selected { background-color: #c0c0c0; color: black; }
        """)
        layout.addWidget(self.external_country_list)

        for country, impacts in self.external_cost_country.items():
            try:
                pm = impacts.get("Particulate matter", 0)
                ht = impacts.get("Human Toxicity", 0)
                display = f"{country} — Particualte Matter: {pm:.5f}, Health toxicity: {ht:.5f}"
                self.external_country_list.addItem(display)
            except Exception as e:
                print(f"Error loading country {country}: {e}")

        save_btn = QPushButton("Save")
        save_btn.setStyleSheet(GenerationPopupHandler.style)
        save_btn.clicked.connect(lambda: self._save_external_country(dialog))
        layout.addWidget(save_btn, alignment=Qt.AlignRight)

        dialog.exec_()

    def _save_external_country(self, dialog):
        selected_item = self.external_country_list.currentItem()
        if not selected_item:
            QMessageBox.warning(dialog, "No Selection", "Please select a country from the list.")
            return

        country_name = selected_item.text().split(" — ")[0]
        try:
            data = self.external_cost_country.get(country_name, {})
            pm = round(float(data.get("Particulate matter", 0)), 4)
            ht = round(float(data.get("Human Toxicity", 0)), 4)
        except Exception as e:
            QMessageBox.warning(dialog, "Error", f"Could not parse selected country data.\n{e}")
            return

        self.last_external_cost_country_inputs = {
            'mode': 'External cost country',
            'country': country_name,
            'external_pm_cost': f'{pm:.4f}',
            'external_ht_cost': f'{ht:.4f}',
        }

        self.workspace_manager.update("Input", "Thermal External Cost Inputs", self.last_external_cost_country_inputs, coordinates=False)
        self.workspace_manager.show_success("External cost by country saved successfully.")
        dialog.accept()

    # External costs (production) – safe item data
    def show_external_production_popup(self):
        dialog = QDialog(self.parent)
        remove_qt_help_button(dialog)
        dialog.setWindowTitle("External Cost by Production Type")
        dialog.setFixedSize(400, 350)
        dialog.setModal(True)

        layout = QVBoxLayout(dialog)

        top_row = QHBoxLayout()
        top_row.addStretch()
        help_btn = QPushButton("?")
        help_btn.setFixedSize(35, 35)
        help_btn.setStyleSheet(GenerationPopupHandler.style)
        help_btn.clicked.connect(lambda: self.show_thermal_external_production_help(dialog))
        top_row.addWidget(help_btn)
        layout.addLayout(top_row)

        self.external_fuel_list = QListWidget()
        self.external_fuel_list.setStyleSheet("""
            QListWidget { background-color: white; font-size: 12px; font-weight: bold; border: 1px solid black; padding: 4px; outline: none; }
            QListWidget::item { padding: 6px; }
            QListWidget::item:hover { background-color: #e0e0e0; }
            QListWidget::item:selected { background-color: #c0c0c0; color: black; }
        """)
        layout.addWidget(self.external_fuel_list)

        # Attach full row to the item
        for entry in self.external_cost_fuel_type:
            try:
                fuel   = entry.get("fuel", entry.get("Technology", "Unknown"))
                region = entry.get("region", entry.get("Region", ""))
                pm     = entry.get("Particulate matter", 0)
                ht     = entry.get("Human Toxicity", 0)
                text = f"{fuel} ({region}) — Particualte Matter: {pm:.5f}, Health toxicity: {ht:.5f}"
                item = QListWidgetItem(text)
                item.setData(Qt.UserRole, entry)
                self.external_fuel_list.addItem(item)
            except Exception as e:
                print(f"Error loading fuel entry: {e}")

        save_btn = QPushButton("Save")
        save_btn.setStyleSheet(GenerationPopupHandler.style)
        save_btn.clicked.connect(lambda: self._save_external_production(dialog))
        layout.addWidget(save_btn, alignment=Qt.AlignRight)

        dialog.exec_()

    def _save_external_production(self, dialog):
        item = self.external_fuel_list.currentItem()
        if not item:
            QMessageBox.warning(dialog, "No Selection", "Please select a fuel/region from the list.")
            return

        try:
            entry = item.data(Qt.UserRole)
            fuel   = entry.get("fuel", entry.get("Technology", "Unknown"))
            region = entry.get("region", entry.get("Region", ""))
            pm = round(float(entry.get("Particulate matter", 0)), 4)
            ht = round(float(entry.get("Human Toxicity", 0)), 4)

            self.last_external_cost_fuel_inputs = {
                'mode': 'External cost fuel',
                'fuel': fuel,
                'region': region,
                'external_pm_cost': f'{pm:.4f}',
                'external_ht_cost': f'{ht:.4f}',
            }

            self.workspace_manager.update("Input", "Thermal External Cost Inputs", self.last_external_cost_fuel_inputs, coordinates=False)
            self.workspace_manager.show_success("External cost by fuel type saved successfully.")
            dialog.accept()

        except Exception as e:
            QMessageBox.warning(dialog, "Error", f"Could not parse selected fuel entry.\n{e}")

    # External costs 
    def show_external_manual_popup(self):
        dialog = QDialog(self.parent)
        remove_qt_help_button(dialog)
        dialog.setWindowTitle("Custom External Cost Input")
        dialog.setFixedSize(300, 160)
        dialog.setModal(True)

        layout = QVBoxLayout(dialog)

        top_row = QHBoxLayout()
        top_row.addStretch()
        help_btn = QPushButton("?")
        help_btn.setFixedSize(35, 35)
        help_btn.setStyleSheet(GenerationPopupHandler.style)
        help_btn.clicked.connect(lambda: self.show_thermal_external_manual_help(dialog))
        top_row.addWidget(help_btn)
        layout.addLayout(top_row)

        row1 = QHBoxLayout()
        label1 = QLabel("Particulate Matter (€/kWh):")
        label1.setStyleSheet("font-weight: bold; font-size: 12px;")
        self.manual_pm_input = QLineEdit()
        self.manual_pm_input.setPlaceholderText("e.g. 0.015")
        row1.addWidget(label1)
        row1.addWidget(self.manual_pm_input)
        layout.addLayout(row1)

        row2 = QHBoxLayout()
        label2 = QLabel("Human Toxicity (€/kWh):")
        label2.setStyleSheet("font-weight: bold; font-size: 12px;")
        self.manual_ht_input = QLineEdit()
        self.manual_ht_input.setPlaceholderText("e.g. 0.030")
        row2.addWidget(label2)
        row2.addWidget(self.manual_ht_input)
        layout.addLayout(row2)

        save_btn = QPushButton("Save")
        save_btn.setStyleSheet(GenerationPopupHandler.style)
        save_btn.clicked.connect(lambda: self._save_external_manual(dialog))
        layout.addWidget(save_btn, alignment=Qt.AlignRight)

        dialog.exec_()

    def _save_external_manual(self, dialog):
        val_pm = self.manual_pm_input.text()
        val_ht = self.manual_ht_input.text()
        try:
            parsed_pm = round(float(val_pm), 4)
            parsed_ht = round(float(val_ht), 4)

            self.last_external_cost_manual_inputs = {
                'mode': 'External cost manual',
                'external_pm_cost': parsed_pm,
                'external_ht_cost': parsed_ht
            }

            self.workspace_manager.update("Input", "Thermal External Cost Inputs", self.last_external_cost_manual_inputs, coordinates=False)
            self.workspace_manager.show_success("Manual external cost saved successfully.")
            dialog.accept()

        except ValueError:
            QMessageBox.warning(dialog, "Invalid Input", "Please enter valid numbers for both fields.")

    # Help dialogs
    def show_thermal_main_help(self, parent):
        dlg = QDialog(parent)
        remove_qt_help_button(dlg)
        dlg.setWindowTitle("Thermal Emissions – Help")
        dlg.setFixedSize(380, 320)
        layout = QVBoxLayout(dlg)
        msg = QLabel("""
            <b>Thermal Emissions – Input Help</b><br><br>
            <b>CO₂ emissions price:</b> €/kgCO₂ used to compute emission costs.<br><br>
            <b>Fuel-based:</b> Pick a fuel and metric. Provide efficiency (kgCO₂/kWh mode) or yearly consumption (physical units) and fuel price.<br><br>
            <b>System-based:</b> Select technology, set efficiency and fuel price.<br><br>
            <b>Custom:</b> Enter your own efficiency, fuel price and emission factor.
        """)
        msg.setWordWrap(True)
        layout.addWidget(msg)
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(GenerationPopupHandler.style)
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)
        dlg.exec()

    def show_thermal_fuel_help(self, parent, mode):
        dlg = QDialog(parent)
        remove_qt_help_button(dlg)
        dlg.setWindowTitle("Fuel-based Thermal Emissions – Help")
        dlg.setFixedSize(380, 300)
        layout = QVBoxLayout(dlg)
        mode_text = "kgCO₂/kWh with efficiency in the range (0 - 1) + fuel price" if mode == "tj" else "kgCO₂ per physical unit with yearly consumption + fuel price"
        msg = QLabel(f"""
            <b>Fuel-based Thermal Emissions</b><br><br>
            Select a metric and a fuel. This dialog uses <b>{mode_text}</b>.<br>
            Provide valid numeric inputs, then press <b>Save</b>.
        """)
        msg.setWordWrap(True)
        layout.addWidget(msg)
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(GenerationPopupHandler.style)
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)
        dlg.exec()

    def show_thermal_system_help(self, parent):
        dlg = QDialog(parent)
        remove_qt_help_button(dlg)
        dlg.setWindowTitle("System-based Thermal Emissions – Help")
        dlg.setFixedSize(380, 280)
        layout = QVBoxLayout(dlg)
        msg = QLabel("""
            <b>System-based Thermal Emissions</b><br><br>
            Select technology. Emission factors are in kgCO₂e/kWh.
            Enter or adjust system efficiency <b>(0 – 1)</b> and fuel price (€/kWh), then click <b>Save</b>.
        """)
        msg.setWordWrap(True)
        layout.addWidget(msg)
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(GenerationPopupHandler.style)
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)
        dlg.exec()

    def show_thermal_custom_help(self, parent):
        dlg = QDialog(parent)
        remove_qt_help_button(dlg)
        dlg.setWindowTitle("Custom Thermal Emissions – Help")
        dlg.setFixedSize(380, 280)
        layout = QVBoxLayout(dlg)
        msg = QLabel("""
            <b>Custom Thermal Emissions</b><br><br>
            Enter system efficiency (0–1), fuel price (€/kWh) and an emission factor (kgCO₂/kWh).
        """)
        msg.setWordWrap(True)
        layout.addWidget(msg)
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(GenerationPopupHandler.style)
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)
        dlg.exec()

    def show_thermal_external_country_help(self, parent):
        dlg = QDialog(parent)
        remove_qt_help_button(dlg)
        dlg.setWindowTitle("Thermal External Cost (Country) – Help")
        dlg.setFixedSize(380, 260)
        layout = QVBoxLayout(dlg)
        msg = QLabel("""
            <b>External Cost by Country</b><br><br>
            Select country-specific external cost values (€/kWh) for particulate matter and human toxicity.
        """)
        msg.setWordWrap(True)
        layout.addWidget(msg)
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(GenerationPopupHandler.style)
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)
        dlg.exec()

    def show_thermal_external_production_help(self, parent):
        dlg = QDialog(parent)
        remove_qt_help_button(dlg)
        dlg.setWindowTitle("Thermal External Cost (Production) – Help")
        dlg.setFixedSize(380, 280)
        layout = QVBoxLayout(dlg)
        msg = QLabel("""
            <b>External Cost by Production Type</b><br><br>
            Choose fuel/technology and region. Values are €/kWh for particulate matter and human toxicity.
        """)
        msg.setWordWrap(True)
        layout.addWidget(msg)
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(GenerationPopupHandler.style)
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)
        dlg.exec()

    def show_thermal_external_manual_help(self, parent):
        dlg = QDialog(parent)
        remove_qt_help_button(dlg)
        dlg.setWindowTitle("Thermal External Cost (Custom) – Help")
        dlg.setFixedSize(380, 240)
        layout = QVBoxLayout(dlg)
        msg = QLabel("""
            <b>Custom External Cost</b><br><br>
            Enter your own €/kWh values for particulate matter and human toxicity, then Save.
        """)
        msg.setWordWrap(True)
        layout.addWidget(msg)
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(GenerationPopupHandler.style)
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn, alignment=Qt.AlignRight)
        dlg.exec()


class PreviousSystemPopupHandler:
    def __init__(self, parent, toolbar, workspace_manager):
        self.parent = parent
        self.toolbar = toolbar
        self.workspace_manager = workspace_manager
        self.validate = Technology(self.parent)

    def show_popup(self, pos=None):
        dialog = QDialog(self.parent)
        remove_qt_help_button(dialog)
        dialog.setWindowTitle("Previous System Setup")
        dialog.setFixedSize(500, 300)
        dialog.setModal(True)

        dialog.setStyleSheet("""
            QCheckBox {
                background-color: white;
                font-size: 12px;
            }
            QGroupBox {
                font-weight: bold;
                font-size: 13px;
            }
        """)

        layout = QVBoxLayout(dialog)

        electricity_group = QGroupBox("Previous Electricity System")
        electricity_layout = QVBoxLayout(electricity_group)

        grid_only_checkbox = QCheckBox("Previous Electricity System\ndemand fufiled from grid\nuses data from Electricity CO\u2082 emissions")
        grid_only_checkbox.setChecked(True)
        grid_only_checkbox.setEnabled(False)

        electricity_layout.addWidget(grid_only_checkbox)
        layout.addWidget(electricity_group)

        thermal_group = QGroupBox("Previous Thermal System")
        thermal_layout = QVBoxLayout(thermal_group)

        thermal_only_checkbox = QCheckBox("Previous Thermal System\nuses data from Thermal CO\u2082 emissions")
        thermal_only_checkbox.setChecked(True)
        thermal_only_checkbox.setEnabled(False)

        thermal_layout.addWidget(thermal_only_checkbox)

        layout.addWidget(thermal_group)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet(GenerationPopupHandler.style)
        close_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(close_btn)
        layout.addLayout(btn_layout)

        dialog.exec_()

if __name__ == '__main__':
    print('toolbar_buttons is supporting script')