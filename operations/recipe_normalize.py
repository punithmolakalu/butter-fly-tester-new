"""
Normalize recipe dicts after load so GUI-saved JSON and hand-edited files behave the same at runtime.

RecipeWindow saves: GENERAL.TestSequence (no top-level TEST_SEQUENCE), GENERAL.RecipeName,
OPERATIONS.SPECTRUM.current (lowercase), etc. Test sequence / readonly view / Arroyo helpers
also accept top-level TEST_SEQUENCE, Recipe_Name, Current aliases — we merge missing keys here.
"""
from __future__ import annotations

from typing import Any, Dict


def _pull_known_blocks_from_top(data: Dict[str, Any]) -> Dict[str, Any]:
    """Map top-level section keys to canonical OPERATIONS keys (flat JSON / INI)."""
    out: Dict[str, Any] = {}

    def n(k: str) -> str:
        return k.strip().lower().replace(" ", "").replace("_", "")

    for k, v in data.items():
        if not isinstance(v, dict) or not v:
            continue
        nk = n(k)
        ck = None
        if k in ("LIV", "PER", "SPECTRUM", "STABILITY", "WAVEMETER", "Temperature Stability 1", "Temperature Stability 2"):
            ck = k
        elif nk == "liv":
            ck = "LIV"
        elif nk == "per":
            ck = "PER"
        elif nk == "spectrum":
            ck = "SPECTRUM"
        elif nk == "stability":
            ck = "STABILITY"
        elif nk == "wavemeter":
            ck = "WAVEMETER"
        elif nk in ("temperaturestability1", "tempstability1", "ts1"):
            ck = "Temperature Stability 1"
        elif nk in ("temperaturestability2", "tempstability2", "ts2"):
            ck = "Temperature Stability 2"
        if ck is not None and ck not in out:
            out[ck] = dict(v)
    return out


def hoist_recipe_blocks_into_operations(data: Any) -> None:
    """
    Mutate in-place: ensure OPERATIONS contains LIV/PER/SPECTRUM/TS/STABILITY when present
    at top level or under recipe.OPERATIONS. Merges top-level TS blocks when OPERATIONS exists
    but omits them (common hand-edited layout).
    """
    if not isinstance(data, dict):
        return
    for nest_key in ("recipe", "Recipe"):
        nested = data.get(nest_key)
        if isinstance(nested, dict) and isinstance(nested.get("OPERATIONS"), dict) and nested["OPERATIONS"]:
            data["OPERATIONS"] = nested["OPERATIONS"]
            return
    op = data.get("OPERATIONS") or data.get("operations")
    if not isinstance(op, dict):
        op = {}
    pulled = _pull_known_blocks_from_top(data)
    for ck, blk in pulled.items():
        if not isinstance(blk, dict) or not blk:
            continue
        if ck not in op or not op[ck]:
            op[ck] = blk
    if op:
        data["OPERATIONS"] = op


def _f(x: Any) -> float:
    try:
        if x is None or x == "":
            return 0.0
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def _first_positive_current(op: Dict[str, Any], g: Dict[str, Any]) -> float:
    """Best-effort drive current (mA) from typical OPERATIONS + GENERAL blocks."""
    spec = op.get("SPECTRUM") or op.get("spectrum") or {}
    if isinstance(spec, dict):
        for k in ("Current", "current", "laser_current_mA"):
            v = _f(spec.get(k))
            if v > 0:
                return v
    liv = op.get("LIV") or op.get("liv") or {}
    if isinstance(liv, dict):
        for k in ("rated_current_mA", "min_current_mA"):
            v = _f(liv.get(k))
            if v > 0:
                return v
    per = op.get("PER") or op.get("per") or {}
    if isinstance(per, dict):
        for k in ("Current", "current"):
            v = _f(per.get(k))
            if v > 0:
                return v
    for k in ("Current", "current", "SetCurr", "set_curr"):
        v = _f(g.get(k))
        if v > 0:
            return v
    return 0.0


def normalize_loaded_recipe(data: Any) -> Any:
    """
    Mutate in-place: fills missing canonical keys so runtime and UI agree.
    Call on dicts returned from json.load for Butterfly-style recipes (OPERATIONS block).
    """
    if not isinstance(data, dict):
        return data
    hoist_recipe_blocks_into_operations(data)
    op = data.get("OPERATIONS") or data.get("operations")
    if not isinstance(op, dict):
        return data

    g = data.get("GENERAL") or data.get("general")
    if not isinstance(g, dict):
        g = {}
    data["GENERAL"] = g

    # Top-level metadata (readonly view + some scripts expect these)
    if not data.get("Recipe_Name") and not data.get("recipe_name"):
        rn = g.get("RecipeName") or g.get("recipe_name")
        if rn is not None and str(rn).strip():
            data["Recipe_Name"] = str(rn).strip()
    if data.get("Description") in (None, "") and g.get("Comments") not in (None, ""):
        data["Description"] = str(g.get("Comments"))

    # Test sequence: RecipeWindow saves only GENERAL.TestSequence
    if not data.get("TEST_SEQUENCE") and not data.get("TestSequence"):
        ts = g.get("TestSequence") or g.get("TEST_SEQUENCE")
        if isinstance(ts, list) and ts:
            data["TEST_SEQUENCE"] = [str(x) for x in ts]
        elif isinstance(ts, str) and ts.strip():
            data["TEST_SEQUENCE"] = [ts.strip()]

    # SPECTRUM: keep Current + current in sync (save uses lowercase "current")
    spec = op.get("SPECTRUM") or op.get("spectrum")
    if isinstance(spec, dict):
        c = _f(spec.get("Current")) or _f(spec.get("current")) or _f(spec.get("laser_current_mA"))
        if c > 0:
            spec["Current"] = c
            spec["current"] = c

    # GENERAL: laser current mA for fallbacks (RecipeWindow historically omitted this)
    cur_g = _f(g.get("Current")) or _f(g.get("current"))
    if cur_g <= 0:
        fc = _first_positive_current(op, g)
        if fc > 0:
            g["Current"] = fc

    # Temperature Stability blocks: copy current if step omits it
    for step_key in ("Temperature Stability 1", "Temperature Stability 2"):
        blk = op.get(step_key)
        if not isinstance(blk, dict):
            continue
        cur_b = _f(blk.get("Current")) or _f(blk.get("current"))
        if cur_b > 0:
            blk["Current"] = cur_b
            blk["current"] = cur_b
            continue
        ref = _f(g.get("Current")) or _f(g.get("current"))
        if ref <= 0:
            spec2 = op.get("SPECTRUM") or op.get("spectrum") or {}
            if isinstance(spec2, dict):
                ref = _f(spec2.get("Current")) or _f(spec2.get("current"))
        if ref > 0:
            blk["Current"] = ref
            blk["current"] = ref

    return data
