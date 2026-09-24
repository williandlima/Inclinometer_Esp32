#pragma once

#include <stdint.h>

#include "Mpu6050.h"
#include "PeakHold.h"

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
//    PAN_ZUPT_WINDOW_MS calcula-se a média de gy e gz; se ela estiver
//    próxima do bias corrente, a janela é considerada parada e o bias é
//    atualizado em direção a essa média. O gate usa a MÉDIA (e não a
//    dispersão) de propósito: vibração é de média zero, então o mastro pode
//    estar balançando sob vento que a janela ainda é reconhecida como parada.
//
//    O bias é estimado POR EIXO, no referencial do sensor (gy, gz), e só
//    depois projetado na vertical — nunca sobre ω_pan já projetado. O bias
//    de fábrica é fixo nos eixos do chip; projetado, ele vale
//    bgz·cos(θ) − bgy·sin(θ) e portanto MUDA com o tilt. Estimado sobre
//    ω_pan, qualquer mudança de inclinação deixava o bias aprendido errado
//    por alguns °/s, o gate passava a rejeitar toda janela parada (o bias
//    nunca mais se corrigia) e esse erro era integrado sem fim até cravar a
//    leitura em ±PAN_MAX_DEG — medido em simulação: 45° de tilt com bias de
//    fábrica típico dava ~1,4°/s de deriva, travando em -90° em ~60 s.
//    A distância usada no gate, hypot(Δgy, Δgz), vale exatamente |ω_pan|
//    para uma rotação de pan em qualquer tilt, então o limiar mantém o
//    significado de "°/s de pan". Rotação de tilt (eixo X) não aparece em
//    gy/gz e não tira a janela da condição de parada.
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
// BOOT E RECUPERAÇÃO. O bias inicial não pode passar pelo gate do item 2,
// porque o zero-rate de fábrica do MPU6050 chega a ±20°/s. Ele é adotado
// quando DUAS janelas seguidas têm médias coerentes entre si (distância
// abaixo de PAN_ZUPT_RATE_THRESHOLD_DPS): placa manuseada ao ligar tem média
// variando de janela a janela e é recusada; vibração, de média zero, não
// atrapalha. Até lá o ângulo fica congelado (~2 s após o boot/calibração).
//
// Antes (≤1.6.1) a PRIMEIRA janela era aceita sem teste. Ligada em
// movimento (típico no uso via BLE, com a placa na mão; via USB o app
// reinicia o ESP32 ao abrir a porta, com a placa parada na bancada), o bias
// saía errado, o gate recusava toda janela parada dali em diante e a
// leitura derivava até cravar em ±PAN_MAX_DEG para sempre.
//
// Rede de segurança para o caso raro de o bias ainda sair errado (ex.: giro
// lento e constante bem na hora do boot): PAN_BIAS_RELEARN_WINDOWS janelas
// seguidas, coerentes entre si mas todas longe do bias, só podem ser o eixo
// parado sob um bias errado — nenhuma varredura do motor dura tanto a
// velocidade constante dentro do curso. Nesse caso o bias é reaprendido e
// o que foi integrado nessas janelas é desfeito.
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

    // Extremos do pan acumulados desde o último reset/calibração, medidos a
    // 100 Hz (ver PeakHold.h). Aqui o peak-hold é SIMPLES, sem filtro extra e
    // sem teste de persistência, ao contrário do tilt — e por dois motivos:
    //
    // - não há ruído a filtrar. O ângulo de pan não vem do acelerômetro, vem
    //   de uma integração cujo mecanismo de cancelamento de janela parada
    //   (item 3 do cabeçalho acima) já deixa o valor cravado com o eixo
    //   parado. Filtrar de novo só adicionaria atraso;
    // - persistência aqui custaria caro. O motor gira a ~20-30°/s, então
    //   100 ms de exigência de persistência cortariam 2-3° do ponto de
    //   retorno de cada varredura — justamente o extremo que se quer registrar.
    //
    // O que o peak-hold resolve no pan é o outro problema: a 4-5 Hz de
    // polling, uma varredura rápida do motor passa pelo extremo entre duas
    // leituras do app e some.
    //
    // Efeito de borda conhecido: um movimento pequeno o bastante para a janela
    // ainda ser classificada como parada (< ~1°, ver item 3) é cancelado no
    // ângulo mas fica registrado no extremo, porque o peak-hold já o viu
    // acontecer. O extremo é o valor honesto dos dois — o movimento existiu.
    bool hasPeaks() const { return _peaks.hasData(); }
    float minPanDeg();
    float maxPanDeg();

    // Esquece os extremos sem mexer no zero — o botão de reset dos apps.
    void resetPeaks() { _peaks.reset(); }

    // Zera o pan na posição atual e reinicia a estimativa de bias do giro —
    // a próxima janela vira a nova referência de "parado". Chamado junto com
    // AngleSensor::calibrate(), pela mesma ação de calibração dos apps.
    void calibrate();

    // true depois que duas janelas coerentes estabeleceram o bias (até lá o
    // ângulo fica congelado, ~2 s após o boot).
    bool biasReady() const { return _biasReady; }

    // Velocidade angular instantânea do eixo de pan, em graus/s, já
    // compensada por tilt, com o bias estimado subtraído e o fator de escala
    // aplicado. Faz uma leitura I2C na hora.
    //
    // É ESTA a grandeza usada pelo Modo Vibração do pan — e não o ângulo
    // integrado de readPanDeg(). O motivo é o mecanismo 3 do cabeçalho
    // acima: um ensaio de vibração acontece justamente com o eixo parado,
    // então o cancelamento de janela parada apagaria de propósito toda a
    // oscilação que se quer medir. A taxa não passa por integração nem por
    // cancelamento, e ainda deixa o bias residual concentrado em 0 Hz, onde
    // a análise espectral já o descarta por construção.
    float readInstantRateDps();

