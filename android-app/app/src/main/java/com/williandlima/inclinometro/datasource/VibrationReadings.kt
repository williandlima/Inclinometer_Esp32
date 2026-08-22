package com.williandlima.inclinometro.datasource

/**
 * Montagem das amostras de uma captura do Modo Vibração a partir das séries
 * brutas de cada eixo — equivalente a `build_vibration_readings` em
 * `python-app/data_source/base.py`, usado pelas duas fontes de dados.
 */
object VibrationReadings {

    /**
     * Converte a série de velocidade angular do azimute (graus/s) na variação
     * angular correspondente (graus).
     *
     * O firmware envia o eixo de azimute como TAXA, não como ângulo — ver
     * `firmware/src/VibrationCapture.h`. Aqui ela é integrada (regra do
     * trapézio) e a tendência linear resultante é removida.
     *
     * A remoção da tendência não é cosmética: o bias residual do giroscópio é
     * uma constante somada à taxa, e integrar uma constante dá exatamente uma
     * rampa linear. Tirar a reta ajustada elimina esse termo por construção, e
     * o que sobra é a oscilação em torno da posição média — que é o que o
     * ensaio de vibração quer medir.
     */
    fun panRatesToAngles(ratesDps: DoubleArray, rateHz: Double): DoubleArray {
        val n = ratesDps.size
        if (n == 0) return DoubleArray(0)
        if (n == 1) return DoubleArray(1)

        val dt = 1.0 / rateHz
        val angles = DoubleArray(n)
        for (i in 1 until n) {
            angles[i] = angles[i - 1] + (ratesDps[i - 1] + ratesDps[i]) * 0.5 * dt
        }

        // Ajuste de reta por mínimos quadrados, subtraída em seguida.
        var sumX = 0.0
        var sumY = 0.0
        var sumXY = 0.0
        var sumXX = 0.0
        for (i in 0 until n) {
            val x = i.toDouble()
            sumX += x
            sumY += angles[i]
            sumXY += x * angles[i]
            sumXX += x * x
        }
        val denom = n * sumXX - sumX * sumX
        if (denom != 0.0) {
            val slope = (n * sumXY - sumX * sumY) / denom
            val intercept = (sumY - slope * sumX) / n
            for (i in 0 until n) {
                angles[i] -= slope * i + intercept
            }
        }
        return angles
    }

    /**
     * Monta as amostras da captura. `panRatesDps` são velocidades angulares,
     * como o firmware as envia; passe `null` (ou um tamanho diferente do eixo
     * de tilt) quando o firmware conectado não fornecer o eixo de azimute —
     * as amostras saem com `panDeg`/`panRateDps` nulos.
     */
    fun build(
        anglesDeg: DoubleArray,
        panRatesDps: DoubleArray?,
        rateHz: Int,
        startMillis: Long,
    ): List<AngleReading> {
        val panAngles = if (panRatesDps != null && panRatesDps.size == anglesDeg.size) {
            panRatesToAngles(panRatesDps, rateHz.toDouble())
        } else {
            null
        }
        return anglesDeg.mapIndexed { i, angle ->
            AngleReading(
                angleDeg = angle,
                timestamp = startMillis + (i * 1000L) / rateHz,
                panDeg = panAngles?.get(i),
                panRateDps = if (panAngles != null) panRatesDps!![i] else null,
            )
        }
    }
}
