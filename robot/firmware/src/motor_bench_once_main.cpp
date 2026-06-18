#include <Arduino.h>
#include "motor_ctrl.h"

MotorController motor;

constexpr int TEST_SPEED = 220;
constexpr uint32_t ARM_DELAY_MS = 5000;
constexpr uint32_t RUN_MS = 1500;
constexpr uint32_t PAUSE_MS = 1000;

void holdMotorPinsLow() {
    const int8_t motorPins[] = {
        PIN_MOTOR_L_IN1,
        PIN_MOTOR_L_IN2,
        PIN_MOTOR_R_IN1,
        PIN_MOTOR_R_IN2,
    };

    for (int8_t pin : motorPins) {
        if (pin >= 0) {
            pinMode(pin, OUTPUT);
            digitalWrite(pin, LOW);
        }
    }
}

void runStep(const char* label, void (*drive)(int)) {
    Serial.printf("[BenchOnce] %s speed=%d for %lu ms\n",
                  label,
                  TEST_SPEED,
                  static_cast<unsigned long>(RUN_MS));
    drive(TEST_SPEED);
    delay(RUN_MS);
    motor.stop();
    delay(PAUSE_MS);
}

void driveForward(int speed) {
    motor.forward(speed);
}

void driveBackward(int speed) {
    motor.backward(speed);
}

void driveLeft(int speed) {
    motor.turnLeft(speed);
}

void driveRight(int speed) {
    motor.turnRight(speed);
}

void setup() {
    holdMotorPinsLow();

    Serial.begin(115200);
    delay(1000);

    Serial.println("[BenchOnce] Xiao-An motor front/back/left/right test");
    Serial.println("[BenchOnce] Wheels must be lifted. Cut motor power if anything looks wrong.");
    Serial.printf("[BenchOnce] Starting in %lu ms\n", static_cast<unsigned long>(ARM_DELAY_MS));

    motor.begin();
    motor.stop();
    delay(ARM_DELAY_MS);

    runStep("FORWARD: both wheels forward", driveForward);
    runStep("BACKWARD: both wheels backward", driveBackward);
    runStep("LEFT: left wheel backward, right wheel forward", driveLeft);
    runStep("RIGHT: left wheel forward, right wheel backward", driveRight);

    motor.stop();
    Serial.println("[BenchOnce] Done. Holding motors stopped.");
}

void loop() {
    motor.stop();
    delay(1000);
}
