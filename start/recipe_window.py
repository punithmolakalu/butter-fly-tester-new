"""
Full Recipe window (QMainWindow) for creating/editing recipes.
Opens maximized on the secondary monitor when user clicks New Recipe from the main GUI.
"""
import sys
import json
import os
from typing import Any, Dict, Optional
from PyQt5.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTabWidget,
    QLabel,
    QPushButton,
    QLineEdit,
    QSpinBox,
    QDoubleSpinBox,
    QCheckBox,
    QComboBox,
    QGroupBox,
    QGridLayout,
    QScrollArea,
    QFileDialog,
    QMessageBox,
    QInputDialog,
    QFormLayout,
    QFrame,
    QSizePolicy,
    QApplication,
)
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont

from view.dark_theme import get_dark_palette, main_stylesheet, set_dark_title_bar

# Shared dark theme for all recipe tab content (match Wavemeter Settings layout exactly)
RECIPE_TAB_STYLESHEET = """
    QWidget { background-color: #121212; color: #FFFFFF; }
    QGroupBox { font-weight: bold; font-size: 13px; border: 1px solid #333333; border-radius: 4px;
        margin-top: 12px; padding-top: 12px; background-color: #1E1E1E; color: #FFFFFF; }
    QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; font-size: 13px; color: #FFFFFF; }
    QLabel { color: #FFFFFF; font-size: 12px; }
    QPushButton { background-color: #3A3A3A; color: #FFFFFF; border: 1px solid #333333; border-radius: 3px;
        padding: 8px; font-weight: bold; font-size: 13px; }
    QPushButton:hover { background-color: #2A2A2A; }
    QPushButton:pressed { background-color: #505050; }
    QLineEdit, QSpinBox, QDoubleSpinBox { background-color: #1E1E1E !important; color: #FFFFFF !important;
        border: 1px solid #333333; border-radius: 2px; padding: 5px; font-size: 12px; }
    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus { background-color: #1E1E1E !important; border: 1px solid #2196F3; }
    QSpinBox::up-button, QDoubleSpinBox::up-button { subcontrol-origin: border; subcontrol-position: top right;
        width: 26px; min-width: 26px; height: 16px; min-height: 16px; background-color: #3d3d3d;
        border-top: 1px solid #505050; border-left: 1px solid #505050; border-right: 1px solid #252525; border-bottom: 1px solid #252525; }
    QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover { background-color: #4a4a4a; }
    QSpinBox::down-button, QDoubleSpinBox::down-button { subcontrol-origin: border; subcontrol-position: bottom right;
        width: 26px; min-width: 26px; height: 16px; min-height: 16px; background-color: #3d3d3d;
        border-top: 1px solid #505050; border-left: 1px solid #505050; border-right: 1px solid #252525; border-bottom: 1px solid #252525; }
    QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover { background-color: #4a4a4a; }
    QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
        image: none; width: 0px; height: 0px;
        border-left: 5px solid transparent; border-right: 5px solid transparent; border-bottom: 7px solid #e8e8f0;
        margin-right: 5px; margin-bottom: 1px;
    }
    QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
        image: none; width: 0px; height: 0px;
        border-left: 5px solid transparent; border-right: 5px solid transparent; border-top: 7px solid #e8e8f0;
        margin-right: 5px; margin-top: 1px;
    }
""" + """
    QComboBox { background-color: #1E1E1E !important; color: #FFFFFF !important; border: 1px solid #333333;
        border-radius: 2px; padding: 4px 24px 4px 6px; font-size: 12px; }
    QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: top right; width: 20px;
        border-left: 1px solid #333333; border-top-right-radius: 2px; border-bottom-right-radius: 2px; background-color: #1E1E1E; }
    QCheckBox { color: #FFFFFF; font-size: 12px; }
    QCheckBox::indicator { width: 18px; height: 18px; border: 1px solid #333333; border-radius: 2px; background-color: #1E1E1E; }
    QCheckBox::indicator:checked { background-color: #2196F3; }
    QScrollArea { background-color: #121212; border: 1px solid #333333; }
    QScrollArea > QWidget > QWidget { background-color: #121212; }
"""
GROUP_SPACING = 10
GROUP_MARGINS = (15, 20, 15, 15)
INPUT_WIDTH = 120
INPUT_WIDTH_WIDE = 150

# Not exposed in TEMP STABILITY UI; merged with loaded slot backup on save so Run still works.
_TS_RECIPE_DEFAULTS = {
    "FWHM_recovery_threshold_nm": 0.3,
    "StabilityResolution_nm": 0.05,
    "auto_ref_level": True,
    "Analysis": "DFB-LD",
    "MaxRetries": 5,
    "TecTolerance_C": 0.5,
    "TecSettleTimeout_s": 300.0,
    "PreamblePause_s": 2.0,
    "delta_wl_per_c_enable": False,
    "delta_wl_per_c_min": -1.0,
    "delta_wl_per_c_max": 1.0,
    # Minimum stable temperature span (°C) required after an exceed before another is allowed.
    "RecoveryStep_C": 0.7,
    # Consecutive exceeds allowed before resetting the counter (no fail).
    "RecoverySteps": 2,
    "SMSR_correction_enable": False,
    "ThorlabsRequired": False,
}


