"""
Temperature stability: Part A — program Arroyo (THI, initial T, current), enable TEC + laser,
then Ando phase-1 wide sweep → peak as narrow center + Part B — cold→hot search with hot→cold verification.

- TEC and laser must be ON before any Ando sweep: no optical signal otherwise, and TEC output must be ON
  for the controller to regulate temperature toward the setpoint.
- Phase 1 Ando: center from Spectrum recipe; span fixed (``STABILITY_WIDE_SPAN_NM``, 2 nm); resolution / SMPL / analysis fixed in code for peak find.
- Thorlabs powermeter must be connected for this step.
- If ``ContinuousScan``: after narrow Ando setup, ``repeat_sweep`` (RPT) so per-point reads skip ``SGL``.

- Cold→hot sweep: ``MinTemp`` → ``MaxTemp`` (see ``docs/TEMPERATURE_STABILITY_COMPLETE_PROCESS.md``).
- Required stable span °C = ``DegOfStability`` (recipe).
- Recovery: ``RecoverySteps`` = N → test fails on **N+1** consecutive failed setpoints (after retries).
- ``RecoveryStep_C``: min °C between fails; if the next fail is too soon, degree-of-stability tracking resets.
- Pass: first upward window where all points are stable and span ≥ deg span, then hot→cold
  on that window passes; if verification fails, resume upward from the top of the window.
- Raw CSV + ``raw_measurement_rows`` include every attempt (retries); summary plots omit retry rows.
+ optional Δλ/°C.
"""
from __future__ import annotations

import csv
import math
import re
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Optional, Set, Tuple

from operations.arroyo_laser_helpers import arroyo_laser_on_safe
from operations.recipe_ts_helpers import first_in_dict
from operations.result_saver import get_results_root
from operations.spectrum.spectrum_process import (
    SpectrumProcessParameters,
    _analysis_command,
    _recipe_sensitivity_to_ando,
    _truthy,
)

# Phase-1 initial Ando sweep: fixed span (nm) to locate the peak; center from recipe.
STABILITY_WIDE_SPAN_NM = 2.0
# Brief pause before remeasuring at the same T after a failed attempt (limits / recovery / Thorlabs).
STABILITY_RETRY_SETTLE_S = 0.2


def _interruptible_sleep(seconds: float, stop_requested: Callable[[], bool],
                         chunk: float = 0.25) -> bool:
    """Sleep in small chunks, returning True immediately if stop is requested."""
    remaining = max(0.0, float(seconds))
    while remaining > 0.0:
        if stop_requested():
            return True
        step = min(chunk, remaining)
        time.sleep(step)
        remaining -= step
    return stop_requested()


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        if v is None or v == "":
            return default
        return float(v)
    except (TypeError, ValueError):
        return default


def _read_finite_temp_celsius(blk: Any, keys: Tuple[str, ...]) -> Optional[float]:
    """First finite float from ``blk`` for any of ``keys``; None if missing or invalid."""
    if not isinstance(blk, dict):
        return None
    v = first_in_dict(blk, keys, "")
    if v == "" or v is None:
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(x):
        return None
    return x


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


def _find_window_ending_at(
    stable_flags: List[bool], temps: List[float], min_span_c: float, end_idx: int
) -> Optional[Tuple[int, int]]:
    """Smallest ``i`` such that ``[i..end_idx]`` are all stable and ``temps[end_idx]-temps[i] >= min_span_c``."""
    if end_idx < 0 or end_idx >= len(temps) or len(stable_flags) != len(temps):
        return None
    if not stable_flags[end_idx]:
        return None
    ms = float(max(1e-6, min_span_c))
    for i in range(end_idx + 1):
        if temps[end_idx] - temps[i] + 1e-9 < ms:
            continue
        if all(stable_flags[k] for k in range(i, end_idx + 1)):
            return (i, end_idx)
    return None


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
    """Merge TS slot Initial temperature + drive current into OPERATIONS.SPECTRUM for Arroyo configure + laser ON."""
    stab = _get_block(recipe, slot)
    op = dict(recipe.get("OPERATIONS") or {})
    spec = dict(op.get("SPECTRUM") or {})
    liv = op.get("LIV") or {}
    if not isinstance(liv, dict):
        liv = {}
    init_t = _read_finite_temp_celsius(
        stab, ("InitialTemperature", "initial_temp_c", "Initial_Temp", "InitTemp")
    )
    if init_t is not None:
        spec["Temperature"] = float(init_t)
    use_rated = _truthy(stab.get("UseI_at_Rated_P", stab.get("use_I_at_rated", False)))
    set_m = _to_float(stab.get("SetCurrent_mA", stab.get("set_current_mA", 0)), 0)
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


def _recipe_ts_ando_offsets_nm(recipe: Dict[str, Any], slot: int) -> Tuple[Optional[float], Optional[float]]:
    """Return (offset1_nm, offset2_nm) from the TS block if present."""
    stab = _get_block(recipe, slot)
    if not isinstance(stab, dict):
        return (None, None)
    o1 = first_in_dict(stab, ("Offset1_nm", "offset1_nm", "Offset1", "offset1"), "")
    o2 = first_in_dict(stab, ("Offset2_nm", "offset2_nm", "Offset2", "offset2"), "")
    off1 = None if o1 in ("", None) else _to_float(o1, float("nan"))
    off2 = None if o2 in ("", None) else _to_float(o2, float("nan"))
    if off1 is not None and (not math.isfinite(float(off1))):
        off1 = None
    if off2 is not None and (not math.isfinite(float(off2))):
        off2 = None
    return (float(off1) if off1 is not None else None, float(off2) if off2 is not None else None)


