"""
Terminal test for wavemeter: connect over GPIB using commands from instrument_commands/Wavemeter_Commands.md.

Commands used: D1 (terminator NL), K0 (wavelength mode), W0/W1 (range), E (single measurement), then read result.

Usage:
  python test_wavemeter_connection.py [GPIB_ADDRESS]
  python test_wavemeter_connection.py --interactive [GPIB_ADDRESS]

Examples:
  python test_wavemeter_connection.py           -> connect to GPIB1::2::INSTR, run check, exit
  python test_wavemeter_connection.py 3         -> use GPIB0::3::INSTR
  python test_wavemeter_connection.py --interactive  -> prompt for commands (K0, E, W0, WL?, etc.)
"""
from __future__ import print_function

import sys
import time

try:
    import pyvisa
except ImportError:
    print("PyVISA is not installed. Install with: pip install pyvisa pyvisa-py")
    sys.exit(1)


def main():
    args = [a for a in sys.argv[1:] if a and not a.startswith("-")]
    interactive = "--interactive" in sys.argv or "-i" in sys.argv

    # GPIB address: number (e.g. 1) or full resource (e.g. GPIB1::2::INSTR). Default: wavemeter at GPIB1::2::INSTR
    if args:
        addr = args[0].strip()
    else:
        addr = "GPIB1::2::INSTR"
    if addr.isdigit():
        resource = "GPIB0::{}::INSTR".format(addr)
    else:
        resource = addr

    print("Connecting to wavemeter: {}".format(resource))
    rm = pyvisa.ResourceManager()
    try:
        inst = rm.open_resource(resource)
    except Exception as e:
        print("Failed to open resource: {}".format(e))
        sys.exit(1)

    inst.write_termination = "\n"
    inst.read_termination = "\n"
    inst.timeout = 5000

    try:
        # Use commands from Wavemeter_Commands.md: D=terminator, K=mode, W=range, E=single measurement
        inst.write("D1")   # Terminator: NL (match host)
        time.sleep(0.05)
        inst.write("K0")   # K0: Wavelength measurement
        time.sleep(0.05)
        inst.write("W1")   # W0: 480-1000 nm (use W1 for 1000-1650 nm)
        time.sleep(0.05)
        inst.write("C")    # C: Reset / clear data
        time.sleep(0.05)
        inst.write("E")    # E: SINGLE measurement
        time.sleep(0.3)
        # Read result (device may return value after E, or use WL? if supported)
        try:
            wl = inst.read().strip()
        except Exception:
            try:
                wl = inst.query("WL?").strip()
            except Exception:
                wl = "(read failed)"
        print("Result: {} nm".format(wl))

        if interactive:
            print("\nInteractive mode. Commands from Wavemeter_Commands.md: K0, K1, E, W0, W1, D1, RE1, etc. Type quit to exit.\n")
            while True:
                try:
                    cmd = input("wavemeter> ").strip()
                except EOFError:
                    break
                if not cmd:
                    continue
                if cmd.upper() in ("QUIT", "EXIT", "Q"):
                    break
                try:
                    if "?" in cmd:
                        print(inst.query(cmd).strip())
                    else:
                        inst.write(cmd)
                        print("OK")
                except Exception as e:
                    print("Error: {}".format(e))
        else:
            print("\n(Use --interactive to send more commands from the terminal.)")

    finally:
        try:
            inst.write("LOCAL")  # Return to local if supported; harmless if not
        except Exception:
            pass
        try:
            inst.close()
        except Exception:
            pass
        try:
            rm.close()
        except Exception:
            pass

    print("Done.")


if __name__ == "__main__":
    main()
