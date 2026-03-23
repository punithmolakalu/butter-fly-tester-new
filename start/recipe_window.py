"""
Full Recipe window (QMainWindow) for creating/editing recipes.
Opens maximized on the secondary monitor when user clicks New Recipe from the main GUI.
"""
import sys
import json
import os
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
    QFormLayout,
    QFrame,
    QSizePolicy,
    QApplication,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont

from view.dark_theme import get_dark_palette, main_stylesheet, set_dark_title_bar

# Arrow icons for spinbox (up/down) from resource folder
_resource_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "resource")
def _arrow_url(name):
    p = os.path.abspath(os.path.join(_resource_dir, name + ".png")).replace("\\", "/").replace(" ", "%20")
    return "file:///" + p if os.name == "nt" else "file://" + p
_arrow_up = _arrow_url("arrow_up")
_arrow_down = _arrow_url("arrow_down")

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
    QSpinBox::up-arrow { width: 16px; height: 16px; image: url("%s"); }
    QSpinBox::down-arrow { width: 16px; height: 16px; image: url("%s"); }
    QDoubleSpinBox::up-arrow { width: 16px; height: 16px; image: url("%s"); }
    QDoubleSpinBox::down-arrow { width: 16px; height: 16px; image: url("%s"); }
""" % (_arrow_up, _arrow_down, _arrow_up, _arrow_down) + """
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


