"""
Normalize Ando WDATA/LDATA for PyQtGraph: plain Python lists of float, aligned length, finite values only.
"""
from __future__ import annotations

import math
from typing import Any, List, Optional, Tuple

# Typical Ando log display: reference level at top, this many divisions downward.
DEFAULT_OSA_VERTICAL_DIVISIONS = 10


def spectrum_plot_x_range_nm(center_nm: float, span_nm: float) -> Tuple[float, float]:
    """Horizontal extent of a single sweep (matches CTR ± SPAN/2 on the instrument)."""
    half = max(1e-9, float(span_nm) * 0.5)
    c = float(center_nm)
    return c - half, c + half


def spectrum_plot_y_range_dbm(
    ref_level_dbm: float,
    db_per_div: float,
    n_divisions: int = DEFAULT_OSA_VERTICAL_DIVISIONS,
) -> Optional[Tuple[float, float]]:
    """
    Vertical extent for log-scale level (dBm): reference at top, n divisions × dB/div downward.
    Returns None if scale is not a valid log dB/div (e.g. linear mode) — use auto-range for Y.
    """
    ls = float(db_per_div)
    if ls <= 0 or ls > 15.0:
        return None
    y_top = float(ref_level_dbm)
    y_bot = y_top - ls * float(n_divisions)
    return y_bot, y_top


def spectrum_wavemeter_bottom_axis_label(
    wavelength_nm: Optional[Any],
    *,
    default: str = "Wavelength (nm)",
) -> str:
    """
    Text for the plot bottom axis: the wavemeter wavelength in nm with up to 12 fractional digits
    (trailing zeros trimmed). Tick values stay trace wavelengths; only this title shows the reading.
    """
    if wavelength_nm is None:
        return default
    try:
        x = float(wavelength_nm)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(x):
        return default
    s = ("{:.12f}".format(x)).rstrip("0").rstrip(".")
    if s in ("", "-", "-0"):
        return default
    return "{} nm".format(s)


def pair_trace_floats(wdata: Any, ldata: Any) -> Tuple[List[float], List[float]]:
    """
    Convert instrument traces (list, tuple, numpy 1-D, etc.) to aligned ``List[float]`` for plotting.

    Pairs where either value is missing, non-numeric, or non-finite are skipped so the GUI always
    receives data ``setData`` can render.
    """
    if wdata is None or ldata is None:
        return [], []
    try:
        w = list(wdata)
        l_ = list(ldata)
    except (TypeError, ValueError):
        return [], []
    n = min(len(w), len(l_))
    out_w: List[float] = []
    out_l: List[float] = []
    for i in range(n):
        try:
            aw = float(w[i])
            al = float(l_[i])
            if math.isfinite(aw) and math.isfinite(al):
                out_w.append(aw)
                out_l.append(al)
        except (TypeError, ValueError):
            continue
    return out_w, out_l
