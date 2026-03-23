"""
Simulation switches (no hardware) — use for bench development.

1) All simulated (no real hardware anywhere):
     BF_SIMULATE_ALL=1   or   simulate_all = 1

2) **Measurement chain real, rest simulated** (PRM + Thorlabs + Gentec real; Arroyo, Actuator, Ando, Wavemeter sim):
     BF_SIMULATE_EXCEPT_MEASUREMENT=1   or   simulate_except_measurement = 1
   You can still force one of the three to sim with simulate_thorlabs=1 / BF_SIMULATE_THORLABS=1, etc.

3) À la carte (simulate_all off, except_measurement off):
     BF_SIMULATE_ARROYO=1, simulate_gentec=1, ... per instrument.

If simulate_all is on, it wins over simulate_except_measurement.
"""
from __future__ import annotations

import configparser
import os
from pathlib import Path
from typing import Any, Dict, Optional

_ENV_TRUE = frozenset({"1", "true", "yes", "on"})

_KEYS = (
    "all",
    "arroyo",
    "actuator",
    "prm",
    "gentec",
    "thorlabs",
    "ando",
    "wavemeter",
)

_ENV_NAMES: Dict[str, str] = {
    "all": "BF_SIMULATE_ALL",
    "arroyo": "BF_SIMULATE_ARROYO",
    "actuator": "BF_SIMULATE_ACTUATOR",
    "prm": "BF_SIMULATE_PRM",
    "gentec": "BF_SIMULATE_GENTEC",
    "thorlabs": "BF_SIMULATE_THORLABS",
    "ando": "BF_SIMULATE_ANDO",
    "wavemeter": "BF_SIMULATE_WAVEMETER",
}

# Preset: real PRM + Thorlabs + Gentec; sim Arroyo, Actuator, Ando, Wavemeter
_ENV_EXCEPT_MEASUREMENT = "BF_SIMULATE_EXCEPT_MEASUREMENT"
_REAL_WHEN_EXCEPT_MEASUREMENT = frozenset({"prm", "gentec", "thorlabs"})
_SIM_WHEN_EXCEPT_MEASUREMENT = frozenset({"arroyo", "actuator", "ando", "wavemeter"})


def _truthy_env(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _ENV_TRUE


_ini_sim_cache: Optional[Dict[str, Any]] = None


def _read_ini_sim() -> Dict[str, Any]:
    global _ini_sim_cache  # noqa: PLW0603
    if _ini_sim_cache is not None:
        return _ini_sim_cache
    out: Dict[str, Any] = {k: False for k in _KEYS}
    out["except_measurement"] = False
    path = Path(__file__).resolve().parent / "instrument_config.ini"
    if path.is_file():
        try:
            cfg = configparser.ConfigParser()
            cfg.read(path, encoding="utf-8")
            if cfg.has_section("Simulation"):
                sec = cfg["Simulation"]
                if sec.has_option("simulate_except_measurement"):
                    out["except_measurement"] = (
                        str(sec.get("simulate_except_measurement", "0")).strip().lower() in _ENV_TRUE
                    )
                for k in _KEYS:
                    opt = "simulate_all" if k == "all" else f"simulate_{k}"
                    if sec.has_option(opt):
                        out[k] = str(sec.get(opt, "0")).strip().lower() in _ENV_TRUE
        except Exception:
            pass
    _ini_sim_cache = out
    return _ini_sim_cache


def simulate_except_measurement_enabled() -> bool:
    """Preset: real PRM, Thorlabs, Gentec; simulated Arroyo, Actuator, Ando, Wavemeter."""
    if _truthy_env(_ENV_NAMES["all"]):
        return False
    if _read_ini_sim().get("all"):
        return False
    if _truthy_env(_ENV_EXCEPT_MEASUREMENT):
        return True
    return bool(_read_ini_sim().get("except_measurement"))


def _effective(key: str) -> bool:
    assert key in _KEYS
    if _truthy_env(_ENV_NAMES["all"]):
        return True
    ini = _read_ini_sim()
    if ini.get("all"):
        return True

    if simulate_except_measurement_enabled():
        if key in _REAL_WHEN_EXCEPT_MEASUREMENT:
            if _truthy_env(_ENV_NAMES[key]):
                return True
            if bool(ini.get(key, False)):
                return True
            return False
        if key in _SIM_WHEN_EXCEPT_MEASUREMENT:
            return True
        if key == "all":
            return False
        return False

    if _truthy_env(_ENV_NAMES.get(key, "")):
        return True
    return bool(ini.get(key, False))


def simulate_all_enabled() -> bool:
    """True if every instrument should use simulation."""
    if _truthy_env(_ENV_NAMES["all"]):
        return True
    return bool(_read_ini_sim().get("all"))


def simulate_arroyo_enabled() -> bool:
    return _effective("arroyo")


def simulate_actuator_enabled() -> bool:
    return _effective("actuator")


def simulate_prm_enabled() -> bool:
    return _effective("prm")


def simulate_gentec_enabled() -> bool:
    return _effective("gentec")


def simulate_thorlabs_enabled() -> bool:
    return _effective("thorlabs")


def simulate_ando_enabled() -> bool:
    return _effective("ando")


def simulate_wavemeter_enabled() -> bool:
    return _effective("wavemeter")
