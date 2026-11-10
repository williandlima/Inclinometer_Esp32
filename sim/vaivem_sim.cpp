// Pan: vaivém rápido de ±30° com paradas curtas e volta ao zero (bancada de
// 10/11/2026: ~2,7° de erro na volta ao zero com a 1.6.25). PanSensor REAL;
// o giro tem a escala por sentido que o firmware supõe (PAN_SCALE_CORRECTION
// e PAN_SCALE_ASYM): o teste confere que nada mais acumula na volta. Ver run.sh.
#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <random>
#include "Arduino.h"
#include "Config.h"
#include "Mpu6050.h"
#include "PanSensor.h"
uint64_t g_now_us = 0; HardwareSerial Serial;
static double g_panRate = 0, WARM = 0.02, SCALE_ERR = 0, RING = 0;
static double ringT0 = -1e9, ringSign = 0;
static const double BG[3] = {1.5, 3.0, -2.0};
static std::mt19937 rng(5); static std::normal_distribution<double> nz(0.0, 1.0);
bool Mpu6050::begin() { return true; }
bool Mpu6050::readAccelG(float &ax, float &ay, float &az) { ax = 0.0023 * nz(rng); ay = 0.0023 * nz(rng); az = 1 + 0.0023 * nz(rng); return true; }
bool Mpu6050::readMotion(float &ax, float &ay, float &az, float &gx, float &gy, float &gz) {
    readAccelG(ax, ay, az);
    const double ts = g_now_us / 1e6;
    double r = g_panRate * (1 + SCALE_ERR) / (PAN_SCALE_CORRECTION * (1 + (g_panRate >= 0 ? PAN_SCALE_ASYM : -PAN_SCALE_ASYM)));
    // tranco/oscilação da estrutura logo após a parada brusca (amortecido, 4 Hz)
    double dt = ts - ringT0; if (dt >= 0 && dt < 2) r += ringSign * RING * exp(-dt * 3) * sin(2 * M_PI * 4 * dt);
    gx = BG[0] + 0.05 * nz(rng); gy = BG[1] + 0.05 * nz(rng);
    gz = -r + BG[2] + WARM * (1 - exp(-ts / 600)) + 0.05 * nz(rng);
    return true; }
bool Mpu6050::setDlpfForSampleRate(uint16_t) { return true; }
bool Mpu6050::restoreDefaultDlpf() { return true; }
bool Mpu6050::writeRegister(uint8_t, uint8_t) { return true; }
static double run(double speed, double stop, int cycles, double ring) {
    RING = ring; const double accel = 200; ringT0 = -1e9; rng.seed(5);
    Mpu6050 mpu; PanSensor pan(mpu);
    uint32_t ms = 0; double truth = 0;
    auto step = [&]() { g_now_us = (uint64_t)ms * 1000; pan.update(); ms++; };
    for (int i = 0; i < 20000; i++) step();
    double p0 = pan.readPanDeg();
    auto moveTo = [&](double target) {   // perfil trapezoidal, aceleração `accel` °/s²
        double dir = target > truth ? 1 : -1, v = 0;
        while (dir * (target - truth) > 1e-6) {
            double rem = dir * (target - truth);
            double vmaxStop = sqrt(2 * accel * rem);
            v = std::min({speed, v + accel * 0.001, vmaxStop}); if (v < 0.5) v = std::min(0.5, rem / 0.001);
            g_panRate = dir * v; truth += g_panRate * 0.001; step();
        }
        g_panRate = 0; truth = target; ringT0 = ms / 1000.0; ringSign = dir;
        for (int i = 0; i < stop * 1000; i++) step();
    };
    for (int c = 0; c < cycles; c++) { moveTo(30); moveTo(-30); }
    moveTo(0);
    for (int i = 0; i < 10000; i++) step();
    const double err = pan.readPanDeg() - p0;
    printf("  %3.0f°/s, paradas de %.0f s, %d vaivéns, tranco %2.0f°/s: volta ao zero lê %+.2f°\n", speed, stop, cycles, ring, err);
    return err;
}

int main() {
    printf("=== pan: vaivém de ±30° e volta ao zero ===\n");
    int failures = 0;
    const double cases[][4] = {{30, 3, 4, 0}, {60, 3, 4, 0}, {60, 2, 8, 0}, {100, 2, 4, 0}, {60, 3, 4, 15}};
    for (const auto &c : cases) {
        const double e = run(c[0], c[1], (int)c[2], c[3]);
        // Com tranco forte na parada (estrutura vibrando), parte do giro cai na
        // janela parada; o limite é mais largo ali.
        if (fabs(e) > (c[3] > 0 ? 2.0 : 0.5)) { printf("  FALHOU\n"); failures++; }
    }
    printf(failures ? "VAIVÉM: HOUVE FALHA\n" : "VAIVÉM: TUDO OK\n");
    return failures ? 1 : 0;
}
