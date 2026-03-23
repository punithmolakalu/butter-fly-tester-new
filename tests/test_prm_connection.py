"""
Terminal test for PRM (KDC101/Kinesis): scan, connect, read position, disconnect.
Usage: python test_prm_connection.py [SERIAL]
       python test_prm_connection.py   -> auto-detect first device and connect
"""
from __future__ import print_function

import sys

# Run from project root so instruments package is found
sys.path.insert(0, ".")

from instruments.prm import (
    KINESIS_AVAILABLE,
    _KINESIS_LOAD_ERROR,
    scan_prm_serial_numbers,
    get_prm_scan_status,
    PRMConnection,
)

def main():
    print("PRM (Kinesis) connection test")
    print("-" * 40)
    if not KINESIS_AVAILABLE:
        print("FAIL: Kinesis not available.")
        if _KINESIS_LOAD_ERROR:
            print("Error:", _KINESIS_LOAD_ERROR)
        print("Install: Thorlabs Kinesis + pip install pythonnet")
        sys.exit(1)
    print("Kinesis: OK")

    serials = scan_prm_serial_numbers()
    if not serials:
        ok, msg = get_prm_scan_status()
        print("Scan: No devices found.")
        print("Message:", msg)
        sys.exit(1)
    print("Scan: Found serials:", serials)

    serial = (sys.argv[1].strip() if len(sys.argv) > 1 else None) or serials[0]
    if serial not in serials:
        print("Serial", serial, "not in list. Using first:", serials[0])
        serial = serials[0]
    print("Connecting to:", serial)

    conn = PRMConnection(serial)
    try:
        conn.connect()
        print("Connect: OK")
        pos = conn.get_position()
        print("Position: {:.3f} deg".format(pos) if pos is not None else "Position: (read failed)")
    except Exception as e:
        print("Connect FAIL:", e)
        err = str(e)
        if "not connected" in err.lower() or "VerifyDeviceConnected" in err:
            print("Tip: Check USB cable, close Thorlabs Kinesis GUI if open, then try again.")
        sys.exit(1)
    finally:
        conn.disconnect()
        print("Disconnected.")
    print("Done.")


if __name__ == "__main__":
    main()
