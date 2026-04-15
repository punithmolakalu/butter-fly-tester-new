"""
Shared Arroyo TEC/laser sequencing for LIV, PER test sequence, and GUI consistency.
"""
from __future__ import annotations

import os
import time
from typing import Any, Callable, Dict, Optional, Tuple, cast


def per_keep_laser_on_after_step(recipe: Optional[Dict[str, Any]]) -> bool:
    """
    If True, the test sequence will NOT call arroyo_laser_off after a PER step (laser stays on).

    Enable with environment ``BF_PER_KEEP_LASER_ON=1`` (or true/yes), or recipe:
    ``OPERATIONS.PER.keep_laser_on_after`` / ``KeepLaserOnAfter`` = 1 / true / yes,
    or ``GENERAL.keep_laser_on_after_per``.
    Default is False (laser OFF after PER for enclosure safety).
    """
    v = os.environ.get("BF_PER_KEEP_LASER_ON", "").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if not isinstance(recipe, dict):
        return False

    def _truthy(x: Any) -> bool:
        if x is None:
            return False
        if isinstance(x, bool):
            return x
        s = str(x).strip().lower()
        return s in ("1", "true", "yes", "on")

    op = recipe.get("OPERATIONS") or recipe.get("operations") or {}
    per = op.get("PER") or op.get("per") or {}
    for key in ("keep_laser_on_after", "KeepLaserOnAfter", "keep_laser_on_after_per"):
        if key in per:
            return _truthy(per.get(key))

    g = recipe.get("GENERAL") or recipe.get("general") or {}
    for key in ("keep_laser_on_after_per", "KeepLaserOnAfterPER"):
        if key in g:
            return _truthy(g.get(key))

    return False


def per_allow_laser_readback_off(recipe: Optional[Dict[str, Any]]) -> bool:
    """
    If True, PER does **not** abort when ``laser_read_output`` still reports OFF after ON commands.
    Use when the laser is on but the query is wrong (driver/firmware), and you will verify on Thorlabs.

    Enable with ``BF_PER_ALLOW_LASER_READBACK_OFF=1`` (or true/yes), or recipe under OPERATIONS.PER /
    GENERAL: ``allow_laser_readback_off``, ``AllowLaserReadbackOff``, ``skip_laser_output_readback_check``.
    """
    v = os.environ.get("BF_PER_ALLOW_LASER_READBACK_OFF", "").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if not isinstance(recipe, dict):
        return False

    def _truthy(x: Any) -> bool:
        if x is None:
            return False
        if isinstance(x, bool):
            return x
        s = str(x).strip().lower()
        return s in ("1", "true", "yes", "on")

    op = recipe.get("OPERATIONS") or recipe.get("operations") or {}
    per = op.get("PER") or op.get("per") or {}
    for key in (
        "allow_laser_readback_off",
        "AllowLaserReadbackOff",
        "skip_laser_output_readback_check",
        "SkipLaserOutputReadbackCheck",
    ):
        if key in per:
            return _truthy(per.get(key))

    g = recipe.get("GENERAL") or recipe.get("general") or {}
    for key in ("allow_laser_readback_off_per", "AllowLaserReadbackOffPER"):
        if key in g:
            return _truthy(g.get(key))

    return False


def arroyo_laser_off(arroyo: Any) -> None:
    """Turn off Arroyo laser output only; never raise."""
    try:
        if arroyo is not None and getattr(arroyo, "laser_set_output", None):
            arroyo.laser_set_output(0)
    except Exception:
        pass


def read_laser_output_on(arroyo: Any):
    """
    Read laser output state from Arroyo if supported.
    Returns True (on), False (off), or None (unknown / query failed / method missing).
    """
    lr = getattr(arroyo, "laser_read_output", None)
    if not callable(lr):
        return None
    try:
        v = lr()
    except Exception:
        return None
    if v is None:
        return None
    if v is True or v == 1:
        return True
    if v is False or v == 0:
        return False
    try:
        fv = float(cast(Any, v))
        if fv >= 0.5:
            return True
        return False
    except (TypeError, ValueError):
        pass
    s = str(v).strip().upper()
    if s in ("ON", "1", "YES", "TRUE"):
        return True
    if s in ("OFF", "0", "NO", "FALSE"):
        return False
    return None


def _ensure_arroyo_remote(arroyo: Any) -> None:
    """Re-assert remote/programmatic mode so laser/TEC commands are accepted."""
    try:
        fn = getattr(arroyo, "set_remote_mode", None)
        if callable(fn):
            fn()
            time.sleep(0.1)
    except Exception:
        pass


