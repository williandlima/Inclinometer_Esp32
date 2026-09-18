package com.williandlima.inclinometro.report

import android.content.Context
import android.graphics.Color
import android.graphics.Paint
import android.graphics.pdf.PdfDocument
import com.williandlima.inclinometro.datasource.ANGLE_MAX_DEG
import com.williandlima.inclinometro.datasource.ANGLE_MIN_DEG
import com.williandlima.inclinometro.datasource.AngleReading
import com.williandlima.inclinometro.datasource.ConnectionMode
import com.williandlima.inclinometro.datasource.PAN_MAX_DEG
import com.williandlima.inclinometro.datasource.PAN_MIN_DEG
import com.williandlima.inclinometro.limits.LimitAxis
import com.williandlima.inclinometro.limits.LimitEvent
import com.williandlima.inclinometro.limits.LimitKind
import com.williandlima.inclinometro.limits.AxisAnalysis
import com.williandlima.inclinometro.limits.SessionInfo
import com.williandlima.inclinometro.limits.VibrationCaptureInfo
import com.williandlima.inclinometro.limits.VibrationStats
import java.io.File
import java.io.FileOutputStream
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext

/**
 * Gera o relatório em PDF de uma sessão usando a API nativa do Android
 * (`android.graphics.pdf.PdfDocument` + `Canvas`), sem dependência externa.
 * Conteúdo equivalente ao relatório do app desktop: resumo da sessão,
 * gráfico do ângulo ao longo do tempo com os extremos marcados, e tabela de
 * eventos de limite.
 */
object PdfReportGenerator {

    private const val PAGE_WIDTH = 595 // A4 a 72dpi
    private const val PAGE_HEIGHT = 842
    private const val MARGIN = 40f
    private const val ROWS_PER_EVENTS_PAGE = 32

    private val timeFormat = SimpleDateFormat("dd/MM/yyyy HH:mm:ss", Locale("pt", "BR"))

    suspend fun generate(
        context: Context,
        session: SessionInfo,
        readings: List<AngleReading>,
        events: List<LimitEvent>,
    ): File = withContext(Dispatchers.IO) {
        val document = PdfDocument()

        drawSummaryAndChartPage(document, session, readings, events)
        if (events.isNotEmpty()) {
            drawEventsPages(document, events)
        }

        val dir = File(context.getExternalFilesDir(null), "relatorios").apply { mkdirs() }
        val fileName = "relatorio_inclinometro_${System.currentTimeMillis()}.pdf"
        val file = File(dir, fileName)
        FileOutputStream(file).use { document.writeTo(it) }
        document.close()
        file
    }

    private fun drawSummaryAndChartPage(
        document: PdfDocument,
        session: SessionInfo,
        readings: List<AngleReading>,
        events: List<LimitEvent>,
    ) {
        val pageInfo = PdfDocument.PageInfo.Builder(PAGE_WIDTH, PAGE_HEIGHT, 1).create()
        val page = document.startPage(pageInfo)
        val canvas = page.canvas

        val titlePaint = Paint().apply { textSize = 20f; isFakeBoldText = true; color = Color.BLACK }
        val labelPaint = Paint().apply { textSize = 12f; isFakeBoldText = true; color = Color.DKGRAY }
        val valuePaint = Paint().apply { textSize = 12f; color = Color.BLACK }
        val headingPaint = Paint().apply { textSize = 14f; isFakeBoldText = true; color = Color.BLACK }

        var y = MARGIN
        canvas.drawText("Relatório do Inclinômetro", MARGIN, y, titlePaint)
        y += 30f

        val modeLabel = if (session.mode == ConnectionMode.SIMULATED) "Simulação" else "Real (BLE)"
        val started = timeFormat.format(Date(session.startedAt))
        val ended = session.endedAt?.let { timeFormat.format(Date(it)) } ?: "em andamento"
        val (angleMin, angleMax) = axisExtremes(readings, events, LimitAxis.TILT)
        val panValues = readings.mapNotNull { it.panDeg }
        val (panMin, panMax) = axisExtremes(readings, events, LimitAxis.PAN)

        fun fmtRange(low: Double?, high: Double?): String =
            if (low == null || high == null) "-" else "%.2f°  /  %.2f°".format(low, high)

        val summaryRows = listOf(
            "Modo" to modeLabel,
            "Início" to started,
            "Fim" to ended,
            "Leituras registradas" to readings.size.toString(),
            "Inclinação mín. / máx. registrada" to fmtRange(angleMin, angleMax),
            "Azimute mín. / máx. registrado" to if (panValues.isNotEmpty()) {
                fmtRange(panMin, panMax)
            } else {
                "não registrado (firmware sem eixo de azimute)"
            },
        )
        for ((label, value) in summaryRows) {
            canvas.drawText("$label:", MARGIN, y, labelPaint)
            canvas.drawText(value, MARGIN + 170f, y, valuePaint)
            y += 18f
        }

        y += 16f
        canvas.drawText("Inclinação (tilt) ao longo do tempo", MARGIN, y, headingPaint)
        y += 12f
        drawChart(canvas, readings, events, LimitAxis.TILT, top = y, bottom = y + 230f)
        y += 230f

        y += 26f
        canvas.drawText("Azimute (pan) ao longo do tempo", MARGIN, y, headingPaint)
        y += 12f
        if (panValues.isNotEmpty()) {
            drawChart(canvas, readings, events, LimitAxis.PAN, top = y, bottom = y + 230f)
        } else {
            y += 14f
            canvas.drawText(
                "Nenhum valor de azimute registrado nesta sessão — o ESP32 conectado estava",
                MARGIN, y, valuePaint,
            )
            y += 16f
            canvas.drawText("com firmware anterior à v1.2.0, que mede apenas a inclinação.", MARGIN, y, valuePaint)
        }

        document.finishPage(page)
    }

