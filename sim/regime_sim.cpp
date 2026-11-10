// Os dois regimes de uso — PARADO POR MUITO TEMPO e EM MOVIMENTO CONSTANTE —
// nos dois eixos ao mesmo tempo, com AngleSensor (tilt, fusão) e PanSensor
// REAIS sobre um MPU6050 falso: bias de fábrica, aquecimento do giro (o zero
// anda 0,3 °/s em ~10 min), passeio aleatório do zero, ruído e 3% de erro de
// escala. Mede o erro contra a verdade ao longo de todo o ensaio. Ver run.sh.
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <random>
#include "Arduino.h"
#include "Config.h"
#include "Mpu6050.h"
#include "AngleSensor.h"
#include "PanSensor.h"

uint64_t g_now_us = 0;
HardwareSerial Serial;

static double g_tilt = 0, g_tiltRate = 0, g_panRate = 0;  // verdade (°, °/s; pan + = horário visto de cima)
static double g_warmDps = 0.3, g_warmTauS = 600, g_walkDps = 0.002, g_walk[3] = {0, 0, 0};
static const double BG[3] = {1.5, 3.0, -2.0};
static std::mt19937 rng(5);
static std::normal_distribution<double> nz(0.0, 1.0);
static double g_n[6]; static uint64_t g_nAt = ~0ull;
static void noise() { if (g_nAt == g_now_us) return; g_nAt = g_now_us; for (double &v : g_n) v = nz(rng); }
static double seenTilt() { return g_tilt / (g_tilt >= 0 ? TILT_SCALE_CORRECTION_POS : TILT_SCALE_CORRECTION_NEG); }

bool Mpu6050::begin() { return true; }
bool Mpu6050::readAccelG(float &ax, float &ay, float &az) {
    noise();
    const double t = seenTilt() * M_PI / 180;
    ax = 0.0023 * g_n[0]; ay = sin(t) + 0.0023 * g_n[1]; az = cos(t) + 0.0023 * g_n[2];
    return true;
}
bool Mpu6050::readMotion(float &ax, float &ay, float &az, float &gx, float &gy, float &gz) {
    readAccelG(ax, ay, az);
    const double t = seenTilt() * M_PI / 180, ts = g_now_us / 1e6;
    const double warm = g_warmDps * (1 - exp(-ts / g_warmTauS));
    // Giro com a escala que o firmware supõe (PAN_SCALE_CORRECTION, PAN_SCALE_ASYM).
    const double ccw = -g_panRate / (PAN_SCALE_CORRECTION * (1.0 + (g_panRate >= 0 ? PAN_SCALE_ASYM : -PAN_SCALE_ASYM)));
    gx = 0.97 * g_tiltRate + BG[0] + g_walk[0] + 0.5 * warm + 0.05 * g_n[3];
    gy = ccw * sin(t) + BG[1] + g_walk[1] + 0.05 * g_n[4];
    gz = ccw * cos(t) + BG[2] + g_walk[2] + warm + 0.05 * g_n[5];
    return true;
}
bool Mpu6050::setDlpfForSampleRate(uint16_t) { return true; }
bool Mpu6050::restoreDefaultDlpf() { return true; }
bool Mpu6050::writeRegister(uint8_t, uint8_t) { return true; }

static int failures = 0;
struct Result { double panWorst, panFinal, tiltWorst, tiltFinal, accWorst, fusedPct; };

// Onda triangular: vai de -amp a +amp a `rate` °/s e fica `dwell` s parado em
// cada ponta. Devolve posição e velocidade no instante t (começa em 0, subindo).
static void triangle(double t, double amp, double rate, double dwell, double &pos, double &vel) {
    if (amp <= 0 || rate <= 0) { pos = vel = 0; return; }
    const double leg = 2 * amp / rate, period = 2 * (leg + dwell);
    double x = fmod(t + leg / 2, period);  // desloca para começar no centro
    if (x < leg) { pos = -amp + rate * x; vel = rate; }
    else if (x < leg + dwell) { pos = amp; vel = 0; }
    else if (x < 2 * leg + dwell) { pos = amp - rate * (x - leg - dwell); vel = -rate; }
    else { pos = -amp; vel = 0; }
}

