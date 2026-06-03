from PyQt5.QtCore import Qt, QCoreApplication, QTimer, QPoint, QSize
QCoreApplication.setAttribute(Qt.AA_ShareOpenGLContexts)

import sys
from PyQt5.QtGui import QPixmap, QFont, QIcon
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel,
    QVBoxLayout, QHBoxLayout, QToolBar, QAction, QMessageBox, QPushButton,
    QGridLayout, QSizePolicy, QSpacerItem, QWidgetAction, QSplitter,
    QDialog, QLineEdit, QDialogButtonBox
)

from config_loader import get_ninja_api_key, save_ninja_api_key


class ApiKeyDialog(QDialog):
    def __init__(self, current_key: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Renewables.ninja API Key")
        self.setFixedWidth(460)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)
        self.setStyleSheet("QDialog { background-color: #ffffff; } QWidget { background-color: #ffffff; color: #101828; }")

        lay = QVBoxLayout(self)
        lay.setContentsMargins(30, 26, 30, 22)
        lay.setSpacing(12)

        title = QLabel("Renewables.ninja API Key")
        title.setFont(QFont("Segoe UI", 13, QFont.Bold))
        lay.addWidget(title)

        desc = QLabel(
            "GREENADVISE uses the Renewables.ninja API to fetch solar and wind\n"
            "generation data for your location.\n\n"
            "Register for a free key at: <b>www.renewables.ninja</b>"
        )
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #555; font-size: 12px;")
        lay.addWidget(desc)

        self._key_edit = QLineEdit(current_key)
        self._key_edit.setPlaceholderText("Paste your API key here...")
        self._key_edit.setFixedHeight(38)
        self._key_edit.setEchoMode(QLineEdit.Password)
        self._key_edit.setStyleSheet("""
            QLineEdit {
                border: 2px solid #aaa; border-radius: 4px;
                padding: 0 10px; font-size: 13px; background: #f9f9f9;
            }
            QLineEdit:focus { border-color: #333; background: #fff; }
        """)
        lay.addWidget(self._key_edit)

        toggle = QPushButton("Show key")
        toggle.setCheckable(True)
        toggle.setFixedHeight(26)
        toggle.setStyleSheet("""
            QPushButton { background: transparent; color: #333; border: none; font-size: 11px; text-align: left; }
            QPushButton:hover { text-decoration: underline; }
        """)
        toggle.clicked.connect(lambda checked: (
            self._key_edit.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password),
            toggle.setText("Hide key" if checked else "Show key"),
        ))
        lay.addWidget(toggle)

        btn_style = """
            QPushButton {
                background-color: #101828; color: #fff;
                border: none; border-radius: 4px;
                padding: 0 24px; font-size: 13px; font-weight: bold;
            }
            QPushButton:hover { background-color: #333; }
        """
        skip_style = """
            QPushButton {
                background-color: #f0f0f0; color: #555;
                border: 1px solid #ccc; border-radius: 4px;
                padding: 0 18px; font-size: 13px;
            }
            QPushButton:hover { background-color: #e0e0e0; }
        """

        ok_btn = QPushButton("Continue")
        ok_btn.setFixedHeight(36)
        ok_btn.setDefault(True)
        ok_btn.setStyleSheet(btn_style)
        ok_btn.clicked.connect(self._on_ok)

        skip_btn = QPushButton("Skip")
        skip_btn.setFixedHeight(36)
        skip_btn.setStyleSheet(skip_style)
        skip_btn.clicked.connect(self.reject)

        hbtn = QHBoxLayout()
        hbtn.addWidget(skip_btn)
        hbtn.addStretch()
        hbtn.addWidget(ok_btn)
        lay.addLayout(hbtn)

    def _on_ok(self):
        key = self._key_edit.text().strip()
        if key:
            save_ninja_api_key(key)
        self.accept()

    def api_key(self) -> str:
        return self._key_edit.text().strip()



