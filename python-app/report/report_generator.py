"""Geração do relatório em PDF a partir do histórico de uma aquisição:
como os dados foram adquiridos (janela, duração, taxa, interrupções, origem
dos mín/máx — ver `report.acquisition`), gráfico do ângulo ao longo do tempo
(com os extremos marcados) e tabela de eventos de limite.
"""
from __future__ import annotations

import datetime as _dt
import io
from typing import TYPE_CHECKING

import matplotlib

matplotlib.use("Agg")  # backend sem display, seguro para gerar imagens em background
import matplotlib.pyplot as plt
from matplotlib.ticker import AutoMinorLocator, MaxNLocator
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import (
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.lib.styles import getSampleStyleSheet

from limits.limit_tracker import PAN_AXIS, SOURCE_FIRMWARE, TILT_AXIS
from report.acquisition import (
    AcquisitionSummary,
    format_duration,
    format_planned,
    summarize_acquisition,
)

if TYPE_CHECKING:
    from data_source.base import AngleReading
    from limits.history_store import SessionInfo, VibrationCaptureInfo
    from limits.limit_tracker import LimitEvent
    from limits.vibration_stats import AxisAnalysis, VibrationStats
    import numpy as np

_MODE_LABELS = {
    "simulado": "Simulação",
    "real": "Real (USB/Modbus RTU)",
    "ble": "Real (Bluetooth BLE)",
}

# Cada eixo tem seu próprio rótulo e escala fixa no gráfico. A escala é fixa
# de propósito: deixar o matplotlib autoescalar faria uma variação de décimos
# de grau ocupar o gráfico inteiro e parecer enorme.
_AXIS_CHART_CONFIG = {
    TILT_AXIS: ("Inclinação", "Inclinação (°)", "#1f77b4", (-65, 65)),
    PAN_AXIS: ("Azimute", "Azimute (°)", "#9467bd", (-185, 185)),
}


def _fmt_dt(ts: float) -> str:
    return _dt.datetime.fromtimestamp(ts).strftime("%d/%m/%Y %H:%M:%S")


def _axis_value(reading: "AngleReading", axis: str) -> float | None:
    return reading.pan_deg if axis == PAN_AXIS else reading.angle_deg


def _axis_extremes(
    readings: list["AngleReading"], events: list["LimitEvent"], axis: str
) -> tuple[float | None, float | None]:
    """Mínimo e máximo do eixo para o resumo do relatório.

    Prefere os EVENTOS DE LIMITE às leituras. Com firmware v1.5.0+ eles
    carregam o extremo medido no ESP32 a 100 Hz, enquanto as leituras são o
    valor suavizado para a tela, amostrado a 4-5 Hz — nelas uma rajada de meio
    segundo aparece com menos da metade da amplitude real. É por isso que o
    marcador de extremo no gráfico pode aparecer fora da curva: a curva mostra
    o que a tela mostrou, o marcador mostra o que de fato aconteceu.

    Cai para as leituras quando não há eventos do eixo — sessão sem eventos
    gravados, ou eixo que o firmware conectado não mede.
    """
    axis_events = [e for e in events if e.axis == axis]
    if axis_events:
        mins = [e.value_deg for e in axis_events if e.kind == "min"]
        maxs = [e.value_deg for e in axis_events if e.kind == "max"]
        if mins and maxs:
            return min(mins), max(maxs)

    values = [v for v in (_axis_value(r, axis) for r in readings) if v is not None]
    if not values:
        return None, None
    return min(values), max(values)


def _time_scale(duration_s: float) -> tuple[float, str]:
    """Divisor e rótulo do eixo de tempo: segundos até 5 min, minutos até
    3 h, horas acima disso — um eixo com "3600" não diz nada a ninguém."""
    if duration_s > 3 * 3600:
        return 3600.0, "Tempo desde o início da aquisição (h)"
    if duration_s > 300:
        return 60.0, "Tempo desde o início da aquisição (min)"
    return 1.0, "Tempo desde o início da aquisição (s)"


def _build_chart_image(
    readings: list["AngleReading"],
    events: list["LimitEvent"],
    axis: str = TILT_AXIS,
    acquisition: AcquisitionSummary | None = None,
) -> Image:
    series_label, y_label, color, y_limits = _AXIS_CHART_CONFIG[axis]
    fig, ax = plt.subplots(figsize=(16, 8))
    if acquisition is None:
        acquisition = summarize_acquisition(None, readings, events)

    # O zero do eixo de tempo é o INÍCIO DA AQUISIÇÃO (não a primeira leitura),
    # para o gráfico e a tabela "Aquisição dos dados" falarem do mesmo tempo.
    t0 = acquisition.started_at if acquisition.started_at is not None else (
        readings[0].timestamp if readings else 0.0
    )
    div, x_label = _time_scale(acquisition.duration_s)

    # Leituras sem valor neste eixo são puladas (não viram zero na curva).
    points = [(r, _axis_value(r, axis)) for r in readings]
    points = [(r, v) for r, v in points if v is not None]
    if points:
        # Uma interrupção vira um buraco na curva (NaN), e não uma reta
        # ligando as duas pontas como se o ângulo tivesse sido medido ali.
        gap_starts = {g.start for g in acquisition.gaps}
        xs: list[float] = []
        ys: list[float] = []
        for r, v in points:
            xs.append((r.timestamp - t0) / div)
            ys.append(v)
            if r.timestamp in gap_starts:
                xs.append(float("nan"))
                ys.append(float("nan"))
        ax.plot(xs, ys, color=color, linewidth=1, label=series_label)
        for i, g in enumerate(acquisition.gaps):
            ax.axvspan(
                (g.start - t0) / div,
                (g.end - t0) / div,
                color="#ff9800",
                alpha=0.18,
                label="Sem leitura (interrupção)" if i == 0 else None,
            )
        ys = [v for _, v in points]

        axis_events = [e for e in events if e.axis == axis]
        mins_x = [(e.reading.timestamp - t0) / div for e in axis_events if e.kind == "min"]
        mins_y = [e.value_deg for e in axis_events if e.kind == "min"]
        maxs_x = [(e.reading.timestamp - t0) / div for e in axis_events if e.kind == "max"]
        maxs_y = [e.value_deg for e in axis_events if e.kind == "max"]
        ax.scatter(mins_x, mins_y, color="#d62728", marker="v", zorder=3, label="Novo mínimo")
        ax.scatter(maxs_x, maxs_y, color="#2ca02c", marker="^", zorder=3, label="Novo máximo")

        # A escala fixa acima é só um valor confortável para variações
        # pequenas (ver comentário de _AXIS_CHART_CONFIG); se a leitura real
        # (ou um evento de mínimo/máximo) ultrapassar essa faixa, mantê-la
        # fixa faria o `set_ylim` abaixo CORTAR a curva no limite — aparecendo
        # como se o sinal tivesse "saturado" no topo/fundo do gráfico, mesmo
        # com o valor medido correto. Por isso a faixa é expandida (nunca
        # encolhida) para sempre cobrir os dados reais dessa sessão.
        all_y = ys + mins_y + maxs_y
        data_min, data_max = min(all_y), max(all_y)
        fixed_lo, fixed_hi = y_limits
        if data_min < fixed_lo or data_max > fixed_hi:
            margin = max((data_max - data_min) * 0.05, 1.0)
            y_limits = (min(fixed_lo, data_min - margin), max(fixed_hi, data_max + margin))

    ax.set_xlabel(x_label)
    ax.set_ylabel(y_label)
    ax.set_ylim(*y_limits)
    if acquisition.duration_s > 0:
        ax.set_xlim(0, acquisition.duration_s / div)
    ax.grid(True, linestyle="--", alpha=0.4)
    ax.legend(loc="upper right")
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150)
    plt.close(fig)
    buf.seek(0)

    img = Image(buf, width=17 * cm, height=8.5 * cm)
    return img


