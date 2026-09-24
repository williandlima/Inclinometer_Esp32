#pragma once
// Mock da Wire do Arduino-ESP32: o barramento I2C é implementado pelo teste
// (soak_sim.cpp), que emula o MPU6050 no nível de registrador e injeta
// falhas. Assim o driver REAL (firmware/src/Mpu6050.cpp) é exercitado.
#include "Arduino.h"

class TwoWire {
public:
    bool begin(int sda = -1, int scl = -1, uint32_t freq = 0);
    void setClock(uint32_t hz);
    bool end();
    void beginTransmission(uint8_t address);
    size_t write(uint8_t b);
    uint8_t endTransmission(bool sendStop = true);
    uint8_t requestFrom(uint8_t address, uint8_t quantity);
    int read();
};
extern TwoWire Wire;
