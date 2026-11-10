package com.williandlima.inclinometro

import com.williandlima.inclinometro.datasource.AngleReading
import com.williandlima.inclinometro.datasource.ConnectionMode
import com.williandlima.inclinometro.limits.HistoryExport
import com.williandlima.inclinometro.limits.LimitAxis
import com.williandlima.inclinometro.limits.LimitEvent
import com.williandlima.inclinometro.limits.LimitKind
import com.williandlima.inclinometro.limits.SessionInfo
import com.williandlima.inclinometro.limits.retentionLabel
import com.williandlima.inclinometro.report.Acquisition
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Regras da aquisição e do CSV — as mesmas do app desktop
 * (`sim/relatorio_test.py`). Kotlin puro: roda na JVM, sem aparelho.
 */
class AcquisitionTest {
    private val t0 = 1_700_000_000_000L

    /** Leituras a 5 Hz de `fromS` a `toS` segundos depois de t0. */
    private fun readings(fromS: Int, toS: Int, pan: Boolean = true): List<AngleReading> =
        (fromS * 5 until toS * 5).map { i ->
            AngleReading(angleDeg = 1.0 + i * 0.01, timestamp = t0 + i * 200L, panDeg = if (pan) -2.5 else null)
        }

    private fun session(endS: Int?, planned: Int? = null) = SessionInfo(
        id = 7,
        startedAt = t0,
        endedAt = endS?.let { t0 + it * 1000L },
        mode = ConnectionMode.REAL,
        plannedDurationS = planned,
        appVersion = "2.4.0",
        firmwareVersion = "1.6.23",
    )

    @Test
    fun aquisicaoContinuaSemInterrupcao() {
        val acq = Acquisition.summarize(session(endS = 60, planned = 60), readings(0, 60))
        assertEquals(300, acq.nReadings)
        assertEquals(300, acq.nPanReadings)
        assertEquals(60.0, acq.durationS, 1e-9)
        assertTrue(acq.gaps.isEmpty())
        assertEquals(5.0, acq.meanRateHz!!, 0.01)
        assertTrue(acq.coveragePct!! > 99.0)
        assertFalse(acq.inProgress)
    }

    @Test
    fun interrupcaoDeDezSegundosApareceNoResumo() {
        val acq = Acquisition.summarize(session(endS = 60), readings(0, 20) + readings(30, 60))
        assertEquals(1, acq.gaps.size)
        assertEquals(10.2, acq.gapTotalS, 0.01)
        assertEquals(83.0, acq.coveragePct!!, 1.0)
    }

    @Test
    fun perderUmaLeituraNaoContaComoInterrupcao() {
        val all = readings(0, 10)
        val acq = Acquisition.summarize(session(endS = 10), all.filterIndexed { i, _ -> i != 20 })
        assertTrue(acq.gaps.isEmpty())
    }

    @Test
    fun emAndamentoUsaAUltimaLeituraComoFim() {
        val acq = Acquisition.summarize(session(endS = null), readings(0, 30))
        assertTrue(acq.inProgress)
        assertEquals(29.8, acq.durationS, 1e-9)
    }

    @Test
    fun semLeiturasNaoQuebra() {
        val acq = Acquisition.summarize(session(endS = 5), emptyList())
        assertEquals(0, acq.nReadings)
        assertNull(acq.meanRateHz)
        assertNull(acq.coveragePct)
        assertEquals(5.0, acq.durationS, 1e-9)
    }

    @Test
    fun firmwareSemAzimute() {
        val acq = Acquisition.summarize(session(endS = 10), readings(0, 10, pan = false))
        assertEquals(0, acq.nPanReadings)
    }

    @Test
    fun rotulos() {
        assertEquals("45 s", Acquisition.formatDuration(45.0))
        assertEquals("5 min 03 s", Acquisition.formatDuration(303.0))
        assertEquals("1 h 02 min 05 s", Acquisition.formatDuration(3725.0))
        assertEquals("Livre (até \"Parar\")", Acquisition.formatPlanned(null))
        assertEquals("1 min", Acquisition.formatPlanned(60))
        assertEquals("30 min", Acquisition.formatPlanned(1800))
        assertEquals("1 h", Acquisition.formatPlanned(3600))
        assertEquals("03:12", Acquisition.formatClock(192))
        assertEquals("1:02:05", Acquisition.formatClock(3725))
        assertEquals("Sempre", retentionLabel(null))
        assertEquals("90 dias", retentionLabel(90))
        assertEquals("1 ano", retentionLabel(365))
    }

    @Test
    fun csvAbreNoExcelEmPortugues() {
        val rs = listOf(
            AngleReading(angleDeg = 1.25, timestamp = t0 + 200, panDeg = -3.5),
            AngleReading(angleDeg = -0.5, timestamp = t0 + 400, panDeg = null),
        )
        val events = listOf(LimitEvent(LimitKind.MAX, rs[0], LimitAxis.TILT))
        val csv = HistoryExport.sessionCsv(session(endS = 1), rs, events)
        assertTrue(csv.startsWith("﻿# Inclinometro - aquisicao 7\n"))
        val lines = csv.trimEnd().lines()
        assertTrue(lines.any { it == "# app: 2.4.0; firmware: 1.6.23" })
        assertTrue(lines.any { it.startsWith("# limite: TILT;MAX;1,25;") })
        val header = lines.indexOf("data_hora;t_s;inclinacao_graus;azimute_graus")
        assertTrue(header > 0)
        assertEquals(header + 3, lines.size)
        assertTrue(lines[header + 1].endsWith(";0,200;1,25;-3,50"))
        // Firmware sem azimute: coluna vazia, não zero.
        assertTrue(lines[header + 2].endsWith(";0,400;-0,50;"))
    }
}
