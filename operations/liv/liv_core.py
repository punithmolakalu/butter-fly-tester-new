"""
Full LIV process per flowchart/LIV_PROCESS.md.
Uses an executor (TestSequenceExecutor) for UI callbacks: window, prompts, alignment, plot updates, result.
"""
from __future__ import annotations

import time
import threading
from dataclasses import dataclass, field

from operations.arroyo_laser_helpers import arroyo_laser_off, arroyo_laser_on_safe
from operations.pass_fail_recipe import apply_liv_pass_fail_criteria
from typing import Any, Dict, List, Optional, cast

# Optional PyQt for thread
try:
    from PyQt5.QtCore import QObject, pyqtSignal, QThread
    _QT_AVAILABLE = True
except ImportError:
    _QT_AVAILABLE = False
    QObject = None  # type: ignore[misc, assignment]


def _to_float(value: Any) -> float:
    """Convert value to float for type checker; return 0.0 if not convertible."""
    if value is None:
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _get_float(d: Any, *keys: str, default: float = 0.0) -> float:
    if not keys:
        return default
    v = d
    for k in keys:
        if isinstance(v, dict) and k in v:
            v = v[k]
        else:
            return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _read_arroyo_laser_voltage_v(arroyo: Any) -> float:
    """
    Laser forward voltage readback (V), same path as tools/read_arroyo_pd_voltage.py:
    prefer laser_read_voltage(), else LAS:LDV?.
    """
    try:
        fn = getattr(arroyo, "laser_read_voltage", None)
        if callable(fn):
            v = fn()
            if v is not None:
                return float(v)
    except (TypeError, ValueError):
        pass
    except Exception:
        pass
    try:
        q = getattr(arroyo, "query", None)
        if callable(q):
            r = q("LAS:LDV?")
            if r is not None and str(r).strip():
                return float(str(r).strip())
    except Exception:
        pass
    return 0.0


def _read_arroyo_monitor_diode_raw(arroyo: Any) -> float:
    """
    Monitor photodiode readback (LAS:MDI?), raw instrument scalar — no µA rescaling.
    Matches terminal / Arroyo front-panel style values (e.g. ~19 at moderate drive).
    """
    try:
        fn = getattr(arroyo, "laser_read_monitor_diode_current", None)
        if callable(fn):
            v = fn()
            if v is not None:
                return float(v)
    except (TypeError, ValueError):
        pass
    except Exception:
        pass
    try:
        fn2 = getattr(arroyo, "laser_read_monitor_diode_power", None)
        if callable(fn2):
            v = fn2()
            if v is not None:
                return float(v)
    except Exception:
        pass
    try:
        q = getattr(arroyo, "query", None)
        if callable(q):
            r = q("LAS:MDI?")
            if r is not None and str(r).strip():
                return float(str(r).strip())
    except Exception:
        pass
    return 0.0


@dataclass
class LIVMainParameters:
    """LIV parameters from recipe (OPERATIONS.LIV)."""
    fiber_coupled: bool = True
    min_current_mA: float = 0.0
    max_current_mA: float = 500.0
    increment_mA: float = 10.0
    wait_time_ms: float = 50.0
    temperature: float = 25.0
    rated_current_mA: float = 500.0
    rated_power_mW: float = 100.0
    se_data_points: int = 5

    @classmethod
    def from_recipe(cls, recipe: Dict[str, Any]) -> "LIVMainParameters":
        op = recipe.get("OPERATIONS") or recipe.get("operations") or {}
        liv = op.get("LIV") or op.get("liv") or {}
        gen = recipe.get("GENERAL") or recipe.get("general") or {}
        fiber = gen.get("FiberCoupled") if isinstance(gen.get("FiberCoupled"), bool) else recipe.get("FiberCoupled", True)
        return cls(
            fiber_coupled=bool(fiber),
            min_current_mA=_get_float(liv, "min_current_mA", default=0.0),
            max_current_mA=_get_float(liv, "max_current_mA", default=500.0),
            increment_mA=_get_float(liv, "increment_mA", default=10.0),
            wait_time_ms=_get_float(liv, "wait_time_ms", default=50.0),
            temperature=_get_float(liv, "temperature", default=25.0),
            rated_current_mA=_get_float(liv, "rated_current_mA", default=500.0),
            rated_power_mW=_get_float(liv, "rated_power_mW", default=100.0),
            se_data_points=int(_get_float(liv, "se_data_points", default=5)),
        )


