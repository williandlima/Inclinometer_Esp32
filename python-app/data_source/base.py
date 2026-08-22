"""Interface comum de fonte de dados de ângulo.

Tanto o modo simulado quanto os modos reais (Modbus RTU via USB, BLE)
implementam esta interface, permitindo trocar a fonte sem alterar o resto
do app (UI, rastreamento de limites, histórico e relatório).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable

# Faixa física do eixo de inclinação (-60 a +60 graus), usada para
# clamping/validação.
ANGLE_MIN_DEG = -60.0
ANGLE_MAX_DEG = 60.0

# Faixa do eixo de azimute (pan). Espelha PAN_MIN_DEG/PAN_MAX_DEG de
# firmware/src/Config.h — ainda é um placeholder ali, a ajustar quando a
# mecânica do pan estiver definida.
PAN_MIN_DEG = -90.0
PAN_MAX_DEG = 90.0


@dataclass(frozen=True)
class AngleReading:
    """Uma leitura dos eixos do inclinômetro.

    `pan_deg` é opcional: fica `None` quando a fonte não fornece azimute —
    caso de um ESP32 com firmware anterior à v1.2.0, que não expõe o
    registrador/characteristic de pan. Todo o resto do app (limites,
    histórico, relatório) trata `None` como "este eixo não foi medido" e
    simplesmente o ignora, em vez de assumir zero.
    """

    angle_deg: float
    timestamp: float  # segundos desde epoch (time.time())
    pan_deg: float | None = None

    # Só preenchido em capturas do Modo Vibração: a velocidade angular bruta
    # do eixo de azimute, como o firmware a envia (`pan_deg` é a integral
    # dela). Guardar as duas não é redundância — a análise espectral do
    # azimute precisa da taxa, cujo ruído é branco, enquanto os gráficos e as
    # estatísticas no tempo precisam do ângulo. Ver `limits.vibration_stats`.
    pan_rate_dps: float | None = None


def build_vibration_readings(
    angles_deg: list[float],
    pan_rates_dps: list[float] | None,
    rate_hz: float,
    t_start: float,
) -> list[AngleReading]:
    """Monta as amostras de uma captura de vibração a partir das séries
    brutas de cada eixo, usada pelas três fontes de dados.

    `pan_rates_dps` são **velocidades angulares** (graus/s), como o firmware
    as envia, e são convertidas aqui para variação angular — ver
    `limits.vibration_stats.pan_rates_to_angles`. Passe `None` (ou uma lista
    de tamanho diferente do eixo de tilt) quando o firmware conectado não
    fornecer o eixo de azimute: as amostras saem com `pan_deg` nulo.
    """
    # Import local para `data_source` não depender de numpy quando só as
    # leituras contínuas forem usadas, e para não amarrar a ordem de import
    # entre os pacotes `data_source` e `limits`.
    from limits.vibration_stats import pan_rates_to_angles

    pan_angles: list[float] | None = None
    if pan_rates_dps is not None and len(pan_rates_dps) == len(angles_deg):
        pan_angles = pan_rates_to_angles(pan_rates_dps, rate_hz)

    return [
        AngleReading(
            angle_deg=angle,
            timestamp=t_start + i / rate_hz,
            pan_deg=pan_angles[i] if pan_angles is not None else None,
            pan_rate_dps=pan_rates_dps[i] if pan_angles is not None else None,
        )
        for i, angle in enumerate(angles_deg)
    ]


ReadingCallback = Callable[[AngleReading], None]
ErrorCallback = Callable[[str], None]
VibrationProgressCallback = Callable[[float], None]  # percentual 0-100
VibrationDoneCallback = Callable[[list[AngleReading] | None, str | None], None]  # amostras, erro


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
        """Nome curto exibido na UI (ex: 'Simulação' ou 'USB/Modbus RTU')."""

    @property
    def supports_calibration(self) -> bool:
        """Indica se esta fonte suporta `calibrate()`. Por padrão, não."""
        return False

    def calibrate(self) -> None:
        """Zera os dois eixos (tilt e pan) na posição atual.

        É uma ação só, de propósito: o firmware zera tilt e pan juntos no
        mesmo comando (`COIL_CALIBRATE`/`CHAR_CALIBRATE_UUID`), então a UI
        expõe um único botão "Calibrar".

        Chamada de forma síncrona (bloqueante) pelo chamador; fontes que
        suportam calibração devem sobrescrever este método. Levanta
        `NotImplementedError` se a fonte não suportar.
        """
        raise NotImplementedError("Esta fonte de dados não suporta calibração.")

    @property
    def supports_vibration_capture(self) -> bool:
        """Indica se esta fonte suporta captura de vibração em alta taxa
        (`start_vibration_capture`). Por padrão, não."""
        return False

    def start_vibration_capture(
        self,
        duration_s: float,
        rate_hz: float,
        on_progress: VibrationProgressCallback,
        on_done: VibrationDoneCallback,
    ) -> None:
        """Inicia uma captura de amostras em alta taxa por `duration_s`
        segundos, a ~`rate_hz` amostras/s — usada para caracterizar
        vibração/variação angular (ex: efeito de vento em um mastro), que a
        leitura contínua normal (poll a cada ~250ms) não consegue captar.

        Não bloqueante: roda em background e chama `on_progress(percentual)`
        periodicamente e `on_done(amostras, erro)` ao final — `amostras` é
        `None` e `erro` descreve a falha (ou cancelamento) em caso de erro.
        Fontes que suportam devem sobrescrever este método. Levanta
        `NotImplementedError` se a fonte não suportar.
        """
        raise NotImplementedError("Esta fonte de dados não suporta captura de vibração.")

    def stop_vibration_capture(self) -> None:
        """Cancela uma captura de vibração em andamento, se houver. Seguro
        chamar mesmo sem captura em andamento. No-op por padrão."""
        return
