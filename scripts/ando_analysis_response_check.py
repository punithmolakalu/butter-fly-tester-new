#!/usr/bin/env python3
"""
Quick check: does the Ando respond to analysis-related GPIB queries?

Prints each command as OK (with short preview) or FAIL / no response.
Use after a sweep (--sweep) so ANA? / ANAR? usually return real data; without sweep they may be empty.

  python scripts/ando_analysis_response_check.py --ando GPIB0::5::INSTR
  python scripts/ando_analysis_response_check.py --ando GPIB0::5::INSTR --sweep

Exit code: 0 if Ando connects and *IDN? responds; 1 on connect failure; 2 if any listed query errors (optional --strict).
"""
from __future__ import annotations

import argparse
import os
import sys
from typing import Any

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

import ando_wdata_ldata_terminal_common as ando_term  # noqa: E402


def _preview(s: object, max_len: int = 72) -> str:
    t = repr(s) if s is not None else "None"
    if len(t) > max_len:
        return t[: max_len - 3] + "..."
    return t


def run_queries(ando: Any, *, after_sweep: bool) -> tuple[bool, list[tuple[str, bool, str]]]:
    """
    Returns (all_ok, [(cmd, ok, detail), ...]).
    """
    if after_sweep:
        print("Running single sweep + wait + WRTA + peak search (for meaningful ANA?/ANAR?)...")
        ando.single_sweep()
        wait = getattr(ando, "wait_sweep_done", None)
        if callable(wait):
            wait(timeout_s=180.0)
        else:
            import time

            t0 = time.time()
            while __import__("time").time() - t0 < 180.0:
                if getattr(ando, "is_sweep_done", lambda: True)():
                    break
                __import__("time").sleep(0.2)
        import time

        time.sleep(0.25)
        tw = getattr(ando, "trace_write_a", None)
        if callable(tw):
            tw()
        time.sleep(0.1)
        ps = getattr(ando, "peak_search", None)
        if callable(ps):
            ps()
            time.sleep(0.12)

    q = getattr(ando, "query", None)
    if not callable(q):
        print("FAIL: instrument has no query()")
        return False, []

    commands = (
        "*IDN?",
        "SWEEP?",
        "ANA?",
        "ANAR?",
        "PKWL?",
        "PKLVL?",
        "SPWD?",
        "SMSR?",
    )
    rows: list[tuple[str, bool, str]] = []
    all_ok = True
    for cmd in commands:
        try:
            raw = q(cmd)
            ok = raw is not None and str(raw).strip() != ""
            detail = _preview(raw) if ok else "(empty or None)"
            if not ok:
                all_ok = False
            rows.append((cmd, ok, detail))
        except Exception as ex:
            all_ok = False
            rows.append((cmd, False, "ERROR: " + str(ex)))

    # Driver-level parsers (optional)
    for name, fn_name in (
        ("query_analysis_ana()", "query_analysis_ana"),
        ("query_analysis_anar('')", "query_analysis_anar"),
    ):
        fn = getattr(ando, fn_name, None)
        if not callable(fn):
            rows.append((name, False, "(not on driver)"))
            all_ok = False
            continue
        try:
            if fn_name == "query_analysis_anar":
                d = fn("")
            else:
                d = fn()
            ok = d is not None and (not isinstance(d, dict) or len(d) > 0)
            detail = _preview(d)
            if not ok:
                all_ok = False
            rows.append((name, ok, detail))
        except Exception as ex:
            all_ok = False
            rows.append((name, False, "ERROR: " + str(ex)))

    return all_ok, rows


def main() -> int:
    ap = argparse.ArgumentParser(description="Check whether Ando responds to analysis GPIB queries.")
    ap.add_argument("--ando", default="", help="GPIB address e.g. GPIB0::5::INSTR")
    ap.add_argument(
        "--sweep",
        action="store_true",
        help="Run one sweep + peak search before queries (recommended for ANA?/ANAR?)",
    )
    ap.add_argument(
        "--strict",
        action="store_true",
        help="Exit 2 if any query fails (default: exit 0 after connect+*IDN? ok)",
    )
    args = ap.parse_args()

    ando = None
    try:
        print("Connecting Ando...")
        ando = ando_term.connect_ando(args.ando.strip())
        print("OK:", getattr(ando, "gpib_address", ""))
    except Exception as e:
        print("FAIL connect:", e)
        return 1

    all_ok, rows = run_queries(ando, after_sweep=args.sweep)

    print("\n--- Response check ---")
    print(f"{'Command':<26} {'Status':<10} Detail")
    print("-" * 90)
    for cmd, ok, detail in rows:
        st = "OK" if ok else "FAIL"
        print(f"{cmd:<26} {st:<10} {detail}")

    idn_ok = any(c == "*IDN?" and ok for c, ok, _ in rows)
    if not idn_ok:
        print("\n*IDN? did not respond — check GPIB / address.")
        rc = 1
    elif args.strict and not all_ok:
        print("\nStrict: one or more queries failed.")
        rc = 2
    else:
        print("\nSummary: Ando is responding." + (" (run with --sweep for fuller ANA?/ANAR?)" if not args.sweep else ""))
        rc = 0

    try:
        fn = getattr(ando, "disconnect", None)
        if callable(fn):
            fn()
            print("Disconnected.")
    except Exception:
        pass
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
