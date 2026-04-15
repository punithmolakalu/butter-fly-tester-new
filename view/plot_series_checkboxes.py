# -*- coding: utf-8 -*-
"""Checkbox rows to show/hide pyqtgraph series without clearing data (visibility only)."""
import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

from PyQt5.QtWidgets import QWidget, QHBoxLayout, QCheckBox, QFrame


STABILITY_SERIES_LABELS: Tuple[str, ...] = (
    "Peak λ (nm)",
    "FWHM (nm)",
    "SMSR (dB)",
    "Peak lvl (dBm)",
    "Thorlabs (mW)",
)
# Order matches checkbox row: Peak λ, FWHM, SMSR, Peak lvl, Thorlabs
# Five maximally-distinct hue families: Red · Blue · Green · Purple · Orange
STABILITY_SERIES_COLORS: Tuple[str, ...] = ("#d32f2f", "#1565c0", "#2e7d32", "#7b1fa2", "#e65100")
# Cold→hot (upward T sweep) — saturated primaries
STABILITY_RAMP_C_H_COLORS: Tuple[str, ...] = ("#d32f2f", "#1565c0", "#2e7d32", "#7b1fa2", "#e65100")
# Hot→cold (verification sweep) — shifted lighter variants of the same hue family
STABILITY_RAMP_H_C_COLORS: Tuple[str, ...] = ("#e91e63", "#00acc1", "#66bb6a", "#ce93d8", "#ffb300")
LIV_SERIES_LABELS: Tuple[str, ...] = ("Power", "Voltage", "PD (μA)")
# Same pens as LIV Process / liv_process_plot (Power, Voltage, PD)
LIV_SERIES_COLORS: Tuple[str, ...] = ("#d32f2f", "#1565c0", "#2e7d32")

# Plot tab PER graph: single trace (dBm vs angle), same blue as PER Process live plot
PER_SERIES_LABELS: Tuple[str, ...] = ("Power",)
PER_SERIES_COLORS: Tuple[str, ...] = ("#1f77b4",)


def pg_curve_axis_list(curve: Any, axis: str) -> List[Any]:
    """Return PlotDataItem *Data as a Python list.

    pyqtgraph stores ``xData`` / ``yData`` as numpy arrays; ``arr or []`` raises
    ``ValueError`` on truthiness, which breaks autorange if swallowed.
    """
    if curve is None:
        return []
    name = "xData" if axis == "x" else "yData"
    raw = getattr(curve, name, None)
    if raw is None:
        return []
    try:
        return list(raw)
    except Exception:
        return []


def freeze_plot_navigation(plot_item: Any, *extra_viewboxes: Any) -> None:
    """
    Disable mouse drag (pan) and wheel zoom so scales only change from code (autorange / setData).
    Enable auto-range so the plot always fits all data points.
    Apply to the main PlotItem and every linked pyqtgraph ViewBox (multi-axis plots).
    """
    try:
        vb0 = plot_item.getViewBox()
        vb0.setMouseEnabled(x=False, y=False)
        vb0.enableAutoRange()
    except Exception:
        pass
    for vb in extra_viewboxes:
        if vb is None:
            continue
        try:
            vb.setMouseEnabled(x=False, y=False)
            vb.enableAutoRange()
        except Exception:
            pass
    try:
        plot_item.setMenuEnabled(False)
    except Exception:
        pass


def stability_arrays_with_duplicate_x_breaks(
    tx: List[float],
    py: List[float],
    fy: List[float],
    sy: List[float],
    lv: List[float],
    tl: List[float],
    abs_tol_c: float = 1e-6,
) -> Tuple[List[float], List[float], List[float], List[float], List[float], List[float]]:
    """
    When the same temperature appears twice in a row (retries, verify + main, etc.), inserting
    NaN breaks stops pyqtgraph from drawing a vertical line between two different y values at one x.
    Raw buffers are unchanged; use this only for display passed to setData.
    """
    n = min(len(tx), len(py), len(fy), len(sy), len(lv), len(tl))
    if n == 0:
        return [], [], [], [], [], []

    def _same_x(a: float, b: float) -> bool:
        try:
            fa, fb = float(a), float(b)
            if math.isnan(fa) or math.isnan(fb):
                return False
            return abs(fa - fb) <= max(abs_tol_c, abs_tol_c * max(abs(fa), abs(fb), 1.0))
        except (TypeError, ValueError):
            return False

    ox: List[float] = []
    opy: List[float] = []
    ofy: List[float] = []
    osy: List[float] = []
    olv: List[float] = []
    otl: List[float] = []
    for i in range(n):
        if i > 0 and _same_x(tx[i], tx[i - 1]):
            ox.append(float("nan"))
            opy.append(float("nan"))
            ofy.append(float("nan"))
            osy.append(float("nan"))
            olv.append(float("nan"))
            otl.append(float("nan"))
        ox.append(float(tx[i]))
        opy.append(float(py[i]))
        ofy.append(float(fy[i]))
        osy.append(float(sy[i]))
        olv.append(float(lv[i]))
        otl.append(float(tl[i]))
    return ox, opy, ofy, osy, olv, otl