def arroyo_laser_on_safe(arroyo: Any) -> None:
    """
    Turn **TEC output on first**, wait, then **laser output on** (readback-aware, never raises).

    Order is fixed: ``set_output(1)`` (TEC) → short settle → ``laser_set_output(1)`` (laser).
    If readback shows TEC already on, the TEC command is skipped; laser is still enabled if off.
    """
    try:
        if arroyo is None:
            return
        set_out = getattr(arroyo, "set_output", None)
        ro = getattr(arroyo, "read_output", None)
        tec_need_on = True
        if callable(ro):
            try:
                tec_need_on = ro() != 1
            except Exception:
                tec_need_on = True
        # No read_output → always turn TEC on first (tec_need_on stays True).
        if tec_need_on and callable(set_out):
            set_out(1)
            time.sleep(0.28)
        lr = getattr(arroyo, "laser_read_output", None)
        if callable(lr):
            try:
                if lr() == 1:
                    return
            except Exception:
                pass
        if getattr(arroyo, "laser_set_output", None):
            arroyo.laser_set_output(1)
    except Exception:
        pass


def _to_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def per_laser_params_from_recipe(recipe: Dict[str, Any]) -> Tuple[float, float, float]:
    """
    Return (temp_C, drive_current_mA, current_limit_mA) for PER / laser prep.
    Order: OPERATIONS.PER, LIV, GENERAL.

    **Current limit:** defaults to the **same value as the drive current** (``laser_set_current_limit`` =
    ``laser_set_current``), so PER does not inherit LIV ``max_current_mA`` unless you set an explicit limit
    under ``OPERATIONS.PER``: ``max_current_mA``, ``MaxCurrent``, or ``current_limit_mA`` (must be ≥ drive current).
    """
    g = recipe.get("GENERAL") or recipe.get("general") or {}
    op = recipe.get("OPERATIONS") or recipe.get("operations") or {}
    per = op.get("PER") or op.get("per") or {}
    liv = op.get("LIV") or op.get("liv") or {}

    temp = _to_float(per.get("Temperature"), 0) or _to_float(per.get("temperature"), 0)
    if temp <= 0:
        temp = _to_float(liv.get("temperature"), 0) or _to_float(liv.get("Temperature"), 0)
    if temp <= 0:
        temp = _to_float(g.get("Temperature"), 0) or _to_float(g.get("temperature"), 0)
    if temp <= 0:
        temp = 25.0

    cur = _to_float(per.get("Current"), 0) or _to_float(per.get("current"), 0)
    if cur <= 0:
        cur = _to_float(g.get("Current"), 0) or _to_float(g.get("current"), 0)
    if cur <= 0:
        # Match LIV Thorlabs calibration: drive at LIV max when PER/GENERAL omit current.
        cur = _to_float(liv.get("max_current_mA"), 0)
    if cur <= 0:
        cur = _to_float(liv.get("min_current_mA"), 0) or _to_float(liv.get("rated_current_mA"), 0)

    lim = (
        _to_float(per.get("max_current_mA"), 0)
        or _to_float(per.get("MaxCurrent"), 0)
        or _to_float(per.get("current_limit_mA"), 0)
        or _to_float(per.get("CurrentLimit_mA"), 0)
    )
    if lim <= 0:
        # Default: current limit = drive current for PER (see per_laser_params_from_recipe docstring).
        lim = cur if cur > 0 else 1500.0
    if cur > 0:
        lim = max(lim, cur)

    return (temp, cur, lim)