    /** Extrai o valor do eixo pedido, ou `null` se a leitura não o mediu. */
    private fun axisValue(reading: AngleReading, axis: LimitAxis): Double? = when (axis) {
        LimitAxis.PAN -> reading.panDeg
        LimitAxis.TILT -> reading.angleDeg
    }

    /**
     * Mínimo e máximo do eixo para o resumo do relatório.
     *
     * Prefere os EVENTOS DE LIMITE às leituras. Com firmware v1.5.0+ eles
     * carregam o extremo medido no ESP32 a 100 Hz, enquanto as leituras são o
     * valor suavizado para a tela, amostrado a 5 Hz — nelas uma rajada de meio
     * segundo aparece com menos da metade da amplitude real. É por isso que o
     * marcador de extremo no gráfico pode aparecer fora da curva: a curva
     * mostra o que a tela mostrou, o marcador mostra o que de fato aconteceu.
     *
     * Cai para as leituras quando não há eventos do eixo.
     */
    private fun axisExtremes(
        readings: List<AngleReading>,
        events: List<LimitEvent>,
        axis: LimitAxis,
    ): Pair<Double?, Double?> {
        val axisEvents = events.filter { it.axis == axis }
        val mins = axisEvents.filter { it.kind == LimitKind.MIN }.map { it.valueDeg }
        val maxs = axisEvents.filter { it.kind == LimitKind.MAX }.map { it.valueDeg }
        if (mins.isNotEmpty() && maxs.isNotEmpty()) {
            return mins.min() to maxs.max()
        }

        val values = readings.mapNotNull { axisValue(it, axis) }
        if (values.isEmpty()) return null to null
        return values.min() to values.max()
    }

    private fun drawChart(
        canvas: android.graphics.Canvas,
        readings: List<AngleReading>,
        events: List<LimitEvent>,
        axis: LimitAxis,
        top: Float,
        bottom: Float,
    ) {
        val left = MARGIN
        val right = PAGE_WIDTH - MARGIN

        val axisPaint = Paint().apply { color = Color.GRAY; strokeWidth = 1f }
        canvas.drawLine(left, top, left, bottom, axisPaint)
        canvas.drawLine(left, bottom, right, bottom, axisPaint)

        if (readings.isEmpty()) return

        // Escala fixa por eixo (e não autoescala): assim uma variação de
        // décimos de grau não ocupa o gráfico inteiro e parece enorme.
        val (rangeMin, rangeMax) = when (axis) {
            LimitAxis.PAN -> PAN_MIN_DEG to PAN_MAX_DEG
            LimitAxis.TILT -> ANGLE_MIN_DEG to ANGLE_MAX_DEG
        }
        val lineColor = when (axis) {
            LimitAxis.PAN -> Color.rgb(148, 103, 189)
            LimitAxis.TILT -> Color.rgb(31, 119, 180)
        }

        val t0 = readings.first().timestamp
        val tEnd = readings.last().timestamp
        val duration = (tEnd - t0).coerceAtLeast(1L)

        fun xFor(timestamp: Long): Float = left + (right - left) * (timestamp - t0).toFloat() / duration
        fun yFor(angle: Double): Float =
            bottom - (bottom - top) * ((angle - rangeMin) / (rangeMax - rangeMin)).toFloat()

        val linePaint = Paint().apply { color = lineColor; strokeWidth = 2f; isAntiAlias = true }
        var prevX: Float? = null
        var prevY: Float? = null
        for (reading in readings) {
            val value = axisValue(reading, axis)
            if (value == null) {
                // Leitura sem este eixo: interrompe a linha em vez de ligá-la
                // a um zero que nunca foi medido.
                prevX = null
                prevY = null
                continue
            }
            val x = xFor(reading.timestamp)
            val y = yFor(value)
            if (prevX != null && prevY != null) {
                canvas.drawLine(prevX, prevY, x, y, linePaint)
            }
            prevX = x
            prevY = y
        }

        val minPaint = Paint().apply { color = Color.rgb(214, 39, 40); style = Paint.Style.FILL; isAntiAlias = true }
        val maxPaint = Paint().apply { color = Color.rgb(44, 160, 44); style = Paint.Style.FILL; isAntiAlias = true }
        for (event in events.filter { it.axis == axis }) {
            val x = xFor(event.reading.timestamp)
            val y = yFor(event.valueDeg)
            val paint = if (event.kind == LimitKind.MIN) minPaint else maxPaint
            canvas.drawCircle(x, y, 3.5f, paint)
        }
    }

