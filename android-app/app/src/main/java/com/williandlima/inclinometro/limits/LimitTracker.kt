package com.williandlima.inclinometro.limits

import com.williandlima.inclinometro.datasource.AngleReading

/**
 * Rastreamento de mínimo/máximo em runtime, independente da fonte de dados.
 * Funciona igual em modo simulado ou real: recebe cada [AngleReading] e
 * retorna os eventos de novo limite (0, 1 ou 2) desde o último reset.
 */
class LimitTracker {
    var minReading: AngleReading? = null
        private set
    var maxReading: AngleReading? = null
        private set

    fun reset() {
        minReading = null
        maxReading = null
    }

    fun process(reading: AngleReading): List<LimitEvent> {
        val events = mutableListOf<LimitEvent>()

        val currentMin = minReading
        if (currentMin == null || reading.angleDeg < currentMin.angleDeg) {
            minReading = reading
            events += LimitEvent(LimitKind.MIN, reading)
        }

        val currentMax = maxReading
        if (currentMax == null || reading.angleDeg > currentMax.angleDeg) {
            maxReading = reading
            events += LimitEvent(LimitKind.MAX, reading)
        }

        return events
    }
}
