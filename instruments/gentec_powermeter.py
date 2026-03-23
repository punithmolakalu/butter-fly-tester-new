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

FLOAT_RE = re.compile(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")


class GentecConnection:
    """Gentec INTEGRA power meter via COM. Connect to given port; then *VER, *CVU for power (mW etc.)."""

    def __init__(self, config_file='instrument_config.ini', instrument_name='Gentec', port=None):
        self.instrument_name = instrument_name
        self.serial_connection = None
        self.connected = False
        self.baudrate = 115200
        if port and str(port).strip():
            self.port = str(port).strip()
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

    def connect(self) -> bool:
        if not self.enabled or not self.port or serial is None:
            return False
        if self.serial_connection and self.serial_connection.is_open:
            try:
                self.serial_connection.close()
            except Exception:
                pass
            self.serial_connection = None
        timeout_sec = max(2.0, float(getattr(self, "timeout", 0.5)))
        for attempt in range(2):
            try:
                self.serial_connection = serial.Serial(
                    port=self.port, baudrate=self.baudrate, timeout=timeout_sec,
                    bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE,
                    write_timeout=timeout_sec
                )
                time.sleep(0.3)
                try:
                    self.serial_connection.dtr = True
                    self.serial_connection.rts = True
                    time.sleep(0.1)
                except Exception:
                    pass
                self.serial_connection.reset_input_buffer()
                self.serial_connection.reset_output_buffer()
                time.sleep(0.2)
                version = self.get_version()
                if version:
                    self.connected = True
                    return True
                try:
                    self.serial_connection.close()
                except Exception:
                    pass
                self.serial_connection = None
            except Exception:
                if self.serial_connection and getattr(self.serial_connection, "is_open", False):
                    try:
                        self.serial_connection.close()
                    except Exception:
                        pass
                self.serial_connection = None
            if attempt == 0:
                time.sleep(0.5)
        self.connected = False
        return False

    def disconnect(self) -> None:
        if self.serial_connection and self.serial_connection.is_open:
            self.serial_connection.close()
            self.connected = False

    def is_connected(self) -> bool:
        return bool(self.connected and self.serial_connection and self.serial_connection.is_open)

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
        if not self.serial_connection or not self.serial_connection.is_open:
            raise IOError("Gentec not connected")
        try:
            if self.serial_connection.in_waiting > 0:
                out = self.serial_connection.readline().decode('ascii', errors='ignore').strip()
            else:
                out = self.serial_connection.readline().decode('ascii', errors='ignore').strip()
            if not out:
                raise IOError("Gentec read timeout (device may be off or not responding)")
            return out
        except Exception:
            raise

    def query(self, command: str) -> str:
        if not self.write_command(command):
            return ""
        time.sleep(0.3)
        response = self.read_response()
        if not response:
            time.sleep(0.2)
            response = self.read_response()
        return response

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
        value, unit = self.get_value_with_unit()
        if value is None:
            return None
        if unit == "W":
            return value * 1000.0
        elif unit == "mW":
            return value
        elif unit == "µW":
            return value / 1000.0
        elif unit == "nW":
            return value / 1000000.0
        return value
