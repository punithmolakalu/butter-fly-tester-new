#!/usr/bin/env python3
"""
Minimal bench script:
  1) Connect Ando (GPIB)
  2) Connect Arroyo (COM)
  3) TEC on + laser on (from recipe)
  4) Apply Ando settings from recipe JSON
  5) One single sweep (SGL), then read WDATA? and LDATA? only
  6) Laser off, TEC off, disconnect

  python scripts/ando_wdata_ldata_terminal_test.py --simulate
  python scripts/ando_wdata_ldata_terminal_test.py --ando GPIB0::5::INSTR --arroyo COM5
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, Tuple

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from operations.arroyo_laser_helpers import (  # noqa: E402
    apply_arroyo_recipe_and_laser_on_for_spectrum,
    arroyo_laser_off,
)
from operations.spectrum.spectrum_process import SpectrumProcess, SpectrumProcessParameters  # noqa: E402


def _truthy(v: Any) -> bool:
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    return s in ("1", "true", "yes", "on")


def _recipe_auto_ref(recipe: Dict[str, Any]) -> bool:
    op = recipe.get("OPERATIONS") or recipe.get("operations") or {}
    spec = op.get("SPECTRUM") or op.get("spectrum") or {}
    if not isinstance(spec, dict):
        return False
    return _truthy(spec.get("auto_ref_level", spec.get("AutoRefLevel")))


def _atref(ando: Any, on: bool) -> None:
    if ando is None or not getattr(ando, "is_connected", lambda: False)():
        return
    wc = getattr(ando, "write_command", None)
    if callable(wc):
        wc("ATREF1" if on else "ATREF0")


def _shutdown_arroyo(arroyo: Any) -> None:
    if arroyo is None or not getattr(arroyo, "is_connected", lambda: False)():
        return
    try:
        arroyo_laser_off(arroyo)
        time.sleep(0.25)
        so = getattr(arroyo, "set_output", None)
        if callable(so):
            so(0)
        time.sleep(0.1)
        print("Laser OFF, TEC OFF.")
    except Exception:
        pass


def _load_recipe(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _connect_ando(address: str, simulate: bool) -> Any:
    if simulate:
        from instruments.instrument_simulations import AndoSimulationConnection

        d = AndoSimulationConnection(address=address or "SIM")
        d.connect()
        return d
    from instruments.ando import AndoConnection

    d = AndoConnection(address=address)
    if not d.connect(address if "GPIB" in str(address).upper() else None):
        raise RuntimeError("Ando connect failed.")
    return d


def _connect_arroyo(port: Optional[str], simulate: bool) -> Any:
    if simulate:
        from instruments.instrument_simulations import ArroyoSimulationConnection

        d = ArroyoSimulationConnection(port="SIM")
        d.connect()
        return d
    from instruments.arroyo import ArroyoConnection

    d = ArroyoConnection(port=port)
    if not d.connect():
        raise RuntimeError("Arroyo connect failed.")
    return d


def _single_sweep_collect_wdata_ldata(ando: Any) -> Tuple[List[float], List[float]]:
    """SGL, wait until idle, then read trace A via WDATA? / LDATA? (separate queries; values come from these)."""
    if ando is None:
        return [], []
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
    # Let the OSA finish writing trace buffers before WDATA?/LDATA?
    time.sleep(0.25)
    tw = getattr(ando, "trace_write_a", None)
    if callable(tw):
        tw()
    time.sleep(0.1)
    # WDATA? = wavelength trace A; LDATA? = level trace A (same point count)
    rw = getattr(ando, "read_wdata_trace", None)
    rl = getattr(ando, "read_ldata_trace", None)
    wdata = list(rw() or []) if callable(rw) else []
    ldata = list(rl() or []) if callable(rl) else []
    return wdata, ldata


def _print_wdata_ldata(wdata: List[float], ldata: List[float], full: bool) -> None:
    print("\n--- WDATA / LDATA (only) ---")
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


def main() -> int:
    ap = argparse.ArgumentParser(description="Ando + Arroyo: TEC/laser on, single sweep, WDATA/LDATA only")
    ap.add_argument(
        "--recipe",
        default=os.path.join(_ROOT, "scripts", "sample_ando_spectrum_terminal_rcp.json"),
        help="JSON with OPERATIONS.SPECTRUM + laser current",
    )
    ap.add_argument("--ando", default="", help="GPIB e.g. GPIB0::5::INSTR or 5")
    ap.add_argument("--arroyo", default="COM5", help="Arroyo COM port")
    ap.add_argument("--simulate", action="store_true", help="Simulated instruments")
    ap.add_argument("--full", action="store_true", help="Print full WDATA/LDATA lists (can be long)")
    args = ap.parse_args()

    recipe = _load_recipe(args.recipe)
    params = SpectrumProcessParameters.from_recipe(recipe)

    ando = None
    arroyo = None
    try:
        print("1) Connect Ando...")
        ando = _connect_ando(args.ando.strip(), args.simulate)
        print("   OK", getattr(ando, "gpib_address", ""))

        print("2) Connect Arroyo...")
        arroyo = _connect_arroyo((args.arroyo or "").strip() or None, args.simulate)
        print("   OK", getattr(arroyo, "port", ""))

        print("3) TEC on, laser on (recipe)...")
        ok, err = apply_arroyo_recipe_and_laser_on_for_spectrum(
            arroyo, recipe, log=lambda m: print("  ", m)
        )
        if not ok:
            print("ERROR:", err)
            return 1

        sp = SpectrumProcess()
        sp.set_instruments(arroyo, ando, None)
        ex = SimpleNamespace(log_message=None)
        if not sp._apply_ando_recipe(params, ex):  # noqa: SLF001
            print("ERROR: Ando setup failed.")
            return 1
        _atref(ando, _recipe_auto_ref(recipe))

        print(
            "4) Single sweep, collect WDATA/LDATA only - CTR={:.3f} nm span={:.3f} nm RES={:.3f} nm".format(
                params.center_nm, params.span_nm, params.resolution_nm
            )
        )
        wdata, ldata = _single_sweep_collect_wdata_ldata(ando)
        _print_wdata_ldata(wdata, ldata, args.full)

        return 0
    except Exception as e:
        print("ERROR:", e)
        return 1
    finally:
        if arroyo is not None:
            _shutdown_arroyo(arroyo)
        for dev, name in ((ando, "Ando"), (arroyo, "Arroyo")):
            if dev is None:
                continue
            try:
                fn = getattr(dev, "disconnect", None)
                if callable(fn):
                    fn()
                    print("Disconnected", name + ".")
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
