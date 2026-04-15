"""
Shared LIV sweep plot: same PyQtGraph layout as LIV Process (triple axis, series toggles with color swatches)
and the same Phase-4 analysis overlays (Ith, P@Ir / I@Pr construction, SE fit).
"""
import sys
from pathlib import Path

# Project root on sys.path so `python view/liv_process_plot.py` resolves `view.*` imports.
_root = Path(__file__).resolve().parent.parent
_rp = str(_root)
if _rp not in sys.path:
    sys.path.insert(0, _rp)

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, cast

from PyQt5.QtCore import Qt, QRectF

# PyQt5 / pyqtgraph stubs are incomplete; use dynamic Qt namespace like main_window.QtCompat.
QtCompat: Any = cast(Any, Qt)

try:
    import pyqtgraph as pg

    _PG_AVAILABLE = True
except ImportError:
    _PG_AVAILABLE = False
    pg = None

from view.liv_se_ith_overlays import apply_liv_rated_construction_overlays, apply_liv_se_ith_overlays
from view.pg_axis_style import apply_standard_pg_axis_fonts
from view.plot_series_checkboxes import (
    LIV_SERIES_COLORS,
    LIV_SERIES_LABELS,
    freeze_plot_navigation,
    make_series_checkbox_row,
)

# Match temperature-stability multi-Y: tight grid columns + tick alignment at origin.
LIV_PLOT_COL_LEFT = 70
LIV_PLOT_COL_RIGHT_VOLT = 54
LIV_PLOT_COL_RIGHT_PD = 72


def _axis_set_width(ax: Any, width_px: int) -> None:
    fn = getattr(ax, "setWidth", None)
    if not callable(fn):
        return
    try:
        fn(int(width_px))
    except Exception:
        pass


def compact_liv_triple_y_axes(p1: Any, ax_pd: Any, plot_widget: Any) -> None:
    """Zero GraphicsLayout spacing, fixed axis column widths, tick alignment (same idea as TS multi-Y)."""
    lay = p1.layout
    try:
        lay.setHorizontalSpacing(0)
    except Exception:
        pass
    try:
        lay.setVerticalSpacing(0)
    except Exception:
        pass
    for col, w in (
        (0, LIV_PLOT_COL_LEFT),
        (2, LIV_PLOT_COL_RIGHT_VOLT),
        (3, LIV_PLOT_COL_RIGHT_PD),
    ):
        try:
            lay.setColumnMinimumWidth(col, w)
        except Exception:
            pass

    def _style_axis_tight(ax: Any) -> None:
        if ax is None:
            return
        try:
            ax.setStyle(autoExpandTextSpace=False, tickTextOffset=2, tickLength=4)
        except Exception:
            try:
                ax.setStyle(tickTextOffset=2, tickLength=4)
            except Exception:
                pass

    for side in ("left", "bottom"):
        _style_axis_tight(p1.getAxis(side))
    ax_v = p1.getAxis("right")
    if ax_v is not None:
        _style_axis_tight(ax_v)
        _axis_set_width(ax_v, LIV_PLOT_COL_RIGHT_VOLT)
    if ax_pd is not None:
        _style_axis_tight(ax_pd)
        _axis_set_width(ax_pd, LIV_PLOT_COL_RIGHT_PD)

    for ax in (p1.getAxis("left"), p1.getAxis("bottom"), p1.getAxis("right"), ax_pd):
        if ax is None:
            continue
        _fn = getattr(ax, "enableAutoSIPrefix", None)
        if callable(_fn):
            try:
                _fn(False)
            except Exception:
                pass

    apply_standard_pg_axis_fonts(p1, plot_widget=plot_widget, extra_axis_items=(ax_pd,))
    try:
        p1.setContentsMargins(2, 2, 2, 2)
    except Exception:
        pass


@dataclass
class LivProcessPlotBundle:
    plot_widget: Any
    power_curve: Any
    voltage_curve: Any
    pd_curve: Any
    p1: Any
    vb_voltage: Any
    vb_pd: Any
    series_checkbox_row: Any


