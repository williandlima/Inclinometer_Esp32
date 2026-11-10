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
    /** Tempo programado da aquisição, em segundos; `null` = livre (até o "Parar"). */
    val plannedDurationS: Int? = null,
    val appVersion: String? = null,
    val firmwareVersion: String? = null,
)

/** Uma aquisição na lista do Histórico. */
data class SessionSummary(val info: SessionInfo, val readingCount: Int)

/** O que a limpeza do histórico apagou. */
data class PruneResult(val sessions: Int = 0, val readings: Int = 0, val captures: Int = 0) {
    val nothing: Boolean get() = sessions == 0 && captures == 0
}

/**
 * Opções de "Manter histórico por" (dias; `null` = sempre), as mesmas do app
 * desktop. O banco gravava cada leitura (~5 por segundo) e nunca apagava nada.
 */
val RETENTION_OPTIONS_DAYS: List<Int?> = listOf(30, 90, 180, 365, null)
const val DEFAULT_RETENTION_DAYS = 90

fun retentionLabel(days: Int?): String = when (days) {
    null -> "Sempre"
    365 -> "1 ano"
    else -> "$days dias"
}

data class VibrationCaptureInfo(
    val id: Long,
    val startedAt: Long,
    val mode: ConnectionMode,
    val durationS: Int,
    val rateHz: Int,
)

/** Persistência do histórico de leituras e eventos de limite (Room/SQLite). */
class HistoryRepository(private val dao: InclinometerDao) {

    suspend fun startSession(mode: ConnectionMode, plannedDurationS: Int? = null, appVersion: String? = null): Long =
        dao.insertSession(
            SessionEntity(
                startedAt = System.currentTimeMillis(),
                mode = mode.name,
                plannedDurationS = plannedDurationS,
                appVersion = appVersion,
            ),
        )

    /** Rastreabilidade: a aquisição guarda o firmware com que foi feita. */
    suspend fun setFirmwareVersion(sessionId: Long, firmwareVersion: String) {
        val session = dao.getSession(sessionId) ?: return
        if (session.firmwareVersion != firmwareVersion) {
            dao.updateSession(session.copy(firmwareVersion = firmwareVersion))
        }
    }

    /** Aquisições com pelo menos uma leitura, da mais recente para a mais antiga. */
    suspend fun listSessionSummaries(): List<SessionSummary> =
        dao.listSessions()
            .map { SessionSummary(it.toSessionInfo(), dao.countReadings(it.id)) }
            .filter { it.readingCount > 0 }

    suspend fun latestSessionWithReadings(): SessionInfo? = listSessionSummaries().firstOrNull()?.info

    suspend fun countReadings(sessionId: Long): Int = dao.countReadings(sessionId)

    suspend fun countAllReadings(): Int = dao.countAllReadings()

    suspend fun deleteSession(sessionId: Long) {
        dao.deleteReadings(sessionId)
        dao.deleteLimitEvents(sessionId)
        dao.deleteSessionRow(sessionId)
    }

    /**
     * Apaga aquisições e capturas de vibração mais antigas que
     * [retentionDays] (`null` = não apaga por idade) e as aquisições vazias
     * (abertas e fechadas sem nenhuma leitura). Nunca toca em [keepSessionId],
     * a aquisição em andamento.
     */
    suspend fun prune(
        retentionDays: Int?,
        keepSessionId: Long?,
        now: Long = System.currentTimeMillis(),
    ): PruneResult {
        val cutoff = retentionDays?.let { now - it * 86_400_000L }
        var sessions = 0
        var readings = 0
        var captures = 0
        for (session in dao.listSessions()) {
            if (session.id == keepSessionId) continue
            val n = dao.countReadings(session.id)
            val old = cutoff != null && session.startedAt < cutoff
            if (old || n == 0) {
                deleteSession(session.id)
                // Aquisição vazia não conta: o usuário nunca a viu.
                if (n > 0) {
                    sessions++
                    readings += n
                }
            }
        }
        if (cutoff != null) {
            for (captureId in dao.vibrationCaptureIdsBefore(cutoff)) {
                dao.deleteVibrationSamples(captureId)
                dao.deleteVibrationCaptureRow(captureId)
                captures++
            }
        }
        return PruneResult(sessions, readings, captures)
    }

    suspend fun endSession(sessionId: Long) {
        val session = dao.getSession(sessionId) ?: return
        dao.updateSession(session.copy(endedAt = System.currentTimeMillis()))
    }

    suspend fun addReading(sessionId: Long, reading: AngleReading) {
        dao.insertReading(
            ReadingEntity(
                sessionId = sessionId,
                timestamp = reading.timestamp,
                angleDeg = reading.angleDeg,
                panDeg = reading.panDeg,
            )
        )
    }

    suspend fun addLimitEvent(sessionId: Long, event: LimitEvent) {
        dao.insertLimitEvent(
            LimitEventEntity(
                sessionId = sessionId,
                kind = event.kind.name,
                angleDeg = event.reading.angleDeg,
                timestamp = event.reading.timestamp,
                axis = event.axis.name,
                panDeg = event.reading.panDeg,
            )
        )
    }

    suspend fun getSession(sessionId: Long): SessionInfo? = dao.getSession(sessionId)?.toSessionInfo()

    suspend fun listSessions(): List<SessionInfo> = dao.listSessions().map { it.toSessionInfo() }

    suspend fun getReadings(sessionId: Long): List<AngleReading> =
        dao.getReadings(sessionId).map {
            AngleReading(angleDeg = it.angleDeg, timestamp = it.timestamp, panDeg = it.panDeg)
        }

    suspend fun getLimitEvents(sessionId: Long): List<LimitEvent> =
        dao.getLimitEvents(sessionId).map {
            LimitEvent(
                kind = LimitKind.valueOf(it.kind),
                reading = AngleReading(angleDeg = it.angleDeg, timestamp = it.timestamp, panDeg = it.panDeg),
                axis = LimitAxis.valueOf(it.axis),
            )
        }

    private fun SessionEntity.toSessionInfo() =
        SessionInfo(
            id = id,
            startedAt = startedAt,
            endedAt = endedAt,
            mode = ConnectionMode.valueOf(mode),
            plannedDurationS = plannedDurationS,
            appVersion = appVersion,
            firmwareVersion = firmwareVersion,
        )

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
            readings.map {
                VibrationSampleEntity(
                    captureId = captureId,
                    timestamp = it.timestamp,
                    angleDeg = it.angleDeg,
                    panDeg = it.panDeg,
                    panRateDps = it.panRateDps,
                )
            }
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
        dao.getVibrationSamples(captureId).map {
            AngleReading(
                angleDeg = it.angleDeg,
                timestamp = it.timestamp,
                panDeg = it.panDeg,
                panRateDps = it.panRateDps,
            )
        }
}
