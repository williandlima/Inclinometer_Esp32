#include "BleServer.h"

#include <BLE2902.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <math.h>

#include "Config.h"

namespace {
BLECharacteristic *angleChar = nullptr;
BLECharacteristic *panChar = nullptr;
BLECharacteristic *vibrationStatusChar = nullptr;
BLECharacteristic *vibrationDataChar = nullptr;
BLECharacteristic *vibrationPanDataChar = nullptr;
BleServer *self = nullptr;  // única instância — usada pelos callbacks estáticos do BLE

class CalibrateCallbacks : public BLECharacteristicCallbacks {
    void onWrite(BLECharacteristic *characteristic) override {
        std::string value = characteristic->getValue();
        if (!value.empty() && static_cast<uint8_t>(value[0]) == 0x01 && self != nullptr) {
            self->handleCalibrateWrite();
        }
    }
};

class VibrationConfigCallbacks : public BLECharacteristicCallbacks {
    void onWrite(BLECharacteristic *characteristic) override {
        std::string value = characteristic->getValue();
        if (value.size() < 4 || self == nullptr) {
            return;
        }
        uint16_t durationS = static_cast<uint8_t>(value[0]) | (static_cast<uint16_t>(static_cast<uint8_t>(value[1])) << 8);
        uint16_t rateHz = static_cast<uint8_t>(value[2]) | (static_cast<uint16_t>(static_cast<uint8_t>(value[3])) << 8);
        self->handleVibrationConfigWrite(durationS, rateHz);
    }
};
}  // namespace

void BleServer::begin() {
    self = this;

    BLEDevice::init(BLE_DEVICE_NAME);
    BLEDevice::setMTU(247);  // best-effort: reduz o nº de pacotes se o central negociar MTU maior
    BLEServer *server = BLEDevice::createServer();
    BLEService *service = server->createService(SERVICE_UUID);

    angleChar = service->createCharacteristic(
        CHAR_ANGLE_UUID, BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_NOTIFY
    );
    angleChar->addDescriptor(new BLE2902());

    panChar = service->createCharacteristic(
        CHAR_PAN_UUID, BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_NOTIFY
    );
    panChar->addDescriptor(new BLE2902());

    BLECharacteristic *calibrateChar =
        service->createCharacteristic(CHAR_CALIBRATE_UUID, BLECharacteristic::PROPERTY_WRITE);
    calibrateChar->setCallbacks(new CalibrateCallbacks());

    BLECharacteristic *vibrationConfigChar =
        service->createCharacteristic(CHAR_VIBRATION_CONFIG_UUID, BLECharacteristic::PROPERTY_WRITE);
    vibrationConfigChar->setCallbacks(new VibrationConfigCallbacks());

    vibrationStatusChar =
        service->createCharacteristic(CHAR_VIBRATION_STATUS_UUID, BLECharacteristic::PROPERTY_NOTIFY);
    vibrationStatusChar->addDescriptor(new BLE2902());

    vibrationDataChar =
        service->createCharacteristic(CHAR_VIBRATION_DATA_UUID, BLECharacteristic::PROPERTY_NOTIFY);
    vibrationDataChar->addDescriptor(new BLE2902());

    vibrationPanDataChar =
        service->createCharacteristic(CHAR_VIBRATION_PAN_DATA_UUID, BLECharacteristic::PROPERTY_NOTIFY);
    vibrationPanDataChar->addDescriptor(new BLE2902());

    BLECharacteristic *firmwareVersionChar =
        service->createCharacteristic(CHAR_FIRMWARE_VERSION_UUID, BLECharacteristic::PROPERTY_READ);
    uint8_t versionPayload[2] = {
        static_cast<uint8_t>(FIRMWARE_VERSION_CODE & 0xFF),
        static_cast<uint8_t>(FIRMWARE_VERSION_CODE >> 8),
    };
    firmwareVersionChar->setValue(versionPayload, 2);

    service->start();

    BLEAdvertising *advertising = BLEDevice::getAdvertising();
    advertising->addServiceUUID(SERVICE_UUID);
    advertising->start();
}

void BleServer::handleCalibrateWrite() {
    // Uma ação de calibração zera os DOIS eixos: é o que os apps expõem como
    // um único botão "Calibrar".
    _sensor.calibrate();
    _pan.calibrate();
}

void BleServer::handleVibrationConfigWrite(uint16_t durationS, uint16_t rateHz) {
    if (_vibration.start(durationS, rateHz)) {
        _vibrationDataCursor = 0;
        _vibrationPanDataCursor = 0;
        _lastReportedVibrationStatus = VibrationCapture::Status::Capturing;
    }
}

