"""
Read-only recipe view: same layout as New Recipe window (RecipeWindow).
All fields non-editable; layout matches RecipeWindow (GENERAL, PER, LIV, SPECTRUM, Temperature Stability).
Always shows full layout; values empty when no recipe loaded, filled when recipe loaded.
"""
from PyQt5.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTabWidget,
    QLabel,
    QLineEdit,
    QGroupBox,
    QFormLayout,
    QGridLayout,
    QScrollArea,
    QSizePolicy,
    QCheckBox,
    QSpinBox,
    QAbstractSpinBox,
)
from PyQt5.QtCore import Qt

# Match recipe_window exactly
GROUP_SPACING = 10
GROUP_MARGINS = (15, 20, 15, 15)
INPUT_WIDTH = 120
INPUT_WIDTH_WIDE = 150

RO_STYLE = """
    QWidget { background-color: transparent; color: #FFFFFF; }
    QGroupBox { font-weight: bold; font-size: 13px; border: 1px solid #333333; border-radius: 4px;
        margin-top: 12px; padding-top: 12px; background-color: transparent; color: #FFFFFF; }
    QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; color: #FFFFFF; }
    QLabel { color: #FFFFFF; font-size: 12px; }
    QLineEdit { background-color: #2d2d2d; color: #e6e6e6; border: 1px solid #3a3a42; padding: 5px; font-size: 12px; }
    QScrollArea { background-color: transparent; border: 1px solid #333333; }
    QSpinBox { background-color: #2d2d2d; color: #e6e6e6; border: 1px solid #3a3a42; padding: 3px; font-size: 12px; }
    QCheckBox { color: #FFFFFF; font-size: 12px; }
    QCheckBox::indicator { width: 18px; height: 18px; border: 1px solid #333333; border-radius: 2px; background-color: transparent; }
    QCheckBox::indicator:checked { background-color: #2196F3; }
"""


def _ro_line(parent=None, width=INPUT_WIDTH):
    le = QLineEdit()
    le.setReadOnly(True)
    le.setMinimumWidth(width)
    le.setStyleSheet("background-color: #2d2d2d; color: #e6e6e6; border: 1px solid #3a3a42; padding: 5px;")
    return le


def _ro_spin(min_val=0, max_val=20, width=60):
    """Read-only small value box (no buttons) for # Tests."""
    sp = QSpinBox()
    sp.setReadOnly(True)
    sp.setButtonSymbols(QAbstractSpinBox.NoButtons)
    sp.setRange(min_val, max_val)
    sp.setValue(0)
    sp.setMinimumWidth(width)
    sp.setStyleSheet("background-color: #2d2d2d; color: #e6e6e6; border: 1px solid #3a3a42; padding: 3px;")
    return sp


def _ro_check():
    """Disabled checkbox for read-only on/off state (matches RecipeWindow toggles)."""
    cb = QCheckBox()
    cb.setEnabled(False)
    cb.setStyleSheet(
        "QCheckBox { color: #FFFFFF; font-size: 12px; } "
        "QCheckBox::indicator { width: 18px; height: 18px; border: 1px solid #333333; border-radius: 2px; background-color: transparent; } "
        "QCheckBox::indicator:checked { background-color: #2196F3; }"
    )
    return cb


