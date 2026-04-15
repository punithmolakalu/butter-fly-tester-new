"""
Main ViewModel: exposes data and commands to the View.
Connection (connect/disconnect) uses separate worker threads so UI does not block.
PRM move/home: run in separate threads (same as reference Tkinter) so Stop does not block next Home/Move.
"""
import os
import time
import math
import configparser
import threading
from typing import Any, Optional, Tuple, Union

from PyQt5.QtCore import QObject, QThread, pyqtSignal, QTimer, pyqtSlot, QMetaObject, Qt

from instruments import connection as conn
from instruments.connection import PRMConnection
from instruments.thorlabs_powermeter import THORLABS_GUI_MULT_MAX, THORLABS_GUI_MULT_MIN
from workers.workers import (
    ArroyoWorker,
    AndoWorker,
    ActuatorWorker,
    WavemeterWorker,
    GentecWorker,
    ThorlabsPowermeterWorker,
    PRMWorker,
)


def _run_prm_home(viewmodel):
    """Run home in thread (same as reference: each Home in its own thread). Emit when done so UI updates."""
    conn = viewmodel._prm_connection
    if not conn or not conn.is_connected():
        viewmodel._prm_op_done.emit()
        return
    try:
        conn.home()
    except Exception:
        pass
    finally:
        viewmodel._prm_op_done.emit()


def _run_prm_move(viewmodel, angle_val, speed):
    """Run move in thread (same as reference: each Move in its own thread). Emit when done so UI updates."""
    conn = viewmodel._prm_connection
    if not conn or not conn.is_connected():
        viewmodel._prm_op_done.emit()
        return
    try:
        if speed > 0:
            conn.set_speed(speed)
        conn.move_to(angle_val)
    except Exception:
        pass
    finally:
        viewmodel._prm_op_done.emit()


