"""
Spectrum test sequence window (secondary monitor).
Left: Spectrum RCP details, then live wavemeter reading (instrument readbacks during the step).
Right: Ando OSA live trace — WDATA (nm) vs LDATA (dBm), same styling as Main PER graph.
"""
from PyQt5.QtWidgets import (
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QFormLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QFrame,
    QScrollArea,
)
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QShowEvent

try:
    import pyqtgraph as pg
    _PG_AVAILABLE = True
except ImportError:
    _PG_AVAILABLE = False
    pg = None

from view.dark_theme import get_dark_palette, main_stylesheet, set_dark_title_bar


def _fmt(v, default="—"):
    if v is None:
        return default
    try:
        return "{:.4g}".format(float(v))
    except Exception:
        return str(v)


class SpectrumTestSequenceWindow(QMainWindow):
    """Floating window opened when a Spectrum test step starts (second monitor)."""

    stop_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Spectrum Process")
        self.setMinimumSize(980, 640)
        self.resize(1140, 720)
        self.setPalette(get_dark_palette())
        self.setStyleSheet(main_stylesheet())
        self.setAttribute(Qt.WA_DeleteOnClose, True)

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(16)

        # ----- Left: RCP + wavemeter + control -----
        left_widget = QWidget()
        left_widget.setMinimumWidth(320)
        left_widget.setMaximumWidth(460)
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        params_group = QGroupBox("Spectrum RCP (recipe)")
        params_group.setStyleSheet(
            "QGroupBox { font-weight: bold; font-size: 13px; color: #e6e6e6; } "
            "QLabel { color: #c8c8c8; font-size: 12px; }"
        )
        form = QFormLayout(params_group)
        self._labels = {}
        for key, title in [
            ("center_nm", "Center (nm)"),
            ("span_nm", "Span (nm)"),
            ("resolution_nm", "Resolution (nm)"),
            ("sampling_points", "Sampling (pts)"),
            ("temperature_c", "Temperature (°C)"),
            ("laser_current_mA", "Laser current (mA)"),
            ("sensitivity", "Sensitivity"),
            ("analysis", "Analysis"),
        ]:
            lb = QLabel("—")
            self._labels[key] = lb
            form.addRow(title + ":", lb)
        left_layout.addWidget(params_group)

        wm_group = QGroupBox("Wavemeter (instrument)")
        wm_group.setStyleSheet(
            "QGroupBox { font-weight: bold; font-size: 13px; color: #e6e6e6; } "
            "QLabel { color: #c8c8c8; font-size: 12px; }"
        )
        wm_form = QFormLayout(wm_group)
        self._wm_value = QLabel("—")
        self._wm_value.setStyleSheet("color: #aed581; font-size: 14px; font-weight: bold;")
        wm_form.addRow("Wavelength (nm):", self._wm_value)
        wm_hint = QLabel("Live read while Spectrum runs (same GPIB session as test).")
        wm_hint.setWordWrap(True)
        wm_hint.setStyleSheet("color: #9e9e9e; font-size: 10px;")
        wm_form.addRow(wm_hint)
        left_layout.addWidget(wm_group)

        ctrl_group = QGroupBox("Control")
        ctrl_group.setStyleSheet(
            "QGroupBox { font-weight: bold; font-size: 12px; color: #e6e6e6; } "
            "QLabel { color: #c8c8c8; font-size: 11px; }"
        )
        ctrl_layout = QVBoxLayout(ctrl_group)
        self._stop_btn = QPushButton("Stop")
        self._stop_btn.setMinimumHeight(34)
        self._stop_btn.setStyleSheet(
            "QPushButton { background-color: #f44336; color: white; font-weight: bold; padding: 8px 16px; } "
            "QPushButton:hover { background-color: #d32f2f; }"
        )
        self._stop_btn.clicked.connect(self.stop_requested.emit)
        ctrl_layout.addWidget(self._stop_btn)
        self._status = QLabel("Running Spectrum (Ando + wavemeter)…")
        self._status.setWordWrap(True)
        self._status.setStyleSheet("color: #b0bec5; font-size: 12px;")
        ctrl_layout.addWidget(self._status)
        left_layout.addWidget(ctrl_group)
        left_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidget(left_widget)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        main_layout.addWidget(scroll)

        # ----- Right: Ando live graph -----
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        title = QLabel("Ando OSA — live sweep (Level dBm vs wavelength nm)")
        title.setStyleSheet("font-weight: bold; font-size: 13px; color: #e6e6e6;")
        right_layout.addWidget(title)

        if not _PG_AVAILABLE:
            right_layout.addWidget(QLabel("pyqtgraph required for graph display."))
            self._plot_widget = None
            self._curve = None
        else:
            pw = pg.PlotWidget()
            pw.setBackground("w")
            p = pw.getPlotItem()
            p.getViewBox().setBackgroundColor((255, 255, 255))
            p.showGrid(x=True, y=True, alpha=0.4)
            p.setLabel("bottom", "Wavelength WDATA (nm)", color="#333333")
            p.setLabel("left", "Level LDATA (dBm)", color="#333333")
            axis_pen = pg.mkPen(color="#333333", width=1)
            p.getAxis("left").setPen(axis_pen)
            p.getAxis("left").setTextPen(axis_pen)
            p.getAxis("bottom").setPen(axis_pen)
            p.getAxis("bottom").setTextPen(axis_pen)
            self._plot_widget = pw
            self._curve = pw.plot(
                [],
                [],
                pen=pg.mkPen("#00AA00", width=2),
                symbol="o",
                symbolSize=4,
                symbolBrush="#00AA00",
            )
            right_layout.addWidget(pw, 1)

        self._footnote = QLabel("Updates after each sweep completes (first, then second).")
        self._footnote.setStyleSheet("color: #9e9e9e; font-size: 10px;")
        right_layout.addWidget(self._footnote)
        main_layout.addWidget(right_widget, 1)

    def showEvent(self, event: QShowEvent):
        super().showEvent(event)
        try:
            set_dark_title_bar(int(self.winId()), True)
        except Exception:
            pass

    def set_params(self, params: dict):
        params = params or {}
        for k, lbl in self._labels.items():
            v = params.get(k)
            if k in ("analysis", "sensitivity"):
                lbl.setText(str(v) if v not in (None, "") else "—")
            else:
                lbl.setText(_fmt(v))

    def set_wavemeter_reading(self, nm) -> None:
        """Live wavelength from wavemeter (nm); None shows —."""
        if nm is None:
            self._wm_value.setText("—")
            return
        try:
            self._wm_value.setText("{:.6f}".format(float(nm)))
        except Exception:
            self._wm_value.setText(str(nm))

    def set_live_trace(self, wdata, ldata) -> None:
        """Plot Ando WDATA vs LDATA (same instrument as sweep)."""
        if self._curve is None:
            return
        w = list(wdata or [])
        l_ = list(ldata or [])
        n = min(len(w), len(l_))
        if n:
            self._curve.setData(w[:n], l_[:n])
            try:
                pw = getattr(self, "_plot_widget", None)
                if pw is not None:
                    pw.getPlotItem().getViewBox().autoRange()
            except Exception:
                pass
        else:
            self._curve.setData([], [])

    def clear_live_plot(self) -> None:
        if self._curve is not None:
            self._curve.setData([], [])

    def set_status(self, text: str):
        self._status.setText(text or "")

    def set_finished(self, passed: bool, detail: str = ""):
        self._stop_btn.setEnabled(False)
        if passed:
            self._status.setStyleSheet("color: #81c784; font-size: 12px; font-weight: bold;")
            self._status.setText("Finished — PASS\n" + (detail or ""))
        else:
            self._status.setStyleSheet("color: #ef9a9a; font-size: 12px; font-weight: bold;")
            self._status.setText("Finished — FAIL\n" + (detail or ""))
