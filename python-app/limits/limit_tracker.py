"""Rastreamento de mínimo/máximo em runtime, independente da fonte de dados.

Funciona igual em modo simulado ou real: recebe cada `AngleReading` e informa
se ela representa um novo mínimo e/ou um novo máximo desde o último reset.

Cada instância rastreia **um eixo**. O app cria duas: uma para a inclinação
(tilt) e outra para o azimute (pan). Leituras em que o eixo rastreado não foi
medido — `pan_deg is None`, caso de um ESP32 com firmware anterior à v1.2.0 —
são simplesmente ignoradas, em vez de contarem como zero e poluírem os
extremos.
"""
from __future__ import annotations

from dataclasses import dataclass

from data_source.base import AngleReading

TILT_AXIS = "tilt"
PAN_AXIS = "pan"

AXIS_LABELS = {TILT_AXIS: "Inclinação", PAN_AXIS: "Azimute"}


@dataclass
class LimitEvent:
    kind: str  # "min" | "max"
    reading: AngleReading
    axis: str = TILT_AXIS

    @property
    def value_deg(self) -> float:
        """Valor do eixo a que este evento se refere.

        Um evento de pan só é criado a partir de uma leitura que tem pan, e a
        releitura do histórico reconstrói os dois eixos — então o `None` aqui
        seria dado corrompido, não um caso normal.
        """
        if self.axis == PAN_AXIS:
            if self.reading.pan_deg is None:
                raise ValueError("Evento de limite do eixo de azimute sem valor de azimute.")
            return self.reading.pan_deg
        return self.reading.angle_deg


class LimitTracker:
    def __init__(self, axis: str = TILT_AXIS) -> None:
        self._axis = axis
        self._min_reading: AngleReading | None = None
        self._max_reading: AngleReading | None = None

    @property
    def axis(self) -> str:
        return self._axis

    def reset(self) -> None:
        self._min_reading = None
        self._max_reading = None

    @property
    def min_reading(self) -> AngleReading | None:
        return self._min_reading

    @property
    def max_reading(self) -> AngleReading | None:
        return self._max_reading

    def _value(self, reading: AngleReading) -> float | None:
        return reading.pan_deg if self._axis == PAN_AXIS else reading.angle_deg

    def process(self, reading: AngleReading) -> list[LimitEvent]:
        """Atualiza os extremos e retorna os eventos de novo limite (0, 1 ou 2).

        Devolve lista vazia se o eixo rastreado não foi medido nesta leitura.
        """
        value = self._value(reading)
        if value is None:
            return []

        events: list[LimitEvent] = []

        current_min = None if self._min_reading is None else self._value(self._min_reading)
        if current_min is None or value < current_min:
            self._min_reading = reading
            events.append(LimitEvent(kind="min", reading=reading, axis=self._axis))

        current_max = None if self._max_reading is None else self._value(self._max_reading)
        if current_max is None or value > current_max:
            self._max_reading = reading
            events.append(LimitEvent(kind="max", reading=reading, axis=self._axis))

        return events
