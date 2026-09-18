#include "PeakHold.h"

PeakHold::PeakHold(uint8_t persistSamples) {
    if (persistSamples < 1) {
        persistSamples = 1;
    } else if (persistSamples > MAX_PERSIST_SAMPLES) {
        persistSamples = MAX_PERSIST_SAMPLES;
    }
    _persist = persistSamples;
    for (uint8_t i = 0; i < MAX_PERSIST_SAMPLES; i++) {
        _window[i] = 0.0f;
    }
}

void PeakHold::push(float value) {
    _window[_head] = value;
    _head = static_cast<uint8_t>((_head + 1) % _persist);

    if (_filled < _persist) {
        _filled++;
        if (_filled < _persist) {
            return;  // janela ainda incompleta: não dá para testar persistência
        }
    }

    // Menor e maior da janela deslizante. Com _persist == 1 os dois são a
    // própria amostra, e o teste some (peak-hold simples).
    float lo = _window[0];
    float hi = _window[0];
    for (uint8_t i = 1; i < _persist; i++) {
        if (_window[i] < lo) lo = _window[i];
        if (_window[i] > hi) hi = _window[i];
    }

    if (!_hasData) {
        // Primeira janela completa define os dois extremos. Note o cruzamento:
        // o mínimo nasce do MAIOR da janela e o máximo do MENOR — é o mesmo
        // critério conservador aplicado abaixo, só que sem valor anterior com
        // que comparar.
        _minValue = hi;
        _maxValue = lo;
        _hasData = true;
        return;
    }

    // Novo máximo só se o MENOR da janela já o supera — ou seja, o sinal ficou
    // acima do máximo anterior durante toda a janela. Idem, espelhado, para o
    // mínimo.
    if (lo > _maxValue) _maxValue = lo;
    if (hi < _minValue) _minValue = hi;
}

void PeakHold::reset() {
    _head = 0;
    _filled = 0;
    _hasData = false;
    _minValue = 0.0f;
    _maxValue = 0.0f;
}
