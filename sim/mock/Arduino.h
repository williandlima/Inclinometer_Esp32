#pragma once
#include <stdint.h>
#include <stddef.h>
#include <math.h>
extern uint64_t g_now_us;
inline uint32_t millis() { return (uint32_t)(g_now_us / 1000); }
inline uint32_t micros() { return (uint32_t)g_now_us; }
class HardwareSerial {
public:
    void begin(unsigned long) {}
    int available() { return 0; }
    int read() { return -1; }
    size_t write(const uint8_t *, size_t n) { return n; }
    void flush() {}
};
extern HardwareSerial Serial;
