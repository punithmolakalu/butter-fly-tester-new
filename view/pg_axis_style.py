"""
Shared PyQtGraph axis typography: tick values and axis labels use the same QFont as a
standard PlotWidget (pyqtgraph default when AxisItem.style['tickFont'] is None).
"""
from __future__ import annotations

from typing import Any, Optional, Sequence

from PyQt5.QtGui import QFont
from PyQt5.QtWidgets import QApplication


def _base_axis_font(plot_widget: Optional[Any]) -> QFont:
    if plot_widget is not None:
        try:
            return QFont(plot_widget.font())
        except Exception:
            pass
    app = QApplication.instance()
    if app is not None:
        try:
            return QFont(app.font())
        except Exception:
            pass
    return QFont()


def apply_standard_pg_axis_fonts(
    plot_item: Any,
    *,
    plot_widget: Optional[Any] = None,
    extra_axis_items: Sequence[Any] = (),
) -> None:
    """
    Apply one tick font and one label font to every AxisItem on the plot, plus any
    extra right-axis items not registered in plot_item.axes (e.g. third Y scale).

    Call after axis setLabel/setPen so labels exist and colors are set.
    """
    tick_font = _base_axis_font(plot_widget)
    label_font = QFont(tick_font)
    seen: set[int] = set()

    def _style_one(ax: Any) -> None:
        if ax is None:
            return
        aid = id(ax)
        if aid in seen:
            return
        seen.add(aid)
        try:
            ax.setTickFont(tick_font)
        except Exception:
            pass
        try:
            ax.label.setFont(label_font)
        except Exception:
            pass

    axes = getattr(plot_item, "axes", None)
    if isinstance(axes, dict):
        for _name, info in axes.items():
            if isinstance(info, dict):
                item = info.get("item")
                if item is not None:
                    _style_one(item)
    for ax in extra_axis_items:
        _style_one(ax)
