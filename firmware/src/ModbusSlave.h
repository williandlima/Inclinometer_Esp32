#pragma once

#include <Arduino.h>

#include "AngleSensor.h"
#include "VibrationCapture.h"

// Escravo Modbus RTU sobre RS485 (UART2 + pino de direção DE/RE) — contrato
// documentado em python-app/data_source/modbus_source.py. Implementa só o
// necessário: função 0x04 (read input registers), 0x05 (write single coil)
// e 0x06 (write single register).
class ModbusSlave {
public:
    ModbusSlave(AngleSensor &sensor, VibrationCapture &vibration)
        : _sensor(sensor), _vibration(vibration) {}

    void begin();

    // Chamar a cada iteração do loop() — não bloqueante.
    void update();

private:
    AngleSensor &_sensor;
    VibrationCapture &_vibration;

    uint16_t _vibrationDurationS = 30;
    uint16_t _vibrationRateHz = 50;
    uint16_t _vibrationCursor = 0;

    uint8_t _frame[256];
    uint16_t _frameLen = 0;  // uint16_t de propósito: precisa exceder 255 pra comparação com sizeof(_frame) ter efeito
    uint32_t _lastByteMs = 0;

    void handleFrame();
    void handleReadInputRegisters(uint16_t startAddr, uint16_t count);
    void handleWriteCoil(uint16_t addr, uint16_t value);
    void handleWriteRegister(uint16_t addr, uint16_t value);
    void sendException(uint8_t functionCode, uint8_t exceptionCode);
    void sendResponse(const uint8_t *payload, uint8_t len);

    static uint16_t crc16(const uint8_t *data, uint8_t len);
};
