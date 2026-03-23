"""
Temperature stability: ramp TEC, measure FWHM / SMSR / peak WL at each temperature (Ando).
Evaluates enabled metrics together at each point; SMSR or peak-WL failure aborts immediately.
FWHM uses retry-at-same-temp (up to 5) and consecutive-exceed / recovery logic per recipe.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from operations.arroyo_laser_helpers import (
    arroyo_laser_off,
    arroyo_laser_on_safe,
    read_laser_output_on,
)
from operations.spectrum.spectrum_process import (
    _analysis_command,
    _dbm_to_mw,
    _peak_from_traces,
    _recipe_sensitivity_to_ando,
)


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _truthy(x: Any) -> bool:
    if x is None:
        return False
    if isinstance(x, bool):
        return x
    s = str(x).strip().lower()
    return s in ("1", "true", "yes", "on")


def _get_block(recipe: Dict[str, Any], step_name: str) -> Dict[str, Any]:
    op = recipe.get("OPERATIONS") or recipe.get("operations") or {}
    if step_name in op and isinstance(op[step_name], dict):
        return op[step_name]  # type: ignore[return-value]
    low = step_name.lower()
    for k, v in op.items():
        if str(k).strip().lower() == low and isinstance(v, dict):
            return v  # type: ignore[return-value]
    return {}


def _ando_query_smsr_db(ando: Any) -> Optional[float]:
    fn = getattr(ando, "query_smsr_db", None)
    if callable(fn):
        try:
            v = fn()
            if v is not None:
                return _to_float(v)
        except Exception:
            pass
    qfn = getattr(ando, "query", None)
    if not callable(qfn):
        return None
    for cmd in ("SMSR?", "MSR?", "SMSR1?"):
        try:
            r = qfn(cmd)
            if r is None:
                continue
            s = str(r).strip().split(",")[0]
            return float(s)
        except Exception:
            continue
    return None


@dataclass
class TemperatureStabilityParameters:
    step_name: str = "Temperature Stability 1"
    stability_plot_slot: int = 1
    initial_temp_c: float = 25.0
    max_temp_c: float = 35.0
    temp_increment_c: float = 1.0
    laser_current_mA: float = 100.0
    stabilization_time_s: float = 5.0
    temp_tolerance_c: float = 0.3
    temp_settle_timeout_s: float = 180.0
    deg_stability_c: float = 5.0
    recovery_steps: int = 3
    fwhm_max_nm: float = 999.0
    check_fwhm: bool = True
    smsr_min_db: float = 0.0
    smsr_max_db: float = 999.0
    check_smsr: bool = False
    peak_wl_min_nm: float = 0.0
    peak_wl_max_nm: float = 99999.0
    check_peak_wl: bool = False
    auto_center: bool = True
    wide_span_nm: float = 50.0
    fwhm_retry_max: int = 5
    consecutive_temp_window_c: float = 0.8
    # Ando / spectrum (merged from SPECTRUM + step block)
    center_nm: float = 1550.0
    span_nm: float = 10.0
    resolution_nm: float = 0.1
    sampling_points: int = 501
    ref_level_dbm: float = -10.0
    sensitivity: str = "MID"
    analysis: str = "DFB-LD"

    @classmethod
    def from_recipe(cls, recipe: Dict[str, Any], step_name: str, plot_slot: int) -> "TemperatureStabilityParameters":
        g = recipe.get("GENERAL") or recipe.get("general") or {}
        op = recipe.get("OPERATIONS") or recipe.get("operations") or {}
        spec = op.get("SPECTRUM") or op.get("spectrum") or {}
        blk = _get_block(recipe, step_name)

        def gf(keys: List[str], default: float) -> float:
            for k in keys:
                if k in blk:
                    return _to_float(blk.get(k), default)
            return default

        init_t = gf(["InitTemp", "Init_Temp", "InitialTemp", "initial_temp_c", "MinTemp", "min_temp"], 25.0)
        max_t = gf(["MaxTemp", "MAXTemp", "max_temp"], 35.0)
        inc = gf(["TempIncrement", "INC", "inc", "TempIncrement_c"], 1.0)
        if inc <= 0:
            inc = 1.0

        cur = gf(
            [
                "Current",
                "current",
                "SetCurr",
                "set_curr",
                "Set_Curr_mA",
                "laser_current_mA",
                "LaserCurrent",
                "laser_current",
            ],
            0.0,
        )
        if cur <= 0:
            cur = (
                _to_float(g.get("Current"), 0.0)
                or _to_float(g.get("current"), 0.0)
                or _to_float(g.get("SetCurr"), 0.0)
                or _to_float(g.get("set_curr"), 0.0)
                or _to_float(spec.get("Current"), 0.0)
                or _to_float(spec.get("current"), 0.0)
                or _to_float(spec.get("laser_current_mA"), 0.0)
            )
        if cur <= 0:
            liv = op.get("LIV") or op.get("liv") or {}
            per = op.get("PER") or op.get("per") or {}
            cur = (
                _to_float(liv.get("rated_current_mA"), 0.0)
                or _to_float(liv.get("min_current_mA"), 0.0)
                or _to_float(per.get("Current"), 0.0)
                or _to_float(per.get("current"), 0.0)
            )
        if cur <= 0:
            cur = _to_float(recipe.get("Current"), 0.0) or _to_float(recipe.get("current"), 0.0)

        stab_s = gf(["StabilizationTime_s", "stab_time_s"], 5.0)
        if "WaitTime_ms" in blk:
            stab_s = max(0.0, gf(["WaitTime_ms"], 0.0) / 1000.0)
        tol = gf(["TempTolerance_c", "tec_tolerance_c"], 0.3)
        tmo = gf(["TempSettleTimeout_s", "tec_settle_timeout_s"], 180.0)

        center = gf(["CenterWL", "center_nm"], 0.0)
        if center <= 0:
            center = _to_float(spec.get("CenterWL"), 0.0) or _to_float(g.get("Wavelength"), 0.0) or _to_float(
                recipe.get("Wavelength"), 1550.0
            )

        span = gf(["Span", "span_nm"], 0.0)
        if span <= 0:
            span = _to_float(spec.get("Span"), 10.0)

        res = gf(["Resolution", "resolution_nm"], 0.0)
        if res <= 0:
            res = _to_float(spec.get("Resolution"), 0.1)

        smpl = int(gf(["Sampling", "sampling_points"], 0.0))
        if smpl <= 0:
            smpl = int(max(11, min(20001, _to_float(spec.get("Sampling"), 501))))

        sens = str(blk.get("Sensitivity") or spec.get("Sensitivity") or "MID").strip()
        analysis = str(blk.get("Analysis") or spec.get("Analysis") or "DFB-LD").strip()

        # Limits — explicit flags or infer from PASS_FAIL
        pfc = recipe.get("PASS_FAIL_CRITERIA") or recipe.get("pass_fail_criteria") or {}
        pfc_ts = pfc.get(step_name) or pfc.get(str(step_name).replace(" ", "")) or {}

        fwhm_max = gf(["FWHM_Max_nm", "fwhm_max_nm", "FWHM_UL"], 999.0)
        check_fwhm = _truthy(blk.get("CheckFWHM", blk.get("check_fwhm", pfc_ts.get("check_fwhm"))))
        if not check_fwhm and fwhm_max < 900:
            check_fwhm = True

        smsr_min = gf(["SMSR_Min_dB", "smsr_min_db", "SMSR_LL"], 0.0)
        smsr_max = gf(["SMSR_Max_dB", "smsr_max_db", "SMSR_UL"], 999.0)
        check_smsr = _truthy(blk.get("CheckSMSR", blk.get("check_smsr", pfc_ts.get("check_smsr"))))
        if not check_smsr and smsr_min > 0:
            check_smsr = True

        wl_min = gf(["PeakWL_Min_nm", "WL_LL", "wl_min"], 0.0)
        wl_max = gf(["PeakWL_Max_nm", "WL_UL", "wl_max"], 99999.0)
        check_wl = _truthy(blk.get("CheckPeakWL", blk.get("check_peak_wl", pfc_ts.get("check_peak_wl"))))
        tol_nm = gf(["WavelengthTolerance_nm", "wavelength_tolerance_nm"], 0.0)
        if not check_wl and tol_nm > 0:
            check_wl = True
            wl_min = center - tol_nm
            wl_max = center + tol_nm

        deg = gf(["DegOfStability", "deg_stability", "Deg of Stability"], 5.0)
        recov = int(gf(["Recovery_Steps", "recovery_steps"], 3.0))
        auto = _truthy(blk.get("AutoCenter", blk.get("auto_center", True)))
        wide = gf(["WideSpan_nm", "wide_span_nm"], max(span * 4.0, 40.0))

        return cls(
            step_name=step_name,
            stability_plot_slot=max(1, min(2, int(plot_slot))),
            initial_temp_c=float(init_t),
            max_temp_c=float(max_t),
            temp_increment_c=float(inc),
            laser_current_mA=float(cur),
            stabilization_time_s=float(max(0.0, stab_s)),
            temp_tolerance_c=float(max(0.05, tol)),
            temp_settle_timeout_s=float(max(10.0, tmo)),
            deg_stability_c=float(max(0.1, deg)),
            recovery_steps=max(1, recov),
            fwhm_max_nm=float(fwhm_max),
            check_fwhm=bool(check_fwhm),
            smsr_min_db=float(smsr_min),
            smsr_max_db=float(smsr_max),
            check_smsr=bool(check_smsr),
            peak_wl_min_nm=float(wl_min),
            peak_wl_max_nm=float(wl_max),
            check_peak_wl=bool(check_wl),
            auto_center=bool(auto),
            wide_span_nm=float(max(5.0, wide)),
            center_nm=float(center),
            span_nm=float(span),
            resolution_nm=float(res),
            sampling_points=smpl,
            ref_level_dbm=_to_float(blk.get("RefLevel") or spec.get("RefLevel"), -10.0),
            sensitivity=sens,
            analysis=analysis,
        )


@dataclass
class TemperatureStabilityProcessResult:
    passed: bool = False
    status: str = "FAIL"
    fail_reasons: List[str] = field(default_factory=list)
    stability_plot_slot: int = 1
    step_name: str = ""
    temperature_data: List[float] = field(default_factory=list)
    peak_wl_data: List[float] = field(default_factory=list)
    smsr_data: List[float] = field(default_factory=list)
    fwhm_data: List[float] = field(default_factory=list)
    power_data: List[float] = field(default_factory=list)
    fwhm_stable_span_achieved: bool = False


def _temp_points(t0: float, t1: float, step: float) -> List[float]:
    if step <= 0:
        return [t0, t1]
    if t1 < t0:
        t0, t1 = t1, t0
    out: List[float] = []
    t = t0
    while t <= t1 + 1e-6:
        out.append(round(t, 4))
        t += step
    if out and out[-1] < t1 - 1e-6:
        out.append(round(t1, 4))
    return out


def _apply_ando(
    ando: Any, params: TemperatureStabilityParameters, log: Optional[Callable[[str], None]] = None
) -> bool:
    if ando is None or not getattr(ando, "is_connected", lambda: False)():
        return False
    try:
        ando.write_command("REMOTE")
    except Exception:
        pass
    tw = getattr(ando, "trace_write_a", None)
    if callable(tw):
        tw()
    sens = _recipe_sensitivity_to_ando(params.sensitivity)
    ando.set_sensitivity(sens)
    ando.set_center_wavelength(params.center_nm)
    ando.set_span(params.span_nm)
    ando.set_resolution(params.resolution_nm)
    ando.set_ref_level(params.ref_level_dbm)
    ls = 10.0
    if ls > 0:
        ando.set_log_scale(ls)
    ando.set_sampling_points(params.sampling_points)
    _analysis_command(ando, params.analysis)
    if log:
        log(
            "Stability: Ando CTR {:.3f} nm, span {:.3f} nm, SMPL {}.".format(
                params.center_nm, params.span_nm, params.sampling_points
            )
        )
    return True


def _sweep_and_read(
    ando: Any, stop_requested: Callable[[], bool]
) -> Tuple[float, float, float, float, Optional[float]]:
    """Returns peak_nm, peak_dbm, fwhm_nm, power_mw, smsr_db."""
    if stop_requested():
        return 0.0, -99.0, 0.0, 0.0, None
    ando.single_sweep()
    wait = getattr(ando, "wait_sweep_done", None)
    if callable(wait):
        wait(timeout_s=180.0)
    else:
        t0 = time.time()
        while (time.time() - t0) < 180.0:
            if getattr(ando, "is_sweep_done", lambda: True)():
                break
            time.sleep(0.2)
    time.sleep(0.12)
    ps = getattr(ando, "peak_search", None)
    if callable(ps):
        ps()
        time.sleep(0.12)
    pk_wl = getattr(ando, "query_peak_wavelength_nm", lambda: None)()
    pk_lv = getattr(ando, "query_peak_level_dbm", lambda: None)()
    wdata = list(getattr(ando, "read_wdata_trace", lambda: [])() or [])
    ldata = list(getattr(ando, "read_ldata_trace", lambda: [])() or [])
    if pk_wl is None or pk_lv is None:
        pw, pl = _peak_from_traces(wdata, ldata)
        if pk_wl is None:
            pk_wl = pw
        if pk_lv is None:
            pk_lv = pl
    fwhm = getattr(ando, "query_spectral_width_nm", lambda: None)()
    smsr = _ando_query_smsr_db(ando)
    pk_nm = float(pk_wl) if pk_wl is not None else 0.0
    pk_dbm = float(pk_lv) if pk_lv is not None else -99.0
    fwhm_v = float(fwhm) if fwhm is not None else 0.0
    p_mw = _dbm_to_mw(pk_dbm) if pk_dbm > -90 else 0.0
    return pk_nm, pk_dbm, fwhm_v, p_mw, smsr


def _wait_tec(
    arroyo: Any,
    target_c: float,
    tolerance_c: float,
    timeout_s: float,
    stop_requested: Callable[[], bool],
) -> Tuple[bool, float]:
    t0 = time.time()
    last = target_c
    while (time.time() - t0) < timeout_s:
        if stop_requested():
            return False, last
        rt = getattr(arroyo, "read_temp", None)
        if callable(rt):
            try:
                last = _to_float(rt(), last)
            except Exception:
                pass
        if abs(last - target_c) <= tolerance_c:
            return True, last
        time.sleep(0.25)
    return abs(last - target_c) <= tolerance_c * 3.0, last


def _arroyo_setup_laser(
    arroyo: Any,
    recipe: Dict[str, Any],
    params: TemperatureStabilityParameters,
    log: Optional[Callable[[str], None]],
) -> Tuple[bool, str]:
    if arroyo is None or not getattr(arroyo, "is_connected", lambda: False)():
        return False, "Arroyo not connected."
    cur = float(params.laser_current_mA)
    if cur <= 0:
        return False, "Set laser current (mA) in the temperature stability recipe block or GENERAL.Current."
    try:
        fn = getattr(arroyo, "set_remote_mode", None)
        if callable(fn):
            fn()
            time.sleep(0.1)
    except Exception:
        pass
    st = getattr(arroyo, "set_temp", None)
    if callable(st):
        st(float(params.initial_temp_c))
        time.sleep(0.2)
    so = getattr(arroyo, "set_output", None)
    if callable(so):
        so(1)
        time.sleep(0.15)
    lim = max(cur * 1.2, cur + 200.0, 500.0)
    if getattr(arroyo, "laser_set_current_limit", None):
        arroyo.laser_set_current_limit(lim)
        time.sleep(0.08)
    if getattr(arroyo, "laser_set_current", None):
        arroyo.laser_set_current(cur)
        time.sleep(0.12)
    arroyo_laser_on_safe(arroyo)
    time.sleep(0.45)
    state = read_laser_output_on(arroyo)
    if state is False:
        return False, "Laser did not turn ON."
    if log:
        log("Stability: Arroyo laser ON, {:.0f} mA.".format(cur))
    return True, ""


def _set_tec_temp(arroyo: Any, temp_c: float) -> None:
    fn = getattr(arroyo, "set_temp", None)
    if callable(fn):
        fn(float(temp_c))
        time.sleep(0.15)


class TemperatureStabilityProcess:
    def __init__(self) -> None:
        self._arroyo: Any = None
        self._ando: Any = None

    def set_instruments(self, arroyo: Any = None, ando: Any = None) -> None:
        self._arroyo = arroyo
        self._ando = ando

    def _emit(
        self,
        executor: Any,
        result: TemperatureStabilityProcessResult,
    ) -> None:
        sig = getattr(executor, "stability_test_result", None)
        if sig is not None and hasattr(sig, "emit"):
            sig.emit(result)

    def _auto_center(self, params: TemperatureStabilityParameters, stop_requested: Callable[[], bool], log) -> bool:
        a = self._ando
        if a is None:
            return False
        try:
            a.set_span(float(params.wide_span_nm))
            a.set_center_wavelength(float(params.center_nm))
            if log:
                log("Stability: Auto-center wide span {:.1f} nm.".format(params.wide_span_nm))
        except Exception:
            pass
        pk_nm, _, _, _, _ = _sweep_and_read(a, stop_requested)
        if stop_requested() or pk_nm <= 0:
            return False
        try:
            a.set_center_wavelength(pk_nm)
            a.set_span(float(params.span_nm))
            a.set_sampling_points(int(params.sampling_points))
            if log:
                log("Stability: Recentered to {:.4f} nm, final span {:.2f} nm.".format(pk_nm, params.span_nm))
        except Exception:
            return False
        return True

    def run(
        self,
        recipe: Dict[str, Any],
        executor: Any,
        stop_requested: Callable[[], bool],
        step_name: str,
        plot_slot: int = 1,
    ) -> TemperatureStabilityProcessResult:
        out = TemperatureStabilityProcessResult(step_name=step_name, stability_plot_slot=plot_slot)
        params = TemperatureStabilityParameters.from_recipe(recipe if isinstance(recipe, dict) else {}, step_name, plot_slot)

        def log(msg: str) -> None:
            sig = getattr(executor, "stability_log_message", None)
            if sig is not None and hasattr(sig, "emit"):
                sig.emit(msg)
                return
            sig = getattr(executor, "log_message", None)
            if sig is not None and hasattr(sig, "emit"):
                sig.emit(msg)

        arroyo = self._arroyo
        ando = self._ando
        if arroyo is None or not getattr(arroyo, "is_connected", lambda: False)():
            out.fail_reasons.append("Arroyo not connected.")
            self._emit(executor, out)
            return out
        if ando is None or not getattr(ando, "is_connected", lambda: False)():
            out.fail_reasons.append("Ando not connected.")
            self._emit(executor, out)
            return out

        ok_laser, err = _arroyo_setup_laser(arroyo, recipe, params, log)
        if not ok_laser:
            out.fail_reasons.append(err or "Arroyo laser setup failed.")
            self._emit(executor, out)
            return out

        if not _apply_ando(ando, params, log):
            out.fail_reasons.append("Failed to apply Ando settings.")
            self._emit(executor, out)
            return out

        if params.auto_center:
            if not self._auto_center(params, stop_requested, log):
                out.fail_reasons.append("Auto-center failed (no peak or stopped).")
                arroyo_laser_off(arroyo)
                try:
                    ando.stop_sweep()
                except Exception:
                    pass
                self._emit(executor, out)
                return out
        else:
            _apply_ando(ando, params, log)

        temps = _temp_points(params.initial_temp_c, params.max_temp_c, params.temp_increment_c)
        if not temps:
            out.fail_reasons.append("Invalid temperature range.")
            self._emit(executor, out)
            return out

        consecutive_exceed = 0
        last_exceed_temp: Optional[float] = None
        stable_span_start: Optional[float] = None
        fwhm_span_ok = False

        temps_list: List[float] = []
        wl_list: List[float] = []
        smsr_list: List[float] = []
        fwhm_list: List[float] = []
        pow_list: List[float] = []

        for current_temp in temps:
            if stop_requested():
                out.status = "ABORTED"
                out.fail_reasons.append("Stopped by user.")
                break

            _set_tec_temp(arroyo, current_temp)
            ok_settle, read_t = _wait_tec(
                arroyo,
                current_temp,
                float(params.temp_tolerance_c),
                float(params.temp_settle_timeout_s),
                stop_requested,
            )
            if not ok_settle:
                log("Stability: Warning — TEC within tolerance not reached at {:.2f} °C (read {:.2f}).".format(current_temp, read_t))
            time.sleep(max(0.0, params.stabilization_time_s))

            # --- measure (retries only affect FWHM logic) ---
            fwhm_ok_for_temp = False
            retry = 0
            pk_nm = 0.0
            pk_dbm = -99.0
            fwhm_v = 0.0
            p_mw = 0.0
            smsr_v: Optional[float] = None

            while retry < params.fwhm_retry_max:
                if stop_requested():
                    out.status = "ABORTED"
                    out.fail_reasons.append("Stopped by user.")
                    break
                pk_nm, pk_dbm, fwhm_v, p_mw, smsr_v = _sweep_and_read(ando, stop_requested)
                if stop_requested():
                    out.status = "ABORTED"
                    out.fail_reasons.append("Stopped by user.")
                    break

                # SMSR / Peak WL: evaluate immediately on every attempt — any failure aborts the test
                if params.check_smsr and smsr_v is not None:
                    if smsr_v < params.smsr_min_db or smsr_v > params.smsr_max_db:
                        out.fail_reasons.append(
                            "SMSR limit fail at {:.1f} °C: {:.2f} dB (allowed {:.2f}–{:.2f}).".format(
                                current_temp, smsr_v, params.smsr_min_db, params.smsr_max_db
                            )
                        )
                        self._emit(executor, out)
                        arroyo_laser_off(arroyo)
                        try:
                            ando.stop_sweep()
                        except Exception:
                            pass
                        return out
                elif params.check_smsr and smsr_v is None:
                    out.fail_reasons.append("SMSR read failed at {:.1f} °C.".format(current_temp))
                    self._emit(executor, out)
                    arroyo_laser_off(arroyo)
                    try:
                        ando.stop_sweep()
                    except Exception:
                        pass
                    return out

                if params.check_peak_wl:
                    if pk_nm < params.peak_wl_min_nm or pk_nm > params.peak_wl_max_nm:
                        out.fail_reasons.append(
                            "Peak WL limit fail at {:.1f} °C: {:.4f} nm (allowed {:.4f}–{:.4f}).".format(
                                current_temp, pk_nm, params.peak_wl_min_nm, params.peak_wl_max_nm
                            )
                        )
                        self._emit(executor, out)
                        arroyo_laser_off(arroyo)
                        try:
                            ando.stop_sweep()
                        except Exception:
                            pass
                        return out

                # FWHM
                if not params.check_fwhm:
                    fwhm_ok_for_temp = True
                    break
                if fwhm_v <= params.fwhm_max_nm:
                    fwhm_ok_for_temp = True
                    break
                retry += 1
                log(
                    "Stability: FWHM {:.4f} nm > {:.4f} nm at {:.1f} °C — retry {}/{}.".format(
                        fwhm_v, params.fwhm_max_nm, current_temp, retry, params.fwhm_retry_max
                    )
                )

            if out.status == "ABORTED":
                break
            if stop_requested():
                out.status = "ABORTED"
                out.fail_reasons.append("Stopped by user.")
                break

            if params.check_fwhm and not fwhm_ok_for_temp:
                # FWHM exceed event after retries
                if last_exceed_temp is not None and abs(current_temp - last_exceed_temp) < params.consecutive_temp_window_c:
                    out.fail_reasons.append(
                        "FWHM 0.8 °C rule: consecutive exceed within {:.2f} °C at {:.2f} and {:.2f} °C.".format(
                            params.consecutive_temp_window_c, last_exceed_temp, current_temp
                        )
                    )
                    break
                consecutive_exceed += 1
                last_exceed_temp = current_temp
                if consecutive_exceed > params.recovery_steps:
                    stable_span_start = None
                    consecutive_exceed = 0
                    last_exceed_temp = None
                    log("Stability: FWHM recovery — reset stability tracking.")
                stable_span_start = None
                continue

            # All enabled checks passed at this temperature
            consecutive_exceed = 0
            last_exceed_temp = None
            smsr_plot = float(smsr_v) if smsr_v is not None else float("nan")
            temps_list.append(float(read_t if math.isfinite(read_t) else current_temp))
            wl_list.append(pk_nm)
            smsr_list.append(smsr_plot)
            fwhm_list.append(fwhm_v)
            pow_list.append(p_mw)

            out.temperature_data = list(temps_list)
            out.peak_wl_data = list(wl_list)
            out.smsr_data = list(smsr_list)
            out.fwhm_data = list(fwhm_list)
            out.power_data = list(pow_list)
            self._emit(executor, out)

            if params.check_fwhm:
                if stable_span_start is None:
                    stable_span_start = float(current_temp)
                span_now = float(current_temp) - float(stable_span_start)
                if span_now >= params.deg_stability_c - 1e-6:
                    fwhm_span_ok = True
                    log(
                        "Stability: FWHM stable span ≥ {:.1f} °C (from {:.2f} to {:.2f} °C).".format(
                            params.deg_stability_c, stable_span_start, current_temp
                        )
                    )

        # Cleanup
        try:
            arroyo_laser_off(arroyo)
        except Exception:
            pass
        try:
            ando.stop_sweep()
        except Exception:
            pass

        out.temperature_data = list(temps_list)
        out.peak_wl_data = list(wl_list)
        out.smsr_data = list(smsr_list)
        out.fwhm_data = list(fwhm_list)
        out.power_data = list(pow_list)
        out.fwhm_stable_span_achieved = bool(fwhm_span_ok)

        if out.status == "ABORTED":
            out.passed = False
            self._emit(executor, out)
            return out

        if out.fail_reasons:
            out.passed = False
            out.status = "FAIL"
            self._emit(executor, out)
            return out

        if params.check_fwhm and not fwhm_span_ok:
            out.passed = False
            out.status = "FAIL"
            out.fail_reasons.append(
                "No {:.1f} °C FWHM-stable span achieved (check enabled FWHM limits).".format(params.deg_stability_c)
            )
            self._emit(executor, out)
            return out

        out.passed = True
        out.status = "PASS"
        self._emit(executor, out)
        return out
