"""Dark / light theme palette and stylesheet for PyQt5. Windows: dark title bar via DWM."""
import sys
from dataclasses import dataclass
from typing import Any

from PyQt5.QtGui import QPalette, QColor
from PyQt5.QtCore import Qt, QSettings

def _spinbox_stepper_and_arrows_qss(*, btn_bg: str, line: str, arrow: str) -> str:
    """Step buttons + arrows without external images (file:// URLs are unreliable on some Windows/OneDrive paths)."""
    w = "width: 22px; min-width: 22px;"
    common = f" {w} background-color: {btn_bg}; border: none; border-left: 1px solid {line}; subcontrol-origin: border; "
    up_btn = (
        f"QSpinBox::up-button, QDoubleSpinBox::up-button {{ {common} subcontrol-position: top right; "
        f"height: 11px; min-height: 10px; border-top-right-radius: 2px; }}"
    )
    down_btn = (
        f"QSpinBox::down-button, QDoubleSpinBox::down-button {{ {common} subcontrol-position: bottom right; "
        f"height: 11px; min-height: 10px; border-top: 1px solid {line}; border-bottom-right-radius: 2px; }}"
    )
    # Triangles via borders. Qt QSS often ignores ``transparent`` on borders (shows a dash only);
    # match left/right borders to the stepper button bg so the chevron reads as a real up/down arrow.
    arrows = (
        "QSpinBox::up-arrow, QDoubleSpinBox::up-arrow { image: none; width: 0px; height: 0px; "
        "border-left: 5px solid %(btn)s; border-right: 5px solid %(btn)s; "
        "border-bottom: 6px solid %(arr)s; margin-right: 4px; margin-bottom: 1px; } "
        "QSpinBox::down-arrow, QDoubleSpinBox::down-arrow { image: none; width: 0px; height: 0px; "
        "border-left: 5px solid %(btn)s; border-right: 5px solid %(btn)s; "
        "border-top: 6px solid %(arr)s; margin-right: 4px; margin-top: 1px; } "
        % {"btn": btn_bg, "arr": arrow}
    )
    hover = (
        "QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover, "
        "QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover { background-color: #4a4a54; } "
        "QSpinBox::up-button:pressed, QDoubleSpinBox::up-button:pressed, "
        "QSpinBox::down-button:pressed, QDoubleSpinBox::down-button:pressed { background-color: #55555f; } "
    )
    return " " + up_btn + " " + down_btn + " " + arrows + " " + hover + " "


def spinbox_arrow_styles() -> str:
    """QSS for QSpinBox/QDoubleSpinBox step buttons and arrow icons.

    Up and down must use top right / bottom right — both ``center`` stacks them and hides arrows on Fusion/Windows.
    """
    return _spinbox_stepper_and_arrows_qss(btn_bg="#3a3a45", line="#5a5a66", arrow="#e8e8f0")


def spinbox_arrow_styles_for_theme(dark: bool) -> str:
    """Inline spinbox arrows for Engineer / Main tab when global QSS is overridden per-widget."""
    if dark:
        return spinbox_arrow_styles()
    return _spinbox_stepper_and_arrows_qss(btn_bg="#ececec", line="#b0b0b0", arrow="#333333")


