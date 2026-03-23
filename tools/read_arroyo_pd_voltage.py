"""Arroyo terminal helper: read laser voltage / PD current, or run a full set+enable+read sequence."""
from __future__ import annotations

import argparse
import configparser
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from instruments.arroyo import ArroyoConnection  # noqa: E402


def _default_port() -> str:
    saved = ROOT / "instruments" / "saved_connections.ini"
    port = "COM5"
    if saved.exists():
        cfg = configparser.ConfigParser()
        cfg.read(saved)
        if cfg.has_section("saved"):
            port = (cfg["saved"].get("arroyo_port") or port).strip()
    return port


def _print_reads(a: ArroyoConnection, title: str) -> None:
    print(f"\n--- {title} ---")
    for cmd in ("LAS:SET:LDI?", "LAS:LDI?", "LAS:LDV?", "LAS:MDI?", "LAS:MDP?", "LAS:OUT?", "TEC:SET:T?", "TEC:T?", "TEC:OUT?"):
        r = a.query(cmd)
        print(cmd, "->", repr(r))
    mdi = getattr(a, "laser_read_monitor_diode_current", None)
    if callable(mdi):
        print("laser_read_monitor_diode_current():", mdi())
    print("laser_read_voltage():", a.laser_read_voltage())
    err = a.get_error()
    if err is not None and str(err).strip():
        print("ERR?", repr(err))


def run_sequence(
    a: ArroyoConnection,
    current_ma: float,
    temp_c: float,
    tec_wait_s: float,
    laser_wait_s: float,
    shutdown: bool,
) -> None:
    """
    Example order (as requested): set laser current setpoint, set TEC temp, TEC on, laser on, read.
    Ensure laser current and temperature limits on the instrument are safe for your diode.
    """
    print("\n=== Sequence: set current, set temp, TEC on, laser on, read ===")
    ok = a.laser_set_current(current_ma)
    print(f"laser_set_current({current_ma}) ->", "OK" if ok else "FAILED")
    time.sleep(0.2)

    ok = a.set_temp(temp_c)
    print(f"set_temp({temp_c}) ->", "OK" if ok else "FAILED")
    time.sleep(0.2)

    ok = a.set_output(True)
    print("set_output(True) [TEC ON] ->", "OK" if ok else "FAILED")
    if tec_wait_s > 0:
        print(f"Waiting {tec_wait_s:.1f} s after TEC on...")
        time.sleep(tec_wait_s)

    ok = a.laser_set_output(True)
    print("laser_set_output(True) [LASER ON] ->", "OK" if ok else "FAILED")
    if laser_wait_s > 0:
        print(f"Waiting {laser_wait_s:.1f} s after laser on...")
        time.sleep(laser_wait_s)

    _print_reads(a, "After sequence")

    if shutdown:
        print("\n=== Shutdown: laser off, TEC off ===")
        a.laser_set_output(False)
        time.sleep(0.15)
        a.set_output(False)
        time.sleep(0.15)
        _print_reads(a, "After shutdown")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("port", nargs="?", default=None, help="COM port (default: saved_connections.ini)")
    p.add_argument(
        "--sequence",
        action="store_true",
        help="Set laser current, TEC setpoint, enable TEC then laser, then read (real hardware!)",
    )
    p.add_argument("--current", type=float, default=400.0, help="Laser current setpoint (e.g. mA, instrument units)")
    p.add_argument("--temp", type=float, default=25.0, help="TEC temperature setpoint (°C)")
    p.add_argument("--tec-wait", type=float, default=5.0, help="Seconds to wait after TEC on before laser on")
    p.add_argument("--laser-wait", type=float, default=3.0, help="Seconds to wait after laser on before read")
    p.add_argument(
        "--shutdown",
        action="store_true",
        help="After read, turn laser output off then TEC output off",
    )
    args = p.parse_args()

    port = (args.port or _default_port()).strip()
    print("Arroyo port:", port)
    a = ArroyoConnection(port=port)
    if not a.connect():
        print("ERROR: Could not connect to Arroyo on", port)
        return 1

    try:
        print("IDN:", a.identify())
        if args.sequence:
            run_sequence(
                a,
                current_ma=args.current,
                temp_c=args.temp,
                tec_wait_s=args.tec_wait,
                laser_wait_s=args.laser_wait,
                shutdown=args.shutdown,
            )
        else:
            _print_reads(a, "Read only")
    finally:
        a.disconnect()
    print("\nDone.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
