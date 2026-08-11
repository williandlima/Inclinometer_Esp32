package com.williandlima.inclinometro.report

import android.content.Context
import android.graphics.Color
import android.graphics.Paint
import android.graphics.pdf.PdfDocument
import com.williandlima.inclinometro.datasource.AngleReading
import com.williandlima.inclinometro.datasource.ConnectionMode
import com.williandlima.inclinometro.limits.LimitEvent
import com.williandlima.inclinometro.limits.LimitKind
import com.williandlima.inclinometro.limits.SessionInfo
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
        val angleMin = readings.minOfOrNull { it.angleDeg }
        val angleMax = readings.maxOfOrNull { it.angleDeg }

        val summaryRows = listOf(
            "Modo" to modeLabel,
            "Início" to started,
            "Fim" to ended,
            "Leituras registradas" to readings.size.toString(),
            "Ângulo mínimo observado" to (angleMin?.let { "%.2f°".format(it) } ?: "-"),
            "Ângulo máximo observado" to (angleMax?.let { "%.2f°".format(it) } ?: "-"),
        )
        for ((label, value) in summaryRows) {
            canvas.drawText("$label:", MARGIN, y, labelPaint)
            canvas.drawText(value, MARGIN + 170f, y, valuePaint)
            y += 18f
        }

        y += 16f
        canvas.drawText("Ângulo ao longo do tempo", MARGIN, y, headingPaint)
        y += 12f

        drawChart(canvas, readings, events, top = y, bottom = y + 260f)

        document.finishPage(page)
    }

    private fun drawChart(
        canvas: android.graphics.Canvas,
        readings: List<AngleReading>,
        events: List<LimitEvent>,
        top: Float,
        bottom: Float,
    ) {
        val left = MARGIN
        val right = PAGE_WIDTH - MARGIN

        val axisPaint = Paint().apply { color = Color.GRAY; strokeWidth = 1f }
        canvas.drawLine(left, top, left, bottom, axisPaint)
        canvas.drawLine(left, bottom, right, bottom, axisPaint)

        if (readings.isEmpty()) return

        val t0 = readings.first().timestamp
        val tEnd = readings.last().timestamp
        val duration = (tEnd - t0).coerceAtLeast(1L)

        fun xFor(timestamp: Long): Float = left + (right - left) * (timestamp - t0).toFloat() / duration
        fun yFor(angle: Double): Float = bottom - (bottom - top) * (angle / 120.0).toFloat()

        val linePaint = Paint().apply { color = Color.rgb(31, 119, 180); strokeWidth = 2f; isAntiAlias = true }
        var prevX: Float? = null
        var prevY: Float? = null
        for (reading in readings) {
            val x = xFor(reading.timestamp)
            val y = yFor(reading.angleDeg)
            if (prevX != null && prevY != null) {
                canvas.drawLine(prevX, prevY, x, y, linePaint)
            }
            prevX = x
            prevY = y
        }

        val minPaint = Paint().apply { color = Color.rgb(214, 39, 40); style = Paint.Style.FILL; isAntiAlias = true }
        val maxPaint = Paint().apply { color = Color.rgb(44, 160, 44); style = Paint.Style.FILL; isAntiAlias = true }
        for (event in events) {
            val x = xFor(event.reading.timestamp)
            val y = yFor(event.reading.angleDeg)
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

            val colX = floatArrayOf(MARGIN, MARGIN + 40f, MARGIN + 140f, MARGIN + 220f)
            canvas.drawRect(MARGIN, y - 14f, PAGE_WIDTH - MARGIN, y + 4f, headerBgPaint)
            canvas.drawText("#", colX[0], y, headerPaint)
            canvas.drawText("Tipo", colX[1], y, headerPaint)
            canvas.drawText("Ângulo", colX[2], y, headerPaint)
            canvas.drawText("Data/Hora", colX[3], y, headerPaint)
            y += 20f

            val startIndex = (pageNumber - 2) * ROWS_PER_EVENTS_PAGE
            chunk.forEachIndexed { index, event ->
                val tipo = if (event.kind == LimitKind.MIN) "Novo mínimo" else "Novo máximo"
                canvas.drawText((startIndex + index + 1).toString(), colX[0], y, rowPaint)
                canvas.drawText(tipo, colX[1], y, rowPaint)
                canvas.drawText("%.2f°".format(event.reading.angleDeg), colX[2], y, rowPaint)
                canvas.drawText(timeFormat.format(Date(event.reading.timestamp)), colX[3], y, rowPaint)
                y += 18f
            }

            document.finishPage(page)
            pageNumber++
        }
    }
}