def _main_spinbox_qss(px: Any, dark: bool) -> str:
    """Global main window spinboxes: scaled padding + triangle arrows (no file URLs)."""
    if dark:
        base, line, btn, edge, arr, txt = "#25252c", "#3a3a42", "#3a3a45", "#5a5a66", "#e8e8f0", "#e6e6e6"
        hov, prs = "#4a4a54", "#55555f"
    else:
        base, line, btn, edge, arr, txt = "#ffffff", "#c0c0c0", "#ececec", "#a8a8a8", "#333333", "#222222"
        hov, prs = "#d8d8d8", "#c8c8c8"
    w, h1, h0, br = px(22), px(11), px(10), px(2)
    return f"""
    QSpinBox, QDoubleSpinBox {{ background-color: {base}; color: {txt}; border: 1px solid {line}; padding: {px(4)}px; min-height: {px(26)}px; }}
    QSpinBox::up-button, QDoubleSpinBox::up-button {{ width: {w}px; min-width: {w}px; height: {h1}px; min-height: {h0}px; background-color: {btn}; border: none; border-left: 1px solid {edge}; subcontrol-origin: border; subcontrol-position: top right; border-top-right-radius: {br}px; }}
    QSpinBox::down-button, QDoubleSpinBox::down-button {{ width: {w}px; min-width: {w}px; height: {h1}px; min-height: {h0}px; background-color: {btn}; border: none; border-left: 1px solid {edge}; border-top: 1px solid {edge}; subcontrol-origin: border; subcontrol-position: bottom right; border-bottom-right-radius: {br}px; }}
    QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover, QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{ background-color: {hov}; }}
    QSpinBox::up-button:pressed, QDoubleSpinBox::up-button:pressed, QSpinBox::down-button:pressed, QDoubleSpinBox::down-button:pressed {{ background-color: {prs}; }}
    QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: none; width: 0px; height: 0px; border-left: {px(5)}px solid {btn}; border-right: {px(5)}px solid {btn}; border-bottom: {px(7)}px solid {arr}; margin-right: {px(4)}px; margin-bottom: 1px; }}
    QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: none; width: 0px; height: 0px; border-left: {px(5)}px solid {btn}; border-right: {px(5)}px solid {btn}; border-top: {px(7)}px solid {arr}; margin-right: {px(4)}px; margin-top: 1px; }}
    """


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


def get_light_palette() -> QPalette:
    p = QPalette()
    p.setColor(QPalette.Window, QColor(240, 240, 240))
    p.setColor(QPalette.WindowText, QColor(34, 34, 34))
    p.setColor(QPalette.Base, QColor(255, 255, 255))
    p.setColor(QPalette.AlternateBase, QColor(233, 233, 233))
    p.setColor(QPalette.ToolTipBase, QColor(255, 255, 220))
    p.setColor(QPalette.ToolTipText, QColor(34, 34, 34))
    p.setColor(QPalette.Text, QColor(34, 34, 34))
    p.setColor(QPalette.Button, QColor(228, 228, 228))
    p.setColor(QPalette.ButtonText, QColor(34, 34, 34))
    p.setColor(QPalette.BrightText, Qt.red)
    p.setColor(QPalette.Link, QColor(25, 118, 210))
    p.setColor(QPalette.Highlight, QColor(33, 150, 243))
    p.setColor(QPalette.HighlightedText, Qt.white)
    return p


def is_dark_theme_saved() -> bool:
    """User preference: Settings → Dark theme (default on)."""
    try:
        v: Any = QSettings("BF", "ButterflyTester").value("appearance/dark_theme", True)
        if isinstance(v, str):
            return v.strip().lower() not in ("0", "false", "no", "off")
        return True if v is None else bool(v)
    except Exception:
        return True


def set_dark_theme_saved(dark: bool) -> None:
    try:
        QSettings("BF", "ButterflyTester").setValue("appearance/dark_theme", bool(dark))
    except Exception:
        pass


def app_shell_stylesheet(dark: bool = True) -> str:
    """QApplication-level shell before MainWindow; avoids white flash. Matches main.py _APP_SHELL_STYLESHEET."""
    if dark:
        return (
            "QMainWindow { background-color: #1e1e23; color: #e6e6e6; }\n"
            "QWidget#main_content { background-color: #1e1e23; }\n"
            "QTabWidget::pane { background-color: #1e1e23; border: 1px solid #3a3a42; }\n"
            "QStackedWidget { background-color: #1e1e23; }\n"
            "QScrollArea { background-color: #1e1e23; border: 1px solid #3a3a42; }\n"
        )
    return (
        "QMainWindow { background-color: #f0f0f0; color: #222222; }\n"
        "QWidget#main_content { background-color: #f0f0f0; }\n"
        "QTabWidget::pane { background-color: #f0f0f0; border: 1px solid #c0c0c0; }\n"
        "QStackedWidget { background-color: #f0f0f0; }\n"
        "QScrollArea { background-color: #f0f0f0; border: 1px solid #c0c0c0; }\n"
    )


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


