package com.williandlima.inclinometro.limits

import com.williandlima.inclinometro.datasource.AngleReading
import kotlin.math.PI
import kotlin.math.sqrt

/** Estatísticas de uma captura de vibração — equivalente ao
 * `limits/vibration_stats.py` do app desktop. */
data class VibrationStats(
    val nSamples: Int,
    val durationS: Double,
    val meanDeg: Double,
    val stdDevDeg: Double,
    val rmsDeg: Double,
    val peakToPeakDeg: Double,
    val minDeg: Double,
    val maxDeg: Double,
    val dominantFreqHz: Double? = null,
    val dominantAmplitudeDeg: Double? = null,
    val dominantSnrDb: Double? = null,
)

/** Resultado completo da análise de vibração de um eixo. */
data class AxisAnalysis(
    val axis: LimitAxis,
    val stats: VibrationStats,
    val freqsHz: DoubleArray,
    val magnitudes: DoubleArray,
) {
    // DoubleArray usa identidade em equals/hashCode gerados, o que tornaria a
    // comparação desta data class inútil e enganosa; comparar pelo conteúdo.
    override fun equals(other: Any?): Boolean {
        if (this === other) return true
        if (other !is AxisAnalysis) return false
        return axis == other.axis &&
            stats == other.stats &&
            freqsHz.contentEquals(other.freqsHz) &&
            magnitudes.contentEquals(other.magnitudes)
    }

    override fun hashCode(): Int {
        var result = axis.hashCode()
        result = 31 * result + stats.hashCode()
        result = 31 * result + freqsHz.contentHashCode()
        result = 31 * result + magnitudes.contentHashCode()
        return result
    }
}

object VibrationStatsCalculator {

    /** Série do eixo pedido, em graus. */
    private fun axisValues(readings: List<AngleReading>, axis: LimitAxis): DoubleArray = when (axis) {
        LimitAxis.PAN -> readings.map {
            it.panDeg ?: error("Captura sem amostras do eixo de azimute.")
        }.toDoubleArray()
        LimitAxis.TILT -> readings.map { it.angleDeg }.toDoubleArray()
    }

    /** Velocidade angular bruta do azimute, em graus/s. */
    private fun panRates(readings: List<AngleReading>): DoubleArray =
        readings.map {
            it.panRateDps ?: error("Captura sem a velocidade angular do eixo de azimute.")
        }.toDoubleArray()

    /** True se a captura tem o eixo de azimute em todas as amostras. */
    fun hasPanSamples(readings: List<AngleReading>): Boolean =
        readings.isNotEmpty() && readings.all { it.panDeg != null && it.panRateDps != null }

    fun computeStats(readings: List<AngleReading>, axis: LimitAxis = LimitAxis.TILT): VibrationStats {
        require(readings.isNotEmpty()) { "Nenhuma amostra na captura." }
        val values = axisValues(readings, axis).toList()
        val mean = values.average()
        val variance = values.sumOf { (it - mean) * (it - mean) } / values.size
        val stdDev = sqrt(variance)
        val rms = sqrt(values.sumOf { it * it } / values.size)
        val durationS = (readings.last().timestamp - readings.first().timestamp) / 1000.0
        return VibrationStats(
            nSamples = readings.size,
            durationS = durationS,
            meanDeg = mean,
            stdDevDeg = stdDev,
            rmsDeg = rms,
            peakToPeakDeg = (values.max() - values.min()),
            minDeg = values.min(),
            maxDeg = values.max(),
        )
    }

    /**
     * Roda o pipeline inteiro (estatísticas + espectro + pico dominante) num
     * eixo de uma captura. Equivalente a `analyze_axis` do app desktop.
     *
     * A diferença entre os eixos está em QUAL espectro alimenta a detecção do
     * pico. [Fft.findDominantPeak] compara o pico com a mediana do espectro,
     * o que só é justo se o piso de ruído for plano:
     *
     * - **tilt**: o ruído do acelerômetro já é branco no ângulo, então o
     *   espectro do ângulo serve direto;
     * - **azimute**: o ruído do giroscópio é branco na TAXA. O espectro do
     *   ângulo (que é a integral) tem ruído de passeio aleatório, caindo com
     *   1/f² — nele a mediana global fica dominada pelas frequências altas e
     *   qualquer bin de baixa frequência vira um "pico" enorme. Medido em
     *   teste no app desktop: ruído puro era apontado como frequência
     *   dominante em 100% das tentativas. Por isso a detecção roda no
     *   espectro da taxa, e só a amplitude do pico é convertida para graus.
     *
     * O espectro devolvido para os gráficos é sempre em graus, nos dois casos.
     */
    fun analyzeAxis(
        readings: List<AngleReading>,
        rateHz: Int,
        axis: LimitAxis = LimitAxis.TILT,
    ): AxisAnalysis {
        require(readings.isNotEmpty()) { "Nenhuma amostra na captura." }
        val stats = computeStats(readings, axis)

        val freqs: DoubleArray
        val magnitudes: DoubleArray
        val peak: Fft.DominantPeak?
        val amplitudeDeg: Double?

        if (axis == LimitAxis.PAN) {
            val (f, rateMagnitudes) = Fft.computeSpectrum(panRates(readings), rateHz.toDouble())
            freqs = f
            peak = Fft.findDominantPeak(freqs, rateMagnitudes)
            magnitudes = Fft.rateSpectrumToAngle(freqs, rateMagnitudes)
            amplitudeDeg = peak
                ?.takeIf { it.freqHz > 0 }
                ?.let { it.amplitudeDeg / (2.0 * PI * it.freqHz) }
        } else {
            val (f, m) = Fft.computeSpectrum(axisValues(readings, axis), rateHz.toDouble())
            freqs = f
            magnitudes = m
            peak = Fft.findDominantPeak(freqs, magnitudes)
            amplitudeDeg = peak?.amplitudeDeg
        }

        val withPeak = if (peak != null && amplitudeDeg != null) {
            stats.copy(
                dominantFreqHz = peak.freqHz,
                dominantAmplitudeDeg = amplitudeDeg,
                dominantSnrDb = peak.snrDb,
            )
        } else {
            stats
        }
        return AxisAnalysis(axis = axis, stats = withPeak, freqsHz = freqs, magnitudes = magnitudes)
    }
}
