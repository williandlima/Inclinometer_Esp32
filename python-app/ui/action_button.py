"""Botão de ação com ícone + título + legenda — usado na barra inferior.
Um `QPushButton`/`QToolButton` comum não separa um título em destaque de
uma legenda discreta abaixo dele (são a mesma fonte/cor); este widget é um
`QFrame` clicável (emite seu próprio `clicked`) com um layout de verdade
dentro — ícone num selo circular, título em negrito, legenda pequena e
discreta — no nível de acabamento das referências que motivaram este
redesenho, sem depender de nenhuma lib de terceiros."""
from __future__ import annotations

from PyQt5.QtCore import QSize, Qt, pyqtSignal
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QFrame, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout


class ActionButton(QFrame):
    clicked = pyqtSignal()

    def __init__(
        self,
        title: str,
        subtitle: str,
        icon: QIcon,
        bg_color: str,
        text_color: str,
        hover_color: str | None = None,
        pressed_color: str | None = None,
        subtitle_color: str | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(64)
        self._enabled_visual = True

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 16, 8)
        layout.setSpacing(12)

        # Selo circular atrás do ícone — o mesmo truque do cubo do
        # ponteiro/mostrador: duas camadas em vez de um ícone solto no ar.
        self._icon_badge = QLabel()
        self._icon_badge.setFixedSize(36, 36)
        self._icon_badge.setAlignment(Qt.AlignCenter)
        self._icon_badge.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(self._icon_badge)

        text_column = QVBoxLayout()
        text_column.setSpacing(1)
        self._title_label = QLabel()
        self._title_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self._subtitle_label = QLabel()
        self._subtitle_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        text_column.addWidget(self._title_label)
        text_column.addWidget(self._subtitle_label)
        layout.addLayout(text_column)
        layout.addStretch(1)

        self.set_content(title, subtitle, icon)
        self.set_colors(bg_color, text_color, hover_color, pressed_color, subtitle_color)

    def set_content(self, title: str, subtitle: str, icon: QIcon) -> None:
        self._title_label.setText(title)
        self._subtitle_full_text = subtitle
        self._icon_badge.setPixmap(icon.pixmap(QSize(19, 19)))
        self._update_subtitle_elision()

    def _update_subtitle_elision(self) -> None:
        # Sem isso, um subtítulo mais longo do que a largura do botão (numa
        # janela redimensionada bem estreita) simplesmente cortava no meio
        # da palavra, sem "..." — aconteceu ao testar o tamanho mínimo da
        # janela. `elidedText` recalcula a cada redimensionamento
        # (`resizeEvent`), então continua correto se a janela mudar de
        # tamanho depois.
        text = getattr(self, "_subtitle_full_text", "")
        width = self._subtitle_label.width()
        if not text or width <= 0:
            return
        metrics = self._subtitle_label.fontMetrics()
        self._subtitle_label.setText(metrics.elidedText(text, Qt.ElideRight, width))

    def resizeEvent(self, event) -> None:  # noqa: N802 - override Qt
        super().resizeEvent(event)
        self._update_subtitle_elision()

    def set_colors(
        self,
        bg_color: str,
        text_color: str,
        hover_color: str | None = None,
        pressed_color: str | None = None,
        subtitle_color: str | None = None,
    ) -> None:
        self._bg_color = bg_color
        self._hover_color = hover_color or bg_color
        self._pressed_color = pressed_color or bg_color
        self._text_color = text_color
        self._subtitle_color = subtitle_color or text_color
        self._apply_background(self._bg_color)
        self._icon_badge.setStyleSheet("background-color: rgba(255, 255, 255, 45); border-radius: 18px; border: none;")
        self._title_label.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {text_color}; background: transparent; border: none;")
        self._subtitle_label.setStyleSheet(f"font-size: 11px; color: {self._subtitle_color}; background: transparent; border: none;")

    def _apply_background(self, color: str) -> None:
        self.setStyleSheet(f"QFrame {{ background-color: {color}; border-radius: 12px; border: none; }}")

    def setEnabled(self, enabled: bool) -> None:  # noqa: N802 - override Qt
        super().setEnabled(enabled)
        self._enabled_visual = enabled
        if enabled:
            self._apply_background(self._bg_color)
            self._title_label.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {self._text_color}; background: transparent; border: none;")
        else:
            self._apply_background("#4d5566")
            self._title_label.setStyleSheet("font-size: 14px; font-weight: bold; color: #b7bdc7; background: transparent; border: none;")

    def enterEvent(self, event) -> None:  # noqa: N802 - override Qt
        if self._enabled_visual:
            self._apply_background(self._hover_color)
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802 - override Qt
        if self._enabled_visual:
            self._apply_background(self._bg_color)
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802 - override Qt
        if self._enabled_visual and event.button() == Qt.LeftButton:
            self._apply_background(self._pressed_color)
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802 - override Qt
        if self._enabled_visual and event.button() == Qt.LeftButton:
            self._apply_background(self._hover_color if self.rect().contains(event.pos()) else self._bg_color)
            if self.rect().contains(event.pos()):
                self.clicked.emit()
        super().mouseReleaseEvent(event)
