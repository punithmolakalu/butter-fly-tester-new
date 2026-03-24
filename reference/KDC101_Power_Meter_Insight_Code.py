import os
import sys
import time

import matplotlib.pyplot as plt


def _import_clr():
    """Import clr from pythonnet with a helpful error if unavailable."""
    try:
        import clr  # type: ignore
        return clr
    except ModuleNotFoundError:
        pass

    try:
        import pythonnet  # type: ignore
    except Exception as e:
        raise RuntimeError(
            "pythonnet is not installed. Install it with: pip install pythonnet"
        ) from e

    load_err = None
    for args in (("netfx",), tuple()):
        try:
            pythonnet.load(*args)  # type: ignore
            import clr  # type: ignore
            return clr
        except Exception as e:
            load_err = e

    raise RuntimeError(f"Failed to load .NET runtime for pythonnet: {load_err}") from load_err


KINESIS_DIR = r"C:\Program Files\Thorlabs\Kinesis"
if os.path.isdir(KINESIS_DIR):
    if KINESIS_DIR not in sys.path:
        sys.path.append(KINESIS_DIR)
    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(KINESIS_DIR)

clr = _import_clr()
clr.AddReference("Thorlabs.MotionControl.DeviceManagerCLI")
clr.AddReference("Thorlabs.MotionControl.GenericMotorCLI")
clr.AddReference("Thorlabs.MotionControl.KCube.DCServoCLI")

from Thorlabs.MotionControl.DeviceManagerCLI import *
from Thorlabs.MotionControl.GenericMotorCLI import *
from Thorlabs.MotionControl.GenericMotorCLI import KCubeMotor
from Thorlabs.MotionControl.GenericMotorCLI.ControlParameters import JogParametersBase
from Thorlabs.MotionControl.KCube.DCServoCLI import *
from System import Decimal

try:
    import pyvisa  # type: ignore
except Exception:
    pyvisa = None  # type: ignore

PM100_RESOURCE = "USB0::0x1313::0x8072::1924947::INSTR"


def _import_tlpm_class():
    """Import TLPM class by probing common locations of Thorlabs TLPM.py wrapper."""
    try:
        from TLPM import TLPM as _TLPM  # type: ignore
        return _TLPM
    except Exception:
        pass

    script_dir = os.path.dirname(os.path.abspath(__file__))
    probe_dirs = [
        script_dir,
        os.path.join(script_dir, "Thorlabs"),
        os.path.join(script_dir, "thorlabs"),
        # Typical TLPM Python wrapper locations from IVI VISA installs.
        r"C:\Program Files\IVI Foundation\VISA\Win64\TLPM\Examples\Python",
        r"C:\Program Files (x86)\IVI Foundation\VISA\WinNT\TLPM\Examples\Python",
        # Common direct TLPM.py drop-in locations.
        r"C:\Program Files\IVI Foundation\VISA\Win64\Bin",
        r"C:\Program Files (x86)\IVI Foundation\VISA\WinNT\Bin",
        r"C:\Program Files\Thorlabs\OPM",
        r"C:\Program Files\Thorlabs\Optical Power Monitor",
        r"C:\Program Files (x86)\Thorlabs\OPM",
        r"C:\Program Files (x86)\Thorlabs\Optical Power Monitor",
    ]

    dll_dirs = [
        r"C:\Program Files\IVI Foundation\VISA\Win64\Bin",
        r"C:\Program Files (x86)\IVI Foundation\VISA\WinNT\Bin",
    ]

    for d in probe_dirs:
        if d and os.path.isdir(d) and d not in sys.path:
            sys.path.append(d)

    if hasattr(os, "add_dll_directory"):
        for d in dll_dirs:
            if d and os.path.isdir(d):
                os.add_dll_directory(d)

    try:
        from TLPM import TLPM as _TLPM  # type: ignore
        return _TLPM
    except Exception as e:
        raise RuntimeError(
            "Cannot import TLPM. Install Thorlabs Optical Power Monitor software/driver "
            "and ensure TLPM.py is on PYTHONPATH. Probed paths include VISA TLPM "
            "Examples\\Python and VISA Bin folders."
        ) from e


def _open_pm100_pyvisa(resource: str, timeout_ms: int = 5000):
    """Open PM100 via PyVISA/SCPI (same pattern as working PER code)."""
    if pyvisa is None:
        raise RuntimeError("pyvisa is not installed. Install it with: pip install pyvisa")

    rm = pyvisa.ResourceManager()
    inst = rm.open_resource(resource)
    inst.timeout = int(timeout_ms)
    inst.write_termination = "\n"
    inst.read_termination = "\n"
    return rm, inst


def _plot_power_vs_angle(angles_deg, powers_dbm):
    """Plot sampled PM100 power in dBm against motor angle."""
    if not angles_deg or not powers_dbm:
        print("No angle/power samples were collected, so no plot was created.")
        return

    plt.figure(figsize=(9, 5))
    plt.plot(angles_deg, powers_dbm, color="tab:blue", linewidth=1.5)
    plt.xlabel("Angle (deg)")
    plt.ylabel("Power (dBm)")
    plt.title("Power vs Angle")
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.show()


