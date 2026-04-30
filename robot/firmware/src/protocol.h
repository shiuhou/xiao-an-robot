#pragma once
// protocol.h
// Defines all WebSocket message type constants and payload structs
// Matches docs/protocol.md v0.1
// Author: Team Xiao An

#include <Arduino.h>
#include <ArduinoJson.h>

// Message types: Robot -> Base Station
namespace MsgType {
  // Robot -> Base Station
  constexpr const char* DEVICE_HELLO       = "device.hello";
  constexpr const char* DEVICE_HEARTBEAT   = "device.heartbeat";
  constexpr const char* SENSOR_BUTTON      = "sensor.button";
  constexpr const char* SENSOR_DOCK_STATUS = "sensor.dock_status";
  constexpr const char* MOTION_COMPLETED   = "motion.completed";
  constexpr const char* ERROR_REPORT       = "error.report";

  // Base Station -> Robot
  constexpr const char* SYSTEM_WELCOME     = "system.welcome";
  constexpr const char* DISPLAY_EXPRESSION = "display.expression";
  constexpr const char* MOTION_EXECUTE     = "motion.execute";
  constexpr const char* AUDIO_PLAY_TTS     = "audio.play_tts";
  constexpr const char* AUDIO_PLAY_LOCAL   = "audio.play_local";
  constexpr const char* CONFIG_UPDATE      = "config.update";
  constexpr const char* SYSTEM_SHUTDOWN    = "system.shutdown";
}

// Supported expression names
namespace Expression {
  constexpr const char* HAPPY     = "happy";
  constexpr const char* SAD       = "sad";
  constexpr const char* CARING    = "caring";
  constexpr const char* TIRED     = "tired";
  constexpr const char* THINKING  = "thinking";
  constexpr const char* SPEAKING  = "speaking";
  constexpr const char* IDLE      = "idle";
  constexpr const char* SURPRISED = "surprised";
  constexpr const char* SLEEPING  = "sleeping";
}

// Supported motion actions
namespace MotionAction {
  constexpr const char* MOVE_OUT_OF_DOCK  = "move_out_of_dock";
  constexpr const char* MOVE_BACK_TO_DOCK = "move_back_to_dock";
  constexpr const char* TURN              = "turn";
  constexpr const char* NOD_HEAD          = "nod_head";
  constexpr const char* TILT_HEAD         = "tilt_head";
  constexpr const char* WIGGLE_EARS       = "wiggle_ears";
  constexpr const char* STOP              = "stop";
}

// Error codes
namespace ErrorCode {
  constexpr const char* MOTOR_STALL    = "MOTOR_STALL";
  constexpr const char* MOTOR_LIMIT    = "MOTOR_LIMIT";
  constexpr const char* BATTERY_LOW    = "BATTERY_LOW";
  constexpr const char* BATTERY_CRIT   = "BATTERY_CRITICAL";
  constexpr const char* WIFI_WEAK      = "WIFI_WEAK";
  constexpr const char* CAM_INIT_FAIL  = "CAM_INIT_FAIL";
  constexpr const char* MIC_INIT_FAIL  = "MIC_INIT_FAIL";
}

// Helper: build base message envelope
// Usage: auto doc = buildMsg(MsgType::DEVICE_HELLO, seq++);
// Then: doc["payload"]["key"] = value;
inline JsonDocument buildMsg(const char* type, uint32_t seq) {
  JsonDocument doc;
  doc["type"] = type;
  doc["ts"]   = (long long)millis(); // TODO: replace with NTP time
  doc["seq"]  = seq;
  doc["payload"].to<JsonObject>();
  return doc;
}
