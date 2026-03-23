"""
PER Test Sequence Window.
Left: PER RCP values + Stop button.
Right: live graph — Thorlabs power (mW) vs PRM angle (deg).
"""
# Match standalone Kinesis live plot: keep last N points for responsiveness.
LIVE_PLOT_MAX_POINTS = 500
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
    QPlainTextEdit,
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


class PerTestSequenceWindow(QMainWindow):
    stop_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("PER Process")
        self.setMinimumSize(980, 640)
        self.resize(1140, 720)
        self.setPalette(get_dark_palette())
        self.setStyleSheet(main_stylesheet())
        self.setAttribute(Qt.WA_DeleteOnClose, True)

        self._angles = []
        self._powers_mw = []
        self._value_labels = {}

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(16)

        # Left: RCP details + stop
        left_widget = QWidget()
        left_widget.setMinimumWidth(320)
        left_widget.setMaximumWidth(430)
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)

        params_group = QGroupBox("PER Recipe Parameters")
        params_group.setStyleSheet(
            "QGroupBox { font-weight: bold; font-size: 13px; color: #e6e6e6; } "
            "QLabel { color: #c8c8c8; font-size: 12px; }"
        )
        form = QFormLayout(params_group)
        for key, label in [
            ("wavelength_nm", "Wavelength (nm)"),
            ("start_angle_deg", "Start Angle (deg)"),
            ("travel_distance_deg", "Travel Distance (deg)"),
            ("meas_speed_deg_per_sec", "Meas Speed (deg/s)"),
            ("setup_speed_deg_per_sec", "Setup Speed (deg/s)"),
            ("actuator_speed", "Actuator Speed"),
            ("actuator_distance", "Actuator Distance"),
            ("skip_actuator", "Skip actuator"),
            ("wait_time_ms", "Wait Time (ms)"),
            ("steps_per_degree", "Steps / Degree"),
            ("min_per_db", "Min PER Limit (dB)"),
        ]:
            v = QLabel("—")
            self._value_labels[key] = v
            form.addRow(label + ":", v)
        left_layout.addWidget(params_group)

        stop_group = QGroupBox("Control")
        stop_group.setStyleSheet(
            "QGroupBox { font-weight: bold; font-size: 12px; color: #e6e6e6; } "
            "QLabel { color: #c8c8c8; font-size: 11px; }"
        )
        stop_layout = QVBoxLayout(stop_group)
        self._stop_btn = QPushButton("Stop")
        self._stop_btn.setMinimumHeight(34)
        self._stop_btn.clicked.connect(self.stop_requested.emit)
        stop_layout.addWidget(self._stop_btn)
        self._status = QLabel("Running...")
        stop_layout.addWidget(self._status)
        left_layout.addWidget(stop_group)

        log_group = QGroupBox("Process log")
        log_group.setStyleSheet(
            "QGroupBox { font-weight: bold; font-size: 12px; color: #e6e6e6; } "
            "QPlainTextEdit { background-color: #1e1e1e; color: #c8c8c8; font-size: 11px; }"
        )
        log_layout = QVBoxLayout(log_group)
        self._process_log = QPlainTextEdit()
        self._process_log.setReadOnly(True)
        self._process_log.setMinimumHeight(120)
        self._process_log.setPlaceholderText("PER step messages appear here…")
        log_layout.addWidget(self._process_log)
        left_layout.addWidget(log_group)

        left_layout.addStretch()

        scroll = QScrollArea()
        scroll.setWidget(left_widget)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        main_layout.addWidget(scroll)

        # Right: graph
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(0, 0, 0, 0)
        title = QLabel("PER Live — Thorlabs power (mW) vs PRM angle")
        title.setStyleSheet("font-weight: bold; font-size: 13px; color: #e6e6e6;")
        right_layout.addWidget(title)

        if not _PG_AVAILABLE:
            right_layout.addWidget(QLabel("pyqtgraph required for graph display."))
            self._curve = None
        else:
            pw = pg.PlotWidget()
            pw.setBackground("w")
            p = pw.getPlotItem()
            p.showGrid(x=True, y=True, alpha=0.4)
            p.setLabel("bottom", "PRM Angle (deg)", color="#333333")
            p.setLabel("left", "Power (mW)", color="#333333")
            axis_pen = pg.mkPen(color="#333333", width=1)
            p.getAxis("left").setPen(axis_pen)
            p.getAxis("left").setTextPen(axis_pen)
            p.getAxis("bottom").setPen(axis_pen)
            p.getAxis("bottom").setTextPen(axis_pen)
            self._curve = pw.plot(
                [], [],
                pen=pg.mkPen("#00AA00", width=2),
                symbol="o",
                symbolSize=5,
                symbolBrush="#00AA00",
            )
            right_layout.addWidget(pw, 1)

        self._result_label = QLabel("Max: —   Min: —   PER: —   Angle: —")
        self._result_label.setStyleSheet("color: #c8c8c8; font-size: 11px;")
        right_layout.addWidget(self._result_label)
        main_layout.addWidget(right_widget, 1)

    def showEvent(self, event: QShowEvent):
        super().showEvent(event)
        try:
            set_dark_title_bar(int(self.winId()), True)
        except Exception:
            pass

    def set_params(self, params: dict):
        params = params or {}
        for k, lbl in self._value_labels.items():
            v = params.get(k)
            if k == "skip_actuator":
                lbl.setText("Yes" if v else "No")
            else:
                lbl.setText(_fmt(v))

    def _rolling(self, seq):
        if not seq:
            return seq
        if len(seq) <= LIVE_PLOT_MAX_POINTS:
            return seq
        return seq[-LIVE_PLOT_MAX_POINTS:]

    def update_live(self, result, angles, powers_mw):
        self._angles = list(angles or [])
        self._powers_mw = list(powers_mw or [])
        n = min(len(self._angles), len(self._powers_mw))

        if self._curve is not None and n:
            self._curve.setData(
                self._rolling(self._angles[:n]),
                self._rolling(self._powers_mw[:n]),
            )
        if result is not None:
            mx = getattr(result, "max_power", None)
            mn = getattr(result, "min_power", None)
            pd = getattr(result, "per_db", None)
            ag = getattr(result, "max_angle", None)
            self._result_label.setText(
                "Max (mW): {}   Min (mW): {}   PER (dB): {}   Angle (°): {}".format(
                    _fmt(mx), _fmt(mn), _fmt(pd), _fmt(ag)
                )
            )
            if bool(getattr(result, "is_final", False)):
                if bool(getattr(result, "passed", False)):
                    self._status.setText("Finished — Pass")
                else:
                    reasons = list(getattr(result, "fail_reasons", []) or [])
                    if any("stopped by user" in str(x).lower() for x in reasons):
                        self._status.setText("Stopped")
                    else:
                        self._status.setText("Finished — Fail (see log / Reason for Failure)")

    def set_status(self, text: str):
        self._status.setText(text or "")

    def clear_process_log(self) -> None:
        if hasattr(self, "_process_log"):
            self._process_log.clear()

    def append_process_log(self, text: str) -> None:
        pl = getattr(self, "_process_log", None)
        if pl is None:
            return
        t = (text or "").rstrip()
        if not t:
            return
        pl.appendPlainText(t)
        sb = pl.verticalScrollBar()
        sb.setValue(sb.maximum())

