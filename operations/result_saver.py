"""
Persist every test-sequence run to ``results/<recipe_name>_<timestamp>/``.

Each sub-folder contains:
  session.json          – recipe name, timestamp, sequence list, overall pass/fail
  sequence.json         – **single combined archive** for the whole run: same session block, every test’s
                          dict (LIV / PER / Spectrum / TS1 / TS2) with **raw sweep arrays**, and ``status_log``
  liv.json … ts2.json   – per-step copies (same payloads) for the Data View and simple tools
  log.txt               – full status-log captured during the run

One **folder** per Run; one **combined** ``sequence.json`` holds all steps that executed in that run (not
separate runs). Stem JSON files are still written so existing viewers keep working.

On ``save()``, every distinct step listed in ``TEST_SEQUENCE`` gets a stem entry so PASS/FAIL/ABORT
and early exits still leave a loadable record.

All JSON values are plain Python scalars/lists so the viewer can load
them without importing instrument code.
"""
from __future__ import annotations

import copy
import dataclasses
import json
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


_RESULTS_ROOT = Path(__file__).resolve().parents[1] / "results"


def get_results_root() -> Path:
    """Absolute path to the project ``results`` directory (each run uses ``<recipe>_<timestamp>/`` inside it)."""
    return _RESULTS_ROOT.resolve()


def _stem_for_sequence_step(step_name: str) -> Optional[str]:
    """Map one TEST_SEQUENCE label to a result file stem (same rules as the sequence executor / data viewer)."""
    t = (step_name or "").strip().upper()
    if t == "LIV":
        return "liv"
    if t == "PER":
        return "per"
    if t == "SPECTRUM" or "SPECTRUM" in t:
        return "spectrum"
    if "STABILITY 2" in t or t in ("TS2", "TS 2"):
        return "ts2"
    if "STABILITY 1" in t or t in ("TS1", "TS 1"):
        return "ts1"
    if "STABILITY" in t and "2" in t:
        return "ts2"
    if "STABILITY" in t and "1" in t:
        return "ts1"
    return None


# Stems written to ``<stem>.json`` and shown in Load Result / Data View (fixed order).
_STEM_JSON_ORDER: tuple = ("liv", "per", "spectrum", "ts1", "ts2")

# Folder names are ``<safe_recipe>_<YYYYMMDD_HHMMSS>`` (see ``ResultSession._folder_name``).
_FOLDER_TS_RE = re.compile(r"^(.+)_(\d{8}_\d{6})$")


def _folder_has_any_stem_json(folder: Path) -> bool:
    return any((folder / "{}.json".format(s)).is_file() for s in _STEM_JSON_ORDER)


def _infer_session_meta_from_folder(folder: Path) -> Dict[str, Any]:
    """List-row metadata when ``session.json`` / ``sequence.json`` are missing (legacy stem-only saves)."""
    name = folder.name
    m = _FOLDER_TS_RE.match(name)
    if m:
        return {
            "recipe_name": m.group(1),
            "timestamp": m.group(2),
            "overall_passed": None,
            "stopped_by_user": False,
        }
    return {"recipe_name": name, "timestamp": "", "overall_passed": None, "stopped_by_user": False}


def _epoch_for_session_row(entry: Dict[str, Any]) -> float:
    """Sort key: larger = newer. Uses ``timestamp``, else parses folder name, else directory mtime."""
    ts = str(entry.get("timestamp") or "").strip()
    name = str(entry.get("name") or "")
    folder = Path(str(entry.get("folder", "")))
    if len(ts) >= 15 and ts[8] == "_" and ts[:8].isdigit() and ts[9:15].isdigit():
        try:
            return datetime.strptime(ts, "%Y%m%d_%H%M%S").timestamp()
        except ValueError:
            pass
    m = _FOLDER_TS_RE.match(name)
    if m:
        try:
            return datetime.strptime(m.group(2), "%Y%m%d_%H%M%S").timestamp()
        except ValueError:
            pass
    try:
        if folder.is_dir():
            return folder.stat().st_mtime
    except Exception:
        pass
    return 0.0


