"""
Main ViewModel: exposes data and commands to the View.
Connection (connect/disconnect) uses separate worker threads so UI does not block.
PRM move/home: run in separate threads (same as reference Tkinter) so Stop does not block next Home/Move.
"""
import os
import time
import configparser
import threading

from PyQt5.QtCore import QObject, QThread, pyqtSignal, QTimer
from PyQt5.QtWidgets import QApplication

from instruments import connection as conn
from instruments.connection import PRMConnection
from instruments.instrument_simulations import PRMSimulationConnection
from instruments.simulation_config import (
    simulate_actuator_enabled,
    simulate_ando_enabled,
    simulate_arroyo_enabled,
    simulate_gentec_enabled,
    simulate_prm_enabled,
    simulate_thorlabs_enabled,
    simulate_wavemeter_enabled,
)
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
    wavemeter_wavelength_updated = pyqtSignal(object)  # float (nm) or None
    wavemeter_range_applied = pyqtSignal(bool, str)  # success, range_str
    prm_position_updated = pyqtSignal(object)  # float or None
    prm_connection_failed = pyqtSignal(str)  # error message when PRM connect fails
    prm_error = pyqtSignal(str)  # error message for PRM speed/stop (show dialog like Tkinter messagebox)
    prm_command_finished = pyqtSignal()  # move/home subprocess finished (re-enable PRM buttons)
    _prm_op_done = pyqtSignal()  # emitted from background thread when move/home finishes (triggers poll + command_finished)
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
        self._gentec_connected = False
        self._thorlabs_connected = False

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

        self._thorlabs_thread = QThread(self)
        self._thorlabs_worker = ThorlabsPowermeterWorker()
        self._thorlabs_worker.moveToThread(self._thorlabs_thread)
        self._thorlabs_thread.start()
        self._thorlabs_worker.connection_state_changed.connect(self._on_thorlabs_connection_changed)
        self._thorlabs_worker.reading_ready.connect(self._on_thorlabs_reading_ready)

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

    def start_workers(self):
        """After UI is up, auto-connect any instrument slots that use simulation (SIM) so footer shows Connected (simulation)."""
        QTimer.singleShot(0, self.auto_connect_simulated_instruments)

    def auto_connect_simulated_instruments(self) -> None:
        """
        Connect software simulators automatically when simulation is enabled for that slot.
        Real PRM / Gentec / Thorlabs are skipped unless their simulate_* flag is on (e.g. simulate_all).
        """
        try:
            if simulate_arroyo_enabled() and not self._arroyo_connected:
                self.connect_arroyo("SIM")
            if simulate_actuator_enabled() and not self._actuator_connected:
                self.connect_actuator("SIM")
            if simulate_ando_enabled() and not self._ando_connected:
                self.connect_ando("SIM")
            if simulate_wavemeter_enabled() and not self._wavemeter_connected:
                self.connect_wavemeter("SIM")
            if simulate_gentec_enabled() and not self._gentec_connected:
                self.connect_gentec("SIM")
            if simulate_thorlabs_enabled() and not self._thorlabs_connected:
                self.connect_thorlabs("SIM::VISA")
            if simulate_prm_enabled() and not self._prm_connected:
                self.connect_prm("SIM", reconnecting=False)
        except Exception:
            pass

    def _on_arroyo_connection_result(self, ok: bool):
        self._arroyo_connecting = False
        self._arroyo_connected = ok
        self.connection_state_changed.emit(self.get_connection_state())
        if ok:
            a = getattr(self._worker, "_arroyo", None)
            _sim = bool(getattr(a, "is_simulation", False))
            self.status_log_message.emit(
                "Arroyo: Connected (simulation)" if _sim else "Arroyo: Connected"
            )
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
            self._poll_timer.stop()
            self.connection_state_changed.emit(self.get_connection_state())

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
        self.connection_state_changed.emit(self.get_connection_state())
        ando = getattr(self._ando_worker, "_ando", None)
        _sim = bool(getattr(ando, "is_simulation", False))
        if self._ando_connected:
            self.status_log_message.emit(
                "Ando: Connected (simulation)" if _sim else "Ando: Connected"
            )
        else:
            self.status_log_message.emit("Ando: Disconnected")

    def _on_actuator_connection_changed(self, state: dict):
        if "Actuator" in state:
            self._actuator_connected = state.get("Actuator", False)
        if self._actuator_connected:
            self._actuator_poll_timer.start()
            self._request_actuator_ping()
        else:
            self._actuator_poll_timer.stop()
        self.connection_state_changed.emit(self.get_connection_state())
        act = getattr(self._actuator_worker, "_actuator", None)
        _asim = bool(getattr(act, "is_simulation", False))
        if self._actuator_connected:
            self.status_log_message.emit(
                "Actuator: Connected (simulation)" if _asim else "Actuator: Connected"
            )
        else:
            self.status_log_message.emit("Actuator: Disconnected")

    def _on_wavemeter_connection_changed(self, state: dict):
        # Only update our state when this dict is for Wavemeter (avoids cross-talk if signal were miswired)
        if "Wavemeter" in state:
            self._wavemeter_connected = state.get("Wavemeter", False)
        error_msg = state.get("Wavemeter_error")
        self.connection_state_changed.emit(self.get_connection_state())
        if self._wavemeter_connected:
            wm = getattr(self._wavemeter_worker, "_wavemeter", None)
            _wsim = bool(getattr(wm, "is_simulation", False))
            self.status_log_message.emit(
                "Wavemeter: Connected (simulation)" if _wsim else "Wavemeter: Connected"
            )
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
        self.connection_state_changed.emit(self.get_connection_state())
        g = getattr(self._gentec_worker, "_gentec", None)
        _gsim = bool(getattr(g, "is_simulation", False))
        if self._gentec_connected:
            self.status_log_message.emit(
                "Gentec: Connected (simulation)" if _gsim else "Gentec: Connected"
            )
        else:
            self.status_log_message.emit("Gentec: Disconnected")
        if self._gentec_connected:
            self._gentec_poll_timer.start()
            self._request_gentec_read()
        else:
            self._gentec_poll_timer.stop()

    def _on_gentec_reading_ready(self, value_mw):
        self.gentec_reading_updated.emit(value_mw)

    def _on_thorlabs_connection_changed(self, state: dict):
        # Only update our state when this dict is for Thorlabs (avoids cross-talk e.g. Wavemeter disconnect affecting Thorlabs)
        if "Thorlabs" in state:
            self._thorlabs_connected = state.get("Thorlabs", False)
        self.connection_state_changed.emit(self.get_connection_state())
        t = getattr(self._thorlabs_worker, "_thorlabs", None)
        _tsim = bool(getattr(t, "is_simulation", False))
        err = state.get("Thorlabs_error") if isinstance(state, dict) else None
        if self._thorlabs_connected:
            self.status_log_message.emit(
                "Thorlabs: Connected (simulation)" if _tsim else "Thorlabs: Connected"
            )
        else:
            if err:
                self.status_log_message.emit("Thorlabs: Connection failed — {}".format(err))
            else:
                self.status_log_message.emit("Thorlabs: Disconnected")
        if self._thorlabs_connected:
            self._thorlabs_poll_timer.start()
            self._request_thorlabs_read()
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
            self.connection_state_changed.emit(self.get_connection_state())

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
                self.connection_state_changed.emit(self.get_connection_state())
                self.status_log_message.emit("PRM: Disconnected (device turned off or unplugged)")
            self.prm_position_updated.emit(None)

    def get_connection_state(self):
        return {
            "Arroyo": self._arroyo_connected,
            "Ando": self._ando_connected,
            "Actuator": self._actuator_connected,
            "Wavemeter": self._wavemeter_connected,
            "PRM": self._prm_connected,
            "Gentec": self._gentec_connected,
            "Thorlabs": self._thorlabs_connected,
        }

    def is_instrument_simulated(self, key: str) -> bool:
        """
        True if this slot uses a simulator — UI shows '(simulation)' next to the name.
        When connected, uses the live object; when disconnected, uses simulation config
        (e.g. simulate_except_measurement: real PRM, Gentec, Thorlabs only).
        """
        k = (key or "").strip()
        if k == "Arroyo":
            o = getattr(self._worker, "_arroyo", None)
            if o is not None and getattr(o, "is_connected", lambda: False)():
                return bool(getattr(o, "is_simulation", False))
            return simulate_arroyo_enabled()
        if k == "Actuator":
            o = getattr(self._actuator_worker, "_actuator", None)
            if o is not None and getattr(o, "is_connected", lambda: False)():
                return bool(getattr(o, "is_simulation", False))
            return simulate_actuator_enabled()
        if k == "Ando":
            o = getattr(self._ando_worker, "_ando", None)
            if o is not None and getattr(o, "is_connected", lambda: False)():
                return bool(getattr(o, "is_simulation", False))
            return simulate_ando_enabled()
        if k == "Wavemeter":
            o = getattr(self._wavemeter_worker, "_wavemeter", None)
            if o is not None and getattr(o, "is_connected", lambda: False)():
                return bool(getattr(o, "is_simulation", False))
            return simulate_wavemeter_enabled()
        if k == "PRM":
            c = getattr(self, "_prm_connection", None)
            if c is not None and getattr(c, "is_connected", lambda: False)():
                return bool(getattr(c, "is_simulation", False))
            return simulate_prm_enabled()
        if k == "Gentec":
            o = getattr(self._gentec_worker, "_gentec", None)
            if o is not None and getattr(o, "is_connected", lambda: False)():
                return bool(getattr(o, "is_simulation", False))
            return simulate_gentec_enabled()
        if k == "Thorlabs":
            o = getattr(self._thorlabs_worker, "_thorlabs", None)
            if o is not None and getattr(o, "is_connected", lambda: False)():
                return bool(getattr(o, "is_simulation", False))
            return simulate_thorlabs_enabled()
        return False

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
            self.status_log_message.emit("Connection: VISA scan timeout, continuing without VISA list.")
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
            self.status_log_message.emit("Connection: Thorlabs VISA scan timeout, continuing without list.")
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
        """Instruments folder (for instrument_config.ini and saved_connections.ini)."""
        return os.path.dirname(os.path.abspath(conn.__file__))

    def _saved_connections_path(self):
        """Path to saved_connections.ini in instruments folder."""
        return os.path.join(self._instruments_dir(), "saved_connections.ini")

    def _instrument_config_path(self):
        """Path to instrument_config.ini in instruments folder."""
        return os.path.join(self._instruments_dir(), "instrument_config.ini")

    def save_connection_addresses(self, addresses: dict):
        """Save current addresses to file. Keys: arroyo_port, actuator_port, ando_gpib, wavemeter_gpib, prm_serial, gentec_port, thorlabs_visa, auto_connect."""
        path = self._saved_connections_path()
        cfg = configparser.ConfigParser()
        cfg["saved"] = {k: (str(v).strip() if v else "") for k, v in addresses.items()}
        try:
            with open(path, "w") as f:
                cfg.write(f)
        except Exception:
            pass

    def load_saved_addresses(self) -> dict:
        """Load all connection addresses: defaults, then instrument_config.ini (all sections), then saved_connections.ini. So addresses from file show correctly."""
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
        # 1) Load from instrument_config.ini (single file for all connection settings)
        config_path = self._instrument_config_path()
        if os.path.exists(config_path):
            try:
                cfg = configparser.ConfigParser()
                cfg.read(config_path)
                # [Connection] section: arroyo_port, actuator_port, ando_gpib, wavemeter_gpib, prm_serial, gentec_port, thorlabs_visa
                if cfg.has_section("Connection"):
                    for k in ("arroyo_port", "actuator_port", "ando_gpib", "wavemeter_gpib", "prm_serial", "gentec_port", "thorlabs_visa"):
                        if cfg.has_option("Connection", k):
                            defaults[k] = cfg.get("Connection", k).strip()
                # Per-instrument sections (override if present)
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
        # 2) Override with saved_connections.ini (UI Save button)
        path = self._saved_connections_path()
        if os.path.exists(path):
            try:
                cfg = configparser.ConfigParser()
                cfg.read(path)
                if cfg.has_section("saved"):
                    for k in defaults:
                        if cfg.has_option("saved", k):
                            defaults[k] = cfg.get("saved", k).strip()
            except Exception:
                pass
        return defaults

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
        sim_prm = simulate_prm_enabled()
        if sim_prm:
            if not serial_number or serial_number.lower().startswith("(no ") or "not found" in serial_number.lower():
                serial_number = "SIM"
        elif not serial_number or serial_number.lower().startswith("(no ") or "not found" in serial_number.lower():
            self._prm_connected = False
            self.connection_state_changed.emit(self.get_connection_state())
            return
        # Already connected to this serial: skip (avoids duplicate connect messages when Connect All / auto-connect runs multiple times)
        if not reconnecting and self._prm_connected and self._prm_connection and (self._prm_connection.serial_number or "").strip() == serial_number:
            return
        self._prm_position_timer.stop()
        if self._prm_connection:
            try:
                self._prm_connection.disconnect()
            except Exception:
                pass
            self._prm_connection = None
        self._prm_worker.set_prm(None)
        try:
            if not reconnecting:
                self.status_log_message.emit("[PRM] Connecting to serial: {}".format(serial_number))
            # Keep PRM status concise in GUI log (avoid duplicate "Connected" lines).
            status_callback = None
            if sim_prm:
                self._prm_connection = PRMSimulationConnection(serial_number)
            else:
                self._prm_connection = PRMConnection(serial_number)
            self._prm_connection.connect(status_log=status_callback, verbose=False)
            self._prm_worker.set_prm(self._prm_connection)
            self._prm_connected = True
            self._prm_had_successful_read = False
            state = self.get_connection_state()
            self.connection_state_changed.emit(state)
            # Emit again after event loop processes so footer/UI reliably shows PRM Connected
            QTimer.singleShot(0, lambda: self.connection_state_changed.emit(self.get_connection_state()))
            self._prm_position_timer.start()
            self._poll_prm_position()
            if not reconnecting:
                _psim = bool(getattr(self._prm_connection, "is_simulation", False))
                if _psim:
                    self.status_log_message.emit("PRM: Connected (simulation)")
                else:
                    try:
                        pos = self._prm_connection.get_position()
                        self.status_log_message.emit(
                            "PRM: Connected — Kinesis OK, serial {}, position {:.3f} °".format(
                                serial_number, float(pos) if pos is not None else 0.0
                            )
                        )
                    except Exception:
                        self.status_log_message.emit(
                            "PRM: Connected — Kinesis OK, serial {}".format(serial_number)
                        )
        except Exception as e:
            self.status_log_message.emit("PRM: Connection failed ({})".format(e))
            self._prm_connection = None
            self._prm_worker.set_prm(None)
            self._prm_connected = False
            self.connection_state_changed.emit(self.get_connection_state())
            self.prm_connection_failed.emit(str(e))

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
        self.connection_state_changed.emit(self.get_connection_state())
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

    def prm_move_to(self, angle: float, speed_deg_per_sec: float = None):
        """Move PRM to angle (degrees). Same as reference: run in a NEW thread so Stop does not block next command."""
        if not self._prm_connection or not self._prm_connection.is_connected():
            self.status_log_message.emit("PRM: Not connected.")
            self.prm_command_finished.emit()
            return
        if isinstance(angle, str):
            angle = angle.strip().replace("'", "").replace('"', "")
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
        """Connection in separate thread (worker)."""
        self._gentec_worker.request_connect.emit(port or "")

    def disconnect_gentec(self):
        self._gentec_worker.request_disconnect.emit()

    def request_gentec_read(self):
        self._gentec_worker.trigger_read.emit()

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
        self._arroyo_connected = False
        if was_connected:
            self.connection_state_changed.emit(self.get_connection_state())
        self._worker.request_connect.emit(port or "")

    def disconnect_arroyo(self):
        self._poll_timer.stop()
        self._arroyo_connecting = False
        self._worker.request_disconnect.emit()

    def set_arroyo_temp(self, value: float):
        self._worker.request_set_temp.emit(value)

    def set_arroyo_laser_current(self, value_mA: float):
        self._worker.request_set_laser_current.emit(value_mA)

    def set_arroyo_laser_current_limit(self, value_mA: float):
        self._worker.request_set_laser_current_limit.emit(value_mA)

    def set_arroyo_THI_limit(self, value: float):
        self._worker.request_set_THI_limit.emit(value)

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
        self._worker.request_safe_laser_output.emit(bool(on))
        self.schedule_arroyo_readback_refresh()

    def set_arroyo_tec_output(self, on: bool):
        self._worker.request_set_output.emit(1 if on else 0)
        self.schedule_arroyo_readback_refresh()

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

    def shutdown(self):
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
