#include "VibrationCapture.h"

#include <Arduino.h>
#include <math.h>

bool VibrationCapture::start(uint16_t durationS, uint16_t rateHz) {
    if (_status == Status::Capturing) {
        return false;  // já em andamento
    }
    if (durationS == 0 || rateHz == 0) {
        _status = Status::Error;
        return false;
    }

    uint32_t requested = static_cast<uint32_t>(durationS) * rateHz;
    _totalSamples = static_cast<uint16_t>(
        requested > VIBRATION_MAX_SAMPLES ? VIBRATION_MAX_SAMPLES : requested
    );
    if (_totalSamples == 0) {
        _status = Status::Error;
        return false;
    }

    _sampleCount = 0;
    _progressPercent = 0;
    _intervalMs = 1000UL / rateHz;
    _lastSampleMs = millis();
    _status = Status::Capturing;
    return true;
}

void VibrationCapture::update() {
    if (_status != Status::Capturing) {
        return;
    }
    uint32_t now = millis();
    if (now - _lastSampleMs < _intervalMs) {
        return;
    }
    _lastSampleMs = now;

    float angleDeg = _sensor.readRelativeAngleDeg();
    _buffer[_sampleCount] = toInt16(angleDeg * ANGLE_SCALE);
    // Velocidade angular, não ângulo — ver o cabeçalho de VibrationCapture.h.
    _panBuffer[_sampleCount] = toInt16(_pan.readInstantRateDps() * PAN_RATE_SCALE);
    _sampleCount++;

    _progressPercent = static_cast<uint8_t>((static_cast<uint32_t>(_sampleCount) * 100) / _totalSamples);

    if (_sampleCount >= _totalSamples) {
        _status = Status::Ready;
        _progressPercent = 100;
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
