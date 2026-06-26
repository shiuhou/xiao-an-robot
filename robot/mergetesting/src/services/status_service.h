#pragma once

#include <Arduino.h>
#include "services/robot_state.h"
#include "ws_client.h"

class StatusService {
public:
  StatusService(WSClient& ws, RobotState& state);

  void sendCurrent();
  void ack(
      const char* commandType,
      const char* status,
      const char* detail = nullptr,
      const char* actionId = nullptr);
  void error(const char* where, const char* message, const char* code = ErrorCode::UNSUPPORTED_COMMAND);
  void motionCompleted(const char* actionId, const char* result, const char* position, bool facingUser);

private:
  WSClient& _ws;
  RobotState& _state;
};
