#include "PanSensor.h"

#include <Arduino.h>
#include <math.h>

#include "Config.h"

bool PanSensor::sampleMotion(float &gyDps, float &gzDps, float &tiltRad) {
    float ax, ay, az, gxDps;
    if (!_mpu.readMotion(ax, ay, az, gxDps, gyDps, gzDps)) {
        return false;
    }
    // Tilt do MESMO burst: sem defasagem entre o ângulo usado na projeção e
    // as taxas projetadas.
    tiltRad = atan2f(ay, az);
    return true;
}

float PanSensor::panRateDps(float gyDps, float gzDps, float tiltRad) const {
    // Projeção da velocidade angular sobre a vertical, escrita em coordenadas
    // do corpo (item 1 do cabeçalho de PanSensor.h), com o bias de cada eixo
    // removido ANTES de projetar (item 2).
    return (gzDps - _biasGzDps) * cosf(tiltRad) - (gyDps - _biasGyDps) * sinf(tiltRad);
}

float PanSensor::readInstantRateDps() {
    float gyDps, gzDps, tiltRad;
    if (!sampleMotion(gyDps, gzDps, tiltRad)) {
        return _lastRateDps;  // amostra perdida: repete a última válida
    }
    _lastRateDps = panRateDps(gyDps, gzDps, tiltRad) * PAN_SCALE_CORRECTION;
    return _lastRateDps;
}

namespace {
// Mediana de n <= 5 valores (média dos dois centrais se n for par).
float medianOf(const float *v, int n) {
    float s[5];
    for (int i = 0; i < n; i++) {
        float x = v[i];
        int j = i - 1;
        while (j >= 0 && s[j] > x) {
            s[j + 1] = s[j];
            j--;
        }
        s[j + 1] = x;
    }
    return (n % 2) ? s[n / 2] : 0.5f * (s[n / 2 - 1] + s[n / 2]);
}
}  // namespace

bool PanSensor::despike(float &gyDps, float &gzDps, float &tiltRad) {
    for (int i = 0; i < PAN_DESPIKE_LEN - 1; i++) {
        _gyHist[i] = _gyHist[i + 1];
        _gzHist[i] = _gzHist[i + 1];
        _tiltHist[i] = _tiltHist[i + 1];
    }
    _gyHist[PAN_DESPIKE_LEN - 1] = gyDps;
    _gzHist[PAN_DESPIKE_LEN - 1] = gzDps;
    _tiltHist[PAN_DESPIKE_LEN - 1] = tiltRad;
    if (_histCount < PAN_DESPIKE_LEN) {
        _histCount++;
    }
    // Só com o histórico cheio a mediana rejeita até 2 amostras ruins
    // seguidas (picos vêm em dupla); antes disso, melhor esperar.
    if (_histCount < PAN_DESPIKE_LEN) {
        return false;
    }
    int first = PAN_DESPIKE_LEN - _histCount;
    float gy = medianOf(_gyHist + first, _histCount);
    float gz = medianOf(_gzHist + first, _histCount);
    if (fabsf(gy - gyDps) > PAN_SPIKE_REPORT_DPS || fabsf(gz - gzDps) > PAN_SPIKE_REPORT_DPS) {
        _spikeCount++;
    }
    gyDps = gy;
    gzDps = gz;
    // O tilt da projeção vem do MESMO quadro; um quadro de lixo que passe
    // pelo teste de plausibilidade traz também um tilt errado.
    tiltRad = medianOf(_tiltHist + first, _histCount);
    return true;
}