_SOURCE_TEXT = {
    SOURCE_FIRMWARE: "medidos no ESP32 a 100 Hz (firmware v1.5.0+)",
    "app": "calculados pelo app a partir das leituras (~4-5 Hz)",
    None: "-",
}


def _acquisition_rows(acq: AcquisitionSummary, mode_label: str, versions: str = "-") -> list[list[str]]:
    if acq.in_progress:
        end_text = (
            f"em andamento — dados até {_fmt_dt(acq.last_reading_at)}"
            if acq.last_reading_at is not None
            else "em andamento — nenhuma leitura ainda"
        )
    elif acq.ended_at is not None:
        end_text = _fmt_dt(acq.ended_at)
    else:
        end_text = "-"

    planned = format_planned(acq.planned_duration_s)
    if acq.completed_planned is True:
        planned += "  —  concluída"
    elif acq.completed_planned is False:
        planned += "  —  em andamento" if acq.in_progress else "  —  interrompida antes do fim"

    rate = acq.mean_rate_hz
    rate_text = "-"
    if rate is not None:
        rate_text = f"{rate:.1f} leituras/s"
        if acq.median_interval_s is not None:
            rate_text += f"  (uma a cada {acq.median_interval_s * 1000:.0f} ms)"

    if acq.gaps:
        longest = max(g.duration_s for g in acq.gaps)
        gaps_text = (
            f"{len(acq.gaps)} — {format_duration(acq.gap_total_s)} sem leitura no total "
            f"(maior: {format_duration(longest)})"
        )
    else:
        gaps_text = "nenhuma"

    coverage = acq.coverage_pct
    pan_count = (
        str(acq.n_pan_readings) if acq.n_pan_readings else "0 (firmware sem eixo de azimute)"
    )
    return [
        ["Modo", mode_label],
        ["Versões (app / firmware)", versions],
        ["Início da aquisição", _fmt_dt(acq.started_at) if acq.started_at is not None else "-"],
        ["Fim da aquisição", end_text],
        ["Duração da aquisição", format_duration(acq.duration_s)],
        ["Tempo programado", planned],
        ["Leituras de inclinação", str(acq.n_readings)],
        ["Leituras de azimute", pan_count],
        ["Taxa média de leitura", rate_text],
        ["Interrupções (> 2 s sem leitura)", gaps_text],
        ["Cobertura da aquisição", f"{coverage:.1f} %" if coverage is not None else "-"],
        ["Mín/máx de inclinação", _extremes_source_text(acq, TILT_AXIS)],
        ["Mín/máx de azimute", _extremes_source_text(acq, PAN_AXIS)],
    ]


