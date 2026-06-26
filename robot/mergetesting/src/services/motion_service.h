#pragma once

#include <Arduino.h>
#include <ArduinoJson.h>
#include "motor_ctrl.h"
#include "services/robot_state.h"
#include "services/status_service.h"

class MotionService {
public:
  MotionService(MotorController& motor, RobotState& state, StatusService& status);

  void execute(JsonObject payload);
  void loop();

private:
  MotorController& _motor;
  RobotState& _state;
  StatusService& _status;

  bool _active = false;
  String _activeAction;
  String _activeActionId;
  String _activeFinalPosition;
  bool _activeFacingUser = true;
  uint32_t _activeDeadlineMs = 0;

  float paramFromPayload(JsonObject payload, const char* action) const;
  float speedFromPayload(JsonObject payload) const;
  uint32_t timeoutFromPayload(JsonObject payload) const;
  uint32_t durationForAction(const char* action, float param, float speed, uint32_t timeoutMs) const;
  int speedToDuty(float speed) const;
  bool isSupportedAction(const char* action) const;
  const char* finalPositionForAction(const char* action);
  void startMotor(const char* action, float param, int duty);
  void stopMotor();
  void completeActive(const char* result);
};
