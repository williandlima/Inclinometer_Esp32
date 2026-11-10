// Fusão giroscópio + acelerômetro no TILT — AngleSensor e PanSensor REAIS,
// com MPU6050 falso fisicamente coerente: o giro vê a rotação real (com bias
// de fábrica, erro de escala e ruído) e o acelerômetro vê a gravidade MAIS a
// aceleração linear (vibração do motor), que não é rotação. Ver run.sh.
// Dois AngleSensor leem o mesmo sensor: um com o giro ligado (1.6.23) e um
// só com o acelerômetro (o método até a 1.6.22), para comparar lado a lado.
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

static double g_tilt = 0, g_tiltRate = 0;       // rotação REAL (°, °/s)
static double g_vibDeg = 0, g_vibHz = 0;         // aceleração linear em Y, como ângulo aparente (°)
static double g_mountDeg = 0;                    // eixo do tilt a ψ do X do chip (no plano XY)
static double g_gyroScale = 0.97;                // sensibilidade do giro 3% abaixo do nominal
static int g_spikeEvery = 0, g_reads = 0;        // leitura espúria de 500°/s em gx a cada N leituras
static const double BG[3] = {1.5, 3.0, -2.0};    // bias de fábrica (°/s)
static std::mt19937 rng(9);
static std::normal_distribution<double> nz(0.0, 1.0);

// Ruído sorteado UMA vez por instante: os dois AngleSensor e o PanSensor leem
// o mesmo chip, então têm de ver a mesma amostra (senão a comparação entre os
// métodos mede o ruído, não o método).
static double g_noise[6]; static uint64_t g_noiseAt = ~0ull;
static void noise() {
    if (g_noiseAt == g_now_us) return;
    g_noiseAt = g_now_us;
    for (double &v : g_noise) v = nz(rng);
    g_reads++;
}
static void physics(double out_u[3], double out_w[3]) {
    // Como nos outros simuladores, o acelerômetro "vê" um ângulo menor que o
    // real (é o que TILT_SCALE_CORRECTION_NEG/_POS compensam); o giro vê a
    // rotação verdadeira.
    const double seen = g_tilt / (g_tilt >= 0 ? TILT_SCALE_CORRECTION_POS : TILT_SCALE_CORRECTION_NEG);
    const double D = M_PI / 180, th = -seen * D, m = g_mountDeg * D;
    const double a[3] = {cos(m), sin(m), 0};                  // eixo do tilt nos eixos do chip
    const double z[3] = {0, 0, 1};
    const double axz[3] = {a[1], -a[0], 0};                  // a × z
    const double adz = 0;                                     // a · z
    for (int i = 0; i < 3; i++) out_u[i] = z[i] * cos(th) + axz[i] * sin(th) + a[i] * adz * (1 - cos(th));
    for (int i = 0; i < 3; i++) out_w[i] = g_tiltRate * a[i];
}
bool Mpu6050::begin() { return true; }
bool Mpu6050::readAccelG(float &ax, float &ay, float &az) {
    double u[3], w[3]; physics(u, w);
    const double t = g_now_us / 1e6;
    // Aceleração linear (não gira nada): soma em Y o que desloca o ângulo aparente.
    const double lin = tan(g_vibDeg * M_PI / 180) * sin(2 * M_PI * g_vibHz * t);
    noise();
    ax = u[0] + 0.0023 * g_noise[0]; ay = u[1] + lin + 0.0023 * g_noise[1]; az = u[2] + 0.0023 * g_noise[2];
    return true;
}
bool Mpu6050::readMotion(float &ax, float &ay, float &az, float &gx, float &gy, float &gz) {
    readAccelG(ax, ay, az);
    double u[3], w[3]; physics(u, w);
    gx = g_gyroScale * w[0] + BG[0] + 0.05 * g_noise[3];
    gy = g_gyroScale * w[1] + BG[1] + 0.05 * g_noise[4];
    gz = g_gyroScale * w[2] + BG[2] + 0.05 * g_noise[5];
    if (g_spikeEvery && g_reads % g_spikeEvery == 0) gx = 500;
    return true;
}
bool Mpu6050::setDlpfForSampleRate(uint16_t) { return true; }
bool Mpu6050::restoreDefaultDlpf() { return true; }
bool Mpu6050::writeRegister(uint8_t, uint8_t) { return true; }

static int failures = 0;
static void check(const char *name, bool ok, const char *fmt, double a = 0, double b = 0) {
    char detail[160]; snprintf(detail, sizeof detail, fmt, a, b);
    printf("  %s %s: %s\n", ok ? "OK    " : "FALHOU", name, detail);
    if (!ok) failures++;
}

