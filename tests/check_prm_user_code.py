"""
Terminal check: use the exact connection code you gave to see if PRM connects or not.
Run from project root:  python -m tests.check_prm_user_code
"""
import time
import sys
import os

# Your code: import pythonnet and Thorlabs Kinesis
import clr  # type: ignore
kinesis_path = r"C:\Program Files\Thorlabs\Kinesis"
sys.path.append(kinesis_path)
clr.AddReference("System")  # type: ignore
clr.AddReference("Thorlabs.MotionControl.DeviceManagerCLI")  # type: ignore
clr.AddReference("Thorlabs.MotionControl.KCube.DCServoCLI")  # type: ignore
from System import Decimal  # type: ignore
from Thorlabs.MotionControl.DeviceManagerCLI import DeviceManagerCLI  # type: ignore
from Thorlabs.MotionControl.KCube.DCServoCLI import KCubeDCServo  # type: ignore

TIMEOUT = 60000
POLLING_RATE = 250


def find_available_kcube_dc_servo():
    """Scan for available KCube DCServo devices and return the first one's serial number."""
    DeviceManagerCLI.BuildDeviceList()
    device_list = DeviceManagerCLI.GetDeviceList()
    if device_list is None:
        return None
    if isinstance(device_list, str):
        serials = [s.strip() for s in device_list.split(",") if s.strip()]
    elif hasattr(device_list, "Count") and device_list.Count == 0:
        return None
    else:
        try:
            serials = [str(s).strip() for s in device_list if str(s).strip()]
        except (TypeError, AttributeError):
            serials = [str(device_list).strip()] if str(device_list).strip() else []
    for sn in serials:
        if not sn:
            continue
        try:
            motor = KCubeDCServo.CreateKCubeDCServo(sn)  # type: ignore
            if motor is not None:
                return sn
        except Exception:
            continue
    return None


class KDC101Controller:
    def __init__(self, serial_number):
        self.motor = None
        self.connected = False
        self.serial_number = serial_number

    def connect(self):
        if self.connected:
            return
        DeviceManagerCLI.BuildDeviceList()
        device_list = DeviceManagerCLI.GetDeviceList()
        if self.serial_number not in device_list:
            raise RuntimeError("Device {} not found. Available: {}".format(self.serial_number, list(device_list)))
        try:
            self.motor = KCubeDCServo.CreateKCubeDCServo(self.serial_number)  # type: ignore
        except Exception as e:
            error_msg = str(e)
            if "NullReferenceException" in error_msg or "Object reference" in error_msg:
                raise RuntimeError("Device configuration missing. Configure in Thorlabs Kinesis first.")
            raise RuntimeError("Failed to create device: {}".format(error_msg))
        if self.motor is None:
            raise RuntimeError("Failed to create device object")
        self.motor.Connect(self.serial_number)  # type: ignore
        time.sleep(0.5)
        try:
            self.motor.WaitForSettingsInitialized(10000)  # type: ignore
            self.motor.LoadMotorConfiguration(self.serial_number)  # type: ignore
        except Exception:
            pass
        time.sleep(0.5)
        self.motor.StartPolling(POLLING_RATE)  # type: ignore
        time.sleep(0.5)
        self.motor.EnableDevice()  # type: ignore
        time.sleep(0.5)
        self.connected = True

    def get_position(self):
        if not self.connected or self.motor is None:
            return None
        try:
            return float(self.motor.DevicePosition)  # type: ignore
        except Exception:
            try:
                return float(self.motor.Position)  # type: ignore
            except Exception:
                return None

    def disconnect(self):
        if self.motor and self.connected:
            try:
                self.motor.StopPolling()  # type: ignore
                self.motor.DisableDevice()  # type: ignore
                self.motor.Disconnect()  # type: ignore
            except Exception:
                pass
        self.motor = None
        self.connected = False


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    print("Checking PRM connection with your code...")
    print()
    serial_number = find_available_kcube_dc_servo()
    if not serial_number:
        print("Result: NOT CONNECTING - No device detected (find_available_kcube_dc_servo returned None).")
        sys.exit(1)
    print("Device detected: serial {}".format(serial_number))
    try:
        ctrl = KDC101Controller(serial_number)
        ctrl.connect()
        pos = ctrl.get_position()
        ctrl.disconnect()
        print("Result: CONNECTING - Connect and position read OK. Position: {:.3f} deg".format(pos if pos is not None else 0))
        sys.exit(0)
    except Exception as e:
        print("Result: NOT CONNECTING - Error: {}".format(e))
        sys.exit(1)
