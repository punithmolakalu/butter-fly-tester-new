"""
Shared WDATA/LDATA validation (DTNUM/SMPL vs lengths) for SpectrumProcess and terminal scripts.
"""
from __future__ import annotations

from typing import Any, List, Optional, Tuple


def _call_optional_int(ando: Any, name: str) -> Optional[int]:
    fn = getattr(ando, name, None)
    if not callable(fn):
        return None
    try:
        v = fn()
    except Exception:
        return None
    if v is None:
        return None
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return None


def detect_wdata_ldata(
    ando: Any,
    wdata: List[float],
    ldata: List[float],
    *,
    recipe_sampling: Optional[int] = None,
    query_instrument: bool = True,
) -> Tuple[bool, List[str]]:
    """
    Validate captured traces: non-empty, equal lengths, optional match to DTNUM? / SMPL? / recipe.
    Returns (ok, lines) for logging. ``ok`` is False if empty, length mismatch, or len != DTNUM? when DTNUM is available.

    If ``query_instrument`` is False, skip DTNUM?/SMPL? (avoids extra GPIB traffic right after WDATA/LDATA reads).
    """
    lines: List[str] = []
    nw, nl = len(wdata), len(ldata)
    lines.append("--- Data detection ---")
    dtnum: Optional[int] = None
    smpl: Optional[int] = None
    if query_instrument:
        dtnum = _call_optional_int(ando, "query_data_point_count")
        smpl = _call_optional_int(ando, "query_sampling_points")
    if dtnum is not None:
        lines.append(f"  DTNUM? points:     {dtnum}")
    else:
        lines.append("  DTNUM?:            (n/a)" + (" — skipped" if not query_instrument else ""))
    if smpl is not None:
        lines.append(f"  SMPL? points:      {smpl}")
    else:
        lines.append("  SMPL?:             (n/a)" + (" — skipped" if not query_instrument else ""))
    if recipe_sampling is not None:
        lines.append(f"  Recipe SMPL:       {recipe_sampling}")

    if not wdata and not ldata:
        lines.append("  RESULT: FAIL — WDATA and LDATA are empty (no trace read).")
        return False, lines
    if not wdata:
        lines.append("  RESULT: FAIL — WDATA empty.")
        return False, lines
    if not ldata:
        lines.append("  RESULT: FAIL — LDATA empty.")
        return False, lines
    if nw != nl:
        lines.append(f"  RESULT: FAIL — length mismatch len(WDATA)={nw} len(LDATA)={nl}.")
        return False, lines

    ok = True
    if dtnum is not None and nw != dtnum:
        lines.append(f"  RESULT: FAIL — len={nw} != DTNUM?={dtnum} (wrong read or partial buffer).")
        ok = False
    elif smpl is not None and nw != smpl:
        lines.append(f"  WARN — len={nw} != SMPL?={smpl} (DTNUM absent; verify firmware).")
    elif recipe_sampling is not None and nw != recipe_sampling:
        lines.append(f"  WARN — len={nw} != recipe SMPL={recipe_sampling} (acceptable if SMPL is AUTO).")
    else:
        lines.append(f"  RESULT: OK — {nw} points, WDATA/LDATA aligned.")

    try:
        wmin, wmax = float(min(wdata)), float(max(wdata))
        lmin, lmax = float(min(ldata)), float(max(ldata))
        lines.append(f"  WDATA span (nm):   {wmin:.6f} .. {wmax:.6f}")
        lines.append(f"  LDATA span (dBm): {lmin:.3f} .. {lmax:.3f}")
        if wmax <= wmin:
            lines.append("  WARN — WDATA min >= max (constant or invalid axis).")
            ok = False
        elif wmin < 200.0 or wmax > 3000.0:
            lines.append("  WARN — WDATA nm range unusual (check units / instrument).")
    except Exception as ex:
        lines.append(f"  WARN — range check failed: {ex}")

    return ok, lines
