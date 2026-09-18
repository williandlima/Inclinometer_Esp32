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
 *
 * DE ONDE VEM O EXTREMO. A partir do firmware v1.5.0, quem mede os extremos é
 * o próprio ESP32, e a leitura os traz prontos ([AngleReading.angleMinDeg] e
 * companhia). Este rastreador então apenas os acompanha, em vez de
 * calculá-los. O motivo é de amostragem, não de código: o firmware vê o
 * sensor a 100 Hz, o app vê a 5 Hz, e um evento curto — a rajada de vento que
 * o relatório existe para registrar — acontece inteiro entre duas leituras.
 *
 * Sem esses campos (firmware antigo, modo simulação) o cálculo volta a ser
 * feito aqui, exatamente como antes. As duas fontes convivem por eixo.
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

    /** Extremo medido pelo firmware para o eixo deste rastreador, se houver. */
    private fun devicePeak(reading: AngleReading, kind: LimitKind): Double? = when (axis) {
        LimitAxis.PAN -> if (kind == LimitKind.MIN) reading.panMinDeg else reading.panMaxDeg
        LimitAxis.TILT -> if (kind == LimitKind.MIN) reading.angleMinDeg else reading.angleMaxDeg
    }

    /**
     * Leitura que representa um extremo vindo do dispositivo.
     *
     * O extremo do firmware é só um número — não vem acompanhado do instante
     * em que aconteceu. Aqui ele é ancorado na leitura que o trouxe, com o
     * valor do eixo rastreado substituído pelo extremo. O carimbo de tempo
     * fica portanto até um ciclo de notify (~200 ms) depois do evento real; o
     * VALOR, que é o que vai para o relatório, é exato.
     */
    private fun asExtreme(reading: AngleReading, value: Double): AngleReading = when (axis) {
        LimitAxis.PAN -> reading.copy(panDeg = value)
        LimitAxis.TILT -> reading.copy(angleDeg = value)
    }

    fun process(reading: AngleReading): List<LimitEvent> {
        val value = valueOf(reading) ?: return emptyList()
        val events = mutableListOf<LimitEvent>()

        for (kind in listOf(LimitKind.MIN, LimitKind.MAX)) {
            val peak = devicePeak(reading, kind)
            val candidate = peak ?: value
            val candidateReading = if (peak == null) reading else asExtreme(reading, candidate)

            val previous = if (kind == LimitKind.MIN) minReading else maxReading
            val current = previous?.let { valueOf(it) }
            val improved = current == null ||
                if (kind == LimitKind.MIN) candidate < current else candidate > current
            if (!improved) continue

            if (kind == LimitKind.MIN) {
                minReading = candidateReading
            } else {
                maxReading = candidateReading
            }
            events += LimitEvent(kind, candidateReading, axis)
        }

        return events
    }
}