struct Rig {
    Mpu6050 mpu; PanSensor pan{mpu}; AngleSensor fused{mpu}, accel{mpu};
    uint32_t ms = 0;
    double worstDiff = 0;
    Rig() { fused.attachGyro(&pan); }
    // motion(t) define g_tilt/g_tiltRate; roda `seconds`.
    template <class F> void run(double seconds, F motion) {
        for (uint32_t end = ms + (uint32_t)(seconds * 1000); ms < end; ms++) {
            motion(ms / 1000.0);
            g_now_us = (uint64_t)ms * 1000;
            fused.update(); accel.update(); pan.update();
        }
    }
    void settle(double tilt0, double seconds = 8) {
        run(seconds, [&](double) { g_tilt = tilt0; g_tiltRate = 0; });
    }
    void zero() { fused.calibrate(); accel.calibrate(); }
};
static void reset(double mount = 0) {
    g_now_us = 0; g_tilt = g_tiltRate = 0; g_vibDeg = g_vibHz = 0; g_mountDeg = mount; g_gyroScale = 0.97;
    g_spikeEvery = 0; g_reads = 0; g_noiseAt = ~0ull; rng.seed(9);
}

int main() {
    printf("=== tilt: fusão giroscópio + acelerômetro (AngleSensor) ===\n");
    {   // 1. Boot e parado: sem bias confirmado vale o acelerômetro; depois, os dois iguais.
        reset(); Rig r;
        r.run(1.5, [&](double) { g_tilt = 12; g_tiltRate = 0; });
        check("1. antes do bias do giro: só acelerômetro", !r.fused.fusionActive(), "fusão ativa = %.0f", r.fused.fusionActive());
        r.settle(12, 10);
        check("1. bias confirmado: fusão ativa", r.fused.fusionActive(), "fusão ativa = %.0f", r.fused.fusionActive());
        double worst = 0;
        r.run(600, [&](double) { g_tilt = 12; g_tiltRate = 0; worst = std::max(worst, fabs((double)r.fused.readAngleDeg() - r.accel.readAngleDeg())); });
        check("1. parado 10 min: igual ao acelerômetro, sem deriva", worst < 0.05, "maior diferença %.3f°", worst);
    }
    {   // 2. Vibração do motor: ±2° APARENTES a 17,6 Hz, sem rotação nenhuma.
        reset(); Rig r; r.settle(0, 10); r.zero();
        g_vibDeg = 2.0; g_vibHz = 17.63;
        r.run(30, [&](double) { g_tilt = 0; g_tiltRate = 0; });
        double sf = r.fused.maxAngleDeg() - r.fused.minAngleDeg(), sa = r.accel.maxAngleDeg() - r.accel.minAngleDeg();
        check("2. vibração linear 17,6 Hz (±2° aparentes): mín/máx", sf < 0.12 && sf < sa, "fundido %.2f° de faixa; só acelerômetro %.2f°", sf, sa);
    }
    {   // 2b. O caso que importa: o topo do mastro TRANSLADA a 1 Hz (balanço),
        // sem inclinar — o acelerômetro lê ±1° que não existem.
        reset(); Rig r; r.settle(0, 10); r.zero();
        g_vibDeg = 1.0; g_vibHz = 1.0;
        r.run(30, [&](double) { g_tilt = 0; g_tiltRate = 0; });
        double sf = r.fused.maxAngleDeg() - r.fused.minAngleDeg(), sa = r.accel.maxAngleDeg() - r.accel.minAngleDeg();
        check("2b. translação a 1 Hz (±1° aparentes, 0° reais): mín/máx", sf < 0.45 && sa > 1.7, "fundido %.2f° de faixa; só acelerômetro %.2f°", sf, sa);
        g_vibDeg = 1.0; g_vibHz = 2.0; r.zero();
        r.run(30, [&](double) { g_tilt = 0; g_tiltRate = 0; });
        sf = r.fused.maxAngleDeg() - r.fused.minAngleDeg(); sa = r.accel.maxAngleDeg() - r.accel.minAngleDeg();
        check("2b. translação a 2 Hz (±1° aparentes, 0° reais): mín/máx", sf < 0.25 && sa > 1.4, "fundido %.2f° de faixa; só acelerômetro %.2f°", sf, sa);
    }
    {   // 3. Rajada REAL: meio seno de 2° em 0,5 s (rotação de verdade).
        reset(); Rig r; r.settle(0, 10); r.zero();
        r.run(6, [&](double t) {
            double x = t - 12.0;
            if (x >= 0 && x < 0.5) { g_tilt = 2 * sin(M_PI * x / 0.5); g_tiltRate = 2 * (M_PI / 0.5) * cos(M_PI * x / 0.5); }
            else { g_tilt = 0; g_tiltRate = 0; }
        });
        check("3. rajada real de 2° em 0,5 s: máximo registrado", r.fused.maxAngleDeg() > 1.65 && r.fused.maxAngleDeg() < 2.1 &&
              r.fused.maxAngleDeg() > r.accel.maxAngleDeg() - 0.15,
              "fundido %.2f°; só acelerômetro %.2f° (real 2,00°)", r.fused.maxAngleDeg(), r.accel.maxAngleDeg());
    }
    {   // 4. Balanço real de ±1° a 1 Hz COM vibração do motor por cima.
        reset(); Rig r; r.settle(0, 10); r.zero();
        g_vibDeg = 2.0; g_vibHz = 17.63;
        r.run(30, [&](double t) { g_tilt = sin(2 * M_PI * t); g_tiltRate = 2 * M_PI * cos(2 * M_PI * t); });
        double sf = r.fused.maxAngleDeg() - r.fused.minAngleDeg(), sa = r.accel.maxAngleDeg() - r.accel.minAngleDeg();
        check("4. balanço real ±1° + vibração: faixa medida (real 2,00°)", fabs(sf - 2.0) < 0.2,
              "fundido %.2f°; só acelerômetro %.2f°", sf, sa);
    }
    for (double gs : {0.97, 1.03}) {   // 5. Movimento do motor do tilt: 0 -> 30° a 15°/s, giro 3% fora de escala.
        reset(); Rig r; r.settle(0, 10); r.zero(); g_gyroScale = gs;
        r.run(16, [&](double t) {
            double x = t - 12.0;
            if (x >= 0 && x < 2.0) { g_tiltRate = 15; g_tilt = 15 * x; } else { g_tiltRate = 0; g_tilt = x < 0 ? 0 : 30; }
        });
        double fin = r.accel.readAngleDeg();  // onde o acelerômetro assenta (mesma calibração de escala)
        printf("  (giro com escala %.2f)\n", gs);
        check("5. motor 0->30° a 15°/s: ultrapassa o ponto final < 0,6° (0,03·Ω·τ)", r.fused.maxAngleDeg() - fin < 0.6,
              "máximo %.2f° para um final de %.2f°", r.fused.maxAngleDeg(), fin);
        check("5. depois de parar: fundido = acelerômetro", fabs(r.fused.readAngleDeg() - fin) < 0.05, "diferença %.3f°", r.fused.readAngleDeg() - fin);
    }
    {   // 6. Leituras espúrias do giro (500°/s em gx a cada ~0,7 s), parado.
        reset(); Rig r; r.settle(0, 10); r.zero();
        g_spikeEvery = 211;
        r.run(60, [&](double) { g_tilt = 0; g_tiltRate = 0; });
        double sf = r.fused.maxAngleDeg() - r.fused.minAngleDeg();
        check("6. leituras espúrias do giro não entram nos mín/máx", sf < 0.15, "faixa %.2f°", sf);
    }
    {   // 7. Eixo do tilt a 30° do X do chip: a taxa vem dos três eixos.
        reset(30); Rig r; r.settle(0, 10); r.zero();
        double worst = 0;
        r.run(40, [&](double t) {
            g_tilt = 5 * sin(2 * M_PI * 0.2 * t); g_tiltRate = 5 * 2 * M_PI * 0.2 * cos(2 * M_PI * 0.2 * t);
            worst = std::max(worst, fabs((double)r.fused.minAngleDeg() - r.accel.minAngleDeg()));
        });
        double sf = r.fused.maxAngleDeg() - r.fused.minAngleDeg(), sa = r.accel.maxAngleDeg() - r.accel.minAngleDeg();
        check("7. montagem torta (30°): movimento lento igual nos dois métodos", fabs(sf - sa) < 0.25 && r.fused.fusionActive(),
              "fundido %.2f°; só acelerômetro %.2f°", sf, sa);
    }
    {   // 8. Giro muito errado (escala 1,5x): a salvaguarda de divergência devolve ao acelerômetro.
        reset(); Rig r; r.settle(0, 10); r.zero(); g_gyroScale = 1.6;
        r.run(25, [&](double t) {
            double x = t - 12.0;
            if (x >= 0 && x < 2.0) { g_tiltRate = 20; g_tilt = 20 * x; } else { g_tiltRate = 0; g_tilt = x < 0 ? 0 : 40; }
        });
        check("8. giro com escala absurda: leitura final correta", fabs(r.fused.readAngleDeg() - r.accel.readAngleDeg()) < 0.1 &&
              r.fused.maxAngleDeg() - r.accel.readAngleDeg() < 3.5, "final %.2f°, máximo %.2f°", r.fused.readAngleDeg(), r.fused.maxAngleDeg());
    }
    printf(failures ? "TILT (FUSÃO): HOUVE FALHA\n" : "TILT (FUSÃO): TUDO OK\n");
    return failures ? 1 : 0;
}
