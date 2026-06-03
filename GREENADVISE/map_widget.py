from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtCore import pyqtSignal, QObject, pyqtSlot, QUrl
from PyQt5.QtWebChannel import QWebChannel
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QFrame, QMessageBox, QSizePolicy
import os
from resources import resource_path



class MapBridge(QObject):
    coordinatesChanged = pyqtSignal(float, float)

    @pyqtSlot(float, float)
    def sendCoordinates(self, lat, lon):
        self.coordinatesChanged.emit(lat, lon)

class MapWidget(QWidget):
    def __init__(self, workspace_manager):
        super().__init__()

        self.workspace_manager = workspace_manager

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self.setStyleSheet("background-color: white;")

        # Initial Zagreb coordinates
        self.initial_lat = 45.8150
        self.initial_lon = 15.9819

        self.view = QWebEngineView()
        self.view.setStyleSheet("border: 2px solid #999;")

        self.bridge = MapBridge()

        self.channel = QWebChannel()
        self.channel.registerObject("bridge", self.bridge)
        self.view.page().setWebChannel(self.channel)

        self.view.load(QUrl.fromLocalFile(resource_path("map.html")))
        
        self.lat_entry = QLineEdit(f"{self.initial_lat}")
        self.lon_entry = QLineEdit(f"{self.initial_lon}")

        update_button = QPushButton("Update Map")
        update_button.setFixedHeight(28)
        update_button.setStyleSheet("""
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
    
        input_frame = QFrame()
        input_frame.setStyleSheet("""
            QFrame {
                background-color: white;
                border: none;
                padding-top: 8px;  /* Aligns with Export to Excel button */
                padding-left: 8px;
                padding-right: 8px;
                padding-bottom: 8px;  /* <- Adds spacing below inputs */
            }
            QLabel {
                font-size: 12px;
                font-weight: bold;
                border: none;
            }
            QLineEdit {
                padding: 4px;
                border: 1px solid #aaa;
                border-radius: 0px;
            }
            QPushButton {
                padding: 4px 12px;
                background-color: #0078d7;
                color: white;
                border: none;
                border-radius: 0px; 
            }
            QPushButton:hover {
                background-color: #005fa3;
            }
        """)
        coords_layout = QHBoxLayout(input_frame)
        coords_layout.setContentsMargins(0, 0, 0, 0)
        coords_layout.setSpacing(5)
        coords_layout.addWidget(QLabel("Lat:"))
        coords_layout.addWidget(self.lat_entry)
        coords_layout.addWidget(QLabel("Lon:"))
        coords_layout.addWidget(self.lon_entry)
        coords_layout.addWidget(update_button)
    
        border_frame = QFrame()
        border_frame.setObjectName("MapBorderFrame")
        border_frame.setStyleSheet("""
            #MapBorderFrame {
                border-top: 4px solid black;
                border-bottom: 4px solid black;
                background-color: white;
            }
        """)
        
        border_layout = QVBoxLayout(border_frame)
        border_layout.setContentsMargins(0, 0, 0, 0)
        border_layout.setSpacing(0)
        border_layout.addWidget(input_frame)
        border_layout.addWidget(self.view)
    
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)
        outer_layout.addWidget(border_frame)

        update_button.clicked.connect(self.update_map)
        self.bridge.coordinatesChanged.connect(self.update_entries)

    def update_entries(self, lat, lon):
        self.lat_entry.setText(f"{lat:.6f}")
        self.lon_entry.setText(f"{lon:.6f}")

    def update_map(self):
        try:
            lat = float(self.lat_entry.text())
            lon = float(self.lon_entry.text())

            if not (-90.0 <= lat <= 90.0):
                QMessageBox.warning(self, "Invalid Latitude", "Latitude must be between -90 and 90.")
                return

            if not (-180.0 <= lon <= 180.0):
                QMessageBox.warning(self, "Invalid Longitude", "Longitude must be between -180 and 180.")
                return

            self.set_location(lat, lon)

            self.workspace_manager.refresh(lat, lon)

        except ValueError:
            QMessageBox.warning(self, "Invalid Input", "Please enter valid numeric coordinates.")

    def set_location(self, lat, lon):
        js = f"setMapLocation({lat}, {lon});"
        self.view.page().runJavaScript(js)

    def get_coordinates(self):
        try:
            lat = float(self.lat_entry.text())
            lon = float(self.lon_entry.text())
            return lat, lon
        except ValueError:
            return None, None