def build_liv_process_plot() -> Optional[LivProcessPlotBundle]:
    """
    Same graph as LIV Process window (white plot area, Power / Voltage / PD (μA) vs Current mA).
    Series legend is not drawn inside the plot — colors appear beside the checkboxes above.
    """
    if not _PG_AVAILABLE or pg is None:
        return None
    _pg = cast(Any, pg)
    pw = _pg.PlotWidget()
    pw.setBackground("w")
    p1 = cast(Any, pw.getPlotItem())
    p1.getViewBox().setBackgroundColor((255, 255, 255))
    p1.showGrid(x=True, y=True, alpha=0.5)
    axis_pen = _pg.mkPen(color="#333333", width=1)
    p1.setLabel("bottom", "Current mA", color="#333333")
    p1.setLabel("left", "Power (mW)", color="#333333")
    p1.layout.setColumnMinimumWidth(0, LIV_PLOT_COL_LEFT)
    p1.getAxis("left").setPen(axis_pen)
    p1.getAxis("left").setTextPen(axis_pen)
    p1.getAxis("bottom").setPen(axis_pen)
    p1.getAxis("bottom").setTextPen(axis_pen)
    _c_power, _c_volt, _c_pd = LIV_SERIES_COLORS
    power_curve = pw.plot(
        [],
        [],
        pen=_pg.mkPen(_c_power, width=2),
        name="Power",
        symbol="d",
        symbolSize=5,
        symbolBrush=_c_power,
        symbolPen=_pg.mkPen(_c_power),
    )
    p1.vb.setZValue(-100)
    p2 = _pg.ViewBox()
    p1.showAxis("right")
    p1.scene().addItem(p2)
    p1.getAxis("right").linkToView(p2)
    p2.setXLink(p1.vb)
    p2.setZValue(10)
    p1.getAxis("right").setLabel("Voltage(v)", color="#333333")
    p1.getAxis("right").setPen(axis_pen)
    p1.getAxis("right").setTextPen(axis_pen)
    voltage_curve = _pg.PlotDataItem(
        [],
        [],
        pen=_pg.mkPen(_c_volt, width=2),
        name="Voltage",
        symbol="s",
        symbolSize=4,
        symbolBrush=_c_volt,
        symbolPen=_pg.mkPen(_c_volt),
    )
    p2.addItem(voltage_curve)
    p3 = _pg.ViewBox()
    ax3 = _pg.AxisItem("right")
    p1.layout.addItem(ax3, 2, 3)
    p1.layout.setColumnMinimumWidth(3, LIV_PLOT_COL_RIGHT_PD)
    p1.scene().addItem(p3)
    ax3.linkToView(p3)
    p3.setXLink(p1.vb)
    p3.setZValue(10)
    ax3.setLabel("PD current (μA)", color="#333333")
    ax3.setPen(axis_pen)
    ax3.setTextPen(axis_pen)
    pd_curve = _pg.PlotDataItem(
        [],
        [],
        pen=_pg.mkPen(_c_pd, width=2),
        name="PD (μA)",
        symbol="t",
        symbolSize=4,
        symbolBrush=_c_pd,
        symbolPen=_pg.mkPen(_c_pd),
    )
    p3.addItem(pd_curve)

    def _sync():
        r = p1.vb.sceneBoundingRect()
        try:
            rr = QRectF(
                round(float(r.x())),
                round(float(r.y())),
                max(1.0, round(float(r.width()))),
                max(1.0, round(float(r.height()))),
            )
        except Exception:
            rr = r
        p2.setGeometry(rr)
        p3.setGeometry(rr)
        p2.linkedViewChanged(p1.vb, p2.XAxis)
        p3.linkedViewChanged(p1.vb, p3.XAxis)

    _sync()
    p1.vb.sigResized.connect(_sync)
    freeze_plot_navigation(p1, p2, p3)
    series_spec = [
        {"curve": power_curve, "axis": p1.getAxis("left")},
        {"curve": voltage_curve, "axis": p1.getAxis("right")},
        {"curve": pd_curve, "axis": ax3},
    ]
    liv_cb_row, _ = make_series_checkbox_row(
        series_spec,
        LIV_SERIES_LABELS,
        legend=None,
        color_swatches=LIV_SERIES_COLORS,
    )
    compact_liv_triple_y_axes(p1, ax3, pw)
    try:
        p1.setTitle("LIV — Power / Voltage / PD (μA) vs Current", color="#333333")
    except Exception:
        pass
    return LivProcessPlotBundle(
        plot_widget=pw,
        power_curve=power_curve,
        voltage_curve=voltage_curve,
        pd_curve=pd_curve,
        p1=p1,
        vb_voltage=p2,
        vb_pd=p3,
        series_checkbox_row=liv_cb_row,
    )


