"""
Graphical overlays for LIV Method-1: threshold current Ith and slope efficiency SE.

Draws on a pyqtgraph PlotItem: P=0 guide, (Ith, 0) marker, analytic line P = SE·(I−Ith),
highlight of the linear fit segment, fit-point markers, and a short text legend.
"""
from __future__ import annotations

from typing import Any, List, Optional, Sequence

try:
    from PyQt5.QtCore import Qt
except ImportError:
    Qt = None  # type: ignore[misc, assignment]


def apply_liv_se_ith_overlays(
    plot_item: Any,
    pg: Any,
    currents: Sequence[float],
    powers: Sequence[float],
    ith: float,
    se: float,
    slope_fit_currents: Optional[Sequence[float]],
    slope_fit_powers: Optional[Sequence[float]],
    overlay_items: List[Any],
    *,
    dark_theme: bool = True,
) -> None:
    """
    Append SE/Ith visualization items to ``overlay_items`` (caller owns list and prior clear).

    ``pg`` is the pyqtgraph module (``import pyqtgraph as pg``).
    """
    if plot_item is None or not currents or not powers:
        return
    try:
        i_lo = float(min(currents))
        i_hi = float(max(currents))
        p_max = float(max(powers))
    except (TypeError, ValueError):
        return
    if i_hi <= i_lo:
        return

    tc = "#e6e6e6" if dark_theme else "#222222"

    # P = 0 guide (see threshold intercept on power axis)
    try:
        dot = Qt.DotLine if Qt is not None else 1
        zline = pg.InfiniteLine(pos=0, angle=0, pen=pg.mkPen("#888888", width=1, style=dot))
        zline.setZValue(3)
        plot_item.addItem(zline)
        overlay_items.append(zline)
    except Exception:
        pass

    if se <= 1e-12:
        return

    ith_f = float(ith)

    # Analytic line P = SE * (I - Ith), from max(Ith, I_lo) to I_hi
    x0 = max(ith_f, i_lo)
    n_pts = 100
    xs = []
    ys = []
    for k in range(n_pts + 1):
        t = k / float(n_pts)
        x = x0 + t * (i_hi - x0)
        y = se * (x - ith_f)
        if y >= -1e-12:
            xs.append(x)
            ys.append(max(0.0, float(y)))
    if len(xs) > 1:
        dash = Qt.DashLine if Qt is not None else 2
        analytic = pg.PlotDataItem(xs, ys, pen=pg.mkPen("#9c27b0", width=2, style=dash))
        analytic.setZValue(4)
        plot_item.addItem(analytic)
        overlay_items.append(analytic)

    # Bold segment on the chosen linear window; fit sample points
    sfc = list(slope_fit_currents or [])
    sfp = list(slope_fit_powers or [])
    if len(sfc) >= 2 and len(sfc) == len(sfp):
        lo = min(float(x) for x in sfc)
        hi = max(float(x) for x in sfc)
        y_lo = se * (lo - ith_f)
        y_hi = se * (hi - ith_f)
        seg = pg.PlotDataItem(
            [lo, hi],
            [max(0.0, y_lo), max(0.0, y_hi)],
            pen=pg.mkPen("#ffc107", width=5),
        )
        seg.setZValue(7)
        plot_item.addItem(seg)
        overlay_items.append(seg)
        sc_fit = pg.ScatterPlotItem(
            [float(x) for x in sfc],
            [float(y) for y in sfp],
            size=9,
            pen=pg.mkPen("#6a1b9a", width=2),
            brush=pg.mkBrush(106, 27, 154, 200),
            symbol="o",
        )
        sc_fit.setZValue(8)
        plot_item.addItem(sc_fit)
        overlay_items.append(sc_fit)

    # Threshold point (Ith, 0)
    if ith_f >= i_lo - abs(i_hi) * 0.05 and ith_f <= i_hi * 1.05:
        sc_ith = pg.ScatterPlotItem(
            [ith_f],
            [0.0],
            size=18,
            pen=pg.mkPen("#2e7d32", width=2),
            brush=pg.mkBrush(46, 125, 50, 220),
            symbol="d",
        )
        sc_ith.setZValue(9)
        plot_item.addItem(sc_ith)
        overlay_items.append(sc_ith)

    # Caption: formula + numeric Ith / SE
    try:
        cap = "Ith = {:.4f} mA\nSE = {:.4f} mW/mA\nP = SE·(I − Ith)".format(ith_f, se)
        txt = pg.TextItem(cap, color=tc, anchor=(0, 1))
        txt.setZValue(15)
        xi = i_lo + (i_hi - i_lo) * 0.02
        yi = p_max * 0.98 if p_max > 0 else 1.0
        txt.setPos(xi, yi)
        plot_item.addItem(txt)
        overlay_items.append(txt)
    except Exception:
        pass


