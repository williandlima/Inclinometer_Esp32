#pragma once
#include <stdint.h>
#include <stddef.h>
#include <math.h>
extern uint64_t g_now_us;
inline uint32_t millis() { return (uint32_t)(g_now_us / 1000); }
inline uint32_t micros() { return (uint32_t)g_now_us; }
// Serial pode ser ligada a um transporte real pelo teste (modbus_sim.cpp liga
// num pseudo-terminal); sem ganchos, é um dreno mudo.
struct SerialHooks {
    int (*available)() = nullptr;
    int (*read)() = nullptr;
    size_t (*write)(const uint8_t *, size_t) = nullptr;
};
inline SerialHooks g_serialHooks;
class HardwareSerial {
public:
    void begin(unsigned long) {}
    int available() { return g_serialHooks.available ? g_serialHooks.available() : 0; }
    int read() { return g_serialHooks.read ? g_serialHooks.read() : -1; }
    size_t write(const uint8_t *d, size_t n) { return g_serialHooks.write ? g_serialHooks.write(d, n) : n; }
    void flush() {}
};
extern HardwareSerial Serial;
