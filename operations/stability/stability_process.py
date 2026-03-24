"""
Temperature stability: Part A (laser on, TEC min, Ando wide sweep → peak, narrow span) +
Part B (cold→hot, hot→cold, FWHM recovery + retries + consecutive exceed + optional limits + Δλ/°C).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from operations.arroyo_laser_helpers import apply_arroyo_recipe_and_laser_on_for_spectrum, arroyo_laser_off
from operations.recipe_ts_helpers import first_in_dict
from operations.spectrum.spectrum_process import (
    SpectrumProcessParameters,
    _analysis_command,
    _merge_metrics_from_ana,
    _merge_metrics_from_anar,
    _peak_from_traces,
    _recipe_sensitivity_to_ando,
    _truthy,
)
from operations.spectrum.trace_validation import detect_wdata_ldata

POST_SWEEP_SETTLE_S = 0.35


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _get_block(recipe: Dict[str, Any], slot: int) -> Dict[str, Any]:
    op = recipe.get("OPERATIONS") or recipe.get("operations") or {}
    keys = (
        f"Temperature Stability {slot}",
        f"Temperature_Stability_{slot}",
        f"TEMPERATURE_STABILITY_{slot}",
        f"TS{slot}",
        f"ts{slot}",
    )
    for k in keys:
        if k in op and isinstance(op[k], dict):
            return op[k]
    return {}


def _linreg_slope_nm_per_c(temps: List[float], peaks: List[float]) -> Optional[float]:
    n = min(len(temps), len(peaks))
    if n < 2:
        return None
    xs = [float(temps[i]) for i in range(n)]
    ys = [float(peaks[i]) for i in range(n)]
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((xs[i] - mx) * (ys[i] - my) for i in range(n))
    den = sum((xs[i] - mx) ** 2 for i in range(n))
    if abs(den) < 1e-18:
        return None
    return num / den


def _setpoints_inclusive(t0: float, t1: float, step: float) -> List[float]:
    if step <= 0:
        return [t0]
    lo, hi = (t0, t1) if t0 <= t1 else (t1, t0)
    out: List[float] = []
    t = lo
    guard = 0
    while t <= hi + 1e-6 and guard < 5000:
        out.append(round(t, 4))
        t += step
        guard += 1
    if out and abs(out[-1] - hi) > 1e-3 and hi > lo:
        if abs(out[-1] - hi) > step * 0.5:
            out.append(round(hi, 4))
    return out


def _setpoints_descending(t0: float, t1: float, step: float) -> List[float]:
    fwd = _setpoints_inclusive(min(t0, t1), max(t0, t1), step)
    return list(reversed(fwd))


def _parse_limits_row(stab: Dict[str, Any], name: str) -> Tuple[str, str, bool]:
    lim = stab.get("limits")
    if not isinstance(lim, dict):
        return ("", "", False)
    row = lim.get(name)
    if row is None:
        row = lim.get(name.replace(" ", ""))
    if not isinstance(row, dict):
        return ("", "", False)
    ll = row.get("ll", row.get("LL", ""))
    ul = row.get("ul", row.get("UL", ""))
    en = row.get("enable", row.get("Enable", False))
    return (str(ll) if ll is not None else "", str(ul) if ul is not None else "", _truthy(en))


def _auto_ref_enabled_for_stability(recipe: Dict[str, Any], slot: int) -> bool:
    """
    Prefer OPERATIONS['Temperature Stability N'].auto_ref_level; else SPECTRUM.auto_ref_level;
    default True (same as spectrum ATREF1 when enabled).
    """
    stab = _get_block(recipe, slot)
    op = recipe.get("OPERATIONS") or recipe.get("operations") or {}
    spec = op.get("SPECTRUM") or op.get("spectrum") or {}
    if not isinstance(spec, dict):
        spec = {}
    if isinstance(stab, dict):
        for k in ("auto_ref_level", "AutoRefLevel"):
            if k in stab:
                return _truthy(stab[k])
    vs = spec.get("auto_ref_level", spec.get("AutoRefLevel"))
    if vs is not None and str(vs).strip() != "":
        return _truthy(vs)
    return True


def _recipe_with_ts_laser_overrides(recipe: Dict[str, Any], slot: int) -> Dict[str, Any]:
    """Merge TS slot drive current into OPERATIONS.SPECTRUM for apply_arroyo_recipe_and_laser_on_for_spectrum."""
    stab = _get_block(recipe, slot)
    use_rated = _truthy(stab.get("UseI_at_Rated_P", stab.get("use_I_at_rated", False)))
    set_m = _to_float(stab.get("SetCurrent_mA", stab.get("set_current_mA", 0)), 0)
    if not use_rated and set_m <= 0:
        return recipe
    op = dict(recipe.get("OPERATIONS") or {})
    spec = dict(op.get("SPECTRUM") or {})
    liv = op.get("LIV") or {}
    if not isinstance(liv, dict):
        liv = {}
    if use_rated:
        rc = _to_float(liv.get("rated_current_mA"), 0)
        if rc > 0:
            spec["Current"] = rc
    elif set_m > 0:
        spec["Current"] = set_m
    op["SPECTRUM"] = spec
    out = dict(recipe)
    out["OPERATIONS"] = op
    return out


@dataclass
class TemperatureStabilityParameters:
    initial_temp_c: float = 25.0
    max_temp_c: float = 45.0
    step_temp_c: float = 2.0
    min_temp_c: float = 25.0
    wait_step_ms: int = 0
    continuous_scan: bool = False
    fwhm_recovery_threshold_nm: float = 0.3
    max_retries_same_point: int = 5
    tec_tolerance_c: float = 0.5
    tec_settle_timeout_s: float = 300.0
    preamble_pause_s: float = 2.0
    ando_span_nm: float = 2.0
    ando_sampling_points: int = 1001
    ando_resolution_nm: float = 0.05
    analysis: str = "DFB-LD"
    deg_of_stability: int = 3
    fwhm_ll_enabled: bool = False
    fwhm_ll_nm: float = 0.0
    fwhm_ul_enabled: bool = False
    fwhm_ul_nm: float = 999.0
    smsr_ll_enabled: bool = False
    smsr_ll_db: float = 0.0
    smsr_ul_enabled: bool = False
    smsr_ul_db: float = 999.0
    peak_wl_ll_enabled: bool = False
    peak_wl_ll_nm: float = 0.0
    peak_wl_ul_enabled: bool = False
    peak_wl_ul_nm: float = 9999.0
    peak_power_ll_enabled: bool = False
    peak_power_ll_dbm: float = -999.0
    peak_power_ul_enabled: bool = False
    peak_power_ul_dbm: float = 999.0
    delta_wl_per_c_enabled: bool = False
    delta_wl_per_c_min: float = -999.0
    delta_wl_per_c_max: float = 999.0

    @classmethod
    def from_recipe_blocks(cls, recipe: Dict[str, Any], slot: int) -> "TemperatureStabilityParameters":
        stab = _get_block(recipe, slot)
        spec = (recipe.get("OPERATIONS") or recipe.get("operations") or {}).get("SPECTRUM") or {}
        if not isinstance(spec, dict):
            spec = {}

        def sf(keys: Tuple[str, ...], default: float) -> float:
            v = first_in_dict(stab, keys, "")
            if v == "":
                v = first_in_dict(spec, keys, "")
            return _to_float(v, default)

        def sb(keys: Tuple[str, ...], default: bool) -> bool:
            v = first_in_dict(stab, keys, "")
            if v == "":
                return default
            return _truthy(v)

        def _row_bounds(name: str) -> Tuple[bool, float, bool, float]:
            ll_s, ul_s, en = _parse_limits_row(stab, name)
            if not en:
                return (False, 0.0, False, 999.0)
            ll_en = bool(str(ll_s).strip() != "")
            ul_en = bool(str(ul_s).strip() != "")
            ll_v = _to_float(ll_s, 0.0) if ll_en else 0.0
            ul_v = _to_float(ul_s, 999.0) if ul_en else 999.0
            return (ll_en, ll_v, ul_en, ul_v)

        initial = sf(("InitialTemperature", "initial_temp_c", "Initial_Temp", "InitTemp"), 25.0)
        mx = sf(("MaxTemperature", "max_temp_c", "MaxTemp"), 45.0)
        step = sf(("TemperatureStep", "step_temp_c", "Step", "delta_T", "INC"), 2.0)
        min_t = sf(("MinTemp", "min_temp_c", "PreambleMinTemp", "MINTemp"), min(initial, mx))
        thr = sf(("FWHM_recovery_threshold_nm", "fwhm_recovery_nm", "RecoveryThreshold_nm", "FWHM_Recovery_nm"), 0.3)
        wait_ms = int(max(0, min(3_600_000, sf(("WaitTime_ms", "wait_time_ms", "WAIT TIME"), 0.0))))
        continuous_scan = sb(("ContinuousScan", "continuous_scan"), False)

        span = sf(("StabilitySpan_nm", "span_nm", "Span_nm", "narrow_span_nm", "Span"), 2.0)
        smpl = int(sf(("StabilitySampling", "sampling_points", "Sampling", "SMPL"), 1001))
        res = sf(("StabilityResolution_nm", "resolution_nm", "Resolution"), 0.05)

        deg = int(max(1, min(50, sf(("DegOfStability", "deg_of_stability", "ConsecutiveExceedLimit"), 3.0))))

        lim_raw = stab.get("limits")
        has_limits_table = isinstance(lim_raw, dict) and bool(lim_raw)

        if has_limits_table:
            # Table rows (New Recipe TEMP STABILITY layout)
            f_ll_en, f_ll, f_ul_en, f_ul = _row_bounds("FWHM")
            s_ll_en, s_ll, s_ul_en, s_ul = _row_bounds("SMSR")
            wl_ll_en, wl_ll, wl_ul_en, wl_ul = _row_bounds("WL")
            pw_ll_s, pw_ul_s, pw_en = _parse_limits_row(stab, "Power")
            pw_ll_en = pw_en and bool(str(pw_ll_s).strip() != "")
            pw_ul_en = pw_en and bool(str(pw_ul_s).strip() != "")
            pw_ll_v = _to_float(pw_ll_s, -999.0) if pw_ll_en else -999.0
            pw_ul_v = _to_float(pw_ul_s, 999.0) if pw_ul_en else 999.0
        else:
            # Legacy flat keys (no limits dict)
            f_ll_en = sb(("fwhm_ll_enable", "FWHM_LL_enable", "EnableFWHM_LL"), False)
            f_ll = sf(("FWHM_LL_nm", "fwhm_ll_nm"), 0.0)
            f_ul_en = sb(("fwhm_ul_enable", "FWHM_UL_enable", "EnableFWHM_UL"), False)
            f_ul = sf(("FWHM_UL_nm", "fwhm_ul_nm"), 999.0)
            s_ll_en = sb(("smsr_ll_enable", "SMSR_LL_enable", "EnableSMSR_LL"), False)
            s_ll = sf(("SMSR_LL_dB", "smsr_ll_db"), 0.0)
            s_ul_en = sb(("smsr_ul_enable", "SMSR_UL_enable", "EnableSMSR_UL"), False)
            s_ul = sf(("SMSR_UL_dB", "smsr_ul_db"), 999.0)
            wl_ll_en = wl_ul_en = False
            wl_ll = wl_ul = 0.0
            pw_ll_en = pw_ul_en = False
            pw_ll_v = -999.0
            pw_ul_v = 999.0

        return cls(
            initial_temp_c=float(initial),
            max_temp_c=float(mx),
            step_temp_c=float(max(0.01, step)),
            min_temp_c=float(min_t),
            wait_step_ms=wait_ms,
            continuous_scan=continuous_scan,
            fwhm_recovery_threshold_nm=float(max(1e-6, thr)),
            max_retries_same_point=int(max(1, min(20, sf(("MaxRetries", "max_retries"), 5)))),
            tec_tolerance_c=float(max(0.05, sf(("TecTolerance_C", "tec_tolerance_c"), 0.5))),
            tec_settle_timeout_s=float(max(5.0, sf(("TecSettleTimeout_s", "tec_settle_timeout_s"), 300.0))),
            preamble_pause_s=float(max(0.0, sf(("PreamblePause_s", "preamble_pause_s"), 2.0))),
            ando_span_nm=float(max(0.01, span)),
            ando_sampling_points=int(max(11, min(20001, smpl))),
            ando_resolution_nm=float(max(1e-4, res)),
            analysis=str(first_in_dict(stab, ("Analysis", "analysis"), "") or first_in_dict(spec, ("Analysis", "analysis"), "") or "DFB-LD"),
            deg_of_stability=deg,
            fwhm_ll_enabled=f_ll_en,
            fwhm_ll_nm=float(f_ll),
            fwhm_ul_enabled=f_ul_en,
            fwhm_ul_nm=float(f_ul),
            smsr_ll_enabled=s_ll_en,
            smsr_ll_db=float(s_ll),
            smsr_ul_enabled=s_ul_en,
            smsr_ul_db=float(s_ul),
            peak_wl_ll_enabled=wl_ll_en,
            peak_wl_ll_nm=float(wl_ll),
            peak_wl_ul_enabled=wl_ul_en,
            peak_wl_ul_nm=float(wl_ul),
            peak_power_ll_enabled=pw_ll_en,
            peak_power_ll_dbm=float(pw_ll_v),
            peak_power_ul_enabled=pw_ul_en,
            peak_power_ul_dbm=float(pw_ul_v),
            delta_wl_per_c_enabled=sb(("delta_wl_per_c_enable", "DeltaWL_per_C_enable"), False),
            delta_wl_per_c_min=sf(("delta_wl_per_c_min", "DeltaWL_per_C_min"), -999.0),
            delta_wl_per_c_max=sf(("delta_wl_per_c_max", "DeltaWL_per_C_max"), 999.0),
        )


@dataclass
class TemperatureStabilityProcessResult:
    passed: bool = False
    fail_reasons: List[str] = field(default_factory=list)
    slot: int = 1
    step_label: str = ""
    temperature_c: List[float] = field(default_factory=list)
    fwhm_nm: List[float] = field(default_factory=list)
    smsr_db: List[float] = field(default_factory=list)
    peak_wavelength_nm: List[float] = field(default_factory=list)
    peak_level_dbm: List[float] = field(default_factory=list)
    delta_wl_per_c: Optional[float] = None


class TemperatureStabilityProcess:
    """Runs preamble + TEC sweeps; uses same Ando/Arroyo objects as the rest of the app."""

    def __init__(self) -> None:
        self._arroyo: Any = None
        self._ando: Any = None

    def set_instruments(self, arroyo: Any = None, ando: Any = None) -> None:
        self._arroyo = arroyo
        self._ando = ando

    def _log(self, executor: Any, msg: str) -> None:
        sig = getattr(executor, "stability_log_message", None)
        if sig is not None and hasattr(sig, "emit"):
            sig.emit(msg)
            return
        sig = getattr(executor, "log_message", None)
        if sig is not None and hasattr(sig, "emit"):
            sig.emit(msg)

    def _emit_live(
        self,
        executor: Any,
        t_c: float,
        fwhm: float,
        smsr: float,
        peak_nm: float,
    ) -> None:
        sig = getattr(executor, "stability_live_point", None)
        if sig is not None and hasattr(sig, "emit"):
            sig.emit(float(t_c), float(fwhm), float(smsr), float(peak_nm))

    def _emit_result(self, executor: Any, result: TemperatureStabilityProcessResult) -> None:
        sig = getattr(executor, "stability_test_result", None)
        if sig is not None and hasattr(sig, "emit"):
            sig.emit(result)

    def _wait_tec(
        self,
        executor: Any,
        target_c: float,
        tol: float,
        timeout_s: float,
        stop_requested: Callable[[], bool],
    ) -> Tuple[bool, str]:
        ar = self._arroyo
        if ar is None:
            return False, "Arroyo not available."
        t0 = time.time()
        while time.time() - t0 < timeout_s:
            if stop_requested():
                return False, "Stopped by user during TEC settle."
            rt = getattr(ar, "read_temp", None)
            cur = None
            if callable(rt):
                try:
                    cur = rt()
                except Exception:
                    cur = None
            if cur is not None and abs(float(cur) - float(target_c)) <= tol:
                return True, ""
            time.sleep(0.25)
        return False, "TEC did not reach {:.2f} °C within {:.0f} s.".format(target_c, timeout_s)

    def _apply_ando_from_spec_params(self, params: SpectrumProcessParameters, executor: Any) -> bool:
        a = self._ando
        if a is None or not getattr(a, "is_connected", lambda: False)():
            return False
        try:
            a.write_command("REMOTE")
        except Exception:
            pass
        tw = getattr(a, "trace_write_a", None)
        if callable(tw):
            tw()
        sens = _recipe_sensitivity_to_ando(params.sensitivity)
        a.set_sensitivity(sens)
        a.set_center_wavelength(params.center_nm)
        a.set_span(params.span_nm)
        a.set_resolution(params.resolution_nm)
        a.set_ref_level(params.ref_level_dbm)
        ls = float(params.level_scale_db_per_div)
        if ls > 0:
            a.set_log_scale(ls)
        a.set_sampling_points(params.sampling_points)
        _analysis_command(a, params.analysis)
        self._log(
            executor,
            "Stability: Ando CTR {:.3f} nm, span {:.3f} nm, SMPL {}.".format(
                params.center_nm, params.span_nm, params.sampling_points
            ),
        )
        return True

    def _apply_auto_ref_ando(self, recipe: Dict[str, Any], executor: Any, slot: int) -> None:
        """ATREF1 / ATREF0 — same as SpectrumProcess._apply_auto_ref (Ando auto reference level)."""
        a = self._ando
        if a is None or not getattr(a, "is_connected", lambda: False)():
            return
        wc = getattr(a, "write_command", None)
        if not callable(wc):
            return
        on = _auto_ref_enabled_for_stability(recipe, slot)
        if on:
            try:
                wc("ATREF1")
            except Exception:
                pass
            self._log(executor, "Stability: Ando ATREF1 (auto reference level ON).")
        else:
            try:
                wc("ATREF0")
            except Exception:
                pass
            self._log(executor, "Stability: Ando ATREF0 (auto reference level OFF).")

    def _apply_narrow_ando(self, p: TemperatureStabilityParameters, center_nm: float, spec: SpectrumProcessParameters, executor: Any) -> bool:
        a = self._ando
        if a is None:
            return False
        sens = _recipe_sensitivity_to_ando(spec.sensitivity)
        a.set_sensitivity(sens)
        a.set_center_wavelength(center_nm)
        a.set_span(p.ando_span_nm)
        a.set_resolution(p.ando_resolution_nm)
        a.set_sampling_points(p.ando_sampling_points)
        _analysis_command(a, p.analysis)
        self._log(
            executor,
            "Stability: narrow Ando CTR {:.4f} nm, span {:.4f} nm, SMPL {}.".format(
                center_nm, p.ando_span_nm, p.ando_sampling_points
            ),
        )
        return True

    def _one_sweep_metrics_vbg(
        self,
        executor: Any,
        analysis_name: str,
        stop_requested: Callable[[], bool],
        continuous_scan: bool,
    ) -> Dict[str, Any]:
        """
        VBG-style path: optional SGL+wait → WRTA → PKSR → DFBAN/LEDAN/FPAN → read_all_analysis_results (ANA?/ANAR? + fallbacks).
        If ``continuous_scan`` is True, skip SGL/wait (repeat sweep already running).
        """
        a = self._ando
        empty: Dict[str, Any] = {"pk_wl": None, "pk_lv": None, "fwhm": None, "smsr": None, "ana": None, "anar": None}
        if a is None or stop_requested():
            return empty
        if not continuous_scan:
            a.single_sweep()
            wait = getattr(a, "wait_sweep_done", None)
            if callable(wait):
                wait(timeout_s=180.0)
            else:
                t0 = time.time()
                while (time.time() - t0) < 180.0:
                    if getattr(a, "is_sweep_done", lambda: True)():
                        break
                    time.sleep(0.2)
            time.sleep(0.12 + POST_SWEEP_SETTLE_S)
        tw = getattr(a, "trace_write_a", None)
        if callable(tw):
            tw()
        time.sleep(0.08)
        ps = getattr(a, "peak_search", None)
        if callable(ps):
            ps()
            time.sleep(0.1)
        _analysis_command(a, analysis_name)
        time.sleep(0.12)
        triple = None
        rfn = getattr(a, "read_all_analysis_results", None)
        if callable(rfn):
            try:
                triple = rfn(analysis_name)
            except Exception:
                triple = None
        if triple is None:
            return empty
        fwhm, smsr, pk_wl = triple[0], triple[1], triple[2]
        pk_lv = None
        qpl = getattr(a, "query_peak_level_dbm", None)
        if callable(qpl):
            try:
                pk_lv = qpl()
            except Exception:
                pk_lv = None
        self._log(
            executor,
            "Stability: VBG read — FWHM {} nm, SMSR {} dB, PK {} nm (continuous_scan={}).".format(
                "{:.4f}".format(float(fwhm)) if fwhm is not None else "n/a",
                "{:.2f}".format(float(smsr)) if smsr is not None else "n/a",
                "{:.6f}".format(float(pk_wl)) if pk_wl is not None else "n/a",
                continuous_scan,
            ),
        )
        return {"pk_wl": pk_wl, "pk_lv": pk_lv, "fwhm": fwhm, "smsr": smsr, "ana": None, "anar": None}

    def _one_sweep_metrics_spectrum(
        self,
        executor: Any,
        analysis_name: str,
        stop_requested: Callable[[], bool],
        sampling_points: Optional[int] = None,
        continuous_scan: bool = False,
    ) -> Dict[str, Any]:
        """
        Same acquisition order as SpectrumProcess._sweep_fetch_traces_and_metrics:
        SGL → wait → trace write → peak search → ANA? → ANAR? → PKWL/PKLV/SPWD/SMSR → merge → WDATA/LDATA peak fallback.
        If ``continuous_scan`` is True, skip SGL/wait (repeat sweep already running).
        """
        a = self._ando
        empty: Dict[str, Any] = {"pk_wl": None, "pk_lv": None, "fwhm": None, "smsr": None, "ana": None, "anar": None}
        if a is None or stop_requested():
            return empty
        if not continuous_scan:
            a.single_sweep()
            wait = getattr(a, "wait_sweep_done", None)
            if callable(wait):
                wait(timeout_s=180.0)
            else:
                t0 = time.time()
                while (time.time() - t0) < 180.0:
                    if getattr(a, "is_sweep_done", lambda: True)():
                        break
                    time.sleep(0.2)
            time.sleep(0.12)
            time.sleep(POST_SWEEP_SETTLE_S)
        else:
            time.sleep(POST_SWEEP_SETTLE_S)
        tw = getattr(a, "trace_write_a", None)
        if callable(tw):
            tw()
        time.sleep(0.1)
        ps = getattr(a, "peak_search", None)
        if callable(ps):
            ps()
            time.sleep(0.12)
        # ANA? / ANAR? before PKWL? (same as spectrum — avoids empty ANA? on some stacks)
        qana = getattr(a, "query_analysis_ana", None)
        ana = None
        if callable(qana):
            try:
                ana = qana(analysis_name)
            except TypeError:
                ana = qana()
        anar = None
        qanar = getattr(a, "query_analysis_anar", None)
        if callable(qanar):
            try:
                anar = qanar(analysis_name)
            except Exception:
                anar = None
        pk_wl = getattr(a, "query_peak_wavelength_nm", lambda: None)()
        pk_lv = getattr(a, "query_peak_level_dbm", lambda: None)()
        fwhm = getattr(a, "query_spectral_width_nm", lambda: None)()
        smsr = getattr(a, "query_smsr_db", lambda: None)()
        pk_wl, pk_lv, fwhm, smsr = _merge_metrics_from_ana(ana, pk_wl, pk_lv, fwhm, smsr)
        pk_wl, pk_lv, fwhm, smsr = _merge_metrics_from_anar(anar, pk_wl, pk_lv, fwhm, smsr)
        wdata = list(getattr(a, "read_wdata_trace", lambda: [])() or [])
        ldata = list(getattr(a, "read_ldata_trace", lambda: [])() or [])
        if pk_wl is None or pk_lv is None:
            pw, pl = _peak_from_traces(wdata, ldata)
            if pk_wl is None:
                pk_wl = pw
            if pk_lv is None:
                pk_lv = pl
        try:
            _ok, det_lines = detect_wdata_ldata(
                a,
                wdata,
                ldata,
                recipe_sampling=sampling_points,
                query_instrument=False,
            )
            for ln in det_lines:
                self._log(executor, "Stability: {}".format(ln))
        except Exception:
            pass
        self._log(
            executor,
            "Stability: analysis result — PK {} nm, {} dBm; FWHM {}; SMSR {} (ANA/ANAR/PKWL/trace).".format(
                "{:.6f}".format(float(pk_wl)) if pk_wl is not None else "n/a",
                "{:.2f}".format(float(pk_lv)) if pk_lv is not None else "n/a",
                "{:.4f} nm".format(float(fwhm)) if fwhm is not None else "n/a",
                "{:.2f} dB".format(float(smsr)) if smsr is not None else "n/a",
            ),
        )
        return {"pk_wl": pk_wl, "pk_lv": pk_lv, "fwhm": fwhm, "smsr": smsr, "ana": ana, "anar": anar}

    def _one_sweep_metrics(
        self,
        executor: Any,
        analysis_name: str,
        stop_requested: Callable[[], bool],
        sampling_points: Optional[int] = None,
        continuous_scan: bool = False,
        use_vbg_first: bool = True,
    ) -> Dict[str, Any]:
        """Prefer VBG-style DFBAN + read_all_analysis_results; fall back to full spectrum-style path if incomplete."""
        if use_vbg_first:
            m = self._one_sweep_metrics_vbg(executor, analysis_name, stop_requested, continuous_scan)
            if m.get("pk_wl") is not None or m.get("fwhm") is not None:
                return m
            self._log(executor, "Stability: VBG read incomplete — using full Spectrum-style acquisition (WDATA/ANA…).")
        return self._one_sweep_metrics_spectrum(
            executor, analysis_name, stop_requested, sampling_points, continuous_scan
        )

    def _check_hard_limits(
        self,
        p: TemperatureStabilityParameters,
        fwhm: Optional[float],
        smsr: Optional[float],
        peak_nm: Optional[float] = None,
        peak_dbm: Optional[float] = None,
    ) -> List[str]:
        reasons: List[str] = []
        if fwhm is not None:
            if p.fwhm_ll_enabled and float(fwhm) < p.fwhm_ll_nm:
                reasons.append("FWHM {:.4f} nm below lower limit {:.4f} nm.".format(float(fwhm), p.fwhm_ll_nm))
            if p.fwhm_ul_enabled and float(fwhm) > p.fwhm_ul_nm:
                reasons.append("FWHM {:.4f} nm above upper limit {:.4f} nm.".format(float(fwhm), p.fwhm_ul_nm))
        else:
            if p.fwhm_ll_enabled or p.fwhm_ul_enabled:
                reasons.append("FWHM not available (limits enabled).")
        if smsr is not None:
            if p.smsr_ll_enabled and float(smsr) < p.smsr_ll_db:
                reasons.append("SMSR {:.2f} dB below lower limit {:.2f} dB.".format(float(smsr), p.smsr_ll_db))
            if p.smsr_ul_enabled and float(smsr) > p.smsr_ul_db:
                reasons.append("SMSR {:.2f} dB above upper limit {:.2f} dB.".format(float(smsr), p.smsr_ul_db))
        else:
            if p.smsr_ll_enabled or p.smsr_ul_enabled:
                reasons.append("SMSR not available (limits enabled).")
        if peak_nm is not None:
            if p.peak_wl_ll_enabled and float(peak_nm) < p.peak_wl_ll_nm:
                reasons.append("Peak λ {:.4f} nm below lower limit {:.4f} nm.".format(float(peak_nm), p.peak_wl_ll_nm))
            if p.peak_wl_ul_enabled and float(peak_nm) > p.peak_wl_ul_nm:
                reasons.append("Peak λ {:.4f} nm above upper limit {:.4f} nm.".format(float(peak_nm), p.peak_wl_ul_nm))
        else:
            if p.peak_wl_ll_enabled or p.peak_wl_ul_enabled:
                reasons.append("Peak wavelength not available (limits enabled).")
        if peak_dbm is not None:
            if p.peak_power_ll_enabled and float(peak_dbm) < p.peak_power_ll_dbm:
                reasons.append("Peak level {:.2f} dBm below lower limit {:.2f} dBm.".format(float(peak_dbm), p.peak_power_ll_dbm))
            if p.peak_power_ul_enabled and float(peak_dbm) > p.peak_power_ul_dbm:
                reasons.append("Peak level {:.2f} dBm above upper limit {:.2f} dBm.".format(float(peak_dbm), p.peak_power_ul_dbm))
        else:
            if p.peak_power_ll_enabled or p.peak_power_ul_enabled:
                reasons.append("Peak level not available (limits enabled).")
        return reasons

    def run(
        self,
        recipe: Dict[str, Any],
        executor: Any,
        slot: int,
        stop_requested: Callable[[], bool],
        step_label: str = "",
    ) -> TemperatureStabilityProcessResult:
        out = TemperatureStabilityProcessResult(slot=slot, step_label=step_label or "Temperature Stability {}".format(slot))
        p = TemperatureStabilityParameters.from_recipe_blocks(recipe, slot)
        spec_params = SpectrumProcessParameters.from_recipe(recipe if isinstance(recipe, dict) else {})

        ar = self._arroyo
        ando = self._ando
        if ar is None or not getattr(ar, "is_connected", lambda: False)():
            out.fail_reasons.append("Arroyo is not connected.")
            self._emit_result(executor, out)
            return out
        if ando is None or not getattr(ando, "is_connected", lambda: False)():
            out.fail_reasons.append("Ando is not connected.")
            self._emit_result(executor, out)
            return out

        recipe_dict = recipe if isinstance(recipe, dict) else {}
        recipe_laser = _recipe_with_ts_laser_overrides(recipe_dict, slot)

        ok_laser, err_laser = apply_arroyo_recipe_and_laser_on_for_spectrum(
            ar, recipe_laser, log=lambda m: self._log(executor, m)
        )
        if not ok_laser:
            out.fail_reasons.append(err_laser or "Arroyo laser setup failed.")
            self._emit_result(executor, out)
            return out

        # Part A: TEC to min temp for alignment sweep
        set_temp = getattr(ar, "set_temp", None)
        if callable(set_temp):
            set_temp(p.min_temp_c)
            time.sleep(0.2)
        set_out = getattr(ar, "set_output", None)
        if callable(set_out):
            set_out(1)
            time.sleep(0.15)
        ok_tec, msg_tec = self._wait_tec(executor, p.min_temp_c, p.tec_tolerance_c, p.tec_settle_timeout_s, stop_requested)
        if not ok_tec:
            out.fail_reasons.append(msg_tec or "TEC preamble failed.")
            self._emit_result(executor, out)
            return out
        time.sleep(max(0.0, p.preamble_pause_s))

        if not self._apply_ando_from_spec_params(spec_params, executor):
            out.fail_reasons.append("Failed to apply Ando (Spectrum) settings for preamble sweep.")
            self._emit_result(executor, out)
            return out
        self._apply_auto_ref_ando(recipe_dict, executor, slot)

        m0 = self._one_sweep_metrics(
            executor,
            spec_params.analysis,
            stop_requested,
            spec_params.sampling_points,
            continuous_scan=False,
        )
        if stop_requested():
            out.fail_reasons.append("Stopped during preamble sweep.")
            self._emit_result(executor, out)
            return out
        peak0 = m0.get("pk_wl")
        if peak0 is None:
            out.fail_reasons.append("Preamble sweep: could not read peak wavelength.")
            self._emit_result(executor, out)
            return out
        center_nm = float(peak0)
        if not self._apply_narrow_ando(p, center_nm, spec_params, executor):
            out.fail_reasons.append("Failed to apply narrow Ando settings for stability.")
            self._emit_result(executor, out)
            return out
        self._apply_auto_ref_ando(recipe_dict, executor, slot)

        temps_ch: List[float] = _setpoints_inclusive(p.initial_temp_c, p.max_temp_c, p.step_temp_c)
        temps_hc: List[float] = _setpoints_descending(p.initial_temp_c, p.max_temp_c, p.step_temp_c)

        consecutive_exceed = 0
        all_t: List[float] = []
        all_f: List[float] = []
        all_s: List[float] = []
        all_pk: List[float] = []
        all_pk_lv: List[float] = []

        def run_sweep(name: str, temps: List[float]) -> bool:
            nonlocal consecutive_exceed, all_t, all_f, all_s, all_pk, all_pk_lv
            self._log(executor, "Stability: {} — {} setpoints.".format(name, len(temps)))
            for t_set in temps:
                if stop_requested():
                    out.fail_reasons.append("Stopped by user.")
                    return False
                if callable(set_temp):
                    set_temp(t_set)
                    time.sleep(0.15)
                ok_w, msg_w = self._wait_tec(executor, t_set, p.tec_tolerance_c, p.tec_settle_timeout_s, stop_requested)
                if not ok_w:
                    out.fail_reasons.append(msg_w)
                    return False
                if p.wait_step_ms > 0:
                    time.sleep(min(120.0, p.wait_step_ms / 1000.0))

                fwhm_acc: Optional[float] = None
                smsr_acc: Optional[float] = None
                pk_acc: Optional[float] = None
                pk_lv_acc: Optional[float] = None
                exceed = False

                for attempt in range(p.max_retries_same_point + 1):
                    if stop_requested():
                        out.fail_reasons.append("Stopped by user.")
                        return False
                    m = self._one_sweep_metrics(
                        executor,
                        p.analysis,
                        stop_requested,
                        p.ando_sampling_points,
                        continuous_scan=p.continuous_scan,
                    )
                    fwhm = m.get("fwhm")
                    smsr = m.get("smsr")
                    pk = m.get("pk_wl")
                    pk_lv = m.get("pk_lv")
                    try:
                        fwhm_f = float(fwhm) if fwhm is not None else None
                    except (TypeError, ValueError):
                        fwhm_f = None
                    try:
                        smsr_f = float(smsr) if smsr is not None else None
                    except (TypeError, ValueError):
                        smsr_f = None
                    try:
                        pk_f = float(pk) if pk is not None else None
                    except (TypeError, ValueError):
                        pk_f = None
                    try:
                        pk_lv_f = float(pk_lv) if pk_lv is not None else None
                    except (TypeError, ValueError):
                        pk_lv_f = None

                    hard = self._check_hard_limits(p, fwhm_f, smsr_f, pk_f, pk_lv_f)
                    if hard:
                        out.fail_reasons.extend(hard)
                        return False

                    if fwhm_f is not None and fwhm_f <= p.fwhm_recovery_threshold_nm:
                        fwhm_acc, smsr_acc, pk_acc, pk_lv_acc = fwhm_f, smsr_f, pk_f, pk_lv_f
                        exceed = False
                        break
                    if attempt < p.max_retries_same_point:
                        self._log(
                            executor,
                            "Stability: T={:.2f} °C FWHM {:.4f} nm > {:.4f} — retry {}/{}.".format(
                                t_set, fwhm_f or -1.0, p.fwhm_recovery_threshold_nm, attempt + 1, p.max_retries_same_point
                            ),
                        )
                        continue
                    fwhm_acc, smsr_acc, pk_acc, pk_lv_acc = fwhm_f, smsr_f, pk_f, pk_lv_f
                    exceed = True

                if fwhm_acc is None:
                    out.fail_reasons.append("FWHM missing at T={:.2f} °C.".format(t_set))
                    return False

                all_t.append(float(t_set))
                all_f.append(float(fwhm_acc))
                all_s.append(float(smsr_acc) if smsr_acc is not None else float("nan"))
                all_pk.append(float(pk_acc) if pk_acc is not None else float("nan"))
                all_pk_lv.append(float(pk_lv_acc) if pk_lv_acc is not None else float("nan"))

                self._emit_live(executor, float(t_set), float(fwhm_acc), float(smsr_acc or 0.0), float(pk_acc or 0.0))

                if exceed:
                    consecutive_exceed += 1
                    if consecutive_exceed >= max(1, p.deg_of_stability):
                        out.fail_reasons.append(
                            "{} consecutive FWHM exceeds (recovery threshold {:.4f} nm).".format(
                                p.deg_of_stability, p.fwhm_recovery_threshold_nm
                            )
                        )
                        return False
                else:
                    consecutive_exceed = 0

            return True

        if not run_sweep("Cold → Hot", temps_ch):
            out.temperature_c = all_t
            out.fwhm_nm = all_f
            out.smsr_db = all_s
            out.peak_wavelength_nm = all_pk
            out.peak_level_dbm = all_pk_lv
            self._emit_result(executor, out)
            return out
        if not run_sweep("Hot → Cold", temps_hc):
            out.temperature_c = all_t
            out.fwhm_nm = all_f
            out.smsr_db = all_s
            out.peak_wavelength_nm = all_pk
            out.peak_level_dbm = all_pk_lv
            self._emit_result(executor, out)
            return out

        out.temperature_c = all_t
        out.fwhm_nm = all_f
        out.smsr_db = all_s
        out.peak_wavelength_nm = all_pk
        out.peak_level_dbm = all_pk_lv

        if p.delta_wl_per_c_enabled:
            slope = _linreg_slope_nm_per_c(all_t, all_pk)
            out.delta_wl_per_c = slope
            if slope is None:
                out.fail_reasons.append("Delta λ/°C: not enough points.")
            else:
                if slope < p.delta_wl_per_c_min or slope > p.delta_wl_per_c_max:
                    out.fail_reasons.append(
                        "Delta λ/°C {:.5f} nm/°C outside [{:.5f}, {:.5f}].".format(
                            slope, p.delta_wl_per_c_min, p.delta_wl_per_c_max
                        )
                    )

        out.passed = len(out.fail_reasons) == 0
        self._emit_result(executor, out)
        return out