void PanSensor::update() {
    uint32_t now = millis();
    if (_hasLastSample && now - _lastSampleMs < ANGLE_SAMPLE_INTERVAL_MS) {
        return;
    }
    if (_failedAttempt && now == _lastAttemptMs) {
        return;  // falhou neste mesmo ms: tenta de novo no próximo
    }

    float gyDps, gzDps, tiltRad;
    if (!sampleMotion(gyDps, gzDps, tiltRad)) {
        // O relógio da integração NÃO avança numa falha: o intervalo fica
        // para a próxima leitura boa, que o integra inteiro. Avançando aqui
        // (como até a 1.6.4), cada leitura perdida durante um giro jogava
        // fora 10 ms de rotação (0,2° a 20°/s) — em silêncio, a cada falha.
        _i2cFailures++;
        _failedAttempt = true;
        _lastAttemptMs = now;
        return;  // falha de I2C: preserva o estado em vez de corrompê-lo
    }
    _failedAttempt = false;
    uint32_t elapsedMs = now - _lastSampleMs;
    _lastSampleMs = now;
    _lastGyDps = gyDps;
    _lastGzDps = gzDps;
    _lastTiltRad = tiltRad;
    _sampleCount++;
    if (!_hasLastSample) {
        // Primeira amostra: sem intervalo anterior, não há dt para integrar.
        _hasLastSample = true;
        resetWindow(now);
        despike(gyDps, gzDps, tiltRad);
        return;
    }

    float dtS = elapsedMs / 1000.0f;
    if (dtS > PAN_MAX_INTEGRATION_DT_S) {
        dtS = PAN_MAX_INTEGRATION_DT_S;
    }

    // Depois de um buraco (loop atrasado, leituras perdidas), o histórico da
    // mediana é de ANTES dele: no fim de um giro, 4 amostras velhas a 20°/s
    // venciam a nova já parada e o buraco inteiro era integrado a 20°/s. Ele
    // é descartado, e o buraco só é integrado quando 5 amostras novas dão
    // uma mediana confiável — nunca com uma amostra isolada, que pode ser
    // justamente a espúria.
    if (elapsedMs > 3 * ANGLE_SAMPLE_INTERVAL_MS) {
        _histCount = 0;
    }
    if (!despike(gyDps, gzDps, tiltRad)) {
        _pendingDtS += dtS;
        return;
    }
    dtS += _pendingDtS;
    _pendingDtS = 0.0f;

    // Só integra depois que a primeira janela estabeleceu o bias: antes
    // disso, o zero-rate de fábrica (±20°/s) jogaria o ângulo longe.
    if (_biasReady && _sinceStillS < PAN_BIAS_EXTRAPOLATION_MAX_S) {
        // Deriva térmica do bias continua durante o movimento, quando não
        // há janela parada para corrigi-lo: segue a velocidade estimada.
        // Só por um tempo limitado — a estimativa envelhece.
        _biasGyDps += _biasSlopeGy * dtS;
        _biasGzDps += _biasSlopeGz * dtS;
        _sinceStillS += dtS;
    }

    if (_biasReady) {
        // Regra do trapézio: a taxa muda entre duas amostras (início e fim de
        // cada giro), e multiplicar só a taxa nova pelo intervalo inteiro
        // errava até uma amostra (~0,2° a 20°/s) por borda de movimento.
        float rate = panRateDps(gyDps, gzDps, tiltRad) * PAN_SCALE_CORRECTION;
        float prevRate = _hasPrevIntegRate ? _prevIntegRateDps : rate;
        _prevIntegRateDps = rate;
        _hasPrevIntegRate = true;
        float before = _panDeg;
        _panDeg += 0.5f * (prevRate + rate) * dtS;
        clampIntegrator();
        // O que foi EFETIVAMENTE aplicado (após o clamp), para o cancelamento
        // da janela desfazer exatamente isso.
        _windowDeltaDeg += _panDeg - before;
    }

    _windowGySumDps += gyDps;
    _windowGzSumDps += gzDps;
    _windowSamples++;
    if (_biasReady) {
        float peak = hypotf(gyDps - _biasGyDps, gzDps - _biasGzDps);
        if (peak > _windowPeakDps) {
            _windowPeakDps = peak;
        }
    }

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

    float meanGyDps = _windowGySumDps / _windowSamples;
    float meanGzDps = _windowGzSumDps / _windowSamples;

    // Coerente com a janela anterior = mesma taxa média nas duas: ou o eixo
    // está parado, ou girando a velocidade constante. Ver "BOOT E
    // RECUPERAÇÃO" em PanSensor.h.
    bool coherent = _hasPrevMean &&
        hypotf(meanGyDps - _prevMeanGyDps, meanGzDps - _prevMeanGzDps) < PAN_ZUPT_RATE_THRESHOLD_DPS;
    _prevMeanGyDps = meanGyDps;
    _prevMeanGzDps = meanGzDps;
    _hasPrevMean = true;

    if (!_biasReady) {
        if (coherent) {
            adoptBias(meanGyDps, meanGzDps);
        }
    } else {
        // A média da janela corresponde ao bias do MEIO da janela; o bias
        // corrente já foi extrapolado até o fim dela.
        float winS = (now - _windowStartMs) / 1000.0f;
        float dGy = meanGyDps - (_biasGyDps - _biasSlopeGy * 0.5f * winS);
        float dGz = meanGzDps - (_biasGzDps - _biasSlopeGz * 0.5f * winS);
        if (hypotf(dGy, dGz) < PAN_ZUPT_RATE_THRESHOLD_DPS && _windowPeakDps < PAN_ZUPT_PEAK_DPS) {
            // Janela parada: refina o bias (filtro alfa-beta: nível e
            // velocidade de deriva) e desfaz o que foi integrado nela, para o
            // ruído do giro não virar random walk enquanto parado.
            _biasGyDps += PAN_ZUPT_BIAS_ALPHA * dGy;
            _biasGzDps += PAN_ZUPT_BIAS_ALPHA * dGz;
            if (winS > 0.0f) {
                _biasSlopeGy = clampSlope(_biasSlopeGy + PAN_ZUPT_SLOPE_BETA * dGy / winS);
                _biasSlopeGz = clampSlope(_biasSlopeGz + PAN_ZUPT_SLOPE_BETA * dGz / winS);
            }
            _sinceStillS = 0.0f;
            _panDeg -= _windowDeltaDeg;
            clampIntegrator();
            _mismatchWindows = 0;
            _mismatchDeltaDeg = 0.0f;
        } else {
            if (coherent && _mismatchWindows > 0) {
                _mismatchWindows++;
                _mismatchDeltaDeg += _windowDeltaDeg;
            } else {
                _mismatchWindows = 1;
                _mismatchDeltaDeg = _windowDeltaDeg;
            }
            if (_mismatchWindows >= PAN_BIAS_RELEARN_WINDOWS) {
                // Parado sob bias errado: reaprende e desfaz a deriva da
                // sequência inteira.
                _panDeg -= _mismatchDeltaDeg;
                clampIntegrator();
                adoptBias(meanGyDps, meanGzDps);
            }
        }
    }

    resetWindow(now);
}

