"""
Thorlabs Power Meter (SCPI)

Instrument: Thorlabs power meter (SCPI). *IDN?, CONF:POW, SENS:WAV <nm>, MEAS:POW? / READ?.
Connection: VISA (PyVISA) by resource string or by serial number (find in VISA resources).
Details: Photodiode mode, wavelength setting. READ? is normalized to watts using SENS:POW:UNIT? (or
instrument_config.ini power_scpi_unit=w|mw|uw|dbm). The GUI shows Thorlabs power in milliwatts (mW).
"""
from __future__ import annotations

import configparser
import math
import os
import re
import threading
import time
from typing import Any, List, Optional, Protocol, Set, cast


class _VisaMessageResource(Protocol):
    timeout: int
    write_termination: str
    read_termination: str

    def query(self, cmd: str) -> Any: ...

    def write(self, cmd: str) -> Any: ...

    def close(self) -> Any: ...

    def flush(self, mask: int) -> Any: ...

try:
    import pyvisa  # type: ignore[reportMissingImports]
    PYVISA_AVAILABLE = True
except ImportError:
    pyvisa = None
    PYVISA_AVAILABLE = False

from instruments.visa_safe import safe_close_pyvisa_resource, safe_close_pyvisa_resource_manager

FLOAT_RE = re.compile(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")

# Reject non-physical parses / overflow garbage from bad SCPI fragments.
THORLABS_MAX_RAW_W = 5e3
THORLABS_MAX_MW = 1e9


def _parse_scpi_response_float(resp: Any) -> Optional[float]:
    """
    Parse the primary numeric value from a SCPI response.
    Prefer parsing the whole line (preserves full mantissa from the instrument), else use the
    last regex match (avoids a leading stray digit in verbose replies).
    """
    if resp is None:
        return None
    s = str(resp).strip()
    if not s:
        return None
    upper = s.upper()
    for suf in (" NM", " M", " HZ", "HZ"):
        if upper.endswith(suf):
            s = s[: -len(suf)].strip()
            break
    try:
        v = float(s)
        if math.isfinite(v):
            return v
    except ValueError:
        pass
    matches = FLOAT_RE.findall(s)
    if not matches:
        return None
    try:
        v = float(matches[-1])
        return v if math.isfinite(v) else None
    except ValueError:
        return None


def format_power_mw_display(value_mw: Any) -> str:
    """
    Format a power reading (mW) for GUI labels.
    Adapts decimal places to magnitude so the display always shows
    ~4 significant digits and stays readable.
    """
    if value_mw is None:
        return "—"
    try:
        v = float(value_mw)
    except (TypeError, ValueError):
        return "—"
    if not math.isfinite(v):
        return "—"
    if abs(v) < 1e-300:
        return "0.0000"
    av = abs(v)
    if av >= 1000:
        return f"{v:.1f}"
    if av >= 100:
        return f"{v:.2f}"
    if av >= 10:
        return f"{v:.3f}"
    if av >= 1e-4:
        return f"{v:.4f}"
    if av > 0:
        return f"{v:.4e}"
    return "0.0000"


def thorlabs_power_display_unit(value_mw: Any) -> str:
    """GUI unit next to Thorlabs readouts — always milliwatts (same scale as read_power_mw())."""
    return "mW"


# Spinbox bounds for Main / Connection tab (not in upstream; kept for UI compatibility).
THORLABS_GUI_MULT_MIN = 1e-12
THORLABS_GUI_MULT_MAX = 1e6


def format_thorlabs_power_mw_display(value_mw: Any) -> str:
    """Format Thorlabs power for labels; value is in mW (same rules as format_power_mw_display)."""
    return format_power_mw_display(value_mw)


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

    rm = None
    try:
        rm = pyvisa.ResourceManager()
        add_from_rm(rm)
    except Exception:
        pass
    finally:
        safe_close_pyvisa_resource_manager(rm)

    rm_py = None
    try:
        rm_py = pyvisa.ResourceManager("@py")
        add_from_rm(rm_py)
    except Exception:
        pass
    finally:
        safe_close_pyvisa_resource_manager(rm_py)
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


def _enumerate_visa_resources(rm: Any) -> List[str]:
    """All instrument resources (same idea as a minimal PM100USB test app: list_resources). Never raises."""
    seen: Set[str] = set()
    out: List[str] = []
    for q in (None, "?*", "?*::INSTR", "USB?*", "USB?*::INSTR"):
        try:
            if q is None:
                it = rm.list_resources()
            else:
                it = rm.list_resources(q)
            for r in it:
                if r and r not in seen:
                    seen.add(r)
                    out.append(r)
        except Exception:
            pass
    return out


def _find_resource_for_serial(rm: Any, serial_sn: str, open_timeout_ms: int) -> Optional[str]:
    """
    Match PM100USB sample app: prefer VISA string containing serial, else open each resource and *IDN?.
    """
    if not serial_sn or not PYVISA_AVAILABLE:
        return None
    sn = str(serial_sn).strip()
    if not sn:
        return None
    try:
        resources = _enumerate_visa_resources(rm)
    except Exception:
        resources = []
    for r in resources:
        if sn in r:
            return r
    for r in resources:
        try:
            try:
                temp = cast(_VisaMessageResource, rm.open_resource(r, open_timeout=open_timeout_ms))
            except TypeError:
                temp = cast(_VisaMessageResource, rm.open_resource(r))
            temp.timeout = 2000
            temp.write_termination = "\n"
            temp.read_termination = "\n"
            idn = str(temp.query("*IDN?")).strip()
            safe_close_pyvisa_resource(temp)
            if sn in idn:
                return r
        except Exception:
            continue
    return None


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
        self._rm: Any = None
        self._inst: Optional[_VisaMessageResource] = None
        self._connected = False
        self._last_wav_nm = None
        self._phot_mode_set = False
        self._io_lock = threading.RLock()
        self.last_connect_error: Optional[str] = None
        # GUI multiplier: purely a software scale applied to returned values (mW/W) for UI/recipes.
        self._gui_multiplier = 1.0
        # How READ? / MEAS:POW? numeric value is scaled: W, MW, UW, or DBM (from query or instrument_config.ini).
        self._power_scpi_unit_config = "auto"
        self._detected_scpi_unit = "W"
        if self.config.has_section(instrument_name):
            self._power_scpi_unit_config = self.config.get(
                instrument_name, "power_scpi_unit", fallback="auto"
            ).strip()
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

    def set_gui_multiplier(self, value: float) -> None:
        """Set GUI scale factor (applied in read_power_w/read_power_mw)."""
        try:
            v = float(value)
            self._gui_multiplier = v if math.isfinite(v) and 0.0 < v < 1e15 else 1.0
        except Exception:
            self._gui_multiplier = 1.0

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
                            inst = cast(_VisaMessageResource, self._rm.open_resource(self.resource, open_timeout=open_timeout_ms))
                        except TypeError:
                            inst = cast(_VisaMessageResource, self._rm.open_resource(self.resource))
                        inst.timeout = timeout_ms
                        inst.write_termination = "\n"
                        inst.read_termination = "\n"
                        time.sleep(0.2)
                        idn = str(inst.query("*IDN?")).strip()
                        if idn:
                            time.sleep(0.1)
                            self._inst = inst
                            self.set_photodiode_mode()
                            self._connected = True
                            return True
                        self.last_connect_error = "*IDN? empty for {}".format(self.resource)
                        safe_close_pyvisa_resource(inst)
                    except Exception as e:
                        self.last_connect_error = str(e)
                        if self._inst:
                            safe_close_pyvisa_resource(self._inst)
                            self._inst = None
                serial_sn = self.serial_number
                if not serial_sn:
                    continue
                resource = _find_resource_for_serial(self._rm, serial_sn, open_timeout_ms)
                if resource is None:
                    self.last_connect_error = "Device with serial {} not found on VISA bus".format(serial_sn)
                    continue
                try:
                    inst2 = cast(_VisaMessageResource, self._rm.open_resource(resource, open_timeout=open_timeout_ms))
                except TypeError:
                    inst2 = cast(_VisaMessageResource, self._rm.open_resource(resource))
                inst2.timeout = timeout_ms
                inst2.write_termination = "\n"
                inst2.read_termination = "\n"
                time.sleep(0.2)
                idn = str(inst2.query("*IDN?")).strip()
                if not idn:
                    safe_close_pyvisa_resource(inst2)
                    self.last_connect_error = "*IDN? empty for {}".format(resource)
                    continue
                time.sleep(0.1)
                self.resource = resource
                self._inst = inst2
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
        if self._inst is not None:
            safe_close_pyvisa_resource(self._inst)
        self._inst = None
        if self._rm is not None:
            safe_close_pyvisa_resource_manager(self._rm)
        self._rm = None
        self._connected = False
        self._phot_mode_set = False
        self._last_wav_nm = None
        self._detected_scpi_unit = "W"

    def is_connected(self) -> bool:
        return bool(self._connected and self._inst is not None)

    def write(self, cmd: str) -> None:
        with self._io_lock:
            if not self.is_connected() or self._inst is None:
                raise RuntimeError("Thorlabs powermeter not connected")
            self._inst.write(cmd)

    def query(self, cmd: str) -> str:
        with self._io_lock:
            if not self.is_connected() or self._inst is None:
                raise RuntimeError("Thorlabs powermeter not connected")
            return str(self._inst.query(cmd)).strip()

    def set_photodiode_mode(self) -> bool:
        if not self.is_connected():
            return False
        if self._phot_mode_set:
            return True
        try:
            # PM100USB sample app does not reset the head; *RST can delay reads and confuse unit state.
            self.write("*CLS")
            time.sleep(0.15)
            self.write("CONF:POW")
            self.write("POW:UNIT W")
            try:
                self.write("SENS:POW:UNIT W")
            except Exception:
                pass
            self.write("POW:RANG:AUTO ON")
            self.write("SENS:AVER 4")
            try:
                self.write("INP:PDI:FILT:STAT ON")
            except Exception:
                pass
            time.sleep(0.2)
            self._phot_mode_set = True
            self._sync_scpi_power_unit()
            return True
        except Exception:
            return False

    def _sync_scpi_power_unit(self) -> None:
        """
        READ? returns a float in the meter's active unit (W, mW, µW, or dBm depending on firmware).
        We normalize to watts in read_power_w(); read_power_mw() is always W×1000.

        instrument_config.ini [Thorlabs_Powermeter] power_scpi_unit:
          auto — query SENS:POW:UNIT? / POW:UNIT? (default)
          w | mw | uw | dbm — force interpretation if query fails or meter is wrong
        """
        cfg = (self._power_scpi_unit_config or "auto").strip().lower()
        if cfg in ("mw", "milliwatt", "milliwatts"):
            self._detected_scpi_unit = "MW"
            return
        if cfg in ("w", "watt", "watts"):
            self._detected_scpi_unit = "W"
            return
        if cfg in ("uw", "microwatt", "microwatts", "uwatt"):
            self._detected_scpi_unit = "UW"
            return
        if cfg in ("dbm",):
            self._detected_scpi_unit = "DBM"
            return

        self._detected_scpi_unit = "W"
        if not self.is_connected():
            return
        for cmd in ("SENS:POW:UNIT?", "POW:UNIT?", "SENS:POW:DC:UNIT?"):
            try:
                r = self.query(cmd).strip().upper().replace(" ", "")
                if not r:
                    continue
                if "DBM" in r:
                    self._detected_scpi_unit = "DBM"
                    return
                if r == "MW" or r.startswith("MW") or "MILLIWATT" in r:
                    self._detected_scpi_unit = "MW"
                    return
                if r == "UW" or "MICROW" in r or "UWATT" in r:
                    self._detected_scpi_unit = "UW"
                    return
                if r == "W" or r == "WATT" or r == "WATTS":
                    self._detected_scpi_unit = "W"
                    return
            except Exception:
                continue

    def _reading_float_to_watts(self, val: float) -> Optional[float]:
        """Convert parsed READ? value to watts using _detected_scpi_unit."""
        if not math.isfinite(val):
            return None
        u = getattr(self, "_detected_scpi_unit", "W")
        if u == "MW":
            return float(val) * 1e-3
        if u == "UW":
            return float(val) * 1e-6
        if u == "DBM":
            try:
                return 10.0 ** ((float(val) - 30.0) / 10.0)
            except Exception:
                return None
        return float(val)

    def set_wavelength_nm(self, wav_nm: float, *, force: bool = False) -> bool:
        """
        Set sensor calibration wavelength (nm). SCPI: SENS:WAV; some heads also accept SENS:CORR:WAV.
        When force is False, skip sending if the last applied value already matches.
        When force is True (main GUI Manual Control Apply λ, recipe LIV/PER, CLI tests), always send SCPI and run SENS:WAV? verify.
        """
        if not self.is_connected():
            return False
        try:
            wav_nm = float(wav_nm)
            if wav_nm <= 0:
                return False
        except Exception:
            return False
        if (
            not force
            and self._last_wav_nm is not None
            and abs(self._last_wav_nm - wav_nm) < 0.001
        ):
            return True
        try:
            self.write(f"SENS:WAV {wav_nm}")
            try:
                self.write(f"SENS:CORR:WAV {wav_nm}")
            except Exception:
                pass
            time.sleep(0.25)
            verified = False
            try:
                r = self.query("SENS:WAV?")
                got = _parse_scpi_response_float(r)
                if got is not None:
                    if got < 1.0 and wav_nm > 50:
                        got *= 1e9
                    tol = max(0.2, abs(wav_nm) * 1e-4)
                    verified = abs(got - wav_nm) <= tol
                else:
                    verified = True
            except Exception:
                verified = True
            if verified:
                self._last_wav_nm = wav_nm
                return True
            return False
        except Exception:
            return False

    def read_wavelength_nm(self) -> Optional[float]:
        """
        Query calibration wavelength (nm). Tries SENS:WAV? then SENS:CORR:WAV?.
        Instrument may return meters (small float) or nm; values in (0, 1) are treated as meters × 1e9.
        """
        if not self.is_connected():
            return None
        for cmd in ("SENS:WAV?", "SENS:CORR:WAV?"):
            try:
                r = self.query(cmd)
                got = _parse_scpi_response_float(r)
                if got is None:
                    continue
                if 0 < got < 1.0:
                    got *= 1e9
                if not math.isfinite(got) or got <= 0:
                    continue
                return got
            except Exception:
                continue
        return None

    def read_power_w(self) -> Optional[float]:
        if not self.is_connected():
            return None
        # PM100USB reference: primary command is MEAS:POW? (same as Thorlabs sample single-file app).
        for cmd in ("MEAS:POW?", "READ?", "FETC?"):
            try:
                with self._io_lock:
                    if self._inst is None:
                        return None
                    resp = str(self._inst.query(cmd)).strip()
                val_o = _parse_scpi_response_float(resp)
                if val_o is None:
                    continue
                val = float(val_o)
                p_w = self._reading_float_to_watts(val)
                if p_w is None:
                    continue
                if not math.isfinite(p_w) or abs(float(p_w)) > THORLABS_MAX_RAW_W:
                    continue
                m = float(getattr(self, "_gui_multiplier", 1.0) or 1.0)
                if not math.isfinite(m) or m <= 0.0:
                    m = 1.0
                p_w = float(p_w) * m
                if not math.isfinite(p_w) or abs(float(p_w)) > THORLABS_MAX_RAW_W:
                    continue
                return p_w
            except Exception:
                continue
        # Do not raise: PER/LIV poll in a loop and need None to retry; raising skips samples silently.
        return None

    def read_power_mw(self) -> Optional[float]:
        """
        Power in milliwatts for Gentec/LIV/PER/GUI (single canonical scale).

        read_power_w() always returns **watts** (READ? value normalized using the meter's SCPI unit).
        This method is W×1000 only — it does not assume READ? was already in mW.
        """
        try:
            p_w = self.read_power_w()
        except Exception:
            return None
        if p_w is None:
            return None
        try:
            out = float(p_w) * 1000.0
            if not math.isfinite(out) or abs(out) > THORLABS_MAX_MW:
                return None
            return out
        except (TypeError, ValueError):
            return None
