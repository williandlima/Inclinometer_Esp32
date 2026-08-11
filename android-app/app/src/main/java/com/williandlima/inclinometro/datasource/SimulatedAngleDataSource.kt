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
 * estarem prontos. Gera uma oscilação senoidal dentro da faixa 0-120°, somada
 * a ruído gaussiano, com os mesmos parâmetros padrão do app desktop (Python)
 * para gerar dados comparáveis durante os testes.
 */
class SimulatedAngleDataSource(
    private val centerDeg: Double = 60.0,
    private val amplitudeDeg: Double = 55.0,
    private val periodS: Double = 20.0,
    private val noiseStdDeg: Double = 0.3,
    private val pollIntervalMs: Long = 250L,
) : AngleDataSource {

    override val label: String = "Simulação"

    override fun readings(): Flow<AngleReading> = flow {
        val random = java.util.Random()
        val t0 = System.currentTimeMillis()
        while (true) {
            val now = System.currentTimeMillis()
            val elapsedS = (now - t0) / 1000.0
            var angle = centerDeg + amplitudeDeg * sin(2 * PI * elapsedS / periodS)
            angle += random.nextGaussian() * noiseStdDeg
            angle = angle.coerceIn(ANGLE_MIN_DEG, ANGLE_MAX_DEG)
            emit(AngleReading(angleDeg = angle, timestamp = now))
            delay(pollIntervalMs)
        }
    }
}
