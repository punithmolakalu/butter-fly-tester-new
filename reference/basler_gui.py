# -*- coding: utf-8 -*-
"""
Created on Fri Jan 23 15:09:36 2026

@author: 4510205
"""

#!/usr/bin/env python3
"""
PyQt5-based GUI for Basler Camera Analysis
This is a GUI module imported FROM basler_analysis_labview_output_layout_v2_updated.py
NOT a standalone application - it's a component of the main analysis code.
"""
import sys, os
import re
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
#print('USING GUI FILE:', __file__)
import time as _time
from arroyo_backend_DISABLE_CLAMP_PATCHED import ArroyoLaserSystem
#import arroyo_backend_DISABLE_CLAMP_PATCHED as ab
#print("IMPORTING BACKEND FROM:", ab.__file__)
#print("HAS connect_combo?", hasattr(ArroyoLaserSystem, "connect_combo"))
#print("HAS connect_separate?", hasattr(ArroyoLaserSystem, "connect_separate"))
import datetime as _dt
import numpy as np
from pathlib import Path
import serial.tools.list_ports
from typing import Any, Dict, Optional, Tuple, Iterable, List, Union
import pythonnet  # type: ignore
import cv2
import contextlib
from matplotlib import cm, colors
from matplotlib.ticker import MultipleLocator, MaxNLocator
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
from basler_analysis_labview_output_layout_v2_updated_loop_gui_fixed_rgbdisplay_square_sat_v2_POWER_REQUESTS_PATCHED import Config
from laser_control_panel_v2_frontpanel import LaserControlPanel

from PyQt5.QtCore import QTimer, QEventLoop, pyqtSignal
from dataclasses import dataclass
import xml.etree.ElementTree as _ET
from matplotlib.patches import Circle
# Import zoom and plot functions for SA/FA zoomed plots
# (Imports moved inside methods to avoid circular import)
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QSpinBox, QDoubleSpinBox,
    QCheckBox, QTabWidget, QGroupBox, QGridLayout, QScrollArea, QFileDialog,
    QProgressBar, QTextEdit, QMessageBox, QSpacerItem, QSizePolicy, QRadioButton, QSplitter, QGraphicsView, QGraphicsScene, QGraphicsPixmapItem, QToolButton
)
# UV Control (Omnicure) tab
#try:
 #   from uv_control_panel_FIXED_PATCHED_UPDATED_v3 import UVControlPanel
# --- M² / Divergence (Thorlabs Beam launcher + export helper) ---
try:
    from m2_measurment import M2MeasurementWidget
except Exception:
    M2MeasurementWidget = None
#except Exception:
 #   try:
   #     from uv_control_panel_FIXED_PATCHED_UPDATED_v3 import UVControlPanel
   # except Exception:
      #  UVControlPanel = None
#from PyQt5.QtWidgets import QRadioButton
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QImage, QPixmap, QPainter
import csv
import json
import datetime
try:
    from pypylon import pylon  # type: ignore
    _PYPYLON_AVAILABLE = True
except Exception:
    pylon = None
    _PYPYLON_AVAILABLE = False
# --- PER tab ---
from PER_EDITED_PATCHED_v11_POWER_W_ANGLE_ALWAYS import PERWidget, PowerMeterSettingsPanel
import subprocess
import threading as _threading
import traceback
import importlib
import serial
from types import SimpleNamespace
from uv_control_panel_FIXED_PATCHED_UPDATED_v3 import UVControlPanel







###########################
def to_falsecolor_rgb(
    frame: np.ndarray,
    *,
    lo_pct: float = 1.0,
    hi_pct: float = 99.7,
    gamma: float = 0.8,
    magenta_start: float = 0.75,   # where magenta begins (0..1 after scaling)
    magenta_strength: float = 1.0, # 0..1 how strong magenta becomes near peak
    white_cap_start: float = 0.995, # only the very top becomes white-ish
) -> np.ndarray:
    """
    Falsecolor to resemble your screenshot:
    black -> blue -> green -> yellow -> red -> magenta core (+ tiny white cap at the very peak).
    Returns RGB uint8.
    """

    # 1) reduce to single channel if needed
    if frame.ndim == 3 and frame.shape[2] >= 3:
        gray = frame[:, :, 0]
    else:
        gray = frame

    g = gray.astype(np.float32)

    # 2) robust scaling using percentiles (prevents hot pixels from wrecking the map)
    lo = float(np.nanpercentile(g, lo_pct))
    hi = float(np.nanpercentile(g, hi_pct))
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        lo = float(np.nanmin(g))
        hi = float(np.nanmax(g)) if float(np.nanmax(g)) > lo else lo + 1.0

    x = (g - lo) / (hi - lo)
    x = np.clip(x, 0.0, 1.0)

    # 3) gamma (boosts center vs wings to look like beam profiles)
    if gamma is not None and gamma > 0:
        x = np.power(x, gamma)

    # 4) base colormap: black -> blue -> green -> yellow -> red
    # Build LUT in RGB
    lut = np.zeros((256, 3), dtype=np.uint8)
    stops = [
        (0.00, (0,   0,   0  )),  # black
        (0.18, (0,   0,   255)),  # blue
        (0.42, (0,   255, 0  )),  # green
        (0.62, (255, 255, 0  )),  # yellow
        (0.78, (255, 0,   0  )),  # red
    ]

    def lerp(a, b, t):
        return (a[0] + (b[0] - a[0]) * t,
                a[1] + (b[1] - a[1]) * t,
                a[2] + (b[2] - a[2]) * t)

    for i in range(256):
        u = i / 255.0
        # find segment
        for (p0, c0), (p1, c1) in zip(stops[:-1], stops[1:]):
            if u <= p1:
                t = 0.0 if p1 == p0 else (u - p0) / (p1 - p0)
                r, g2, b = lerp(c0, c1, t)
                lut[i] = (int(r), int(g2), int(b))
                break
        else:
            lut[i] = stops[-1][1]

    idx = (x * 255.0 + 0.5).astype(np.uint8)
    rgb = lut[idx].astype(np.float32)  # RGB float for blending

    # 5) magenta core tint near the peak (this is what your screenshot has)
    # Blend towards magenta as x approaches 1
    t = np.clip((x - magenta_start) / max(1e-6, (1.0 - magenta_start)), 0.0, 1.0)
    t = t * magenta_strength
    magenta = np.array([255.0, 0.0, 255.0], dtype=np.float32)  # RGB
    rgb = rgb * (1.0 - t[..., None]) + magenta * t[..., None]

    # 6) tiny white cap at the very top (optional; set white_cap_start=1.1 to disable)
    tw = np.clip((x - white_cap_start) / max(1e-6, (1.0 - white_cap_start)), 0.0, 1.0)
    white = np.array([255.0, 255.0, 255.0], dtype=np.float32)
    rgb = rgb * (1.0 - tw[..., None]) + white * tw[..., None]

    return np.clip(rgb, 0, 255).astype(np.uint8)

def _beam_falsecolor_cmap():
    """Matplotlib colormap that matches to_falsecolor_rgb color progression."""
    ramp = np.tile(np.arange(256, dtype=np.uint8), (2, 1))
    rgb = to_falsecolor_rgb(
        ramp,
        lo_pct=0.0,
        hi_pct=100.0,
        gamma=0.8,
        magenta_start=0.75,
        magenta_strength=1.0,
        white_cap_start=0.995,
    )
    return colors.ListedColormap((rgb[0].astype(np.float32) / 255.0), name="beam_falsecolor")

_BEAM_FALSECOLOR_CMAP = _beam_falsecolor_cmap()
_BEAM_FALSECOLOR_LUT = (_BEAM_FALSECOLOR_CMAP(np.linspace(0.0, 1.0, 256))[:, :3] * 255.0).astype(np.uint8)

def to_falsecolor_rgb_fixed(frame: np.ndarray) -> np.ndarray:
    """Apply a fixed 0..255 false-color mapping so colors mean the same thing every frame."""
    if frame.ndim == 3 and frame.shape[2] >= 3:
        gray = frame[:, :, 0]
    else:
        gray = frame

    if gray.dtype != np.uint8:
        gray = np.clip(gray, 0, 255).astype(np.uint8)

    return _BEAM_FALSECOLOR_LUT[gray]



##################################
@dataclass(frozen=True)
class Trace:
    """A simple XY trace representation (spectrum or marker line)."""
    x: np.ndarray
    y: np.ndarray
    label: str = ""

class ZoomResult:
    zoomed_array: np.ndarray          # cropped numeric array (NxM)
    start_index: int                  # first index above threshold
    end_index: int                    # last index above threshold
    sa_zoomed_spreadsheet: str        # LabVIEW-like spreadsheet string output

@dataclass(frozen=True)
class ZoomResult:
    x_zoom: np.ndarray
    y_zoom: np.ndarray
    x1: float
    x2: float
    xmid: float
    rebase: bool
##########

def _as_float(x: Union[int, float, np.number]) -> float:
    return float(np.asarray(x).item())

#plot zoom image 
def _detect_marker_x_positions_from_traces(
    traces: Iterable[Trace],
    xspan_threshold: float = 0.01
) -> Tuple[List[float], Optional[Trace]]:
    """
    Detect marker traces based on small X-span and return their X positions,
    plus the 'main spectrum' trace (largest X-span).
    """
    marker_xs: List[float] = []
    spectrum_candidate: Optional[Trace] = None
    spectrum_span = -np.inf

    for tr in traces:
        if tr.x.size == 0:
            continue
        xspan = float(np.nanmax(tr.x) - np.nanmin(tr.x))
        if xspan <= xspan_threshold:
            marker_xs.append(float(np.nanmean(tr.x)))
        else:
            if xspan > spectrum_span:
                spectrum_span = xspan
                spectrum_candidate = tr

    return marker_xs, spectrum_candidate


def _crop_spectrum_between(
    x: np.ndarray,
    y: np.ndarray,
    x_min: float,
    x_max: float,
    *,
    left_margin_x: float = 0.0,
    right_margin_x: float = 0.0,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Crop x,y to [x_min - left_margin_x, x_max + right_margin_x].

    - Works with sorted or unsorted x.
    - If x is sorted, uses searchsorted (preserves order).
    - If unsorted, uses boolean mask (order preserved but not "zoom-order" if x is chaotic).
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)

    if x.shape != y.shape:
        raise ValueError(f"x and y must have the same shape. Got {x.shape} vs {y.shape}.")

    finite_mask = np.isfinite(x) & np.isfinite(y)
    x_f = x[finite_mask]
    y_f = y[finite_mask]

    if x_f.size == 0:
        return x_f, y_f

    lo = float(min(x_min, x_max))
    hi = float(max(x_min, x_max))

    lo_ext = lo - float(left_margin_x)
    hi_ext = hi + float(right_margin_x)

    is_sorted = np.all(np.diff(x_f) >= 0)

    if is_sorted:
        left = int(np.searchsorted(x_f, lo_ext, side="left"))
        right = int(np.searchsorted(x_f, hi_ext, side="right"))
        return x_f[left:right], y_f[left:right]

    mask = (x_f >= lo_ext) & (x_f <= hi_ext)
    return x_f[mask], y_f[mask]


def zoom_sa(
    *,
    x: Optional[np.ndarray] = None,
    y: Optional[np.ndarray] = None,
    x1: Optional[float] = None,
    x2: Optional[float] = None,
    traces: Optional[Iterable[Trace]] = None,
    rebase_x_to_left_marker: bool = False,
    xspan_threshold_for_marker_detection: float = 0.01,

    # NEW: tail control as fraction of zoom width
    tail_fraction: float = 0.0,          # same fraction on both sides
    tail_left_fraction: Optional[float] = None,
    tail_right_fraction: Optional[float] = None,
) -> ZoomResult:
    # --- same marker / spectrum selection as your current code ---
    if traces is not None:
        marker_xs, spectrum = _detect_marker_x_positions_from_traces(
            traces, xspan_threshold=xspan_threshold_for_marker_detection
        )
        if spectrum is None:
            raise ValueError("Could not find a spectrum trace (large X-span) in traces.")
        if len(marker_xs) < 2:
            raise ValueError("Could not detect at least two marker X positions from traces.")

        marker_xs_sorted = sorted(marker_xs)
        x1v = marker_xs_sorted[0]
        x2v = marker_xs_sorted[-1]
        x = spectrum.x
        y = spectrum.y
    else:
        if x is None or y is None or x1 is None or x2 is None:
            raise ValueError("Provide either traces=... OR x,y,x1,x2.")
        x1v = _as_float(x1)
        x2v = _as_float(x2)

    x_min = min(x1v, x2v)
    x_max = max(x1v, x2v)
    xmid = (x_min + x_max) / 2.0

    # --- compute margins in X-units ---
    width = float(x_max - x_min)
    lf = tail_left_fraction if tail_left_fraction is not None else tail_fraction
    rf = tail_right_fraction if tail_right_fraction is not None else tail_fraction

    left_margin_x = max(0.0, float(lf) * width)
    right_margin_x = max(0.0, float(rf) * width)

    x_zoom, y_zoom = _crop_spectrum_between(
        np.asarray(x),
        np.asarray(y),
        x_min,
        x_max,
        left_margin_x=left_margin_x,
        right_margin_x=right_margin_x,
    )

    if rebase_x_to_left_marker:
        # NOTE: left tail will become negative after rebasing, which is expected.
        x_zoom = x_zoom - x_min
        x1r, x2r, xmidr = 0.0, width, (xmid - x_min)
        return ZoomResult(x_zoom=x_zoom, y_zoom=y_zoom, x1=x1r, x2=x2r, xmid=xmidr, rebase=True)

    return ZoomResult(x_zoom=x_zoom, y_zoom=y_zoom, x1=x_min, x2=x_max, xmid=xmid, rebase=False)


# --- Motor / Angle Control (moved from PER_EDITED into main GUI) ---
# --- Motor / Angle Control (moved from PER_EDITED into main GUI) ---
class _AptMotorBackend:
    """
    Motor backend for Thorlabs controllers.

    Priority:
      1) thorlabs_apt (legacy; works for some APT-era devices)
      2) Thorlabs Kinesis .NET via pythonnet (recommended; works for T-Cube Brushless, etc.)

    Your controller (from your screenshot):
      - T-Cube Brushless Motor Controller, S/N 67431294

    NOTE: Many newer Kinesis devices are NOT supported by thorlabs_apt.
    """
    def __init__(self, logger=None):
        self._log = logger or (lambda msg: None)
        self._driver = None   # "apt" | "kinesis"
        self._dev = None
        self.serial = None

    def _import_clr_kinesis(self):
        """Ensure pythonnet is loaded and `clr` is importable (pythonnet 3.x needs pythonnet.load())."""
        try:
            import clr  # type: ignore
            return clr
        except ModuleNotFoundError:
            pass

        # pythonnet may be installed but `clr` is unavailable until pythonnet.load()
    #    try:
    #        import pythonnet  # type: ignore
    #    except Exception as e:
         #   raise RuntimeError(
         #       "pythonnet is not installed in this Python environment. "
          #      "Install with: pip install pythonnet. "
          #      f"(sys.executable={sys.executable}) Details: {e}"
         #   ) from e

        # Try explicit .NET Framework runtime first (most Thorlabs Kinesis installs are netfx)
        load_err = None
        for args in (("netfx",), tuple()):
            try:
                pythonnet.load(*args)  # type: ignore
                import clr  # type: ignore
                return clr
            except Exception as e:
                load_err = e

        raise RuntimeError(
            "pythonnet is installed but failed to load the .NET runtime, so `clr` is not available. "
            "Common causes: running in a different Python than where pythonnet was installed, "
            "or missing .NET Framework runtime. "
            f"(sys.executable={sys.executable}) Error: {load_err}"
        ) from load_err

    
    def _ensure_kinesis_settings(self, timeout_ms: int = 20000):
        """Ensure Kinesis device settings are fully initialized + applied."""
        if not self.is_connected() or self._driver != "kinesis":
            return

        dev = self._dev

        # Polling + enable first (some devices won't finalize settings otherwise)
        try:
            dev.StartPolling(250)
        except Exception:
            pass

        try:
            dev.EnableDevice()
        except Exception:
            pass

        try:
        #    import time as _time
            _time.sleep(0.25)
        except Exception:
            pass

        # Wait for settings
        try:
            dev.WaitForSettingsInitialized(int(timeout_ms))
        except Exception:
            pass

        # Load configuration
        try:
            cfg = dev.LoadMotorConfiguration(str(self.serial))
        except Exception:
            cfg = None

        # Some device families require applying settings explicitly
        if cfg is not None:
            for meth_name in ("SetSettings", "ApplySettings"):
                fn = getattr(dev, meth_name, None)
                if callable(fn):
                    try:
                        if meth_name == "SetSettings":
                            ds = getattr(cfg, "DeviceSettings", None)
                            if ds is not None:
                                fn(ds, True, False)
                        else:
                            fn(cfg)
                        break
                    except Exception:
                        pass

# ---------------- discovery ----------------
    def list_devices(self):
        """Return list of serial numbers (strings).

        NOTE: For your T-Cube Brushless controller, Kinesis is the reliable path.
        `thorlabs_apt` uses a legacy native DLL (APT.dll) that often fails when re-running
        in the same Python process (e.g., Spyder/IDLE) and may not support newer devices.
        Set environment variable USE_THORLABS_APT=1 if you *really* want to try APT.
        """
        # Prefer Kinesis .NET (recommended)
        sns = []
        try:
            clr = self._import_clr_kinesis()
          #  import sys, os

            kinesis_dir = r"C:\Program Files\Thorlabs\Kinesis"
            if os.path.isdir(kinesis_dir) and kinesis_dir not in sys.path:
                sys.path.append(kinesis_dir)

            clr.AddReference("Thorlabs.MotionControl.DeviceManagerCLI")
            from Thorlabs.MotionControl.DeviceManagerCLI import DeviceManagerCLI  # type: ignore

            DeviceManagerCLI.BuildDeviceList()

            try:
                for sn in DeviceManagerCLI.GetDeviceList():
                    s = str(sn).strip()
                    if s:
                        sns.append(s)
            except Exception:
                pass

            sns = sorted(list(dict.fromkeys(sns)))
        except Exception:
            pass

        # Optional: legacy APT enumeration (ONLY if user explicitly enables it)
        try:
           # import os as _os
            if not bool(os.environ.get("USE_THORLABS_APT", "")):
                return sns
        except Exception:
            return sns

        try:
            import thorlabs_apt as apt  # type: ignore
            devs = apt.list_available_devices() or []
            for item in devs:
                try:
                    sn = str(item[1]).strip()
                    if sn:
                        sns.append(sn)
                except Exception:
                    continue
            return sorted(list(dict.fromkeys(sns)))
        except Exception:
            return sorted(list(dict.fromkeys(sns)))

    # ---------------- connection ----------------
    def connect(self, serial=None):
        # Disconnect current device before connecting to a new one
        if self.is_connected():
            self.disconnect()
        """Connect to a supported Thorlabs Kinesis motor controller by serial."""
        serial = (str(serial).strip() if serial is not None else "")
        devs = self.list_devices()
        if not serial:
            if devs:
                serial = devs[0]
        if not serial:
            raise RuntimeError("Serial number required (e.g., 27271352).")
        clr = self._import_clr_kinesis()
        kinesis_dir = r"C:\Program Files\Thorlabs\Kinesis"
        if os.path.isdir(kinesis_dir) and kinesis_dir not in sys.path:
            sys.path.append(kinesis_dir)
        clr.AddReference("System")
        clr.AddReference("Thorlabs.MotionControl.DeviceManagerCLI")
        from Thorlabs.MotionControl.DeviceManagerCLI import DeviceManagerCLI  # type: ignore
        DeviceManagerCLI.BuildDeviceList()
        try:
            device_list = DeviceManagerCLI.GetDeviceList()
        except Exception:
            device_list = []
        available_serials = [str(x).strip() for x in device_list] if device_list else []
        # No popups: auto-resolve serial when multiple devices are present.
        if device_list and str(serial) not in available_serials:
            # Prefer the first enumerated serial if requested one is missing.
            if available_serials:
                serial = available_serials[0]
            else:
                raise RuntimeError(f"Device {serial} not found. Available: {available_serials}")
        # Build family-specific candidate list from Kinesis APIs so we don't try
        # non-motor/global serials with wrong motor classes.
        serial_s = str(serial).strip()
        families = []
        family_errors = []
        family_specs = [
            # DC servo families
            ("Thorlabs.MotionControl.KCube.DCServoCLI", "KCubeDCServo", "CreateKCubeDCServo"),
            ("Thorlabs.MotionControl.TCube.DCServoCLI", "TCubeDCServo", "CreateTCubeDCServo"),
            # Stepper families (some 27xxxxxx controllers are stepper)
            ("Thorlabs.MotionControl.KCube.StepperMotorCLI", "KCubeStepper", "CreateKCubeStepper"),
            ("Thorlabs.MotionControl.TCube.StepperMotorCLI", "TCubeStepper", "CreateTCubeStepper"),
            # Brushless families
            ("Thorlabs.MotionControl.TCube.BrushlessMotorCLI", "TCubeBrushlessMotor", "CreateTCubeBrushlessMotor"),
            ("Thorlabs.MotionControl.KCube.BrushlessMotorCLI", "KCubeBrushlessMotor", "CreateKCubeBrushlessMotor"),
        ]

        for assembly, class_name, factory_name in family_specs:
            try:
                clr.AddReference(assembly)
                mod = __import__(assembly, fromlist=[class_name])
                cls = getattr(mod, class_name)
                prefix = getattr(cls, "DevicePrefix", None)
                sns = []
                try:
                    if prefix is not None:
                        sns = [str(x).strip() for x in DeviceManagerCLI.GetDeviceList(prefix)]
                except Exception:
                    sns = []
                if serial_s in sns:
                    families.append((assembly, class_name, factory_name))
            except Exception as e:
                family_errors.append(f"{class_name}: probe failed ({e})")

        # Fallback order only if family-specific query couldn't classify the serial.
        if not families:
            # Use a practical order by likely hardware family.
            by_name = {item[1]: item for item in family_specs}
            if serial_s.startswith("67"):
                order_names = [
                    "TCubeBrushlessMotor", "KCubeBrushlessMotor",
                    "TCubeDCServo", "KCubeDCServo",
                    "TCubeStepper", "KCubeStepper",
                ]
            elif serial_s.startswith("28"):
                order_names = [
                    "KCubeBrushlessMotor", "TCubeBrushlessMotor",
                    "KCubeDCServo", "TCubeDCServo",
                    "KCubeStepper", "TCubeStepper",
                ]
            elif serial_s.startswith("27"):
                order_names = [
                    "KCubeDCServo", "TCubeDCServo",
                    "KCubeStepper", "TCubeStepper",
                    "KCubeBrushlessMotor", "TCubeBrushlessMotor",
                ]
            else:
                order_names = [item[1] for item in family_specs]
            families = [by_name[n] for n in order_names if n in by_name]

        errors = []
        for assembly, class_name, factory_name in families:
            try:
                clr.AddReference(assembly)
            except Exception as e:
                errors.append(f"{class_name}: load '{assembly}' failed ({e})")
                continue

            try:
                mod = __import__(assembly, fromlist=[class_name])
                cls = getattr(mod, class_name)
                factory = getattr(cls, factory_name)
                dev = factory(serial_s)
            except Exception as e:
                errors.append(f"{class_name}: create failed ({e})")
                continue

            if dev is None:
                errors.append(f"{class_name}: factory returned None")
                continue

            # Retry once after forcing DeviceManager refresh.
            last_connect_err = None
            for attempt in (1, 2):
                try:
                    DeviceManagerCLI.BuildDeviceList()
                except Exception:
                    pass
                _time.sleep(0.2)

                try:
                    dev.Connect(serial_s)  # type: ignore
                    _time.sleep(0.5)
                    try:
                        dev.WaitForSettingsInitialized(10000)  # type: ignore
                        dev.LoadMotorConfiguration(serial_s)  # type: ignore
                    except Exception:
                        pass
                    _time.sleep(0.2)
                    try:
                        dev.StartPolling(250)  # type: ignore
                    except Exception:
                        pass
                    _time.sleep(0.2)
                    try:
                        dev.EnableDevice()  # type: ignore
                    except Exception:
                        pass
                    _time.sleep(0.2)

                    self._dev = dev
                    self._driver = "kinesis"
                    self.serial = serial_s
                    self._log(f"[MOTOR] Connected via Kinesis .NET ({class_name}) to SN {serial_s}")
                    return True
                except Exception as e:
                    last_connect_err = e
                    # release stale device handle before retry
                    try:
                        dev.Disconnect(True)  # type: ignore
                    except Exception:
                        try:
                            dev.Disconnect()  # type: ignore
                        except Exception:
                            pass
                    if attempt == 1 and "Device is not connected" in str(e):
                        self._log(f"[MOTOR] {class_name} first connect failed; refreshing Kinesis list and retrying once.")
                        _time.sleep(0.4)
                        continue
                    break

            errors.append(f"{class_name}: connect failed ({last_connect_err})")

        detail = " | ".join(errors[-6:])
        if family_errors:
            detail = (detail + " | " if detail else "") + " | ".join(family_errors[-3:])
        # Log error to console
        print(f"[MOTOR] Kinesis connection failed for serial {serial_s}. Attempts: {detail}")
        # Show user notification if in GUI context
        try:
            from PyQt5.QtWidgets import QMessageBox
            msg = QMessageBox()
            msg.setIcon(QMessageBox.Critical)
            msg.setWindowTitle("Motor Connection Error")
            msg.setText(f"Kinesis connection failed for serial {serial_s}.")
            msg.setInformativeText(
                "Troubleshooting steps:\n"
                "1. Ensure the device is powered and connected via USB.\n"
                "2. Check that Thorlabs Kinesis software and drivers are installed.\n"
                "3. Try unplugging/replugging the device or using a different USB port.\n"
                "4. Restart Kinesis and this application.\n\n"
                f"Error details: {detail}"
            )
            msg.exec_()
        except Exception:
            pass
        raise RuntimeError(
            "Kinesis connection failed for serial "
            f"{serial_s}. Attempts: " + detail
        )


    def disconnect(self):

        if not self.is_connected():
            return
        try:
            if self._driver == "apt":
                self._dev = None
            elif self._driver == "kinesis":
                try:
                    self.stop_motion()
                except Exception:
                    pass
                try:
                    self._dev.StopPolling()
                except Exception:
                    pass
                try:
                    # Some devices accept Disconnect(True), others want Disconnect()
                    try:
                        self._dev.Disconnect(True)
                    except Exception:
                        try:
                            self._dev.Disconnect()
                        except Exception:
                            pass
                except Exception:
                    pass
                self._dev = None
        finally:
            self._driver = None
            self.serial = None

    def is_connected(self):
        return self._dev is not None and self._driver in ("apt", "kinesis")

    def home(self):
        if not self.is_connected():
            raise RuntimeError("Motor not connected")
        if self._driver == "apt":
            self._dev.move_home(True)
            return
        self._dev.Home(60000)


    def move_deg(self, angle_deg: float):
        if not self.is_connected():
            raise RuntimeError("Motor not connected")
    
        # APT legacy
        if self._driver == "apt":
            self._dev.move_to(float(angle_deg), True)
            return
    
        # --- Kinesis path ---
        target_f = float(angle_deg)
        timeout_ms = 60000

        # Ensure settings are really ready (fixes: "Device settings not initialized")
        try:
            self._ensure_kinesis_settings(timeout_ms=20000)
        except Exception:
            pass

        from System import Decimal, Int32  # <-- IMPORTANT

        target_d = Decimal(float(target_f))  # Decimal ctor avoids Parse(str) overload issues

        # This matches your device overload:
        # MoveTo(System.Decimal, System.Int32)
        try:
            self._dev.MoveTo(target_d, Int32(timeout_ms))
        except Exception as e:
            # One retry after forcing settings init (some devices need it on first move)
            try:
                self._ensure_kinesis_settings(timeout_ms=20000)
                self._dev.MoveTo(target_d, Int32(timeout_ms))
                return
            except Exception:
                pass
            raise RuntimeError(
                f"Kinesis MoveTo failed for target={target_f}: {e}"
            ) from e

    
        # Optional wait if supported
        for name in (
            "WaitForMoveToComplete",
            "WaitForMovementCompleted",
            "WaitForMoveCompleted",
        ):
            fn = getattr(self._dev, name, None)
            if callable(fn):
                try:
                    fn(timeout_ms)
                    break
                except Exception:
                    pass

    def configure_jog(self, step_deg: float, velocity_deg_s: float = 10.0):
        """Configure Kinesis single-step jog (same style as KDC101_Power_Meter_Insight_Code)."""
        if not self.is_connected():
            raise RuntimeError("Motor not connected")
        if self._driver == "apt":
            return
        from System import Decimal
        from Thorlabs.MotionControl.GenericMotorCLI.ControlParameters import JogParametersBase  # type: ignore

        jog_params = self._dev.GetJogParams()
        jog_params.StepSize = Decimal(float(step_deg))
        try:
            jog_params.VelocityParams.MaxVelocity = Decimal(float(velocity_deg_s))
        except Exception:
            pass
        jog_params.JogMode = JogParametersBase.JogModes.SingleStep
        self._dev.SetJogParams(jog_params)

    def set_max_velocity(self, velocity_deg_s: float):
        """Best-effort setter for motor max velocity in deg/s."""
        if not self.is_connected() or self._driver == "apt":
            return
        from System import Decimal
        try:
            vp = self._dev.GetVelocityParams()
            vp.MaxVelocity = Decimal(float(velocity_deg_s))
            self._dev.SetVelocityParams(vp)
        except Exception:
            pass

    def jog_forward(self):
        """Move one jog step forward."""
        if not self.is_connected():
            raise RuntimeError("Motor not connected")
        if self._driver == "apt":
            raise RuntimeError("Jog is not implemented for APT backend")
        from Thorlabs.MotionControl.GenericMotorCLI import MotorDirection  # type: ignore
        self._dev.MoveJog(MotorDirection.Forward, 0)

    def is_busy(self) -> bool:
        if not self.is_connected():
            return False
        try:
            return bool(self._dev.IsDeviceBusy)
        except Exception:
            return False

    def start_continuous_forward(self) -> bool:
        """Start continuous forward rotation if supported by the Kinesis API."""
        if not self.is_connected():
            raise RuntimeError("Motor not connected")
        if self._driver == "apt":
            return False
        from Thorlabs.MotionControl.GenericMotorCLI import MotorDirection  # type: ignore
        try:
            self._dev.MoveAtVelocity(MotorDirection.Forward)
            return True
        except Exception:
            pass
        try:
            self._dev.MoveContinuous(MotorDirection.Forward)
            return True
        except Exception:
            return False


    def stop_motion(self):
        """Best-effort stop for continuous/jog motion."""
        if not self.is_connected():
            return
        for name in ("StopImmediate", "StopProfiled", "Stop"):
            fn = getattr(self._dev, name, None)
            if callable(fn):
                try:
                    fn()
                    return
                except TypeError:
                    try:
                        fn(0)
                        return
                    except Exception:
                        pass
                except Exception:
                    pass



    def position_deg(self):
        """Best-effort readback of current position in degrees (or None)."""
        if not self.is_connected():
            return None
        try:
            if self._driver == "apt":
                return float(getattr(self._dev, "position"))
            # Kinesis often exposes Position as Decimal
            try:
                return float(getattr(self._dev, "DevicePosition"))
            except Exception:
                return float(getattr(self._dev, "Position"))
        except Exception:
            try:
                return float(getattr(self._dev, "Position", None))
            except Exception:
                return None

############################### 
           
def _extract_serial_from_usb_instance_id(instance_id: str) -> str:
    """
    Try to extract a useful serial-like token from a Windows PnP InstanceId.
    Examples:
      USB\VID_0403&PID_6001\A9XYZ123  -> A9XYZ123
      USB\VID_1313&PID_????\12345678  -> 12345678
    Returns "" if nothing plausible is found.
    """
    s = (instance_id or "").strip()
    if not s:
        return ""
    # last component after backslash is often the unique ID / serial
    parts = re.split(r"[\\/]+", s)
    tail = parts[-1].strip() if parts else ""
    if not tail or tail.upper().startswith("VID_") or tail.upper().startswith("PID_"):
        return ""
    # If tail contains '&', take last segment (some IDs look like "...&MI_00\<serial>")
    if "&" in tail:
        tail = tail.split("&")[-1].strip()
    # Keep only safe chars
    tail = re.sub(r"[^A-Za-z0-9_-]", "", tail)
    # Prefer a digit-heavy token (Thorlabs serials are usually digits)
    m = re.search(r"(\d{6,})", tail)
    if m:
        return m.group(1)
    return tail if len(tail) >= 6 else ""

def _list_usb_controllers_windows() -> list:
    """
    Best-effort enumeration of Windows USB devices/controllers using PowerShell.
    Returns list of dicts: {name, instance_id, status, class}
    """
    try:
       # import subprocess
       # import csv
        # Get-PnpDevice requires admin? usually not. Works on Win10/11.
        ps = r"""
        $items = @()
        try { $items += Get-PnpDevice -Class USB -ErrorAction SilentlyContinue } catch {}
        try { $items += Get-PnpDevice -Class USBDevice -ErrorAction SilentlyContinue } catch {}
        $items = $items | Sort-Object -Property FriendlyName, InstanceId -Unique
        $items | Select-Object FriendlyName, InstanceId, Status, Class | ConvertTo-Csv -NoTypeInformation
        """
        out = subprocess.check_output(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps],
            stderr=subprocess.STDOUT,
            text=True,
            timeout=10,
        )
        rows = []
        reader = csv.DictReader([ln for ln in out.splitlines() if ln.strip()])
        for r in reader:
            name = (r.get("FriendlyName") or "").strip()
            iid = (r.get("InstanceId") or "").strip()
            status = (r.get("Status") or "").strip()
            cls = (r.get("Class") or "").strip()
            if not name and not iid:
                continue
            rows.append({"name": name, "instance_id": iid, "status": status, "class": cls})
        return rows
    except Exception:
        return []

def _list_usb_controllers() -> list:
    """Cross-platform wrapper. On non-Windows returns empty list."""
    if sys.platform.startswith("win"):
        return _list_usb_controllers_windows()
    return []

