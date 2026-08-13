#include "AngleSensor.h"

#include <math.h>

#include "Config.h"

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

bool AngleSensor::begin() {
    return _mpu.begin();
}

float AngleSensor::readRawAngleDeg() {
    float ax, ay, az;
    if (!_mpu.readAccelG(ax, ay, az)) {
        return _offsetDeg;  // leitura falhou: mantém o último ângulo relativo em 0
    }
    return atan2(ay, az) * 180.0f / static_cast<float>(M_PI);
}

float AngleSensor::readRelativeAngleDeg() {
    return readRawAngleDeg() - _offsetDeg;
}

float AngleSensor::readAngleDeg() {
    float angle = readRelativeAngleDeg();
    if (angle < ANGLE_MIN_DEG) angle = ANGLE_MIN_DEG;
    if (angle > ANGLE_MAX_DEG) angle = ANGLE_MAX_DEG;
    return angle;
}

void AngleSensor::calibrate() {
    _offsetDeg = readRawAngleDeg();
}
