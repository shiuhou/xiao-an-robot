#pragma once
// cam_stream.h - OV2640 camera streaming to base station
// Author: 施宇灏

#include <Arduino.h>

class CamStream {
public:
    void begin();
    void captureLoop();    // call in main loop()
    bool isActive();

private:
    // TODO: define camera pin constants for OV2640 on ESP32-S3
    bool     _active       = false;
    uint32_t _lastCapture  = 0;
    static constexpr uint32_t CAPTURE_INTERVAL_MS = 5000;  // 0.2 fps
};
