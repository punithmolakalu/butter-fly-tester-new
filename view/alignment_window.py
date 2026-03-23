"""Alignment window: Align tab (wavelength, Laser Settings, Ando Details, Laser On/Ando On, power meters, OK/Cancel) and ANDO SETTINGS tab.
Laser details (readbacks) only show what the main GUI sends; main GUI is linked to Arroyo. Setting changes in alignment window communicate with Arroyo instrument via viewmodel."""
from PyQt5.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QTabWidget,
    QGroupBox,
    QLabel,
    QPushButton,
    QDoubleSpinBox,
    QSpinBox,
    QComboBox,
    QFormLayout,
    QSizePolicy,
    QMessageBox,
)
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QShowEvent

from view.dark_theme import get_dark_palette, main_stylesheet, set_dark_title_bar, spinbox_arrow_styles


class AlignmentWindow(QMainWindow):
    """Alignment window: Laser details from main GUI only; setting changes go to Arroyo. ANDO SETTINGS tab. OK/Cancel emit for LIV flow."""

    alignment_confirmed = pyqtSignal()
    alignment_cancelled = pyqtSignal()

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self._main = main_window
        self._arroyo_laser_on = False
        self._arroyo_tec_on = False
        self._meter_refresh_timer = QTimer(self)
        self._meter_refresh_timer.setInterval(500)
        self._meter_refresh_timer.timeout.connect(self._refresh_meter_readings)
        self.setWindowTitle("Alignment")
        self.setMinimumSize(560, 420)
        self.resize(680, 460)
        self.setPalette(get_dark_palette())
        self.setStyleSheet(main_stylesheet())

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(12, 12, 12, 12)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._make_align_tab(), "Align")
        self._tabs.addTab(self._make_settings_tab(), "ANDO SETTINGS")
        # Ensure both tab labels are fully visible (prevent truncation)
        self._tabs.tabBar().setMinimumWidth(240)
        root.addWidget(self._tabs)
        self._update_ando_details()
        # Set initial wavelength from recipe when main window calls set_wavelength_from_recipe (or 0 = empty)

    def showEvent(self, event: QShowEvent):
        super().showEvent(event)
        try:
            set_dark_title_bar(int(self.winId()), True)
        except Exception:
            pass
        # While alignment is open (including LIV flow where polling may be paused),
        # explicitly request meter reads so readouts stay live.
        self._refresh_meter_readings()
        self._meter_refresh_timer.start()

    def closeEvent(self, event):
        try:
            self._meter_refresh_timer.stop()
        except Exception:
            pass
        super().closeEvent(event)

    def set_wavelength_from_recipe(self, value):
        """Set wavelength from recipe (called by main GUI when alignment window opens). Use None or 0 for empty if no recipe."""
        if value is None or value == "" or (isinstance(value, str) and value.strip() in ("", "—")):
            self._align_wavelength.setValue(0)
        else:
            try:
                wl = float(value)
                self._align_wavelength.setValue(wl if 0 <= wl <= 1700 else 0)
            except (TypeError, ValueError):
                self._align_wavelength.setValue(0)
        self._update_ando_details()
        # Laser details: only show what main GUI sends (main GUI links to Arroyo). Setting changes go to Arroyo via viewmodel.
        vm = self._vm()
        if vm is not None:
            if hasattr(vm, "gentec_reading_updated"):
                vm.gentec_reading_updated.connect(self._on_gentec_reading_updated, Qt.QueuedConnection)
            if hasattr(vm, "thorlabs_reading_updated"):
                vm.thorlabs_reading_updated.connect(self._on_thorlabs_reading_updated, Qt.QueuedConnection)
        self.setAttribute(Qt.WA_DeleteOnClose, True)

    def _vm(self):
        return getattr(self._main, "_viewmodel", None)

    def _refresh_meter_readings(self):
        vm = self._vm()
        if vm is None:
            return
        try:
            if hasattr(vm, "request_gentec_read"):
                vm.request_gentec_read()
            if hasattr(vm, "request_thorlabs_read"):
                vm.request_thorlabs_read()
        except Exception:
            pass

    def _make_align_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setSpacing(6)
        box_style = (
            "QGroupBox { font-weight: bold; padding-top: 6px; margin-top: 4px; "
            "border: 1px solid #3a3a42; border-radius: 4px; } "
            "QGroupBox::title { subcontrol-origin: margin; left: 8px; padding: 0 4px; }"
        )
        read_style = "color: #b0b0b0; font-size: 12px;"
        btn_style = "QPushButton { background-color: #2d2d34; color: #e6e6e6; padding: 6px 14px; } QPushButton:hover { background-color: #3a3a42; }"
        laser_ando_btn_style = "QPushButton { background-color: #2d2d34; color: #e6e6e6; padding: 6px 14px; font-weight: bold; } QPushButton:hover { background-color: #3a3a42; }"
        spin_style = "font-size: 12px; min-height: 22px; max-height: 26px;" + spinbox_arrow_styles()

        # First row: Wavelength (outside boxes)
        wl_row = QHBoxLayout()
        wl_label = QLabel("Wavelength (nm):")
        wl_label.setStyleSheet(read_style)
        self._align_wavelength = QDoubleSpinBox()
        self._align_wavelength.setStyleSheet(spin_style)
        self._align_wavelength.setRange(0, 1700)
        self._align_wavelength.setDecimals(1)
        self._align_wavelength.setValue(0)
        self._align_wavelength.setSpecialValueText("")
        self._align_wavelength.setSuffix(" nm")
        wl_row.addWidget(wl_label)
        wl_row.addWidget(self._align_wavelength)
        wl_row.addStretch()
        layout.addLayout(wl_row)
        self._align_wavelength.editingFinished.connect(self._on_align_wavelength)
        self._align_wavelength.valueChanged.connect(self._update_ando_details)

        # Laser On and Ando On buttons (moved up, above the two boxes)
        on_row = QHBoxLayout()
        self._align_laser_btn = QPushButton("LASER ON")
        self._align_laser_btn.setToolTip(
            "LASER ON: TEC output on first if needed, then laser. Already-on channels skipped. "
            "LASER OFF: laser off and TEC off."
        )
        self._align_laser_btn.setCheckable(True)
        self._align_laser_btn.setMinimumWidth(190)
        self._align_laser_btn.setMinimumHeight(64)
        self._align_laser_btn.setStyleSheet(laser_ando_btn_style)
        self._align_laser_btn.clicked.connect(self._on_align_laser_clicked)
        self._align_ando_btn = QPushButton("ANDO ON")
        self._align_ando_btn.setCheckable(True)
        self._align_ando_btn.setMinimumWidth(190)
        self._align_ando_btn.setMinimumHeight(64)
        self._align_ando_btn.setStyleSheet(laser_ando_btn_style)
        self._align_ando_btn.clicked.connect(self._on_align_ando_clicked)
        on_row.addStretch()
        on_row.addWidget(self._align_laser_btn)
        on_row.addWidget(self._align_ando_btn)
        on_row.addStretch()
        layout.addLayout(on_row)

        # Two boxes side by side: Laser Settings, Ando Details (reduced height)
        boxes_row = QHBoxLayout()
        laser_box = QGroupBox("Laser Settings")
        laser_box.setStyleSheet(box_style)
        laser_box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        laser_box.setMaximumHeight(165)
        laser_inner = QVBoxLayout(laser_box)
        laser_inner.setContentsMargins(8, 10, 8, 8)
        laser_inner.setSpacing(0)
        display_style = "color: #4caf50; font-size: 12px; background-color: #2d2d34; padding: 4px 8px; border: 1px solid #3a3a42;"
        # Column layout: left = setpoints/limits, right = readbacks
        cols = QHBoxLayout()
        cols.setSpacing(16)
        # Left column: Set Temperature, Set Current, Max Temperature, Max Current
        col_left = QFormLayout()
        col_left.setSpacing(0)
        lbl_set_temp = QLabel("Set Temperature:")
        lbl_set_temp.setStyleSheet(read_style)
        self._align_set_temp = QDoubleSpinBox()
        self._align_set_temp.setStyleSheet(spin_style)
        self._align_set_temp.setRange(-50, 150)
        self._align_set_temp.setDecimals(2)
        self._align_set_temp.setValue(0)
        self._align_set_temp.setSuffix(" °C")
        col_left.addRow(lbl_set_temp, self._align_set_temp)
        lbl_set_cur = QLabel("Set Current:")
        lbl_set_cur.setStyleSheet(read_style)
        self._align_set_current = QDoubleSpinBox()
        self._align_set_current.setStyleSheet(spin_style)
        self._align_set_current.setRange(0, 5000)
        self._align_set_current.setDecimals(1)
        self._align_set_current.setValue(0)
        self._align_set_current.setSuffix(" mA")
        col_left.addRow(lbl_set_cur, self._align_set_current)
        lbl_max_temp = QLabel("Max Temperature:")
        lbl_max_temp.setStyleSheet(read_style)
        self._align_max_temp = QDoubleSpinBox()
        self._align_max_temp.setStyleSheet(spin_style)
        self._align_max_temp.setRange(-50, 150)
        self._align_max_temp.setDecimals(2)
        self._align_max_temp.setValue(50)
        self._align_max_temp.setSuffix(" °C")
        col_left.addRow(lbl_max_temp, self._align_max_temp)
        lbl_max_cur = QLabel("Max Current:")
        lbl_max_cur.setStyleSheet(read_style)
        self._align_max_current = QDoubleSpinBox()
        self._align_max_current.setStyleSheet(spin_style)
        self._align_max_current.setRange(0, 5000)
        self._align_max_current.setDecimals(1)
        self._align_max_current.setValue(100)
        self._align_max_current.setSuffix(" mA")
        col_left.addRow(lbl_max_cur, self._align_max_current)
        cols.addLayout(col_left)
        # Right column: Current Temp, Current mA (read-only)
        col_right = QFormLayout()
        col_right.setSpacing(0)
        lbl_cur_temp = QLabel("Current Temp:")
        lbl_cur_temp.setStyleSheet(read_style)
        self._align_current_temp_display = QLabel("0.00 °C")
        self._align_current_temp_display.setStyleSheet(display_style)
        self._align_current_temp_display.setMinimumWidth(80)
        col_right.addRow(lbl_cur_temp, self._align_current_temp_display)
        lbl_cur_ma = QLabel("Current mA:")
        lbl_cur_ma.setStyleSheet(read_style)
        self._align_current_ma_display = QLabel("0.000 mA")
        self._align_current_ma_display.setStyleSheet(display_style)
        self._align_current_ma_display.setMinimumWidth(90)
        col_right.addRow(lbl_cur_ma, self._align_current_ma_display)
        cols.addLayout(col_right)
        laser_inner.addLayout(cols)
        self._align_set_temp.editingFinished.connect(self._on_align_set_temp)
        self._align_set_current.editingFinished.connect(self._on_align_set_current)
        self._align_max_temp.editingFinished.connect(self._on_align_max_temp)
        self._align_max_current.editingFinished.connect(self._on_align_max_current)
        ando_box = QGroupBox("Ando Details")
        ando_box.setStyleSheet(box_style)
        ando_box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        ando_box.setMaximumHeight(165)
        ando_inner = QVBoxLayout(ando_box)
        ando_inner.setContentsMargins(8, 10, 8, 8)
        ando_inner.setSpacing(0)
        # Read-only display: Wavelength (from Align tab) first, then ANDO SETTINGS values
        ando_detail_style = "color: #b0b0b0; font-size: 12px; background-color: #2d2d34; padding: 4px 8px; border: 1px solid #3a3a42;"
        ando_detail_form = QFormLayout()
        ando_detail_form.setSpacing(0)
        lbl_wl = QLabel("Wavelength:")
        lbl_wl.setStyleSheet(read_style)
        self._ando_detail_wavelength = QLabel("—")
        self._ando_detail_wavelength.setStyleSheet(ando_detail_style)
        self._ando_detail_wavelength.setMinimumWidth(70)
        ando_detail_form.addRow(lbl_wl, self._ando_detail_wavelength)
        lbl_s = QLabel("Span:")
        lbl_s.setStyleSheet(read_style)
        self._ando_detail_span = QLabel("—")
        self._ando_detail_span.setStyleSheet(ando_detail_style)
        self._ando_detail_span.setMinimumWidth(70)
        ando_detail_form.addRow(lbl_s, self._ando_detail_span)
        lbl_r = QLabel("Resolution:")
        lbl_r.setStyleSheet(read_style)
        self._ando_detail_resolution = QLabel("—")
        self._ando_detail_resolution.setStyleSheet(ando_detail_style)
        self._ando_detail_resolution.setMinimumWidth(70)
        ando_detail_form.addRow(lbl_r, self._ando_detail_resolution)
        lbl_n = QLabel("Sampling:")
        lbl_n.setStyleSheet(read_style)
        self._ando_detail_sampling = QLabel("—")
        self._ando_detail_sampling.setStyleSheet(ando_detail_style)
        self._ando_detail_sampling.setMinimumWidth(70)
        ando_detail_form.addRow(lbl_n, self._ando_detail_sampling)
        lbl_x = QLabel("Sensitivity:")
        lbl_x.setStyleSheet(read_style)
        self._ando_detail_sensitivity = QLabel("—")
        self._ando_detail_sensitivity.setStyleSheet(ando_detail_style)
        self._ando_detail_sensitivity.setMinimumWidth(70)
        ando_detail_form.addRow(lbl_x, self._ando_detail_sensitivity)
        ando_inner.addLayout(ando_detail_form)
        boxes_row.addWidget(laser_box, 1)
        boxes_row.addWidget(ando_box, 1)
        layout.addLayout(boxes_row)

        # Powermeter Reading box: Gentec and Thorlabs (read-only)
        readout_style = "color: #4caf50; font-size: 12px; background-color: #2d2d34; padding: 4px 8px; border: 1px solid #3a3a42; min-width: 90px;"
        pm_box = QGroupBox("Powermeter Reading")
        pm_box.setStyleSheet(box_style)
        pm_box.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        pm_inner = QVBoxLayout(pm_box)
        pm_inner.setSpacing(4)
        pm_row1 = QHBoxLayout()
        lbl_gentec = QLabel("Gentec:")
        lbl_gentec.setStyleSheet(read_style)
        self._align_gentec_reading = QLabel("—")
        self._align_gentec_reading.setStyleSheet(readout_style)
        pm_row1.addWidget(lbl_gentec)
        pm_row1.addWidget(self._align_gentec_reading)
        pm_row1.addWidget(QLabel("mW"))
        pm_row1.addStretch()
        pm_inner.addLayout(pm_row1)
        pm_row2 = QHBoxLayout()
        lbl_thorlabs = QLabel("Thorlabs:")
        lbl_thorlabs.setStyleSheet(read_style)
        self._align_thorlabs_reading = QLabel("—")
        self._align_thorlabs_reading.setStyleSheet(readout_style)
        pm_row2.addWidget(lbl_thorlabs)
        pm_row2.addWidget(self._align_thorlabs_reading)
        pm_row2.addWidget(QLabel("mW"))
        pm_row2.addStretch()
        pm_inner.addLayout(pm_row2)
        layout.addWidget(pm_box)

        # OK and Cancel
        ok_cancel_row = QHBoxLayout()
        ok_cancel_row.addStretch()
        self._ok_btn = QPushButton("OK")
        self._ok_btn.setStyleSheet(btn_style)
        self._ok_btn.clicked.connect(self._on_ok_clicked)
        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setStyleSheet(btn_style)
        self._cancel_btn.clicked.connect(self._on_cancel_clicked)
        ok_cancel_row.addWidget(self._ok_btn)
        ok_cancel_row.addWidget(self._cancel_btn)
        layout.addLayout(ok_cancel_row)

        return w

    def _make_settings_tab(self):
        w = QWidget()
        layout = QVBoxLayout(w)
        read_style = "color: #b0b0b0; font-size: 12px;"
        spin_style = "font-size: 12px; min-height: 24px; max-height: 28px;" + spinbox_arrow_styles()
        form = QFormLayout()
        lbl_span = QLabel("Span:")
        lbl_span.setStyleSheet(read_style)
        self._settings_span = QDoubleSpinBox()
        self._settings_span.setStyleSheet(spin_style)
        self._settings_span.setRange(0.1, 200)
        self._settings_span.setDecimals(2)
        self._settings_span.setValue(2)
        self._settings_span.setSuffix(" nm")
        form.addRow(lbl_span, self._settings_span)
        lbl_res = QLabel("Resolution:")
        lbl_res.setStyleSheet(read_style)
        self._settings_resolution = QDoubleSpinBox()
        self._settings_resolution.setStyleSheet(spin_style)
        self._settings_resolution.setRange(0.01, 2)
        self._settings_resolution.setDecimals(3)
        self._settings_resolution.setValue(0.01)
        self._settings_resolution.setSuffix(" nm")
        form.addRow(lbl_res, self._settings_resolution)
        lbl_samp = QLabel("Sampling:")
        lbl_samp.setStyleSheet(read_style)
        self._settings_sampling = QSpinBox()
        self._settings_sampling.setStyleSheet(spin_style)
        self._settings_sampling.setRange(11, 20001)
        self._settings_sampling.setValue(501)
        form.addRow(lbl_samp, self._settings_sampling)
        lbl_sens = QLabel("Sensitivity:")
        lbl_sens.setStyleSheet(read_style)
        self._settings_sensitivity = QComboBox()
        self._settings_sensitivity.setStyleSheet("font-size: 12px; min-height: 24px;")
        self._settings_sensitivity.addItems([
            "Normal range auto", "Normal range hold", "Mid", "High1", "High2", "High3"
        ])
        self._settings_sensitivity.setCurrentIndex(2)  # default: Mid
        form.addRow(lbl_sens, self._settings_sensitivity)
        layout.addLayout(form)
        self._settings_span.editingFinished.connect(self._on_settings_span)
        self._settings_resolution.editingFinished.connect(self._on_settings_resolution)
        self._settings_sampling.editingFinished.connect(self._on_settings_sampling)
        self._settings_sensitivity.currentIndexChanged.connect(self._on_settings_sensitivity)
        self._settings_span.editingFinished.connect(self._update_ando_details)
        self._settings_resolution.editingFinished.connect(self._update_ando_details)
        self._settings_sampling.editingFinished.connect(self._update_ando_details)
        self._settings_sensitivity.currentIndexChanged.connect(self._update_ando_details)
        layout.addStretch()
        return w

    def _update_ando_details(self):
        """Refresh Ando Details: Wavelength from Align tab, then ANDO SETTINGS tab values."""
        if not hasattr(self, "_ando_detail_span"):
            return
        wl = self._align_wavelength.value()
        self._ando_detail_wavelength.setText(f"{wl:.1f} nm" if wl else "—")
        self._ando_detail_span.setText(f"{self._settings_span.value()} nm")
        self._ando_detail_resolution.setText(f"{self._settings_resolution.value()} nm")
        self._ando_detail_sampling.setText(str(self._settings_sampling.value()))
        self._ando_detail_sensitivity.setText(self._settings_sensitivity.currentText())

    def _on_settings_span(self):
        vm = self._vm()
        if vm and hasattr(vm, "set_ando_span"):
            vm.set_ando_span(self._settings_span.value())

    def _on_settings_resolution(self):
        vm = self._vm()
        if vm and hasattr(vm, "set_ando_resolution"):
            vm.set_ando_resolution(self._settings_resolution.value())

    def _on_settings_sampling(self):
        vm = self._vm()
        if vm and hasattr(vm, "set_ando_sampling_points"):
            vm.set_ando_sampling_points(self._settings_sampling.value())

    def _on_settings_sensitivity(self, index: int):
        vm = self._vm()
        if vm and hasattr(vm, "set_ando_sensitivity_index"):
            vm.set_ando_sensitivity_index(index)

    def update_laser_details(self, data: dict):
        """Update Laser Settings display from main GUI (main GUI gets Arroyo readings). Only shows; setting changes communicate with Arroyo via viewmodel."""
        try:
            temp = data.get("tec_temp", data.get("actual_temp"))
            current_raw = data.get("laser_current", data.get("actual_current"))
            self._align_current_temp_display.setText(f"{temp:.2f} °C" if temp is not None else "—")
            if current_raw is not None:
                # Show instrument value directly (no scaling/multiplication).
                self._align_current_ma_display.setText(f"{float(current_raw):.3f} mA")
            else:
                self._align_current_ma_display.setText("—")
            # Do not overwrite Set Temperature / Set Current — user values stay visible
            # Sync only max spinboxes from main GUI when not focused
            if not self._align_max_temp.hasFocus() and data.get("max_temp") is not None:
                self._align_max_temp.setValue(data["max_temp"])
            if not self._align_max_current.hasFocus() and data.get("max_current") is not None:
                self._align_max_current.setValue(data["max_current"])
            if data.get("laser_on") is not None:
                self._arroyo_laser_on = bool(data["laser_on"])
            if data.get("tec_on") is not None:
                self._arroyo_tec_on = bool(data["tec_on"])
            self._update_laser_btn_ui()
        except Exception:
            self._align_current_temp_display.setText("—")
            self._align_current_ma_display.setText("—")

    def _update_laser_btn_ui(self):
        """Set Laser On button to green + 'Laser Off' when laser is on, else normal + 'Laser On'. User can always click to turn laser off when it is on."""
        if not hasattr(self, "_align_laser_btn"):
            return
        btn_style_off = "QPushButton { background-color: #2d2d34; color: #e6e6e6; font-weight: bold; } QPushButton:hover { background-color: #3a3a42; }"
        btn_style_on = "QPushButton { background-color: #4caf50; color: white; font-weight: bold; }"
        if self._arroyo_laser_on:
            self._align_laser_btn.setText("LASER OFF")
            self._align_laser_btn.setStyleSheet(btn_style_on)
            self._align_laser_btn.setChecked(True)
        else:
            self._align_laser_btn.setText("LASER ON")
            self._align_laser_btn.setStyleSheet(btn_style_off)
            self._align_laser_btn.setChecked(False)

    def _on_gentec_reading_updated(self, value_mw):
        if value_mw is None:
            self._align_gentec_reading.setText("—")
        else:
            self._align_gentec_reading.setText(f"{value_mw:.4f}")

    def _on_thorlabs_reading_updated(self, value_mw):
        if value_mw is None:
            self._align_thorlabs_reading.setText("—")
        else:
            self._align_thorlabs_reading.setText(f"{value_mw:.4f}")

    def _on_align_wavelength(self):
        vm = self._vm()
        if vm and hasattr(vm, "set_ando_center_wl"):
            vm.set_ando_center_wl(self._align_wavelength.value())

    def _on_align_set_current(self):
        vm = self._vm()
        if vm and hasattr(vm, "set_arroyo_laser_current"):
            vm.set_arroyo_laser_current(self._align_set_current.value())

    def _on_align_set_temp(self):
        vm = self._vm()
        if vm and hasattr(vm, "set_arroyo_temp"):
            vm.set_arroyo_temp(self._align_set_temp.value())

    def _on_align_max_temp(self):
        vm = self._vm()
        if vm and hasattr(vm, "set_arroyo_THI_limit"):
            vm.set_arroyo_THI_limit(self._align_max_temp.value())

    def _on_align_max_current(self):
        vm = self._vm()
        if vm and hasattr(vm, "set_arroyo_laser_current_limit"):
            vm.set_arroyo_laser_current_limit(self._align_max_current.value())

    def set_liv_recipe_params(self, min_current: float, max_current: float, temperature: float):
        """Apply LIV recipe values to alignment window: Set Current = min_current, Set Temperature = temperature, Max Current = max_current; then send to Arroyo."""
        self._align_set_current.setValue(min_current)
        self._align_set_temp.setValue(temperature)
        self._align_max_current.setValue(max_current)
        vm = self._vm()
        if vm:
            if hasattr(vm, "set_arroyo_laser_current"):
                vm.set_arroyo_laser_current(min_current)
            if hasattr(vm, "set_arroyo_temp"):
                vm.set_arroyo_temp(temperature)
            if hasattr(vm, "set_arroyo_laser_current_limit"):
                vm.set_arroyo_laser_current_limit(max_current)

    def _on_align_laser_clicked(self):
        vm = self._vm()
        if not vm or not hasattr(vm, "set_arroyo_laser_output"):
            return
        if not hasattr(vm, "set_arroyo_tec_output"):
            return
        # When laser is on (button green "Laser Off"): user clicks to turn laser off and TEC off.
        if self._arroyo_laser_on:
            vm.set_arroyo_laser_output(False)
            vm.set_arroyo_tec_output(False)
            return
        # Laser is off: Arroyo must be connected before Laser ON.
        if hasattr(vm, "is_arroyo_connected") and not vm.is_arroyo_connected():
            QMessageBox.warning(
                self,
                "Arroyo not connected",
                "Connect Arroyo in the Connection tab before turning the laser ON.",
            )
            return
        # viewmodel/worker turns TEC on first (if not already), then laser (if not already).
        vm.set_arroyo_laser_output(True)

    def _on_align_ando_clicked(self):
        on = self._align_ando_btn.isChecked()
        vm = self._vm()
        btn_style_off = "QPushButton { background-color: #2d2d34; color: #e6e6e6; font-weight: bold; } QPushButton:hover { background-color: #3a3a42; }"
        btn_style_on = "QPushButton { background-color: #4caf50; color: white; font-weight: bold; }"
        if on:
            # Ando On: send all Ando Details to instrument (Center WL, Span, Resolution, Sampling, Sensitivity) via proper SCPI, then repeat sweep
            self._align_ando_btn.setText("ANDO OFF")
            self._align_ando_btn.setStyleSheet(btn_style_on)
            self._align_ando_btn.setChecked(True)
            self._send_ando_details_to_instrument()
            QTimer.singleShot(200, self._ando_start_repeat)
        else:
            # Ando Off: send stop command, button grey and "ANDO ON"
            if vm and hasattr(vm, "set_ando_sweep_stop"):
                vm.set_ando_sweep_stop()
            self._align_ando_btn.setText("ANDO ON")
            self._align_ando_btn.setStyleSheet(btn_style_off)
            self._align_ando_btn.setChecked(False)

    def _send_ando_details_to_instrument(self):
        """Send all Ando Details from this window to the Ando instrument using proper commands (via viewmodel → Ando worker → GPIB: CTRWL, SPAN, RESLN, SMPL, sensitivity)."""
        vm = self._vm()
        if not vm:
            return
        wl = self._align_wavelength.value()
        if wl and hasattr(vm, "set_ando_center_wl"):
            vm.set_ando_center_wl(wl)
        if hasattr(vm, "set_ando_span"):
            vm.set_ando_span(self._settings_span.value())
        if hasattr(vm, "set_ando_resolution"):
            vm.set_ando_resolution(self._settings_resolution.value())
        if hasattr(vm, "set_ando_sampling_points"):
            vm.set_ando_sampling_points(self._settings_sampling.value())
        if hasattr(vm, "set_ando_sensitivity_index"):
            vm.set_ando_sensitivity_index(self._settings_sensitivity.currentIndex())

    def apply_ando_on_to_instrument(self):
        """Apply all Ando Details to the instrument and start repeat sweep (e.g. when opened by LIV). Same as clicking ANDO ON."""
        self._send_ando_details_to_instrument()
        QTimer.singleShot(150, self._ando_start_repeat)
        if hasattr(self, "_align_ando_btn"):
            self._align_ando_btn.setText("ANDO OFF")
            self._align_ando_btn.setStyleSheet("QPushButton { background-color: #4caf50; color: white; font-weight: bold; }")
            self._align_ando_btn.setChecked(True)

    def _liv_auto_laser_on_only(self) -> None:
        """
        LIV alignment auto-sequence: command laser ON only (never toggle OFF).

        Do not call _on_align_laser_clicked() here: if _arroyo_laser_on is stale True
        (e.g. polling paused while LIV turned the laser off), the click handler would
        turn the laser OFF, then ANDO would run — wrong order and unsafe.
        """
        vm = self._vm()
        if not vm or not hasattr(vm, "set_arroyo_laser_output"):
            return
        if hasattr(vm, "is_arroyo_connected") and not vm.is_arroyo_connected():
            QMessageBox.warning(
                self,
                "Arroyo not connected",
                "Connect Arroyo in the Connection tab before turning the laser ON.",
            )
            return
        vm.set_arroyo_laser_output(True)

    def start_liv_alignment_auto(self):
        """For LIV flow: LASER ON first, then ANDO ON (same order as the two buttons, left to right)."""
        self._liv_auto_laser_on_only()
        # Let TEC/laser worker settle before starting OSA sweep (was racing ANDO before laser).
        QTimer.singleShot(550, self.apply_ando_on_to_instrument)

    def _ando_start_repeat(self):
        """Send repeat command (RPT) to Ando to start sweep (called after parameters are sent)."""
        vm = self._vm()
        if vm and hasattr(vm, "set_ando_sweep_repeat"):
            vm.set_ando_sweep_repeat()

    def _on_ok_clicked(self):
        # Stop Ando sweep (STP) before leaving alignment so instrument is in known state
        vm = self._vm()
        if vm and hasattr(vm, "set_ando_sweep_stop"):
            vm.set_ando_sweep_stop()
        self.alignment_confirmed.emit()
        self.close()

    def _on_cancel_clicked(self):
        # Keep instrument state safe if user closes alignment without OK.
        vm = self._vm()
        if vm and hasattr(vm, "set_ando_sweep_stop"):
            vm.set_ando_sweep_stop()
        self.alignment_cancelled.emit()
        self.close()
