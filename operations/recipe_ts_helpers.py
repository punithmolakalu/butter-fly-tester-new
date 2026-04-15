"""
Shared helpers for recipe load/display (numeric keys, alternate spellings).
"""
from __future__ import annotations

from typing import Any, Dict, Optional, Tuple


def extract_recipe_wavelength_nm(recipe: Any) -> Optional[float]:
    """
    Nominal laser wavelength (nm) from a loaded recipe dict.
    Checks top-level, GENERAL, OPERATIONS.SPECTRUM (center), OPERATIONS.LIV, and legacy top-level LIV.
    """
    if not isinstance(recipe, dict):
        return None

    def _pos_float(v: Any) -> Optional[float]:
        if v is None or v == "":
            return None
        try:
            x = float(v)
            return x if x > 0 else None
        except (TypeError, ValueError):
            return None

    for k in ("Wavelength", "wavelength"):
        w = _pos_float(recipe.get(k))
        if w is not None:
            return w
    g = recipe.get("GENERAL") or recipe.get("general")
    if isinstance(g, dict):
        for k in ("Wavelength", "wavelength"):
            w = _pos_float(g.get(k))
            if w is not None:
                return w
    op = recipe.get("OPERATIONS") or recipe.get("operations") or {}
    if isinstance(op, dict):
        spec = op.get("SPECTRUM") or op.get("spectrum")
        if isinstance(spec, dict):
            for k in ("center_nm", "CenterWL", "wavelength", "Wavelength", "Center"):
                w = _pos_float(spec.get(k))
                if w is not None:
                    return w
        liv = op.get("LIV") or op.get("liv")
        if isinstance(liv, dict):
            for k in ("wavelength", "Wavelength"):
                w = _pos_float(liv.get(k))
                if w is not None:
                    return w
    liv_top = recipe.get("LIV")
    if isinstance(liv_top, dict):
        for k in ("wavelength", "Wavelength"):
            w = _pos_float(liv_top.get(k))
            if w is not None:
                return w
    return None


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
