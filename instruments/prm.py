"""
Thorlabs PRM1-Z8 / KCube DCServo (KDC101)

Instrument: Thorlabs PRM1-Z8 rotation mount driven by KDC101 (KCube DCServo). Kinesis API.
Connection: USB via Thorlabs Kinesis (DeviceManagerCLI, KCubeDCServo). Connect on main thread.
Details: Scan by serial number; connect, home, move_to(angle), get_position, stop(), disconnect.
         Must connect/disconnect on main thread (Kinesis requirement). Polling 250 ms.
Commands reference: instrument_commands/PRM_Commands.md
"""
from __future__ import annotations

import os
import sys
import time
from typing import Callable, List, Optional

_KINESIS_LOAD_ERROR = None

try:
    import clr  # type: ignore
    kinesis_path = r"C:\Program Files\Thorlabs\Kinesis"
    if os.path.exists(kinesis_path):
        sys.path.insert(0, kinesis_path)
    clr.AddReference("System")  # type: ignore
    clr.AddReference("Thorlabs.MotionControl.DeviceManagerCLI")  # type: ignore
    clr.AddReference("Thorlabs.MotionControl.GenericMotorCLI")  # type: ignore
    clr.AddReference("Thorlabs.MotionControl.KCube.DCServoCLI")  # type: ignore
    from System import Decimal  # type: ignore
    from Thorlabs.MotionControl.DeviceManagerCLI import DeviceManagerCLI  # type: ignore
    from Thorlabs.MotionControl.KCube.DCServoCLI import KCubeDCServo  # type: ignore
    KINESIS_AVAILABLE = True
except Exception as e:
    KINESIS_AVAILABLE = False
    _KINESIS_LOAD_ERROR = str(e)
    DeviceManagerCLI = None
    KCubeDCServo = None
    Decimal = None

TIMEOUT = 180000  # 3 min (same as working Tkinter app) for MoveTo/Home
POLLING_RATE = 250
DEFAULT_ACCEL = 10.0  # deg/s^2 (same as working Tkinter app)
MAX_SPEED = 25.0  # max allowed speed in deg/s (PRM manual control limit)


def _normalize_serial(serial_number):  # type: ignore
    """Return clean serial string: strip whitespace and surrounding quotes (no quotes passed to Kinesis)."""
    sn = (str(serial_number).strip() if serial_number else "") or ""
    while len(sn) >= 2 and (
        (sn[0] == "'" and sn[-1] == "'") or (sn[0] == '"' and sn[-1] == '"')
    ):
        sn = sn[1:-1].strip()
    return sn


def _device_list_to_serials(device_list):  # type: ignore
    """Convert GetDeviceList() result to list of serial strings. Same logic as standalone."""
    if device_list is None:
        return []
    if isinstance(device_list, str):
        return [s.strip() for s in device_list.split(",") if s.strip()]
    if hasattr(device_list, "Count") and device_list.Count == 0:
        return []
    try:
        return [str(s).strip() for s in device_list if str(s).strip()]
    except (TypeError, AttributeError):
        return [str(device_list).strip()] if str(device_list).strip() else []


def _get_device_list_serials() -> List[str]:
    """Return list of Kinesis device serial numbers. Used for Scan in UI."""
    if not KINESIS_AVAILABLE or DeviceManagerCLI is None:
        print("[PRM] Scan skipped: Kinesis not available")
        return []
    try:
        DeviceManagerCLI.BuildDeviceList()
        device_list = DeviceManagerCLI.GetDeviceList()
        serials = _device_list_to_serials(device_list)
        print("[PRM] Scan found {} device(s): {}".format(len(serials), serials))
        return serials
    except Exception as e:
        print("[PRM] Scan failed: {}".format(e))
        pass
    return []


def find_available_kcube_dc_servo():
    """Scan for first available KCube DCServo (KDC101). Same logic as standalone."""
    if not KINESIS_AVAILABLE or DeviceManagerCLI is None or KCubeDCServo is None:
        return None
    try:
        DeviceManagerCLI.BuildDeviceList()
        device_list = DeviceManagerCLI.GetDeviceList()
        serials = _device_list_to_serials(device_list)
        for sn in serials:
            if not sn:
                continue
            try:
                motor = KCubeDCServo.CreateKCubeDCServo(sn)  # type: ignore
                if motor is not None:
                    return sn
            except Exception:
                continue
    except Exception:
        pass
    return None


