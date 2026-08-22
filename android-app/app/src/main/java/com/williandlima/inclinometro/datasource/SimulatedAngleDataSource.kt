package com.williandlima.inclinometro.datasource

import kotlin.math.PI
import kotlin.math.cos
import kotlin.math.sin
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.flow

// Velocidade e cadência do pan simulado — na mesma ordem de grandeza do motor
// real (~20-30°/s em rajadas de poucos segundos).
private const val PAN_MOVE_RATE_DPS = 20.0
private const val PAN_HOLD_MS = 12_000L
// A primeira rajada sai bem antes do intervalo normal: com PAN_HOLD_MS
// inteiro aqui, quem inicia a leitura ficaria 12s olhando um eixo cravado,
// com cara de app quebrado, antes de ver qualquer movimento.
private const val PAN_FIRST_MOVE_MS = 2_000L

// Vibração sintética do eixo de pan: frequência diferente da do tilt, para os
// dois espectros do relatório não ficarem idênticos, e um bias de giroscópio
// somado à taxa, para exercitar a remoção de tendência da conversão.
private const val PAN_VIB_FREQ_HZ = 2.1
private const val PAN_VIB_AMPLITUDE_DEG = 0.08
private const val PAN_VIB_BIAS_DPS = 0.3

/**
 * Fonte de dados simulada: gera ângulos sintéticos sem hardware real.
 *
 * Usada para desenvolver e testar o app sem o ESP32 conectado, com os mesmos
 * parâmetros padrão do app desktop (Python) para gerar dados comparáveis. Os
 * dois eixos têm comportamentos deliberadamente diferentes, imitando o real:
 * - **Tilt**: oscilação senoidal contínua dentro de -60° a +60°, somada a
 *   ruído gaussiano — é um eixo que se move o tempo todo (vento no mastro).
 * - **Pan**: fica parado a maior parte do tempo e se desloca em rajadas até
 *   uma nova posição, que é o padrão de uso real do azimute (e a razão de o
 *   firmware conseguir medi-lo por giroscópio + ZUPT). Sem ruído entre os
 *   movimentos, porque o ZUPT do firmware congela a leitura quando parado.
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

    // Estado do eixo de pan: posição atual, alvo do movimento em curso e
    // quando a próxima rajada começa.
    @Volatile private var panRawDeg: Double = 0.0
    @Volatile private var panOffsetDeg: Double = 0.0
    private var panTargetDeg: Double = 0.0
    private var panNextMoveAt: Long = 0L
    private var panLastTickMs: Long = 0L

    /**
     * Avança o eixo de pan e devolve o valor relativo ao zero calibrado. Move
     * em direção ao alvo a [PAN_MOVE_RATE_DPS]; ao chegar, fica parado até a
     * próxima rajada.
     */
    private fun advancePan(nowMs: Long, random: java.util.Random): Double {
        val dtS = ((nowMs - panLastTickMs).coerceAtLeast(0L)) / 1000.0
        panLastTickMs = nowMs

        val remaining = panTargetDeg - panRawDeg
        if (kotlin.math.abs(remaining) > 1e-6) {
            val step = PAN_MOVE_RATE_DPS * dtS
            if (step >= kotlin.math.abs(remaining)) {
                panRawDeg = panTargetDeg
                panNextMoveAt = nowMs + PAN_HOLD_MS
            } else {
                panRawDeg += if (remaining > 0) step else -step
            }
        } else if (nowMs >= panNextMoveAt) {
            panTargetDeg = PAN_MIN_DEG * 0.7 + random.nextDouble() * (PAN_MAX_DEG - PAN_MIN_DEG) * 0.7
        }

        return panRawDeg - panOffsetDeg
    }

    override fun readings(): Flow<AngleReading> = flow {
        val random = java.util.Random()
        val t0 = System.currentTimeMillis()
        panLastTickMs = t0
        panNextMoveAt = t0 + PAN_FIRST_MOVE_MS
        while (true) {
            val now = System.currentTimeMillis()
            val elapsedS = (now - t0) / 1000.0
            var raw = centerDeg + amplitudeDeg * sin(2 * PI * elapsedS / periodS)
            raw += random.nextGaussian() * noiseStdDeg
            lastRawDeg = raw
            val angle = (raw - offsetDeg).coerceIn(ANGLE_MIN_DEG, ANGLE_MAX_DEG)
            val pan = advancePan(now, random).coerceIn(PAN_MIN_DEG, PAN_MAX_DEG)
            emit(AngleReading(angleDeg = angle, timestamp = now, panDeg = pan))
            delay(pollIntervalMs)
        }
    }

    override val supportsCalibration: Boolean = true

    /**
     * Zera os dois eixos, como o firmware real faz no mesmo comando.
     */
    override suspend fun calibrate() {
        offsetDeg = lastRawDeg
        panOffsetDeg = panRawDeg
    }

    override val supportsVibrationCapture: Boolean = true

    /**
     * Gera uma série sintética de "vibração" em torno de 0° (posição de
     * calibração) nos dois eixos, só para exercitar todo o fluxo de
     * captura/estatística/relatório sem hardware real (mesmo gerador usado no
     * app desktop):
     *
     * - **tilt**: soma de duas oscilações de baixa amplitude, em frequências
     *   plausíveis para balanço de mastro sob vento (~1.3Hz) e vibração
     *   mecânica (~5Hz), mais ruído;
     * - **pan**: gerado como **velocidade angular**, igual ao que o firmware
     *   envia — a derivada de uma oscilação de [PAN_VIB_AMPLITUDE_DEG] a
     *   [PAN_VIB_FREQ_HZ] tem amplitude `A*2*PI*f` em graus/s. Vai somado a um
     *   bias constante, de propósito: é ele que exercita a remoção de
     *   tendência linear da conversão taxa→ângulo.
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
        val angles = DoubleArray(totalSamples)
        val panRates = DoubleArray(totalSamples)
        val panRateAmplitude = PAN_VIB_AMPLITUDE_DEG * 2 * PI * PAN_VIB_FREQ_HZ
        for (i in 0 until totalSamples) {
            val now = System.currentTimeMillis()
            val elapsedS = (now - t0) / 1000.0
            angles[i] = 0.15 * sin(2 * PI * 1.3 * elapsedS) +
                0.05 * sin(2 * PI * 5.0 * elapsedS + 0.7) +
                random.nextGaussian() * 0.03
            panRates[i] = panRateAmplitude * cos(2 * PI * PAN_VIB_FREQ_HZ * elapsedS) +
                PAN_VIB_BIAS_DPS +
                random.nextGaussian() * 0.05
            onProgress(((i + 1) * 100) / totalSamples)
            delay(intervalMs)
        }
        return VibrationReadings.build(angles, panRates, rateHz, t0)
    }
}
