"""Rastreamento de mínimo/máximo em runtime, independente da fonte de dados.

Funciona igual em modo simulado ou real: recebe cada `AngleReading` e informa
se ela representa um novo mínimo e/ou um novo máximo desde o último reset.

Cada instância rastreia **um eixo**. O app cria duas: uma para a inclinação
(tilt) e outra para o azimute (pan). Leituras em que o eixo rastreado não foi
medido — `pan_deg is None`, caso de um ESP32 com firmware anterior à v1.2.0 —
são simplesmente ignoradas, em vez de contarem como zero e poluírem os
extremos.

DE ONDE VEM O EXTREMO. A partir do firmware v1.5.0, quem mede os extremos é o
próprio ESP32, e a leitura os traz prontos (`angle_min_deg` e companhia). Este
rastreador então apenas os acompanha, em vez de calculá-los. O motivo é de
amostragem, não de código: o firmware vê o sensor a 100 Hz, o app vê a 4-5 Hz,
e um evento curto — a rajada de vento que o relatório existe para registrar —
acontece inteiro entre duas leituras do app.

Sem esses campos (firmware antigo, modo simulação) o cálculo volta a ser feito
aqui, a partir das leituras recebidas, exatamente como antes. As duas fontes
convivem por eixo: dá para o tilt vir do dispositivo e o pan ser calculado
aqui, se for isso que o firmware conectado oferecer.
"""
from __future__ import annotations

import dataclasses
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

    def _device_peak(self, reading: AngleReading, kind: str) -> float | None:
        """Extremo medido pelo firmware para o eixo deste rastreador, se houver."""
        if self._axis == PAN_AXIS:
            return reading.pan_min_deg if kind == "min" else reading.pan_max_deg
        return reading.angle_min_deg if kind == "min" else reading.angle_max_deg

    def _as_extreme(self, reading: AngleReading, value: float) -> AngleReading:
        """Leitura que representa um extremo vindo do dispositivo.

        O extremo do firmware é só um número — não vem acompanhado do instante
        em que aconteceu. Aqui ele é ancorado na leitura que o trouxe, com o
        valor do eixo rastreado substituído pelo extremo. O carimbo de tempo
        fica portanto até um intervalo de poll (~250 ms) depois do evento real;
        o VALOR, que é o que vai para o relatório, é exato.
        """
        field = "pan_deg" if self._axis == PAN_AXIS else "angle_deg"
        return dataclasses.replace(reading, **{field: value})

    def process(self, reading: AngleReading) -> list[LimitEvent]:
        """Atualiza os extremos e retorna os eventos de novo limite (0, 1 ou 2).

        Devolve lista vazia se o eixo rastreado não foi medido nesta leitura.
        """
        value = self._value(reading)
        if value is None:
            return []

        events: list[LimitEvent] = []

        for kind in ("min", "max"):
            peak = self._device_peak(reading, kind)
            candidate = value if peak is None else peak
            candidate_reading = reading if peak is None else self._as_extreme(reading, candidate)

            previous = self._min_reading if kind == "min" else self._max_reading
            current = None if previous is None else self._value(previous)
            improved = current is None or (
                candidate < current if kind == "min" else candidate > current
            )
            if not improved:
                continue

            if kind == "min":
                self._min_reading = candidate_reading
            else:
                self._max_reading = candidate_reading
            events.append(LimitEvent(kind=kind, reading=candidate_reading, axis=self._axis))

        return events
