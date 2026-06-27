#include "services/motion_service.h"

#include <Arduino.h>
#include <cstring>
#include <math.h>

#include "config.h"
#include "debug_log.h"
#include "display.h"
#include "protocol.h"

namespace {

constexpr uint32_t DEFAULT_TIMEOUT_MS = 5000;
constexpr uint32_t MAX_TIMEOUT_MS = 10000;
constexpr uint32_t MIN_MOTION_MS = 250;
constexpr uint32_t MAX_BENCH_DURATION_MS = 10000;
constexpr float DEFAULT_SPEED = 0.56f;
constexpr float MIN_EFFECTIVE_SPEED = 0.52f;

uint32_t clampDuration(uint32_t durationMs, uint32_t timeoutMs) {
  const uint32_t cappedTimeout = constrain(timeoutMs, MIN_MOTION_MS, MAX_TIMEOUT_MS);
  return constrain(durationMs, MIN_MOTION_MS, cappedTimeout);
}

}  // namespace

MotionService::MotionService(MotorController& motor, RobotState& state, StatusService& status)
    : _motor(motor), _state(state), _status(status) {}

float MotionService::paramFromPayload(JsonObject payload, const char* action) const {
  if (payload["param"].is<float>() || payload["param"].is<int>()) {
    return payload["param"] | 0.0f;
  }

  JsonObject params = payload["params"].as<JsonObject>();
  if (params.isNull()) {
    return 0.0f;
  }

  if (strcmp(action, MotionAction::MOVE_OUT_OF_DOCK) == 0) {
    return params["distance_cm"] | params["distance"] | 0.0f;
  }
  if (strcmp(action, MotionAction::TURN) == 0) {
    return params["angle_deg"] | params["angle"] | 0.0f;
  }
  return 0.0f;
}

uint32_t durationOverrideFromPayload(JsonObject payload, uint32_t timeoutMs) {
  JsonObject params = payload["params"].as<JsonObject>();
  if (params.isNull() || !(params["duration_ms"].is<uint32_t>() || params["duration_ms"].is<int>())) {
    return 0;
  }
  const uint32_t requested = params["duration_ms"] | 0;
  return clampDuration(
      constrain(requested, MIN_MOTION_MS, MAX_BENCH_DURATION_MS),
      timeoutMs);
}

float MotionService::speedFromPayload(JsonObject payload) const {
  JsonObject params = payload["params"].as<JsonObject>();
  float speed = DEFAULT_SPEED;
  if (!params.isNull() && (params["speed"].is<float>() || params["speed"].is<int>())) {
    speed = params["speed"] | DEFAULT_SPEED;
  } else if (payload["speed"].is<float>() || payload["speed"].is<int>()) {
    speed = payload["speed"] | DEFAULT_SPEED;
  }
  return constrain(speed, 0.0f, 1.0f);
}

uint32_t MotionService::timeoutFromPayload(JsonObject payload) const {
  const uint32_t timeoutMs = payload["timeout_ms"] | DEFAULT_TIMEOUT_MS;
  return constrain(timeoutMs, MIN_MOTION_MS, MAX_TIMEOUT_MS);
}

uint32_t MotionService::durationForAction(
    const char* action,
    float param,
    float speed,
    uint32_t timeoutMs) const {
  if (strcmp(action, MotionAction::MOVE_OUT_OF_DOCK) == 0) {
    if (param <= 0.0f) {
      // Bench / remote drive: no distance => run for timeout_ms (not fixed 1.5s pulse).
      return clampDuration(timeoutMs, timeoutMs);
    }
    const float cmPerSec = DRIVE_CM_PER_SEC * max(speed, MIN_EFFECTIVE_SPEED);
    const uint32_t durationMs = static_cast<uint32_t>((param / cmPerSec) * 1000.0f);
    return clampDuration(durationMs, timeoutMs);
  }

  if (strcmp(action, MotionAction::MOVE_BACK_TO_DOCK) == 0) {
    return clampDuration(timeoutMs, timeoutMs);
  }

  if (strcmp(action, MotionAction::TURN) == 0) {
    const float angleDeg = param == 0.0f ? 30.0f : fabsf(param);
    const uint32_t durationMs = static_cast<uint32_t>(angleDeg * TURN_MS_PER_DEG);
    return clampDuration(durationMs, timeoutMs);
  }

  return MIN_MOTION_MS;
}

int MotionService::speedToDuty(float speed) const {
  if (speed <= 0.0f) {
    return 0;
  }
  const int duty = constrain(static_cast<int>(80.0f + speed * 175.0f), 0, 255);
#if MERGETEST_ENABLE_MOTOR
  return max(duty, MOTOR_MIN_BENCH_DUTY);
#else
  return duty;
#endif
}

