"""
Test Information dialog: opens when user clicks Start New.
Operator name, serial no, part no, comments, recipe selection, wavelength, test sequence.
When a recipe is loaded (Browse), wavelength and test sequence are filled from the file.
Emits recipe_path_changed when a recipe file is successfully loaded so the main Recipe tab can mirror it.
"""
import os

from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QLabel,
    QLineEdit,
    QPushButton,
    QPlainTextEdit,
    QFileDialog,
    QGroupBox,
    QFormLayout,
    QMessageBox,
    QComboBox,
    QSizePolicy,
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QShowEvent

try:
    from view.dark_theme import get_dark_palette, main_stylesheet, set_dark_title_bar
except ImportError:
    get_dark_palette = None
    main_stylesheet = None
    set_dark_title_bar = None


def _section_style():
    return (
        "QGroupBox { font-weight: bold; font-size: 14px; border: 1px solid #3a3a42; border-radius: 4px; "
        "margin: 0; padding: 14px 8px 8px 8px; margin-top: 10px; background-color: #25252c; } "
        "QGroupBox::title { subcontrol-origin: padding; subcontrol-position: top left; top: 2px; left: 10px; "
        "padding: 0 6px; color: #e6e6e6; font-size: 14px; }"
    )


# Readable value fields on all resolutions (contrast + padding; grows with layout).
_STARTNEW_VALUE_LINEEDIT_STYLE = (
    "QLineEdit {"
    " background-color: #1e1e24;"
    " color: #f0f0f5;"
    " border: 1px solid #5c5c6a;"
    " border-radius: 4px;"
    " padding: 6px 10px;"
    " min-height: 22px;"
    " selection-background-color: #3d5a80;"
    "}"
    "QLineEdit:focus { border: 1px solid #7eb8da; }"
)
_STARTNEW_VALUE_PLAIN_STYLE = (
    "QPlainTextEdit {"
    " background-color: #1e1e24;"
    " color: #f0f0f5;"
    " border: 1px solid #5c5c6a;"
    " border-radius: 4px;"
    " padding: 8px 10px;"
    " selection-background-color: #3d5a80;"
    "}"
    "QPlainTextEdit:focus { border: 1px solid #7eb8da; }"
)


# Single visual row: combo + ▼ share one outline (same height, no vertical offset).
_STARTNEW_COMBO_ROW_HEIGHT_PX = 36
_STARTNEW_COMBO_ARROW_WIDTH_PX = 30


def _style_combo_flat_left(combo: QComboBox, row_height: int) -> None:
    """Combo text area only: native drop arrow hidden; height matches arrow cell exactly."""
    h = int(row_height)
    combo.setStyleSheet(
        "QComboBox {"
        " background-color: #1e1e24;"
        " color: #f0f0f5;"
        " border: 1px solid #5c5c6a;"
        " border-right: none;"
        " border-top-left-radius: 4px;"
        " border-bottom-left-radius: 4px;"
        " padding: 4px 10px;"
        " margin: 0px;"
        "}"
        "QComboBox:focus { border: 1px solid #7eb8da; border-right: none; }"
        "QComboBox::drop-down { width: 0px; height: 0px; border: none; }"
        "QComboBox::down-arrow { image: none; width: 0; height: 0; border: none; }"
    )
    combo.setFixedHeight(h)
    combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)