def stability_arrays_for_ramp(
    tx: List[float],
    py: List[float],
    fy: List[float],
    sy: List[float],
    lv: List[float],
    tl: List[float],
    codes: Optional[Sequence[str]],
    ramp: str,
) -> Tuple[List[float], List[float], List[float], List[float], List[float], List[float]]:
    """
    Keep only points whose ramp code matches ``ramp`` (``\"c_h\"`` = cold→hot, ``\"h_c\"`` = hot→cold).
    If ``codes`` is missing or shorter than data, all points are treated as cold→hot (backward compatible).
    Applies duplicate-x NaN breaks for display.
    """
    n = min(len(tx), len(py), len(fy), len(sy), len(lv), len(tl))
    if n == 0:
        return [], [], [], [], [], []
    use_codes = codes is not None and len(codes) >= n
    def _sf(v):
        if v is None:
            return float("nan")
        try:
            return float(v)
        except (TypeError, ValueError):
            return float("nan")

    tx_f: List[float] = []
    py_f: List[float] = []
    fy_f: List[float] = []
    sy_f: List[float] = []
    lv_f: List[float] = []
    tl_f: List[float] = []
    for i in range(n):
        c = str(codes[i]).strip().lower() if use_codes else "c_h"
        if c in ("hc", "h-c", "hot_cold", "hot-to-cold"):
            c = "h_c"
        if c in ("ch", "c-h", "cold_hot", "cold-to-hot"):
            c = "c_h"
        if c != ramp and use_codes:
            continue
        if not use_codes and ramp == "h_c":
            continue
        tx_f.append(_sf(tx[i]))
        py_f.append(_sf(py[i]))
        fy_f.append(_sf(fy[i]))
        sy_f.append(_sf(sy[i]))
        lv_f.append(_sf(lv[i]))
        tl_f.append(_sf(tl[i]))
    return stability_arrays_with_duplicate_x_breaks(tx_f, py_f, fy_f, sy_f, lv_f, tl_f)


def apply_series_visibility(
    specs: Sequence[Dict[str, Any]],
    checkboxes: Sequence[QCheckBox],
    legend: Any = None,
) -> None:
    """Toggle curve visibility only. AxisItem visibility is not changed — hiding an axis
    (e.g. PlotItem 'right' for SMSR) breaks the main ViewBox horizontal grid in pyqtgraph."""
    for spec, cb in zip(specs, checkboxes):
        vis = cb.isChecked()
        for key in ("curve", "curve_alt"):
            c = spec.get(key)
            if c is not None:
                try:
                    c.setVisible(vis)
                except Exception:
                    pass
    any_on = any(cb.isChecked() for cb in checkboxes)
    if legend is not None:
        try:
            legend.setVisible(bool(any_on))
        except Exception:
            pass


def make_series_checkbox_row(
    specs: Sequence[Dict[str, Any]],
    labels: Sequence[str],
    parent: Optional[QWidget] = None,
    style_sheet: Optional[str] = None,
    legend: Any = None,
    color_swatches: Optional[Sequence[str]] = None,
    color_swatch_pairs: Optional[Sequence[Tuple[str, str]]] = None,
) -> Tuple[QWidget, List[QCheckBox]]:
    """
    One row of QCheckBoxes; toggling updates curve visibility (axes stay visible). Data is unchanged.
    len(specs) must equal len(labels).
    If color_swatches is set (same length as labels), a small color bar is drawn before each label.
    If color_swatch_pairs is set (c→h color, h→c color per series), two bars are shown (overrides color_swatches).
    """
    row = QWidget(parent)
    hl = QHBoxLayout(row)
    hl.setContentsMargins(0, 2, 0, 4)
    hl.setSpacing(10)
    ss = style_sheet or "color: #c8c8c8; font-size: 11px;"
    cbs: List[QCheckBox] = []
    n = len(labels)
    for i in range(n):
        lbl = labels[i]
        if color_swatch_pairs is not None and i < len(color_swatch_pairs):
            pair = color_swatch_pairs[i]
            if pair is not None and len(pair) >= 2:
                c1 = (pair[0] or "").strip()
                c2 = (pair[1] or "").strip()
                if c1 or c2:
                    sw = QWidget()
                    sw_l = QHBoxLayout(sw)
                    sw_l.setContentsMargins(0, 0, 0, 0)
                    sw_l.setSpacing(2)
                    if c1:
                        b1 = QFrame()
                        b1.setFixedSize(14, 6)
                        b1.setStyleSheet(f"background-color: {c1}; border-radius: 3px; border: none;")
                        sw_l.addWidget(b1)
                    if c2:
                        b2 = QFrame()
                        b2.setFixedSize(14, 6)
                        b2.setStyleSheet(f"background-color: {c2}; border-radius: 3px; border: none;")
                        sw_l.addWidget(b2)
                    hl.addWidget(sw)
        elif color_swatches is not None and i < len(color_swatches):
            c = (color_swatches[i] or "").strip()
            if c:
                bar = QFrame()
                bar.setFixedSize(22, 4)
                bar.setStyleSheet(f"background-color: {c}; border-radius: 2px; border: none;")
                hl.addWidget(bar)
        cb = QCheckBox(lbl)
        cb.setChecked(True)
        label_color: Optional[str] = None
        if color_swatch_pairs is not None and i < len(color_swatch_pairs):
            pair = color_swatch_pairs[i]
            if pair is not None and len(pair) >= 1:
                label_color = (pair[0] or "").strip() or None
        elif color_swatches is not None and i < len(color_swatches):
            label_color = (color_swatches[i] or "").strip() or None
        if label_color:
            cb.setStyleSheet(f"color: {label_color}; font-size: 11px; font-weight: bold;")
        else:
            cb.setStyleSheet(ss)
        hl.addWidget(cb)
        cbs.append(cb)
    hl.addStretch(1)

    def _refresh():
        apply_series_visibility(specs, cbs, legend)

    for cb in cbs:
        cb.stateChanged.connect(lambda *_: _refresh())
    _refresh()
    return row, cbs
