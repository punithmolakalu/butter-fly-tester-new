"""
PER process implementation based on flowchart/PER_PROCESS.md.

Behavior:
- When run from the GUI test sequence, Arroyo TEC + drive current are applied and the laser is turned ON
  (and verified) in TestSequenceExecutor before this process runs; PER assumes beam is available for Thorlabs.
- PRM speed uses same set_speed(°/s, DEFAULT_ACCEL) as Manual Control; setup speed defaults to meas speed if omitted
- Continuous sweep: Thorlabs is read when |Δangle| ≥ meas speed (°/s), e.g. 5 °/s → every 5°, 10 °/s → every 10°
  (same idea as tests/per_prm_thorlabs_terminal_test.py). Position is polled each loop; loop sleep still respects
  wait_time and motion rate. If async MoveTo is unavailable, a worker thread runs blocking move_to(end)
  while the main loop samples (still continuous motion). Step-scan is last resort only (no move_to).
- Move PRM to start angle
- Rotate to end angle
- While rotating, keep reading Thorlabs power + PRM position
- Emit running updates for live PER plotting
- Compute final max power, min power, PER(dB), max angle
- Move PRM back to start
- Teardown "actuator home" means **actuator B only** (`home_b()`), not A or HOME BOTH.
- Recipe ``skip_actuator`` / env ``BF_PER_SKIP_ACTUATOR=1``: skip actuator B move and home (no 206 mm / travel-driven move).
- Console: each sample prints angle (deg) and Thorlabs (mW) when PER_TERMINAL_SAMPLES is on (default).
"""
from __future__ import annotations

import math
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from operations.pass_fail_recipe import apply_per_pass_fail_criteria

