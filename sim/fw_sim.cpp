// Simulador host do firmware REAL (main.cpp + BleServer + VibrationCapture +
// sensores), com MPU6050 e lib BLE falsos. Protocolo linha-a-linha em stdin:
//   LIST | READ <uuid> | WRITE <uuid> <hex> | RUN <ms> | QUIT
#include <cstdio>
#include <cmath>
#include <iostream>
#include <random>
#include <sstream>
#include <string>
#include "Arduino.h"
#include "Mpu6050.h"
#include "BLEMock.h"

uint64_t g_now_us = 0;
HardwareSerial Serial;
std::vector<BLEService *> g_services;
std::function<void(BLECharacteristic *)> g_onNotify;
void setup();
void loop();

// ---- MPU6050 falso: tilt 3,0 Hz (+-0,5 grau), pan 4,5 Hz (+-2 graus/s), bias de fabrica
static const double TILT_HZ = 3.0, TILT_AMP_DEG = 0.5, PAN_HZ = 4.5, PAN_AMP_DPS = 2.0;
static const double BGY = 3.0, BGZ = -2.0;
static std::mt19937 rng(7);
static std::normal_distribution<double> nz(0.0, 0.02);
static double tNow() { return g_now_us / 1e6; }
static double tiltRad() { return (TILT_AMP_DEG * sin(2 * M_PI * TILT_HZ * tNow())) * M_PI / 180; }
bool Mpu6050::begin() { return true; }
void Mpu6050::maintain() {}
bool Mpu6050::readAccelG(float &ax, float &ay, float &az) {
    double t = tiltRad(); ax = 0; ay = sin(t) + nz(rng) * 0.01; az = cos(t); return true;
}
bool Mpu6050::readMotion(float &ax, float &ay, float &az, float &gx, float &gy, float &gz) {
    readAccelG(ax, ay, az);
    // PAN_SENSOR_SCALE: ver sim/pan_sim.cpp e PAN_SCALE_CORRECTION em Config.h.
    static const double PAN_SENSOR_SCALE = 1.0 / 1.051;
    double t = tiltRad(), w = PAN_AMP_DPS * PAN_SENSOR_SCALE * sin(2 * M_PI * PAN_HZ * tNow());
    gx = nz(rng); gy = -w * sin(t) + BGY + nz(rng); gz = w * cos(t) + BGZ + nz(rng);
    return true;
}
bool Mpu6050::setDlpfForSampleRate(uint16_t) { return true; }
bool Mpu6050::restoreDefaultDlpf() { return true; }
bool Mpu6050::writeRegister(uint8_t, uint8_t) { return true; }

static std::string hex(const std::string &b) { static const char *h = "0123456789abcdef"; std::string o; for (unsigned char c : b) { o += h[c >> 4]; o += h[c & 15]; } return o; }
static std::string unhex(const std::string &s) { std::string o; for (size_t i = 0; i + 1 < s.size(); i += 2) o += (char)std::stoi(s.substr(i, 2), nullptr, 16); return o; }
static BLECharacteristic *find(const std::string &u) {
    for (auto *s : g_services) for (auto *c : s->chars) if (c->uuid == u && c->registered) return c;
    return nullptr;
}

int main() {
    g_onNotify = [](BLECharacteristic *c) { printf("N %s %s\n", c->uuid.c_str(), hex(c->value).c_str()); };
    setup();
    std::string line;
    while (std::getline(std::cin, line)) {
        std::istringstream in(line); std::string cmd, uuid, data; in >> cmd >> uuid >> data;
        if (cmd == "LIST") {
            printf("CHARS");
            for (auto *s : g_services) for (auto *c : s->chars) if (c->registered) printf(" %s", c->uuid.c_str());
            printf("\n");
        } else if (cmd == "READ") {
            auto *c = find(uuid); if (c) printf("VAL %s\n", hex(c->value).c_str()); else printf("ERR notfound\n");
        } else if (cmd == "WRITE") {
            auto *c = find(uuid);
            if (!c) printf("ERR notfound\n");
            else { c->value = unhex(data); if (c->cb) c->cb->onWrite(c); printf("OK\n"); }
        } else if (cmd == "RUN") {
            uint64_t end = g_now_us + (uint64_t)std::stoul(uuid) * 1000;
            while (g_now_us < end) { loop(); g_now_us += 100; }  // loop() a cada 100 us
            printf("END\n");
        } else if (cmd == "QUIT") break;
        fflush(stdout);
    }
}
