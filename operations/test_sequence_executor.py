"""
Runs recipe TEST_SEQUENCE in order. When step is LIV, runs full LIV process (operations.liv.liv_core)
with bridge instruments and emits liv_process_window_requested, liv_pre_start_prompt_requested,
alignment_window_requested, liv_test_result, etc., so the main window's connections work.
"""
from PyQt5.QtCore import pyqtSignal, QObject, QThread, QMetaObject, Qt
import threading
from typing import Any, List, Optional, cast

try:
    from operations.result_saver import ResultSession
except ImportError:
    ResultSession = None  # type: ignore

# PyQt5 stubs omit ConnectionType members on Qt; cast keeps strict checkers quiet.
QtCompat: Any = cast(Any, Qt)

try:
    from operations.stability.stability_process import TemperatureStabilityParameters, TemperatureStabilityProcess
except ImportError:
    TemperatureStabilityProcess = None  # type: ignore
    TemperatureStabilityParameters = None  # type: ignore

# Full LIV process (sweep + Thorlabs + pass/fail + executor callbacks)
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
    # Check slot 2 before 1 so labels like "TEMP STABILITY 2" match reliably.
    if "STABILITY 2" in t or t in ("TS2", "TS 2"):
        return 2
    if "STABILITY 1" in t or t in ("TS1", "TS 1"):
        return 1
    return None

try:
    from operations.per.PER_PROCESS import PERProcess, PERProcessParameters
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


