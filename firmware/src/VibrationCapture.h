#pragma once

#include <stdint.h>

#include "AngleSensor.h"
#include "Config.h"

// Motor de captura de vibração compartilhado pelos dois transportes
// (Modbus RTU e BLE) — amostra o ângulo em alta taxa por um período
// configurável, sem bloquear o loop principal (chamar update() a cada
// iteração do loop()). Contrato: python-app/data_source/modbus_source.py
// e python-app/data_source/ble_source.py.
class VibrationCapture {
public:
    enum class Status : uint8_t { Idle = 0, Capturing = 1, Ready = 2, Error = 3 };

    explicit VibrationCapture(AngleSensor &sensor) : _sensor(sensor) {}

    // Inicia uma nova captura. `durationS`/`rateHz` são clampados a
    // VIBRATION_MAX_SAMPLES amostras no total, se necessário (limite de
    // memória do buffer). Retorna false se já houver captura em andamento
    // ou os parâmetros forem inválidos (nesse caso, status vira Error).
    bool start(uint16_t durationS, uint16_t rateHz);

    // Chamar a cada iteração do loop() — faz a amostragem não-bloqueante.
    void update();

    Status status() const { return _status; }
    uint8_t progressPercent() const { return _progressPercent; }
    uint16_t sampleCount() const { return _sampleCount; }

    // Amostra no índice pedido (ângulo relativo * ANGLE_SCALE, com sinal).
    // Retorna 0 se o índice ainda não foi capturado.
    int16_t sampleAt(uint16_t index) const;

private:
    AngleSensor &_sensor;
    Status _status = Status::Idle;
    uint8_t _progressPercent = 0;

    uint16_t _totalSamples = 0;
    uint16_t _sampleCount = 0;
    uint32_t _intervalMs = 0;
    uint32_t _lastSampleMs = 0;
    int16_t _buffer[VIBRATION_MAX_SAMPLES];
};
