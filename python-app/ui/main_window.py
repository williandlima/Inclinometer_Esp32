"""Janela principal: exibição do ângulo em tempo real, destaque de novos
limites (mín/máx), e ações de reset/relatório."""
from __future__ import annotations

import datetime as _dt
import os
import threading

from PyQt5.QtCore import QObject, Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QFont, QPixmap
from PyQt5.QtWidgets import (
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QProgressDialog,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from data_source.base import AngleReading, IAngleDataSource
from data_source.ble_source import BleAngleSource
from data_source.modbus_source import ModbusAngleSource
from data_source.simulated_source import SimulatedAngleSource
from limits.history_store import HistoryStore
from limits.limit_tracker import PAN_AXIS, TILT_AXIS, LimitTracker
from limits.vibration_stats import analyze_axis, has_pan_samples
from report.report_generator import generate_report, generate_vibration_report
from ui.settings_dialog import AppSettings, SettingsDialog
from ui.vibration_dialog import VibrationConfigDialog, VibrationResultDialog

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

_VALUE_STYLE = f"font-size: 20px; font-weight: bold; color: {TEXT_LIGHT};"
_FLASH_STYLE = f"font-size: 20px; font-weight: bold; background-color: {ORANGE}; color: {NAVY}; border-radius: 4px;"

_BADGE_STYLE = "font-size: 13px; font-weight: bold; border-radius: 10px; padding: 4px 12px;"

_CONN_STYLES = {
    "parado": ("○ Parado", f"color: #9aa5b1; background: transparent;"),
    "conectando": ("◐ Conectando...", f"color: {ORANGE}; background: transparent; font-weight: bold;"),
    "conectado": ("● Conectado", f"{_BADGE_STYLE} color: white; background-color: {GREEN};"),
    "erro": ("● Falha de conexão", f"{_BADGE_STYLE} color: white; background-color: {RED};"),
    "simulacao": ("● Simulação (interna)", f"color: {ORANGE}; background: transparent; font-weight: bold;"),
}

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
    border-radius: 4px;
    padding: 8px 14px;
    font-weight: bold;
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
    border-radius: 6px;
}}
QStatusBar {{
    color: {TEXT_LIGHT};
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
        self.setWindowTitle("Inclinômetro — Painel Desktop")
        self.resize(900, 520)
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

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)

        root.addLayout(self._build_header())

        self.mode_label = QLabel()
        self.mode_label.setAlignment(Qt.AlignCenter)
        root.addWidget(self.mode_label)

        self.connection_label = QLabel()
        self.connection_label.setAlignment(Qt.AlignCenter)
        root.addWidget(self.connection_label)

        # Os dois eixos lado a lado, cada um com seu valor grande e seu par de
        # extremos. Inclinação à esquerda por ser o eixo principal do produto.
        axes_row = QHBoxLayout()
        self._axis_widgets = {
            TILT_AXIS: self._build_axis_panel("Inclinação (tilt)"),
            PAN_AXIS: self._build_axis_panel("Azimute (pan)"),
        }
        axes_row.addLayout(self._axis_widgets[TILT_AXIS]["layout"])
        axes_row.addLayout(self._axis_widgets[PAN_AXIS]["layout"])
        root.addLayout(axes_row)

        buttons_row = QHBoxLayout()
        self.start_stop_btn = QPushButton("Iniciar")
        self.start_stop_btn.clicked.connect(self._toggle_start_stop)
        self.reset_btn = QPushButton("Resetar limites")
        self.reset_btn.clicked.connect(self._reset_limits)
        self.calibrate_btn = QPushButton("Calibrar")
        self.calibrate_btn.clicked.connect(self._calibrate)
        self.vibration_btn = QPushButton("Modo Vibração")
        self.vibration_btn.clicked.connect(self._start_vibration_capture)
        self.settings_btn = QPushButton("Configurações...")
        self.settings_btn.clicked.connect(self._open_settings)
        self.report_btn = QPushButton("Gerar relatório PDF")
        self.report_btn.clicked.connect(self._generate_report)
        for btn in (
            self.start_stop_btn,
            self.reset_btn,
            self.calibrate_btn,
            self.vibration_btn,
            self.settings_btn,
            self.report_btn,
        ):
            buttons_row.addWidget(btn)
        root.addLayout(buttons_row)

        self.statusBar().showMessage("Pronto.")

    def _build_header(self) -> QHBoxLayout:
        header = QHBoxLayout()

        title_label = QLabel("Inclinômetro")
        title_label.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {TEXT_LIGHT};")
        header.addWidget(title_label)

        header.addStretch(1)

        if LOGO_PATH is not None:
            logo_label = QLabel()
            pixmap = QPixmap(LOGO_PATH)
            if not pixmap.isNull():
                logo_label.setPixmap(pixmap.scaledToHeight(40, Qt.SmoothTransformation))
                # A logo tem fundo branco (não transparente) — um "cartão"
                # branco arredondado ao redor evita que pareça um retângulo
                # solto sobre o fundo azul marinho do cabeçalho.
                logo_label.setStyleSheet("background-color: white; border-radius: 6px; padding: 6px 10px;")
                header.addWidget(logo_label, 0, Qt.AlignRight)
        else:
            logo_label = QLabel("AVIBRAS aeroco")
            logo_label.setStyleSheet(f"font-size: 16px; font-weight: bold; color: {ORANGE};")
            header.addWidget(logo_label, 0, Qt.AlignRight)

        return header

    def _build_axis_panel(self, title: str) -> dict:
        """Coluna de um eixo: título, valor grande, aviso opcional e o par de
        caixas de mínimo/máximo. Devolve os widgets num dicionário, para o
        resto da janela atualizar os dois eixos pelo mesmo caminho de código."""
        column = QVBoxLayout()

        title_label = QLabel(title)
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet(f"font-size: 14px; font-weight: bold; color: {ORANGE};")
        column.addWidget(title_label)

        value_label = QLabel("--.--°")
        value_label.setAlignment(Qt.AlignCenter)
        value_label.setFont(QFont("Sans Serif", 46, QFont.Bold))
        column.addWidget(value_label)

        # Normalmente oculto; usado para explicar por que um eixo está sem
        # valor (ex: firmware antigo, sem azimute). Fica escondido em vez de
        # só vazio porque a folha de estilo desta janela dá borda a QFrame, e
        # QLabel herda de QFrame — um rótulo vazio apareceria como uma faixa
        # com borda no meio do painel.
        note_label = QLabel("")
        note_label.setAlignment(Qt.AlignCenter)
        note_label.setStyleSheet("font-size: 11px; color: #9aa5b1;")
        note_label.setVisible(False)
        column.addWidget(note_label)

        limits_row = QHBoxLayout()
        min_frame, min_value_label, min_time_label = self._build_limit_box("Mínimo")
        max_frame, max_value_label, max_time_label = self._build_limit_box("Máximo")
        limits_row.addWidget(min_frame)
        limits_row.addWidget(max_frame)
        column.addLayout(limits_row)

        return {
            "layout": column,
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
        layout = QVBoxLayout(frame)

        title_label = QLabel(title)
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("font-weight: bold;")

        value_label = QLabel("--.--°")
        value_label.setAlignment(Qt.AlignCenter)
        value_label.setStyleSheet(_VALUE_STYLE)

        time_label = QLabel("")
        time_label.setAlignment(Qt.AlignCenter)

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
        self.mode_label.setText(f"Modo: {modo} — {estado}")

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
        for axis, value in values.items():
            widgets = self._axis_widgets[axis]
            if value is None:
                # Firmware anterior à v1.2.0 não mede azimute — deixa claro
                # que o eixo está sem dado, em vez de mostrar um zero falso.
                widgets["value"].setText("--.--°")
                widgets["note"].setText("firmware sem este eixo")
                widgets["note"].setVisible(True)
                continue
            widgets["value"].setText(f"{self._angle_for_display(axis, value):.2f}°")
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