def _create_live_plot():
    """Create a live-updating power-vs-angle plot."""
    plt.ion()
    fig, ax = plt.subplots(figsize=(9, 5))
    line, = ax.plot([], [], color="tab:blue", linewidth=1.5)
    ax.set_xlabel("Angle (deg)")
    ax.set_ylabel("Power (dBm)")
    ax.set_title("Power vs Angle")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    plt.show(block=False)
    try:
        fig.canvas.draw_idle()
        fig.canvas.flush_events()
    except Exception:
        pass
    return fig, ax, line


def _update_live_plot(fig, ax, line, angles_deg, powers_dbm):
    """Refresh the live plot with the latest collected samples."""
    if not angles_deg or not powers_dbm:
        return
    line.set_data(angles_deg, powers_dbm)
    xmin = min(angles_deg)
    xmax = max(angles_deg)
    if xmin == xmax:
        xmin -= 0.5
        xmax += 0.5
    ymin = min(powers_dbm)
    ymax = max(powers_dbm)
    if ymin == ymax:
        ymin -= 0.5
        ymax += 0.5
    ax.set_xlim(xmin, xmax)
    ax.set_ylim(ymin, ymax)
    try:
        line.figure.canvas.draw_idle()
        line.figure.canvas.flush_events()
    except Exception:
        pass
    plt.pause(0.01)


def _to_float(value):
    """Best-effort conversion for .NET numeric types such as System.Decimal."""
    try:
        return float(value)
    except TypeError:
        return float(str(value))


def _list_kinesis_serials():
    """Return the currently enumerated Kinesis device serials as strings."""
    DeviceManagerCLI.BuildDeviceList()
    try:
        return [str(sn).strip() for sn in DeviceManagerCLI.GetDeviceList()]
    except Exception:
        return []


def _connect_controller_with_retry(controller, serial_num: str):
    """Connect to the controller with one refresh/retry, similar to the GUI path."""
    available = _list_kinesis_serials()
    print(f"Kinesis devices: {available}")
    if available and serial_num not in available:
        raise RuntimeError(f"Requested serial {serial_num} not found in Kinesis list: {available}")

    last_error = None
    for attempt in (1, 2):
        try:
            DeviceManagerCLI.BuildDeviceList()
        except Exception:
            pass
        time.sleep(0.2)

        try:
            controller.Connect(serial_num)
            return
        except Exception as exc:
            last_error = exc
            try:
                controller.Disconnect(True)
            except Exception:
                try:
                    controller.Disconnect()
                except Exception:
                    pass
            if attempt == 1:
                print("First motor connect attempt failed; refreshing Kinesis list and retrying once.")
                time.sleep(0.4)

    raise last_error

def main():
    """The main entry point for the application"""
    if hasattr(os, "add_dll_directory"):
        os.add_dll_directory(os.getcwd())
    selected_resource = PM100_RESOURCE
    print(f"Using PM100 resource: {selected_resource}")
    rm, pm = _open_pm100_pyvisa(selected_resource, timeout_ms=5000)
    angles_deg = []
    powers_dbm = []
    fig, ax, line = _create_live_plot()
    try:
        idn = pm.query("*IDN?").strip()
    except Exception:
        idn = "Unknown"
    print(f"PM100 IDN: {idn}")
    pm.write("SENS:CORR:WAV 635.000000NM")
    pm.write("SENS:POW:UNIT DBM")
    try:
        unit = pm.query("SENS:POW:UNIT?").strip()
    except Exception as exc:
        unit = f"UNKNOWN ({exc})"
    print(f"PM100 unit: {unit}")

    #SimulationManager.Instance.InitializeSimulations()

    serial_num = str("27271352")
    
    DeviceManagerCLI.BuildDeviceList()

    controller  = KCubeDCServo.CreateKCubeDCServo(serial_num)

    if not controller == None:
        _connect_controller_with_retry(controller, serial_num)
        if not controller.IsSettingsInitialized():
            controller.WaitForSettingsInitialized(3000)
        
        controller.StartPolling(50)
        time.sleep(.1)
        controller.EnableDevice()
        time.sleep(.1)
        config = controller.LoadMotorConfiguration(serial_num, DeviceConfiguration.DeviceSettingsUseOptionType.UseDeviceSettings)
        config.DeviceSettingsName = str('PRM1-Z8')
        config.UpdateCurrentConfiguration()

        print('Homing Motor')
        controller.Home(60000);

        jog_params = controller.GetJogParams()
        jog_params.StepSize = Decimal(360)
        jog_params.VelocityParams.MaxVelocity = Decimal(25)     
        jog_params.JogMode = JogParametersBase.JogModes.SingleStep

        controller.SetJogParams(jog_params)

        print('Moving motor')
        controller.MoveJog(MotorDirection.Forward, 0)
        time.sleep(.25)
        while controller.IsDeviceBusy:        
            try:
                power_dbm = float(pm.query("MEAS:POW?").strip())
            except Exception:
                power_dbm = float("nan")
            angle_deg = _to_float(controller.Position)
            angles_deg.append(angle_deg)
            powers_dbm.append(power_dbm)
            #print(f'{angle_deg}, {power_dbm}')
            _update_live_plot(fig, ax, line, angles_deg, powers_dbm)
            time.sleep(.1)

        controller.StopPolling()
        controller.Disconnect(False);
    try:
        pm.close()
    finally:
        rm.close()
    plt.ioff()
    _plot_power_vs_angle(angles_deg, powers_dbm)
    #SimulationManager.Instance.UninitializeSimulations()


if __name__ == "__main__":
    main()
