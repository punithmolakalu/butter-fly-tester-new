"""
Wavemeter (GPIB) — PyVISA

Supports:
  * **Advantest Q8326**-style SCPI: ``ID?``, ``*IDN?``, ``WL?``, ``MEAS``, ``REMOTE``, etc.
  * **Exfo / legacy** heads per ``instrument_commands/Wavemeter_Commands.md``: ``D1``/``K0``, ``E`` + read, ``W0``/``W1`` range.

Connect tries the configured GPIB address first, then the alternate GPIB interface (0 ↔ 1) when
the resource string matches ``GPIBn::addr::INSTR``. Opens use ``pyvisa_open_lock`` (see ``visa_safe``).
"""
from __future__ import annotations

import configparser
import os
import re
import time
from typing import Any, List, Optional, Tuple, cast

try:
    import pyvisa  # type: ignore[reportMissingImports]
except ImportError:
    pyvisa = None

from instruments.visa_safe import (
    pyvisa_open_lock,
    safe_close_pyvisa_resource,
    safe_close_pyvisa_resource_manager,
)


def _config_path() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "instrument_config.ini")


def _load_wavemeter_ini_options() -> Tuple[float, bool]:
    """Optional ``[Wavemeter]`` in ``instrument_config.ini``: timeout, skip_verify."""
    timeout = 8.0
    skip_verify = False
    path = _config_path()
    if not os.path.isfile(path):
        return timeout, skip_verify
    cfg = configparser.ConfigParser()
    try:
        cfg.read(path)
        if not cfg.has_section("Wavemeter"):
            return timeout, skip_verify
        timeout = float(cfg.get("Wavemeter", "timeout", fallback="8"))
        skip_verify = cfg.getboolean("Wavemeter", "skip_verify", fallback=False)
    except Exception:
        pass
    return timeout, skip_verify


def _normalize_primary_address(address: str) -> str:
    a = (address or "").strip()
    if not a:
        return "GPIB0::2::INSTR"
    if a.isdigit():
        return f"GPIB0::{a}::INSTR"
    return a


def _gpib_addresses_to_try(primary: str) -> List[str]:
    primary = (primary or "").strip()
    if not primary:
        primary = "GPIB0::2::INSTR"
    out: List[str] = [primary]
    try:
        m = re.match(r"GPIB(\d+)::(\d+)::INSTR", primary, re.I)
        if m:
            iface, addr = m.group(1), m.group(2)
            alt_iface = "1" if iface == "0" else "0"
            alt = f"GPIB{alt_iface}::{addr}::INSTR"
            if alt.upper() not in {x.upper() for x in out}:
                out.append(alt)
    except Exception:
        pass
    return out


def _configure_visa_terminators(inst: Any) -> None:
    try:
        inst.write_termination = "\n"
        inst.read_termination = "\n"
    except Exception:
        pass


def _try_prime_exfo_scpi(inst: Any) -> None:
    try:
        inst.write("D1")
        time.sleep(0.05)
        inst.write("K0")
        time.sleep(0.05)
    except Exception:
        pass


def _query_strip(inst: Any, cmd: str) -> str:
    try:
        r = inst.query(cmd)
        return (str(r) if r is not None else "").strip()
    except Exception:
        return ""


# First numeric token in a reply (handles "1550.12 nm", "λ=1064.5", scientific notation).
_FLOAT_RE = re.compile(r"[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")


def _parse_first_float_nm(text: str) -> Optional[float]:
    """Parse first float from ``text``; if value looks like meters (0 < v < 0.01), convert to nm."""
    if not text or not str(text).strip():
        return None
    m = _FLOAT_RE.search(str(text).strip())
    if not m:
        return None
    try:
        val = float(m.group(0))
    except (TypeError, ValueError):
        return None
    if 0 < val < 0.01:
        val = val * 1e9
    return val


def _is_plausible_wavelength_nm(val: float) -> bool:
    """Accept no-signal (0) or a wavelength in a broad optical range (nm)."""
    if val == 0:
        return True
    return 180.0 <= val <= 2600.0


