"""Diálogos do Modo Vibração: configurar a captura (duração/taxa) e exibir
o resultado (estatísticas + opção de salvar relatório em PDF)."""
from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt5.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
)

if TYPE_CHECKING:
    from limits.vibration_stats import VibrationStats


class VibrationConfigDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Modo Vibração — Configurar captura")

        layout = QVBoxLayout(self)

        info = QLabel(
            "Posicione o pan-tilt na posição de referência (ex: 90°) e use "
            "\"Calibrar\" antes de iniciar, para que a variação registrada "
            "seja relativa a essa posição."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        form = QFormLayout()

        self.duration_spin = QSpinBox()
        self.duration_spin.setRange(5, 600)
        self.duration_spin.setValue(30)
        self.duration_spin.setSuffix(" s")
        form.addRow("Duração da captura:", self.duration_spin)

        self.rate_spin = QSpinBox()
        self.rate_spin.setRange(1, 200)
        self.rate_spin.setValue(50)
        self.rate_spin.setSuffix(" Hz")
        form.addRow("Taxa de amostragem:", self.rate_spin)

        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def result_values(self) -> tuple[float, float]:
        return float(self.duration_spin.value()), float(self.rate_spin.value())


class VibrationResultDialog(QDialog):
    def __init__(self, stats: "VibrationStats", parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Modo Vibração — Resultado da captura")
        self._save_requested = False

        layout = QVBoxLayout(self)

        summary = (
            f"Amostras: {stats.n_samples}  (duração efetiva: {stats.duration_s:.2f} s)\n\n"
            f"Média: {stats.mean_deg:.3f}°\n"
            f"Desvio padrão: {stats.std_dev_deg:.3f}°\n"
            f"RMS: {stats.rms_deg:.3f}°\n"
            f"Pico a pico: {stats.peak_to_peak_deg:.3f}°\n"
            f"Mínimo / Máximo: {stats.min_deg:.3f}° / {stats.max_deg:.3f}°"
        )
        label = QLabel(summary)
        layout.addWidget(label)

        save_btn = QPushButton("Salvar relatório PDF...")
        save_btn.clicked.connect(self._on_save)
        layout.addWidget(save_btn)

        close_btn = QPushButton("Fechar")
        close_btn.clicked.connect(self.accept)
        layout.addWidget(close_btn)

    def _on_save(self) -> None:
        self._save_requested = True
        self.accept()

    @property
    def save_requested(self) -> bool:
        return self._save_requested
