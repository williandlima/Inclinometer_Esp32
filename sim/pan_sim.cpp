// Simulação host do PanSensor REAL (firmware/src/PanSensor.cpp), com MPU6050
// falso: bias de fábrica do giro + mudanças de posição da placa. Ver run.sh.
#include <algorithm>
#include <cstdio>
#include <cstdlib>
#include <random>
#include <cmath>
#include "Arduino.h"
#include "Config.h"
#include "Mpu6050.h"
#include "PanSensor.h"

uint64_t g_now_us = 0;
HardwareSerial Serial;

// Estado físico simulado
static double g_tiltDeg = 0, g_tiltRateDps = 0, g_panRateDps = 0;
static double BGX = 1.5, BGY = 3.0, BGZ = -2.0;  // bias de fábrica do giro (°/s), corpo
static std::mt19937 rng(42);
static std::normal_distribution<double> noise(0.0, 0.05);
// Leitura espúria isolada (ruído no I2C): a cada g_spikeEveryMs, uma amostra
// de gz vem com g_spikeDps. 0 = desligado.
static uint32_t g_spikeEveryMs = 0, g_readCount = 0;
static double g_spikeDps = 0;
// Vibração do mastro (°/s por eixo, fases diferentes em gy e gz). 0 = sem.
static double g_vibDps = 0, g_vibHz = 0;
// Zero do giro que anda com o eixo parado: passeio aleatório (°/s/sqrt(s),
// por eixo) e aquecimento (gz muda g_warmDps com constante g_warmTauS).
static double g_walkDps = 0, g_walkGy = 0, g_walkGz = 0, g_warmDps = 0, g_warmTauS = 60;
static std::normal_distribution<double> unit(0.0, 1.0);
// true: g_panRateDps é o giro FÍSICO, positivo no sentido horário visto de
// cima, convertido para os eixos do chip sem passar por PAN_DIRECTION_SIGN —
// fixa a convenção do usuário independentemente da constante do firmware.
static bool g_clockwiseTruth = false;
// Montagem com o eixo X do chip fora da horizontal (graus): a vertical vira
// (sin m, cos m·sin t, cos m·cos t). Só com o tilt parado — o eixo do tilt é
// horizontal, então com m != 0 ele não é o X.
static double g_mountDeg = 0;

