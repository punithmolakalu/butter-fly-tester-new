#!/usr/bin/env python3
"""
Minimal bench script:
  1) Connect Ando (GPIB)
  2) Connect Arroyo (COM)
  3) TEC on + laser on (from recipe)
  4) Apply Ando settings from recipe JSON
  5) One single sweep (SGL), then read WDATA/LDATA (driver)
  6) Print data detection (DTNUM/SMPL vs lengths), then samples; optional --strict exit 1 on failure
  7) Laser off, TEC off, disconnect

Shared WDATA/LDATA logic: scripts/ando_wdata_ldata_terminal_common.py

  python scripts/ando_wdata_ldata_terminal_test.py --ando GPIB0::5::INSTR --arroyo COM5
  python scripts/ando_wdata_ldata_terminal_test.py --ando GPIB0::5::INSTR --strict
"""
from __future__ import annotations

import argparse
import os
import sys
from types import SimpleNamespace

# Project root, then scripts/ so we can import ando_wdata_ldata_terminal_common
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

import ando_wdata_ldata_terminal_common as ando_term  # noqa: E402

from operations.arroyo_laser_helpers import apply_arroyo_recipe_and_laser_on_for_spectrum  # noqa: E402
from operations.spectrum.spectrum_process import SpectrumProcess, SpectrumProcessParameters  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Ando + Arroyo: TEC/laser on, single sweep, WDATA/LDATA only")
    ap.add_argument(
        "--recipe",
        default=os.path.join(_ROOT, "scripts", "sample_ando_spectrum_terminal_rcp.json"),
        help="JSON with OPERATIONS.SPECTRUM + laser current",
    )
    ap.add_argument("--ando", default="", help="GPIB e.g. GPIB0::5::INSTR or 5")
    ap.add_argument("--arroyo", default="COM5", help="Arroyo COM port")
    ap.add_argument("--full", action="store_true", help="Print full WDATA/LDATA lists (can be long)")
    ap.add_argument(
        "--strict",
        action="store_true",
        help="Exit with code 1 if data detection fails (empty trace, len mismatch, or len != DTNUM?).",
    )
    args = ap.parse_args()

    recipe = ando_term.load_recipe(args.recipe)
    params = SpectrumProcessParameters.from_recipe(recipe)

    ando = None
    arroyo = None
    try:
        print("1) Connect Ando...")
        ando = ando_term.connect_ando(args.ando.strip())
        print("   OK", getattr(ando, "gpib_address", ""))

        print("2) Connect Arroyo...")
        arroyo = ando_term.connect_arroyo((args.arroyo or "").strip() or None)
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
        ando_term.apply_atref_for_test(ando, ando_term.recipe_spectrum_auto_ref(recipe))

        print(
            "4) Single sweep, collect WDATA/LDATA only - CTR={:.3f} nm span={:.3f} nm RES={:.3f} nm".format(
                params.center_nm, params.span_nm, params.resolution_nm
            )
        )
        wdata, ldata = ando_term.collect_wdata_ldata(ando, do_sweep=True)
        ok_trace, det_lines = ando_term.detect_wdata_ldata(
            ando, wdata, ldata, recipe_sampling=int(params.sampling_points)
        )
        for line in det_lines:
            print(line)
        ando_term.print_wdata_ldata(wdata, ldata, args.full, header="--- WDATA / LDATA (only) ---")

        if args.strict and not ok_trace:
            print("Exit 1 (--strict): data detection failed.")
            return 1
        return 0
    except Exception as e:
        print("ERROR:", e)
        return 1
    finally:
        if arroyo is not None:
            ando_term.shutdown_arroyo_laser_and_tec(arroyo)
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
