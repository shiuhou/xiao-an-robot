#pragma once

#include <Arduino.h>
#include "feature_flags.h"

class WSClient;

class CamStream {
public:
    void begin();
#if ENABLE_WS_INTEGRATED
    void captureLoop(WSClient& ws);
#else
    void captureLoop();
#endif
    bool isActive();

private:
    bool     _active      = false;
    uint32_t _lastCapture = 0;
    uint32_t _captureOk   = 0;
    uint32_t _captureFail = 0;
#if ENABLE_WS_INTEGRATED
    uint32_t _frameId = 0;
    static constexpr uint32_t CAPTURE_INTERVAL_MS = 1000;
#else
    static constexpr uint32_t CAPTURE_INTERVAL_MS = 2000;
#endif
};
