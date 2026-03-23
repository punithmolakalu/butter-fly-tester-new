"""
Shared helpers for Ando terminal scripts (WDATA/LDATA).

Used by:
  - scripts/ando_wdata_ldata_terminal_test.py  (Ando + Arroyo + recipe + sweep)
  - scripts/ando_trace_terminal_print.py        (Ando-only terminal print)

Single source for: connect, sweep, read WDATA/LDATA (driver), optional ATREF, print, shutdown,
and trace data detection (DTNUM/SMPL vs lengths).
"""
from __future__ import annotations

import json
import os
import sys
import time
from collections.abc import Iterable
from typing import Any, Dict, List, Optional, Tuple, cast

# Project root (parent of scripts/)
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from operations.spectrum.trace_validation import detect_wdata_ldata  # noqa: E402


def truthy(v: Any) -> bool:
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    return s in ("1", "true", "yes", "on")


def recipe_spectrum_auto_ref(recipe: Dict[str, Any]) -> bool:
    op = recipe.get("OPERATIONS") or recipe.get("operations") or {}
    spec = op.get("SPECTRUM") or op.get("spectrum") or {}
    if not isinstance(spec, dict):
        return False
    return truthy(spec.get("auto_ref_level", spec.get("AutoRefLevel")))


def apply_atref_for_test(ando: Any, on: bool) -> None:
    """After REFL from SpectrumProcess, send ATREF1/0 (test-only scripts)."""
    if ando is None or not getattr(ando, "is_connected", lambda: False)():
        return
    wc = getattr(ando, "write_command", None)
    if callable(wc):
        wc("ATREF1" if on else "ATREF0")


def load_recipe(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def connect_ando(address: str, timeout_s: Optional[float] = None) -> Any:
    from instruments.ando import AndoConnection

    d = AndoConnection(address=address)
    if timeout_s is not None:
        try:
            d.timeout = float(timeout_s)
        except (TypeError, ValueError):
            pass
    if not d.connect(address if "GPIB" in str(address).upper() else None):
        raise RuntimeError("Ando connect failed.")
    return d


def connect_arroyo(port: Optional[str]) -> Any:
    from instruments.arroyo import ArroyoConnection

    d = ArroyoConnection(port=port)
    if not d.connect():
        raise RuntimeError("Arroyo connect failed.")
    return d


def collect_wdata_ldata(ando: Any, *, do_sweep: bool = True) -> Tuple[List[float], List[float]]:
    """
    If do_sweep: SGL, wait until idle, settle, WRTA, then WDATA? / LDATA?.
    If not do_sweep: WRTA, then WDATA? / LDATA? (current trace).
    """
    if ando is None:
        return [], []
    if do_sweep:
        ando.single_sweep()
        wait = getattr(ando, "wait_sweep_done", None)
        if callable(wait):
            wait(timeout_s=180.0)
        else:
            t0 = time.time()
            while (time.time() - t0) < 180.0:
                if getattr(ando, "is_sweep_done", lambda: True)():
                    break
                time.sleep(0.2)
        time.sleep(0.25)
    tw = getattr(ando, "trace_write_a", None)
    if callable(tw):
        tw()
    time.sleep(0.1)
    rw = getattr(ando, "read_wdata_trace", None)
    rl = getattr(ando, "read_ldata_trace", None)
    if callable(rw):
        wdata = list(cast(Iterable[Any], rw() or []))
    else:
        wdata = []
    if callable(rl):
        ldata = list(cast(Iterable[Any], rl() or []))
    else:
        ldata = []
    return wdata, ldata


def print_wdata_ldata(
    wdata: List[float],
    ldata: List[float],
    full: bool,
    *,
    header: str = "--- WDATA / LDATA ---",
) -> None:
    print(f"\n{header}")
    nw, nl = len(wdata), len(ldata)
    print(f"len(WDATA)={nw}  len(LDATA)={nl}")
    if nw != nl:
        print("WARNING: length mismatch.")
        return
    if not wdata:
        print("(empty)")
        return
    if full:
        print("WDATA (nm):", wdata)
        print("LDATA (dBm):", ldata)
        return
    head, tail = 5, 5
    print(f"WDATA min/max: {min(wdata):.6f} ... {max(wdata):.6f}")
    print(f"LDATA min/max: {min(ldata):.6f} ... {max(ldata):.6f}")
    if nw <= head + tail:
        print("WDATA:", wdata)
        print("LDATA:", ldata)
    else:
        print(f"WDATA first {head}:", wdata[:head])
        print(f"WDATA last {tail}:", wdata[-tail:])
        print(f"LDATA first {head}:", ldata[:head])
        print(f"LDATA last {tail}:", ldata[-tail:])
        print("(use --full for complete arrays)")


def project_root() -> str:
    return _ROOT


def shutdown_arroyo_laser_and_tec(arroyo: Any) -> None:
    """Laser output off, then TEC output off. Never raises."""
    if arroyo is None or not getattr(arroyo, "is_connected", lambda: False)():
        return
    try:
        from operations.arroyo_laser_helpers import arroyo_laser_off

        arroyo_laser_off(arroyo)
        time.sleep(0.25)
        so = getattr(arroyo, "set_output", None)
        if callable(so):
            so(0)
        time.sleep(0.1)
        print("Laser OFF, TEC OFF.")
    except Exception:
        pass