def _verify_advantest(inst: Any) -> bool:
    """Return True if the session looks like an Advantest Q8326 (or compatible) wavemeter."""
    for cmd in ("ID?", "*IDN?", "WL?", "DA?", "DATA?", "FR?"):
        try:
            resp = _query_strip(inst, cmd)
            if resp:
                return True
        except Exception:
            pass
        try:
            inst.clear()
        except Exception:
            pass
        time.sleep(0.05)

    try:
        inst.write("MEAS")
        time.sleep(0.2)
        if _query_strip(inst, "WL?"):
            return True
    except Exception:
        pass
    try:
        inst.clear()
    except Exception:
        pass

    try:
        inst.write("REMOTE")
        time.sleep(0.1)
        if _query_strip(inst, "WL?"):
            return True
    except Exception:
        pass

    try:
        inst.write("WL?")
        time.sleep(0.15)
        raw = inst.read()
        if raw is not None and str(raw).strip():
            return True
    except Exception:
        pass

    return False


def _verify_exfo(inst: Any) -> bool:
    _try_prime_exfo_scpi(inst)
    try:
        inst.write("E")
        time.sleep(0.15)
        try:
            resp = str(inst.read()).strip()
        except Exception:
            resp = _query_strip(inst, "WL?")
        if not resp:
            return False
        val = _parse_first_float_nm(resp)
        if val is None:
            return False
        return _is_plausible_wavelength_nm(val)
    except Exception:
        pass
    return False


def _advantest_read_wavelength_nm(inst: Any) -> Optional[float]:
    try:
        resp = _query_strip(inst, "WL?")
        if not resp:
            try:
                inst.write("MEAS")
                time.sleep(0.15)
                resp = _query_strip(inst, "WL?")
            except Exception:
                resp = ""
        if not resp:
            return None
        val = _parse_first_float_nm(resp)
        if val is None:
            return None
        if _is_plausible_wavelength_nm(val):
            return val
        return None
    except (ValueError, TypeError, IndexError):
        return None


def _exfo_read_wavelength_nm(inst: Any) -> Optional[float]:
    """
    Single-shot wavelength read (Exfo / doc ``E`` + read).
    Returns None on timeout/empty/unparseable — does not raise (caller poll stays stable).
    """
    try:
        inst.write("E")
        time.sleep(0.15)
        try:
            resp = str(inst.read()).strip()
        except Exception:
            resp = _query_strip(inst, "WL?")
        if not resp:
            return None
        val = _parse_first_float_nm(resp)
        if val is None:
            return None
        if _is_plausible_wavelength_nm(val):
            return val
        return None
    except Exception:
        return None