def configure_pyqtgraph_for_theme(dark: bool = True) -> None:
    try:
        import pyqtgraph as pg  # type: ignore

        if dark:
            pg.setConfigOption("background", PYQTGRAPH_PLOT_BACKGROUND)
            pg.setConfigOption("foreground", "w")
        else:
            pg.setConfigOption("background", "w")
            pg.setConfigOption("foreground", "k")
    except Exception:
        pass


def apply_application_theme(app: Any, dark: bool) -> None:
    """Palette + app shell QSS + pyqtgraph defaults (call when toggling theme or at startup)."""
    try:
        app.setPalette(get_dark_palette() if dark else get_light_palette())
    except Exception:
        pass
    try:
        app.setStyleSheet(app_shell_stylesheet(dark))
    except Exception:
        pass
    configure_pyqtgraph_for_theme(dark)


def theme_chrome_bg(dark: bool) -> str:
    """Main tab / plot host background (matches app shell)."""
    return "#1e1e23" if dark else "#f0f0f0"


def theme_chrome_inner(dark: bool) -> str:
    """Slightly inset panels (footer, inputs area feel)."""
    return "#25252c" if dark else "#ffffff"


def theme_footer_muted_text(dark: bool) -> str:
    return "#b0b0b0" if dark else "#555555"


@dataclass(frozen=True)
class ThemeTokens:
    """Structured colors for inline QSS (MainWindow tabs, dialogs)."""

    dark: bool
    chrome: str
    panel: str
    panel_bd: str
    text: str
    muted: str
    caption: str
    input_bg: str
    input_fg: str
    input_bd: str
    cell_hover: str
    chip_bg: str
    chip_bd: str
    footer_bg: str
    footer_top: str


def theme_tokens(dark: bool) -> ThemeTokens:
    if dark:
        return ThemeTokens(
            True,
            "#1e1e23",
            "#2d2d34",
            "#3a3a42",
            "#e6e6e6",
            "#b0b0b0",
            "#c8c8c8",
            "#25252c",
            "#e6e6e6",
            "#3a3a42",
            "#3a3a42",
            "#2c2c34",
            "#3a3a42",
            "#25252c",
            "#3a3a42",
        )
    return ThemeTokens(
        False,
        "#f0f0f0",
        "#f5f5f5",
        "#c0c0c0",
        "#222222",
        "#555555",
        "#555555",
        "#ffffff",
        "#222222",
        "#b0b0b0",
        "#d8d8d8",
        "#ececec",
        "#c0c0c0",
        "#e8e8e8",
        "#c0c0c0",
    )


def theme_qframe_form_panel_qss(t: ThemeTokens, frame_object_name: str) -> str:
    """Summary / Result summary frame with read-only line edits."""
    return (
        f"QFrame#{frame_object_name} {{ background-color: {t.panel}; border: 1px solid {t.panel_bd}; border-radius: 4px; }} "
        f"QLabel {{ color: {t.text}; font-size: 11pt; background-color: transparent; }} "
        f"QLineEdit {{ background-color: {t.input_bg}; color: {t.input_fg}; border: 1px solid {t.input_bd}; "
        f"padding: 4px 6px; min-height: 22px; max-height: 24px; font-size: 11pt; }} "
        f'QLineEdit[readOnly="true"] {{ background-color: {t.input_bg}; }}'
    )


def theme_qgroupbox_plot_surround_qss(t: ThemeTokens) -> str:
    """Group boxes around plot areas (Plot tab, Result tab graphs)."""
    return (
        f"QGroupBox {{ font-weight: bold; font-size: 12px; border: 1px solid {t.panel_bd}; border-radius: 4px; "
        f"margin-top: 10px; padding-top: 8px; background-color: {t.panel}; color: {t.text}; }}"
        "QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 6px; }"
    )


def theme_metric_caption_style(t: ThemeTokens) -> str:
    return f"color: {t.caption}; font-size: 11px; background: transparent;"


def theme_metric_field_style(t: ThemeTokens) -> str:
    return (
        f"background-color: {t.input_bg}; color: {t.input_fg}; border: 1px solid {t.input_bd}; "
        "padding: 3px 6px; min-width: 76px; max-width: 128px; font-size: 11px;"
    )


def theme_failure_outer_qss(t: ThemeTokens) -> str:
    return (
        f"QFrame {{ border: 1px solid {t.panel_bd}; border-radius: 4px; padding: 8px; background-color: {t.panel}; }}"
    )


