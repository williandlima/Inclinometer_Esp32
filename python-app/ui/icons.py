"""Ícones desenhados com QPainter — nada de emoji (renderiza como emoji
colorido, inconsistente entre sistemas, ver o histórico do botão de
Configurações) nem de arquivo externo. Cada função devolve um `QIcon` de
uma cor só."""
from __future__ import annotations

import math

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF


def _new_pixmap(size: int) -> tuple[QPixmap, QPainter]:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    return pixmap, painter


def _point_on_circle(cx: float, cy: float, r: float, angle_deg: float) -> QPointF:
    a = math.radians(angle_deg)
    return QPointF(cx + r * math.cos(a), cy - r * math.sin(a))


def _arrowhead(tip: QPointF, dir_x: float, dir_y: float, head_len: float) -> QPolygonF:
    back = QPointF(tip.x() - head_len * dir_x, tip.y() - head_len * dir_y)
    perp_x, perp_y = -dir_y, dir_x
    half_w = head_len * 0.62
    p2 = QPointF(back.x() + half_w * perp_x, back.y() + half_w * perp_y)
    p3 = QPointF(back.x() - half_w * perp_x, back.y() - half_w * perp_y)
    return QPolygonF([tip, p2, p3])


def _arc_arrowhead(cx: float, cy: float, r: float, end_angle_deg: float, clockwise_screen: bool, head_len: float) -> QPolygonF:
    eps = 3.0
    step = -eps if clockwise_screen else eps
    tip = _point_on_circle(cx, cy, r, end_angle_deg)
    before = _point_on_circle(cx, cy, r, end_angle_deg - step)
    dx, dy = tip.x() - before.x(), tip.y() - before.y()
    norm = math.hypot(dx, dy) or 1.0
    return _arrowhead(tip, dx / norm, dy / norm, head_len)


def gear_icon(color: str, size: int = 22) -> QIcon:
    pixmap, painter = _new_pixmap(size)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(color))

    center = QPointF(size / 2, size / 2)
    outer_r = size * 0.46
    inner_r = size * 0.30
    tooth_w = size * 0.16
    tooth_len = outer_r - inner_r + size * 0.04
    teeth = 8

    for i in range(teeth):
        painter.save()
        painter.translate(center)
        painter.rotate(360.0 / teeth * i)
        painter.drawRoundedRect(QRectF(-tooth_w / 2, -outer_r, tooth_w, tooth_len), 1.0, 1.0)
        painter.restore()

    painter.drawEllipse(center, inner_r, inner_r)
    painter.setCompositionMode(QPainter.CompositionMode_Clear)
    painter.drawEllipse(center, size * 0.13, size * 0.13)
    painter.end()
    return QIcon(pixmap)


def tilt_icon(color: str, size: int = 20) -> QIcon:
    pixmap, painter = _new_pixmap(size)
    pen_color = QColor(color)

    painter.setPen(Qt.NoPen)
    painter.setBrush(pen_color)
    painter.drawRoundedRect(QRectF(size * 0.06, size * 0.80, size * 0.88, size * 0.09), 1.5, 1.5)

    angle_deg = -38
    angle_rad = math.radians(angle_deg)
    dir_x, dir_y = math.cos(angle_rad), math.sin(angle_rad)
    origin = QPointF(size * 0.22, size * 0.80)
    length = size * 0.60
    tip = QPointF(origin.x() + length * dir_x, origin.y() + length * dir_y)

    pen = QPen(pen_color, size * 0.10)
    pen.setCapStyle(Qt.RoundCap)
    painter.setPen(pen)
    painter.drawLine(origin, tip)

    painter.setPen(Qt.NoPen)
    painter.setBrush(pen_color)
    painter.drawPolygon(_arrowhead(tip, dir_x, dir_y, size * 0.24))
    painter.end()
    return QIcon(pixmap)


def pan_icon(color: str, size: int = 20) -> QIcon:
    pixmap, painter = _new_pixmap(size)
    pen_color = QColor(color)
    cx, cy, r = size / 2, size / 2, size * 0.36
    start_deg, span_deg = 15, 260

    pen = QPen(pen_color, size * 0.10)
    pen.setCapStyle(Qt.RoundCap)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    painter.drawArc(QRectF(cx - r, cy - r, r * 2, r * 2), int(start_deg * 16), int(span_deg * 16))

    painter.setPen(Qt.NoPen)
    painter.setBrush(pen_color)
    painter.drawPolygon(_arc_arrowhead(cx, cy, r, start_deg + span_deg, clockwise_screen=False, head_len=size * 0.22))
    painter.end()
    return QIcon(pixmap)


