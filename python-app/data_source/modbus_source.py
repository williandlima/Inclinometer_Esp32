"""Fonte de dados real: leitura do ângulo via Modbus RTU, pela porta serial
USB do ESP32 (conectado direto por cabo — sem RS485).

Usa o kwarg `device_id=` do pymodbus (renomeado de `slave=` nas versões mais
recentes da lib) — por isso `requirements.txt` trava `pymodbus==3.14.0`
exatamente: sem essa trava, um `pip install` puxando uma versão diferente
pode voltar a quebrar com `unexpected keyword argument`.

Contrato com o firmware do ESP32: a inclinação (tilt) é exposta no
registrador de entrada (input register) `ANGLE_INPUT_REGISTER` e o azimute
(pan) em `PAN_INPUT_REGISTER`, ambos como inteiro de 16 bits **com sinal**
igual a `angulo * SCALE` (duas casas decimais de resolução). Por serem
registradores contíguos, os dois eixos são lidos numa única transação. O
rastreamento de mínimo/máximo é feito no próprio app
(`limits.limit_tracker`), não depende de registradores extras no escravo —
assim o contrato Modbus fica mínimo e estável.

Compatibilidade com firmware anterior à v1.2.0 (que não tem o eixo de pan):
aquele firmware responde com exceção de "endereço inválido" ao ver o
registrador 1, derrubando a leitura dos dois eixos junto. Por isso a leitura
começa pedindo os dois registradores e, se o escravo responder com uma
*exceção Modbus*, passa a pedir só o de tilt dali em diante, com `pan_deg`
ficando `None`. A degradação é só para exceção do escravo — erro de
transporte (timeout, CRC) não desabilita o pan, senão uma falha passageira
de cabo deixaria o eixo desligado pelo resto da sessão.

Calibração: escrever `True` na coil `CALIBRATE_COIL` sinaliza ao firmware
para zerar **os dois eixos** na posição atual (novo "zero" mecânico).

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
from typing import NamedTuple

from data_source.base import AngleReading, ErrorCallback, IAngleDataSource, ReadingCallback

# Muitas placas ESP32 (incluindo a usada neste projeto, com chip CH9102)
# resetam a placa via DTR/RTS toda vez que a porta serial é aberta — é o
# mesmo mecanismo de auto-reset usado para gravar o firmware sem apertar
# botão. Isso significa que CADA conexão nova (não só a primeira do app)
# reinicia o ESP32, que leva um tempo pra voltar a responder Modbus:
# inicialização de I2C + do stack BLE do firmware (BLEDevice::init) pode
# levar bem mais que 1s. Sem essa folga, a primeira leitura logo após
# conectar falha com timeout mesmo com o hardware saudável.
BOARD_RESET_GRACE_S = 2.5

ANGLE_INPUT_REGISTER = 0
PAN_INPUT_REGISTER = 1  # contíguo ao de tilt de propósito: os dois saem numa leitura só
ANGLE_SCALE = 100.0  # registrador = ângulo * 100 (int16, resolução de 0.01°)
CALIBRATE_COIL = 0
FIRMWARE_VERSION_REGISTER = 40  # registrador = major*10000 + minor*100 + patch (ex: "1.0.0" -> 10000)

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


def _decode_firmware_version(code: int) -> str:
    major = code // 10000
    minor = (code // 100) % 100
    patch = code % 100
    return f"{major}.{minor}.{patch}"


def _is_slave_exception(result) -> bool:
    """True se o escravo respondeu com uma exceção Modbus (ex: endereço
    inválido), em vez de a transação ter falhado no transporte (timeout, CRC).

    Checa o atributo em vez de importar `ExceptionResponse` porque o caminho
    de import dessa classe já mudou entre versões do pymodbus.
    """
    return getattr(result, "exception_code", None) is not None


def _read_axes(client, slave_id: int, pan_supported: bool) -> tuple[float, float | None, bool]:
    """Lê tilt (e pan, quando disponível) do escravo.

    Retorna `(angle_deg, pan_deg | None, pan_supported)` — o terceiro item é
    o valor atualizado da flag, que fica `False` depois que o escravo rejeita
    o registrador de pan (firmware anterior à v1.2.0). Levanta `IOError` em
    falha de transporte.
    """
    if pan_supported:
        result = client.read_input_registers(
            address=ANGLE_INPUT_REGISTER, count=2, device_id=slave_id
        )
        if not result.isError():
            return (
                _to_signed16(result.registers[0]) / ANGLE_SCALE,
                _to_signed16(result.registers[1]) / ANGLE_SCALE,
                True,
            )
        if not _is_slave_exception(result):
            raise IOError(str(result))
        pan_supported = False  # firmware sem eixo de pan: segue só com o tilt

    result = client.read_input_registers(address=ANGLE_INPUT_REGISTER, count=1, device_id=slave_id)
    if result.isError():
        raise IOError(str(result))
    return _to_signed16(result.registers[0]) / ANGLE_SCALE, None, pan_supported


class ConnectionTestResult(NamedTuple):
    angle_deg: float
    firmware_version: str
    pan_deg: float | None = None


def test_connection(port: str, baudrate: int, slave_id: int, timeout_s: float = 1.0) -> ConnectionTestResult:
    """Testa a conexão Modbus RTU (via USB) com o ESP32: abre a porta, lê o
    ângulo e a versão do firmware uma única vez, e fecha a conexão. Retorna
    ambos em caso de sucesso; levanta exceção (IOError/RuntimeError) em caso
    de falha.
    """
    from pymodbus.client import ModbusSerialClient

    client = ModbusSerialClient(port=port, baudrate=baudrate, timeout=timeout_s)
    try:
        if not client.connect():
            raise IOError(f"Não foi possível abrir a porta serial {port}.")
        time.sleep(BOARD_RESET_GRACE_S)  # ver BOARD_RESET_GRACE_S: a porta abrir já reseta o ESP32
        angle_deg, pan_deg, _ = _read_axes(client, slave_id, pan_supported=True)

        version_result = client.read_input_registers(address=FIRMWARE_VERSION_REGISTER, count=1, device_id=slave_id)
        firmware_version = (
            _decode_firmware_version(version_result.registers[0]) if not version_result.isError() else "?"
        )

        return ConnectionTestResult(angle_deg, firmware_version, pan_deg)
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

        # Vira False se o escravo rejeitar o registrador de pan (firmware
        # anterior à v1.2.0) — ver o cabeçalho do módulo.
        self._pan_supported = True

    @property
    def label(self) -> str:
        return f"USB/Modbus RTU ({self._port}@{self._baudrate}, id={self._slave_id})"

    @property
    def supports_calibration(self) -> bool:
        return True

    def calibrate(self) -> None:
        """Envia o comando de calibração (zera tilt e pan) ao escravo Modbus.

        Bloqueante — deve ser chamado fora da thread da UI. Levanta
        `RuntimeError`/`IOError` se não estiver conectado ou se a escrita falhar.
        """
        with self._client_lock:
            if self._client is None:
                raise RuntimeError("Não conectado ao dispositivo.")
            result = self._client.write_coil(address=CALIBRATE_COIL, value=True, device_id=self._slave_id)
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
                r1 = client.write_register(address=VIBRATION_DURATION_REG, value=int(duration_s), device_id=self._slave_id)
                r2 = client.write_register(address=VIBRATION_RATE_REG, value=int(rate_hz), device_id=self._slave_id)
                r3 = client.write_coil(address=VIBRATION_START_COIL, value=True, device_id=self._slave_id)
                if r1.isError() or r2.isError() or r3.isError():
                    raise IOError("Falha ao configurar/iniciar a captura de vibração no dispositivo.")

            sample_count = 0
            while True:
                if self._vibration_stop_event.is_set():
                    on_done(None, "Captura cancelada pelo usuário.")
                    return
                with self._client_lock:
                    status_result = client.read_input_registers(
                        address=VIBRATION_STATUS_REG, count=3, device_id=self._slave_id
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
                        address=VIBRATION_CURSOR_REG, value=index, device_id=self._slave_id
                    )
                    if cursor_result.isError():
                        raise IOError(str(cursor_result))
                    block_result = client.read_input_registers(
                        address=VIBRATION_BLOCK_START_REG, count=block_size, device_id=self._slave_id
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
        # simulado for usado (ex: ambiente de desenvolvimento sem o ESP32 conectado).
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

            # Ver BOARD_RESET_GRACE_S: a porta abrir já reseta o ESP32 — sem
            # essa folga, a primeira leitura falharia com timeout mesmo com o
            # hardware saudável. Usa wait() em vez de sleep() pra "Parar"
            # continuar responsivo mesmo durante essa espera inicial.
            self._stop_event.wait(BOARD_RESET_GRACE_S)

            while not self._stop_event.is_set():
                try:
                    with self._client_lock:
                        angle, pan, self._pan_supported = _read_axes(
                            client, self._slave_id, self._pan_supported
                        )
                    on_reading(AngleReading(angle_deg=angle, pan_deg=pan, timestamp=time.time()))
                except Exception as exc:  # noqa: BLE001 - reporta e segue tentando
                    if on_error:
                        on_error(f"Erro de leitura Modbus: {exc}")
                self._stop_event.wait(self._poll_interval)
        finally:
            with self._client_lock:
                self._client = None
            client.close()
