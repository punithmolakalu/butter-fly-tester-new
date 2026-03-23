#!/usr/bin/env python3
"""
Ando AQ6317B — interactive manual terminal (same engine as ando_commands_check --manual).

How results are shown
---------------------
• **Normal SCPI queries** (*IDN?, CTRWL?, SPAN?, SWEEP?, ANA?, ANAR?, SMSR?, …) — the reply is
  printed under "Response:" as plain text from the instrument (driver flushes the read buffer
  before each query to avoid stale *IDN? lines).

• **PKWL? / PKLVL?** — On many AQ6317B units these return the **same comma-separated analysis line**
  as **ANA?** (not a single number). The terminal prints a **hint** when it sees five fields; peak
  wavelength is usually the **2nd** value (nm).

• **Trace data** — type **WDATA?**, **LDATA?**, **WDATB?**, **LDATB?**, **WDATC?**, **LDATC?**
  (or range forms like **WDATA R1-R100?**). The driver uses **read_trace_data()**, not a raw
  short query, so you see **how many points** and a **preview of the first values** (large/binary
  traces cannot be shown as one line).

• **Writes** — prefix with **w** (e.g. **w REMOTE**, **w SGL**, **w WRTA**, **w PKSR**). No
  response body; confirms "OK (write sent)".

• **Session** — **help** (troubleshooting), **remote** (force REMOTE), **doc** (path to
  Ando_Commands.md), **q** (quit).

Typical analysis sequence (after a sweep)
-----------------------------------------
  w SGL          start sweep — wait until finished
  w WRTA         trace A write
  w PKSR         peak search
  ANAR?   or   ANA?     analysis result strings

CLI (all arguments are passed through to ando_commands_check)
-------------------------------------------------------------
  python scripts/ando_manual_terminal.py --ando GPIB0::5::INSTR
  python scripts/ando_manual_terminal.py --ando 5
  python scripts/ando_manual_terminal.py --ando GPIB0::5::INSTR --timeout 30

Equivalent to:
  python scripts/ando_commands_check.py --manual --ando …
"""
from __future__ import annotations

import os
import sys

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_SCRIPT_DIR)
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

# Same as ando_commands_check --manual / --interactive
if not any(x in ("--manual", "-m", "--interactive", "-i") for x in sys.argv[1:]):
    sys.argv.insert(1, "--manual")

import ando_commands_check as _chk  # noqa: E402


def _print_banner() -> None:
    """Short on-screen reminder of how responses are formatted (see module docstring for full detail)."""
    if os.environ.get("BF_ANDO_MANUAL_BANNER", "1").strip() in ("0", "false", "no"):
        return
    sep = "—" * 58
    print(sep)
    print("Ando manual terminal — how results appear")
    print("  • Queries (*IDN?, CTRWL?, ANAR?, …)  → full text under \"Response:\"")
    print("  • PKWL? / PKLVL?                    → often full ANA-style line; hint printed if 5 fields")
    print("  • WDATA? / LDATA? / WDATB? …        → point count + first values (trace read)")
    print("  • w REMOTE | w SGL | w WRTA | w PKSR  → write only; then use ANAR? / ANA?")
    print("  • help | remote | doc | q")
    print(sep)
    print()


def main() -> int:
    _print_banner()
    return int(_chk.main())


if __name__ == "__main__":
    raise SystemExit(main())
