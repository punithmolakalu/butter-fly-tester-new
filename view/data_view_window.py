"""
Password-protected Data View window.

Opens on secondary monitor maximized with empty layout.
User loads a result via the toolbar — tabs fill with graphs, logs, tables.

Summary tab: session line, combined parameter table for every test present, and RCP as flat name/value rows.

Per-test tabs follow ``session.test_sequence`` (LIV, PER, Spectrum, Temperature Stability 1/2, etc.);
any result JSON present but not listed in the sequence is appended so nothing is skipped.

Each test tab has two inner sub-tabs:
  Plot  — left: RCP parameters (name → value table) + status log; right: graph + summary info
  Table — grid numeric values for that test
"""
from __future__ import annotations

import json
import math
from typing import Any, Dict, List, Optional

from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTabWidget,
    QLabel, QTableWidget, QTableWidgetItem, QHeaderView,
    QPlainTextEdit, QDialog, QLineEdit, QPushButton,
    QListWidget, QListWidgetItem, QMessageBox, QSplitter,
    QFormLayout, QAbstractItemView, QToolBar, QAction, QScrollArea,
)
from PyQt5.QtCore import Qt, QSize, QObject, QEvent
from PyQt5.QtGui import QColor, QDoubleValidator

from view.dark_theme import get_dark_palette, main_stylesheet, set_dark_title_bar

try:
    import pyqtgraph as pg
    _PG = True
except ImportError:
    pg = None  # type: ignore
    _PG = False

from operations.result_saver import list_saved_sessions, load_session

try:
    from view.temperature_stability_plot import (
        build_stability_tab_plot,
        stability_tab_apply_result,
        stability_tab_autorange,
    )
    _TS_PLOT_AVAILABLE = True
except ImportError:
    _TS_PLOT_AVAILABLE = False

try:
    from view.liv_process_plot import build_liv_process_plot, liv_autorange_secondary_axes
    _LIV_PLOT_AVAILABLE = True
except ImportError:
    _LIV_PLOT_AVAILABLE = False

try:
    from view.plot_series_checkboxes import (
        PER_SERIES_LABELS, PER_SERIES_COLORS,
        make_series_checkbox_row, freeze_plot_navigation,
    )
    from view.temperature_stability_plot import compact_simple_xy_plot_axes
    _SERIES_CB_AVAILABLE = True
except ImportError:
    _SERIES_CB_AVAILABLE = False

_PASSWORD = "1234"

_LOG_STYLE = "background: #1e1e22; color: #b0bec5; font-size: 11px; font-family: Consolas, monospace;"
_PASS_COLOR = "#43a047"
_FAIL_COLOR = "#e53935"
_ABORTED_COLOR = "#FF9800"
_UNKNOWN_COLOR = "#9e9e9e"

_TABLE_STYLE = (
    "QTableWidget { alternate-background-color: #2a2a30; background-color: #1e1e22; "
    "color: #e0e0e0; gridline-color: #3a3a42; font-size: 11px; } "
    "QHeaderView::section { background-color: #333340; color: #e0e0e0; "
    "font-weight: bold; padding: 4px; border: 1px solid #3a3a42; }"
)

_INNER_TAB_STYLE = (
    "QTabBar::tab { min-width: 90px; padding: 5px 14px; font-size: 11px; }"
)


# ── Utilities ─────────────────────────────────────────────────────────────

def _safe_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        f = float(v)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError):
        return None


def _fmt(v: Any, decimals: int = 4) -> str:
    f = _safe_float(v)
    if f is None:
        return "\u2014"
    return ("{:." + str(decimals) + "f}").format(f)


_XBAR_STYLE = (
    "QLineEdit { background: #25252c; color: #e0e0e0; border: 1px solid #3a3a42; "
    "border-radius: 3px; padding: 2px 6px; font-size: 11px; min-width: 70px; max-width: 100px; }"
    "QLineEdit:focus { border: 1px solid #4fc3f7; }"
)


class _XAxisRangeBar(QWidget):
    """Compact bar with X-axis Min / Max editable fields and a Reset button.

    Placed below a pyqtgraph PlotWidget. Typing a value and pressing Enter
    (or tabbing away) applies the new X range to the graph.
    """

    def __init__(self, plot_widget: Any, parent: Any = None) -> None:
        super().__init__(parent)
        self._pw = plot_widget
        lay = QHBoxLayout(self)
        lay.setContentsMargins(4, 2, 4, 2)
        lay.setSpacing(6)

        lbl_style = "color: #b0bec5; font-size: 11px; font-weight: bold;"
        validator = QDoubleValidator()
        validator.setNotation(QDoubleValidator.Notation.StandardNotation)

        lay.addStretch()
        lmin = QLabel("X Min:")
        lmin.setStyleSheet(lbl_style)
        lay.addWidget(lmin)
        self._edit_min = QLineEdit()
        self._edit_min.setStyleSheet(_XBAR_STYLE)
        self._edit_min.setValidator(validator)
        self._edit_min.setPlaceholderText("auto")
        self._edit_min.setToolTip("Type a value and press Enter to set the X-axis start")
        self._edit_min.editingFinished.connect(self._apply_range)
        lay.addWidget(self._edit_min)

        lmax = QLabel("X Max:")
        lmax.setStyleSheet(lbl_style)
        lay.addWidget(lmax)
        self._edit_max = QLineEdit()
        self._edit_max.setStyleSheet(_XBAR_STYLE)
        self._edit_max.setValidator(validator)
        self._edit_max.setPlaceholderText("auto")
        self._edit_max.setToolTip("Type a value and press Enter to set the X-axis end")
        self._edit_max.editingFinished.connect(self._apply_range)
        lay.addWidget(self._edit_max)

        reset_btn = QPushButton("Reset")
        reset_btn.setFixedHeight(22)
        reset_btn.setStyleSheet(
            "QPushButton { background: #333340; color: #e0e0e0; border: 1px solid #3a3a42; "
            "border-radius: 3px; padding: 2px 10px; font-size: 11px; }"
            "QPushButton:hover { background: #43434d; }"
        )
        reset_btn.setToolTip("Reset X-axis to show all data (auto-range)")
        reset_btn.clicked.connect(self._reset_range)
        lay.addWidget(reset_btn)
        lay.addStretch()

    def _get_viewbox(self) -> Any:
        try:
            return self._pw.getPlotItem().getViewBox()
        except Exception:
            return None

    def _apply_range(self) -> None:
        vb = self._get_viewbox()
        if vb is None:
            return
        t_min = self._edit_min.text().strip()
        t_max = self._edit_max.text().strip()
        try:
            v_min = float(t_min) if t_min else None
        except ValueError:
            v_min = None
        try:
            v_max = float(t_max) if t_max else None
        except ValueError:
            v_max = None

        if v_min is not None and v_max is not None and v_min < v_max:
            vb.setXRange(v_min, v_max, padding=0.01)
            vb.disableAutoRange(axis="x")
        elif v_min is not None and v_max is None:
            cur = vb.viewRange()
            vb.setXRange(v_min, cur[0][1], padding=0.01)
            vb.disableAutoRange(axis="x")
        elif v_max is not None and v_min is None:
            cur = vb.viewRange()
            vb.setXRange(cur[0][0], v_max, padding=0.01)
            vb.disableAutoRange(axis="x")

    def _reset_range(self) -> None:
        self._edit_min.clear()
        self._edit_max.clear()
        vb = self._get_viewbox()
        if vb is not None:
            vb.enableAutoRange(axis="x")


def _white_plot() -> Any:
    if not _PG:
        return QLabel("pyqtgraph not available")
    pw = pg.PlotWidget()
    pw.setBackground("w")
    pi = pw.getPlotItem()
    pi.getViewBox().setBackgroundColor((255, 255, 255))
    pi.showGrid(x=True, y=True, alpha=0.45)
    pen = pg.mkPen(color="#333333", width=1)
    for ax_name in ("left", "bottom"):
        ax = pi.getAxis(ax_name)
        ax.setPen(pen)
        ax.setTextPen(pen)
    return pw


def _valid_pairs(x_list: list, y_list: list) -> tuple:
    vx, vy = [], []
    for xi, yi in zip(x_list, y_list):
        if xi is not None and yi is not None:
            vx.append(xi)
            vy.append(yi)
    return vx, vy


def _make_log_widget(text: str = "") -> QPlainTextEdit:
    te = QPlainTextEdit()
    te.setReadOnly(True)
    te.setPlainText(text)
    te.setStyleSheet(_LOG_STYLE)
    return te


def _minimal_saved_record_banner() -> QLabel:
    """Shown when only a placeholder or empty sweep was persisted for this test."""
    lab = QLabel(
        "Minimal saved record — no sweep curves in this file. See Summary / fail reasons, "
        "or re-run if the step stopped early."
    )
    lab.setWordWrap(True)
    lab.setStyleSheet(
        "color: #ffe082; font-size: 11px; padding: 6px; background: #3d3518; border-radius: 4px;"
    )
    return lab