void BleServer::notifyAngles() {
    uint32_t now = millis();
    if (now - _lastAngleNotifyMs < BLE_NOTIFY_INTERVAL_MS) {
        return;
    }
    _lastAngleNotifyMs = now;

    uint16_t rawAngle = static_cast<uint16_t>(lroundf(_sensor.readAngleDeg() * ANGLE_SCALE));
    uint8_t anglePayload[2] = {
        static_cast<uint8_t>(rawAngle & 0xFF),
        static_cast<uint8_t>(rawAngle >> 8),
    };
    angleChar->setValue(anglePayload, 2);
    angleChar->notify();

    uint16_t rawPan = static_cast<uint16_t>(lroundf(_pan.readPanDeg() * ANGLE_SCALE));
    uint8_t panPayload[2] = {
        static_cast<uint8_t>(rawPan & 0xFF),
        static_cast<uint8_t>(rawPan >> 8),
    };
    panChar->setValue(panPayload, 2);
    panChar->notify();
}

void BleServer::updateVibrationNotify() {
    VibrationCapture::Status status = _vibration.status();
    uint32_t now = millis();

    if (status == VibrationCapture::Status::Idle) {
        _lastReportedVibrationStatus = VibrationCapture::Status::Idle;
        return;
    }

    if (status == VibrationCapture::Status::Capturing) {
        // Throttled: sem isso, notify() seria chamado a cada iteração do
        // loop() (milhares de vezes/segundo) e sobrecarregaria a fila BLE.
        bool justStarted = _lastReportedVibrationStatus != VibrationCapture::Status::Capturing;
        if (justStarted || now - _lastVibrationStatusNotifyMs >= BLE_VIBRATION_STATUS_NOTIFY_INTERVAL_MS) {
            uint8_t payload[2] = {static_cast<uint8_t>(status), _vibration.progressPercent()};
            vibrationStatusChar->setValue(payload, 2);
            vibrationStatusChar->notify();
            _lastVibrationStatusNotifyMs = now;
        }
        _lastReportedVibrationStatus = status;
        return;
    }

    if (status == VibrationCapture::Status::Error) {
        if (_lastReportedVibrationStatus != VibrationCapture::Status::Error) {
            uint8_t payload[2] = {static_cast<uint8_t>(status), 0};
            vibrationStatusChar->setValue(payload, 2);
            vibrationStatusChar->notify();
            _lastReportedVibrationStatus = status;
        }
        return;
    }

    // status == Ready: primeiro esvazia os DOIS buffers de amostras (com
    // pacing entre pacotes) e só então notifica "pronto" na characteristic
    // de status. A ordem importa: o app (ble_source.py) considera a
    // captura concluída assim que recebe esse "pronto" — se ele chegasse
    // antes dos dados, o app leria um resultado truncado. Tilt primeiro,
    // pan depois, mas o "pronto" só sai quando os dois terminarem.
    uint16_t total = _vibration.sampleCount();
    if (_vibrationDataCursor < total || _vibrationPanDataCursor < total) {
        if (now - _lastVibrationChunkMs < BLE_VIBRATION_CHUNK_INTERVAL_MS) {
            return;
        }
        _lastVibrationChunkMs = now;

        if (_vibrationDataCursor < total) {
            sendVibrationChunk(vibrationDataChar, _vibrationDataCursor, total, false);
        } else {
            sendVibrationChunk(vibrationPanDataChar, _vibrationPanDataCursor, total, true);
        }
        return;
    }

    if (_lastReportedVibrationStatus != VibrationCapture::Status::Ready) {
        uint8_t payload[4] = {
            static_cast<uint8_t>(status),
            100,
            static_cast<uint8_t>(total & 0xFF),
            static_cast<uint8_t>(total >> 8),
        };
        vibrationStatusChar->setValue(payload, 4);
        vibrationStatusChar->notify();
        _lastReportedVibrationStatus = status;
    }
}

void BleServer::sendVibrationChunk(
    BLECharacteristic *characteristic, uint16_t &cursor, uint16_t total, bool pan
) {
    // Pacotes pequenos: o ATT MTU padrão do BLE (sem negociação) só garante
    // 20 bytes úteis por notificação — 2 bytes de índice + 8 amostras (16
    // bytes) = 18 bytes, cabe mesmo sem MTU maior negociado.
    constexpr uint16_t kSamplesPerPacket = 8;
    uint16_t remaining = total - cursor;
    uint16_t chunk = remaining < kSamplesPerPacket ? remaining : kSamplesPerPacket;

    uint8_t payload[2 + kSamplesPerPacket * 2];
    payload[0] = static_cast<uint8_t>(cursor & 0xFF);
    payload[1] = static_cast<uint8_t>(cursor >> 8);
    for (uint16_t i = 0; i < chunk; i++) {
        int16_t sample = pan ? _vibration.panSampleAt(cursor + i) : _vibration.sampleAt(cursor + i);
        payload[2 + i * 2] = static_cast<uint8_t>(sample & 0xFF);
        payload[2 + i * 2 + 1] = static_cast<uint8_t>((sample >> 8) & 0xFF);
    }
    characteristic->setValue(payload, 2 + chunk * 2);
    characteristic->notify();
    cursor += chunk;
}

void BleServer::update() {
    notifyAngles();
    updateVibrationNotify();
}