@dataclass
class TemperatureStabilityParameters:
    #: Sweep temperatures (°C) — always filled from recipe in ``from_recipe_blocks`` (no hardcoded 25/45 defaults).
    initial_temp_c: float = float("nan")
    max_temp_c: float = float("nan")
    step_temp_c: float = 2.0
    min_temp_c: float = float("nan")
    wait_step_ms: int = 0
    continuous_scan: bool = False
    fwhm_recovery_threshold_nm: float = 0.3
    #: Number of measurement attempts at the same T setpoint (not 1 + retries).
    max_retries_same_point: int = 5
    tec_tolerance_c: float = 0.5
    tec_settle_timeout_s: float = 300.0
    preamble_pause_s: float = 2.0
    ando_span_nm: float = 2.0
    ando_sampling_points: int = 1001
    ando_resolution_nm: float = 0.05
    analysis: str = "DFB-LD"
    #: Required continuous stable temperature span (°C) to qualify (``DegOfStability`` in recipe).
    deg_span_c: float = 5.0
    #: N in “Recovery Steps = N”: fail the test on **N+1** consecutive failed setpoints (after retries).
    recovery_steps_n: int = 2
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
    #: Minimum stable temperature span (°C) after an exceed before another (recipe ``RecoveryStep_C``).
    recovery_step_c: float = 0.7
    #: When True, SMSR used for limits / plots / stored series = raw SMSR (dB) − peak level (dBm).
    smsr_correction_enabled: bool = False
    thorlabs_required: bool = False
    thorlabs_ll_enabled: bool = False
    thorlabs_ul_enabled: bool = False
    thorlabs_ll_mw: float = 0.0
    thorlabs_ul_mw: float = 999999.0

    @classmethod
    def from_recipe_blocks(cls, recipe: Dict[str, Any], slot: int) -> "TemperatureStabilityParameters":
        stab = _get_block(recipe, slot)
        spec = (recipe.get("OPERATIONS") or recipe.get("operations") or {}).get("SPECTRUM") or {}
        if not isinstance(spec, dict):
            spec = {}
        g = recipe.get("GENERAL") or recipe.get("general") or {}
        if not isinstance(g, dict):
            g = {}
        op = recipe.get("OPERATIONS") or recipe.get("operations") or {}
        if not isinstance(op, dict):
            op = {}
        liv_blk = op.get("LIV") or op.get("liv") or recipe.get("LIV") or {}
        if not isinstance(liv_blk, dict):
            liv_blk = {}

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

        initial_o = _read_finite_temp_celsius(stab, ("InitialTemperature", "initial_temp_c", "Initial_Temp", "InitTemp"))
        if initial_o is None:
            initial_o = _read_finite_temp_celsius(spec, ("temperature", "Temperature"))
        if initial_o is None:
            initial_o = _read_finite_temp_celsius(g, ("temperature", "Temperature"))
        if initial_o is None:
            initial_o = _read_finite_temp_celsius(liv_blk, ("temperature", "Temperature"))

        mx_o = _read_finite_temp_celsius(stab, ("MaxTemperature", "max_temp_c", "MaxTemp", "Max_Temp"))
        min_o = _read_finite_temp_celsius(
            stab, ("MinTemp", "min_temp_c", "PreambleMinTemp", "MINTemp", "MinTemperature")
        )

        if min_o is None and initial_o is not None and mx_o is not None:
            min_o = min(float(initial_o), float(mx_o))
        if initial_o is None and min_o is not None and mx_o is not None:
            initial_o = min(float(min_o), float(mx_o))
        if initial_o is None and mx_o is not None:
            initial_o = float(mx_o)
        if mx_o is None and initial_o is not None:
            mx_o = float(initial_o)
        if min_o is None and initial_o is not None and mx_o is not None:
            min_o = min(float(initial_o), float(mx_o))

        initial = float(initial_o) if initial_o is not None else float("nan")
        mx = float(mx_o) if mx_o is not None else float("nan")
        min_t = float(min_o) if min_o is not None else float("nan")

        step = sf(("TemperatureStep", "step_temp_c", "Step", "delta_T", "INC"), 2.0)
        thr = sf(("FWHM_recovery_threshold_nm", "fwhm_recovery_nm", "RecoveryThreshold_nm", "FWHM_Recovery_nm"), 0.3)
        wait_ms = int(max(0, min(3_600_000, sf(("WaitTime_ms", "wait_time_ms", "WAIT TIME"), 0.0))))
        continuous_scan = sb(("ContinuousScan", "continuous_scan"), False)

        span = sf(("StabilitySpan_nm", "span_nm", "Span_nm", "narrow_span_nm", "Span"), 2.0)
        smpl = int(sf(("StabilitySampling", "sampling_points", "Sampling", "SMPL"), 1001))
        res = sf(("StabilityResolution_nm", "resolution_nm", "Resolution"), 0.05)

        deg_span = float(max(0.1, min(100.0, sf(("DegOfStability", "deg_of_stability", "DegreeOfStabilitySpan_C"), 5.0))))
        recovery_step_c = float(max(0.0, sf(("RecoveryStep_C", "recovery_step_C", "MinStabilitySpanAfterExceed_C"), 0.7)))
        recovery_steps_n = int(max(1, min(50, sf(("RecoverySteps", "recovery_steps", "Recovery_Steps"), 2.0))))
        smsr_corr_en = sb(
            (
                "SMSR_correction_enable",
                "EnableSMSR_correction",
                "smsr_correction_enable",
                "SMSRCorrection",
            ),
            False,
        )

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
            tl_ll_en, tl_ll, tl_ul_en, tl_ul = _row_bounds("Thorlabs")
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
            tl_ll_en = sb(("thorlabs_power_ll_enable", "ThorlabsPower_LL_enable"), False)
            tl_ll = sf(("thorlabs_power_ll_mw", "Thorlabs_LL_mW"), 0.0)
            tl_ul_en = sb(("thorlabs_power_ul_enable", "ThorlabsPower_UL_enable"), False)
            tl_ul = sf(("thorlabs_power_ul_mw", "Thorlabs_UL_mW"), 999999.0)

        return cls(
            initial_temp_c=float(initial),
            max_temp_c=float(mx),
            step_temp_c=float(max(0.01, step)),
            min_temp_c=float(min_t),
            wait_step_ms=wait_ms,
            continuous_scan=continuous_scan,
            fwhm_recovery_threshold_nm=float(max(1e-6, thr)),
            # §8: remeasure at same T if limits/recovery fail — up to MaxRetries total attempts (default 5, 1–20).
            max_retries_same_point=int(max(1, min(20, round(sf(("MaxRetries", "max_retries"), 5.0))))),
            tec_tolerance_c=float(max(0.05, sf(("TecTolerance_C", "tec_tolerance_c"), 0.5))),
            tec_settle_timeout_s=float(max(5.0, sf(("TecSettleTimeout_s", "tec_settle_timeout_s"), 300.0))),
            preamble_pause_s=float(max(0.0, sf(("PreamblePause_s", "preamble_pause_s"), 2.0))),
            ando_span_nm=float(max(0.01, span)),
            ando_sampling_points=int(max(11, min(20001, smpl))),
            ando_resolution_nm=float(max(1e-4, res)),
            analysis=str(first_in_dict(stab, ("Analysis", "analysis"), "") or first_in_dict(spec, ("Analysis", "analysis"), "") or "DFB-LD"),
            deg_span_c=deg_span,
            recovery_steps_n=recovery_steps_n,
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
            recovery_step_c=recovery_step_c,
            smsr_correction_enabled=smsr_corr_en,
            thorlabs_required=sb(("ThorlabsRequired", "require_thorlabs", "thorlabs_required"), False),
            thorlabs_ll_enabled=tl_ll_en,
            thorlabs_ll_mw=float(tl_ll),
            thorlabs_ul_enabled=tl_ul_en,
            thorlabs_ul_mw=float(tl_ul),
        )


