"""
Gentec INTEGRA Power Meter

Instrument: Gentec INTEGRA power meter. Commands: *VER, *CVU (current value/unit). Responses CR/LF.
Connection: Serial (COM port), 115200 baud. Config from instrument_config.ini [Gentec] or direct port.
Details: Commands start with *; get_value(), get_value_with_unit(), get_value_mw().
"""
from __future__ import annotations

import configparser
import os
import re
import time

try:
    import serial  # type: ignore[import-untyped]
except ImportError:
    serial = None

from instruments.actuator import format_com_port_open_error, iter_serial_port_names_for_open

FLOAT_RE = re.compile(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")
# INTEGRA text replies often contain this; some firmware omits newlines until buffer fills.
_VER_HINTS = ("INTEGRA", "INTEGR", "VERSION", "VER", "GENTEC")


class GentecConnection:
    """Gentec INTEGRA power meter via COM. Connect to given port; then *VER, *CVU for power (mW etc.)."""

    def __init__(self, config_file='instrument_config.ini', instrument_name='Gentec', port=None):
        self.instrument_name = instrument_name
        self.serial_connection = None
        self.connected = False
        self.last_connect_error = ""
        self.baudrate = 115200
        # GUI / test scaling (Main tab Gentec Mult); applied to all get_value_mw* results.
        self._gui_multiplier = 1.0
        if port and str(port).strip():
            p = str(port).strip()
            if len(p) >= 2 and ((p[0] == p[-1] == '"') or (p[0] == p[-1] == "'")):
                p = p[1:-1].strip()
            self.port = p
            self.timeout = 0.5
            self.enabled = True
        else:
            if not os.path.isabs(config_file):
                config_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), config_file)
            self.config = configparser.ConfigParser()
            self.config.read(config_file)
            self.port = None
            self.timeout = 0.5
            self.enabled = False
            if self.config.has_section(instrument_name):
                try:
                    self.port = self.config.get(instrument_name, 'port', fallback=None)
                    if self.port:
                        self.port = self.port.strip()
                    self.timeout = self.config.getfloat(instrument_name, 'timeout', fallback=0.5)
                    self.enabled = self.config.getboolean(instrument_name, 'enabled', fallback=False)
                except Exception:
                    self.enabled = False

    def _response_looks_like_integra(self, text: str) -> bool:
        if not text or not str(text).strip():
            return False
        u = str(text).strip().upper()
        if FLOAT_RE.search(text):
            return True
        return any(h in u for h in _VER_HINTS)

    def _try_handshake(self) -> bool:
        """Return True if *VER or *CVU gets a plausible INTEGRA response (after port is open)."""
        # Command variants: manual says no terminator; some USB stacks still need \r.
        ver_cmds = ("*VER", "*ver", "*VER\r", "*VER\n")
        for cmd in ver_cmds:
            for _ in range(4):
                version = self.query(cmd)
                if self._response_looks_like_integra(version):
                    return True
                time.sleep(0.12)
        try:
            self.serial_connection.reset_input_buffer()
            time.sleep(0.05)
        except Exception:
            pass
        cvu_cmds = ("*CVU", "*cvu", "*CVU\r")
        for cmd in cvu_cmds:
            for _ in range(4):
                resp = self.query(cmd)
                if resp and (FLOAT_RE.search(resp) or self._response_looks_like_integra(resp)):
                    return True
                time.sleep(0.15)
        return False

    def connect(self) -> bool:
        self.last_connect_error = ""
        if not self.enabled or not self.port or serial is None:
            self.last_connect_error = "No COM port or pyserial is not installed"
            return False
        if self.serial_connection and self.serial_connection.is_open:
            try:
                self.serial_connection.close()
            except Exception:
                pass
            self.serial_connection = None
        timeout_sec = max(2.0, float(getattr(self, "timeout", 0.5)))
        primary_baud = int(getattr(self, "baudrate", 115200) or 115200)
        baud_candidates = [primary_baud]
        for b in (115200, 9600, 57600, 38400):
            if b not in baud_candidates:
                baud_candidates.append(b)
        last_serial_open_error = None
        handshake_failed = False
        for attempt in range(2):
            for baud in baud_candidates:
                opened = False
                for port_try in iter_serial_port_names_for_open(self.port):
                    try:
                        self.serial_connection = serial.Serial(
                            port=port_try, baudrate=baud, timeout=timeout_sec,
                            bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE,
                            write_timeout=timeout_sec
                        )
                        opened = True
                        last_serial_open_error = None
                        break
                    except Exception as e:
                        last_serial_open_error = e
                        self.serial_connection = None
                if not opened:
                    continue
                # USB-CDC meters often need >300 ms before the first *VER succeeds.
                time.sleep(1.0)
                try:
                    self.serial_connection.dtr = True
                    self.serial_connection.rts = True
                    time.sleep(0.15)
                except Exception:
                    pass
                try:
                    self.serial_connection.reset_input_buffer()
                    self.serial_connection.reset_output_buffer()
                except Exception:
                    pass
                time.sleep(0.2)
                self.baudrate = baud
                if self._try_handshake():
                    self.connected = True
                    return True
                handshake_failed = True
                try:
                    if self.serial_connection and getattr(self.serial_connection, "is_open", False):
                        self.serial_connection.close()
                except Exception:
                    pass
                self.serial_connection = None
            if attempt == 0:
                time.sleep(0.6)
        self.connected = False
        if last_serial_open_error is not None:
            self.last_connect_error = format_com_port_open_error(
                self.port, last_serial_open_error, "Gentec powermeter"
            )
        elif handshake_failed:
            self.last_connect_error = (
                "No response to *VER or *CVU on {} — wrong port, baud (tried several rates), "
                "meter busy in another app, or device not INTEGRA/serial."
            ).format(self.port)
        else:
            self.last_connect_error = (
                "Could not open {} — check USB, Scan COM, Save, Connect."
            ).format(self.port)
        return False

    def disconnect(self) -> None:
        if self.serial_connection and self.serial_connection.is_open:
            self.serial_connection.close()
            self.connected = False

    def is_connected(self) -> bool:
        return bool(self.connected and self.serial_connection and self.serial_connection.is_open)

    def set_gui_multiplier(self, value: float) -> None:
        """Multiply all ``get_value_mw`` / ``get_value_mw_and_display_unit`` results (Main tab + LIV, etc.)."""
        try:
            v = float(value)
            self._gui_multiplier = v if v > 0.0 and v < 1e15 else 1.0
        except (TypeError, ValueError):
            self._gui_multiplier = 1.0

    def write_command(self, command: str) -> bool:
        if not self.serial_connection or not self.serial_connection.is_open or not command.startswith('*'):
            return False
        try:
            self.serial_connection.write(command.encode('ascii', errors='ignore'))
            self.serial_connection.flush()
            return True
        except Exception:
            return False

    def read_response(self) -> str:
        """Read one reply; never raises — callers treat empty as timeout/no data."""
        if not self.serial_connection or not self.serial_connection.is_open:
            return ""
        ser = self.serial_connection
        try:
            t = max(0.15, float(ser.timeout or 0.5))
            deadline = time.time() + t
            buf = bytearray()
            while time.time() < deadline:
                try:
                    n = ser.in_waiting
                except Exception:
                    return ""
                if n:
                    try:
                        chunk = ser.read(n)
                    except Exception:
                        return ""
                    if chunk:
                        buf.extend(chunk)
                        if b"\n" in chunk or b"\r" in chunk:
                            break
                else:
                    if buf:
                        break
                    time.sleep(0.02)
            if buf:
                return buf.decode("ascii", errors="ignore").strip()
            try:
                line = ser.readline()
            except Exception:
                return ""
            if line:
                return line.decode("ascii", errors="ignore").strip()
            return ""
        except Exception:
            return ""

    def query(self, command: str) -> str:
        if not self.write_command(command):
            return ""
        time.sleep(0.25)
        try:
            response = self.read_response()
            if not response:
                time.sleep(0.2)
                response = self.read_response()
            return response
        except Exception:
            return ""

    def get_version(self) -> str:
        return self.query("*VER")

    def get_value(self):
        resp = self.query("*CVU")
        if not resp:
            return None
        m = FLOAT_RE.search(resp)
        if not m:
            return None
        try:
            return float(m.group(0))
        except ValueError:
            return None

    def get_value_with_unit(self) -> tuple:
        resp = self.query("*CVU")
        if not resp:
            return (None, "")
        m = FLOAT_RE.search(resp)
        if not m:
            return (None, "")
        try:
            value = float(m.group(0))
        except ValueError:
            return (None, "")
        resp_upper = resp.upper()
        if "MW" in resp_upper or "MILLIWATT" in resp_upper:
            unit = "mW"
        elif "UW" in resp_upper or "MICROWATT" in resp_upper:
            unit = "µW"
        elif "NW" in resp_upper or "NANOWATT" in resp_upper:
            unit = "nW"
        elif "W" in resp_upper or "WATT" in resp_upper:
            unit = "W" if "MW" not in resp_upper and "UW" not in resp_upper and "NW" not in resp_upper else "mW"
        else:
            unit = "mW" if abs(value) < 0.001 else "W"
        return (value, unit)

    def get_value_mw(self):
        mw, _ = self.get_value_mw_and_display_unit()
        return mw

    def get_value_mw_and_display_unit(self):
        """Return (power_mW, unit_label). Required by GentecWorker — one *CVU read; GUI polls this after connect."""
        value, unit = self.get_value_with_unit()
        if value is None:
            return (None, "")
        disp = unit if unit else "mW"
        if unit == "W":
            mw = value * 1000.0
        elif unit == "mW":
            mw = value
        elif unit == "µW":
            mw = value / 1000.0
        elif unit == "nW":
            mw = value / 1000000.0
        else:
            mw = value
        m = float(getattr(self, "_gui_multiplier", 1.0) or 1.0)
        if m != 1.0 and mw is not None:
            mw = float(mw) * m
        return (mw, disp)
