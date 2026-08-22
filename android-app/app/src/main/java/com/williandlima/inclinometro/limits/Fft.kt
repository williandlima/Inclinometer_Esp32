package com.williandlima.inclinometro.limits

import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.hypot
import kotlin.math.ln
import kotlin.math.log10
import kotlin.math.max
import kotlin.math.min
import kotlin.math.sin

/**
 * FFT real simples (Cooley-Tukey iterativo, radix-2) + análise espectral da
 * captura de vibração — equivalente a `limits/vibration_stats.py` do app
 * desktop (mesmo pipeline, mesmas constantes), sem depender de biblioteca
 * externa. Ver o docstring do módulo Python para a explicação completa do
 * porquê de cada etapa (detrend, janela, correção de amplitude, SNR
 * adaptativo pelo número de bins).
 */
internal object Fft {

    /** Abaixo dessa frequência não é considerado pico dominante. */
    private const val MIN_PEAK_FREQ_HZ = 0.15

    /** Margem de segurança (dB) somada ao limiar teórico de SNR. */
    private const val SNR_SAFETY_MARGIN_DB = 8.0

    /** Piso absoluto de SNR, mesmo com poucos bins. */
    private const val SNR_FLOOR_DB = 6.0

    data class DominantPeak(
        val freqHz: Double,
        val amplitudeDeg: Double,
        val snrDb: Double,
    )

    /**
     * Retorna `(frequências_hz, amplitude_graus)` do espectro de `values`
     * (amostras igualmente espaçadas em `rateHz`): tendência linear
     * removida, janela de Hann aplicada (com correção de ganho coerente),
     * zero-padding até a próxima potência de 2, amplitude de um lado só
     * (bins não-DC/não-Nyquist dobrados) — equivalente a
     * `vibration_stats.compute_fft` do app desktop.
     */
    fun computeSpectrum(values: DoubleArray, rateHz: Double): Pair<DoubleArray, DoubleArray> {
        require(values.isNotEmpty()) { "Nenhuma amostra na captura." }

        val nOriginal = values.size
        val detrended = detrendLinear(values)

        val window = hannWindow(nOriginal)
        val coherentGain = if (nOriginal > 1) window.average() else 1.0
        val windowed = DoubleArray(nOriginal) { detrended[it] * window[it] }

        val n = nextPowerOfTwo(nOriginal)
        val real = DoubleArray(n)
        val imag = DoubleArray(n)
        for (i in windowed.indices) real[i] = windowed[i]

        fft(real, imag)

        val half = n / 2 + 1
        val freqs = DoubleArray(half) { it * rateHz / n }
        val magnitudes = DoubleArray(half) { k ->
            val raw = hypot(real[k], imag[k]) / (nOriginal * coherentGain)
            if (k == 0 || k == half - 1) raw else raw * 2.0
        }
        return freqs to magnitudes
    }

    /**
     * Identifica a frequência dominante do espectro, com refinamento
     * sub-bin (interpolação parabólica) e um teste de confiança (SNR contra
     * o piso de ruído, com limiar que se ajusta ao número de bins
     * pesquisados). Retorna `null` se nenhum pico for confiável — sinal
     * compatível com ruído, sem vibração periódica clara.
     */
    fun findDominantPeak(freqs: DoubleArray, magnitudes: DoubleArray): DominantPeak? {
        if (freqs.size < 3) return null

        var startIdx = freqs.indexOfFirst { it >= MIN_PEAK_FREQ_HZ }
        if (startIdx < 0) startIdx = freqs.size
        if (startIdx >= magnitudes.size - 1) return null

        var peakIdx = startIdx
        for (i in startIdx until magnitudes.size) {
            if (magnitudes[i] > magnitudes[peakIdx]) peakIdx = i
        }

        val freqStep = if (freqs.size > 1) freqs[1] - freqs[0] else 0.0
        var peakFreq = freqs[peakIdx]
        var peakAmp = magnitudes[peakIdx]
        if (peakIdx in (startIdx + 1) until (magnitudes.size - 1)) {
            val alpha = magnitudes[peakIdx - 1]
            val beta = magnitudes[peakIdx]
            val gamma = magnitudes[peakIdx + 1]
            val denom = alpha - 2 * beta + gamma
            if (denom != 0.0) {
                val p = (0.5 * (alpha - gamma) / denom).coerceIn(-1.0, 1.0)
                peakFreq = freqs[peakIdx] + p * freqStep
                peakAmp = beta - 0.25 * (alpha - gamma) * p
            }
        }

        // Piso de ruído: mediana do espectro na faixa de busca, excluindo os
        // bins do próprio pico.
        val excludeLo = max(startIdx, peakIdx - 2)
        val excludeHi = min(magnitudes.size - 1, peakIdx + 2)
        val noiseValues = mutableListOf<Double>()
        for (i in startIdx until magnitudes.size) {
            if (i < excludeLo || i > excludeHi) noiseValues.add(magnitudes[i])
        }
        val noiseFloor = if (noiseValues.isNotEmpty()) median(noiseValues) else 0.0

        val minSnrDb = minSnrDbForBins(magnitudes.size - startIdx)
        val snrDb = if (noiseFloor <= 1e-9) {
            Double.POSITIVE_INFINITY
        } else {
            20.0 * log10(max(peakAmp, 1e-9) / noiseFloor)
        }

        if (snrDb < minSnrDb) return null
        return DominantPeak(freqHz = peakFreq, amplitudeDeg = peakAmp, snrDb = snrDb)
    }

