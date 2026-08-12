"""Fonte de dados real: leitura do ângulo via Bluetooth Low Energy (BLE),
usando o adaptador Bluetooth do próprio notebook (sem necessidade de
dongle RS485).

Contrato assumido com o firmware do ESP32 (ainda não implementado nesta
fase) — o mesmo usado pelo app Android, para manter os transportes
consistentes:
- Serviço `SERVICE_UUID`, característica `ANGLE_CHARACTERISTIC_UUID` com
  notify (e read) de 2 bytes little-endian igual a `angulo * ANGLE_SCALE`.
- Calibração: escrever o byte `0x01` na característica
  `CALIBRATE_CHARACTERISTIC_UUID` sinaliza ao firmware para zerar o eixo de
  tilt na posição atual (equivalente à coil Modbus usada no modo RS485).
- Captura de vibração (leitura em alta taxa, para caracterizar variação
  angular por vento/vibração — o notify normal já é "tempo real", mas numa
  taxa que depende do firmware; este modo pede uma taxa/duração explícitas):
  contrato assumido, a confirmar quando o firmware existir.
  - App escreve 4 bytes little-endian em `VIBRATION_CONFIG_CHARACTERISTIC_UUID`
    — `duration_s` (uint16) + `rate_hz` (uint16) — para configurar e iniciar.
  - Firmware notifica em `VIBRATION_STATUS_CHARACTERISTIC_UUID`: byte 0 =
    status (0=ocioso, 1=capturando, 2=pronto, 3=erro), byte 1 = progresso
    (0-100); quando status=pronto, inclui ainda bytes 2-3 = total de
    amostras (uint16 LE).
  - Firmware envia os dados em `VIBRATION_DATA_CHARACTERISTIC_UUID`, em
    pacotes de notify: bytes 0-1 = índice inicial do pacote (uint16 LE),
    restante = amostras sequenciais (int16 LE, **com sinal**, ângulo * 100),
    quantas couberem no MTU — repete até cobrir o total informado.

Usa a biblioteca `bleak` (multiplataforma: Windows/Linux/macOS), importada
localmente para não exigir a dependência quando só o modo simulado ou RS485
forem usados.
"""
from __future__ import annotations

import asyncio
import struct
import threading
import time

from data_source.base import AngleReading, ErrorCallback, IAngleDataSource, ReadingCallback

SERVICE_UUID = "6e6e0001-3c17-4a2e-8f4b-1a2b3c4d5e6f"
ANGLE_CHARACTERISTIC_UUID = "6e6e0002-3c17-4a2e-8f4b-1a2b3c4d5e6f"
CALIBRATE_CHARACTERISTIC_UUID = "6e6e0003-3c17-4a2e-8f4b-1a2b3c4d5e6f"
VIBRATION_CONFIG_CHARACTERISTIC_UUID = "6e6e0004-3c17-4a2e-8f4b-1a2b3c4d5e6f"
VIBRATION_STATUS_CHARACTERISTIC_UUID = "6e6e0005-3c17-4a2e-8f4b-1a2b3c4d5e6f"
VIBRATION_DATA_CHARACTERISTIC_UUID = "6e6e0006-3c17-4a2e-8f4b-1a2b3c4d5e6f"
ANGLE_SCALE = 100.0
CONNECT_TIMEOUT_S = 10.0
VIBRATION_TIMEOUT_MARGIN_S = 30.0


def _decode_angle(raw: bytearray | bytes) -> float:
    if len(raw) < 2:
        raise IOError("Resposta BLE inválida (esperado ao menos 2 bytes).")
    raw_value = raw[0] | (raw[1] << 8)
    return raw_value / ANGLE_SCALE


def _to_signed16(raw: int) -> int:
    return raw - 0x10000 if raw >= 0x8000 else raw


def test_connection(device_address: str, timeout_s: float = 8.0) -> float:
    """Testa a conexão BLE com o ESP32: conecta, lê o ângulo uma vez e
    desconecta. Retorna o ângulo lido (°) em caso de sucesso; levanta
    exceção em caso de falha."""
    from bleak import BleakClient

    async def _test() -> float:
        async with BleakClient(device_address, timeout=timeout_s) as client:
            raw = await client.read_gatt_char(ANGLE_CHARACTERISTIC_UUID)
            return _decode_angle(raw)

    return asyncio.run(_test())


def scan_devices(timeout_s: float = 5.0) -> list[tuple[str, str]]:
    """Varre dispositivos BLE próximos usando o Bluetooth do notebook.
    Retorna lista de (endereço, nome)."""
    from bleak import BleakScanner

    async def _scan() -> list[tuple[str, str]]:
        devices = await BleakScanner.discover(timeout=timeout_s)
        return [(d.address, d.name or "(sem nome)") for d in devices]

    return asyncio.run(_scan())