def _extremes_source_text(acq: AcquisitionSummary, axis: str) -> str:
    source = acq.extremes_source.get(axis)
    if source is not None:
        return _SOURCE_TEXT.get(source, source)
    # Sem evento gravado o resumo usa as próprias leituras (_axis_extremes).
    has_values = acq.n_pan_readings if axis == PAN_AXIS else acq.n_readings
    return "calculados a partir das leituras (sem eventos de limite gravados)" if has_values else "-"


def _acquisition_explanation(acq: AcquisitionSummary) -> str:
    planned = (
        f"programada para {format_planned(acq.planned_duration_s)}"
        if acq.planned_duration_s is not None
        else "livre, encerrada no botão \"Parar\""
    )
    return (
        "<b>Como os dados foram adquiridos.</b> Este relatório usa todas as leituras de uma"
        " única aquisição: ela começa no botão \"Iniciar\" (ou em \"Resetar limites\"/"
        "\"Calibrar\" com a leitura em andamento, que abrem uma aquisição nova) e termina em"
        f" \"Parar\" ou no fim do tempo programado. Esta aquisição foi {planned}. Cada leitura"
        " é o valor exibido na tela, recebido do ESP32 cerca de 4 a 5 vezes por segundo, e é"
        " o que forma as curvas abaixo. Os mínimos e máximos são medidos pelo próprio ESP32"
        " a 100 Hz quando o firmware oferece (v1.5.0 ou mais nova), por isso um extremo pode"
        " aparecer fora da curva: a curva mostra o que a tela mostrou, o marcador mostra o que"
        " de fato aconteceu. Trechos sem leitura por mais de 2 s (queda de conexão, por"
        " exemplo) aparecem em laranja nos gráficos e não entram na curva."
    )


