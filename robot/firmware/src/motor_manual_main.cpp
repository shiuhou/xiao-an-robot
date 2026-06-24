#include <Arduino.h>
#include "motor_ctrl.h"

MotorController motor;

constexpr int MOTOR_MANUAL_SPEED_MIN = 40;
constexpr int MOTOR_MANUAL_SPEED_MAX = 150;
constexpr int MOTOR_MANUAL_SPEED_STEP = 15;
constexpr uint32_t MOTOR_MANUAL_TIMEOUT_MS = 50;

int motorManualSpeed = 220;
uint32_t motorManualUntilMs = 0;
bool motorManualActive = false;
uint32_t lastSafeHoldPrintMs = 0;

void holdMotorPinsLowBeforeSerial() {
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

void printMotorManualHelp() {
    Serial.println("[MotorManual] WASD control:");
    Serial.println("[MotorManual]   w=forward  s=backward  a=turn left  d=turn right");
    Serial.println("[MotorManual]   x or space=stop  +=speed up  -=speed down  g=bench test");
    Serial.printf("[MotorManual] Deadman timeout: %lu ms. Repeat keys to keep moving.\n",
                  static_cast<unsigned long>(MOTOR_MANUAL_TIMEOUT_MS));
    Serial.printf("[MotorManual] Current speed: %d\n", motorManualSpeed);
}

void printSafeHoldStatus() {
    Serial.printf("[MotorManual] SAFE HOLD: waiting for WASD input. uptime=%lu ms\n",
                  static_cast<unsigned long>(millis()));
    Serial.println("[MotorManual] Type ? for help. Use x or space to stop.");
}

void stopMotorManual(const char* reason) {
    if (motorManualActive) {
        motor.stop();
        motorManualActive = false;
        Serial.printf("[MotorManual] stop: %s\n", reason);
    }
}

void driveMotorManual(char command) {
    motorManualUntilMs = millis() + MOTOR_MANUAL_TIMEOUT_MS;
    motorManualActive = true;

    if (command == 'w' || command == 'W') {
        motor.forward(motorManualSpeed);
        Serial.printf("[MotorManual] w forward speed=%d\n", motorManualSpeed);
    } else if (command == 's' || command == 'S') {
        motor.backward(motorManualSpeed);
        Serial.printf("[MotorManual] s backward speed=%d\n", motorManualSpeed);
    } else if (command == 'a' || command == 'A') {
        motor.turnLeft(motorManualSpeed);
        Serial.printf("[MotorManual] a turn left speed=%d\n", motorManualSpeed);
    } else if (command == 'd' || command == 'D') {
        motor.turnRight(motorManualSpeed);
        Serial.printf("[MotorManual] d turn right speed=%d\n", motorManualSpeed);
    }
}

void handleMotorManualCommand(char command) {
    if (command == '\r' || command == '\n') {
        return;
    }

    if (command == 'w' || command == 'W' ||
        command == 's' || command == 'S' ||
        command == 'a' || command == 'A' ||
        command == 'd' || command == 'D') {
        driveMotorManual(command);
        return;
    }

    if (command == 'x' || command == 'X' || command == ' ') {
        stopMotorManual("manual stop");
        return;
    }

    if (command == '+' || command == '=') {
        motorManualSpeed = min(motorManualSpeed + MOTOR_MANUAL_SPEED_STEP,
                               MOTOR_MANUAL_SPEED_MAX);
        Serial.printf("[MotorManual] speed=%d\n", motorManualSpeed);
        return;
    }

    if (command == '-' || command == '_') {
        motorManualSpeed = max(motorManualSpeed - MOTOR_MANUAL_SPEED_STEP,
                               MOTOR_MANUAL_SPEED_MIN);
        Serial.printf("[MotorManual] speed=%d\n", motorManualSpeed);
        return;
    }

    if (command == '?' || command == 'h' || command == 'H') {
        printMotorManualHelp();
        return;
    }

    Serial.printf("[MotorManual] unknown command '%c'. Type ? for help.\n", command);
}

void runMotorSelfTest() {
    constexpr int TEST_SPEED = 160;
    constexpr uint32_t RAW_MS = 700;
    constexpr uint32_t RUN_MS = 900;
    constexpr uint32_t PAUSE_MS = 1000;

    Serial.println();
    Serial.println("[MotorTest] ===== Xiao-An motor bench bring-up =====");
    Serial.println("[MotorTest] Wheels must be lifted. Be ready to cut motor power.");
    Serial.println("[MotorTest] Wiring under test:");
    Serial.println("[MotorTest]   GPIO1  -> left  driver IN1");
    Serial.println("[MotorTest]   GPIO2  -> left  driver IN2");
    Serial.println("[MotorTest]   GPIO3 -> right driver IN1");
    Serial.println("[MotorTest]   GPIO48 -> right driver IN2");
    Serial.println("[MotorTest] If a raw GPIO moves the wrong wheel, edit PIN_MOTOR_* in motor_ctrl.h.");
    Serial.println("[MotorTest] If the wheel is correct but direction is wrong, flip MOTOR_*_FORWARD_USES_IN1.");
    Serial.println("[MotorTest] Manual stop is 'x' or space after this test returns.");

    Serial.println();
    Serial.println("[MotorTest] Step 1/3: raw GPIO identification, one pin active at a time.");

    Serial.println("[MotorTest] EXPECT: GPIO1/L_IN1 moves LEFT motor one direction.");
    motor.debugDriveRaw(TEST_SPEED, 0, 0, 0, RAW_MS);
    delay(PAUSE_MS);

    Serial.println("[MotorTest] EXPECT: GPIO2/L_IN2 moves LEFT motor opposite direction.");
    motor.debugDriveRaw(0, TEST_SPEED, 0, 0, RAW_MS);
    delay(PAUSE_MS);

    Serial.println("[MotorTest] EXPECT: GPIO3/R_IN1 moves RIGHT motor one direction.");
    motor.debugDriveRaw(0, 0, TEST_SPEED, 0, RAW_MS);
    delay(PAUSE_MS);

    Serial.println("[MotorTest] EXPECT: GPIO48/R_IN2 moves RIGHT motor opposite direction.");
    motor.debugDriveRaw(0, 0, 0, TEST_SPEED, RAW_MS);
    delay(PAUSE_MS);

    Serial.println();
    Serial.println("[MotorTest] Step 2/3: per-side direction check using configured forward map.");
    Serial.println("[MotorTest] EXPECT: LEFT motor forward.");
    motor.debugDriveRaw(MOTOR_LEFT_FORWARD_USES_IN1 ? TEST_SPEED : 0,
                        MOTOR_LEFT_FORWARD_USES_IN1 ? 0 : TEST_SPEED,
                        0,
                        0,
                        RUN_MS);
    delay(PAUSE_MS);

    Serial.println("[MotorTest] EXPECT: LEFT motor reverse.");
    motor.debugDriveRaw(MOTOR_LEFT_FORWARD_USES_IN1 ? 0 : TEST_SPEED,
                        MOTOR_LEFT_FORWARD_USES_IN1 ? TEST_SPEED : 0,
                        0,
                        0,
                        RUN_MS);
    delay(PAUSE_MS);

    Serial.println("[MotorTest] EXPECT: RIGHT motor forward.");
    motor.debugDriveRaw(0,
                        0,
                        MOTOR_RIGHT_FORWARD_USES_IN1 ? TEST_SPEED : 0,
                        MOTOR_RIGHT_FORWARD_USES_IN1 ? 0 : TEST_SPEED,
                        RUN_MS);
    delay(PAUSE_MS);

    Serial.println("[MotorTest] EXPECT: RIGHT motor reverse.");
    motor.debugDriveRaw(0,
                        0,
                        MOTOR_RIGHT_FORWARD_USES_IN1 ? 0 : TEST_SPEED,
                        MOTOR_RIGHT_FORWARD_USES_IN1 ? TEST_SPEED : 0,
                        RUN_MS);
    delay(PAUSE_MS);

    Serial.println();
    Serial.println("[MotorTest] Step 3/3: paired chassis commands.");
    Serial.println("[MotorTest] EXPECT: both wheels forward, same chassis direction.");
    motor.forward(TEST_SPEED);
    delay(RUN_MS);
    motor.stop();
    delay(PAUSE_MS);

    Serial.println("[MotorTest] EXPECT: both wheels backward, same chassis direction.");
    motor.backward(TEST_SPEED);
    delay(RUN_MS);
    motor.stop();
    delay(PAUSE_MS);

    Serial.println("[MotorTest] EXPECT: pivot left: left wheel reverse, right wheel forward.");
    motor.turnLeft(TEST_SPEED);
    delay(RUN_MS);
    motor.stop();
    delay(PAUSE_MS);

    Serial.println("[MotorTest] EXPECT: pivot right: left wheel forward, right wheel reverse.");
    motor.turnRight(TEST_SPEED);
    delay(RUN_MS);
    motor.stop();

    Serial.println("[MotorTest] Done. loop() will hold motors stopped.");
    Serial.println("[MotorTest] Record mismatches, edit motor_ctrl.h, rebuild, then rerun.");
}

void setup() {
    holdMotorPinsLowBeforeSerial();

    Serial.begin(115200);
    delay(2000);

    Serial.println("[MotorManual] Xiao-An motor manual bring-up");
    Serial.println("[MotorManual] SAFE HOLD: motor test will NOT auto-start.");
    Serial.println("[MotorManual] Keep motor power disconnected while flashing.");
    Serial.println("[MotorManual] After wheels are lifted, use WASD in Serial Monitor.");

    motor.begin();
    motor.stop();
    printMotorManualHelp();
}

void loop() {
    if (Serial.available() > 0) {
        const char command = static_cast<char>(Serial.read());
        if (command == 'g' || command == 'G') {
            stopMotorManual("bench test requested");
            Serial.println("[MotorManual] Command g received: running one motor bench test.");
            runMotorSelfTest();
            motor.stop();
            Serial.println("[MotorManual] SAFE HOLD: test finished. Type 'g' to run again.");
        } else {
            handleMotorManualCommand(command);
        }
    }

    if (motorManualActive &&
        static_cast<int32_t>(millis() - motorManualUntilMs) >= 0) {
        stopMotorManual("deadman timeout");
    }

    if (!motorManualActive && (millis() - lastSafeHoldPrintMs >= 3000)) {
        lastSafeHoldPrintMs = millis();
        printSafeHoldStatus();
    }

    delay(50);
}
