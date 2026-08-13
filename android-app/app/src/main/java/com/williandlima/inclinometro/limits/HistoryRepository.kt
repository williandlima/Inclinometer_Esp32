package com.williandlima.inclinometro.limits

import com.williandlima.inclinometro.datasource.AngleReading
import com.williandlima.inclinometro.datasource.ConnectionMode
import com.williandlima.inclinometro.limits.db.InclinometerDao
import com.williandlima.inclinometro.limits.db.LimitEventEntity
import com.williandlima.inclinometro.limits.db.ReadingEntity
import com.williandlima.inclinometro.limits.db.SessionEntity
import com.williandlima.inclinometro.limits.db.VibrationCaptureEntity
import com.williandlima.inclinometro.limits.db.VibrationSampleEntity

data class SessionInfo(
    val id: Long,
    val startedAt: Long,
    val endedAt: Long?,
    val mode: ConnectionMode,
)

data class VibrationCaptureInfo(
    val id: Long,
    val startedAt: Long,
    val mode: ConnectionMode,
    val durationS: Int,
    val rateHz: Int,
)

/** Persistência do histórico de leituras e eventos de limite (Room/SQLite). */
class HistoryRepository(private val dao: InclinometerDao) {

    suspend fun startSession(mode: ConnectionMode): Long =
        dao.insertSession(SessionEntity(startedAt = System.currentTimeMillis(), mode = mode.name))

    suspend fun endSession(sessionId: Long) {
        val session = dao.getSession(sessionId) ?: return
        dao.updateSession(session.copy(endedAt = System.currentTimeMillis()))
    }

    suspend fun addReading(sessionId: Long, reading: AngleReading) {
        dao.insertReading(
            ReadingEntity(sessionId = sessionId, timestamp = reading.timestamp, angleDeg = reading.angleDeg)
        )
    }

    suspend fun addLimitEvent(sessionId: Long, event: LimitEvent) {
        dao.insertLimitEvent(
            LimitEventEntity(
                sessionId = sessionId,
                kind = event.kind.name,
                angleDeg = event.reading.angleDeg,
                timestamp = event.reading.timestamp,
            )
        )
    }

    suspend fun getSession(sessionId: Long): SessionInfo? = dao.getSession(sessionId)?.toSessionInfo()

    suspend fun listSessions(): List<SessionInfo> = dao.listSessions().map { it.toSessionInfo() }

    suspend fun getReadings(sessionId: Long): List<AngleReading> =
        dao.getReadings(sessionId).map { AngleReading(angleDeg = it.angleDeg, timestamp = it.timestamp) }

    suspend fun getLimitEvents(sessionId: Long): List<LimitEvent> =
        dao.getLimitEvents(sessionId).map {
            LimitEvent(
                kind = LimitKind.valueOf(it.kind),
                reading = AngleReading(angleDeg = it.angleDeg, timestamp = it.timestamp),
            )
        }

    private fun SessionEntity.toSessionInfo() =
        SessionInfo(id = id, startedAt = startedAt, endedAt = endedAt, mode = ConnectionMode.valueOf(mode))

    suspend fun saveVibrationCapture(
        mode: ConnectionMode,
        durationS: Int,
        rateHz: Int,
        readings: List<AngleReading>,
    ): Long {
        val captureId = dao.insertVibrationCapture(
            VibrationCaptureEntity(
                startedAt = System.currentTimeMillis(),
                mode = mode.name,
                durationS = durationS,
                rateHz = rateHz,
            )
        )
        dao.insertVibrationSamples(
            readings.map { VibrationSampleEntity(captureId = captureId, timestamp = it.timestamp, angleDeg = it.angleDeg) }
        )
        return captureId
    }

    suspend fun listVibrationCaptures(): List<VibrationCaptureInfo> =
        dao.listVibrationCaptures().map {
            VibrationCaptureInfo(
                id = it.id,
                startedAt = it.startedAt,
                mode = ConnectionMode.valueOf(it.mode),
                durationS = it.durationS,
                rateHz = it.rateHz,
            )
        }

    suspend fun getVibrationSamples(captureId: Long): List<AngleReading> =
        dao.getVibrationSamples(captureId).map { AngleReading(angleDeg = it.angleDeg, timestamp = it.timestamp) }
}
