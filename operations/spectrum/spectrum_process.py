"""
Spectrum test step: TEC + laser on, apply RCP to Ando + wavemeter, two single sweeps.

After each sweep: UI and plots update immediately (no fixed delay between sweeps or before the final
main-tab result). First sweep updates the **First sweep** sub-tab only; second sweep updates the
**Second sweep** (primary) sub-tab. ANAR? / ANA? layouts follow recipe analysis (DFB-LD, LED, FP-LD);
second-sweep center wavelength uses ANAR? PK_WL_nm, else ANA? ``PK_WL_nm`` / comma fields, else PKWL? / trace peak.

WDATA/LDATA validation matches terminal scripts; ANA? fields include ``EXTRA_nm`` (4th value) when present.
Pass/fail limits run when the recipe enables them (flags) or defines SPECTRUM limits / thresholds
(PASS_FAIL_CRITERIA.SPECTRUM and OPERATIONS.SPECTRUM.limits: SMSR/FWHM scalars merged; Peak WL / Cen WL use absolute LL/UL vs measured peak / center wavelength).
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


def _parse_limit_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _spec_limits_any_row_enabled(spec: Dict[str, Any]) -> bool:
    lim = spec.get("limits") if isinstance(spec.get("limits"), dict) else None
    if not lim:
        return False
    for sub in lim.values():
        if not isinstance(sub, dict):
            continue
        if _truthy(sub.get("enable", sub.get("Enable", False))):
            return True
    return False


def _merge_spectrum_limits_from_operations_spec(
    spec: Dict[str, Any],
    min_smsr_db: float,
    max_fwhm_nm: float,
    wavelength_tolerance_nm: float,
) -> Tuple[float, float, float, float]:
    """
    Merge SMSR / FWHM rows from OPERATIONS.SPECTRUM.limits into scalar thresholds.
    Peak WL / Cen WL are **not** merged here — they use absolute LL/UL bands via SpectrumProcessParameters.
    """
    lim = spec.get("limits") if isinstance(spec.get("limits"), dict) else None
    if not lim:
        return float(min_smsr_db), float(max_fwhm_nm), float(wavelength_tolerance_nm), 0.0

    ms, mf, wt = float(min_smsr_db), float(max_fwhm_nm), float(wavelength_tolerance_nm)
    min_fwhm = 0.0

    for key in ("SMSR", "smsr"):
        sub = lim.get(key)
        if not isinstance(sub, dict) or not _truthy(sub.get("enable", sub.get("Enable", False))):
            continue
        ll = _parse_limit_float(sub.get("ll", sub.get("LL")))
        if ll is not None:
            ms = max(ms, ll)

    for key in ("FWHM", "fwhm"):
        sub = lim.get(key)
        if not isinstance(sub, dict) or not _truthy(sub.get("enable", sub.get("Enable", False))):
            continue
        ul = _parse_limit_float(sub.get("ul", sub.get("UL")))
        if ul is not None:
            mf = min(mf, ul)
        ll_f = _parse_limit_float(sub.get("ll", sub.get("LL")))
        if ll_f is not None:
            min_fwhm = max(min_fwhm, ll_f)

    return ms, mf, wt, min_fwhm


def _parse_peak_cen_wl_bands_from_spec(spec: Dict[str, Any]) -> Tuple[bool, Optional[float], Optional[float], bool, Optional[float], Optional[float]]:
    """Peak WL / Cen WL rows: enabled + LL/UL as absolute wavelength bands (nm)."""
    lim = spec.get("limits") if isinstance(spec.get("limits"), dict) else None
    if not lim:
        return False, None, None, False, None, None

    def one(param_names: Tuple[str, ...]) -> Tuple[bool, Optional[float], Optional[float]]:
        sub = None
        for p in param_names:
            sub = lim.get(p) or lim.get(p.replace(" ", ""))
            if isinstance(sub, dict):
                break
        if not isinstance(sub, dict) or not _truthy(sub.get("enable", sub.get("Enable", False))):
            return False, None, None
        return True, _parse_limit_float(sub.get("ll", sub.get("LL"))), _parse_limit_float(sub.get("ul", sub.get("UL")))

    pk_e, pk_ll, pk_ul = one(("Peak WL", "PeakWL"))
    cn_e, cn_ll, cn_ul = one(("Cen WL", "CenWL"))
    return pk_e, pk_ll, pk_ul, cn_e, cn_ll, cn_ul


def _center_wl_nm_from_metrics(m: Dict[str, Any]) -> Optional[float]:
    """Center wavelength for Cen WL limits: LED MEAN WL, else PK + MODE offset, else peak."""
    anar = m.get("anar") if isinstance(m.get("anar"), dict) else {}
    ana = m.get("ana") if isinstance(m.get("ana"), dict) else {}
    if anar.get("MEAN_WL_nm") is not None:
        try:
            return float(anar["MEAN_WL_nm"])
        except (TypeError, ValueError):
            pass
    pk = m.get("pk_wl")
    for d in (anar, ana):
        if not isinstance(d, dict):
            continue
        pw = d.get("PK_WL_nm")
        if pw is None:
            pw = pk
        mo = d.get("MODE_OFFSET_nm")
        if pw is not None and mo is not None:
            try:
                return float(pw) + float(mo)
            except (TypeError, ValueError):
                pass
    if pk is not None:
        try:
            return float(pk)
        except (TypeError, ValueError):
            pass
    return None


def _wl_band_failures(
    label: str,
    param_name: str,
    value_nm: Optional[float],
    ll_nm: Optional[float],
    ul_nm: Optional[float],
) -> List[str]:
    """Absolute band: value within [LL, UL] for whichever bounds are set."""
    if value_nm is None:
        return ["{}: {} not available (LL/UL check).".format(label, param_name)]
    v = float(value_nm)
    out: List[str] = []
    if ll_nm is not None and v < float(ll_nm):
        out.append("{}: {} {:.6f} nm below LL {:.6f} nm.".format(label, param_name, v, float(ll_nm)))
    if ul_nm is not None and v > float(ul_nm):
        out.append("{}: {} {:.6f} nm above UL {:.6f} nm.".format(label, param_name, v, float(ul_nm)))
    return out


def _should_enable_spectrum_limit_checks(
    pfc_s: Any,
    spec: Dict[str, Any],
    min_smsr_db: float,
    max_fwhm_nm: float,
    wavelength_tolerance_nm: float,
    peak_wl_check: bool = False,
    cen_wl_check: bool = False,
    min_fwhm_nm: float = 0.0,
) -> bool:
    if peak_wl_check or cen_wl_check:
        return True
    if min_fwhm_nm > 0.0:
        return True
    if isinstance(pfc_s, dict):
        if (
            _truthy(pfc_s.get("enable_limits"))
            or _truthy(pfc_s.get("limits_enabled"))
            or _truthy(pfc_s.get("check_limits"))
        ):
            return True
    if isinstance(spec, dict):
        if (
            _truthy(spec.get("enable_limits"))
            or _truthy(spec.get("limits_enabled"))
            or _truthy(spec.get("check_limits"))
        ):
            return True
        if _spec_limits_any_row_enabled(spec):
            return True
    if min_smsr_db > 0.0:
        return True
    if max_fwhm_nm < 899.5:
        return True
    if wavelength_tolerance_nm < 899.5:
        return True
    return False


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
    peak_wl_check: bool = False
    peak_wl_ll: Optional[float] = None
    peak_wl_ul: Optional[float] = None
    cen_wl_check: bool = False
    cen_wl_ll: Optional[float] = None
    cen_wl_ul: Optional[float] = None
    min_fwhm_nm: float = 0.0
    # Recipe ``wl_shift`` (nm) applied at start on Ando ``WLSFT``; see ``auto_wl_shift_wavemeter_minus_peak``.
    wl_shift_nm: float = 0.0
    # After sweep 1: set Ando ``WLSFT`` to (wavemeter − Ando peak used for CTR) when both are valid.
    auto_wl_shift_wavemeter_minus_peak: bool = True
    # While waiting for sweep 1 to finish, poll wavemeter and update the Spectrum window (throttled).
    wavemeter_poll_during_first_sweep: bool = True

    @classmethod
    def from_recipe(cls, recipe: Dict[str, Any]) -> "SpectrumProcessParameters":
        op = recipe.get("OPERATIONS") or recipe.get("operations") or {}
        spec = op.get("SPECTRUM") or op.get("spectrum") or {}
        if not isinstance(spec, dict):
            spec = {}
        pfc = recipe.get("PASS_FAIL_CRITERIA") or recipe.get("pass_fail_criteria") or {}
        pfc_s = pfc.get("SPECTRUM") or pfc.get("spectrum") or {}
        if not isinstance(pfc_s, dict):
            pfc_s = {}
        general = recipe.get("GENERAL") or recipe.get("general") or {}

        min_smsr_db = _get_float(
            pfc_s, ["min_SMSR_dB", "SMSR_Min_dB", "min_smsr_dB"], _get_float(spec, ["SMSR_Min_dB"], 0.0)
        )
        max_fwhm_nm = _get_float(
            pfc_s, ["max_FWHM_nm", "FWHM_Max_nm", "max_fwhm_nm"], _get_float(spec, ["FWHM_Max_nm"], 999.0)
        )
        wavelength_tolerance_nm = _get_float(
            pfc_s, ["wavelength_tolerance_nm", "WavelengthTolerance_nm"], 999.0
        )
        min_smsr_db, max_fwhm_nm, wavelength_tolerance_nm, min_fwhm_nm = _merge_spectrum_limits_from_operations_spec(
            spec, min_smsr_db, max_fwhm_nm, wavelength_tolerance_nm
        )
        peak_wl_check, peak_wl_ll, peak_wl_ul, cen_wl_check, cen_wl_ll, cen_wl_ul = _parse_peak_cen_wl_bands_from_spec(
            spec
        )
        limits_enabled = _should_enable_spectrum_limit_checks(
            pfc_s,
            spec,
            min_smsr_db,
            max_fwhm_nm,
            wavelength_tolerance_nm,
            peak_wl_check=peak_wl_check,
            cen_wl_check=cen_wl_check,
            min_fwhm_nm=min_fwhm_nm,
        )

        # Prefer snake_case / INI keys so merged vendor+file dicts use the file values, not template CamelCase.
        center = _get_float(spec, ["center_nm", "CenterWL", "center", "wavelength"], 1550.0)
        if center <= 0:
            center = _to_float(general.get("Wavelength"), 1550.0) or _to_float(recipe.get("Wavelength"), 1550.0)

        wl_shift_nm = _get_float(spec, ["wl_shift", "WlShift", "WL_Shift", "wlShift"], 0.0)
        auto_wm = spec.get("auto_wl_shift_wavemeter", spec.get("auto_wl_shift"))
        if auto_wm is None:
            auto_wl_shift_wavemeter_minus_peak = True
        else:
            auto_wl_shift_wavemeter_minus_peak = _truthy(auto_wm)
        poll_wm = spec.get("wavemeter_during_first_sweep", spec.get("wavemeter_poll_first_sweep"))
        if poll_wm is None:
            wavemeter_poll_during_first_sweep = True
        else:
            wavemeter_poll_during_first_sweep = _truthy(poll_wm)

        return cls(
            center_nm=float(center),
            span_nm=_get_float(spec, ["span_nm", "Span"], 10.0),
            resolution_nm=_get_float(spec, ["resolution_nm", "Resolution"], 0.1),
            sampling_points=int(
                max(11, min(20001, _get_float(spec, ["sampling", "Sampling", "sampling_points"], 501)))
            ),
            ref_level_dbm=_get_float(spec, ["ref_level_dbm", "ref_level_dBm", "RefLevel"], -10.0),
            level_scale_db_per_div=_get_float(spec, ["level_scale_db_per_div", "level_scale", "LevelScale"], 10.0),
            temperature_c=_get_float(spec, ["temperature", "Temperature"], 25.0),
            laser_current_mA=_get_float(spec, ["current", "Current", "laser_current_mA"], 0.0),
            sensitivity=_get_str(spec, ["sensitivity", "Sensitivity"], "MID"),
            analysis=_get_str(spec, ["analysis", "Analysis"], "DFB-LD"),
            min_smsr_db=min_smsr_db,
            max_fwhm_nm=max_fwhm_nm,
            wavelength_tolerance_nm=wavelength_tolerance_nm,
            limits_enabled=limits_enabled,
            peak_wl_check=peak_wl_check,
            peak_wl_ll=peak_wl_ll,
            peak_wl_ul=peak_wl_ul,
            cen_wl_check=cen_wl_check,
            cen_wl_ll=cen_wl_ll,
            cen_wl_ul=cen_wl_ul,
            min_fwhm_nm=min_fwhm_nm,
            wl_shift_nm=float(wl_shift_nm),
            auto_wl_shift_wavemeter_minus_peak=auto_wl_shift_wavemeter_minus_peak,
            wavemeter_poll_during_first_sweep=wavemeter_poll_during_first_sweep,
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
    peak_level_first_dbm: Optional[float] = None
    fwhm_first_nm: Optional[float] = None
    smsr_first_db: Optional[float] = None
    passed_first_sweep: bool = False
    wavemeter_nm_for_axis_label: Optional[float] = None
    # If True, main tab may show final PASS/FAIL and Spectrum floating window closes after this emit.
    # If False, only refresh plots (first sweep done; keep floating window open until final emit).
    # Must stay False until the last result — do not flip back to True on the same object before the GUI slot runs.
    spectrum_finalize_secondary_window: bool = True
    # Ando WLSFT applied before sweep 2 when ``auto_wl_shift_wavemeter_minus_peak`` is enabled (nm).
    wl_shift_applied_nm: Optional[float] = None


class SpectrumProcess:
    PAUSE_S_BEFORE_SECOND_SWEEP_S = 0.0
    PAUSE_AFTER_SECOND_SWEEP_S = 0.0

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

    def _wait_sweep_done_with_wavemeter_poll(
        self, executor: Any, stop_requested: Callable[[], bool], poll_wavemeter: bool
    ) -> bool:
        """
        Wait until Ando single sweep finishes. If ``poll_wavemeter``, read the wavemeter on a
        throttled interval and emit to the GUI (first sweep live display).
        """
        a = self._ando
        if a is None:
            return False
        t0 = time.time()
        last_wm_emit = 0.0
        wm_interval_s = 0.12
        while (time.time() - t0) < 180.0:
            if stop_requested():
                ss = getattr(a, "stop_sweep", None)
                if callable(ss):
                    ss()
                return False
            if getattr(a, "is_sweep_done", lambda: True)():
                return True
            if poll_wavemeter:
                now = time.time()
                if now - last_wm_emit >= wm_interval_s:
                    self._emit_wavemeter(executor, self._read_wavemeter_nm())
                    last_wm_emit = now
            time.sleep(0.04)
        return bool(getattr(a, "is_sweep_done", lambda: True)())

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
        if abs(float(params.wl_shift_nm)) > 1e-9:
            fn = getattr(a, "set_wavelength_shift_nm", None)
            if callable(fn):
                try:
                    fn(float(params.wl_shift_nm))
                    self._log(
                        executor,
                        "Spectrum: Ando WLSFT {:.6f} nm (recipe wl_shift).".format(float(params.wl_shift_nm)),
                    )
                except Exception as ex:
                    self._log(executor, "Spectrum: recipe wl_shift not applied: {}".format(ex))
            else:
                try:
                    a.write_command("WLSFT {:.6f}".format(float(params.wl_shift_nm)))
                    self._log(
                        executor,
                        "Spectrum: Ando WLSFT {:.6f} nm (recipe wl_shift, generic write).".format(
                            float(params.wl_shift_nm)
                        ),
                    )
                except Exception as ex:
                    self._log(executor, "Spectrum: recipe wl_shift write failed: {}".format(ex))
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
        poll_wavemeter_during_wait: bool = False,
    ) -> Tuple[List[float], List[float], Dict[str, Any]]:
        """
        Fast sweep + read (reference pattern):
          1. SGL + wait
          2. WRTA (select trace A)
          3. Execute analysis (DFBAN / LEDAN / FPAN) — must run AFTER sweep
          4. ANA? → (fwhm, peak_wl, pk_lv, smsr)
          5. Fallback: SPWD?, SMSR?, PKWL?, PKLV?
          6. WDATA/LDATA for trace plot
        """
        a = self._ando
        empty: Dict[str, Any] = {
            "pk_wl": None, "pk_lv": None, "fwhm": None, "smsr": None,
            "ana": None, "anar": None,
        }
        if a is None or stop_requested():
            return [], [], empty

        a.single_sweep()
        if poll_wavemeter_during_wait:
            if not self._wait_sweep_done_with_wavemeter_poll(executor, stop_requested, True):
                return [], [], empty
        else:
            wait = getattr(a, "wait_sweep_done", None)
            if callable(wait):
                try:
                    wait(timeout_s=180.0, stop_requested=stop_requested)
                except TypeError:
                    wait(timeout_s=180.0)
            else:
                t0 = time.time()
                while (time.time() - t0) < 180.0:
                    if stop_requested():
                        ss = getattr(a, "stop_sweep", None)
                        if callable(ss):
                            ss()
                        return [], [], empty
                    if getattr(a, "is_sweep_done", lambda: True)():
                        break
                    time.sleep(0.04)
        if stop_requested():
            return [], [], empty

        tw = getattr(a, "trace_write_a", None)
        if callable(tw):
            tw()

        # Execute analysis AFTER sweep completes (DFBAN/LEDAN/FPAN)
        _analysis_command(a, analysis_name)

        # ANA? returns FWHM + peak WL + peak level (+ often SMSR) in one query
        ana = None
        qana = getattr(a, "query_analysis_ana", None)
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

        pk_wl: Optional[float] = None
        pk_lv: Optional[float] = None
        fwhm: Optional[float] = None
        smsr: Optional[float] = None

        if isinstance(ana, dict):
            for key, target in (
                ("PK_WL_nm", "pk_wl"), ("PK_LVL_dBm", "pk_lv"),
                ("WD_3dB_nm", "fwhm"), ("SMSR_dB", "smsr"),
            ):
                if ana.get(key) is not None:
                    try:
                        val = float(ana[key])
                        if target == "pk_wl":
                            pk_wl = val
                        elif target == "pk_lv":
                            pk_lv = val
                        elif target == "fwhm":
                            fwhm = val
                        elif target == "smsr":
                            smsr = val
                    except (TypeError, ValueError):
                        pass

        if isinstance(anar, dict):
            if pk_wl is None and anar.get("PK_WL_nm") is not None:
                try:
                    pk_wl = float(anar["PK_WL_nm"])
                except (TypeError, ValueError):
                    pass
            if pk_lv is None and anar.get("PK_LVL_dBm") is not None:
                try:
                    pk_lv = float(anar["PK_LVL_dBm"])
                except (TypeError, ValueError):
                    pass
            if smsr is None and anar.get("SMSR_dB") is not None:
                try:
                    smsr = float(anar["SMSR_dB"])
                except (TypeError, ValueError):
                    pass

        # Fallback: SPWD? for FWHM only when ANA?/ANAR? didn't provide it.
        # SMSR?/PKWL?/PKLV? return bogus "1" on this AQ6317B firmware — skip them.
        # Peak WL/level fallback comes from WDATA/LDATA trace below.
        if fwhm is None:
            v = getattr(a, "query_spectral_width_nm", lambda: None)()
            if v is not None:
                try:
                    fwhm = float(v)
                except (TypeError, ValueError):
                    pass

        # WDATA/LDATA for the trace plot
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
        cen_wl_nm: Optional[float],
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
        if params.peak_wl_check and (params.peak_wl_ll is not None or params.peak_wl_ul is not None):
            reasons.extend(_wl_band_failures(label, "Peak WL", pk_wl, params.peak_wl_ll, params.peak_wl_ul))
        if params.cen_wl_check and (params.cen_wl_ll is not None or params.cen_wl_ul is not None):
            reasons.extend(
                _wl_band_failures(label, "Cen WL", cen_wl_nm, params.cen_wl_ll, params.cen_wl_ul)
            )
        if float(params.min_smsr_db) > 0.0:
            if smsr_db is None:
                reasons.append("{}: SMSR not available (limit {:.2f} dB).".format(label, params.min_smsr_db))
            elif float(smsr_db) < float(params.min_smsr_db):
                reasons.append(
                    "{}: SMSR {:.2f} dB below limit {:.2f} dB.".format(label, float(smsr_db), params.min_smsr_db)
                )
        if float(params.min_fwhm_nm) > 0.0:
            if fwhm_nm is None:
                reasons.append("{}: FWHM (SPWD) not available (min {:.4f} nm).".format(label, params.min_fwhm_nm))
            elif float(fwhm_nm) < float(params.min_fwhm_nm):
                reasons.append(
                    "{}: FWHM {:.4f} nm below limit {:.4f} nm.".format(label, float(fwhm_nm), params.min_fwhm_nm)
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

        _arm_laser_fn = getattr(executor, "notify_laser_monitor_armed", None)
        if callable(_arm_laser_fn):
            try:
                _arm_laser_fn(True)
            except Exception:
                pass

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
        self._emit_step_status(executor, "[1/2] First sweep — starting SGL, then analysis read and WDATA/LDATA.")
        try:
            w1, l1, m1 = self._sweep_fetch_traces_and_metrics(
                executor,
                stop_fn,
                params.analysis,
                fetch_anar=True,
                poll_wavemeter_during_wait=params.wavemeter_poll_during_first_sweep,
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

        # Plot as soon as trace data is valid (before limits / peak parsing) so the UI updates immediately.
        result.first_sweep_wdata = w1
        result.first_sweep_ldata = l1
        self._emit_live_trace(executor, w1, l1)

        if params.limits_enabled:
            lim1 = self._evaluate_limits(
                params,
                result.first_wavemeter_nm,
                m1.get("pk_wl"),
                _center_wl_nm_from_metrics(m1),
                m1.get("fwhm"),
                m1.get("smsr"),
                "First sweep",
            )
            if lim1:
                result.fail_reasons.extend(lim1)

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
        result.peak_level_first_dbm = float(m1["pk_lv"]) if m1.get("pk_lv") is not None else None
        result.fwhm_first_nm = float(m1["fwhm"]) if m1.get("fwhm") is not None else None
        result.smsr_first_db = float(m1["smsr"]) if m1.get("smsr") is not None else None
        result.passed_first_sweep = len(result.fail_reasons) == 0
        # Live trace was already emitted right after WDATA/LDATA validation.
        self._emit_step_status(
            executor,
            "[1/2] First sweep — WDATA/LDATA plotted; updating main window (First sweep tab).",
        )
        result.passed = len(result.fail_reasons) == 0
        result.spectrum_finalize_secondary_window = False
        self._emit_spectrum(executor, result)
        # Leave finalize False until second sweep completes or a failure path sets True (avoid Qt queued-slot race).
        _p1 = float(self.PAUSE_S_BEFORE_SECOND_SWEEP_S)
        if _p1 > 0:
            self._emit_step_status(
                executor,
                "[1/2] Waiting {:.0f} s, then set Ando CTR to ANA? peak and run second sweep.".format(_p1),
            )
            time.sleep(_p1)
        else:
            self._emit_step_status(
                executor,
                "[1/2] First sweep done — setting Ando CTR to ANA? peak and running second sweep.",
            )

        if stop_fn():
            if getattr(executor, "_stop_from_user", True):
                result.fail_reasons.append("Stopped by user after first sweep.")
            else:
                result.fail_reasons.append(
                    "Arroyo laser output went OFF after first sweep — Spectrum test stopped."
                )
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

        wm_here = self._read_wavemeter_nm()
        self._emit_wavemeter(executor, wm_here)
        result.second_wavemeter_nm = wm_here

        if params.auto_wl_shift_wavemeter_minus_peak and wm_here is not None:
            try:
                delta = float(wm_here) - float(peak_for_center)
                result.wl_shift_applied_nm = float(delta)
                fn = getattr(self._ando, "set_wavelength_shift_nm", None)
                if callable(fn):
                    fn(float(delta))
                else:
                    self._ando.write_command("WLSFT {:.6f}".format(float(delta)))
                self._log(
                    executor,
                    "Spectrum: Ando WLSFT {:.6f} nm (wavemeter {:.6f} nm − Ando peak / CTR {:.6f} nm).".format(
                        float(delta),
                        float(wm_here),
                        float(peak_for_center),
                    ),
                )
            except Exception as ex:
                self._log(executor, "Spectrum: auto WLSFT (wavemeter − peak) skipped: {}".format(ex))
                result.wl_shift_applied_nm = None

        self._emit_step_status(executor, "Preparing [2/2] second sweep — SGL + trace read (first trace stays until new data).")

        # ----- Second sweep -----
        self._emit_step_status(executor, "[2/2] Second sweep — starting SGL, then analysis read and WDATA/LDATA.")
        try:
            w2, l2, m2 = self._sweep_fetch_traces_and_metrics(
                executor, stop_fn, params.analysis, fetch_anar=False, poll_wavemeter_during_wait=False
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

        result.second_sweep_wdata = w2
        result.second_sweep_ldata = l2
        result.peak_wavelength_second_nm = float(m2["pk_wl"]) if m2.get("pk_wl") is not None else None
        # Plot second sweep immediately after validation (before pass/fail limit checks).
        self._emit_live_trace(executor, w2, l2)

        if params.limits_enabled:
            lim2 = self._evaluate_limits(
                params,
                result.second_wavemeter_nm,
                m2.get("pk_wl"),
                _center_wl_nm_from_metrics(m2),
                m2.get("fwhm"),
                m2.get("smsr"),
                "Second sweep",
            )
            if lim2:
                result.fail_reasons.extend(lim2)
        _p2 = float(self.PAUSE_AFTER_SECOND_SWEEP_S)
        if _p2 > 0:
            self._emit_step_status(
                executor,
                "[2/2] Second sweep — plotted. Waiting {:.0f} s, then main tab + result.".format(_p2),
            )
            time.sleep(_p2)
        else:
            self._emit_step_status(
                executor,
                "[2/2] Second sweep — updating main tab and result.",
            )

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
