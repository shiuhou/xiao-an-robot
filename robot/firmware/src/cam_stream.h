#pragma once

#include <Arduino.h>

class CamStream {
public:
    void begin();
    void captureLoop();
    bool isActive();

private:
    bool     _active      = false;
    uint32_t _lastCapture = 0;
    uint32_t _captureOk   = 0;
    uint32_t _captureFail = 0;

    static constexpr uint32_t CAPTURE_INTERVAL_MS = 2000;
};
