"""
Arduino-based Actuator Controller

Instrument: Arduino (or compatible) controlling actuators. Commands: homea, homeb, HOME BOTH, movea <mm>, moveb <mm>.
movea/moveb <mm> are absolute distance from the mechanical home reference (mm). The GUI worker stacks each Move click
into that total until Home resets the axis counter; other callers (e.g. tests) send absolute mm directly on the connection.
Connection: Serial (COM port), 115200 baud default. Config from instrument_config.ini [Actuators] or direct port.
Details: Send text commands with \\n; read response lines. Arduino may reset on serial open (2 s delay).
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


class ActuatorConnection:
    """Arduino actuator connection via COM. Connect to given port; then home/move A/B."""

    def __init__(self, config_file='instrument_config.ini', instrument_name='Actuators', port=None, baudrate=None):
        self.instrument_name = instrument_name
        self.serial_connection = None
        self.connected = False
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
        if not self.enabled or not self.port or serial is None:
            return False
        if self.serial_connection and self.serial_connection.is_open:
            try:
                self.serial_connection.close()
            except Exception:
                pass
            self.serial_connection = None
        timeout_sec = max(2.0, float(getattr(self, "timeout", 1.0)))
        for attempt in range(2):
            try:
                self.serial_connection = serial.Serial(
                    port=self.port, baudrate=self.baudrate, timeout=timeout_sec,
                    bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE,
                    write_timeout=timeout_sec
                )
                time.sleep(2.0)
                self.serial_connection.reset_input_buffer()
                self.serial_connection.reset_output_buffer()
                time.sleep(0.2)
                self.connected = True
                return True
            except Exception:
                self.connected = False
                if self.serial_connection and getattr(self.serial_connection, "is_open", False):
                    try:
                        self.serial_connection.close()
                    except Exception:
                        pass
                self.serial_connection = None
                if attempt == 0:
                    time.sleep(1.0)
        return False

    def disconnect(self) -> None:
        if self.serial_connection and self.serial_connection.is_open:
            try:
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

    def send_command(self, command: str, read_timeout: Optional[float] = None) -> list:
        """
        Write command and return quickly. Only waits up to read_timeout to collect any immediate serial lines.
        """
        if self.serial_connection is None or not self.serial_connection.is_open:
            raise IOError("Actuator not connected")
        rt = ACTUATOR_SEND_READ_TIMEOUT_SEC if read_timeout is None else float(read_timeout)
        try:
            self.serial_connection.write((command + "\n").encode())
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
                    time.sleep(0.02)
            return response_lines
        except Exception as e:
            raise IOError("Actuator communication failed (device may be off or disconnected)") from e

    def home_a(self) -> bool:
        if not self.is_connected():
            return False
        self.send_command("homea")
        return True

    def home_b(self) -> bool:
        if not self.is_connected():
            return False
        self.send_command("homeb")
        return True

    def home_both(self) -> bool:
        if not self.is_connected():
            return False
        self.send_command("HOME BOTH")
        return True

    def move_a(self, distance_mm: float) -> bool:
        if not self.is_connected() or distance_mm <= 0:
            return False
        distance_str = str(int(round(distance_mm))) if abs(distance_mm - round(distance_mm)) < 1e-6 else str(distance_mm)
        self.send_command("movea " + distance_str)
        return True

    def move_b(self, distance_mm: float) -> bool:
        if not self.is_connected() or distance_mm <= 0:
            return False
        distance_str = str(int(round(distance_mm))) if abs(distance_mm - round(distance_mm)) < 1e-6 else str(distance_mm)
        self.send_command("moveb " + distance_str)
        return True