// ---------------------------------------------------------------------------
// Modo CORPO RÍGIDO (cenários V*): cinemática completa do pan-tilt, com o
// eixo de pan podendo estar fora da vertical (viatura/mastro inclinado de
// g_leanDeg). Referencial do sensor:
//     R = R_lean · R_z(-pan) · R_x(tilt) · R_mount
// (pan positivo horário visto de cima; tilt em torno do X do cabeçote; a
// placa montada com R_mount = R_y(g_rigidMountYDeg)·R_x(g_rigidMountXDeg)).
// Giro medido = escala · Rᵀ·ω_mundo + bias + ruído; acelerômetro = Rᵀ·ẑ.
// A verdade do pan é o ângulo do encoder (rotação em torno do eixo de pan,
// que está inclinado), e não a rotação em torno da gravidade.
static bool g_rigid = false;
static double g_leanDeg = 0, g_leanAzDeg = 0, g_rigidMountXDeg = 0, g_rigidMountYDeg = 0;
static double g_panTruthDeg = 0;
static double g_accelNoiseG = 0.0023;
// Balanço do mastro (rotação em torno de eixos horizontais do mundo):
// amplitude em °/s e frequência, com fases diferentes nos dois eixos.
static double g_swayDps = 0, g_swayHz = 0;
struct M3 { double m[3][3]; };
static M3 mul(const M3 &a, const M3 &b) { M3 r{}; for (int i = 0; i < 3; i++) for (int j = 0; j < 3; j++) for (int k = 0; k < 3; k++) r.m[i][j] += a.m[i][k] * b.m[k][j]; return r; }
static void mulv(const M3 &a, const double v[3], double o[3]) { for (int i = 0; i < 3; i++) o[i] = a.m[i][0] * v[0] + a.m[i][1] * v[1] + a.m[i][2] * v[2]; }
static void mulTv(const M3 &a, const double v[3], double o[3]) { for (int i = 0; i < 3; i++) o[i] = a.m[0][i] * v[0] + a.m[1][i] * v[1] + a.m[2][i] * v[2]; }
static M3 rotX(double d) { double c = cos(d * M_PI / 180), s = sin(d * M_PI / 180); return {{{1, 0, 0}, {0, c, -s}, {0, s, c}}}; }
static M3 rotY(double d) { double c = cos(d * M_PI / 180), s = sin(d * M_PI / 180); return {{{c, 0, s}, {0, 1, 0}, {-s, 0, c}}}; }
static M3 rotZ(double d) { double c = cos(d * M_PI / 180), s = sin(d * M_PI / 180); return {{{c, -s, 0}, {s, c, 0}, {0, 0, 1}}}; }
static M3 leanRot() { return mul(mul(rotZ(g_leanAzDeg), rotY(g_leanDeg)), rotZ(-g_leanAzDeg)); }
static bool rigidMotion(float &ax, float &ay, float &az, float &gx, float &gy, float &gz) {
    static const double SCALE = 1.0 / PAN_SCALE_CORRECTION;
    const double ts = g_now_us / 1e6;
    M3 L = leanRot(), Pz = rotZ(-g_panTruthDeg), Tx = rotX(g_tiltDeg), Mt = mul(rotY(g_rigidMountYDeg), rotX(g_rigidMountXDeg));
    // Balanço: rotação pequena em torno dos eixos horizontais do MUNDO,
    // aplicada à esquerda (o mastro inteiro oscila) — o acelerômetro vê a
    // vertical oscilar junto, como na realidade.
    const double w0 = 2 * M_PI * g_swayHz;
    const double ampDeg = g_swayHz > 0 ? g_swayDps / w0 : 0;
    M3 Sw = mul(rotX(-ampDeg * cos(w0 * ts)), rotY(-ampDeg * cos(w0 * ts + 1.7)));
    M3 R = mul(mul(mul(mul(Sw, L), Pz), Tx), Mt);
    const double z[3] = {0, 0, 1}, x[3] = {1, 0, 0};
    double up[3]; mulTv(R, z, up);
    // Ruído do acelerômetro do MPU6050 (400 µg/√Hz, DLPF de 21 Hz: ~2,3 mg RMS).
    ax = up[0] + g_accelNoiseG * unit(rng); ay = up[1] + g_accelNoiseG * unit(rng); az = up[2] + g_accelNoiseG * unit(rng);
    // ω_mundo = L·(-ṗ·ẑ) + L·Pz·(ṫ·x̂) + balanço horizontal (°/s)
    double kz[3], at[3], LPz_x[3];
    M3 SL = mul(Sw, L); mulv(SL, z, kz);
    M3 LPz = mul(SL, Pz); mulv(LPz, x, LPz_x);
    for (int i = 0; i < 3; i++) at[i] = LPz_x[i];
    double sx = g_swayDps * sin(2 * M_PI * g_swayHz * ts), sy = g_swayDps * sin(2 * M_PI * g_swayHz * ts + 1.7);
    double w[3] = {-g_panRateDps * kz[0] + g_tiltRateDps * at[0] + sx,
                   -g_panRateDps * kz[1] + g_tiltRateDps * at[1] + sy,
                   -g_panRateDps * kz[2] + g_tiltRateDps * at[2]};
    double wb[3]; mulTv(R, w, wb);
    gx = SCALE * wb[0] + BGX + noise(rng);
    gy = SCALE * wb[1] + BGY + noise(rng);
    gz = SCALE * wb[2] + BGZ + noise(rng);
    return true;
}

bool Mpu6050::begin() { return true; }
bool Mpu6050::readAccelG(float &ax, float &ay, float &az) {
    double t = g_tiltDeg * M_PI / 180, m = g_mountDeg * M_PI / 180;
    ax = sin(m); ay = cos(m) * sin(t); az = cos(m) * cos(t);
    return true;
}
bool Mpu6050::readMotion(float &ax, float &ay, float &az, float &gx, float &gy, float &gz) {
    if (g_rigid) return rigidMotion(ax, ay, az, gx, gy, gz);
    readAccelG(ax, ay, az);
    double t = g_tiltDeg * M_PI / 180;
    // Sensibilidade do giroscópio ~3% abaixo do nominal (ver PAN_SCALE_CORRECTION
    // em firmware/src/Config.h, calibrado em bancada na 1.6.9).
    static const double PAN_SENSOR_SCALE = 1.0 / PAN_SCALE_CORRECTION;
    double ts = g_now_us / 1e6;
    const double mx = sin(g_mountDeg * M_PI / 180), myz = cos(g_mountDeg * M_PI / 180);
    double warm = g_warmDps * (1 - exp(-ts / g_warmTauS));
    // Giro em torno da vertical para cima, nos eixos do chip: (0, sin t, cos t)
    // vezes a velocidade anti-horária vista de cima.
    const double ccw = g_clockwiseTruth ? -g_panRateDps : PAN_DIRECTION_SIGN * g_panRateDps;
    gx = ccw * PAN_SENSOR_SCALE * mx + g_tiltRateDps + BGX + noise(rng);
    gy = ccw * PAN_SENSOR_SCALE * myz * sin(t) + BGY + g_walkGy + noise(rng) + g_vibDps * sin(2 * M_PI * g_vibHz * ts + 1.3);
    gz =  ccw * PAN_SENSOR_SCALE * myz * cos(t) + BGZ + g_walkGz + warm + noise(rng) + g_vibDps * sin(2 * M_PI * g_vibHz * ts + 4.1);
    // Uma leitura a cada 10 ms (ANGLE_SAMPLE_INTERVAL_MS).
    if (g_spikeEveryMs && ++g_readCount % (g_spikeEveryMs / 10) == 0) gz = g_spikeDps;
    return true;
}
bool Mpu6050::setDlpfForSampleRate(uint16_t) { return true; }
bool Mpu6050::restoreDefaultDlpf() { return true; }
bool Mpu6050::writeRegister(uint8_t, uint8_t) { return true; }

