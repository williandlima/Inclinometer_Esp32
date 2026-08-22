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
    if (!writeRegister(REG_ACCEL_CONFIG, ACCEL_RANGE_2G)) {
        return false;
    }
    return writeRegister(REG_GYRO_CONFIG, GYRO_RANGE_250DPS);
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

bool Mpu6050::readMotion(float &ax, float &ay, float &az, float &gxDps, float &gyDps, float &gzDps) {
    Wire.beginTransmission(I2C_ADDRESS);
    Wire.write(REG_ACCEL_XOUT_H);
    if (Wire.endTransmission(false) != 0) {
        return false;
    }
    if (Wire.requestFrom(I2C_ADDRESS, static_cast<uint8_t>(MOTION_BURST_LEN)) != MOTION_BURST_LEN) {
        return false;
    }

    // Bytes vão para um buffer antes de serem combinados, de propósito: em
    // `(Wire.read() << 8) | Wire.read()` a ordem de avaliação dos dois lados
    // do `|` não é garantida pelo padrão C++, então os bytes poderiam sair
    // trocados dependendo do compilador.
    uint8_t buffer[MOTION_BURST_LEN];
    for (uint8_t i = 0; i < MOTION_BURST_LEN; i++) {
        buffer[i] = static_cast<uint8_t>(Wire.read());
    }

    int16_t rawAx = static_cast<int16_t>((buffer[0] << 8) | buffer[1]);
    int16_t rawAy = static_cast<int16_t>((buffer[2] << 8) | buffer[3]);
    int16_t rawAz = static_cast<int16_t>((buffer[4] << 8) | buffer[5]);
    // buffer[6..7] = temperatura, não usada (ver MOTION_BURST_LEN em Mpu6050.h)
    int16_t rawGx = static_cast<int16_t>((buffer[8] << 8) | buffer[9]);
    int16_t rawGy = static_cast<int16_t>((buffer[10] << 8) | buffer[11]);
    int16_t rawGz = static_cast<int16_t>((buffer[12] << 8) | buffer[13]);

    ax = rawAx / ACCEL_SENSITIVITY_LSB_PER_G;
    ay = rawAy / ACCEL_SENSITIVITY_LSB_PER_G;
    az = rawAz / ACCEL_SENSITIVITY_LSB_PER_G;
    gxDps = rawGx / GYRO_SENSITIVITY_LSB_PER_DPS;
    gyDps = rawGy / GYRO_SENSITIVITY_LSB_PER_DPS;
    gzDps = rawGz / GYRO_SENSITIVITY_LSB_PER_DPS;
    return true;
}
