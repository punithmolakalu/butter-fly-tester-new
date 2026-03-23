"""
BF Tester Application - Main Entry Point
Using MVVM (Model-View-ViewModel) Architecture with PyQt5

Structure:
- models/: Data models and business entities
- viewmodels/: View models with logic and commands
- views/: UI components (Views)
- utils/: Utilities, constants, helpers
- ui/: Fallback UI (used if MVVM import fails)

Debug: Set DEBUG_GUI=1 to print button/action lag to terminal.
If GUI closes suddenly: run from terminal or use run_with_crash_log.bat to see errors.
Set SKIP_AUTO_CONNECT=1 to disable auto-connect (avoids driver crashes on startup).
"""

import sys
import os
import traceback
import threading

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# #region agent log
try:
    from utils.debug_log import log
    log("main_startup", {"cwd": os.getcwd()}, "startup")
except Exception:
    pass
# #endregion

# Enable timing debug when DEBUG_GUI=1
if os.environ.get("DEBUG_GUI", "0").strip() in ("1", "true", "True"):
    print("[GUI] DEBUG_GUI=1 - timing will be printed to terminal")
# Diagnostic mode: extra logging for button lag and crash location
DIAGNOSTIC = os.environ.get("DIAGNOSTIC_MODE", "0").strip() in ("1", "true", "True")


def _exception_hook(exc_type, exc_value, exc_tb):
    """Log unhandled exceptions so user can see why GUI closed."""
    lines = traceback.format_exception(exc_type, exc_value, exc_tb)
    msg = "".join(lines)
    print("[CRASH] Unhandled exception - GUI closing:", file=sys.stderr)
    print(msg, file=sys.stderr)
    try:
        from utils.debug_log import log
        log("CRASH_unhandled", {"exc_type": str(exc_type.__name__), "exc_value": str(exc_value)[:200]}, "crash")
    except Exception:
        pass
    try:
        log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crash_log.txt")
        with open(log_path, "a", encoding="utf-8") as f:
            from datetime import datetime
            f.write(f"\n--- {datetime.now().isoformat()} [unhandled exception] ---\n")
            try:
                from utils.crash_context import get_crash_context
                f.write(get_crash_context() + "\n\n")
            except Exception:
                pass
            f.write(msg)
        print(f"[CRASH] Logged to {log_path}", file=sys.stderr)
    except Exception:
        pass
    sys.__excepthook__(exc_type, exc_value, exc_tb)


def _threading_excepthook(args):
    """Log exceptions from worker threads (Python 3.8+)."""
    try:
        msg = "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))
        print("[CRASH] Exception in worker thread:", file=sys.stderr)
        print(msg, file=sys.stderr)
        log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crash_log.txt")
        with open(log_path, "a", encoding="utf-8") as f:
            from datetime import datetime
            f.write(f"\n--- {datetime.now().isoformat()} [worker thread] ---\n")
            try:
                from utils.crash_context import get_crash_context
                f.write(get_crash_context() + "\n\n")
            except Exception:
                pass
            f.write(msg)
    except Exception:
        pass


sys.excepthook = _exception_hook
if hasattr(sys, "unraisablehook"):  # Python 3.8+ - catch exceptions in __del__, callbacks, etc.
    def _unraisable_hook(hook_args):
        try:
            msg = f"Unraisable: {hook_args.exc_type.__name__}: {hook_args.exc_value}"
            if hook_args.exc_traceback:
                msg += "\n" + "".join(traceback.format_exception(
                    hook_args.exc_type, hook_args.exc_value, hook_args.exc_traceback))
            else:
                msg += "\n(No Python traceback - exception may have originated in C/Qt code)"
            print(f"[CRASH] {msg}", file=sys.stderr)
            log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "crash_log.txt")
            with open(log_path, "a", encoding="utf-8") as f:
                from datetime import datetime
                f.write(f"\n--- {datetime.now().isoformat()} [unraisable] ---\n")
                try:
                    from utils.crash_context import get_crash_context
                    f.write(get_crash_context() + "\n\n")
                except Exception:
                    pass
                f.write(msg + "\n")
        except Exception:
            pass
    sys.unraisablehook = _unraisable_hook
