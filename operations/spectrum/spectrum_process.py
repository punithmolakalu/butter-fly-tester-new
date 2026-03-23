"""
Spectrum test step: TEC + laser on, apply RCP to Ando + wavemeter, two single sweeps,
peak-based center correction, real GPIB reads (WDATA/LDATA, wavemeter).

Main window may relabel the X axis using wavemeter readings without changing stored Ando trace data
(see SpectrumProcessResult.wavemeter_nm_for_axis_label).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from operations.arroyo_laser_helpers import apply_arroyo_recipe_and_laser_on_for_spectrum


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


def _get_str(d: Any, keys: List[str], default: str = "") -> str:
    if not isinstance(d, dict):
        return default
    for k in keys:
        if k in d and d.get(k) is not None:
            return str(d.get(k)).strip()
    return default


def _wavemeter_range_to_api(range_str: str) -> str:
    u = str(range_str or "").upper().replace(" ", "")
    if "1650" in u or ("1000" in u and "1650" in u):
        return "1000-1650"
    return "480-1000"


def _recipe_sensitivity_to_ando(s: str) -> str:
    u = str(s or "").strip().upper()
    mapping = {
        "LOW": "SLO1",
        "LOW1": "SLO1",
        "LOW2": "SLO2",
        "MEDIUM": "SMID",
        "MID": "SMID",
        "NORMAL RANGE AUTO": "SNAT",
        "NORMAL RANGE HOLD": "SNHD",
        "HIGH": "SHI1",
        "HIGH1": "SHI1",
        "HIGH2": "SHI2",
        "HIGH3": "SHI3",
    }
    if u in mapping:
        return mapping[u]
    if u in ("SNAT", "SNHD", "SMID", "SHI1", "SHI2", "SHI3", "SLO1", "SLO2"):
        return u
    return "SMID"


def _analysis_command(ando: Any, analysis_name: str) -> bool:
    a = str(analysis_name or "").strip().upper()
    if "DFB" in a:
        fn = getattr(ando, "analysis_dfb_ld", None)
        return bool(callable(fn) and fn())
    if "LED" in a:
        fn = getattr(ando, "analysis_led", None)
        return bool(callable(fn) and fn())
    if "FP" in a:
        fn = getattr(ando, "analysis_fp_ld", None)
        return bool(callable(fn) and fn())
    fn = getattr(ando, "analysis_dfb_ld", None)
    return bool(callable(fn) and fn())


def _peak_from_traces(wdata: List[float], ldata: List[float]) -> Tuple[Optional[float], Optional[float]]:
    if not wdata or not ldata or len(wdata) != len(ldata):
        return None, None
    try:
        i = max(range(len(ldata)), key=lambda j: float(ldata[j]))
        return float(wdata[i]), float(ldata[i])
    except Exception:
        return None, None


def _dbm_to_mw(dbm: float) -> float:
    try:
        return float(10.0 ** (float(dbm) / 10.0))
    except Exception:
        return 0.0


@dataclass
class SpectrumProcessParameters:
    center_nm: float = 1550.0
    span_nm: float = 10.0
    resolution_nm: float = 0.1
    sampling_points: int = 501
    ref_level_dbm: float = -10.0
    level_scale_db_per_div: float = 10.0
    temperature_c: float = 25.0
    laser_current_mA: float = 0.0
    sensitivity: str = "MID"
    analysis: str = "DFB-LD"
    min_smsr_db: float = 0.0
    max_fwhm_nm: float = 999.0
    wavelength_tolerance_nm: float = 999.0

    @classmethod
    def from_recipe(cls, recipe: Dict[str, Any]) -> "SpectrumProcessParameters":
        op = recipe.get("OPERATIONS") or recipe.get("operations") or {}
        spec = op.get("SPECTRUM") or op.get("spectrum") or {}
        pfc = recipe.get("PASS_FAIL_CRITERIA") or recipe.get("pass_fail_criteria") or {}
        pfc_s = pfc.get("SPECTRUM") or pfc.get("spectrum") or {}
        general = recipe.get("GENERAL") or recipe.get("general") or {}

        center = _get_float(spec, ["CenterWL", "center_nm", "center", "wavelength"], 1550.0)
        if center <= 0:
            center = _to_float(general.get("Wavelength"), 1550.0) or _to_float(recipe.get("Wavelength"), 1550.0)

        return cls(
            center_nm=float(center),
            span_nm=_get_float(spec, ["Span", "span_nm"], 10.0),
            resolution_nm=_get_float(spec, ["Resolution", "resolution_nm"], 0.1),
            sampling_points=int(max(11, min(20001, _get_float(spec, ["Sampling", "sampling"], 501)))),
            ref_level_dbm=_get_float(spec, ["RefLevel", "ref_level_dBm"], -10.0),
            level_scale_db_per_div=_get_float(spec, ["level_scale", "LevelScale"], 10.0),
            temperature_c=_get_float(spec, ["Temperature", "temperature"], 25.0),
            laser_current_mA=_get_float(spec, ["Current", "current"], 0.0),
            sensitivity=_get_str(spec, ["Sensitivity", "sensitivity"], "MID"),
            analysis=_get_str(spec, ["Analysis", "analysis"], "DFB-LD"),
            min_smsr_db=_get_float(
                pfc_s, ["min_SMSR_dB", "SMSR_Min_dB", "min_smsr_dB"], _get_float(spec, ["SMSR_Min_dB"], 0.0)
            ),
            max_fwhm_nm=_get_float(
                pfc_s, ["max_FWHM_nm", "FWHM_Max_nm", "max_fwhm_nm"], _get_float(spec, ["FWHM_Max_nm"], 999.0)
            ),
            wavelength_tolerance_nm=_get_float(pfc_s, ["wavelength_tolerance_nm", "WavelengthTolerance_nm"], 999.0),
        )


@dataclass
class SpectrumProcessResult:
    passed: bool = False
    fail_reasons: List[str] = field(default_factory=list)
    temperature: float = 25.0
    peak_wavelength: float = 0.0
    peak_power: float = 0.0
    peak_level_dbm: float = 0.0
    smsr: float = 0.0
    fwhm: float = 0.0
    first_sweep_wdata: List[float] = field(default_factory=list)
    first_sweep_ldata: List[float] = field(default_factory=list)
    second_sweep_wdata: List[float] = field(default_factory=list)
    second_sweep_ldata: List[float] = field(default_factory=list)
    first_wavemeter_nm: Optional[float] = None
    second_wavemeter_nm: Optional[float] = None
    peak_wavelength_first_nm: Optional[float] = None
    peak_wavelength_second_nm: Optional[float] = None
    wavemeter_nm_for_axis_label: Optional[float] = None


class SpectrumProcess:
    def __init__(self) -> None:
        self._arroyo: Any = None
        self._ando: Any = None
        self._wavemeter: Any = None

    def set_instruments(self, arroyo: Any = None, ando: Any = None, wavemeter: Any = None) -> None:
        self._arroyo = arroyo
        self._ando = ando
        self._wavemeter = wavemeter

    def _log(self, executor: Any, msg: str) -> None:
        sig = getattr(executor, "log_message", None)
        if sig is not None and hasattr(sig, "emit"):
            sig.emit(msg)

    def _emit_spectrum(self, executor: Any, result: SpectrumProcessResult) -> None:
        sig = getattr(executor, "spectrum_test_result", None)
        if sig is not None and hasattr(sig, "emit"):
            sig.emit(result)

    def _emit_live_trace(self, executor: Any, wdata: List[float], ldata: List[float]) -> None:
        sig = getattr(executor, "spectrum_live_trace", None)
        if sig is not None and hasattr(sig, "emit"):
            sig.emit(list(wdata or []), list(ldata or []))

    def _emit_wavemeter(self, executor: Any, nm: Optional[float]) -> None:
        sig = getattr(executor, "spectrum_wavemeter_reading", None)
        if sig is not None and hasattr(sig, "emit"):
            sig.emit(nm)

    def _read_wavemeter_nm(self) -> Optional[float]:
        if self._wavemeter is None or not getattr(self._wavemeter, "is_connected", lambda: False)():
            return None
        fn = getattr(self._wavemeter, "read_wavelength_nm", None)
        if not callable(fn):
            return None
        try:
            v = fn()
            if v is None:
                return None
            return float(v)
        except Exception:
            return None

    def _apply_wavemeter_recipe(self, recipe: Dict[str, Any], executor: Any) -> None:
        if self._wavemeter is None or not getattr(self._wavemeter, "is_connected", lambda: False)():
            return
        op = recipe.get("OPERATIONS") or recipe.get("operations") or {}
        wm = op.get("WAVEMETER") or op.get("wavemeter") or {}
        r = _get_str(wm, ["wavelength_range", "WavelengthRange", "range"], "")
        if r:
            api = _wavemeter_range_to_api(r)
            fn = getattr(self._wavemeter, "set_wavelength_range", None)
            if callable(fn):
                try:
                    fn(api)
                    self._log(executor, "Spectrum: Wavemeter range set to {} (RCP).".format(api))
                except Exception:
                    pass

    def _apply_ando_recipe(self, params: SpectrumProcessParameters, executor: Any) -> bool:
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
            "Spectrum: Ando CTR {:.3f} nm, span {:.3f} nm, SMPL {}.".format(
                params.center_nm, params.span_nm, params.sampling_points
            ),
        )
        return True

    def _single_sweep_and_fetch(self, executor: Any, stop_requested: Callable[[], bool]) -> Tuple[
        List[float], List[float], Optional[float], Optional[float], Optional[float]
    ]:
        """Sweep, read traces, peak search, return wdata, ldata, peak_nm, peak_dbm, fwhm_nm."""
        a = self._ando
        if a is None:
            return [], [], None, None, None
        if stop_requested():
            return [], [], None, None, None
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
        ps = getattr(a, "peak_search", None)
        if callable(ps):
            ps()
            time.sleep(0.12)
        pk_wl = getattr(a, "query_peak_wavelength_nm", lambda: None)()
        pk_lv = getattr(a, "query_peak_level_dbm", lambda: None)()
        wdata = list(getattr(a, "read_wdata_trace", lambda: [])() or [])
        ldata = list(getattr(a, "read_ldata_trace", lambda: [])() or [])
        if pk_wl is None or pk_lv is None:
            pw, pl = _peak_from_traces(wdata, ldata)
            if pk_wl is None:
                pk_wl = pw
            if pk_lv is None:
                pk_lv = pl
        fwhm = getattr(a, "query_spectral_width_nm", lambda: None)()
        return wdata, ldata, pk_wl, pk_lv, fwhm

    def run(
        self,
        recipe: Dict[str, Any],
        executor: Any,
        stop_requested: Optional[Callable[[], bool]] = None,
    ) -> SpectrumProcessResult:
        stop_fn = stop_requested or (lambda: False)
        result = SpectrumProcessResult()
        params = SpectrumProcessParameters.from_recipe(recipe if isinstance(recipe, dict) else {})
        result.temperature = float(params.temperature_c)

        if self._ando is None or not getattr(self._ando, "is_connected", lambda: False)():
            result.fail_reasons.append("Ando is not connected.")
            self._emit_spectrum(executor, result)
            return result

        if self._arroyo is None or not getattr(self._arroyo, "is_connected", lambda: False)():
            result.fail_reasons.append("Arroyo is not connected (Spectrum needs TEC + laser).")
            self._emit_spectrum(executor, result)
            return result

        ok_laser, err_laser = apply_arroyo_recipe_and_laser_on_for_spectrum(
            self._arroyo, recipe if isinstance(recipe, dict) else {}, log=lambda m: self._log(executor, m)
        )
        if not ok_laser:
            result.fail_reasons.append(err_laser or "Arroyo laser setup failed.")
            self._emit_spectrum(executor, result)
            return result

        self._apply_wavemeter_recipe(recipe, executor)
        if not self._apply_ando_recipe(params, executor):
            result.fail_reasons.append("Failed to apply Ando settings.")
            self._emit_spectrum(executor, result)
            return result

        result.first_wavemeter_nm = self._read_wavemeter_nm()
        self._emit_wavemeter(executor, result.first_wavemeter_nm)
        w1, l1, peak1, lv1, fwhm1 = self._single_sweep_and_fetch(executor, stop_fn)
        result.first_sweep_wdata = w1
        result.first_sweep_ldata = l1
        self._emit_live_trace(executor, w1, l1)
        result.peak_wavelength_first_nm = float(peak1) if peak1 is not None else None
        if stop_fn():
            result.fail_reasons.append("Stopped by user during first sweep.")
            self._emit_spectrum(executor, result)
            return result

        if peak1 is None:
            result.fail_reasons.append("Could not determine peak wavelength after first sweep.")
            self._emit_spectrum(executor, result)
            return result

        try:
            self._ando.set_center_wavelength(float(peak1))
            self._log(executor, "Spectrum: Ando center set to peak {:.6f} nm.".format(float(peak1)))
        except Exception as ex:
            result.fail_reasons.append("Failed to set Ando center to peak: {}".format(ex))
            self._emit_spectrum(executor, result)
            return result

        result.second_wavemeter_nm = self._read_wavemeter_nm()
        self._emit_wavemeter(executor, result.second_wavemeter_nm)
        w2, l2, peak2, lv2, fwhm2 = self._single_sweep_and_fetch(executor, stop_fn)
        result.second_sweep_wdata = w2
        result.second_sweep_ldata = l2
        self._emit_live_trace(executor, w2, l2)
        result.peak_wavelength_second_nm = float(peak2) if peak2 is not None else None
        result.fwhm = float(fwhm2) if fwhm2 is not None else float(fwhm1 or 0.0)

        pk_nm = float(peak2) if peak2 is not None else float(peak1)
        pk_dbm = float(lv2) if lv2 is not None else (float(lv1) if lv1 is not None else 0.0)
        result.peak_wavelength = pk_nm
        result.peak_level_dbm = pk_dbm
        result.peak_power = _dbm_to_mw(pk_dbm)
        result.wavemeter_nm_for_axis_label = result.second_wavemeter_nm

        result.passed = True
        if params.min_smsr_db > 0 and result.smsr > 0 and result.smsr < params.min_smsr_db:
            result.passed = False
            result.fail_reasons.append(
                "SMSR {:.2f} dB below limit {:.2f} dB.".format(result.smsr, params.min_smsr_db)
            )
        if params.max_fwhm_nm < 900 and result.fwhm > params.max_fwhm_nm:
            result.passed = False
            result.fail_reasons.append(
                "FWHM {:.4f} nm above limit {:.4f} nm.".format(result.fwhm, params.max_fwhm_nm)
            )

        self._emit_spectrum(executor, result)
        return result
