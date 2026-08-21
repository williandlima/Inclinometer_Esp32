"""Fonte de dados simulada: gera ângulos sintéticos sem hardware real.

Usada para desenvolver e testar o app sem o ESP32 conectado. Os dois eixos
são simulados com comportamentos deliberadamente diferentes, imitando o que
cada um faz de verdade:

- **Tilt**: oscilação senoidal contínua dentro da faixa -60° a +60°, somada a
  ruído gaussiano — é um eixo que se move o tempo todo (vento no mastro).
- **Pan**: fica parado a maior parte do tempo e se desloca em rajadas até uma
  nova posição, que é exatamente o padrão de uso real do azimute (e a razão
  de o firmware conseguir medi-lo por giroscópio + ZUPT). Sem ruído entre os
  movimentos, porque o ZUPT do firmware justamente congela a leitura
  enquanto o eixo está parado.
"""
from __future__ import annotations

import math
import random
import threading
import time

from data_source.base import (
    ANGLE_MAX_DEG,
    ANGLE_MIN_DEG,
    PAN_MAX_DEG,
    PAN_MIN_DEG,
    AngleReading,
    ErrorCallback,
    IAngleDataSource,
    ReadingCallback,
)

# Velocidade e cadência do pan simulado — na mesma ordem de grandeza do motor
# real (~20-30°/s em rajadas de poucos segundos).
PAN_MOVE_RATE_DPS = 20.0
PAN_HOLD_S = 12.0
# A primeira rajada sai bem antes do intervalo normal: com PAN_HOLD_S inteiro
# aqui, quem inicia a leitura ficaria 12s olhando um eixo cravado, com cara de
# app quebrado, antes de ver qualquer movimento.
PAN_FIRST_MOVE_S = 2.0


class SimulatedAngleSource(IAngleDataSource):
    def __init__(
        self,
        center_deg: float = 0.0,
        amplitude_deg: float = 12.0,
        period_s: float = 45.0,
        # Ruído equivalente ao que o firmware entrega JÁ FILTRADO (filtro
        # interno do MPU6050 + média móvel, ver firmware/src/AngleSensor.h).
        # A fonte simulada substitui o conjunto sensor+firmware, então imitar
        # o sinal cru aqui daria uma falsa impressão de instabilidade que o
        # hardware real não tem mais.
        noise_std_deg: float = 0.015,
        poll_interval_s: float = 0.25,
    ) -> None:
        self._center = center_deg
        self._amplitude = amplitude_deg
        self._period = period_s
        self._noise_std = noise_std_deg
        self._poll_interval = poll_interval_s

        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._t0 = 0.0

        self._lock = threading.Lock()
        self._offset_deg = 0.0
        self._last_raw_deg = center_deg

        # Estado do eixo de pan: posição atual, alvo do movimento em curso e
        # quando o próximo movimento começa.
        self._pan_raw_deg = 0.0
        self._pan_target_deg = 0.0
        self._pan_offset_deg = 0.0
        self._pan_next_move_at = 0.0
        self._pan_last_tick = 0.0

        self._vibration_thread: threading.Thread | None = None
        self._vibration_stop_event = threading.Event()

    @property
    def label(self) -> str:
        return "Simulação"

    @property
    def supports_calibration(self) -> bool:
        return True

    def calibrate(self) -> None:
        """Ajusta os offsets para que os próximos ângulos lidos sejam ~0°,
        simulando o zeramento dos dois eixos na posição atual — o firmware
        real também zera tilt e pan no mesmo comando."""
        with self._lock:
            self._offset_deg = self._last_raw_deg
            self._pan_offset_deg = self._pan_raw_deg

    def start(self, on_reading: ReadingCallback, on_error: ErrorCallback | None = None) -> None:
        if self._thread is not None:
            return
        self._stop_event.clear()
        self._t0 = time.time()
        self._pan_last_tick = self._t0
        self._pan_next_move_at = self._t0 + PAN_FIRST_MOVE_S
        self._thread = threading.Thread(target=self._run, args=(on_reading,), daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _advance_pan(self, now: float) -> float:
        """Avança o eixo de pan simulado e devolve o valor relativo ao zero
        calibrado. Move em direção ao alvo a PAN_MOVE_RATE_DPS; ao chegar,
        fica parado até a próxima rajada."""
        dt = max(0.0, now - self._pan_last_tick)
        self._pan_last_tick = now

        remaining = self._pan_target_deg - self._pan_raw_deg
        if abs(remaining) > 1e-6:
            step = PAN_MOVE_RATE_DPS * dt
            if step >= abs(remaining):
                self._pan_raw_deg = self._pan_target_deg
                self._pan_next_move_at = now + PAN_HOLD_S
            else:
                self._pan_raw_deg += math.copysign(step, remaining)
        elif now >= self._pan_next_move_at:
            self._pan_target_deg = random.uniform(PAN_MIN_DEG * 0.7, PAN_MAX_DEG * 0.7)

        return self._pan_raw_deg - self._pan_offset_deg

    def _run(self, on_reading: ReadingCallback) -> None:
        while not self._stop_event.is_set():
            now = time.time()
            elapsed = now - self._t0
            raw_angle = self._center + self._amplitude * math.sin(2 * math.pi * elapsed / self._period)
            raw_angle += random.gauss(0.0, self._noise_std)

            with self._lock:
                self._last_raw_deg = raw_angle
                angle = raw_angle - self._offset_deg
                pan = self._advance_pan(now)

            angle = max(ANGLE_MIN_DEG, min(ANGLE_MAX_DEG, angle))
            pan = max(PAN_MIN_DEG, min(PAN_MAX_DEG, pan))
            on_reading(AngleReading(angle_deg=angle, pan_deg=pan, timestamp=now))
            self._stop_event.wait(self._poll_interval)

    @property
    def supports_vibration_capture(self) -> bool:
        return True

    def start_vibration_capture(
        self,
        duration_s: float,
        rate_hz: float,
        on_progress,
        on_done,
    ) -> None:
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
        """Gera uma série sintética de "vibração" em torno de 0° (posição de
        calibração): soma de duas oscilações de baixa amplitude, em
        frequências plausíveis para balanço de mastro sob vento (~1.3Hz) e
        vibração mecânica (~5Hz), mais ruído — só para exercitar todo o
        fluxo de captura/estatística/relatório sem hardware real."""
        interval = 1.0 / rate_hz
        n_samples = max(1, int(duration_s * rate_hz))
        readings: list[AngleReading] = []
        t0 = time.time()
        try:
            for i in range(n_samples):
                if self._vibration_stop_event.is_set():
                    on_done(None, "Captura cancelada pelo usuário.")
                    return
                now = time.time()
                elapsed = now - t0
                vib = (
                    0.15 * math.sin(2 * math.pi * 1.3 * elapsed)
                    + 0.05 * math.sin(2 * math.pi * 5.0 * elapsed + 0.7)
                    + random.gauss(0.0, 0.03)
                )
                readings.append(AngleReading(angle_deg=vib, timestamp=now))
                on_progress(min(100.0, 100.0 * (i + 1) / n_samples))
                self._vibration_stop_event.wait(interval)
            on_done(readings, None)
        except Exception as exc:  # noqa: BLE001
            on_done(None, str(exc))
        finally:
            self._vibration_thread = None
