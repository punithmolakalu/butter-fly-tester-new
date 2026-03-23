"""
Arroyo TEC/Laser Controller

Instrument: Arroyo Instruments TEC and laser diode controller (SCPI).
Connection: Serial (COM port), 38400 baud, 8N1. Termination: \\r.
Details: Laser channel (LAS:), TEC channel (TEC:), temperature/current setpoints and limits.
         Uses SCPI from Arroyo Computer Interfacing Manual. Config from instrument_config.ini or direct port.
"""
from __future__ import annotations

import configparser
import os
import re
import threading
import time
from typing import List

try:
    import serial  # type: ignore[reportMissingImports]
    from serial.tools import list_ports  # type: ignore[reportMissingImports]
except ImportError:
    serial = None
    list_ports = None

# ----- Connection: COM scan -----
def scan_available_ports() -> List[str]:
    """Return list of available COM port names, naturally sorted (e.g. COM2, COM10)."""
    if list_ports is None:
        return []
    try:
        ports = list_ports.comports()
        names = [p.device for p in ports]
        def key(s):
            m = re.match(r"^(\D*)(\d+)(.*)$", s)
            return (m.group(1).lower(), int(m.group(2)), m.group(3)) if m else (s.lower(), 0, "")
        return sorted(names, key=key)
    except Exception:
        return []

# ----- Instrument: SCPI command sets -----
COMMON = {
    "IDN": "*IDN?", "RESET": "*RST", "CLEAR_STATUS": "*CLS", "OPC": "*OPC", "OPC_QUERY": "*OPC?",
    "STATUS_BYTE": "*STB?", "ERROR": "ERR?", "ERROR_STRING": "ERRSTR?", "LOCAL": "LOCAL",
}
LASER = {
    "CHANNEL_SET": "LAS:CHAN {}", "CHANNEL_QUERY": "LAS:CHAN?", "MODE_QUERY": "LAS:MODE?",
    "OUTPUT_ON": "LAS:OUT 1", "OUTPUT_OFF": "LAS:OUT 0", "OUTPUT_QUERY": "LAS:OUT?",
    "SET_CURRENT": "LAS:LDI {}", "GET_CURRENT": "LAS:LDI?", "GET_CURRENT_SET": "LAS:SET:LDI?",
    "CURRENT_LIMIT": "LAS:LIM:LDI {}", "CURRENT_LIMIT_QUERY": "LAS:LIM:LDI?",
    "GET_VOLTAGE": "LAS:LDV?", "VOLTAGE_LIMIT_QUERY": "LAS:LIM:LDV?",
    # Monitor diode / photodiode readings
    "GET_MONITOR_DIODE_POWER": "LAS:MDP?",
    "GET_MONITOR_DIODE_CURRENT": "LAS:MDI?",
}
TEC = {
    "CHANNEL_SET": "TEC:CHAN {}", "CHANNEL_QUERY": "TEC:CHAN?", "MODE_QUERY": "TEC:MODE?",
    "OUTPUT_ON": "TEC:OUT 1", "OUTPUT_OFF": "TEC:OUT 0", "OUTPUT_QUERY": "TEC:OUT?",
    "SET_TEMP": "TEC:T {}", "GET_TEMP": "TEC:T?", "GET_TEMP_SET": "TEC:SET:T?",
    "TEMP_HIGH_LIMIT": "TEC:LIM:THI {}", "TEMP_HIGH_LIMIT_QUERY": "TEC:LIM:THI?",
    "GET_CURRENT": "TEC:ITE?", "CURRENT_LIMIT": "TEC:LIM:ITE {}", "CURRENT_LIMIT_QUERY": "TEC:LIM:ITE?",
}


def _format_cmd(cmd: str, *args) -> str:
    return cmd.format(*args)