if hasattr(threading, "excepthook"):  # Python 3.8+
    threading.excepthook = _threading_excepthook

# Import PyQt5 (suppress linter warnings)
from PyQt5.QtWidgets import QApplication  # type: ignore
from PyQt5.QtCore import Qt  # type: ignore
from PyQt5.QtGui import QIcon  # type: ignore

from utils.constants import APP_NAME, APP_ORGANIZATION, APP_VERSION
from utils.helpers import enable_dark_title_bar, suppress_qt_setgeometry_warnings


def main():
    """Main application entry point"""
    # Enable high DPI scaling (deprecated in Qt 5.14+, automatic in Qt 6)
    # Use getattr() for compatibility with different Qt versions and to avoid type checker errors
    high_dpi_scaling = getattr(Qt, 'AA_EnableHighDpiScaling', None)
    high_dpi_pixmaps = getattr(Qt, 'AA_UseHighDpiPixmaps', None)
    if high_dpi_scaling is not None:
        QApplication.setAttribute(high_dpi_scaling, True)
    if high_dpi_pixmaps is not None:
        QApplication.setAttribute(high_dpi_pixmaps, True)
    
    # Create application
    app = QApplication(sys.argv)
    suppress_qt_setgeometry_warnings()  # Stop "Unable to set geometry" console spam on Windows
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_ORGANIZATION)
    app.setApplicationVersion(APP_VERSION)
    
    # Import and create main view with MVVM
    try:
        from viewmodels import MainViewModel
        from views import MainView
        
        # Create ViewModel
        viewmodel = MainViewModel()
        
        # Ensure cleanup (Ando STOP, laser off, TEC off) runs when app quits - connect at app level
        app.aboutToQuit.connect(viewmodel.cleanup)
        # Log shutdown context for crash debugging
        def _on_about_to_quit():
            try:
                from utils.crash_context import set_active_operation
                set_active_operation("app_shutdown", "User closed application (normal quit)")
            except Exception:
                pass
        app.aboutToQuit.connect(_on_about_to_quit)
        
        # Create View and bind to ViewModel
        window = MainView(viewmodel)
        window.show()
        # Apply dark title bar on supported Windows versions
        enable_dark_title_bar(window)
        
        print(f"[OK] {APP_NAME} v{APP_VERSION} started with MVVM architecture")
        if DIAGNOSTIC:
            print("[DIAGNOSTIC] Mode ON - button clicks and tab loads logged; check crash_log.txt if app closes")
        
    except ImportError as e:
        print(f"[WARNING] MVVM not available ({e}), falling back to legacy UI")
        
        # Fallback to legacy UI
        try:
            from ui import MainWindow
            window = MainWindow()
            window.show()
            enable_dark_title_bar(window)
            print(f"[OK] {APP_NAME} v{APP_VERSION} started with legacy UI")
        except Exception as e2:
            print(f"[ERROR] Failed to start application: {e2}")
            sys.exit(1)
    
    except Exception as e:
        print(f"[ERROR] Failed to initialize MVVM: {e}")
        
        # Attempt fallback to legacy UI
        try:
            from ui import MainWindow
            window = MainWindow()
            window.show()
            enable_dark_title_bar(window)
            print(f"[OK] {APP_NAME} started with legacy UI (fallback)")
        except Exception as e2:
            print(f"[ERROR] All UI options failed: {e2}")
            sys.exit(1)
    
    # Run application
    exit_code = app.exec_()
    if DIAGNOSTIC:
        try:
            from utils.crash_context import get_crash_context
            print(f"[DIAGNOSTIC] App exiting (code={exit_code}), last operation:\n{get_crash_context()}")
        except Exception:
            pass
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
