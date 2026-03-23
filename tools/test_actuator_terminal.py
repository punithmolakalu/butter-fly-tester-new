"""
Terminal check: connect to Arduino actuator, send movea / homea (and optionally moveb / homeb).

Default (no args): COM13 → movea 206 → homea

Run from project root:

  .\\.venv\\Scripts\\python.exe tools\\test_actuator_terminal.py

Full A+B sequence:

  .\\.venv\\Scripts\\python.exe tools\\test_actuator_terminal.py --full --distance 100
"""
from __future__ import annotations

import argparse
import configparser
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from instruments.actuator import (  # noqa: E402
    ACTUATOR_DEFAULT_MANUAL_DISTANCE_MM,
    ActuatorConnection,
)


def _default_port() -> str:
    """Prefer saved_connections.ini, then instrument_config, else COM13."""
    port = ""
    saved = ROOT / "instruments" / "saved_connections.ini"
    if saved.exists():
        cfg = configparser.ConfigParser()
        cfg.read(saved)
        if cfg.has_section("saved"):
            port = (cfg["saved"].get("actuator_port") or "").strip()
    if not port:
        ini = ROOT / "instruments" / "instrument_config.ini"
        if ini.exists():
            cfg = configparser.ConfigParser()
            cfg.read(ini)
            if cfg.has_section("Actuators"):
                port = (cfg.get("Actuators", "port", fallback="") or "").strip()
            if not port and cfg.has_section("Connection"):
                port = (cfg.get("Connection", "actuator_port", fallback="") or "").strip()
    return port or "COM13"


def main() -> int:
    p = argparse.ArgumentParser(description="Actuator movea/homea (optional full A+B) over serial")
    p.add_argument(
        "--port",
        default=_default_port(),
        help="COM port (default: saved config or COM13)",
    )
    p.add_argument(
        "--distance",
        type=float,
        default=float(ACTUATOR_DEFAULT_MANUAL_DISTANCE_MM),
        help="mm for move_a (and move_b if --full); default matches Manual Control quick move",
    )
    p.add_argument("--pause", type=float, default=3.0, help="seconds after each command (default 3)")
    p.add_argument(
        "--full",
        action="store_true",
        help="After A: also move_b and home_b with same --distance",
    )
    args = p.parse_args()
    if not args.port:
        print("Error: no COM port.")
        return 1

    dist = args.distance
    if dist <= 0:
        print("Error: --distance must be > 0")
        return 1

    act = ActuatorConnection(port=args.port.strip())
    print("Connecting to", args.port, "@", act.baudrate, "baud...")
    if not act.connect():
        print("Connect failed.")
        return 1
    print("Connected.\n")

    def step(name: str, fn) -> None:
        print(">>>", name)
        fn()
        time.sleep(args.pause)

    try:
        step("Move A {:.4g} mm (movea ...)".format(dist), lambda: act.move_a(dist))
        step("Home A (homea)", act.home_a)
        if args.full:
            step("Move B {:.4g} mm (moveb ...)".format(dist), lambda: act.move_b(dist))
            step("Home B (homeb)", act.home_b)
        print("\nDone.")
    finally:
        act.disconnect()
        print("Disconnected.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
