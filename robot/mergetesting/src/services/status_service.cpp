#include "services/status_service.h"

StatusService::StatusService(WSClient& ws, RobotState& state)
    : _ws(ws), _state(state) {}

void StatusService::sendCurrent() {
  _ws.sendStatus(
      _state.expression(),
      _state.motion(),
      _state.camera(),
      _state.isDocked());
}

void StatusService::ack(
    const char* commandType,
    const char* status,
    const char* detail,
    const char* actionId) {
  _ws.sendCommandAck(commandType, status, detail, actionId);
}

void StatusService::error(const char* where, const char* message, const char* code) {
  _ws.sendErrorReport(where, message, code);
}

void StatusService::motionCompleted(
    const char* actionId,
    const char* result,
    const char* position,
    bool facingUser) {
  _ws.sendMotionCompleted(actionId, result, position, facingUser);
}
