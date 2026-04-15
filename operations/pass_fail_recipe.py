"""
Evaluate PASS_FAIL_CRITERIA from recipe JSON against LIV / PER results.

Recipe limits use LL (lower level) and UL (upper level): measured value must satisfy
LL <= value <= UL when that bound is set. Nested form per metric::

    "LIV": {
        "IT": {"ll": "50", "ul": "200", "enable": true},
        "L @ Ir": {"ll": "10", "ul": "500", "enable": true},
        ...
    }

Legacy flat keys (min_*/max_*) remain supported as LL/UL equivalents.
Mutates result.fail_reasons in place; callers set passed from fail_reasons.
"""
from __future__ import annotations

import math
from typing import Any, Dict, Optional, Tuple


def _pfc_section(recipe: Optional[Dict[str, Any]], key: str) -> Dict[str, Any]:
    if not recipe or not isinstance(recipe, dict):
        return {}
    pfc = recipe.get("PASS_FAIL_CRITERIA") or recipe.get("pass_fail_criteria") or {}
    if not isinstance(pfc, dict):
        return {}
    sec = pfc.get(key) or pfc.get(key.upper()) or pfc.get(key.lower())
    return sec if isinstance(sec, dict) else {}


def _f(d: Dict[str, Any], *names: str) -> Optional[float]:
    for k in names:
        if k in d:
            try:
                v = d[k]
                if v is None or v == "":
                    continue
                return float(v)
            except (TypeError, ValueError):
                return None
    return None


def _is_finite(x: Any) -> bool:
    try:
        v = float(x)
        return math.isfinite(v)
    except (TypeError, ValueError):
        return False


def _extract_ll_ul(
    liv: Dict[str, Any],
    nested_keys: Tuple[str, ...],
    flat_ll_names: Tuple[str, ...],
    flat_ul_names: Tuple[str, ...],
) -> Tuple[Optional[float], Optional[float], bool]:
    """
    Return (ll, ul, active) where active means this metric's limits should be checked.
    If a nested dict has enable=False, active is False.
    """
    for nk in nested_keys:
        sub = liv.get(nk)
        if isinstance(sub, dict):
            ll = _f(sub, "ll", "LL", "min", "Min", "lower", "Lower")
            ul = _f(sub, "ul", "UL", "max", "Max", "upper", "Upper")
            en = sub.get("enable", sub.get("Enable", True))
            if not bool(en):
                return None, None, False
            if ll is None and ul is None:
                return None, None, False
            return ll, ul, True

    ll = _f(liv, *flat_ll_names)
    ul = _f(liv, *flat_ul_names)
    if ll is None and ul is None:
        return None, None, False
    return ll, ul, True


def _append_limit_reason(
    result: Any,
    label: str,
    measured: float,
    unit: str,
    ll: Optional[float],
    ul: Optional[float],
) -> None:
    """Append one clear reason using LL / UL wording."""
    if ll is not None and measured < float(ll):
        result.fail_reasons.append(
            "LIV: {}: measured {:.6g} {} is below LL ({:.6g}).".format(
                label,
                float(measured),
                unit,
                float(ll),
            )
        )
        return
    if ul is not None and measured > float(ul):
        result.fail_reasons.append(
            "LIV: {}: measured {:.6g} {} is above UL ({:.6g}).".format(
                label,
                float(measured),
                unit,
                float(ul),
            )
        )


