#pragma once

#include <stdint.h>

#include "AngleSensor.h"
#include "VibrationCapture.h"

// Servidor BLE (GATT) — contrato documentado em
// python-app/data_source/ble_source.py e
// android-app/.../datasource/BleContract.kt.
class BleServer {
public:
    BleServer(AngleSensor &sensor, VibrationCapture &vibration)
        : _sensor(sensor), _vibration(vibration) {}

    void begin();

    // Chamar a cada iteração do loop() — envia notify do ângulo em modo
    // contínuo e do progresso/dados da captura de vibração. A versão do
    // firmware é só leitura (não muda em runtime), então é escrita uma
    // única vez em begin() e não precisa de notify.
    void update();

    // Chamados pelos callbacks de escrita GATT (ver BleServer.cpp).
    void handleCalibrateWrite();
    void handleVibrationConfigWrite(uint16_t durationS, uint16_t rateHz);

private:
    AngleSensor &_sensor;
    VibrationCapture &_vibration;

    uint32_t _lastAngleNotifyMs = 0;
    VibrationCapture::Status _lastReportedVibrationStatus = VibrationCapture::Status::Idle;
    uint16_t _vibrationDataCursor = 0;
    uint32_t _lastVibrationStatusNotifyMs = 0;
    uint32_t _lastVibrationChunkMs = 0;

    void notifyAngle();
    void updateVibrationNotify();
};
