"""Butterfly Tester — MVVM + PyQt5."""
import sys
import warnings

# Suppress PyVISA resource-discovery warnings (TCPIP/psutil/zeroconf); connection code unchanged
warnings.filterwarnings("ignore", category=UserWarning, module="pyvisa_py.tcpip")

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QApplication
from view.dark_theme import PYQTGRAPH_PLOT_BACKGROUND, get_dark_palette
from view.main_window import MainWindow
from viewmodel.main_viewmodel import MainViewModel

# Applied before MainWindow exists so the first frame is not plain white (Windows default).
# Do not use a bare "QWidget { background: ... }" here — QPushButton is a QWidget and that rule
# flattens all buttons to the same gray and overrides QPushButton#btn_run / #btn_stop (semantic colors).
_APP_SHELL_STYLESHEET = """
QMainWindow { background-color: #1e1e23; color: #e6e6e6; }
QWidget#main_content { background-color: #1e1e23; }
QTabWidget::pane { background-color: #1e1e23; border: 1px solid #3a3a42; }
QStackedWidget { background-color: #1e1e23; }
QScrollArea { background-color: #1e1e23; border: 1px solid #3a3a42; }
"""


def _set_pre_app_attributes() -> None:
    """Qt application attributes that must be set before QApplication()."""
    # Stylesheet inheritance (when supported)
    _propagate = getattr(Qt, "AA_UseStyleSheetPropagationInWidgetStyles", None)
    if _propagate is not None:
        try:
            QApplication.setAttribute(_propagate, True)
        except Exception:
            pass
    # Crisp UI on high-DPI displays (Windows / mixed scaling)
    for name in ("AA_EnableHighDpiScaling", "AA_UseHighDpiPixmaps"):
        attr = getattr(Qt, name, None)
        if attr is not None:
            try:
                QApplication.setAttribute(attr, True)
            except Exception:
                pass


def _run_event_loop(app: QApplication) -> int:
    """PyQt5 uses exec_(); newer bindings may provide exec()."""
    exe = getattr(app, "exec", None)
    if callable(exe):
        code = exe()
        return int(code) if isinstance(code, int) else 0
    code = app.exec_()
    return int(code) if isinstance(code, int) else 0


def main() -> int:
    _set_pre_app_attributes()
    app = QApplication(sys.argv)
    app.setApplicationName("Butterfly Tester")
    app.setApplicationDisplayName("Butterfly Tester")
    app.setStyle("Fusion")
    app.setPalette(get_dark_palette())
    app.setStyleSheet(_APP_SHELL_STYLESHEET)

    try:
        import pyqtgraph as pg

        pg.setConfigOptions(antialias=True)
        pg.setConfigOption("background", PYQTGRAPH_PLOT_BACKGROUND)
        pg.setConfigOption("foreground", "w")
    except Exception:
        pass

    # ViewModel starts worker QThreads (non-blocking emits). Heavy UI + COM/GPIB scan + auto-connect
    # are deferred in MainWindow._complete_heavy_startup so the window can paint first.
    viewmodel = MainViewModel()
    # Ensure all instrument threads/connections (including pythonnet/Kinesis PRM)
    # are cleanly shut down before the Python runtime exits to avoid access
    # violations from unmanaged drivers during interpreter shutdown.
    app.aboutToQuit.connect(viewmodel.shutdown)
    window = MainWindow(viewmodel)
    # Keep a strong ref until quit (avoids rare GC edge cases during startup)
    app.setProperty("_main_window", window)
    window.ensurePolished()
    # Main entry schedules deferred work (see _complete_heavy_startup); showEvent skips duplicate if this is set.
    window._heavy_startup_scheduled_from_main = True
    window.showMaximized()
    # Let the window paint once with placeholders + theme (no long blocking PyQtGraph build in __init__).
    app.processEvents()
    # Qt equivalent of Tkinter after(): next event-loop tick — not before first frame (avoids long white flash).
    QTimer.singleShot(0, window._complete_heavy_startup)
    return _run_event_loop(app)


if __name__ == "__main__":
    sys.exit(main())