def play_icon(color: str, size: int = 20) -> QIcon:
    pixmap, painter = _new_pixmap(size)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(color))
    m = size * 0.22
    painter.drawPolygon(QPolygonF([QPointF(m, size * 0.16), QPointF(m, size * 0.84), QPointF(size - m, size * 0.5)]))
    painter.end()
    return QIcon(pixmap)


def stop_icon(color: str, size: int = 20) -> QIcon:
    pixmap, painter = _new_pixmap(size)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor(color))
    m = size * 0.24
    painter.drawRoundedRect(QRectF(m, m, size - 2 * m, size - 2 * m), 2.0, 2.0)
    painter.end()
    return QIcon(pixmap)


def target_icon(color: str, size: int = 20) -> QIcon:
    pixmap, painter = _new_pixmap(size)
    pen_color = QColor(color)
    pen = QPen(pen_color, size * 0.09)
    pen.setCapStyle(Qt.RoundCap)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    center = QPointF(size / 2, size / 2)
    painter.drawEllipse(center, size * 0.34, size * 0.34)
    painter.drawEllipse(center, size * 0.13, size * 0.13)
    for dx, dy in ((0, -1), (0, 1), (-1, 0), (1, 0)):
        inner = QPointF(center.x() + dx * size * 0.40, center.y() + dy * size * 0.40)
        outer = QPointF(center.x() + dx * size * 0.48, center.y() + dy * size * 0.48)
        painter.drawLine(inner, outer)
    painter.end()
    return QIcon(pixmap)


def reset_icon(color: str, size: int = 20) -> QIcon:
    pixmap, painter = _new_pixmap(size)
    pen_color = QColor(color)
    cx, cy, r = size / 2, size / 2, size * 0.34
    start_deg, span_deg = 50, 260

    pen = QPen(pen_color, size * 0.11)
    pen.setCapStyle(Qt.RoundCap)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    painter.drawArc(QRectF(cx - r, cy - r, r * 2, r * 2), int(start_deg * 16), int(span_deg * 16))

    painter.setPen(Qt.NoPen)
    painter.setBrush(pen_color)
    painter.drawPolygon(_arc_arrowhead(cx, cy, r, start_deg + span_deg, clockwise_screen=False, head_len=size * 0.20))
    painter.end()
    return QIcon(pixmap)


def vibration_icon(color: str, size: int = 20) -> QIcon:
    pixmap, painter = _new_pixmap(size)
    pen = QPen(QColor(color), size * 0.10)
    pen.setCapStyle(Qt.RoundCap)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    path = QPainterPath()
    path.moveTo(size * 0.05, size * 0.5)
    path.cubicTo(size * 0.22, size * 0.10, size * 0.28, size * 0.10, size * 0.40, size * 0.5)
    path.cubicTo(size * 0.52, size * 0.90, size * 0.58, size * 0.90, size * 0.70, size * 0.5)
    path.cubicTo(size * 0.78, size * 0.22, size * 0.85, size * 0.22, size * 0.95, size * 0.5)
    painter.drawPath(path)
    painter.end()
    return QIcon(pixmap)


def report_icon(color: str, size: int = 20) -> QIcon:
    pixmap, painter = _new_pixmap(size)
    pen_color = QColor(color)
    path = QPainterPath()
    m_x, m_y = size * 0.24, size * 0.10
    w, h = size * 0.52, size * 0.80
    fold = size * 0.16
    path.moveTo(m_x, m_y)
    path.lineTo(m_x + w - fold, m_y)
    path.lineTo(m_x + w, m_y + fold)
    path.lineTo(m_x + w, m_y + h)
    path.lineTo(m_x, m_y + h)
    path.closeSubpath()

    pen = QPen(pen_color, size * 0.07)
    pen.setJoinStyle(Qt.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.NoBrush)
    painter.drawPath(path)

    line_pen = QPen(pen_color, size * 0.06)
    line_pen.setCapStyle(Qt.RoundCap)
    painter.setPen(line_pen)
    for i in range(3):
        y = m_y + h * 0.42 + i * size * 0.14
        painter.drawLine(QPointF(m_x + size * 0.10, y), QPointF(m_x + w - size * 0.08, y))
    painter.end()
    return QIcon(pixmap)
