"""
Spectrum test sequence window (secondary monitor).
Left: Spectrum RCP details, then live wavemeter reading (instrument readbacks during the step).
Right: Ando OSA live trace — WDATA (nm) vs LDATA (dBm), same styling as Main PER graph.
"""
from PyQt5.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QFrame,
    QScrollArea,
    QPlainTextEdit,
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QShowEvent

try:
    import pyqtgraph as pg
    _PG_AVAILABLE = True
except ImportError:
    _PG_AVAILABLE = False
    pg = None

from view.dark_theme import get_dark_palette, main_stylesheet, set_dark_title_bar
from view.temperature_stability_plot import compact_simple_xy_plot_axes
from view.plot_series_checkboxes import freeze_plot_navigation

try:
    from operations.spectrum.trace_plotting import (
        pair_trace_floats,
        spectrum_plot_x_range_nm,
        spectrum_plot_y_range_dbm,
        spectrum_wavemeter_bottom_axis_label,
    )
except ImportError:
    pair_trace_floats = None  # type: ignore[misc, assignment]
    spectrum_plot_x_range_nm = None  # type: ignore[misc, assignment]
    spectrum_plot_y_range_dbm = None  # type: ignore[misc, assignment]
    spectrum_wavemeter_bottom_axis_label = None  # type: ignore[misc, assignment]


def _fmt(v, default="—"):
    if v is None:
        return default
    try:
        return "{:.4g}".format(float(v))
    except Exception:
        return str(v)