class RecipeReadonlyView(QWidget):
    """Same layout as New Recipe window; all fields read-only. Always visible; empty or filled from set_data()."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._widgets = {}
        self.setStyleSheet(RO_STYLE)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self._tab_widget = QTabWidget()
        self._tab_widget.setUsesScrollButtons(True)
        self._tab_widget.setStyleSheet(
            "QTabBar::tab { min-width: 100px; max-width: 180px; padding: 8px 14px; margin-right: 2px; font-size: 11px; } "
            "QTabBar::tab:selected { background-color: #2196f3; color: white; } "
            "QTabBar::tab:hover:!selected { background-color: #35353c; } "
        )
        self._build_general_tab()
        self._build_per_tab()
        self._build_liv_tab()
        self._build_spectrum_tab()
        self._build_temp_stability_tab()
        layout.addWidget(self._tab_widget)

    def _w(self, key, widget):
        self._widgets[key] = widget
        return widget

    def _build_general_tab(self):
        tab = QWidget()
        tab.setStyleSheet(RO_STYLE)
        gl = QVBoxLayout(tab)
        gl.setContentsMargins(12, 12, 12, 12)
        gl.setSpacing(8)
        # Same as New Recipe: RCP-GEN with Recipe Name, Comments, Test Sequence row, then scroll area
        rcp = QGroupBox("RCP-GEN")
        rcp.setStyleSheet("QGroupBox { font-weight: bold; color: #e6e6e6; }")
        rcp_layout = QVBoxLayout(rcp)
        rcp_layout.setSpacing(GROUP_SPACING)
        rcp_layout.setContentsMargins(*GROUP_MARGINS)
        name_row = QHBoxLayout()
        name_row.addWidget(QLabel("RECIPE NAME:"))
        name_row.addWidget(self._w("gen.recipe_name", _ro_line(None, 400)))
        rcp_layout.addLayout(name_row)
        comments_row = QHBoxLayout()
        comments_row.addWidget(QLabel("COMMENTS:"))
        comments_row.addWidget(self._w("gen.comments", _ro_line(None, 400)))
        rcp_layout.addLayout(comments_row)
        # Same row as New Recipe: Test Sequence (left), # Tests (right), Fiber Coupled (right)
        seq_header = QHBoxLayout()
        seq_header.addWidget(QLabel("Test Sequence"))
        seq_header.addSpacing(200)
        seq_header.addWidget(QLabel("# Tests"))
        seq_header.addWidget(self._w("gen.num_tests", _ro_spin(0, 20, 60)))
        seq_header.addSpacing(24)
        fiber_check = QCheckBox("Fiber Coupled")
        fiber_check.setEnabled(False)
        seq_header.addWidget(self._w("gen.fiber_coupled", fiber_check))
        seq_header.addSpacing(24)
        seq_header.addWidget(QLabel("Wavelength (nm):"))
        seq_header.addWidget(self._w("gen.wavelength", _ro_line(None, 80)))
        seq_header.addSpacing(24)
        seq_header.addWidget(QLabel("SMSR:"))
        seq_header.addWidget(self._w("gen.smsr", _ro_line(None, 50)))
        seq_header.addStretch()
        rcp_layout.addLayout(seq_header)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setMinimumHeight(250)
        scroll_area.setStyleSheet("QScrollArea { background-color: transparent; border: 1px solid #333333; }")
        seq_frame = QWidget()
        seq_frame.setStyleSheet("background-color: transparent;")
        seq_fl = QVBoxLayout(seq_frame)
        seq_fl.setContentsMargins(0, 0, 0, 0)
        seq_fl.setSpacing(5)
        self._seq_layout = seq_fl  # filled in set_data() with one row per step (1. LIV, 2. PER, ...)
        scroll_area.setWidget(seq_frame)
        rcp_layout.addWidget(scroll_area)
        gl.addWidget(rcp)
        gl.addStretch()
        self._tab_widget.addTab(tab, "GENERAL")

    def _build_per_tab(self):
        tab = QWidget()
        tab.setStyleSheet(RO_STYLE)
        hl = QHBoxLayout(tab)
        hl.setContentsMargins(15, 15, 15, 15)
        hl.setSpacing(15)
        hl.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        center_widget = QWidget()
        center_layout = QHBoxLayout(center_widget)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(15)
        motor = QGroupBox("Motor Settings")
        motor.setStyleSheet("QGroupBox { font-weight: bold; color: #e6e6e6; }")
        fl = QFormLayout(motor)
        fl.setSpacing(GROUP_SPACING)
        fl.setContentsMargins(*GROUP_MARGINS)
        fl.addRow("Meas Speed:", self._w("per.meas_speed", _ro_line()))
        fl.addRow("Setup Speed:", self._w("per.setup_speed", _ro_line()))
        fl.addRow("Starting Angle:", self._w("per.start_angle", _ro_line()))
        fl.addRow("Travel Distance:", self._w("per.travel_dist", _ro_line()))
        center_layout.addWidget(motor, 0)
        act = QGroupBox("Actuator Settings")
        act.setStyleSheet("QGroupBox { font-weight: bold; color: #e6e6e6; }")
        fl2 = QFormLayout(act)
        fl2.setSpacing(GROUP_SPACING)
        fl2.setContentsMargins(*GROUP_MARGINS)
        fl2.addRow("Speed:", self._w("per.act_speed", _ro_line()))
        fl2.addRow("Distance:", self._w("per.act_dist", _ro_line()))
        center_layout.addWidget(act, 0)
        hl.addWidget(center_widget, 0)
        hl.addStretch(1)
        self._tab_widget.addTab(tab, "PER")

    def _build_liv_tab(self):
        tab = QWidget()
        tab.setStyleSheet(RO_STYLE)
        hl = QHBoxLayout(tab)
        hl.setContentsMargins(15, 15, 15, 15)
        hl.setSpacing(15)
        hl.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        left = QWidget()
        left.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        ll = QVBoxLayout(left)
        ll.setSpacing(GROUP_SPACING)
        curr = QGroupBox("Current Control Parameters")
        curr.setStyleSheet("QGroupBox { font-weight: bold; color: #e6e6e6; margin-top: 6px; padding-top: 6px; }")
        curr.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        fl = QFormLayout(curr)
        fl.setSpacing(4)
        fl.setContentsMargins(15, 8, 15, 8)
        fl.addRow("MINCurr (mA):", self._w("liv.min_curr", _ro_line()))
        fl.addRow("MAXCurr (mA):", self._w("liv.max_curr", _ro_line()))
        fl.addRow("INC (mA):", self._w("liv.inc", _ro_line()))
        fl.addRow("WAIT TIME (ms):", self._w("liv.wait_time", _ro_line()))
        ll.addWidget(curr)
        temp_row = QHBoxLayout()
        temp_row.setSpacing(GROUP_SPACING)
        temp_row.addWidget(QLabel("Temperature (C):"))
        temp_row.addWidget(self._w("liv.temp", _ro_line()))
        ll.addLayout(temp_row)
        mult_row = QHBoxLayout()
        mult_row.setSpacing(GROUP_SPACING)
        mult_row.addWidget(QLabel("Mult Factor:"))
        mult_row.addWidget(self._w("liv.mult", _ro_line()))
        ll.addLayout(mult_row)
        hl.addWidget(left, 0, Qt.AlignTop)
        right = QWidget()
        right.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Minimum)
        rl = QVBoxLayout(right)
        rl.setSpacing(GROUP_SPACING)
        rated = QGroupBox("Rated Operation")
        rated.setStyleSheet("QGroupBox { font-weight: bold; color: #e6e6e6; }")
        fl3 = QFormLayout(rated)
        fl3.setSpacing(GROUP_SPACING)
        fl3.setContentsMargins(*GROUP_MARGINS)
        fl3.addRow("Rated Current (Ir) (mA):", self._w("liv.rated_current", _ro_line()))
        fl3.addRow("Rated Power (Lr) (mW):", self._w("liv.rated_power", _ro_line()))
        rl.addWidget(rated)
        se = QGroupBox("Slope Efficiency (SE) & TH calc")
        se.setStyleSheet("QGroupBox { font-weight: bold; color: #e6e6e6; }")
        fl4 = QFormLayout(se)
        fl4.setSpacing(GROUP_SPACING)
        fl4.setContentsMargins(*GROUP_MARGINS)
        fl4.addRow("# data points for SE calc:", self._w("liv.se_points", _ro_line()))
        rl.addWidget(se)
        criteria = QGroupBox("Pass / Fail Criteria")
        criteria.setStyleSheet("QGroupBox { font-weight: bold; color: #e6e6e6; }")
        gl = QGridLayout(criteria)
        gl.setSpacing(GROUP_SPACING)
        gl.setContentsMargins(*GROUP_MARGINS)
        gl.addWidget(QLabel("Lower Limit"), 0, 1)
        gl.addWidget(QLabel("Upper Limit"), 0, 2)
        gl.addWidget(QLabel("ENABLE"), 0, 3)
        criteria_params = ["L @ Ir", "V @ Ir", "I @ Lr", "V @ Lr", "SE1", "IT", "PD @ Ir"]
        for i, param in enumerate(criteria_params):
            row = i + 1
            key = "liv.crit_" + param.replace(" ", "").replace("@", "")
            gl.addWidget(QLabel(param), row, 0)
            gl.addWidget(self._w(key + "_ll", _ro_line(None, 50)), row, 1)
            gl.addWidget(self._w(key + "_ul", _ro_line(None, 50)), row, 2)
            gl.addWidget(self._w(key + "_en", _ro_line(None, 40)), row, 3)
        rl.addWidget(criteria)
        rl.addStretch()
        hl.addWidget(right, 0)
        hl.addStretch(1)
        self._tab_widget.addTab(tab, "LIV")

    def _build_spectrum_tab(self):
        # Mirror RecipeWindow._create_ando_settings_tab: Ando Settings + Wavemeter sub-tabs.
        tab = QWidget()
        tab.setStyleSheet(RO_STYLE)
        vl = QVBoxLayout(tab)
        vl.setContentsMargins(5, 5, 5, 5)
        sub = QTabWidget()
        sub.setStyleSheet("QTabBar::tab { min-width: 90px; padding: 6px 12px; } ")
        ando = QWidget()
        ando.setStyleSheet(RO_STYLE)
        al = QHBoxLayout(ando)
        al.setContentsMargins(15, 15, 15, 15)
        al.setSpacing(15)
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(10)
        spec_w = 75
        ctrl_group = QGroupBox("Control Parameters")
        ctrl_group.setStyleSheet("QGroupBox { font-weight: bold; color: #e6e6e6; }")
        ctrl_grid = QGridLayout(ctrl_group)
        ctrl_grid.setSpacing(GROUP_SPACING)
        ctrl_grid.setContentsMargins(*GROUP_MARGINS)
        row = 0
        ctrl_grid.addWidget(QLabel("Current"), row, 0)
        ctrl_grid.addWidget(self._w("spec.current", _ro_line(None, spec_w)), row, 1)
        ctrl_grid.addWidget(QLabel("mA"), row, 2)
        ctrl_grid.addWidget(QLabel("Analysis"), row, 3)
        ctrl_grid.addWidget(self._w("spec.analysis", _ro_line(None, 100)), row, 4)
        row += 1
        ctrl_grid.addWidget(QLabel("Res(nm)"), row, 0)
        ctrl_grid.addWidget(self._w("spec.resolution", _ro_line(None, spec_w)), row, 1)
        ctrl_grid.addWidget(QLabel("Sensitivity"), row, 3)
        ctrl_grid.addWidget(self._w("spec.sensitivity", _ro_line(None, 100)), row, 4)
        row += 1
        ctrl_grid.addWidget(QLabel("Average"), row, 0)
        ctrl_grid.addWidget(self._w("spec.average", _ro_line(None, spec_w)), row, 1)
        ctrl_grid.addWidget(QLabel("Active Trace"), row, 3)
        ctrl_grid.addWidget(self._w("spec.active_trace", _ro_line(None, 100)), row, 4)
        row += 1
        ctrl_grid.addWidget(QLabel("Sampling"), row, 0)
        ctrl_grid.addWidget(self._w("spec.sampling", _ro_line(None, spec_w)), row, 1)
        ctrl_grid.addWidget(QLabel("Air/Vac"), row, 3)
        ctrl_grid.addWidget(self._w("spec.air_vac", _ro_line(None, 100)), row, 4)
        row += 1
        ctrl_grid.addWidget(QLabel("Center/Start"), row, 0)
        ctrl_grid.addWidget(self._w("spec.center", _ro_line(None, spec_w)), row, 1)
        ctrl_grid.addWidget(QLabel("Pulse/CW"), row, 3)
        ctrl_grid.addWidget(self._w("spec.pulse_cw", _ro_line(None, 100)), row, 4)
        row += 1
        ctrl_grid.addWidget(QLabel("Span/Stop"), row, 0)
        ctrl_grid.addWidget(self._w("spec.span", _ro_line(None, spec_w)), row, 1)
        ctrl_grid.addWidget(QLabel("Range Sw"), row, 3)
        ctrl_grid.addWidget(self._w("spec.range_switch", _ro_line(None, 100)), row, 4)
        row += 1
        ctrl_grid.addWidget(QLabel("Level Scale"), row, 3)
        ctrl_grid.addWidget(self._w("spec.level_scale", _ro_line(None, spec_w)), row, 4)
        ctrl_grid.addWidget(QLabel("dB"), row, 5)
        row += 1
        ctrl_grid.addWidget(QLabel("Ref Level"), row, 0)
        ctrl_grid.addWidget(self._w("spec.ref_level", _ro_line(None, spec_w)), row, 1)
        ctrl_grid.addWidget(QLabel("Auto Analysis"), row, 3)
        ctrl_grid.addWidget(self._w("spec.auto_analysis", _ro_check()), row, 4)
        row += 1
        ctrl_grid.addWidget(QLabel("Temp"), row, 0)
        ctrl_grid.addWidget(self._w("spec.temp", _ro_line(None, spec_w)), row, 1)
        ctrl_grid.addWidget(QLabel("C"), row, 2)
        ctrl_grid.addWidget(QLabel("WL Shift"), row, 3)
        ctrl_grid.addWidget(self._w("spec.wl_shift", _ro_line(None, spec_w)), row, 4)
        left_layout.addWidget(ctrl_group)
        _uc = self._w("spec.use_current_rated_power", _ro_check())
        _uc.setText("Use Current@Rated Power")
        left_layout.addWidget(_uc)
        left_layout.addStretch()
        al.addWidget(left_widget, 7)
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(5)
        limits_group = QGroupBox("Limits")
        limits_group.setStyleSheet("QGroupBox { font-weight: bold; color: #e6e6e6; }")
        limits_grid = QGridLayout(limits_group)
        limits_grid.setSpacing(GROUP_SPACING)
        limits_grid.setContentsMargins(*GROUP_MARGINS)
        limits_grid.addWidget(QLabel("LL"), 0, 1)
        limits_grid.addWidget(QLabel("UL"), 0, 2)
        limits_grid.addWidget(QLabel("Enable"), 0, 3)
        limit_params = ["Peak WL", "FWHM", "Cen WL", "SMSR"]
        for i, param in enumerate(limit_params):
            r = i + 1
            pk = param.replace(" ", "").lower()
            limits_grid.addWidget(QLabel(param), r, 0)
            limits_grid.addWidget(self._w("spec.lim_" + pk + "_ll", _ro_line(None, 60)), r, 1)
            limits_grid.addWidget(self._w("spec.lim_" + pk + "_ul", _ro_line(None, 60)), r, 2)
            limits_grid.addWidget(self._w("spec.lim_" + pk + "_en", _ro_check()), r, 3)
        right_layout.addWidget(limits_group)
        boxes_row = QHBoxLayout()
        boxes_row.setSpacing(10)
        box1 = QGroupBox("")
        box1.setStyleSheet("QGroupBox { border: 1px solid #333333; border-radius: 4px; }")
        box1_grid = QGridLayout(box1)
        box1_grid.setContentsMargins(10, 15, 10, 10)
        box1_grid.setSpacing(5)
        box1_grid.addWidget(QLabel("SMSRMsk"), 0, 0)
        box1_grid.addWidget(self._w("spec.smsrmsk", _ro_line(None, 60)), 1, 0)
        box1_grid.addWidget(QLabel("TH"), 0, 1)
        box1_grid.addWidget(self._w("spec.th", _ro_line(None, 60)), 1, 1)
        box1_grid.addWidget(QLabel("K"), 2, 0)
        box1_grid.addWidget(self._w("spec.k", _ro_line(None, 60)), 3, 0)
        box1_grid.addWidget(QLabel("TH 2"), 2, 1)
        box1_grid.addWidget(self._w("spec.th2", _ro_line(None, 60)), 3, 1)
        box1.setMaximumWidth(160)
        boxes_row.addWidget(box1, 1)
        box2 = QGroupBox("")
        box2.setStyleSheet("QGroupBox { border: 1px solid #333333; border-radius: 4px; }")
        box2_layout = QVBoxLayout(box2)
        box2_layout.setContentsMargins(10, 15, 10, 10)
        box2_layout.setSpacing(8)
        box2_layout.addWidget(QLabel("SpecWd"))
        box2_layout.addWidget(self._w("spec.specwd", _ro_line(None, 90)))
        box2_layout.addWidget(QLabel("ModeFit"))
        box2_layout.addWidget(self._w("spec.mode_fit", _ro_line(None, 90)))
        boxes_row.addWidget(box2, 2)
        right_layout.addLayout(boxes_row)
        auto_ref_row = QHBoxLayout()
        auto_ref_row.addStretch()
        auto_ref_row.addWidget(QLabel("Auto Ref Level"))
        auto_ref_row.addWidget(self._w("spec.auto_ref_level", _ro_check()))
        right_layout.addLayout(auto_ref_row)
        right_layout.addStretch()
        al.addWidget(right_widget, 3)
        sub.addTab(ando, "Ando Settings")
        wm_tab = QWidget()
        wm_tab.setStyleSheet(RO_STYLE)
        wml = QVBoxLayout(wm_tab)
        wml.setContentsMargins(15, 15, 15, 15)
        q8326 = QGroupBox("Q8326 Settings")
        q8326.setStyleSheet("QGroupBox { font-weight: bold; color: #e6e6e6; }")
        fl3 = QFormLayout(q8326)
        fl3.setSpacing(GROUP_SPACING)
        fl3.setContentsMargins(*GROUP_MARGINS)
        fl3.addRow("Wavelength Range:", self._w("wm.wl_range", _ro_line(INPUT_WIDTH_WIDE)))
        fl3.addRow("Function:", self._w("wm.function", _ro_line()))
        fl3.addRow("Resolution:", self._w("wm.resolution", _ro_line()))
        fl3.addRow("Sample Mode:", self._w("wm.sample_mode", _ro_line()))
        fl3.addRow("AVG:", self._w("wm.avg", _ro_line()))
        fl3.addRow("SMSR:", self._w("wm.smsr", _ro_line()))
        wml.addWidget(q8326)
        wml.addStretch()
        sub.addTab(wm_tab, "Wavemeter Settings")
        vl.addWidget(sub)
        self._tab_widget.addTab(tab, "SPECTRUM")

    def _build_temp_stability_tab(self):
        tab = QWidget()
        tab.setStyleSheet(RO_STYLE)
        vl = QVBoxLayout(tab)
        vl.setContentsMargins(15, 15, 15, 15)
        vl.setSpacing(15)
        for i, title in enumerate(["Temperature Stability 1", "Temperature Stability 2"]):
            g = QGroupBox(title)
            g.setStyleSheet("QGroupBox { font-weight: bold; color: #e6e6e6; }")
            hl = QHBoxLayout(g)
            hl.setSpacing(GROUP_SPACING)
            ctrl = QGroupBox("Control Parameters")
            ctrl.setStyleSheet("QGroupBox { font-weight: bold; color: #e6e6e6; }")
            fl = QFormLayout(ctrl)
            fl.setSpacing(GROUP_SPACING)
            fl.setContentsMargins(*GROUP_MARGINS)
            prefix = "ts1." if i == 0 else "ts2."
            fl.addRow("MINTemp (C):", self._w(prefix + "min_temp", _ro_line()))
            fl.addRow("MAXTemp (C):", self._w(prefix + "max_temp", _ro_line()))
            fl.addRow("INC (C):", self._w(prefix + "inc", _ro_line()))
            fl.addRow("WAIT TIME (ms):", self._w(prefix + "wait_time", _ro_line()))
            fl.addRow("Set Curr (mA):", self._w(prefix + "set_curr", _ro_line()))
            fl.addRow("Init Temp (C):", self._w(prefix + "init_temp", _ro_line()))
            hl.addWidget(ctrl)
            ando = QGroupBox("Ando Parameters")
            ando.setStyleSheet("QGroupBox { font-weight: bold; color: #e6e6e6; }")
            fl2 = QFormLayout(ando)
            fl2.setSpacing(GROUP_SPACING)
            fl2.setContentsMargins(*GROUP_MARGINS)
            fl2.addRow("Span:", self._w(prefix + "span", _ro_line()))
            fl2.addRow("Sampling:", self._w(prefix + "sampling", _ro_line()))
            fl2.addRow("Offset1:", self._w(prefix + "offset1", _ro_line()))
            fl2.addRow("Offset2:", self._w(prefix + "offset2", _ro_line()))
            hl.addWidget(ando)
            limits = QGroupBox("Limits")
            limits.setStyleSheet("QGroupBox { font-weight: bold; color: #e6e6e6; }")
            gl_ts = QGridLayout(limits)
            gl_ts.setSpacing(GROUP_SPACING)
            gl_ts.setContentsMargins(*GROUP_MARGINS)
            gl_ts.addWidget(QLabel("LL"), 0, 1)
            gl_ts.addWidget(QLabel("UL"), 0, 2)
            gl_ts.addWidget(QLabel("Enable"), 0, 3)
            for row, param in enumerate(["FWHM", "SMSR", "Width1", "Width2", "WL", "Power"], 1):
                pk = param.lower()
                gl_ts.addWidget(QLabel(param), row, 0)
                gl_ts.addWidget(self._w(prefix + "lim_" + pk + "_ll", _ro_line(None, 50)), row, 1)
                gl_ts.addWidget(self._w(prefix + "lim_" + pk + "_ul", _ro_line(None, 50)), row, 2)
                gl_ts.addWidget(self._w(prefix + "lim_" + pk + "_en", _ro_line(None, 40)), row, 3)
            hl.addWidget(limits)
            deg_row = QHBoxLayout()
            deg_row.addWidget(QLabel("Deg of Stability:"))
            deg_row.addWidget(self._w(prefix + "deg_stability", _ro_line(None, 40)))
            deg_row.addStretch()
            hl.addLayout(deg_row)
            vl.addWidget(g)
        vl.addWidget(QLabel("Temperature Stability 2 will only run if Temperature Stability 1 passes."))
        vl.addStretch()
        self._tab_widget.addTab(tab, "Temperature Stability")

    def _clear_seq_layout(self):
        """Remove all rows from the test sequence area (GENERAL tab)."""
        while self._seq_layout.count():
            item = self._seq_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                lay = item.layout()
                while lay.count():
                    sub = lay.takeAt(0)
                    if sub.widget():
                        sub.widget().deleteLater()

    def _set(self, key, value):
        w = self._widgets.get(key)
        if w is None:
            return
        if isinstance(w, QCheckBox):
            if isinstance(value, str):
                v = value.strip().lower()
                w.setChecked(v in ("1", "true", "yes", "on"))
            else:
                w.setChecked(bool(value) if value not in (None, "") else False)
        elif isinstance(w, QSpinBox):
            try:
                w.setValue(int(value) if value not in (None, "") else 0)
            except (TypeError, ValueError):
                w.setValue(0)
        else:
            w.setText(str(value).strip() if value is not None else "")

    def clear(self):
        for w in self._widgets.values():
            if isinstance(w, QCheckBox):
                w.setChecked(False)
            elif isinstance(w, QSpinBox):
                w.setValue(0)
            else:
                w.setText("")
        self._clear_seq_layout()

    def set_data(self, data):
        """Fill all fields from recipe dict; same keys as recipe_window load/save."""
        if not data:
            self.clear()
            return
        def get(d, *keys, default=""):
            for k in keys:
                if isinstance(d, dict) and k in d:
                    d = d[k]
                else:
                    return default
            return d
        def section(*path):
            return get(data, *path) if isinstance(data, dict) else {}

        gen = section("GENERAL") or section("General") or {}
        ops = data.get("OPERATIONS") or {}
        liv = section("LIV") or get(ops, "LIV") or {}
        per = section("PER") or get(ops, "PER") or {}
        spec = section("SPECTRUM") or get(ops, "SPECTRUM") or {}
        wm = get(data, "spec", "WAVEMETER") or get(ops, "WAVEMETER") or get(data, "WAVEMETER") or {}
        stab = get(ops, "STABILITY") or {}
        stab1 = get(ops, "Temperature Stability 1") or {}
        stab2 = get(ops, "Temperature Stability 2") or {}

        self._set("gen.recipe_name", data.get("Recipe_Name") or data.get("recipe_name") or "")
        self._set("gen.comments", data.get("Description") or get(gen, "Comments") or "")
        seq = data.get("TEST_SEQUENCE") or gen.get("TestSequence") or []
        if not isinstance(seq, (list, tuple)):
            seq = [str(seq)] if seq else []
        self._set("gen.num_tests", str(len(seq)) if seq else get(gen, "NumTests"))
        self._set("gen.fiber_coupled", str(data.get("FiberCoupled", gen.get("FiberCoupled", ""))))
        self._set("gen.wavelength", str(data.get("Wavelength", gen.get("Wavelength", ""))))
        wm_for_gen = get(data, "spec", "WAVEMETER") or get(ops, "WAVEMETER") or get(data, "WAVEMETER") or {}
        self._set("gen.smsr", "Yes" if (isinstance(wm_for_gen, dict) and wm_for_gen.get("smsr")) else "No")
        self._clear_seq_layout()
        for i, name in enumerate(seq):
            row = QHBoxLayout()
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(8)
            lbl = QLabel(f"{i + 1}.")
            lbl.setStyleSheet("color: #e6e6e6; font-size: 12px;")
            row.addWidget(lbl)
            ro = _ro_line(None, 220)
            ro.setText(str(name).strip())
            row.addWidget(ro)
            self._seq_layout.addLayout(row)

        self._set("per.meas_speed", get(per, "MeasSpeed") or get(per, "meas_speed"))
        self._set("per.setup_speed", get(per, "SetupSpeed") or get(per, "setup_speed"))
        self._set("per.start_angle", get(per, "StartAngle") or get(per, "start_angle"))
        self._set("per.travel_dist", get(per, "TravelDistance") or get(per, "travel_distance"))
        self._set("per.act_speed", get(per, "ActuatorSpeed") or get(per, "actuator_speed"))
        self._set("per.act_dist", get(per, "ActuatorDistance") or get(per, "actuator_distance"))

        self._set("liv.min_curr", get(liv, "min_current_mA") or get(liv, "MINCurr"))
        self._set("liv.max_curr", get(liv, "max_current_mA") or get(liv, "MAXCurr"))
        self._set("liv.inc", get(liv, "increment_mA") or get(liv, "INC"))
        self._set("liv.wait_time", get(liv, "wait_time_ms") or get(liv, "WAIT TIME"))
        self._set("liv.temp", get(liv, "Temperature") or get(liv, "temperature") or "25")
        self._set("liv.mult", get(liv, "multiplier") or "1")
        self._set("liv.rated_current", get(liv, "rated_current_mA"))
        self._set("liv.rated_power", get(liv, "rated_power_mW"))
        self._set("liv.se_points", get(liv, "se_data_points"))

        self._set("spec.current", get(spec, "Current") or get(spec, "current"))
        self._set("spec.resolution", get(spec, "Resolution") or get(spec, "resolution_nm"))
        self._set("spec.average", get(spec, "Average") or get(spec, "average"))
        self._set("spec.sampling", get(spec, "Sampling") or get(spec, "sampling"))
        self._set("spec.center", get(spec, "CenterWL") or get(spec, "center_nm"))
        self._set("spec.span", get(spec, "Span") or get(spec, "span_nm"))
        self._set("spec.ref_level", get(spec, "RefLevel") or get(spec, "ref_level_dBm"))
        self._set("spec.level_scale", get(spec, "level_scale") or get(spec, "LevelScale"))
        self._set("spec.temp", get(spec, "Temperature") or get(spec, "temperature"))
        self._set("spec.analysis", get(spec, "Analysis") or get(spec, "analysis"))
        self._set("spec.sensitivity", get(spec, "Sensitivity") or get(spec, "sensitivity"))
        self._set("spec.active_trace", get(spec, "active_trace") or get(spec, "ActiveTrace"))
        self._set("spec.air_vac", get(spec, "air_vac") or get(spec, "AirVac"))
        self._set("spec.pulse_cw", get(spec, "pulse_cw") or get(spec, "PulseCw"))
        self._set("spec.range_switch", get(spec, "range_switch") or get(spec, "RangeSwitch"))
        self._set("spec.wl_shift", get(spec, "wl_shift") or get(spec, "WlShift"))
        self._set("spec.auto_analysis", get(spec, "auto_analysis"))
        self._set(
            "spec.use_current_rated_power",
            get(spec, "use_current_rated_power") if get(spec, "use_current_rated_power") != ""
            else get(spec, "UseRatedPower"),
        )
        self._set("spec.auto_ref_level", get(spec, "auto_ref_level"))
        if isinstance(spec, dict) and "threshold" in spec:
            self._set("spec.specwd", spec.get("threshold"))
        else:
            self._set("spec.specwd", get(spec, "SpecWd"))
        self._set("spec.mode_fit", get(spec, "mode_fit") or get(spec, "ModeFit"))
        self._set("spec.smsrmsk", get(spec, "smsrmsk") or get(spec, "SMSRMsk") or get(spec, "smsr_mask"))
        self._set("spec.th", get(spec, "th") or get(spec, "TH"))
        self._set("spec.k", get(spec, "k") or get(spec, "K"))
        self._set("spec.th2", get(spec, "th2") or get(spec, "TH2") or get(spec, "TH 2"))

        pf_spec = {}
        if isinstance(data, dict):
            pfc = data.get("PASS_FAIL_CRITERIA") or data.get("PassFailCriteria") or {}
            if isinstance(pfc, dict):
                pf_spec = pfc.get("SPECTRUM") or pfc.get("Spectrum") or {}
        lim_src = spec.get("limits") if isinstance(spec, dict) and isinstance(spec.get("limits"), dict) else {}
        for param in ["Peak WL", "FWHM", "Cen WL", "SMSR"]:
            pk = param.replace(" ", "").lower()
            sub = lim_src.get(param) or lim_src.get(pk) or {}
            if isinstance(sub, dict):
                ll, ul, en = sub.get("ll"), sub.get("ul"), sub.get("enable")
            else:
                ll = ul = en = None
            if isinstance(pf_spec, dict):
                if param == "SMSR" and ll is None:
                    ll = pf_spec.get("min_SMSR_dB")
                elif param == "FWHM" and ul is None:
                    ul = pf_spec.get("max_FWHM_nm")
                elif param in ("Peak WL", "Cen WL") and ll is None and ul is None:
                    tol = pf_spec.get("wavelength_tolerance_nm")
                    if tol is not None:
                        ll, ul = -abs(tol), abs(tol)
            self._set("spec.lim_" + pk + "_ll", ll if ll is not None else "")
            self._set("spec.lim_" + pk + "_ul", ul if ul is not None else "")
            self._set("spec.lim_" + pk + "_en", en if en is not None else False)

        self._set("wm.wl_range", get(wm, "wavelength_range"))
        self._set("wm.function", get(wm, "function"))
        self._set("wm.resolution", get(wm, "resolution"))
        self._set("wm.sample_mode", get(wm, "sample_mode"))
        self._set("wm.avg", get(wm, "averaging"))
        self._set("wm.smsr", "Yes" if wm.get("smsr") else "No")

        self._set("ts1.min_temp", get(stab1, "MinTemp") or get(stab, "min_temp"))
        self._set("ts1.max_temp", get(stab1, "MaxTemp") or get(stab, "max_temp"))
        self._set("ts1.inc", get(stab1, "TempIncrement") or get(stab1, "INC") or get(stab, "inc"))
        self._set("ts1.wait_time", get(stab1, "StabilizationTime_s") or get(stab, "wait_time"))
        self._set("ts1.set_curr", get(stab1, "Current") or get(stab, "set_curr"))
        self._set("ts1.init_temp", get(stab1, "InitTemp") or get(stab, "init_temp"))
        self._set("ts1.span", get(stab1, "Span"))
        self._set("ts1.sampling", get(stab1, "Sampling"))
        self._set("ts1.offset1", get(stab1, "Offset1"))
        self._set("ts1.offset2", get(stab1, "Offset2"))
        self._set("ts2.min_temp", get(stab2, "MinTemp"))
        self._set("ts2.max_temp", get(stab2, "MaxTemp"))
        self._set("ts2.inc", get(stab2, "TempIncrement") or get(stab2, "INC"))
        self._set("ts2.wait_time", get(stab2, "StabilizationTime_s"))
        self._set("ts2.set_curr", get(stab2, "Current"))
        self._set("ts2.init_temp", get(stab2, "InitTemp"))
        self._set("ts2.span", get(stab2, "Span"))
        self._set("ts2.sampling", get(stab2, "Sampling"))
        self._set("ts2.offset1", get(stab2, "Offset1"))
        self._set("ts2.offset2", get(stab2, "Offset2"))