def _summary_table(rows: list[list[str]], first_col_cm: float = 6.0) -> Table:
    # Valores em Paragraph para quebrarem linha dentro da célula, em vez de
    # vazarem para fora da tabela quando o texto é longo.
    cell_style = getSampleStyleSheet()["BodyText"]
    rows = [[label, Paragraph(value, cell_style)] for label, value in rows]
    table = Table(rows, colWidths=[first_col_cm * cm, (17 - first_col_cm) * cm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    return table


def generate_report(
    path: str,
    session_info: "SessionInfo | None",
    readings: list["AngleReading"],
    events: list["LimitEvent"],
) -> None:
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(path, pagesize=A4, title="Relatório do Inclinômetro")
    story = []

    story.append(Paragraph("Relatório do Inclinômetro", styles["Title"]))
    story.append(Spacer(1, 0.3 * cm))

    acq = summarize_acquisition(session_info, readings, events)
    mode_label = _MODE_LABELS.get(session_info.mode, session_info.mode) if session_info else "-"
    angle_min, angle_max = _axis_extremes(readings, events, TILT_AXIS)
    pan_values = [r.pan_deg for r in readings if r.pan_deg is not None]
    pan_min, pan_max = _axis_extremes(readings, events, PAN_AXIS)

    def _fmt_range(low: float | None, high: float | None) -> str:
        if low is None or high is None:
            return "-"
        return f"{low:.2f}°  /  {high:.2f}°"

    story.append(Paragraph("Resultado", styles["Heading2"]))
    story.append(
        _summary_table(
            [
                ["Inclinação mín. / máx.", _fmt_range(angle_min, angle_max)],
                [
                    "Azimute mín. / máx.",
                    _fmt_range(pan_min, pan_max)
                    if pan_values
                    else "não registrado (firmware sem eixo de azimute)",
                ],
                ["Duração da aquisição", format_duration(acq.duration_s)],
            ]
        )
    )
    story.append(Spacer(1, 0.5 * cm))

    story.append(Paragraph("Aquisição dos dados", styles["Heading2"]))
    # Rastreabilidade da medição: com que versões a aquisição foi feita.
    versions = "-"
    if session_info is not None and (session_info.app_version or session_info.firmware_version):
        fw = session_info.firmware_version
        if not fw:
            fw = "simulação" if session_info.mode == "simulado" else "não registrado"
        versions = f"app {session_info.app_version or 'não registrado'} / firmware {fw}"
    story.append(_summary_table(_acquisition_rows(acq, mode_label, versions)))
    story.append(Spacer(1, 0.3 * cm))
    story.append(Paragraph(_acquisition_explanation(acq), styles["Normal"]))
    story.append(Spacer(1, 0.6 * cm))

    # Título e gráfico juntos: sem isso o título ficava no pé de uma página
    # e o gráfico na seguinte.
    story.append(
        KeepTogether(
            [
                Paragraph("Inclinação (tilt) ao longo do tempo", styles["Heading2"]),
                _build_chart_image(readings, events, TILT_AXIS, acq),
            ]
        )
    )
    story.append(Spacer(1, 0.8 * cm))

    if pan_values:
        story.append(
            KeepTogether(
                [
                    Paragraph("Azimute (pan) ao longo do tempo", styles["Heading2"]),
                    _build_chart_image(readings, events, PAN_AXIS, acq),
                ]
            )
        )
    else:
        story.append(Paragraph("Azimute (pan) ao longo do tempo", styles["Heading2"]))
        story.append(
            Paragraph(
                "Nenhum valor de azimute foi registrado nesta sessão — o ESP32 conectado"
                " estava com firmware anterior à v1.2.0, que mede apenas a inclinação.",
                styles["Normal"],
            )
        )
    story.append(Spacer(1, 0.8 * cm))

    story.append(Paragraph("Histórico de limites atingidos", styles["Heading2"]))
    if events:
        event_rows = [["#", "Eixo", "Tipo", "Valor", "Data/Hora", "Medido por"]]
        for i, e in enumerate(events, start=1):
            tipo = "Novo mínimo" if e.kind == "min" else "Novo máximo"
            eixo = "Azimute" if e.axis == PAN_AXIS else "Inclinação"
            origem = "ESP32 (100 Hz)" if e.source == SOURCE_FIRMWARE else "App (leituras)"
            event_rows.append(
                [str(i), eixo, tipo, f"{e.value_deg:.2f}°", _fmt_dt(e.reading.timestamp), origem]
            )
        events_table = Table(
            event_rows, colWidths=[1.0 * cm, 2.6 * cm, 3.0 * cm, 2.2 * cm, 4.4 * cm, 3.8 * cm]
        )
        events_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#37474f")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.whitesmoke]),
                ]
            )
        )
        story.append(events_table)
    else:
        story.append(Paragraph("Nenhum evento de limite registrado nesta aquisição.", styles["Normal"]))

    doc.build(story)