def wrap_combo_with_down_arrow(combo: QComboBox, arrow_tooltip: str = "") -> QWidget:
    """
    Combo + ▼ in one bar: identical height, shared border, arrow vertically centered.
    (Qt QSS down-arrow images are unreliable on Windows.)
    """
    h = _STARTNEW_COMBO_ROW_HEIGHT_PX
    aw = _STARTNEW_COMBO_ARROW_WIDTH_PX
    _style_combo_flat_left(combo, h)
    wrap = QWidget()
    wrap.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    wrap.setFixedHeight(h)
    row = QHBoxLayout(wrap)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(0)
    row.addWidget(combo, 1, Qt.AlignVCenter)
    # U+25BC — same background as combo; thin divider only (reads as one field).
    ob = QPushButton("\u25bc")
    ob.setObjectName("startnew_combo_arrow_btn")
    ob.setFixedSize(aw, h)
    ob.setCursor(Qt.PointingHandCursor)
    ob.setToolTip(arrow_tooltip or "Open list")
    ob.setFocusPolicy(Qt.NoFocus)
    ob.setStyleSheet(
        "QPushButton#startnew_combo_arrow_btn {"
        " background-color: #1e1e24;"
        " color: #d8d8ec;"
        " font-size: 14px;"
        " font-weight: bold;"
        " border: 1px solid #5c5c6a;"
        " border-left: 1px solid #4a4a58;"
        " border-top-right-radius: 4px;"
        " border-bottom-right-radius: 4px;"
        " padding: 0px;"
        " margin: 0px;"
        " min-width: %dpx; max-width: %dpx;"
        " min-height: %dpx; max-height: %dpx;"
        "}"
        "QPushButton#startnew_combo_arrow_btn:hover { background-color: #2a2a34; color: #ffffff; }"
        "QPushButton#startnew_combo_arrow_btn:pressed { background-color: #23232a; }" % (aw, aw, h, h)
    )

    def _open_popup():
        combo.showPopup()
        combo.setFocus()

    ob.clicked.connect(_open_popup)
    row.addWidget(ob, 0, Qt.AlignVCenter)
    return wrap


def _apply_value_field_style(w):
    """Make line edits and plain text areas clearly visible and horizontally elastic."""
    if isinstance(w, QLineEdit):
        w.setStyleSheet(_STARTNEW_VALUE_LINEEDIT_STYLE)
        w.setMinimumHeight(30)
        w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    elif isinstance(w, QPlainTextEdit):
        w.setStyleSheet(_STARTNEW_VALUE_PLAIN_STYLE)
        w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        w.setLineWrapMode(QPlainTextEdit.WidgetWidth)


def _recipes_directory() -> str:
    """Project `recipes` folder (next to `start/`)."""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "recipes"))


def list_recipe_files() -> list:
    """Sorted absolute paths to .ini (and .rcp) in the recipes directory — ship recipes as INI only."""
    base = _recipes_directory()
    if not os.path.isdir(base):
        return []
    out = []
    for fn in os.listdir(base):
        low = fn.lower()
        if low.endswith(".ini") or low.endswith(".rcp"):
            out.append(os.path.join(base, fn))
    return sorted(out, key=lambda p: os.path.basename(p).lower())


