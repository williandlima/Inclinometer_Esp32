"""Janela principal: exibição do ângulo em tempo real, destaque de novos
limites (mín/máx), e ações de reset/relatório."""
from __future__ import annotations

import datetime as _dt
import os
import threading

from PyQt5.QtCore import QObject, QSize, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QPixmap
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from app_version import APP_NAME
from data_source.base import (
    ANGLE_MAX_DEG,
    ANGLE_MIN_DEG,
    PAN_MAX_DEG,
    PAN_MIN_DEG,
    AngleReading,
    IAngleDataSource,
)
from data_source.ble_source import BleAngleSource
from data_source.modbus_source import ModbusAngleSource
from data_source.simulated_source import SimulatedAngleSource
from limits.history_store import HistoryStore
from limits.limit_tracker import PAN_AXIS, TILT_AXIS, LimitTracker
from limits.vibration_stats import analyze_axis, has_pan_samples
from report.report_generator import generate_report, generate_vibration_report
from ui import icons
from ui.gauge_widget import AngleGauge
from ui.settings_dialog import AppSettings, SettingsDialog
from ui.vibration_dialog import VibrationConfigDialog, VibrationResultDialog

# Faixa de cada eixo, usada para desenhar o mostrador analógico (mín./máx.
# nas duas pontas do arco) e para preencher a tabela de "Valores de
# referência". A mesma faixa já usada para clamping em data_source/base.py.
_AXIS_RANGE = {
    TILT_AXIS: (ANGLE_MIN_DEG, ANGLE_MAX_DEG),
    PAN_AXIS: (PAN_MIN_DEG, PAN_MAX_DEG),
}
_AXIS_LABEL = {
    TILT_AXIS: "Inclinação (tilt)",
    PAN_AXIS: "Azimute (pan)",
}

# Paleta Avibras Aeroco (fundo azul marinho, laranja só como sotaque
# pontual — cubo do ponteiro, indicador de aviso do mostrador — não mais
# como preenchimento de botão/título/borda de cartão espalhado pela tela;
# ver o histórico de feedback: "muito colorido"/"muito chamativo"/"tem que
# ficar mais profissional"). O logo é opcional: se `assets/logo.<ext>`
# existir (png, jpg ou jpeg), é exibido no canto superior esquerdo, junto do
# título; caso contrário, o título em texto já usa a mesma identidade
# visual.
NAVY = "#0B2145"
NAVY_PANEL = "#122A52"  # tom mais claro que o fundo, para destacar cartões/caixas
CARD_BORDER = "#22406E"  # contorno discreto dos cartões — não mais laranja
ORANGE = "#F5821F"
TEXT_LIGHT = "#F4F6F9"
TEXT_MUTED = "#8C9AB3"
GREEN = "#3DA55A"
RED = "#D9534F"
_ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")


def _fmt_num(value: float, decimals: int = 2) -> str:
    """Formata um número com separador decimal de vírgula (padrão
    brasileiro), sem o símbolo de grau — para células de tabela, cujo
    cabeçalho de coluna já diz a unidade."""
    return f"{value:.{decimals}f}".replace(".", ",")


def _fmt_deg(value: float, decimals: int = 2) -> str:
    """Como `_fmt_num`, mas com o símbolo de grau — para valores exibidos
    fora de uma tabela (mostrador digital, lista de mínimo/máximo/limite)."""
    return f"{_fmt_num(value, decimals)}°"


_PLACEHOLDER_DEG = "--,--°"
_PLACEHOLDER_NUM = "--,--"


def _find_logo_path() -> str | None:
    for ext in ("png", "jpg", "jpeg"):
        candidate = os.path.join(_ASSETS_DIR, f"logo.{ext}")
        if os.path.isfile(candidate):
            return candidate
    return None


LOGO_PATH = _find_logo_path()

# Exibição da leitura contínua em degraus de 0,25°. O grosso da estabilidade
# vem do firmware (filtro interno do MPU6050 + média móvel, ver
# firmware/src/AngleSensor.h); aqui é só a apresentação.
#
# A histerese evita o último resíduo de tremulação: sem ela, um valor parado
# bem na fronteira entre dois degraus (ex: 1,125°) alterna entre 1,00° e 1,25°
# a cada leitura. Só troca de degrau quando o valor passa da fronteira com
# uma margem extra.
#
# Nada disso afeta os dados guardados: histórico, mín/máx e relatório usam
# sempre o ângulo bruto.
DISPLAY_ANGLE_STEP_DEG = 0.25
DISPLAY_ANGLE_HYSTERESIS_DEG = 0.05

# Quantas leituras recentes ficam visíveis na tabela "Últimas leituras" — só
# um resumo em tela; o histórico completo de cada sessão continua
# integralmente no banco (ver limits/history_store.py) e no relatório PDF.
_RECENT_READINGS_ROWS = 6

_VALUE_STYLE = f"font-size: 20px; font-weight: bold; color: {TEXT_LIGHT}; background: transparent;"
_FLASH_STYLE = f"font-size: 20px; font-weight: bold; color: {ORANGE}; background: transparent;"

# O grande valor central de cada eixo: só o número, sem caixa/borda ao redor
# — lê como o dado "vivo" do cartão, na mesma superfície do resto do
# cartão, em vez de mais um retângulo chapado. O tamanho e o peso da fonte
# já bastam para destacá-lo.
_MAIN_VALUE_STYLE = f"font-size: 64px; font-weight: bold; color: {TEXT_LIGHT}; background: transparent;"

