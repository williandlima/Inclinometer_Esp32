#pragma once

#include <stdint.h>

#include <atomic>

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
    void handleResetPeaksWrite();
    void handleVibrationConfigWrite(uint16_t durationS, uint16_t rateHz);
    // Pedido de retransmissão a partir de `startIndex` no eixo indicado —
    // o app usa isto quando detecta um buraco na série recebida, já que
    // notificação BLE não tem confirmação e um pacote pode sumir em
    // silêncio se a fila do rádio encher.
    void handleVibrationResendWrite(uint16_t startIndex, bool pan);

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
    // Pedidos de retransmissão: escritos pela task do BLE e consumidos pelo
    // loop principal. Uma vaga POR EIXO: o app pede tilt e pan na mesma
    // rodada, e com uma vaga só o segundo pedido podia sobrescrever o
    // primeiro antes de o loop consumi-lo. Atômicos porque o consumo lê e
    // limpa de uma vez — com volatile, um pedido que chegasse entre a
    // leitura e a limpeza se perdia. NO_RESEND = nenhum pedido pendente.
    static constexpr uint32_t NO_RESEND = UINT32_MAX;
    std::atomic<uint32_t> _resendTiltFrom{NO_RESEND};
    std::atomic<uint32_t> _resendPanFrom{NO_RESEND};
    void consumeResend(std::atomic<uint32_t> &request, uint16_t &cursor);

    // Idem para calibrar/resetar picos: sem isso, handleCalibrateWrite()/
    // handleResetPeaksWrite() mutariam PanSensor/AngleSensor direto da task
    // do BLE, concorrentemente com panSensor.update()/angleSensor.update()
    // no loop() principal — corrida que corrompe o offset do pan e crava a
    // leitura no limite do clamp (ver PanSensor::readPanDeg).
    volatile bool _calibratePending = false;
    volatile bool _resetPeaksPending = false;

    // Atualiza o valor (sem notify) da characteristic de diagnóstico do pan.
    void updatePanDiagnostics();

    // Último pacote de extremos enviado, para notificar só quando muda.
    uint16_t _lastSentPeaks[4] = {0, 0, 0, 0};
    bool _hasSentPeaks = false;

    // Envia um pacote de amostras a partir de `cursor` (que é avançado) na
    // characteristic indicada. `pan` escolhe de qual dos dois buffers ler.
    void sendVibrationChunk(BLECharacteristic *characteristic, uint16_t &cursor, uint16_t total, bool pan);

    // Notifica tilt e pan na mesma cadência (BLE_NOTIFY_INTERVAL_MS), em
    // characteristics separadas — ver CHAR_PAN_UUID em Config.h.
    void notifyAngles();

    // Extremos do peak-hold num pacote só (ver CHAR_PEAKS_UUID em Config.h).
    // Chamado por notifyAngles(), mas só emite notify quando o valor muda.
    void notifyPeaks();

    void updateVibrationNotify();
};
