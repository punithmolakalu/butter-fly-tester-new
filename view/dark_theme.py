"""Dark theme palette and stylesheet for PyQt5. Windows: dark title bar via DWM."""
import os
import sys
from PyQt5.QtGui import QPalette, QColor
from PyQt5.QtCore import Qt

# Arrow icons for spinbox (up/down) - from resource folder
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_resource = os.path.join(_root, "resource")
def _arrow_url(name):
    p = os.path.abspath(os.path.join(_resource, name + ".png")).replace("\\", "/").replace(" ", "%20")
    return ("file:///" + p) if os.name == "nt" else ("file://" + p)
_ARROW_UP, _ARROW_DOWN = _arrow_url("arrow_up"), _arrow_url("arrow_down")


def spinbox_arrow_styles() -> str:
    """Return CSS for QSpinBox/QDoubleSpinBox up/down arrows: same background as spinbox so no separate grey box overlapping value."""
    # Match spinbox base (#25252c) and border (#3a3a42) so buttons don't look like a separate grey box
    btn_common = (
        " width: 22px; min-width: 22px; height: 14px; min-height: 14px; "
        " background-color: #25252c; "
        " border: none; border-left: 1px solid #3a3a42; "
        " subcontrol-origin: border; subcontrol-position: center; "
    )
    return (
        f" QSpinBox::up-button, QDoubleSpinBox::up-button {{ {btn_common} }} "
        f" QSpinBox::down-button, QDoubleSpinBox::down-button {{ {btn_common} }} "
        f' QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ width: 14px; height: 14px; image: url("{_ARROW_UP}"); }} '
        f' QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ width: 14px; height: 14px; image: url("{_ARROW_DOWN}"); }} '
    )


def get_dark_palette() -> QPalette:
    p = QPalette()
    p.setColor(QPalette.Window, QColor(30, 30, 35))
    p.setColor(QPalette.WindowText, QColor(230, 230, 230))
    p.setColor(QPalette.Base, QColor(25, 25, 28))
    p.setColor(QPalette.AlternateBase, QColor(45, 45, 52))
    p.setColor(QPalette.ToolTipBase, QColor(230, 230, 230))
    p.setColor(QPalette.ToolTipText, QColor(230, 230, 230))
    p.setColor(QPalette.Text, QColor(230, 230, 230))
    p.setColor(QPalette.Button, QColor(45, 45, 52))
    p.setColor(QPalette.ButtonText, QColor(230, 230, 230))
    p.setColor(QPalette.BrightText, Qt.red)
    p.setColor(QPalette.Link, QColor(42, 130, 218))
    p.setColor(QPalette.Highlight, QColor(42, 130, 218))
    p.setColor(QPalette.HighlightedText, Qt.black)
    return p


# UI color roles (green=positive, red=negative, orange=action/clear, blue=primary/scan)
COLOR_GREEN = "#4caf50"       # Run, Connect, Connected
COLOR_GREEN_HOVER = "#388e3c"
COLOR_RED = "#f44336"        # Stop, Disconnect, Disconnected
COLOR_RED_HOVER = "#d32f2f"
COLOR_ORANGE = "#ff9800"     # Clear, Align
COLOR_ORANGE_HOVER = "#f57c00"
COLOR_BLUE = "#2196f3"       # Scan, primary actions, selected tab
COLOR_BLUE_HOVER = "#1976d2"

# PyQtGraph: match app dark theme (was white — caused full-window white flash during startup / tab paint).
PYQTGRAPH_PLOT_BACKGROUND = "#25252c"
PYQTGRAPH_VIEWBOX_RGB = (37, 37, 44)
PYQTGRAPH_AXIS_TEXT = "#d4d4d4"


