#pragma once

#include <stdint.h>

// Driver mínimo para o MPU6050 via I2C (sem biblioteca externa).
// Registradores e escalas default (acelerômetro +-2g, 16384 LSB/g;
// giroscópio +-250°/s, 131 LSB/°/s) conforme o datasheet do MPU6050.
//
// Dois caminhos de leitura, para dois consumidores diferentes:
// - readAccelG(): só o acelerômetro (6 bytes), usado pelo AngleSensor para
//   o tilt e pela captura de vibração — é o caminho mais curto no
//   barramento, chamado nas taxas mais altas do firmware;
// - readMotion(): acelerômetro + giroscópio num burst único (14 bytes),
//   usado pelo PanSensor. O burst único importa: a compensação de tilt da
//   taxa de pan combina accel e giro, e os dois precisam ser da MESMA
//   amostra — duas transações separadas dariam instantes diferentes.
class Mpu6050 {
public:
    bool begin();

    // Preenche ax, ay, az em unidades de g. Retorna false em falha de I2C.
    bool readAccelG(float &ax, float &ay, float &az);

    // Preenche acelerômetro (g) e giroscópio (graus/s) da mesma amostra,
    // num único burst I2C. Retorna false em falha de I2C.
    bool readMotion(float &ax, float &ay, float &az, float &gxDps, float &gyDps, float &gzDps);

private:
    static constexpr uint8_t I2C_ADDRESS = 0x68;
    static constexpr uint8_t REG_PWR_MGMT_1 = 0x6B;
    static constexpr uint8_t REG_CONFIG = 0x1A;
    static constexpr uint8_t REG_GYRO_CONFIG = 0x1B;
    static constexpr uint8_t REG_ACCEL_CONFIG = 0x1C;
    static constexpr uint8_t REG_ACCEL_XOUT_H = 0x3B;
    static constexpr float ACCEL_SENSITIVITY_LSB_PER_G = 16384.0f;
    static constexpr float GYRO_SENSITIVITY_LSB_PER_DPS = 131.0f;

    // Bloco contíguo a partir de REG_ACCEL_XOUT_H: 6 bytes de acelerômetro,
    // 2 de temperatura e 6 de giroscópio. A temperatura fica no meio e não
    // pode ser pulada — por isso o burst é de 14 bytes e não de 12.
    static constexpr uint8_t MOTION_BURST_LEN = 14;

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

    // Fundo de escala do giroscópio: +-250°/s, o mais sensível (131 LSB/°/s).
    // Sobra folga de sobra para o caso de uso: o motor do pan gira a ~20-30°/s
    // e a vibração do mastro sob vento fica na casa de 1°/s. Escolher uma
    // faixa maior só jogaria fora resolução.
    static constexpr uint8_t GYRO_RANGE_250DPS = 0x00;

    bool writeRegister(uint8_t reg, uint8_t value);
};
