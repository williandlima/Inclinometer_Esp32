package com.williandlima.inclinometro.limits

import com.williandlima.inclinometro.datasource.AngleReading

/**
 * Rastreamento de mínimo/máximo em runtime, independente da fonte de dados.
 * Funciona igual em modo simulado ou real: recebe cada [AngleReading] e
 * retorna os eventos de novo limite (0, 1 ou 2) desde o último reset.
 *
 * Cada instância rastreia **um eixo** ([axis]). O app cria duas: uma para a
 * inclinação e outra para o azimute. Leituras em que o eixo rastreado não foi
 * medido (`panDeg == null`, caso de firmware anterior à v1.2.0) são
 * ignoradas, em vez de contarem como zero e poluírem os extremos.
 */
class LimitTracker(val axis: LimitAxis = LimitAxis.TILT) {
    var minReading: AngleReading? = null
        private set
    var maxReading: AngleReading? = null
        private set

    fun reset() {
        minReading = null
        maxReading = null
    }

    private fun valueOf(reading: AngleReading): Double? = when (axis) {
        LimitAxis.PAN -> reading.panDeg
        LimitAxis.TILT -> reading.angleDeg
    }

    fun process(reading: AngleReading): List<LimitEvent> {
        val value = valueOf(reading) ?: return emptyList()
        val events = mutableListOf<LimitEvent>()

        val currentMin = minReading?.let { valueOf(it) }
        if (currentMin == null || value < currentMin) {
            minReading = reading
            events += LimitEvent(LimitKind.MIN, reading, axis)
        }

        val currentMax = maxReading?.let { valueOf(it) }
        if (currentMax == null || value > currentMax) {
            maxReading = reading
            events += LimitEvent(LimitKind.MAX, reading, axis)
        }

        return events
    }
}
