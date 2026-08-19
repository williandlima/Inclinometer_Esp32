"""Estatísticas de uma captura de vibração: pico-a-pico, desvio padrão, RMS
e espectro de frequência (FFT) a partir das amostras registradas em alta
taxa. Independente da fonte de dados, como o restante de `limits/`.

O pipeline da FFT (`compute_fft` + `find_dominant_peak`) segue práticas
padrão de análise espectral para deixar o resultado mais confiável e claro:

1. **Remoção de tendência linear** (não só a média): uma deriva lenta
   durante a captura (ex: pequeno movimento real, drift térmico) apareceria
   como energia falsa perto de 0 Hz se só a média fosse removida.
2. **Janela de Hann** antes da FFT: sem janela (retangular, implícita), o
   espectro sofre "vazamento" (spectral leakage) — a energia de uma
   frequência real se espalha pelos bins vizinhos, borrando picos e criando
   lóbulos secundários. A amplitude é corrigida pelo ganho coerente da
   janela para o valor em graus continuar fisicamente correto.
3. **Zero-padding até a próxima potência de 2**: interpola o espectro para
   uma curva mais suave (mesma técnica usada no app Android, que precisa
   disso pela FFT radix-2) — não aumenta a resolução real (que continua
   sendo 1/duração), só deixa o gráfico mais legível.
4. **Amplitude de um lado só (single-sided) corrigida**: os bins não-DC e
   não-Nyquist são dobrados, para o valor reportado bater com a amplitude
   física real da oscilação (antes, o valor cru da FFT subestimava a
   amplitude pela metade).
5. **Frequência dominante com interpolação parabólica**: em vez de só o bin
   de pico (limitado à resolução rate_hz/n), ajusta uma parábola nos 3
   pontos ao redor do pico pra estimar a frequência real entre bins.
6. **SNR mínimo (piso de ruído)**: só reporta uma frequência dominante se o
   pico for significativamente mais alto que o piso de ruído do espectro —
   evita apontar "frequência dominante" num sinal que é só ruído aleatório.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from data_source.base import AngleReading

# Abaixo dessa frequência não é considerado pico dominante — evita que
# deriva lenta residual (não totalmente removida pelo detrend) ou o
# lóbulo da janela ao redor de 0 Hz seja confundido com vibração real.
MIN_PEAK_FREQ_HZ = 0.15

# Margem de segurança (dB) somada ao limiar teórico de SNR — ver
# `_min_snr_db_for_bins`.
_SNR_SAFETY_MARGIN_DB = 8.0

# Piso absoluto: mesmo com poucos bins (limiar teórico baixo), nunca aceita
# um pico com menos que isso de SNR.
_SNR_FLOOR_DB = 6.0


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
    dominant_freq_hz: float | None = None
    dominant_amplitude_deg: float | None = None
    dominant_snr_db: float | None = None


@dataclass(frozen=True)
class DominantPeak:
    freq_hz: float
    amplitude_deg: float
    snr_db: float


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


def _next_pow2(n: int) -> int:
    return 1 if n <= 1 else 1 << (n - 1).bit_length()


def compute_fft(readings: list["AngleReading"], rate_hz: float) -> tuple[np.ndarray, np.ndarray]:
    """Retorna `(frequências_hz, amplitude_graus)` do espectro da variação
    angular — amplitude de um lado só, corrigida pela janela, já pronta pra
    ler diretamente como a amplitude física da oscilação naquela frequência
    (ver notas do módulo sobre o pipeline completo)."""
    if not readings:
        raise ValueError("Nenhuma amostra na captura.")
    values = np.array([r.angle_deg for r in readings], dtype=float)
    n = len(values)

    x = np.arange(n, dtype=float)
    slope, intercept = np.polyfit(x, values, 1)
    detrended = values - (slope * x + intercept)

    window = np.hanning(n) if n > 1 else np.ones(n)
    coherent_gain = window.mean() if n > 1 else 1.0
    windowed = detrended * window

    n_fft = _next_pow2(n)
    spectrum = np.fft.rfft(windowed, n=n_fft)
    freqs = np.fft.rfftfreq(n_fft, d=1.0 / rate_hz)

    magnitude = np.abs(spectrum) / (n * coherent_gain)
    if len(magnitude) > 2:
        magnitude[1:-1] *= 2.0  # single-sided: dobra tudo, exceto DC e Nyquist
    return freqs, magnitude


def _min_snr_db_for_bins(num_bins: int) -> float:
    """Limiar de SNR mínimo, ajustado pelo número de bins pesquisados.

    Sob ruído puro (sem vibração periódica real), a magnitude de cada bin
    da FFT segue aproximadamente uma distribuição de Rayleigh i.i.d.. Quanto
    mais bins são pesquisados, maior a chance de que o maior deles pareça
    "alto" só por acaso (estatística de valores extremos) — um limiar fixo
    de poucos dB gera falso positivo com sinais de centenas/milhares de
    bins. O valor esperado do máximo de `M` amostras Rayleigh i.i.d. fica
    ~10*log10(ln(M)/ln(2)) dB acima da mediana; somamos uma margem de
    segurança fixa por cima disso.
    """
    m = max(int(num_bins), 2)
    theoretical_db = 10.0 * math.log10(math.log(m) / math.log(2))
    return max(_SNR_FLOOR_DB, theoretical_db + _SNR_SAFETY_MARGIN_DB)


def find_dominant_peak(
    freqs: np.ndarray,
    magnitudes: np.ndarray,
    min_freq_hz: float = MIN_PEAK_FREQ_HZ,
    min_snr_db: float | None = None,
) -> DominantPeak | None:
    """Identifica a frequência dominante do espectro, com refinamento
    sub-bin (interpolação parabólica) e um teste de confiança (SNR contra o
    piso de ruído). Retorna `None` se nenhum pico for confiável — ou seja, o
    sinal é compatível com ruído, sem vibração periódica clara."""
    if len(freqs) < 3:
        return None

    start_idx = int(np.searchsorted(freqs, min_freq_hz))
    if start_idx >= len(magnitudes) - 1:
        return None

    search = magnitudes[start_idx:]
    if min_snr_db is None:
        min_snr_db = _min_snr_db_for_bins(len(search))
    peak_idx = start_idx + int(np.argmax(search))

    freq_step = freqs[1] - freqs[0] if len(freqs) > 1 else 0.0
    peak_freq = float(freqs[peak_idx])
    peak_amp = float(magnitudes[peak_idx])
    if start_idx < peak_idx < len(magnitudes) - 1:
        alpha, beta, gamma = magnitudes[peak_idx - 1], magnitudes[peak_idx], magnitudes[peak_idx + 1]
        denom = alpha - 2 * beta + gamma
        if denom != 0:
            p = 0.5 * (alpha - gamma) / denom
            p = max(-1.0, min(1.0, p))
            peak_freq = float(freqs[peak_idx] + p * freq_step)
            peak_amp = float(beta - 0.25 * (alpha - gamma) * p)

    # Piso de ruído: mediana do espectro na faixa de busca, excluindo os
    # bins do próprio pico (mediana é robusta a outliers, ou seja, ao
    # próprio pico e a eventuais harmônicos).
    exclude_lo = max(start_idx, peak_idx - 2)
    exclude_hi = min(len(magnitudes) - 1, peak_idx + 2)
    noise_idx = [i for i in range(start_idx, len(magnitudes)) if i < exclude_lo or i > exclude_hi]
    noise_floor = float(np.median(magnitudes[noise_idx])) if noise_idx else 0.0

    if noise_floor <= 1e-9:
        snr_db = math.inf
    else:
        snr_db = 20.0 * math.log10(max(peak_amp, 1e-9) / noise_floor)

    if snr_db < min_snr_db:
        return None
    return DominantPeak(freq_hz=peak_freq, amplitude_deg=peak_amp, snr_db=snr_db)
