#pragma once
// motor_ctrl.h - Differential drive motor controller for Xiao An robot
// Driver: DRV8833 dual H-bridge
// Author: 施宇灏

#include <Arduino.h>

// ── Motor bring-up wiring map ────────────────────────────────────────────────
// Canonical map: hardware/wiring/esp32_pinout.md and board_pins.h (camera/audio).
// Bench assumption for the current harness:
//   GPIO1  -> left  driver IN1
//   GPIO2  -> left  driver IN2
//   GPIO47 -> right driver IN1
//   GPIO38 -> right driver IN2
//
// If the one-pin raw test shows a GPIO moves the wrong physical wheel, change
// the PIN_MOTOR_* mapping below. If the correct wheel spins but forward is
// reversed, flip that side's *_FORWARD_USES_IN1 constant instead of rewiring.
constexpr int8_t PIN_MOTOR_L_IN1  = 1;
constexpr int8_t PIN_MOTOR_L_IN2  = 2;
constexpr int8_t PIN_MOTOR_R_IN1  = 47;
constexpr int8_t PIN_MOTOR_R_IN2  = 38;
constexpr bool MOTOR_LEFT_FORWARD_USES_IN1  = true;
constexpr bool MOTOR_RIGHT_FORWARD_USES_IN1 = true;

// Limit switches are disabled during bench motor bring-up. Set real GPIOs only
// after motor direction is confirmed.
constexpr int8_t PIN_LIMIT_FRONT  = -1;
constexpr int8_t PIN_LIMIT_BACK   = -1;

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
    void debugDriveRaw(int lIn1, int lIn2, int rIn1, int rIn2, uint32_t durationMs);

    // Protocol action dispatcher (maps MotionAction strings to above calls)
    void execute(const char* action, float param = 0.0f);

private:
    // motor: 0=left, 1=right | dir: 1=forward, -1=backward, 0=brake
    void setMotor(uint8_t motor, int dir, int speed);
};
