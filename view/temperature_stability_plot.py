"""
Plot-tab temperature stability chart: same five-axis layout as TemperatureStabilityWindow (quantities vs °C with units on axes).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Callable, List, Optional, cast

from PyQt5.QtCore import Qt
QtCompat: Any = cast(Any, Qt)

try:
    import pyqtgraph as pg

    _PG_AVAILABLE = True
except ImportError:
    _PG_AVAILABLE = False
    pg = None

from view.pg_axis_style import apply_standard_pg_axis_fonts
from view.plot_series_checkboxes import (
    STABILITY_RAMP_C_H_COLORS,
    STABILITY_RAMP_H_C_COLORS,
    STABILITY_SERIES_LABELS,
    freeze_plot_navigation,
    make_series_checkbox_row,
    pg_curve_axis_list,
    stability_arrays_for_ramp,
)

# Column widths for multi-axis stability plot; wide enough for tick values to be readable.
STABILITY_PLOT_COL_LEFT = 70
STABILITY_PLOT_COL_RIGHT_SMSR = 65
STABILITY_PLOT_COL_RIGHT_EXTRA = 62


def _to_f(v: Any) -> float:
    """Convert any value to float, returning NaN for None / non-numeric."""
    if v is None:
        return float("nan")
    try:
        f = float(v)
        return f
    except (TypeError, ValueError):
        return float("nan")


def _result_val(result: Any, name: str, default: Any = None) -> Any:
    """Scalar / object field from a dataclass/namespace or a plain dict (saved JSON)."""
    if isinstance(result, dict):
        return result.get(name, default)
    return getattr(result, name, default)


def stability_smsr_y_for_plot(result: Any, smsr_db: List[float], lv_dbm: List[float], n: int) -> List[float]:
    """
    SMSR series Y values for the stability chart.
    When recipe SMSR correction is on, plot raw OSA SMSR (dB) minus peak level (dBm) per point.
    """
    if n < 1:
        return []
    if not bool(_result_val(result, "smsr_correction_enabled", False)):
        return [_to_f(smsr_db[i]) for i in range(n)]
    raw = _result_val(result, "smsr_osa_raw_db", None)
    if not isinstance(raw, list) or len(raw) < n:
        return [_to_f(smsr_db[i]) for i in range(n)]
    out: List[float] = []
    for i in range(n):
        r = _to_f(raw[i])
        lval = _to_f(lv_dbm[i])
        if math.isfinite(r) and math.isfinite(lval):
            out.append(r - lval)
        elif math.isfinite(r):
            out.append(r)
        else:
            out.append(float("nan"))
    return out


@dataclass
class StabilityTabPlotBundle:
    plot_widget: Any
    p1: Any
    curve_peak_nm: Any
    curve_peak_nm_hc: Any
    curve_fwhm: Any
    curve_fwhm_hc: Any
    curve_smsr: Any
    curve_smsr_hc: Any
    curve_pk_lv: Any
    curve_pk_lv_hc: Any
    curve_thorlabs: Any
    curve_thorlabs_hc: Any
    vb_smsr: Any
    vb_pk_lv: Any
    vb_fwhm: Any
    vb_thorlabs: Any
    series_checkbox_row: Any
    sync_stability_vbs: Callable[[], None]

    @property
    def curves_for_main_apply(self) -> List[Any]:
        """Order expected by MainWindow legacy apply: peak, fwhm, smsr, pk_lv [, thor] (cold→hot traces only)."""
        return [
            self.curve_peak_nm,
            self.curve_fwhm,
            self.curve_smsr,
            self.curve_pk_lv,
            self.curve_thorlabs,
        ]


def compact_simple_xy_plot_axes(p1: Any, plot_widget: Any) -> None:
    """Tight left + bottom axis layout (Spectrum-style single trace); matches TS plot tab axis chrome."""
    lay = p1.layout
    try:
        lay.setHorizontalSpacing(0)
    except Exception:
        pass
    try:
        lay.setColumnMinimumWidth(0, STABILITY_PLOT_COL_LEFT)
    except Exception:
        pass
    for side in ("left", "bottom"):
        ax = p1.getAxis(side)
        if ax is None:
            continue
        try:
            ax.setStyle(autoExpandTextSpace=True, tickTextOffset=2, tickLength=4)
        except Exception:
            try:
                ax.setStyle(tickTextOffset=2, tickLength=4)
            except Exception:
                pass
        _fn = getattr(ax, "enableAutoSIPrefix", None)
        if callable(_fn):
            try:
                _fn(False)
            except Exception:
                pass
    apply_standard_pg_axis_fonts(p1, plot_widget=plot_widget)
    try:
        p1.setContentsMargins(2, 2, 2, 2)
    except Exception:
        pass


def _stability_axis_set_width(ax: Any, width_px: int) -> None:
    """pyqtgraph AxisItem: set minimum width hint but let autoExpandTextSpace grow beyond it."""
    pass


def compact_stability_multi_y_axes(p1: Any, extra_right_axes: List[Any], plot_widget: Any) -> None:
    """Minimize gaps between right Y axes: tight grid cols, small tick offset, setWidth on AxisItems."""
    lay = p1.layout
    try:
        lay.setHorizontalSpacing(0)
    except Exception:
        pass
    # Column 1 = main ViewBox — do not set min width.
    for col, w in (
        (0, STABILITY_PLOT_COL_LEFT),
        (2, STABILITY_PLOT_COL_RIGHT_SMSR),
        (3, STABILITY_PLOT_COL_RIGHT_EXTRA),
        (4, STABILITY_PLOT_COL_RIGHT_EXTRA),
        (5, STABILITY_PLOT_COL_RIGHT_EXTRA),
    ):
        try:
            lay.setColumnMinimumWidth(col, w)
        except Exception:
            pass
    def _style_axis_tight(ax: Any) -> None:
        try:
            ax.setStyle(autoExpandTextSpace=True, tickTextOffset=3, tickLength=4)
        except Exception:
            try:
                ax.setStyle(tickTextOffset=3, tickLength=4)
            except Exception:
                pass

    for side in ("left", "bottom"):
        ax = p1.getAxis(side)
        if ax is not None:
            _style_axis_tight(ax)

    _r = p1.getAxis("right")
    if _r is not None:
        _style_axis_tight(_r)
        _stability_axis_set_width(_r, STABILITY_PLOT_COL_RIGHT_SMSR)
    for ax in list(extra_right_axes):
        if ax is not None:
            _style_axis_tight(ax)
            _stability_axis_set_width(ax, STABILITY_PLOT_COL_RIGHT_EXTRA)

    apply_standard_pg_axis_fonts(
        p1, plot_widget=plot_widget, extra_axis_items=tuple(extra_right_axes)
    )


def build_stability_tab_plot(plot_title: str) -> Optional[StabilityTabPlotBundle]:
    """White multi-axis stability plot; series names + color swatches on checkbox row above (no in-plot legend)."""
    if not _PG_AVAILABLE or pg is None:
        return None
    _pg = cast(Any, pg)
    pw = _pg.PlotWidget()
    pw.setBackground("w")
    p1 = cast(Any, pw.getPlotItem())
    p1.getViewBox().setBackgroundColor((255, 255, 255))
    p1.showGrid(x=True, y=True, alpha=0.45)
    try:
        p1.setTitle(plot_title, color="#333333")
    except Exception:
        pass
    axis_pen = _pg.mkPen(color="#333333", width=1)
    tc = "#333333"
    _ch = STABILITY_RAMP_C_H_COLORS
    _hc = STABILITY_RAMP_H_C_COLORS
    p1.setLabel("bottom", "Temperature (°C)", color=tc)
    p1.setLabel("left", "Peak λ (nm)", color=_ch[0])
    p1.layout.setColumnMinimumWidth(0, STABILITY_PLOT_COL_LEFT)
    p1.getAxis("bottom").setPen(axis_pen)
    p1.getAxis("bottom").setTextPen(axis_pen)
    p1.getAxis("left").setPen(_pg.mkPen(color=_ch[0], width=1))
    p1.getAxis("left").setTextPen(_pg.mkPen(color=_ch[0]))

    p1.vb.setZValue(-100)

    curve_peak_nm = pw.plot(
        [],
        [],
        pen=_pg.mkPen(_ch[0], width=2),
        symbol="s",
        symbolSize=6,
        symbolBrush=_ch[0],
        symbolPen=_pg.mkPen(_ch[0]),
    )
    curve_peak_nm_hc = pw.plot(
        [],
        [],
        pen=_pg.mkPen(_hc[0], width=2),
        symbol="s",
        symbolSize=6,
        symbolBrush=_hc[0],
        symbolPen=_pg.mkPen(_hc[0]),
    )

    p2 = _pg.ViewBox()
    p1.showAxis("right")
    p1.scene().addItem(p2)
    p1.getAxis("right").linkToView(p2)
    p2.setXLink(p1.vb)
    p2.setZValue(10)
    p1.getAxis("right").setLabel("SMSR (dB)", color=_ch[2])
    p1.getAxis("right").setPen(_pg.mkPen(color=_ch[2], width=1))
    p1.getAxis("right").setTextPen(_pg.mkPen(color=_ch[2]))
    curve_smsr = _pg.PlotDataItem(
        [],
        [],
        pen=_pg.mkPen(_ch[2], width=2),
        name="SMSR",
        symbol="x",
        symbolSize=7,
        symbolBrush=_ch[2],
        symbolPen=_pg.mkPen(_ch[2]),
    )
    p2.addItem(curve_smsr)
    curve_smsr_hc = _pg.PlotDataItem(
        [],
        [],
        pen=_pg.mkPen(_hc[2], width=2),
        name="SMSR h→c",
        symbol="x",
        symbolSize=7,
        symbolBrush=_hc[2],
        symbolPen=_pg.mkPen(_hc[2]),
    )
    p2.addItem(curve_smsr_hc)

    p3 = _pg.ViewBox()
    ax3 = _pg.AxisItem("right")
    p1.layout.addItem(ax3, 2, 3)
    p1.layout.setColumnMinimumWidth(3, STABILITY_PLOT_COL_RIGHT_EXTRA)
    p1.scene().addItem(p3)
    ax3.linkToView(p3)
    p3.setXLink(p1.vb)
    p3.setZValue(10)
    ax3.setLabel("Peak lvl (dBm)", color=_ch[3])
    ax3.setPen(_pg.mkPen(color=_ch[3], width=1))
    ax3.setTextPen(_pg.mkPen(color=_ch[3]))
    curve_pk_lv = _pg.PlotDataItem(
        [],
        [],
        pen=_pg.mkPen(_ch[3], width=2, style=QtCompat.DashLine),
        name="Peak level",
        symbol="o",
        symbolSize=5,
        symbolBrush=_ch[3],
        symbolPen=_pg.mkPen(_ch[3]),
    )
    p3.addItem(curve_pk_lv)
    curve_pk_lv_hc = _pg.PlotDataItem(
        [],
        [],
        pen=_pg.mkPen(_hc[3], width=2, style=QtCompat.DashLine),
        name="Peak level h→c",
        symbol="o",
        symbolSize=5,
        symbolBrush=_hc[3],
        symbolPen=_pg.mkPen(_hc[3]),
    )
    p3.addItem(curve_pk_lv_hc)

    p4 = _pg.ViewBox()
    ax4 = _pg.AxisItem("right")
    p1.layout.addItem(ax4, 2, 4)
    p1.layout.setColumnMinimumWidth(4, STABILITY_PLOT_COL_RIGHT_EXTRA)
    p1.scene().addItem(p4)
    ax4.linkToView(p4)
    p4.setXLink(p1.vb)
    p4.setZValue(10)
    ax4.setLabel("FWHM (nm)", color=_ch[1])
    ax4.setPen(_pg.mkPen(color=_ch[1], width=1))
    ax4.setTextPen(_pg.mkPen(color=_ch[1]))
    curve_fwhm = _pg.PlotDataItem(
        [],
        [],
        pen=_pg.mkPen(_ch[1], width=2),
        name="FWHM",
        symbol="t",
        symbolSize=6,
        symbolBrush=_ch[1],
        symbolPen=_pg.mkPen(_ch[1]),
    )
    p4.addItem(curve_fwhm)
    curve_fwhm_hc = _pg.PlotDataItem(
        [],
        [],
        pen=_pg.mkPen(_hc[1], width=2),
        name="FWHM h→c",
        symbol="t",
        symbolSize=6,
        symbolBrush=_hc[1],
        symbolPen=_pg.mkPen(_hc[1]),
    )
    p4.addItem(curve_fwhm_hc)

    p5 = _pg.ViewBox()
    ax5 = _pg.AxisItem("right")
    p1.layout.addItem(ax5, 2, 5)
    p1.layout.setColumnMinimumWidth(5, STABILITY_PLOT_COL_RIGHT_EXTRA)
    p1.scene().addItem(p5)
    ax5.linkToView(p5)
    p5.setXLink(p1.vb)
    p5.setZValue(10)
    ax5.setLabel("Thorlabs (mW)", color=_ch[4])
    ax5.setPen(_pg.mkPen(color=_ch[4], width=1))
    ax5.setTextPen(_pg.mkPen(color=_ch[4]))
    curve_thorlabs = _pg.PlotDataItem(
        [],
        [],
        pen=_pg.mkPen(_ch[4], width=2),
        name="Thorlabs",
        symbol="d",
        symbolSize=5,
        symbolBrush=_ch[4],
        symbolPen=_pg.mkPen(_ch[4]),
    )
    p5.addItem(curve_thorlabs)
    curve_thorlabs_hc = _pg.PlotDataItem(
        [],
        [],
        pen=_pg.mkPen(_hc[4], width=2),
        name="Thorlabs h→c",
        symbol="d",
        symbolSize=5,
        symbolBrush=_hc[4],
        symbolPen=_pg.mkPen(_hc[4]),
    )
    p5.addItem(curve_thorlabs_hc)

    def _sync_vbs() -> None:
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

    for _ax in (p1.getAxis("left"), p1.getAxis("bottom"), p1.getAxis("right"), ax3, ax4, ax5):
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
    series_spec = [
        {"curve": curve_peak_nm, "curve_alt": curve_peak_nm_hc, "axis": p1.getAxis("left")},
        {"curve": curve_fwhm, "curve_alt": curve_fwhm_hc, "axis": ax4},
        {"curve": curve_smsr, "curve_alt": curve_smsr_hc, "axis": p1.getAxis("right")},
        {"curve": curve_pk_lv, "curve_alt": curve_pk_lv_hc, "axis": ax3},
        {"curve": curve_thorlabs, "curve_alt": curve_thorlabs_hc, "axis": ax5},
    ]
    ts_cb_row, _ = make_series_checkbox_row(
        series_spec,
        STABILITY_SERIES_LABELS,
        legend=None,
        color_swatch_pairs=_sw_pairs,
    )

    return StabilityTabPlotBundle(
        plot_widget=pw,
        p1=p1,
        curve_peak_nm=curve_peak_nm,
        curve_peak_nm_hc=curve_peak_nm_hc,
        curve_fwhm=curve_fwhm,
        curve_fwhm_hc=curve_fwhm_hc,
        curve_smsr=curve_smsr,
        curve_smsr_hc=curve_smsr_hc,
        curve_pk_lv=curve_pk_lv,
        curve_pk_lv_hc=curve_pk_lv_hc,
        curve_thorlabs=curve_thorlabs,
        curve_thorlabs_hc=curve_thorlabs_hc,
        vb_smsr=p2,
        vb_pk_lv=p3,
        vb_fwhm=p4,
        vb_thorlabs=p5,
        series_checkbox_row=ts_cb_row,
        sync_stability_vbs=_sync_vbs,
    )


def stability_tab_clear_plot(b: StabilityTabPlotBundle) -> None:
    try:
        for c in (
            b.curve_peak_nm,
            b.curve_peak_nm_hc,
            b.curve_fwhm,
            b.curve_fwhm_hc,
            b.curve_smsr,
            b.curve_smsr_hc,
            b.curve_pk_lv,
            b.curve_pk_lv_hc,
            b.curve_thorlabs,
            b.curve_thorlabs_hc,
        ):
            c.setData([], [])
    except Exception:
        pass


def _result_seq(result: Any, name: str) -> List[Any]:
    """List field from a dataclass/namespace or a plain dict (saved JSON)."""
    if isinstance(result, dict):
        v = result.get(name)
        if v is None:
            return []
        return list(v) if isinstance(v, (list, tuple)) else []
    v = getattr(result, name, None)
    if v is None:
        return []
    return list(v) if isinstance(v, (list, tuple)) else []


def stability_tab_apply_result(b: StabilityTabPlotBundle, result: Any) -> None:
    """Load final stability arrays from a process result object (omits same-temperature retry rows for display)."""
    tx = [_to_f(v) for v in _result_seq(result, "temperature_c")]
    fy = [_to_f(v) for v in _result_seq(result, "fwhm_nm")]
    sy_db = list(_result_seq(result, "smsr_db"))
    py = [_to_f(v) for v in _result_seq(result, "peak_wavelength_nm")]
    lv = [_to_f(v) for v in _result_seq(result, "peak_level_dbm")]
    tl = [_to_f(v) for v in _result_seq(result, "thorlabs_power_mw")]
    pst = _result_seq(result, "point_status")
    if not tx:
        stability_tab_clear_plot(b)
        return
    # Core sweep length: do not let a short optional column (SMSR / Thorlabs) drop n to 0.
    n = min(len(tx), len(py), len(fy), len(lv))
    if n < 1:
        stability_tab_clear_plot(b)
        return
    if len(sy_db) < n:
        sy_db = sy_db + [None] * (n - len(sy_db))
    else:
        sy_db = sy_db[:n]
    try:
        tx = tx[:n]
        py = py[:n]
        fy = fy[:n]
        lv = lv[:n]
        sy = stability_smsr_y_for_plot(result, sy_db, lv, n)
        if tl and len(tl) >= n:
            tl = tl[:n]
        else:
            tl = [float("nan")] * n
        codes = _result_val(result, "point_ramp_code", None)
        if isinstance(codes, list) and len(codes) >= n:
            codes = codes[:n]
        else:
            codes = None
        # Plot: one point per setpoint — drop intermediate same-temperature retries (raw data stays in JSON).
        if isinstance(pst, list) and len(pst) >= n:
            keep = [i for i in range(n) if str(pst[i]).strip().lower() != "retry"]
        else:
            keep = list(range(n))
        if not keep:
            stability_tab_clear_plot(b)
            return
        if len(keep) < n:
            tx = [tx[i] for i in keep]
            py = [py[i] for i in keep]
            fy = [fy[i] for i in keep]
            lv = [lv[i] for i in keep]
            tl = [tl[i] for i in keep]
            sy_db = [sy_db[i] for i in keep]
            n = len(keep)
            sy = stability_smsr_y_for_plot(result, sy_db, lv, n)
            if isinstance(codes, list) and len(codes) >= n:
                codes = [codes[i] for i in keep]
            else:
                codes = None
        dx_ch, dpy_ch, dfy_ch, dsy_ch, dlv_ch, dtl_ch = stability_arrays_for_ramp(
            tx, py, fy, sy, lv, tl, codes, "c_h"
        )
        dx_hc, dpy_hc, dfy_hc, dsy_hc, dlv_hc, dtl_hc = stability_arrays_for_ramp(
            tx, py, fy, sy, lv, tl, codes, "h_c"
        )
        b.curve_peak_nm.setData(dx_ch, dpy_ch)
        b.curve_peak_nm_hc.setData(dx_hc, dpy_hc)
        b.curve_fwhm.setData(dx_ch, dfy_ch)
        b.curve_fwhm_hc.setData(dx_hc, dfy_hc)
        b.curve_smsr.setData(dx_ch, dsy_ch)
        b.curve_smsr_hc.setData(dx_hc, dsy_hc)
        b.curve_pk_lv.setData(dx_ch, dlv_ch)
        b.curve_pk_lv_hc.setData(dx_hc, dlv_hc)
        b.curve_thorlabs.setData(dx_ch, dtl_ch)
        b.curve_thorlabs_hc.setData(dx_hc, dtl_hc)
    except Exception:
        pass
    try:
        if b.p1 is not None:
            b.p1.getAxis("right").setLabel("SMSR (dB)", color=STABILITY_RAMP_C_H_COLORS[2])
    except Exception:
        pass
    stability_tab_autorange(b)


def stability_tab_autorange(b: StabilityTabPlotBundle) -> None:
    """Fit X and each Y axis (respecting series visibility). Port of TemperatureStabilityWindow._autorange_stability_axes."""
    p1 = b.p1
    if p1 is None:
        return

    def _xvals_from_curve(curve: Any) -> List[float]:
        if curve is None:
            return []
        try:
            xd = pg_curve_axis_list(curve, "x")
        except Exception:
            return []
        out: List[float] = []
        for x in xd:
            try:
                v = float(x)
            except (TypeError, ValueError):
                continue
            if math.isfinite(v):
                out.append(v)
        return out

    def _yrange_from_ydata_pair(c1: Any, c2: Any) -> Optional[tuple]:
        ys: List[float] = []
        for c in (c1, c2):
            if c is None:
                continue
            try:
                ys_raw = pg_curve_axis_list(c, "y")
            except Exception:
                continue
            for v in ys_raw:
                try:
                    x = float(v)
                except (TypeError, ValueError):
                    continue
                if math.isfinite(x):
                    ys.append(x)
        if not ys:
            return None
        lo, hi = min(ys), max(ys)
        span = hi - lo
        # Always include *all* points; add small padding so symbols aren't clipped.
        pad = max(span * 0.12, 0.08)
        if span < 1e-12:
            pad = max(abs(lo) * 0.1, 0.1)
        return lo - pad, hi + pad

    def _vis_pair(c1: Any, c2: Any) -> bool:
        v1 = c1 is None or not hasattr(c1, "isVisible") or c1.isVisible()
        v2 = c2 is None or not hasattr(c2, "isVisible") or c2.isVisible()
        return v1 or v2

    try:
        xs = _xvals_from_curve(b.curve_peak_nm) + _xvals_from_curve(getattr(b, "curve_peak_nm_hc", None))
        for c in (
            b.curve_smsr,
            getattr(b, "curve_smsr_hc", None),
            b.curve_fwhm,
            getattr(b, "curve_fwhm_hc", None),
            b.curve_pk_lv,
            getattr(b, "curve_pk_lv_hc", None),
            b.curve_thorlabs,
            getattr(b, "curve_thorlabs_hc", None),
        ):
            xs.extend(_xvals_from_curve(c))
        if not xs:
            return
        x0, x1 = min(xs), max(xs)
        dx_pad = x1 - x0
        if dx_pad < 1e-12:
            px = 0.15
        else:
            px = max(dx_pad * 0.10, 0.03)
        p1.vb.setXRange(x0 - px, x1 + px, padding=0)
    except Exception:
        pass

    r_pk = _yrange_from_ydata_pair(b.curve_peak_nm, getattr(b, "curve_peak_nm_hc", None))
    if r_pk is not None and _vis_pair(b.curve_peak_nm, getattr(b, "curve_peak_nm_hc", None)):
        p1.vb.setYRange(r_pk[0], r_pk[1], padding=0)
    r_s = _yrange_from_ydata_pair(b.curve_smsr, getattr(b, "curve_smsr_hc", None))
    if r_s is not None and b.vb_smsr is not None and _vis_pair(b.curve_smsr, getattr(b, "curve_smsr_hc", None)):
        b.vb_smsr.setYRange(r_s[0], r_s[1], padding=0)
    r_lv = _yrange_from_ydata_pair(b.curve_pk_lv, getattr(b, "curve_pk_lv_hc", None))
    if r_lv is not None and b.vb_pk_lv is not None and _vis_pair(b.curve_pk_lv, getattr(b, "curve_pk_lv_hc", None)):
        b.vb_pk_lv.setYRange(r_lv[0], r_lv[1], padding=0)
    r_f = _yrange_from_ydata_pair(b.curve_fwhm, getattr(b, "curve_fwhm_hc", None))
    if r_f is not None and b.vb_fwhm is not None and _vis_pair(b.curve_fwhm, getattr(b, "curve_fwhm_hc", None)):
        b.vb_fwhm.setYRange(r_f[0], r_f[1], padding=0)
    r_th = _yrange_from_ydata_pair(b.curve_thorlabs, getattr(b, "curve_thorlabs_hc", None))
    if r_th is not None and b.vb_thorlabs is not None and _vis_pair(b.curve_thorlabs, getattr(b, "curve_thorlabs_hc", None)):
        b.vb_thorlabs.setYRange(r_th[0], r_th[1], padding=0)

    try:
        b.sync_stability_vbs()
    except Exception:
        pass
    try:
        pw = getattr(b, "plot_widget", None)
        if pw is not None:
            pw.update()
    except Exception:
        pass
