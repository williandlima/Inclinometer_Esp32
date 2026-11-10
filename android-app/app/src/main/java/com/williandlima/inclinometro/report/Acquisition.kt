package com.williandlima.inclinometro.report

import com.williandlima.inclinometro.datasource.AngleReading
import com.williandlima.inclinometro.limits.SessionInfo

/**
 * Resumo da aquisição que alimenta o relatório em PDF — mesma regra do app
 * desktop (`python-app/report/acquisition.py`).
 *
 * O relatório usa as leituras de UMA aquisição (uma sessão do histórico):
 * - começa no "Iniciar", ou no "Resetar limites"/"Calibrar" com a leitura em
 *   andamento (os dois abrem uma aquisição nova, porque mín/máx de antes do
 *   reset não valem mais);
 * - termina no "Parar" ou quando acaba o tempo programado; gerado com a
 *   leitura em andamento, o relatório usa os dados até o momento.
 *
 * Kotlin puro (sem Android), para a tela e o relatório dizerem a mesma coisa
 * e para poder ser testado isoladamente (`app/src/test`).
 */
object Acquisition {
    /** Tempos de aquisição oferecidos na tela, em segundos. `null` = livre. */
    val DURATIONS_S: List<Int?> = listOf(null, 60, 5 * 60, 10 * 60, 30 * 60, 60 * 60)

    /** Intervalo sem leitura a partir do qual o relatório aponta uma interrupção. */
    const val GAP_THRESHOLD_MS = 2000L

    data class Gap(val startMs: Long, val endMs: Long) {
        val durationMs: Long get() = endMs - startMs
    }

    data class Summary(
        val startedAt: Long?,
        val endedAt: Long?, // null = aquisição em andamento
        val plannedDurationS: Int?,
        val firstReadingAt: Long?,
        val lastReadingAt: Long?,
        val nReadings: Int,
        val nPanReadings: Int,
        val gaps: List<Gap>,
    ) {
        val inProgress: Boolean get() = startedAt != null && endedAt == null

        /** Fim da janela do relatório: o "Parar", ou a última leitura se em andamento. */
        val endReference: Long? get() = endedAt ?: lastReadingAt

        val durationS: Double
            get() {
                val start = startedAt ?: firstReadingAt
                val end = endReference
                if (start == null || end == null) return 0.0
                return maxOf(0L, end - start) / 1000.0
            }

        val gapTotalS: Double get() = gaps.sumOf { it.durationMs } / 1000.0

        /** Leituras por segundo entre a primeira e a última leitura. */
        val meanRateHz: Double?
            get() {
                val first = firstReadingAt
                val last = lastReadingAt
                if (nReadings < 2 || first == null || last == null || last <= first) return null
                return (nReadings - 1) * 1000.0 / (last - first)
            }

        /** Parte da aquisição que tem leitura (descontadas interrupções e a espera da conexão). */
        val coveragePct: Double?
            get() {
                val first = firstReadingAt
                val last = lastReadingAt
                if (durationS <= 0.0 || first == null || last == null) return null
                val covered = (last - first) / 1000.0 - gapTotalS
                return (100.0 * covered / durationS).coerceIn(0.0, 100.0)
            }
    }

    fun summarize(session: SessionInfo?, readings: List<AngleReading>): Summary {
        val timestamps = readings.map { it.timestamp }.sorted()
        val gaps = timestamps.zipWithNext()
            .filter { (a, b) -> b - a > GAP_THRESHOLD_MS }
            .map { (a, b) -> Gap(a, b) }
        return Summary(
            startedAt = session?.startedAt ?: timestamps.firstOrNull(),
            endedAt = if (session != null) session.endedAt else timestamps.lastOrNull(),
            plannedDurationS = session?.plannedDurationS,
            firstReadingAt = timestamps.firstOrNull(),
            lastReadingAt = timestamps.lastOrNull(),
            nReadings = readings.size,
            nPanReadings = readings.count { it.panDeg != null },
            gaps = gaps,
        )
    }

    /** Duração legível: "45 s", "5 min 03 s", "1 h 02 min 05 s". */
    fun formatDuration(seconds: Double?): String {
        if (seconds == null) return "-"
        val total = Math.round(seconds)
        val h = total / 3600
        val m = (total % 3600) / 60
        val s = total % 60
        return when {
            h > 0 -> "%d h %02d min %02d s".format(h, m, s)
            m > 0 -> "%d min %02d s".format(m, s)
            else -> "$s s"
        }
    }

    /** Rótulo de um tempo de aquisição programado (o mesmo da tela). */
    fun formatPlanned(plannedS: Int?): String = when {
        plannedS == null -> "Livre (até \"Parar\")"
        plannedS >= 3600 && plannedS % 3600 == 0 -> "${plannedS / 3600} h"
        plannedS >= 60 && plannedS % 60 == 0 -> "${plannedS / 60} min"
        else -> formatDuration(plannedS.toDouble())
    }

    /** Cronômetro da tela: "03:12" ou "1:02:05". */
    fun formatClock(seconds: Long): String {
        val total = maxOf(0L, seconds)
        val h = total / 3600
        val m = (total % 3600) / 60
        val s = total % 60
        return if (h > 0) "%d:%02d:%02d".format(h, m, s) else "%02d:%02d".format(m, s)
    }
}