def theme_failure_plaintext_qss(t: ThemeTokens) -> str:
    return f"background-color: {t.panel}; color: {t.text}; border: 1px solid {t.panel_bd};"


def theme_console_plaintext_qss(t: ThemeTokens) -> str:
    return (
        f"QPlainTextEdit {{ font-family: Consolas, monospace; font-size: 11px; "
        f"background-color: {t.input_bg}; color: {t.input_fg}; border: 1px solid {t.input_bd}; }}"
    )


def theme_pass_fail_chip_style(t: ThemeTokens) -> str:
    return f"color: #888888; background-color: {t.chip_bg}; border: 1px solid {t.chip_bd};"


def theme_pass_fail_name_style(t: ThemeTokens) -> str:
    return f"color: {t.text}; font-size: 12px; font-weight: bold;"


def theme_engineer_groupbox_qss(t: ThemeTokens) -> str:
    return (
        f"QGroupBox {{ font-weight: bold; font-size: 13px; border: 1px solid {t.panel_bd}; border-radius: 4px; "
        f"margin: 0; padding: 18px 6px 6px 6px; background-color: {t.panel}; }} "
        f"QGroupBox::title {{ subcontrol-origin: padding; subcontrol-position: top left; top: 2px; left: 10px; "
        f"padding: 0 6px; color: {t.text}; font-size: 13px; }}"
    )


def theme_engineer_spin_qss(t: ThemeTokens) -> str:
    return (
        f"background-color: {t.input_bg}; color: {t.input_fg}; border: 1px solid {t.input_bd}; "
        f"font-size: 12px; min-height: 22px; max-height: 26px;"
    ) + spinbox_arrow_styles_for_theme(t.dark)


def theme_engineer_btn_off_qss(t: ThemeTokens, *, pv: int, ph: int, fs: int = 12) -> str:
    return (
        f"QPushButton {{ background-color: {t.panel}; color: {t.text}; font-size: {fs}px; "
        f"padding: {pv}px {ph}px; }} QPushButton:hover {{ background-color: {t.cell_hover}; }}"
    )


def theme_ando_stop_idle_qss(t: ThemeTokens) -> str:
    return (
        f"QPushButton {{ background-color: {t.panel}; color: {t.text}; }} "
        f"QPushButton:hover {{ background-color: {t.cell_hover}; }}"
    )


def theme_actuator_status_bar_qss(t: ThemeTokens) -> str:
    c = "#b0bec5" if t.dark else "#546e7a"
    return (
        f"QLabel#actuator_status_bar {{ background-color: {t.panel}; color: {c}; "
        f"padding: 6px 8px; border-radius: 3px; font-size: 11px; }}"
    )


def theme_engineer_lineedit_ando_qss(t: ThemeTokens) -> str:
    return (
        f"background-color: {t.input_bg}; color: {t.input_fg}; font-size: 11px; min-height: 22px; max-height: 26px; "
        f"padding: 4px; border: 1px solid {t.input_bd};"
    )


def theme_engineer_combo_ando_qss(t: ThemeTokens, *, font_px: int = 12) -> str:
    return (
        f"background-color: {t.input_bg}; color: {t.input_fg}; font-size: {font_px}px; min-height: 24px; "
        f"border: 1px solid {t.input_bd};"
    )


def theme_wavemeter_big_value_qss(t: ThemeTokens) -> str:
    return f"background: transparent; color: {t.text}; font-size: 24px; font-weight: bold; min-height: 32px;"


def theme_main_tab_gentec_mult_spin_qss(t: ThemeTokens, sp4: int, sp6: int, sp22: int, sp12: int) -> str:
    return (
        f"QDoubleSpinBox {{ background-color: {t.input_bg}; color: {t.input_fg}; border: 1px solid {t.input_bd}; "
        f"padding: {sp4}px {sp6}px; min-height: {sp22}px; font-size: {sp12}px; font-weight: bold; }}"
    ) + spinbox_arrow_styles_for_theme(t.dark)


def theme_prm_stop_grey_qss(t: ThemeTokens) -> str:
    return (
        f"QPushButton {{ background-color: {t.panel}; color: {t.text}; font-weight: bold; }} "
        f"QPushButton:hover {{ background-color: {t.cell_hover}; }}"
    )


