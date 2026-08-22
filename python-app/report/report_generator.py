"""Geração do relatório em PDF a partir do histórico de uma sessão:
gráfico do ângulo ao longo do tempo (com os extremos marcados), tabela de
eventos de limite e um resumo textual da sessão.
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
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)
from reportlab.lib.styles import getSampleStyleSheet

from limits.limit_tracker import PAN_AXIS, TILT_AXIS

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
    PAN_AXIS: ("Azimute", "Azimute (°)", "#9467bd", (-95, 95)),
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


def _build_chart_image(
    readings: list["AngleReading"], events: list["LimitEvent"], axis: str = TILT_AXIS
) -> Image:
    series_label, y_label, color, y_limits = _AXIS_CHART_CONFIG[axis]
    fig, ax = plt.subplots(figsize=(16, 8))

    # Leituras sem valor neste eixo são puladas (não viram zero na curva).
    points = [(r, _axis_value(r, axis)) for r in readings]
    points = [(r, v) for r, v in points if v is not None]
    if points:
        t0 = readings[0].timestamp
        xs = [(r.timestamp - t0) for r, _ in points]
        ys = [v for _, v in points]
        ax.plot(xs, ys, color=color, linewidth=1, label=series_label)

        axis_events = [e for e in events if e.axis == axis]
        mins_x = [(e.reading.timestamp - t0) for e in axis_events if e.kind == "min"]
        mins_y = [e.value_deg for e in axis_events if e.kind == "min"]
        maxs_x = [(e.reading.timestamp - t0) for e in axis_events if e.kind == "max"]
        maxs_y = [e.value_deg for e in axis_events if e.kind == "max"]
        ax.scatter(mins_x, mins_y, color="#d62728", marker="v", zorder=3, label="Novo mínimo")
        ax.scatter(maxs_x, maxs_y, color="#2ca02c", marker="^", zorder=3, label="Novo máximo")

    ax.set_xlabel("Tempo (s)")
    ax.set_ylabel(y_label)
    ax.set_ylim(*y_limits)
    ax.grid(True, linestyle="--", alpha=0.4)
    ax.legend(loc="upper right")
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150)
    plt.close(fig)
    buf.seek(0)

    img = Image(buf, width=17 * cm, height=8.5 * cm)
    return img


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
    story.append(Spacer(1, 0.5 * cm))

    mode_label = _MODE_LABELS.get(session_info.mode, session_info.mode) if session_info else "-"
    started = _fmt_dt(session_info.started_at) if session_info else "-"
    ended = _fmt_dt(session_info.ended_at) if (session_info and session_info.ended_at) else "em andamento"
    n_readings = len(readings)
    angle_min, angle_max = _axis_extremes(readings, events, TILT_AXIS)
    pan_values = [r.pan_deg for r in readings if r.pan_deg is not None]
    pan_min, pan_max = _axis_extremes(readings, events, PAN_AXIS)

    def _fmt_range(low: float | None, high: float | None) -> str:
        if low is None or high is None:
            return "-"
        return f"{low:.2f}°  /  {high:.2f}°"

    summary_rows = [
        ["Modo", mode_label],
        ["Início", started],
        ["Fim", ended],
        ["Leituras registradas", str(n_readings)],
        ["Inclinação mín. / máx. registrada", _fmt_range(angle_min, angle_max)],
        [
            "Azimute mín. / máx. registrado",
            _fmt_range(pan_min, pan_max)
            if pan_values
            else "não registrado (firmware sem eixo de azimute)",
        ],
    ]
    summary_table = Table(summary_rows, colWidths=[6 * cm, 10 * cm])
    summary_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.whitesmoke),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ]
        )
    )
    story.append(summary_table)
    story.append(Spacer(1, 0.8 * cm))

    story.append(Paragraph("Inclinação (tilt) ao longo do tempo", styles["Heading2"]))
    story.append(_build_chart_image(readings, events, TILT_AXIS))
    story.append(Spacer(1, 0.8 * cm))

    story.append(Paragraph("Azimute (pan) ao longo do tempo", styles["Heading2"]))
    if pan_values:
        story.append(_build_chart_image(readings, events, PAN_AXIS))
    else:
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
        event_rows = [["#", "Eixo", "Tipo", "Valor", "Data/Hora"]]
        for i, e in enumerate(events, start=1):
            tipo = "Novo mínimo" if e.kind == "min" else "Novo máximo"
            eixo = "Azimute" if e.axis == PAN_AXIS else "Inclinação"
            event_rows.append(
                [str(i), eixo, tipo, f"{e.value_deg:.2f}°", _fmt_dt(e.reading.timestamp)]
            )
        events_table = Table(event_rows, colWidths=[1.2 * cm, 3 * cm, 3.5 * cm, 2.8 * cm, 5 * cm])
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
        story.append(Paragraph("Nenhum evento de limite registrado nesta sessão.", styles["Normal"]))

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
