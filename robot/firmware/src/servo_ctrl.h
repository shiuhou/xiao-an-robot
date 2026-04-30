#pragma once
// servo_ctrl.h - Servo controller for head tilt and ear wiggle
// Author: 施宇灏

#include <Arduino.h>

class ServoController {
public:
    void begin();
    void setHeadTilt(int angle);
    void wiggleEars(int count);
    void nodHead(int times);
    void centerAll();

private:
    // TODO: define servo pin constants and Servo objects (ESP32Servo)
};
