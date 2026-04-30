#pragma once
// mic_stream.h - I2S microphone streaming to base station
// Author: 施宇灏

#include <Arduino.h>

class MicStream {
public:
    void begin();
    void streamLoop();     // call in main loop()
    bool isActive();

private:
    // TODO: define I2S pin constants (INMP441: BCK, WS, DATA)
    bool _active = false;
};
