package com.williandlima.inclinometro.datasource

import kotlinx.coroutines.flow.Flow

/**
 * Fonte de leituras de ângulo. Implementada tanto pelo modo simulado quanto
 * pelo modo real (BLE), permitindo trocar a fonte sem alterar o resto do
 * app (UI, rastreamento de limites, histórico e relatório).
 */
interface AngleDataSource {
    /** Nome curto exibido na UI (ex: "Simulação" ou "BLE (AA:BB:CC:DD:EE:FF)"). */
    val label: String

    /** Fluxo contínuo de leituras. Cancelar a coleta encerra a conexão/loop. */
    fun readings(): Flow<AngleReading>

    /** Indica se esta fonte suporta [calibrate]. Por padrão, não. */
    val supportsCalibration: Boolean get() = false

    /**
     * Zera o eixo de tilt na posição atual. Chamada enquanto [readings] está
     * sendo coletado. Levanta [UnsupportedOperationException] se a fonte não
     * suportar.
     */
    suspend fun calibrate(): Unit =
        throw UnsupportedOperationException("Esta fonte de dados não suporta calibração.")

    /** Indica se esta fonte suporta [startVibrationCapture]. Por padrão, não. */
    val supportsVibrationCapture: Boolean get() = false

    /**
     * Inicia uma captura de amostras em alta taxa por `durationS` segundos, a
     * ~`rateHz` amostras/s — usada para caracterizar vibração/variação
     * angular (ex: efeito de vento em um mastro), que a leitura contínua
     * normal não consegue captar. `onProgress` é chamado periodicamente com
     * o percentual (0-100). Suspende até a captura terminar e retorna as
     * amostras capturadas; cancelar a coroutine chamadora cancela a captura.
     * Levanta [UnsupportedOperationException] se a fonte não suportar.
     */
    suspend fun startVibrationCapture(
        durationS: Int,
        rateHz: Int,
        onProgress: (Int) -> Unit,
    ): List<AngleReading> =
        throw UnsupportedOperationException("Esta fonte de dados não suporta captura de vibração.")
}
