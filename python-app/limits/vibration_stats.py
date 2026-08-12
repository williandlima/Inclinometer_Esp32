"""Estatísticas de uma captura de vibração: pico-a-pico, desvio padrão, RMS
e espectro de frequência (FFT) a partir das amostras registradas em alta
taxa. Independente da fonte de dados, como o restante de `limits/`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from data_source.base import AngleReading


@dataclass(frozen=True)
class VibrationStats:
    n_samples: int
    duration_s: float
    mean_deg: float
    std_dev_deg: float
    rms_deg: float
    peak_to_peak_deg: float
    min_deg: float
    max_deg: float


def compute_stats(readings: list["AngleReading"]) -> VibrationStats:
    if not readings:
        raise ValueError("Nenhuma amostra na captura.")
    values = np.array([r.angle_deg for r in readings], dtype=float)
    duration = readings[-1].timestamp - readings[0].timestamp
    return VibrationStats(
        n_samples=len(readings),
        duration_s=duration,
        mean_deg=float(values.mean()),
        std_dev_deg=float(values.std()),
        rms_deg=float(np.sqrt(np.mean(values ** 2))),
        peak_to_peak_deg=float(values.max() - values.min()),
        min_deg=float(values.min()),
        max_deg=float(values.max()),
    )


def compute_fft(readings: list["AngleReading"], rate_hz: float) -> tuple[np.ndarray, np.ndarray]:
    """Retorna `(frequências_hz, magnitude_graus)` do espectro da variação
    angular. A componente contínua (média) é removida antes da FFT, já que
    o interesse aqui é a variação em torno do ponto calibrado, não o valor
    absoluto do ângulo.
    """
    if not readings:
        raise ValueError("Nenhuma amostra na captura.")
    values = np.array([r.angle_deg for r in readings], dtype=float)
    values = values - values.mean()
    n = len(values)
    spectrum = np.fft.rfft(values)
    freqs = np.fft.rfftfreq(n, d=1.0 / rate_hz)
    magnitude = np.abs(spectrum) / n
    return freqs, magnitude