def _planned_stems_from_session(session: Any) -> List[str]:
    """Distinct result stems implied by ``session['test_sequence']`` (or ``TestSequence``), in run order."""
    if not isinstance(session, dict):
        return []
    seq = session.get("test_sequence") or session.get("TestSequence") or []
    if not isinstance(seq, list):
        return []
    seen: set = set()
    out: List[str] = []
    for step in seq:
        st = _stem_for_sequence_step(str(step))
        if st is None or st in seen:
            continue
        seen.add(st)
        out.append(st)
    return out


def _stems_present_in_sequence_archive(folder: Path) -> set:
    """Stems that have a non-empty dict inside ``sequence.json`` → ``tests`` (if that file exists)."""
    out: set = set()
    sq = folder / "sequence.json"
    if not sq.is_file():
        return out
    try:
        with open(sq, "r", encoding="utf-8") as f:
            cj = json.load(f)
        t = cj.get("tests")
        if isinstance(t, dict):
            for stem in _STEM_JSON_ORDER:
                blob = t.get(stem)
                if isinstance(blob, dict) and blob:
                    out.add(stem)
    except Exception:
        pass
    return out


def _tests_for_result_folder(info: Dict[str, Any], folder: Path) -> List[str]:
    """Stems for the Load Result line: stem JSON, ``sequence.json`` tests, and/or session sequence."""
    on_disk = {s for s in _STEM_JSON_ORDER if (folder / "{}.json".format(s)).is_file()}
    on_disk |= _stems_present_in_sequence_archive(folder)
    planned = set(_planned_stems_from_session(info))
    merged = on_disk | planned
    return [s for s in _STEM_JSON_ORDER if s in merged]


def _merge_archive_session_into(base_session: Dict[str, Any], archive_session: Dict[str, Any]) -> None:
    """Fill missing or empty fields in ``base_session`` from ``sequence.json``'s ``session`` object."""
    for k, v in archive_session.items():
        if v in (None, "", [], {}):
            continue
        if k == "recipe" and isinstance(v, dict):
            cur = base_session.get("recipe")
            if not isinstance(cur, dict) or len(cur) == 0:
                base_session["recipe"] = copy.deepcopy(v)
            continue
        cur = base_session.get(k)
        if k not in base_session or cur in (None, "", [], {}):
            base_session[k] = copy.deepcopy(v) if isinstance(v, (dict, list)) else v
        elif k == "test_sequence" and isinstance(cur, list) and len(cur) == 0 and isinstance(v, list) and len(v) > 0:
            base_session[k] = copy.deepcopy(v)


def _normalize_test_sequence_in_session(sess: Dict[str, Any]) -> None:
    """Ensure ``test_sequence`` is a ``list[str]`` so the Data View can order tabs (handles INI/string quirks)."""
    raw = sess.get("test_sequence")
    if raw is None:
        raw = sess.get("TestSequence")
    if isinstance(raw, list):
        sess["test_sequence"] = [str(x) for x in raw]
        return
    if isinstance(raw, str):
        s = raw.strip()
        if s.startswith("["):
            try:
                j = json.loads(s)
                if isinstance(j, list):
                    sess["test_sequence"] = [str(x) for x in j]
                    return
            except Exception:
                pass
        parts = [x.strip() for x in s.replace(";", ",").split(",") if x.strip()]
        if parts:
            sess["test_sequence"] = parts
            return
    if not isinstance(sess.get("test_sequence"), list):
        sess["test_sequence"] = []


def _safe_filename(s: str, max_len: int = 80) -> str:
    t = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(s or "unknown").strip())
    return t[:max_len] or "unknown"