class MotorControlPanel(QWidget):
    per_sample_ready = pyqtSignal(float, float)
    per_run_finished = pyqtSignal(object, object, str)
    """
    Motor/angle control panel for Thorlabs rotation stage controllers.

    Your setup note:
      - If the rotation stage shows up as **APT USB Device**, it typically won't appear as a COM port.
      - This panel connects through APT/Kinesis APIs (not PyVISA, not serial).
      - If you leave the Serial field empty, it will auto-connect to the first detected device.

    Added in this patch:
      - A Windows Device Manager (PnP) USB dropdown so you can explicitly pick **APT USB Device**.
    """
    def __init__(self, parent=None, status_logger=None):
        super().__init__(parent)
        self._status_logger = status_logger  # optional: main GUI log_status
        self.backend = _AptMotorBackend(logger=self._log)
        self._preferred_motor_serial = "27271352"
        self._per_widget = None
        self._pm_settings_panel = None
        self._sweep_abort = False
        self._pm_none_warned = False
        self._sweep_thread = None
        self._usb_rows = []  # cache of dicts from _list_usb_controllers()
        self._build_ui()
        self._wire()
        self.per_sample_ready.connect(self._on_per_sample_ready)
        self.per_run_finished.connect(self._on_per_run_finished)
        self._update_ui_connected(False)

    def _on_per_sample_ready(self, angle_deg: float, power_dbm: float):
        perw = getattr(self, "_per_widget", None)
        if perw is None:
            return
        try:
            perw.add_power_sample(float(power_dbm), x_value=float(angle_deg))
        except Exception:
            pass

    def _trim_continuous_per_tail_sample(self, angles_deg, powers_dbm, near_zero_threshold: float = 0.01):
        """Drop a trailing near-zero wraparound angle from continuous PER results."""
        try:
            angles = list(angles_deg)
            powers = list(powers_dbm)
        except Exception:
            return angles_deg, powers_dbm

        if len(angles) < 2 or len(angles) != len(powers):
            return angles, powers

        try:
            last_angle = float(angles[-1])
            prev_angle = float(angles[-2])
        except Exception:
            return angles, powers

        if abs(last_angle) <= float(near_zero_threshold) and prev_angle > float(near_zero_threshold):
            return angles[:-1], powers[:-1]

        return angles, powers

    def _on_per_run_finished(self, angles_deg, powers_dbm, msg: str):
        perw = getattr(self, "_per_widget", None)
        try:
            self.btn_sweep_2x360.setEnabled(True)
            self.btn_abort_sweep.setEnabled(False)
        except Exception:
            pass
        angles_deg, powers_dbm = self._trim_continuous_per_tail_sample(angles_deg, powers_dbm)
        if perw is not None:
            try:
                if hasattr(perw, "set_power_samples"):
                    perw.set_power_samples(list(angles_deg), list(powers_dbm))
            except Exception:
                pass
            try:
                perw.stop_per(False)
            except Exception:
                pass
        self._log(str(msg))

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)

        box = QGroupBox("Angle Control (APT USB / Kinesis)")
        g = QGridLayout(box)
        g.setContentsMargins(8, 8, 8, 8)
        g.setHorizontalSpacing(10)
        g.setVerticalSpacing(6)

        self.edt_motor_sn = QLineEdit("")
        self.edt_motor_sn.setPlaceholderText("Serial number (optional). Leave blank for auto-detect.")

        self.btn_motor_refresh = QPushButton("Refresh Devices")
        self.cmb_devices = QComboBox()
        self.cmb_devices.setMinimumWidth(220)

        # --- NEW: USB Device Manager enumeration (Windows) ---
        self.btn_usb_refresh = QPushButton("Refresh USB")
        self.cmb_usb_devices = QComboBox()
        self.cmb_usb_devices.setMinimumWidth(420)

        self.btn_motor_connect = QPushButton("Connect Motor")
        self.btn_motor_disconnect = QPushButton("Disconnect Motor")
        self.btn_motor_disconnect.setEnabled(False)

        self.lbl_motor_status = QLabel("Motor: Disconnected")

        self.edt_target_angle = QDoubleSpinBox()
        self.edt_target_angle.setRange(-100000.0, 100000.0)
        self.edt_target_angle.setDecimals(3)
        self.edt_target_angle.setSingleStep(1.0)
        self.edt_target_angle.setSuffix(" °")

        self.btn_motor_move = QPushButton("MOVE")
        self.btn_motor_home = QPushButton("HOME / Go to Initial")

        self.lbl_motor_pos = QLabel("Pos: -- °")

        self.spn_step_deg = QDoubleSpinBox()
        self.spn_step_deg.setRange(0.001, 360.0)
        self.spn_step_deg.setDecimals(3)
        self.spn_step_deg.setSingleStep(0.1)
        self.spn_step_deg.setValue(1.0)
        self.spn_step_deg.setSuffix(" °")

        self.spn_settle_ms = QSpinBox()
        self.spn_settle_ms.setRange(0, 600000)
        self.spn_settle_ms.setValue(150)
        self.spn_settle_ms.setSuffix(" ms")

        self.spn_samples_per_step = QSpinBox()
        self.spn_samples_per_step.setRange(1, 1000)
        self.spn_samples_per_step.setValue(1)

        self.spn_rot_speed = QDoubleSpinBox()
        self.spn_rot_speed.setRange(0.1, 200.0)
        self.spn_rot_speed.setDecimals(2)
        self.spn_rot_speed.setSingleStep(0.5)
        self.spn_rot_speed.setValue(10.0)
        self.spn_rot_speed.setSuffix(" deg/s")

        self.btn_sweep_2x360 = QPushButton("2×360 SWEEP (PER)")
        self.btn_abort_sweep = QPushButton("ABORT")

        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setMinimumHeight(110)

        # Layout
        g.addWidget(QLabel("Serial"), 0, 0)
        g.addWidget(self.edt_motor_sn, 0, 1, 1, 3)
        g.addWidget(self.btn_motor_connect, 0, 4)
        g.addWidget(self.btn_motor_disconnect, 0, 5)

        g.addWidget(QLabel("Detected (APT/Kinesis)"), 1, 0)
        g.addWidget(self.cmb_devices, 1, 1, 1, 2)
        g.addWidget(self.btn_motor_refresh, 1, 3)

        g.addWidget(QLabel("USB (Device Manager)"), 2, 0)
        g.addWidget(self.cmb_usb_devices, 2, 1, 1, 4)
        g.addWidget(self.btn_usb_refresh, 2, 5)

        g.addWidget(self.lbl_motor_status, 3, 0, 1, 3)
        g.addWidget(self.lbl_motor_pos, 3, 3, 1, 3)

        g.addWidget(QLabel("Target"), 4, 0)
        g.addWidget(self.edt_target_angle, 4, 1)
        g.addWidget(self.btn_motor_move, 4, 2)
        g.addWidget(self.btn_motor_home, 4, 3, 1, 3)

        g.addWidget(QLabel("Sweep"), 5, 0)
        g.addWidget(self.spn_step_deg, 5, 1)
        g.addWidget(self.spn_settle_ms, 5, 2)
        g.addWidget(self.spn_samples_per_step, 5, 3)
        g.addWidget(QLabel("Speed"), 5, 4)
        g.addWidget(self.spn_rot_speed, 5, 5)
        g.addWidget(self.btn_sweep_2x360, 6, 0, 1, 4)
        g.addWidget(self.btn_abort_sweep, 6, 4, 1, 2)

        g.addWidget(self.log_box, 7, 0, 1, 6)

        outer.addWidget(box)
        box.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def _wire(self):
        # Button wiring (guarded to avoid killing the whole Settings tab)
        self.btn_motor_refresh.clicked.connect(self._refresh_devices)
        self.btn_usb_refresh.clicked.connect(self._refresh_usb_devices)
        self.cmb_usb_devices.currentIndexChanged.connect(self._on_usb_device_selected)

        self.btn_motor_connect.clicked.connect(self._connect_motor)
        self.btn_motor_disconnect.clicked.connect(self._disconnect_motor)
        self.btn_motor_home.clicked.connect(self._home_motor)
        self.btn_motor_move.clicked.connect(self._move_motor)

        self.btn_sweep_2x360.clicked.connect(self._start_2x360_sweep)
        self.btn_abort_sweep.clicked.connect(self._abort_sweep)
        self.edt_motor_sn.returnPressed.connect(self._connect_motor)

        # Auto-refresh once at startup (never raise)
        try:
            self._refresh_devices()
        except Exception as e:
            self._log(f"[MOTOR] Refresh devices failed: {e}")
        try:
            self._refresh_usb_devices()
        except Exception as e:
            self._log(f"[MOTOR] Refresh USB failed: {e}")

    def _log(self, msg: str):
        try:
            self.log_box.append(str(msg))
        except Exception:
            pass
        try:
            if callable(self._status_logger):
                self._status_logger(str(msg), "INFO")
        except Exception:
            pass

    def _update_ui_connected(self, connected: bool):
        self.btn_motor_connect.setEnabled(not connected)
        self.btn_motor_disconnect.setEnabled(connected)
        self.btn_motor_move.setEnabled(connected)
        self.btn_motor_home.setEnabled(connected)

    def _refresh_devices(self):
        self.cmb_devices.clear()
        try:
            devs = self.backend.list_devices()
        except Exception as e:
            self.cmb_devices.addItem("(error)")
            self._log(f"[MOTOR] Device enumerate failed: {e}")
            return

        if not devs:
            self.cmb_devices.addItem("(none)")
            self._log("[MOTOR] No APT/Kinesis devices detected.")
            return
        pref = (self._preferred_motor_serial or "").strip()
        filtered = [str(s).strip() for s in devs if str(s).strip()]
        if pref and pref in filtered:
            filtered = [pref]
            self.edt_motor_sn.setText(pref)
            self._log(f"[MOTOR] Detected device(s): {', '.join(devs)}")
            self._log(f"[MOTOR] Device list locked to preferred serial: {pref}")
        else:
            self._log(f"[MOTOR] Detected device(s): {', '.join(filtered)}")

        for sn in filtered:
            self.cmb_devices.addItem(str(sn))

    def _refresh_usb_devices(self):
        """Populate the USB dropdown with devices from Windows Device Manager (PnP)."""
        self.cmb_usb_devices.clear()
        self._usb_rows = _list_usb_controllers()
        if not self._usb_rows:
            self.cmb_usb_devices.addItem("(none)")
            self.cmb_usb_devices.setItemData(0, "(none)")
            self._log("[MOTOR] No USB devices found via PnP enumeration (or not running on Windows).")
            return

        best_idx = None
        for i, row in enumerate(self._usb_rows):
            name = (row.get("name") or "").strip() or "(no friendly name)"
            status = (row.get("status") or "").strip()
            cls = (row.get("class") or "").strip()
            iid = (row.get("instance_id") or "").strip()

            disp = f"{name}  [{cls}]  ({status})"
            if "apt usb" in name.lower():
                disp = "★ " + disp
                if best_idx is None:
                    best_idx = i

            self.cmb_usb_devices.addItem(disp)
            # store instance id as item data
            self.cmb_usb_devices.setItemData(self.cmb_usb_devices.count() - 1, iid)

        if best_idx is not None:
            self.cmb_usb_devices.setCurrentIndex(best_idx)
            # selecting triggers _on_usb_device_selected

        self._log(f"[MOTOR] USB (PnP) entries: {len(self._usb_rows)}")

    def _on_usb_device_selected(self):
        """When user picks a USB entry, auto-fill the Serial field when possible."""
        try:
            iid = (self.cmb_usb_devices.itemData(self.cmb_usb_devices.currentIndex()) or "").strip()
        except Exception:
            iid = ""

        if not iid or iid == "(none)":
            return

        sn = _extract_serial_from_usb_instance_id(iid)
        pref = (self._preferred_motor_serial or "").strip()
        if pref:
            # Keep serial fixed to preferred motor for this setup.
            self.edt_motor_sn.setText(pref)
            return
        if sn:
            if not (self.edt_motor_sn.text() or "").strip():
                self.edt_motor_sn.setText(sn)
            self._log(f"[MOTOR] USB selection → parsed serial '{sn}' from instance_id.")
        else:
            self._log("[MOTOR] USB selection: could not parse a serial from InstanceId (this is OK).")

    def _connect_motor(self):
        try:
            sn = (self.edt_motor_sn.text() or "").strip()

            def _is_likely_motor_serial(s: str) -> bool:
                ss = (s or "").strip()
                if not ss or ss in ("(none)", "(error)"):
                    return False
                # Common Thorlabs motor/controller prefixes:
                # 27=KCube DC Servo, 28=KCube Brushless, 67=TCube Brushless
                return ss.startswith(("27", "28", "67"))

            candidates = []
            if sn and sn.lower() != "auto":
                candidates.append(sn)
            else:
                # Preferred from combo current selection
                try:
                    pick = (self.cmb_devices.currentText() or "").strip()
                    if pick and pick not in ("(none)", "(error)"):
                        candidates.append(pick)
                except Exception:
                    pass
                # Add full detected list, likely-motor serials first
                try:
                    devs = [str(d).strip() for d in (self.backend.list_devices() or []) if str(d).strip()]
                except Exception:
                    devs = []
                devs = sorted(devs, key=lambda s: (0 if _is_likely_motor_serial(s) else 1, s))
                for d in devs:
                    if d not in candidates:
                        candidates.append(d)

            if not candidates:
                candidates = [None]

            last_err = None
            connected_sn = None
            for cand in candidates:
                try:
                    self.backend.connect(cand if cand else None)
                    connected_sn = cand
                    break
                except Exception as e:
                    last_err = e
                    self._log(f"[MOTOR] Skipping serial '{cand}': {e}")

            if connected_sn is None and not self.backend.is_connected():
                raise (last_err or RuntimeError("No connectable motor serial found."))

            self.lbl_motor_status.setText("Motor: Connected")
            self._update_ui_connected(True)
            self._update_position_label()
            self._log(f"[MOTOR] Connected (serial='{connected_sn or sn or 'auto'}').")
            return True
        except Exception as e:
            self.lbl_motor_status.setText("Motor: Disconnected")
            self._update_ui_connected(False)
            self._log(f"[MOTOR] Connect failed: {e}")
            return False

    def _disconnect_motor(self):
        try:
            self._sweep_abort = True
            with contextlib.suppress(Exception):
                self.backend.stop_motion()
            self.backend.disconnect()
        finally:
            self.lbl_motor_status.setText("Motor: Disconnected")
            self.lbl_motor_pos.setText("Pos: -- °")
            self._update_ui_connected(False)
            self._log("[MOTOR] Disconnected.")

    def _update_position_label(self):
        try:
            pos = self.backend.position_deg()
        except Exception:
            pos = None
        if pos is None:
            self.lbl_motor_pos.setText("Pos: -- °")
        else:
            self.lbl_motor_pos.setText(f"Pos: {pos:.3f} °")

    def _home_motor(self):
        try:
            self.backend.home()
            self._log("[MOTOR] HOME complete.")
            self._update_position_label()
            return True
        except Exception as e:
            self._log(f"[MOTOR] HOME failed: {e}")
            return False

    def _move_motor(self):
        try:
            ang = float(self.edt_target_angle.value())
            vel = float(self.spn_rot_speed.value())
            self.backend.set_max_velocity(vel)
            self.backend.move_deg(ang)
            self._log(f"[MOTOR] MOVE → {ang:.3f}° complete.")
            self._update_position_label()
        except Exception as e:
            self._log(f"[MOTOR] MOVE failed: {e}")

    # ----------------------------
    # PER sweep (2×360) integration
    # ----------------------------
    def set_per_components(self, per_widget=None, pm_settings_panel=None):
        """Attach PER tab + power-meter settings so SWEEP can measure+plot."""
        self._per_widget = per_widget
        self._pm_settings_panel = pm_settings_panel

    def _abort_sweep(self):
        self._sweep_abort = True
        with contextlib.suppress(Exception):
            self.backend.stop_motion()
        self._log("Sweep: abort requested.")

    def _get_power_sample_w(self):
        """Best-effort single power sample in Watts using PowerMeterSettingsPanel logic."""
        pmp = getattr(self, "_pm_settings_panel", None)
        if pmp is None:
            return None
        fn = getattr(pmp, "_get_power_sample_w", None)
        if callable(fn):
            try:
                return float(fn())
            except Exception:
                return None
        # Fallback: try common names
        for name in ("get_power_w", "read_power_w", "read_w", "read_power", "get_power_dbm", "read_dbm", "read_power_dbm"):
            f2 = getattr(pmp, name, None)
            if callable(f2):
                try:
                    return float(f2())
                except Exception:
                    return None
        return None

    def _get_power_sample_dbm(self):
        pmp = getattr(self, "_pm_settings_panel", None)
        if pmp is None:
            return None
        fn = getattr(pmp, "_get_power_sample_dbm", None)
        if callable(fn):
            try:
                return float(fn())
            except Exception:
                return None
        return None


    def _to_float(self, value):
        """Best-effort conversion for .NET numeric types such as System.Decimal."""
        try:
            return float(value)
        except TypeError:
            return float(str(value))


    def _start_continuous_per(self):
        """Start continuous PER rotation/measurement until aborted."""
        if not self.backend.is_connected():
            self._log("PER: motor not connected.")
            return
        perw = getattr(self, "_per_widget", None)
        if perw is None:
            self._log("PER: PER tab not attached (no per_widget).")
            return
        pmp = getattr(self, "_pm_settings_panel", None)
        if pmp is None:
            self._log("PER: Power meter settings panel not attached.")
            return

        if getattr(self, "_sweep_thread", None) is not None and self._sweep_thread.is_alive():
            self._log("PER: already running.")
            return

        step_deg = float(self.spn_step_deg.value())
        if step_deg <= 0:
            self._log("PER: step must be > 0.")
            return

        vel_deg_s = float(self.spn_rot_speed.value())
        settle_ms = int(self.spn_settle_ms.value())
        sample_dt_s = 0.05

        try:
            perw.clear()
        except Exception:
            pass
        try:
            if hasattr(pmp, "_poll_timer"):
                pmp._poll_timer.stop()
        except Exception:
            pass

        self._sweep_abort = False
        try:
            self.btn_sweep_2x360.setEnabled(False)
            self.btn_abort_sweep.setEnabled(True)
        except Exception:
            pass

        def worker():
            ok = True
            msg = "PER continuous run stopped"
            angles_deg = []
            powers_dbm = []
            try:
                controller = getattr(self.backend, "_dev", None)
                inst = pmp._pm_inst() if hasattr(pmp, "_pm_inst") else None

                if controller is not None and getattr(self.backend, "_driver", "") == "kinesis" and inst is not None:
                    from System import Decimal
                    from Thorlabs.MotionControl.DeviceManagerCLI import DeviceConfiguration  # type: ignore
                    from Thorlabs.MotionControl.GenericMotorCLI import MotorDirection  # type: ignore
                    from Thorlabs.MotionControl.GenericMotorCLI.ControlParameters import JogParametersBase  # type: ignore
                   # from KDC101_Power_Meter_Insight_Code import _to_float

                    try:
                        controller.StartPolling(50)
                    except Exception:
                        pass
                    _time.sleep(0.1)
                    try:
                        controller.EnableDevice()
                    except Exception:
                        pass
                    _time.sleep(0.1)

                    try:
                        serial_num = str(getattr(self.backend, "serial", "") or "").strip()
                        if serial_num:
                            config = controller.LoadMotorConfiguration(
                                serial_num,
                                DeviceConfiguration.DeviceSettingsUseOptionType.UseDeviceSettings,
                            )
                            config.DeviceSettingsName = str("PRM1-Z8")
                            config.UpdateCurrentConfiguration()
                    except Exception as e:
                        self._log(f"PER: motor configuration warning: {e}")

                    try:
                        wavelength_nm = float(pmp.spn_wavelength.value()) if hasattr(pmp, "spn_wavelength") else 635.0
                        inst.write(f"SENS:CORR:WAV {wavelength_nm:.6f}NM")
                        inst.write("SENS:POW:UNIT DBM")
                    except Exception as e:
                        self._log(f"PER: PM setup warning: {e}")

                    self._log("PER: homing motor.")
                   # controller.Home(60000)

                    jog_step_deg = 360.0
                    try:
                        if hasattr(pmp, "spn_per_jog_step_deg"):
                            jog_step_deg = float(pmp.spn_per_jog_step_deg.value())
                    except Exception:
                        jog_step_deg = 360.0

                    jog_params = controller.GetJogParams()
                    jog_params.StepSize = Decimal(jog_step_deg)
                    jog_params.VelocityParams.MaxVelocity = Decimal(25)
                    jog_params.JogMode = JogParametersBase.JogModes.SingleStep
                    controller.SetJogParams(jog_params)

                    self._log("PER: moving motor.")
                    controller.MoveJog(MotorDirection.Forward, 0)
                    _time.sleep(0.25)
                    while bool(controller.IsDeviceBusy) and not self._sweep_abort:
                        try:
                            power_dbm = float(str(inst.query("MEAS:POW?")).strip())
                        except Exception:
                            power_dbm = float("nan")
                        angle_deg = self._to_float(controller.Position)
                        angles_deg.append(angle_deg)
                        powers_dbm.append(power_dbm)
                     #   print(f"{angle_deg}, {power_dbm}")
                        self.per_sample_ready.emit(float(angle_deg), float(power_dbm))
                        _time.sleep(0.1)
                    try:
                        self.backend.stop_motion()
                    except Exception:
                        pass
                else:
                    self._log("PER: raw Kinesis device unavailable, falling back to GUI jog-step mode.")
                    start_pos = self.backend.position_deg()
                    if start_pos is None:
                        start_pos = 0.0
                    start_pos = float(start_pos)
                    self.backend.set_max_velocity(vel_deg_s)
                    self.backend.configure_jog(step_deg=step_deg, velocity_deg_s=vel_deg_s)
                    circle = 0
                    step_index = 0
                    while not self._sweep_abort:
                        try:
                            self.backend.jog_forward()
                        except Exception as e:
                            raise RuntimeError(f"Jog failed at step {step_index + 1}: {e}") from e

                        if settle_ms > 0:
                            _time.sleep(settle_ms / 1000.0)

                        any_sample = False
                        while self.backend.is_busy() and not self._sweep_abort:
                            pp = self._get_power_sample_dbm()
                            if pp is None:
                                if not getattr(self, "_pm_none_warned", False):
                                    self._pm_none_warned = True
                                    self._log("PER: power sample is None. Connect Power Meter or enable 'Disable PowerMeter' (simulation).")
                                p_val = float("nan")
                            else:
                                p_val = float(pp)
                            any_sample = True

                            pos = self.backend.position_deg()
                            if pos is None:
                                x_angle = float(circle * 360.0 + step_index * step_deg)
                            else:
                                x_angle = float(circle * 360.0 + ((float(pos) - start_pos) % 360.0))
                            angles_deg.append(x_angle)
                            powers_dbm.append(p_val)
                            self.per_sample_ready.emit(float(x_angle), float(p_val))
                            _time.sleep(sample_dt_s)

                        if not any_sample and not self._sweep_abort:
                            pp = self._get_power_sample_dbm()
                            p_val = float(pp) if pp is not None else float("nan")
                            x_angle = float(circle * 360.0 + step_index * step_deg)
                            angles_deg.append(x_angle)
                            powers_dbm.append(p_val)
                            self.per_sample_ready.emit(float(x_angle), float(p_val))

                        step_index += 1
                        if step_index >= max(1, int(round(360.0 / step_deg))):
                            step_index = 0
                            circle += 1

                if self._sweep_abort:
                    ok = False
                    msg = "PER continuous run aborted"

            except Exception as e:
                ok = False
                msg = f"PER continuous run failed: {e}"
            finally:
                try:
                    self.backend.stop_motion()
                except Exception:
                    pass
            self.per_run_finished.emit(angles_deg, powers_dbm, msg)

        self._sweep_thread = _threading.Thread(target=worker, daemon=True)
        self._sweep_thread.start()

    def start_continuous_per(self):
        self._start_continuous_per()

    def connect_motor(self):
        return self._connect_motor()

    def disconnect_motor(self):
        self._disconnect_motor()

    def home_motor(self):
        return self._home_motor()

    def abort_sweep(self):
        self._abort_sweep()

    def start_2x360_sweep(self):
        self._start_2x360_sweep()

    def startup_connect(self):
        with contextlib.suppress(Exception):
            self._refresh_devices()
        with contextlib.suppress(Exception):
            self._refresh_usb_devices()
        if self.backend is not None and self.backend.is_connected():
            self._log("[MOTOR] Startup connect skipped: already connected.")
            return True
        return bool(self.connect_motor())

    def _set_per_home_status(self, text: str):
        perw = getattr(self, "_per_widget", None)
        if perw is None or not hasattr(perw, "set_home_status"):
            return
        try:
            perw.set_home_status(text)
            QApplication.processEvents()
        except Exception:
            pass

    def home_motor_from_per(self):
        self._set_per_home_status("Homing...")
        ok = bool(self.home_motor())
        self._set_per_home_status("Home completed" if ok else "Home failed")
        return ok

    def _start_2x360_sweep(self):
        """Rotate smoothly with jog steps and stream power samples for 2x360."""
        if not self.backend.is_connected():
            self._log("Sweep: motor not connected.")
            return
        perw = getattr(self, "_per_widget", None)
        if perw is None:
            self._log("Sweep: PER tab not attached (no per_widget).")
            return
        pmp = getattr(self, "_pm_settings_panel", None)
        if pmp is None:
            self._log("Sweep: Power meter settings panel not attached.")
            return

        if getattr(self, "_sweep_thread", None) is not None and self._sweep_thread.is_alive():
            self._log("Sweep: already running.")
            return

        step_deg = float(self.spn_step_deg.value())
        if step_deg <= 0:
            self._log("Sweep: step must be > 0.")
            return

        vel_deg_s = float(self.spn_rot_speed.value())
        settle_ms = int(self.spn_settle_ms.value())
        sample_dt_s = 0.05

        try:
            perw.clear()
            perw.start_per()
        except Exception:
            pass

        self._sweep_abort = False
        try:
            self.btn_sweep_2x360.setEnabled(False)
            self.btn_abort_sweep.setEnabled(True)
        except Exception:
            pass

        def worker():
            ok = True
            msg = "Sweep complete"
            try:
                start_pos = self.backend.position_deg()
                if start_pos is None:
                    start_pos = 0.0
                start_pos = float(start_pos)

                steps = int(round(360.0 / step_deg))
                if steps < 1:
                    steps = 1
                self.backend.set_max_velocity(vel_deg_s)
                self.backend.configure_jog(step_deg=step_deg, velocity_deg_s=vel_deg_s)

                # Prefer truly continuous rotation. If not supported, fallback to jog-step mode.
                continuous_ok = self.backend.start_continuous_forward()
                if continuous_ok:
                    self._log("Sweep: using continuous forward rotation.")
                    accum_deg = 0.0
                    prev_pos = start_pos
                    target_total = 720.0
                    if settle_ms > 0:
                        _time.sleep(settle_ms / 1000.0)

                    while accum_deg < target_total:
                        if self._sweep_abort:
                            ok = False
                            msg = "Sweep aborted"
                            break

                        pos = self.backend.position_deg()
                        if pos is not None:
                            pos = float(pos)
                            delta = pos - prev_pos
                            while delta <= -180.0:
                                delta += 360.0
                            while delta > 180.0:
                                delta -= 360.0
                            if delta > 0:
                                accum_deg += delta
                            prev_pos = pos

                        pp = self._get_power_sample_dbm()
                        if pp is None:
                            if not getattr(self, "_pm_none_warned", False):
                                self._pm_none_warned = True
                                self._log("Sweep: power sample is None. Connect Power Meter or enable 'Disable PowerMeter' (simulation).")
                            p_val = float("nan")
                        else:
                            p_val = float(pp)
                        x_angle = min(accum_deg, target_total)
                        QTimer.singleShot(0, lambda val=p_val, x=x_angle: perw.add_power_sample(val, x_value=x))
                        _time.sleep(sample_dt_s)

                    self.backend.stop_motion()
                else:
                    self._log("Sweep: continuous mode unavailable, falling back to jog-step mode.")
                    for circle in range(2):
                        if self._sweep_abort:
                            ok = False
                            msg = "Sweep aborted"
                            break
                        self._log(f"Sweep: circle {circle+1}/2")
                        for i in range(steps):
                            if self._sweep_abort:
                                ok = False
                                msg = "Sweep aborted"
                                break

                            try:
                                self.backend.jog_forward()
                            except Exception as e:
                                raise RuntimeError(f"Jog failed at step {i+1}: {e}") from e

                            if settle_ms > 0:
                                _time.sleep(settle_ms / 1000.0)

                            any_sample = False
                            while self.backend.is_busy():
                                if self._sweep_abort:
                                    ok = False
                                    msg = "Sweep aborted"
                                    break
                                pp = self._get_power_sample_dbm()
                                if pp is None:
                                    if not getattr(self, "_pm_none_warned", False):
                                        self._pm_none_warned = True
                                        self._log("Sweep: power sample is None. Connect Power Meter or enable 'Disable PowerMeter' (simulation).")
                                    p_val = float("nan")
                                else:
                                    p_val = float(pp)
                                any_sample = True

                                pos = self.backend.position_deg()
                                if pos is None:
                                    x_angle = float(circle * 360.0 + i * step_deg)
                                else:
                                    x_angle = float(circle * 360.0 + ((float(pos) - start_pos) % 360.0))
                                QTimer.singleShot(0, lambda val=p_val, x=x_angle: perw.add_power_sample(val, x_value=x))
                                _time.sleep(sample_dt_s)

                            if not ok:
                                break

                            if not any_sample:
                                pp = self._get_power_sample_dbm()
                                p_val = float(pp) if pp is not None else float("nan")
                                x_angle = float(circle * 360.0 + i * step_deg)
                                QTimer.singleShot(0, lambda val=p_val, x=x_angle: perw.add_power_sample(val, x_value=x))

                QTimer.singleShot(0, perw.stop_per)

            except Exception as e:
                ok = False
                msg = f"Sweep failed: {e}"
                try:
                    QTimer.singleShot(0, perw.stop_per)
                except Exception:
                    pass
            finally:
                try:
                    self.backend.stop_motion()
                except Exception:
                    pass

            def finish():
                try:
                    self.btn_sweep_2x360.setEnabled(True)
                    self.btn_abort_sweep.setEnabled(False)
                except Exception:
                    pass
                self._log(msg)

            QTimer.singleShot(0, finish)

        self._sweep_thread = _threading.Thread(target=worker, daemon=True)
        self._sweep_thread.start()
#######################################

#######################################

class OpenCVCameraWrapper:
    """Simple adapter to present an OpenCV VideoCapture as a .grab() camera.

    Notes (Windows):
      - Camera *indices* (0,1,2,...) are assigned by DirectShow/MediaFoundation and may change.
      - Some identical USB UVC cameras may not open reliably with one backend; we allow selecting a backend.
    """
    def __init__(self, index: int = 0, backend: int | None = None):
        self.index = int(index)
        # backend: cv2.CAP_DSHOW (default) or cv2.CAP_MSMF, etc.
        self.backend = backend
        self.cap = None
        self._beam_im = None
        self._beam_cbar = None
    def open(self):
        if self.cap is None:
            # Try to open with the requested backend (default: DirectShow).
            if self.backend is None:
                self.cap = cv2.VideoCapture(self.index, cv2.CAP_DSHOW)
            else:
                self.cap = cv2.VideoCapture(self.index, int(self.backend))

            # IMPORTANT (USB bandwidth / multi-cam reliability):
            # When two identical UVC cameras are opened, default resolution/FPS can exceed USB bandwidth
            # and both streams may freeze. Force a conservative MJPG + 640x480 @ 15fps setup.
            try:
                if self.cap is not None and self.cap.isOpened():
                    try:
                        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    except Exception:
                        pass
                    try:
                        self.cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
                    except Exception:
                        pass
                    try:
                        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
                    except Exception:
                        pass
                    try:
                        self.cap.set(cv2.CAP_PROP_FPS, 15)
                    except Exception:
                        pass
            except Exception:
                pass


    def close(self):
        if self.cap is not None:
            try:
                self.cap.release()
            finally:
                self.cap = None

    def is_open(self) -> bool:
        return self.cap is not None and self.cap.isOpened()

    def set_exposure_us(self, exposure_us: float):
        # Many laptop webcams ignore manual exposure through OpenCV. Best-effort only.
        if self.cap is None:
            return
        try:
            self.cap.set(cv2.CAP_PROP_EXPOSURE, float(exposure_us))
        except Exception:
            pass

    def grab(self, timeout_ms: int = 0):
        if self.cap is None:
            self.open()
        if self.cap is None or not self.cap.isOpened():
            return None
        ok, frame = self.cap.read()
        return frame if ok else None
######################################

class BaslerCameraWrapper:
    """Thin wrapper around pypylon.InstantCamera with a similar API to OpenCVCameraWrapper.

    Notes:
      - Device selection can be by serial number (LabVIEW/IMAQdx-like) or by enumeration index.
      - Exposure is set in microseconds (µs), matching your Settings controls.
      - Returns frames as BGR uint8 numpy arrays for easy display/rotation.
    """

    def __init__(self, device_index: int = 0, serial_number: str | None = None):
        self.device_index = int(device_index)
        self.serial_number = (str(serial_number).strip() if serial_number is not None else "")
        self._cam = None
        self._converter = None
        self._is_open = False

    def open(self):
        if self._is_open and self._cam is not None:
            return
        if not _PYPYLON_AVAILABLE:
            raise RuntimeError(
                "pypylon is not installed. Install Basler pylon + pypylon to use 'External Camera'."
            )
        tl = pylon.TlFactory.GetInstance()
        devices = tl.EnumerateDevices()
        if not devices:
            raise RuntimeError("No Basler devices found (pylon EnumerateDevices returned 0).")

        # LabVIEW/IMAQdx-like selection: prefer serial number if provided.
        selected = None
        if getattr(self, "serial_number", ""):
            target = str(self.serial_number).strip()
            for d in devices:
                try:
                    if str(d.GetSerialNumber()).strip() == target:
                        selected = d
                        break
                except Exception:
                    continue
            if selected is None:
                raise RuntimeError(
                    f"Basler serial not found: {target}. Found {len(devices)} device(s). "
                    "Reconnect camera and restart the app if needed."
                )
        else:
            # Auto-pick a *real* camera if pylon emulation is present.
            # Basler's emulation device commonly reports SN '0815-0000'.
            preferred = None
            try:
                for d in devices:
                    try:
                        sn = str(d.GetSerialNumber()).strip()
                    except Exception:
                        sn = ""
                    try:
                        model = str(d.GetModelName()).lower()
                    except Exception:
                        model = ""
                    # Skip common emulation identifiers
                    if sn == "0815-0000" or "emulation" in model:
                        continue
                    preferred = d
                    break
            except Exception:
                preferred = None

            if preferred is not None:
                selected = preferred
            else:
                if self.device_index < 0 or self.device_index >= len(devices):
                    raise RuntimeError(
                        f"Basler device_index={self.device_index} out of range. Found {len(devices)} device(s)."
                    )
                selected = devices[self.device_index]

        self._cam = pylon.InstantCamera(tl.CreateDevice(selected))
        self._cam.Open()

        # Robust defaults (helps when the camera was last left in a triggered mode in pylon Viewer)
        try:
            if hasattr(self._cam, "TriggerMode"):
                self._cam.TriggerMode.SetValue("Off")
        except Exception:
            pass
        try:
            if hasattr(self._cam, "AcquisitionMode"):
                self._cam.AcquisitionMode.SetValue("Continuous")
        except Exception:
            pass
        # Try to keep the stream format predictable
        try:
            if hasattr(self._cam, "PixelFormat"):
                # Prefer Mono8 if available, else leave as-is
                try:
                    self._cam.PixelFormat.SetValue("Mono8")
                except Exception:
                    pass
        except Exception:
            pass


        # Use an image format converter so we always get BGR8 packed output
        self._converter = pylon.ImageFormatConverter()
        self._converter.OutputPixelFormat = pylon.PixelType_BGR8packed
        self._converter.OutputBitAlignment = pylon.OutputBitAlignment_MsbAligned

        # Start grabbing using the most-recent-image-only strategy (good for live preview)
        self._cam.StartGrabbing(pylon.GrabStrategy_LatestImageOnly)
        self._is_open = True

    def close(self):
        try:
            if self._cam is not None:
                if self._cam.IsGrabbing():
                    self._cam.StopGrabbing()
                if self._cam.IsOpen():
                    self._cam.Close()
        except Exception:
            pass
        self._cam = None
        self._converter = None
        self._is_open = False

    def is_open(self) -> bool:
        return bool(self._is_open and self._cam is not None and self._cam.IsOpen())

    def set_exposure_us__(self, exposure_us: float):
        if not self.is_open():
            return
        try:
            # Most Basler cameras expose ExposureTime in microseconds
            if hasattr(self._cam, "ExposureTime"):
                self._cam.ExposureTime.SetValue(float(exposure_us))
        except Exception:
            # If the camera doesn't support ExposureTime (rare), ignore
            pass

    def set_exposure_us(self, exposure_us: float) -> None:
        if self._cam is None:
            raise RuntimeError(
                            "Camera not opened")
    
        exp_us = float(exposure_us)
    
        try:
            # Disable auto exposure if available (important)
            try:
                if hasattr(self._cam, "ExposureAuto"):
                    self._cam.ExposureAuto.SetValue("Off")
            except Exception:
                pass
    
            # Many acAxxxx-gm models use ExposureTimeAbs (µs)
            if hasattr(self._cam, "ExposureTimeAbs"):
                self._cam.ExposureTimeAbs.SetValue(exp_us)
                return
    
            # Newer SFNC-style name
            if hasattr(self._cam, "ExposureTime"):
                self._cam.ExposureTime.SetValue(exp_us)
                return
    
            # Raw fallback (rarely needed, but safe)
            if hasattr(self._cam, "ExposureTimeRaw"):
                self._cam.ExposureTimeRaw.SetValue(int(round(exp_us)))
                return
    
            raise RuntimeError("No exposure node found (ExposureTimeAbs/ExposureTime/ExposureTimeRaw).")
    
        except Exception as e:
            raise RuntimeError(f"Failed to set exposure to {exp_us} us: {e}") from e
    

    def grab(self, timeout_ms: int = 500):
        """Return a BGR frame (numpy array) or None."""
        if not self.is_open():
            return None
        try:
            grab = self._cam.RetrieveResult(int(timeout_ms), pylon.TimeoutHandling_Return)
            if grab is None or not grab.GrabSucceeded():
                try:
                    if grab is not None:
                        grab.Release()
                except Exception:
                    pass
                return None

            # Convert to BGR8 packed
            try:
                img = self._converter.Convert(grab) if self._converter is not None else grab
                arr = img.GetArray()
            finally:
                grab.Release()

            # Some Basler cameras may output Mono8; convert to BGR for consistent downstream display.
            try:
                if arr is not None and getattr(arr, "ndim", 0) == 2:
                    arr = cv2.cvtColor(arr, cv2.COLOR_GRAY2BGR)
            except Exception:
                pass

            return arr  # BGR
        except Exception:
            return None


