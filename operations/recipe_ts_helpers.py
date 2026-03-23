"""
Resolve Temperature Stability 1 / 2 blocks from recipe dicts (OPERATIONS, top-level, STABILITY).
Used by Recipe tab read-only view and Recipe editor load.
"""
from __future__ import annotations

from typing import Any, Dict, Tuple


def _ops(data: Dict[str, Any]) -> Dict[str, Any]:
    op = data.get("OPERATIONS") or data.get("operations")
    return op if isinstance(op, dict) else {}


def find_temperature_stability_block(ops: Dict[str, Any], data: Dict[str, Any], canonical: str) -> Dict[str, Any]:
    """Find block by exact name, then top-level, then case/space-insensitive key match."""
    # Do not use `and block` — empty dict is still a valid (loaded) section.
    if canonical in ops and isinstance(ops[canonical], dict):
        return dict(ops[canonical])
    if canonical in data and isinstance(data[canonical], dict):
        return dict(data[canonical])
    target = canonical.strip().lower().replace(" ", "")
    for container in (ops, data):
        if not isinstance(container, dict):
            continue
        for k, v in container.items():
            if not isinstance(k, str) or not isinstance(v, dict):
                continue
            if k.strip().lower().replace(" ", "") == target:
                return dict(v)
    return {}


def stability_legacy_block(ops: Dict[str, Any], data: Dict[str, Any]) -> Dict[str, Any]:
    """STABILITY under OPERATIONS, or top-level (flat INI / hand-edited JSON)."""
    s = ops.get("STABILITY") or ops.get("Stability") or ops.get("stability")
    if isinstance(s, dict) and s:
        return s
    for key in ("STABILITY", "Stability", "stability"):
        if key in data and isinstance(data[key], dict) and data[key]:
            return dict(data[key])
    return {}


def merge_stability_into_ts1(ts1: Dict[str, Any], stab: Dict[str, Any]) -> Dict[str, Any]:
    """When TS1 block is missing, map legacy STABILITY (temperature/current/duration) for display."""
    if ts1 or not stab:
        return ts1
    out: Dict[str, Any] = {}
    if "temperature" in stab:
        out["InitTemp"] = stab["temperature"]
    if "current" in stab:
        out["Current"] = stab["current"]
    for k, v in stab.items():
        if k not in ("temperature", "current"):
            out.setdefault(k, v)
    return out


def resolve_temperature_stability_blocks(data: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
    """
    Return (ts1, ts2, stab_legacy) merged for UI.
    ts1 includes STABILITY fallbacks when no dedicated Temperature Stability 1 section exists.
    """
    if not isinstance(data, dict):
        return {}, {}, {}
    ops = _ops(data)
    stab = stability_legacy_block(ops, data)
    ts1 = find_temperature_stability_block(ops, data, "Temperature Stability 1")
    ts2 = find_temperature_stability_block(ops, data, "Temperature Stability 2")
    ts1 = merge_stability_into_ts1(ts1, stab)
    return ts1, ts2, stab


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
