package com.williandlima.inclinometro

import com.williandlima.inclinometro.report.ChartScale
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

/** Mesma regra do gráfico do app desktop: faixa fixa, só expandida. */
class ChartScaleTest {
    @Test
    fun dentroDaFaixaFicaAFaixaFixa() {
        assertEquals(-95.0 to 95.0, ChartScale.range(-95.0, 95.0, listOf(-30.0, 0.0, 30.0)))
    }

    @Test
    fun semDadosFicaAFaixaFixa() {
        assertEquals(-60.0 to 60.0, ChartScale.range(-60.0, 60.0, emptyList()))
    }

    @Test
    fun foraDaFaixaExpandeSemCortarACurva() {
        val (lo, hi) = ChartScale.range(-95.0, 95.0, listOf(-10.0, 150.0))
        assertEquals(-95.0, lo, 1e-9)                // o lado que coube não muda
        assertTrue(hi > 150.0)                         // o pico cabe, com margem
        assertEquals(150.0 + 0.05 * 160.0, hi, 1e-9)
    }

    @Test
    fun nuncaEncolhe() {
        val (lo, hi) = ChartScale.range(-95.0, 95.0, listOf(100.0, 100.5))
        assertEquals(-95.0, lo, 1e-9)
        assertEquals(101.5, hi, 1e-9)                  // margem mínima de 1°
    }
}