class _SyncedZoomView(QGraphicsView):
    """A QGraphicsView with wheel-zoom + hand-drag panning, and optional sync to a peer view."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._peer = None
        self._sync_guard = False

        self.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorUnderMouse)
        self.setViewportUpdateMode(QGraphicsView.SmartViewportUpdate)

        # Make scrollbars less visually noisy (still functional)
        try:
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        except Exception:
            pass

    def set_peer(self, peer_view: "_SyncedZoomView"):
        self._peer = peer_view

    def wheelEvent(self, event):
        # Zoom factor
        try:
            delta = event.angleDelta().y()
        except Exception:
            delta = 0

        if delta == 0:
            return super().wheelEvent(event)

        factor = 1.25 if delta > 0 else 0.8
        self._apply_zoom(factor, sync_peer=True)
        event.accept()

    def _apply_zoom(self, factor: float, *, sync_peer: bool):
        if self._sync_guard:
            return

        self._sync_guard = True
        try:
            self.scale(factor, factor)
        finally:
            self._sync_guard = False

        if sync_peer and self._peer is not None:
            try:
                self._peer._apply_zoom(factor, sync_peer=False)
            except Exception:
                pass

    def reset_zoom(self, *, sync_peer: bool = True):
        # Reset transform and fit whole scene
        try:
            self.resetTransform()
        except Exception:
            pass
        try:
            if self.scene() is not None and not self.scene().itemsBoundingRect().isNull():
                self.fitInView(self.scene().itemsBoundingRect(), Qt.KeepAspectRatio)
        except Exception:
            pass

        if sync_peer and self._peer is not None:
            try:
                self._peer.reset_zoom(sync_peer=False)
            except Exception:
                pass


class SecondaryCamerasWindow(QWidget):
    """Pop-off window to show Camera 2 and Camera 3 side-by-side with synchronized zoom/pan."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Camera 2 / Camera 3")
        self.setMinimumSize(980, 520)

        root = QVBoxLayout(self)
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)

        # Top row: info + controls
        top = QHBoxLayout()
        self.info = QLabel("Live views (Camera 2 and Camera 3). Mouse-wheel to zoom; drag to pan. Zoom is synchronized.")
        self.info.setStyleSheet("font-weight: bold;")
        top.addWidget(self.info, 1)

        self.btn_reset = QToolButton()
        self.btn_reset.setText("Reset Zoom")
        self.btn_reset.setToolTip("Reset zoom for both views")
        top.addWidget(self.btn_reset, 0, Qt.AlignRight)

        root.addLayout(top)

        row = QHBoxLayout()
        row.setSpacing(10)
        root.addLayout(row, 1)

        # Scenes + items
        self._scene2 = QGraphicsScene(self)
        self._scene3 = QGraphicsScene(self)
        self._item2 = QGraphicsPixmapItem()
        self._item3 = QGraphicsPixmapItem()
        self._scene2.addItem(self._item2)
        self._scene3.addItem(self._item3)

        # Views
        cam2_box = QGroupBox("Camera 2")
        cam2_layout = QVBoxLayout(cam2_box)
        self.view2 = _SyncedZoomView(self._scene2, self)
        self.view2.setStyleSheet("background:#111; border:1px solid #444;")
        cam2_layout.addWidget(self.view2, 1)
        row.addWidget(cam2_box, 1)

        cam3_box = QGroupBox("Camera 3")
        cam3_layout = QVBoxLayout(cam3_box)
        self.view3 = _SyncedZoomView(self._scene3, self)
        self.view3.setStyleSheet("background:#111; border:1px solid #444;")
        cam3_layout.addWidget(self.view3, 1)
        row.addWidget(cam3_box, 1)

        # Sync peers (zoom only; pan is naturally per-view but since drag is done similarly, it's OK)
        self.view2.set_peer(self.view3)
        self.view3.set_peer(self.view2)

        self.btn_reset.clicked.connect(lambda: self.reset_zoom())

        # Start with a nice fit
        self.reset_zoom()

    def reset_zoom(self):
        self.view2.reset_zoom(sync_peer=True)

    def _set_pixmap_to_item(self, item: QGraphicsPixmapItem, scene: QGraphicsScene, pm: QPixmap | None, disabled_text: str):
        if pm is None or pm.isNull():
            # Show text overlay via scene's background text
            scene.clear()
            t = scene.addText(disabled_text)
            try:
                t.setDefaultTextColor(Qt.lightGray)
            except Exception:
                pass
            # Re-add item for later updates
            item = QGraphicsPixmapItem()
            scene.addItem(item)
            return item

        # Ensure item belongs to scene (scene might have been cleared)
        if item.scene() is None:
            scene.addItem(item)

        item.setPixmap(pm)
        # Expand the scene rect to the pixmap size so fitInView works well
        try:
            scene.setSceneRect(pm.rect())
        except Exception:
            pass
        return item

    def set_cam2_pixmap(self, pm: QPixmap | None):
        self._item2 = self._set_pixmap_to_item(self._item2, self._scene2, pm, "Camera 2 disabled / no frame.")
        # Keep current zoom (do NOT auto-fit every frame)

    def set_cam3_pixmap(self, pm: QPixmap | None):
        self._item3 = self._set_pixmap_to_item(self._item3, self._scene3, pm, "Camera 3 disabled / no frame.")
        # Keep current zoom (do NOT auto-fit every frame)


@dataclass
class ProductRecipe:
    product: str = ""
    source_xml: str = ""
    tec_temp_c: float | None = None
    laser_set_current_ma: float | None = None
    laser_max_current_ma: float | None = None
    laser_max_voltage_v: float | None = None
    laser_max_power_mw: float | None = None

    @staticmethod
    def _to_float(x):
        if x is None:
            return None
        try:
            s = str(x).strip()
            if s == "":
                return None
            return float(s)
        except Exception:
            return None

    @classmethod
    def from_xml(cls, xml_path: str, product: str = ""):
        r = cls(product=product or "", source_xml=xml_path or "")
        try:
            tree = _ET.parse(xml_path)
            root = tree.getroot()
        except Exception:
            return r

        def find_text_by_tags(tags):
            for t in tags:
                el = root.find(".//" + t)
                if el is not None and el.text is not None:
                    return el.text
            return None

        def find_param_by_name(names):
            # Support <Parameter name="...">value</Parameter> and value attributes
            wanted = set([n.lower() for n in names])
            for el in root.iter():
                nm = (el.get("name") or el.get("Name") or el.get("key") or el.get("Key") or "").strip().lower()
                if nm and nm in wanted:
                    v = el.text
                    if v is None:
                        v = el.get("value") or el.get("Value")
                    return v
            return None

        # TEC temperature
        tec_txt = (
            find_text_by_tags(["tec_temp_c", "TEC_Temp_C", "tec_temperature_c"])
            or find_param_by_name(["tec_temp_c", "tec_temperature_c", "tec_setpoint_c", "tec_temp"])
        )
        r.tec_temp_c = cls._to_float(tec_txt)

        # Laser set current
        set_i = (
            find_text_by_tags(["laser_set_current_ma", "LASER_SetCurrent_mA", "set_current_ma", "LDI_mA"])
            or find_param_by_name(["laser_set_current_ma", "set_current_ma", "ldi_ma", "laser_current_ma"])
        )
        r.laser_set_current_ma = cls._to_float(set_i)

        # Laser max current
        max_i = (
            find_text_by_tags(["laser_max_current_ma", "LASER_MaxCurrent_mA", "max_current_ma", "LIM_I_mA"])
            or find_param_by_name(["laser_max_current_ma", "max_current_ma", "lim_i_ma", "max_i_ma"])
        )
        r.laser_max_current_ma = cls._to_float(max_i)

        # Laser max voltage
        max_v = (
            find_text_by_tags(["laser_max_voltage_v", "LASER_MaxVoltage_V", "max_voltage_v", "LIM_V_V"])
            or find_param_by_name(["laser_max_voltage_v", "max_voltage_v", "lim_v_v", "max_v_v"])
        )
        r.laser_max_voltage_v = cls._to_float(max_v)

        # Laser max power
        max_p = (
            find_text_by_tags(["laser_max_power_mw", "LASER_MaxPower_mW", "max_power_mw", "LIM_P_mW"])
            or find_param_by_name(["laser_max_power_mw", "max_power_mw", "lim_p_mw", "max_p_mw"])
        )
        r.laser_max_power_mw = cls._to_float(max_p)

        return r


class BaslerAnalysisGUI(QMainWindow):
            def _per_trigger_continuous_run(self):
                """Start continuous PER rotation/measurement from the PER tab Start button."""
                try:
                    mp = getattr(self, 'motor_panel', None)
                    if mp is None:
                        self.log_status('PER: Motor panel not initialized (open Settings tab once).', 'WARN')
                        return
                    if hasattr(mp, 'start_continuous_per') and callable(getattr(mp, 'start_continuous_per')):
                        mp.start_continuous_per()
                    else:
                        self.log_status('PER: Motor panel has no continuous PER handler.', 'ERROR')
                except Exception as e:
                    try:
                        self.log_status(f'PER: Failed to start continuous PER: {e}', 'ERROR')
                    except Exception:
                        pass

            def _per_trigger_2x360_sweep(self):
                """Trigger the same 2×360 motor sweep from the PER tab."""
                try:
                    mp = getattr(self, 'motor_panel', None)
                    if mp is None:
                        self.log_status('PER: Motor panel not initialized (open Settings tab once).', 'WARN')
                        return
                    if hasattr(mp, 'start_2x360_sweep') and callable(getattr(mp, 'start_2x360_sweep')):
                        mp.start_2x360_sweep()
                    else:
                        self.log_status('PER: Motor panel has no sweep handler.', 'ERROR')
                except Exception as e:
                    try:
                        self.log_status(f'PER: Failed to start sweep: {e}', 'ERROR')
                    except Exception:
                        pass

            def _abort_per_sweep_from_tab(self):
                """Stop the motor sweep when Stop PER is pressed from the PER tab."""
                try:
                    mp = getattr(self, 'motor_panel', None)
                    if mp is None:
                        return
                    if hasattr(mp, 'abort_sweep') and callable(getattr(mp, 'abort_sweep')):
                        mp.abort_sweep()
                except Exception as e:
                    try:
                        self.log_status(f'PER: Failed to stop sweep: {e}', 'ERROR')
                    except Exception:
                        pass

            def _per_trigger_home_motor(self):
                """Trigger the same home/initial motor action from the PER tab."""
                try:
                    mp = getattr(self, 'motor_panel', None)
                    if mp is None:
                        self.log_status('PER: Motor panel not initialized (open Settings tab once).', 'WARN')
                        return
                    if hasattr(mp, 'home_motor_from_per') and callable(getattr(mp, 'home_motor_from_per')):
                        mp.home_motor_from_per()
                    else:
                        self.log_status('PER: Motor panel has no home handler.', 'ERROR')
                except Exception as e:
                    try:
                        if hasattr(self, 'motor_panel') and hasattr(self.motor_panel, '_set_per_home_status'):
                            self.motor_panel._set_per_home_status("Home failed")
                    except Exception:
                        pass
                    try:
                        self.log_status(f'PER: Failed to home motor: {e}', 'ERROR')
                    except Exception:
                        pass

            # --- TEC/LASER COMMANDS (PyQt5 version) ---
            
            # --- TEC/LASER COMMANDS (PyQt5 version) ---
            
            def tec_cmd(self, cmd):
                try:
                    if hasattr(self, "arroyo") and self.arroyo and getattr(self.arroyo, "is_connected", False):
                        return bool(self.arroyo.tec_cmd(cmd))
                except Exception as e:
                    self.log_status(f"TEC backend error: {e}", "ERROR")
                return False

            def list_available_com_ports(self):
                ports = []
                for p in serial.tools.list_ports.comports():
                    ports.append(p.device)  # e.g. "COM5"
                return ports

            def laser_cmd(self, cmd):
                try:
                    if hasattr(self, "arroyo") and self.arroyo and getattr(self.arroyo, "is_connected", False):
                        return bool(self.arroyo.laser_cmd(cmd))
                except Exception as e:
                    self.log_status(f"Laser backend error: {e}", "ERROR")
                return False

            def set_temp(self):
                temp = self.tec_edits[0].text()
                if self.tec_cmd(f"TEC:T {temp}"):
                    self.log_status(f"Temperature set to {temp} °C", "SUCCESS")

            def set_max_temp(self):
                temp = self.tec_edits[1].text()
                if self.tec_cmd(f"TEC:LIM:THI {temp}"):
                    self.log_status(f"Max temperature set to {temp} °C", "SUCCESS")

            def set_min_temp(self):
                temp = self.tec_edits[2].text()
                if self.tec_cmd(f"TEC:LIM:TLO {temp}"):
                    self.log_status(f"Min temperature set to {temp} °C", "SUCCESS")

            def set_max_tec_current(self):
                curr = self.tec_edits[3].text()
                if self.tec_cmd(f"TEC:LIM:ITE {curr}"):
                    self.log_status(f"Max TEC current set to {curr} A", "SUCCESS")

            def tec_on(self):
                if self.tec_cmd("TEC:OUT 1"):
                    self.log_status("TEC turned ON", "SUCCESS")
                    self.btn_tec_on.setEnabled(False)
                    self.btn_tec_off.setEnabled(True)

            def debugging(self,exposure):
                    self.log_status("this value of exposure", exposure)


            def tec_off(self):
                if self.tec_cmd("TEC:OUT 0"):
                    self.log_status("TEC turned OFF", "SUCCESS")
                    self.btn_tec_on.setEnabled(True)
                    self.btn_tec_off.setEnabled(False)

            def set_laser_current(self):
                """Engineer-set current (mA) with explicit software clamp like LabVIEW."""
                curr_txt = self.laser_edits[0].text().strip() if self.laser_edits else ""
                max_txt = self.laser_edits[1].text().strip() if self.laser_edits and len(self.laser_edits) > 1 else ""
                try:
                    curr = float(curr_txt)
                except Exception:
                    self.log_status(f"Invalid laser current: {curr_txt}", "ERROR")
                    return
                max_curr = None
                try:
                    if max_txt != "":
                        max_curr = float(max_txt)
                except Exception:
                    max_curr = None

                # Prefer backend request layer (enforces Disable Arroyo + clamps)
                if hasattr(self, "arroyo") and self.arroyo is not None:
                    try:
                        ok = bool(self.arroyo.request_set_laser_current(curr, max_current_ma=max_curr, source="engineer"))
                        # If backend clamped, mirror the clamped value back into the UI (best-effort)
                        try:
                            if max_curr is not None and curr > max_curr:
                                self.laser_edits[0].setText(f"{max_curr:g}")
                        except Exception:
                            pass
                        if ok:
                            shown = (max_curr if (max_curr is not None and curr > max_curr) else curr)
                            self.log_status(f"Laser current set to {shown:g} mA", "SUCCESS")
                        return
                    except Exception as e:
                        self.log_status(f"Set current request failed: {e}", "ERROR")

                # Fallback: clamp locally then send LAS:LDI
                send_curr = curr
                if max_curr is not None and curr > max_curr:
                    send_curr = max_curr
                    self.log_status(f"Requested laser current {curr:g} mA clamped to {max_curr:g} mA", "WARN")
                    try:
                        self.laser_edits[0].setText(f"{send_curr:g}")
                    except Exception:
                        pass
                if self.laser_cmd(f"LAS:LDI {send_curr}"):
                    self.log_status(f"Laser current set to {send_curr:g} mA", "SUCCESS")

            def set_max_laser_current(self):
                curr = self.laser_edits[1].text()
                if self.laser_cmd(f"LAS:LIM:LDI {curr}"):
                    self.log_status(f"Max laser current set to {curr} mA", "SUCCESS")

            def set_max_laser_voltage(self):
                volt = self.laser_edits[2].text()
                if self.laser_cmd(f"LAS:LIM:LDV {volt}"):
                    self.log_status(f"Max laser voltage set to {volt} V", "SUCCESS")

            def set_max_laser_power(self):
                power = self.laser_edits[3].text()
                if self.laser_cmd(f"LAS:LIM:MDP {power}"):
                    self.log_status(f"Max laser power set to {power} mW", "SUCCESS")

            def _sync_beam_preview_with_laser(self, want_on: bool):
                """Keep beam panel empty until laser is turned on, then start live preview.

                This preserves the empty startup box but automatically starts the main
                beam preview after Laser ON, and clears it again after Laser OFF.
                """
                try:
                    live_mode = hasattr(self, "mode_combo") and self.mode_combo.currentText().startswith("Live")
                except Exception:
                    live_mode = False

                if not live_mode:
                    return

                try:
                    if want_on:
                        if getattr(self, "active_camera", None) is None and getattr(self, "external_camera", None) is not None:
                            self.active_camera = self.external_camera
                        self.start_camera_preview()
                    else:
                        self.stop_camera_preview()
                except Exception as e:
                    try:
                        self.log_status(f"Beam preview sync failed: {e}", "WARN")
                    except Exception:
                        pass

            def laser_on(self):
                # If a serial-number-based spec was loaded, force Set Current from CSV before turning ON.
                try:
                    cur = getattr(self, "_laser_spec_current_ma", None)
                    if cur is not None:
                        try:
                            if hasattr(self, "laser_edits") and self.laser_edits and len(self.laser_edits) >= 1:
                                self.laser_edits[0].setText(f"{float(cur):g}")
                        except Exception:
                            pass
                        try:
                            # Push current limit/setpoint to controller BEFORE enabling output
                            self.set_laser_current()
                        except Exception:
                            pass
                except Exception:
                    pass

                if self.laser_cmd("LAS:OUT 1"):
                    self.log_status("Laser turned ON", "SUCCESS")
                    self.btn_laser_on.setEnabled(False)
                    self.btn_laser_off.setEnabled(True)
                    self._sync_beam_preview_with_laser(True)


            def laser_off(self):
                if self.laser_cmd("LAS:OUT 0"):
                    self.log_status("Laser turned OFF", "SUCCESS")
                    self.btn_laser_on.setEnabled(True)
                    self.btn_laser_off.setEnabled(False)
                    self._sync_beam_preview_with_laser(False)

            def _force_laser_off_for_shutdown(self):
                """Best-effort laser shutdown that bypasses normal UI command guards."""
                success = False
                with contextlib.suppress(Exception):
                    if hasattr(self, "arroyo") and self.arroyo is not None:
                        success = bool(self.arroyo.force_laser_off(source="shutdown"))

                if success:
                    with contextlib.suppress(Exception):
                        self.btn_laser_on.setEnabled(True)
                        self.btn_laser_off.setEnabled(False)
                    with contextlib.suppress(Exception):
                        self._sync_beam_preview_with_laser(False)
                    with contextlib.suppress(Exception):
                        self.log_status("Laser forced OFF for shutdown", "SUCCESS")
                return success
            


            # -----------------------------
            # Laser Control tab integration
            # -----------------------------
            def _laser_control_recipe_changed(self, recipe_obj):
                """LabVIEW-style: a committed recipe updates BOTH:
                - Laser Control front panel display
                - Settings tab (TEC/LASER CONTROL edits)
                and is cached for subsequent Laser ON/OFF requests.
                """
                self._laser_recipe = recipe_obj

                # Update Laser Control panel display (if present)
                try:
                    if hasattr(self, "laser_control_panel") and self.laser_control_panel:
                        if hasattr(self.laser_control_panel, "set_recipe_display"):
                            self.laser_control_panel.set_recipe_display(recipe_obj)
                except Exception:
                    pass

                # Update Settings tab edits (if present)
                def _fmt(v):
                    return "" if v is None else f"{v:g}"
                try:
                    # TEC
                    if hasattr(self, "tec_edits") and self.tec_edits and len(self.tec_edits) >= 1:
                        t = getattr(recipe_obj, "tec_temp_c", None)
                        if t is not None:
                            self.tec_edits[0].setText(_fmt(t))
                    # LASER (Set I, Max I, Max V, Max P)
                    if hasattr(self, "laser_edits") and self.laser_edits and len(self.laser_edits) >= 4:
                        self.laser_edits[0].setText(_fmt(getattr(recipe_obj, "laser_set_current_ma", None)))
                        self.laser_edits[1].setText(_fmt(getattr(recipe_obj, "laser_max_current_ma", None)))
                        self.laser_edits[2].setText(_fmt(getattr(recipe_obj, "laser_max_voltage_v", None)))
                        self.laser_edits[3].setText(_fmt(getattr(recipe_obj, "laser_max_power_mw", None)))
                except Exception:
                    pass

            def _laser_control_laser_on(self):
                """Laser ON from Laser Control tab (VI-style request)."""
                if not getattr(self, "is_connected", False):
                    self.log_status("Laser ON blocked: Not connected (CONNECT first).", "ERROR")
                    return
                recipe = getattr(self, "_laser_recipe", None)
                # If serial-number-based spec was loaded, force Set Current from CSV before turning ON.
                try:
                    cur = getattr(self, "_laser_spec_current_ma", None)
                    if cur is not None:
                        # Update recipe object if it supports it
                        try:
                            if recipe is not None and hasattr(recipe, "laser_set_current_ma"):
                                setattr(recipe, "laser_set_current_ma", float(cur))
                        except Exception:
                            pass
                        # Update Settings tab display
                        try:
                            if hasattr(self, "laser_edits") and self.laser_edits and len(self.laser_edits) >= 1:
                                self.laser_edits[0].setText(f"{float(cur):g}")
                        except Exception:
                            pass
                        # Push to controller before enabling output
                        try:
                            self.set_laser_current()
                        except Exception:
                            pass
                except Exception:
                    pass

                # 1) Ask backend to turn ON (preferred path)
                try:
                    if hasattr(self, "arroyo") and self.arroyo:
                        self.arroyo.request_laser_on(recipe_obj=recipe, source="laser_control_tab")
                except Exception as e:
                    self.log_status(f"Laser ON request failed (backend): {e}", "ERROR")
                    # fall through to direct command attempt below

                # 2) Always attempt a direct LAS:OUT 1 as a safety net (fixes 'request sent but no output')
                ok_direct = False
                try:
                    ok_direct = bool(self.laser_cmd("LAS:OUT 1"))
                except Exception as e:
                    self.log_status(f"Laser ON direct command failed: {e}", "ERROR")

                # 3) Verify (best-effort)
                verified = None  # True/False/None
                try:
                    if hasattr(self, "arroyo") and self.arroyo:
                        verified = self.arroyo.get_laser_output_state()
                except Exception:
                    verified = None

                # UI + logs
                try:
                    self.btn_laser_on.setEnabled(False)
                    self.btn_laser_off.setEnabled(True)
                except Exception:
                    pass

                if verified is True:
                    self.log_status("Laser turned ON (verified by LAS:OUT?)", "SUCCESS")
                    self._sync_beam_preview_with_laser(True)
                elif verified is False:
                    self.log_status("Laser ON was requested but controller reports output is OFF (LAS:OUT? -> 0).", "ERROR")
                else:
                    # Unknown verification; still report what we did
                    if ok_direct:
                        self.log_status("Laser ON requested (direct LAS:OUT 1 sent; verification not available).", "SUCCESS")
                        self._sync_beam_preview_with_laser(True)
                    else:
                        self.log_status("Laser ON requested, but direct LAS:OUT 1 did not confirm success (check controller/port).", "WARN")

            def _laser_control_laser_off(self):
                """Laser OFF from Laser Control tab."""
                try:
                    if hasattr(self, "arroyo") and self.arroyo and getattr(self, "is_connected", False):
                        self.arroyo.request_laser_off(source="laser_control_tab")
                except Exception as e:
                    self.log_status(f"Laser OFF request failed: {e}", "ERROR")
                    return
                try:
                    self.btn_laser_on.setEnabled(True)
                    self.btn_laser_off.setEnabled(False)
                except Exception:
                    pass
                self._sync_beam_preview_with_laser(False)
                self.log_status("Laser OFF requested (Laser Control tab)", "SUCCESS")
            def start_monitoring(self):
                if not hasattr(self, 'monitor_timer'):
                    self.monitor_timer = QTimer()
                    self.monitor_timer.timeout.connect(self.update_monitoring)
                self.monitor_timer.start(1000)  # 1 second interval
            
            def stop_monitoring(self):
                if hasattr(self, 'monitor_timer'):
                    self.monitor_timer.stop()
            
            def update_monitoring(self):
                # Read TEC temperature
                try:
                    temp = self.arroyo.get_tec_temperature_c() if hasattr(self, "arroyo") and self.arroyo else None
                    if temp:
                        self.arroyo_temp_label.setText(f"{temp} °C")
                except Exception:
                    self.arroyo_temp_label.setText("-- °C")
                # Read Laser current
                try:
                    curr = self.arroyo.get_laser_current_ma() if hasattr(self, "arroyo") and self.arroyo else None
                    if curr:
                        self.arroyo_current_label.setText(f"{curr} mA")
                except Exception:
                    self.arroyo_current_label.setText("-- mA")
        # =========================
        # ARROYO CONTROLLER LOGIC (PyQt5 version)
        # =========================



            def detect_com_ports(self):
                """Return ONLY COM ports that actually exist on this machine.

                We intentionally rely on `serial.tools.list_ports.comports()` because it reflects
                what Windows Device Manager shows under Ports (COM & LPT), and avoids listing
                stale/non-existent ports that can appear via VISA enumeration.
                """
                ports = []
                try:
                    for p in serial.tools.list_ports.comports():
                        dev = (getattr(p, "device", "") or "").upper().strip()
                        if dev.startswith("COM"):
                            ports.append(dev)
                except Exception:
                    ports = []

                # De-duplicate and sort numerically (COM3 < COM10)
                def _com_key(s: str):
                    m = re.search(r"(\d+)", s)
                    return int(m.group(1)) if m else 9999

                ports = sorted(list(dict.fromkeys(ports)), key=_com_key)
                return ports

            def refresh_com_ports(self):
                """Refresh the COM dropdowns and auto-select USB Serial Port (COM3) if present."""
                ports = self.detect_com_ports()

                self.combo_tec.clear()
                self.combo_laser.clear()

                if not ports:
                    self.combo_tec.addItem("No COM ports found")
                    self.combo_laser.addItem("No COM ports found")
                    try:
                        self.btn_connect.setEnabled(False)
                    except Exception:
                        pass
                    self.log_status("COM Ports refreshed: none found.", "WARN")
                    return

                for cb in (self.combo_tec, self.combo_laser):
                    cb.addItems(ports)

                # Prefer the known station port (USB Serial Port (COM3))
                preferred = "COM3"
                try:
                    if preferred in ports:
                        self.combo_tec.setCurrentText(preferred)
                        self.combo_laser.setCurrentText(preferred)
                except Exception:
                    pass

                try:
                    self.btn_connect.setEnabled(True)
                except Exception:
                    pass

                self.log_status(f"COM Ports refreshed: Found {len(ports)} port(s): {', '.join(ports)}", "SUCCESS")


            def log_status(self, message, level="INFO"):
                timestamp = datetime.datetime.now().strftime("%H:%M:%S")
                prefix = f"[{timestamp}] [{level}] "
                print(prefix + message)
                # Mirror to GUI status boxes if available
                try:
                    if hasattr(self, "status_log") and self.status_log is not None:
                        self.status_log.append(prefix + message)
                except Exception:
                    pass
                try:
                    if hasattr(self, "main_status_log") and self.main_status_log is not None:
                        self.main_status_log.append(prefix + message)
                except Exception:
                    pass

            def _on_disable_arroyo_toggled(self, checked: bool) -> None:
                """LabVIEW Disable Arroyo: hard gate for any TEC/Laser control."""
                try:
                    if hasattr(self, "arroyo") and self.arroyo is not None:
                        # Backend enforces this gate for all requests
                        if hasattr(self.arroyo, "set_disable_arroyo"):
                            self.arroyo.set_disable_arroyo(bool(checked))
                        else:
                            # Fallback: set attribute if method not present
                            setattr(self.arroyo, "disable_arroyo", bool(checked))
                    self.log_status(f"Disable Arroyo set to {bool(checked)}", "INFO")
                except Exception as e:
                    self.log_status(f"Failed to set Disable Arroyo: {e}", "ERROR")


            def _on_operator_changed(self, name: str) -> None:
                # (Legacy) kept for compatibility; LabVIEW-style selector uses ▲/▼ buttons.
                self.current_operator = (name or "").strip()

            def _update_operator_display(self) -> None:
                """Update the read-only operator display from self.operators/self.operator_index."""
                try:
                    if not getattr(self, "operators", None) or int(getattr(self, "operator_index", -1)) < 0:
                        if hasattr(self, "operator_edit"):
                            self.operator_edit.setText("")
                        self.current_operator = ""
                        return

                    self.operator_index = int(self.operator_index) % len(self.operators)
                    name = str(self.operators[self.operator_index]).strip()
                    if hasattr(self, "operator_edit"):
                        self.operator_edit.setText(name)
                    self.current_operator = name
                except Exception:
                    # Best-effort: never crash UI for operator display issues
                    return

            def operator_next(self) -> None:
                """▲ button: advance to next operator (wrap-around)."""
                if not getattr(self, "operators", None):
                    return
                self.operator_index = int(getattr(self, "operator_index", 0)) + 1
                # self._update_operator_display()  # legacy

            def operator_prev(self) -> None:
                """▼ button: go to previous operator (wrap-around)."""
                if not getattr(self, "operators", None):
                    return
                self.operator_index = int(getattr(self, "operator_index", 0)) - 1
                # self._update_operator_display()  # legacy

            def load_operators(self) -> None:
                """Best-effort clone of LabVIEW Get Operators.vi.

                LabVIEW does:
                    SELECT [Operator] FROM [IPSMES].[dbo].[Operators] WHERE [Status] = 1
                using a UDL connection (data\IPSMES.udl).

                In Python we try the same via pyodbc if available; otherwise we fall back
                to a small local list so the UI keeps working.
                """
                operators: list[str] = []
                # 1) Try SQL via UDL (closest to LabVIEW)
                try:
                    self.log_status("Attempting to load operators from IPSMES database via UDL...", "DEBUG")
                    ops = self._query_operators_from_udl()
                    self.log_status(f"_query_operators_from_udl() returned: {ops}", "DEBUG")
                    if ops:
                        operators = ops
                        self.log_status(f"Loaded {len(operators)} operator(s) from IPSMES database: {operators}", "INFO")
                    else:
                        self.log_status("No operators returned from database query.", "WARN")
                except Exception as e:
                   # import traceback
                    tb = traceback.format_exc()
                    self.log_status(f"Get Operators (SQL) failed, using fallback list. Reason: {e}\nTraceback:\n{tb}", "WARN")

                # 2) Fallback list (keeps UI functional if DB driver/UDL not available)
                if not operators:
                    self.log_status("Using fallback operator list: ['Operator']", "WARN")
                    operators = ["Operator"]  # placeholder like an empty enum in LabVIEW

                # Update operator dropdown
                try:
                    current = (self.current_operator or "").strip()
                    self.log_status(f"Updating operator list with: {operators}", "DEBUG")
                    self.operators = list(operators)

                    # Populate the dropdown
                    try:
                        self.operator_combo.blockSignals(True)
                        self.operator_combo.clear()
                        self.operator_combo.addItems(self.operators)
                    finally:
                        try:
                            self.operator_combo.blockSignals(False)
                        except Exception:
                            pass

                    # Restore selection if possible
                    if self.operators:
                        if current and current in self.operators:
                            self.operator_combo.setCurrentText(current)
                            self.current_operator = current
                        else:
                            self.current_operator = (self.operator_combo.currentText() or "").strip()
                    else:
                        self.current_operator = ""
                except Exception as e:
                    self.log_status(f"Exception updating operator selector: {e}", "ERROR")
            def _query_operators_from_udl(self) -> list[str]:
                            """Attempt to read data\IPSMES.udl and query operators where Status=1."""
                            # LabVIEW uses a relative path "data\IPSMES.udl".
                            # We resolve relative to this script first, then CWD as fallback.
                            # Force the UDL path to the known correct location
                            udl_path = Path(r"C:/Users/4510205/Downloads/data/IPSMES.udl")
                            if not udl_path.exists():
                                raise FileNotFoundError(str(udl_path))
                            udl_text = udl_path.read_text(encoding="utf-16", errors="ignore")
                            self.log_status(f"Raw UDL text after reading (first 200 chars): {repr(udl_text[:200])}", "DEBUG")
                            conn_str = self._udl_to_pyodbc_connstr(udl_text)

                            # pyodbc is the most common way to connect to SQL Server from Python on Windows.
                          #  import importlib
                            pyodbc = importlib.import_module("pyodbc")

                            query = ("SELECT [Operator] "
                                     "FROM [IPSMES].[dbo].[Operators] "
                                     "WHERE [Status] = 1")

                            ops: list[str] = []
                            try:
                                self.log_status(f"Connecting to SQL with: {conn_str}", "DEBUG")
                                with pyodbc.connect(conn_str, timeout=3) as cn:
                                    cur = cn.cursor()
                                    self.log_status(f"Connected. Executing: {query}", "DEBUG")
                                    for row in cur.execute(query):
                                        # row[0] is the Operator string
                                        if row and row[0] is not None:
                                            s = str(row[0]).strip()
                                            if s:
                                                ops.append(s)
                                    self.log_status(f"Query returned {len(ops)} rows: {ops}", "DEBUG")
                            except Exception as e:
                              #  import traceback
                                tb = traceback.format_exc()
                                self.log_status(f"SQL connection/query failed: {e}\nTraceback:\n{tb}", "ERROR")
                            # De-duplicate but keep order
                            seen = set()
                            uniq = []
                            for s in ops:
                                if s not in seen:
                                    seen.add(s); uniq.append(s)
                            return uniq

            def _udl_to_pyodbc_connstr(self, udl_text: str) -> str:
                """Convert a .udl file (OLE DB style) to a pyodbc connection string (best-effort).

                Notes:
                - Many .udl files contain a line like:
                      Provider=SQLOLEDB.1;Integrated Security=SSPI;Persist Security Info=False;Initial Catalog=IPSMES;Data Source=SERVER
                - pyodbc expects DRIVER + SERVER + DATABASE (+ auth).
                """


                # Improved UDL parsing: skip comments/headers, handle multiline, and log extracted values
                kvpairs = {}
               # import re
                udl_lines = [line for line in udl_text.splitlines() if line.strip() and not line.strip().startswith(';') and not line.strip().startswith('[')]
                udl_str = ''.join(udl_lines)
                for part in udl_str.split(';'):
                    if '=' in part:
                        k, v = part.split('=', 1)
                        k = k.strip().lower()
                        v = v.strip()
                        kvpairs[k] = v
                self.log_status(f"UDL key-value pairs: {kvpairs}", "DEBUG")

                server = kvpairs.get('data source') or kvpairs.get('server')
                database = kvpairs.get('initial catalog') or kvpairs.get('database')
                uid = kvpairs.get('user id') or kvpairs.get('uid')
                pwd = kvpairs.get('password') or kvpairs.get('pwd')
                integrated = kvpairs.get('integrated security')

                # Log the extracted values for debug
                self.log_status(f"Extracted server: {server}, database: {database}, uid: {uid}, integrated: {integrated}", "DEBUG")

                if not server or not database:
                    self.log_status(f"UDL parse failure: server={server}, database={database}", "ERROR")
                    raise ValueError("UDL missing Data Source / Initial Catalog")

                # Prefer modern SQL Server driver if installed; user can override in the UDL later.
                driver = "{SQL Server}"
                if integrated and integrated.strip().lower() in ("sspi", "true", "yes"):
                    return f"DRIVER={driver};SERVER={server};DATABASE={database};Trusted_Connection=yes;"
                if uid and pwd:
                    return f"DRIVER={driver};SERVER={server};DATABASE={database};UID={uid};PWD={pwd};"
                # Last resort: try trusted connection
                return f"DRIVER={driver};SERVER={server};DATABASE={database};Trusted_Connection=yes;"


            def _port_open_test(self, port: str, baud: int = 38400) -> tuple:
                """Best-effort check: can we open/close the COM port right now?"""
                try:
                 #   import serial
                    s = serial.Serial(port=str(port), baudrate=int(baud), timeout=1, write_timeout=1)
                    try:
                        return True, ""
                    finally:
                        try:
                            s.close()
                        except Exception:
                            pass
                except Exception as e:
                    return False, str(e)

            def _diagnose_arroyo_link(self) -> None:
                """Run quick diagnostics: port availability, device response, and best-effort remote-mode status."""
                try:
                    diag = self.arroyo.diagnose_link()
                except Exception as e:
                    self.log_status(f"DIAG: backend diagnostics failed: {e}", "ERROR")
                    return

                laser_resp = diag.get("laser_resp")
                if laser_resp in (None, ""):
                    self.log_status("DIAG: Connected but LAS:LDI? did not return a response (wrong port / stale state / cable).", "ERROR")
                else:
                    self.log_status(f"DIAG: Laser responds (LAS:LDI? -> {laser_resp}).", "SUCCESS")

                tec_resp = diag.get("tec_resp")
                if tec_resp in (None, ""):
                    self.log_status("DIAG: Connected but TEC:T? did not return a response.", "WARN")
                else:
                    self.log_status(f"DIAG: TEC responds (TEC:T? -> {tec_resp}).", "SUCCESS")

                remote_resp = diag.get("remote_resp")
                if remote_resp in (None, ""):
                    self.log_status("DIAG: Remote-mode status query not supported (skipped).", "INFO")
                else:
                    s = str(remote_resp).strip().upper()
                    if s in ("1", "ON", "REMOTE", "REM"):
                        self.log_status(f"DIAG: Controller reports REMOTE mode ({remote_resp}).", "WARN")
                    else:
                        self.log_status(f"DIAG: Remote/local status reported: {remote_resp}", "INFO")

            def connect_arroyo(self):

                # --- Connection logic using headless backend (arroyo_backend.py) ---

                try:

                    # Stop monitoring first so it doesn't race the connect/disconnect sequence
                    try:
                        self.stop_monitoring()
                    except Exception:
                        pass

                    mode = 'combo'
                    self.log_status(f"Connecting in mode: {mode}", "INFO")

                    # Clear legacy handles
                    self.rm_tec = self.rm_laser = self.rm_combo = None
                    self.tec = self.laser = self.combo = None
                    self.is_connected = False

                    # ---- Pre-flight COM checks (detect 'COM port already in use') ----
                    combo_port_str = self.combo_laser.currentText().strip()
                    if not combo_port_str:
                        self.log_status("Please select Laser Source COM port", "ERROR")
                        return
                    ok, err = self._port_open_test(combo_port_str)
                    if not ok:
                        self.log_status(f"CONNECT blocked: {combo_port_str} cannot be opened (already in use / driver issue). Details: {err}", "ERROR")
                        return

                    # ---- Connect using backend ----
                    self.arroyo.connect_combo(combo_port_str)
                    self.combo = self.arroyo.combo
                    self.tec = None
                    self.laser = None
                    self.log_status(f"Connected to Laser Source ({combo_port_str})", "SUCCESS")

                    self.is_connected = True
                    self.btn_connect.setText("DISCONNECT")
                    self.btn_connect.setStyleSheet("background-color: #ff6b6b; font-weight: bold; font-size: 14px; height: 32px;")

                    # ---- Post-connect diagnostics: does the device respond? ----
                    self._diagnose_arroyo_link()

                    # Start monitoring after diagnostics (so diagnostics aren't racing the timer)
                    self.start_monitoring()
                    self._refresh_connection_indicators()

                except Exception as e:
                    self.log_status(f"Connection error: {e}", "ERROR")
                    self._refresh_connection_indicators()


            def disconnect_arroyo(self):
                """Safe disconnect that prevents the controller/COM port being left in a bad state."""
                try:
                    # Stop monitoring FIRST (prevents background queries from racing disconnect)
                    try:
                        self.stop_monitoring()
                    except Exception:
                        pass

                    # Best-effort: turn laser output OFF before disconnect
                    try:
                        if hasattr(self, "arroyo") and self.arroyo and getattr(self, "is_connected", False):
                            try:
                                # Preferred request layer (if present)
                                if hasattr(self.arroyo, "request_laser_off"):
                                    self.arroyo.request_laser_off(source="disconnect")
                                else:
                                    # Fallback command
                                    self.laser_cmd("LAS:OUT 0")
                            except Exception:
                                pass
                    except Exception:
                        pass

                    # Now close ports via backend
                    try:
                        if hasattr(self, "arroyo") and self.arroyo:
                            self.arroyo.disconnect()
                    except Exception as e:
                        self.log_status(f"Backend disconnect error: {e}", "WARN")

                    # Clear handles/state
                    self.tec = None
                    self.laser = None
                    self.combo = None
                    self.rm_tec = self.rm_laser = self.rm_combo = None
                    self.is_connected = False

                    self.log_status("Disconnected successfully (laser off + COM released).", "SUCCESS")

                    try:
                        self.arroyo_temp_label.setText("-- °C")
                        self.arroyo_current_label.setText("-- mA")
                    except Exception:
                        pass

                except Exception as e:
                    self.log_status(f"Disconnect error: {e}", "ERROR")

                try:
                    self.btn_connect.setText("CONNECT")
                    self.btn_connect.setStyleSheet("background-color: #3ecfcf; font-weight: bold; font-size: 14px; height: 32px;")
                except Exception:
                    pass
                self._refresh_connection_indicators()


            def toggle_connection(self):
                if self.btn_connect.text() == "CONNECT":
                    self.connect_arroyo()
                else:
                    self.disconnect_arroyo()
                    """Main GUI Window - User controls all analysis from here."""

            def __init__(self):
                super().__init__()
                self.setWindowTitle("Basler Camera Analysis")
                self.setGeometry(100, 100, 1600, 900)

                self.config = None
                self.current_image = None
                self.analysis_worker = None
                self.logged_data = []
                self.profile_data = {}



                # Engineering settings lock / password (LabVIEW-style)
                self._engineering_password = None  # set when 'Require Password' is enabled
                self._engineering_locked = False
                # Headless Arroyo backend (LabVIEW-style request layer)
                self.arroyo = ArroyoLaserSystem(logger=self.log_status)
                self._laser_recipe = None
                # -----------------------------
                # Live camera support
                # -----------------------------
                # External camera is usually a BaslerCamera (pypylon) attached by main.
                # OpenCV camera can be created on-demand inside the GUI.
                self.external_camera = None
                self.opencv_camera = None
                self.active_camera = None
                self.camera_timer = QTimer(self)
                self.camera_timer.timeout.connect(self.update_camera_frame)
                self.camera_interval_ms = 30



                # Secondary cameras (Cam2 / Cam3 pop-off)
                self.cam2_camera = None
                self.cam3_camera = None
                # Fixed USB camera indices for Cam2/Cam3 (no user selection).
                # Cam2 defaults to 0. Cam3 will be auto-discovered if index 1 doesn't work.
                self._usb_cam2_index = 0
                self._usb_cam3_index = 1
                self.cam23_window = None
                self.cam23_timer = QTimer(self)
                self.cam23_timer.timeout.connect(self.update_secondary_cameras)
                self.cam23_interval_ms = 60
                # Auto-analyze timer (continuous analysis without blocking the GUI)
                self.auto_analyze_timer = QTimer(self)
                self.auto_analyze_timer.timeout.connect(self._auto_analyze_tick)
                self._auto_analyze_enabled = False
                self._analysis_busy = False
                self._run_loop_active = False
                self._analysis_stop_requested = False
                self._live_view_active = False
                self._beam_colorbar = None
                self._beam_draw_deferred = False
                self._beam_draw_requested = False
                self._last_beam_display_rgb = None
                self._startup_ports_initialized = False
                self._initial_beam_placeholder_synced = False

                self.init_ui()
                self.setup_styles()
                self._conn_indicator_timer = QTimer(self)
                self._conn_indicator_timer.timeout.connect(self._refresh_connection_indicators)
                self._conn_indicator_timer.start(500)
                QTimer.singleShot(50, self._refresh_connection_indicators)
                # Auto-open Cam2/Cam3 helper window at startup (no enable checkboxes).
                QTimer.singleShot(200, self.open_secondary_cameras_window)
                # Auto-initialize Settings defaults at startup (best-effort, non-fatal).
                QTimer.singleShot(1200, self._kickoff_startup_settings_init)
                self._beam_im = None
                self._beam_cbar = None

            def showEvent(self, event):
                super().showEvent(event)
                # More reliable than only running from __init__: triggers when window is visible.
                if not getattr(self, "_startup_ports_initialized", False):
                    QTimer.singleShot(250, self._kickoff_startup_settings_init)
                # One-time geometry sync so the initial empty beam box matches post-analysis size.
                if not getattr(self, "_initial_beam_placeholder_synced", False):
                    QTimer.singleShot(0, self._sync_initial_beam_placeholder_geometry)

            def _kickoff_startup_settings_init(self):
                if getattr(self, "_startup_ports_initialized", False):
                    return
                self._startup_ports_initialized = True
                self._startup_initialize_settings_ports()

            def _startup_initialize_settings_ports(self):
                """Best-effort startup init for Settings controls requested by user."""
                self.log_status("Startup init: begin auto-connect sequence.", "INFO")

                # 1) Enable auto exposure by default.
                try:
                    if hasattr(self, "btn_enable_auto_exposure") and self.btn_enable_auto_exposure is not None:
                        self.btn_enable_auto_exposure.setChecked(True)
                        self.log_status("Startup init: Auto Exposure set to TRUE.", "INFO")
                except Exception as e:
                    self.log_status(f"Startup init: Auto Exposure enable failed: {e}", "WARN")

                # 2) Connect Arroyo connection (Laser Source COM).
                def _connect_arroyo_startup():
                    try:
                        with contextlib.suppress(Exception):
                            self.refresh_com_ports()
                        if getattr(self, "is_connected", False):
                            self.log_status("Startup init: Connection already connected.", "INFO")
                            return
                        self.connect_arroyo()
                    except Exception as e:
                        self.log_status(f"Startup init: Connection connect failed: {e}", "WARN")

                # 3) Connect UV control.
                def _connect_uv_startup():
                    try:
                        uv = getattr(self, "uv_control_panel", None)
                        if uv is None:
                            self.log_status("Startup init: UV panel not available.", "WARN")
                            return
                        if hasattr(uv, "startup_connect"):
                            uv.startup_connect()
                    except Exception as e:
                        self.log_status(f"Startup init: UV connect failed: {e}", "WARN")

                # 4) Connect power meter.
                def _connect_pm_startup():
                    try:
                        pm = getattr(self, "pm_settings_panel", None)
                        if pm is None:
                            self.log_status("Startup init: Power meter panel not available.", "WARN")
                            return
                        with contextlib.suppress(Exception):
                            pm._refresh_resources()
                        if hasattr(pm, "chk_disable_pm") and pm.chk_disable_pm.isChecked():
                            pm.chk_disable_pm.setChecked(False)
                        if hasattr(pm, "btn_connect") and not pm.btn_connect.isEnabled():
                            self.log_status("Startup init: Power meter already connected.", "INFO")
                            return
                        if hasattr(pm, "_connect"):
                            pm._connect()
                    except Exception as e:
                        self.log_status(f"Startup init: Power meter connect failed: {e}", "WARN")

                # 5) Connect angle control motor.
                def _connect_angle_startup():
                    try:
                        mp = getattr(self, "motor_panel", None)
                        if mp is None:
                            self.log_status("Startup init: Angle control panel not available.", "WARN")
                            return
                        if hasattr(mp, "startup_connect"):
                            mp.startup_connect()
                    except Exception as e:
                        self.log_status(f"Startup init: Angle control connect failed: {e}", "WARN")

                # Stagger startup connects to reduce driver contention during app load.
                QTimer.singleShot(0, _connect_arroyo_startup)
                QTimer.singleShot(300, _connect_uv_startup)
                QTimer.singleShot(700, _connect_pm_startup)
                QTimer.singleShot(1100, _connect_angle_startup)
                # One retry pass to catch late COM/Kinesis initialization.
                QTimer.singleShot(2200, _connect_arroyo_startup)
                QTimer.singleShot(2600, _connect_uv_startup)
                QTimer.singleShot(3000, _connect_pm_startup)
                QTimer.singleShot(3400, _connect_angle_startup)


            def set_config(self, cfg):
                """Set configuration from main code."""
                self.config = cfg
                if cfg:
                   # self.wavelength_input.setValue(int(cfg.analysis.wavelength_nm or 780))
                    self.exposure_ms_spin.setValue(float(cfg.camera.exposure_us or 10000.0) / 1000.0)
                 #   self.rotation_input.setValue(cfg.camera.rotate_deg or 0)
                    if hasattr(self, 'sat_thresh_input'):
                        self.sat_thresh_input.setValue(float(getattr(cfg.analysis, 'saturation_threshold_percent', 0.2) or 0.2))
                    try:
                        if hasattr(self, 'sat_kp_spin'):
                            self.sat_kp_spin.setValue(float(getattr(getattr(cfg, 'auto_exposure', None), 'kp', 0.2) or 0.2))
                        if hasattr(self, 'sat_ki_spin'):
                            self.sat_ki_spin.setValue(float(getattr(getattr(cfg, 'auto_exposure', None), 'ki', 0.05) or 0.05))
                    except Exception:
                        pass