def scan_prm_serial_numbers() -> List[str]:
    return _get_device_list_serials()


def get_prm_scan_status() -> tuple:
    if not KINESIS_AVAILABLE:
        return False, "Kinesis not available (install Thorlabs Kinesis)"
    try:
        serials = _get_device_list_serials()
        if not serials:
            return True, "No devices found (power on device, USB connected)"
        return True, ""
    except Exception as e:
        return False, str(e)


class PRMConnection:
    """PRM1-Z8 / KDC101. Connect and disconnect on main thread."""

    def __init__(self, serial_number=None):
        self.motor = None
        self.connected = False
        # Store serial without quotes so Kinesis never sees quoted string
        sn = _normalize_serial(serial_number)
        self.serial_number = sn if sn else None

    def connect(self, status_log: Optional[Callable[[str], None]] = None, verbose: bool = True) -> bool:
        def _log(msg: str) -> None:
            if verbose:
                print(msg)
            if status_log:
                status_log(msg)

        if self.connected:
            return True
        if not KINESIS_AVAILABLE:
            msg = "Thorlabs Kinesis not available. Install Thorlabs Kinesis and pythonnet (pip install pythonnet)."
            if _KINESIS_LOAD_ERROR:
                msg += " Load error: " + _KINESIS_LOAD_ERROR
            raise RuntimeError(msg)
        sn = _normalize_serial(self.serial_number or "")
        if not sn or sn.lower().startswith("(no ") or "not found" in sn.lower():
            raise RuntimeError("PRM serial number not configured. Run Scan in the Connection tab and select a device.")
        self.serial_number = sn
        _log("[PRM] Connecting to serial: {}".format(sn))
        # BuildDeviceList (once), get list, use serial from list when possible so Kinesis gets same type.
        DeviceManagerCLI.BuildDeviceList()  # type: ignore
        device_list = DeviceManagerCLI.GetDeviceList()  # type: ignore
        if device_list is None:
            _log("[PRM] GetDeviceList() returned None")
            raise RuntimeError("No PRM devices found. Power on device and connect via USB.")
        serials = _device_list_to_serials(device_list)
        # Prefer serial string from device_list so we pass exactly what Kinesis returned (no quote/type issues).
        sn_to_use = sn
        for item in serials:
            s = (str(item).strip() if item else "") or ""
            if s == sn:
                sn_to_use = s
                break
        try:
            in_list = sn in serials or sn_to_use in serials
        except Exception:
            in_list = False
        if not in_list:
            try:
                in_list = sn in device_list
            except Exception:
                pass
        if not in_list and serials:
            in_list = any(sn == (str(x).strip() if x else "") for x in serials)
        if not in_list:
            try:
                available = list(device_list)
            except Exception:
                available = serials
            _log("[PRM] Serial {} not in list. Available: {}".format(sn, available))
            raise RuntimeError("Device {} not found. Available: {}".format(sn, available))
        try:
            self.motor = KCubeDCServo.CreateKCubeDCServo(sn_to_use)  # type: ignore
        except Exception as e:
            err = str(e)
            if "NullReferenceException" in err or "Object reference" in err:
                raise RuntimeError(
                    "Device configuration missing. Configure device in Thorlabs Kinesis first (Open Kinesis, connect device, save settings), then try again."
                ) from e
            raise RuntimeError("Failed to create device: {}".format(err)) from e
        if self.motor is None:
            raise RuntimeError("Failed to create device object")
        self.motor.Connect(sn_to_use)  # type: ignore
        time.sleep(0.5)
        if not self.motor.IsSettingsInitialized():  # type: ignore
            self.motor.WaitForSettingsInitialized(10000)  # type: ignore
        try:
            self.motor.LoadMotorConfiguration(sn_to_use)  # type: ignore
        except Exception:
            pass
        time.sleep(0.5)
        self.motor.StartPolling(POLLING_RATE)  # type: ignore
        time.sleep(0.5)
        self.motor.EnableDevice()  # type: ignore
        time.sleep(0.5)
        self.connected = True
        _log("[PRM] Connected successfully.")
        # Prove the Kinesis session works (not just Create/Connect without working I/O).
        try:
            pos = self.get_position()
            _log("[PRM] Kinesis link OK — position readback: {:.4f} °".format(pos if pos is not None else 0.0))
        except Exception as e:
            try:
                self.disconnect()
            except Exception:
                pass
            raise RuntimeError(
                "Kinesis opened the device but position read failed (not fully usable). "
                "Check USB, power, and Thorlabs Kinesis configuration. ({})".format(e)
            ) from e
        return True

    def is_connected(self) -> bool:
        return bool(self.connected and self.motor is not None)

    def enable_device(self) -> None:
        """Re-enable the device so it accepts move/home after a stop. Kinesis: EnableDevice()."""
        if not self.connected or self.motor is None:
            raise RuntimeError("Device not connected")
        self.motor.EnableDevice()  # type: ignore
        time.sleep(0.25)

    def home(self) -> None:
        """Home stage. Kinesis: Home()."""
        if not self.connected or self.motor is None:
            raise RuntimeError("Device not connected")
        self.motor.Home(TIMEOUT)  # type: ignore

    def move_to(self, angle) -> None:
        """Move to position (degrees). Same as Tkinter PRM app: MoveTo(Decimal(angle), TIMEOUT)."""
        if not self.connected or self.motor is None:
            raise RuntimeError("Device not connected")
        if isinstance(angle, str):
            angle = angle.strip().replace("'", "").replace('"', "")
        target_val = float(angle)
        target = Decimal(target_val)  # type: ignore
        self.motor.MoveTo(target, TIMEOUT)  # type: ignore

    def move_relative(self, delta_degrees: float) -> None:
        """Move by relative distance (degrees). Kinesis: MoveRelative()."""
        if not self.connected or self.motor is None:
            raise RuntimeError("Device not connected")
        delta = Decimal(float(delta_degrees))  # type: ignore
        if hasattr(self.motor, "MoveRelative"):
            self.motor.MoveRelative(delta, TIMEOUT)  # type: ignore
        else:
            try:
                pos = self.get_position()
                self.move_to((pos or 0) + float(delta_degrees))
            except Exception:
                raise RuntimeError("MoveRelative not supported and position read failed")

    def get_max_velocity(self) -> float:
        """Return max velocity (deg/s). Same as working Tkinter: GetVelocityParams().MaxVelocity."""
        if not self.connected or self.motor is None:
            return 0.0
        try:
            if hasattr(self.motor, "GetVelocityParams"):
                vp = self.motor.GetVelocityParams()  # type: ignore
                if vp is not None and hasattr(vp, "MaxVelocity"):
                    return float(str(vp.MaxVelocity))
            if hasattr(self.motor, "GetVelParams"):
                result = self.motor.GetVelParams()  # type: ignore
                if isinstance(result, (list, tuple)) and len(result) >= 2:
                    return float(result[1])
                if hasattr(result, "Item2"):
                    return float(result.Item2)
                if hasattr(result, "MaxVelocity"):
                    return float(str(result.MaxVelocity))
        except Exception:
            pass
        return 0.0

    def get_acceleration(self) -> float:
        """Return acceleration (deg/s²). Same as working Tkinter: GetVelocityParams().Acceleration."""
        if not self.connected or self.motor is None:
            return 0.0
        try:
            if hasattr(self.motor, "GetVelocityParams"):
                vp = self.motor.GetVelocityParams()  # type: ignore
                if vp is not None and hasattr(vp, "Acceleration"):
                    return float(str(vp.Acceleration))
            if hasattr(self.motor, "GetVelParams"):
                result = self.motor.GetVelParams()  # type: ignore
                if isinstance(result, (list, tuple)) and len(result) >= 1:
                    return float(result[0])
                if hasattr(result, "Item1"):
                    return float(result.Item1)
                if hasattr(result, "Acceleration"):
                    return float(str(result.Acceleration))
        except Exception:
            pass
        return 0.0

    def set_speed(self, max_velocity: float, acceleration: float = DEFAULT_ACCEL):
        """
        Set max velocity (deg/s) and acceleration (deg/s²) on instrument.
        Exact copy from working Tkinter app.
        API order: SetVelocityParams(maxVelocity, acceleration).
        Returns (actual_vel, actual_accel) from readback.
        """
        if self.motor is None:
            raise RuntimeError("Device not connected")
        max_vel = float(max_velocity)
        accel = float(acceleration)
        if max_vel <= 0:
            raise ValueError("Speed must be positive (deg/s).")
        if max_vel > MAX_SPEED:
            raise ValueError("Speed must not exceed {} deg/s.".format(MAX_SPEED))
        self.motor.SetVelocityParams(Decimal(max_vel), Decimal(accel))  # type: ignore
        time.sleep(0.25)
        vel_params = self.motor.GetVelocityParams()  # type: ignore
        actual_accel = float(str(vel_params.Acceleration))
        actual_vel = float(str(vel_params.MaxVelocity))
        return actual_vel, actual_accel

    def set_max_velocity(self, velocity_deg_per_sec: float) -> None:
        """Set motor speed (deg/s). Uses same code as working Tkinter set_speed()."""
        self.set_speed(velocity_deg_per_sec, DEFAULT_ACCEL)

    def set_velocity_params(self, acceleration: float, max_velocity_deg_per_sec: float) -> None:
        """Set acceleration and max velocity. Uses same code as working Tkinter set_speed()."""
        self.set_speed(max_velocity_deg_per_sec, acceleration)

    def _position_to_float(self, value) -> float:
        """Convert Kinesis position (may be System.Decimal) to Python float."""
        if value is None:
            raise TypeError("position is None")
        if isinstance(value, (int, float)):
            return float(value)
        # Kinesis often returns System.Decimal; Python float() does not accept it
        return float(str(value))

    def get_position(self):
        """Return current position in degrees. Same as working Tkinter: float(str(device.Position))."""
        if not self.connected or self.motor is None:
            return None
        try:
            raw = self.motor.Position  # type: ignore
            return self._position_to_float(raw)
        except Exception as e:
            try:
                raw = self.motor.DevicePosition  # type: ignore
                return self._position_to_float(raw)
            except Exception:
                raise RuntimeError("PRM not responding (device may be off or unplugged)") from e

    def stop_immediate(self) -> None:
        """Send immediate stop command to the motor. Same as KDC101 Tkinter: StopImmediate() or Stop(True)."""
        if self.motor is None:
            raise RuntimeError("Device not connected")
        try:
            self.motor.StopImmediate()  # type: ignore
        except AttributeError:
            try:
                self.motor.Stop(True)  # type: ignore  # True = immediate stop
            except Exception:
                raise RuntimeError("Immediate stop not supported on this device.")
        except Exception as e:
            raise RuntimeError("Immediate stop failed: {}".format(e))

    def stop_smooth(self) -> None:
        """Send profiled (smooth) stop command to the motor. Same as KDC101 Tkinter: StopProfiled() or Stop(False)."""
        if self.motor is None:
            raise RuntimeError("Device not connected")
        try:
            self.motor.StopProfiled()  # type: ignore
        except AttributeError:
            try:
                self.motor.Stop(False)  # type: ignore  # False = profiled stop
            except Exception:
                raise RuntimeError("Smooth stop not supported on this device.")
        except Exception as e:
            raise RuntimeError("Smooth stop failed: {}".format(e))

    def stop(self) -> None:
        """Alias for stop_immediate (backward compatibility)."""
        self.stop_immediate()

    def disconnect(self) -> None:
        """Same as working Tkinter: StopPolling, DisableDevice, Disconnect(True)."""
        if self.motor and self.connected:
            try:
                self.motor.StopPolling()  # type: ignore
            except Exception:
                pass
            try:
                self.motor.DisableDevice()  # type: ignore
            except Exception:
                pass
            try:
                try:
                    self.motor.Disconnect(True)  # type: ignore  # same as Tkinter
                except TypeError:
                    self.motor.Disconnect()  # type: ignore
            except Exception:
                pass
        self.motor = None
        self.connected = False
