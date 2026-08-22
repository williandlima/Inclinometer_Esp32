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
        _filterReady = true;
        return;
    }

    // Média móvel exponencial com alpha derivado do tempo realmente decorrido
    // (e não do intervalo nominal), para o filtro manter a mesma constante de
    // tempo mesmo se o loop atrasar — ex: durante uma captura de vibração,
    // que divide o barramento I2C.
    float dtS = elapsedMs / 1000.0f;
    float alpha = dtS / (ANGLE_FILTER_TIME_CONSTANT_S + dtS);
    _filteredRawDeg += alpha * (rawDeg - _filteredRawDeg);
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
