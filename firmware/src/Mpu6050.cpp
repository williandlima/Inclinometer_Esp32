#include "Mpu6050.h"

#include <Wire.h>

#include "Config.h"

bool Mpu6050::begin() {
    Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL);
    // Sai do modo sleep (padrão de fábrica) e usa o clock interno.
    if (!writeRegister(REG_PWR_MGMT_1, 0x00)) {
        return false;
    }
    // Liga o filtro passa-baixa interno e fixa o fundo de escala — ver a
    // justificativa de cada valor em Mpu6050.h.
    if (!writeRegister(REG_CONFIG, DLPF_CFG_21HZ)) {
        return false;
    }
    return writeRegister(REG_ACCEL_CONFIG, ACCEL_RANGE_2G);
}

bool Mpu6050::writeRegister(uint8_t reg, uint8_t value) {
    Wire.beginTransmission(I2C_ADDRESS);
    Wire.write(reg);
    Wire.write(value);
    return Wire.endTransmission() == 0;
}

bool Mpu6050::readAccelG(float &ax, float &ay, float &az) {
    Wire.beginTransmission(I2C_ADDRESS);
    Wire.write(REG_ACCEL_XOUT_H);
    if (Wire.endTransmission(false) != 0) {
        return false;
    }
    if (Wire.requestFrom(I2C_ADDRESS, static_cast<uint8_t>(6)) != 6) {
        return false;
    }

    int16_t rawX = (Wire.read() << 8) | Wire.read();
    int16_t rawY = (Wire.read() << 8) | Wire.read();
    int16_t rawZ = (Wire.read() << 8) | Wire.read();

    ax = rawX / ACCEL_SENSITIVITY_LSB_PER_G;
    ay = rawY / ACCEL_SENSITIVITY_LSB_PER_G;
    az = rawZ / ACCEL_SENSITIVITY_LSB_PER_G;
    return true;
}
