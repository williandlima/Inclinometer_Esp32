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
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet

if TYPE_CHECKING:
    from data_source.base import AngleReading
    from limits.history_store import SessionInfo, VibrationCaptureInfo
    from limits.limit_tracker import LimitEvent
    from limits.vibration_stats import VibrationStats
    import numpy as np

_MODE_LABELS = {
    "simulado": "Simulação",
    "real": "Real (USB/Modbus RTU)",
    "ble": "Real (Bluetooth BLE)",
}


def _fmt_dt(ts: float) -> str:
    return _dt.datetime.fromtimestamp(ts).strftime("%d/%m/%Y %H:%M:%S")


def _build_chart_image(readings: list["AngleReading"], events: list["LimitEvent"]) -> Image:
    fig, ax = plt.subplots(figsize=(16, 8))
    if readings:
        t0 = readings[0].timestamp
        xs = [(r.timestamp - t0) for r in readings]
        ys = [r.angle_deg for r in readings]
        ax.plot(xs, ys, color="#1f77b4", linewidth=1, label="Ângulo")

        mins_x = [(e.reading.timestamp - t0) for e in events if e.kind == "min"]
        mins_y = [e.reading.angle_deg for e in events if e.kind == "min"]
        maxs_x = [(e.reading.timestamp - t0) for e in events if e.kind == "max"]
        maxs_y = [e.reading.angle_deg for e in events if e.kind == "max"]
        ax.scatter(mins_x, mins_y, color="#d62728", marker="v", zorder=3, label="Novo mínimo")
        ax.scatter(maxs_x, maxs_y, color="#2ca02c", marker="^", zorder=3, label="Novo máximo")

    ax.set_xlabel("Tempo (s)")
    ax.set_ylabel("Ângulo (°)")
    ax.set_ylim(-5, 125)
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
    angle_min = min((r.angle_deg for r in readings), default=None)
    angle_max = max((r.angle_deg for r in readings), default=None)

    summary_rows = [
        ["Modo", mode_label],
        ["Início", started],
        ["Fim", ended],
        ["Leituras registradas", str(n_readings)],
        ["Ângulo mínimo observado", f"{angle_min:.2f}°" if angle_min is not None else "-"],
        ["Ângulo máximo observado", f"{angle_max:.2f}°" if angle_max is not None else "-"],
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

    story.append(Paragraph("Ângulo ao longo do tempo", styles["Heading2"]))
    story.append(_build_chart_image(readings, events))
    story.append(Spacer(1, 0.8 * cm))

    story.append(Paragraph("Histórico de limites atingidos", styles["Heading2"]))
    if events:
        event_rows = [["#", "Tipo", "Ângulo", "Data/Hora"]]
        for i, e in enumerate(events, start=1):
            tipo = "Novo mínimo" if e.kind == "min" else "Novo máximo"
            event_rows.append([str(i), tipo, f"{e.reading.angle_deg:.2f}°", _fmt_dt(e.reading.timestamp)])
        events_table = Table(event_rows, colWidths=[1.5 * cm, 4 * cm, 3 * cm, 6 * cm])
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


def _build_vibration_time_chart_image(readings: list["AngleReading"]) -> Image:
    fig, ax = plt.subplots(figsize=(16, 6))
    t0 = readings[0].timestamp
    xs = [r.timestamp - t0 for r in readings]
    ys = [r.angle_deg for r in readings]
    ax.plot(xs, ys, color="#1f77b4", linewidth=0.8)
    ax.set_xlabel("Tempo (s)")
    ax.set_ylabel("Variação angular em relação à calibração (°)")
    ax.grid(True, linestyle="--", alpha=0.4)
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150)
    plt.close(fig)
    buf.seek(0)
    return Image(buf, width=17 * cm, height=6.5 * cm)


def _build_vibration_spectrum_chart_image(freqs: "np.ndarray", magnitudes: "np.ndarray") -> Image:
    fig, ax = plt.subplots(figsize=(16, 6))
    ax.plot(freqs, magnitudes, color="#d62728", linewidth=1)
    ax.set_xlabel("Frequência (Hz)")
    ax.set_ylabel("Amplitude (°)")
    ax.grid(True, linestyle="--", alpha=0.4)
    fig.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150)
    plt.close(fig)
    buf.seek(0)
    return Image(buf, width=17 * cm, height=6.5 * cm)


def generate_vibration_report(
    path: str,
    capture_info: "VibrationCaptureInfo | None",
    readings: list["AngleReading"],
    stats: "VibrationStats",
    freqs: "np.ndarray",
    magnitudes: "np.ndarray",
) -> None:
    """Relatório de uma captura de vibração (Modo Vibração): resumo
    estatístico, gráfico da variação angular no tempo e espectro de
    frequência (FFT), para identificar eventual frequência de ressonância
    dominante (ex: balanço de mastro sob vento)."""
    styles = getSampleStyleSheet()
    doc = SimpleDocTemplate(path, pagesize=A4, title="Relatório de Captura de Vibração")
    story = []

    story.append(Paragraph("Relatório de Captura de Vibração", styles["Title"]))
    story.append(Spacer(1, 0.5 * cm))

    mode_label = _MODE_LABELS.get(capture_info.mode, capture_info.mode) if capture_info else "-"
    started = _fmt_dt(capture_info.started_at) if capture_info else "-"
    duration_cfg = f"{capture_info.duration_s:.0f} s" if capture_info else "-"
    rate_cfg = f"{capture_info.rate_hz:.0f} Hz" if capture_info else "-"

    summary_rows = [
        ["Modo", mode_label],
        ["Início", started],
        ["Duração configurada", duration_cfg],
        ["Taxa de amostragem configurada", rate_cfg],
        ["Amostras capturadas", str(stats.n_samples)],
        ["Duração efetiva", f"{stats.duration_s:.2f} s"],
        ["Média", f"{stats.mean_deg:.3f}°"],
        ["Desvio padrão", f"{stats.std_dev_deg:.3f}°"],
        ["RMS", f"{stats.rms_deg:.3f}°"],
        ["Pico a pico", f"{stats.peak_to_peak_deg:.3f}°"],
        ["Mínimo / Máximo", f"{stats.min_deg:.3f}° / {stats.max_deg:.3f}°"],
    ]
    summary_table = Table(summary_rows, colWidths=[7 * cm, 9 * cm])
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

    story.append(Paragraph("Variação angular ao longo do tempo", styles["Heading2"]))
    story.append(_build_vibration_time_chart_image(readings))
    story.append(Spacer(1, 0.8 * cm))

    story.append(Paragraph("Espectro de frequência (FFT)", styles["Heading2"]))
    story.append(_build_vibration_spectrum_chart_image(freqs, magnitudes))

    doc.build(story)
