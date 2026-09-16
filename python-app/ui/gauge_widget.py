"""Mostrador analógico (ponteiro em arco, estilo instrumento de aviação) da
posição atual de um eixo, complementando o valor digital exibido ao lado.

Referência visual: instrumentos de bordo clássicos (indicador de
velocidade/atitude) — mostrador escuro, aro claro e graduação numerada, em
vez de um ícone plano. A cor de aviso perto das pontas (o mesmo papel do
arco vermelho de "não exceder" de um instrumento real, adaptado ao que este
projeto de fato sabe: os limites configurados em `data_source/base.py` —
`ANGLE_MIN_DEG`/`MAX_DEG`, `PAN_MIN_DEG`/`MAX_DEG`, não uma zona de
segurança validada por ensaio) é discreta e dentro da própria paleta da
marca (o mesmo laranja escurecido usado no cubo do ponteiro) — nada de
verde/âmbar/vermelho de semáforo cobrindo o mostrador inteiro.

Desenhado com QPainter em vez de widgets prontos: um `QDial`/`QProgressBar`
do Qt não tem o formato de meia-lua com ponteiro nem faixas coloridas por
zona, e um SVG fixo não escalaria com o cartão nem se adaptaria à faixa de
cada eixo (tilt: -60°~+60°; pan: -90°~+90°).

Convenção de ângulos usada aqui (a mesma do `QPainter.drawArc`): 0° aponta
para a direita (3h), 90° para cima (12h), 180° para a esquerda (9h). O
`mínimo` do eixo fica em 180°, o `máximo` em 0°, e o meio (que para os dois
eixos deste projeto é o zero calibrado, já que as faixas são simétricas) em
90°, apontando para cima."""
from __future__ import annotations

import math

from PyQt5.QtCore import QPointF, QRectF, QSize, Qt
from PyQt5.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPolygonF, QRadialGradient
from PyQt5.QtWidgets import QSizePolicy, QWidget

# Mesma paleta de ui/main_window.py, repetida aqui para este widget não
# depender daquele módulo (evita import circular) — os arquivos devem ser
# mantidos em sincronia se a paleta um dia mudar.
_FACE_COLOR_CENTER = QColor("#123163")
_FACE_COLOR_EDGE = QColor("#081B3D")
_BEZEL_COLOR = QColor("#AEB9CC")  # aro claro, acabamento "instrumento"
_ORANGE = QColor("#F5821F")
_ORANGE_DARK = QColor("#C25E0E")
_TEXT_LIGHT = QColor("#F4F6F9")
_TEXT_MUTED = QColor("#9AA5B1")

# Faixa de aviso perto de cada ponta — só essa, discreta e dentro da mesma
# paleta azul/laranja do resto do app (ver docstring do módulo). Nada de
# verde/âmbar: uma terceira e quarta cor só deixaria o mostrador com cara
# de painel de brinquedo, não de instrumento.
_TRACK_COLOR = QColor("#28417A")   # a maior parte do arco (faixa normal)
_WARN_COLOR = QColor("#8A3B2A")    # laranja bem escurecido/dessaturado, só na ponta
_ZONE_WARN_FRACTION = 0.12          # últimos 12% da faixa, de cada lado

