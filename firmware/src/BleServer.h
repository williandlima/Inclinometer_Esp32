#pragma once

#include <stdint.h>

#include "AngleSensor.h"
#include "PanSensor.h"
#include "VibrationCapture.h"

// Declarada só como ponteiro aqui, para este header não arrastar o header da
// lib BLE (e o tempo de compilação junto) para quem o inclui.
class BLECharacteristic;

// Servidor BLE (GATT) — contrato documentado em
// python-app/data_source/ble_source.py e
// android-app/.../datasource/BleContract.kt.
class BleServer {
public:
    BleServer(AngleSensor &sensor, PanSensor &pan, VibrationCapture &vibration)
        : _sensor(sensor), _pan(pan), _vibration(vibration) {}

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
    PanSensor &_pan;
    VibrationCapture &_vibration;

    uint32_t _lastAngleNotifyMs = 0;
    VibrationCapture::Status _lastReportedVibrationStatus = VibrationCapture::Status::Idle;
    uint16_t _vibrationDataCursor = 0;
    uint16_t _vibrationPanDataCursor = 0;
    uint32_t _lastVibrationStatusNotifyMs = 0;
    uint32_t _lastVibrationChunkMs = 0;

    // Envia um pacote de amostras a partir de `cursor` (que é avançado) na
    // characteristic indicada. `pan` escolhe de qual dos dois buffers ler.
    void sendVibrationChunk(BLECharacteristic *characteristic, uint16_t &cursor, uint16_t total, bool pan);

    // Notifica tilt e pan na mesma cadência (BLE_NOTIFY_INTERVAL_MS), em
    // characteristics separadas — ver CHAR_PAN_UUID em Config.h.
    void notifyAngles();
    void updateVibrationNotify();
};
