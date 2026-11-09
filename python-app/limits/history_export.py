"""Exportação das leituras de uma aquisição para CSV.

Formato pensado para abrir direto no Excel em português: separador ";" e
vírgula decimal, com BOM UTF-8 (sem ele o Excel troca os acentos). O
cabeçalho traz os dados da aquisição em linhas iniciadas por "#", que
ferramentas de análise (pandas `comment="#"`) ignoram.
"""
from __future__ import annotations

import csv
import datetime as _dt
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from data_source.base import AngleReading
    from limits.history_store import SessionInfo
    from limits.limit_tracker import LimitEvent


def _num(value: float | None, digits: int = 2) -> str:
    return "" if value is None else f"{value:.{digits}f}".replace(".", ",")


def export_session_csv(
    path: str,
    session: "SessionInfo",
    readings: list["AngleReading"],
    events: list["LimitEvent"] | None = None,
) -> int:
    """Grava o CSV e devolve o número de leituras exportadas."""
    events = events or []
    fmt = lambda ts: _dt.datetime.fromtimestamp(ts).strftime("%d/%m/%Y %H:%M:%S")  # noqa: E731
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        f.write(f"# Inclinometro - aquisicao {session.id}\n")
        f.write(f"# modo: {session.mode}\n")
        f.write(f"# inicio: {fmt(session.started_at)}\n")
        f.write(f"# fim: {fmt(session.ended_at) if session.ended_at else 'em andamento'}\n")
        f.write(f"# app: {session.app_version or '-'}; firmware: {session.firmware_version or '-'}\n")
        for e in events:
            f.write(f"# limite: {e.axis};{e.kind};{_num(e.value_deg)};{fmt(e.reading.timestamp)};{e.source}\n")
        w = csv.writer(f, delimiter=";")
        w.writerow(["data_hora", "t_s", "inclinacao_graus", "azimute_graus"])
        t0 = session.started_at
        for r in readings:
            stamp = _dt.datetime.fromtimestamp(r.timestamp)
            w.writerow([
                stamp.strftime("%d/%m/%Y %H:%M:%S") + f",{stamp.microsecond // 1000:03d}",
                _num(r.timestamp - t0, 3),
                _num(r.angle_deg),
                _num(r.pan_deg),
            ])
    return len(readings)
