#!/usr/bin/env python3
"""
Check Ando AQ6317B SCPI/GPIB responses: connect, run queries, print OK/FAIL per line.

Uses scripts/ando_wdata_ldata_terminal_common.py to connect.

**Command reference (complete list in repo):**
  instrument_commands/Ando_Commands.md

Parse all concrete query strings from that markdown with --from-md (backtick tokens ending
in ? with no {placeholders}).

Examples:
  # Type commands in the terminal and read plain-text responses (no batch file needed):
  python scripts/ando_commands_check.py --ando GPIB0::5::INSTR --manual
  python scripts/ando_manual_terminal.py --ando 5

  python scripts/ando_commands_check.py --ando GPIB0::5::INSTR
  python scripts/ando_commands_check.py --ando 5 --from-md --sweep
  python scripts/ando_commands_check.py --ando 5 --interactive
  python scripts/ando_commands_check.py --list-md-queries
  python scripts/ando_commands_check.py --ando GPIB0::5::INSTR --save-report ando_query_report.tsv

Exit codes:
  0 — connected and *IDN? OK (and all queries OK if --strict)
  1 — connect failure or *IDN? missing/failed
  2 — --strict and at least one query failed
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from typing import Any

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ANDO_COMMANDS_MD = os.path.join(_ROOT, "instrument_commands", "Ando_Commands.md")

if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
if _SCRIPT_DIR not in sys.path:
    sys.path.insert(0, _SCRIPT_DIR)

import ando_wdata_ldata_terminal_common as ando_term  # noqa: E402


def _connect_ando_cli(args: Any) -> Any:
    """Connect Ando using --ando and optional --timeout (seconds, for slow GPIB)."""
    ts = getattr(args, "timeout", None)
    return ando_term.connect_ando((args.ando or "").strip(), timeout_s=ts)


# Short default batch (safe subset). Full inventory: --from-md (see Ando_Commands.md).
DEFAULT_QUERIES: tuple[str, ...] = (
    "*IDN?",
    "*OPC?",
    "SWEEP?",
    "CTRWL?",
    "SPAN?",
    "RESOLN?",
    "REFL?",
    "LSCL?",
    "SMPL?",
    "DTNUM?",
    "SMSR?",
    "PKWL?",
    "PKLVL?",
    "SPWD?",
    "ANA?",
    "ANAR?",
)

# Match markdown table rows: | `COMMAND` | Description | ...
_RE_TABLE_CMD = re.compile(
    r"^\|\s*`([^`]+)`\s*\|\s*([^|]+?)\s*\|(?:\s*([^|]*)\s*\|)?(?:\s*([^|]*)\s*\|)?\s*$"
)
_RE_BTICK = re.compile(r"`([^`]+)`")
# WDATA?/LDATA? (and range forms) return large/binary data — not suitable for simple query().
_RE_TRACE_READ = re.compile(
    r"^\s*(WDATA|LDATA|WDATB|LDATB|WDATC|LDATC)(\s+.*)?\?\s*$",
    re.IGNORECASE,
)


def parse_ando_commands_md(md_path: str) -> tuple[list[tuple[str, str]], int]:
    """
    Load Ando_Commands.md and return [(query, description), ...] for every concrete query:
    backtick token ending with '?' and containing no { } placeholders.
    Also counts total backtick tokens scanned for diagnostics.
    """
    if not os.path.isfile(md_path):
        return [], 0
    with open(md_path, encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    seen: set[str] = set()
    ordered: list[tuple[str, str]] = []
    tick_total = 0

    def _add(cmd: str, desc: str) -> None:
        c = cmd.strip()
        if not c.endswith("?"):
            return
        if len(c) < 2 or c == "?":
            return  # ignore notes like `` `?` `` in prose
        if "{" in c or "}" in c:
            return
        if c in seen:
            return
        seen.add(c)
        ordered.append((c, (desc or "").strip()))

    for line in lines:
        m = _RE_TABLE_CMD.match(line.rstrip())
        if m:
            cmd, desc = m.group(1), m.group(2)
            _add(cmd, desc)
            continue
        for bm in _RE_BTICK.finditer(line):
            tick_total += 1
            _add(bm.group(1), "")

    return ordered, tick_total


def list_md_queries(md_path: str) -> int:
    """Print queries parsed from Ando_Commands.md (no hardware)."""
    rows, ticks = parse_ando_commands_md(md_path)
    print("Reference:", md_path)
    print("Backtick tokens scanned (approx.):", ticks)
    print("Unique concrete queries (no {{}} placeholders):", len(rows))
    print()
    for cmd, desc in rows:
        if desc:
            print(f"{cmd}\t# {desc}")
        else:
            print(cmd)
    return 0 if rows else 1


def _preview(s: object, max_len: int = 96) -> str:
    t = repr(s) if s is not None else "None"
    if len(t) > max_len:
        return t[: max_len - 3] + "..."
    return t


def _format_terminal_response(raw: object, *, max_chars: int = 12000) -> str:
    """Plain text for interactive terminal (not Python repr)."""
    if raw is None:
        return "(no response / None)"
    s = str(raw)
    if len(s) > max_chars:
        return s[:max_chars] + "\n... [truncated, total length " + str(len(s)) + " chars]"
    return s


def _maybe_print_composite_peak_hint(cmd_line: str, raw: object) -> None:
    """
    PKWL? / PKLVL? often return the same 5-value ANA-style line on AQ6317B (not one number).
    Helps manual-terminal users read peak λ vs width vs SMSR.
    """
    if not isinstance(raw, str) or "," not in raw:
        return
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if len(parts) < 5:
        return
    cu = cmd_line.strip().upper()
    if not (
        cu.startswith("PKWL")
        or cu.startswith("PKLV")
        or cu.startswith("SPWD")
        or cu.startswith("SMSR")
    ):
        return
    print(
        "\nNote: This firmware returns a full analysis line (same style as ANA?), not one number."
        "\n  Typical DFB-style fields:  [0] width (nm)  [1] peak λ (nm)  [2] peak level (dBm)  [3] …  [4] SMSR (dB)"
        f"\n  → Peak wavelength ≈ {parts[1]} nm    Peak level ≈ {parts[2]} dBm    SMSR ≈ {parts[4]} dB"
    )


def _response_looks_like_idn(s: object) -> bool:
    """True if the string matches a typical *IDN? reply (stale buffer gave wrong read for ANAR? etc.)."""
    t = str(s or "").strip()
    if len(t) < 12:
        return False
    u = t.upper()
    return "ANDO" in u and "AQ6317" in u and "," in t


def _load_commands_from_file(path: str) -> list[str]:
    out: list[str] = []
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            # Allow "CMD # comment"
            if "#" in s:
                s = s.split("#", 1)[0].strip()
            if s:
                out.append(s)
    return out


def _optional_sweep(ando: Any) -> None:
    """Single sweep + wait + trace A write (helps DTNUM/SMPL/ANA? etc.)."""
    print("Running single sweep + wait + WRTA...")
    ando.single_sweep()
    wait = getattr(ando, "wait_sweep_done", None)
    if callable(wait):
        wait(timeout_s=180.0)
    else:
        t0 = time.time()
        while time.time() - t0 < 180.0:
            if getattr(ando, "is_sweep_done", lambda: True)():
                break
            time.sleep(0.2)
    time.sleep(0.25)
    tw = getattr(ando, "trace_write_a", None)
    if callable(tw):
        tw()
    time.sleep(0.15)


def run_queries(
    ando: Any, commands: list[str]
) -> tuple[bool, list[tuple[str, bool, str]]]:
    qfn = getattr(ando, "query", None)
    if not callable(qfn):
        return False, [("(no query())", False, "instrument has no query()")]

    rows: list[tuple[str, bool, str]] = []
    all_ok = True
    for cmd in commands:
        try:
            raw = qfn(cmd)
            ok = raw is not None and str(raw).strip() != ""
            detail = _preview(raw) if ok else "(empty or None)"
            if not ok:
                all_ok = False
            rows.append((cmd, ok, detail))
        except Exception as ex:
            all_ok = False
            rows.append((cmd, False, "ERROR: " + str(ex)))
    return all_ok, rows


def _run_interactive(ando: Any) -> None:
    """Type a query (…?) or 'w <line>' to write_command; q quits."""
    print("Manual mode — type a SCPI query and press Enter (response printed below).")
    print("  Examples:  *IDN?   CTRWL?   SPAN?")
    print("  WDATA? / LDATA?   full trace read (uses driver — not plain query())")
    print("  remote            send REMOTE (if front panel took over / no replies)")
    print("  w REMOTE          same as write (no ?)")
    print("  help              troubleshooting if you get no response")
    print("  doc               show path to Ando_Commands.md")
    print("  q                 quit")
    qfn = getattr(ando, "query", None)
    wfn = getattr(ando, "write_command", None)
    while True:
        try:
            line = input("Ando> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line or line.lower() in ("q", "quit", "exit"):
            break
        if line.lower() == "doc":
            print(ANDO_COMMANDS_MD)
            continue
        if line.lower() == "help":
            print(
                "No response usually means: wrong GPIB address, USB–GPIB unplugged, OSA off,\n"
                "or the unit is in LOCAL — press REMOTE on the OSA or type:  remote\n"
                "Try first:  *IDN?     Retry with:  python ... --ando GPIB0::5::INSTR --timeout 30 --manual"
            )
            continue
        if line.lower() == "remote":
            rm = getattr(ando, "set_remote_mode", None)
            if callable(rm) and rm():
                print("REMOTE sent OK.")
            elif callable(wfn) and wfn("REMOTE"):
                print("REMOTE sent OK.")
            else:
                print("Could not send REMOTE.")
            continue
        low = line.lower()
        if low.startswith("w ") or low.startswith("write "):
            rest = line.split(None, 1)[1].strip() if len(line.split(None, 1)) > 1 else ""
            if not rest:
                print("(empty)")
                continue
            if not callable(wfn):
                print("No write_command() on driver.")
                continue
            try:
                wfn(rest)
                print("OK (write sent)")
            except Exception as ex:
                print("ERROR:", ex)
            continue
        # Trace wavelength/level data: must use read_trace_data() — simple query() can mis-read (e.g. *IDN? text).
        if _RE_TRACE_READ.match(line):
            rtd = getattr(ando, "read_trace_data", None)
            if not callable(rtd):
                print("No read_trace_data() on driver.")
                print()
                continue
            print("Reading trace (may take a while; driver uses WDATA/LDATA + binary/ASCII paths)…")
            try:
                raw_vals = rtd(line.strip())
            except Exception as ex:
                print("ERROR:", ex)
                print()
                continue
            vals: list[float]
            if isinstance(raw_vals, (list, tuple)):
                vals = [float(x) for x in raw_vals]
            else:
                vals = []
            print("Response:")
            print(f"  {len(vals)} data point(s)")
            if vals:
                prev = min(20, len(vals))
                print(f"  first {prev}: {vals[:prev]}")
                if len(vals) > prev:
                    print(f"  … ({len(vals) - prev} more)")
            else:
                print(
                    "  (empty — run a sweep first: e.g. w SGL, wait for sweep done, w WRTA, then WDATA? again)"
                )
            print()
            continue
        if not callable(qfn):
            print("No query()")
            continue
        try:
            raw = qfn(line)
            print("Response:")
            if raw is None or (isinstance(raw, str) and not raw.strip()):
                print(
                    "(no reply — empty or timeout)\n"
                    "  → Check GPIB cable, power, address (NI MAX / Connection tab). "
                    "Type  remote  then  *IDN?   again. Try --timeout 30"
                )
            else:
                print(_format_terminal_response(raw))
                _maybe_print_composite_peak_hint(line, raw)
                lu = line.strip().upper()
                if _response_looks_like_idn(raw) and not lu.startswith("*IDN"):
                    print(
                        "\nThat reply is the instrument identity (*IDN?), not data for this command.\n"
                        "  The driver flushes the buffer and retries once on stale *IDN? reads — try your query again.\n"
                        "  If it repeats:  *IDN?   then  remote   then e.g.  w PKSR   then  PKWL?  or  ANAR?.\n"
                        "  Full analysis path:  w SGL  (wait) →  w WRTA  →  w PKSR  →  PKWL? / ANAR? / ANA?.\n"
                        "  Reconnect USB–GPIB or increase --timeout if needed."
                    )
            print()
        except Exception as ex:
            print("ERROR:", ex)
            print()


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Check Ando GPIB/SCPI queries. Full command list: instrument_commands/Ando_Commands.md"
    )
    ap.add_argument("--ando", default="", help="GPIB address e.g. GPIB0::5::INSTR or primary address digit(s)")
    ap.add_argument(
        "--timeout",
        type=float,
        default=None,
        metavar="SEC",
        help="PyVISA read timeout in seconds (default ~5). Use 20–60 if queries often time out.",
    )
    ap.add_argument(
        "--md-path",
        default=ANDO_COMMANDS_MD,
        help="Path to Ando_Commands.md (default: project instrument_commands/Ando_Commands.md).",
    )
    ap.add_argument(
        "--from-md",
        action="store_true",
        help="Add every concrete query parsed from Ando_Commands.md (see --list-md-queries).",
    )
    ap.add_argument(
        "--list-md-queries",
        action="store_true",
        help="Print all queries extracted from Ando_Commands.md and exit (no instrument).",
    )
    ap.add_argument(
        "--interactive",
        "-i",
        action="store_true",
        help="After connect, type commands in the terminal and read responses (quit: q).",
    )
    ap.add_argument(
        "--manual",
        "-m",
        action="store_true",
        help="Same as --interactive: manual terminal session (no batch command list required).",
    )
    ap.add_argument(
        "--sweep",
        action="store_true",
        help="Before batch queries: run one sweep, wait, WRTA (recommended for trace-dependent queries).",
    )
    ap.add_argument(
        "--file",
        default="",
        help="Text file: one SCPI query per line (# comments allowed).",
    )
    ap.add_argument(
        "--cmd",
        action="append",
        default=[],
        metavar="QUERY",
        help="Extra query (repeatable).",
    )
    ap.add_argument(
        "--no-defaults",
        action="store_true",
        help="Do not use the short built-in default list (use --from-md, --file, and/or --cmd).",
    )
    ap.add_argument(
        "--strict",
        action="store_true",
        help="Exit 2 if any query fails (non-strict still requires *IDN? to pass).",
    )
    ap.add_argument(
        "--save-report",
        default="",
        metavar="PATH",
        help="Write TSV: command, ok, response (after batch run).",
    )
    args = ap.parse_args()

    md_path = os.path.normpath(args.md_path.strip() or ANDO_COMMANDS_MD)
    manual_terminal = bool(args.interactive or args.manual)

    if args.list_md_queries:
        if not os.path.isfile(md_path):
            print("ERROR: markdown not found:", md_path)
            return 1
        return list_md_queries(md_path)

    # Manual terminal: connect, type queries, print plain responses — no --file / defaults required.
    if manual_terminal:
        ando = None
        try:
            print("Connecting Ando...")
            ando = _connect_ando_cli(args)
            print("OK:", getattr(ando, "gpib_address", ""))
            _run_interactive(ando)
        except Exception as e:
            print("FAIL connect:", e)
            return 1
        finally:
            try:
                fn = getattr(ando, "disconnect", None)
                if callable(fn):
                    fn()
                    print("Disconnected.")
            except Exception:
                pass
        return 0

    commands: list[str] = []
    md_descriptions: dict[str, str] = {}

    if not args.no_defaults:
        commands.extend(DEFAULT_QUERIES)

    if args.from_md:
        if not os.path.isfile(md_path):
            print("ERROR: --from-md but file not found:", md_path)
            return 1
        parsed, _n = parse_ando_commands_md(md_path)
        for cmd, desc in parsed:
            md_descriptions[cmd] = desc
        commands.extend([c for c, _ in parsed])

    if args.file.strip():
        path = args.file.strip()
        if not os.path.isfile(path):
            print("ERROR: --file not found:", path)
            return 1
        commands.extend(_load_commands_from_file(path))
    for c in args.cmd:
        if c and str(c).strip():
            commands.append(str(c).strip())

    # De-dupe preserving order (defaults + from-md may overlap)
    seen_cmd: set[str] = set()
    deduped: list[str] = []
    for c in commands:
        if c in seen_cmd:
            continue
        seen_cmd.add(c)
        deduped.append(c)
    commands = deduped

    if not commands:
        print("ERROR: no commands (defaults, --from-md, --file, or --cmd).")
        return 1

    if args.from_md and len(commands) > 80:
        print(
            f"Note: running {len(commands)} queries from markdown (this can take several minutes).\n"
        )

    ando = None
    try:
        print("Connecting Ando...")
        ando = _connect_ando_cli(args)
        print("OK:", getattr(ando, "gpib_address", ""))
    except Exception as e:
        print("FAIL connect:", e)
        return 1

    try:
        if args.sweep:
            _optional_sweep(ando)
        all_ok, rows = run_queries(ando, commands)
    finally:
        try:
            fn = getattr(ando, "disconnect", None)
            if callable(fn):
                fn()
                print("Disconnected.")
        except Exception:
            pass

    print("\n--- Ando command check ---")
    print(f"{'Command':<32} {'Status':<8} Detail")
    print("-" * 108)
    for cmd, ok, detail in rows:
        st = "OK" if ok else "FAIL"
        extra = md_descriptions.get(cmd, "")
        if extra:
            detail = (detail + "  |  " + extra)[:200]
        print(f"{cmd:<32} {st:<8} {detail}")

    if args.save_report.strip():
        rp = args.save_report.strip()
        try:
            with open(rp, "w", encoding="utf-8", newline="") as out:
                out.write("command\tok\tresponse\n")
                for cmd, ok, detail in rows:
                    ok_s = "1" if ok else "0"
                    # TSV: escape tabs in detail
                    d = detail.replace("\t", " ").replace("\r\n", " ").replace("\n", " ")
                    out.write(f"{cmd}\t{ok_s}\t{d}\n")
            print("\nWrote report:", os.path.abspath(rp))
        except OSError as ex:
            print("\nERROR writing report:", ex)

    idn_ok = any(c.strip().upper() == "*IDN?" and ok for c, ok, _ in rows)
    if not idn_ok:
        print("\n*IDN? did not return data — check GPIB address, cable, and REMOTE mode.")
        return 1
    if args.strict and not all_ok:
        print("\nStrict: one or more queries failed.")
        return 2
    print(
        "\nSummary: Ando responded."
        + (" (use --sweep if some trace queries were empty)" if not args.sweep else "")
    )
    print("Full command reference:", md_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