def apply_arroyo_recipe_and_laser_on_for_per(
    arroyo: Any,
    recipe: Dict[str, Any],
    log: Optional[Callable[[str], None]] = None,
) -> Tuple[bool, str]:
    """
    Apply recipe setpoints, then enable outputs in order: **TEC on → (set limits/current) → laser on**.

    Sequence: remote mode → set TEC temperature → **TEC output ON** → laser current limit & setpoint
    → :func:`arroyo_laser_on_safe` (**TEC first, then laser**, with readback retry).
    Returns (success, error_message).
    """
    def _log(msg: str) -> None:
        if log:
            log(msg)

    if arroyo is None or not getattr(arroyo, "is_connected", lambda: False)():
        return False, "Arroyo not connected."

    temp, cur, lim = per_laser_params_from_recipe(recipe)
    if cur <= 0:
        return (
            False,
            "Recipe missing laser current for PER. Set OPERATIONS.PER.Current (or GENERAL.Current / LIV min current).",
        )

    try:
        _ensure_arroyo_remote(arroyo)
        _log("PER: Arroyo — applying recipe temperature, limits, and drive current (RCP).")
        set_temp = getattr(arroyo, "set_temp", None) or getattr(arroyo, "tec_set_temp", None)
        if callable(set_temp):
            set_temp(temp)
            time.sleep(0.2)

        set_tec_out = getattr(arroyo, "set_output", None)
        if callable(set_tec_out):
            set_tec_out(1)
            time.sleep(0.15)

        if getattr(arroyo, "laser_set_current_limit", None):
            arroyo.laser_set_current_limit(lim)
            time.sleep(0.1)
        if getattr(arroyo, "laser_set_current", None):
            arroyo.laser_set_current(cur)
            time.sleep(0.15)

        arroyo_laser_on_safe(arroyo)
        time.sleep(0.4)
        state = read_laser_output_on(arroyo)
        if state is not True:
            _log(
                "PER: Arroyo — laser not confirmed ON{}; retrying (TEC on, then laser).".format(
                    " (readback OFF)" if state is False else " (readback unclear)"
                )
            )
            _ensure_arroyo_remote(arroyo)
            # Never call laser_set_output before TEC — use shared TEC→laser sequence only
            arroyo_laser_on_safe(arroyo)
            time.sleep(0.5)
            state = read_laser_output_on(arroyo)

        if state is False:
            if per_allow_laser_readback_off(recipe):
                _log(
                    "PER: Arroyo — laser readback still OFF; continuing (BF_PER_ALLOW_LASER_READBACK_OFF or "
                    "recipe allow_laser_readback_off — verify beam on Thorlabs)."
                )
                time.sleep(max(0.2, min(0.8, 0.15 + cur / 2000.0)))
                _log(
                    "PER: Arroyo — laser ON command sent ({:.0f} mA drive, {:.0f} mA limit), TEC {:.1f} °C "
                    "(readback not enforced).".format(cur, lim, temp)
                )
                return True, ""
            return False, "Laser did not turn ON (check Arroyo, interlocks, and recipe current)."
        if state is None:
            _log(
                "PER: Arroyo — could not read laser output state; proceeding after ON command "
                "(verify beam on Thorlabs)."
            )

        # Brief settle so output stabilizes before PRM sweep / Thorlabs pre-check.
        time.sleep(max(0.2, min(0.8, 0.15 + cur / 2000.0)))

        _log("PER: Arroyo — laser ON ({:.0f} mA drive, {:.0f} mA limit), TEC {:.1f} °C.".format(cur, lim, temp))
        return True, ""
    except Exception as e:
        return False, str(e)


def spectrum_laser_params_from_recipe(recipe: Dict[str, Any]) -> Tuple[float, float, float]:
    """
    Temperature (°C), drive current (mA), current limit (mA) for Spectrum step.
    Prefers OPERATIONS.SPECTRUM, then GENERAL / LIV / PER (same fallbacks as PER order where useful).
    """
    g = recipe.get("GENERAL") or recipe.get("general") or {}
    op = recipe.get("OPERATIONS") or recipe.get("operations") or {}
    spec = op.get("SPECTRUM") or op.get("spectrum") or {}
    liv = op.get("LIV") or op.get("liv") or {}
    per = op.get("PER") or op.get("per") or {}

    temp = _to_float(spec.get("Temperature"), 0) or _to_float(spec.get("temperature"), 0)
    if temp <= 0:
        temp = _to_float(spec.get("Temp"), 0)
    if temp <= 0:
        temp = _to_float(g.get("Temperature"), 0) or _to_float(g.get("temperature"), 0)
    if temp <= 0:
        temp = _to_float(liv.get("temperature"), 0) or _to_float(per.get("Temperature"), 0)
    if temp <= 0:
        temp = 25.0

    # Prefer SPECTRUM block; accept common save/load variants (GUI saves "current" lowercase).
    cur = (
        _to_float(spec.get("Current"), 0)
        or _to_float(spec.get("current"), 0)
        or _to_float(spec.get("laser_current_mA"), 0)
        or _to_float(spec.get("LaserCurrent"), 0)
    )
    if cur <= 0:
        cur = (
            _to_float(g.get("Current"), 0)
            or _to_float(g.get("current"), 0)
            or _to_float(g.get("SetCurr"), 0)
            or _to_float(g.get("set_curr"), 0)
            or _to_float(g.get("LaserCurrent"), 0)
            or _to_float(recipe.get("Current"), 0)
            or _to_float(recipe.get("current"), 0)
        )
    # Same order as PER: PER step often carries the drive current when SPECTRUM block is minimal.
    if cur <= 0:
        cur = _to_float(per.get("Current"), 0) or _to_float(per.get("current"), 0)
    if cur <= 0:
        cur = _to_float(liv.get("min_current_mA"), 0) or _to_float(liv.get("rated_current_mA"), 0)

    lim = _to_float(liv.get("max_current_mA"), 0)
    if lim <= 0:
        lim = max(cur * 1.2, cur + 200.0, 500.0) if cur > 0 else 1500.0
    if cur > 0:
        lim = max(lim, cur)

    return (temp, cur, lim)