struct Seg { double t0, t1, tiltRate, panRate; };
// Giro de pan feito à mão: desloca A graus em T s a partir de t0, com
// velocidade em cosseno levantado (parte e para suave, pico 2A/T).
struct Move { double t0, T, A; };
static const Move *g_moves = nullptr;
static int g_nMoves = 0;
static double g_minPan, g_settleFrom, g_settleMin, g_settleMax;

static double run(const char *name, const Seg *segs, int n, double endS, double startTilt, const double *reportAt, int nr) {
    Mpu6050 mpu; PanSensor pan(mpu);
    g_now_us = 0; g_tiltDeg = startTilt; rng.seed(42); g_walkGy = g_walkGz = 0;
    g_minPan = 1e9; g_settleMin = 1e9; g_settleMax = -1e9;
    int r = 0;
    printf("== %s ==\n", name);
    for (uint32_t ms = 0; ms <= (uint32_t)(endS * 1000); ms++) {
        double t = ms / 1000.0;
        g_tiltRateDps = 0; g_panRateDps = 0;
        for (int i = 0; i < n; i++) if (t >= segs[i].t0 && t < segs[i].t1) { g_tiltRateDps = segs[i].tiltRate; g_panRateDps = segs[i].panRate; }
        for (int i = 0; i < g_nMoves; i++) {
            const Move &m = g_moves[i];
            if (t >= m.t0 && t < m.t0 + m.T) g_panRateDps += (m.A / m.T) * (1 - cos(2 * M_PI * (t - m.t0) / m.T));
        }
        g_tiltDeg += g_tiltRateDps * 0.001;
        g_walkGy += g_walkDps * sqrt(0.001) * unit(rng);
        g_walkGz += g_walkDps * sqrt(0.001) * unit(rng);
        g_now_us = (uint64_t)ms * 1000;
        pan.update();
        double p = pan.readPanDeg();
        if (p < g_minPan) g_minPan = p;
        if (g_nMoves && t >= g_settleFrom) { g_settleMin = std::min(g_settleMin, p); g_settleMax = std::max(g_settleMax, p); }
        if (r < nr && t >= reportAt[r]) { printf("  t=%6.1fs  tilt=%5.1f°  pan=%7.2f°\n", t, g_tiltDeg, p); r++; }
    }
    return pan.readPanDeg();
}

// Roda um cenário no modo corpo rígido. Devolve o pior |erro| (leitura −
// verdade do encoder) depois de t >= 3 s e o erro final.
static void runRigid(const char *name, const Seg *segs, int n, double endS, double startTilt, double &worst, double &finalErr) {
    Mpu6050 mpu; PanSensor pan(mpu);
    g_rigid = true; g_now_us = 0; g_tiltDeg = startTilt; g_panTruthDeg = 0; rng.seed(42);
    worst = 0;
    for (uint32_t ms = 0; ms <= (uint32_t)(endS * 1000); ms++) {
        double t = ms / 1000.0;
        g_tiltRateDps = 0; g_panRateDps = 0;
        for (int i = 0; i < n; i++) if (t >= segs[i].t0 && t < segs[i].t1) { g_tiltRateDps = segs[i].tiltRate; g_panRateDps = segs[i].panRate; }
        g_tiltDeg += g_tiltRateDps * 0.001;
        g_panTruthDeg += g_panRateDps * 0.001;
        g_now_us = (uint64_t)ms * 1000;
        pan.update();
        double e = pan.readPanDeg() - g_panTruthDeg;
        if (t >= 3 && fabs(e) > worst) worst = fabs(e);
        if (getenv("PAN_DEBUG") && ms % 2000 == 0) {
            PanSensor::Diagnostics dg = pan.diagnostics();
            printf("    t=%5.1f err=%6.2f bias=(%.2f %.2f %.2f) ready=%d mism=%u\n", t, e, dg.biasGxDps - BGX, dg.biasGyDps - BGY, dg.biasGzDps - BGZ, dg.biasReady, dg.mismatchWindows);
        }
    }
    finalErr = pan.readPanDeg() - g_panTruthDeg;
    printf("== %s ==\n  pior erro %.2f°, erro final %.2f° (verdade final %.2f°)\n", name, worst, finalErr, g_panTruthDeg);
    g_rigid = false;
}

