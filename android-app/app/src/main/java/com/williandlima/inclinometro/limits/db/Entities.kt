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