class RecipeWindow(QMainWindow):
    """Full-screen recipe editor (NEW RECIPE)."""

    recipe_saved = pyqtSignal(str)  # absolute path after SAVE writes the file (main window may ignore for tab preview)

    def __init__(self, parent=None):
        super().__init__(None)
        self.setWindowTitle("NEW RECIPE")

        self.setGeometry(100, 100, 1200, 800)
        self.setMinimumSize(880, 560)

        self.default_font = QFont()
        self.default_font.setPointSize(10)
        self.label_font = QFont()
        self.label_font.setPointSize(10)
        self.button_font = QFont()
        self.button_font.setPointSize(10)
        self.input_font = QFont()
        self.input_font.setPointSize(10)

        self.fp_enabled = False
        self.save_path = ""
        # Full path of last loaded or saved file — Save overwrites this when set.
        self._last_saved_or_loaded_path = None
        self.test_sequence_combos = []
        self.saved_selections = {}
        self._suppress_sequence_rule = False
        # Last loaded PASS_FAIL_CRITERIA (merge on save so keys not in the LIV grid are preserved).
        self._pass_fail_criteria_backup = {}
        # While loading a file, do not autosave on every setText (limits / criteria).
        self._suppress_recipe_autosave = False
        self._recipe_autosave_timer: Optional[QTimer] = None

        self._create_ui()

        font_style = """
            QWidget { font-size: 10pt; }
            QLabel { font-size: 10pt; }
            QPushButton { font-size: 10pt; padding: 5px; }
            QLineEdit, QSpinBox, QDoubleSpinBox { font-size: 10pt; padding: 3px; }
            QComboBox { font-size: 10pt; padding: 3px; }
            QCheckBox { font-size: 10pt; }
            QGroupBox { font-size: 10pt; font-weight: bold; }
            QGroupBox::title { font-size: 10pt; }
            QTabBar::tab { font-size: 10pt; padding: 10px 18px; min-height: 30px; }
            QTextEdit { font-size: 10pt; }
        """
        self.setPalette(get_dark_palette())
        self.setStyleSheet(main_stylesheet() + font_style)
        # Apply recipe theme + arrows to entire content so all tabs (including SPECTRUM sub-tabs) show arrows
        self.centralWidget().setStyleSheet(RECIPE_TAB_STYLESHEET + font_style)
        self.resize(1200, 800)

    def showEvent(self, event):
        super().showEvent(event)
        set_dark_title_bar(int(self.winId()), True)

    def _apply_font_to_widget(self, widget, font_type='default'):
        if font_type == 'label':
            widget.setFont(self.label_font)
        elif font_type == 'button':
            widget.setFont(self.button_font)
        elif font_type == 'input':
            widget.setFont(self.input_font)
        else:
            widget.setFont(self.default_font)

    def _create_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(8)
        main_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        top_frame = QFrame()
        top_layout = QHBoxLayout(top_frame)
        top_layout.setContentsMargins(0, 0, 0, 0)
        self.fpPathCheck = QCheckBox("FP Path")
        self.fpPathCheck.setFont(self.default_font)
        self.fpPathCheck.toggled.connect(lambda checked: setattr(self, 'fp_enabled', checked))
        top_layout.addWidget(self.fpPathCheck)
        save_path_label = QLabel("Save Path:")
        save_path_label.setFont(self.label_font)
        top_layout.addWidget(save_path_label)
        self.savePathEdit = QLineEdit()
        self.savePathEdit.setFont(self.input_font)
        self.savePathEdit.setMinimumWidth(200)
        top_layout.addWidget(self.savePathEdit)
        self.browseBtn = QPushButton("Browse")
        self.browseBtn.setFont(self.button_font)
        self.browseBtn.clicked.connect(self._browse_folder)
        top_layout.addWidget(self.browseBtn)
        self.saveBtn = QPushButton("SAVE")
        self.saveBtn.setFont(self.button_font)
        self.saveBtn.clicked.connect(self._save_recipe)
        top_layout.addWidget(self.saveBtn)
        self.exitBtn = QPushButton("EXIT")
        self.exitBtn.setFont(self.button_font)
        self.exitBtn.clicked.connect(self.close)
        top_layout.addWidget(self.exitBtn)
        top_layout.addStretch()
        main_layout.addWidget(top_frame)

        self.tabWidget = QTabWidget()
        self.tabWidget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        main_layout.addWidget(self.tabWidget, 1)
        self._create_general_tab()
        self._create_per_tab()
        self._create_liv_tab()
        self._create_spectrum_tab()
        self._create_temperature_stability_tab()
        self._wire_limits_autosave()

    def _create_general_tab(self):
        gen_tab = QWidget()
        gen_tab.setStyleSheet(RECIPE_TAB_STYLESHEET)
        gen_layout = QVBoxLayout(gen_tab)
        gen_layout.setContentsMargins(15, 15, 15, 15)
        gen_layout.setSpacing(GROUP_SPACING)
        gen_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        browse_frame = QFrame()
        browse_layout = QHBoxLayout(browse_frame)
        browse_label = QLabel("BROWSE")
        self._apply_font_to_widget(browse_label, 'label')
        browse_layout.addWidget(browse_label)
        self.recipePathEdit = QLineEdit()
        self._apply_font_to_widget(self.recipePathEdit, 'input')
        self.recipePathEdit.setMinimumWidth(600)
        browse_layout.addWidget(self.recipePathEdit)
        self.browseRecipeBtn = QPushButton("Browse")
        self._apply_font_to_widget(self.browseRecipeBtn, 'button')
        self.browseRecipeBtn.clicked.connect(self._browse_recipe_file)
        browse_layout.addWidget(self.browseRecipeBtn)
        self.saveRecipeBtn = QPushButton("Save")
        self._apply_font_to_widget(self.saveRecipeBtn, 'button')
        self.saveRecipeBtn.clicked.connect(self._save_recipe)
        browse_layout.addWidget(self.saveRecipeBtn)
        gen_layout.addWidget(browse_frame)
        browse_desc_label = QLabel("Browse for Recipe to view/Alter it")
        self._apply_font_to_widget(browse_desc_label, 'label')
        gen_layout.addWidget(browse_desc_label)
        rcp_gen_group = QGroupBox("RCP-GEN")
        rcp_gen_group.setFont(self.label_font)
        rcp_gen_layout = QVBoxLayout(rcp_gen_group)
        rcp_gen_layout.setSpacing(GROUP_SPACING)
        rcp_gen_layout.setContentsMargins(*GROUP_MARGINS)
        name_layout = QHBoxLayout()
        name_label = QLabel("RECIPE NAME:")
        self._apply_font_to_widget(name_label, 'label')
        name_layout.addWidget(name_label)
        self.recipeNameEdit = QLineEdit()
        self._apply_font_to_widget(self.recipeNameEdit, 'input')
        name_layout.addWidget(self.recipeNameEdit)
        rcp_gen_layout.addLayout(name_layout)
        comments_layout = QHBoxLayout()
        comments_label = QLabel("COMMENTS:")
        self._apply_font_to_widget(comments_label, 'label')
        comments_layout.addWidget(comments_label)
        self.commentsEdit = QLineEdit()
        self._apply_font_to_widget(self.commentsEdit, 'input')
        comments_layout.addWidget(self.commentsEdit)
        rcp_gen_layout.addLayout(comments_layout)
        seq_header_layout = QHBoxLayout()
        seq_label = QLabel("Test Sequence")
        self._apply_font_to_widget(seq_label, 'label')
        seq_header_layout.addWidget(seq_label)
        seq_header_layout.addSpacing(200)
        num_tests_label = QLabel("# Tests")
        self._apply_font_to_widget(num_tests_label, 'label')
        seq_header_layout.addWidget(num_tests_label)
        self.numTestsSpin = QSpinBox()
        self._apply_font_to_widget(self.numTestsSpin, 'input')
        self.numTestsSpin.setRange(1, 20)
        self.numTestsSpin.setValue(1)
        self.numTestsSpin.setMinimumWidth(60)
        self.numTestsSpin.valueChanged.connect(self._update_test_sequence)
        seq_header_layout.addWidget(self.numTestsSpin)
        seq_header_layout.addSpacing(24)
        self.fiberCoupledCheck = QCheckBox("Fiber Coupled")
        self._apply_font_to_widget(self.fiberCoupledCheck, 'label')
        self.fiberCoupledCheck.setChecked(False)
        seq_header_layout.addWidget(self.fiberCoupledCheck)
        seq_header_layout.addSpacing(24)
        seq_header_layout.addWidget(QLabel("Wavelength (nm):"))
        self.wavelengthEdit = QLineEdit()
        self.wavelengthEdit.setPlaceholderText("e.g. 1310")
        self.wavelengthEdit.setMinimumWidth(80)
        self._apply_font_to_widget(self.wavelengthEdit, 'input')
        seq_header_layout.addWidget(self.wavelengthEdit)
        seq_header_layout.addSpacing(24)
        self.smsrCheckBox = QCheckBox("SMSR Correction")
        self.smsrCheckBox.setChecked(False)
        self.smsrCheckBox.setToolTip(
            "When checked: WAVEMETER → smsr is enabled, and Temperature Stability uses "
            "corrected SMSR = measured SMSR (dB) − peak level (dBm) for limits, plots, and CSV "
            "(saved as SMSR_correction_enable on each TS step)."
        )
        self._apply_font_to_widget(self.smsrCheckBox, 'label')
        seq_header_layout.addWidget(self.smsrCheckBox)
        rcp_gen_layout.addLayout(seq_header_layout)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setMinimumHeight(250)
        self.seqFrame = QWidget()
        self.seqFrame.setStyleSheet("background-color: #121212;")
        self.seqLayout = QVBoxLayout(self.seqFrame)
        self.seqLayout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.seqLayout.setContentsMargins(0, 0, 0, 0)
        self.seqLayout.setSpacing(5)
        scroll_area.setWidget(self.seqFrame)
        rcp_gen_layout.addWidget(scroll_area)
        gen_layout.addWidget(rcp_gen_group)
        gen_layout.addStretch()
        self.tabWidget.addTab(gen_tab, "GENERAL")
        self._update_test_sequence()

    def _normalize_sequence(self, sequence: list) -> list:
        return list(sequence)

    def _update_test_sequence(self):
        num = self.numTestsSpin.value()
        previous_count = len(self.test_sequence_combos)
        for i, combo in enumerate(self.test_sequence_combos):
            self.saved_selections[i] = combo.currentText() if combo.currentText() else ""
        if num < previous_count:
            for i in range(num, previous_count):
                self.saved_selections.pop(i, None)
        current_list = [self.saved_selections.get(i, "") for i in range(num)]
        normalized = self._normalize_sequence(current_list)
        if normalized != current_list:
            self.saved_selections = {i: normalized[i] for i in range(len(normalized))}
            self._suppress_sequence_rule = True
            self.numTestsSpin.blockSignals(True)
            self.numTestsSpin.setValue(len(normalized))
            self.numTestsSpin.blockSignals(False)
            self._suppress_sequence_rule = False
            num = len(normalized)
        for combo in self.test_sequence_combos:
            combo.setParent(None)
            combo.deleteLater()
        self.test_sequence_combos.clear()
        while self.seqLayout.count():
            child = self.seqLayout.takeAt(0)
            if child is not None:
                widget = child.widget()
                if widget is not None:
                    widget.deleteLater()
                layout = child.layout()
                if layout is not None:
                    while layout.count():
                        nested = layout.takeAt(0)
                        if nested:
                            w = nested.widget()
                            if w:
                                w.deleteLater()
        test_options = [
            "LIV",
            "PER",
            "Spectrum",
            "Temperature Stability 1",
            "Temperature Stability 2",
            "WLvsTemp",
            "WLvsCurrent",
        ]
        ITEMS_PER_COLUMN = 7
        columns = []
        num_columns = (num + ITEMS_PER_COLUMN - 1) // ITEMS_PER_COLUMN
        for col_idx in range(num_columns):
            col_layout = QVBoxLayout()
            col_layout.setContentsMargins(0, 0, 0, 0)
            col_layout.setSpacing(5)
            columns.append(col_layout)
        for i in range(num):
            col_index = i // ITEMS_PER_COLUMN
            row_layout = QHBoxLayout()
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(0)
            label = QLabel(f"{i+1}.")
            label.setContentsMargins(0, 0, 0, 0)
            row_layout.addWidget(label)
            combo = QComboBox()
            combo.addItem("")
            combo.addItems(test_options)
            combo.setFixedWidth(200)
            combo.setContentsMargins(0, 0, 0, 0)
            sel = self.saved_selections.get(i, "")
            if sel:
                idx = combo.findText(sel)
                if idx >= 0:
                    combo.setCurrentIndex(idx)
            self.test_sequence_combos.append(combo)
            row_layout.addWidget(combo)
            columns[col_index].addLayout(row_layout)
        main_row_layout = QHBoxLayout()
        main_row_layout.setContentsMargins(0, 0, 0, 0)
        main_row_layout.setSpacing(20)
        main_row_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        for col_layout in columns:
            col_widget = QWidget()
            col_widget.setLayout(col_layout)
            col_widget.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
            main_row_layout.addWidget(col_widget, 0, Qt.AlignmentFlag.AlignTop)
        self.seqLayout.addLayout(main_row_layout)
        for i, combo in enumerate(self.test_sequence_combos):
            combo.currentIndexChanged.connect(lambda new_index, idx=i: self._on_sequence_combo_changed(idx))

    def _on_sequence_combo_changed(self, index: int):
        if self._suppress_sequence_rule:
            return
        if index >= len(self.test_sequence_combos):
            return

    def _create_per_tab(self):
        per_tab = QWidget()
        per_tab.setStyleSheet(RECIPE_TAB_STYLESHEET)
        per_layout = QHBoxLayout(per_tab)
        per_layout.setContentsMargins(15, 15, 15, 15)
        per_layout.setSpacing(15)
        per_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        center_widget = QWidget()
        center_layout = QHBoxLayout(center_widget)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(15)
        motor_group = QGroupBox("Motor Settings")
        motor_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        motor_layout = QFormLayout(motor_group)
        motor_layout.setSpacing(GROUP_SPACING)
        motor_layout.setContentsMargins(*GROUP_MARGINS)
        motor_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.measSpeedEdit = QLineEdit()
        self.measSpeedEdit.setFixedWidth(INPUT_WIDTH)
        self.measSpeedEdit.setPlaceholderText("e.g. 10")
        self.measSpeedEdit.setToolTip(
            "PRM rotation speed during the PER sweep, in degrees per second (°/s). "
            "Sent to Thorlabs Kinesis as max velocity (capped at 25 °/s for PRM1-Z8 / KDC101)."
        )
        motor_layout.addRow("Meas speed (°/s):", self.measSpeedEdit)
        self.setupSpeedEdit = QLineEdit()
        self.setupSpeedEdit.setFixedWidth(INPUT_WIDTH)
        self.setupSpeedEdit.setPlaceholderText("optional — defaults to meas speed")
        self.setupSpeedEdit.setToolTip(
            "PRM speed for moving to the start angle and returning, in degrees per second (°/s). "
            "Uses the same set_speed call as Manual Control (capped at 25 °/s). "
            "Leave blank or 0 to use the meas speed for setup moves."
        )
        motor_layout.addRow("Setup speed (°/s):", self.setupSpeedEdit)
        self.startAngleEdit = QLineEdit()
        self.startAngleEdit.setFixedWidth(INPUT_WIDTH)
        self.startAngleEdit.setToolTip("PRM absolute angle (degrees) before the sweep.")
        motor_layout.addRow("Starting Angle:", self.startAngleEdit)
        self.travelDistEdit = QLineEdit()
        self.travelDistEdit.setFixedWidth(INPUT_WIDTH)
        self.travelDistEdit.setToolTip(
            "PRM rotation during Thorlabs sampling (degrees), not actuator mm. "
            "Sweep runs from Starting Angle to Starting Angle + Travel Distance at Meas speed."
        )
        motor_layout.addRow("Travel Distance:", self.travelDistEdit)
        center_layout.addWidget(motor_group, 0)
        act_group = QGroupBox("Actuator Settings")
        act_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        act_layout = QFormLayout(act_group)
        act_layout.setSpacing(GROUP_SPACING)
        act_layout.setContentsMargins(*GROUP_MARGINS)
        act_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.actSpeedEdit = QLineEdit()
        self.actSpeedEdit.setFixedWidth(INPUT_WIDTH)
        self.actSpeedEdit.setToolTip(
            "Linear actuator B: speed in mm/s used to estimate move duration after moveb (serial command is distance only)."
        )
        act_layout.addRow("Speed:", self.actSpeedEdit)
        self.actDistEdit = QLineEdit()
        self.actDistEdit.setFixedWidth(INPUT_WIDTH)
        self.actDistEdit.setToolTip(
            "Linear actuator B: travel in millimetres for moveb before PER (not PRM Travel Distance)."
        )
        act_layout.addRow("Distance:", self.actDistEdit)
        center_layout.addWidget(act_group, 0)
        per_layout.addWidget(center_widget, 0)
        self.tabWidget.addTab(per_tab, "PER")

    def _create_liv_tab(self):
        liv_tab = QWidget()
        liv_tab.setStyleSheet(RECIPE_TAB_STYLESHEET)
        liv_layout = QHBoxLayout(liv_tab)
        liv_layout.setContentsMargins(15, 15, 15, 15)
        liv_layout.setSpacing(15)
        liv_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        left_column = QWidget()
        left_layout = QVBoxLayout(left_column)
        left_layout.setSpacing(GROUP_SPACING)
        curr_group = QGroupBox("Current Control Parameters")
        curr_layout = QFormLayout(curr_group)
        curr_layout.setSpacing(GROUP_SPACING)
        curr_layout.setContentsMargins(*GROUP_MARGINS)
        self.minCurrEdit = QLineEdit("0")
        self.minCurrEdit.setFixedWidth(INPUT_WIDTH)
        curr_layout.addRow("MINCurr (mA):", self.minCurrEdit)
        self.maxCurrEdit = QLineEdit("0")
        self.maxCurrEdit.setFixedWidth(INPUT_WIDTH)
        curr_layout.addRow("MAXCurr (mA):", self.maxCurrEdit)
        self.incEdit = QLineEdit("0")
        self.incEdit.setFixedWidth(INPUT_WIDTH)
        curr_layout.addRow("INC (mA):", self.incEdit)
        self.waitTimeEdit = QLineEdit("0")
        self.waitTimeEdit.setFixedWidth(INPUT_WIDTH)
        curr_layout.addRow("WAIT TIME (ms):", self.waitTimeEdit)
        left_layout.addWidget(curr_group)
        temp_layout = QHBoxLayout()
        temp_layout.setSpacing(GROUP_SPACING)
        temp_layout.addWidget(QLabel("Temperature (C):"))
        self.tempSpin = QSpinBox()
        self.tempSpin.setRange(0, 200)
        self.tempSpin.setFixedWidth(INPUT_WIDTH)
        temp_layout.addWidget(self.tempSpin)
        left_layout.addLayout(temp_layout)
        mult_layout = QHBoxLayout()
        mult_layout.setSpacing(GROUP_SPACING)
        mult_layout.addWidget(QLabel("Mult Factor:"))
        self.multSpin = QSpinBox()
        self.multSpin.setRange(0, 100)
        self.multSpin.setFixedWidth(INPUT_WIDTH)
        mult_layout.addWidget(self.multSpin)
        left_layout.addStretch()
        liv_layout.addWidget(left_column, 0)
        right_column = QWidget()
        right_layout = QVBoxLayout(right_column)
        right_layout.setSpacing(GROUP_SPACING)
        rated_group = QGroupBox("Rated Operation")
        rated_layout = QFormLayout(rated_group)
        rated_layout.setSpacing(GROUP_SPACING)
        rated_layout.setContentsMargins(*GROUP_MARGINS)
        self.ratedCurrentEdit = QLineEdit("0")
        self.ratedCurrentEdit.setFixedWidth(INPUT_WIDTH)
        rated_layout.addRow("Rated Current (Ir) (mA):", self.ratedCurrentEdit)
        self.ratedPowerEdit = QLineEdit("0")
        self.ratedPowerEdit.setFixedWidth(INPUT_WIDTH)
        rated_layout.addRow("Rated Power (Lr) (mW):", self.ratedPowerEdit)
        right_layout.addWidget(rated_group)
        se_group = QGroupBox("Slope Efficiency (SE) & TH calc")
        se_layout = QFormLayout(se_group)
        se_layout.setSpacing(GROUP_SPACING)
        se_layout.setContentsMargins(*GROUP_MARGINS)
        self.sePointsEdit = QLineEdit("0")
        self.sePointsEdit.setFixedWidth(INPUT_WIDTH)
        se_layout.addRow("# data points for SE calc:", self.sePointsEdit)
        right_layout.addWidget(se_group)
        criteria_group = QGroupBox("Pass / Fail Criteria")
        criteria_layout = QGridLayout(criteria_group)
        criteria_layout.setSpacing(GROUP_SPACING)
        criteria_layout.setContentsMargins(*GROUP_MARGINS)
        criteria_layout.addWidget(QLabel("Lower Limit"), 0, 1)
        criteria_layout.addWidget(QLabel("Upper Limit"), 0, 2)
        criteria_layout.addWidget(QLabel("ENABLE"), 0, 3)
        criteria_params = [
            ("L @ Ir", "mW", "mW"),
            ("V @ Ir", "V", "V"),
            ("I @ Lr", "mA", "mA"),
            ("V @ Lr", "V", "V"),
            ("SE1", "mW/", "mW/"),
            ("IT", "mA", "mA"),
            ("PD @ Ir", "", "")
        ]
        self.liv_criteria_entries = {}
        for i, (param, unit1, unit2) in enumerate(criteria_params):
            row = i + 1
            criteria_layout.addWidget(QLabel(param), row, 0)
            ll_entry = QLineEdit("0")
            ll_entry.setFixedWidth(INPUT_WIDTH)
            # One cell per column: line edit + unit label in a row (do not stack two widgets on the same grid cell).
            ll_wrap = QWidget()
            ll_h = QHBoxLayout(ll_wrap)
            ll_h.setContentsMargins(0, 0, 0, 0)
            ll_h.setSpacing(4)
            ll_h.addWidget(ll_entry)
            if unit1:
                ll_h.addWidget(QLabel(unit1))
            ll_h.addStretch(1)
            criteria_layout.addWidget(ll_wrap, row, 1)
            ul_entry = QLineEdit("0")
            ul_entry.setFixedWidth(INPUT_WIDTH)
            ul_wrap = QWidget()
            ul_h = QHBoxLayout(ul_wrap)
            ul_h.setContentsMargins(0, 0, 0, 0)
            ul_h.setSpacing(4)
            ul_h.addWidget(ul_entry)
            if unit2:
                ul_h.addWidget(QLabel(unit2))
            ul_h.addStretch(1)
            criteria_layout.addWidget(ul_wrap, row, 2)
            enable_check = QCheckBox()
            criteria_layout.addWidget(enable_check, row, 3)
            self.liv_criteria_entries[param] = {"ll": ll_entry, "ul": ul_entry, "enable": enable_check}
        right_layout.addWidget(criteria_group)
        right_layout.addStretch()
        liv_layout.addWidget(right_column, 0)
        self.tabWidget.addTab(liv_tab, "LIV")

    def _create_spectrum_tab(self):
        spec_tab = QWidget()
        spec_tab.setStyleSheet(RECIPE_TAB_STYLESHEET)
        spec_layout = QVBoxLayout(spec_tab)
        spec_layout.setContentsMargins(5, 5, 5, 5)
        spec_layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        spec_notebook = QTabWidget()
        ando_tab = self._create_ando_settings_tab()
        spec_notebook.addTab(ando_tab, "Ando Settings")
        wavemeter_tab = self._create_wavemeter_settings_tab()
        spec_notebook.addTab(wavemeter_tab, "Wavemeter Settings")
        spec_layout.addWidget(spec_notebook)
        self.tabWidget.addTab(spec_tab, "SPECTRUM")

    def _create_temperature_stability_tab(self):
        """OPERATIONS['Temperature Stability 1'] and ['Temperature Stability 2'] — matches stability_process recipe keys."""
        self._ts_slot_widgets = {1: {}, 2: {}}
        # Full OPERATIONS block last loaded per slot (preserves keys not shown in the minimal UI).
        self._ts_slot_backup = {1: {}, 2: {}}
        outer = QWidget()
        outer.setStyleSheet(RECIPE_TAB_STYLESHEET)
        outer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        lay = QVBoxLayout(outer)
        lay.setContentsMargins(5, 5, 5, 5)
        lay.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        inner = QWidget()
        inner.setMinimumWidth(0)
        inner.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        vl = QVBoxLayout(inner)
        vl.setContentsMargins(8, 8, 8, 8)
        vl.setSpacing(16)
        vl.setAlignment(Qt.AlignmentFlag.AlignTop)

        title1 = QLabel("Temperature Stability 1")
        title1.setStyleSheet("font-weight: bold; font-size: 14px; color: #FFFFFF;")
        vl.addWidget(title1)
        vl.addWidget(self._build_ts_stability_panel(1))

        title2 = QLabel("Temperature Stability 2")
        title2.setStyleSheet("font-weight: bold; font-size: 14px; color: #FFFFFF;")
        vl.addWidget(title2)
        col2 = QVBoxLayout()
        col2.setSpacing(8)
        col2.addWidget(self._build_ts_stability_panel(2), 0)
        ts2_note = QLabel(
            "Temperature Stability 2 will only run if Temperature Stability 1 passes."
        )
        ts2_note.setWordWrap(True)
        ts2_note.setStyleSheet("color: #CCCCCC; font-size: 12px;")
        ts2_note.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        ts2_note.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        col2.addWidget(ts2_note, 0)
        w2 = QWidget()
        w2.setLayout(col2)
        w2.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        vl.addWidget(w2)
        vl.addStretch()
        scroll.setWidget(inner)
        lay.addWidget(scroll, 1)
        self.tabWidget.addTab(outer, "TEMP STABILITY")

    def _merge_ts_operation_block(self, slot: int, visible: dict) -> dict:
        """Defaults + last-loaded hidden keys + current visible fields (visible wins)."""
        out = dict(_TS_RECIPE_DEFAULTS)
        b = self._ts_slot_backup.get(slot)
        if isinstance(b, dict):
            out.update(b)
        out.update(visible)
        return out

    def _build_ts_stability_panel(self, slot: int) -> QWidget:
        d = self._ts_slot_widgets[slot]
        w = QWidget()
        w.setStyleSheet(RECIPE_TAB_STYLESHEET)
        w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)

        def _ts_spin(sb: QWidget, lo: int = 56, hi: int = 140) -> None:
            sb.setMinimumWidth(lo)
            sb.setMaximumWidth(hi)

        def _ts_line(le: QLineEdit, lo: int = 48, hi: int = 120) -> None:
            le.setMinimumWidth(lo)
            le.setMaximumWidth(hi)

        root = QVBoxLayout(w)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(GROUP_SPACING)

        top_band = QHBoxLayout()
        top_band.setSpacing(12)

        ctrl = QGroupBox("Control Parameters")
        ctrl.setStyleSheet(RECIPE_TAB_STYLESHEET)
        ctrl.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        cg = QGridLayout(ctrl)
        cg.setSpacing(8)
        cg.setContentsMargins(*GROUP_MARGINS)
        r = 0
        d["min_temp"] = QDoubleSpinBox()
        d["min_temp"].setRange(-200.0, 200.0)
        d["min_temp"].setDecimals(2)
        d["min_temp"].setValue(0.0)
        _ts_spin(d["min_temp"])
        cg.addWidget(QLabel("MIN Temp"), r, 0)
        cg.addWidget(d["min_temp"], r, 1)
        cg.addWidget(QLabel("°C"), r, 2)
        r += 1
        d["max_t"] = QDoubleSpinBox()
        d["max_t"].setRange(-200.0, 200.0)
        d["max_t"].setDecimals(2)
        d["max_t"].setValue(0.0)
        _ts_spin(d["max_t"])
        cg.addWidget(QLabel("MAX Temp"), r, 0)
        cg.addWidget(d["max_t"], r, 1)
        cg.addWidget(QLabel("°C"), r, 2)
        r += 1
        d["step"] = QDoubleSpinBox()
        d["step"].setRange(0.0, 50.0)
        d["step"].setDecimals(3)
        d["step"].setValue(0.0)
        _ts_spin(d["step"])
        cg.addWidget(QLabel("INC"), r, 0)
        cg.addWidget(d["step"], r, 1)
        cg.addWidget(QLabel("°C"), r, 2)
        r += 1
        d["wait_ms"] = QSpinBox()
        d["wait_ms"].setRange(0, 3_600_000)
        d["wait_ms"].setValue(0)
        _ts_spin(d["wait_ms"])
        cg.addWidget(QLabel("WAIT TIME"), r, 0)
        cg.addWidget(d["wait_ms"], r, 1)
        cg.addWidget(QLabel("ms"), r, 2)
        r += 1
        d["set_curr"] = QDoubleSpinBox()
        d["set_curr"].setRange(0.0, 5000.0)
        d["set_curr"].setDecimals(2)
        d["set_curr"].setValue(10.0)
        _ts_spin(d["set_curr"], 56, 160)
        d["use_rated"] = QCheckBox("Use I@Rated_P")
        hset = QHBoxLayout()
        hset.addWidget(d["set_curr"])
        hset.addWidget(QLabel("mA"))
        hset.addWidget(d["use_rated"])
        hset.addStretch()
        cg.addWidget(QLabel("Set Curr"), r, 0)
        cg.addLayout(hset, r, 1, 1, 2)
        r += 1
        d["initial"] = QDoubleSpinBox()
        d["initial"].setRange(-200.0, 200.0)
        d["initial"].setDecimals(2)
        d["initial"].setValue(0.0)
        _ts_spin(d["initial"])
        cg.addWidget(QLabel("Init Temp"), r, 0)
        cg.addWidget(d["initial"], r, 1)
        cg.addWidget(QLabel("°C"), r, 2)
        cg.setColumnStretch(1, 1)
        top_band.addWidget(ctrl, 1)

        ando = QGroupBox("Ando Parameters")
        ando.setStyleSheet(RECIPE_TAB_STYLESHEET)
        ando.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        ag = QGridLayout(ando)
        ag.setSpacing(8)
        ag.setContentsMargins(*GROUP_MARGINS)
        r = 0
        d["span_nm"] = QDoubleSpinBox()
        d["span_nm"].setRange(0.0, 500.0)
        d["span_nm"].setDecimals(3)
        d["span_nm"].setValue(0.0)
        _ts_spin(d["span_nm"])
        ag.addWidget(QLabel("Span"), r, 0)
        ag.addWidget(d["span_nm"], r, 1)
        ag.addWidget(QLabel("nm"), r, 2)
        r += 1
        d["smpl"] = QSpinBox()
        d["smpl"].setRange(0, 20001)
        d["smpl"].setValue(0)
        _ts_spin(d["smpl"])
        ag.addWidget(QLabel("Sampling"), r, 0)
        ag.addWidget(d["smpl"], r, 1)
        r += 1
        d["continuous_scan"] = QCheckBox("Continuous Scan")
        ag.addWidget(d["continuous_scan"], r, 0, 1, 3)
        ag.setColumnStretch(1, 1)

        mid_col = QWidget()
        mid_col.setStyleSheet(RECIPE_TAB_STYLESHEET)
        mid_col.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        mid_v = QVBoxLayout(mid_col)
        mid_v.setContentsMargins(0, 0, 0, 0)
        mid_v.setSpacing(8)
        mid_v.addWidget(ando)
        off_row1 = QHBoxLayout()
        off_row1.setSpacing(10)
        d["offset1"] = QLineEdit("10")
        _ts_line(d["offset1"])
        d["offset2"] = QLineEdit("0")
        _ts_line(d["offset2"])
        off_row1.addWidget(QLabel("Offset1"))
        off_row1.addWidget(d["offset1"])
        off_row1.addWidget(QLabel("Offset2"))
        off_row1.addWidget(d["offset2"])
        off_row1.addStretch()
        mid_v.addLayout(off_row1)
        off_row2 = QHBoxLayout()
        off_row2.setSpacing(10)
        d["deg_stability"] = QSpinBox()
        d["deg_stability"].setRange(1, 50)
        d["deg_stability"].setValue(5)
        _ts_spin(d["deg_stability"], 44, 88)
        d["deg_stability"].setToolTip(
            "Required continuous stable temperature span (°C) to qualify, then hot→cold check. "
            "Saved as DegOfStability."
        )
        off_row2.addWidget(QLabel("Deg of Stability"))
        off_row2.addWidget(d["deg_stability"])
        off_row2.addStretch()
        mid_v.addLayout(off_row2)
        d["recovery_step"] = QDoubleSpinBox()
        d["recovery_step"].setRange(0.0, 50.0)
        d["recovery_step"].setDecimals(2)
        d["recovery_step"].setValue(0.7)
        _ts_spin(d["recovery_step"])
        d["recovery_step"].setToolTip(
            "Min stability span (°C): minimum stable temperature range after an exceed before another exceed may occur. "
            "Saved as RecoveryStep_C in the recipe."
        )
        rec_row1 = QHBoxLayout()
        rec_row1.setSpacing(10)
        rec_row1.addWidget(QLabel("Min stability span"))
        rec_row1.addWidget(d["recovery_step"])
        rec_row1.addWidget(QLabel("°C"))
        rec_row1.addStretch()
        mid_v.addLayout(rec_row1)
        d["recovery_steps_count"] = QSpinBox()
        d["recovery_steps_count"].setRange(1, 20)
        d["recovery_steps_count"].setValue(2)
        _ts_spin(d["recovery_steps_count"], 44, 72)
        d["recovery_steps_count"].setToolTip(
            "Allow this many consecutive exceed temperatures; the next consecutive exceed resets the counter "
            "(no fail). Saved as RecoverySteps."
        )
        rec_row2 = QHBoxLayout()
        rec_row2.setSpacing(10)
        rec_row2.addWidget(QLabel("Recovery steps"))
        rec_row2.addWidget(d["recovery_steps_count"])
        rec_row2.addStretch()
        mid_v.addLayout(rec_row2)
        top_band.addWidget(mid_col, 1)

        lim = QGroupBox("Limits")
        lim.setStyleSheet(RECIPE_TAB_STYLESHEET)
        lim.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        lg = QGridLayout(lim)
        lg.setSpacing(6)
        lg.setContentsMargins(*GROUP_MARGINS)
        lg.addWidget(QLabel(""), 0, 0)
        h_ll = QLabel("LL")
        h_ul = QLabel("UL")
        h_en = QLabel("Enable")
        for hx, c in ((h_ll, 1), (h_ul, 2), (h_en, 3)):
            hx.setStyleSheet("font-weight: bold;")
            lg.addWidget(hx, 0, c)
        limit_names = ("FWHM", "SMSR", "Width1", "Width2", "WL", "Power", "Thorlabs")
        d["limits_entries"] = {}
        for ri, name in enumerate(limit_names, start=1):
            nm = QLabel(name)
            nm.setWordWrap(False)
            lg.addWidget(nm, ri, 0)
            ll_e = QLineEdit("0")
            ll_e.setMinimumWidth(48)
            ll_e.setMaximumWidth(100)
            ul_e = QLineEdit("0")
            ul_e.setMinimumWidth(48)
            ul_e.setMaximumWidth(100)
            en_e = QCheckBox()
            lg.addWidget(ll_e, ri, 1)
            if name == "Power":
                ul_e.setVisible(False)
                lg.addWidget(QLabel("—"), ri, 2)
            else:
                lg.addWidget(ul_e, ri, 2)
            lg.addWidget(en_e, ri, 3)
            d["limits_entries"][name] = {"ll": ll_e, "ul": ul_e, "enable": en_e}
        lg.setColumnStretch(1, 1)
        lg.setColumnStretch(2, 1)
        lim.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        top_band.addWidget(lim, 1)

        root.addLayout(top_band)

        foot_col = QVBoxLayout()
        foot_col.setSpacing(6)
        d["save_pdf"] = QCheckBox("Save PDF")
        foot_col.addWidget(d["save_pdf"])
        d["require_thorlabs"] = QCheckBox("Require Thorlabs")
        d["require_thorlabs"].setToolTip(
            "When checked, temperature stability requires a connected Thorlabs powermeter. "
            "Saved as ThorlabsRequired."
        )
        foot_col.addWidget(d["require_thorlabs"])
        root.addLayout(foot_col)

        return w

    def _create_ando_settings_tab(self):
        ando_tab = QWidget()
        ando_tab.setStyleSheet(RECIPE_TAB_STYLESHEET)
        ando_layout = QHBoxLayout(ando_tab)
        ando_layout.setContentsMargins(15, 15, 15, 15)
        ando_layout.setSpacing(15)
        ando_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)
        ctrl_group = QGroupBox("Control Parameters")
        ctrl_grid = QGridLayout(ctrl_group)
        ctrl_grid.setSpacing(GROUP_SPACING)
        ctrl_grid.setContentsMargins(*GROUP_MARGINS)
        row = 0
        current_label = QLabel("Current")
        self._apply_font_to_widget(current_label, 'label')
        ctrl_grid.addWidget(current_label, row, 0)
        self.andoCurrentSpin = QSpinBox()
        self._apply_font_to_widget(self.andoCurrentSpin, 'input')
        self.andoCurrentSpin.setRange(0, 9999)
        self.andoCurrentSpin.setValue(0)
        self.andoCurrentSpin.setFixedWidth(75)
        ctrl_grid.addWidget(self.andoCurrentSpin, row, 1)
        ma_label = QLabel("mA")
        self._apply_font_to_widget(ma_label, 'label')
        ctrl_grid.addWidget(ma_label, row, 2)
        analysis_label = QLabel("Analysis")
        self._apply_font_to_widget(analysis_label, 'label')
        ctrl_grid.addWidget(analysis_label, row, 3)
        self.analysisCombo = QComboBox()
        self._apply_font_to_widget(self.analysisCombo, 'input')
        self.analysisCombo.addItems(["DFB-LD", "FP-LD", "LED"])
        self.analysisCombo.setFixedWidth(100)
        ctrl_grid.addWidget(self.analysisCombo, row, 4)
        row += 1
        res_label = QLabel("Res(nm)")
        self._apply_font_to_widget(res_label, 'label')
        ctrl_grid.addWidget(res_label, row, 0)
        self.andoResSpin = QDoubleSpinBox()
        self._apply_font_to_widget(self.andoResSpin, 'input')
        self.andoResSpin.setRange(0.01, 10.0)
        self.andoResSpin.setValue(0.01)
        self.andoResSpin.setDecimals(2)
        self.andoResSpin.setSingleStep(0.01)
        self.andoResSpin.setFixedWidth(75)
        ctrl_grid.addWidget(self.andoResSpin, row, 1)
        sensitivity_label = QLabel("Sensitivity")
        self._apply_font_to_widget(sensitivity_label, 'label')
        ctrl_grid.addWidget(sensitivity_label, row, 3)
        self.sensitivityCombo = QComboBox()
        self._apply_font_to_widget(self.sensitivityCombo, 'input')
        self.sensitivityCombo.addItems(["Low", "Medium", "High"])
        self.sensitivityCombo.setCurrentText("Medium")
        self.sensitivityCombo.setFixedWidth(100)
        ctrl_grid.addWidget(self.sensitivityCombo, row, 4)
        row += 1
        avg_label = QLabel("Average")
        self._apply_font_to_widget(avg_label, 'label')
        ctrl_grid.addWidget(avg_label, row, 0)
        self.andoAvgSpin = QSpinBox()
        self._apply_font_to_widget(self.andoAvgSpin, 'input')
        self.andoAvgSpin.setRange(1, 100)
        self.andoAvgSpin.setValue(1)
        self.andoAvgSpin.setFixedWidth(75)
        ctrl_grid.addWidget(self.andoAvgSpin, row, 1)
        active_trace_label = QLabel("Active Trace")
        self._apply_font_to_widget(active_trace_label, 'label')
        ctrl_grid.addWidget(active_trace_label, row, 3)
        self.activeTraceCombo = QComboBox()
        self._apply_font_to_widget(self.activeTraceCombo, 'input')
        self.activeTraceCombo.addItems(["TraceA", "TraceB", "TraceC"])
        self.activeTraceCombo.setFixedWidth(100)
        ctrl_grid.addWidget(self.activeTraceCombo, row, 4)
        row += 1
        sampling_label = QLabel("Sampling")
        self._apply_font_to_widget(sampling_label, 'label')
        ctrl_grid.addWidget(sampling_label, row, 0)
        self.andoSamplingSpin = QSpinBox()
        self._apply_font_to_widget(self.andoSamplingSpin, 'input')
        self.andoSamplingSpin.setRange(1, 10000)
        self.andoSamplingSpin.setValue(500)
        self.andoSamplingSpin.setFixedWidth(75)
        ctrl_grid.addWidget(self.andoSamplingSpin, row, 1)
        air_vac_label = QLabel("Air/Vac")
        self._apply_font_to_widget(air_vac_label, 'label')
        ctrl_grid.addWidget(air_vac_label, row, 3)
        self.airVacCombo = QComboBox()
        self._apply_font_to_widget(self.airVacCombo, 'input')
        self.airVacCombo.addItems(["Air", "Vac"])
        self.airVacCombo.setFixedWidth(100)
        ctrl_grid.addWidget(self.airVacCombo, row, 4)
        row += 1
        center_label = QLabel("Center/Start")
        self._apply_font_to_widget(center_label, 'label')
        ctrl_grid.addWidget(center_label, row, 0)
        self.andoCenterSpin = QDoubleSpinBox()
        self._apply_font_to_widget(self.andoCenterSpin, 'input')
        self.andoCenterSpin.setRange(0.0, 9999.999)
        self.andoCenterSpin.setValue(0.000)
        self.andoCenterSpin.setDecimals(3)
        self.andoCenterSpin.setSingleStep(0.001)
        self.andoCenterSpin.setFixedWidth(75)
        ctrl_grid.addWidget(self.andoCenterSpin, row, 1)
        pulse_cw_label = QLabel("Pulse/CW")
        self._apply_font_to_widget(pulse_cw_label, 'label')
        ctrl_grid.addWidget(pulse_cw_label, row, 3)
        self.pulseCwCombo = QComboBox()
        self._apply_font_to_widget(self.pulseCwCombo, 'input')
        self.pulseCwCombo.addItems(["Pulse", "CW"])
        self.pulseCwCombo.setFixedWidth(100)
        ctrl_grid.addWidget(self.pulseCwCombo, row, 4)
        row += 1
        span_label = QLabel("Span/Stop")
        self._apply_font_to_widget(span_label, 'label')
        ctrl_grid.addWidget(span_label, row, 0)
        self.andoSpanSpin = QDoubleSpinBox()
        self._apply_font_to_widget(self.andoSpanSpin, 'input')
        self.andoSpanSpin.setRange(0.0, 9999.999)
        self.andoSpanSpin.setValue(0.000)
        self.andoSpanSpin.setDecimals(3)
        self.andoSpanSpin.setSingleStep(0.001)
        self.andoSpanSpin.setFixedWidth(75)
        ctrl_grid.addWidget(self.andoSpanSpin, row, 1)
        range_sw_label = QLabel("Range Sw")
        self._apply_font_to_widget(range_sw_label, 'label')
        ctrl_grid.addWidget(range_sw_label, row, 3)
        self.rangeSwCombo = QComboBox()
        self._apply_font_to_widget(self.rangeSwCombo, 'input')
        self.rangeSwCombo.addItems(["Center&Span", "Start&Stop"])
        self.rangeSwCombo.setFixedWidth(100)
        ctrl_grid.addWidget(self.rangeSwCombo, row, 4)
        row += 1
        level_scale_label = QLabel("Level Scale")
        self._apply_font_to_widget(level_scale_label, 'label')
        ctrl_grid.addWidget(level_scale_label, row, 3)
        self.levelScaleSpin = QDoubleSpinBox()
        self._apply_font_to_widget(self.levelScaleSpin, 'input')
        self.levelScaleSpin.setRange(-100.0, 100.0)
        self.levelScaleSpin.setValue(0.0)
        self.levelScaleSpin.setDecimals(1)
        self.levelScaleSpin.setSingleStep(0.1)
        self.levelScaleSpin.setFixedWidth(75)
        ctrl_grid.addWidget(self.levelScaleSpin, row, 4)
        db_label = QLabel("dB")
        self._apply_font_to_widget(db_label, 'label')
        ctrl_grid.addWidget(db_label, row, 5)
        row += 1
        ref_level_label = QLabel("Ref Level")
        self._apply_font_to_widget(ref_level_label, 'label')
        ctrl_grid.addWidget(ref_level_label, row, 0)
        self.andoRefLevelSpin = QDoubleSpinBox()
        self._apply_font_to_widget(self.andoRefLevelSpin, 'input')
        self.andoRefLevelSpin.setRange(-100.0, 100.0)
        self.andoRefLevelSpin.setValue(-10.0)
        self.andoRefLevelSpin.setDecimals(1)
        self.andoRefLevelSpin.setSingleStep(0.1)
        self.andoRefLevelSpin.setFixedWidth(75)
        ctrl_grid.addWidget(self.andoRefLevelSpin, row, 1)
        auto_analysis_label = QLabel("Auto Analysis")
        self._apply_font_to_widget(auto_analysis_label, 'label')
        ctrl_grid.addWidget(auto_analysis_label, row, 3)
        self.autoAnalysisCheck = QCheckBox()
        self._apply_font_to_widget(self.autoAnalysisCheck, 'input')
        self.autoAnalysisCheck.setStyleSheet("QCheckBox::indicator { width: 40px; height: 20px; }")
        ctrl_grid.addWidget(self.autoAnalysisCheck, row, 4)
        row += 1
        temp_label = QLabel("Temp")
        self._apply_font_to_widget(temp_label, 'label')
        ctrl_grid.addWidget(temp_label, row, 0)
        self.andoTempSpin = QSpinBox()
        self._apply_font_to_widget(self.andoTempSpin, 'input')
        self.andoTempSpin.setRange(0, 200)
        self.andoTempSpin.setValue(10)
        self.andoTempSpin.setFixedWidth(75)
        ctrl_grid.addWidget(self.andoTempSpin, row, 1)
        c_label = QLabel("C")
        self._apply_font_to_widget(c_label, 'label')
        ctrl_grid.addWidget(c_label, row, 2)
        wl_shift_label = QLabel("WL Shift")
        self._apply_font_to_widget(wl_shift_label, 'label')
        ctrl_grid.addWidget(wl_shift_label, row, 3)
        self.wlShiftSpin = QSpinBox()
        self._apply_font_to_widget(self.wlShiftSpin, 'input')
        self.wlShiftSpin.setRange(-999, 999)
        self.wlShiftSpin.setValue(0)
        self.wlShiftSpin.setFixedWidth(75)
        ctrl_grid.addWidget(self.wlShiftSpin, row, 4)
        left_layout.addWidget(ctrl_group)
        self.useCurrentRatedPowerCheck = QCheckBox("Use Current@Rated Power")
        self._apply_font_to_widget(self.useCurrentRatedPowerCheck, 'label')
        left_layout.addWidget(self.useCurrentRatedPowerCheck)
        left_layout.addStretch()
        ando_layout.addWidget(left_widget, 7)
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(5)
        limits_group = QGroupBox("Limits")
        limits_grid = QGridLayout(limits_group)
        limits_grid.setSpacing(GROUP_SPACING)
        limits_grid.setContentsMargins(*GROUP_MARGINS)
        ll_header = QLabel("LL")
        self._apply_font_to_widget(ll_header, 'label')
        limits_grid.addWidget(ll_header, 0, 1)
        ul_header = QLabel("UL")
        self._apply_font_to_widget(ul_header, 'label')
        limits_grid.addWidget(ul_header, 0, 2)
        enable_header = QLabel("Enable")
        self._apply_font_to_widget(enable_header, 'label')
        limits_grid.addWidget(enable_header, 0, 3)
        limit_params = ["Peak WL", "FWHM", "Cen WL", "SMSR"]
        self.limits_entries = {}
        for i, param in enumerate(limit_params):
            row = i + 1
            param_label = QLabel(param)
            self._apply_font_to_widget(param_label, 'label')
            limits_grid.addWidget(param_label, row, 0)
            ll_entry = QLineEdit("10")
            self._apply_font_to_widget(ll_entry, 'input')
            ll_entry.setFixedWidth(60)
            limits_grid.addWidget(ll_entry, row, 1)
            ul_entry = QLineEdit("10")
            self._apply_font_to_widget(ul_entry, 'input')
            ul_entry.setFixedWidth(60)
            limits_grid.addWidget(ul_entry, row, 2)
            enable_check = QCheckBox()
            self._apply_font_to_widget(enable_check, 'input')
            limits_grid.addWidget(enable_check, row, 3)
            self.limits_entries[param] = {'ll': ll_entry, 'ul': ul_entry, 'enable': enable_check}
        right_layout.addWidget(limits_group)
        boxes_row = QHBoxLayout()
        boxes_row.setSpacing(10)
        box1 = QGroupBox("")
        box1_grid = QGridLayout(box1)
        box1_grid.setContentsMargins(10, 15, 10, 10)
        box1_grid.setSpacing(5)
        box1_grid.setVerticalSpacing(5)
        smsrmsk_label = QLabel("SMSRMsk")
        self._apply_font_to_widget(smsrmsk_label, 'label')
        box1_grid.addWidget(smsrmsk_label, 0, 0)
        self.smsrEntry1 = QLineEdit("0")
        self._apply_font_to_widget(self.smsrEntry1, 'input')
        self.smsrEntry1.setFixedWidth(60)
        self.smsrEntry1.setFixedHeight(25)
        box1_grid.addWidget(self.smsrEntry1, 1, 0)
        th_label = QLabel("TH")
        self._apply_font_to_widget(th_label, 'label')
        box1_grid.addWidget(th_label, 0, 1)
        self.smsrTh = QLineEdit("0")
        self._apply_font_to_widget(self.smsrTh, 'input')
        self.smsrTh.setFixedWidth(60)
        self.smsrTh.setFixedHeight(25)
        box1_grid.addWidget(self.smsrTh, 1, 1)
        k_label = QLabel("K")
        self._apply_font_to_widget(k_label, 'label')
        box1_grid.addWidget(k_label, 2, 0)
        self.smsrK = QLineEdit("0")
        self._apply_font_to_widget(self.smsrK, 'input')
        self.smsrK.setFixedWidth(60)
        self.smsrK.setFixedHeight(25)
        box1_grid.addWidget(self.smsrK, 3, 0)
        th2_label = QLabel("TH 2")
        self._apply_font_to_widget(th2_label, 'label')
        box1_grid.addWidget(th2_label, 2, 1)
        self.smsrTh2 = QLineEdit("0")
        self._apply_font_to_widget(self.smsrTh2, 'input')
        self.smsrTh2.setFixedWidth(60)
        self.smsrTh2.setFixedHeight(25)
        box1_grid.addWidget(self.smsrTh2, 3, 1)
        box1.setMaximumWidth(160)
        boxes_row.addWidget(box1, 1)
        box2 = QGroupBox("")
        box2_layout = QVBoxLayout(box2)
        box2_layout.setContentsMargins(10, 15, 10, 10)
        box2_layout.setSpacing(8)
        specwd_label = QLabel("SpecWd")
        self._apply_font_to_widget(specwd_label, 'label')
        box2_layout.addWidget(specwd_label)
        self.thresholdSpin = QSpinBox()
        self._apply_font_to_widget(self.thresholdSpin, 'input')
        self.thresholdSpin.setRange(0, 9999)
        self.thresholdSpin.setValue(0)
        self.thresholdSpin.setFixedWidth(90)
        self.thresholdSpin.setFixedHeight(25)
        box2_layout.addWidget(self.thresholdSpin)
        modefit_label = QLabel("ModeFit")
        self._apply_font_to_widget(modefit_label, 'label')
        box2_layout.addWidget(modefit_label)
        self.modeFitCombo = QComboBox()
        self._apply_font_to_widget(self.modeFitCombo, 'input')
        self.modeFitCombo.addItems(["OFF", "ON"])
        self.modeFitCombo.setFixedWidth(90)
        self.modeFitCombo.setFixedHeight(25)
        box2_layout.addWidget(self.modeFitCombo)
        boxes_row.addWidget(box2, 2)
        right_layout.addLayout(boxes_row)
        auto_ref_row = QHBoxLayout()
        auto_ref_label = QLabel("Auto Ref Level")
        self._apply_font_to_widget(auto_ref_label, 'label')
        auto_ref_row.addWidget(auto_ref_label)
        self.autoRefLevelCheck = QCheckBox()
        self.autoRefLevelCheck.setStyleSheet("QCheckBox::indicator { width: 40px; height: 20px; }")
        auto_ref_row.addWidget(self.autoRefLevelCheck)
        right_layout.addLayout(auto_ref_row)
        right_layout.addStretch()
        ando_layout.addWidget(right_widget, 3)
        return ando_tab

    def _create_wavemeter_settings_tab(self):
        wavemeter_tab = QWidget()
        wavemeter_tab.setStyleSheet(RECIPE_TAB_STYLESHEET)
        wavemeter_layout = QHBoxLayout(wavemeter_tab)
        wavemeter_layout.setContentsMargins(15, 15, 15, 15)
        wavemeter_layout.setSpacing(15)
        wavemeter_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        center_widget = QWidget()
        center_layout = QVBoxLayout(center_widget)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(GROUP_SPACING)
        q8326_group = QGroupBox("Q8326 Settings")
        q8326_group.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Minimum)
        q8326_layout = QFormLayout(q8326_group)
        q8326_layout.setSpacing(GROUP_SPACING)
        q8326_layout.setContentsMargins(*GROUP_MARGINS)
        q8326_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.wlRangeCombo = QComboBox()
        self._apply_font_to_widget(self.wlRangeCombo, 'input')
        self.wlRangeCombo.addItem("480nm - 1000nm")
        self.wlRangeCombo.setFixedWidth(INPUT_WIDTH_WIDE)
        q8326_layout.addRow("Wavelength Range:", self.wlRangeCombo)
        self.functionCombo = QComboBox()
        self._apply_font_to_widget(self.functionCombo, 'input')
        self.functionCombo.addItem("LASER")
        self.functionCombo.setFixedWidth(INPUT_WIDTH)
        q8326_layout.addRow("Function:", self.functionCombo)
        self.resolutionCombo = QComboBox()
        self._apply_font_to_widget(self.resolutionCombo, 'input')
        self.resolutionCombo.addItem("0.001nm")
        self.resolutionCombo.setFixedWidth(INPUT_WIDTH)
        q8326_layout.addRow("Resolution:", self.resolutionCombo)
        self.sampleModeCombo = QComboBox()
        self._apply_font_to_widget(self.sampleModeCombo, 'input')
        self.sampleModeCombo.addItem("RUN")
        self.sampleModeCombo.setFixedWidth(INPUT_WIDTH)
        q8326_layout.addRow("Sample Mode:", self.sampleModeCombo)
        self.avgCombo = QComboBox()
        self._apply_font_to_widget(self.avgCombo, 'input')
        self.avgCombo.addItems(["OFF", "ON"])
        self.avgCombo.setFixedWidth(INPUT_WIDTH)
        q8326_layout.addRow("AVG:", self.avgCombo)
        center_layout.addWidget(q8326_group)
        center_layout.addStretch()
        wavemeter_layout.addWidget(center_widget, 0)
        return wavemeter_tab

    def _load_liv_pass_fail_into_ui(self, liv_pfc: dict) -> None:
        """Fill LIV Pass/Fail grid from PASS_FAIL_CRITERIA.LIV (nested ll/ul/enable or legacy flat min/max keys)."""
        ent = getattr(self, "liv_criteria_entries", None) or {}
        if not isinstance(liv_pfc, dict):
            return
        legacy_flat = {
            "IT": ("min_threshold_mA", "max_threshold_mA"),
            "SE1": ("min_slope_efficiency", "max_slope_efficiency"),
            "L @ Ir": ("min_power_at_rated_mW", "max_power_at_rated_mW"),
            "I @ Lr": ("min_current_at_rated_mA", "max_current_at_rated_mA"),
            "V @ Ir": ("min_voltage_at_Ir_V", "max_voltage_at_Ir_V"),
            "V @ Lr": ("min_voltage_at_Lr_V", "max_voltage_at_Lr_V"),
            "PD @ Ir": ("min_pd_at_Ir", "max_pd_at_Ir"),
        }
        for param, widgets in ent.items():
            if not isinstance(widgets, dict):
                continue
            sub = liv_pfc.get(param)
            if isinstance(sub, dict):
                ll = sub.get("ll", sub.get("LL", ""))
                ul = sub.get("ul", sub.get("UL", ""))
                en = sub.get("enable", sub.get("Enable", False))
                if widgets.get("ll") is not None:
                    widgets["ll"].setText("" if ll is None else str(ll))
                if widgets.get("ul") is not None:
                    widgets["ul"].setText("" if ul is None else str(ul))
                if widgets.get("enable") is not None:
                    widgets["enable"].setChecked(bool(en))
            elif param in legacy_flat:
                kmin, kmax = legacy_flat[param]
                if kmin in liv_pfc or kmax in liv_pfc:
                    if widgets.get("ll") is not None:
                        widgets["ll"].setText(str(liv_pfc.get(kmin, "") or ""))
                    if widgets.get("ul") is not None:
                        widgets["ul"].setText(str(liv_pfc.get(kmax, "") or ""))
                    if widgets.get("enable") is not None:
                        widgets["enable"].setChecked(True)

    @staticmethod
    def _sanitize_recipe_filename_stem(name: str) -> str:
        stem = "".join(c for c in (name or "").strip() if c not in '<>:"/\\|?*').strip()
        return stem or "recipe"

    def _recipe_save_extension(self) -> str:
        """Keep the same format as the loaded file when applicable (.ini / .rcp / .json)."""
        p = getattr(self, "_last_saved_or_loaded_path", None)
        if p:
            ext = os.path.splitext(p)[1].lower()
            if ext in (".ini", ".rcp", ".json"):
                return ext
        return ".ini"

    def _disk_bound_recipe_stem(self) -> Optional[str]:
        """File name stem of the recipe file on disk we last loaded or saved to, or None."""
        p = getattr(self, "_last_saved_or_loaded_path", None)
        if not p or not os.path.isfile(p):
            return None
        return os.path.splitext(os.path.basename(p))[0]

    def _stem_matches_disk_binding(self, safe_name: str) -> bool:
        """False when the user changed RECIPE NAME vs the file autosave is bound to — skip autosave."""
        disk = self._disk_bound_recipe_stem()
        if disk is None:
            return True
        return disk.lower() == (safe_name or "").lower()

    def _browse_folder(self):
        path = QFileDialog.getExistingDirectory(self, "Select Save Directory")
        if path:
            self.savePathEdit.setText(path)
            self.save_path = path

    def _browse_recipe_file(self):
        recipes_folder = os.path.join(os.path.dirname(__file__), '..', 'recipes')
        if not os.path.exists(recipes_folder):
            recipes_folder = os.getcwd()
        filename, _ = QFileDialog.getOpenFileName(
            self,
            "Select Recipe File",
            recipes_folder,
            "INI / RCP (*.ini *.INI *.rcp *.RCP);;"
            "All Recipe Files (*.ini *.INI *.rcp *.RCP *.json *.JSON);;All Files (*.*)"
        )
        if filename:
            self.recipePathEdit.setText(filename)
            self._load_recipe_data(filename)

    def _load_recipe_data(self, filepath: str):
        try:
            self._suppress_recipe_autosave = True
            from operations.recipe_io import load_recipe_file

            data = load_recipe_file(filepath)
            if not data:
                QMessageBox.warning(
                    self,
                    "Load Error",
                    "Could not load recipe (empty, invalid, or unsupported format):\n{}".format(filepath),
                )
                return

            def safe_set_text(widget, value):
                if value is not None:
                    widget.setText(str(value))

            def safe_set_value(widget, value):
                if value is not None:
                    try:
                        widget.setValue(float(value) if isinstance(widget, QDoubleSpinBox) else int(value))
                    except Exception:
                        pass

            def safe_set_combo(widget, value):
                if value is not None:
                    idx = widget.findText(str(value))
                    if idx >= 0:
                        widget.setCurrentIndex(idx)

            def safe_set_check(widget, value):
                if value is not None:
                    widget.setChecked(bool(value))

            recipe_name = data.get('Recipe_Name', data.get('recipe_name', ''))
            if not recipe_name:
                recipe_name = os.path.splitext(os.path.basename(filepath))[0]
            safe_set_text(self.recipeNameEdit, recipe_name)
            general = data.get('GENERAL', data.get('General', {}))
            safe_set_text(self.commentsEdit, data.get('Description', general.get('Comments', '')))
            fiber_coupled = data.get('FiberCoupled', general.get('FiberCoupled', False))
            safe_set_check(self.fiberCoupledCheck, fiber_coupled)
            safe_set_text(self.wavelengthEdit, data.get('Wavelength', general.get('Wavelength', '')))
            test_seq = data.get('TEST_SEQUENCE', general.get('TestSequence', []))
            if test_seq and len(test_seq) > 0:
                self.numTestsSpin.setValue(len(test_seq))
                self._update_test_sequence()
                seq_list = list(test_seq)
                for i, test in enumerate(seq_list):
                    if i < len(self.test_sequence_combos) and test:
                        idx = self.test_sequence_combos[i].findText(test)
                        if idx >= 0:
                            self.test_sequence_combos[i].setCurrentIndex(idx)
                self.saved_selections = {i: seq_list[i] for i in range(len(seq_list))}

            def get_section(d, *keys):
                for key in keys:
                    val = d.get(key) if isinstance(d, dict) else None
                    if isinstance(val, dict):
                        return val
                return {}

            liv = get_section(data, 'LIV') or get_section(data.get('OPERATIONS', {}), 'LIV')
            safe_set_text(self.minCurrEdit, liv.get('min_current_mA', liv.get('MINCurr', '')))
            safe_set_text(self.maxCurrEdit, liv.get('max_current_mA', liv.get('MAXCurr', '')))
            safe_set_text(self.incEdit, liv.get('increment_mA', liv.get('INC', '')))
            safe_set_text(self.waitTimeEdit, liv.get('wait_time_ms', liv.get('WAIT TIME', '')))
            safe_set_value(self.tempSpin, liv.get('Temperature', liv.get('temperature', 25)))
            try:
                mult_v = liv.get("multiplier", liv.get("Mult", liv.get("mult", None)))
                if mult_v is not None and mult_v != "":
                    self.multSpin.setValue(max(0, min(100, int(float(mult_v)))))
            except Exception:
                pass
            safe_set_text(self.ratedCurrentEdit, liv.get('rated_current_mA', ''))
            safe_set_text(self.ratedPowerEdit, liv.get('rated_power_mW', ''))
            safe_set_text(self.sePointsEdit, liv.get('se_data_points', ''))
            per = get_section(data, 'PER') or get_section(data.get('OPERATIONS', {}), 'PER')
            safe_set_text(self.startAngleEdit, per.get('StartAngle', per.get('start_angle', '')))
            safe_set_text(self.travelDistEdit, per.get('TravelDistance', per.get('travel_distance', '')))
            safe_set_text(self.measSpeedEdit, per.get('MeasSpeed', per.get('meas_speed', '')))
            safe_set_text(self.setupSpeedEdit, per.get('SetupSpeed', per.get('setup_speed', '')))
            safe_set_text(self.actSpeedEdit, per.get('ActuatorSpeed', per.get('actuator_speed', '')))
            safe_set_text(self.actDistEdit, per.get('ActuatorDistance', per.get('actuator_distance', '')))
            spectrum = get_section(data, 'SPECTRUM', 'Spectrum') or get_section(data.get('OPERATIONS', {}), 'SPECTRUM')
            safe_set_value(self.andoCurrentSpin, spectrum.get('Current', spectrum.get('current', 0)))
            safe_set_value(self.andoResSpin, spectrum.get('Resolution', spectrum.get('resolution_nm', 0.01)))
            safe_set_value(self.andoAvgSpin, spectrum.get('Average', spectrum.get('average', 1)))
            safe_set_value(self.andoSamplingSpin, spectrum.get('Sampling', spectrum.get('sampling', 500)))
            safe_set_value(self.andoCenterSpin, spectrum.get('CenterWL', spectrum.get('center_nm', 0)))
            safe_set_value(self.andoSpanSpin, spectrum.get('Span', spectrum.get('span_nm', 0)))
            safe_set_value(self.andoRefLevelSpin, spectrum.get('RefLevel', spectrum.get('ref_level_dBm', -10)))
            safe_set_value(self.andoTempSpin, spectrum.get('Temperature', spectrum.get('temperature', 25)))
            safe_set_combo(self.analysisCombo, spectrum.get('Analysis', spectrum.get('analysis', '')))
            safe_set_combo(self.sensitivityCombo, spectrum.get('Sensitivity', spectrum.get('sensitivity', '')))
            safe_set_combo(self.activeTraceCombo, spectrum.get('active_trace', ''))
            safe_set_combo(self.airVacCombo, spectrum.get('air_vac', ''))
            safe_set_combo(self.pulseCwCombo, spectrum.get('pulse_cw', ''))
            safe_set_combo(self.rangeSwCombo, spectrum.get('range_switch', ''))
            safe_set_value(self.levelScaleSpin, spectrum.get('level_scale', 0))
            safe_set_check(self.autoAnalysisCheck, spectrum.get('auto_analysis', False))
            safe_set_value(self.wlShiftSpin, spectrum.get('wl_shift', 0))
            safe_set_check(
                self.useCurrentRatedPowerCheck,
                spectrum.get('use_current_rated_power', spectrum.get('UseRatedPower', False)),
            )
            safe_set_value(self.thresholdSpin, spectrum.get('threshold', 0))
            safe_set_combo(self.modeFitCombo, spectrum.get('mode_fit', ''))
            safe_set_check(self.autoRefLevelCheck, spectrum.get('auto_ref_level', False))
            safe_set_text(self.smsrEntry1, spectrum.get('SMSRMsk', spectrum.get('smsrmsk', '')))
            safe_set_text(self.smsrTh, spectrum.get('TH', spectrum.get('th', '')))
            safe_set_text(self.smsrK, spectrum.get('K', spectrum.get('k', '')))
            safe_set_text(self.smsrTh2, spectrum.get('TH2', spectrum.get('TH 2', spectrum.get('th2', ''))))
            lim = spectrum.get('limits') if isinstance(spectrum.get('limits'), dict) else {}
            for param, entries in getattr(self, 'limits_entries', {}).items():
                sub = lim.get(param) or lim.get(param.replace(' ', '')) or {}
                if isinstance(sub, dict):
                    safe_set_text(entries['ll'], sub.get('ll', ''))
                    safe_set_text(entries['ul'], sub.get('ul', ''))
                    safe_set_check(entries['enable'], sub.get('enable', False))
            wavelength = data.get('Wavelength') or general.get('Wavelength') or spectrum.get('CenterWL', 0)
            if wavelength and isinstance(wavelength, (int, float)) and wavelength > 0:
                safe_set_value(self.andoCenterSpin, wavelength)
            spec = get_section(data, 'spec') or {}
            wavemeter = spec.get('WAVEMETER', data.get('WAVEMETER', {}))
            if not isinstance(wavemeter, dict):
                wavemeter = {}
            ops = data.get("OPERATIONS") or data.get("operations") or {}
            smsr_corr_any = bool(wavemeter.get("smsr", False))
            if isinstance(ops, dict):
                for _slot in (1, 2):
                    _key = "Temperature Stability {}".format(_slot)
                    _ts = ops.get(_key) if isinstance(ops.get(_key), dict) else {}
                    if isinstance(_ts, dict):
                        smsr_corr_any = smsr_corr_any or bool(
                            _ts.get(
                                "SMSR_correction_enable",
                                _ts.get("EnableSMSR_correction", _ts.get("smsr_correction_enable", False)),
                            )
                        )
            safe_set_check(self.smsrCheckBox, smsr_corr_any)
            if isinstance(ops, dict) and getattr(self, "_ts_slot_widgets", None):
                for slot in (1, 2):
                    key = "Temperature Stability {}".format(slot)
                    ts = ops.get(key) if isinstance(ops.get(key), dict) else {}
                    d = self._ts_slot_widgets.get(slot) or {}
                    if not d:
                        continue
                    if isinstance(ts, dict):
                        self._ts_slot_backup[slot] = dict(ts)
                    else:
                        self._ts_slot_backup[slot] = {}
                    safe_set_value(d["min_temp"], ts.get("MinTemp", ts.get("min_temp_c", ts.get("MINTemp", 0))))
                    safe_set_value(d["max_t"], ts.get("MaxTemperature", ts.get("max_temp_c", 0)))
                    safe_set_value(d["step"], ts.get("TemperatureStep", ts.get("step_temp_c", 0)))
                    safe_set_value(d["wait_ms"], int(ts.get("WaitTime_ms", ts.get("wait_time_ms", 0)) or 0))
                    safe_set_value(d["set_curr"], float(ts.get("SetCurrent_mA", ts.get("set_current_mA", 10)) or 0))
                    safe_set_check(d["use_rated"], ts.get("UseI_at_Rated_P", ts.get("use_I_at_rated", False)))
                    safe_set_value(d["initial"], ts.get("InitialTemperature", ts.get("initial_temp_c", 0)))
                    safe_set_value(d["span_nm"], ts.get("StabilitySpan_nm", ts.get("span_nm", 0)))
                    safe_set_value(d["smpl"], ts.get("StabilitySampling", ts.get("sampling_points", 0)))
                    safe_set_check(d["continuous_scan"], ts.get("ContinuousScan", ts.get("continuous_scan", False)))
                    safe_set_text(d["offset1"], ts.get("Offset1_nm", ts.get("offset1", "10")))
                    safe_set_text(d["offset2"], ts.get("Offset2_nm", ts.get("offset2", "0")))
                    safe_set_check(d["save_pdf"], ts.get("SavePDF", ts.get("save_pdf", False)))
                    safe_set_check(
                        d["require_thorlabs"],
                        ts.get("ThorlabsRequired", ts.get("thorlabs_required", False)),
                    )
                    safe_set_value(d["deg_stability"], int(ts.get("DegOfStability", ts.get("deg_of_stability", 5)) or 5))
                    rs = ts.get("RecoveryStep_C", ts.get("recovery_step_C", ts.get("MinStabilitySpanAfterExceed_C")))
                    if rs is None or rs == "":
                        rs = 0.7
                    safe_set_value(d["recovery_step"], float(rs))
                    safe_set_value(
                        d["recovery_steps_count"],
                        int(ts.get("RecoverySteps", ts.get("recovery_steps", ts.get("Recovery_Steps", 2))) or 2),
                    )
                    lim = ts.get("limits") if isinstance(ts.get("limits"), dict) else {}
                    for pname, ent in (d.get("limits_entries") or {}).items():
                        if not isinstance(ent, dict):
                            continue
                        sub = lim.get(pname) if isinstance(lim.get(pname), dict) else {}
                        safe_set_text(ent.get("ll"), sub.get("ll", sub.get("LL", "0")))
                        if pname != "Power" and ent.get("ul") is not None:
                            safe_set_text(ent["ul"], sub.get("ul", sub.get("UL", "0")))
                        safe_set_check(ent.get("enable"), sub.get("enable", sub.get("Enable", False)))
            pfc = data.get("PASS_FAIL_CRITERIA") or data.get("PassFailCriteria") or {}
            if isinstance(pfc, dict):
                self._pass_fail_criteria_backup = dict(pfc)
                self._load_liv_pass_fail_into_ui(pfc.get("LIV") or {})
            # So Save works without Browse: remember file and set save folder.
            self._last_saved_or_loaded_path = os.path.abspath(filepath)
            ddir = os.path.dirname(self._last_saved_or_loaded_path)
            self.savePathEdit.setText(ddir)
            self.save_path = ddir
            QMessageBox.information(self, "Recipe Loaded", f"Recipe loaded successfully:\n{recipe_name}")
        except Exception as e:
            QMessageBox.warning(self, "Load Error", f"Failed to load recipe:\n{str(e)}")
        finally:
            self._suppress_recipe_autosave = False

    def _build_recipe_dict_from_ui(self) -> Dict[str, Any]:
        """Full recipe dict from current editor state (same as Save)."""
        recipe_name = (self.recipeNameEdit.text() or "").strip() or "recipe"
        test_sequence = [combo.currentText() if combo.currentText() else "" for combo in self.test_sequence_combos]

        def get_text(widget, default=""):
            try:
                return widget.text() if widget else default
            except Exception:
                return default

        def get_value(widget, default=0.0):
            try:
                return widget.value() if widget else default
            except Exception:
                return default

        def get_combo(widget, default=""):
            try:
                return widget.currentText() if widget else default
            except Exception:
                return default

        def get_checked(widget, default=False):
            try:
                return widget.isChecked() if widget else default
            except Exception:
                return default

        def get_float_from_lineedit(widget, default=0.0):
            raw = (get_text(widget, "") or "").strip()
            if raw == "":
                return float(default)
            try:
                return float(raw)
            except (TypeError, ValueError):
                return float(default)

        def get_int_from_lineedit(widget, default=0):
            raw = (get_text(widget, "") or "").strip()
            if raw == "":
                return int(default)
            try:
                return int(float(raw))
            except (TypeError, ValueError):
                return int(default)

        fiber_coupled = get_checked(self.fiberCoupledCheck)
        wavelength = get_text(self.wavelengthEdit).strip()
        comments_text = get_text(self.commentsEdit)
        drive_cur = float(get_value(self.andoCurrentSpin, 0.0))
        if drive_cur <= 0:
            drive_cur = float(get_float_from_lineedit(self.ratedCurrentEdit, 0.0))
        recipe: Dict[str, Any] = {
            "Recipe_Name": recipe_name,
            "Description": comments_text,
            "TEST_SEQUENCE": test_sequence,
            "FiberCoupled": fiber_coupled,
            "Wavelength": wavelength,
            "Current": drive_cur,
            "GENERAL": {
                "RecipeName": recipe_name,
                "Comments": comments_text,
                "NumTests": get_value(self.numTestsSpin, 1),
                "TestSequence": test_sequence,
                "FiberCoupled": fiber_coupled,
                "Wavelength": wavelength,
                "Current": drive_cur,
                "FPPath": get_checked(self.fpPathCheck),
                "SavePath": get_text(self.savePathEdit),
            },
            "OPERATIONS": {
                "LIV": {
                    "min_current_mA": get_float_from_lineedit(self.minCurrEdit, 0.0),
                    "max_current_mA": get_float_from_lineedit(self.maxCurrEdit, 0.0),
                    "increment_mA": get_float_from_lineedit(self.incEdit, 0.0),
                    "wait_time_ms": get_float_from_lineedit(self.waitTimeEdit, 0.0),
                    "temperature": get_value(self.tempSpin, 25),
                    "multiplier": get_value(self.multSpin, 1),
                    "rated_current_mA": get_float_from_lineedit(self.ratedCurrentEdit, 0.0),
                    "rated_power_mW": get_float_from_lineedit(self.ratedPowerEdit, 0.0),
                    "se_data_points": get_int_from_lineedit(self.sePointsEdit, 0),
                },
                "PER": {
                    "meas_speed": get_text(self.measSpeedEdit),
                    "setup_speed": get_text(self.setupSpeedEdit),
                    "start_angle": get_text(self.startAngleEdit),
                    "travel_distance": get_text(self.travelDistEdit),
                    "actuator_speed": get_text(self.actSpeedEdit),
                    "actuator_distance": get_text(self.actDistEdit),
                },
                "SPECTRUM": {
                    "current": get_value(self.andoCurrentSpin, 0),
                    "resolution_nm": get_value(self.andoResSpin, 0.01),
                    "average": get_value(self.andoAvgSpin, 1),
                    "sampling": get_value(self.andoSamplingSpin, 500),
                    "center_nm": get_value(self.andoCenterSpin, 0.0),
                    "span_nm": get_value(self.andoSpanSpin, 0.0),
                    "ref_level_dBm": get_value(self.andoRefLevelSpin, -10.0),
                    "level_scale": get_value(self.levelScaleSpin, 0.0),
                    "temperature": get_value(self.andoTempSpin, 25),
                    "wavelength": get_value(self.andoCenterSpin, 0.0),
                    "analysis": get_combo(self.analysisCombo, "DFB-LD"),
                    "sensitivity": get_combo(self.sensitivityCombo, "Medium"),
                    "active_trace": get_combo(self.activeTraceCombo, "TraceA"),
                    "air_vac": get_combo(self.airVacCombo, "Air"),
                    "pulse_cw": get_combo(self.pulseCwCombo, "CW"),
                    "range_switch": get_combo(self.rangeSwCombo, "Center&Span"),
                    "auto_analysis": get_checked(self.autoAnalysisCheck),
                    "use_current_rated_power": get_checked(self.useCurrentRatedPowerCheck),
                    "wl_shift": get_value(self.wlShiftSpin, 0),
                    "threshold": get_value(self.thresholdSpin, 0),
                    "mode_fit": get_combo(self.modeFitCombo, "OFF"),
                    "auto_ref_level": get_checked(self.autoRefLevelCheck),
                    "limits": {
                        param: {
                            "ll": get_text(ent["ll"]),
                            "ul": get_text(ent["ul"]),
                            "enable": get_checked(ent["enable"]),
                        }
                        for param, ent in getattr(self, "limits_entries", {}).items()
                    },
                    "SMSRMsk": get_text(self.smsrEntry1),
                    "TH": get_text(self.smsrTh),
                    "K": get_text(self.smsrK),
                    "TH2": get_text(self.smsrTh2),
                },
                "WAVEMETER": {
                    "wavelength_range": get_combo(self.wlRangeCombo, "480nm - 1000nm"),
                    "function": get_combo(self.functionCombo, "LASER"),
                    "resolution": get_combo(self.resolutionCombo, "0.001nm"),
                    "sample_mode": get_combo(self.sampleModeCombo, "RUN"),
                    "averaging": get_combo(self.avgCombo, "OFF"),
                    "smsr": get_checked(self.smsrCheckBox, False),
                },
            },
        }
        tw = getattr(self, "_ts_slot_widgets", None)
        if isinstance(tw, dict):
            for slot in (1, 2):
                d = tw.get(slot) or {}
                if not d:
                    continue
                limits_out = {}
                for pname, ent in (d.get("limits_entries") or {}).items():
                    if not isinstance(ent, dict):
                        continue
                    limits_out[pname] = {
                        "ll": get_text(ent.get("ll"), "0"),
                        "ul": "" if pname == "Power" else get_text(ent.get("ul"), "0"),
                        "enable": get_checked(ent.get("enable"), False),
                    }
                visible_ts = {
                    "MinTemp": float(get_value(d["min_temp"], 0.0)),
                    "MaxTemperature": float(get_value(d["max_t"], 0.0)),
                    "TemperatureStep": float(get_value(d["step"], 0.0)),
                    "WaitTime_ms": int(get_value(d["wait_ms"], 0)),
                    "SetCurrent_mA": float(get_value(d["set_curr"], 10.0)),
                    "UseI_at_Rated_P": get_checked(d["use_rated"], False),
                    "InitialTemperature": float(get_value(d["initial"], 0.0)),
                    "StabilitySpan_nm": float(get_value(d["span_nm"], 0.0)),
                    "StabilitySampling": int(get_value(d["smpl"], 0)),
                    "ContinuousScan": get_checked(d["continuous_scan"], False),
                    "SMSR_correction_enable": get_checked(self.smsrCheckBox, False),
                    "Offset1_nm": get_text(d["offset1"], "10"),
                    "Offset2_nm": get_text(d["offset2"], "0"),
                    "limits": limits_out,
                    "SavePDF": get_checked(d["save_pdf"], False),
                    "DegOfStability": int(get_value(d["deg_stability"], 5)),
                    "RecoveryStep_C": float(get_value(d["recovery_step"], 0.7)),
                    "RecoverySteps": int(get_value(d["recovery_steps_count"], 2)),
                    "ThorlabsRequired": get_checked(d["require_thorlabs"], False),
                }
                recipe["OPERATIONS"]["Temperature Stability {}".format(slot)] = self._merge_ts_operation_block(
                    slot, visible_ts
                )
        pfc_out = dict(getattr(self, "_pass_fail_criteria_backup", {}) or {})
        liv_ui = {}
        for param, ent in getattr(self, "liv_criteria_entries", {}).items():
            if not isinstance(ent, dict):
                continue
            liv_ui[param] = {
                "ll": get_text(ent.get("ll"), "0"),
                "ul": get_text(ent.get("ul"), "0"),
                "enable": get_checked(ent.get("enable"), False),
            }
        if liv_ui:
            liv_prev = pfc_out.get("LIV") if isinstance(pfc_out.get("LIV"), dict) else {}
            liv_merged = dict(liv_prev)
            liv_merged.update(liv_ui)
            pfc_out["LIV"] = liv_merged
        if pfc_out:
            recipe["PASS_FAIL_CRITERIA"] = pfc_out
        return recipe

    def _write_recipe_file(self, filename: str, recipe: Dict[str, Any], emit_signal: bool = True) -> None:
        """Write recipe to .ini (INI) or .rcp/.json (JSON). Updates paths and PASS_FAIL backup."""
        ext = os.path.splitext(filename)[1].lower()
        if ext == ".ini":
            from operations.recipe_io import save_recipe_ini

            save_recipe_ini(filename, recipe)
        else:
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(recipe, f, indent=4)
        self._last_saved_or_loaded_path = os.path.abspath(filename)
        self.savePathEdit.setText(os.path.dirname(self._last_saved_or_loaded_path))
        self.save_path = os.path.dirname(self._last_saved_or_loaded_path)
        if isinstance(recipe.get("PASS_FAIL_CRITERIA"), dict):
            self._pass_fail_criteria_backup = dict(recipe["PASS_FAIL_CRITERIA"])
        if emit_signal:
            self.recipe_saved.emit(self._last_saved_or_loaded_path)

    def _schedule_recipe_autosave(self) -> None:
        """Debounced save when limits / pass-fail fields change — keeps .rcp in sync without clicking Save."""
        if getattr(self, "_suppress_recipe_autosave", False):
            return
        if self._recipe_autosave_timer is None:
            self._recipe_autosave_timer = QTimer(self)
            self._recipe_autosave_timer.setSingleShot(True)
            self._recipe_autosave_timer.timeout.connect(self._do_recipe_autosave)
        self._recipe_autosave_timer.stop()
        self._recipe_autosave_timer.start(500)

    def _do_recipe_autosave(self) -> None:
        if getattr(self, "_suppress_recipe_autosave", False):
            return
        path = getattr(self, "_last_saved_or_loaded_path", None)
        if not path or not os.path.isfile(path):
            return
        safe_name = self._sanitize_recipe_filename_stem((self.recipeNameEdit.text() or "").strip())
        if not self._stem_matches_disk_binding(safe_name):
            return
        try:
            recipe = self._build_recipe_dict_from_ui()
            # Persist .rcp/.json/.ini without reloading main window on every keystroke
            self._write_recipe_file(path, recipe, emit_signal=False)
        except Exception:
            pass

    def _wire_limits_autosave(self) -> None:
        """Autosave loaded .rcp/.ini/.json when user edits limit or LIV criteria fields."""

        def hook(w):
            if isinstance(w, QLineEdit):
                w.textChanged.connect(self._schedule_recipe_autosave)
            elif isinstance(w, QCheckBox):
                w.stateChanged.connect(lambda _state: self._schedule_recipe_autosave())

        for _param, ent in getattr(self, "limits_entries", {}).items():
            if not isinstance(ent, dict):
                continue
            for k in ("ll", "ul"):
                if ent.get(k):
                    hook(ent[k])
            if ent.get("enable"):
                hook(ent["enable"])
        for slot in (1, 2):
            d = getattr(self, "_ts_slot_widgets", {}).get(slot) or {}
            for _pname, ent in (d.get("limits_entries") or {}).items():
                if not isinstance(ent, dict):
                    continue
                for k in ("ll", "ul"):
                    if ent.get(k) is not None:
                        hook(ent[k])
                if ent.get("enable"):
                    hook(ent["enable"])
        for _param, ent in getattr(self, "liv_criteria_entries", {}).items():
            if not isinstance(ent, dict):
                continue
            for k in ("ll", "ul"):
                if ent.get(k):
                    hook(ent[k])
            if ent.get("enable"):
                hook(ent["enable"])

    def _save_recipe(self):
        save_path = (self.savePathEdit.text() or "").strip()
        loaded = getattr(self, "_last_saved_or_loaded_path", None)
        # After Load Recipe, folder is filled automatically; still allow save if only linked path exists.
        if not save_path and loaded:
            save_path = os.path.dirname(os.path.abspath(loaded))
            self.savePathEdit.setText(save_path)
            self.save_path = save_path
        if not save_path:
            QMessageBox.critical(
                self,
                "Error",
                "Save path not selected.\n\n"
                "Click Browse to choose a folder, or use Load Recipe — the folder is set automatically.",
            )
            return
        recipe_name = (self.recipeNameEdit.text() or "").strip()
        if not recipe_name:
            QMessageBox.critical(self, "Error", "Recipe name is empty")
            return
        safe_name = self._sanitize_recipe_filename_stem(recipe_name)
        ext = self._recipe_save_extension()
        disk_stem = self._disk_bound_recipe_stem()
        if disk_stem is not None and safe_name.lower() != disk_stem.lower():
            entered, ok = QInputDialog.getText(
                self,
                "Save recipe file name",
                "The recipe name no longer matches the loaded file {!r}.\n\n"
                "Enter the file name to save as (no extension; {} will be added):".format(disk_stem, ext),
                text=safe_name,
            )
            if not ok:
                return
            safe_name = self._sanitize_recipe_filename_stem(entered)
            self.recipeNameEdit.setText(safe_name)
        filename = os.path.normpath(os.path.join(save_path, f"{safe_name}{ext}"))
        loaded_abs = os.path.abspath(loaded) if loaded and os.path.isfile(loaded) else ""
        if os.path.isfile(filename) and (not loaded_abs or os.path.normcase(filename) != os.path.normcase(loaded_abs)):
            reply = QMessageBox.question(
                self,
                "Replace file?",
                "A file already exists at:\n{}\n\nReplace it?".format(filename),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
        try:
            recipe = self._build_recipe_dict_from_ui()
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to build recipe:\n{str(e)}")
            return
        try:
            self._write_recipe_file(filename, recipe)
            try:
                self.recipePathEdit.setText(filename)
            except Exception:
                pass
            QMessageBox.information(self, "Saved", f"Recipe saved:\n{filename}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save recipe:\n{str(e)}")


if __name__ == "__main__":
    from start.window_placement import place_on_secondary_screen_before_show
    app = QApplication(sys.argv)
    window = RecipeWindow()
    place_on_secondary_screen_before_show(window, None, maximize=True)
    window.show()
    sys.exit(app.exec_())
