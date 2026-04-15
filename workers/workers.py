"""
All instrument workers in one module. Run in QThread; use instruments.connection for I/O.
"""
import time
from typing import Any, Dict, Optional

from PyQt5.QtCore import QObject, QTimer, pyqtSignal, pyqtSlot

from instruments.actuator import ACTUATOR_ESTIMATE_HOME_BOTH_SEC, ACTUATOR_ESTIMATE_HOME_SINGLE_SEC
from instruments.connection import (
    ArroyoConnection,
    ActuatorConnection,
    AndoConnection,
    GentecConnection,
    GenericComConnection,
    GenericGpibConnection,
    GenericVisaConnection,
    ThorlabsPowermeterConnection,
    WavemeterConnection,
)


# ----- ArroyoWorker -----
class ArroyoWorker(QObject):
    connection_result = pyqtSignal(bool)
    connection_state_changed = pyqtSignal(dict)
    readings_ready = pyqtSignal(dict)
    trigger_read = pyqtSignal()
    request_connect = pyqtSignal(str)
    request_disconnect = pyqtSignal()
    request_set_temp = pyqtSignal(float)
    request_set_laser_current = pyqtSignal(float)
    request_set_laser_current_limit = pyqtSignal(float)
    request_set_THI_limit = pyqtSignal(float)
    request_laser_set_output = pyqtSignal(int)
    request_set_output = pyqtSignal(int)
    # Laser ON: TEC output first (if not already on), brief wait, then laser (if not already on).
    request_safe_laser_output = pyqtSignal(bool)

    def __init__(self, parent=None):
        super(ArroyoWorker, self).__init__(parent)
        self._arroyo = None
        self.trigger_read.connect(self.read_all)
        self.request_connect.connect(self.do_connect)
        self.request_disconnect.connect(self.do_disconnect)
        self.request_set_temp.connect(self.set_temp)
        self.request_set_laser_current.connect(self.set_laser_current)
        self.request_set_laser_current_limit.connect(self.set_laser_current_limit)
        self.request_set_THI_limit.connect(self.set_THI_limit)
        self.request_laser_set_output.connect(self.laser_set_output)
        self.request_set_output.connect(self.set_output)
        self.request_safe_laser_output.connect(self.safe_laser_output)

    @pyqtSlot()
    def laser_tec_shutdown_for_quit(self) -> None:
        """
        App exit: turn **laser output OFF** then **TEC output OFF** on the worker thread only.

        MainWindow/ViewModel must not call ``ArroyoConnection`` directly — serial is shared with
        ``read_all`` polling on this thread; cross-thread writes can race and mis-command hardware.
        """
        if not self._arroyo or not self._arroyo.is_connected():
            return
        try:
            self._arroyo.laser_set_output(0)
        except Exception:
            pass
        time.sleep(0.25)
        try:
            self._arroyo.set_output(0)
        except Exception:
            pass
        time.sleep(0.15)

    @pyqtSlot(str)
    def do_connect(self, port: str):
        port = (port or "").strip()
        if not port:
            self.connection_result.emit(False)
            self.connection_state_changed.emit({"Arroyo": False})
            return
        try:
            if self._arroyo:
                try:
                    self._arroyo.disconnect()
                except Exception:
                    pass
                self._arroyo = None
            time.sleep(0.35)
            self._arroyo = ArroyoConnection(port=port)
            ok = self._arroyo.connect()
            self.connection_result.emit(ok)
            self.connection_state_changed.emit({"Arroyo": ok})
        except Exception:
            self._arroyo = None
            self.connection_result.emit(False)
            self.connection_state_changed.emit({"Arroyo": False})

    @pyqtSlot()
    def do_disconnect(self):
        try:
            if self._arroyo:
                self._arroyo.disconnect()
                self._arroyo = None
        except Exception:
            pass
        self.connection_result.emit(False)
        self.connection_state_changed.emit({"Arroyo": False})

    @pyqtSlot()
    def read_all(self):
        out: Dict[str, Any] = {
            "actual_current": None,
            "actual_temp": None,
            "max_current": None,
            "max_temp": None,
            # None = query failed this poll; do not force UI to OFF (avoids TEC/Laser flicker).
            "laser_on": None,
            "tec_on": None,
            "laser_current": None,
            "laser_voltage": None,
            "laser_set_current": None,
            "tec_current": None,
            "tec_voltage": None,
            "tec_temp": None,
            "tec_set_temp": None,
        }
        if not self._arroyo or not self._arroyo.is_connected():
            out["laser_on"] = False
            out["tec_on"] = False
            self.readings_ready.emit(out)
            return
        a = self._arroyo

        def _safe(callable_fn):
            try:
                return callable_fn()
            except Exception:
                return None

        # Per-query isolation: a failing laser SCPI query must not wipe TEC readbacks or disconnect.
        out["laser_current"] = _safe(a.laser_read_current)
        out["laser_voltage"] = _safe(a.laser_read_voltage)
        out["laser_set_current"] = _safe(a.laser_read_set_current)
        out["tec_current"] = _safe(a.read_current)
        out["tec_temp"] = _safe(a.read_temp)
        out["tec_set_temp"] = _safe(a.read_set_temp)
        try:
            tec_v = a.query("TEC:V?")
            out["tec_voltage"] = float(tec_v) if tec_v is not None else None
        except Exception:
            out["tec_voltage"] = None
        out["actual_current"] = out["laser_current"]
        out["actual_temp"] = out["tec_temp"]
        out["max_current"] = _safe(a.laser_read_current_limit)
        out["max_temp"] = _safe(a.read_THI_limit)
        lo = _safe(a.laser_read_output)
        out["laser_on"] = (lo == 1) if lo is not None else None
        to = _safe(a.read_output)
        out["tec_on"] = (to == 1) if to is not None else None

        self.readings_ready.emit(out)

    @pyqtSlot(float)
    def set_temp(self, value: float):
        if self._arroyo and self._arroyo.is_connected():
            try:
                self._arroyo.set_temp(value)
            except Exception:
                pass

    @pyqtSlot(float)
    def set_laser_current(self, value_mA: float):
        if self._arroyo and self._arroyo.is_connected():
            try:
                self._arroyo.laser_set_current(value_mA)
            except Exception:
                pass

    @pyqtSlot(float)
    def set_laser_current_limit(self, value_mA: float):
        if self._arroyo and self._arroyo.is_connected():
            try:
                self._arroyo.laser_set_current_limit(value_mA)
            except Exception:
                pass

    @pyqtSlot(float)
    def set_THI_limit(self, value: float):
        if self._arroyo and self._arroyo.is_connected():
            try:
                self._arroyo.set_THI_limit(value)
            except Exception:
                pass

    @pyqtSlot(int)
    def laser_set_output(self, value: int):
        if self._arroyo and self._arroyo.is_connected():
            try:
                self._arroyo.laser_set_output(1 if value else 0)
            except Exception:
                pass

    @pyqtSlot(int)
    def set_output(self, value: int):
        if self._arroyo and self._arroyo.is_connected():
            try:
                self._arroyo.set_output(1 if value else 0)
            except Exception:
                pass

    @pyqtSlot(bool)
    def safe_laser_output(self, on: bool):
        """
        GUI / global rule: Laser ON => TEC output ON first, then laser output ON.
        If TEC or laser is already ON, skip that step (no redundant toggles).
        Laser OFF => laser output only (does not turn TEC off).
        """
        if not self._arroyo or not self._arroyo.is_connected():
            return
        try:
            if on:
                tec_on = None
                try:
                    tec_on = self._arroyo.read_output()
                except Exception:
                    tec_on = None
                if tec_on != 1:
                    self._arroyo.set_output(1)
                    time.sleep(0.10)
                las_on = None
                try:
                    las_on = self._arroyo.laser_read_output()
                except Exception:
                    las_on = None
                if las_on != 1:
                    self._arroyo.laser_set_output(1)
            else:
                self._arroyo.laser_set_output(0)
        except Exception:
            pass

    @pyqtSlot(list)
    def append_instrument_info_line(self, lines):
        """Info menu: append one *IDN? line for Arroyo (must run on Arroyo worker thread)."""
        try:
            if self._arroyo and self._arroyo.is_connected():
                idn = self._arroyo.identify()
                lines.append("Arroyo (*IDN?): {}".format((idn or "").strip()))
            else:
                lines.append("Arroyo: (not connected)")
        except Exception as e:
            lines.append("Arroyo: Error — {}".format(e))


