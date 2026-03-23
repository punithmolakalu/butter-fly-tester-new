"""
LIV Test Sequence Window: LIV runs in test sequence.
Left: recipe params + LIV results (calibration, P@Ir, I@Pr, Ith, SE, pass/fail).
Right: live graph + markers (threshold, rated I/P, slope-fit segment).
"""
from PyQt5.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QGroupBox,
    QLabel,
    QScrollArea,
    QFrame,
    QPushButton,
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
    if isinstance(v, float):
        return f"{v:.4g}"
    return str(v)


def _fmt4(v, default="—"):
    if v is None:
        return default
    try:
        return f"{float(v):.4f}"
    except (TypeError, ValueError):
        return str(v)


class LivTestSequenceWindow(QMainWindow):
    """LIV Process: recipe + Phase-4 results on left; power/voltage/PD + analysis overlays on right."""
    stop_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("LIV Process")
        self.setMinimumSize(980, 560)
        self.resize(1180, 640)
        self.setPalette(get_dark_palette())
        self.setStyleSheet(main_stylesheet())
        self.setAttribute(Qt.WA_DeleteOnClose, True)

        self._recipe_params = {}
        self._p1 = None
        self._overlay_items = []

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(16)

        # —— Left: recipe + results ——
        left_widget = QWidget()
        left_widget.setMinimumWidth(300)
        left_widget.setMaximumWidth(420)
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        params_group = QGroupBox("LIV Recipe Parameters")
        params_group.setStyleSheet(
            "QGroupBox { font-weight: bold; font-size: 13px; color: #e6e6e6; } "
            "QLabel { color: #b0b0b0; font-size: 12px; }"
        )
        self._form = QFormLayout(params_group)
        self._form.setSpacing(6)
        self._form.setContentsMargins(12, 16, 12, 12)
        self._value_labels = {}
        for key, label in [
            ("min_current_mA", "Min Current (mA)"),
            ("max_current_mA", "Max Current (mA)"),
            ("increment_mA", "Increment (mA)"),
            ("temperature", "Temperature (°C)"),
            ("rated_current_mA", "Rated Current (mA)"),
            ("rated_power_mW", "Rated Power (mW)"),
            ("wait_time_ms", "Wait Time (ms)"),
            ("num_increments", "Num Increments"),
        ]:
            lbl = QLabel("—")
            lbl.setMinimumWidth(80)
            self._value_labels[key] = lbl
            self._form.addRow(label + ":", lbl)
        left_layout.addWidget(params_group)

        res_group = QGroupBox("LIV")
        res_group.setStyleSheet(
            "QGroupBox { font-weight: bold; font-size: 14px; color: #7cb7ff; } "
            "QLabel { color: #c8c8c8; font-size: 11px; } "
            "QLabel#livResTitle { color: #e6e6e6; font-size: 12px; font-weight: bold; }"
        )
        res_layout = QVBoxLayout(res_group)
        res_layout.setSpacing(4)
        tit = QLabel("Results (Phase 4 — calibration & pass/fail)")
        tit.setObjectName("livResTitle")
        res_layout.addWidget(tit)
        self._result_form = QFormLayout()
        self._result_form.setSpacing(4)
        self._result_form.setContentsMargins(0, 8, 0, 0)
        self._result_labels = {}
        for key, label in [
            ("final_power_mW", "Final power @ max I (mW)"),
            ("thorlabs_avg_mW", "Thorlabs average (mW)"),
            ("calib_factor", "Calib factor (final ÷ Thorlabs avg)"),
            ("power_at_Ir", "Power @ rated current (mW)"),
            ("current_at_Pr", "Current @ rated power (mA)"),
            ("threshold_mA", "Threshold current Ith (mA)"),
            ("slope_mW_mA", "Slope efficiency SE (mW/mA)"),
            ("pass_fail", "Pass / Fail"),
        ]:
            lbl = QLabel("—")
            lbl.setWordWrap(True)
            lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self._result_labels[key] = lbl
            self._result_form.addRow(label + ":", lbl)
        res_layout.addLayout(self._result_form)
        self._fail_detail = QLabel("")
        self._fail_detail.setWordWrap(True)
        self._fail_detail.setStyleSheet("color: #ff8a80; font-size: 11px;")
        self._fail_detail.hide()
        res_layout.addWidget(self._fail_detail)
        # Per request: do not show LIV result/calculation block in LIV popup window.
        res_group.setVisible(False)
        left_layout.addWidget(res_group)
        # Live power readings below results section.
        live_group = QGroupBox("Live Power Readings")
        live_group.setStyleSheet(
            "QGroupBox { font-weight: bold; font-size: 12px; color: #e6e6e6; } "
            "QLabel { color: #c8c8c8; font-size: 11px; }"
        )
        live_form = QFormLayout(live_group)
        self._live_gentec_label = QLabel("—")
        self._live_thorlabs_label = QLabel("—")
        live_form.addRow("Gentec (mW):", self._live_gentec_label)
        live_form.addRow("Thorlabs (mW):", self._live_thorlabs_label)
        left_layout.addWidget(live_group)
        left_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidget(left_widget)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")
        main_layout.addWidget(scroll)

        # —— Right: graph ——
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self._graph_title = QLabel("LIV — Power / Voltage / PD vs Current")
        self._graph_title.setStyleSheet("font-weight: bold; font-size: 13px; color: #e6e6e6;")
        right_layout.addWidget(self._graph_title)
        stop_row = QHBoxLayout()
        stop_row.addStretch()
        self._stop_btn = QPushButton("Stop")
        self._stop_btn.setMinimumWidth(120)
        self._stop_btn.clicked.connect(self.stop_requested.emit)
        stop_row.addWidget(self._stop_btn)
        right_layout.addLayout(stop_row)
        if not _PG_AVAILABLE:
            right_layout.addWidget(QLabel("pyqtgraph required for graphs."))
            self._liv_power_curve = self._liv_voltage_curve = self._liv_pd_curve = None
            self._liv_vb_voltage = self._liv_vb_pd = None
            self._plot_widget = None
        else:
            pw = pg.PlotWidget()
            self._plot_widget = pw
            pw.setBackground("w")
            p1 = pw.getPlotItem()
            self._p1 = p1
            p1.getViewBox().setBackgroundColor((255, 255, 255))
            p1.showGrid(x=True, y=True, alpha=0.5)
            axis_pen = pg.mkPen(color="#333333", width=1)
            p1.setLabel("bottom", "Current mA", color="#333333")
            p1.setLabel("left", "Power (mW)", color="#333333")
            p1.layout.setColumnMinimumWidth(0, 70)
            p1.getAxis("left").setPen(axis_pen)
            p1.getAxis("left").setTextPen(axis_pen)
            p1.getAxis("bottom").setPen(axis_pen)
            p1.getAxis("bottom").setTextPen(axis_pen)
            legend = p1.addLegend(offset=(10, 10), labelTextColor="#333333")
            legend.setParentItem(p1.vb)
            legend.anchor((1, 1), (1, 1))
            self._liv_power_curve = pw.plot(
                [], [], pen=pg.mkPen("#FF0000", width=2), name="Power",
                symbol="d", symbolSize=5, symbolBrush="#FF0000", symbolPen=pg.mkPen("#FF0000")
            )
            # Secondary ViewBoxes must stack ABOVE the main ViewBox: its white background
            # otherwise paints over p2/p3 and hides voltage + PD curves (only power remains visible).
            p1.vb.setZValue(-100)
            p2 = pg.ViewBox()
            p1.showAxis("right")
            p1.scene().addItem(p2)
            p1.getAxis("right").linkToView(p2)
            p2.setXLink(p1.vb)
            p2.setZValue(10)
            self._liv_vb_voltage = p2
            p1.getAxis("right").setLabel("Voltage(v)", color="#333333")
            p1.getAxis("right").setPen(axis_pen)
            p1.getAxis("right").setTextPen(axis_pen)
            self._liv_voltage_curve = pg.PlotDataItem(
                [], [], pen=pg.mkPen("#0066FF", width=2), name="Voltage",
                symbol="s", symbolSize=4, symbolBrush="#0066FF", symbolPen=pg.mkPen("#0066FF")
            )
            p2.addItem(self._liv_voltage_curve)
            legend.addItem(self._liv_voltage_curve, "Voltage")
            p3 = pg.ViewBox()
            ax3 = pg.AxisItem("right")
            p1.layout.addItem(ax3, 2, 3)
            p1.layout.setColumnMinimumWidth(3, 72)
            p1.scene().addItem(p3)
            ax3.linkToView(p3)
            p3.setXLink(p1.vb)
            p3.setZValue(10)
            self._liv_vb_pd = p3
            ax3.setLabel("PD current (MDI)", color="#333333")
            ax3.setPen(axis_pen)
            ax3.setTextPen(axis_pen)
            self._liv_pd_curve = pg.PlotDataItem(
                [], [], pen=pg.mkPen("#000000", width=2), name="PD (MDI)",
                symbol="t", symbolSize=4, symbolBrush="#000000", symbolPen=pg.mkPen("#000000")
            )
            p3.addItem(self._liv_pd_curve)
            legend.addItem(self._liv_pd_curve, "PD (MDI)")

            def _sync():
                r = p1.vb.sceneBoundingRect()
                p2.setGeometry(r)
                p3.setGeometry(r)
                p2.linkedViewChanged(p1.vb, p2.XAxis)
                p3.linkedViewChanged(p1.vb, p3.XAxis)

            _sync()
            p1.vb.sigResized.connect(_sync)
            right_layout.addWidget(pw, 1)

        hint = QLabel(
            "Graph: green = Ith | orange = Irated | blue = Prated | "
            "magenta ★ = P@Ir | cyan ◆ = I@Pr | purple = slope-fit window"
        )
        hint.setStyleSheet("color: #888; font-size: 10px;")
        hint.setWordWrap(True)
        right_layout.addWidget(hint)

        # Calculation summary below graph (default placeholders, updated when results arrive).
        calc_group = QGroupBox("Calculation")
        calc_group.setStyleSheet(
            "QGroupBox { font-weight: bold; font-size: 12px; color: #e6e6e6; } "
            "QLabel { color: #c8c8c8; font-size: 11px; }"
        )
        self._calc_form = QFormLayout(calc_group)
        self._calc_form.setSpacing(4)
        self._calc_labels = {}
        for key, title in [
            ("power_at_ir", "Power @ Rated Current (mW)"),
            ("current_at_pr", "Current @ Rated Power (mA)"),
            ("threshold", "Threshold Current Ith (mA)"),
            ("slope", "Slope Efficiency (mW/mA)"),
        ]:
            lbl = QLabel("—")
            lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self._calc_labels[key] = lbl
            self._calc_form.addRow(title + ":", lbl)
        # Per request: do not show calculation block inside LIV popup window.
        calc_group.setVisible(False)
        right_layout.addWidget(calc_group)

        main_layout.addWidget(right_widget, 1)

        self._currents = []
        self._powers = []
        self._voltages = []
        self._pds = []

    def showEvent(self, event: QShowEvent):
        super().showEvent(event)
        try:
            set_dark_title_bar(int(self.winId()), True)
        except Exception:
            pass

    def set_params(self, params: dict):
        """Set left-side recipe labels from LIV recipe params."""
        self._recipe_params = dict(params) if params else {}
        if not params:
            return
        key_map = [
            ("min_current_mA", ("min_current_mA", "min_current")),
            ("max_current_mA", ("max_current_mA", "max_current")),
            ("increment_mA", ("increment_mA", "increment")),
            ("temperature", ("temperature", "Temperature")),
            ("rated_current_mA", ("rated_current_mA", "rated_current")),
            ("rated_power_mW", ("rated_power_mW", "rated_power")),
            ("wait_time_ms", ("wait_time_ms", "wait_time")),
            ("num_increments", ("num_increments",)),
        ]
        for label_key, param_keys in key_map:
            val = None
            for k in param_keys:
                if k in params:
                    val = params[k]
                    break
            if label_key in self._value_labels:
                self._value_labels[label_key].setText(_fmt(val))

    def _liv_autorange_secondary_y_axes(self) -> None:
        """Keep voltage / PD ViewBox Y range in sync with data (X stays linked to main plot)."""
        if not _PG_AVAILABLE:
            return
        n = len(self._currents)
        if n < 1:
            return
        for vb, series in (
            (getattr(self, "_liv_vb_voltage", None), self._voltages),
            (getattr(self, "_liv_vb_pd", None), self._pds),
        ):
            if vb is None or len(series) < n:
                continue
            try:
                y_vals = [float(y) for y in series[:n]]
                if not y_vals:
                    continue
                lo, hi = min(y_vals), max(y_vals)
                span = hi - lo
                pad = max(span * 0.12, 1e-9)
                if span < 1e-12:
                    pad = max(abs(lo) * 0.05, 0.01)
                vb.setYRange(lo - pad, hi + pad, padding=0)
            except Exception:
                pass

    def _clear_result_overlays(self):
        if self._p1 is None:
            return
        for item in self._overlay_items:
            try:
                self._p1.removeItem(item)
            except Exception:
                pass
        self._overlay_items.clear()

    def clear_plot(self):
        """Clear live graph and analysis overlays (when LIV sweep restarts)."""
        self._clear_result_overlays()
        self._currents = []
        self._powers = []
        self._voltages = []
        self._pds = []
        if self._liv_power_curve is not None:
            self._liv_power_curve.setData([], [])
        if self._liv_voltage_curve is not None:
            self._liv_voltage_curve.setData([], [])
        if self._liv_pd_curve is not None:
            self._liv_pd_curve.setData([], [])
        self._reset_results_panel()

    def _reset_results_panel(self):
        for lbl in self._result_labels.values():
            lbl.setText("—")
            lbl.setStyleSheet("")
        self._fail_detail.hide()
        for lbl in getattr(self, "_calc_labels", {}).values():
            lbl.setText("—")

    def set_liv_results(self, result):
        """
        Fill LIV results panel and draw Phase-4 overlays on the power vs current plot.
        `result`: LIVProcessResult-like object with arrays and scalar metrics.
        """
        r = result
        if r is None:
            return

        def ga(name, default=None):
            return getattr(r, name, default)

        fp = float(ga("final_power", 0) or 0)
        th = float(ga("thorlabs_average_power_mw", 0) or 0)
        cf = float(ga("thorlabs_calib_factor", 0) or 0)
        p_ir = float(ga("power_at_rated_current", 0) or 0)
        i_pr = float(ga("current_at_rated_power", 0) or 0)
        ith = float(ga("threshold_current", 0) or 0)
        se = float(ga("slope_efficiency", 0) or 0)
        passed = bool(ga("passed", False))
        reasons = ga("fail_reasons", None) or []

        rp = self._recipe_params
        try:
            ir_m = float(rp.get("rated_current_mA", rp.get("rated_current", 0)) or 0)
        except (TypeError, ValueError):
            ir_m = 0.0
        try:
            pr_mw = float(rp.get("rated_power_mW", rp.get("rated_power", 0)) or 0)
        except (TypeError, ValueError):
            pr_mw = 0.0

        self._result_labels["final_power_mW"].setText(_fmt4(fp))
        self._result_labels["thorlabs_avg_mW"].setText(_fmt4(th))
        self._result_labels["calib_factor"].setText(_fmt4(cf))
        if ir_m > 0:
            self._result_labels["power_at_Ir"].setText(f"{_fmt4(p_ir)}  (Ir = {_fmt4(ir_m)} mA)")
        else:
            self._result_labels["power_at_Ir"].setText(_fmt4(p_ir))
        if pr_mw > 0:
            self._result_labels["current_at_Pr"].setText(f"{_fmt4(i_pr)}  (Pr = {_fmt4(pr_mw)} mW)")
        else:
            self._result_labels["current_at_Pr"].setText(_fmt4(i_pr))
        self._result_labels["threshold_mA"].setText(_fmt4(ith))
        self._result_labels["slope_mW_mA"].setText(_fmt4(se))
        # Calculation section below graph
        if hasattr(self, "_calc_labels"):
            self._calc_labels["power_at_ir"].setText(_fmt4(p_ir))
            self._calc_labels["current_at_pr"].setText(_fmt4(i_pr))
            self._calc_labels["threshold"].setText(_fmt4(ith))
            self._calc_labels["slope"].setText(_fmt4(se))

        pf = self._result_labels["pass_fail"]
        if passed:
            pf.setText("PASS")
            pf.setStyleSheet("color: #69f0ae; font-weight: bold; font-size: 13px;")
        else:
            pf.setText("FAIL")
            pf.setStyleSheet("color: #ff8a80; font-weight: bold; font-size: 13px;")
        if reasons:
            self._fail_detail.setText("Details: " + "; ".join(str(x) for x in reasons))
            self._fail_detail.show()
        else:
            self._fail_detail.hide()

        cur = list(ga("current_array", []) or [])
        pwr = list(ga("power_array", []) or [])
        if _PG_AVAILABLE and self._p1 is not None and len(cur) == len(pwr) and len(cur) > 1:
            self._clear_result_overlays()
            dash = Qt.DashLine
            # Ith vertical
            if ith > 0 and cur and ith <= max(cur) * 1.05:
                ln = pg.InfiniteLine(pos=ith, angle=90, pen=pg.mkPen("#2e7d32", width=2, style=dash))
                ln.setZValue(5)
                self._p1.addItem(ln)
                self._overlay_items.append(ln)
            # Irated vertical
            if ir_m > 0 and cur and min(cur) <= ir_m <= max(cur) * 1.02:
                ln2 = pg.InfiniteLine(pos=ir_m, angle=90, pen=pg.mkPen("#e65100", width=2, style=dash))
                ln2.setZValue(5)
                self._p1.addItem(ln2)
                self._overlay_items.append(ln2)
            # Prated horizontal (power axis)
            if pr_mw > 0:
                hl = pg.InfiniteLine(pos=pr_mw, angle=0, pen=pg.mkPen("#1565c0", width=2, style=dash))
                hl.setZValue(5)
                self._p1.addItem(hl)
                self._overlay_items.append(hl)
            # P @ Ir
            if ir_m > 0 and p_ir >= 0:
                sc = pg.ScatterPlotItem(
                    [ir_m], [p_ir], size=14, pen=pg.mkPen("#c2185b", width=2),
                    brush=pg.mkBrush(200, 25, 90, 200), symbol="star",
                )
                sc.setZValue(8)
                self._p1.addItem(sc)
                self._overlay_items.append(sc)
            # I @ Pr
            if pr_mw > 0 and i_pr >= 0:
                sc2 = pg.ScatterPlotItem(
                    [i_pr], [pr_mw], size=12, pen=pg.mkPen("#00838f", width=2),
                    brush=pg.mkBrush(0, 130, 150, 200), symbol="d",
                )
                sc2.setZValue(8)
                self._p1.addItem(sc2)
                self._overlay_items.append(sc2)
            # Slope-fit window (measured points)
            sfc = list(ga("slope_fit_currents", []) or [])
            sfp = list(ga("slope_fit_powers", []) or [])
            if len(sfc) >= 2 and len(sfc) == len(sfp):
                fit_seg = pg.PlotDataItem(
                    sfc, sfp, pen=pg.mkPen("#6a1b9a", width=4), name="SE fit window",
                )
                fit_seg.setZValue(6)
                self._p1.addItem(fit_seg)
                self._overlay_items.append(fit_seg)
            # Extrapolated line y = SE * (x - Ith) for x from Ith to max current
            if se > 1e-9 and ith >= 0 and cur:
                x_max = max(cur)
                xs = []
                ys = []
                for i in range(41):
                    t = i / 40.0
                    x = ith + t * (x_max - ith)
                    y = se * (x - ith)
                    if y >= 0:
                        xs.append(x)
                        ys.append(y)
                if len(xs) > 1:
                    ext = pg.PlotDataItem(
                        xs, ys, pen=pg.mkPen("#6a1b9a", width=1, style=dash),
                    )
                    ext.setZValue(4)
                    self._p1.addItem(ext)
                    self._overlay_items.append(ext)

        self._graph_title.setText("LIV — sweep complete | overlays = calibration analysis")

    def on_plot_update(self, current: float, power: float, voltage: float, pd: float = 0.0):
        """
        One point per sweep step: Gentec power + Arroyo LAS:LDV (V) + LAS:MDI (raw), vs readback current.
        Fourth argument must be supplied by liv_plot_update (4-float signal).
        """
        self._currents.append(current)
        self._powers.append(power)
        self._voltages.append(voltage)
        self._pds.append(pd)
        if self._liv_power_curve is not None:
            self._liv_power_curve.setData(self._currents, self._powers)
        if self._liv_voltage_curve is not None:
            self._liv_voltage_curve.setData(self._currents, self._voltages)
        if self._liv_pd_curve is not None:
            self._liv_pd_curve.setData(self._currents, self._pds)
        self._liv_autorange_secondary_y_axes()

    def on_power_reading_update(self, gentec_mw: float, thorlabs_mw: float):
        try:
            if gentec_mw is not None and gentec_mw > 0:
                self._live_gentec_label.setText(f"{float(gentec_mw):.4f}")
            if thorlabs_mw is not None and thorlabs_mw > 0:
                self._live_thorlabs_label.setText(f"{float(thorlabs_mw):.4f}")
        except Exception:
            pass
