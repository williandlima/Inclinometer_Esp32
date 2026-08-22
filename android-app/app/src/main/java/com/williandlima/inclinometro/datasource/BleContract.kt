package com.williandlima.inclinometro.datasource

import java.util.UUID

/**
 * Contrato BLE assumido com o firmware do ESP32 — mesmo contrato usado pelo
 * app desktop (`python-app/data_source/ble_source.py`) e implementado no
 * firmware (`firmware/src/BleServer.cpp`), para os transportes ficarem
 * consistentes:
 * - Serviço [SERVICE_UUID], característica [ANGLE_CHARACTERISTIC_UUID] com
 *   notify/read de 2 bytes little-endian (int16, com sinal, faixa -60° a
 *   +60°) igual a `angulo * ANGLE_SCALE`.
 * - Azimute (pan): [PAN_CHARACTERISTIC_UUID], mesmo formato de 2 bytes da
 *   característica de ângulo, notificada na mesma cadência. É separada da de
 *   tilt de propósito — assim um app antigo, que só conhece a de tilt,
 *   continua funcionando contra o firmware novo. Como são duas notificações
 *   distintas, o app usa a de tilt como gatilho e junta o último valor de pan
 *   recebido: as duas saem na mesma iteração do firmware, então a defasagem é
 *   de no máximo um ciclo de notify (~200ms), e só se um pacote se perder.
 *   Firmware anterior à v1.2.0 não tem essa característica — o app segue só
 *   com o tilt e `panDeg` fica `null`.
 * - Extremos (mín/máx de cada eixo): [PEAKS_CHARACTERISTIC_UUID], 8 bytes =
 *   4 int16 LE na escala do ângulo — tilt mín, tilt máx, pan mín, pan máx.
 *   Quem os mede é o firmware, e não o app, porque ele vê o sensor a 100 Hz
 *   enquanto o notify chega a 5 Hz: uma rajada de vento de meio segundo
 *   acontece inteira entre duas notificações. O firmware só notifica quando o
 *   valor muda (extremo fica parado quase o tempo todo), então o último
 *   pacote recebido continua valendo. Firmware anterior à v1.5.0 não tem essa
 *   característica — o app volta a calcular os extremos a partir das leituras.
 * - Reset dos extremos: escrever `0x01` em
 *   [RESET_PEAKS_CHARACTERISTIC_UUID] faz o firmware esquecê-los sem mexer
 *   no zero.
 * - Calibração: escrever o byte `0x01` em [CALIBRATE_CHARACTERISTIC_UUID]
 *   zera **os dois eixos** na posição atual, o que zera os extremos junto.
 * - Captura de vibração: escrever 4 bytes little-endian (duração em
 *   segundos + taxa em Hz, cada um uint16) em
 *   [VIBRATION_CONFIG_CHARACTERISTIC_UUID] inicia uma captura em alta taxa;
 *   o firmware notifica progresso/conclusão em
 *   [VIBRATION_STATUS_CHARACTERISTIC_UUID] (byte 0 = status: 0=ocioso,
 *   1=capturando, 2=pronto, 3=erro; byte 1 = progresso 0-100; quando
 *   pronto, bytes 2-3 = total de amostras uint16 LE) e envia os dados em
 *   [VIBRATION_DATA_CHARACTERISTIC_UUID] em pacotes (bytes 0-1 = índice
 *   inicial uint16 LE, restante = amostras int16 LE com sinal).
 * - Vibração do eixo de **azimute**: [VIBRATION_PAN_DATA_CHARACTERISTIC_UUID],
 *   mesmo formato de pacote, mas carregando **velocidade angular em graus/s**
 *   * [PAN_RATE_SCALE], e não ângulo (ver `firmware/src/VibrationCapture.h`
 *   para o porquê). O firmware envia todos os pacotes de tilt, depois todos
 *   os de pan, e só então notifica "pronto". Firmware anterior à v1.3.0 não
 *   tem essa característica — a captura sai só com o tilt.
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
    val PAN_CHARACTERISTIC_UUID: UUID = UUID.fromString("6e6e0008-3c17-4a2e-8f4b-1a2b3c4d5e6f")
    val VIBRATION_PAN_DATA_CHARACTERISTIC_UUID: UUID =
        UUID.fromString("6e6e0009-3c17-4a2e-8f4b-1a2b3c4d5e6f")
    val PEAKS_CHARACTERISTIC_UUID: UUID = UUID.fromString("6e6e000a-3c17-4a2e-8f4b-1a2b3c4d5e6f")
    val RESET_PEAKS_CHARACTERISTIC_UUID: UUID =
        UUID.fromString("6e6e000b-3c17-4a2e-8f4b-1a2b3c4d5e6f")
    val CLIENT_CHARACTERISTIC_CONFIG_UUID: UUID = UUID.fromString("00002902-0000-1000-8000-00805f9b34fb")

    const val ANGLE_SCALE = 100.0

    /** Amostra de vibração do azimute = graus/s * 100 (int16, +-327°/s). */
    const val PAN_RATE_SCALE = 100.0
    const val VIBRATION_CAPTURE_TIMEOUT_MARGIN_S = 30L

    /**
     * Por quanto tempo os extremos vindos do dispositivo são ignorados depois
     * de um pedido de reset. A escrita BLE é assíncrona, então uma notificação
     * com os valores ANTIGOS pode estar em trânsito; como mín/máx só andam
     * para fora, um único pacote atrasado envenenaria a faixa nova de forma
     * permanente. Só precisa cobrir a latência de um pacote.
     */
    const val PEAKS_RESET_GRACE_MS = 1000L
}
