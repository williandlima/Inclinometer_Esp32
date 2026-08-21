package com.williandlima.inclinometro.limits

import com.williandlima.inclinometro.datasource.AngleReading

enum class LimitKind { MIN, MAX }

/** Eixo a que um limite se refere: inclinação ou azimute. */
enum class LimitAxis(val label: String) {
    TILT("Inclinação"),
    PAN("Azimute"),
}

data class LimitEvent(
    val kind: LimitKind,
    val reading: AngleReading,
    val axis: LimitAxis = LimitAxis.TILT,
) {
    /**
     * Valor do eixo a que este evento se refere.
     *
     * Um evento de pan só é criado a partir de uma leitura que tem pan, e a
     * releitura do histórico reconstrói os dois eixos — então um `null` aqui
     * seria dado corrompido, não um caso normal.
     */
    val valueDeg: Double
        get() = when (axis) {
            LimitAxis.PAN -> reading.panDeg
                ?: error("Evento de limite do eixo de azimute sem valor de azimute.")
            LimitAxis.TILT -> reading.angleDeg
        }
}
