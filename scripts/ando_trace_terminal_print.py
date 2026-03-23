#!/usr/bin/env python3
"""
Print Ando trace values to the terminal only (no matplotlib, no PNG).

Uses scripts/ando_wdata_ldata_terminal_common.py — same collect/print as
ando_wdata_ldata_terminal_test.py, plus data detection (DTNUM/SMPL vs lengths); use --strict for CI.

Ando-only: no Arroyo / TEC / laser.

  python scripts/ando_trace_terminal_print.py --address GPIB0::1::INSTR --recipe scripts/sample_ando_spectrum_terminal_rcp.json --strict
"""
from __future__ import annotations

import argparse
import os
import sys
from types import SimpleNamespace

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

import ando_wdata_ldata_terminal_common as ando_term  # noqa: E402

from operations.spectrum.spectrum_process import SpectrumProcess, SpectrumProcessParameters  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Ando only: apply RCP to OSA, optional sweep, print WDATA/LDATA to terminal (no plot)."
    )
    ap.add_argument("--address", default="GPIB0::1::INSTR", help="GPIB VISA address")
    ap.add_argument(
        "--recipe",
        default=os.path.join(_ROOT, "scripts", "sample_ando_spectrum_terminal_rcp.json"),
        help="Recipe JSON with OPERATIONS.SPECTRUM (center, span, SMPL, etc.)",
    )
    ap.add_argument("--no-sweep", action="store_true", help="Do not run SGL; read current trace only")
    ap.add_argument("--full", action="store_true", help="Print full WDATA/LDATA lists")
    ap.add_argument(
        "--strict",
        action="store_true",
        help="Exit with code 1 if data detection fails (empty, len mismatch, or len != DTNUM?).",
    )
    ap.add_argument(
        "--extras",
        action="store_true",
        help="Also print PKWL? / PKLVL? / SMSR? if supported",
    )
    args = ap.parse_args()

    recipe = ando_term.load_recipe(args.recipe)
    params = SpectrumProcessParameters.from_recipe(recipe)

    ando = None
    try:
        print("Connect Ando:", args.address)
        ando = ando_term.connect_ando(args.address.strip())
        print("OK", getattr(ando, "gpib_address", args.address))

        sp = SpectrumProcess()
        sp.set_instruments(None, ando, None)
        ex = SimpleNamespace(log_message=None)
        if not sp._apply_ando_recipe(params, ex):  # noqa: SLF001
            print("ERROR: Ando setup from recipe failed.")
            return 1
        ando_term.apply_atref_for_test(ando, ando_term.recipe_spectrum_auto_ref(recipe))

        print(
            "Setup: CTR={:.3f} nm  span={:.3f} nm  RES={:.3f} nm  SMPL={}  analysis={}".format(
                params.center_nm, params.span_nm, params.resolution_nm, params.sampling_points, params.analysis
            )
        )
        if args.no_sweep:
            print("Reading trace (no new sweep)...")
        else:
            print("Single sweep (SGL), then WDATA? / LDATA? ...")

        wdata, ldata = ando_term.collect_wdata_ldata(ando, do_sweep=not args.no_sweep)
        ok_trace, det_lines = ando_term.detect_wdata_ldata(
            ando, wdata, ldata, recipe_sampling=int(params.sampling_points)
        )
        for line in det_lines:
            print(line)
        ando_term.print_wdata_ldata(
            wdata, ldata, args.full, header="--- WDATA (nm) / LDATA (dBm) ---"
        )

        if args.strict and not ok_trace:
            print("Exit 1 (--strict): data detection failed.")
            return 1

        if args.extras and ando is not None:
            print("\n--- optional queries ---")
            for label, fn in (
                ("PKWL?", getattr(ando, "query_peak_wavelength_nm", None)),
                ("PKLVL?", getattr(ando, "query_peak_level_dbm", None)),
                ("SMSR?", getattr(ando, "query_smsr_db", None)),
            ):
                if callable(fn):
                    try:
                        v = fn()
                        print(f"  {label} {v!r}")
                    except Exception as e:
                        print(f"  {label} (error) {e}")

        return 0
    except Exception as e:
        print("ERROR:", e)
        return 1
    finally:
        if ando is not None:
            try:
                fn = getattr(ando, "disconnect", None)
                if callable(fn):
                    fn()
                    print("Disconnected Ando.")
            except Exception:
                pass


if __name__ == "__main__":
    raise SystemExit(main())