#   self.path_input.setText(cfg.output.out_dir or "output")


                    try:
                        if hasattr(self, "btn_enable_auto_exposure") and hasattr(cfg, "auto_exposure"):
                            self.btn_enable_auto_exposure.blockSignals(True)
                            self.btn_enable_auto_exposure.setChecked(bool(getattr(cfg.auto_exposure, "enabled", False)))
                            self.btn_enable_auto_exposure.blockSignals(False)
                    except Exception:
                        pass
            def init_ui(self):
                """Initialize user interface with tabbed panels."""
                tab_widget = QTabWidget()
                self.tab_widget = tab_widget
                self.setCentralWidget(tab_widget)

                # --- Basler Camera Analysis Tab ---
                basler_tab = QWidget()

                # Root layout so we can have a LabVIEW-like top row (Operator + Serial Number) above the main panels
                basler_root = QVBoxLayout(basler_tab)
                basler_root.setContentsMargins(5, 5, 5, 5)
                basler_root.setSpacing(6)

                # --- Top bar: Operator + Serial Number (LabVIEW Get Operators.vi parity) ---
                top_bar = QWidget()
                top_layout = QHBoxLayout(top_bar)
                top_layout.setContentsMargins(0, 0, 0, 0)
                top_layout.setSpacing(12)

                top_grid = QGridLayout()
                top_grid.setContentsMargins(0, 0, 0, 0)
                top_grid.setHorizontalSpacing(10)
                top_grid.setVerticalSpacing(6)

                # Operator dropdown (replaces legacy ▲/▼ operator selector)
                self.operator_combo = QComboBox()
                self.operator_combo.setMinimumWidth(200)
                self.operator_combo.currentTextChanged.connect(self._on_operator_changed)
                self.operator_refresh_btn = QPushButton("↻")
                self.operator_refresh_btn.setFixedWidth(30)
                self.operator_refresh_btn.setToolTip("Reload operator list (like Get Operators.vi)")
                self.operator_refresh_btn.clicked.connect(self.load_operators)

                self.operator_serial_edit = QLineEdit()
                self.operator_serial_edit.setPlaceholderText("")
                self.fac_sac_combo = QComboBox()
                self.fac_sac_combo.addItems(["FAC", "SAC"])
                self.fac_sac_combo.setCurrentIndex(0)
                self.save_path_edit = QLineEdit()
                self.save_path_edit.setMinimumWidth(260)
                self.save_path_edit.setText(r"Y:\Operations\Lensing Data\FAC-SAC-Lensing")
                self.btn_browse_save_path = QPushButton("...")
                self.btn_browse_save_path.setFixedWidth(28)
                self.btn_browse_save_path.setToolTip("Browse folder for screenshot save path")
                self.btn_browse_save_path.clicked.connect(self._browse_save_path)
                self.path_save_widget = QWidget()
                _path_layout = QHBoxLayout(self.path_save_widget)
                _path_layout.setContentsMargins(0, 0, 0, 0)
                _path_layout.setSpacing(4)
                _path_layout.addWidget(self.save_path_edit, 1)
                _path_layout.addWidget(self.btn_browse_save_path, 0)
                self.image_type_combo = QComboBox()
                self.image_type_combo.addItems(["PNG", "JPG", "BMP", "TIFF"])
                self.image_type_combo.setCurrentText("PNG")
                self.btn_save_snapshot = QPushButton("Save")
                self.btn_save_snapshot.setFixedWidth(60)
                self.btn_save_snapshot.setToolTip("Save screenshot of beam panel (beam + color bar + FA/SA plots + saturation)")
                self.btn_save_snapshot.clicked.connect(self._save_beam_panel_snapshot)

                # Button: load Product + Lensing Current from General Laser Specification Reference.csv for this serial
                self.btn_load_serial_spec = QPushButton("Load")
                self.btn_load_serial_spec.setFixedWidth(48)
                self.btn_load_serial_spec.setToolTip("Load laser specs for this SN from database")
                self.btn_load_serial_spec.clicked.connect(self._on_main_serial_load_clicked)

                top_grid.addWidget(QLabel("Operator"), 0, 0)
                top_grid.addWidget(self.operator_combo, 0, 1)
                top_grid.addWidget(self.operator_refresh_btn, 0, 2)
                top_grid.addWidget(QLabel("Serial Number"), 0, 3)
                top_grid.addWidget(self.operator_serial_edit, 0, 4)
                top_grid.addWidget(self.btn_load_serial_spec, 0, 5)
                top_grid.addWidget(QLabel("FAC/SAC"), 0, 6)
                top_grid.addWidget(self.fac_sac_combo, 0, 7)
                top_grid.addWidget(QLabel("Path to save"), 0, 8)
                top_grid.addWidget(self.path_save_widget, 0, 9)
                top_grid.addWidget(QLabel("Image type"), 0, 10)
                top_grid.addWidget(self.image_type_combo, 0, 11)
                top_grid.addWidget(self.btn_save_snapshot, 0, 12)

                top_layout.addLayout(top_grid)
                top_layout.addStretch(1)
                basler_root.addWidget(top_bar, 0)

                # Store for downstream logging / recipes if needed
                self.current_operator = ""
                self.operators = []
                self.operator_index = -1
                self.last_snapshot_path = ""
                self._last_laser_spec_record = None

                # LabVIEW-style operator enum navigation (▲/▼)# Populate operators at startup (SQL via UDL if available, otherwise fallback list)
                self.load_operators()

                # Body widget holds the original left/center/right panels
                body_widget = QWidget()
                basler_layout = QHBoxLayout(body_widget)
                basler_layout.setContentsMargins(0, 0, 0, 0)
                basler_layout.setSpacing(10)
                basler_root.addWidget(body_widget, 1)

                # LEFT: Controls
                left_panel = self.create_left_panel()
                basler_layout.addWidget(left_panel, 0)

                # CENTER: Beam image with SA/FA analysis plots
                center_widget = QWidget()
                center_layout = QVBoxLayout(center_widget)

                # Create matplotlib figure with subplots
                self.beam_figure = Figure(figsize=(16, 12), dpi=100)
                self.beam_canvas = FigureCanvas(self.beam_figure)

                # --- Layout per Somayeh's sketch constraints ---
                # 3 rows: SA zoom, SA profile, beam row
                # 4 cols: intensity bar (left of beam), beam image, rotated FA profile, FA zoom
                # SA plots span ONLY the beam column so their length matches the beam image width.
                # New: 5 columns to allow SA zoom to be half-width and centered
                gs = self.beam_figure.add_gridspec(
                    3, 5,
                    hspace=0.02, wspace=0.02,
                    width_ratios=[0.08, 0.75, 0.75, 0.3, 0.30],  # FA profile width matches SA profile height
                    height_ratios=[0.55, 0.30, 3.50],  # Decreased SA profile height
                )

                # Remove extra margins from the canvas
                self.beam_figure.subplots_adjust(left=0.01, right=0.99, top=0.99, bottom=0.01)

                # Row 0: SA zoom (same width as beam image)
                # Row 0: SA zoom (half width, centered)
                                # Row 0: SA zoom (half width, left, centered with profile)
                # Row 0: SA zoom (centered above profile)
                self.ax_sa_zoom = self.beam_figure.add_subplot(gs[0, 2])
                self._style_sa_zoom_axis()

                # Row 1: SA profile (same width as beam image)
                # Row 1: SA profile (same width as beam image)
                self.ax_sa_profile = self.beam_figure.add_subplot(gs[1, 1:3])
                # self.ax_sa_profile.set_title('SA Profile', fontweight='normal', fontsize=10)
                self._style_sa_profile_axis()

                # Intensity bar: match the vertical extent of the beam image (row 2 only)
                self.ax_intensity_bar = self.beam_figure.add_subplot(gs[2, 0])
                self.ax_intensity_bar.set_axis_on()

                # Beam image: row 2 only
                self.ax_beam = self.beam_figure.add_subplot(gs[2, 1:3])
                #  self.ax_beam.set_title('Beam Image', fontweight='normal', fontsize=10)
                self.ax_beam.axis('off')
                for spine in self.ax_beam.spines.values():
                    spine.set_edgecolor('black')
                    spine.set_linewidth(2)
                    spine.set_visible(True)

                # Row 2, Col 2: rotated FA profile (same row height as beam => same length)
                self.ax_fa_profile = self.beam_figure.add_subplot(gs[2, 3])
                # self.ax_fa_profile.set_title('FA Profile', fontweight='normal', fontsize=10)
                self._style_fa_profile_axis()

                # Row 2, Col 3: FA zoom
                self.ax_fa_zoom = self.beam_figure.add_subplot(gs[2, 4])
                self._style_fa_zoom_axis()
                self._apply_profile_zoom_borders_double()
                self._move_sa_panels_closer_to_beam()
                self._capture_fixed_axes_positions()
                self._restore_fixed_axes_positions()
                self._ensure_beam_colorbar_placeholder()

                # --- Saturation status indicator (figure-level, between Beam and FA panels) ---
                self._sat_circle = Circle((0.5, 0.5), 0.03, transform=self.beam_figure.transFigure,
                                          facecolor="red", edgecolor="black", linewidth=1.5, zorder=10)
                self.beam_figure.patches.append(self._sat_circle)

                self._sat_circle_text = self.beam_figure.text(
                    0.5, 0.5, "SAT BAD",
                    transform=self.beam_figure.transFigure,
                    ha="center", va="center",
                    fontsize=11, fontweight="bold",
                    color="white", zorder=11
                )

                # %Saturated label (above the box)
                self._sat_percent_label = self.beam_figure.text(
                    0.5, 0.5, "%Saturated",
                    transform=self.beam_figure.transFigure,
                    ha="center", va="bottom",
                    fontsize=10,
                    color="black", zorder=11
                )#, fontweight="bold"

                # Box for saturation value (empty initially, gray background, visible before analysis)
                self._sat_value_box = self.beam_figure.text(
                    0.5, 0.5, "",
                    transform=self.beam_figure.transFigure,
                    ha="center", va="top",
                    fontsize=12, fontweight="bold",
                    color="black", zorder=12,
                    bbox=dict(boxstyle="round,pad=0.25", facecolor="#b0b0b0", edgecolor="#888", alpha=0.95)
                )
                # Ensure box is visible and empty at startup
                self._ensure_sat_value_box_placeholder()

                self._reposition_sat_indicator()
                self._show_empty_beam_placeholder()

                center_layout.addWidget(self.beam_canvas)
                basler_layout.addWidget(center_widget, 2)

                # RIGHT: Results
                right_panel = self.create_right_panel()
                basler_layout.addWidget(right_panel, 0)

                tab_widget.addTab(basler_tab, "Main")

                                # --- PER Tab (Power / PER) ---
                self.per_tab = PERWidget()
                # No real power meter is wired in this Python project yet, so start in "disconnected" mode.
                # (Demo can still be used to visualize behavior.)
                tab_widget.addTab(self.per_tab, "PER")
                try:
                    self.per_tab.connect_gui_actions(
                        on_continuous=self._per_trigger_continuous_run,
                        on_sweep=self._per_trigger_2x360_sweep,
                        on_abort=self._abort_per_sweep_from_tab,
                        on_home=self._per_trigger_home_motor,
                    )
                except Exception:
                    pass
                # Settings tab (laser-related controls)
                # --- Arroyo TEC + Laser Control Tab ---
                # --- Refactored Settings Tab: Split left/right ---
                arroyo_tab = QWidget()
                tab_widget.addTab(arroyo_tab, "Settings")

                

                # --- M² / Divergence tab (Thorlabs Beam software integration stub) ---
                try:
                    if M2MeasurementWidget is None:
                        raise RuntimeError("m2_measurment.py not available (import failed).")
                    self.m2_widget = M2MeasurementWidget(parent=self)
                    tab_widget.addTab(self.m2_widget, getattr(self.m2_widget, "TAB_TITLE", "M² Measurement"))
                except Exception as e:
                    try:
                        self.log_status(f"M² tab failed to load: {e}", "ERROR")
                    except Exception:
                        pass
                    self.m2_widget = None
                arroyo_tab_layout = QVBoxLayout(arroyo_tab)
                arroyo_tab_layout.setContentsMargins(12, 12, 12, 12)
                arroyo_tab_layout.setSpacing(10)

                settings_scroll = QScrollArea()
                settings_scroll.setWidgetResizable(True)
                settings_scroll.setFrameShape(QScrollArea.NoFrame)
                arroyo_tab_layout.addWidget(settings_scroll)

                settings_content = QWidget()
                settings_scroll.setWidget(settings_content)

                columns_layout = QHBoxLayout(settings_content)
                columns_layout.setContentsMargins(6, 6, 6, 6)
                columns_layout.setSpacing(12)

                # Column 1: Connection / Power Meter / UV
                left_widget = QWidget()
                left_layout = QVBoxLayout(left_widget)
                left_layout.setSpacing(10)
                left_layout.setContentsMargins(6, 6, 6, 6)

                # Column 2: Camera-related settings (Image Rotation, etc.)
                middle_widget = QWidget()
                middle_layout = QVBoxLayout(middle_widget)
                middle_layout.setSpacing(10)
                middle_layout.setContentsMargins(6, 6, 6, 6)

                # Column 3: Motor / TEC / Laser
                right_widget = QWidget()
                right_layout = QVBoxLayout(right_widget)
                right_layout.setSpacing(10)
                right_layout.setContentsMargins(6, 6, 6, 6)

                columns_layout.addWidget(left_widget, 1)
                columns_layout.addWidget(middle_widget, 1)
                columns_layout.addWidget(right_widget, 1)

                # LEFT COLUMN CONTENT

                # Engineering Settings (LabVIEW-style gate + Auto Exposure toggle)
                self.engineering_group = QGroupBox("Engineering Settings")
                self.engineering_group.setContentsMargins(12, 12, 12, 12)
                self.engineering_group.setMinimumWidth(400)
                eng_layout = QVBoxLayout(self.engineering_group)
                eng_layout.setContentsMargins(12, 12, 12, 12)
                eng_layout.setSpacing(10)

                self.lbl_engineering_note = QLabel("Please input a password in order\nto access the engineering settings")
                self.lbl_engineering_note.setWordWrap(True)

                btn_row = QHBoxLayout()
                self.btn_enable_auto_exposure = QPushButton("Enable Auto Exposure")
                self.btn_enable_auto_exposure.setCheckable(True)
                self.btn_enable_auto_exposure.setChecked(bool(getattr(getattr(self, 'config', None), 'auto_exposure', None) and self.config.auto_exposure.enabled))
                self._update_auto_exposure_button_style(self.btn_enable_auto_exposure.isChecked())

                self.btn_require_password = QPushButton("Require Password")
                self.btn_require_password.setCheckable(True)
                self.btn_require_password.setChecked(False)

                btn_row.addWidget(self.btn_require_password)

                eng_layout.addWidget(self.lbl_engineering_note)
                eng_layout.addLayout(btn_row)

                left_layout.addWidget(self.engineering_group)
                self.btn_enable_auto_exposure.toggled.connect(self._on_auto_exposure_toggled)
                self.btn_require_password.toggled.connect(self._on_require_password_toggled)
                # Power Meter
                try:
                    self.pm_settings_panel = PowerMeterSettingsPanel(per_widget=self.per_tab, parent=self)
                    self.pm_settings_panel.setContentsMargins(12, 12, 12, 12)
                    self.pm_settings_panel.setMinimumWidth(400)
                    left_layout.addWidget(self.pm_settings_panel)
                    self.log_status("Power Meter settings panel added to Settings tab.", "INFO")
                except Exception as e:
                    self.pm_settings_panel = None
                    self.log_status(f"Failed to add Power Meter settings panel: {e}", "ERROR")
                # Connection Group
                connection_group = QGroupBox("Connection")
                connection_group.setContentsMargins(12, 12, 12, 12)
                connection_group.setMinimumWidth(400)
                connection_layout = QGridLayout(connection_group)
                connection_layout.setHorizontalSpacing(14)
                connection_layout.setVerticalSpacing(8)
                connection_layout.setContentsMargins(12, 12, 12, 12)
                connection_layout.setHorizontalSpacing(12)
                connection_layout.setVerticalSpacing(8)
                self.rb_separate = QRadioButton("Separate Instruments")
                self.rb_combo = QRadioButton("Combo Instrument")
                self.rb_combo.setChecked(True)
                # Keep radio controls for backend compatibility, but hide from UI.
                self.rb_separate.setVisible(False)
                self.rb_combo.setVisible(False)
                self.combo_tec = QComboBox()
                self.combo_laser = QComboBox()
                # Keep TEC combo hidden and mirror Laser selection into it for legacy paths.
                self.combo_tec.setVisible(False)
                connection_layout.addWidget(QLabel("Laser Source COM:"), 1, 0)
                connection_layout.addWidget(self.combo_laser, 1, 1, 1, 2)
                self.disable_arroyo_cb = QCheckBox("Disable Arroyo")
                self.disable_arroyo_cb.setToolTip("Block all Arroyo TEC/Laser I/O even if connected")
                connection_layout.addWidget(self.disable_arroyo_cb, 1, 3)
                self.disable_arroyo_cb.toggled.connect(self._on_disable_arroyo_toggled)
                self.btn_refresh = QPushButton("Refresh COM Ports")
                self.btn_connect = QPushButton("CONNECT")
                self.btn_connect.setStyleSheet("background-color: #3ecfcf; font-weight: bold; font-size: 14px; height: 32px;")
                connection_layout.addWidget(self.btn_refresh, 2, 0, 1, 2)
                connection_layout.addWidget(self.btn_connect, 3, 0, 1, 4)
                self.btn_refresh.clicked.connect(self.refresh_com_ports)
                self.btn_connect.clicked.connect(self.toggle_connection)
                self.combo_laser.currentTextChanged.connect(lambda t: self.combo_tec.setCurrentText(t))
                left_layout.addWidget(connection_group)

                # Populate COM port dropdowns at startup (only existing ports)
                try:
                    self.refresh_com_ports()
                except Exception:
                    pass

                # Configuration & Control (moved from Main)
                cfg_group = QGroupBox("Configuration & Control")
                cfg_group.setContentsMargins(12, 12, 12, 12)
                cfg_group.setMinimumWidth(400)
                cfg_layout = QGridLayout(cfg_group)
                cfg_layout.setContentsMargins(12, 12, 12, 12)
                cfg_layout.setHorizontalSpacing(12)
                cfg_layout.setVerticalSpacing(8)

                cfg_layout.addWidget(QLabel("Mode:"), 0, 0)
                cfg_layout.addWidget(self.mode_combo, 0, 1, 1, 3)

                cfg_layout.addWidget(QLabel("Camera Source:"), 1, 0)
                cfg_layout.addWidget(self.camera_source_combo, 1, 1)
                cfg_layout.addWidget(QLabel("OpenCV Index:"), 1, 2)
                cfg_layout.addWidget(self.cam_index_spin, 1, 3)

                cfg_layout.addWidget(self.force_basler_only_cb, 2, 0, 1, 4)

                cfg_layout.addWidget(QLabel("Image:"), 3, 0)
                cfg_layout.addWidget(self.image_path_input, 3, 1, 1, 2)
                cfg_layout.addWidget(self.browse_btn, 3, 3)

                cfg_layout.addWidget(self.enable_logging_cb, 4, 0, 1, 2)
                cfg_layout.addWidget(self.show_overlay_cb, 4, 2, 1, 2)

                cfg_layout.addWidget(self.auto_analyze_cb, 5, 0, 1, 2)
                cfg_layout.addWidget(QLabel("Period (ms):"), 5, 2)
                cfg_layout.addWidget(self.auto_analyze_period, 5, 3)

                cfg_layout.addWidget(self.clear_btn, 6, 0, 1, 4)

                middle_layout.addWidget(cfg_group)
                # Camera Attributes (Main Camera) + Averaging (LabVIEW-style)
                camattr_group = QGroupBox("Camera Attributes (Main Camera)")
                camattr_group.setContentsMargins(12, 12, 12, 12)
                camattr_group.setMinimumWidth(420)
                camattr_layout = QGridLayout(camattr_group)
                camattr_layout.setContentsMargins(12, 12, 12, 12)
                camattr_layout.setHorizontalSpacing(14)
                camattr_layout.setVerticalSpacing(8)
                camattr_layout.setColumnMinimumWidth(0, 190)
                camattr_layout.setColumnStretch(1, 1)

                # Exposure in ms (matches LabVIEW control units)
                self.exposure_ms_spin = QDoubleSpinBox()
                self.exposure_ms_spin.setDecimals(2)
                self.exposure_ms_spin.setRange(0.05, 5000.0)
                self.exposure_ms_spin.setValue(10.0)
                self.exposure_ms_spin.setSuffix(" ms")
                self.exposure_ms_spin.setToolTip("Main camera exposure in milliseconds (ms).")

                # Max exposure in ms (hard clamp for auto/manual exposure writes)
                self.max_exposure_ms_spin = QDoubleSpinBox()
                self.max_exposure_ms_spin.setDecimals(2)
                self.max_exposure_ms_spin.setRange(0.05, 5000.0)
                self.max_exposure_ms_spin.setValue(1000.0)
                self.max_exposure_ms_spin.setEnabled(False)
                self.max_exposure_ms_spin.setSuffix(" ms")
                self.max_exposure_ms_spin.setToolTip("Maximum allowed exposure (ms). Auto-exposure will never exceed this.")

                # Optional gain (driver-dependent)
                self.gain_db_spin = QDoubleSpinBox()
                self.gain_db_spin.setDecimals(2)
                self.gain_db_spin.setRange(0.0, 24.0)
                self.gain_db_spin.setValue(0.0)
                self.gain_db_spin.setSuffix(" dB")
                self.gain_db_spin.setToolTip("Camera gain (dB). Use sparingly; exposure is preferred for brightness control.")

                # SA/FA reference points (display/cursor reference)
                self.sa_reference_spin = QSpinBox()
                self.sa_reference_spin.setRange(0, 100000)
                self.sa_reference_spin.setValue(0)
                self.sa_reference_spin.setToolTip("SA Reference Point (pixel index). Used as a display/reference marker.")

                self.fa_reference_spin = QSpinBox()
                self.fa_reference_spin.setRange(0, 100000)
                self.fa_reference_spin.setValue(0)
                self.fa_reference_spin.setToolTip("FA Reference Point (pixel index). Used as a display/reference marker.")

                camattr_layout.addWidget(QLabel("Exposure (ms):"), 0, 0)
                camattr_layout.addWidget(self.exposure_ms_spin, 0, 1)
                camattr_layout.addWidget(QLabel("Max Exposure (ms):"), 1, 0)
                camattr_layout.addWidget(self.max_exposure_ms_spin, 1, 1)
                camattr_layout.addWidget(QLabel("Gain (dB):"), 2, 0)
                camattr_layout.addWidget(self.gain_db_spin, 2, 1)
                camattr_layout.addWidget(QLabel("SA Reference Point:"), 3, 0)
                camattr_layout.addWidget(self.sa_reference_spin, 3, 1)
                camattr_layout.addWidget(QLabel("FA Reference Point:"), 4, 0)
                camattr_layout.addWidget(self.fa_reference_spin, 4, 1)

                middle_layout.addWidget(camattr_group)



                # Saturation threshold + PI gains (moved from Main panel)
                self.sat_pi_group = QGroupBox("Saturation / Auto-Exposure PI")
                self.sat_pi_group.setContentsMargins(12, 12, 12, 12)
                self.sat_pi_group.setMinimumWidth(420)
                satpi_layout = QGridLayout(self.sat_pi_group)
                satpi_layout.setContentsMargins(12, 12, 12, 12)
                satpi_layout.setHorizontalSpacing(14)
                satpi_layout.setVerticalSpacing(8)
                satpi_layout.setColumnMinimumWidth(0, 190)
                satpi_layout.setColumnStretch(1, 1)

                satpi_layout.addWidget(self.btn_enable_auto_exposure, 0, 0, 1, 2)

                satpi_layout.addWidget(QLabel("Sat Threshold (%)"), 1, 0)
                self.sat_thresh_input = QDoubleSpinBox()
                self.sat_thresh_input.setRange(0.0, 100.0)
                self.sat_thresh_input.setDecimals(3)
                self.sat_thresh_input.setSingleStep(0.05)
                self.sat_thresh_input.setValue(0.2)
                satpi_layout.addWidget(self.sat_thresh_input, 1, 1)

                satpi_layout.addWidget(QLabel("Kp"), 2, 0)
                self.sat_kp_spin = QDoubleSpinBox()
                self.sat_kp_spin.setRange(0.0, 1000.0)
                self.sat_kp_spin.setDecimals(6)
                self.sat_kp_spin.setSingleStep(0.001)
                self.sat_kp_spin.setValue(0.2)
                satpi_layout.addWidget(self.sat_kp_spin, 2, 1)

                satpi_layout.addWidget(QLabel("Ki"), 3, 0)
                self.sat_ki_spin = QDoubleSpinBox()
                self.sat_ki_spin.setRange(0.0, 1000.0)
                self.sat_ki_spin.setDecimals(6)
                self.sat_ki_spin.setSingleStep(0.001)
                self.sat_ki_spin.setValue(0.05)
                satpi_layout.addWidget(self.sat_ki_spin, 3, 1)

                # keep config in-sync when values change
                self.sat_thresh_input.valueChanged.connect(self._on_sat_pi_params_changed)
                self.sat_kp_spin.valueChanged.connect(self._on_sat_pi_params_changed)
                self.sat_ki_spin.valueChanged.connect(self._on_sat_pi_params_changed)

                middle_layout.addWidget(self.sat_pi_group)

                avg_group = QGroupBox("Averaging / Intensity Graph")
                avg_group.setContentsMargins(12, 12, 12, 12)
                avg_group.setMinimumWidth(420)
                avg_layout = QGridLayout(avg_group)
                avg_layout.setContentsMargins(12, 12, 12, 12)
                avg_layout.setHorizontalSpacing(14)
                avg_layout.setVerticalSpacing(8)
                avg_layout.setColumnMinimumWidth(0, 190)
                avg_layout.setColumnStretch(1, 1)

                self.enable_averaging_cb = QCheckBox("Enable Averaging")
                self.enable_averaging_cb.setChecked(True)
                self.enable_averaging_cb.setToolTip("If enabled, keeps a rolling N-frame average before profile extraction.")

                self.averaging_frames_spin = QSpinBox()
                self.averaging_frames_spin.setRange(1, 100)
                self.averaging_frames_spin.setValue(5)
                self.averaging_frames_spin.setToolTip("Number of frames for rolling average (N).")

                avg_layout.addWidget(self.enable_averaging_cb, 0, 0, 1, 2)
                avg_layout.addWidget(QLabel("Averaging Frames (N):"), 1, 0)
                avg_layout.addWidget(self.averaging_frames_spin, 1, 1)

                middle_layout.addWidget(avg_group)


                # Image Rotation (Camera 2 / Camera 3)
                imgrot_group = QGroupBox("Image Rotation (Camera 2 / Camera 3)")
                imgrot_group.setContentsMargins(12, 12, 12, 12)
                imgrot_group.setMinimumWidth(400)
                imgrot_layout = QGridLayout(imgrot_group)
                imgrot_layout.setHorizontalSpacing(14)
                imgrot_layout.setVerticalSpacing(8)
                imgrot_layout.setContentsMargins(12, 12, 12, 12)
                imgrot_layout.setColumnMinimumWidth(0, 175)
                imgrot_layout.setColumnMinimumWidth(2, 175)
                imgrot_layout.setColumnStretch(1, 1)
                imgrot_layout.setColumnStretch(3, 1)
                imgrot_layout.setHorizontalSpacing(12)
                imgrot_layout.setVerticalSpacing(8)

                # Cam2/Cam3 are always enabled and shown in a separate window at startup.

                
                # Cam2 / Cam3 are fixed USB cameras in this station build (no Basler selection here)

