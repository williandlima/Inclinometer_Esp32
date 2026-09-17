#pragma once

#include <stdint.h>

#include "AngleSensor.h"
#include "Config.h"
#include "Mpu6050.h"
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

    VibrationCapture(AngleSensor &sensor, PanSensor &pan, Mpu6050 &mpu)
        : _sensor(sensor), _pan(pan), _mpu(mpu) {}

    // Inicia uma nova captura. `durationS`/`rateHz` são clampados a
    // VIBRATION_MAX_SAMPLES amostras no total, se necessário (limite de
    // memória do buffer). Retorna false se já houver captura em andamento
    // ou os parâmetros forem inválidos (nesse caso, status vira Error).
    //
    // ATENÇÃO: deve ser chamado a partir do loop principal, nunca de dentro
    // de um callback do BLE — ver requestStart().
    bool start(uint16_t durationS, uint16_t rateHz);

    // Agenda uma captura para ser iniciada na próxima chamada de update().
    // É o que os callbacks do BLE devem usar: eles rodam na task do stack
    // BLE, e start() mexe nos mesmos campos que update() usa no loop
    // principal (contador de amostras, buffers, status) — chamá-lo dali
    // abriria uma corrida entre as duas tasks. Mesmo motivo pelo qual o
    // reinício do anúncio BLE já é adiado para o loop (ver BleServer.cpp).
    void requestStart(uint16_t durationS, uint16_t rateHz);

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
    Mpu6050 &_mpu;
    // volatile: lido pela task do BLE (status/notificação) enquanto o loop
    // principal o escreve.
    volatile Status _status = Status::Idle;
    volatile uint8_t _progressPercent = 0;

    // Pedido de início vindo de outra task, consumido por update().
    volatile bool _startPending = false;
    volatile uint16_t _pendingDurationS = 0;
    volatile uint16_t _pendingRateHz = 0;

    uint16_t _totalSamples = 0;
    volatile uint16_t _sampleCount = 0;
    // Período em MICROSSEGUNDOS, não milissegundos: com milissegundos, o
    // período de uma taxa alta era truncado por divisão inteira (300Hz
    // viravam 3ms = 333Hz de verdade), e o app calcula todas as frequências
    // do espectro a partir da taxa PEDIDA — um desvio ali desloca o espectro
    // inteiro. Em microssegundos o erro de quantização fica abaixo de 0,1%
    // em toda a faixa até VIBRATION_MAX_RATE_HZ.
    uint32_t _intervalUs = 0;
    uint32_t _lastSampleUs = 0;

    // Arredonda e satura para int16, o formato das amostras no protocolo.
    static int16_t toInt16(float scaledValue);
    // Dois buffers de VIBRATION_MAX_SAMPLES int16 = ~24KB de RAM estática no
    // total. Cabe com folga no ESP32 mesmo com o stack BLE ativo, mas é o
    // maior consumo de memória do firmware — se um dia precisar de capturas
    // mais longas, é aqui que o limite aperta.
    int16_t _buffer[VIBRATION_MAX_SAMPLES];
    int16_t _panBuffer[VIBRATION_MAX_SAMPLES];
};