from toolbar_buttons import (
    GenerationPopupHandler, StoragePopupHandler,
    ThermalDemandPopupHandler, ElectricityDemandPopupHandler, PricePopupHandler,
    EmissionsPopupHandler, ThermalEmissionsPopupHandler, PreviousSystemPopupHandler
)

from Prepare_data import PrepareData
from Workspace_menager import WorkspaceManager
from Workspace_optimization_menager import (OptimizationWorkspaceManager,
                                            FinancialWorkspaceManager,
                                            EmissionsWorkspaceManager,
                                            OptimizationTextAnalysisManager)
from Export_data import export_to_excel
from map_widget import MapWidget
from resources import resource_path


class _StepBtn(QWidget):
    """A single clickable step button inside a _NavGroup."""

    _NORMAL = "background: transparent; border-left: 1px solid #ddd;"
    _HOVER  = "background: #eef7f2; border-left: 1px solid #ddd;"

    def __init__(self, label: str, handler, parent=None):
        super().__init__(parent)
        self.handler = handler
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumWidth(70)
        self.setStyleSheet(self._NORMAL)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(10, 4, 10, 4)
        lay.setSpacing(1)

        text_lbl = QLabel(label)
        text_lbl.setAlignment(Qt.AlignCenter)
        text_lbl.setStyleSheet(
            "color: #222; font-size: 11px; font-weight: bold;"
            " background: transparent; border: none;"
        )

        lay.addWidget(text_lbl)

    def enterEvent(self, e):
        self.setStyleSheet(self._HOVER)

    def leaveEvent(self, e):
        self.setStyleSheet(self._NORMAL)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.handler()


