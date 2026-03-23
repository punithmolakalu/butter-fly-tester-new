"""
Wavemeter (GPIB)

Uses PyVISA only: ResourceManager() with default backend (NI-VISA on Windows).
See: https://github.com/pyvisa/pyvisa — open_resource('GPIB0::N::INSTR'), write/read.

Commands: instrument_commands/Wavemeter_Commands.md (E = single measure, W0/W1 = range).
"""
from __future__ import annotations

import time
from typing import Optional, Tuple

try:
    import pyvisa  # type: ignore[reportMissingImports]
except ImportError:
    pyvisa = None


class WavemeterInstrument:
    """GPIB instrument session: open, set terminator/timeout, send E then read for wavelength."""

    def __init__(self, resource: str, open_timeout_ms: int = 10000):
        if not resource:
            raise ValueError("GPIB resource required.")
        if not pyvisa:
            raise RuntimeError("Install PyVISA: pip install pyvisa")
        self.resource = resource.strip()
        self._rm = pyvisa.ResourceManager()
        try:
            self._inst = self._rm.open_resource(self.resource, open_timeout=open_timeout_ms)
        except TypeError:
            self._inst = self._rm.open_resource(self.resource)
        self._inst.write_termination = "\n"
        self._inst.read_termination = "\n"
        # Shorter read timeout (2s) so unplug/turn-off is detected quickly and status switches to Disconnected
        self._inst.timeout = 2000
        time.sleep(0.25)
        self._current_range = None

    def _send_range(self, range_str: str) -> None:
        if not getattr(self, "_inst", None):
            return
        if self._current_range is None:
            time.sleep(0.2)
        cmd = "W1" if range_str == "1000-1650" else "W0"
        self._inst.write(cmd)
        self._current_range = "1000-1650" if cmd == "W1" else "480-1000"
        try:
            self._inst.flush()
        except Exception:
            pass
        time.sleep(0.05)

    def set_wavelength_range(self, range_str: str) -> None:
        r = str(range_str).strip() if range_str else ""
        if r not in ("480-1000", "1000-1650"):
            return
        if getattr(self, "_inst", None):
            self._send_range(r)

    def apply_range(self) -> None:
        if self._current_range is not None:
            self._send_range(self._current_range)

    def read_wavelength_nm(self):
        try:
            self._inst.write("E")
            time.sleep(0.15)
            try:
                resp = self._inst.read().strip()
            except Exception:
                resp = self._inst.query("WL?").strip()
            if not resp:
                raise IOError("Wavemeter read timeout (device may be off or not responding)")
            val = float(resp)
            if 0 < val < 0.01:
                val = val * 1e9
            return val
        except Exception:
            raise

    def close(self) -> None:
        try:
            self._inst.write("LOCAL")
        except Exception:
            pass
        try:
            self._inst.close()
            self._rm.close()
        except Exception:
            pass


class WavemeterConnection:
    """Wavemeter GPIB connection using PyVISA only (default backend)."""

    def __init__(self, address: str):
        self._instrument = None
        self.connected = False
        a = (address or "").strip()
        if not a:
            self.gpib_address = "GPIB0::1::INSTR"
        elif a.isdigit():
            self.gpib_address = f"GPIB0::{a}::INSTR"
        else:
            self.gpib_address = a

    def connect(self) -> Tuple[bool, Optional[str]]:
        if not pyvisa:
            return (False, "Install PyVISA: pip install pyvisa")
        try:
            self.disconnect()
            self._instrument = WavemeterInstrument(self.gpib_address, open_timeout_ms=10000)
            self.connected = True
            return (True, None)
        except Exception as e:
            err = str(e).strip() or type(e).__name__
            self.disconnect()
            return (False, err)

    def disconnect(self) -> None:
        if self._instrument:
            self._instrument.close()
        self._instrument = None
        self.connected = False

    def is_connected(self) -> bool:
        return bool(self.connected and self._instrument is not None)

    def read_wavelength_nm(self):
        if not self.is_connected():
            return None
        return self._instrument.read_wavelength_nm()

    def set_wavelength_range(self, range_str: str) -> None:
        if self._instrument:
            r = str(range_str).strip() if range_str else ""
            if r in ("480-1000", "1000-1650"):
                self._instrument.set_wavelength_range(r)

    def apply_range(self) -> None:
        if self._instrument:
            self._instrument.apply_range()
