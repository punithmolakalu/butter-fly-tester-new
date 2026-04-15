"""
Load recipe files from disk. Same logic everywhere so Browse / Recipe tab / Start New agree.

- .json — UTF-8 (with BOM) JSON object
- .rcp — JSON first (app often saves .RCP as JSON); if that fails, ConfigParser (INI-style)
- .ini — ConfigParser (INI); nested dict/list values are stored as JSON on one line.
  Optional [RECIPE] section maps to top-level Recipe_Name, TEST_SEQUENCE, etc.
- other — try JSON, then ConfigParser

Normalize is applied to nested JSON-style dicts (OPERATIONS) via recipe_normalize.
"""
from __future__ import annotations

import configparser
import json
import os
from typing import Any, Dict, Optional


def _make_configparser() -> configparser.ConfigParser:
    cfg = configparser.ConfigParser(interpolation=None)
    # Identity transform preserves key case (Recipe_Name, min_current_mA, …); builtin `str` fails strict stubs.
    cfg.optionxform = lambda option: option
    return cfg


def _normalize_if_dict(data: Any) -> None:
    if not isinstance(data, dict):
        return
    try:
        from operations.recipe_normalize import normalize_loaded_recipe

        normalize_loaded_recipe(data)
    except Exception:
        pass


def _load_ini(path: str) -> Optional[Dict[str, Any]]:
    cfg = _make_configparser()
    try:
        read = cfg.read(path, encoding="utf-8")
    except TypeError:
        read = cfg.read(path)
    if not read or not cfg.sections():
        return None
    return {s: dict(cfg[s]) for s in cfg.sections()}


def _ini_value_decode(raw: str) -> Any:
    s = (raw or "").strip()
    if not s:
        return ""
    if s[0] in "[{":
        try:
            return json.loads(s)
        except json.JSONDecodeError:
            pass
    return raw


def _expand_ini_sections_to_recipe(sections: Dict[str, Dict[str, str]]) -> Dict[str, Any]:
    """Turn ConfigParser section dict into the same shape JSON recipes use (before normalize)."""
    out: Dict[str, Any] = {}
    for sec_name, sec_dict in sections.items():
        decoded: Dict[str, Any] = {}
        for k, v in sec_dict.items():
            decoded[k] = _ini_value_decode(v)
        name = sec_name.strip()
        uname = name.upper()
        if uname == "RECIPE":
            for k2, v2 in decoded.items():
                out[k2] = v2
        else:
            out[name] = decoded
    return out


def _format_ini_value(v: Any) -> str:
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    if isinstance(v, bool):
        return "true" if v else "false"
    if v is None:
        return ""
    return str(v)


def save_recipe_ini(path: str, data: Dict[str, Any]) -> None:
    """
    Write a recipe dict as an INI file. OPERATIONS blocks become one section each
    (e.g. [LIV], [SPECTRUM], [Temperature Stability 1]). Top-level metadata goes in [RECIPE].
    """
    if not isinstance(data, dict):
        raise TypeError("recipe data must be a dict")
    cfg = _make_configparser()
    g = data.get("GENERAL") if isinstance(data.get("GENERAL"), dict) else {}
    g = dict(g) if isinstance(g, dict) else {}

    recipe_sec: Dict[str, str] = {}
    if data.get("Recipe_Name") is not None:
        recipe_sec["Recipe_Name"] = _format_ini_value(data.get("Recipe_Name"))
    if data.get("Description") is not None:
        recipe_sec["Description"] = _format_ini_value(data.get("Description"))
    ts = data.get("TEST_SEQUENCE") or data.get("TestSequence")
    if isinstance(ts, list):
        recipe_sec["TEST_SEQUENCE"] = ", ".join(str(x).strip() for x in ts if str(x).strip())
    elif isinstance(ts, str) and ts.strip():
        recipe_sec["TEST_SEQUENCE"] = ts.strip()
    for key in ("FiberCoupled", "Wavelength", "Current"):
        if key in data and data[key] is not None:
            recipe_sec[key] = _format_ini_value(data[key])
    if recipe_sec:
        cfg["RECIPE"] = recipe_sec

    if g:
        cfg["GENERAL"] = {k: _format_ini_value(g[k]) for k in g}

    op = data.get("OPERATIONS") or data.get("operations")
    if isinstance(op, dict):
        for block_name, block in op.items():
            if not isinstance(block, dict):
                continue
            sec = str(block_name).strip() or "OPERATIONS"
            cfg[sec] = {k: _format_ini_value(block[k]) for k in block}

    for key in ("PASS_FAIL_CRITERIA", "PASS_FAIL", "pass_fail_criteria"):
        blk = data.get(key)
        if isinstance(blk, dict) and blk:
            cfg[key] = {k: _format_ini_value(blk[k]) for k in blk}

    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        cfg.write(f)


def load_recipe_file(path: str) -> Optional[Dict[str, Any]]:
    path = (path or "").strip()
    if not path or not os.path.isfile(path):
        return None

    ext = os.path.splitext(path)[1].lower()

    def _load_json_file() -> Optional[Dict[str, Any]]:
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                data = json.load(f)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            return None
        if isinstance(data, dict):
            _normalize_if_dict(data)
            return data
        return None

    def _load_json_raw() -> Optional[Dict[str, Any]]:
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                raw = f.read()
        except (OSError, UnicodeDecodeError):
            return None
        raw = raw.strip()
        if not raw:
            return None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if isinstance(data, dict):
            _normalize_if_dict(data)
            return data
        return None

    if ext == ".json":
        return _load_json_file()

    if ext == ".rcp":
        data = _load_json_raw()
        if data is not None:
            return data
        raw_ini = _load_ini(path)
        if raw_ini is not None:
            data = _expand_ini_sections_to_recipe(raw_ini)
            _normalize_if_dict(data)
            return data
        return None

    if ext == ".ini":
        raw_ini = _load_ini(path)
        if raw_ini is not None:
            data = _expand_ini_sections_to_recipe(raw_ini)
            _normalize_if_dict(data)
            return data
        return _load_json_file()

    # Unknown extension: JSON then INI
    data = _load_json_raw()
    if data is not None:
        return data
    raw_ini = _load_ini(path)
    if raw_ini is not None:
        data = _expand_ini_sections_to_recipe(raw_ini)
        _normalize_if_dict(data)
        return data
    return None
