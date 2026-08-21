#include "ModbusSlave.h"

#include <math.h>
#include <string.h>

#include "Config.h"

namespace {
// UART0 — a mesma porta serial usada para gravar o firmware, exposta como
// porta USB/COM direto pelo chip USB-UART embutido do ESP32. Full-duplex,
// então (diferente de RS485) não precisa de nenhum controle de direção.
// Nome evita "link" de propósito: colide com o `int link(const char*,
// const char*)` de sys/unistd.h (chega via <functional> -> HardwareSerial.h),
// dando "reference to 'link' is ambiguous" na hora de compilar.
HardwareSerial &modbusSerial = Serial;
}  // namespace

void ModbusSlave::begin() {
    modbusSerial.begin(MODBUS_BAUDRATE);
}

void ModbusSlave::update() {
    while (modbusSerial.available()) {
        if (_frameLen < sizeof(_frame)) {
            _frame[_frameLen++] = modbusSerial.read();
        } else {
            modbusSerial.read();  // descarta, frame maior que o esperado
        }
        _lastByteMs = millis();
    }

    // Fim de frame Modbus RTU: silêncio de ~3.5 caracteres. Simplificado
    // aqui para um timeout fixo, suficiente nas baudrates usadas no projeto.
    if (_frameLen > 0 && millis() - _lastByteMs > 5) {
        handleFrame();
        _frameLen = 0;
    }
}

void ModbusSlave::handleFrame() {
    if (_frameLen < 4) {
        return;  // frame curto demais pra ser válido
    }
    uint16_t receivedCrc = _frame[_frameLen - 2] | (_frame[_frameLen - 1] << 8);
    uint16_t computedCrc = crc16(_frame, _frameLen - 2);
    if (receivedCrc != computedCrc) {
        return;  // CRC inválido, ignora o frame
    }

    uint8_t slaveId = _frame[0];
    if (slaveId != MODBUS_SLAVE_ID) {
        return;  // não é pra este escravo
    }
    if (_frameLen < 8) {
        return;  // frame válido em CRC mas curto demais pra ter endereço+dado
    }

    uint8_t functionCode = _frame[1];
    uint16_t addr = (_frame[2] << 8) | _frame[3];
    uint16_t value = (_frame[4] << 8) | _frame[5];

    switch (functionCode) {
        case 0x04:
            handleReadInputRegisters(addr, value);
            break;
        case 0x05:
            handleWriteCoil(addr, value);
            break;
        case 0x06:
            handleWriteRegister(addr, value);
            break;
        default:
            sendException(functionCode, 0x01);  // função não suportada
            break;
    }
}

void ModbusSlave::handleReadInputRegisters(uint16_t startAddr, uint16_t count) {
    if (count == 0 || count > 125) {
        sendException(0x04, 0x03);  // valor de dado inválido
        return;
    }

    uint16_t values[125];
    for (uint16_t i = 0; i < count; i++) {
        uint16_t addr = startAddr + i;
        if (addr == REG_ANGLE_INPUT) {
            values[i] = static_cast<uint16_t>(lroundf(_sensor.readAngleDeg() * ANGLE_SCALE));
        } else if (addr == REG_PAN_INPUT) {
            values[i] = static_cast<uint16_t>(lroundf(_pan.readPanDeg() * ANGLE_SCALE));
        } else if (addr == REG_VIBRATION_STATUS) {
            values[i] = static_cast<uint16_t>(_vibration.status());
        } else if (addr == REG_VIBRATION_PROGRESS) {
            values[i] = _vibration.progressPercent();
        } else if (addr == REG_VIBRATION_SAMPLE_COUNT) {
            values[i] = _vibration.sampleCount();
        } else if (addr == REG_FIRMWARE_VERSION) {
            values[i] = FIRMWARE_VERSION_CODE;
        } else if (addr >= REG_VIBRATION_BLOCK_START && addr < REG_VIBRATION_BLOCK_START + VIBRATION_BLOCK_SIZE) {
            uint16_t sampleIndex = _vibrationCursor + (addr - REG_VIBRATION_BLOCK_START);
            values[i] = static_cast<uint16_t>(_vibration.sampleAt(sampleIndex));
        } else if (addr >= REG_VIBRATION_PAN_BLOCK_START && addr < REG_VIBRATION_PAN_BLOCK_START + VIBRATION_BLOCK_SIZE) {
            uint16_t sampleIndex = _vibrationCursor + (addr - REG_VIBRATION_PAN_BLOCK_START);
            values[i] = static_cast<uint16_t>(_vibration.panSampleAt(sampleIndex));
        } else {
            sendException(0x04, 0x02);  // endereço inválido
            return;
        }
    }

    uint8_t payload[3 + 125 * 2];
    payload[0] = MODBUS_SLAVE_ID;
    payload[1] = 0x04;
    payload[2] = static_cast<uint8_t>(count * 2);
    for (uint16_t i = 0; i < count; i++) {
        payload[3 + i * 2] = values[i] >> 8;
        payload[3 + i * 2 + 1] = values[i] & 0xFF;
    }
    sendResponse(payload, static_cast<uint8_t>(3 + count * 2));
}