static int failures = 0;
static void expect(const char *name, double got, double want, double tol) {
    bool ok = fabs(got - want) <= tol;
    printf("  -> %s: pan final %.2f° (esperado %.2f° ±%.2f) %s\n", name, got, want, tol, ok ? "OK" : "FALHOU");
    if (!ok) failures++;
}

int main() {
    const double rep[] = {4, 10, 20, 40, 60, 90, 120, 150, 180};
    // A: placa parada, depois muda de posição (tilt 0 -> 45°), fica parada.
    Seg a[] = {{5, 8, 15, 0}};
    expect("A", run("A: muda posicao da placa (tilt 0->45), sem girar o pan", a, 1, 180, 0, rep, 9), 0, 0.5);
    // B: gira o pan +30° (20°/s), muda de posição (tilt 0->45) e volta (45->0).
    Seg b[] = {{5, 6.5, 0, 20}, {10, 13, 15, 0}, {60, 63, -15, 0}};
    expect("B", run("B: pan +30, tilt 0->45, depois tilt volta 45->0", b, 3, 180, 0, rep, 9), 29.76, 0.5);
    // C: placa ligada já inclinada (tilt 45), muda para 0.
    Seg c[] = {{5, 8, -15, 0}};
    expect("C", run("C: liga inclinada (45) e muda para 0", c, 1, 180, 45, rep, 9), 0, 0.5);
    // D: tilt 45 fixo; pan +40 e volta -40.
    Seg d[] = {{5, 7, 0, 20}, {15, 17, 0, -20}};
    expect("D", run("D: tilt 45 fixo, pan +40 e volta -40", d, 2, 120, 45, rep, 8), 0, 0.5);
    // E: bias de fábrica grande (pior caso), tilt 0->60, pan +30, tilt 60->10.
    BGX = 12; BGY = -15; BGZ = 14;
    Seg e[] = {{5, 9, 15, 0}, {12, 13.5, 0, 20}, {30, 33.33, -15, 0}};
    expect("E", run("E: bias ±15°/s, tilt 0->60, pan +30, tilt 60->10", e, 3, 120, 0, rep, 8), 29.75, 0.5);
    // F: ligada com a placa na mão (pan mexendo nos primeiros ~2,4 s), depois
    // parada; muda de posição (tilt 0->45) e gira o pan +30.
    BGX = 1.5; BGY = 3.0; BGZ = -2.0;
    Seg f[] = {{0, 0.7, 0, 15}, {0.7, 1.6, 0, -25}, {1.6, 2.4, 0, 10}, {10, 13, 15, 0}, {20, 21.5, 0, 20}};
    expect("F", run("F: liga com a placa em movimento, tilt 0->45, pan +30", f, 5, 180, 0, rep, 9), 30, 0.5);
    // G: giro lento e constante (5°/s) exatamente durante o boot — o bias sai
    // errado; a rede de segurança tem de reaprendê-lo e desfazer a deriva.
    Seg g[] = {{0, 2.0, 0, 5}, {10, 13, 15, 0}};
    expect("G", run("G: giro constante no boot (bias errado), tilt 0->45", g, 2, 180, 0, rep, 9), 0, 0.5);
    // H: varreduras do motor a 20°/s (a mais longa, 8 s) não podem disparar
    // o reaprendizado do bias.
    Seg h[] = {{5, 9, 0, -20}, {15, 23, 0, 20}, {40, 42, 15, 0}};
    expect("H", run("H: varreduras do motor -80 -> +80, tilt 0->30", h, 3, 180, 0, rep, 9), 80, 0.5);
    // I: placa parada 10 min, com uma leitura espúria de -250°/s em gz a cada
    // ~7 s (ruído no barramento I2C). Não pode derivar.
    g_spikeEveryMs = 7000; g_spikeDps = -250; g_readCount = 0;
    const double repI[] = {60, 120, 240, 360, 480, 600};
    expect("I", run("I: parada 10 min com leituras espurias de gz", nullptr, 0, 600, 0, repI, 6), 0, 0.5);
    // J: idem, com pan +30 e mudança de posição no meio.
    Seg j[] = {{20, 21.5, 0, 20}, {100, 103, 15, 0}};
    g_readCount = 0;
    expect("J", run("J: espurias + pan +30 + tilt 0->45", j, 2, 600, 0, repI, 6), 30, 0.5);
    g_spikeEveryMs = 0;

    // K-N: giros feitos À MÃO na bancada, com partida e parada suaves. Até a
    // 1.6.13 o ZUPT tomava as janelas lentas como paradas, apagava o que
    // fora integrado nelas e ensinava a velocidade ao bias: +8° em 16 s lia
    // 0,00° com excursões negativas (-0,6°) e oscilava por ~1 min. Além do
    // valor final, exige que a leitura nunca vá para o lado contrário do giro
    // e que fique estável depois de parar (de 2 s após parar até o fim).
    auto hand = [&](const char *id, const char *name, const Move *mv, int nmv, double endS, double want, double tol,
                    bool oneWay) {
        g_moves = mv; g_nMoves = nmv;
        double stop = 0;
        for (int i = 0; i < nmv; i++) stop = std::max(stop, mv[i].t0 + mv[i].T);
        g_settleFrom = stop + 2;
        const double repK[] = {stop, stop + 2, stop + 10, endS};
        double got = run(name, nullptr, 0, endS, 0, repK, 4);
        expect(id, got, want, tol);
        bool okMin = !oneWay || g_minPan > -0.05, okSettle = g_settleMax - g_settleMin < 0.05;
        if (oneWay) printf("  -> %s: menor leitura %.2f° (> -0,05) %s\n", id, g_minPan, okMin ? "OK" : "FALHOU");
        printf("  -> %s: variação após parar %.3f° (< 0,05) %s\n", id, g_settleMax - g_settleMin, okSettle ? "OK" : "FALHOU");
        if (!okMin) failures++;
        if (!okSettle) failures++;
        g_moves = nullptr; g_nMoves = 0;
    };
    const Move k[] = {{10, 4, 8}};
    hand("K", "K: giro a mao +8 em 4 s, suave", k, 1, 60, 8, 0.1, true);
    const Move l[] = {{10, 16, 8}};
    hand("L", "L: giro a mao lento, +8 em 16 s (pico 1°/s)", l, 1, 80, 8, 0.2, true);
    const Move m[] = {{10, 1.5, 1}, {12.5, 1.5, 1}, {15, 1.5, 1}, {17.5, 1.5, 1},
                      {20, 1.5, 1}, {22.5, 1.5, 1}, {25, 1.5, 1}, {27.5, 1.5, 1}};
    hand("M", "M: passos a mao de +1 (8x, 1,5 s cada, pausa de 1 s)", m, 8, 80, 8, 0.2, true);
    // Mais lento que isto (velocidade quase constante abaixo de ~0,5°/s por
    // vários segundos, ou abaixo de 1°/s por mais de 20 s) é indistinguível
    // de um zero do giro que andou: ver PAN_ZUPT_SHIFT_* em Config.h.
    const Move nn[] = {{10, 16, 8}, {44, 4, -8}};
    hand("N", "N: lento, +8 em 16 s, depois volta -8 em 4 s", nn, 2, 80, 0, 0.4, false);

    // O: vibração forte (2°/s) a 33,3 Hz = 100/3, onde a mediana anti-picos
    // mais retifica a vibração num bias falso. Sob vibração forte o giro à
    // mão lento se perde (o limiar sobe de propósito, ver
    // PAN_ZUPT_VIBRATION_FACTOR), mas a leitura NÃO pode disparar para fora
    // do que foi girado: na 1.6.13 ela ia a +16..+25° depois de +8°, e uma
    // deriva falsa extrapolada chegou a levá-la a -65° (PAN_BIAS_SLOPE_MAX_DPS2).
    g_vibDps = 2.0; g_vibHz = 33.3;
    const Move o[] = {{10, 4, 8}};
    g_moves = o; g_nMoves = 1;
    const double repO[] = {14, 30, 60};
    expect("O", run("O: vibracao 2°/s a 33,3 Hz + giro a mao +8 em 4 s (nao pode disparar)", nullptr, 0, 60, 0, repO, 3), 4, 4.5);
    g_moves = nullptr; g_nMoves = 0;
    g_vibDps = 0;

    // P-Q: o ensaio de bancada que achou o problema da 1.6.14 — giros à mão
    // 0 -> -30 -> +90 -> +30 -> +60 -> 0, lendo ~15 s depois de cada um —
    // com o zero do giro andando (P: passeio aleatório; Q: aquecimento logo
    // depois de ligar). Na 1.6.14 o bias saía do limiar de "parado" e não
    // voltava: P leu -32/+83/+20/+45/-18 e Q passou de 40° de erro.
    // approachDeg > 0: os últimos approachDeg graus de cada giro são feitos
    // devagar, em approachS segundos — a aproximação final da marca à mão.
    // Semente do ruído dos ensaios de bancada (benchStats() varia).
    static unsigned g_benchSeed = 42;
    static bool g_benchQuiet = false;
    auto bench = [&](const char *id, const char *name, double approachDeg = 0, double approachS = 0, double tol = 0.5) -> double {
        static const double targets[] = {-30, 90, 30, 60, 0};
        Move mv[10];
        int nmv = 0;
        double reads[5], t = 15, pos = 0;
        for (int i = 0; i < 5; i++) {
            double A = targets[i] - pos;
            double ap = approachDeg > 0 ? (A > 0 ? approachDeg : -approachDeg) : 0;
            mv[nmv] = {t, std::max(0.5, fabs(A - ap) / 45.0), A - ap};
            t += mv[nmv++].T;
            if (ap != 0) {
                mv[nmv] = {t + 0.3, approachS, ap};
                t += 0.3 + mv[nmv++].T;
            }
            t += 15;
            reads[i] = t - 0.5;
            pos = targets[i];
        }
        g_moves = mv; g_nMoves = nmv;
        Mpu6050 mpu; PanSensor pan(mpu);
        g_now_us = 0; g_tiltDeg = 0; rng.seed(getenv("PAN_SEED") ? atoi(getenv("PAN_SEED")) : g_benchSeed); g_walkGy = g_walkGz = 0;
        if (!g_benchQuiet) printf("== %s ==\n", name);
        double truth = 0, worst = 0;
        int r = 0;
        for (uint32_t ms = 0; ms <= (uint32_t)(t * 1000); ms++) {
            double ts = ms / 1000.0;
            g_panRateDps = 0; g_tiltRateDps = 0;
            for (int i = 0; i < nmv; i++)
                if (ts >= mv[i].t0 && ts < mv[i].t0 + mv[i].T)
                    g_panRateDps += (mv[i].A / mv[i].T) * (1 - cos(2 * M_PI * (ts - mv[i].t0) / mv[i].T));
            truth += g_panRateDps * 0.001;
            g_walkGy += g_walkDps * sqrt(0.001) * unit(rng);
            g_walkGz += g_walkDps * sqrt(0.001) * unit(rng);
            g_now_us = (uint64_t)ms * 1000;
            pan.update();
            if (r < 5 && ts >= reads[r]) {
                double p = pan.readPanDeg();
                if (!g_benchQuiet) printf("  real %6.1f°  lido %7.2f°\n", truth, p);
                worst = std::max(worst, fabs(p - truth));
                r++;
            }
        }
        g_moves = nullptr; g_nMoves = 0;
        if (g_benchQuiet) return worst;
        bool ok = worst <= tol;
        printf("  -> %s: pior erro %.2f° (< %.2f) %s\n", id, worst, tol, ok ? "OK" : "FALHOU");
        if (!ok) failures++;
        return worst;
    };
    // O mesmo ensaio com 10 sementes de ruído: uma única realização do passeio
    // do zero do giro não diz se uma mudança melhorou ou piorou o modelo.
    auto benchStats = [&](const char *id, const char *name, double approachDeg, double approachS, double tolMean,
                          double tolMax) {
        if (getenv("PAN_SEED")) {  // comparação semente a semente (fora do run.sh)
            bench(id, name, approachDeg, approachS, tolMax);
            return;
        }
        double sum = 0, mx = 0;
        const int N = 10;
        printf("== %s (10 sementes) ==\n", name);
        g_benchQuiet = true;
        for (int k = 0; k < N; k++) {
            g_benchSeed = k == 0 ? 42 : k;
            double w = bench(id, name, approachDeg, approachS);
            sum += w;
            mx = std::max(mx, w);
        }
        g_benchQuiet = false;
        g_benchSeed = 42;
        bool ok = sum / N <= tolMean && mx <= tolMax;
        printf("  -> %s: pior erro médio %.2f° (< %.2f), máximo %.2f° (< %.2f) %s\n", id, sum / N, tolMean, mx, tolMax,
               ok ? "OK" : "FALHOU");
        if (!ok) failures++;
    };
    g_walkDps = 0.02;
    bench("P", "P: bancada -30/+90/+30/+60/0, zero do giro passeando (0,02°/s/sqrt(s))");
    benchStats("P*", "P: bancada, zero do giro passeando", 0, 0, 0.35, 1.0);
    g_walkDps = 0;
    g_warmDps = 2.0; g_warmTauS = 60;
    bench("Q", "Q: bancada -30/+90/+30/+60/0, logo depois de ligar (zero do giro +2°/s em ~1 min)");
    g_warmDps = 0;

    // R: tilt fixo em 30° e pan +40. A projeção na vertical tinha o sinal do
    // termo de gy trocado (até a 1.6.14): a taxa saía multiplicada por
    // cos(2·tilt) — metade a 30°, zero a 45°, sentido invertido acima disso.
    // Os cenários acima não pegavam porque o sensor simulado tinha o mesmo
    // sinal trocado.
    Seg rr[] = {{5, 7, 0, 20}};
    expect("R", run("R: tilt 30 fixo, pan +40", rr, 1, 60, 30, rep, 4), 40, 0.3);

    // S: o SENTIDO. Giro de 30° no sentido horário visto de cima tem de ler
    // +30°, com a placa deitada (tilt 0) e em pé (tilt 90): a projeção não
    // depende da montagem. A 1.6.15 lia -30° (bancada: "movimento positivo
    // aparece negativo").
    g_clockwiseTruth = true;
    Seg ss[] = {{5, 6.5, 0, 20}};
    expect("S1", run("S1: giro horario visto de cima, placa deitada (tilt 0)", ss, 1, 30, 0, rep, 3), 30, 0.3);
    expect("S2", run("S2: giro horario visto de cima, placa em pe (tilt 90)", ss, 1, 30, 90, rep, 3), 30, 0.3);
    g_clockwiseTruth = false;

    // U: sensor montado com o eixo X a 44° da horizontal, giro de pan +40°.
    // Até a 1.6.16 a projeção usava só gy/gz (supunha X horizontal) e lia
    // 40·cos(44°) = 28,8° — o que a bancada mostrou: "posição 40 mostra
    // 28,75". A projeção nos 3 eixos não depende da montagem.
    g_mountDeg = 44;
    Seg uu[] = {{5, 7, 0, 20}};
    expect("U1", run("U1: eixo X a 44 graus da horizontal, tilt 0, pan +40", uu, 1, 40, 0, rep, 4), 40, 0.3);
    expect("U2", run("U2: eixo X a 44 graus da horizontal, tilt 30, pan +40", uu, 1, 40, 30, rep, 4), 40, 0.3);
    g_mountDeg = 0;

    // T: o mesmo ensaio de bancada, com a aproximação final de cada giro
    // feita devagar (últimos 3° em 5 s) e o zero do giro passeando. Na 1.6.15,
    // ao readotar um bias que andou, as janelas lentas da aproximação eram
    // apagadas como se fossem deriva (bancada: "erro de 6 graus acumulado,
    // constante"; aqui a 1.6.15 erra 4,5°). Com o zero passeando e a
    // aproximação lenta, sobra cerca de 1°: parte dela é indistinguível da
    // deriva, e no fim do curso (+90°) o integrador preso esconde a deriva.
    g_walkDps = 0.02;
    // Medido em 30 sementes (1.6.18 -> 1.6.19): pior erro médio 0,82 -> 0,68°,
    // máximo 3,74 -> 1,55°. A semente 42 sozinha dá 1,18 -> 1,75°: azar de uma
    // realização, por isso o critério é estatístico.
    benchStats("T", "T: bancada com aproximacao final lenta (3° em 5 s), zero passeando", 3, 5, 0.9, 2.0);
    g_walkDps = 0;

    // V: eixo de pan FORA DA VERTICAL (viatura/mastro inclinado) — modo corpo
    // rígido. A projeção na gravidade (ω·u) soma ao pan ṫ·(a·ẑ), em que a é o
    // eixo do tilt: com o eixo de pan inclinado de β, o eixo do tilt deixa de
    // ser horizontal e até sen β de todo movimento de tilt vaza para o pan.
    {
        double worst, fin;
        // V0: nivelado, placa montada torta (X a 44°, Y a 10°): referência.
        g_leanDeg = 0; g_rigidMountXDeg = 0; g_rigidMountYDeg = 44;
        Seg v0[] = {{5, 9, 15, 0}, {40, 42, 0, 15}, {60, 64, -15, 0}};
        runRigid("V0: nivelado, montagem torta, tilt 0->60, pan +30 a 60, tilt volta", v0, 3, 90, 0, worst, fin);
        expect("V0 erro final", fin, 0, 0.3); expect("V0 pior erro", worst, 0, 0.5);
        // V1: inclinado 3° na direção de pior caso; tilt 0->60 e segura.
        g_leanDeg = 3; g_leanAzDeg = 0;
        // V1: inclinado 3° na direção de pior caso; tilt 0->60 e segura. O
        // firmware 1.6.18 erra 3,2° com o tilt em 60° (60·sen 3°).
        g_leanDeg = 3; g_leanAzDeg = 0;
        runRigid("V1: eixo de pan inclinado 3°, tilt 0->60, pan +30 a 60, tilt volta", v0, 3, 90, 0, worst, fin);
        expect("V1 erro final", fin, 0, 0.2); expect("V1 pior erro", worst, 0, 1.0);
        // V2: inclinado 5°, caminho com pan girando com o tilt inclinado — o
        // erro do 1.6.18 FICA (-2,5°).
        g_leanDeg = 5; g_leanAzDeg = 30;
        Seg v2[] = {{5, 7, 0, 20}, {20, 23, 15, 0}, {40, 44, 0, -20}, {60, 63, -15, 0}, {80, 82, 0, 20}};
        runRigid("V2: inclinado 5°, pan +40, tilt 0->45, pan -80, tilt 45->0, pan +40", v2, 5, 110, 0, worst, fin);
        expect("V2 erro final", fin, 0, 0.3); expect("V2 pior erro", worst, 0, 1.0);
        // V3: V1 com balanço do mastro (1,5°/s a 1,2 Hz) — 1.6.18: 8°.
        g_leanDeg = 3; g_leanAzDeg = 0; g_swayDps = 1.5; g_swayHz = 1.2;
        runRigid("V3: V1 com balanco do mastro (1,5°/s a 1,2 Hz)", v0, 3, 90, 0, worst, fin);
        expect("V3 erro final", fin, 0, 0.3); expect("V3 pior erro", worst, 0, 1.0);
        // V3b: nivelado, só o balanço — 1.6.18: 5° (nenhuma janela parada).
        g_leanDeg = 0;
        runRigid("V3b: nivelado com balanco do mastro", v0, 3, 90, 0, worst, fin);
        expect("V3b erro final", fin, 0, 0.3); expect("V3b pior erro", worst, 0, 0.5);
        g_swayDps = 0;
        // V4: nivelado e PARADO por 10 min, com o ruído do acelerômetro: o
        // aprendizado do bias pelo acelerômetro não pode criar deriva.
        runRigid("V4: nivelado, parado 10 min (ruido do acelerometro)", nullptr, 0, 600, 0, worst, fin);
        expect("V4 pior erro", worst, 0, 0.1);
        // V5: 10 min de operação com desnível de 3°, balanço e movimentos de
        // pan e tilt, em três frequências de balanço.
        Seg v5[] = {{20, 22, 0, 15}, {60, 64, 10, 0}, {100, 103, 0, -20}, {150, 154, -10, 0},
                    {200, 202, 0, 15}, {260, 263, 15, 0}, {320, 324, 0, -15}, {400, 403, -15, 0}, {480, 482, 0, 15}};
        const double hz[] = {0.6, 1.2, 2.5};
        for (double f : hz) {
            char nm[96], id[32];
            snprintf(nm, sizeof nm, "V5: 10 min, desnivel 3°, balanco 2°/s a %.1f Hz, pan e tilt", f);
            snprintf(id, sizeof id, "V5 %.1f Hz pior erro", f);
            g_leanDeg = 3; g_leanAzDeg = 60; g_swayDps = 2.0; g_swayHz = f;
            runRigid(nm, v5, 9, 600, 0, worst, fin);
            expect(id, worst, 0, 1.0);
        }
        g_swayDps = 0;
        // V6: desnível grande (10°) — o limite do desacoplamento é 1−cos β.
        g_leanDeg = 10; g_leanAzDeg = 0;
        runRigid("V6: desnivel 10°, tilt 0->60, pan +30 a 60, tilt volta", v0, 3, 90, 0, worst, fin);
        expect("V6 erro final", fin, 0, 0.5);
        g_swayDps = 0; g_leanDeg = 0; g_leanAzDeg = 0; g_rigidMountXDeg = 0; g_rigidMountYDeg = 0;
    }

    printf(failures ? "PAN: HOUVE FALHA\n" : "PAN: TUDO OK\n");
    return failures ? 1 : 0;
}
