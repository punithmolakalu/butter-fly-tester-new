"""
Test Information dialog: opens when user clicks Start New.
Operator name, serial no, part no, comments, recipe selection, wavelength, test sequence.
When a recipe is loaded (Browse), wavelength and test sequence are filled from the recipe.
Emits recipe_path_changed when a recipe file is successfully loaded so the main Recipe tab can mirror it.
"""
import os

from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QPlainTextEdit,
    QFileDialog,
    QGroupBox,
    QFormLayout,
    QMessageBox,
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


class TestInformationDialog(QDialog):
    """Dialog for test information: OP name, serial no, part no, comments, recipe, wavelength, test sequence."""
    clear_requested = pyqtSignal()
    # Absolute path after a recipe file is successfully read (Browse, paste path, or initial fill).
    recipe_path_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super(TestInformationDialog, self).__init__(parent)
        self.setWindowTitle("Test Information")
        self.setMinimumWidth(480)
        self.setMinimumHeight(520)
        if get_dark_palette:
            self.setPalette(get_dark_palette())
        if main_stylesheet:
            self.setStyleSheet(main_stylesheet())
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        self._build_content()

    def showEvent(self, event: QShowEvent):
        super().showEvent(event)
        if set_dark_title_bar:
            try:
                set_dark_title_bar(int(self.winId()), True)
            except Exception:
                pass

    def _build_content(self):
        layout = self.layout()
        # ----- Test Information -----
        info_box = QGroupBox("Test Information")
        info_box.setStyleSheet(_section_style())
        info_form = QFormLayout(info_box)
        info_form.setSpacing(8)
        self.operator_name_edit = QLineEdit()
        self.operator_name_edit.setPlaceholderText("Enter operator name")
        info_form.addRow(QLabel("Operator Name:"), self.operator_name_edit)
        self.serial_no_edit = QLineEdit()
        self.serial_no_edit.setPlaceholderText("Enter serial number")
        info_form.addRow(QLabel("Serial No:"), self.serial_no_edit)
        self.part_no_edit = QLineEdit()
        self.part_no_edit.setPlaceholderText("Enter part number")
        info_form.addRow(QLabel("Part No:"), self.part_no_edit)
        self.comments_edit = QLineEdit()
        self.comments_edit.setPlaceholderText("Enter comments (optional)")
        info_form.addRow(QLabel("Comments:"), self.comments_edit)
        layout.addWidget(info_box)

        # ----- Recipe Selection -----
        recipe_box = QGroupBox("Recipe Selection")
        recipe_box.setStyleSheet(_section_style())
        recipe_layout = QVBoxLayout(recipe_box)
        recipe_row = QHBoxLayout()
        self.recipe_path_edit = QLineEdit()
        self.recipe_path_edit.setPlaceholderText("Select recipe file (.json, .rcp, .ini)")
        recipe_row.addWidget(self.recipe_path_edit)
        browse_btn = QPushButton("Browse...")
        browse_btn.clicked.connect(self._on_browse_recipe)
        recipe_row.addWidget(browse_btn)
        recipe_layout.addLayout(recipe_row)
        self.recipe_path_edit.editingFinished.connect(self._on_recipe_path_editing_finished)
        self.wavelength_edit = QLineEdit()
        self.wavelength_edit.setPlaceholderText("Auto from recipe or enter manually (nm)")
        recipe_layout.addWidget(QLabel("Wavelength (nm):"))
        recipe_layout.addWidget(self.wavelength_edit)
        layout.addWidget(recipe_box)

        # ----- Test Sequence -----
        seq_box = QGroupBox("Test Sequence")
        seq_box.setStyleSheet(_section_style())
        seq_layout = QVBoxLayout(seq_box)
        self.sequence_display = QPlainTextEdit()
        self.sequence_display.setReadOnly(True)
        self.sequence_display.setPlaceholderText("Select a recipe to view test sequence")
        self.sequence_display.setMinimumHeight(120)
        seq_layout.addWidget(self.sequence_display)
        layout.addWidget(seq_box)

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
        layout.addLayout(btn_row)

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
        """Load recipe at path and fill wavelength and test sequence display."""
        path = (path or "").strip()
        if not path:
            self.wavelength_edit.clear()
            self.sequence_display.clear()
            return
        data = self._load_recipe_file(path)
        if not data:
            self.wavelength_edit.clear()
            self.sequence_display.clear()
            return
        general = data.get("GENERAL") or data.get("General") or {}
        wl = data.get("Wavelength") or general.get("Wavelength") or ""
        self.wavelength_edit.setText(str(wl).strip() if wl != "" else "")
        seq = data.get("TEST_SEQUENCE") or general.get("TestSequence") or []
        if not isinstance(seq, (list, tuple)):
            seq = [str(seq)] if seq else []
        lines = ["{}. {}".format(i + 1, name) for i, name in enumerate(seq)]
        self.sequence_display.setPlainText("\n".join(lines) if lines else "")
        self.recipe_path_changed.emit(os.path.abspath(path))

    def _on_browse_recipe(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select recipe file",
            "",
            "Recipe files (*.json *.rcp *.ini);;All files (*)",
        )
        if path:
            self.recipe_path_edit.setText(path)
            self._fill_from_recipe(path)

    def _get_splitter_message(self):
        """Return (splitter_name, short_message) based on wavelength. 400–700 Visible, 700–1100 NIR, >1100 IR."""
        try:
            wl_str = (self.wavelength_edit.text() or "").strip()
            wl = float(wl_str) if wl_str else None
        except ValueError:
            wl = None
        if wl is None:
            return "Unknown", "Enter wavelength and load a recipe to see which splitter to choose."
        if wl <= 700:
            name = "Visible (400–700 nm)"
        elif wl <= 1100:
            name = "NIR (700–1100 nm)"
        else:
            name = "IR (>1100 nm)"
        return name, "Choose the range: {}.".format(name)

    def set_initial_values(self, op_name="", serial_no="", part_no="", comments="", recipe_path="", wavelength=""):
        """Pre-fill form with current values (e.g. from main window). Operator name and other details persist until user changes or Clear."""
        self.operator_name_edit.setText(op_name or "")
        self.serial_no_edit.setText(serial_no or "")
        self.part_no_edit.setText(part_no or "")
        self.comments_edit.setText(comments or "")
        self.recipe_path_edit.blockSignals(True)
        self.recipe_path_edit.setText(recipe_path or "")
        self.recipe_path_edit.blockSignals(False)
        self.wavelength_edit.setText(wavelength or "")
        if (recipe_path or "").strip():
            self._fill_from_recipe((recipe_path or "").strip())
        else:
            self.sequence_display.clear()

    def _on_clear(self):
        """Clear all fields except Operator Name."""
        self.serial_no_edit.clear()
        self.part_no_edit.clear()
        self.comments_edit.clear()
        self.recipe_path_edit.clear()
        self.wavelength_edit.clear()
        self.sequence_display.clear()
        self.clear_requested.emit()

    def _on_start_test(self):
        # Show splitter reminder; on OK load details to GUI only (test starts on Run)
        splitter_name, msg = self._get_splitter_message()
        QMessageBox.information(self, "Beam splitter", msg)
        self.accept()

    def get_operator_name(self):
        return (self.operator_name_edit.text() or "").strip()

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
