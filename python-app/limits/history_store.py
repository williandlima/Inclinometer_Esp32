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
    angle_deg REAL NOT NULL,
    pan_deg REAL
);

CREATE TABLE IF NOT EXISTS limit_events (
    session_id INTEGER NOT NULL REFERENCES sessions(id),
    kind TEXT NOT NULL,
    angle_deg REAL NOT NULL,
    timestamp REAL NOT NULL,
    axis TEXT NOT NULL DEFAULT 'tilt',
    pan_deg REAL
);

CREATE TABLE IF NOT EXISTS vibration_captures (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at REAL NOT NULL,
    mode TEXT NOT NULL,
    duration_s REAL NOT NULL,
    rate_hz REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS vibration_samples (
    capture_id INTEGER NOT NULL REFERENCES vibration_captures(id),
    timestamp REAL NOT NULL,
    angle_deg REAL NOT NULL,
    pan_deg REAL,
    pan_rate_dps REAL
);

CREATE INDEX IF NOT EXISTS idx_readings_session ON readings(session_id);
CREATE INDEX IF NOT EXISTS idx_limit_events_session ON limit_events(session_id);
CREATE INDEX IF NOT EXISTS idx_vibration_samples_capture ON vibration_samples(capture_id);
"""


@dataclass
class SessionInfo:
    id: int
    started_at: float
    ended_at: float | None
    mode: str


@dataclass
class VibrationCaptureInfo:
    id: int
    started_at: float
    mode: str
    duration_s: float
    rate_hz: float


# Colunas acrescentadas depois que o schema original já estava em uso, com o
# `ALTER TABLE` que as adiciona. `CREATE TABLE IF NOT EXISTS` não altera uma
# tabela que já existe, então sem isso um banco criado por uma versão anterior
# do app continuaria sem as colunas do eixo de azimute — e as gravações
# quebrariam com "no such column".
_MIGRATIONS = [
    ("readings", "pan_deg", "ALTER TABLE readings ADD COLUMN pan_deg REAL"),
    ("limit_events", "pan_deg", "ALTER TABLE limit_events ADD COLUMN pan_deg REAL"),
    ("limit_events", "axis", "ALTER TABLE limit_events ADD COLUMN axis TEXT NOT NULL DEFAULT 'tilt'"),
    ("vibration_samples", "pan_deg", "ALTER TABLE vibration_samples ADD COLUMN pan_deg REAL"),
    (
        "vibration_samples",
        "pan_rate_dps",
        "ALTER TABLE vibration_samples ADD COLUMN pan_rate_dps REAL",
    ),
]


class HistoryStore:
    def __init__(self, db_path: Path | str = DEFAULT_DB_PATH) -> None:
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._migrate()
        self._conn.commit()
        self._current_session_id: int | None = None

    def _migrate(self) -> None:
        """Aplica as colunas novas a bancos criados por versões anteriores.

        Os registros antigos ficam com `pan_deg` nulo e `axis = 'tilt'`, que é
        exatamente a verdade sobre eles: foram gravados quando só existia o
        eixo de inclinação.
        """
        for table, column, statement in _MIGRATIONS:
            existing = {row[1] for row in self._conn.execute(f"PRAGMA table_info({table})")}
            if column not in existing:
                self._conn.execute(statement)

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
            "INSERT INTO readings (session_id, timestamp, angle_deg, pan_deg) VALUES (?, ?, ?, ?)",
            (self._current_session_id, reading.timestamp, reading.angle_deg, reading.pan_deg),
        )
        self._conn.commit()

    def add_limit_event(self, event: LimitEvent) -> None:
        if self._current_session_id is None:
            return
        # Guarda os dois eixos da leitura (e não só o valor do eixo do
        # evento), para a releitura reconstruir o `AngleReading` inteiro.
        self._conn.execute(
            "INSERT INTO limit_events (session_id, kind, axis, angle_deg, pan_deg, timestamp)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                self._current_session_id,
                event.kind,
                event.axis,
                event.reading.angle_deg,
                event.reading.pan_deg,
                event.reading.timestamp,
            ),
        )
        self._conn.commit()

    def list_sessions(self) -> list[SessionInfo]:
        rows = self._conn.execute(
            "SELECT id, started_at, ended_at, mode FROM sessions ORDER BY started_at DESC"
        ).fetchall()
        return [SessionInfo(*row) for row in rows]

    def get_readings(self, session_id: int) -> list[AngleReading]:
        rows = self._conn.execute(
            "SELECT angle_deg, timestamp, pan_deg FROM readings WHERE session_id = ? ORDER BY timestamp",
            (session_id,),
        ).fetchall()
        return [AngleReading(angle_deg=row[0], timestamp=row[1], pan_deg=row[2]) for row in rows]

    def get_limit_events(self, session_id: int) -> list[LimitEvent]:
        rows = self._conn.execute(
            "SELECT kind, angle_deg, timestamp, axis, pan_deg FROM limit_events"
            " WHERE session_id = ? ORDER BY timestamp",
            (session_id,),
        ).fetchall()
        return [
            LimitEvent(
                kind=row[0],
                reading=AngleReading(angle_deg=row[1], timestamp=row[2], pan_deg=row[4]),
                axis=row[3],
            )
            for row in rows
        ]

    def save_vibration_capture(
        self, mode: str, duration_s: float, rate_hz: float, readings: list[AngleReading]
    ) -> int:
        cur = self._conn.execute(
            "INSERT INTO vibration_captures (started_at, mode, duration_s, rate_hz) VALUES (?, ?, ?, ?)",
            (time.time(), mode, duration_s, rate_hz),
        )
        capture_id = cur.lastrowid
        self._conn.executemany(
            "INSERT INTO vibration_samples (capture_id, timestamp, angle_deg, pan_deg, pan_rate_dps)"
            " VALUES (?, ?, ?, ?, ?)",
            [(capture_id, r.timestamp, r.angle_deg, r.pan_deg, r.pan_rate_dps) for r in readings],
        )
        self._conn.commit()
        return capture_id

    def list_vibration_captures(self) -> list[VibrationCaptureInfo]:
        rows = self._conn.execute(
            "SELECT id, started_at, mode, duration_s, rate_hz FROM vibration_captures ORDER BY started_at DESC"
        ).fetchall()
        return [VibrationCaptureInfo(*row) for row in rows]

    def get_vibration_samples(self, capture_id: int) -> list[AngleReading]:
        rows = self._conn.execute(
            "SELECT angle_deg, timestamp, pan_deg, pan_rate_dps FROM vibration_samples"
            " WHERE capture_id = ? ORDER BY timestamp",
            (capture_id,),
        ).fetchall()
        return [
            AngleReading(angle_deg=row[0], timestamp=row[1], pan_deg=row[2], pan_rate_dps=row[3])
            for row in rows
        ]

    def close(self) -> None:
        self._conn.close()
