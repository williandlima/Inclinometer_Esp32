package com.williandlima.inclinometro.datasource

import kotlin.math.PI
import kotlin.math.sin
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow

/**
 * Fonte de dados simulada: gera ângulos sintéticos sem hardware real.
 *
 * Usada para desenvolver e testar o app antes do firmware/hardware do ESP32
 * estarem prontos. Gera uma oscilação senoidal dentro da faixa -60° a +60°,
 * somada a ruído gaussiano, com os mesmos parâmetros padrão do app desktop
 * (Python) para gerar dados comparáveis durante os testes.
 */
class SimulatedAngleDataSource(
    private val centerDeg: Double = 0.0,
    private val amplitudeDeg: Double = 12.0,
    private val periodS: Double = 45.0,
    // Ruído equivalente ao que o firmware entrega JÁ FILTRADO (filtro interno
    // do MPU6050 + média móvel, ver firmware/src/AngleSensor.h). A fonte
    // simulada substitui o conjunto sensor+firmware, então imitar o sinal cru
    // aqui daria uma falsa impressão de instabilidade que o hardware real não
    // tem mais.
    private val noiseStdDeg: Double = 0.015,
    private val pollIntervalMs: Long = 250L,
) : AngleDataSource {

    override val label: String = "Simulação"

    @Volatile private var offsetDeg: Double = 0.0
    @Volatile private var lastRawDeg: Double = centerDeg

    override fun readings(): Flow<AngleReading> = flow {
        val random = java.util.Random()
        val t0 = System.currentTimeMillis()
        while (true) {
            val now = System.currentTimeMillis()
            val elapsedS = (now - t0) / 1000.0
            var raw = centerDeg + amplitudeDeg * sin(2 * PI * elapsedS / periodS)
            raw += random.nextGaussian() * noiseStdDeg
            lastRawDeg = raw
            val angle = (raw - offsetDeg).coerceIn(ANGLE_MIN_DEG, ANGLE_MAX_DEG)
            emit(AngleReading(angleDeg = angle, timestamp = now))
            delay(pollIntervalMs)
        }
    }

    override val supportsCalibration: Boolean = true

    override suspend fun calibrate() {
        offsetDeg = lastRawDeg
    }

    override val supportsVibrationCapture: Boolean = true

    /**
     * Gera uma série sintética de "vibração" em torno de 0° (posição de
     * calibração): soma de duas oscilações de baixa amplitude, em
     * frequências plausíveis para balanço de mastro sob vento (~1.3Hz) e
     * vibração mecânica (~5Hz), mais ruído — só para exercitar todo o fluxo
     * de captura/estatística/relatório sem hardware real (mesmo gerador
     * usado no app desktop).
     */
    override suspend fun startVibrationCapture(
        durationS: Int,
        rateHz: Int,
        onProgress: (Int) -> Unit,
    ): List<AngleReading> {
        val intervalMs = (1000.0 / rateHz).toLong().coerceAtLeast(1)
        val totalSamples = (durationS * rateHz).coerceAtLeast(1)
        val random = java.util.Random()
        val t0 = System.currentTimeMillis()
        val readings = ArrayList<AngleReading>(totalSamples)
        for (i in 0 until totalSamples) {
            val now = System.currentTimeMillis()
            val elapsedS = (now - t0) / 1000.0
            val vib = 0.15 * sin(2 * PI * 1.3 * elapsedS) +
                0.05 * sin(2 * PI * 5.0 * elapsedS + 0.7) +
                random.nextGaussian() * 0.03
            readings.add(AngleReading(angleDeg = vib, timestamp = now))
            onProgress(((i + 1) * 100) / totalSamples)
            delay(intervalMs)
        }
        return readings
    }
}
