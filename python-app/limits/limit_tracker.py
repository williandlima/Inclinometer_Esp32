"""Rastreamento de mínimo/máximo em runtime, independente da fonte de dados.

Funciona igual em modo simulado ou real: recebe cada `AngleReading` e informa
se ela representa um novo mínimo e/ou um novo máximo desde o último reset.
"""
from __future__ import annotations

from dataclasses import dataclass

from data_source.base import AngleReading


@dataclass
class LimitEvent:
    kind: str  # "min" | "max"
    reading: AngleReading


class LimitTracker:
    def __init__(self) -> None:
        self._min_reading: AngleReading | None = None
        self._max_reading: AngleReading | None = None

    def reset(self) -> None:
        self._min_reading = None
        self._max_reading = None

    @property
    def min_reading(self) -> AngleReading | None:
        return self._min_reading

    @property
    def max_reading(self) -> AngleReading | None:
        return self._max_reading

    def process(self, reading: AngleReading) -> list[LimitEvent]:
        """Atualiza os extremos e retorna os eventos de novo limite (0, 1 ou 2)."""
        events: list[LimitEvent] = []

        if self._min_reading is None or reading.angle_deg < self._min_reading.angle_deg:
            self._min_reading = reading
            events.append(LimitEvent(kind="min", reading=reading))

        if self._max_reading is None or reading.angle_deg > self._max_reading.angle_deg:
            self._max_reading = reading
            events.append(LimitEvent(kind="max", reading=reading))

        return events