@dataclass
class LIVProcessResult:
    """Result of the full LIV process (sweep + Thorlabs + pass/fail)."""
    passed: bool = False
    fail_reasons: List[str] = field(default_factory=list)
    current_array: List[float] = field(default_factory=list)
    gentec_power_array: List[float] = field(default_factory=list)
    power_array: List[float] = field(default_factory=list)
    voltage_array: List[float] = field(default_factory=list)
    pd_array: List[float] = field(default_factory=list)
    tec_temp_min: float = 0.0
    tec_temp_max: float = 0.0
    final_power: float = 0.0
    thorlabs_average_power_mw: float = 0.0
    thorlabs_calib_factor: float = 1.0
    power_at_rated_current: float = 0.0
    current_at_rated_power: float = 0.0
    pd_at_rated_current: float = 0.0
    threshold_current: float = 0.0
    slope_efficiency: float = 0.0
    liv_result: Any = None  # self for GUI compatibility

    def __post_init__(self) -> None:
        self.liv_result = self


_LIVMainBase: type = cast(type, QObject if _QT_AVAILABLE else object)


class LIVMain(_LIVMainBase):
    """Runs the full LIV process; uses executor for window, prompts, alignment, plot, result."""

    if _QT_AVAILABLE:
        status_message = pyqtSignal(str)

    def __init__(self, parent: Any = None) -> None:
        if _QT_AVAILABLE and QObject is not None:
            super().__init__(parent)
        self._arroyo: Any = None
        self._gentec: Any = None
        self._thorlabs_pm: Any = None
        self._actuator: Any = None
        self._ando: Any = None

    def set_instruments(
        self,
        arroyo: Any = None,
        gentec: Any = None,
        thorlabs_pm: Any = None,
        actuator: Any = None,
        ando: Any = None,
    ) -> None:
        self._arroyo = arroyo
        self._gentec = gentec
        self._thorlabs_pm = thorlabs_pm
        self._actuator = actuator
        self._ando = ando

    def _emit(self, executor: Any, name: str, *args: Any) -> None:
        sig = getattr(executor, name, None)
        if sig is not None and hasattr(sig, "emit"):
            sig.emit(*args)

    def _emit_status(self, executor: Any, message: str) -> None:
        """Emit status to LIV floating window log (liv_log_message) and optional status_message signal."""
        sig = getattr(executor, "liv_log_message", None)
        if sig is not None and hasattr(sig, "emit"):
            sig.emit(message)
        else:
            self._emit(executor, "log_message", message)
        if _QT_AVAILABLE and hasattr(self, "status_message"):
            self.status_message.emit(message)

    def _wait_prompt_ack(self, executor: Any) -> None:
        cond = getattr(executor, "_liv_prompt_condition", None)
        if cond is not None:
            with cond:
                cond.wait(timeout=300)

    def _wait_connect_fiber(self, executor: Any) -> bool:
        cond = getattr(executor, "_connect_fiber_condition", None)
        ack = getattr(executor, "_connect_fiber_ack", None)
        if cond is not None:
            with cond:
                executor._connect_fiber_ack = None
                cond.wait(timeout=300)
                ack = getattr(executor, "_connect_fiber_ack", None)
        return ack is True

    def _wait_alignment(self, executor: Any) -> bool:
        cond = getattr(executor, "_alignment_condition", None)
        if cond is not None:
            with cond:
                executor._alignment_ack = None
                cond.wait(timeout=600)
                ack = getattr(executor, "_alignment_ack", True)
            return ack is True
        return True

    def _gentec_power_mw(self) -> float:
        if self._gentec is None:
            return 0.0
        m = getattr(self._gentec, "get_value_mw", None) or getattr(self._gentec, "read_power", None)
        if m is None:
            return 0.0
        try:
            v = m() if callable(m) else 0.0
            return _to_float(v)
        except Exception:
            return 0.0

    def _thorlabs_power_mw(self) -> float:
        if self._thorlabs_pm is None:
            return 0.0
        m = getattr(self._thorlabs_pm, "read_power_mw", None) or getattr(self._thorlabs_pm, "read_power_w", None)
        if m is None:
            return 0.0
        try:
            v = m() if callable(m) else None
            if v is None:
                return 0.0
            p = _to_float(v)
            if getattr(self._thorlabs_pm, "read_power_mw", None) == m:
                return p
            return p * 1000.0
        except Exception:
            return 0.0

    def _arroyo_connected(self) -> bool:
        """Return True if Arroyo connection is present and connected."""
        if self._arroyo is None:
            return False
        return bool(getattr(self._arroyo, "is_connected", lambda: True)())

    def _gentec_connected(self) -> bool:
        """Return True if Gentec connection is present and connected."""
        if self._gentec is None:
            return False
        return bool(getattr(self._gentec, "is_connected", lambda: True)())

    def _arroyo_laser_off(self) -> None:
        """Turn off Arroyo laser; never raise."""
        arroyo_laser_off(self._arroyo)

    def _arroyo_tec_on(self) -> None:
        """Turn on Arroyo TEC output; never raise."""
        try:
            if self._arroyo is not None and getattr(self._arroyo, "set_output", None):
                self._arroyo.set_output(1)
        except Exception:
            pass

    def _arroyo_laser_on_safe(self) -> None:
        """Turn on TEC then laser; skip each step if already ON (shared with GUI / PER). Never raise."""
        arroyo_laser_on_safe(self._arroyo)

    def _actuator_home_a(self) -> None:
        """Move actuator A to home; never raise."""
        try:
            if self._actuator is not None and getattr(self._actuator, "home_a", None):
                self._actuator.home_a()
        except Exception:
            pass

    def run(
        self,
        params: LIVMainParameters,
        executor: Any,
        recipe: Optional[Dict[str, Any]] = None,
    ) -> LIVProcessResult:
        """Run full LIV process; executor provides UI callbacks and wait conditions.
        Optional ``recipe`` (full dict) is used for PASS_FAIL_CRITERIA.LIV after measurements."""
        result = LIVProcessResult()
        if self._arroyo is None or self._gentec is None:
            result.fail_reasons.append("Missing Arroyo or Gentec")
            self._emit(executor, "liv_test_result", result)
            return result
        if not self._arroyo_connected():
            result.fail_reasons.append("Arroyo not connected. Connect Arroyo in the Connection tab.")
            self._emit(executor, "liv_test_result", result)
            return result
        if not self._gentec_connected():
            result.fail_reasons.append("Gentec not connected. Connect Gentec in the Connection tab.")
            self._emit(executor, "liv_test_result", result)
            return result

        # Defensive: ensure params is a LIVMainParameters object.
        p: LIVMainParameters
        if isinstance(params, LIVMainParameters):
            p = params
        elif isinstance(params, dict):
            p = LIVMainParameters.from_recipe(params)
        else:
            result.fail_reasons.append(
                f"Invalid LIV params type: {type(params).__name__}. Expected LIVMainParameters."
            )
            self._emit(executor, "liv_test_result", result)
            return result
        wait_s = max(0.001, p.wait_time_ms / 1000.0)
        num_steps = int((p.max_current_mA - p.min_current_mA) / p.increment_mA) + 1 if p.increment_mA > 0 else 0
        num_steps = max(0, min(10000, num_steps))

        try:
            self._emit_status(executor, "LIV: Starting.")
            if p.fiber_coupled:
                self._emit(executor, "connect_fiber_before_liv_requested", "Connect fiber to power meter before LIV.")
                if not self._wait_connect_fiber(executor):
                    result.fail_reasons.append("User cancelled connect fiber")
                    self._emit(executor, "liv_test_result", result)
                    return result
            else:
                # Not fiber-coupled: move actuator A in front of beam per flowchart
                if self._actuator is not None:
                    self._emit_status(executor, "LIV: Moving actuator in front of beam.")
                    try:
                        move_a = getattr(self._actuator, "move_a", None)
                        if move_a is not None and callable(move_a):
                            move_a(5.0)
                            time.sleep(0.5)
                    except Exception:
                        pass

            # 1) Set temperature setpoint first (Arroyo TEC)
            self._emit_status(executor, "LIV: Setting temperature (Arroyo).")
            try:
                set_temp = getattr(self._arroyo, "set_temp", None) or getattr(self._arroyo, "tec_set_temp", None)
                if set_temp is not None and callable(set_temp):
                    set_temp(p.temperature)
                    time.sleep(0.2)

                # IMPORTANT: temperature setpoint alone may not enable TEC output.
                # Enable TEC output before turning the laser on (laser may be interlocked on TEC).
                set_tec_out = getattr(self._arroyo, "set_output", None)
                if set_tec_out is not None and callable(set_tec_out):
                    set_tec_out(1)
                    time.sleep(0.2)
            except Exception as e:
                result.fail_reasons.append(f"Arroyo set temperature failed: {e}")
                self._emit(executor, "liv_pre_start_prompt_requested", "Could not set temperature.", {})
                self._wait_prompt_ack(executor)
                self._actuator_home_a()
                self._emit(executor, "liv_test_result", result)
                return result

            # 2) Set current limit and current, then turn laser on (Arroyo)
            self._emit_status(executor, "LIV: Turning on laser (Arroyo).")
            try:
                if getattr(self._arroyo, "laser_set_current_limit", None):
                    self._arroyo.laser_set_current_limit(p.max_current_mA)
                    time.sleep(0.15)
                if getattr(self._arroyo, "laser_set_current", None):
                    self._arroyo.laser_set_current(p.min_current_mA)
                    time.sleep(0.15)
                if getattr(self._arroyo, "laser_set_output", None):
                    self._arroyo_laser_on_safe()
            except Exception as e:
                result.fail_reasons.append(f"Laser set failed: {e}")
                self._emit(executor, "liv_pre_start_prompt_requested", "Laser could not turn on.", {})
                self._wait_prompt_ack(executor)
                self._actuator_home_a()
                self._emit(executor, "liv_test_result", result)
                return result

            time.sleep(0.5)
            on = getattr(self._arroyo, "laser_read_output", lambda: None)()
            if on != 1:
                result.fail_reasons.append("Laser did not turn on")
                self._emit(executor, "liv_pre_start_prompt_requested", "Laser could not turn on.", {})
                self._wait_prompt_ack(executor)
                self._arroyo_laser_off()
                self._actuator_home_a()
                self._emit(executor, "liv_test_result", result)
                return result

            # 3) Wait for temperature to stabilize within ±0.5 °C (after TEC+laser on)
            self._emit_status(executor, "LIV: Stabilizing temperature.")
            temp_ok = False
            for _ in range(120):
                if getattr(executor, "_stop_requested", False):
                    result.fail_reasons.append("Stopped by user")
                    result.passed = False
                    self._arroyo_laser_off()
                    self._emit(executor, "liv_test_result", result)
                    return result
                try:
                    actual = getattr(self._arroyo, "read_temp", None)
                    if actual is not None and callable(actual):
                        t = actual()
                        t_f = _to_float(t) if t is not None else 0.0
                        if t is not None and abs(t_f - p.temperature) <= 0.5:
                            temp_ok = True
                            break
                except Exception:
                    pass
                time.sleep(0.5)
            if not temp_ok:
                # Preserve original behavior: wait a little and continue even if not fully stable.
                time.sleep(1.0)

            # Request LIV process window (laser is on)
            self._emit(executor, "liv_process_window_requested", {"temperature": p.temperature, "min_current_mA": p.min_current_mA, "max_current_mA": p.max_current_mA})

            # Clear plot and run LIV sweep (Arroyo current steps, Gentec power, Arroyo voltage)
            self._emit_status(executor, "LIV: Running sweep (Arroyo + Gentec).")
            self._emit(executor, "liv_plot_clear")
            currents: List[float] = []
            powers: List[float] = []
            voltages: List[float] = []
            pd_list: List[float] = []
            temps_sweep: List[float] = []
            liv_sweep_stopped = False

            for i in range(num_steps):
                if getattr(executor, "_stop_requested", False):
                    liv_sweep_stopped = True
                    self._emit_status(executor, "LIV: Stop requested — exiting sweep.")
                    break
                cur = p.min_current_mA + i * p.increment_mA
                if cur > p.max_current_mA:
                    break
                try:
                    self._arroyo.laser_set_current(cur)
                except Exception:
                    pass
                time.sleep(wait_s)
                # Read back actual laser current and temperature at this point.
                cur_meas = cur
                try:
                    if getattr(self._arroyo, "laser_read_current", None):
                        c_read = self._arroyo.laser_read_current()
                        if c_read is not None:
                            cur_meas = float(c_read)
                except Exception:
                    pass
                try:
                    if getattr(self._arroyo, "read_temp", None):
                        t_r = self._arroyo.read_temp()
                        if t_r is not None:
                            temps_sweep.append(float(t_r))
                except Exception:
                    pass

                readings = []
                for _ in range(10):
                    readings.append(self._gentec_power_mw())
                avg_power = sum(readings) / len(readings) if readings else 0.0
                # Live power readout in LIV window: Gentec during sweep, Thorlabs not available yet.
                self._emit(executor, "liv_power_reading_update", avg_power, 0.0)
                v = _read_arroyo_laser_voltage_v(self._arroyo)
                pd_val = _read_arroyo_monitor_diode_raw(self._arroyo)
                currents.append(cur_meas)
                powers.append(avg_power)
                voltages.append(v)
                pd_list.append(pd_val)
                # Single update: current, Gentec power, LAS:LDV (V), LAS:MDI (raw) — matches terminal script.
                self._emit(executor, "liv_plot_update", cur_meas, avg_power, v, pd_val)

            result.current_array = currents
            result.gentec_power_array = powers
            result.power_array = powers
            result.voltage_array = voltages
            result.pd_array = pd_list
            if temps_sweep:
                result.tec_temp_min = min(temps_sweep)
                result.tec_temp_max = max(temps_sweep)
            else:
                result.tec_temp_min = float(p.temperature)
                result.tec_temp_max = float(p.temperature)
            result.final_power = powers[-1] if powers else 0.0

            if liv_sweep_stopped:
                result.fail_reasons.append("Stopped by user")
                result.passed = False
                self._emit(executor, "liv_test_result", result)
                return result

            # Fiber / alignment path
            if p.fiber_coupled:
                self._emit_status(executor, "LIV: Fiber path — connect fiber for Thorlabs.")
                try:
                    # Keep laser OFF before prompting user to connect fiber/splitter.
                    self._arroyo_laser_off()
                    time.sleep(0.3)
                except Exception:
                    pass
                self._emit(executor, "connect_fiber_before_liv_requested", "Connect fiber to power meter for Thorlabs calibration.")
                if not self._wait_connect_fiber(executor):
                    result.fail_reasons.append("User cancelled fiber connect")
                    self._arroyo_laser_off()
                    self._emit(executor, "liv_test_result", result)
                    return result
                self._emit(executor, "alignment_window_requested")
                if not self._wait_alignment(executor):
                    result.fail_reasons.append("Alignment cancelled")
                    self._arroyo_laser_off()
                    self._emit(executor, "liv_test_result", result)
                    return result
            else:
                # Non-fiber: move actuator A to home after sweep (per flowchart)
                self._actuator_home_a()

            # Thorlabs power meter: 10 readings average
            self._emit_status(executor, "LIV: Thorlabs power meter calibration.")
            thorlabs_readings = []
            for _ in range(10):
                t_mw = self._thorlabs_power_mw()
                thorlabs_readings.append(t_mw)
                # Keep latest Gentec final power visible while Thorlabs calibration runs.
                self._emit(executor, "liv_power_reading_update", result.final_power, t_mw)
            result.thorlabs_average_power_mw = sum(thorlabs_readings) / len(thorlabs_readings) if thorlabs_readings else 0.0
            if result.thorlabs_average_power_mw > 0:
                result.thorlabs_calib_factor = result.final_power / result.thorlabs_average_power_mw
            else:
                result.thorlabs_calib_factor = 1.0

            # Simple calculations
            if currents and powers:
                idx_rated = min(int((p.rated_current_mA - p.min_current_mA) / p.increment_mA), len(powers) - 1)
                idx_rated = max(0, idx_rated)
                result.power_at_rated_current = powers[idx_rated] if idx_rated < len(powers) else powers[-1]
                if pd_list and 0 <= idx_rated < len(pd_list):
                    result.pd_at_rated_current = float(pd_list[idx_rated])
                for i, pw in enumerate(powers):
                    if pw >= p.rated_power_mW:
                        result.current_at_rated_power = currents[i] if i < len(currents) else currents[-1]
                        break
                if len(currents) >= 2 and currents[0] < currents[-1]:
                    result.threshold_current = currents[0]
                    result.slope_efficiency = (powers[-1] - powers[0]) / (currents[-1] - currents[0]) if (currents[-1] - currents[0]) != 0 else 0.0

            apply_liv_pass_fail_criteria(recipe, result)
            result.passed = len(result.fail_reasons) == 0 and result.final_power >= 0
            self._emit_status(
                executor,
                "LIV: Recipe pass/fail criteria: {}.".format("PASS" if result.passed else "FAIL"),
            )
            self._emit(executor, "liv_test_result", result)
        except Exception as e:
            result.fail_reasons.append(str(e))
            result.passed = False
            self._emit(executor, "liv_test_result", result)
        finally:
            self._arroyo_laser_off()
            if not p.fiber_coupled and self._actuator is not None:
                self._actuator_home_a()

        return result


if _QT_AVAILABLE:

    class LIVMainThread(QThread):
        """Runs LIVMain.run(params, executor) in a worker thread."""
        test_completed = pyqtSignal(object)

        def __init__(
            self,
            liv_main: "LIVMain",
            params: "LIVMainParameters",
            executor: Any = None,
            parent: Any = None,
        ) -> None:
            super().__init__(parent)
            self._liv = liv_main
            self._params = params
            self._executor = executor
            self.result: Optional["LIVProcessResult"] = None

        def run(self) -> None:
            try:
                self.result = self._liv.run(self._params, self._executor or self._liv)
                self.test_completed.emit(self.result)
            except Exception as e:
                r = LIVProcessResult(passed=False, fail_reasons=[str(e)])
                self.result = r
                self.test_completed.emit(r)

else:
    LIVMainThread = None  # type: ignore