# ----- AndoWorker -----
class AndoWorker(QObject):
    connection_result = pyqtSignal(bool)
    connection_state_changed = pyqtSignal(dict)
    sweep_status_updated = pyqtSignal(bool)  # True = sweeping, False = idle/stopped
    request_connect = pyqtSignal(str)
    request_disconnect = pyqtSignal()
    request_set_center_wl = pyqtSignal(float)
    request_set_span = pyqtSignal(float)
    request_set_ref_level = pyqtSignal(float)
    request_set_log_scale = pyqtSignal(float)
    request_set_resolution = pyqtSignal(float)
    request_set_sensitivity_index = pyqtSignal(int)
    request_set_sampling_points = pyqtSignal(int)
    request_analysis_dfb_ld = pyqtSignal()
    request_analysis_led = pyqtSignal()
    request_sweep_auto = pyqtSignal()
    request_sweep_single = pyqtSignal()
    request_sweep_repeat = pyqtSignal()
    request_sweep_stop = pyqtSignal()
    trigger_ping = pyqtSignal()

    def __init__(self, parent=None):
        super(AndoWorker, self).__init__(parent)
        self._ando: Optional[AndoConnection] = None
        self.request_connect.connect(self.do_connect)
        self.request_disconnect.connect(self.do_disconnect)
        self.trigger_ping.connect(self.do_ping)
        self.request_set_center_wl.connect(self.set_center_wl)
        self.request_set_span.connect(self.set_span)
        self.request_set_ref_level.connect(self.set_ref_level)
        self.request_set_log_scale.connect(self.set_log_scale)
        self.request_set_resolution.connect(self.set_resolution)
        self.request_set_sensitivity_index.connect(self.set_sensitivity_index)
        self.request_set_sampling_points.connect(self.set_sampling_points)
        self.request_analysis_dfb_ld.connect(self.analysis_dfb_ld)
        self.request_analysis_led.connect(self.analysis_led)
        self.request_sweep_auto.connect(self.sweep_auto)
        self.request_sweep_single.connect(self.sweep_single)
        self.request_sweep_repeat.connect(self.sweep_repeat)
        self.request_sweep_stop.connect(self.sweep_stop)

    @pyqtSlot(str)
    def do_connect(self, gpib_address: str):
        gpib_address = (gpib_address or "").strip()
        if not gpib_address:
            self.connection_result.emit(False)
            self.connection_state_changed.emit({"Ando": False})
            return
        try:
            if self._ando and self._ando.is_connected():
                self._ando.disconnect()
            self._ando = AndoConnection(address=gpib_address)
            ok = self._ando.connect()
            self.connection_result.emit(ok)
            self.connection_state_changed.emit({"Ando": ok})
        except Exception:
            self._ando = None
            self.connection_result.emit(False)
            self.connection_state_changed.emit({"Ando": False})

    @pyqtSlot()
    def do_disconnect(self):
        try:
            if self._ando:
                self._ando.disconnect()
                self._ando = None
        except Exception:
            pass
        self.connection_result.emit(False)
        self.connection_state_changed.emit({"Ando": False})

    def _connected(self):
        return self._ando and self._ando.is_connected()

    @pyqtSlot()
    def do_ping(self):
        """Connection check + sweep status poll so GUI Stop button tracks instrument state."""
        if not self._ando or not self._ando.is_connected():
            return
        try:
            self._ando.identify()
            try:
                done = self._ando.is_sweep_done()
                self.sweep_status_updated.emit(not done)
            except Exception:
                pass
        except Exception:
            try:
                if self._ando:
                    self._ando.disconnect()
            except Exception:
                pass
            self._ando = None
            self.connection_state_changed.emit({"Ando": False})

    @pyqtSlot(float)
    def set_center_wl(self, value: float):
        ando = self._ando
        if not ando or not ando.is_connected():
            return
        try:
            ando.set_center_wl(value)
        except Exception:
            try:
                ando.disconnect()
            except Exception:
                pass
            self._ando = None
            self.connection_state_changed.emit({"Ando": False})

    @pyqtSlot(float)
    def set_span(self, value: float):
        ando = self._ando
        if not ando or not ando.is_connected():
            return
        try:
            ando.set_span(value)
        except Exception:
            try:
                ando.disconnect()
            except Exception:
                pass
            self._ando = None
            self.connection_state_changed.emit({"Ando": False})

    @pyqtSlot(float)
    def set_ref_level(self, value: float):
        ando = self._ando
        if not ando or not ando.is_connected():
            return
        try:
            ando.set_ref_level(value)
        except Exception:
            try:
                ando.disconnect()
            except Exception:
                pass
            self._ando = None
            self.connection_state_changed.emit({"Ando": False})

    @pyqtSlot(float)
    def set_log_scale(self, value: float):
        ando = self._ando
        if not ando or not ando.is_connected():
            return
        try:
            ando.set_log_scale(value)
        except Exception:
            try:
                ando.disconnect()
            except Exception:
                pass
            self._ando = None
            self.connection_state_changed.emit({"Ando": False})

    @pyqtSlot(float)
    def set_resolution(self, value: float):
        ando = self._ando
        if not ando or not ando.is_connected():
            return
        try:
            ando.set_resolution(value)
        except Exception:
            try:
                ando.disconnect()
            except Exception:
                pass
            self._ando = None
            self.connection_state_changed.emit({"Ando": False})

    @pyqtSlot(int)
    def set_sensitivity_index(self, index: int):
        ando = self._ando
        if not ando or not ando.is_connected():
            return
        try:
            ando.set_sensitivity_index(index)
        except Exception:
            try:
                ando.disconnect()
            except Exception:
                pass
            self._ando = None
            self.connection_state_changed.emit({"Ando": False})

    @pyqtSlot(int)
    def set_sampling_points(self, points: int):
        ando = self._ando
        if not ando or not ando.is_connected():
            return
        try:
            ando.set_sampling_points(points)
        except Exception:
            try:
                ando.disconnect()
            except Exception:
                pass
            self._ando = None
            self.connection_state_changed.emit({"Ando": False})

    @pyqtSlot()
    def analysis_dfb_ld(self):
        ando = self._ando
        if not ando or not ando.is_connected():
            return
        try:
            ando.analysis_dfb_ld()
        except Exception:
            try:
                ando.disconnect()
            except Exception:
                pass
            self._ando = None
            self.connection_state_changed.emit({"Ando": False})

    @pyqtSlot()
    def analysis_led(self):
        ando = self._ando
        if not ando or not ando.is_connected():
            return
        try:
            ando.analysis_led()
        except Exception:
            try:
                ando.disconnect()
            except Exception:
                pass
            self._ando = None
            self.connection_state_changed.emit({"Ando": False})

    @pyqtSlot()
    def sweep_auto(self):
        ando = self._ando
        if not ando or not ando.is_connected():
            return
        try:
            ando.sweep_auto()
        except Exception:
            try:
                ando.disconnect()
            except Exception:
                pass
            self._ando = None
            self.connection_state_changed.emit({"Ando": False})

    @pyqtSlot()
    def sweep_single(self):
        ando = self._ando
        if not ando or not ando.is_connected():
            return
        try:
            ando.sweep_single()
        except Exception:
            try:
                ando.disconnect()
            except Exception:
                pass
            self._ando = None
            self.connection_state_changed.emit({"Ando": False})

    @pyqtSlot()
    def sweep_repeat(self):
        ando = self._ando
        if not ando or not ando.is_connected():
            return
        try:
            ando.sweep_repeat()
        except Exception:
            try:
                ando.disconnect()
            except Exception:
                pass
            self._ando = None
            self.connection_state_changed.emit({"Ando": False})

    @pyqtSlot()
    def sweep_stop(self):
        ando = self._ando
        if not ando or not ando.is_connected():
            return
        try:
            ando.sweep_stop()
        except Exception:
            try:
                ando.disconnect()
            except Exception:
                pass
            self._ando = None
            self.connection_state_changed.emit({"Ando": False})

    @pyqtSlot(list)
    def append_instrument_info_line(self, lines):
        """Info menu: append *IDN? for Ando OSA (must run on Ando worker thread)."""
        try:
            if self._ando and self._ando.is_connected():
                idn = self._ando.identify()
                lines.append("Ando (*IDN?): {}".format((idn or "").strip()))
            else:
                lines.append("Ando: (not connected)")
        except Exception as e:
            lines.append("Ando: Error — {}".format(e))


