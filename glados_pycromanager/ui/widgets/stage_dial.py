"""`StageDial`: an XY stage jog control drawn as three rings by four directions.

Clicking a ring segment asks for a move in that direction: the inner ring is the
smallest step (size 1), the outer ring the largest (size 3). The widget only
emits `stepRequested(dx, dy, size)` -- the caller decides how far a step is --
and shows the stage position in its centre (`setText`, like a QLabel).

Colours come from the widget's palette, which the dock stylesheet sets, so the
dial follows napari's light/dark theme like the buttons around it.
"""
from __future__ import annotations

import math

from PyQt5.QtCore import QPointF, QRectF, QSize, Qt, pyqtSignal
from PyQt5.QtGui import QColor, QPainter, QPainterPath, QPalette, QPolygonF
from PyQt5.QtWidgets import QSizePolicy, QToolTip, QWidget

#: Number of step sizes, inner to outer.
RINGS = 3
RING_NAMES = ("inner", "middle", "outer")
#: (name, dx, dy, angle in degrees counter-clockwise from +x) per direction.
DIRECTIONS = (("right", 1, 0, 0), ("up", 0, 1, 90), ("left", -1, 0, 180), ("down", 0, -1, 270))


def _blend(a: QColor, b: QColor, t: float) -> QColor:
    """`a` moved a fraction `t` of the way to `b`."""
    return QColor(round(a.red() + (b.red() - a.red()) * t),
                  round(a.green() + (b.green() - a.green()) * t),
                  round(a.blue() + (b.blue() - a.blue()) * t))


class StageDial(QWidget):
    #: dx, dy in {-1, 0, 1} (up is +y), size in 1..RINGS (1 = inner ring)
    stepRequested = pyqtSignal(int, int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._text = ""
        self._hover = None  # (direction index, ring) under the mouse
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)

    # -- QLabel-like readout -------------------------------------------------
    def setText(self, text: str) -> None:
        self._text = str(text)
        self.update()

    def text(self) -> str:
        return self._text

    # -- geometry ------------------------------------------------------------
    def _ring_width(self) -> float:
        return max(16.0, self.fontMetrics().height() * 1.25)

    def _hub_radius(self) -> float:
        fm = self.fontMetrics()
        return max(fm.horizontalAdvance("-00000.0") / 2 + 4, fm.height() * 1.2)

    def sizeHint(self) -> QSize:
        d = math.ceil(2 * (self._hub_radius() + RINGS * self._ring_width()) + 4)
        return QSize(d, d)

    minimumSizeHint = sizeHint

    def segment_at(self, pos: QPointF):
        """(direction index, ring 1..RINGS) under `pos`, or None (hub/outside)."""
        c = QPointF(self.width() / 2, self.height() / 2)
        dx, dy = pos.x() - c.x(), c.y() - pos.y()
        r = math.hypot(dx, dy)
        hub, ring_w = self._hub_radius(), self._ring_width()
        if r <= hub or r > hub + RINGS * ring_w:
            return None
        ring = min(RINGS, int((r - hub) // ring_w) + 1)
        angle = math.degrees(math.atan2(dy, dx)) % 360
        direction = int(((angle + 45) % 360) // 90)  # 0 right, 1 up, 2 left, 3 down
        return direction, ring

    def segment_center(self, direction: int, ring: int) -> QPointF:
        """Widget coordinates of the middle of one segment (tests, tooltips)."""
        c = QPointF(self.width() / 2, self.height() / 2)
        r = self._hub_radius() + (ring - 0.5) * self._ring_width()
        a = math.radians(DIRECTIONS[direction][3])
        return QPointF(c.x() + r * math.cos(a), c.y() - r * math.sin(a))

    # -- events --------------------------------------------------------------
    def mouseMoveEvent(self, event):
        hover = self.segment_at(QPointF(event.pos()))
        if hover != self._hover:
            self._hover = hover
            if hover is not None:
                name = DIRECTIONS[hover[0]][0]
                QToolTip.showText(event.globalPos(), f"Move {name} by the {RING_NAMES[hover[1] - 1]}-ring step", self)
            else:
                QToolTip.hideText()
            self.update()

    def leaveEvent(self, event):
        self._hover = None
        self.update()
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.LeftButton:
            return
        hit = self.segment_at(QPointF(event.pos()))
        if hit is not None:
            _name, dx, dy, _angle = DIRECTIONS[hit[0]]
            self.stepRequested.emit(dx, dy, hit[1])

    # -- painting ------------------------------------------------------------
    def paintEvent(self, _event):
        # Window/WindowText are what a dock stylesheet's `QWidget { background;
        # color }` reliably sets; Button/Base can keep Qt's light defaults under
        # napari's dark theme, so every fill is a blend of those two.
        pal = self.palette()
        window = pal.color(QPalette.Window)
        text = pal.color(QPalette.WindowText)
        hover = pal.color(QPalette.Highlight)
        button = _blend(window, text, 0.22)
        hub_fill = _blend(window, text, 0.06)

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = QPointF(self.width() / 2, self.height() / 2)
        hub, ring_w = self._hub_radius(), self._ring_width()
        gap = 1.5

        for d_index, (_name, _dx, _dy, angle) in enumerate(DIRECTIONS):
            for ring in range(1, RINGS + 1):
                r0, r1 = hub + (ring - 1) * ring_w + gap, hub + ring * ring_w - gap
                # Inner rings slightly lighter than the outer ones, like the mockup.
                fill = _blend(button, text, 0.07 * (RINGS - ring))
                if self._hover == (d_index, ring):
                    fill = _blend(button, hover, 0.65)
                p.setPen(Qt.NoPen)
                p.setBrush(fill)
                p.drawPath(self._segment_path(c, r0, r1, angle - 45 + 1.2, angle + 45 - 1.2))
                self._draw_arrow(p, c, (r0 + r1) / 2, angle, 3 + ring, text)

        p.setBrush(hub_fill)
        p.setPen(_blend(window, text, 0.25))
        p.drawEllipse(c, hub - 1, hub - 1)
        p.setPen(text)
        p.drawText(QRectF(c.x() - hub, c.y() - hub, 2 * hub, 2 * hub), Qt.AlignCenter, self._text)
        p.end()

    @staticmethod
    def _segment_path(c, r0, r1, a0, a1) -> QPainterPath:
        path = QPainterPath()
        path.arcMoveTo(QRectF(c.x() - r1, c.y() - r1, 2 * r1, 2 * r1), a0)
        path.arcTo(QRectF(c.x() - r1, c.y() - r1, 2 * r1, 2 * r1), a0, a1 - a0)
        path.arcTo(QRectF(c.x() - r0, c.y() - r0, 2 * r0, 2 * r0), a1, a0 - a1)
        path.closeSubpath()
        return path

    @staticmethod
    def _draw_arrow(p, c, r, angle, size, color):
        a = math.radians(angle)
        ux, uy = math.cos(a), -math.sin(a)          # outward, screen coordinates
        tip = QPointF(c.x() + (r + size) * ux, c.y() + (r + size) * uy)
        base = QPointF(c.x() + (r - size) * ux, c.y() + (r - size) * uy)
        perp = QPointF(-uy * size, ux * size)
        p.setPen(Qt.NoPen)
        p.setBrush(color)
        p.drawPolygon(QPolygonF([tip, base + perp, base - perp]))
