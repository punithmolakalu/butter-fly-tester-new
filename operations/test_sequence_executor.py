"""
Runs recipe TEST_SEQUENCE in order. When step is LIV, runs full LIV process (operations.LIV.liv_core)
with bridge instruments and emits liv_process_window_requested, liv_pre_start_prompt_requested,
alignment_window_requested, liv_test_result, etc., so the main window's connections work.
"""
from PyQt5.QtCore import pyqtSignal, QObject, QThread, QMetaObject, Qt
import os
import sys
import threading
from typing import Any, List, Optional

try:
    from operations.stability.stability_process import TemperatureStabilityParameters, TemperatureStabilityProcess
except ImportError:
    TemperatureStabilityProcess = None  # type: ignore
    TemperatureStabilityParameters = None  # type: ignore

# Full LIV process (sweep + Thorlabs + pass/fail + executor callbacks)
try:
    from operations.LIV.liv_core import LIVMain, LIVMainParameters, LIVProcessResult
except ImportError:
    try:
        from operations.liv.liv_core import LIVMain, LIVMainParameters, LIVProcessResult
    except ImportError:
        LIVMain = None  # type: ignore
        LIVMainParameters = None  # type: ignore
        LIVProcessResult = None  # type: ignore

from operations.arroyo_laser_helpers import (
    apply_arroyo_recipe_and_laser_on_for_per,
    arroyo_laser_off,
    per_keep_laser_on_after_step,
    spectrum_keep_laser_on_after_step,
)


def _stability_slot_from_test_name(name: str) -> Optional[int]:
    """Map TEST_SEQUENCE label to slot 1 or 2 (Temperature Stability 1 / 2)."""
    t = (name or "").strip().upper()
    if "STABILITY 2" in t or t == "TS2":
        return 2
    if "STABILITY 1" in t or t == "TS1":
        return 1
    return None

try:
    # Actual path: operations/per/PER_PROCESS.py (lowercase package, uppercase module name)
    from operations.per.PER_PROCESS import PERProcess, PERProcessParameters
except ImportError:
    try:
        from operations.PER.PER_PROCESS import PERProcess, PERProcessParameters
    except ImportError:
        PERProcess = None  # type: ignore
        PERProcessParameters = None  # type: ignore

try:
    from operations.spectrum.spectrum_process import SpectrumProcess, SpectrumProcessParameters
except ImportError:
    try:
        from operations.spectrum import SpectrumProcess, SpectrumProcessParameters
    except ImportError:
        SpectrumProcess = None  # type: ignore
        SpectrumProcessParameters = None  # type: ignore

