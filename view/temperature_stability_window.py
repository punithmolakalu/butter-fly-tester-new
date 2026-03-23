"""
Temperature Stability sequence window (secondary monitor).
Left: RCP details for the active step (Temperature Stability 1/2) + Stop.
Right: live graph — Temp(°C) vs Peak WL, SMSR, Power, Spec width (same layout as Main Temperature Stability tab).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, cast

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


def _fmt(v: Any, default: str = "—") -> str:
    if v is None:
        return default
    try:
        if isinstance(v, float):
            return "{:.6g}".format(v)
        return str(v)
    except Exception:
        return str(v)


def _recipe_block(recipe: Dict[str, Any], step_name: str) -> Dict[str, Any]:
    op = recipe.get("OPERATIONS") or recipe.get("operations") or {}
    if step_name in op and isinstance(op[step_name], dict):
        return op[step_name]
    low = (step_name or "").strip().lower()
    for k, v in op.items():
        if str(k).strip().lower() == low and isinstance(v, dict):
            return v
    return {}


class TemperatureStabilitySequenceWindow(QMainWindow):
    """Floating window: left RCP, right live stability plot (second monitor)."""

    stop_requested = pyqtSignal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._step_name: str = ""
        self._plot_widget: Any = None
        self._curves: Any = None
        self._value_labels: Dict[str, QLabel] = {}

        self.setMinimumSize(1000, 640)
        self.resize(1180, 760)
        self.setPalette(get_dark_palette())
        self.setStyleSheet(main_stylesheet())
        self.setAttribute(Qt.WA_DeleteOnClose, True)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(16)

        # ----- Left: RCP -----
        left_widget = QWidget()
        left_widget.setMinimumWidth(340)
        left_widget.setMaximumWidth(480)
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        self._rcp_group = QGroupBox("Temperature Stability — RCP")
        self._rcp_group.setStyleSheet(
            "QGroupBox { font-weight: bold; font-size: 13px; color: #e6e6e6; } "
            "QLabel { color: #c8c8c8; font-size: 12px; }"
        )
        form = QFormLayout(self._rcp_group)
        for key, title in [
            ("recipe_name", "Recipe name"),
            ("step_name", "Step"),
            ("min_temp", "Min / init temp (°C)"),
            ("max_temp", "Max temp (°C)"),
            ("inc", "Increment (°C)"),
            ("current_ma", "Laser current (mA)"),
            ("stab_s", "Stabilization (s)"),
            ("center_nm", "Ando center (nm)"),
            ("span_nm", "Span (nm)"),
            ("resolution_nm", "Resolution (nm)"),
            ("sampling", "Sampling (pts)"),
            ("sensitivity", "Sensitivity"),
            ("analysis", "Analysis"),
            ("fwhm_lim", "FWHM limit (nm)"),
            ("smsr_lim", "SMSR (dB)"),
            ("wl_lim", "Peak WL (nm)"),
            ("deg_stab", "Deg of stability (°C)"),
        ]:
            lb = QLabel("—")
            self._value_labels[key] = lb
            form.addRow(title + ":", lb)
        left_layout.addWidget(self._rcp_group)

        ctrl = QGroupBox("Control")
        ctrl.setStyleSheet(
            "QGroupBox { font-weight: bold; font-size: 12px; color: #e6e6e6; } "
            "QLabel { color: #c8c8c8; font-size: 11px; }"
        )
        cv = QVBoxLayout(ctrl)
        self._stop_btn = QPushButton("Stop")
        self._stop_btn.setMinimumHeight(34)
        self._stop_btn.setStyleSheet(
            "QPushButton { background-color: #f44336; color: white; font-weight: bold; padding: 8px 16px; } "
            "QPushButton:hover { background-color: #d32f2f; }"
        )
        self._stop_btn.clicked.connect(self.stop_requested.emit)
        cv.addWidget(self._stop_btn)
        self._status = QLabel("Running…")
        self._status.setWordWrap(True)
        self._status.setStyleSheet("color: #b0bec5; font-size: 12px;")
        cv.addWidget(self._status)
        left_layout.addWidget(ctrl)
        left_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidget(left_widget)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        main_layout.addWidget(scroll)

        # ----- Right: graph -----
        right = QWidget()
        rl = QVBoxLayout(right)
        rl.setContentsMargins(0, 0, 0, 0)
        self._plot_title = QLabel("Live plot")
        self._plot_title.setStyleSheet("font-weight: bold; font-size: 13px; color: #e6e6e6;")
        rl.addWidget(self._plot_title)

        if not _PG_AVAILABLE or pg is None:
            rl.addWidget(QLabel("pyqtgraph required for graph display."))
        else:
            pw, curves = self._build_stability_plot_widget("Temperature Stability")
            self._plot_widget = pw
            self._curves = curves
            rl.addWidget(pw, 1)
        main_layout.addWidget(right, 1)

    def _build_stability_plot_widget(self, title_text: str):
        PG: Any = cast(Any, pg)
        axis_pen = PG.mkPen(color="#333333", width=1)
        pw = PG.PlotWidget()
        pw.setBackground("w")
        pi = cast(Any, pw.getPlotItem())
        pi.setTitle(title_text)
        pi.getViewBox().setBackgroundColor((255, 255, 255))
        pi.showGrid(x=True, y=True, alpha=0.5)
        pi.setLabel("bottom", "Temp (°C)", color="#333333")
        pi.setLabel("left", "Wavelength (nm)", color="#333333")
        pi.getAxis("left").setPen(axis_pen)
        pi.getAxis("left").setTextPen(axis_pen)
        pi.getAxis("bottom").setPen(axis_pen)
        pi.getAxis("bottom").setTextPen(axis_pen)
        pi.layout.setColumnMinimumWidth(0, 72)

        curve_wl = pw.plot(
            [],
            [],
            pen=PG.mkPen("#0066CC", width=2),
            symbol="o",
            symbolSize=5,
            symbolBrush="#0066CC",
            name="PeakWL",
        )
        pi.showAxis("right")
        vb_smsr = PG.ViewBox()
        pi.scene().addItem(vb_smsr)
        pi.getAxis("right").linkToView(vb_smsr)
        vb_smsr.setXLink(pi.vb)
        pi.getAxis("right").setLabel("SMSR", color="#333333")
        pi.getAxis("right").setPen(axis_pen)
        pi.getAxis("right").setTextPen(axis_pen)
        pi.layout.setColumnMinimumWidth(2, 48)
        curve_smsr = PG.PlotDataItem(
            [], [], pen=PG.mkPen("#333333", width=2), symbol="o", symbolSize=5, symbolBrush="#333333", name="SMSR"
        )
        vb_smsr.addItem(curve_smsr)

        ax_power = PG.AxisItem("right")
        pi.layout.addItem(ax_power, 2, 3)
        pi.layout.setColumnMinimumWidth(3, 58)
        vb_power = PG.ViewBox()
        pi.scene().addItem(vb_power)
        ax_power.linkToView(vb_power)
        vb_power.setXLink(pi.vb)
        ax_power.setLabel("Power (mW)", color="#333333")
        ax_power.setPen(axis_pen)
        ax_power.setTextPen(axis_pen)
        curve_power = PG.PlotDataItem(
            [], [], pen=PG.mkPen("#008800", width=2), symbol="o", symbolSize=5, symbolBrush="#008800", name="Power"
        )
        vb_power.addItem(curve_power)

        ax_sw = PG.AxisItem("right")
        pi.layout.addItem(ax_sw, 2, 4)
        pi.layout.setColumnMinimumWidth(4, 72)
        vb_sw = PG.ViewBox()
        pi.scene().addItem(vb_sw)
        ax_sw.linkToView(vb_sw)
        vb_sw.setXLink(pi.vb)
        ax_sw.setLabel("SpecWidth (nm)", color="#333333")
        ax_sw.setPen(axis_pen)
        ax_sw.setTextPen(axis_pen)
        curve_sw = PG.PlotDataItem(
            [], [], pen=PG.mkPen("#CC0000", width=2), symbol="o", symbolSize=5, symbolBrush="#CC0000", name="SpecWidth"
        )
        vb_sw.addItem(curve_sw)

        def sync_vbs():
            r = pi.vb.sceneBoundingRect()
            vb_smsr.setGeometry(r)
            vb_power.setGeometry(r)
            vb_sw.setGeometry(r)
            vb_smsr.linkedViewChanged(pi.vb, vb_smsr.XAxis)
            vb_power.linkedViewChanged(pi.vb, vb_power.XAxis)
            vb_sw.linkedViewChanged(pi.vb, vb_sw.XAxis)

        sync_vbs()
        pi.vb.sigResized.connect(sync_vbs)

        legend = pi.addLegend(offset=(10, 10), labelTextColor="#333333")
        legend.setParentItem(pi.vb)
        legend.anchor((1, 1), (1, 1))
        legend.addItem(curve_smsr, "SMSR")
        legend.addItem(curve_power, "Power")
        legend.addItem(curve_sw, "SpecWidth")

        curves = (curve_wl, curve_smsr, curve_power, curve_sw)
        return pw, curves

    def set_params(self, params: Dict[str, Any]) -> None:
        recipe = params.get("recipe") if isinstance(params.get("recipe"), dict) else {}
        step = str(params.get("step_name") or "Temperature Stability")
        self._step_name = step
        self.setWindowTitle(step)
        self._plot_title.setText("Live — {}".format(step))

        blk = _recipe_block(recipe, step)
        g = recipe.get("GENERAL") or recipe.get("general") or {}
        op = recipe.get("OPERATIONS") or recipe.get("operations") or {}
        spec = op.get("SPECTRUM") or op.get("spectrum") or {}

        def gf(keys: List[str], default: float = 0.0) -> float:
            for k in keys:
                if k in blk:
                    try:
                        return float(blk[k])
                    except (TypeError, ValueError):
                        pass
            return default

        def gs(keys: List[str], default: str = "") -> str:
            for k in keys:
                if k in blk and blk[k] is not None:
                    return str(blk[k]).strip()
            return default

        rn = str(recipe.get("Recipe_Name") or recipe.get("recipe_name") or g.get("PartNumber") or "—")
        self._value_labels["recipe_name"].setText(rn)
        self._value_labels["step_name"].setText(step)

        init_t = gf(["InitTemp", "MinTemp", "min_temp"], 25.0)
        if "InitialTemp" in blk:
            try:
                init_t = float(blk["InitialTemp"])
            except (TypeError, ValueError):
                pass
        max_t = gf(["MaxTemp", "MAXTemp"], 35.0)
        inc = gf(["TempIncrement", "INC"], 1.0)
        cur = gf(["Current", "SetCurr"], 0.0)
        if cur <= 0:
            try:
                cur = float(g.get("Current") or spec.get("Current") or 0.0)
            except (TypeError, ValueError):
                cur = 0.0
        stab = gf(["StabilizationTime_s"], 5.0)

        ctr = gf(["CenterWL", "center_nm"], 0.0)
        if ctr <= 0:
            try:
                ctr = float(spec.get("CenterWL") or g.get("Wavelength") or recipe.get("Wavelength") or 1550.0)
            except (TypeError, ValueError):
                ctr = 1550.0
        span = gf(["Span", "span_nm"], 0.0) or float(spec.get("Span") or 10.0)
        res = gf(["Resolution", "resolution_nm"], 0.0) or float(spec.get("Resolution") or 0.1)
        smpl = int(gf(["Sampling", "sampling_points"], 0.0)) or int(spec.get("Sampling") or 501)
        sens = gs(["Sensitivity"], str(spec.get("Sensitivity") or "MID"))
        analysis = gs(["Analysis"], str(spec.get("Analysis") or "DFB-LD"))

        self._value_labels["min_temp"].setText(_fmt(init_t))
        self._value_labels["max_temp"].setText(_fmt(max_t))
        self._value_labels["inc"].setText(_fmt(inc))
        self._value_labels["current_ma"].setText(_fmt(cur) if cur else "—")
        self._value_labels["stab_s"].setText(_fmt(stab))
        self._value_labels["center_nm"].setText(_fmt(ctr))
        self._value_labels["span_nm"].setText(_fmt(span))
        self._value_labels["resolution_nm"].setText(_fmt(res))
        self._value_labels["sampling"].setText(str(smpl))
        self._value_labels["sensitivity"].setText(sens)
        self._value_labels["analysis"].setText(analysis)

        fwhm = gf(["FWHM_Max_nm", "FWHM_UL"], 999.0)
        smsr_lo = gf(["SMSR_Min_dB", "SMSR_LL"], 0.0)
        smsr_hi = gf(["SMSR_Max_dB", "SMSR_UL"], 999.0)
        wl_lo = gf(["PeakWL_Min_nm", "WL_LL"], 0.0)
        wl_hi = gf(["PeakWL_Max_nm", "WL_UL"], 99999.0)
        deg = gf(["DegOfStability", "deg_stability"], 5.0)

        self._value_labels["fwhm_lim"].setText("≤ {}".format(_fmt(fwhm)))
        self._value_labels["smsr_lim"].setText("{} – {}".format(_fmt(smsr_lo), _fmt(smsr_hi)))
        self._value_labels["wl_lim"].setText("{} – {}".format(_fmt(wl_lo), _fmt(wl_hi)))
        self._value_labels["deg_stab"].setText(_fmt(deg))

        try:
            pi = self._plot_widget.getPlotItem() if self._plot_widget is not None else None
            if pi is not None:
                pi.setTitle(step)
        except Exception:
            pass

    def update_live(self, result: Any) -> None:
        """Update right-hand plot from TemperatureStabilityProcessResult (same fields as main window)."""
        if not _PG_AVAILABLE or self._curves is None:
            return
        sw, ss, sp, sx = self._curves
        temps = list(getattr(result, "temperature_data", None) or getattr(result, "temp_data", None) or [])
        wl = list(getattr(result, "peak_wl_data", None) or getattr(result, "wavelength_per_temp", None) or [])
        smsr = list(getattr(result, "smsr_data", None) or [])
        pwr = list(getattr(result, "power_data", None) or [])
        swd = list(getattr(result, "specwidth_data", None) or getattr(result, "fwhm_data", None) or [])
        n = len(temps)
        if n:
            wl_v = (wl + [0] * n)[:n]
            smsr_v = (smsr + [0] * n)[:n]
            pwr_v = (pwr + [0] * n)[:n]
            sw_v = (swd + [0] * n)[:n]
            sw.setData(temps, wl_v)
            ss.setData(temps, smsr_v)
            sp.setData(temps, pwr_v)
            sx.setData(temps, sw_v)

        status = getattr(result, "status", None)
        passed = getattr(result, "passed", None)
        if status == "ABORTED":
            self._status.setText("Stopped.")
        elif passed is True:
            self._status.setText("PASS")
        elif passed is False:
            fr = getattr(result, "fail_reasons", None) or []
            self._status.setText("FAIL — " + ("; ".join(str(x) for x in fr) if fr else "see Main"))

    def set_finished(self, passed: bool, detail: str = "") -> None:
        self._status.setText(("PASS — " if passed else "FAIL — ") + (detail or ""))

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        try:
            set_dark_title_bar(int(self.winId()), True)
        except Exception:
            pass
