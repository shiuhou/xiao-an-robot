#pragma once

#include <Arduino.h>
#include "feature_flags.h"

class WSClient;

class MicStream {
public:
    void begin();
#if ENABLE_WS_INTEGRATED
    void streamLoop(WSClient& ws);
#else
    void streamLoop();
#endif
    bool isActive();

private:
    bool _active = false;
#if ENABLE_WS_INTEGRATED
    uint32_t _chunkId = 0;
    uint32_t _lastSendMs = 0;
#endif
};
