from PyQt5.QtWidgets import (
    QListWidgetItem, QMessageBox, QMenu, QLabel, QVBoxLayout, QHBoxLayout,
    QWidget, QListWidget, QFrame, QSizePolicy, QStackedWidget
)
from PyQt5.QtCore import Qt, QEvent
from PyQt5.QtGui import QBrush, QColor
from collections import OrderedDict
from Ploting_handler import PlottingHandler

class WorkspaceManager(QWidget):
    item_style = ("""
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
        self._workspace_list = QListWidget()
        self._parent = parent
        self._build_ui()
        self._workspace_list.installEventFilter(self)

    def _build_ui(self):
        container = QFrame()
        container.setObjectName("LeftFrame")
        container.setStyleSheet("""
            QFrame#LeftFrame {
                border: 4px solid black;
                background-color: white;
            }
        """)

        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)

        # ── panel title ──
        title_bar = QWidget()
        title_bar.setFixedHeight(26)
        title_bar.setStyleSheet("background-color: #2c2c2c; border: none;")
        t_lay = QHBoxLayout(title_bar)
        t_lay.setContentsMargins(8, 0, 8, 0)
        t_lbl = QLabel("CONFIGURED INPUTS")
        t_lbl.setStyleSheet(
            "color: #ffffff; font-size: 9px; font-weight: bold;"
            " letter-spacing: 1.5px; background: transparent; border: none;"
        )
        t_lay.addWidget(t_lbl)
        container_layout.addWidget(title_bar)

        # ── content stack: page 0 = placeholder, page 1 = list ──
        self._content_stack = QStackedWidget()

        _ph = QLabel(
            "No inputs configured yet.\n\n"
            "Use the toolbar buttons above to add system components:\n\n"
            "  •  Generation — PV, Wind Turbine\n"
            "  •  Generation — Heat Pump, Solar Collector\n"
            "  •  Storage — Battery, Buffer Tank\n"
            "  •  Thermal & Electricity Demand\n"
            "  •  Buy & Sell Prices\n"
            "  •  CO₂ Emissions\n\n"
            "Each item you configure will appear here.\n"
            "Double-click an item to inspect its data.\n"
            "Right-click an item to delete it."
        )
        _ph.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        _ph.setWordWrap(True)
        _ph.setStyleSheet(
            "QLabel { color: #b0b0b0; font-size: 11px; font-family: Arial;"
            " background: white; padding: 12px; border: none; }"
        )
        self._content_stack.addWidget(_ph)
        self._content_stack.addWidget(self._workspace_list)

        container_layout.addWidget(self._content_stack, 1)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(container)
        layout.setStretch(0, 1)

        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        self._workspace_list.itemDoubleClicked.connect(
            lambda item: PlottingHandler.show_workspace_item_details(self._parent, item)
        )

        self.setup_layout()
        self.setStyleSheet("background-color: white;")

        self._workspace_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self._workspace_list.customContextMenuRequested.connect(self._show_workspace_menu)

    def setup(self, parent_window):
        self._parent = parent_window

    def setup_layout(self):
        self._workspace_list.setStyleSheet(self._style())

    def _style(self):
        return """
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
                background-color: #f0f0f0;
                color: black;
                border: none; 
                outline: none;
            }
            QListWidget::item:focus {
                outline: none;  /* removes the focus rectangle */
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

    def update(self, category, name, value, coordinates=True):
        if self._workspace_list is None:
            print("Workspace not initialized.")
            return

        import inspect
        caller_frame = inspect.currentframe().f_back
        caller_self = caller_frame.f_locals.get('self', None)

        if coordinates and isinstance(value, dict) and caller_self:
            if hasattr(caller_self, 'lat') and hasattr(caller_self, 'lon'):
                lat = str(caller_self.lat)
                lon = str(caller_self.lon)
                new_value = OrderedDict()
                for k, v in value.items():
                    if k not in ("latitude", "longitude"):
                        new_value[k] = v
                new_value["latitude"] = lat
                new_value["longitude"] = lon
                value = new_value

        to_remove = []
        target_text = f"{category}: {name}"
        for i in range(self._workspace_list.count()):
            item = self._workspace_list.item(i)
            item_text = item.text().lstrip("⚠️ ").strip()
            if item_text == target_text:
                to_remove.append(item)
        for item in to_remove:
            self._workspace_list.takeItem(self._workspace_list.row(item))

        try:
            item_text = f"{category}: {name}"
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, value)
            self._workspace_list.addItem(item)

            if self._content_stack.currentIndex() == 0:
                self._content_stack.setCurrentIndex(1)

            if coordinates and isinstance(value, dict):
                lat = value.get("latitude")
                lon = value.get("longitude")
                if lat is not None and lon is not None:
                    self.refresh(lat, lon)

        except Exception as e:
            self.show_error(f"Error adding to workspace: {str(e)}")

    def show_success(self, message):
        if self._workspace_list:
            QMessageBox.information(self._workspace_list, "Success", message)

    def show_error(self, message):
        if self._workspace_list:
            QMessageBox.critical(self._workspace_list, "Error", message)

    def clear(self):
        if self._workspace_list:
            self._workspace_list.clear()
            self._content_stack.setCurrentIndex(0)

    def refresh(self, current_lat, current_lon):
        if self._workspace_list is None:
            return

        for i in range(self._workspace_list.count()):
            item = self._workspace_list.item(i)
            data = item.data(Qt.UserRole)

            if isinstance(data, dict):
                lat = data.get("latitude")
                lon = data.get("longitude")

                if lat is not None and lon is not None:
                    if str(lat) != str(current_lat) or str(lon) != str(current_lon):
                        item.setForeground(QBrush(QColor("red")))
                        item.setToolTip("Coordinates differ from current map location.")
                        if not item.text().startswith("⚠️"):
                            item.setText(f"⚠️ {item.text()}")
                    else:
                        item.setForeground(QBrush(QColor("black")))
                        item.setToolTip("")
                        if item.text().startswith("⚠️ "):
                            item.setText(item.text()[2:].strip())

    def delete(self, item):
        if self._workspace_list is None:
            return
        try:
            self._workspace_list.takeItem(self._workspace_list.row(item))
        except Exception as e:
            self.show_error(f"Error deleting from workspace: {str(e)}")

    def get_workspace_data(self):
        if self._workspace_list is None:
            return {}

        out = {}
        for i in range(self._workspace_list.count()):
            key = self._workspace_list.item(i).text()
            val = self._workspace_list.item(i).data(Qt.UserRole)
            try:
                from collections import OrderedDict
                if isinstance(val, OrderedDict):
                    val = dict(val)
            except Exception:
                pass
            out[key] = val
        return out

    def eventFilter(self, obj, event):
        if obj == self._workspace_list and event.type() == QEvent.KeyPress and event.key() == Qt.Key_Delete:
            item = self._workspace_list.currentItem()
            self.delete(item)
            return True
        return super().eventFilter(obj, event)

    def _show_workspace_menu(self, pos):
        item = self._workspace_list.itemAt(pos)
        if item:
            menu = QMenu(self._parent)
            menu.setStyleSheet("""
                QMenu { background-color: white; border: 2px solid black;}
                QMenu::item { padding: 6px 24px; background-color: white; color: black; }
                QMenu::item:selected { background-color: #f0f0f0; }
            """)
            delete_action = menu.addAction("Delete")
            selected_action = menu.exec_(self._workspace_list.mapToGlobal(pos))
            if selected_action == delete_action:
                self.delete(item)