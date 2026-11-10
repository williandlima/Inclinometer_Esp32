package com.williandlima.inclinometro.limits.db

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.Query
import androidx.room.Update

@Dao
interface InclinometerDao {
    @Insert
    suspend fun insertSession(session: SessionEntity): Long

    @Update
    suspend fun updateSession(session: SessionEntity)

    @Query("SELECT * FROM sessions WHERE id = :sessionId")
    suspend fun getSession(sessionId: Long): SessionEntity?

    @Query("SELECT * FROM sessions ORDER BY startedAt DESC")
    suspend fun listSessions(): List<SessionEntity>

    @Insert
    suspend fun insertReading(reading: ReadingEntity)

    @Query("SELECT * FROM readings WHERE sessionId = :sessionId ORDER BY timestamp")
    suspend fun getReadings(sessionId: Long): List<ReadingEntity>

    @Insert
    suspend fun insertLimitEvent(event: LimitEventEntity)

    @Query("SELECT * FROM limit_events WHERE sessionId = :sessionId ORDER BY timestamp")
    suspend fun getLimitEvents(sessionId: Long): List<LimitEventEntity>

    @Insert
    suspend fun insertVibrationCapture(capture: VibrationCaptureEntity): Long

    @Query("SELECT * FROM vibration_captures ORDER BY startedAt DESC")
    suspend fun listVibrationCaptures(): List<VibrationCaptureEntity>

    @Insert
    suspend fun insertVibrationSamples(samples: List<VibrationSampleEntity>)

    @Query("SELECT * FROM vibration_samples WHERE captureId = :captureId ORDER BY timestamp")
    suspend fun getVibrationSamples(captureId: Long): List<VibrationSampleEntity>

    // ---- Histórico: contagem, exclusão e limpeza por retenção ----

    @Query("SELECT COUNT(*) FROM readings WHERE sessionId = :sessionId")
    suspend fun countReadings(sessionId: Long): Int

    @Query("SELECT COUNT(*) FROM readings")
    suspend fun countAllReadings(): Int

    @Query("DELETE FROM readings WHERE sessionId = :sessionId")
    suspend fun deleteReadings(sessionId: Long)

    @Query("DELETE FROM limit_events WHERE sessionId = :sessionId")
    suspend fun deleteLimitEvents(sessionId: Long)

    @Query("DELETE FROM sessions WHERE id = :sessionId")
    suspend fun deleteSessionRow(sessionId: Long)

    @Query("SELECT id FROM vibration_captures WHERE startedAt < :cutoff")
    suspend fun vibrationCaptureIdsBefore(cutoff: Long): List<Long>

    @Query("DELETE FROM vibration_samples WHERE captureId = :captureId")
    suspend fun deleteVibrationSamples(captureId: Long)

    @Query("DELETE FROM vibration_captures WHERE id = :captureId")
    suspend fun deleteVibrationCaptureRow(captureId: Long)
}