def _sanitize(obj: Any) -> Any:
    """Convert dataclass / float('nan') / nested dicts to JSON-safe primitives."""
    try:
        import numpy as np  # type: ignore

        if isinstance(obj, np.ndarray):
            return _sanitize(obj.tolist())
        if isinstance(obj, np.generic):
            return _sanitize(obj.item())
    except ImportError:
        pass
    except Exception:
        pass
    if dataclasses.is_dataclass(obj) and not isinstance(obj, type):
        # ``dataclasses.asdict`` follows every field; LIVProcessResult sets ``liv_result`` to ``self`` for GUI
        # compatibility, which causes infinite recursion. Build a shallow field dict and skip any field
        # whose value is the instance itself (same pattern safe for other accidental cycles).
        d: Dict[str, Any] = {}
        for f in dataclasses.fields(obj):
            try:
                v = getattr(obj, f.name)
            except Exception:
                continue
            if v is obj:
                continue
            d[f.name] = v
        return _sanitize(d)
    if isinstance(obj, dict):
        return {str(k): _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, (int, bool, str, type(None))):
        return obj
    return str(obj)


class ResultSession:
    """Accumulates test results then writes the folder on ``save()``."""

    def __init__(self, recipe_name: str, recipe_data: Optional[Dict[str, Any]] = None,
                 test_sequence: Optional[List[str]] = None):
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._folder_name = "{}_{}".format(_safe_filename(recipe_name), ts)
        self._folder: Optional[Path] = None
        self._recipe_name = str(recipe_name or "")
        self._recipe_data = recipe_data
        self._test_sequence = list(test_sequence or [])
        self._timestamp = ts
        self._overall_passed: Optional[bool] = None
        self._stopped = False
        self._results: Dict[str, Any] = {}
        self._log_lines: List[str] = []

    @property
    def folder_path(self) -> Optional[Path]:
        return self._folder

    def append_log(self, line: str) -> None:
        self._log_lines.append(str(line))

    def set_liv_result(self, result: Any) -> None:
        self._results["liv"] = _sanitize(result)

    def set_per_result(self, result: Any) -> None:
        self._results["per"] = _sanitize(result)

    def set_spectrum_result(self, result: Any) -> None:
        self._results["spectrum"] = _sanitize(result)

    def set_stability_result(self, slot: int, result: Any) -> None:
        key = "ts{}".format(int(slot))
        self._results[key] = _sanitize(result)

    def has_result(self, stem: str) -> bool:
        """True if we already stored JSON for this stem (liv / per / spectrum / ts1 / ts2)."""
        return stem in self._results

    def ensure_placeholder_result(self, stem: str, fail_reasons: List[str]) -> None:
        """If a step ran but nothing was stored (prerequisite fail, serialization error, etc.), save a minimal record."""
        if stem not in ("liv", "per", "spectrum", "ts1", "ts2"):
            return
        if stem in self._results:
            return
        reasons = [str(x) for x in (fail_reasons or []) if x is not None and str(x).strip()]
        if not reasons:
            reasons = ["No measurement payload was saved for this step."]
        payload: Dict[str, Any] = {
            "passed": False,
            "fail_reasons": reasons,
            "result_placeholder": True,
        }
        if stem == "ts1":
            payload["slot"] = 1
        elif stem == "ts2":
            payload["slot"] = 2
        self._results[stem] = _sanitize(payload)

    def set_overall(self, passed: bool, stopped: bool = False) -> None:
        self._overall_passed = passed
        self._stopped = stopped

    def _ensure_placeholder_for_planned_sequence(self) -> None:
        """Before writing files: every distinct step in ``_test_sequence`` must have a stem entry so
        ``liv.json`` / ``per.json`` / … always exist (PASS, FAIL, ABORT, exception, or not reached)."""
        seen: set = set()
        for step in self._test_sequence:
            stem = _stem_for_sequence_step(str(step))
            if stem is None or stem in seen:
                continue
            seen.add(stem)
            if not self.has_result(stem):
                self.ensure_placeholder_result(
                    stem,
                    [
                        "No detailed result was stored for this step before save "
                        "(stopped early, prerequisite failed, crash, or older run). "
                        "Check the session log and main-window failure text.",
                    ],
                )

    def save(self) -> Path:
        root = _RESULTS_ROOT
        root.mkdir(parents=True, exist_ok=True)
        folder = root / self._folder_name
        folder.mkdir(parents=True, exist_ok=True)
        self._folder = folder

        self._ensure_placeholder_for_planned_sequence()

        session_info: Dict[str, Any] = {
            "recipe_name": self._recipe_name,
            "timestamp": self._timestamp,
            "test_sequence": self._test_sequence,
            "overall_passed": self._overall_passed,
            "stopped_by_user": self._stopped,
        }
        if self._recipe_data is not None:
            try:
                session_info["recipe"] = _sanitize(self._recipe_data)
            except Exception:
                session_info["recipe"] = {
                    "_note": "Full recipe could not be serialized for this session.json (non-JSON-safe or too deep).",
                    "Recipe_Name": (self._recipe_data or {}).get("Recipe_Name")
                    if isinstance(self._recipe_data, dict)
                    else None,
                }
        try:
            _write_json(folder / "session.json", session_info)
        except Exception:
            # Minimal session so the folder is still listable and per-stem files can be opened.
            _write_json(
                folder / "session.json",
                {
                    "recipe_name": self._recipe_name,
                    "timestamp": self._timestamp,
                    "test_sequence": self._test_sequence,
                    "overall_passed": self._overall_passed,
                    "stopped_by_user": self._stopped,
                    "_session_write_error": "Primary session.json write failed; recipe snapshot omitted.",
                },
            )

        for key, data in list(self._results.items()):
            try:
                _write_json(folder / "{}.json".format(key), data)
            except Exception:
                try:
                    _write_json(
                        folder / "{}.json".format(key),
                        {
                            "passed": False,
                            "fail_reasons": ["Result JSON write failed for stem {!r}.".format(key)],
                            "result_placeholder": True,
                        },
                    )
                except Exception:
                    pass

        # One combined file for the entire sequence (all tests, raw arrays, session snapshot, log).
        try:
            ordered_keys = [k for k in _STEM_JSON_ORDER if k in self._results]
            ordered_keys.extend(k for k in self._results if k not in ordered_keys)
            seq_archive: Dict[str, Any] = {
                "schema_version": 1,
                "session": copy.deepcopy(session_info),
                "tests": {k: copy.deepcopy(self._results[k]) for k in ordered_keys},
                "status_log": "\n".join(self._log_lines),
            }
            _write_json(folder / "sequence.json", _sanitize(seq_archive))
        except Exception:
            try:
                _write_json(
                    folder / "sequence.json",
                    {
                        "schema_version": 1,
                        "error": "sequence.json write failed",
                        "recipe_name": self._recipe_name,
                        "timestamp": self._timestamp,
                    },
                )
            except Exception:
                pass

        if self._log_lines:
            try:
                (folder / "log.txt").write_text("\n".join(self._log_lines), encoding="utf-8")
            except Exception:
                pass

        return folder