class BleAngleSource(IAngleDataSource):
    def __init__(self, device_address: str) -> None:
        self._device_address = device_address

        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._client = None

    @property
    def label(self) -> str:
        return f"Bluetooth BLE ({self._device_address})"

    @property
    def supports_calibration(self) -> bool:
        return True

    def calibrate(self) -> None:
        """Envia o comando de calibração (zerar tilt) ao ESP32 via BLE.

        Bloqueante — deve ser chamado fora da thread da UI. Levanta
        `RuntimeError`/`IOError` se não estiver conectado ou se a escrita falhar.
        """
        if self._loop is None or self._client is None:
            raise RuntimeError("Não conectado ao dispositivo.")
        future = asyncio.run_coroutine_threadsafe(
            self._client.write_gatt_char(CALIBRATE_CHARACTERISTIC_UUID, bytes([0x01]), response=True),
            self._loop,
        )
        future.result(timeout=5.0)

    @property
    def supports_vibration_capture(self) -> bool:
        return True

    def start_vibration_capture(self, duration_s: float, rate_hz: float, on_progress, on_done) -> None:
        if self._loop is None or self._client is None:
            on_done(None, "Não conectado ao dispositivo.")
            return
        asyncio.run_coroutine_threadsafe(
            self._run_vibration_capture_async(duration_s, rate_hz, on_progress, on_done),
            self._loop,
        )

    def stop_vibration_capture(self) -> None:
        # Cancelamento cooperativo ainda não faz parte do contrato BLE
        # assumido: a captura roda até o firmware concluir/errar ou até o
        # timeout local (duration_s + VIBRATION_TIMEOUT_MARGIN_S) estourar.
        return

    async def _run_vibration_capture_async(self, duration_s: float, rate_hz: float, on_progress, on_done) -> None:
        samples: dict[int, int] = {}
        total_expected: list[int] = []
        error_holder: list[str] = []
        done_event = asyncio.Event()

        def _on_status(_characteristic, raw: bytearray) -> None:
            if len(raw) < 2:
                return
            status, progress = raw[0], raw[1]
            if status == 1:
                on_progress(float(progress))
            elif status == 2:
                if len(raw) >= 4:
                    total_expected.append(raw[2] | (raw[3] << 8))
                done_event.set()
            elif status == 3:
                error_holder.append("Firmware reportou erro durante a captura de vibração.")
                done_event.set()

        def _on_data(_characteristic, raw: bytearray) -> None:
            if len(raw) < 4:
                return
            start_index = raw[0] | (raw[1] << 8)
            payload = raw[2:]
            for i in range(0, len(payload) - 1, 2):
                raw_value = payload[i] | (payload[i + 1] << 8)
                samples[start_index + i // 2] = _to_signed16(raw_value)

        client = self._client
        try:
            await client.start_notify(VIBRATION_STATUS_CHARACTERISTIC_UUID, _on_status)
            await client.start_notify(VIBRATION_DATA_CHARACTERISTIC_UUID, _on_data)

            config = struct.pack("<HH", int(duration_s), int(rate_hz))
            await client.write_gatt_char(VIBRATION_CONFIG_CHARACTERISTIC_UUID, config, response=True)

            try:
                await asyncio.wait_for(done_event.wait(), timeout=duration_s + VIBRATION_TIMEOUT_MARGIN_S)
            except asyncio.TimeoutError:
                on_done(None, "Tempo esgotado aguardando a captura de vibração.")
                return

            if error_holder:
                on_done(None, error_holder[0])
                return

            sample_count = total_expected[0] if total_expected else len(samples)
            t_start = time.time() - sample_count / rate_hz
            readings = [
                AngleReading(angle_deg=samples[i] / ANGLE_SCALE, timestamp=t_start + i / rate_hz)
                for i in sorted(samples)
            ]
            on_done(readings, None)
        except Exception as exc:  # noqa: BLE001
            on_done(None, f"Erro BLE na captura de vibração: {exc}")
        finally:
            try:
                await client.stop_notify(VIBRATION_STATUS_CHARACTERISTIC_UUID)
                await client.stop_notify(VIBRATION_DATA_CHARACTERISTIC_UUID)
            except Exception:  # noqa: BLE001 - já desconectado/encerrando
                pass

    def start(self, on_reading: ReadingCallback, on_error: ErrorCallback | None = None) -> None:
        if self._thread is not None:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_thread, args=(on_reading, on_error), daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None

    def _run_thread(self, on_reading: ReadingCallback, on_error: ErrorCallback | None) -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        self._loop = loop
        try:
            loop.run_until_complete(self._run_async(on_reading, on_error))
        finally:
            self._loop = None
            loop.close()

    async def _run_async(self, on_reading: ReadingCallback, on_error: ErrorCallback | None) -> None:
        from bleak import BleakClient

        def _handle_notify(_characteristic, raw: bytearray) -> None:
            try:
                angle = _decode_angle(raw)
            except Exception:  # noqa: BLE001 - notificação malformada, ignora
                return
            on_reading(AngleReading(angle_deg=angle, timestamp=time.time()))

        try:
            async with BleakClient(self._device_address, timeout=CONNECT_TIMEOUT_S) as client:
                self._client = client
                await client.start_notify(ANGLE_CHARACTERISTIC_UUID, _handle_notify)
                while not self._stop_event.is_set():
                    await asyncio.sleep(0.2)
                await client.stop_notify(ANGLE_CHARACTERISTIC_UUID)
        except Exception as exc:  # noqa: BLE001
            if on_error:
                on_error(f"Erro BLE: {exc}")
        finally:
            self._client = None