# Print every PER sample to the terminal (angle °, Thorlabs mW). Disable with env PER_TERMINAL_SAMPLES=0.
def _per_terminal_samples_enabled() -> bool:
    return os.environ.get("PER_TERMINAL_SAMPLES", "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _per_print_sample(sample_index: int, angle_deg: float, power_mw: float, mode: str) -> None:
    if not _per_terminal_samples_enabled():
        return
    print(
        "[PER] {:5d}  angle = {:10.4f} deg   Thorlabs = {:12.6g} mW   ({})".format(
            sample_index, float(angle_deg), float(power_mw), mode
        ),
        flush=True,
    )

# Same constants as Manual Control PRM / viewmodel._run_prm_move (instruments.prm).
try:
    from instruments.prm import DEFAULT_ACCEL as _PRM_DEFAULT_ACCEL, MAX_SPEED as _PRM_MAX_SPEED
except Exception:  # Kinesis optional on some installs
    _PRM_DEFAULT_ACCEL = 10.0
    _PRM_MAX_SPEED = 25.0

_PRM_MIN_VELOCITY_DEG_S = 0.1


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _get_float(d: Any, keys: List[str], default: float) -> float:
    if not isinstance(d, dict):
        return default
    for k in keys:
        if k in d:
            return _to_float(d.get(k), default)
    return default


def _get_bool(d: Any, keys: List[str], default: bool = False) -> bool:
    if not isinstance(d, dict):
        return default
    for k in keys:
        if k in d:
            v = d.get(k)
            if isinstance(v, bool):
                return v
            s = str(v).strip().lower()
            return s in ("1", "true", "yes", "on")
    return default


def _per_skip_actuator_from_env() -> bool:
    return os.environ.get("BF_PER_SKIP_ACTUATOR", "").strip().lower() in ("1", "true", "yes", "on")


def _clamp_prm_speed_deg_s(speed_deg_per_sec: float, default: float = 10.0) -> float:
    """Clamp recipe speed to valid PRM range; values are interpreted as degrees per second."""
    x = _to_float(speed_deg_per_sec, default=default)
    if x <= 0:
        x = default
    return max(_PRM_MIN_VELOCITY_DEG_S, min(x, float(_PRM_MAX_SPEED)))


def _per_power_read_spacing_deg(meas_speed_deg_per_sec: float) -> float:
    """
    Degrees between Thorlabs power reads during the meas sweep, matched to meas speed (°/s):
    5 °/s → read every 5°, 10 °/s → every 10°, etc. (clamped like PRM speed, min 0.1°).
    """
    sp = _clamp_prm_speed_deg_s(float(meas_speed_deg_per_sec or 10.0))
    return max(0.1, min(sp, 180.0))


@dataclass
class PERProcessParameters:
    start_angle_deg: float = 0.0
    travel_distance_deg: float = 180.0
    # Recipe "MeasSpeed" / "meas_speed": **degrees per second** on the PRM (Kinesis max velocity, typically ≤ 25).
    meas_speed_deg_per_sec: float = 10.0
    # Recipe "SetupSpeed" / "setup_speed": °/s for moves to/from start. If omitted/zero, uses meas_speed (avoids surprise 25 °/s).
    setup_speed_deg_per_sec: float = 10.0
    wait_time_ms: float = 50.0
    steps_per_degree: float = 10.0
    min_per_db: float = 0.0
    actuator_speed: float = 0.0
    actuator_distance: float = 0.0
    # If True: do not move actuator B before sweep or home B after (beam already aligned; Arroyo-only setups).
    skip_actuator: bool = False
    # Recipe wavelength (nm) for Thorlabs powermeter calibration; 0 = do not send SENS:WAV
    wavelength_nm: float = 0.0

    @classmethod
    def from_recipe(cls, recipe: Dict[str, Any]) -> "PERProcessParameters":
        op = recipe.get("OPERATIONS") or recipe.get("operations") or {}
        per = op.get("PER") or op.get("per") or {}
        pfc = recipe.get("PASS_FAIL_CRITERIA") or recipe.get("pass_fail_criteria") or {}
        pfc_per = pfc.get("PER") or pfc.get("per") or {}
        general = recipe.get("GENERAL") or recipe.get("general") or {}
        wl = _get_float(per, ["wavelength", "Wavelength"], 0.0)
        if wl <= 0:
            wl = _get_float(general, ["wavelength", "Wavelength"], 0.0)
        if wl <= 0:
            wl = _get_float(recipe, ["Wavelength"], 0.0)
        meas_spd = _get_float(per, ["meas_speed", "MeasSpeed"], 10.0)
        setup_raw = _get_float(per, ["setup_speed", "SetupSpeed"], 0.0)
        # If setup speed not set, match meas speed so entering "10" for meas is not overridden by old default 25 for setup.
        setup_spd = setup_raw if setup_raw > 0 else meas_spd
        return cls(
            start_angle_deg=_get_float(per, ["start_angle", "StartAngle"], 0.0),
            travel_distance_deg=_get_float(per, ["travel_distance", "TravelDistance"], 180.0),
            meas_speed_deg_per_sec=meas_spd,
            setup_speed_deg_per_sec=setup_spd,
            wait_time_ms=_get_float(per, ["wait_time_ms", "WaitTimeMs"], 50.0),
            steps_per_degree=max(1.0, _get_float(per, ["steps_per_degree", "StepsPerDegree"], 10.0)),
            min_per_db=_get_float(pfc_per, ["min_PER_dB", "MinPER_dB"], _get_float(per, ["MinPER_dB"], 0.0)),
            actuator_speed=_get_float(per, ["actuator_speed", "ActuatorSpeed"], 0.0),
            actuator_distance=_get_float(per, ["actuator_distance", "ActuatorDistance"], 0.0),
            skip_actuator=_get_bool(per, ["skip_actuator", "SkipActuator", "pause_actuator", "PauseActuator"], False)
            or _per_skip_actuator_from_env(),
            wavelength_nm=wl,
        )


@dataclass
class PERProcessResult:
    passed: bool = False
    is_final: bool = False
    fail_reasons: List[str] = field(default_factory=list)
    max_power: float = 0.0
    min_power: float = 0.0
    per_db: float = 0.0
    max_angle: float = 0.0
    positions_deg: List[float] = field(default_factory=list)
    powers_mw: List[float] = field(default_factory=list)
    # Seconds since sweep sampling started (aligned with positions_deg / powers_mw); for live time-vs-angle plot.
    sample_times_s: List[float] = field(default_factory=list)


class PERProcess:
    def __init__(self) -> None:
        self._thorlabs_pm: Any = None
        self._prm: Any = None
        self._actuator: Any = None
        self._skip_actuator_for_run: bool = False
        # Skip redundant set_speed + log when velocity unchanged (same as last hardware apply).
        self._prm_last_applied_speed_deg_s: Optional[float] = None

    def set_instruments(self, thorlabs_pm: Any = None, prm: Any = None, actuator: Any = None) -> None:
        self._thorlabs_pm = thorlabs_pm
        self._prm = prm
        self._actuator = actuator

    def _move_actuator_b_in_front_of_beam(
        self, params: PERProcessParameters, executor: Any, stop_requested: Callable[[], bool]
    ) -> bool:
        """
        Move actuator B in front of beam and wait until expected completion.
        Note: actuator API has no position readback, so wait uses distance/speed estimate.
        """
        if getattr(params, "skip_actuator", False):
            self._log(executor, "PER: skip_actuator — no actuator B move (recipe or BF_PER_SKIP_ACTUATOR).")
            return True
        if self._actuator is None:
            self._log(executor, "PER: Actuator not available; skip actuator B move.")
            return True
        # Use PER travel distance as the actuator move distance (requested behavior in PER recipe UI:
        # value under Start Angle / Travel Distance drives the actuator move).
        travel_dist = float(params.travel_distance_deg or 0.0)
        cfg_act_dist = float(params.actuator_distance or 0.0)
        dist = travel_dist if travel_dist > 0 else cfg_act_dist
        if dist <= 0:
            self._log(executor, "PER: Actuator B distance not set; skip move.")
            return True
        if travel_dist > 0:
            self._log(
                executor,
                "PER: Actuator B move distance = {:.4g} (from PER travel_distance).".format(dist),
            )
        elif cfg_act_dist > 0:
            self._log(
                executor,
                "PER: Actuator B move distance = {:.4g} (from actuator_distance fallback).".format(dist),
            )
        self._log(executor, "PER: Moving actuator B in front of beam.")
        try:
            ok = bool(self._actuator.move_b(dist))
        except Exception:
            ok = False
        if not ok:
            return False
        speed = float(params.actuator_speed or 0.0)
        est_sec = (dist / speed) if speed > 0 else 2.0
        wait_sec = max(1.0, est_sec + 0.75)
        t0 = time.time()
        while (time.time() - t0) < wait_sec:
            if stop_requested():
                return False
            time.sleep(0.05)
        self._log(executor, "PER: Actuator B reached measurement position.")
        return True

    def _home_actuator_b(self, executor: Any) -> None:
        """PER teardown: send **actuator B** home only (`home_b` / homeb) — not A, not both."""
        if self._skip_actuator_for_run:
            return
        if self._actuator is None:
            return
        try:
            self._log(executor, "PER: Sending actuator B to home (homeb).")
            self._actuator.home_b()
        except Exception:
            pass

    def _emit(self, executor: Any, name: str, *args: Any) -> None:
        sig = getattr(executor, name, None)
        if sig is not None and hasattr(sig, "emit"):
            sig.emit(*args)

    def _log(self, executor: Any, msg: str) -> None:
        sig = getattr(executor, "per_log_message", None)
        if sig is not None and hasattr(sig, "emit"):
            sig.emit(msg)
        else:
            self._emit(executor, "log_message", msg)

    def _apply_thorlabs_wavelength(self, wavelength_nm: float, executor: Any) -> bool:
        """
        Set Thorlabs head wavelength from recipe (real instrument calibration).
        Returns True if a wavelength command was sent successfully (caller may add extra settle + retries).
        """
        if self._thorlabs_pm is None or wavelength_nm is None or float(wavelength_nm) <= 0:
            return False
        fn = getattr(self._thorlabs_pm, "set_wavelength_nm", None)
        if not callable(fn):
            return False
        try:
            ok = bool(fn(float(wavelength_nm)))
            if ok:
                self._log(executor, "PER: Thorlabs wavelength set to {:.1f} nm (instrument).".format(float(wavelength_nm)))
            return ok
        except Exception as ex:
            self._log(executor, "PER: Thorlabs set_wavelength_nm failed: {}".format(ex))
            return False

    def _thorlabs_power_mw(self) -> Optional[float]:
        if self._thorlabs_pm is None:
            return None
        m = getattr(self._thorlabs_pm, "read_power_mw", None) or getattr(self._thorlabs_pm, "read_power_w", None)
        if m is None:
            return None
        try:
            v = m() if callable(m) else None
            if v is None:
                return None
            p = _to_float(v, default=-1.0)
            if p < 0:
                return None
            if getattr(self._thorlabs_pm, "read_power_mw", None) == m:
                return p
            return p * 1000.0
        except Exception:
            return None

    def _thorlabs_power_mw_precheck(self, executor: Any, *, wavelength_just_set: bool) -> Optional[float]:
        """
        First Thorlabs read after connect or after SENS:WAV often returns None / errors briefly.
        Retry with short delays before failing pre-check.
        """
        extra_first_delay = 0.25 if wavelength_just_set else 0.05
        time.sleep(extra_first_delay)
        attempts = 10 if wavelength_just_set else 6
        delay_s = 0.15
        last_fail_log = False
        for i in range(attempts):
            p = self._thorlabs_power_mw()
            if p is not None:
                if i > 0:
                    self._log(executor, "PER: Thorlabs read OK after {} retry(s).".format(i))
                return p
            if wavelength_just_set and i == 2 and not last_fail_log:
                self._log(
                    executor,
                    "PER: Waiting for Thorlabs after wavelength change (retries)…",
                )
                last_fail_log = True
            time.sleep(delay_s)
        return None

    def _emit_per_done(
        self,
        executor: Any,
        result: PERProcessResult,
        positions: List[float],
        powers: List[float],
        times_s: Optional[List[float]] = None,
    ) -> None:
        """Mark PER finished for UI (close live window, show pass/fail) and emit."""
        result.is_final = True
        if times_s is not None:
            result.sample_times_s = list(times_s)
        self._emit(executor, "per_test_result", result, list(positions), list(powers))

    def _prm_position_deg(self) -> Optional[float]:
        if self._prm is None:
            return None
        m = getattr(self._prm, "get_position", None)
        if m is None:
            return None
        try:
            v = m() if callable(m) else None
            return _to_float(v, default=float("nan")) if v is not None else None
        except Exception:
            return None

    def _prm_set_speed_manual(self, executor: Any, speed_deg_per_sec: float, role: str) -> bool:
        """
        Same path as Manual Control PRM box / viewmodel._run_prm_move:
        PRMConnection.set_speed(°/s, DEFAULT_ACCEL). Logs are minimal (no readback spam).
        """
        if self._prm is None:
            self._log(executor, "PER: PRM not connected; cannot set speed (°/s).")
            return False
        raw = _to_float(speed_deg_per_sec, default=0.0)
        if raw <= 0:
            raw = 10.0
            self._log(executor, "PER: Invalid/zero speed in recipe; using {:.1f} °/s ({}).".format(raw, role))
        clamped = _clamp_prm_speed_deg_s(raw, default=raw)
        last = self._prm_last_applied_speed_deg_s
        if last is not None and abs(clamped - last) <= 1e-4:
            return True

        msg = "PER: PRM {:.4g} °/s ({}).".format(clamped, role)
        if abs(clamped - raw) > 1e-6:
            msg = "PER: PRM {:.4g} °/s (recipe {:.4g}, max {:.0f} °/s) ({}).".format(
                clamped, raw, _PRM_MAX_SPEED, role
            )
        self._log(executor, msg)
        try:
            if hasattr(self._prm, "set_speed"):
                self._prm.set_speed(clamped, _PRM_DEFAULT_ACCEL)
            elif hasattr(self._prm, "set_velocity_params"):
                self._prm.set_velocity_params(_PRM_DEFAULT_ACCEL, clamped)
            elif hasattr(self._prm, "set_max_velocity"):
                self._prm.set_max_velocity(clamped)
            else:
                self._log(executor, "PER: PRM driver has no set_speed; speed not applied.")
                return False
            self._prm_last_applied_speed_deg_s = clamped
            return True
        except Exception as ex:
            self._log(executor, "PER: set_speed failed ({}): {}".format(role, ex))
            return False

    def _move_prm_to_angle(self, angle_deg: float, speed_deg_per_sec: float, executor: Any, role: str) -> bool:
        """Apply Manual Control speed, then blocking move_to (setup / return legs)."""
        if self._prm is None or not hasattr(self._prm, "move_to"):
            return False
        self._prm_set_speed_manual(executor, speed_deg_per_sec, role)
        try:
            self._prm.move_to(angle_deg)
            return True
        except Exception as ex:
            self._log(executor, "PER: move_to failed ({}): {}".format(role, ex))
            return False

    def _prm_move_to_position_only(self, angle_deg: float, executor: Any, role: str) -> bool:
        """move_to when meas speed was already set (step scan loop)."""
        if self._prm is None or not hasattr(self._prm, "move_to"):
            return False
        try:
            self._prm.move_to(angle_deg)
            return True
        except Exception as ex:
            self._log(executor, "PER: move_to failed ({}): {}".format(role, ex))
            return False

    def _motor_busy(self) -> Optional[bool]:
        if self._prm is None:
            return None
        motor = getattr(self._prm, "motor", None)
        if motor is None:
            return None
        try:
            raw = getattr(motor, "IsDeviceBusy", None)
            if callable(raw):
                return bool(raw())
            if raw is not None:
                return bool(raw)
        except Exception:
            pass
        for attr in ("Status", "status"):
            try:
                st = getattr(motor, attr, None)
                if st is None:
                    continue
                mv = getattr(st, "IsMoving", None)
                if callable(mv):
                    return bool(mv())
                if mv is not None:
                    return bool(mv)
            except Exception:
                pass
        return None

    def _continuous_sweep_poll_loop(
        self,
        params: PERProcessParameters,
        start: float,
        end: float,
        executor: Any,
        stop_fn: Callable[[], bool],
        *,
        t_sweep_start: float,
        completion_mode: str,
        move_thread: Optional[threading.Thread] = None,
        move_done: Optional[threading.Event] = None,
    ) -> tuple[List[float], List[float], List[float]]:
        """
        Sample Thorlabs + PRM position while the stage moves from start toward end.
        completion_mode:
          - \"busy\": end when IsDeviceBusy is False (or position within tol if busy unknown).
          - \"thread\": end when move_done is set and move_thread has finished (blocking move_to on worker).
        """
        positions: List[float] = []
        powers: List[float] = []
        sample_times: List[float] = []
        tol = max(0.05, 1.0 / max(1.0, params.steps_per_degree))
        travel = abs(float(end) - float(start))
        spd = _clamp_prm_speed_deg_s(float(params.meas_speed_deg_per_sec or 10.0))
        read_spacing_deg = _per_power_read_spacing_deg(params.meas_speed_deg_per_sec)
        wait_s = max(0.01, params.wait_time_ms / 1000.0)
        sleep_from_speed = read_spacing_deg / max(spd, 0.01)
        loop_sleep_s = max(wait_s, min(sleep_from_speed, 2.0))
        max_scan_sec = travel / max(spd, 0.01) + 120.0
        t_scan0 = time.time()
        last_sample_angle: Optional[float] = None
        pos: Optional[float] = None

        while not stop_fn():
            if (time.time() - t_scan0) > max_scan_sec:
                self._log(executor, "PER: Scan time limit reached; ending capture (check PRM / Kinesis).")
                break
            pos = self._prm_position_deg()
            if pos is not None:
                ang = float(pos)
                take_power = (
                    last_sample_angle is None
                    or abs(ang - last_sample_angle) >= read_spacing_deg
                )
                if take_power:
                    p = self._thorlabs_power_mw()
                    if p is None:
                        for _ in range(4):
                            time.sleep(0.04)
                            p = self._thorlabs_power_mw()
                            if p is not None:
                                break
                    if p is not None:
                        last_sample_angle = ang
                        positions.append(ang)
                        powers.append(float(p))
                        sample_times.append(time.perf_counter() - t_sweep_start)
                        _per_print_sample(len(positions), ang, float(p), "sweep")
                        live = self._compute_live_result(positions, powers, sample_times)
                        self._emit(executor, "per_test_result", live, list(positions), list(powers))

            if completion_mode == "busy":
                # Kinesis often reports IsDeviceBusy=False briefly before motion starts (or when idle at
                # start). Do not exit on "not busy" until we are near the sweep end angle — otherwise
                # the loop can exit with 0 samples while the stage never left the start.
                busy = self._motor_busy()
                near_end = pos is not None and abs(float(pos) - float(end)) <= max(tol, 0.5)
                if busy is False:
                    if near_end:
                        break
                elif busy is None:
                    if near_end:
                        break
            elif completion_mode == "thread":
                if (
                    move_done is not None
                    and move_thread is not None
                    and move_done.is_set()
                    and not move_thread.is_alive()
                ):
                    break
            else:
                break

            time.sleep(loop_sleep_s)

        pos_end = self._prm_position_deg()
        if pos_end is not None and last_sample_angle is not None:
            ang_e = float(pos_end)
            if abs(ang_e - last_sample_angle) >= max(0.05, read_spacing_deg * 0.25):
                p_e = self._thorlabs_power_mw()
                if p_e is not None:
                    positions.append(ang_e)
                    powers.append(float(p_e))
                    sample_times.append(time.perf_counter() - t_sweep_start)
                    _per_print_sample(len(positions), ang_e, float(p_e), "sweep end")
                    live = self._compute_live_result(positions, powers, sample_times)
                    self._emit(executor, "per_test_result", live, list(positions), list(powers))
        if _per_terminal_samples_enabled():
            print("[PER] --- end sweep: {} samples ---".format(len(positions)), flush=True)
        return positions, powers, sample_times

    def _compute_live_result(
        self,
        positions: List[float],
        powers: List[float],
        times_s: Optional[List[float]] = None,
    ) -> PERProcessResult:
        r = PERProcessResult(is_final=False, positions_deg=list(positions), powers_mw=list(powers))
        if times_s is not None:
            r.sample_times_s = list(times_s)
        if not powers:
            return r
        max_p = max(powers)
        min_p = min(powers)
        r.max_power = max_p
        r.min_power = min_p
        if min_p > 0:
            r.per_db = 10.0 * math.log10(max_p / min_p)
        else:
            r.per_db = 0.0
        idx = powers.index(max_p)
        r.max_angle = positions[idx] if 0 <= idx < len(positions) else 0.0
        return r

    def _scan_in_steps(
        self,
        params: PERProcessParameters,
        start_angle: float,
        end_angle: float,
        executor: Any,
        stop_requested: Callable[[], bool],
    ) -> tuple[List[float], List[float], List[float]]:
        positions: List[float] = []
        powers: List[float] = []
        sample_times: List[float] = []
        t_sweep_start = time.perf_counter()
        self._prm_set_speed_manual(executor, params.meas_speed_deg_per_sec, "step scan")
        spd_c = _clamp_prm_speed_deg_s(float(params.meas_speed_deg_per_sec or 10.0))
        spacing_deg = _per_power_read_spacing_deg(params.meas_speed_deg_per_sec)
        fine_deg = 1.0 / max(1.0, params.steps_per_degree)
        step_mag = max(spacing_deg, fine_deg)
        self._log(
            executor,
            "PER: Step scan — {:.3f}° per stop (≥ meas {:.2f}°/s); recipe min step {:.4f}°.".format(
                step_mag, spd_c, fine_deg
            ),
        )
        if _per_terminal_samples_enabled():
            print(
                "[PER] --- step-scan samples: index | angle (deg) | Thorlabs (mW) ---",
                flush=True,
            )
        direction = 1.0 if end_angle >= start_angle else -1.0
        step_deg = direction * step_mag
        cur = start_angle
        while True:
            if stop_requested():
                break
            reached = (direction > 0 and cur >= end_angle) or (direction < 0 and cur <= end_angle)
            if reached:
                cur = end_angle
            self._prm_move_to_position_only(cur, executor, "step scan")
            p = self._thorlabs_power_mw()
            pos = self._prm_position_deg()
            if p is not None and pos is not None:
                positions.append(float(pos))
                powers.append(float(p))
                sample_times.append(time.perf_counter() - t_sweep_start)
                _per_print_sample(len(positions), float(pos), float(p), "step")
                live = self._compute_live_result(positions, powers, sample_times)
                self._emit(executor, "per_test_result", live, list(positions), list(powers))
            if reached:
                break
            cur += step_deg
            spd = _clamp_prm_speed_deg_s(float(params.meas_speed_deg_per_sec or 10.0))
            wait_s = max(0.01, params.wait_time_ms / 1000.0)
            move_time_est = abs(step_deg) / max(spd, 0.01)
            time.sleep(max(wait_s, min(move_time_est + 0.02, 5.0)))
        if _per_terminal_samples_enabled():
            print("[PER] --- end step scan: {} samples ---".format(len(positions)), flush=True)
        return positions, powers, sample_times

    def run(
        self,
        params: PERProcessParameters,
        executor: Any,
        stop_requested: Optional[Callable[[], bool]] = None,
        recipe: Optional[Dict[str, Any]] = None,
    ) -> PERProcessResult:
        stop_fn = stop_requested or (lambda: False)
        result = PERProcessResult()
        self._prm_last_applied_speed_deg_s = None
        self._skip_actuator_for_run = bool(getattr(params, "skip_actuator", False))

        if self._thorlabs_pm is None or self._prm is None:
            result.fail_reasons.append("Missing Thorlabs or PRM")
            self._emit_per_done(executor, result, [], [])
            return result

        self._log(executor, "PER: Using live hardware (Thorlabs powermeter + PRM).")
        wl_nm = float(getattr(params, "wavelength_nm", 0.0) or 0.0)
        wavelength_just_set = self._apply_thorlabs_wavelength(wl_nm, executor)
        p0 = self._thorlabs_power_mw_precheck(executor, wavelength_just_set=wavelength_just_set)
        pos0 = self._prm_position_deg()
        if p0 is None:
            result.fail_reasons.append(
                "Thorlabs did not return power — check VISA connection, beam on sensor, and recipe wavelength "
                "(after wavelength change the meter may need a few seconds; verify SENS:WAV matches your laser)."
            )
            self._log(executor, "PER: Pre-check failed: Thorlabs read returned None (after retries).")
            self._emit_per_done(executor, result, [], [])
            return result
        if pos0 is None:
            result.fail_reasons.append(
                "PRM position not readable — connect PRM in Connection tab (Kinesis) and try again."
            )
            self._log(executor, "PER: Pre-check failed: PRM position returned None.")
            self._emit_per_done(executor, result, [], [])
            return result
        self._log(
            executor,
            "PER: Pre-check OK — Thorlabs {:.6g} mW, PRM {:.3f}°.".format(float(p0), float(pos0)),
        )
        if _per_terminal_samples_enabled():
            print(
                "[PER] Pre-check   angle = {:.4f} deg   Thorlabs = {:.6g} mW".format(float(pos0), float(p0)),
                flush=True,
            )

        if not self._move_actuator_b_in_front_of_beam(params, executor, stop_fn):
            result.fail_reasons.append("Failed to move actuator B in front of beam.")
            self._emit_per_done(executor, result, [], [])
            return result

        start = float(params.start_angle_deg)
        end = float(params.start_angle_deg + params.travel_distance_deg)
        self._emit(executor, "per_test_result", PERProcessResult(), [], [])

        if not self._move_prm_to_angle(start, params.setup_speed_deg_per_sec, executor, "move to start"):
            result.fail_reasons.append("Failed to move PRM to start angle.")
            self._emit_per_done(executor, result, [], [])
            return result

        if stop_fn():
            result.fail_reasons.append("PER stopped by user.")
            self._home_actuator_b(executor)
            self._emit_per_done(executor, result, [], [])
            return result

        positions: List[float] = []
        powers: List[float] = []
        sample_times: List[float] = []

        self._prm_set_speed_manual(executor, params.meas_speed_deg_per_sec, "sweep")
        spd_log = _clamp_prm_speed_deg_s(float(params.meas_speed_deg_per_sec or 10.0))
        read_spacing_log = _per_power_read_spacing_deg(params.meas_speed_deg_per_sec)

        # 1) Prefer async MoveTo(position) on the Kinesis motor handle (no timeout overload).
        moving_started = False
        motor = getattr(self._prm, "motor", None)
        decimal_type = globals().get("Decimal", None)
        target = decimal_type(end) if decimal_type is not None else end  # type: ignore[misc]
        if motor is not None:
            move_m = getattr(motor, "MoveTo", None)
            if callable(move_m):
                try:
                    move_m(target)
                    moving_started = True
                except Exception:
                    moving_started = False

        if moving_started:
            self._log(executor, "PER: Start rotating and sampling Thorlabs power + position (live hardware).")
            if _per_terminal_samples_enabled():
                print(
                    "[PER] --- sweep samples (continuous): index | angle (deg) | Thorlabs (mW) ---",
                    flush=True,
                )
            self._log(
                executor,
                "PER: Continuous sweep — Thorlabs every {:.2f}° (meas speed {:.2f}°/s).".format(
                    read_spacing_log, spd_log
                ),
            )
            t_sweep_start = time.perf_counter()
            positions, powers, sample_times = self._continuous_sweep_poll_loop(
                params,
                start,
                end,
                executor,
                stop_fn,
                t_sweep_start=t_sweep_start,
                completion_mode="busy",
            )
        elif callable(getattr(self._prm, "move_to", None)):
            # 2) Kinesis PRM uses blocking MoveTo(angle, TIMEOUT) — run it on a worker thread so we can
            #    poll position + Thorlabs during one continuous move (same as terminal PER test).
            self._log(
                executor,
                "PER: Continuous sweep (background move_to) — one move to end while sampling "
                "(no stop-and-go step scan).",
            )
            if _per_terminal_samples_enabled():
                print(
                    "[PER] --- sweep samples (continuous): index | angle (deg) | Thorlabs (mW) ---",
                    flush=True,
                )
            self._log(
                executor,
                "PER: Continuous sweep — Thorlabs every {:.2f}° (meas speed {:.2f}°/s).".format(
                    read_spacing_log, spd_log
                ),
            )
            move_done = threading.Event()
            move_err: List[Any] = []

            def _run_blocking_move_to_end() -> None:
                try:
                    self._prm.move_to(end)
                except Exception as e:
                    move_err.append(e)
                finally:
                    move_done.set()

            th = threading.Thread(target=_run_blocking_move_to_end, daemon=True)
            th.start()
            t_sweep_start = time.perf_counter()
            positions, powers, sample_times = self._continuous_sweep_poll_loop(
                params,
                start,
                end,
                executor,
                stop_fn,
                t_sweep_start=t_sweep_start,
                completion_mode="thread",
                move_thread=th,
                move_done=move_done,
            )
            th.join(timeout=200.0)
            if move_err:
                self._log(executor, "PER: PRM move thread error: {}".format(move_err[0]))
        else:
            self._log(executor, "PER: Step scan fallback (no move_to on PRM driver).")
            positions, powers, sample_times = self._scan_in_steps(params, start, end, executor, stop_fn)

        if stop_fn():
            result.fail_reasons.append("PER stopped by user.")
            self._home_actuator_b(executor)
            self._emit_per_done(executor, result, list(positions), list(powers), sample_times)
            return result

        self._move_prm_to_angle(start, params.setup_speed_deg_per_sec, executor, "return to start")
        self._home_actuator_b(executor)

        final = self._compute_live_result(positions, powers, sample_times)
        final.fail_reasons = []
        if not powers:
            final.fail_reasons.append("No Thorlabs readings captured during PER scan.")
            final.passed = False
        else:
            apply_per_pass_fail_criteria(recipe, final, params)
            final.passed = len(final.fail_reasons) == 0

        self._log(
            executor,
            "PER: Recipe pass/fail criteria: {}.".format("PASS" if final.passed else "FAIL"),
        )

        if _per_terminal_samples_enabled() and powers:
            print(
                "[PER] Summary  samples={}  PER={:.3f} dB  at_max_angle={:.4f} deg  "
                "P_min={:.6g} mW  P_max={:.6g} mW".format(
                    len(powers),
                    float(final.per_db),
                    float(final.max_angle),
                    float(final.min_power),
                    float(final.max_power),
                ),
                flush=True,
            )
        self._emit_per_done(executor, final, list(positions), list(powers), sample_times)
        return final
