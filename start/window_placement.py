"""Move windows to a specific screen (e.g. secondary monitor)."""
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QGuiApplication


def get_screen_not_containing(widget):
    """
    Return a QScreen that does NOT contain the given widget (e.g. the "other" monitor).
    If the widget is on screen 0, returns screen 1 (or any other); if on screen 1, returns screen 0.
    Returns None if only one screen exists.
    """
    screens = QGuiApplication.screens()
    if len(screens) < 2:
        return None
    win = widget.window() if hasattr(widget, "window") else widget
    try:
        # Center of window in global (virtual desktop) coordinates
        center = win.mapToGlobal(win.rect().center())
    except Exception:
        center = None
    for screen in screens:
        geom = screen.geometry()
        if center is not None and geom.contains(center):
            # This screen has the widget; return another screen
            for other in screens:
                if other != screen:
                    return other
            return None
    # Widget not on any screen (e.g. not shown yet) or center unknown: return non-primary (index 1) if exists
    return screens[1] if len(screens) > 1 else None


def get_secondary_screen(reference_window=None):
    """
    Return the screen where we should open the "other" window.
    - If reference_window is given and has a screen, return a screen that does NOT contain it.
    - Otherwise return screens[1] if multiple screens, else screens[0].
    """
    screens = QGuiApplication.screens()
    if len(screens) < 2:
        return screens[0] if screens else None
    if reference_window is not None:
        other = get_screen_not_containing(reference_window)
        if other is not None:
            return other
    return screens[1]


def move_to_screen(window, screen, maximize=False):
    """Move the window to the given screen. If maximize is False, use a capped size; if True, maximize on that screen."""
    if screen is None:
        return
    geom = screen.availableGeometry()
    # Set screen on the window handle when available (important on Windows)
    if hasattr(window, "windowHandle") and window.windowHandle() is not None:
        try:
            window.windowHandle().setScreen(screen)
        except Exception:
            pass
    window.move(geom.x(), geom.y())
    if maximize:
        window.showMaximized()
    else:
        window.resize(min(geom.width(), 1200), min(geom.height(), 800))


def place_on_secondary_screen_before_show(window, reference_window=None, maximize=False):
    """
    Put the window on the secondary monitor **before** the first show() so it does not
    briefly appear on the primary display. Same geometry as move_to_secondary_screen.

    Use this for LIV / PER / Spectrum / Recipe / Alignment / Temperature Stability floating windows.
    After show(), optional: call move_to_secondary_screen again if the platform nudges the window.
    """
    screen = get_secondary_screen(reference_window)
    if screen is None:
        return
    geom = screen.availableGeometry()
    if maximize:
        window.setGeometry(geom)
    else:
        w = min(geom.width(), 1200)
        h = min(geom.height(), 800)
        window.resize(w, h)
        window.move(geom.x(), geom.y())


def move_to_secondary_screen(window, reference_window=None, maximize=False):
    """
    Move the given window to a monitor that is NOT the one containing reference_window.
    If reference_window is None, use the secondary monitor (screens[1]) when multiple screens exist.

    Prefer place_on_secondary_screen_before_show() + show() to avoid a flash on the primary monitor.
    If maximize is True, show the window maximized on that screen (taskbar excluded via availableGeometry).
    """
    screen = get_secondary_screen(reference_window)
    if screen is None:
        return
    move_to_screen(window, screen, maximize=maximize)
