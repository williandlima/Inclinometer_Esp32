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

from app_version import user_data_dir
from data_source.base import AngleReading
from limits.limit_tracker import LimitEvent

# Fica na pasta de dados desta versão do app — ver `app_version.user_data_dir`.
# Isso resolve duas coisas de uma vez: o banco vai para um lugar onde o
# usuário realmente pode escrever quando o app está instalado em Program
# Files, e os históricos de duas versões instaladas lado a lado não se
# misturam.
DEFAULT_DB_PATH = user_data_dir() / "inclinometro_historico.db"

# Intervalo máximo entre gravações em disco das leituras (ver `_commit_soon`).
COMMIT_INTERVAL_S = 1.0

# Por quanto tempo o histórico é mantido. O app grava ~4 leituras por
# segundo: 8 h de leitura por dia são ~115 mil linhas (~4 MB), e até a 2.3.0
# nada era apagado — o arquivo só crescia. As opções aparecem em
# Configurações; `None` = manter sempre.
RETENTION_OPTIONS_DAYS: list[int | None] = [30, 90, 180, 365, None]
DEFAULT_RETENTION_DAYS = 90

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at REAL NOT NULL,
    ended_at REAL,
    mode TEXT NOT NULL,
    planned_duration_s REAL,
    firmware_version TEXT,
    app_version TEXT
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
    pan_deg REAL,
    source TEXT NOT NULL DEFAULT 'app'
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
    """Uma aquisição: do "Iniciar" (ou "Resetar limites"/"Calibrar", que
    abrem uma nova) até o "Parar" ou o fim do tempo programado.

    `planned_duration_s` é o tempo programado para a aquisição, ou `None`
    para aquisição livre (só termina no "Parar")."""

    id: int
    started_at: float
    ended_at: float | None
    mode: str
    planned_duration_s: float | None = None
    # Rastreabilidade da medição: versões com que a aquisição foi feita.
    firmware_version: str | None = None
    app_version: str | None = None


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
    ("limit_events", "source", "ALTER TABLE limit_events ADD COLUMN source TEXT NOT NULL DEFAULT 'app'"),
    ("sessions", "planned_duration_s", "ALTER TABLE sessions ADD COLUMN planned_duration_s REAL"),
    ("sessions", "firmware_version", "ALTER TABLE sessions ADD COLUMN firmware_version TEXT"),
    ("sessions", "app_version", "ALTER TABLE sessions ADD COLUMN app_version TEXT"),
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
        self._db_path = str(db_path)
        self._last_commit = time.monotonic()

    def _commit_soon(self) -> None:
        """Grava em disco no máximo uma vez por COMMIT_INTERVAL_S.

        Antes era um commit (fsync) por leitura — 4 a 5 por segundo, o dia
        inteiro. Em lote, uma queda de energia perde no máximo o último
        segundo de leituras; tudo o que importa (fim da aquisição, eventos
        consultados pelo relatório) passa por `flush()`.
        """
        now = time.monotonic()
        if now - self._last_commit >= COMMIT_INTERVAL_S:
            self._conn.commit()
            self._last_commit = now

    def flush(self) -> None:
        self._conn.commit()
        self._last_commit = time.monotonic()

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

    def start_session(
        self, mode: str, planned_duration_s: float | None = None, app_version: str | None = None
    ) -> int:
        cur = self._conn.execute(
            "INSERT INTO sessions (started_at, mode, planned_duration_s, app_version) VALUES (?, ?, ?, ?)",
            (time.time(), mode, planned_duration_s, app_version),
        )
        self.flush()
        self._current_session_id = cur.lastrowid
        return self._current_session_id

    def end_session(self) -> None:
        if self._current_session_id is None:
            return
        self._conn.execute(
            "UPDATE sessions SET ended_at = ? WHERE id = ?", (time.time(), self._current_session_id)
        )
        self.flush()
        self._current_session_id = None

    def set_firmware_version(self, version: str | None) -> None:
        """Anota na aquisição atual a versão do firmware conectado (só é
        conhecida depois de conectar, não no início da aquisição)."""
        if self._current_session_id is None or not version:
            return
        self._conn.execute(
            "UPDATE sessions SET firmware_version = ? WHERE id = ? AND firmware_version IS NOT ?",
            (version, self._current_session_id, version),
        )
        self._commit_soon()

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
        self._commit_soon()

    def add_limit_event(self, event: LimitEvent) -> None:
        if self._current_session_id is None:
            return
        # Guarda os dois eixos da leitura (e não só o valor do eixo do
        # evento), para a releitura reconstruir o `AngleReading` inteiro.
        self._conn.execute(
            "INSERT INTO limit_events (session_id, kind, axis, angle_deg, pan_deg, timestamp, source)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                self._current_session_id,
                event.kind,
                event.axis,
                event.reading.angle_deg,
                event.reading.pan_deg,
                event.reading.timestamp,
                event.source,
            ),
        )
        self._commit_soon()

    def list_sessions(self) -> list[SessionInfo]:
        rows = self._conn.execute(
            "SELECT id, started_at, ended_at, mode, planned_duration_s, firmware_version, app_version FROM sessions"
            " ORDER BY started_at DESC, id DESC"
        ).fetchall()
        return [SessionInfo(*row) for row in rows]

    def get_session(self, session_id: int) -> SessionInfo | None:
        row = self._conn.execute(
            "SELECT id, started_at, ended_at, mode, planned_duration_s, firmware_version, app_version FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        return SessionInfo(*row) if row else None

    def count_readings(self, session_id: int) -> int:
        return self._conn.execute(
            "SELECT COUNT(*) FROM readings WHERE session_id = ?", (session_id,)
        ).fetchone()[0]

    def latest_session_with_readings(self) -> SessionInfo | None:
        """A aquisição mais recente que tem leituras.

        Era usada a mais recente de todas, mas "Resetar limites" e "Calibrar"
        abrem uma aquisição nova: clicar num deles e depois em "Parar" deixava
        uma aquisição vazia por último, e o relatório saía sem dado nenhum.
        """
        row = self._conn.execute(
            "SELECT s.id, s.started_at, s.ended_at, s.mode, s.planned_duration_s, s.firmware_version, s.app_version"
            " FROM sessions s"
            " WHERE EXISTS (SELECT 1 FROM readings r WHERE r.session_id = s.id)"
            " ORDER BY s.started_at DESC, s.id DESC LIMIT 1"
        ).fetchone()
        return SessionInfo(*row) if row else None

    def get_readings(self, session_id: int) -> list[AngleReading]:
        rows = self._conn.execute(
            "SELECT angle_deg, timestamp, pan_deg FROM readings WHERE session_id = ? ORDER BY timestamp",
            (session_id,),
        ).fetchall()
        return [AngleReading(angle_deg=row[0], timestamp=row[1], pan_deg=row[2]) for row in rows]

    def get_limit_events(self, session_id: int) -> list[LimitEvent]:
        rows = self._conn.execute(
            "SELECT kind, angle_deg, timestamp, axis, pan_deg, source FROM limit_events"
            " WHERE session_id = ? ORDER BY timestamp",
            (session_id,),
        ).fetchall()
        return [
            LimitEvent(
                kind=row[0],
                reading=AngleReading(angle_deg=row[1], timestamp=row[2], pan_deg=row[4]),
                axis=row[3],
                source=row[5],
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

    # ------------------------------------------------------------ retenção
    def size_bytes(self) -> int:
        """Tamanho do arquivo do histórico (0 para banco em memória)."""
        try:
            return Path(self._db_path).stat().st_size
        except OSError:
            return 0

    def stats(self) -> dict:
        q = lambda sql: self._conn.execute(sql).fetchone()[0]  # noqa: E731
        return {
            "sessions": q("SELECT COUNT(*) FROM sessions"),
            "readings": q("SELECT COUNT(*) FROM readings"),
            "vibration_captures": q("SELECT COUNT(*) FROM vibration_captures"),
            "oldest": q("SELECT MIN(started_at) FROM sessions"),
            "size_bytes": self.size_bytes(),
        }

    def prune(self, retention_days: int | None, now: float | None = None) -> dict:
        """Apaga do histórico o que passou do prazo de retenção e devolve o
        que foi removido.

        - aquisições (com leituras e eventos de limite) e capturas de
          vibração iniciadas há mais de `retention_days` dias — `None` não
          apaga nada por idade;
        - sempre: aquisições encerradas que ficaram SEM leitura nenhuma
          (ex.: "Resetar limites" seguido de "Parar", ou falha de conexão),
          que só ocupam a lista;
        - nunca a aquisição em andamento.

        Depois de apagar, o arquivo é compactado (VACUUM): sem isso o SQLite
        guarda o espaço livre para reutilizar e o arquivo não diminui.
        """
        self.flush()
        current = self._current_session_id if self._current_session_id is not None else -1
        removed = {"sessions": 0, "readings": 0, "vibration_captures": 0, "empty_sessions": 0}
        size_before = self.size_bytes()

        old_ids: list[int] = []
        if retention_days is not None:
            cutoff = (now if now is not None else time.time()) - retention_days * 86400.0
            old_ids = [r[0] for r in self._conn.execute(
                "SELECT id FROM sessions WHERE started_at < ? AND id != ?", (cutoff, current))]
            old_caps = [r[0] for r in self._conn.execute(
                "SELECT id FROM vibration_captures WHERE started_at < ?", (cutoff,))]
            for cid in old_caps:
                self._conn.execute("DELETE FROM vibration_samples WHERE capture_id = ?", (cid,))
                self._conn.execute("DELETE FROM vibration_captures WHERE id = ?", (cid,))
            removed["vibration_captures"] = len(old_caps)

        empty_ids = [r[0] for r in self._conn.execute(
            "SELECT s.id FROM sessions s WHERE s.ended_at IS NOT NULL AND s.id != ?"
            " AND NOT EXISTS (SELECT 1 FROM readings r WHERE r.session_id = s.id)", (current,))]
        removed["empty_sessions"] = len(set(empty_ids) - set(old_ids))

        for sid in set(old_ids) | set(empty_ids):
            removed["readings"] += self._conn.execute(
                "DELETE FROM readings WHERE session_id = ?", (sid,)).rowcount
            self._conn.execute("DELETE FROM limit_events WHERE session_id = ?", (sid,))
            self._conn.execute("DELETE FROM sessions WHERE id = ?", (sid,))
        removed["sessions"] = len(old_ids)
        self.flush()

        if removed["readings"] or removed["vibration_captures"]:
            try:
                self._conn.execute("VACUUM")
            except sqlite3.Error:
                pass  # compactação é só economia de disco: não pode impedir o app de abrir
        removed["freed_bytes"] = max(0, size_before - self.size_bytes())
        return removed

    def close(self) -> None:
        self.flush()
        self._conn.close()
