"""Janela de Histórico: lista as aquisições gravadas e permite gerar o
relatório PDF, exportar as leituras em CSV ou apagar uma delas.

Antes, o relatório só podia ser gerado da aquisição atual ou da última:
depois de um novo "Iniciar", as anteriores continuavam no banco, mas sem
nenhum caminho na tela para chegar até elas.
"""
from __future__ import annotations

import datetime as _dt
from typing import Callable

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from report.acquisition import format_duration, format_planned

_MODES = {"simulado": "Simulação", "real": "USB", "ble": "Bluetooth"}
_COLUMNS = ["Início", "Duração", "Modo", "Leituras", "Inclinação mín/máx", "Azimute mín/máx", "Programado", "Firmware"]


def _range(lo: float | None, hi: float | None) -> str:
    return "—" if lo is None or hi is None else f"{lo:.2f}° / {hi:.2f}°"


class HistoryDialog(QDialog):
    def __init__(
        self,
        history,
        on_report: Callable[[int], None],
        on_export: Callable[[int], None],
        on_delete: Callable[[int], bool],
        retention_text: str = "",
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Histórico de aquisições")
        self.resize(1200, 520)
        self._history = history
        self._on_report, self._on_export, self._on_delete = on_report, on_export, on_delete

        layout = QVBoxLayout(self)
        self.info_label = QLabel()
        layout.addWidget(self.info_label)

        self.table = QTableWidget(0, len(_COLUMNS))
        self.table.setHorizontalHeaderLabels(_COLUMNS)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        # Cada coluna na largura do seu conteúdo (a data inteira tem de caber);
        # a última ocupa o que sobrar.
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemSelectionChanged.connect(self._update_buttons)
        self.table.doubleClicked.connect(lambda _i: self._act(self._on_report))
        layout.addWidget(self.table, 1)

        self._retention_text = retention_text
        buttons = QHBoxLayout()
        self.report_btn = QPushButton("Gerar relatório PDF")
        self.report_btn.clicked.connect(lambda: self._act(self._on_report))
        self.export_btn = QPushButton("Exportar CSV...")
        self.export_btn.clicked.connect(lambda: self._act(self._on_export))
        self.delete_btn = QPushButton("Apagar")
        self.delete_btn.clicked.connect(self._delete)
        close_btn = QPushButton("Fechar")
        close_btn.clicked.connect(self.accept)
        for b in (self.report_btn, self.export_btn, self.delete_btn):
            buttons.addWidget(b)
        buttons.addStretch(1)
        buttons.addWidget(close_btn)
        layout.addLayout(buttons)
        self.reload()

    def reload(self) -> None:
        self._rows = self._history.list_session_summaries()
        self.table.setRowCount(len(self._rows))
        for i, row in enumerate(self._rows):
            s = row["session"]
            start = _dt.datetime.fromtimestamp(s.started_at).strftime("%d/%m/%Y %H:%M:%S")
            if row["in_progress"]:
                start += "  (em andamento)"
            values = [
                start,
                format_duration(row["duration_s"]),
                _MODES.get(s.mode, s.mode),
                str(row["n_readings"]),
                _range(row["tilt_min"], row["tilt_max"]),
                _range(row["pan_min"], row["pan_max"]),
                format_planned(s.planned_duration_s) if s.planned_duration_s else "Livre",
                s.firmware_version or "—",
            ]
            for col, text in enumerate(values):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignCenter)
                self.table.setItem(i, col, item)
        st = self._history.stats()
        text = f"{len(self._rows)} aquisições com leituras — {st['readings']} leituras, {st['size_bytes'] / 1e6:.1f} MB."
        if self._retention_text:
            text += f"  Mantidas por: {self._retention_text} (mude em Configurações)."
        self.info_label.setText(text)
        if self._rows:
            self.table.selectRow(0)
        self._update_buttons()

    def selected_session_id(self) -> int | None:
        r = self.table.currentRow()
        return self._rows[r]["session"].id if 0 <= r < len(self._rows) else None

    def _update_buttons(self) -> None:
        r = self.table.currentRow()
        has = 0 <= r < len(self._rows)
        self.report_btn.setEnabled(has)
        self.export_btn.setEnabled(has)
        # A aquisição em andamento não pode ser apagada.
        self.delete_btn.setEnabled(has and not self._rows[r]["in_progress"])

    def _act(self, fn: Callable[[int], None]) -> None:
        sid = self.selected_session_id()
        if sid is not None:
            fn(sid)

    def _delete(self) -> None:
        sid = self.selected_session_id()
        if sid is not None and self._on_delete(sid):
            self.reload()
