package com.williandlima.inclinometro.limits

import kotlin.math.cos
import kotlin.math.hypot
import kotlin.math.sin

/**
 * FFT real simples (Cooley-Tukey iterativo, radix-2), usada por
 * [VibrationStats] para o espectro de frequência da captura de vibração —
 * equivalente ao `numpy.fft.rfft` usado no app desktop, sem depender de
 * biblioteca externa.
 */
internal object Fft {

    /**
     * Retorna `(frequências_hz, magnitude)` do espectro de `values`
     * (amostras igualmente espaçadas em `rateHz`). A média é removida antes
     * da FFT (componente contínua), e o array é completado com zeros até a
     * próxima potência de 2.
     */
    fun computeSpectrum(values: DoubleArray, rateHz: Double): Pair<DoubleArray, DoubleArray> {
        require(values.isNotEmpty()) { "Nenhuma amostra na captura." }

        val mean = values.average()
        val n = nextPowerOfTwo(values.size)
        val real = DoubleArray(n)
        val imag = DoubleArray(n)
        for (i in values.indices) real[i] = values[i] - mean

        fft(real, imag)

        val half = n / 2 + 1
        val freqs = DoubleArray(half) { it * rateHz / n }
        val magnitudes = DoubleArray(half) { hypot(real[it], imag[it]) / values.size }
        return freqs to magnitudes
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