def theme_tests_pass_chip_pass(t: ThemeTokens) -> str:
    if t.dark:
        return "color: #b9f6ca; background-color: #1b3d2e; border: 1px solid #4caf50;"
    return "color: #1b5e20; background-color: #e8f5e9; border: 1px solid #4caf50;"


def theme_tests_pass_chip_fail(t: ThemeTokens) -> str:
    if t.dark:
        return "color: #ffcdd2; background-color: #3d1b1b; border: 1px solid #c62828;"
    return "color: #b71c1c; background-color: #ffebee; border: 1px solid #c62828;"


def theme_manual_read_wavelength_btn_qss(t: ThemeTokens) -> str:
    if t.dark:
        bg, fg, hov = "#455a64", "#e6e6e6", "#546e7a"
    else:
        bg, fg, hov = "#90a4ae", "#222222", "#78909c"
    return (
        f"QPushButton {{ background-color: {bg}; color: {fg}; font-size: 11px; padding: 4px 10px; }} "
        f"QPushButton:hover {{ background-color: {hov}; }}"
    )


def main_stylesheet(scale: float = 1.0, dark: bool = True) -> str:
    """Global QSS for main windows. Optional scale (from window resize) adjusts fonts and padding."""
    s = max(0.75, min(1.25, float(scale)))

    def px(n: float) -> int:
        return max(1, int(round(n * s)))

    if dark:
        win, pane_b, tab_bg, tab_tx, tab_bd, tab_hov = "#1e1e23", "#1e1e23", "#2d2d34", "#e6e6e6", "#3a3a42", "#35353c"
        btn_bg, btn_hov, btn_pr, btn_dis_bg, btn_dis_tx = "#2d2d34", "#3a3a42", "#25252c", "#25252c", "#808080"
        inp_bg, inp_tx, inp_bd = "#25252c", "#e6e6e6", "#3a3a42"
        foot_bg, foot_top = "#25252c", "#3a3a42"
        menubar_sel, menu_bg, menu_sel = "#3a3a42", "#2d2d34", "#3a3a42"
    else:
        win, pane_b, tab_bg, tab_tx, tab_bd, tab_hov = "#f0f0f0", "#f0f0f0", "#e4e4e4", "#222222", "#c0c0c0", "#d8d8d8"
        btn_bg, btn_hov, btn_pr, btn_dis_bg, btn_dis_tx = "#e8e8e8", "#d0d0d0", "#c8c8c8", "#e0e0e0", "#888888"
        inp_bg, inp_tx, inp_bd = "#ffffff", "#222222", "#b0b0b0"
        foot_bg, foot_top = "#e8e8e8", "#c0c0c0"
        menubar_sel, menu_bg, menu_sel = "#d0d0d0", "#f5f5f5", "#d8d8d8"

    return (
        f"""
    QMainWindow {{ background-color: {win}; }}
    QTabWidget::pane {{ border: 1px solid {tab_bd}; background-color: {pane_b}; margin: 0; padding: 0; top: 0; }}
    QTabBar::tab {{
        background-color: {tab_bg};
        color: {tab_tx};
        font-size: {px(13)}px;
        font-weight: normal;
        padding: {px(5)}px {px(18)}px;
        margin-right: {px(3)}px;
        margin-left: 1px;
        min-height: {px(24)}px;
        min-width: {px(64)}px;
        border: 1px solid {tab_bd};
        border-bottom: none;
        border-top-left-radius: {px(4)}px;
        border-top-right-radius: {px(4)}px;
    }}
    QTabBar::tab:selected {{
        background-color: {COLOR_BLUE};
        color: #ffffff;
        font-weight: normal;
        border-color: {COLOR_BLUE};
    }}
    QTabBar::tab:hover:!selected {{ background-color: {tab_hov}; }}
    QPushButton {{ background-color: {btn_bg}; color: {tab_tx}; border: 1px solid {tab_bd}; padding: {px(6)}px {px(14)}px; }}
    QPushButton:hover {{ background-color: {btn_hov}; }}
    QPushButton:pressed {{ background-color: {btn_pr}; }}
    QPushButton:disabled {{ background-color: {btn_dis_bg}; color: {btn_dis_tx}; }}
    QPushButton#btn_run {{ background-color: {COLOR_GREEN}; color: white; font-weight: bold; }}
    QPushButton#btn_run:hover {{ background-color: {COLOR_GREEN_HOVER}; }}
    QPushButton#btn_stop {{ background-color: {COLOR_RED}; color: white; font-weight: bold; }}
    QPushButton#btn_stop:hover {{ background-color: {COLOR_RED_HOVER}; }}
    QPushButton#btn_clear {{ background-color: {COLOR_ORANGE}; color: white; }}
    QPushButton#btn_clear:hover {{ background-color: {COLOR_ORANGE_HOVER}; }}
    QPushButton#btn_start_new {{ background-color: {COLOR_ORANGE}; color: white; font-weight: bold; }}
    QPushButton#btn_start_new:hover {{ background-color: {COLOR_ORANGE_HOVER}; }}
    QPushButton#btn_align {{ background-color: {COLOR_ORANGE}; color: white; font-weight: bold; font-size: {px(14)}px; padding: {px(10)}px {px(24)}px; }}
    QPushButton#btn_align:hover {{ background-color: {COLOR_ORANGE_HOVER}; }}
    QPushButton#btn_primary {{ background-color: {COLOR_BLUE}; color: white; }}
    QPushButton#btn_primary:hover {{ background-color: {COLOR_BLUE_HOVER}; }}
    QLineEdit, QComboBox {{ background-color: {inp_bg}; color: {inp_tx}; border: 1px solid {inp_bd}; padding: {px(4)}px; }}
    """
        + _main_spinbox_qss(px, dark)
        + f"""
    QFrame#footer {{ background-color: {foot_bg}; border-top: 1px solid {foot_top}; }}
    QMenuBar {{ background-color: {win}; color: {tab_tx}; }}
    QMenuBar::item:selected {{ background-color: {menubar_sel}; }}
    QMenu {{ background-color: {menu_bg}; color: {tab_tx}; }}
    QMenu::item:selected {{ background-color: {menu_sel}; }}
    """
    )


