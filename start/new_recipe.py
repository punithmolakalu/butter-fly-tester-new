"""
New Recipe: separate window for creating/editing a recipe.
Opens when user clicks New Recipe on the main window.
"""
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
    QCheckBox,
    QDoubleSpinBox,
    QTabWidget,
    QWidget,
    QMessageBox,
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QShowEvent
import json
import os

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


class NewRecipeWindow(QDialog):
    """Separate window for creating or editing a recipe. Save to file when done."""

    def __init__(self, parent=None, initial_data=None, initial_path=None):
        super(NewRecipeWindow, self).__init__(parent)
        self.setWindowTitle("New Recipe")
        self.setMinimumSize(640, 560)
        self.resize(720, 620)
        if get_dark_palette:
            self.setPalette(get_dark_palette())
        if main_stylesheet:
            self.setStyleSheet(main_stylesheet())

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # ----- Top: Recipe name, wavelength, description -----
        top_box = QGroupBox("Recipe")
        top_box.setStyleSheet(_section_style())
        top_form = QFormLayout(top_box)
        self.recipe_name_edit = QLineEdit()
        self.recipe_name_edit.setPlaceholderText("Recipe name")
        top_form.addRow(QLabel("Name:"), self.recipe_name_edit)
        self.wavelength_spin = QDoubleSpinBox()
        self.wavelength_spin.setRange(300, 2000)
        self.wavelength_spin.setDecimals(0)
        self.wavelength_spin.setValue(1064)
        self.wavelength_spin.setSuffix(" nm")
        top_form.addRow(QLabel("Wavelength (nm):"), self.wavelength_spin)
        self.description_edit = QLineEdit()
        self.description_edit.setPlaceholderText("Description (optional)")
        top_form.addRow(QLabel("Description:"), self.description_edit)
        self.fiber_coupled_check = QCheckBox("Fiber coupled")
        self.fiber_coupled_check.setChecked(False)
        top_form.addRow("", self.fiber_coupled_check)
        layout.addWidget(top_box)

        # ----- Tabs: GENERAL, LIV, PER -----
        self.tabs = QTabWidget()
        self._add_general_tab()
        self._add_liv_tab()
        self._add_per_tab()
        layout.addWidget(self.tabs)

        # ----- JSON preview -----
        json_box = QGroupBox("Recipe JSON (read-only)")
        json_box.setStyleSheet(_section_style())
        json_layout = QVBoxLayout(json_box)
        self.json_display = QPlainTextEdit()
        self.json_display.setReadOnly(True)
        self.json_display.setMaximumHeight(120)
        self.json_display.setPlaceholderText("Summary will appear after you fill fields above.")
        json_layout.addWidget(self.json_display)
        layout.addWidget(json_box)

        # ----- Buttons -----
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        save_btn = QPushButton("Save to file...")
        save_btn.setStyleSheet("QPushButton { background-color: #2d5a2d; } QPushButton:hover { background-color: #3d6b3d; }")
        save_btn.clicked.connect(self._on_save_to_file)
        btn_row.addWidget(save_btn)
        close_btn = QPushButton("Close")
        close_btn.setStyleSheet("QPushButton { background-color: #555; } QPushButton:hover { background-color: #666; }")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self._saved_path = None
        if initial_path:
            self._saved_path = os.path.abspath(str(initial_path))
        if initial_data:
            self._load_data(initial_data)
        else:
            self.recipe_name_edit.setText("New Recipe")
            self._update_json_preview()

        self.recipe_name_edit.textChanged.connect(self._update_json_preview)
        self.wavelength_spin.valueChanged.connect(self._update_json_preview)
        self.description_edit.textChanged.connect(self._update_json_preview)
        self.fiber_coupled_check.stateChanged.connect(self._update_json_preview)

    def showEvent(self, event: QShowEvent):
        super().showEvent(event)
        if set_dark_title_bar:
            try:
                set_dark_title_bar(int(self.winId()), True)
            except Exception:
                pass

    def _add_general_tab(self):
        w = QWidget()
        form = QFormLayout(w)
        self.general_temp = QDoubleSpinBox()
        self.general_temp.setRange(-50, 150)
        self.general_temp.setDecimals(2)
        self.general_temp.setValue(25)
        form.addRow(QLabel("Temperature (°C):"), self.general_temp)
        self.general_current = QDoubleSpinBox()
        self.general_current.setRange(0, 5000)
        self.general_current.setDecimals(1)
        self.general_current.setValue(500)
        form.addRow(QLabel("Current (mA):"), self.general_current)
        self.general_part_no = QLineEdit()
        self.general_part_no.setPlaceholderText("Part number")
        form.addRow(QLabel("Part number:"), self.general_part_no)
        self.general_batch = QLineEdit()
        self.general_batch.setPlaceholderText("Batch number")
        form.addRow(QLabel("Batch number:"), self.general_batch)
        w.setLayout(form)
        self.tabs.addTab(w, "GENERAL")

    def _add_liv_tab(self):
        w = QWidget()
        form = QFormLayout(w)
        self.liv_min_current = QDoubleSpinBox()
        self.liv_min_current.setRange(0, 5000)
        self.liv_min_current.setValue(0)
        form.addRow(QLabel("Min current (mA):"), self.liv_min_current)
        self.liv_max_current = QDoubleSpinBox()
        self.liv_max_current.setRange(0, 5000)
        self.liv_max_current.setValue(1500)
        form.addRow(QLabel("Max current (mA):"), self.liv_max_current)
        self.liv_increment = QDoubleSpinBox()
        self.liv_increment.setRange(0.1, 500)
        self.liv_increment.setValue(10)
        form.addRow(QLabel("Increment (mA):"), self.liv_increment)
        self.liv_temp = QDoubleSpinBox()
        self.liv_temp.setRange(-50, 150)
        self.liv_temp.setValue(25)
        form.addRow(QLabel("Temperature (°C):"), self.liv_temp)
        self.liv_rated_current = QDoubleSpinBox()
        self.liv_rated_current.setRange(0, 5000)
        self.liv_rated_current.setValue(1350)
        form.addRow(QLabel("Rated current (mA):"), self.liv_rated_current)
        self.liv_rated_power = QDoubleSpinBox()
        self.liv_rated_power.setRange(0, 10000)
        self.liv_rated_power.setValue(100)
        form.addRow(QLabel("Rated power (mW):"), self.liv_rated_power)
        w.setLayout(form)
        self.tabs.addTab(w, "LIV")

    def _add_per_tab(self):
        w = QWidget()
        form = QFormLayout(w)
        self.per_temp = QDoubleSpinBox()
        self.per_temp.setRange(-50, 150)
        self.per_temp.setValue(25)
        form.addRow(QLabel("Temperature (°C):"), self.per_temp)
        self.per_current = QDoubleSpinBox()
        self.per_current.setRange(0, 5000)
        self.per_current.setValue(80)
        form.addRow(QLabel("Current (mA):"), self.per_current)
        self.per_start_angle = QDoubleSpinBox()
        self.per_start_angle.setRange(-360, 360)
        self.per_start_angle.setValue(0)
        form.addRow(QLabel("Start angle (°):"), self.per_start_angle)
        self.per_travel = QDoubleSpinBox()
        self.per_travel.setRange(0, 360)
        self.per_travel.setValue(180)
        form.addRow(QLabel("Travel distance (°):"), self.per_travel)
        self.per_min_per = QDoubleSpinBox()
        self.per_min_per.setRange(0, 100)
        self.per_min_per.setValue(25)
        self.per_min_per.setSuffix(" dB")
        form.addRow(QLabel("Min PER (dB):"), self.per_min_per)
        w.setLayout(form)
        self.tabs.addTab(w, "PER")

    def _build_recipe_dict(self):
        wl = int(self.wavelength_spin.value())
        fc = self.fiber_coupled_check.isChecked()
        return {
            "Recipe_Name": (self.recipe_name_edit.text() or "New Recipe").strip() or "New Recipe",
            "Laser_Type": "DPSS",
            "Wavelength": wl,
            "Description": (self.description_edit.text() or "").strip(),
            "FiberCoupled": fc,
            "GENERAL": {
                "Wavelength": wl,
                "Temperature": self.general_temp.value(),
                "Current": self.general_current.value(),
                "LaserType": "DPSS",
                "PartNumber": (self.general_part_no.text() or "").strip(),
                "BatchNumber": (self.general_batch.text() or "").strip(),
                "FiberCoupled": fc,
                "TestSequence": ["LIV", "PER", "Spectrum"]
            },
            "OPERATIONS": {
                "LIV": {
                    "min_current_mA": self.liv_min_current.value(),
                    "max_current_mA": self.liv_max_current.value(),
                    "increment_mA": self.liv_increment.value(),
                    "wait_time_ms": 50,
                    "Temperature": self.liv_temp.value(),
                    "rated_current_mA": self.liv_rated_current.value(),
                    "rated_power_mW": self.liv_rated_power.value(),
                    "threshold_method": "max_slope",
                    "se_data_points": 10,
                    "FiberCoupled": fc
                },
                "PER": {
                    "Temperature": self.per_temp.value(),
                    "Current": self.per_current.value(),
                    "StartAngle": self.per_start_angle.value(),
                    "TravelDistance": self.per_travel.value(),
                    "Wavelength": wl,
                    "StepsPerDegree": 10,
                    "WaitTimeMs": 50,
                    "MinPER_dB": self.per_min_per.value()
                }
            },
            "TEST_SEQUENCE": ["LIV", "PER", "Spectrum"],
            "PASS_FAIL_CRITERIA": {
                "LIV": {
                    "min_threshold_mA": 50,
                    "max_threshold_mA": 300,
                    "min_slope_efficiency": 0.05,
                    "max_slope_efficiency": 0.15
                },
                "PER": {"min_PER_dB": self.per_min_per.value()}
            }
        }

    def _update_json_preview(self):
        try:
            d = self._build_recipe_dict()
            self.json_display.setPlainText(json.dumps(d, indent=2))
        except Exception:
            self.json_display.setPlainText("")

    def _load_data(self, data):
        if not isinstance(data, dict):
            return
        self.recipe_name_edit.setText(str(data.get("Recipe_Name", "New Recipe")))
        self.wavelength_spin.setValue(float(data.get("Wavelength", 1064)))
        self.description_edit.setText(str(data.get("Description", "")))
        self.fiber_coupled_check.setChecked(bool(data.get("FiberCoupled", False)))
        g = data.get("GENERAL") or {}
        if isinstance(g, dict):
            self.general_temp.setValue(float(g.get("Temperature", 25)))
            self.general_current.setValue(float(g.get("Current", 500)))
            self.general_part_no.setText(str(g.get("PartNumber", "")))
            self.general_batch.setText(str(g.get("BatchNumber", "")))
        liv = (data.get("OPERATIONS") or {}).get("LIV")
        if isinstance(liv, dict):
            self.liv_min_current.setValue(float(liv.get("min_current_mA", 0)))
            self.liv_max_current.setValue(float(liv.get("max_current_mA", 1500)))
            self.liv_increment.setValue(float(liv.get("increment_mA", 10)))
            self.liv_temp.setValue(float(liv.get("Temperature", 25)))
            self.liv_rated_current.setValue(float(liv.get("rated_current_mA", 1350)))
            self.liv_rated_power.setValue(float(liv.get("rated_power_mW", 100)))
        per = (data.get("OPERATIONS") or {}).get("PER")
        if isinstance(per, dict):
            self.per_temp.setValue(float(per.get("Temperature", 25)))
            self.per_current.setValue(float(per.get("Current", 80)))
            self.per_start_angle.setValue(float(per.get("StartAngle", 0)))
            self.per_travel.setValue(float(per.get("TravelDistance", 180)))
            self.per_min_per.setValue(float(per.get("MinPER_dB", 25)))
        self._update_json_preview()

    def _on_save_to_file(self):
        start_dir = ""
        if getattr(self, "_saved_path", None):
            start_dir = self._saved_path
        path, _ = QFileDialog.getSaveFileName(
            self, "Save recipe", start_dir,
            "Recipe files (*.json);;All files (*)",
        )
        if not path:
            return
        if not path.lower().endswith(".json"):
            path = path + ".json"
        try:
            d = self._build_recipe_dict()
            with open(path, "w", encoding="utf-8") as f:
                json.dump(d, f, indent=2)
            QMessageBox.information(self, "New Recipe", "Recipe saved to:\n{}".format(path))
            self._saved_path = path
        except Exception as e:
            QMessageBox.warning(self, "Save recipe", "Could not save: {}".format(e))

    def get_saved_path(self):
        return getattr(self, "_saved_path", None)
