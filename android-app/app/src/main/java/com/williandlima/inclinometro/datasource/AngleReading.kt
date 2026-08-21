package com.williandlima.inclinometro.datasource

/** Faixa física do eixo de inclinação (-60 a +60 graus). */
const val ANGLE_MIN_DEG = -60.0
const val ANGLE_MAX_DEG = 60.0

/**
 * Faixa do eixo de azimute (pan). Espelha `PAN_MIN_DEG`/`PAN_MAX_DEG` de
 * `firmware/src/Config.h` — ainda é um placeholder ali, a ajustar quando a
 * mecânica do pan estiver definida.
 */
const val PAN_MIN_DEG = -90.0
const val PAN_MAX_DEG = 90.0

/**
 * Uma leitura dos eixos do inclinômetro.
 *
 * [panDeg] é opcional: fica `null` quando a fonte não fornece azimute — caso
 * de um ESP32 com firmware anterior à v1.2.0, que não expõe a characteristic
 * de pan. Todo o resto do app (limites, histórico, relatório) trata `null`
 * como "este eixo não foi medido" e o ignora, em vez de assumir zero.
 */
data class AngleReading(
    val angleDeg: Double,
    val timestamp: Long, // epoch millis
    val panDeg: Double? = null,
)

enum class ConnectionMode {
    SIMULATED,
    REAL,
}
