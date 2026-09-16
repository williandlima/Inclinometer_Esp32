"""Janela principal: exibição do ângulo em tempo real, destaque de novos
limites (mín/máx), e ações de reset/relatório."""
from __future__ import annotations

import datetime as _dt
import os
import threading

from PyQt5.QtCore import QObject, QSize, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QPixmap
from PyQt5.QtWidgets import (
    QFileDialog,
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QSizePolicy,
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
from ui.action_button import ActionButton
from ui.equipment_schematic import EquipmentSchematic
from ui.gauge_widget import AngleGauge
from ui.settings_dialog import AppSettings, SettingsDialog
from ui.vibration_dialog import VibrationConfigDialog, VibrationResultDialog

# Faixa de cada eixo, usada para desenhar o mostrador analógico (mín./máx.
# nas duas pontas do arco). A mesma faixa já usada para clamping em
# data_source/base.py.
_AXIS_RANGE = {
    TILT_AXIS: (ANGLE_MIN_DEG, ANGLE_MAX_DEG),
    PAN_AXIS: (PAN_MIN_DEG, PAN_MAX_DEG),
}

# Paleta Avibras Aeroco (fundo azul marinho + detalhes laranja). O logo é
# opcional: se `assets/logo.<ext>` existir (png, jpg ou jpeg), é exibido no
# canto superior direito; caso contrário, o título em texto já usa a mesma
# identidade visual.
NAVY = "#0B2145"
NAVY_PANEL = "#15305F"  # tom mais claro que o fundo, para destacar painéis/caixas
ORANGE = "#F5821F"
TEXT_LIGHT = "#F4F6F9"
GREEN = "#2e7d32"
RED = "#c62828"
STEEL_BLUE = "#2E5C8A"  # só para o botão de relatório — sinaliza "categoria diferente" (exportar dado, não operar o equipamento)
_ASSETS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")


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

_VALUE_BG = "#0D2557"  # navy mais escuro que NAVY_PANEL, para o número "flutuar" dentro da caixa
_VALUE_STYLE = f"font-size: 24px; font-weight: bold; color: {TEXT_LIGHT}; background-color: {_VALUE_BG}; border-radius: 12px; padding: 6px;"
_FLASH_STYLE = f"font-size: 24px; font-weight: bold; background-color: {ORANGE}; color: {NAVY}; border-radius: 12px; padding: 6px;"

# O grande valor central de cada eixo: mesma linguagem visual das caixas de
# mínimo/máximo (fundo mais escuro, canto arredondado), só maior e com borda
# — para ler como o "mostrador" principal do cartão. A caixa ocupa a largura
# do cartão (ver `column.addWidget(value_label)`, sem alinhamento central
# restringindo a largura ao texto) — um número grande boiando numa caixa
# pequena, do tamanho do próprio texto, é o que ficava "pequeno diante do
# tamanho do quadro".
_MAIN_VALUE_STYLE = (
    f"font-size: 88px; font-weight: bold; color: {TEXT_LIGHT}; background-color: {_VALUE_BG}; "
    f"border: 2px solid {ORANGE}; border-radius: 22px; padding: 10px 16px;"
)

# `border: none` explícito em todos: QLabel é subclasse de QFrame no Qt, então
# a borda laranja definida globalmente para QFrame (cartões/caixas) também
# valeria para qualquer QLabel comum, a menos que a própria regra do label
# a sobrescreva — sem isso, este indicador (isolado na barra de status,
# sem um fundo colorido cobrindo tudo) apareceria com uma moldura perdida.
_BADGE_STYLE = "font-size: 15px; font-weight: bold; border-radius: 12px; padding: 6px 16px; border: none;"

_CONN_STYLES = {
    "parado": ("○ Parado", "color: #9aa5b1; background: transparent; border: none;"),
    "conectando": ("◐ Conectando...", f"color: {ORANGE}; background: transparent; font-weight: bold; border: none;"),
    "conectado": ("● Conectado", f"{_BADGE_STYLE} color: white; background-color: {GREEN};"),
    "erro": ("● Falha de conexão", f"{_BADGE_STYLE} color: white; background-color: {RED};"),
    "simulacao": ("● Simulação (interna)", f"color: {ORANGE}; background: transparent; font-weight: bold; border: none;"),
}

# Botão de Configurações: estilo "fantasma" (contorno, sem preenchimento) —
# fica no cabeçalho, junto da marca, deliberadamente diferente dos botões de
# ação principal (que são a barra inferior, cheios), para não competir com
# eles nem parecer mais uma ação operacional do dia a dia.
_GHOST_BUTTON_STYLE = f"""
QPushButton {{
    background-color: transparent;
    color: {TEXT_LIGHT};
    border: 2px solid {ORANGE};
    border-radius: 8px;
    padding: 8px 16px;
    font-weight: bold;
    font-size: 13px;
}}
QPushButton:hover {{ background-color: rgba(245, 130, 31, 40); }}
QPushButton:pressed {{ background-color: rgba(245, 130, 31, 80); }}
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
    background-color: {ORANGE};
    color: {NAVY};
    border: none;
    border-radius: 10px;
    padding: 12px 18px;
    font-weight: bold;
    font-size: 14px;
}}
QPushButton:hover {{
    background-color: #ff9d40;
}}
QPushButton:pressed {{
    background-color: #cf6a12;
}}
QPushButton:disabled {{
    background-color: #5a6472;
    color: #cfd4da;
}}
QFrame {{
    background-color: {NAVY_PANEL};
    border: 2px solid {ORANGE};
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
        # mostrador analógico) + a barra de botões nunca se sobreporem,
        # mesmo desmaximizada e redimensionada para o menor tamanho possível.
        self.setMinimumSize(1160, 950)
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
        root.setSpacing(18)

        root.addLayout(self._build_header())
        root.addWidget(self._build_info_bar())

        # Os dois eixos lado a lado, com o esquema do equipamento entre
        # eles — cada cartão de eixo tem o mesmo tamanho (stretch 1), o
        # esquema fica no seu próprio tamanho (stretch 0). Peso 1 na coluna
        # principal para ocupar o espaço vertical que sobra numa janela
        # maximizada.
        axes_row = QHBoxLayout()
        axes_row.setSpacing(24)
        self._axis_widgets = {
            TILT_AXIS: self._build_axis_panel("Inclinação (tilt)", icons.tilt_icon, *_AXIS_RANGE[TILT_AXIS]),
            PAN_AXIS: self._build_axis_panel("Azimute (pan)", icons.pan_icon, *_AXIS_RANGE[PAN_AXIS]),
        }
        axes_row.addWidget(self._axis_widgets[TILT_AXIS]["frame"], 1)
        axes_row.addLayout(self._build_equipment_column())
        axes_row.addWidget(self._axis_widgets[PAN_AXIS]["frame"], 1)
        root.addLayout(axes_row, 1)

        root.addLayout(self._build_buttons_row())

        # Indicador de conexão embaixo da tela, junto da barra de status —
        # widget permanente (não é apagado pelas mensagens temporárias de
        # showMessage()) e fica à direita, convenção usual para indicador de
        # conexão persistente.
        self.connection_label = QLabel()
        self.connection_label.setAlignment(Qt.AlignCenter)
        self.statusBar().addPermanentWidget(self.connection_label)
        self.statusBar().showMessage("Pronto.")

    def _build_buttons_row(self) -> QHBoxLayout:
        buttons_row = QHBoxLayout()
        buttons_row.setSpacing(16)

        self.start_stop_btn = ActionButton("Iniciar", icons.play_icon("white"), GREEN, "white", "#3a9440", "#245c26")
        self.start_stop_btn.clicked.connect(self._toggle_start_stop)
        self.calibrate_btn = ActionButton("Calibrar", icons.target_icon(NAVY), ORANGE, NAVY, "#ff9d40", "#cf6a12")
        self.calibrate_btn.clicked.connect(self._calibrate)
        self.reset_btn = ActionButton("Resetar limites", icons.reset_icon(NAVY), ORANGE, NAVY, "#ff9d40", "#cf6a12")
        self.reset_btn.clicked.connect(self._reset_limits)
        self.vibration_btn = ActionButton("Modo Vibração", icons.vibration_icon(NAVY), ORANGE, NAVY, "#ff9d40", "#cf6a12")
        self.vibration_btn.clicked.connect(self._start_vibration_capture)
        self.report_btn = ActionButton("Gerar relatório PDF", icons.report_icon("white"), STEEL_BLUE, "white", "#3d74ab", "#1f405c")
        self.report_btn.clicked.connect(self._generate_report)

        # Ordem e agrupamento seguem o fluxo de uso, esquerda->direita:
        # (1) Iniciar/Parar, a ação principal, destacada por cor
        # (verde/vermelho); (2) Calibrar + Resetar limites, as duas ações
        # de preparação/ajuste da sessão, juntas, em laranja (a cor
        # "operacional" do resto do app); (3) Modo Vibração, um ensaio
        # especial, isolado, também laranja; (4) Gerar relatório, a ação
        # final ("exportar dado"), na ponta direita, na única cor nova
        # (azul-aço) — sinaliza que é uma categoria diferente de ação, sem
        # acrescentar mais que isso à paleta.
        buttons_row.addWidget(self.start_stop_btn, 1)
        buttons_row.addSpacing(8)
        buttons_row.addWidget(self.calibrate_btn, 1)
        buttons_row.addWidget(self.reset_btn, 1)
        buttons_row.addSpacing(8)
        buttons_row.addWidget(self.vibration_btn, 1)
        buttons_row.addSpacing(8)
        buttons_row.addWidget(self.report_btn, 1)

        return buttons_row

    def _set_start_stop_style(self, running: bool) -> None:
        if running:
            self.start_stop_btn.set_content("Parar", icons.stop_icon("white"))
            self.start_stop_btn.set_colors(RED, "white", "#e14040", "#931d1d")
        else:
            self.start_stop_btn.set_content("Iniciar", icons.play_icon("white"))
            self.start_stop_btn.set_colors(GREEN, "white", "#3a9440", "#245c26")

    def _build_header(self) -> QVBoxLayout:
        header_wrapper = QVBoxLayout()
        header_wrapper.setSpacing(14)

        header = QHBoxLayout()
        header.setSpacing(16)

        # Cartão branco simples, sem contorno colorido — a logo já tem
        # contraste de sobra contra o branco; uma borda laranja por cima só
        # competia com as cores da própria marca. A sombra suave já basta
        # para separar o cartão do fundo azul marinho. Fica à esquerda,
        # junto do título — é a marca "assinando" a tela, não um selo solto
        # no canto.
        logo_card = QFrame()
        logo_card.setStyleSheet("background-color: white; border: none; border-radius: 10px; padding: 6px 16px;")
        logo_card_layout = QHBoxLayout(logo_card)
        logo_card_layout.setContentsMargins(0, 0, 0, 0)
        if LOGO_PATH is not None:
            logo_label = QLabel()
            pixmap = QPixmap(LOGO_PATH)
            if not pixmap.isNull():
                logo_label.setPixmap(pixmap.scaledToHeight(52, Qt.SmoothTransformation))
        else:
            logo_label = QLabel("AVIBRAS aeroco")
            logo_label.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {ORANGE}; background: transparent;")
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
        title_label.setStyleSheet(f"font-size: 22px; font-weight: bold; color: {TEXT_LIGHT};")
        subtitle_label = QLabel("Monitoramento e Ensaio de Posicionamento")
        subtitle_label.setStyleSheet("font-size: 12px; color: #9aa5b1;")
        title_column.addWidget(title_label)
        title_column.addWidget(subtitle_label)
        header.addLayout(title_column)

        header.addStretch(1)

        # Configurações fica no cabeçalho, junto da marca — fora da barra de
        # ações operacionais de baixo (Iniciar/Calibrar/etc.), já que ajuste
        # de conexão é uma etapa de preparação, não uma ação do dia a dia.
        self.settings_btn = QPushButton(" Configurações")
        self.settings_btn.setIcon(icons.gear_icon(TEXT_LIGHT))
        self.settings_btn.setIconSize(QSize(18, 18))
        self.settings_btn.setStyleSheet(_GHOST_BUTTON_STYLE)
        self.settings_btn.clicked.connect(self._open_settings)
        header.addWidget(self.settings_btn)

        # Relógio — atualizado por QTimer em _update_clock(). Só decorativo
        # (não afeta nenhum dado/registro, que continuam usando o horário
        # real do sistema em cada leitura).
        self.clock_label = QLabel()
        self.clock_label.setStyleSheet("font-size: 13px; color: #9aa5b1;")
        self.clock_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        header.addWidget(self.clock_label)

        header_wrapper.addLayout(header)

        # Linha fina separando o cabeçalho do resto da tela — costura visual
        # entre a marca e os cartões de eixo abaixo.
        separator = QFrame()
        separator.setFrameShape(QFrame.HLine)
        separator.setFixedHeight(2)
        separator.setStyleSheet(f"background-color: {ORANGE}; border: none;")
        header_wrapper.addWidget(separator)

        return header_wrapper

    def _build_info_bar(self) -> QFrame:
        # Faixa de contexto entre o cabeçalho e os cartões — modo atual,
        # sensor (fixo: é o hardware que o firmware sempre usa, não depende
        # de nenhuma leitura) e porta/dispositivo quando aplicável. Deixada
        # de fora de propósito: telemetria que este app não recebe de
        # verdade (taxa de amostragem "vista" pelo app é a do polling, não
        # os 100Hz internos do firmware; não há leitura de temperatura no
        # protocolo) — mostrar isso seria inventar dado.
        frame = QFrame()
        frame.setStyleSheet(f"background-color: {NAVY_PANEL}; border: 1px solid #234070; border-radius: 8px;")
        layout = QHBoxLayout(frame)
        layout.setContentsMargins(18, 8, 18, 8)
        layout.setSpacing(24)

        def _segment(label_text: str) -> QLabel:
            value = QLabel(label_text)
            value.setStyleSheet(f"font-size: 13px; color: {TEXT_LIGHT}; font-weight: bold; border: none; background: transparent;")
            return value

        self.info_mode_label = _segment("—")
        self.info_sensor_label = _segment("MPU6050")
        self.info_device_label = _segment("—")

        for caption, value_label in (
            ("Modo", self.info_mode_label),
            ("Sensor", self.info_sensor_label),
            ("Porta/Dispositivo", self.info_device_label),
        ):
            caption_label = QLabel(caption + ":")
            caption_label.setStyleSheet("font-size: 12px; color: #9aa5b1; border: none; background: transparent;")
            pair = QHBoxLayout()
            pair.setSpacing(6)
            pair.addWidget(caption_label)
            pair.addWidget(value_label)
            layout.addLayout(pair)

        layout.addStretch(1)
        return frame

    def _build_equipment_column(self) -> QVBoxLayout:
        column = QVBoxLayout()
        column.setSpacing(8)
        title_label = QLabel("Posição do Equipamento")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setWordWrap(True)
        title_label.setStyleSheet(f"font-size: 13px; font-weight: bold; color: {ORANGE};")
        column.addWidget(title_label)
        self._equipment_schematic = EquipmentSchematic()
        column.addWidget(self._equipment_schematic, 1)
        return column

    def _build_axis_panel(self, title: str, icon_fn, minimum: float, maximum: float) -> dict:
        """Cartão de um eixo: título, mostrador analógico, valor digital
        grande, aviso opcional e o par de caixas de mínimo/máximo. Devolve
        os widgets num dicionário, para o resto da janela atualizar os dois
        eixos pelo mesmo caminho de código.

        É um QFrame (e não só um layout) de propósito: os dois eixos ficam
        como dois cartões do mesmo tamanho, com a mesma borda usada nas
        caixas de mínimo/máximo — o mesmo padrão visual, só numa escala
        maior — em vez de dois blocos de texto soltos sobre o fundo."""
        frame = QFrame()
        frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        frame.setMinimumHeight(570)
        column = QVBoxLayout(frame)
        column.setContentsMargins(20, 18, 20, 18)
        column.setSpacing(12)

        # Sombra suave por baixo do cartão — a mesma "elevação" da logo,
        # pra dar profundidade em vez de um contorno chapado.
        card_shadow = QGraphicsDropShadowEffect(frame)
        card_shadow.setBlurRadius(28)
        card_shadow.setOffset(0, 6)
        card_shadow.setColor(QColor(0, 0, 0, 90))
        frame.setGraphicsEffect(card_shadow)

        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        icon_label = QLabel()
        icon_label.setPixmap(icon_fn(ORANGE, 22).pixmap(QSize(22, 22)))
        title_label = QLabel(title)
        title_label.setStyleSheet(f"font-size: 17px; font-weight: bold; color: {ORANGE};")
        title_row.addStretch(1)
        title_row.addWidget(icon_label)
        title_row.addWidget(title_label)
        title_row.addStretch(1)
        column.addLayout(title_row)

        # Mostrador analógico (ponteiro em arco) — a indicação de posição
        # pedida, além do valor digital abaixo dele.
        gauge = AngleGauge(minimum, maximum)
        column.addWidget(gauge)

        value_label = QLabel("--.--°")
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
        note_label.setStyleSheet("font-size: 12px; color: #9aa5b1;")
        note_label.setVisible(False)
        column.addWidget(note_label)

        column.addStretch(1)

        limits_row = QHBoxLayout()
        limits_row.setSpacing(14)
        min_frame, min_value_label, min_time_label = self._build_limit_box("Mínimo")
        max_frame, max_value_label, max_time_label = self._build_limit_box("Máximo")
        limits_row.addWidget(min_frame, 1)
        limits_row.addWidget(max_frame, 1)
        column.addLayout(limits_row)

        return {
            "frame": frame,
            "gauge": gauge,
            "value": value_label,
            "note": note_label,
            "min_value": min_value_label,
            "min_time": min_time_label,
            "max_value": max_value_label,
            "max_time": max_time_label,
        }

    def _build_limit_box(self, title: str) -> tuple[QFrame, QLabel, QLabel]:
        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)
        frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        frame.setMinimumHeight(100)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(4)

        title_label = QLabel(title)
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("font-size: 13px; font-weight: bold;")

        value_label = QLabel("--.--°")
        value_label.setAlignment(Qt.AlignCenter)
        value_label.setStyleSheet(_VALUE_STYLE)

        time_label = QLabel("")
        time_label.setAlignment(Qt.AlignCenter)
        time_label.setStyleSheet("font-size: 12px; color: #b8c0cb;")

        layout.addWidget(title_label)
        layout.addWidget(value_label)
        layout.addWidget(time_label)
        return frame, value_label, time_label

    def _update_mode_label(self) -> None:
        modo = {
            "simulado": "Simulação",
            "real": "Real (USB/Modbus RTU)",
            "ble": "Real (Bluetooth BLE)",
        }[self._settings.mode]
        estado = "em execução" if self._running else "parado"
        self.info_mode_label.setText(f"{modo} ({estado})")

        if self._settings.mode == "real":
            device_text = self._settings.serial_port or "—"
        elif self._settings.mode == "ble":
            device_text = self._settings.ble_address or "—"
        else:
            device_text = "—"
        self.info_device_label.setText(device_text)

    def _update_clock(self) -> None:
        self.clock_label.setText(_dt.datetime.now().strftime("%d/%m/%Y   %H:%M:%S"))

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
        self.start_stop_btn.setText("Parar")
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
        self.start_stop_btn.setText("Iniciar")
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
        for axis, tracker in self._trackers.items():
            tracker.reset()
            widgets = self._axis_widgets[axis]
            widgets["min_value"].setText("--.--°")
            widgets["min_time"].setText("")
            widgets["max_value"].setText("--.--°")
            widgets["max_time"].setText("")
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
        self._equipment_schematic.setValues(values[TILT_AXIS], values[PAN_AXIS])
        for axis, value in values.items():
            widgets = self._axis_widgets[axis]
            if value is None:
                # Firmware anterior à v1.2.0 não mede azimute — deixa claro
                # que o eixo está sem dado, em vez de mostrar um zero falso.
                widgets["value"].setText("--.--°")
                widgets["gauge"].setValue(None)
                widgets["note"].setText("firmware sem este eixo")
                widgets["note"].setVisible(True)
                continue
            widgets["value"].setText(f"{self._angle_for_display(axis, value):.2f}°")
            widgets["gauge"].setValue(value)
            widgets["note"].setVisible(False)

            for event in self._trackers[axis].process(reading):
                self._history.add_limit_event(event)
                prefix = "min" if event.kind == "min" else "max"
                widgets[f"{prefix}_value"].setText(f"{event.value_deg:.2f}°")
                widgets[f"{prefix}_time"].setText(_fmt_time(event.reading.timestamp))
                self._flash(widgets[f"{prefix}_value"])

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
