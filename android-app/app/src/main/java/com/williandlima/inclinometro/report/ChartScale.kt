package com.williandlima.inclinometro.report

/**
 * Faixa vertical de um gráfico do relatório — mesma regra do app desktop
 * (`_build_chart_image` em `python-app/report/report_generator.py`).
 *
 * Parte de uma faixa FIXA confortável para o uso típico (uma variação de
 * décimos de grau não ocupa o gráfico inteiro e parece enorme) e só a
 * EXPANDE, nunca encolhe, quando os dados passam dela — senão a curva seria
 * cortada no topo ou no fundo, como se o sinal tivesse saturado. Kotlin puro,
 * testado em `app/src/test`.
 */
object ChartScale {
    fun range(fixedLo: Double, fixedHi: Double, values: List<Double>): Pair<Double, Double> {
        if (values.isEmpty()) return fixedLo to fixedHi
        val dataMin = values.min()
        val dataMax = values.max()
        if (dataMin >= fixedLo && dataMax <= fixedHi) return fixedLo to fixedHi
        val margin = maxOf((dataMax - dataMin) * 0.05, 1.0)
        return minOf(fixedLo, dataMin - margin) to maxOf(fixedHi, dataMax + margin)
    }
}
