#pragma once

#include <Arduino.h>

// ============================================================================
// Configuração de hardware — pinagem definida para ESP32 DevKit clássico
// (WROOM-32). Ver firmware/README.md para o mapeamento completo (incluindo
// alimentação, AD0, terminação RS485) e as notas de nível lógico do módulo
// transceptor RS485.
// ============================================================================

// I2C do MPU6050 (padrão do ESP32 DevKit). AD0 do sensor deve ir para GND
// (endereço 0x68, o que o driver em Mpu6050.h assume).
constexpr int PIN_I2C_SDA = 21;
constexpr int PIN_I2C_SCL = 22;

// RS485, via módulo transceptor 3.3V-nativo (ex: MAX3485) — usa a UART2 do
// ESP32. DE e RE̅ do módulo ficam ligados juntos neste único pino de
// direção (HIGH = transmite/DE ativo, LOW = recebe/RE̅ ativo).
constexpr int PIN_RS485_RX = 16;  // <- RO do módulo RS485
constexpr int PIN_RS485_TX = 17;  // -> DI do módulo RS485
constexpr int PIN_RS485_DE_RE = 4;  // -> DE + RE̅ do módulo RS485 (juntos)

// ============================================================================
// Parâmetros Modbus RTU — devem bater com python-app/data_source/modbus_source.py
// ============================================================================
constexpr uint8_t MODBUS_SLAVE_ID = 1;
constexpr uint32_t MODBUS_BAUDRATE = 9600;

constexpr uint16_t REG_ANGLE_INPUT = 0;       // input register: ângulo * ANGLE_SCALE (uint16)
constexpr uint16_t COIL_CALIBRATE = 0;        // coil: write true -> zera o eixo de tilt
constexpr uint16_t COIL_VIBRATION_START = 1;  // coil: write true -> inicia captura de vibração

constexpr uint16_t REG_VIBRATION_DURATION = 10;  // holding register: duração da captura (s)
constexpr uint16_t REG_VIBRATION_RATE = 11;      // holding register: taxa de amostragem (Hz)

constexpr uint16_t REG_VIBRATION_STATUS = 20;       // input register: 0=ocioso,1=capturando,2=pronto,3=erro
constexpr uint16_t REG_VIBRATION_PROGRESS = 21;     // input register: percentual 0-100
constexpr uint16_t REG_VIBRATION_SAMPLE_COUNT = 22; // input register: total de amostras (quando pronto)

constexpr uint16_t REG_VIBRATION_CURSOR = 30;       // holding register: índice inicial do bloco a ler
constexpr uint16_t REG_VIBRATION_BLOCK_START = 31;  // input register: início do bloco de amostras
constexpr uint16_t VIBRATION_BLOCK_SIZE = 32;       // amostras por bloco de leitura

// ============================================================================
// Parâmetros BLE — devem bater com python-app/data_source/ble_source.py e
// android-app/.../datasource/BleContract.kt
// ============================================================================
constexpr char BLE_DEVICE_NAME[] = "Inclinometro-ESP32";
constexpr char SERVICE_UUID[] = "6e6e0001-3c17-4a2e-8f4b-1a2b3c4d5e6f";
constexpr char CHAR_ANGLE_UUID[] = "6e6e0002-3c17-4a2e-8f4b-1a2b3c4d5e6f";
constexpr char CHAR_CALIBRATE_UUID[] = "6e6e0003-3c17-4a2e-8f4b-1a2b3c4d5e6f";
constexpr char CHAR_VIBRATION_CONFIG_UUID[] = "6e6e0004-3c17-4a2e-8f4b-1a2b3c4d5e6f";
constexpr char CHAR_VIBRATION_STATUS_UUID[] = "6e6e0005-3c17-4a2e-8f4b-1a2b3c4d5e6f";
constexpr char CHAR_VIBRATION_DATA_UUID[] = "6e6e0006-3c17-4a2e-8f4b-1a2b3c4d5e6f";
constexpr uint32_t BLE_NOTIFY_INTERVAL_MS = 200;  // taxa de notificação do ângulo em modo contínuo

// ============================================================================
// Compartilhados entre os dois transportes
// ============================================================================
constexpr float ANGLE_SCALE = 100.0f;  // valor no protocolo = ângulo * ANGLE_SCALE
constexpr float ANGLE_MIN_DEG = 0.0f;
constexpr float ANGLE_MAX_DEG = 120.0f;
constexpr uint16_t VIBRATION_MAX_SAMPLES = 6000;  // limite de memória do buffer de captura