# ----- ActuatorWorker -----
class ActuatorWorker(QObject):
    connection_result = pyqtSignal(bool)
    connection_state_changed = pyqtSignal(dict)
    command_log = pyqtSignal(str)  # manual move/home feedback for status log
    # One line for Manual Control actuator bar: "A: …  |  B: …"
    actuator_status_line = pyqtSignal(str)
    request_connect = pyqtSignal(str)
    request_disconnect = pyqtSignal()
    # object avoids PyQt float/slot edge cases from QDoubleSpinBox / QVariant
    request_move_a = pyqtSignal(object)
    request_move_b = pyqtSignal(object)
    request_home_a = pyqtSignal()
    request_home_b = pyqtSignal()
    request_home_both = pyqtSignal()
    trigger_ping = pyqtSignal()

    def __init__(self, parent=None):
        super(ActuatorWorker, self).__init__(parent)
        self._actuator: Optional[ActuatorConnection] = None
        self._bar_a = "Not connected"
        self._bar_b = "Not connected"
        self._gen_a = 0
        self._gen_b = 0
        self._gen_both = 0
        # Manual Control: each Move adds this step to cumulative absolute mm from last Home (movea/moveb target).
        self._accum_a_mm = 0.0
        self._accum_b_mm = 0.0
        self.request_connect.connect(self.do_connect)
        self.request_disconnect.connect(self.do_disconnect)
        self.trigger_ping.connect(self.do_ping)
        self.request_move_a.connect(self.move_a)
        self.request_move_b.connect(self.move_b)
        self.request_home_a.connect(self.home_a)
        self.request_home_b.connect(self.home_b)
        self.request_home_both.connect(self.home_both)

    def _format_actuator_bar(self) -> str:
        return "A: {}  |  B: {}".format(self._bar_a, self._bar_b)

    def _emit_actuator_bar(self) -> None:
        self.actuator_status_line.emit(self._format_actuator_bar())

    def _invalidate_actuator_timers(self) -> None:
        self._gen_a += 1
        self._gen_b += 1
        self._gen_both += 1

    @pyqtSlot(str)
    def do_connect(self, port: str):
        port = (port or "").strip()
        if not port:
            self.connection_result.emit(False)
            self.connection_state_changed.emit({"Actuator": False})
            return
        try:
            want = _com_port_key(port)
            if self._actuator is not None and self._actuator.is_connected():
                cur = _com_port_key(getattr(self._actuator, "port", "") or "")
                if cur == want:
                    try:
                        self._actuator.ping()
                        self.connection_result.emit(True)
                        self.connection_state_changed.emit({"Actuator": True, "com_port": port})
                        return
                    except Exception:
                        pass

            released = False
            if self._actuator:
                try:
                    self._actuator.disconnect()
                except Exception:
                    pass
                self._actuator = None
                released = True
            if released:
                time.sleep(0.75)
            self._actuator = ActuatorConnection(port=port)
            ok = self._actuator.connect()
            payload = {"Actuator": ok, "com_port": port}
            if not ok:
                err = getattr(self._actuator, "last_connect_error", "") or ""
                if err:
                    payload["Actuator_error"] = err
            self.connection_result.emit(ok)
            self.connection_state_changed.emit(payload)
            if ok:
                self._accum_a_mm = 0.0
                self._accum_b_mm = 0.0
                self._bar_a = "Ready"
                self._bar_b = "Ready"
                self._emit_actuator_bar()
            else:
                self._bar_a = self._bar_b = "Not connected"
                self._emit_actuator_bar()
        except Exception as e:
            self._actuator = None
            self._accum_a_mm = 0.0
            self._accum_b_mm = 0.0
            self.connection_result.emit(False)
            self.connection_state_changed.emit(
                {"Actuator": False, "Actuator_error": str(e), "com_port": port}
            )
            self._bar_a = self._bar_b = "Not connected"
            self._emit_actuator_bar()

    @pyqtSlot()
    def do_disconnect(self):
        self._invalidate_actuator_timers()
        self._accum_a_mm = 0.0
        self._accum_b_mm = 0.0
        try:
            if self._actuator:
                self._actuator.disconnect()
                self._actuator = None
        except Exception:
            pass
        self._bar_a = self._bar_b = "Not connected"
        self._emit_actuator_bar()
        self.connection_result.emit(False)
        self.connection_state_changed.emit({"Actuator": False})

    def _connected(self):
        return self._actuator and self._actuator.is_connected()

    @pyqtSlot()
    def do_ping(self):
        """Lightweight connection check so disconnect is detected immediately when device is unplugged/turned off."""
        if not self._actuator or not self._actuator.is_connected():
            return
        try:
            self._actuator.ping()
        except Exception:
            try:
                if self._actuator:
                    self._actuator.disconnect()
            except Exception:
                pass
            self._actuator = None
            self._accum_a_mm = 0.0
            self._accum_b_mm = 0.0
            self._bar_a = self._bar_b = "Not connected"
            self._emit_actuator_bar()
            self.connection_state_changed.emit({"Actuator": False})

    def _finalize_move_a(self, gen, target_abs_mm):
        if gen != self._gen_a or not self._connected():
            return
        self._bar_a = "~{:.1f} mm from home (est.)".format(float(target_abs_mm))
        self._emit_actuator_bar()

    def _finalize_move_b(self, gen, target_abs_mm):
        if gen != self._gen_b or not self._connected():
            return
        self._bar_b = "~{:.1f} mm from home (est.)".format(float(target_abs_mm))
        self._emit_actuator_bar()

    def _finalize_home_a(self, gen):
        if gen != self._gen_a or not self._connected():
            return
        self._accum_a_mm = 0.0
        self._bar_a = "Home"
        self._emit_actuator_bar()

    def _finalize_home_b(self, gen):
        if gen != self._gen_b or not self._connected():
            return
        self._accum_b_mm = 0.0
        self._bar_b = "Home"
        self._emit_actuator_bar()

    def _finalize_home_both(self, gen):
        if gen != self._gen_both or not self._connected():
            return
        self._accum_a_mm = 0.0
        self._accum_b_mm = 0.0
        self._bar_a = "Home"
        self._bar_b = "Home"
        self._emit_actuator_bar()

    @pyqtSlot(object)
    def move_a(self, distance_mm):
        act = self._actuator
        if not act or not act.is_connected():
            print("[Actuator] Move A ignored — not connected (Connection tab: Connect).")
            self.command_log.emit("Actuator: Move A ignored — not connected.")
            return
        d = float(distance_mm)
        if d <= 0:
            self.command_log.emit("Actuator: movea skipped (distance must be > 0).")
            return
        self._gen_a += 1
        self._gen_both += 1
        g = self._gen_a
        self._accum_a_mm += d
        target = self._accum_a_mm
        self._bar_a = "Moving to {:.1f} mm from home (+{:.1f} this step)…".format(target, d)
        self._emit_actuator_bar()
        try:
            ok = act.move_a(target)
            if not ok:
                self._accum_a_mm -= d
                print("[Actuator] Move A skipped (distance <= 0 or not connected).")
                self.command_log.emit("Actuator: movea skipped (check distance > 0).")
                self._bar_a = (
                    "{:.1f} mm from home".format(self._accum_a_mm)
                    if self._accum_a_mm > 1e-6
                    else "Ready"
                )
                self._emit_actuator_bar()
                return
            self.command_log.emit(
                "Actuator: movea +{:.4g} mm step -> {:.4g} mm total from home (sent)".format(d, target)
            )
            ms = int(ActuatorConnection.estimate_move_seconds(d) * 1000)
            QTimer.singleShot(ms, lambda: self._finalize_move_a(g, target))
        except Exception as e:
            self._accum_a_mm -= d
            print("[Actuator] Move A failed: {}".format(e))
            self.command_log.emit("Actuator: movea failed — {}".format(e))
            try:
                act.disconnect()
            except Exception:
                pass
            self._actuator = None
            self._accum_a_mm = 0.0
            self._accum_b_mm = 0.0
            self._bar_a = self._bar_b = "Not connected"
            self._emit_actuator_bar()
            self.connection_state_changed.emit({"Actuator": False})

    @pyqtSlot(object)
    def move_b(self, distance_mm):
        act = self._actuator
        if not act or not act.is_connected():
            print("[Actuator] Move B ignored — not connected (Connection tab: Connect).")
            self.command_log.emit("Actuator: Move B ignored — not connected.")
            return
        d = float(distance_mm)
        if d <= 0:
            self.command_log.emit("Actuator: moveb skipped (distance must be > 0).")
            return
        self._gen_b += 1
        self._gen_both += 1
        g = self._gen_b
        self._accum_b_mm += d
        target = self._accum_b_mm
        self._bar_b = "Moving to {:.1f} mm from home (+{:.1f} this step)…".format(target, d)
        self._emit_actuator_bar()
        try:
            ok = act.move_b(target)
            if not ok:
                self._accum_b_mm -= d
                print("[Actuator] Move B skipped (distance <= 0 or not connected).")
                self.command_log.emit("Actuator: moveb skipped (check distance > 0).")
                self._bar_b = (
                    "{:.1f} mm from home".format(self._accum_b_mm)
                    if self._accum_b_mm > 1e-6
                    else "Ready"
                )
                self._emit_actuator_bar()
                return
            self.command_log.emit(
                "Actuator: moveb +{:.4g} mm step -> {:.4g} mm total from home (sent)".format(d, target)
            )
            ms = int(ActuatorConnection.estimate_move_seconds(d) * 1000)
            QTimer.singleShot(ms, lambda: self._finalize_move_b(g, target))
        except Exception as e:
            self._accum_b_mm -= d
            print("[Actuator] Move B failed: {}".format(e))
            self.command_log.emit("Actuator: moveb failed — {}".format(e))
            try:
                act.disconnect()
            except Exception:
                pass
            self._actuator = None
            self._accum_a_mm = 0.0
            self._accum_b_mm = 0.0
            self._bar_a = self._bar_b = "Not connected"
            self._emit_actuator_bar()
            self.connection_state_changed.emit({"Actuator": False})

    @pyqtSlot()
    def home_a(self):
        act = self._actuator
        if not act or not act.is_connected():
            print("[Actuator] Home A ignored — not connected (Connection tab: Connect).")
            self.command_log.emit("Actuator: Home A ignored — not connected.")
            return
        try:
            self._gen_a += 1
            self._gen_both += 1
            g = self._gen_a
            self._bar_a = "Homing…"
            self._emit_actuator_bar()
            act.home_a()
            self.command_log.emit("Actuator: homea (sent)")
            ms = int(ACTUATOR_ESTIMATE_HOME_SINGLE_SEC * 1000)
            QTimer.singleShot(ms, lambda: self._finalize_home_a(g))
        except Exception as e:
            print("[Actuator] Home A failed: {}".format(e))
            self.command_log.emit("Actuator: homea failed — {}".format(e))
            try:
                act.disconnect()
            except Exception:
                pass
            self._actuator = None
            self._accum_a_mm = 0.0
            self._accum_b_mm = 0.0
            self._bar_a = self._bar_b = "Not connected"
            self._emit_actuator_bar()
            self.connection_state_changed.emit({"Actuator": False})

    @pyqtSlot()
    def home_b(self):
        act = self._actuator
        if not act or not act.is_connected():
            print("[Actuator] Home B ignored — not connected (Connection tab: Connect).")
            self.command_log.emit("Actuator: Home B ignored — not connected.")
            return
        try:
            self._gen_b += 1
            self._gen_both += 1
            g = self._gen_b
            self._bar_b = "Homing…"
            self._emit_actuator_bar()
            act.home_b()
            self.command_log.emit("Actuator: homeb (sent)")
            ms = int(ACTUATOR_ESTIMATE_HOME_SINGLE_SEC * 1000)
            QTimer.singleShot(ms, lambda: self._finalize_home_b(g))
        except Exception as e:
            print("[Actuator] Home B failed: {}".format(e))
            self.command_log.emit("Actuator: homeb failed — {}".format(e))
            try:
                act.disconnect()
            except Exception:
                pass
            self._actuator = None
            self._accum_a_mm = 0.0
            self._accum_b_mm = 0.0
            self._bar_a = self._bar_b = "Not connected"
            self._emit_actuator_bar()
            self.connection_state_changed.emit({"Actuator": False})

    @pyqtSlot()
    def home_both(self):
        act = self._actuator
        if not act or not act.is_connected():
            print("[Actuator] Home Both ignored — not connected (Connection tab: Connect).")
            self.command_log.emit("Actuator: Home Both ignored — not connected.")
            return
        try:
            self._gen_both += 1
            self._gen_a += 1
            self._gen_b += 1
            g = self._gen_both
            self._bar_a = "Homing…"
            self._bar_b = "Homing…"
            self._emit_actuator_bar()
            act.home_both()
            self.command_log.emit("Actuator: HOME BOTH (sent)")
            ms = int(ACTUATOR_ESTIMATE_HOME_BOTH_SEC * 1000)
            QTimer.singleShot(ms, lambda: self._finalize_home_both(g))
        except Exception as e:
            print("[Actuator] Home Both failed: {}".format(e))
            self.command_log.emit("Actuator: HOME BOTH failed — {}".format(e))
            try:
                act.disconnect()
            except Exception:
                pass
            self._actuator = None
            self._accum_a_mm = 0.0
            self._accum_b_mm = 0.0
            self._bar_a = self._bar_b = "Not connected"
            self._emit_actuator_bar()
            self.connection_state_changed.emit({"Actuator": False})

    @pyqtSlot(list)
    def append_instrument_info_line(self, lines):
        """Info menu: actuator has no SCPI *IDN — report COM and link status."""
        try:
            if self._actuator and self._actuator.is_connected():
                port = getattr(self._actuator, "port", "") or "?"
                try:
                    self._actuator.ping()
                    lines.append(
                        "Actuator (Arduino): {} — connected (no *IDN; serial link OK)".format(port)
                    )
                except Exception as e:
                    lines.append("Actuator: {} — {}".format(port, e))
            else:
                lines.append("Actuator: (not connected)")
        except Exception as e:
            lines.append("Actuator: Error — {}".format(e))


