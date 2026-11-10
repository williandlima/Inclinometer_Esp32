package com.williandlima.inclinometro.limits

import com.williandlima.inclinometro.datasource.AngleReading
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/**
 * Exportação das leituras de uma aquisição para CSV — mesmo formato do app
 * desktop (`python-app/limits/history_export.py`): separador ";" e vírgula
 * decimal, para abrir direto no Excel em português, com BOM UTF-8 (sem ele o
 * Excel troca os acentos). O cabeçalho traz os dados da aquisição em linhas
 * iniciadas por "#".
 */
object HistoryExport {
    private fun num(value: Double?, digits: Int = 2): String =
        if (value == null) "" else String.format(Locale.US, "%.${digits}f", value).replace('.', ',')

    fun sessionCsv(session: SessionInfo, readings: List<AngleReading>, events: List<LimitEvent>): String {
        // Formatadores locais: SimpleDateFormat não é seguro entre threads.
        val stamp = SimpleDateFormat("dd/MM/yyyy HH:mm:ss", Locale.US)
        val millis = SimpleDateFormat("dd/MM/yyyy HH:mm:ss,SSS", Locale.US)
        val sb = StringBuilder("﻿")
        sb.append("# Inclinometro - aquisicao ${session.id}\n")
        sb.append("# modo: ${session.mode.name}\n")
        sb.append("# inicio: ${stamp.format(Date(session.startedAt))}\n")
        sb.append("# fim: ${session.endedAt?.let { stamp.format(Date(it)) } ?: "em andamento"}\n")
        sb.append("# app: ${session.appVersion ?: "-"}; firmware: ${session.firmwareVersion ?: "-"}\n")
        for (e in events) {
            sb.append(
                "# limite: ${e.axis.name};${e.kind.name};${num(e.valueDeg)};" +
                    "${stamp.format(Date(e.reading.timestamp))}\n",
            )
        }
        sb.append("data_hora;t_s;inclinacao_graus;azimute_graus\n")
        for (r in readings) {
            sb.append(millis.format(Date(r.timestamp))).append(';')
                .append(num((r.timestamp - session.startedAt) / 1000.0, 3)).append(';')
                .append(num(r.angleDeg)).append(';')
                .append(num(r.panDeg)).append('\n')
        }
        return sb.toString()
    }
}
