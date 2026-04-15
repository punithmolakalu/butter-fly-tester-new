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
from view.liv_process_plot import apply_liv_phase4_overlays, build_liv_process_plot


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
            ("fiber_coupled", "Fiber coupled"),
            ("min_current_mA", "Min Current (mA)"),
            ("max_current_mA", "Max Current (mA)"),
            ("increment_mA", "Increment (mA)"),
            ("num_increments", "Num Increments"),
            ("wait_time_ms", "Wait Time (ms)"),
            ("temperature", "Temperature (°C)"),
            ("rated_current_mA", "Rated Current (mA)"),
            ("rated_power_mW", "Rated Power (mW)"),
            ("se_data_points", "SE fit points (se_data_points)"),
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

        log_group = QGroupBox("Process log")
        log_group.setStyleSheet(
            "QGroupBox { font-weight: bold; font-size: 12px; color: #e6e6e6; } "
            "QPlainTextEdit { background-color: #1e1e1e; color: #c8c8c8; font-size: 11px; }"
        )
        log_layout = QVBoxLayout(log_group)
        self._process_log = QPlainTextEdit()
        self._process_log.setReadOnly(True)
        self._process_log.setMinimumHeight(120)
        self._process_log.setPlaceholderText("LIV step messages appear here…")
        log_layout.addWidget(self._process_log)
        left_layout.addWidget(log_group)

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
        self._graph_title = QLabel("LIV — Power / Voltage / PD (μA) vs Current")
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
            built = build_liv_process_plot()
            if built is None:
                right_layout.addWidget(QLabel("pyqtgraph required for graphs."))
                self._liv_power_curve = self._liv_voltage_curve = self._liv_pd_curve = None
                self._liv_vb_voltage = self._liv_vb_pd = None
                self._plot_widget = None
            else:
                self._plot_widget = built.plot_widget
                self._p1 = built.p1
                self._liv_power_curve = built.power_curve
                self._liv_voltage_curve = built.voltage_curve
                self._liv_pd_curve = built.pd_curve
                self._liv_vb_voltage = built.vb_voltage
                self._liv_vb_pd = built.vb_pd
                right_layout.addWidget(built.series_checkbox_row)
                right_layout.addWidget(built.plot_widget, 1)

        hint = QLabel(
            "Graph: green vertical = Ith | orange = Ir construction (up to L–I, then horizontal = P@Ir) | "
            "blue = Pr construction (along to L–I, then down = I@Pr) | ★ = P@Ir | ◆ = I@Pr | "
            "purple dashed = P=SE·(I−Ith), "
            "gold bar = SE fit window, green ◆ = (Ith,0), text = Ith & SE values."
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

    def set_params(self, params: dict):
        """Set left-side recipe labels from full LIV recipe params (OPERATIONS.LIV + computed num_increments)."""
        self._recipe_params = dict(params) if params else {}
        if not params:
            return
        key_map = [
            ("fiber_coupled", ("fiber_coupled", "FiberCoupled")),
            ("min_current_mA", ("min_current_mA", "min_current")),
            ("max_current_mA", ("max_current_mA", "max_current")),
            ("increment_mA", ("increment_mA", "increment")),
            ("num_increments", ("num_increments",)),
            ("wait_time_ms", ("wait_time_ms", "wait_time")),
            ("temperature", ("temperature", "Temperature")),
            ("rated_current_mA", ("rated_current_mA", "rated_current")),
            ("rated_power_mW", ("rated_power_mW", "rated_power")),
            ("se_data_points", ("se_data_points",)),
        ]
        for label_key, param_keys in key_map:
            val = None
            for k in param_keys:
                if k in params:
                    val = params[k]
                    break
            if label_key not in self._value_labels:
                continue
            if label_key == "fiber_coupled":
                if isinstance(val, bool):
                    txt = "Yes" if val else "No"
                elif val is None:
                    txt = "—"
                else:
                    s = str(val).strip().lower()
                    txt = "Yes" if s in ("1", "true", "yes", "on") else "No" if s in ("0", "false", "no", "off") else _fmt(val)
                self._value_labels[label_key].setText(txt)
            else:
                self._value_labels[label_key].setText(_fmt(val))

    def _liv_autorange_secondary_y_axes(self) -> None:
        """Keep voltage / PD ViewBox Y range in sync with data (X stays linked to main plot)."""
        if not _PG_AVAILABLE:
            return
        n = len(self._currents)
        if n < 1:
            return
        for curve, vb, series in (
            (getattr(self, "_liv_voltage_curve", None), getattr(self, "_liv_vb_voltage", None), self._voltages),
            (getattr(self, "_liv_pd_curve", None), getattr(self, "_liv_vb_pd", None), self._pds),
        ):
            if curve is not None and hasattr(curve, "isVisible") and not curve.isVisible():
                continue
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
        if not pwr:
            pwr = list(ga("gentec_power_array", []) or [])
        if _PG_AVAILABLE and self._p1 is not None and len(cur) == len(pwr) and len(cur) > 1:
            self._clear_result_overlays()
            apply_liv_phase4_overlays(self._p1, pg, r, rp, self._overlay_items)

        self._graph_title.setText(
            "LIV — sweep complete | orange = P@Ir construction | blue = I@Pr construction | "
            "purple = P=SE·(I−Ith) | gold = linear fit | green ◆ = Ith"
        )

    def on_plot_update(self, current: float, power: float, voltage: float, pd: float = 0.0, tec_temp: float = 0.0):
        """
        One point per sweep step: Gentec power + Arroyo LAS:LDV (V) + LAS:MDI (raw), vs readback current.
        Fifth arg is TEC temperature (°C) from LIV; unused for plotting (Main GUI uses it for live sync).
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