    private fun drawEventsPages(document: PdfDocument, events: List<LimitEvent>) {
        val chunks = events.chunked(ROWS_PER_EVENTS_PAGE)
        var pageNumber = 2
        for (chunk in chunks) {
            val pageInfo = PdfDocument.PageInfo.Builder(PAGE_WIDTH, PAGE_HEIGHT, pageNumber).create()
            val page = document.startPage(pageInfo)
            val canvas = page.canvas

            val headingPaint = Paint().apply { textSize = 16f; isFakeBoldText = true; color = Color.BLACK }
            val headerPaint = Paint().apply { textSize = 11f; isFakeBoldText = true; color = Color.WHITE }
            val headerBgPaint = Paint().apply { color = Color.rgb(55, 71, 79) }
            val rowPaint = Paint().apply { textSize = 11f; color = Color.BLACK }

            var y = MARGIN
            canvas.drawText("Histórico de limites atingidos", MARGIN, y, headingPaint)
            y += 24f

            val colX = floatArrayOf(MARGIN, MARGIN + 30f, MARGIN + 120f, MARGIN + 220f, MARGIN + 300f)
            canvas.drawRect(MARGIN, y - 14f, PAGE_WIDTH - MARGIN, y + 4f, headerBgPaint)
            canvas.drawText("#", colX[0], y, headerPaint)
            canvas.drawText("Eixo", colX[1], y, headerPaint)
            canvas.drawText("Tipo", colX[2], y, headerPaint)
            canvas.drawText("Valor", colX[3], y, headerPaint)
            canvas.drawText("Data/Hora", colX[4], y, headerPaint)
            y += 20f

            val startIndex = (pageNumber - 2) * ROWS_PER_EVENTS_PAGE
            chunk.forEachIndexed { index, event ->
                val tipo = if (event.kind == LimitKind.MIN) "Novo mínimo" else "Novo máximo"
                canvas.drawText((startIndex + index + 1).toString(), colX[0], y, rowPaint)
                canvas.drawText(event.axis.label, colX[1], y, rowPaint)
                canvas.drawText(tipo, colX[2], y, rowPaint)
                canvas.drawText("%.2f°".format(event.valueDeg), colX[3], y, rowPaint)
                canvas.drawText(timeFormat.format(Date(event.reading.timestamp)), colX[4], y, rowPaint)
                y += 18f
            }

            document.finishPage(page)
            pageNumber++
        }
    }