class TestInformationDialog(QDialog):
    """Dialog for test information: OP name, serial no, part no, comments, recipe, wavelength, test sequence."""
    clear_requested = pyqtSignal()
    # Absolute path after a recipe file is successfully read (Browse, paste path, or initial fill).
    recipe_path_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super(TestInformationDialog, self).__init__(parent)
        self.setWindowTitle("Test Information")
        self.setMinimumSize(520, 420)
        self.resize(760, 620)
        self.setSizeGripEnabled(True)
        if get_dark_palette:
            self.setPalette(get_dark_palette())
        if main_stylesheet:
            self.setStyleSheet(main_stylesheet())
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        layout.setContentsMargins(12, 12, 12, 12)
        self._build_content()

    def showEvent(self, event: QShowEvent):
        super().showEvent(event)
        if set_dark_title_bar:
            try:
                set_dark_title_bar(int(self.winId()), True)
            except Exception:
                pass
        self._populate_recipe_combo(preserve_path=(self.recipe_path_edit.text() or "").strip())

    def _build_content(self):
        layout = self.layout()
        # ----- Test Information -----
        info_box = QGroupBox("Test Information")
        info_box.setStyleSheet(_section_style())
        info_form = QFormLayout(info_box)
        info_form.setSpacing(10)
        info_form.setHorizontalSpacing(16)
        info_form.setFieldGrowthPolicy(QFormLayout.ExpandingFieldsGrow)
        self.operator_combo = QComboBox()
        self.operator_combo.setEditable(False)
        self.operator_combo.addItems(["Punith", "Dmitri"])
        self.operator_combo.setToolTip("Click the list or the ▼ button on the right to choose an operator.")
        op_wrap = wrap_combo_with_down_arrow(
            self.operator_combo, arrow_tooltip="Open operator list"
        )
        info_form.addRow(QLabel("Operator Name:"), op_wrap)
        self.serial_no_edit = QLineEdit()
        self.serial_no_edit.setPlaceholderText("Enter serial number")
        _apply_value_field_style(self.serial_no_edit)
        info_form.addRow(QLabel("Serial No:"), self.serial_no_edit)
        self.part_no_edit = QLineEdit()
        self.part_no_edit.setPlaceholderText("Enter part number")
        _apply_value_field_style(self.part_no_edit)
        info_form.addRow(QLabel("Part No:"), self.part_no_edit)
        self.comments_edit = QLineEdit()
        self.comments_edit.setPlaceholderText("Enter comments (optional)")
        _apply_value_field_style(self.comments_edit)
        info_form.addRow(QLabel("Comments:"), self.comments_edit)
        layout.addWidget(info_box, 0)

        # ----- Recipe Selection -----
        recipe_box = QGroupBox("Recipe Selection")
        recipe_box.setStyleSheet(_section_style())
        recipe_layout = QVBoxLayout(recipe_box)
        recipe_layout.setSpacing(10)
        recipe_row = QHBoxLayout()
        self.recipe_combo = QComboBox()
        self.recipe_combo.setMinimumWidth(200)
        self._populate_recipe_combo()
        self.recipe_combo.currentIndexChanged.connect(self._on_recipe_combo_changed_int)
        self.recipe_combo.setToolTip(
            "Recipe list: click the field or the ▼ button, or use Browse… to pick a recipe file."
        )
        recipe_wrap = wrap_combo_with_down_arrow(
            self.recipe_combo, arrow_tooltip="Open recipe list"
        )
        recipe_row.addWidget(recipe_wrap, 1)
        browse_btn = QPushButton("Browse...")
        browse_btn.setToolTip("Choose a recipe file outside the list if needed.")
        browse_btn.clicked.connect(self._on_browse_recipe)
        recipe_row.addWidget(browse_btn)
        recipe_layout.addLayout(recipe_row)
        self.recipe_path_edit = QLineEdit()
        self.recipe_path_edit.setPlaceholderText("Recipe path (set by dropdown or Browse)")
        self.recipe_path_edit.setVisible(False)
        self.recipe_path_edit.editingFinished.connect(self._on_recipe_path_editing_finished)
        self.recipe_file_label = QLabel("")
        self.recipe_file_label.setWordWrap(True)
        self.recipe_file_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.recipe_file_label.setStyleSheet("color: #c5c5d0; font-size: 11px; padding: 2px 0;")
        recipe_layout.addWidget(self.recipe_file_label)
        wl_row = QHBoxLayout()
        wl_row.addWidget(QLabel("Wavelength (nm):"))
        self.wavelength_edit = QLineEdit()
        self.wavelength_edit.setPlaceholderText("Auto from recipe or enter manually (nm)")
        _apply_value_field_style(self.wavelength_edit)
        wl_row.addWidget(self.wavelength_edit, 1)
        recipe_layout.addLayout(wl_row)
        layout.addWidget(recipe_box, 0)

        # ----- Test Sequence -----
        seq_box = QGroupBox("Test Sequence")
        seq_box.setStyleSheet(_section_style())
        seq_layout = QVBoxLayout(seq_box)
        seq_layout.setContentsMargins(8, 12, 8, 8)
        self.sequence_display = QPlainTextEdit()
        self.sequence_display.setReadOnly(True)
        self.sequence_display.setPlaceholderText("Select a recipe to view test sequence")
        self.sequence_display.setMinimumHeight(88)
        _apply_value_field_style(self.sequence_display)
        seq_layout.addWidget(self.sequence_display, 1)
        layout.addWidget(seq_box, 1)

        # ----- Buttons -----
        btn_row = QHBoxLayout()
        clear_btn = QPushButton("Clear")
        clear_btn.setStyleSheet("QPushButton { background-color: #5a5a5a; } QPushButton:hover { background-color: #6a6a6a; }")
        clear_btn.clicked.connect(self._on_clear)
        clear_btn.setToolTip("Clear all except Operator Name")
        btn_row.addWidget(clear_btn)
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setStyleSheet("QPushButton { background-color: #8b3a3a; } QPushButton:hover { background-color: #a04545; }")
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)
        start_test_btn = QPushButton("Start Test")
        start_test_btn.setStyleSheet("QPushButton { background-color: #2d5a2d; } QPushButton:hover { background-color: #3d6b3d; }")
        start_test_btn.clicked.connect(self._on_start_test)
        btn_row.addWidget(start_test_btn)
        layout.addLayout(btn_row, 0)

    def _update_recipe_file_label(self):
        p = (self.recipe_path_edit.text() or "").strip()
        self.recipe_file_label.setText(p if p else "")

    def _populate_recipe_combo(self, preserve_path=""):
        """Fill recipe dropdown from the project `recipes` folder; optionally re-select a path."""
        prev = (preserve_path or "").strip()
        self.recipe_combo.blockSignals(True)
        self.recipe_combo.clear()
        self.recipe_combo.addItem("— Select recipe —", None)
        for p in list_recipe_files():
            self.recipe_combo.addItem(os.path.basename(p), p)
        self.recipe_combo.blockSignals(False)
        if prev:
            self._sync_combo_to_path(prev)
        else:
            self.recipe_combo.setCurrentIndex(0)

    def _sync_combo_to_path(self, path: str):
        """Select the combo row that matches this absolute path, or '— Select recipe —' if not listed."""
        path = (path or "").strip()
        if not path:
            self.recipe_combo.blockSignals(True)
            self.recipe_combo.setCurrentIndex(0)
            self.recipe_combo.blockSignals(False)
            return
        ap = os.path.normpath(os.path.abspath(path))
        for i in range(self.recipe_combo.count()):
            d = self.recipe_combo.itemData(i)
            if d and os.path.normpath(os.path.abspath(str(d))) == ap:
                self.recipe_combo.blockSignals(True)
                self.recipe_combo.setCurrentIndex(i)
                self.recipe_combo.blockSignals(False)
                return
        self.recipe_combo.blockSignals(True)
        self.recipe_combo.setCurrentIndex(0)
        self.recipe_combo.blockSignals(False)

    def _on_recipe_combo_changed_int(self, index: int):
        path = self.recipe_combo.itemData(index)
        if path:
            path = str(path)
            self.recipe_path_edit.setText(path)
            self._update_recipe_file_label()
            self._fill_from_recipe(path)
        else:
            self.recipe_path_edit.clear()
            self._update_recipe_file_label()
            self.wavelength_edit.clear()
            self.sequence_display.clear()

    def _load_recipe_file(self, path):
        """Load recipe from .json / .rcp / .ini (shared loader with main window Recipe tab)."""
        from operations.recipe_io import load_recipe_file

        return load_recipe_file(path or "")

    def _on_recipe_path_editing_finished(self):
        """User pasted or typed a path — load if it is an existing file."""
        path = (self.recipe_path_edit.text() or "").strip()
        if path and os.path.isfile(path):
            self._fill_from_recipe(path)

    def _fill_from_recipe(self, path):
        """Load recipe at path and fill wavelength and test sequence."""
        path = (path or "").strip()
        if not path:
            self.wavelength_edit.clear()
            self.sequence_display.clear()
            self._update_recipe_file_label()
            return
        data = self._load_recipe_file(path)
        if not data:
            self.wavelength_edit.clear()
            self.sequence_display.clear()
            self._update_recipe_file_label()
            return
        general = data.get("GENERAL") or data.get("General") or {}
        wl = data.get("Wavelength") or general.get("Wavelength") or ""
        self.wavelength_edit.setText(str(wl).strip() if wl != "" else "")
        seq = data.get("TEST_SEQUENCE") or general.get("TestSequence") or []
        if not isinstance(seq, (list, tuple)):
            seq = [str(seq)] if seq else []
        lines = ["{}. {}".format(i + 1, name) for i, name in enumerate(seq)]
        self.sequence_display.setPlainText("\n".join(lines) if lines else "")
        self._update_recipe_file_label()
        self.recipe_path_changed.emit(os.path.abspath(path))

    def _on_browse_recipe(self):
        start_dir = _recipes_directory()
        if not os.path.isdir(start_dir):
            start_dir = ""
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select recipe file",
            start_dir,
            "Recipe files (*.json *.rcp *.ini);;All files (*)",
        )
        if path:
            path = os.path.abspath(path)
            self.recipe_path_edit.setText(path)
            self._sync_combo_to_path(path)
            self._fill_from_recipe(path)

    def _get_splitter_range_text(self):
        """Prompt the user to choose the beam-splitter value based on wavelength."""
        try:
            wl_str = (self.wavelength_edit.text() or "").strip()
            wl = float(wl_str) if wl_str else None
        except ValueError:
            wl = None
        if wl is None:
            return "Enter wavelength (nm) first."
        if wl < 700:
            return "Choose the beam splitter 400–700"
        if wl < 1100:
            return "Choose the beam splitter 700–1100"
        return "Choose the beam splitter 1100–1600"

    def set_initial_values(self, op_name="", serial_no="", part_no="", comments="", recipe_path="", wavelength=""):
        """Pre-fill form with current values (e.g. from main window). Operator name and other details persist until user changes or Clear."""
        op = (op_name or "").strip()
        if op in ("Punith", "Dmitri"):
            self.operator_combo.setCurrentText(op)
        else:
            self.operator_combo.setCurrentIndex(0)
        self.serial_no_edit.setText(serial_no or "")
        self.part_no_edit.setText(part_no or "")
        self.comments_edit.setText(comments or "")
        rp = (recipe_path or "").strip()
        self.recipe_path_edit.blockSignals(True)
        self.recipe_path_edit.setText(rp)
        self.recipe_path_edit.blockSignals(False)
        self._sync_combo_to_path(rp)
        self.wavelength_edit.setText(wavelength or "")
        if rp:
            self._fill_from_recipe(rp)
        else:
            self.sequence_display.clear()
            self._update_recipe_file_label()

    def _on_clear(self):
        """Clear all fields except Operator Name."""
        self.serial_no_edit.clear()
        self.part_no_edit.clear()
        self.comments_edit.clear()
        self.recipe_path_edit.clear()
        self.recipe_combo.blockSignals(True)
        self.recipe_combo.setCurrentIndex(0)
        self.recipe_combo.blockSignals(False)
        self.wavelength_edit.clear()
        self.sequence_display.clear()
        self._update_recipe_file_label()
        self.clear_requested.emit()

    def _on_start_test(self):
        QMessageBox.information(self, "Beam Splitter Selection", self._get_splitter_range_text())
        self.accept()

    def get_operator_name(self):
        return (self.operator_combo.currentText() or "").strip()

    def get_serial_no(self):
        return (self.serial_no_edit.text() or "").strip()

    def get_part_no(self):
        return (self.part_no_edit.text() or "").strip()

    def get_comments(self):
        return (self.comments_edit.text() or "").strip()

    def get_recipe_path(self):
        return (self.recipe_path_edit.text() or "").strip()

    def get_wavelength(self):
        return (self.wavelength_edit.text() or "").strip()
