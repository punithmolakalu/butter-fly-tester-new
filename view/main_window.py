"""Main window: View only. Binds to ViewModel."""
from typing import Any, List, Optional, Tuple, cast
import threading
import time
import os
import json

from PyQt5.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTabWidget,
    QLabel,
    QMessageBox,
    QAction,
    QFrame,
    QPushButton,
    QComboBox,
    QGridLayout,
    QGroupBox,
    QFormLayout,
    QSizePolicy,
    QDoubleSpinBox,
    QSpinBox,
    QLineEdit,
    QPlainTextEdit,
    QDialog,
    QFileDialog,
    QScrollArea,
    QStackedWidget,
)
from PyQt5.QtCore import Qt, QTimer, QObject, pyqtSignal, pyqtSlot, QEvent
from PyQt5.QtGui import QPalette, QColor, QShowEvent, QDoubleValidator, QResizeEvent, QCursor, QFocusEvent

# PyQt5 stubs omit many Qt namespace members; cast keeps strict checkers quiet.
QtCompat: Any = cast(Any, Qt)

try:
    import pyqtgraph as _pyqtgraph_mod
    _PG_AVAILABLE = True
except ImportError:
    _PG_AVAILABLE = False
    _pyqtgraph_mod = None
# When graphs are disabled, code paths return early; treat as Any for attribute access.
PG: Any = cast(Any, _pyqtgraph_mod)

from view.dark_theme import (
    COLOR_GREEN,
    COLOR_GREEN_HOVER,
    COLOR_ORANGE,
    COLOR_ORANGE_HOVER,
    COLOR_RED,
    COLOR_RED_HOVER,
    PYQTGRAPH_AXIS_TEXT,
    PYQTGRAPH_PLOT_BACKGROUND,
    PYQTGRAPH_VIEWBOX_RGB,
    get_dark_palette,
    main_stylesheet,
    qpushbutton_local_style,
    qpushbutton_local_style_neutral,
    set_dark_title_bar,
    spinbox_arrow_styles,
)
from start.startnew_dialog import TestInformationDialog
from start.recipe_window import RecipeWindow
from start.recipe_readonly_view import RecipeReadonlyView
from start.window_placement import place_on_secondary_screen_before_show
from view.alignment_window import AlignmentWindow
from view.liv_test_window import LivTestSequenceWindow
from view.per_test_window import PerTestSequenceWindow
from view.spectrum_test_window import SpectrumTestSequenceWindow
from view.temperature_stability_window import TemperatureStabilityWindow

from instruments.actuator import ACTUATOR_DEFAULT_MANUAL_DISTANCE_MM
from operations.per.per_units import mw_series_to_dbm, mw_to_dbm

try:
    from operations.spectrum.trace_plotting import pair_trace_floats as _spectrum_pair_trace_floats
    from operations.spectrum.trace_plotting import spectrum_plot_x_range_nm as _spectrum_plot_x_range_nm
    from operations.spectrum.trace_plotting import spectrum_plot_y_range_dbm as _spectrum_plot_y_range_dbm
except ImportError:
    _spectrum_pair_trace_floats = None
    _spectrum_plot_x_range_nm = None
    _spectrum_plot_y_range_dbm = None


def _log_scan_results(ports, gpib, prm_serials, visa_list, thorlabs_usb=None):
    """Print detected devices to terminal so user can check if instruments are detecting."""
    print("\n[Scan All] Devices detected:")
    if ports:
        print("  COM ports ({}): {}".format(len(ports), ", ".join(ports)))
    else:
        print("  COM ports: none")
    if gpib:
        print("  GPIB ({}): {}".format(len(gpib), ", ".join(gpib)))
    else:
        print("  GPIB: none")
    if prm_serials:
        print("  PRM/Kinesis ({}): {}".format(len(prm_serials), ", ".join(prm_serials)))
    else:
        print("  PRM/Kinesis: none")
    if thorlabs_usb is not None:
        if thorlabs_usb:
            print("  Thorlabs USB VID 0x1313 ({}): {}".format(len(thorlabs_usb), ", ".join(thorlabs_usb)))
        else:
            print("  Thorlabs USB VID 0x1313: none")
    if visa_list:
        print("  VISA all ({}): {}".format(len(visa_list), ", ".join(visa_list)))
    else:
        print("  VISA all: none")
    print("")


def _log_connect_attempts(attempts):
    """Print Connect All attempts to terminal; connection success/fail is printed by workers."""
    if not attempts:
        print("\n[Connect All] No valid addresses selected (run Scan All).\n")
        return
    print("\n[Connect All] Connecting instruments (check below for OK/FAIL):")
    for name, addr in attempts:
        print("  {} -> {}".format(name, addr))
    print("  (Connection results will appear below as each completes.)\n")


class _InitialConnectionScanBridge(QObject):
    """Delivers initial COM/GPIB/VISA scan results from a worker thread to the GUI thread."""

    done = pyqtSignal(object)


