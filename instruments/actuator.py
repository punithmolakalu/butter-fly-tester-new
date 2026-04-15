"""
Arduino-based Actuator Controller

Connection and command framing match the working standalone actuator GUI: open → 2 s reset settle → clear RX only;
send lines with \\n; poll readline() with configurable wait. Windows: plain COM1–9, \\\\.\\ for COM10+.
"""
from __future__ import annotations

import configparser
from typing import Optional
import os
import time

try:
    import serial  # type: ignore[reportMissingImports]
except ImportError:
    serial = None

# Default distance (mm) for Manual Control quick Move A / Move B and tools/test_actuator_terminal.py
ACTUATOR_DEFAULT_MANUAL_DISTANCE_MM = 206.0

# After a command is written, only read the port for this long (seconds). Do not block for full motion.
ACTUATOR_SEND_READ_TIMEOUT_SEC = 0.35

# UI status-bar estimates when firmware does not report completion (seconds).
ACTUATOR_ESTIMATE_HOME_SINGLE_SEC = 10.0
ACTUATOR_ESTIMATE_HOME_BOTH_SEC = 15.0


def _serial_port_for_open(port: str) -> str:
    """Windows: plain COM1–COM9; \\\\.\\COM10+ only (same rule as Gentec / pyserial docs)."""
    p = (port or "").strip()
    if not p or os.name != "nt":
        return p
    u = p.upper()
    if u.startswith("\\\\.\\"):
        return p
    if u.startswith("COM") and u[3:].isdigit():
        n = int(u[3:])
        if n >= 10:
            return "\\\\.\\" + u
        return p
    return p


def iter_serial_port_names_for_open(logical_port: str):
    """
    Names to pass to serial.Serial(). On Windows COM10+, try extended \\\\.\\COMnn first,
    then the plain COMnn string — some USB-serial stacks only accept one form.
    """
    p = (logical_port or "").strip()
    if not p:
        return
    if os.name != "nt":
        yield p
        return
    seen = set()
    for cand in (_serial_port_for_open(p), p):
        if cand not in seen:
            seen.add(cand)
            yield cand


def _is_serial_access_denied(exc: BaseException) -> bool:
    if isinstance(exc, PermissionError):
        return True
    if getattr(exc, "errno", None) == 13:
        return True
    msg = str(exc).lower()
    return "access is denied" in msg or ("permission" in msg and "denied" in msg)


def format_com_port_open_error(port: str, exc: BaseException, device_label: str) -> str:
    """User-facing message for pyserial Serial() failures (shared by Actuator, Gentec, tests)."""
    if _is_serial_access_denied(exc):
        return (
            "{} — access denied (port busy). Close Arduino Serial Monitor, PuTTY, Butterfly Tester rows on this COM, "
            "then wait a few seconds and connect again."
        ).format(port)
    msg = str(exc).lower()
    if (isinstance(exc, OSError) and getattr(exc, "errno", None) == 2) or "cannot find the file" in msg or "cannot find" in msg:
        return (
            "{} — port not found ({} unplugged, COM reassigned, or hub not ready). "
            "Connection tab: Scan COM, pick the current port for this device, Save, Connect."
        ).format(port, device_label)
    return str(exc) or "Serial open failed"


def _friendly_actuator_open_error(port: str, exc: BaseException) -> str:
    return format_com_port_open_error(port, exc, "Arduino")


