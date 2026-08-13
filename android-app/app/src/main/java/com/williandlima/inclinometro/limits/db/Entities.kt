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
)

@Entity(tableName = "limit_events")
data class LimitEventEntity(
    @PrimaryKey(autoGenerate = true) val id: Long = 0,
    val sessionId: Long,
    val kind: String,
    val angleDeg: Double,
    val timestamp: Long,
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
)
