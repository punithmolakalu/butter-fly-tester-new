"""PER display helpers: Thorlabs reports power in mW; reference plots use dBm (PM100-style)."""
from __future__ import annotations

import math
from typing import Iterable, List


def mw_to_dbm(p_mw: float) -> float:
    """Convert milliwatts to dBm: 10*log10(mW). Non-positive → floor (noise floor for plotting)."""
    try:
        p = float(p_mw)
        if p <= 0 or not math.isfinite(p):
            return -120.0
        return 10.0 * math.log10(p)
    except Exception:
        return -120.0


def mw_series_to_dbm(mw: Iterable[float]) -> List[float]:
    return [mw_to_dbm(float(x)) for x in mw]
