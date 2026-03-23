"""
Spectrum test step: TEC + laser on, apply RCP to Ando + wavemeter, two single sweeps.

After sweep 1: plot Spectrum window + main **First sweep** tab, then wait 4 s. After sweep 2: plot Spectrum window, wait 4 s, then final main-tab update. First sweep updates the **First sweep**
sub-tab only; second sweep updates the **Second sweep** (primary) sub-tab. ANAR? / ANA? layouts follow
recipe analysis (DFB-LD, LED, FP-LD); second-sweep center wavelength uses ANAR? PK_WL_nm, else ANA?
``PK_WL_nm`` / comma fields, else PKWL? / trace peak.

WDATA/LDATA validation matches terminal scripts; ANA? fields include ``EXTRA_nm`` (4th value) when present.
Optional pass/fail limits apply only when enabled in the recipe.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

from operations.arroyo_laser_helpers import apply_arroyo_recipe_and_laser_on_for_spectrum
from operations.spectrum.trace_plotting import pair_trace_floats
from operations.spectrum.trace_validation import detect_wdata_ldata


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


def _truthy(v: Any) -> bool:
    if v is None:
        return False
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    return s in ("1", "true", "yes", "on")


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


def _first_sweep_center_nm_for_second_sweep(metrics: Dict[str, Any]) -> Optional[float]:
    """
    Wavelength to set as Ando CTR before the second single sweep.
    Prefer **ANA?** ``PK_WL_nm`` (or 2nd comma field), then ANAR? for LED-style layouts, then ``pk_wl`` (PKWL? / trace).
    """
    ana = metrics.get("ana")
    if isinstance(ana, dict):
        v = ana.get("PK_WL_nm")
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
        fields = ana.get("fields")
        if isinstance(fields, (list, tuple)) and len(fields) >= 2:
            try:
                return float(fields[1])
            except (TypeError, ValueError):
                pass
    anar = metrics.get("anar")
    if isinstance(anar, dict):
        v = anar.get("PK_WL_nm")
        if v is not None:
            try:
                return float(v)
            except (TypeError, ValueError):
                pass
    pk = metrics.get("pk_wl")
    if pk is not None:
        try:
            return float(pk)
        except (TypeError, ValueError):
            pass
    return None


def _second_sweep_center_source_note(m1: Dict[str, Any]) -> str:
    """Short label for logs: where the CTR wavelength came from."""
    ana = m1.get("ana")
    if isinstance(ana, dict):
        if ana.get("PK_WL_nm") is not None:
            return "ANA? PK_WL_nm"
        fields = ana.get("fields")
        if isinstance(fields, (list, tuple)) and len(fields) >= 2:
            return "ANA? (comma fields)"
    anar = m1.get("anar")
    if isinstance(anar, dict) and anar.get("PK_WL_nm") is not None:
        return "ANAR? PK_WL_nm"
    return "PKWL/trace peak"


def _merge_metrics_from_ana(
    ana: Any,
    pk_wl: Optional[float],
    pk_lv: Optional[float],
    fwhm: Optional[float],
    smsr: Optional[float],
) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
    if not isinstance(ana, dict):
        return pk_wl, pk_lv, fwhm, smsr
    try:
        if pk_wl is None and ana.get("PK_WL_nm") is not None:
            pk_wl = float(ana["PK_WL_nm"])
        if pk_lv is None and ana.get("PK_LVL_dBm") is not None:
            pk_lv = float(ana["PK_LVL_dBm"])
        if smsr is None and ana.get("SMSR_dB") is not None:
            smsr = float(ana["SMSR_dB"])
        if fwhm is None and ana.get("WD_3dB_nm") is not None:
            fwhm = float(ana["WD_3dB_nm"])
    except (TypeError, ValueError):
        pass
    return pk_wl, pk_lv, fwhm, smsr


def _merge_metrics_from_anar(
    anar: Any,
    pk_wl: Optional[float],
    pk_lv: Optional[float],
    fwhm: Optional[float],
    smsr: Optional[float],
) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
    """Fill gaps when ANAR? holds peak data but ANA? did not merge (e.g. mode-only ANA? reply)."""
    if not isinstance(anar, dict):
        return pk_wl, pk_lv, fwhm, smsr
    try:
        if pk_wl is None and anar.get("PK_WL_nm") is not None:
            pk_wl = float(anar["PK_WL_nm"])
        if pk_lv is None and anar.get("PK_LVL_dBm") is not None:
            pk_lv = float(anar["PK_LVL_dBm"])
        if smsr is None and anar.get("SMSR_dB") is not None:
            smsr = float(anar["SMSR_dB"])
        if fwhm is None and anar.get("SPEC_WD_nm") is not None:
            fwhm = float(anar["SPEC_WD_nm"])
    except (TypeError, ValueError):
        pass
    return pk_wl, pk_lv, fwhm, smsr


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
    limits_enabled: bool = False

    @classmethod
    def from_recipe(cls, recipe: Dict[str, Any]) -> "SpectrumProcessParameters":
        op = recipe.get("OPERATIONS") or recipe.get("operations") or {}
        spec = op.get("SPECTRUM") or op.get("spectrum") or {}
        pfc = recipe.get("PASS_FAIL_CRITERIA") or recipe.get("pass_fail_criteria") or {}
        pfc_s = pfc.get("SPECTRUM") or pfc.get("spectrum") or {}
        general = recipe.get("GENERAL") or recipe.get("general") or {}

        limits_enabled = False
        if isinstance(pfc_s, dict):
            limits_enabled = (
                _truthy(pfc_s.get("enable_limits"))
                or _truthy(pfc_s.get("limits_enabled"))
                or _truthy(pfc_s.get("check_limits"))
            )
        if isinstance(spec, dict) and not limits_enabled:
            limits_enabled = (
                _truthy(spec.get("enable_limits"))
                or _truthy(spec.get("limits_enabled"))
                or _truthy(spec.get("check_limits"))
            )

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
            limits_enabled=limits_enabled,
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
    span_nm: float = 10.0
    center_nm: float = 1550.0
    ref_level_dbm: float = -10.0
    level_scale_db_per_div: float = 10.0
    first_sweep_wdata: List[float] = field(default_factory=list)
    first_sweep_ldata: List[float] = field(default_factory=list)
    second_sweep_wdata: List[float] = field(default_factory=list)
    second_sweep_ldata: List[float] = field(default_factory=list)
    first_wavemeter_nm: Optional[float] = None
    second_wavemeter_nm: Optional[float] = None
    peak_wavelength_first_nm: Optional[float] = None
    peak_wavelength_second_nm: Optional[float] = None
    wavemeter_nm_for_axis_label: Optional[float] = None
    # If True, main tab may show final PASS/FAIL and Spectrum floating window closes after this emit.
    # If False, only refresh plots (first sweep done; keep floating window open until final emit).
    # Must stay False until the last result — do not flip back to True on the same object before the GUI slot runs.
    spectrum_finalize_secondary_window: bool = True


class SpectrumProcess:
    # After first sweep: main First tab + floating plot updated, then wait before re-center + second SGL.
    PAUSE_S_BEFORE_SECOND_SWEEP_S = 4.0
    # After second sweep: floating plot updated, then wait before final main-tab update / PASS row.
    PAUSE_AFTER_SECOND_SWEEP_S = 4.0
    # Extra delay after SWEEP? idle before peak/trace queries (reduces GPIB timeouts).
    POST_SWEEP_SETTLE_S = 0.35

    def __init__(self) -> None:
        self._arroyo: Any = None
        self._ando: Any = None
        self._wavemeter: Any = None

    def set_instruments(self, arroyo: Any = None, ando: Any = None, wavemeter: Any = None) -> None:
        self._arroyo = arroyo
        self._ando = ando
        self._wavemeter = wavemeter

    def _log(self, executor: Any, msg: str) -> None:
        sig = getattr(executor, "spectrum_log_message", None)
        if sig is not None and hasattr(sig, "emit"):
            sig.emit(msg)
            return
        sig = getattr(executor, "log_message", None)
        if sig is not None and hasattr(sig, "emit"):
            sig.emit(msg)

    def _emit_spectrum(self, executor: Any, result: SpectrumProcessResult) -> None:
        sig = getattr(executor, "spectrum_test_result", None)
        if sig is not None and hasattr(sig, "emit"):
            sig.emit(result)

    def _emit_live_trace(self, executor: Any, wdata: List[float], ldata: List[float]) -> None:
        """Send Ando WDATA/LDATA to the Spectrum window as plain float lists for pyqtgraph."""
        sig = getattr(executor, "spectrum_live_trace", None)
        if sig is not None and hasattr(sig, "emit"):
            pw, pl = pair_trace_floats(wdata, ldata)
            sig.emit(pw, pl)

    def _emit_wavemeter(self, executor: Any, nm: Optional[float]) -> None:
        sig = getattr(executor, "spectrum_wavemeter_reading", None)
        if sig is not None and hasattr(sig, "emit"):
            sig.emit(nm)

    def _emit_step_status(self, executor: Any, msg: str) -> None:
        """Log + Spectrum window status line (first vs second sweep)."""
        self._log(executor, "Spectrum: " + msg)
        sig = getattr(executor, "spectrum_step_status", None)
        if sig is not None and hasattr(sig, "emit"):
            sig.emit(msg)

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

    def _apply_auto_ref(self, recipe: Dict[str, Any], executor: Any) -> None:
        a = self._ando
        if a is None or not getattr(a, "is_connected", lambda: False)():
            return
        op = recipe.get("OPERATIONS") or recipe.get("operations") or {}
        spec = op.get("SPECTRUM") or op.get("spectrum") or {}
        if not isinstance(spec, dict):
            return
        on = spec.get("auto_ref_level", spec.get("AutoRefLevel"))
        wc = getattr(a, "write_command", None)
        if not callable(wc):
            return
        if _truthy(on):
            wc("ATREF1")
            self._log(executor, "Spectrum: ATREF1 (auto reference level ON).")
        else:
            wc("ATREF0")

    def _read_axes_from_ando(self, params: SpectrumProcessParameters) -> Tuple[float, float, float, float]:
        """Prefer live Ando queries (CTRWL, SPAN, REFL, LSCL) when available; else RCP params."""
        c = float(params.center_nm)
        s = float(params.span_nm)
        r = float(params.ref_level_dbm)
        ls = float(params.level_scale_db_per_div)
        a = self._ando
        if a is None or not getattr(a, "is_connected", lambda: False)():
            return c, s, r, ls
        fn = getattr(a, "get_center_wl", None)
        if callable(fn):
            try:
                v = fn()
                if v is not None:
                    c = float(v)
            except Exception:
                pass
        fn = getattr(a, "get_span", None)
        if callable(fn):
            try:
                v = fn()
                if v is not None:
                    s = max(1e-6, float(v))
            except Exception:
                pass
        fn = getattr(a, "get_ref_level", None)
        if callable(fn):
            try:
                v = fn()
                if v is not None:
                    r = float(v)
            except Exception:
                pass
        fn = getattr(a, "get_log_scale", None)
        if callable(fn):
            try:
                v = fn()
                if v is not None:
                    fv = float(v)
                    if 0.1 <= fv <= 15.0:
                        ls = fv
            except Exception:
                pass
        return c, s, r, ls

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

    def _sweep_fetch_traces_and_metrics(
        self,
        executor: Any,
        stop_requested: Callable[[], bool],
        analysis_name: str = "",
        fetch_anar: bool = False,
    ) -> Tuple[List[float], List[float], Dict[str, Any]]:
        """Single sweep, peak search, PKWL/PKLV/SPWD/SMSR/ANA?, optional ANAR? (first sweep), then WDATA/LDATA."""
        a = self._ando
        empty: Dict[str, Any] = {
            "pk_wl": None,
            "pk_lv": None,
            "fwhm": None,
            "smsr": None,
            "ana": None,
            "anar": None,
        }
        if a is None:
            return [], [], empty
        if stop_requested():
            return [], [], empty
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
        time.sleep(float(self.POST_SWEEP_SETTLE_S))
        tw = getattr(a, "trace_write_a", None)
        if callable(tw):
            tw()
        time.sleep(0.1)
        ps = getattr(a, "peak_search", None)
        if callable(ps):
            ps()
            time.sleep(0.12)
        # ANA?/ANAR? right after PKSR (same order as manual terminal). Querying PKWL?/SPWD? first can
        # confuse some USB–GPIB stacks or leave ANA? empty on certain firmware.
        qana = getattr(a, "query_analysis_ana", None)
        ana = None
        if callable(qana):
            try:
                ana = qana(analysis_name)
            except TypeError:
                ana = qana()
        anar = None
        if fetch_anar:
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
        metrics = {"pk_wl": pk_wl, "pk_lv": pk_lv, "fwhm": fwhm, "smsr": smsr, "ana": ana, "anar": anar}
        return wdata, ldata, metrics

    def _evaluate_limits(
        self,
        params: SpectrumProcessParameters,
        wavemeter_nm: Optional[float],
        pk_wl: Optional[float],
        fwhm_nm: Optional[float],
        smsr_db: Optional[float],
        label: str,
    ) -> List[str]:
        reasons: List[str] = []
        tol = float(params.wavelength_tolerance_nm)
        if tol < 900.0 and wavemeter_nm is not None and pk_wl is not None:
            if abs(float(pk_wl) - float(wavemeter_nm)) > tol:
                reasons.append(
                    "{}: peak {:.6f} nm vs wavemeter {:.6f} nm exceeds tolerance {:.3f} nm.".format(
                        label, float(pk_wl), float(wavemeter_nm), tol
                    )
                )
        if float(params.min_smsr_db) > 0.0:
            if smsr_db is None:
                reasons.append("{}: SMSR not available (limit {:.2f} dB).".format(label, params.min_smsr_db))
            elif float(smsr_db) < float(params.min_smsr_db):
                reasons.append(
                    "{}: SMSR {:.2f} dB below limit {:.2f} dB.".format(label, float(smsr_db), params.min_smsr_db)
                )
        if float(params.max_fwhm_nm) < 900.0:
            if fwhm_nm is None:
                reasons.append("{}: FWHM (SPWD) not available (max {:.4f} nm).".format(label, params.max_fwhm_nm))
            elif float(fwhm_nm) > float(params.max_fwhm_nm):
                reasons.append(
                    "{}: FWHM {:.4f} nm above limit {:.4f} nm.".format(label, float(fwhm_nm), params.max_fwhm_nm)
                )
        return reasons

    def _log_detection(self, executor: Any, lines: List[str]) -> None:
        for line in lines:
            self._log(executor, "Spectrum: {}".format(line))

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
        result.span_nm = float(params.span_nm)
        result.center_nm = float(params.center_nm)
        result.ref_level_dbm = float(params.ref_level_dbm)
        result.level_scale_db_per_div = float(params.level_scale_db_per_div)
        recipe_dict = recipe if isinstance(recipe, dict) else {}

        if self._ando is None or not getattr(self._ando, "is_connected", lambda: False)():
            result.fail_reasons.append("Ando is not connected.")
            self._emit_spectrum(executor, result)
            return result

        if self._arroyo is None or not getattr(self._arroyo, "is_connected", lambda: False)():
            result.fail_reasons.append("Arroyo is not connected (Spectrum needs TEC + laser).")
            self._emit_spectrum(executor, result)
            return result

        if self._wavemeter is None or not getattr(self._wavemeter, "is_connected", lambda: False)():
            result.fail_reasons.append("Wavemeter is not connected.")
            self._emit_spectrum(executor, result)
            return result

        ok_laser, err_laser = apply_arroyo_recipe_and_laser_on_for_spectrum(
            self._arroyo, recipe_dict, log=lambda m: self._log(executor, m)
        )
        if not ok_laser:
            result.fail_reasons.append(err_laser or "Arroyo laser setup failed.")
            self._emit_spectrum(executor, result)
            return result

        # Ando (OSA) RCP from recipe, then wavemeter range/commands from recipe (see instrument command docs).
        if not self._apply_ando_recipe(params, executor):
            result.fail_reasons.append("Failed to apply Ando settings.")
            self._emit_spectrum(executor, result)
            return result
        self._apply_wavemeter_recipe(recipe_dict, executor)
        self._apply_auto_ref(recipe_dict, executor)

        cx, sp_nm, rlv, lscl = self._read_axes_from_ando(params)
        result.center_nm = cx
        result.span_nm = sp_nm
        result.ref_level_dbm = rlv
        result.level_scale_db_per_div = lscl

        result.first_wavemeter_nm = self._read_wavemeter_nm()
        self._emit_wavemeter(executor, result.first_wavemeter_nm)

        # ----- First sweep -----
        self._emit_step_status(executor, "[1/2] First sweep — starting SGL, then peak search and WDATA/LDATA read.")
        try:
            w1, l1, m1 = self._sweep_fetch_traces_and_metrics(
                executor, stop_fn, params.analysis, fetch_anar=True
            )
        except Exception as ex:
            result.fail_reasons.append("First sweep failed: {}".format(ex))
            self._emit_spectrum(executor, result)
            return result
        ok1, det1 = detect_wdata_ldata(
            self._ando,
            w1,
            l1,
            recipe_sampling=params.sampling_points,
            query_instrument=False,
        )
        self._log_detection(executor, det1)
        if not ok1:
            result.fail_reasons.append("First sweep: WDATA/LDATA validation failed.")
            for ln in det1:
                if "FAIL" in ln or "fail" in ln.lower():
                    result.fail_reasons.append(ln.strip())
            self._emit_live_trace(executor, w1, l1)
            self._emit_spectrum(executor, result)
            return result

        if params.limits_enabled:
            lim1 = self._evaluate_limits(
                params,
                result.first_wavemeter_nm,
                m1.get("pk_wl"),
                m1.get("fwhm"),
                m1.get("smsr"),
                "First sweep",
            )
            if lim1:
                result.fail_reasons.extend(lim1)

        result.first_sweep_wdata = w1
        result.first_sweep_ldata = l1
        _ana1 = m1.get("ana")
        if isinstance(_ana1, dict) and _ana1.get("PK_WL_nm") is not None:
            try:
                result.peak_wavelength_first_nm = float(_ana1["PK_WL_nm"])
                self._log(
                    executor,
                    "Spectrum: ANA? — PK_WL = {:.6f} nm (first sweep).".format(float(_ana1["PK_WL_nm"])),
                )
            except (TypeError, ValueError):
                result.peak_wavelength_first_nm = float(m1["pk_wl"]) if m1.get("pk_wl") is not None else None
        else:
            _an1 = m1.get("anar")
            if isinstance(_an1, dict) and _an1.get("PK_WL_nm") is not None:
                try:
                    result.peak_wavelength_first_nm = float(_an1["PK_WL_nm"])
                    self._log(
                        executor,
                        "Spectrum: ANAR? — PK_WL = {:.6f} nm (first sweep).".format(float(_an1["PK_WL_nm"])),
                    )
                except (TypeError, ValueError):
                    result.peak_wavelength_first_nm = float(m1["pk_wl"]) if m1.get("pk_wl") is not None else None
            else:
                result.peak_wavelength_first_nm = float(m1["pk_wl"]) if m1.get("pk_wl") is not None else None
        # Floating Spectrum window first, then main window First sweep tab; then wait before second sweep.
        self._emit_live_trace(executor, w1, l1)
        self._emit_step_status(
            executor,
            "[1/2] First sweep — WDATA/LDATA plotted; updating main window (First sweep tab).",
        )
        result.passed = len(result.fail_reasons) == 0
        result.spectrum_finalize_secondary_window = False
        self._emit_spectrum(executor, result)
        # Leave finalize False until second sweep completes or a failure path sets True (avoid Qt queued-slot race).
        self._emit_step_status(
            executor,
            "[1/2] Waiting {:.0f} s, then set Ando CTR to ANA? peak and run second sweep.".format(
                float(self.PAUSE_S_BEFORE_SECOND_SWEEP_S)
            ),
        )
        time.sleep(float(self.PAUSE_S_BEFORE_SECOND_SWEEP_S))

        if stop_fn():
            result.fail_reasons.append("Stopped by user after first sweep.")
            result.spectrum_finalize_secondary_window = True
            self._emit_spectrum(executor, result)
            return result

        peak_for_center = _first_sweep_center_nm_for_second_sweep(m1)
        if peak_for_center is None:
            result.fail_reasons.append("First sweep: could not determine peak wavelength (ANA? PK_WL or PKWL).")
            result.spectrum_finalize_secondary_window = True
            self._emit_spectrum(executor, result)
            return result

        try:
            self._ando.set_center_wavelength(float(peak_for_center))
            self._log(
                executor,
                "Spectrum: Ando CTR set to {:.6f} nm for second sweep ({}).".format(
                    float(peak_for_center),
                    _second_sweep_center_source_note(m1),
                ),
            )
        except Exception as ex:
            result.fail_reasons.append("Failed to set Ando center to peak: {}".format(ex))
            result.spectrum_finalize_secondary_window = True
            self._emit_spectrum(executor, result)
            return result

        result.second_wavemeter_nm = self._read_wavemeter_nm()
        self._emit_wavemeter(executor, result.second_wavemeter_nm)

        self._emit_step_status(executor, "Preparing [2/2] second sweep — clearing live plot, then SGL + trace read.")
        self._emit_live_trace(executor, [], [])

        # ----- Second sweep -----
        self._emit_step_status(executor, "[2/2] Second sweep — starting SGL, then peak search and WDATA/LDATA read.")
        try:
            w2, l2, m2 = self._sweep_fetch_traces_and_metrics(
                executor, stop_fn, params.analysis, fetch_anar=False
            )
        except Exception as ex:
            result.fail_reasons.append("Second sweep failed: {}".format(ex))
            result.spectrum_finalize_secondary_window = True
            self._emit_spectrum(executor, result)
            return result
        ok2, det2 = detect_wdata_ldata(
            self._ando,
            w2,
            l2,
            recipe_sampling=params.sampling_points,
            query_instrument=False,
        )
        self._log_detection(executor, det2)
        if not ok2:
            result.fail_reasons.append("Second sweep: WDATA/LDATA validation failed.")
            for ln in det2:
                if "FAIL" in ln or "fail" in ln.lower():
                    result.fail_reasons.append(ln.strip())
            self._emit_live_trace(executor, w2, l2)
            result.spectrum_finalize_secondary_window = True
            self._emit_spectrum(executor, result)
            return result

        if params.limits_enabled:
            lim2 = self._evaluate_limits(
                params,
                result.second_wavemeter_nm,
                m2.get("pk_wl"),
                m2.get("fwhm"),
                m2.get("smsr"),
                "Second sweep",
            )
            if lim2:
                result.fail_reasons.extend(lim2)

        result.second_sweep_wdata = w2
        result.second_sweep_ldata = l2
        result.peak_wavelength_second_nm = float(m2["pk_wl"]) if m2.get("pk_wl") is not None else None
        self._emit_live_trace(executor, w2, l2)
        self._emit_step_status(
            executor,
            "[2/2] Second sweep — WDATA/LDATA plotted in Spectrum window. Waiting {:.0f} s, then main tab + result.".format(
                float(self.PAUSE_AFTER_SECOND_SWEEP_S),
            ),
        )
        time.sleep(float(self.PAUSE_AFTER_SECOND_SWEEP_S))

        pk_nm = float(m2["pk_wl"]) if m2.get("pk_wl") is not None else float(peak_for_center)
        pk_dbm = float(m2["pk_lv"]) if m2.get("pk_lv") is not None else 0.0
        result.peak_wavelength = pk_nm
        result.peak_level_dbm = pk_dbm
        result.peak_power = _dbm_to_mw(pk_dbm)
        result.smsr = float(m2["smsr"]) if m2.get("smsr") is not None else 0.0
        result.fwhm = float(m2["fwhm"]) if m2.get("fwhm") is not None else 0.0
        result.wavemeter_nm_for_axis_label = result.second_wavemeter_nm

        cx2, sp2, rlv2, lscl2 = self._read_axes_from_ando(params)
        result.center_nm = cx2
        result.span_nm = sp2
        result.ref_level_dbm = rlv2
        result.level_scale_db_per_div = lscl2

        result.passed = len(result.fail_reasons) == 0
        result.spectrum_finalize_secondary_window = True

        self._emit_spectrum(executor, result)
        return result
