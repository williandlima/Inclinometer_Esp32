#pragma once

#include <stdint.h>

#include "AngleSensor.h"
#include "Config.h"
#include "PanSensor.h"

// Motor de captura de vibração compartilhado pelos dois transportes
// (Modbus RTU e BLE) — amostra os DOIS eixos em alta taxa por um período
// configurável, sem bloquear o loop principal (chamar update() a cada
// iteração do loop()). Contrato: python-app/data_source/modbus_source.py
// e python-app/data_source/ble_source.py.
//
// Os dois eixos guardam grandezas DIFERENTES, de propósito:
// - tilt: o ângulo relativo à calibração, em graus * ANGLE_SCALE;
// - pan: a VELOCIDADE ANGULAR, em graus/s * PAN_RATE_SCALE.
//
// O motivo está em PanSensor::readInstantRateDps(): o ângulo de pan é obtido
// por integração com ZUPT, e o ZUPT cancela de propósito o que foi integrado
// enquanto o eixo está parado — que é exatamente a condição de um ensaio de
// vibração. Guardar o ângulo integrado apagaria o sinal que se quer medir.
// A taxa não passa por isso, e ainda joga o bias residual em 0 Hz, onde a
// análise espectral já o descarta. Os apps integram e removem a tendência
// linear para obter a variação angular em graus.
//
// As duas amostras de um mesmo índice vêm de leituras I2C separadas, com
// ~1ms de diferença. Isso não importa porque cada eixo é analisado
// independentemente (não há espectro cruzado entre eles).
class VibrationCapture {
public:
    enum class Status : uint8_t { Idle = 0, Capturing = 1, Ready = 2, Error = 3 };

    VibrationCapture(AngleSensor &sensor, PanSensor &pan) : _sensor(sensor), _pan(pan) {}

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

    // Amostra de tilt no índice pedido (ângulo relativo * ANGLE_SCALE, com
    // sinal). Retorna 0 se o índice ainda não foi capturado.
    int16_t sampleAt(uint16_t index) const;

    // Amostra de pan no índice pedido (velocidade angular em graus/s *
    // PAN_RATE_SCALE, com sinal). Retorna 0 se o índice ainda não foi
    // capturado.
    int16_t panSampleAt(uint16_t index) const;

private:
    AngleSensor &_sensor;
    PanSensor &_pan;
    Status _status = Status::Idle;
    uint8_t _progressPercent = 0;

    uint16_t _totalSamples = 0;
    uint16_t _sampleCount = 0;
    uint32_t _intervalMs = 0;
    uint32_t _lastSampleMs = 0;

    // Arredonda e satura para int16, o formato das amostras no protocolo.
    static int16_t toInt16(float scaledValue);
    // Dois buffers de VIBRATION_MAX_SAMPLES int16 = ~24KB de RAM estática no
    // total. Cabe com folga no ESP32 mesmo com o stack BLE ativo, mas é o
    // maior consumo de memória do firmware — se um dia precisar de capturas
    // mais longas, é aqui que o limite aperta.
    int16_t _buffer[VIBRATION_MAX_SAMPLES];
    int16_t _panBuffer[VIBRATION_MAX_SAMPLES];
};
