// Firmware do Inclinômetro ESP32 — expõe os dois eixos medidos pelo MPU6050
// (tilt pelo acelerômetro, pan pelo giroscópio) tanto por Modbus RTU (via
// cabo USB direto) quanto por Bluetooth LE, seguindo os contratos
// documentados em python-app/data_source/{modbus_source,ble_source}.py e
// android-app/.../datasource/BleContract.kt. Orientação de montagem do
// sensor em AngleSensor.h ainda não foi confirmada (ver firmware/README.md).
#include <Arduino.h>
#include <Preferences.h>
#include <esp_task_wdt.h>

#include "AngleSensor.h"
#include "BleServer.h"
#include "ModbusSlave.h"
#include "Mpu6050.h"
#include "PanSensor.h"
#include "VibrationCapture.h"

// Um único MPU6050 físico, compartilhado por referência entre os dois
// sensores lógicos: AngleSensor lê o acelerômetro (tilt), PanSensor lê
// acelerômetro + giroscópio no mesmo burst (pan). Cada um faz a própria
// transação I2C, na própria cadência.
Mpu6050 mpu;
AngleSensor angleSensor(mpu);
PanSensor panSensor(mpu);
VibrationCapture vibrationCapture(angleSensor, panSensor, mpu);
ModbusSlave modbusSlave(angleSensor, panSensor, vibrationCapture);
BleServer bleServer(angleSensor, panSensor, vibrationCapture);

// ZERO DO TILT NA MEMÓRIA PERMANENTE (1.6.22). Até a 1.6.21 o zero da
// calibração vivia só na RAM: toda vez que o ESP32 era desligado (ou
// reiniciava sozinho), o tilt voltava a ser lido em relação ao zero do
// sensor e o operador precisava calibrar de novo — sem aviso nenhum de que
// o zero tinha sumido. O tilt vem da gravidade, uma referência absoluta,
// então o zero salvo continua valendo depois de religar. O PAN não: ele é
// integrado do giroscópio e recomeça em 0° na posição em que ligar.
//
// A gravação é feita aqui, no loop principal, comparando com o último valor
// salvo — e não dentro de calibrate(), que pode ser chamada a partir da
// task do BLE. Só grava quando o zero muda (calibrar é raro), então o
// desgaste da flash é desprezível.
Preferences preferences;
float savedTiltOffsetDeg = 0.0f;

static void restoreTiltOffset() {
    preferences.begin(NVS_NAMESPACE, false);
    float stored = preferences.getFloat(NVS_KEY_TILT_OFFSET, 0.0f);
    // Valor absurdo (flash corrompida, NaN) é ignorado: melhor sem zero que
    // com um zero errado.
    if (!(stored >= -180.0f && stored <= 180.0f)) {
        stored = 0.0f;
    }
    savedTiltOffsetDeg = stored;
    angleSensor.restoreCalibrationOffsetDeg(stored);
}

static void persistTiltOffsetIfChanged() {
    float current = angleSensor.calibrationOffsetDeg();
    if (current != savedTiltOffsetDeg) {
        preferences.putFloat(NVS_KEY_TILT_OFFSET, current);
        savedTiltOffsetDeg = current;
    }
}

// WATCHDOG (1.6.22). Se o loop principal travar (barramento I2C preso, bug),
// o ESP32 reinicia sozinho depois de WATCHDOG_TIMEOUT_S em vez de ficar
// mudo até alguém desligar e religar no topo do mastro. Os apps já
// reconectam sozinhos, e o zero do tilt volta da memória permanente.
static void startWatchdog() {
#if ESP_IDF_VERSION_MAJOR >= 5
    esp_task_wdt_config_t config = {};
    config.timeout_ms = WATCHDOG_TIMEOUT_S * 1000;
    config.trigger_panic = true;
    esp_task_wdt_reconfigure(&config);
#else
    esp_task_wdt_init(WATCHDOG_TIMEOUT_S, true);
#endif
    esp_task_wdt_add(nullptr);  // a task do loop()
}

void setup() {
    // Sem Serial.println() de debug aqui de propósito: a UART0 (porta USB)
    // agora carrega o protocolo Modbus RTU byte a byte — qualquer texto de
    // debug escrito nela corromperia o framing visto pelo app no PC.
    mpu.begin();
    restoreTiltOffset();
    if (TILT_FUSION_ENABLED) {
        angleSensor.attachGyro(&panSensor);  // tilt = giro + acelerômetro (AngleSensor.h)
    }

    modbusSlave.begin();
    bleServer.begin();
    startWatchdog();  // por último: a inicialização do BLE leva alguns segundos
}

void loop() {
    mpu.maintain();        // reconfigura o sensor se ele reiniciou (ver Mpu6050.h)
    angleSensor.update();  // alimenta o filtro da leitura contínua (tilt)
    panSensor.update();    // integra o giro + ZUPT (pan)
    vibrationCapture.update();
    modbusSlave.update();
    bleServer.update();
    persistTiltOffsetIfChanged();
    esp_task_wdt_reset();
}
