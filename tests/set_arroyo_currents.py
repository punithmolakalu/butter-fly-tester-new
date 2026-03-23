"""
Terminal script: connect to Arroyo on a COM port and set Set Current and Max Current (mA).
Run from project root:
  python -m tests.set_arroyo_currents
  python -m tests.set_arroyo_currents COM12
  python -m tests.set_arroyo_currents COM12 250 250
  python tests/set_arroyo_currents.py COM12 250 250
"""
import sys
import os

# Project root (parent of tests/)
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)

from instruments.connection import ArroyoConnection


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else "COM12"
    set_current_mA = float(sys.argv[2]) if len(sys.argv) > 2 else 250.0
    max_current_mA = float(sys.argv[3]) if len(sys.argv) > 3 else 250.0

    print(f"Arroyo: connecting to {port}...")
    arroyo = ArroyoConnection(port=port)
    if not arroyo.connect():
        print("Failed to connect.")
        return 1
    print("Connected.")

    print(f"Setting Set Current to {set_current_mA} mA (LAS:LDI)...")
    ok1 = arroyo.laser_set_current(set_current_mA)
    print("  OK" if ok1 else "  FAILED")

    print(f"Setting Max Current to {max_current_mA} mA (LAS:LIM:LDI)...")
    ok2 = arroyo.laser_set_current_limit(max_current_mA)
    print("  OK" if ok2 else "  FAILED")

    arroyo.disconnect()
    print("Disconnected.")
    return 0 if (ok1 and ok2) else 1


if __name__ == "__main__":
    sys.exit(main())
