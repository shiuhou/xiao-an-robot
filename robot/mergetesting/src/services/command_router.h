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
  void loop();

private:
  struct PendingPcmStream {
    bool active = false;
    uint32_t sampleRate = 0;
    uint8_t channels = 0;
    char url[80] = {};
    char preview[96] = {};
  };

  struct PendingPcmStreamEnd {
    bool active = false;
    char audioId[48] = {};
  };

  WSClient& _ws;
  RobotState& _state;
  StatusService& _status;
  MotionService& _motion;
  PendingPcmStream _pendingPcmStream;
  PendingPcmStreamEnd _pendingPcmStreamEnd;

  void handleSystemWelcome(JsonObject payload);
  void handleDisplayExpression(JsonObject payload);
  void handleAudioPlayLocal(JsonObject payload);
  void handleAudioPlayTts(JsonObject payload);
  void startPendingPcmStream();
  void finishPendingPcmStream();
  void handleAudioStreamEnd(JsonObject payload);
  void handleUnsupported(const String& type);
};
