#pragma once

#include <ArduinoJson.h>
#include "services/motion_service.h"
#include "services/robot_state.h"
#include "services/status_service.h"
#include "ws_client.h"

class CommandRouter {
public:
  CommandRouter(WSClient& ws, RobotState& state, StatusService& status, MotionService& motion);

  void handle(const String& type, JsonObject payload);

private:
  WSClient& _ws;
  RobotState& _state;
  StatusService& _status;
  MotionService& _motion;

  void handleSystemWelcome(JsonObject payload);
  void handleDisplayExpression(JsonObject payload);
  void handleAudioPlayLocal(JsonObject payload);
  void handleAudioPlayTts(JsonObject payload);
  void handleUnsupported(const String& type);
};
