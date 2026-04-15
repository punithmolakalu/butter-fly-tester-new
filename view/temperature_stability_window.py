"""
Floating window for Temperature Stability 1/2: left RCP summary, right live plot.
Single white pyqtgraph plot with five series vs temperature (°C); series toggles and color swatches sit above the plot (no in-plot legend).
"""
import math
import time
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
from view.plot_series_checkboxes import (
    STABILITY_RAMP_C_H_COLORS,
    STABILITY_RAMP_H_C_COLORS,
    STABILITY_SERIES_LABELS,
    freeze_plot_navigation,
    make_series_checkbox_row,
    pg_curve_axis_list,
    stability_arrays_with_duplicate_x_breaks,
)
from view.temperature_stability_plot import (
    STABILITY_PLOT_COL_LEFT,
    STABILITY_PLOT_COL_RIGHT_EXTRA,
    STABILITY_PLOT_COL_RIGHT_SMSR,
    compact_stability_multi_y_axes,
)


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
        self._vb_pk_lv = None
        self._vb_fwhm = None
        self._vb_thorlabs = None
        self._curve_peak_nm = None
        self._curve_peak_nm_hc = None
        self._curve_smsr = None
        self._curve_smsr_hc = None
        self._curve_pk_lv = None
        self._curve_pk_lv_hc = None
        self._curve_fwhm = None
        self._curve_fwhm_hc = None
        self._curve_thorlabs = None
        self._curve_thorlabs_hc = None
        self._plot_widget = None
        self._stability_series_spec = None

        if _PG_AVAILABLE and pg is not None:
            pw = pg.PlotWidget()
            self._plot_widget = pw
            pw.setBackground("w")
            p1 = pw.getPlotItem()
            self._p1 = p1
            p1.getViewBox().setBackgroundColor((255, 255, 255))
            p1.showGrid(x=True, y=True, alpha=0.45)
            axis_pen = pg.mkPen(color="#333333", width=1)
            tc = "#333333"
            _ch = STABILITY_RAMP_C_H_COLORS
            _hc = STABILITY_RAMP_H_C_COLORS
            p1.setLabel("bottom", "Temperature (°C)", color=tc)
            p1.setLabel("left", "Peak λ (nm)", color=_ch[0])
            p1.layout.setColumnMinimumWidth(0, STABILITY_PLOT_COL_LEFT)
            p1.getAxis("bottom").setPen(axis_pen)
            p1.getAxis("bottom").setTextPen(axis_pen)
            p1.getAxis("left").setPen(pg.mkPen(color=_ch[0], width=1))
            p1.getAxis("left").setTextPen(pg.mkPen(color=_ch[0]))

            p1.vb.setZValue(-100)

            self._curve_peak_nm = pw.plot(
                [],
                [],
                pen=pg.mkPen(_ch[0], width=2),
                symbol="s",
                symbolSize=6,
                symbolBrush=_ch[0],
                symbolPen=pg.mkPen(_ch[0]),
            )
            self._curve_peak_nm_hc = pw.plot(
                [],
                [],
                pen=pg.mkPen(_hc[0], width=2),
                symbol="s",
                symbolSize=6,
                symbolBrush=_hc[0],
                symbolPen=pg.mkPen(_hc[0]),
            )

            p2 = pg.ViewBox()
            p1.showAxis("right")
            p1.scene().addItem(p2)
            p1.getAxis("right").linkToView(p2)
            p2.setXLink(p1.vb)
            p2.setZValue(10)
            self._vb_smsr = p2
            p1.getAxis("right").setLabel("SMSR (dB)", color=_ch[2])
            p1.getAxis("right").setPen(pg.mkPen(color=_ch[2], width=1))
            p1.getAxis("right").setTextPen(pg.mkPen(color=_ch[2]))
            self._curve_smsr = pg.PlotDataItem(
                [],
                [],
                pen=pg.mkPen(_ch[2], width=2),
                name="SMSR",
                symbol="x",
                symbolSize=7,
                symbolBrush=_ch[2],
                symbolPen=pg.mkPen(_ch[2]),
            )
            p2.addItem(self._curve_smsr)
            self._curve_smsr_hc = pg.PlotDataItem(
                [],
                [],
                pen=pg.mkPen(_hc[2], width=2),
                name="SMSR h→c",
                symbol="x",
                symbolSize=7,
                symbolBrush=_hc[2],
                symbolPen=pg.mkPen(_hc[2]),
            )
            p2.addItem(self._curve_smsr_hc)

            p3 = pg.ViewBox()
            ax3 = pg.AxisItem("right")
            p1.layout.addItem(ax3, 2, 3)
            p1.layout.setColumnMinimumWidth(3, STABILITY_PLOT_COL_RIGHT_EXTRA)
            p1.scene().addItem(p3)
            ax3.linkToView(p3)
            p3.setXLink(p1.vb)
            p3.setZValue(10)
            self._vb_pk_lv = p3
            ax3.setLabel("Peak lvl (dBm)", color=_ch[3])
            ax3.setPen(pg.mkPen(color=_ch[3], width=1))
            ax3.setTextPen(pg.mkPen(color=_ch[3]))
            self._curve_pk_lv = pg.PlotDataItem(
                [],
                [],
                pen=pg.mkPen(_ch[3], width=2, style=Qt.DashLine),
                name="Peak level",
                symbol="o",
                symbolSize=5,
                symbolBrush=_ch[3],
                symbolPen=pg.mkPen(_ch[3]),
            )
            p3.addItem(self._curve_pk_lv)
            self._curve_pk_lv_hc = pg.PlotDataItem(
                [],
                [],
                pen=pg.mkPen(_hc[3], width=2, style=Qt.DashLine),
                name="Peak level h→c",
                symbol="o",
                symbolSize=5,
                symbolBrush=_hc[3],
                symbolPen=pg.mkPen(_hc[3]),
            )
            p3.addItem(self._curve_pk_lv_hc)

            p4 = pg.ViewBox()
            ax4 = pg.AxisItem("right")
            p1.layout.addItem(ax4, 2, 4)
            p1.layout.setColumnMinimumWidth(4, STABILITY_PLOT_COL_RIGHT_EXTRA)
            p1.scene().addItem(p4)
            ax4.linkToView(p4)
            p4.setXLink(p1.vb)
            p4.setZValue(10)
            self._vb_fwhm = p4
            ax4.setLabel("FWHM (nm)", color=_ch[1])
            ax4.setPen(pg.mkPen(color=_ch[1], width=1))
            ax4.setTextPen(pg.mkPen(color=_ch[1]))
            self._curve_fwhm = pg.PlotDataItem(
                [],
                [],
                pen=pg.mkPen(_ch[1], width=2),
                name="FWHM",
                symbol="t",
                symbolSize=6,
                symbolBrush=_ch[1],
                symbolPen=pg.mkPen(_ch[1]),
            )
            p4.addItem(self._curve_fwhm)
            self._curve_fwhm_hc = pg.PlotDataItem(
                [],
                [],
                pen=pg.mkPen(_hc[1], width=2),
                name="FWHM h→c",
                symbol="t",
                symbolSize=6,
                symbolBrush=_hc[1],
                symbolPen=pg.mkPen(_hc[1]),
            )
            p4.addItem(self._curve_fwhm_hc)

            p5 = pg.ViewBox()
            ax5 = pg.AxisItem("right")
            p1.layout.addItem(ax5, 2, 5)
            p1.layout.setColumnMinimumWidth(5, STABILITY_PLOT_COL_RIGHT_EXTRA)
            p1.scene().addItem(p5)
            ax5.linkToView(p5)
            p5.setXLink(p1.vb)
            p5.setZValue(10)
            self._vb_thorlabs = p5
            ax5.setLabel("Thorlabs (mW)", color=_ch[4])
            ax5.setPen(pg.mkPen(color=_ch[4], width=1))
            ax5.setTextPen(pg.mkPen(color=_ch[4]))
            self._curve_thorlabs = pg.PlotDataItem(
                [],
                [],
                pen=pg.mkPen(_ch[4], width=2),
                name="Thorlabs",
                symbol="d",
                symbolSize=5,
                symbolBrush=_ch[4],
                symbolPen=pg.mkPen(_ch[4]),
            )
            p5.addItem(self._curve_thorlabs)
            self._curve_thorlabs_hc = pg.PlotDataItem(
                [],
                [],
                pen=pg.mkPen(_hc[4], width=2),
                name="Thorlabs h→c",
                symbol="d",
                symbolSize=5,
                symbolBrush=_hc[4],
                symbolPen=pg.mkPen(_hc[4]),
            )
            p5.addItem(self._curve_thorlabs_hc)

            def _sync_vbs():
                r = p1.vb.sceneBoundingRect()
                p2.setGeometry(r)
                p3.setGeometry(r)
                p4.setGeometry(r)
                p5.setGeometry(r)
                p2.linkedViewChanged(p1.vb, p2.XAxis)
                p3.linkedViewChanged(p1.vb, p3.XAxis)
                p4.linkedViewChanged(p1.vb, p4.XAxis)
                p5.linkedViewChanged(p1.vb, p5.XAxis)

            _sync_vbs()
            p1.vb.sigResized.connect(_sync_vbs)
            self._sync_stability_vbs = _sync_vbs

            for _ax in (
                p1.getAxis("left"),
                p1.getAxis("bottom"),
                p1.getAxis("right"),
                ax3,
                ax4,
                ax5,
            ):
                _fn = getattr(_ax, "enableAutoSIPrefix", None)
                if callable(_fn):
                    try:
                        _fn(False)
                    except Exception:
                        pass

            try:
                p1.layout.setColumnMinimumWidth(2, STABILITY_PLOT_COL_RIGHT_SMSR)
            except Exception:
                pass
            compact_stability_multi_y_axes(p1, [ax3, ax4, ax5], pw)

            freeze_plot_navigation(p1, p2, p3, p4, p5)
            for _vb in (p1.getViewBox(), p2, p3, p4, p5):
                try:
                    _vb.disableAutoRange()
                except Exception:
                    pass
            _sw_pairs = list(zip(STABILITY_RAMP_C_H_COLORS, STABILITY_RAMP_H_C_COLORS))
            self._stability_series_spec = [
                {"curve": self._curve_peak_nm, "curve_alt": self._curve_peak_nm_hc, "axis": p1.getAxis("left")},
                {"curve": self._curve_fwhm, "curve_alt": self._curve_fwhm_hc, "axis": ax4},
                {"curve": self._curve_smsr, "curve_alt": self._curve_smsr_hc, "axis": p1.getAxis("right")},
                {"curve": self._curve_pk_lv, "curve_alt": self._curve_pk_lv_hc, "axis": ax3},
                {"curve": self._curve_thorlabs, "curve_alt": self._curve_thorlabs_hc, "axis": ax5},
            ]
            ts_cb_row, _ = make_series_checkbox_row(
                self._stability_series_spec,
                STABILITY_SERIES_LABELS,
                legend=None,
                color_swatch_pairs=_sw_pairs,
            )
            rl.addWidget(ts_cb_row)
            _hint = QLabel("Swatch: left = cold→hot sweep · right = hot→cold verify")
            _hint.setStyleSheet("color: #9e9e9e; font-size: 10px;")
            _hint.setWordWrap(True)
            rl.addWidget(_hint)
            rl.addWidget(pw, 1)
        else:
            rl.addWidget(QLabel("pyqtgraph required for stability plots."))
        main_layout.addWidget(right, 1)

        self._tx_ch: list = []
        self._peak_nm_ch: list = []
        self._smsr_ch: list = []
        self._pk_dbm_ch: list = []
        self._fwhm_ch: list = []
        self._thor_ch: list = []
        self._tx_hc: list = []
        self._peak_nm_hc: list = []
        self._smsr_hc: list = []
        self._pk_dbm_hc: list = []
        self._fwhm_hc: list = []
        self._thor_hc: list = []

    def _autorange_stability_axes(self) -> None:
        """Fit X and each Y axis to current data (five separate scales; cold→hot + hot→cold traces)."""
        if not _PG_AVAILABLE or self._p1 is None:
            return
        xs: List[float] = []
        for seq in (getattr(self, "_tx_ch", None), getattr(self, "_tx_hc", None)):
            if not seq:
                continue
            for v in seq:
                try:
                    fv = float(v)
                except (TypeError, ValueError):
                    continue
                if math.isfinite(fv):
                    xs.append(fv)
        if not xs:
            for c in (getattr(self, "_curve_peak_nm", None), getattr(self, "_curve_peak_nm_hc", None)):
                if c is None:
                    continue
                try:
                    for x in pg_curve_axis_list(c, "x"):
                        try:
                            v = float(x)
                        except (TypeError, ValueError):
                            continue
                        if math.isfinite(v):
                            xs.append(v)
                except Exception:
                    pass
        if not xs:
            return
        try:
            x0, x1 = min(xs), max(xs)
            dx = x1 - x0
            if dx < 1e-12:
                pad = 0.15
            else:
                pad = max(dx * 0.10, 0.03)
            self._p1.vb.setXRange(x0 - pad, x1 + pad, padding=0)
        except Exception:
            pass

        def _yrange_from_curves(c1, c2) -> Optional[Tuple[float, float]]:
            ys: List[float] = []
            for c in (c1, c2):
                if c is None:
                    continue
                try:
                    for v in pg_curve_axis_list(c, "y"):
                        try:
                            y = float(v)
                        except (TypeError, ValueError):
                            continue
                        if math.isfinite(y):
                            ys.append(y)
                except Exception:
                    pass
            if not ys:
                return None
            lo, hi = min(ys), max(ys)
            span = hi - lo
            # Always include *all* points; add small padding so symbols aren't clipped by axes.
            pad = max(span * 0.12, 0.08)
            if span < 1e-12:
                pad = max(abs(lo) * 0.1, 0.1)
            return lo - pad, hi + pad

        def _vis_pair(c1, c2):
            v1 = c1 is None or not hasattr(c1, "isVisible") or c1.isVisible()
            v2 = c2 is None or not hasattr(c2, "isVisible") or c2.isVisible()
            return v1 or v2

        r_pk = _yrange_from_curves(self._curve_peak_nm, getattr(self, "_curve_peak_nm_hc", None))
        if r_pk is not None and _vis_pair(self._curve_peak_nm, getattr(self, "_curve_peak_nm_hc", None)):
            self._p1.vb.setYRange(r_pk[0], r_pk[1], padding=0)
        r_s = _yrange_from_curves(self._curve_smsr, getattr(self, "_curve_smsr_hc", None))
        if r_s is not None and self._vb_smsr is not None and _vis_pair(self._curve_smsr, getattr(self, "_curve_smsr_hc", None)):
            self._vb_smsr.setYRange(r_s[0], r_s[1], padding=0)
        r_lv = _yrange_from_curves(self._curve_pk_lv, getattr(self, "_curve_pk_lv_hc", None))
        if r_lv is not None and self._vb_pk_lv is not None and _vis_pair(self._curve_pk_lv, getattr(self, "_curve_pk_lv_hc", None)):
            self._vb_pk_lv.setYRange(r_lv[0], r_lv[1], padding=0)
        r_f = _yrange_from_curves(self._curve_fwhm, getattr(self, "_curve_fwhm_hc", None))
        if r_f is not None and self._vb_fwhm is not None and _vis_pair(self._curve_fwhm, getattr(self, "_curve_fwhm_hc", None)):
            self._vb_fwhm.setYRange(r_f[0], r_f[1], padding=0)
        r_th = _yrange_from_curves(self._curve_thorlabs, getattr(self, "_curve_thorlabs_hc", None))
        if r_th is not None and self._vb_thorlabs is not None and _vis_pair(self._curve_thorlabs, getattr(self, "_curve_thorlabs_hc", None)):
            self._vb_thorlabs.setYRange(r_th[0], r_th[1], padding=0)

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
        smsr_corr = bool(pr.get("smsr_correction_enabled", False))
        self._update_smsr_axis_label(smsr_corr)

    def _update_smsr_axis_label(self, correction_enabled: bool) -> None:
        """Refresh SMSR axis colour (label text is always 'SMSR (dB)')."""
        if self._p1 is None:
            return
        try:
            self._p1.getAxis("right").setLabel("SMSR (dB)", color=STABILITY_RAMP_C_H_COLORS[2])
        except Exception:
            pass

    def clear_plots(self) -> None:
        self._tx_ch = []
        self._peak_nm_ch = []
        self._smsr_ch = []
        self._pk_dbm_ch = []
        self._fwhm_ch = []
        self._thor_ch = []
        self._tx_hc = []
        self._peak_nm_hc = []
        self._smsr_hc = []
        self._pk_dbm_hc = []
        self._fwhm_hc = []
        self._thor_hc = []
        if _PG_AVAILABLE and self._curve_peak_nm is not None:
            for c in (
                self._curve_peak_nm,
                self._curve_peak_nm_hc,
                self._curve_smsr,
                self._curve_smsr_hc,
                self._curve_pk_lv,
                self._curve_pk_lv_hc,
                self._curve_fwhm,
                self._curve_fwhm_hc,
                self._curve_thorlabs,
                self._curve_thorlabs_hc,
            ):
                if c is not None:
                    c.setData([], [])
        try:
            self._last_plot_redraw_ts = 0.0
        except Exception:
            pass

    def append_live_point(
        self,
        t_c: float,
        fwhm: float,
        smsr: float,
        peak_nm: float,
        peak_dbm: float,
        thorlabs_mw: float,
        ramp_code: str = "c_h",
    ) -> None:
        def _f(v):
            try:
                return float(v)
            except (TypeError, ValueError):
                return float("nan")

        rc = (ramp_code or "c_h").strip().lower()
        if rc in ("hc", "h-c", "h_c", "hot_cold"):
            use_hc = True
        else:
            use_hc = False

        if use_hc:
            self._tx_hc.append(_f(t_c))
            self._fwhm_hc.append(_f(fwhm))
            self._smsr_hc.append(_f(smsr))
            self._peak_nm_hc.append(_f(peak_nm))
            self._pk_dbm_hc.append(_f(peak_dbm))
            self._thor_hc.append(_f(thorlabs_mw))
        else:
            self._tx_ch.append(_f(t_c))
            self._fwhm_ch.append(_f(fwhm))
            self._smsr_ch.append(_f(smsr))
            self._peak_nm_ch.append(_f(peak_nm))
            self._pk_dbm_ch.append(_f(peak_dbm))
            self._thor_ch.append(_f(thorlabs_mw))

        if _PG_AVAILABLE and self._curve_peak_nm is not None:
            # Throttle plot redraw + autorange to keep UI responsive (especially with small temperature steps).
            # We still keep *all* points in memory; we just redraw at most ~6–8 fps.
            now = time.time()
            last = float(getattr(self, "_last_plot_redraw_ts", 0.0) or 0.0)
            if (now - last) < 0.14:
                return
            self._last_plot_redraw_ts = now
            dx_ch, dpy_ch, dfy_ch, dsy_ch, dlv_ch, dtl_ch = stability_arrays_with_duplicate_x_breaks(
                self._tx_ch, self._peak_nm_ch, self._fwhm_ch, self._smsr_ch, self._pk_dbm_ch, self._thor_ch
            )
            dx_hc, dpy_hc, dfy_hc, dsy_hc, dlv_hc, dtl_hc = stability_arrays_with_duplicate_x_breaks(
                self._tx_hc, self._peak_nm_hc, self._fwhm_hc, self._smsr_hc, self._pk_dbm_hc, self._thor_hc
            )
            self._curve_peak_nm.setData(dx_ch, dpy_ch)
            if self._curve_peak_nm_hc is not None:
                self._curve_peak_nm_hc.setData(dx_hc, dpy_hc)
            if self._curve_smsr is not None:
                self._curve_smsr.setData(dx_ch, dsy_ch)
            if self._curve_smsr_hc is not None:
                self._curve_smsr_hc.setData(dx_hc, dsy_hc)
            if self._curve_pk_lv is not None:
                self._curve_pk_lv.setData(dx_ch, dlv_ch)
            if self._curve_pk_lv_hc is not None:
                self._curve_pk_lv_hc.setData(dx_hc, dlv_hc)
            if self._curve_fwhm is not None:
                self._curve_fwhm.setData(dx_ch, dfy_ch)
            if self._curve_fwhm_hc is not None:
                self._curve_fwhm_hc.setData(dx_hc, dfy_hc)
            if self._curve_thorlabs is not None:
                self._curve_thorlabs.setData(dx_ch, dtl_ch)
            if self._curve_thorlabs_hc is not None:
                self._curve_thorlabs_hc.setData(dx_hc, dtl_hc)
            if callable(getattr(self, "_sync_stability_vbs", None)):
                try:
                    self._sync_stability_vbs()
                except Exception:
                    pass
            # Autorange is expensive; do it less often than redraw.
            try:
                ar_last = float(getattr(self, "_last_plot_autorange_ts", 0.0) or 0.0)
            except Exception:
                ar_last = 0.0
            if (now - ar_last) >= 0.7:
                try:
                    self._last_plot_autorange_ts = now
                except Exception:
                    pass
                self._autorange_stability_axes()
            pw = getattr(self, "_plot_widget", None)
            if pw is not None:
                try:
                    pw.update()
                except Exception:
                    pass

    def append_process_log(self, msg: str) -> None:
        self._log.appendPlainText(msg)
        sb = self._log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def clear_process_log(self) -> None:
        self._log.clear()

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        try:
            set_dark_title_bar(int(self.winId()), True)
        except Exception:
            pass
