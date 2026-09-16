"""Esquema simplificado do pan-tilt, entre os dois mostradores — mostra a
posição atual (tilt/pan) junto de um desenho do equipamento, em vez de só
os dois números lado a lado. Ideia sintetizada de uma referência de
"visão do produto" que o usuário trouxe, adaptada ao que o app de fato
mede: os traços das setas de tilt/pan são fixos (ilustram os dois eixos de
movimento, não a inclinação real desenhada em 3D — isso exigiria um motor
gráfico bem mais pesado só pra decoração), e só os números ao lado são
dados em tempo real."""
from __future__ import annotations

import math

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QColor, QFont, QLinearGradient, QPainter, QPainterPath, QPen, QPolygonF
from PyQt5.QtWidgets import QSizePolicy, QWidget

_BODY_COLOR = QColor("#C9CED6")
_BODY_SHADE = QColor("#8B95A8")
_BASE_COLOR = QColor("#5B6577")
_LENS_COLOR = QColor("#0D2557")
_ORANGE = QColor("#F5821F")
_TEXT_LIGHT = QColor("#F4F6F9")
_TEXT_MUTED = QColor("#9AA5B1")


class EquipmentSchematic(QWidget):
    """Desenho estático do pan-tilt com os valores atuais de tilt/pan
    anotados ao lado — `setValues(tilt_deg, pan_deg)`, `None` para
    "sem dado" (mesmo critério do resto da tela)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tilt: float | None = None
        self._pan: float | None = None
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(300)
        self.setMinimumWidth(180)

    def setValues(self, tilt_deg: float | None, pan_deg: float | None) -> None:
        if tilt_deg == self._tilt and pan_deg == self._pan:
            return
        self._tilt, self._pan = tilt_deg, pan_deg
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802 - override Qt
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        cx = w / 2.0
        # Unidade de escala do desenho, calibrada para caber com folga no
        # espaço disponível (largura estreita entre os dois mostradores).
        unit = min(w / 2.2, h / 6.0)

        base_y = h * 0.86
        self._draw_base(painter, cx, base_y, unit)
        self._draw_pan_arrow(painter, cx, base_y, unit)
        head_cy = base_y - unit * 2.0
        self._draw_post(painter, cx, base_y, head_cy, unit)
        self._draw_head(painter, cx, head_cy, unit)
        self._draw_tilt_arrow(painter, cx, head_cy, unit)
        self._draw_readout(painter, w, h)

    def _draw_base(self, painter: QPainter, cx: float, base_y: float, unit: float) -> None:
        path = QPainterPath()
        w_top, w_bottom = unit * 1.5, unit * 2.0
        h_base = unit * 0.55
        path.moveTo(cx - w_top / 2, base_y - h_base)
        path.lineTo(cx + w_top / 2, base_y - h_base)
        path.lineTo(cx + w_bottom / 2, base_y)
        path.lineTo(cx - w_bottom / 2, base_y)
        path.closeSubpath()
        gradient = QLinearGradient(cx, base_y - h_base, cx, base_y)
        gradient.setColorAt(0.0, _BODY_SHADE)
        gradient.setColorAt(1.0, _BASE_COLOR)
        painter.setPen(QPen(_BASE_COLOR, 1.5))
        painter.setBrush(gradient)
        painter.drawPath(path)

    def _draw_post(self, painter: QPainter, cx: float, base_y: float, head_cy: float, unit: float) -> None:
        post_w = unit * 0.32
        top = head_cy + unit * 0.15
        bottom = base_y - unit * 0.55
        painter.setPen(Qt.NoPen)
        painter.setBrush(_BODY_SHADE)
        painter.drawRoundedRect(QRectF(cx - post_w / 2, top, post_w, bottom - top), 2.0, 2.0)

    def _draw_head(self, painter: QPainter, cx: float, cy: float, unit: float) -> None:
        # Corpo do sensor: cápsula horizontal com uma "lente" na ponta —
        # lê como uma câmera/sensor num suporte pan-tilt, sem precisar de
        # nenhum recurso gráfico 3D.
        body_w, body_h = unit * 1.7, unit * 0.85
        body_rect = QRectF(cx - body_w / 2, cy - body_h / 2, body_w, body_h)
        gradient = QLinearGradient(body_rect.topLeft(), body_rect.bottomLeft())
        gradient.setColorAt(0.0, _BODY_COLOR)
        gradient.setColorAt(1.0, _BODY_SHADE)
        painter.setPen(QPen(_BASE_COLOR, 1.5))
        painter.setBrush(gradient)
        painter.drawRoundedRect(body_rect, body_h * 0.4, body_h * 0.4)

        lens_r = body_h * 0.42
        lens_c = QPointF(cx + body_w / 2 - lens_r * 1.1, cy)
        painter.setPen(QPen(_ORANGE, 2.0))
        painter.setBrush(_LENS_COLOR)
        painter.drawEllipse(lens_c, lens_r, lens_r)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 70))
        painter.drawEllipse(QPointF(lens_c.x() - lens_r * 0.25, lens_c.y() - lens_r * 0.3), lens_r * 0.3, lens_r * 0.3)

    def _draw_tilt_arrow(self, painter: QPainter, cx: float, head_cy: float, unit: float) -> None:
        pen = QPen(_ORANGE, unit * 0.09)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        rect = QRectF(cx - unit * 1.05, head_cy - unit * 1.05, unit * 2.1, unit * 2.1)
        painter.drawArc(rect, 35 * 16, 110 * 16)
        # Setas nas duas pontas (rotação nos dois sentidos).
        for angle_deg, sweep_positive in ((35, False), (145, True)):
            tip_r = unit * 1.05
            a = math.radians(angle_deg)
            tip = QPointF(cx + tip_r * math.cos(a), head_cy - tip_r * math.sin(a))
            tangent_a = math.radians(angle_deg + (2 if sweep_positive else -2))
            near = QPointF(cx + tip_r * math.cos(tangent_a), head_cy - tip_r * math.sin(tangent_a))
            dx, dy = tip.x() - near.x(), tip.y() - near.y()
            norm = (dx * dx + dy * dy) ** 0.5 or 1.0
            dx, dy = dx / norm, dy / norm
            head_len = unit * 0.28
            back = QPointF(tip.x() - head_len * dx, tip.y() - head_len * dy)
            perp = (-dy, dx)
            half_w = head_len * 0.6
            poly = QPolygonF([
                tip,
                QPointF(back.x() + half_w * perp[0], back.y() + half_w * perp[1]),
                QPointF(back.x() - half_w * perp[0], back.y() - half_w * perp[1]),
            ])
            painter.setPen(Qt.NoPen)
            painter.setBrush(_ORANGE)
            painter.drawPolygon(poly)

    def _draw_pan_arrow(self, painter: QPainter, cx: float, base_y: float, unit: float) -> None:
        pen = QPen(_ORANGE, unit * 0.08)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        rect = QRectF(cx - unit * 1.15, base_y - unit * 0.42, unit * 2.3, unit * 0.85)
        painter.drawArc(rect, 200 * 16, 140 * 16)

    def _draw_readout(self, painter: QPainter, w: float, h: float) -> None:
        painter.setFont(QFont("Sans Serif", 9, QFont.DemiBold))
        tilt_text = "--.--°" if self._tilt is None else f"{self._tilt:.2f}°"
        pan_text = "--.--°" if self._pan is None else f"{self._pan:.2f}°"

        painter.setPen(_TEXT_MUTED)
        painter.drawText(QRectF(0, h * 0.06, w, 16), Qt.AlignCenter, "TILT")
        painter.setPen(_TEXT_LIGHT)
        painter.drawText(QRectF(0, h * 0.06 + 14, w, 20), Qt.AlignCenter, tilt_text)

        painter.setPen(_TEXT_MUTED)
        painter.drawText(QRectF(0, h * 0.92, w, 16), Qt.AlignCenter, "PAN")
        painter.setPen(_TEXT_LIGHT)
        painter.drawText(QRectF(0, h * 0.92 - 18, w, 20), Qt.AlignCenter, pan_text)
