"""Fonte de dados real: leitura do ângulo via RS485/Modbus RTU.

Contrato assumido com o firmware do ESP32 (ainda não implementado nesta
fase): o ângulo atual é exposto no registrador de entrada (input register)
`ANGLE_INPUT_REGISTER`, como inteiro de 16 bits igual a `angulo * SCALE`
(duas casas decimais de resolução). O rastreamento de mínimo/máximo é feito
no próprio app (`limits.limit_tracker`), não depende de registradores extras
no escravo — assim o contrato Modbus fica mínimo e estável mesmo antes do
firmware existir.

Calibração: escrever `True` na coil `CALIBRATE_COIL` sinaliza ao firmware
para zerar o eixo de tilt do acelerômetro na posição atual (novo "zero"
mecânico). Contrato assumido, a confirmar quando o firmware existir.

Captura de vibração (leitura em alta taxa, usada para caracterizar variação
angular por vento/vibração — o poll normal de ~250ms é lento demais para
isso): contrato assumido, a confirmar quando o firmware existir.
- App escreve `duration_s` em `VIBRATION_DURATION_REG` e `rate_hz` em
  `VIBRATION_RATE_REG`, depois escreve `True` na coil `VIBRATION_START_COIL`
  para iniciar. O firmware passa a amostrar internamente na taxa pedida e
  guarda o buffer em memória.
- App faz poll de `VIBRATION_STATUS_REG` (0=ocioso, 1=capturando, 2=pronto,
  3=erro), `VIBRATION_PROGRESS_REG` (0-100) e `VIBRATION_SAMPLE_COUNT_REG`
  (total de amostras, válido quando status=pronto).
- Quando pronto, app lê o buffer em blocos: escreve o índice inicial em
  `VIBRATION_CURSOR_REG`, depois lê `VIBRATION_BLOCK_SIZE` registradores a
  partir de `VIBRATION_BLOCK_START_REG` (cada um = ângulo relativo ao "zero"
  calibrado * `ANGLE_SCALE`, inteiro **com sinal** de 16 bits, já que a
  variação pode ser negativa) — repete até completar `VIBRATION_SAMPLE_COUNT_REG`.
"""
from __future__ import annotations

import threading
import time

from data_source.base import AngleReading, ErrorCallback, IAngleDataSource, ReadingCallback

ANGLE_INPUT_REGISTER = 0
ANGLE_SCALE = 100.0  # registrador = ângulo * 100 (int16, resolução de 0.01°)
CALIBRATE_COIL = 0

VIBRATION_START_COIL = 1
VIBRATION_DURATION_REG = 10  # segundos (uint16)
VIBRATION_RATE_REG = 11  # amostras/s (uint16)
VIBRATION_STATUS_REG = 20  # 0=ocioso, 1=capturando, 2=pronto, 3=erro
VIBRATION_PROGRESS_REG = 21  # percentual 0-100
VIBRATION_SAMPLE_COUNT_REG = 22  # total de amostras capturadas (válido quando status=pronto)
VIBRATION_CURSOR_REG = 30  # índice inicial do próximo bloco a ler (escrita)
VIBRATION_BLOCK_START_REG = 31  # início do bloco de amostras (leitura)
VIBRATION_BLOCK_SIZE = 32  # amostras por bloco de leitura
VIBRATION_STATUS_POLL_INTERVAL_S = 0.5


def _to_signed16(raw: int) -> int:
    return raw - 0x10000 if raw >= 0x8000 else raw


