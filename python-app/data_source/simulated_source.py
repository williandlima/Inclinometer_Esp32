"""Fonte de dados simulada: gera ângulos sintéticos sem hardware real.

Usada para desenvolver e testar o app antes do firmware/hardware do ESP32
estarem prontos. Gera uma oscilação senoidal dentro da faixa 0-120°, somada
a ruído gaussiano, para se aproximar de uma leitura real de sensor.
"""
from __future__ import annotations

import math
import random
import threading
import time

from data_source.base import ANGLE_MAX_DEG, ANGLE_MIN_DEG, AngleReading, ErrorCallback, IAngleDataSource, ReadingCallback


class SimulatedAngleSource(IAngleDataSource):
    def __init__(
        self,
        center_deg: float = 60.0,
        amplitude_deg: float = 12.0,
        period_s: float = 45.0,
        noise_std_deg: float = 0.08,
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

    @property
    def label(self) -> str:
        return "Simulação"

    @property
    def supports_calibration(self) -> bool:
        return True

    def calibrate(self) -> None:
        """Ajusta o offset para que o próximo ângulo lido seja ~0°,
        simulando o zeramento do acelerômetro na posição atual."""
        with self._lock:
            self._offset_deg = self._last_raw_deg

    def start(self, on_reading: ReadingCallback, on_error: ErrorCallback | None = None) -> None:
        if self._thread is not None:
            return
        self._stop_event.clear()
        self._t0 = time.time()
        self._thread = threading.Thread(target=self._run, args=(on_reading,), daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _run(self, on_reading: ReadingCallback) -> None:
        while not self._stop_event.is_set():
            now = time.time()
            elapsed = now - self._t0
            raw_angle = self._center + self._amplitude * math.sin(2 * math.pi * elapsed / self._period)
            raw_angle += random.gauss(0.0, self._noise_std)

            with self._lock:
                self._last_raw_deg = raw_angle
                angle = raw_angle - self._offset_deg

            angle = max(ANGLE_MIN_DEG, min(ANGLE_MAX_DEG, angle))
            on_reading(AngleReading(angle_deg=angle, timestamp=now))
            self._stop_event.wait(self._poll_interval)