def _write_json(path: Path, data: Any) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)


def list_saved_sessions() -> List[Dict[str, Any]]:
    """Return list of saved sessions sorted newest-first (by run timestamp, not folder-name spelling).

    Includes:
    - normal folders with ``session.json`` and/or ``sequence.json``;
    - legacy folders that only have ``liv.json`` / ``per.json`` / … and no session file.

    Each dict has keys: ``folder``, ``recipe_name``, ``timestamp``,
    ``overall_passed``, ``stopped_by_user``, ``tests`` (list of file stems).
    """
    root = _RESULTS_ROOT
    if not root.is_dir():
        return []
    sessions: List[Dict[str, Any]] = []
    for d in root.iterdir():
        if not d.is_dir():
            continue
        sp = d / "session.json"
        sq = d / "sequence.json"
        stem_any = _folder_has_any_stem_json(d)
        if not sp.is_file() and not sq.is_file() and not stem_any:
            continue
        info: Optional[Dict[str, Any]] = None
        if sp.is_file():
            try:
                with open(sp, "r", encoding="utf-8") as f:
                    info = json.load(f)
            except Exception:
                info = None
        if not isinstance(info, dict) and sq.is_file():
            try:
                with open(sq, "r", encoding="utf-8") as f:
                    cj = json.load(f)
                if isinstance(cj, dict) and isinstance(cj.get("session"), dict):
                    info = copy.deepcopy(cj["session"])
            except Exception:
                pass
        if not isinstance(info, dict):
            if stem_any:
                info = _infer_session_meta_from_folder(d)
            else:
                continue
        try:
            tests = _tests_for_result_folder(info, d)
            sessions.append({
                "folder": str(d),
                "name": d.name,
                "recipe_name": str(info.get("recipe_name") or ""),
                "timestamp": str(info.get("timestamp") or ""),
                "overall_passed": info.get("overall_passed"),
                "stopped_by_user": bool(info.get("stopped_by_user", False)),
                "tests": tests,
            })
        except Exception:
            continue
    sessions.sort(key=_epoch_for_session_row, reverse=True)
    return sessions