# ----- WavemeterWorker -----  (matches origin/main workers + append_instrument_info_line)
class WavemeterWorker(QObject):
    connection_state_changed = pyqtSignal(dict)
    wavelength_updated = pyqtSignal(object)
    range_applied = pyqtSignal(bool, str)
    request_connect = pyqtSignal(str)
    request_disconnect = pyqtSignal()
    trigger_read = pyqtSignal()
    request_apply_range = pyqtSignal(str)

    def __init__(self, parent=None):
        super(WavemeterWorker, self).__init__(parent)
        self._wavemeter = None
        self.request_connect.connect(self.do_connect)
        self.request_disconnect.connect(self.do_disconnect)
        self.trigger_read.connect(self.do_read_wavelength)
        self.request_apply_range.connect(self.do_apply_range)

    @pyqtSlot(str)
    def do_connect(self, address: str):
        address = (address or "").strip()
        if not address:
            self.connection_state_changed.emit({"Wavemeter": False, "Wavemeter_error": "No address selected"})
            return
        try:
            if self._wavemeter and self._wavemeter.is_connected():
                self._wavemeter.disconnect()
            self._wavemeter = WavemeterConnection(address=address)
            ok, err = self._wavemeter.connect()
            self.connection_state_changed.emit({
                "Wavemeter": ok,
                "Wavemeter_error": None if ok else (err or "Connection failed"),
            })
        except Exception as e:
            err_msg = str(e).strip() or type(e).__name__
            self._wavemeter = None
            self.connection_state_changed.emit({"Wavemeter": False, "Wavemeter_error": err_msg})

    @pyqtSlot()
    def do_disconnect(self):
        try:
            if self._wavemeter:
                self._wavemeter.disconnect()
                self._wavemeter = None
        except Exception:
            pass
        self.connection_state_changed.emit({"Wavemeter": False})

    @pyqtSlot()
    def do_read_wavelength(self):
        if not self._wavemeter or not self._wavemeter.is_connected():
            self.wavelength_updated.emit(None)
            return
        try:
            wl = self._wavemeter.read_wavelength_nm()
            self.wavelength_updated.emit(wl)
        except Exception:
            try:
                if self._wavemeter:
                    self._wavemeter.disconnect()
            except Exception:
                pass
            self._wavemeter = None
            self.connection_state_changed.emit({"Wavemeter": False})
            self.wavelength_updated.emit(None)

    @pyqtSlot(str)
    def do_apply_range(self, range_str: str):
        range_str = str(range_str).strip() if range_str else ""
        if range_str not in ("480-1000", "1000-1650"):
            self.range_applied.emit(False, range_str)
            return
        if not self._wavemeter or not self._wavemeter.is_connected():
            self.range_applied.emit(False, range_str)
            return
        try:
            self._wavemeter.set_wavelength_range(range_str)
            self.range_applied.emit(True, range_str)
        except Exception:
            # Do not disconnect on apply failure: first write can raise transient errors
            # (e.g. instrument not ready, timeout). Emit failure so user can retry without reconnecting.
            self.range_applied.emit(False, range_str)

    @pyqtSlot(list)
    def append_instrument_info_line(self, lines):
        """Info menu: *IDN? on wavemeter VISA session if available."""
        try:
            if not self._wavemeter or not self._wavemeter.is_connected():
                lines.append("Wavemeter: (not connected)")
                return
            addr = getattr(self._wavemeter, "gpib_address", "") or ""
            wi = getattr(self._wavemeter, "_instrument", None)
            inst = getattr(wi, "_inst", None) if wi is not None else None
            if inst is None:
                lines.append("Wavemeter: {} — (no VISA session)".format(addr))
                return
            try:
                raw = inst.query("*IDN?").strip()
                lines.append("Wavemeter (*IDN?) [{}]: {}".format(addr, raw))
            except Exception as e:
                lines.append("Wavemeter [{}]: *IDN? failed — {}".format(addr, e))
        except Exception as e:
            lines.append("Wavemeter: Error — {}".format(e))


