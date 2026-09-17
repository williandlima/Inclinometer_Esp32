#include "VibrationCapture.h"

#include <Arduino.h>
#include <math.h>

void VibrationCapture::requestStart(uint16_t durationS, uint16_t rateHz) {
    _pendingDurationS = durationS;
    _pendingRateHz = rateHz;
    _startPending = true;
}

bool VibrationCapture::start(uint16_t durationS, uint16_t rateHz) {
    if (_status == Status::Capturing) {
        return false;  // já em andamento
    }
    if (durationS == 0 || rateHz == 0) {
        _status = Status::Error;
        return false;
    }
    if (rateHz > VIBRATION_MAX_RATE_HZ) {
        rateHz = VIBRATION_MAX_RATE_HZ;
    }

    uint32_t requested = static_cast<uint32_t>(durationS) * rateHz;
    _totalSamples = static_cast<uint16_t>(
        requested > VIBRATION_MAX_SAMPLES ? VIBRATION_MAX_SAMPLES : requested
    );
    if (_totalSamples == 0) {
        _status = Status::Error;
        return false;
    }

    // Abre a banda do filtro interno do sensor conforme a taxa pedida: em
    // taxa alta, manter os 21Hz da leitura contínua apagaria justamente o
    // que a taxa alta foi feita para medir (ver Mpu6050::setDlpfForSampleRate).
    _mpu.setDlpfForSampleRate(rateHz);

    _sampleCount = 0;
    _progressPercent = 0;
    _intervalUs = 1000000UL / rateHz;
    _lastSampleUs = micros();
    _status = Status::Capturing;
    return true;
}

void VibrationCapture::update() {
    if (_startPending) {
        _startPending = false;
        start(_pendingDurationS, _pendingRateHz);
    }
    if (_status != Status::Capturing) {
        return;
    }
    uint32_t now = micros();
    if (now - _lastSampleUs < _intervalUs) {
        return;
    }
    // Avança o instante-alvo pelo período exato, em vez de zerar a partir de
    // "agora": zerando, todo atraso de uma amostra se somava ao das
    // seguintes e a taxa real ficava sistematicamente abaixo da pedida —
    // exatamente o tipo de desvio que desloca o espectro inteiro. Se o
    // atraso for grande a ponto de já ter passado mais de um período (loop
    // ocupado), reancora em "agora" para não entrar numa rajada de amostras
    // tentando recuperar o atraso.
    if (now - _lastSampleUs > 2 * _intervalUs) {
        _lastSampleUs = now;
    } else {
        _lastSampleUs += _intervalUs;
    }

    float angleDeg = _sensor.readRelativeAngleDeg();
    _buffer[_sampleCount] = toInt16(angleDeg * ANGLE_SCALE);
    // Velocidade angular, não ângulo — ver o cabeçalho de VibrationCapture.h.
    _panBuffer[_sampleCount] = toInt16(_pan.readInstantRateDps() * PAN_RATE_SCALE);
    _sampleCount++;

    _progressPercent = static_cast<uint8_t>((static_cast<uint32_t>(_sampleCount) * 100) / _totalSamples);

    if (_sampleCount >= _totalSamples) {
        _status = Status::Ready;
        _progressPercent = 100;
        // Devolve a banda estreita para a leitura contínua, que precisa de
        // estabilidade e não de banda.
        _mpu.restoreDefaultDlpf();
    }
}

int16_t VibrationCapture::toInt16(float scaledValue) {
    long raw = lroundf(scaledValue);
    if (raw > 32767) raw = 32767;
    if (raw < -32768) raw = -32768;
    return static_cast<int16_t>(raw);
}

int16_t VibrationCapture::sampleAt(uint16_t index) const {
    if (index >= _sampleCount) {
        return 0;
    }
    return _buffer[index];
}

int16_t VibrationCapture::panSampleAt(uint16_t index) const {
    if (index >= _sampleCount) {
        return 0;
    }
    return _panBuffer[index];
}
