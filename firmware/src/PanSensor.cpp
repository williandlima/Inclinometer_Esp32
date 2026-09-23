#include "PanSensor.h"

#include <Arduino.h>
#include <math.h>

#include "Config.h"

bool PanSensor::sampleMotion(float &gyDps, float &gzDps, float &tiltRad) {
    float ax, ay, az, gxDps;
    if (!_mpu.readMotion(ax, ay, az, gxDps, gyDps, gzDps)) {
        return false;
    }
    // Tilt do MESMO burst: sem defasagem entre o ângulo usado na projeção e
    // as taxas projetadas.
    tiltRad = atan2f(ay, az);
    return true;
}

float PanSensor::panRateDps(float gyDps, float gzDps, float tiltRad) const {
    // Projeção da velocidade angular sobre a vertical, escrita em coordenadas
    // do corpo (item 1 do cabeçalho de PanSensor.h), com o bias de cada eixo
    // removido ANTES de projetar (item 2).
    return (gzDps - _biasGzDps) * cosf(tiltRad) - (gyDps - _biasGyDps) * sinf(tiltRad);
}

float PanSensor::readInstantRateDps() {
    float gyDps, gzDps, tiltRad;
    if (!sampleMotion(gyDps, gzDps, tiltRad)) {
        return _lastRateDps;  // amostra perdida: repete a última válida
    }
    _lastRateDps = panRateDps(gyDps, gzDps, tiltRad) * PAN_SCALE_CORRECTION;
    return _lastRateDps;
}

void PanSensor::update() {
    uint32_t now = millis();
    if (_hasLastSample && now - _lastSampleMs < ANGLE_SAMPLE_INTERVAL_MS) {
        return;
    }
    uint32_t elapsedMs = now - _lastSampleMs;
    _lastSampleMs = now;

    float gyDps, gzDps, tiltRad;
    if (!sampleMotion(gyDps, gzDps, tiltRad)) {
        return;  // falha de I2C: preserva o estado em vez de corrompê-lo
    }

    if (!_hasLastSample) {
        // Primeira amostra: sem intervalo anterior, não há dt para integrar.
        _hasLastSample = true;
        resetWindow(now);
        return;
    }

    float dtS = elapsedMs / 1000.0f;
    if (dtS > PAN_MAX_INTEGRATION_DT_S) {
        dtS = PAN_MAX_INTEGRATION_DT_S;
    }

    // Só integra depois que a primeira janela estabeleceu o bias: antes
    // disso, o zero-rate de fábrica (±20°/s) jogaria o ângulo longe.
    if (_biasReady) {
        float deltaDeg = panRateDps(gyDps, gzDps, tiltRad) * dtS * PAN_SCALE_CORRECTION;
        _panDeg += deltaDeg;
        _windowDeltaDeg += deltaDeg;
    }

    _windowGySumDps += gyDps;
    _windowGzSumDps += gzDps;
    _windowSamples++;

    if (now - _windowStartMs >= PAN_ZUPT_WINDOW_MS) {
        closeWindow(now);
    }

    // Extremos amostrados a 100 Hz, e não na cadência do protocolo: uma
    // varredura do motor a 20-30°/s atravessa vários graus entre duas leituras
    // do app. Ver minPanDeg() em PanSensor.h.
    _peaks.push(readPanDeg());
}

void PanSensor::closeWindow(uint32_t now) {
    if (_windowSamples == 0) {
        resetWindow(now);
        return;
    }

    float meanGyDps = _windowGySumDps / _windowSamples;
    float meanGzDps = _windowGzSumDps / _windowSamples;

    if (!_biasReady) {
        // Primeira janela desde o boot (ou desde a última calibração): adota
        // a média como bias, sem aplicar limiar. Ver "PREMISSA DE BOOT" em
        // PanSensor.h — o zero-rate de fábrica é grande demais para passar
        // por qualquer limiar razoável.
        _biasGyDps = meanGyDps;
        _biasGzDps = meanGzDps;
        _biasReady = true;
    } else {
        float dGy = meanGyDps - _biasGyDps;
        float dGz = meanGzDps - _biasGzDps;
        if (hypotf(dGy, dGz) < PAN_ZUPT_RATE_THRESHOLD_DPS) {
            // Janela parada: refina o bias e desfaz o que foi integrado nela,
            // para o ruído do giro não virar random walk enquanto parado.
            _biasGyDps += PAN_ZUPT_BIAS_ALPHA * dGy;
            _biasGzDps += PAN_ZUPT_BIAS_ALPHA * dGz;
            _panDeg -= _windowDeltaDeg;
        }
    }

    resetWindow(now);
}

void PanSensor::resetWindow(uint32_t now) {
    _windowStartMs = now;
    _windowGySumDps = 0.0f;
    _windowGzSumDps = 0.0f;
    _windowSamples = 0;
    _windowDeltaDeg = 0.0f;
}

float PanSensor::readPanDeg() {
    float pan = _panDeg - _offsetDeg;
    if (pan < PAN_MIN_DEG) pan = PAN_MIN_DEG;
    if (pan > PAN_MAX_DEG) pan = PAN_MAX_DEG;
    return pan;
}

float PanSensor::minPanDeg() {
    return _peaks.hasData() ? _peaks.minValue() : readPanDeg();
}

float PanSensor::maxPanDeg() {
    return _peaks.hasData() ? _peaks.maxValue() : readPanDeg();
}

void PanSensor::calibrate() {
    _offsetDeg = _panDeg;

    // Extremos guardados são relativos ao zero antigo — ver o mesmo raciocínio
    // em AngleSensor::calibrate().
    _peaks.reset();

    // Refaz também a estimativa de bias: a calibração é feita com o eixo
    // parado na posição de referência, que é exatamente a condição ideal para
    // reestabelecer o zero do giroscópio. É o que recupera o caso de o ESP32
    // ter sido ligado com o eixo em movimento.
    _biasReady = false;
    resetWindow(millis());
}
