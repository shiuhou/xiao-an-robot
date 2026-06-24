/**
 * integrated_main.cpp
 * DK-2500 integration firmware entry (control + video + audio + face240).
 * Replaces mergetesting main for esp32-s3-integrated env.
 */

#include <Arduino.h>
#include <WiFi.h>
#include <ArduinoJson.h>

#include "feature_flags.h"
#include "debug_log.h"
#include "protocol.h"
#include "ws_client.h"
#include "motor_ctrl.h"
#include "cam_stream.h"
#include "mic_stream.h"
#include "peripherals/speaker.h"
#include "peripherals/face240_display.h"

#define WIFI_SSID     "YOUR_WIFI_SSID"
#define WIFI_PASSWORD "YOUR_WIFI_PASSWORD"
#define BASE_STATION_IP   "192.168.1.100"
#define BASE_STATION_PORT 8765

WSClient wsClient;
MotorController motor;
CamStream cam;
MicStream mic;

String currentExpression = Expression::IDLE;
String currentMotion = "idle";
String currentCamera = "cam_off";
bool gBusy = false;

float motionParamFromPayload(JsonObject payload, const char* action) {
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

const char* finalPositionForAction(const char* action) {
  if (strcmp(action, MotionAction::MOVE_OUT_OF_DOCK) == 0) {
    return "out_of_dock";
  }
  if (strcmp(action, MotionAction::MOVE_BACK_TO_DOCK) == 0) {
    return "in_dock";
  }
  if (strcmp(action, MotionAction::STOP) == 0) {
    return motor.isDocked() ? "in_dock" : "out_of_dock";
  }
  return motor.isDocked() ? "in_dock" : "unknown";
}

void sendCurrentStatus() {
  wsClient.sendStatus(
      currentExpression.c_str(),
      currentMotion.c_str(),
      currentCamera.c_str(),
      motor.isDocked());
}

void holdMotorPinsLowBeforeSerial() {
  const int8_t pins[] = {PIN_MOTOR_L_IN1, PIN_MOTOR_L_IN2, PIN_MOTOR_R_IN1, PIN_MOTOR_R_IN2};
  for (int8_t pin : pins) {
    pinMode(pin, OUTPUT);
    digitalWrite(pin, LOW);
  }
}

void handleDisplayExpression(JsonObject payload) {
  const char* expr = expressionFromPayload(payload);
  int intensity = payload["intensity"] | 5;
  face240_emotion(expr, intensity);
  currentExpression = expr;
  sendCurrentStatus();
  wsClient.sendCommandAck(MsgType::DISPLAY_EXPRESSION, "ok");
}

void handleMotionExecute(JsonObject payload) {
  const char* action = motionActionFromPayload(payload);
  const char* actionId = payload["action_id"] | "";
  float param = motionParamFromPayload(payload, action);

  if (gBusy) {
    wsClient.sendErrorReport(MsgType::MOTION_EXECUTE, "motor busy", ErrorCode::MOTOR_STALL);
    wsClient.sendCommandAck(MsgType::MOTION_EXECUTE, "error", "busy");
    return;
  }

  gBusy = true;
  currentMotion = action;
  sendCurrentStatus();
  motor.execute(action, param);
  currentMotion = "idle";
  gBusy = false;

  wsClient.sendMotionCompleted(actionId, "success", finalPositionForAction(action), true);
  wsClient.sendCommandAck(MsgType::MOTION_EXECUTE, "ok");
  sendCurrentStatus();
}

void handleAudioPlayLocal(JsonObject payload) {
  const char* sound = payload["sound"] | LocalSound::CARE_01;
  bool ok = speaker_play_local(sound);
  if (ok) {
    wsClient.sendCommandAck(MsgType::AUDIO_PLAY_LOCAL, "ok");
  } else {
    wsClient.sendErrorReport(MsgType::AUDIO_PLAY_LOCAL, "speaker not ready", ErrorCode::AUDIO_UNSUPPORTED);
    wsClient.sendCommandAck(MsgType::AUDIO_PLAY_LOCAL, "error", "speaker_init_fail");
  }
}

void handleAudioPlayTts(JsonObject payload) {
  const char* preview = payload["text_preview"] | payload["text"] | "";
  (void)(payload["audio_url"] | "");
  bool ok = speaker_play_tts_mock(preview);
  if (ok) {
    wsClient.sendCommandAck(MsgType::AUDIO_PLAY_TTS, "ok", "mock_tone");
  } else {
    wsClient.sendCommandAck(MsgType::AUDIO_PLAY_TTS, "error", "speaker_init_fail");
  }
}

void onControlMessage(const String& type, JsonObject payload) {
  LOGI("Main", "Dispatch: %s", type.c_str());

  if (type == MsgType::SYSTEM_WELCOME) {
    JsonObject config = payload["config"].as<JsonObject>();
    if (!config.isNull()) {
      int hbSec = config["heartbeat_interval_sec"] | 0;
      if (hbSec > 0) {
        wsClient.setHeartbeatIntervalMs(static_cast<uint32_t>(hbSec) * 1000U);
      }
      float videoFps = config["video_fps"] | 0.0f;
      if (videoFps > 0.0f) {
        wsClient.setVideoFps(videoFps);
      }
    }
    sendCurrentStatus();

  } else if (type == MsgType::DISPLAY_EXPRESSION) {
    handleDisplayExpression(payload);

  } else if (type == MsgType::MOTION_EXECUTE) {
    handleMotionExecute(payload);

  } else if (type == MsgType::AUDIO_PLAY_LOCAL) {
    handleAudioPlayLocal(payload);

  } else if (type == MsgType::AUDIO_PLAY_TTS) {
    handleAudioPlayTts(payload);

  } else if (type == MsgType::CONFIG_UPDATE) {
    wsClient.sendCommandAck(MsgType::CONFIG_UPDATE, "ok");

  } else if (type == MsgType::SYSTEM_SHUTDOWN) {
    wsClient.sendCommandAck(MsgType::SYSTEM_SHUTDOWN, "ok");
    delay(100);
    ESP.restart();

  } else {
    wsClient.sendErrorReport(type.c_str(), "unsupported command", ErrorCode::UNSUPPORTED_COMMAND);
    wsClient.sendCommandAck(type.c_str(), "error", "unsupported");
  }
}

void connectWiFi() {
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  uint32_t start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 30000) {
    delay(500);
    Serial.print(".");
  }
  if (WiFi.status() != WL_CONNECTED) {
    LOGE("WiFi", "Connect timeout");
    return;
  }
  LOGI("WiFi", "Connected IP=%s RSSI=%d", WiFi.localIP().toString().c_str(), WiFi.RSSI());
}

void maintainWiFi() {
  if (WiFi.status() != WL_CONNECTED) {
    WiFi.reconnect();
  }
}

void setup() {
  holdMotorPinsLowBeforeSerial();
  Serial.begin(115200);
  delay(1000);
  LOGI("Main", "Xiao An integrated firmware starting");

  face240_init();
  connectWiFi();
  motor.begin();
  speaker_init();
  mic.begin();
  cam.begin();
  currentCamera = cam.isActive() ? "cam_ok" : "cam_err";

  wsClient.begin(BASE_STATION_IP, BASE_STATION_PORT, onControlMessage);
  LOGI("Main", "Setup complete -> ws://%s:%u", BASE_STATION_IP, BASE_STATION_PORT);
}

void loop() {
  maintainWiFi();
  wsClient.loop();
  face240_tick();

  if (wsClient.isAudioConnected()) {
    mic.streamLoop(wsClient);
  }
  if (wsClient.isVideoConnected()) {
    cam.captureLoop(wsClient);
  }
}