float PanSensor::clampSlope(float slope) {
    if (slope > PAN_BIAS_SLOPE_MAX_DPS2) return PAN_BIAS_SLOPE_MAX_DPS2;
    if (slope < -PAN_BIAS_SLOPE_MAX_DPS2) return -PAN_BIAS_SLOPE_MAX_DPS2;
    return slope;
}

void PanSensor::clampIntegrator() {
    // Anti-windup: o integrador nunca passa da faixa mecânica. Sem isto, um
    // erro qualquer que o empurrasse para além de ±PAN_MAX_DEG (leitura
    // espúria, bias errado, a placa girada à mão além do curso) deixava a
    // leitura presa no limite: girar de volta só descontava do excesso, e o
    // valor mostrado não saía do lugar — "travado". Com o clamp, a volta
    // responde na hora.
    float lo = _offsetDeg + PAN_MIN_DEG;
    float hi = _offsetDeg + PAN_MAX_DEG;
    if (_panDeg < lo) _panDeg = lo;
    if (_panDeg > hi) _panDeg = hi;
}

void PanSensor::adoptBias(float gyDps, float gzDps) {
    _biasGyDps = gyDps;
    _biasGzDps = gzDps;
    _biasReady = true;
    _hasPrevIntegRate = false;
    _biasSlopeGy = 0.0f;
    _biasSlopeGz = 0.0f;
    _sinceStillS = 0.0f;
    _mismatchWindows = 0;
    _mismatchDeltaDeg = 0.0f;
}

void PanSensor::resetWindow(uint32_t now) {
    _windowStartMs = now;
    _windowGySumDps = 0.0f;
    _windowGzSumDps = 0.0f;
    _windowSamples = 0;
    _windowDeltaDeg = 0.0f;
    _windowPeakDps = 0.0f;
}

float PanSensor::readPanDeg() {
    float pan = _panDeg - _offsetDeg;
    if (pan < PAN_MIN_DEG) pan = PAN_MIN_DEG;
    if (pan > PAN_MAX_DEG) pan = PAN_MAX_DEG;
    return pan;
}

PanSensor::Diagnostics PanSensor::diagnostics() const {
    return Diagnostics{
        _panDeg, _offsetDeg, _biasGyDps, _biasGzDps, _prevMeanGyDps, _prevMeanGzDps,
        _lastGyDps, _lastGzDps, _lastTiltRad * 57.29578f, _sampleCount, _i2cFailures,
        _mismatchWindows, static_cast<uint8_t>(_biasReady ? 1 : 0), _spikeCount,
        _mpu.recoveries(),
    };
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
    _hasPrevMean = false;
    _mismatchWindows = 0;
    _mismatchDeltaDeg = 0.0f;
    resetWindow(millis());
}
