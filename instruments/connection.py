"""
Connection: single entry point for all instrument connections and scan functions.
Requirements: PyVISA (pyvisa), pyserial (serial). Optional: Thorlabs Kinesis + pythonnet for PRM.
Imports all instrument modules so one place has everything for the Connection tab:
  arroyo, ando, wavemeter, actuator, prm, thorlabs_powermeter, gentec_powermeter, instrument_manager.
Use: from instruments.connection import ArroyoConnection, AndoConnection, scan_gpib, scan_visa, ...
"""
from __future__ import annotations

from typing import List

try:
    import pyvisa  # type: ignore[reportMissingImports]
    PYVISA_AVAILABLE = True
except ImportError:
    pyvisa = None
    PYVISA_AVAILABLE = False

try:
    import serial  # type: ignore[reportMissingImports]
except ImportError:
    serial = None

# ----- All instrument modules (required for Connection tab and workers) -----
from instruments.arroyo import scan_available_ports, ArroyoConnection
from instruments.ando import scan_gpib_resources, probe_gpib_andos, AndoConnection
from instruments.wavemeter import WavemeterInstrument, WavemeterConnection
from instruments.actuator import ActuatorConnection
from instruments.prm import (
    KINESIS_AVAILABLE,
    find_available_kcube_dc_servo,
    scan_prm_serial_numbers,
    get_prm_scan_status,
    PRMConnection,
)
from instruments.thorlabs_powermeter import ThorlabsPowermeterConnection, scan_thorlabs_visa_resources
from instruments.gentec_powermeter import GentecConnection
from instruments.instrument_manager import InstrumentManager  # noqa: E402

# ----- Generic connections (no specific instrument) -----
class GenericComConnection:
    """Minimal serial: connect, disconnect, is_connected. Port from UI."""

    def __init__(self, port: str, baudrate: int = 9600):
        self.port = (port or "").strip()
        self.baudrate = baudrate
        self._ser = None
        self.connected = False

    def connect(self) -> bool:
        if not self.port or serial is None:
            return False
        try:
            if self._ser and self._ser.is_open:
                self._ser.close()
            self._ser = serial.Serial(port=self.port, baudrate=self.baudrate, timeout=1.0, write_timeout=1.0)
            self.connected = True
            return True
        except Exception:
            self.connected = False
            if self._ser and self._ser.is_open:
                try:
                    self._ser.close()
                except Exception:
                    pass
            return False

    def disconnect(self) -> None:
        if self._ser and self._ser.is_open:
            try:
                self._ser.close()
            except Exception:
                pass
        self._ser = None
        self.connected = False

    def is_connected(self) -> bool:
        return bool(self.connected and self._ser is not None and self._ser.is_open)


class GenericGpibConnection:
    """Minimal GPIB: connect, disconnect, is_connected. Address from UI."""

    def __init__(self, address: str):
        a = (address or "").strip()
        self.gpib_address = f"GPIB0::{a}::INSTR" if a.isdigit() else (a or "GPIB0::1::INSTR")
        self._resource = None
        self._rm = None
        self.connected = False

    def connect(self) -> bool:
        if not PYVISA_AVAILABLE or pyvisa is None:
            return False
        try:
            if self._resource:
                try:
                    self._resource.close()
                except Exception:
                    pass
                self._resource = None
            self._rm = pyvisa.ResourceManager()
            self._resource = self._rm.open_resource(self.gpib_address, open_timeout=5000)
            self._resource.timeout = 5000
            self.connected = True
            return True
        except Exception:
            self.connected = False
            if self._resource:
                try:
                    self._resource.close()
                except Exception:
                    pass
                self._resource = None
            return False

    def disconnect(self) -> None:
        if self._resource:
            try:
                self._resource.close()
            except Exception:
                pass
        self._resource = None
        self._rm = None
        self.connected = False

    def is_connected(self) -> bool:
        return bool(self.connected and self._resource is not None)