class RecipeWindow(QMainWindow):
    def __init__(self, parent=None):
        super().__init__(None)
        self.setWindowTitle("NEW RECIPE")

        self.setGeometry(100, 100, 1200, 800)
        self.setMinimumSize(1200, 800)

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
        self.savePathEdit.setMinimumWidth(500)
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
        main_layout.addWidget(self.tabWidget)
        self._create_general_tab()
        self._create_per_tab()
        self._create_liv_tab()
        self._create_spectrum_tab()
        self._create_temp_stability_tab()

    def _create_general_tab(self):
        gen_tab = QWidget()
        gen_tab.setStyleSheet(RECIPE_TAB_STYLESHEET)
        gen_layout = QVBoxLayout(gen_tab)
        gen_layout.setContentsMargins(15, 15, 15, 15)
        gen_layout.setSpacing(GROUP_SPACING)
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
        self.smsrCheckBox = QCheckBox("SMSR")
        self.smsrCheckBox.setChecked(False)
        self._apply_font_to_widget(self.smsrCheckBox, 'label')
        seq_header_layout.addWidget(self.smsrCheckBox)
        seq_header_layout.addStretch()
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
        out = list(sequence)
        i = 0
        while i < len(out):
            if out[i] in ("Temperature Stability 1", "Temperature Stability 2"):
                if "Spectrum" not in out[:i]:
                    out.insert(i, "Spectrum")
                    i += 1
            i += 1
        i = 0
        while i < len(out) - 1:
            if out[i] == "Temperature Stability 1" and out[i + 1] == "Temperature Stability 1":
                out.pop(i + 1)
                continue
            if out[i] == "Temperature Stability 2" and out[i + 1] == "Temperature Stability 2":
                out.pop(i + 1)
                continue
            i += 1
        return out

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
        test_options = ["LIV", "PER", "Spectrum", "WLvsTemp", "WLvsCurrent",
                        "Temperature Stability 1", "Temperature Stability 2", "Stability"]
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
        for col_layout in columns:
            col_widget = QWidget()
            col_widget.setLayout(col_layout)
            col_widget.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
            main_row_layout.addWidget(col_widget, 0, Qt.AlignmentFlag.AlignTop)
        main_row_layout.addStretch()
        self.seqLayout.addLayout(main_row_layout)
        for i, combo in enumerate(self.test_sequence_combos):
            combo.currentIndexChanged.connect(lambda new_index, idx=i: self._on_sequence_combo_changed(idx))

    def _on_sequence_combo_changed(self, index: int):
        if self._suppress_sequence_rule:
            return
        if index >= len(self.test_sequence_combos):
            return
        current = self.test_sequence_combos[index].currentText()
        if current not in ("Temperature Stability 1", "Temperature Stability 2"):
            return
        sequence = [c.currentText() if c.currentText() else "" for c in self.test_sequence_combos]
        if "Spectrum" in sequence[:index]:
            return
        new_sequence = sequence[:index] + ["Spectrum"] + sequence[index:]
        self.saved_selections = {i: new_sequence[i] for i in range(len(new_sequence))}
        self._suppress_sequence_rule = True
        try:
            self.numTestsSpin.setValue(len(new_sequence))
            self._update_test_sequence()
        finally:
            self._suppress_sequence_rule = False

    def _create_per_tab(self):
        per_tab = QWidget()
        per_tab.setStyleSheet(RECIPE_TAB_STYLESHEET)
        per_layout = QHBoxLayout(per_tab)
        per_layout.setContentsMargins(15, 15, 15, 15)
        per_layout.setSpacing(15)
        per_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        per_layout.addStretch(1)
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
        motor_layout.addRow("Starting Angle:", self.startAngleEdit)
        self.travelDistEdit = QLineEdit()
        self.travelDistEdit.setFixedWidth(INPUT_WIDTH)
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
        act_layout.addRow("Speed:", self.actSpeedEdit)
        self.actDistEdit = QLineEdit()
        self.actDistEdit.setFixedWidth(INPUT_WIDTH)
        act_layout.addRow("Distance:", self.actDistEdit)
        center_layout.addWidget(act_group, 0)
        per_layout.addWidget(center_widget, 0)
        per_layout.addStretch(1)
        self.tabWidget.addTab(per_tab, "PER")

    def _create_liv_tab(self):
        liv_tab = QWidget()
        liv_tab.setStyleSheet(RECIPE_TAB_STYLESHEET)
        liv_layout = QHBoxLayout(liv_tab)
        liv_layout.setContentsMargins(15, 15, 15, 15)
        liv_layout.setSpacing(15)
        liv_layout.addStretch(1)
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
        for i, (param, unit1, unit2) in enumerate(criteria_params):
            row = i + 1
            criteria_layout.addWidget(QLabel(param), row, 0)
            ll_entry = QLineEdit("0")
            criteria_layout.addWidget(ll_entry, row, 1)
            if unit1:
                criteria_layout.addWidget(QLabel(unit1), row, 1, Qt.AlignmentFlag.AlignRight)
            ul_entry = QLineEdit("0")
            criteria_layout.addWidget(ul_entry, row, 2)
            if unit2:
                criteria_layout.addWidget(QLabel(unit2), row, 2, Qt.AlignmentFlag.AlignRight)
            enable_check = QCheckBox()
            criteria_layout.addWidget(enable_check, row, 3)
        right_layout.addWidget(criteria_group)
        right_layout.addStretch()
        liv_layout.addWidget(right_column, 0)
        liv_layout.addStretch(1)
        self.tabWidget.addTab(liv_tab, "LIV")

    def _create_spectrum_tab(self):
        spec_tab = QWidget()
        spec_tab.setStyleSheet(RECIPE_TAB_STYLESHEET)
        spec_layout = QVBoxLayout(spec_tab)
        spec_layout.setContentsMargins(5, 5, 5, 5)
        spec_notebook = QTabWidget()
        ando_tab = self._create_ando_settings_tab()
        spec_notebook.addTab(ando_tab, "Ando Settings")
        wavemeter_tab = self._create_wavemeter_settings_tab()
        spec_notebook.addTab(wavemeter_tab, "Wavemeter Settings")
        spec_layout.addWidget(spec_notebook)
        self.tabWidget.addTab(spec_tab, "SPECTRUM")

    def _create_ando_settings_tab(self):
        ando_tab = QWidget()
        ando_tab.setStyleSheet(RECIPE_TAB_STYLESHEET)
        ando_layout = QHBoxLayout(ando_tab)
        ando_layout.setContentsMargins(15, 15, 15, 15)
        ando_layout.setSpacing(15)
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
        auto_ref_row.addStretch()
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
        wavemeter_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        wavemeter_layout.addStretch(1)
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
        wavemeter_layout.addStretch(1)
        return wavemeter_tab

    def _create_temp_stability_tab(self):
        tempstab_tab = QWidget()
        tempstab_tab.setStyleSheet(RECIPE_TAB_STYLESHEET)
        tempstab_layout = QVBoxLayout(tempstab_tab)
        tempstab_layout.setContentsMargins(15, 15, 15, 15)
        tempstab_layout.setSpacing(15)
        ts1_group = self._create_temp_stability_block("Temperature Stability 1")
        tempstab_layout.addWidget(ts1_group)
        ts2_group = self._create_temp_stability_block("Temperature Stability 2")
        tempstab_layout.addWidget(ts2_group)
        tempstab_layout.addWidget(QLabel("Temperature Stability 2 will only run if Temperature Stability 1 passes."))
        tempstab_layout.addStretch()
        self.tabWidget.addTab(tempstab_tab, "Temperature Stability")

    def _create_temp_stability_block(self, title):
        main_group = QGroupBox(title)
        main_layout = QHBoxLayout(main_group)
        main_layout.setSpacing(GROUP_SPACING)
        ctrl_group = QGroupBox("Control Parameters")
        ctrl_layout = QFormLayout(ctrl_group)
        ctrl_layout.setSpacing(GROUP_SPACING)
        ctrl_layout.setContentsMargins(*GROUP_MARGINS)
        ctrl_layout.addRow("MINTemp (C):", QLineEdit("0"))
        ctrl_layout.addRow("MAXTemp (C):", QLineEdit("0"))
        ctrl_layout.addRow("INC (C):", QLineEdit("0"))
        ctrl_layout.addRow("WAIT TIME (ms):", QLineEdit("0"))
        ctrl_layout.addRow("Set Curr (mA):", QLineEdit("10"))
        ctrl_layout.addRow("", QCheckBox("Use I@Rated_P"))
        ctrl_layout.addRow("Init Temp (C):", QLineEdit("0"))
        main_layout.addWidget(ctrl_group)
        main_layout.addWidget(QCheckBox("Save PDF"))
        ando_group = QGroupBox("Ando Parameters")
        ando_layout = QFormLayout(ando_group)
        ando_layout.setSpacing(GROUP_SPACING)
        ando_layout.setContentsMargins(*GROUP_MARGINS)
        ando_layout.addRow("Span:", QLineEdit("0"))
        ando_layout.addRow("Sampling:", QLineEdit("0"))
        ando_layout.addRow("", QCheckBox("Continuous Scan"))
        ando_layout.addRow("Offset1:", QLineEdit("10"))
        ando_layout.addRow("Offset2:", QLineEdit("0"))
        main_layout.addWidget(ando_group)
        limits_group = QGroupBox("Limits")
        limits_layout = QGridLayout(limits_group)
        limits_layout.setSpacing(GROUP_SPACING)
        limits_layout.setContentsMargins(*GROUP_MARGINS)
        limits_layout.addWidget(QLabel("LL"), 0, 1)
        limits_layout.addWidget(QLabel("UL"), 0, 2)
        limits_layout.addWidget(QLabel("Enable"), 0, 3)
        limit_params = [
            ("FWHM", "10", "10"),
            ("SMSR", "10", "10"),
            ("Width1", "10", "10"),
            ("Width2", "10", "10"),
            ("WL", "10", "10"),
            ("Power", "0", "")
        ]
        for i, (param, ll_val, ul_val) in enumerate(limit_params):
            row = i + 1
            limits_layout.addWidget(QLabel(param), row, 0)
            limits_layout.addWidget(QLineEdit(ll_val), row, 1)
            limits_layout.addWidget(QLineEdit(ul_val if ul_val else ""), row, 2)
            limits_layout.addWidget(QCheckBox(), row, 3)
        main_layout.addWidget(limits_group)
        deg_layout = QHBoxLayout()
        deg_layout.addWidget(QLabel("Deg of Stability:"))
        deg_layout.addWidget(QLineEdit("5"))
        deg_layout.addStretch()
        main_layout.addLayout(deg_layout)
        return main_group

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
            "All Recipe Files (*.json *.JSON *.rcp *.RCP *.ini *.INI);;"
            "JSON Files (*.json *.JSON);;All Files (*.*)"
        )
        if filename:
            self.recipePathEdit.setText(filename)
            self._load_recipe_data(filename)

    def _load_recipe_data(self, filepath: str):
        try:
            import configparser
            ext = os.path.splitext(filepath)[1].lower()
            if ext in ['.json', '.rcp']:
                with open(filepath, 'r') as f:
                    data = json.load(f)
            elif ext == '.ini':
                config = configparser.ConfigParser()
                config.read(filepath)
                data = {section: dict(config[section]) for section in config.sections()}
            else:
                try:
                    with open(filepath, 'r') as f:
                        data = json.load(f)
                except Exception:
                    config = configparser.ConfigParser()
                    config.read(filepath)
                    data = {section: dict(config[section]) for section in config.sections()}

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
            if isinstance(wavemeter, dict):
                safe_set_check(self.smsrCheckBox, wavemeter.get('smsr', False))
            # So Save works without Browse: remember file and set save folder.
            self._last_saved_or_loaded_path = os.path.abspath(filepath)
            ddir = os.path.dirname(self._last_saved_or_loaded_path)
            self.savePathEdit.setText(ddir)
            self.save_path = ddir
            QMessageBox.information(self, "Recipe Loaded", f"Recipe loaded successfully:\n{recipe_name}")
        except Exception as e:
            QMessageBox.warning(self, "Load Error", f"Failed to load recipe:\n{str(e)}")

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
            """Line edits may be empty; float('') raises — use default instead."""
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
        recipe = {
            "FiberCoupled": fiber_coupled,
            "Wavelength": wavelength,
            "GENERAL": {
                "RecipeName": recipe_name,
                "Comments": get_text(self.commentsEdit),
                "NumTests": get_value(self.numTestsSpin, 1),
                "TestSequence": test_sequence,
                "FiberCoupled": fiber_coupled,
                "Wavelength": wavelength,
                "FPPath": get_checked(self.fpPathCheck),
                "SavePath": get_text(self.savePathEdit)
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
                    "actuator_distance": get_text(self.actDistEdit)
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
                    "smsr": get_checked(self.smsrCheckBox, False)
                },
                "STABILITY": {
                    "temperature": get_value(self.tempSpin, 25),
                    "current": get_value(self.andoCurrentSpin, 0),
                    "duration_minutes": 60
                }
            }
        }
        safe_name = "".join(c for c in recipe_name if c not in '<>:"/\\|?*').strip() or "recipe"
        # Overwrite the file that was loaded (keeps .json / .RCP); otherwise create .json in save folder.
        if loaded and os.path.isfile(loaded):
            filename = os.path.abspath(loaded)
        else:
            filename = os.path.join(save_path, f"{safe_name}.json")
        try:
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(recipe, f, indent=4)
            self._last_saved_or_loaded_path = os.path.abspath(filename)
            self.savePathEdit.setText(os.path.dirname(self._last_saved_or_loaded_path))
            self.save_path = os.path.dirname(self._last_saved_or_loaded_path)
            QMessageBox.information(self, "Saved", f"Recipe saved:\n{filename}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to save recipe:\n{str(e)}")


if __name__ == "__main__":
    from start.window_placement import move_to_secondary_screen
    app = QApplication(sys.argv)
    window = RecipeWindow()
    window.show()
    QTimer.singleShot(50, lambda: move_to_secondary_screen(window, maximize=True))
    sys.exit(app.exec_())