void ModbusSlave::handleWriteCoil(uint16_t addr, uint16_t value) {
    bool on = (value == 0xFF00);
    if (addr == COIL_CALIBRATE) {
        if (on) {
            // Uma ação de calibração zera os DOIS eixos: é o que os apps
            // expõem como um único botão "Calibrar".
            _sensor.calibrate();
            _pan.calibrate();
        }
    } else if (addr == COIL_VIBRATION_START) {
        if (on) {
            _vibration.start(_vibrationDurationS, _vibrationRateHz);
        }
    } else {
        sendException(0x05, 0x02);
        return;
    }

    uint8_t payload[6];
    payload[0] = MODBUS_SLAVE_ID;
    payload[1] = 0x05;
    payload[2] = addr >> 8;
    payload[3] = addr & 0xFF;
    payload[4] = value >> 8;
    payload[5] = value & 0xFF;
    sendResponse(payload, 6);
}

void ModbusSlave::handleWriteRegister(uint16_t addr, uint16_t value) {
    if (addr == REG_VIBRATION_DURATION) {
        _vibrationDurationS = value;
    } else if (addr == REG_VIBRATION_RATE) {
        _vibrationRateHz = value;
    } else if (addr == REG_VIBRATION_CURSOR) {
        _vibrationCursor = value;
    } else {
        sendException(0x06, 0x02);
        return;
    }

    uint8_t payload[6];
    payload[0] = MODBUS_SLAVE_ID;
    payload[1] = 0x06;
    payload[2] = addr >> 8;
    payload[3] = addr & 0xFF;
    payload[4] = value >> 8;
    payload[5] = value & 0xFF;
    sendResponse(payload, 6);
}

void ModbusSlave::sendException(uint8_t functionCode, uint8_t exceptionCode) {
    uint8_t payload[3];
    payload[0] = MODBUS_SLAVE_ID;
    payload[1] = functionCode | 0x80;
    payload[2] = exceptionCode;
    sendResponse(payload, 3);
}

void ModbusSlave::sendResponse(const uint8_t *payload, uint8_t len) {
    uint8_t frame[3 + 125 * 2 + 2];
    memcpy(frame, payload, len);
    uint16_t crc = crc16(payload, len);
    frame[len] = crc & 0xFF;
    frame[len + 1] = crc >> 8;

    modbusSerial.write(frame, len + 2);
    modbusSerial.flush();
}

uint16_t ModbusSlave::crc16(const uint8_t *data, uint8_t len) {
    uint16_t crc = 0xFFFF;
    for (uint8_t pos = 0; pos < len; pos++) {
        crc ^= data[pos];
        for (uint8_t i = 0; i < 8; i++) {
            if (crc & 0x0001) {
                crc >>= 1;
                crc ^= 0xA001;
            } else {
                crc >>= 1;
            }
        }
    }
    return crc;
}
