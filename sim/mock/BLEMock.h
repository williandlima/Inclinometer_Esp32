#pragma once
// Mock minimo da lib BLE (Bluedroid) do Arduino-ESP32, reproduzindo a
// contabilidade de handles GATT: servico=1, characteristic=2, descritor=+1,
// e o default numHandles=15 de BLEServer::createService.
#include <stdint.h>
#include <string>
#include <vector>
#include <functional>

class BLECharacteristic;
class BLEServer;
struct BLEUUID { std::string s; BLEUUID(const char *u) : s(u) {} };
class BLEDescriptor { public: virtual ~BLEDescriptor() {} };
class BLE2902 : public BLEDescriptor {};
class BLECharacteristicCallbacks { public: virtual ~BLECharacteristicCallbacks() {} virtual void onWrite(BLECharacteristic *) {} };
class BLEServerCallbacks { public: virtual ~BLEServerCallbacks() {} virtual void onConnect(BLEServer *) {} virtual void onDisconnect(BLEServer *) {} };

class BLECharacteristic {
public:
    static const uint32_t PROPERTY_READ = 1, PROPERTY_WRITE = 2, PROPERTY_NOTIFY = 4;
    std::string uuid; uint32_t props; int descriptors = 0; bool registered = false;
    std::string value; BLECharacteristicCallbacks *cb = nullptr;
    BLECharacteristic(const char *u, uint32_t p) : uuid(u), props(p) {}
    void addDescriptor(BLEDescriptor *) { descriptors++; }
    void setCallbacks(BLECharacteristicCallbacks *c) { cb = c; }
    void setValue(uint8_t *d, size_t n) { value.assign((const char *)d, n); }
    std::string getValue() { return value; }
    void notify();
};
extern std::function<void(BLECharacteristic *)> g_onNotify;
inline void BLECharacteristic::notify() { if (registered && g_onNotify) g_onNotify(this); }

class BLEService {
public:
    uint32_t numHandles; std::vector<BLECharacteristic *> chars;
    explicit BLEService(uint32_t n) : numHandles(n) {}
    BLECharacteristic *createCharacteristic(const char *u, uint32_t p) { auto *c = new BLECharacteristic(u, p); chars.push_back(c); return c; }
    void start() {
        uint32_t used = 1;  // declaracao do servico
        for (auto *c : chars) {
            uint32_t need = 2 + c->descriptors;
            if (used + need <= numHandles) { used += need; c->registered = true; }
        }
    }
};
extern std::vector<BLEService *> g_services;
class BLEServer {
public:
    void setCallbacks(BLEServerCallbacks *) {}
    BLEService *createService(const char *uuid) { return createService(BLEUUID(uuid)); }
    BLEService *createService(BLEUUID, uint32_t numHandles = 15, uint8_t = 0) { auto *s = new BLEService(numHandles); g_services.push_back(s); return s; }
};
class BLEAdvertising { public: void addServiceUUID(const char *) {} void start() {} };
class BLEDevice {
public:
    static void init(const char *) {}
    static void setMTU(int) {}
    static BLEServer *createServer() { static BLEServer s; return &s; }
    static BLEAdvertising *getAdvertising() { static BLEAdvertising a; return &a; }
    static void startAdvertising() {}
};