def _com_port_key(port: str) -> str:
    """Normalize COM port names for comparison (COM4 vs \\\\.\\COM4)."""
    p = (port or "").strip().upper()
    if p.startswith("\\\\.\\"):
        p = p[4:]
    return p


# ----- GentecWorker -----
class GentecWorker(QObject):
    connection_state_changed = pyqtSignal(dict)
    reading_ready = pyqtSignal(object)
    request_connect = pyqtSignal(str)
    request_disconnect = pyqtSignal()
    request_set_gui_multiplier = pyqtSignal(float)
    trigger_read = pyqtSignal()
    request_set_wavelength_nm = pyqtSignal(float, bool)
    gentec_wavelength_applied = pyqtSignal(bool, float)
    request_read_wavelength_nm = pyqtSignal()
    gentec_wavelength_nm_read_ready = pyqtSignal(object)

    def __init__(self, parent=None):
        super(GentecWorker, self).__init__(parent)
        self._gentec = None
        self.request_connect.connect(self.do_connect)
        self.request_disconnect.connect(self.do_disconnect)
        self.request_set_gui_multiplier.connect(self.do_set_gui_multiplier)
        self.trigger_read.connect(self.do_read)
        self.request_set_wavelength_nm.connect(self.do_set_wavelength_nm)
        self.request_read_wavelength_nm.connect(self.do_read_wavelength_nm)

    @pyqtSlot(str)
    def do_connect(self, port: str):
        port = (port or "").strip()
        if not port:
            self.connection_state_changed.emit({"Gentec": False})
            return
        try:
            want = _com_port_key(port)
            if self._gentec is not None and self._gentec.is_connected():
                cur = _com_port_key(getattr(self._gentec, "port", "") or "")
                if cur == want:
                    try:
                        if self._gentec.get_version():
                            self.connection_state_changed.emit({"Gentec": True, "com_port": port})
                            return
                    except Exception:
                        pass

            released = False
            if self._gentec:
                try:
                    self._gentec.disconnect()
                except Exception:
                    pass
                self._gentec = None
                released = True
            if released:
                time.sleep(0.55)
            self._gentec = GentecConnection(port=port)
            ok = self._gentec.connect()
            payload = {"Gentec": ok, "com_port": port}
            if not ok:
                err = getattr(self._gentec, "last_connect_error", "") or ""
                if err:
                    payload["Gentec_error"] = err
            self.connection_state_changed.emit(payload)
        except Exception as e:
            self._gentec = None
            self.connection_state_changed.emit(
                {"Gentec": False, "Gentec_error": str(e), "com_port": port}
            )

    @pyqtSlot()
    def do_disconnect(self):
        try:
            if self._gentec:
                self._gentec.disconnect()
                self._gentec = None
        except Exception:
            pass
        self.connection_state_changed.emit({"Gentec": False})

    @pyqtSlot(float)
    def do_set_gui_multiplier(self, value: float):
        if self._gentec and self._gentec.is_connected():
            try:
                fn = getattr(self._gentec, "set_gui_multiplier", None)
                if callable(fn):
                    fn(float(value))
            except Exception:
                pass

    @pyqtSlot()
    def do_read(self):
        if not self._gentec or not self._gentec.is_connected():
            self.reading_ready.emit(None)
            return
        try:
            value_mw, disp_unit = self._gentec.get_value_mw_and_display_unit()
            if value_mw is None:
                self.reading_ready.emit(None)
            else:
                self.reading_ready.emit((value_mw, disp_unit if disp_unit else ""))
        except Exception as e:
            # Never auto-disconnect on read errors: keep session and let user decide when to reconnect.
            err_msg = str(e).strip() or type(e).__name__
            self.connection_state_changed.emit({"Gentec": True, "Gentec_error": err_msg, "com_port": getattr(self._gentec, "port", "") if self._gentec else ""})
            self.reading_ready.emit(None)

    @pyqtSlot(float, bool)
    def do_set_wavelength_nm(self, wavelength_nm: float, force: bool = True):
        wl = float(wavelength_nm)
        if not self._gentec or not self._gentec.is_connected():
            self.gentec_wavelength_applied.emit(False, wl)
            return
        ok = False
        try:
            fn = getattr(self._gentec, "set_wavelength_nm", None)
            if callable(fn):
                ok = bool(fn(wl, force=force))
        except Exception:
            ok = False
        self.gentec_wavelength_applied.emit(ok, wl)

    @pyqtSlot()
    def do_read_wavelength_nm(self):
        if not self._gentec or not self._gentec.is_connected():
            self.gentec_wavelength_nm_read_ready.emit(None)
            return
        try:
            fn = getattr(self._gentec, "read_wavelength_nm", None)
            v = fn() if callable(fn) else None
            self.gentec_wavelength_nm_read_ready.emit(v)
        except Exception:
            self.gentec_wavelength_nm_read_ready.emit(None)

    @pyqtSlot(list)
    def append_instrument_info_line(self, lines):
        """Info menu: Gentec may use *VER instead of *IDN — try both."""
        try:
            if not self._gentec or not self._gentec.is_connected():
                lines.append("Gentec: (not connected)")
                return
            port = getattr(self._gentec, "port", "") or "?"
            for cmd in ("*IDN?", "*VER"):
                try:
                    r = self._gentec.query(cmd).strip()
                    if r:
                        lines.append("Gentec ({}) [{}]: {}".format(cmd, port, r))
                        return
                except Exception:
                    continue
            lines.append("Gentec [{}]: (no reply to *IDN? / *VER)".format(port))
        except Exception as e:
            lines.append("Gentec: Error — {}".format(e))


