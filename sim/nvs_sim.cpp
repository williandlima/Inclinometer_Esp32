// Zero do tilt na memória permanente e watchdog — firmware REAL (main.cpp),
// com MPU6050, BLE, NVS e watchdog falsos. Ver run.sh.
//   nvs_sim calibra   -> liga com o tilt em 10°, calibra pelo BLE, confere o
//                        zero e que a flash foi gravada uma única vez
//   nvs_sim religa    -> "religa" (novo processo, mesma NVS em arquivo): o
//                        tilt já tem de ler ~0° sem calibrar de novo
#include <cmath>
#include <cstdio>
#include <cstring>
#include "Arduino.h"
#include "BLEMock.h"
#include "Config.h"
#include "Mpu6050.h"
#include "AngleSensor.h"
#include "Preferences.h"
#include "esp_task_wdt.h"

uint64_t g_now_us = 0;
HardwareSerial Serial;
std::vector<BLEService *> g_services;
std::function<void(BLECharacteristic *)> g_onNotify;
void setup();
void loop();
extern AngleSensor angleSensor;

static double g_tiltDeg = 10.0;
bool Mpu6050::begin() { return true; }
void Mpu6050::maintain() {}
bool Mpu6050::readAccelG(float &ax, float &ay, float &az) {
    double t = g_tiltDeg * M_PI / 180; ax = 0; ay = sin(t); az = cos(t); return true;
}
bool Mpu6050::readMotion(float &ax, float &ay, float &az, float &gx, float &gy, float &gz) {
    readAccelG(ax, ay, az); gx = gy = gz = 0; return true;
}
bool Mpu6050::setDlpfForSampleRate(uint16_t) { return true; }
bool Mpu6050::restoreDefaultDlpf() { return true; }
bool Mpu6050::writeRegister(uint8_t, uint8_t) { return true; }

static int failures = 0;
static void check(const char *name, bool ok, double v) {
    printf("  %s %s: %.3f\n", ok ? "OK    " : "FALHOU", name, v);
    if (!ok) failures++;
}
static void run(uint32_t ms) { for (uint32_t i = 0; i < ms; i++) { g_now_us += 1000; loop(); } }
static BLECharacteristic *find(const char *uuid) {
    for (auto *s : g_services) for (auto *c : s->chars) if (c->uuid == uuid && c->registered) return c;
    return nullptr;
}

int main(int argc, char **argv) {
    bool religa = argc > 1 && !strcmp(argv[1], "religa");
    setup();
    check("watchdog iniciado no setup, 10 s", g_wdtInits == 1 && g_wdtAdds == 1 && g_wdtTimeoutS == WATCHDOG_TIMEOUT_S, g_wdtTimeoutS);
    run(2000);
    check("loop alimenta o watchdog a cada iteração", g_wdtResets == 2000, g_wdtResets);
    if (!religa) {
        printf("== calibra ==\n");
        check("antes de calibrar: lê a inclinação do sensor (~10°)", fabs(angleSensor.readAngleDeg()) > 8.0, angleSensor.readAngleDeg());
        check("nada gravado na flash sem calibrar", Preferences::writes() == 0, Preferences::writes());
        BLECharacteristic *cal = find(CHAR_CALIBRATE_UUID);
        if (!cal) { printf("  FALHOU característica de calibração não encontrada\n"); return 1; }
        cal->value = std::string("\x01", 1);
        cal->cb->onWrite(cal);
        run(2000);
        check("depois de calibrar: 0°", fabs(angleSensor.readAngleDeg()) < 0.05, angleSensor.readAngleDeg());
        check("zero gravado na flash uma única vez (2 s de loop)", Preferences::writes() == 1, Preferences::writes());
        g_tiltDeg = 25.0;
        run(3000);
        check("tilt real +15° a partir do zero", fabs(angleSensor.readAngleDeg() - 15.0 * TILT_SCALE_CORRECTION_POS) < 1.2, angleSensor.readAngleDeg());
        check("mover o tilt não grava na flash", Preferences::writes() == 1, Preferences::writes());
    } else {
        printf("== religa ==\n");
        check("religado SEM calibrar: zero restaurado (0° na mesma posição)", fabs(angleSensor.readAngleDeg()) < 0.05, angleSensor.readAngleDeg());
        check("restaurar não regrava a flash", Preferences::writes() == 0, Preferences::writes());
    }
    printf(failures ? "NVS/WATCHDOG: HOUVE FALHA\n" : "NVS/WATCHDOG: TUDO OK\n");
    return failures ? 1 : 0;
}