class SpectrumTestSequenceWindow(QMainWindow):
    """Floating window opened when a Spectrum test step starts (second monitor)."""

    stop_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Spectrum Process")
        self.setMinimumSize(980, 640)
        self.resize(1140, 720)
        self.setPalette(get_dark_palette())
        self.setStyleSheet(main_stylesheet())
        self.setAttribute(Qt.WA_DeleteOnClose, True)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(16)

        # ----- Left: RCP + wavemeter + control -----
        left_widget = QWidget()
        left_widget.setMinimumWidth(320)
        left_widget.setMaximumWidth(460)
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        params_group = QGroupBox("Spectrum RCP (recipe)")
        params_group.setStyleSheet(
            "QGroupBox { font-weight: bold; font-size: 13px; color: #e6e6e6; } "
            "QLabel { color: #c8c8c8; font-size: 12px; }"
        )
        form = QFormLayout(params_group)
        self._labels = {}
        for key, title in [
            ("center_nm", "Center (nm)"),
            ("span_nm", "Span (nm)"),
            ("resolution_nm", "Resolution (nm)"),
            ("sampling_points", "Sampling (pts)"),
            ("ref_level_dbm", "Ref level (dBm)"),
            ("level_scale_db_per_div", "Level scale (dB/div)"),
            ("temperature_c", "Temperature (°C)"),
            ("laser_current_mA", "Laser current (mA)"),
            ("sensitivity", "Sensitivity"),
            ("analysis", "Analysis"),
        ]:
            lb = QLabel("—")
            self._labels[key] = lb
            form.addRow(title + ":", lb)
        left_layout.addWidget(params_group)

        wm_group = QGroupBox("Wavemeter (instrument)")
        wm_group.setStyleSheet(
            "QGroupBox { font-weight: bold; font-size: 13px; color: #e6e6e6; } "
            "QLabel { color: #c8c8c8; font-size: 12px; }"
        )
        wm_form = QFormLayout(wm_group)
        self._wm_value = QLabel("—")
        self._wm_value.setStyleSheet("color: #aed581; font-size: 14px; font-weight: bold;")
        wm_form.addRow("Wavelength (nm):", self._wm_value)
        wm_hint = QLabel("Live read while Spectrum runs (same GPIB session as test).")
        wm_hint.setWordWrap(True)
        wm_hint.setStyleSheet("color: #9e9e9e; font-size: 10px;")
        wm_form.addRow(wm_hint)
        left_layout.addWidget(wm_group)

        ctrl_group = QGroupBox("Control")
        ctrl_group.setStyleSheet(
            "QGroupBox { font-weight: bold; font-size: 12px; color: #e6e6e6; } "
            "QLabel { color: #c8c8c8; font-size: 11px; }"
        )
        ctrl_layout = QVBoxLayout(ctrl_group)
        self._stop_btn = QPushButton("Stop")
        self._stop_btn.setMinimumHeight(34)
        self._stop_btn.setStyleSheet(
            "QPushButton { background-color: #f44336; color: white; font-weight: bold; padding: 8px 16px; } "
            "QPushButton:hover { background-color: #d32f2f; }"
        )
        self._stop_btn.clicked.connect(self.stop_requested.emit)
        ctrl_layout.addWidget(self._stop_btn)
        self._status = QLabel("Running Spectrum (Ando + wavemeter)…")
        self._status.setWordWrap(True)
        self._status.setStyleSheet("color: #b0bec5; font-size: 12px;")
        ctrl_layout.addWidget(self._status)
        left_layout.addWidget(ctrl_group)

        log_group = QGroupBox("Process log")
        log_group.setStyleSheet(
            "QGroupBox { font-weight: bold; font-size: 12px; color: #e6e6e6; } "
            "QPlainTextEdit { background-color: #1e1e1e; color: #c8c8c8; font-size: 11px; }"
        )
        log_layout = QVBoxLayout(log_group)
        self._process_log = QPlainTextEdit()
        self._process_log.setReadOnly(True)
        self._process_log.setMinimumHeight(120)
        self._process_log.setPlaceholderText("Spectrum step messages appear here…")
        log_layout.addWidget(self._process_log)
        left_layout.addWidget(log_group)

        left_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidget(left_widget)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        main_layout.addWidget(scroll)

        # ----- Right: Ando live graph -----
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Ando OSA — live sweep (Level dBm vs wavelength nm)")
        title.setStyleSheet("font-weight: bold; font-size: 13px; color: #e6e6e6;")
        right_layout.addWidget(title)

        if not _PG_AVAILABLE:
            right_layout.addWidget(QLabel("pyqtgraph required for graph display."))
            self._plot_widget = None
            self._spectrum_plot_item = None
            self._spectrum_bottom_axis_color = "#333333"
            self._spectrum_bottom_default_label = "Wavelength WDATA (nm)"
            self._curve = None
        else:
            pw = pg.PlotWidget()
            pw.setBackground("w")
            p = pw.getPlotItem()
            p.getViewBox().setBackgroundColor((255, 255, 255))
            p.showGrid(x=True, y=True, alpha=0.35)
            _ax = "#333333"
            p.setLabel("bottom", "Wavelength WDATA (nm)", color=_ax)
            p.setLabel("left", "Level LDATA (dBm)", color=_ax)
            axis_pen = pg.mkPen(color=_ax, width=1)
            p.getAxis("left").setPen(axis_pen)
            p.getAxis("left").setTextPen(axis_pen)
            p.getAxis("bottom").setPen(axis_pen)
            p.getAxis("bottom").setTextPen(axis_pen)
            self._plot_widget = pw
            self._spectrum_plot_item = p
            self._spectrum_bottom_axis_color = _ax
            self._spectrum_bottom_default_label = "Wavelength WDATA (nm)"
            self._curve = pw.plot([], [], pen=pg.mkPen("#000000", width=1.5), antialias=True)
            freeze_plot_navigation(p)
            compact_simple_xy_plot_axes(p, pw)
            right_layout.addWidget(pw, 1)

        self._rcp_center_nm = None
        self._rcp_span_nm = None
        self._rcp_ref_dbm = None
        self._rcp_ls = None

        self._footnote = QLabel(
            "Live trace: sweep 1 plots as soon as WDATA/LDATA is read; sweep 2 replaces the trace when ready (no intentional blank gap)."
        )
        self._footnote.setStyleSheet("color: #9e9e9e; font-size: 10px;")
        right_layout.addWidget(self._footnote)
        main_layout.addWidget(right_widget, 1)

    def showEvent(self, event: QShowEvent):
        super().showEvent(event)
        try:
            set_dark_title_bar(int(self.winId()), True)
        except Exception:
            pass

    def set_params(self, params: dict):
        params = params or {}
        for k, lbl in self._labels.items():
            v = params.get(k)
            if k in ("analysis", "sensitivity"):
                lbl.setText(str(v) if v not in (None, "") else "—")
            else:
                lbl.setText(_fmt(v))

        def _to_f(key: str):
            v = params.get(key)
            if v is None or v == "":
                return None
            try:
                return float(v)
            except Exception:
                return None

        self._rcp_center_nm = _to_f("center_nm")
        self._rcp_span_nm = _to_f("span_nm")
        self._rcp_ref_dbm = _to_f("ref_level_dbm")
        self._rcp_ls = _to_f("level_scale_db_per_div")
        self._apply_axes_from_rcp()

    def _apply_axes_from_rcp(self) -> None:
        """X = CTR ± SPAN/2 (Ando RCP); Y = REFL top, LSCL × divisions down (log scale)."""
        pw = getattr(self, "_plot_widget", None)
        if pw is None or spectrum_plot_x_range_nm is None:
            return
        vb = pw.getPlotItem().getViewBox()
        c = self._rcp_center_nm
        s = self._rcp_span_nm
        if c is not None and s is not None and float(s) > 0:
            x0, x1 = spectrum_plot_x_range_nm(c, s)
            vb.setXRange(x0, x1, padding=0.02)
        r = self._rcp_ref_dbm
        ls = self._rcp_ls
        if spectrum_plot_y_range_dbm is not None and r is not None and ls is not None:
            yr = spectrum_plot_y_range_dbm(r, ls)
            if yr is not None:
                vb.setYRange(yr[0], yr[1], padding=0.02)

    def _apply_wavemeter_bottom_axis_label(self, nm) -> None:
        """Bottom axis title = wavemeter nm (full decimals); ticks stay WDATA."""
        pi = getattr(self, "_spectrum_plot_item", None)
        if pi is None:
            return
        tc = getattr(self, "_spectrum_bottom_axis_color", "#333333")
        default = getattr(self, "_spectrum_bottom_default_label", "Wavelength WDATA (nm)")
        if spectrum_wavemeter_bottom_axis_label is not None:
            txt = spectrum_wavemeter_bottom_axis_label(nm, default=default)
        else:
            txt = default if nm is None else "{} nm".format(float(nm))
        try:
            pi.setLabel("bottom", txt, color=tc)
        except Exception:
            pass

    def set_wavemeter_reading(self, nm) -> None:
        """Live wavelength from wavemeter (nm); None shows —. Plot bottom axis shows same reading as its label."""
        if nm is None:
            self._wm_value.setText("—")
            self._apply_wavemeter_bottom_axis_label(None)
            return
        try:
            v = float(nm)
            if spectrum_wavemeter_bottom_axis_label is not None:
                self._wm_value.setText(spectrum_wavemeter_bottom_axis_label(v, default="—"))
            else:
                s = ("{:.12f}".format(v)).rstrip("0").rstrip(".")
                self._wm_value.setText(s + " nm")
        except Exception:
            self._wm_value.setText(str(nm))
        self._apply_wavemeter_bottom_axis_label(nm)

    def set_live_trace(self, wdata, ldata) -> None:
        """Plot Ando WDATA vs LDATA (instrument readback; coerced to float for pyqtgraph)."""
        if self._curve is None:
            return
        if pair_trace_floats is not None:
            w, l_ = pair_trace_floats(wdata, ldata)
        else:
            w = list(wdata or [])
            l_ = list(ldata or [])
            n = min(len(w), len(l_))
            w, l_ = w[:n], l_[:n]
        n = len(w)
        if n:
            self._curve.setData(w, l_)
            try:
                pw = getattr(self, "_plot_widget", None)
                if pw is not None:
                    vb = pw.getPlotItem().getViewBox()
                    self._apply_axes_from_rcp()
                    r = self._rcp_ref_dbm
                    ls = self._rcp_ls
                    y_from_rcp = (
                        spectrum_plot_y_range_dbm is not None
                        and r is not None
                        and ls is not None
                        and spectrum_plot_y_range_dbm(r, ls) is not None
                    )
                    if not y_from_rcp and l_:
                        lo = min(l_)
                        hi = max(l_)
                        pad = max(0.5, (hi - lo) * 0.1)
                        vb.setYRange(lo - pad, hi + pad, padding=0.02)
            except Exception:
                pass
        else:
            self._curve.setData([], [])
            if (wdata or ldata) and n == 0:
                self._status.setText("Plot: no finite WDATA/LDATA pairs — check Ando trace read.")

    def clear_live_plot(self) -> None:
        if self._curve is not None:
            self._curve.setData([], [])
        self._apply_wavemeter_bottom_axis_label(None)

    def set_status(self, text: str):
        self._status.setText(text or "")

    def clear_process_log(self) -> None:
        if hasattr(self, "_process_log"):
            self._process_log.clear()

    def append_process_log(self, text: str) -> None:
        pl = getattr(self, "_process_log", None)
        if pl is None:
            return
        t = (text or "").rstrip()
        if not t:
            return
        pl.appendPlainText(t)
        sb = pl.verticalScrollBar()
        sb.setValue(sb.maximum())

    def set_finished(self, passed: bool, detail: str = ""):
        self._stop_btn.setEnabled(False)
        if passed:
            self._status.setStyleSheet("color: #81c784; font-size: 12px; font-weight: bold;")
            self._status.setText("Finished — PASS\n" + (detail or ""))
        else:
            self._status.setStyleSheet("color: #ef9a9a; font-size: 12px; font-weight: bold;")
            self._status.setText("Finished — FAIL\n" + (detail or ""))
