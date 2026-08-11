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
}