def _recipe_snapshot_from_data(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Full recipe dict saved under ``session.json`` → ``recipe`` (newer sessions only)."""
    sess = data.get("session")
    if not isinstance(sess, dict):
        return None
    r = sess.get("recipe")
    return r if isinstance(r, dict) and r else None


def _recipe_flat_rows(d: Any, prefix: str = "", max_rows: int = 2000) -> List[tuple]:
    """Flatten nested recipe dict into (path, value) rows for read-only display (no code — names + values only)."""
    rows: List[tuple] = []
    if len(rows) >= max_rows or d is None:
        return rows
    if isinstance(d, dict):
        for k in sorted(d.keys(), key=lambda x: str(x).lower()):
            if len(rows) >= max_rows:
                break
            path = "{} → {}".format(prefix, k) if prefix else str(k)
            v = d[k]
            if isinstance(v, dict) and v:
                rows.extend(_recipe_flat_rows(v, path, max_rows - len(rows)))
            elif isinstance(v, list):
                if not v:
                    rows.append((path, "[]"))
                elif all(not isinstance(x, (dict, list)) for x in v):
                    shown = ", ".join(str(x) for x in v[:40])
                    if len(v) > 40:
                        shown += " … ({} total)".format(len(v))
                    rows.append((path, shown))
                else:
                    rows.append((path, "[{} nested items]".format(len(v))))
            else:
                rows.append((path, "" if v is None else str(v)))
    return rows


def _ts_recipe_block(recipe: Dict[str, Any], slot: int) -> Dict[str, Any]:
    """Same key resolution as stability_process._get_block (OPERATIONS Temperature Stability N)."""
    op = recipe.get("OPERATIONS") or recipe.get("operations") or {}
    if not isinstance(op, dict):
        return {}
    keys = (
        "Temperature Stability {}".format(slot),
        "Temperature_Stability_{}".format(slot),
        "TEMPERATURE_STABILITY_{}".format(slot),
        "TS{}".format(slot),
        "ts{}".format(slot),
    )
    for k in keys:
        b = op.get(k)
        if isinstance(b, dict) and b:
            return b
    return {}


def _recipe_rows_temperature_stability(recipe: Dict[str, Any], slot: int) -> List[tuple]:
    """Flat name → value rows for one TS slot only (min/max/initial/step, limits, Ando, etc.)."""
    block = _ts_recipe_block(recipe, slot)
    if not block:
        return []
    label = "Temperature Stability {}".format(slot)
    return _recipe_flat_rows(block, prefix="OPERATIONS → {}".format(label))


def _make_recipe_view(recipe: Optional[Dict[str, Any]], ts_slot: Optional[int] = None) -> QWidget:
    """Read-only RCP as parameter name + value table (left column above the status log).

    For Temperature Stability tabs, ``ts_slot`` 1 or 2 limits rows to that OPERATIONS block
    (initial/min/max temp, step, Ando, limits, …) instead of the full recipe (which sorts GENERAL first).
    """
    wrap = QWidget()
    vl = QVBoxLayout(wrap)
    vl.setContentsMargins(2, 2, 2, 2)
    if ts_slot is not None:
        lbl = QLabel("RCP / Recipe — Temperature Stability {} (name → value)".format(ts_slot))
    else:
        lbl = QLabel("RCP / Recipe (name → value)")
    lbl.setStyleSheet("color: #81c784; font-weight: bold; font-size: 12px; margin-bottom: 2px;")
    vl.addWidget(lbl)
    if not recipe:
        te = QPlainTextEdit()
        te.setReadOnly(True)
        te.setMinimumHeight(100)
        te.setStyleSheet(_LOG_STYLE)
        te.setPlainText(
            "(No recipe snapshot in this session. Older result folders may omit it; "
            "re-run and save with a current app version to embed RCP in session.json.)"
        )
        vl.addWidget(te)
        return wrap
    if ts_slot is not None:
        flat = _recipe_rows_temperature_stability(recipe, ts_slot)
        if not flat:
            flat = [
                (
                    "—",
                    "No OPERATIONS → Temperature Stability {} block in embedded recipe. "
                    "Re-save the session after a run, or check the Summary tab full RCP table.".format(ts_slot),
                )
            ]
    else:
        flat = _recipe_flat_rows(recipe)
    tbl = QTableWidget(len(flat), 2)
    tbl.setHorizontalHeaderLabels(["Parameter", "Value"])
    _apply_table_chrome(tbl)
    for i, (pn, val) in enumerate(flat):
        pi = QTableWidgetItem(pn)
        pi.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        tbl.setItem(i, 0, pi)
        vi = QTableWidgetItem(val)
        vi.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        vi.setToolTip(val if len(val) < 2000 else val[:1997] + "…")
        tbl.setItem(i, 1, vi)
    _finish_recipe_parameter_table(tbl)
    tbl.setMinimumHeight(160)
    vl.addWidget(tbl)
    return wrap


def _test_sequence_name_to_stem(step_name: str) -> Optional[str]:
    """Map one TEST_SEQUENCE entry to a result file stem (liv / per / spectrum / ts1 / ts2)."""
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


def _default_tab_title(stem: str) -> str:
    return {
        "liv": "LIV",
        "per": "PER",
        "spectrum": "Spectrum",
        "ts1": "Temp Stability 1",
        "ts2": "Temp Stability 2",
    }.get(stem, stem.upper())


def _ordered_test_tabs_plan(data: Dict[str, Any]) -> List[tuple]:
    """(stem, tab_title) in run order, then any result files not listed in session sequence."""
    session = data.get("session") if isinstance(data.get("session"), dict) else {}
    seq = session.get("test_sequence") or session.get("TestSequence") or []
    if not isinstance(seq, list):
        seq = []
    ordered: List[tuple] = []
    seen: set = set()
    for step in seq:
        label = str(step).strip()
        stem = _test_sequence_name_to_stem(label)
        if stem is None or stem in seen:
            continue
        seen.add(stem)
        title = label if len(label) <= 48 else (label[:45] + "…")
        ordered.append((stem, title))
    for stem in ("liv", "per", "spectrum", "ts1", "ts2"):
        if stem in seen:
            continue
        blob = data.get(stem)
        # Any dict payload (including placeholders) gets a tab — do not require len(blob) > 0.
        if isinstance(blob, dict):
            ordered.append((stem, _default_tab_title(stem)))
            seen.add(stem)
    return ordered


def _build_summary_tab(data: Dict[str, Any]) -> QWidget:
    """Session overview + one table of all numeric/pass rows from every test present."""
    inner = QWidget()
    vl = QVBoxLayout(inner)
    vl.setContentsMargins(8, 8, 8, 8)
    session = data.get("session") if isinstance(data.get("session"), dict) else {}
    rn = session.get("recipe_name", "?")
    ts = session.get("timestamp", "?")
    seq = session.get("test_sequence") or session.get("TestSequence") or []
    seq_s = ", ".join(str(x) for x in seq) if isinstance(seq, list) else str(seq)
    stopped = session.get("stopped_by_user", False)
    passed = session.get("overall_passed")
    if stopped:
        st = "ABORTED"
    elif passed is True:
        st = "PASS"
    elif passed is False:
        st = "FAIL"
    else:
        st = "UNKNOWN"
    head = QLabel(
        "<b>Recipe:</b> {} &nbsp;|&nbsp; <b>Time:</b> {} &nbsp;|&nbsp; <b>Overall:</b> {}<br>"
        "<b>Sequence:</b> {}".format(rn, ts, st, seq_s or "—")
    )
    head.setWordWrap(True)
    head.setStyleSheet("color: #e0e0e0; font-size: 12px;")
    vl.addWidget(head)
    rows: List[tuple] = []
    rows.append(("Session", "Recipe name", str(rn)))
    rows.append(("Session", "Timestamp", str(ts)))
    rows.append(("Session", "Overall", st))
    rows.append(("Session", "Test sequence", seq_s or "—"))
    liv = data.get("liv")
    if isinstance(liv, dict):
        _add_liv_rows(rows, liv)
    per = data.get("per")
    if isinstance(per, dict):
        _add_per_rows(rows, per)
    spec = data.get("spectrum")
    if isinstance(spec, dict):
        _add_spectrum_rows(rows, spec)
    for slot, stem in ((1, "ts1"), (2, "ts2")):
        tsb = data.get(stem)
        if isinstance(tsb, dict):
            _add_ts_rows(rows, tsb, slot)
    vl.addWidget(QLabel("<b>All tests — parameters</b>"))
    vl.addWidget(_make_table(rows))
    recipe = _recipe_snapshot_from_data(data)
    if recipe:
        vl.addWidget(QLabel("<b>RCP / recipe — parameters</b>"))
        rrows = _recipe_flat_rows(recipe)
        rtbl = QTableWidget(len(rrows), 2)
        rtbl.setHorizontalHeaderLabels(["Parameter", "Value"])
        _apply_table_chrome(rtbl)
        for i, (pn, val) in enumerate(rrows):
            a = QTableWidgetItem(pn)
            a.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            rtbl.setItem(i, 0, a)
            b = QTableWidgetItem(val)
            b.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            rtbl.setItem(i, 1, b)
        _finish_recipe_parameter_table(rtbl)
        rtbl.setMinimumHeight(220)
        vl.addWidget(rtbl)
    vl.addStretch()
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setWidget(inner)
    w = QWidget()
    QVBoxLayout(w).addWidget(scroll)
    return w


def _build_empty_summary_tab() -> QWidget:
    w = QWidget()
    vl = QVBoxLayout(w)
    vl.setContentsMargins(12, 12, 12, 12)
    lab = QLabel("Load a saved result to see a session summary, RCP parameters, and every test in the sequence.")
    lab.setWordWrap(True)
    lab.setStyleSheet("color: #9e9e9e; font-size: 12px;")
    vl.addWidget(lab)
    vl.addStretch()
    return w


def _add_fail_reasons(layout: Any, d: Dict[str, Any]) -> None:
    reasons = d.get("fail_reasons", [])
    if isinstance(reasons, str):
        reasons = [reasons] if reasons.strip() else []
    elif not isinstance(reasons, (list, tuple)):
        reasons = [str(reasons)] if reasons is not None else []
    if reasons:
        lbl = QLabel("Fail Reasons:")
        lbl.setStyleSheet("color: #ef9a9a; font-weight: bold; margin-top: 4px;")
        layout.addWidget(lbl)
        for r in reasons:
            rl = QLabel("  \u2022 " + str(r))
            rl.setStyleSheet("color: #ef9a9a;")
            rl.setWordWrap(True)
            layout.addWidget(rl)


def _apply_table_chrome(tbl: QTableWidget) -> None:
    """Alternating rows, stylesheet, selection — without touching column resize (call after rows exist when sizing matters)."""
    tbl.setAlternatingRowColors(True)
    tbl.setStyleSheet(_TABLE_STYLE)
    tbl.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    tbl.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    tbl.verticalHeader().setVisible(False)


def _style_grid_table(tbl: QTableWidget) -> None:
    """Apply consistent left-aligned, compact styling to any grid table."""
    _apply_table_chrome(tbl)
    hdr = tbl.horizontalHeader()
    hdr.setStretchLastSection(False)
    for ci in range(tbl.columnCount()):
        hdr.setSectionResizeMode(ci, QHeaderView.ResizeMode.ResizeToContents)


def _finish_recipe_parameter_table(tbl: QTableWidget) -> None:
    """After Parameter/Value cells exist: size column 0 to content, give column 1 the rest (never collapse Value)."""
    hdr = tbl.horizontalHeader()
    if hdr is None:
        return
    hdr.setMinimumSectionSize(64)
    hdr.setStretchLastSection(True)
    hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
    tbl.resizeColumnToContents(0)
    hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
    hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)


def _make_empty_grid(headers: List[str]) -> QTableWidget:
    """Create an empty table with given column headers, properly styled."""
    tbl = QTableWidget(0, len(headers))
    tbl.setHorizontalHeaderLabels(headers)
    _style_grid_table(tbl)
    return tbl


def _make_table(rows: List[tuple]) -> QTableWidget:
    table = QTableWidget(len(rows), 3)
    table.setHorizontalHeaderLabels(["Test", "Parameter", "Value"])
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setAlternatingRowColors(True)
    table.setStyleSheet(_TABLE_STYLE)
    hdr = table.horizontalHeader()
    if hdr is not None:
        hdr.setStretchLastSection(True)
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
    for i, (test, param, val) in enumerate(rows):
        t_item = QTableWidgetItem(test)
        t_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        table.setItem(i, 0, t_item)
        p_item = QTableWidgetItem(param)
        p_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        table.setItem(i, 1, p_item)
        v_item = QTableWidgetItem(val)
        v_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        if val == "PASS":
            v_item.setForeground(QColor(_PASS_COLOR))
        elif val == "FAIL":
            v_item.setForeground(QColor(_FAIL_COLOR))
        table.setItem(i, 2, v_item)
    return table


def _filter_log(full_log: Any, prefix: str) -> str:
    """Extract log lines for a specific test prefix, e.g. '[LIV]'."""
    if not isinstance(full_log, str):
        full_log = str(full_log or "")
    if not full_log:
        return ""
    lines = []
    tag = "[{}]".format(prefix)
    for line in full_log.splitlines():
        if tag in line or "[SEQ]" in line:
            lines.append(line)
    return "\n".join(lines) if lines else "(No log lines for {})".format(prefix)


# ── Password Dialog ───────────────────────────────────────────────────────

class _PasswordDialog(QDialog):
    def __init__(self, parent: Any = None):
        super().__init__(parent)
        self.setWindowTitle("Data View \u2014 Password")
        self.setFixedSize(340, 140)
        self.setPalette(get_dark_palette())
        self.setStyleSheet(main_stylesheet())
        set_dark_title_bar(self)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Enter password to access Data View:"))
        self._input = QLineEdit()
        self._input.setEchoMode(QLineEdit.EchoMode.Password)
        self._input.returnPressed.connect(self._check)
        layout.addWidget(self._input)
        btn = QPushButton("OK")
        btn.clicked.connect(self._check)
        layout.addWidget(btn)
        self._accepted = False

    def _check(self) -> None:
        if self._input.text() == _PASSWORD:
            self._accepted = True
            self.accept()
        else:
            QMessageBox.warning(self, "Wrong password", "Incorrect password. Try again.")
            self._input.clear()
            self._input.setFocus()

    @property
    def authenticated(self) -> bool:
        return self._accepted


# ── Session Picker ────────────────────────────────────────────────────────

class _SessionPicker(QDialog):
    def __init__(self, parent: Any = None):
        super().__init__(parent)
        self.setWindowTitle("Load Result")
        self.setMinimumSize(650, 420)
        self.setPalette(get_dark_palette())
        self.setStyleSheet(main_stylesheet())
        set_dark_title_bar(self)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Select a saved test result to load:"))
        self._list = QListWidget()
        self._list.setStyleSheet("QListWidget { font-size: 12px; }")
        self._list.itemDoubleClicked.connect(lambda _: self.accept())
        layout.addWidget(self._list)
        btn_row = QHBoxLayout()
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setToolTip("Reload the list from the results folder (e.g. after a new run saved).")
        refresh_btn.clicked.connect(self._repopulate_sessions)
        btn_row.addWidget(refresh_btn)
        btn_row.addStretch()
        open_btn = QPushButton("Load")
        open_btn.setMinimumWidth(100)
        open_btn.clicked.connect(self.accept)
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setMinimumWidth(100)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        btn_row.addWidget(open_btn)
        layout.addLayout(btn_row)

        self._sessions: List[Dict[str, Any]] = []
        self._repopulate_sessions()

    def _repopulate_sessions(self) -> None:
        self._list.clear()
        self._sessions = list_saved_sessions()
        if not self._sessions:
            self._list.addItem(QListWidgetItem("(No saved results found in the project results folder.)"))
            return
        for s in self._sessions:
            ov = s.get("overall_passed")
            if ov is True:
                status = "PASS"
                fg = QColor(_PASS_COLOR)
            elif s.get("stopped_by_user"):
                status = "ABORTED"
                fg = QColor(_ABORTED_COLOR)
            elif ov is False:
                status = "FAIL"
                fg = QColor(_FAIL_COLOR)
            else:
                status = "UNKNOWN"
                fg = QColor(_UNKNOWN_COLOR)
            text = "{} \u2014 {} \u2014 {} \u2014 [{}]".format(
                s.get("recipe_name", "?"),
                s.get("timestamp", "?"),
                status,
                ", ".join(str(t).upper() for t in s.get("tests", [])),
            )
            item = QListWidgetItem(text)
            item.setForeground(fg)
            self._list.addItem(item)
        self._list.setCurrentRow(0)

    def selected_folder(self) -> Optional[str]:
        row = self._list.currentRow()
        if 0 <= row < len(self._sessions):
            return self._sessions[row].get("folder")
        return None


# ── Wrapped test tab: inner QTabWidget with Plot + Table sub-tabs ─────────

def _wrap_test_tab(plot_widget: QWidget, table_widget: QWidget) -> QTabWidget:
    """Each test's outer tab contains an inner QTabWidget with Plot and Table."""
    inner = QTabWidget()
    inner.setStyleSheet(_INNER_TAB_STYLE)
    inner.addTab(plot_widget, "Plot")
    inner.addTab(table_widget, "Table")
    return inner


# ── Plot sub-tab: left = RCP (top) + status log (bottom); right = graph + info ─

def _make_plot_subtab(
    recipe: Optional[Dict[str, Any]],
    log_widget: QPlainTextEdit,
    graph_and_info: QWidget,
    ts_slot: Optional[int] = None,
) -> QWidget:
    outer = QSplitter(Qt.Orientation.Horizontal)
    left_col = QSplitter(Qt.Orientation.Vertical)
    left_col.addWidget(_make_recipe_view(recipe, ts_slot=ts_slot))
    log_container = QWidget()
    lc_layout = QVBoxLayout(log_container)
    lc_layout.setContentsMargins(2, 2, 2, 2)
    lbl = QLabel("Status Log")
    lbl.setStyleSheet("color: #4fc3f7; font-weight: bold; font-size: 12px; margin-bottom: 2px;")
    lc_layout.addWidget(lbl)
    lc_layout.addWidget(log_widget)
    left_col.addWidget(log_container)
    left_col.setStretchFactor(0, 1)
    left_col.setStretchFactor(1, 1)
    try:
        left_col.setSizes([320, 320])
    except Exception:
        pass
    outer.addWidget(left_col)
    outer.addWidget(graph_and_info)
    outer.setStretchFactor(0, 2)
    outer.setStretchFactor(1, 3)
    w = QWidget()
    QVBoxLayout(w).addWidget(outer)
    return w


def _make_graph_and_info(graph_widget: Any, info_widget: QWidget) -> QWidget:
    splitter = QSplitter(Qt.Orientation.Vertical)
    splitter.addWidget(graph_widget)
    splitter.addWidget(info_widget)
    splitter.setStretchFactor(0, 3)
    splitter.setStretchFactor(1, 1)
    w = QWidget()
    QVBoxLayout(w).addWidget(splitter)
    return w


# ══════════════════════════════════════════════════════════════════════════
# EMPTY tabs (before data loaded)
# ══════════════════════════════════════════════════════════════════════════

def _empty_info(rows: List[str]) -> QWidget:
    w = QWidget()
    il = QVBoxLayout(w)
    il.setContentsMargins(8, 8, 8, 8)
    s = QLabel("Result: \u2014")
    s.setStyleSheet("font-weight: bold; font-size: 14px; color: #616161;")
    il.addWidget(s)
    form = QFormLayout()
    for r in rows:
        v = QLabel("\u2014")
        v.setStyleSheet("color: #616161;")
        form.addRow(r + ":", v)
    il.addLayout(form)
    il.addStretch()
    return w


def _empty_graph(x_label: str, y_label: str) -> QWidget:
    w = QWidget()
    gl = QVBoxLayout(w)
    gl.setContentsMargins(4, 4, 4, 4)
    if _PG:
        pw = _white_plot()
        pi = pw.getPlotItem()
        pi.setLabel("bottom", x_label, color="#333")
        pi.setLabel("left", y_label, color="#333")
        gl.addWidget(pw)
    else:
        gl.addWidget(QLabel("pyqtgraph not available"))
    return w


def _build_empty_test_tab(
    x_label: str,
    y_label: str,
    info_rows: List[str],
    table_headers: Optional[List[str]] = None,
    recipe: Optional[Dict[str, Any]] = None,
    ts_slot: Optional[int] = None,
) -> QTabWidget:
    graph_w = _empty_graph(x_label, y_label)
    info_w = _empty_info(info_rows)
    gi = _make_graph_and_info(graph_w, info_w)
    log_w = _make_log_widget("(Load a result to view)")
    plot_tab = _make_plot_subtab(recipe, log_w, gi, ts_slot=ts_slot)
    table_tab = QWidget()
    hdrs = table_headers or ["#", "Parameter", "Value"]
    QVBoxLayout(table_tab).addWidget(_make_empty_grid(hdrs))
    return _wrap_test_tab(plot_tab, table_tab)


_LIV_TABLE_HEADERS = ["#", "Current (mA)", "Power (mW)", "Voltage (V)", "PD (\u00b5A)"]
_PER_TABLE_HEADERS = ["#", "Angle (\u00b0)", "Power (mW)"]
_SPEC_TABLE_HEADERS = ["#", "Wavelength (nm)", "Level (dBm)"]
_TS_TABLE_HEADERS = ["#", "Status", "Ramp", "Temp (\u00b0C)", "Peak \u03bb (nm)", "FWHM (nm)",
                     "SMSR (dB)", "Peak Lvl (dBm)", "Thorlabs (mW)"]
_TS_SMSR_ANDO_HEADER = "smsrando"


def _build_empty_liv(recipe: Optional[Dict[str, Any]] = None) -> QTabWidget:
    return _build_empty_test_tab("Current (mA)", "Power (mW)", [
        "Threshold Current (mA)", "Slope Efficiency (W/A)",
        "Power @ Rated Current (mW)", "Current @ Rated Power (mA)",
        "Thorlabs Avg Power (mW)", "TEC Temp Range"],
        table_headers=_LIV_TABLE_HEADERS,
        recipe=recipe)


def _build_empty_per(recipe: Optional[Dict[str, Any]] = None) -> QTabWidget:
    return _build_empty_test_tab("Angle (\u00b0)", "Power (mW)", [
        "PER (dB)", "Max Power (mW)", "Min Power (mW)", "Max Angle (\u00b0)"],
        table_headers=_PER_TABLE_HEADERS,
        recipe=recipe)


def _build_empty_spectrum(recipe: Optional[Dict[str, Any]] = None) -> QTabWidget:
    return _build_empty_test_tab("Wavelength (nm)", "Level (dBm)", [
        "Peak Wavelength (nm)", "Peak Level (dBm)", "FWHM (nm)",
        "SMSR (dB)", "Center (nm)", "Span (nm)"],
        table_headers=_SPEC_TABLE_HEADERS,
        recipe=recipe)


def _build_empty_ts(slot: int, recipe: Optional[Dict[str, Any]] = None) -> QTabWidget:
    return _build_empty_test_tab("Temperature (\u00b0C)", "Peak \u03bb (nm)", [
        "Slot", "Step Label", "SMSR Correction"],
        table_headers=_TS_TABLE_HEADERS,
        recipe=recipe,
        ts_slot=slot)


# ══════════════════════════════════════════════════════════════════════════
# FILLED tabs (after data loaded)
# ══════════════════════════════════════════════════════════════════════════

def _build_liv_tab(data: Dict[str, Any], enlarge_host: Any = None) -> QTabWidget:
    liv = data.get("liv")
    if not isinstance(liv, dict):
        return _build_empty_liv(_recipe_snapshot_from_data(data))

    currents = liv.get("current_array", [])
    powers = liv.get("power_array") or liv.get("gentec_power_array", [])
    voltages = liv.get("voltage_array", [])
    pds = liv.get("pd_array", [])

    graph_w = QWidget()
    gl = QVBoxLayout(graph_w)
    gl.setContentsMargins(4, 4, 4, 4)
    if liv.get("result_placeholder") or (
        not currents and not powers and not voltages and not pds
    ):
        gl.addWidget(_minimal_saved_record_banner())
    _liv_pw = None
    if _PG and _LIV_PLOT_AVAILABLE:
        bundle = build_liv_process_plot()
        if bundle is not None:
            n = min(len(currents), len(powers))
            if n > 0:
                bundle.power_curve.setData(currents[:n], powers[:n])
            nv = min(len(currents), len(voltages))
            if nv > 0:
                bundle.voltage_curve.setData(currents[:nv], voltages[:nv])
            np_ = min(len(currents), len(pds))
            if np_ > 0:
                bundle.pd_curve.setData(currents[:np_], pds[:np_])
            if n > 0:
                liv_autorange_secondary_axes(
                    bundle.vb_voltage, bundle.vb_pd,
                    currents[:n], voltages[:nv] if nv > 0 else [],
                    pds[:np_] if np_ > 0 else [],
                )
            gl.addWidget(bundle.series_checkbox_row, 0)
            gl.addWidget(bundle.plot_widget, 1)
            _liv_pw = bundle.plot_widget
        else:
            gl.addWidget(QLabel("Could not build LIV plot."))
    elif _PG:
        pw = _white_plot()
        pi = pw.getPlotItem()
        pi.setLabel("bottom", "Current (mA)", color="#333")
        pi.setLabel("left", "Power (mW)", color="#333")
        n = min(len(currents), len(powers))
        if n > 0:
            pi.plot(currents[:n], powers[:n], pen=pg.mkPen("#d32f2f", width=2))
        gl.addWidget(pw)
        _liv_pw = pw
    else:
        gl.addWidget(QLabel("pyqtgraph not available"))
    if _liv_pw is not None:
        gl.addWidget(_XAxisRangeBar(_liv_pw))
    _maybe_install_data_view_plot_enlarge(enlarge_host, _liv_pw, "LIV — Data View")

    info_w = QWidget()
    il = QVBoxLayout(info_w)
    il.setContentsMargins(8, 8, 8, 8)
    passed = liv.get("passed", False)
    s = QLabel("Result: {}".format("PASS" if passed else "FAIL"))
    s.setStyleSheet("font-weight: bold; font-size: 14px; color: {};".format(
        _PASS_COLOR if passed else _FAIL_COLOR))
    il.addWidget(s)
    form = QFormLayout()
    form.addRow("Threshold Current (mA):", QLabel(_fmt(liv.get("threshold_current"), 2)))
    form.addRow("Slope Efficiency (W/A):", QLabel(_fmt(liv.get("slope_efficiency"), 4)))
    form.addRow("Power @ Rated Current (mW):", QLabel(_fmt(liv.get("power_at_rated_current"), 4)))
    form.addRow("Current @ Rated Power (mA):", QLabel(_fmt(liv.get("current_at_rated_power"), 2)))
    form.addRow("Thorlabs Avg Power (mW):", QLabel(_fmt(liv.get("thorlabs_average_power_mw"), 4)))
    form.addRow("PD @ Rated Current (\u00b5A):", QLabel(_fmt(liv.get("pd_at_rated_current"), 4)))
    form.addRow("Voltage @ Rated Current (V):", QLabel(_fmt(liv.get("voltage_at_rated_current_V"), 4)))
    form.addRow("TEC Temp Range:", QLabel("{} \u2014 {} \u00b0C".format(
        _fmt(liv.get("tec_temp_min"), 2), _fmt(liv.get("tec_temp_max"), 2))))
    form.addRow("Data Points:", QLabel(str(len(currents))))
    il.addLayout(form)
    _add_fail_reasons(il, liv)
    il.addStretch()

    gi = _make_graph_and_info(graph_w, info_w)
    log_w = _make_log_widget(_filter_log(data.get("log", ""), "LIV"))
    plot_tab = _make_plot_subtab(_recipe_snapshot_from_data(data), log_w, gi)

    table_tab = QWidget()
    QVBoxLayout(table_tab).addWidget(_make_liv_grid_table(liv))

    return _wrap_test_tab(plot_tab, table_tab)


def _build_per_tab(data: Dict[str, Any], enlarge_host: Any = None) -> QTabWidget:
    per = data.get("per")
    if not isinstance(per, dict):
        return _build_empty_per(_recipe_snapshot_from_data(data))

    angles = per.get("positions_deg", [])
    powers = per.get("powers_mw", [])

    graph_w = QWidget()
    gl = QVBoxLayout(graph_w)
    gl.setContentsMargins(4, 4, 4, 4)
    if per.get("result_placeholder") or (not angles and not powers):
        gl.addWidget(_minimal_saved_record_banner())
    _per_pw = None
    if _PG:
        pw = _white_plot()
        pi = pw.getPlotItem()
        try:
            pi.setTitle("PER \u2014 Power (mW) vs Angle (\u00b0)", color="#333333")
        except Exception:
            pass
        pi.setLabel("bottom", "Angle (\u00b0)", color="#333")
        pi.setLabel("left", "Power (mW)", color="#333")
        _c_per = "#1f77b4"
        if _SERIES_CB_AVAILABLE:
            _c_per = PER_SERIES_COLORS[0]
        n = min(len(angles), len(powers))
        curve = None
        if n > 0:
            curve = pi.plot(angles[:n], powers[:n], pen=pg.mkPen(_c_per, width=2),
                            symbol="o", symbolSize=4, symbolBrush=_c_per, symbolPen=pg.mkPen(_c_per))
        if _SERIES_CB_AVAILABLE and curve is not None:
            per_spec = [{"curve": curve}]
            cb_row, _ = make_series_checkbox_row(per_spec, PER_SERIES_LABELS,
                                                  legend=None, color_swatches=PER_SERIES_COLORS)
            gl.addWidget(cb_row, 0)
            try:
                compact_simple_xy_plot_axes(pi, pw)
                freeze_plot_navigation(pi)
            except Exception:
                pass
        gl.addWidget(pw, 1)
        _per_pw = pw
    else:
        gl.addWidget(QLabel("pyqtgraph not available"))
    if _per_pw is not None:
        gl.addWidget(_XAxisRangeBar(_per_pw))
    _maybe_install_data_view_plot_enlarge(enlarge_host, _per_pw, "PER — Data View")

    info_w = QWidget()
    il = QVBoxLayout(info_w)
    il.setContentsMargins(8, 8, 8, 8)
    passed = per.get("passed", False)
    s = QLabel("Result: {}".format("PASS" if passed else "FAIL"))
    s.setStyleSheet("font-weight: bold; font-size: 14px; color: {};".format(
        _PASS_COLOR if passed else _FAIL_COLOR))
    il.addWidget(s)
    form = QFormLayout()
    form.addRow("PER (dB):", QLabel(_fmt(per.get("per_db"), 2)))
    form.addRow("Max Power (mW):", QLabel(_fmt(per.get("max_power"), 4)))
    form.addRow("Min Power (mW):", QLabel(_fmt(per.get("min_power"), 4)))
    form.addRow("Max Angle (\u00b0):", QLabel(_fmt(per.get("max_angle"), 2)))
    form.addRow("Data Points:", QLabel(str(len(angles))))
    il.addLayout(form)
    _add_fail_reasons(il, per)
    il.addStretch()

    gi = _make_graph_and_info(graph_w, info_w)
    log_w = _make_log_widget(_filter_log(data.get("log", ""), "PER"))
    plot_tab = _make_plot_subtab(_recipe_snapshot_from_data(data), log_w, gi)

    table_tab = QWidget()
    QVBoxLayout(table_tab).addWidget(_make_per_grid_table(per))

    return _wrap_test_tab(plot_tab, table_tab)


def _build_spectrum_tab(data: Dict[str, Any], enlarge_host: Any = None) -> QTabWidget:
    spec = data.get("spectrum")
    if not isinstance(spec, dict):
        return _build_empty_spectrum(_recipe_snapshot_from_data(data))

    graph_w = QWidget()
    gl = QVBoxLayout(graph_w)
    gl.setContentsMargins(4, 4, 4, 4)
    w1_chk = spec.get("first_sweep_wdata", [])
    l1_chk = spec.get("first_sweep_ldata", [])
    w2_chk = spec.get("second_sweep_wdata", [])
    l2_chk = spec.get("second_sweep_ldata", [])
    if spec.get("result_placeholder") or (
        not (w1_chk and l1_chk) and not (w2_chk and l2_chk)
    ):
        gl.addWidget(_minimal_saved_record_banner())
    _spec_pw = None
    if _PG:
        pw = _white_plot()
        pi = pw.getPlotItem()
        try:
            pi.setTitle("Spectrum \u2014 Level (dBm) vs Wavelength (nm)", color="#333333")
        except Exception:
            pass
        pi.setLabel("bottom", "Wavelength (nm)", color="#333")
        pi.setLabel("left", "Level (dBm)", color="#333")

        def _plot_trace(wd, ld, color, name):
            if not wd or not ld:
                return
            n = min(len(wd), len(ld))
            vw, vl = [], []
            for i in range(n):
                wf, lf = _safe_float(wd[i]), _safe_float(ld[i])
                if wf is not None and lf is not None:
                    vw.append(wf)
                    vl.append(lf)
            if vw:
                pi.plot(vw, vl, pen=pg.mkPen(color, width=2), name=name)

        w1 = spec.get("first_sweep_wdata", [])
        l1 = spec.get("first_sweep_ldata", [])
        w2 = spec.get("second_sweep_wdata", [])
        l2 = spec.get("second_sweep_ldata", [])
        if w2 and l2:
            _plot_trace(w1, l1, "#90a4ae", "Sweep 1")
            _plot_trace(w2, l2, "#6a1b9a", "Sweep 2 (final)")
        elif w1 and l1:
            _plot_trace(w1, l1, "#6a1b9a", "Spectrum")

        pk_wl = _safe_float(spec.get("peak_wavelength"))
        pk_lv = _safe_float(spec.get("peak_level_dbm"))
        if pk_wl is not None and pk_lv is not None:
            pi.plot([pk_wl], [pk_lv], pen=None, symbol="o", symbolSize=10,
                    symbolBrush=pg.mkBrush("#e53935"), symbolPen=pg.mkPen("#e53935", width=2),
                    name="Peak")

        if _SERIES_CB_AVAILABLE:
            try:
                compact_simple_xy_plot_axes(pi, pw)
                freeze_plot_navigation(pi)
            except Exception:
                pass
        gl.addWidget(pw, 1)
        _spec_pw = pw
    else:
        gl.addWidget(QLabel("pyqtgraph not available"))
    if _spec_pw is not None:
        gl.addWidget(_XAxisRangeBar(_spec_pw))
    _maybe_install_data_view_plot_enlarge(enlarge_host, _spec_pw, "Spectrum — Data View")

    info_w = QWidget()
    il = QVBoxLayout(info_w)
    il.setContentsMargins(8, 8, 8, 8)
    passed = spec.get("passed", False)
    s = QLabel("Result: {}".format("PASS" if passed else "FAIL"))
    s.setStyleSheet("font-weight: bold; font-size: 14px; color: {};".format(
        _PASS_COLOR if passed else _FAIL_COLOR))
    il.addWidget(s)
    form = QFormLayout()
    form.addRow("Peak Wavelength (nm):", QLabel(_fmt(spec.get("peak_wavelength"), 6)))
    form.addRow("Peak Level (dBm):", QLabel(_fmt(spec.get("peak_level_dbm"), 2)))
    form.addRow("FWHM (nm):", QLabel(_fmt(spec.get("fwhm"), 4)))
    form.addRow("SMSR (dB):", QLabel(_fmt(spec.get("smsr"), 2)))
    form.addRow("Center (nm):", QLabel(_fmt(spec.get("center_nm"), 4)))
    form.addRow("Span (nm):", QLabel(_fmt(spec.get("span_nm"), 2)))
    form.addRow("1st Sweep Pass:", QLabel("PASS" if spec.get("passed_first_sweep") else "FAIL"))
    il.addLayout(form)
    _add_fail_reasons(il, spec)
    il.addStretch()

    gi = _make_graph_and_info(graph_w, info_w)
    log_w = _make_log_widget(_filter_log(data.get("log", ""), "SPEC"))
    plot_tab = _make_plot_subtab(_recipe_snapshot_from_data(data), log_w, gi)

    table_tab = QWidget()
    QVBoxLayout(table_tab).addWidget(_make_spectrum_grid_table(spec))

    return _wrap_test_tab(plot_tab, table_tab)


class _SimpleNamespace:
    """Lightweight attribute container so stability_tab_apply_result can read dict data as attrs."""
    def __init__(self, d: dict):
        for k, v in d.items():
            setattr(self, k, v)


def _build_ts_tab(data: Dict[str, Any], slot: int, enlarge_host: Any = None) -> QTabWidget:
    key = "ts{}".format(slot)
    ts = data.get(key)
    if not isinstance(ts, dict):
        return _build_empty_ts(slot, _recipe_snapshot_from_data(data))

    graph_w = QWidget()
    gl = QVBoxLayout(graph_w)
    gl.setContentsMargins(4, 4, 4, 4)
    temps_chk = ts.get("temperature_c", [])
    if ts.get("result_placeholder") or not temps_chk:
        gl.addWidget(_minimal_saved_record_banner())
    _ts_pw = None
    if _PG and _TS_PLOT_AVAILABLE:
        title = "Temperature Stability {} — vs Temperature (\u00b0C)".format(slot)
        bundle = build_stability_tab_plot(title)
        if bundle is not None:
            result_obj = _SimpleNamespace(ts)
            stability_tab_apply_result(bundle, result_obj)
            stability_tab_autorange(bundle)
            gl.addWidget(bundle.series_checkbox_row, 0)
            hint = QLabel("Swatch: left = cold\u2192hot \u00b7 right = hot\u2192cold verify")
            hint.setStyleSheet("color: #9e9e9e; font-size: 10px;")
            hint.setWordWrap(True)
            gl.addWidget(hint)
            gl.addWidget(bundle.plot_widget, 1)
            _ts_pw = bundle.plot_widget
        else:
            gl.addWidget(QLabel("Could not build stability plot."))
    elif _PG:
        gl.addWidget(QLabel("Stability plot module not available."))
    else:
        gl.addWidget(QLabel("pyqtgraph not available"))
    if _ts_pw is not None:
        gl.addWidget(_XAxisRangeBar(_ts_pw))
    _maybe_install_data_view_plot_enlarge(
        enlarge_host, _ts_pw, "Temperature Stability {} — Data View".format(slot)
    )

    info_w = QWidget()
    il = QVBoxLayout(info_w)
    il.setContentsMargins(8, 8, 8, 8)
    passed = ts.get("passed", False)
    s = QLabel("Result: {}".format("PASS" if passed else "FAIL"))
    s.setStyleSheet("font-weight: bold; font-size: 14px; color: {};".format(
        _PASS_COLOR if passed else _FAIL_COLOR))
    il.addWidget(s)
    form = QFormLayout()
    form.addRow("Slot:", QLabel(str(ts.get("slot", slot))))
    form.addRow("Step Label:", QLabel(str(ts.get("step_label", ""))))
    form.addRow("SMSR Correction:", QLabel("Yes" if ts.get("smsr_correction_enabled") else "No"))
    n_pts = len(ts.get("temperature_c", []))
    form.addRow("Data Points:", QLabel(str(n_pts)))
    il.addLayout(form)
    _add_fail_reasons(il, ts)
    il.addStretch()

    gi = _make_graph_and_info(graph_w, info_w)
    log_w = _make_log_widget(_filter_log(data.get("log", ""), "TS"))
    plot_tab = _make_plot_subtab(_recipe_snapshot_from_data(data), log_w, gi, ts_slot=slot)

    table_tab = QWidget()
    QVBoxLayout(table_tab).addWidget(_make_ts_grid_table(ts, slot))

    return _wrap_test_tab(plot_tab, table_tab)


# ── Table row builders ────────────────────────────────────────────────────

def _add_liv_rows(rows: list, liv: dict) -> None:
    rows.append(("LIV", "Passed", "PASS" if liv.get("passed") else "FAIL"))
    rows.append(("LIV", "Threshold Current (mA)", _fmt(liv.get("threshold_current"), 2)))
    rows.append(("LIV", "Slope Efficiency (W/A)", _fmt(liv.get("slope_efficiency"), 4)))
    rows.append(("LIV", "Power @ Rated Current (mW)", _fmt(liv.get("power_at_rated_current"), 4)))
    rows.append(("LIV", "Current @ Rated Power (mA)", _fmt(liv.get("current_at_rated_power"), 2)))
    rows.append(("LIV", "Thorlabs Avg Power (mW)", _fmt(liv.get("thorlabs_average_power_mw"), 4)))
    rows.append(("LIV", "Final Power (mW)", _fmt(liv.get("final_power"), 4)))
    rows.append(("LIV", "PD @ Rated Current", _fmt(liv.get("pd_at_rated_current"), 4)))
    rows.append(("LIV", "Voltage @ Rated Current (V)", _fmt(liv.get("voltage_at_rated_current_V"), 4)))
    rows.append(("LIV", "TEC Temp Min (\u00b0C)", _fmt(liv.get("tec_temp_min"), 2)))
    rows.append(("LIV", "TEC Temp Max (\u00b0C)", _fmt(liv.get("tec_temp_max"), 2)))
    rows.append(("LIV", "Data Points", str(len(liv.get("current_array", [])))))
    for r in liv.get("fail_reasons", []):
        rows.append(("LIV", "Fail Reason", str(r)))


def _add_per_rows(rows: list, per: dict) -> None:
    rows.append(("PER", "Passed", "PASS" if per.get("passed") else "FAIL"))
    rows.append(("PER", "PER (dB)", _fmt(per.get("per_db"), 2)))
    rows.append(("PER", "Max Power (mW)", _fmt(per.get("max_power"), 4)))
    rows.append(("PER", "Min Power (mW)", _fmt(per.get("min_power"), 4)))
    rows.append(("PER", "Max Angle (\u00b0)", _fmt(per.get("max_angle"), 2)))
    rows.append(("PER", "Data Points", str(len(per.get("positions_deg", [])))))
    for r in per.get("fail_reasons", []):
        rows.append(("PER", "Fail Reason", str(r)))


def _add_spectrum_rows(rows: list, spec: dict) -> None:
    rows.append(("Spectrum", "Passed", "PASS" if spec.get("passed") else "FAIL"))
    rows.append(("Spectrum", "Peak Wavelength (nm)", _fmt(spec.get("peak_wavelength"), 6)))
    rows.append(("Spectrum", "Peak Level (dBm)", _fmt(spec.get("peak_level_dbm"), 2)))
    rows.append(("Spectrum", "Peak Power (mW)", _fmt(spec.get("peak_power"), 4)))
    rows.append(("Spectrum", "FWHM (nm)", _fmt(spec.get("fwhm"), 4)))
    rows.append(("Spectrum", "SMSR (dB)", _fmt(spec.get("smsr"), 2)))
    rows.append(("Spectrum", "Center (nm)", _fmt(spec.get("center_nm"), 4)))
    rows.append(("Spectrum", "Span (nm)", _fmt(spec.get("span_nm"), 2)))
    rows.append(("Spectrum", "SMSR First (dB)", _fmt(spec.get("smsr_first_db"), 2)))
    rows.append(("Spectrum", "FWHM First (nm)", _fmt(spec.get("fwhm_first_nm"), 4)))
    rows.append(("Spectrum", "1st Sweep Pass", "PASS" if spec.get("passed_first_sweep") else "FAIL"))
    for r in spec.get("fail_reasons", []):
        rows.append(("Spectrum", "Fail Reason", str(r)))


def _left_cell(text: str) -> QTableWidgetItem:
    """Left-aligned table cell."""
    item = QTableWidgetItem(text)
    item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    return item


def _make_liv_grid_table(liv: dict) -> QTableWidget:
    """Grid table: one row per current step — Current, Power, Voltage, PD."""
    currents = liv.get("current_array", [])
    powers = liv.get("power_array") or liv.get("gentec_power_array", [])
    voltages = liv.get("voltage_array", [])
    pds = liv.get("pd_array", [])
    n = max(len(currents), len(powers), len(voltages), len(pds))
    tbl = QTableWidget(n, len(_LIV_TABLE_HEADERS))
    tbl.setHorizontalHeaderLabels(_LIV_TABLE_HEADERS)
    _style_grid_table(tbl)
    for i in range(n):
        tbl.setItem(i, 0, _left_cell(str(i + 1)))
        tbl.setItem(i, 1, _left_cell(_fmt(currents[i] if i < len(currents) else None, 3)))
        tbl.setItem(i, 2, _left_cell(_fmt(powers[i] if i < len(powers) else None, 4)))
        tbl.setItem(i, 3, _left_cell(_fmt(voltages[i] if i < len(voltages) else None, 4)))
        tbl.setItem(i, 4, _left_cell(_fmt(pds[i] if i < len(pds) else None, 4)))
    return tbl


def _make_per_grid_table(per: dict) -> QTableWidget:
    """Grid table: one row per angle position — Angle, Power."""
    angles = per.get("positions_deg", [])
    powers = per.get("powers_mw", [])
    n = max(len(angles), len(powers))
    tbl = QTableWidget(n, len(_PER_TABLE_HEADERS))
    tbl.setHorizontalHeaderLabels(_PER_TABLE_HEADERS)
    _style_grid_table(tbl)
    for i in range(n):
        tbl.setItem(i, 0, _left_cell(str(i + 1)))
        tbl.setItem(i, 1, _left_cell(_fmt(angles[i] if i < len(angles) else None, 3)))
        tbl.setItem(i, 2, _left_cell(_fmt(powers[i] if i < len(powers) else None, 6)))
    return tbl


def _make_spectrum_grid_table(spec: dict) -> QTableWidget:
    """Grid table: one row per wavelength sample — Wavelength, Level.
    Shows second sweep data if available, otherwise first."""
    wdata = spec.get("second_sweep_wdata") or spec.get("first_sweep_wdata", [])
    ldata = spec.get("second_sweep_ldata") or spec.get("first_sweep_ldata", [])
    n = min(len(wdata), len(ldata))
    tbl = QTableWidget(n, len(_SPEC_TABLE_HEADERS))
    tbl.setHorizontalHeaderLabels(_SPEC_TABLE_HEADERS)
    _style_grid_table(tbl)
    for i in range(n):
        wf = _safe_float(wdata[i])
        lf = _safe_float(ldata[i])
        tbl.setItem(i, 0, _left_cell(str(i + 1)))
        tbl.setItem(i, 1, _left_cell(_fmt(wf, 6) if wf is not None else "—"))
        tbl.setItem(i, 2, _left_cell(_fmt(lf, 3) if lf is not None else "—"))
    return tbl


_STATUS_DISPLAY = {
    "stable": "Stable",
    "exceed": "Exceed",
    "retry": "Retry",
    "hard_fail": "Hard Fail",
    "tl_fail": "TL Fail",
}
# Retries are intermediate attempts — not a final row failure (still listed for raw trace).
_FAIL_STATUSES = {"exceed", "hard_fail", "tl_fail"}
_RED_BG = QColor("#4d0000")
_RED_FG = QColor("#ff6666")


def _make_ts_grid_table(ts: dict, slot: int) -> QTableWidget:
    """Build a proper grid table: one row per stored sample (includes retries), columns for all metrics.
    Rows where status is exceed / hard_fail / tl_fail are highlighted red (retry rows are normal)."""
    temps = ts.get("temperature_c", [])
    fwhm_list = ts.get("fwhm_nm", [])
    smsr_list = ts.get("smsr_db", [])
    smsr_ando_list = ts.get("smsr_osa_raw_db", [])
    pk_list = ts.get("peak_wavelength_nm", [])
    lv_list = ts.get("peak_level_dbm", [])
    tl_list = ts.get("thorlabs_power_mw", [])
    ramps_list = ts.get("point_ramp_code", [])
    status_list = ts.get("point_status", [])
    n = len(temps)

    smsr_corr = bool(ts.get("smsr_correction_enabled"))
    headers = list(_TS_TABLE_HEADERS)
    if smsr_corr:
        _smsr_col = "SMSR (dB)"
        try:
            _i = headers.index(_smsr_col) + 1
        except ValueError:
            _i = 7
        headers = headers[:_i] + [_TS_SMSR_ANDO_HEADER] + headers[_i:]
    tbl = QTableWidget(n, len(headers))
    tbl.setHorizontalHeaderLabels(headers)
    _style_grid_table(tbl)

    for i in range(n):
        st_code = str(status_list[i]) if i < len(status_list) else "stable"
        is_fail = st_code in _FAIL_STATUSES
        rc = str(ramps_list[i]) if i < len(ramps_list) else "c_h"
        ramp_label = "cold\u2192hot" if not rc.startswith("h") else "hot\u2192cold"

        row_items: list = []
        row_items.append(_left_cell(str(i + 1)))

        st_item = _left_cell(_STATUS_DISPLAY.get(st_code, st_code))
        if is_fail:
            st_item.setForeground(_RED_FG)
        else:
            st_item.setForeground(QColor("#66bb6a"))
        row_items.append(st_item)

        ramp_item = _left_cell(ramp_label)
        if rc.startswith("h"):
            ramp_item.setForeground(QColor("#e91e63"))
        else:
            ramp_item.setForeground(QColor("#1565c0"))
        row_items.append(ramp_item)

        row_items.append(_left_cell(_fmt(temps[i], 2)))
        row_items.append(_left_cell(_fmt(pk_list[i] if i < len(pk_list) else None, 6)))
        row_items.append(_left_cell(_fmt(fwhm_list[i] if i < len(fwhm_list) else None, 4)))
        row_items.append(_left_cell(_fmt(smsr_list[i] if i < len(smsr_list) else None, 2)))
        if smsr_corr:
            row_items.append(
                _left_cell(_fmt(smsr_ando_list[i] if i < len(smsr_ando_list) else None, 2))
            )
        row_items.append(_left_cell(_fmt(lv_list[i] if i < len(lv_list) else None, 2)))
        row_items.append(_left_cell(_fmt(tl_list[i] if i < len(tl_list) else None, 4)))

        for ci, item in enumerate(row_items):
            if is_fail:
                item.setBackground(_RED_BG)
            tbl.setItem(i, ci, item)

    return tbl


def _add_ts_rows(rows: list, ts: dict, slot: int) -> None:
    """Legacy 3-column row builder (used by global table)."""
    label = "TS{}".format(slot)
    rows.append((label, "Passed", "PASS" if ts.get("passed") else "FAIL"))
    rows.append((label, "Slot", str(ts.get("slot", slot))))
    rows.append((label, "SMSR Correction", "Yes" if ts.get("smsr_correction_enabled") else "No"))
    rows.append((label, "Data Points", str(len(ts.get("temperature_c", [])))))
    for r in ts.get("fail_reasons", []):
        rows.append((label, "Fail Reason", str(r)))


# ══════════════════════════════════════════════════════════════════════════
# Plot double-click enlarge (same idea as Main \u2192 Plot tab)
# ══════════════════════════════════════════════════════════════════════════


class _DataViewPlotEnlargeFilter(QObject):
    """Double-click on pyqtgraph canvas: full-window enlarge (viewport filter; matches ``MainWindow``)."""

    def __init__(self, host: "DataViewWindow", plot_widget: Any, title: str) -> None:
        super().__init__(host)
        self._host = host
        self._pw = plot_widget
        self._title = title
        self._handling = False

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:  # type: ignore[override]
        if event.type() == QEvent.MouseButtonDblClick:
            if self._handling:
                return True
            self._handling = True
            try:
                self._host._toggle_enlarged_data_view_plot(self._pw, self._title)
            finally:
                self._handling = False
            return True
        return False


def _maybe_install_data_view_plot_enlarge(host: Any, plot_widget: Any, dialog_title: str) -> None:
    if host is not None and plot_widget is not None and hasattr(host, "_install_pg_viewport_dblclick_enlarge"):
        host._install_pg_viewport_dblclick_enlarge(plot_widget, dialog_title)


# ══════════════════════════════════════════════════════════════════════════
# Main DataView Window
# ══════════════════════════════════════════════════════════════════════════

class DataViewWindow(QMainWindow):
    """Result viewer: toolbar with Load Result, tabs with inner Plot/Table."""

    def __init__(self, parent: Any = None):
        super().__init__(parent)
        self.setWindowTitle("Data View")
        self.setMinimumSize(1100, 700)
        self.setPalette(get_dark_palette())
        self.setStyleSheet(main_stylesheet())
        set_dark_title_bar(self)

        # Toolbar
        toolbar = QToolBar("Data View")
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(20, 20))
        toolbar.setStyleSheet(
            "QToolBar { background: #2a2a30; border-bottom: 1px solid #3a3a42; spacing: 8px; padding: 4px; } "
            "QToolButton { color: #e0e0e0; font-size: 12px; padding: 6px 16px; } "
            "QToolButton:hover { background: #3a3a42; }")
        self._load_act = QAction("Load Result", self)
        self._load_act.triggered.connect(self._on_load_result)
        toolbar.addAction(self._load_act)
        toolbar.addSeparator()
        self._info_label = QLabel("  No result loaded")
        self._info_label.setStyleSheet("color: #757575; font-size: 12px; padding-left: 8px;")
        toolbar.addWidget(self._info_label)
        self.addToolBar(toolbar)

        # Outer tabs
        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(
            "QTabBar::tab { min-width: 140px; padding: 7px 18px; font-size: 12px; }")
        self.setCentralWidget(self._tabs)
        self._build_empty_tabs()
        self._dv_enlarge_pw: Any = None
        self._dv_enlarge_dialog: Any = None
        self._dv_enlarge_restore: Any = None
        self._dv_enlarge_filters: List[QObject] = []

    def _build_empty_tabs(self) -> None:
        self._tabs.clear()
        self._tabs.addTab(_build_empty_summary_tab(), "Summary")
        self._tabs.addTab(_build_empty_liv(), "LIV")
        self._tabs.addTab(_build_empty_per(), "PER")
        self._tabs.addTab(_build_empty_spectrum(), "Spectrum")
        self._tabs.addTab(_build_empty_ts(1), "Temp Stability 1")
        self._tabs.addTab(_build_empty_ts(2), "Temp Stability 2")

    def _clear_dv_enlarge_filters(self) -> None:
        self._restore_enlarged_data_view_plot()
        for f in list(getattr(self, "_dv_enlarge_filters", []) or []):
            try:
                if isinstance(f, _DataViewPlotEnlargeFilter):
                    pw = getattr(f, "_pw", None)
                    if pw is not None:
                        vp = getattr(pw, "viewport", None)
                        if callable(vp):
                            vp().removeEventFilter(f)
                        else:
                            pw.removeEventFilter(f)
            except Exception:
                pass
            try:
                f.deleteLater()
            except Exception:
                pass
        self._dv_enlarge_filters = []

    def _install_pg_viewport_dblclick_enlarge(self, plot_widget: Any, dialog_title: str) -> None:
        if plot_widget is None:
            return
        try:
            plot_widget.setToolTip("Double-click plot to enlarge (same as Main \u2192 Plot tab).")
        except Exception:
            pass
        flt = _DataViewPlotEnlargeFilter(self, plot_widget, dialog_title)
        vp = getattr(plot_widget, "viewport", None)
        if callable(vp):
            vp().installEventFilter(flt)
        else:
            plot_widget.installEventFilter(flt)
        self._dv_enlarge_filters.append(flt)

    def _toggle_enlarged_data_view_plot(self, pw: Any, dialog_title: str) -> None:
        if getattr(self, "_dv_enlarge_pw", None) is pw:
            self._restore_enlarged_data_view_plot()
            return
        self._restore_enlarged_data_view_plot()
        self._open_enlarged_data_view_plot(pw, dialog_title)

    def _open_enlarged_data_view_plot(self, pw: Any, dialog_title: str) -> None:
        if pw is None:
            return
        parent = pw.parentWidget()
        if parent is None:
            return
        lay = parent.layout()
        if lay is None:
            return
        pw_idx = lay.indexOf(pw)
        if pw_idx < 0:
            return
        try:
            pw_stretch = lay.stretch(pw_idx)
        except Exception:
            pw_stretch = 1
        companions: List[tuple] = []
        for ci in range(pw_idx - 1, -1, -1):
            item = lay.itemAt(ci)
            if item is None:
                break
            w = item.widget()
            if w is None:
                break
            try:
                st = lay.stretch(ci)
            except Exception:
                st = 0
            companions.insert(0, (w, ci, st))
        for w, _ci, _st in companions:
            lay.removeWidget(w)
        lay.removeWidget(pw)
        dlg = QDialog(self)
        dlg.setWindowTitle(dialog_title)
        dlg.setModal(False)
        vl = QVBoxLayout(dlg)
        vl.setContentsMargins(6, 6, 6, 6)
        for w, _ci, _st in companions:
            vl.addWidget(w, 0)
        vl.addWidget(pw, 1)
        dlg.setWindowFlags(
            (dlg.windowFlags() | Qt.WindowMinMaxButtonsHint | Qt.Window)
            & ~Qt.WindowContextHelpButtonHint
        )
        first_companion_idx = companions[0][1] if companions else pw_idx
        self._dv_enlarge_pw = pw
        self._dv_enlarge_dialog = dlg
        self._dv_enlarge_restore = (lay, first_companion_idx, pw_stretch, companions)

        def _on_finished(_code: int = 0) -> None:
            if getattr(self, "_dv_enlarge_restore", None) is None:
                return
            self._restore_enlarged_data_view_plot()

        dlg.finished.connect(_on_finished)
        dlg.showMaximized()
        try:
            dlg.raise_()
            dlg.activateWindow()
        except Exception:
            pass

    def _restore_enlarged_data_view_plot(self) -> None:
        pw_stored = getattr(self, "_dv_enlarge_pw", None)
        rest = getattr(self, "_dv_enlarge_restore", None)
        dlg = getattr(self, "_dv_enlarge_dialog", None)
        self._dv_enlarge_pw = None
        self._dv_enlarge_dialog = None
        self._dv_enlarge_restore = None
        if pw_stored is None or rest is None:
            if dlg is not None:
                try:
                    dlg.blockSignals(True)
                    dlg.close()
                except Exception:
                    pass
                try:
                    dlg.deleteLater()
                except Exception:
                    pass
            return
        lay, first_idx, pw_stretch, companions = rest
        pw = pw_stored
        if dlg is not None:
            try:
                dl = dlg.layout()
                if dl is not None:
                    for w, _ci, _st in companions:
                        dl.removeWidget(w)
                    dl.removeWidget(pw)
            except Exception:
                pass
            try:
                dlg.blockSignals(True)
                dlg.close()
            except Exception:
                pass
            try:
                dlg.deleteLater()
            except Exception:
                pass
        try:
            insert_at = first_idx
            for w, _ci, st in companions:
                w.setParent(None)
                lay.insertWidget(insert_at, w, st)
                w.show()
                insert_at += 1
            pw.setParent(None)
            lay.insertWidget(insert_at, pw, pw_stretch)
            pw.show()
            gp = lay.parentWidget()
            if gp is not None:
                gp.updateGeometry()
        except Exception:
            pass

    def _on_load_result(self) -> None:
        picker = _SessionPicker(self)
        if picker.exec() != QDialog.DialogCode.Accepted:
            return
        folder = picker.selected_folder()
        if not folder:
            QMessageBox.warning(self, "No selection", "No result selected.")
            return
        try:
            data = load_session(folder)
        except Exception as e:
            QMessageBox.critical(self, "Load error", "Could not load result:\n{}".format(e))
            return
        self._apply_data(data)

    def _apply_data(self, data: Dict[str, Any]) -> None:
        session = data.get("session")
        if not isinstance(session, dict):
            session = {}
        recipe_name = session.get("recipe_name", "?")
        timestamp = session.get("timestamp", "?")
        raw_seq = session.get("test_sequence") or session.get("TestSequence") or []
        if isinstance(raw_seq, list):
            seq = ", ".join(str(x) for x in raw_seq)
        else:
            seq = str(raw_seq) if raw_seq else ""
        stopped = session.get("stopped_by_user", False)
        passed = session.get("overall_passed")
        if stopped:
            st, sc = "ABORTED", _ABORTED_COLOR
        elif passed is True:
            st, sc = "PASS", _PASS_COLOR
        elif passed is False:
            st, sc = "FAIL", _FAIL_COLOR
        else:
            st, sc = "UNKNOWN", "#9e9e9e"

        self._info_label.setText(
            '  <b style="color:#4fc3f7">{}</b>  |  {}  |  [{}]  |  '
            '<b style="color:{}">{}</b>'.format(recipe_name, timestamp, seq, sc, st))

        self._clear_dv_enlarge_filters()
        self._tabs.clear()
        try:
            self._tabs.addTab(_build_summary_tab(data), "Summary")
        except Exception as e:
            QMessageBox.critical(
                self,
                "Data View",
                "Could not build Summary tab. The folder may be corrupt or incompatible.\n\n{}".format(e),
            )
            self._build_empty_tabs()
            return
        plan = _ordered_test_tabs_plan(data)
        for stem, title in plan:
            try:
                if stem == "liv":
                    self._tabs.addTab(_build_liv_tab(data, self), title)
                elif stem == "per":
                    self._tabs.addTab(_build_per_tab(data, self), title)
                elif stem == "spectrum":
                    self._tabs.addTab(_build_spectrum_tab(data, self), title)
                elif stem == "ts1":
                    self._tabs.addTab(_build_ts_tab(data, 1, self), title)
                elif stem == "ts2":
                    self._tabs.addTab(_build_ts_tab(data, 2, self), title)
            except Exception as e:
                err = QWidget()
                ev = QVBoxLayout(err)
                ev.setContentsMargins(12, 12, 12, 12)
                lab = QLabel(
                    "This tab could not be built (data shape or plotting error). "
                    "Other tabs are still available.\n\n<b>{}</b>: {}".format(stem.upper(), e)
                )
                lab.setWordWrap(True)
                lab.setTextFormat(Qt.TextFormat.RichText)
                lab.setStyleSheet("color: #ffab91; font-size: 12px;")
                ev.addWidget(lab)
                self._tabs.addTab(err, title)
        self.setWindowTitle("Data View \u2014 {} [{}]".format(recipe_name, st))


def open_data_view(parent: Any = None) -> Optional[DataViewWindow]:
    """Entry point: password \u2192 DataView window (empty, ready for Load)."""
    pwd_dlg = _PasswordDialog(parent)
    if pwd_dlg.exec() != QDialog.DialogCode.Accepted or not pwd_dlg.authenticated:
        return None
    return DataViewWindow(None)