def liv_autorange_secondary_axes(
    vb_voltage: Any,
    vb_pd: Any,
    currents: List[float],
    voltages: List[float],
    pds: List[float],
) -> None:
    """Match LivTestSequenceWindow._liv_autorange_secondary_y_axes (linked V / PD ViewBoxes)."""
    if not _PG_AVAILABLE:
        return
    n = len(currents)
    if n < 1:
        return
    for vb, series in ((vb_voltage, voltages), (vb_pd, pds)):
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


def clear_liv_analysis_overlays(p1: Any, overlay_items: List[Any]) -> None:
    for item in overlay_items:
        try:
            p1.removeItem(item)
        except Exception:
            pass
    overlay_items.clear()


def recipe_params_for_liv_overlays(recipe: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Rated I/P for overlay construction — same keys as LIV Process set_params."""
    if not recipe or not isinstance(recipe, dict):
        return {}
    ops = recipe.get("OPERATIONS") or {}
    liv = ops.get("LIV")
    if isinstance(liv, dict):
        return dict(liv)
    liv = recipe.get("LIV")
    if isinstance(liv, dict):
        return dict(liv)
    return {}


def apply_liv_phase4_overlays(
    p1: Any,
    pg_mod: Any,
    result: Any,
    recipe_params: Dict[str, Any],
    overlay_items: List[Any],
    *,
    dark_theme: bool = True,
) -> None:
    """
    Same overlays as LivTestSequenceWindow.set_liv_results (after sweep data is on the curves).
    Use dark_theme=False for white PlotWidget backgrounds (readable caption text).
    """
    if not _PG_AVAILABLE or p1 is None or result is None or pg_mod is None:
        return

    def ga(name, default=None):
        return getattr(result, name, default)

    rp = recipe_params or {}
    try:
        ir_m = float(rp.get("rated_current_mA", rp.get("rated_current", 0)) or 0)
    except (TypeError, ValueError):
        ir_m = 0.0
    try:
        pr_mw = float(rp.get("rated_power_mW", rp.get("rated_power", 0)) or 0)
    except (TypeError, ValueError):
        pr_mw = 0.0

    ith = float(ga("threshold_current", 0) or 0)
    p_ir = float(ga("power_at_rated_current", 0) or 0)
    i_pr = float(ga("current_at_rated_power", 0) or 0)
    se = float(ga("slope_efficiency", 0) or 0)

    cur = list(ga("current_array", []) or [])
    pwr = list(ga("power_array", []) or [])
    if not pwr:
        pwr = list(ga("gentec_power_array", []) or [])
    if len(cur) != len(pwr) or len(cur) < 2:
        return

    dash = QtCompat.DashLine
    if ith > 0 and cur and ith <= max(cur) * 1.05:
        ln = pg_mod.InfiniteLine(pos=ith, angle=90, pen=pg_mod.mkPen("#2e7d32", width=2, style=dash))
        ln.setZValue(5)
        p1.addItem(ln)
        overlay_items.append(ln)
    apply_liv_rated_construction_overlays(
        p1,
        pg_mod,
        cur,
        pwr,
        ir_m,
        pr_mw,
        p_ir,
        i_pr,
        overlay_items,
        dark_theme=dark_theme,
    )
    if ir_m > 0 and p_ir > 1e-15:
        sc = pg_mod.ScatterPlotItem(
            [ir_m],
            [p_ir],
            size=14,
            pen=pg_mod.mkPen("#c2185b", width=2),
            brush=pg_mod.mkBrush(200, 25, 90, 200),
            symbol="star",
        )
        sc.setZValue(8)
        p1.addItem(sc)
        overlay_items.append(sc)
    if pr_mw > 0 and i_pr > 1e-6:
        sc2 = pg_mod.ScatterPlotItem(
            [i_pr],
            [pr_mw],
            size=12,
            pen=pg_mod.mkPen("#00838f", width=2),
            brush=pg_mod.mkBrush(0, 130, 150, 200),
            symbol="d",
        )
        sc2.setZValue(8)
        p1.addItem(sc2)
        overlay_items.append(sc2)
    sfc = list(ga("slope_fit_currents", []) or [])
    sfp = list(ga("slope_fit_powers", []) or [])
    apply_liv_se_ith_overlays(
        p1,
        pg_mod,
        cur,
        pwr,
        ith,
        se,
        sfc,
        sfp,
        overlay_items,
        dark_theme=dark_theme,
    )