class TestSequenceExecutor(QObject):
    log_message = pyqtSignal(str)
    # Step-specific process logs (secondary-monitor windows only; not Main tab status log).
    liv_log_message = pyqtSignal(str)
    per_log_message = pyqtSignal(str)
    spectrum_log_message = pyqtSignal(str)
    liv_test_result = pyqtSignal(object)
    per_test_result = pyqtSignal(object, object, object)  # result, angles, powers_mw
    spectrum_test_result = pyqtSignal(object)
    test_window_requested = pyqtSignal(str, dict)
    liv_process_window_requested = pyqtSignal(dict)
    connect_fiber_before_liv_requested = pyqtSignal(str)
    liv_pre_start_prompt_requested = pyqtSignal(str, dict)
    alignment_window_requested = pyqtSignal()
    liv_plot_clear = pyqtSignal()
    # current (mA), Gentec power (mW), laser voltage LAS:LDV (V), monitor diode LAS:MDI (raw instrument units)
    liv_plot_update = pyqtSignal(float, float, float, float)
    liv_power_reading_update = pyqtSignal(float, float)  # gentec_mW, thorlabs_mW
    per_process_window_requested = pyqtSignal(dict)
    spectrum_process_window_requested = pyqtSignal(dict)  # RCP summary for secondary Spectrum window
    spectrum_live_trace = pyqtSignal(object, object)  # wdata, ldata (Ando trace; worker thread → UI)
    spectrum_wavemeter_reading = pyqtSignal(object)  # wavelength nm or None
    spectrum_step_status = pyqtSignal(str)  # first/second sweep status for Spectrum window + log
    stability_log_message = pyqtSignal(str)
    stability_live_point = pyqtSignal(float, float, float, float)  # T °C, FWHM nm, SMSR dB, peak nm
    stability_test_result = pyqtSignal(object)
    # Step name + list of reason strings for Main tab "Reason for Failure" (worker thread → UI).
    sequence_step_failed = pyqtSignal(str, object)

    def __init__(self, main_window: Any) -> None:
        super().__init__()
        self.main_window = main_window
        self._bridge: Any = None
        self._recipe: Any = None
        self._test_sequence: List[str] = []
        self._instrument_manager: Any = None
        self._stop_requested = False
        # Set True when run() exits because user pressed Stop (so UI shows Stopped, not Done/Fail).
        self._sequence_stopped_by_user = False
        # Conditions for LIV prompts / alignment (main thread acks via slots)
        self._liv_prompt_condition = threading.Condition()
        self._connect_fiber_condition = threading.Condition()
        self._connect_fiber_ack: Optional[bool] = None
        self._alignment_condition = threading.Condition()
        self._alignment_ack: Optional[bool] = None
        # Which Temperature Stability slot (1/2) is running — used by Plot tab live mirror.
        self._stability_live_slot: Optional[int] = None

    def set_test_sequence(self, test_sequence: Any, recipe: Any) -> None:
        if isinstance(test_sequence, (list, tuple)):
            self._test_sequence = [str(x) for x in test_sequence]
        else:
            self._test_sequence = []
        self._recipe = recipe
        # Same normalization as load_recipe_file: hoist TEMP STABILITY blocks into OPERATIONS,
        # copy Wavelength → SPECTRUM center when needed — so Run uses the same dict as New Recipe + RCP tab.
        if isinstance(self._recipe, dict):
            try:
                from operations.recipe_normalize import normalize_loaded_recipe

                normalize_loaded_recipe(self._recipe)
            except Exception:
                pass

    def set_sequence_bridge(self, bridge: Any) -> None:
        self._bridge = bridge

    def set_instrument_manager(self, manager: Any) -> None:
        self._instrument_manager = manager

    def _emit_step_failed(self, test_name: str, reasons: Any) -> None:
        """Push failure text to the Main window Reason for Failure box (via signal)."""
        if isinstance(reasons, (list, tuple)):
            rs = [str(x).strip() for x in reasons if x is not None and str(x).strip()]
        elif reasons is None or (isinstance(reasons, str) and not reasons.strip()):
            rs = []
        else:
            rs = [str(reasons).strip()]
        self.sequence_step_failed.emit(test_name, rs)

    def stop(self) -> None:
        self._stop_requested = True

    def ack_liv_pre_start_prompt(self) -> None:
        with self._liv_prompt_condition:
            self._liv_prompt_condition.notify_all()

    def confirm_connect_fiber_before_liv(self) -> None:
        with self._connect_fiber_condition:
            self._connect_fiber_ack = True
            self._connect_fiber_condition.notify_all()

    def cancel_connect_fiber_before_liv(self) -> None:
        with self._connect_fiber_condition:
            self._connect_fiber_ack = False
            self._connect_fiber_condition.notify_all()

    def continue_after_alignment(self) -> None:
        with self._alignment_condition:
            self._alignment_ack = True
            self._alignment_condition.notify_all()

    def alignment_cancelled(self) -> None:
        with self._alignment_condition:
            self._alignment_ack = False
            self._alignment_condition.notify_all()

    def get_liv_alignment_params(self) -> Optional[tuple]:
        """Return (min_current, max_current, temperature) for alignment window."""
        r = self._recipe
        if not r:
            return None
        op = (r.get("OPERATIONS") or r.get("operations")) or {}
        liv = (op.get("LIV") or op.get("liv")) or {}
        def f(k: str, default: float = 0.0) -> float:
            v = liv.get(k)
            try:
                return float(v) if v is not None else default
            except (TypeError, ValueError):
                return default
        return (f("min_current_mA", 0), f("max_current_mA", 500), f("temperature", 25))

    def run(self) -> bool:
        """Run TEST_SEQUENCE in order; return True if all steps passed."""
        self._stop_requested = False
        self._sequence_stopped_by_user = False
        self.log_message.emit("Starting test sequence...")
        if not self._test_sequence or self._recipe is None:
            self.log_message.emit("No test sequence or recipe loaded.")
            self._emit_step_failed(
                "TEST_SEQUENCE",
                ["No test sequence or recipe loaded. Load a recipe with TEST_SEQUENCE before starting."],
            )
            return False

        all_passed = True
        recipe = self._recipe if isinstance(self._recipe, dict) else {}

        seq_list = [str(x) for x in self._test_sequence]
        ts1_in_sequence = any(_stability_slot_from_test_name(x) == 1 for x in seq_list)
        ts1_passed: Optional[bool] = None

        for test_name in self._test_sequence:
            if self._stop_requested:
                self._sequence_stopped_by_user = True
                self.log_message.emit("STOP: Test sequence aborted by user.")
                return False
            name_upper = (test_name or "").strip().upper()
            if not name_upper:
                continue
            stab_slot = _stability_slot_from_test_name(str(test_name))
            if stab_slot is not None:
                if stab_slot == 2 and ts1_in_sequence and ts1_passed is False:
                    self.log_message.emit("Temperature Stability 2 skipped (Temperature Stability 1 did not pass).")
                    self._emit_step_failed(
                        str(test_name),
                        ["Temperature Stability 2 skipped because Temperature Stability 1 did not pass."],
                    )
                    all_passed = False
                    continue
                self.stability_log_message.emit("Starting {}…".format(test_name))
                step_ok = self._run_temperature_stability(recipe, stab_slot, str(test_name))
                if stab_slot == 1:
                    ts1_passed = step_ok
                if not step_ok:
                    all_passed = False
                self.stability_log_message.emit("{} completed.".format(test_name))
                continue
            if name_upper == "LIV":
                self.liv_log_message.emit("Starting LIV test…")
                step_ok = self._run_liv(recipe)
                if not step_ok:
                    all_passed = False
                self.liv_log_message.emit("LIV test completed.")
            elif name_upper == "PER":
                self.per_log_message.emit("Starting PER test…")
                step_ok = self._run_per(recipe)
                if not step_ok:
                    all_passed = False
                self.per_log_message.emit("PER test completed.")
            elif name_upper == "SPECTRUM":
                self.spectrum_log_message.emit("Starting Spectrum test…")
                step_ok = self._run_spectrum(recipe)
                if not step_ok:
                    all_passed = False
                self.spectrum_log_message.emit("Spectrum test completed.")
            else:
                self.log_message.emit(f"Test {test_name} not implemented.")
                self._emit_step_failed(
                    str(test_name),
                    ["Test type {!r} is not implemented.".format(test_name)],
                )
                all_passed = False

        # If Stop was pressed while the last step was running, we never re-enter the loop.
        if self._stop_requested:
            self._sequence_stopped_by_user = True
            self.log_message.emit("STOP: Test sequence aborted by user.")
            return False

        return all_passed

    def _run_liv(self, recipe: Any) -> bool:
        if LIVMain is None or LIVMainParameters is None or LIVProcessResult is None:
            self.log_message.emit("LIV module not available.")
            self._emit_step_failed("LIV", ["LIV module not available (import failed)."])
            return False
        bridge = self._bridge
        if bridge is None:
            self.log_message.emit("No sequence bridge for LIV.")
            self._emit_step_failed("LIV", ["Internal error: no sequence bridge for LIV."])
            return False
        arroyo = bridge.get_arroyo()
        gentec = bridge.get_instrument("Gentec")
        thorlabs = bridge.get_instrument("Thorlabs") or bridge.get_instrument("Thorlabs_Powermeter")
        actuator = bridge.get_instrument("Actuator") or bridge.get_instrument("Actuators")
        ando = bridge.get_instrument("Ando")
        if not arroyo or not gentec:
            self.log_message.emit("Missing Arroyo or Gentec for LIV. Connect them in the Connection tab.")
            self._emit_step_failed(
                "LIV",
                ["Missing Arroyo or Gentec — connect both in the Connection tab before LIV."],
            )
            return False
        recipe_dict = recipe if isinstance(recipe, dict) else {}

        # Pause UI polling on main thread (timers cannot be stopped from this worker thread)
        mw = getattr(self, "main_window", None)
        if mw is not None and hasattr(mw, "pausePollingForLiv"):
            QMetaObject.invokeMethod(mw, "pausePollingForLiv", Qt.BlockingQueuedConnection)
        try:
            params = LIVMainParameters.from_recipe(recipe_dict)
            if not isinstance(params, LIVMainParameters):
                self.liv_log_message.emit(
                    f"LIV internal error: from_recipe returned {type(params).__name__}, expected LIVMainParameters."
                )
                self._emit_step_failed(
                    "LIV",
                    [
                        "LIV internal error: recipe parameters could not be built (check OPERATIONS.LIV in the recipe).",
                    ],
                )
                return False
            liv = LIVMain(None)  # no parent: created in worker thread; executor is in main thread
            liv.set_instruments(
                arroyo=arroyo,
                gentec=gentec,
                thorlabs_pm=thorlabs,
                actuator=actuator,
                ando=ando,
            )
            result = liv.run(params, executor=self, recipe=recipe_dict)
            return bool(result.passed)
        except Exception as e:
            self.liv_log_message.emit(f"LIV error: {e}")
            self._emit_step_failed("LIV", ["LIV error: {}".format(e)])
            return False
        finally:
            # Resume UI polling on main thread (timers cannot be started from this worker thread)
            if mw is not None and hasattr(mw, "resumePollingAfterLiv"):
                QMetaObject.invokeMethod(mw, "resumePollingAfterLiv", Qt.BlockingQueuedConnection)

    def _run_per(self, recipe: Any) -> bool:
        if PERProcess is None or PERProcessParameters is None:
            self.log_message.emit("PER module not available.")
            self._emit_step_failed("PER", ["PER module not available (import failed)."])
            return False
        bridge = self._bridge
        if bridge is None:
            self.log_message.emit("No sequence bridge for PER.")
            self._emit_step_failed("PER", ["Internal error: no sequence bridge for PER."])
            return False
        thorlabs = bridge.get_instrument("Thorlabs") or bridge.get_instrument("Thorlabs_Powermeter")
        actuator = bridge.get_instrument("Actuator") or bridge.get_instrument("Actuators")
        arroyo = bridge.get_arroyo()
        prm = None
        if self.main_window is not None:
            vm = getattr(self.main_window, "_viewmodel", None)
            prm = getattr(vm, "_prm_connection", None) if vm is not None else None
        if arroyo is None or not getattr(arroyo, "is_connected", lambda: False)():
            self.log_message.emit(
                "PER requires Arroyo connected — recipe laser/TEC (RCP) is applied and laser must turn ON. "
                "Connect Arroyo in the Connection tab."
            )
            self._emit_step_failed(
                "PER",
                [
                    "Arroyo is not connected — connect Arroyo in the Connection tab (PER needs laser/TEC RCP).",
                ],
            )
            return False
        if not thorlabs or not prm:
            self.log_message.emit("Missing Thorlabs or PRM for PER. Connect them in the Connection tab.")
            self._emit_step_failed(
                "PER",
                ["Missing Thorlabs powermeter or PRM — connect both in the Connection tab before PER."],
            )
            return False

        recipe_dict = recipe if isinstance(recipe, dict) else {}
        mw = getattr(self, "main_window", None)
        if mw is not None and hasattr(mw, "pausePollingForLiv"):
            QMetaObject.invokeMethod(mw, "pausePollingForLiv", Qt.BlockingQueuedConnection)
        try:
            ok_laser, err_laser = apply_arroyo_recipe_and_laser_on_for_per(
                arroyo, recipe_dict, log=lambda m: self.per_log_message.emit(m)
            )
            if not ok_laser:
                msg = err_laser or "Arroyo laser setup failed."
                self.per_log_message.emit("PER aborted: {}".format(msg))
                self._emit_step_failed(
                    "PER",
                    [
                        "PER aborted: {} — check Arroyo, interlocks, and recipe current/temperature; "
                        "if the laser is on but readback says OFF, set allow_laser_readback_off or BF_PER_ALLOW_LASER_READBACK_OFF.".format(
                            msg
                        ),
                    ],
                )
                return False

            # Laser ON + recipe current/temp were applied above; PER sweep runs next (Thorlabs + PRM).
            self.per_log_message.emit("PER: Laser is ON — starting PRM sweep and Thorlabs sampling.")

            params = PERProcessParameters.from_recipe(recipe_dict)
            self.per_process_window_requested.emit(
                {
                    "start_angle_deg": float(getattr(params, "start_angle_deg", 0.0)),
                    "travel_distance_deg": float(getattr(params, "travel_distance_deg", 0.0)),
                    "meas_speed_deg_per_sec": float(getattr(params, "meas_speed_deg_per_sec", 0.0)),
                    "setup_speed_deg_per_sec": float(getattr(params, "setup_speed_deg_per_sec", 0.0)),
                    "wait_time_ms": float(getattr(params, "wait_time_ms", 0.0)),
                    "steps_per_degree": float(getattr(params, "steps_per_degree", 0.0)),
                    "min_per_db": float(getattr(params, "min_per_db", 0.0)),
                    "actuator_speed": float(getattr(params, "actuator_speed", 0.0)),
                    "actuator_distance": float(getattr(params, "actuator_distance", 0.0)),
                    "skip_actuator": bool(getattr(params, "skip_actuator", False)),
                    "wavelength_nm": float(getattr(params, "wavelength_nm", 0.0) or 0.0),
                }
            )
            self.per_log_message.emit(
                "PER: Arroyo + Thorlabs (VISA) + PRM (Kinesis); RCP laser conditions applied, laser ON."
            )
            per = PERProcess()
            per.set_instruments(thorlabs_pm=thorlabs, prm=prm, actuator=actuator)
            result = per.run(
                params,
                executor=self,
                stop_requested=lambda: bool(getattr(self, "_stop_requested", False)),
                recipe=recipe_dict,
            )
            passed = bool(result.passed)
            return passed
        except Exception as e:
            self.per_log_message.emit(f"PER error: {e}")
            self._emit_step_failed("PER", ["PER error: {}".format(e)])
            return False
        finally:
            # Default: turn laser off when PER exits (pass/fail/stop) — enclosure safety.
            # Opt out: recipe OPERATIONS.PER.keep_laser_on_after / GENERAL.keep_laser_on_after_per, or BF_PER_KEEP_LASER_ON=1
            try:
                if per_keep_laser_on_after_step(recipe_dict):
                    self.per_log_message.emit(
                        "PER: Arroyo laser left ON (keep_laser_on_after in recipe or BF_PER_KEEP_LASER_ON). "
                        "Turn laser off manually when finished."
                    )
                else:
                    arroyo_laser_off(arroyo)
                    self.per_log_message.emit(
                        "PER: Arroyo laser output OFF (PER step ended — laser safety; safe to open enclosure)."
                    )
            except Exception:
                pass
            if mw is not None and hasattr(mw, "resumePollingAfterLiv"):
                QMetaObject.invokeMethod(mw, "resumePollingAfterLiv", Qt.BlockingQueuedConnection)

    def _run_spectrum(self, recipe: Any) -> bool:
        if SpectrumProcess is None:
            self.log_message.emit("Spectrum module not available.")
            self._emit_step_failed("SPECTRUM", ["Spectrum module not available (import failed)."])
            return False
        bridge = self._bridge
        if bridge is None:
            self.log_message.emit("No sequence bridge for Spectrum.")
            self._emit_step_failed("SPECTRUM", ["Internal error: no sequence bridge for Spectrum."])
            return False
        arroyo = bridge.get_arroyo()
        ando = bridge.get_instrument("Ando")
        wavemeter = bridge.get_instrument("Wavemeter")
        recipe_dict = recipe if isinstance(recipe, dict) else {}
        if arroyo is None or not getattr(arroyo, "is_connected", lambda: False)():
            self.log_message.emit("Spectrum requires Arroyo connected (TEC + laser).")
            self._emit_step_failed(
                "SPECTRUM",
                ["Arroyo is not connected — connect Arroyo in the Connection tab before Spectrum."],
            )
            return False
        if ando is None or not getattr(ando, "is_connected", lambda: False)():
            self.log_message.emit("Spectrum requires Ando (OSA) connected.")
            self._emit_step_failed(
                "SPECTRUM",
                ["Ando is not connected — connect the optical spectrum analyzer in the Connection tab."],
            )
            return False
        if wavemeter is None or not getattr(wavemeter, "is_connected", lambda: False)():
            self.log_message.emit("Spectrum requires Wavemeter connected (live wavelength read).")
            self._emit_step_failed(
                "SPECTRUM",
                ["Wavemeter is not connected — connect the wavemeter in the Connection tab before Spectrum."],
            )
            return False

        self.spectrum_log_message.emit(
            "Spectrum: Arroyo, Ando, and Wavemeter connected — opening Spectrum window on secondary display."
        )

        # Build params for the secondary Spectrum window. Must open + connect live-plot signals
        # *before* spec.run() — otherwise spectrum_live_trace emits from the worker thread while
        # spectrum_process_window_requested is still queued on the GUI thread (race: no plot).
        params_dict: dict = {}
        if SpectrumProcessParameters is not None:
            try:
                sp = SpectrumProcessParameters.from_recipe(recipe_dict)
                params_dict = {
                    "center_nm": sp.center_nm,
                    "span_nm": sp.span_nm,
                    "resolution_nm": sp.resolution_nm,
                    "sampling_points": sp.sampling_points,
                    "temperature_c": sp.temperature_c,
                    "laser_current_mA": sp.laser_current_mA,
                    "sensitivity": sp.sensitivity,
                    "analysis": sp.analysis,
                    "ref_level_dbm": sp.ref_level_dbm,
                    "level_scale_db_per_div": sp.level_scale_db_per_div,
                }
            except Exception:
                pass
        self._spectrum_window_params_pending = params_dict

        mw = getattr(self, "main_window", None)
        if mw is not None:
            QMetaObject.invokeMethod(
                mw,
                "blocking_open_spectrum_test_window",
                Qt.BlockingQueuedConnection,
            )
        else:
            self.spectrum_process_window_requested.emit(params_dict)

        if mw is not None and hasattr(mw, "pausePollingForLiv"):
            QMetaObject.invokeMethod(mw, "pausePollingForLiv", Qt.BlockingQueuedConnection)
        try:
            spec = SpectrumProcess()
            spec.set_instruments(arroyo=arroyo, ando=ando, wavemeter=wavemeter)
            result = spec.run(
                recipe_dict,
                executor=self,
                stop_requested=lambda: bool(getattr(self, "_stop_requested", False)),
            )
            if result.fail_reasons:
                self._emit_step_failed("SPECTRUM", list(result.fail_reasons))
            return bool(result.passed)
        except Exception as e:
            self.spectrum_log_message.emit(f"Spectrum error: {e}")
            self._emit_step_failed("SPECTRUM", ["Spectrum error: {}".format(e)])
            return False
        finally:
            try:
                if spectrum_keep_laser_on_after_step(recipe_dict):
                    self.spectrum_log_message.emit(
                        "Spectrum: Arroyo laser left ON (keep_laser_on_after in recipe or BF_SPECTRUM_KEEP_LASER_ON)."
                    )
                else:
                    arroyo_laser_off(arroyo)
                    self.spectrum_log_message.emit("Spectrum: Arroyo laser output OFF (step ended).")
            except Exception:
                pass
            if mw is not None and hasattr(mw, "resumePollingAfterLiv"):
                QMetaObject.invokeMethod(mw, "resumePollingAfterLiv", Qt.BlockingQueuedConnection)

    def _run_temperature_stability(self, recipe: Any, slot: int, step_name: str) -> bool:
        if TemperatureStabilityProcess is None or TemperatureStabilityParameters is None:
            self.log_message.emit("Temperature stability module not available.")
            self._emit_step_failed(step_name, ["Temperature stability module not available (import failed)."])
            return False
        bridge = self._bridge
        if bridge is None:
            self._emit_step_failed(step_name, ["Internal error: no sequence bridge for temperature stability."])
            return False
        arroyo = bridge.get_arroyo()
        ando = bridge.get_instrument("Ando")
        recipe_dict = recipe if isinstance(recipe, dict) else {}
        if arroyo is None or not getattr(arroyo, "is_connected", lambda: False)():
            self.stability_log_message.emit("Temperature stability requires Arroyo connected.")
            self._emit_step_failed(
                step_name,
                ["Arroyo is not connected — connect the laser/TEC controller in the Connection tab."],
            )
            return False
        if ando is None or not getattr(ando, "is_connected", lambda: False)():
            self.stability_log_message.emit("Temperature stability requires Ando (OSA) connected.")
            self._emit_step_failed(
                step_name,
                ["Ando is not connected — connect the optical spectrum analyzer in the Connection tab."],
            )
            return False

        params_obj = TemperatureStabilityParameters.from_recipe_blocks(recipe_dict, slot)
        try:
            import dataclasses

            pr_dict = dataclasses.asdict(params_obj)
        except Exception:
            pr_dict = {}
        self._stability_window_params_pending = {"slot": slot, "params": pr_dict, "step_name": step_name}

        mw = getattr(self, "main_window", None)
        if mw is not None:
            QMetaObject.invokeMethod(
                mw,
                "blocking_open_stability_test_window",
                Qt.BlockingQueuedConnection,
            )
        else:
            self.stability_log_message.emit("No main window — cannot open stability secondary window.")

        if mw is not None and hasattr(mw, "pausePollingForLiv"):
            QMetaObject.invokeMethod(mw, "pausePollingForLiv", Qt.BlockingQueuedConnection)
        self._stability_live_slot = int(slot)
        try:
            proc = TemperatureStabilityProcess()
            proc.set_instruments(arroyo=arroyo, ando=ando)
            result = proc.run(
                recipe_dict,
                self,
                slot,
                stop_requested=lambda: bool(getattr(self, "_stop_requested", False)),
                step_label=step_name,
            )
            if result.fail_reasons:
                self._emit_step_failed(step_name, list(result.fail_reasons))
            return bool(result.passed)
        except Exception as e:
            self.stability_log_message.emit("Temperature stability error: {}".format(e))
            self._emit_step_failed(step_name, ["Temperature stability error: {}".format(e)])
            return False
        finally:
            try:
                if spectrum_keep_laser_on_after_step(recipe_dict):
                    self.stability_log_message.emit(
                        "Stability: Arroyo laser left ON (keep_laser_on_after / BF_SPECTRUM_KEEP_LASER_ON)."
                    )
                else:
                    arroyo_laser_off(arroyo)
                    self.stability_log_message.emit("Stability: Arroyo laser output OFF (step ended).")
            except Exception:
                pass
            if mw is not None and hasattr(mw, "resumePollingAfterLiv"):
                QMetaObject.invokeMethod(mw, "resumePollingAfterLiv", Qt.BlockingQueuedConnection)
            self._stability_live_slot = None


class TestSequenceThread(QThread):
    sequence_completed = pyqtSignal(bool)  # all_passed
    sequence_stopped = pyqtSignal()

    def __init__(self, executor: TestSequenceExecutor, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.executor = executor
        self.result: Optional[bool] = None

    def run(self) -> None:
        try:
            self.result = self.executor.run()
            if getattr(self.executor, "_sequence_stopped_by_user", False):
                self.sequence_stopped.emit()
            else:
                self.sequence_completed.emit(self.result if self.result is not None else False)
        except Exception:
            self.result = False
            if getattr(self.executor, "_stop_requested", False):
                setattr(self.executor, "_sequence_stopped_by_user", True)
                try:
                    self.executor.log_message.emit("STOP: Test sequence ended (stop requested).")
                except Exception:
                    pass
                self.sequence_stopped.emit()
            else:
                self.sequence_completed.emit(False)
