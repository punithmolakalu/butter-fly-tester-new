"""
Software-only instrument stand-ins for development without hardware.

Used when simulation flags are on (see simulation_config.py). Duck-type the real connection classes.
"""
from __future__ import annotations

import math
import threading
import time
from typing import Any, Callable, Optional, Tuple

# ----- Arroyo -----
class ArroyoSimulationConnection:
    is_simulation = True

    def __init__(self, port: Any = None, instrument_name: str = "Arroyo"):
        self.port = str(port or "SIM").strip() or "SIM"
        self.instrument_name = instrument_name
        self.serial_connection = object()
        self.connected = False
        self.enabled = True
        self.timeout = 0.5
        self.baudrate = 38400
        self._tec_set = 25.0
        self._tec_temp = 25.0
        self._tec_out = 1
        self._las_set_ma = 100.0
        self._las_ma = 0.0
        self._las_v = 2.1
        self._las_out = 0
        self._las_lim_ma = 500.0
        self._thi_lim = 80.0
        self._serial_lock = threading.RLock()

    def connect(self) -> bool:
        self.connected = True
        return True

    def disconnect(self) -> None:
        self.connected = False

    def is_connected(self) -> bool:
        return bool(self.connected)

    def clear_status(self) -> bool:
        return True

    def write_command(self, cmd: str) -> bool:
        return bool(self.connected)

    def query(self, cmd: str) -> Optional[str]:
        if not self.connected:
            return None
        c = str(cmd or "").strip().upper()
        if "TEC:V" in c or c == "TEC:V?":
            return "12.0"
        return "OK"

    def read_temp(self) -> Optional[float]:
        return float(self._tec_temp) if self.connected else None

    def read_set_temp(self) -> Optional[float]:
        return float(self._tec_set) if self.connected else None

    def read_current(self) -> Optional[float]:
        return 0.5 if self.connected else None

    def read_output(self) -> Optional[int]:
        return int(self._tec_out) if self.connected else None

    def read_THI_limit(self) -> Optional[float]:
        return float(self._thi_lim) if self.connected else None

    def set_temp(self, t: float) -> bool:
        if not self.connected:
            return False
        self._tec_set = float(t)
        self._tec_temp = float(t) + 0.02 * math.sin(time.time())
        return True

    def set_output(self, v: int) -> bool:
        if not self.connected:
            return False
        self._tec_out = 1 if v else 0
        return True

    def set_THI_limit(self, lim: float) -> bool:
        if not self.connected:
            return False
        self._thi_lim = float(lim)
        return True

    def laser_read_current(self) -> Optional[float]:
        if not self.connected:
            return None
        if self._las_out:
            self._las_ma = self._las_set_ma + 0.5 * math.sin(time.time())
        else:
            self._las_ma = 0.0
        return float(self._las_ma)

    def laser_read_set_current(self) -> Optional[float]:
        return float(self._las_set_ma) if self.connected else None

    def laser_read_voltage(self) -> Optional[float]:
        return float(self._las_v) if self.connected else None

    def laser_read_current_limit(self) -> Optional[float]:
        return float(self._las_lim_ma) if self.connected else None

    def laser_read_output(self) -> Optional[int]:
        return int(self._las_out) if self.connected else None

    def laser_set_current(self, ma: float) -> bool:
        if not self.connected:
            return False
        self._las_set_ma = float(ma)
        return True

    def laser_set_current_limit(self, ma: float) -> bool:
        if not self.connected:
            return False
        self._las_lim_ma = float(ma)
        return True

    def laser_set_output(self, v: int) -> bool:
        if not self.connected:
            return False
        self._las_out = 1 if v else 0
        return True


# ----- Actuator -----
class ActuatorSimulationConnection:
    is_simulation = True

    def __init__(self, port: str = "SIM", baudrate: int = 115200):
        self.port = str(port or "SIM").strip() or "SIM"
        self.baudrate = baudrate
        self.serial_connection = object()
        self.connected = False
        self.enabled = True
        self.timeout = 1.0
        self.instrument_name = "Actuators"

    def connect(self) -> bool:
        self.connected = True
        return True

    def disconnect(self) -> None:
        self.connected = False

    def is_connected(self) -> bool:
        return bool(self.connected)

    def ping(self) -> None:
        if not self.connected:
            raise IOError("Actuator not connected")

    def home_a(self) -> bool:
        return self.is_connected()

    def home_b(self) -> bool:
        return self.is_connected()

    def home_both(self) -> bool:
        return self.is_connected()

    def move_a(self, distance_mm: float) -> bool:
        return self.is_connected() and float(distance_mm) > 0

    def move_b(self, distance_mm: float) -> bool:
        return self.is_connected() and float(distance_mm) > 0


