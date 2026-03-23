"""
Load recipe files from disk. Same logic everywhere so Browse / Recipe tab / Start New agree.

- .json — UTF-8 (with BOM) JSON object
- .rcp — JSON first (app often saves .RCP as JSON); if that fails, ConfigParser (INI-style)
- .ini — ConfigParser; if no sections, try JSON (misnamed files)
- other — try JSON, then ConfigParser

Normalize is applied to nested JSON-style dicts (OPERATIONS) via recipe_normalize.
"""
from __future__ import annotations

import configparser
import json
import os
from typing import Any, Dict, Optional


def _normalize_if_dict(data: Any) -> None:
    if not isinstance(data, dict):
        return
    try:
        from operations.recipe_normalize import normalize_loaded_recipe

        normalize_loaded_recipe(data)
    except Exception:
        pass


def _load_ini(path: str) -> Optional[Dict[str, Any]]:
    cfg = configparser.ConfigParser()
    try:
        read = cfg.read(path, encoding="utf-8")
    except TypeError:
        read = cfg.read(path)
    if not read or not cfg.sections():
        return None
    return {s: dict(cfg[s]) for s in cfg.sections()}


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
        data = _load_ini(path)
        if isinstance(data, dict):
            _normalize_if_dict(data)
        return data

    if ext == ".ini":
        data = _load_ini(path)
        if data is not None:
            _normalize_if_dict(data)
            return data
        return _load_json_file()

    # Unknown extension: JSON then INI
    data = _load_json_raw()
    if data is not None:
        return data
    data = _load_ini(path)
    if isinstance(data, dict):
        _normalize_if_dict(data)
    return data
