"""Fonte de dados real: leitura do ângulo via Bluetooth Low Energy (BLE),
usando o adaptador Bluetooth do próprio notebook (sem precisar de cabo até
o ESP32, diferente do modo USB/Modbus RTU).

Contrato assumido com o firmware do ESP32 (ainda não implementado nesta
fase) — o mesmo usado pelo app Android, para manter os transportes
consistentes:
- Serviço `SERVICE_UUID`, característica `ANGLE_CHARACTERISTIC_UUID` com
  notify (e read) de 2 bytes little-endian (int16, **com sinal**, faixa
  -60.00° a +60.00°) igual a `angulo * ANGLE_SCALE`.
- Azimute (pan): característica `PAN_CHARACTERISTIC_UUID`, mesmo formato de
  2 bytes, notificada na mesma cadência. É uma característica separada da de
  tilt de propósito — assim um app antigo, que só conhece a de tilt, continua
  funcionando contra o firmware novo. Como são duas notificações distintas, o
  app usa a de tilt como gatilho e junta o último valor de pan recebido: as
  duas chegam na mesma iteração do firmware, então a defasagem é de no
  máximo um ciclo de notify (~200ms) e só em caso de pacote perdido.
  Firmware anterior à v1.2.0 não tem essa característica — o `start_notify`
  falha, o app segue só com o tilt e `pan_deg` fica `None`.
- Extremos (mín/máx de cada eixo): característica `PEAKS_CHARACTERISTIC_UUID`,
  8 bytes = 4 int16 LE na escala do ângulo — tilt mín, tilt máx, pan mín, pan
  máx. Quem os mede é o firmware, e não o app, porque ele vê o sensor a
  100 Hz enquanto o notify chega a 5 Hz: uma rajada de vento de meio segundo
  acontece inteira entre duas notificações. O firmware só notifica quando o
  valor muda (extremo fica parado quase o tempo todo), então o último pacote
  recebido continua valendo. Firmware anterior à v1.5.0 não tem essa
  característica — o app volta a calcular os extremos a partir das leituras.
- Reset dos extremos: escrever `0x01` em `RESET_PEAKS_CHARACTERISTIC_UUID`
  faz o firmware esquecê-los sem mexer no zero.
- Calibração: escrever o byte `0x01` na característica
  `CALIBRATE_CHARACTERISTIC_UUID` sinaliza ao firmware para zerar **os dois
  eixos** na posição atual (equivalente à coil Modbus usada no modo USB), o
  que zera os extremos junto.
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
  - O eixo de **pan** vem em `VIBRATION_PAN_DATA_CHARACTERISTIC_UUID`, com o
    mesmo formato de pacote, mas carregando **velocidade angular em graus/s**
    * `PAN_RATE_SCALE`, e não ângulo (ver `firmware/src/VibrationCapture.h`
    para o porquê); `limits.vibration_stats.pan_rates_to_angles` faz a
    conversão. O firmware envia todos os pacotes de tilt, depois todos os de
    pan, e só então notifica "pronto". Firmware anterior à v1.3.0 não tem
    essa característica — a captura sai só com o tilt.
- Versão do firmware: `FIRMWARE_VERSION_CHARACTERISTIC_UUID`, read-only,
  2 bytes little-endian = `major*10000 + minor*100 + patch` (ex: "1.0.0" ->
  10000). Valor fixo (não muda em runtime, sem notify).

Usa a biblioteca `bleak` (multiplataforma: Windows/Linux/macOS), importada
localmente para não exigir a dependência quando só o modo simulado ou
USB/Modbus RTU forem usados.
"""
from __future__ import annotations

import asyncio
import struct
import threading
import time
from typing import NamedTuple

from data_source.base import (
    AngleReading,
    ErrorCallback,
    IAngleDataSource,
    ReadingCallback,
    build_vibration_readings,
)