    /**
     * Limiar de SNR mínimo, ajustado pelo número de bins pesquisados (ver
     * `vibration_stats._min_snr_db_for_bins` no app desktop para a
     * justificativa estatística completa): sob ruído puro, quanto mais bins
     * são pesquisados, maior a chance de um deles parecer "alto" só por
     * acaso — o valor esperado do máximo de M amostras Rayleigh i.i.d. fica
     * ~10*log10(ln(M)/ln(2)) dB acima da mediana.
     */
    /**
     * Converte um espectro de velocidade angular (graus/s) no espectro de
     * amplitude angular correspondente (graus): uma oscilação de amplitude A
     * em `f` tem velocidade de amplitude `A*2*pi*f`, logo `A = R(f)/(2*pi*f)`.
     *
     * O bin de 0 Hz vira zero — ali a divisão explodiria, e é justamente onde
     * mora o bias do giroscópio, que não é vibração.
     */
    fun rateSpectrumToAngle(freqs: DoubleArray, rateMagnitudes: DoubleArray): DoubleArray =
        DoubleArray(rateMagnitudes.size) { i ->
            if (i < freqs.size && freqs[i] > 0.0) {
                rateMagnitudes[i] / (2.0 * PI * freqs[i])
            } else {
                0.0
            }
        }

    private fun minSnrDbForBins(numBins: Int): Double {
        val m = max(numBins, 2)
        val theoreticalDb = 10.0 * log10(ln(m.toDouble()) / ln(2.0))
        return max(SNR_FLOOR_DB, theoreticalDb + SNR_SAFETY_MARGIN_DB)
    }

    private fun median(values: List<Double>): Double {
        val sorted = values.sorted()
        val mid = sorted.size / 2
        return if (sorted.size % 2 == 0) (sorted[mid - 1] + sorted[mid]) / 2.0 else sorted[mid]
    }

    private fun detrendLinear(values: DoubleArray): DoubleArray {
        val n = values.size
        if (n < 2) return values.copyOf()
        val xMean = (n - 1) / 2.0
        val yMean = values.average()
        var num = 0.0
        var den = 0.0
        for (i in values.indices) {
            val dx = i - xMean
            num += dx * (values[i] - yMean)
            den += dx * dx
        }
        val slope = if (den != 0.0) num / den else 0.0
        val intercept = yMean - slope * xMean
        return DoubleArray(n) { values[it] - (slope * it + intercept) }
    }

    private fun hannWindow(n: Int): DoubleArray {
        if (n <= 1) return DoubleArray(n) { 1.0 }
        return DoubleArray(n) { i -> 0.5 - 0.5 * cos(2.0 * Math.PI * i / (n - 1)) }
    }

    private fun nextPowerOfTwo(n: Int): Int {
        var p = 1
        while (p < n) p = p shl 1
        return p.coerceAtLeast(1)
    }

    /** FFT iterativa in-place (Cooley-Tukey). `real.size` deve ser potência de 2. */
    private fun fft(real: DoubleArray, imag: DoubleArray) {
        val n = real.size
        if (n <= 1) return

        var j = 0
        for (i in 1 until n) {
            var bit = n shr 1
            while (j and bit != 0) {
                j = j xor bit
                bit = bit shr 1
            }
            j = j or bit
            if (i < j) {
                var tmp = real[i]; real[i] = real[j]; real[j] = tmp
                tmp = imag[i]; imag[i] = imag[j]; imag[j] = tmp
            }
        }

        var len = 2
        while (len <= n) {
            val ang = -2.0 * Math.PI / len
            val wr = cos(ang)
            val wi = sin(ang)
            var i = 0
            while (i < n) {
                var curWr = 1.0
                var curWi = 0.0
                for (k in 0 until len / 2) {
                    val uR = real[i + k]
                    val uI = imag[i + k]
                    val vR = real[i + k + len / 2] * curWr - imag[i + k + len / 2] * curWi
                    val vI = real[i + k + len / 2] * curWi + imag[i + k + len / 2] * curWr
                    real[i + k] = uR + vR
                    imag[i + k] = uI + vI
                    real[i + k + len / 2] = uR - vR
                    imag[i + k + len / 2] = uI - vI
                    val nextWr = curWr * wr - curWi * wi
                    val nextWi = curWr * wi + curWi * wr
                    curWr = nextWr
                    curWi = nextWi
                }
                i += len
            }
            len = len shl 1
        }
    }
}