# `border: none` explícito em todos: QLabel é subclasse de QFrame no Qt, então
# a borda definida globalmente para QFrame (cartões) também valeria para
# qualquer QLabel comum, a menos que a própria regra do label a sobrescreva.
_PILL_STYLE = "font-size: 13px; font-weight: bold; border-radius: 10px; padding: 6px 14px; border: 1px solid #2C4A7C;"

_CONN_STYLES = {
    "parado": ("○ Parado", f"{_PILL_STYLE} color: {TEXT_MUTED}; background-color: {NAVY_PANEL};"),
    "conectando": ("◐ Conectando...", f"{_PILL_STYLE} color: {ORANGE}; background-color: {NAVY_PANEL};"),
    "conectado": ("●  Conectado", f"{_PILL_STYLE} color: {TEXT_LIGHT}; background-color: {NAVY_PANEL}; border-color: {GREEN};"),
    "erro": ("●  Falha de conexão", f"{_PILL_STYLE} color: {TEXT_LIGHT}; background-color: {NAVY_PANEL}; border-color: {RED};"),
    "simulacao": ("●  Simulação (interna)", f"{_PILL_STYLE} color: {ORANGE}; background-color: {NAVY_PANEL};"),
}

# Botão de Configurações: estilo "fantasma" (contorno neutro, sem
# preenchimento) — fica no cabeçalho, junto da marca, deliberadamente
# diferente dos botões de ação principal (a barra inferior), para não
# competir com eles nem parecer mais uma ação operacional do dia a dia.
_GHOST_BUTTON_STYLE = f"""
QPushButton {{
    background-color: transparent;
    color: {TEXT_LIGHT};
    border: 1px solid #2C4A7C;
    border-radius: 8px;
    padding: 8px 16px;
    font-weight: bold;
    font-size: 13px;
}}
QPushButton:hover {{ background-color: #1B3766; }}
QPushButton:pressed {{ background-color: #0D1D3B; }}
"""

# Botões de ação principal: os quatro neutros (Calibrar/Resetar/Vibração/
# Relatório) usam o mesmo fundo azul-marinho escuro do QPushButton padrão
# (ver _APP_STYLESHEET) — sem preenchimento laranja. Só o par Iniciar/Parar
# ganha uma cor própria (verde/vermelho apagados, não um sinal de trânsito),
# porque é a única ação com dois estados opostos que precisam ser
# distinguíveis à distância.
_START_BTN_STYLE = f"""
QPushButton {{ background-color: #234A34; color: {TEXT_LIGHT}; border: 1px solid {GREEN}; border-radius: 10px; padding: 12px 18px; font-weight: bold; font-size: 13px; }}
QPushButton:hover {{ background-color: #2B5A3F; }}
QPushButton:pressed {{ background-color: #1A3827; }}
"""
_STOP_BTN_STYLE = f"""
QPushButton {{ background-color: #4A2323; color: {TEXT_LIGHT}; border: 1px solid {RED}; border-radius: 10px; padding: 12px 18px; font-weight: bold; font-size: 13px; }}
QPushButton:hover {{ background-color: #5A2B2B; }}
QPushButton:pressed {{ background-color: #381A1A; }}
"""

_APP_STYLESHEET = f"""
QMainWindow, QWidget {{
    background-color: {NAVY};
    color: {TEXT_LIGHT};
}}
QLabel {{
    color: {TEXT_LIGHT};
}}
QPushButton {{
    background-color: #13284D;
    color: {TEXT_LIGHT};
    border: 1px solid #2C4A7C;
    border-radius: 10px;
    padding: 12px 18px;
    font-weight: bold;
    font-size: 13px;
}}
QPushButton:hover {{
    background-color: #1B3766;
}}
QPushButton:pressed {{
    background-color: #0D1D3B;
}}
QPushButton:disabled {{
    background-color: #1a2740;
    color: #5a6472;
    border-color: #223350;
}}
QFrame {{
    background-color: {NAVY_PANEL};
    border: 1px solid {CARD_BORDER};
    border-radius: 14px;
}}
/* QLabel é subclasse de QFrame no Qt — sem esta regra depois da de QFrame
   (a ordem decide o empate entre dois seletores de mesma especificidade),
   todo texto simples (títulos, "Modo: ...", etc.) herdaria a borda/fundo dos
   cartões. Widgets que precisam de um fundo próprio (badges, valores)
   definem seu style inline, que sempre tem prioridade sobre esta regra. */
QLabel {{
    border: none;
    background: transparent;
}}
QTableWidget {{
    background-color: transparent;
    color: {TEXT_LIGHT};
    border: none;
    gridline-color: {CARD_BORDER};
    font-size: 13px;
}}
QTableWidget::item {{
    padding: 6px;
    border: none;
    border-bottom: 1px solid {CARD_BORDER};
}}
QHeaderView::section {{
    background-color: transparent;
    color: {TEXT_LIGHT};
    font-weight: bold;
    font-size: 12px;
    border: none;
    border-bottom: 1px solid {CARD_BORDER};
    padding: 6px;
}}
QStatusBar {{
    color: {TEXT_LIGHT};
}}
QStatusBar::item {{
    border: none;
}}
"""


class _SignalBridge(QObject):
    """Ponte thread-safe: os data sources chamam callbacks em threads próprias;
    aqui os dados viram sinais Qt (fila automática para a thread da UI)."""

    reading = pyqtSignal(object)  # AngleReading
    error = pyqtSignal(str)
    calibration_done = pyqtSignal(bool, str)
    vibration_progress = pyqtSignal(float)
    vibration_done = pyqtSignal(object, str, float, float)  # amostras|None, erro, duration_s, rate_hz


