"""Resumo da aquisição que alimenta o relatório em PDF.

O relatório usa as leituras de UMA aquisição (uma "sessão" do histórico):

- começa no "Iniciar", ou no "Resetar limites"/"Calibrar" com a leitura em
  andamento (os dois abrem uma aquisição nova, porque mín/máx de antes do
  reset não valem mais);
- termina no "Parar" ou quando acaba o tempo programado (ver
  `ACQUISITION_DURATIONS_S`); gerado com a leitura em andamento, o
  relatório usa os dados até o momento.

Cada leitura é o valor que a tela mostra, recebido a ~4-5 Hz (poll Modbus de
250 ms, notify BLE de ~200 ms). Os mín/máx vêm, sempre que o firmware
oferece (v1.5.0+), do próprio ESP32, que mede a 100 Hz.

Este módulo não depende de Qt nem de reportlab: só calcula os números que o
relatório e a tela mostram sobre a aquisição, para os dois dizerem a mesma
coisa e para poder ser testado isoladamente.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from limits.limit_tracker import PAN_AXIS, SOURCE_FIRMWARE, TILT_AXIS

if TYPE_CHECKING:
    from data_source.base import AngleReading
    from limits.history_store import SessionInfo
    from limits.limit_tracker import LimitEvent

# Tempos de aquisição oferecidos na tela, em segundos. `None` = livre (até o
# "Parar"). A primeira opção é o padrão, que mantém o comportamento antigo.
ACQUISITION_DURATIONS_S: list[float | None] = [None, 60, 5 * 60, 10 * 60, 30 * 60, 60 * 60]

# Intervalo sem leitura a partir do qual o relatório aponta uma interrupção
# (queda e reconexão do Bluetooth, cabo USB solto...). Dez vezes o intervalo
# normal: perder uma ou duas leituras não conta.
GAP_THRESHOLD_S = 2.0


@dataclass(frozen=True)
class Gap:
    start: float  # timestamp da última leitura antes do buraco
    end: float  # timestamp da primeira leitura depois dele

    @property
    def duration_s(self) -> float:
        return self.end - self.start


@dataclass(frozen=True)
class AcquisitionSummary:
    started_at: float | None
    ended_at: float | None  # None = aquisição em andamento
    planned_duration_s: float | None
    first_reading_at: float | None
    last_reading_at: float | None
    n_readings: int
    n_pan_readings: int
    gaps: list[Gap] = field(default_factory=list)
    # Origem dos mín/máx por eixo: SOURCE_FIRMWARE, SOURCE_APP ou None (sem dado).
    extremes_source: dict[str, str | None] = field(default_factory=dict)
    median_interval_s: float | None = None

    @property
    def in_progress(self) -> bool:
        return self.started_at is not None and self.ended_at is None

    @property
    def end_reference(self) -> float | None:
        """Fim da janela coberta pelo relatório: o "Parar", ou a última
        leitura se a aquisição ainda estiver em andamento."""
        if self.ended_at is not None:
            return self.ended_at
        return self.last_reading_at

    @property
    def duration_s(self) -> float:
        """Duração da aquisição (do início ao fim/última leitura)."""
        start = self.started_at if self.started_at is not None else self.first_reading_at
        end = self.end_reference
        if start is None or end is None:
            return 0.0
        return max(0.0, end - start)

    @property
    def gap_total_s(self) -> float:
        return sum(g.duration_s for g in self.gaps)

    @property
    def mean_rate_hz(self) -> float | None:
        """Leituras por segundo entre a primeira e a última leitura."""
        if self.n_readings < 2 or self.first_reading_at is None or self.last_reading_at is None:
            return None
        span = self.last_reading_at - self.first_reading_at
        return (self.n_readings - 1) / span if span > 0 else None

    @property
    def coverage_pct(self) -> float | None:
        """Parte da aquisição que tem leitura (descontadas as interrupções e
        o tempo até a primeira leitura chegar, ex: conectando ao ESP32)."""
        if self.duration_s <= 0 or self.first_reading_at is None or self.last_reading_at is None:
            return None
        covered = (self.last_reading_at - self.first_reading_at) - self.gap_total_s
        return max(0.0, min(100.0, 100.0 * covered / self.duration_s))

    @property
    def completed_planned(self) -> bool | None:
        """Se a aquisição programada chegou ao fim do tempo (None se livre)."""
        if self.planned_duration_s is None:
            return None
        return self.duration_s >= self.planned_duration_s - 1.0


def _extremes_source(events: list["LimitEvent"], axis: str) -> str | None:
    sources = {e.source for e in events if e.axis == axis}
    if not sources:
        return None
    # Basta um extremo vindo do firmware para a origem ser ele: o primeiro
    # evento da sessão sai da própria leitura antes de o pacote de extremos
    # chegar, e não muda o que foi medido depois.
    return SOURCE_FIRMWARE if SOURCE_FIRMWARE in sources else sorted(sources)[0]


def summarize_acquisition(
    session: "SessionInfo | None",
    readings: list["AngleReading"],
    events: list["LimitEvent"] | None = None,
) -> AcquisitionSummary:
    events = events or []
    timestamps = sorted(r.timestamp for r in readings)
    gaps: list[Gap] = []
    intervals: list[float] = []
    for a, b in zip(timestamps, timestamps[1:]):
        intervals.append(b - a)
        if b - a > GAP_THRESHOLD_S:
            gaps.append(Gap(a, b))

    return AcquisitionSummary(
        started_at=session.started_at if session else (timestamps[0] if timestamps else None),
        ended_at=(session.ended_at if session else (timestamps[-1] if timestamps else None)),
        planned_duration_s=session.planned_duration_s if session else None,
        first_reading_at=timestamps[0] if timestamps else None,
        last_reading_at=timestamps[-1] if timestamps else None,
        n_readings=len(readings),
        n_pan_readings=sum(1 for r in readings if r.pan_deg is not None),
        gaps=gaps,
        extremes_source={axis: _extremes_source(events, axis) for axis in (TILT_AXIS, PAN_AXIS)},
        median_interval_s=statistics.median(intervals) if intervals else None,
    )


def format_duration(seconds: float | None) -> str:
    """Duração legível: "45 s", "5 min 03 s", "1 h 02 min 05 s"."""
    if seconds is None:
        return "-"
    total = int(round(seconds))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h} h {m:02d} min {s:02d} s"
    if m:
        return f"{m} min {s:02d} s"
    return f"{s} s"


def format_planned(planned_s: float | None) -> str:
    """Rótulo de um tempo de aquisição programado (o mesmo da tela)."""
    if planned_s is None:
        return "Livre (até \"Parar\")"
    minutes = planned_s / 60
    if minutes >= 60 and minutes % 60 == 0:
        return f"{int(minutes // 60)} h"
    if minutes >= 1 and minutes == int(minutes):
        return f"{int(minutes)} min"
    return format_duration(planned_s)


def format_clock(seconds: float) -> str:
    """Cronômetro da tela: "03:12" ou "1:02:05"."""
    total = max(0, int(seconds))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"