    /**
     * Relatório de uma captura de vibração (Modo Vibração): resumo
     * estatístico, gráfico da variação angular no tempo e espectro de
     * frequência (FFT) — equivalente ao `generate_vibration_report()` do
     * app desktop.
     */
    suspend fun generateVibrationReport(
        context: Context,
        capture: VibrationCaptureInfo,
        readings: List<AngleReading>,
        tilt: AxisAnalysis,
        pan: AxisAnalysis? = null,
    ): File = withContext(Dispatchers.IO) {
        val document = PdfDocument()

        val titlePaint = Paint().apply { textSize = 20f; isFakeBoldText = true; color = Color.BLACK }
        val labelPaint = Paint().apply { textSize = 12f; isFakeBoldText = true; color = Color.DKGRAY }
        val valuePaint = Paint().apply { textSize = 12f; color = Color.BLACK }

        val pageInfo = PdfDocument.PageInfo.Builder(PAGE_WIDTH, PAGE_HEIGHT, 1).create()
        val page = document.startPage(pageInfo)
        val canvas = page.canvas

        var y = MARGIN
        canvas.drawText("Relatório de Captura de Vibração", MARGIN, y, titlePaint)
        y += 30f

        val modeLabel = if (capture.mode == ConnectionMode.SIMULATED) "Simulação" else "Real (BLE)"
        val summaryRows = listOf(
            "Modo" to modeLabel,
            "Início" to timeFormat.format(Date(capture.startedAt)),
            "Duração configurada" to "${capture.durationS} s",
            "Taxa de amostragem" to "${capture.rateHz} Hz",
            "Amostras capturadas" to tilt.stats.nSamples.toString(),
            "Duração efetiva" to "%.2f s".format(tilt.stats.durationS),
        )
        for ((label, value) in summaryRows) {
            canvas.drawText("$label:", MARGIN, y, labelPaint)
            canvas.drawText(value, MARGIN + 190f, y, valuePaint)
            y += 18f
        }

        y += 10f
        drawVibrationAxisSection(canvas, "Inclinação (tilt)", readings, tilt, y)
        document.finishPage(page)

        // Um eixo por página: cada bloco leva tabela + dois gráficos, e os dois
        // não caberiam legíveis na mesma folha.
        val panPageInfo = PdfDocument.PageInfo.Builder(PAGE_WIDTH, PAGE_HEIGHT, 2).create()
        val panPage = document.startPage(panPageInfo)
        if (pan != null) {
            drawVibrationAxisSection(panPage.canvas, "Azimute (pan)", readings, pan, MARGIN)
        } else {
            var py = MARGIN
            panPage.canvas.drawText("Azimute (pan)", MARGIN, py, titlePaint)
            py += 26f
            panPage.canvas.drawText(
                "O eixo de azimute não foi capturado: o ESP32 conectado estava com",
                MARGIN, py, valuePaint,
            )
            py += 16f
            panPage.canvas.drawText(
                "firmware anterior à v1.3.0, que não amostra esse eixo no Modo Vibração.",
                MARGIN, py, valuePaint,
            )
        }
        document.finishPage(panPage)

        val dir = File(context.getExternalFilesDir(null), "relatorios").apply { mkdirs() }
        val fileName = "relatorio_vibracao_${System.currentTimeMillis()}.pdf"
        val file = File(dir, fileName)
        FileOutputStream(file).use { document.writeTo(it) }
        document.close()
        file
    }

    /** Bloco de um eixo: título, estatísticas, gráfico no tempo e espectro. */
    private fun drawVibrationAxisSection(
        canvas: android.graphics.Canvas,
        title: String,
        readings: List<AngleReading>,
        analysis: AxisAnalysis,
        startY: Float,
    ) {
        val titlePaint = Paint().apply { textSize = 16f; isFakeBoldText = true; color = Color.BLACK }
        val labelPaint = Paint().apply { textSize = 12f; isFakeBoldText = true; color = Color.DKGRAY }
        val valuePaint = Paint().apply { textSize = 12f; color = Color.BLACK }
        val headingPaint = Paint().apply { textSize = 14f; isFakeBoldText = true; color = Color.BLACK }
        val stats = analysis.stats

        var y = startY
        canvas.drawText(title, MARGIN, y, titlePaint)
        y += 22f

        val rows = listOf(
            "Média" to "%.3f°".format(stats.meanDeg),
            "Desvio padrão" to "%.3f°".format(stats.stdDevDeg),
            "RMS" to "%.3f°".format(stats.rmsDeg),
            "Pico a pico" to "%.3f°".format(stats.peakToPeakDeg),
            "Mínimo / Máximo" to "%.3f° / %.3f°".format(stats.minDeg, stats.maxDeg),
            "Frequência dominante" to (
                stats.dominantFreqHz?.let {
                    "%.2f Hz (amplitude %.3f°, SNR %.1f dB)".format(
                        it, stats.dominantAmplitudeDeg ?: 0.0, stats.dominantSnrDb ?: 0.0,
                    )
                } ?: "nenhum pico confiável (sinal compatível com ruído)"
            ),
        )
        for ((label, value) in rows) {
            canvas.drawText("$label:", MARGIN, y, labelPaint)
            canvas.drawText(value, MARGIN + 190f, y, valuePaint)
            y += 18f
        }

        y += 14f
        canvas.drawText("Variação angular ao longo do tempo", MARGIN, y, headingPaint)
        y += 12f
        drawVibrationTimeChart(canvas, readings, analysis.axis, top = y, bottom = y + 190f)
        y += 210f

        canvas.drawText("Espectro de frequência (FFT)", MARGIN, y, headingPaint)
        y += 12f
        drawSpectrumChart(canvas, analysis.freqsHz, analysis.magnitudes, stats, top = y, bottom = y + 190f)
    }

