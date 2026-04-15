"""
Full LIV process per flowchart/LIV_PROCESS.md.
Uses an executor (TestSequenceExecutor) for UI callbacks: window, prompts, alignment, plot updates, result.
"""
from __future__ import annotations

import math
import time
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


def _executor_sequence_should_stop(executor: Any) -> bool:
    """User Stop or TestSequenceExecutor laser-interlock abort."""
    if executor is None:
        return False
    fn = getattr(executor, "_stop_requested_or_laser_off", None)
    if callable(fn):
        try:
            return bool(fn())
        except Exception:
            pass
    return bool(getattr(executor, "_stop_requested", False))


def _liv_executor_has_more_sequence_steps(executor: Any) -> bool:
    """True when a multi-step TEST_SEQUENCE still has steps to run after the current one (executor sets counter)."""
    if executor is None:
        return False
    try:
        return int(getattr(executor, "_tests_remaining_after_current_step", 0) or 0) > 0
    except Exception:
        return False


def _liv_notify_laser_monitor_armed(executor: Any, armed: bool) -> None:
    fn = getattr(executor, "notify_laser_monitor_armed", None)
    if callable(fn):
        try:
            fn(bool(armed))
        except Exception:
            pass


def _to_float(value: Any) -> float:
    """Convert value to float; return 0.0 if not convertible. Avoid ``float(Any)`` for strict type checkers."""
    if value is None:
        return 0.0
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return 0.0
    try:
        return float(str(value).strip())
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
        return _float_any(v)
    except (TypeError, ValueError):
        return default


def _float_any(x: Any) -> float:
    """Convert instrument/readback to float; raises TypeError/ValueError if not numeric. No ``float(Any)``."""
    if isinstance(x, bool):
        return float(int(x))
    if isinstance(x, (int, float)):
        return float(x)
    if isinstance(x, str):
        return float(x.strip())
    return float(str(x).strip())


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
                try:
                    return _float_any(v)
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
                try:
                    return _float_any(v)
                except (TypeError, ValueError):
                    pass
    except Exception:
        pass
    try:
        fn2 = getattr(arroyo, "laser_read_monitor_diode_power", None)
        if callable(fn2):
            v = fn2()
            if v is not None:
                try:
                    return _float_any(v)
                except (TypeError, ValueError):
                    pass
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


def _liv_interp_power_at_current(currents_mA: List[float], powers_mW: List[float], i_target_mA: float) -> float:
    """
    Piecewise-linear P(I) on the **measured** L–I polyline only (no extrapolation past sweep ends).
    If ``i_target_mA`` is not on any segment of the polyline, returns ``0.0``.
    """
    i_ma = [float(x) for x in currents_mA]
    P = [float(x) for x in powers_mW]
    n = len(i_ma)
    if n == 0 or n != len(P):
        return 0.0
    iq = float(i_target_mA)
    if n == 1:
        tol = 1e-9 * max(1.0, abs(i_ma[0]))
        return float(P[0]) if abs(iq - i_ma[0]) <= tol else 0.0
    for j in range(n - 1):
        i0, i1 = i_ma[j], i_ma[j + 1]
        lo_i, hi_i = (i0, i1) if i0 <= i1 else (i1, i0)
        if iq + 1e-12 < lo_i or iq - 1e-12 > hi_i:
            continue
        d = i1 - i0
        if abs(d) < 1e-18:
            tol_i = 1e-9 * max(1.0, abs(i0))
            return float(P[j]) if abs(iq - i0) <= tol_i else 0.0
        t = (iq - i0) / d
        if t < -1e-9 or t > 1.0 + 1e-9:
            continue
        return float(P[j] + t * (P[j + 1] - P[j]))
    return 0.0