def apply_liv_rated_construction_overlays(
    plot_item: Any,
    pg: Any,
    currents: Sequence[float],
    powers: Sequence[float],
    ir_m: float,
    pr_mw: float,
    p_ir: float,
    i_pr: float,
    overlay_items: List[Any],
    *,
    dark_theme: bool = True,
) -> None:
    """
    Draw L–I construction lines for recipe-rated quantities:

    - **P @ Ir**: vertical at I = Ir from P = 0 to the curve (Ir, P@Ir), then horizontal to the
      left at P = P@Ir (read power on the vertical axis).
    - **I @ Pr**: horizontal at P = Pr from I = I_min to (I@Pr, Pr), then vertical to the
      current axis at I = I@Pr.

    Finite segments only (not full-axis infinite lines).
    """
    _ = dark_theme  # API parity with SE/Ith overlays
    if plot_item is None:
        return
    if len(currents) != len(powers) or len(currents) < 1:
        return
    try:
        cur = [float(x) for x in currents]
    except (TypeError, ValueError):
        return
    try:
        x_lo = float(min(cur))
    except (TypeError, ValueError):
        return

    dash = Qt.DashLine if Qt is not None else 2
    pen_ir = pg.mkPen("#e65100", width=2, style=dash)
    pen_pr = pg.mkPen("#1565c0", width=2, style=dash)
    zc = 6

    try:
        ir = float(ir_m)
        p_at_ir = float(p_ir)
        # Only draw P@Ir construction when Ir lies on the sweep and P@Ir is on the measured curve (not extrapolated 0).
        if ir > 0 and p_at_ir > 1e-15:
            p_at_ir = max(0.0, p_at_ir)
            v_ir = pg.PlotDataItem([ir, ir], [0.0, p_at_ir], pen=pen_ir)
            v_ir.setZValue(zc)
            plot_item.addItem(v_ir)
            overlay_items.append(v_ir)
            xa, xb = sorted([x_lo, ir])
            h_ir = pg.PlotDataItem([xa, xb], [p_at_ir, p_at_ir], pen=pen_ir)
            h_ir.setZValue(zc)
            plot_item.addItem(h_ir)
            overlay_items.append(h_ir)
    except Exception:
        pass

    try:
        pr = float(pr_mw)
        i_at_pr = float(i_pr)
        # I@Pr must be a real intersection on the L–I polyline (caller uses 0 when Pr is never reached).
        if pr > 0 and i_at_pr > 1e-6:
            i_at_pr = max(0.0, i_at_pr)
            xa2, xb2 = sorted([x_lo, i_at_pr])
            h_pr = pg.PlotDataItem([xa2, xb2], [pr, pr], pen=pen_pr)
            h_pr.setZValue(zc)
            plot_item.addItem(h_pr)
            overlay_items.append(h_pr)
            v_pr = pg.PlotDataItem([i_at_pr, i_at_pr], [0.0, pr], pen=pen_pr)
            v_pr.setZValue(zc)
            plot_item.addItem(v_pr)
            overlay_items.append(v_pr)
    except Exception:
        pass