class WavemeterInstrument:
    """Opened GPIB session with protocol detection (Advantest vs Exfo-style)."""

    def __init__(
        self,
        primary_address: str,
        open_timeout_ms: int = 10000,
        verify_timeout_ms: int = 2500,
        skip_verify: bool = False,
    ):
        if not pyvisa:
            raise RuntimeError("Install PyVISA: pip install pyvisa")
        self._primary = _normalize_primary_address(primary_address)
        self._rm: Any = None
        self._inst: Any = None
        self._protocol = "exfo"
        self._current_range: Optional[str] = None
        self.resource = self._primary
        open_timeout_ms = max(5000, int(open_timeout_ms))
        verify_timeout_ms = max(800, int(verify_timeout_ms))
        last_exc: Optional[BaseException] = None

        for addr in _gpib_addresses_to_try(self._primary):
            for backend in (None, "@py"):
                try:
                    with pyvisa_open_lock():
                        if self._rm is not None:
                            safe_close_pyvisa_resource_manager(self._rm)
                            self._rm = None
                        self._rm = pyvisa.ResourceManager(backend) if backend else pyvisa.ResourceManager()
                        try:
                            inst = self._rm.open_resource(addr, open_timeout=open_timeout_ms)
                        except TypeError:
                            inst = self._rm.open_resource(addr)
                        inst = cast(Any, inst)
                        _configure_visa_terminators(inst)
                        inst.timeout = verify_timeout_ms if not skip_verify else min(8000, open_timeout_ms)

                        if skip_verify:
                            # Open only: try reads in order (WL? then E-style) at runtime.
                            self._protocol = "auto"
                            try:
                                inst.write("REMOTE")
                                time.sleep(0.05)
                            except Exception:
                                pass
                        else:
                            # Prefer Exfo (E + read) first so a generic ``*IDN?`` on another head
                            # does not mis-classify as Advantest and break ``WL?`` reads.
                            if _verify_exfo(inst):
                                self._protocol = "exfo"
                            elif _verify_advantest(inst):
                                self._protocol = "advantest"
                            else:
                                raise RuntimeError(
                                    "Instrument did not respond to Exfo-style (E + read) "
                                    "or Advantest-style (ID?/WL?/…) verification."
                                )

                        inst.timeout = max(3000, min(8000, int(open_timeout_ms)))
                        try:
                            inst.write("REMOTE")
                            time.sleep(0.05)
                        except Exception:
                            pass

                        self._inst = inst
                        self.resource = addr
                    return
                except Exception as e:
                    last_exc = e
                    if self._inst is not None:
                        safe_close_pyvisa_resource(self._inst)
                        self._inst = None
                    if self._rm is not None:
                        safe_close_pyvisa_resource_manager(self._rm)
                        self._rm = None

        raise RuntimeError(
            "Could not open wavemeter at {}: {}".format(self._primary, last_exc or "unknown error")
        ) from last_exc

    def _send_range_exfo(self, range_str: str) -> None:
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
        if not getattr(self, "_inst", None):
            return
        if self._protocol == "exfo":
            self._send_range_exfo(r)
        else:
            # Advantest: optional Exfo-style range (ignored on pure Q8326); best-effort only.
            try:
                self._send_range_exfo(r)
            except Exception:
                pass

    def apply_range(self) -> None:
        if self._protocol != "exfo" or self._current_range is None:
            return
        if getattr(self, "_inst", None):
            self._send_range_exfo(self._current_range)

    def read_wavelength_nm(self) -> Optional[float]:
        inst = self._inst
        if inst is None:
            return None
        if self._protocol == "auto":
            v = _exfo_read_wavelength_nm(inst)
            if v is not None:
                return v
            return _advantest_read_wavelength_nm(inst)
        if self._protocol == "advantest":
            return _advantest_read_wavelength_nm(inst)
        v = _exfo_read_wavelength_nm(inst)
        if v is not None:
            return v
        return _advantest_read_wavelength_nm(inst)

    def close(self) -> None:
        try:
            if self._inst is not None:
                try:
                    self._inst.write("LOCAL")
                except Exception:
                    pass
        except Exception:
            pass
        safe_close_pyvisa_resource(self._inst)
        self._inst = None
        safe_close_pyvisa_resource_manager(self._rm)
        self._rm = None


class WavemeterConnection:
    """GUI / worker facade: same API as before, with Q8326 + legacy support."""

    def __init__(self, address: str):
        self._instrument: Optional[WavemeterInstrument] = None
        self.connected = False
        a = (address or "").strip()
        if not a:
            self.gpib_address = "GPIB0::2::INSTR"
        elif a.isdigit():
            self.gpib_address = f"GPIB0::{a}::INSTR"
        else:
            self.gpib_address = a
        self._ini_timeout, self._ini_skip_verify = _load_wavemeter_ini_options()

    def connect(self) -> Tuple[bool, Optional[str]]:
        if not pyvisa:
            return (False, "Install PyVISA: pip install pyvisa")
        try:
            self.disconnect()
            open_ms = int(max(5.0, float(self._ini_timeout)) * 1000)
            self._instrument = WavemeterInstrument(
                self.gpib_address,
                open_timeout_ms=open_ms,
                verify_timeout_ms=2500,
                skip_verify=bool(self._ini_skip_verify),
            )
            if self._instrument.resource != self.gpib_address:
                self.gpib_address = self._instrument.resource
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

    def read_wavelength_nm(self) -> Optional[float]:
        if not self.is_connected():
            return None
        inst = self._instrument
        if inst is None:
            return None
        return inst.read_wavelength_nm()

    def set_wavelength_range(self, range_str: str) -> None:
        if self._instrument:
            r = str(range_str).strip() if range_str else ""
            if r in ("480-1000", "1000-1650"):
                self._instrument.set_wavelength_range(r)

    def apply_range(self) -> None:
        if self._instrument:
            self._instrument.apply_range()
