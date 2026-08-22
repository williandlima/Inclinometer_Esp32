#include "AngleSensor.h"

#include <Arduino.h>
#include <math.h>

#include "Config.h"

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

bool AngleSensor::readRawAngleDeg(float &angleDeg) {
    float ax, ay, az;
    if (!_mpu.readAccelG(ax, ay, az)) {
        return false;
    }
    angleDeg = atan2(ay, az) * 180.0f / static_cast<float>(M_PI);
    _lastRawDeg = angleDeg;
    return true;
}

float AngleSensor::emaAlpha(float cutoffHz, float dtS) {
    // tau = 1/(2*pi*fc); alpha = dt/(tau+dt)
    float tau = 1.0f / (2.0f * static_cast<float>(M_PI) * cutoffHz);
    return dtS / (tau + dtS);
}

void AngleSensor::update() {
    uint32_t now = millis();
    if (_filterReady && now - _lastSampleMs < ANGLE_SAMPLE_INTERVAL_MS) {
        return;
    }
    uint32_t elapsedMs = now - _lastSampleMs;
    _lastSampleMs = now;

    float rawDeg;
    if (!readRawAngleDeg(rawDeg)) {
        return;  // falha de I2C: preserva o estado do filtro em vez de corrompê-lo
    }

    if (!_filterReady) {
        // Primeira amostra entra direto: sem isso a leitura começaria em 0°
        // e levaria segundos subindo até o valor real.
        _filteredRawDeg = rawDeg;
        _prevRawDeg = rawDeg;
        _filteredRateDps = 0.0f;
        _filterReady = true;
        return;
    }

    // dt vem do tempo REALMENTE decorrido, e não do intervalo nominal, para o
    // filtro manter o mesmo comportamento se o loop atrasar — ex: durante uma
    // captura de vibração, que divide o barramento I2C.
    float dtS = elapsedMs / 1000.0f;
    if (dtS <= 0.0f) {
        return;  // relógio não avançou: nada a integrar, e evita divisão por zero
    }

    // Filtro 1-euro (ver o bloco ANGLE_FILTER_* em Config.h). Primeiro estima
    // a velocidade angular e a suaviza; é ela que decide o quanto o filtro
    // deve "abrir".
    float rateDps = (rawDeg - _prevRawDeg) / dtS;
    _prevRawDeg = rawDeg;
    _filteredRateDps += emaAlpha(ANGLE_FILTER_DERIV_CUTOFF_HZ, dtS) * (rateDps - _filteredRateDps);

    // Parado, a velocidade é ~0 e o corte fica em MIN_CUTOFF (bem suave).
    // Em movimento real, o termo do BETA levanta o corte e o filtro acompanha.
    float cutoffHz = ANGLE_FILTER_MIN_CUTOFF_HZ + ANGLE_FILTER_BETA * fabsf(_filteredRateDps);
    _filteredRawDeg += emaAlpha(cutoffHz, dtS) * (rawDeg - _filteredRawDeg);
}

float AngleSensor::readRelativeAngleDeg() {
    float rawDeg;
    if (!readRawAngleDeg(rawDeg)) {
        rawDeg = _lastRawDeg;  // amostra perdida: repete a última válida
    }
    return rawDeg - _offsetDeg;
}

float AngleSensor::readAngleDeg() {
    float angle = _filteredRawDeg - _offsetDeg;
    if (angle < ANGLE_MIN_DEG) angle = ANGLE_MIN_DEG;
    if (angle > ANGLE_MAX_DEG) angle = ANGLE_MAX_DEG;
    return angle;
}

void AngleSensor::calibrate() {
    _offsetDeg = _filteredRawDeg;
}
