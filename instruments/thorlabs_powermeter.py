"""
Thorlabs Power Meter (SCPI)

Instrument: Thorlabs power meter (SCPI). *IDN?, CONF:POW, SENS:WAV <nm>, MEAS:POW? / READ?.
Connection: VISA (PyVISA) by resource string or by serial number (find in VISA resources).
Details: Photodiode mode, wavelength setting, power in W or mW. Config from instrument_config.ini or resource=.
"""
from __future__ import annotations

import configparser
import os
import re
import time
from typing import List, Optional, Set

try:
    import pyvisa  # type: ignore[reportMissingImports]
    PYVISA_AVAILABLE = True
except ImportError:
    pyvisa = None
    PYVISA_AVAILABLE = False

FLOAT_RE = re.compile(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")


def is_thorlabs_usb_visa_resource(resource: str) -> bool:
    """True if this looks like a Thorlabs USB device on the VISA bus (VID 0x1313)."""
    if not resource or "::" not in resource:
        return False
    u = resource.upper()
    return "USB" in u and "0X1313" in u


def _collect_usb_visa_resources() -> List[str]:
    """USB-only VISA enumeration (fast). Used to find Thorlabs VID 0x1313 without scanning all buses."""
    if not PYVISA_AVAILABLE or pyvisa is None:
        return []
    seen: Set[str] = set()
    out: List[str] = []
    queries = ("USB?*", "USB?*::INSTR")

    def add_from_rm(rm):
        for q in queries:
            try:
                for r in rm.list_resources(q):
                    if r and r not in seen:
                        seen.add(r)
                        out.append(r)
            except Exception:
                pass

    try:
        add_from_rm(pyvisa.ResourceManager())
    except Exception:
        pass
    try:
        add_from_rm(pyvisa.ResourceManager("@py"))
    except Exception:
        pass
    return out


def scan_thorlabs_visa_resources() -> List[str]:
    """
    Return VISA resource strings for Thorlabs USB instruments (VID 0x1313).
    Use this for the Thorlabs powermeter combo so every Thorlabs USB device VISA sees is listed.
    Never raises.
    """
    try:
        candidates = _collect_usb_visa_resources()
        tl = [r for r in candidates if is_thorlabs_usb_visa_resource(r)]
        return sorted(set(tl))
    except Exception:
        return []


class ThorlabsPowermeterConnection:
    """Thorlabs power meter via VISA/SCPI. Connect by resource string or serial number."""

    def __init__(self, config_file: str = "instrument_config.ini", instrument_name: str = "Thorlabs_Powermeter", resource=None):
        if not os.path.isabs(config_file):
            config_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), config_file)
        self.config_file = config_file
        self.instrument_name = instrument_name
        self.config = configparser.ConfigParser()
        self.config.read(config_file)
        self.enabled = False
        self.timeout_s = 1.0
        self.resource = None
        self.serial_number = None
        self._rm = None
        self._inst = None
        self._connected = False
        self._last_wav_nm = None
        self._phot_mode_set = False
        self.last_connect_error: Optional[str] = None
        if resource and str(resource).strip():
            self.resource = str(resource).strip()
            parts = self.resource.split("::")
            if len(parts) >= 4:
                self.serial_number = parts[3]
            if not self.serial_number:
                self.serial_number = self.resource
            self.enabled = True
            self.timeout_s = 1.0
        elif self.config.has_section(instrument_name):
            self.enabled = self.config.getboolean(instrument_name, "enabled", fallback=False)
            self.timeout_s = self.config.getfloat(instrument_name, "timeout", fallback=1.0)
            self.resource = self.config.get(instrument_name, "resource", fallback=None)
            if self.resource:
                parts = self.resource.split("::")
                if len(parts) >= 4:
                    self.serial_number = parts[3]
            if not self.serial_number:
                self.serial_number = self.config.get(instrument_name, "serial_number", fallback=None)

    def connect(self) -> bool:
        self.last_connect_error = None
        if not self.enabled or not PYVISA_AVAILABLE or pyvisa is None:
            self.last_connect_error = "PyVISA not available or instrument disabled"
            return False
        timeout_ms = max(5000, int(self.timeout_s * 1000))
        open_timeout_ms = max(10000, timeout_ms)
        for backend in (None, "@py"):
            try:
                self.disconnect()
                self._rm = pyvisa.ResourceManager(backend) if backend else pyvisa.ResourceManager()
                if not self._rm:
                    continue
                if self.resource and "::" in self.resource:
                    # Open by address directly. Do not require self.resource to appear in list_resources():
                    # NI-VISA vs @py and some drivers enumerate differently, but open_resource often still works.
                    try:
                        try:
                            self._inst = self._rm.open_resource(self.resource, open_timeout=open_timeout_ms)
                        except TypeError:
                            self._inst = self._rm.open_resource(self.resource)
                        self._inst.timeout = timeout_ms
                        self._inst.write_termination = "\n"
                        self._inst.read_termination = "\n"
                        time.sleep(0.2)
                        idn = self._inst.query("*IDN?").strip()
                        if idn:
                            time.sleep(0.1)
                            self.set_photodiode_mode()
                            self._connected = True
                            return True
                        self.last_connect_error = "*IDN? empty for {}".format(self.resource)
                        self._inst.close()
                        self._inst = None
                    except Exception as e:
                        self.last_connect_error = str(e)
                        if self._inst:
                            try:
                                self._inst.close()
                            except Exception:
                                pass
                            self._inst = None
                serial_sn = self.serial_number
                if not serial_sn:
                    continue
                try:
                    resources = self._rm.list_resources()
                except Exception:
                    resources = []
                resource = None
                for r in resources:
                    if serial_sn in r:
                        resource = r
                        break
                if resource is None:
                    for r in resources:
                        try:
                            inst = self._rm.open_resource(r, open_timeout=open_timeout_ms)
                            inst.timeout = timeout_ms
                            idn = inst.query("*IDN?").strip()
                            inst.close()
                            if serial_sn in idn:
                                resource = r
                                break
                        except Exception:
                            continue
                if resource is None:
                    continue
                try:
                    self._inst = self._rm.open_resource(resource, open_timeout=open_timeout_ms)
                except TypeError:
                    self._inst = self._rm.open_resource(resource)
                self._inst.timeout = timeout_ms
                self._inst.write_termination = "\n"
                self._inst.read_termination = "\n"
                time.sleep(0.2)
                idn = self._inst.query("*IDN?").strip()
                if not idn or serial_sn not in idn:
                    self.disconnect()
                    continue
                time.sleep(0.1)
                self.set_photodiode_mode()
                self._connected = True
                return True
            except Exception:
                self.disconnect()
                if backend == "@py":
                    break
        if not self.last_connect_error:
            self.last_connect_error = "Could not open resource or verify *IDN? (check USB, NI-VISA / pyvisa-py driver)"
        return False

    def disconnect(self) -> None:
        try:
            if self._inst is not None:
                self._inst.close()
        except Exception:
            pass
        self._inst = None
        try:
            if self._rm is not None:
                self._rm.close()
        except Exception:
            pass
        self._rm = None
        self._connected = False
        self._phot_mode_set = False
        self._last_wav_nm = None

    def is_connected(self) -> bool:
        return bool(self._connected and self._inst is not None)

    def write(self, cmd: str) -> None:
        if not self.is_connected() or self._inst is None:
            raise RuntimeError("Thorlabs powermeter not connected")
        self._inst.write(cmd)

    def query(self, cmd: str) -> str:
        if not self.is_connected() or self._inst is None:
            raise RuntimeError("Thorlabs powermeter not connected")
        return str(self._inst.query(cmd)).strip()

    def set_photodiode_mode(self) -> bool:
        if not self.is_connected():
            return False
        if self._phot_mode_set:
            return True
        try:
            self.write("*RST")
            self.write("*CLS")
            time.sleep(0.5)
            self.write("CONF:POW")
            self.write("POW:UNIT W")
            self.write("POW:RANG:AUTO ON")
            self.write("SENS:AVER 10")
            self.write("INP:PDI:FILT:STAT ON")
            self._phot_mode_set = True
            return True
        except Exception:
            return False

    def set_wavelength_nm(self, wav_nm: float) -> bool:
        if not self.is_connected():
            return False
        try:
            wav_nm = float(wav_nm)
            if wav_nm <= 0:
                return False
        except Exception:
            return False
        if self._last_wav_nm is not None and abs(self._last_wav_nm - wav_nm) < 0.001:
            return True
        try:
            self.write(f"SENS:WAV {wav_nm}")
            # Head needs time to apply calibration before MEAS:POW? is valid (was 50 ms; too short for some PM100).
            time.sleep(0.2)
            self._last_wav_nm = wav_nm
            return True
        except Exception:
            return False

    def read_power_w(self) -> Optional[float]:
        if not self.is_connected():
            return None
        last_err = None
        for cmd in ("MEAS:POW?", "READ?", "FETC?"):
            try:
                resp = self.query(cmd)
                m = FLOAT_RE.search(resp)
                if not m:
                    continue
                return float(m.group(0))
            except Exception as e:
                last_err = e
                continue
        raise IOError("Thorlabs powermeter read failed (device may be off or not responding)") from last_err

    def read_power_mw(self) -> Optional[float]:
        p_w = self.read_power_w()
        if p_w is None:
            return None
        return p_w * 1000.0