def main_stylesheet() -> str:
    return f"""
    QMainWindow, QWidget {{ background-color: #1e1e23; }}
    QTabWidget::pane {{ border: 1px solid #3a3a42; background-color: #1e1e23; margin: 0; padding: 0; top: 0; }}
    /* Tabs: enough horizontal padding + min-width so labels are not clipped (e.g. "Plot", "Calculation"). */
    QTabBar::tab {{
        background-color: #2d2d34;
        color: #e6e6e6;
        font-size: 13px;
        font-weight: normal;
        padding: 10px 20px;
        margin-right: 3px;
        margin-left: 1px;
        min-height: 26px;
        min-width: 88px;
        border: 1px solid #3a3a42;
        border-bottom: none;
        border-top-left-radius: 4px;
        border-top-right-radius: 4px;
    }}
    QTabBar::tab:selected {{
        background-color: {COLOR_BLUE};
        color: #ffffff;
        font-weight: normal;
        border-color: {COLOR_BLUE};
    }}
    QTabBar::tab:hover:!selected {{ background-color: #35353c; }}
    QPushButton {{ background-color: #2d2d34; color: #e6e6e6; border: 1px solid #3a3a42; padding: 6px 14px; }}
    QPushButton:hover {{ background-color: #3a3a42; }}
    QPushButton:pressed {{ background-color: #25252c; }}
    QPushButton:disabled {{ background-color: #25252c; color: #808080; }}
    QPushButton#btn_run {{ background-color: {COLOR_GREEN}; color: white; font-weight: bold; }}
    QPushButton#btn_run:hover {{ background-color: {COLOR_GREEN_HOVER}; }}
    QPushButton#btn_stop {{ background-color: {COLOR_RED}; color: white; font-weight: bold; }}
    QPushButton#btn_stop:hover {{ background-color: {COLOR_RED_HOVER}; }}
    QPushButton#btn_clear {{ background-color: {COLOR_ORANGE}; color: white; }}
    QPushButton#btn_clear:hover {{ background-color: {COLOR_ORANGE_HOVER}; }}
    QPushButton#btn_align {{ background-color: {COLOR_ORANGE}; color: white; font-weight: bold; font-size: 14px; padding: 10px 24px; }}
    QPushButton#btn_align:hover {{ background-color: {COLOR_ORANGE_HOVER}; }}
    QPushButton#btn_primary {{ background-color: {COLOR_BLUE}; color: white; }}
    QPushButton#btn_primary:hover {{ background-color: {COLOR_BLUE_HOVER}; }}
    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{ background-color: #25252c; color: #e6e6e6; border: 1px solid #3a3a42; padding: 4px; }}
    QSpinBox::up-button, QDoubleSpinBox::up-button {{ width: 22px; min-width: 22px; height: 14px; min-height: 14px; background-color: #25252c; border: none; border-left: 1px solid #3a3a42; subcontrol-origin: border; subcontrol-position: center; }}
    QSpinBox::down-button, QDoubleSpinBox::down-button {{ width: 22px; min-width: 22px; height: 14px; min-height: 14px; background-color: #25252c; border: none; border-left: 1px solid #3a3a42; subcontrol-origin: border; subcontrol-position: center; }}
    QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ width: 14px; height: 14px; image: url("{_ARROW_UP}"); }}
    QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ width: 14px; height: 14px; image: url("{_ARROW_DOWN}"); }}
    QFrame#footer {{ background-color: #25252c; border-top: 1px solid #3a3a42; }}
    QMenuBar {{ background-color: #1e1e23; color: #e6e6e6; }}
    QMenuBar::item:selected {{ background-color: #3a3a42; }}
    QMenu {{ background-color: #2d2d34; color: #e6e6e6; }}
    QMenu::item:selected {{ background-color: #3a3a42; }}
    """


def set_dark_title_bar(hwnd: int, dark: bool = True) -> None:
    """Set window title bar to dark theme on Windows. hwnd = int(widget.winId())."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        from ctypes import wintypes
        dwmapi = ctypes.windll.dwmapi  # type: ignore
        DWMWA_USE_IMMERSIVE_DARK_MODE = 20
        value = ctypes.c_int(1 if dark else 0)
        dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd),
            DWMWA_USE_IMMERSIVE_DARK_MODE,
            ctypes.byref(value),
            ctypes.sizeof(value),
        )
    except Exception:
        pass
