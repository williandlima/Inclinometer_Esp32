"""Interface comum de fonte de dados de ângulo.

Tanto o modo simulado quanto o modo real (Modbus RTU via RS485) implementam
esta interface, permitindo trocar a fonte sem alterar o resto do app (UI,
rastreamento de limites, histórico e relatório).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable

# Faixa física do inclinômetro (0-120 graus), usada para clamping/validação.
ANGLE_MIN_DEG = 0.0
ANGLE_MAX_DEG = 120.0


@dataclass(frozen=True)
class AngleReading:
    angle_deg: float
    timestamp: float  # segundos desde epoch (time.time())


ReadingCallback = Callable[[AngleReading], None]
ErrorCallback = Callable[[str], None]


class IAngleDataSource(ABC):
    """Fonte de leituras de ângulo, entregues via callback em thread própria."""

    @abstractmethod
    def start(self, on_reading: ReadingCallback, on_error: ErrorCallback | None = None) -> None:
        """Inicia a leitura em background e passa a chamar on_reading periodicamente."""

    @abstractmethod
    def stop(self) -> None:
        """Para a leitura em background. Deve ser seguro chamar mesmo se não iniciado."""

    @property
    @abstractmethod
    def label(self) -> str:
        """Nome curto exibido na UI (ex: 'Simulação' ou 'RS485/Modbus RTU')."""

    @property
    def supports_calibration(self) -> bool:
        """Indica se esta fonte suporta `calibrate()`. Por padrão, não."""
        return False

    def calibrate(self) -> None:
        """Zera o eixo de tilt do acelerômetro na posição atual.

        Chamada de forma síncrona (bloqueante) pelo chamador; fontes que
        suportam calibração devem sobrescrever este método. Levanta
        `NotImplementedError` se a fonte não suportar.
        """
        raise NotImplementedError("Esta fonte de dados não suporta calibração.")
