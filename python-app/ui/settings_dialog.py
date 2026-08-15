"""Diálogo de configurações: escolha de modo (simulado / USB / BLE) e
parâmetros de conexão de cada transporte."""
from __future__ import annotations

from dataclasses import dataclass

from PyQt5.QtCore import pyqtSignal
from PyQt5.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

try:
    from serial.tools import list_ports
except ImportError:  # pyserial pode não estar instalado em modo só-simulação
    list_ports = None


@dataclass
class AppSettings:
    mode: str = "simulado"  # "simulado" | "real" (USB/Modbus RTU) | "ble"
    serial_port: str = ""
    baudrate: int = 9600
    slave_id: int = 1
    ble_address: str = ""


class SettingsDialog(QDialog):
    _devices_found = pyqtSignal(list, str)  # [(endereco, nome)], erro (vazio se ok)

    def __init__(self, current: AppSettings, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Configurações")
        self._devices_found.connect(self._on_devices_found)

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Simulação", "simulado")
        self.mode_combo.addItem("Real (USB/Modbus RTU)", "real")
        self.mode_combo.addItem("Real (Bluetooth BLE)", "ble")
        idx = self.mode_combo.findData(current.mode)
        if idx >= 0:
            self.mode_combo.setCurrentIndex(idx)
        self.mode_combo.currentIndexChanged.connect(self._update_visible_fields)

        # --- USB/Modbus RTU ---
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

        self.usb_port_label = QLabel("Porta serial:")
        self.usb_baud_label = QLabel("Baud rate:")
        self.usb_slave_label = QLabel("Endereço Modbus (slave id):")

        # --- Bluetooth BLE ---
        self.ble_combo = QComboBox()
        self.ble_combo.setEditable(True)
        if current.ble_address:
            self.ble_combo.setCurrentText(current.ble_address)

        self.scan_ble_btn = QPushButton("Escanear")
        self.scan_ble_btn.clicked.connect(self._scan_ble_devices)

        ble_row = QHBoxLayout()
        ble_row.addWidget(self.ble_combo, 1)
        ble_row.addWidget(self.scan_ble_btn)
        self.ble_row_label = QLabel("Dispositivo BLE:")

        form = QFormLayout()
        form.addRow("Modo:", self.mode_combo)
        form.addRow(self.usb_port_label, self.port_combo)
        form.addRow(self.usb_baud_label, self.baud_combo)
        form.addRow(self.usb_slave_label, self.slave_spin)
        form.addRow(self.ble_row_label, ble_row)

        self.test_btn = QPushButton("Testar conexão com ESP32")
        self.test_btn.clicked.connect(self._test_connection)
        self.test_result_label = QLabel("")

        test_row = QHBoxLayout()
        test_row.addWidget(self.test_btn)
        test_row.addWidget(self.test_result_label, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(test_row)
        layout.addWidget(buttons)

        self._update_visible_fields()

    def _update_visible_fields(self) -> None:
        mode = self.mode_combo.currentData()
        for widget in (self.usb_port_label, self.port_combo, self.usb_baud_label,
                       self.baud_combo, self.usb_slave_label, self.slave_spin):
            widget.setVisible(mode == "real")
        self.ble_row_label.setVisible(mode == "ble")
        self.ble_combo.setVisible(mode == "ble")
        self.scan_ble_btn.setVisible(mode == "ble")
        self.test_btn.setVisible(mode in ("real", "ble"))
        self.test_result_label.clear()

    def _test_connection(self) -> None:
        mode = self.mode_combo.currentData()
        self.test_btn.setEnabled(False)
        self.test_result_label.setText("Testando...")
        self.test_result_label.setStyleSheet("color: #888;")
        QApplication.processEvents()

        try:
            if mode == "real":
                port = self.port_combo.currentText().strip()
                if not port:
                    raise ValueError("Selecione uma porta serial.")
                from data_source.modbus_source import test_connection

                angle = test_connection(port, self.baud_combo.currentData(), self.slave_spin.value())
            elif mode == "ble":
                address = self.ble_combo.currentText().strip()
                if not address:
                    raise ValueError("Selecione ou informe um endereço BLE.")
                from data_source.ble_source import test_connection

                angle = test_connection(address)
            else:
                return

            self.test_result_label.setText(f"✓ ESP32 respondeu — ângulo atual: {angle:.2f}°")
            self.test_result_label.setStyleSheet("color: #2e7d32; font-weight: bold;")
        except Exception as exc:  # noqa: BLE001
            self.test_result_label.setText(f"✗ Falha: {exc}")
            self.test_result_label.setStyleSheet("color: #c62828; font-weight: bold;")
        finally:
            self.test_btn.setEnabled(True)

    def _scan_ble_devices(self) -> None:
        import threading

        self.scan_ble_btn.setEnabled(False)
        self.test_result_label.setText("Escaneando dispositivos BLE...")
        self.test_result_label.setStyleSheet("color: #888;")

        def worker() -> None:
            try:
                from data_source.ble_source import scan_devices

                devices = scan_devices()
                self._devices_found.emit(devices, "")
            except Exception as exc:  # noqa: BLE001
                self._devices_found.emit([], str(exc))

        threading.Thread(target=worker, daemon=True).start()

    def _on_devices_found(self, devices: list, error: str) -> None:
        self.scan_ble_btn.setEnabled(True)
        if error:
            self.test_result_label.setText(f"✗ Falha ao escanear: {error}")
            self.test_result_label.setStyleSheet("color: #c62828; font-weight: bold;")
            return
        if not devices:
            self.test_result_label.setText("Nenhum dispositivo BLE encontrado por perto.")
            self.test_result_label.setStyleSheet("color: #888;")
            return
        current_text = self.ble_combo.currentText()
        self.ble_combo.clear()
        for address, name in devices:
            self.ble_combo.addItem(f"{name} ({address})", address)
        if current_text:
            self.ble_combo.setCurrentText(current_text)
        self.test_result_label.setText(f"{len(devices)} dispositivo(s) encontrado(s).")
        self.test_result_label.setStyleSheet("color: #2e7d32; font-weight: bold;")

    def _populate_ports(self) -> None:
        if list_ports is None:
            return
        for p in list_ports.comports():
            self.port_combo.addItem(p.device)

    def result_settings(self) -> AppSettings:
        ble_address = self.ble_combo.currentData() or self.ble_combo.currentText().strip()
        return AppSettings(
            mode=self.mode_combo.currentData(),
            serial_port=self.port_combo.currentText().strip(),
            baudrate=self.baud_combo.currentData(),
            slave_id=self.slave_spin.value(),
            ble_address=ble_address,
        )