def spectrum_keep_laser_on_after_step(recipe: Optional[Dict[str, Any]]) -> bool:
    """If True, do not turn laser off after Spectrum (env BF_SPECTRUM_KEEP_LASER_ON or recipe flag)."""
    v = os.environ.get("BF_SPECTRUM_KEEP_LASER_ON", "").strip().lower()
    if v in ("1", "true", "yes", "on"):
        return True
    if not isinstance(recipe, dict):
        return False

    def _truthy(x: Any) -> bool:
        if x is None:
            return False
        if isinstance(x, bool):
            return x
        s = str(x).strip().lower()
        return s in ("1", "true", "yes", "on")

    op = recipe.get("OPERATIONS") or recipe.get("operations") or {}
    spec = op.get("SPECTRUM") or op.get("spectrum") or {}
    for key in ("keep_laser_on_after", "KeepLaserOnAfter", "keep_laser_on_after_spectrum"):
        if key in spec:
            return _truthy(spec.get(key))

    g = recipe.get("GENERAL") or recipe.get("general") or {}
    for key in ("keep_laser_on_after_spectrum", "KeepLaserOnAfterSpectrum"):
        if key in g:
            return _truthy(g.get(key))

    return False


def apply_arroyo_recipe_and_laser_on_for_spectrum(
    arroyo: Any,
    recipe: Dict[str, Any],
    log: Optional[Callable[[str], None]] = None,
) -> Tuple[bool, str]:
    """Same sequence as PER: TEC temp → TEC on → limits → laser current → laser on (readback). Uses SPECTRUM RCP currents."""
    def _log(msg: str) -> None:
        if log:
            log(msg)

    if arroyo is None or not getattr(arroyo, "is_connected", lambda: False)():
        return False, "Arroyo not connected."

    temp, cur, lim = spectrum_laser_params_from_recipe(recipe)
    if cur <= 0:
        return (
            False,
            "Recipe missing laser current for Spectrum. Set OPERATIONS.SPECTRUM.Current (or GENERAL.Current).",
        )

    try:
        _ensure_arroyo_remote(arroyo)
        _log("Spectrum: Arroyo — applying recipe temperature, limits, and drive current (SPECTRUM RCP).")
        set_temp = getattr(arroyo, "set_temp", None) or getattr(arroyo, "tec_set_temp", None)
        if callable(set_temp):
            set_temp(temp)
            time.sleep(0.2)

        set_tec_out = getattr(arroyo, "set_output", None)
        if callable(set_tec_out):
            set_tec_out(1)
            time.sleep(0.15)

        if getattr(arroyo, "laser_set_current_limit", None):
            arroyo.laser_set_current_limit(lim)
            time.sleep(0.1)
        if getattr(arroyo, "laser_set_current", None):
            arroyo.laser_set_current(cur)
            time.sleep(0.15)

        arroyo_laser_on_safe(arroyo)
        time.sleep(0.4)
        state = read_laser_output_on(arroyo)
        if state is not True:
            _log(
                "Spectrum: Arroyo — laser not confirmed ON{}; retrying.".format(
                    " (readback OFF)" if state is False else " (readback unclear)"
                )
            )
            _ensure_arroyo_remote(arroyo)
            arroyo_laser_on_safe(arroyo)
            time.sleep(0.5)
            state = read_laser_output_on(arroyo)

        if state is False:
            if per_allow_laser_readback_off(recipe):
                _log(
                    "Spectrum: laser readback OFF; continuing (allow_laser_readback_off / BF_PER_ALLOW_LASER_READBACK_OFF)."
                )
                time.sleep(max(0.2, min(0.8, 0.15 + cur / 2000.0)))
                return True, ""
            return False, "Laser did not turn ON (check Arroyo, interlocks, and recipe current)."
        if state is None:
            _log("Spectrum: could not read laser output; proceeding after ON command.")

        time.sleep(max(0.2, min(0.8, 0.15 + cur / 2000.0)))
        _log("Spectrum: Arroyo — laser ON ({:.0f} mA set), TEC {:.1f} °C.".format(cur, temp))
        return True, ""
    except Exception as e:
        return False, str(e)