def load_session(folder: str) -> Dict[str, Any]:
    """Load all data from a saved session folder."""
    p = Path(folder)
    data: Dict[str, Any] = {"folder": str(p)}
    sp = p / "session.json"
    if sp.is_file():
        try:
            with open(sp, "r", encoding="utf-8") as f:
                data["session"] = json.load(f)
        except Exception:
            data["session"] = {}
    if not isinstance(data.get("session"), dict):
        data["session"] = {}

    combined_tests: Optional[Dict[str, Any]] = None
    combined_log: Optional[str] = None
    comb: Optional[Dict[str, Any]] = None
    sqp = p / "sequence.json"
    if sqp.is_file():
        try:
            with open(sqp, "r", encoding="utf-8") as f:
                comb = json.load(f)
        except Exception:
            comb = None
    if isinstance(comb, dict):
        arch_sess = comb.get("session")
        if isinstance(arch_sess, dict):
            if len(data["session"]) == 0:
                data["session"] = copy.deepcopy(arch_sess)
            else:
                _merge_archive_session_into(data["session"], arch_sess)
        t = comb.get("tests")
        if isinstance(t, dict):
            combined_tests = t
        sl = comb.get("status_log")
        if isinstance(sl, str) and sl.strip():
            combined_log = sl

    _normalize_test_sequence_in_session(data["session"])
    sess0 = data.get("session")
    if isinstance(sess0, dict):
        if not str(sess0.get("recipe_name") or "").strip() or not str(sess0.get("timestamp") or "").strip():
            inf = _infer_session_meta_from_folder(p)
            if not str(sess0.get("recipe_name") or "").strip():
                sess0["recipe_name"] = str(inf.get("recipe_name") or "")
            if not str(sess0.get("timestamp") or "").strip():
                sess0["timestamp"] = str(inf.get("timestamp") or "")

    for stem in _STEM_JSON_ORDER:
        fp = p / "{}.json".format(stem)
        loaded = False
        if fp.is_file():
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    blob = json.load(f)
                if isinstance(blob, dict):
                    data[stem] = blob
                    loaded = True
            except Exception:
                pass
        if not loaded and combined_tests is not None:
            blob = combined_tests.get(stem)
            if isinstance(blob, dict):
                data[stem] = blob
    sess = data.get("session")
    if isinstance(sess, dict):
        for stem in _planned_stems_from_session(sess):
            cur = data.get(stem)
            if not isinstance(cur, dict):
                data[stem] = {
                    "passed": False,
                    "fail_reasons": [
                        "No usable JSON for this step in this folder (incomplete save, corrupt file, or viewer opened mid-save).",
                    ],
                    "result_placeholder": True,
                }
    log_fp = p / "log.txt"
    if log_fp.is_file():
        data["log"] = log_fp.read_text(encoding="utf-8")
    elif combined_log is not None:
        data["log"] = combined_log
    return data