# ----- ThorlabsPowermeterWorker -----  (matches origin/main workers + gui mult slot + append_instrument_info_line)
class ThorlabsPowermeterWorker(QObject):
    connection_state_changed = pyqtSignal(dict)
    reading_ready = pyqtSignal(object)
    request_connect = pyqtSignal(str)
    request_disconnect = pyqtSignal()
    trigger_read = pyqtSignal()
    request_set_gui_multiplier = pyqtSignal(float)
    request_set_wavelength_nm = pyqtSignal(float, bool)
    thorlabs_wavelength_applied = pyqtSignal(bool, float)
    request_read_wavelength_nm = pyqtSignal()
    thorlabs_wavelength_nm_read_ready = pyqtSignal(object)

    def __init__(self, parent=None):
        super(ThorlabsPowermeterWorker, self).__init__(parent)
        self._thorlabs = None
        self.request_connect.connect(self.do_connect)
        self.request_disconnect.connect(self.do_disconnect)
        self.trigger_read.connect(self.do_read)
        self.request_set_gui_multiplier.connect(self.do_set_gui_multiplier)
        self.request_set_wavelength_nm.connect(self.do_set_wavelength_nm)
        self.request_read_wavelength_nm.connect(self.do_read_wavelength_nm)

    @pyqtSlot(float)
    def do_set_gui_multiplier(self, value: float):
        if self._thorlabs and self._thorlabs.is_connected():
            try:
                fn = getattr(self._thorlabs, "set_gui_multiplier", None)
                if callable(fn):
                    fn(float(value))
            except Exception:
                pass

    @pyqtSlot(str)
    def do_connect(self, resource_str: str):
        resource_str = (resource_str or "").strip()
        if not resource_str:
            self.connection_state_changed.emit({"Thorlabs": False})
            return
        try:
            if self._thorlabs and self._thorlabs.is_connected():
                self._thorlabs.disconnect()
            self._thorlabs = ThorlabsPowermeterConnection(resource=resource_str)
            ok = self._thorlabs.connect()
            err_payload = ""
            if not ok and self._thorlabs is not None:
                err_payload = getattr(self._thorlabs, "last_connect_error", None) or ""
            payload = {"Thorlabs": ok}
            if err_payload:
                payload["Thorlabs_error"] = err_payload
            self.connection_state_changed.emit(payload)
        except Exception as e:
            self._thorlabs = None
            self.connection_state_changed.emit({"Thorlabs": False, "Thorlabs_error": str(e)})

    @pyqtSlot()
    def do_disconnect(self):
        try:
            if self._thorlabs:
                self._thorlabs.disconnect()
                self._thorlabs = None
        except Exception:
            pass
        self.connection_state_changed.emit({"Thorlabs": False})

    @pyqtSlot()
    def do_read(self):
        if not self._thorlabs or not self._thorlabs.is_connected():
            self.reading_ready.emit(None)
            return
        try:
            value_mw = self._thorlabs.read_power_mw()
            if value_mw is not None:
                try:
                    v = float(value_mw)
                    if not (v == v) or v <= 0:
                        v = None
                    value_mw = v
                except (TypeError, ValueError):
                    value_mw = None
            self.reading_ready.emit(value_mw)
        except Exception:
            try:
                if self._thorlabs:
                    self._thorlabs.disconnect()
            except Exception:
                pass
            self._thorlabs = None
            self.connection_state_changed.emit({"Thorlabs": False})
            self.reading_ready.emit(None)

    @pyqtSlot(float, bool)
    def do_set_wavelength_nm(self, wavelength_nm: float, force: bool = True):
        wl = float(wavelength_nm)
        if not self._thorlabs or not self._thorlabs.is_connected():
            self.thorlabs_wavelength_applied.emit(False, wl)
            return
        ok = False
        try:
            fn = getattr(self._thorlabs, "set_wavelength_nm", None)
            if callable(fn):
                ok = bool(fn(wl, force=force))
        except Exception:
            ok = False
        self.thorlabs_wavelength_applied.emit(ok, wl)

    @pyqtSlot()
    def do_read_wavelength_nm(self):
        if not self._thorlabs or not self._thorlabs.is_connected():
            self.thorlabs_wavelength_nm_read_ready.emit(None)
            return
        try:
            fn = getattr(self._thorlabs, "read_wavelength_nm", None)
            v = fn() if callable(fn) else None
            self.thorlabs_wavelength_nm_read_ready.emit(v)
        except Exception:
            self.thorlabs_wavelength_nm_read_ready.emit(None)

    @pyqtSlot(list)
    def append_instrument_info_line(self, lines):
        """Info menu: Thorlabs powermeter *IDN?."""
        try:
            if not self._thorlabs or not self._thorlabs.is_connected():
                lines.append("Thorlabs powermeter: (not connected)")
                return
            res = getattr(self._thorlabs, "resource", None) or "?"
            try:
                raw = self._thorlabs.query("*IDN?").strip()
                lines.append("Thorlabs (*IDN?) [{}]: {}".format(res, raw))
            except Exception as e:
                lines.append("Thorlabs [{}]: *IDN? failed — {}".format(res, e))
        except Exception as e:
            lines.append("Thorlabs: Error — {}".format(e))