def _apply_reference_grid(ax) -> None:
    """Grade densa (maior + menor) nos dois eixos, com valores de escala
    legíveis — para servir de referência de amplitude/tempo ao olhar o
    gráfico, já que as variações do Modo Vibração costumam ser pequenas."""
    ax.xaxis.set_major_locator(MaxNLocator(nbins=12))
    ax.yaxis.set_major_locator(MaxNLocator(nbins=10))
    ax.xaxis.set_minor_locator(AutoMinorLocator(2))
    ax.yaxis.set_minor_locator(AutoMinorLocator(2))
    ax.grid(True, which="major", linestyle="--", linewidth=0.7, alpha=0.5)
    ax.grid(True, which="minor", linestyle=":", linewidth=0.5, alpha=0.25)
    ax.tick_params(axis="both", which="major", labelsize=8)


def _build_vibration_time_chart_image(readings: list["AngleReading"], axis: str = TILT_AXIS) -> Image:
    fig, ax = plt.subplots(figsize=(16, 6))
    t0 = readings[0].timestamp
    xs = [r.timestamp - t0 for r in readings]
    ys = [_axis_value(r, axis) for r in readings]
    color = "#9467bd" if axis == PAN_AXIS else "#1f77b4"
    ax.plot(xs, ys, color=color, linewidth=0.8)
    ax.set_xlabel("Tempo (s)")
    ax.set_ylabel("Variação angular em relação à calibração (°)")
    _apply_reference_grid(ax)
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150)
    plt.close(fig)
    buf.seek(0)
    return Image(buf, width=17 * cm, height=6.5 * cm)


def _build_vibration_spectrum_chart_image(
    freqs: "np.ndarray", magnitudes: "np.ndarray", stats: "VibrationStats", axis: str = TILT_AXIS
) -> Image:
    fig, ax = plt.subplots(figsize=(16, 6))
    ax.plot(freqs, magnitudes, color="#8c564b" if axis == PAN_AXIS else "#d62728", linewidth=1)
    ax.set_xlabel("Frequência (Hz)")
    ax.set_ylabel("Amplitude (°)")
    _apply_reference_grid(ax)
    if stats.dominant_freq_hz is not None:
        ax.axvline(stats.dominant_freq_hz, color="#2ca02c", linestyle="--", linewidth=1.2, alpha=0.8)
        ax.annotate(
            f"{stats.dominant_freq_hz:.2f} Hz\n{stats.dominant_amplitude_deg:.3f}°",
            xy=(stats.dominant_freq_hz, stats.dominant_amplitude_deg),
            xytext=(8, 8),
            textcoords="offset points",
            color="#2ca02c",
            fontsize=9,
            fontweight="bold",
        )
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150)
    plt.close(fig)
    buf.seek(0)
    return Image(buf, width=17 * cm, height=6.5 * cm)