def qpushbutton_local_style(background: str, hover: str, *, bold: bool = True, dark: bool = True) -> str:
    """Set on a QPushButton via setStyleSheet() so fill/hover survive parent QGroupBox styles (propagation can hide global QSS)."""
    fw = "font-weight: bold;" if bold else ""
    bd = "#3a3a42" if dark else "#b0b0b0"
    dis_bg, dis_tx = ("#25252c", "#808080") if dark else ("#e0e0e0", "#888888")
    return (
        f"QPushButton {{ background-color: {background}; color: white; {fw} border: 1px solid {bd}; padding: 6px 14px; }}"
        f"QPushButton:hover {{ background-color: {hover}; }}"
        f"QPushButton:pressed {{ background-color: {hover}; }}"
        f"QPushButton:disabled {{ background-color: {dis_bg}; color: {dis_tx}; }}"
    )


def qpushbutton_local_style_neutral(*, dark: bool = True) -> str:
    """Grey default-style button (e.g. New Recipe in Start box)."""
    if dark:
        return (
            "QPushButton { background-color: #2d2d34; color: #e6e6e6; border: 1px solid #3a3a42; padding: 6px 14px; }"
            "QPushButton:hover { background-color: #3a3a42; }"
            "QPushButton:pressed { background-color: #25252c; }"
            "QPushButton:disabled { background-color: #25252c; color: #808080; }"
        )
    return (
        "QPushButton { background-color: #e8e8e8; color: #222222; border: 1px solid #b0b0b0; padding: 6px 14px; }"
        "QPushButton:hover { background-color: #d8d8d8; }"
        "QPushButton:pressed { background-color: #c8c8c8; }"
        "QPushButton:disabled { background-color: #e0e0e0; color: #888888; }"
    )


def scaled_px(n: float, scale: float = 1.0) -> int:
    """Scale a nominal pixel size by UI scale (e.g. window resize factor). Used by MainWindow._sp."""
    try:
        return max(1, int(round(float(n) * float(scale))))
    except (TypeError, ValueError):
        return max(1, int(round(float(n))))


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
