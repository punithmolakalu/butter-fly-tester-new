"""
Shared helpers for recipe load/display (numeric keys, alternate spellings).
"""
from __future__ import annotations

from typing import Any, Dict, Tuple


def first_in_dict(blk: Any, keys: Tuple[str, ...], default: Any = "") -> Any:
    """First matching key with a non-missing value (0 and False are valid; None and '' skip to next key)."""
    if not isinstance(blk, dict):
        return default
    for k in keys:
        if k not in blk:
            continue
        v = blk[k]
        if v is None or v == "":
            continue
        return v
    return default


def first_or_fallback(
    primary: Dict[str, Any],
    keys: Tuple[str, ...],
    fb: Dict[str, Any],
    fb_keys: Tuple[str, ...],
    default: Any = "",
) -> Any:
    """Like first_in_dict(primary), then first_in_dict(fb); avoids `or` so 0 is not skipped."""
    v = first_in_dict(primary, keys, "")
    if v != "":
        return v
    return first_in_dict(fb, fb_keys, default)


def wait_time_ms_for_display(blk: Dict[str, Any], stab: Dict[str, Any]) -> Any:
    """
    WAIT TIME row is labeled (ms). Prefer WaitTime_ms; else StabilizationTime_s * 1000.
    """
    wt = first_in_dict(blk, ("WaitTime_ms", "wait_time_ms", "WAIT TIME", "wait_time"), "")
    if wt not in (None, ""):
        return wt
    s = first_in_dict(blk, ("StabilizationTime_s", "stab_time_s", "StabilizationTime"), "")
    if s in (None, ""):
        s = first_in_dict(stab, ("StabilizationTime_s", "stab_time_s"), "")
    if s in (None, ""):
        return ""
    try:
        return float(s) * 1000.0
    except (TypeError, ValueError):
        return ""