def _vibration_summary_rows(stats: "VibrationStats") -> list[list[str]]:
    return [
        ["Média", f"{stats.mean_deg:.3f}°"],
        ["Desvio padrão", f"{stats.std_dev_deg:.3f}°"],
        ["RMS", f"{stats.rms_deg:.3f}°"],
        ["Pico a pico", f"{stats.peak_to_peak_deg:.3f}°"],
        ["Mínimo / Máximo", f"{stats.min_deg:.3f}° / {stats.max_deg:.3f}°"],
        [
            "Frequência dominante",
            (
                f"{stats.dominant_freq_hz:.2f} Hz  "
                f"(amplitude {stats.dominant_amplitude_deg:.3f}°, SNR {stats.dominant_snr_db:.1f} dB)"
                if stats.dominant_freq_hz is not None
                else "nenhum pico confiável identificado (sinal compatível com ruído)"
            ),
        ],
    ]


def _vibration_table(rows: list[list[str]]) -> Table:
    table = Table(rows, colWidths=[7 * cm, 9 * cm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    return table


def _append_vibration_axis_section(
    story: list, styles, title: str, readings: list["AngleReading"], analysis: "AxisAnalysis"
) -> None:
    """Bloco de um eixo no relatório: tabela de estatísticas, gráfico no
    tempo e espectro. Os dois eixos usam exatamente o mesmo bloco."""
    story.append(Paragraph(title, styles["Heading2"]))
    story.append(_vibration_table(_vibration_summary_rows(analysis.stats)))
    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph("Variação angular ao longo do tempo", styles["Heading3"]))
    story.append(_build_vibration_time_chart_image(readings, analysis.axis))
    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph("Espectro de frequência (FFT)", styles["Heading3"]))
    story.append(
        _build_vibration_spectrum_chart_image(
            analysis.freqs, analysis.magnitudes, analysis.stats, analysis.axis
        )
    )


def generate_vibration_report(
    path: str,
    capture_info: "VibrationCaptureInfo | None",
    readings: list["AngleReading"],
    tilt: "AxisAnalysis",
    pan: "AxisAnalysis | None" = None,
) -> None:
    """Relatório de uma captura de vibração (Modo Vibração): resumo
    estatístico, gráfico da variação angular no tempo e espectro de
    frequência (FFT) para cada eixo, para identificar eventual frequência de
    ressonância dominante (ex: balanço de mastro sob vento).

    `pan` é `None` quando a captura veio de um firmware anterior à v1.3.0,
    que não amostra o eixo de azimute."""
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(path, pagesize=A4, title="Relatório de Captura de Vibração")
    story = []

    story.append(Paragraph("Relatório de Captura de Vibração", styles["Title"]))
    story.append(Spacer(1, 0.5 * cm))

    mode_label = _MODE_LABELS.get(capture_info.mode, capture_info.mode) if capture_info else "-"
    started = _fmt_dt(capture_info.started_at) if capture_info else "-"
    duration_cfg = f"{capture_info.duration_s:.0f} s" if capture_info else "-"
    rate_cfg = f"{capture_info.rate_hz:.0f} Hz" if capture_info else "-"

    story.append(
        _vibration_table(
            [
                ["Modo", mode_label],
                ["Início", started],
                ["Duração configurada", duration_cfg],
                ["Taxa de amostragem configurada", rate_cfg],
                ["Amostras capturadas", str(tilt.stats.n_samples)],
                ["Duração efetiva", f"{tilt.stats.duration_s:.2f} s"],
            ]
        )
    )
    story.append(Spacer(1, 0.8 * cm))

    _append_vibration_axis_section(story, styles, "Inclinação (tilt)", readings, tilt)

    story.append(PageBreak())
    if pan is not None:
        _append_vibration_axis_section(story, styles, "Azimute (pan)", readings, pan)
    else:
        story.append(Paragraph("Azimute (pan)", styles["Heading2"]))
        story.append(
            Paragraph(
                "O eixo de azimute não foi capturado: o ESP32 conectado estava com firmware"
                " anterior à v1.2.0 (leitura contínua) ou v1.3.0 (Modo Vibração), que não"
                " amostram esse eixo.",
                styles["Normal"],
            )
        )

    doc.build(story)
