#include "BleServer.h"

#include <BLE2902.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <math.h>

#include "Config.h"

namespace {
BLECharacteristic *angleChar = nullptr;
BLECharacteristic *vibrationStatusChar = nullptr;
BLECharacteristic *vibrationDataChar = nullptr;
BleServer *self = nullptr;  // única instância — usada pelos callbacks estáticos do BLE

// Sinalizado pelo callback de desconexão e consumido no loop principal.
volatile bool restartAdvertisingPending = false;

class ServerCallbacks : public BLEServerCallbacks {
    void onDisconnect(BLEServer *) override {
        // O ESP32 PARA de anunciar assim que um cliente conecta, e a lib BLE
        // do Arduino não volta a anunciar sozinha quando ele desconecta — o
        // dispositivo simplesmente some do scan até ser resetado na mão.
        // Aparece ao reabrir o app (ou ao alternar entre as duas versões do
        // app) e parece hardware com defeito.
        //
        // Só marca aqui: quem realmente reinicia o anúncio é update(), no
        // loop principal. Este callback roda na task do stack BLE, e chamar
        // startAdvertising() de dentro dele, no meio do processamento da
        // desconexão, é justamente o caso em que essa chamada falha calada.
        restartAdvertisingPending = true;
    }
};

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
    server->setCallbacks(new ServerCallbacks());
    BLEService *service = server->createService(SERVICE_UUID);

    angleChar = service->createCharacteristic(
        CHAR_ANGLE_UUID, BLECharacteristic::PROPERTY_READ | BLECharacteristic::PROPERTY_NOTIFY
    );
    angleChar->addDescriptor(new BLE2902());

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
    _sensor.calibrate();
}

void BleServer::handleVibrationConfigWrite(uint16_t durationS, uint16_t rateHz) {
    if (_vibration.start(durationS, rateHz)) {
        _vibrationDataCursor = 0;
        _lastReportedVibrationStatus = VibrationCapture::Status::Capturing;
    }
}

void BleServer::notifyAngle() {
    uint32_t now = millis();
    if (now - _lastAngleNotifyMs < BLE_NOTIFY_INTERVAL_MS) {
        return;
    }
    _lastAngleNotifyMs = now;

    uint16_t raw = static_cast<uint16_t>(lroundf(_sensor.readAngleDeg() * ANGLE_SCALE));
    uint8_t payload[2] = {static_cast<uint8_t>(raw & 0xFF), static_cast<uint8_t>(raw >> 8)};
    angleChar->setValue(payload, 2);
    angleChar->notify();
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

    // status == Ready: primeiro esvazia todo o buffer de amostras (com
    // pacing entre pacotes) e só então notifica "pronto" na characteristic
    // de status. A ordem importa: o app (ble_source.py) considera a
    // captura concluída assim que recebe esse "pronto" — se ele chegasse
    // antes dos dados, o app leria um resultado truncado.
    uint16_t total = _vibration.sampleCount();
    if (_vibrationDataCursor < total) {
        if (now - _lastVibrationChunkMs < BLE_VIBRATION_CHUNK_INTERVAL_MS) {
            return;
        }
        _lastVibrationChunkMs = now;

        // Pacotes pequenos: o ATT MTU padrão do BLE (sem negociação) só
        // garante 20 bytes úteis por notificação — 2 bytes de índice + 8
        // amostras (16 bytes) = 18 bytes, cabe mesmo sem MTU maior negociado.
        constexpr uint16_t kSamplesPerPacket = 8;
        uint16_t remaining = total - _vibrationDataCursor;
        uint16_t chunk = remaining < kSamplesPerPacket ? remaining : kSamplesPerPacket;

        uint8_t payload[2 + kSamplesPerPacket * 2];
        payload[0] = static_cast<uint8_t>(_vibrationDataCursor & 0xFF);
        payload[1] = static_cast<uint8_t>(_vibrationDataCursor >> 8);
        for (uint16_t i = 0; i < chunk; i++) {
            int16_t sample = _vibration.sampleAt(_vibrationDataCursor + i);
            payload[2 + i * 2] = static_cast<uint8_t>(sample & 0xFF);
            payload[2 + i * 2 + 1] = static_cast<uint8_t>((sample >> 8) & 0xFF);
        }
        vibrationDataChar->setValue(payload, 2 + chunk * 2);
        vibrationDataChar->notify();
        _vibrationDataCursor += chunk;
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

void BleServer::update() {
    if (restartAdvertisingPending) {
        restartAdvertisingPending = false;
        BLEDevice::startAdvertising();
    }
    notifyAngle();
    updateVibrationNotify();
}