class _NavGroup(QWidget):
    """
    A labeled group block for the toolbar.
    The group title spans across the top of all its buttons,
    making the grouping structure immediately visible.
    """

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setFixedHeight(60)
        self.setStyleSheet(
            "background: #f9f9f9;"
            " border-left: 2px solid #d0d0d0;"
            " border-right: 2px solid #d0d0d0;"
        )

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Title strip spans full width of the group
        title_bar = QWidget()
        title_bar.setFixedHeight(17)
        title_bar.setStyleSheet("background: #efefef; border-bottom: 1px solid #ddd;")
        tlay = QHBoxLayout(title_bar)
        tlay.setContentsMargins(8, 0, 8, 0)

        lbl = QLabel(title)
        lbl.setStyleSheet(
            "color: #888; font-size: 8px; font-weight: bold;"
            " letter-spacing: 1.2px; background: transparent; border: none;"
        )
        tlay.addWidget(lbl)
        tlay.addStretch()

        # ── Buttons row
        self._btn_row = QWidget()
        self._btn_row.setStyleSheet("background: #f9f9f9;")
        self._btn_lay = QHBoxLayout(self._btn_row)
        self._btn_lay.setContentsMargins(0, 0, 0, 0)
        self._btn_lay.setSpacing(0)

        outer.addWidget(title_bar)
        outer.addWidget(self._btn_row, 1)

    def add(self, label: str, handler) -> _StepBtn:
        btn = _StepBtn(label, handler, self._btn_row)
        self._btn_lay.addWidget(btn)
        return btn


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("GREENADVISE")
        self.setWindowIcon(QIcon(resource_path("images/Greenadvise_logo.png")))
        self.setStyleSheet("background-color: white;")
        self.setMinimumSize(600, 400)
        self.optimization_popup = None

        self._init_toolbar()
        self._show_initial_selection()

        QTimer.singleShot(0, self._prompt_api_key)

    def _prompt_api_key(self):
        dlg = ApiKeyDialog(current_key=get_ninja_api_key(), parent=self)
        dlg.adjustSize()
        screen = QApplication.primaryScreen().availableGeometry()
        dlg.move(
            screen.center().x() - dlg.width() // 2,
            screen.center().y() - dlg.height() // 2,
        )
        dlg.exec_()

    def _init_toolbar(self):
        self.toolbar = QToolBar("Main Toolbar")
        self.toolbar.setMovable(False)
        self.toolbar.setFixedHeight(60)
        self.addToolBar(self.toolbar)

        self.toolbar.setStyleSheet("""
            QToolBar {
                background-color: #ffffff;
                border-bottom: 2px solid #d0d0d0;
                padding: 0; margin: 0; spacing: 0;
            }
        """)

        def _wa(widget):
            wa = QWidgetAction(self)
            wa.setDefaultWidget(widget)
            self.toolbar.addAction(wa)

        def _gap(w=8):
            sp = QWidget()
            sp.setFixedSize(w, 60)
            sp.setStyleSheet("background: #ffffff;")
            return sp

        # \u2500\u2500 Home button (standalone, distinct)
        home = QPushButton()
        home.setFixedSize(72, 60)
        home.setToolTip("Return to main menu")
        _icon_path = resource_path("images/home_icon.png")
        _icon_pix = QPixmap(_icon_path).scaled(26, 26, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        home.setIcon(QIcon(_icon_pix))
        home.setIconSize(QSize(26, 26))
        home.setStyleSheet("""
            QPushButton {
                background: #f0f0f0;
                border: none; border-right: 2px solid #d0d0d0;
            }
            QPushButton:hover { background: #e0e0e0; }
        """)
        home.clicked.connect(self._show_initial_selection)
        _wa(home)
        _wa(_gap())

        # \u2500\u2500 SYSTEM INPUTS group
        inputs = _NavGroup("SYSTEM INPUTS")
        self._gen_btn  = inputs.add("Generation",   self._generation)
        self._stor_btn = inputs.add("Storage",      self._storage)
        self._therm_btn= inputs.add("Thermal",      self._thermal)
        self._elec_btn = inputs.add("Electricity",  self._electricity)
        self._price_btn= inputs.add("Prices",       self._price)
        _wa(inputs)
        _wa(_gap())

        # \u2500\u2500 EMISSIONS group
        emis = _NavGroup("EMISSIONS")
        self._emis_btn  = emis.add("Electricity CO\u2082", self._emissions)
        self._temis_btn = emis.add("Thermal CO\u2082",     self._thermal_emissions)
        _wa(emis)
        _wa(_gap())

        # \u2500\u2500 OPTIONAL group
        opt = _NavGroup("OPTIONAL")
        self._prev_btn = opt.add("Previous System", self._previous_system)
        _wa(opt)
        _wa(_gap())

        # \u2500\u2500 Run button (final action, green)
        run_btn = QPushButton("\u25b6  Start\nOptimization")
        run_btn.setFixedHeight(60)
        run_btn.setMinimumWidth(110)
        run_btn.clicked.connect(lambda: self.run_optimization(None, None))
        run_btn.setStyleSheet("""
            QPushButton {
                background: #1a7f3c; color: #ffffff;
                border: none; border-radius: 0;
                font-size: 11px; font-weight: bold;
                padding: 0 18px;
            }
            QPushButton:hover { background: #146030; }
        """)
        _wa(run_btn)

        # \u2500\u2500 Spacer + logos
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        _wa(spacer)

        logo_widget = QWidget()
        logo_layout = QHBoxLayout(logo_widget)
        logo_layout.setContentsMargins(0, 0, 10, 0)
        logo_layout.setSpacing(5)

        emerge_label = QLabel()
        emerge_pixmap = QPixmap(resource_path("images/Emerge_logo.png")).scaledToHeight(32, Qt.SmoothTransformation)
        emerge_label.setPixmap(emerge_pixmap)
        logo_layout.addWidget(emerge_label)

        eu_label = QLabel()
        eu_pixmap = QPixmap(resource_path("images/EU_logo.png")).scaledToHeight(32, Qt.SmoothTransformation)
        eu_label.setPixmap(eu_pixmap)
        logo_layout.addWidget(eu_label)

        _wa(logo_widget)

        self.toolbar.hide()

    def _show_initial_selection(self):
        self.toolbar.hide()


        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)


        self.main_layout.addStretch()
        

        title_label = QLabel('<span style="color:black;">GREEN</span><span style="color:green;">ADVISE</span>')
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setFont(QFont("Century Schoolbook", 22, QFont.Bold))
        title_label.setStyleSheet("color: black;")
        self.main_layout.addWidget(title_label, alignment=Qt.AlignCenter)
        

        self.selection_container = QWidget()
        layout = QVBoxLayout(self.selection_container)
        layout.setAlignment(Qt.AlignCenter)
        layout.setContentsMargins(20, 20, 20, 20)

        image_row = QHBoxLayout()
        image_row.setSpacing(60)
        image_row.setAlignment(Qt.AlignCenter)

        image_row.addWidget(self._create_image_button("images/euro.png", "Energy system\n optimization\n START", self._profit_clicked))

        layout.addLayout(image_row) 
        self.main_layout.addWidget(self.selection_container, alignment=Qt.AlignCenter)


        self.main_layout.addStretch()


        bottom_logo_widget = QWidget()
        bottom_logo_layout = QHBoxLayout(bottom_logo_widget)
        bottom_logo_layout.setContentsMargins(0, 0, 20, 20)
        bottom_logo_layout.setSpacing(10)
        bottom_logo_layout.setAlignment(Qt.AlignRight | Qt.AlignBottom)

        emerge_logo = QLabel()
        emerge_pixmap = QPixmap(resource_path("images/Emerge_logo.png")).scaledToHeight(50, Qt.SmoothTransformation)
        emerge_logo.setPixmap(emerge_pixmap)

        eu_logo = QLabel()
        eu_pixmap = QPixmap(resource_path("images/EU_logo.png")).scaledToHeight(50, Qt.SmoothTransformation)
        eu_logo.setPixmap(eu_pixmap)

        bottom_logo_layout.addWidget(emerge_logo)
        bottom_logo_layout.addWidget(eu_logo)

        self.main_layout.addWidget(bottom_logo_widget, alignment=Qt.AlignRight | Qt.AlignBottom)


    def _create_image_button(self, image_path, label_text, on_click):
        container = QWidget()
        container.setStyleSheet("""
            QWidget {
                border: 2px solid #555;
                border-radius: 100px;
                background-color: white;
            }
            QWidget:hover {
                border: 2px solid #000;
            }
        """)
        layout = QVBoxLayout(container)
        layout.setAlignment(Qt.AlignCenter)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        img_label = QLabel()
        img_label.setStyleSheet("background: transparent; border: none;")
        pixmap = QPixmap(resource_path(image_path))
        img_label.setPixmap(pixmap.scaled(150, 120, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        img_label.setAlignment(Qt.AlignCenter)

        container.setCursor(Qt.PointingHandCursor)
        container.mousePressEvent = lambda event: on_click()
        
        img_label.setCursor(Qt.PointingHandCursor)
        img_label.mousePressEvent = lambda event: on_click()
        
        text_label = QLabel(label_text)
        text_label.setAlignment(Qt.AlignCenter)
        text_label.setFont(QFont("Arial", 10, QFont.Bold))
        text_label.setStyleSheet("background: transparent; border: none;")
        text_label.setCursor(Qt.PointingHandCursor)
        text_label.mousePressEvent = lambda event: on_click()


        layout.addWidget(img_label)
        layout.addWidget(text_label)
        return container

    
    def _profit_clicked(self):
        self._clear_main_layout()


        self.main_container = QWidget()
        self.setCentralWidget(self.main_container)


        outer_layout = QVBoxLayout(self.main_container)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)

        self.workspace_manager = WorkspaceManager(self)
        self.workspace_manager.setup(self)

        self.map_widget = MapWidget(self.workspace_manager)
        self.map_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.text_analysis_workspace = OptimizationTextAnalysisManager(self)
        self.text_analysis_workspace.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # Map container with toggle button in header
        map_container = QWidget()
        map_container.setStyleSheet("background-color: white;")
        _map_vlay = QVBoxLayout(map_container)
        _map_vlay.setContentsMargins(0, 0, 0, 0)
        _map_vlay.setSpacing(0)

        _map_header = QWidget()
        _map_header.setFixedHeight(28)
        _map_header.setStyleSheet(
            "background: #f0f0f0; border-bottom: 1px solid #c0c0c0;"
        )
        _map_hlay = QHBoxLayout(_map_header)
        _map_hlay.setContentsMargins(8, 0, 8, 0)
        _map_hlay.setSpacing(6)

        # Restore button for inputs panel — hidden until inputs are collapsed
        self._show_inputs_btn = QPushButton("▶ Inputs")
        self._show_inputs_btn.setFixedHeight(20)
        self._show_inputs_btn.setVisible(False)
        self._show_inputs_btn.setStyleSheet("""
            QPushButton {
                background: #e8f5e9; color: #1a7f3c;
                border: 1px solid #1a7f3c; border-radius: 3px;
                font-size: 10px; padding: 0 8px;
            }
            QPushButton:hover { background: #c8e6c9; }
        """)
        self._show_inputs_btn.clicked.connect(self._toggle_inputs)
        _map_hlay.addWidget(self._show_inputs_btn)

        _map_lbl = QLabel("Map View")
        _map_lbl.setStyleSheet(
            "color: #444444; font-size: 11px; font-weight: bold; background: transparent;"
        )
        _map_hlay.addWidget(_map_lbl)
        _map_hlay.addStretch()
        self._map_toggle_btn = QPushButton("Hide Map")
        self._map_toggle_btn.setFixedHeight(20)
        self._map_toggle_btn.setStyleSheet("""
            QPushButton {
                background: white; color: #333333;
                border: 1px solid #bbbbbb; border-radius: 3px;
                font-size: 10px; padding: 0 8px;
            }
            QPushButton:hover {
                background: #e8f5e9; color: #1a7f3c; border-color: #1a7f3c;
            }
        """)
        self._map_toggle_btn.clicked.connect(self._toggle_map)
        _map_hlay.addWidget(self._map_toggle_btn)

        _map_vlay.addWidget(_map_header)
        _map_vlay.addWidget(self.map_widget)

        self._center_splitter = QSplitter(Qt.Vertical)
        self._center_splitter.setHandleWidth(2)
        self._center_splitter.setStyleSheet("QSplitter::handle { background: black; }")
        self._center_splitter.setChildrenCollapsible(True)
        self._center_splitter.addWidget(map_container)
        self._center_splitter.addWidget(self.text_analysis_workspace)
        self._center_splitter.setSizes([420, 520])
        self.map_widget.setMinimumHeight(0)
        center_splitter = self._center_splitter

        self.emissions_workspace = EmissionsWorkspaceManager(self)
        self.emissions_workspace.setup_layout()
        self.emissions_workspace.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.financial_workspace = FinancialWorkspaceManager(self)
        self.financial_workspace.setup_layout()
        self.financial_workspace.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.output_workspace = OptimizationWorkspaceManager(self)
        self.output_workspace.setup_layout()
        self.output_workspace.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)


        right_container = QWidget()
        right_container.setMinimumWidth(420)


        bordered_frame = QWidget()
        bordered_frame.setObjectName("BorderedFrame")
        bordered_frame.setStyleSheet("""
            #BorderedFrame {
                border: 4px solid black;
                background-color: white;
            }
        """)


        export_button = QPushButton("Export to Excel")
        export_button.setFixedHeight(32)
        export_button.setStyleSheet("""
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
        export_button.clicked.connect(self._export_results_to_excel)


        frame_layout = QGridLayout()
        frame_layout.setContentsMargins(8, 8, 8, 8)
        frame_layout.setSpacing(0)

        frame_layout.addWidget(export_button, 0, 0, 1, 2)
        frame_layout.addItem(QSpacerItem(0, 10, QSizePolicy.Minimum, QSizePolicy.Fixed), 1, 0, 1, 2)
        left_results_container = QWidget()
        left_results_layout = QVBoxLayout(left_results_container)
        left_results_layout.setContentsMargins(0, 0, 0, 0)
        left_results_layout.setSpacing(0)
        left_results_layout.addWidget(self.financial_workspace, stretch=1)
        left_results_layout.addWidget(self.emissions_workspace, stretch=1)

        frame_layout.addWidget(left_results_container, 2, 0)
        frame_layout.addWidget(self.output_workspace, 2, 1)
        frame_layout.setRowStretch(2, 1)
        frame_layout.setColumnStretch(0, 1)
        frame_layout.setColumnStretch(1, 1)

        bordered_frame.setLayout(frame_layout)


        container_layout = QVBoxLayout()
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.addWidget(bordered_frame)
        right_container.setLayout(container_layout)


        # ── Inputs container with header + hide/show toggle ──────────────
        self._inputs_container = QWidget()
        inputs_container = self._inputs_container
        inputs_container.setStyleSheet("background: white;")
        _inputs_vlay = QVBoxLayout(inputs_container)
        _inputs_vlay.setContentsMargins(0, 0, 0, 0)
        _inputs_vlay.setSpacing(0)

        _inputs_header = QWidget()
        _inputs_header.setFixedHeight(28)
        _inputs_header.setStyleSheet(
            "background: #f0f0f0; border-bottom: 1px solid #c0c0c0;"
        )
        _inputs_hlay = QHBoxLayout(_inputs_header)
        _inputs_hlay.setContentsMargins(8, 0, 8, 0)
        _inputs_hlay.setSpacing(6)

        self._inputs_lbl = QLabel("Configured Inputs")
        self._inputs_lbl.setStyleSheet(
            "color: #444444; font-size: 11px; font-weight: bold; background: transparent;"
        )
        _inputs_hlay.addWidget(self._inputs_lbl)
        _inputs_hlay.addStretch()

        self._inputs_toggle_btn = QPushButton("◀ Hide")
        self._inputs_toggle_btn.setFixedHeight(20)
        self._inputs_toggle_btn.setStyleSheet("""
            QPushButton {
                background: white; color: #333333;
                border: 1px solid #bbbbbb; border-radius: 3px;
                font-size: 10px; padding: 0 8px;
            }
            QPushButton:hover {
                background: #e8f5e9; color: #1a7f3c; border-color: #1a7f3c;
            }
        """)
        self._inputs_toggle_btn.clicked.connect(self._toggle_inputs)
        _inputs_hlay.addWidget(self._inputs_toggle_btn)

        _inputs_vlay.addWidget(_inputs_header)
        _inputs_vlay.addWidget(self.workspace_manager)
        self.workspace_manager.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self._main_splitter = QSplitter(Qt.Horizontal)
        self._main_splitter.setHandleWidth(2)
        self._main_splitter.setStyleSheet("QSplitter::handle { background: black; }")
        self._main_splitter.setChildrenCollapsible(True)
        self._main_splitter.addWidget(inputs_container)
        self._main_splitter.addWidget(center_splitter)
        self._main_splitter.addWidget(right_container)
        self._main_splitter.setSizes([260, 900, 620])
        main_splitter = self._main_splitter


        outer_layout.addWidget(main_splitter)


        self.toolbar.show()
    def _toggle_map(self):
        if getattr(self, "_map_visible", True):
            self._saved_center_sizes = self._center_splitter.sizes()
            total = sum(self._saved_center_sizes)
            self._center_splitter.setSizes([28, total - 28])
            self._map_toggle_btn.setText("Show Map")
            self._map_visible = False
        else:
            saved = getattr(self, "_saved_center_sizes", [420, 520])
            self._center_splitter.setSizes(saved)
            self._map_toggle_btn.setText("Hide Map")
            self._map_visible = True

    def _toggle_inputs(self):
        if getattr(self, "_inputs_visible", True):
            # Save the current splitter proportions, then hide the panel
            self._saved_main_sizes = self._main_splitter.sizes()
            self._inputs_container.setVisible(False)
            self._inputs_toggle_btn.setVisible(False)
            self._show_inputs_btn.setVisible(True)
            self._inputs_visible = False
        else:
            # Restore the saved proportions and show the panel
            self._inputs_container.setVisible(True)
            self._inputs_toggle_btn.setVisible(True)
            self._show_inputs_btn.setVisible(False)
            saved = getattr(self, "_saved_main_sizes", [260, 900, 620])
            self._main_splitter.setSizes(saved)
            self._inputs_visible = True

    def _capacity_clicked(self):
        print("Capacity button clicked (placeholder)")

    def run_optimization(self, selected_inputs=None, input_metadata=None):
        self.selected_inputs = selected_inputs
        self.input_metadata = input_metadata

        preparator = PrepareData(self.workspace_manager)
        all_inputs = preparator.run_input_selection_flow(self)

        try:
            self.selected_inputs = all_inputs["selected_inputs"]
            self.input_metadata = all_inputs["input_metadata"]

            print(self.selected_inputs)
        except Exception:
            pass

        if not self.selected_inputs:
            print("⚠️ Optimization cancelled or no inputs selected.")
            return

        try:

            if "stochastic" in self.selected_inputs:
                from OptimizationStochastic import OptimizationInputPreparator, OptimizationPopup
            else:
                from OptimizationDeterministic import OptimizationInputPreparator, OptimizationPopup


            preparator = OptimizationInputPreparator(self.selected_inputs)
            self.optimization_popup = OptimizationPopup(self, preparator)
            self.optimization_popup.exec_()

        except Exception as e:
            print(f"❌ Optimization failed: {e}")

    def _export_results_to_excel(self):
        try:
            tab_index = self.output_workspace.tabs.currentIndex()
            if tab_index < 0:
                QMessageBox.warning(self, "No Tab Selected", "Please select an optimization tab to export.")
                return

            selected_inputs = self. output_workspace.selected_inputs_list[tab_index]
            optimization_data = self.output_workspace.optimizations[tab_index]
            financial_data = self.financial_workspace.financial_data[tab_index]
            emissions_data = self.emissions_workspace.emission_data[tab_index]
            metadata = self.financial_workspace.metadata_list[tab_index]
            tab_name = self.output_workspace.tabs.tabText(tab_index).replace(" ", "_").lower()

            export_to_excel(self, optimization_data, financial_data, emissions_data,
                            metadata, selected_inputs, tab_name)

        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export:\n{str(e)}")

    def _get_coords(self):
        return self.map_widget.get_coordinates() if hasattr(self, "map_widget") else (None, None)

    def _btn_pos(self, btn):
        return btn.mapToGlobal(QPoint(0, btn.height()))

    def _generation(self):
        lat, lon = self._get_coords()
        GenerationPopupHandler(self, self.toolbar, lat, lon, self.workspace_manager).show_popup(self._btn_pos(self._gen_btn))

    def _storage(self):
        StoragePopupHandler(self, self.toolbar, self.workspace_manager).show_popup(self._btn_pos(self._stor_btn))

    def _thermal(self):
        lat, lon = self._get_coords()
        ThermalDemandPopupHandler(self, self.toolbar, lat, lon, self.workspace_manager).show_popup(self._btn_pos(self._therm_btn))

    def _electricity(self):
        ElectricityDemandPopupHandler(self, self.toolbar, self.workspace_manager).show_popup(self._btn_pos(self._elec_btn))

    def _price(self):
        PricePopupHandler(self, self.toolbar, self.workspace_manager).show_popup(self._btn_pos(self._price_btn))

    def _emissions(self):
        EmissionsPopupHandler(self, self.toolbar, self.workspace_manager).show_popup(self._btn_pos(self._emis_btn))

    def _thermal_emissions(self):
        ThermalEmissionsPopupHandler(self, self.toolbar, self.workspace_manager).show_popup(self._btn_pos(self._temis_btn))

    def _previous_system(self):
        PreviousSystemPopupHandler(self, self.toolbar, self.workspace_manager).show_popup(self._btn_pos(self._prev_btn))

    def _clear_main_layout(self):
        while self.main_layout.count():
            widget = self.main_layout.takeAt(0).widget()
            if widget: widget.setParent(None)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MainWindow()
    window.showMaximized()
    sys.exit(app.exec_())