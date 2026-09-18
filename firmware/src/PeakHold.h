#pragma once

#include <stdint.h>

// Guarda os extremos (mínimo e máximo) de um sinal, com um teste de
// PERSISTÊNCIA opcional para não deixar o ruído virar extremo.
//
// POR QUE ISSO MORA NO FIRMWARE. Os apps só enxergam o ângulo a 4-5 Hz
// (polling do Modbus a 250 ms, notify BLE a 200 ms), enquanto o sensor é
// amostrado a 100 Hz. Calcular mín/máx no app significa perder o pico de
// qualquer evento curto — uma rajada de vento de meio segundo cai entre duas
// amostras. Medido em simulação da cadeia completa, uma rajada real de 2,0°
// com 0,5 s de duração chegava ao relatório como 0,78° (39% do pico). Com o
// peak-hold aqui, a 100 Hz, chega como 1,76° (88%).
//
// COMO O TESTE DE PERSISTÊNCIA FUNCIONA. Um extremo só é aceito se o sinal
// SE MANTEVE lá por `persistSamples` amostras seguidas. Na prática: o
// candidato a máximo é o MENOR valor da janela deslizante (se o menor já
// supera o máximo registrado, todos os outros também superam); o candidato a
// mínimo é o MAIOR. Ruído não se mantém — uma excursão isolada de uma amostra
// é descartada; um movimento real do mastro se mantém e passa.
//
// É esse teste que separa as duas necessidades. Sem ele, o filtro leve que
// alimenta este peak-hold (necessário para não achatar rajada) deixaria os
// extremos falsos irem a 0,34° com o eixo parado. Com 100 ms de persistência
// eles caem para 0,24° — abaixo de um passo de tela de 0,25° — sem custo
// relevante na captura da rajada (88% contra 88%).
//
// Com persistSamples = 1 vira um peak-hold simples, sem teste algum: é assim
// que o eixo de pan o usa, porque lá o sinal já não tem ruído de acelerômetro
// (o ZUPT cancela a integração enquanto parado) e a persistência só cortaria
// o ponto de retorno de uma varredura rápida do motor.
class PeakHold {
public:
    // Teto da janela de persistência. 16 amostras a 100 Hz = 160 ms, bem acima
    // do que faz sentido usar aqui; existe só para a janela ser um array fixo,
    // sem alocação dinâmica.
    static constexpr uint8_t MAX_PERSIST_SAMPLES = 16;

    explicit PeakHold(uint8_t persistSamples = 1);

    // Alimenta uma amostra nova. Chamar na cadência de amostragem do sensor
    // (100 Hz), não na cadência de leitura do protocolo.
    void push(float value);

    // Esquece os extremos e a janela. Chamado na calibração (o zero mudou,
    // então os extremos antigos perdem o sentido) e no reset explícito
    // disparado pelos apps.
    void reset();

    // false até a primeira janela completa — antes disso não há extremo
    // definido e quem lê deve usar a leitura corrente no lugar.
    bool hasData() const { return _hasData; }

    float minValue() const { return _minValue; }
    float maxValue() const { return _maxValue; }

private:
    uint8_t _persist;
    float _window[MAX_PERSIST_SAMPLES];
    uint8_t _head = 0;
    uint8_t _filled = 0;

    float _minValue = 0.0f;
    float _maxValue = 0.0f;
    bool _hasData = false;
};