def _fmt_time(ts: float) -> str:
    return _dt.datetime.fromtimestamp(ts).strftime("%H:%M:%S")


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} — Painel Desktop")
        # A janela abre maximizada (ver main.py, `showMaximized()`); este
        # tamanho só vale para quando o usuário desmaximiza manualmente, daí
        # ser bem maior que o mínimo abaixo.
        self.resize(1400, 970)
        # Alto o bastante para o cabeçalho + os dois cartões de eixo (com o
        # mostrador analógico) + as tabelas de resumo + a barra de botões
        # nunca se sobreporem, mesmo desmaximizada e redimensionada para o
        # menor tamanho possível. A largura mínima também precisa caber o
        # cabeçalho inteiro (marca + título + pill de conexão + caixa de
        # porta/IMU + relógio + botão de Configurações) sem que o título
        # seja espremido a ponto de cortar o texto.
        self.setMinimumSize(1360, 950)
        self.setStyleSheet(_APP_STYLESHEET)

        self._settings = AppSettings()
        self._history = HistoryStore()
        # Um rastreador de mín/máx por eixo: os extremos de inclinação e de
        # azimute são independentes.
        self._trackers = {TILT_AXIS: LimitTracker(TILT_AXIS), PAN_AXIS: LimitTracker(PAN_AXIS)}
        self._source: IAngleDataSource | None = None
        self._running = False
        self._vibration_progress_dialog: QProgressDialog | None = None
        # Degrau atualmente exibido em cada eixo (histerese da exibição).
        self._displayed: dict[str, float | None] = {TILT_AXIS: None, PAN_AXIS: None}

        self._bridge = _SignalBridge()
        self._bridge.reading.connect(self._on_reading)
        self._bridge.error.connect(self._on_error)
        self._bridge.calibration_done.connect(self._on_calibration_done)
        self._bridge.vibration_progress.connect(self._on_vibration_progress)
        self._bridge.vibration_done.connect(self._on_vibration_done)

        self._build_ui()
        self._update_mode_label()
        self._set_connection_status("parado")
        self._set_start_stop_style(running=False)
        self._init_reference_table()

        self._clock_timer = QTimer(self)
        self._clock_timer.timeout.connect(self._update_clock)
        self._clock_timer.start(1000)
        self._update_clock()

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        # Margens generosas e espaçamento maior: numa janela maximizada, sem
        # isso o conteúdo fica colado nas bordas e amontoado no topo,
        # deixando um vão vazio embaixo — a origem da impressão de
        # "desproporcional" relatada.
        root.setContentsMargins(28, 20, 28, 20)
        root.setSpacing(16)

        root.addLayout(self._build_header())

        axes_row = QHBoxLayout()
        axes_row.setSpacing(24)
        self._axis_widgets = {
            TILT_AXIS: self._build_axis_panel(_AXIS_LABEL[TILT_AXIS], icons.tilt_icon, *_AXIS_RANGE[TILT_AXIS]),
            PAN_AXIS: self._build_axis_panel(_AXIS_LABEL[PAN_AXIS], icons.pan_icon, *_AXIS_RANGE[PAN_AXIS]),
        }
        axes_row.addWidget(self._axis_widgets[TILT_AXIS]["frame"], 1)
        axes_row.addWidget(self._axis_widgets[PAN_AXIS]["frame"], 1)
        root.addLayout(axes_row, 1)

        root.addLayout(self._build_tables_row())
        root.addLayout(self._build_buttons_row())

        # Indicador de modo embaixo da tela, junto da barra de status —
        # widget permanente (não é apagado pelas mensagens temporárias de
        # showMessage()). O status de conexão já mora no cabeçalho (o "pill"
        # junto do título), então aqui sobra só o modo de operação.
        self.mode_label = QLabel()
        self.mode_label.setStyleSheet(f"font-size: 12px; color: {TEXT_MUTED};")
        self.statusBar().addPermanentWidget(self.mode_label)
        self.statusBar().showMessage("Pronto.")

    def _build_header(self) -> QVBoxLayout:
        header_wrapper = QVBoxLayout()
        header_wrapper.setSpacing(14)

        header = QHBoxLayout()
        header.setSpacing(16)

        # Cartão branco simples, sem contorno colorido — a logo já tem
        # contraste de sobra contra o branco; uma borda laranja por cima só
        # competia com as cores da própria marca. A sombra suave já basta
        # para separar o cartão do fundo azul marinho.
        logo_card = QFrame()
        logo_card.setStyleSheet("background-color: white; border: none; border-radius: 10px; padding: 6px 16px;")
        logo_card_layout = QHBoxLayout(logo_card)
        logo_card_layout.setContentsMargins(0, 0, 0, 0)
        if LOGO_PATH is not None:
            logo_label = QLabel()
            pixmap = QPixmap(LOGO_PATH)
            if not pixmap.isNull():
                logo_label.setPixmap(pixmap.scaledToHeight(48, Qt.SmoothTransformation))
        else:
            logo_label = QLabel("AVIBRAS aeroco")
            logo_label.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {NAVY}; background: transparent;")
        logo_card_layout.addWidget(logo_label)
        shadow = QGraphicsDropShadowEffect(logo_card)
        shadow.setBlurRadius(24)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 110))
        logo_card.setGraphicsEffect(shadow)
        header.addWidget(logo_card)

        title_column = QVBoxLayout()
        title_column.setSpacing(2)
        title_label = QLabel(APP_NAME)
        title_label.setStyleSheet(f"font-size: 20px; font-weight: bold; color: {TEXT_LIGHT};")
        # Nunca deixa a marca ser espremida abaixo do tamanho do próprio
        # texto — sem isso, num cabeçalho apertado (janela no tamanho
        # mínimo), o layout cortava o fim do título ("...Aeroco") em vez de
        # tirar espaço de outro elemento.
        title_label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Preferred)
        subtitle_label = QLabel("Monitoramento de Posicionamento")
        subtitle_label.setStyleSheet(f"font-size: 12px; color: {TEXT_MUTED};")
        title_column.addWidget(title_label)
        title_column.addWidget(subtitle_label)
        header.addLayout(title_column)

        header.addStretch(1)

        # Status de conexão — junto da marca, sempre visível, em vez de
        # escondido na barra de status lá embaixo.
        self.connection_label = QLabel()
        self.connection_label.setAlignment(Qt.AlignCenter)
        header.addWidget(self.connection_label)

        header.addWidget(self._build_info_card())
        header.addWidget(self._build_datetime_card())

        # Configurações fica no cabeçalho, junto da marca — fora da barra de
        # ações operacionais de baixo (Iniciar/Calibrar/etc.), já que ajuste
        # de conexão é uma etapa de preparação, não uma ação do dia a dia.
        self.settings_btn = QPushButton(" Configurações")
        self.settings_btn.setIcon(icons.gear_icon(TEXT_LIGHT))
        self.settings_btn.setIconSize(QSize(18, 18))
        self.settings_btn.setStyleSheet(_GHOST_BUTTON_STYLE)
        self.settings_btn.clicked.connect(self._open_settings)
        header.addWidget(self.settings_btn)

        header_wrapper.addLayout(header)

        # Linha fina separando o cabeçalho do resto da tela — costura visual
        # entre a marca e os cartões de eixo abaixo.
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFixedHeight(1)
        separator.setStyleSheet(f"background-color: {CARD_BORDER}; border: none;")
        header_wrapper.addWidget(separator)

        return header_wrapper

    def _build_info_card(self) -> QFrame:
        # Caixa curta de contexto no próprio cabeçalho — porta/dispositivo em
        # uso e o sensor do equipamento (fixo: é o hardware que o firmware
        # sempre usa, não depende de nenhuma leitura) — uma linha por dado,
        # em vez de lado a lado, para caber num cartão estreito.
        frame = QFrame()
        frame.setStyleSheet(f"background-color: {NAVY_PANEL}; border: 1px solid {CARD_BORDER}; border-radius: 8px;")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(4)

        def _segment(caption: str, value_text: str) -> tuple[QLabel, QHBoxLayout]:
            caption_label = QLabel(caption + ":")
            caption_label.setStyleSheet(f"font-size: 12px; color: {TEXT_MUTED}; border: none; background: transparent;")
            value_label = QLabel(value_text)
            value_label.setStyleSheet(f"font-size: 13px; color: {TEXT_LIGHT}; font-weight: bold; border: none; background: transparent;")
            pair = QHBoxLayout()
            pair.setSpacing(6)
            pair.addWidget(caption_label)
            pair.addWidget(value_label)
            pair.addStretch(1)
            return value_label, pair

        self.info_device_label, device_pair = _segment("Porta", "—")
        self.info_sensor_label, sensor_pair = _segment("IMU", "MPU6050")
        layout.addLayout(device_pair)
        layout.addLayout(sensor_pair)
        return frame

    def _build_datetime_card(self) -> QFrame:
        # Data em cima (texto normal) e hora embaixo (em negrito, o dado que
        # muda a cada segundo) — mesma linguagem visual do cartão de
        # Porta/IMU ao lado, só com os dois valores empilhados em vez de
        # rotulados, já que "data" e "hora" já são óbvios pelo formato.
        frame = QFrame()
        frame.setStyleSheet(f"background-color: {NAVY_PANEL}; border: 1px solid {CARD_BORDER}; border-radius: 8px;")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(2)

        self.date_label = QLabel()
        self.date_label.setStyleSheet(f"font-size: 12px; color: {TEXT_MUTED}; border: none; background: transparent;")
        self.clock_label = QLabel()
        self.clock_label.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {TEXT_LIGHT}; border: none; background: transparent;")

        layout.addWidget(self.date_label)
        layout.addWidget(self.clock_label)
        return frame

    def _build_axis_panel(self, title: str, icon_fn, minimum: float, maximum: float) -> dict:
        """Cartão de um eixo: título, mostrador analógico ao lado da lista de
        Mínimo/Máximo/Limite, e o valor digital grande abaixo, ocupando a
        largura toda do cartão. Devolve os widgets num dicionário, para o
        resto da janela atualizar os dois eixos pelo mesmo caminho de
        código.

        É um QFrame (e não só um layout) de propósito: os dois eixos ficam
        como dois cartões do mesmo tamanho, com a mesma borda usada nas
        caixas de mínimo/máximo — o mesmo padrão visual, só numa escala
        maior — em vez de dois blocos de texto soltos sobre o fundo."""
        frame = QFrame()
        frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        frame.setMinimumHeight(480)
        column = QVBoxLayout(frame)
        column.setContentsMargins(20, 16, 20, 16)
        column.setSpacing(12)

        # Sombra suave por baixo do cartão — a mesma "elevação" da logo, pra
        # dar profundidade em vez de um contorno chapado.
        card_shadow = QGraphicsDropShadowEffect(frame)
        card_shadow.setBlurRadius(28)
        card_shadow.setOffset(0, 6)
        card_shadow.setColor(QColor(0, 0, 0, 90))
        frame.setGraphicsEffect(card_shadow)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        icon_label = QLabel()
        icon_label.setPixmap(icon_fn(TEXT_LIGHT, 20).pixmap(QSize(20, 20)))
        title_label = QLabel(title)
        title_label.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {TEXT_LIGHT};")
        title_row.addWidget(icon_label)
        title_row.addWidget(title_label)
        title_row.addStretch(1)
        column.addLayout(title_row)

        # Mostrador analógico ao lado da lista vertical de Mínimo/Máximo/
        # Limite — o ponteiro dá a leitura de relance, a lista ao lado dá o
        # detalhe (valor e horário de cada extremo).
        content_row = QHBoxLayout()
        content_row.setSpacing(16)

        gauge = AngleGauge(minimum, maximum)
        content_row.addWidget(gauge, 2)

        limits_column = QVBoxLayout()
        limits_column.setSpacing(0)
        min_value_label = self._build_limit_row(limits_column, "Mínimo", with_divider=True)
        max_value_label = self._build_limit_row(limits_column, "Máximo", with_divider=True)
        # "Limite" é a própria faixa mecânica/de medição do eixo (a mesma
        # que define as pontas do mostrador) — estático, não um novo
        # conceito de limiar configurável que este app não tem.
        limit_value_label = self._build_limit_row(limits_column, "Limite", with_divider=False)
        limit_value_label.setText(f"±{_fmt_num(maximum)}")
        limits_column.addStretch(1)
        content_row.addLayout(limits_column, 1)

        column.addLayout(content_row, 1)

        value_label = QLabel(_PLACEHOLDER_DEG)
        value_label.setAlignment(Qt.AlignCenter)
        value_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        value_label.setStyleSheet(_MAIN_VALUE_STYLE)
        column.addWidget(value_label)

        # Normalmente oculto; usado para explicar por que um eixo está sem
        # valor (ex: firmware antigo, sem azimute). Escondido (setVisible)
        # em vez de só vazio para não reservar uma linha de espaço em branco
        # quando não há nenhum aviso a mostrar.
        note_label = QLabel("")
        note_label.setAlignment(Qt.AlignCenter)
        note_label.setStyleSheet(f"font-size: 12px; color: {TEXT_MUTED};")
        note_label.setVisible(False)
        column.addWidget(note_label)

        return {
            "frame": frame,
            "gauge": gauge,
            "value": value_label,
            "note": note_label,
            "min_value": min_value_label,
            "max_value": max_value_label,
            "limit_value": limit_value_label,
        }

    def _build_limit_row(self, parent_layout: QVBoxLayout, title: str, with_divider: bool) -> QLabel:
        """Uma linha "Mínimo"/"Máximo"/"Limite" na lista ao lado do
        mostrador: legenda pequena em cima, valor em negrito embaixo — sem
        caixa/borda própria (ela ficaria como um cartão dentro do cartão),
        só uma linha divisória fina abaixo para separar da próxima. O
        horário de cada extremo continua disponível, só que como dica
        (tooltip) no valor, em vez de uma terceira linha permanente na
        lista — a lista listada na referência não tem espaço pra isso."""
        row = QWidget()
        if with_divider:
            row.setObjectName("limitRow")
            row.setStyleSheet(f"QWidget#limitRow {{ border-bottom: 1px solid {CARD_BORDER}; }}")
        layout = QVBoxLayout(row)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(2)

        title_label = QLabel(title)
        title_label.setStyleSheet(f"font-size: 12px; color: {TEXT_MUTED};")

        value_label = QLabel(_PLACEHOLDER_DEG)
        value_label.setStyleSheet(_VALUE_STYLE)

        layout.addWidget(title_label)
        layout.addWidget(value_label)
        parent_layout.addWidget(row)
        return value_label

    def _build_tables_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(24)

        readings_card, self.readings_table = self._build_table_card(
            "Últimas leituras", ["Horário", "Tilt (°)", "Pan (°)"]
        )
        reference_card, self.reference_table = self._build_table_card(
            "Valores de referência", ["Parâmetro", "Mínimo (°)", "Máximo (°)", "Limite (°)"]
        )
        self.reference_table.setRowCount(len(_AXIS_LABEL))
        for row_idx, axis in enumerate((TILT_AXIS, PAN_AXIS)):
            self.reference_table.setItem(row_idx, 0, QTableWidgetItem(_AXIS_LABEL[axis]))

        row.addWidget(readings_card, 1)
        row.addWidget(reference_card, 1)
        return row

    def _build_table_card(self, title: str, columns: list[str]) -> tuple[QFrame, QTableWidget]:
        frame = QFrame()
        frame.setMinimumHeight(200)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(10)

        title_label = QLabel(title)
        title_label.setStyleSheet(f"font-size: 15px; font-weight: bold; color: {TEXT_LIGHT};")
        layout.addWidget(title_label)

        table = QTableWidget(0, len(columns))
        table.setHorizontalHeaderLabels(columns)
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionMode(QAbstractItemView.NoSelection)
        table.setFocusPolicy(Qt.NoFocus)
        # Sem cor alternada: sem um `alternate-background-color` explícito
        # no QSS, o Qt cai no cinza claro padrão da paleta do sistema — uma
        # faixa branca berrante sobre o fundo escuro. A linha divisória fina
        # de cada célula (ver QTableWidget::item no QSS) já separa as linhas
        # sem precisar de uma segunda cor de fundo.
        table.setAlternatingRowColors(False)
        table.setShowGrid(False)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(table, 1)

        return frame, table

    def _init_reference_table(self) -> None:
        for row_idx, axis in enumerate((TILT_AXIS, PAN_AXIS)):
            _minimum, maximum = _AXIS_RANGE[axis]
            self._set_reference_row(row_idx, min_text=_PLACEHOLDER_NUM, max_text=_PLACEHOLDER_NUM, limit_text=f"±{_fmt_num(maximum)}")

    def _set_reference_row(self, row_idx: int, *, min_text: str | None = None, max_text: str | None = None, limit_text: str | None = None) -> None:
        for col, text in ((1, min_text), (2, max_text), (3, limit_text)):
            if text is None:
                continue
            item = QTableWidgetItem(text)
            item.setTextAlignment(Qt.AlignCenter)
            self.reference_table.setItem(row_idx, col, item)

    def _push_recent_reading(self, tilt_deg: float | None, pan_deg: float | None, timestamp: float) -> None:
        table = self.readings_table
        table.insertRow(0)
        values = [
            _fmt_time(timestamp),
            _fmt_num(tilt_deg) if tilt_deg is not None else "—",
            _fmt_num(pan_deg) if pan_deg is not None else "—",
        ]
        for col, text in enumerate(values):
            item = QTableWidgetItem(text)
            item.setTextAlignment(Qt.AlignCenter)
            table.setItem(0, col, item)
        while table.rowCount() > _RECENT_READINGS_ROWS:
            table.removeRow(table.rowCount() - 1)

    def _build_buttons_row(self) -> QHBoxLayout:
        buttons_row = QHBoxLayout()
        buttons_row.setSpacing(16)

        self.start_stop_btn = QPushButton()
        self.start_stop_btn.setIconSize(QSize(18, 18))
        self.start_stop_btn.clicked.connect(self._toggle_start_stop)

        self.calibrate_btn = QPushButton(" CALIBRAR")
        self.calibrate_btn.setIcon(icons.target_icon(TEXT_LIGHT))
        self.calibrate_btn.setIconSize(QSize(18, 18))
        self.calibrate_btn.clicked.connect(self._calibrate)

        self.reset_btn = QPushButton(" RESETAR LIMITES")
        self.reset_btn.setIcon(icons.reset_icon(TEXT_LIGHT))
        self.reset_btn.setIconSize(QSize(18, 18))
        self.reset_btn.clicked.connect(self._reset_limits)

        self.vibration_btn = QPushButton(" MODO VIBRAÇÃO")
        self.vibration_btn.setIcon(icons.vibration_icon(TEXT_LIGHT))
        self.vibration_btn.setIconSize(QSize(18, 18))
        self.vibration_btn.clicked.connect(self._start_vibration_capture)

        self.report_btn = QPushButton(" GERAR RELATÓRIO")
        self.report_btn.setIcon(icons.report_icon(TEXT_LIGHT))
        self.report_btn.setIconSize(QSize(18, 18))
        self.report_btn.clicked.connect(self._generate_report)

        for btn in (
            self.start_stop_btn,
            self.calibrate_btn,
            self.reset_btn,
            self.vibration_btn,
            self.report_btn,
        ):
            btn.setMinimumHeight(46)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            buttons_row.addWidget(btn, 1)

        return buttons_row

    def _set_start_stop_style(self, running: bool) -> None:
        if running:
            self.start_stop_btn.setText(" PARAR")
            self.start_stop_btn.setIcon(icons.stop_icon(TEXT_LIGHT))
            self.start_stop_btn.setStyleSheet(_STOP_BTN_STYLE)
        else:
            self.start_stop_btn.setText(" INICIAR")
            self.start_stop_btn.setIcon(icons.play_icon(TEXT_LIGHT))
            self.start_stop_btn.setStyleSheet(_START_BTN_STYLE)

    def _update_mode_label(self) -> None:
        modo = {
            "simulado": "Simulação",
            "real": "Real (USB/Modbus RTU)",
            "ble": "Real (Bluetooth BLE)",
        }[self._settings.mode]
        estado = "em execução" if self._running else "parado"
        self.mode_label.setText(f"Modo: {modo} — {estado}")

        if self._settings.mode == "real":
            device_text = self._settings.serial_port or "—"
        elif self._settings.mode == "ble":
            device_text = self._settings.ble_address or "—"
        else:
            device_text = "—"
        self.info_device_label.setText(device_text)

    def _update_clock(self) -> None:
        now = _dt.datetime.now()
        self.date_label.setText(now.strftime("%d/%m/%Y"))
        self.clock_label.setText(now.strftime("%H:%M:%S"))

    def _set_connection_status(self, status: str) -> None:
        text, style = _CONN_STYLES[status]
        self.connection_label.setText(text)
        self.connection_label.setStyleSheet(style)

    # --------------------------------------------------------------- ações
    def _open_settings(self) -> None:
        dialog = SettingsDialog(self._settings, self)
        if dialog.exec_() == SettingsDialog.Accepted:
            was_running = self._running
            if was_running:
                self._stop()
            self._settings = dialog.result_settings()
            self._update_mode_label()
            if was_running:
                self._start()

    def _toggle_start_stop(self) -> None:
        if self._running:
            self._stop()
        else:
            self._start()

    def _start(self) -> None:
        if self._settings.mode == "real" and not self._settings.serial_port:
            QMessageBox.warning(self, "Configuração incompleta", "Selecione uma porta serial nas Configurações.")
            return
        if self._settings.mode == "ble" and not self._settings.ble_address:
            QMessageBox.warning(self, "Configuração incompleta", "Selecione ou informe um dispositivo BLE nas Configurações.")
            return

        if self._settings.mode == "simulado":
            self._source = SimulatedAngleSource()
        elif self._settings.mode == "ble":
            self._source = BleAngleSource(device_address=self._settings.ble_address)
        else:
            self._source = ModbusAngleSource(
                port=self._settings.serial_port,
                baudrate=self._settings.baudrate,
                slave_id=self._settings.slave_id,
            )

        for tracker in self._trackers.values():
            tracker.reset()
        self._displayed = {TILT_AXIS: None, PAN_AXIS: None}
        self._history.start_session(mode=self._settings.mode)
        self._source.start(
            on_reading=lambda r: self._bridge.reading.emit(r),
            on_error=lambda msg: self._bridge.error.emit(msg),
        )
        self._running = True
        self._set_start_stop_style(running=True)
        self._update_mode_label()
        self._set_connection_status("simulacao" if self._settings.mode == "simulado" else "conectando")
        self.statusBar().showMessage(f"Conectado: {self._source.label}")

    def _stop(self) -> None:
        if self._source is not None:
            self._source.stop()
            self._source = None
        self._history.end_session()
        self._running = False
        self._displayed = {TILT_AXIS: None, PAN_AXIS: None}
        self._set_start_stop_style(running=False)
        self._update_mode_label()
        self._set_connection_status("parado")
        self.statusBar().showMessage("Parado.")

    def _reset_limits(self) -> None:
        was_running = self._running
        mode = self._settings.mode
        if was_running:
            self._history.end_session()
            self._history.start_session(mode=mode)
        for row_idx, axis in enumerate((TILT_AXIS, PAN_AXIS)):
            tracker = self._trackers[axis]
            tracker.reset()
            widgets = self._axis_widgets[axis]
            widgets["min_value"].setText(_PLACEHOLDER_DEG)
            widgets["min_value"].setToolTip("")
            widgets["max_value"].setText(_PLACEHOLDER_DEG)
            widgets["max_value"].setToolTip("")
            self._set_reference_row(row_idx, min_text=_PLACEHOLDER_NUM, max_text=_PLACEHOLDER_NUM)
        self.statusBar().showMessage(
            "Limites resetados (histórico anterior preservado)." if was_running
            else "Limites resetados."
        )

    def _generate_report(self) -> None:
        session_id = self._history.current_session_id
        if session_id is None:
            sessions = self._history.list_sessions()
            if not sessions:
                QMessageBox.information(self, "Sem dados", "Ainda não há nenhuma sessão registrada.")
                return
            session_id = sessions[0].id

        default_name = f"relatorio_inclinometro_{_dt.datetime.now():%Y%m%d_%H%M%S}.pdf"
        default_path = os.path.join(os.getcwd(), default_name)
        path, _ = QFileDialog.getSaveFileName(self, "Salvar relatório", default_path, "PDF (*.pdf)")
        if not path:
            return

        readings = self._history.get_readings(session_id)
        events = self._history.get_limit_events(session_id)
        sessions_by_id = {s.id: s for s in self._history.list_sessions()}
        session_info = sessions_by_id.get(session_id)

        try:
            generate_report(path, session_info, readings, events)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Erro ao gerar relatório", str(exc))
            return

        QMessageBox.information(self, "Relatório gerado", f"Relatório salvo em:\n{path}")

    def _angle_for_display(self, axis: str, angle_deg: float) -> float:
        """Arredonda para o degrau de exibição, com histerese para não
        alternar entre dois degraus quando o valor fica na fronteira. Cada
        eixo tem seu próprio estado de histerese."""
        step = DISPLAY_ANGLE_STEP_DEG
        current = self._displayed[axis]
        if current is None or abs(angle_deg - current) >= step / 2 + DISPLAY_ANGLE_HYSTERESIS_DEG:
            self._displayed[axis] = round(angle_deg / step) * step
        return self._displayed[axis]

    # ------------------------------------------------------------ callbacks
    def _on_reading(self, reading: AngleReading) -> None:
        if self._settings.mode in ("real", "ble"):
            self._set_connection_status("conectado")
        self._history.add_reading(reading)

        values = {TILT_AXIS: reading.angle_deg, PAN_AXIS: reading.pan_deg}
        self._push_recent_reading(values[TILT_AXIS], values[PAN_AXIS], reading.timestamp)

        for row_idx, axis in enumerate((TILT_AXIS, PAN_AXIS)):
            value = values[axis]
            widgets = self._axis_widgets[axis]
            if value is None:
                # Firmware anterior à v1.2.0 não mede azimute — deixa claro
                # que o eixo está sem dado, em vez de mostrar um zero falso.
                widgets["value"].setText(_PLACEHOLDER_DEG)
                widgets["gauge"].setValue(None)
                widgets["note"].setText("firmware sem este eixo")
                widgets["note"].setVisible(True)
                continue
            widgets["value"].setText(_fmt_deg(self._angle_for_display(axis, value)))
            widgets["gauge"].setValue(value)
            widgets["note"].setVisible(False)

            for event in self._trackers[axis].process(reading):
                self._history.add_limit_event(event)
                prefix = "min" if event.kind == "min" else "max"
                label = widgets[f"{prefix}_value"]
                label.setText(_fmt_deg(event.value_deg))
                label.setToolTip(f"Ocorreu às {_fmt_time(event.reading.timestamp)}")
                self._flash(label)
                self._set_reference_row(row_idx, **{f"{prefix}_text": _fmt_num(event.value_deg)})

    def _on_error(self, message: str) -> None:
        if self._settings.mode in ("real", "ble"):
            self._set_connection_status("erro")
        self.statusBar().showMessage(message, 5000)

    def _calibrate(self) -> None:
        if self._source is None or not self._running:
            QMessageBox.warning(self, "Não conectado", "Inicie a leitura antes de calibrar.")
            return
        if not getattr(self._source, "supports_calibration", False):
            QMessageBox.information(self, "Calibração", "Esta fonte de dados não suporta calibração.")
            return

        source = self._source
        self.calibrate_btn.setEnabled(False)
        self.statusBar().showMessage("Calibrando...")

        def worker() -> None:
            try:
                source.calibrate()
                self._bridge.calibration_done.emit(True, "Calibração concluída: posição atual definida como 0°.")
            except Exception as exc:  # noqa: BLE001
                self._bridge.calibration_done.emit(False, f"Falha na calibração: {exc}")

        threading.Thread(target=worker, daemon=True).start()

    def _on_calibration_done(self, ok: bool, message: str) -> None:
        self.calibrate_btn.setEnabled(True)
        self.statusBar().showMessage(message, 5000)
        if ok:
            self._reset_limits()
        else:
            QMessageBox.warning(self, "Calibração", message)

    def _start_vibration_capture(self) -> None:
        if self._source is None or not self._running:
            QMessageBox.warning(self, "Não conectado", "Inicie a leitura antes de usar o Modo Vibração.")
            return
        if not getattr(self._source, "supports_vibration_capture", False):
            QMessageBox.information(self, "Modo Vibração", "Esta fonte de dados não suporta captura de vibração.")
            return

        dialog = VibrationConfigDialog(self)
        if dialog.exec_() != VibrationConfigDialog.Accepted:
            return
        duration_s, rate_hz = dialog.result_values()

        progress = QProgressDialog("Capturando...", "Cancelar", 0, 100, self)
        progress.setWindowTitle("Modo Vibração")
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.setValue(0)

        source = self._source
        progress.canceled.connect(lambda: getattr(source, "stop_vibration_capture", lambda: None)())
        self._vibration_progress_dialog = progress

        self.vibration_btn.setEnabled(False)
        self.statusBar().showMessage("Captura de vibração em andamento...")

        def on_progress(percent: float) -> None:
            self._bridge.vibration_progress.emit(percent)

        def on_done(readings: list[AngleReading] | None, error: str | None) -> None:
            self._bridge.vibration_done.emit(readings if readings is not None else [], error or "", duration_s, rate_hz)

        source.start_vibration_capture(duration_s, rate_hz, on_progress, on_done)

    def _on_vibration_progress(self, percent: float) -> None:
        if self._vibration_progress_dialog is not None:
            self._vibration_progress_dialog.setValue(int(percent))

    def _on_vibration_done(self, readings: list, error: str, duration_s: float, rate_hz: float) -> None:
        self.vibration_btn.setEnabled(True)
        if self._vibration_progress_dialog is not None:
            self._vibration_progress_dialog.close()
            self._vibration_progress_dialog = None

        if error:
            self.statusBar().showMessage(f"Captura de vibração: {error}", 5000)
            if error != "Captura cancelada pelo usuário.":
                QMessageBox.warning(self, "Modo Vibração", error)
            return

        if not readings:
            QMessageBox.warning(self, "Modo Vibração", "Nenhuma amostra foi capturada.")
            return

        capture_id = self._history.save_vibration_capture(self._settings.mode, duration_s, rate_hz, readings)
        tilt = analyze_axis(readings, rate_hz, TILT_AXIS)
        # O eixo de azimute só existe na captura com firmware >= 1.3.0.
        pan = analyze_axis(readings, rate_hz, PAN_AXIS) if has_pan_samples(readings) else None
        self.statusBar().showMessage("Captura de vibração concluída.", 5000)

        result_dialog = VibrationResultDialog(tilt.stats, pan.stats if pan else None, self)
        result_dialog.exec_()
        if not result_dialog.save_requested:
            return

        default_name = f"relatorio_vibracao_{_dt.datetime.now():%Y%m%d_%H%M%S}.pdf"
        default_path = os.path.join(os.getcwd(), default_name)
        path, _ = QFileDialog.getSaveFileName(self, "Salvar relatório de vibração", default_path, "PDF (*.pdf)")
        if not path:
            return

        captures_by_id = {c.id: c for c in self._history.list_vibration_captures()}
        capture_info = captures_by_id.get(capture_id)
        try:
            generate_vibration_report(path, capture_info, readings, tilt, pan)
        except Exception as exc:  # noqa: BLE001
            QMessageBox.critical(self, "Erro ao gerar relatório", str(exc))
            return

        QMessageBox.information(self, "Relatório gerado", f"Relatório salvo em:\n{path}")

    def _flash(self, label: QLabel) -> None:
        label.setStyleSheet(_FLASH_STYLE)
        QTimer.singleShot(1500, lambda: label.setStyleSheet(_VALUE_STYLE))

    # -------------------------------------------------------------- ciclo de vida
    def closeEvent(self, event) -> None:  # noqa: N802 - método do Qt
        if self._running:
            self._stop()
        self._history.close()
        super().closeEvent(event)
