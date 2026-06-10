#pragma once
// motor_ctrl.h - Differential drive motor controller for Xiao An robot
// Driver: DRV8833 dual H-bridge
// Author: 施宇灏

#include <Arduino.h>

// ── Pin assignments ──────────────────────────────────────────────────────────
// TODO: adjust to match your actual wiring on ESP32-S3
constexpr uint8_t PIN_MOTOR_L_IN1  = 15;   // Left  motor, channel A IN1 (PWM fwd)
constexpr uint8_t PIN_MOTOR_L_IN2  = 16;   // Left  motor, channel A IN2 (PWM bwd)
constexpr uint8_t PIN_MOTOR_R_IN1  = 17;   // Right motor, channel B IN1 (PWM fwd)
constexpr uint8_t PIN_MOTOR_R_IN2  = 18;   // Right motor, channel B IN2 (PWM bwd)
constexpr uint8_t PIN_LIMIT_FRONT  = 19;   // Front limit switch, active-LOW
constexpr uint8_t PIN_LIMIT_BACK   = 20;   // Back  limit switch, active-LOW (dock sensor)

// ── LEDC PWM settings ────────────────────────────────────────────────────────
constexpr uint32_t MOTOR_PWM_FREQ_HZ  = 20000;  // 20 kHz — above hearing range
constexpr uint8_t  MOTOR_PWM_RES_BITS = 8;       // duty 0–255

// ── Calibration constants ────────────────────────────────────────────────────
// TODO: measure and tune on the real chassis after assembly
constexpr float DRIVE_CM_PER_SEC   = 18.0f;  // linear speed at duty=255
constexpr float TURN_MS_PER_DEG    = 6.5f;   // pivot-turn: ms per degree at duty=200
constexpr int   TURN_DEFAULT_SPEED = 200;     // duty used by turn(angle_deg)

class MotorController {
public:
    // Initialization
    void begin();

    // High-level motion (blocking, stop on completion or limit switch)
    void moveForward(int speed, float distance_cm);
    void moveBackward(int speed);    // stops when back limit switch triggers (docked)
    void turn(float angle_deg);      // +deg = right, -deg = left, timed pivot

    // Immediate cut-off
    void stop();

    // State query
    bool isDocked();

    // Raw drive helpers (non-blocking, indefinite — caller must stop())
    void forward(int speed);
    void backward(int speed);
    void turnLeft(int speed);
    void turnRight(int speed);

    // Protocol action dispatcher (maps MotionAction strings to above calls)
    void execute(const char* action, float param = 0.0f);

private:
    // motor: 0=left, 1=right | dir: 1=forward, -1=backward, 0=brake
    void setMotor(uint8_t motor, int dir, int speed);
};