# ----- Gentec -----
class GentecSimulationConnection:
    is_simulation = True

    def __init__(self, port: str = "SIM"):
        self.port = str(port or "SIM").strip() or "SIM"
        self.serial_connection = object()
        self.connected = False
        self.enabled = True
        self.baudrate = 115200
        self.timeout = 0.5
        self.instrument_name = "Gentec"

    def connect(self) -> bool:
        self.connected = True
        return True

    def disconnect(self) -> None:
        self.connected = False

    def is_connected(self) -> bool:
        return bool(self.connected)

    def get_value_mw(self) -> Optional[float]:
        if not self.connected:
            return None
        return 42.0 + 0.1 * math.sin(time.time() * 0.5)


# ----- Thorlabs -----
class ThorlabsPowermeterSimulationConnection:
    is_simulation = True

    def __init__(self, resource: str = "SIM"):
        self.resource = str(resource or "SIM").strip() or "SIM"
        self.serial_number = "SIM"
        self.enabled = True
        self.timeout_s = 1.0
        self._connected = False
        self._phot_mode_set = True
        self._last_wav_nm: Optional[float] = None

    def connect(self) -> bool:
        self._connected = True
        return True

    def disconnect(self) -> None:
        self._connected = False
        self._last_wav_nm = None

    def is_connected(self) -> bool:
        return bool(self._connected)

    def set_photodiode_mode(self) -> bool:
        return bool(self._connected)

    def set_wavelength_nm(self, wav_nm: float) -> bool:
        if not self._connected:
            return False
        try:
            w = float(wav_nm)
            if w <= 0:
                return False
        except (TypeError, ValueError):
            return False
        self._last_wav_nm = w
        return True

    def read_power_w(self) -> Optional[float]:
        if not self._connected:
            return None
        base = 0.015
        return base + 1e-4 * math.sin(time.time())

    def read_power_mw(self) -> Optional[float]:
        p = self.read_power_w()
        return None if p is None else p * 1000.0


# ----- PRM -----
class PRMSimulationConnection:
    is_simulation = True

    def __init__(self, serial_number: Any = None):
        sn = str(serial_number or "SIM").strip() or "SIM"
        self.serial_number = sn
        self.motor = None
        self.connected = False
        self._lock = threading.RLock()
        self._angle = 0.0
        self._max_vel = 10.0
        self._accel = 10.0
        self._stop = threading.Event()

    def connect(self, status_log: Optional[Callable[[str], None]] = None, verbose: bool = True) -> bool:
        def _log(msg: str) -> None:
            if verbose:
                print(msg)
            if status_log:
                status_log(msg)

        self._stop.clear()
        with self._lock:
            self._angle = 0.0
        self.connected = True
        self.motor = None
        _log("[PRM] Simulation connected (serial={}).".format(self.serial_number))
        return True

    def is_connected(self) -> bool:
        return bool(self.connected)

    def disconnect(self) -> None:
        self._stop.set()
        self.connected = False
        self.motor = None

    def enable_device(self) -> None:
        if not self.connected:
            raise RuntimeError("Device not connected")

    def get_position(self) -> Optional[float]:
        if not self.connected:
            return None
        with self._lock:
            return float(self._angle)

    def set_speed(self, max_velocity: float, acceleration: float = 10.0) -> Tuple[float, float]:
        self._max_vel = max(0.1, float(max_velocity))
        self._accel = max(0.1, float(acceleration))
        return self._max_vel, self._accel

    def set_max_velocity(self, velocity_deg_per_sec: float) -> None:
        self.set_speed(float(velocity_deg_per_sec), self._accel)

    def set_velocity_params(self, acceleration: float, max_velocity_deg_per_sec: float) -> None:
        self.set_speed(float(max_velocity_deg_per_sec), float(acceleration))

    def get_max_velocity(self) -> float:
        return float(self._max_vel)

    def get_acceleration(self) -> float:
        return float(self._accel)

    def _position_to_float(self, value: Any) -> float:
        return float(value)

    def move_to(self, angle: Any) -> None:
        if not self.connected:
            raise RuntimeError("Device not connected")
        if isinstance(angle, str):
            angle = angle.strip().replace("'", "").replace('"', "")
        target = float(angle)
        spd = max(self._max_vel, 0.1)
        dt = 0.05
        self._stop.clear()
        while not self._stop.is_set():
            with self._lock:
                cur = self._angle
                if abs(cur - target) < 0.02:
                    self._angle = target
                    break
                step = spd * dt
                if target > cur:
                    self._angle = min(cur + step, target)
                else:
                    self._angle = max(cur - step, target)
            time.sleep(dt)

    def move_relative(self, delta_degrees: float) -> None:
        with self._lock:
            t = self._angle + float(delta_degrees)
        self.move_to(t)

    def home(self) -> None:
        self.move_to(0.0)

    def stop_immediate(self) -> None:
        self._stop.set()

    def stop_smooth(self) -> None:
        self._stop.set()

    def stop(self) -> None:
        self.stop_immediate()


