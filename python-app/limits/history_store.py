"""Persistência do histórico de leituras e eventos de limite em SQLite.

Cada execução do app abre (ou cria) o mesmo arquivo de banco e trabalha
dentro de "sessões" — uma sessão corresponde a um período contínuo de
monitoramento (do Iniciar até o Parar/fechar), guardando as leituras e os
eventos de novo mínimo/máximo, para depois alimentar o relatório em PDF.
"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path

from data_source.base import AngleReading
from limits.limit_tracker import LimitEvent

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent / "inclinometro_historico.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at REAL NOT NULL,
    ended_at REAL,
    mode TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS readings (
    session_id INTEGER NOT NULL REFERENCES sessions(id),
    timestamp REAL NOT NULL,
    angle_deg REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS limit_events (
    session_id INTEGER NOT NULL REFERENCES sessions(id),
    kind TEXT NOT NULL,
    angle_deg REAL NOT NULL,
    timestamp REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_readings_session ON readings(session_id);
CREATE INDEX IF NOT EXISTS idx_limit_events_session ON limit_events(session_id);
"""


@dataclass
class SessionInfo:
    id: int
    started_at: float
    ended_at: float | None
    mode: str


class HistoryStore:
    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH) -> None:
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        self._current_session_id: int | None = None

    def start_session(self, mode: str) -> int:
        cur = self._conn.execute(
            "INSERT INTO sessions (started_at, mode) VALUES (?, ?)", (time.time(), mode)
        )
        self._conn.commit()
        self._current_session_id = cur.lastrowid
        return self._current_session_id

    def end_session(self) -> None:
        if self._current_session_id is None:
            return
        self._conn.execute(
            "UPDATE sessions SET ended_at = ? WHERE id = ?", (time.time(), self._current_session_id)
        )
        self._conn.commit()
        self._current_session_id = None

    @property
    def current_session_id(self) -> int | None:
        return self._current_session_id

    def add_reading(self, reading: AngleReading) -> None:
        if self._current_session_id is None:
            return
        self._conn.execute(
            "INSERT INTO readings (session_id, timestamp, angle_deg) VALUES (?, ?, ?)",
            (self._current_session_id, reading.timestamp, reading.angle_deg),
        )
        self._conn.commit()

    def add_limit_event(self, event: LimitEvent) -> None:
        if self._current_session_id is None:
            return
        self._conn.execute(
            "INSERT INTO limit_events (session_id, kind, angle_deg, timestamp) VALUES (?, ?, ?, ?)",
            (self._current_session_id, event.kind, event.reading.angle_deg, event.reading.timestamp),
        )
        self._conn.commit()

    def list_sessions(self) -> list[SessionInfo]:
        rows = self._conn.execute(
            "SELECT id, started_at, ended_at, mode FROM sessions ORDER BY started_at DESC"
        ).fetchall()
        return [SessionInfo(*row) for row in rows]

    def get_readings(self, session_id: int) -> list[AngleReading]:
        rows = self._conn.execute(
            "SELECT angle_deg, timestamp FROM readings WHERE session_id = ? ORDER BY timestamp",
            (session_id,),
        ).fetchall()
        return [AngleReading(angle_deg=row[0], timestamp=row[1]) for row in rows]

    def get_limit_events(self, session_id: int) -> list[LimitEvent]:
        rows = self._conn.execute(
            "SELECT kind, angle_deg, timestamp FROM limit_events WHERE session_id = ? ORDER BY timestamp",
            (session_id,),
        ).fetchall()
        return [
            LimitEvent(kind=row[0], reading=AngleReading(angle_deg=row[1], timestamp=row[2]))
            for row in rows
        ]

    def close(self) -> None:
        self._conn.close()
