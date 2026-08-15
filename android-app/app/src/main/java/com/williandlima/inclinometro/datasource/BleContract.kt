package com.williandlima.inclinometro.datasource

import java.util.UUID

/**
 * Contrato BLE assumido com o firmware do ESP32 — mesmo contrato usado pelo
 * app desktop (`python-app/data_source/ble_source.py`) e implementado no
 * firmware (`firmware/src/BleServer.cpp`), para os transportes ficarem
 * consistentes:
 * - Serviço [SERVICE_UUID], característica [ANGLE_CHARACTERISTIC_UUID] com
 *   notify/read de 2 bytes little-endian igual a `angulo * ANGLE_SCALE`.
 * - Calibração: escrever o byte `0x01` em [CALIBRATE_CHARACTERISTIC_UUID]
 *   zera o eixo de tilt na posição atual.
 * - Captura de vibração: escrever 4 bytes little-endian (duração em
 *   segundos + taxa em Hz, cada um uint16) em
 *   [VIBRATION_CONFIG_CHARACTERISTIC_UUID] inicia uma captura em alta taxa;
 *   o firmware notifica progresso/conclusão em
 *   [VIBRATION_STATUS_CHARACTERISTIC_UUID] (byte 0 = status: 0=ocioso,
 *   1=capturando, 2=pronto, 3=erro; byte 1 = progresso 0-100; quando
 *   pronto, bytes 2-3 = total de amostras uint16 LE) e envia os dados em
 *   [VIBRATION_DATA_CHARACTERISTIC_UUID] em pacotes (bytes 0-1 = índice
 *   inicial uint16 LE, restante = amostras int16 LE com sinal).
 * - Versão do firmware: [FIRMWARE_VERSION_CHARACTERISTIC_UUID], read-only,
 *   2 bytes little-endian = `major*10000 + minor*100 + patch` (ex: "1.0.0"
 *   -> 10000). Valor fixo (não muda em runtime, sem notify) — ainda não
 *   lido pelo app Android (só documentado aqui para paridade de contrato;
 *   o app desktop já exibe no teste de conexão).
 */
object BleContract {
    val SERVICE_UUID: UUID = UUID.fromString("6e6e0001-3c17-4a2e-8f4b-1a2b3c4d5e6f")
    val ANGLE_CHARACTERISTIC_UUID: UUID = UUID.fromString("6e6e0002-3c17-4a2e-8f4b-1a2b3c4d5e6f")
    val CALIBRATE_CHARACTERISTIC_UUID: UUID = UUID.fromString("6e6e0003-3c17-4a2e-8f4b-1a2b3c4d5e6f")
    val VIBRATION_CONFIG_CHARACTERISTIC_UUID: UUID = UUID.fromString("6e6e0004-3c17-4a2e-8f4b-1a2b3c4d5e6f")
    val VIBRATION_STATUS_CHARACTERISTIC_UUID: UUID = UUID.fromString("6e6e0005-3c17-4a2e-8f4b-1a2b3c4d5e6f")
    val VIBRATION_DATA_CHARACTERISTIC_UUID: UUID = UUID.fromString("6e6e0006-3c17-4a2e-8f4b-1a2b3c4d5e6f")
    val FIRMWARE_VERSION_CHARACTERISTIC_UUID: UUID = UUID.fromString("6e6e0007-3c17-4a2e-8f4b-1a2b3c4d5e6f")
    val CLIENT_CHARACTERISTIC_CONFIG_UUID: UUID = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb")

    const val ANGLE_SCALE = 100.0
    const val VIBRATION_CAPTURE_TIMEOUT_MARGIN_S = 30L
}