# ----- Ando (same as previous module) -----
class AndoSimulationConnection:
    is_simulation = True

    def __init__(self, address: Any = None, config_file: Any = None, instrument_name: str = "Ando"):
        self.instrument_name = instrument_name
        self.enabled = True
        self.timeout = 5.0
        a = str(address or "").strip()
        if not a:
            self.gpib_address = "GPIB0::SIM::INSTR"
        elif a.isdigit():
            self.gpib_address = f"GPIB0::{a}::INSTR"
        else:
            self.gpib_address = a
        self.gpib_connection = None
        self.connected = False
        self._center_nm = 1550.0
        self._span_nm = 50.0
        self._ref_dbm = -20.0
        self._log_scale = 10.0
        self._resolution_nm = 0.1
        self._sampling_points = 501
        self._sensitivity_index = 0

    def connect(self, address: Any = None) -> bool:
        if address:
            addr = str(address).strip()
            if addr:
                if addr.isdigit():
                    self.gpib_address = f"GPIB0::{addr}::INSTR"
                else:
                    self.gpib_address = addr
        self.gpib_connection = object()
        self.connected = True
        return True

    def disconnect(self) -> None:
        try:
            self.set_local_mode()
        except Exception:
            pass
        self.gpib_connection = None
        self.connected = False

    def is_connected(self) -> bool:
        return bool(self.connected and self.gpib_connection is not None)

    def write_command(self, command: str) -> bool:
        return bool(self.connected)

    def read_response(self, timeout: Any = None) -> str:
        return ""

    def query(self, command: str) -> Optional[str]:
        if not self.connected:
            return None
        c = str(command or "").strip().upper()
        if c == "*IDN?":
            return "SIMULATION,ANDO,AQ6317B,0"
        if c == "CTRWL?":
            return str(self._center_nm)
        if c == "SPAN?":
            return str(self._span_nm)
        if c == "REFL?":
            return str(self._ref_dbm)
        if c == "LSCL?":
            return str(self._log_scale)
        if c == "RESOLN?":
            return str(self._resolution_nm)
        if c == "SWEEP?":
            return "0"
        if c == "WDATA?" or c.startswith("WDATA"):
            n = max(11, min(int(self._sampling_points), 2001))
            span = float(self._span_nm) if self._span_nm else 10.0
            ctr = float(self._center_nm)
            lo = ctr - span / 2.0
            step = span / max(n - 1, 1)
            vals = [lo + i * step for i in range(n)]
            return ",".join("{:.6f}".format(x) for x in vals)
        if c == "LDATA?" or c.startswith("LDATA"):
            n = max(11, min(int(self._sampling_points), 2001))
            ctr = float(self._center_nm)
            out = []
            for i in range(n):
                x = (i - n / 2.0) / max(n, 1)
                lv = float(self._ref_dbm) - 20.0 * (x * x) + 0.5 * math.sin(i * 0.1)
                out.append(lv)
            return ",".join("{:.6f}".format(x) for x in out)
        if c == "PKWL?":
            return str(self._center_nm + 0.02)
        if c == "PKLVL?":
            return str(self._ref_dbm)
        if c == "SPWD?":
            return "0.15"
        if c == "SMSR?" or c == "MSR?":
            return "42.5"
        return "OK"

    def identify(self) -> str:
        return self.query("*IDN?") or "SIMULATION,ANDO"

    def reset(self) -> bool:
        return self.write_command("*RST")

    def set_remote_mode(self) -> bool:
        return self.is_connected()

    def set_local_mode(self) -> bool:
        return self.is_connected()

    def get_center_wl(self) -> Optional[float]:
        return float(self._center_nm) if self.connected else None

    def get_span(self) -> Optional[float]:
        return float(self._span_nm) if self.connected else None

    def get_ref_level(self) -> Optional[float]:
        return float(self._ref_dbm) if self.connected else None

    def get_log_scale(self) -> Optional[float]:
        return float(self._log_scale) if self.connected else None

    def get_resolution(self) -> Optional[float]:
        return float(self._resolution_nm) if self.connected else None

    def set_center_wavelength(self, wavelength_nm: float) -> bool:
        if not self.connected:
            return False
        self._center_nm = float(wavelength_nm)
        return True

    def set_center_wl(self, wavelength_nm: float) -> bool:
        return self.set_center_wavelength(wavelength_nm)

    def set_span(self, span_nm: float) -> bool:
        if not self.connected:
            return False
        self._span_nm = float(span_nm)
        return True

    def set_resolution(self, resolution_nm: float) -> bool:
        if not self.connected:
            return False
        self._resolution_nm = float(resolution_nm)
        return True

    def set_ref_level(self, level_dbm: float) -> bool:
        if not self.connected:
            return False
        self._ref_dbm = float(level_dbm)
        return True

    def set_log_scale(self, dB_per_div: float) -> bool:
        if not self.connected:
            return False
        self._log_scale = float(dB_per_div)
        return True

    def set_sensitivity(self, sensitivity: str) -> bool:
        return self.is_connected()

    def set_sensitivity_index(self, index: int) -> bool:
        if not self.connected:
            return False
        self._sensitivity_index = int(index)
        return True

    def set_sampling_points(self, points: int) -> bool:
        if not self.connected:
            return False
        self._sampling_points = max(11, min(20001, int(points)))
        return True

    def analysis_dfb_ld(self) -> bool:
        return self.is_connected()

    def analysis_led(self) -> bool:
        return self.is_connected()

    def sweep_auto(self) -> bool:
        return self.is_connected()

    def single_sweep(self) -> bool:
        return self.is_connected()

    def sweep_single(self) -> bool:
        return self.single_sweep()

    def repeat_sweep(self) -> bool:
        return self.is_connected()

    def sweep_repeat(self) -> bool:
        return self.repeat_sweep()

    def stop_sweep(self) -> bool:
        return self.is_connected()

    def sweep_stop(self) -> bool:
        return self.stop_sweep()

    def query_sweep_status(self) -> Optional[str]:
        return "0"

    def is_sweep_done(self) -> bool:
        return True

    def analysis_fp_ld(self) -> bool:
        return self.is_connected()

    def trace_write_a(self) -> bool:
        return self.is_connected()

    def peak_search(self) -> bool:
        return self.is_connected()

    def query_peak_wavelength_nm(self):
        return float(self._center_nm) if self.connected else None

    def query_peak_level_dbm(self):
        return float(self._ref_dbm) if self.connected else None

    def query_spectral_width_nm(self):
        return 0.15 if self.connected else None

    def query_smsr_db(self):
        if not self.connected:
            return None
        r = self.query("SMSR?")
        try:
            return float(str(r).strip().split(",")[0]) if r is not None else None
        except (TypeError, ValueError, IndexError):
            return 42.5

    def wait_sweep_done(self, timeout_s: float = 180.0, poll_s: float = 0.25) -> bool:
        return bool(self.connected)

    def read_trace_data(self, query_cmd: str = "WDATA?") -> list:
        raw = self.query(query_cmd if query_cmd.endswith("?") else (query_cmd + "?"))
        if raw is None:
            return []
        s = str(raw).strip()
        parts = [p for p in s.replace(";", ",").split(",") if p.strip()]
        out = []
        for p in parts:
            try:
                out.append(float(p))
            except (TypeError, ValueError):
                pass
        return out

    def read_wdata_trace(self) -> list:
        return self.read_trace_data("WDATA?")

    def read_ldata_trace(self) -> list:
        return self.read_trace_data("LDATA?")