# ----- PRMWorker (PRMConnection set by ViewModel on main thread) -----
class PRMWorker(QObject):
    connection_state_changed = pyqtSignal(dict)
    move_completed = pyqtSignal()
    home_completed = pyqtSignal()
    position_updated = pyqtSignal(object)
    request_disconnect = pyqtSignal()
    request_move_to = pyqtSignal(float, float)  # (angle_deg, speed_deg_per_sec; 0 = do not set speed)
    request_home = pyqtSignal()
    request_position = pyqtSignal()
    request_stop = pyqtSignal()

    def __init__(self, parent=None):
        super(PRMWorker, self).__init__(parent)
        self._prm = None
        self._prm_had_successful_read = False  # only report disconnected after we've seen a good read
        self.request_disconnect.connect(self.do_disconnect)
        self.request_move_to.connect(self.do_move_to)
        self.request_home.connect(self.do_home)
        self.request_position.connect(self.do_get_position)
        self.request_stop.connect(self.do_stop)

    def set_prm(self, prm):
        self._prm = prm
        self._prm_had_successful_read = False

    @pyqtSlot()
    def do_disconnect(self):
        try:
            if self._prm:
                self._prm.disconnect()
                self._prm = None
        except Exception:
            pass
        self.connection_state_changed.emit({"PRM": False})

    @pyqtSlot(float, float)
    def do_move_to(self, angle: float, speed_deg_per_sec: float = 0):
        if self._prm and self._prm.is_connected():
            try:
                if speed_deg_per_sec > 0:
                    self._prm.set_speed(speed_deg_per_sec)
                self._prm.move_to(angle)
                self.move_completed.emit()
            except Exception:
                # Do not clear _prm on failure (e.g. move aborted by Stop/IStop); allow next Home/Move to be sent
                self.move_completed.emit()
        else:
            self.move_completed.emit()

    @pyqtSlot()
    def do_home(self):
        if self._prm and self._prm.is_connected():
            try:
                self._prm.home()
                self.home_completed.emit()
            except Exception:
                # Do not clear _prm on failure; allow next command to be sent
                self.home_completed.emit()
        else:
            self.home_completed.emit()

    @pyqtSlot()
    def do_get_position(self):
        if self._prm and self._prm.is_connected():
            try:
                pos = self._prm.get_position()
                self._prm_had_successful_read = True
                self.position_updated.emit(pos)
            except Exception:
                # Never auto-disconnect on read errors: keep session and let user decide when to reconnect.
                self.position_updated.emit(None)
        else:
            self.position_updated.emit(None)

    @pyqtSlot()
    def do_stop(self):
        """Stop any ongoing move/home command to the PRM instrument."""
        if self._prm and self._prm.is_connected():
            try:
                self._prm.stop()
            except Exception:
                pass


