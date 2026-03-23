#!/usr/bin/env python3
"""
Terminal test: finish one Ando sweep, then read analysis results (ANA? / ANAR? and parsed dicts).

Use this to verify on the bench that analysis completes and GP-IB readback matches the manual
(DFB: PK WL, PK LVL, SMSR, MODE OFFSET; LED: MEAN WL, TOTAL POWER, PK WL, PK LVL, SPEC WD).

  python scripts/ando_analysis_result_terminal_test.py --ando GPIB0::5::INSTR --arroyo COM5

Shared helpers: scripts/ando_wdata_ldata_terminal_common.py
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from types import SimpleNamespace

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

import ando_wdata_ldata_terminal_common as ando_term  # noqa: E402

from operations.arroyo_laser_helpers import apply_arroyo_recipe_and_laser_on_for_spectrum  # noqa: E402
from operations.spectrum.spectrum_process import SpectrumProcess, SpectrumProcessParameters  # noqa: E402


def _print_line(title: str, value: object) -> None:
    print("  {:16} {}".format(title + ":", value))


def print_analysis_results(ando: object, analysis_name: str) -> None:
    """After sweep idle: WRTA, peak search, then ANA? / ANAR? and driver parsers."""
    print("\n=== Analysis readback (instrument must be idle; peak search run) ===")
    tw = getattr(ando, "trace_write_a", None)
    if callable(tw):
        tw()
    time.sleep(0.1)
    ps = getattr(ando, "peak_search", None)
    if callable(ps):
        ps()
        time.sleep(0.12)
    else:
        print("  (no peak_search on driver — raw queries may still work)")

    q = getattr(ando, "query", None)
    if callable(q):
        for cmd in ("ANA?", "ANAR?"):
            try:
                raw = q(cmd)
                print("  {:16} {}".format(cmd + " raw", repr(raw)))
            except Exception as ex:
                print("  {:16} ERROR {}".format(cmd, ex))

    qana = getattr(ando, "query_analysis_ana", None)
    if callable(qana):
        try:
            d = qana()
            print("  query_analysis_ana():")
            if isinstance(d, dict):
                for k, v in sorted(d.items()):
                    print("    {:20} {}".format(str(k) + ":", v))
            else:
                print("    ", d)
        except Exception as ex:
            print("  query_analysis_ana ERROR:", ex)

    qanar = getattr(ando, "query_analysis_anar", None)
    if callable(qanar):
        try:
            d = qanar(analysis_name)
            print('  query_analysis_anar({!r}):'.format(analysis_name))
            if isinstance(d, dict):
                for k, v in sorted(d.items()):
                    print("    {:20} {}".format(str(k) + ":", v))
            else:
                print("    ", d)
        except Exception as ex:
            print("  query_analysis_anar ERROR:", ex)

    print("\n  --- Scalar queries (if implemented) ---")
    for name, fn_name in (
        ("PKWL nm", "query_peak_wavelength_nm"),
        ("PKLV dBm", "query_peak_level_dbm"),
        ("SPWD nm", "query_spectral_width_nm"),
        ("SMSR dB", "query_smsr_db"),
    ):
        fn = getattr(ando, fn_name, None)
        if callable(fn):
            try:
                _print_line(name, fn())
            except Exception as ex:
                _print_line(name, "ERROR " + str(ex))


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Ando: apply recipe, one sweep, then print ANA?/ANAR? and parsed analysis results."
    )
    ap.add_argument(
        "--recipe",
        default=os.path.join(_ROOT, "scripts", "sample_ando_spectrum_terminal_rcp.json"),
        help="JSON with OPERATIONS.SPECTRUM (Analysis, CenterWL, …)",
    )
    ap.add_argument("--ando", default="", help="GPIB e.g. GPIB0::5::INSTR or 5")
    ap.add_argument("--arroyo", default="COM5", help="Arroyo COM port (for laser on)")
    ap.add_argument(
        "--analysis",
        default="",
        help="Override recipe OPERATIONS.SPECTRUM Analysis (e.g. DFB-LD, LED)",
    )
    args = ap.parse_args()

    recipe = ando_term.load_recipe(args.recipe)
    params = SpectrumProcessParameters.from_recipe(recipe)
    analysis = (args.analysis or "").strip() or params.analysis

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

        # Optional: re-select analysis if user overrode string (driver uses recipe in _apply; we only affect ANAR parse hint)
        if args.analysis.strip():
            print("4) Analysis mode (override):", analysis)
        else:
            print("4) Analysis mode (from recipe):", analysis)

        print(
            "5) Single sweep — CTR={:.3f} nm span={:.3f} nm — wait for idle, then analysis queries.".format(
                params.center_nm, params.span_nm
            )
        )
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
        time.sleep(0.35)

        sweep_st = getattr(ando, "query_sweep_status", None)
        if callable(sweep_st):
            _print_line("SWEEP? / status", sweep_st())

        print_analysis_results(ando, analysis)
        print("\nDone.")
        return 0
    except Exception as e:
        print("ERROR:", e)
        import traceback

        traceback.print_exc()
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
