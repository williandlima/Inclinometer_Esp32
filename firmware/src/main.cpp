// Firmware do Inclinômetro ESP32 — expõe os dois eixos medidos pelo MPU6050
// (tilt pelo acelerômetro, pan pelo giroscópio) tanto por Modbus RTU (via
// cabo USB direto) quanto por Bluetooth LE, seguindo os contratos
// documentados em python-app/data_source/{modbus_source,ble_source}.py e
// android-app/.../datasource/BleContract.kt. Orientação de montagem do
// sensor em AngleSensor.h ainda não foi confirmada (ver firmware/README.md).
#include <Arduino.h>

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
VibrationCapture vibrationCapture(angleSensor, panSensor);
ModbusSlave modbusSlave(angleSensor, panSensor, vibrationCapture);
BleServer bleServer(angleSensor, panSensor, vibrationCapture);

void setup() {
    // Sem Serial.println() de debug aqui de propósito: a UART0 (porta USB)
    // agora carrega o protocolo Modbus RTU byte a byte — qualquer texto de
    // debug escrito nela corromperia o framing visto pelo app no PC.
    mpu.begin();

    modbusSlave.begin();
    bleServer.begin();
}

void loop() {
    angleSensor.update();  // alimenta o filtro da leitura contínua (tilt)
    panSensor.update();    // integra o giro + ZUPT (pan)
    vibrationCapture.update();
    modbusSlave.update();
    bleServer.update();
}
