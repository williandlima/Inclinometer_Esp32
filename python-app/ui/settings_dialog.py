"""Diálogo de configurações: escolha de modo (simulado/real) e parâmetros
de conexão RS485/Modbus RTU."""
from __future__ import annotations

from dataclasses import dataclass

from PyQt5.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QSpinBox,
    QVBoxLayout,
)

try:
    from serial.tools import list_ports
except ImportError:  # pyserial pode não estar instalado em modo só-simulação
    list_ports = None


@dataclass
class AppSettings:
    mode: str = "simulado"  # "simulado" | "real"
    serial_port: str = ""
    baudrate: int = 9600
    slave_id: int = 1


class SettingsDialog(QDialog):
    def __init__(self, current: AppSettings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Configurações")

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Simulação", "simulado")
        self.mode_combo.addItem("Real (RS485/Modbus RTU)", "real")
        idx = self.mode_combo.findData(current.mode)
        if idx >= 0:
            self.mode_combo.setCurrentIndex(idx)

        self.port_combo = QComboBox()
        self.port_combo.setEditable(True)
        self._populate_ports()
        if current.serial_port:
            self.port_combo.setCurrentText(current.serial_port)

        self.baud_combo = QComboBox()
        for baud in (9600, 19200, 38400, 57600, 115200):
            self.baud_combo.addItem(str(baud), baud)
        idx = self.baud_combo.findData(current.baudrate)
        if idx >= 0:
            self.baud_combo.setCurrentIndex(idx)

        self.slave_spin = QSpinBox()
        self.slave_spin.setRange(1, 247)
        self.slave_spin.setValue(current.slave_id)

        form = QFormLayout()
        form.addRow("Modo:", self.mode_combo)
        form.addRow("Porta serial:", self.port_combo)
        form.addRow("Baud rate:", self.baud_combo)
        form.addRow("Endereço Modbus (slave id):", self.slave_spin)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _populate_ports(self) -> None:
        if list_ports is None:
            return
        for p in list_ports.comports():
            self.port_combo.addItem(p.device)

    def result_settings(self) -> AppSettings:
        return AppSettings(
            mode=self.mode_combo.currentData(),
            serial_port=self.port_combo.currentText().strip(),
            baudrate=self.baud_combo.currentData(),
            slave_id=self.slave_spin.value(),
        )
