"""
Test Ando AQ6317B connection over GPIB.
Run from project root:
  python -m tests.test_ando_connection
  python -m tests.test_ando_connection GPIB0::1::INSTR
  python -m tests.test_ando_connection 1
"""
import sys
import os

# Ensure project root is on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    from instruments.connection import (
        PYVISA_AVAILABLE,
        scan_gpib_resources,
        probe_gpib_andos,
        AndoConnection,
    )

    print("=" * 60)
    print("Ando connection test")
    print("=" * 60)

    if not PYVISA_AVAILABLE:
        print("FAIL: PyVISA is not installed. Install with: pip install pyvisa")
        print("(When installed, Scan will list GPIB0::1::INSTR .. GPIB0::30::INSTR if no VISA GPIB list.)")
        return 1

    print("PyVISA: OK")
    print()

    # 1) List GPIB resources (includes defaults if VISA returns empty)
    print("Scanning GPIB resources...")
    resources = scan_gpib_resources()
    if not resources:
        print("No GPIB addresses available (scan returned empty).")
        return 1
    print(f"Found {len(resources)} GPIB address(es):")
    for r in resources[:15]:
        print(f"  {r}")
    if len(resources) > 15:
        print(f"  ... and {len(resources) - 15} more")
    print()

    # 2) Optional: probe with *IDN? to detect responding instruments (Ando)
    print("Probing for responding instruments (*IDN?) on first 10 addresses...")
    try:
        probed = probe_gpib_andos(timeout_ms=1500, addresses=resources[:10])
        if probed:
            print(f"Responding: {len(probed)}")
            for addr, idn in probed:
                is_ando = "Ando" in idn or "AQ6317" in idn or "Yokogawa" in idn
                print(f"  {addr} -> {idn[:60]}{'...' if len(idn) > 60 else ''}  {'[Ando]' if is_ando else ''}")
        else:
            print("No instrument responded to *IDN? (try connecting to GPIB0::1 if Ando is at primary address 1).")
    except Exception as e:
        print(f"Probe error: {e}")
    print()

    # 3) Try connect with AndoConnection
    address = (sys.argv[1] if len(sys.argv) > 1 else None) or "GPIB0::1::INSTR"
    if address.isdigit():
        address = f"GPIB0::{address}::INSTR"
    print(f"Connecting to {address}...")
    try:
        ando = AndoConnection(address=address)
        ok = ando.connect()
        if not ok:
            print("Connection FAILED.")
            return 1
        print("Connection: OK")
        idn = ando.identify()
        if idn:
            print(f"*IDN?: {idn.strip()}")
        ando.disconnect()
        print("Disconnect: OK")
    except ImportError as e:
        print(f"Import error: {e}")
        return 1
    except Exception as e:
        print(f"Error: {e}")
        return 1

    print()
    print("Ando connection test: PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
