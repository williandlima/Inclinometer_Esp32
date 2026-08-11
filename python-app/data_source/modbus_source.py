"""Fonte de dados real: leitura do ângulo via RS485/Modbus RTU.

Contrato assumido com o firmware do ESP32 (ainda não implementado nesta
fase): o ângulo atual é exposto no registrador de entrada (input register)
`ANGLE_INPUT_REGISTER`, como inteiro de 16 bits igual a `angulo * SCALE`
(duas casas decimais de resolução). O rastreamento de mínimo/máximo é feito
no próprio app (`limits.limit_tracker`), não depende de registradores extras
no escravo — assim o contrato Modbus fica mínimo e estável mesmo antes do
firmware existir.
"""
from __future__ import annotations

import threading
import time

from data_source.base import AngleReading, ErrorCallback, IAngleDataSource, ReadingCallback

ANGLE_INPUT_REGISTER = 0
ANGLE_SCALE = 100.0  # registrador = ângulo * 100 (int16, resolução de 0.01°)


class ModbusAngleSource(IAngleDataSource):
    def __init__(
        self,
        port: str,
        baudrate: int = 9600,
        slave_id: int = 1,
        poll_interval_s: float = 0.25,
        timeout_s: float = 1.0,
    ) -> None:
        self._port = port
        self._baudrate = baudrate
        self._slave_id = slave_id
        self._poll_interval = poll_interval_s
        self._timeout = timeout_s

        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

    @property
    def label(self) -> str:
        return f"RS485/Modbus RTU ({self._port}@{self._baudrate}, id={self._slave_id})"

    def start(self, on_reading: ReadingCallback, on_error: ErrorCallback | None = None) -> None:
        if self._thread is not None:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, args=(on_reading, on_error), daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _run(self, on_reading: ReadingCallback, on_error: ErrorCallback | None) -> None:
        # Import local para não exigir pymodbus/pyserial quando só o modo
        # simulado for usado (ex: ambiente de desenvolvimento sem RS485).
        from pymodbus.client import ModbusSerialClient

        client = ModbusSerialClient(
            port=self._port,
            baudrate=self._baudrate,
            timeout=self._timeout,
        )

        try:
            if not client.connect():
                if on_error:
                    on_error(f"Não foi possível abrir a porta serial {self._port}.")
                return

            while not self._stop_event.is_set():
                try:
                    result = client.read_input_registers(
                        address=ANGLE_INPUT_REGISTER, count=1, slave=self._slave_id
                    )
                    if result.isError():
                        raise IOError(str(result))
                    raw = result.registers[0]
                    angle = raw / ANGLE_SCALE
                    on_reading(AngleReading(angle_deg=angle, timestamp=time.time()))
                except Exception as exc:  # noqa: BLE001 - reporta e segue tentando
                    if on_error:
                        on_error(f"Erro de leitura Modbus: {exc}")
                self._stop_event.wait(self._poll_interval)
        finally:
            client.close()
