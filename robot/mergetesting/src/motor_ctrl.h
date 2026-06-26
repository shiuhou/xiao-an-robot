#pragma once
// motor_ctrl.h — 提取自 robot/firmware/src/motor_ctrl.h

#include <Arduino.h>
#include "hardware_pins.h"

constexpr bool MOTOR_LEFT_FORWARD_USES_IN1  = true;
constexpr bool MOTOR_RIGHT_FORWARD_USES_IN1 = true;
constexpr int8_t PIN_LIMIT_FRONT  = -1;
constexpr int8_t PIN_LIMIT_BACK   = -1;
constexpr uint32_t MOTOR_PWM_FREQ_HZ  = 20000;
constexpr uint8_t  MOTOR_PWM_RES_BITS = 8;
constexpr float DRIVE_CM_PER_SEC   = 18.0f;
constexpr float TURN_MS_PER_DEG    = 6.5f;
constexpr int   TURN_DEFAULT_SPEED = 200;
constexpr int   MOTOR_MIN_BENCH_DUTY = 160;

#ifndef MERGE_PULSE_FORWARD_MS
#define MERGE_PULSE_FORWARD_MS 1500
#endif

class MotorController {
public:
  void begin();
  void moveForward(int speed, float distance_cm);
  void moveBackward(int speed);
  void turn(float angle_deg);
  void stop();
  bool isDocked();
  void forward(int speed);
  void backward(int speed);
  void turnLeft(int speed);
  void turnRight(int speed);
  void debugDriveRaw(int lIn1, int lIn2, int rIn1, int rIn2, uint32_t durationMs);
  void execute(const char* action, float param = 0.0f);

private:
  void setMotor(uint8_t motor, int dir, int speed);
};
