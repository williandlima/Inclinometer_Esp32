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
    static constexpr uint8_t REG_CONFIG = 0x1A;
    static constexpr uint8_t REG_ACCEL_CONFIG = 0x1C;
    static constexpr uint8_t REG_ACCEL_XOUT_H = 0x3B;
    static constexpr float ACCEL_SENSITIVITY_LSB_PER_G = 16384.0f;

    // Filtro passa-baixa digital interno do MPU6050 (registrador CONFIG,
    // campo DLPF_CFG). O padrão de fábrica é 0 = 260Hz de banda passante no
    // acelerômetro, ou seja, praticamente nenhum filtro: todo o ruído
    // mecânico/térmico de alta frequência entra em cada amostra e vira
    // tremulação de centésimos de grau na leitura de ângulo.
    //
    // DLPF_CFG=4 -> 21Hz de banda (atraso de ~8.5ms), que:
    // - corta a maior parte desse ruído já no hardware, antes de qualquer
    //   filtragem em software;
    // - serve de filtro anti-aliasing para o Modo Vibração: na taxa padrão
    //   de 50 amostras/s, Nyquist é 25Hz — com os 260Hz de fábrica, ruído
    //   acima disso era rebatido para dentro da faixa medida e sujava a FFT.
    // Ainda deixa passar com folga as frequências de interesse do ensaio
    // (balanço de mastro sob vento, tipicamente 1-5Hz).
    static constexpr uint8_t DLPF_CFG_21HZ = 0x04;

    // Fundo de escala do acelerômetro: +-2g (o mais sensível, ideal para
    // inclinação). É o padrão de fábrica, mas fica explícito para o driver
    // não depender do estado em que o chip foi encontrado.
    static constexpr uint8_t ACCEL_RANGE_2G = 0x00;

    bool writeRegister(uint8_t reg, uint8_t value);
};
