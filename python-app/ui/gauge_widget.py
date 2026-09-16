"""Mostrador analógico (ponteiro em arco, estilo velocímetro) da posição
atual de um eixo, complementando o valor digital exibido ao lado — pedido
como "indicação analógica de posição, além dos valores lidos".

Desenhado com QPainter em vez de widgets prontos: um `QDial`/`QProgressBar`
do Qt não tem o formato de meia-lua com ponteiro que se espera de um
inclinômetro analógico, e um SVG fixo não escalaria com o cartão nem se
adaptaria à faixa de cada eixo (tilt: -60°~+60°; pan: -90°~+90°).

Convenção de ângulos usada aqui (a mesma do `QPainter.drawArc`): 0° aponta
para a direita (3h), 90° para cima (12h), 180° para a esquerda (9h). O
`mínimo` do eixo fica em 180°, o `máximo` em 0°, e o meio (que para os dois
eixos deste projeto é o zero calibrado, já que as faixas são simétricas) em
90°, apontando para cima — o mesmo desenho de um velocímetro."""
from __future__ import annotations

import math

from PyQt5.QtCore import QPointF, QRectF, Qt
from PyQt5.QtGui import QColor, QFont, QPainter, QPen
from PyQt5.QtWidgets import QSizePolicy, QWidget

# Mesma paleta de ui/main_window.py, repetida aqui para este widget não
# depender daquele módulo (evita import circular) — os dois arquivos devem
# ser mantidos em sincronia se a paleta um dia mudar.
_NAVY_PANEL = QColor("#15305F")
_TRACK_COLOR = QColor("#2A4A85")  # arco "trilho", mais claro que o painel
_ORANGE = QColor("#F5821F")
_TEXT_LIGHT = QColor("#F4F6F9")
_TEXT_MUTED = QColor("#9AA5B1")


class AngleGauge(QWidget):
    """Meia-lua com ponteiro indicando `value` dentro de [minimum, maximum].
    `value=None` desenha só o mostrador vazio (mesmo caso de um eixo sem
    dado, ex: firmware antigo sem azimute — o rótulo de aviso ao lado já
    explica o motivo, o mostrador só evita fingir uma leitura de 0°)."""

    def __init__(self, minimum: float, maximum: float, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._minimum = minimum
        self._maximum = maximum
        self._value: float | None = None
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(150)

    def setValue(self, value: float | None) -> None:
        if value == self._value:
            return
        self._value = value
        self.update()

    def sizeHint(self):  # noqa: N802 - override Qt
        from PyQt5.QtCore import QSize

        return QSize(240, 150)

    def _value_to_angle_deg(self, value: float) -> float:
        span = self._maximum - self._minimum
        fraction = 0.0 if span == 0 else (value - self._minimum) / span
        fraction = min(1.0, max(0.0, fraction))
        return 180.0 - fraction * 180.0  # min->180° (esquerda), max->0° (direita)

    def paintEvent(self, event) -> None:  # noqa: N802 - override Qt
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        margin = 14
        # A meia-lua ocupa uma caixa 2:1 (largura = 2x raio); soma-se uma
        # margem embaixo para caber os rótulos de mínimo/máximo/zero.
        radius = min((w - 2 * margin) / 2.0, h - margin - 22)
        radius = max(radius, 20.0)
        cx = w / 2.0
        cy = margin + radius

        rect = QRectF(cx - radius, cy - radius, radius * 2, radius * 2)

        # Trilho de fundo (a meia-lua completa, min->max).
        track_pen = QPen(_TRACK_COLOR, max(4.0, radius * 0.09))
        track_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(track_pen)
        painter.drawArc(rect, 0 * 16, 180 * 16)

        # Marcas: mínimo (180°), 1/4 e 3/4 (135°/45°, sem rótulo), zero/meio
        # (90°) e máximo (0°) — o zero é a posição calibrada, o ponto de
        # referência mais importante do mostrador.
        painter.setPen(QPen(_TEXT_MUTED, 2))
        for tick_deg in (180, 135, 90, 45, 0):
            self._draw_tick(painter, cx, cy, radius, tick_deg)

        painter.setFont(QFont("Sans Serif", 9))
        painter.setPen(_TEXT_MUTED)
        self._draw_label(painter, cx, cy, radius, 180, f"{self._minimum:g}°", "left")
        self._draw_label(painter, cx, cy, radius, 0, f"{self._maximum:g}°", "right")
        self._draw_label(painter, cx, cy, radius, 90, "0°", "top")

        if self._value is not None:
            angle_deg = self._value_to_angle_deg(self._value)
            self._draw_needle(painter, cx, cy, radius, angle_deg)

    def _draw_tick(self, painter: QPainter, cx: float, cy: float, radius: float, angle_deg: float) -> None:
        angle_rad = math.radians(angle_deg)
        outer = QPointF(cx + radius * math.cos(angle_rad), cy - radius * math.sin(angle_rad))
        inner_r = radius * 0.86
        inner = QPointF(cx + inner_r * math.cos(angle_rad), cy - inner_r * math.sin(angle_rad))
        painter.drawLine(inner, outer)

    def _draw_label(self, painter: QPainter, cx: float, cy: float, radius: float, angle_deg: float, text: str, side: str) -> None:
        # Fica logo depois da ponta da marcação (que vai até `radius`), fora
        # do alcance do ponteiro (que para em 0.78*radius) — sem isso, um
        # valor perto do centro da faixa cobre o rótulo "0°" com a própria
        # agulha (aconteceu na primeira versão deste widget).
        angle_rad = math.radians(angle_deg)
        label_r = radius + 12
        x = cx + label_r * math.cos(angle_rad)
        y = cy - label_r * math.sin(angle_rad)
        box_w, box_h = 46, 16
        if side == "left":  # mínimo (180°): texto termina no ponto, crescendo para a esquerda
            box = QRectF(x - box_w, y - box_h / 2, box_w, box_h)
        elif side == "right":  # máximo (0°): texto começa no ponto, crescendo para a direita
            box = QRectF(x, y - box_h / 2, box_w, box_h)
        else:  # "top": zero (90°), centrado e inteiramente acima do ponto
            box = QRectF(x - box_w / 2, y - box_h, box_w, box_h)
        painter.drawText(box, Qt.AlignCenter, text)

    def _draw_needle(self, painter: QPainter, cx: float, cy: float, radius: float, angle_deg: float) -> None:
        angle_rad = math.radians(angle_deg)
        length = radius * 0.78
        tip = QPointF(cx + length * math.cos(angle_rad), cy - length * math.sin(angle_rad))

        pen = QPen(_ORANGE, max(3.0, radius * 0.07))
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawLine(QPointF(cx, cy), tip)

        # Cubo do ponteiro: navy com borda laranja, mesma linguagem visual
        # dos cartões/caixas do resto da janela.
        hub_r = max(5.0, radius * 0.11)
        painter.setPen(QPen(_ORANGE, 2))
        painter.setBrush(_NAVY_PANEL)
        painter.drawEllipse(QPointF(cx, cy), hub_r, hub_r)