# Geometria dos rótulos/marcações — usados tanto para desenhar quanto para
# calcular, em paintEvent, o maior raio que ainda deixa espaço para eles
# (ver o comentário lá) sem cortar nada nas bordas do widget.
_OUTER_FACTOR = 1.08  # marcação maior e "sobra" da pena do arco, além do raio nominal
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
        # Altura fixa (generosa — este é o elemento a que a tela deve dar
        # mais ênfase) e largura elástica: cresce com a largura do cartão
        # sem virar um retângulo esquisito numa janela muito alta.
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(300)

    def setValue(self, value: float | None) -> None:
        if value == self._value:
            return
        self._value = value
        self.update()

    def sizeHint(self) -> QSize:  # noqa: N802 - override Qt
        return QSize(360, 300)

    def _value_to_angle_deg(self, value: float) -> float:
        span = self._maximum - self._minimum
        fraction = 0.0 if span == 0 else (value - self._minimum) / span
        fraction = min(1.0, max(0.0, fraction))
        return 180.0 - fraction * 180.0  # min->180° (esquerda), max->0° (direita)

    def _fraction_to_angle_deg(self, fraction: float) -> float:
        return 180.0 - fraction * 180.0

    def paintEvent(self, event) -> None:  # noqa: N802 - override Qt
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()

        # O raio precisa deixar espaço não só para o arco em si, mas para os
        # rótulos de mínimo/máximo (dos lados) e de zero (por cima) — e para
        # o cubo do ponteiro (por baixo do centro). `_OUTER_FACTOR` cobre a
        # marcação maior e a "sobra" da pena do arco, que vão um pouco além
        # do raio nominal. Sem essas reservas, em janelas menores os rótulos
        # das pontas saem cortados (aconteceu numa versão anterior).
        side_allowance = _LABEL_GAP + _SIDE_LABEL_W + 6
        top_allowance = _LABEL_GAP + _TOP_LABEL_H + 6
        bottom_allowance = 30

        max_radius_w = (w / 2.0 - side_allowance) / _OUTER_FACTOR
        max_radius_h = (h - top_allowance - bottom_allowance) / _OUTER_FACTOR
        radius = max(24.0, min(max_radius_w, max_radius_h))

        cx = w / 2.0
        cy = top_allowance + radius * _OUTER_FACTOR

        rect = QRectF(cx - radius, cy - radius, radius * 2, radius * 2)

        self._draw_face(painter, cx, cy, radius)
        self._draw_zones(painter, rect, radius)
        self._draw_ticks(painter, cx, cy, radius)
        self._draw_labels(painter, cx, cy, radius)
        if self._value is not None:
            angle_deg = self._value_to_angle_deg(self._value)
            self._draw_needle(painter, cx, cy, radius, angle_deg)
        else:
            self._draw_hub(painter, cx, cy, radius)

    def _draw_face(self, painter: QPainter, cx: float, cy: float, radius: float) -> None:
        # Mostrador escuro com um leve gradiente radial (dá uma sugestão de
        # profundidade/vidro, em vez de uma cor chapada) e um aro claro —
        # a combinação "cara escura + aro claro" é o que lê como instrumento
        # de painel, e não como um ícone plano qualquer.
        face_r = radius * (_OUTER_FACTOR + 0.05)
        path = QPainterPath()
        path.moveTo(cx - face_r, cy)
        path.arcTo(QRectF(cx - face_r, cy - face_r, face_r * 2, face_r * 2), 180, -180)
        path.closeSubpath()

        gradient = QRadialGradient(QPointF(cx, cy - face_r * 0.15), face_r * 1.3)
        gradient.setColorAt(0.0, _FACE_COLOR_CENTER)
        gradient.setColorAt(1.0, _FACE_COLOR_EDGE)
        painter.setPen(Qt.NoPen)
        painter.setBrush(gradient)
        painter.drawPath(path)

        painter.setPen(QPen(_BEZEL_COLOR, 2.0))
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)

    def _draw_zones(self, painter: QPainter, rect: QRectF, radius: float) -> None:
        # Arco em três trechos — a faixa normal (a grande maioria do arco)
        # e um tom de aviso discreto só na pontinha de cada lado. Ver a
        # ressalva sobre o significado dessa cor no cabeçalho do módulo.
        bounds = [0.0, _ZONE_WARN_FRACTION, 1.0 - _ZONE_WARN_FRACTION, 1.0]
        colors = [_WARN_COLOR, _TRACK_COLOR, _WARN_COLOR]
        pen = QPen()
        pen.setWidthF(max(7.0, radius * 0.14))
        pen.setCapStyle(Qt.FlatCap)
        for i, color in enumerate(colors):
            start_angle = self._fraction_to_angle_deg(bounds[i])
            end_angle = self._fraction_to_angle_deg(bounds[i + 1])
            pen.setColor(color)
            painter.setPen(pen)
            painter.drawArc(rect, int(start_angle * 16), int((end_angle - start_angle) * 16))

    def _draw_ticks(self, painter: QPainter, cx: float, cy: float, radius: float) -> None:
        # Marcas maiores (e mais claras) no mínimo/quarto/zero/quarto/máximo
        # — as cinco referências com número — e menores nos oitavos, só
        # para dar noção de escala fina entre elas (visual de instrumento
        # de bordo, com muitas graduações).
        for tick_deg in (180, 135, 90, 45, 0):
            self._draw_tick(painter, cx, cy, radius, tick_deg, major=True)
        for tick_deg in (157.5, 112.5, 67.5, 22.5):
            self._draw_tick(painter, cx, cy, radius, tick_deg, major=False)

    def _draw_tick(self, painter: QPainter, cx: float, cy: float, radius: float, angle_deg: float, major: bool) -> None:
        angle_rad = math.radians(angle_deg)
        outer_r = radius * _OUTER_FACTOR
        inner_r = radius * (0.90 if major else 0.96)
        outer = QPointF(cx + outer_r * math.cos(angle_rad), cy - outer_r * math.sin(angle_rad))
        inner = QPointF(cx + inner_r * math.cos(angle_rad), cy - inner_r * math.sin(angle_rad))
        pen = QPen(_TEXT_LIGHT if major else _TEXT_MUTED, 2.6 if major else 1.4)
        pen.setCapStyle(Qt.RoundCap)
        painter.setPen(pen)
        painter.drawLine(inner, outer)

    def _draw_labels(self, painter: QPainter, cx: float, cy: float, radius: float) -> None:
        mid = (self._minimum + self._maximum) / 2.0
        quarter = (self._maximum - self._minimum) / 4.0
        painter.setFont(QFont("Sans Serif", 10, QFont.DemiBold))
        painter.setPen(_TEXT_MUTED)
        self._draw_label(painter, cx, cy, radius, 180, f"{self._minimum:g}°", "left")
        self._draw_label(painter, cx, cy, radius, 0, f"{self._maximum:g}°", "right")
        self._draw_label(painter, cx, cy, radius, 135, f"{mid - quarter:g}°", "center")
        self._draw_label(painter, cx, cy, radius, 45, f"{mid + quarter:g}°", "center")
        painter.setPen(_TEXT_LIGHT)
        self._draw_label(painter, cx, cy, radius, 90, "0°", "top")

    def _draw_label(self, painter: QPainter, cx: float, cy: float, radius: float, angle_deg: float, text: str, side: str) -> None:
        # Fica além da ponta da marcação maior e do alcance do ponteiro —
        # sem isso, um valor perto do centro da faixa cobre o rótulo "0°"
        # com a própria agulha (aconteceu numa versão anterior deste
        # widget). As mesmas constantes (`_OUTER_FACTOR`/`_LABEL_GAP`/
        # `_SIDE_LABEL_W`/`_TOP_LABEL_H`) usadas aqui também reservam espaço
        # para isso no cálculo do raio em `paintEvent` — mudar um lado sem
        # o outro volta a cortar rótulo em janelas pequenas. Os rótulos
        # "center" (nos quartos, em diagonal) cabem com folga dentro dessa
        # mesma reserva, por ficarem sempre mais próximos do centro do que
        # os de topo/lado.
        angle_rad = math.radians(angle_deg)
        label_r = radius * _OUTER_FACTOR + _LABEL_GAP
        x = cx + label_r * math.cos(angle_rad)
        y = cy - label_r * math.sin(angle_rad)
        if side == "left":  # mínimo (180°): texto termina no ponto, crescendo para a esquerda
            box_w, box_h = _SIDE_LABEL_W, 18
            box = QRectF(x - box_w, y - box_h / 2, box_w, box_h)
        elif side == "right":  # máximo (0°): texto começa no ponto, crescendo para a direita
            box_w, box_h = _SIDE_LABEL_W, 18
            box = QRectF(x, y - box_h / 2, box_w, box_h)
        elif side == "top":  # zero (90°): centrado e inteiramente acima do ponto
            box_w, box_h = 50, _TOP_LABEL_H
            box = QRectF(x - box_w / 2, y - box_h, box_w, box_h)
        else:  # "center": rótulos dos quartos (45°/135°), centrados no ponto
            box_w, box_h = 44, 16
            box = QRectF(x - box_w / 2, y - box_h / 2, box_w, box_h)
        painter.drawText(box, Qt.AlignCenter, text)

    def _draw_needle(self, painter: QPainter, cx: float, cy: float, radius: float, angle_deg: float) -> None:
        # Agulha afunilada (triângulo estreito), não uma linha reta — lê
        # como um instrumento de precisão, não como um traço de rascunho.
        angle_rad = math.radians(angle_deg)
        length = radius * 0.84
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

        painter.setPen(QPen(QColor(255, 255, 255, 160), 1))
        painter.setBrush(_TEXT_LIGHT)
        painter.drawPolygon(needle)

        self._draw_hub(painter, cx, cy, radius)

    def _draw_hub(self, painter: QPainter, cx: float, cy: float, radius: float) -> None:
        # Cubo do ponteiro em dois anéis (laranja fora, escuro dentro) mais
        # um brilho pequeno — o mesmo truque visual de um mostrador
        # automotivo/de bordo, em vez de um círculo plano de uma cor só.
        center = QPointF(cx, cy)
        outer_r = max(7.0, radius * 0.13)
        painter.setPen(QPen(_ORANGE_DARK, 1.5))
        painter.setBrush(_ORANGE)
        painter.drawEllipse(center, outer_r, outer_r)
        painter.setPen(Qt.NoPen)
        painter.setBrush(_FACE_COLOR_EDGE)
        painter.drawEllipse(center, outer_r * 0.55, outer_r * 0.55)
        painter.setBrush(QColor(255, 255, 255, 70))
        painter.drawEllipse(QPointF(cx - outer_r * 0.18, cy - outer_r * 0.22), outer_r * 0.22, outer_r * 0.22)