class ArroyoConnection:
    """Arroyo TEC/Laser connection via COM. Connect to given port; then query/set temp, current, laser."""

    def __init__(self, config_file='instrument_config.ini', instrument_name='Arroyo', port=None):
        self.serial_connection = None
        self.connected = False
        self.instrument_name = instrument_name
        self.baudrate = 38400
        if port and str(port).strip():
            self.port = str(port).strip()
            self.timeout = 0.5
            self.enabled = True
        else:
            if not os.path.isabs(config_file):
                config_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), config_file)
            self.config = configparser.ConfigParser()
            if os.path.exists(config_file):
                self.config.read(config_file)
            try:
                self.port = self.config.get(instrument_name, 'port', fallback='COM1').strip() or 'COM1'
                self.timeout = float(self.config.get(instrument_name, 'timeout', fallback=0.5))
                self.enabled = self.config.getboolean(instrument_name, 'enabled', fallback=True)
            except Exception:
                self.port = 'COM1'
                self.timeout = 0.5
                self.enabled = True
        # One thread at a time on serial (GUI poll + LIV test thread share this connection).
        self._serial_lock = threading.RLock()

    def connect(self) -> bool:
        if not self.enabled or not self.port or not str(self.port).strip() or serial is None:
            return False
        if self.serial_connection and self.serial_connection.is_open:
            try:
                self.serial_connection.close()
            except Exception:
                pass
            self.serial_connection = None
        timeout_sec = max(1.0, float(getattr(self, "timeout", 0.5)))
        for attempt in range(2):
            try:
                self.serial_connection = serial.Serial(
                    port=self.port, baudrate=self.baudrate, timeout=timeout_sec,
                    bytesize=serial.EIGHTBITS, parity=serial.PARITY_NONE, stopbits=serial.STOPBITS_ONE,
                    write_timeout=timeout_sec, inter_byte_timeout=0.1
                )
                time.sleep(0.5)
                self.serial_connection.reset_input_buffer()
                self.serial_connection.reset_output_buffer()
                time.sleep(0.1)
                self.connected = True
                self.clear_status()
                time.sleep(0.15)
                self.set_remote_mode()
                time.sleep(0.15)
                self.write_command('LAS:CHAN 1')
                time.sleep(0.1)
                self.write_command('TEC:CHAN 1')
                time.sleep(0.1)
                # Verify device responds (not just port open)
                try:
                    if self.read_temp() is None:
                        raise IOError("No response from Arroyo")
                except Exception:
                    self.connected = False
                    if self.serial_connection and self.serial_connection.is_open:
                        try:
                            self.serial_connection.close()
                        except Exception:
                            pass
                    self.serial_connection = None
                    return False
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
                    time.sleep(0.5)
        return False

    def disconnect(self) -> None:
        with getattr(self, "_serial_lock", threading.RLock()):
            if self.serial_connection and self.serial_connection.is_open:
                try:
                    self.serial_connection.close()
                except Exception:
                    pass
            self.serial_connection = None
            self.connected = False

    def is_connected(self) -> bool:
        return bool(self.connected and self.serial_connection and self.serial_connection.is_open)

    def write_command(self, command: str) -> bool:
        with self._serial_lock:
            if not self.is_connected():
                return False
            command = command.strip()
            if not command.endswith('\r'):
                command += '\r'
            conn = self.serial_connection
            if conn is None:
                return False
            try:
                conn.reset_input_buffer()
                conn.write(command.encode('utf-8'))
                conn.flush()
                return True
            except Exception:
                return False

    def _readline_r(self, timeout=0.5):
        conn = self.serial_connection
        if conn is None:
            return None
        eol = (b'\r', b'\n')
        line = bytearray()
        orig_timeout = conn.timeout
        conn.timeout = timeout
        try:
            while True:
                c = conn.read(1)
                if c:
                    if c in eol:
                        break
                    line.extend(c)
                else:
                    # Timeout or device off: no data. Raise so worker can mark disconnected.
                    conn.timeout = orig_timeout
                    raise IOError("Arroyo read timeout (device may be off or disconnected)")
            conn.timeout = orig_timeout
            return bytes(line).decode('utf-8', errors='ignore').strip() if line else None
        except Exception:
            conn.timeout = orig_timeout
            raise

    def read_response(self, timeout=None):
        with self._serial_lock:
            if not self.is_connected():
                return None
            tout = timeout if timeout is not None else 0.4
            try:
                return self._readline_r(timeout=tout)
            except Exception:
                return None

    def query(self, command: str):
        """Single locked transaction so GUI poll and LIV thread cannot interleave bytes."""
        with self._serial_lock:
            if not self.is_connected():
                return None
            command = (command or "").strip()
            if not command.endswith("\r"):
                command += "\r"
            conn = self.serial_connection
            if conn is None:
                return None
            try:
                conn.reset_input_buffer()
                conn.write(command.encode("utf-8"))
                conn.flush()
            except Exception:
                return None
            time.sleep(0.06)
            try:
                return self._readline_r(timeout=0.4)
            except Exception:
                return None

    def identify(self): return self.query(COMMON["IDN"])
    def reset(self): return self.write_command(COMMON["RESET"])
    def clear_status(self): return self.write_command(COMMON["CLEAR_STATUS"])
    def get_error(self): return self.query(COMMON["ERROR"])

    def read_temp(self):
        response = self.query(TEC["GET_TEMP"])
        if response:
            try:
                return float(response.strip())
            except (ValueError, TypeError):
                return None
        return None

    def read_set_temp(self):
        response = self.query(TEC["GET_TEMP_SET"])
        try:
            return float(response) if response else None
        except (ValueError, TypeError):
            return None

    def set_temp(self, value) -> bool:
        try:
            v = float(value)
            return self.write_command(_format_cmd(TEC["SET_TEMP"], v))
        except (TypeError, ValueError):
            return False

    def read_THI_limit(self):
        for q in (TEC["TEMP_HIGH_LIMIT_QUERY"], "TEC:LIM:THI?", "TEC:LIM:TEMP:HI?"):
            response = self.query(q)
            if response is not None and str(response).strip():
                try:
                    s = str(response).strip().replace(",", ".").split()
                    if s:
                        return float(s[0])
                except (ValueError, TypeError):
                    pass
        return None

    def set_THI_limit(self, value) -> bool:
        try:
            v = float(value)
            ok = self.write_command(_format_cmd(TEC["TEMP_HIGH_LIMIT"], v))
            if ok:
                time.sleep(0.05)
            return ok
        except (TypeError, ValueError):
            return False

    def read_output(self):
        response = self.query(TEC["OUTPUT_QUERY"])
        try:
            return int(response) if response else None
        except (ValueError, TypeError):
            if response and response.strip().upper() in ['ON', '1']:
                return 1
            if response and response.strip().upper() in ['OFF', '0']:
                return 0
            return None

    def set_output(self, value) -> bool:
        return self.write_command(TEC["OUTPUT_ON"] if value else TEC["OUTPUT_OFF"])

    def read_current(self):
        response = self.query(TEC["GET_CURRENT"])
        try:
            return float(response) if response else None
        except (ValueError, TypeError):
            return None

    def set_tec_current_setpoint(self, value) -> bool:
        try:
            v = float(value)
            ok = self.write_command("TEC:ITE {:.4f}".format(v))
            if ok:
                time.sleep(0.05)
            return ok
        except (TypeError, ValueError):
            return False

    def set_tec_current_limit(self, value) -> bool:
        try:
            v = float(value)
            ok = self.write_command("TEC:LIM:ITE {:.4f}".format(v))
            if ok:
                time.sleep(0.05)
            return ok
        except (TypeError, ValueError):
            return False

    def read_tec_current_limit(self):
        for q in (TEC["CURRENT_LIMIT_QUERY"], "TEC:LIM:ITE?"):
            response = self.query(q)
            if response is not None and str(response).strip():
                try:
                    s = str(response).strip().replace(",", ".").split()
                    if s:
                        return float(s[0])
                except (ValueError, TypeError):
                    pass
        return None

    def laser_read_current(self):
        response = self.query(LASER["GET_CURRENT"])
        if response:
            try:
                return float(str(response).strip())
            except (ValueError, TypeError):
                pass
        return None

    def laser_read_set_current(self):
        response = self.query(LASER["GET_CURRENT_SET"])
        try:
            return float(response) if response else None
        except (ValueError, TypeError):
            return None

    def laser_set_current(self, value) -> bool:
        try:
            v = float(value)
            s = str(int(round(v))) if abs(v - round(v)) < 1e-6 else str(v)
            return self.write_command("LAS:LDI " + s)
        except (TypeError, ValueError):
            return False

    def laser_read_voltage(self):
        response = self.query(LASER["GET_VOLTAGE"])
        if response is None:
            return None
        try:
            return float(str(response).strip())
        except (ValueError, TypeError):
            return None

    def laser_read_monitor_diode_current(self):
        response = self.query(LASER["GET_MONITOR_DIODE_CURRENT"])
        if response is None:
            return None
        try:
            s = str(response).strip().replace(",", ".")
            m = re.search(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", s)
            return float(m.group(0)) if m else None
        except Exception:
            return None

    def laser_read_monitor_diode_power(self):
        response = self.query(LASER["GET_MONITOR_DIODE_POWER"])
        if response is None:
            return None
        try:
            s = str(response).strip().replace(",", ".")
            m = re.search(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", s)
            return float(m.group(0)) if m else None
        except Exception:
            return None

    def laser_read_monitor_diode_power(self):
        """Read monitor diode power (PD) from the laser controller (SCPI LASER:MDP?)."""
        try:
            response = self.query(LASER["GET_MONITOR_DIODE_POWER"])
            if response is None:
                return None
            s = str(response).strip()
            # Be tolerant if the instrument returns units or extra characters.
            m = re.search(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", s)
            return float(m.group(0)) if m else None
        except Exception:
            return None

    def laser_read_monitor_diode_current(self):
        """Read monitor diode current (PD) from the laser controller (SCPI LASER:MDI?)."""
        try:
            response = self.query(LASER["GET_MONITOR_DIODE_CURRENT"])
            if response is None:
                return None
            s = str(response).strip()
            # Be tolerant if the instrument returns units or extra characters.
            m = re.search(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", s)
            return float(m.group(0)) if m else None
        except Exception:
            return None

    def laser_read_output(self):
        response = self.query(LASER["OUTPUT_QUERY"])
        try:
            return int(response) if response else None
        except (ValueError, TypeError):
            if response and response.strip().upper() in ['ON', '1']:
                return 1
            if response and response.strip().upper() in ['OFF', '0']:
                return 0
            return None

    def laser_set_output(self, value) -> bool:
        return self.write_command(LASER["OUTPUT_ON"] if value else LASER["OUTPUT_OFF"])

    def laser_read_current_limit(self):
        response = self.query(LASER["CURRENT_LIMIT_QUERY"])
        try:
            return float(response) if response else None
        except (ValueError, TypeError):
            return None

    def laser_set_current_limit(self, value) -> bool:
        try:
            v = float(value)
            s = str(int(round(v))) if abs(v - round(v)) < 1e-6 else str(v)
            return self.write_command("LAS:LIM:LDI " + s)
        except (TypeError, ValueError):
            return False

    def set_remote_mode(self) -> bool:
        if not self.is_connected():
            return False
        if self.write_command('COMM:SETWHILERMT 1'):
            time.sleep(0.1)
            return True
        return False

    def set_local_mode(self) -> bool:
        try:
            self.write_command(COMMON["LOCAL"])
            time.sleep(0.1)
            return True
        except Exception:
            return False
    def read_THI_limit(self):
        for q in (TEC["TEMP_HIGH_LIMIT_QUERY"], "TEC:LIM:THI?", "TEC:LIM:TEMP:HI?"):
            response = self.query(q)
            if response is not None and str(response).strip():
                try:
                    s = str(response).strip().replace(",", ".").split()
                    if s:
                        return float(s[0])
                except (ValueError, TypeError):
                    pass
        return None

    def set_THI_limit(self, value) -> bool:
        try:
            v = float(value)
            ok = self.write_command(_format_cmd(TEC["TEMP_HIGH_LIMIT"], v))
            if ok:
                time.sleep(0.05)
            return ok
        except (TypeError, ValueError):
            return False

    def read_output(self):
        response = self.query(TEC["OUTPUT_QUERY"])
        try:
            return int(response) if response else None
        except (ValueError, TypeError):
            if response and response.strip().upper() in ['ON', '1']:
                return 1
            if response and response.strip().upper() in ['OFF', '0']:
                return 0
            return None

    def set_output(self, value) -> bool:
        return self.write_command(TEC["OUTPUT_ON"] if value else TEC["OUTPUT_OFF"])

    def read_current(self):
        response = self.query(TEC["GET_CURRENT"])
        try:
            return float(response) if response else None
        except (ValueError, TypeError):
            return None

    def set_tec_current_setpoint(self, value) -> bool:
        try:
            v = float(value)
            ok = self.write_command("TEC:ITE {:.4f}".format(v))
            if ok:
                time.sleep(0.05)
            return ok
        except (TypeError, ValueError):
            return False

    def set_tec_current_limit(self, value) -> bool:
        try:
            v = float(value)
            ok = self.write_command("TEC:LIM:ITE {:.4f}".format(v))
            if ok:
                time.sleep(0.05)
            return ok
        except (TypeError, ValueError):
            return False

    def read_tec_current_limit(self):
        for q in (TEC["CURRENT_LIMIT_QUERY"], "TEC:LIM:ITE?"):
            response = self.query(q)
            if response is not None and str(response).strip():
                try:
                    s = str(response).strip().replace(",", ".").split()
                    if s:
                        return float(s[0])
                except (ValueError, TypeError):
                    pass
        return None

    def laser_read_current(self):
        for cmd in (LASER["GET_CURRENT"], "LAS:I?"):
            response = self.query(cmd)
            if response:
                try:
                    return float(response.strip())
                except (ValueError, TypeError):
                    pass
        return None

    def laser_read_set_current(self):
        response = self.query(LASER["GET_CURRENT_SET"])
        try:
            return float(response) if response else None
        except (ValueError, TypeError):
            return None

    def laser_set_current(self, value) -> bool:
        try:
            v = float(value)
            s = str(int(round(v))) if abs(v - round(v)) < 1e-6 else str(v)
            return self.write_command("LAS:LDI " + s)
        except (TypeError, ValueError):
            return False

    def laser_read_voltage(self):
        # Try both short and long SCPI forms across firmware variants.
        for cmd in (LASER.get("GET_VOLTAGE"), "LAS:LDV?", "LASER:LDV?"):
            if not cmd:
                continue
            response = self.query(cmd)
            if response is not None and str(response).strip():
                try:
                    return float(str(response).strip())
                except (ValueError, TypeError):
                    pass
        return None

    def laser_read_monitor_diode_power(self):
        """Read monitor-diode power from Arroyo (if supported by model/firmware)."""
        for cmd in ("LAS:MDP?", "LASER:MDP?", "LAS:IPD?", "LASER:IPD?"):
            response = self.query(cmd)
            if response is not None and str(response).strip():
                try:
                    s = str(response).strip().replace(",", ".")
                    m = re.search(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", s)
                    if m:
                        return float(m.group(0))
                except Exception:
                    pass
        return None

    def laser_read_monitor_diode_current(self):
        """Read monitor-diode current from Arroyo (if supported by model/firmware)."""
        for cmd in ("LAS:MDI?", "LASER:MDI?", "LAS:IPD?", "LASER:IPD?"):
            response = self.query(cmd)
            if response is not None and str(response).strip():
                try:
                    s = str(response).strip().replace(",", ".")
                    m = re.search(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", s)
                    if m:
                        return float(m.group(0))
                except Exception:
                    pass
        return None

    def laser_read_output(self):
        response = self.query(LASER["OUTPUT_QUERY"])
        try:
            return int(response) if response else None
        except (ValueError, TypeError):
            if response and response.strip().upper() in ['ON', '1']:
                return 1
            if response and response.strip().upper() in ['OFF', '0']:
                return 0
            return None

    def laser_set_output(self, value) -> bool:
        return self.write_command(LASER["OUTPUT_ON"] if value else LASER["OUTPUT_OFF"])

    def laser_read_current_limit(self):
        response = self.query(LASER["CURRENT_LIMIT_QUERY"])
        try:
            return float(response) if response else None
        except (ValueError, TypeError):
            return None

    def laser_set_current_limit(self, value) -> bool:
        try:
            v = float(value)
            s = str(int(round(v))) if abs(v - round(v)) < 1e-6 else str(v)
            return self.write_command("LAS:LIM:LDI " + s)
        except (TypeError, ValueError):
            return False

    def set_remote_mode(self) -> bool:
        if not self.is_connected():
            return False
        if self.write_command('COMM:SETWHILERMT 1'):
            time.sleep(0.1)
            return True
        return False

    def set_local_mode(self) -> bool:
        try:
            self.write_command(COMMON["LOCAL"])
            time.sleep(0.1)
            return True
        except Exception:
            return False
    def read_THI_limit(self):
        for q in (TEC["TEMP_HIGH_LIMIT_QUERY"], "TEC:LIM:THI?", "TEC:LIM:TEMP:HI?"):
            response = self.query(q)
            if response is not None and str(response).strip():
                try:
                    s = str(response).strip().replace(",", ".").split()
                    if s:
                        return float(s[0])
                except (ValueError, TypeError):
                    pass
        return None

    def set_THI_limit(self, value) -> bool:
        try:
            v = float(value)
            ok = self.write_command(_format_cmd(TEC["TEMP_HIGH_LIMIT"], v))
            if ok:
                time.sleep(0.05)
            return ok
        except (TypeError, ValueError):
            return False

    def read_output(self):
        response = self.query(TEC["OUTPUT_QUERY"])
        try:
            return int(response) if response else None
        except (ValueError, TypeError):
            if response and response.strip().upper() in ['ON', '1']:
                return 1
            if response and response.strip().upper() in ['OFF', '0']:
                return 0
            return None

    def set_output(self, value) -> bool:
        return self.write_command(TEC["OUTPUT_ON"] if value else TEC["OUTPUT_OFF"])

    def read_current(self):
        response = self.query(TEC["GET_CURRENT"])
        try:
            return float(response) if response else None
        except (ValueError, TypeError):
            return None

    def set_tec_current_setpoint(self, value) -> bool:
        try:
            v = float(value)
            ok = self.write_command("TEC:ITE {:.4f}".format(v))
            if ok:
                time.sleep(0.05)
            return ok
        except (TypeError, ValueError):
            return False

    def set_tec_current_limit(self, value) -> bool:
        try:
            v = float(value)
            ok = self.write_command("TEC:LIM:ITE {:.4f}".format(v))
            if ok:
                time.sleep(0.05)
            return ok
        except (TypeError, ValueError):
            return False

    def read_tec_current_limit(self):
        for q in (TEC["CURRENT_LIMIT_QUERY"], "TEC:LIM:ITE?"):
            response = self.query(q)
            if response is not None and str(response).strip():
                try:
                    s = str(response).strip().replace(",", ".").split()
                    if s:
                        return float(s[0])
                except (ValueError, TypeError):
                    pass
        return None

    def laser_read_current(self):
        for cmd in (LASER["GET_CURRENT"], "LAS:I?"):
            response = self.query(cmd)
            if response:
                try:
                    return float(response.strip())
                except (ValueError, TypeError):
                    pass
        return None

    def laser_read_set_current(self):
        response = self.query(LASER["GET_CURRENT_SET"])
        try:
            return float(response) if response else None
        except (ValueError, TypeError):
            return None

    def laser_set_current(self, value) -> bool:
        try:
            v = float(value)
            s = str(int(round(v))) if abs(v - round(v)) < 1e-6 else str(v)
            return self.write_command("LAS:LDI " + s)
        except (TypeError, ValueError):
            return False

    def laser_read_voltage(self):
        response = self.query(LASER["GET_VOLTAGE"])
        try:
            return float(response) if response else None
        except (ValueError, TypeError):
            return None

    def laser_read_output(self):
        response = self.query(LASER["OUTPUT_QUERY"])
        try:
            return int(response) if response else None
        except (ValueError, TypeError):
            if response and response.strip().upper() in ['ON', '1']:
                return 1
            if response and response.strip().upper() in ['OFF', '0']:
                return 0
            return None

    def laser_set_output(self, value) -> bool:
        return self.write_command(LASER["OUTPUT_ON"] if value else LASER["OUTPUT_OFF"])

    def laser_read_current_limit(self):
        response = self.query(LASER["CURRENT_LIMIT_QUERY"])
        try:
            return float(response) if response else None
        except (ValueError, TypeError):
            return None

    def laser_set_current_limit(self, value) -> bool:
        try:
            v = float(value)
            s = str(int(round(v))) if abs(v - round(v)) < 1e-6 else str(v)
            return self.write_command("LAS:LIM:LDI " + s)
        except (TypeError, ValueError):
            return False

    def set_remote_mode(self) -> bool:
        if not self.is_connected():
            return False
        if self.write_command('COMM:SETWHILERMT 1'):
            time.sleep(0.1)
            return True
        return False

    def set_local_mode(self) -> bool:
        try:
            self.write_command(COMMON["LOCAL"])
            time.sleep(0.1)
            return True
        except Exception:
            return False