# Webcam indices for Simulation (OpenCV)
                self._lbl_cam2_webcam_index = QLabel("Cam2 Webcam Index:")
                self._lbl_cam2_webcam_index.setVisible(False)
                imgrot_layout.addWidget(self._lbl_cam2_webcam_index, 3, 0)
                self.cam2_index_spin = QSpinBox()
                self.cam2_index_spin.setRange(0, 10)
                self.cam2_index_spin.setValue(0)
                self.cam2_index_spin.setEnabled(False)
                self.cam2_index_spin.setVisible(False)
                imgrot_layout.addWidget(self.cam2_index_spin, 3, 1)

                self._lbl_cam3_webcam_index = QLabel("Cam3 Webcam Index:")
                self._lbl_cam3_webcam_index.setVisible(False)
                imgrot_layout.addWidget(self._lbl_cam3_webcam_index, 3, 2)
                self.cam3_index_spin = QSpinBox()
                self.cam3_index_spin.setRange(0, 10)
                self.cam3_index_spin.setValue(1)
                self.cam3_index_spin.setEnabled(False)
                self.cam3_index_spin.setVisible(False)
                imgrot_layout.addWidget(self.cam3_index_spin, 3, 3)

                self._lbl_usb_fixed_note = QLabel("Cam2/Cam3 are fixed USB cameras: Cam2 index=0, Cam3 index=1")
                self._lbl_usb_fixed_note.setStyleSheet("color: #555; font-style: italic;")
                imgrot_layout.addWidget(self._lbl_usb_fixed_note, 3, 0, 1, 4)

                # Rotation/exposure controls
                imgrot_layout.addWidget(QLabel("Camera 2 Rotation (°):"), 4, 0)
                self.cam2_rotation_spin = QSpinBox()
                self.cam2_rotation_spin.setRange(0, 360)
                self.cam2_rotation_spin.setSingleStep(90)
                self.cam2_rotation_spin.setValue(90)
                imgrot_layout.addWidget(self.cam2_rotation_spin, 4, 1)

                imgrot_layout.addWidget(QLabel("Camera 2 Exposure (µs):"), 4, 2)
                self.cam2_exposure_spin = QSpinBox()
                self.cam2_exposure_spin.setRange(1, 2000000)
                self.cam2_exposure_spin.setValue(5000)
                imgrot_layout.addWidget(self.cam2_exposure_spin, 4, 3)

                imgrot_layout.addWidget(QLabel("Camera 3 Rotation (°):"), 5, 0)
                self.cam3_rotation_spin = QSpinBox()
                self.cam3_rotation_spin.setRange(0, 360)
                self.cam3_rotation_spin.setSingleStep(90)
                self.cam3_rotation_spin.setValue(90)
                imgrot_layout.addWidget(self.cam3_rotation_spin, 5, 1)

                imgrot_layout.addWidget(QLabel("Camera 3 Exposure (µs):"), 5, 2)
                self.cam3_exposure_spin = QSpinBox()
                self.cam3_exposure_spin.setRange(1, 2000000)
                self.cam3_exposure_spin.setValue(5000)
                imgrot_layout.addWidget(self.cam3_exposure_spin, 5, 3)

                self.btn_show_cam23 = QPushButton("Show Cam2/Cam3 Window")
                self.btn_show_cam23.setStyleSheet("background-color: #ddd; font-weight: bold; height: 28px;")
                imgrot_layout.addWidget(self.btn_show_cam23, 6, 0, 1, 4)

                # Wire events
                self.btn_show_cam23.clicked.connect(self.open_secondary_cameras_window)
                self.cam2_index_spin.valueChanged.connect(self._on_secondary_cam_settings_changed)
                self.cam3_index_spin.valueChanged.connect(self._on_secondary_cam_settings_changed)
                self.cam2_rotation_spin.valueChanged.connect(self._on_secondary_cam_settings_changed)
                self.cam3_rotation_spin.valueChanged.connect(self._on_secondary_cam_settings_changed)
                self.cam2_exposure_spin.valueChanged.connect(self._on_secondary_cam_settings_changed)
                self.cam3_exposure_spin.valueChanged.connect(self._on_secondary_cam_settings_changed)

                middle_layout.addWidget(imgrot_group)



                # UV Control
                try:
                    if not hasattr(self, "uv_control_panel") or self.uv_control_panel is None:
                        self.uv_control_panel = UVControlPanel(parent=self)
                    if hasattr(self.uv_control_panel, "build_settings_group_for_layout"):
                        uv_group = self.uv_control_panel.build_settings_group_for_layout(minimum_width=400)
                    else:
                        uv_group = self.uv_control_panel.build_settings_group()
                        uv_group.setContentsMargins(12, 12, 12, 12)
                        uv_group.setMinimumWidth(400)
                    left_layout.addWidget(uv_group)
                    self.log_status("UV advanced controls added to Settings tab.", "INFO")
                    self._pending_uv_settings = None
                except Exception as e:
                    self.log_status(f"Failed to attach UV settings: {e}", "ERROR")

                # RIGHT COLUMN CONTENT

                # Motor
                try:
                    self.motor_panel = MotorControlPanel(parent=self, status_logger=self.log_status)
                    self.motor_panel.set_per_components(self.per_tab, self.pm_settings_panel)
                    self.motor_panel.setContentsMargins(12, 12, 12, 12)
                    self.motor_panel.setMinimumWidth(400)
                    right_layout.addWidget(self.motor_panel)
                    self.log_status("Motor/Angle control panel added to Settings tab.", "INFO")
                except Exception as e:
                    self.motor_panel = None
                    self.log_status(f"Failed to add Motor/Angle control panel: {e}", "ERROR")

                # TEC CONTROL
                tec_group = QGroupBox("TEC CONTROL")
                tec_group.setContentsMargins(12, 12, 12, 12)
                tec_group.setMinimumWidth(400)
                tec_group.setMaximumHeight(220)
                tec_layout = QGridLayout(tec_group)
                tec_layout.setHorizontalSpacing(14)
                tec_layout.setVerticalSpacing(8)
                tec_layout.setContentsMargins(12, 12, 12, 12)
                tec_layout.setHorizontalSpacing(12)
                tec_layout.setVerticalSpacing(8)
                tec_labels = ["Set Temp (°C):", "Max Temp (°C):", "Min Temp (°C):", "Max Current (A):"]
                self.tec_edits = []
                for i, label in enumerate(tec_labels):
                    tec_layout.addWidget(QLabel(label), i, 0)
                    edit = QLineEdit(); edit.setFixedWidth(70)
                    self.tec_edits.append(edit)
                    tec_layout.addWidget(edit, i, 1)
                    if i == 0:
                        btn = QPushButton("Set"); btn.setFixedWidth(50); btn.clicked.connect(self.set_temp)
                    elif i == 1:
                        btn = QPushButton("Set"); btn.setFixedWidth(50); btn.clicked.connect(self.set_max_temp)
                    elif i == 2:
                        btn = QPushButton("Set"); btn.setFixedWidth(50); btn.clicked.connect(self.set_min_temp)
                    elif i == 3:
                        btn = QPushButton("Set"); btn.setFixedWidth(50); btn.clicked.connect(self.set_max_tec_current)
                    tec_layout.addWidget(btn, i, 2)
                self.btn_tec_on = QPushButton("TEC ON"); self.btn_tec_on.setStyleSheet("background-color: #3ecfcf; font-weight: bold;")
                self.btn_tec_off = QPushButton("TEC OFF"); self.btn_tec_off.setEnabled(False)
                self.btn_tec_on.clicked.connect(self.tec_on)
                self.btn_tec_off.clicked.connect(self.tec_off)
                tec_layout.addWidget(self.btn_tec_on, 4, 0, 1, 1)
                tec_layout.addWidget(self.btn_tec_off, 4, 1, 1, 2)
                self.arroyo_temp_label = QLabel("-- °C")
                tec_layout.addWidget(self.arroyo_temp_label, 5, 0, 1, 3, alignment=Qt.AlignHCenter)
                tec_layout.addWidget(QLabel("Actual Temp:"), 6, 0, 1, 3, alignment=Qt.AlignHCenter)
                right_layout.addWidget(tec_group)

                # LASER CONTROL
                laser_group = QGroupBox("LASER CONTROL")
                laser_group.setContentsMargins(12, 12, 12, 12)
                laser_group.setMinimumWidth(400)
                laser_group.setMaximumHeight(240)
                laser_layout = QGridLayout(laser_group)
                laser_layout.setHorizontalSpacing(14)
                laser_layout.setVerticalSpacing(8)
                laser_layout.setContentsMargins(12, 12, 12, 12)
                laser_layout.setHorizontalSpacing(12)
                laser_layout.setVerticalSpacing(8)
                laser_labels = ["Set Current (mA):", "Max Current (mA):", "Max Voltage (V):", "Max Power (mW):"]
                self.laser_edits = []
                for i, label in enumerate(laser_labels):
                    laser_layout.addWidget(QLabel(label), i, 0)
                    edit = QLineEdit(); edit.setFixedWidth(70)
                    self.laser_edits.append(edit)
                    laser_layout.addWidget(edit, i, 1)
                    if i == 0:
                        btn = QPushButton("Set"); btn.setFixedWidth(50); btn.clicked.connect(self.set_laser_current)
                    elif i == 1:
                        btn = QPushButton("Set"); btn.setFixedWidth(50); btn.clicked.connect(self.set_max_laser_current)
                    elif i == 2:
                        btn = QPushButton("Set"); btn.setFixedWidth(50); btn.clicked.connect(self.set_max_laser_voltage)
                    elif i == 3:
                        btn = QPushButton("Set"); btn.setFixedWidth(50); btn.clicked.connect(self.set_max_laser_power)
                    laser_layout.addWidget(btn, i, 2)
                self.btn_laser_on = QPushButton("LASER ON"); self.btn_laser_on.setEnabled(False)
                self.btn_laser_off = QPushButton("LASER OFF"); self.btn_laser_off.setEnabled(False)
                self.btn_laser_on.clicked.connect(self.laser_on)
                self.btn_laser_off.clicked.connect(self.laser_off)
                laser_layout.addWidget(self.btn_laser_on, 4, 0, 1, 1)
                laser_layout.addWidget(self.btn_laser_off, 4, 1, 1, 2)
                self.arroyo_current_label = QLabel("-- mA")
                laser_layout.addWidget(self.arroyo_current_label, 5, 0, 1, 3, alignment=Qt.AlignHCenter)
                laser_layout.addWidget(QLabel("Actual Current:"), 6, 0, 1, 3, alignment=Qt.AlignHCenter)
                right_layout.addWidget(laser_group)

                # Status Log
                status_group = QGroupBox("Status Log")
                status_group.setContentsMargins(12, 12, 12, 12)
                status_group.setMinimumWidth(400)
                status_layout = QVBoxLayout(status_group)
                status_layout.setSpacing(8)
                self.status_log = QTextEdit()
                self.status_log.setReadOnly(True)
                self.status_log.setStyleSheet("background-color: #222; color: #8ff; font-family: monospace;")
                self.status_log.setFixedHeight(80)
                self.status_log.setText("[11:37:53] [INFO] Arroyo Controller initialized. Ready to connect.")
                status_layout.addWidget(self.status_log)
                right_layout.addWidget(status_group)

                left_layout.addStretch(1)
                middle_layout.addStretch(1)
                right_layout.addStretch(1)
            def create_left_panel(self):
                """Left panel with only Analyze button; config controls moved to Settings."""
                panel = QGroupBox("Configuration & Control")
                panel.setMinimumWidth(220)
                layout = QVBoxLayout()
                layout.setSpacing(16)
                layout.setContentsMargins(16, 12, 16, 12)

                # Keep these widgets instantiated for shared logic; they are now shown in Settings.
                self.status_label = QLabel("Ready")
                self.status_label.setStyleSheet("color: blue; font-weight: bold; padding: 10px; background-color: #f0f0f0; border-radius: 3px;")
                self.progress_bar = QProgressBar()
                self.progress_bar.setVisible(False)
                layout.addWidget(self.status_label)
                layout.addWidget(self.progress_bar)

                # Connection keys (red=disconnected/off, green=connected/on)
                conn_box = QGroupBox("Connections Status")
                conn_grid = QGridLayout(conn_box)
                conn_grid.setHorizontalSpacing(8)
                conn_grid.setVerticalSpacing(4)
                self._conn_leds = {}
                conn_rows = [
                    ("connection", "Arroyo"),
                    ("auto_exposure", "Enable Auto Exposure"),
                    ("uv_control", "UV Control"),
                    ("power_meter", "Power Meter"),
                    ("angle_control", "Angle Control"),
                ]
                for r, (key, text) in enumerate(conn_rows):
                    lbl = QLabel("●")
                    lbl.setFixedWidth(14)
                    lbl.setAlignment(Qt.AlignCenter)
                    lbl.setStyleSheet("color: #d50000; font-size: 14px; font-weight: bold;")
                    self._conn_leds[key] = lbl
                    conn_grid.addWidget(lbl, r, 0)
                    conn_grid.addWidget(QLabel(text), r, 1)
                layout.addWidget(conn_box)

                self.mode_combo = QComboBox()
                self.mode_combo.addItems(["Simulation (Load Image)", "Live Camera"])
                self.mode_combo.setCurrentText("Live Camera")
                self.mode_combo.currentIndexChanged.connect(self.on_mode_changed)
                self.mode_combo.setMinimumWidth(220)

                self.camera_source_combo = QComboBox()
                self.camera_source_combo.addItems(['External Camera', 'OpenCV Camera'])
                self.camera_source_combo.setMinimumWidth(110)
                self.camera_source_combo.setMaximumWidth(140)
                self.camera_source_combo.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
                self.camera_source_combo.currentIndexChanged.connect(self.on_camera_source_changed)

                self.force_basler_only_cb = QCheckBox("Force Basler-only mode")
                self.force_basler_only_cb.setToolTip("If enabled, the main camera source is locked to External Camera (Basler) and OpenCV/webcam options are disabled.")
                self.force_basler_only_cb.setChecked(False)
                self.force_basler_only_cb.toggled.connect(self._on_force_basler_only_toggled)

                self.cam_index_spin = QSpinBox()
                self.cam_index_spin.setRange(0, 10)
                self.cam_index_spin.setValue(0)
                self.cam_index_spin.setFixedWidth(45)
                self.cam_index_spin.valueChanged.connect(self.on_cam_index_changed)

                self.image_path_input = QLineEdit("")
                self.browse_btn = QPushButton("Browse...")
                self.browse_btn.clicked.connect(self.browse_image)

                self.enable_logging_cb = QCheckBox("Enable Data Logging")
                self.enable_logging_cb.setChecked(True)
                self.show_overlay_cb = QCheckBox("Generate Plot")
                self.show_overlay_cb.setChecked(True)

                self.auto_analyze_cb = QCheckBox("Auto Analyze (continuous)")
                self.auto_analyze_cb.setChecked(False)
                self.auto_analyze_cb.stateChanged.connect(self.toggle_auto_analyze)

                self.auto_analyze_period = QSpinBox()
                self.auto_analyze_period.setRange(50, 5000)
                self.auto_analyze_period.setSingleStep(50)
                self.auto_analyze_period.setValue(50)#was 250
                self.auto_analyze_period.valueChanged.connect(self._auto_analyze_period_changed)

                self.clear_btn = QPushButton("Clear Results")
                self.clear_btn.clicked.connect(self.clear_results)

                # Keep only Analyze button on Main panel.
                self.analyze_btn = QPushButton("Analyze Image")
                self.analyze_btn.setStyleSheet("background-color: #4CAF50; color: white; font-weight: bold; padding: 10px; font-size: 12px;")
                self.analyze_btn.clicked.connect(self.start_analysis)
                layout.addWidget(self.analyze_btn)

                self.stop_analysis_btn = QPushButton("Stop Analysis")
                self.stop_analysis_btn.setStyleSheet("background-color: #d9534f; color: white; font-weight: bold; padding: 10px; font-size: 12px;")
                self.stop_analysis_btn.clicked.connect(self.stop_analysis_only)
                layout.addWidget(self.stop_analysis_btn)

                layout.addSpacing(8)
                layout.addWidget(QLabel("Status Log:"))
                self.main_status_log = QTextEdit()
                self.main_status_log.setReadOnly(True)
                self.main_status_log.setStyleSheet("background-color: #222; color: #8ff; font-family: monospace;")
                self.main_status_log.setFixedHeight(120)
                self.main_status_log.setText("[11:37:53] [INFO] Arroyo Controller initialized. Ready to connect.")
                layout.addWidget(self.main_status_log)

                layout.addStretch()

                panel.setLayout(layout)
                panel.setMaximumWidth(300)
                return panel

            def _set_connection_led(self, key: str, is_on: bool):
                leds = getattr(self, "_conn_leds", None)
                if not isinstance(leds, dict):
                    return
                led = leds.get(key)
                if led is None:
                    return
                color = "#00c853" if bool(is_on) else "#d50000"
                led.setStyleSheet(f"color: {color}; font-size: 14px; font-weight: bold;")

            def _refresh_connection_indicators(self):
                try:
                    connection_ok = bool(getattr(self, "is_connected", False))
                    auto_exposure_ok = bool(
                        hasattr(self, "btn_enable_auto_exposure")
                        and self.btn_enable_auto_exposure is not None
                        and self.btn_enable_auto_exposure.isChecked()
                    )

                    uv_ok = False
                    uv = getattr(self, "uv_control_panel", None)
                    if uv is not None:
                        if hasattr(uv, "is_uv_connected"):
                            uv_ok = bool(uv.is_uv_connected())
                        elif bool(getattr(uv, "simulation_enabled", False)):
                            uv_ok = False
                        elif hasattr(uv, "_omnicure_hw"):
                            uv_ok = bool(getattr(uv._omnicure_hw, "is_connected", False))

                    pm_ok = False
                    pm = getattr(self, "pm_settings_panel", None)
                    if pm is not None:
                        pm_connected = bool(getattr(pm, "_pm_connected", False))
                        pm_disabled = bool(hasattr(pm, "chk_disable_pm") and pm.chk_disable_pm.isChecked())
                        pm_ok = pm_connected and (not pm_disabled)

                    angle_ok = False
                    mp = getattr(self, "motor_panel", None)
                    if mp is not None and hasattr(mp, "backend") and mp.backend is not None:
                        with contextlib.suppress(Exception):
                            angle_ok = bool(mp.backend.is_connected())

                    self._set_connection_led("connection", connection_ok)
                    self._set_connection_led("auto_exposure", auto_exposure_ok)
                    self._set_connection_led("uv_control", uv_ok)
                    self._set_connection_led("power_meter", pm_ok)
                    self._set_connection_led("angle_control", angle_ok)
                except Exception:
                    pass

            def create_right_panel(self):
                """Right panel split into TOP (parameters/log) and BOTTOM (zoomed beam)."""
                panel = QWidget()
                layout = QVBoxLayout(panel)
                layout.setContentsMargins(0, 0, 0, 0)
                layout.setSpacing(6)

                splitter = QSplitter(Qt.Vertical)

                # --- TOP: tabs for metrics + logging ---
                top_tabs = QTabWidget()

                # -----------------------------
                # Beam Details tab (move before Laser Control)
                # -----------------------------
                top_tabs.setStyleSheet("QTabWidget::pane { margin: 0px; padding: 0px; } QTabBar::tab { margin: 0px; padding: 2px 6px; }")
                details = self.create_beam_details_tab()
                top_tabs.addTab(details, "Beam Details")

                # -----------------------------
                # Laser Control tab (guaranteed)
                # -----------------------------
                try:
                    if ProductRecipe is None:
                        raise RuntimeError("ProductRecipe is None")

                    self.laser_control_panel = LaserControlPanel(ProductRecipe, parent=self)
                    top_tabs.addTab(self.laser_control_panel, getattr(self.laser_control_panel, "TAB_TITLE", "Laser Control"))
                    self.laser_control_panel.connect_gui_actions(
                        on_laser_on=self._laser_control_laser_on,
                        on_laser_off=self._laser_control_laser_off,
                        on_recipe_changed=self._laser_control_recipe_changed,
                    )

                    # Auto-fill product + set-current from General Laser Specification Reference.csv
                    self._init_general_laser_spec_lookup()


                    # Scan all XML files in the current folder and load their products
                    try:
                        xml_dir = os.path.dirname(__file__)
                        loaded_products = self.laser_control_panel.load_products_from_directory(xml_dir)
                        self.log_status(f"Loaded products from XMLs: {loaded_products}", "INFO")
                    except Exception as e:
                        self.log_status(f"Product XML scan failed: {e}", "ERROR")

                    self.log_status("Laser Control tab loaded.", "INFO")
                except Exception as e:
                    self.log_status(f"Laser Control tab failed to load: {e}", "ERROR")

                # -----------------------------
                # UV Control tab (Omnicure)
                # -----------------------------
                try:
                    if UVControlPanel is None:
                        raise RuntimeError("UVControlPanel is None (uv_control_panel.py not found / import failed)")
                    self.uv_control_panel = UVControlPanel(parent=self)
                    top_tabs.addTab(self.uv_control_panel, "UV Control")
                    self.log_status("UV Control tab loaded.", "INFO")
                    # Defer moving advanced UV controls to the Settings tab until Settings is built
                    self._pending_uv_settings = self.uv_control_panel
                except Exception as e:
                    self.uv_control_panel = None
                    self.log_status(f"UV Control import failed: {e}", "ERROR")
                    self._pending_uv_settings = None
                    self.log_status(f"UV Control tab failed to load: {e}", "ERROR")

                logs = self.create_logging_tab()
                top_tabs.addTab(logs, "Log & Export")

                splitter.addWidget(top_tabs)

                # --- BOTTOM: zoomed beam image (replaces old Intensity tab content) ---
                zoom_widget = self.create_zoomed_beam_tab()
                splitter.addWidget(zoom_widget)

                splitter.setStretchFactor(0, 2)
                splitter.setStretchFactor(1, 1)
                splitter.setSizes([320, 680])  # ensure tabs are visible

                layout.addWidget(splitter)

                panel.setMaximumWidth(360)
                return panel

            def create_beam_details_tab(self):

                """Create beam details display."""
                widget = QWidget()
                layout = QGridLayout(widget)

                self.beam_details = {}

                metrics = [
                    ("Centroid X (px):", "centroid_x"),
                    ("Centroid Y (px):", "centroid_y"),
                    ("FWHM X (µm):", "fwhm_x"),
                    ("FWHM Y (µm):", "fwhm_y"),
                    ("1/e² X (µm):", "width_1e2_x"),
                    ("1/e² Y (µm):", "width_1e2_y"),
                    ("95% SA (µm):", "p95_sa"),
                    ("95% FA (µm):", "p95_fa"),
                    ("Div X (mrad):", "divergence_x"),
                    ("Div Y (mrad):", "divergence_y"),
                    ("Beam angle (deg):", "beam_angle_deg"),
                  #  ("Rotate laser (deg):", "rotate_laser_deg"),
                    ("Peak Int.:", "peak_intensity"),
                    ("Total Int.:", "total_intensity"),
                    ("Final Exposure (ms):", "final_exposure_ms"),
                    ("Final Gain (dB):", "final_gain_db"),
                    ("Ellipticity (e2x/e2y):", "ellipticity"),
                ]
                highlighted_metrics = {
                    "centroid_x",
                    "centroid_y",
                    "divergence_x",
                    "divergence_y",
                    "beam_angle_deg",
                }

                row = 0
                for label_text, key in metrics:
                    label = QLabel(label_text)
                    label.setFont(QFont("Arial", 9))
                    value_label = QLabel("--")
                    if key in highlighted_metrics:
                        label.setStyleSheet(
                            "color: #102a43; font-weight: bold; "
                            "background-color: #e8f1ff; border: 1px solid #b7d2ff; padding: 2px 6px;"
                        )
                        value_label.setStyleSheet(
                            "color: #0b5ed7; font-weight: bold; "
                            "background-color: #eef5ff; border: 1px solid #b7d2ff; padding: 2px 6px;"
                        )
                    else:
                        value_label.setStyleSheet("color: #0066cc; font-weight: bold;")
                    self.beam_details[key] = value_label

                    layout.addWidget(label, row, 0)
                    layout.addWidget(value_label, row, 1)
                    row += 1

                layout.addItem(QSpacerItem(20, 40, QSizePolicy.Minimum, QSizePolicy.Expanding), row, 0, 1, 2)
                return widget

            def create_intensity_tab(self):
                """Create intensity profile tab."""
                widget = QWidget()
                layout = QVBoxLayout(widget)

                self.intensity_figure = Figure(figsize=(4, 5), dpi=80)
                self.intensity_canvas = FigureCanvas(self.intensity_figure)

                self.intensity_figure.clear()
                self.ax_x = self.intensity_figure.add_subplot(211)
                self.ax_y = self.intensity_figure.add_subplot(212)

            #    self.ax_x.set_title('X Profile (SAC)', fontsize=10, fontweight='bold')
             #   self.ax_x.set_ylabel('Intensity', fontsize=9)
                self.ax_x.grid(True, alpha=0.3)

                #self.ax_y.set_title('Y Profile (FAC)', fontsize=10, fontweight='bold')
              #  self.ax_y.set_xlabel('Position (pixels)', fontsize=9)
               # self.ax_y.set_ylabel('Intensity', fontsize=9)
                self.ax_y.grid(True, alpha=0.3)

                self.ax_x.text(0.5, 0.5, 'Waiting for data...', ha='center', va='center', 
                              transform=self.ax_x.transAxes, fontsize=10, color='gray')
                self.ax_y.text(0.5, 0.5, 'Waiting for data...', ha='center', va='center', 
                              transform=self.ax_y.transAxes, fontsize=10, color='gray')

                self.intensity_figure.tight_layout()
                layout.addWidget(self.intensity_canvas)

                return widget


            def create_zoomed_beam_tab(self):
                """Bottom-right panel: show zoomed beam image around centroid (LabVIEW-like)."""
                widget = QWidget()
                layout = QVBoxLayout(widget)
                layout.setContentsMargins(4, 4, 4, 4)
                layout.setSpacing(4)

                title = QLabel("Zoomed Beam (around centroid)")
                title.setAlignment(Qt.AlignHCenter)
                title.setStyleSheet("font-weight: bold;")
                layout.addWidget(title)

                # Matplotlib canvas (single axes + colorbar)
                self.zoom_figure = Figure(figsize=(4.2, 3.2), dpi=90)
                self.zoom_canvas = FigureCanvas(self.zoom_figure)
                self.zoom_figure.clear()

                self.ax_zoom_img = self.zoom_figure.add_subplot(111)
             #   self.ax_zoom_img.set_xlabel("X (px)")
              #  self.ax_zoom_img.set_ylabel("Y (px)")
                self.ax_zoom_img.grid(False)

                # Placeholder message
                self.ax_zoom_img.text(
                    0.5, 0.5, "Waiting for data.",
                    ha="center", va="center",
                    transform=self.ax_zoom_img.transAxes,
                    fontsize=10, color="gray"
                )

                self._zoom_im = None
                self._zoom_cbar = None

                self.zoom_figure.tight_layout()
                layout.addWidget(self.zoom_canvas, 1)

                return widget

            def _build_beam_display_rgb(self, img):
                """Build the exact RGB image used by the main beam-image panel."""
                if img is None:
                    return None

                if img.ndim == 2:
                    gray = img
                    if gray.dtype != np.uint8:
                        gmax = float(np.max(gray)) if np.size(gray) else 0.0
                        if gmax > 0:
                            gray = (np.clip(gray, 0, gmax) / gmax * 255.0).astype(np.uint8)
                        else:
                            gray = np.zeros_like(gray, dtype=np.uint8)
                    return to_falsecolor_rgb_fixed(gray)

                if img.ndim == 3 and img.shape[2] >= 3:
                    x3 = img[:, :, :3]
                    try:
                        rgb = cv2.cvtColor(x3, cv2.COLOR_BGR2RGB)
                    except Exception:
                        rgb = x3
                    if rgb.dtype != np.uint8:
                        mx = float(np.max(rgb)) if rgb.size else 0.0
                        if mx <= 0:
                            rgb = np.zeros_like(rgb, dtype=np.uint8)
                        elif mx > 255.0:
                            rgb = (np.clip(rgb, 0, mx) / mx * 255.0).astype(np.uint8)
                        else:
                            rgb = np.clip(rgb, 0, 255).astype(np.uint8)
                    if np.array_equal(img[:, :, 0], img[:, :, 1]) and np.array_equal(img[:, :, 1], img[:, :, 2]):
                        return to_falsecolor_rgb_fixed(img)
                    return rgb

                return None

            def update_zoomed_beam(self, centroid_x: float, centroid_y: float, radius_px: float = None):
                """Update zoomed-beam panel around centroid."""
                try:
                    rgb = getattr(self, "_last_beam_display_rgb", None)
                    if rgb is None:
                        return
            
                    h, w = rgb.shape[:2]
                    centroid_x = w/2 - centroid_x
                    centroid_y = h/2 - centroid_y
                    cx = int(round(float(centroid_x))) if centroid_x is not None else w // 2
                    cy = int(round(float(centroid_y))) if centroid_y is not None else h // 2
             
                    # radius default
                    if radius_px is None:
                        radius_px = int(getattr(self, "_last_zoom_radius_px", 80) or 80)
                    radius_px = int(max(10, radius_px))
            
                    x1 = max(cx - radius_px, 0)
                    x2 = min(cx + radius_px, w)
                    y1 = max(cy - radius_px, 0)
                    y2 = min(cy + radius_px, h)
            
                    crop = rgb[y1:y2, x1:x2]
                    if crop.size == 0:
                        return
            
                    # ---- draw ----
                    self.ax_zoom_img.clear()
                 #   self.ax_zoom_img.set_xlabel("X (px)")
                  #  self.ax_zoom_img.set_ylabel("Y (px)")
                    self.ax_zoom_img.grid(False)
            
                    self._zoom_im = self.ax_zoom_img.imshow(
                        crop,
                        interpolation="nearest",
                        origin="upper",
                        aspect="equal",
                        resample=False
                    )
                    ch, cw = crop.shape[:2]
                    self.ax_zoom_img.set_xlim(-0.5, cw - 0.5)
                    self.ax_zoom_img.set_ylim(ch - 0.5, -0.5)
                    self.ax_zoom_img.set_aspect("equal", adjustable="box")
                    self.ax_zoom_img.set_anchor("C")
                    try:
                        self.ax_zoom_img.set_box_aspect(ch / max(cw, 1))
                    except Exception:
                        pass
                    self.zoom_canvas.draw_idle()
            
                except Exception as e:
                    # Don’t fail silently while debugging this feature
                    try:
                        self.ax_zoom_img.clear()
                        self.ax_zoom_img.text(0.5, 0.5, f"Zoom error:\n{e}", ha="center", va="center", transform=self.ax_zoom_img.transAxes)
                        self.zoom_canvas.draw_idle()
                    except Exception:
                        pass

            def create_logging_tab(self):
                """Create logging tab."""
                widget = QWidget()
                layout = QVBoxLayout(widget)

                layout.addWidget(QLabel("Data Log:"))
                self.log_display = QTextEdit()
                self.log_display.setReadOnly(True)
                layout.addWidget(self.log_display)

                layout.addSpacing(10)
                layout.addWidget(QLabel("Export:"))

                csv_btn = QPushButton("Export to CSV")
                csv_btn.clicked.connect(self.export_csv)
                layout.addWidget(csv_btn)

                json_btn = QPushButton("Export to JSON")
                json_btn.clicked.connect(self.export_json)
                layout.addWidget(json_btn)

                layout.addStretch()
                return widget

            def setup_styles(self):
                """Setup stylesheet."""
                self.setStyleSheet("""
                    QMainWindow { background-color: #f0f0f0; }
                    QGroupBox { font-weight: bold; border: 2px solid #cccccc; border-radius: 5px; 
                               margin-top: 10px; padding-top: 10px; }
                    QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 3px 0 3px; }
                    QPushButton { background-color: #e0e0e0; border: 1px solid #999; border-radius: 3px; 
                                 padding: 5px; font-weight: bold; }
                    QPushButton:hover { background-color: #d0d0d0; }
                    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox { border: 1px solid #999; 
                                                                     border-radius: 3px; padding: 3px; }
                """)

            def browse_image(self):
                """Browse for image file."""
                path, _ = QFileDialog.getOpenFileName(self, "Select Image", "", "Image Files (*.png *.jpg *.bmp *.tiff)")
                if path:
                    self.image_path_input.setText(path)
                    self.load_image(path)

            def browse_path(self):
                """Browse for output directory."""
                path = QFileDialog.getExistingDirectory(self, "Select Output Directory")
                if path:
                    self.path_input.setText(path)

            # -----------------------------
            # Camera / Simulation integration
            # -----------------------------
            def set_camera(self, camera_obj):
                """Attach an external camera object (BaslerCamera) from the main script.

                Do not auto-start live preview here. The main beam panel must stay empty at startup
                until the user intentionally begins acquisition / preview.
                """

                self.external_camera = camera_obj
                try:
                    if hasattr(self, 'camera_source_combo') and self.camera_source_combo.currentText().startswith("External"):
                        self.active_camera = self.external_camera
                except Exception:
                    pass

            def set_simulation_image(self, image_path: str):
                """Load a simulation image path (called from main when --simulate is provided)."""
                if hasattr(self, 'mode_combo'):
                    self.mode_combo.setCurrentIndex(0)  # Simulation
                self.image_path_input.setText(image_path)
                self.load_image(image_path)

            def on_mode_changed(self, idx: int):
                """Switch between simulation and live camera."""
                live = self.mode_combo.currentText().startswith("Live")

                # Enable/disable simulation controls
                self.image_path_input.setEnabled(not live)
                if hasattr(self, 'browse_btn'):
                    self.browse_btn.setEnabled(not live)

                # Enable/disable live camera controls
                if hasattr(self, 'camera_source_combo'):
                    self.camera_source_combo.setEnabled(live)
                if hasattr(self, 'cam_index_spin'):
                    self.cam_index_spin.setEnabled(live and self.camera_source_combo.currentText().startswith("OpenCV"))

                if live:
                    # Choose active camera based on selection
                    if hasattr(self, 'camera_source_combo'):
                        self.on_camera_source_changed(self.camera_source_combo.currentIndex())
                    if self.active_camera is None:
                        QMessageBox.information(self, "Live Camera", "No camera available for the selected source.")
                        return
                    self.start_camera_preview()
                else:
                    self.stop_camera_preview()

            def start_camera_preview(self):
                """Open the camera (if needed) and start periodic grabbing."""
                if self.active_camera is None:
                    return

                # Open camera if possible and not already open
                try:
                    is_open = getattr(self.active_camera, "is_open", None)
                    already = bool(is_open()) if callable(is_open) else False
                    if not already and hasattr(self.active_camera, "open"):
                        self.active_camera.open()
                except Exception as e:
                    self.set_status(f"Camera open failed: {e}", "error")
                    return

                # Best-effort exposure set from UI
                try:
                    exp_us = float(self.exposure_ms_spin.value()) * 1000.0
                    if hasattr(self.active_camera, "set_exposure_us"):
                        self.active_camera.set_exposure_us(exp_us)
                except Exception:
                    pass

                self._live_view_active = True

                if not self.camera_timer.isActive():
                    self.camera_timer.start(int(self.camera_interval_ms))

                # Draw one frame immediately
                try:
                    self.update_camera_frame()
                except Exception:
                    pass
            def stop_camera_preview(self):
                """Stop periodic grabbing and release OpenCV camera if used."""
                self._live_view_active = False
                if self.camera_timer.isActive():
                    self.camera_timer.stop()

                # Clear the main beam panel so startup / stopped state remains an empty box.
                self.current_image = None
                self._show_empty_beam_placeholder()

                # If OpenCV camera is active, release it so other apps can use the webcam
                try:
                    if isinstance(self.active_camera, OpenCVCameraWrapper):
                        self.active_camera.close()
                except Exception:
                    pass
            def _update_live_view(self):
                """Qt timer callback (alias)."""
                self.update_camera_frame()

            def update_camera_frame(self):
                """Grab one frame from the camera and display it."""
                if self.active_camera is None:
                    return
                try:
                    frame = self.active_camera.grab(timeout_ms=2000)
                except TypeError:
                    # Some grab() signatures might not accept timeout_ms
                    try:
                        frame = self.active_camera.grab()
                    except Exception:
                        return
                except Exception:
                    return

                if frame is None:
                    return

                # Store raw frame for analysis                
                self.current_image = frame
                if bool(getattr(self, "_analysis_busy", False)):
                    return
                self.display_image_array(frame)
            def _reposition_sat_indicator(self):
                """Place SAT indicator and %Saturated/value box at a stable lower position."""
                try:
                    if not hasattr(self, "ax_fa_profile") or not hasattr(self, "_sat_circle"):
                        return
                    f = self.ax_fa_profile.get_position()
                    x = 0.5 * (f.x0 + f.x1)
                    # Fixed anchor so startup and post-analysis locations are identical.
                    y = f.y1 + 0.068  # circle center (nudged up)
                    r = 0.035
                    self._sat_circle.center = (x, y)
                    self._sat_circle.radius = r
                    self._sat_circle_text.set_position((x, y))
                    label_y = y + r + 0.050
                    self._sat_percent_label.set_position((x, label_y))
                    box_y = label_y - 0.01
                    self._sat_value_box.set_position((x, box_y))
                except Exception:
                    return

            def _ensure_sat_value_box_placeholder(self):
                """Show saturation value box as an empty gray box before analysis."""
                try:
                    if not hasattr(self, "_sat_value_box"):
                        return
                    self._sat_value_box.set_visible(True)
                    # Keep box visible with visually-empty content but fixed width.
                    self._sat_value_box.set_text("0.00 %")
                    self._sat_value_box.set_color("#b0b0b0")
                    self._sat_value_box.set_bbox(
                        dict(
                            boxstyle="round,pad=0.35",
                            facecolor="#b0b0b0",
                            edgecolor="#888",
                            alpha=0.95,
                        )
                    )
                except Exception:
                    pass

            
            def _show_empty_beam_placeholder(self):
                """Show an empty beam-image box at startup / when preview is stopped.

                This keeps the beam panel visible and at the same size, but with no image displayed.
                """
                try:
                    self.ax_beam.set_facecolor('black')
                    self.ax_beam.set_xticks([])
                    self.ax_beam.set_yticks([])
                    self.ax_beam.set_frame_on(True)
                    for spine in self.ax_beam.spines.values():
                        spine.set_edgecolor('black')
                        spine.set_linewidth(2)
                        spine.set_visible(True)

                    # Remove any previously displayed image / overlays.
                    if hasattr(self, '_center_lines'):
                        for line in self._center_lines:
                            try:
                                line.remove()
                            except Exception:
                                pass
                        self._center_lines = []

                    self._ensure_beam_colorbar_placeholder()

                    # Apply same geometry policy as the real beam-image draw path.
                    # Use a live-frame-derived shape when possible so startup layout matches laser-on layout.
                    h, w = self._get_beam_shape_for_layout()
                    try:
                        h = int(max(1, h))
                        w = int(max(1, w))
                        self.ax_beam.set_xlim(-0.5, w - 0.5)
                        self.ax_beam.set_ylim(h - 0.5, -0.5)
                        self.ax_beam.set_aspect('equal', adjustable='box')
                        self.ax_beam.set_anchor("C")
                        with contextlib.suppress(Exception):
                            self.ax_beam.set_box_aspect(h / max(w, 1))
                        # If we already have a real plotted beam rectangle, force exact same size.
                        pos = getattr(self, "_last_beam_axes_position", None)
                        if pos is not None:
                            self.ax_beam.set_position(pos)
                    except Exception:
                        pass

                    blank_rgb = np.zeros((h, w, 3), dtype=np.uint8)
                    self._last_beam_display_rgb = blank_rgb.copy()
                    if self._beam_im is None:
                        self._beam_im = self.ax_beam.imshow(
                            blank_rgb,
                            aspect='equal',
                            interpolation='nearest',
                            origin='upper',
                            resample=False,
                        )
                    else:
                        self._beam_im.set_data(blank_rgb)
                        self._beam_im.set_visible(True)

                    self._restore_fixed_axes_positions()
                    self._apply_empty_plot_layout()
                    self._ensure_sat_value_box_placeholder()
                    self._reposition_sat_indicator()
                    self._queue_beam_canvas_draw()
                except Exception:
                    pass

            def _get_beam_shape_for_layout(self):
                """Best-effort beam image shape used only for stable layout/aspect before plotting."""
                # 1) Most recent displayed beam frame shape (preferred).
                shp = getattr(self, "_last_beam_shape", None)
                if isinstance(shp, tuple) and len(shp) == 2:
                    try:
                        return int(shp[0]), int(shp[1])
                    except Exception:
                        pass

                # 2) Current cached live frame shape, if any.
                try:
                    if getattr(self, "current_image", None) is not None:
                        hh, ww = self.current_image.shape[:2]
                        return int(hh), int(ww)
                except Exception:
                    pass

                # 3) One non-displayed probe grab from active camera (does not alter UI image content).
                try:
                    cam = getattr(self, "active_camera", None)
                    if cam is not None and hasattr(cam, "grab"):
                        with contextlib.suppress(TypeError):
                            frm = cam.grab(timeout_ms=150)
                            if frm is not None:
                                hh, ww = frm.shape[:2]
                                self._last_beam_shape = (int(hh), int(ww))
                                return int(hh), int(ww)
                        with contextlib.suppress(Exception):
                            frm = cam.grab()
                            if frm is not None:
                                hh, ww = frm.shape[:2]
                                self._last_beam_shape = (int(hh), int(ww))
                                return int(hh), int(ww)
                except Exception:
                    pass

                # 4) Live-camera-like fallback (matches typical Basler frame ratio better than 480x640).
                return (1080, 1920)

            def display_image_array(self, img):
                """Display the *single-frame* beam image in the GUI using the raw RGB frame.

                Notes:
                  - This display is NOT averaged. Averaging is only for analysis/metrics.
                  - We convert OpenCV-style BGR -> RGB for correct colors.
                  - We keep the displayed image "as-is" (no colormap / no background masking).
                """
                # img -> img_rgb (uint8, RGB) for display
                if img is None:
                    return
                
                img_rgb = self._build_beam_display_rgb(img)
                if img_rgb is None:
                    return
                self._last_beam_display_rgb = np.array(img_rgb, copy=True)
                

                # --- Intensity colorbar (based on grayscale intensity) ---
                if getattr(img, "ndim", 0) == 3 and img.shape[2] >= 3:
                    try:
                        gray = cv2.cvtColor(img[:, :, :3], cv2.COLOR_BGR2GRAY)
                    except Exception:
                        gray = cv2.cvtColor(img[:, :, :3], cv2.COLOR_RGB2GRAY)
                else:
                    gray = img
                if gray is not None and gray.dtype != np.uint8:
                    gmax = float(np.max(gray)) if np.size(gray) else 0.0
                    if gmax > 0:
                        gray_disp = (np.clip(gray, 0, gmax) / gmax * 255.0).astype(np.uint8)
                    else:
                        gray_disp = np.zeros_like(gray, dtype=np.uint8)
                else:
                    gray_disp = gray

                # Draw beam image without recreating the axis, so the layout never jumps.
                self.ax_beam.axis('off')
                for spine in self.ax_beam.spines.values():
                    spine.set_edgecolor('black')
                    spine.set_linewidth(2)
                    spine.set_visible(True)

                if self._beam_im is None:
                    self._beam_im = self.ax_beam.imshow(
                        img_rgb,
                        aspect='equal',
                        interpolation='nearest',
                        origin='upper',
                        resample=False
                    )
                else:
                    self._beam_im.set_data(img_rgb)
                    self._beam_im.set_visible(True)
                # Force full native-frame view (no cropping / no pixel-count changes).
                # Any size change is only visual scaling of the same pixel grid.
                try:
                    hh, ww = img_rgb.shape[:2]
                    self._last_beam_shape = (int(hh), int(ww))
                    self.ax_beam.set_xlim(-0.5, ww - 0.5)
                    self.ax_beam.set_ylim(hh - 0.5, -0.5)
                    self.ax_beam.set_aspect('equal', adjustable='box')
                    self.ax_beam.set_anchor("C")
                    try:
                        self.ax_beam.set_box_aspect(hh / max(ww, 1))
                    except Exception:
                        pass
                except Exception:
                    pass

                # Keep panel geometry fixed between startup and analysis.
                self._restore_fixed_axes_positions()
                self._reposition_sat_indicator()

                # Update (or create) the intensity bar as a standard colormap colorbar from grayscale
                self._ensure_beam_colorbar_placeholder()
                # ---- Add center crosshair lines (yellow) ----
                h, w = img_rgb.shape[:2]
                cx = w / 2
                cy = h / 2
                
                # Remove previous crosshair lines if they exist
                if hasattr(self, "_center_lines"):
                    for line in self._center_lines:
                        try:
                            line.remove()
                        except Exception:
                            pass
                
                # Draw new lines
                vline = self.ax_beam.axvline(cx, color='yellow', linewidth=2)
                hline = self.ax_beam.axhline(cy, color='yellow', linewidth=2)
                
                # Store references so they can be removed next frame
                self._center_lines = [vline, hline]

                self._queue_beam_canvas_draw()

            # -----------------------------
            # Secondary Cameras (Cam2/Cam3)
            # -----------------------------
            def open_secondary_cameras_window(self):
                """Open (or raise) the pop-off window for Camera 2 and Camera 3."""
                try:
                    if self.cam23_window is None:
                        self.cam23_window = SecondaryCamerasWindow(parent=None)
                    self.cam23_window.show()
                    self.cam23_window.raise_()
                    self.cam23_window.activateWindow()
                except Exception as e:
                    self.log_status(f"Failed to open Cam2/Cam3 window: {e}", "ERROR")
                    return
                # Start/refresh capture based on current settings
                self._ensure_secondary_cameras_started()

            def _on_secondary_cam_settings_changed(self, *args):
                # Called on any rotation/exposure/index/enable toggle change
                self._ensure_secondary_cameras_started()

            def _ensure_secondary_cameras_started(self):
                """Start/stop Cam2/Cam3 USB capture depending on UI toggles.

                Station build assumption:
                  - Cam2 and Cam3 are fixed USB/UVC cameras (OpenCV).
                  - No Basler selection for Cam2/Cam3.
                """
                # If the window isn't open, do nothing (keeps resources free)
                if self.cam23_window is None or not self.cam23_window.isVisible():
                    try:
                        if hasattr(self, "cam23_timer") and self.cam23_timer.isActive():
                            self.cam23_timer.stop()
                    except Exception:
                        pass
                    self._close_secondary_cameras()
                    return

                try:
                    # Cam2/Cam3 always enabled while the Cam2/Cam3 window is visible.
                    enable2 = True
                    enable3 = True

                    # Fixed USB indices (Cam2=0, Cam3=1). If you ever need to change,
                    # edit these two values only.
                    idx2 = int(getattr(self, "_usb_cam2_index", 0))
                    idx3 = int(getattr(self, "_usb_cam3_index", 1))

                    # Cam2
                    if enable2:
                        if self.cam2_camera is None or not isinstance(self.cam2_camera, OpenCVCameraWrapper) or getattr(self.cam2_camera, "index", None) != idx2:
                            try:
                                if self.cam2_camera is not None:
                                    self.cam2_camera.close()
                            except Exception:
                                pass
                            self.cam2_camera = OpenCVCameraWrapper(index=idx2)
                            try:
                                self.cam2_camera.open()
                            except Exception as e:
                                self.log_status(f"Cam2 open failed (idx={idx2}): {e}", "ERROR")
                                self.cam2_camera = None
                    else:
                        try:
                            if self.cam2_camera is not None:
                                self.cam2_camera.close()
                        except Exception:
                            pass
                        self.cam2_camera = None

                    # Cam3
                    if enable3:
                        if self.cam3_camera is None or not isinstance(self.cam3_camera, OpenCVCameraWrapper) or getattr(self.cam3_camera, "index", None) != idx3:
                            try:
                                if self.cam3_camera is not None:
                                    self.cam3_camera.close()
                            except Exception:
                                pass
                            self.cam3_camera = OpenCVCameraWrapper(index=idx3)
                            try:
                                self.cam3_camera.open()
                            except Exception as e:
                                self.log_status(f"Cam3 open failed (idx={idx3}): {e}", "ERROR")
                                self.cam3_camera = None
                    else:
                        try:
                            if self.cam3_camera is not None:
                                self.cam3_camera.close()
                        except Exception:
                            pass
                        self.cam3_camera = None

                    # Timer
                    if (enable2 or enable3):
                        if not self.cam23_timer.isActive():
                            self.cam23_timer.start(int(getattr(self, "cam23_interval_ms", 60)))
                    else:
                        if self.cam23_timer.isActive():
                            self.cam23_timer.stop()

                except Exception as e:
                    self.log_status(f"Secondary camera start logic failed: {e}", "ERROR")


            def _close_secondary_cameras(self):
                try:
                    if self.cam2_camera is not None and hasattr(self.cam2_camera, "close"):
                        self.cam2_camera.close()
                except Exception:
                    pass
                try:
                    if self.cam3_camera is not None and self.cam3_camera is not self.cam2_camera and hasattr(self.cam3_camera, "close"):
                        self.cam3_camera.close()
                except Exception:
                    pass
                self.cam2_camera = None
                self.cam3_camera = None

            
            def update_secondary_cameras(self):
                """Grab frames from Cam2/Cam3, apply rotation, and push to the pop-off window.

                IMPORTANT:
                  - We send **full-resolution** pixmaps to the pop-off window.
                  - The pop-off window handles zoom/pan (including synchronized zoom).
                  - We do NOT rescale here, so zoom has real detail.
                """
                if self.cam23_window is None or not self.cam23_window.isVisible():
                    return

                def _frame_to_qpixmap_full(frame_bgr) -> QPixmap | None:
                    try:
                        if frame_bgr is None:
                            return None
                        if getattr(frame_bgr, "ndim", 0) == 2:
                            # grayscale -> RGB
                            rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_GRAY2RGB)
                        elif getattr(frame_bgr, "ndim", 0) == 3 and frame_bgr.shape[2] >= 3:
                            rgb = cv2.cvtColor(frame_bgr[:, :, :3], cv2.COLOR_BGR2RGB)
                        else:
                            return None

                        h, w = rgb.shape[:2]
                        qimg = QImage(rgb.data, w, h, int(rgb.strides[0]), QImage.Format_RGB888)
                        # copy() is critical: otherwise it can reference freed numpy memory
                        return QPixmap.fromImage(qimg.copy())
                    except Exception:
                        return None

                # Cam2
                pm2 = None
                try:
                    if self.cam2_camera is not None:
                        frame2 = self.cam2_camera.grab(timeout_ms=500)
                        if frame2 is not None:
                            rot2 = int(self.cam2_rotation_spin.value()) if hasattr(self, "cam2_rotation_spin") else 0
                            frame2 = self._apply_rotation(frame2, rot2)
                            pm2 = _frame_to_qpixmap_full(frame2)
                except Exception as e:
                    self.log_status(f"Cam2 grab error: {e}", "ERROR")
                try:
                    self.cam23_window.set_cam2_pixmap(pm2)
                except Exception:
                    pass

                # Cam3
                pm3 = None
                try:
                    if self.cam3_camera is not None:
                        frame3 = self.cam3_camera.grab(timeout_ms=500)
                        if frame3 is not None:
                            rot3 = int(self.cam3_rotation_spin.value()) if hasattr(self, "cam3_rotation_spin") else 0
                            frame3 = self._apply_rotation(frame3, rot3)
                            pm3 = _frame_to_qpixmap_full(frame3)
                except Exception as e:
                    self.log_status(f"Cam3 grab error: {e}", "ERROR")
                try:
                    self.cam23_window.set_cam3_pixmap(pm3)
                except Exception:
                    pass

            def _apply_rotation(self, frame_bgr, deg: int):
                            """Rotate an OpenCV BGR frame by deg degrees (supports 0/90/180/270 and arbitrary)."""
                            if frame_bgr is None:
                                return None
                            d = int(deg) % 360
                            if d == 0:
                                return frame_bgr
                            if d == 90:
                                return cv2.rotate(frame_bgr, cv2.ROTATE_90_CLOCKWISE)
                            if d == 180:
                                return cv2.rotate(frame_bgr, cv2.ROTATE_180)
                            if d == 270:
                                return cv2.rotate(frame_bgr, cv2.ROTATE_90_COUNTERCLOCKWISE)
                            # Arbitrary rotation around center (may crop)
                            h, w = frame_bgr.shape[:2]
                            M = cv2.getRotationMatrix2D((w / 2.0, h / 2.0), d, 1.0)
                            return cv2.warpAffine(frame_bgr, M, (w, h))

            def _frame_to_pixmap(self, frame_bgr, max_w: int = 420, max_h: int = 320) -> QPixmap | None:
                if frame_bgr is None:
                    return None
                try:
                    rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
                    h, w = rgb.shape[:2]
                    qimg = QImage(rgb.data, w, h, 3 * w, QImage.Format_RGB888)
                    pm = QPixmap.fromImage(qimg)
                    return pm.scaled(max_w, max_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                except Exception:
                    return None



            def closeEvent(self, event):
                """Ensure timers/camera/laser resources are released when the GUI closes."""
                # Stop PER UI first without emitting another abort request.
                with contextlib.suppress(Exception):
                    if getattr(self, "per_tab", None) is not None and hasattr(self.per_tab, "stop_per"):
                        self.per_tab.stop_per(False)

                # Motor first: abort sweep and stop any ongoing rotation immediately.
                with contextlib.suppress(Exception):
                    mp = getattr(self, "motor_panel", None)
                    if mp is not None:
                        if hasattr(mp, "abort_sweep"):
                            mp.abort_sweep()
                        if hasattr(mp, "backend") and getattr(mp, "backend", None) is not None:
                            with contextlib.suppress(Exception):
                                mp.backend.stop_motion()

                # Cameras / windows
                with contextlib.suppress(Exception):
                    self.stop_camera_preview()
                with contextlib.suppress(Exception):
                    if self.active_camera is not None and hasattr(self.active_camera, "close"):
                        self.active_camera.close()
                with contextlib.suppress(Exception):
                    if self.opencv_camera is not None and hasattr(self.opencv_camera, "close"):
                        self.opencv_camera.close()
                with contextlib.suppress(Exception):
                    if self.external_camera is not None and hasattr(self.external_camera, "close"):
                        self.external_camera.close()
                with contextlib.suppress(Exception):
                    if hasattr(self, 'cam23_timer') and self.cam23_timer.isActive():
                        self.cam23_timer.stop()
                with contextlib.suppress(Exception):
                    self._close_secondary_cameras()
                with contextlib.suppress(Exception):
                    if getattr(self, "cam23_window", None) is not None:
                        self.cam23_window.close()
                        self.cam23_window = None
                with contextlib.suppress(Exception):
                    if getattr(self, "m2_widget", None) is not None:
                        self.m2_widget.close()

                # Laser/TEC (critical: release COM ports so you don't need to power-cycle daily)
                with contextlib.suppress(Exception):
                    self._force_laser_off_for_shutdown()
                with contextlib.suppress(Exception):
                    self.laser_off()
                with contextlib.suppress(Exception):
                    if getattr(self, "is_connected", False) or (
                        hasattr(self, "arroyo") and self.arroyo and getattr(self.arroyo, "is_connected", False)
                    ):
                        self.disconnect_arroyo()
                with contextlib.suppress(Exception):
                    mp = getattr(self, "motor_panel", None)
                    if mp is not None:
                        if hasattr(mp, "abort_sweep"):
                            mp.abort_sweep()
                        if hasattr(mp, "disconnect_motor"):
                            mp.disconnect_motor()

                super().closeEvent(event)


            def load_image(self, image_path: str):
                """Load and display image in matplotlib figure."""
                try:
                    image = cv2.imread(image_path, cv2.IMREAD_COLOR)
                    if image is None:
                        raise ValueError("Could not load image")
                    # Keep raw BGR for analysis, but display as RGB
                    self.current_image = image
                    image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

                    # Clear all axes except beam image
                    self.ax_beam.clear()
                    self.ax_sa_profile.clear()
                    self.ax_fa_profile.clear()
                    self.ax_sa_zoom.clear()
                    self.ax_fa_zoom.clear()
                    self._beam_im = None

                    self.display_image_array(image)
                    self.beam_canvas.draw()
                    self.ax_fa_zoom.grid(True, alpha=0.3)

                    self._restore_fixed_axes_positions()
                    self.beam_canvas.draw()

                    self.set_status(f"Image loaded: {Path(image_path).name}", "info")

                except Exception as e:
                    self.set_status(f"Error loading image: {e}", "error")                    

                    #display_image_array(image_rgb)
                 #   self.ax_fa_zoom.grid(True, alpha=0.3)

                #    self.beam_figure.tight_layout()
                  #  self.beam_canvas.draw()

                  #  self.set_status(f"Image loaded: {Path(image_path).name}", "info")

                except Exception as e:
                    self.set_status(f"Error loading image: {e}", "error")

            def toggle_auto_analyze(self, state: int):
                """Enable/disable continuous analysis (GUI-safe replacement for a while True loop)."""
                enabled = bool(state)
                self._auto_analyze_enabled = enabled
                if enabled:
                    period = int(self.auto_analyze_period.value()) if hasattr(self, "auto_analyze_period") else 250
                    # Start timer; analysis runs on the *latest* frame already captured by the live preview.
                    if not self.auto_analyze_timer.isActive():
                        self.auto_analyze_timer.start(period)
                    self.set_status(f"Auto Analyze ON ({period} ms)", "info")
                else:
                    if self.auto_analyze_timer.isActive():
                        self.auto_analyze_timer.stop()
                    self.set_status("Auto Analyze OFF", "info")

            def _auto_analyze_period_changed(self, value: int):
                """Update timer interval while running."""
                if hasattr(self, "auto_analyze_timer") and self.auto_analyze_timer.isActive():
                    self.auto_analyze_timer.setInterval(int(value))

            def _auto_analyze_tick(self):
                """Timer callback: trigger one analysis pass if we have a live frame."""
                if not getattr(self, "_auto_analyze_enabled", False):
                    return
                # Avoid overlapping analyses
                if getattr(self, "_analysis_busy", False):
                    return
                # Only meaningful in Live mode
                live = hasattr(self, 'mode_combo') and self.mode_combo.currentText().startswith("Live")
                if not live:
                    return
                if self.current_image is None:
                    return
                self._analysis_busy = True
                try:
                    self.start_analysis()
                except Exception:
                    # If something goes wrong, don't wedge the timer
                    self._analysis_busy = False
                    raise
            def _continue_start_analysis(self):
            
                # Update config from GUI
                if not self.config:
                    self.config = Config()
            
                self.config.camera.exposure_us = float(self.exposure_ms_spin.value()) * 1000.0
            
                try:
                    if hasattr(self, "btn_enable_auto_exposure") and hasattr(self.config, "auto_exposure"):
                        self.config.auto_exposure.enabled = bool(self.btn_enable_auto_exposure.isChecked())
                except Exception:
                    pass
            
                # Show initial values
                self.show_initial_metrics()
            
                self.set_status("Analyzing...", "info")
            
                # Call analysis callback
                if hasattr(self, 'on_analyze_clicked') and callable(getattr(self, 'on_analyze_clicked')):
                    self.on_analyze_clicked(self.current_image, self.config, self.image_path_input.text())
                else:
                    self.set_status("Error: Analysis callback not configured", "error")
                    self.analyze_btn.setEnabled(True)
            
            
            def _qt_delay_ms(self, ms: int) -> None:
                """Delay without freezing UI (processes Qt events)."""
                loop = QEventLoop()
                QTimer.singleShot(ms, loop.quit)
                loop.exec_()
    
            def start_analysis(self):
                """Start analysis - triggers analysis from main code."""
                self._analysis_stop_requested = False
                self._run_loop_active = True
                live = hasattr(self, 'mode_combo') and self.mode_combo.currentText().startswith("Live")
                if live:
                    if self.current_image is None:
                        try:
                            self.update_camera_frame()
                        except Exception:
                            pass
                        with contextlib.suppress(Exception):
                            QApplication.processEvents()
                    if self.current_image is None:
                        QMessageBox.warning(self, "Error", "No live frame available yet. Wait for the preview to show an image.")
                        return
                else:
                    if not self.image_path_input.text():
                        QMessageBox.warning(self, "Error", "Please select an image file first")
                        return
                # UI feedback
                self.set_status("Waiting 2 seconds before configuring...", "info")
                self.progress_bar.setVisible(True)
                self.analyze_btn.setEnabled(False)
            
                # ✅ REAL delay that still lets Qt process events
                self._qt_delay_ms(2000)

                # Update config from GUI
                if not self.config:
                    # from basler_analysis_labview_output_layout_v2_updated import Config
                    self.config = Config()

                self.config.camera.exposure_us = float(self.exposure_ms_spin.value()) * 1000.0
              # self.config.camera.rotate_deg = float(self.rotation_input.value())
                #self.config.analysis.wavelength_nm = float(self.wavelength_input.value())
            #    self.config.output.out_dir = self.path_input.text()


                try:
                    if hasattr(self, "btn_enable_auto_exposure") and hasattr(self.config, "auto_exposure"):
                        self.config.auto_exposure.enabled = bool(self.btn_enable_auto_exposure.isChecked())
                except Exception:
                    pass
                # Show initial values
                self.show_initial_metrics()

                # Start analysis in background
                self.set_status("Analyzing...", "info")
                self.progress_bar.setVisible(True)
                self.analyze_btn.setEnabled(False)
                self._analysis_busy = True

                # Call analysis callback (provided by main code)
                if hasattr(self, 'on_analyze_clicked') and callable(getattr(self, 'on_analyze_clicked')):
                    # Pass the already loaded image and the image name
                    self.on_analyze_clicked(self.current_image, self.config, self.image_path_input.text())
                else:
                    self.set_status("Error: Analysis callback not configured", "error")
                    self._analysis_busy = False
                    self.analyze_btn.setEnabled(True)

            def stop_analysis_only(self):
                """Stop analysis loop only."""
                try:
                    self._analysis_stop_requested = True
                    self._run_loop_active = False
                    self._auto_analyze_enabled = False
                    if hasattr(self, "auto_analyze_timer") and self.auto_analyze_timer.isActive():
                        self.auto_analyze_timer.stop()
                    if hasattr(self, "auto_analyze_cb"):
                        with contextlib.suppress(Exception):
                            self.auto_analyze_cb.blockSignals(True)
                            self.auto_analyze_cb.setChecked(False)
                            self.auto_analyze_cb.blockSignals(False)
                    self.progress_bar.setVisible(False)
                    self.analyze_btn.setEnabled(True)
                    self._analysis_busy = False
                    self.set_status("Analysis stopped.", "info")
                except Exception as e:
                    self.set_status(f"Failed to stop analysis: {e}", "error")

            def show_initial_metrics(self):
                """Show default/initial metric values."""
                for key in self.beam_details:
                    self.beam_details[key].setText("0.00")

            def update_results(self, results_dict: Dict[str, Any]):
                """Update GUI with analysis results - called by main code."""
                if bool(getattr(self, "_analysis_stop_requested", False)):
                    return
                if 'error' in results_dict:
                    self.set_status(f"Error: {results_dict['error']}", "error")
                    return
                try:
                    self.last_results_dict = dict(results_dict)
                except Exception:
                    self.last_results_dict = results_dict
                self._beam_draw_deferred = True
                try:
                    # Update beam metrics
                    for key, label in self.beam_details.items():
                        if key in results_dict:
                            value = results_dict[key]
                            if isinstance(value, float):
                                label.setText(f"{value:.2f}")
                            else:
                                label.setText(str(value))
                    # --- Update saturation indicator ---
                    try:
                        sat = results_dict.get("saturation_percent", None)
                        thr = float(self.sat_thresh_input.value()) if hasattr(self, "sat_thresh_input") else 0.2
                        if hasattr(self, "_sat_value_box"):
                            if sat is not None:
                                sat_f = float(sat)
                                self._sat_value_box.set_color("black")
                                self._sat_value_box.set_text(f"{sat_f:.2f} %")
                            else:
                                self._ensure_sat_value_box_placeholder()
                        if sat is not None and hasattr(self, "_sat_circle"):
                            sat_f = float(sat)
                            good = sat_f <= thr
                            self._sat_circle.set_facecolor("green" if good else "red")
                            self._sat_circle_text.set_text("SAT GOOD" if good else "SAT BAD")
                            self._reposition_sat_indicator()
                    except Exception:
                        pass

                    e2_x = results_dict.get('e2_x', None)
                    e2_y = results_dict.get('e2_y', None)
                    centroid_x = results_dict.get('centroid_x', None)
                    centroid_y = results_dict.get('centroid_y', None)

                    try:
                        rx = None
                        ry = None
                        if e2_x is not None and hasattr(e2_x, "__len__") and len(e2_x) == 2:
                            rx = abs(float(e2_x[1]) - float(e2_x[0])) / 2.0
                        if e2_y is not None and hasattr(e2_y, "__len__") and len(e2_y) == 2:
                            ry = abs(float(e2_y[1]) - float(e2_y[0])) / 2.0
                        r = None
                        if rx is not None and ry is not None:
                            r = max(rx, ry)
                        elif rx is not None:
                            r = rx
                        elif ry is not None:
                            r = ry
                        if r is not None and np.isfinite(r) and r > 0:
                            self._last_zoom_radius_px = float(max(10.0, 1.2 * r))
                    except Exception:
                        pass
                    self.update_zoomed_beam(centroid_x, centroid_y, radius_px=getattr(self, '_last_zoom_radius_px', None))

                    if 'profile_x' in results_dict:
                        self.update_SA_plot(results_dict['profile_x'], e2_x, centroid_x)
                        self.update_SA_zoom_plot(results_dict['profile_x'], e2_x)
                    if 'profile_y' in results_dict:
                        self.update_FA_plot(results_dict['profile_y'], e2_y, centroid_y)
                        self.update_FA_zoom_plot(results_dict['profile_y'], e2_y)

                    if self.enable_logging_cb.isChecked():
                        self.log_result(results_dict)
                finally:
                    self._beam_draw_deferred = False
                    self._queue_beam_canvas_draw(force=True)

            def update_SA_zoom_plot(self, profile_x, e2_x=None):
                """Update the SA zoom plot using zoom_sa, with break lines and colored regions."""
              #  from basler_analysis_labview_output_layout_v2_updated_loop_gui_fixed_rgbdisplay_square_sat_v2_POWER_REQUESTS_PATCHED import zoom_sa
                self.ax_sa_zoom.clear()
                self._style_sa_zoom_axis()
                if profile_x is not None and e2_x is not None and len(e2_x) == 2:
                    try:
                        x = np.arange(len(profile_x))
                        zoom_result = zoom_sa(x=x, y=profile_x, x1=e2_x[0], x2=e2_x[1])
                        # Plot only the zoomed region
                        self.ax_sa_zoom.plot(zoom_result.x_zoom, zoom_result.y_zoom, 'b-', linewidth=2)
                        self.ax_sa_zoom.set_title("SA Zoom (1/e²)", fontweight="normal", fontsize=10)
                      #  self.ax_sa_zoom.set_xlabel("X (pixels)")
                       # self.ax_sa_zoom.set_ylabel("Intensity")
                        # Add break lines and colored regions
                        x1 = zoom_result.x1
                        x2 = zoom_result.x2
                        xmid = zoom_result.xmid
                        # Red: from x1 to xmid
                        self.ax_sa_zoom.axvspan(x1, xmid, color='red', alpha=0.3)
                        # Green: from xmid to x2
                        self.ax_sa_zoom.axvspan(xmid, x2, color='green', alpha=0.3)
                        # Draw the 1/e2 lines
                        self.ax_sa_zoom.axvline(x1, color='red', linestyle='--', linewidth=2)
                        self.ax_sa_zoom.axvline(x2, color='red', linestyle='--', linewidth=2)
                        # Draw midpoint line
                        self.ax_sa_zoom.axvline(xmid, color='black', linestyle=':', linewidth=1)
                    except Exception as e:
                        self.ax_sa_zoom.set_title(f"SA Zoom Error: {e}", fontweight="normal", fontsize=10)
                else:
                    self.ax_sa_zoom.set_title("SA Zoom (1/e²)", fontweight="normal", fontsize=10)
                self.ax_sa_zoom.set_ylim(0.0, 1.05)
                self.ax_sa_zoom.grid(True, alpha=0.3)
                self._apply_profile_zoom_borders_double()
                self._restore_fixed_axes_positions()
                self._queue_beam_canvas_draw()

            def update_FA_zoom_plot(self, profile_y, e2_y=None):
                """Update the FA zoom plot using zoom_sa, with break lines and colored regions."""
             #   from basler_analysis_labview_output_layout_v2_updated_loop_gui_fixed_rgbdisplay_square_sat_v2_POWER_REQUESTS_PATCHED import zoom_sa
                self.ax_fa_zoom.clear()
                self._style_fa_zoom_axis()
                if profile_y is not None and e2_y is not None and len(e2_y) == 2:
                    try:
                        y = np.arange(len(profile_y))
                        zoom_result = zoom_sa(x=y, y=profile_y, x1=e2_y[0], x2=e2_y[1])
                        # Plot only the zoomed region, intensity on x-axis, position on y-axis
                        self.ax_fa_zoom.plot(zoom_result.y_zoom, zoom_result.x_zoom, 'b-', linewidth=2)
                        self.ax_fa_zoom.set_title("FA Zoom (1/e²)", fontweight="normal", fontsize=10)
                  #      self.ax_fa_zoom.set_xlabel("Intensity")
                   #     self.ax_fa_zoom.set_ylabel("Position (pixels)")
                        # Add break lines and colored regions
                        x1 = zoom_result.x1
                        x2 = zoom_result.x2
                        xmid = zoom_result.xmid
                        # Red: from x1 to xmid
                        self.ax_fa_zoom.axhspan(x1, xmid, color='red', alpha=0.3)
                        # Green: from xmid to x2
                        self.ax_fa_zoom.axhspan(xmid, x2, color='green', alpha=0.3)
                        # Draw the 1/e2 lines
                        self.ax_fa_zoom.axhline(x1, color='red', linestyle='--', linewidth=2)
                        self.ax_fa_zoom.axhline(x2, color='red', linestyle='--', linewidth=2)
                        # Draw midpoint line
                        self.ax_fa_zoom.axhline(xmid, color='black', linestyle=':', linewidth=1)
                    except Exception as e:
                        self.ax_fa_zoom.set_title(f"FA Zoom Error: {e}", fontweight="normal", fontsize=10)
                else:
                    self.ax_fa_zoom.set_title("FA Zoom (1/e²)", fontweight="normal", fontsize=10)
                self.ax_fa_zoom.set_xlim(0.0, 1.05)
                self.ax_fa_zoom.grid(True, alpha=0.3)
                self._apply_fa_profile_width_from_sa_height()
                self._apply_fa_profile_height_from_beam()
                self._apply_fa_zoom_half_height()
                self._apply_profile_zoom_borders_double()
                self._restore_fixed_axes_positions()
                self._queue_beam_canvas_draw()
            # Note: If you need Config or plot_zoomed_sa elsewhere, import them inside the function to avoid circular import.

            def update_FA_plot(self, profile_y, e2_y=None, centroid_y=None):
                """Update FA (row profile) with Y-pixel coordinates aligned to beam image rows."""
                self.ax_fa_profile.clear()
                self._style_fa_profile_axis()
                if len(profile_y) > 0:
                    y = np.arange(len(profile_y))
                    self.ax_fa_profile.plot(profile_y, y, 'b-', linewidth=2)
                    # Plot FA reference from spinbox
                    try:
                        fa_ref = None
                        if hasattr(self, "fa_reference_spin"):
                            fa_ref = int(self.fa_reference_spin.value())
                        elif hasattr(self, "cfg") and hasattr(self.cfg, "analysis") and hasattr(self.cfg.analysis, "fa_reference_point"):
                            fa_ref = int(self.cfg.analysis.fa_reference_point)
                        if fa_ref is not None:
                            fa_ref = max(0, min(fa_ref, len(profile_y)-1))
                            self.ax_fa_profile.axhline(fa_ref, linestyle='--', linewidth=2, color='r', alpha=0.85, label='FA Ref')
                    except Exception:
                        pass
                    # Match beam-image row coordinates exactly (origin at top).
                   # self.ax_fa_profile.set_ylim(len(profile_y) - 0.5, -0.5)
                   # self.ax_fa_profile.set_title('FA Profile', fontsize=10, fontweight='bold')
                    self.ax_fa_profile.grid(True, alpha=0.3)
                    #self.ax_fa_profile.set_xlabel('Intensity', fontsize=9)
                    #self.ax_fa_profile.set_ylabel('Position (pixels)', fontsize=9)
                    #self.ax_fa_profile.legend(loc='best', fontsize=8)
                self.ax_fa_profile.set_xlim(0.0, 1.05)
                self._apply_fa_profile_width_from_sa_height()
                self._apply_fa_profile_height_from_beam()
                self._apply_fa_zoom_half_height()
                self._apply_profile_zoom_borders_double()
                self._restore_fixed_axes_positions()
                self._queue_beam_canvas_draw()

            def update_SA_plot(self, profile_x, e2_x=None, centroid_x=None):
                """Update SA (column profile) with X-pixel coordinates aligned to beam image columns."""
                self.ax_sa_profile.clear()
                self._style_sa_profile_axis()
                if len(profile_x) > 0:
                    x = np.arange(len(profile_x))
                    self.ax_sa_profile.plot(x, profile_x, 'b-', linewidth=2)
                    # Match beam-image column coordinates exactly.
                    self.ax_sa_profile.set_xlim(-0.5, len(profile_x) - 0.5)
                #    self.ax_sa_profile.set_xlabel('Position (pixels)', fontsize=9)
                # Plot SA reference from spinbox if available
                try:
                    sa_ref = None
                    if hasattr(self, "sa_reference_spin"):
                        sa_ref = int(self.sa_reference_spin.value())
                    elif hasattr(self, "cfg") and hasattr(self.cfg, "analysis") and hasattr(self.cfg.analysis, "sa_reference_point"):
                        sa_ref = int(self.cfg.analysis.sa_reference_point)
                    if sa_ref is not None:
                        self.ax_sa_profile.axvline(sa_ref, linestyle='--', linewidth=2, color='r', alpha=0.85, label='SA Ref')
                except Exception:
                    pass

              #  self.ax_sa_profile.set_title('SA Profile', fontsize=10, fontweight='bold')
                self.ax_sa_profile.set_ylim(0.0, 1.05)
                self.ax_sa_profile.grid(True, alpha=0.3)
              #  self.ax_sa_profile.set_ylabel('Intensity', fontsize=9)
               # self.ax_sa_profile.legend(loc='best', fontsize=8)
                self._apply_fa_profile_width_from_sa_height()
                self._apply_fa_profile_height_from_beam()
                self._apply_fa_zoom_half_height()
                self._apply_profile_zoom_borders_double()
                self._restore_fixed_axes_positions()
                self._queue_beam_canvas_draw()


            def _apply_fa_profile_width_from_sa_height(self):
                """Set FA profile width to match SA profile height (figure coordinates)."""
                try:
                    p_sa = self.ax_sa_profile.get_position()
                    p_fa = self.ax_fa_profile.get_position()
                    new_w = p_sa.height
                    cx = p_fa.x0 + 0.5 * p_fa.width
                    new_x = cx - 0.5 * new_w
                    self.ax_fa_profile.set_position([new_x, p_fa.y0, new_w, p_fa.height])
                except Exception:
                    pass
                # Cache the exact on-canvas beam box used for real image plotting.
                with contextlib.suppress(Exception):
                    self._last_beam_axes_position = self.ax_beam.get_position().frozen()

            def _apply_fa_profile_height_from_beam(self):
                """Set FA profile height to match beam image height (figure coordinates)."""
                try:
                    p_beam = self.ax_beam.get_position()
                    p_fa = self.ax_fa_profile.get_position()
                    self.ax_fa_profile.set_position([p_fa.x0, p_beam.y0, p_fa.width, p_beam.height])
                except Exception:
                    pass

            def _apply_fa_zoom_half_height(self):
                """Set FA zoom height to half FA profile height and width equal to SA zoom height."""
                try:
                    p_prof = self.ax_fa_profile.get_position()
                    p_zoom = self.ax_fa_zoom.get_position()
                    p_sa_zoom = self.ax_sa_zoom.get_position()
                    new_h = 0.5 * p_prof.height
                    new_y = p_zoom.y0 + (p_zoom.height - new_h) / 2.0
                    # Match on-screen pixels: fa_zoom width (x-axis) == sa_zoom height (y-axis).
                    fig_w_in, fig_h_in = self.beam_figure.get_size_inches()
                    fig_ratio_h_over_w = (fig_h_in / fig_w_in) if fig_w_in > 0 else 1.0
                    new_w = p_sa_zoom.height * fig_ratio_h_over_w
                    new_x = p_zoom.x0 + (p_zoom.width - new_w) / 2.0
                    self.ax_fa_zoom.set_position([new_x, new_y, new_w, new_h])
                except Exception:
                    pass

            def _apply_profile_zoom_borders_double(self):
                """Apply double-thickness gray border to SA/FA profile and SA/FA zoom axes."""
                try:
                    for ax in (self.ax_sa_profile, self.ax_fa_profile, self.ax_sa_zoom, self.ax_fa_zoom):
                        for spine in ax.spines.values():
                            spine.set_edgecolor('#888888')
                            spine.set_linewidth(4)
                            spine.set_visible(True)
                except Exception:
                    pass

            def _queue_beam_canvas_draw(self, force: bool = False):
                if not hasattr(self, "beam_canvas"):
                    return
                if getattr(self, "_beam_draw_deferred", False) and not force:
                    self._beam_draw_requested = True
                    return
                self._beam_draw_requested = False
                if force:
                    self.beam_canvas.draw()
                else:
                    self.beam_canvas.draw_idle()

            def _style_sa_zoom_axis(self):
                self.ax_sa_zoom.set_title("SA Zoom (1/e²)", fontweight="normal", fontsize=10)
                self.ax_sa_zoom.set_xlabel("")
                self.ax_sa_zoom.set_ylabel("")
                self.ax_sa_zoom.tick_params(labelbottom=False, labelleft=False)
                self.ax_sa_zoom.grid(True, alpha=0.3, linewidth=2.0)
                for spine in self.ax_sa_zoom.spines.values():
                    spine.set_edgecolor('#888888')
                    spine.set_linewidth(4)
                    spine.set_visible(True)

            def _style_fa_zoom_axis(self):
                self.ax_fa_zoom.set_title("FA Zoom (1/e²)", fontweight="normal", fontsize=10)
                self.ax_fa_zoom.set_xlabel("")
                self.ax_fa_zoom.set_ylabel("")
                self.ax_fa_zoom.tick_params(labelbottom=False, labelleft=False)
                self.ax_fa_zoom.grid(True, alpha=0.3)
                for spine in self.ax_fa_zoom.spines.values():
                    spine.set_edgecolor('#888888')
                    spine.set_linewidth(4)
                    spine.set_visible(True)

            def _style_sa_profile_axis(self):
                self.ax_sa_profile.set_xlabel("")
                self.ax_sa_profile.set_ylabel("")
                self.ax_sa_profile.tick_params(labelbottom=False, labelleft=False)
                self.ax_sa_profile.grid(True, alpha=0.3)
                for spine in self.ax_sa_profile.spines.values():
                    spine.set_edgecolor('#888888')
                    spine.set_linewidth(4)
                    spine.set_visible(True)

            def _style_fa_profile_axis(self):
                self.ax_fa_profile.set_xlabel("")
                self.ax_fa_profile.set_ylabel("")
                self.ax_fa_profile.tick_params(labelbottom=False, labelleft=False)
                self.ax_fa_profile.grid(True, alpha=0.3)
                for spine in self.ax_fa_profile.spines.values():
                    spine.set_edgecolor('#888888')
                    spine.set_linewidth(4)
                    spine.set_visible(True)

            def _apply_empty_plot_layout(self):
                try:
                    h, w = self._get_beam_shape_for_layout()
                    self._style_sa_profile_axis()
                    self._style_fa_profile_axis()
                    self._style_sa_zoom_axis()
                    self._style_fa_zoom_axis()
                    self.ax_sa_profile.set_xlim(-0.5, max(w - 0.5, 0.5))
                    self.ax_sa_profile.set_ylim(0.0, 1.05)
                    self.ax_sa_zoom.set_xlim(-0.5, max(w - 0.5, 0.5))
                    self.ax_sa_zoom.set_ylim(0.0, 1.05)
                    self.ax_fa_profile.set_ylim(max(h - 0.5, 0.5), -0.5)
                    self.ax_fa_profile.set_xlim(0.0, 1.05)
                    self.ax_fa_zoom.set_ylim(max(h - 0.5, 0.5), -0.5)
                    self.ax_fa_zoom.set_xlim(0.0, 1.05)
                except Exception:
                    pass

            def _ensure_beam_colorbar_placeholder(self):
                """Create the intensity colorbar once and keep its slot fixed across startup, analysis, and stop."""
                try:
                    self.ax_intensity_bar.set_axis_on()
                    if self._beam_cbar is None:
                        sm = cm.ScalarMappable(
                            norm=colors.Normalize(vmin=0.0, vmax=255.0),
                            cmap=_BEAM_FALSECOLOR_CMAP,
                        )
                        sm.set_array([])
                        self._beam_cbar = self.beam_figure.colorbar(sm, cax=self.ax_intensity_bar)
                    with contextlib.suppress(Exception):
                        self._beam_cbar.ax.tick_params(labelsize=8, length=0)
                    with contextlib.suppress(Exception):
                        self._beam_cbar.set_ticks([0, 255])
                        self._beam_cbar.set_ticklabels(["0", "255"])
                    with contextlib.suppress(Exception):
                        self._beam_cbar.outline.set_linewidth(1.0)
                except Exception:
                    pass

            def _nice_grid_step(self, span: float, target_divisions: int = 8) -> float:
                """Return a 1/2/5 x 10^n grid step for readable and consistent scales."""
                span = float(abs(span))
                if not np.isfinite(span) or span <= 0:
                    return 1.0
                raw = span / max(1, int(target_divisions))
                exp = np.floor(np.log10(raw))
                base = raw / (10 ** exp)
                if base < 1.5:
                    nice = 1.0
                elif base < 3.5:
                    nice = 2.0
                elif base < 7.5:
                    nice = 5.0
                else:
                    nice = 10.0
                return float(nice * (10 ** exp))

            def _apply_shared_profile_zoom_grids(self):
                """Synchronize profile/zoom grid spacing with a hard cap on tick count."""
                try:
                    # Position axes
                    self.ax_sa_profile.xaxis.set_major_locator(MaxNLocator(nbins=8, min_n_ticks=2))
                    self.ax_sa_zoom.xaxis.set_major_locator(MaxNLocator(nbins=8, min_n_ticks=2))
                    self.ax_fa_profile.yaxis.set_major_locator(MaxNLocator(nbins=8, min_n_ticks=2))
                    self.ax_fa_zoom.yaxis.set_major_locator(MaxNLocator(nbins=8, min_n_ticks=2))

                    # Intensity axes
                    self.ax_sa_profile.yaxis.set_major_locator(MaxNLocator(nbins=5, min_n_ticks=2))
                    self.ax_sa_zoom.yaxis.set_major_locator(MaxNLocator(nbins=5, min_n_ticks=2))
                    self.ax_fa_profile.xaxis.set_major_locator(MaxNLocator(nbins=5, min_n_ticks=2))
                    self.ax_fa_zoom.xaxis.set_major_locator(MaxNLocator(nbins=5, min_n_ticks=2))

                    for ax in (self.ax_sa_profile, self.ax_sa_zoom, self.ax_fa_profile, self.ax_fa_zoom):
                        with contextlib.suppress(Exception):
                            ax.minorticks_off()
                        ax.grid(True, which='major', alpha=0.25, linewidth=0.8)
                except Exception:
                    pass

            def _apply_intensity_bar_height_from_beam(self):
                """Set intensity bar axis height/y to match beam image height/y."""
                try:
                    p_beam = self.ax_beam.get_position()
                    p_bar = self.ax_intensity_bar.get_position()
                    self.ax_intensity_bar.set_position([p_bar.x0, p_beam.y0, p_bar.width, p_beam.height])
                except Exception:
                    pass

            def _move_sa_panels_closer_to_beam(self):
                """Move SA profile/zoom down so they sit closer to the beam image."""
                try:
                    p_beam = self.ax_beam.get_position()
                    p_sa = self.ax_sa_profile.get_position()
                    p_zoom = self.ax_sa_zoom.get_position()
                    p_fa_prof = self.ax_fa_profile.get_position()
                    p_fa_zoom = self.ax_fa_zoom.get_position()
                    gap_sa_beam = max(0.0, p_fa_prof.x0 - p_beam.x1)
                    gap_zoom_sa = max(0.0, p_fa_zoom.x0 - p_fa_prof.x1)
                    new_sa_y0 = p_beam.y1 + gap_sa_beam
                    self.ax_sa_profile.set_position([p_sa.x0, new_sa_y0, p_sa.width, p_sa.height])
                    p_sa_new = self.ax_sa_profile.get_position()
                    new_zoom_y0 = p_sa_new.y1 + gap_zoom_sa
                    self.ax_sa_zoom.set_position([p_zoom.x0, new_zoom_y0, p_zoom.width, p_zoom.height])
                except Exception:
                    pass

            def _center_sa_zoom_over_sa_profile(self):
                """Center SA zoom horizontally above SA profile."""
                try:
                    p_sa = self.ax_sa_profile.get_position()
                    p_zoom = self.ax_sa_zoom.get_position()
                    sa_center = p_sa.x0 + 0.5 * p_sa.width
                    new_x = sa_center - 0.5 * p_zoom.width
                    self.ax_sa_zoom.set_position([new_x, p_zoom.y0, p_zoom.width, p_zoom.height])
                except Exception:
                    pass

            def _capture_fixed_axes_positions(self):
                """Capture startup beam-panel geometry to keep ratios/sizes stable across analysis redraws."""
                try:
                    self._fixed_axes_pos = {
                        "beam": self.ax_beam.get_position().frozen(),
                        "sa_zoom": self.ax_sa_zoom.get_position().frozen(),
                        "sa_profile": self.ax_sa_profile.get_position().frozen(),
                        "fa_profile": self.ax_fa_profile.get_position().frozen(),
                        "fa_zoom": self.ax_fa_zoom.get_position().frozen(),
                        "intensity_bar": self.ax_intensity_bar.get_position().frozen(),
                    }
                except Exception:
                    self._fixed_axes_pos = None

            def _sync_initial_beam_placeholder_geometry(self):
                """After the window is shown, sync and cache the real on-screen empty beam box size once."""
                if getattr(self, "_initial_beam_placeholder_synced", False):
                    return
                self._initial_beam_placeholder_synced = True
                try:
                    self._restore_fixed_axes_positions()
                    self._capture_fixed_axes_positions()
                    with contextlib.suppress(Exception):
                        self._last_beam_axes_position = self.ax_beam.get_position().frozen()
                    self._show_empty_beam_placeholder()
                except Exception:
                    pass

            def _restore_fixed_axes_positions(self):
                """Restore startup beam-panel geometry and enforce requested FA constraints."""
                try:
                    pos = getattr(self, "_fixed_axes_pos", None)
                    if isinstance(pos, dict):
                        self.ax_beam.set_position(pos["beam"])
                        self.ax_sa_zoom.set_position(pos["sa_zoom"])
                        self.ax_sa_profile.set_position(pos["sa_profile"])
                        self.ax_fa_profile.set_position(pos["fa_profile"])
                        self.ax_fa_zoom.set_position(pos["fa_zoom"])
                        self.ax_intensity_bar.set_position(pos["intensity_bar"])
                except Exception:
                    pass
                self._move_sa_panels_closer_to_beam()
                self._center_sa_zoom_over_sa_profile()
                self._apply_fa_profile_width_from_sa_height()
                self._apply_fa_profile_height_from_beam()
                self._apply_intensity_bar_height_from_beam()
                self._apply_fa_zoom_half_height()
                self._apply_shared_profile_zoom_grids()
                self._apply_profile_zoom_borders_double()

            def update_intensity_profiles(self, profile_x: list, profile_y: list):
                """Update intensity graphs."""
                try:
                    self.ax_x.clear()
                    self.ax_y.clear()

                    if profile_x and len(profile_x) > 0:
                        self.ax_x.plot(profile_x, 'b-', linewidth=2)
                        self.ax_x.set_title(f'X Profile - Peak: {max(profile_x):.0f}', fontsize=10, fontweight='bold')
                        self.ax_x.grid(True, alpha=0.3)
                        self.ax_x.set_ylabel('Intensity', fontsize=9)

                    if profile_y and len(profile_y) > 0:
                        self.ax_y.plot(profile_y, 'r-', linewidth=2)
                        self.ax_y.set_title(f'Y Profile - Peak: {max(profile_y):.0f}', fontsize=10, fontweight='bold')
                        self.ax_y.grid(True, alpha=0.3)
                   #     self.ax_y.set_xlabel('Position (pixels)', fontsize=9)
                    #    self.ax_y.set_ylabel('Intensity', fontsize=9)

                    self.intensity_figure.tight_layout()
                    self.intensity_canvas.draw()

                    self.profile_data = {'x': profile_x, 'y': profile_y}

                except Exception as e:
                    print(f"Profile error: {e}")

            def log_result(self, results: Dict):
                """Log analysis result."""
                log_text = f"[{_dt.datetime.now().isoformat()}]\n"
                log_text += f"  Centroid: ({results.get('centroid_x', '--'):.1f}, {results.get('centroid_y', '--'):.1f})\n"
                log_text += f"  FWHM: ({results.get('fwhm_x', '--'):.2f}, {results.get('fwhm_y', '--'):.2f}) µm\n"
                log_text += f"  Peak: {results.get('peak_intensity', '--'):.0f} | Total: {results.get('total_intensity', '--'):.0f}\n"

                current = self.log_display.toPlainText()
                self.log_display.setText(log_text + ("\n" if current else "") + current)

                self.logged_data.append(results)

            def analysis_finished(self, success: bool):
                """Handle analysis completion."""
                self.progress_bar.setVisible(False)
                self.analyze_btn.setEnabled(True)
                self._analysis_busy = False
                if bool(getattr(self, "_analysis_stop_requested", False)):
                    self.set_status("Analysis stopped.", "info")
                    return

                if success:
                    self.set_status("Analysis complete", "success")
                else:
                    self.set_status("Analysis failed", "error")

            def clear_results(self):
                """Clear all results."""
                for label in self.beam_details.values():
                    label.setText("--")
                self.log_display.clear()
                self.logged_data = []
                self.ax_x.clear()
                self.ax_y.clear()
                self.intensity_canvas.draw()
                self.set_status("Ready", "info")
                # Also clear the saturation value box
                if hasattr(self, '_sat_value_box'):
                    self._ensure_sat_value_box_placeholder()

            def export_csv(self):
                """Export data to CSV."""
                if not self.logged_data:
                    QMessageBox.warning(self, "Export", "No data to export")
                    return

                path, _ = QFileDialog.getSaveFileName(self, "Save CSV", "beam_analysis.csv", "CSV Files (*.csv)")
                if not path:
                    return

                try:
                    with open(path, 'w', newline='') as f:
                        writer = csv.DictWriter(f, fieldnames=self.logged_data[0].keys())
                        writer.writeheader()
                        writer.writerows(self.logged_data)
                    QMessageBox.information(self, "Export", f"Saved to {path}")
                    self.set_status(f"Exported: {Path(path).name}", "success")
                except Exception as e:
                    QMessageBox.critical(self, "Error", str(e))

            def export_json(self):
                """Export data to JSON."""
                if not self.logged_data:
                    QMessageBox.warning(self, "Export", "No data to export")
                    return

                path, _ = QFileDialog.getSaveFileName(self, "Save JSON", "beam_analysis.json", "JSON Files (*.json)")
                if not path:
                    return

                try:
                    with open(path, 'w') as f:
                        json.dump(self.logged_data, f, indent=2)
                    QMessageBox.information(self, "Export", f"Saved to {path}")
                    self.set_status(f"Exported: {Path(path).name}", "success")
                except Exception as e:
                    QMessageBox.critical(self, "Error", str(e))

            def set_status(self, message: str, status_type: str = "info"):
                """Update status label."""
                color_map = {"info": "blue", "success": "green", "error": "red"}
                color = color_map.get(status_type, "blue")
                self.status_label.setText(message)
                self.status_label.setStyleSheet(f"color: {color}; font-weight: bold; padding: 10px; background-color: #f0f0f0; border-radius: 3px;")

            def _on_force_basler_only_toggled(self, checked: bool):
                """
                Force Basler-only mode:
                  - Locks Camera Source to "External Camera"
                  - Disables OpenCV index controls (and any webcam-related options)
                """
                try:
                    if checked:
                        # Lock to External Camera
                        if hasattr(self, "camera_source_combo"):
                            try:
                                i = self.camera_source_combo.findText("External Camera")
                                if i >= 0:
                                    self.camera_source_combo.setCurrentIndex(i)
                            except Exception:
                                pass
                            self.camera_source_combo.setEnabled(False)

                        # Disable OpenCV index spin (if present)
                        if hasattr(self, "cam_index_spin"):
                            self.cam_index_spin.setEnabled(False)

                    else:
                        if hasattr(self, "camera_source_combo"):
                            self.camera_source_combo.setEnabled(True)
                        if hasattr(self, "cam_index_spin"):
                            self.cam_index_spin.setEnabled(True)

                    # Re-run source-changed handler (signature may accept an index)
                    try:
                        if hasattr(self, "camera_source_combo"):
                            self.on_camera_source_changed(self.camera_source_combo.currentIndex())
                        else:
                            self.on_camera_source_changed(0)
                    except TypeError:
                        self.on_camera_source_changed()
                    except Exception:
                        pass
                except Exception as e:
                    try:
                        self.log_status(f"Force Basler-only toggle error: {e}", "ERROR")
                    except Exception:
                        pass



            def on_camera_source_changed(self, index):
                """Handle switching between External Camera and OpenCV Camera."""
                # Stop preview before switching
                try:
                    self.stop_camera_preview()
                except Exception:
                    pass

                source = self.camera_source_combo.currentText() if hasattr(self, "camera_source_combo") else "External Camera"

                if source.startswith("External"):
                    # Prefer an attached external camera (from main script), but if none exists,
                    # create a BaslerCameraWrapper using the selected serial number (LabVIEW/IMAQdx-like).
                    if self.external_camera is None:
                        serial = ""
                        try:
                            if hasattr(self, "main_basler_combo"):
                                serial = str(self.main_basler_combo.currentData() or "").strip()
                        except Exception:
                            serial = ""
                        try:
                            self.external_camera = BaslerCameraWrapper(device_index=0, serial_number=(serial if serial else None))
                        except Exception as e:
                            try:
                                self.log(f"[ERROR] Cannot create Basler camera wrapper: {e}")
                            except Exception:
                                pass
                            self.external_camera = None
                    self.active_camera = self.external_camera
                else:
                    idx = int(self.cam_index_spin.value()) if hasattr(self, "cam_index_spin") else 0
                    self.opencv_camera = OpenCVCameraWrapper(idx)
                    self.active_camera = self.opencv_camera

                # If we are in Live mode, restart preview
                try:
                    if hasattr(self, "mode_combo") and self.mode_combo.currentText().startswith("Live") and self.active_camera is not None:
                        self.start_camera_preview()
                except Exception:
                    pass
            def on_cam_index_changed(self, value):
                """Handle change of OpenCV camera index (restart OpenCV preview if active)."""
                if not hasattr(self, "camera_source_combo") or not self.camera_source_combo.currentText().startswith("OpenCV"):
                    return

                # Recreate OpenCV camera with new index
                try:
                    self.stop_camera_preview()
                except Exception:
                    pass

                idx = int(value)
                self.opencv_camera = OpenCVCameraWrapper(idx)
                self.active_camera = self.opencv_camera

                try:
                    if hasattr(self, "mode_combo") and self.mode_combo.currentText().startswith("Live"):
                        self.start_camera_preview()
                except Exception:
                    pass

            # ---------------- Engineering Settings Gate + Auto Exposure ----------------
            def _set_engineering_locked(self, locked: bool):
                """Enable/disable the engineering settings panels inside the Settings tab."""
                self._engineering_locked = bool(locked)

                # Disable/enable Settings-tab groups except the Engineering box itself.
                try:
                    widgets = []
                    # Common panels
                    for name in [
                        "pm_settings_panel",
                        "per_settings_panel",
                        "motor_panel",
                        "connection_group",
                        "camattr_group",
                        "sat_pi_group",
                        "camera2_group",
                        "camera3_group",
                        "uv_settings_group",
                        "laser_settings_group",
                        "tec_settings_group",
                    ]:
                        if hasattr(self, name):
                            widgets.append(getattr(self, name))
                    for w in widgets:
                        if w is None:
                            continue
                        if w is getattr(self, "engineering_group", None):
                            w.setEnabled(True)
                        else:
                            w.setEnabled(not locked)
                except Exception:
                    pass

                try:
                    if locked:
                        self.lbl_engineering_note.setText(
                            "Please input a password in order\nto access the engineering settings\n\n(Engineering settings are locked.)"
                        )
                    else:
                        self.lbl_engineering_note.setText(
                            "Please input a password in order\nto access the engineering settings"
                        )
                except Exception:
                    pass


            def _on_auto_exposure_toggled(self, checked: bool):
                """Toggle Auto Exposure and update button style (LabVIEW-like)."""
                try:
                    # Keep config as the single source of truth
                    if hasattr(self, "config") and self.config is not None:
                        self.config.auto_exposure.enabled = bool(checked)
                except Exception:
                    pass

                # Update visual style
                try:
                    self._update_auto_exposure_button_style(bool(checked))
                except Exception:
                    pass
                self._refresh_connection_indicators()


            def _update_auto_exposure_button_style(self, enabled: bool):
                """Bright color when enabled, neutral when disabled."""
                btn = getattr(self, "btn_enable_auto_exposure", None)
                if btn is None:
                    return

                if enabled:
                    btn.setText("Enable Auto Exposure (ON)")
                    btn.setStyleSheet("""
                        QPushButton {
                            background-color: #00c853;
                            color: white;
                            font-weight: bold;
                            border: 2px solid #009624;
                            border-radius: 6px;
                            padding: 6px;
                        }
                    """)
                else:
                    btn.setText("Enable Auto Exposure")
                    btn.setStyleSheet("""
                        QPushButton {
                            background-color: #cccccc;
                            color: black;
                            border: 1px solid #999999;
                            border-radius: 6px;
                            padding: 6px;
                        }
                    """)

            def _on_sat_pi_params_changed(self, *args):
                """Sync Saturation threshold and PI gains to the config (if present)."""
                try:
                    sat = float(self.sat_thresh_input.value()) if hasattr(self, "sat_thresh_input") else None
                except Exception:
                    sat = None
                try:
                    kp = float(self.sat_kp_spin.value()) if hasattr(self, "sat_kp_spin") else None
                except Exception:
                    kp = None
                try:
                    ki = float(self.sat_ki_spin.value()) if hasattr(self, "sat_ki_spin") else None
                except Exception:
                    ki = None

                cfg = getattr(self, "config", None)
                if cfg is None:
                    return

                # saturation threshold lives under analysis
                try:
                    if sat is not None and hasattr(cfg, "analysis") and cfg.analysis is not None:
                        setattr(cfg.analysis, "saturation_threshold_percent", sat)
                except Exception:
                    pass

                # PI gains live under auto_exposure (if that block exists)
                try:
                    if hasattr(cfg, "auto_exposure") and cfg.auto_exposure is not None:
                        if kp is not None:
                            setattr(cfg.auto_exposure, "kp", kp)
                        if ki is not None:
                            setattr(cfg.auto_exposure, "ki", ki)
                except Exception:
                    pass


            def _on_require_password_toggled(self, checked: bool):
                """When enabled, lock engineering settings behind a user-defined password."""
                try:
                    from PyQt5.QtWidgets import QInputDialog
                except Exception:
                    self._set_engineering_locked(bool(checked))
                    return

                if checked:
                    # Ask user to create password first time.
                    if not self._engineering_password:
                        pw, ok = QInputDialog.getText(
                            self,
                            "Set Engineering Password",
                            "Create a password for Engineering Settings:",
                            QLineEdit.Password,
                        )
                        if not ok or not str(pw).strip():
                            try:
                                self.btn_require_password.blockSignals(True)
                                self.btn_require_password.setChecked(False)
                            finally:
                                self.btn_require_password.blockSignals(False)
                            return
                        self._engineering_password = str(pw)

                    self._set_engineering_locked(True)

                    # Prompt to unlock now (optional)
                    pw2, ok2 = QInputDialog.getText(
                        self,
                        "Unlock Engineering Settings",
                        "Enter password to unlock Engineering Settings:",
                        QLineEdit.Password,
                    )
                    if ok2 and str(pw2) == str(self._engineering_password):
                        self._set_engineering_locked(False)
                    else:
                        self._set_engineering_locked(True)
                else:
                    self._set_engineering_locked(False)
                    self._engineering_password = None

            def _update_auto_exposure_style(self, enabled: bool):
                """Backward-compatible wrapper (use _update_auto_exposure_button_style)."""
                try:
                    self._update_auto_exposure_button_style(bool(enabled))
                except Exception:
                    pass


            
            # -----------------------------
            # Serial Number → Laser Specs auto-fill (from CSV)
            # -----------------------------
            def _init_general_laser_spec_lookup(self):
                """Wire the Laser Control tab serial-number box to auto-fill product + set current.
                
                Reads: 'General Laser Specification Reference.csv' (same folder as this .py by default).
                Behavior:
                  - When the user finishes editing the serial-number field, we look up the row in the CSV.
                  - We set the product name on the Laser Control panel (if a suitable widget exists).
                  - We set 'Set Current (mA)' in the Settings tab to the 'lensing/lasing current' value.
                """
                try:
                    if not hasattr(self, "laser_control_panel") or self.laser_control_panel is None:
                        return
                except Exception:
                    return

                # Load (and cache) the reference table once.
                try:
                    self._laser_spec_ref = self._load_general_laser_spec_reference()
                except Exception as e:
                    try:
                        self.log_status(f"Laser spec CSV load failed: {e}", "ERROR")
                    except Exception:
                        pass
                    self._laser_spec_ref = {}
                    return

                # Find a serial-number entry widget on the LaserControlPanel (best-effort).

                # Make product display non-dropdown (hide combo and show read-only text field) if possible.
                try:
                    self._ensure_laser_product_is_text(panel=self.laser_control_panel)
                except Exception:
                    pass


                # Add PartNo field near Product (best-effort)
                try:
                    self._ensure_laser_partno_field(panel=self.laser_control_panel)
                except Exception:
                    pass

                serial_w = self._find_first_attr(
                    self.laser_control_panel,
                    [
                        "serial_number_edit", "serial_edit", "edt_serial", "edit_serial", "serialNumberEdit",
                        "serial_number_box", "serial_box", "serialNumberBox", "serial_line_edit",
                        "le_serial", "line_serial", "txt_serial", "serial_input"
                    ]
                )

                if serial_w is None:
                    # Fall back: scan all QLineEdits for objectName containing 'partno'/'serial'/'sn'
                    try:
                        from PyQt5.QtWidgets import QLineEdit
                        for le in self.laser_control_panel.findChildren(QLineEdit):
                            name = (le.objectName() or "").lower()
                            if ("partno" in name) or ("serial" in name) or (name in ("sn", "s_n")):
                                serial_w = le
                                break
                    except Exception:
                        serial_w = None

                if serial_w is None:
                    try:
                        self.log_status("Laser spec lookup: could not find serial-number widget on LaserControlPanel.", "WARN")
                    except Exception:
                        pass
                    return

                # Use editingFinished to avoid triggering on every keystroke.
                try:
                    serial_w.editingFinished.connect(self._on_laser_serial_entered)
                except Exception:
                    # If it's not a QLineEdit-like widget, try textChanged
                    try:
                        serial_w.textChanged.connect(lambda _t: self._on_laser_serial_entered())
                    except Exception:
                        pass

                # Run once if a serial number is already filled in
                try:
                    if hasattr(serial_w, "text") and str(serial_w.text()).strip():
                        self._on_laser_serial_entered()
                except Exception:
                    pass

            
            def _load_general_laser_spec_reference(self):
                """Return dict: PartNo -> {'product': str|None, 'set_current_ma': float|None}.

                CSV (exact columns):
                  - PartNo (serial/part number)
                  - Product (product name)
                  - Lensing Current (mA)
                """
                # Default path: same directory as this script
                base_dir = os.path.dirname(os.path.abspath(__file__))
                candidates = [
                    os.path.join(base_dir, "General Laser Specification Reference.csv"),
                    os.path.join(os.getcwd(), "General Laser Specification Reference.csv"),
                ]
                csv_path = None
                for p in candidates:
                    try:
                        if os.path.isfile(p):
                            csv_path = p
                            break
                    except Exception:
                        continue

                if not csv_path:
                    raise FileNotFoundError(
                        "Could not find 'General Laser Specification Reference.csv'. "
                        "Place the CSV in the same folder as this .py file."
                    )

                ref = {}
                with open(csv_path, "r", newline="", encoding="utf-8-sig", errors="ignore") as f:
                    reader = csv.DictReader(f)
                    headers = [h for h in (reader.fieldnames or []) if h is not None]

                    required = ["PartNo", "Product", "Lensing Current"]
                    missing = [c for c in required if c not in headers]
                    if missing:
                        raise ValueError(f"CSV missing required column(s) {missing}. Found headers: {headers}")

                    for row in reader:
                        try:
                            sn = str(row.get("PartNo", "")).strip()
                            if not sn:
                                continue
                            prod = str(row.get("Product", "")).strip() or None

                            cur_txt = str(row.get("Lensing Current", "")).strip()
                            cur = None
                            if cur_txt != "":
                                mm = re.search(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", cur_txt)
                                if mm:
                                    cur = float(mm.group(0))

                            ref[sn] = {"product": prod, "set_current_ma": cur}
                        except Exception:
                            continue

                return ref


            def _pick_column(self, headers, candidates):
                """Pick a header from `headers` that best matches any candidate string."""
                def _norm(s: str) -> str:
                    return re.sub(r"\s+", " ", str(s or "")).strip().lower()

                hnorm = {_norm(h): h for h in headers}
                for cand in candidates:
                    c = _norm(cand)
                    if c in hnorm:
                        return hnorm[c]
                # Contains-match fallback
                for h in headers:
                    hn = _norm(h)
                    for cand in candidates:
                        c = _norm(cand)
                        if c and c in hn:
                            return h
                return None
            def _on_main_serial_load_clicked(self):
                """Load laser specs from SQL view dbo.v_LaserSpecs_by_SN using the top-bar SN field.

                NOTE: This is DB-only (no CSV fallback)."""
                try:
                    sn_txt = str(self.operator_serial_edit.text()).strip() if hasattr(self, "operator_serial_edit") else ""
                except Exception:
                    sn_txt = ""
                if not sn_txt:
                    try:
                        self.log_status("Serial load: enter an SN first.", "WARN")
                    except Exception:
                        pass
                    return

                try:
                    sn_int = int(sn_txt)
                except Exception:
                    try:
                        self.log_status(f"Serial load: SN must be an integer (got '{sn_txt}').", "WARN")
                    except Exception:
                        pass
                    return

                rec = self._query_laser_specs_by_sn_from_udl(sn_int)
                if not rec:
                    try:
                        self.log_status(f"SN '{sn_int}' not found in database view dbo.v_LaserSpecs_by_SN", "WARN")
                    except Exception:
                        pass
                    return

                panel = getattr(self, "laser_control_panel", None)
                try:
                    self._populate_laser_specs_from_record(panel, rec)
                except Exception as e:
                    try:
                        self.log_status(f"Serial load: could not populate fields from DB record: {e}", "WARN")
                    except Exception:
                        pass
                    return

                try:
                    prod = rec.get("Product") or rec.get("PRODUCT") or ""
                    self.log_status(f"Serial load: loaded specs for SN={sn_int} from DB. Product={prod if prod else '(n/a)'}", "SUCCESS")
                except Exception:
                    pass

            def _save_beam_panel_snapshot(self):
                """Save screenshot of the beam canvas (beam image + colorbar + FA/SA plots + saturation indicator)."""
                try:
                    if not hasattr(self, "beam_canvas") or self.beam_canvas is None:
                        self.log_status("Save screenshot: beam canvas is not available.", "WARN")
                        return

                    save_dir_txt = ""
                    try:
                        save_dir_txt = str(self.save_path_edit.text()).strip()
                    except Exception:
                        save_dir_txt = ""
                    if not save_dir_txt:
                        self.log_status("Save screenshot: enter 'Path to save' first.", "WARN")
                        return

                    ext = "png"
                    try:
                        ext = str(self.image_type_combo.currentText()).strip().lower() or "png"
                    except Exception:
                        ext = "png"

                    save_dir = Path(save_dir_txt).expanduser()
                    save_dir.mkdir(parents=True, exist_ok=True)

                    sn_txt = ""
                    try:
                        sn_txt = str(self.operator_serial_edit.text()).strip()
                    except Exception:
                        sn_txt = ""
                    sn_tag = re.sub(r"[^A-Za-z0-9_-]", "_", sn_txt) if sn_txt else "NA"

                    fac_sac = "FACSAC"
                    try:
                        fac_sac = str(self.fac_sac_combo.currentText()).strip().upper() or "FACSAC"
                    except Exception:
                        fac_sac = "FACSAC"

                    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    out_path = save_dir / f"beam_panel_{sn_tag}_{fac_sac}_{ts}.{ext}"

                    # Grab the exact displayed canvas (includes beam image, colorbar, FA/SA profile+zoom, and saturation indicator).
                    pix = self.beam_canvas.grab()
                    ok = pix.save(str(out_path), ext.upper())
                    if not ok:
                        # Fallback to direct figure save if Qt grab-save fails for any reason.
                        self.beam_figure.savefig(str(out_path), dpi=150)

                    self.last_snapshot_path = str(out_path)
                    self.log_status(f"Screenshot saved: {out_path}", "SUCCESS")
                    metrics = getattr(self, "last_analysis_metrics", None)
                    if metrics is None:
                        metrics = self._results_dict_to_metrics_like(getattr(self, "last_results_dict", None))
                    if metrics is None:
                        self.log_status("Database export skipped: no analysis results are available yet.", "WARN")
                        return
                    self.export_lensing_analysis_to_db(metrics)
                except Exception as e:
                    try:
                        self.log_status(f"Save screenshot failed: {e}", "ERROR")
                    except Exception:
                        pass

            def _browse_save_path(self):
                """Browse and set directory for screenshot saving."""
                try:
                    current = ""
                    try:
                        current = str(self.save_path_edit.text()).strip()
                    except Exception:
                        current = ""
                    folder = QFileDialog.getExistingDirectory(self, "Select Save Folder", current or "")
                    if folder:
                        self.save_path_edit.setText(str(folder))
                except Exception as e:
                    try:
                        self.log_status(f"Browse save path failed: {e}", "WARN")
                    except Exception:
                        pass


            def _query_laser_specs_by_sn_from_udl(self, sn_int: int) -> dict | None:
                """Query dbo.v_LaserSpecs_by_SN for a given SN using the same UDL connection as Operators.

                Returns a dict of column->value for the first match, or None if not found / on error.
                """
                try:
                    # Use the same UDL path logic as _query_operators_from_udl (LabVIEW parity)
                    udl_path = Path(r"C:/Users/4510205/Downloads/data/IPSMES.udl")
                    if not udl_path.exists():
                        # Fallback: try relative 'data/IPSMES.udl' next to this file
                        try:
                            udl_path2 = Path(__file__).resolve().parent / "data" / "IPSMES.udl"
                            if udl_path2.exists():
                                udl_path = udl_path2
                        except Exception:
                            pass
                    if not udl_path.exists():
                        raise FileNotFoundError(str(udl_path))
            
                    udl_text = udl_path.read_text(encoding="utf-16", errors="ignore")
                    conn_str = self._udl_to_pyodbc_connstr(udl_text)
            
                   # import importlib
                    pyodbc = importlib.import_module("pyodbc")
            
                    sql = "SELECT TOP 1 * FROM dbo.v_LaserSpecs_by_SN WHERE SN = ?"
                    with pyodbc.connect(conn_str, timeout=3) as cn:
                        cur = cn.cursor()
                        cur.execute(sql, int(sn_int))
                        row = cur.fetchone()
                        if not row:
                            return None
                        cols = [d[0] for d in cur.description] if getattr(cur, "description", None) else []
                        try:
                            return {cols[i]: row[i] for i in range(len(cols))}
                        except Exception:
                            # Fallback if description/row is weird
                            return {}
                except Exception as e:
                    try:
                        self.log_status(f"Laser DB lookup failed for SN={sn_int}: {e}", "WARN")
                    except Exception:
                        pass
                    return None
            
            def _set_laser_panel_field_best_effort(self, panel, keys: list[str], value):
                """Best-effort: set a value onto a widget on LaserControlPanel by matching objectName/attr names."""
                if panel is None:
                    return
                if value is None:
                    return
                val_s = "" if value is None else str(value)
            
                # 1) direct attribute names
                w = self._find_first_attr(panel, keys)
                if w is not None:
                    try:
                        if hasattr(w, "setText"):
                            w.setText(val_s)
                            return
                    except Exception:
                        pass
            
                # 2) search child line edits by objectName heuristics
                try:
                    for le in panel.findChildren(QLineEdit):
                        try:
                            nm = (le.objectName() or "").lower()
                            if not nm:
                                continue
                            for k in keys:
                                if k.lower() in nm:
                                    le.setText(val_s)
                                    return
                        except Exception:
                            continue
                except Exception:
                    pass
            
            def _populate_laser_specs_from_record(self, panel, rec: dict):
                """Populate LaserControlPanel + Settings tab fields from a DB record (dbo.v_LaserSpecs_by_SN)."""
                if not rec:
                    return
                try:
                    self._last_laser_spec_record = dict(rec)
                except Exception:
                    self._last_laser_spec_record = rec
            
                # Common columns from the view (based on your SSMS screenshot)
                partno = rec.get("PartNo") or rec.get("PartNO") or rec.get("PARTNO")
                product = rec.get("Product") or rec.get("PRODUCT")
                bed = rec.get("Bed") or rec.get("BED")
                chip = rec.get("Chip") or rec.get("CHIP")
                vendor = rec.get("Vendor") or rec.get("VENDOR")
                notes = rec.get("Notes") or rec.get("NOTES")
            
                # Some current/limit fields (exist in your view list)
                set_current = rec.get("Lensing_Current") or rec.get("Set_Current_mA") or rec.get("laser_set_current_ma")
                # Many of your view columns are REAL and may be None; keep best-effort conversions.
            
                # Cache for Laser ON behavior (if your code uses it)
                try:
                    self._laser_spec_product = product
                except Exception:
                    pass
                try:
                    if set_current is not None:
                        self._laser_spec_current_ma = float(set_current)
                except Exception:
                    pass
            
                # Update product name (existing helper keeps UI consistent)
                if product:
                    try:
                        self._set_product_on_laser_panel(panel, str(product))
                    except Exception:
                        pass
            
                # Update Set Current (mA) in Settings tab + laser panel if present
                if set_current is not None:
                    try:
                        sc = float(set_current)
                    except Exception:
                        sc = None
                    if sc is not None:
                        try:
                            if hasattr(self, "laser_edits") and self.laser_edits and len(self.laser_edits) >= 1:
                                self.laser_edits[0].setText(f"{sc:g}")
                        except Exception:
                            pass
                        try:
                            self._set_current_on_laser_panel(panel, float(sc))
                        except Exception:
                            pass
            
                # Fill other text fields on the laser panel (best-effort)
                if partno is not None:
                    self._set_laser_panel_field_best_effort(panel, ["partno", "part_no", "part"], partno)
                if bed is not None:
                    self._set_laser_panel_field_best_effort(panel, ["bed"], bed)
                if chip is not None:
                    self._set_laser_panel_field_best_effort(panel, ["chip"], chip)
                if vendor is not None:
                    self._set_laser_panel_field_best_effort(panel, ["vendor"], vendor)
                if notes is not None:
                    self._set_laser_panel_field_best_effort(panel, ["notes", "note"], notes)
            
                try:
                    self.log_status(
                        f"Laser specs loaded from DB for SN={rec.get('SN', '')} → product={product or '(n/a)'}, part={partno or '(n/a)'}",
                        "INFO",
                    )
                except Exception:
                    pass
            
            def _resolve_ipismes_udl_path(self) -> Path:
                """Resolve the IPSMES UDL path using the same search order as the other DB helpers."""
                candidates = [
                    Path(r"C:/Users/4510205/Downloads/data/IPSMES.udl"),
                    Path(__file__).resolve().parent / "data" / "IPSMES.udl",
                ]
                for candidate in candidates:
                    try:
                        if candidate.exists():
                            return candidate
                    except Exception:
                        continue
                raise FileNotFoundError(str(candidates[0]))

            def _db_safe_float(self, value):
                """Convert a numeric value for database writes, preserving NULL for blank/NaN/inf."""
                try:
                    if value is None:
                        return None
                    out = float(value)
                    if np.isnan(out) or np.isinf(out):
                        return None
                    return out
                except Exception:
                    return None

            def _results_dict_to_metrics_like(self, results_dict):
                """Build a minimal metrics-like object from the latest displayed GUI results."""
                if not results_dict:
                    return None
                exposure_ms = self._db_safe_float(results_dict.get("final_exposure_ms"))
                return SimpleNamespace(
                    timestamp=results_dict.get("timestamp"),
                    saturated_percent=self._db_safe_float(results_dict.get("saturation_percent")),
                    centroid_x_px=self._db_safe_float(results_dict.get("centroid_x")),
                    centroid_y_px=self._db_safe_float(results_dict.get("centroid_y")),
                    fwhm_x_um=self._db_safe_float(results_dict.get("fwhm_x")),
                    fwhm_y_um=self._db_safe_float(results_dict.get("fwhm_y")),
                    e2_x_um=self._db_safe_float(results_dict.get("width_1e2_x")),
                    e2_y_um=self._db_safe_float(results_dict.get("width_1e2_y")),
                    divergence_x_mrad=self._db_safe_float(results_dict.get("divergence_x")),
                    divergence_y_mrad=self._db_safe_float(results_dict.get("divergence_y")),
                    exposure_us=None if exposure_ms is None else exposure_ms * 1000.0,
                    ellipticity_e2=self._db_safe_float(results_dict.get("ellipticity")),
                    beam_angle_deg=self._db_safe_float(results_dict.get("beam_angle_deg")),
                )

            def export_lensing_analysis_to_db(self, metrics) -> bool:
                """Insert one analysis row into IPSMES.dbo.Lensing_Analysis."""
                try:
                    udl_path = self._resolve_ipismes_udl_path()
                    udl_text = udl_path.read_text(encoding="utf-16", errors="ignore")
                    conn_str = self._udl_to_pyodbc_connstr(udl_text)
                    pyodbc = importlib.import_module("pyodbc")

                    serial_number = ""
                    try:
                        serial_number = str(self.operator_serial_edit.text()).strip()
                    except Exception:
                        pass

                    operator_name = ""
                    try:
                        operator_name = str(self.operator_combo.currentText()).strip()
                    except Exception:
                        pass
                    if not operator_name:
                        operator_name = str(getattr(self, "current_operator", "") or "").strip()

                    wavelength_nm = None
                    try:
                        pm_panel = getattr(self, "pm_settings_panel", None)
                        if pm_panel is not None and hasattr(pm_panel, "spn_wavelength"):
                            wavelength_nm = self._db_safe_float(pm_panel.spn_wavelength.value())
                        if wavelength_nm is None:
                            cfg = getattr(self, "config", None)
                            analysis_cfg = getattr(cfg, "analysis", None) if cfg is not None else None
                            wavelength_nm = self._db_safe_float(getattr(analysis_cfg, "wavelength_nm", None))
                    except Exception:
                        wavelength_nm = None

                    sat_threshold = 0.2
                    try:
                        sat_threshold = float(self.sat_thresh_input.value())
                    except Exception:
                        pass

                    sat_percent = self._db_safe_float(getattr(metrics, "saturated_percent", None))
                    sat_good = None if sat_percent is None else bool(sat_percent <= sat_threshold)

                    gain_db = None
                    try:
                        gain_db = self._db_safe_float(self.gain_db_spin.value())
                    except Exception:
                        gain_db = None

                    lens_type = None
                    try:
                        lens_type = str(self.fac_sac_combo.currentText()).strip() or None
                    except Exception:
                        lens_type = None

                    snapshot_path = None
                    try:
                        snapshot_path = str(getattr(self, "last_snapshot_path", "") or "").strip() or None
                    except Exception:
                        snapshot_path = None

                    row = (
                        serial_number or None,
                        getattr(metrics, "timestamp", None),
                        operator_name or None,
                        wavelength_nm,
                        sat_good,
                        self._db_safe_float(getattr(metrics, "centroid_x_px", None)),
                        None,
                        None,
                        self._db_safe_float(getattr(metrics, "centroid_y_px", None)),
                        self._db_safe_float(getattr(metrics, "fwhm_x_um", None)),
                        self._db_safe_float(getattr(metrics, "fwhm_y_um", None)),
                        self._db_safe_float(getattr(metrics, "e2_x_um", None)),
                        self._db_safe_float(getattr(metrics, "e2_y_um", None)),
                        self._db_safe_float(getattr(metrics, "divergence_x_mrad", None)),
                        self._db_safe_float(getattr(metrics, "divergence_y_mrad", None)),
                        self._db_safe_float((getattr(metrics, "exposure_us", None) or 0.0) / 1000.0),
                        gain_db,
                        sat_percent,
                        self._db_safe_float(getattr(metrics, "ellipticity_e2", None)),
                        lens_type,
                        snapshot_path,
                        self._db_safe_float(getattr(metrics, "beam_angle_deg", None)),
                        datetime.datetime.now(),
                    )

                    sql = """
                    INSERT INTO [IPSMES].[dbo].[Lensing_Analysis] (
                        [Serial Number],
                        [Date Time],
                        [Operator],
                        [WL],
                        [Sat Good],
                        [SA Cx],
                        [SA Cy],
                        [FA Cx],
                        [FA Cy],
                        [FWHM SA],
                        [FWHM FA],
                        [1/e^2 SA],
                        [1/e^2 FA],
                        [Div SA],
                        [Div FA],
                        [Exposure],
                        [Gain],
                        [Percent Saturated],
                        [Ellipticity],
                        [LensType],
                        [Path to PDF],
                        [FA_Angle],
                        [DateCreated]
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """

                    with pyodbc.connect(conn_str, timeout=5) as cn:
                        cur = cn.cursor()
                        cur.execute(sql, row)
                        cn.commit()

                    self.log_status(
                        f"Lensing_Analysis export saved for SN={serial_number or 'N/A'} at {getattr(metrics, 'timestamp', 'N/A')}",
                        "SUCCESS",
                    )
                    return True
                except Exception as e:
                    self.log_status(f"Lensing_Analysis export failed: {e}", "ERROR")
                    return False

            def _on_laser_serial_entered(self):
                """When the user enters SN on the LaserControlPanel, load specs from IPSMES (dbo.v_LaserSpecs_by_SN)."""
                try:
                    panel = getattr(self, "laser_control_panel", None)
                    if panel is None:
                        return
                except Exception:
                    return
            
                # Find the SN widget on the LaserControlPanel (best-effort)
                serial_w = self._find_first_attr(
                    panel,
                    [
                        "sn_edit", "sn_input", "sn_line_edit", "edt_sn", "edit_sn", "txt_sn",
                        "serial_number_edit", "serial_edit", "edt_serial", "edit_serial", "serialNumberEdit",
                        "serial_number_box", "serial_box", "serialNumberBox", "serial_line_edit",
                        "le_serial", "line_serial", "txt_serial", "serial_input"
                    ]
                )
                if serial_w is None or not hasattr(serial_w, "text"):
                    return
            
                sn_text = str(serial_w.text()).strip()
                if not sn_text:
                    return
            
                # DB view expects SN as int
                try:
                    sn_int = int(float(sn_text))
                except Exception:
                    try:
                        self.log_status(f"Laser SN must be an integer (got '{sn_text}')", "WARN")
                    except Exception:
                        pass
                    return
            
            
                # 1) Try DB lookup first
                rec = self._query_laser_specs_by_sn_from_udl(sn_int)
                if rec:
                    self._populate_laser_specs_from_record(panel, rec)
                    return
            
                # 2) Fallback: existing CSV reference (if present)
                try:
                    ref = getattr(self, "_laser_spec_ref", None) or {}
                    info = ref.get(str(sn_text)) or ref.get(str(sn_int))
                except Exception:
                    info = None
            
                if not info:
                    try:
                        self.log_status(f"SN '{sn_text}' not found in DB view or CSV reference.", "WARN")
                    except Exception:
                        pass
                    return
            
            
                # Existing behavior for CSV
                product = info.get("product")
                set_current = info.get("set_current_ma")
                try:
                    self._laser_spec_product = product
                    self._laser_spec_current_ma = set_current
                except Exception:
                    pass
                if product:
                    self._set_product_on_laser_panel(panel, product)
                if set_current is not None:
                    try:
                        if hasattr(self, "laser_edits") and self.laser_edits and len(self.laser_edits) >= 1:
                            self.laser_edits[0].setText(f"{float(set_current):g}")
                    except Exception:
                        pass
                    self._set_current_on_laser_panel(panel, float(set_current))
                try:
                    self.log_status(
                        f"(CSV fallback) Serial lookup: SN={sn_text} → product={product or '(n/a)'}, set_current={set_current if set_current is not None else '(n/a)'} mA",
                        "INFO",
                    )
                except Exception:
                    pass
            def _ensure_laser_product_is_text(self, panel):
                """Hide any product QComboBox on the LaserControlPanel and replace with a read-only QLineEdit.

                This removes the dropdown arrow in the Operator Laser Control product field.
                """
                try:
                    # If we've already created it, nothing to do
                    if hasattr(panel, "_product_readonly_edit") and panel._product_readonly_edit is not None:
                        return
                except Exception:
                    pass

                # Try to find a product combo by common attribute names first
                combo = self._find_first_attr(panel, ["product_combo", "cmb_product", "combo_product", "productCombo"])
                if combo is None:
                    # Fall back: scan children for a QComboBox whose objectName contains 'product'
                    try:
                      #  from PyQt5.QtWidgets import QComboBox
                        for c in panel.findChildren(QComboBox):
                            name = (c.objectName() or "").lower()
                            if "product" in name:
                                combo = c
                                break
                    except Exception:
                        combo = None

                if combo is None:
                    return

                # Create a read-only line edit and swap it into the same layout position (best effort)
                try:
                    #from PyQt5.QtWidgets import QLineEdit 
                    le = QLineEdit(panel)
                    le.setReadOnly(True)
                    le.setPlaceholderText("Product (auto from serial)")
                    le.setObjectName("product_readonly_edit")

                    parent = combo.parent()
                    layout = getattr(parent, "layout", lambda: None)()
                    replaced = False
                    if layout is not None:
                        try:
                            # Replace widget in layout if supported
                            layout.replaceWidget(combo, le)
                            replaced = True
                        except Exception:
                            replaced = False

                    # If we couldn't replace via layout, position it over the combo
                    if not replaced:
                        try:
                            le.setGeometry(combo.geometry())
                        except Exception:
                            pass

                    try:
                        combo.hide()
                    except Exception:
                        pass

                    panel._product_readonly_edit = le
                except Exception:
                    # If anything goes wrong, just disable combo (at least prevents choosing wrong product)
                    try:
                        combo.setEnabled(False)
                    except Exception:
                        pass
            def _set_product_on_laser_panel(self, panel, product: str):
                """Best-effort: push Product text into whatever widget the LaserControlPanel uses."""
                if panel is None:
                    return
                if product is None:
                    product = ""

                # 1) If we created a read-only overlay, write into it
                try:
                    if hasattr(panel, "_product_readonly_edit") and panel._product_readonly_edit is not None:
                        panel._product_readonly_edit.setText(str(product))
                        return
                except Exception:
                    pass

                # 2) Prefer a panel method if provided
                try:
                    if hasattr(panel, "set_product_name") and callable(panel.set_product_name):
                        panel.set_product_name(product)
                        return
                except Exception:
                    pass

                # 3) Try common widget names (QLineEdit/QLabel)
                try:
                    le = self._find_first_attr(panel, [
                        "product_name_edit", "product_edit", "edt_product", "product_line_edit",
                        "product_line", "product_line_edit", "le_product", "lbl_product",
                        "label_product", "product_name_label", "product_readonly_edit"
                    ])
                    if le is not None and hasattr(le, "setText"):
                        le.setText(str(product))
                        return
                except Exception:
                    pass

                # 4) Try a combo box (select matching item)
                try:
                    #from PyQt5.QtWidgets import QComboBox 
                    combo = self._find_first_attr(panel, ["product_combo", "cmb_product", "combo_product", "productCombo"])
                    if combo is None:
                        for c in panel.findChildren(QComboBox):
                            name = (c.objectName() or "").lower()
                            if "product" in name:
                                combo = c
                                break
                    if combo is not None and hasattr(combo, "findText"):
                        idx = combo.findText(str(product))
                        if idx >= 0:
                            combo.setCurrentIndex(idx)
                        else:
                            # If not found, set editable text if supported
                            try:
                                if combo.isEditable():
                                    combo.setEditText(str(product))
                            except Exception:
                                pass
                        return
                except Exception:
                    pass

                # 5) As a last resort, do nothing
                return

            def _ensure_laser_partno_field(self, panel):
                """Add a read-only PartNo field near the Product field on the LaserControlPanel (best effort).

                The DB view uses column name 'PartNo'. We create a QLineEdit with objectName containing 'partno'
                so existing best-effort setters can populate it.
                """
                if panel is None:
                    return
                try:
                    if hasattr(panel, "_partno_readonly_edit") and panel._partno_readonly_edit is not None:
                        return
                except Exception:
                    pass

               # try:
                   # from PyQt5.QtWidgets import QLineEdit, QLabel, QGridLayout  
              #  except Exception:
              #      return

                # Prefer to anchor relative to the product widget (combo or the swapped read-only edit)
                anchor = None
                try:
                    anchor = getattr(panel, "_product_readonly_edit", None)
                except Exception:
                    anchor = None
                if anchor is None:
                    # Try to find original product combo
                    anchor = self._find_first_attr(panel, ["product_combo", "cmb_product", "combo_product", "productCombo"])
                    if anchor is None:
                        # Last resort: any child whose name contains 'product'
                        try:
                            for w in panel.findChildren(QLineEdit):
                                nm = (w.objectName() or "").lower()
                                if "product" in nm:
                                    anchor = w
                                    break
                        except Exception:
                            anchor = None

                # Create widgets
                try:
                    le = QLineEdit(panel)
                    le.setReadOnly(True)
                    le.setPlaceholderText("PartNo (auto from serial)")
                    le.setObjectName("partno_readonly_edit")
                    lbl = QLabel("Part No:", panel)
                    lbl.setObjectName("partno_label")
                except Exception:
                    return

                placed = False

                # Try to place into the same grid layout as the anchor
                try:
                    if anchor is not None:
                        parent = anchor.parent() or panel
                    else:
                        parent = panel
                    layout = getattr(parent, "layout", lambda: None)()
                    if isinstance(layout, QGridLayout) and anchor is not None:
                        idx = layout.indexOf(anchor)
                        if idx >= 0:
                            row, col, rowspan, colspan = layout.getItemPosition(idx)
                            # Heuristic: label is usually one column to the left of widget
                            label_col = max(0, col - 1)
                            target_row = row + 1
                            layout.addWidget(lbl, target_row, label_col)
                            layout.addWidget(le, target_row, col, 1, max(1, colspan))
                            placed = True
                except Exception:
                    placed = False

                # Fallback: position it just below the anchor geometry so it's visible even if layout unknown
                if not placed and anchor is not None:
                    try:
                        g = anchor.geometry()
                        # Put label left of the edit, align with existing label column if any
                        lbl.move(max(0, g.x() - 90), g.y() + g.height() + 6)
                        le.setGeometry(g.x(), g.y() + g.height() + 4, g.width(), g.height())
                        placed = True
                    except Exception:
                        placed = False

                # Last resort: just add to panel's main layout at the bottom
                if not placed:
                    try:
                        lay = getattr(panel, "layout", lambda: None)()
                        if lay is not None:
                            lay.addWidget(lbl)
                            lay.addWidget(le)
                            placed = True
                    except Exception:
                        placed = False

                try:
                    panel._partno_readonly_edit = le
                except Exception:
                    pass
                # If we replaced the product dropdown with a read-only text field, use it
                try:
                    le = getattr(panel, "_product_readonly_edit", None)
                    if le is not None and hasattr(le, "setText"):
                        le.setText(str(product))
                        return
                except Exception:
                    pass

                # Try common widget names
                w = self._find_first_attr(panel, ["product_name_edit", "product_edit", "edt_product", "product_line_edit", "lbl_product", "label_product", "product_name_label"])
                if w is not None:
                    # QLabel or QLineEdit
                    try:
                        if hasattr(w, "setText"):
                            w.setText(str(product))
                            return
                    except Exception:
                        pass

                # Try a combo box (select matching item)
                combo = self._find_first_attr(panel, ["product_combo", "cmb_product", "combo_product", "productCombo"])
                if combo is not None:
                    try:
                        # exact match first, then contains match
                        for i in range(combo.count()):
                            if str(combo.itemText(i)).strip() == str(product).strip():
                                combo.setCurrentIndex(i)
                                return
                        for i in range(combo.count()):
                            if str(product).strip().lower() in str(combo.itemText(i)).strip().lower():
                                combo.setCurrentIndex(i)
                                return
                    except Exception:
                        pass

            def _set_current_on_laser_panel(self, panel, current_ma: float):
                # Prefer a method if the panel provides one
                try:
                    if hasattr(panel, "set_set_current_ma") and callable(panel.set_set_current_ma):
                        panel.set_set_current_ma(float(current_ma))
                        return
                except Exception:
                    pass

                # Try common widget names for "set current"
                w = self._find_first_attr(panel, ["set_current_edit", "set_current_ma_edit", "edt_set_current", "edit_set_current", "le_set_current", "current_edit"])
                if w is not None:
                    try:
                        if hasattr(w, "setText"):
                            w.setText(f"{float(current_ma):g}")
                            return
                    except Exception:
                        pass
                # QDoubleSpinBox
                sp = self._find_first_attr(panel, ["spn_set_current", "spin_set_current", "set_current_spin", "spin_current"])
                if sp is not None:
                    try:
                        if hasattr(sp, "setValue"):
                            sp.setValue(float(current_ma))
                            return
                    except Exception:
                        pass

            def _find_first_attr(self, obj, names):
                for n in names:
                    try:
                        if hasattr(obj, n):
                            return getattr(obj, n)
                    except Exception:
                        continue
                return None



def _on_auto_exposure_toggled(self, checked: bool):
                """Bind UI toggle to cfg.auto_exposure.enabled."""
                try:
                    if self.config is None:
                        self.config = Config()
                except Exception:
                    pass

                try:
                    if self.config is not None and hasattr(self.config, "auto_exposure"):
                        self.config.auto_exposure.enabled = bool(checked)
                except Exception:
                    pass

                try:
                    if hasattr(self, "max_exposure_ms_spin") and self.max_exposure_ms_spin is not None:
                        self.max_exposure_ms_spin.setEnabled(bool(checked))
                except Exception:
                    pass

                try:
                    self._update_auto_exposure_style(bool(checked))
                except Exception:
                    pass



def main():
    """Main entry point."""
    app = QApplication(sys.argv)
    gui = BaslerAnalysisGUI()
    gui.show()
    sys.exit(app.exec_())



if __name__ == "__main__":
    main()