SERVICE_UUID = "6e6e0001-3c17-4a2e-8f4b-1a2b3c4d5e6f"
ANGLE_CHARACTERISTIC_UUID = "6e6e0002-3c17-4a2e-8f4b-1a2b3c4d5e6f"
CALIBRATE_CHARACTERISTIC_UUID = "6e6e0003-3c17-4a2e-8f4b-1a2b3c4d5e6f"
VIBRATION_CONFIG_CHARACTERISTIC_UUID = "6e6e0004-3c17-4a2e-8f4b-1a2b3c4d5e6f"
VIBRATION_STATUS_CHARACTERISTIC_UUID = "6e6e0005-3c17-4a2e-8f4b-1a2b3c4d5e6f"
VIBRATION_DATA_CHARACTERISTIC_UUID = "6e6e0006-3c17-4a2e-8f4b-1a2b3c4d5e6f"
FIRMWARE_VERSION_CHARACTERISTIC_UUID = "6e6e0007-3c17-4a2e-8f4b-1a2b3c4d5e6f"
PAN_CHARACTERISTIC_UUID = "6e6e0008-3c17-4a2e-8f4b-1a2b3c4d5e6f"
VIBRATION_PAN_DATA_CHARACTERISTIC_UUID = "6e6e0009-3c17-4a2e-8f4b-1a2b3c4d5e6f"
PEAKS_CHARACTERISTIC_UUID = "6e6e000a-3c17-4a2e-8f4b-1a2b3c4d5e6f"
RESET_PEAKS_CHARACTERISTIC_UUID = "6e6e000b-3c17-4a2e-8f4b-1a2b3c4d5e6f"
ANGLE_SCALE = 100.0
PAN_RATE_SCALE = 100.0  # amostra = graus/s * 100 (int16, faixa +-327°/s)
# Quanto tempo os extremos vindos do dispositivo são ignorados após um pedido
# de reset. Só precisa cobrir a latência de uma notificação BLE em trânsito —
# ver `BleAngleSource.reset_peaks`.
PEAKS_RESET_GRACE_S = 1.0
CONNECT_TIMEOUT_S = 10.0
VIBRATION_TIMEOUT_MARGIN_S = 30.0


def _decode_angle(raw: bytearray | bytes) -> float:
    if len(raw) < 2:
        raise IOError("Resposta BLE inválida (esperado ao menos 2 bytes).")
    raw_value = raw[0] | (raw[1] << 8)
    return _to_signed16(raw_value) / ANGLE_SCALE


def _decode_peaks(raw: bytearray | bytes) -> tuple[float, float, float, float]:
    """Decodifica o pacote de extremos: 4 int16 LE — tilt mín, tilt máx,
    pan mín, pan máx — todos em `graus * ANGLE_SCALE`."""
    if len(raw) < 8:
        raise IOError("Pacote de extremos BLE inválido (esperado ao menos 8 bytes).")
    values = tuple(
        _to_signed16(raw[i * 2] | (raw[i * 2 + 1] << 8)) / ANGLE_SCALE for i in range(4)
    )
    return values  # type: ignore[return-value]


def _to_signed16(raw: int) -> int:
    return raw - 0x10000 if raw >= 0x8000 else raw