# ----- GenericComWorker -----
class GenericComWorker(QObject):
    connection_state_changed = pyqtSignal(dict)
    request_connect = pyqtSignal(str)
    request_disconnect = pyqtSignal()

    def __init__(self, instrument_name: str, parent=None):
        super(GenericComWorker, self).__init__(parent)
        self._name = instrument_name
        self._conn = None
        self.request_connect.connect(self.do_connect)
        self.request_disconnect.connect(self.do_disconnect)

    @pyqtSlot(str)
    def do_connect(self, port: str):
        port = (port or "").strip()
        if not port:
            self.connection_state_changed.emit({self._name: False})
            return
        try:
            if self._conn and self._conn.is_connected():
                self._conn.disconnect()
            self._conn = GenericComConnection(port=port)
            ok = self._conn.connect()
            self.connection_state_changed.emit({self._name: ok})
        except Exception:
            self._conn = None
            self.connection_state_changed.emit({self._name: False})

    @pyqtSlot()
    def do_disconnect(self):
        try:
            if self._conn:
                self._conn.disconnect()
                self._conn = None
        except Exception:
            pass
        self.connection_state_changed.emit({self._name: False})


# ----- GenericGpibWorker -----
class GenericGpibWorker(QObject):
    connection_state_changed = pyqtSignal(dict)
    request_connect = pyqtSignal(str)
    request_disconnect = pyqtSignal()

    def __init__(self, instrument_name: str, parent=None):
        super(GenericGpibWorker, self).__init__(parent)
        self._name = instrument_name
        self._conn = None
        self.request_connect.connect(self.do_connect)
        self.request_disconnect.connect(self.do_disconnect)

    @pyqtSlot(str)
    def do_connect(self, address: str):
        address = (address or "").strip()
        if not address:
            self.connection_state_changed.emit({self._name: False})
            return
        try:
            if self._conn and self._conn.is_connected():
                self._conn.disconnect()
            self._conn = GenericGpibConnection(address=address)
            ok = self._conn.connect()
            self.connection_state_changed.emit({self._name: ok})
        except Exception:
            self._conn = None
            self.connection_state_changed.emit({self._name: False})

    @pyqtSlot()
    def do_disconnect(self):
        try:
            if self._conn:
                self._conn.disconnect()
                self._conn = None
        except Exception:
            pass
        self.connection_state_changed.emit({self._name: False})


# ----- GenericVisaWorker -----
class GenericVisaWorker(QObject):
    connection_state_changed = pyqtSignal(dict)
    request_connect = pyqtSignal(str)
    request_disconnect = pyqtSignal()

    def __init__(self, instrument_name: str, parent=None):
        super(GenericVisaWorker, self).__init__(parent)
        self._name = instrument_name
        self._conn = None
        self.request_connect.connect(self.do_connect)
        self.request_disconnect.connect(self.do_disconnect)

    @pyqtSlot(str)
    def do_connect(self, resource_str: str):
        resource_str = (resource_str or "").strip()
        if not resource_str:
            self.connection_state_changed.emit({self._name: False})
            return
        try:
            if self._conn and self._conn.is_connected():
                self._conn.disconnect()
            self._conn = GenericVisaConnection(resource_str=resource_str)
            ok = self._conn.connect()
            self.connection_state_changed.emit({self._name: ok})
        except Exception:
            self._conn = None
            self.connection_state_changed.emit({self._name: False})

    @pyqtSlot()
    def do_disconnect(self):
        try:
            if self._conn:
                self._conn.disconnect()
                self._conn = None
        except Exception:
            pass
        self.connection_state_changed.emit({self._name: False})
