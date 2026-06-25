#pragma once

#include <Arduino.h>

using OtaStartCallback = void (*)();

#if ENABLE_ARDUINO_OTA
void ota_set_on_start(OtaStartCallback callback);
void ota_begin(const char* hostname);
void ota_loop();
#else
inline void ota_set_on_start(OtaStartCallback) {}
inline void ota_begin(const char*) {}
inline void ota_loop() {}
#endif