def test_connection(port: str, baudrate: int, slave_id: int, timeout_s: float = 1.0) -> float:
    """Testa a conexão RS485/Modbus RTU com o ESP32: abre a porta, faz uma
    única leitura do ângulo e fecha a conexão. Retorna o ângulo lido (°) em
    caso de sucesso; levanta exceção (IOError/RuntimeError) em caso de falha.
    """
    from pymodbus.client import ModbusSerialClient

    client = ModbusSerialClient(port=port, baudrate=baudrate, timeout=timeout_s)
    try:
        if not client.connect():
            raise IOError(f"Não foi possível abrir a porta serial {port}.")
        result = client.read_input_registers(address=ANGLE_INPUT_REGISTER, count=1, slave=slave_id)
        if result.isError():
            raise IOError(str(result))
        return result.registers[0] / ANGLE_SCALE
    finally:
        client.close()


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

        self._client_lock = threading.Lock()
        self._client = None

        self._vibration_thread: threading.Thread | None = None
        self._vibration_stop_event = threading.Event()

    @property
    def label(self) -> str:
        return f"RS485/Modbus RTU ({self._port}@{self._baudrate}, id={self._slave_id})"

    @property
    def supports_calibration(self) -> bool:
        return True

    def calibrate(self) -> None:
        """Envia o comando de calibração (zerar tilt) ao escravo Modbus.

        Bloqueante — deve ser chamado fora da thread da UI. Levanta
        `RuntimeError`/`IOError` se não estiver conectado ou se a escrita falhar.
        """
        with self._client_lock:
            if self._client is None:
                raise RuntimeError("Não conectado ao dispositivo.")
            result = self._client.write_coil(address=CALIBRATE_COIL, value=True, slave=self._slave_id)
            if result.isError():
                raise IOError(str(result))

    @property
    def supports_vibration_capture(self) -> bool:
        return True

    def start_vibration_capture(self, duration_s: float, rate_hz: float, on_progress, on_done) -> None:
        if self._vibration_thread is not None:
            return
        self._vibration_stop_event.clear()
        self._vibration_thread = threading.Thread(
            target=self._run_vibration_capture,
            args=(duration_s, rate_hz, on_progress, on_done),
            daemon=True,
        )
        self._vibration_thread.start()

    def stop_vibration_capture(self) -> None:
        self._vibration_stop_event.set()
        if self._vibration_thread is not None:
            self._vibration_thread.join(timeout=2.0)
            self._vibration_thread = None

    def _run_vibration_capture(self, duration_s: float, rate_hz: float, on_progress, on_done) -> None:
        try:
            with self._client_lock:
                if self._client is None:
                    raise RuntimeError("Não conectado ao dispositivo.")
                client = self._client
                r1 = client.write_register(address=VIBRATION_DURATION_REG, value=int(duration_s), slave=self._slave_id)
                r2 = client.write_register(address=VIBRATION_RATE_REG, value=int(rate_hz), slave=self._slave_id)
                r3 = client.write_coil(address=VIBRATION_START_COIL, value=True, slave=self._slave_id)
                if r1.isError() or r2.isError() or r3.isError():
                    raise IOError("Falha ao configurar/iniciar a captura de vibração no dispositivo.")

            sample_count = 0
            while True:
                if self._vibration_stop_event.is_set():
                    on_done(None, "Captura cancelada pelo usuário.")
                    return
                with self._client_lock:
                    status_result = client.read_input_registers(
                        address=VIBRATION_STATUS_REG, count=3, slave=self._slave_id
                    )
                if status_result.isError():
                    raise IOError(str(status_result))
                status, progress, sample_count = status_result.registers
                if status == 2:
                    break
                if status == 3:
                    raise IOError("Firmware reportou erro durante a captura de vibração.")
                on_progress(float(progress))
                self._vibration_stop_event.wait(VIBRATION_STATUS_POLL_INTERVAL_S)

            on_progress(100.0)
            capture_finished_at = time.time()
            t_start = capture_finished_at - sample_count / rate_hz

            readings: list[AngleReading] = []
            index = 0
            while index < sample_count:
                block_size = min(VIBRATION_BLOCK_SIZE, sample_count - index)
                with self._client_lock:
                    cursor_result = client.write_register(
                        address=VIBRATION_CURSOR_REG, value=index, slave=self._slave_id
                    )
                    if cursor_result.isError():
                        raise IOError(str(cursor_result))
                    block_result = client.read_input_registers(
                        address=VIBRATION_BLOCK_START_REG, count=block_size, slave=self._slave_id
                    )
                if block_result.isError():
                    raise IOError(str(block_result))
                for i, raw in enumerate(block_result.registers):
                    angle = _to_signed16(raw) / ANGLE_SCALE
                    readings.append(AngleReading(angle_deg=angle, timestamp=t_start + (index + i) / rate_hz))
                index += block_size

            on_done(readings, None)
        except Exception as exc:  # noqa: BLE001
            on_done(None, str(exc))
        finally:
            self._vibration_thread = None

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

            with self._client_lock:
                self._client = client

            while not self._stop_event.is_set():
                try:
                    with self._client_lock:
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
            with self._client_lock:
                self._client = None
            client.close()
