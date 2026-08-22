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
6. **SNR mínimo contra o piso de ruído LOCAL**: só reporta uma frequência
   dominante se o pico for significativamente mais alto que o ruído à sua
   volta — evita apontar "frequência dominante" num sinal que é só ruído
   aleatório. O piso é medido numa janela em torno do pico, e não no
   espectro inteiro, porque no eixo de azimute o ruído não é branco (ver
   abaixo) e uma mediana global daria falso positivo garantido.

O firmware manda o eixo de **azimute como velocidade angular** (graus/s),
não como ângulo, porque o ângulo de pan é obtido por integração com ZUPT e o
ZUPT apaga de propósito o que integra enquanto o eixo está parado — que é
justamente a condição de um ensaio de vibração.

Por isso o azimute guarda as DUAS séries: `pan_rates_to_angles` produz o
ângulo, usado nos gráficos no tempo e nas estatísticas (desvio padrão, RMS,
pico a pico), e a taxa original fica em `pan_rate_dps`, usada na detecção do
pico dominante. Não é redundância: o passo 6 supõe piso de ruído plano, e o
ruído do giroscópio só é branco na taxa — no ângulo integrado ele vira
passeio aleatório (1/f²) e a detecção acusaria pico em ruído puro. Ver
`analyze_axis`.
"""
from __future__ import annotations

import dataclasses
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from limits.limit_tracker import PAN_AXIS, TILT_AXIS

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


def pan_rates_to_angles(rates_dps: list[float], rate_hz: float) -> list[float]:
    """Converte a série de velocidade angular do pan (graus/s) na variação
    angular correspondente (graus).

    O firmware envia o eixo de pan como TAXA, não como ângulo — ver
    `firmware/src/VibrationCapture.h`. Aqui ela é integrada (regra do
    trapézio) e a tendência linear resultante é removida.

    A remoção da tendência não é cosmética: o bias residual do giroscópio é
    uma constante somada à taxa, e integrar uma constante dá exatamente uma
    rampa linear. Tirar a reta ajustada elimina esse termo por construção, e
    o que sobra é a oscilação em torno da posição média — que é o que o
    ensaio de vibração quer medir. É também por isso que integrar no tempo
    aqui é tão bom quanto integrar no domínio da frequência: o único termo
    que a integração amplificaria de forma problemática é justamente o que a
    reta remove.
    """
    n = len(rates_dps)
    if n == 0:
        return []
    rates = np.asarray(rates_dps, dtype=float)
    dt = 1.0 / rate_hz

    # Trapézio cumulativo, começando em zero.
    angles = np.concatenate(([0.0], np.cumsum((rates[:-1] + rates[1:]) * 0.5 * dt))) if n > 1 else np.zeros(1)

    if n > 1:
        x = np.arange(n, dtype=float)
        slope, intercept = np.polyfit(x, angles, 1)
        angles = angles - (slope * x + intercept)
    return [float(v) for v in angles]


def _axis_values(readings: list["AngleReading"], axis: str) -> np.ndarray:
    """Série numérica do eixo pedido. Levanta erro se o eixo não foi medido —
    quem chama deve checar antes (ver `has_pan_samples`)."""
    if axis == PAN_AXIS:
        if any(r.pan_deg is None for r in readings):
            raise ValueError("Captura sem amostras do eixo de azimute.")
        return np.array([r.pan_deg for r in readings], dtype=float)
    return np.array([r.angle_deg for r in readings], dtype=float)


def has_pan_samples(readings: list["AngleReading"]) -> bool:
    """True se a captura tem o eixo de azimute em todas as amostras."""
    return bool(readings) and all(r.pan_deg is not None for r in readings)


def compute_stats(readings: list["AngleReading"], axis: str = TILT_AXIS) -> VibrationStats:
    if not readings:
        raise ValueError("Nenhuma amostra na captura.")
    values = _axis_values(readings, axis)
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


def _spectrum(values: np.ndarray, rate_hz: float) -> tuple[np.ndarray, np.ndarray]:
    """Espectro de amplitude de um lado só de uma série qualquer, com os
    passos 1-4 do pipeline descrito no topo do módulo. A unidade da saída é a
    mesma da entrada (graus, ou graus/s no caso da taxa do azimute)."""
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


def _pan_rates(readings: list["AngleReading"]) -> np.ndarray:
    if any(r.pan_rate_dps is None for r in readings):
        raise ValueError("Captura sem a velocidade angular do eixo de azimute.")
    return np.array([r.pan_rate_dps for r in readings], dtype=float)


def _rate_spectrum_to_angle(freqs: np.ndarray, rate_magnitudes: np.ndarray) -> np.ndarray:
    """Converte um espectro de velocidade angular (graus/s) no espectro de
    amplitude angular correspondente (graus): uma oscilação de amplitude A em
    `f` tem velocidade de amplitude `A*2*pi*f`, logo `A = R(f) / (2*pi*f)`.

    O bin de 0 Hz vira zero — ali a divisão explodiria, e é justamente onde
    mora o bias do giroscópio, que não é vibração."""
    angle = np.zeros_like(rate_magnitudes)
    nonzero = freqs > 0
    angle[nonzero] = rate_magnitudes[nonzero] / (2.0 * np.pi * freqs[nonzero])
    return angle


def compute_fft(
    readings: list["AngleReading"], rate_hz: float, axis: str = TILT_AXIS
) -> tuple[np.ndarray, np.ndarray]:
    """Retorna `(frequências_hz, amplitude_graus)` do espectro da variação
    angular — amplitude de um lado só, corrigida pela janela, já pronta pra
    ler diretamente como a amplitude física da oscilação naquela frequência
    (ver notas do módulo sobre o pipeline completo).

    No eixo de azimute o espectro é calculado a partir da VELOCIDADE angular
    e depois convertido para amplitude angular — ver `analyze_axis`."""
    if not readings:
        raise ValueError("Nenhuma amostra na captura.")
    if axis == PAN_AXIS:
        freqs, rate_magnitudes = _spectrum(_pan_rates(readings), rate_hz)
        return freqs, _rate_spectrum_to_angle(freqs, rate_magnitudes)
    return _spectrum(_axis_values(readings, axis), rate_hz)


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
    #
    # Isso pressupõe um piso de ruído aproximadamente PLANO — por isso esta
    # função é sempre alimentada com um espectro cujo ruído é branco: o do
    # ângulo, no eixo de tilt, e o da VELOCIDADE ANGULAR, no eixo de azimute
    # (ver `analyze_axis`).
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


@dataclass(frozen=True)
class AxisAnalysis:
    """Resultado completo da análise de vibração de um eixo."""

    axis: str
    stats: VibrationStats
    freqs: np.ndarray
    magnitudes: np.ndarray


def analyze_axis(
    readings: list["AngleReading"], rate_hz: float, axis: str = TILT_AXIS
) -> AxisAnalysis:
    """Roda o pipeline inteiro (estatísticas + espectro + pico dominante) num
    eixo de uma captura.

    A diferença entre os eixos está em QUAL espectro alimenta a detecção do
    pico. `find_dominant_peak` compara o pico com a mediana do espectro, o
    que só é justo se o piso de ruído for plano:

    - **tilt**: o ruído do acelerômetro já é branco no ângulo, então o
      espectro do ângulo serve direto;
    - **azimute**: o ruído do giroscópio é branco na TAXA. O espectro do
      ângulo (que é a integral) tem ruído de passeio aleatório, caindo com
      1/f² — nele a mediana global fica dominada pelas frequências altas e
      qualquer bin de baixa frequência vira um "pico" enorme. Medido em
      teste: ruído puro era apontado como frequência dominante em 100% das
      tentativas. Por isso a detecção roda no espectro da taxa, e só a
      amplitude do pico encontrado é convertida para graus.

    O espectro devolvido para os gráficos é sempre em graus, nos dois casos.
    """
    stats = compute_stats(readings, axis)

    if axis == PAN_AXIS:
        freqs, rate_magnitudes = _spectrum(_pan_rates(readings), rate_hz)
        peak = find_dominant_peak(freqs, rate_magnitudes)
        magnitudes = _rate_spectrum_to_angle(freqs, rate_magnitudes)
        amplitude_deg = (
            peak.amplitude_deg / (2.0 * math.pi * peak.freq_hz)
            if peak is not None and peak.freq_hz > 0
            else None
        )
    else:
        freqs, magnitudes = _spectrum(_axis_values(readings, axis), rate_hz)
        peak = find_dominant_peak(freqs, magnitudes)
        amplitude_deg = peak.amplitude_deg if peak is not None else None

    if peak is not None and amplitude_deg is not None:
        stats = dataclasses.replace(
            stats,
            dominant_freq_hz=peak.freq_hz,
            dominant_amplitude_deg=amplitude_deg,
            dominant_snr_db=peak.snr_db,
        )
    return AxisAnalysis(axis=axis, stats=stats, freqs=freqs, magnitudes=magnitudes)
