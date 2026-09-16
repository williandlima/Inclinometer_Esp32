"""Mostrador analógico (ponteiro em arco, estilo velocímetro) da posição
atual de um eixo, complementando o valor digital exibido ao lado — pedido
como "indicação analógica de posição, além dos valores lidos", e depois
como o elemento a que a tela deveria dar mais ênfase visual.

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

from PyQt5.QtCore import QPointF, QRectF, QSize, Qt
from PyQt5.QtGui import QColor, QConicalGradient, QFont, QPainter, QPainterPath, QPen, QPolygonF
from PyQt5.QtWidgets import QSizePolicy, QWidget

# Mesma paleta de ui/main_window.py, repetida aqui para este widget não
# depender daquele módulo (evita import circular) — os dois arquivos devem
# ser mantidos em sincronia se a paleta um dia mudar.
_FACE_COLOR = QColor("#0D2557")  # mesmo tom "afundado" das caixas de valor
_TRACK_COLOR = QColor("#28417A")  # arco "trilho" (faixa completa min->max)
_RIM_COLOR = QColor("#3A5C9C")
_ORANGE = QColor("#F5821F")
_ORANGE_DARK = QColor("#C25E0E")
_TEXT_LIGHT = QColor("#F4F6F9")
_TEXT_MUTED = QColor("#9AA5B1")

# Geometria dos rótulos/marcações — usados tanto para desenhar quanto para
# calcular, em paintEvent, o maior raio que ainda deixa espaço para eles
# (ver o comentário lá) sem cortar nada nas bordas do widget.
_OUTER_FACTOR = 1.08  # marcação maior e "sobra" da pena do trilho, além do raio nominal
_LABEL_GAP = 12
_SIDE_LABEL_W = 46
_TOP_LABEL_H = 16


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
        # Altura fixa (generosa, bem maior que a versão anterior) e largura
        # elástica: cresce com a largura do cartão sem virar um retângulo
        # esquisito com o mostrador pequeno lá embaixo numa janela muito alta.
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(250)

    def setValue(self, value: float | None) -> None:
        if value == self._value:
            return
        self._value = value
        self.update()

    def sizeHint(self) -> QSize:  # noqa: N802 - override Qt
        return QSize(320, 250)

    def _value_to_angle_deg(self, value: float) -> float:
        span = self._maximum - self._minimum
        fraction = 0.0 if span == 0 else (value - self._minimum) / span
        fraction = min(1.0, max(0.0, fraction))
        return 180.0 - fraction * 180.0  # min->180° (esquerda), max->0° (direita)

    def paintEvent(self, event) -> None:  # noqa: N802 - override Qt
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()

        # O raio precisa deixar espaço não só para o arco em si, mas para os
        # rótulos de mínimo/máximo (dos lados) e de zero (por cima) — e para
        # o cubo do ponteiro (por baixo do centro). `_OUTER_FACTOR` cobre a
        # marcação maior e a "sobra" da pena do trilho, que vão um pouco além
        # do raio nominal. Sem essas reservas, em janelas menores os rótulos
        # das pontas saem cortados (aconteceu numa versão anterior).
        side_allowance = _LABEL_GAP + _SIDE_LABEL_W + 6
        top_allowance = _LABEL_GAP + _TOP_LABEL_H + 6
        bottom_allowance = 26

        max_radius_w = (w / 2.0 - side_allowance) / _OUTER_FACTOR
        max_radius_h = (h - top_allowance - bottom_allowance) / _OUTER_FACTOR
        radius = max(24.0, min(max_radius_w, max_radius_h))

        cx = w / 2.0
        cy = top_allowance + radius * _OUTER_FACTOR

        rect = QRectF(cx - radius, cy - radius, radius * 2, radius * 2)

        self._draw_face(painter, cx, cy, radius)
        self._draw_track(painter, rect, radius)
        if self._value is not None:
            self._draw_progress_arc(painter, rect, radius, self._value)
        self._draw_ticks(painter, cx, cy, radius)
        self._draw_labels(painter, cx, cy, radius)
        if self._value is not None:
            angle_deg = self._value_to_angle_deg(self._value)
            self._draw_needle(painter, cx, cy, radius, angle_deg)
        else:
            self._draw_hub(painter, cx, cy, radius)

    def _draw_face(self, painter: QPainter, cx: float, cy: float, radius: float) -> None:
        # Fundo "afundado" atrás do trilho — dá ao mostrador uma cara própria
        # de instrumento (mesmo tom das caixas de valor), em vez de o arco
        # flutuar solto sobre a cor de fundo do cartão.
        face_r = radius * (_OUTER_FACTOR + 0.03)
        path = QPainterPath()
        path.moveTo(cx - face_r, cy)
        path.arcTo(QRectF(cx - face_r, cy - face_r, face_r * 2, face_r * 2), 180, -180)
        path.closeSubpath()
        painter.setPen(Qt.NoPen)
        painter.setBrush(_FACE_COLOR)
        painter.drawPath(path)
        painter.setPen(QPen(_RIM_COLOR, 1.5))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)

    def _draw_track(self, painter: QPainter, rect: QRectF, radius: float) -> None:
        track_pen = QPen(_TRACK_COLOR, max(6.0, radius * 0.14))
        track_pen.setCapStyle(Qt.RoundCap)
        painter.setPen(track_pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawArc(rect, 0 * 16, 180 * 16)

    def _draw_progress_arc(self, painter: QPainter, rect: QRectF, radius: float, value: float) -> None:
        # Arco colorido do zero calibrado até o valor atual — em vez de só
        # a marca de ponteiro, mostra de cara "quanto e para que lado" o
        # eixo se afastou da referência, reforçando a leitura analógica.
        zero_angle = self._value_to_angle_deg((self._minimum + self._maximum) / 2.0)
        value_angle = self._value_to_angle_deg(value)
        gradient = QConicalGradient(rect.center(), 0)
        gradient.setColorAt(0.0, _ORANGE_DARK)
        gradient.setColorAt(0.5, _ORANGE)
        gradient.setColorAt(1.0, _ORANGE_DARK)
        pen = QPen(gradient, max(6.0, radius * 0.14))
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawArc(rect, int(zero_angle * 16), int((value_angle - zero_angle) * 16))

    def _draw_ticks(self, painter: QPainter, cx: float, cy: float, radius: float) -> None:
        # Marcas maiores (e mais claras) no mínimo/zero/máximo — as três
        # referências que têm rótulo; marcas menores nos quartos, só para
        # dar noção de escala entre elas.
        for tick_deg in (180, 0, 90):
            self._draw_tick(painter, cx, cy, radius, tick_deg, major=True)
        for tick_deg in (135, 45):
            self._draw_tick(painter, cx, cy, radius, tick_deg, major=False)

    def _draw_tick(self, painter: QPainter, cx: float, cy: float, radius: float, angle_deg: float, major: bool) -> None:
        angle_rad = math.radians(angle_deg)
        outer_r = radius * _OUTER_FACTOR
        inner_r = radius * (0.92 if major else 0.97)
        outer = QPointF(cx + outer_r * math.cos(angle_rad), cy - outer_r * math.sin(angle_rad))
        inner = QPointF(cx + inner_r * math.cos(angle_rad), cy - inner_r * math.sin(angle_rad))
        pen = QPen(_TEXT_LIGHT if major else _TEXT_MUTED, 2.4 if major else 1.4)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawLine(inner, outer)

    def _draw_labels(self, painter: QPainter, cx: float, cy: float, radius: float) -> None:
        painter.setFont(QFont("Sans Serif", 10, QFont.DemiBold))
        painter.setPen(_TEXT_MUTED)
        self._draw_label(painter, cx, cy, radius, 180, f"{self._minimum:g}°", "left")
        self._draw_label(painter, cx, cy, radius, 0, f"{self._maximum:g}°", "right")
        self._draw_label(painter, cx, cy, radius, 90, "0°", "top")

    def _draw_label(self, painter: QPainter, cx: float, cy: float, radius: float, angle_deg: float, text: str, side: str) -> None:
        # Fica além da ponta da marcação maior e do alcance do ponteiro —
        # sem isso, um valor perto do centro da faixa cobre o rótulo "0°"
        # com a própria agulha (aconteceu numa versão anterior deste
        # widget). As mesmas constantes (`_OUTER_FACTOR`/`_LABEL_GAP`/
        # `_SIDE_LABEL_W`/`_TOP_LABEL_H`) usadas aqui também reservam espaço
        # para isso no cálculo do raio em `paintEvent` — mudar um lado sem
        # o outro volta a cortar rótulo em janelas pequenas.
        angle_rad = math.radians(angle_deg)
        label_r = radius * _OUTER_FACTOR + _LABEL_GAP
        x = cx + label_r * math.cos(angle_rad)
        y = cy - label_r * math.sin(angle_rad)
        box_w, box_h = (_SIDE_LABEL_W, 18) if side in ("left", "right") else (50, _TOP_LABEL_H)
        if side == "left":  # mínimo (180°): texto termina no ponto, crescendo para a esquerda
            box = QRectF(x - box_w, y - box_h / 2, box_w, box_h)
        elif side == "right":  # máximo (0°): texto começa no ponto, crescendo para a direita
            box = QRectF(x, y - box_h / 2, box_w, box_h)
        else:  # "top": zero (90°), centrado e inteiramente acima do ponto
            box = QRectF(x - box_w / 2, y - box_h, box_w, box_h)
        painter.drawText(box, Qt.AlignCenter, text)

    def _draw_needle(self, painter: QPainter, cx: float, cy: float, radius: float, angle_deg: float) -> None:
        # Agulha afunilada (triângulo estreito), não uma linha reta — lê
        # como um instrumento de precisão, não como um traço de rascunho.
        angle_rad = math.radians(angle_deg)
        length = radius * 0.86
        base_half_w = max(3.0, radius * 0.045)

        tip = QPointF(cx + length * math.cos(angle_rad), cy - length * math.sin(angle_rad))
        perp = angle_rad + math.pi / 2
        base_a = QPointF(cx + base_half_w * math.cos(perp), cy - base_half_w * math.sin(perp))
        base_b = QPointF(cx - base_half_w * math.cos(perp), cy + base_half_w * math.sin(perp))
        needle = QPolygonF([tip, base_a, base_b])

        # Sombra por baixo, levemente deslocada — dá profundidade sem
        # precisar de QGraphicsDropShadowEffect (não se aplica bem dentro de
        # um único paintEvent com várias formas).
        shadow_offset = QPointF(radius * 0.02, radius * 0.03)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(0, 0, 0, 90))
        painter.drawPolygon(needle.translated(shadow_offset))

        painter.setPen(QPen(_ORANGE_DARK, 1))
        painter.setBrush(_ORANGE)
        painter.drawPolygon(needle)

        self._draw_hub(painter, cx, cy, radius)

    def _draw_hub(self, painter: QPainter, cx: float, cy: float, radius: float) -> None:
        # Cubo do ponteiro em dois anéis (laranja fora, navy dentro) mais um
        # brilho pequeno — o mesmo truque visual de um mostrador automotivo,
        # em vez de um círculo plano de uma cor só.
        center = QPointF(cx, cy)
        outer_r = max(7.0, radius * 0.13)
        painter.setPen(Qt.NoPen)
        painter.setBrush(_ORANGE)
        painter.drawEllipse(center, outer_r, outer_r)
        painter.setBrush(_FACE_COLOR)
        painter.drawEllipse(center, outer_r * 0.6, outer_r * 0.6)
        painter.setBrush(QColor(255, 255, 255, 60))
        painter.drawEllipse(QPointF(cx - outer_r * 0.18, cy - outer_r * 0.22), outer_r * 0.22, outer_r * 0.22)
