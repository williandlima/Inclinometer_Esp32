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
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from data_source.base import AngleReading, IAngleDataSource
from data_source.modbus_source import ModbusAngleSource
from data_source.simulated_source import SimulatedAngleSource
from limits.history_store import HistoryStore
from limits.limit_tracker import LimitTracker
from report.report_generator import generate_report
from ui.settings_dialog import AppSettings, SettingsDialog

# Paleta Avibras Aeroco (azul marinho + laranja). O logo (PNG com fundo
# transparente) é opcional: se `assets/logo.png` existir, é exibido no
# cabeçalho; caso contrário, o título em texto já usa as mesmas cores.
NAVY = "#0B2145"
ORANGE = "#F5821F"
LIGHT_BG = "#F4F6F9"
LOGO_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "logo.png")

_VALUE_STYLE = f"font-size: 20px; font-weight: bold; color: {NAVY};"
_FLASH_STYLE = f"font-size: 20px; font-weight: bold; background-color: {ORANGE}; color: white; border-radius: 4px;"

_CONN_STYLES = {
    "parado": ("○ Parado", "color: #888;"),
    "conectando": ("◐ Conectando...", f"color: {ORANGE}; font-weight: bold;"),
    "conectado": ("● Conectado", "color: #2e7d32; font-weight: bold;"),
    "erro": ("● Falha de conexão", "color: #c62828; font-weight: bold;"),
    "simulacao": ("● Simulação (interna)", f"color: {NAVY}; font-weight: bold;"),
}

_APP_STYLESHEET = f"""
QMainWindow, QWidget {{
    background-color: {LIGHT_BG};
}}
QPushButton {{
    background-color: {NAVY};
    color: white;
    border: none;
    border-radius: 4px;
    padding: 8px 14px;
    font-weight: bold;
}}
QPushButton:hover {{
    background-color: {ORANGE};
}}
QPushButton:pressed {{
    background-color: #cf6a12;
}}
QPushButton:disabled {{
    background-color: #a9b2bd;
}}
QFrame {{
    background-color: white;
    border: 2px solid {ORANGE};
    border-radius: 6px;
}}
"""


class _SignalBridge(QObject):
    """Ponte thread-safe: os data sources chamam callbacks em threads próprias;
    aqui os dados viram sinais Qt (fila automática para a thread da UI)."""

    reading = pyqtSignal(object)  # AngleReading
    error = pyqtSignal(str)
    calibration_done = pyqtSignal(bool, str)


def _fmt_time(ts: float) -> str:
    return _dt.datetime.fromtimestamp(ts).strftime("%H:%M:%S")


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Inclinômetro — Painel Desktop")
        self.resize(520, 460)
        self.setStyleSheet(_APP_STYLESHEET)

        self._settings = AppSettings()
        self._history = HistoryStore()
        self._tracker = LimitTracker()
        self._source: IAngleDataSource | None = None
        self._running = False

        self._bridge = _SignalBridge()
        self._bridge.reading.connect(self._on_reading)
        self._bridge.error.connect(self._on_error)
        self._bridge.calibration_done.connect(self._on_calibration_done)

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

        self.angle_label = QLabel("--.--°")
        self.angle_label.setAlignment(Qt.AlignCenter)
        self.angle_label.setFont(QFont("Sans Serif", 64, QFont.Bold))
        root.addWidget(self.angle_label)

        limits_row = QHBoxLayout()
        self.min_frame, self.min_value_label, self.min_time_label = self._build_limit_box("Mínimo")
        self.max_frame, self.max_value_label, self.max_time_label = self._build_limit_box("Máximo")
        limits_row.addWidget(self.min_frame)
        limits_row.addWidget(self.max_frame)
        root.addLayout(limits_row)

        buttons_row = QHBoxLayout()
        self.start_stop_btn = QPushButton("Iniciar")
        self.start_stop_btn.clicked.connect(self._toggle_start_stop)
        self.reset_btn = QPushButton("Resetar limites")
        self.reset_btn.clicked.connect(self._reset_limits)
        self.calibrate_btn = QPushButton("Calibrar")
        self.calibrate_btn.clicked.connect(self._calibrate)
        self.settings_btn = QPushButton("Configurações...")
        self.settings_btn.clicked.connect(self._open_settings)
        self.report_btn = QPushButton("Gerar relatório PDF")
        self.report_btn.clicked.connect(self._generate_report)
        for btn in (self.start_stop_btn, self.reset_btn, self.calibrate_btn, self.settings_btn, self.report_btn):
            buttons_row.addWidget(btn)
        root.addLayout(buttons_row)

        self.statusBar().showMessage("Pronto.")

    def _build_header(self) -> QHBoxLayout:
        header = QHBoxLayout()
        header.setAlignment(Qt.AlignCenter)

        if os.path.isfile(LOGO_PATH):
            logo_label = QLabel()
            pixmap = QPixmap(LOGO_PATH)
            if not pixmap.isNull():
                logo_label.setPixmap(pixmap.scaledToHeight(48, Qt.SmoothTransformation))
                header.addWidget(logo_label)

        title_label = QLabel("Inclinômetro — Avibras Aeroco")
        title_label.setStyleSheet(f"font-size: 18px; font-weight: bold; color: {NAVY};")
        header.addWidget(title_label)
        return header

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
        modo = "Simulação" if self._settings.mode == "simulado" else "Real (RS485/Modbus RTU)"
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

        if self._settings.mode == "simulado":
            self._source = SimulatedAngleSource()
        else:
            self._source = ModbusAngleSource(
                port=self._settings.serial_port,
                baudrate=self._settings.baudrate,
                slave_id=self._settings.slave_id,
            )

        self._tracker.reset()
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
        self._tracker.reset()
        self.min_value_label.setText("--.--°")
        self.min_time_label.setText("")
        self.max_value_label.setText("--.--°")
        self.max_time_label.setText("")
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

    # ------------------------------------------------------------ callbacks
    def _on_reading(self, reading: AngleReading) -> None:
        if self._settings.mode == "real":
            self._set_connection_status("conectado")
        self.angle_label.setText(f"{reading.angle_deg:.2f}°")
        self._history.add_reading(reading)

        for event in self._tracker.process(reading):
            self._history.add_limit_event(event)
            if event.kind == "min":
                self.min_value_label.setText(f"{event.reading.angle_deg:.2f}°")
                self.min_time_label.setText(_fmt_time(event.reading.timestamp))
                self._flash(self.min_value_label)
            else:
                self.max_value_label.setText(f"{event.reading.angle_deg:.2f}°")
                self.max_time_label.setText(_fmt_time(event.reading.timestamp))
                self._flash(self.max_value_label)

    def _on_error(self, message: str) -> None:
        if self._settings.mode == "real":
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

    def _flash(self, label: QLabel) -> None:
        label.setStyleSheet(_FLASH_STYLE)
        QTimer.singleShot(1500, lambda: label.setStyleSheet(_VALUE_STYLE))

    # -------------------------------------------------------------- ciclo de vida
    def closeEvent(self, event) -> None:  # noqa: N802 - método do Qt
        if self._running:
            self._stop()
        self._history.close()
        super().closeEvent(event)
