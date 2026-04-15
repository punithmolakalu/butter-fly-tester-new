"""Main window: View only. Binds to ViewModel."""
from typing import Any, Dict, List, Optional, Tuple, cast
import math
import threading
import os
import re

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
    QSplitter,
    QStackedWidget,
)
from PyQt5.QtCore import Qt, QTimer, QObject, QSize, pyqtSignal, pyqtSlot, QEvent
from PyQt5.QtGui import QPalette, QColor, QFont, QShowEvent, QDoubleValidator, QResizeEvent, QCursor, QFocusEvent

# PyQt5 stubs omit many Qt namespace members; cast keeps strict checkers quiet.
QtCompat: Any = cast(Any, Qt)
QEventCompat: Any = cast(Any, QEvent)


class _PlotTabGraphEnlargeFilter(QObject):
    """Double-click on Plot tab pyqtgraph canvas: toggle full-window enlarge.

    Must be installed on the **viewport** of the QGraphicsView (PlotWidget),
    not on the PlotWidget itself — Qt delivers mouse events to the viewport
    widget, so an event filter on the parent QGraphicsView never sees them.
    Returning True here also prevents pyqtgraph's ViewBox.mouseDoubleClickEvent
    (autoRange) from firing.
    """

    def __init__(self, main_window: Any, plot_key: str, dialog_title: str) -> None:
        super().__init__(main_window)
        self._mw = main_window
        self._plot_key = plot_key
        self._dialog_title = dialog_title
        self._handling = False

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # type: ignore[override]
        if event.type() == QEventCompat.MouseButtonDblClick:
            if self._handling:
                return True
            self._handling = True
            try:
                self._mw._toggle_plot_tab_graph_enlarge(self._plot_key, self._dialog_title)
            finally:
                self._handling = False
            return True
        return False


try:
    import pyqtgraph as _pyqtgraph_mod
    _PG_AVAILABLE = True
except ImportError:
    _PG_AVAILABLE = False
    _pyqtgraph_mod = None
# When graphs are disabled, code paths return early; treat as Any for attribute access.
PG: Any = cast(Any, _pyqtgraph_mod)

try:
    from view.natural_tab_bar import NaturalWidthTabBar  # noqa: E402
except ImportError:
    from PyQt5.QtGui import QFont, QFontMetrics
    from PyQt5.QtWidgets import QApplication, QTabBar

    class NaturalWidthTabBar(QTabBar):
        """Fallback if view/natural_tab_bar.py is missing (unsynced copy). Tabs size to label text."""

        def tabSizeHint(self, index: int) -> QSize:
            hint = super().tabSizeHint(index)
            text = self.tabText(index)
            if not text:
                return hint
            s = 1.0
            app = QApplication.instance()
            if app is not None:
                v = app.property("ui_scale")
                if v is not None:
                    try:
                        s = float(v)
                    except (TypeError, ValueError):
                        s = 1.0
            s = max(0.75, min(1.25, s))
            font_px = max(9, int(round(13 * s)))
            f = QFont(self.font())
            f.setPixelSize(font_px)
            fm = QFontMetrics(f)
            tw = fm.horizontalAdvance(text) if hasattr(fm, "horizontalAdvance") else fm.width(text)
            try:
                tw = max(int(tw), int(fm.boundingRect(text).width()))
            except Exception:
                pass
            horizontal_extra = 64
            w = max(hint.width(), tw + horizontal_extra)
            h = max(hint.height(), fm.height() + 8)
            return QSize(w, h)

        def minimumSizeHint(self):
            sz = super().minimumSizeHint()
            total = sum(self.tabSizeHint(i).width() for i in range(self.count()))
            if total > 0:
                return QSize(total, sz.height())
            return sz

from view.dark_theme import (  # noqa: E402
    COLOR_GREEN,
    COLOR_GREEN_HOVER,
    COLOR_ORANGE,
    COLOR_ORANGE_HOVER,
    COLOR_RED,
    COLOR_RED_HOVER,
    ThemeTokens,
    apply_application_theme,
    get_dark_palette,
    get_light_palette,
    is_dark_theme_saved,
    main_stylesheet,
    qpushbutton_local_style,
    qpushbutton_local_style_neutral,
    scaled_px,
    set_dark_theme_saved,
    set_dark_title_bar,
    spinbox_arrow_styles,
    spinbox_arrow_styles_for_theme,
    theme_actuator_status_bar_qss,
    theme_ando_stop_idle_qss,
    theme_chrome_bg,
    theme_console_plaintext_qss,
    theme_engineer_btn_off_qss,
    theme_engineer_combo_ando_qss,
    theme_engineer_groupbox_qss,
    theme_engineer_lineedit_ando_qss,
    theme_engineer_spin_qss,
    theme_failure_outer_qss,
    theme_failure_plaintext_qss,
    theme_main_tab_gentec_mult_spin_qss,
    theme_manual_read_wavelength_btn_qss,
    theme_metric_caption_style,
    theme_metric_field_style,
    theme_pass_fail_chip_style,
    theme_pass_fail_name_style,
    theme_prm_stop_grey_qss,
    theme_qframe_form_panel_qss,
    theme_qgroupbox_plot_surround_qss,
    theme_tests_pass_chip_fail,
    theme_tests_pass_chip_pass,
    theme_tokens,
    theme_wavemeter_big_value_qss,
)
from start.startnew_dialog import TestInformationDialog  # noqa: E402
from start.recipe_window import RecipeWindow  # noqa: E402
from start.recipe_readonly_view import RecipeReadonlyView  # noqa: E402
from start.window_placement import place_on_secondary_screen_before_show  # noqa: E402
from view.instrument_info_thread import GatherInstrumentInfoThread  # noqa: E402
from view.alignment_window import AlignmentWindow  # noqa: E402
from view.liv_process_plot import (  # noqa: E402
    apply_liv_phase4_overlays,
    build_liv_process_plot,
    clear_liv_analysis_overlays,
    liv_autorange_secondary_axes,
    recipe_params_for_liv_overlays,
)
from view.liv_test_window import LivTestSequenceWindow  # noqa: E402
from view.plot_series_checkboxes import (  # noqa: E402
    PER_SERIES_COLORS,
    PER_SERIES_LABELS,
    freeze_plot_navigation,
    make_series_checkbox_row,
)
from view.per_test_window import PerTestSequenceWindow  # noqa: E402
from view.spectrum_test_window import SpectrumTestSequenceWindow  # noqa: E402
from view.temperature_stability_plot import (  # noqa: E402
    build_stability_tab_plot,
    compact_simple_xy_plot_axes,
    stability_smsr_y_for_plot,
    stability_tab_apply_result,
    stability_tab_clear_plot,
)
from view.temperature_stability_window import TemperatureStabilityWindow  # noqa: E402
from instruments.actuator import ACTUATOR_DEFAULT_MANUAL_DISTANCE_MM  # noqa: E402
from instruments.thorlabs_powermeter import (  # noqa: E402
    THORLABS_GUI_MULT_MAX,
    THORLABS_GUI_MULT_MIN,
    format_power_mw_display,
    format_thorlabs_power_mw_display,
    thorlabs_power_display_unit,
)
from operations.per.per_units import mw_series_to_dbm, mw_to_dbm  # noqa: E402
from operations.result_saver import _stem_for_sequence_step  # noqa: E402

try:
    from operations.spectrum.trace_plotting import pair_trace_floats as _spectrum_pair_trace_floats  # noqa: E402
    from operations.spectrum.trace_plotting import spectrum_plot_x_range_nm as _spectrum_plot_x_range_nm  # noqa: E402
    from operations.spectrum.trace_plotting import spectrum_plot_y_range_dbm as _spectrum_plot_y_range_dbm  # noqa: E402
    from operations.spectrum.trace_plotting import (  # noqa: E402
        spectrum_wavemeter_bottom_axis_label as _spectrum_wm_bottom_axis_label,
    )
except ImportError:
    _spectrum_pair_trace_floats = None
    _spectrum_plot_x_range_nm = None
    _spectrum_plot_y_range_dbm = None
    _spectrum_wm_bottom_axis_label = None


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


def _thorlabs_visa_combo_fallback_list(visa_list):
    """
    Thorlabs powermeters are USB (VID 0x1313) or serial — not GPIB. When the Thorlabs-specific
    USB scan finds nothing, we may fall back to a full VISA list; exclude GPIB resources so
    wavemeter / Ando GPIB addresses cannot be selected by mistake for Thorlabs.
    """
    out = []
    for r in visa_list or []:
        s = (r or "").strip()
        if not s:
            continue
        if "GPIB" in s.upper():
            continue
        out.append(s)
    return out


# Main tab "Test" / "Result" circles — 1.5× original 88px side (132px)
_MAIN_TAB_STATUS_CIRCLE_PX = 132

# Gentec must open after PRM (Kinesis) + Thorlabs (VISA/USB) + Arroyo have started settling — opening the Gentec COM
# too early often hits "access denied" while other devices still hold serial/VISA; actuator stagger stays after Gentec.
_CONNECT_ALL_GENTEC_DELAY_MS = 1200
_CONNECT_ALL_ACTUATOR_DELAY_MS = 4000

# Startup auto-connect: Windows USB-serial is often not ready the instant the process starts.
_STARTUP_AUTO_CONNECT_DELAY_MS = 900
# Stagger wavemeter after Ando on the same PC (shared GPIB adapter / VISA startup).
# Manual disconnect/reconnect working is a strong sign of early-start timing/race; use longer startup delay.
_CONNECT_ALL_WAVEMETER_AFTER_ANDO_MS = 1500
_STARTUP_WAVEMETER_AFTER_ANDO_MS = 2500
# After the first Connect All, re-try anything still disconnected (workers finish async; hubs wake slowly).
_STARTUP_SERIAL_RETRY_1_AFTER_FIRST_MS = 6500
_STARTUP_SERIAL_RETRY_2_AFTER_FIRST_MS = 13500


def _connect_all_prm_will_connect(serial_number: str) -> bool:
    s = (serial_number or "").strip()
    if not s or s.startswith("(no "):
        return False
    return "no devices" not in s.lower()


def _com_combo_text_is_usable_port(text: str) -> bool:
    """True if Connection-tab COM combo text is a real port name (not a scan placeholder)."""
    t = (text or "").strip()
    if not t:
        return False
    if t in ("(no ports found)", "(loading COM list…)"):
        return False
    return True


def _strip_saved_tag(text: str) -> str:
    """Remove the ' (saved)' suffix appended by scan-restore when the address wasn't detected."""
    t = (text or "").strip()
    if t.endswith(" (saved)"):
        t = t[: -len(" (saved)")].strip()
    return t


def _normalize_user_com_port(text: str) -> str:
    """Strip whitespace and surrounding quotes; pass any COMn / \\\\.\\COMn the user typed or saved."""
    p = (text or "").strip()
    if len(p) >= 2 and ((p[0] == p[-1] == '"') or (p[0] == p[-1] == "'")):
        p = p[1:-1].strip()
    return p


def _connect_all_gentec_actuator_delays_ms(defer_prm_ms: int, prm_serial: str) -> tuple:
    """Return (gentec_delay_ms, actuator_delay_ms). Extend Gentec delay when PRM connects (immediate or deferred)."""
    g0 = _CONNECT_ALL_GENTEC_DELAY_MS
    a0 = _CONNECT_ALL_ACTUATOR_DELAY_MS
    if not _connect_all_prm_will_connect(prm_serial):
        return (g0, a0)
    d = int(defer_prm_ms)
    if d > 0:
        g = max(g0, d + 1300)
    else:
        # PRM + Thorlabs + VISA at t=0 — shared USB/serial stack often busy until ~2.4s
        g = max(g0, 2600)
    a = max(a0, g + 2400)
    return (g, a)


def _main_tab_status_circle_stylesheet(bg_color: str, size: int, font_px: int = 15) -> str:
    radius = size // 2
    return (
        "background-color: {}; color: white; border-radius: {}px; font-size: {}px; font-weight: bold; "
        "min-width: {}px; max-width: {}px; min-height: {}px; max-height: {}px;"
    ).format(bg_color, radius, font_px, size, size, size, size)


class _InitialConnectionScanBridge(QObject):
    """Delivers initial COM/GPIB/VISA scan results from a worker thread to the GUI thread."""

    done = pyqtSignal(object)


class _ConnectionScanBridge(QObject):
    """User-triggered Connection tab scans: work runs off the GUI thread; results queued here."""

    finished = pyqtSignal(dict)


