#pragma once
// protocol.h — WebSocket 消息常量（对齐 docs/protocol.md v0.1 + 联调扩展）

#include <Arduino.h>
#include <ArduinoJson.h>

namespace MsgType {
  // Robot -> Base Station
  constexpr const char* DEVICE_HELLO         = "device.hello";
  constexpr const char* DEVICE_HEARTBEAT     = "device.heartbeat";
  constexpr const char* DEVICE_STATUS        = "device.status";
  constexpr const char* MOTION_COMPLETED     = "motion.completed";
  constexpr const char* ERROR_REPORT         = "error.report";
  constexpr const char* COMMAND_ACK          = "command.ack";
  constexpr const char* VIDEO_FRAME_META     = "video.frame_meta";
  constexpr const char* VIDEO_FRAME          = "video.frame";
  constexpr const char* AUDIO_CHUNK_META     = "audio.chunk_meta";
  constexpr const char* ASR_TRANSCRIPT_MOCK  = "asr.transcript.mock";

  // Base Station -> Robot
  constexpr const char* SYSTEM_WELCOME       = "system.welcome";
  constexpr const char* DISPLAY_EXPRESSION   = "display.expression";
  constexpr const char* MOTION_EXECUTE       = "motion.execute";
  constexpr const char* AUDIO_PLAY_TTS         = "audio.play_tts";
  constexpr const char* AUDIO_PLAY_LOCAL     = "audio.play_local";
  constexpr const char* CONFIG_UPDATE        = "config.update";
  constexpr const char* SYSTEM_SHUTDOWN      = "system.shutdown";
}

namespace Expression {
  constexpr const char* NEUTRAL    = "neutral";
  constexpr const char* IDLE       = "idle";
  constexpr const char* HAPPY      = "happy";
  constexpr const char* SAD        = "sad";
  constexpr const char* CARING     = "caring";
  constexpr const char* TIRED      = "tired";
  constexpr const char* THINKING   = "thinking";
  constexpr const char* SPEAKING   = "speaking";
  constexpr const char* LISTENING  = "listening";
  constexpr const char* SURPRISED  = "surprised";
  constexpr const char* SLEEPING   = "sleeping";
  constexpr const char* ERROR      = "error";
}

namespace MotionAction {
  constexpr const char* MOVE_OUT_OF_DOCK  = "move_out_of_dock";
  constexpr const char* MOVE_BACK_TO_DOCK = "move_back_to_dock";
  constexpr const char* TURN              = "turn";
  constexpr const char* NOD_HEAD          = "nod_head";
  constexpr const char* TILT_HEAD         = "tilt_head";
  constexpr const char* WIGGLE_EARS       = "wiggle_ears";
  constexpr const char* STOP              = "stop";
}

namespace ErrorCode {
  constexpr const char* MOTOR_STALL         = "MOTOR_STALL";
  constexpr const char* MOTOR_LIMIT         = "MOTOR_LIMIT";
  constexpr const char* CAM_INIT_FAIL       = "CAM_INIT_FAIL";
  constexpr const char* AUDIO_UNSUPPORTED   = "AUDIO_UNSUPPORTED";
  constexpr const char* UNSUPPORTED_COMMAND   = "UNSUPPORTED_COMMAND";
}

namespace LocalSound {
  constexpr const char* CARE_01   = "care_01";
  constexpr const char* ALARM_01  = "alarm_01";
  constexpr const char* WAKE_01   = "wake_01";
}

inline JsonDocument buildMsg(const char* type, uint32_t seq) {
  JsonDocument doc;
  doc["type"] = type;
  doc["ts"]   = static_cast<long long>(millis());
  doc["seq"]  = seq;
  doc["payload"].to<JsonObject>();
  return doc;
}

// 兼容 envelope（payload 子对象）与 flat（字段在根）两种入站格式
inline JsonObject messagePayload(JsonDocument& doc) {
  JsonObject nested = doc["payload"].as<JsonObject>();
  if (!nested.isNull() && nested.size() > 0) {
    return nested;
  }
  return doc.as<JsonObject>();
}

inline const char* motionActionFromPayload(JsonObject payload) {
  const char* action = payload["action"] | payload["motion"] | MotionAction::STOP;
  return action;
}

inline const char* expressionFromPayload(JsonObject payload) {
  return payload["expression"] | Expression::NEUTRAL;
}
