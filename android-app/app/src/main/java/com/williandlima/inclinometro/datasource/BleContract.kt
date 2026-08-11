package com.williandlima.inclinometro.datasource

import java.util.UUID

/**
 * Contrato BLE assumido com o firmware do ESP32 (ainda não implementado
 * nesta fase do projeto). O ângulo atual é exposto como característica com
 * notify, valor de 2 bytes little-endian igual a `angulo * 100` (mesma
 * escala usada no registrador Modbus do app desktop), para manter os dois
 * transportes consistentes até o firmware existir de fato.
 */
object BleContract {
    val SERVICE_UUID: UUID = UUID.fromString("6e6e0001-3c17-4a2e-8f4b-1a2b3c4d5e6f")
    val ANGLE_CHARACTERISTIC_UUID: UUID = UUID.fromString("6e6e0002-3c17-4a2e-8f4b-1a2b3c4d5e6f")
    val CLIENT_CHARACTERISTIC_CONFIG_UUID: UUID = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb")

    const val ANGLE_SCALE = 100.0
}