class MainViewModel(QObject):
    connection_state_changed = pyqtSignal(dict)  # {"Arroyo": bool, "Ando": bool, "Actuator": bool, ...}
    arroyo_readings_updated = pyqtSignal(dict)
    gentec_reading_updated = pyqtSignal(object)
    thorlabs_reading_updated = pyqtSignal(object)
    gentec_wavelength_nm_read = pyqtSignal(object)  # float nm or None — Manual Control readback
    thorlabs_wavelength_nm_read = pyqtSignal(object)
    wavemeter_wavelength_updated = pyqtSignal(object)  # float (nm) or None
    wavemeter_range_applied = pyqtSignal(bool, str)  # success, range_str
    prm_position_updated = pyqtSignal(object)  # float or None
    prm_connection_failed = pyqtSignal(str)  # error message when PRM connect fails
    prm_error = pyqtSignal(str)  # error message for PRM speed/stop (show dialog like Tkinter messagebox)
    prm_command_finished = pyqtSignal()  # move/home subprocess finished (re-enable PRM buttons)
    _prm_op_done = pyqtSignal()  # emitted from background thread when move/home finishes (triggers poll + command_finished)
    ando_sweep_status_updated = pyqtSignal(bool)  # True = sweeping, False = idle/stopped
    status_log_message = pyqtSignal(str)  # append to Main tab status log (connection details, etc.)
    actuator_status_line = pyqtSignal(str)  # Manual Control: actuator A/B state line

    def __init__(self, parent=None):
        super(MainViewModel, self).__init__(parent)
        self._arroyo_connected = False
        self._arroyo_connecting = False  # True while worker is opening serial; blocks poll/read races
        self._ando_connected = False
        self._actuator_connected = False
        self._wavemeter_connected = False
        self._prm_connected = False
        self._prm_connecting = False  # True while Kinesis connect() runs on GUI thread (yielding waits)
        self._gentec_connected = False
        self._thorlabs_connected = False
        self._shutdown_done = False
        # True only while reconnecting an already-open Arroyo (get_connection_state keeps Arroyo True until result).
        self._arroyo_reconnect_active = False
        self._last_connection_snapshot: Optional[Tuple[Tuple[str, Any], ...]] = None

        # Connection in separate threads (workers) for Arroyo, Ando, Actuator, Wavemeter, Gentec, Thorlabs
        self._thread = QThread(self)
        self._worker = ArroyoWorker()
        self._worker.moveToThread(self._thread)
        self._thread.start()
        self._worker.connection_result.connect(self._on_arroyo_connection_result)
        self._worker.connection_state_changed.connect(self._on_arroyo_connection_state_changed)
        self._worker.readings_ready.connect(self._on_readings_ready)

        self._ando_thread = QThread(self)
        self._ando_worker = AndoWorker()
        self._ando_worker.moveToThread(self._ando_thread)
        self._ando_thread.start()
        self._ando_worker.connection_state_changed.connect(self._on_ando_connection_changed)
        self._ando_worker.sweep_status_updated.connect(self._on_ando_sweep_status)

        self._actuator_thread = QThread(self)
        self._actuator_worker = ActuatorWorker()
        self._actuator_worker.moveToThread(self._actuator_thread)
        self._actuator_thread.start()
        self._actuator_worker.connection_state_changed.connect(self._on_actuator_connection_changed)
        self._actuator_worker.command_log.connect(self.status_log_message.emit)
        self._actuator_worker.actuator_status_line.connect(self.actuator_status_line.emit)

        self._wavemeter_thread = QThread(self)
        self._wavemeter_worker = WavemeterWorker()
        self._wavemeter_worker.moveToThread(self._wavemeter_thread)
        self._wavemeter_thread.start()
        self._wavemeter_worker.connection_state_changed.connect(self._on_wavemeter_connection_changed)
        self._wavemeter_worker.wavelength_updated.connect(self._on_wavemeter_wavelength)
        self._wavemeter_worker.range_applied.connect(self._on_wavemeter_range_applied)

        self._gentec_thread = QThread(self)
        self._gentec_worker = GentecWorker()
        self._gentec_worker.moveToThread(self._gentec_thread)
        self._gentec_thread.start()
        self._gentec_worker.connection_state_changed.connect(self._on_gentec_connection_changed)
        self._gentec_worker.reading_ready.connect(self._on_gentec_reading_ready)
        self._gentec_worker.gentec_wavelength_applied.connect(self._on_gentec_wavelength_applied)
        self._gentec_worker.gentec_wavelength_nm_read_ready.connect(self.gentec_wavelength_nm_read.emit)

        self._thorlabs_thread = QThread(self)
        self._thorlabs_worker = ThorlabsPowermeterWorker()
        self._thorlabs_worker.moveToThread(self._thorlabs_thread)
        self._thorlabs_thread.start()
        self._thorlabs_worker.connection_state_changed.connect(self._on_thorlabs_connection_changed)
        self._thorlabs_worker.reading_ready.connect(self._on_thorlabs_reading_ready)
        self._thorlabs_worker.thorlabs_wavelength_applied.connect(self._on_thorlabs_wavelength_applied)
        self._thorlabs_worker.thorlabs_wavelength_nm_read_ready.connect(self.thorlabs_wavelength_nm_read.emit)

        # PRM: connect on main thread (Kinesis); worker used for move/home/position only
        self._prm_thread = QThread(self)
        self._prm_worker = PRMWorker()
        self._prm_worker.moveToThread(self._prm_thread)
        self._prm_thread.start()
        self._prm_worker.position_updated.connect(self._on_prm_position)
        self._prm_worker.connection_state_changed.connect(self._on_prm_connection_state_changed)
        self._prm_connection = None

        self._wavemeter_poll_timer = QTimer(self)
        self._wavemeter_poll_timer.setInterval(800)
        self._wavemeter_poll_timer.timeout.connect(self._request_wavemeter_wavelength)

        self._gentec_poll_timer = QTimer(self)
        self._gentec_poll_timer.setInterval(800)
        self._gentec_poll_timer.timeout.connect(self._request_gentec_read)

        self._thorlabs_poll_timer = QTimer(self)
        self._thorlabs_poll_timer.setInterval(800)
        self._thorlabs_poll_timer.timeout.connect(self._request_thorlabs_read)

        self._prm_position_timer = QTimer(self)
        self._prm_position_timer.setInterval(250)
        self._prm_position_timer.timeout.connect(self._poll_prm_position)
        self._prm_had_successful_read = False
        self._prm_worker.move_completed.connect(self._on_prm_move_completed)
        self._prm_worker.home_completed.connect(self._on_prm_home_completed)
        self._prm_op_done.connect(self._on_prm_op_done)

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(800)
        self._poll_timer.timeout.connect(self._request_arroyo_read)

        self._ando_poll_timer = QTimer(self)
        self._ando_poll_timer.setInterval(800)
        self._ando_poll_timer.timeout.connect(self._request_ando_ping)

        self._actuator_poll_timer = QTimer(self)
        self._actuator_poll_timer.setInterval(800)
        self._actuator_poll_timer.timeout.connect(self._request_actuator_ping)

        # Same live connections as Connection tab → test sequence / LIV
        from viewmodel.sequence_instrument_bridge import SequenceInstrumentBridge

        self._instrument_manager = SequenceInstrumentBridge(self)
        self._gentec_gui_multiplier = self._load_gentec_gui_multiplier_from_ini()
        self._thorlabs_gui_multiplier = self._load_thorlabs_gui_multiplier_from_ini()

    def _on_arroyo_connection_result(self, ok: bool):
        self._arroyo_connecting = False
        self._arroyo_reconnect_active = False
        self._arroyo_connected = ok
        self._emit_connection_state_if_changed()
        if ok:
            self.status_log_message.emit("Arroyo: Connected")
        else:
            self.status_log_message.emit("Arroyo: Connection failed")
        if ok:
            self._poll_timer.start()
            self._request_arroyo_read()
            QTimer.singleShot(100, self._request_arroyo_read)
        else:
            self._poll_timer.stop()

    def _on_arroyo_connection_state_changed(self, state: dict):
        """When Arroyo worker reports disconnected (e.g. instrument turned off), update immediately so UI shows Disconnected."""
        if "Arroyo" in state and not state.get("Arroyo", True):
            if self._arroyo_connected:
                self.status_log_message.emit("Arroyo: Disconnected (device turned off or unplugged)")
            self._arroyo_connected = False
            self._arroyo_connecting = False
            self._arroyo_reconnect_active = False
            self._poll_timer.stop()
            self._emit_connection_state_if_changed()

    def _on_readings_ready(self, data: dict):
        self.arroyo_readings_updated.emit(data)

    def _on_ando_connection_changed(self, state: dict):
        if "Ando" in state:
            self._ando_connected = state.get("Ando", False)
        if self._ando_connected:
            self._ando_poll_timer.start()
            self._request_ando_ping()
        else:
            self._ando_poll_timer.stop()
        self._emit_connection_state_if_changed()
        if self._ando_connected:
            self.status_log_message.emit("Ando: Connected")
        else:
            self.status_log_message.emit("Ando: Disconnected")

    def _on_ando_sweep_status(self, sweeping: bool):
        self.ando_sweep_status_updated.emit(sweeping)

    def _on_actuator_connection_changed(self, state: dict):
        if "Actuator" in state:
            self._actuator_connected = state.get("Actuator", False)
        err = state.get("Actuator_error") if isinstance(state, dict) else None
        if self._actuator_connected:
            self._actuator_poll_timer.start()
            self._request_actuator_ping()
        else:
            self._actuator_poll_timer.stop()
        self._emit_connection_state_if_changed()
        if self._actuator_connected:
            self.status_log_message.emit("Actuator: Connected")
        else:
            if err:
                self.status_log_message.emit("Actuator: Connection failed — {}".format(err))
            else:
                self.status_log_message.emit("Actuator: Disconnected")

    def _on_wavemeter_connection_changed(self, state: dict):
        # Only update our state when this dict is for Wavemeter (avoids cross-talk if signal were miswired)
        if "Wavemeter" in state:
            self._wavemeter_connected = state.get("Wavemeter", False)
        error_msg = state.get("Wavemeter_error")
        self._emit_connection_state_if_changed()
        if self._wavemeter_connected:
            self.status_log_message.emit("Wavemeter: Connected")
            self._wavemeter_poll_timer.start()
            self._wavemeter_worker.trigger_read.emit()
        else:
            if error_msg:
                self.status_log_message.emit("Wavemeter: Connection failed ({})".format(error_msg))
            else:
                self.status_log_message.emit("Wavemeter: Disconnected")
            self._wavemeter_poll_timer.stop()
            self.wavemeter_wavelength_updated.emit(None)

    def _on_wavemeter_wavelength(self, wl_nm):
        self.wavemeter_wavelength_updated.emit(wl_nm)

    def _on_wavemeter_range_applied(self, success: bool, range_str: str):
        self.wavemeter_range_applied.emit(success, range_str)

    def _on_gentec_connection_changed(self, state: dict):
        if "Gentec" in state:
            self._gentec_connected = state.get("Gentec", False)
        self._emit_connection_state_if_changed()
        err = state.get("Gentec_error") if isinstance(state, dict) else None
        if self._gentec_connected:
            self.status_log_message.emit("Gentec: Connected")
        else:
            if err:
                self.status_log_message.emit("Gentec: Connection failed — {}".format(err))
            else:
                self.status_log_message.emit("Gentec: Disconnected")
        if self._gentec_connected:
            self._gentec_worker.request_set_gui_multiplier.emit(self._gentec_gui_multiplier)
            self._gentec_poll_timer.start()
            self._request_gentec_read()
            QTimer.singleShot(900, self.request_powermeter_wavelength_readbacks)
        else:
            self._gentec_poll_timer.stop()

    def _on_gentec_reading_ready(self, payload):
        """payload is None, or (power_mW: float, display_unit: str) from Gentec worker."""
        self.gentec_reading_updated.emit(payload)

    def _on_thorlabs_connection_changed(self, state: dict):
        # Only update our state when this dict is for Thorlabs (avoids cross-talk e.g. Wavemeter disconnect affecting Thorlabs)
        if "Thorlabs" in state:
            self._thorlabs_connected = state.get("Thorlabs", False)
        self._emit_connection_state_if_changed()
        err = state.get("Thorlabs_error") if isinstance(state, dict) else None
        if self._thorlabs_connected:
            self.status_log_message.emit("Thorlabs: Connected")
        else:
            if err:
                self.status_log_message.emit("Thorlabs: Connection failed — {}".format(err))
            else:
                self.status_log_message.emit("Thorlabs: Disconnected")
        if self._thorlabs_connected:
            self._thorlabs_worker.request_set_gui_multiplier.emit(self._thorlabs_gui_multiplier)
            self._thorlabs_poll_timer.start()
            self._request_thorlabs_read()
            QTimer.singleShot(900, self.request_powermeter_wavelength_readbacks)
        else:
            self._thorlabs_poll_timer.stop()

    def _on_thorlabs_reading_ready(self, value_mw):
        self.thorlabs_reading_updated.emit(value_mw)

    def _on_prm_position(self, pos):
        self.prm_position_updated.emit(pos)

    def _on_prm_connection_state_changed(self, state: dict):
        """When PRM worker reports disconnected (e.g. move/home failed or user Disconnect), clear state so UI shows Disconnected."""
        if "PRM" in state and not state.get("PRM", True):
            if self._prm_connected:
                self.status_log_message.emit("PRM: Disconnected")
            self._prm_connected = False
            self._prm_had_successful_read = False
            self._prm_position_timer.stop()
            try:
                if self._prm_connection:
                    self._prm_connection.disconnect()
            except Exception:
                pass
            self._prm_connection = None
            self._prm_worker.set_prm(None)
            self.prm_position_updated.emit(None)
            self._emit_connection_state_if_changed()

    def _request_arroyo_read(self):
        if not self._arroyo_connected or self._arroyo_connecting:
            return
        self._worker.trigger_read.emit()

    def refresh_arroyo_readings(self) -> None:
        """Trigger one immediate Arroyo poll so Main + Manual Control + linked tabs update without waiting for the timer."""
        if self._arroyo_connected and not self._arroyo_connecting:
            self._request_arroyo_read()

    def schedule_arroyo_readback_refresh(self) -> None:
        """
        Queue several Arroyo polls after laser/TEC commands or LIV/PER (when polling was paused).
        Keeps Main Laser/TEC boxes, Manual Control Arroyo block, and Alignment in sync with hardware.
        """
        if not self._arroyo_connected or self._arroyo_connecting:
            return
        self._request_arroyo_read()
        QTimer.singleShot(120, self._request_arroyo_read)
        QTimer.singleShot(350, self._request_arroyo_read)
        QTimer.singleShot(900, self._request_arroyo_read)

    def _schedule_arroyo_readback_and_resume_poll(self) -> None:
        """After a set command: schedule readback reads and restart the poll timer."""
        if not self._arroyo_connected or self._arroyo_connecting:
            return
        QTimer.singleShot(80, self._request_arroyo_read)
        QTimer.singleShot(300, self._request_arroyo_read)
        QTimer.singleShot(700, self._request_arroyo_read)
        QTimer.singleShot(1200, self._resume_arroyo_poll)

    def _resume_arroyo_poll(self) -> None:
        if self._arroyo_connected and not self._arroyo_connecting:
            if not self._poll_timer.isActive():
                self._poll_timer.start()

    def schedule_thorlabs_readback_refresh(self) -> None:
        """After LIV or other work that paused Thorlabs polling, catch up the Main tab readout."""
        if not self._thorlabs_connected:
            return
        self._request_thorlabs_read()
        QTimer.singleShot(120, self._request_thorlabs_read)
        QTimer.singleShot(350, self._request_thorlabs_read)

    def schedule_power_meter_reads_after_laser_change(self) -> None:
        """Poll Gentec/Thorlabs soon after laser or drive changes so power readouts update without waiting for the 800 ms poll."""
        if self._gentec_connected:
            self._request_gentec_read()
            QTimer.singleShot(150, self._request_gentec_read)
            QTimer.singleShot(400, self._request_gentec_read)
        if self._thorlabs_connected:
            self._request_thorlabs_read()
            QTimer.singleShot(150, self._request_thorlabs_read)
            QTimer.singleShot(400, self._request_thorlabs_read)

    def _request_ando_ping(self):
        self._ando_worker.trigger_ping.emit()

    def _request_actuator_ping(self):
        self._actuator_worker.trigger_ping.emit()

    def _request_wavemeter_wavelength(self):
        self._wavemeter_worker.trigger_read.emit()

    def _request_gentec_read(self):
        self._gentec_worker.trigger_read.emit()

    def _request_thorlabs_read(self):
        self._thorlabs_worker.trigger_read.emit()

    def _poll_prm_position(self):
        """Poll PRM position on main thread (Kinesis must be used from one thread). Update UI; on failure after a successful read, mark disconnected."""
        if not self._prm_connection or not self._prm_connection.is_connected():
            self.prm_position_updated.emit(None)
            return
        try:
            pos = self._prm_connection.get_position()
            if pos is not None:
                self._prm_had_successful_read = True
            self.prm_position_updated.emit(pos)
        except Exception:
            try:
                if self._prm_connection:
                    self._prm_connection.disconnect()
            except Exception:
                pass
            self._prm_connection = None
            self._prm_worker.set_prm(None)
            if self._prm_had_successful_read:
                self._prm_had_successful_read = False
                self._prm_connected = False
                self._prm_position_timer.stop()
                self._emit_connection_state_if_changed()
                self.status_log_message.emit("PRM: Disconnected (device turned off or unplugged)")
            self.prm_position_updated.emit(None)

    def get_connection_state(self):
        # During Arroyo COM reconnect, keep showing Connected until the worker reports success/failure
        # (avoids a bogus all-off snapshot while other instruments are still connecting in parallel).
        arroyo = self._arroyo_connected
        if self._arroyo_connecting and self._arroyo_reconnect_active:
            arroyo = True
        return {
            "Arroyo": arroyo,
            "Ando": self._ando_connected,
            "Actuator": self._actuator_connected,
            "Wavemeter": self._wavemeter_connected,
            "PRM": self._prm_connected,
            "Gentec": self._gentec_connected,
            "Thorlabs": self._thorlabs_connected,
        }

    def _emit_connection_state_if_changed(self) -> None:
        """Emit connection_state_changed only when the aggregated map changes (reduces duplicate terminal/UI updates)."""
        st = self.get_connection_state()
        snap = tuple(sorted(st.items()))
        if snap == self._last_connection_snapshot:
            return
        self._last_connection_snapshot = snap
        self.connection_state_changed.emit(st)

    def scan_ports(self):
        """Fast, runs on main thread."""
        return conn.scan_ports()

    def scan_gpib(self):
        """Return list of GPIB resource strings."""
        result = []
        done = threading.Event()

        def _scan():
            nonlocal result
            try:
                result = conn.scan_gpib()
            except Exception:
                result = []
            finally:
                done.set()

        threading.Thread(target=_scan, daemon=True).start()
        # GPIB enumeration can be slow (NI-VISA + @py, multiple list_resources queries);
        # must exceed worst-case scan time or the UI shows an empty list while discovery is still running.
        if not done.wait(timeout=35.0):
            self.status_log_message.emit("Connection: GPIB scan timeout, continuing without GPIB list.")
            return []
        return result

    def scan_visa(self):
        """Return list of all VISA resource strings (for Thorlabs powermeter etc.). Never raises."""
        result = []
        done = threading.Event()

        def _scan():
            nonlocal result
            try:
                result = conn.scan_visa()
            except Exception:
                result = []
            finally:
                done.set()

        threading.Thread(target=_scan, daemon=True).start()
        if not done.wait(timeout=3.0):
            return []
        return result

    def scan_thorlabs_powermeters(self):
        """Return VISA resource strings for Thorlabs USB devices (VID 0x1313). Never raises."""
        result = []
        done = threading.Event()

        def _scan():
            nonlocal result
            try:
                result = conn.scan_thorlabs_visa()
            except Exception:
                result = []
            finally:
                done.set()

        threading.Thread(target=_scan, daemon=True).start()
        if not done.wait(timeout=12.0):
            return []
        return result

    def scan_prm(self):
        """Return list of PRM (Kinesis) device serial numbers."""
        return conn.scan_prm()

    def get_prm_scan_status(self):
        """Return (ok, message) for PRM scan; use when scan_prm() is empty to show why."""
        return conn.get_prm_scan_status()

    # ----- Saved connection addresses (Save / Load / Auto-connect) -----
    def _instruments_dir(self):
        """Instruments folder for instrument_config.ini."""
        return os.path.dirname(os.path.abspath(conn.__file__))

    def _instrument_config_path(self):
        """Path to instrument_config.ini in instruments folder."""
        return os.path.join(self._instruments_dir(), "instrument_config.ini")

    def _load_gentec_gui_multiplier_from_ini(self) -> float:
        try:
            path = self._instrument_config_path()
            cfg = configparser.ConfigParser()
            cfg.read(path)
            if cfg.has_section("Gentec"):
                v = cfg.getfloat("Gentec", "gui_multiplier", fallback=1.1)
                if math.isfinite(v) and v > 0:
                    return float(v)
        except Exception:
            pass
        return 1.1

    def _save_gentec_gui_multiplier_to_ini(self, value: float) -> None:
        path = self._instrument_config_path()
        cfg = configparser.ConfigParser()
        if os.path.exists(path):
            try:
                cfg.read(path)
            except Exception:
                pass
        if not cfg.has_section("Gentec"):
            cfg.add_section("Gentec")
        cfg.set("Gentec", "gui_multiplier", "{:.12g}".format(float(value)))
        try:
            with open(path, "w") as f:
                cfg.write(f)
        except Exception:
            pass

    def get_gentec_gui_multiplier(self) -> float:
        return float(self._gentec_gui_multiplier)

    def set_gentec_gui_multiplier(self, value, persist: bool = True) -> None:
        try:
            v = float(value)
            if not math.isfinite(v) or v <= 0:
                v = 1.0
        except (TypeError, ValueError):
            v = 1.0
        self._gentec_gui_multiplier = v
        self._gentec_worker.request_set_gui_multiplier.emit(v)
        if persist:
            self._save_gentec_gui_multiplier_to_ini(v)

    def _load_thorlabs_gui_multiplier_from_ini(self) -> float:
        try:
            path = self._instrument_config_path()
            cfg = configparser.ConfigParser()
            cfg.read(path)
            if cfg.has_section("Thorlabs_Powermeter"):
                v = cfg.getfloat("Thorlabs_Powermeter", "gui_multiplier", fallback=1.0)
                if math.isfinite(v) and THORLABS_GUI_MULT_MIN < v < THORLABS_GUI_MULT_MAX:
                    return float(v)
        except Exception:
            pass
        return 1.0

    def _save_thorlabs_gui_multiplier_to_ini(self, value: float) -> None:
        path = self._instrument_config_path()
        cfg = configparser.ConfigParser()
        if os.path.exists(path):
            try:
                cfg.read(path)
            except Exception:
                pass
        if not cfg.has_section("Thorlabs_Powermeter"):
            cfg.add_section("Thorlabs_Powermeter")
        cfg.set("Thorlabs_Powermeter", "gui_multiplier", "{:.12g}".format(float(value)))
        try:
            with open(path, "w") as f:
                cfg.write(f)
        except Exception:
            pass

    def get_thorlabs_gui_multiplier(self) -> float:
        return float(self._thorlabs_gui_multiplier)

    def set_thorlabs_gui_multiplier(self, value, persist: bool = True) -> None:
        try:
            v = float(value)
            if not math.isfinite(v) or v <= 0:
                v = 1.0
            else:
                v = min(THORLABS_GUI_MULT_MAX, max(THORLABS_GUI_MULT_MIN, v))
        except (TypeError, ValueError):
            v = 1.0
        self._thorlabs_gui_multiplier = v
        self._thorlabs_worker.request_set_gui_multiplier.emit(v)
        if persist:
            self._save_thorlabs_gui_multiplier_to_ini(v)

    def save_connection_addresses(self, addresses: dict):
        """Save current addresses directly to instrument_config.ini."""
        path = self._instrument_config_path()
        cfg = configparser.ConfigParser()
        if os.path.exists(path):
            try:
                cfg.read(path)
            except Exception:
                pass
        if not cfg.has_section("Connection"):
            cfg.add_section("Connection")
        cfg.set("Connection", "arroyo_port", addresses.get("arroyo_port", ""))
        cfg.set("Connection", "actuator_port", addresses.get("actuator_port", ""))
        cfg.set("Connection", "ando_gpib", addresses.get("ando_gpib", ""))
        cfg.set("Connection", "wavemeter_gpib", addresses.get("wavemeter_gpib", ""))
        cfg.set("Connection", "prm_serial", addresses.get("prm_serial", ""))
        cfg.set("Connection", "gentec_port", addresses.get("gentec_port", ""))
        cfg.set("Connection", "thorlabs_visa", addresses.get("thorlabs_visa", ""))
        cfg.set("Connection", "auto_connect", addresses.get("auto_connect", "1"))
        for section, key, addr_key in [
            ("Arroyo", "port", "arroyo_port"),
            ("Actuators", "port", "actuator_port"),
            ("Gentec", "port", "gentec_port"),
            ("Thorlabs_Powermeter", "resource", "thorlabs_visa"),
            ("PRM", "serial_number", "prm_serial"),
        ]:
            val = addresses.get(addr_key, "")
            if not cfg.has_section(section):
                cfg.add_section(section)
            cfg.set(section, key, val)
        try:
            with open(path, "w") as f:
                cfg.write(f)
        except Exception:
            pass

    def load_saved_addresses(self) -> dict:
        """Load all connection addresses from instrument_config.ini."""
        defaults = {
            "arroyo_port": "",
            "actuator_port": "",
            "ando_gpib": "",
            "wavemeter_gpib": "",
            "prm_serial": "",
            "gentec_port": "",
            "thorlabs_visa": "",
            "auto_connect": "1",
        }
        config_path = self._instrument_config_path()
        if not os.path.exists(config_path):
            self._merge_saved_connections_ini_fallback(defaults)
            return defaults
        try:
            cfg = configparser.ConfigParser()
            cfg.read(config_path)
            if cfg.has_section("Connection"):
                for k in defaults:
                    if cfg.has_option("Connection", k):
                        defaults[k] = cfg.get("Connection", k).strip()
            if cfg.has_section("Arroyo") and cfg.has_option("Arroyo", "port"):
                val = cfg.get("Arroyo", "port").strip()
                if val:
                    defaults["arroyo_port"] = val
            if cfg.has_section("Actuators") and cfg.has_option("Actuators", "port"):
                val = cfg.get("Actuators", "port").strip()
                if val:
                    defaults["actuator_port"] = val
            if cfg.has_section("Gentec") and cfg.has_option("Gentec", "port"):
                val = cfg.get("Gentec", "port").strip()
                if val:
                    defaults["gentec_port"] = val
            if cfg.has_section("Thorlabs_Powermeter"):
                for opt in ("resource", "resource_string"):
                    if cfg.has_option("Thorlabs_Powermeter", opt):
                        val = cfg.get("Thorlabs_Powermeter", opt).strip()
                        if val:
                            defaults["thorlabs_visa"] = val
                            break
            if cfg.has_section("PRM") and cfg.has_option("PRM", "serial_number"):
                val = cfg.get("PRM", "serial_number").strip()
                if val:
                    defaults["prm_serial"] = val
        except Exception:
            pass
        self._merge_saved_connections_ini_fallback(defaults)
        return defaults

    def _merge_saved_connections_ini_fallback(self, defaults: dict) -> None:
        """
        If keys are still empty in ``defaults``, fill from ``instruments/saved_connections.ini``
        (``[saved]`` or ``[Connection]``). Some setups only maintain that file; the app primarily
        uses ``instrument_config.ini``.
        """
        if not isinstance(defaults, dict):
            return
        path = os.path.join(self._instruments_dir(), "saved_connections.ini")
        if not os.path.exists(path):
            return
        keys = (
            "arroyo_port",
            "actuator_port",
            "ando_gpib",
            "wavemeter_gpib",
            "prm_serial",
            "gentec_port",
            "thorlabs_visa",
            "auto_connect",
        )
        try:
            cfg = configparser.ConfigParser()
            cfg.read(path)
            for sec in ("saved", "Saved", "Connection", "CONNECTION"):
                if not cfg.has_section(sec):
                    continue
                for k in keys:
                    cur = (defaults.get(k) or "").strip()
                    if cur:
                        continue
                    if not cfg.has_option(sec, k):
                        continue
                    v = cfg.get(sec, k).strip()
                    if v:
                        defaults[k] = v
        except Exception:
            pass

    def connect_ando(self, gpib_address: str):
        """Connection in separate thread (worker)."""
        self._ando_worker.request_connect.emit(gpib_address or "")

    def disconnect_ando(self):
        self._ando_worker.request_disconnect.emit()

    def connect_wavemeter(self, gpib_address: str):
        """Connection in separate thread (worker)."""
        self._wavemeter_worker.request_connect.emit(gpib_address or "")

    def disconnect_wavemeter(self):
        self._wavemeter_worker.request_disconnect.emit()

    def apply_wavemeter_range(self, range_str: str):
        range_str = str(range_str).strip() if range_str else ""
        if range_str not in ("480-1000", "1000-1650"):
            return
        self._wavemeter_worker.request_apply_range.emit(range_str)

    def connect_actuator(self, port: str):
        """Connection in separate thread (worker)."""
        self._actuator_worker.request_connect.emit(port or "")

    def disconnect_actuator(self):
        self._actuator_worker.request_disconnect.emit()

    def connect_prm(self, serial_number: str, reconnecting: bool = False):
        """Connect PRM when device is detected (user selects serial and clicks Connect). After connect, show Connected. If device is turned off or unplugged, UI updates to Disconnected. reconnecting=True: used after move/home subprocess; do not log connection messages to status (show once only)."""
        serial_number = (serial_number or "").strip()
        if not serial_number or serial_number.lower().startswith("(no ") or "not found" in serial_number.lower():
            if self._prm_connected:
                self._prm_connected = False
                self._emit_connection_state_if_changed()
            return
        # Already connected to this serial: skip (avoids duplicate connect messages when Connect All / auto-connect runs multiple times)
        if not reconnecting and self._prm_connected and self._prm_connection and (self._prm_connection.serial_number or "").strip() == serial_number:
            return
        if self._prm_connecting:
            self.status_log_message.emit("PRM: Connection already in progress.")
            return
        self._prm_connecting = True
        self._prm_position_timer.stop()
        if self._prm_connection:
            try:
                self._prm_connection.disconnect()
            except Exception:
                pass
            self._prm_connection = None
        self._prm_worker.set_prm(None)
        try:
            status_callback = None
            self._prm_connection = PRMConnection(serial_number)
            self._prm_connection.connect(status_log=status_callback, verbose=False)
            self._prm_worker.set_prm(self._prm_connection)
            self._prm_connected = True
            self._prm_had_successful_read = False
            self._emit_connection_state_if_changed()
            self._prm_position_timer.start()
            self._poll_prm_position()
            if not reconnecting:
                self.status_log_message.emit("PRM: Connected")
        except Exception as e:
            self.status_log_message.emit("PRM: Connection failed ({})".format(e))
            self._prm_connection = None
            self._prm_worker.set_prm(None)
            self._prm_connected = False
            self._emit_connection_state_if_changed()
            self.prm_connection_failed.emit(str(e))
        finally:
            self._prm_connecting = False

    def disconnect_prm(self):
        """User-initiated disconnect. Clears state so PRM can be connected again when available."""
        self._prm_position_timer.stop()
        try:
            if self._prm_connection:
                self._prm_connection.disconnect()
        except Exception:
            pass
        self._prm_connection = None
        self._prm_worker.set_prm(None)
        self._prm_connected = False
        self._prm_had_successful_read = False
        self._emit_connection_state_if_changed()
        self.prm_position_updated.emit(None)
        self.status_log_message.emit("PRM: Disconnected")

    def _on_prm_move_completed(self):
        self._poll_prm_position()
        self.prm_command_finished.emit()

    def _on_prm_home_completed(self):
        self._poll_prm_position()
        self.prm_command_finished.emit()

    def _on_prm_op_done(self):
        """Called when move/home thread finishes (same as reference). Poll position and re-enable UI."""
        self._poll_prm_position()
        self.prm_command_finished.emit()

    def prm_move_to(self, angle: Union[float, str], speed_deg_per_sec: Optional[float] = None) -> None:
        """Move PRM to angle (degrees). Same as reference: run in a NEW thread so Stop does not block next command."""
        if not self._prm_connection or not self._prm_connection.is_connected():
            self.status_log_message.emit("PRM: Not connected.")
            self.prm_command_finished.emit()
            return
        if isinstance(angle, str):
            angle_val = float(angle.strip().replace("'", "").replace('"', ""))
        else:
            angle_val = float(angle)
        speed = float(speed_deg_per_sec) if speed_deg_per_sec is not None else 0.0
        threading.Thread(target=_run_prm_move, args=(self, angle_val, speed), daemon=True).start()

    def prm_home(self):
        """Home PRM. Same as reference: run in a NEW thread so Stop does not block next command."""
        if not self._prm_connection or not self._prm_connection.is_connected():
            self.status_log_message.emit("PRM: Not connected.")
            self.prm_command_finished.emit()
            return
        threading.Thread(target=_run_prm_home, args=(self,), daemon=True).start()

    def prm_stop_immediate(self):
        """Stop PRM motion immediately. Same as Tkinter: StopImmediate() or Stop(True)."""
        if not self._prm_connection or not self._prm_connection.is_connected():
            self.status_log_message.emit("PRM: Not connected.")
            self.prm_error.emit("Device is not connected.")
            return
        try:
            self._prm_connection.stop_immediate()
            self.status_log_message.emit("PRM: Stop (immediate).")
        except Exception as e:
            msg = str(e)
            self.status_log_message.emit("PRM: IStop failed: {}".format(msg))
            self.prm_error.emit(msg)

    def prm_stop_smooth(self):
        """Stop PRM motion smoothly. Same as Tkinter: StopProfiled() or Stop(False)."""
        if not self._prm_connection or not self._prm_connection.is_connected():
            self.status_log_message.emit("PRM: Not connected.")
            self.prm_error.emit("Device is not connected.")
            return
        try:
            self._prm_connection.stop_smooth()
            self.status_log_message.emit("PRM: Stop (smooth).")
        except Exception as e:
            msg = str(e)
            self.status_log_message.emit("PRM: Stop failed: {}".format(msg))
            self.prm_error.emit(msg)

    def prm_stop(self):
        """Alias: immediate stop."""
        self.prm_stop_immediate()

    def prm_enable_device(self) -> None:
        """Re-enable the PRM device so it accepts move/home after Stop/IStop. Sends EnableDevice() to instrument."""
        if not self._prm_connection or not self._prm_connection.is_connected():
            self.status_log_message.emit("PRM: Not connected.")
            return
        try:
            self._prm_connection.enable_device()
            self.status_log_message.emit("PRM: Device enabled (ready for move/home).")
        except Exception as e:
            self.status_log_message.emit("PRM: Enable failed: {}.".format(e))
            self.prm_error.emit(str(e))

    def prm_set_velocity(self, velocity_deg_per_sec: float) -> None:
        """Set PRM motor speed (deg/s). Same as Tkinter: SetVelocityParams(Decimal(max_vel), Decimal(accel))."""
        if not self._prm_connection or not self._prm_connection.is_connected():
            self.prm_error.emit("Device is not connected.")
            return
        try:
            self._prm_connection.set_max_velocity(float(velocity_deg_per_sec))
            self.status_log_message.emit("PRM: Speed set to {} °/s.".format(velocity_deg_per_sec))
        except Exception as e:
            msg = str(e)
            self.status_log_message.emit("PRM set velocity failed: {}".format(msg))
            self.prm_error.emit(msg)

    def prm_set_velocity_params(self, acceleration: float, max_velocity_deg_per_sec: float) -> None:
        """Set PRM acceleration and max velocity (deg/s). For internal use; UI uses speed only."""
        if not self._prm_connection or not self._prm_connection.is_connected():
            return
        try:
            self._prm_connection.set_velocity_params(float(acceleration), float(max_velocity_deg_per_sec))
            self.status_log_message.emit("PRM: Speed set to {} °/s.".format(max_velocity_deg_per_sec))
        except Exception as e:
            self.status_log_message.emit("PRM set velocity params failed: {}".format(e))

    def prm_get_velocity(self) -> float:
        """Get PRM motor max velocity (deg/s). Returns 0 if not connected or not supported."""
        if self._prm_connection and self._prm_connection.is_connected():
            try:
                return self._prm_connection.get_max_velocity()
            except Exception:
                pass
        return 0.0

    def prm_get_acceleration(self) -> float:
        """Get PRM acceleration. Returns 0 if not connected or not supported."""
        if self._prm_connection and self._prm_connection.is_connected():
            try:
                return self._prm_connection.get_acceleration()
            except Exception:
                pass
        return 0.0

    def connect_gentec(self, port: str):
        """Connection in separate thread (worker). Accepts any COM string from UI or INI (COMn, \\\\.\\COM10+, quoted)."""
        p = (port or "").strip()
        if len(p) >= 2 and ((p[0] == p[-1] == '"') or (p[0] == p[-1] == "'")):
            p = p[1:-1].strip()
        self._gentec_worker.request_connect.emit(p)

    def disconnect_gentec(self):
        self._gentec_worker.request_disconnect.emit()

    def request_gentec_read(self):
        self._gentec_worker.trigger_read.emit()

    def apply_power_meter_wavelength_nm(self, wavelength_nm: float, *, gentec: bool = True) -> None:
        """
        Send calibration wavelength to powermeter worker threads.
        Manual Control Apply λ: Gentec + Thorlabs (default). Start New: Thorlabs only (gentec=False).
        Uses ThorlabsPowermeterConnection.set_wavelength_nm (SENS:CORR:WAV) / Gentec set_wavelength_nm,
        with force=True so SCPI is always sent.
        """
        try:
            wl = float(wavelength_nm)
        except (TypeError, ValueError):
            return
        if wl <= 0:
            return
        if gentec:
            self._gentec_worker.request_set_wavelength_nm.emit(wl, True)
        self._thorlabs_worker.request_set_wavelength_nm.emit(wl, True)

    def request_powermeter_wavelength_readbacks(self, *, gentec: bool = False) -> None:
        """Query calibration wavelength on worker threads (Thorlabs by default; Gentec optional — no Manual Control UI)."""
        if self._thorlabs_connected:
            self._thorlabs_worker.request_read_wavelength_nm.emit()
        if gentec and self._gentec_connected:
            self._gentec_worker.request_read_wavelength_nm.emit()

    def _on_thorlabs_wavelength_applied(self, ok: bool, wl: float) -> None:
        if ok:
            self.status_log_message.emit("Thorlabs: wavelength set to {:.2f} nm.".format(wl))
        else:
            self.status_log_message.emit(
                "Thorlabs: wavelength command failed for {:.2f} nm — check connection.".format(wl)
            )

    def _on_gentec_wavelength_applied(self, ok: bool, wl: float) -> None:
        if ok:
            self.status_log_message.emit("Gentec: wavelength set to {:.0f} nm (*PWM).".format(wl))
        else:
            self.status_log_message.emit(
                "Gentec: wavelength set failed for {:.0f} nm — check connection.".format(wl)
            )

    def request_thorlabs_read(self):
        self._thorlabs_worker.trigger_read.emit()

    def connect_thorlabs(self, visa_resource: str):
        """Connection in separate thread (worker)."""
        self._thorlabs_worker.request_connect.emit(visa_resource or "")

    def disconnect_thorlabs(self):
        self._thorlabs_worker.request_disconnect.emit()

    def connect_arroyo(self, port: str):
        """Connection in separate thread (worker)."""
        self._poll_timer.stop()
        self._arroyo_connecting = True
        was_connected = self._arroyo_connected
        self._arroyo_reconnect_active = was_connected
        if was_connected:
            self._arroyo_connected = False
            self._emit_connection_state_if_changed()
        self._worker.request_connect.emit(port or "")

    def disconnect_arroyo(self):
        self._poll_timer.stop()
        self._arroyo_connecting = False
        self._arroyo_reconnect_active = False
        self._worker.request_disconnect.emit()

    def set_arroyo_temp(self, value: float):
        self._poll_timer.stop()
        self._worker.request_set_temp.emit(value)
        self._schedule_arroyo_readback_and_resume_poll()

    def set_arroyo_laser_current(self, value_mA: float):
        self._poll_timer.stop()
        self._worker.request_set_laser_current.emit(value_mA)
        self._schedule_arroyo_readback_and_resume_poll()
        self.schedule_power_meter_reads_after_laser_change()

    def set_arroyo_laser_current_limit(self, value_mA: float):
        self._poll_timer.stop()
        self._worker.request_set_laser_current_limit.emit(value_mA)
        self._schedule_arroyo_readback_and_resume_poll()

    def set_arroyo_THI_limit(self, value: float):
        self._poll_timer.stop()
        self._worker.request_set_THI_limit.emit(value)
        self._schedule_arroyo_readback_and_resume_poll()

    def is_arroyo_connected(self) -> bool:
        """True when Arroyo serial session is connected (required before Laser ON). False while reconnect is in progress."""
        return bool(self._arroyo_connected) and not self._arroyo_connecting

    def set_arroyo_laser_output(self, on: bool):
        """Laser ON: TEC on first if needed, then laser on if needed (single worker slot, readback-aware). Laser OFF: laser only."""
        if on and not self._arroyo_connected:
            self.status_log_message.emit(
                "Laser ON blocked: Arroyo is not connected. Connect Arroyo in the Connection tab first."
            )
            return
        self._poll_timer.stop()
        self._worker.request_safe_laser_output.emit(bool(on))
        self._schedule_arroyo_readback_and_resume_poll()
        self.schedule_power_meter_reads_after_laser_change()

    def set_arroyo_tec_output(self, on: bool):
        self._poll_timer.stop()
        self._worker.request_set_output.emit(1 if on else 0)
        self._schedule_arroyo_readback_and_resume_poll()

    def set_ando_center_wl(self, value: float):
        self._ando_worker.request_set_center_wl.emit(value)

    def set_ando_span(self, value: float):
        self._ando_worker.request_set_span.emit(value)

    def set_ando_ref_level(self, value: float):
        self._ando_worker.request_set_ref_level.emit(value)

    def set_ando_log_scale(self, value: float):
        self._ando_worker.request_set_log_scale.emit(value)

    def set_ando_resolution(self, value: float):
        self._ando_worker.request_set_resolution.emit(value)

    def set_ando_sensitivity_index(self, index: int):
        self._ando_worker.request_set_sensitivity_index.emit(index)

    def set_ando_sampling_points(self, points: int):
        self._ando_worker.request_set_sampling_points.emit(points)

    def set_ando_analysis_dfb_ld(self):
        self._ando_worker.request_analysis_dfb_ld.emit()

    def set_ando_analysis_led(self):
        self._ando_worker.request_analysis_led.emit()

    def set_ando_sweep_auto(self):
        self._ando_worker.request_sweep_auto.emit()

    def set_ando_sweep_single(self):
        self._ando_worker.request_sweep_single.emit()

    def set_ando_sweep_repeat(self):
        self._ando_worker.request_sweep_repeat.emit()

    def set_ando_sweep_stop(self):
        self._ando_worker.request_sweep_stop.emit()

    def actuator_move_a(self, distance_mm: float):
        self._actuator_worker.request_move_a.emit(float(distance_mm))

    def actuator_move_b(self, distance_mm: float):
        self._actuator_worker.request_move_b.emit(float(distance_mm))

    def actuator_home_a(self):
        self._actuator_worker.request_home_a.emit()

    def actuator_home_b(self):
        self._actuator_worker.request_home_b.emit()

    def actuator_home_both(self):
        self._actuator_worker.request_home_both.emit()

    @pyqtSlot(list)
    def append_instrument_info_prm_line(self, lines):
        """Info menu: PRM uses Thorlabs Kinesis on the GUI thread (no SCPI *IDN)."""
        try:
            prm = self._prm_connection
            if prm and getattr(prm, "is_connected", lambda: False)():
                sn = getattr(prm, "serial_number", None) or "?"
                try:
                    pos = prm.get_position()
                except Exception:
                    pos = None
                pos_s = "{:.4f}".format(float(pos)) if pos is not None else "n/a"
                lines.append(
                    "PRM (Kinesis / rotation mount): serial {} — connected; position {}° (hardware API, not *IDN?)".format(
                        sn, pos_s
                    )
                )
            else:
                lines.append("PRM: (not connected)")
        except Exception as e:
            lines.append("PRM: Error — {}".format(e))

    def shutdown(self):
        if self._shutdown_done:
            return
        self._shutdown_done = True
        self._poll_timer.stop()
        # Arroyo serial must only be touched on the Arroyo worker thread (same as laser/TEC GUI actions).
        # Calling laser_set_output / set_output from the GUI thread during poll can race and mis-command
        # the unit (outputs can appear to turn ON or commands are lost).
        try:
            w = getattr(self, "_worker", None)
            if w is not None:
                QMetaObject.invokeMethod(
                    w,
                    "laser_tec_shutdown_for_quit",
                    Qt.BlockingQueuedConnection,
                )
        except Exception:
            pass
        self._poll_timer.stop()
        self._ando_poll_timer.stop()
        self._actuator_poll_timer.stop()
        self._wavemeter_poll_timer.stop()
        self._gentec_poll_timer.stop()
        self._thorlabs_poll_timer.stop()
        self._prm_position_timer.stop()
        self._worker.request_disconnect.emit()
        self._ando_worker.request_disconnect.emit()
        self._actuator_worker.request_disconnect.emit()
        self._wavemeter_worker.request_disconnect.emit()
        self._gentec_worker.request_disconnect.emit()
        self._thorlabs_worker.request_disconnect.emit()
        try:
            if self._prm_connection:
                self._prm_connection.disconnect()
        except Exception:
            pass
        self._prm_connection = None
        self._prm_worker.set_prm(None)
        self._prm_worker.request_disconnect.emit()
        self._thread.quit()
        self._ando_thread.quit()
        self._actuator_thread.quit()
        self._wavemeter_thread.quit()
        self._gentec_thread.quit()
        self._thorlabs_thread.quit()
        self._prm_thread.quit()
        self._thread.wait(2000)
        self._ando_thread.wait(2000)
        self._actuator_thread.wait(2000)
        self._wavemeter_thread.wait(2000)
        self._gentec_thread.wait(2000)
        self._thorlabs_thread.wait(2000)
        self._prm_thread.wait(2000)
