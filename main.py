"""Butterfly Tester — MVVM + PyQt5."""
import sys
import warnings

# Suppress PyVISA resource-discovery warnings (TCPIP/psutil/zeroconf); connection code unchanged
warnings.filterwarnings("ignore", category=UserWarning, module="pyvisa_py.tcpip")

from PyQt5.QtCore import QTimer, Qt
from PyQt5.QtWidgets import QApplication
from view.dark_theme import PYQTGRAPH_PLOT_BACKGROUND, get_dark_palette
from view.main_window import MainWindow
from viewmodel.main_viewmodel import MainViewModel

# Applied before MainWindow exists so the first frame is not plain white (Windows default).
_APP_SHELL_STYLESHEET = "QMainWindow, QWidget { background-color: #1e1e23; color: #e6e6e6; }"


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

    viewmodel = MainViewModel()
    # Ensure all instrument threads/connections (including pythonnet/Kinesis PRM)
    # are cleanly shut down before the Python runtime exits to avoid access
    # violations from unmanaged drivers during interpreter shutdown.
    app.aboutToQuit.connect(viewmodel.shutdown)
    window = MainWindow(viewmodel)
    # Keep a strong ref until quit (avoids rare GC edge cases during startup)
    app.setProperty("_main_window", window)
    window.showMaximized()
    # Flush one event-loop pass so the dark UI paints before the next timers (avoids a long white client area on Windows).
    app.processEvents()
    # Let the first paint complete before workers / sim auto-connect run.
    QTimer.singleShot(0, viewmodel.start_workers)
    return _run_event_loop(app)


if __name__ == "__main__":
    sys.exit(main())