private:
    Mpu6050 &_mpu;

    float _panDeg = 0.0f;     // integrado desde o boot (absoluto, sem clamp)
    float _offsetDeg = 0.0f;  // zero da calibração
    // Bias estimado de cada eixo do giro, no referencial do sensor (°/s) —
    // ver item 2 do cabeçalho: não pode ser estimado sobre ω_pan projetado.
    float _biasGyDps = 0.0f;
    float _biasGzDps = 0.0f;
    bool _biasReady = false;  // primeira janela já definiu o bias?

    uint32_t _lastSampleMs = 0;
    bool _hasLastSample = false;  // primeira amostra não tem dt confiável
    float _lastRateDps = 0.0f;    // última taxa válida (repetida em falha de I2C)

    // Estado da janela de ZUPT em andamento.
    uint32_t _windowStartMs = 0;
    float _windowGySumDps = 0.0f;
    float _windowGzSumDps = 0.0f;
    uint16_t _windowSamples = 0;
    float _windowDeltaDeg = 0.0f;  // quanto foi integrado nesta janela

    // Média da janela anterior, para o teste de coerência (BOOT E RECUPERAÇÃO).
    bool _hasPrevMean = false;
    float _prevMeanGyDps = 0.0f;
    float _prevMeanGzDps = 0.0f;

    // Sequência corrente de janelas coerentes entre si mas longe do bias.
    uint16_t _mismatchWindows = 0;
    float _mismatchDeltaDeg = 0.0f;  // integrado ao longo dessa sequência

    PeakHold _peaks{1};  // sem teste de persistência — ver minPanDeg() acima

    // Fecha a janela corrente: decide se estava parada, atualiza o bias e
    // cancela a integração da janela em caso afirmativo.
    void closeWindow(uint32_t now);

    void resetWindow(uint32_t now);

    void adoptBias(float gyDps, float gzDps);

    // Lê o sensor: gy/gz crus (°/s, sem bias subtraído) e o tilt do mesmo
    // burst (rad). false em falha de I2C.
    bool sampleMotion(float &gyDps, float &gzDps, float &tiltRad);

    // Taxa de pan (°/s): bias de cada eixo subtraído no referencial do
    // sensor e só então projetado na vertical (item 1 do cabeçalho).
    float panRateDps(float gyDps, float gzDps, float tiltRad) const;
};