class _FullWidthTabWidget(QTabWidget):
    """Tab widget whose tab bar uses the full width; no scroll buttons, all tabs visible."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDocumentMode(True)
        tb = self.tabBar()
        if tb is not None:
            tb.setExpanding(True)
            tb.setUsesScrollButtons(False)
            tb.setElideMode(Qt.ElideNone)  # type: ignore[attr-defined]

    def resizeEvent(self, event):
        super().resizeEvent(event)
        tb = self.tabBar()
        if tb is not None:
            tb.setMinimumWidth(self.width())


class MainWindow(QMainWindow):
    @staticmethod
    def _recipe_display_name(path: str) -> str:
        """Return recipe file name without extension for Details section."""
        p = (path or "").strip()
        if not p:
            return "—"
        base = os.path.basename(p)
        stem, _ = os.path.splitext(base)
        return stem or "—"

    def __init__(self, viewmodel, parent=None):
        super(MainWindow, self).__init__(parent)
        self._viewmodel = viewmodel
        self.setWindowTitle("Butterfly Tester")
        self.setMinimumSize(800, 500)
        self.resize(900, 600)
        # Apply theme before any child widgets exist so nothing is created with the default white Fusion look.
        self.setPalette(get_dark_palette())
        self.setStyleSheet(main_stylesheet())
        self.setAutoFillBackground(True)
        try:
            self.setAttribute(QtCompat.WA_StyledBackground, True)
        except Exception:
            pass

        central = QWidget()
        central.setObjectName("main_content")
        central.setAutoFillBackground(True)
        try:
            central.setAttribute(QtCompat.WA_StyledBackground, True)
        except Exception:
            pass
        pal = QPalette()
        pal.setColor(QPalette.Window, QColor(30, 30, 35))
        central.setPalette(pal)
        central.setStyleSheet("background-color: #1e1e23;")
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(4, 0, 4, 4)  # no top space

        self._build_menu_bar()
        self._initial_scan_bridge = _InitialConnectionScanBridge(self)
        self._initial_scan_bridge.done.connect(self._on_initial_connection_scan_done)
        self.tabs = _FullWidthTabWidget()
        self.tabs.setStyleSheet("QTabWidget::pane { background-color: #1e1e23; }")
        self.tabs.addTab(self._make_main_tab(), "Main")
        self.tabs.addTab(self._make_engineer_control_tab(), "Engineer Control")
        self.tabs.addTab(self._make_recipe_tab(), "Recipe")
        # Placeholders replaced in __init__ by _deferred_install_graph_tabs() before first show (avoids white flash).
        self.tabs.addTab(self._make_graph_tab_placeholder(), "LIV")
        self.tabs.addTab(self._make_graph_tab_placeholder(), "PER")
        self.tabs.addTab(self._make_graph_tab_placeholder(), "Spectrum")
        self.tabs.addTab(self._make_graph_tab_placeholder(), "Temperature Stability")
        self._graph_tabs_installed = False
        self.tabs.addTab(self._make_summary_tab(), "Summary")
        self.tabs.addTab(self._make_plot_tab(), "Plot")
        self.tabs.addTab(self._make_result_tab(), "Result")
        # Fusion + QTabWidget: internal stack can paint default light background before child styles apply.
        _stack = self.tabs.findChild(QStackedWidget)
        if _stack is not None:
            _stack.setAutoFillBackground(True)
            _sp = QPalette()
            _sp.setColor(QPalette.Window, QColor(30, 30, 35))
            _stack.setPalette(_sp)
        self._last_arroyo_readings: Optional[dict] = None  # re-apply when switching tabs so all tabs stay in sync
        self.tabs.currentChanged.connect(self._on_tabs_current_changed)
        _tb = self.tabs.tabBar()
        if _tb is not None:
            _tb.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            _tb.tabBarClicked.connect(self._on_main_tab_bar_clicked)
        self.tabs.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.tabs)

        self._build_footer()
        layout.addWidget(self.footer_frame)

        self._viewmodel.connection_state_changed.connect(self._on_connection_state_changed)
        self._viewmodel.arroyo_readings_updated.connect(self._on_arroyo_readings_updated)
        self._viewmodel.gentec_reading_updated.connect(self._on_gentec_reading_updated)
        self._viewmodel.thorlabs_reading_updated.connect(self._on_thorlabs_reading_updated)
        self._viewmodel.wavemeter_wavelength_updated.connect(self._on_wavemeter_wavelength_updated)
        self._viewmodel.wavemeter_range_applied.connect(self._on_wavemeter_range_applied)
        self._viewmodel.prm_position_updated.connect(self._on_prm_position_updated)
        self._viewmodel.prm_connection_failed.connect(self._on_prm_connection_failed)
        self._viewmodel.prm_error.connect(self._on_prm_error)
        self._viewmodel.prm_command_finished.connect(self._on_prm_command_finished)
        self._viewmodel.status_log_message.connect(self._on_status_log_message)
        self._viewmodel.actuator_status_line.connect(self._on_actuator_status_line)
        self._refresh_footer(self._viewmodel.get_connection_state())

        self.main_start_new_btn.clicked.connect(self._on_start_new_clicked)
        self.main_new_recipe_btn.clicked.connect(self._on_new_recipe_clicked)
        self.main_run_btn.clicked.connect(self._on_run_clicked)
        self.main_stop_btn.clicked.connect(self._on_stop_clicked)
        self.main_align_btn.clicked.connect(self._on_align_clicked)
        # Test status: READY until Run; then Running (blue); then Done (green) or Stopped (red). Pass/Fail set when result in.
        self._test_sequence_executor = None
        self._test_sequence_thread = None
        self._recipe_window = None  # keep reference so New Recipe window is not garbage-collected
        self._alignment_window = None  # keep reference so Alignment window is not garbage-collected
        self._liv_test_window = None  # LIV test sequence live window (other monitor)
        self._per_test_window = None  # PER test sequence live window (other monitor)
        self._spectrum_test_window = None  # Spectrum test step window (other monitor)
        self._stability_test_window = None  # Temperature Stability 1/2 live window (other monitor)
        self._close_per_window_after_home = False
        self._home_actuator_b_after_prm_home = False

        self._arroyo_laser_on = False
        self._arroyo_tec_on = False

        # Stubs until graph tabs load (update paths use getattr / None checks).
        self._liv_calc_overlay_items = []
        self.liv_plot = self.liv_power_curve = self.liv_voltage_curve = self.liv_pd_curve = None
        self.liv_calc_plot = self.liv_calc_power_curve = self.liv_calc_voltage_curve = self.liv_calc_pd_curve = None
        self.liv_calc_power_at_ir = self.liv_calc_current_at_pr = self.liv_calc_threshold = self.liv_calc_slope = None
        self._liv_calc_plot_item = None
        self.per_plot = self.per_power_curve = None
        self.per_result_max_power = self.per_result_min_power = self.per_result_per = self.per_result_angle = None
        self.spectrum_os_plot = self.spectrum_os_curve = None
        self.spectrum_first_os_plot = self.spectrum_first_os_curve = None
        self._last_spectrum_result = None
        self._stability_ts1_curves = []  # [peak, fwhm, smsr, peak_level_dbm] PlotDataItem
        self._stability_ts2_curves = []
        # Plot tab — consolidated mirrors (filled in _make_plot_tab)
        self.result_liv_plot = self.result_liv_power_curve = self.result_liv_voltage_curve = self.result_liv_pd_curve = None
        self.result_spectrum_os_plot = self.result_spectrum_os_curve = None
        self.result_ts1_plot = None
        self.result_ts2_plot = None
        self.result_ts1_curves: List[Any] = []
        self.result_ts2_curves: List[Any] = []
        self.result_per_plot = self.result_per_power_curve = None
        # Plot tab — LIV Results beside LIV graph; PER Results beside Spectrum (filled on final results)
        self.result_plot_liv_min_temp = None
        self.result_plot_liv_max_temp = None
        self.result_plot_liv_min_wl = None
        self.result_plot_liv_max_wl = None
        self.result_plot_liv_power_at_ir = None
        self.result_plot_liv_current_at_pr = None
        self.result_plot_liv_rated_current = None
        self.result_plot_liv_rated_power = None
        self.result_plot_liv_threshold = None
        self.result_plot_liv_slope = None
        self.result_plot_liv_pd_at_ir = None
        self.result_plot_per_sp_max = None
        self.result_plot_per_sp_min = None
        self.result_plot_per_sp_per = None
        self.result_plot_per_sp_angle = None
        self._result_plot_cells: List[Any] = []
        self._result_plot_viewport = None
        self._plot_tab_content: Optional[QWidget] = None  # scroll content; explicit min size for vertical scroll

        # PyQtGraph tabs: built in _complete_heavy_startup() after first show (see main.py QTimer.singleShot).

        # One-click select full value for all spinboxes and value line edits; units (suffix) stay visible
        _app = QApplication.instance()
        if _app is not None:
            _app.installEventFilter(self)

    def _make_graph_tab_placeholder(self) -> QWidget:
        """Dark empty tab; replaced on next event-loop tick with real PyQtGraph content."""
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addStretch()
        w.setStyleSheet("background-color: #1e1e23;")
        w.setMinimumHeight(120)
        return w

    def _complete_heavy_startup(self) -> None:
        """After first window paint: PyQtGraph tabs, lazy Recipe read-only view, then connection setup (main.py schedules)."""
        if getattr(self, "_heavy_startup_done", False):
            return
        self._heavy_startup_done = True
        self._deferred_install_graph_tabs()
        self._ensure_recipe_readonly_view()
        # Was previously in Connection tab __init__ — moved here so the window/layout can paint first.
        self._apply_saved_addresses_and_auto_connect()
        # Next tick: auto-connect (non-blocking worker connects + deferred PRM; see _on_connect_all defer_prm_ms).
        QTimer.singleShot(0, self._run_startup_auto_connect)

    def _deferred_install_graph_tabs(self) -> None:
        """Build LIV/PER/Spectrum/Temperature Stability; replaces placeholders after first show."""
        if getattr(self, "_graph_tabs_installed", False):
            return
        self._graph_tabs_installed = True
        builders = [
            ("LIV", self._make_liv_graph_tab),
            ("PER", self._make_per_graph_tab),
            ("Spectrum", self._make_spectrum_graph_tab),
            ("Temperature Stability", self._make_stability_graph_tab),
        ]
        self.tabs.blockSignals(True)
        try:
            cur = self.tabs.currentIndex()
            for i, (title, factory) in enumerate(builders):
                idx = 3 + i
                self.tabs.removeTab(idx)
                self.tabs.insertTab(idx, factory(), title)
            if 0 <= cur < self.tabs.count():
                self.tabs.setCurrentIndex(cur)
        finally:
            self.tabs.blockSignals(False)

    def eventFilter(self, obj, event):
        """On focus: select full value so one click selects complete number; unit/suffix unchanged."""
        try:
            vp = getattr(self, "_result_plot_viewport", None)
            if vp is not None and obj is vp and event.type() == QEvent.Resize:
                self._sync_result_plot_cell_heights()
        except Exception:
            pass
        try:
            if isinstance(event, QFocusEvent) and event.gotFocus():
                if isinstance(obj, (QDoubleSpinBox, QSpinBox)):
                    obj.selectAll()
                elif isinstance(obj, QLineEdit) and not obj.isReadOnly():
                    obj.selectAll()
        except Exception:
            # Never let focus helper break the app event loop.
            pass
        return super(MainWindow, self).eventFilter(obj, event)

    def showEvent(self, event: QShowEvent):
        super(MainWindow, self).showEvent(event)
        try:
            set_dark_title_bar(int(self.winId()), True)
        except Exception:
            pass
        _tb_show = self.tabs.tabBar()
        if _tb_show is not None:
            _tb_show.setMinimumWidth(self.tabs.width())
        # If window was not opened via main.py (no _heavy_startup_scheduled_from_main), defer heavy work here.
        if not getattr(self, "_heavy_startup_scheduled_from_main", False) and not getattr(self, "_heavy_startup_done", False):
            QTimer.singleShot(0, self._complete_heavy_startup)

    def _run_startup_auto_connect(self) -> None:
        """Run after deferred startup: Connect All from saved addresses (PRM Kinesis connect delayed so GUI stays responsive)."""
        saved = getattr(self, "_pending_startup_auto_connect", None)
        self._pending_startup_auto_connect = None
        if not isinstance(saved, dict) or saved.get("auto_connect", "1") != "1":
            return
        self._on_connect_all(use_saved=saved, wavemeter_delay_ms=80, defer_prm_ms=350)

    def _build_menu_bar(self):
        menubar = self.menuBar()
        if menubar is None:
            return
        menubar.setNativeMenuBar(False)
        file_menu = menubar.addMenu("&File")
        if file_menu is not None:
            exit_act = QAction("E&xit", self)
            exit_act.triggered.connect(self._on_file_exit)
            file_menu.addAction(exit_act)
        help_menu = menubar.addMenu("&Help")
        if help_menu is not None:
            about_act = QAction("&About", self)
            about_act.triggered.connect(self._on_about)
            help_menu.addAction(about_act)

    def _make_main_tab(self):
        """Main tab: 4 equal columns. Col1: Laser Details, TEC Details, Status Log. Col2: Start, Details. Col3–4: empty."""
        w = QWidget()
        grid = QGridLayout(w)
        grid.setSpacing(12)
        box_style = (
            "QGroupBox { font-weight: bold; font-size: 15px; border: 1px solid #3a3a42; border-radius: 4px; "
            "margin: 0; padding: 18px 6px 6px 6px; background-color: #25252c; } "
            "QGroupBox::title { subcontrol-origin: padding; subcontrol-position: top left; top: 2px; left: 10px; "
            "padding: 0 6px; color: #e6e6e6; font-size: 15px; }"
        )

        # Column 1: Laser Details, TEC Details, Status Log
        read_style = "color: #b0b0b0; font-size: 13px;"
        value_style = "color: #e6e6e6; font-size: 14px; font-weight: bold;"
        led_off = "background-color: #555; border-radius: 8px; min-width: 16px; max-width: 16px; min-height: 16px; max-height: 16px;"

        laser_details_box = QGroupBox("Laser Details")
        laser_details_box.setStyleSheet(box_style)
        laser_details_box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)  # do not stretch height
        laser_grid = QGridLayout(laser_details_box)
        laser_grid.setHorizontalSpacing(8)
        laser_grid.setVerticalSpacing(6)
        laser_grid.addWidget(QLabel("Current"), 0, 0)
        self.main_laser_current_value = QLabel("-")
        self.main_laser_current_value.setStyleSheet(value_style)
        laser_grid.addWidget(self.main_laser_current_value, 0, 1)
        laser_grid.addWidget(QLabel("mA"), 0, 2)
        laser_grid.addWidget(QLabel("Voltage"), 1, 0)
        self.main_laser_voltage_value = QLabel("-")
        self.main_laser_voltage_value.setStyleSheet(value_style)
        laser_grid.addWidget(self.main_laser_voltage_value, 1, 1)
        laser_grid.addWidget(QLabel("V"), 1, 2)
        laser_grid.addWidget(QLabel("Set Current"), 2, 0)
        self.main_laser_set_current_value = QLabel("-")
        self.main_laser_set_current_value.setStyleSheet(value_style)
        laser_grid.addWidget(self.main_laser_set_current_value, 2, 1)
        laser_grid.addWidget(QLabel("mA"), 2, 2)
        laser_grid.addWidget(QLabel("Laser ON/OFF"), 3, 0)
        self.main_laser_status_value = QLabel("OFF")
        self.main_laser_status_value.setStyleSheet(value_style)
        laser_grid.addWidget(self.main_laser_status_value, 3, 1)
        self.main_laser_led = QLabel()
        self.main_laser_led.setFixedSize(16, 16)
        self.main_laser_led.setStyleSheet(led_off)
        laser_grid.addWidget(self.main_laser_led, 3, 2)
        for lbl in laser_details_box.findChildren(QLabel):
            if lbl not in (self.main_laser_current_value, self.main_laser_voltage_value, self.main_laser_set_current_value, self.main_laser_status_value, self.main_laser_led):
                lbl.setStyleSheet(read_style)

        tec_details_box = QGroupBox("TEC Details")
        tec_details_box.setStyleSheet(box_style)
        tec_details_box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        tec_grid = QGridLayout(tec_details_box)
        tec_grid.setHorizontalSpacing(8)
        tec_grid.setVerticalSpacing(6)
        tec_grid.addWidget(QLabel("Voltage"), 0, 0)
        self.main_tec_voltage_value = QLabel("-")
        self.main_tec_voltage_value.setStyleSheet(value_style)
        tec_grid.addWidget(self.main_tec_voltage_value, 0, 1)
        tec_grid.addWidget(QLabel("V"), 0, 2)
        tec_grid.addWidget(QLabel("Temperature"), 1, 0)
        self.main_tec_temp_value = QLabel("-")
        self.main_tec_temp_value.setStyleSheet(value_style)
        tec_grid.addWidget(self.main_tec_temp_value, 1, 1)
        tec_grid.addWidget(QLabel("C"), 1, 2)
        tec_grid.addWidget(QLabel("Current"), 2, 0)
        self.main_tec_current_value = QLabel("-")
        self.main_tec_current_value.setStyleSheet(value_style)
        tec_grid.addWidget(self.main_tec_current_value, 2, 1)
        tec_grid.addWidget(QLabel("A"), 2, 2)
        tec_grid.addWidget(QLabel("Set Temperature"), 3, 0)
        self.main_tec_set_temp_value = QLabel("-")
        self.main_tec_set_temp_value.setStyleSheet(value_style)
        tec_grid.addWidget(self.main_tec_set_temp_value, 3, 1)
        tec_grid.addWidget(QLabel("C"), 3, 2)
        tec_grid.addWidget(QLabel("TEC ON/OFF"), 4, 0)
        self.main_tec_status_value = QLabel("OFF")
        self.main_tec_status_value.setStyleSheet(value_style)
        tec_grid.addWidget(self.main_tec_status_value, 4, 1)
        self.main_tec_led = QLabel()
        self.main_tec_led.setFixedSize(16, 16)
        self.main_tec_led.setStyleSheet(led_off)
        tec_grid.addWidget(self.main_tec_led, 4, 2)
        for lbl in tec_details_box.findChildren(QLabel):
            if lbl not in (self.main_tec_voltage_value, self.main_tec_temp_value, self.main_tec_current_value, self.main_tec_set_temp_value, self.main_tec_status_value, self.main_tec_led):
                lbl.setStyleSheet(read_style)

        status_log_box = QGroupBox("Status Log")
        status_log_box.setStyleSheet(box_style)
        status_inner = QVBoxLayout(status_log_box)
        status_header = QHBoxLayout()
        status_header.addStretch()
        self.main_status_log_clear_btn = QPushButton("Clear")
        self.main_status_log_clear_btn.setObjectName("btn_clear")
        self.main_status_log_clear_btn.clicked.connect(lambda: self.main_status_log.clear())
        status_header.addWidget(self.main_status_log_clear_btn)
        status_inner.addLayout(status_header)
        self.main_status_log = QPlainTextEdit()
        self.main_status_log.setReadOnly(True)
        self.main_status_log.setPlaceholderText("Log messages will appear here.")
        self.main_status_log.setMinimumHeight(72)
        self.main_status_log.setStyleSheet(
            "QPlainTextEdit { font-size: 11px; padding: 4px 6px; background-color: #25252c; color: #e6e6e6; border: 1px solid #3a3a42; }"
        )
        status_inner.addWidget(self.main_status_log)

        # Left column: Laser + TEC + Status Log, free layout, tight spacing so TEC is right under Laser
        left_column = QWidget()
        left_column_layout = QVBoxLayout(left_column)
        left_column_layout.setContentsMargins(0, 0, 0, 0)
        left_column_layout.setSpacing(4)
        left_column_layout.addWidget(laser_details_box)
        left_column_layout.addWidget(tec_details_box)
        left_column_layout.addWidget(status_log_box, 1)
        grid.addWidget(left_column, 0, 0, 3, 1)

        # Column 2: Start — vertical stack (no row layout), taller box and buttons (height unchanged)
        start_box = QGroupBox("Start")
        start_box.setStyleSheet(box_style)
        start_box.setMinimumHeight(300)
        start_inner = QVBoxLayout(start_box)
        start_inner.setSpacing(12)
        start_btn_min_h = 48
        self.main_start_new_btn = QPushButton("Start New")
        self.main_start_new_btn.setObjectName("btn_start_new")
        self.main_start_new_btn.setMinimumHeight(start_btn_min_h)
        self.main_start_new_btn.setStyleSheet(qpushbutton_local_style(COLOR_ORANGE, COLOR_ORANGE_HOVER))
        start_inner.addWidget(self.main_start_new_btn)
        self.main_new_recipe_btn = QPushButton("New Recipe")
        self.main_new_recipe_btn.setToolTip("Opens the Recipe window on the other monitor.")
        self.main_new_recipe_btn.setMinimumHeight(start_btn_min_h)
        self.main_new_recipe_btn.setStyleSheet(qpushbutton_local_style_neutral())
        start_inner.addWidget(self.main_new_recipe_btn)
        self.main_run_btn = QPushButton("Run")
        self.main_run_btn.setObjectName("btn_run")
        self.main_run_btn.setMinimumHeight(start_btn_min_h)
        self.main_run_btn.setStyleSheet(qpushbutton_local_style(COLOR_GREEN, COLOR_GREEN_HOVER))
        start_inner.addWidget(self.main_run_btn)
        self.main_stop_btn = QPushButton("Stop")
        self.main_stop_btn.setObjectName("btn_stop")
        self.main_stop_btn.setMinimumHeight(start_btn_min_h)
        self.main_stop_btn.setStyleSheet(qpushbutton_local_style(COLOR_RED, COLOR_RED_HOVER))
        start_inner.addWidget(self.main_stop_btn)
        start_inner.addStretch()
        grid.addWidget(start_box, 0, 1)

        details_box = QGroupBox("Details")
        details_box.setStyleSheet(box_style)
        details_inner = QVBoxLayout(details_box)
        detail_label_style = "color: #b0b0b0; font-size: 12px;"
        detail_value_style = "color: #e6e6e6; font-size: 13px; min-height: 18px;"
        # Reading box: values displayed when Start New is clicked (you can wire display logic later)
        def detail_row(name):
            row = QHBoxLayout()
            lbl = QLabel(name + ":")
            lbl.setStyleSheet(detail_label_style)
            val = QLabel("—")
            val.setStyleSheet(detail_value_style)
            val.setMinimumWidth(80)
            row.addWidget(lbl)
            row.addWidget(val, 1, QtCompat.AlignLeft)
            return row, val
        r1, self.details_op_name = detail_row("OP name")
        details_inner.addLayout(r1)
        r2, self.details_recipe = detail_row("Recipe")
        details_inner.addLayout(r2)
        r3, self.details_serial_no = detail_row("Serial no")
        details_inner.addLayout(r3)
        r4, self.details_part_no = detail_row("Part no")
        details_inner.addLayout(r4)
        r5, self.details_wavelength = detail_row("Wavelength")
        details_inner.addLayout(r5)
        r6, self.details_smsr_on = detail_row("SMSR on")
        details_inner.addLayout(r6)
        details_inner.addStretch()
        grid.addWidget(details_box, 1, 1)

        # Column 3: Test status, ALIGN, Time Elapsed, readings, Data Viewer, Reason for Failure
        col3 = QWidget()
        col3_layout = QVBoxLayout(col3)
        col3_layout.setSpacing(10)
        read_style_c3 = "color: #b0b0b0; font-size: 12px;"
        value_box_style = "background-color: #25252c; color: #e6e6e6; border: 1px solid #3a3a42; padding: 6px; min-height: 22px;"
        # Circular indicator: equal width/height + border-radius half = circle
        circle_size = 120
        circle_radius = circle_size // 2
        circle_style = (
            "background-color: #555; color: white; border-radius: {}px; font-size: 14px; font-weight: bold; "
            "min-width: {}px; max-width: {}px; min-height: {}px; max-height: {}px;"
        ).format(circle_radius, circle_size, circle_size, circle_size, circle_size)
        # Test Finished | Pass/Fail row
        status_row = QHBoxLayout()
        status_row.setSpacing(12)
        test_finished_col = QVBoxLayout()
        tf_lbl = QLabel("Test")
        tf_lbl.setStyleSheet(read_style_c3)
        test_finished_col.addWidget(tf_lbl)
        self.main_test_ready_indicator = QLabel("READY")
        self.main_test_ready_indicator.setAlignment(QtCompat.AlignCenter)
        self.main_test_ready_indicator.setStyleSheet(circle_style)
        self.main_test_ready_indicator.setFixedSize(circle_size, circle_size)
        test_finished_col.addWidget(self.main_test_ready_indicator, 0, QtCompat.AlignCenter)
        status_row.addLayout(test_finished_col)
        status_row.addStretch()
        pass_fail_col = QVBoxLayout()
        pf_lbl = QLabel("Pass/Fail")
        pf_lbl.setStyleSheet(read_style_c3)
        pass_fail_col.addWidget(pf_lbl)
        self.main_pass_fail_indicator = QLabel("--")
        self.main_pass_fail_indicator.setAlignment(QtCompat.AlignCenter)
        self.main_pass_fail_indicator.setStyleSheet(circle_style)
        self.main_pass_fail_indicator.setFixedSize(circle_size, circle_size)
        pass_fail_col.addWidget(self.main_pass_fail_indicator, 0, QtCompat.AlignCenter)
        status_row.addLayout(pass_fail_col)
        col3_layout.addLayout(status_row)
        # ALIGN button (orange — same role as theme QPushButton#btn_align; local sheet so color always wins)
        self.main_align_btn = QPushButton("ALIGN")
        self.main_align_btn.setObjectName("btn_align")
        self.main_align_btn.setMinimumHeight(48)
        self.main_align_btn.setStyleSheet(
            f"QPushButton#btn_align {{ background-color: {COLOR_ORANGE}; color: white; font-weight: bold; "
            f"font-size: 14px; padding: 10px 24px; border: 1px solid #3a3a42; }}"
            f"QPushButton#btn_align:hover {{ background-color: {COLOR_ORANGE_HOVER}; }}"
            f"QPushButton#btn_align:pressed {{ background-color: {COLOR_ORANGE_HOVER}; }}"
            f"QPushButton#btn_align:disabled {{ background-color: #25252c; color: #808080; }}"
        )
        col3_layout.addWidget(self.main_align_btn)
        # Time Elapsed
        time_elapsed_lbl = QLabel("Time Elapsed")
        time_elapsed_lbl.setStyleSheet(read_style_c3)
        col3_layout.addWidget(time_elapsed_lbl)
        time_row = QHBoxLayout()
        self.main_time_min = QLineEdit()
        self.main_time_min.setReadOnly(True)
        self.main_time_min.setMaximumWidth(48)
        self.main_time_min.setAlignment(QtCompat.AlignCenter)
        self.main_time_min.setText("0")
        self.main_time_min.setStyleSheet(value_box_style)
        time_row.addWidget(self.main_time_min)
        time_colon = QLabel(":")
        time_colon.setStyleSheet(value_box_style)
        time_colon.setAlignment(QtCompat.AlignCenter)
        time_colon.setMaximumWidth(24)
        time_row.addWidget(time_colon)
        self.main_time_sec = QLineEdit()
        self.main_time_sec.setReadOnly(True)
        self.main_time_sec.setMaximumWidth(48)
        self.main_time_sec.setAlignment(QtCompat.AlignCenter)
        self.main_time_sec.setText("0")
        self.main_time_sec.setStyleSheet(value_box_style)
        time_row.addWidget(self.main_time_sec)
        col3_layout.addLayout(time_row)
        # Gentec Power
        gp_row = QHBoxLayout()
        gp_lbl = QLabel("Gentec Power:")
        gp_lbl.setStyleSheet(read_style_c3)
        gp_row.addWidget(gp_lbl)
        self.main_gentec_power_value = QLineEdit()
        self.main_gentec_power_value.setReadOnly(True)
        self.main_gentec_power_value.setStyleSheet(value_box_style)
        self.main_gentec_power_value.setText("0")
        gp_row.addWidget(self.main_gentec_power_value)
        col3_layout.addLayout(gp_row)
        # Gentec Mult
        gm_row = QHBoxLayout()
        gm_lbl = QLabel("Gentec Mult:")
        gm_lbl.setStyleSheet(read_style_c3)
        gm_row.addWidget(gm_lbl)
        self.main_gentec_mult_value = QLineEdit()
        self.main_gentec_mult_value.setReadOnly(True)
        self.main_gentec_mult_value.setStyleSheet(value_box_style)
        self.main_gentec_mult_value.setText("0")
        gm_row.addWidget(self.main_gentec_mult_value)
        col3_layout.addLayout(gm_row)
        # Thorlabs Power
        tp_row = QHBoxLayout()
        tp_lbl = QLabel("Thorlabs Power:")
        tp_lbl.setStyleSheet(read_style_c3)
        tp_row.addWidget(tp_lbl)
        self.main_thorlabs_power_value = QLineEdit()
        self.main_thorlabs_power_value.setReadOnly(True)
        self.main_thorlabs_power_value.setStyleSheet(value_box_style)
        self.main_thorlabs_power_value.setText("0")
        tp_row.addWidget(self.main_thorlabs_power_value)
        col3_layout.addLayout(tp_row)
        # Data Viewer button
        self.main_data_viewer_btn = QPushButton("Data Viewer")
        col3_layout.addWidget(self.main_data_viewer_btn)
        # Reason for Failure
        failure_frame = QFrame()
        failure_frame.setStyleSheet("QFrame { border: 1px solid #3a3a42; border-radius: 4px; padding: 8px; background-color: #25252c; }")
        failure_layout = QVBoxLayout(failure_frame)
        failure_header = QHBoxLayout()
        failure_lbl = QLabel("Reason for Failure")
        failure_lbl.setStyleSheet("color: #e6e6e6; font-weight: bold; font-size: 13px;")
        failure_header.addWidget(failure_lbl)
        failure_header.addStretch()
        self.main_failure_clear_btn = QPushButton("Clear")
        self.main_failure_clear_btn.setObjectName("btn_clear")
        self.main_failure_clear_btn.clicked.connect(lambda: self.main_failure_reason.clear())
        failure_header.addWidget(self.main_failure_clear_btn)
        failure_layout.addLayout(failure_header)
        self.main_failure_reason = QPlainTextEdit()
        self.main_failure_reason.setPlaceholderText(
            "When a test fails, specific reasons (LIV, PER, etc.) appear here automatically."
        )
        self.main_failure_reason.setMinimumHeight(80)
        self.main_failure_reason.setStyleSheet("background-color: #25252c; color: #e6e6e6; border: 1px solid #3a3a42;")
        failure_layout.addWidget(self.main_failure_reason)
        col3_layout.addWidget(failure_frame)
        col3_layout.addStretch()
        grid.addWidget(col3, 0, 2, 3, 1)
        empty_col4 = QFrame()
        empty_col4.setFrameShape(QFrame.StyledPanel)
        empty_col4.setStyleSheet("background-color: transparent; border: none;")
        grid.addWidget(empty_col4, 0, 3, 3, 1)

        # Equal column stretch
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)
        grid.setColumnStretch(3, 1)
        grid.setRowStretch(2, 1)
        return w

    def _build_liv_plot_widget(self, include_voltage_pd: bool = True, title: Optional[str] = None):
        """Shared LIV pyqtgraph bundle (main LIV tab, Plot tab mirror)."""
        pw = PG.PlotWidget()
        pw.setBackground("w")
        p1 = cast(Any, pw.getPlotItem())
        p1.getViewBox().setBackgroundColor((255, 255, 255))
        p1.showGrid(x=True, y=True, alpha=0.35)
        tc = "#333333"
        p1.setTitle(title if title is not None else "LIV — Power / Voltage / PD vs Current", color=tc)
        axis_pen = PG.mkPen(color=tc, width=1)
        p1.setLabel('bottom', 'Current mA', color=tc)
        p1.setLabel('left', 'Power (mW)', color=tc)
        p1.layout.setColumnMinimumWidth(0, 70)
        left_axis = p1.getAxis('left')
        left_axis.setPen(axis_pen)
        left_axis.setTextPen(axis_pen)
        p1.getAxis('bottom').setPen(axis_pen)
        p1.getAxis('bottom').setTextPen(axis_pen)
        legend = p1.addLegend(offset=(10, 10), labelTextColor=tc)
        legend.setParentItem(p1.vb)
        legend.anchor((1, 1), (1, 1))
        power_curve = pw.plot([], [], pen=PG.mkPen('#000000', width=2), name='Power',
            symbol='d', symbolSize=6, symbolBrush='#000000', symbolPen=PG.mkPen('#000000'))
        voltage_curve = None
        pd_curve = None
        if include_voltage_pd:
            # Same as LIV popup: main ViewBox must sit behind secondary ViewBoxes (stacking / z-order)
            # or voltage/PD curves are invisible under the paint stack.
            p1.vb.setZValue(-100)
            p2 = PG.ViewBox()
            p1.showAxis('right')
            p1.scene().addItem(p2)
            p1.getAxis('right').linkToView(p2)
            p2.setXLink(p1.vb)
            p2.setZValue(10)
            p1.getAxis('right').setLabel('Voltage(v)', color=tc)
            p1.getAxis('right').setPen(axis_pen)
            p1.getAxis('right').setTextPen(axis_pen)
            voltage_curve = PG.PlotDataItem([], [], pen=PG.mkPen('#000000', width=2, style=QtCompat.DashLine), name='Voltage',
                symbol='s', symbolSize=5, symbolBrush='#000000', symbolPen=PG.mkPen('#000000'))
            p2.addItem(voltage_curve)
            legend.addItem(voltage_curve, 'Voltage')
            p3 = PG.ViewBox()
            ax3 = PG.AxisItem('right')
            p1.layout.addItem(ax3, 2, 3)
            p1.layout.setColumnMinimumWidth(3, 72)
            p1.scene().addItem(p3)
            ax3.linkToView(p3)
            p3.setXLink(p1.vb)
            p3.setZValue(10)
            ax3.setLabel('PD current (MDI)', color=tc)
            ax3.setPen(axis_pen)
            ax3.setTextPen(axis_pen)
            pd_curve = PG.PlotDataItem([], [], pen=PG.mkPen('#000000', width=2, style=QtCompat.DotLine), name='PD (MDI)',
                symbol='t', symbolSize=5, symbolBrush='#000000', symbolPen=PG.mkPen('#000000'))
            p3.addItem(pd_curve)
            legend.addItem(pd_curve, 'PD (MDI)')

            def _sync():
                r = p1.vb.sceneBoundingRect()
                p2.setGeometry(r)
                p3.setGeometry(r)
                p2.linkedViewChanged(p1.vb, p2.XAxis)
                p3.linkedViewChanged(p1.vb, p3.XAxis)
            _sync()
            p1.vb.sigResized.connect(_sync)
        return pw, p1, power_curve, voltage_curve, pd_curve

    def _build_stability_combined_plotwidget(self, title: str) -> Tuple[Any, List[Any]]:
        """
        One white plot vs Temp (°C): Peak λ (left), SMSR, Peak level (dBm), SpecWidth/FWHM (nm) on linked right axes.
        Returns (PlotWidget, [peak, fwhm, smsr, peak_level] PlotDataItems).
        """
        pw = PG.PlotWidget()
        pw.setBackground("w")
        p1 = cast(Any, pw.getPlotItem())
        p1.vb.setZValue(-100)
        p1.getViewBox().setBackgroundColor((255, 255, 255))
        p1.showGrid(x=True, y=True, alpha=0.35)
        p1.setTitle(title, color="#333333")
        tc = "#333333"
        axis_pen = PG.mkPen(color=tc, width=1)
        p1.setLabel("bottom", "Temp (°C)", color=tc)
        p1.setLabel("left", "Peak λ (nm)", color=tc)
        p1.layout.setColumnMinimumWidth(0, 72)
        for axn in ("left", "bottom"):
            p1.getAxis(axn).setPen(axis_pen)
            p1.getAxis(axn).setTextPen(axis_pen)
        legend = p1.addLegend(offset=(10, 10), labelTextColor=tc)
        legend.setParentItem(p1.vb)
        legend.anchor((1, 1), (1, 1))

        c_peak = pw.plot(
            [],
            [],
            pen=PG.mkPen("#c62828", width=2),
            name="PeakWL",
            symbol="s",
            symbolSize=6,
            symbolBrush="#c62828",
            symbolPen=PG.mkPen("#c62828"),
        )

        p2 = PG.ViewBox()
        p1.showAxis("right")
        p1.scene().addItem(p2)
        p1.getAxis("right").linkToView(p2)
        p2.setXLink(p1.vb)
        p2.setZValue(10)
        p1.getAxis("right").setLabel("SMSR (dB)", color=tc)
        p1.getAxis("right").setPen(axis_pen)
        p1.getAxis("right").setTextPen(axis_pen)
        c_smsr = PG.PlotDataItem(
            [],
            [],
            pen=PG.mkPen("#000000", width=2),
            name="SMSR",
            symbol="x",
            symbolSize=7,
            symbolBrush="#000000",
            symbolPen=PG.mkPen("#000000"),
        )
        p2.addItem(c_smsr)
        legend.addItem(c_smsr, "SMSR")

        p3 = PG.ViewBox()
        ax3 = PG.AxisItem("right")
        p1.layout.addItem(ax3, 2, 3)
        p1.layout.setColumnMinimumWidth(3, 76)
        p1.scene().addItem(p3)
        ax3.linkToView(p3)
        p3.setXLink(p1.vb)
        p3.setZValue(10)
        ax3.setLabel("Peak level (dBm)", color=tc)
        ax3.setPen(axis_pen)
        ax3.setTextPen(axis_pen)
        c_pk_lv = PG.PlotDataItem(
            [],
            [],
            pen=PG.mkPen("#1565c0", width=2, style=QtCompat.DashLine),
            name="Peak level",
            symbol="o",
            symbolSize=5,
            symbolBrush="#1565c0",
            symbolPen=PG.mkPen("#1565c0"),
        )
        p3.addItem(c_pk_lv)
        legend.addItem(c_pk_lv, "Peak level (dBm)")

        p4 = PG.ViewBox()
        ax4 = PG.AxisItem("right")
        p1.layout.addItem(ax4, 2, 4)
        p1.layout.setColumnMinimumWidth(4, 76)
        p1.scene().addItem(p4)
        ax4.linkToView(p4)
        p4.setXLink(p1.vb)
        p4.setZValue(10)
        ax4.setLabel("SpecWidth (nm)", color=tc)
        ax4.setPen(axis_pen)
        ax4.setTextPen(axis_pen)
        c_fwhm = PG.PlotDataItem(
            [],
            [],
            pen=PG.mkPen("#1565c0", width=2),
            name="SpecWidth",
            symbol="t",
            symbolSize=6,
            symbolBrush="#1565c0",
            symbolPen=PG.mkPen("#1565c0"),
        )
        p4.addItem(c_fwhm)
        legend.addItem(c_fwhm, "SpecWidth (nm)")

        def _sync():
            r = p1.vb.sceneBoundingRect()
            p2.setGeometry(r)
            p3.setGeometry(r)
            p4.setGeometry(r)
            p2.linkedViewChanged(p1.vb, p2.XAxis)
            p3.linkedViewChanged(p1.vb, p3.XAxis)
            p4.linkedViewChanged(p1.vb, p4.XAxis)

        _sync()
        p1.vb.sigResized.connect(_sync)

        curves = [c_peak, c_fwhm, c_smsr, c_pk_lv]
        return pw, curves

    @staticmethod
    def _stability_autorange_y(vb: Any, xs: List[float], ys: List[float]) -> None:
        if vb is None or not xs or not ys or len(xs) != len(ys):
            return
        vals = []
        for y in ys:
            try:
                fv = float(y)
            except (TypeError, ValueError):
                continue
            if fv != fv:  # nan
                continue
            vals.append(fv)
        if not vals:
            return
        lo, hi = min(vals), max(vals)
        span = hi - lo
        pad = max(span * 0.12, 1e-12)
        if span < 1e-18:
            pad = max(abs(lo) * 0.05, 0.01)
        vb.setYRange(lo - pad, hi + pad, padding=0)

    def _autorange_stability_combined(
        self,
        curves: List[Any],
        tx: List[float],
        py: List[float],
        fy: List[float],
        sy: List[float],
        lv: List[float],
    ) -> None:
        """Fit X on main ViewBox and Y on each linked ViewBox (skip NaNs)."""
        if not curves or len(curves) < 4 or not tx:
            return
        try:
            xs = [float(x) for x in tx]
            x0, x1 = min(xs), max(xs)
            dx = x1 - x0
            px = max(dx * 0.06, 0.25) if dx > 1e-12 else 0.5
            c0 = curves[0]
            vb0 = c0.getViewBox()
            if vb0 is not None:
                vb0.setXRange(x0 - px, x1 + px, padding=0)
        except Exception:
            pass
        for c, ylist in zip(curves, (py, fy, sy, lv)):
            try:
                vb = c.getViewBox()
                self._stability_autorange_y(vb, tx, ylist)
            except Exception:
                pass

    def _make_liv_graph_tab(self):
        """LIV tab with inner tabs: Plot and Calculation."""
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)
        if not _PG_AVAILABLE:
            layout.addWidget(QLabel("pyqtgraph required for graphs. Install: pip install pyqtgraph"))
            self.liv_plot = self.liv_power_curve = self.liv_voltage_curve = self.liv_pd_curve = None
            self.liv_calc_plot = self.liv_calc_power_curve = self.liv_calc_voltage_curve = self.liv_calc_pd_curve = None
            self._liv_calc_overlay_items = []
            return w

        inner_tabs = QTabWidget()
        inner_tabs.setObjectName("livInnerTabs")
        # Cleaner native-style tabs on Windows; no eliding so "Calculation" stays one full label.
        inner_tabs.setDocumentMode(True)
        _liv_inner_tab_bar = inner_tabs.tabBar()
        if _liv_inner_tab_bar is not None:
            _liv_inner_tab_bar.setElideMode(Qt.ElideNone)  # type: ignore[attr-defined]
            _liv_inner_tab_bar.setUsesScrollButtons(False)
        # Plot tab
        plot_tab = QWidget()
        plot_layout = QVBoxLayout(plot_tab)
        self.liv_plot, _, self.liv_power_curve, self.liv_voltage_curve, self.liv_pd_curve = self._build_liv_plot_widget()
        plot_layout.addWidget(self.liv_plot, 1)
        inner_tabs.addTab(plot_tab, "Plot")

        # Calculation tab
        calc_tab = QWidget()
        calc_layout = QVBoxLayout(calc_tab)
        calc_group = QGroupBox("Calculation")
        calc_group.setStyleSheet(
            "QGroupBox { font-weight: bold; font-size: 12px; color: #e6e6e6; } "
            "QLabel { color: #e6e6e6; font-size: 11px; }"
        )
        calc_form = QFormLayout(calc_group)
        self.liv_calc_power_at_ir = QLabel("—")
        self.liv_calc_current_at_pr = QLabel("—")
        self.liv_calc_threshold = QLabel("—")
        self.liv_calc_slope = QLabel("—")
        calc_form.addRow("Power @ Rated Current (mW):", self.liv_calc_power_at_ir)
        calc_form.addRow("Current @ Rated Power (mA):", self.liv_calc_current_at_pr)
        calc_form.addRow("Threshold Current Ith (mA):", self.liv_calc_threshold)
        calc_form.addRow("Slope Efficiency (mW/mA):", self.liv_calc_slope)
        calc_layout.addWidget(calc_group)

        self.liv_calc_plot, self._liv_calc_plot_item, self.liv_calc_power_curve, self.liv_calc_voltage_curve, self.liv_calc_pd_curve = self._build_liv_plot_widget(include_voltage_pd=False)
        self._liv_calc_overlay_items = []
        calc_hint = QLabel(
            "Plot: solid black=Power | dashed black=Voltage | dotted black=PD. "
            "Overlays: vertical dashed=Ith | vertical dotted=Ir | horizontal dash-dot=Pr | star=P@Ir | diamond=I@Pr (all black)."
        )
        calc_hint.setStyleSheet("color: #bbbbbb; font-size: 10px;")
        calc_hint.setWordWrap(True)
        calc_layout.addWidget(calc_hint)
        calc_layout.addWidget(self.liv_calc_plot, 1)
        inner_tabs.addTab(calc_tab, "Calculation")

        layout.addWidget(inner_tabs, 1)
        return w

    def _make_per_graph_tab(self):
        """PER tab: final Thorlabs curve + PER Results (updated when the run ends). Live samples plot only in the PER window."""
        w = QWidget()
        main_layout = QHBoxLayout(w)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.setSpacing(12)
        if not _PG_AVAILABLE:
            main_layout.addWidget(QLabel("pyqtgraph required for graphs."))
            self.per_plot = self.per_power_curve = None
            self.per_result_max_power = self.per_result_min_power = self.per_result_per = self.per_result_angle = None
            return w
        # Left: Power Graph
        graph_widget = QWidget()
        graph_layout = QVBoxLayout(graph_widget)
        graph_layout.setContentsMargins(0, 0, 0, 0)
        graph_label = QLabel("Power vs angle (Thorlabs, dBm)")
        graph_label.setStyleSheet("font-weight: bold; font-size: 13px; color: #e6e6e6;")
        graph_layout.addWidget(graph_label)
        pw = PG.PlotWidget()
        pw.setBackground("w")
        cast(Any, pw.getPlotItem()).getViewBox().setBackgroundColor((255, 255, 255))
        pw.showGrid(x=True, y=True, alpha=0.35)
        tc = "#333333"
        axis_pen = PG.mkPen(color=tc, width=1)
        pw.setLabel("left", "Power (dBm)", color=tc)
        pw.setLabel("bottom", "Angle (deg)", color=tc)
        pi_per = cast(Any, pw.getPlotItem())
        pi_per.getAxis('left').setPen(axis_pen)
        pi_per.getAxis('left').setTextPen(axis_pen)
        pi_per.getAxis('bottom').setPen(axis_pen)
        pi_per.getAxis('bottom').setTextPen(axis_pen)
        self.per_power_curve = pw.plot(
            [], [], pen=PG.mkPen("#1f77b4", width=1.5), antialias=True
        )
        self.per_plot = pw
        graph_layout.addWidget(pw, 1)
        main_layout.addWidget(graph_widget, 1)
        # Right: PER Results panel
        result_style = "QGroupBox { font-weight: bold; font-size: 13px; color: #e6e6e6; } QLabel { color: #e6e6e6; }"
        results_group = QGroupBox("PER Results")
        results_group.setStyleSheet(result_style)
        results_group.setMinimumWidth(180)
        results_layout = QFormLayout(results_group)
        self.per_result_max_power = QLabel("—")
        self.per_result_min_power = QLabel("—")
        self.per_result_per = QLabel("—")
        self.per_result_angle = QLabel("—")
        for lbl in (self.per_result_max_power, self.per_result_min_power, self.per_result_per, self.per_result_angle):
            lbl.setStyleSheet("color: #e6e6e6; font-size: 12px;")
        results_layout.addRow("Max Power (dBm):", self.per_result_max_power)
        results_layout.addRow("Min Power (dBm):", self.per_result_min_power)
        results_layout.addRow("PER:", self.per_result_per)
        results_layout.addRow("Angle:", self.per_result_angle)
        main_layout.addWidget(results_group, 0, QtCompat.AlignTop)
        return w

    def _make_spectrum_graph_tab(self):
        """Spectrum tab: inner tabs for second sweep (primary) and first sweep; white plot area, black trace."""
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)
        if not _PG_AVAILABLE:
            layout.addWidget(QLabel("pyqtgraph required for graphs."))
            self.spectrum_os_plot = None
            self.spectrum_os_curve = None
            self.spectrum_first_os_plot = None
            self.spectrum_first_os_curve = None
            return w

        title_lbl = QLabel("Spectrum")
        title_lbl.setStyleSheet("font-weight: bold; color: #e6e6e6; font-size: 13px;")
        layout.addWidget(title_lbl)

        # White plot area + dark axis text; black trace (matches Spectrum secondary window).
        self._spectrum_axis_text_color = "#333333"
        tc = self._spectrum_axis_text_color
        axis_pen = PG.mkPen(color=tc, width=1)
        self._spectrum_axis_bottom_default = "Wavelength (nm) — peak aligned to wavemeter"
        self._spectrum_axis_left_default = "Level (dBm)"

        def _mk_spectrum_pg(initial_title: str) -> Tuple[Any, Any]:
            pw = PG.PlotWidget()
            pw.setBackground("w")
            pi = cast(Any, pw.getPlotItem())
            pi.getViewBox().setBackgroundColor((255, 255, 255))
            pi.setTitle(initial_title, color=tc)
            pi.showGrid(x=True, y=True, alpha=0.35)
            pi.setLabel("bottom", self._spectrum_axis_bottom_default, color=tc)
            pi.setLabel("left", self._spectrum_axis_left_default, color=tc)
            for axn in ("left", "bottom"):
                pi.getAxis(axn).setPen(axis_pen)
                pi.getAxis(axn).setTextPen(axis_pen)
            # Line only (no per-point markers) — hundreds of OSA samples look like stems/noise with symbols on.
            curve = pw.plot([], [], pen=PG.mkPen("#000000", width=1.5), antialias=True)
            return pw, curve

        inner = QTabWidget()
        inner.setObjectName("spectrumInnerTabs")
        inner.setDocumentMode(True)
        _sp_bar = inner.tabBar()
        if _sp_bar is not None:
            _sp_bar.setElideMode(Qt.ElideNone)  # type: ignore[attr-defined]

        tab_second = QWidget()
        lay_second = QVBoxLayout(tab_second)
        lay_second.setContentsMargins(0, 0, 0, 0)
        pw2, c2 = _mk_spectrum_pg("Ando sweep — LVL (dBm)")
        lay_second.addWidget(pw2, 1)
        self.spectrum_os_plot = pw2
        self.spectrum_os_curve = c2
        inner.addTab(tab_second, "Second sweep")

        tab_first = QWidget()
        lay_first = QVBoxLayout(tab_first)
        lay_first.setContentsMargins(0, 0, 0, 0)
        pw1, c1 = _mk_spectrum_pg("First sweep — LVL (dBm)")
        lay_first.addWidget(pw1, 1)
        self.spectrum_first_os_plot = pw1
        self.spectrum_first_os_curve = c1
        inner.addTab(tab_first, "First sweep")

        sum_style = (
            "QGroupBox { font-weight: bold; font-size: 12px; color: #e6e6e6; } "
            "QLabel { color: #c8c8c8; font-size: 11px; }"
        )
        sum_second = QGroupBox("second sweep result")
        sum_second.setStyleSheet(sum_style)
        sum_second.setMinimumWidth(200)
        sform2 = QFormLayout(sum_second)
        self.spectrum_peak_wl = QLabel("—")
        self.spectrum_peak_dbm = QLabel("—")
        self.spectrum_fwhm = QLabel("—")
        self.spectrum_smsr = QLabel("—")
        self.spectrum_pass_label = QLabel("—")
        for lb in (
            self.spectrum_peak_wl,
            self.spectrum_peak_dbm,
            self.spectrum_fwhm,
            self.spectrum_smsr,
            self.spectrum_pass_label,
        ):
            lb.setStyleSheet("color: #e6e6e6; font-size: 12px;")
        self.spectrum_wavemeter_reading = QLabel("—")
        self.spectrum_wavemeter_reading.setStyleSheet("color: #e6e6e6; font-size: 12px;")
        sform2.addRow("Wavemeter reading (nm):", self.spectrum_wavemeter_reading)
        sform2.addRow("Peak wavelength (nm):", self.spectrum_peak_wl)
        sform2.addRow("Peak level (dBm):", self.spectrum_peak_dbm)
        sform2.addRow("FWHM (nm):", self.spectrum_fwhm)
        sform2.addRow("SMSR (dB):", self.spectrum_smsr)
        sform2.addRow("Pass / fail:", self.spectrum_pass_label)

        sum_first = QGroupBox("first sweep result")
        sum_first.setStyleSheet(sum_style)
        sum_first.setMinimumWidth(200)
        sform1 = QFormLayout(sum_first)
        self.spectrum_first_wavemeter_reading = QLabel("—")
        self.spectrum_first_peak_wl = QLabel("—")
        self.spectrum_first_peak_dbm = QLabel("—")
        self.spectrum_first_fwhm = QLabel("—")
        self.spectrum_first_smsr = QLabel("—")
        self.spectrum_first_pass_label = QLabel("—")
        for lb in (
            self.spectrum_first_wavemeter_reading,
            self.spectrum_first_peak_wl,
            self.spectrum_first_peak_dbm,
            self.spectrum_first_fwhm,
            self.spectrum_first_smsr,
            self.spectrum_first_pass_label,
        ):
            lb.setStyleSheet("color: #e6e6e6; font-size: 12px;")
        sform1.addRow("Wavemeter reading (nm):", self.spectrum_first_wavemeter_reading)
        sform1.addRow("Peak wavelength (nm):", self.spectrum_first_peak_wl)
        sform1.addRow("Peak level (dBm):", self.spectrum_first_peak_dbm)
        sform1.addRow("FWHM (nm):", self.spectrum_first_fwhm)
        sform1.addRow("SMSR (dB):", self.spectrum_first_smsr)
        sform1.addRow("Pass / fail:", self.spectrum_first_pass_label)

        page_second = QWidget()
        lay_page_second = QVBoxLayout(page_second)
        lay_page_second.setContentsMargins(0, 0, 0, 0)
        lay_page_second.addWidget(sum_second)
        lay_page_second.addStretch(1)

        btn_save_first = QPushButton("Save first sweep results only")
        btn_save_first.setObjectName("spectrumSaveFirstSweepBtn")
        btn_save_first.clicked.connect(self._save_first_sweep_results_only)
        page_first = QWidget()
        lay_page_first = QVBoxLayout(page_first)
        lay_page_first.setContentsMargins(0, 0, 0, 0)
        lay_page_first.addWidget(sum_first)
        lay_page_first.addWidget(btn_save_first, 0, QtCompat.AlignLeft)
        lay_page_first.addStretch(1)

        right_stack = QStackedWidget()
        right_stack.addWidget(page_second)
        right_stack.addWidget(page_first)
        inner.currentChanged.connect(right_stack.setCurrentIndex)

        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(inner, 1)
        row.addWidget(right_stack, 0, QtCompat.AlignTop)
        layout.addLayout(row, 1)
        return w

    def _make_stability_graph_tab(self):
        """Temperature Stability: side-by-side combined plots (Peak λ, SpecWidth, SMSR, peak level vs Temp)."""
        w = QWidget()
        layout = QHBoxLayout(w)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(10)
        self._stability_ts1_curves = []
        self._stability_ts2_curves = []
        if not _PG_AVAILABLE:
            layout.addWidget(QLabel("pyqtgraph required for Temperature Stability graphs."))
            return w
        pw1, self._stability_ts1_curves = self._build_stability_combined_plotwidget("Temp Stability 1")
        pw2, self._stability_ts2_curves = self._build_stability_combined_plotwidget("Temp Stability 2")
        layout.addWidget(pw1, 1)
        layout.addWidget(pw2, 1)
        return w

    def _recipe_liv_wavelength_min_max(self) -> Tuple[Optional[float], Optional[float]]:
        """Nominal / min–max wavelength (nm) from loaded recipe for Plot-tab LIV labels."""
        d = getattr(self, "_current_recipe_data", None) or {}
        if not isinstance(d, dict):
            return (None, None)
        op = d.get("OPERATIONS") or {}
        gen = op.get("GENERAL") if isinstance(op.get("GENERAL"), dict) else {}
        liv = op.get("LIV") if isinstance(op.get("LIV"), dict) else {}

        def _f(keys: Tuple[str, ...], *sources: Any) -> Optional[float]:
            for src in sources:
                if not isinstance(src, dict):
                    continue
                for k in keys:
                    if k in src and src[k] is not None and str(src[k]).strip() != "":
                        try:
                            return float(src[k])
                        except (TypeError, ValueError):
                            pass
            return None

        wmin = _f(("wavelength_min_nm", "wavelength_min", "wl_min"), liv, gen)
        wmax = _f(("wavelength_max_nm", "wavelength_max", "wl_max"), liv, gen)
        wnom = _f(("wavelength", "Wavelength"), liv, gen, d)
        if wmin is not None and wmax is not None:
            return (wmin, wmax)
        if wnom is not None:
            return (wnom, wnom)
        return (None, None)

    def _recipe_liv_rated_current_power_mw(self) -> Tuple[Optional[float], Optional[float]]:
        d = getattr(self, "_current_recipe_data", None) or {}
        if not isinstance(d, dict):
            return (None, None)
        op = d.get("OPERATIONS") or {}
        liv = op.get("LIV") if isinstance(op.get("LIV"), dict) else {}
        ir = None
        pr = None
        try:
            if liv.get("rated_current_mA") is not None:
                ir = float(liv["rated_current_mA"])
        except (TypeError, ValueError):
            pass
        try:
            if liv.get("rated_power_mW") is not None:
                pr = float(liv["rated_power_mW"])
        except (TypeError, ValueError):
            pass
        return (ir, pr)

    def _build_plot_tab_liv_results_panel(self) -> QGroupBox:
        """LIV Results beside the Plot-tab LIV graph (numeric summary; filled in _on_liv_result)."""
        gb = QGroupBox("LIV Results")
        gb.setStyleSheet(
            "QGroupBox { font-weight: bold; font-size: 11px; color: #e6e6e6; border: 1px solid #3a3a42; "
            "border-radius: 4px; margin-top: 6px; padding-top: 6px; } "
            "QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }"
        )
        gb.setMinimumWidth(210)
        gb.setMaximumWidth(270)
        gb.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        outer = QVBoxLayout(gb)
        outer.setContentsMargins(8, 10, 8, 8)
        outer.setSpacing(4)
        val_style = (
            "QLineEdit { background-color: #3a3a3e; color: #e6e6e6; border: 1px inset #555560; "
            "border-radius: 2px; padding: 2px 4px; min-height: 18px; font-size: 10px; }"
        )
        form = QFormLayout()
        form.setSpacing(4)
        form.setContentsMargins(0, 0, 0, 0)
        rows = (
            ("Min temp (°C):", "result_plot_liv_min_temp"),
            ("Max temp (°C):", "result_plot_liv_max_temp"),
            ("Min λ (nm):", "result_plot_liv_min_wl"),
            ("Max λ (nm):", "result_plot_liv_max_wl"),
            ("Power @ rated I (mW):", "result_plot_liv_power_at_ir"),
            ("Current @ rated P (mA):", "result_plot_liv_current_at_pr"),
            ("Rated current (mA):", "result_plot_liv_rated_current"),
            ("Rated power (mW):", "result_plot_liv_rated_power"),
            ("Threshold Ith (mA):", "result_plot_liv_threshold"),
            ("Slope efficiency (mW/mA):", "result_plot_liv_slope"),
            ("PD @ rated I (MDI):", "result_plot_liv_pd_at_ir"),
        )
        for label_text, attr in rows:
            ed = QLineEdit("—")
            ed.setReadOnly(True)
            ed.setStyleSheet(val_style)
            form.addRow(label_text, ed)
            setattr(self, attr, ed)
        outer.addLayout(form)
        return gb

    def _apply_plot_tab_liv_results(self, r: Any) -> None:
        """Fill Plot-tab LIV Results from LIVProcessResult + recipe wavelength / rated limits."""

        def _set(edit: Any, text: str) -> None:
            if edit is not None:
                edit.setText(text)

        def _fmt(v: Any, nd: int = 4) -> str:
            if v is None:
                return "—"
            try:
                return ("{:." + str(nd) + "f}").format(float(v))
            except (TypeError, ValueError):
                return "—"

        if r is None:
            self._clear_plot_tab_liv_results()
            return
        tmin = getattr(r, "tec_temp_min", None)
        tmax = getattr(r, "tec_temp_max", None)
        _set(getattr(self, "result_plot_liv_min_temp", None), _fmt(tmin, 2))
        _set(getattr(self, "result_plot_liv_max_temp", None), _fmt(tmax, 2))
        wl_lo, wl_hi = self._recipe_liv_wavelength_min_max()
        _set(getattr(self, "result_plot_liv_min_wl", None), _fmt(wl_lo, 3) if wl_lo is not None else "—")
        _set(getattr(self, "result_plot_liv_max_wl", None), _fmt(wl_hi, 3) if wl_hi is not None else "—")
        _set(getattr(self, "result_plot_liv_power_at_ir", None), _fmt(getattr(r, "power_at_rated_current", None), 4))
        _set(getattr(self, "result_plot_liv_current_at_pr", None), _fmt(getattr(r, "current_at_rated_power", None), 4))
        ir_r, pr_r = self._recipe_liv_rated_current_power_mw()
        _set(getattr(self, "result_plot_liv_rated_current", None), _fmt(ir_r, 3) if ir_r is not None else "—")
        _set(getattr(self, "result_plot_liv_rated_power", None), _fmt(pr_r, 3) if pr_r is not None else "—")
        _set(getattr(self, "result_plot_liv_threshold", None), _fmt(getattr(r, "threshold_current", None), 4))
        _set(getattr(self, "result_plot_liv_slope", None), _fmt(getattr(r, "slope_efficiency", None), 4))
        _set(getattr(self, "result_plot_liv_pd_at_ir", None), _fmt(getattr(r, "pd_at_rated_current", None), 4))

    def _clear_plot_tab_liv_results(self) -> None:
        for name in (
            "result_plot_liv_min_temp",
            "result_plot_liv_max_temp",
            "result_plot_liv_min_wl",
            "result_plot_liv_max_wl",
            "result_plot_liv_power_at_ir",
            "result_plot_liv_current_at_pr",
            "result_plot_liv_rated_current",
            "result_plot_liv_rated_power",
            "result_plot_liv_threshold",
            "result_plot_liv_slope",
            "result_plot_liv_pd_at_ir",
        ):
            w = getattr(self, name, None)
            if w is not None:
                w.setText("—")

    def _build_plot_tab_per_results_panel(self, slot: str) -> QGroupBox:
        """
        Compact PER Results block for Plot tab (label above read-only value), beside Spectrum.
        slot: 'sp' — assigns self.result_plot_per_{slot}_* QLineEdit refs.
        """
        gb = QGroupBox("PER Results")
        gb.setStyleSheet(
            "QGroupBox { font-weight: bold; font-size: 11px; color: #e6e6e6; border: 1px solid #3a3a42; "
            "border-radius: 4px; margin-top: 6px; padding-top: 6px; } "
            "QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }"
        )
        gb.setFixedWidth(118)
        gb.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
        outer = QVBoxLayout(gb)
        outer.setContentsMargins(8, 10, 8, 8)
        outer.setSpacing(8)
        outer.setAlignment(QtCompat.AlignTop | QtCompat.AlignLeft)
        val_style = (
            "QLineEdit { background-color: #3a3a3e; color: #e6e6e6; border: 1px inset #555560; "
            "border-radius: 2px; padding: 3px 5px; min-height: 20px; font-size: 11px; }"
        )
        rows = (
            ("Max Power", "max"),
            ("Min Power", "min"),
            ("PER", "per"),
            ("Angle", "angle"),
        )
        for label_text, key in rows:
            col = QVBoxLayout()
            col.setSpacing(2)
            col.setAlignment(QtCompat.AlignLeft | QtCompat.AlignTop)
            lab = QLabel(label_text)
            lab.setStyleSheet("color: #c8c8c8; font-size: 11px;")
            lab.setAlignment(QtCompat.AlignLeft | QtCompat.AlignVCenter)
            col.addWidget(lab)
            edit = QLineEdit("—")
            edit.setReadOnly(True)
            edit.setFrame(True)
            edit.setStyleSheet(val_style)
            col.addWidget(edit)
            outer.addLayout(col)
            setattr(self, "result_plot_per_{}_{}".format(slot, key), edit)
        return gb

    def _apply_per_result_values(self, result: Any) -> None:
        """Update PER tab + Plot-tab LIV/Spectrum PER Results fields from a final PER result object."""
        max_t = "{:.3f}".format(mw_to_dbm(getattr(result, "max_power", 0) or 0))
        min_t = "{:.3f}".format(mw_to_dbm(getattr(result, "min_power", 0) or 0))
        per_t = "{:.2f}".format(getattr(result, "per_db", 0) or 0)
        ang_t = "{:.2f}".format(getattr(result, "max_angle", 0) or 0)
        for w in (
            getattr(self, "per_result_max_power", None),
            getattr(self, "result_plot_per_sp_max", None),
        ):
            if w is not None:
                w.setText(max_t)
        for w in (
            getattr(self, "per_result_min_power", None),
            getattr(self, "result_plot_per_sp_min", None),
        ):
            if w is not None:
                w.setText(min_t)
        for w in (
            getattr(self, "per_result_per", None),
            getattr(self, "result_plot_per_sp_per", None),
        ):
            if w is not None:
                w.setText(per_t)
        for w in (
            getattr(self, "per_result_angle", None),
            getattr(self, "result_plot_per_sp_angle", None),
        ):
            if w is not None:
                w.setText(ang_t)

    def _clear_per_result_displays(self) -> None:
        """Reset PER result text on PER tab and Plot-tab Spectrum PER panel."""
        self._clear_plot_tab_liv_results()
        for w in (
            getattr(self, "per_result_max_power", None),
            getattr(self, "per_result_min_power", None),
            getattr(self, "per_result_per", None),
            getattr(self, "per_result_angle", None),
            getattr(self, "result_plot_per_sp_max", None),
            getattr(self, "result_plot_per_sp_min", None),
            getattr(self, "result_plot_per_sp_per", None),
            getattr(self, "result_plot_per_sp_angle", None),
        ):
            if w is not None:
                w.setText("—")

    def _sync_result_plot_cell_heights(self) -> None:
        """
        Plot tab: five equal-height graph panels in a 2-column grid that uses the full scroll viewport width.
        row0: LIV | Spectrum, row1: Temp 1 | 2, row2: PER (left). Two rows visible; scroll for PER.
        Content width is forced to the viewport width so there is no empty strip on the right.
        """
        cells = getattr(self, "_result_plot_cells", None) or []
        vp = getattr(self, "_result_plot_viewport", None)
        content = getattr(self, "_plot_tab_content", None)
        if not cells or vp is None:
            return
        try:
            vw = int(vp.width())
            vh = int(vp.height())
            if vw < 80 or vh < 80:
                return
            # Two visible rows in viewport: 2*row_h + 10 (gap) + 8 (grid top+bottom margins)
            row_h = max(160, (vh - 18) // 2)
            _wmax = 16777215  # reset any prior setFixedSize width on frames
            for fr in cells:
                fr.setMinimumWidth(0)
                fr.setMaximumWidth(_wmax)
                fr.setFixedHeight(row_h)
                fr.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            if content is not None:
                # Match viewport width exactly so the 2-column grid expands edge-to-edge (no dead space on the right).
                content.setFixedWidth(vw)
                min_h = 3 * row_h + 28  # 3 rows + 2 row gaps + grid top/bottom margins
                content.setMinimumHeight(min_h)
        except Exception:
            pass

    def _make_plot_tab(self) -> QWidget:
        """Plot tab — scrollable grid: 2×2 (LIV, Spectrum | TS1, TS2) then PER below; equal cell sizes."""
        outer = QWidget()
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(8, 8, 8, 8)
        outer_layout.setSpacing(0)
        if not _PG_AVAILABLE:
            self.result_liv_plot = self.result_liv_power_curve = self.result_liv_voltage_curve = self.result_liv_pd_curve = None
            self.result_spectrum_os_plot = self.result_spectrum_os_curve = None
            self.result_ts1_plot = None
            self.result_ts2_plot = None
            self.result_ts1_curves = []
            self.result_ts2_curves = []
            self.result_per_plot = self.result_per_power_curve = None
            self._result_plot_cells = []
            self._result_plot_viewport = None
            self._plot_tab_content = None
            outer_layout.addWidget(QLabel("pyqtgraph required for the Plot tab. Install: pip install pyqtgraph"))
            return outer

        scroll = QScrollArea()
        scroll.setObjectName("plotTabScroll")
        # False: do not shrink content to the viewport — otherwise all five graphs fit on one page with no scroll.
        scroll.setWidgetResizable(False)
        scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        content = QWidget()
        self._plot_tab_content = content
        content.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Minimum)
        grid = QGridLayout(content)
        grid.setSpacing(10)
        grid.setContentsMargins(4, 4, 4, 4)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        self._result_plot_cells = []

        def _cell_frame(title: str, plot_widget: QWidget) -> QFrame:
            fr = QFrame()
            fr.setStyleSheet(
                "QFrame { background-color: #25252c; border: 1px solid #3a3a42; border-radius: 4px; }"
            )
            vl = QVBoxLayout(fr)
            vl.setContentsMargins(6, 6, 6, 6)
            vl.setSpacing(4)
            hl = QLabel(title)
            hl.setStyleSheet("font-weight: bold; color: #e6e6e6; font-size: 12px;")
            hl.setFixedHeight(22)
            vl.addWidget(hl)
            plot_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            vl.addWidget(plot_widget, 1)
            self._result_plot_cells.append(fr)
            return fr

        # 1 LIV, 2 Spectrum, 3–4 TS1/TS2 (combined multi-axis), 5 PER — same cell footprint; scroll for row 3.
        self.result_liv_plot, _, self.result_liv_power_curve, self.result_liv_voltage_curve, self.result_liv_pd_curve = (
            self._build_liv_plot_widget()
        )

        tc_sp = "#333333"
        axis_pen_sp = PG.mkPen(color=tc_sp, width=1)
        result_sp = PG.PlotWidget()
        result_sp.setBackground("w")
        pi_sp = cast(Any, result_sp.getPlotItem())
        pi_sp.getViewBox().setBackgroundColor((255, 255, 255))
        pi_sp.setTitle("Spectrum — second sweep (dBm)", color=tc_sp)
        pi_sp.showGrid(x=True, y=True, alpha=0.35)
        pi_sp.setLabel("bottom", "Wavelength (nm)", color=tc_sp)
        pi_sp.setLabel("left", "Level (dBm)", color=tc_sp)
        for axn in ("left", "bottom"):
            pi_sp.getAxis(axn).setPen(axis_pen_sp)
            pi_sp.getAxis(axn).setTextPen(axis_pen_sp)
        self.result_spectrum_os_curve = result_sp.plot([], [], pen=PG.mkPen("#000000", width=1.5), antialias=True)
        self.result_spectrum_os_plot = result_sp

        self.result_ts1_plot, self.result_ts1_curves = self._build_stability_combined_plotwidget("Temp Stability 1")
        self.result_ts2_plot, self.result_ts2_curves = self._build_stability_combined_plotwidget("Temp Stability 2")

        self.result_per_plot = PG.PlotWidget()
        self.result_per_plot.setBackground("w")
        pi_per = cast(Any, self.result_per_plot.getPlotItem())
        pi_per.getViewBox().setBackgroundColor((255, 255, 255))
        self.result_per_plot.showGrid(x=True, y=True, alpha=0.35)
        tc_per = "#333333"
        pen_per = PG.mkPen(color=tc_per, width=1)
        self.result_per_plot.setLabel("left", "Power (dBm)", color=tc_per)
        self.result_per_plot.setLabel("bottom", "Angle (deg)", color=tc_per)
        pi_per.getAxis("left").setPen(pen_per)
        pi_per.getAxis("left").setTextPen(pen_per)
        pi_per.getAxis("bottom").setPen(pen_per)
        pi_per.getAxis("bottom").setTextPen(pen_per)
        self.result_per_power_curve = self.result_per_plot.plot(
            [], [], pen=PG.mkPen("#1f77b4", width=1.5), antialias=True
        )

        liv_inner = QWidget()
        liv_h = QHBoxLayout(liv_inner)
        liv_h.setContentsMargins(0, 0, 0, 0)
        liv_h.setSpacing(8)
        liv_h.addWidget(self.result_liv_plot, 1)
        liv_h.addWidget(self._build_plot_tab_liv_results_panel(), 0, QtCompat.AlignTop)

        spec_inner = QWidget()
        spec_h = QHBoxLayout(spec_inner)
        spec_h.setContentsMargins(0, 0, 0, 0)
        spec_h.setSpacing(8)
        spec_h.addWidget(self.result_spectrum_os_plot, 1)
        spec_h.addWidget(self._build_plot_tab_per_results_panel("sp"), 0, QtCompat.AlignTop)

        # Row 0: LIV | Spectrum — row 1: Temp 1 | Temp 2 — row 2: PER (same cell size as others; scroll to view)
        grid.addWidget(_cell_frame("LIV", liv_inner), 0, 0)
        grid.addWidget(_cell_frame("Spectrum", spec_inner), 0, 1)
        grid.addWidget(_cell_frame("Temperature stability 1", self.result_ts1_plot), 1, 0)
        grid.addWidget(_cell_frame("Temperature stability 2", self.result_ts2_plot), 1, 1)
        grid.addWidget(_cell_frame("PER", self.result_per_plot), 2, 0)

        scroll.setWidget(content)
        outer_layout.addWidget(scroll, 1)

        vp = scroll.viewport()
        self._result_plot_viewport = vp
        vp.installEventFilter(self)
        QTimer.singleShot(0, self._sync_result_plot_cell_heights)
        QTimer.singleShot(120, self._sync_result_plot_cell_heights)
        return outer

    def _make_result_tab(self) -> QWidget:
        """Result tab — placeholder (consolidated graphs are on the Plot tab)."""
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(16, 16, 16, 16)
        msg = QLabel(
            "Consolidated LIV, Spectrum, Temperature Stability, and PER graphs are on the Plot tab. "
            "Use the Summary tab for the numeric summary fields."
        )
        msg.setWordWrap(True)
        msg.setStyleSheet("color: #c8c8c8; font-size: 12px;")
        lay.addWidget(msg)
        lay.addStretch(1)
        return w

    def _clear_all_result_graphs(self):
        """Clear LIV, PER, Spectrum graphs so they show empty. Call when starting a new run."""
        if not _PG_AVAILABLE:
            return
        lpc = getattr(self, "liv_power_curve", None)
        if lpc is not None:
            lpc.setData([], [])
            lvv = self.liv_voltage_curve
            lpd = self.liv_pd_curve
            if lvv is not None:
                lvv.setData([], [])
            if lpd is not None:
                lpd.setData([], [])
        lpc2 = getattr(self, "liv_calc_power_curve", None)
        if lpc2 is not None:
            lpc2.setData([], [])
            lvv2 = getattr(self, "liv_calc_voltage_curve", None)
            lpd2 = getattr(self, "liv_calc_pd_curve", None)
            if lvv2 is not None:
                lvv2.setData([], [])
            if lpd2 is not None:
                lpd2.setData([], [])
            for it in getattr(self, "_liv_calc_overlay_items", []) or []:
                try:
                    self._liv_calc_plot_item.removeItem(it)
                except Exception:
                    pass
            self._liv_calc_overlay_items = []
        for nm in ("liv_calc_power_at_ir", "liv_calc_current_at_pr", "liv_calc_threshold", "liv_calc_slope"):
            lbl = getattr(self, nm, None)
            if lbl is not None:
                lbl.setText("—")
        ppc = getattr(self, "per_power_curve", None)
        if ppc is not None:
            ppc.setData([], [])
        self._clear_per_result_displays()
        sc = getattr(self, "spectrum_os_curve", None)
        if sc is not None:
            sc.setData([], [])
        scf = getattr(self, "spectrum_first_os_curve", None)
        if scf is not None:
            scf.setData([], [])
        for c in getattr(self, "_stability_ts1_curves", []) or []:
            try:
                c.setData([], [])
            except Exception:
                pass
        for c in getattr(self, "_stability_ts2_curves", []) or []:
            try:
                c.setData([], [])
            except Exception:
                pass
        # Plot tab mirrors
        rlp = getattr(self, "result_liv_power_curve", None)
        if rlp is not None:
            rlp.setData([], [])
            rlv = getattr(self, "result_liv_voltage_curve", None)
            rpd = getattr(self, "result_liv_pd_curve", None)
            if rlv is not None:
                rlv.setData([], [])
            if rpd is not None:
                rpd.setData([], [])
        rsc = getattr(self, "result_spectrum_os_curve", None)
        if rsc is not None:
            rsc.setData([], [])
        for c in getattr(self, "result_ts1_curves", []) or []:
            try:
                c.setData([], [])
            except Exception:
                pass
        for c in getattr(self, "result_ts2_curves", []) or []:
            try:
                c.setData([], [])
            except Exception:
                pass
        rpc = getattr(self, "result_per_power_curve", None)
        if rpc is not None:
            rpc.setData([], [])
        for nm in (
            "spectrum_wavemeter_reading",
            "spectrum_peak_wl",
            "spectrum_peak_dbm",
            "spectrum_fwhm",
            "spectrum_smsr",
            "spectrum_pass_label",
            "spectrum_first_wavemeter_reading",
            "spectrum_first_peak_wl",
            "spectrum_first_peak_dbm",
            "spectrum_first_fwhm",
            "spectrum_first_smsr",
            "spectrum_first_pass_label",
        ):
            lb = getattr(self, nm, None)
            if lb is not None:
                lb.setText("—")
        for nm in ("spectrum_pass_label", "spectrum_first_pass_label"):
            lb = getattr(self, nm, None)
            if lb is not None:
                lb.setStyleSheet("color: #e6e6e6; font-size: 12px;")
        self._last_spectrum_result = None
        try:
            self._reset_spectrum_plot_axis_labels()
        except Exception:
            pass

    def _make_summary_tab(self):
        """Summary panel: dark theme so labels and value boxes are visible; layout as spec with Serial #, IPS Part Number, two columns."""
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        # Dark theme: no white background — panel and value boxes use dark bg, light text so everything is visible
        summary_style = (
            "QFrame#summary_panel { background-color: #25252c; border: 1px solid #3a3a42; border-radius: 4px; } "
            "QLabel { color: #e6e6e6; font-size: 11pt; } "
            "QLineEdit { background-color: #2d2d34; color: #e6e6e6; border: 1px solid #3a3a42; "
            "padding: 4px 6px; min-height: 22px; max-height: 24px; font-size: 11pt; } "
            "QLineEdit[readOnly=\"true\"] { background-color: #2d2d34; }"
        )
        panel = QFrame()
        panel.setObjectName("summary_panel")
        panel.setStyleSheet(summary_style)
        panel.setMinimumWidth(560)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setSpacing(12)
        panel_layout.setContentsMargins(20, 18, 20, 20)

        def value_box(default_text="0", width=70):
            le = QLineEdit()
            le.setReadOnly(True)
            le.setAlignment(QtCompat.AlignRight)
            le.setText(default_text)
            le.setMinimumWidth(width)
            le.setMaximumHeight(26)
            return le

        # Title: Summary:
        title_lbl = QLabel("Summary:")
        title_lbl.setStyleSheet("font-weight: bold; color: #e6e6e6; font-size: 12pt;")
        panel_layout.addWidget(title_lbl)

        # Top row: Serial # and IPS Part Number (wider value boxes)
        top_row = QHBoxLayout()
        top_row.setSpacing(24)
        serial_lbl = QLabel("Serial # :")
        serial_lbl.setMinimumWidth(120)
        self.summary_serial = value_box("", 180)
        top_row.addWidget(serial_lbl)
        top_row.addWidget(self.summary_serial, 0)
        ips_lbl = QLabel("IPS Part Number :")
        ips_lbl.setMinimumWidth(140)
        self.summary_ips_part = value_box("", 180)
        top_row.addWidget(ips_lbl)
        top_row.addWidget(self.summary_ips_part, 0)
        top_row.addStretch()
        panel_layout.addLayout(top_row)

        # Two columns: left and right
        columns = QHBoxLayout()
        columns.setSpacing(48)
        left_form = QFormLayout()
        left_form.setSpacing(10)
        left_form.setLabelAlignment(QtCompat.AlignLeft)
        self.summary_test_temp = value_box("0", 72)
        self.summary_threshold_current = value_box("0", 72)
        self.summary_slope_efficiency = value_box("0", 72)
        self.summary_max_current = value_box("0", 72)
        self.summary_rated_power = value_box("0", 72)
        self.summary_power_at_max_current = value_box("0", 72)
        self.summary_i_at_rated_power = value_box("0", 72)
        left_form.addRow("Test Temperature (°C) :", self.summary_test_temp)
        left_form.addRow("Threshold Current(mA) :", self.summary_threshold_current)
        left_form.addRow("Slope Efficiency :", self.summary_slope_efficiency)
        left_form.addRow("Max Current (mA) :", self.summary_max_current)
        left_form.addRow("Rated Power(mW) :", self.summary_rated_power)
        left_form.addRow("Power @ Max Current(mW) :", self.summary_power_at_max_current)
        left_form.addRow("I @ Rated Power (mA) :", self.summary_i_at_rated_power)
        columns.addLayout(left_form)

        right_form = QFormLayout()
        right_form.setSpacing(10)
        right_form.setLabelAlignment(QtCompat.AlignLeft)
        # Peak Wavelength(nm) Min [value] @ [temp] C
        pw_min_row = QHBoxLayout()
        self.summary_pw_min = value_box("0", 72)
        pw_min_row.addWidget(self.summary_pw_min)
        pw_min_row.addWidget(QLabel(" @ "))
        self.summary_pw_min_temp = value_box("0", 56)
        pw_min_row.addWidget(self.summary_pw_min_temp)
        pw_min_row.addWidget(QLabel(" C"))
        pw_min_row.addStretch()
        right_form.addRow("Peak Wavelength(nm) Min :", pw_min_row)
        # Peak Wavelength(nm) Max [value] @ [temp] C
        pw_max_row = QHBoxLayout()
        self.summary_pw_max = value_box("0", 72)
        pw_max_row.addWidget(self.summary_pw_max)
        pw_max_row.addWidget(QLabel(" @ "))
        self.summary_pw_max_temp = value_box("0", 56)
        pw_max_row.addWidget(self.summary_pw_max_temp)
        pw_max_row.addWidget(QLabel(" C"))
        pw_max_row.addStretch()
        right_form.addRow("Peak Wavelength(nm) Max :", pw_max_row)
        self.summary_pw_at_test_t = value_box("0", 72)
        right_form.addRow("Peak Wavelength(nm) @Test T :", self.summary_pw_at_test_t)
        self.summary_resolution = value_box("0", 72)
        right_form.addRow("Resolution(nm) :", self.summary_resolution)
        columns.addLayout(right_form)
        panel_layout.addLayout(columns)

        layout.addWidget(panel)
        layout.addStretch()
        return w

    def _make_recipe_tab(self):
        """Recipe tab: path row + lazy-loaded read-only view (large widget tree — not built in __init__ to avoid startup freeze / white flash)."""
        w = QWidget()
        w.setObjectName("recipe_tab_container")
        w.setAutoFillBackground(True)
        w.setStyleSheet("background-color: #1e1e23;")
        vbox = QVBoxLayout(w)
        # Path + Browse row
        search_row = QHBoxLayout()
        self._recipe_path_display = QLineEdit()
        self._recipe_path_display.setReadOnly(True)
        self._recipe_path_display.setPlaceholderText("No recipe loaded. Use Browse or select a recipe in Start New.")
        self._recipe_path_display.setMinimumWidth(400)
        search_row.addWidget(self._recipe_path_display)
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self._on_recipe_tab_browse)
        search_row.addWidget(browse_btn)
        search_row.addStretch()
        vbox.addLayout(search_row)
        self._recipe_detail_host = QWidget()
        self._recipe_detail_host.setStyleSheet("background-color: #1e1e23;")
        self._recipe_detail_host.setAutoFillBackground(True)
        self._recipe_detail_layout = QVBoxLayout(self._recipe_detail_host)
        self._recipe_detail_layout.setContentsMargins(0, 0, 0, 0)
        self._recipe_loading_label = QLabel("Loading recipe layout…")
        self._recipe_loading_label.setStyleSheet(
            "color: #9e9e9e; font-size: 13px; padding: 12px; background-color: #1e1e23;"
        )
        self._recipe_loading_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        self._recipe_detail_layout.addWidget(self._recipe_loading_label)
        self._recipe_readonly_view = None
        vbox.addWidget(self._recipe_detail_host, 1)
        self._current_recipe_data = None
        self._current_recipe_path = None
        self._startnew_comments = ""
        return w

    def _ensure_recipe_readonly_view(self) -> None:
        """Create RecipeReadonlyView on first use (after first paint or when Recipe tab / data refresh needs it)."""
        if getattr(self, "_recipe_readonly_view", None) is not None:
            return
        host = getattr(self, "_recipe_detail_host", None)
        lay = getattr(self, "_recipe_detail_layout", None)
        if host is None or lay is None:
            return
        self._recipe_readonly_view = RecipeReadonlyView(host)
        self._recipe_readonly_view.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        while lay.count():
            item = lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        lay.addWidget(self._recipe_readonly_view)
        self._recipe_loading_label = None
        data = getattr(self, "_current_recipe_data", None)
        if data:
            self._recipe_readonly_view.set_data(data)
        else:
            self._recipe_readonly_view.clear()

    def _on_recipe_tab_browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select recipe file", "",
            "Recipe files (*.json *.rcp *.ini);;All files (*)",
        )
        if not path:
            return
        try:
            data = self._load_recipe_file(path)
            if data:
                self._current_recipe_data = data
                self._current_recipe_path = path
                self._refresh_recipe_tab()
                # Do NOT apply wavemeter range here — only in Start New after recipe is selected and Start Test is pressed.
        except Exception as e:
            QMessageBox.warning(self, "Recipe", "Could not load recipe: {}".format(e))

    def _load_recipe_file(self, path):
        """Load recipe from .json / .rcp (JSON or INI) / .ini — same as Recipe editor and Start New."""
        from operations.recipe_io import load_recipe_file

        return load_recipe_file(path or "")

    def _refresh_recipe_tab(self):
        """Update path display and fill or clear the read-only recipe view (same layout always visible)."""
        path_display = getattr(self, "_recipe_path_display", None)
        if path_display is not None:
            path = getattr(self, "_current_recipe_path", None) or ""
            path_display.setText(path)
        self._ensure_recipe_readonly_view()
        view = getattr(self, "_recipe_readonly_view", None)
        if view is None:
            return
        data = getattr(self, "_current_recipe_data", None)
        if data:
            view.set_data(data)
        else:
            view.clear()

    def _switch_to_recipe_tab(self) -> None:
        """Show the Recipe tab (read-only view: GENERAL, PER, LIV, SPECTRUM, TEMP STABILITY)."""
        tb = getattr(self, "tabs", None)
        if tb is None:
            return
        for i in range(tb.count()):
            if tb.tabText(i) == "Recipe":
                tb.setCurrentIndex(i)
                return

    def _apply_recipe_from_path(self, path: str) -> None:
        """Load recipe file into main window state and refresh the Recipe tab (all sections via set_data)."""
        path = (path or "").strip()
        if not path:
            return
        try:
            data = self._load_recipe_file(path)
            if not data:
                return
            self._current_recipe_data = data
            self._current_recipe_path = path
            self._refresh_recipe_tab()
        except Exception:
            pass

    def _on_recipe_saved_from_editor(self, path: str) -> None:
        """New Recipe window SAVE — mirror file on main Recipe tab and switch to that tab."""
        self._apply_recipe_from_path(path)
        self._switch_to_recipe_tab()

    def _on_start_new_recipe_selection_changed(self, path: str) -> None:
        """Start New: user chose a recipe file — same content as main Recipe tab (no tab switch)."""
        self._apply_recipe_from_path(path)

    def _apply_wavemeter_range_from_recipe(self, recipe_data):
        """Set wavemeter range from recipe wavelength: <1000 -> 480-1000 (W0), else 1000-1650 (W1). Only sends to instrument if wavemeter is connected."""
        if not recipe_data or not isinstance(recipe_data, dict):
            return
        try:
            wl = recipe_data.get("wavelength")
            if wl is None:
                g = recipe_data.get("GENERAL")
                if isinstance(g, dict):
                    wl = g.get("wavelength") or g.get("Wavelength")
            if wl is None and "LIV" in recipe_data and isinstance(recipe_data["LIV"], dict):
                wl = recipe_data["LIV"].get("wavelength") or recipe_data["LIV"].get("Wavelength")
            if wl is not None:
                try:
                    wl_nm = float(wl)
                except (TypeError, ValueError):
                    wl_nm = 1000.0
            else:
                wl_nm = 1000.0
            r = "480-1000" if wl_nm < 1000 else "1000-1650"
            i = self.wavemeter_range_combo.findText(r)
            if i >= 0:
                self.wavemeter_range_combo.setCurrentIndex(i)
            if self._viewmodel.get_connection_state().get("Wavemeter"):
                self._viewmodel.apply_wavemeter_range(r)
        except Exception:
            pass

    def _make_manual_control_tab(self):
        """Manual Control: four columns — Arroyo (linked), Actuator, PRM, Ando. Row pinned to top."""
        w = QWidget()
        vbox = QVBoxLayout(w)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setAlignment(QtCompat.AlignTop)
        content = QWidget()
        content.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        row = QHBoxLayout(content)
        row.setContentsMargins(8, 0, 8, 0)
        row.setSpacing(20)
        row.setAlignment(QtCompat.AlignTop)
        box_style = (
            "QGroupBox { font-weight: bold; font-size: 15px; border: 1px solid #3a3a42; border-radius: 4px; "
            "margin: 0; padding: 18px 6px 6px 6px; background-color: #25252c; } "
            "QGroupBox::title { subcontrol-origin: padding; subcontrol-position: top left; top: 2px; left: 10px; "
            "padding: 0 6px; color: #e6e6e6; font-size: 15px; }"
        )
        read_style = "color: #b0b0b0; font-size: 13px;"
        value_style = "color: #e6e6e6; font-size: 15px; font-weight: bold; min-height: 20px;"

        # Arroyo box — equal column width; reduced height
        arroyo_box = QGroupBox("Arroyo")
        arroyo_box.setMinimumWidth(180)
        arroyo_box.setMaximumHeight(450)
        arroyo_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        arroyo_box.setStyleSheet(box_style)
        arroyo_inner = QVBoxLayout(arroyo_box)
        arroyo_inner.setSpacing(8)
        arroyo_inner.setContentsMargins(10, 8, 10, 8)
        # Actual Current and Actual Temperature — labels beside each other
        actual_row_labels = QHBoxLayout()
        actual_row_labels.addWidget(QLabel("Actual Current (mA)"))
        actual_row_labels.addWidget(QLabel("Actual Temperature"))
        arroyo_inner.addLayout(actual_row_labels)
        # Reading values beside each other
        actual_row_values = QHBoxLayout()
        self.arroyo_actual_current_label = QLabel("—")
        self.arroyo_actual_current_label.setStyleSheet(value_style)
        actual_row_values.addWidget(self.arroyo_actual_current_label)
        self.arroyo_actual_temp_label = QLabel("—")
        self.arroyo_actual_temp_label.setStyleSheet(value_style)
        actual_row_values.addWidget(self.arroyo_actual_temp_label)
        arroyo_inner.addLayout(actual_row_values)
        # Set Current, Set Temperature — labels beside each other
        set_row_labels = QHBoxLayout()
        set_row_labels.addWidget(QLabel("Set Current"))
        set_row_labels.addSpacing(12)
        set_row_labels.addWidget(QLabel("Set Temperature"))
        arroyo_inner.addLayout(set_row_labels)
        # Value boxes: number only; unit label outside — min width so up/down arrows don't overlap
        set_row_boxes = QHBoxLayout()
        set_row_boxes.setSpacing(8)
        spin_style = "font-size: 12px; min-height: 22px; max-height: 26px;" + spinbox_arrow_styles()
        spin_min_w = 88
        self.arroyo_set_current_spin = QDoubleSpinBox()
        self.arroyo_set_current_spin.setStyleSheet(spin_style)
        self.arroyo_set_current_spin.setMinimumWidth(spin_min_w)
        self.arroyo_set_current_spin.setRange(0, 5000)
        self.arroyo_set_current_spin.setDecimals(1)
        self.arroyo_set_current_spin.setSpecialValueText("")
        self.arroyo_set_current_spin.setValue(0)
        self.arroyo_set_current_spin.editingFinished.connect(self._on_arroyo_set_current)
        set_row_boxes.addWidget(self.arroyo_set_current_spin)
        set_row_boxes.addWidget(QLabel("mA"))
        set_row_boxes.addSpacing(12)
        self.arroyo_set_temp_spin = QDoubleSpinBox()
        self.arroyo_set_temp_spin.setStyleSheet(spin_style)
        self.arroyo_set_temp_spin.setMinimumWidth(spin_min_w)
        self.arroyo_set_temp_spin.setRange(-50, 150)
        self.arroyo_set_temp_spin.setDecimals(2)
        self.arroyo_set_temp_spin.setSpecialValueText("")
        self.arroyo_set_temp_spin.setValue(20)
        self.arroyo_set_temp_spin.editingFinished.connect(self._on_arroyo_set_temp)
        set_row_boxes.addWidget(self.arroyo_set_temp_spin)
        set_row_boxes.addWidget(QLabel("°C"))
        arroyo_inner.addLayout(set_row_boxes)
        # Max Current, Max Temp
        max_row_labels = QHBoxLayout()
        max_row_labels.addWidget(QLabel("Max Current"))
        max_row_labels.addSpacing(12)
        max_row_labels.addWidget(QLabel("Max Temp"))
        arroyo_inner.addLayout(max_row_labels)
        max_row_values = QHBoxLayout()
        max_row_values.setSpacing(8)
        self.arroyo_max_current_spin = QDoubleSpinBox()
        self.arroyo_max_current_spin.setStyleSheet(spin_style)
        self.arroyo_max_current_spin.setMinimumWidth(spin_min_w)
        self.arroyo_max_current_spin.setRange(0, 10000)
        self.arroyo_max_current_spin.setDecimals(1)
        self.arroyo_max_current_spin.setSpecialValueText("")
        self.arroyo_max_current_spin.setValue(0)
        self.arroyo_max_current_spin.setKeyboardTracking(False)
        self.arroyo_max_current_spin.editingFinished.connect(self._on_arroyo_max_current)
        max_row_values.addWidget(self.arroyo_max_current_spin)
        max_row_values.addWidget(QLabel("mA"))
        max_row_values.addSpacing(12)
        self.arroyo_max_temp_spin = QDoubleSpinBox()
        self.arroyo_max_temp_spin.setStyleSheet(spin_style)
        self.arroyo_max_temp_spin.setMinimumWidth(spin_min_w)
        self.arroyo_max_temp_spin.setRange(-50, 200)
        self.arroyo_max_temp_spin.setDecimals(2)
        self.arroyo_max_temp_spin.setSpecialValueText("")
        self.arroyo_max_temp_spin.setValue(-50)
        self.arroyo_max_temp_spin.setKeyboardTracking(False)
        self.arroyo_max_temp_spin.editingFinished.connect(self._on_arroyo_max_temp)
        max_row_values.addWidget(self.arroyo_max_temp_spin)
        max_row_values.addWidget(QLabel("°C"))
        arroyo_inner.addLayout(max_row_values)
        # Laser On/Off and TEC On/Off toggle buttons
        btn_style_off = "QPushButton { background-color: #2d2d34; color: #e6e6e6; font-size: 12px; padding: 4px 10px; } QPushButton:hover { background-color: #3a3a42; }"
        btn_style_on = "QPushButton { background-color: #4caf50; color: white; font-size: 12px; padding: 4px 10px; } QPushButton:hover { background-color: #388E3C; }"
        self.arroyo_laser_btn = QPushButton("Laser On")
        self.arroyo_laser_btn.setToolTip(
            "Laser ON: enables TEC output first if it is off, waits briefly, then enables laser output if needed. "
            "Already-on channels are skipped. Laser OFF: turns laser output off only (TEC unchanged)."
        )
        self.arroyo_laser_btn.setStyleSheet(btn_style_off)
        self.arroyo_laser_btn.setCheckable(True)
        self.arroyo_laser_btn.clicked.connect(self._on_arroyo_laser_clicked)
        self.arroyo_tec_btn = QPushButton("TEC On")
        self.arroyo_tec_btn.setStyleSheet(btn_style_off)
        self.arroyo_tec_btn.setCheckable(True)
        self.arroyo_tec_btn.clicked.connect(self._on_arroyo_tec_clicked)
        btn_row = QHBoxLayout()
        btn_row.addWidget(self.arroyo_laser_btn)
        btn_row.addWidget(self.arroyo_tec_btn)
        arroyo_inner.addLayout(btn_row)
        # Laser On LED, TEC On LED
        led_style_off = "background-color: #555; border-radius: 8px; min-width: 16px; max-width: 16px; min-height: 16px; max-height: 16px;"
        led_style_on = "background-color: #4caf50; border-radius: 8px; min-width: 16px; max-width: 16px; min-height: 16px; max-height: 16px;"
        led_row = QHBoxLayout()
        self.arroyo_laser_led = QLabel()
        self.arroyo_laser_led.setStyleSheet(led_style_off)
        self.arroyo_laser_led.setFixedSize(16, 16)
        led_row.addWidget(QLabel("Laser On LED"))
        led_row.addWidget(self.arroyo_laser_led)
        led_row.addStretch()
        self.arroyo_tec_led = QLabel()
        self.arroyo_tec_led.setStyleSheet(led_style_off)
        self.arroyo_tec_led.setFixedSize(16, 16)
        led_row.addWidget(QLabel("TEC On LED"))
        led_row.addWidget(self.arroyo_tec_led)
        arroyo_inner.addLayout(led_row)
        for lbl in arroyo_box.findChildren(QLabel):
            if lbl not in (self.arroyo_actual_current_label, self.arroyo_actual_temp_label,
                          self.arroyo_laser_led, self.arroyo_tec_led):
                lbl.setStyleSheet(read_style)
        row.addWidget(arroyo_box, 1, QtCompat.AlignTop)

        # Actuator — Distance rows: movea/moveb from spinbox; Quick row: fixed mm; Home: homea/homeb
        act_box = QGroupBox("Actuator")
        act_box.setToolTip(
            "Each Move adds the mm in the box to a running total from home, then sends movea/moveb with that total "
            "(e.g. 206 twice -> 206 mm then 412 mm). Home resets that axis to 0 mm. "
            "Quick Move A/B adds {} mm per click. Home = homea/homeb.".format(
                int(ACTUATOR_DEFAULT_MANUAL_DISTANCE_MM)
            )
        )
        act_box.setMinimumWidth(180)
        act_box.setMaximumHeight(520)
        act_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        act_box.setStyleSheet(box_style)
        act_inner = QVBoxLayout(act_box)
        act_inner.setSpacing(10)
        act_inner.setContentsMargins(10, 8, 10, 8)
        act_spin_style = "font-size: 12px; min-height: 22px; max-height: 26px;" + spinbox_arrow_styles()
        act_spin_min_w = 88
        # Distance A — Move uses spinbox mm (movea <mm>); Home sends homea
        lbl_dist_a = QLabel("Distance A")
        lbl_dist_a.setToolTip(
            "Each Move adds this distance to the total from home, then sends movea with the cumulative mm. Home resets A."
        )
        act_inner.addWidget(lbl_dist_a)
        dist_a_row = QHBoxLayout()
        dist_a_row.setSpacing(8)
        self.actuator_dist_a_spin = QDoubleSpinBox()
        self.actuator_dist_a_spin.setStyleSheet(act_spin_style)
        self.actuator_dist_a_spin.setMinimumWidth(act_spin_min_w)
        self.actuator_dist_a_spin.setRange(0.1, 1000)
        self.actuator_dist_a_spin.setDecimals(1)
        self.actuator_dist_a_spin.setSpecialValueText("")
        self.actuator_dist_a_spin.setValue(float(ACTUATOR_DEFAULT_MANUAL_DISTANCE_MM))
        self.actuator_dist_a_spin.setToolTip("Step (mm) added to A total from home on each Move (then movea <total>).")
        dist_a_row.addWidget(self.actuator_dist_a_spin)
        dist_a_row.addWidget(QLabel("mm"))
        dist_a_row.addSpacing(6)
        move_a_btn = QPushButton("Move")
        move_a_btn.setStyleSheet(btn_style_off)
        move_a_btn.setToolTip("Adds spinbox mm to A total from home, then movea <total mm>")
        move_a_btn.clicked.connect(self._on_actuator_move_a)
        dist_a_row.addWidget(move_a_btn)
        home_a_btn = QPushButton("Home")
        home_a_btn.setStyleSheet(btn_style_off)
        home_a_btn.setToolTip("homea — home actuator A")
        home_a_btn.clicked.connect(self._on_actuator_home_a)
        dist_a_row.addWidget(home_a_btn)
        act_inner.addLayout(dist_a_row)
        # Distance B — Move uses spinbox (moveb <mm>); Home sends homeb
        lbl_dist_b = QLabel("Distance B")
        lbl_dist_b.setToolTip(
            "Each Move adds this distance to the total from home, then sends moveb with the cumulative mm. Home resets B."
        )
        act_inner.addWidget(lbl_dist_b)
        dist_b_row = QHBoxLayout()
        dist_b_row.setSpacing(8)
        self.actuator_dist_b_spin = QDoubleSpinBox()
        self.actuator_dist_b_spin.setStyleSheet(act_spin_style)
        self.actuator_dist_b_spin.setMinimumWidth(act_spin_min_w)
        self.actuator_dist_b_spin.setRange(0.1, 1000)
        self.actuator_dist_b_spin.setDecimals(1)
        self.actuator_dist_b_spin.setSpecialValueText("")
        self.actuator_dist_b_spin.setValue(float(ACTUATOR_DEFAULT_MANUAL_DISTANCE_MM))
        self.actuator_dist_b_spin.setToolTip("Step (mm) added to B total from home on each Move (then moveb <total>).")
        dist_b_row.addWidget(self.actuator_dist_b_spin)
        dist_b_row.addWidget(QLabel("mm"))
        dist_b_row.addSpacing(6)
        move_b_btn = QPushButton("Move")
        move_b_btn.setStyleSheet(btn_style_off)
        move_b_btn.setToolTip("Adds spinbox mm to B total from home, then moveb <total mm>")
        move_b_btn.clicked.connect(self._on_actuator_move_b)
        dist_b_row.addWidget(move_b_btn)
        home_b_btn = QPushButton("Home")
        home_b_btn.setStyleSheet(btn_style_off)
        home_b_btn.setToolTip("homeb — home actuator B")
        home_b_btn.clicked.connect(self._on_actuator_home_b)
        dist_b_row.addWidget(home_b_btn)
        act_inner.addLayout(dist_b_row)
        # Quick row: fixed distance movea 206 / moveb 206 (same as terminal test script)
        lbl_quick = QLabel("Quick ({} mm)".format(int(ACTUATOR_DEFAULT_MANUAL_DISTANCE_MM)))
        lbl_quick.setToolTip(
            "Each quick click adds {} mm to that axis total from home (same stacking as Distance rows).".format(
                int(ACTUATOR_DEFAULT_MANUAL_DISTANCE_MM)
            )
        )
        act_inner.addWidget(lbl_quick)
        actions_row = QHBoxLayout()
        move_a_act_btn = QPushButton("Move A")
        move_a_act_btn.setStyleSheet(btn_style_off)
        move_a_act_btn.setToolTip(
            "Adds {} mm to A total from home, then movea <total>".format(int(ACTUATOR_DEFAULT_MANUAL_DISTANCE_MM))
        )
        move_a_act_btn.clicked.connect(self._on_actuator_move_a_quick)
        home_a_act_btn = QPushButton("Home A")
        home_a_act_btn.setStyleSheet(btn_style_off)
        home_a_act_btn.setToolTip("homea — home actuator A")
        home_a_act_btn.clicked.connect(self._on_actuator_home_a)
        move_b_act_btn = QPushButton("Move B")
        move_b_act_btn.setStyleSheet(btn_style_off)
        move_b_act_btn.setToolTip(
            "Adds {} mm to B total from home, then moveb <total>".format(int(ACTUATOR_DEFAULT_MANUAL_DISTANCE_MM))
        )
        move_b_act_btn.clicked.connect(self._on_actuator_move_b_quick)
        home_b_act_btn = QPushButton("Home B")
        home_b_act_btn.setStyleSheet(btn_style_off)
        home_b_act_btn.setToolTip("homeb — home actuator B")
        home_b_act_btn.clicked.connect(self._on_actuator_home_b)
        actions_row.addWidget(move_a_act_btn)
        actions_row.addWidget(home_a_act_btn)
        actions_row.addWidget(move_b_act_btn)
        actions_row.addWidget(home_b_act_btn)
        act_inner.addLayout(actions_row)
        home_both_btn = QPushButton("Home Both")
        home_both_btn.setStyleSheet(btn_style_off)
        home_both_btn.setToolTip("HOME BOTH — home both actuators")
        home_both_btn.clicked.connect(self._on_actuator_home_both)
        act_inner.addWidget(home_both_btn)
        for lbl in act_box.findChildren(QLabel):
            lbl.setStyleSheet(read_style)
        self.actuator_status_bar = QLabel("A: Not connected  |  B: Not connected")
        self.actuator_status_bar.setObjectName("actuator_status_bar")
        self.actuator_status_bar.setWordWrap(True)
        self.actuator_status_bar.setToolTip(
            "Position is cumulative mm from the last Home for each axis. "
            "Moving/homing/reached labels are immediate send + time estimates."
        )
        self.actuator_status_bar.setStyleSheet(
            "QLabel#actuator_status_bar { background-color: #2a2a2a; color: #b0bec5; "
            "padding: 6px 8px; border-radius: 3px; font-size: 11px; }"
        )
        act_inner.addWidget(self.actuator_status_bar)
        row.addWidget(act_box, 1, QtCompat.AlignTop)
        # PRM1-Z8: Speed, Acceleration, Position + Move, Home, Quick angles, Stop / IStop
        prm_box = QGroupBox("PRM")
        prm_box.setObjectName("prm_control_box")
        prm_box.setMinimumWidth(200)
        prm_box.setMaximumHeight(450)
        prm_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        prm_box.setStyleSheet(box_style)
        prm_inner = QVBoxLayout(prm_box)
        prm_inner.setSpacing(10)
        prm_inner.setContentsMargins(10, 8, 10, 8)
        prm_spin_min_w = 88
        # Row 1: Speed (velocity v in °/s) — formula: v = speed; Set sends value to SetVelParams
        prm_row1 = QHBoxLayout()
        prm_row1.setSpacing(8)
        prm_row1.addWidget(QLabel("Speed (°/s):"))
        self.prm_speed_spin = QDoubleSpinBox()
        self.prm_speed_spin.setToolTip("Target velocity in °/s (max 25). Set sends to SetVelocityParams; Move uses this speed.")
        self.prm_speed_spin.setStyleSheet(act_spin_style)
        self.prm_speed_spin.setRange(0.5, 25.0)  # PRM manual control limit 25 °/s
        self.prm_speed_spin.setDecimals(2)
        self.prm_speed_spin.setSingleStep(0.5)
        self.prm_speed_spin.setSuffix(" °/s")
        self.prm_speed_spin.setValue(25.0)
        self.prm_speed_spin.setMinimumWidth(prm_spin_min_w)
        prm_row1.addWidget(self.prm_speed_spin)
        prm_set_btn = QPushButton("Set")
        prm_set_btn.setStyleSheet("QPushButton { background-color: #607D8B; color: white; } QPushButton:hover { background-color: #546E7A; }")
        prm_set_btn.setMinimumWidth(44)
        prm_set_btn.clicked.connect(self._on_prm_set_speed)
        prm_inner.addLayout(prm_row1)
        # Row 2: Position value box + Move button
        prm_row2 = QHBoxLayout()
        prm_row2.setSpacing(8)
        prm_row2.addWidget(QLabel("Position (°):"))
        self.prm_angle_spin = QDoubleSpinBox()
        self.prm_angle_spin.setToolTip("Target angle in degrees. Press Move to go to this position.")
        self.prm_angle_spin.setStyleSheet(act_spin_style)
        self.prm_angle_spin.setRange(-360, 360)
        self.prm_angle_spin.setDecimals(2)
        self.prm_angle_spin.setSpecialValueText("")
        self.prm_angle_spin.setValue(0.0)
        self.prm_angle_spin.setMinimumWidth(prm_spin_min_w)
        prm_row2.addWidget(self.prm_angle_spin)
        prm_move_btn = QPushButton("Move")
        prm_move_btn.setToolTip("Move to the angle entered above")
        prm_move_btn.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; font-weight: bold; } QPushButton:hover { background-color: #45a049; }")
        prm_move_btn.setMinimumWidth(60)
        prm_move_btn.clicked.connect(self._on_prm_move)
        prm_row2.addWidget(prm_move_btn)
        prm_inner.addLayout(prm_row2)
        # Position readout (updates when connected)
        self.prm_position_label = QLabel("Position: --- °")
        self.prm_position_label.setStyleSheet("font-weight: bold; font-size: 11px;")
        prm_inner.addWidget(self.prm_position_label)
        # Home button
        prm_home_btn = QPushButton("Home")
        prm_home_btn.setToolTip("Move to home (reference zero) position")
        prm_home_btn.setStyleSheet("QPushButton { background-color: #2196F3; color: white; } QPushButton:hover { background-color: #1976D2; }")
        prm_home_btn.clicked.connect(self._on_prm_initial_position)
        prm_inner.addWidget(prm_home_btn)
        # Quick: 45, 90, 180, 360
        prm_inner.addWidget(QLabel("Quick:"))
        prm_shortcut_row = QHBoxLayout()
        for angle in (45, 90, 180, 360):
            btn = QPushButton("{}°".format(angle))
            btn.setToolTip("Move to {} deg".format(angle))
            btn.setStyleSheet(btn_style_off)
            btn.setMinimumWidth(44)
            btn.clicked.connect(lambda checked=False, a=angle: self._on_prm_quick_rotate(a))
            prm_shortcut_row.addWidget(btn)
        prm_inner.addLayout(prm_shortcut_row)
        # Stop (smooth), IStop (immediate) — always enabled so user can stop then use other buttons; send commands to instrument
        prm_stop_row = QHBoxLayout()
        self.prm_stop_btn = QPushButton("Stop")
        self.prm_stop_btn.setObjectName("prm_stop_smooth_btn")
        self.prm_stop_btn.setToolTip("Smooth stop (StopProfiled) — sends command to instrument; other buttons stay usable")
        self.prm_stop_btn.setStyleSheet("QPushButton { background-color: #FF9800; color: white; font-weight: bold; } QPushButton:hover { background-color: #F57C00; } QPushButton:pressed { background-color: #E65100; }")
        self.prm_stop_btn.setMinimumWidth(52)
        self.prm_stop_btn.setFocusPolicy(QtCompat.StrongFocus)
        self.prm_stop_btn.setCursor(QCursor(QtCompat.PointingHandCursor))
        self.prm_stop_btn.setEnabled(True)
        self.prm_stop_btn.clicked.connect(self._on_prm_stop_smooth)
        prm_stop_row.addWidget(self.prm_stop_btn)
        self.prm_istop_btn = QPushButton("IStop")
        self.prm_istop_btn.setObjectName("prm_stop_immediate_btn")
        self.prm_istop_btn.setToolTip("Immediate stop (StopImmediate) — sends command to instrument; other buttons stay usable")
        self.prm_istop_btn.setStyleSheet("QPushButton { background-color: #f44336; color: white; font-weight: bold; } QPushButton:hover { background-color: #d32f2f; } QPushButton:pressed { background-color: #b71c1c; }")
        self.prm_istop_btn.setMinimumWidth(52)
        self.prm_istop_btn.setFocusPolicy(QtCompat.StrongFocus)
        self.prm_istop_btn.setCursor(QCursor(QtCompat.PointingHandCursor))
        self.prm_istop_btn.setEnabled(True)
        self.prm_istop_btn.clicked.connect(self._on_prm_stop_immediate)
        prm_stop_row.addWidget(self.prm_istop_btn)
        prm_inner.addLayout(prm_stop_row)
        # Status: green = Ready (idle), orange = moving/homing or smooth-stop message
        self.prm_status_label = QLabel("Status: Ready")
        self.prm_status_label.setObjectName("prm_status_label")
        self.prm_status_label.setStyleSheet("font-size: 11px; color: #4caf50;")
        self.prm_status_label.setToolTip(
            "PRM status: green = idle (Ready), orange = moving/homing, red = immediate stop."
        )
        prm_inner.addWidget(self.prm_status_label)
        for lbl in prm_box.findChildren(QLabel):
            lbl.setStyleSheet(read_style)
        self.prm_position_label.setStyleSheet(read_style + " font-weight: bold; font-size: 11px;")
        self.prm_status_label.setStyleSheet(read_style + " font-size: 11px; color: #4caf50;")
        row.addWidget(prm_box, 1, QtCompat.AlignTop)
        # Ando OSA panel (Center, Span, Ref Level, Log Scale, Resolution, Sensitivity, Analysis, Sweep)
        ando_box = QGroupBox("Ando")
        ando_box.setMinimumWidth(180)
        ando_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        ando_box.setStyleSheet(box_style)
        ando_inner = QVBoxLayout(ando_box)
        ando_inner.setSpacing(10)
        ando_inner.setContentsMargins(10, 8, 10, 8)
        line_ando = "font-size: 12px; min-height: 22px; max-height: 26px; padding: 4px;"
        # Center — empty until user enters value
        ando_inner.addWidget(QLabel("Center"))
        ando_center_row = QHBoxLayout()
        ando_center_row.setSpacing(8)
        self.ando_center_edit = QLineEdit()
        self.ando_center_edit.setStyleSheet(line_ando)
        self.ando_center_edit.setMinimumWidth(90)
        self.ando_center_edit.setPlaceholderText("")
        self.ando_center_edit.setValidator(QDoubleValidator(600, 1750, 2))
        self.ando_center_edit.setMaxLength(8)
        self.ando_center_edit.editingFinished.connect(self._on_ando_center)
        ando_center_row.addWidget(self.ando_center_edit)
        ando_center_row.addWidget(QLabel("nm"))
        ando_inner.addLayout(ando_center_row)
        # Span
        ando_inner.addWidget(QLabel("Span"))
        ando_span_row = QHBoxLayout()
        ando_span_row.setSpacing(8)
        self.ando_span_edit = QLineEdit()
        self.ando_span_edit.setStyleSheet(line_ando)
        self.ando_span_edit.setMinimumWidth(90)
        self.ando_span_edit.setValidator(QDoubleValidator(0, 1200, 2))
        self.ando_span_edit.setMaxLength(8)
        self.ando_span_edit.editingFinished.connect(self._on_ando_span)
        ando_span_row.addWidget(self.ando_span_edit)
        ando_span_row.addWidget(QLabel("nm"))
        ando_inner.addLayout(ando_span_row)
        # Ref Level
        ando_inner.addWidget(QLabel("Ref Level"))
        ando_ref_row = QHBoxLayout()
        ando_ref_row.setSpacing(8)
        self.ando_ref_level_edit = QLineEdit()
        self.ando_ref_level_edit.setStyleSheet(line_ando)
        self.ando_ref_level_edit.setMinimumWidth(90)
        self.ando_ref_level_edit.setValidator(QDoubleValidator(-90, 20, 1))
        self.ando_ref_level_edit.setMaxLength(6)
        self.ando_ref_level_edit.editingFinished.connect(self._on_ando_ref_level)
        ando_ref_row.addWidget(self.ando_ref_level_edit)
        ando_ref_row.addWidget(QLabel("dBm"))
        ando_inner.addLayout(ando_ref_row)
        # Log Scale (0 = linear)
        ando_inner.addWidget(QLabel("Log Scale (0=linear)"))
        ando_log_row = QHBoxLayout()
        ando_log_row.setSpacing(8)
        self.ando_log_scale_edit = QLineEdit()
        self.ando_log_scale_edit.setStyleSheet(line_ando)
        self.ando_log_scale_edit.setMinimumWidth(90)
        self.ando_log_scale_edit.setValidator(QDoubleValidator(0, 10, 1))
        self.ando_log_scale_edit.setMaxLength(5)
        self.ando_log_scale_edit.editingFinished.connect(self._on_ando_log_scale)
        ando_log_row.addWidget(self.ando_log_scale_edit)
        ando_log_row.addWidget(QLabel("dB/DIV"))
        ando_inner.addLayout(ando_log_row)
        # Resolution
        ando_inner.addWidget(QLabel("Resolution"))
        ando_res_row = QHBoxLayout()
        ando_res_row.setSpacing(8)
        self.ando_resolution_edit = QLineEdit()
        self.ando_resolution_edit.setStyleSheet(line_ando)
        self.ando_resolution_edit.setMinimumWidth(90)
        self.ando_resolution_edit.setValidator(QDoubleValidator(0.01, 2.0, 2))
        self.ando_resolution_edit.setMaxLength(6)
        self.ando_resolution_edit.editingFinished.connect(self._on_ando_resolution)
        ando_res_row.addWidget(self.ando_resolution_edit)
        ando_res_row.addWidget(QLabel("nm"))
        ando_inner.addLayout(ando_res_row)
        # Best Sensitivity dropdown
        ando_inner.addWidget(QLabel("Best Sensitivity"))
        self.ando_sensitivity_combo = QComboBox()
        self.ando_sensitivity_combo.setStyleSheet("font-size: 12px; min-height: 24px;")
        self.ando_sensitivity_combo.addItems([
            "Normal range auto", "Normal range hold", "Mid", "High1", "High2", "High3"
        ])
        self.ando_sensitivity_combo.currentIndexChanged[int].connect(self._on_ando_sensitivity)
        ando_inner.addWidget(self.ando_sensitivity_combo)
        # Analysis: DFB LD, LED
        ando_inner.addWidget(QLabel("Analysis"))
        analysis_row = QHBoxLayout()
        self.ando_dfb_btn = QPushButton("DFB LD")
        self.ando_dfb_btn.setStyleSheet(btn_style_off)
        self.ando_dfb_btn.clicked.connect(self._on_ando_analysis_dfb)
        self.ando_led_btn = QPushButton("LED")
        self.ando_led_btn.setStyleSheet(btn_style_off)
        self.ando_led_btn.clicked.connect(self._on_ando_analysis_led)
        analysis_row.addWidget(self.ando_dfb_btn)
        analysis_row.addWidget(self.ando_led_btn)
        ando_inner.addLayout(analysis_row)
        # Sweep: Auto, Single, Repeat, Stop
        ando_inner.addWidget(QLabel("Sweep"))
        sweep_row = QHBoxLayout()
        self.ando_sweep_auto_btn = QPushButton("Auto")
        self.ando_sweep_auto_btn.setStyleSheet(btn_style_off)
        self.ando_sweep_auto_btn.clicked.connect(lambda: self._viewmodel.set_ando_sweep_auto())
        self.ando_sweep_single_btn = QPushButton("Single")
        self.ando_sweep_single_btn.setStyleSheet(btn_style_off)
        self.ando_sweep_single_btn.clicked.connect(lambda: self._viewmodel.set_ando_sweep_single())
        self.ando_sweep_repeat_btn = QPushButton("Repeat")
        self.ando_sweep_repeat_btn.setStyleSheet(btn_style_off)
        self.ando_sweep_repeat_btn.clicked.connect(lambda: self._viewmodel.set_ando_sweep_repeat())
        self.ando_sweep_stop_btn = QPushButton("Stop")
        self.ando_sweep_stop_btn.setObjectName("btn_ando_stop")
        self.ando_sweep_stop_btn.setStyleSheet(
            "QPushButton#btn_ando_stop { background-color: #f44336; color: white; } "
            "QPushButton#btn_ando_stop:hover { background-color: #d32f2f; } "
        )
        self.ando_sweep_stop_btn.clicked.connect(lambda: self._viewmodel.set_ando_sweep_stop())
        sweep_row.addWidget(self.ando_sweep_auto_btn)
        sweep_row.addWidget(self.ando_sweep_single_btn)
        sweep_row.addWidget(self.ando_sweep_repeat_btn)
        sweep_row.addWidget(self.ando_sweep_stop_btn)
        ando_inner.addLayout(sweep_row)
        for lbl in ando_box.findChildren(QLabel):
            lbl.setStyleSheet(read_style)
        row.addWidget(ando_box, 1, QtCompat.AlignTop)
        # Readings — Gentec power (mW), Thorlabs Power
        readings_box = QGroupBox("Readings")
        readings_box.setMinimumWidth(180)
        readings_box.setMaximumHeight(450)
        readings_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        readings_box.setStyleSheet(box_style)
        readings_inner = QVBoxLayout(readings_box)
        readings_inner.setSpacing(4)
        readings_inner.setContentsMargins(8, 4, 8, 8)
        readings_inner.addWidget(QLabel("Gentec Power"))
        gentec_power_row = QHBoxLayout()
        self.gentec_power_label = QLabel("—")
        self.gentec_power_label.setStyleSheet(value_style)
        gentec_power_row.addWidget(self.gentec_power_label)
        gentec_power_row.addWidget(QLabel("mW"))
        readings_inner.addLayout(gentec_power_row)
        readings_inner.addWidget(QLabel("Thorlabs Power"))
        thorlabs_power_row = QHBoxLayout()
        self.thorlabs_power_label = QLabel("—")
        self.thorlabs_power_label.setStyleSheet(value_style)
        thorlabs_power_row.addWidget(self.thorlabs_power_label)
        thorlabs_power_row.addWidget(QLabel("mW"))
        readings_inner.addLayout(thorlabs_power_row)
        for lbl in readings_box.findChildren(QLabel):
            lbl.setStyleSheet(read_style)
        self.gentec_power_label.setStyleSheet(value_style)
        self.thorlabs_power_label.setStyleSheet(value_style)
        # Column: Readings on top, Wavemeter box below
        readings_wavemeter_column = QWidget()
        readings_wavemeter_column.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        col_layout = QVBoxLayout(readings_wavemeter_column)
        col_layout.setContentsMargins(0, 0, 0, 0)
        col_layout.setSpacing(12)
        col_layout.addWidget(readings_box, 0, QtCompat.AlignTop)
        # Wavemeter — below Readings: range dropdown, Apply range, wavelength display
        wavemeter_box = QGroupBox("Wavemeter")
        wavemeter_box.setMinimumWidth(200)
        wavemeter_box.setMaximumHeight(450)
        wavemeter_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        wavemeter_box.setStyleSheet(box_style)
        wavemeter_inner = QVBoxLayout(wavemeter_box)
        wavemeter_inner.setSpacing(4)
        wavemeter_inner.setContentsMargins(8, 4, 8, 8)
        wavemeter_range_row = QHBoxLayout()
        wavemeter_inner.addWidget(QLabel("Range"))
        self.wavemeter_range_combo = QComboBox()
        self.wavemeter_range_combo.setMinimumWidth(140)
        self.wavemeter_range_combo.addItems(["480-1000", "1000-1650"])
        wavemeter_range_row.addWidget(self.wavemeter_range_combo)
        wavemeter_apply_btn = QPushButton("Apply range")
        wavemeter_apply_btn.setStyleSheet(
            "QPushButton { background-color: #2196F3; color: white; } QPushButton:hover { background-color: #1976D2; }"
        )
        wavemeter_apply_btn.clicked.connect(self._on_apply_wavemeter_range)
        wavemeter_range_row.addWidget(wavemeter_apply_btn)
        wavemeter_inner.addLayout(wavemeter_range_row)
        wavemeter_inner.addWidget(QLabel("Wavelength (nm):"))
        self.wavemeter_wavelength_label = QLabel("—")
        self.wavemeter_wavelength_label.setStyleSheet(
            "color: #e6e6e6; font-size: 24px; font-weight: bold; min-height: 32px;"
        )
        wavemeter_inner.addWidget(self.wavemeter_wavelength_label)
        wavemeter_inner.addWidget(QLabel("nm"))
        for lbl in wavemeter_box.findChildren(QLabel):
            lbl.setStyleSheet(read_style)
        self.wavemeter_wavelength_label.setStyleSheet(
            "color: #e6e6e6; font-size: 24px; font-weight: bold; min-height: 32px;"
        )
        col_layout.addWidget(wavemeter_box, 0, QtCompat.AlignTop)
        row.addWidget(readings_wavemeter_column, 1, QtCompat.AlignTop)
        vbox.addWidget(content, 0, QtCompat.AlignTop)
        return w

    def _update_prm_manual_status(self, connected: bool):
        """Update PRM position label, speed and acceleration spinboxes when connection state changes."""
        if not connected and hasattr(self, "prm_position_label"):
            self.prm_position_label.setText("Position: --- °")
        if connected and hasattr(self, "prm_speed_spin"):
            try:
                v = self._viewmodel.prm_get_velocity()
                if v > 0:
                    self.prm_speed_spin.setValue(v)
            except Exception:
                pass

    def _build_footer(self):
        self.footer_frame = QFrame()
        self.footer_frame.setObjectName("footer")
        self.footer_frame.setFrameShape(QFrame.StyledPanel)
        layout = QHBoxLayout(self.footer_frame)
        layout.setContentsMargins(12, 8, 12, 8)
        self.footer_status_label = QLabel()
        self.footer_status_label.setTextFormat(QtCompat.RichText)
        self.footer_status_label.setStyleSheet("color: #e6e6e6; font-size: 12px;")
        layout.addWidget(self.footer_status_label)
        layout.addStretch()
        # Small status before Disconnect All: "Connecting..." while any device is connecting; empty when idle
        self.footer_connecting_label = QLabel("")
        self.footer_connecting_label.setStyleSheet("color: #ff9800; font-size: 12px; font-weight: bold;")
        self.footer_connecting_label.setMinimumWidth(120)
        layout.addWidget(self.footer_connecting_label)
        layout.addSpacing(12)
        disconnect_all_btn = QPushButton("Disconnect All")
        disconnect_all_btn.setStyleSheet(
            "QPushButton { background-color: #f44336; color: white; padding: 4px 12px; } "
            "QPushButton:hover { background-color: #d32f2f; } QPushButton:pressed { background-color: #b71c1c; }"
        )
        disconnect_all_btn.clicked.connect(self._on_disconnect_all)
        layout.addWidget(disconnect_all_btn)
        reconnect_btn = QPushButton("Reconnect")
        reconnect_btn.setStyleSheet(
            "QPushButton { background-color: #2196F3; color: white; padding: 4px 12px; } "
            "QPushButton:hover { background-color: #1976D2; } QPushButton:pressed { background-color: #0d47a1; }"
        )
        reconnect_btn.clicked.connect(self._on_footer_reconnect)
        layout.addWidget(reconnect_btn)
        self.footer_frame.setFixedHeight(40)
        # Timer: clear "Connecting..." only after no connection_state_changed for a while (so Thorlabs/slow devices still show Connecting)
        self._footer_connecting_clear_timer = QTimer(self.footer_frame)
        self._footer_connecting_clear_timer.setSingleShot(True)
        self._footer_connecting_clear_timer.timeout.connect(self._clear_footer_connecting)

    def _refresh_footer(self, state: dict):
        def _status(key: str) -> str:
            """Connected in green; Disconnected in red."""
            ok = state.get(key, False)
            if ok:
                return '<span style="color:#4caf50;">Connected</span>'
            return '<span style="color:#f44336;">Disconnected</span>'

        parts = [
            "Arroyo: {}".format(_status("Arroyo")),
            "Actuator: {}".format(_status("Actuator")),
            "Ando: {}".format(_status("Ando")),
            "Wavemeter: {}".format(_status("Wavemeter")),
            "PRM: {}".format(_status("PRM")),
            "Gentec: {}".format(_status("Gentec")),
            "Thorlabs: {}".format(_status("Thorlabs")),
        ]
        self.footer_status_label.setText("  |  ".join(parts))
        # Reset clear timer: only clear "Connecting..." when no connection event for 1.5s (so user sees Connecting until Thorlabs etc. are done)
        if hasattr(self, "footer_connecting_label") and self.footer_connecting_label.text():
            if hasattr(self, "_footer_connecting_clear_timer"):
                self._footer_connecting_clear_timer.stop()
                self._footer_connecting_clear_timer.start(1500)

    def _clear_footer_connecting(self):
        """Clear the Connecting status in footer (nothing happening)."""
        if hasattr(self, "footer_connecting_label"):
            self.footer_connecting_label.setText("")

    def _set_footer_connecting(self):
        """Show Connecting in footer when any device connection is in progress."""
        if hasattr(self, "footer_connecting_label"):
            self.footer_connecting_label.setText("Connecting...")

    def _on_connection_state_changed(self, _state: dict):
        # Always use ViewModel's full map — workers sometimes emit partial dicts; missing keys must not mean "disconnected".
        full = self._viewmodel.get_connection_state()
        self._refresh_footer(full)
        self._update_prm_manual_status(full.get("PRM", False))
        if not full.get("Arroyo", False):
            self._last_arroyo_readings = None
            self.arroyo_actual_current_label.setText("—")
            self.arroyo_actual_temp_label.setText("—")
            self.arroyo_max_current_spin.setValue(0)
            self.arroyo_max_temp_spin.setValue(-50)
            self.main_laser_current_value.setText("-")
            self.main_laser_voltage_value.setText("-")
            self.main_laser_set_current_value.setText("-")
            self.main_tec_voltage_value.setText("-")
            self.main_tec_temp_value.setText("-")
            self.main_tec_current_value.setText("-")
            self.main_tec_set_temp_value.setText("-")
            self._arroyo_laser_on = False
            self._arroyo_tec_on = False
            self._arroyo_update_laser_tec_ui()
        if not full.get("Gentec", False):
            self.gentec_power_label.setText("—")
        if not full.get("Thorlabs", False):
            self.thorlabs_power_label.setText("—")
        if not full.get("Wavemeter", False):
            self.wavemeter_wavelength_label.setText("—")

    def _on_gentec_reading_updated(self, value_mw):
        if value_mw is None:
            self.gentec_power_label.setText("—")
        else:
            self.gentec_power_label.setText(f"{value_mw:.4f}")
        # Forward live Gentec reading to Alignment window readout.
        align_w = getattr(self, "_alignment_window", None)
        if align_w is not None and align_w.isVisible() and hasattr(align_w, "_on_gentec_reading_updated"):
            try:
                align_w._on_gentec_reading_updated(value_mw)
            except Exception:
                pass

    def _on_thorlabs_reading_updated(self, value_mw):
        if value_mw is None:
            self.thorlabs_power_label.setText("—")
        else:
            self.thorlabs_power_label.setText(f"{value_mw:.4f}")
        # Forward live Thorlabs reading to Alignment window readout.
        align_w = getattr(self, "_alignment_window", None)
        if align_w is not None and align_w.isVisible() and hasattr(align_w, "_on_thorlabs_reading_updated"):
            try:
                align_w._on_thorlabs_reading_updated(value_mw)
            except Exception:
                pass

    def _on_wavemeter_wavelength_updated(self, wl_nm):
        if wl_nm is None:
            self.wavemeter_wavelength_label.setText("—")
        else:
            self.wavemeter_wavelength_label.setText(f"{wl_nm:.4f}")

    def _on_wavemeter_range_applied(self, success: bool, range_str: str):
        if success:
            self.main_status_log.appendPlainText("Wavemeter range set to {} nm.".format(range_str))
        else:
            self.main_status_log.appendPlainText("Wavemeter range failed (reconnect and try again).")

    def _focus_engineer_control_manual_subtab(self) -> None:
        """Inner Engineer Control tabs: default to Manual Control."""
        try:
            tw = getattr(self, "_engineer_control_inner_tabs", None)
            if tw is not None:
                tw.setCurrentIndex(0)
        except Exception:
            pass

    def _on_main_tab_bar_clicked(self, index: int) -> None:
        """Selecting Engineer Control (even re-click) opens the Manual Control sub-tab."""
        try:
            if self.tabs.tabText(index) == "Engineer Control":
                self._focus_engineer_control_manual_subtab()
        except Exception:
            pass

    def _on_tabs_current_changed(self, _index: int) -> None:
        """Re-apply last Arroyo snapshot, then poll so Laser/TEC boxes match hardware on any tab."""
        # Engineer Control — show Manual Control when user switches to this top tab from another.
        try:
            if self.tabs.tabText(_index) == "Engineer Control":
                self._focus_engineer_control_manual_subtab()
        except Exception:
            pass
        # Recipe tab — ensure read-only view exists if user opens tab before deferred timer runs.
        try:
            if self.tabs.tabText(_index) == "Recipe":
                self._ensure_recipe_readonly_view()
        except Exception:
            pass
        try:
            if self.tabs.tabText(_index) == "Plot":
                QTimer.singleShot(0, self._sync_result_plot_cell_heights)
        except Exception:
            pass
        if self._last_arroyo_readings is not None:
            self._apply_arroyo_readings_to_panels(self._last_arroyo_readings)
        if self._viewmodel.is_arroyo_connected():
            self._viewmodel.refresh_arroyo_readings()

    def _on_arroyo_readings_updated(self, data: dict):
        """Cache latest Arroyo poll and update Main tab, Manual Control, and visible linked windows."""
        try:
            self._last_arroyo_readings = dict(data) if isinstance(data, dict) else None
            self._apply_arroyo_readings_to_panels(data)
        except Exception:
            self.arroyo_actual_current_label.setText("—")
            self.arroyo_actual_temp_label.setText("—")

    def _apply_arroyo_readings_to_panels(self, data: dict) -> None:
        """Push one Arroyo readings dict to Main Laser/TEC, Manual Control Arroyo block, and Alignment when open."""
        if not isinstance(data, dict):
            return
        try:
            current = data.get("laser_current", data.get("actual_current"))
            temp = data.get("tec_temp", data.get("actual_temp"))
            # Laser diode current from Arroyo SCPI is in mA (same as Main tab).
            self.arroyo_actual_current_label.setText(f"{current:.4f} mA" if current is not None else "—")
            self.arroyo_actual_temp_label.setText(f"{temp:.2f} °C" if temp is not None else "—")
            max_curr = data.get("max_current")
            max_temp = data.get("max_temp")
            if not self.arroyo_max_current_spin.hasFocus() and max_curr is not None:
                self.arroyo_max_current_spin.setValue(max_curr)
            if not self.arroyo_max_temp_spin.hasFocus() and max_temp is not None:
                self.arroyo_max_temp_spin.setValue(max_temp)
            if not self.arroyo_set_current_spin.hasFocus() and data.get("laser_set_current") is not None:
                self.arroyo_set_current_spin.blockSignals(True)
                self.arroyo_set_current_spin.setValue(float(data["laser_set_current"]))
                self.arroyo_set_current_spin.blockSignals(False)
            if not self.arroyo_set_temp_spin.hasFocus() and data.get("tec_set_temp") is not None:
                self.arroyo_set_temp_spin.blockSignals(True)
                self.arroyo_set_temp_spin.setValue(float(data["tec_set_temp"]))
                self.arroyo_set_temp_spin.blockSignals(False)
            laser_voltage = data.get("laser_voltage")
            laser_set_current = data.get("laser_set_current")
            tec_voltage = data.get("tec_voltage")
            tec_current = data.get("tec_current")
            tec_set_temp = data.get("tec_set_temp")
            self.main_laser_current_value.setText(f"{current:.3f}" if current is not None else "-")
            self.main_laser_voltage_value.setText(f"{laser_voltage:.3f}" if laser_voltage is not None else "-")
            self.main_laser_set_current_value.setText(f"{laser_set_current:.3f}" if laser_set_current is not None else "-")
            self.main_tec_voltage_value.setText(f"{tec_voltage:.3f}" if tec_voltage is not None else "-")
            self.main_tec_temp_value.setText(f"{temp:.3f}" if temp is not None else "-")
            self.main_tec_current_value.setText(f"{tec_current:.3f}" if tec_current is not None else "-")
            self.main_tec_set_temp_value.setText(f"{tec_set_temp:.3f}" if tec_set_temp is not None else "-")
            # Only apply when the worker got a valid read; None = query failed — do not force OFF.
            if data.get("laser_on") is not None:
                self._arroyo_laser_on = bool(data["laser_on"])
            if data.get("tec_on") is not None:
                self._arroyo_tec_on = bool(data["tec_on"])
            self._arroyo_update_laser_tec_ui()
            align_w = getattr(self, "_alignment_window", None)
            if align_w is not None and hasattr(align_w, "update_laser_details"):
                align_w.update_laser_details(data)
        except Exception:
            self.arroyo_actual_current_label.setText("—")
            self.arroyo_actual_temp_label.setText("—")

    def _arroyo_update_laser_tec_ui(self):
        """Update Laser/TEC button text, highlight and LEDs from instrument state (_arroyo_laser_on / _arroyo_tec_on)."""
        btn_off = "QPushButton { background-color: #2d2d34; color: #e6e6e6; font-size: 13px; padding: 6px 12px; } QPushButton:hover { background-color: #3a3a42; }"
        btn_on = "QPushButton { background-color: #4caf50; color: white; font-size: 13px; padding: 6px 12px; } QPushButton:hover { background-color: #388E3C; }"
        led_off = "background-color: #555; border-radius: 8px; min-width: 16px; max-width: 16px; min-height: 16px; max-height: 16px;"
        led_on = "background-color: #4caf50; border-radius: 8px; min-width: 16px; max-width: 16px; min-height: 16px; max-height: 16px;"
        self.arroyo_laser_btn.setText("Laser Off" if self._arroyo_laser_on else "Laser On")
        self.arroyo_laser_btn.setStyleSheet(btn_on if self._arroyo_laser_on else btn_off)
        self.arroyo_laser_btn.setChecked(self._arroyo_laser_on)
        self.arroyo_tec_btn.setText("TEC Off" if self._arroyo_tec_on else "TEC On")
        self.arroyo_tec_btn.setStyleSheet(btn_on if self._arroyo_tec_on else btn_off)
        self.arroyo_tec_btn.setChecked(self._arroyo_tec_on)
        self.arroyo_laser_led.setStyleSheet(led_on if self._arroyo_laser_on else led_off)
        self.arroyo_tec_led.setStyleSheet(led_on if self._arroyo_tec_on else led_off)
        self.main_laser_status_value.setText("ON" if self._arroyo_laser_on else "OFF")
        self.main_tec_status_value.setText("ON" if self._arroyo_tec_on else "OFF")
        self.main_laser_led.setStyleSheet(led_on if self._arroyo_laser_on else led_off)
        self.main_tec_led.setStyleSheet(led_on if self._arroyo_tec_on else led_off)

    def _on_arroyo_set_current(self):
        """Set Current (mA) -> worker sends LAS:LDI (different thread)."""
        self._viewmodel.set_arroyo_laser_current(self.arroyo_set_current_spin.value())

    def _on_arroyo_set_temp(self):
        """Set Temperature -> worker sends TEC:T (different thread)."""
        self._viewmodel.set_arroyo_temp(self.arroyo_set_temp_spin.value())

    def _on_arroyo_max_current(self):
        """Max Current = laser current limit. Worker sends LAS:LIM:LDI (mA)."""
        self._viewmodel.set_arroyo_laser_current_limit(self.arroyo_max_current_spin.value())

    def _on_arroyo_max_temp(self):
        """Max Temp = TEC temp limit. Worker sends TEC:LIM:THI (different thread)."""
        self._viewmodel.set_arroyo_THI_limit(self.arroyo_max_temp_spin.value())

    def _on_arroyo_laser_clicked(self):
        """Toggle Laser -> worker: ON = TEC first if needed, then laser; OFF = laser only. UI follows Arroyo readback."""
        turning_on = not self._arroyo_laser_on
        if turning_on and not self._viewmodel.is_arroyo_connected():
            self._on_status_log_message("Laser ON requires Arroyo connected — open Engineer Control → Connection.")
            return
        desired = not self._arroyo_laser_on
        if desired:
            self._on_status_log_message("Laser ON: enabling TEC if needed, then laser (instrument readback).")
        self._viewmodel.set_arroyo_laser_output(desired)

    def _on_arroyo_tec_clicked(self):
        """Toggle TEC -> worker; UI follows Arroyo readback (same as Main Laser/TEC boxes)."""
        desired = not self._arroyo_tec_on
        self._viewmodel.set_arroyo_tec_output(desired)

    def _make_connection_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.addWidget(QLabel("Instruments — Ports"))
        # Scan All / Connect All / Save
        btn_row = QHBoxLayout()
        scan_all_btn = QPushButton("Scan All")
        scan_all_btn.setToolTip(
            "Refresh every row: COM for Arroyo/Actuator/Gentec, GPIB for Ando/Wavemeter, "
            "Kinesis for PRM, Thorlabs USB VISA for the powermeter."
        )
        scan_all_btn.setStyleSheet("QPushButton { background-color: #2196F3; color: white; } QPushButton:hover { background-color: #1976D2; }")
        scan_all_btn.clicked.connect(self._on_scan_all)
        btn_row.addWidget(scan_all_btn)
        connect_all_btn = QPushButton("Connect All")
        connect_all_btn.setStyleSheet("QPushButton { background-color: #4caf50; color: white; } QPushButton:hover { background-color: #388E3C; }")
        connect_all_btn.clicked.connect(self._on_connect_all)
        btn_row.addWidget(connect_all_btn)
        save_btn = QPushButton("Save")
        save_btn.setStyleSheet("QPushButton { background-color: #FF9800; color: white; } QPushButton:hover { background-color: #F57C00; }")
        save_btn.setToolTip("Save current addresses; next time app will auto-connect to these. Manual connect still works if addresses change.")
        save_btn.clicked.connect(self._on_save_connections)
        btn_row.addWidget(save_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)
        grid = QGridLayout()
        # Arroyo — COM only (same physical list as Actuator/Gentec scans; pick the port for this instrument)
        arroyo_lbl = QLabel("Arroyo (serial COM)")
        arroyo_lbl.setToolTip("Arroyo TEC/laser controller. Scan lists only serial COM ports on this PC.")
        grid.addWidget(arroyo_lbl, 0, 0)
        self.available_ports_combo = QComboBox()
        self.available_ports_combo.setMinimumWidth(120)
        self.available_ports_combo.setToolTip("COM port for Arroyo — use Scan COM to refresh the list.")
        grid.addWidget(self.available_ports_combo, 0, 1)
        scan_btn = QPushButton("Scan COM")
        scan_btn.setObjectName("btn_scan")
        scan_btn.setMinimumWidth(108)
        scan_btn.setToolTip("Detect serial COM ports and fill this row only.")
        scan_btn.setStyleSheet(
            "QPushButton#btn_scan { background-color: #2196F3; color: white; } "
            "QPushButton#btn_scan:hover { background-color: #1976D2; } "
            "QPushButton#btn_scan:pressed { background-color: #0D47A1; }"
        )
        scan_btn.clicked.connect(self._on_scan_ports)
        grid.addWidget(scan_btn, 0, 2)
        connect_btn = QPushButton("Connect")
        connect_btn.setObjectName("btn_connect")
        connect_btn.setStyleSheet(
            "QPushButton#btn_connect { background-color: #4caf50; color: white; } "
            "QPushButton#btn_connect:hover { background-color: #388E3C; } "
            "QPushButton#btn_connect:pressed { background-color: #2E7D32; }"
        )
        connect_btn.clicked.connect(self._on_connect_arroyo)
        grid.addWidget(connect_btn, 0, 3)
        disconnect_btn = QPushButton("Disconnect")
        disconnect_btn.setObjectName("btn_disconnect_arroyo")
        disconnect_btn.setStyleSheet(
            "QPushButton#btn_disconnect_arroyo { background-color: #f44336; color: white; } "
            "QPushButton#btn_disconnect_arroyo:hover { background-color: #d32f2f; } "
            "QPushButton#btn_disconnect_arroyo:pressed { background-color: #b71c1c; }"
        )
        disconnect_btn.clicked.connect(self._on_disconnect_arroyo)
        grid.addWidget(disconnect_btn, 0, 4)
        # Actuator — COM only
        act_lbl = QLabel("Actuator (serial COM)")
        act_lbl.setToolTip("Actuator / Arduino. Scan lists only serial COM ports.")
        grid.addWidget(act_lbl, 1, 0)
        self.actuator_ports_combo = QComboBox()
        self.actuator_ports_combo.setMinimumWidth(120)
        self.actuator_ports_combo.setToolTip("COM port for the actuator — use Scan COM to refresh.")
        grid.addWidget(self.actuator_ports_combo, 1, 1)
        scan_act_btn = QPushButton("Scan COM")
        scan_act_btn.setObjectName("btn_scan_actuator")
        scan_act_btn.setMinimumWidth(108)
        scan_act_btn.setToolTip("Detect serial COM ports and fill this row only.")
        scan_act_btn.setStyleSheet(
            "QPushButton#btn_scan_actuator { background-color: #2196F3; color: white; } "
            "QPushButton#btn_scan_actuator:hover { background-color: #1976D2; } "
        )
        scan_act_btn.clicked.connect(self._on_scan_ports_actuator)
        grid.addWidget(scan_act_btn, 1, 2)
        connect_act_btn = QPushButton("Connect")
        connect_act_btn.setObjectName("btn_connect_actuator")
        connect_act_btn.setStyleSheet(
            "QPushButton#btn_connect_actuator { background-color: #4caf50; color: white; } "
            "QPushButton#btn_connect_actuator:hover { background-color: #388E3C; } "
        )
        connect_act_btn.clicked.connect(self._on_connect_actuator)
        grid.addWidget(connect_act_btn, 1, 3)
        disconnect_act_btn = QPushButton("Disconnect")
        disconnect_act_btn.setObjectName("btn_disconnect_actuator")
        disconnect_act_btn.setStyleSheet(
            "QPushButton#btn_disconnect_actuator { background-color: #f44336; color: white; } "
            "QPushButton#btn_disconnect_actuator:hover { background-color: #d32f2f; } "
        )
        disconnect_act_btn.clicked.connect(self._on_disconnect_actuator)
        grid.addWidget(disconnect_act_btn, 1, 4)
        # Ando — GPIB VISA resources only
        ando_lbl = QLabel("Ando OSA (GPIB)")
        ando_lbl.setToolTip("Ando spectrum analyzer. Scan lists only GPIB VISA resources (e.g. GPIB0::5::INSTR).")
        grid.addWidget(ando_lbl, 2, 0)
        self.available_gpib_combo = QComboBox()
        self.available_gpib_combo.setMinimumWidth(180)
        self.available_gpib_combo.setEditable(True)
        self.available_gpib_combo.setToolTip("GPIB address for Ando — use Scan GPIB to refresh.")
        grid.addWidget(self.available_gpib_combo, 2, 1)
        scan_gpib_btn = QPushButton("Scan GPIB")
        scan_gpib_btn.setObjectName("btn_scan_gpib")
        scan_gpib_btn.setMinimumWidth(108)
        scan_gpib_btn.setToolTip("Detect GPIB instruments and fill this row only.")
        scan_gpib_btn.setStyleSheet(
            "QPushButton#btn_scan_gpib { background-color: #2196F3; color: white; } "
            "QPushButton#btn_scan_gpib:hover { background-color: #1976D2; } "
        )
        scan_gpib_btn.clicked.connect(self._on_scan_gpib)
        grid.addWidget(scan_gpib_btn, 2, 2)
        connect_ando_btn = QPushButton("Connect")
        connect_ando_btn.setObjectName("btn_connect_ando")
        connect_ando_btn.setStyleSheet(
            "QPushButton#btn_connect_ando { background-color: #4caf50; color: white; } "
            "QPushButton#btn_connect_ando:hover { background-color: #388E3C; } "
        )
        connect_ando_btn.clicked.connect(self._on_connect_ando)
        grid.addWidget(connect_ando_btn, 2, 3)
        disconnect_ando_btn = QPushButton("Disconnect")
        disconnect_ando_btn.setObjectName("btn_disconnect_ando")
        disconnect_ando_btn.setStyleSheet(
            "QPushButton#btn_disconnect_ando { background-color: #f44336; color: white; } "
            "QPushButton#btn_disconnect_ando:hover { background-color: #d32f2f; } "
        )
        disconnect_ando_btn.clicked.connect(self._on_disconnect_ando)
        grid.addWidget(disconnect_ando_btn, 2, 4)
        # Wavemeter — GPIB VISA resources only (non-editable: pick from list)
        wm_lbl = QLabel("Wavemeter (GPIB)")
        wm_lbl.setToolTip("HighFinesse / wavemeter on GPIB. Scan lists only GPIB VISA resources.")
        grid.addWidget(wm_lbl, 3, 0)
        self.wavemeter_gpib_combo = QComboBox()
        self.wavemeter_gpib_combo.setMinimumWidth(180)
        self.wavemeter_gpib_combo.setEditable(False)
        self.wavemeter_gpib_combo.setToolTip("GPIB address for the wavemeter — use Scan GPIB to refresh.")
        grid.addWidget(self.wavemeter_gpib_combo, 3, 1)
        scan_wm_btn = QPushButton("Scan GPIB")
        scan_wm_btn.setMinimumWidth(108)
        scan_wm_btn.setToolTip("Detect GPIB instruments and fill this row only.")
        scan_wm_btn.setStyleSheet("QPushButton { background-color: #2196F3; color: white; } QPushButton:hover { background-color: #1976D2; }")
        scan_wm_btn.clicked.connect(self._on_scan_gpib_wavemeter)
        grid.addWidget(scan_wm_btn, 3, 2)
        connect_wm_btn = QPushButton("Connect")
        connect_wm_btn.setStyleSheet("QPushButton { background-color: #4caf50; color: white; } QPushButton:hover { background-color: #388E3C; }")
        connect_wm_btn.clicked.connect(self._on_connect_wavemeter)
        grid.addWidget(connect_wm_btn, 3, 3)
        disconnect_wm_btn = QPushButton("Disconnect")
        disconnect_wm_btn.setStyleSheet("QPushButton { background-color: #f44336; color: white; } QPushButton:hover { background-color: #d32f2f; }")
        disconnect_wm_btn.clicked.connect(self._on_disconnect_wavemeter)
        grid.addWidget(disconnect_wm_btn, 3, 4)
        # PRM — Kinesis serial numbers only (not COM)
        prm_lbl = QLabel("PRM stage (Kinesis)")
        prm_lbl.setToolTip("Thorlabs PRM / KCube. Scan lists only Kinesis motor controller serial numbers.")
        grid.addWidget(prm_lbl, 4, 0)
        self.prm_serial_combo = QComboBox()
        self.prm_serial_combo.setMinimumWidth(120)
        self.prm_serial_combo.setEditable(True)
        self.prm_serial_combo.setToolTip("Kinesis serial — use Scan Kinesis to refresh.")
        grid.addWidget(self.prm_serial_combo, 4, 1)
        scan_prm_btn = QPushButton("Scan Kinesis")
        scan_prm_btn.setMinimumWidth(108)
        scan_prm_btn.setToolTip("Detect Thorlabs Kinesis devices and fill this row only.")
        scan_prm_btn.setStyleSheet("QPushButton { background-color: #2196F3; color: white; } QPushButton:hover { background-color: #1976D2; }")
        scan_prm_btn.clicked.connect(self._on_scan_prm)
        grid.addWidget(scan_prm_btn, 4, 2)
        connect_prm_btn = QPushButton("Connect")
        connect_prm_btn.setStyleSheet("QPushButton { background-color: #4caf50; color: white; } QPushButton:hover { background-color: #388E3C; }")
        connect_prm_btn.clicked.connect(self._on_connect_prm)
        grid.addWidget(connect_prm_btn, 4, 3)
        disconnect_prm_btn = QPushButton("Disconnect")
        disconnect_prm_btn.setStyleSheet("QPushButton { background-color: #f44336; color: white; } QPushButton:hover { background-color: #d32f2f; }")
        disconnect_prm_btn.clicked.connect(self._on_disconnect_prm)
        grid.addWidget(disconnect_prm_btn, 4, 4)
        # Gentec — COM only
        g_lbl = QLabel("Gentec powermeter (COM)")
        g_lbl.setToolTip("Gentec USB/serial powermeter. Scan lists only serial COM ports.")
        grid.addWidget(g_lbl, 5, 0)
        self.gentec_ports_combo = QComboBox()
        self.gentec_ports_combo.setMinimumWidth(120)
        self.gentec_ports_combo.setToolTip("COM port for Gentec — use Scan COM to refresh.")
        grid.addWidget(self.gentec_ports_combo, 5, 1)
        scan_gentec_btn = QPushButton("Scan COM")
        scan_gentec_btn.setMinimumWidth(108)
        scan_gentec_btn.setToolTip("Detect serial COM ports and fill this row only.")
        scan_gentec_btn.setStyleSheet("QPushButton { background-color: #2196F3; color: white; } QPushButton:hover { background-color: #1976D2; }")
        scan_gentec_btn.clicked.connect(self._on_scan_ports_gentec)
        grid.addWidget(scan_gentec_btn, 5, 2)
        connect_gentec_btn = QPushButton("Connect")
        connect_gentec_btn.setStyleSheet("QPushButton { background-color: #4caf50; color: white; } QPushButton:hover { background-color: #388E3C; }")
        connect_gentec_btn.clicked.connect(self._on_connect_gentec)
        grid.addWidget(connect_gentec_btn, 5, 3)
        disconnect_gentec_btn = QPushButton("Disconnect")
        disconnect_gentec_btn.setStyleSheet("QPushButton { background-color: #f44336; color: white; } QPushButton:hover { background-color: #d32f2f; }")
        disconnect_gentec_btn.clicked.connect(self._on_disconnect_gentec)
        grid.addWidget(disconnect_gentec_btn, 5, 4)
        # Thorlabs — USB VISA (Thorlabs VID); fallback to full VISA list if none
        tl_lbl = QLabel("Thorlabs powermeter (USB)")
        tl_lbl.setToolTip("Thorlabs PM100 / etc. over USB. Scan lists Thorlabs USB VISA (VID 0x1313), or all VISA if none match.")
        grid.addWidget(tl_lbl, 6, 0)
        self.thorlabs_visa_combo = QComboBox()
        self.thorlabs_visa_combo.setMinimumWidth(180)
        self.thorlabs_visa_combo.setEditable(True)
        self.thorlabs_visa_combo.setToolTip("VISA resource string — use Scan Thorlabs to refresh.")
        grid.addWidget(self.thorlabs_visa_combo, 6, 1)
        scan_thorlabs_btn = QPushButton("Scan Thorlabs")
        scan_thorlabs_btn.setMinimumWidth(108)
        scan_thorlabs_btn.setToolTip("Detect Thorlabs USB powermeters (VISA) and fill this row only.")
        scan_thorlabs_btn.setStyleSheet("QPushButton { background-color: #2196F3; color: white; } QPushButton:hover { background-color: #1976D2; }")
        scan_thorlabs_btn.clicked.connect(self._on_scan_visa_thorlabs)
        grid.addWidget(scan_thorlabs_btn, 6, 2)
        connect_thorlabs_btn = QPushButton("Connect")
        connect_thorlabs_btn.setStyleSheet("QPushButton { background-color: #4caf50; color: white; } QPushButton:hover { background-color: #388E3C; }")
        connect_thorlabs_btn.clicked.connect(self._on_connect_thorlabs)
        grid.addWidget(connect_thorlabs_btn, 6, 3)
        disconnect_thorlabs_btn = QPushButton("Disconnect")
        disconnect_thorlabs_btn.setStyleSheet("QPushButton { background-color: #f44336; color: white; } QPushButton:hover { background-color: #d32f2f; }")
        disconnect_thorlabs_btn.clicked.connect(self._on_disconnect_thorlabs)
        grid.addWidget(disconnect_thorlabs_btn, 6, 4)
        layout.addLayout(grid)
        conn_hint = QLabel(
            "Each Scan button only refreshes that row: <b>Scan COM</b> — serial ports; "
            "<b>Scan GPIB</b> — GPIB VISA addresses; <b>Scan Kinesis</b> — PRM serials; "
            "<b>Scan Thorlabs</b> — USB powermeters (Thorlabs VID). "
            "<b>Scan All</b> runs every detector and fills each combo with the matching resource type."
        )
        conn_hint.setWordWrap(True)
        conn_hint.setTextFormat(QtCompat.RichText)
        conn_hint.setStyleSheet("color: #aaaaaa; font-size: 11px; padding: 6px 2px 0 2px;")
        layout.addWidget(conn_hint)
        layout.addStretch()
        # Saved addresses + background scan run from _complete_heavy_startup (after first paint), not here.
        self._connection_tab_saved_applied = False
        return w

    def _make_engineer_control_tab(self) -> QWidget:
        """Engineer Control: nested tabs — Manual Control and Connection (instruments / ports)."""
        outer = QWidget()
        lay = QVBoxLayout(outer)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        inner = QTabWidget()
        inner.setObjectName("engineerControlInnerTabs")
        inner.setDocumentMode(True)
        inner.setStyleSheet("QTabWidget::pane { background-color: #1e1e23; }")
        _eng_tb = inner.tabBar()
        if _eng_tb is not None:
            _eng_tb.setElideMode(QtCompat.ElideNone)  # type: ignore[attr-defined]
            _eng_tb.setUsesScrollButtons(False)
        inner.addTab(self._make_manual_control_tab(), "Manual Control")
        inner.addTab(self._make_connection_tab(), "Connection")
        inner.setCurrentIndex(0)
        self._engineer_control_inner_tabs = inner
        lay.addWidget(inner)
        return outer

    def _on_ando_center(self):
        t = self.ando_center_edit.text().strip()
        if t:
            try:
                self._viewmodel.set_ando_center_wl(float(t))
            except ValueError:
                pass

    def _on_ando_span(self):
        t = self.ando_span_edit.text().strip()
        if t:
            try:
                self._viewmodel.set_ando_span(float(t))
            except ValueError:
                pass

    def _on_ando_ref_level(self):
        t = self.ando_ref_level_edit.text().strip()
        if t:
            try:
                self._viewmodel.set_ando_ref_level(float(t))
            except ValueError:
                pass

    def _on_ando_log_scale(self):
        t = self.ando_log_scale_edit.text().strip()
        if t:
            try:
                self._viewmodel.set_ando_log_scale(float(t))
            except ValueError:
                pass

    def _on_ando_resolution(self):
        t = self.ando_resolution_edit.text().strip()
        if t:
            try:
                self._viewmodel.set_ando_resolution(float(t))
            except ValueError:
                pass

    def _on_ando_sensitivity(self, index: int):
        self._viewmodel.set_ando_sensitivity_index(index)

    def _on_ando_analysis_dfb(self):
        self._viewmodel.set_ando_analysis_dfb_ld()

    def _on_ando_analysis_led(self):
        self._viewmodel.set_ando_analysis_led()

    def _on_scan_ports(self):
        try:
            ports = self._viewmodel.scan_ports()
            self.available_ports_combo.clear()
            self.available_ports_combo.addItems(ports if ports else ["(no ports found)"])
            if ports:
                self.main_status_log.appendPlainText(
                    "Arroyo — COM: {} port(s): {}".format(len(ports), ", ".join(ports))
                )
            else:
                self.main_status_log.appendPlainText("Arroyo — COM: no serial ports found.")
        except Exception as e:
            self.available_ports_combo.clear()
            self.available_ports_combo.addItems(["(no ports found)"])
            self.main_status_log.appendPlainText("Arroyo — COM scan failed: {}".format(e))
            QMessageBox.warning(self, "Scan", "Arroyo COM scan failed: {}".format(e))

    def _on_connect_arroyo(self):
        port = self.available_ports_combo.currentText().strip()
        if not port or port == "(no ports found)":
            QMessageBox.warning(self, "Connection", "Select a port and run Scan first.")
            return
        self._set_footer_connecting()
        self._viewmodel.connect_arroyo(port)  # runs in worker thread; footer updates when done

    def _on_disconnect_arroyo(self):
        self._viewmodel.disconnect_arroyo()

    def _on_scan_gpib(self):
        try:
            resources = self._viewmodel.scan_gpib()
            self.available_gpib_combo.clear()
            self.available_gpib_combo.addItems(resources if resources else ["(no GPIB found)"])
            if resources:
                self.main_status_log.appendPlainText(
                    "Ando — GPIB: {} resource(s): {}".format(len(resources), ", ".join(resources))
                )
            else:
                self.main_status_log.appendPlainText("Ando — GPIB: no GPIB addresses found.")
        except Exception as e:
            self.available_gpib_combo.clear()
            self.available_gpib_combo.addItems(["(no GPIB found)"])
            self.main_status_log.appendPlainText("Ando — GPIB scan failed: {}".format(e))
            QMessageBox.warning(self, "Scan", "GPIB scan failed: {}".format(e))

    def _on_connect_ando(self):
        addr = self.available_gpib_combo.currentText().strip()
        if not addr or addr == "(no GPIB found)":
            QMessageBox.warning(self, "Connection", "Select a GPIB address and run Scan first.")
            return
        self._set_footer_connecting()
        self._viewmodel.connect_ando(addr)

    def _on_disconnect_ando(self):
        self._viewmodel.disconnect_ando()

    def _on_scan_ports_actuator(self):
        try:
            ports = self._viewmodel.scan_ports()
            self.actuator_ports_combo.clear()
            self.actuator_ports_combo.addItems(ports if ports else ["(no ports found)"])
            if ports:
                self.main_status_log.appendPlainText(
                    "Actuator — COM: {} port(s): {}".format(len(ports), ", ".join(ports))
                )
            else:
                self.main_status_log.appendPlainText("Actuator — COM: no serial ports found.")
        except Exception as e:
            self.actuator_ports_combo.clear()
            self.actuator_ports_combo.addItems(["(no ports found)"])
            self.main_status_log.appendPlainText("Actuator — COM scan failed: {}".format(e))
            QMessageBox.warning(self, "Scan", "Actuator COM scan failed: {}".format(e))

    def _on_connect_actuator(self):
        port = self.actuator_ports_combo.currentText().strip()
        if not port or port == "(no ports found)":
            QMessageBox.warning(self, "Connection", "Select a port and run Scan first.")
            return
        self._set_footer_connecting()
        self._viewmodel.connect_actuator(port)

    def _on_disconnect_actuator(self):
        self._viewmodel.disconnect_actuator()

    def _on_scan_gpib_wavemeter(self):
        try:
            resources = self._viewmodel.scan_gpib()
            self.wavemeter_gpib_combo.clear()
            self.wavemeter_gpib_combo.addItems(resources if resources else ["(no GPIB found)"])
            if resources:
                self.main_status_log.appendPlainText(
                    "Wavemeter — GPIB: {} resource(s): {}".format(len(resources), ", ".join(resources))
                )
            else:
                self.main_status_log.appendPlainText("Wavemeter — GPIB: no GPIB addresses found.")
        except Exception as e:
            self.wavemeter_gpib_combo.clear()
            self.wavemeter_gpib_combo.addItems(["(no GPIB found)"])
            self.main_status_log.appendPlainText("Wavemeter — GPIB scan failed: {}".format(e))
            QMessageBox.warning(self, "Scan", "Wavemeter GPIB scan failed: {}".format(e))

    def _on_connect_wavemeter(self):
        # Use selected list item (combo non-editable) or currentText() when one item loaded from saved
        addr = self.wavemeter_gpib_combo.currentText().strip()
        if not addr or addr == "(no GPIB found)":
            QMessageBox.warning(self, "Connection", "Select a GPIB address and run Scan first (or Save then Connect All).")
            return
        self._set_footer_connecting()
        self._viewmodel.connect_wavemeter(addr)

    def _on_disconnect_wavemeter(self):
        self._viewmodel.disconnect_wavemeter()

    def _on_apply_wavemeter_range(self):
        r = self.wavemeter_range_combo.currentText().strip()
        state = self._viewmodel.get_connection_state()
        if not state.get("Wavemeter"):
            self.main_status_log.appendPlainText("Wavemeter not connected. Connect wavemeter first, then Apply range.")
            return
        self.main_status_log.appendPlainText("Applying wavemeter range: {}.".format(r))
        self._viewmodel.apply_wavemeter_range(r)

    def _on_scan_prm(self):
        try:
            serials = self._viewmodel.scan_prm()
            self.prm_serial_combo.clear()
            if serials:
                self.prm_serial_combo.addItems(serials)
                self.main_status_log.appendPlainText(
                    "PRM Scan (Kinesis): {} device(s): {}".format(len(serials), ", ".join(serials))
                )
            else:
                ok, msg = self._viewmodel.get_prm_scan_status()
                self.prm_serial_combo.addItems(["(no devices found)"])
                line = "PRM Scan (Kinesis): no devices."
                if msg:
                    line += " " + msg
                self.main_status_log.appendPlainText(line)
                if not ok and msg:
                    QMessageBox.warning(self, "PRM Scan", msg)
        except Exception as e:
            self.prm_serial_combo.clear()
            self.prm_serial_combo.addItems(["(no devices found)"])
            self.main_status_log.appendPlainText("PRM Scan (Kinesis): failed — {}".format(e))
            QMessageBox.warning(self, "Scan", "PRM scan failed: {}".format(e))
    def _on_connect_prm(self):
        raw = self.prm_serial_combo.currentText().strip()
        if not raw or raw == "(no devices found)":
            QMessageBox.warning(self, "Connection", "Select a PRM serial number and run Scan first.")
            return
        # Pass serial without quotes so Kinesis gets plain string (e.g. 27271436 not '27271436')
        from instruments.prm import _normalize_serial
        serial_number = _normalize_serial(raw)
        if not serial_number:
            QMessageBox.warning(self, "Connection", "Invalid PRM serial.")
            return
        self._set_footer_connecting()
        self._viewmodel.connect_prm(serial_number)
    def _on_disconnect_prm(self):
        self._viewmodel.disconnect_prm()

    def _on_scan_ports_gentec(self):
        try:
            ports = self._viewmodel.scan_ports()
            self.gentec_ports_combo.clear()
            self.gentec_ports_combo.addItems(ports if ports else ["(no ports found)"])
            if ports:
                self.main_status_log.appendPlainText(
                    "Gentec — COM: {} port(s): {}".format(len(ports), ", ".join(ports))
                )
            else:
                self.main_status_log.appendPlainText("Gentec — COM: no serial ports found.")
        except Exception as e:
            self.gentec_ports_combo.clear()
            self.gentec_ports_combo.addItems(["(no ports found)"])
            self.main_status_log.appendPlainText("Gentec — COM scan failed: {}".format(e))
            QMessageBox.warning(self, "Scan", "Gentec COM scan failed: {}".format(e))
    def _on_connect_gentec(self):
        port = self.gentec_ports_combo.currentText().strip()
        if not port or port == "(no ports found)":
            QMessageBox.warning(self, "Connection", "Select a port and run Scan first.")
            return
        self._set_footer_connecting()
        self._viewmodel.connect_gentec(port)
    def _on_disconnect_gentec(self):
        self._viewmodel.disconnect_gentec()

    def _on_scan_visa_thorlabs(self):
        try:
            resources = self._viewmodel.scan_thorlabs_powermeters()
            self.thorlabs_visa_combo.clear()
            if resources:
                self.thorlabs_visa_combo.addItems(resources)
                self.main_status_log.appendPlainText(
                    "Thorlabs scan (USB VID 0x1313): {} device(s): {}".format(
                        len(resources), ", ".join(resources)
                    )
                )
            else:
                # Fallback: full VISA list (e.g. non-standard address or driver only lists under full scan)
                all_visa = self._viewmodel.scan_visa()
                if all_visa:
                    self.thorlabs_visa_combo.addItems(all_visa)
                    self.main_status_log.appendPlainText(
                        "Thorlabs USB (0x1313): none. Showing all {} VISA resource(s) — pick the Thorlabs line."
                        .format(len(all_visa))
                    )
                else:
                    self.thorlabs_visa_combo.addItems(["(no Thorlabs / VISA found)"])
                    self.main_status_log.appendPlainText(
                        "Thorlabs scan: no USB 0x1313 and no VISA resources (install NI-VISA or use pyvisa-py)."
                    )
        except Exception as e:
            self.thorlabs_visa_combo.clear()
            self.thorlabs_visa_combo.addItems(["(no Thorlabs / VISA found)"])
            self.main_status_log.appendPlainText("Thorlabs scan failed: {}".format(e))
            QMessageBox.warning(self, "Scan", "Thorlabs/VISA scan failed: {}".format(e))
    def _on_connect_thorlabs(self):
        visa_resource = self.thorlabs_visa_combo.currentText().strip()
        if not visa_resource or visa_resource in ("(no VISA found)", "(no Thorlabs / VISA found)"):
            QMessageBox.warning(self, "Connection", "Select a VISA resource and run Scan first.")
            return
        self._set_footer_connecting()
        self._viewmodel.connect_thorlabs(visa_resource)
    def _on_disconnect_thorlabs(self):
        self._viewmodel.disconnect_thorlabs()

    def _on_scan_all(self):
        """Scan COM, GPIB, VISA, and PRM (Kinesis)."""
        self.main_status_log.appendPlainText(
            "Scan All: COM (Arroyo/Actuator/Gentec), GPIB (Ando/Wavemeter), Kinesis (PRM), Thorlabs USB + full VISA..."
        )
        try:
            ports = self._viewmodel.scan_ports()
            port_list = ports if ports else ["(no ports found)"]
            self.available_ports_combo.clear()
            self.available_ports_combo.addItems(port_list)
            self.actuator_ports_combo.clear()
            self.actuator_ports_combo.addItems(port_list)
            self.gentec_ports_combo.clear()
            self.gentec_ports_combo.addItems(port_list)
            gpib = self._viewmodel.scan_gpib()
            gpib_list = gpib if gpib else ["(no GPIB found)"]
            self.available_gpib_combo.clear()
            self.available_gpib_combo.addItems(gpib_list)
            self.wavemeter_gpib_combo.clear()
            self.wavemeter_gpib_combo.addItems(gpib_list)
            prm_serials = self._viewmodel.scan_prm()
            self.prm_serial_combo.clear()
            if prm_serials:
                self.prm_serial_combo.addItems(prm_serials)
            else:
                self.prm_serial_combo.addItems(["(no devices found)"])
            visa_list = self._viewmodel.scan_visa()
            thorlabs_usb = self._viewmodel.scan_thorlabs_powermeters()
            self.thorlabs_visa_combo.clear()
            if thorlabs_usb:
                self.thorlabs_visa_combo.addItems(thorlabs_usb)
            elif visa_list:
                self.thorlabs_visa_combo.addItems(visa_list)
            else:
                self.thorlabs_visa_combo.addItems(["(no Thorlabs / VISA found)"])
            _log_scan_results(ports, gpib, prm_serials, visa_list, thorlabs_usb)
            self.main_status_log.appendPlainText("Scan All: done.")
        except Exception as e:
            QMessageBox.warning(self, "Scan All", "One or more scans failed: {}".format(e))

    def _schedule_wavemeter_connect(self, wm_addr: str, delay_ms: int) -> None:
        """Connect wavemeter after delay_ms (0 = immediate). Stagger avoids GPIB bus contention with Ando."""
        a = (wm_addr or "").strip()
        if not a:
            return
        if delay_ms <= 0:
            self._viewmodel.connect_wavemeter(a)
        else:
            QTimer.singleShot(delay_ms, lambda addr=a: self._viewmodel.connect_wavemeter(addr))

    def _on_connect_all(self, use_saved=None, wavemeter_delay_ms: int = 700, defer_prm_ms: int = 0):
        """Connect to all instruments. If use_saved is a dict (from load_saved_addresses), use those addresses; otherwise use current combo values.
        defer_prm_ms > 0: schedule PRM (blocking Kinesis) after that many ms so other workers connect first (startup auto-connect)."""
        self._set_footer_connecting()
        # Button click passes bool (clicked signal); only use saved when explicitly given a dict
        if isinstance(use_saved, dict):
            attempts = []
            port = (use_saved.get("arroyo_port") or "").strip()
            if port:
                self._viewmodel.connect_arroyo(port)
                attempts.append(("Arroyo", port))
            port = (use_saved.get("actuator_port") or "").strip()
            if port:
                self._viewmodel.connect_actuator(port)
                attempts.append(("Actuator", port))
            addr = (use_saved.get("ando_gpib") or "").strip()
            if addr:
                self._viewmodel.connect_ando(addr)
                attempts.append(("Ando", addr))
            addr = (use_saved.get("wavemeter_gpib") or "").strip()
            if addr:
                self._schedule_wavemeter_connect(addr, int(wavemeter_delay_ms))
                attempts.append(("Wavemeter", addr))
            serial_number = (use_saved.get("prm_serial") or "").strip()
            if serial_number:
                if defer_prm_ms > 0:
                    QTimer.singleShot(int(defer_prm_ms), lambda s=serial_number: self._viewmodel.connect_prm(s))
                    attempts.append(("PRM", serial_number + " (queued)"))
                else:
                    self._viewmodel.connect_prm(serial_number)
                    attempts.append(("PRM", serial_number))
            port = (use_saved.get("gentec_port") or "").strip()
            if port:
                self._viewmodel.connect_gentec(port)
                attempts.append(("Gentec", port))
            visa_resource = (use_saved.get("thorlabs_visa") or "").strip()
            if visa_resource:
                self._viewmodel.connect_thorlabs(visa_resource)
                attempts.append(("Thorlabs", visa_resource))
            _log_connect_attempts(attempts)
            return
        attempts = []
        port = self.available_ports_combo.currentText().strip()
        if port and port != "(no ports found)":
            self._viewmodel.connect_arroyo(port)
            attempts.append(("Arroyo", port))
        port = self.actuator_ports_combo.currentText().strip()
        if port and port != "(no ports found)":
            self._viewmodel.connect_actuator(port)
            attempts.append(("Actuator", port))
        addr = self.available_gpib_combo.currentText().strip()
        if addr and addr != "(no GPIB found)":
            self._viewmodel.connect_ando(addr)
            attempts.append(("Ando", addr))
        addr = self.wavemeter_gpib_combo.currentText().strip()
        if addr and addr != "(no GPIB found)":
            self._schedule_wavemeter_connect(addr, int(wavemeter_delay_ms))
            attempts.append(("Wavemeter", addr))
        serial_number = self.prm_serial_combo.currentText().strip()
        if serial_number and serial_number != "(no devices found)":
            if defer_prm_ms > 0:
                QTimer.singleShot(int(defer_prm_ms), lambda s=serial_number: self._viewmodel.connect_prm(s))
                attempts.append(("PRM", serial_number + " (queued)"))
            else:
                self._viewmodel.connect_prm(serial_number)
                attempts.append(("PRM", serial_number))
        port = self.gentec_ports_combo.currentText().strip()
        if port and port != "(no ports found)":
            self._viewmodel.connect_gentec(port)
            attempts.append(("Gentec", port))
        visa_resource = self.thorlabs_visa_combo.currentText().strip()
        if visa_resource and visa_resource not in ("(no VISA found)", "(no Thorlabs / VISA found)"):
            self._viewmodel.connect_thorlabs(visa_resource)
            attempts.append(("Thorlabs", visa_resource))
        _log_connect_attempts(attempts)

    def _on_disconnect_all(self):
        """Disconnect all instruments from the footer."""
        self._viewmodel.disconnect_arroyo()
        self._viewmodel.disconnect_actuator()
        self._viewmodel.disconnect_ando()
        self._viewmodel.disconnect_wavemeter()
        self._viewmodel.disconnect_prm()
        self._viewmodel.disconnect_gentec()
        self._viewmodel.disconnect_thorlabs()
        self.main_status_log.appendPlainText("Disconnect All: disconnecting all instruments.")

    def _on_footer_reconnect(self):
        """Reconnect using saved addresses if available, else current combo selections."""
        saved = self._viewmodel.load_saved_addresses()
        has_saved = (
            isinstance(saved, dict)
            and any(
                [
                    (saved.get("arroyo_port") or "").strip(),
                    (saved.get("actuator_port") or "").strip(),
                    (saved.get("ando_gpib") or "").strip(),
                    (saved.get("wavemeter_gpib") or "").strip(),
                    (saved.get("prm_serial") or "").strip(),
                    (saved.get("gentec_port") or "").strip(),
                    (saved.get("thorlabs_visa") or "").strip(),
                ]
            )
        )
        # Close all sessions first so COM/GPIB/VISA handles release (Windows); then connect after a short settle.
        self._on_disconnect_all()
        self.main_status_log.appendPlainText("Reconnect: closed all sessions; connecting again…")
        if has_saved:
            QTimer.singleShot(280, lambda s=saved: self._on_connect_all(use_saved=s, wavemeter_delay_ms=80))
        else:
            QTimer.singleShot(280, lambda: self._on_connect_all(wavemeter_delay_ms=80))

    def _on_save_connections(self):
        """Save current addresses; next startup will load them and can auto-connect. Manual connect always available."""
        addresses = {
            "arroyo_port": self.available_ports_combo.currentText().strip(),
            "actuator_port": self.actuator_ports_combo.currentText().strip(),
            "ando_gpib": self.available_gpib_combo.currentText().strip(),
            "wavemeter_gpib": self.wavemeter_gpib_combo.currentText().strip(),
            "prm_serial": self.prm_serial_combo.currentText().strip(),
            "gentec_port": self.gentec_ports_combo.currentText().strip(),
            "thorlabs_visa": self.thorlabs_visa_combo.currentText().strip(),
            "auto_connect": "1",
        }
        self._viewmodel.save_connection_addresses(addresses)
        self.main_status_log.appendPlainText("Connection: addresses saved.")
        QMessageBox.information(self, "Connection", "Addresses saved. Next time the app will use these for auto-connect. You can still Scan and connect manually if addresses change.")

    def _seed_connection_combos_from_saved(self, saved: dict) -> None:
        """Show saved addresses in combos immediately (before slow COM/GPIB/VISA scans finish)."""
        def uniq(keys):
            out = []
            for k in keys:
                v = (saved.get(k) or "").strip()
                if v and v not in out:
                    out.append(v)
            return out

        ports = uniq(("arroyo_port", "actuator_port", "gentec_port"))
        if not ports:
            ports = ["(loading COM list…)"]
        self.available_ports_combo.clear()
        self.available_ports_combo.addItems(ports)
        self.actuator_ports_combo.clear()
        self.actuator_ports_combo.addItems(list(ports))
        self.gentec_ports_combo.clear()
        self.gentec_ports_combo.addItems(list(ports))

        gpib = uniq(("ando_gpib", "wavemeter_gpib"))
        if not gpib:
            gpib = ["(loading GPIB list…)"]
        self.available_gpib_combo.clear()
        self.available_gpib_combo.addItems(gpib)
        self.wavemeter_gpib_combo.clear()
        self.wavemeter_gpib_combo.addItems(list(gpib))

        self.thorlabs_visa_combo.clear()
        tv = (saved.get("thorlabs_visa") or "").strip()
        if tv:
            self.thorlabs_visa_combo.addItem(tv)
        else:
            self.thorlabs_visa_combo.addItem("(loading Thorlabs / VISA…)")

        self.prm_serial_combo.clear()
        pm = (saved.get("prm_serial") or "").strip()
        if pm:
            self.prm_serial_combo.addItem(pm)
        else:
            self.prm_serial_combo.addItem("(no devices found)")

        def set_combo(cb, value):
            if not value:
                return
            i = cb.findText(value)
            if i >= 0:
                cb.setCurrentIndex(i)
            else:
                cb.insertItem(0, value)
                cb.setCurrentIndex(0)

        set_combo(self.available_ports_combo, saved.get("arroyo_port", ""))
        set_combo(self.actuator_ports_combo, saved.get("actuator_port", ""))
        set_combo(self.available_gpib_combo, saved.get("ando_gpib", ""))
        wm = saved.get("wavemeter_gpib", "")
        if wm:
            i = self.wavemeter_gpib_combo.findText(wm)
            if i >= 0:
                self.wavemeter_gpib_combo.setCurrentIndex(i)
            else:
                self.wavemeter_gpib_combo.insertItem(0, wm)
                self.wavemeter_gpib_combo.setCurrentIndex(0)
        set_combo(self.gentec_ports_combo, saved.get("gentec_port", ""))
        set_combo(self.thorlabs_visa_combo, saved.get("thorlabs_visa", ""))

    def _apply_saved_addresses_and_auto_connect(self):
        """Load saved addresses, seed combos, auto-connect immediately if enabled; refresh port lists in background."""
        if getattr(self, "_connection_tab_saved_applied", True):
            return
        self._connection_tab_saved_applied = True
        saved = self._viewmodel.load_saved_addresses()
        self._seed_connection_combos_from_saved(saved)
        # Defer Connect All until after first show (see showEvent) so the UI paints with theme, not during white buffer.
        if saved.get("auto_connect", "1") == "1":
            self._pending_startup_auto_connect = saved

        def work():
            try:
                ports = self._viewmodel.scan_ports()
                port_list = ports if ports else ["(no ports found)"]
            except Exception:
                port_list = ["(no ports found)"]
            try:
                gpib = self._viewmodel.scan_gpib()
                gpib_list = gpib if gpib else ["(no GPIB found)"]
            except Exception:
                gpib_list = ["(no GPIB found)"]
            try:
                thorlabs_usb = self._viewmodel.scan_thorlabs_powermeters()
                visa_list = self._viewmodel.scan_visa()
            except Exception:
                thorlabs_usb = []
                visa_list = []
            payload = {
                "port_list": port_list,
                "gpib_list": gpib_list,
                "thorlabs_usb": thorlabs_usb,
                "visa_list": visa_list,
                "saved": saved,
            }
            self._initial_scan_bridge.done.emit(payload)

        threading.Thread(target=work, daemon=True).start()

    @pyqtSlot(object)
    def _on_initial_connection_scan_done(self, payload: object) -> None:
        """Merge full COM/GPIB/VISA scan into combos; keep saved selections. Does not reconnect (already connected)."""
        if not isinstance(payload, dict):
            return
        try:
            port_list = payload.get("port_list") or ["(no ports found)"]
            gpib_list = payload.get("gpib_list") or ["(no GPIB found)"]
            thorlabs_usb = payload.get("thorlabs_usb") or []
            visa_list = payload.get("visa_list") or []
            saved = payload.get("saved") or {}
        except Exception:
            return

        self.available_ports_combo.clear()
        self.available_ports_combo.addItems(port_list)
        self.actuator_ports_combo.clear()
        self.actuator_ports_combo.addItems(port_list)
        self.gentec_ports_combo.clear()
        self.gentec_ports_combo.addItems(port_list)
        self.available_gpib_combo.clear()
        self.available_gpib_combo.addItems(gpib_list)
        self.wavemeter_gpib_combo.clear()
        self.wavemeter_gpib_combo.addItems(gpib_list)
        self.thorlabs_visa_combo.clear()
        if thorlabs_usb:
            self.thorlabs_visa_combo.addItems(thorlabs_usb)
        elif visa_list:
            self.thorlabs_visa_combo.addItems(visa_list)
        else:
            self.thorlabs_visa_combo.addItems(["(no Thorlabs / VISA found)"])

        def set_combo(cb, value):
            if not value:
                return
            i = cb.findText(value)
            if i >= 0:
                cb.setCurrentIndex(i)
            else:
                cb.insertItem(0, value)
                cb.setCurrentIndex(0)

        set_combo(self.available_ports_combo, saved.get("arroyo_port", ""))
        set_combo(self.actuator_ports_combo, saved.get("actuator_port", ""))
        set_combo(self.available_gpib_combo, saved.get("ando_gpib", ""))
        wm = saved.get("wavemeter_gpib", "")
        if wm:
            i = self.wavemeter_gpib_combo.findText(wm)
            if i >= 0:
                self.wavemeter_gpib_combo.setCurrentIndex(i)
            else:
                self.wavemeter_gpib_combo.insertItem(0, wm)
                self.wavemeter_gpib_combo.setCurrentIndex(0)
        set_combo(self.prm_serial_combo, saved.get("prm_serial", ""))
        set_combo(self.gentec_ports_combo, saved.get("gentec_port", ""))
        set_combo(self.thorlabs_visa_combo, saved.get("thorlabs_visa", ""))

        self.main_status_log.appendPlainText("Connection tab: full device lists loaded (background scan).")

    def _ensure_actuator_manual(self) -> bool:
        """Require Connection-tab connect before Manual Control moves."""
        if not self._viewmodel.get_connection_state().get("Actuator"):
            self._viewmodel.status_log_message.emit(
                "Actuator: Not connected — Connection tab: Scan COM, select port, Connect."
            )
            QMessageBox.warning(
                self,
                "Actuator not connected",
                "The actuator is not connected.\n\n"
                "On the Connection tab:\n"
                "• Click Scan COM next to Actuator\n"
                "• Choose your Arduino port\n"
                "• Click Connect\n\n"
                "Then try Move / Home again on Manual Control.",
            )
            return False
        return True

    def _on_actuator_move_a(self):
        """movea <mm> using Distance A spinbox."""
        if not self._ensure_actuator_manual():
            return
        self._viewmodel.actuator_move_a(float(self.actuator_dist_a_spin.value()))

    def _on_actuator_move_a_quick(self):
        """movea at fixed ACTUATOR_DEFAULT_MANUAL_DISTANCE_MM (206 mm), same as terminal test."""
        if not self._ensure_actuator_manual():
            return
        self._viewmodel.actuator_move_a(float(ACTUATOR_DEFAULT_MANUAL_DISTANCE_MM))

    def _on_actuator_home_a(self):
        if not self._ensure_actuator_manual():
            return
        self._viewmodel.actuator_home_a()

    def _on_actuator_move_b(self):
        """moveb <mm> using Distance B spinbox."""
        if not self._ensure_actuator_manual():
            return
        self._viewmodel.actuator_move_b(float(self.actuator_dist_b_spin.value()))

    def _on_actuator_move_b_quick(self):
        """moveb at fixed ACTUATOR_DEFAULT_MANUAL_DISTANCE_MM (206 mm)."""
        if not self._ensure_actuator_manual():
            return
        self._viewmodel.actuator_move_b(float(ACTUATOR_DEFAULT_MANUAL_DISTANCE_MM))

    def _on_actuator_home_b(self):
        if not self._ensure_actuator_manual():
            return
        self._viewmodel.actuator_home_b()

    def _on_actuator_home_both(self):
        if not self._ensure_actuator_manual():
            return
        self._viewmodel.actuator_home_both()

    def _on_prm_set_speed(self):
        state = self._viewmodel.get_connection_state()
        if not state.get("PRM", False):
            QMessageBox.warning(
                self,
                "PRM Not Connected",
                "PRM is not connected.\n\nConnect PRM from the Connection tab: select the PRM serial (click Scan if needed) and click Connect.",
            )
            return
        self._viewmodel.prm_set_velocity(self.prm_speed_spin.value())

    def _set_prm_busy(self, busy: bool, status_hint: Optional[str] = None):
        """Disable/enable PRM Move/Home/Quick/Set during move/home. Stop, IStop stay enabled. status_hint: 'move' or 'home' for status text. Orange while busy, green when Ready."""
        box = self.findChild(QGroupBox, "prm_control_box")
        if box:
            for btn in box.findChildren(QPushButton):
                if btn.objectName() in ("prm_stop_smooth_btn", "prm_stop_immediate_btn"):
                    btn.setEnabled(True)  # Stop, IStop always enabled
                else:
                    btn.setEnabled(not busy)
        if hasattr(self, "prm_status_label"):
            if busy and status_hint == "move":
                self.prm_status_label.setText("Status: Moving...")
                self.prm_status_label.setStyleSheet("color: #ff9800; font-size: 11px;")
            elif busy and status_hint == "home":
                self.prm_status_label.setText("Status: Homing...")
                self.prm_status_label.setStyleSheet("color: #ff9800; font-size: 11px;")
            elif not busy:
                self.prm_status_label.setText("Status: Ready")
                self.prm_status_label.setStyleSheet("color: #4caf50; font-size: 11px;")

    def _on_prm_command_finished(self):
        """Move/home subprocess finished; re-enable PRM buttons."""
        self._set_prm_busy(False)
        if getattr(self, "_home_actuator_b_after_prm_home", False):
            self._home_actuator_b_after_prm_home = False
            try:
                self._viewmodel.actuator_home_b()
            except Exception:
                pass
        if getattr(self, "_close_per_window_after_home", False):
            self._close_per_window_after_home = False
            try:
                w = getattr(self, "_per_test_window", None)
                if w is not None:
                    w.close()
            except Exception:
                pass

    def _on_prm_move(self):
        """Move to the angle entered. Same as Tkinter: set speed from box then move."""
        state = self._viewmodel.get_connection_state()
        if not state.get("PRM", False):
            QMessageBox.warning(
                self,
                "PRM Not Connected",
                "PRM is not connected.\n\nConnect PRM from the Connection tab: select the PRM serial (click Scan if needed) and click Connect.",
            )
            return
        self._set_prm_busy(True, "move")
        self._viewmodel.prm_move_to(float(self.prm_angle_spin.value()), speed_deg_per_sec=self.prm_speed_spin.value())

    def _on_prm_initial_position(self):
        """Go to initial (home) position."""
        state = self._viewmodel.get_connection_state()
        if not state.get("PRM", False):
            QMessageBox.warning(
                self,
                "PRM Not Connected",
                "PRM is not connected.\n\nConnect PRM from the Connection tab: select the PRM serial (click Scan if needed) and click Connect.",
            )
            return
        self._set_prm_busy(True, "home")
        self._viewmodel.prm_home()

    def _on_prm_quick_rotate(self, angle: float):
        """Move to preset angle. Same as Tkinter: set speed then move."""
        state = self._viewmodel.get_connection_state()
        if not state.get("PRM", False):
            QMessageBox.warning(
                self,
                "PRM Not Connected",
                "PRM is not connected.\n\nConnect PRM from the Connection tab: select the PRM serial (click Scan if needed) and click Connect.",
            )
            return
        self.prm_angle_spin.setValue(float(angle))
        self._set_prm_busy(True, "move")
        self._viewmodel.prm_move_to(float(angle), speed_deg_per_sec=self.prm_speed_spin.value())

    def _on_prm_stop_smooth(self):
        """Same as reference: send StopProfiled only, set status, re-enable buttons (no EnableDevice, no delay)."""
        self._viewmodel.prm_stop_smooth()
        self._set_prm_busy(False)
        if hasattr(self, "prm_status_label"):
            self.prm_status_label.setText("Status: Smooth stop sent")
            self.prm_status_label.setStyleSheet("color: #ff9800; font-size: 11px;")

    def _on_prm_stop_immediate(self):
        """Same as reference: send StopImmediate only, set status, re-enable buttons (no EnableDevice, no delay)."""
        self._viewmodel.prm_stop_immediate()
        self._set_prm_busy(False)
        if hasattr(self, "prm_status_label"):
            self.prm_status_label.setText("Status: Immediate stop sent")
            self.prm_status_label.setStyleSheet("color: #f44336; font-size: 11px;")

    def _on_prm_position_updated(self, pos):
        if not hasattr(self, "prm_position_label"):
            return
        if pos is not None:
            self.prm_position_label.setText("Position: {:.3f} °".format(pos))
        else:
            self.prm_position_label.setText("Position: --- °")

    def _on_prm_connection_failed(self, message: str):
        # Normal connection logic: no popup; status already updated and logged by viewmodel.
        pass

    def _on_prm_error(self, message: str):
        """Show PRM error dialog (speed/stop), same as Tkinter messagebox.showerror."""
        if message:
            QMessageBox.warning(self, "PRM", message)

    def _on_actuator_status_line(self, text: str):
        if hasattr(self, "actuator_status_bar") and self.actuator_status_bar:
            self.actuator_status_bar.setText(text)

    def _on_status_log_message(self, message: str):
        if message and hasattr(self, "main_status_log"):
            self.main_status_log.appendPlainText(message)

    @pyqtSlot(str, object)
    def _on_sequence_step_failed(self, test_name: str, reasons: object) -> None:
        """Worker thread reports a failed step before/alongside log lines — fill Reason for Failure directly."""
        if isinstance(reasons, (list, tuple)):
            rs: List[Any] = list(reasons)
        elif reasons is None:
            rs = []
        else:
            rs = [reasons]
        self._append_reason_for_failure_box(test_name, rs, False)

    def _append_reason_for_failure_box(self, test_name: str, reasons: List[Any], passed: bool) -> None:
        """
        Main tab — Reason for Failure: show clear bullet list when a step fails.
        Multiple failed steps in one run are stacked with a separator.
        """
        if passed or not hasattr(self, "main_failure_reason"):
            return
        rs = [str(x).strip() for x in (reasons or []) if x is not None and str(x).strip()]
        lines = [f"{test_name}", ""]
        if rs:
            for x in rs:
                lines.append(f"  • {x}")
        else:
            lines.append("  • (No detailed reason was recorded for this step.)")
        block = "\n".join(lines)
        cur = self.main_failure_reason.toPlainText().strip()
        if cur:
            self.main_failure_reason.setPlainText(cur + "\n\n" + "—" * 28 + "\n\n" + block)
        else:
            self.main_failure_reason.setPlainText(block)

    # ----- Test status and Pass/Fail (READY → Running → Done/Stopped; Pass/Fail when result in) -----
    def _circle_style(self, bg_color, size=120):
        radius = size // 2
        return (
            "background-color: {}; color: white; border-radius: {}px; font-size: 14px; font-weight: bold; "
            "min-width: {}px; max-width: {}px; min-height: {}px; max-height: {}px;"
        ).format(bg_color, radius, size, size, size, size)

    def _set_test_status(self, text, bg_color):
        if not hasattr(self, "main_test_ready_indicator"):
            return
        self.main_test_ready_indicator.setText(text)
        self.main_test_ready_indicator.setStyleSheet(self._circle_style(bg_color))

    def _set_pass_fail(self, text, bg_color):
        if not hasattr(self, "main_pass_fail_indicator"):
            return
        self.main_pass_fail_indicator.setText(text)
        self.main_pass_fail_indicator.setStyleSheet(self._circle_style(bg_color))

    def _clear_part_details_after_pass(self):
        """Clear part no, serial, recipe, wavelength (and recipe tab) after test passes. Operator name unchanged."""
        self.details_recipe.setText("—")
        self.details_serial_no.setText("—")
        self.details_part_no.setText("—")
        self.details_wavelength.setText("—")
        self.details_smsr_on.setText("—")
        self._current_recipe_path = None
        self._current_recipe_data = None
        self._startnew_comments = ""
        self._refresh_recipe_tab()

    def _on_sequence_completed(self, all_passed):
        self._set_test_status("Done", "#4caf50")  # green
        if all_passed:
            self._set_pass_fail("Pass", "#4caf50")
            if hasattr(self, "main_failure_reason"):
                self.main_failure_reason.clear()
            # Auto-clear all Start New details except Operator Name after PASS.
            self._clear_part_details_after_pass()
        else:
            self._set_pass_fail("Fail", "#c62828")  # red
            # If no step wrote specifics (e.g. unimplemented test), show a fallback hint.
            try:
                if hasattr(self, "main_failure_reason") and not self.main_failure_reason.toPlainText().strip():
                    self.main_failure_reason.setPlainText(
                        "Sequence result: FAIL\n\n"
                        "  • No failure details were recorded for this run.\n"
                        "  • Re-run the test; if this message appears again, note which step was active when it failed."
                    )
            except Exception:
                pass
        # On PASS we clear details (except operator); on FAIL keep values for quick retry.
        self._test_sequence_executor = None
        self._test_sequence_thread = None
        self._liv_sequence_bridge = None

    def _on_start_new_clear_requested(self):
        """Start New Clear: clear all details except Operator Name."""
        self._clear_part_details_after_pass()

    def _on_sequence_stopped(self):
        self._set_test_status("STOP", "#c62828")  # red — final state after user stop
        self._set_pass_fail("--", "#555")
        try:
            self._append_reason_for_failure_box(
                "STOP",
                ["Test sequence was stopped by the user before completion."],
                False,
            )
        except Exception:
            pass
        self._test_sequence_executor = None
        self._test_sequence_thread = None
        self._liv_sequence_bridge = None

    def _on_test_sequence_thread_finished(self):
        """Clear thread ref; if UI still shows Stopping..., force final STOP (signal safety net)."""
        self._test_sequence_thread = None
        if not hasattr(self, "main_test_ready_indicator"):
            return
        try:
            txt = (self.main_test_ready_indicator.text() or "").strip()
            if txt in ("Stopping...", "Stopping…"):
                self._set_test_status("STOP", "#c62828")
                self._set_pass_fail("--", "#555")
        except Exception:
            pass

    def _on_connect_fiber_before_liv(self, message: str):
        """Show popup with OK and Cancel when fiber coupled: connect fiber to power meter before LIV."""
        reply = QMessageBox.question(
            self,
            "Fiber Coupled – Connect Fiber",
            message + "\n\nClick OK when fiber is connected to power meter, or Cancel to skip LIV.",
            QMessageBox.Ok | QMessageBox.Cancel,
            QMessageBox.Ok,
        )
        if reply == QMessageBox.Ok and self._test_sequence_executor is not None:
            self._test_sequence_executor.confirm_connect_fiber_before_liv()
        elif reply == QMessageBox.Cancel and self._test_sequence_executor is not None:
            self._test_sequence_executor.cancel_connect_fiber_before_liv()

    def _on_liv_pre_start_prompt(self, message: str, params: dict):
        """Popup during LIV (fault, Thorlabs prompt); OK unblocks worker."""
        QMessageBox.information(self, "LIV", message or "LIV", QMessageBox.Ok)
        if self._test_sequence_executor is not None:
            self._test_sequence_executor.ack_liv_pre_start_prompt()

    def _on_alignment_window_for_liv_sequence(self):
        """LIV opens alignment for Thorlabs path (same as Align + LIV recipe params)."""
        self._on_align_clicked(from_liv_sequence=True)

    def _on_liv_process_window_requested(self, params: dict):
        """Laser is on — open LIV Process on 2nd monitor (recipe left, live plot right). Same for fiber-coupled and not."""
        self._open_liv_test_window(params or {})

    def _open_liv_test_window(self, params: dict):
        """Open LIV window on other monitor: left = RCP/recipe params, right = live graph."""
        ex = self._test_sequence_executor
        prev = getattr(self, "_liv_test_window", None)
        if prev is not None and ex is not None:
            for sig, slot in (
                (ex.liv_plot_clear, prev.clear_plot),
                (ex.liv_plot_update, prev.on_plot_update),
                (ex.liv_power_reading_update, prev.on_power_reading_update),
                (ex.liv_log_message, prev.append_process_log),
                (prev.stop_requested, self._on_stop_clicked),
            ):
                try:
                    sig.disconnect(slot)
                except (TypeError, RuntimeError):
                    pass
            try:
                prev.close()
            except Exception:
                pass
            self._liv_test_window = None
        # Create as top-level window (not child of main) so user can minimize/maximize independently.
        self._liv_test_window = LivTestSequenceWindow(None)
        self._liv_test_window.setWindowFlags(
            self._liv_test_window.windowFlags()
            | QtCompat.Window
            | QtCompat.WindowMinimizeButtonHint
            | QtCompat.WindowMaximizeButtonHint
            | QtCompat.WindowCloseButtonHint
        )
        self._liv_test_window.set_params(params)
        if hasattr(self._liv_test_window, "clear_process_log"):
            self._liv_test_window.clear_process_log()
        self._liv_test_window.setAttribute(QtCompat.WA_DeleteOnClose, True)
        self._liv_test_window.destroyed.connect(self._on_liv_test_window_destroyed)
        if ex is not None:
            _qc = QtCompat.QueuedConnection
            cast(Any, ex.liv_plot_clear).connect(
                self._liv_test_window.clear_plot, _qc
            )
            cast(Any, ex.liv_plot_update).connect(
                self._liv_test_window.on_plot_update, _qc
            )
            cast(Any, ex.liv_power_reading_update).connect(
                self._liv_test_window.on_power_reading_update, _qc
            )
            cast(Any, ex.liv_log_message).connect(
                self._liv_test_window.append_process_log, _qc
            )
            cast(Any, self._liv_test_window.stop_requested).connect(
                self._on_stop_clicked, _qc
            )
        place_on_secondary_screen_before_show(self._liv_test_window, self)
        self._liv_test_window.show()

    def _on_test_window_requested(self, test_name: str, params: dict):
        """When a test (non-LIV) requests a window: open it. LIV uses liv_pre_start_prompt flow instead."""
        if test_name == "LIV":
            return
        if test_name == "PER":
            self._open_per_test_window(params or {})
            return

    def _on_liv_test_window_destroyed(self):
        self._liv_test_window = None

    def _open_per_test_window(self, params: dict):
        ex = self._test_sequence_executor
        prev = getattr(self, "_per_test_window", None)
        if prev is not None and ex is not None:
            for sig, slot in (
                (ex.per_test_result, prev.update_live),
                (ex.per_log_message, prev.append_process_log),
                (prev.stop_requested, self._on_per_window_stop_requested),
            ):
                try:
                    sig.disconnect(slot)
                except (TypeError, RuntimeError):
                    pass
            try:
                prev.close()
            except Exception:
                pass
            self._per_test_window = None
        self._per_test_window = PerTestSequenceWindow(None)
        self._per_test_window.setWindowFlags(
            self._per_test_window.windowFlags()
            | QtCompat.Window
            | QtCompat.WindowMinimizeButtonHint
            | QtCompat.WindowMaximizeButtonHint
            | QtCompat.WindowCloseButtonHint
        )
        self._per_test_window.set_params(params or {})
        if hasattr(self._per_test_window, "clear_process_log"):
            self._per_test_window.clear_process_log()
        self._per_test_window.setAttribute(QtCompat.WA_DeleteOnClose, True)
        self._per_test_window.destroyed.connect(self._on_per_test_window_destroyed)
        if ex is not None:
            _qc = QtCompat.QueuedConnection
            cast(Any, ex.per_test_result).connect(
                self._per_test_window.update_live, _qc
            )
            cast(Any, ex.per_log_message).connect(
                self._per_test_window.append_process_log, _qc
            )
            cast(Any, self._per_test_window.stop_requested).connect(
                self._on_per_window_stop_requested, _qc
            )
        place_on_secondary_screen_before_show(self._per_test_window, self)
        self._per_test_window.show()

    def _on_per_test_window_destroyed(self):
        self._per_test_window = None

    def _on_per_window_stop_requested(self):
        """PER window Stop: stop sequence, immediate PRM stop, then home and close PER window."""
        ex = getattr(self, "_test_sequence_executor", None)
        if ex is not None:
            try:
                cast(Any, ex.per_log_message).emit("STOP: Stop requested from PER window.")
            except Exception:
                pass
        self._set_test_status("Stopping...", "#FF9800")
        if self._test_sequence_executor is not None:
            self._test_sequence_executor.stop()
        try:
            if hasattr(self._viewmodel, "set_arroyo_laser_output"):
                self._viewmodel.set_arroyo_laser_output(False)
        except Exception:
            pass
        try:
            self._viewmodel.prm_stop_immediate()
        except Exception:
            pass
        try:
            self._viewmodel.prm_enable_device()
        except Exception:
            pass
        self._close_per_window_after_home = True
        self._home_actuator_b_after_prm_home = True
        try:
            self._set_prm_busy(True, "home")
        except Exception:
            pass
        try:
            w = getattr(self, "_per_test_window", None)
            if w is not None and hasattr(w, "set_status"):
                w.set_status("Stopping... PRM immediate stop sent. Homing PRM...")
        except Exception:
            pass
        try:
            self._viewmodel.prm_home()
        except Exception:
            self._close_per_window_after_home = False

    def _on_liv_result(self, result):
        """Update LIV tab; close LIV Process window only after all updates are applied."""
        w = getattr(self, "_liv_test_window", None)
        if w is not None:
            ex = self._test_sequence_executor
            if ex is not None:
                try:
                    ex.liv_plot_clear.disconnect(w.clear_plot)
                except Exception:
                    pass
                try:
                    ex.liv_plot_update.disconnect(w.on_plot_update)
                except Exception:
                    pass
                try:
                    ex.liv_power_reading_update.disconnect(w.on_power_reading_update)
                except Exception:
                    pass
                try:
                    w.stop_requested.disconnect(self._on_stop_clicked)
                except Exception:
                    pass
            r_win = getattr(result, "liv_result", None) or result
            try:
                if hasattr(w, "set_liv_results") and r_win is not None:
                    w.set_liv_results(r_win)
            except Exception:
                pass
        r = getattr(result, "liv_result", None)
        if r is None and result is not None:
            if hasattr(result, "passed") or hasattr(result, "current_array") or hasattr(result, "power_array"):
                r = result
        if r is not None:
            try:
                passed_flag = bool(getattr(r, "passed", False))
                reasons = list(getattr(r, "fail_reasons", []) or [])
                if not passed_flag:
                    if reasons:
                        self._on_status_log_message("LIV FAILED:")
                        for rs in reasons:
                            self._on_status_log_message(f"  - {rs}")
                    else:
                        self._on_status_log_message("LIV FAILED: No failure reason provided.")
                    self._append_reason_for_failure_box(
                        "LIV",
                        reasons if reasons else ["LIV did not pass (no fail_reasons on result)."],
                        False,
                    )
            except Exception:
                pass
        if not _PG_AVAILABLE or getattr(self, 'liv_power_curve', None) is None:
            # Even without graph support, close LIV window after processing.
            try:
                if w is not None:
                    w.close()
            except Exception:
                pass
            return
        lp = self.liv_power_curve
        lv = self.liv_voltage_curve
        lpd = self.liv_pd_curve
        if lp is None or lv is None or lpd is None:
            return
        if r is None:
            return
        currents = getattr(r, 'currents', None) or getattr(r, 'current_array', None) or []
        # LIV power graph must use Gentec sweep values (not Thorlabs calibration values).
        powers = (
            getattr(r, 'gentec_powers', None)
            or getattr(r, 'gentec_power_array', None)
            or getattr(r, 'powers', None)
            or getattr(r, 'power_array', None)
            or []
        )
        voltages = getattr(r, 'voltages', None) or getattr(r, 'voltage_array', None) or []
        pd = getattr(r, 'pd_currents', None) or getattr(r, 'pd_array', None) or []
        if currents and powers:
            lp.setData(currents, powers)
        if currents and voltages:
            lv.setData(currents, voltages)
        if currents and pd:
            lpd.setData(currents, pd)
        # Fit secondary axes Y to data (same stacking fix as LIV popup; autoscale after setData).
        try:
            for curve, ys in ((lv, voltages), (lpd, pd)):
                if curve is None or not ys or len(currents) != len(ys):
                    continue
                vb = curve.getViewBox()
                if vb is None:
                    continue
                yf = [float(y) for y in ys]
                lo, hi = min(yf), max(yf)
                span = hi - lo
                pad = max(span * 0.12, 1e-9)
                if span < 1e-12:
                    pad = max(abs(lo) * 0.05, 0.01)
                vb.setYRange(lo - pad, hi + pad, padding=0)
        except Exception:
            pass
        # Plot tab — mirror main LIV plot (same axes / secondary scaling).
        try:
            rlp = getattr(self, "result_liv_power_curve", None)
            rlv = getattr(self, "result_liv_voltage_curve", None)
            rlpd = getattr(self, "result_liv_pd_curve", None)
            if rlp is not None:
                rlp.setData(currents, powers) if currents and powers else rlp.setData([], [])
            if rlv is not None:
                rlv.setData(currents, voltages) if currents and voltages else rlv.setData([], [])
            if rlpd is not None:
                rlpd.setData(currents, pd) if currents and pd else rlpd.setData([], [])
            for curve, ys in ((rlv, voltages), (rlpd, pd)):
                if curve is None or not ys or len(currents) != len(ys):
                    continue
                vb = curve.getViewBox()
                if vb is None:
                    continue
                yf = [float(y) for y in ys]
                lo, hi = min(yf), max(yf)
                span = hi - lo
                pad = max(span * 0.12, 1e-9)
                if span < 1e-12:
                    pad = max(abs(lo) * 0.05, 0.01)
                vb.setYRange(lo - pad, hi + pad, padding=0)
        except Exception:
            pass
        # Mirror curves in LIV -> Calculation tab graph.
        lp2 = getattr(self, "liv_calc_power_curve", None)
        lv2 = getattr(self, "liv_calc_voltage_curve", None)
        lpd2 = getattr(self, "liv_calc_pd_curve", None)
        if lp2 is not None and currents and powers:
            lp2.setData(currents, powers)
        # Calculation graph intentionally shows calculation-relevant power view only.
        # Update LIV-tab calculation panel (below graph)
        p_ir = getattr(r, "power_at_rated_current", None)
        i_pr = getattr(r, "current_at_rated_power", None)
        ith = getattr(r, "threshold_current", None)
        se = getattr(r, "slope_efficiency", None)
        if getattr(self, "liv_calc_power_at_ir", None) is not None:
            self.liv_calc_power_at_ir.setText("—" if p_ir is None else "{:.4f}".format(float(p_ir)))
        if getattr(self, "liv_calc_current_at_pr", None) is not None:
            self.liv_calc_current_at_pr.setText("—" if i_pr is None else "{:.4f}".format(float(i_pr)))
        if getattr(self, "liv_calc_threshold", None) is not None:
            self.liv_calc_threshold.setText("—" if ith is None else "{:.4f}".format(float(ith)))
        if getattr(self, "liv_calc_slope", None) is not None:
            self.liv_calc_slope.setText("—" if se is None else "{:.4f}".format(float(se)))
        try:
            self._apply_plot_tab_liv_results(r)
        except Exception:
            pass
        # Draw calculation overlays on Calculation-tab graph.
        try:
            p_item = getattr(self, "_liv_calc_plot_item", None)
            if p_item is not None and currents and powers:
                for it in getattr(self, "_liv_calc_overlay_items", []) or []:
                    try:
                        p_item.removeItem(it)
                    except Exception:
                        pass
                self._liv_calc_overlay_items = []
                dash = QtCompat.DashLine
                dot = QtCompat.DotLine
                dash_dot = QtCompat.DashDotLine
                ir_m = None
                pr_mw = None
                try:
                    ir_m = float((getattr(self, "_current_recipe_data", {}) or {}).get("OPERATIONS", {}).get("LIV", {}).get("rated_current_mA"))
                except Exception:
                    ir_m = None
                try:
                    pr_mw = float((getattr(self, "_current_recipe_data", {}) or {}).get("OPERATIONS", {}).get("LIV", {}).get("rated_power_mW"))
                except Exception:
                    pr_mw = None
                if ith is not None and float(ith) > 0:
                    ln = PG.InfiniteLine(pos=float(ith), angle=90, pen=PG.mkPen("#000000", width=2, style=dash))
                    p_item.addItem(ln)
                    self._liv_calc_overlay_items.append(ln)
                if ir_m is not None and min(currents) <= ir_m <= max(currents):
                    ln2 = PG.InfiniteLine(pos=float(ir_m), angle=90, pen=PG.mkPen("#000000", width=2, style=dot))
                    p_item.addItem(ln2)
                    self._liv_calc_overlay_items.append(ln2)
                if pr_mw is not None and pr_mw > 0:
                    hl = PG.InfiniteLine(pos=float(pr_mw), angle=0, pen=PG.mkPen("#000000", width=2, style=dash_dot))
                    p_item.addItem(hl)
                    self._liv_calc_overlay_items.append(hl)
                if ir_m is not None and p_ir is not None:
                    sc = PG.ScatterPlotItem([float(ir_m)], [float(p_ir)], size=12, pen=PG.mkPen("#000000", width=2),
                                            brush=PG.mkBrush(0, 0, 0, 220), symbol="star")
                    p_item.addItem(sc)
                    self._liv_calc_overlay_items.append(sc)
                if pr_mw is not None and i_pr is not None:
                    sc2 = PG.ScatterPlotItem([float(i_pr)], [float(pr_mw)], size=10, pen=PG.mkPen("#000000", width=2),
                                             brush=PG.mkBrush(0, 0, 0, 220), symbol="d")
                    p_item.addItem(sc2)
                    self._liv_calc_overlay_items.append(sc2)
        except Exception:
            pass
        # Close LIV process window only after all graph + calculation updates are done.
        try:
            if w is not None:
                w.close()
        except Exception:
            pass

    def _on_per_result(self, result, angles, powers_mw):
        """PER window gets every live sample via its own slot; Main PER tab updates only on the final result."""
        is_final = bool(getattr(result, "is_final", False)) if result is not None else False
        if is_final:
            ppc = getattr(self, "per_power_curve", None)
            if _PG_AVAILABLE and ppc is not None:
                if angles and powers_mw:
                    pw = list(powers_mw)
                    ang = list(angles)
                    n = min(len(ang), len(pw))
                    y_dbm = mw_series_to_dbm(pw[:n])
                    ppc.setData(ang[:n], y_dbm)
                    rppc = getattr(self, "result_per_power_curve", None)
                    if rppc is not None:
                        rppc.setData(ang[:n], y_dbm)
                else:
                    ppc.setData([], [])
                    rppc = getattr(self, "result_per_power_curve", None)
                    if rppc is not None:
                        rppc.setData([], [])
            if result is not None and hasattr(self, "per_result_max_power"):
                self._apply_per_result_values(result)
        try:
            if result is not None and is_final:
                if not bool(getattr(result, "passed", True)):
                    fr = list(getattr(result, "fail_reasons", []) or [])
                    self._append_reason_for_failure_box(
                        "PER",
                        fr if fr else ["PER did not pass (no fail_reasons on result)."],
                        False,
                    )
        except Exception:
            pass
        # After final curve + results are on the Main PER tab, close the live PER window.
        try:
            if is_final:
                w = getattr(self, "_per_test_window", None)
                if w is not None:
                    w.close()
        except Exception:
            pass

    def _reset_spectrum_plot_axis_labels(self) -> None:
        """Default axis titles before/after a run (Spectrum tab)."""
        tc = getattr(self, "_spectrum_axis_text_color", PYQTGRAPH_AXIS_TEXT)
        bottom = getattr(self, "_spectrum_axis_bottom_default", "Wavelength (nm)")
        left = getattr(self, "_spectrum_axis_left_default", "Level (dBm)")
        sp = getattr(self, "spectrum_os_plot", None)
        if sp is not None:
            pi = cast(Any, sp.getPlotItem())
            pi.setTitle("Ando sweep — LVL (dBm)", color=tc)
            pi.setLabel("bottom", bottom, color=tc)
            pi.setLabel("left", left, color=tc)
        spf = getattr(self, "spectrum_first_os_plot", None)
        if spf is not None:
            pif = cast(Any, spf.getPlotItem())
            pif.setTitle("First sweep — LVL (dBm)", color=tc)
            pif.setLabel("bottom", bottom, color=tc)
            pif.setLabel("left", left, color=tc)

    @staticmethod
    def _spectrum_peak_wavelength_from_trace(w: List[float], l: List[float]) -> Optional[float]:
        if not w or not l or len(w) != len(l):
            return None
        try:
            i = max(range(len(l)), key=lambda j: float(l[j]))
            return float(w[i])
        except Exception:
            return None

    @staticmethod
    def _spectrum_x_aligned_to_wavemeter(
        wdata: List[float], ldata: List[float], peak_ando_nm: Optional[float], wavemeter_nm: Optional[float]
    ) -> List[float]:
        """
        Same Ando LDATA vs shifted WDATA: rigid X shift so trace peak sits at wavemeter reading.
        If wavemeter or peak is missing, returns original WDATA.
        """
        if not wdata or not ldata or len(wdata) != len(ldata):
            return []
        if wavemeter_nm is None or peak_ando_nm is None:
            return list(wdata)
        try:
            delta = float(wavemeter_nm) - float(peak_ando_nm)
            return [float(x) + delta for x in wdata]
        except Exception:
            return list(wdata)

    def _spectrum_apply_viewbox_axes_main_tab(self, vb: Any, result: Any, wm: Optional[float], ldata: List[float]) -> None:
        """X: wavemeter ± span/2 when aligned; else CTR ± span/2 from result. Y: Ando REFL / LSCL (log) or trace padding."""
        span_nm = float(getattr(result, "span_nm", 0.0) or 0.0)
        ref = float(getattr(result, "ref_level_dbm", -10.0))
        ls = float(getattr(result, "level_scale_db_per_div", 10.0))
        center = float(getattr(result, "center_nm", 0.0) or 0.0)
        if wm is not None and span_nm > 0:
            vb.setXRange(float(wm) - span_nm / 2.0, float(wm) + span_nm / 2.0, padding=0.02)
        elif _spectrum_plot_x_range_nm is not None and center > 0 and span_nm > 0:
            x0, x1 = _spectrum_plot_x_range_nm(center, span_nm)
            vb.setXRange(x0, x1, padding=0.02)
        else:
            vb.autoRange()
        if _spectrum_plot_y_range_dbm is not None:
            yr = _spectrum_plot_y_range_dbm(ref, ls)
            if yr is not None:
                vb.setYRange(yr[0], yr[1], padding=0.02)
                return
        if ldata:
            lo = min(float(x) for x in ldata)
            hi = max(float(x) for x in ldata)
            pad = max(0.5, (hi - lo) * 0.1)
            vb.setYRange(lo - pad, hi + pad, padding=0.02)

    def _on_spectrum_result(self, result):
        """Update Spectrum tab: First sweep sub-tab = first WDATA/LDATA; primary sub-tab = second sweep only."""
        if not _PG_AVAILABLE:
            return
        curve = getattr(self, "spectrum_os_curve", None)
        if curve is None and not getattr(self, "_graph_tabs_installed", False):
            self._deferred_install_graph_tabs()
            curve = getattr(self, "spectrum_os_curve", None)
        if curve is None:
            return
        passed = bool(getattr(result, "passed", False))
        fail_reasons = list(getattr(result, "fail_reasons", None) or [])
        detail = "; ".join(str(x) for x in fail_reasons) if fail_reasons else ""

        def _pair(raw_w: Any, raw_l: Any) -> Tuple[List[float], List[float]]:
            if _spectrum_pair_trace_floats is not None:
                pw, pl = _spectrum_pair_trace_floats(raw_w, raw_l)
                return list(pw or []), list(pl or [])
            w = list(raw_w or [])
            l = list(raw_l or [])
            n = min(len(w), len(l))
            return w[:n], l[:n]

        w2, l2 = _pair(getattr(result, "second_sweep_wdata", None), getattr(result, "second_sweep_ldata", None))
        use_second = len(w2) > 0 and len(l2) > 0
        span_nm = float(getattr(result, "span_nm", 0.0) or 0.0)

        if use_second:
            wm = getattr(result, "second_wavemeter_nm", None)
            if wm is None:
                wm = getattr(result, "wavemeter_nm_for_axis_label", None)
            peak_ando = getattr(result, "peak_wavelength_second_nm", None)
            if peak_ando is None:
                peak_ando = getattr(result, "peak_wavelength", None)
            if peak_ando is None and len(w2) > 0:
                peak_ando = self._spectrum_peak_wavelength_from_trace(w2, l2)
        else:
            wm = getattr(result, "first_wavemeter_nm", None)
            if wm is None:
                wm = getattr(result, "wavemeter_nm_for_axis_label", None)
            peak_ando = None

        if hasattr(self, "spectrum_wavemeter_reading") and self.spectrum_wavemeter_reading is not None:
            if use_second:
                wm_disp = getattr(result, "second_wavemeter_nm", None)
                if wm_disp is None:
                    wm_disp = getattr(result, "wavemeter_nm_for_axis_label", None)
                self.spectrum_wavemeter_reading.setText("{:.6f}".format(float(wm_disp)) if wm_disp is not None else "—")
            else:
                self.spectrum_wavemeter_reading.setText("—")

        if use_second:
            x_plot = self._spectrum_x_aligned_to_wavemeter(w2, l2, peak_ando, wm)
            curve.setData(x_plot, l2)
            try:
                sp = getattr(self, "spectrum_os_plot", None)
                if sp is not None:
                    pi = cast(Any, sp.getPlotItem())
                    tc = getattr(self, "_spectrum_axis_text_color", PYQTGRAPH_AXIS_TEXT)
                    pi.setTitle(
                        "Ando — Second sweep · LVL (dBm)",
                        color=tc,
                    )
                    pi.setLabel("left", "Level (dBm)", color=tc)
                    if wm is not None:
                        pi.setLabel(
                            "bottom",
                            "Wavelength (nm) — wavemeter {:.4f} nm · span {:.3f} nm".format(float(wm), span_nm),
                            color=tc,
                        )
                    else:
                        pi.setLabel(
                            "bottom",
                            "Wavelength (nm) — span {:.3f} nm · Ando CTR {:.4f} nm".format(
                                span_nm,
                                float(getattr(result, "center_nm", 0.0) or 0.0),
                            ),
                            color=tc,
                        )
                    vb = cast(Any, sp).getPlotItem().getViewBox()
                    self._spectrum_apply_viewbox_axes_main_tab(vb, result, wm, l2)
            except Exception:
                pass
            try:
                rc = getattr(self, "result_spectrum_os_curve", None)
                rsp = getattr(self, "result_spectrum_os_plot", None)
                if rc is not None:
                    rc.setData(x_plot, l2)
                if rsp is not None:
                    pi_r = cast(Any, rsp.getPlotItem())
                    tc_r = getattr(self, "_spectrum_axis_text_color", "#333333")
                    pi_r.setTitle("Ando — Second sweep · LVL (dBm)", color=tc_r)
                    pi_r.setLabel("left", "Level (dBm)", color=tc_r)
                    if wm is not None:
                        pi_r.setLabel(
                            "bottom",
                            "Wavelength (nm) — wavemeter {:.4f} nm · span {:.3f} nm".format(float(wm), span_nm),
                            color=tc_r,
                        )
                    else:
                        pi_r.setLabel(
                            "bottom",
                            "Wavelength (nm) — span {:.3f} nm · Ando CTR {:.4f} nm".format(
                                span_nm,
                                float(getattr(result, "center_nm", 0.0) or 0.0),
                            ),
                            color=tc_r,
                        )
                    vb_r = cast(Any, rsp).getPlotItem().getViewBox()
                    self._spectrum_apply_viewbox_axes_main_tab(vb_r, result, wm, l2)
            except Exception:
                pass
        else:
            curve.setData([], [])
            try:
                rc = getattr(self, "result_spectrum_os_curve", None)
                if rc is not None:
                    rc.setData([], [])
            except Exception:
                pass
            try:
                self._reset_spectrum_plot_axis_labels()
            except Exception:
                pass

        first_curve = getattr(self, "spectrum_first_os_curve", None)
        if first_curve is not None:
            w1, l1 = _pair(getattr(result, "first_sweep_wdata", None), getattr(result, "first_sweep_ldata", None))
            if len(w1) > 0 and len(l1) > 0:
                wm1 = getattr(result, "first_wavemeter_nm", None)
                peak1 = getattr(result, "peak_wavelength_first_nm", None)
                if peak1 is None:
                    peak1 = self._spectrum_peak_wavelength_from_trace(w1, l1)
                x1 = self._spectrum_x_aligned_to_wavemeter(w1, l1, peak1, wm1)
                first_curve.setData(x1, l1)
                try:
                    spf = getattr(self, "spectrum_first_os_plot", None)
                    if spf is not None:
                        pif = cast(Any, spf.getPlotItem())
                        tc = getattr(self, "_spectrum_axis_text_color", PYQTGRAPH_AXIS_TEXT)
                        pif.setTitle("Ando — First sweep · LVL (dBm)", color=tc)
                        pif.setLabel("left", "Level (dBm)", color=tc)
                        if wm1 is not None:
                            pif.setLabel(
                                "bottom",
                                "Wavelength (nm) — wavemeter {:.4f} nm · span {:.3f} nm".format(float(wm1), span_nm),
                                color=tc,
                            )
                        else:
                            pif.setLabel(
                                "bottom",
                                "Wavelength (nm) — span {:.3f} nm · Ando CTR {:.4f} nm".format(
                                    span_nm,
                                    float(getattr(result, "center_nm", 0.0) or 0.0),
                                ),
                                color=tc,
                            )
                        vbf = cast(Any, spf).getPlotItem().getViewBox()
                        self._spectrum_apply_viewbox_axes_main_tab(vbf, result, wm1, l1)
                except Exception:
                    pass
            else:
                first_curve.setData([], [])

        self._spectrum_update_first_sweep_result_panel(result)

        finalize = bool(getattr(result, "spectrum_finalize_secondary_window", True))
        if finalize:
            pk = getattr(result, "peak_wavelength", None)
            pdb = getattr(result, "peak_level_dbm", None)
            fwhm = getattr(result, "fwhm", None)
            smsr = getattr(result, "smsr", None)
            if hasattr(self, "spectrum_peak_wl") and self.spectrum_peak_wl is not None:
                self.spectrum_peak_wl.setText("{:.6f}".format(float(pk)) if pk is not None else "—")
            if hasattr(self, "spectrum_peak_dbm") and self.spectrum_peak_dbm is not None:
                self.spectrum_peak_dbm.setText("{:.3f}".format(float(pdb)) if pdb is not None else "—")
            if hasattr(self, "spectrum_fwhm") and self.spectrum_fwhm is not None:
                self.spectrum_fwhm.setText("{:.6f}".format(float(fwhm)) if fwhm is not None else "—")
            if hasattr(self, "spectrum_smsr") and self.spectrum_smsr is not None:
                self.spectrum_smsr.setText("{:.2f}".format(float(smsr)) if smsr is not None else "—")
            if hasattr(self, "spectrum_pass_label") and self.spectrum_pass_label is not None:
                if passed:
                    self.spectrum_pass_label.setText("PASS")
                    self.spectrum_pass_label.setStyleSheet("color: #81c784; font-size: 12px; font-weight: bold;")
                else:
                    self.spectrum_pass_label.setText("FAIL")
                    self.spectrum_pass_label.setStyleSheet("color: #ef9a9a; font-size: 12px; font-weight: bold;")

            try:
                sw = getattr(self, "_spectrum_test_window", None)
                if sw is not None and hasattr(sw, "set_finished"):
                    sw.set_finished(passed, detail if not passed else "")
            except Exception:
                pass
            try:
                QTimer.singleShot(600, self._close_spectrum_test_window)
            except Exception:
                pass

        self._last_spectrum_result = result

    def _spectrum_update_first_sweep_result_panel(self, result: Any) -> None:
        if getattr(self, "spectrum_first_wavemeter_reading", None) is None:
            return
        w1 = list(getattr(result, "first_sweep_wdata", None) or [])
        l1 = list(getattr(result, "first_sweep_ldata", None) or [])
        has_first = len(w1) > 0 and len(l1) > 0
        wm1 = getattr(result, "first_wavemeter_nm", None)
        self.spectrum_first_wavemeter_reading.setText("{:.6f}".format(float(wm1)) if wm1 is not None else "—")
        pk1 = getattr(result, "peak_wavelength_first_nm", None)
        self.spectrum_first_peak_wl.setText("{:.6f}".format(float(pk1)) if pk1 is not None else "—")
        pl1 = getattr(result, "peak_level_first_dbm", None)
        self.spectrum_first_peak_dbm.setText("{:.3f}".format(float(pl1)) if pl1 is not None else "—")
        fh1 = getattr(result, "fwhm_first_nm", None)
        self.spectrum_first_fwhm.setText("{:.6f}".format(float(fh1)) if fh1 is not None else "—")
        sm1 = getattr(result, "smsr_first_db", None)
        self.spectrum_first_smsr.setText("{:.2f}".format(float(sm1)) if sm1 is not None else "—")
        pf = bool(getattr(result, "passed_first_sweep", False))
        lbl = self.spectrum_first_pass_label
        if not has_first and pk1 is None:
            lbl.setText("—")
            lbl.setStyleSheet("color: #e6e6e6; font-size: 12px;")
        else:
            if pf:
                lbl.setText("PASS")
                lbl.setStyleSheet("color: #81c784; font-size: 12px; font-weight: bold;")
            else:
                lbl.setText("FAIL")
                lbl.setStyleSheet("color: #ef9a9a; font-size: 12px; font-weight: bold;")

    def _save_first_sweep_results_only(self) -> None:
        r = getattr(self, "_last_spectrum_result", None)
        if r is None:
            QMessageBox.information(self, "Spectrum", "No spectrum result to save.")
            return
        w1 = list(getattr(r, "first_sweep_wdata", None) or [])
        l1 = list(getattr(r, "first_sweep_ldata", None) or [])
        if not w1 and not l1 and getattr(r, "peak_wavelength_first_nm", None) is None:
            QMessageBox.information(self, "Spectrum", "No first sweep data available yet.")
            return
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save first sweep results",
            "",
            "JSON (*.json);;All files (*)",
        )
        if not path:
            return
        if not path.lower().endswith(".json"):
            path = path + ".json"
        payload = {
            "first_wavemeter_nm": getattr(r, "first_wavemeter_nm", None),
            "peak_wavelength_first_nm": getattr(r, "peak_wavelength_first_nm", None),
            "peak_level_first_dbm": getattr(r, "peak_level_first_dbm", None),
            "fwhm_first_nm": getattr(r, "fwhm_first_nm", None),
            "smsr_first_db": getattr(r, "smsr_first_db", None),
            "passed_first_sweep": getattr(r, "passed_first_sweep", None),
            "first_sweep_wdata": w1,
            "first_sweep_ldata": l1,
        }
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2)
        except OSError as ex:
            QMessageBox.warning(self, "Save failed", str(ex))
            return
        QMessageBox.information(self, "Spectrum", "First sweep results saved.")

    def _close_spectrum_test_window(self) -> None:
        w = getattr(self, "_spectrum_test_window", None)
        if w is None:
            return
        try:
            w.close()
        except Exception:
            pass

    def _on_spectrum_test_window_destroyed(self):
        ex = getattr(self, "_test_sequence_executor", None)
        w = getattr(self, "_spectrum_test_window", None)
        if ex is not None and w is not None:
            try:
                cast(Any, ex.spectrum_log_message).disconnect(w.append_process_log)
            except Exception:
                pass
        self._spectrum_test_window = None
        self._disconnect_spectrum_live_signals()

    def _disconnect_spectrum_live_signals(self) -> None:
        ex = getattr(self, "_test_sequence_executor", None)
        if ex is None:
            return
        for name in ("spectrum_live_trace", "spectrum_wavemeter_reading", "spectrum_step_status"):
            sig = getattr(ex, name, None)
            if sig is None:
                continue
            try:
                sig.disconnect()
            except Exception:
                pass

    @pyqtSlot()
    def blocking_open_spectrum_test_window(self):
        """Open Spectrum window from the test worker via BlockingQueuedConnection before spec.run() (avoids live-plot race)."""
        ex = getattr(self, "_test_sequence_executor", None)
        params: dict = {}
        if ex is not None:
            params = getattr(ex, "_spectrum_window_params_pending", None) or {}
        self._open_spectrum_test_window(params)

    def _open_spectrum_test_window(self, params: dict):
        """Open Spectrum step window on the secondary monitor (same pattern as PER)."""
        ex = self._test_sequence_executor
        prev = getattr(self, "_spectrum_test_window", None)
        if prev is not None:
            try:
                prev.close()
            except Exception:
                pass
            self._spectrum_test_window = None
        self._spectrum_test_window = SpectrumTestSequenceWindow(None)
        self._spectrum_test_window.setWindowFlags(
            self._spectrum_test_window.windowFlags()
            | QtCompat.Window
            | QtCompat.WindowMinimizeButtonHint
            | QtCompat.WindowMaximizeButtonHint
            | QtCompat.WindowCloseButtonHint
        )
        self._spectrum_test_window.set_params(params or {})
        if hasattr(self._spectrum_test_window, "clear_live_plot"):
            self._spectrum_test_window.clear_live_plot()
        if hasattr(self._spectrum_test_window, "clear_process_log"):
            self._spectrum_test_window.clear_process_log()
        self._spectrum_test_window.setAttribute(QtCompat.WA_DeleteOnClose, True)
        self._spectrum_test_window.destroyed.connect(self._on_spectrum_test_window_destroyed)
        _qc = QtCompat.QueuedConnection
        cast(Any, self._spectrum_test_window.stop_requested).connect(self._on_stop_clicked, _qc)
        ex = getattr(self, "_test_sequence_executor", None)
        if ex is not None:
            try:
                cast(Any, ex.spectrum_live_trace).connect(self._spectrum_test_window.set_live_trace, _qc)
                cast(Any, ex.spectrum_wavemeter_reading).connect(
                    self._spectrum_test_window.set_wavemeter_reading, _qc
                )
                if hasattr(self._spectrum_test_window, "set_status"):
                    cast(Any, ex.spectrum_step_status).connect(self._spectrum_test_window.set_status, _qc)
                if hasattr(self._spectrum_test_window, "append_process_log"):
                    cast(Any, ex.spectrum_log_message).connect(
                        self._spectrum_test_window.append_process_log, _qc
                    )
                    cast(Any, ex.spectrum_step_status).connect(
                        self._spectrum_test_window.append_process_log, _qc
                    )
            except Exception:
                pass
        place_on_secondary_screen_before_show(self._spectrum_test_window, self)
        self._spectrum_test_window.show()

    @pyqtSlot()
    def blocking_open_stability_test_window(self):
        """Open Temperature Stability window from worker before process.run() (live plot + log signals)."""
        ex = getattr(self, "_test_sequence_executor", None)
        params: dict = {}
        if ex is not None:
            params = getattr(ex, "_stability_window_params_pending", None) or {}
        self._open_stability_test_window(params)

    def _open_stability_test_window(self, params: dict):
        ex = getattr(self, "_test_sequence_executor", None)
        prev = getattr(self, "_stability_test_window", None)
        if prev is not None:
            try:
                prev.close()
            except Exception:
                pass
            self._stability_test_window = None
        self._stability_test_window = TemperatureStabilityWindow(None)
        self._stability_test_window.setWindowFlags(
            self._stability_test_window.windowFlags()
            | QtCompat.Window
            | QtCompat.WindowMinimizeButtonHint
            | QtCompat.WindowMaximizeButtonHint
            | QtCompat.WindowCloseButtonHint
        )
        slot = int((params or {}).get("slot", 1))
        self._stability_test_window.set_window_title_slot(slot)
        self._stability_test_window.set_params(params or {})
        if hasattr(self._stability_test_window, "clear_plots"):
            self._stability_test_window.clear_plots()
        if hasattr(self._stability_test_window, "clear_process_log"):
            self._stability_test_window.clear_process_log()
        self._stability_test_window.setAttribute(QtCompat.WA_DeleteOnClose, True)
        self._stability_test_window.destroyed.connect(self._on_stability_test_window_destroyed)
        _qc = QtCompat.QueuedConnection
        cast(Any, self._stability_test_window.stop_requested).connect(self._on_stop_clicked, _qc)
        if ex is not None:
            try:
                cast(Any, ex.stability_live_point).connect(self._stability_test_window.append_live_point, _qc)
                cast(Any, ex.stability_log_message).connect(self._stability_test_window.append_process_log, _qc)
            except Exception:
                pass
        place_on_secondary_screen_before_show(self._stability_test_window, self)
        self._stability_test_window.show()

    def _on_stability_test_window_destroyed(self):
        ex = getattr(self, "_test_sequence_executor", None)
        w = getattr(self, "_stability_test_window", None)
        if ex is not None and w is not None:
            try:
                cast(Any, ex.stability_live_point).disconnect(w.append_live_point)
            except Exception:
                pass
            try:
                cast(Any, ex.stability_log_message).disconnect(w.append_process_log)
            except Exception:
                pass
        self._stability_test_window = None

    def _apply_stability_result_to_main_tab(self, slot: int, result: Any) -> None:
        if not _PG_AVAILABLE:
            return
        curves = self._stability_ts1_curves if int(slot) == 1 else self._stability_ts2_curves
        if not curves or len(curves) < 4:
            if not getattr(self, "_graph_tabs_installed", False):
                self._deferred_install_graph_tabs()
            curves = self._stability_ts1_curves if int(slot) == 1 else self._stability_ts2_curves
        if not curves or len(curves) < 4:
            return
        tx = list(getattr(result, "temperature_c", []) or [])
        fy = list(getattr(result, "fwhm_nm", []) or [])
        sy = list(getattr(result, "smsr_db", []) or [])
        py = list(getattr(result, "peak_wavelength_nm", []) or [])
        lv = list(getattr(result, "peak_level_dbm", []) or [])
        try:
            curves[0].setData(tx, py)
            curves[1].setData(tx, fy)
            curves[2].setData(tx, sy)
            curves[3].setData(tx, lv)
        except Exception:
            pass
        try:
            self._autorange_stability_combined(curves, tx, py, fy, sy, lv)
        except Exception:
            pass
        r_curves = getattr(self, "result_ts1_curves", []) if int(slot) == 1 else getattr(self, "result_ts2_curves", [])
        if len(r_curves) >= 4:
            try:
                r_curves[0].setData(tx, py)
                r_curves[1].setData(tx, fy)
                r_curves[2].setData(tx, sy)
                r_curves[3].setData(tx, lv)
                self._autorange_stability_combined(r_curves, tx, py, fy, sy, lv)
            except Exception:
                pass

    def _on_stability_test_result(self, result: Any) -> None:
        self._apply_stability_result_to_main_tab(getattr(result, "slot", 1), result)
        w = getattr(self, "_stability_test_window", None)
        if w is not None:
            try:
                w.close()
            except Exception:
                pass

    @staticmethod
    def _coerce_test_sequence(raw: Any) -> List[str]:
        if raw is None:
            return []
        if isinstance(raw, list):
            return [str(x) for x in raw]
        if isinstance(raw, str):
            return [raw] if raw.strip() else []
        if isinstance(raw, dict):
            return [str(v) for v in raw.values()]
        return [str(raw)]

    def _on_run_clicked(self):
        recipe = getattr(self, "_current_recipe_data", None)
        if not recipe or not isinstance(recipe, dict):
            QMessageBox.information(self, "Run", "Load a recipe first (Start New → select recipe → Start Test).")
            return
        raw_seq = (
            recipe.get("TEST_SEQUENCE")
            or recipe.get("TestSequence")
            or (recipe.get("GENERAL") or {}).get("TestSequence")
            or (recipe.get("GENERAL") or {}).get("TEST_SEQUENCE")
        )
        seq = self._coerce_test_sequence(raw_seq)
        if not seq:
            QMessageBox.information(self, "Run", "Recipe has no test sequence.")
            return
        # PyQtGraph tabs are normally installed after first paint. If Run starts before that,
        # spectrum_os_curve (etc.) is still None and spectrum_test_result cannot draw on the main tab.
        if not getattr(self, "_graph_tabs_installed", False):
            self._deferred_install_graph_tabs()
        self._set_test_status("Running", "#2196F3")  # blue
        self._set_pass_fail("--", "#555")  # keep gray until result
        if hasattr(self, "main_failure_reason"):
            self.main_failure_reason.clear()
        try:
            from operations.test_sequence_executor import TestSequenceExecutor, TestSequenceThread
            from viewmodel.sequence_instrument_bridge import SequenceInstrumentBridge

            bridge = SequenceInstrumentBridge(self._viewmodel)
            self._liv_sequence_bridge = bridge
            self._test_sequence_executor = TestSequenceExecutor(self)
            self._test_sequence_executor.set_test_sequence(seq, recipe)
            self._test_sequence_executor.set_sequence_bridge(bridge)
            self._test_sequence_executor.log_message.connect(self._on_status_log_message)
            if hasattr(self._viewmodel, "_instrument_manager") and self._viewmodel._instrument_manager is not None:
                self._test_sequence_executor.set_instrument_manager(self._viewmodel._instrument_manager)
            self._test_sequence_thread = TestSequenceThread(self._test_sequence_executor)
            _qthread = cast(Any, self._test_sequence_thread)
            _qthread.sequence_completed.connect(
                self._on_sequence_completed, QtCompat.QueuedConnection
            )
            _qthread.sequence_stopped.connect(
                self._on_sequence_stopped, QtCompat.QueuedConnection
            )
            _qthread.finished.connect(self._on_test_sequence_thread_finished)
            self._test_sequence_executor.liv_test_result.connect(self._on_liv_result)
            self._test_sequence_executor.per_test_result.connect(self._on_per_result)
            cast(Any, self._test_sequence_executor.sequence_step_failed).connect(
                self._on_sequence_step_failed, QtCompat.QueuedConnection
            )
            _qc = QtCompat.QueuedConnection
            cast(Any, self._test_sequence_executor.spectrum_test_result).connect(
                self._on_spectrum_result, _qc
            )
            self._test_sequence_executor.test_window_requested.connect(self._on_test_window_requested)
            # LIV window now opens from liv_process_window_requested (after laser is ON).
            # Pre-LIV fiber popup is handled via connect_fiber_before_liv_requested only.
            self._test_sequence_executor.liv_process_window_requested.connect(
                self._on_liv_process_window_requested
            )
            self._test_sequence_executor.connect_fiber_before_liv_requested.connect(self._on_connect_fiber_before_liv)
            cast(Any, self._test_sequence_executor.liv_pre_start_prompt_requested).connect(
                self._on_liv_pre_start_prompt, _qc
            )
            cast(Any, self._test_sequence_executor.alignment_window_requested).connect(
                self._on_alignment_window_for_liv_sequence, _qc
            )
            cast(Any, self._test_sequence_executor.per_process_window_requested).connect(
                self._open_per_test_window, _qc
            )
            cast(Any, self._test_sequence_executor.spectrum_process_window_requested).connect(
                self._open_spectrum_test_window, _qc
            )
            cast(Any, self._test_sequence_executor.stability_test_result).connect(
                self._on_stability_test_result, _qc
            )
            self._clear_all_result_graphs()
            self._test_sequence_thread.start()
        except Exception as e:
            self._set_test_status("READY", "#555")
            self._set_pass_fail("--", "#555")
            QMessageBox.warning(self, "Run", "Could not start test sequence: {}".format(e))

    @pyqtSlot()
    def pausePollingForLiv(self):
        """Called from LIV worker thread via QMetaObject.invokeMethod so timers are stopped on main thread."""
        b = getattr(self, "_liv_sequence_bridge", None)
        if b is not None and hasattr(b, "pause_for_liv") and callable(b.pause_for_liv):
            b.pause_for_liv()

    @pyqtSlot()
    def resumePollingAfterLiv(self):
        """Called from LIV worker thread via QMetaObject.invokeMethod so timers are started on main thread."""
        b = getattr(self, "_liv_sequence_bridge", None)
        if b is not None and hasattr(b, "resume_after_liv") and callable(b.resume_after_liv):
            b.resume_after_liv()
        if hasattr(self._viewmodel, "schedule_arroyo_readback_refresh"):
            self._viewmodel.schedule_arroyo_readback_refresh()
        elif hasattr(self._viewmodel, "refresh_arroyo_readings"):
            self._viewmodel.refresh_arroyo_readings()
            QTimer.singleShot(250, self._viewmodel.refresh_arroyo_readings)

    def _on_stop_clicked(self):
        # Safety: always force laser OFF when user presses Stop.
        try:
            if hasattr(self._viewmodel, "set_arroyo_laser_output"):
                self._viewmodel.set_arroyo_laser_output(False)
        except Exception:
            pass
        if self._test_sequence_executor is not None:
            self._on_status_log_message(
                "STOP: Stop requested — current step will exit, then sequence aborts."
            )
            self._set_test_status("Stopping...", "#FF9800")
            self._test_sequence_executor.stop()
        else:
            self._on_status_log_message("STOP: Stop pressed (no test sequence running; laser off if connected).")
        # Close active run windows immediately on any stop request.
        try:
            w = getattr(self, "_liv_test_window", None)
            if w is not None and w.isVisible():
                w.close()
        except Exception:
            pass
        try:
            pw = getattr(self, "_per_test_window", None)
            if pw is not None and pw.isVisible():
                pw.close()
        except Exception:
            pass
        try:
            aw = getattr(self, "_alignment_window", None)
            if aw is not None and aw.isVisible():
                aw.close()
        except Exception:
            pass
        try:
            sw = getattr(self, "_spectrum_test_window", None)
            if sw is not None and sw.isVisible():
                sw.close()
        except Exception:
            pass
        try:
            stw = getattr(self, "_stability_test_window", None)
            if stw is not None and stw.isVisible():
                stw.close()
        except Exception:
            pass

    def _on_start_new_clicked(self):
        dialog = TestInformationDialog(self)
        dialog.clear_requested.connect(self._on_start_new_clear_requested)
        dialog.recipe_path_changed.connect(self._on_start_new_recipe_selection_changed)
        # Pre-fill with current details so user sees existing data (persist until test done or Clear)
        op = (self.details_op_name.text() or "").strip()
        if op == "—":
            op = ""
        serial = (self.details_serial_no.text() or "").strip()
        if serial == "—":
            serial = ""
        part = (self.details_part_no.text() or "").strip()
        if part == "—":
            part = ""
        wl = (self.details_wavelength.text() or "").strip()
        if wl == "—":
            wl = ""
        recipe_path = getattr(self, "_current_recipe_path", None) or ""
        comments = getattr(self, "_startnew_comments", "") or ""
        dialog.set_initial_values(op_name=op, serial_no=serial, part_no=part, comments=comments, recipe_path=recipe_path, wavelength=wl)
        if dialog.exec_() == QDialog.Accepted:
            # Operator name: update from dialog so it persists; only changes when user edits in Start New and Start Test, or when GUI closes
            self.details_op_name.setText(dialog.get_operator_name() or "—")
            # Serial, part, comments, recipe, wavelength: update from dialog when user presses Start Test
            recipe_path = dialog.get_recipe_path() or ""
            self.details_recipe.setText(self._recipe_display_name(recipe_path))
            self.details_serial_no.setText(dialog.get_serial_no() or "—")
            self.details_part_no.setText(dialog.get_part_no() or "—")
            self.details_wavelength.setText(dialog.get_wavelength() or "—")
            self.details_smsr_on.setText("—")
            self._startnew_comments = dialog.get_comments() or ""
            # Recipe tab: always mirror the path chosen here — reload from disk so resaved files show up.
            if recipe_path:
                try:
                    data = self._load_recipe_file(recipe_path)
                    if data:
                        self._current_recipe_data = data
                        self._current_recipe_path = recipe_path
                    else:
                        self._current_recipe_data = None
                        self._current_recipe_path = None
                        QMessageBox.warning(
                            self,
                            "Recipe",
                            "Could not read or parse the recipe file:\n{}".format(recipe_path),
                        )
                except Exception as e:
                    self._current_recipe_data = None
                    self._current_recipe_path = None
                    QMessageBox.warning(
                        self,
                        "Recipe",
                        "Could not load recipe:\n{}\n\n{}".format(recipe_path, e),
                    )
            else:
                self._current_recipe_data = None
                self._current_recipe_path = None
            self._refresh_recipe_tab()
            data = getattr(self, "_current_recipe_data", None)
            if isinstance(data, dict):
                try:
                    self._apply_wavemeter_range_from_recipe(data)
                except Exception:
                    pass
                try:
                    ops = data.get("OPERATIONS") or {}
                    wm = (data.get("spec") or {}).get("WAVEMETER") or ops.get("WAVEMETER") or data.get("WAVEMETER") or {}
                    if isinstance(wm, dict):
                        self.details_smsr_on.setText("Yes" if wm.get("smsr") else "No")
                    else:
                        self.details_smsr_on.setText("—")
                except Exception:
                    pass

    def _on_new_recipe_clicked(self):
        """Open the full Recipe window on a different monitor, maximized. Independent minimize/restore; closes when main closes."""
        self._recipe_window = RecipeWindow()
        self._recipe_window.recipe_saved.connect(self._on_recipe_saved_from_editor)
        # Same title-bar hints as LIV/PER/Spectrum so minimize / maximize / close show on Windows.
        self._recipe_window.setWindowFlags(
            self._recipe_window.windowFlags()
            | QtCompat.Window
            | QtCompat.WindowMinimizeButtonHint
            | QtCompat.WindowMaximizeButtonHint
            | QtCompat.WindowCloseButtonHint
        )
        self._recipe_window.setAttribute(QtCompat.WA_DeleteOnClose, True)
        self._recipe_window.destroyed.connect(self._on_recipe_window_destroyed)
        place_on_secondary_screen_before_show(self._recipe_window, self, maximize=True)
        self._recipe_window.show()

    def _on_recipe_window_destroyed(self):
        """Clear reference when user closes the Recipe window."""
        self._recipe_window = None

    def _get_recipe_wavelength_for_align(self):
        """Get wavelength from current recipe for alignment window. Returns value or None if no recipe."""
        data = getattr(self, "_current_recipe_data", None)
        if data and isinstance(data, dict):
            wl = data.get("wavelength")
            if wl is None:
                g = data.get("GENERAL") or data.get("General")
                if isinstance(g, dict):
                    wl = g.get("wavelength") or g.get("Wavelength")
            if wl is None and isinstance(data.get("LIV"), dict):
                wl = data["LIV"].get("wavelength") or data["LIV"].get("Wavelength")
            if wl is not None:
                try:
                    return float(wl)
                except (TypeError, ValueError):
                    pass
        txt = (self.details_wavelength.text() or "").strip()
        if txt and txt != "—":
            try:
                return float(txt)
            except (TypeError, ValueError):
                pass
        return None

    def _on_align_clicked(self, from_liv_sequence: bool = False):
        """Open Alignment window: Align tab (Laser + Ando in one row) and Settings tab. Proper window, not vertical."""
        align_existing = getattr(self, "_alignment_window", None)
        if align_existing is not None and align_existing.isVisible():
            align_existing.raise_()
            align_existing.activateWindow()
            align_existing.set_wavelength_from_recipe(self._get_recipe_wavelength_for_align())
            liv_params = self._test_sequence_executor.get_liv_alignment_params() if self._test_sequence_executor else None
            if liv_params is not None and len(liv_params) == 3:
                align_existing.set_liv_recipe_params(liv_params[0], liv_params[1], liv_params[2])
            if self._last_arroyo_readings:
                align_existing.update_laser_details(self._last_arroyo_readings)
            if hasattr(self._viewmodel, "refresh_arroyo_readings"):
                self._viewmodel.refresh_arroyo_readings()
            if from_liv_sequence and hasattr(align_existing, "start_liv_alignment_auto"):
                QTimer.singleShot(120, align_existing.start_liv_alignment_auto)
            return
        self._alignment_window = AlignmentWindow(self)
        self._alignment_window.setWindowFlags(self._alignment_window.windowFlags() | QtCompat.Window)
        self._alignment_window.setAttribute(QtCompat.WA_DeleteOnClose, True)
        self._alignment_window.destroyed.connect(self._on_alignment_window_destroyed)
        if self._test_sequence_executor is not None:
            _qc = QtCompat.QueuedConnection
            cast(Any, self._alignment_window.alignment_confirmed).connect(
                self._test_sequence_executor.continue_after_alignment, _qc
            )
            cast(Any, self._alignment_window.alignment_cancelled).connect(
                self._test_sequence_executor.alignment_cancelled, _qc
            )
        self._alignment_window.set_wavelength_from_recipe(self._get_recipe_wavelength_for_align())
        # Apply LIV recipe params (min current → Set current, temperature → Set temperature, max current → Max current) if available
        liv_params = self._test_sequence_executor.get_liv_alignment_params() if self._test_sequence_executor else None
        if liv_params is not None and len(liv_params) == 3:
            self._alignment_window.set_liv_recipe_params(liv_params[0], liv_params[1], liv_params[2])
        if self._last_arroyo_readings:
            self._alignment_window.update_laser_details(self._last_arroyo_readings)
        if hasattr(self._viewmodel, "refresh_arroyo_readings"):
            self._viewmodel.refresh_arroyo_readings()
        place_on_secondary_screen_before_show(self._alignment_window, self)
        self._alignment_window.show()
        if from_liv_sequence and hasattr(self._alignment_window, "start_liv_alignment_auto"):
            QTimer.singleShot(120, self._alignment_window.start_liv_alignment_auto)

    def _on_alignment_window_destroyed(self):
        """Clear reference when user closes the Alignment window."""
        self._alignment_window = None

    def _on_file_exit(self) -> None:
        """File → Exit. Wraps close() because QWidget.close() returns bool (not a valid PYQT_SLOT)."""
        self.close()

    def _on_about(self):
        QMessageBox.about(
            self,
            "About Butterfly Tester",
            "Butterfly Tester\n\nMVVM structure with PyQt5.",
        )

    def closeEvent(self, event):
        # When main GUI closes, close every secondary window we own (not only if currently visible — e.g. minimized).
        rw = getattr(self, "_recipe_window", None)
        if rw is not None:
            rw.close()
            self._recipe_window = None
        aw_close = getattr(self, "_alignment_window", None)
        if aw_close is not None:
            aw_close.close()
            self._alignment_window = None
        liv_w = getattr(self, "_liv_test_window", None)
        if liv_w is not None:
            liv_w.close()
            self._liv_test_window = None
        per_w = getattr(self, "_per_test_window", None)
        if per_w is not None:
            per_w.close()
            self._per_test_window = None
        sp_w = getattr(self, "_spectrum_test_window", None)
        if sp_w is not None:
            sp_w.close()
            self._spectrum_test_window = None
        st_w = getattr(self, "_stability_test_window", None)
        if st_w is not None:
            st_w.close()
            self._stability_test_window = None
        # Flush closes so WA_DeleteOnClose widgets are gone before instrument shutdown.
        for _ in range(5):
            QApplication.processEvents()
        # Safety shutdown: always request Arroyo laser OFF + TEC OFF before worker disconnect.
        try:
            if hasattr(self._viewmodel, "set_arroyo_laser_output"):
                self._viewmodel.set_arroyo_laser_output(False)
            if hasattr(self._viewmodel, "set_arroyo_tec_output"):
                self._viewmodel.set_arroyo_tec_output(False)
            # Let queued worker commands flush before shutdown/disconnect.
            for _ in range(3):
                QApplication.processEvents()
                time.sleep(0.06)
        except Exception:
            pass
        if hasattr(self._viewmodel, "shutdown"):
            self._viewmodel.shutdown()
        event.accept()
