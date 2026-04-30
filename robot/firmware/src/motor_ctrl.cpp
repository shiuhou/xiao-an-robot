#include "motor_ctrl.h"

void MotorController::begin() {
    // TODO: configure motor driver pins (e.g. DRV8833 or L298N)
}

void MotorController::forward(int speed) {
    // TODO: set PWM to drive both wheels forward
}

void MotorController::backward(int speed) {
    // TODO: set PWM to drive both wheels backward
}

void MotorController::turnLeft(int speed) {
    // TODO: right wheel forward, left wheel stop/reverse
}

void MotorController::turnRight(int speed) {
    // TODO: left wheel forward, right wheel stop/reverse
}

void MotorController::stop() {
    // TODO: set all motor PWM to 0
}

void MotorController::execute(const char* action, float param) {
    // TODO: map MotionAction strings to motor commands
}
