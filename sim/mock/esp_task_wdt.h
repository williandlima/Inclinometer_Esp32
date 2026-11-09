#pragma once
// Watchdog de tarefa falso: conta as chamadas, para o teste conferir que o
// loop o alimenta.
#include <stdint.h>
#define ESP_IDF_VERSION_MAJOR 4
inline int g_wdtInits = 0, g_wdtAdds = 0, g_wdtResets = 0;
inline uint32_t g_wdtTimeoutS = 0;
inline int esp_task_wdt_init(uint32_t timeoutS, bool) { g_wdtInits++; g_wdtTimeoutS = timeoutS; return 0; }
inline int esp_task_wdt_add(void *) { g_wdtAdds++; return 0; }
inline int esp_task_wdt_reset() { g_wdtResets++; return 0; }
