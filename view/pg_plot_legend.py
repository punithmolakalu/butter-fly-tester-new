"""PyQtGraph: four legend slots anchored below the plot (LIV / Spectrum / PER / stability result plots)."""
from __future__ import annotations

from typing import Any, List

import pyqtgraph as pg


def install_quad_legends_below_axis(plot_item: Any, labelTextColor: str = "#333333") -> List[Any]:
    """
    Create four LegendItem instances parented to the plot ViewBox, spaced horizontally.
    Call slots[i].addItem(curve_or_item, "Label") for each series.
    """
    vb = plot_item.vb
    slots: List[Any] = []
    kw: dict = {"frame": False}
    try:
        leg0 = pg.LegendItem(offset=(8, 18), labelTextColor=labelTextColor, **kw)
    except TypeError:
        leg0 = pg.LegendItem(offset=(8, 18), **kw)
        try:
            leg0.setLabelTextColor(labelTextColor)
        except Exception:
            pass

    for i in range(4):
        if i == 0:
            leg = leg0
        else:
            try:
                leg = pg.LegendItem(offset=(8 + i * 92, 18), labelTextColor=labelTextColor, **kw)
            except TypeError:
                leg = pg.LegendItem(offset=(8 + i * 92, 18), **kw)
                try:
                    leg.setLabelTextColor(labelTextColor)
                except Exception:
                    pass
        leg.setParentItem(vb)
        try:
            leg.anchor(itemPos=(0, 1), parentPos=(0, 1), offset=(8 + i * 92, -6))
        except Exception:
            pass
        slots.append(leg)

    try:
        setattr(plot_item, "_legend_slots", slots)
    except Exception:
        pass
    return slots