class _FullWidthTabWidget(QTabWidget):
    """Top-level tabs: natural width each (not stretched); scroll arrows if many tabs / narrow window; full text, no elide."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDocumentMode(True)
        tb = NaturalWidthTabBar(self)
        tb.setExpanding(False)
        tb.setUsesScrollButtons(True)
        tb.setElideMode(Qt.ElideNone)  # type: ignore[attr-defined]
        self.setTabBar(tb)
        try:
            tb.setDrawBase(False)
        except Exception:
            pass
        self.currentChanged.connect(self._stack_flush_under_tab_bar)

    def showEvent(self, event: QShowEvent):
        super().showEvent(event)
        QTimer.singleShot(0, self._stack_flush_under_tab_bar)

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        self._stack_flush_under_tab_bar()
        QTimer.singleShot(0, self._stack_flush_under_tab_bar)

    def _stack_flush_under_tab_bar(self, *_args: Any) -> None:
        """
        Remove the default gap between the tab bar and the page stack.

        Qt's Fusion style positions QStackedWidget with internal layout; QSS on QTabWidget::pane
        (e.g. margin-top) does not move that layout, so stylesheet-only fixes have no effect.
        """
        stack = self.findChild(QStackedWidget)
        tb = self.tabBar()
        if stack is None or tb is None:
            return
        try:
            g = stack.geometry()
            # Flush to tab bar bottom (no extra pixel gap before stacked page content).
            top = int(tb.geometry().bottom())
            h = max(0, int(self.height()) - top)
            stack.setGeometry(int(g.x()), top, int(g.width()), h)
        except Exception:
            pass


class MainWindow(QMainWindow):
    def _tt(self) -> ThemeTokens:
        return theme_tokens(bool(getattr(self, "_dark_theme_enabled", True)))

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
        # Responsive text: scale factor from window width (updated in resizeEvent).
        self._ui_scale = 1.0
        self._ui_scale_timer = QTimer(self)
        self._ui_scale_timer.setSingleShot(True)
        self._ui_scale_timer.setInterval(90)
        self._ui_scale_timer.timeout.connect(self._apply_ui_scale_from_resize)
        self._instrument_info_gather_thread = None
        self.setWindowTitle("Butterfly Tester")
        self.setMinimumSize(720, 480)
        self.resize(1024, 700)
        self._dark_theme_enabled = is_dark_theme_saved()
        # Apply theme before any child widgets exist so nothing is created with the default white Fusion look.
        self.setPalette(get_dark_palette() if self._dark_theme_enabled else get_light_palette())
        try:
            _app0 = QApplication.instance()
            if _app0 is not None:
                _app0.setProperty("ui_scale", 1.0)
        except Exception:
            pass
        self.setStyleSheet(main_stylesheet(1.0, self._dark_theme_enabled))
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
        _chrom = theme_chrome_bg(self._dark_theme_enabled)
        pal = QPalette()
        pal.setColor(QPalette.Window, QColor(_chrom))
        central.setPalette(pal)
        central.setStyleSheet("background-color: {};".format(_chrom))
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._build_menu_bar()
        self._initial_scan_bridge = _InitialConnectionScanBridge(self)
        self._initial_scan_bridge.done.connect(self._on_initial_connection_scan_done)
        self._connection_scan_bridge = _ConnectionScanBridge(self)
        self._connection_scan_bridge.finished.connect(self._on_connection_scan_worker_finished)
        self._connection_scan_busy = False
        self._connection_scan_lock_widgets: List[QWidget] = []
        self.tabs = _FullWidthTabWidget()
        self.tabs.setObjectName("mainTabs")
        self.tabs.setStyleSheet(self._main_tabs_stylesheet())
        self.tabs.addTab(self._make_main_tab(), "Main")
        self.tabs.addTab(self._make_engineer_control_tab(), "Engineer Control")
        self.tabs.addTab(self._make_recipe_tab(), "Recipe")
        self.tabs.addTab(self._make_summary_tab(), "Summary")
        self.tabs.addTab(self._make_plot_tab(), "Plot")
        self.tabs.addTab(self._make_result_tab(), "Result")
        try:
            self._rebuild_result_tab_graph_layout(None)
        except Exception:
            pass
        # Fusion + QTabWidget: internal stack can paint default light background before child styles apply.
        _stack = self.tabs.findChild(QStackedWidget)
        if _stack is not None:
            _stack.setAutoFillBackground(True)
            _sp = QPalette()
            _sp.setColor(QPalette.Window, QColor(_chrom))
            _stack.setPalette(_sp)
            _stack.setStyleSheet(
                "QStackedWidget {{ margin: 0px; padding: 0px; border: none; background-color: {}; }}".format(_chrom)
            )
            try:
                _stack.setContentsMargins(0, 0, 0, 0)
            except Exception:
                pass
        self._last_arroyo_readings: Optional[dict] = None  # re-apply when switching tabs so all tabs stay in sync
        self.tabs.currentChanged.connect(self._on_tabs_current_changed)
        _tb = self.tabs.tabBar()
        if _tb is not None:
            _tb.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
            _tb.setExpanding(False)
            _tb.setUsesScrollButtons(True)
            _tb.setElideMode(Qt.ElideNone)  # type: ignore[attr-defined]
            _tb.tabBarClicked.connect(self._on_main_tab_bar_clicked)
        self.tabs.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.tabs, 1)

        self._build_footer()
        layout.addWidget(self.footer_frame, 0)

        self._viewmodel.connection_state_changed.connect(self._on_connection_state_changed)
        self._viewmodel.arroyo_readings_updated.connect(self._on_arroyo_readings_updated)
        self._viewmodel.gentec_reading_updated.connect(self._on_gentec_reading_updated)
        self._viewmodel.thorlabs_reading_updated.connect(self._on_thorlabs_reading_updated)
        self._viewmodel.thorlabs_wavelength_nm_read.connect(self._on_manual_thorlabs_wavelength_read)
        self._viewmodel.wavemeter_wavelength_updated.connect(self._on_wavemeter_wavelength_updated)
        self._viewmodel.wavemeter_range_applied.connect(self._on_wavemeter_range_applied)
        self._viewmodel.prm_position_updated.connect(self._on_prm_position_updated)
        self._viewmodel.prm_connection_failed.connect(self._on_prm_connection_failed)
        self._viewmodel.prm_error.connect(self._on_prm_error)
        self._viewmodel.prm_command_finished.connect(self._on_prm_command_finished)
        self._viewmodel.status_log_message.connect(self._on_status_log_message)
        self._viewmodel.actuator_status_line.connect(self._on_actuator_status_line)
        self._viewmodel.ando_sweep_status_updated.connect(self._on_ando_sweep_status_from_instrument)
        self._refresh_footer(self._viewmodel.get_connection_state())

        self.main_start_new_btn.clicked.connect(self._on_start_new_clicked)
        self.main_new_recipe_btn.clicked.connect(self._on_new_recipe_clicked)
        self.main_run_btn.clicked.connect(self._on_run_clicked)
        self.main_stop_btn.clicked.connect(self._on_stop_clicked)
        self.main_align_btn.clicked.connect(self._on_align_clicked)
        # Test status: READY until Run; then Running (blue); then Done (green) or Stopped (red). Result circle: last step while running, overall at end.
        self._test_sequence_executor = None
        self._test_sequence_thread = None
        # True while operator should not start another sequence from the main tab; cleared on Stop request and on thread finished.
        self._main_tab_sequence_ui_locked = False
        self._tests_pass_fail_rows: List[Dict[str, Any]] = []
        self._recipe_window = None  # keep reference so New Recipe window is not garbage-collected
        self._alignment_window = None  # keep reference so Alignment window is not garbage-collected
        self._liv_test_window = None  # LIV test sequence live window (other monitor)
        self._per_test_window = None  # PER test sequence live window (other monitor)
        self._spectrum_test_window = None  # Spectrum test step window (other monitor)
        self._stability_test_window = None  # Temperature Stability 1/2 live window (other monitor)
        self._close_per_window_after_home = False
        self._home_actuator_b_after_prm_home = False
        # PER Stop: turn laser off after PRM home + actuator home (not before).
        self._per_stop_deferred_laser_off = False

        self._arroyo_laser_on = False
        self._arroyo_tec_on = False
        self._prm_manual_busy = False
        self._ando_sweep_running = False

        self.per_result_max_power = self.per_result_min_power = self.per_result_per = self.per_result_angle = None
        self._last_spectrum_result = None
        self._last_liv_result: Optional[Any] = None
        self._last_per_result: Optional[Any] = None
        self._last_stability_results: Dict[int, Any] = {}
        self._liv_annot_overlay_items: List[Any] = []
        self._plot_tab_liv_live_i: List[float] = []
        self._plot_tab_liv_live_p: List[float] = []
        self._plot_tab_liv_live_v: List[float] = []
        self._plot_tab_liv_live_pd: List[float] = []

        try:
            self._reapply_main_tab_fonts()
            self._reapply_engineer_tab_fonts()
            self._reapply_footer_fonts()
        except Exception:
            pass

        # One-click select full value for all spinboxes and value line edits; units (suffix) stay visible
        _app = QApplication.instance()
        if _app is not None:
            _app.installEventFilter(self)

    def _complete_heavy_startup(self) -> None:
        """After first window paint: lazy Recipe read-only view, then connection setup (main.py calls after processEvents)."""
        if getattr(self, "_heavy_startup_done", False):
            return
        self._heavy_startup_done = True
        self._ensure_recipe_readonly_view()
        # Was previously in Connection tab __init__ — moved here so the window/layout can paint first.
        self._apply_saved_addresses_and_auto_connect()
        self._run_startup_auto_connect()

    def eventFilter(self, obj, event):
        """On focus: select full value so one click selects complete number; unit/suffix unchanged."""
        try:
            if isinstance(event, QFocusEvent) and event.gotFocus():
                if isinstance(obj, (QDoubleSpinBox, QSpinBox)):
                    obj.selectAll()
                elif isinstance(obj, QLineEdit) and not obj.isReadOnly():
                    obj.selectAll()
        except Exception:
            pass
        return super(MainWindow, self).eventFilter(obj, event)

    def showEvent(self, event: QShowEvent):
        super(MainWindow, self).showEvent(event)
        try:
            set_dark_title_bar(int(self.winId()), bool(getattr(self, "_dark_theme_enabled", True)))
        except Exception:
            pass
        # If window was not opened via main.py (no _heavy_startup_scheduled_from_main), defer heavy work here.
        if not getattr(self, "_heavy_startup_scheduled_from_main", False) and not getattr(self, "_heavy_startup_done", False):
            QTimer.singleShot(0, self._complete_heavy_startup)
        if not getattr(self, "_ui_scale_bootstrapped", False):
            self._ui_scale_bootstrapped = True
            QTimer.singleShot(0, self._apply_ui_scale_from_resize)

    def _run_startup_auto_connect(self) -> None:
        """Run after deferred startup: Connect All from saved addresses after USB has time to enumerate; then timed retries."""
        saved = getattr(self, "_pending_startup_auto_connect", None)
        self._pending_startup_auto_connect = None
        if not isinstance(saved, dict) or saved.get("auto_connect", "1") != "1":
            return
        ms = int(_STARTUP_AUTO_CONNECT_DELAY_MS)
        QTimer.singleShot(ms, lambda s=dict(saved): self._startup_auto_connect_execute(s))

    def _startup_auto_connect_execute(self, saved: dict) -> None:
        """First auto-connect pass; retries are scheduled inside _on_connect_all from the same address snapshot."""
        if not isinstance(saved, dict):
            return
        self._on_connect_all(
            use_saved=dict(saved),
            wavemeter_delay_ms=int(_STARTUP_WAVEMETER_AFTER_ANDO_MS),
            defer_prm_ms=350,
        )

    def _connection_addresses_from_combos(self) -> dict:
        """Current Connection-tab selections (same shape as load_saved_addresses / Save)."""
        return {
            "arroyo_port": _strip_saved_tag(self.available_ports_combo.currentText()),
            "actuator_port": _strip_saved_tag(self.actuator_ports_combo.currentText()),
            "ando_gpib": _strip_saved_tag(self.available_gpib_combo.currentText()),
            "wavemeter_gpib": _strip_saved_tag(self.wavemeter_gpib_combo.currentText()),
            "prm_serial": _strip_saved_tag(self.prm_serial_combo.currentText()),
            "gentec_port": _strip_saved_tag(self.gentec_ports_combo.currentText()),
            "thorlabs_visa": _strip_saved_tag(self.thorlabs_visa_combo.currentText()),
            "auto_connect": "1",
        }

    def _schedule_post_connect_retries(self) -> None:
        """After Connect All, re-try anything still offline using _last_connect_all_addresses (INI or combos)."""
        QTimer.singleShot(
            int(_STARTUP_SERIAL_RETRY_1_AFTER_FIRST_MS),
            lambda: self._retry_instruments_if_disconnected(attempt=1),
        )
        QTimer.singleShot(
            int(_STARTUP_SERIAL_RETRY_2_AFTER_FIRST_MS),
            lambda: self._retry_instruments_if_disconnected(attempt=2),
        )

    def _retry_instruments_if_disconnected(self, attempt: int) -> None:
        """
        Re-connect instruments that are still disconnected using the address set from the last Connect All
        (saved instrument_config.ini or current combo values), plus a fallback load from disk if needed.
        """
        saved = getattr(self, "_last_connect_all_addresses", None)
        if not isinstance(saved, dict):
            try:
                saved = self._viewmodel.load_saved_addresses()
            except Exception:
                return
        if not isinstance(saved, dict) or not self._saved_ini_has_any_connection(saved):
            return
        st = self._viewmodel.get_connection_state()
        prm_sn = (saved.get("prm_serial") or "").strip()
        g_delay, a_delay = _connect_all_gentec_actuator_delays_ms(350, prm_sn)
        parts = []

        try:
            self._viewmodel.scan_ports()
        except Exception:
            pass

        ap = _normalize_user_com_port((saved.get("arroyo_port") or "").strip())
        acp = _normalize_user_com_port((saved.get("actuator_port") or "").strip())
        same_ra = (
            ap
            and acp
            and self._com_port_key_ui(ap) == self._com_port_key_ui(acp)
        )

        if ap and _com_combo_text_is_usable_port(ap) and not st.get("Arroyo"):
            self._viewmodel.connect_arroyo(ap)
            parts.append("Arroyo")

        gp = _normalize_user_com_port((saved.get("gentec_port") or "").strip())
        if gp and _com_combo_text_is_usable_port(gp) and not st.get("Gentec"):
            QTimer.singleShot(g_delay, lambda p=gp: self._viewmodel.connect_gentec(p))
            parts.append("Gentec")

        if (
            acp
            and _com_combo_text_is_usable_port(acp)
            and not st.get("Actuator")
            and not same_ra
        ):
            QTimer.singleShot(a_delay, lambda p=acp: self._viewmodel.connect_actuator(p))
            parts.append("Actuator")

        addr = (saved.get("ando_gpib") or "").strip()
        if addr and addr not in ("(no GPIB found)",) and not st.get("Ando"):
            self._viewmodel.connect_ando(addr)
            parts.append("Ando")

        wm = (saved.get("wavemeter_gpib") or "").strip()
        if wm and wm not in ("(no GPIB found)",) and not st.get("Wavemeter"):
            QTimer.singleShot(
                int(_CONNECT_ALL_WAVEMETER_AFTER_ANDO_MS),
                lambda a=wm: self._viewmodel.connect_wavemeter(a),
            )
            parts.append("Wavemeter")

        visa = (saved.get("thorlabs_visa") or "").strip()
        if (
            visa
            and visa not in ("(no VISA found)", "(no Thorlabs / VISA found)")
            and not st.get("Thorlabs")
        ):
            self._viewmodel.connect_thorlabs(visa)
            parts.append("Thorlabs")

        if prm_sn and prm_sn not in ("(no devices found)",) and not st.get("PRM"):
            try:
                self._viewmodel.connect_prm(prm_sn)
                parts.append("PRM")
            except Exception:
                pass

        if parts:
            self.main_status_log.appendPlainText(
                "Connect retry #{}: reconnecting still disconnected -> {}.".format(attempt, ", ".join(parts))
            )

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
        view_menu = menubar.addMenu("&View")
        if view_menu is not None:
            data_view_act = QAction("&Data View…", self)
            data_view_act.triggered.connect(self._on_open_data_view)
            view_menu.addAction(data_view_act)
        settings_menu = menubar.addMenu("&Settings")
        if settings_menu is not None:
            self._action_dark_theme = QAction("&Dark theme", self)
            self._action_dark_theme.setCheckable(True)
            self._action_dark_theme.setChecked(self._dark_theme_enabled)
            self._action_dark_theme.setToolTip("When checked, use the dark UI theme; when unchecked, use a light theme.")
            self._action_dark_theme.toggled.connect(self._on_dark_theme_toggled)
            settings_menu.addAction(self._action_dark_theme)
        info_menu = menubar.addMenu("&Info")
        if info_menu is not None:
            inst_act = QAction("Connected &instruments…", self)
            inst_act.triggered.connect(self._on_menu_instrument_info)
            info_menu.addAction(inst_act)
        help_menu = menubar.addMenu("&Help")
        if help_menu is not None:
            about_act = QAction("&About", self)
            about_act.triggered.connect(self._on_about)
            help_menu.addAction(about_act)

    def _on_dark_theme_toggled(self, checked: bool) -> None:
        if bool(checked) == bool(self._dark_theme_enabled):
            return
        self._apply_window_chrome_theme(bool(checked))

    def _apply_window_chrome_theme(self, dark: bool) -> None:
        """Persist choice, refresh QApplication + main window chrome (palette, QSS, title bar, footer)."""
        set_dark_theme_saved(dark)
        self._dark_theme_enabled = dark
        app = QApplication.instance()
        if app is not None:
            apply_application_theme(app, dark)
        self.setPalette(get_dark_palette() if dark else get_light_palette())
        self.setStyleSheet(main_stylesheet(getattr(self, "_ui_scale", 1.0), dark))
        chrom = theme_chrome_bg(dark)
        try:
            cw = self.centralWidget()
            if cw is not None:
                _p = QPalette()
                _p.setColor(QPalette.Window, QColor(chrom))
                cw.setPalette(_p)
                cw.setStyleSheet("background-color: {};".format(chrom))
        except Exception:
            pass
        try:
            _stack = self.tabs.findChild(QStackedWidget)
            if _stack is not None:
                _sp = QPalette()
                _sp.setColor(QPalette.Window, QColor(chrom))
                _stack.setPalette(_sp)
                _stack.setStyleSheet(
                    "QStackedWidget {{ margin: 0px; padding: 0px; border: none; background-color: {}; }}".format(chrom)
                )
        except Exception:
            pass
        try:
            self.tabs.setStyleSheet(self._main_tabs_stylesheet())
        except Exception:
            pass
        try:
            set_dark_title_bar(int(self.winId()), dark)
        except Exception:
            pass
        try:
            self.main_new_recipe_btn.setStyleSheet(qpushbutton_local_style_neutral(dark=dark))
        except Exception:
            pass
        self._reapply_footer_fonts()
        self._reapply_main_tab_fonts()
        self._reapply_engineer_tab_fonts()
        self._reapply_result_plot_summary_chrome()
        self._reapply_tests_pass_fail_row_styles()

    def _reapply_result_plot_summary_chrome(self) -> None:
        """Re-apply Result summary, Summary tab panel, and plot group/metric QSS after dark/light toggle."""
        t = self._tt()
        spanel = getattr(self, "_rt_summary_panel", None)
        if spanel is not None:
            spanel.setStyleSheet(theme_qframe_form_panel_qss(t, "rt_summary_panel"))
        tsum = getattr(self, "_rt_summary_title_lbl", None)
        if tsum is not None:
            tsum.setStyleSheet(f"background: transparent; font-weight: bold; color: {t.text}; font-size: 12pt;")
        sump = getattr(self, "_summary_tab_panel", None)
        if sump is not None:
            sump.setStyleSheet(theme_qframe_form_panel_qss(t, "summary_panel"))
        stit = getattr(self, "_summary_tab_title_lbl", None)
        if stit is not None:
            stit.setStyleSheet(f"background: transparent; font-weight: bold; color: {t.text}; font-size: 12pt;")
        gb_style = theme_qgroupbox_plot_surround_qss(t)
        for gb in getattr(self, "_rt_graph_groupboxes", []) or []:
            try:
                gb.setStyleSheet(gb_style)
            except Exception:
                pass
        for gb in getattr(self, "_plot_tab_graph_groupboxes", []) or []:
            try:
                gb.setStyleSheet(gb_style)
            except Exception:
                pass
        mfield = theme_metric_field_style(t)
        for le in getattr(self, "_rt_metric_line_edits", []) or []:
            try:
                le.setStyleSheet(mfield)
            except Exception:
                pass
        for le in getattr(self, "_plot_tab_metric_line_edits", []) or []:
            try:
                le.setStyleSheet(mfield)
            except Exception:
                pass
        mcaption = theme_metric_caption_style(t)
        for lb in getattr(self, "_rt_metric_labels", []) or []:
            try:
                lb.setStyleSheet(mcaption)
            except Exception:
                pass
        for lb in getattr(self, "_plot_tab_metric_labels", []) or []:
            try:
                lb.setStyleSheet(mcaption)
            except Exception:
                pass
        rsep = getattr(self, "_rt_graph_section_lbl", None)
        if rsep is not None:
            rsep.setStyleSheet(
                f"color: {t.muted}; font-size: 11px; font-weight: bold; margin-top: 4px; background: transparent;"
            )

    def _reapply_tests_pass_fail_row_styles(self) -> None:
        """Pending / PASS / FAIL chip colors after theme toggle."""
        rows = getattr(self, "_tests_pass_fail_rows", None)
        if not rows:
            return
        t = self._tt()
        chip_base = (
            "padding: 3px 10px; border-radius: 4px; font-size: 11px; font-weight: bold; min-width: 52px;"
        )
        pending = theme_pass_fail_chip_style(t)
        for row in rows:
            nl = row.get("name_lbl")
            if nl is not None:
                nl.setStyleSheet(theme_pass_fail_name_style(t))
            ol = row.get("outcome_lbl")
            if ol is None:
                continue
            txt = (ol.text() or "").strip().upper()
            if txt == "PASS":
                self._apply_tests_pass_fail_row_state(row, True)
            elif txt == "FAIL":
                self._apply_tests_pass_fail_row_state(row, False)
            else:
                ol.setStyleSheet(chip_base + pending)

    def _on_open_data_view(self) -> None:
        try:
            from view.data_view_window import open_data_view
            win = open_data_view(self)
            if win is not None:
                win.setWindowFlags(
                    win.windowFlags()
                    | QtCompat.Window
                    | QtCompat.WindowMinimizeButtonHint
                    | QtCompat.WindowMaximizeButtonHint
                    | QtCompat.WindowCloseButtonHint
                )
                place_on_secondary_screen_before_show(win, self, maximize=True)
                win.showMaximized()
            self._data_view_win = win
        except Exception as e:
            QMessageBox.critical(self, "Data View Error", "Could not open Data View:\n{}".format(e))

    def _on_menu_instrument_info(self) -> None:
        """Modeless dialog; *IDN? queries run on GatherInstrumentInfoThread (GUI stays responsive)."""
        dlg = QDialog(self)
        dlg.setWindowTitle("Instrument information")
        sc = max(0.85, float(getattr(self, "_ui_scale", 1.0)))
        dlg.setMinimumSize(int(560 * sc), int(420 * sc))
        vl = QVBoxLayout(dlg)
        lab = QLabel(
            "Queries *IDN? (or the closest command) for each connected device. "
            "Work runs in a background thread so the UI stays responsive."
        )
        lab.setWordWrap(True)
        _t_dlg = self._tt()
        lab.setStyleSheet(f"color: {_t_dlg.muted}; font-size: 11px;")
        vl.addWidget(lab)
        te = QPlainTextEdit()
        te.setReadOnly(True)
        te.setPlainText("Starting background query…")
        te.setStyleSheet(theme_console_plaintext_qss(_t_dlg))
        vl.addWidget(te, 1)
        close_btn = QPushButton("Close")
        close_btn.clicked.connect(dlg.accept)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(close_btn)
        vl.addLayout(row)

        th = GatherInstrumentInfoThread(self._viewmodel, self)
        self._instrument_info_gather_thread = th

        def _apply_text(txt: str) -> None:
            try:
                te.setPlainText(txt)
            except RuntimeError:
                pass

        def _apply_fail(tb: str) -> None:
            try:
                te.setPlainText("Error while gathering instrument info:\n\n" + tb)
            except RuntimeError:
                pass

        th.result_ready.connect(_apply_text)
        th.failed.connect(_apply_fail)
        th.finished.connect(th.deleteLater)

        def _clear_ref() -> None:
            if getattr(self, "_instrument_info_gather_thread", None) is th:
                self._instrument_info_gather_thread = None

        th.finished.connect(_clear_ref)
        th.start()
        dlg.show()

    def _sp(self, n: float) -> int:
        """Scaled pixel size for fonts/spacing from current window scale."""
        return scaled_px(n, self._ui_scale)

    def _main_tabs_stylesheet(self) -> str:
        """
        Pane colors only — the gap under the tab bar is fixed in _FullWidthTabWidget._stack_flush_under_tab_bar
        (QSS cannot move QStackedWidget; negative margin on QTabWidget::pane does not affect layout).
        """
        c = theme_chrome_bg(getattr(self, "_dark_theme_enabled", True))
        return (
            "QTabWidget::pane {{ background-color: {}; border: 0px; margin: 0px; padding: 0px; }}"
            "QTabBar::tab {{ margin-bottom: 0px; }}".format(c)
        )

    @staticmethod
    def _scale_font_size_px_in_style(style: str, new_px: int) -> str:
        """Replace or append font-size in a QSS fragment while preserving color and other rules."""
        s = (style or "").strip()
        if not s:
            return f"font-size: {new_px}px;"
        if re.search(r"font-size:\s*\d+(\.\d+)?px", s, re.I):
            return re.sub(r"font-size:\s*\d+(\.\d+)?px", f"font-size: {new_px}px;", s, flags=re.I)
        return f"{s}; font-size: {new_px}px;"

    def _prm_status_label_style(self, color_hex: str) -> str:
        return f"background: transparent; color: {color_hex}; font-size: {self._sp(11)}px;"

    def resizeEvent(self, event: QResizeEvent):
        super().resizeEvent(event)
        self._ui_scale_timer.start()

    def _apply_ui_scale_from_resize(self):
        """Derive font/UI scale from window width; refresh global stylesheet and tab-local styles."""
        w = max(640, self.width())
        # Gentler curve + lower cap so maximized / very wide windows do not oversize text (was w/1500, cap 1.38).
        scale = max(0.78, min(1.12, w / 1720.0))
        if abs(scale - getattr(self, "_ui_scale", 0)) < 0.02:
            return
        self._ui_scale = scale
        app = QApplication.instance()
        if app is not None:
            app.setProperty("ui_scale", scale)
            app_a = cast(Any, app)
            f = QFont(app_a.font())
            f.setPointSizeF(8.75 * scale)
            app_a.setFont(f)
        self.setStyleSheet(main_stylesheet(scale, self._dark_theme_enabled))
        try:
            self.tabs.setStyleSheet(self._main_tabs_stylesheet())
        except Exception:
            pass
        try:
            _tb_main = self.tabs.tabBar()
            if _tb_main is not None:
                _tb_main.updateGeometry()
        except Exception:
            pass
        try:
            _eng = getattr(self, "_engineer_control_inner_tabs", None)
            if _eng is not None:
                _eng.tabBar().updateGeometry()
        except Exception:
            pass
        self._reapply_main_tab_fonts()
        self._reapply_engineer_tab_fonts()
        self._reapply_footer_fonts()

    def _reapply_footer_fonts(self):
        if not hasattr(self, "footer_status_label"):
            return
        sp = self._sp
        _ft = self._tt().text
        self.footer_status_label.setStyleSheet(f"background: transparent; color: {_ft}; font-size: {sp(11)}px;")
        self.footer_connecting_label.setStyleSheet(
            f"background: transparent; color: #ff9800; font-size: {sp(11)}px; font-weight: bold;"
        )
        self.footer_frame.setMinimumHeight(max(34, int(40 * self._ui_scale)))

    def _reapply_main_tab_fonts(self):
        """Re-apply Main tab inline styles when window scale changes."""
        if not hasattr(self, "main_status_log"):
            return
        sp = self._sp
        _d = getattr(self, "_dark_theme_enabled", True)
        if _d:
            _gb_bg, _gb_bd, _gb_ttl = "#2d2d34", "#3a3a42", "#e6e6e6"
            _read_c, _val_c = "#b0b0b0", "#e6e6e6"
            _cell_bg, _cell_bd = "#2d2d34", "#3a3a42"
            _log_bg, _log_fg, _log_bd = "#2d2d34", "#e6e6e6", "#3a3a42"
            _align_dis_bg, _align_dis_tx = "#2d2d34", "#808080"
        else:
            _gb_bg, _gb_bd, _gb_ttl = "#f5f5f5", "#c0c0c0", "#222222"
            _read_c, _val_c = "#555555", "#222222"
            _cell_bg, _cell_bd = "#ffffff", "#b0b0b0"
            _log_bg, _log_fg, _log_bd = "#ffffff", "#222222", "#b0b0b0"
            _align_dis_bg, _align_dis_tx = "#e8e8e8", "#888888"
        box_style = (
            f"QGroupBox {{ font-weight: bold; font-size: {sp(13)}px; border: 1px solid {_gb_bd}; border-radius: 4px; "
            f"margin: 0; padding: {sp(18)}px {sp(6)}px {sp(6)}px {sp(6)}px; background-color: {_gb_bg}; }} "
            f"QGroupBox::title {{ subcontrol-origin: padding; subcontrol-position: top left; top: 2px; left: 10px; "
            f"padding: 0 {sp(6)}px; color: {_gb_ttl}; font-size: {sp(13)}px; }}"
        )
        read_style = f"background: transparent; color: {_read_c}; font-size: {sp(12)}px;"
        value_style = f"background: transparent; color: {_val_c}; font-size: {sp(13)}px; font-weight: bold;"
        led_off = (
            f"background-color: #555; border-radius: {sp(8)}px; min-width: {sp(16)}px; max-width: {sp(16)}px; "
            f"min-height: {sp(16)}px; max-height: {sp(16)}px;"
        )
        read_style_c3 = f"background: transparent; color: {_read_c}; font-size: {sp(11)}px;"
        value_box_style = (
            f"background-color: {_cell_bg}; color: {_val_c}; border: 1px solid {_cell_bd}; padding: {sp(6)}px; min-height: {sp(22)}px;"
        )
        detail_label_style = f"background: transparent; color: {_read_c}; font-size: {sp(11)}px;"
        detail_value_style = f"background: transparent; color: {_val_c}; font-size: {sp(12)}px; min-height: {sp(18)}px;"
        for gb in (
            getattr(self, "_main_tab_gb_laser", None),
            getattr(self, "_main_tab_gb_tec", None),
            getattr(self, "_main_tab_gb_status", None),
            getattr(self, "_main_tab_gb_start", None),
            getattr(self, "_main_tab_gb_details", None),
            getattr(self, "_main_tab_gb_tests", None),
        ):
            if gb is not None:
                gb.setStyleSheet(box_style)
        for lbl in (
            self.main_laser_current_value,
            self.main_laser_voltage_value,
            self.main_laser_set_current_value,
            self.main_laser_status_value,
        ):
            lbl.setStyleSheet(value_style)
        for lbl in (
            self.main_tec_voltage_value,
            self.main_tec_temp_value,
            self.main_tec_current_value,
            self.main_tec_set_temp_value,
            self.main_tec_status_value,
        ):
            lbl.setStyleSheet(value_style)
        gl = getattr(self, "_main_tab_gb_laser", None)
        if gl is not None:
            for lbl in gl.findChildren(QLabel):
                if lbl not in (
                    self.main_laser_current_value,
                    self.main_laser_voltage_value,
                    self.main_laser_set_current_value,
                    self.main_laser_status_value,
                    self.main_laser_led,
                ):
                    lbl.setStyleSheet(read_style)
        gt = getattr(self, "_main_tab_gb_tec", None)
        if gt is not None:
            for lbl in gt.findChildren(QLabel):
                if lbl not in (
                    self.main_tec_voltage_value,
                    self.main_tec_temp_value,
                    self.main_tec_current_value,
                    self.main_tec_set_temp_value,
                    self.main_tec_status_value,
                    self.main_tec_led,
                ):
                    lbl.setStyleSheet(read_style)
        self.main_laser_led.setFixedSize(sp(16), sp(16))
        self.main_laser_led.setStyleSheet(led_off)
        self.main_tec_led.setFixedSize(sp(16), sp(16))
        self.main_tec_led.setStyleSheet(led_off)
        self.main_status_log.setMinimumHeight(max(56, sp(72)))
        self.main_status_log.setStyleSheet(
            f"QPlainTextEdit {{ font-size: {sp(10)}px; padding: {sp(4)}px {sp(6)}px; background-color: {_log_bg}; "
            f"color: {_log_fg}; border: 1px solid {_log_bd}; }}"
        )
        self.main_start_new_btn.setMinimumHeight(max(40, sp(48)))
        self.main_new_recipe_btn.setMinimumHeight(max(40, sp(48)))
        self.main_run_btn.setMinimumHeight(max(40, sp(48)))
        self.main_stop_btn.setMinimumHeight(max(40, sp(48)))
        dbox = getattr(self, "_main_tab_gb_details", None)
        if dbox is not None:
            for lbl in dbox.findChildren(QLabel):
                if lbl in (
                    self.details_op_name,
                    self.details_recipe,
                    self.details_serial_no,
                    self.details_part_no,
                    self.details_wavelength,
                    self.details_smsr_on,
                ):
                    lbl.setStyleSheet(detail_value_style)
                else:
                    lbl.setStyleSheet(detail_label_style)
        self._tests_pass_fail_placeholder.setStyleSheet(
            f"background: transparent; color: #888888; font-size: {sp(11)}px; padding: {sp(4)}px;"
        )
        cs = max(96, min(180, int(round(_MAIN_TAB_STATUS_CIRCLE_PX * self._ui_scale))))
        cst = _main_tab_status_circle_stylesheet("#555", cs, sp(13))
        for circ in (self.main_test_ready_indicator, self.main_pass_fail_indicator):
            circ.setStyleSheet(cst)
            circ.setFixedSize(cs, cs)
        self.main_align_btn.setMinimumHeight(max(40, sp(48)))
        self.main_align_btn.setStyleSheet(
            f"QPushButton#btn_align {{ background-color: {COLOR_ORANGE}; color: white; font-weight: bold; "
            f"font-size: {sp(12)}px; padding: {sp(10)}px {sp(24)}px; border: 1px solid {_cell_bd}; }}"
            f"QPushButton#btn_align:hover {{ background-color: {COLOR_ORANGE_HOVER}; }}"
            f"QPushButton#btn_align:pressed {{ background-color: {COLOR_ORANGE_HOVER}; }}"
            f"QPushButton#btn_align:disabled {{ background-color: {_align_dis_bg}; color: {_align_dis_tx}; }}"
        )
        for w in (
            self.main_time_min,
            self.main_time_sec,
            self.main_gentec_power_value,
            self.main_thorlabs_power_value,
        ):
            w.setStyleSheet(value_box_style)
        if hasattr(self, "main_gentec_mult_value"):
            self.main_gentec_mult_value.setStyleSheet(
                f"QDoubleSpinBox {{ background-color: {_cell_bg}; color: {_val_c}; border: 1px solid {_cell_bd}; "
                f"padding: {sp(4)}px {sp(6)}px; min-height: {sp(22)}px; font-size: {sp(12)}px; font-weight: bold; }}"
                + spinbox_arrow_styles_for_theme(_d)
            )
        if hasattr(self, "main_thorlabs_mult_value"):
            self.main_thorlabs_mult_value.setStyleSheet(
                f"QDoubleSpinBox {{ background-color: {_cell_bg}; color: {_val_c}; border: 1px solid {_cell_bd}; "
                f"padding: {sp(4)}px {sp(6)}px; min-height: {sp(22)}px; font-size: {sp(12)}px; font-weight: bold; }}"
                + spinbox_arrow_styles_for_theme(_d)
            )
        time_colon = getattr(self, "_main_time_colon_label", None)
        if time_colon is not None:
            time_colon.setStyleSheet(value_box_style)
        for lbl, t in (
            (getattr(self, "_main_tab_tf_lbl", None), read_style_c3),
            (getattr(self, "_main_tab_pf_lbl", None), read_style_c3),
            (getattr(self, "_main_tab_time_elapsed_lbl", None), read_style_c3),
            (getattr(self, "_main_tab_gp_lbl", None), read_style_c3),
            (getattr(self, "_main_tab_gm_lbl", None), read_style_c3),
            (getattr(self, "_main_tab_tp_lbl", None), read_style_c3),
            (getattr(self, "_main_tab_tm_lbl", None), read_style_c3),
        ):
            if lbl is not None:
                lbl.setStyleSheet(t)
        if hasattr(self, "main_failure_reason"):
            self.main_failure_reason.setMinimumHeight(max(120, sp(100)))
        _t_m = theme_tokens(_d)
        ff = getattr(self, "_main_failure_outer_frame", None)
        if ff is not None:
            ff.setStyleSheet(theme_failure_outer_qss(_t_m))
        fl = getattr(self, "_main_failure_title_lbl", None)
        if fl is not None:
            fl.setStyleSheet(f"background: transparent; color: {_t_m.text}; font-weight: bold; font-size: {sp(12)}px;")
        if hasattr(self, "main_failure_reason"):
            self.main_failure_reason.setStyleSheet(theme_failure_plaintext_qss(_t_m))

    def _reapply_engineer_tab_fonts(self):
        """Re-apply Engineer Control (manual) tab fonts when scale changes."""
        if not hasattr(self, "arroyo_set_current_spin"):
            return
        sp = self._sp
        _d = getattr(self, "_dark_theme_enabled", True)
        if _d:
            _gb_bg, _gb_bd, _gb_ttl = "#2d2d34", "#3a3a42", "#e6e6e6"
            _read_c, _val_c = "#b0b0b0", "#e6e6e6"
            _cell, _cell_hov = "#2d2d34", "#3a3a42"
            _stat_bg, _stat_tx = "#2d2d34", "#b0bec5"
        else:
            _gb_bg, _gb_bd, _gb_ttl = "#f5f5f5", "#c0c0c0", "#222222"
            _read_c, _val_c = "#555555", "#222222"
            _cell, _cell_hov = "#ffffff", "#e8e8e8"
            _stat_bg, _stat_tx = "#ececec", "#444444"
        box_style = (
            f"QGroupBox {{ font-weight: bold; font-size: {sp(13)}px; border: 1px solid {_gb_bd}; border-radius: 4px; "
            f"margin: 0; padding: {sp(18)}px {sp(6)}px {sp(6)}px {sp(6)}px; background-color: {_gb_bg}; }} "
            f"QGroupBox::title {{ subcontrol-origin: padding; subcontrol-position: top left; top: 2px; left: 10px; "
            f"padding: 0 {sp(6)}px; color: {_gb_ttl}; font-size: {sp(13)}px; }}"
        )
        read_style = f"background: transparent; color: {_read_c}; font-size: {sp(12)}px;"
        value_style = f"background: transparent; color: {_val_c}; font-size: {sp(13)}px; font-weight: bold; min-height: {sp(20)}px;"
        spin_style = (
            f"background-color: {_cell}; color: {_val_c}; font-size: {sp(11)}px; min-height: {sp(22)}px; max-height: {sp(26)}px;"
            f"border: 1px solid {_gb_bd};"
            + spinbox_arrow_styles_for_theme(_d)
        )
        btn_style_off = (
            f"QPushButton {{ background-color: {_cell}; color: {_val_c}; font-size: {sp(11)}px; padding: {sp(4)}px {sp(10)}px; }} "
            f"QPushButton:hover {{ background-color: {_cell_hov}; }}"
        )
        btn_style_on = (
            f"QPushButton {{ background-color: #4caf50; color: white; font-size: {sp(11)}px; padding: {sp(4)}px {sp(10)}px; }} "
            f"QPushButton:hover {{ background-color: #388E3C; }}"
        )
        line_ando = f"background-color: {_cell}; color: {_val_c}; font-size: {sp(11)}px; min-height: {sp(22)}px; max-height: {sp(26)}px; padding: {sp(4)}px;"
        for gb in (
            getattr(self, "_eng_gb_arroyo", None),
            getattr(self, "_eng_gb_actuator", None),
            getattr(self, "_eng_gb_prm", None),
            getattr(self, "_eng_gb_ando", None),
            getattr(self, "_eng_gb_readings", None),
            getattr(self, "_eng_gb_wavemeter", None),
        ):
            if gb is not None:
                gb.setStyleSheet(box_style)
        for w in (self.arroyo_actual_current_label, self.arroyo_actual_temp_label):
            w.setStyleSheet(value_style)
        for spin in (
            self.arroyo_set_current_spin,
            self.arroyo_set_temp_spin,
            self.arroyo_max_current_spin,
            self.arroyo_max_temp_spin,
        ):
            spin.setStyleSheet(spin_style)
        self.arroyo_laser_btn.setStyleSheet(btn_style_on if self.arroyo_laser_btn.isChecked() else btn_style_off)
        self.arroyo_tec_btn.setStyleSheet(btn_style_on if self.arroyo_tec_btn.isChecked() else btn_style_off)
        for spin in (
            getattr(self, "actuator_dist_a_spin", None),
            getattr(self, "actuator_dist_b_spin", None),
            getattr(self, "prm_speed_spin", None),
            getattr(self, "prm_angle_spin", None),
            getattr(self, "connection_gentec_mult_value", None),
            getattr(self, "connection_thorlabs_mult_value", None),
            getattr(self, "_manual_pm_wavelength_spin", None),
        ):
            if spin is not None:
                spin.setStyleSheet(spin_style)
        for ed in (
            getattr(self, "ando_center_edit", None),
            getattr(self, "ando_span_edit", None),
            getattr(self, "ando_ref_level_edit", None),
            getattr(self, "ando_log_scale_edit", None),
            getattr(self, "ando_resolution_edit", None),
        ):
            if ed is not None:
                ed.setStyleSheet(line_ando)
        self.ando_sensitivity_combo.setStyleSheet(
            f"background-color: {_cell}; color: {_val_c}; font-size: {sp(11)}px; min-height: {sp(24)}px;"
        )
        if hasattr(self, "wavemeter_wavelength_label"):
            self.wavemeter_wavelength_label.setStyleSheet(
                f"background: transparent; color: {_val_c}; font-size: {sp(21)}px; font-weight: bold; min-height: {sp(28)}px;"
            )
        ab = getattr(self, "_eng_gb_arroyo", None)
        if ab is not None:
            for lbl in ab.findChildren(QLabel):
                if lbl not in (
                    self.arroyo_actual_current_label,
                    self.arroyo_actual_temp_label,
                    getattr(self, "arroyo_laser_led", None),
                    getattr(self, "arroyo_tec_led", None),
                ):
                    lbl.setStyleSheet(read_style)
        act_box = getattr(self, "_eng_gb_actuator", None)
        if act_box is not None:
            for lbl in act_box.findChildren(QLabel):
                if lbl.objectName() == "actuator_status_bar":
                    continue
                lbl.setStyleSheet(read_style)
        if hasattr(self, "actuator_status_bar"):
            self.actuator_status_bar.setStyleSheet(
                f"QLabel#actuator_status_bar {{ background-color: {_stat_bg}; color: {_stat_tx}; "
                f"padding: {sp(6)}px {sp(8)}px; border-radius: 3px; font-size: {sp(11)}px; }}"
            )
        prm_box = getattr(self, "_eng_gb_prm", None)
        if prm_box is not None:
            for lbl in prm_box.findChildren(QLabel):
                if lbl is self.prm_position_label or lbl is self.prm_status_label:
                    continue
                lbl.setStyleSheet(read_style)
        if hasattr(self, "prm_position_label"):
            self.prm_position_label.setStyleSheet(
                f"background: transparent; color: {_read_c}; font-weight: bold; font-size: {sp(11)}px;"
            )
        if hasattr(self, "prm_status_label"):
            self.prm_status_label.setStyleSheet(
                self._scale_font_size_px_in_style(self.prm_status_label.styleSheet(), sp(11))
            )
        ando_box = getattr(self, "_eng_gb_ando", None)
        if ando_box is not None:
            for lbl in ando_box.findChildren(QLabel):
                lbl.setStyleSheet(read_style)
        readings_box = getattr(self, "_eng_gb_readings", None)
        if readings_box is not None:
            for lbl in readings_box.findChildren(QLabel):
                if lbl in (self.gentec_power_label, self.thorlabs_power_label):
                    continue
                lbl.setStyleSheet(read_style)
        if hasattr(self, "gentec_power_label"):
            self.gentec_power_label.setStyleSheet(value_style)
        if hasattr(self, "thorlabs_power_label"):
            self.thorlabs_power_label.setStyleSheet(value_style)
        wavemeter_box = getattr(self, "_eng_gb_wavemeter", None)
        if wavemeter_box is not None and hasattr(self, "wavemeter_wavelength_label"):
            for lbl in wavemeter_box.findChildren(QLabel):
                if lbl is self.wavemeter_wavelength_label:
                    continue
                lbl.setStyleSheet(read_style)
        self._prm_stop_grey_style = theme_prm_stop_grey_qss(self._tt())
        if getattr(self, "_prm_manual_busy", False) and hasattr(self, "prm_stop_btn"):
            self.prm_stop_btn.setStyleSheet(self._prm_stop_orange_style)
            self.prm_istop_btn.setStyleSheet(self._prm_istop_red_style)
        elif hasattr(self, "prm_stop_btn"):
            self.prm_stop_btn.setStyleSheet(self._prm_stop_grey_style)
            self.prm_istop_btn.setStyleSheet(self._prm_stop_grey_style)
        if hasattr(self, "ando_sweep_auto_btn"):
            tbtn = self._tt()
            _bs_off = (
                f"QPushButton {{ background-color: {tbtn.input_bg}; color: {tbtn.input_fg}; font-size: {sp(11)}px; "
                f"padding: {sp(4)}px {sp(10)}px; }} QPushButton:hover {{ background-color: {tbtn.cell_hover}; }}"
            )
            for _b in (
                getattr(self, "ando_sweep_auto_btn", None),
                getattr(self, "ando_sweep_single_btn", None),
                getattr(self, "ando_sweep_repeat_btn", None),
            ):
                if _b is not None:
                    _b.setStyleSheet(_bs_off)
            _stop = getattr(self, "ando_sweep_stop_btn", None)
            if _stop is not None:
                if getattr(self, "_ando_sweep_running", False):
                    _stop.setStyleSheet(
                        "QPushButton { background-color: #f44336; color: white; } "
                        "QPushButton:hover { background-color: #d32f2f; }"
                    )
                else:
                    _stop.setStyleSheet(theme_ando_stop_idle_qss(tbtn))
        if hasattr(self, "_manual_read_wavelength_btn"):
            self._manual_read_wavelength_btn.setStyleSheet(theme_manual_read_wavelength_btn_qss(self._tt()))

    def _make_main_tab(self):
        """Main tab: scrollable 3-column layout so small windows scroll instead of overlapping."""
        outer = QWidget()
        outer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        outer_layout = QVBoxLayout(outer)
        outer_layout.setContentsMargins(0, 0, 0, 0)
        outer_layout.setSpacing(0)
        scroll = QScrollArea()
        scroll.setObjectName("mainTabScroll")
        scroll.setWidgetResizable(True)
        scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(QtCompat.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(QtCompat.ScrollBarAsNeeded)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        w = QWidget()
        w.setObjectName("mainTabScrollContent")
        w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        w.setMinimumWidth(520)
        grid = QGridLayout(w)
        grid.setSpacing(10)
        grid.setContentsMargins(2, 2, 2, 2)
        sp = self._sp
        t = self._tt()
        box_style = (
            f"QGroupBox {{ font-weight: bold; font-size: {sp(13)}px; border: 1px solid {t.panel_bd}; border-radius: 4px; "
            f"margin: 0; padding: {sp(18)}px {sp(6)}px {sp(6)}px {sp(6)}px; background-color: {t.panel}; }} "
            f"QGroupBox::title {{ subcontrol-origin: padding; subcontrol-position: top left; top: 2px; left: 10px; "
            f"padding: 0 {sp(6)}px; color: {t.text}; font-size: {sp(13)}px; }}"
        )

        # Column 1: Laser Details, TEC Details, Status Log
        read_style = f"background: transparent; color: {t.muted}; font-size: {sp(12)}px;"
        value_style = f"background: transparent; color: {t.text}; font-size: {sp(13)}px; font-weight: bold;"
        led_off = (
            f"background-color: #555; border-radius: {sp(8)}px; min-width: {sp(16)}px; max-width: {sp(16)}px; "
            f"min-height: {sp(16)}px; max-height: {sp(16)}px;"
        )

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
        self.main_laser_led.setFixedSize(sp(16), sp(16))
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
        self.main_tec_led.setFixedSize(sp(16), sp(16))
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
        self.main_status_log.setMinimumHeight(max(56, sp(72)))
        self.main_status_log.setStyleSheet(
            f"QPlainTextEdit {{ font-size: {sp(10)}px; padding: {sp(4)}px {sp(6)}px; background-color: {t.input_bg}; "
            f"color: {t.input_fg}; border: 1px solid {t.input_bd}; }}"
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
        left_column.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        grid.addWidget(left_column, 0, 0, 3, 1)

        # Column 2: Start — compact vertical stack; does not reserve excessive height on small screens
        start_box = QGroupBox("Start")
        start_box.setStyleSheet(box_style)
        start_box.setMinimumHeight(200)
        start_box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        start_inner = QVBoxLayout(start_box)
        start_inner.setSpacing(12)
        start_btn_min_h = max(40, sp(48))
        self.main_start_new_btn = QPushButton("Start New")
        self.main_start_new_btn.setObjectName("btn_start_new")
        self.main_start_new_btn.setMinimumHeight(start_btn_min_h)
        self.main_start_new_btn.setStyleSheet(qpushbutton_local_style(COLOR_ORANGE, COLOR_ORANGE_HOVER))
        start_inner.addWidget(self.main_start_new_btn)
        self.main_new_recipe_btn = QPushButton("New Recipe")
        self.main_new_recipe_btn.setMinimumHeight(start_btn_min_h)
        self.main_new_recipe_btn.setStyleSheet(qpushbutton_local_style_neutral(dark=self._dark_theme_enabled))
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
        details_box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        details_inner = QVBoxLayout(details_box)
        detail_label_style = f"background: transparent; color: {t.muted}; font-size: {sp(11)}px;"
        detail_value_style = f"background: transparent; color: {t.text}; font-size: {sp(12)}px; min-height: {sp(18)}px;"
        def detail_row(name):
            row = QHBoxLayout()
            lbl = QLabel(name + ":")
            lbl.setStyleSheet(detail_label_style)
            val = QLabel("—")
            val.setStyleSheet(detail_value_style)
            val.setMinimumWidth(48)
            val.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
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

        # Below Details: one row per TEST_SEQUENCE step — single PASS or FAIL outcome + LED (updated during Run).
        tests_pass_fail_box = QGroupBox("TEST RESULTS")
        tests_pass_fail_box.setStyleSheet(box_style)
        tests_pass_fail_box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.MinimumExpanding)
        tests_pf_outer = QVBoxLayout(tests_pass_fail_box)
        tests_pf_outer.setContentsMargins(8, 12, 8, 8)
        tests_pf_scroll = QScrollArea()
        tests_pf_scroll.setWidgetResizable(True)
        tests_pf_scroll.setFrameShape(QFrame.NoFrame)
        tests_pf_scroll.setHorizontalScrollBarPolicy(QtCompat.ScrollBarAlwaysOff)
        tests_pf_scroll.setMinimumHeight(72)
        tests_pf_scroll.setMaximumHeight(200)
        tests_pf_scroll.setStyleSheet("QScrollArea { background-color: transparent; }")
        self._tests_pass_fail_inner = QWidget()
        self._tests_pass_fail_inner_layout = QVBoxLayout(self._tests_pass_fail_inner)
        self._tests_pass_fail_inner_layout.setContentsMargins(4, 4, 4, 4)
        self._tests_pass_fail_inner_layout.setSpacing(6)
        tests_pf_scroll.setWidget(self._tests_pass_fail_inner)
        tests_pf_outer.addWidget(tests_pf_scroll)
        self.main_tests_pass_fail_box = tests_pass_fail_box
        self._tests_pass_fail_placeholder = QLabel(
            "Choose a recipe in Start New and press Start Test to list tests here."
        )
        self._tests_pass_fail_placeholder.setStyleSheet(
            f"background: transparent; color: #888888; font-size: {sp(11)}px; padding: {sp(4)}px;"
        )
        self._tests_pass_fail_placeholder.setWordWrap(True)
        self._tests_pass_fail_inner_layout.addWidget(self._tests_pass_fail_placeholder)
        self._tests_pass_fail_inner_layout.addStretch()
        grid.addWidget(tests_pass_fail_box, 2, 1)

        # Column 3: Test status, ALIGN, Time Elapsed, readings, Data Viewer, Reason for Failure
        col3 = QWidget()
        col3.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        col3_layout = QVBoxLayout(col3)
        col3_layout.setSpacing(8)
        read_style_c3 = f"background: transparent; color: {t.muted}; font-size: {sp(11)}px;"
        value_box_style = (
            f"background-color: {t.input_bg}; color: {t.input_fg}; border: 1px solid {t.input_bd}; padding: {sp(6)}px; min-height: {sp(22)}px;"
        )
        # Circular indicator: equal width/height + border-radius half = circle
        circle_size = max(96, min(180, int(round(_MAIN_TAB_STATUS_CIRCLE_PX * self._ui_scale))))
        circle_style = _main_tab_status_circle_stylesheet("#555", circle_size, sp(13))
        # Test Finished | Result (last step or overall when run ends)
        status_row = QHBoxLayout()
        status_row.setSpacing(12)
        test_finished_col = QVBoxLayout()
        tf_lbl = QLabel("Test")
        tf_lbl.setStyleSheet(read_style_c3)
        self._main_tab_tf_lbl = tf_lbl
        test_finished_col.addWidget(tf_lbl)
        self.main_test_ready_indicator = QLabel("READY")
        self.main_test_ready_indicator.setAlignment(QtCompat.AlignCenter)
        self.main_test_ready_indicator.setStyleSheet(circle_style)
        self.main_test_ready_indicator.setFixedSize(circle_size, circle_size)
        test_finished_col.addWidget(self.main_test_ready_indicator, 0, QtCompat.AlignCenter)
        status_row.addLayout(test_finished_col)
        status_row.addStretch()
        pass_fail_col = QVBoxLayout()
        pf_lbl = QLabel("Result")
        pf_lbl.setStyleSheet(read_style_c3)
        pf_lbl.setToolTip("Pass or Fail for the last completed step while running; overall result when the sequence finishes.")
        self._main_tab_pf_lbl = pf_lbl
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
        self.main_align_btn.setMinimumHeight(max(40, sp(48)))
        self.main_align_btn.setStyleSheet(
            f"QPushButton#btn_align {{ background-color: {COLOR_ORANGE}; color: white; font-weight: bold; "
            f"font-size: {sp(12)}px; padding: {sp(10)}px {sp(24)}px; border: 1px solid {t.input_bd}; }}"
            f"QPushButton#btn_align:hover {{ background-color: {COLOR_ORANGE_HOVER}; }}"
            f"QPushButton#btn_align:pressed {{ background-color: {COLOR_ORANGE_HOVER}; }}"
            f"QPushButton#btn_align:disabled {{ background-color: {t.panel}; color: #808080; }}"
        )
        col3_layout.addWidget(self.main_align_btn)
        # Time Elapsed
        time_elapsed_lbl = QLabel("Time Elapsed")
        time_elapsed_lbl.setStyleSheet(read_style_c3)
        self._main_tab_time_elapsed_lbl = time_elapsed_lbl
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
        self._main_time_colon_label = time_colon
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
        self._main_tab_gp_lbl = gp_lbl
        gp_row.addWidget(gp_lbl)
        self.main_gentec_power_value = QLineEdit()
        self.main_gentec_power_value.setReadOnly(True)
        self.main_gentec_power_value.setStyleSheet(value_box_style)
        self.main_gentec_power_value.setText("—")
        gp_row.addWidget(self.main_gentec_power_value, 1)
        gp_unit = QLabel("mW")
        gp_unit.setStyleSheet(read_style_c3)
        gp_row.addWidget(gp_unit)
        col3_layout.addLayout(gp_row)
        # Gentec Mult — software scale (× raw *CVU mW after optional meter *GUM); persisted as [Gentec] gui_multiplier
        gm_row = QHBoxLayout()
        gm_lbl = QLabel("Gentec Mult:")
        gm_lbl.setStyleSheet(read_style_c3)
        self._main_tab_gm_lbl = gm_lbl
        gm_row.addWidget(gm_lbl)
        gentec_mult_spin_style = theme_main_tab_gentec_mult_spin_qss(t, sp(4), sp(6), sp(22), sp(12))
        self.main_gentec_mult_value = QDoubleSpinBox()
        self.main_gentec_mult_value.setRange(1e-9, 1e9)
        self.main_gentec_mult_value.setDecimals(6)
        self.main_gentec_mult_value.setSingleStep(0.01)
        self.main_gentec_mult_value.setKeyboardTracking(True)
        self.main_gentec_mult_value.setToolTip(
            "Multiply Gentec power for display and all tests (LIV, limits). "
            "Applied after *CVU→mW and optional meter user multiplier (*GUM). Saved to instrument_config.ini."
        )
        self.main_gentec_mult_value.setStyleSheet(gentec_mult_spin_style)
        self.main_gentec_mult_value.blockSignals(True)
        self.main_gentec_mult_value.setValue(float(self._viewmodel.get_gentec_gui_multiplier()))
        self.main_gentec_mult_value.blockSignals(False)
        self.main_gentec_mult_value.valueChanged.connect(self._on_gentec_mult_spin_value_changed)
        self.main_gentec_mult_value.editingFinished.connect(self._on_gentec_mult_spin_editing_finished)
        gm_row.addWidget(self.main_gentec_mult_value, 1)
        col3_layout.addLayout(gm_row)
        # Thorlabs Power
        tp_row = QHBoxLayout()
        tp_lbl = QLabel("Thorlabs Power:")
        tp_lbl.setStyleSheet(read_style_c3)
        self._main_tab_tp_lbl = tp_lbl
        tp_row.addWidget(tp_lbl)
        self.main_thorlabs_power_value = QLineEdit()
        self.main_thorlabs_power_value.setReadOnly(True)
        self.main_thorlabs_power_value.setStyleSheet(value_box_style)
        self.main_thorlabs_power_value.setText("—")
        tp_row.addWidget(self.main_thorlabs_power_value, 1)
        self.main_thorlabs_power_unit_label = QLabel("mW")
        self.main_thorlabs_power_unit_label.setStyleSheet(read_style_c3)
        tp_row.addWidget(self.main_thorlabs_power_unit_label)
        col3_layout.addLayout(tp_row)
        # Thorlabs Mult — same idea as Gentec Mult; scales all Thorlabs mW/W readbacks (Main tab, PER, LIV, TS…).
        tm_row = QHBoxLayout()
        tm_lbl = QLabel("Thorlabs Mult:")
        tm_lbl.setStyleSheet(read_style_c3)
        self._main_tab_tm_lbl = tm_lbl
        tm_row.addWidget(tm_lbl)
        self.main_thorlabs_mult_value = QDoubleSpinBox()
        self.main_thorlabs_mult_value.setRange(float(THORLABS_GUI_MULT_MIN), float(THORLABS_GUI_MULT_MAX))
        self.main_thorlabs_mult_value.setDecimals(6)
        self.main_thorlabs_mult_value.setSingleStep(0.01)
        self.main_thorlabs_mult_value.setKeyboardTracking(True)
        self.main_thorlabs_mult_value.setToolTip(
            "Multiply raw Thorlabs power once (instrument W × this factor → mW). "
            "Example: 0.3 W × 2 = 600 mW. Range {:.0e}…{:.0e}. Saved to instrument_config.ini [Thorlabs_Powermeter].".format(
                THORLABS_GUI_MULT_MIN, THORLABS_GUI_MULT_MAX
            )
        )
        self.main_thorlabs_mult_value.setStyleSheet(gentec_mult_spin_style)
        self.main_thorlabs_mult_value.blockSignals(True)
        self.main_thorlabs_mult_value.setValue(float(self._viewmodel.get_thorlabs_gui_multiplier()))
        self.main_thorlabs_mult_value.blockSignals(False)
        self.main_thorlabs_mult_value.valueChanged.connect(self._on_thorlabs_mult_spin_value_changed)
        self.main_thorlabs_mult_value.editingFinished.connect(self._on_thorlabs_mult_spin_editing_finished)
        tm_row.addWidget(self.main_thorlabs_mult_value, 1)
        col3_layout.addLayout(tm_row)
        # Data Viewer button
        self.main_data_viewer_btn = QPushButton("Data Viewer")
        self.main_data_viewer_btn.clicked.connect(self._on_open_data_view)
        col3_layout.addWidget(self.main_data_viewer_btn)
        # Reason for Failure
        failure_frame = QFrame()
        failure_frame.setStyleSheet(theme_failure_outer_qss(t))
        self._main_failure_outer_frame = failure_frame
        failure_layout = QVBoxLayout(failure_frame)
        failure_header = QHBoxLayout()
        failure_lbl = QLabel("Reason for Failure")
        failure_lbl.setStyleSheet(f"background: transparent; color: {t.text}; font-weight: bold; font-size: {sp(12)}px;")
        self._main_failure_title_lbl = failure_lbl
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
        self.main_failure_reason.setMinimumHeight(max(120, sp(100)))
        self.main_failure_reason.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.main_failure_reason.setStyleSheet(theme_failure_plaintext_qss(t))
        failure_layout.addWidget(self.main_failure_reason, 1)
        failure_frame.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        col3_layout.addWidget(failure_frame, 1)
        grid.addWidget(col3, 0, 2, 3, 1)

        # Fourth column: intentionally empty (same width share as cols 0–2 so content does not span full window alone)
        empty_col4 = QFrame()
        empty_col4.setFrameShape(QFrame.NoFrame)
        empty_col4.setStyleSheet("background-color: transparent; border: none;")
        grid.addWidget(empty_col4, 0, 3, 3, 1)

        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)
        grid.setColumnStretch(3, 1)
        grid.setRowStretch(2, 1)
        self._main_tab_gb_laser = laser_details_box
        self._main_tab_gb_tec = tec_details_box
        self._main_tab_gb_status = status_log_box
        self._main_tab_gb_start = start_box
        self._main_tab_gb_details = details_box
        self._main_tab_gb_tests = tests_pass_fail_box
        scroll.setWidget(w)
        outer_layout.addWidget(scroll, 1)
        return outer

    def _make_result_tab(self) -> QWidget:
        """Result tab: summary (mirrors Summary tab) first, then test graphs in recipe order (LIV → PER → Spectrum → TS1 → TS2)."""
        outer = QWidget()
        outer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        outer.setStyleSheet("background-color: {};".format(theme_chrome_bg(self._dark_theme_enabled)))
        outer_lay = QVBoxLayout(outer)
        outer_lay.setContentsMargins(0, 0, 0, 0)
        outer_lay.setSpacing(0)

        _chrom_rt = theme_chrome_bg(self._dark_theme_enabled)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(QtCompat.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(QtCompat.ScrollBarAsNeeded)
        scroll.setStyleSheet("QScrollArea {{ background-color: {}; border: none; }}".format(_chrom_rt))

        inner = QWidget()
        inner.setStyleSheet("background-color: {};".format(_chrom_rt))
        inner.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        v = QVBoxLayout(inner)
        v.setContentsMargins(12, 12, 12, 12)
        v.setSpacing(14)

        _t_rt = self._tt()
        summary_style = theme_qframe_form_panel_qss(_t_rt, "rt_summary_panel")

        def _rt_value_box(default_text="0", width=70):
            le = QLineEdit()
            le.setReadOnly(True)
            le.setAlignment(QtCompat.AlignRight)
            le.setText(default_text)
            le.setMinimumWidth(width)
            le.setMaximumHeight(26)
            return le

        spanel = QFrame()
        spanel.setObjectName("rt_summary_panel")
        spanel.setStyleSheet(summary_style)
        self._rt_summary_panel = spanel
        spanel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        spl = QVBoxLayout(spanel)
        spl.setSpacing(10)
        spl.setContentsMargins(16, 14, 16, 14)
        tsum = QLabel("Summary")
        tsum.setStyleSheet(f"background: transparent; font-weight: bold; color: {_t_rt.text}; font-size: 12pt;")
        self._rt_summary_title_lbl = tsum
        spl.addWidget(tsum)
        s_top = QHBoxLayout()
        s_top.setSpacing(20)
        lb_s = QLabel("Serial # :")
        lb_s.setMinimumWidth(100)
        self.rt_summary_serial = _rt_value_box("", 180)
        s_top.addWidget(lb_s)
        s_top.addWidget(self.rt_summary_serial, 0)
        lb_p = QLabel("IPS Part Number :")
        lb_p.setMinimumWidth(120)
        self.rt_summary_ips_part = _rt_value_box("", 180)
        s_top.addWidget(lb_p)
        s_top.addWidget(self.rt_summary_ips_part, 0)
        s_top.addStretch()
        spl.addLayout(s_top)
        cols = QHBoxLayout()
        cols.setSpacing(40)
        lf = QFormLayout()
        lf.setSpacing(8)
        lf.setLabelAlignment(QtCompat.AlignLeft)
        self.rt_summary_test_temp = _rt_value_box("—", 72)
        self.rt_summary_threshold_current = _rt_value_box("—", 72)
        self.rt_summary_slope_efficiency = _rt_value_box("—", 72)
        self.rt_summary_max_current = _rt_value_box("—", 72)
        self.rt_summary_rated_power = _rt_value_box("—", 72)
        self.rt_summary_power_at_max_current = _rt_value_box("—", 72)
        self.rt_summary_i_at_rated_power = _rt_value_box("—", 72)
        lf.addRow("T test (°C):", self.rt_summary_test_temp)
        lf.addRow("Ith (mA):", self.rt_summary_threshold_current)
        lf.addRow("SE:", self.rt_summary_slope_efficiency)
        lf.addRow("Imax (mA):", self.rt_summary_max_current)
        lf.addRow("Lr (mW):", self.rt_summary_rated_power)
        lf.addRow("L@Imax (mW):", self.rt_summary_power_at_max_current)
        lf.addRow("I@Lr (mA):", self.rt_summary_i_at_rated_power)
        cols.addLayout(lf)
        rf = QFormLayout()
        rf.setSpacing(8)
        rf.setLabelAlignment(QtCompat.AlignLeft)
        pw_min_row = QHBoxLayout()
        self.rt_summary_pw_min = _rt_value_box("—", 72)
        pw_min_row.addWidget(self.rt_summary_pw_min)
        pw_min_row.addWidget(QLabel(" @ "))
        self.rt_summary_pw_min_temp = _rt_value_box("—", 56)
        pw_min_row.addWidget(self.rt_summary_pw_min_temp)
        pw_min_row.addWidget(QLabel(" °C"))
        pw_min_row.addStretch()
        rf.addRow("λpk min (nm):", pw_min_row)
        pw_max_row = QHBoxLayout()
        self.rt_summary_pw_max = _rt_value_box("—", 72)
        pw_max_row.addWidget(self.rt_summary_pw_max)
        pw_max_row.addWidget(QLabel(" @ "))
        self.rt_summary_pw_max_temp = _rt_value_box("—", 56)
        pw_max_row.addWidget(self.rt_summary_pw_max_temp)
        pw_max_row.addWidget(QLabel(" °C"))
        pw_max_row.addStretch()
        rf.addRow("λpk max (nm):", pw_max_row)
        self.rt_summary_pw_at_test_t = _rt_value_box("—", 72)
        self.rt_summary_resolution = _rt_value_box("—", 72)
        rf.addRow("λpk @T:", self.rt_summary_pw_at_test_t)
        rf.addRow("Res (nm):", self.rt_summary_resolution)
        cols.addLayout(rf)
        spl.addLayout(cols)
        v.addWidget(spanel)

        sep = QLabel("Test graphs (recipe order)")
        sep.setStyleSheet(
            f"color: {_t_rt.muted}; font-size: 11px; font-weight: bold; margin-top: 4px; background: transparent;"
        )
        self._rt_graph_section_lbl = sep
        v.addWidget(sep)

        self._result_tab_graph_host = QWidget()
        self._result_tab_graph_host.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self._result_tab_graphs_vlayout = QVBoxLayout(self._result_tab_graph_host)
        self._result_tab_graphs_vlayout.setContentsMargins(0, 0, 0, 0)
        self._result_tab_graphs_vlayout.setSpacing(14)
        v.addWidget(self._result_tab_graph_host, 1)

        inner.setMinimumWidth(320)
        scroll.setWidget(inner)
        outer_lay.addWidget(scroll, 1)

        self._rt_seq_stems: List[str] = []
        self._rt_clear_result_graph_refs()
        return outer

    def _rt_clear_result_graph_refs(self) -> None:
        """Clear pointers to Result-tab-only plot widgets (host layout cleared separately)."""
        for attr in (
            "rt_liv_power_curve",
            "rt_liv_voltage_curve",
            "rt_liv_pd_curve",
            "_rt_liv_p1",
            "_rt_liv_vb_voltage",
            "_rt_liv_vb_pd",
            "rt_spectrum_os_curve",
            "rt_spectrum_os_plot",
            "rt_per_plot",
            "rt_per_power_curve",
        ):
            setattr(self, attr, None)
        self._rt_ts1_bundle = None
        self._rt_ts2_bundle = None
        self._rt_liv_overlay_items = []

    def _recipe_ordered_result_stems(self, recipe: Optional[dict]) -> List[str]:
        """Ordered unique stems (liv, per, spectrum, ts1, ts2) from recipe TEST_SEQUENCE."""
        if not recipe or not isinstance(recipe, dict):
            return []
        raw_seq = (
            recipe.get("TEST_SEQUENCE")
            or recipe.get("TestSequence")
            or (recipe.get("GENERAL") or {}).get("TestSequence")
            or (recipe.get("GENERAL") or {}).get("TEST_SEQUENCE")
        )
        seq = self._coerce_test_sequence(raw_seq)
        seen: set = set()
        out: List[str] = []
        for step in seq:
            st = _stem_for_sequence_step(str(step))
            if st and st not in seen:
                seen.add(st)
                out.append(st)
        return out

    def _rebuild_result_tab_graph_layout(self, recipe: Optional[dict]) -> None:
        """Build Result-tab graph group boxes in recipe order (summary stays above)."""
        lay = getattr(self, "_result_tab_graphs_vlayout", None)
        if lay is None:
            return
        while lay.count():
            item = lay.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._rt_clear_result_graph_refs()
        stems = self._recipe_ordered_result_stems(recipe)
        self._rt_seq_stems = stems
        self._rt_graph_groupboxes = []
        self._rt_metric_line_edits = []
        self._rt_metric_labels = []
        if not stems:
            hint = QLabel("Start a recipe with a test sequence to show graphs here.")
            hint.setWordWrap(True)
            _t_h = self._tt()
            hint.setStyleSheet(f"color: {_t_h.muted}; font-size: 12px; background: transparent;")
            lay.addWidget(hint)
            return

        _rt_graph_min_h = 200
        _t_rg = self._tt()
        liv_box_style = theme_qgroupbox_plot_surround_qss(_t_rg)
        res_lbl_style = theme_metric_caption_style(_t_rg)
        res_le_style = theme_metric_field_style(_t_rg)

        def _metric_row(parent_lay: QVBoxLayout, specs: List[Tuple[str, str]]) -> None:
            row = QHBoxLayout()
            row.setSpacing(10)
            for caption, attr in specs:
                lb = QLabel(caption)
                lb.setStyleSheet(res_lbl_style)
                self._rt_metric_labels.append(lb)
                le = QLineEdit()
                le.setReadOnly(True)
                le.setAlignment(QtCompat.AlignRight)
                le.setText("—")
                le.setStyleSheet(res_le_style)
                self._rt_metric_line_edits.append(le)
                setattr(self, attr, le)
                row.addWidget(lb)
                row.addWidget(le)
            row.addStretch(1)
            parent_lay.addLayout(row)

        for stem in stems:
            if stem == "liv":
                gb = QGroupBox("LIV")
                gb.setStyleSheet(liv_box_style)
                gb.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.MinimumExpanding)
                self._rt_graph_groupboxes.append(gb)
                gl = QVBoxLayout(gb)
                gl.setContentsMargins(8, 12, 8, 8)
                if not _PG_AVAILABLE:
                    gl.addWidget(QLabel("Install pyqtgraph for the LIV plot."))
                else:
                    built = build_liv_process_plot()
                    if built is not None:
                        built.series_checkbox_row.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                        gl.addWidget(built.series_checkbox_row, 0)
                        built.plot_widget.setMinimumSize(0, _rt_graph_min_h)
                        built.plot_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                        gl.addWidget(built.plot_widget, 1)
                        self._rt_liv_p1 = built.p1
                        self._rt_liv_vb_voltage = built.vb_voltage
                        self._rt_liv_vb_pd = built.vb_pd
                        self.rt_liv_power_curve = built.power_curve
                        self.rt_liv_voltage_curve = built.voltage_curve
                        self.rt_liv_pd_curve = built.pd_curve
                _metric_row(
                    gl,
                    [
                        ("L@Ir (mW):", "rt_liv_l_at_ir"),
                        ("I@Lr (mA):", "rt_liv_i_at_lr"),
                        ("Ith (mA):", "rt_liv_ith"),
                    ],
                )
                _metric_row(
                    gl,
                    [
                        ("SE (mW/mA):", "rt_liv_se"),
                        ("PD@Ir:", "rt_liv_pd_at_ir"),
                        ("Cal factor:", "rt_liv_cal_factor"),
                    ],
                )
                lay.addWidget(gb)
            elif stem == "per":
                gb = QGroupBox("PER")
                gb.setStyleSheet(liv_box_style)
                gb.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.MinimumExpanding)
                self._rt_graph_groupboxes.append(gb)
                gl = QVBoxLayout(gb)
                gl.setContentsMargins(8, 12, 8, 8)
                if not _PG_AVAILABLE:
                    gl.addWidget(QLabel("Install pyqtgraph for the PER plot."))
                else:
                    pw = PG.PlotWidget()
                    pw.setBackground("w")
                    p = cast(Any, pw.getPlotItem())
                    p.showGrid(x=True, y=True, alpha=0.35)
                    try:
                        p.setTitle("PER — Power (dBm) vs Angle (deg)", color="#333333")
                    except Exception:
                        pass
                    p.setLabel("bottom", "Angle (deg)", color="#333333")
                    p.setLabel("left", "Power (dBm)", color="#333333")
                    axis_pen = PG.mkPen(color="#333333", width=1)
                    for ax_name in ("left", "bottom"):
                        ax = p.getAxis(ax_name)
                        ax.setPen(axis_pen)
                        ax.setTextPen(axis_pen)
                    compact_simple_xy_plot_axes(p, pw)
                    curve = pw.plot([], [], pen=PG.mkPen(PER_SERIES_COLORS[0], width=2), antialias=True)
                    freeze_plot_navigation(p)
                    per_spec = [{"curve": curve}]
                    per_cb_row, _ = make_series_checkbox_row(
                        per_spec,
                        PER_SERIES_LABELS,
                        legend=None,
                        color_swatches=PER_SERIES_COLORS,
                    )
                    per_cb_row.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                    gl.addWidget(per_cb_row, 0)
                    pw.setMinimumSize(0, _rt_graph_min_h)
                    pw.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                    gl.addWidget(pw, 1)
                    self.rt_per_plot = pw
                    self.rt_per_power_curve = curve
                _metric_row(
                    gl,
                    [
                        ("Max power (dBm):", "rt_per_max_dbm"),
                        ("Min power (dBm):", "rt_per_min_dbm"),
                        ("PER angle (°):", "rt_per_angle"),
                    ],
                )
                lay.addWidget(gb)
            elif stem == "spectrum":
                gb = QGroupBox("Spectrum")
                gb.setStyleSheet(liv_box_style)
                gb.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.MinimumExpanding)
                self._rt_graph_groupboxes.append(gb)
                gl = QVBoxLayout(gb)
                gl.setContentsMargins(8, 12, 8, 8)
                if not _PG_AVAILABLE:
                    gl.addWidget(QLabel("Install pyqtgraph for the Spectrum plot."))
                else:
                    spw = PG.PlotWidget()
                    spw.setBackground("w")
                    sp = cast(Any, spw.getPlotItem())
                    sp.getViewBox().setBackgroundColor((255, 255, 255))
                    sp.showGrid(x=True, y=True, alpha=0.45)
                    _sax = "#333333"
                    sp.setLabel("bottom", "Wavelength (nm)", color=_sax)
                    sp.setLabel("left", "Level (dBm)", color=_sax)
                    axis_pen_sp = PG.mkPen(color=_sax, width=1)
                    sp.getAxis("left").setPen(axis_pen_sp)
                    sp.getAxis("left").setTextPen(axis_pen_sp)
                    sp.getAxis("bottom").setPen(axis_pen_sp)
                    sp.getAxis("bottom").setTextPen(axis_pen_sp)
                    os_curve = spw.plot([], [], pen=PG.mkPen("#000000", width=1.5), antialias=True)
                    try:
                        sp.hideAxis("right")
                    except Exception:
                        pass
                    compact_simple_xy_plot_axes(sp, spw)
                    freeze_plot_navigation(sp)
                    try:
                        sp.setTitle("Ando sweep — LVL (dBm)", color=_sax)
                    except Exception:
                        pass
                    spw.setMinimumSize(0, _rt_graph_min_h)
                    spw.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                    gl.addWidget(spw, 1)
                    self.rt_spectrum_os_plot = spw
                    self.rt_spectrum_os_curve = os_curve
                lay.addWidget(gb)
            elif stem in ("ts1", "ts2"):
                title = "Temperature Stability 1" if stem == "ts1" else "Temperature Stability 2"
                plot_title = title + " — vs Temperature (°C)"
                gb = QGroupBox(title)
                gb.setStyleSheet(liv_box_style)
                gb.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.MinimumExpanding)
                self._rt_graph_groupboxes.append(gb)
                gl = QVBoxLayout(gb)
                gl.setContentsMargins(8, 12, 8, 8)
                if not _PG_AVAILABLE:
                    gl.addWidget(QLabel("Install pyqtgraph for temperature stability plots."))
                else:
                    bundle = build_stability_tab_plot(plot_title)
                    if bundle is None:
                        gl.addWidget(QLabel("Could not build stability plot."))
                    else:
                        bundle.series_checkbox_row.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                        gl.addWidget(bundle.series_checkbox_row, 0)
                        bundle.plot_widget.setMinimumSize(0, _rt_graph_min_h)
                        bundle.plot_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                        gl.addWidget(bundle.plot_widget, 1)
                        if stem == "ts1":
                            self._rt_ts1_bundle = bundle
                        else:
                            self._rt_ts2_bundle = bundle
                lay.addWidget(gb)

        self._apply_all_cached_results_to_result_tab()
        self._safe_refresh_summary_tab_from_cached_results()

    def _apply_all_cached_results_to_result_tab(self) -> None:
        """After rebuilding Result graphs or loading cached data, push last step results into Result-tab plots."""
        try:
            self._refresh_liv_panel_common("result", getattr(self, "_last_liv_result", None))
        except Exception:
            pass
        try:
            self._apply_spectrum_result_to_curve_plot(
                getattr(self, "rt_spectrum_os_curve", None),
                getattr(self, "rt_spectrum_os_plot", None),
                getattr(self, "_last_spectrum_result", None),
            )
        except Exception:
            pass
        try:
            b1 = getattr(self, "_rt_ts1_bundle", None)
            if b1 is not None:
                r1 = (getattr(self, "_last_stability_results", None) or {}).get(1)
                if r1 is not None:
                    stability_tab_apply_result(b1, r1)
                else:
                    stability_tab_clear_plot(b1)
        except Exception:
            pass
        try:
            b2 = getattr(self, "_rt_ts2_bundle", None)
            if b2 is not None:
                r2 = (getattr(self, "_last_stability_results", None) or {}).get(2)
                if r2 is not None:
                    stability_tab_apply_result(b2, r2)
                else:
                    stability_tab_clear_plot(b2)
        except Exception:
            pass
        try:
            self._refresh_result_tab_per_plot(getattr(self, "_last_per_result", None))
        except Exception:
            pass

    def _make_plot_tab(self) -> QWidget:
        """Plot tab: scrollable rows (LIV/PER, TS1/TS2, Spectrum) that expand with window size; modest plot minimum height."""
        _chrom_pt = theme_chrome_bg(self._dark_theme_enabled)
        w = QWidget()
        w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        w.setStyleSheet("background-color: {};".format(_chrom_pt))

        # Plot canvases: low minimum so the tab fits small monitors; QSizePolicy.Expanding lets graphs grow with the window.
        _plot_tab_graph_min_h = 200
        _t_pt = self._tt()
        self._plot_tab_graph_groupboxes = []
        self._plot_tab_metric_line_edits = []
        self._plot_tab_metric_labels = []

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(QtCompat.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(QtCompat.ScrollBarAsNeeded)
        scroll.setStyleSheet("QScrollArea {{ background-color: {}; border: none; }}".format(_chrom_pt))

        inner = QWidget()
        inner.setStyleSheet("background-color: {};".format(_chrom_pt))
        inner.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        inner_lay = QVBoxLayout(inner)
        inner_lay.setContentsMargins(8, 8, 8, 8)
        inner_lay.setSpacing(12)

        self._result_liv_overlay_items = []
        self._result_liv_plot_p1 = None
        self._result_liv_vb_voltage = None
        self._result_liv_vb_pd = None
        self.result_liv_power_curve = None
        self.result_liv_voltage_curve = None
        self.result_liv_pd_curve = None
        self.result_per_plot = None
        self.result_per_power_curve = None
        self._plot_tab_ts1_bundle = None
        self._plot_tab_ts2_bundle = None
        self.result_ts1_curves = []
        self.result_ts2_curves = []
        self.result_spectrum_os_plot = None
        self.result_spectrum_os_curve = None

        liv_box_style = theme_qgroupbox_plot_surround_qss(_t_pt)
        res_lbl_style = theme_metric_caption_style(_t_pt)
        res_le_style = theme_metric_field_style(_t_pt)
        _miss_style = f"color: {_t_pt.muted}; font-size: 12px; background: transparent;"

        def _metric_pair(row: QHBoxLayout, caption: str, attr: str) -> None:
            lb = QLabel(caption)
            lb.setStyleSheet(res_lbl_style)
            self._plot_tab_metric_labels.append(lb)
            le = QLineEdit()
            le.setReadOnly(True)
            le.setAlignment(QtCompat.AlignRight)
            le.setText("—")
            le.setStyleSheet(res_le_style)
            self._plot_tab_metric_line_edits.append(le)
            setattr(self, attr, le)
            row.addWidget(lb)
            row.addWidget(le)

        def _add_liv_metric_rows(liv_inner: QVBoxLayout) -> None:
            r1 = QHBoxLayout()
            r1.setSpacing(10)
            _metric_pair(r1, "L@Ir (mW):", "plot_tab_liv_l_at_ir")
            _metric_pair(r1, "I@Lr (mA):", "plot_tab_liv_i_at_lr")
            _metric_pair(r1, "Ith (mA):", "plot_tab_liv_ith")
            r1.addStretch(1)
            liv_inner.addLayout(r1)
            r2 = QHBoxLayout()
            r2.setSpacing(10)
            _metric_pair(r2, "SE (mW/mA):", "plot_tab_liv_se")
            _metric_pair(r2, "PD@Ir:", "plot_tab_liv_pd_at_ir")
            _metric_pair(r2, "Cal factor:", "plot_tab_liv_cal_factor")
            r2.addStretch(1)
            liv_inner.addLayout(r2)

        def _add_per_metric_rows(per_inner: QVBoxLayout) -> None:
            r1 = QHBoxLayout()
            r1.setSpacing(10)
            _metric_pair(r1, "Max power (dBm):", "plot_tab_per_max_dbm")
            _metric_pair(r1, "Min power (dBm):", "plot_tab_per_min_dbm")
            _metric_pair(r1, "PER angle (°):", "plot_tab_per_angle")
            r1.addStretch(1)
            per_inner.addLayout(r1)

        def _add_per_graph(per_inner: QVBoxLayout) -> None:
            if not _PG_AVAILABLE:
                miss = QLabel("Install pyqtgraph to show the PER plot.")
                miss.setStyleSheet(_miss_style)
                miss.setWordWrap(True)
                per_inner.addWidget(miss, 0)
                return
            pw = PG.PlotWidget()
            pw.setBackground("w")
            p = cast(Any, pw.getPlotItem())
            p.showGrid(x=True, y=True, alpha=0.35)
            try:
                p.setTitle("PER — Power (dBm) vs Angle (deg)", color="#333333")
            except Exception:
                pass
            p.setLabel("bottom", "Angle (deg)", color="#333333")
            p.setLabel("left", "Power (dBm)", color="#333333")
            axis_pen = PG.mkPen(color="#333333", width=1)
            for ax_name in ("left", "bottom"):
                ax = p.getAxis(ax_name)
                ax.setPen(axis_pen)
                ax.setTextPen(axis_pen)
            compact_simple_xy_plot_axes(p, pw)
            _c_per = PER_SERIES_COLORS[0]
            curve = pw.plot([], [], pen=PG.mkPen(_c_per, width=2), antialias=True)
            freeze_plot_navigation(p)
            per_spec = [{"curve": curve}]
            per_cb_row, _ = make_series_checkbox_row(
                per_spec,
                PER_SERIES_LABELS,
                legend=None,
                color_swatches=PER_SERIES_COLORS,
            )
            per_cb_row.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            per_inner.addWidget(per_cb_row, 0)
            pw.setMinimumSize(0, _plot_tab_graph_min_h)
            pw.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            per_inner.addWidget(pw, 1)
            self.result_per_plot = pw
            self.result_per_power_curve = curve

        built = build_liv_process_plot() if _PG_AVAILABLE else None

        liv_box = QGroupBox("LIV")
        liv_box.setStyleSheet(liv_box_style)
        liv_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        liv_lay = QVBoxLayout(liv_box)
        liv_lay.setContentsMargins(8, 12, 8, 8)
        liv_lay.setSpacing(6)
        if not _PG_AVAILABLE or built is None:
            miss = QLabel("Install pyqtgraph to show the LIV plot.")
            miss.setStyleSheet(_miss_style)
            miss.setWordWrap(True)
            liv_lay.addWidget(miss)
        else:
            cb_row = built.series_checkbox_row
            cb_row.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            liv_lay.addWidget(cb_row, 0)
            built.plot_widget.setMinimumSize(0, _plot_tab_graph_min_h)
            built.plot_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            liv_lay.addWidget(built.plot_widget, 1)
        _add_liv_metric_rows(liv_lay)

        per_box = QGroupBox("PER")
        per_box.setStyleSheet(liv_box_style)
        per_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        per_lay = QVBoxLayout(per_box)
        per_lay.setContentsMargins(8, 12, 8, 8)
        per_lay.setSpacing(6)
        _add_per_graph(per_lay)
        _add_per_metric_rows(per_lay)

        def _ts_group(title: str, plot_title: str) -> Tuple[QGroupBox, Any]:
            gb = QGroupBox(title)
            gb.setStyleSheet(liv_box_style)
            gb.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            vl = QVBoxLayout(gb)
            vl.setContentsMargins(8, 12, 8, 8)
            vl.setSpacing(6)
            if not _PG_AVAILABLE:
                m = QLabel("Install pyqtgraph to show temperature stability plots.")
                m.setStyleSheet(_miss_style)
                m.setWordWrap(True)
                vl.addWidget(m)
                return gb, None
            bundle = build_stability_tab_plot(plot_title)
            if bundle is None:
                m = QLabel("Install pyqtgraph to show temperature stability plots.")
                m.setStyleSheet(_miss_style)
                m.setWordWrap(True)
                vl.addWidget(m)
                return gb, None
            bundle.series_checkbox_row.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            vl.addWidget(bundle.series_checkbox_row, 0)
            ts_hint = QLabel("Swatch: left = cold→hot · right = hot→cold verify")
            ts_hint.setStyleSheet(f"color: {_t_pt.muted}; font-size: 10px; background: transparent;")
            ts_hint.setWordWrap(True)
            vl.addWidget(ts_hint)
            bundle.plot_widget.setMinimumSize(0, _plot_tab_graph_min_h)
            bundle.plot_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            vl.addWidget(bundle.plot_widget, 1)
            return gb, bundle

        ts1_box, b1 = _ts_group("Temperature Stability 1", "Temperature Stability 1 — vs Temperature (°C)")
        ts2_box, b2 = _ts_group("Temperature Stability 2", "Temperature Stability 2 — vs Temperature (°C)")
        self._plot_tab_ts1_bundle = b1
        self._plot_tab_ts2_bundle = b2
        self.result_ts1_curves = b1.curves_for_main_apply if b1 is not None else []
        self.result_ts2_curves = b2.curves_for_main_apply if b2 is not None else []

        top_wrap = QWidget()
        top_wrap.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        top_row = QHBoxLayout(top_wrap)
        top_row.setContentsMargins(0, 0, 0, 0)
        top_row.setSpacing(12)
        top_row.addWidget(liv_box, 1)
        top_row.addWidget(per_box, 1)

        bot_wrap = QWidget()
        bot_wrap.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        bot_row = QHBoxLayout(bot_wrap)
        bot_row.setContentsMargins(0, 0, 0, 0)
        bot_row.setSpacing(12)
        bot_row.addWidget(ts1_box, 1)
        bot_row.addWidget(ts2_box, 1)

        spectrum_box = QGroupBox("Spectrum")
        spectrum_box.setStyleSheet(liv_box_style)
        spectrum_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        spectrum_lay = QVBoxLayout(spectrum_box)
        spectrum_lay.setContentsMargins(8, 12, 8, 8)
        spectrum_lay.setSpacing(6)
        if not _PG_AVAILABLE:
            sm = QLabel("Install pyqtgraph to show the Spectrum plot.")
            sm.setStyleSheet(_miss_style)
            sm.setWordWrap(True)
            spectrum_lay.addWidget(sm)
        else:
            spw = PG.PlotWidget()
            spw.setBackground("w")
            sp = cast(Any, spw.getPlotItem())
            sp.getViewBox().setBackgroundColor((255, 255, 255))
            sp.showGrid(x=True, y=True, alpha=0.45)
            _sax = "#333333"
            sp.setLabel("bottom", "Wavelength (nm)", color=_sax)
            sp.setLabel("left", "Level (dBm)", color=_sax)
            axis_pen_sp = PG.mkPen(color=_sax, width=1)
            sp.getAxis("left").setPen(axis_pen_sp)
            sp.getAxis("left").setTextPen(axis_pen_sp)
            sp.getAxis("bottom").setPen(axis_pen_sp)
            sp.getAxis("bottom").setTextPen(axis_pen_sp)
            os_curve = spw.plot([], [], pen=PG.mkPen("#000000", width=1.5), antialias=True)
            try:
                sp.hideAxis("right")
            except Exception:
                pass
            compact_simple_xy_plot_axes(sp, spw)
            freeze_plot_navigation(sp)
            try:
                sp.setTitle("Ando sweep — LVL (dBm)", color=_sax)
            except Exception:
                pass
            spw.setMinimumSize(0, _plot_tab_graph_min_h)
            spw.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            spectrum_lay.addWidget(spw, 1)
            self.result_spectrum_os_plot = spw
            self.result_spectrum_os_curve = os_curve

        # Same 2-column widths as rows 1–2: Spectrum graph matches LIV column width; right cell balances layout.
        spec_row_wrap = QWidget()
        spec_row_wrap.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        spec_row = QHBoxLayout(spec_row_wrap)
        spec_row.setContentsMargins(0, 0, 0, 0)
        spec_row.setSpacing(12)
        spec_row.addWidget(spectrum_box, 1)
        spec_balance = QWidget()
        spec_balance.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        spec_balance.setStyleSheet("background-color: transparent;")
        spec_row.addWidget(spec_balance, 1)

        self._plot_tab_graph_groupboxes = [liv_box, per_box, ts1_box, ts2_box, spectrum_box]

        plot_split = QSplitter(Qt.Vertical)
        plot_split.setChildrenCollapsible(False)
        plot_split.setHandleWidth(6)
        plot_split.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        plot_split.addWidget(top_wrap)
        plot_split.addWidget(bot_wrap)
        plot_split.addWidget(spec_row_wrap)
        # Middle band (TS1/TS2) gets extra vertical share so plots are not squashed under LIV/PER.
        plot_split.setStretchFactor(0, 1)
        plot_split.setStretchFactor(1, 2)
        plot_split.setStretchFactor(2, 1)
        inner_lay.addWidget(plot_split, 1)
        scroll.setWidget(inner)

        outer = QVBoxLayout(w)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        outer.addWidget(scroll, 1)

        if built is not None:
            self._result_liv_plot_p1 = built.p1
            self._result_liv_vb_voltage = built.vb_voltage
            self._result_liv_vb_pd = built.vb_pd
            self.result_liv_power_curve = built.power_curve
            self.result_liv_voltage_curve = built.voltage_curve
            self.result_liv_pd_curve = built.pd_curve
            self._plot_tab_liv_plot_widget = built.plot_widget
        else:
            self._result_liv_plot_p1 = None
            self._result_liv_vb_voltage = None
            self._result_liv_vb_pd = None
            self.result_liv_power_curve = None
            self.result_liv_voltage_curve = None
            self.result_liv_pd_curve = None
            self._plot_tab_liv_plot_widget = None

        self._plot_tab_register_graph_enlarge_filters()

        return w

    def _plot_tab_plot_widget_for_key(self, key: str) -> Optional[Any]:
        """Return Plot tab pyqtgraph PlotWidget for LIV / PER / TS1 / TS2 / Spectrum."""
        if key == "liv":
            return getattr(self, "_plot_tab_liv_plot_widget", None)
        if key == "per":
            return getattr(self, "result_per_plot", None)
        if key == "ts1":
            b = getattr(self, "_plot_tab_ts1_bundle", None)
            return b.plot_widget if b is not None else None
        if key == "ts2":
            b = getattr(self, "_plot_tab_ts2_bundle", None)
            return b.plot_widget if b is not None else None
        if key == "spectrum":
            return getattr(self, "result_spectrum_os_plot", None)
        return None

    def _plot_tab_register_graph_enlarge_filters(self) -> None:
        """Install double-click handlers on each Plot tab process graph (enlarge / restore)."""
        self._plot_tab_enlarge_key = None
        self._plot_tab_enlarge_dialog = None
        self._plot_tab_enlarge_restore = None
        old = getattr(self, "_plot_tab_enlarge_filters", None)
        if isinstance(old, list):
            for f in old:
                try:
                    f.deleteLater()
                except Exception:
                    pass
        filters: List[QObject] = []
        specs: List[Tuple[Optional[Any], str, str]] = [
            (getattr(self, "_plot_tab_liv_plot_widget", None), "liv", "LIV — Plot tab"),
            (getattr(self, "result_per_plot", None), "per", "PER — Plot tab"),
            (self._plot_tab_plot_widget_for_key("ts1"), "ts1", "Temperature Stability 1 — Plot tab"),
            (self._plot_tab_plot_widget_for_key("ts2"), "ts2", "Temperature Stability 2 — Plot tab"),
            (getattr(self, "result_spectrum_os_plot", None), "spectrum", "Spectrum — Plot tab"),
        ]
        for pw, pkey, title in specs:
            if pw is None:
                continue
            try:
                pw.setToolTip("")
            except Exception:
                pass
            flt = _PlotTabGraphEnlargeFilter(self, pkey, title)
            vp = getattr(pw, "viewport", None)
            if callable(vp):
                vp().installEventFilter(flt)
            else:
                pw.installEventFilter(flt)
            filters.append(flt)
        self._plot_tab_enlarge_filters = filters

    def _toggle_plot_tab_graph_enlarge(self, plot_key: str, dialog_title: str) -> None:
        """Double-click: maximize graph in a dialog; double-click again (or close dialog) restores."""
        if getattr(self, "_plot_tab_enlarge_key", None) == plot_key:
            self._plot_tab_restore_enlarged_graph()
            return
        self._plot_tab_restore_enlarged_graph()
        self._plot_tab_open_enlarged_graph(plot_key, dialog_title)

    def _plot_tab_open_enlarged_graph(self, plot_key: str, dialog_title: str) -> None:
        pw = self._plot_tab_plot_widget_for_key(plot_key)
        if pw is None:
            return
        parent = pw.parentWidget()
        if parent is None:
            return
        lay = parent.layout()
        if lay is None:
            return
        pw_idx = lay.indexOf(pw)
        if pw_idx < 0:
            return
        try:
            pw_stretch = lay.stretch(pw_idx)
        except Exception:
            pw_stretch = 1

        companions: list = []
        for ci in range(pw_idx - 1, -1, -1):
            item = lay.itemAt(ci)
            if item is None:
                break
            w = item.widget()
            if w is None:
                break
            try:
                st = lay.stretch(ci)
            except Exception:
                st = 0
            companions.insert(0, (w, ci, st))

        for w, _ci, _st in companions:
            lay.removeWidget(w)
        lay.removeWidget(pw)

        dlg = QDialog(self)
        dlg.setWindowTitle(dialog_title)
        dlg.setModal(False)
        vl = QVBoxLayout(dlg)
        vl.setContentsMargins(6, 6, 6, 6)
        for w, _ci, _st in companions:
            vl.addWidget(w, 0)
        vl.addWidget(pw, 1)
        dlg.setWindowFlags(
            (dlg.windowFlags() | QtCompat.WindowMinMaxButtonsHint | QtCompat.Window)
            & ~QtCompat.WindowContextHelpButtonHint
        )
        first_companion_idx = companions[0][1] if companions else pw_idx
        self._plot_tab_enlarge_key = plot_key
        self._plot_tab_enlarge_dialog = dlg
        self._plot_tab_enlarge_restore = (lay, first_companion_idx, pw_stretch, companions)

        def _on_finished(_code: int = 0) -> None:
            if getattr(self, "_plot_tab_enlarge_restore", None) is None:
                return
            self._plot_tab_restore_enlarged_graph()

        dlg.finished.connect(_on_finished)
        dlg.showMaximized()
        try:
            dlg.raise_()
            dlg.activateWindow()
        except Exception:
            pass

    def _plot_tab_restore_enlarged_graph(self) -> None:
        key = getattr(self, "_plot_tab_enlarge_key", None)
        rest = getattr(self, "_plot_tab_enlarge_restore", None)
        dlg = getattr(self, "_plot_tab_enlarge_dialog", None)
        self._plot_tab_enlarge_key = None
        self._plot_tab_enlarge_dialog = None
        self._plot_tab_enlarge_restore = None
        if key is None or rest is None:
            if dlg is not None:
                try:
                    dlg.blockSignals(True)
                    dlg.close()
                except Exception:
                    pass
                try:
                    dlg.deleteLater()
                except Exception:
                    pass
            return
        lay, first_idx, pw_stretch, companions = rest
        pw = self._plot_tab_plot_widget_for_key(key)
        if pw is None:
            if dlg is not None:
                try:
                    dlg.blockSignals(True)
                    dlg.close()
                    dlg.deleteLater()
                except Exception:
                    pass
            return
        if dlg is not None:
            try:
                dl = dlg.layout()
                if dl is not None:
                    for w, _ci, _st in companions:
                        dl.removeWidget(w)
                    dl.removeWidget(pw)
            except Exception:
                pass
            try:
                dlg.blockSignals(True)
                dlg.close()
            except Exception:
                pass
            try:
                dlg.deleteLater()
            except Exception:
                pass
        try:
            insert_at = first_idx
            for w, _ci, st in companions:
                w.setParent(None)
                lay.insertWidget(insert_at, w, st)
                w.show()
                insert_at += 1
            pw.setParent(None)
            lay.insertWidget(insert_at, pw, pw_stretch)
            pw.show()
            gp = lay.parentWidget()
            if gp is not None:
                gp.updateGeometry()
        except Exception:
            pass

    def _liv_power_at_imax_mw(self, liv: Any) -> Optional[float]:
        """Gentec power at the highest sweep current (L@Imax), or final_power if arrays are missing."""
        try:
            cur = list(getattr(liv, "current_array", None) or [])
            pwr = list(getattr(liv, "power_array", None) or getattr(liv, "gentec_power_array", None) or [])
            if cur and pwr and len(cur) == len(pwr):
                im = max(range(len(cur)), key=lambda i: float(cur[i]))
                return float(pwr[im])
            fp = getattr(liv, "final_power", None)
            return float(fp) if fp is not None else None
        except Exception:
            return None

    def _safe_refresh_summary_tab_from_cached_results(self) -> None:
        """Fill Summary tab and Result-tab summary from Main details + recipe + cached LIV/Spectrum/TS/PER."""

        def _dash_txt(s: Optional[str]) -> str:
            t = (s or "").strip()
            return t if t else "—"

        def _set_both(main_attr: str, rt_attr: str, text: str) -> None:
            t = text if (text and str(text).strip() != "") else "—"
            for an in (main_attr, rt_attr):
                w = getattr(self, an, None)
                if w is not None:
                    w.setText(t)

        def _fmt_f(val: Any, nd: int = 4) -> str:
            if val is None:
                return "—"
            try:
                x = float(val)
                if math.isnan(x) or math.isinf(x):
                    return "—"
                return f"{x:.{nd}f}"
            except (TypeError, ValueError):
                return "—"

        recipe = getattr(self, "_current_recipe_data", None)
        liv = self._coerce_liv_result_object(getattr(self, "_last_liv_result", None))
        spec = getattr(self, "_last_spectrum_result", None)
        ts_results = getattr(self, "_last_stability_results", None) or {}

        ser = _dash_txt(getattr(self, "details_serial_no", None) and self.details_serial_no.text())
        part = _dash_txt(getattr(self, "details_part_no", None) and self.details_part_no.text())
        _set_both("summary_serial", "rt_summary_serial", ser)
        _set_both("summary_ips_part", "rt_summary_ips_part", part)

        t_test = "—"
        imax_s = "—"
        lr_s = "—"
        res_nm = "—"
        if isinstance(recipe, dict):
            liv_cfg = recipe.get("LIV") if isinstance(recipe.get("LIV"), dict) else {}
            try:
                tt = liv_cfg.get("temperature") or liv_cfg.get("Temperature")
                if tt is not None and str(tt).strip() != "":
                    t_test = _fmt_f(float(tt), 2)
            except Exception:
                pass
            try:
                mx = liv_cfg.get("max_current_mA") or liv_cfg.get("MAXCurr") or liv_cfg.get("max_current")
                if mx is not None and str(mx).strip() != "":
                    imax_s = _fmt_f(float(mx), 3)
            except Exception:
                pass
            try:
                lr = liv_cfg.get("rated_power_mW") or liv_cfg.get("rated_power") or liv_cfg.get("Lr")
                if lr is not None and str(lr).strip() != "":
                    lr_s = _fmt_f(float(lr), 3)
            except Exception:
                pass
            s_cfg = recipe.get("SPECTRUM") if isinstance(recipe.get("SPECTRUM"), dict) else {}
            try:
                rn = s_cfg.get("resolution_nm") or s_cfg.get("resolution") or s_cfg.get("RESOLUTION")
                if rn is not None and str(rn).strip() != "":
                    res_nm = _fmt_f(float(rn), 4)
            except Exception:
                pass

        _set_both("summary_test_temp", "rt_summary_test_temp", t_test)
        _set_both("summary_max_current", "rt_summary_max_current", imax_s)
        _set_both("summary_rated_power", "rt_summary_rated_power", lr_s)
        _set_both("summary_resolution", "rt_summary_resolution", res_nm)

        if liv is not None:
            _set_both(
                "summary_threshold_current",
                "rt_summary_threshold_current",
                _fmt_f(getattr(liv, "threshold_current", None)),
            )
            _set_both(
                "summary_slope_efficiency",
                "rt_summary_slope_efficiency",
                _fmt_f(getattr(liv, "slope_efficiency", None)),
            )
            _set_both(
                "summary_i_at_rated_power",
                "rt_summary_i_at_rated_power",
                _fmt_f(getattr(liv, "current_at_rated_power", None)),
            )
            p_imax = self._liv_power_at_imax_mw(liv)
            _set_both("summary_power_at_max_current", "rt_summary_power_at_max_current", _fmt_f(p_imax))
        else:
            for a_m, a_r in (
                ("summary_threshold_current", "rt_summary_threshold_current"),
                ("summary_slope_efficiency", "rt_summary_slope_efficiency"),
                ("summary_i_at_rated_power", "rt_summary_i_at_rated_power"),
                ("summary_power_at_max_current", "rt_summary_power_at_max_current"),
            ):
                _set_both(a_m, a_r, "—")

        peaks: List[float] = []
        temps: List[float] = []
        for slot in (1, 2):
            tr = ts_results.get(slot)
            if tr is None:
                continue
            try:
                px = list(getattr(tr, "peak_wavelength_nm", []) or [])
                tx = list(getattr(tr, "temperature_c", []) or [])
                n = min(len(px), len(tx))
                for i in range(n):
                    peaks.append(float(px[i]))
                    temps.append(float(tx[i]))
            except Exception:
                pass
        if peaks and temps and len(peaks) == len(temps):
            imn = min(range(len(peaks)), key=lambda j: peaks[j])
            imx = max(range(len(peaks)), key=lambda j: peaks[j])
            _set_both("summary_pw_min", "rt_summary_pw_min", _fmt_f(peaks[imn], 4))
            _set_both("summary_pw_min_temp", "rt_summary_pw_min_temp", _fmt_f(temps[imn], 2))
            _set_both("summary_pw_max", "rt_summary_pw_max", _fmt_f(peaks[imx], 4))
            _set_both("summary_pw_max_temp", "rt_summary_pw_max_temp", _fmt_f(temps[imx], 2))
        else:
            for a_m, a_r in (
                ("summary_pw_min", "rt_summary_pw_min"),
                ("summary_pw_min_temp", "rt_summary_pw_min_temp"),
                ("summary_pw_max", "rt_summary_pw_max"),
                ("summary_pw_max_temp", "rt_summary_pw_max_temp"),
            ):
                _set_both(a_m, a_r, "—")

        pk_t = "—"
        if spec is not None:
            try:
                pw = float(
                    getattr(spec, "peak_wavelength_second_nm", None)
                    or getattr(spec, "peak_wavelength", None)
                    or getattr(spec, "peak_wavelength_first_nm", None)
                    or 0.0
                )
                if pw > 0:
                    pk_t = _fmt_f(pw, 4)
            except Exception:
                pass
        _set_both("summary_pw_at_test_t", "rt_summary_pw_at_test_t", pk_t)

    def _make_summary_tab(self):
        """Summary panel: theme-aware panel and read-only value boxes (Serial #, IPS Part Number, two columns)."""
        w = QWidget()
        w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout = QVBoxLayout(w)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        t_s = self._tt()
        summary_style = theme_qframe_form_panel_qss(t_s, "summary_panel")
        panel = QFrame()
        panel.setObjectName("summary_panel")
        panel.setStyleSheet(summary_style)
        self._summary_tab_panel = panel
        panel.setMinimumWidth(560)
        panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
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
        title_lbl.setStyleSheet(f"background: transparent; font-weight: bold; color: {t_s.text}; font-size: 12pt;")
        self._summary_tab_title_lbl = title_lbl
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
        left_form.addRow("T test (°C):", self.summary_test_temp)
        left_form.addRow("Ith (mA):", self.summary_threshold_current)
        left_form.addRow("SE:", self.summary_slope_efficiency)
        left_form.addRow("Imax (mA):", self.summary_max_current)
        left_form.addRow("Lr (mW):", self.summary_rated_power)
        left_form.addRow("L@Imax (mW):", self.summary_power_at_max_current)
        left_form.addRow("I@Lr (mA):", self.summary_i_at_rated_power)
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
        right_form.addRow("λpk min (nm):", pw_min_row)
        # Peak Wavelength(nm) Max [value] @ [temp] C
        pw_max_row = QHBoxLayout()
        self.summary_pw_max = value_box("0", 72)
        pw_max_row.addWidget(self.summary_pw_max)
        pw_max_row.addWidget(QLabel(" @ "))
        self.summary_pw_max_temp = value_box("0", 56)
        pw_max_row.addWidget(self.summary_pw_max_temp)
        pw_max_row.addWidget(QLabel(" C"))
        pw_max_row.addStretch()
        right_form.addRow("λpk max (nm):", pw_max_row)
        self.summary_pw_at_test_t = value_box("0", 72)
        right_form.addRow("λpk @T:", self.summary_pw_at_test_t)
        self.summary_resolution = value_box("0", 72)
        right_form.addRow("Res (nm):", self.summary_resolution)
        columns.addLayout(right_form)
        panel_layout.addLayout(columns)

        layout.addWidget(panel)
        layout.addStretch()
        return w

    def _make_recipe_tab(self):
        """Recipe tab: path row + lazy-loaded read-only view (large widget tree — not built in __init__ to avoid startup freeze / white flash)."""
        w = QWidget()
        w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        w.setObjectName("recipe_tab_container")
        w.setAutoFillBackground(True)
        _chrom_rc = theme_chrome_bg(self._dark_theme_enabled)
        w.setStyleSheet("background-color: {};".format(_chrom_rc))
        vbox = QVBoxLayout(w)
        # Path + Browse row
        search_row = QHBoxLayout()
        self._recipe_path_display = QLineEdit()
        self._recipe_path_display.setReadOnly(True)
        self._recipe_path_display.setPlaceholderText(
            "Browse: preview only (does not change Start New). After Start Test, the active recipe is shown here."
        )
        self._recipe_path_display.setMinimumWidth(400)
        search_row.addWidget(self._recipe_path_display)
        browse_btn = QPushButton("Browse")
        browse_btn.clicked.connect(self._on_recipe_tab_browse)
        search_row.addWidget(browse_btn)
        search_row.addStretch()
        vbox.addLayout(search_row)
        self._recipe_detail_host = QWidget()
        self._recipe_detail_host.setStyleSheet("background-color: {};".format(_chrom_rc))
        self._recipe_detail_host.setAutoFillBackground(True)
        self._recipe_detail_layout = QVBoxLayout(self._recipe_detail_host)
        self._recipe_detail_layout.setContentsMargins(0, 0, 0, 0)
        self._recipe_loading_label = QLabel("Loading recipe layout…")
        self._recipe_loading_label.setStyleSheet(
            "color: #9e9e9e; font-size: 12px; padding: 12px; background-color: {};".format(_chrom_rc)
        )
        self._recipe_loading_label.setAlignment(QtCompat.AlignTop | QtCompat.AlignLeft)
        self._recipe_detail_layout.addWidget(self._recipe_loading_label)
        self._recipe_readonly_view = None
        vbox.addWidget(self._recipe_detail_host, 1)
        # Active recipe for Run / alignment / plots (set only on Start Test or Clear).
        self._current_recipe_data = None
        self._current_recipe_path = None
        # Recipe tab read-only view only (Browse, New Recipe save, or mirroring Start New while dialog open).
        self._recipe_tab_data = None
        self._recipe_tab_path = None
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
        data = getattr(self, "_recipe_tab_data", None)
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
                self._recipe_tab_data = data
                self._recipe_tab_path = path
                self._refresh_recipe_tab()
                # Preview only — does not change active run recipe or Start New pre-fill.
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
            path = getattr(self, "_recipe_tab_path", None) or ""
            path_display.setText(path)
        self._ensure_recipe_readonly_view()
        view = getattr(self, "_recipe_readonly_view", None)
        if view is None:
            return
        data = getattr(self, "_recipe_tab_data", None)
        if data:
            view.set_data(data)
        else:
            view.clear()

    def _load_recipe_into_recipe_tab_only(self, path: str) -> None:
        """Load file into Recipe tab preview only; does not change active run recipe (_current_recipe_*)."""
        path = (path or "").strip()
        if not path:
            self._recipe_tab_data = None
            self._recipe_tab_path = None
            self._refresh_recipe_tab()
            return
        try:
            data = self._load_recipe_file(path)
            if not data:
                return
            self._recipe_tab_data = data
            self._recipe_tab_path = path
            self._refresh_recipe_tab()
        except Exception:
            pass

    def _on_recipe_saved_from_editor(self, path: str) -> None:
        """New Recipe SAVE: reload that file into the Recipe tab cache so Browse / tab view match disk (no tab switch)."""
        try:
            self._load_recipe_into_recipe_tab_only((path or "").strip())
        except Exception:
            pass

    def _on_start_new_recipe_selection_changed(self, path: str) -> None:
        """Start New: recipe combo/browse changed — mirror on Recipe tab only until Start Test commits run recipe."""
        self._load_recipe_into_recipe_tab_only(path)

    def _parse_details_wavelength_float(self) -> Optional[float]:
        """Main details strip wavelength (nm) after Start New → Start Test; excludes placeholder dash."""
        txt = (self.details_wavelength.text() or "").strip()
        if not txt or txt == "—":
            return None
        try:
            v = float(txt)
            return v if v > 0 else None
        except (TypeError, ValueError):
            return None

    def _wavelength_nm_from_recipe_dict(self, recipe_data: Dict[str, Any]) -> Optional[float]:
        """Single λ (nm) from loaded recipe dict for fallback when details line is empty."""
        if not isinstance(recipe_data, dict):
            return None
        try:
            wl = recipe_data.get("Wavelength") or recipe_data.get("wavelength")
            if wl is None:
                g = recipe_data.get("GENERAL") or recipe_data.get("General")
                if isinstance(g, dict):
                    wl = g.get("Wavelength") or g.get("wavelength")
            if wl is None:
                liv = recipe_data.get("LIV")
                if isinstance(liv, dict):
                    wl = liv.get("Wavelength") or liv.get("wavelength")
            if wl is not None and str(wl).strip() != "":
                v = float(wl)
                return v if v > 0 else None
        except (TypeError, ValueError):
            pass
        return None

    def _apply_powermeter_wavelength_after_start_new(self, wl_nm: float) -> None:
        """After Start New → Start Test: Thorlabs calibration wavelength only (Gentec λ SCPI not required)."""
        if wl_nm <= 0:
            return
        try:
            self._viewmodel.apply_power_meter_wavelength_nm(float(wl_nm), gentec=False)
        except Exception:
            return
        try:
            self._viewmodel.schedule_power_meter_reads_after_laser_change()
        except Exception:
            pass
        QTimer.singleShot(800, self._viewmodel.request_powermeter_wavelength_readbacks)

    def _apply_wavemeter_range_from_recipe(self, recipe_data, wavelength_nm_override: Optional[float] = None):
        """Set wavemeter TH range from λ (nm): <1000 → 480-1000, else 1000-1650. Sends if wavemeter connected.
        ``wavelength_nm_override`` — Start New dialog λ when it should drive range (and matches powermeter apply)."""
        if not recipe_data or not isinstance(recipe_data, dict):
            return
        try:
            wl_nm: Optional[float] = None
            if wavelength_nm_override is not None:
                try:
                    x = float(wavelength_nm_override)
                    if x > 0:
                        wl_nm = x
                except (TypeError, ValueError):
                    pass
            if wl_nm is None:
                wl = recipe_data.get("Wavelength") or recipe_data.get("wavelength")
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
        """Manual Control: top row Arroyo | Actuator | PRM | Wavemeter | Readings; full-width Ando below (horizontal)."""
        w = QWidget()
        w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        vbox = QVBoxLayout(w)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setAlignment(QtCompat.AlignTop)
        content = QWidget()
        content.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(8, 0, 8, 0)
        content_layout.setSpacing(10)
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(20)
        row.setAlignment(QtCompat.AlignTop)
        t_m = self._tt()
        box_style = theme_engineer_groupbox_qss(t_m)
        read_style = f"background: transparent; color: {t_m.muted}; font-size: 12px;"
        value_style = f"background: transparent; color: {t_m.text}; font-size: 13px; font-weight: bold; min-height: 20px;"
        spin_style = theme_engineer_spin_qss(t_m)
        btn_style_off = theme_engineer_btn_off_qss(t_m, pv=4, ph=10, fs=12)

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
        spin_min_w = 88
        self.arroyo_set_current_spin = QDoubleSpinBox()
        self.arroyo_set_current_spin.setStyleSheet(spin_style)
        self.arroyo_set_current_spin.setMinimumWidth(spin_min_w)
        self.arroyo_set_current_spin.setRange(0, 5000)
        self.arroyo_set_current_spin.setDecimals(1)
        self.arroyo_set_current_spin.setSpecialValueText("")
        self.arroyo_set_current_spin.setKeyboardTracking(False)
        self.arroyo_set_current_spin.setValue(0)
        self.arroyo_set_current_spin.valueChanged.connect(lambda _: self._on_arroyo_set_current())
        set_row_boxes.addWidget(self.arroyo_set_current_spin)
        set_row_boxes.addWidget(QLabel("mA"))
        set_row_boxes.addSpacing(12)
        self.arroyo_set_temp_spin = QDoubleSpinBox()
        self.arroyo_set_temp_spin.setStyleSheet(spin_style)
        self.arroyo_set_temp_spin.setMinimumWidth(spin_min_w)
        self.arroyo_set_temp_spin.setRange(-50, 150)
        self.arroyo_set_temp_spin.setDecimals(2)
        self.arroyo_set_temp_spin.setSpecialValueText("")
        self.arroyo_set_temp_spin.setKeyboardTracking(False)
        self.arroyo_set_temp_spin.setValue(20)
        self.arroyo_set_temp_spin.valueChanged.connect(lambda _: self._on_arroyo_set_temp())
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
        self.arroyo_max_current_spin.valueChanged.connect(lambda _: self._on_arroyo_max_current())
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
        self.arroyo_max_temp_spin.valueChanged.connect(lambda _: self._on_arroyo_max_temp())
        max_row_values.addWidget(self.arroyo_max_temp_spin)
        max_row_values.addWidget(QLabel("°C"))
        arroyo_inner.addLayout(max_row_values)
        # Laser On/Off and TEC On/Off toggle buttons
        self.arroyo_laser_btn = QPushButton("Laser On")
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
        act_box.setMinimumWidth(180)
        act_box.setMaximumHeight(520)
        act_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        act_box.setStyleSheet(box_style)
        act_inner = QVBoxLayout(act_box)
        act_inner.setSpacing(10)
        act_inner.setContentsMargins(10, 8, 10, 8)
        act_spin_style = spin_style
        act_spin_min_w = 88
        # Distance A — Move uses spinbox mm (movea <mm>); Home sends homea
        lbl_dist_a = QLabel("Distance A")
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
        dist_a_row.addWidget(self.actuator_dist_a_spin)
        dist_a_row.addWidget(QLabel("mm"))
        dist_a_row.addSpacing(6)
        move_a_btn = QPushButton("Move")
        move_a_btn.setStyleSheet(btn_style_off)
        move_a_btn.clicked.connect(self._on_actuator_move_a)
        dist_a_row.addWidget(move_a_btn)
        home_a_btn = QPushButton("Home")
        home_a_btn.setStyleSheet(btn_style_off)
        home_a_btn.clicked.connect(self._on_actuator_home_a)
        dist_a_row.addWidget(home_a_btn)
        act_inner.addLayout(dist_a_row)
        # Distance B — Move uses spinbox (moveb <mm>); Home sends homeb
        lbl_dist_b = QLabel("Distance B")
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
        dist_b_row.addWidget(self.actuator_dist_b_spin)
        dist_b_row.addWidget(QLabel("mm"))
        dist_b_row.addSpacing(6)
        move_b_btn = QPushButton("Move")
        move_b_btn.setStyleSheet(btn_style_off)
        move_b_btn.clicked.connect(self._on_actuator_move_b)
        dist_b_row.addWidget(move_b_btn)
        home_b_btn = QPushButton("Home")
        home_b_btn.setStyleSheet(btn_style_off)
        home_b_btn.clicked.connect(self._on_actuator_home_b)
        dist_b_row.addWidget(home_b_btn)
        act_inner.addLayout(dist_b_row)
        # Quick row: fixed distance movea 206 / moveb 206 (same as terminal test script)
        lbl_quick = QLabel("Quick ({} mm)".format(int(ACTUATOR_DEFAULT_MANUAL_DISTANCE_MM)))
        act_inner.addWidget(lbl_quick)
        actions_row = QHBoxLayout()
        move_a_act_btn = QPushButton("Move A")
        move_a_act_btn.setStyleSheet(btn_style_off)
        move_a_act_btn.clicked.connect(self._on_actuator_move_a_quick)
        home_a_act_btn = QPushButton("Home A")
        home_a_act_btn.setStyleSheet(btn_style_off)
        home_a_act_btn.clicked.connect(self._on_actuator_home_a)
        move_b_act_btn = QPushButton("Move B")
        move_b_act_btn.setStyleSheet(btn_style_off)
        move_b_act_btn.clicked.connect(self._on_actuator_move_b_quick)
        home_b_act_btn = QPushButton("Home B")
        home_b_act_btn.setStyleSheet(btn_style_off)
        home_b_act_btn.clicked.connect(self._on_actuator_home_b)
        actions_row.addWidget(move_a_act_btn)
        actions_row.addWidget(home_a_act_btn)
        actions_row.addWidget(move_b_act_btn)
        actions_row.addWidget(home_b_act_btn)
        act_inner.addLayout(actions_row)
        home_both_btn = QPushButton("Home Both")
        home_both_btn.setStyleSheet(btn_style_off)
        home_both_btn.clicked.connect(self._on_actuator_home_both)
        act_inner.addWidget(home_both_btn)
        for lbl in act_box.findChildren(QLabel):
            lbl.setStyleSheet(read_style)
        self.actuator_status_bar = QLabel("A: Not connected  |  B: Not connected")
        self.actuator_status_bar.setObjectName("actuator_status_bar")
        self.actuator_status_bar.setWordWrap(True)
        self.actuator_status_bar.setStyleSheet(theme_actuator_status_bar_qss(t_m))
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
        self.prm_angle_spin.setStyleSheet(act_spin_style)
        self.prm_angle_spin.setRange(-360, 360)
        self.prm_angle_spin.setDecimals(2)
        self.prm_angle_spin.setSpecialValueText("")
        self.prm_angle_spin.setValue(0.0)
        self.prm_angle_spin.setMinimumWidth(prm_spin_min_w)
        prm_row2.addWidget(self.prm_angle_spin)
        prm_move_btn = QPushButton("Move")
        prm_move_btn.setStyleSheet("QPushButton { background-color: #4CAF50; color: white; font-weight: bold; } QPushButton:hover { background-color: #45a049; }")
        prm_move_btn.setMinimumWidth(60)
        prm_move_btn.clicked.connect(self._on_prm_move)
        prm_row2.addWidget(prm_move_btn)
        prm_inner.addLayout(prm_row2)
        # Position readout (updates when connected)
        self.prm_position_label = QLabel("Position: --- °")
        self.prm_position_label.setStyleSheet("background: transparent; font-weight: bold; font-size: 11px;")
        prm_inner.addWidget(self.prm_position_label)
        # Home button
        prm_home_btn = QPushButton("Home")
        prm_home_btn.setStyleSheet("QPushButton { background-color: #2196F3; color: white; } QPushButton:hover { background-color: #1976D2; }")
        prm_home_btn.clicked.connect(self._on_prm_initial_position)
        prm_inner.addWidget(prm_home_btn)
        # Quick: 45, 90, 180, 360
        prm_inner.addWidget(QLabel("Quick:"))
        prm_shortcut_row = QHBoxLayout()
        for angle in (45, 90, 180, 360):
            btn = QPushButton("{}°".format(angle))
            btn.setStyleSheet(btn_style_off)
            btn.setMinimumWidth(44)
            btn.clicked.connect(lambda checked=False, a=angle: self._on_prm_quick_rotate(a))
            prm_shortcut_row.addWidget(btn)
        prm_inner.addLayout(prm_shortcut_row)
        prm_stop_row = QHBoxLayout()
        self._prm_stop_grey_style = theme_prm_stop_grey_qss(t_m)
        self._prm_stop_orange_style = "QPushButton { background-color: #FF9800; color: white; font-weight: bold; } QPushButton:hover { background-color: #F57C00; } QPushButton:pressed { background-color: #E65100; }"
        self._prm_istop_red_style = "QPushButton { background-color: #f44336; color: white; font-weight: bold; } QPushButton:hover { background-color: #d32f2f; } QPushButton:pressed { background-color: #b71c1c; }"
        self.prm_stop_btn = QPushButton("Stop")
        self.prm_stop_btn.setObjectName("prm_stop_smooth_btn")
        self.prm_stop_btn.setStyleSheet(self._prm_stop_grey_style)
        self.prm_stop_btn.setMinimumWidth(52)
        self.prm_stop_btn.setFocusPolicy(QtCompat.StrongFocus)
        self.prm_stop_btn.setCursor(QCursor(QtCompat.PointingHandCursor))
        self.prm_stop_btn.setEnabled(True)
        self.prm_stop_btn.clicked.connect(self._on_prm_stop_smooth)
        prm_stop_row.addWidget(self.prm_stop_btn)
        self.prm_istop_btn = QPushButton("IStop")
        self.prm_istop_btn.setObjectName("prm_stop_immediate_btn")
        self.prm_istop_btn.setStyleSheet(self._prm_stop_grey_style)
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
        prm_inner.addWidget(self.prm_status_label)
        for lbl in prm_box.findChildren(QLabel):
            lbl.setStyleSheet(read_style)
        self.prm_position_label.setStyleSheet(
            f"background: transparent; color: #b0b0b0; font-weight: bold; font-size: {self._sp(11)}px;"
        )
        self.prm_status_label.setStyleSheet(self._prm_status_label_style("#4caf50"))
        row.addWidget(prm_box, 1, QtCompat.AlignTop)
        # Wavemeter — same column slot as former Ando (between PRM and Readings)
        wavemeter_box = QGroupBox("Wavemeter")
        wavemeter_box.setMinimumWidth(200)
        wavemeter_box.setMaximumHeight(450)
        wavemeter_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        wavemeter_box.setStyleSheet(box_style)
        wavemeter_inner = QVBoxLayout(wavemeter_box)
        wavemeter_inner.setSpacing(4)
        wavemeter_inner.setContentsMargins(8, 4, 8, 8)
        wavemeter_inner.addWidget(QLabel("Range"))
        wavemeter_range_row = QHBoxLayout()
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
        self.wavemeter_wavelength_label.setStyleSheet(theme_wavemeter_big_value_qss(t_m))
        wavemeter_inner.addWidget(self.wavemeter_wavelength_label)
        wavemeter_inner.addWidget(QLabel("nm"))
        for lbl in wavemeter_box.findChildren(QLabel):
            lbl.setStyleSheet(read_style)
        self.wavemeter_wavelength_label.setStyleSheet(theme_wavemeter_big_value_qss(t_m))
        row.addWidget(wavemeter_box, 1, QtCompat.AlignTop)
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
        gentec_mult_conn_row = QHBoxLayout()
        gentec_mult_conn_row.addWidget(QLabel("Gentec Mult (×)"))
        self.connection_gentec_mult_value = QDoubleSpinBox()
        spx = self._sp
        self.connection_gentec_mult_value.setStyleSheet(
            theme_main_tab_gentec_mult_spin_qss(t_m, spx(4), spx(6), spx(22), spx(12))
        )
        self.connection_gentec_mult_value.setMinimumWidth(72)
        self.connection_gentec_mult_value.setRange(1e-9, 1e9)
        self.connection_gentec_mult_value.setDecimals(6)
        self.connection_gentec_mult_value.setSingleStep(0.01)
        self.connection_gentec_mult_value.setKeyboardTracking(True)
        self.connection_gentec_mult_value.setToolTip(
            "Same as Main tab — scales Gentec mW everywhere. Editable; saved when you press Enter or leave the field."
        )
        self.connection_gentec_mult_value.blockSignals(True)
        self.connection_gentec_mult_value.setValue(float(self._viewmodel.get_gentec_gui_multiplier()))
        self.connection_gentec_mult_value.blockSignals(False)
        self.connection_gentec_mult_value.valueChanged.connect(self._on_gentec_mult_spin_value_changed)
        self.connection_gentec_mult_value.editingFinished.connect(self._on_gentec_mult_spin_editing_finished)
        gentec_mult_conn_row.addWidget(self.connection_gentec_mult_value, 1)
        readings_inner.addLayout(gentec_mult_conn_row)
        readings_inner.addWidget(QLabel("Thorlabs Power"))
        thorlabs_power_row = QHBoxLayout()
        self.thorlabs_power_label = QLabel("—")
        self.thorlabs_power_label.setStyleSheet(value_style)
        thorlabs_power_row.addWidget(self.thorlabs_power_label)
        self.thorlabs_power_unit_label = QLabel("mW")
        thorlabs_power_row.addWidget(self.thorlabs_power_unit_label)
        readings_inner.addLayout(thorlabs_power_row)
        thorlabs_mult_conn_row = QHBoxLayout()
        thorlabs_mult_conn_row.addWidget(QLabel("Thorlabs Mult (×)"))
        self.connection_thorlabs_mult_value = QDoubleSpinBox()
        self.connection_thorlabs_mult_value.setStyleSheet(
            theme_main_tab_gentec_mult_spin_qss(t_m, spx(4), spx(6), spx(22), spx(12))
        )
        self.connection_thorlabs_mult_value.setMinimumWidth(72)
        self.connection_thorlabs_mult_value.setRange(float(THORLABS_GUI_MULT_MIN), float(THORLABS_GUI_MULT_MAX))
        self.connection_thorlabs_mult_value.setDecimals(6)
        self.connection_thorlabs_mult_value.setSingleStep(0.01)
        self.connection_thorlabs_mult_value.setKeyboardTracking(True)
        self.connection_thorlabs_mult_value.setToolTip(
            "Same as Main tab — scales Thorlabs power everywhere. Editable; saved when you press Enter or leave the field."
        )
        self.connection_thorlabs_mult_value.blockSignals(True)
        self.connection_thorlabs_mult_value.setValue(float(self._viewmodel.get_thorlabs_gui_multiplier()))
        self.connection_thorlabs_mult_value.blockSignals(False)
        self.connection_thorlabs_mult_value.valueChanged.connect(self._on_thorlabs_mult_spin_value_changed)
        self.connection_thorlabs_mult_value.editingFinished.connect(self._on_thorlabs_mult_spin_editing_finished)
        thorlabs_mult_conn_row.addWidget(self.connection_thorlabs_mult_value, 1)
        readings_inner.addLayout(thorlabs_mult_conn_row)
        readings_inner.addWidget(QLabel("Powermeter λ (read from instrument)"))
        pm_wl_read_row = QHBoxLayout()
        pm_wl_read_row.setSpacing(6)
        pm_wl_read_row.addWidget(QLabel("Thorlabs:"))
        self._manual_thorlabs_wl_read_label = QLabel("—")
        self._manual_thorlabs_wl_read_label.setStyleSheet(value_style)
        pm_wl_read_row.addWidget(self._manual_thorlabs_wl_read_label)
        pm_wl_read_row.addWidget(QLabel("nm"))
        readings_inner.addLayout(pm_wl_read_row)
        pm_read_btn_row = QHBoxLayout()
        pm_read_wl_btn = QPushButton("Read λ")
        self._manual_read_wavelength_btn = pm_read_wl_btn
        pm_read_wl_btn.setStyleSheet(theme_manual_read_wavelength_btn_qss(t_m))
        pm_read_wl_btn.setToolTip(
            "Query Thorlabs calibration wavelength (SENS:CORR:WAV?); adjust the field below and Apply λ to change."
        )
        pm_read_wl_btn.clicked.connect(self._on_manual_powermeter_wavelength_read)
        pm_read_btn_row.addWidget(pm_read_wl_btn)
        pm_read_btn_row.addStretch(1)
        readings_inner.addLayout(pm_read_btn_row)
        readings_inner.addWidget(QLabel("Powermeter λ (nm) — set then Apply"))
        pm_wl_row = QHBoxLayout()
        pm_wl_row.setSpacing(6)
        self._manual_pm_wavelength_spin = QDoubleSpinBox()
        self._manual_pm_wavelength_spin.setStyleSheet(spin_style)
        self._manual_pm_wavelength_spin.setMinimumWidth(88)
        self._manual_pm_wavelength_spin.setRange(400.0, 1700.0)
        self._manual_pm_wavelength_spin.setDecimals(2)
        self._manual_pm_wavelength_spin.setKeyboardTracking(False)
        self._manual_pm_wavelength_spin.setValue(1310.0)
        self._manual_pm_wavelength_spin.setToolTip(
            "Wavelength sent to Gentec (*PWM) and Thorlabs (SENS:CORR:WAV). Use Apply; during a test run the recipe wavelength is applied automatically."
        )
        pm_wl_row.addWidget(self._manual_pm_wavelength_spin, 1)
        pm_wl_apply_btn = QPushButton("Apply λ")
        pm_wl_apply_btn.setStyleSheet(
            "QPushButton { background-color: #2196F3; color: white; font-size: 11px; padding: 4px 8px; } "
            "QPushButton:hover { background-color: #1976D2; }"
        )
        pm_wl_apply_btn.setToolTip("Set this wavelength on connected Gentec and Thorlabs powermeters.")
        pm_wl_apply_btn.clicked.connect(self._on_manual_powermeter_wavelength_apply)
        pm_wl_row.addWidget(pm_wl_apply_btn)
        readings_inner.addLayout(pm_wl_row)
        for lbl in readings_box.findChildren(QLabel):
            lbl.setStyleSheet(read_style)
        self.gentec_power_label.setStyleSheet(value_style)
        self.thorlabs_power_label.setStyleSheet(value_style)
        self._manual_thorlabs_wl_read_label.setStyleSheet(value_style)
        row.addWidget(readings_box, 1, QtCompat.AlignTop)
        # Ando — full width below the top row; controls in horizontal strips (under Arroyo column visually)
        ando_box = QGroupBox("Ando")
        ando_box.setMinimumWidth(400)
        ando_box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        ando_box.setStyleSheet(box_style)
        ando_inner = QVBoxLayout(ando_box)
        ando_inner.setSpacing(8)
        ando_inner.setContentsMargins(10, 8, 10, 8)
        line_ando = theme_engineer_lineedit_ando_qss(t_m)
        ando_row_meas = QHBoxLayout()
        ando_row_meas.setSpacing(12)

        def _ando_labeled_field(title: str, edit: QLineEdit, unit: str) -> QVBoxLayout:
            col = QVBoxLayout()
            col.setSpacing(2)
            col.addWidget(QLabel(title))
            hr = QHBoxLayout()
            hr.setSpacing(6)
            hr.addWidget(edit, 1)
            hr.addWidget(QLabel(unit))
            col.addLayout(hr)
            return col

        self.ando_center_edit = QLineEdit()
        self.ando_center_edit.setStyleSheet(line_ando)
        self.ando_center_edit.setMinimumWidth(72)
        self.ando_center_edit.setPlaceholderText("")
        self.ando_center_edit.setValidator(QDoubleValidator(600, 1750, 2))
        self.ando_center_edit.setMaxLength(8)
        self.ando_center_edit.editingFinished.connect(self._on_ando_center)
        w_c = QWidget()
        w_c.setLayout(_ando_labeled_field("Center", self.ando_center_edit, "nm"))
        ando_row_meas.addWidget(w_c, 1)

        self.ando_span_edit = QLineEdit()
        self.ando_span_edit.setStyleSheet(line_ando)
        self.ando_span_edit.setMinimumWidth(72)
        self.ando_span_edit.setValidator(QDoubleValidator(0, 1200, 2))
        self.ando_span_edit.setMaxLength(8)
        self.ando_span_edit.editingFinished.connect(self._on_ando_span)
        w_s = QWidget()
        w_s.setLayout(_ando_labeled_field("Span", self.ando_span_edit, "nm"))
        ando_row_meas.addWidget(w_s, 1)

        self.ando_ref_level_edit = QLineEdit()
        self.ando_ref_level_edit.setStyleSheet(line_ando)
        self.ando_ref_level_edit.setMinimumWidth(72)
        self.ando_ref_level_edit.setValidator(QDoubleValidator(-90, 20, 1))
        self.ando_ref_level_edit.setMaxLength(6)
        self.ando_ref_level_edit.editingFinished.connect(self._on_ando_ref_level)
        w_r = QWidget()
        w_r.setLayout(_ando_labeled_field("Ref Level", self.ando_ref_level_edit, "dBm"))
        ando_row_meas.addWidget(w_r, 1)

        self.ando_log_scale_edit = QLineEdit()
        self.ando_log_scale_edit.setStyleSheet(line_ando)
        self.ando_log_scale_edit.setMinimumWidth(72)
        self.ando_log_scale_edit.setValidator(QDoubleValidator(0, 10, 1))
        self.ando_log_scale_edit.setMaxLength(5)
        self.ando_log_scale_edit.editingFinished.connect(self._on_ando_log_scale)
        w_l = QWidget()
        w_l.setLayout(_ando_labeled_field("Log Scale (0=lin)", self.ando_log_scale_edit, "dB/DIV"))
        ando_row_meas.addWidget(w_l, 1)

        self.ando_resolution_edit = QLineEdit()
        self.ando_resolution_edit.setStyleSheet(line_ando)
        self.ando_resolution_edit.setMinimumWidth(72)
        self.ando_resolution_edit.setValidator(QDoubleValidator(0.01, 2.0, 2))
        self.ando_resolution_edit.setMaxLength(6)
        self.ando_resolution_edit.editingFinished.connect(self._on_ando_resolution)
        w_res = QWidget()
        w_res.setLayout(_ando_labeled_field("Resolution", self.ando_resolution_edit, "nm"))
        ando_row_meas.addWidget(w_res, 1)

        ando_inner.addLayout(ando_row_meas)
        ando_row_ctrl = QHBoxLayout()
        ando_row_ctrl.setSpacing(12)
        sens_col = QVBoxLayout()
        sens_col.setSpacing(2)
        sens_col.addWidget(QLabel("Best Sensitivity"))
        self.ando_sensitivity_combo = QComboBox()
        self.ando_sensitivity_combo.setStyleSheet(theme_engineer_combo_ando_qss(t_m, font_px=12))
        self.ando_sensitivity_combo.addItems([
            "Normal range auto", "Normal range hold", "Mid", "High1", "High2", "High3"
        ])
        self.ando_sensitivity_combo.currentIndexChanged[int].connect(self._on_ando_sensitivity)
        sens_col.addWidget(self.ando_sensitivity_combo)
        w_se = QWidget()
        w_se.setLayout(sens_col)
        ando_row_ctrl.addWidget(w_se, 1)
        ana_col = QVBoxLayout()
        ana_col.setSpacing(2)
        ana_col.addWidget(QLabel("Analysis"))
        analysis_row = QHBoxLayout()
        self.ando_dfb_btn = QPushButton("DFB LD")
        self.ando_dfb_btn.setStyleSheet(btn_style_off)
        self.ando_dfb_btn.clicked.connect(self._on_ando_analysis_dfb)
        self.ando_led_btn = QPushButton("LED")
        self.ando_led_btn.setStyleSheet(btn_style_off)
        self.ando_led_btn.clicked.connect(self._on_ando_analysis_led)
        analysis_row.addWidget(self.ando_dfb_btn)
        analysis_row.addWidget(self.ando_led_btn)
        ana_col.addLayout(analysis_row)
        w_an = QWidget()
        w_an.setLayout(ana_col)
        ando_row_ctrl.addWidget(w_an, 1)
        sw_col = QVBoxLayout()
        sw_col.setSpacing(2)
        sw_col.addWidget(QLabel("Sweep"))
        sweep_row = QHBoxLayout()
        ando_sweep_btn_min_w = 52
        self.ando_sweep_auto_btn = QPushButton("Auto")
        self.ando_sweep_auto_btn.setStyleSheet(btn_style_off)
        self.ando_sweep_auto_btn.setMinimumWidth(ando_sweep_btn_min_w)
        self.ando_sweep_auto_btn.clicked.connect(self._on_ando_sweep_auto)
        self.ando_sweep_single_btn = QPushButton("Single")
        self.ando_sweep_single_btn.setStyleSheet(btn_style_off)
        self.ando_sweep_single_btn.setMinimumWidth(ando_sweep_btn_min_w)
        self.ando_sweep_single_btn.clicked.connect(self._on_ando_sweep_single)
        self.ando_sweep_repeat_btn = QPushButton("Repeat")
        self.ando_sweep_repeat_btn.setStyleSheet(btn_style_off)
        self.ando_sweep_repeat_btn.setMinimumWidth(ando_sweep_btn_min_w)
        self.ando_sweep_repeat_btn.clicked.connect(self._on_ando_sweep_repeat)
        self.ando_sweep_stop_btn = QPushButton("Stop")
        self.ando_sweep_stop_btn.setObjectName("btn_ando_stop")
        self.ando_sweep_stop_btn.setStyleSheet(btn_style_off)
        self.ando_sweep_stop_btn.setMinimumWidth(ando_sweep_btn_min_w)
        self.ando_sweep_stop_btn.clicked.connect(self._on_ando_sweep_stop)
        for _sb in (self.ando_sweep_auto_btn, self.ando_sweep_single_btn,
                    self.ando_sweep_repeat_btn, self.ando_sweep_stop_btn):
            _sb.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        sweep_row.addWidget(self.ando_sweep_auto_btn, 1)
        sweep_row.addWidget(self.ando_sweep_single_btn, 1)
        sweep_row.addWidget(self.ando_sweep_repeat_btn, 1)
        sweep_row.addWidget(self.ando_sweep_stop_btn, 1)
        sw_col.addLayout(sweep_row)
        w_sw = QWidget()
        w_sw.setLayout(sw_col)
        ando_row_ctrl.addWidget(w_sw, 2)
        ando_inner.addLayout(ando_row_ctrl)
        for lbl in ando_box.findChildren(QLabel):
            lbl.setStyleSheet(read_style)
        content_layout.addLayout(row)
        content_layout.addWidget(ando_box)
        vbox.addWidget(content, 0, QtCompat.AlignTop)
        self._eng_gb_arroyo = arroyo_box
        self._eng_gb_actuator = act_box
        self._eng_gb_prm = prm_box
        self._eng_gb_ando = ando_box
        self._eng_gb_readings = readings_box
        self._eng_gb_wavemeter = wavemeter_box
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
        _t_f = self._tt()
        self.footer_status_label.setStyleSheet(
            f"background: transparent; color: {_t_f.text}; font-size: 12px;"
        )
        self.footer_status_label.setWordWrap(True)
        self.footer_status_label.setMinimumWidth(0)
        self.footer_status_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        layout.addWidget(self.footer_status_label, 1)
        layout.addStretch()
        # Small status before Disconnect All: "Connecting..." while any device is connecting; empty when idle
        self.footer_connecting_label = QLabel("")
        self.footer_connecting_label.setStyleSheet("background: transparent; color: #ff9800; font-size: 12px; font-weight: bold;")
        self.footer_connecting_label.setMinimumWidth(0)
        layout.addWidget(self.footer_connecting_label, 0)
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
        self.footer_frame.setMinimumHeight(40)
        self.footer_frame.setMaximumHeight(96)
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
            if hasattr(self, "main_gentec_power_value"):
                self.main_gentec_power_value.setText("—")
        if not full.get("Thorlabs", False):
            self.thorlabs_power_label.setText("—")
            if hasattr(self, "thorlabs_power_unit_label"):
                self.thorlabs_power_unit_label.setText("mW")
            if hasattr(self, "main_thorlabs_power_value"):
                self.main_thorlabs_power_value.setText("—")
            if hasattr(self, "main_thorlabs_power_unit_label"):
                self.main_thorlabs_power_unit_label.setText("mW")
            if hasattr(self, "_manual_thorlabs_wl_read_label"):
                self._manual_thorlabs_wl_read_label.setText("—")
        if not full.get("Wavemeter", False):
            self.wavemeter_wavelength_label.setText("—")

    @staticmethod
    def _gentec_mw_from_payload(payload):
        """None, or (mW, _) tuple from Gentec worker — mW already includes gui multiplier."""
        if payload is None:
            return None
        if isinstance(payload, (tuple, list)) and len(payload) >= 1:
            v = payload[0]
            return None if v is None else float(v)
        try:
            return float(cast(Any, payload))
        except (TypeError, ValueError):
            return None

    def _on_gentec_reading_updated(self, payload):
        """Same Gentec stream as Connection tab + Main tab; payload is None or (power_mW, _). Power is scaled by Gentec Mult."""
        mw = self._gentec_mw_from_payload(payload)

        if mw is None:
            self.gentec_power_label.setText("—")
            if hasattr(self, "main_gentec_power_value"):
                self.main_gentec_power_value.setText("—")
        else:
            s = format_power_mw_display(mw)
            self.gentec_power_label.setText(s)
            if hasattr(self, "main_gentec_power_value"):
                self.main_gentec_power_value.setText(s)
        # Forward live Gentec reading to Alignment window readout.
        align_w = getattr(self, "_alignment_window", None)
        if align_w is not None and align_w.isVisible() and hasattr(align_w, "_on_gentec_reading_updated"):
            try:
                align_w._on_gentec_reading_updated(payload)
            except Exception:
                pass

    def _sync_gentec_mult_spinboxes(self, v: float, sender: Any = None) -> None:
        """Keep Main tab and Connection tab Gentec Mult spinboxes in sync (``sender`` is excluded to avoid signal noise)."""
        for w in (getattr(self, "main_gentec_mult_value", None), getattr(self, "connection_gentec_mult_value", None)):
            if w is None or w is sender:
                continue
            w.blockSignals(True)
            w.setValue(float(v))
            w.blockSignals(False)

    def _sync_thorlabs_mult_spinboxes(self, v: float, sender: Any = None) -> None:
        """Keep Main tab and Connection tab Thorlabs Mult spinboxes in sync."""
        for w in (getattr(self, "main_thorlabs_mult_value", None), getattr(self, "connection_thorlabs_mult_value", None)):
            if w is None or w is sender:
                continue
            w.blockSignals(True)
            w.setValue(float(v))
            w.blockSignals(False)

    def _on_gentec_mult_spin_value_changed(self, v: float):
        self._viewmodel.set_gentec_gui_multiplier(v, persist=False)
        self._sync_gentec_mult_spinboxes(v, self.sender())
        if self._viewmodel.get_connection_state().get("Gentec"):
            self._viewmodel.request_gentec_read()

    def _on_gentec_mult_spin_editing_finished(self):
        w = self.sender()
        if isinstance(w, QDoubleSpinBox):
            v = float(w.value())
        elif hasattr(self, "main_gentec_mult_value"):
            v = float(self.main_gentec_mult_value.value())
        else:
            return
        self._viewmodel.set_gentec_gui_multiplier(v, persist=True)
        self._sync_gentec_mult_spinboxes(float(self._viewmodel.get_gentec_gui_multiplier()), None)

    def _on_thorlabs_mult_spin_value_changed(self, v: float):
        self._viewmodel.set_thorlabs_gui_multiplier(v, persist=False)
        self._sync_thorlabs_mult_spinboxes(v, self.sender())
        if self._viewmodel.get_connection_state().get("Thorlabs"):
            self._viewmodel.request_thorlabs_read()

    def _on_thorlabs_mult_spin_editing_finished(self):
        w = self.sender()
        if isinstance(w, QDoubleSpinBox):
            v = float(w.value())
        elif hasattr(self, "main_thorlabs_mult_value"):
            v = float(self.main_thorlabs_mult_value.value())
        else:
            return
        self._viewmodel.set_thorlabs_gui_multiplier(v, persist=True)
        self._sync_thorlabs_mult_spinboxes(float(self._viewmodel.get_thorlabs_gui_multiplier()), None)
        if self._viewmodel.get_connection_state().get("Thorlabs"):
            self._viewmodel.request_thorlabs_read()

    def _on_thorlabs_reading_updated(self, value_mw):
        s = format_thorlabs_power_mw_display(value_mw)
        u = thorlabs_power_display_unit(value_mw)
        self.thorlabs_power_label.setText(s)
        if hasattr(self, "thorlabs_power_unit_label"):
            self.thorlabs_power_unit_label.setText(u)
        if hasattr(self, "main_thorlabs_power_value"):
            self.main_thorlabs_power_value.setText(s)
        if hasattr(self, "main_thorlabs_power_unit_label"):
            self.main_thorlabs_power_unit_label.setText(u)
        # Forward live Thorlabs reading to Alignment window readout.
        align_w = getattr(self, "_alignment_window", None)
        if align_w is not None and align_w.isVisible() and hasattr(align_w, "_on_thorlabs_reading_updated"):
            try:
                align_w._on_thorlabs_reading_updated(value_mw)
            except Exception:
                pass
        # Forward to LIV window if open (Thorlabs poll stays alive during LIV).
        liv_w = getattr(self, "_liv_test_window", None)
        if liv_w is not None and hasattr(liv_w, "on_thorlabs_reading_from_main"):
            try:
                liv_w.on_thorlabs_reading_from_main(value_mw)
            except Exception:
                pass

    def _on_liv_power_reading_for_main(self, gentec_mw: float, thorlabs_mw: float):
        """Receive live Gentec readings from LIV sweep and show on main tab + alignment.

        During LIV the Gentec poll timer is paused (serial contention), but the
        sweep still reads Gentec at each step.  Forward those readings to every
        label that normally shows the Gentec value.
        """
        if gentec_mw is not None and gentec_mw > 0:
            s = format_power_mw_display(gentec_mw)
            if hasattr(self, "gentec_power_label"):
                self.gentec_power_label.setText(s)
            if hasattr(self, "main_gentec_power_value"):
                self.main_gentec_power_value.setText(s)
            align_w = getattr(self, "_alignment_window", None)
            if align_w is not None and align_w.isVisible() and hasattr(align_w, "_on_gentec_reading_updated"):
                try:
                    align_w._on_gentec_reading_updated((float(gentec_mw), "W"))
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
                self._refresh_plot_tab_liv_full(getattr(self, "_last_liv_result", None))
                self._refresh_plot_tab_per_results(getattr(self, "_last_per_result", None))
                self._refresh_plot_tab_stability()
                self._refresh_plot_tab_spectrum()
            if self.tabs.tabText(_index) == "Result":
                self._safe_refresh_summary_tab_from_cached_results()
                self._apply_all_cached_results_to_result_tab()
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
        btn_off = theme_engineer_btn_off_qss(self._tt(), pv=6, ph=12, fs=12)
        btn_on = "QPushButton { background-color: #4caf50; color: white; font-size: 12px; padding: 6px 12px; } QPushButton:hover { background-color: #388E3C; }"
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
        if not desired and self._is_test_sequence_busy():
            self._on_status_log_message(
                "Laser OFF ignored: a test sequence is running. Press Stop on the main tab to abort, then you can turn the laser off."
            )
            try:
                self._arroyo_update_laser_tec_ui()
            except Exception:
                pass
            return
        if desired:
            self._on_status_log_message("Laser ON: enabling TEC if needed, then laser (instrument readback).")
        self._viewmodel.set_arroyo_laser_output(desired)

    def _on_arroyo_tec_clicked(self):
        """Toggle TEC -> worker; UI follows Arroyo readback (same as Main Laser/TEC boxes)."""
        desired = not self._arroyo_tec_on
        if not desired and self._is_test_sequence_busy():
            self._on_status_log_message(
                "TEC OFF ignored: a test sequence is running (TEC powers the laser path). Press Stop on the main tab to abort first."
            )
            try:
                self._arroyo_update_laser_tec_ui()
            except Exception:
                pass
            return
        self._viewmodel.set_arroyo_tec_output(desired)

    def _make_connection_tab(self):
        w = QWidget()
        w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout = QVBoxLayout(w)
        layout.addWidget(QLabel("Instruments — Ports"))
        # Scan All / Connect All / Save
        btn_row = QHBoxLayout()
        scan_all_btn = QPushButton("Scan All")
        scan_all_btn.setStyleSheet("QPushButton { background-color: #2196F3; color: white; } QPushButton:hover { background-color: #1976D2; }")
        scan_all_btn.clicked.connect(self._on_scan_all)
        btn_row.addWidget(scan_all_btn)
        connect_all_btn = QPushButton("Connect All")
        connect_all_btn.setStyleSheet("QPushButton { background-color: #4caf50; color: white; } QPushButton:hover { background-color: #388E3C; }")
        connect_all_btn.clicked.connect(lambda: self._on_connect_all())
        btn_row.addWidget(connect_all_btn)
        save_btn = QPushButton("Save")
        save_btn.setStyleSheet("QPushButton { background-color: #FF9800; color: white; } QPushButton:hover { background-color: #F57C00; }")
        save_btn.clicked.connect(self._on_save_connections)
        btn_row.addWidget(save_btn)
        self.connection_scan_status_label = QLabel("Ready")
        self.connection_scan_status_label.setStyleSheet(
            "color: #81c784; font-weight: bold; font-size: 12px; min-width: 128px; padding-left: 12px;"
        )
        btn_row.addWidget(self.connection_scan_status_label)
        btn_row.addStretch()
        layout.addLayout(btn_row)
        grid = QGridLayout()
        # Arroyo — COM only (same physical list as Actuator/Gentec scans; pick the port for this instrument)
        arroyo_lbl = QLabel("Arroyo (serial COM)")
        grid.addWidget(arroyo_lbl, 0, 0)
        self.available_ports_combo = QComboBox()
        self.available_ports_combo.setMinimumWidth(120)
        grid.addWidget(self.available_ports_combo, 0, 1)
        scan_btn = QPushButton("Scan COM")
        scan_btn.setObjectName("btn_scan")
        scan_btn.setMinimumWidth(108)
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
        grid.addWidget(act_lbl, 1, 0)
        self.actuator_ports_combo = QComboBox()
        self.actuator_ports_combo.setMinimumWidth(120)
        grid.addWidget(self.actuator_ports_combo, 1, 1)
        scan_act_btn = QPushButton("Scan COM")
        scan_act_btn.setObjectName("btn_scan_actuator")
        scan_act_btn.setMinimumWidth(108)
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
        grid.addWidget(ando_lbl, 2, 0)
        self.available_gpib_combo = QComboBox()
        self.available_gpib_combo.setMinimumWidth(180)
        self.available_gpib_combo.setEditable(True)
        grid.addWidget(self.available_gpib_combo, 2, 1)
        scan_gpib_btn = QPushButton("Scan GPIB")
        scan_gpib_btn.setObjectName("btn_scan_gpib")
        scan_gpib_btn.setMinimumWidth(108)
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
        grid.addWidget(wm_lbl, 3, 0)
        self.wavemeter_gpib_combo = QComboBox()
        self.wavemeter_gpib_combo.setMinimumWidth(180)
        self.wavemeter_gpib_combo.setEditable(False)
        grid.addWidget(self.wavemeter_gpib_combo, 3, 1)
        scan_wm_btn = QPushButton("Scan GPIB")
        scan_wm_btn.setMinimumWidth(108)
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
        grid.addWidget(prm_lbl, 4, 0)
        self.prm_serial_combo = QComboBox()
        self.prm_serial_combo.setMinimumWidth(120)
        self.prm_serial_combo.setEditable(True)
        grid.addWidget(self.prm_serial_combo, 4, 1)
        scan_prm_btn = QPushButton("Scan Kinesis")
        scan_prm_btn.setMinimumWidth(108)
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
        grid.addWidget(g_lbl, 5, 0)
        self.gentec_ports_combo = QComboBox()
        self.gentec_ports_combo.setMinimumWidth(120)
        # Editable: type any port (COM3, COM12, \\\\.\\COM15) before Scan finishes; that exact string is used to connect.
        self.gentec_ports_combo.setEditable(True)
        grid.addWidget(self.gentec_ports_combo, 5, 1)
        scan_gentec_btn = QPushButton("Scan COM")
        scan_gentec_btn.setMinimumWidth(108)
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
        grid.addWidget(tl_lbl, 6, 0)
        self.thorlabs_visa_combo = QComboBox()
        self.thorlabs_visa_combo.setMinimumWidth(180)
        self.thorlabs_visa_combo.setEditable(True)
        grid.addWidget(self.thorlabs_visa_combo, 6, 1)
        scan_thorlabs_btn = QPushButton("Scan Thorlabs")
        scan_thorlabs_btn.setMinimumWidth(108)
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
            "Status next to Save shows <b>Scanning…</b> (orange) while a scan runs and <b>Ready</b> (green) when idle — "
            "Connect/Scan buttons are disabled during scans so the GUI stays responsive. "
            "Each Scan button only refreshes that row: <b>Scan COM</b> — serial ports; "
            "<b>Scan GPIB</b> — GPIB VISA addresses; <b>Scan Kinesis</b> — PRM serials; "
            "<b>Scan Thorlabs</b> — USB powermeters (Thorlabs VID). "
            "<b>Scan All</b> runs every detector and fills each combo with the matching resource type."
        )
        conn_hint.setWordWrap(True)
        conn_hint.setTextFormat(QtCompat.RichText)
        conn_hint.setStyleSheet("background: transparent; color: #aaaaaa; font-size: 11px; padding: 6px 2px 0 2px;")
        layout.addWidget(conn_hint)
        layout.addStretch()
        # Saved addresses + background scan run from _complete_heavy_startup (after first paint), not here.
        self._connection_tab_saved_applied = False
        self._connection_scan_lock_widgets = [
            scan_all_btn,
            connect_all_btn,
            save_btn,
            scan_btn,
            connect_btn,
            disconnect_btn,
            scan_act_btn,
            connect_act_btn,
            disconnect_act_btn,
            scan_gpib_btn,
            connect_ando_btn,
            disconnect_ando_btn,
            scan_wm_btn,
            connect_wm_btn,
            disconnect_wm_btn,
            scan_prm_btn,
            connect_prm_btn,
            disconnect_prm_btn,
            scan_gentec_btn,
            connect_gentec_btn,
            disconnect_gentec_btn,
            scan_thorlabs_btn,
            connect_thorlabs_btn,
            disconnect_thorlabs_btn,
        ]
        return w

    def _make_engineer_control_tab(self) -> QWidget:
        """Engineer Control: nested tabs — Manual Control and Connection (instruments / ports)."""
        outer = QWidget()
        outer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        lay = QVBoxLayout(outer)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        inner = QTabWidget()
        inner.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        inner.setObjectName("engineerControlInnerTabs")
        inner.setDocumentMode(True)
        inner.setStyleSheet(
            "QTabWidget::pane {{ background-color: {}; }}".format(theme_chrome_bg(self._dark_theme_enabled))
        )
        _eng_tb = NaturalWidthTabBar(inner)
        _eng_tb.setExpanding(False)
        _eng_tb.setElideMode(QtCompat.ElideNone)  # type: ignore[attr-defined]
        _eng_tb.setUsesScrollButtons(True)
        inner.setTabBar(_eng_tb)
        inner.addTab(self._make_manual_control_tab(), "Manual Control")
        inner.addTab(self._make_connection_tab(), "Connection")
        inner.setCurrentIndex(0)
        self._engineer_control_inner_tabs = inner
        lay.addWidget(inner, 1)
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

    _ANDO_STOP_RED = (
        "QPushButton { background-color: #f44336; color: white; } "
        "QPushButton:hover { background-color: #d32f2f; }"
    )

    def _set_ando_sweep_running(self, running: bool) -> None:
        self._ando_sweep_running = bool(running)
        if hasattr(self, "ando_sweep_stop_btn"):
            self.ando_sweep_stop_btn.setStyleSheet(
                self._ANDO_STOP_RED if running else theme_ando_stop_idle_qss(self._tt())
            )

    def _on_ando_sweep_auto(self):
        self._viewmodel.set_ando_sweep_auto()
        self._set_ando_sweep_running(True)

    def _on_ando_sweep_single(self):
        self._viewmodel.set_ando_sweep_single()
        self._set_ando_sweep_running(True)

    def _on_ando_sweep_repeat(self):
        self._viewmodel.set_ando_sweep_repeat()
        self._set_ando_sweep_running(True)

    def _on_ando_sweep_stop(self):
        self._viewmodel.set_ando_sweep_stop()
        self._set_ando_sweep_running(False)

    def _on_ando_sweep_status_from_instrument(self, sweeping: bool) -> None:
        self._set_ando_sweep_running(sweeping)

    def _restore_saved_com_ports_after_scan(self) -> None:
        """Re-select ALL saved instruments after scan so dropdowns keep previously-saved addresses.

        If the saved address is in the scan results, select it.
        If not, insert it with a '(saved)' suffix so the user can still see/try it.
        """
        try:
            saved = self._viewmodel.load_saved_addresses()
        except Exception:
            return
        if not isinstance(saved, dict):
            return

        _placeholders = {
            "(no ports found)", "(no GPIB found)", "(no devices found)",
            "(no VISA found)", "(no Thorlabs / VISA found)",
            "(loading COM list…)", "(loading GPIB list…)",
            "(loading Thorlabs / VISA…)",
        }

        def pick(combo, key: str) -> None:
            val = (saved.get(key) or "").strip()
            if not val or val in _placeholders:
                return
            i = combo.findText(val)
            if i >= 0:
                combo.setCurrentIndex(i)
            else:
                combo.insertItem(0, "{} (saved)".format(val))
                combo.setCurrentIndex(0)

        pick(self.available_ports_combo, "arroyo_port")
        pick(self.actuator_ports_combo, "actuator_port")
        pick(self.gentec_ports_combo, "gentec_port")
        pick(self.available_gpib_combo, "ando_gpib")
        pick(self.wavemeter_gpib_combo, "wavemeter_gpib")
        pick(self.prm_serial_combo, "prm_serial")
        pick(self.thorlabs_visa_combo, "thorlabs_visa")

    @staticmethod
    def _com_port_key_ui(port: str) -> str:
        """Normalize COM / \\\\.\\COMn for comparison (Arroyo vs Actuator must not share)."""
        p = (port or "").strip().upper()
        if p.startswith("\\\\.\\"):
            p = p[4:]
        return p

    def _arroyo_port_for_connect(self) -> str:
        """
        Use the Arroyo row combo first (what you selected). Fall back to Save Connections only if
        the combo is empty or a placeholder — so Gentec / Actuator rows are not tied to INI over the UI.
        """
        combo = self.available_ports_combo.currentText().strip()
        if _com_combo_text_is_usable_port(combo):
            return combo
        try:
            saved = self._viewmodel.load_saved_addresses()
        except Exception:
            saved = {}
        s = (saved.get("arroyo_port") or "").strip() if isinstance(saved, dict) else ""
        if s and s not in ("(no ports found)",):
            i = self.available_ports_combo.findText(s)
            if i >= 0:
                self.available_ports_combo.setCurrentIndex(i)
            else:
                self.available_ports_combo.insertItem(0, s)
                self.available_ports_combo.setCurrentIndex(0)
            return s
        return ""

    def _actuator_port_for_connect(self) -> str:
        """Actuator row: combo selection first, then saved address — never override a chosen COM with INI."""
        combo = self.actuator_ports_combo.currentText().strip()
        if _com_combo_text_is_usable_port(combo):
            return combo
        try:
            saved = self._viewmodel.load_saved_addresses()
        except Exception:
            saved = {}
        s = (saved.get("actuator_port") or "").strip() if isinstance(saved, dict) else ""
        if s and s not in ("(no ports found)",):
            i = self.actuator_ports_combo.findText(s)
            if i >= 0:
                self.actuator_ports_combo.setCurrentIndex(i)
            else:
                self.actuator_ports_combo.insertItem(0, s)
                self.actuator_ports_combo.setCurrentIndex(0)
            return s
        return ""

    def _gentec_port_for_connect(self) -> str:
        """Gentec row: combo selection first, then saved address — independent of Actuator / Arroyo INI."""
        combo = _normalize_user_com_port(self.gentec_ports_combo.currentText())
        if _com_combo_text_is_usable_port(combo):
            return combo
        try:
            saved = self._viewmodel.load_saved_addresses()
        except Exception:
            saved = {}
        s = _normalize_user_com_port((saved.get("gentec_port") or "") if isinstance(saved, dict) else "")
        if s and s not in ("(no ports found)",):
            i = self.gentec_ports_combo.findText(s)
            if i >= 0:
                self.gentec_ports_combo.setCurrentIndex(i)
            else:
                self.gentec_ports_combo.insertItem(0, s)
                self.gentec_ports_combo.setCurrentIndex(0)
            return s
        return ""

    def _serial_sharing_violation_message(self, connecting: str, port: str) -> str:
        """Windows allows one handle per COM; block if another connected device already uses this port."""
        key = self._com_port_key_ui(port)
        if not key or port == "(no ports found)":
            return ""
        st = self._viewmodel.get_connection_state()
        if connecting == "arroyo":
            other = self._actuator_port_for_connect()
            if other and self._com_port_key_ui(other) == key and st.get("Actuator"):
                return (
                    "Arroyo cannot use {} — the actuator already has that COM open. "
                    "Only one instrument per serial port. Disconnect the actuator or set different "
                    "arroyo_port / actuator_port under Save Connections."
                ).format(port)
            og = self._gentec_port_for_connect()
            if og and self._com_port_key_ui(og) == key and st.get("Gentec"):
                return (
                    "Arroyo cannot use {} — Gentec already has that COM open. "
                    "Disconnect Gentec or pick a different COM for Arroyo."
                ).format(port)
        elif connecting == "actuator":
            other = self._arroyo_port_for_connect()
            if other and self._com_port_key_ui(other) == key and st.get("Arroyo"):
                return (
                    "Actuator cannot use {} — Arroyo already has that COM open. "
                    "Disconnect Arroyo or set a different actuator_port in Save Connections."
                ).format(port)
            og = self._gentec_port_for_connect()
            if og and self._com_port_key_ui(og) == key and st.get("Gentec"):
                return (
                    "Actuator cannot use {} — Gentec already has that COM open. "
                    "Disconnect Gentec or pick a different COM for the actuator."
                ).format(port)
        elif connecting == "gentec":
            oa = self._arroyo_port_for_connect()
            if oa and self._com_port_key_ui(oa) == key and st.get("Arroyo"):
                return (
                    "Gentec cannot use {} — Arroyo already has that COM open. "
                    "Disconnect Arroyo or pick a different COM for Gentec."
                ).format(port)
            ob = self._actuator_port_for_connect()
            if ob and self._com_port_key_ui(ob) == key and st.get("Actuator"):
                return (
                    "Gentec cannot use {} — the actuator already has that COM open. "
                    "Disconnect the actuator or pick a different COM for Gentec."
                ).format(port)
        return ""

    def _connection_scan_set_busy(self, busy: bool, scanning_text: str = "") -> None:
        """Connection tab: disable instrument buttons while a scan runs; show Scanning… / Ready (non-blocking scans)."""
        self._connection_scan_busy = busy
        lab = getattr(self, "connection_scan_status_label", None)
        if lab is not None:
            if busy:
                lab.setText(scanning_text or "Scanning…")
                lab.setStyleSheet(
                    "color: #ffb74d; font-weight: bold; font-size: 12px; min-width: 128px; padding-left: 12px;"
                )
            else:
                lab.setText("Ready")
                lab.setStyleSheet(
                    "color: #81c784; font-weight: bold; font-size: 12px; min-width: 128px; padding-left: 12px;"
                )
        for w in getattr(self, "_connection_scan_lock_widgets", None) or []:
            try:
                w.setEnabled(not busy)
            except Exception:
                pass

    def _start_connection_scan(self, status_label: str, kind: str, work_fn) -> bool:
        """Run work_fn() in a daemon thread; emit {kind, data|error} on _connection_scan_bridge (GUI thread applies)."""
        if self._connection_scan_busy:
            try:
                self.main_status_log.appendPlainText("Connection: scan already in progress — wait for Ready.")
            except Exception:
                pass
            return False
        self._connection_scan_set_busy(True, status_label)
        bridge = self._connection_scan_bridge

        def thread_main():
            pkg: Dict[str, Any] = {"kind": kind}
            try:
                pkg["data"] = work_fn()
            except Exception as e:
                pkg["error"] = e
            bridge.finished.emit(pkg)

        threading.Thread(target=thread_main, daemon=True).start()
        return True

    @pyqtSlot(dict)
    def _on_connection_scan_worker_finished(self, pkg: dict) -> None:
        try:
            err = pkg.get("error")
            if err is not None:
                msg = str(err)
                self.main_status_log.appendPlainText("Connection scan failed ({}): {}".format(pkg.get("kind", ""), msg))
                QMessageBox.warning(self, "Scan", msg)
                return
            kind = pkg.get("kind") or ""
            data = pkg.get("data")
            if kind == "scan_all":
                self._apply_full_scan_all_results(data)
            elif kind == "gpib_ando":
                resources = data if isinstance(data, list) else []
                self.available_gpib_combo.clear()
                self.available_gpib_combo.addItems(resources if resources else ["(no GPIB found)"])
                if resources:
                    self.main_status_log.appendPlainText(
                        "Ando — GPIB: {} resource(s): {}".format(len(resources), ", ".join(resources))
                    )
                else:
                    self.main_status_log.appendPlainText("Ando — GPIB: no GPIB addresses found.")
            elif kind == "gpib_wm":
                resources = data if isinstance(data, list) else []
                self.wavemeter_gpib_combo.clear()
                self.wavemeter_gpib_combo.addItems(resources if resources else ["(no GPIB found)"])
                if resources:
                    self.main_status_log.appendPlainText(
                        "Wavemeter — GPIB: {} resource(s): {}".format(len(resources), ", ".join(resources))
                    )
                else:
                    self.main_status_log.appendPlainText("Wavemeter — GPIB: no GPIB addresses found.")
            elif kind == "com_arroyo":
                self._apply_com_scan_row(data, self.available_ports_combo, "Arroyo", "arroyo_port")
            elif kind == "com_actuator":
                self._apply_com_scan_row(data, self.actuator_ports_combo, "Actuator", "actuator_port")
            elif kind == "com_gentec":
                self._apply_com_scan_row(data, self.gentec_ports_combo, "Gentec", "gentec_port")
            elif kind == "prm":
                self._apply_prm_scan_result(data)
            elif kind == "thorlabs":
                self._apply_thorlabs_scan_result(data)
        finally:
            self._connection_scan_set_busy(False)

    def _apply_com_scan_row(self, ports_obj, combo: QComboBox, log_name: str, saved_key: str) -> None:
        ports = ports_obj if isinstance(ports_obj, list) else []
        combo.clear()
        combo.addItems(ports if ports else ["(no ports found)"])
        if ports:
            self.main_status_log.appendPlainText(
                "{} — COM: {} port(s): {}".format(log_name, len(ports), ", ".join(ports))
            )
        else:
            self.main_status_log.appendPlainText("{} — COM: no serial ports found.".format(log_name))
        try:
            saved = self._viewmodel.load_saved_addresses()
            if isinstance(saved, dict):
                ap = (saved.get(saved_key) or "").strip()
                if ap and ap != "(no ports found)":
                    i = combo.findText(ap)
                    if i >= 0:
                        combo.setCurrentIndex(i)
                    else:
                        combo.insertItem(0, ap)
                        combo.setCurrentIndex(0)
        except Exception:
            pass

    def _apply_prm_scan_result(self, data: object) -> None:
        if not isinstance(data, dict):
            return
        serials = data.get("serials") or []
        ok = data.get("ok", True)
        msg = data.get("msg") or ""
        self.prm_serial_combo.clear()
        if serials:
            self.prm_serial_combo.addItems(serials)
            self.main_status_log.appendPlainText(
                "PRM Scan (Kinesis): {} device(s): {}".format(len(serials), ", ".join(serials))
            )
        else:
            self.prm_serial_combo.addItems(["(no devices found)"])
            line = "PRM Scan (Kinesis): no devices."
            if msg:
                line += " " + msg
            self.main_status_log.appendPlainText(line)
            if not ok and msg:
                QMessageBox.warning(self, "PRM Scan", msg)

    def _apply_thorlabs_scan_result(self, data: object) -> None:
        if not isinstance(data, dict):
            return
        resources = data.get("thorlabs_usb") or []
        visa_list = data.get("visa_list") or []
        self.thorlabs_visa_combo.clear()
        if resources:
            self.thorlabs_visa_combo.addItems(resources)
            self.main_status_log.appendPlainText(
                "Thorlabs scan (USB VID 0x1313): {} device(s): {}".format(
                    len(resources), ", ".join(resources)
                )
            )
        elif visa_list:
            fb = _thorlabs_visa_combo_fallback_list(visa_list)
            if fb:
                self.thorlabs_visa_combo.addItems(fb)
                self.main_status_log.appendPlainText(
                    "Thorlabs USB (0x1313): none. Showing {} non-GPIB VISA resource(s) (GPIB omitted — not Thorlabs)."
                    .format(len(fb))
                )
            else:
                self.thorlabs_visa_combo.addItems(["(no Thorlabs / VISA found)"])
                self.main_status_log.appendPlainText(
                    "Thorlabs USB (0x1313): none; full VISA scan only listed GPIB — use Thorlabs USB or type USB0::… manually."
                )
        else:
            self.thorlabs_visa_combo.addItems(["(no Thorlabs / VISA found)"])
            self.main_status_log.appendPlainText(
                "Thorlabs scan: no USB 0x1313 and no VISA resources (install NI-VISA or use pyvisa-py)."
            )

    def _apply_full_scan_all_results(self, data: object) -> None:
        if not isinstance(data, dict):
            return
        ports = data.get("ports")
        if not isinstance(ports, list):
            ports = []
        gpib = data.get("gpib")
        if not isinstance(gpib, list):
            gpib = []
        prm_serials = data.get("prm_serials")
        if not isinstance(prm_serials, list):
            prm_serials = []
        visa_list = data.get("visa_list")
        if not isinstance(visa_list, list):
            visa_list = []
        thorlabs_usb = data.get("thorlabs_usb")
        if not isinstance(thorlabs_usb, list):
            thorlabs_usb = []
        port_list = ports if ports else ["(no ports found)"]
        self.available_ports_combo.clear()
        self.available_ports_combo.addItems(port_list)
        self.actuator_ports_combo.clear()
        self.actuator_ports_combo.addItems(port_list)
        self.gentec_ports_combo.clear()
        self.gentec_ports_combo.addItems(port_list)
        gpib_list = gpib if gpib else ["(no GPIB found)"]
        self.available_gpib_combo.clear()
        self.available_gpib_combo.addItems(gpib_list)
        self.wavemeter_gpib_combo.clear()
        self.wavemeter_gpib_combo.addItems(gpib_list)
        self.prm_serial_combo.clear()
        if prm_serials:
            self.prm_serial_combo.addItems(prm_serials)
        else:
            self.prm_serial_combo.addItems(["(no devices found)"])
        self.thorlabs_visa_combo.clear()
        if thorlabs_usb:
            self.thorlabs_visa_combo.addItems(thorlabs_usb)
        elif visa_list:
            fb = _thorlabs_visa_combo_fallback_list(visa_list)
            self.thorlabs_visa_combo.addItems(fb if fb else ["(no Thorlabs / VISA found)"])
        else:
            self.thorlabs_visa_combo.addItems(["(no Thorlabs / VISA found)"])
        _log_scan_results(ports, gpib, prm_serials, visa_list, thorlabs_usb)
        prm_status = data.get("prm_status", "")
        lines = ["Scan All results:"]
        lines.append("  COM ports: {}".format(", ".join(ports) if ports else "none"))
        lines.append("  GPIB: {}".format(", ".join(gpib) if gpib else "none"))
        if prm_serials:
            lines.append("  PRM/Kinesis: {}".format(", ".join(prm_serials)))
        elif prm_status:
            lines.append("  PRM/Kinesis: none — {}".format(prm_status))
        else:
            lines.append("  PRM/Kinesis: none")
        lines.append("  Thorlabs USB: {}".format(", ".join(thorlabs_usb) if thorlabs_usb else "none"))
        lines.append("  VISA all: {}".format(", ".join(visa_list) if visa_list else "none"))
        lines.append("Scan All: done.")
        self.main_status_log.appendPlainText("\n".join(lines))
        try:
            self._restore_saved_com_ports_after_scan()
        except Exception:
            pass

    def _on_scan_ports(self):
        vm = self._viewmodel

        def work():
            return vm.scan_ports()

        if not self._start_connection_scan("Scanning COM…", "com_arroyo", work):
            return

    def _on_connect_arroyo(self):
        port = self._arroyo_port_for_connect()
        if not port:
            QMessageBox.warning(
                self,
                "Connection",
                "No Arroyo COM port: run Scan, pick a port, or Save Connections with arroyo_port set.",
            )
            return
        bad = self._serial_sharing_violation_message("arroyo", port)
        if bad:
            QMessageBox.warning(self, "Connection", bad)
            return
        self._set_footer_connecting()
        self._viewmodel.connect_arroyo(port)

    def _on_disconnect_arroyo(self):
        self._viewmodel.disconnect_arroyo()

    def _on_scan_gpib(self):
        vm = self._viewmodel

        def work():
            return vm.scan_gpib()

        self._start_connection_scan("Scanning GPIB…", "gpib_ando", work)

    def _on_connect_ando(self):
        # Prefer saved address first (fast path; no scan required).
        selected = _strip_saved_tag(self.available_gpib_combo.currentText())
        try:
            saved = self._viewmodel.load_saved_addresses()
        except Exception:
            saved = {}
        saved_addr = (saved.get("ando_gpib") or "").strip() if isinstance(saved, dict) else ""

        addr_first = saved_addr or selected
        if not addr_first or addr_first == "(no GPIB found)":
            QMessageBox.warning(self, "Connection", "No Ando GPIB address: Save Connections or run Scan and select one.")
            return

        self._set_footer_connecting()
        self._viewmodel.connect_ando(addr_first)

        # If user selected a different address, fall back to it only if the saved address didn't connect.
        if selected and saved_addr and selected != saved_addr:
            def _fallback():
                try:
                    st = self._viewmodel.get_connection_state()
                except Exception:
                    st = {}
                if not st.get("Ando"):
                    self._set_footer_connecting()
                    self._viewmodel.connect_ando(selected)
            QTimer.singleShot(650, _fallback)

    def _on_disconnect_ando(self):
        self._viewmodel.disconnect_ando()

    def _on_scan_ports_actuator(self):
        vm = self._viewmodel

        def work():
            return vm.scan_ports()

        self._start_connection_scan("Scanning COM…", "com_actuator", work)

    def _on_connect_actuator(self):
        port = self._actuator_port_for_connect()
        if not port:
            QMessageBox.warning(
                self,
                "Connection",
                "No actuator COM port: run Scan, pick a port, or Save Connections with actuator_port set.",
            )
            return
        bad = self._serial_sharing_violation_message("actuator", port)
        if bad:
            QMessageBox.warning(self, "Connection", bad)
            return
        self._set_footer_connecting()
        self._viewmodel.connect_actuator(port)

    def _on_disconnect_actuator(self):
        self._viewmodel.disconnect_actuator()

    def _on_scan_gpib_wavemeter(self):
        vm = self._viewmodel

        def work():
            return vm.scan_gpib()

        self._start_connection_scan("Scanning GPIB…", "gpib_wm", work)

    def _on_connect_wavemeter(self):
        # Prefer saved address first (fast path; no scan required).
        selected = _strip_saved_tag(self.wavemeter_gpib_combo.currentText())
        try:
            saved = self._viewmodel.load_saved_addresses()
        except Exception:
            saved = {}
        saved_addr = (saved.get("wavemeter_gpib") or "").strip() if isinstance(saved, dict) else ""

        addr_first = saved_addr or selected
        if not addr_first or addr_first == "(no GPIB found)":
            QMessageBox.warning(
                self,
                "Connection",
                "No Wavemeter GPIB address: Save Connections or run Scan and select one.",
            )
            return

        self._set_footer_connecting()
        self._viewmodel.connect_wavemeter(addr_first)

        # If user selected a different address, fall back to it only if the saved address didn't connect.
        if selected and saved_addr and selected != saved_addr:
            def _fallback():
                try:
                    st = self._viewmodel.get_connection_state()
                except Exception:
                    st = {}
                if not st.get("Wavemeter"):
                    self._set_footer_connecting()
                    self._viewmodel.connect_wavemeter(selected)
            QTimer.singleShot(650, _fallback)

    def _on_disconnect_wavemeter(self):
        self._viewmodel.disconnect_wavemeter()

    def _on_manual_powermeter_wavelength_apply(self) -> None:
        """Manual Control Readings: send λ via ViewModel → workers → same set_wavelength_nm as CLI test script."""
        sp = getattr(self, "_manual_pm_wavelength_spin", None)
        if sp is None:
            return
        try:
            wl = float(sp.value())
        except (TypeError, ValueError):
            return
        if wl <= 0:
            return
        self._viewmodel.apply_power_meter_wavelength_nm(wl)
        try:
            self._viewmodel.schedule_power_meter_reads_after_laser_change()
        except Exception:
            pass
        try:
            self.main_status_log.appendPlainText(
                "Apply λ: {:.2f} nm — sending to Gentec + Thorlabs (see status log for verify).".format(wl)
            )
        except Exception:
            pass
        QTimer.singleShot(800, self._viewmodel.request_powermeter_wavelength_readbacks)

    @staticmethod
    def _format_manual_powermeter_wavelength_read(v: object) -> str:
        if v is None:
            return "—"
        try:
            x = float(cast(Any, v))
        except (TypeError, ValueError):
            return "—"
        if x != x or x <= 0:
            return "—"
        # Full double precision (no artificial 2-decimal rounding); matches instrument readback.
        return format(x, ".15g")

    def _on_manual_powermeter_wavelength_read(self) -> None:
        self._viewmodel.request_powermeter_wavelength_readbacks()
        try:
            self.main_status_log.appendPlainText("Read λ: querying Thorlabs calibration wavelength...")
        except Exception:
            pass

    def _on_manual_thorlabs_wavelength_read(self, v: object) -> None:
        if hasattr(self, "_manual_thorlabs_wl_read_label"):
            self._manual_thorlabs_wl_read_label.setText(self._format_manual_powermeter_wavelength_read(v))

    def _sync_manual_powermeter_wavelength_spin_from_recipe(self) -> None:
        """Update Manual Control powermeter λ spin from active recipe (after Start Test / load)."""
        sp = getattr(self, "_manual_pm_wavelength_spin", None)
        if sp is None:
            return
        wl = 0.0
        try:
            from operations.recipe_ts_helpers import extract_recipe_wavelength_nm

            d = getattr(self, "_current_recipe_data", None)
            if isinstance(d, dict):
                _w = extract_recipe_wavelength_nm(d)
                wl = float(_w) if _w is not None else 0.0
        except Exception:
            wl = 0.0
        if wl <= 0:
            try:
                w2 = self._get_recipe_wavelength_for_align()
                if w2 is not None and float(w2) > 0:
                    wl = float(w2)
            except Exception:
                wl = 0.0
        if wl <= 0:
            return
        try:
            lo, hi = sp.minimum(), sp.maximum()
            wv = min(max(wl, lo), hi)
            sp.blockSignals(True)
            sp.setValue(wv)
            sp.blockSignals(False)
        except Exception:
            pass

    def _on_apply_wavemeter_range(self):
        r = self.wavemeter_range_combo.currentText().strip()
        state = self._viewmodel.get_connection_state()
        if not state.get("Wavemeter"):
            self.main_status_log.appendPlainText("Wavemeter not connected. Connect wavemeter first, then Apply range.")
            return
        self.main_status_log.appendPlainText("Applying wavemeter range: {}.".format(r))
        self._viewmodel.apply_wavemeter_range(r)

    def _on_scan_prm(self):
        vm = self._viewmodel

        def work():
            serials = vm.scan_prm()
            ok, msg = vm.get_prm_scan_status()
            return {"serials": serials or [], "ok": ok, "msg": msg or ""}

        self._start_connection_scan("Scanning Kinesis…", "prm", work)

    def _on_connect_prm(self):
        raw_combo = _strip_saved_tag(self.prm_serial_combo.currentText())
        try:
            saved = self._viewmodel.load_saved_addresses()
        except Exception:
            saved = {}
        saved_sn = (saved.get("prm_serial") or "").strip() if isinstance(saved, dict) else ""
        raw = raw_combo if (raw_combo and raw_combo != "(no devices found)") else saved_sn
        if not raw or raw == "(no devices found)":
            QMessageBox.warning(self, "Connection", "Select a PRM serial or Save Connections with prm_serial.")
            return
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
        vm = self._viewmodel

        def work():
            return vm.scan_ports()

        self._start_connection_scan("Scanning COM…", "com_gentec", work)

    def _on_connect_gentec(self):
        port = self._gentec_port_for_connect()
        if not port:
            QMessageBox.warning(
                self,
                "Connection",
                "No Gentec COM port: run Scan COM, pick or type a port (e.g. COM3, COM12, \\\\.\\COM15), "
                "or Save Connections with gentec_port set.",
            )
            return
        bad = self._serial_sharing_violation_message("gentec", port)
        if bad:
            QMessageBox.warning(self, "Connection", bad)
            return
        self._set_footer_connecting()
        self._viewmodel.connect_gentec(port)
    def _on_disconnect_gentec(self):
        self._viewmodel.disconnect_gentec()

    def _on_scan_visa_thorlabs(self):
        vm = self._viewmodel

        def work():
            thorlabs_usb = vm.scan_thorlabs_powermeters() or []
            if thorlabs_usb:
                return {"thorlabs_usb": thorlabs_usb, "visa_list": []}
            return {"thorlabs_usb": [], "visa_list": vm.scan_visa() or []}

        self._start_connection_scan("Scanning Thorlabs / VISA…", "thorlabs", work)

    def _on_connect_thorlabs(self):
        selected = _strip_saved_tag(self.thorlabs_visa_combo.currentText())
        try:
            saved = self._viewmodel.load_saved_addresses()
        except Exception:
            saved = {}
        saved_v = (saved.get("thorlabs_visa") or "").strip() if isinstance(saved, dict) else ""
        visa_first = saved_v or selected
        if not visa_first or visa_first in ("(no VISA found)", "(no Thorlabs / VISA found)"):
            QMessageBox.warning(
                self,
                "Connection",
                "No Thorlabs VISA resource: Save Connections or run Scan and select one.",
            )
            return
        self._set_footer_connecting()
        self._viewmodel.connect_thorlabs(visa_first)
        if selected and saved_v and selected != saved_v:
            def _fallback():
                try:
                    st = self._viewmodel.get_connection_state()
                except Exception:
                    st = {}
                if not st.get("Thorlabs"):
                    self._set_footer_connecting()
                    self._viewmodel.connect_thorlabs(selected)
            QTimer.singleShot(900, _fallback)
    def _on_disconnect_thorlabs(self):
        self._viewmodel.disconnect_thorlabs()

    def _on_scan_all(self):
        """Scan COM, GPIB, VISA, and PRM (Kinesis) on a worker thread — GUI stays responsive.
        PRM (Kinesis/.NET) scan runs on the main thread first because pythonnet requires STA."""
        if self._connection_scan_busy:
            self.main_status_log.appendPlainText("Connection: scan already in progress — wait for Ready.")
            return
        self.main_status_log.appendPlainText(
            "Scan All: COM (Arroyo/Actuator/Gentec), GPIB (Ando/Wavemeter), Kinesis (PRM), Thorlabs USB + full VISA..."
        )
        vm = self._viewmodel

        prm_serials = vm.scan_prm()
        prm_ok, prm_msg = vm.get_prm_scan_status()
        prm_result = {"prm_serials": prm_serials, "prm_status": prm_msg if not prm_serials else ""}

        def work():
            return {
                "ports": vm.scan_ports(),
                "gpib": vm.scan_gpib(),
                "prm_serials": prm_result["prm_serials"],
                "prm_status": prm_result["prm_status"],
                "visa_list": vm.scan_visa(),
                "thorlabs_usb": vm.scan_thorlabs_powermeters(),
            }

        self._start_connection_scan("Scan All: scanning…", "scan_all", work)

    def _schedule_wavemeter_connect(self, wm_addr: str, delay_ms: int) -> None:
        """
        Connect wavemeter after delay_ms (0 = immediate).
        Stagger avoids GPIB contention with Ando, and a short retry loop improves reliability on startup
        (USB/GPIB adapters enumerate late; manual disconnect/reconnect succeeds once ready).
        """
        a = (wm_addr or "").strip()
        if not a:
            return
        delay = max(0, int(delay_ms))

        def _attempt(n: int) -> None:
            try:
                st = self._viewmodel.get_connection_state()
            except Exception:
                st = {}
            if st.get("Wavemeter"):
                return
            self._set_footer_connecting()
            self._viewmodel.connect_wavemeter(a)
            if n >= 3:
                return

            def _maybe_retry():
                try:
                    st2 = self._viewmodel.get_connection_state()
                except Exception:
                    st2 = {}
                if not st2.get("Wavemeter"):
                    _attempt(n + 1)

            QTimer.singleShot(1200 + 800 * (n - 1), _maybe_retry)

        QTimer.singleShot(delay, lambda: _attempt(1))

    @staticmethod
    def _saved_ini_has_any_connection(d: object) -> bool:
        """True if instrument_config.ini [Connection] has at least one usable address (same basis as check_all_connections.py)."""
        if not isinstance(d, dict):
            return False
        bad = (
            "(no ports found)",
            "(no GPIB found)",
            "(no devices found)",
            "(no VISA found)",
            "(no Thorlabs / VISA found)",
            "(loading COM list…)",
            "(loading GPIB list…)",
            "(loading Thorlabs / VISA…)",
        )
        for k in (
            "arroyo_port",
            "actuator_port",
            "gentec_port",
            "ando_gpib",
            "wavemeter_gpib",
            "prm_serial",
            "thorlabs_visa",
        ):
            v = (d.get(k) or "").strip()
            if v and v not in bad:
                return True
        return False

    def _on_connect_all(
        self,
        use_saved=None,
        wavemeter_delay_ms: int = None,
        defer_prm_ms: int = 0,
    ):
        """Connect to all instruments.

        use_saved: pass the dict from load_saved_addresses() for startup auto-connect and footer Reconnect
        (saved instrument_config.ini). When omitted (Connection tab Connect All), addresses come from the
        current combo selections only — not from disk — so a manual scan + pick always wins over stale INI.

        defer_prm_ms > 0: schedule PRM after that many ms (startup auto-connect).
        """
        if isinstance(use_saved, bool):
            use_saved = None
        wm_delay = (
            int(_CONNECT_ALL_WAVEMETER_AFTER_ANDO_MS)
            if wavemeter_delay_ms is None
            else int(wavemeter_delay_ms)
        )
        self._set_footer_connecting()
        if isinstance(use_saved, dict) and self._saved_ini_has_any_connection(use_saved):
            _arp = (use_saved.get("arroyo_port") or "").strip()
            _acp = (use_saved.get("actuator_port") or "").strip()
            _same = (
                _arp
                and _acp
                and self._com_port_key_ui(_arp) == self._com_port_key_ui(_acp)
            )
            if _same:
                self.main_status_log.appendPlainText(
                    "Auto-connect: arroyo_port and actuator_port both {} — connecting Arroyo only; "
                    "use two different COM ports in Save Connections.".format(_arp)
                )
            serial_number = (use_saved.get("prm_serial") or "").strip()
            g_delay, a_delay = _connect_all_gentec_actuator_delays_ms(int(defer_prm_ms), serial_number)
            port = _arp
            if port:
                self._viewmodel.connect_arroyo(port)
            _gport = _normalize_user_com_port((use_saved.get("gentec_port") or "").strip())
            if _gport:
                QTimer.singleShot(g_delay, lambda p=_gport: self._viewmodel.connect_gentec(p))
            if _acp and not _same:
                QTimer.singleShot(a_delay, lambda p=_acp: self._viewmodel.connect_actuator(p))
            addr = (use_saved.get("ando_gpib") or "").strip()
            if addr:
                self._viewmodel.connect_ando(addr)
            addr = (use_saved.get("wavemeter_gpib") or "").strip()
            if addr:
                self._schedule_wavemeter_connect(addr, wm_delay)
            if serial_number:
                if defer_prm_ms > 0:
                    QTimer.singleShot(int(defer_prm_ms), lambda s=serial_number: self._viewmodel.connect_prm(s))
                else:
                    self._viewmodel.connect_prm(serial_number)
            visa_resource = (use_saved.get("thorlabs_visa") or "").strip()
            if visa_resource:
                self._viewmodel.connect_thorlabs(visa_resource)
            self._last_connect_all_addresses = dict(use_saved)
            self._schedule_post_connect_retries()
            return
        arp = self._arroyo_port_for_connect()
        acp = self._actuator_port_for_connect()
        gcp = self._gentec_port_for_connect()
        serial_number = _strip_saved_tag(self.prm_serial_combo.currentText())
        g_delay, a_delay = _connect_all_gentec_actuator_delays_ms(int(defer_prm_ms), serial_number)
        same_serial = (
            arp
            and acp
            and arp != "(no ports found)"
            and self._com_port_key_ui(arp) == self._com_port_key_ui(acp)
        )
        if same_serial:
            self.main_status_log.appendPlainText(
                "Connect All: arroyo_port and actuator_port both are {} — only one device per COM; "
                "connecting Arroyo only. Set different COM ports in Save Connections.".format(arp)
            )
            QMessageBox.warning(
                self,
                "Connection",
                "Arroyo and Actuator are configured for the same COM port ({}). "
                "They are not interlinked in software — Windows only allows one open handle per COM. "
                "Save different arroyo_port and actuator_port (e.g. laser on COM5, actuator on COM3)."
                .format(arp),
            )
            self._viewmodel.connect_arroyo(arp)
            if gcp:
                QTimer.singleShot(g_delay, lambda p=gcp: self._viewmodel.connect_gentec(p))
        else:
            if arp and arp != "(no ports found)":
                self._viewmodel.connect_arroyo(arp)
            if gcp:
                QTimer.singleShot(g_delay, lambda p=gcp: self._viewmodel.connect_gentec(p))
            if acp:
                QTimer.singleShot(a_delay, lambda p=acp: self._viewmodel.connect_actuator(p))
        addr = _strip_saved_tag(self.available_gpib_combo.currentText())
        if addr and addr != "(no GPIB found)":
            self._viewmodel.connect_ando(addr)
        addr = _strip_saved_tag(self.wavemeter_gpib_combo.currentText())
        if addr and addr != "(no GPIB found)":
            self._schedule_wavemeter_connect(addr, wm_delay)
        if serial_number and serial_number != "(no devices found)":
            if defer_prm_ms > 0:
                QTimer.singleShot(int(defer_prm_ms), lambda s=serial_number: self._viewmodel.connect_prm(s))
            else:
                self._viewmodel.connect_prm(serial_number)
        visa_resource = _strip_saved_tag(self.thorlabs_visa_combo.currentText())
        if visa_resource and visa_resource not in ("(no VISA found)", "(no Thorlabs / VISA found)"):
            self._viewmodel.connect_thorlabs(visa_resource)
        self._last_connect_all_addresses = self._connection_addresses_from_combos()
        self._schedule_post_connect_retries()

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
            QTimer.singleShot(
                280,
                lambda s=saved: self._on_connect_all(
                    use_saved=s,
                    wavemeter_delay_ms=int(_CONNECT_ALL_WAVEMETER_AFTER_ANDO_MS),
                    defer_prm_ms=350,
                ),
            )
        else:
            QTimer.singleShot(
                280,
                lambda: self._on_connect_all(
                    wavemeter_delay_ms=int(_CONNECT_ALL_WAVEMETER_AFTER_ANDO_MS),
                    defer_prm_ms=350,
                ),
            )

    def _on_save_connections(self):
        """Save current addresses; next startup will load them and can auto-connect. Manual connect always available."""
        addresses = {
            "arroyo_port": _strip_saved_tag(self.available_ports_combo.currentText()),
            "actuator_port": _strip_saved_tag(self.actuator_ports_combo.currentText()),
            "ando_gpib": _strip_saved_tag(self.available_gpib_combo.currentText()),
            "wavemeter_gpib": _strip_saved_tag(self.wavemeter_gpib_combo.currentText()),
            "prm_serial": _strip_saved_tag(self.prm_serial_combo.currentText()),
            "gentec_port": _strip_saved_tag(self.gentec_ports_combo.currentText()),
            "thorlabs_visa": _strip_saved_tag(self.thorlabs_visa_combo.currentText()),
            "auto_connect": "1",
        }
        self._viewmodel.save_connection_addresses(addresses)
        self.main_status_log.appendPlainText("Saved to instrument_config.ini")

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

        self._connection_scan_set_busy(True, "Scanning…")

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
            except Exception:
                thorlabs_usb = []
            try:
                visa_list = self._viewmodel.scan_visa()
            except Exception:
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
        try:
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
                fb = _thorlabs_visa_combo_fallback_list(visa_list)
                self.thorlabs_visa_combo.addItems(fb if fb else ["(no Thorlabs / VISA found)"])
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
        finally:
            self._connection_scan_set_busy(False)

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
        """Disable/enable PRM Move/Home/Quick/Set during move/home. Stop/IStop: grey when idle, colored when busy."""
        self._prm_manual_busy = bool(busy)
        self._prm_stop_grey_style = theme_prm_stop_grey_qss(self._tt())
        box = self.findChild(QGroupBox, "prm_control_box")
        if box:
            for btn in box.findChildren(QPushButton):
                if btn.objectName() in ("prm_stop_smooth_btn", "prm_stop_immediate_btn"):
                    btn.setEnabled(True)
                else:
                    btn.setEnabled(not busy)
        if hasattr(self, "prm_stop_btn") and hasattr(self, "prm_istop_btn"):
            if busy:
                self.prm_stop_btn.setStyleSheet(self._prm_stop_orange_style)
                self.prm_istop_btn.setStyleSheet(self._prm_istop_red_style)
            else:
                self.prm_stop_btn.setStyleSheet(self._prm_stop_grey_style)
                self.prm_istop_btn.setStyleSheet(self._prm_stop_grey_style)
        if hasattr(self, "prm_status_label"):
            if busy and status_hint == "move":
                self.prm_status_label.setText("Status: Moving...")
                self.prm_status_label.setStyleSheet(self._prm_status_label_style("#ff9800"))
            elif busy and status_hint == "home":
                self.prm_status_label.setText("Status: Homing...")
                self.prm_status_label.setStyleSheet(self._prm_status_label_style("#ff9800"))
            elif not busy:
                self.prm_status_label.setText("Status: Ready")
                self.prm_status_label.setStyleSheet(self._prm_status_label_style("#4caf50"))

    def _on_prm_command_finished(self):
        """Move/home subprocess finished; re-enable PRM buttons."""
        self._set_prm_busy(False)
        if getattr(self, "_home_actuator_b_after_prm_home", False):
            self._home_actuator_b_after_prm_home = False
            try:
                self._viewmodel.actuator_home_b()
            except Exception:
                pass
            # PER Stop: laser off only after PRM home and actuator B home (safe teardown order).
            if getattr(self, "_per_stop_deferred_laser_off", False):
                self._per_stop_deferred_laser_off = False
                try:
                    if hasattr(self._viewmodel, "set_arroyo_laser_output"):
                        self._viewmodel.set_arroyo_laser_output(False)
                except Exception:
                    pass
                try:
                    self.main_status_log.appendPlainText("PER Stop: laser output OFF (after PRM + actuator home).")
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
        self._viewmodel.prm_stop_smooth()
        self._set_prm_busy(False)
        if hasattr(self, "prm_status_label"):
            self.prm_status_label.setText("Status: Smooth stop sent")
            self.prm_status_label.setStyleSheet(self._prm_status_label_style("#ff9800"))

    def _on_prm_stop_immediate(self):
        self._viewmodel.prm_stop_immediate()
        self._set_prm_busy(False)
        if hasattr(self, "prm_status_label"):
            self.prm_status_label.setText("Status: Immediate stop sent")
            self.prm_status_label.setStyleSheet(self._prm_status_label_style("#f44336"))

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
            sb = self.main_status_log.verticalScrollBar()
            sb.setValue(sb.maximum())

    @pyqtSlot(str, object)
    def _on_sequence_step_failed(self, test_name: str, reasons: object) -> None:
        """Worker thread reports a failed step before/alongside log lines — fill Reason for Failure directly."""
        if isinstance(reasons, (list, tuple)):
            rs: List[Any] = list(reasons)
        elif reasons is None:
            rs = []
        else:
            rs = [reasons]
        try:
            self._mark_tests_pass_fail_step_failed(test_name)
        except Exception:
            pass
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

    # ----- Test status and Result circle (READY → Running → Done/STOP; per-step Pass/Fail, then overall) -----
    def _circle_style(self, bg_color, size=None):
        if size is None:
            size = _MAIN_TAB_STATUS_CIRCLE_PX
        return _main_tab_status_circle_stylesheet(bg_color, size)

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

    # ----- Main tab: TEST RESULTS panel (one row per step: PASS or FAIL + LED) -----
    @staticmethod
    def _sequence_step_kind_and_slot(name: str) -> Tuple[str, Optional[int]]:
        """Align with operations.test_sequence_executor step names."""
        t = (name or "").strip()
        u = t.upper()
        if u == "LIV":
            return "LIV", None
        if u == "PER":
            return "PER", None
        if u == "SPECTRUM":
            return "SPECTRUM", None
        nu = u.replace("_", " ")
        if "STABILITY 2" in nu or u == "TS2":
            return "STABILITY", 2
        if "STABILITY 1" in nu or u == "TS1":
            return "STABILITY", 1
        return "OTHER", None

    def _clear_tests_pass_fail_layout(self) -> None:
        lay = getattr(self, "_tests_pass_fail_inner_layout", None)
        ph = getattr(self, "_tests_pass_fail_placeholder", None)
        if lay is None:
            return
        self._tests_pass_fail_rows = []
        while lay.count():
            item = lay.takeAt(0)
            w = item.widget()
            if w is None:
                continue
            if ph is not None and w is ph:
                w.setParent(None)
                continue
            w.deleteLater()

    def _tests_pass_fail_reset_placeholder(self) -> None:
        self._clear_tests_pass_fail_layout()
        lay = getattr(self, "_tests_pass_fail_inner_layout", None)
        ph = getattr(self, "_tests_pass_fail_placeholder", None)
        if lay is not None and ph is not None:
            lay.addWidget(ph)
            lay.addStretch()

    def _build_tests_pass_fail_rows(self, seq: List[str]) -> None:
        """One row per TEST_SEQUENCE entry — pending until that step completes, then PASS or FAIL only."""
        lay = getattr(self, "_tests_pass_fail_inner_layout", None)
        if lay is None:
            return
        self._clear_tests_pass_fail_layout()
        chip_base = (
            "padding: 3px 10px; border-radius: 4px; font-size: 11px; font-weight: bold; min-width: 52px;"
        )
        t_pf = self._tt()
        pending_chip = theme_pass_fail_chip_style(t_pf)
        led_off = (
            "background-color: #555555; border-radius: 9px; min-width: 18px; max-width: 18px; "
            "min-height: 18px; max-height: 18px;"
        )
        name_style = theme_pass_fail_name_style(t_pf)
        for step in seq:
            display = (step or "").strip() or "?"
            kind, slot = self._sequence_step_kind_and_slot(display)
            row_w = QWidget()
            h = QHBoxLayout(row_w)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(8)
            name_lbl = QLabel(display.upper())
            name_lbl.setStyleSheet(name_style)
            name_lbl.setMinimumWidth(72)
            outcome_lbl = QLabel("—")
            outcome_lbl.setAlignment(QtCompat.AlignCenter)
            outcome_lbl.setStyleSheet(chip_base + pending_chip)
            led = QLabel()
            led.setFixedSize(18, 18)
            led.setStyleSheet(led_off)
            h.addWidget(name_lbl)
            h.addStretch(1)
            h.addWidget(outcome_lbl)
            h.addWidget(led, 0, QtCompat.AlignVCenter)
            lay.addWidget(row_w)
            self._tests_pass_fail_rows.append(
                {
                    "widget": row_w,
                    "display_name": display,
                    "kind": kind,
                    "stability_slot": slot,
                    "done": False,
                    "name_lbl": name_lbl,
                    "outcome_lbl": outcome_lbl,
                    "led": led,
                }
            )
        lay.addStretch()

    def _apply_tests_pass_fail_row_state(self, row: Dict[str, Any], passed: bool) -> None:
        chip_base = (
            "padding: 3px 10px; border-radius: 4px; font-size: 11px; font-weight: bold; min-width: 52px;"
        )
        t_row = self._tt()
        pass_hi = theme_tests_pass_chip_pass(t_row)
        fail_hi = theme_tests_pass_chip_fail(t_row)
        led_green = (
            "background-color: #4caf50; border-radius: 9px; min-width: 18px; max-width: 18px; "
            "min-height: 18px; max-height: 18px;"
        )
        led_red = (
            "background-color: #c62828; border-radius: 9px; min-width: 18px; max-width: 18px; "
            "min-height: 18px; max-height: 18px;"
        )
        ol = row["outcome_lbl"]
        led = row["led"]
        if passed:
            ol.setText("PASS")
            ol.setStyleSheet(chip_base + pass_hi)
            led.setStyleSheet(led_green)
        else:
            ol.setText("FAIL")
            ol.setStyleSheet(chip_base + fail_hi)
            led.setStyleSheet(led_red)

    def _find_pending_row_for_step(self, test_name: str, stability_slot: Optional[int] = None) -> Optional[Dict[str, Any]]:
        if not self._tests_pass_fail_rows:
            return None
        tn = (test_name or "").strip()
        tn_u = tn.upper()
        if stability_slot is not None:
            for row in self._tests_pass_fail_rows:
                if row.get("done"):
                    continue
                if row["kind"] == "STABILITY" and row.get("stability_slot") == stability_slot:
                    return row
            return None
        for row in self._tests_pass_fail_rows:
            if row.get("done"):
                continue
            if tn_u in ("LIV", "PER", "SPECTRUM") and row["kind"] == tn_u:
                return row
            if row["display_name"] == tn or row["display_name"].upper() == tn_u:
                return row
        for row in self._tests_pass_fail_rows:
            if row.get("done"):
                continue
            if row["kind"] == "OTHER" and (tn in row["display_name"] or tn_u in row["display_name"].upper()):
                return row
        return None

    def _finalize_tests_pass_fail_step(self, kind: str, passed: bool) -> None:
        row = self._find_pending_row_for_step(kind)
        if row is None:
            return
        self._apply_tests_pass_fail_row_state(row, passed)
        row["done"] = True
        # Main "Result" circle: only set in _on_sequence_completed when the full sequence finishes.

    def _finalize_tests_pass_fail_stability(self, slot: int, passed: bool) -> None:
        row = self._find_pending_row_for_step("", stability_slot=slot)
        if row is None:
            return
        self._apply_tests_pass_fail_row_state(row, passed)
        row["done"] = True

    def _mark_tests_pass_fail_step_failed(self, test_name: str) -> None:
        """sequence_step_failed: mark the matching pending row as FAIL."""
        tn = (test_name or "").strip()
        if tn == "TEST_SEQUENCE":
            return
        row = self._find_pending_row_for_step(tn)
        if row is None:
            return
        self._apply_tests_pass_fail_row_state(row, False)
        row["done"] = True

    def _clear_part_details_after_pass(self):
        """Clear part no, serial, recipe, wavelength (and recipe tab). Used from Start New → Clear only — not on sequence PASS, so the main tab keeps last run details."""
        self.details_recipe.setText("—")
        self.details_serial_no.setText("—")
        self.details_part_no.setText("—")
        self.details_wavelength.setText("—")
        self.details_smsr_on.setText("—")
        self._current_recipe_path = None
        self._current_recipe_data = None
        self._recipe_tab_path = None
        self._recipe_tab_data = None
        self._startnew_comments = ""
        self._refresh_recipe_tab()
        try:
            self._tests_pass_fail_reset_placeholder()
        except Exception:
            pass

    def _on_sequence_completed(self, all_passed):
        self._main_tab_sequence_ui_locked = False
        self._set_test_status("Done", "#4caf50")  # green
        if all_passed:
            self._set_pass_fail("Pass", "#4caf50")
            if hasattr(self, "main_failure_reason"):
                self.main_failure_reason.clear()
            # Keep main-tab part details and recipe visible after PASS; clear only via Start New → Clear.
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
        self._test_sequence_executor = None
        self._test_sequence_thread = None
        self._liv_sequence_bridge = None
        self._safe_refresh_summary_tab_from_cached_results()
        self._refresh_main_tab_sequence_controls_enabled()

    def _on_start_new_clear_requested(self):
        """Start New Clear: clear all details except Operator Name."""
        self._clear_part_details_after_pass()

    def _on_sequence_stopped(self):
        self._main_tab_sequence_ui_locked = False
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
        self._safe_refresh_summary_tab_from_cached_results()
        self._refresh_main_tab_sequence_controls_enabled()

    def _on_test_sequence_thread_finished(self):
        """Clear thread ref; if UI still shows Stopping..., force final STOP (signal safety net)."""
        self._main_tab_sequence_ui_locked = False
        self._test_sequence_thread = None
        if not hasattr(self, "main_test_ready_indicator"):
            self._refresh_main_tab_sequence_controls_enabled()
            return
        try:
            txt = (self.main_test_ready_indicator.text() or "").strip()
            if txt in ("Stopping...", "Stopping…"):
                self._set_test_status("STOP", "#c62828")
                self._set_pass_fail("--", "#555")
        except Exception:
            pass
        self._refresh_main_tab_sequence_controls_enabled()

    def _on_connect_fiber_before_liv(self, message: str):
        """Fiber-coupled LIV: short message only (no extra OK/Cancel wording in the text)."""
        reply = QMessageBox.question(
            self,
            "LIV",
            (message or "").strip(),
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
        if ex is not None:
            self._disconnect_liv_plot_tab_live_signals()
        prev = getattr(self, "_liv_test_window", None)
        if prev is not None and ex is not None:
            for sig, slot in (
                (ex.liv_plot_clear, prev.clear_plot),
                (ex.liv_plot_update, prev.on_plot_update),
                (ex.liv_power_reading_update, prev.on_power_reading_update),
                (ex.liv_log_message, prev.append_process_log),
                (ex.liv_power_reading_update, self._on_liv_power_reading_for_main),
                (ex.liv_live_arroyo, self._on_arroyo_readings_updated),
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
            # Forward LIV's live Gentec readings to main-window labels
            # (Gentec poll is paused during LIV but the sweep still reads it).
            cast(Any, ex.liv_power_reading_update).connect(
                self._on_liv_power_reading_for_main, _qc
            )
            # Forward LIV's live Arroyo readings to Main tab Laser/TEC Details
            # (Arroyo poll is paused during LIV to avoid serial contention).
            cast(Any, ex.liv_live_arroyo).connect(
                self._on_arroyo_readings_updated, _qc
            )
            cast(Any, self._liv_test_window.stop_requested).connect(
                self._on_stop_clicked, _qc
            )
            self._connect_liv_plot_tab_live_signals()
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

    @pyqtSlot()
    def blocking_open_per_test_window(self):
        """
        Called from the sequence worker via BlockingQueuedConnection before PERProcess.run().
        Reads ``TestSequenceExecutor._pending_per_window_params`` (no Q_ARG — reliable in PyQt5).
        Public slot name so QMetaObject.invokeMethod finds the method (underscore-only names can fail).
        """
        ex = getattr(self, "_test_sequence_executor", None)
        params = getattr(ex, "_pending_per_window_params", None) if ex is not None else None
        if not isinstance(params, dict):
            params = {}
        self._open_per_test_window(params)

    @pyqtSlot()
    def _prepare_per_test_window_before_per_run(self):
        """Legacy name — same as blocking_open_per_test_window."""
        self.blocking_open_per_test_window()

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
            # Live plot must run before _on_per_result: the latter closes this window on is_final, which
            # would otherwise run first (sequence connects _on_per_result before PER opens) and skip the
            # last update_live for that emission.
            try:
                cast(Any, ex.per_test_result).disconnect(self._on_per_result)
            except (TypeError, RuntimeError):
                pass
            cast(Any, ex.per_test_result).connect(self._per_test_window.update_live, _qc)
            cast(Any, ex.per_test_result).connect(self._on_per_result, _qc)
            cast(Any, ex.per_log_message).connect(
                self._per_test_window.append_process_log, _qc
            )
            cast(Any, self._per_test_window.stop_requested).connect(
                self._on_per_window_stop_requested, _qc
            )
        place_on_secondary_screen_before_show(self._per_test_window, self)
        self._per_test_window.show()
        try:
            self._per_test_window.raise_()
            self._per_test_window.activateWindow()
        except Exception:
            pass

    def _on_per_test_window_destroyed(self):
        self._per_test_window = None

    def _on_per_window_stop_requested(self):
        """PER window Stop: end sweep (stop flag) → stop PRM motion → PRM home → actuator B home → laser off → close window."""
        ex = getattr(self, "_test_sequence_executor", None)
        if ex is not None:
            try:
                cast(Any, ex.per_log_message).emit("STOP: Stop requested — ending sweep, then PRM home, actuator B home.")
            except Exception:
                pass
        self._set_test_status("Stopping...", "#FF9800")
        # 1) Tell PER sweep / sequence to exit (worker sees stop_requested).
        if self._test_sequence_executor is not None:
            self._test_sequence_executor.stop()
        # 2) Halt rotation immediately, then home PRM; actuator B homes in _on_prm_command_finished; laser off after that.
        self._per_stop_deferred_laser_off = True
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
                w.set_status("Stopping… homing PRM, then actuator B, then laser off.")
        except Exception:
            pass
        try:
            self._viewmodel.prm_home()
        except Exception:
            self._close_per_window_after_home = False
            self._home_actuator_b_after_prm_home = False
            self._per_stop_deferred_laser_off = False
        finally:
            self._main_tab_sequence_ui_locked = False
            self._refresh_main_tab_sequence_controls_enabled()
            try:
                QApplication.processEvents()
            except Exception:
                pass

    def _schedule_liv_process_window_close(self, w) -> None:
        """Close LIV Process window 5 s after LIV step completes so the operator can read results."""
        if w is None:
            return

        def _close():
            try:
                w.close()
            except Exception:
                pass

        QTimer.singleShot(5000, _close)

    def _refresh_plot_tab_liv_results(self, r: Optional[Any], which: str = "plot") -> None:
        """LIV metric line edits: Plot tab and/or Result tab from LIV result (or clear)."""
        groups: List[Tuple[str, Tuple[str, ...]]] = []
        if getattr(self, "plot_tab_liv_l_at_ir", None) is not None:
            groups.append(
                (
                    "plot",
                    (
                        "plot_tab_liv_l_at_ir",
                        "plot_tab_liv_i_at_lr",
                        "plot_tab_liv_ith",
                        "plot_tab_liv_se",
                        "plot_tab_liv_pd_at_ir",
                        "plot_tab_liv_cal_factor",
                    ),
                )
            )
        if getattr(self, "rt_liv_l_at_ir", None) is not None:
            groups.append(
                (
                    "result",
                    (
                        "rt_liv_l_at_ir",
                        "rt_liv_i_at_lr",
                        "rt_liv_ith",
                        "rt_liv_se",
                        "rt_liv_pd_at_ir",
                        "rt_liv_cal_factor",
                    ),
                )
            )
        if not groups:
            return

        def _set(attr: str, text: str) -> None:
            w = getattr(self, attr, None)
            if w is not None:
                w.setText(text)

        def _fmt(val: Any, nd: int = 4) -> str:
            if val is None:
                return "—"
            try:
                x = float(val)
                if math.isnan(x) or math.isinf(x):
                    return "—"
                return f"{x:.{nd}f}"
            except (TypeError, ValueError):
                return "—"

        for g_which, keys in groups:
            if g_which != which and which != "both":
                continue
            if r is None:
                for a in keys:
                    _set(a, "—")
                continue
            vals = (
                _fmt(getattr(r, "power_at_rated_current", None)),
                _fmt(getattr(r, "current_at_rated_power", None)),
                _fmt(getattr(r, "threshold_current", None)),
                _fmt(getattr(r, "slope_efficiency", None)),
                _fmt(getattr(r, "pd_at_rated_current", None)),
                _fmt(getattr(r, "thorlabs_calib_factor", None)),
            )
            for a, t in zip(keys, vals):
                _set(a, t)

    def _refresh_plot_tab_per_results(self, r: Optional[Any]) -> None:
        """Plot tab + Result tab: max/min power (dBm) and PER angle from last final PER result."""
        groups: List[Tuple[str, Tuple[str, str, str]]] = []
        if getattr(self, "plot_tab_per_max_dbm", None) is not None:
            groups.append(("plot", ("plot_tab_per_max_dbm", "plot_tab_per_min_dbm", "plot_tab_per_angle")))
        if getattr(self, "rt_per_max_dbm", None) is not None:
            groups.append(("result", ("rt_per_max_dbm", "rt_per_min_dbm", "rt_per_angle")))

        def _set(attr: str, text: str) -> None:
            w = getattr(self, attr, None)
            if w is not None:
                w.setText(text)

        def _fmt_num(val: Any, nd: int = 4) -> str:
            if val is None:
                return "—"
            try:
                x = float(val)
                if math.isnan(x) or math.isinf(x):
                    return "—"
                return f"{x:.{nd}f}"
            except (TypeError, ValueError):
                return "—"

        def _fmt_g(val: Any) -> str:
            if val is None:
                return "—"
            try:
                x = float(val)
                if math.isnan(x) or math.isinf(x):
                    return "—"
                return f"{x:.4g}"
            except (TypeError, ValueError):
                return "—"

        if not groups:
            return
        for _which, keys in groups:
            if r is None:
                for a in keys:
                    _set(a, "—")
                continue
            mx = getattr(r, "max_power", None)
            mn = getattr(r, "min_power", None)
            ag = getattr(r, "max_angle", None)
            mx_d = _fmt_g(mw_to_dbm(float(mx))) if mx is not None else "—"
            mn_d = _fmt_g(mw_to_dbm(float(mn))) if mn is not None else "—"
            _set(keys[0], mx_d)
            _set(keys[1], mn_d)
            _set(keys[2], _fmt_num(ag))

    def _refresh_result_tab_per_plot(self, result: Optional[Any]) -> None:
        """Result-tab PER curve from final angles/powers (uses last PER sweep if angles not stored on result)."""
        rppc = getattr(self, "rt_per_power_curve", None)
        if not _PG_AVAILABLE or rppc is None:
            return
        if result is None:
            try:
                rppc.setData([], [])
            except Exception:
                pass
            return
        ang = list(
            getattr(result, "positions_deg", None)
            or getattr(result, "angles_deg", None)
            or getattr(result, "angle_array", None)
            or []
        )
        pw = list(getattr(result, "powers_mw", None) or getattr(result, "power_array_mw", None) or [])
        if not ang or not pw:
            try:
                rppc.setData([], [])
            except Exception:
                pass
            return
        n = min(len(ang), len(pw))
        if n < 1:
            return
        try:
            y_dbm = mw_series_to_dbm(pw[:n])
            rppc.setData(ang[:n], y_dbm)
            sp = getattr(self, "rt_per_plot", None)
            if sp is not None:
                pi = sp.getPlotItem()
                if pi is not None:
                    pi.getViewBox().enableAutoRange()
        except Exception:
            pass

    def _refresh_plot_tab_stability(self) -> None:
        """Re-apply cached TS1/TS2 results to Plot tab and Result tab graphs (or clear)."""
        last = getattr(self, "_last_stability_results", None) or {}
        for slot, attr, rt_attr in (
            (1, "_plot_tab_ts1_bundle", "_rt_ts1_bundle"),
            (2, "_plot_tab_ts2_bundle", "_rt_ts2_bundle"),
        ):
            r = last.get(slot)
            for a in (attr, rt_attr):
                b = getattr(self, a, None)
                if b is None:
                    continue
                if r is not None:
                    try:
                        stability_tab_apply_result(b, r)
                    except Exception:
                        pass
                else:
                    try:
                        stability_tab_clear_plot(b)
                    except Exception:
                        pass

    def _refresh_plot_tab_spectrum(self) -> None:
        """Re-apply cached spectrum result to Plot tab Ando trace."""
        self._apply_spectrum_result_to_plot_tab(getattr(self, "_last_spectrum_result", None))

    def _apply_spectrum_result_to_curve_plot(
        self, rc: Optional[Any], rsp: Optional[Any], result: Optional[Any]
    ) -> None:
        """Update one spectrum Ando trace plot (Plot tab and/or Result tab widget)."""
        if not _PG_AVAILABLE or rc is None:
            return
        if result is None:
            try:
                rc.setData([], [])
            except Exception:
                pass
            if rsp is getattr(self, "result_spectrum_os_plot", None):
                try:
                    self._reset_spectrum_plot_axis_labels()
                except Exception:
                    pass
            elif rsp is not None:
                try:
                    tc = "#333333"
                    pi_r = cast(Any, rsp.getPlotItem())
                    pi_r.setTitle("Ando sweep — LVL (dBm)", color=tc)
                    pi_r.setLabel("bottom", "Wavelength (nm)", color=tc)
                    pi_r.setLabel("left", "Level (dBm)", color=tc)
                except Exception:
                    pass
            return

        def _pair(raw_w: Any, raw_l: Any) -> Tuple[List[float], List[float]]:
            if _spectrum_pair_trace_floats is not None:
                pw, pl = _spectrum_pair_trace_floats(raw_w, raw_l)
                return list(pw or []), list(pl or [])
            w = list(raw_w or [])
            level_data = list(raw_l or [])
            n = min(len(w), len(level_data))
            return w[:n], level_data[:n]

        w2, l2 = _pair(getattr(result, "second_sweep_wdata", None), getattr(result, "second_sweep_ldata", None))
        use_second = len(w2) > 0 and len(l2) > 0

        if use_second:
            wm = getattr(result, "second_wavemeter_nm", None)
            if wm is None:
                wm = getattr(result, "wavemeter_nm_for_axis_label", None)
            peak_ando = getattr(result, "peak_wavelength_second_nm", None)
            if peak_ando is None:
                peak_ando = getattr(result, "peak_wavelength", None)
            if peak_ando is None and len(w2) > 0:
                peak_ando = self._spectrum_peak_wavelength_from_trace(w2, l2)
            x_plot = self._spectrum_x_aligned_to_wavemeter(w2, l2, peak_ando, wm)
            try:
                rc.setData(x_plot, l2)
            except Exception:
                pass
            try:
                if rsp is not None:
                    pi_r = cast(Any, rsp.getPlotItem())
                    tc_r = "#333333"
                    pi_r.setTitle("Spectrum — second sweep", color=tc_r)
                    pi_r.setLabel("left", "Level (dBm)", color=tc_r)
                    if wm is not None:
                        if _spectrum_wm_bottom_axis_label is not None:
                            _bottom_lbl = _spectrum_wm_bottom_axis_label(wm)
                        else:
                            _s = ("{:.12f}".format(float(wm))).rstrip("0").rstrip(".")
                            _bottom_lbl = _s + " nm"
                    else:
                        _bottom_lbl = "Wavelength (nm)"
                    pi_r.setLabel("bottom", _bottom_lbl, color=tc_r)
                    vb_r = cast(Any, rsp).getPlotItem().getViewBox()
                    self._spectrum_result_apply_xrange_from_trace(rsp, x_plot)
                    if _spectrum_plot_y_range_dbm is not None:
                        ref = float(getattr(result, "ref_level_dbm", -10.0))
                        ls = float(getattr(result, "level_scale_db_per_div", 10.0))
                        yr = _spectrum_plot_y_range_dbm(ref, ls)
                        if yr is not None:
                            vb_r.setYRange(yr[0], yr[1], padding=0.02)
                    elif l2:
                        lo = min(float(x) for x in l2)
                        hi = max(float(x) for x in l2)
                        pad = max(0.5, (hi - lo) * 0.1)
                        vb_r.setYRange(lo - pad, hi + pad, padding=0.02)
            except Exception:
                pass
        else:
            try:
                rc.setData([], [])
            except Exception:
                pass
            if rsp is getattr(self, "result_spectrum_os_plot", None):
                try:
                    self._reset_spectrum_plot_axis_labels()
                except Exception:
                    pass

    def _apply_spectrum_result_to_plot_tab(self, result: Optional[Any]) -> None:
        """Update Plot tab and Result tab spectrum curves from a spectrum step result (or clear)."""
        self._apply_spectrum_result_to_curve_plot(
            getattr(self, "result_spectrum_os_curve", None),
            getattr(self, "result_spectrum_os_plot", None),
            result,
        )
        self._apply_spectrum_result_to_curve_plot(
            getattr(self, "rt_spectrum_os_curve", None),
            getattr(self, "rt_spectrum_os_plot", None),
            result,
        )

    def _apply_per_result_values(self, result: Any) -> None:
        """Cache final PER result and fill Plot tab line edits."""
        self._last_per_result = result
        self._refresh_plot_tab_per_results(result)

        self.per_result_max_power = getattr(result, "max_power", None)
        self.per_result_min_power = getattr(result, "min_power", None)
        self.per_result_per = getattr(result, "per_db", None)
        self.per_result_angle = getattr(result, "max_angle", None)

    @staticmethod
    def _coerce_liv_result_object(result: Any) -> Any:
        if result is None:
            return None
        return getattr(result, "liv_result", None) or result

    def _disconnect_liv_plot_tab_live_signals(self) -> None:
        ex = getattr(self, "_test_sequence_executor", None)
        if ex is None:
            return
        for sig in (getattr(ex, "liv_plot_clear", None), getattr(ex, "liv_plot_update", None)):
            if sig is None:
                continue
            for slot in (self._on_liv_plot_tab_clear, self._on_liv_plot_tab_update):
                try:
                    sig.disconnect(slot)
                except (TypeError, RuntimeError):
                    pass

    def _connect_liv_plot_tab_live_signals(self) -> None:
        """Wire Plot tab to LIV sweep start (clear only). Curves + metrics refresh in _on_liv_result when LIV finishes."""
        ex = getattr(self, "_test_sequence_executor", None)
        if ex is None:
            return
        _qc = QtCompat.QueuedConnection
        cast(Any, ex.liv_plot_clear).connect(self._on_liv_plot_tab_clear, _qc)

    def _on_liv_plot_tab_clear(self) -> None:
        self._plot_tab_liv_live_i.clear()
        self._plot_tab_liv_live_p.clear()
        self._plot_tab_liv_live_v.clear()
        self._plot_tab_liv_live_pd.clear()
        if not _PG_AVAILABLE:
            return
        p1_liv = getattr(self, "_result_liv_plot_p1", None)
        if getattr(self, "_result_liv_overlay_items", None) is None:
            self._result_liv_overlay_items = []
        ov = self._result_liv_overlay_items
        if p1_liv is not None:
            clear_liv_analysis_overlays(p1_liv, ov)
        rlp = getattr(self, "result_liv_power_curve", None)
        rlv = getattr(self, "result_liv_voltage_curve", None)
        rlpd = getattr(self, "result_liv_pd_curve", None)
        try:
            if rlp is not None:
                rlp.setData([], [])
            if rlv is not None:
                rlv.setData([], [])
            if rlpd is not None:
                rlpd.setData([], [])
        except Exception:
            pass

    def _on_liv_plot_tab_update(
        self, current: float, power: float, voltage: float, pd: float = 0.0, tec_temp: float = 0.0
    ) -> None:
        _ = tec_temp
        if not _PG_AVAILABLE:
            return
        self._plot_tab_liv_live_i.append(float(current))
        self._plot_tab_liv_live_p.append(float(power))
        self._plot_tab_liv_live_v.append(float(voltage))
        self._plot_tab_liv_live_pd.append(float(pd))
        li, lp, lv, lpd = (
            self._plot_tab_liv_live_i,
            self._plot_tab_liv_live_p,
            self._plot_tab_liv_live_v,
            self._plot_tab_liv_live_pd,
        )
        n = len(li)
        rlp = getattr(self, "result_liv_power_curve", None)
        rlv = getattr(self, "result_liv_voltage_curve", None)
        rlpd = getattr(self, "result_liv_pd_curve", None)
        vb_v = getattr(self, "_result_liv_vb_voltage", None)
        vb_pd = getattr(self, "_result_liv_vb_pd", None)
        try:
            if rlp is not None:
                rlp.setData(li, lp)
            if rlv is not None and len(lv) == n:
                rlv.setData(li, lv)
            if rlpd is not None and len(lpd) == n:
                rlpd.setData(li, lpd)
            liv_autorange_secondary_axes(vb_v, vb_pd, li, lv, lpd)
        except Exception:
            pass

    def _refresh_plot_tab_liv_full(self, r: Optional[Any]) -> None:
        """Plot tab LIV: raw curves, Phase-4 analysis overlays (readable on white), and metric fields."""
        self._refresh_liv_panel_common("plot", r)

    def _refresh_liv_panel_common(self, which: str, r: Optional[Any]) -> None:
        """LIV curves + overlays + metrics for Plot tab (which=='plot') or Result tab (which=='result')."""
        if which == "result":
            rlp = getattr(self, "rt_liv_power_curve", None)
            if rlp is None:
                return
            p1_liv = getattr(self, "_rt_liv_p1", None)
            if getattr(self, "_rt_liv_overlay_items", None) is None:
                self._rt_liv_overlay_items = []
            ov_liv = self._rt_liv_overlay_items
            rlv = getattr(self, "rt_liv_voltage_curve", None)
            rlpd = getattr(self, "rt_liv_pd_curve", None)
            vb_v = getattr(self, "_rt_liv_vb_voltage", None)
            vb_pd = getattr(self, "_rt_liv_vb_pd", None)
        else:
            rlp = getattr(self, "result_liv_power_curve", None)
            p1_liv = getattr(self, "_result_liv_plot_p1", None)
            if getattr(self, "_result_liv_overlay_items", None) is None:
                self._result_liv_overlay_items = []
            ov_liv = self._result_liv_overlay_items
            rlv = getattr(self, "result_liv_voltage_curve", None)
            rlpd = getattr(self, "result_liv_pd_curve", None)
            vb_v = getattr(self, "_result_liv_vb_voltage", None)
            vb_pd = getattr(self, "_result_liv_vb_pd", None)

        if not _PG_AVAILABLE or rlp is None:
            self._refresh_plot_tab_liv_results(r, which=which)
            return

        if r is None:
            if p1_liv is not None:
                clear_liv_analysis_overlays(p1_liv, ov_liv)
            if which == "plot":
                li, lp, lv, lpd = (
                    self._plot_tab_liv_live_i,
                    self._plot_tab_liv_live_p,
                    self._plot_tab_liv_live_v,
                    self._plot_tab_liv_live_pd,
                )
                if len(li) > 0 and len(lp) == len(li):
                    try:
                        rlp.setData(li, lp)
                        if rlv is not None and len(lv) == len(li):
                            rlv.setData(li, lv)
                        if rlpd is not None and len(lpd) == len(li):
                            rlpd.setData(li, lpd)
                        liv_autorange_secondary_axes(vb_v, vb_pd, li, lv, lpd)
                    except Exception:
                        pass
                else:
                    try:
                        rlp.setData([], [])
                        if rlv is not None:
                            rlv.setData([], [])
                        if rlpd is not None:
                            rlpd.setData([], [])
                    except Exception:
                        pass
            else:
                try:
                    rlp.setData([], [])
                    if rlv is not None:
                        rlv.setData([], [])
                    if rlpd is not None:
                        rlpd.setData([], [])
                except Exception:
                    pass
            self._refresh_plot_tab_liv_results(None, which=which)
            return

        try:
            currents = list(getattr(r, "current_array", None) or [])
            powers = list(
                getattr(r, "power_array", None) or getattr(r, "gentec_power_array", None) or []
            )
            voltages = list(getattr(r, "voltage_array", None) or [])
            pd = list(getattr(r, "pd_array", None) or [])
            n_cp = len(currents)
            n_pw = len(powers)
            ok_main = n_cp > 0 and n_pw > 0 and n_cp == n_pw
            n_v = len(voltages)
            n_pd = len(pd)
            if p1_liv is not None:
                clear_liv_analysis_overlays(p1_liv, ov_liv)
            if ok_main:
                rlp.setData(currents, powers)
                if rlv is not None and n_v == n_cp:
                    rlv.setData(currents, voltages)
                if rlpd is not None and n_pd == n_cp:
                    rlpd.setData(currents, pd)
                liv_autorange_secondary_axes(vb_v, vb_pd, currents, voltages, pd)
                if p1_liv is not None:
                    apply_liv_phase4_overlays(
                        p1_liv,
                        PG,
                        r,
                        recipe_params_for_liv_overlays(getattr(self, "_current_recipe_data", None)),
                        ov_liv,
                        dark_theme=False,
                    )
            else:
                rlp.setData([], [])
                if rlv is not None:
                    rlv.setData([], [])
                if rlpd is not None:
                    rlpd.setData([], [])
        except Exception:
            pass
        self._refresh_plot_tab_liv_results(r, which=which)

    def _on_liv_result(self, result):
        """Push final LIV results to the LIV Process window; close it after a short delay."""
        w = getattr(self, "_liv_test_window", None)
        ex = self._test_sequence_executor
        if ex is not None:
            try:
                ex.liv_power_reading_update.disconnect(self._on_liv_power_reading_for_main)
            except (TypeError, RuntimeError):
                pass
        if w is not None:
            if ex is not None:
                for sig_name, slot in (
                    ("liv_plot_clear", getattr(w, "clear_plot", None)),
                    ("liv_plot_update", getattr(w, "on_plot_update", None)),
                    ("liv_power_reading_update", getattr(w, "on_power_reading_update", None)),
                ):
                    if slot is None:
                        continue
                    try:
                        getattr(ex, sig_name).disconnect(slot)
                    except Exception:
                        pass
            r_win = getattr(result, "liv_result", None) or result
            try:
                if hasattr(w, "set_liv_results") and r_win is not None:
                    w.set_liv_results(r_win)
            except Exception:
                pass

        r = self._coerce_liv_result_object(result)
        try:
            if r is not None:
                self._last_liv_result = r
                try:
                    passed_flag = bool(getattr(r, "passed", False))
                    reasons = list(getattr(r, "fail_reasons", []) or [])
                    if not passed_flag:
                        # Do not mirror LIV fail_reasons into the main Status Log (noisy duplicate of Reason for Failure).
                        if getattr(self, "_test_sequence_executor", None) is None:
                            self._append_reason_for_failure_box(
                                "LIV",
                                reasons if reasons else ["LIV did not pass (no fail_reasons on result)."],
                                False,
                            )
                except Exception:
                    pass
                try:
                    self._finalize_tests_pass_fail_step("LIV", bool(getattr(r, "passed", False)))
                except Exception:
                    pass

            self._refresh_plot_tab_liv_full(r)
            self._refresh_liv_panel_common("result", r)
            self._schedule_liv_process_window_close(w)
        finally:
            self._safe_refresh_summary_tab_from_cached_results()

    def _on_per_result(self, result, angles, powers_mw):
        """PER window receives live samples; Plot tab curve + metrics update only on the final sweep."""
        is_final = bool(getattr(result, "is_final", False)) if result is not None else False
        rppc = getattr(self, "result_per_power_curve", None)
        rtppc = getattr(self, "rt_per_power_curve", None)
        if _PG_AVAILABLE and is_final:
            for curve in (rppc, rtppc):
                if curve is None:
                    continue
                if angles and powers_mw:
                    pw = list(powers_mw)
                    ang = list(angles)
                    n = min(len(ang), len(pw))
                    if n > 0:
                        y_dbm = mw_series_to_dbm(pw[:n])
                        ax = ang[:n]
                        curve.setData(ax, y_dbm)
                        try:
                            sp = getattr(self, "result_per_plot", None) if curve is rppc else getattr(
                                self, "rt_per_plot", None
                            )
                            if sp is not None:
                                pi = sp.getPlotItem()
                                if pi is not None:
                                    pi.getViewBox().enableAutoRange()
                        except Exception:
                            pass
                    else:
                        curve.setData([], [])
                        try:
                            sp = getattr(self, "result_per_plot", None) if curve is rppc else getattr(
                                self, "rt_per_plot", None
                            )
                            if sp is not None:
                                sp.enableAutoRange()
                        except Exception:
                            pass
                else:
                    curve.setData([], [])
                    try:
                        sp = getattr(self, "result_per_plot", None) if curve is rppc else getattr(self, "rt_per_plot", None)
                        if sp is not None:
                            sp.enableAutoRange()
                    except Exception:
                        pass
        if is_final and result is not None:
            self._apply_per_result_values(result)
        try:
            if result is not None and is_final:
                if not bool(getattr(result, "passed", True)):
                    fr = list(getattr(result, "fail_reasons", []) or [])
                    if getattr(self, "_test_sequence_executor", None) is None:
                        self._append_reason_for_failure_box(
                            "PER",
                            fr if fr else ["PER did not pass (no fail_reasons on result)."],
                            False,
                        )
        except Exception:
            pass
        try:
            if result is not None and is_final:
                self._finalize_tests_pass_fail_step("PER", bool(getattr(result, "passed", True)))
        except Exception:
            pass
        # After final curve + results, close the live PER window.
        try:
            if is_final:
                w = getattr(self, "_per_test_window", None)
                if w is not None:
                    w.close()
        except Exception:
            pass
        if is_final:
            self._safe_refresh_summary_tab_from_cached_results()

    def _reset_spectrum_plot_axis_labels(self) -> None:
        """Default axis titles before/after a run (optional main-window spectrum plot)."""
        tc = "#333333"
        bottom = "Wavelength (nm)"
        left = "Level (dBm)"
        sp = getattr(self, "result_spectrum_os_plot", None)
        if sp is not None:
            pi = cast(Any, sp.getPlotItem())
            pi.setTitle("Ando sweep — LVL (dBm)", color=tc)
            pi.setLabel("bottom", bottom, color=tc)
            pi.setLabel("left", left, color=tc)

    @staticmethod
    def _spectrum_peak_wavelength_from_trace(w: List[float], levels_dbm: List[float]) -> Optional[float]:
        if not w or not levels_dbm or len(w) != len(levels_dbm):
            return None
        try:
            i = max(range(len(levels_dbm)), key=lambda j: float(levels_dbm[j]))
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

    def _on_spectrum_result(self, result):
        """Update Plot tab spectrum curve; finalize the secondary Spectrum step window."""
        self._last_spectrum_result = result
        try:
            self._apply_spectrum_result_to_plot_tab(result)

            passed = bool(getattr(result, "passed", False))
            fail_reasons = list(getattr(result, "fail_reasons", None) or [])
            detail = "; ".join(str(x) for x in fail_reasons) if fail_reasons else ""

            finalize = bool(getattr(result, "spectrum_finalize_secondary_window", True))
            if finalize:
                try:
                    sw = getattr(self, "_spectrum_test_window", None)
                    if sw is not None and hasattr(sw, "set_finished"):
                        sw.set_finished(passed, detail if not passed else "")
                except Exception:
                    pass
                try:
                    self._finalize_tests_pass_fail_step("SPECTRUM", passed)
                except Exception:
                    pass
                try:
                    QTimer.singleShot(600, self._close_spectrum_test_window)
                except Exception:
                    pass
        finally:
            self._safe_refresh_summary_tab_from_cached_results()

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
        self._disconnect_spectrum_live_signals()
        self._spectrum_test_window = None

    def _disconnect_spectrum_live_signals(self) -> None:
        """Detach the Spectrum step window from live signals when the window closes."""
        ex = getattr(self, "_test_sequence_executor", None)
        w = getattr(self, "_spectrum_test_window", None)
        if ex is None:
            return
        if w is not None:
            for sig_name, slot in (
                ("spectrum_live_trace", w.set_live_trace),
                ("spectrum_wavemeter_reading", w.set_wavemeter_reading),
                ("spectrum_step_status", w.set_status),
            ):
                sig = getattr(ex, sig_name, None)
                if sig is None or slot is None:
                    continue
                try:
                    sig.disconnect(slot)
                except (TypeError, RuntimeError):
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
                cast(Any, ex.stability_live_arroyo).connect(self._on_arroyo_readings_updated, _qc)
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
            try:
                cast(Any, ex.stability_live_arroyo).disconnect(self._on_arroyo_readings_updated)
            except Exception:
                pass
        self._stability_test_window = None

    @staticmethod
    def _spectrum_result_apply_xrange_from_trace(plot_widget: Any, x_plot: List[float]) -> None:
        """Set X range from aligned trace (wavemeter-based WDATA)."""
        if plot_widget is None or not x_plot:
            return
        try:
            xf: List[float] = []
            for x in x_plot:
                try:
                    v = float(x)
                except (TypeError, ValueError):
                    continue
                if v == v:  # not NaN
                    xf.append(v)
            if not xf:
                return
            lo, hi = min(xf), max(xf)
            pad = max((hi - lo) * 0.06, 0.02) if hi > lo else 0.1
            vb = cast(Any, plot_widget).getPlotItem().getViewBox()
            vb.setXRange(lo - pad, hi + pad, padding=0)
        except Exception:
            pass

    def _apply_stability_result_to_main_tab(self, slot: int, result: Any) -> None:
        """Apply final temperature-stability arrays to Plot tab and Result tab TS1/TS2 graphs (if present)."""
        if not _PG_AVAILABLE:
            return
        bundle = getattr(self, "_plot_tab_ts1_bundle", None) if int(slot) == 1 else getattr(
            self, "_plot_tab_ts2_bundle", None
        )
        if bundle is not None:
            try:
                stability_tab_apply_result(bundle, result)
            except Exception:
                pass
        rt_b = getattr(self, "_rt_ts1_bundle", None) if int(slot) == 1 else getattr(self, "_rt_ts2_bundle", None)
        if rt_b is not None:
            try:
                stability_tab_apply_result(rt_b, result)
            except Exception:
                pass
        if bundle is not None:
            return
        r_curves = getattr(self, "result_ts1_curves", []) if int(slot) == 1 else getattr(self, "result_ts2_curves", [])
        if len(r_curves) < 4:
            return
        tx = list(getattr(result, "temperature_c", []) or [])
        fy = list(getattr(result, "fwhm_nm", []) or [])
        sy_db = list(getattr(result, "smsr_db", []) or [])
        py = list(getattr(result, "peak_wavelength_nm", []) or [])
        lv = list(getattr(result, "peak_level_dbm", []) or [])
        try:
            n = min(len(tx), len(py), len(fy), len(lv))
            if n < 1:
                return
            if len(sy_db) < n:
                sy_db = sy_db + [None] * (n - len(sy_db))
            else:
                sy_db = sy_db[:n]
            tx = tx[:n]
            py = py[:n]
            fy = fy[:n]
            lv = lv[:n]
            sy = stability_smsr_y_for_plot(result, sy_db, lv, n)
            r_curves[0].setData(tx, py)
            r_curves[1].setData(tx, fy)
            r_curves[2].setData(tx, sy)
            r_curves[3].setData(tx, lv)
            try:
                vb0 = r_curves[0].getViewBox()
                if vb0 is not None:
                    vb0.enableAutoRange()
            except Exception:
                pass
        except Exception:
            pass

    def _on_stability_test_result(self, result: Any) -> None:
        self._apply_stability_result_to_main_tab(getattr(result, "slot", 1), result)
        try:
            slot = int(getattr(result, "slot", 1))
            self._last_stability_results[slot] = result
            self._finalize_tests_pass_fail_stability(slot, bool(getattr(result, "passed", False)))
        except Exception:
            pass
        self._safe_refresh_summary_tab_from_cached_results()
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

    def _sync_tests_pass_fail_panel_from_recipe(self, recipe: Optional[dict]) -> None:
        """Fill TEST RESULTS rows from recipe TEST_SEQUENCE (— until each step finishes). Called after Start Test; also on Run to reset."""
        if not recipe or not isinstance(recipe, dict):
            self._tests_pass_fail_reset_placeholder()
            return
        raw_seq = (
            recipe.get("TEST_SEQUENCE")
            or recipe.get("TestSequence")
            or (recipe.get("GENERAL") or {}).get("TestSequence")
            or (recipe.get("GENERAL") or {}).get("TEST_SEQUENCE")
        )
        seq = self._coerce_test_sequence(raw_seq)
        if seq:
            self._build_tests_pass_fail_rows(seq)
        else:
            self._tests_pass_fail_reset_placeholder()

    def _is_test_sequence_busy(self) -> bool:
        # Do not use executor/thread refs alone: sequence_completed may clear them before the QThread exits.
        return bool(getattr(self, "_main_tab_sequence_ui_locked", False))

    def _refresh_main_tab_sequence_controls_enabled(self) -> None:
        """Disable Start New and Run while a sequence is active; re-enable when idle."""
        busy = self._is_test_sequence_busy()
        tip = "Unavailable while a test sequence is running. Press Stop to abort, then try again."
        for name in ("main_start_new_btn", "main_run_btn"):
            btn = getattr(self, name, None)
            if btn is None:
                continue
            btn.setEnabled(not busy)
            try:
                btn.setToolTip(tip if busy else "")
            except Exception:
                pass
        lock_tip = (
            "Laser and TEC are locked while a test sequence is running so the run is not interrupted. "
            "Press Stop on the main tab to abort the sequence."
        )
        for name in ("arroyo_laser_btn", "arroyo_tec_btn"):
            btn = getattr(self, name, None)
            if btn is None:
                continue
            btn.setEnabled(not busy)
            try:
                btn.setToolTip(lock_tip if busy else "")
            except Exception:
                pass

    def _on_run_clicked(self):
        if self._is_test_sequence_busy():
            return
        thr = getattr(self, "_test_sequence_thread", None)
        if thr is not None and thr.isRunning():
            QMessageBox.information(
                self,
                "Run",
                "The previous test sequence is still stopping. Try again in a moment.",
            )
            return
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
        self._set_test_status("Running", "#2196F3")  # blue
        self._set_pass_fail("--", "#555")  # keep gray until result
        if hasattr(self, "main_failure_reason"):
            self.main_failure_reason.clear()
        self._sync_tests_pass_fail_panel_from_recipe(recipe)
        try:
            self._rebuild_result_tab_graph_layout(recipe)
        except Exception:
            pass
        try:
            from operations.test_sequence_executor import TestSequenceExecutor, TestSequenceThread
            from viewmodel.sequence_instrument_bridge import SequenceInstrumentBridge

            bridge = SequenceInstrumentBridge(self._viewmodel)
            self._liv_sequence_bridge = bridge
            self._test_sequence_executor = TestSequenceExecutor(self)
            self._test_sequence_executor.set_test_sequence(seq, recipe)
            self._test_sequence_executor.set_sequence_bridge(bridge)
            self._test_sequence_executor.log_message.connect(
                self._on_status_log_message, QtCompat.QueuedConnection
            )
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
            _qc = QtCompat.QueuedConnection
            cast(Any, self._test_sequence_executor.liv_test_result).connect(self._on_liv_result, _qc)
            cast(Any, self._test_sequence_executor.per_test_result).connect(self._on_per_result, _qc)
            cast(Any, self._test_sequence_executor.sequence_step_failed).connect(
                self._on_sequence_step_failed, QtCompat.QueuedConnection
            )
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
            # Blocking: if the executor falls back to this signal, the worker must not start the sweep
            # until the PER window is shown and live signals are connected (same idea as invokeMethod).
            cast(Any, self._test_sequence_executor.per_process_window_requested).connect(
                self._open_per_test_window, QtCompat.BlockingQueuedConnection
            )
            cast(Any, self._test_sequence_executor.spectrum_process_window_requested).connect(
                self._open_spectrum_test_window, _qc
            )
            cast(Any, self._test_sequence_executor.stability_test_result).connect(
                self._on_stability_test_result, _qc
            )
            cast(Any, self._test_sequence_executor.live_arroyo).connect(
                self._on_arroyo_readings_updated, _qc
            )
            self._main_tab_sequence_ui_locked = True
            self._refresh_main_tab_sequence_controls_enabled()
            self._test_sequence_thread.start()
        except Exception as e:
            self._main_tab_sequence_ui_locked = False
            self._test_sequence_executor = None
            self._test_sequence_thread = None
            self._liv_sequence_bridge = None
            self._set_test_status("READY", "#555")
            self._set_pass_fail("--", "#555")
            self._tests_pass_fail_reset_placeholder()
            self._refresh_main_tab_sequence_controls_enabled()
            QMessageBox.warning(self, "Run", "Could not start test sequence: {}".format(e))

    @pyqtSlot()
    def pausePollingForLiv(self):
        """Called from LIV worker thread via QMetaObject.invokeMethod so timers are stopped on main thread."""
        b = getattr(self, "_liv_sequence_bridge", None)
        if b is not None and hasattr(b, "pause_for_liv") and callable(b.pause_for_liv):
            b.pause_for_liv()

    @pyqtSlot()
    def pausePollingForStability(self):
        """Same as ``pausePollingForLiv`` but keeps Gentec polling (TS does not use Gentec)."""
        b = getattr(self, "_liv_sequence_bridge", None)
        if b is not None and hasattr(b, "pause_for_temperature_stability") and callable(
            b.pause_for_temperature_stability
        ):
            b.pause_for_temperature_stability()

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
        if hasattr(self._viewmodel, "schedule_thorlabs_readback_refresh"):
            self._viewmodel.schedule_thorlabs_readback_refresh()

    def _on_stop_clicked(self):
        # Safety: always request laser OFF when user presses Stop (worker completes command; UI shows OFF immediately).
        try:
            if hasattr(self._viewmodel, "set_arroyo_laser_output"):
                self._viewmodel.set_arroyo_laser_output(False)
        except Exception:
            pass
        try:
            self._arroyo_laser_on = False
            self._arroyo_update_laser_tec_ui()
        except Exception:
            pass
        # Immediately stop any running Ando sweep so blocking waits exit fast.
        try:
            bridge = getattr(self._test_sequence_executor, "_bridge", None) if self._test_sequence_executor else None
            ando = bridge.get_instrument("Ando") if bridge is not None else None
            if ando is not None and getattr(ando, "is_connected", lambda: False)():
                ss = getattr(ando, "stop_sweep", None)
                if callable(ss):
                    ss()
        except Exception:
            pass
        if self._test_sequence_executor is not None:
            self._on_status_log_message(
                "STOP: Stop requested — aborting current step."
            )
            self._set_test_status("Stopping...", "#FF9800")
            self._test_sequence_executor.stop()
        else:
            self._on_status_log_message("STOP: Stop pressed (no test sequence running; laser off if connected).")
            self._set_test_status("STOP", "#c62828")
        # Re-enable Start New / Run immediately; Run stays blocked until the QThread exits (see _on_run_clicked).
        self._main_tab_sequence_ui_locked = False
        self._refresh_main_tab_sequence_controls_enabled()
        try:
            QApplication.processEvents()
        except Exception:
            pass
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
        if self._is_test_sequence_busy():
            return
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
                        self._recipe_tab_data = data
                        self._recipe_tab_path = recipe_path
                    else:
                        self._current_recipe_data = None
                        self._current_recipe_path = None
                        self._recipe_tab_data = None
                        self._recipe_tab_path = None
                        QMessageBox.warning(
                            self,
                            "Recipe",
                            "Could not read or parse the recipe file:\n{}".format(recipe_path),
                        )
                except Exception as e:
                    self._current_recipe_data = None
                    self._current_recipe_path = None
                    self._recipe_tab_data = None
                    self._recipe_tab_path = None
                    QMessageBox.warning(
                        self,
                        "Recipe",
                        "Could not load recipe:\n{}\n\n{}".format(recipe_path, e),
                    )
            else:
                self._current_recipe_data = None
                self._current_recipe_path = None
                self._recipe_tab_data = None
                self._recipe_tab_path = None
            self._refresh_recipe_tab()
            data = getattr(self, "_current_recipe_data", None)
            if isinstance(data, dict):
                wl_dialog = self._parse_details_wavelength_float()
                wl_eff = wl_dialog if wl_dialog is not None else self._wavelength_nm_from_recipe_dict(data)
                try:
                    self._apply_wavemeter_range_from_recipe(data, wavelength_nm_override=wl_eff)
                except Exception:
                    pass
                try:
                    self._sync_manual_powermeter_wavelength_spin_from_recipe()
                except Exception:
                    pass
                if wl_eff is not None and float(wl_eff) > 0:
                    try:
                        sp = getattr(self, "_manual_pm_wavelength_spin", None)
                        if sp is not None:
                            lo, hi = sp.minimum(), sp.maximum()
                            wv = min(max(float(wl_eff), lo), hi)
                            sp.blockSignals(True)
                            sp.setValue(wv)
                            sp.blockSignals(False)
                    except Exception:
                        pass
                    try:
                        self._apply_powermeter_wavelength_after_start_new(float(wl_eff))
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
                self._sync_tests_pass_fail_panel_from_recipe(data)
                try:
                    self._rebuild_result_tab_graph_layout(data)
                except Exception:
                    pass
            else:
                self._tests_pass_fail_reset_placeholder()
                try:
                    self._rebuild_result_tab_graph_layout(None)
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

    def _liv_fiber_coupled_for_alignment(self) -> bool:
        """Same rule as LIV sequence: GENERAL.FiberCoupled / top-level; default True (fiber path)."""
        ex = getattr(self, "_test_sequence_executor", None)
        if ex is not None and hasattr(ex, "is_liv_fiber_coupled"):
            try:
                return bool(ex.is_liv_fiber_coupled())
            except Exception:
                pass
        data = getattr(self, "_current_recipe_data", None)
        if isinstance(data, dict):
            gen = data.get("GENERAL") or data.get("General") or {}
            if isinstance(gen, dict) and isinstance(gen.get("FiberCoupled"), bool):
                return bool(gen["FiberCoupled"])
            v = data.get("FiberCoupled")
            if isinstance(v, bool):
                return v
            if isinstance(v, str):
                return v.strip().lower() in ("1", "true", "yes", "on")
        return True

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
                align_existing.set_liv_recipe_params(
                    liv_params[0], liv_params[1], liv_params[2], self._liv_fiber_coupled_for_alignment()
                )
            if self._last_arroyo_readings:
                align_existing.update_laser_details(self._last_arroyo_readings)
            if hasattr(align_existing, "set_laser_state_from_main"):
                r = self._last_arroyo_readings
                if r is None or r.get("laser_on") is None or r.get("tec_on") is None:
                    align_existing.set_laser_state_from_main(self._arroyo_laser_on, self._arroyo_tec_on)
            if hasattr(self._viewmodel, "schedule_arroyo_readback_refresh"):
                self._viewmodel.schedule_arroyo_readback_refresh()
            elif hasattr(self._viewmodel, "refresh_arroyo_readings"):
                self._viewmodel.refresh_arroyo_readings()
            if hasattr(align_existing, "set_liv_sequence_options"):
                align_existing.set_liv_sequence_options(
                    require_laser_before_ando=from_liv_sequence,
                    close_delay_ms_on_ok=5000 if from_liv_sequence else 0,
                )
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
            self._alignment_window.set_liv_recipe_params(
                liv_params[0], liv_params[1], liv_params[2], self._liv_fiber_coupled_for_alignment()
            )
        if self._last_arroyo_readings:
            self._alignment_window.update_laser_details(self._last_arroyo_readings)
        if hasattr(self._alignment_window, "set_laser_state_from_main"):
            r = self._last_arroyo_readings
            if r is None or r.get("laser_on") is None or r.get("tec_on") is None:
                self._alignment_window.set_laser_state_from_main(self._arroyo_laser_on, self._arroyo_tec_on)
        if hasattr(self._viewmodel, "schedule_arroyo_readback_refresh"):
            self._viewmodel.schedule_arroyo_readback_refresh()
        elif hasattr(self._viewmodel, "refresh_arroyo_readings"):
            self._viewmodel.refresh_arroyo_readings()
        if hasattr(self._alignment_window, "set_liv_sequence_options"):
            self._alignment_window.set_liv_sequence_options(
                require_laser_before_ando=from_liv_sequence,
                close_delay_ms_on_ok=5000 if from_liv_sequence else 0,
            )
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
        # Arroyo laser OFF + TEC OFF + thread teardown: MainViewModel.shutdown() (also on aboutToQuit).
        if hasattr(self._viewmodel, "shutdown"):
            self._viewmodel.shutdown()
        event.accept()