def apply_liv_pass_fail_criteria(recipe: Optional[Dict[str, Any]], result: Any) -> None:
    """Append to result.fail_reasons when PASS_FAIL_CRITERIA.LIV LL/UL are violated."""
    liv = _pfc_section(recipe, "LIV")
    if not liv:
        return

    def check(
        value: Any,
        nested: Tuple[str, ...],
        flat_min: Tuple[str, ...],
        flat_max: Tuple[str, ...],
        label: str,
        unit: str,
    ) -> None:
        ll, ul, active = _extract_ll_ul(liv, nested, flat_min, flat_max)
        if not active:
            return
        if not _is_finite(value):
            result.fail_reasons.append(
                "LIV: {}: measured value not available; cannot verify LL/UL.".format(label)
            )
            return
        mv = float(value)
        _append_limit_reason(result, label, mv, unit, ll, ul)

    tc = getattr(result, "threshold_current", None)
    check(
        tc,
        ("IT", "Ith", "threshold_current_mA"),
        ("min_threshold_mA", "MinThreshold_mA"),
        ("max_threshold_mA", "MaxThreshold_mA"),
        "IT (threshold current)",
        "mA",
    )

    se = getattr(result, "slope_efficiency", None)
    check(
        se,
        ("SE1", "SE", "slope_efficiency"),
        ("min_slope_efficiency", "MinSlopeEfficiency"),
        ("max_slope_efficiency", "MaxSlopeEfficiency"),
        "SE1 (slope efficiency)",
        "mW/mA",
    )

    par = getattr(result, "power_at_rated_current", None)
    check(
        par,
        ("L @ Ir", "L_at_Ir", "power_at_rated_mW", "P_at_Ir"),
        ("min_power_at_rated_mW", "MinPowerAtRated_mW"),
        ("max_power_at_rated_mW", "MaxPowerAtRated_mW"),
        "L @ Ir (power at rated current)",
        "mW",
    )

    ic_lp = getattr(result, "current_at_rated_power", None)
    check(
        ic_lp,
        ("I @ Lr", "I_at_Lr", "current_at_rated_mA"),
        ("min_current_at_rated_mA", "MinCurrentAtRated_mA"),
        ("max_current_at_rated_mA", "MaxCurrentAtRated_mA"),
        "I @ Lr (current at rated power)",
        "mA",
    )

    v_ir = getattr(result, "voltage_at_rated_current_V", None)
    check(
        v_ir,
        ("V @ Ir", "V_at_Ir", "voltage_at_Ir"),
        ("min_voltage_at_Ir_V", "MinVoltageAtIr_V"),
        ("max_voltage_at_Ir_V", "MaxVoltageAtIr_V"),
        "V @ Ir (voltage at rated current)",
        "V",
    )

    v_lr = getattr(result, "voltage_at_rated_power_V", None)
    check(
        v_lr,
        ("V @ Lr", "V_at_Lr", "voltage_at_Lr"),
        ("min_voltage_at_Lr_V", "MinVoltageAtLr_V"),
        ("max_voltage_at_Lr_V", "MaxVoltageAtLr_V"),
        "V @ Lr (voltage at rated power)",
        "V",
    )

    pd_ir = getattr(result, "pd_at_rated_current", None)
    check(
        pd_ir,
        ("PD @ Ir", "PD_at_Ir", "pd_at_Ir"),
        ("min_pd_at_Ir", "MinPDAtIr"),
        ("max_pd_at_Ir", "MaxPDAtIr"),
        "PD @ Ir (monitor diode at rated current)",
        "(raw)",
    )

    fp = getattr(result, "final_power", None)
    check(
        fp,
        ("Final Gentec", "final_power", "Gentec_final"),
        ("min_final_power_mW", "MinFinalPower_mW"),
        ("max_final_power_mW", "MaxFinalPower_mW"),
        "Final Gentec power (after sweep / calibration)",
        "mW",
    )


def apply_per_pass_fail_criteria(recipe: Optional[Dict[str, Any]], result: Any, params: Any) -> None:
    """
    Append to result.fail_reasons for PASS_FAIL_CRITERIA.PER using LL/UL semantics.
    min_PER_dB / ll act as lower limit; max_PER_dB / ul as upper limit.
    """
    per_pfc = _pfc_section(recipe, "PER")

    ll_per = _f(per_pfc, "ll", "LL", "min_PER_dB", "MinPER_dB") if per_pfc else None
    ul_per = _f(per_pfc, "ul", "UL", "max_PER_dB", "MaxPER_dB") if per_pfc else None
    _per_sub = (per_pfc.get("PER_dB") or per_pfc.get("per_db")) if per_pfc else None
    if per_pfc and isinstance(_per_sub, dict):
        sub = _per_sub
        if not bool(sub.get("enable", sub.get("Enable", True))):
            ll_per, ul_per = None, None
        else:
            ll = _f(sub, "ll", "LL")
            ul = _f(sub, "ul", "UL")
            if ll is not None:
                ll_per = ll
            if ul is not None:
                ul_per = ul

    min_db = float(getattr(params, "min_per_db", 0.0) or 0.0)
    if ll_per is None and min_db > 0:
        ll_per = min_db

    per_db = float(getattr(result, "per_db", 0.0) or 0.0)

    if ll_per is not None and per_db < float(ll_per):
        result.fail_reasons.append(
            "PER: measured PER {:.3f} dB is below LL ({:.3f} dB).".format(per_db, float(ll_per))
        )
    if ul_per is not None and per_db > float(ul_per):
        result.fail_reasons.append(
            "PER: measured PER {:.3f} dB is above UL ({:.3f} dB).".format(per_db, float(ul_per))
        )

    if not per_pfc:
        return

    mxp = _f(per_pfc, "min_max_power_mW", "MinMaxPower_mW")
    maxp = float(getattr(result, "max_power", 0.0) or 0.0)
    if mxp is not None and maxp < mxp:
        result.fail_reasons.append(
            "PER: max Thorlabs power {:.6g} mW is below LL ({:.6g} mW).".format(maxp, mxp)
        )

    mnp = _f(per_pfc, "max_min_power_mW", "MaxMinPower_mW")
    minp = float(getattr(result, "min_power", 0.0) or 0.0)
    if mnp is not None and minp > mnp:
        result.fail_reasons.append(
            "PER: min Thorlabs power {:.6g} mW is above UL ({:.6g} mW).".format(minp, mnp)
        )