# ----- Wavemeter -----
class WavemeterSimulationConnection:
    is_simulation = True

    def __init__(self, address: str = ""):
        self._instrument = self
        self.connected = False
        a = (address or "").strip()
        if not a:
            self.gpib_address = "GPIB0::SIM::INSTR"
        elif a.isdigit():
            self.gpib_address = f"GPIB0::{a}::INSTR"
        else:
            self.gpib_address = a
        self._range_str = "1000-1650"
        self._base_nm = 1310.0

    def connect(self) -> Tuple[bool, Optional[str]]:
        self.connected = True
        return (True, None)

    def disconnect(self) -> None:
        self.connected = False
        self._instrument = self

    def is_connected(self) -> bool:
        return bool(self.connected)

    def set_wavelength_range(self, range_str: str) -> None:
        r = str(range_str).strip() if range_str else ""
        if r in ("480-1000", "1000-1650"):
            self._range_str = r
            self._base_nm = 850.0 if r == "480-1000" else 1310.0

    def apply_range(self) -> None:
        pass

    def read_wavelength_nm(self) -> float:
        if not self.connected:
            raise IOError("Wavemeter simulation not connected")
        t = time.time()
        noise = 0.02 * math.sin(t * 0.7) + 0.01 * math.sin(t * 2.1)
        return float(self._base_nm + noise)
