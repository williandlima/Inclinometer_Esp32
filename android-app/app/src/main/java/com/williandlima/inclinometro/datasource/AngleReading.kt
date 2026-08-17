package com.williandlima.inclinometro.datasource

/** Faixa física do inclinômetro (-60 a +60 graus). */
const val ANGLE_MIN_DEG = -60.0
const val ANGLE_MAX_DEG = 60.0

data class AngleReading(
    val angleDeg: Double,
    val timestamp: Long, // epoch millis
)

enum class ConnectionMode {
    SIMULATED,
    REAL,
}
