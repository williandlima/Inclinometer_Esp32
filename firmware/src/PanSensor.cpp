#include "PanSensor.h"

#include <Arduino.h>
#include <math.h>

#include "Config.h"

bool PanSensor::sampleRateDps(float &rateDps) {
    float ax, ay, az, gxDps, gyDps, gzDps;
    if (!_mpu.readMotion(ax, ay, az, gxDps, gyDps, gzDps)) {
        return false;
    }

    // Projeção da velocidade angular medida sobre a vertical, escrita em
    // coordenadas do corpo — ver o item 1 do cabeçalho de PanSensor.h. O
    // ângulo de tilt vem do MESMO burst, então não há defasagem entre o
    // ângulo usado na projeção e as taxas projetadas.
    float tiltRad = atan2f(ay, az);
    rateDps = gzDps * cosf(tiltRad) - gyDps * sinf(tiltRad);
    _lastRateDps = rateDps;
    return true;
}

float PanSensor::readInstantRateDps() {
    float rateDps;
    if (!sampleRateDps(rateDps)) {
        rateDps = _lastRateDps;  // amostra perdida: repete a última válida
    }
    return (rateDps - _biasDps) * PAN_SCALE_CORRECTION;
}

void PanSensor::update() {
    uint32_t now = millis();
    if (_hasLastSample && now - _lastSampleMs < ANGLE_SAMPLE_INTERVAL_MS) {
        return;
    }
    uint32_t elapsedMs = now - _lastSampleMs;
    _lastSampleMs = now;

    float panRateDps;
    if (!sampleRateDps(panRateDps)) {
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
        float deltaDeg = (panRateDps - _biasDps) * dtS * PAN_SCALE_CORRECTION;
        _panDeg += deltaDeg;
        _windowDeltaDeg += deltaDeg;
    }

    _windowRateSumDps += panRateDps;
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

    float meanDps = _windowRateSumDps / _windowSamples;

    if (!_biasReady) {
        // Primeira janela desde o boot (ou desde a última calibração): adota
        // a média como bias, sem aplicar limiar. Ver "PREMISSA DE BOOT" em
        // PanSensor.h — o zero-rate de fábrica é grande demais para passar
        // por qualquer limiar razoável.
        _biasDps = meanDps;
        _biasReady = true;
    } else if (fabsf(meanDps - _biasDps) < PAN_ZUPT_RATE_THRESHOLD_DPS) {
        // Janela parada: refina o bias e desfaz o que foi integrado nela, para
        // o ruído do giro não virar random walk enquanto o eixo está parado.
        _biasDps += PAN_ZUPT_BIAS_ALPHA * (meanDps - _biasDps);
        _panDeg -= _windowDeltaDeg;
    }

    resetWindow(now);
}

void PanSensor::resetWindow(uint32_t now) {
    _windowStartMs = now;
    _windowRateSumDps = 0.0f;
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