def _liv_interp_current_at_power(currents_mA: List[float], powers_mW: List[float], p_target_mW: float) -> float:
    """
    First intersection (left → right) of horizontal ``P = p_target_mW`` with the **measured**
    L–I polyline. Uses segment interiors and endpoints only — **no extrapolation** beyond measured
    power range (if the line never meets the curve, returns ``0.0``).
    """
    i_ma = [float(x) for x in currents_mA]
    P = [float(x) for x in powers_mW]
    n = len(i_ma)
    if n == 0 or n != len(P):
        return 0.0
    pq = float(p_target_mW)
    if pq < 0.0:
        return 0.0
    if n == 1:
        tol = 1e-9 * max(1.0, abs(P[0]))
        return float(i_ma[0]) if abs(pq - P[0]) <= tol else 0.0
    for j in range(n - 1):
        p0, p1 = P[j], P[j + 1]
        lo_p, hi_p = (p0, p1) if p0 <= p1 else (p1, p0)
        if pq + 1e-12 < lo_p or pq - 1e-12 > hi_p:
            continue
        d = p1 - p0
        if abs(d) < 1e-18:
            tol_p = 1e-9 * max(1.0, abs(p0))
            return float(i_ma[j]) if abs(pq - p0) <= tol_p else 0.0
        t = (pq - p0) / d
        if t < -1e-9 or t > 1.0 + 1e-9:
            continue
        return float(i_ma[j] + t * (i_ma[j + 1] - i_ma[j]))
    return 0.0


def _linear_regression_xy(i_ma: List[float], p_mw: List[float]) -> tuple[float, float, float]:
    """Least-squares line P = m*I + b. Returns (m, b, r_squared)."""
    n = len(i_ma)
    if n != len(p_mw) or n < 2:
        return 0.0, 0.0, 0.0
    mx = sum(i_ma) / n
    my = sum(p_mw) / n
    sxx = sum((x - mx) ** 2 for x in i_ma)
    if sxx < 1e-18:
        return 0.0, my, 0.0
    sxy = sum((i_ma[i] - mx) * (p_mw[i] - my) for i in range(n))
    m = sxy / sxx
    b = my - m * mx
    ss_res = sum((p_mw[i] - (m * i_ma[i] + b)) ** 2 for i in range(n))
    ss_tot = sum((p_mw[i] - my) ** 2 for i in range(n))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 1e-18 else 0.0
    return m, b, r2


# First L–I sample used for SE/Ith fit: power ≥ this fraction of sweep max (0.1% of P_max).
_LIV_SE_START_FRAC_OF_PMAX = 0.001


def _compute_liv_se_ith_method1(
    currents: List[float],
    powers: List[float],
    se_data_points: int,
) -> tuple[float, float, List[float], List[float], float]:
    """
    Method 1 (L–I): take **se_data_points** consecutive samples from the recipe
    (OPERATIONS.LIV.se_data_points, “# data points for SE calc”), starting at the **first**
    index where power ≥ 0.1% of the sweep maximum. Fit P = m·I + b on those points;
    slope efficiency SE = m (mW/mA); threshold Ith = −b/m (extrapolation to P = 0).

    If fewer than **se_data_points** samples remain after the start index, uses all consecutive
    points to the end of the sweep (still at least 2 points required for a line fit).

    Returns (se_mw_per_ma, ith_ma, slope_fit_currents, slope_fit_powers, fit_r2).
    """
    n = len(currents)
    if n != len(powers) or n < 2:
        return 0.0, 0.0, [], [], 0.0

    i_ma = [float(x) for x in currents]
    P = [float(x) for x in powers]

    pmax = max(P)
    if pmax <= 1e-12:
        return 0.0, 0.0, [], [], 0.0

    thr = _LIV_SE_START_FRAC_OF_PMAX * pmax
    i_start = next((i for i, p in enumerate(P) if p >= thr), None)
    if i_start is None:
        return 0.0, 0.0, [], [], 0.0

    # Recipe N (RCP “# data points for SE calc”); same floor as LIVMainParameters.from_recipe.
    n_target = se_data_points if se_data_points >= 3 else 10
    if n_target < 2:
        n_target = 2

    idxs: List[int] = []
    for k in range(n_target):
        j = i_start + k
        if j >= n:
            break
        idxs.append(j)
    if len(idxs) < 2:
        return 0.0, 0.0, [], [], 0.0

    i_fit = [i_ma[i] for i in idxs]
    p_fit = [P[i] for i in idxs]
    m, b, r2_final = _linear_regression_xy(i_fit, p_fit)

    if m <= 1e-12:
        return 0.0, 0.0, i_fit, p_fit, r2_final

    ith = -b / m
    return float(m), float(ith), i_fit, p_fit, float(r2_final)


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
    se_data_points: int = 10

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
            se_data_points=(
                sdp if (sdp := int(_get_float(liv, "se_data_points", default=10))) >= 3 else 10
            ),
        )


