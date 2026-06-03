from PyQt5.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QFrame, QGraphicsScene, QGraphicsView, QGraphicsLineItem
)
from PyQt5.QtGui import QPixmap, QFont, QPen
from PyQt5.QtCore import Qt, QPointF


class ClickableImage(QLabel):
    def __init__(self, path, label_text, callback=None, size=(80,80)):
        super().__init__()
        self.setPixmap(QPixmap(path).scaled(*size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.setAlignment(Qt.AlignCenter)
        self.label_text = label_text
        self.callback = callback
        self.setCursor(Qt.PointingHandCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton and self.callback:
            self.callback(self.label_text)


class GreenadviseTab(QWidget):
    def __init__(self, optimization_data, image_path):
        super().__init__()
        self.optimization_data = optimization_data
        self.image_path = image_path
        self.icons = {}
        self.setContentsMargins(0, 0, 0, 0)
        self._build_ui()

    def _build_ui(self):
        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(5, 5, 5, 5)

        frame = QFrame()
        frame.setStyleSheet("QFrame { border: 4px solid black; background-color: white; }")
        frame_layout = QVBoxLayout(frame)
        frame_layout.setSpacing(5)
        frame_layout.setContentsMargins(10, 10, 10, 10)

        for row_items in self._get_rows():
            frame_layout.addLayout(self._create_icon_row(row_items))

        outer_layout.addWidget(frame)
        self._draw_lines(frame)

    def _get_rows(self):
        return [
            [("sun.png", "Sun"), ("wind.png", "Wind"), ("temperature.png", "Temp")],
            [("thermal_demand.png", "Thermal Demand") if "Thermal Demand" in self.optimization_data else None,
             ("electricity_demand.png", "Electricity Demand") if "Electricity Demand" in self.optimization_data else None],
            [("PV.png", "PV") if "PV Generation" in self.optimization_data else None,
             ("wind_turbine.png", "Wind Turbine") if "Wind Generation" in self.optimization_data else None,
             ("heat_pump.png", "Heat Pump") if "Heat Pump Inputs" in self.optimization_data else None,
             ("solar_collector.png", "Solar Collector") if "Solar Collector Inputs" in self.optimization_data else None],
            [("electricity_stor.png", "Battery") if "Battery Inputs" in self.optimization_data else None,
             ("thermal_stor.png", "Buffer Tank") if "Buffer Tank Inputs" in self.optimization_data else None],
            [("objective_function.png", "Optimization")],
            [("energy_flow.png", "Energy Flow"), ("ecological effects.png", "Ecological"),
             ("education.png", "Education"), ("capex_opex.png", "Financials")]
        ]

    def _create_icon_row(self, items):
        row = QHBoxLayout()
        row.setSpacing(10)
        row.setAlignment(Qt.AlignCenter)
        for item in items:
            if item:
                icon, label = item
                row.addWidget(self._create_icon_widget(icon, label))
        return row

    def _create_icon_widget(self, icon_file, label_text):
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(2)

        icon = ClickableImage(self.image_path + icon_file, label_text, self.on_icon_clicked, size=(70, 70))

        label = QLabel(label_text)
        label.setAlignment(Qt.AlignCenter)
        label.setFont(QFont("Arial", 8))
        label.setStyleSheet("background: none; border: none;")  
        label.setWordWrap(True)

        layout.addWidget(icon)
        layout.addWidget(label)
        self.icons[label_text] = icon
        return container

    def _draw_lines(self, parent_widget):
        scene = QGraphicsScene()
        view = QGraphicsView(scene, parent_widget)
        view.setStyleSheet("background: transparent; border: none;")
        view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        view.setFixedHeight(1)
        view.raise_()
        view.show()

        def connect(label1, label2):
            if label1 not in self.icons or label2 not in self.icons:
                return
            w1 = self.icons[label1]
            w2 = self.icons[label2]
            p1 = w1.mapTo(parent_widget, w1.rect().center())
            p2 = w2.mapTo(parent_widget, w2.rect().center())
            line = QGraphicsLineItem(p1.x(), p1.y(), p2.x(), p2.y())
            pen = QPen(Qt.black, 2)
            line.setPen(pen)
            scene.addItem(line)

        connections = [
            ("Sun", "PV"),
            ("Wind", "Wind Turbine"),
            ("Electricity Demand", "Optimization"),
            ("Thermal Demand", "Optimization"),
            ("Battery", "Optimization"),
            ("Buffer Tank", "Optimization"),
            ("Optimization", "Energy Flow"),
            ("Optimization", "Education"),
            ("Optimization", "Financials"),
            ("Optimization", "Ecological"),
        ]

        for a, b in connections:
            connect(a, b)

    def on_icon_clicked(self, label):
        print(f"📌 Clicked: {label}")