def _post_pause_poll_settle() -> None:
    """After main-thread timers are stopped, wait on the **sequence worker** thread (not the GUI).

    Previously ``time.sleep`` ran inside ``pause_for_liv`` on the main thread (via
    ``BlockingQueuedConnection``), which froze the window for ~750 ms per LIV/PER/Spectrum pause.
    """
    QThread.msleep(750)


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
    # current (mA), Gentec power (mW), laser voltage LAS:LDV (V), monitor diode LAS:MDI (raw), TEC temp (°C, NaN if unknown)
    liv_plot_update = pyqtSignal(float, float, float, float, float)
    liv_power_reading_update = pyqtSignal(float, float)  # gentec_mW, thorlabs_mW
    per_process_window_requested = pyqtSignal(dict)
    spectrum_process_window_requested = pyqtSignal(dict)  # RCP summary for secondary Spectrum window
    spectrum_live_trace = pyqtSignal(object, object)  # wdata, ldata (Ando trace; worker thread → UI)
    spectrum_wavemeter_reading = pyqtSignal(object)  # wavelength nm or None
    spectrum_step_status = pyqtSignal(str)  # first/second sweep status for Spectrum window + log
    stability_log_message = pyqtSignal(str)
    # T °C, FWHM nm, SMSR dB, peak nm, peak dBm (Ando), Thorlabs mW, ramp "c_h"|"h_c" (cold→hot vs hot→cold)
    stability_live_point = pyqtSignal(float, float, float, float, float, float, str)
    # Same keys as ArroyoWorker.read_all — emitted on worker thread after each live point for Main Laser/TEC.
    stability_live_arroyo = pyqtSignal(dict)
    # Same keys as ArroyoWorker.read_all — emitted during LIV so Main Laser/TEC Details stay live.
    liv_live_arroyo = pyqtSignal(dict)
    # Generic Arroyo snapshot for ALL tests (LIV, PER, Spectrum, Stability) — Main tab Laser/TEC Details.
    live_arroyo = pyqtSignal(dict)
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
        # True only when stop() was called (user Stop) — laser-interlock abort clears this so session is not "stopped_by_user".
        self._stop_from_user = False
        # While True, worker polls Arroyo laser output; explicit OFF aborts the sequence (hardware / interlock).
        self._laser_monitor_armed = False
        self._laser_abort_emitted = False
        self._laser_abort_step = ""
        # Set True when run() exits because user pressed Stop (so UI shows Stopped, not Done/Fail).
        self._sequence_stopped_by_user = False
        # Conditions for LIV prompts / alignment (main thread acks via slots)
        self._liv_prompt_condition = threading.Condition()
        self._connect_fiber_condition = threading.Condition()
        self._connect_fiber_ack: Optional[bool] = None
        self._alignment_condition = threading.Condition()
        self._alignment_ack: Optional[bool] = None
        # Which Temperature Stability slot (1/2) is running — used for stability step bookkeeping.
        self._stability_live_slot: Optional[int] = None
        # PER live window: main thread reads this in _prepare_per_test_window_before_per_run (BlockingQueuedConnection).
        self._pending_per_window_params: Optional[dict] = None
        # Steps in TEST_SEQUENCE still to run after the current step finishes (0 = last or only step).
        self._tests_remaining_after_current_step: int = 0

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

    def _emit_arroyo_snapshot(self, arroyo: Any) -> None:
        """Read full Arroyo state and emit live_arroyo so Main tab Laser/TEC Details update."""
        if arroyo is None or not getattr(arroyo, "is_connected", lambda: False)():
            return
        try:
            snap = arroyo.read_gui_snapshot()
            if isinstance(snap, dict):
                self.live_arroyo.emit(snap)
        except Exception:
            pass

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
        self._stop_from_user = True

    def notify_laser_monitor_armed(self, armed: bool) -> None:
        """Called from LIV / Spectrum / Stability after laser is ON; cleared before intentional laser OFF."""
        self._laser_monitor_armed = bool(armed)

    def _arroyo_laser_readback_is_off(self) -> bool:
        """True only when Arroyo is connected and LAS:OUT readback is explicitly not ON (interlock / local OFF)."""
        bridge = getattr(self, "_bridge", None)
        if bridge is None:
            return False
        ar = bridge.get_arroyo()
        if ar is None or not getattr(ar, "is_connected", lambda: False)():
            return False
        try:
            rd = getattr(ar, "laser_read_output", None)
            if not callable(rd):
                return False
            v = rd()
            if v is None:
                return False
            return int(v) != 1
        except Exception:
            return False

    def _fire_laser_off_abort(self) -> None:
        if getattr(self, "_laser_abort_emitted", False):
            return
        self._laser_abort_emitted = True
        self._stop_requested = True
        self._stop_from_user = False
        step = (getattr(self, "_laser_abort_step", None) or "").strip() or "TEST_SEQUENCE"
        msg = (
            "Arroyo laser output went OFF during {!r} — test sequence aborted "
            "(hardware OFF, interlock, or controller fault).".format(step)
        )
        try:
            self.log_message.emit("STOP: " + msg)
        except Exception:
            pass
        self._emit_step_failed(step, [msg])

    def _stop_requested_or_laser_off(self) -> bool:
        """Use as stop_requested for PER / Spectrum / Stability (and LIV via liv_core)."""
        if bool(getattr(self, "_stop_requested", False)):
            return True
        if not bool(getattr(self, "_laser_monitor_armed", False)):
            return False
        if self._arroyo_laser_readback_is_off():
            self._fire_laser_off_abort()
            return True
        return False

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
        """Return (min_current, max_current, temperature) for alignment window (LIV RCP keys + MINCurr/MAXCurr)."""
        r = self._recipe
        if not r:
            return None
        op = (r.get("OPERATIONS") or r.get("operations")) or {}
        liv = (op.get("LIV") or op.get("liv")) or {}

        def pick(keys: tuple, default: float) -> float:
            for k in keys:
                v = liv.get(k)
                if v is None or v == "":
                    continue
                try:
                    return float(v)
                except (TypeError, ValueError):
                    continue
            return default

        return (
            pick(("min_current_mA", "MINCurr"), 0.0),
            pick(("max_current_mA", "MAXCurr"), 500.0),
            pick(("temperature", "Temperature"), 25.0),
        )

    def is_liv_fiber_coupled(self) -> bool:
        """Same as LIV recipe FiberCoupled (default True): fiber path uses Thorlabs + alignment before sweep."""
        r = self._recipe
        if not isinstance(r, dict):
            return True
        gen = r.get("GENERAL") or r.get("General") or {}
        if isinstance(gen, dict) and isinstance(gen.get("FiberCoupled"), bool):
            return bool(gen["FiberCoupled"])
        v = r.get("FiberCoupled")
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.strip().lower() in ("1", "true", "yes", "on")
        return True

    def _ensure_arroyo_laser_off_after_step(self, _step_label: str) -> None:
        """Turn Arroyo laser off after a sequence step (safety); refresh Main GUI readbacks. No status-log line — pass/fail reasons use Reason for Failure only."""
        bridge = getattr(self, "_bridge", None)
        if bridge is None:
            return
        arroyo = bridge.get_arroyo()
        if arroyo is None:
            return
        try:
            if not getattr(arroyo, "is_connected", lambda: False)():
                return
        except Exception:
            return
        try:
            arroyo_laser_off(arroyo)
        except Exception:
            pass
        mw = getattr(self, "main_window", None)
        if mw is not None and hasattr(mw, "refresh_arroyo_after_worker_laser_off"):
            try:
                QMetaObject.invokeMethod(
                    mw,
                    "refresh_arroyo_after_worker_laser_off",
                    QtCompat.QueuedConnection,
                )
            except Exception:
                pass

    def _more_tests_follow_in_sequence(self) -> bool:
        """True when at least one further TEST_SEQUENCE entry will run after the current step."""
        try:
            return int(getattr(self, "_tests_remaining_after_current_step", 0) or 0) > 0
        except Exception:
            return False

    def _log_to_session(self, msg: str) -> None:
        s = getattr(self, "_result_session", None)
        if s is not None:
            s.append_log(msg)

    def _ensure_placeholder_result(self, stem: str, message: str) -> None:
        """If ``stem`` has no saved JSON yet, write a minimal placeholder (failed prereq, save error, etc.)."""
        s = getattr(self, "_result_session", None)
        if s is None:
            return
        try:
            if s.has_result(stem):
                return
            s.ensure_placeholder_result(stem, [message])
        except Exception:
            pass

    def run(self) -> bool:
        """Run TEST_SEQUENCE in order; return True if all steps passed."""
        self._stop_requested = False
        self._stop_from_user = False
        self._laser_monitor_armed = False
        self._laser_abort_emitted = False
        self._laser_abort_step = ""
        self._sequence_stopped_by_user = False
        self.log_message.emit("Starting test sequence…")
        if not self._test_sequence or self._recipe is None:
            self.log_message.emit("No test sequence or recipe loaded.")
            self._emit_step_failed(
                "TEST_SEQUENCE",
                ["No test sequence or recipe loaded. Load a recipe with TEST_SEQUENCE before starting."],
            )
            return False

        recipe = self._recipe if isinstance(self._recipe, dict) else {}
        recipe_name = ""
        mw = getattr(self, "main_window", None)
        if mw is not None:
            try:
                rp = getattr(mw, "_current_recipe_path", None) or getattr(mw, "_recipe_tab_path", None) or ""
                if rp:
                    from pathlib import Path as _P
                    recipe_name = _P(str(rp)).stem
            except Exception:
                pass
        if not recipe_name:
            recipe_name = str(recipe.get("name", recipe.get("GENERAL", {}).get("name", "unknown")))

        session: Any = None
        if ResultSession is None:
            self.log_message.emit(
                "Note: result archive is disabled (could not import operations.result_saver); nothing is written under results/."
            )
        else:
            try:
                session = ResultSession(recipe_name, recipe_data=recipe, test_sequence=list(self._test_sequence))
            except Exception as ex:
                session = None
                self.log_message.emit("Could not create result session (results not saved): {}".format(ex))
        self._result_session = session

        log_connections: list = []
        if session is not None:
            def _make_log_slot(prefix: str):
                def _slot(msg: str) -> None:
                    session.append_log("[{}] {}".format(prefix, msg))
                return _slot
            for sig_name, prefix in (
                ("log_message", "SEQ"), ("liv_log_message", "LIV"),
                ("per_log_message", "PER"), ("spectrum_log_message", "SPEC"),
                ("stability_log_message", "TS"),
            ):
                sig = getattr(self, sig_name, None)
                if sig is not None:
                    slot = _make_log_slot(prefix)
                    try:
                        sig.connect(slot)
                        log_connections.append((sig, slot))
                    except Exception:
                        pass

        try:
            seq_human = ", ".join(str(x).strip() for x in self._test_sequence if str(x).strip())
        except Exception:
            seq_human = ""
        if seq_human:
            self.log_message.emit("Sequence order: {}.".format(seq_human))

        all_passed = True
        try:
            seq_list = [str(x) for x in self._test_sequence]
            ts1_in_sequence = any(_stability_slot_from_test_name(x) == 1 for x in seq_list)
            ts1_passed: Optional[bool] = None
            nseq = len(self._test_sequence)

            for idx, test_name in enumerate(self._test_sequence):
                self._tests_remaining_after_current_step = max(0, nseq - idx - 1)
                if self._stop_requested:
                    if bool(getattr(self, "_stop_from_user", False)):
                        self._sequence_stopped_by_user = True
                        self.log_message.emit("STOP: Test sequence aborted by user.")
                        self.log_message.emit(
                            "Sequence: stopped by user — step {} of {} not started or not completed.".format(
                                idx + 1, nseq
                            )
                        )
                    all_passed = False
                    break
                self._laser_abort_step = str(test_name).strip() or "TEST_SEQUENCE"
                name_upper = (test_name or "").strip().upper()
                if not name_upper:
                    continue
                stab_slot = _stability_slot_from_test_name(str(test_name))
                if stab_slot is not None:
                    if stab_slot == 2 and ts1_in_sequence and ts1_passed is False:
                        self.log_message.emit(
                            "Sequence: {!r} skipped — Temperature Stability 1 did not pass.".format(
                                str(test_name).strip()
                            )
                        )
                        self.log_message.emit("Temperature Stability 2 skipped (Temperature Stability 1 did not pass).")
                        self._emit_step_failed(
                            str(test_name),
                            ["Temperature Stability 2 skipped because Temperature Stability 1 did not pass."],
                        )
                        all_passed = False
                        if session is not None:
                            session.ensure_placeholder_result(
                                "ts2",
                                ["Temperature Stability 2 skipped because Temperature Stability 1 did not pass."],
                            )
                        continue
                    self.log_message.emit("Sequence: {!r} started.".format(str(test_name).strip()))
                    self.stability_log_message.emit("Starting {}…".format(test_name))
                    step_ok = self._run_temperature_stability(recipe, stab_slot, str(test_name))
                    if stab_slot == 1:
                        ts1_passed = step_ok
                    if not step_ok:
                        all_passed = False
                    self.log_message.emit(
                        "Sequence: {!r} finished — {}.".format(
                            str(test_name).strip(), "PASS" if step_ok else "FAIL"
                        )
                    )
                    self.stability_log_message.emit("{} completed.".format(test_name))
                    self._ensure_placeholder_result(
                        "ts{}".format(int(stab_slot)),
                        "Temperature Stability finished without a saved measurement payload.",
                    )
                    continue
                if name_upper == "LIV":
                    self.log_message.emit("Sequence: {!r} started.".format(str(test_name).strip()))
                    self.liv_log_message.emit("Starting LIV test…")
                    step_ok = self._run_liv(recipe)
                    if not step_ok:
                        all_passed = False
                    self.log_message.emit(
                        "Sequence: {!r} finished — {}.".format(
                            str(test_name).strip(), "PASS" if step_ok else "FAIL"
                        )
                    )
                    self.liv_log_message.emit("LIV test completed.")
                    self._ensure_placeholder_result(
                        "liv",
                        "LIV did not write a measurement file (failed before sweep, stopped, or save error).",
                    )
                elif name_upper == "PER":
                    self.log_message.emit("Sequence: {!r} started.".format(str(test_name).strip()))
                    self.per_log_message.emit("Starting PER test…")
                    step_ok = self._run_per(recipe)
                    if not step_ok:
                        all_passed = False
                    self.log_message.emit(
                        "Sequence: {!r} finished — {}.".format(
                            str(test_name).strip(), "PASS" if step_ok else "FAIL"
                        )
                    )
                    self.per_log_message.emit("PER test completed.")
                    self._ensure_placeholder_result(
                        "per",
                        "PER did not write a measurement file (failed before sweep, stopped, or save error).",
                    )
                elif name_upper == "SPECTRUM":
                    self.log_message.emit("Sequence: {!r} started.".format(str(test_name).strip()))
                    self.spectrum_log_message.emit("Starting Spectrum test…")
                    step_ok = self._run_spectrum(recipe)
                    if not step_ok:
                        all_passed = False
                    self.log_message.emit(
                        "Sequence: {!r} finished — {}.".format(
                            str(test_name).strip(), "PASS" if step_ok else "FAIL"
                        )
                    )
                    self.spectrum_log_message.emit("Spectrum test completed.")
                    self._ensure_placeholder_result(
                        "spectrum",
                        "Spectrum did not write a measurement file (failed before sweep, stopped, or save error).",
                    )
                else:
                    self.log_message.emit("Sequence: {!r} started.".format(str(test_name).strip()))
                    self.log_message.emit(f"Test {test_name} not implemented.")
                    self._emit_step_failed(
                        str(test_name),
                        ["Test type {!r} is not implemented.".format(test_name)],
                    )
                    self.log_message.emit(
                        "Sequence: {!r} finished — FAIL (not implemented).".format(str(test_name).strip())
                    )
                    all_passed = False

            self._ensure_arroyo_laser_off_after_step("sequence end")

            if self._stop_requested:
                all_passed = False

            if getattr(self, "_sequence_stopped_by_user", False):
                self.log_message.emit("Sequence: test run ended — STOPPED BY USER (results saved if possible).")
            elif all_passed:
                self.log_message.emit("Sequence: test run ended — ALL STEPS PASSED (results saved if possible).")
            else:
                self.log_message.emit("Sequence: test run ended — ONE OR MORE STEPS FAILED (results saved if possible).")

        finally:
            for sig, slot in log_connections:
                try:
                    sig.disconnect(slot)
                except Exception:
                    pass
            if session is not None:
                try:
                    session.set_overall(all_passed, stopped=bool(self._sequence_stopped_by_user))
                    session.save()
                except Exception as e:
                    self.log_message.emit("Could not save results: {}".format(e))
            self._result_session = None

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
            QMetaObject.invokeMethod(mw, "pausePollingForLiv", QtCompat.BlockingQueuedConnection)
            _post_pause_poll_settle()
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
            s = getattr(self, "_result_session", None)
            if s is not None:
                try:
                    s.set_liv_result(result)
                except Exception as ex:
                    self.liv_log_message.emit("Warning: could not save LIV result to disk: {}".format(ex))
                    s.ensure_placeholder_result("liv", ["LIV result serialization failed: {}".format(ex)])
            ok = bool(result.passed)
            if not ok:
                reasons = list(getattr(result, "fail_reasons", None) or [])
                if not reasons:
                    reasons = [
                        "LIV: step reported FAIL but no failure messages were attached — check the LIV log and connection status.",
                    ]
                self._emit_step_failed("LIV", reasons)
            return ok
        except Exception as e:
            self.liv_log_message.emit(f"LIV error: {e}")
            self._emit_step_failed("LIV", ["LIV error: {}".format(e)])
            return False
        finally:
            self._laser_monitor_armed = False
            # Resume UI polling on main thread (timers cannot be started from this worker thread)
            if mw is not None and hasattr(mw, "resumePollingAfterLiv"):
                QMetaObject.invokeMethod(mw, "resumePollingAfterLiv", QtCompat.BlockingQueuedConnection)

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
            QMetaObject.invokeMethod(mw, "pausePollingForLiv", QtCompat.BlockingQueuedConnection)
            _post_pause_poll_settle()
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
            self._emit_arroyo_snapshot(arroyo)

            params = PERProcessParameters.from_recipe(recipe_dict)
            params_dict = {
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
            # Open PER window on the GUI thread *before* per.run() — same pattern as Spectrum.
            # Do **not** treat invokeMethod's return value as failure: PyQt often returns False/None for
            # void @pyqtSlot methods even when the slot ran; a Queued fallback then opened a second window
            # after per.run() started (race) or closed the first window and broke live signal connections.
            self._pending_per_window_params = params_dict
            mw_per = getattr(self, "main_window", None)
            if mw_per is not None:
                try:
                    QMetaObject.invokeMethod(
                        mw_per,
                        "blocking_open_per_test_window",
                        QtCompat.BlockingQueuedConnection,
                    )
                except Exception:
                    # Rare: invoke not delivered — BlockingQueued signal so the worker does not enter
                    # per.run() until the separate PER window exists (main_window uses Blocking for this).
                    self.per_process_window_requested.emit(params_dict)
            else:
                self.per_process_window_requested.emit(params_dict)
            self._pending_per_window_params = None
            self.per_log_message.emit(
                "PER: Arroyo + Thorlabs (VISA) + PRM (Kinesis); RCP laser conditions applied, laser ON."
            )
            self._laser_monitor_armed = True
            per = PERProcess()
            per.set_instruments(thorlabs_pm=thorlabs, prm=prm, actuator=actuator)
            result = per.run(
                params,
                executor=self,
                stop_requested=self._stop_requested_or_laser_off,
                recipe=recipe_dict,
            )
            s = getattr(self, "_result_session", None)
            if s is not None:
                try:
                    s.set_per_result(result)
                except Exception as ex:
                    self.per_log_message.emit("Warning: could not save PER result to disk: {}".format(ex))
                    s.ensure_placeholder_result("per", ["PER result serialization failed: {}".format(ex)])
            passed = bool(result.passed)
            if not passed:
                reasons = list(getattr(result, "fail_reasons", None) or [])
                if not reasons:
                    reasons = [
                        "PER: step reported FAIL but no failure messages were attached — check the PER log and connection status.",
                    ]
                self._emit_step_failed("PER", reasons)
            return passed
        except Exception as e:
            self.per_log_message.emit(f"PER error: {e}")
            self._emit_step_failed("PER", ["PER error: {}".format(e)])
            return False
        finally:
            self._laser_monitor_armed = False
            # Default: turn laser off when PER exits (pass/fail/stop) — enclosure safety.
            # Opt out: recipe OPERATIONS.PER.keep_laser_on_after / GENERAL.keep_laser_on_after_per, or BF_PER_KEEP_LASER_ON=1
            try:
                keep = per_keep_laser_on_after_step(recipe_dict) or self._more_tests_follow_in_sequence()
                if keep:
                    if self._more_tests_follow_in_sequence() and not per_keep_laser_on_after_step(recipe_dict):
                        self.per_log_message.emit(
                            "PER: Arroyo laser left ON — more tests follow in this sequence."
                        )
                    else:
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
            self._emit_arroyo_snapshot(arroyo)
            if mw is not None and hasattr(mw, "resumePollingAfterLiv"):
                QMetaObject.invokeMethod(mw, "resumePollingAfterLiv", QtCompat.BlockingQueuedConnection)

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
            except Exception as ex:
                self.spectrum_log_message.emit("Spectrum: could not build RCP summary for window (using blanks): {}".format(ex))
        self._spectrum_window_params_pending = params_dict

        mw = getattr(self, "main_window", None)
        if mw is not None:
            QMetaObject.invokeMethod(
                mw,
                "blocking_open_spectrum_test_window",
                QtCompat.BlockingQueuedConnection,
            )
        else:
            self.spectrum_process_window_requested.emit(params_dict)

        if mw is not None and hasattr(mw, "pausePollingForLiv"):
            QMetaObject.invokeMethod(mw, "pausePollingForLiv", QtCompat.BlockingQueuedConnection)
            _post_pause_poll_settle()
        self._emit_arroyo_snapshot(arroyo)
        try:
            spec = SpectrumProcess()
            spec.set_instruments(arroyo=arroyo, ando=ando, wavemeter=wavemeter)
            result = spec.run(
                recipe_dict,
                executor=self,
                stop_requested=self._stop_requested_or_laser_off,
            )
            s = getattr(self, "_result_session", None)
            if s is not None:
                try:
                    s.set_spectrum_result(result)
                except Exception as ex:
                    self.spectrum_log_message.emit("Warning: could not save Spectrum result to disk: {}".format(ex))
                    s.ensure_placeholder_result("spectrum", ["Spectrum result serialization failed: {}".format(ex)])
            ok = bool(result.passed)
            if not ok:
                reasons = list(getattr(result, "fail_reasons", None) or [])
                if not reasons:
                    reasons = [
                        "Spectrum: step reported FAIL but no failure messages were attached — check the Spectrum log.",
                    ]
                self._emit_step_failed("SPECTRUM", reasons)
            return ok
        except Exception as e:
            self.spectrum_log_message.emit(f"Spectrum error: {e}")
            self._emit_step_failed("SPECTRUM", ["Spectrum error: {}".format(e)])
            return False
        finally:
            self._laser_monitor_armed = False
            try:
                keep = spectrum_keep_laser_on_after_step(recipe_dict) or self._more_tests_follow_in_sequence()
                if keep:
                    if self._more_tests_follow_in_sequence() and not spectrum_keep_laser_on_after_step(recipe_dict):
                        self.spectrum_log_message.emit(
                            "Spectrum: Arroyo laser left ON — more tests follow in this sequence."
                        )
                    else:
                        self.spectrum_log_message.emit(
                            "Spectrum: Arroyo laser left ON (keep_laser_on_after in recipe or BF_SPECTRUM_KEEP_LASER_ON)."
                        )
                else:
                    arroyo_laser_off(arroyo)
                    self.spectrum_log_message.emit("Spectrum: Arroyo laser output OFF (step ended).")
            except Exception:
                pass
            self._emit_arroyo_snapshot(arroyo)
            if mw is not None and hasattr(mw, "resumePollingAfterLiv"):
                QMetaObject.invokeMethod(mw, "resumePollingAfterLiv", QtCompat.BlockingQueuedConnection)

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
        thorlabs = bridge.get_instrument("Thorlabs")
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
        if thorlabs is None or not getattr(thorlabs, "is_connected", lambda: False)():
            self.stability_log_message.emit("Temperature stability requires Thorlabs powermeter connected.")
            self._emit_step_failed(
                step_name,
                ["Thorlabs powermeter is not connected — connect it in the Connection tab (required for Temperature Stability)."],
            )
            return False

        params_obj = TemperatureStabilityParameters.from_recipe_blocks(recipe_dict, slot)
        try:
            import dataclasses

            pr_dict = dataclasses.asdict(params_obj)
        except Exception:
            pr_dict = {}
        pending = {"slot": slot, "params": pr_dict, "step_name": step_name}
        self._stability_window_params_pending = pending
        mw = getattr(self, "main_window", None)
        rcp_path_for_ts = ""
        if mw is not None:
            try:
                rcp_path_for_ts = str(
                    getattr(mw, "_current_recipe_path", None) or getattr(mw, "_recipe_tab_path", None) or ""
                )
            except Exception:
                rcp_path_for_ts = ""
        if mw is not None:
            try:
                setattr(mw, "_stability_window_open_params", pending)
            except Exception:
                pass
            # Same as Spectrum: BlockingQueuedConnection to MainWindow — signal was never connected, so emit did nothing.
            try:
                QMetaObject.invokeMethod(
                    mw,
                    "blocking_open_stability_test_window",
                    QtCompat.BlockingQueuedConnection,
                )
            except Exception:
                self.stability_log_message.emit("Temperature Stability: could not open secondary window (invoke failed).")
        else:
            self.stability_log_message.emit("No main window — cannot open stability secondary window.")

        if mw is not None and hasattr(mw, "pausePollingForStability"):
            QMetaObject.invokeMethod(mw, "pausePollingForStability", QtCompat.BlockingQueuedConnection)
            _post_pause_poll_settle()
        self._stability_live_slot = int(slot)
        try:
            proc = TemperatureStabilityProcess()
            proc.set_instruments(arroyo=arroyo, ando=ando, thorlabs=thorlabs)
            result = proc.run(
                recipe_dict,
                self,
                slot,
                stop_requested=self._stop_requested_or_laser_off,
                step_label=step_name,
                recipe_file_path=rcp_path_for_ts,
            )
            s = getattr(self, "_result_session", None)
            if s is not None:
                try:
                    s.set_stability_result(slot, result)
                except Exception as ex:
                    self.stability_log_message.emit("Warning: could not save Temperature Stability result: {}".format(ex))
                    s.ensure_placeholder_result(
                        "ts{}".format(int(slot)),
                        ["Temperature Stability result serialization failed: {}".format(ex)],
                    )
            ok = bool(result.passed)
            if not ok:
                reasons = list(getattr(result, "fail_reasons", None) or [])
                if not reasons:
                    reasons = [
                        "{}: step reported FAIL but no failure messages were attached — check the Temperature Stability log.".format(
                            step_name
                        ),
                    ]
                self._emit_step_failed(step_name, reasons)
            return ok
        except Exception as e:
            self.stability_log_message.emit("Temperature stability error: {}".format(e))
            self._emit_step_failed(step_name, ["Temperature stability error: {}".format(e)])
            return False
        finally:
            self._laser_monitor_armed = False
            try:
                ss = getattr(ando, "stop_sweep", None)
                if callable(ss):
                    ss()
            except Exception:
                pass
            try:
                keep = spectrum_keep_laser_on_after_step(recipe_dict) or self._more_tests_follow_in_sequence()
                if keep:
                    if self._more_tests_follow_in_sequence() and not spectrum_keep_laser_on_after_step(recipe_dict):
                        self.stability_log_message.emit(
                            "Stability: Arroyo laser left ON — more tests follow in this sequence."
                        )
                    else:
                        self.stability_log_message.emit(
                            "Stability: Arroyo laser left ON (keep_laser_on_after / BF_SPECTRUM_KEEP_LASER_ON)."
                        )
                else:
                    arroyo_laser_off(arroyo)
                    self.stability_log_message.emit("Stability: Arroyo laser output OFF (step ended).")
            except Exception:
                pass
            self._emit_arroyo_snapshot(arroyo)
            if mw is not None and hasattr(mw, "resumePollingAfterLiv"):
                QMetaObject.invokeMethod(mw, "resumePollingAfterLiv", QtCompat.BlockingQueuedConnection)
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
            if getattr(self.executor, "_stop_requested", False) and bool(
                getattr(self.executor, "_stop_from_user", False)
            ):
                setattr(self.executor, "_sequence_stopped_by_user", True)
                try:
                    self.executor.log_message.emit("STOP: Test sequence ended (stop requested).")
                except Exception:
                    pass
                self.sequence_stopped.emit()
            else:
                self.sequence_completed.emit(False)
