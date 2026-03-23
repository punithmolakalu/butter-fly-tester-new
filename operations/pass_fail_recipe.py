"""
Evaluate PASS_FAIL_CRITERIA from recipe JSON against LIV / PER results.
Mutates result.fail_reasons in place; does not set passed (callers compute passed from fail_reasons).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


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
                return float(d[k])
            except (TypeError, ValueError):
                return None
    return None


def apply_liv_pass_fail_criteria(recipe: Optional[Dict[str, Any]], result: Any) -> None:
    """Append to result.fail_reasons if PASS_FAIL_CRITERIA.LIV limits are crossed."""
    liv = _pfc_section(recipe, "LIV")
    if not liv:
        return
    tc = getattr(result, "threshold_current", None)
    se = getattr(result, "slope_efficiency", None)
    par = getattr(result, "power_at_rated_current", None)
    fp = getattr(result, "final_power", None)

    mn = _f(liv, "min_threshold_mA", "MinThreshold_mA")
    mx = _f(liv, "max_threshold_mA", "MaxThreshold_mA")
    if tc is not None and mn is not None and tc < mn:
        result.fail_reasons.append(
            "LIV: threshold current {:.4g} mA below PASS_FAIL limit {:.4g} mA.".format(float(tc), mn)
        )
    if tc is not None and mx is not None and tc > mx:
        result.fail_reasons.append(
            "LIV: threshold current {:.4g} mA above PASS_FAIL limit {:.4g} mA.".format(float(tc), mx)
        )

    smin = _f(liv, "min_slope_efficiency", "MinSlopeEfficiency")
    smax = _f(liv, "max_slope_efficiency", "MaxSlopeEfficiency")
    if se is not None and smin is not None and float(se) < smin:
        result.fail_reasons.append(
            "LIV: slope efficiency {:.6g} below PASS_FAIL limit {:.6g} (mW/mA).".format(float(se), smin)
        )
    if se is not None and smax is not None and float(se) > smax:
        result.fail_reasons.append(
            "LIV: slope efficiency {:.6g} above PASS_FAIL limit {:.6g} (mW/mA).".format(float(se), smax)
        )

    pmin = _f(liv, "min_power_at_rated_mW", "MinPowerAtRated_mW")
    pmax = _f(liv, "max_power_at_rated_mW", "MaxPowerAtRated_mW")
    if par is not None and pmin is not None and float(par) < pmin:
        result.fail_reasons.append(
            "LIV: power at rated current {:.6g} mW below PASS_FAIL limit {:.6g} mW.".format(float(par), pmin)
        )
    if par is not None and pmax is not None and float(par) > pmax:
        result.fail_reasons.append(
            "LIV: power at rated current {:.6g} mW above PASS_FAIL limit {:.6g} mW.".format(float(par), pmax)
        )

    fmin = _f(liv, "min_final_power_mW", "MinFinalPower_mW")
    fmax = _f(liv, "max_final_power_mW", "MaxFinalPower_mW")
    if fp is not None and fmin is not None and float(fp) < fmin:
        result.fail_reasons.append(
            "LIV: final Gentec power {:.6g} mW below PASS_FAIL limit {:.6g} mW.".format(float(fp), fmin)
        )
    if fp is not None and fmax is not None and float(fp) > fmax:
        result.fail_reasons.append(
            "LIV: final Gentec power {:.6g} mW above PASS_FAIL limit {:.6g} mW.".format(float(fp), fmax)
        )


def apply_per_pass_fail_criteria(recipe: Optional[Dict[str, Any]], result: Any, params: Any) -> None:
    """
    Append to result.fail_reasons for PASS_FAIL_CRITERIA.PER (min_PER_dB is merged into params via PERProcessParameters.from_recipe).
    Call when sweep produced data; structural errors (no samples) should be handled by caller first.
    """
    per_pfc = _pfc_section(recipe, "PER")
    min_db = float(getattr(params, "min_per_db", 0.0) or 0.0)
    if min_db <= 0 and per_pfc:
        min_db = float(_f(per_pfc, "min_PER_dB", "MinPER_dB") or 0.0)

    per_db = float(getattr(result, "per_db", 0.0) or 0.0)
    if min_db > 0 and per_db < min_db:
        result.fail_reasons.append(
            "PER: {:.3f} dB below PASS_FAIL minimum {:.3f} dB.".format(per_db, min_db)
        )

    if not per_pfc:
        return

    mxp = _f(per_pfc, "min_max_power_mW", "MinMaxPower_mW")
    maxp = float(getattr(result, "max_power", 0.0) or 0.0)
    if mxp is not None and maxp < mxp:
        result.fail_reasons.append(
            "PER: max Thorlabs power {:.6g} mW below PASS_FAIL limit {:.6g} mW.".format(maxp, mxp)
        )

    mnp = _f(per_pfc, "max_min_power_mW", "MaxMinPower_mW")
    minp = float(getattr(result, "min_power", 0.0) or 0.0)
    if mnp is not None and minp > mnp:
        result.fail_reasons.append(
            "PER: min Thorlabs power {:.6g} mW above PASS_FAIL limit {:.6g} mW.".format(minp, mnp)
        )

    pdb_max = _f(per_pfc, "max_PER_dB", "MaxPER_dB")
    if pdb_max is not None and per_db > pdb_max:
        result.fail_reasons.append(
            "PER: {:.3f} dB above PASS_FAIL maximum {:.3f} dB.".format(per_db, pdb_max)
        )
