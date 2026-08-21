#pragma once

#include <stdint.h>

#include "Mpu6050.h"

// Calcula o ângulo de azimute (pan) — a rotação em torno da vertical —
// integrando o GIROSCÓPIO do MPU6050, relativo a um zero calibrado.
//
// Por que não dá pelo acelerômetro: ele mede a direção do vetor gravidade, e
// girar em torno da vertical não muda esse vetor. É limitação física, não de
// código. O giroscópio, por outro lado, mede velocidade angular em torno de
// qualquer eixo — inclusive o vertical.
//
// São quatro mecanismos trabalhando juntos:
//
// 1. COMPENSAÇÃO DE TILT. O sensor está montado na parte que inclina, então o
//    eixo Z dele não aponta para a vertical: ele está inclinado do próprio
//    ângulo de tilt. Uma rotação de pan (velocidade angular ao longo da
//    vertical) se projeta nos eixos do corpo, e pegar gz cru subestimaria a
//    taxa por cos(tilt) — a 60° de tilt a leitura sairia pela metade. A taxa
//    correta é a projeção do vetor de velocidade angular medido sobre a
//    vertical escrita em coordenadas do corpo:
//
//        ω_pan = gz*cos(θ) - gy*sin(θ),   θ = atan2(ay, az)
//
//    Sendo uma projeção (produto escalar com um vetor unitário), e não a
//    fórmula de taxa de Euler (gy*sinφ + gz*cosφ)/cosθ, não há singularidade
//    em nenhum ângulo de tilt. E ela rejeita sozinha a taxa do próprio tilt,
//    que acontece em torno do eixo X e portanto não tem componente na
//    vertical. O accel e o giro vêm do mesmo burst I2C (Mpu6050::readMotion),
//    então θ e as taxas são do mesmo instante.
//
// 2. ZUPT (zero-rate update). Integrar giro acumula erro: um bias residual
//    vira uma rampa. Mas o drift só corre enquanto se integra — e o eixo de
//    pan aqui fica parado a maior parte do tempo. A cada
//    PAN_ZUPT_WINDOW_MS calcula-se a média de ω_pan; se ela estiver próxima
//    do bias corrente, a janela é considerada parada e o bias é atualizado em
//    direção a essa média. O gate usa a MÉDIA (e não a dispersão) de
//    propósito: vibração é de média zero, então o mastro pode estar
//    balançando sob vento que a janela ainda é reconhecida como parada.
//
// 3. CANCELAMENTO DE JANELA PARADA. Não basta parar de corrigir o bias — se a
//    integração continuasse rodando enquanto parado, o ruído do giro viraria
//    random walk no ângulo. Então o quanto foi integrado dentro da janela é
//    acumulado à parte e, se a janela fechar classificada como parada, é
//    subtraído de volta. Parado, o ângulo fica cravado. O preço é o piso de
//    detecção: um movimento cujo deslocamento total fique abaixo de
//    PAN_ZUPT_RATE_THRESHOLD_DPS * janela (~1°) é descartado como ruído.
//
// 4. FATOR DE ESCALA (PAN_SCALE_CORRECTION). Resolvido o bias, o erro
//    dominante passa a ser a tolerância de sensibilidade do giro (~±3% de
//    fábrica). Ele é proporcional ao deslocamento ATUAL em relação ao zero —
//    não se acumula com o tempo nem com o número de movimentos — e some
//    quando o eixo volta ao zero.
//
// PREMISSA DE BOOT: a primeira janela é aceita incondicionalmente e define o
// bias direto, porque o zero-rate de fábrica do MPU6050 chega a ±20°/s e
// nenhum limiar razoável o aceitaria. Ou seja, assume-se o sensor parado ao
// ligar. Se o ESP32 for ligado com o eixo em movimento, o bias inicial sai
// errado e o gate passa a rejeitar as janelas paradas seguintes — pressionar
// Calibrar com o eixo parado refaz a estimativa do zero (ver calibrate()).
class PanSensor {
public:
    explicit PanSensor(Mpu6050 &mpu) : _mpu(mpu) {}

    // Chamar a cada iteração do loop(): amostra o sensor em intervalo fixo
    // (ANGLE_SAMPLE_INTERVAL_MS, o mesmo do tilt), integra e mantém o ZUPT.
    void update();

    // Ângulo de pan relativo à calibração (graus), já clampado a
    // [PAN_MIN_DEG, PAN_MAX_DEG]. Não faz I2C: devolve o estado do
    // integrador mantido por update().
    float readPanDeg();

    // Zera o pan na posição atual e reinicia a estimativa de bias do giro —
    // a próxima janela vira a nova referência de "parado". Chamado junto com
    // AngleSensor::calibrate(), pela mesma ação de calibração dos apps.
    void calibrate();

    // true depois que a primeira janela estabeleceu o bias (até lá o ângulo
    // fica congelado em zero, ~1s após o boot).
    bool biasReady() const { return _biasReady; }

private:
    Mpu6050 &_mpu;

    float _panDeg = 0.0f;     // integrado desde o boot (absoluto, sem clamp)
    float _offsetDeg = 0.0f;  // zero da calibração
    float _biasDps = 0.0f;    // bias estimado do giro, em graus/s
    bool _biasReady = false;  // primeira janela já definiu o bias?

    uint32_t _lastSampleMs = 0;
    bool _hasLastSample = false;  // primeira amostra não tem dt confiável

    // Estado da janela de ZUPT em andamento.
    uint32_t _windowStartMs = 0;
    float _windowRateSumDps = 0.0f;
    uint16_t _windowSamples = 0;
    float _windowDeltaDeg = 0.0f;  // quanto foi integrado nesta janela

    // Fecha a janela corrente: decide se estava parada, atualiza o bias e
    // cancela a integração da janela em caso afirmativo.
    void closeWindow(uint32_t now);

    void resetWindow(uint32_t now);
};
