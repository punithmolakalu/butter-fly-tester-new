"""Butterfly Tester — MVVM + PyQt5."""
import logging
import os
import sys
import threading
import traceback
import warnings

# Suppress PyVISA resource-discovery warnings (TCPIP/psutil/zeroconf); connection code unchanged
warnings.filterwarnings("ignore", category=UserWarning, module="pyvisa_py.tcpip")
try:
    from pyvisa.errors import VisaIOWarning

    warnings.filterwarnings("ignore", category=VisaIOWarning)
except Exception:
    pass

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication
from view.dark_theme import apply_application_theme, is_dark_theme_saved
from view.main_window import MainWindow
from viewmodel.main_viewmodel import MainViewModel

class _PyVisaStaleSessionCloseFilter(logging.Filter):
    """
    PyVISA logs WARNING + traceback when Resource.close() runs after the VISA session is already
    invalid (cable unplugged, NI-VISA already tore down the handle). The exception is suppressed
    inside pyvisa; only the log line is noisy — drop it so stderr matches real failures.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if not str(record.name).startswith("pyvisa"):
            return True
        try:
            msg = record.getMessage()
        except Exception:
            msg = str(getattr(record, "msg", ""))
        if "Exception suppressed while closing a resource" in msg:
            return False
        if "Exception suppressed while destroying a resource" in msg:
            return False
        if "InvalidSession" in msg:
            return False
        if "VI_ERROR_INV_OBJECT" in msg:
            return False
        return True


def _configure_terminal_logging() -> None:
    """Send Python log records to stderr. Set BF_LOG_LEVEL=DEBUG|INFO|WARNING|ERROR (default INFO)."""
    env = (os.environ.get("BF_LOG_LEVEL") or "INFO").strip().upper()
    mapping = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "WARN": logging.WARNING,
        "ERROR": logging.ERROR,
    }
    level = mapping.get(env, logging.INFO)
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    datefmt = "%Y-%m-%d %H:%M:%S"
    try:
        logging.basicConfig(level=level, format=fmt, datefmt=datefmt, stream=sys.stderr, force=True)
    except TypeError:
        root = logging.getLogger()
        root.handlers.clear()
        logging.basicConfig(level=level, format=fmt, datefmt=datefmt, stream=sys.stderr)
    logging.captureWarnings(True)
    _pv_filt = _PyVisaStaleSessionCloseFilter()
    logging.getLogger("pyvisa").addFilter(_pv_filt)
    logging.getLogger("pyvisa.resources").addFilter(_pv_filt)


def _install_excepthooks() -> None:
    """Log uncaught exceptions in the main thread and in worker threads (Python 3.8+)."""

    def _main_excepthook(exc_type, exc_value, exc_tb):
        if exc_type is KeyboardInterrupt:
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        logging.getLogger("bf.uncaught").critical("Uncaught exception in main thread (traceback below)")
        traceback.print_exception(exc_type, exc_value, exc_tb, file=sys.stderr)

    sys.excepthook = _main_excepthook

    if hasattr(threading, "excepthook"):
        def _thread_excepthook(args):  # type: ignore[no-untyped-def]
            logging.getLogger("bf.thread").error(
                "Uncaught exception in thread %r (traceback below)",
                getattr(args.thread, "name", "?"),
            )
            traceback.print_exception(
                args.exc_type, args.exc_value, args.exc_traceback, file=sys.stderr
            )

        threading.excepthook = _thread_excepthook  # type: ignore[attr-defined]


def _install_qt_message_handler() -> None:
    """Forward Qt qWarning/qCritical (and optional debug) to stderr via logging."""
    try:
        from PyQt5.QtCore import QtMsgType, qInstallMessageHandler

        def _qt_handler(mode, context, message):  # noqa: ARG001
            msg = str(message).strip()
            if not msg:
                return
            lg = logging.getLogger("qt")
            if mode == QtMsgType.QtFatalMsg:
                lg.critical("%s", msg)
            elif mode == QtMsgType.QtCriticalMsg:
                lg.error("%s", msg)
            elif mode == QtMsgType.QtWarningMsg:
                lg.warning("%s", msg)
            elif mode == QtMsgType.QtDebugMsg:
                lg.debug("%s", msg)
            else:
                lg.info("%s", msg)

        qInstallMessageHandler(_qt_handler)
    except Exception as exc:
        logging.getLogger("bf").debug("Qt message handler not installed: %s", exc)


def _mirror_connection_logs_to_terminal(viewmodel: MainViewModel) -> None:
    """Duplicate status-log lines to the terminal (same text as the Main tab log).

    Full ``connection_state`` dicts are DEBUG-only so the default INFO level stays quiet
    during Connect All; set BF_LOG_LEVEL=DEBUG to trace state snapshots.
    """
    lg = logging.getLogger("bf.connection")

    def _on_status(msg: str) -> None:
        lg.info("%s", msg)

    def _on_state(state: dict) -> None:
        lg.debug("connection_state: %s", state)

    viewmodel.status_log_message.connect(_on_status)
    viewmodel.connection_state_changed.connect(_on_state)


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
    _configure_terminal_logging()
    _install_excepthooks()
    _set_pre_app_attributes()
    app = QApplication(sys.argv)
    _install_qt_message_handler()
    app.setApplicationName("Butterfly Tester")
    app.setApplicationDisplayName("Butterfly Tester")
    app.setStyle("Fusion")
    _startup_dark = is_dark_theme_saved()
    apply_application_theme(app, _startup_dark)

    try:
        import pyqtgraph as pg

        pg.setConfigOptions(antialias=True)
    except Exception:
        pass

    # ViewModel starts worker QThreads (non-blocking emits). Heavy UI + saved addresses + auto-connect
    # run in MainWindow._complete_heavy_startup right after the first paint (processEvents).
    viewmodel = MainViewModel()
    _mirror_connection_logs_to_terminal(viewmodel)
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
    # Run immediately after first paint; no extra timer tick or ms delay before lazy UI + auto-connect.
    window._complete_heavy_startup()
    return _run_event_loop(app)


if __name__ == "__main__":
    sys.exit(main())
 