    private fun drawVibrationTimeChart(
        canvas: android.graphics.Canvas,
        readings: List<AngleReading>,
        axis: LimitAxis,
        top: Float,
        bottom: Float,
    ) {
        val left = MARGIN
        val right = PAGE_WIDTH - MARGIN
        val axisPaint = Paint().apply { color = Color.GRAY; strokeWidth = 1f }
        canvas.drawLine(left, top, left, bottom, axisPaint)
        canvas.drawLine(left, bottom, right, bottom, axisPaint)
        if (readings.isEmpty()) return

        // Aqui a escala é automática (diferente do gráfico da sessão): a
        // variação de uma captura de vibração é de frações de grau, e uma
        // escala fixa deixaria a curva achatada numa linha reta.
        val values = readings.mapNotNull { axisValue(it, axis) }
        if (values.isEmpty()) return
        val t0 = readings.first().timestamp
        val tEnd = readings.last().timestamp
        val duration = (tEnd - t0).coerceAtLeast(1L)
        val minAngle = values.min()
        val range = (values.max() - minAngle).coerceAtLeast(0.01)

        fun xFor(timestamp: Long): Float = left + (right - left) * (timestamp - t0).toFloat() / duration
        fun yFor(angle: Double): Float = bottom - (bottom - top) * ((angle - minAngle) / range).toFloat()

        val lineColor = if (axis == LimitAxis.PAN) Color.rgb(148, 103, 189) else Color.rgb(31, 119, 180)
        val linePaint = Paint().apply { color = lineColor; strokeWidth = 1.5f; isAntiAlias = true }
        var prevX: Float? = null
        var prevY: Float? = null
        for (reading in readings) {
            val value = axisValue(reading, axis)
            if (value == null) {
                prevX = null
                prevY = null
                continue
            }
            val x = xFor(reading.timestamp)
            val y = yFor(value)
            if (prevX != null && prevY != null) canvas.drawLine(prevX, prevY, x, y, linePaint)
            prevX = x
            prevY = y
        }
    }

    private fun drawSpectrumChart(
        canvas: android.graphics.Canvas,
        freqsHz: DoubleArray,
        magnitudes: DoubleArray,
        stats: VibrationStats,
        top: Float,
        bottom: Float,
    ) {
        val left = MARGIN
        val right = PAGE_WIDTH - MARGIN
        val axisPaint = Paint().apply { color = Color.GRAY; strokeWidth = 1f }
        canvas.drawLine(left, top, left, bottom, axisPaint)
        canvas.drawLine(left, bottom, right, bottom, axisPaint)
        if (freqsHz.isEmpty()) return

        val maxFreq = freqsHz.last().coerceAtLeast(0.01)
        val maxMag = magnitudes.maxOrNull()?.coerceAtLeast(0.0001) ?: 0.0001

        fun xFor(freq: Double): Float = left + (right - left) * (freq / maxFreq).toFloat()
        fun yFor(mag: Double): Float = bottom - (bottom - top) * (mag / maxMag).toFloat()

        val linePaint = Paint().apply { color = Color.rgb(214, 39, 40); strokeWidth = 1.5f; isAntiAlias = true }
        var prevX: Float? = null
        var prevY: Float? = null
        for (i in freqsHz.indices) {
            val x = xFor(freqsHz[i])
            val y = yFor(magnitudes[i])
            if (prevX != null && prevY != null) canvas.drawLine(prevX, prevY, x, y, linePaint)
            prevX = x
            prevY = y
        }

        val peakFreq = stats.dominantFreqHz
        if (peakFreq != null && peakFreq <= maxFreq) {
            val peakX = xFor(peakFreq)
            val peakPaint = Paint().apply {
                color = Color.rgb(44, 160, 44)
                strokeWidth = 1.2f
                pathEffect = android.graphics.DashPathEffect(floatArrayOf(6f, 4f), 0f)
            }
            canvas.drawLine(peakX, top, peakX, bottom, peakPaint)
            val labelPaint = Paint().apply {
                color = Color.rgb(44, 160, 44)
                textSize = 10f
                isFakeBoldText = true
            }
            canvas.drawText(
                "%.2f Hz / %.3f°".format(peakFreq, stats.dominantAmplitudeDeg ?: 0.0),
                (peakX + 4f).coerceAtMost(right - 90f),
                top + 12f,
                labelPaint,
            )
        }
    }
}