def _decode_firmware_version(raw: bytearray | bytes) -> str:
    if len(raw) < 2:
        return "?"
    code = raw[0] | (raw[1] << 8)
    major = code // 10000
    minor = (code // 100) % 100
    patch = code % 100
    return f"{major}.{minor}.{patch}"


class ConnectionTestResult(NamedTuple):
    angle_deg: float
    firmware_version: str
    pan_deg: float | None = None


def test_connection(device_address: str, timeout_s: float = 8.0) -> ConnectionTestResult:
    """Testa a conexão BLE com o ESP32: conecta, lê os ângulos e a versão do
    firmware uma única vez, e desconecta. Retorna tudo em caso de sucesso;
    levanta exceção em caso de falha."""
    from bleak import BleakClient

    async def _test() -> ConnectionTestResult:
        async with BleakClient(device_address, timeout=timeout_s) as client:
            raw = await client.read_gatt_char(ANGLE_CHARACTERISTIC_UUID)
            angle_deg = _decode_angle(raw)
            try:
                version_raw = await client.read_gatt_char(FIRMWARE_VERSION_CHARACTERISTIC_UUID)
                firmware_version = _decode_firmware_version(version_raw)
            except Exception:  # noqa: BLE001 - diagnóstico secundário, não deve derrubar o teste
                firmware_version = "?"
            try:
                pan_deg = _decode_angle(await client.read_gatt_char(PAN_CHARACTERISTIC_UUID))
            except Exception:  # noqa: BLE001 - firmware anterior à v1.2.0 não tem o eixo de pan
                pan_deg = None
            return ConnectionTestResult(angle_deg, firmware_version, pan_deg)

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

        # Extremos medidos pelo firmware (v1.5.0+). `_peaks_ignore_until` é o
        # fim da janela de graça após um reset — ver `_handle_notify`.
        self._peaks_subscribed = False
        self._peaks_ignore_until = 0.0

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
    def supports_peak_reset(self) -> bool:
        return self._peaks_subscribed

    def reset_peaks(self) -> None:
        """Manda o ESP32 esquecer os extremos dos dois eixos, sem mexer no zero.

        Bloqueante — deve ser chamado fora da thread da UI.
        """
        if not self._peaks_subscribed:
            return
        if self._loop is None or self._client is None:
            raise RuntimeError("Não conectado ao dispositivo.")

        # Abre a janela de graça ANTES da escrita: qualquer notificação com os
        # extremos antigos que chegue daqui em diante é descartada. Ver
        # `_handle_notify`.
        self._peaks_ignore_until = time.monotonic() + PEAKS_RESET_GRACE_S
        future = asyncio.run_coroutine_threadsafe(
            self._client.write_gatt_char(RESET_PEAKS_CHARACTERISTIC_UUID, bytes([0x01]), response=True),
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
        pan_samples: dict[int, int] = {}
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

        def _decode_packet_into(target: dict[int, int], raw: bytearray) -> None:
            if len(raw) < 4:
                return
            start_index = raw[0] | (raw[1] << 8)
            payload = raw[2:]
            for i in range(0, len(payload) - 1, 2):
                raw_value = payload[i] | (payload[i + 1] << 8)
                target[start_index + i // 2] = _to_signed16(raw_value)

        def _on_data(_characteristic, raw: bytearray) -> None:
            _decode_packet_into(samples, raw)

        def _on_pan_data(_characteristic, raw: bytearray) -> None:
            _decode_packet_into(pan_samples, raw)

        client = self._client
        pan_subscribed = False
        try:
            await client.start_notify(VIBRATION_STATUS_CHARACTERISTIC_UUID, _on_status)
            await client.start_notify(VIBRATION_DATA_CHARACTERISTIC_UUID, _on_data)
            try:
                await client.start_notify(VIBRATION_PAN_DATA_CHARACTERISTIC_UUID, _on_pan_data)
                pan_subscribed = True
            except Exception:  # noqa: BLE001 - firmware anterior à v1.3.0: segue só com o tilt
                pan_subscribed = False

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
            angles = [samples[i] / ANGLE_SCALE for i in sorted(samples)]
            pan_rates = (
                [pan_samples[i] / PAN_RATE_SCALE for i in sorted(pan_samples)] if pan_samples else None
            )
            on_done(build_vibration_readings(angles, pan_rates, rate_hz, t_start), None)
        except Exception as exc:  # noqa: BLE001
            on_done(None, f"Erro BLE na captura de vibração: {exc}")
        finally:
            try:
                await client.stop_notify(VIBRATION_STATUS_CHARACTERISTIC_UUID)
                await client.stop_notify(VIBRATION_DATA_CHARACTERISTIC_UUID)
                if pan_subscribed:
                    await client.stop_notify(VIBRATION_PAN_DATA_CHARACTERISTIC_UUID)
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

        # Último pan recebido, para ser anexado à próxima notificação de tilt
        # (ver o cabeçalho do módulo). Fica em lista para poder ser escrito de
        # dentro dos callbacks aninhados sem `nonlocal`.
        last_pan: list[float | None] = [None]

        # Idem para os extremos: chegam numa característica própria e num
        # pacote só, e o firmware só os notifica quando mudam — então o último
        # recebido continua valendo entre notificações.
        last_peaks: list[tuple[float, float, float, float] | None] = [None]

        def _handle_pan_notify(_characteristic, raw: bytearray) -> None:
            try:
                last_pan[0] = _decode_angle(raw)
            except Exception:  # noqa: BLE001 - notificação malformada, ignora
                return

        def _handle_peaks_notify(_characteristic, raw: bytearray) -> None:
            try:
                last_peaks[0] = _decode_peaks(raw)
            except Exception:  # noqa: BLE001 - notificação malformada, ignora
                return

        def _handle_notify(_characteristic, raw: bytearray) -> None:
            try:
                angle = _decode_angle(raw)
            except Exception:  # noqa: BLE001 - notificação malformada, ignora
                return

            # Descarta os extremos durante a janela de graça após um reset:
            # a escrita BLE é assíncrona, então uma notificação com os valores
            # ANTIGOS pode estar em trânsito. Como mín/máx só andam para fora,
            # um único pacote atrasado envenenaria a faixa nova de forma
            # permanente. Nessa janela o app usa a própria leitura, que é o
            # comportamento correto e temporário.
            peaks = last_peaks[0]
            if peaks is not None and time.monotonic() < self._peaks_ignore_until:
                peaks = None

            on_reading(
                AngleReading(
                    angle_deg=angle,
                    pan_deg=last_pan[0],
                    timestamp=time.time(),
                    angle_min_deg=peaks[0] if peaks else None,
                    angle_max_deg=peaks[1] if peaks else None,
                    pan_min_deg=peaks[2] if peaks else None,
                    pan_max_deg=peaks[3] if peaks else None,
                )
            )

        try:
            async with BleakClient(self._device_address, timeout=CONNECT_TIMEOUT_S) as client:
                self._client = client
                await client.start_notify(ANGLE_CHARACTERISTIC_UUID, _handle_notify)

                # Firmware anterior à v1.2.0 não expõe o eixo de pan: seguir
                # só com o tilt é melhor que derrubar a sessão inteira.
                pan_subscribed = False
                try:
                    await client.start_notify(PAN_CHARACTERISTIC_UUID, _handle_pan_notify)
                    pan_subscribed = True
                except Exception:  # noqa: BLE001
                    if on_error:
                        on_error("Firmware sem eixo de azimute (pan) — seguindo só com a inclinação.")

                # Firmware anterior à v1.5.0 não mede os extremos: o app volta
                # a calculá-los a partir das leituras. Sem aviso na UI, porque
                # nada some da tela — só a fidelidade em eventos curtos cai.
                try:
                    await client.start_notify(PEAKS_CHARACTERISTIC_UUID, _handle_peaks_notify)
                    self._peaks_subscribed = True
                except Exception:  # noqa: BLE001
                    self._peaks_subscribed = False

                while not self._stop_event.is_set():
                    await asyncio.sleep(0.2)

                if self._peaks_subscribed:
                    await client.stop_notify(PEAKS_CHARACTERISTIC_UUID)
                if pan_subscribed:
                    await client.stop_notify(PAN_CHARACTERISTIC_UUID)
                await client.stop_notify(ANGLE_CHARACTERISTIC_UUID)
        except Exception as exc:  # noqa: BLE001
            if on_error:
                on_error(f"Erro BLE: {exc}")
        finally:
            self._client = None
            self._peaks_subscribed = False
