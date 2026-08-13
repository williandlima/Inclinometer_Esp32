// Firmware do Inclinômetro ESP32 — expõe o ângulo do MPU6050 tanto por
// RS485/Modbus RTU quanto por Bluetooth LE, seguindo os contratos
// documentados em python-app/data_source/{modbus_source,ble_source}.py e
// android-app/.../datasource/BleContract.kt. Pinagem e orientação do
// sensor em Config.h/AngleSensor.h ainda são placeholders a confirmar
// junto ao projeto elétrico (ver firmware/README.md).
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
    Serial.begin(115200);

    if (!angleSensor.begin()) {
        Serial.println("Falha ao iniciar o MPU6050 - verifique a fiacao I2C.");
    }

    modbusSlave.begin();
    bleServer.begin();

    Serial.println("Inclinometro ESP32 pronto (RS485/Modbus RTU + BLE).");
}

void loop() {
    vibrationCapture.update();
    modbusSlave.update();
    bleServer.update();
}