// 15 s parado para o zero do giro (como ao ligar), calibra, e roda `minutes`.
static Result run(const char *name, double minutes, double panAmp, double panRate, double tiltAmp, double tiltRate, double dwell) {
    Mpu6050 mpu; PanSensor pan(mpu); AngleSensor tilt(mpu), acc(mpu); tilt.attachGyro(&pan); long nAct = 0, nTot = 0;
    g_now_us = 0; g_nAt = ~0ull; rng.seed(5); g_walk[0] = g_walk[1] = g_walk[2] = 0;
    g_tilt = 0; g_tiltRate = g_panRate = 0;
    Result r{0, 0, 0, 0, 0, 0};
    double panTruth = 0, pan0 = 0;
    const uint32_t settle = 15000, end = settle + (uint32_t)(minutes * 60000);
    for (uint32_t ms = 0; ms <= end; ms++) {
        g_now_us = (uint64_t)ms * 1000;
        if (ms >= settle) {
            const double t = (ms - settle) / 1000.0;
            double p, v; triangle(t, panAmp, panRate, dwell, p, v); panTruth = p; g_panRate = v;
            triangle(t * 1.37, tiltAmp, tiltRate / 1.37, dwell / 1.37, g_tilt, v); g_tiltRate = v * 1.37;
        }
        for (double &w : g_walk) w += g_walkDps * sqrt(0.001) * nz(rng);
        tilt.update(); acc.update(); pan.update();
        if (ms == settle) { tilt.calibrate(); acc.calibrate(); pan0 = pan.readPanDeg(); }
        if (ms > settle + 2000) {
            const double pe = pan.readPanDeg() - pan0 - panTruth, te = tilt.readAngleDeg() - g_tilt;
            r.panWorst = std::max(r.panWorst, fabs(pe)); r.tiltWorst = std::max(r.tiltWorst, fabs(te));
            r.panFinal = pe; r.tiltFinal = te; r.accWorst = std::max(r.accWorst, fabs(acc.readAngleDeg() - g_tilt)); nTot++; nAct += tilt.fusionActive();
        }
    }
    r.fusedPct = nTot ? 100.0 * nAct / nTot : 0;
    printf("  %-50s pan: pior %5.2f° final %+6.2f° | tilt: pior %4.2f° final %+5.2f° (só acel.: pior %4.2f°; fusão ativa %3.0f%%)\n", name, r.panWorst, r.panFinal, r.tiltWorst, r.tiltFinal, r.accWorst, r.fusedPct);
    return r;
}
static void check(const char *what, bool ok) { if (!ok) { printf("  FALHOU: %s\n", what); failures++; } }

int main() {
    printf("=== regimes de uso: parado por muito tempo x movimento constante ===\n");
    Result all[6];
    all[0] = run("A. parado 2 h (giro aquecendo)", 120, 0, 0, 0, 0, 0);
    check("A: parado 2 h, pan não deriva (< 0,3°)", all[0].panWorst < 0.3);
    check("A: parado 2 h, tilt estável (< 0,1°)", all[0].tiltWorst < 0.1);
    all[1] = run("B. 30 min varrendo, 5 s parado em cada ponta", 30, 60, 10, 20, 5, 5);
    all[2] = run("C. 30 min varrendo, 3 s parado em cada ponta", 30, 60, 10, 20, 5, 3);
    all[3] = run("D. 30 min varrendo SEM parar nunca", 30, 60, 10, 20, 5, 0);
    all[4] = run("E. 30 min: só o tilt varre sem parar", 30, 0, 0, 20, 5, 0);
    all[5] = run("F. 30 min: só o pan varre sem parar", 30, 60, 10, 0, 0, 0);
    // TILT: tem a gravidade como referência o tempo todo — não pode depender
    // de parar, e a fusão não pode ficar pior que o acelerômetro sozinho (o
    // que sobra em movimento é o atraso do filtro da tela, igual nos dois).
    for (const Result &r : all) {
        check("tilt fundido nunca pior que o acelerômetro sozinho (+0,15°)", r.tiltWorst < r.accWorst + 0.15);
        check("fusão ativa o tempo todo", r.fusedPct > 99.0);
    }
    // PAN: integrado do giroscópio, sem referência absoluta. Parado não
    // deriva (A); em movimento, o zero do giro só é corrigido nas paradas. Os
    // números de B a F são o LIMITE CONHECIDO do método (ver firmware/README.md)
    // e ficam aqui para uma mudança que os piore aparecer.
    check("B: paradas de 5 s seguram o pan (< 3°)", all[1].panWorst < 3.0);
    printf(failures ? "REGIMES: HOUVE FALHA\n" : "REGIMES: TUDO OK\n");
    return failures ? 1 : 0;
}
