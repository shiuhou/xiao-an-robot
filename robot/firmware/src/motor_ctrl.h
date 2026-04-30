#pragma once
// motor_ctrl.h - Differential drive motor controller
// Author: 施宇灏

#include <Arduino.h>

class MotorController {
public:
    void begin();
    void forward(int speed);
    void backward(int speed);
    void turnLeft(int speed);
    void turnRight(int speed);
    void stop();
    void execute(const char* action, float param = 0.0f);

private:
    // TODO: add motor driver pin definitions (e.g. DRV8833 or L298N)
};
