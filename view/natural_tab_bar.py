"""QTabBar subclass: tabs use natural width from label text (use with setExpanding(False))."""
from PyQt5.QtCore import QSize
from PyQt5.QtGui import QFont, QFontMetrics
from PyQt5.QtWidgets import QApplication, QTabBar


def _tab_bar_font_metrics_for_style(tab_bar: QTabBar) -> QFontMetrics:
    """
    Match view.dark_theme main_stylesheet: QTabBar::tab font-size is px(13) scaled by ui_scale.
    Default fontMetrics() uses the app font (different size) and underestimates width → clipped text.
    """
    s = 1.0
    app = QApplication.instance()
    if app is not None:
        v = app.property("ui_scale")
        if v is not None:
            try:
                s = float(v)
            except (TypeError, ValueError):
                s = 1.0
    s = max(0.75, min(1.25, s))
    font_px = max(9, int(round(13 * s)))
    f = QFont(tab_bar.font())
    f.setPixelSize(font_px)
    return QFontMetrics(f)


class NaturalWidthTabBar(QTabBar):
    """Tab bar where each tab sizes to its text instead of stretching to fill the bar."""

    def tabSizeHint(self, index: int) -> QSize:
        hint = super().tabSizeHint(index)
        text = self.tabText(index)
        if not text:
            return hint
        fm = _tab_bar_font_metrics_for_style(self)
        tw = fm.horizontalAdvance(text) if hasattr(fm, "horizontalAdvance") else fm.width(text)
        try:
            tw = max(int(tw), int(fm.boundingRect(text).width()))
        except Exception:
            pass
        # QSS: padding left+right ~px(18–22) each + 1px borders + margin-right — keep margin so labels never clip
        horizontal_extra = 64
        w = max(hint.width(), tw + horizontal_extra)
        # Slightly shorter tabs: tight vertical fit to font + QSS padding (see dark_theme QTabBar::tab)
        h = max(hint.height(), fm.height() + 8)
        return QSize(w, h)

    def minimumSizeHint(self):
        # Wide enough for all tabs in a row when not scrolling (parent may still scroll)
        sz = super().minimumSizeHint()
        total = 0
        for i in range(self.count()):
            total += self.tabSizeHint(i).width()
        if total > 0:
            return QSize(total, sz.height())
        return sz
