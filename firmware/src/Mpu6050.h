#pragma once

#include <stdint.h>

// Driver mínimo para o MPU6050 via I2C (sem biblioteca externa) — lê apenas
// o acelerômetro, suficiente para o cálculo de inclinação (tilt) por
// atan2. Registrador e escala default (faixa +-2g, sensibilidade
// 16384 LSB/g) conforme o datasheet do MPU6050.
class Mpu6050 {
public:
    bool begin();

    // Preenche ax, ay, az em unidades de g. Retorna false em falha de I2C.
    bool readAccelG(float &ax, float &ay, float &az);

private:
    static constexpr uint8_t I2C_ADDRESS = 0x68;
    static constexpr uint8_t REG_PWR_MGMT_1 = 0x6B;
    static constexpr uint8_t REG_ACCEL_XOUT_H = 0x3B;
    static constexpr float ACCEL_SENSITIVITY_LSB_PER_G = 16384.0f;

    bool writeRegister(uint8_t reg, uint8_t value);
};
