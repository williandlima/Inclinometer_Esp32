#pragma once

#include "Mpu6050.h"

// Calcula o ângulo de inclinação (tilt) a partir do acelerômetro do
// MPU6050, usando atan2 entre dois eixos para manter sensibilidade
// praticamente uniforme em toda a faixa -60° a +60° — evita a região de baixa
// sensibilidade que a leitura de um único eixo teria perto de 90°
// (ver docs/fluxograma-python-app.md e a discussão do ensaio de vibração).
//
// Eixos e sinal usados aqui (Y, Z) são um ponto de partida — a
// confirmar/ajustar conforme a orientação real de montagem do sensor no
// pan-tilt, quando o projeto elétrico definir isso.
class AngleSensor {
public:
    bool begin();

    // Ângulo relativo à calibração (graus), já clampado a
    // [ANGLE_MIN_DEG, ANGLE_MAX_DEG] — usado na leitura "normal".
    float readAngleDeg();

    // Igual a readAngleDeg(), mas sem clamp de faixa — usado na captura de
    // vibração, onde a variação em torno do zero pode ser negativa.
    float readRelativeAngleDeg();

    // Zera o offset de calibração na leitura atual (novo "zero" mecânico).
    void calibrate();

private:
    Mpu6050 _mpu;
    float _offsetDeg = 0.0f;

    float readRawAngleDeg();
};
