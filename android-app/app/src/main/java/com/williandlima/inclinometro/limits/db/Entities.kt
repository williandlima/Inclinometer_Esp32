package com.williandlima.inclinometro.limits.db

import androidx.room.Entity
import androidx.room.PrimaryKey

@Entity(tableName = "sessions")
data class SessionEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val startedAt: Long,
    val endedAt: Long? = null,
    val mode: String,
)

@Entity(tableName = "readings")
data class ReadingEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val sessionId: Long,
    val timestamp: Long,
    val angleDeg: Double,
    // Nulo quando o firmware conectado não media azimute (anterior à v1.2.0).
    val panDeg: Double? = null,
)

@Entity(tableName = "limit_events")
data class LimitEventEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val sessionId: Long,
    val kind: String,
    val angleDeg: Double,
    val timestamp: Long,
    // Guarda os dois eixos da leitura (e não só o valor do eixo do evento)
    // para a releitura reconstruir o AngleReading inteiro.
    val axis: String = "TILT",
    val panDeg: Double? = null,
)

@Entity(tableName = "vibration_captures")
data class VibrationCaptureEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val startedAt: Long,
    val mode: String,
    val durationS: Int,
    val rateHz: Int,
)

@Entity(tableName = "vibration_samples")
data class VibrationSampleEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val captureId: Long,
    val timestamp: Long,
    val angleDeg: Double,
    // Nulos quando o firmware conectado não amostrava azimute no Modo
    // Vibração (anterior à v1.3.0). São dois campos porque a análise
    // espectral precisa da taxa e os gráficos precisam do ângulo — ver
    // AngleReading.panRateDps.
    val panDeg: Double? = null,
    val panRateDps: Double? = null,
)