bool MotionService::isSupportedAction(const char* action) const {
  return strcmp(action, MotionAction::MOVE_OUT_OF_DOCK) == 0 ||
         strcmp(action, MotionAction::MOVE_BACK_TO_DOCK) == 0 ||
         strcmp(action, MotionAction::TURN) == 0 ||
         strcmp(action, MotionAction::STOP) == 0;
}

const char* MotionService::finalPositionForAction(const char* action) {
  if (strcmp(action, MotionAction::MOVE_OUT_OF_DOCK) == 0) {
    return "out_of_dock";
  }
  if (strcmp(action, MotionAction::MOVE_BACK_TO_DOCK) == 0) {
    return "in_dock";
  }
  return _motor.isDocked() ? "in_dock" : "unknown";
}

void MotionService::startMotor(const char* action, float param, int duty) {
#if MERGETEST_ENABLE_MOTOR
  if (strcmp(action, MotionAction::MOVE_OUT_OF_DOCK) == 0) {
    _motor.forward(duty);
  } else if (strcmp(action, MotionAction::MOVE_BACK_TO_DOCK) == 0) {
    _motor.backward(duty);
  } else if (strcmp(action, MotionAction::TURN) == 0) {
    if (param < 0.0f) {
      _motor.turnLeft(duty);
    } else {
      _motor.turnRight(duty);
    }
  }
#else
  (void)action;
  (void)param;
  (void)duty;
#endif
}

void MotionService::stopMotor() {
#if MERGETEST_ENABLE_MOTOR
  _motor.stop();
#endif
}

void MotionService::completeActive(const char* result) {
  if (!_active) {
    return;
  }

  stopMotor();
  _state.setMotion("idle");
  _state.setBusy(false);
  _state.setDocked(_motor.isDocked());
  display_set_motion("IDLE");

  _status.motionCompleted(
      _activeActionId.c_str(),
      result,
      _activeFinalPosition.c_str(),
      _activeFacingUser);
  _status.sendCurrent();

  LOGI(
      "Motion",
      "completed action=%s action_id=%s result=%s",
      _activeAction.c_str(),
      _activeActionId.c_str(),
      result);

  _active = false;
  _activeAction = "";
  _activeActionId = "";
  _activeFinalPosition = "";
}

void MotionService::execute(JsonObject payload) {
  const char* action = motionActionFromPayload(payload);
  const char* actionId = payload["action_id"] | "";

#if !MERGETEST_ENABLE_MOTOR
  if (strcmp(action, MotionAction::STOP) != 0) {
    LOGE("Motion", "reject action=%s — MERGETEST_ENABLE_MOTOR=0 in this env", action);
    _status.error(
        MsgType::MOTION_EXECUTE,
        "motor disabled in this firmware env",
        ErrorCode::MOTOR_STALL);
    _status.ack(MsgType::MOTION_EXECUTE, "error", "motor_disabled", actionId);
    return;
  }
#endif

  if (!isSupportedAction(action)) {
    _status.error(MsgType::MOTION_EXECUTE, "unsupported motion action");
    _status.ack(MsgType::MOTION_EXECUTE, "error", "unsupported action", actionId);
    return;
  }

  if (strcmp(action, MotionAction::STOP) == 0) {
    if (_active) {
      completeActive("interrupted");
    } else {
      stopMotor();
      _state.setMotion("idle");
      _state.setBusy(false);
      display_set_motion("IDLE");
      _status.sendCurrent();
    }
    _status.ack(MsgType::MOTION_EXECUTE, "ok", "stopped", actionId);
    return;
  }

  if (_active) {
    completeActive("interrupted");
  }

  const float param = paramFromPayload(payload, action);
  const float speed = speedFromPayload(payload);
  const uint32_t timeoutMs = timeoutFromPayload(payload);
  const uint32_t durationOverrideMs = durationOverrideFromPayload(payload, timeoutMs);
  const uint32_t durationMs = durationOverrideMs > 0
      ? durationOverrideMs
      : durationForAction(action, param, speed, timeoutMs);
  const int duty = speedToDuty(speed);

  _active = true;
  _activeAction = action;
  _activeActionId = actionId;
  _activeFinalPosition = finalPositionForAction(action);
  _activeFacingUser = strcmp(action, MotionAction::TURN) != 0;
  _activeDeadlineMs = millis() + durationMs;

  _state.setBusy(true);
  _state.setMotion(action);
  display_set_motion("MOVE");
  _status.sendCurrent();
  startMotor(action, param, duty);

  LOGI(
      "Motion",
      "started action=%s action_id=%s speed=%.2f duty=%d duration=%lu ms",
      action,
      actionId,
      speed,
      duty,
      static_cast<unsigned long>(durationMs));
  _status.ack(MsgType::MOTION_EXECUTE, "ok", "started", actionId);
}

void MotionService::loop() {
  if (!_active) {
    return;
  }

  if (static_cast<int32_t>(millis() - _activeDeadlineMs) >= 0) {
    completeActive("success");
  }
}