class ActuatorConnection:
    """Arduino actuator connection via COM. Connect to given port; then home/move A/B."""

    def __init__(self, config_file='instrument_config.ini', instrument_name='Actuators', port=None, baudrate=None):
        self.instrument_name = instrument_name
        self.serial_connection = None
        self.connected = False
        self.last_connect_error = ""
        if port and str(port).strip():
            self.port = str(port).strip()
            try:
                self.baudrate = int(baudrate) if baudrate is not None else 115200
            except (TypeError, ValueError):
                self.baudrate = 115200
            self.timeout = 1.0
            self.enabled = True
        else:
            if not os.path.isabs(config_file):
                config_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), config_file)
            self.config = configparser.ConfigParser()
            self.config.read(config_file)
            self.port = None
            self.baudrate = 115200
            self.timeout = 1.0
            self.enabled = False
            if self.config.has_section('Actuators'):
                try:
                    self.port = self.config.get('Actuators', 'port', fallback=None)
                    if self.port:
                        self.port = self.port.strip()
                    self.baudrate = self.config.getint('Actuators', 'baudrate', fallback=115200)
                    self.timeout = self.config.getfloat('Actuators', 'timeout', fallback=1.0)
                    self.enabled = self.config.getboolean('Actuators', 'enabled', fallback=False)
                except Exception:
                    self.enabled = False

    def connect(self) -> bool:
        self.last_connect_error = ""
        if serial is None:
            self.last_connect_error = "pyserial is not installed"
            return False
        if not self.enabled or not self.port:
            self.last_connect_error = "Port not set or connection disabled in config"
            return False
        if self.serial_connection is not None:
            try:
                if getattr(self.serial_connection, "is_open", False):
                    self.serial_connection.close()
            except Exception:
                pass
            self.serial_connection = None
        self.connected = False
        tmo = max(1.0, float(getattr(self, "timeout", 1.0)))
        # Busy COM: retry with backoff (Windows often needs time after another app or our own disconnect).
        max_attempts = 5
        for attempt in range(max_attempts):
            last_ex = None
            self.serial_connection = None
            for port_try in iter_serial_port_names_for_open(self.port):
                try:
                    self.serial_connection = serial.Serial(
                        port=port_try,
                        baudrate=self.baudrate,
                        timeout=tmo,
                        bytesize=serial.EIGHTBITS,
                        parity=serial.PARITY_NONE,
                        stopbits=serial.STOPBITS_ONE,
                        write_timeout=tmo,
                    )
                    last_ex = None
                    break
                except Exception as ex:
                    last_ex = ex
                    self.serial_connection = None
            if last_ex is not None or self.serial_connection is None:
                self.last_connect_error = _friendly_actuator_open_error(self.port, last_ex) if last_ex else "Serial open failed"
                self.connected = False
                if attempt >= max_attempts - 1:
                    break
                busy = _is_serial_access_denied(last_ex) if last_ex else False
                if busy:
                    time.sleep(0.6 + 0.5 * attempt)
                elif attempt == 0:
                    time.sleep(1.0)
                else:
                    break
                continue
            try:
                time.sleep(2.0)
                try:
                    self.serial_connection.reset_input_buffer()
                except Exception:
                    pass
                time.sleep(0.1)
                self.connected = True
                return True
            except Exception as ex:
                self.last_connect_error = _friendly_actuator_open_error(self.port, ex)
                try:
                    if self.serial_connection is not None and getattr(self.serial_connection, "is_open", False):
                        self.serial_connection.close()
                except Exception:
                    pass
                self.serial_connection = None
                if attempt >= max_attempts - 1:
                    break
                if _is_serial_access_denied(ex):
                    time.sleep(0.6 + 0.5 * attempt)
                elif attempt == 0:
                    time.sleep(1.0)
                else:
                    break
        return False

    def disconnect(self) -> None:
        if self.serial_connection is not None:
            try:
                if getattr(self.serial_connection, "is_open", False):
                    self.serial_connection.close()
            except Exception:
                pass
        self.serial_connection = None
        self.connected = False

    def is_connected(self) -> bool:
        return bool(self.connected and self.serial_connection and self.serial_connection.is_open)

    def ping(self) -> None:
        """
        Lightweight health check without sending protocol bytes.
        A bare newline every poll was corrupting line-based Arduino command parsing (movea/homea).
        """
        if self.serial_connection is None or not self.serial_connection.is_open:
            raise IOError("Actuator not connected")
        try:
            _ = self.serial_connection.in_waiting
        except (OSError, ValueError, AttributeError) as e:
            raise IOError("Actuator not responding (device may be off or disconnected)") from e

    @staticmethod
    def estimate_move_seconds(distance_mm: float) -> float:
        """Rough motion time for UI status (not used to block serial I/O)."""
        d = abs(float(distance_mm))
        return max(3.0, min(45.0, 2.0 + d * 0.12))

    def send_command(
        self,
        command: str,
        read_timeout: Optional[float] = None,
        *,
        wait_time: Optional[float] = None,
    ) -> list:
        """
        ser.write((command + "\\n").encode()); poll readline until wait_time (GUI reference) or read_timeout elapses.
        If neither is set, uses ACTUATOR_SEND_READ_TIMEOUT_SEC for quick return (e.g. tests).
        """
        if self.serial_connection is None or not self.serial_connection.is_open:
            raise IOError("Actuator not connected")
        if wait_time is not None:
            rt = float(wait_time)
            poll = 0.05
        elif read_timeout is not None:
            rt = float(read_timeout)
            poll = 0.02
        else:
            rt = ACTUATOR_SEND_READ_TIMEOUT_SEC
            poll = 0.02
        try:
            self.serial_connection.write((str(command) + "\n").encode())
            try:
                self.serial_connection.flush()
            except Exception:
                pass
            start = time.time()
            response_lines = []
            while time.time() - start < rt:
                if self.serial_connection.in_waiting:
                    line = self.serial_connection.readline().decode(errors="ignore").strip()
                    response_lines.append(line)
                else:
                    time.sleep(poll)
            return response_lines
        except Exception as e:
            raise IOError("Actuator communication failed (device may be off or disconnected)") from e

    def home_a(self) -> bool:
        if not self.is_connected():
            return False
        self.send_command("homea", wait_time=2.0)
        return True

    def home_b(self) -> bool:
        if not self.is_connected():
            return False
        self.send_command("homeb", wait_time=2.0)
        return True

    def home_both(self) -> bool:
        if not self.is_connected():
            return False
        self.send_command("HOME BOTH", wait_time=3.0)
        return True

    def move_a(self, distance_mm: float) -> bool:
        if not self.is_connected() or distance_mm <= 0:
            return False
        if distance_mm == int(distance_mm):
            distance_str = str(int(distance_mm))
        else:
            distance_str = str(distance_mm)
        self.send_command("movea " + distance_str, wait_time=3.0)
        return True

    def move_b(self, distance_mm: float) -> bool:
        if not self.is_connected() or distance_mm <= 0:
            return False
        if distance_mm == int(distance_mm):
            distance_str = str(int(distance_mm))
        else:
            distance_str = str(distance_mm)
        self.send_command("moveb " + distance_str, wait_time=3.0)
        return True
