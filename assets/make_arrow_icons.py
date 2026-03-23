"""Generate white up/down arrow PNGs for spinbox styling. Run once: python assets/make_arrow_icons.py"""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from PyQt5.QtGui import QImage, QPainter, QColor, QPolygon
from PyQt5.QtCore import QPoint

def main():
    d = os.path.dirname(__file__)
    size = 14
    for name, points in [
        ("arrow_up", [QPoint(size//2, 0), QPoint(0, size), QPoint(size, size)]),
        ("arrow_down", [QPoint(0, 0), QPoint(size, 0), QPoint(size//2, size)]),
    ]:
        img = QImage(size + 2, size + 2, QImage.Format_ARGB32)
        img.fill(0)
        p = QPainter(img)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(QColor(255, 255, 255))
        p.setBrush(QColor(255, 255, 255))
        poly = QPolygon([QPoint(pt.x() + 1, pt.y() + 1) for pt in points])
        p.drawPolygon(poly)
        p.end()
        path = os.path.join(d, name + ".png")
        img.save(path)
        print("Saved", path)

if __name__ == "__main__":
    main()
