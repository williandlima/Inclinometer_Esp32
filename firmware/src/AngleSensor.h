#pragma once

#include <stdint.h>

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
//
// Há DOIS caminhos de leitura, de propósito:
// - readAngleDeg(): filtrado (filtro adaptativo "1-euro" alimentado por
//   update(); ver ANGLE_FILTER_* em Config.h), para a leitura contínua do dia
//   a dia ficar estável sem ficar lenta;
// - readRelativeAngleDeg(): amostra instantânea, sem filtro, para o Modo
//   Vibração — ali a variação de frações de grau é justamente o que se quer
//   medir, então filtrar destruiria o dado.
class AngleSensor {
public:
    // O Mpu6050 é compartilhado (por referência) com o PanSensor: é o mesmo
    // chip físico, então quem o inicializa é o main(), uma vez só.
    explicit AngleSensor(Mpu6050 &mpu) : _mpu(mpu) {}

    // Chamar a cada iteração do loop(): amostra o sensor em intervalo fixo
    // (ANGLE_SAMPLE_INTERVAL_MS) e alimenta o filtro da leitura contínua.
    void update();

    // Ângulo filtrado, relativo à calibração (graus), já clampado a
    // [ANGLE_MIN_DEG, ANGLE_MAX_DEG] — usado na leitura "normal". Não faz
    // I2C: devolve o estado do filtro mantido por update().
    float readAngleDeg();

    // Amostra instantânea (uma leitura I2C na hora), relativa à calibração,
    // sem filtro nem clamp de faixa — usada na captura de vibração, onde a
    // variação em torno do zero pode ser negativa e a sensibilidade é o
    // objetivo.
    float readRelativeAngleDeg();

    // Zera o offset de calibração na leitura atual (novo "zero" mecânico).
    // Usa o valor filtrado, não uma amostra isolada, para a calibração ser
    // repetível mesmo com o sensor sob vibração.
    void calibrate();

private:
    Mpu6050 &_mpu;
    float _offsetDeg = 0.0f;

    // Estado do filtro 1-euro (todos em ângulo absoluto, antes do offset):
    float _filteredRawDeg = 0.0f;   // saída do filtro
    float _filteredRateDps = 0.0f;  // derivada suavizada, que comanda o corte
    float _prevRawDeg = 0.0f;       // amostra anterior, para calcular a derivada
    float _lastRawDeg = 0.0f;       // última amostra válida (absoluta)
    bool _filterReady = false;      // primeira amostra inicializa o filtro direto
    uint32_t _lastSampleMs = 0;

    // Lê uma amostra e converte para ângulo absoluto. Retorna false se a
    // leitura I2C falhar (sensor desconectado, mau contato).
    bool readRawAngleDeg(float &angleDeg);

    // Coeficiente de uma média móvel exponencial de 1 polo para a frequência
    // de corte e o intervalo dados.
    static float emaAlpha(float cutoffHz, float dtS);
};