def _temperature_stability_sweep_temps_error(p: TemperatureStabilityParameters) -> Optional[str]:
    """Fail if cold→hot bounds were not resolved from the recipe (no legacy 25/45 °C defaults)."""
    if (
        math.isfinite(p.initial_temp_c)
        and math.isfinite(p.max_temp_c)
        and math.isfinite(p.min_temp_c)
    ):
        return None
    return (
        "Temperature Stability: set InitialTemperature, MaxTemperature, and MinTemp (or enough to derive them) "
        "in the Temperature Stability recipe block; InitialTemperature may also come from GENERAL / SPECTRUM / LIV "
        "temperature when the TS block omits it."
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
    #: Raw OSA SMSR (dB) per point — used with ``peak_level_dbm`` when plotting SMSR − peak level.
    smsr_osa_raw_db: List[float] = field(default_factory=list)
    smsr_correction_enabled: bool = False
    peak_wavelength_nm: List[float] = field(default_factory=list)
    peak_level_dbm: List[float] = field(default_factory=list)
    thorlabs_power_mw: List[float] = field(default_factory=list)
    # Parallel to temperature_c: "c_h" = cold→hot sweep, "h_c" = hot→cold verification
    point_ramp_code: List[str] = field(default_factory=list)
    # Parallel to temperature_c: per-point status — "stable", "exceed", "retry", "hard_fail", "tl_fail"
    point_status: List[str] = field(default_factory=list)
    delta_wl_per_c: Optional[float] = None
    #: Every measurement attempt (including retries): JSON-safe rows for archive / analysis.
    raw_measurement_rows: List[Dict[str, Any]] = field(default_factory=list)


class TemperatureStabilityProcess:
    """Runs preamble + TEC sweeps; uses same Ando/Arroyo objects as the rest of the app."""

    def __init__(self) -> None:
        self._arroyo: Any = None
        self._ando: Any = None
        self._thorlabs: Any = None
        self._results_csv_fp: Any = None
        self._results_csv_path: Optional[Path] = None
        self._last_sweep_ando_debug: Dict[str, Any] = {}
        self._last_ando_analysis_name: Optional[str] = None

    def set_instruments(self, arroyo: Any = None, ando: Any = None, thorlabs: Any = None) -> None:
        self._arroyo = arroyo
        self._ando = ando
        self._thorlabs = thorlabs

    @staticmethod
    def _safe_results_filename_stem(name: str, max_len: int = 96) -> str:
        s = (name or "recipe").strip()
        s = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", s)
        s = s.strip(" .") or "recipe"
        return s[:max_len]

    def _close_results_csv(self) -> None:
        fp = self._results_csv_fp
        self._results_csv_fp = None
        self._results_csv_path = None
        if fp is not None:
            try:
                fp.close()
            except Exception:
                pass

    @contextmanager
    def _stability_results_csv_session(
        self, executor: Any, recipe_file_path: str, slot: int, step_label: str,
        smsr_correction: bool = False,
    ) -> Iterator[None]:
        self._start_results_csv(executor, recipe_file_path, slot, step_label or "", smsr_correction=smsr_correction)
        try:
            yield
        finally:
            self._close_results_csv()

    def _start_results_csv(self, executor: Any, recipe_file_path: str, slot: int, step_label: str,
                           smsr_correction: bool = False) -> None:
        self._close_results_csv()
        try:
            out_dir = get_results_root() / "stability_raw"
            out_dir.mkdir(parents=True, exist_ok=True)
            stem = self._safe_results_filename_stem(Path(str(recipe_file_path or "").strip()).stem)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            slot_s = str(int(slot))
            step_s = self._safe_results_filename_stem(str(step_label or "TS"), max_len=48)
            fname = "{}_TS{}_{}_{}.csv".format(stem, slot_s, step_s, ts)
            path = out_dir / fname
            fp = open(path, "w", newline="", encoding="utf-8")
            w = csv.writer(fp)
            w.writerow(
                [
                    "temperature_C",
                    "attempt",
                    "point_status",
                    "ramp",
                    "fwhm_nm",
                    "smsr_corrected_dB" if smsr_correction else "smsr_dB",
                    "peak_wavelength_nm",
                    "peak_level_dBm",
                    "thorlabs_mW",
                    "recipe_sweep_span_nm",
                    "fwhm_nm_after_SPWD_parse",
                    "fwhm_nm_from_ana_anar",
                    "span_echo_rejected",
                    "SPWD_reply",
                    "ANA_reply",
                    "ANAR_reply",
                ]
            )
            fp.flush()
            self._results_csv_fp = fp
            self._results_csv_path = path
            self._log(executor, "Stability: raw CSV (all attempts) → {}".format(path))
        except Exception as e:
            self._close_results_csv()
            self._log(executor, "Stability: could not open results CSV ({}).".format(e))

    @staticmethod
    def _csv_text_cell(s: Any, max_len: int = 500) -> str:
        if s is None:
            return ""
        t = str(s).replace("\r", " ").replace("\n", " ").strip()
        if len(t) > max_len:
            return t[: max_len - 3] + "..."
        return t

    def _append_results_csv_row(
        self,
        t_c: float,
        ramp: str,
        fwhm: float,
        smsr: float,
        peak_nm: float,
        peak_dbm: float,
        thorlabs_mw: float,
        ando_debug: Optional[Dict[str, Any]] = None,
        attempt: int = 1,
        point_status: str = "final",
    ) -> None:
        fp = self._results_csv_fp
        if fp is None:
            return
        try:
            w = csv.writer(fp)
            def _cell(x: float, fmt: str) -> str:
                try:
                    xf = float(x)
                except (TypeError, ValueError):
                    return ""
                if math.isnan(xf):
                    return ""
                return fmt.format(xf)

            ad = ando_debug if isinstance(ando_debug, dict) else {}
            fw_sp = ad.get("fwhm_nm_after_SPWD_parse")
            fw_ana = ad.get("fwhm_nm_from_ana_anar")
            sp_nm = ad.get("sweep_span_nm")

            def _opt_float_cell(v: Any, fmt: str) -> str:
                if v is None:
                    return ""
                try:
                    xf = float(v)
                except (TypeError, ValueError):
                    return ""
                if math.isnan(xf):
                    return ""
                return fmt.format(xf)

            w.writerow(
                [
                    _cell(t_c, "{:.6f}"),
                    str(int(max(1, attempt))),
                    self._csv_text_cell(str(point_status or "final"), 40),
                    str(ramp or ""),
                    _cell(fwhm, "{:.8f}"),
                    _cell(smsr, "{:.6f}"),
                    _cell(peak_nm, "{:.8f}"),
                    _cell(peak_dbm, "{:.6f}"),
                    _cell(thorlabs_mw, "{:.8f}"),
                    _opt_float_cell(sp_nm, "{:.6f}"),
                    _opt_float_cell(fw_sp, "{:.8f}"),
                    _opt_float_cell(fw_ana, "{:.8f}"),
                    "1" if ad.get("span_echo_rejected") else "0",
                    self._csv_text_cell(ad.get("SPWD_reply", "")),
                    self._csv_text_cell(ad.get("ANA_reply", "")),
                    self._csv_text_cell(ad.get("ANAR_reply", "")),
                ]
            )
            fp.flush()
        except Exception:
            pass

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
        peak_dbm: float,
        thorlabs_mw: float,
        ramp_code: str = "c_h",
        ando_debug: Optional[Dict[str, Any]] = None,
    ) -> None:
        sig = getattr(executor, "stability_live_point", None)
        if sig is not None and hasattr(sig, "emit"):
            sig.emit(
                float(t_c),
                float(fwhm),
                float(smsr),
                float(peak_nm),
                float(peak_dbm),
                float(thorlabs_mw),
                str(ramp_code or "c_h"),
            )
        ar = self._arroyo
        if ar is not None and getattr(ar, "is_connected", lambda: False)():
            try:
                snap = ar.read_gui_snapshot()
                if isinstance(snap, dict):
                    for sig_name in ("live_arroyo", "stability_live_arroyo"):
                        sig = getattr(executor, sig_name, None)
                        if sig is not None and hasattr(sig, "emit"):
                            sig.emit(snap)
            except Exception:
                pass

    def _log_measurement_attempt(
        self,
        raw_log: Optional[List[Dict[str, Any]]],
        p: TemperatureStabilityParameters,
        t_set: float,
        ramp_code: str,
        attempt_idx: int,
        point_status: str,
        fwhm_f: Optional[float],
        smsr_eval: Optional[float],
        smsr_f: Optional[float],
        pk_f: Optional[float],
        pk_lv_f: Optional[float],
        tl_mw: Optional[float],
        hard: List[str],
        fwhm_ok: bool,
        ando_debug: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Append one row to ``raw_log`` and to the optional raw CSV (every sweep attempt)."""
        row: Dict[str, Any] = {
            "temperature_set_C": float(t_set),
            "ramp": str(ramp_code),
            "attempt": int(attempt_idx + 1),
            "max_attempts": int(p.max_retries_same_point),
            "point_status": str(point_status),
            "fwhm_nm": fwhm_f,
            "smsr_dB": smsr_eval,
            "smsr_osa_raw_dB": smsr_f,
            "peak_wavelength_nm": pk_f,
            "peak_level_dBm": pk_lv_f,
            "thorlabs_mW": tl_mw,
            "hard_limit_messages": list(hard or []),
            "fwhm_within_recovery_threshold_nm": bool(fwhm_ok) if fwhm_f is not None else None,
            "smsr_correction_enabled": bool(p.smsr_correction_enabled),
        }
        if raw_log is not None:
            raw_log.append(row)
        ad = dict(ando_debug) if isinstance(ando_debug, dict) else {}
        self._append_results_csv_row(
            float(t_set),
            str(ramp_code or "c_h"),
            float(fwhm_f or 0.0),
            float(smsr_eval) if smsr_eval is not None else float("nan"),
            float(pk_f or 0.0),
            float(pk_lv_f) if pk_lv_f is not None else float("nan"),
            float(tl_mw) if tl_mw is not None else float("nan"),
            ando_debug=ad,
            attempt=int(attempt_idx + 1),
            point_status=str(point_status),
        )

    def _read_thorlabs_mw(self) -> Optional[float]:
        tl = self._thorlabs
        if tl is None or not getattr(tl, "is_connected", lambda: False)():
            return None
        rfn = getattr(tl, "read_power_mw", None)
        if not callable(rfn):
            return None
        try:
            v = rfn()
            return float(v) if v is not None else None
        except Exception:
            return None

    def _check_thorlabs_limits(self, p: TemperatureStabilityParameters, mw: Optional[float]) -> List[str]:
        if not p.thorlabs_ll_enabled and not p.thorlabs_ul_enabled:
            return []
        reasons: List[str] = []
        if mw is None:
            reasons.append("Thorlabs power not available (limits enabled).")
            return reasons
        if p.thorlabs_ll_enabled and float(mw) < float(p.thorlabs_ll_mw):
            reasons.append(
                "Thorlabs power {:.4f} mW below lower limit {:.4f} mW.".format(float(mw), float(p.thorlabs_ll_mw))
            )
        if p.thorlabs_ul_enabled and float(mw) > float(p.thorlabs_ul_mw):
            reasons.append(
                "Thorlabs power {:.4f} mW above upper limit {:.4f} mW.".format(float(mw), float(p.thorlabs_ul_mw))
            )
        return reasons

    def _emit_result(self, executor: Any, result: TemperatureStabilityProcessResult) -> None:
        sig = getattr(executor, "stability_test_result", None)
        if sig is not None and hasattr(sig, "emit"):
            sig.emit(result)

    def _apply_liv_arroyo_limits_from_recipe(self, recipe: Dict[str, Any], executor: Any) -> None:
        """
        After laser ON: set laser current limit from OPERATIONS.LIV.max_current_mA and optionally
        clamp setpoint into [min_current_mA, max_current_mA] when both are set.
        """
        op = recipe.get("OPERATIONS") or recipe.get("operations") or {}
        liv = op.get("LIV") or op.get("liv") or {}
        if not isinstance(liv, dict):
            return
        hi = _to_float(liv.get("max_current_mA"), 0)
        lo = _to_float(liv.get("min_current_mA"), 0)
        ar = self._arroyo
        if ar is None:
            return
        if hi > 0 and getattr(ar, "laser_set_current_limit", None):
            try:
                ar.laser_set_current_limit(max(hi, lo))
                self._log(executor, "Stability: Arroyo laser current limit (LIV max) = {:.1f} mA.".format(hi))
            except Exception:
                pass
        if lo > 0 and hi > lo and getattr(ar, "laser_set_current", None):
            try:
                rdc = getattr(ar, "laser_read_set_current", None) or getattr(ar, "laser_read_current", None)
                cur_f = None
                if callable(rdc):
                    v = rdc()
                    if v is not None:
                        cur_f = float(v)
                if cur_f is not None and (cur_f < lo or cur_f > hi):
                    new_c = max(lo, min(cur_f, hi))
                    ar.laser_set_current(new_c)
                    self._log(
                        executor,
                        "Stability: Laser current clamped to LIV range [{:.1f}, {:.1f}] mA (set {:.1f}).".format(
                            lo, hi, new_c
                        ),
                    )
            except Exception:
                pass

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

    def _apply_ando_initial_peak_find(
        self,
        center_nm: float,
        executor: Any,
    ) -> bool:
        """
        Phase 1: fixed Ando settings for peak-finding sweep.
        Span 2 nm, log scale 10, resolution 0.01, sensitivity mid, analysis DFB-LD.
        """
        a = self._ando
        if a is None or not getattr(a, "is_connected", lambda: False)():
            return False
        try:
            a.write_command("REMOTE")
        except Exception:
            pass
        a.set_sensitivity("MID")
        a.set_center_wavelength(center_nm)
        a.set_span(float(STABILITY_WIDE_SPAN_NM))
        a.set_resolution(0.01)
        a.set_log_scale(10.0)
        a.set_sampling_points(501)
        _analysis_command(a, "DFB-LD")
        self._log(
            executor,
            "Stability: Phase 1 — Ando CTR {:.3f} nm, span {:.1f} nm, RES 0.01, log 10, mid, DFB-LD.".format(
                center_nm, float(STABILITY_WIDE_SPAN_NM),
            ),
        )
        return True

    def _apply_ando_recipe_values(
        self,
        params: SpectrumProcessParameters,
        center_nm: float,
        executor: Any,
    ) -> bool:
        """
        Phase 2: load remaining recipe values to Ando (use discovered peak as center).
        """
        a = self._ando
        if a is None or not getattr(a, "is_connected", lambda: False)():
            return False
        sens = _recipe_sensitivity_to_ando(params.sensitivity)
        a.set_sensitivity(sens)
        a.set_center_wavelength(center_nm)
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
            "Stability: Phase 2 — Ando CTR {:.6f} nm (peak), span {:.3f} nm, RES {:.4f}, SMPL {}, {}.".format(
                center_nm, params.span_nm, params.resolution_nm,
                params.sampling_points, params.analysis,
            ),
        )
        return True

    def _apply_ts_ando_overrides(
        self,
        p: TemperatureStabilityParameters,
        executor: Any,
    ) -> None:
        """
        Override Ando span, resolution, sampling, and analysis with the TS-specific
        recipe values (StabilitySpan_nm, StabilityResolution_nm, StabilitySampling, Analysis).
        Called after _apply_ando_recipe_values which loads baselines from the Spectrum block.
        """
        a = self._ando
        if a is None or not getattr(a, "is_connected", lambda: False)():
            return
        a.set_span(p.ando_span_nm)
        a.set_resolution(p.ando_resolution_nm)
        a.set_sampling_points(p.ando_sampling_points)
        self._last_ando_analysis_name = None
        _analysis_command(a, p.analysis)
        self._last_ando_analysis_name = str(p.analysis or "").strip() or None
        self._log(
            executor,
            "Stability: TS overrides applied — span {:.3f} nm, RES {:.4f} nm, SMPL {}, analysis {}.".format(
                p.ando_span_nm, p.ando_resolution_nm, p.ando_sampling_points, p.analysis,
            ),
        )

    def _ensure_ando_analysis_mode(self, analysis_name: str) -> None:
        """
        Reduce instrument chatter: only send the analysis mode command when it changes.
        (AQ6317B keeps analysis mode latched across sweeps.)
        """
        a = self._ando
        if a is None:
            return
        an = str(analysis_name or "").strip()
        if not an:
            return
        if self._last_ando_analysis_name == an:
            return
        _analysis_command(a, an)
        self._last_ando_analysis_name = an

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

    def _apply_ando_offsets_from_recipe(self, recipe: Dict[str, Any], executor: Any, slot: int) -> None:
        """
        Apply TS Offset1_nm + Offset2_nm per RCP (process §2.2).

        Driver maps both to a single AQ6317 wavelength-axis shift (WLSFT/WLSHIFT): ``Offset1 + Offset2`` (nm).
        """
        a = self._ando
        if a is None or not getattr(a, "is_connected", lambda: False)():
            return
        off1, off2 = _recipe_ts_ando_offsets_nm(recipe, slot)
        o1 = float(off1) if off1 is not None else 0.0
        o2 = float(off2) if off2 is not None else 0.0
        if abs(o1) < 1e-18 and abs(o2) < 1e-18:
            return
        total = o1 + o2
        fn = getattr(a, "set_wavelength_shift_nm", None)
        if callable(fn):
            try:
                fn(float(total))
                self._log(
                    executor,
                    "Stability: Ando offsets → WLSFT = {:.6f} nm (Offset1 {:.6f} + Offset2 {:.6f}).".format(
                        total, o1, o2,
                    ),
                )
            except Exception:
                self._log(executor, "Stability: Ando wavelength shift (offsets) could not be applied.")

    def _one_sweep_metrics(
        self,
        executor: Any,
        analysis_name: str,
        stop_requested: Callable[[], bool],
        sampling_points: Optional[int] = None,
        continuous_scan: bool = False,
        sweep_span_nm: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        Fast Ando read (reference pattern):
          1. SGL + wait  (skip if continuous_scan)
          2. Execute analysis command (DFBAN / LEDAN / FPAN)
          3. ANA? → (fwhm, peak_wl, pk_lv, smsr) in one response
          4. Fallback: SPWD? for FWHM, SMSR? for SMSR, PKWL?/PKLV? for peaks
        """
        a = self._ando
        empty: Dict[str, Any] = {
            "pk_wl": None, "pk_lv": None, "fwhm": None, "smsr": None,
            "ana": None, "anar": None, "ando_debug": {},
        }
        if a is None or stop_requested():
            return empty

        # Step 1: trigger sweep if not continuous
        if not continuous_scan:
            a.single_sweep()
            wait_fn = getattr(a, "wait_sweep_done", None)
            if callable(wait_fn):
                try:
                    wait_fn(timeout_s=180.0, stop_requested=stop_requested)
                except TypeError:
                    wait_fn(timeout_s=180.0)
            else:
                t0 = time.time()
                while (time.time() - t0) < 180.0:
                    if stop_requested():
                        ss = getattr(a, "stop_sweep", None)
                        if callable(ss):
                            ss()
                        return empty
                    if getattr(a, "is_sweep_done", lambda: True)():
                        break
                    time.sleep(0.04)
            if stop_requested():
                return empty

        # Step 2: execute analysis (DFBAN) — must run AFTER sweep, BEFORE reading ANA?
        self._ensure_ando_analysis_mode(analysis_name)

        # Step 3: read ANA? — returns fwhm, peak_wl, pk_lv, smsr from one query
        ana = None
        qana = getattr(a, "query_analysis_ana", None)
        if callable(qana):
            try:
                ana = qana(analysis_name)
            except TypeError:
                ana = qana()

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

        # Step 4: SPWD? fallback for FWHM only when ANA? didn't provide it.
        # SMSR?/PKWL?/PKLV? return bogus "1" on this AQ6317B firmware — never use them.
        if fwhm is None:
            v = getattr(a, "query_spectral_width_nm", lambda: None)()
            if v is not None:
                try:
                    fwhm = float(v)
                except (TypeError, ValueError):
                    pass

        self._last_sweep_ando_debug = {
            "sweep_span_nm": sweep_span_nm,
            "ANA_reply": self._csv_text_cell(
                (ana or {}).get("raw", "") if isinstance(ana, dict) else "", 200
            ),
        }

        return {
            "pk_wl": pk_wl, "pk_lv": pk_lv, "fwhm": fwhm, "smsr": smsr,
            "ana": ana, "anar": None, "ando_debug": self._last_sweep_ando_debug,
        }

    @staticmethod
    def _any_hard_limit_enabled(p: TemperatureStabilityParameters) -> bool:
        return (
            p.fwhm_ll_enabled or p.fwhm_ul_enabled
            or p.smsr_ll_enabled or p.smsr_ul_enabled
            or p.peak_wl_ll_enabled or p.peak_wl_ul_enabled
            or p.peak_power_ll_enabled or p.peak_power_ul_enabled
        )

    def _check_hard_limits(
        self,
        p: TemperatureStabilityParameters,
        fwhm: Optional[float],
        smsr: Optional[float],
        peak_nm: Optional[float] = None,
        peak_dbm: Optional[float] = None,
    ) -> List[str]:
        if not self._any_hard_limit_enabled(p):
            return []
        reasons: List[str] = []
        if p.fwhm_ll_enabled or p.fwhm_ul_enabled:
            if fwhm is not None:
                if p.fwhm_ll_enabled and float(fwhm) < p.fwhm_ll_nm:
                    reasons.append("FWHM {:.4f} nm below lower limit {:.4f} nm.".format(float(fwhm), p.fwhm_ll_nm))
                if p.fwhm_ul_enabled and float(fwhm) > p.fwhm_ul_nm:
                    reasons.append("FWHM {:.4f} nm above upper limit {:.4f} nm.".format(float(fwhm), p.fwhm_ul_nm))
            else:
                reasons.append("FWHM not available (limits enabled).")
        if p.smsr_ll_enabled or p.smsr_ul_enabled:
            if smsr is not None:
                if p.smsr_ll_enabled and float(smsr) < p.smsr_ll_db:
                    reasons.append("SMSR {:.2f} dB below lower limit {:.2f} dB.".format(float(smsr), p.smsr_ll_db))
                if p.smsr_ul_enabled and float(smsr) > p.smsr_ul_db:
                    reasons.append("SMSR {:.2f} dB above upper limit {:.2f} dB.".format(float(smsr), p.smsr_ul_db))
            else:
                reasons.append("SMSR not available (limits enabled).")
        if p.peak_wl_ll_enabled or p.peak_wl_ul_enabled:
            if peak_nm is not None:
                if p.peak_wl_ll_enabled and float(peak_nm) < p.peak_wl_ll_nm:
                    reasons.append("Peak λ {:.4f} nm below lower limit {:.4f} nm.".format(float(peak_nm), p.peak_wl_ll_nm))
                if p.peak_wl_ul_enabled and float(peak_nm) > p.peak_wl_ul_nm:
                    reasons.append("Peak λ {:.4f} nm above upper limit {:.4f} nm.".format(float(peak_nm), p.peak_wl_ul_nm))
            else:
                reasons.append("Peak wavelength not available (limits enabled).")
        if p.peak_power_ll_enabled or p.peak_power_ul_enabled:
            if peak_dbm is not None:
                if p.peak_power_ll_enabled and float(peak_dbm) < p.peak_power_ll_dbm:
                    reasons.append("Peak level {:.2f} dBm below lower limit {:.2f} dBm.".format(float(peak_dbm), p.peak_power_ll_dbm))
                if p.peak_power_ul_enabled and float(peak_dbm) > p.peak_power_ul_dbm:
                    reasons.append("Peak level {:.2f} dBm above upper limit {:.2f} dBm.".format(float(peak_dbm), p.peak_power_ul_dbm))
            else:
                reasons.append("Peak level not available (limits enabled).")
        return reasons

    def _pk_level_for_smsr_correction(
        self, p: TemperatureStabilityParameters, pk_lv_f: Optional[float], smsr_f: Optional[float]
    ) -> Optional[float]:
        """When ANA? omits PK LVL, try ANAR? so SMSR − peak level (dBm) can be computed."""
        if pk_lv_f is not None:
            return pk_lv_f
        if not p.smsr_correction_enabled or smsr_f is None:
            return None
        a = self._ando
        if a is None or not getattr(a, "is_connected", lambda: False)():
            return None
        qanar = getattr(a, "query_analysis_anar", None)
        if not callable(qanar):
            return None
        try:
            ad = qanar(p.analysis)
        except TypeError:
            ad = qanar()
        if not isinstance(ad, dict):
            return None
        v = ad.get("PK_LVL_dBm")
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    def _measure_at_temperature(
        self,
        p: TemperatureStabilityParameters,
        executor: Any,
        t_set: float,
        stop_requested: Callable[[], bool],
        retry_collector: Optional[List[Dict[str, Any]]] = None,
        ramp_code: str = "c_h",
        raw_log: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[
        bool,
        Optional[float],
        Optional[float],
        Optional[float],
        Optional[float],
        bool,
        List[str],
        Optional[float],
        List[str],
        Optional[float],
    ]:
        """
        Per process §6–§8: one sweep reads FWHM, SMSR, peak λ, peak level; Thorlabs after sweep.

        **Pass** only if every enabled RCP check passes (§7): ANDO limits (FWHM/SMSR/peak λ/peak power when
        enabled), Thorlabs mW limits when enabled, **and** FWHM ≤ recovery threshold.

        If **any** of those fail (limit exceeded, missing value when limits are enabled, or FWHM above
        recovery threshold), **do not advance temperature**: remeasure at this same setpoint up to
        ``max_retries_same_point`` **total** attempts (default 5 from RCP ``MaxRetries``), stopping
        immediately on first pass. If all attempts fail, keep the last reading for logging/plot and return
        with ``exceed`` / failure reasons so the sweep can continue (§8).

        Returns (ok, fwhm, smsr, pk, pk_lv, exceed, hard_reasons, smsr_osa_raw_dB, tl_hard_reasons, thorlabs_mW).
        """
        fwhm_acc: Optional[float] = None
        smsr_acc: Optional[float] = None
        pk_acc: Optional[float] = None
        pk_lv_acc: Optional[float] = None
        smsr_raw_acc: Optional[float] = None
        last_hard: List[str] = []
        last_tl_hard: List[str] = []
        tl_mw_last: Optional[float] = None
        exceed = False

        def _empty_ret(
            ok: bool, msg: str
        ) -> Tuple[
            bool, None, None, None, None, bool, List[str], None, List[str], None,
        ]:
            return (ok, None, None, None, None, False, [msg], None, [], None)

        for attempt in range(p.max_retries_same_point):
            if stop_requested():
                return _empty_ret(False, "Stopped by user.")

            m = self._one_sweep_metrics(
                executor,
                p.analysis,
                stop_requested,
                p.ando_sampling_points,
                continuous_scan=p.continuous_scan,
                sweep_span_nm=float(p.ando_span_nm),
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

            pk_lv_f = self._pk_level_for_smsr_correction(p, pk_lv_f, smsr_f)

            smsr_eval: Optional[float] = smsr_f
            if p.smsr_correction_enabled and smsr_f is not None and pk_lv_f is not None:
                smsr_eval = float(smsr_f) - float(pk_lv_f)
                self._log(
                    executor,
                    "Stability: SMSR corrected {:.2f} dB  (raw {:.2f} \u2212 peak {:.2f} dBm)".format(
                        smsr_eval, float(smsr_f), float(pk_lv_f)
                    ),
                )

            if attempt == 0:
                self._log(
                    executor,
                    "Stability: T={:.2f} °C  up to {} measurement attempt(s) at this setpoint "
                    "(remeasure if RCP limits exceeded or FWHM above recovery threshold)…".format(
                        t_set, p.max_retries_same_point,
                    ),
                )

            hard = self._check_hard_limits(p, fwhm_f, smsr_eval, pk_f, pk_lv_f)
            tl_now = self._read_thorlabs_mw()
            tl_hard = self._check_thorlabs_limits(p, tl_now)
            fwhm_ok = fwhm_f is not None and fwhm_f <= p.fwhm_recovery_threshold_nm
            adbg = dict(self._last_sweep_ando_debug)

            fwhm_acc, smsr_acc, pk_acc, pk_lv_acc = fwhm_f, smsr_eval, pk_f, pk_lv_f
            smsr_raw_acc = smsr_f
            last_hard = hard
            last_tl_hard = tl_hard
            tl_mw_last = tl_now

            fail_parts: List[str] = []
            if hard:
                fail_parts.extend(hard)
            if tl_hard:
                fail_parts.extend(tl_hard)
            if not fwhm_ok:
                fail_parts.append(
                    "FWHM {:.4f} nm > recovery threshold {:.4f} nm".format(
                        fwhm_f or -1.0, p.fwhm_recovery_threshold_nm,
                    )
                )

            point_pass = (not hard) and (not tl_hard) and fwhm_ok

            if point_pass:
                exceed = False
                self._log_measurement_attempt(
                    raw_log, p, t_set, ramp_code, attempt, "pass",
                    fwhm_f, smsr_eval, smsr_f, pk_f, pk_lv_f, tl_now, hard, fwhm_ok, adbg,
                )
                self._log(
                    executor,
                    "Stability: T={:.2f} \u00b0C  attempt {}/{} \u2014 PASS.".format(
                        t_set, attempt + 1, p.max_retries_same_point,
                    ),
                )
                break

            will_retry = attempt + 1 < p.max_retries_same_point
            st_label = "retry" if will_retry else "fail_last"
            self._log_measurement_attempt(
                raw_log, p, t_set, ramp_code, attempt, st_label,
                fwhm_f, smsr_eval, smsr_f, pk_f, pk_lv_f, tl_now, hard, fwhm_ok, adbg,
            )

            if will_retry:
                if retry_collector is not None:
                    retry_collector.append(dict(
                        t=float(t_set), fwhm=float(fwhm_f or 0.0),
                        smsr=float(smsr_eval) if smsr_eval is not None else float("nan"),
                        smsr_raw=float(smsr_f) if smsr_f is not None else float("nan"),
                        pk=float(pk_f) if pk_f is not None else float("nan"),
                        pk_lv=float(pk_lv_f) if pk_lv_f is not None else float("nan"),
                        tl=float(tl_now) if tl_now is not None else float("nan"),
                        ramp=ramp_code, status="retry",
                    ))
                self._log(
                    executor,
                    "Stability: T={:.2f} \u00b0C  attempt {}/{} FAIL ({}) \u2014 remeasuring same temperature.".format(
                        t_set, attempt + 1, p.max_retries_same_point,
                        "; ".join(fail_parts),
                    ),
                )
                if _interruptible_sleep(float(STABILITY_RETRY_SETTLE_S), stop_requested):
                    return _empty_ret(False, "Stopped by user.")
                continue

            exceed = True
            self._log(
                executor,
                "Stability: T={:.2f} \u00b0C  all {} attempts failed ({}).".format(
                    t_set, p.max_retries_same_point, "; ".join(fail_parts),
                ),
            )
            break

        if fwhm_acc is None:
            return (
                False, None, None, None, None, False,
                ["FWHM missing at T={:.2f} \u00b0C.".format(t_set)],
                None, [], None,
            )

        return (
            True,
            fwhm_acc,
            smsr_acc,
            pk_acc,
            pk_lv_acc,
            exceed,
            last_hard if exceed else [],
            smsr_raw_acc,
            last_tl_hard if exceed else [],
            tl_mw_last,
        )

    def _verify_window_hot_to_cold(
        self,
        p: TemperatureStabilityParameters,
        executor: Any,
        t_low: float,
        t_high: float,
        set_temp: Any,
        stop_requested: Callable[[], bool],
        all_t: List[float],
        all_f: List[float],
        all_s: List[float],
        all_s_raw: List[float],
        all_pk: List[float],
        all_pk_lv: List[float],
        all_tl: List[float],
        all_ramp: List[str],
        all_status: Optional[List[str]] = None,
        flush_retries_fn: Optional[Callable[[List[Dict[str, Any]]], None]] = None,
        raw_log: Optional[List[Dict[str, Any]]] = None,
    ) -> bool:
        """Re-measure from t_high down to t_low; all points must be non-exceed (stable)."""
        path = _setpoints_descending(t_low, t_high, p.step_temp_c)
        self._log(
            executor,
            "Stability: hot\u2192cold verification \u2014 {} setpoints ({:.2f} \u2192 {:.2f} \u00b0C).".format(
                len(path), float(t_high), float(t_low)
            ),
        )
        for t_set in path:
            if stop_requested():
                return False
            if callable(set_temp):
                set_temp(t_set)
                time.sleep(0.15)
            ok_w, msg_w = self._wait_tec(executor, t_set, p.tec_tolerance_c, p.tec_settle_timeout_s, stop_requested)
            if not ok_w:
                self._log(executor, "Stability: verify down TEC failed: {}".format(msg_w))
                return False
            if p.wait_step_ms > 0:
                if _interruptible_sleep(min(120.0, p.wait_step_ms / 1000.0), stop_requested):
                    return False

            retries_hc: List[Dict[str, Any]] = []
            ok_m, fwhm_v, smsr_v, pk_v, pk_lv_v, exceed, hard, smsr_raw_v, tl_hard, tl_mw = self._measure_at_temperature(
                p, executor, t_set, stop_requested, retry_collector=retries_hc, ramp_code="h_c",
                raw_log=raw_log,
            )
            if flush_retries_fn is not None:
                flush_retries_fn(retries_hc)

            pt_status = "stable"
            if hard:
                pt_status = "hard_fail"
            elif tl_hard:
                pt_status = "tl_fail"
            elif not ok_m:
                pt_status = "hard_fail"
            elif exceed:
                pt_status = "exceed"

            all_t.append(float(t_set))
            all_f.append(float(fwhm_v or 0.0))
            all_s.append(float(smsr_v) if smsr_v is not None else float("nan"))
            all_s_raw.append(float(smsr_raw_v) if smsr_raw_v is not None else float("nan"))
            all_pk.append(float(pk_v) if pk_v is not None else float("nan"))
            all_pk_lv.append(float(pk_lv_v) if pk_lv_v is not None else float("nan"))
            all_tl.append(float(tl_mw) if tl_mw is not None else float("nan"))
            all_ramp.append("h_c")
            if all_status is not None:
                all_status.append(pt_status)
            self._emit_live(
                executor,
                float(t_set),
                float(fwhm_v or 0.0),
                float(smsr_v or 0.0),
                float(pk_v or 0.0),
                float(pk_lv_v) if pk_lv_v is not None else float("nan"),
                float(tl_mw) if tl_mw is not None else float("nan"),
                "h_c",
                ando_debug=dict(self._last_sweep_ando_debug),
            )

            if hard:
                self._log(executor, "Stability: verify down hard limit: {}".format(hard[0]))
                return False
            if tl_hard:
                if all_status is not None and all_status:
                    all_status[-1] = "tl_fail"
                self._log(executor, "Stability: verify down Thorlabs limit: {}".format(tl_hard[0]))
                return False
            if not ok_m:
                return False
            if exceed:
                self._log(
                    executor,
                    "Stability: hot\u2192cold verify failed at {:.2f} \u00b0C (stable measurement not achieved — see FWHM recovery / limits).".format(
                        t_set
                    ),
                )
                return False

        self._log(executor, "Stability: hot\u2192cold verification passed.")
        return True

    def _log_ts_recipe_audit(
        self, executor: Any, recipe: Dict[str, Any], p: TemperatureStabilityParameters, slot: int
    ) -> None:
        """Confirm which RCP block was parsed and the main sweep / Ando parameters (limits checked separately)."""
        blk = _get_block(recipe, slot)
        nkeys = len(blk) if isinstance(blk, dict) else 0
        self._log(
            executor,
            "Stability: RCP — using OPERATIONS['Temperature Stability {}'] ({} recipe keys). "
            "Initial T (Arroyo) {}; TEC sweep {:.2f} → {:.2f} °C, step {:.3f} °C, wait {} ms; "
            "Ando {:.3f} nm span, {} pts, {:.4f} nm res, {!r}; "
            "DegOfStability={:.2f} °C, RecoveryStep_C={:.2f}, RecoverySteps={}, MaxRetries={}, "
            "FWHM_recovery_threshold={:.4f} nm, ContinuousScan={}.".format(
                int(slot),
                nkeys,
                "{:.2f} °C".format(float(p.initial_temp_c))
                if math.isfinite(float(p.initial_temp_c))
                else "—",
                float(p.min_temp_c),
                float(p.max_temp_c),
                float(p.step_temp_c),
                int(p.wait_step_ms),
                float(p.ando_span_nm),
                int(p.ando_sampling_points),
                float(p.ando_resolution_nm),
                str(p.analysis),
                float(p.deg_span_c),
                float(p.recovery_step_c),
                int(p.recovery_steps_n),
                int(p.max_retries_same_point),
                float(p.fwhm_recovery_threshold_nm),
                bool(p.continuous_scan),
            ),
        )

    def run(
        self,
        recipe: Dict[str, Any],
        executor: Any,
        slot: int,
        stop_requested: Callable[[], bool],
        step_label: str = "",
        recipe_file_path: str = "",
    ) -> TemperatureStabilityProcessResult:
        if isinstance(recipe, dict):
            try:
                from operations.recipe_normalize import normalize_loaded_recipe

                normalize_loaded_recipe(recipe)
            except Exception:
                pass
        out = TemperatureStabilityProcessResult(slot=slot, step_label=step_label or "Temperature Stability {}".format(slot))
        p = TemperatureStabilityParameters.from_recipe_blocks(recipe, slot)
        ts_temp_err = _temperature_stability_sweep_temps_error(p)
        if ts_temp_err:
            out.fail_reasons.append(ts_temp_err)
            self._emit_result(executor, out)
            return out
        self._log_ts_recipe_audit(executor, recipe, p, slot)
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

        tl_inst = self._thorlabs
        if tl_inst is None or not getattr(tl_inst, "is_connected", lambda: False)():
            out.fail_reasons.append(
                "Thorlabs powermeter is not connected — connect it in the Connection tab (required for Temperature Stability)."
            )
            self._emit_result(executor, out)
            return out

        self._log(
            executor,
            "Stability: DegOfStability span = {:.2f} °C (required stable window), RecoveryStep_C = {:.2f} °C, "
            "RecoverySteps = {} (test fails after {} consecutive failed setpoints).".format(
                float(p.deg_span_c),
                float(p.recovery_step_c),
                int(p.recovery_steps_n),
                int(p.recovery_steps_n) + 1,
            ),
        )
        if p.smsr_correction_enabled:
            self._log(
                executor,
                "Stability: SMSR correction ON — SMSR for limits/plots/CSV = measured SMSR (dB) − peak level (dBm).",
            )
        if self._any_hard_limit_enabled(p) or p.thorlabs_ll_enabled or p.thorlabs_ul_enabled:
            parts: List[str] = []
            if p.fwhm_ll_enabled:
                parts.append("FWHM LL={:.4f}".format(p.fwhm_ll_nm))
            if p.fwhm_ul_enabled:
                parts.append("FWHM UL={:.4f}".format(p.fwhm_ul_nm))
            if p.smsr_ll_enabled:
                parts.append("SMSR LL={:.2f}".format(p.smsr_ll_db))
            if p.smsr_ul_enabled:
                parts.append("SMSR UL={:.2f}".format(p.smsr_ul_db))
            if p.peak_wl_ll_enabled:
                parts.append("WL LL={:.4f}".format(p.peak_wl_ll_nm))
            if p.peak_wl_ul_enabled:
                parts.append("WL UL={:.4f}".format(p.peak_wl_ul_nm))
            if p.peak_power_ll_enabled:
                parts.append("Power LL={:.2f}".format(p.peak_power_ll_dbm))
            if p.peak_power_ul_enabled:
                parts.append("Power UL={:.2f}".format(p.peak_power_ul_dbm))
            if p.thorlabs_ll_enabled:
                parts.append("Thorlabs LL={:.4f}".format(p.thorlabs_ll_mw))
            if p.thorlabs_ul_enabled:
                parts.append("Thorlabs UL={:.4f}".format(p.thorlabs_ul_mw))
            self._log(executor, "Stability: ACTIVE hard limits: {}".format(", ".join(parts)))
        else:
            self._log(executor, "Stability: No hard limits enabled — only FWHM recovery threshold is active.")

        recipe_dict = recipe if isinstance(recipe, dict) else {}
        recipe_laser = _recipe_with_ts_laser_overrides(recipe_dict, slot)

        # §2.1 Configure Arroyo (NO outputs yet): Max temp limit, Initial temp, Set current.
        try:
            fn_rm = getattr(ar, "set_remote_mode", None)
            if callable(fn_rm):
                fn_rm()
                time.sleep(0.1)
        except Exception:
            pass
        try:
            fn_thi = getattr(ar, "set_THI_limit", None)
            if callable(fn_thi) and math.isfinite(float(p.max_temp_c)):
                fn_thi(float(p.max_temp_c))
                self._log(executor, "Stability: Arroyo max temperature (THI) = {:.2f} °C.".format(float(p.max_temp_c)))
        except Exception:
            pass
        try:
            # Initial temperature from TS (merged into SPECTRUM by _recipe_with_ts_laser_overrides)
            op = recipe_laser.get("OPERATIONS") if isinstance(recipe_laser, dict) else {}
            spec = (op.get("SPECTRUM") if isinstance(op, dict) else {}) or {}
            t_init = _to_float(spec.get("Temperature", spec.get("temperature", "")), float("nan"))
            set_temp_init = getattr(ar, "set_temp", None) or getattr(ar, "tec_set_temp", None)
            if callable(set_temp_init) and math.isfinite(float(t_init)):
                set_temp_init(float(t_init))
                time.sleep(0.2)
                self._log(executor, "Stability: Arroyo initial temperature = {:.2f} °C.".format(float(t_init)))
        except Exception:
            pass
        try:
            op = recipe_laser.get("OPERATIONS") if isinstance(recipe_laser, dict) else {}
            spec = (op.get("SPECTRUM") if isinstance(op, dict) else {}) or {}
            cur = _to_float(spec.get("Current", spec.get("current", "")), 0.0)
            lim = _to_float(spec.get("MaxCurrent", spec.get("max_current_mA", cur)), cur)
            if cur > 0:
                fn_lim = getattr(ar, "laser_set_current_limit", None)
                if callable(fn_lim):
                    fn_lim(float(lim))
                    time.sleep(0.1)
                fn_cur = getattr(ar, "laser_set_current", None)
                if callable(fn_cur):
                    fn_cur(float(cur))
                    time.sleep(0.15)
                self._log(executor, "Stability: Arroyo set current = {:.0f} mA.".format(float(cur)))
        except Exception:
            pass
        _arm_laser_fn = getattr(executor, "notify_laser_monitor_armed", None)
        if callable(_arm_laser_fn):
            try:
                _arm_laser_fn(True)
            except Exception:
                pass
        self._apply_liv_arroyo_limits_from_recipe(recipe_dict, executor)

        set_temp = getattr(ar, "set_temp", None)

        # §3 Turn ON TEC then Laser **before** ANDO sweeps: spectrum needs optical power; TEC must be ON
        # so the controller actively regulates toward the programmed setpoint (Initial temperature).
        # (Recipe order lists ANDO before §3; instrument programming can precede outputs, but **scans** require them.)
        set_out = getattr(ar, "set_output", None)
        if callable(set_out):
            try:
                set_out(1)
                time.sleep(0.28)
                self._log(executor, "Stability: TEC output ON (regulation active toward initial setpoint).")
            except Exception:
                pass
        try:
            arroyo_laser_on_safe(ar)
            time.sleep(0.4)
            self._log(executor, "Stability: Laser output ON (required for ANDO / Thorlabs).")
        except Exception:
            pass

        # §2.2 Configure ANDO + spectral preamble (with light and TEC regulating).
        # Phase 1: fixed peak-find sweep (span 2, res 0.01, mid, DFB-LD)
        if not self._apply_ando_initial_peak_find(spec_params.center_nm, executor):
            out.fail_reasons.append("Failed to apply Ando settings for phase 1 peak-find sweep.")
            self._emit_result(executor, out)
            return out

        m0 = self._one_sweep_metrics(
            executor, "DFB-LD", stop_requested,
            continuous_scan=False, sweep_span_nm=float(STABILITY_WIDE_SPAN_NM),
        )
        if stop_requested():
            out.fail_reasons.append("Stopped during preamble sweep.")
            self._emit_result(executor, out)
            return out
        peak0 = m0.get("pk_wl")
        if peak0 is None:
            out.fail_reasons.append("Phase 1 sweep: could not read peak wavelength.")
            self._emit_result(executor, out)
            return out
        center_nm = float(peak0)
        self._log(
            executor,
            "Stability: Peak = {:.6f} nm — set as Ando center.".format(center_nm),
        )

        # Phase 2: load baseline Ando settings from Spectrum block (sensitivity, ref level, log scale),
        # then override span/resolution/sampling with TS-specific values.
        if not self._apply_ando_recipe_values(spec_params, center_nm, executor):
            out.fail_reasons.append("Failed to apply recipe Ando settings.")
            self._emit_result(executor, out)
            return out
        self._apply_ts_ando_overrides(p, executor)
        self._apply_auto_ref_ando(recipe_dict, executor, slot)
        self._apply_ando_offsets_from_recipe(recipe_dict, executor, slot)

        self._log(executor, "Stability: Warm-up sweep with final Ando settings (result discarded).")
        self._one_sweep_metrics(
            executor, p.analysis, stop_requested,
            continuous_scan=False,
        )

        if p.continuous_scan:
            rpt = getattr(self._ando, "repeat_sweep", None)
            if callable(rpt):
                try:
                    rpt()
                    self._log(executor, "Stability: Ando repeat sweep (RPT) started — measurements use continuous mode (no SGL each point).")
                    time.sleep(0.35)
                except Exception:
                    self._log(executor, "Stability: Could not start repeat sweep — falling back to single sweep per point.")

        # §4 Move to starting temperature (Min): outputs already ON — ramp setpoint and settle.
        if callable(set_temp):
            set_temp(p.min_temp_c)
            time.sleep(0.2)
        ok_tec, msg_tec = self._wait_tec(executor, p.min_temp_c, p.tec_tolerance_c, p.tec_settle_timeout_s, stop_requested)
        if not ok_tec:
            out.fail_reasons.append(msg_tec or "TEC preamble failed.")
            self._emit_result(executor, out)
            return out
        # Optional extra wait after reaching Min (RCP WaitTime_ms); fallback to PreamblePause_s when wait is 0.
        wait_after_min_s = min(120.0, p.wait_step_ms / 1000.0) if p.wait_step_ms > 0 else float(p.preamble_pause_s)
        if wait_after_min_s > 0:
            self._log(executor, "Stability: post–min-temp wait {:.2f} s (RCP).".format(wait_after_min_s))
            if _interruptible_sleep(wait_after_min_s, stop_requested):
                out.fail_reasons.append("Stopped by user during wait after min temperature.")
                self._emit_result(executor, out)
                return out

        with self._stability_results_csv_session(executor, recipe_file_path, slot, step_label,
                                                    smsr_correction=bool(p.smsr_correction_enabled)):
            t0 = float(min(p.min_temp_c, p.max_temp_c))
            t1 = float(max(p.min_temp_c, p.max_temp_c))
            temps_ch: List[float] = _setpoints_inclusive(t0, t1, p.step_temp_c)
            self._log(
                executor,
                "Stability: cold→hot search — {} setpoints (Min {:.2f} → Max {:.2f} °C).".format(
                    len(temps_ch), t0, t1,
                ),
            )
    
            all_t: List[float] = []
            all_f: List[float] = []
            all_s: List[float] = []
            all_s_raw: List[float] = []
            all_pk: List[float] = []
            all_pk_lv: List[float] = []
            all_tl: List[float] = []
            all_ramp: List[str] = []
            all_status: List[str] = []

            def _flush_retries(retries: List[Dict[str, Any]]) -> None:
                for rd in retries:
                    all_t.append(rd["t"])
                    all_f.append(rd["fwhm"])
                    all_s.append(rd["smsr"])
                    all_s_raw.append(rd["smsr_raw"])
                    all_pk.append(rd["pk"])
                    all_pk_lv.append(rd["pk_lv"])
                    all_tl.append(rd["tl"])
                    all_ramp.append(rd["ramp"])
                    all_status.append(rd["status"])

            stable_flags: List[bool] = []
            last_fail_temp_c: Optional[float] = None
            consec_failed_setpoints = 0
            rejected_windows: Set[Tuple[int, int]] = set()
            raw_rows = out.raw_measurement_rows
    
            passed = False
            idx = 0
            while idx < len(temps_ch):
                if stop_requested():
                    out.fail_reasons.append("Stopped by user.")
                    break
                t_set = temps_ch[idx]
                if callable(set_temp):
                    set_temp(t_set)
                    time.sleep(0.15)
                ok_w, msg_w = self._wait_tec(executor, t_set, p.tec_tolerance_c, p.tec_settle_timeout_s, stop_requested)
                if not ok_w:
                    out.fail_reasons.append(msg_w)
                    break
                if p.wait_step_ms > 0:
                    if _interruptible_sleep(min(120.0, p.wait_step_ms / 1000.0), stop_requested):
                        out.fail_reasons.append("Stopped by user.")
                        break
    
                retries: List[Dict[str, Any]] = []
                ok_m, fwhm_acc, smsr_acc, pk_acc, pk_lv_acc, exceed, hard, smsr_raw_acc, tl_hard, tl_mw = self._measure_at_temperature(
                    p, executor, t_set, stop_requested, retry_collector=retries, ramp_code="c_h",
                    raw_log=raw_rows,
                )
                _flush_retries(retries)

                if not ok_m:
                    all_t.append(float(t_set))
                    all_f.append(float(fwhm_acc or 0.0))
                    all_s.append(float(smsr_acc) if smsr_acc is not None else float("nan"))
                    all_s_raw.append(float(smsr_raw_acc) if smsr_raw_acc is not None else float("nan"))
                    all_pk.append(float(pk_acc) if pk_acc is not None else float("nan"))
                    all_pk_lv.append(float(pk_lv_acc) if pk_lv_acc is not None else float("nan"))
                    all_tl.append(float(tl_mw) if tl_mw is not None else float("nan"))
                    all_ramp.append("c_h")
                    all_status.append("hard_fail")
                    self._emit_live(
                        executor, float(t_set),
                        float(fwhm_acc or 0.0), float(smsr_acc or 0.0),
                        float(pk_acc or 0.0),
                        float(pk_lv_acc) if pk_lv_acc is not None else float("nan"),
                        float(tl_mw) if tl_mw is not None else float("nan"),
                        "c_h", ando_debug=dict(self._last_sweep_ando_debug),
                    )
                    out.fail_reasons.append("Measurement failed at T={:.2f} \u00b0C.".format(t_set))
                    break

                pt_status = "stable"
                if hard:
                    pt_status = "hard_fail"
                elif tl_hard:
                    pt_status = "tl_fail"
                elif exceed:
                    pt_status = "exceed"

                is_stable = not exceed and not hard and not tl_hard
                hit_recovery_abort = False
                if not is_stable:
                    if last_fail_temp_c is not None and float(p.recovery_step_c) > 1e-12:
                        gap = float(t_set) - float(last_fail_temp_c)
                        if gap + 1e-9 < float(p.recovery_step_c):
                            if stable_flags:
                                stable_flags[:] = [False] * len(stable_flags)
                            self._log(
                                executor,
                                "Stability: fails at {:.2f} °C and {:.2f} °C only {:.3f} °C apart "
                                "(< RecoveryStep_C {:.2f} °C) — resetting stability window tracking.".format(
                                    float(last_fail_temp_c), float(t_set), gap, float(p.recovery_step_c),
                                ),
                            )
                    last_fail_temp_c = float(t_set)
                    consec_failed_setpoints += 1
                    if consec_failed_setpoints > int(p.recovery_steps_n):
                        out.fail_reasons.append(
                            "Stopped: {} consecutive failed setpoints (RecoverySteps={}: test fails after {} in a row).".format(
                                consec_failed_setpoints,
                                int(p.recovery_steps_n),
                                int(p.recovery_steps_n) + 1,
                            )
                        )
                        hit_recovery_abort = True
                else:
                    consec_failed_setpoints = 0

                all_t.append(float(t_set))
                all_f.append(float(fwhm_acc or 0.0))
                all_s.append(float(smsr_acc) if smsr_acc is not None else float("nan"))
                all_s_raw.append(float(smsr_raw_acc) if smsr_raw_acc is not None else float("nan"))
                all_pk.append(float(pk_acc) if pk_acc is not None else float("nan"))
                all_pk_lv.append(float(pk_lv_acc) if pk_lv_acc is not None else float("nan"))
                all_tl.append(float(tl_mw) if tl_mw is not None else float("nan"))
                all_ramp.append("c_h")
                all_status.append(pt_status)
                self._emit_live(
                    executor,
                    float(t_set),
                    float(fwhm_acc or 0.0),
                    float(smsr_acc or 0.0),
                    float(pk_acc or 0.0),
                    float(pk_lv_acc) if pk_lv_acc is not None else float("nan"),
                    float(tl_mw) if tl_mw is not None else float("nan"),
                    "c_h",
                    ando_debug=dict(self._last_sweep_ando_debug),
                )
    
                stable_flags.append(is_stable)

                if hit_recovery_abort:
                    break
    
                temps_prefix = temps_ch[: idx + 1]
                win = _find_window_ending_at(stable_flags, temps_prefix, float(p.deg_span_c), idx)
                if win is not None:
                    i0, j0 = win
                    if (i0, j0) not in rejected_windows:
                        t_low = float(temps_ch[i0])
                        t_high = float(temps_ch[j0])
                        self._log(
                            executor,
                            "Stability: qualifying window {:.2f}–{:.2f} °C (span {:.2f} °C) — hot→cold verify.".format(
                                t_low, t_high, t_high - t_low
                            ),
                        )
                        verify_ok = self._verify_window_hot_to_cold(
                            p,
                            executor,
                            t_low,
                            t_high,
                            set_temp,
                            stop_requested,
                            all_t,
                            all_f,
                            all_s,
                            all_s_raw,
                            all_pk,
                            all_pk_lv,
                            all_tl,
                            all_ramp,
                            all_status=all_status,
                            flush_retries_fn=_flush_retries,
                            raw_log=raw_rows,
                        )
                        if callable(set_temp):
                            self._log(
                                executor,
                                "Stability: returning TEC to min temperature {:.2f} °C after hot→cold sweep.".format(
                                    p.min_temp_c
                                ),
                            )
                            set_temp(p.min_temp_c)
                            time.sleep(0.15)
                            self._wait_tec(
                                executor, p.min_temp_c, p.tec_tolerance_c,
                                p.tec_settle_timeout_s, stop_requested,
                            )
                        if verify_ok:
                            passed = True
                            break
                        self._log(
                            executor,
                            "Stability: verification failed — resuming upward from next setpoint after {:.2f} °C.".format(
                                t_high
                            ),
                        )
                        rejected_windows.add((i0, j0))
                        for _k in range(len(stable_flags)):
                            stable_flags[_k] = False
                        last_fail_temp_c = None
                        consec_failed_setpoints = 0
                        idx = j0 + 1
                        continue
    
                idx += 1
    
            if not passed and not out.fail_reasons:
                rest = float(t1) - float(t0)
                if rest + 1e-9 < float(p.deg_span_c):
                    out.fail_reasons.append(
                        "Sweep range {:.2f} °C is smaller than required DegOfStability span {:.2f} °C.".format(
                            rest, float(p.deg_span_c)
                        )
                    )
                else:
                    out.fail_reasons.append(
                        "No qualifying stable span ≥ {:.2f} °C with successful hot→cold verification before end of sweep.".format(
                            float(p.deg_span_c)
                        )
                    )

            out.temperature_c = all_t
            out.fwhm_nm = all_f
            out.smsr_db = all_s
            out.smsr_osa_raw_db = all_s_raw
            out.smsr_correction_enabled = bool(p.smsr_correction_enabled)
            out.peak_wavelength_nm = all_pk
            out.peak_level_dbm = all_pk_lv
            out.thorlabs_power_mw = all_tl
            out.point_ramp_code = all_ramp
            out.point_status = all_status

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

        out.passed = bool(passed) and len(out.fail_reasons) == 0

        if callable(set_temp):
            try:
                self._log(
                    executor,
                    "Stability: setting TEC to min temperature {:.2f} °C at end of test.".format(p.min_temp_c),
                )
                set_temp(p.min_temp_c)
                time.sleep(0.15)
                self._wait_tec(executor, p.min_temp_c, p.tec_tolerance_c, p.tec_settle_timeout_s, stop_requested)
            except Exception:
                pass

        self._emit_result(executor, out)
        return out