def _liv_sweep_current_points_mA(min_mA: float, max_mA: float, inc_mA: float) -> List[float]:
    """
    Monotonic sweep currents from min to **max inclusive**.

    ``int((max-min)/inc)+1`` steps miss the final recipe max when the span is not an exact
    multiple of ``inc`` (e.g. 0→100 mA in 30 mA steps would stop at 90 mA). LIV must read
    power and update the plot through **max_current_mA**.
    """
    lo = float(min_mA)
    hi = float(max_mA)
    step = float(inc_mA)
    if hi < lo:
        return []
    if abs(hi - lo) < 1e-18:
        return [hi]
    if step <= 0:
        return [lo, hi]
    out: List[float] = []
    cur = lo
    tol = 1e-6 * max(1.0, abs(hi))
    for _ in range(10000):
        cand = min(cur, hi)
        if not out or abs(cand - out[-1]) > 1e-12:
            out.append(cand)
        if cand >= hi - tol:
            break
        nxt = cur + step
        if nxt > hi - tol and cur < hi - tol:
            cur = hi
        else:
            cur = nxt
    return out


def liv_params_dict_for_ui(p: LIVMainParameters) -> Dict[str, Any]:
    """All LIV recipe fields for the LIV Process window (left panel labels)."""
    pts = _liv_sweep_current_points_mA(p.min_current_mA, p.max_current_mA, p.increment_mA)
    num_steps = max(0, min(10000, len(pts)))
    return {
        "fiber_coupled": p.fiber_coupled,
        "min_current_mA": p.min_current_mA,
        "max_current_mA": p.max_current_mA,
        "increment_mA": p.increment_mA,
        "wait_time_ms": p.wait_time_ms,
        "temperature": p.temperature,
        "rated_current_mA": p.rated_current_mA,
        "rated_power_mW": p.rated_power_mW,
        "se_data_points": p.se_data_points,
        "num_increments": num_steps,
    }


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
    voltage_at_rated_current_V: float = field(default_factory=lambda: float("nan"))
    voltage_at_rated_power_V: float = field(default_factory=lambda: float("nan"))
    threshold_current: float = 0.0
    slope_efficiency: float = 0.0
    slope_fit_currents: List[float] = field(default_factory=list)
    slope_fit_powers: List[float] = field(default_factory=list)
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
        rm = getattr(self._thorlabs_pm, "read_power_mw", None)
        if callable(rm):
            try:
                v = rm()
                if v is None:
                    return 0.0
                p = _to_float(v)
                return p if math.isfinite(p) else 0.0
            except Exception:
                return 0.0
        rw = getattr(self._thorlabs_pm, "read_power_w", None)
        if callable(rw):
            try:
                v = rw()
                if v is None:
                    return 0.0
                p = _to_float(v) * 1000.0
                return p if math.isfinite(p) else 0.0
            except Exception:
                return 0.0
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

    def _emit_arroyo_snapshot(self, executor: Any) -> None:
        """Read full Arroyo state and emit to Main tab Laser/TEC details."""
        ar = self._arroyo
        if ar is None or not getattr(ar, "is_connected", lambda: False)():
            return
        try:
            snap = ar.read_gui_snapshot()
            if not isinstance(snap, dict):
                return
            for sig_name in ("live_arroyo", "liv_live_arroyo"):
                sig = getattr(executor, sig_name, None)
                if sig is not None and hasattr(sig, "emit"):
                    sig.emit(snap)
        except Exception:
            pass

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

    def _set_laser_to_max_for_thorlabs_liv(
        self,
        p: "LIVMainParameters",
        executor: Any,
        wait_s: float,
    ) -> None:
        """Turn laser on at LIV max current before Thorlabs vs Gentec calibration."""
        if not self._arroyo_connected():
            return
        self._emit_status(
            executor,
            "LIV: Setting laser to {:.1f} mA (LIV max) for Thorlabs calibration.".format(p.max_current_mA),
        )
        try:
            lim = float(p.max_current_mA)
            if getattr(self._arroyo, "laser_set_current_limit", None):
                self._arroyo.laser_set_current_limit(max(lim, float(p.min_current_mA)))
                time.sleep(0.12)
            self._arroyo_laser_on_safe()
            time.sleep(0.2)
            if getattr(self._arroyo, "laser_set_current", None):
                self._arroyo.laser_set_current(lim)
            time.sleep(wait_s)
            time.sleep(0.15)
        except Exception:
            pass

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
        sweep_targets = _liv_sweep_current_points_mA(p.min_current_mA, p.max_current_mA, p.increment_mA)

        try:
            self._emit_status(executor, "LIV: Starting.")
            if p.fiber_coupled:
                self._emit(executor, "connect_fiber_before_liv_requested", "Connect fiber to Gentec powermeter.")
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
                self._emit_arroyo_snapshot(executor)
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
            self._emit_arroyo_snapshot(executor)
            on = getattr(self._arroyo, "laser_read_output", lambda: None)()
            if on != 1:
                result.fail_reasons.append("Laser did not turn on")
                self._emit(executor, "liv_pre_start_prompt_requested", "Laser could not turn on.", {})
                self._wait_prompt_ack(executor)
                self._arroyo_laser_off()
                self._actuator_home_a()
                self._emit(executor, "liv_test_result", result)
                return result

            _liv_notify_laser_monitor_armed(executor, True)

            # 3) Wait for temperature to stabilize within ±0.5 °C (after TEC+laser on)
            self._emit_status(executor, "LIV: Stabilizing temperature.")
            temp_ok = False
            for _ in range(120):
                if _executor_sequence_should_stop(executor):
                    if getattr(executor, "_stop_from_user", True):
                        result.fail_reasons.append("Stopped by user")
                    else:
                        result.fail_reasons.append(
                            "Arroyo laser output went OFF during LIV temperature wait — test stopped."
                        )
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
            self._emit(executor, "liv_process_window_requested", liv_params_dict_for_ui(p))

            # Clear plot and run LIV sweep (Arroyo current steps, Gentec power, Arroyo voltage)
            self._emit_status(executor, "LIV: Running sweep (Arroyo + Gentec).")
            self._emit(executor, "liv_plot_clear")
            currents: List[float] = []
            powers: List[float] = []
            voltages: List[float] = []
            pd_list: List[float] = []
            temps_sweep: List[float] = []
            liv_sweep_stopped = False

            for cur in sweep_targets:
                if _executor_sequence_should_stop(executor):
                    liv_sweep_stopped = True
                    self._emit_status(executor, "LIV: Stop requested — exiting sweep.")
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
                tec_last = float("nan")
                try:
                    if getattr(self._arroyo, "read_temp", None):
                        t_r = self._arroyo.read_temp()
                        if t_r is not None:
                            tec_last = float(t_r)
                            temps_sweep.append(tec_last)
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
                # Single update: current, Gentec power, LAS:LDV (V), LAS:MDI (raw), TEC temp — Main GUI mirrors while polling is paused.
                self._emit(executor, "liv_plot_update", cur_meas, avg_power, v, pd_val, tec_last)
                self._emit_arroyo_snapshot(executor)

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
            result.final_power = max(powers) if powers else 0.0

            if liv_sweep_stopped:
                if getattr(executor, "_stop_from_user", True):
                    result.fail_reasons.append("Stopped by user")
                else:
                    result.fail_reasons.append(
                        "Arroyo laser output went OFF during LIV sweep — test stopped."
                    )
                result.passed = False
                self._emit(executor, "liv_test_result", result)
                return result

            # Fiber / alignment path
            if p.fiber_coupled:
                self._emit_status(executor, "LIV: Fiber path — connect fiber for Thorlabs.")
                try:
                    _liv_notify_laser_monitor_armed(executor, False)
                    # Keep laser OFF before prompting user to connect fiber/splitter.
                    self._arroyo_laser_off()
                    time.sleep(0.3)
                except Exception:
                    pass
                self._emit(executor, "connect_fiber_before_liv_requested", "Connect fiber to splitter for alignment.")
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

            self._set_laser_to_max_for_thorlabs_liv(p, executor, wait_s)
            _liv_notify_laser_monitor_armed(executor, True)
            self._emit(executor, "liv_power_reading_update", result.final_power, 0.0)

            # Settle hardware before Thorlabs (shown in LIV Process log).
            self._emit_status(executor, "LIV: Waiting 1 s before Thorlabs power readings…")
            time.sleep(1.0)

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

            # Simple calculations — P@Ir and I@Pr from piecewise-linear interpolation on the L–I curve
            if currents and powers:
                result.power_at_rated_current = _liv_interp_power_at_current(
                    currents, powers, float(p.rated_current_mA)
                )
                result.current_at_rated_power = _liv_interp_current_at_power(
                    currents, powers, float(p.rated_power_mW)
                )
                if pd_list and len(pd_list) == len(currents):
                    result.pd_at_rated_current = _liv_interp_power_at_current(
                        currents, [float(x) for x in pd_list], float(p.rated_current_mA)
                    )
                if currents and voltages and len(currents) == len(voltages):
                    result.voltage_at_rated_current_V = _liv_interp_power_at_current(
                        currents, voltages, float(p.rated_current_mA)
                    )
                    ic_lp = result.current_at_rated_power
                    if math.isfinite(ic_lp) and float(ic_lp) > 0:
                        result.voltage_at_rated_power_V = _liv_interp_power_at_current(
                            currents, voltages, float(ic_lp)
                        )
                if len(currents) >= 2 and currents[0] < currents[-1]:
                    se, ith, sfc, sfp, r2_fit = _compute_liv_se_ith_method1(
                        currents, powers, p.se_data_points
                    )
                    result.slope_efficiency = se
                    result.threshold_current = ith
                    result.slope_fit_currents = sfc
                    result.slope_fit_powers = sfp
                    self._emit_status(
                        executor,
                        "LIV: SE & Ith — Method 1 linear fit R²={:.4f} ({} fit points).".format(
                            r2_fit,
                            len(sfc),
                        ),
                    )

            apply_liv_pass_fail_criteria(recipe, result)
            if result.final_power < 0:
                result.fail_reasons.append(
                    "LIV: Final Gentec power {:.6g} mW is invalid (negative); check detector.".format(
                        float(result.final_power)
                    )
                )
            result.passed = len(result.fail_reasons) == 0
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
            _liv_notify_laser_monitor_armed(executor, False)
            if not _liv_executor_has_more_sequence_steps(executor):
                self._arroyo_laser_off()
            else:
                self._emit_status(executor, "LIV: Arroyo laser left ON — more tests follow in this sequence.")
            self._emit_arroyo_snapshot(executor)
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
