package com.williandlima.inclinometro.limits

import com.williandlima.inclinometro.datasource.AngleReading
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

object VibrationStatsCalculator {

    fun computeStats(readings: List<AngleReading>): VibrationStats {
        require(readings.isNotEmpty()) { "Nenhuma amostra na captura." }
        val values = readings.map { it.angleDeg }
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

    /** Retorna `(frequências_hz, amplitude_graus)` do espectro da variação angular. */
    fun computeFft(readings: List<AngleReading>, rateHz: Int): Pair<DoubleArray, DoubleArray> {
        require(readings.isNotEmpty()) { "Nenhuma amostra na captura." }
        val values = readings.map { it.angleDeg }.toDoubleArray()
        return Fft.computeSpectrum(values, rateHz.toDouble())
    }

    /** Retorna [stats] com os campos de pico dominante preenchidos a partir
     * do espectro já calculado (ou zerados, se nenhum pico for confiável).
     * A frequência dominante em si é interna a [Fft] — só os campos
     * (públicos, tipos primitivos) chegam a [VibrationStats]. */
    fun withDominantPeak(stats: VibrationStats, freqsHz: DoubleArray, magnitudes: DoubleArray): VibrationStats {
        val peak = Fft.findDominantPeak(freqsHz, magnitudes)
        return stats.copy(
            dominantFreqHz = peak?.freqHz,
            dominantAmplitudeDeg = peak?.amplitudeDeg,
            dominantSnrDb = peak?.snrDb,
        )
    }
}
