"""Botão de ação com ícone — usado na barra inferior. Um `QPushButton`
comum não posiciona ícone+texto com o respiro visual das referências que
motivaram este redesenho; este widget é um `QToolButton` configurado para
isso (ícone acima do texto), com um método de conveniência para trocar
cor/ícone/texto num só lugar (usado pelo botão Iniciar/Parar, que alterna
os dois junto com o estado da leitura)."""
from __future__ import annotations

from PyQt5.QtCore import QSize, Qt
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QSizePolicy, QToolButton


class ActionButton(QToolButton):
    def __init__(
        self,
        text: str,
        icon: QIcon,
        bg_color: str,
        text_color: str,
        hover_color: str | None = None,
        pressed_color: str | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
        self.setIconSize(QSize(22, 22))
        self.setMinimumHeight(58)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setCursor(Qt.PointingHandCursor)
        self.set_content(text, icon)
        self.set_colors(bg_color, text_color, hover_color, pressed_color)

    def set_content(self, text: str, icon: QIcon) -> None:
        self.setText(text)
        self.setIcon(icon)

    def set_colors(self, bg_color: str, text_color: str, hover_color: str | None = None, pressed_color: str | None = None) -> None:
        hover_color = hover_color or bg_color
        pressed_color = pressed_color or bg_color
        self.setStyleSheet(f"""
            QToolButton {{
                background-color: {bg_color};
                color: {text_color};
                border: none;
                border-radius: 10px;
                padding: 6px 10px;
                font-weight: bold;
                font-size: 13px;
            }}
            QToolButton:hover {{ background-color: {hover_color}; }}
            QToolButton:pressed {{ background-color: {pressed_color}; }}
            QToolButton:disabled {{ background-color: #5a6472; color: #cfd4da; }}
        """)
