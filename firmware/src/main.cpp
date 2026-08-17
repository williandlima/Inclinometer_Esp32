// Firmware do Inclinômetro ESP32 — expõe o ângulo do MPU6050 tanto por
// Modbus RTU (via cabo USB direto) quanto por Bluetooth LE, seguindo os
// contratos documentados em python-app/data_source/{modbus_source,ble_source}.py
// e android-app/.../datasource/BleContract.kt. Orientação de montagem do
// sensor em AngleSensor.h ainda não foi confirmada (ver firmware/README.md).
#include <Arduino.h>

#include "AngleSensor.h"
#include "BleServer.h"
#include "ModbusSlave.h"
#include "VibrationCapture.h"

AngleSensor angleSensor;
VibrationCapture vibrationCapture(angleSensor);
ModbusSlave modbusSlave(angleSensor, vibrationCapture);
BleServer bleServer(angleSensor, vibrationCapture);

void setup() {
    // Sem Serial.println() de debug aqui de propósito: a UART0 (porta USB)
    // agora carrega o protocolo Modbus RTU byte a byte — qualquer texto de
    // debug escrito nela corromperia o framing visto pelo app no PC.
    angleSensor.begin();

    modbusSlave.begin();
    bleServer.begin();
}

void loop() {
    angleSensor.update();  // alimenta o filtro da leitura contínua
    vibrationCapture.update();
    modbusSlave.update();
    bleServer.update();
}