class GenericVisaConnection:
    """Minimal VISA: connect, disconnect, is_connected. Resource string from UI."""

    def __init__(self, resource_str: str):
        self.resource_str = (resource_str or "").strip()
        self._resource = None
        self._rm = None
        self.connected = False

    def connect(self) -> bool:
        if not PYVISA_AVAILABLE or pyvisa is None or not self.resource_str:
            return False
        try:
            if self._resource:
                try:
                    self._resource.close()
                except Exception:
                    pass
                self._resource = None
            self._rm = pyvisa.ResourceManager()
            self._resource = self._rm.open_resource(self.resource_str, open_timeout=5000)
            self._resource.timeout = 5000
            self.connected = True
            return True
        except Exception:
            self.connected = False
            if self._resource:
                try:
                    self._resource.close()
                except Exception:
                    pass
                self._resource = None
            return False

    def disconnect(self) -> None:
        if self._resource:
            try:
                self._resource.close()
            except Exception:
                pass
        self._resource = None
        self._rm = None
        self.connected = False

    def is_connected(self) -> bool:
        return bool(self.connected and self._resource is not None)


# ----- Helpers -----
def scan_ports() -> List[str]:
    """Return list of COM ports; never raises."""
    try:
        return scan_available_ports()
    except Exception:
        return []


def scan_gpib() -> List[str]:
    """Return list of GPIB resource strings; never raises."""
    try:
        return scan_gpib_resources()
    except Exception:
        return []


def scan_prm() -> List[str]:
    """Return list of PRM (Kinesis) serial numbers; never raises."""
    try:
        return scan_prm_serial_numbers()
    except Exception:
        return []


def scan_visa() -> List[str]:
    """Return list of all available VISA resource strings (for Thorlabs powermeter, etc.), sorted; never raises."""
    if not PYVISA_AVAILABLE or pyvisa is None:
        return []
    try:
        seen: set = set()
        resources: List[str] = []

        def add_from_rm(rm, queries=None):
            if queries is None:
                queries = ("?*::INSTR", "?*", "USB?*", "GPIB?*", "TCPIP?*", "ASRL?*")
            for q in queries:
                try:
                    for r in rm.list_resources(q):
                        if r and r not in seen:
                            seen.add(r)
                            resources.append(r)
                except Exception:
                    pass

        # Default backend (e.g. NI-VISA on Windows)
        try:
            rm = pyvisa.ResourceManager()
            add_from_rm(rm)
        except Exception:
            pass

        # pyvisa-py backend (often shows USB devices that NI-VISA misses)
        try:
            rm_py = pyvisa.ResourceManager("@py")
            add_from_rm(rm_py)
        except Exception:
            pass

        return sorted(resources)
    except Exception:
        return []


def scan_thorlabs_visa() -> List[str]:
    """Return VISA addresses for Thorlabs USB devices (VID 0x1313). For powermeter combo; never raises."""
    try:
        return scan_thorlabs_visa_resources()
    except Exception:
        return []


def connect_arroyo(manager: InstrumentManager, port: str) -> bool:
    return manager.connect_arroyo(port)


def disconnect_arroyo(manager: InstrumentManager) -> None:
    manager.disconnect_arroyo()


__all__ = [
    "PYVISA_AVAILABLE", "KINESIS_AVAILABLE", "find_available_kcube_dc_servo",
    "scan_ports", "scan_gpib", "scan_prm", "scan_visa", "scan_thorlabs_visa",
    "scan_available_ports", "scan_gpib_resources", "probe_gpib_andos",
    "scan_prm_serial_numbers", "get_prm_scan_status",
    "connect_arroyo", "disconnect_arroyo",
    "ArroyoConnection", "AndoConnection", "WavemeterInstrument", "WavemeterConnection",
    "GentecConnection", "PRMConnection", "ThorlabsPowermeterConnection", "ActuatorConnection",
    "GenericComConnection", "GenericGpibConnection", "GenericVisaConnection",
    "InstrumentManager",
]
