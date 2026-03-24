"""
Floating window for Temperature Stability 1/2: left RCP summary, right live plot.
Single white pyqtgraph plot with three series vs temperature (°C): FWHM (nm), SMSR (dB), peak λ (nm),
each on its own Y axis (left + two right axes) so scales stay readable.
"""
from typing import List, Optional, Tuple

from PyQt5.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QScrollArea,
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


def _fmt(v, default="—"):
    if v is None:
        return default
    try:
        return "{:.5g}".format(float(v))
    except Exception:
        return str(v)


class TemperatureStabilityWindow(QMainWindow):
    """Secondary-monitor window: recipe left, one combined stability plot (white) on the right."""

    stop_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(1000, 680)
        self.resize(1180, 760)
        self.setPalette(get_dark_palette())
        self.setStyleSheet(main_stylesheet())
        self.setAttribute(Qt.WA_DeleteOnClose, True)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(14)

        left = QWidget()
        left.setMinimumWidth(300)
        left.setMaximumWidth(440)
        left_l = QVBoxLayout(left)
        left_l.setContentsMargins(0, 0, 0, 0)

        grp = QGroupBox("Temperature stability RCP")
        grp.setStyleSheet(
            "QGroupBox { font-weight: bold; font-size: 13px; color: #e6e6e6; } "
            "QLabel { color: #c8c8c8; font-size: 11px; }"
        )
        form = QFormLayout(grp)
        self._labels = {}
        for key, title in [
            ("slot", "Slot"),
            ("initial_c", "Initial T (°C)"),
            ("max_c", "Max T (°C)"),
            ("step_c", "Step (°C)"),
            ("recovery_nm", "FWHM recovery (nm)"),
            ("span_nm", "Narrow span (nm)"),
            ("smpl", "Sampling (pts)"),
        ]:
            lb = QLabel("—")
            self._labels[key] = lb
            form.addRow(title + ":", lb)
        left_l.addWidget(grp)

        log_grp = QGroupBox("Log")
        log_grp.setStyleSheet(grp.styleSheet())
        from PyQt5.QtWidgets import QPlainTextEdit

        self._log = QPlainTextEdit()
        self._log.setReadOnly(True)
        self._log.setMaximumHeight(180)
        self._log.setStyleSheet("background: #252528; color: #b0bec5; font-size: 10px;")
        log_grp_layout = QVBoxLayout(log_grp)
        log_grp_layout.addWidget(self._log)
        left_l.addWidget(log_grp)

        ctrl = QGroupBox("Control")
        ctrl.setStyleSheet(
            "QGroupBox { font-weight: bold; font-size: 12px; color: #e6e6e6; } "
            "QLabel { color: #9e9e9e; font-size: 10px; }"
        )
        cl = QVBoxLayout(ctrl)
        self._stop_btn = QPushButton("Stop sequence")
        self._stop_btn.clicked.connect(self.stop_requested.emit)
        cl.addWidget(self._stop_btn)
        left_l.addWidget(ctrl)
        left_l.addStretch()

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(left)
        scroll.setMinimumWidth(320)
        main_layout.addWidget(scroll, 0)

        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        self._p1 = None
        self._vb_smsr = None
        self._vb_peak = None
        self._curve_fwhm = None
        self._curve_smsr = None
        self._curve_peak = None
        self._plot_widget = None

        if _PG_AVAILABLE and pg is not None:
            title_lbl = QLabel("FWHM / SMSR / Peak wavelength vs Temperature (°C)")
            title_lbl.setStyleSheet("font-weight: bold; font-size: 13px; color: #e6e6e6;")
            rl.addWidget(title_lbl)

            pw = pg.PlotWidget()
            self._plot_widget = pw
            pw.setBackground("w")
            p1 = pw.getPlotItem()
            self._p1 = p1
            p1.getViewBox().setBackgroundColor((255, 255, 255))
            p1.showGrid(x=True, y=True, alpha=0.45)
            axis_pen = pg.mkPen(color="#333333", width=1)
            p1.setLabel("bottom", "Temperature (°C)", color="#333333")
            p1.setLabel("left", "FWHM (nm)", color="#333333")
            p1.layout.setColumnMinimumWidth(0, 72)
            for axn in ("left", "bottom"):
                ax = p1.getAxis(axn)
                ax.setPen(axis_pen)
                ax.setTextPen(axis_pen)

            legend = p1.addLegend(offset=(10, 10), labelTextColor="#333333")
            legend.setParentItem(p1.vb)
            legend.anchor((1, 1), (1, 1))

            # Main ViewBox behind overlays (same pattern as LIV window).
            p1.vb.setZValue(-100)

            self._curve_fwhm = pw.plot(
                [],
                [],
                pen=pg.mkPen("#1565c0", width=2),
                name="FWHM (nm)",
                symbol="o",
                symbolSize=6,
                symbolBrush="#1565c0",
                symbolPen=pg.mkPen("#1565c0"),
            )

            p2 = pg.ViewBox()
            p1.showAxis("right")
            p1.scene().addItem(p2)
            p1.getAxis("right").linkToView(p2)
            p2.setXLink(p1.vb)
            p2.setZValue(10)
            self._vb_smsr = p2
            p1.getAxis("right").setLabel("SMSR (dB)", color="#333333")
            p1.getAxis("right").setPen(axis_pen)
            p1.getAxis("right").setTextPen(axis_pen)
            self._curve_smsr = pg.PlotDataItem(
                [],
                [],
                pen=pg.mkPen("#2e7d32", width=2),
                name="SMSR (dB)",
                symbol="s",
                symbolSize=5,
                symbolBrush="#2e7d32",
                symbolPen=pg.mkPen("#2e7d32"),
            )
            p2.addItem(self._curve_smsr)
            legend.addItem(self._curve_smsr, "SMSR (dB)")

            p3 = pg.ViewBox()
            ax3 = pg.AxisItem("right")
            p1.layout.addItem(ax3, 2, 3)
            p1.layout.setColumnMinimumWidth(3, 76)
            p1.scene().addItem(p3)
            ax3.linkToView(p3)
            p3.setXLink(p1.vb)
            p3.setZValue(10)
            self._vb_peak = p3
            ax3.setLabel("Peak λ (nm)", color="#333333")
            ax3.setPen(axis_pen)
            ax3.setTextPen(axis_pen)
            self._curve_peak = pg.PlotDataItem(
                [],
                [],
                pen=pg.mkPen("#c62828", width=2),
                name="Peak λ (nm)",
                symbol="t",
                symbolSize=5,
                symbolBrush="#c62828",
                symbolPen=pg.mkPen("#c62828"),
            )
            p3.addItem(self._curve_peak)
            legend.addItem(self._curve_peak, "Peak λ (nm)")

            def _sync_vbs():
                r = p1.vb.sceneBoundingRect()
                p2.setGeometry(r)
                p3.setGeometry(r)
                p2.linkedViewChanged(p1.vb, p2.XAxis)
                p3.linkedViewChanged(p1.vb, p3.XAxis)

            _sync_vbs()
            p1.vb.sigResized.connect(_sync_vbs)
            self._sync_stability_vbs = _sync_vbs

            rl.addWidget(pw, 1)
        else:
            rl.addWidget(QLabel("pyqtgraph required for stability plots."))
        main_layout.addWidget(right, 1)

        self._tx: list = []
        self._fy: list = []
        self._sy: list = []
        self._py: list = []

    def _autorange_stability_axes(self) -> None:
        """Fit X and each Y axis to current data (three separate scales)."""
        if not _PG_AVAILABLE or self._p1 is None:
            return
        tx = self._tx
        if not tx:
            return
        try:
            xs = [float(x) for x in tx]
            x0, x1 = min(xs), max(xs)
            dx = x1 - x0
            px = max(dx * 0.06, 0.25) if dx > 1e-12 else 0.5
            self._p1.vb.setXRange(x0 - px, x1 + px, padding=0)
        except Exception:
            pass

        def _yrange(vals: List[float]) -> Optional[Tuple[float, float]]:
            if not vals:
                return None
            ys = []
            for v in vals:
                try:
                    ys.append(float(v))
                except (TypeError, ValueError):
                    continue
            if not ys:
                return None
            lo, hi = min(ys), max(ys)
            span = hi - lo
            pad = max(span * 0.12, 1e-12)
            if span < 1e-18:
                pad = max(abs(lo) * 0.05, 0.01)
            return lo - pad, hi + pad

        r_f = _yrange(self._fy)
        if r_f is not None:
            self._p1.vb.setYRange(r_f[0], r_f[1], padding=0)
        r_s = _yrange(self._sy)
        if r_s is not None and self._vb_smsr is not None:
            self._vb_smsr.setYRange(r_s[0], r_s[1], padding=0)
        r_p = _yrange(self._py)
        if r_p is not None and self._vb_peak is not None:
            self._vb_peak.setYRange(r_p[0], r_p[1], padding=0)

    def set_window_title_slot(self, slot: int) -> None:
        self.setWindowTitle("Temperature Stability {}".format(slot))

    def set_params(self, params: dict) -> None:
        p = params or {}
        slot = int(p.get("slot", 1))
        self.set_window_title_slot(slot)
        if "slot" in self._labels:
            self._labels["slot"].setText(str(slot))
        pr = p.get("params") or {}
        if "initial_c" in self._labels:
            self._labels["initial_c"].setText(_fmt(pr.get("initial_temp_c")))
        if "max_c" in self._labels:
            self._labels["max_c"].setText(_fmt(pr.get("max_temp_c")))
        if "step_c" in self._labels:
            self._labels["step_c"].setText(_fmt(pr.get("step_temp_c")))
        if "recovery_nm" in self._labels:
            self._labels["recovery_nm"].setText(_fmt(pr.get("fwhm_recovery_threshold_nm")))
        if "span_nm" in self._labels:
            self._labels["span_nm"].setText(_fmt(pr.get("ando_span_nm")))
        if "smpl" in self._labels:
            self._labels["smpl"].setText(_fmt(pr.get("ando_sampling_points")))

    def clear_plots(self) -> None:
        self._tx = []
        self._fy = []
        self._sy = []
        self._py = []
        if _PG_AVAILABLE and self._curve_fwhm is not None:
            self._curve_fwhm.setData([], [])
            if self._curve_smsr is not None:
                self._curve_smsr.setData([], [])
            if self._curve_peak is not None:
                self._curve_peak.setData([], [])

    def append_live_point(self, t_c: float, fwhm: float, smsr: float, peak_nm: float) -> None:
        self._tx.append(float(t_c))
        self._fy.append(float(fwhm))
        self._sy.append(float(smsr))
        self._py.append(float(peak_nm))
        if _PG_AVAILABLE and self._curve_fwhm is not None:
            self._curve_fwhm.setData(self._tx, self._fy)
            if self._curve_smsr is not None:
                self._curve_smsr.setData(self._tx, self._sy)
            if self._curve_peak is not None:
                self._curve_peak.setData(self._tx, self._py)
            self._autorange_stability_axes()
            if callable(getattr(self, "_sync_stability_vbs", None)):
                try:
                    self._sync_stability_vbs()
                except Exception:
                    pass

    def append_process_log(self, msg: str) -> None:
        self._log.appendPlainText(msg)

    def clear_process_log(self) -> None:
        self._log.clear()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        try:
            set_dark_title_bar(int(self.winId()), True)
        except Exception:
            pass
