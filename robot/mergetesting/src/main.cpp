/**
 * main.cpp — 明日联调最小端到端闭环固件
 * Phase 1: /control hello + heartbeat
 * Phase 2: expression / motion / audio + command.ack
 * Phase 3: /video JPEG 1fps
 * Phase 4: 预留 asr.transcript.mock
 */

#include <Arduino.h>
#include <WiFi.h>
#include <ArduinoJson.h>

#include "config.h"
#include "debug_log.h"
#include "protocol.h"
#include "ws_client.h"
#include "display.h"
#include "motor_ctrl.h"
#include "speaker.h"
#include "cam_stream.h"
#include "mic_stream.h"

WSClient wsClient;
MotorController motor;
CamStream cam;
MicStream mic;

String currentExpression = Expression::NEUTRAL;
String currentMotion = "idle";
String currentCamera = "cam_off";
bool gBusy = false;
bool gDocked = false;

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
      gDocked || motor.isDocked());
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
  display_emotion(expr, intensity);
  currentExpression = expr;
  sendCurrentStatus();
  wsClient.sendCommandAck(MsgType::DISPLAY_EXPRESSION, "ok");
}

void handleMotionExecute(JsonObject payload) {
  const char* action = motionActionFromPayload(payload);
  const char* actionId = payload["action_id"] | "";
  float param = motionParamFromPayload(payload, action);

  if (gBusy) {
    wsClient.sendErrorReport(MsgType::MOTION_EXECUTE, "motor busy or previous motion running", ErrorCode::MOTOR_STALL);
    wsClient.sendCommandAck(MsgType::MOTION_EXECUTE, "error", "busy");
    return;
  }

  gBusy = true;
  currentMotion = action;
  display_set_motion("MOVE");
  sendCurrentStatus();

#if MERGETEST_ENABLE_MOTOR
  motor.execute(action, param);
#else
  delay(300);
#endif

  currentMotion = "idle";
  gBusy = false;
  gDocked = motor.isDocked();
  display_set_motion("IDLE");

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
  const char* url = payload["audio_url"] | "";
  const char* preview = payload["text_preview"] | payload["text"] | "";
  (void)url;
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
    display_set_connection("WS OK");
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
  display_set_connection("WIFI...");
  WiFi.mode(WIFI_STA);
  WiFi.begin(MERGETEST_WIFI_SSID, MERGETEST_WIFI_PASSWORD);

  uint32_t start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 30000) {
    delay(500);
    Serial.print(".");
  }

  if (WiFi.status() != WL_CONNECTED) {
    LOGE("WiFi", "Connect timeout");
    display_set_connection("WIFI ERR");
    return;
  }

  LOGI("WiFi", "Connected IP=%s RSSI=%d", WiFi.localIP().toString().c_str(), WiFi.RSSI());
  display_set_connection("WIFI OK");
}

void maintainWiFi() {
  if (WiFi.status() != WL_CONNECTED) {
    display_set_connection("WIFI...");
    WiFi.reconnect();
  }
}

void pollSerialMockAsr() {
#if MERGETEST_ENABLE_SERIAL_MOCK_ASR
  if (!Serial.available()) {
    return;
  }

  String line = Serial.readStringUntil('\n');
  line.trim();
  if (line.length() == 0) {
    return;
  }

  if (line.startsWith("mock:")) {
    wsClient.sendAsrTranscriptMock(line.substring(5).c_str());
    return;
  }

  // 本地无基站快速测试（串口 monitor 输入）
  if (line.startsWith("expr ")) {
    String expr = line.substring(5);
    display_emotion(expr.c_str(), 5);
    currentExpression = expr;
    LOGI("Main", "serial test expression=%s", expr.c_str());
    return;
  }
  if (line.startsWith("motion ")) {
    String action = line.substring(7);
#if MERGETEST_ENABLE_MOTOR
    motor.execute(action.c_str(), 0.0f);
#endif
    LOGI("Main", "serial test motion=%s", action.c_str());
    return;
  }
  if (line.startsWith("sound ")) {
    String sound = line.substring(6);
    speaker_play_local(sound.c_str());
    LOGI("Main", "serial test sound=%s", sound.c_str());
  }
#endif
}

void setup() {
  holdMotorPinsLowBeforeSerial();
  Serial.begin(115200);
  delay(1000);
  LOGI("Main", "Xiao An merge-testing firmware %s", MERGETEST_FIRMWARE_VERSION);

#if MERGETEST_ENABLE_DISPLAY
  display_init();
#else
  display_show_boot_neutral();
#endif

  connectWiFi();

#if MERGETEST_ENABLE_MOTOR
  motor.begin();
#endif

#if MERGETEST_ENABLE_SPEAKER
  speaker_init();
#endif

#if MERGETEST_ENABLE_MIC
  mic.begin();
#endif

#if MERGETEST_ENABLE_CAMERA
  cam.begin();
  currentCamera = cam.isActive() ? "cam_ok" : "cam_err";
  display_set_camera(cam.isActive() ? "CAM OK" : "CAM ERR");
#else
  currentCamera = "cam_off";
#endif

  wsClient.begin(MERGETEST_BASE_STATION_IP, MERGETEST_BASE_STATION_PORT, onControlMessage);
  LOGI("Main", "Setup complete device_id=%s -> ws://%s:%u",
       MERGETEST_DEVICE_ID, MERGETEST_BASE_STATION_IP, MERGETEST_BASE_STATION_PORT);
}

void loop() {
  maintainWiFi();
  wsClient.loop();
  display_tick();
  pollSerialMockAsr();

#if MERGETEST_ENABLE_MIC
  if (wsClient.isAudioConnected()) {
    mic.streamLoop(wsClient);
  }
#endif

#if MERGETEST_ENABLE_CAMERA
  if (wsClient.isVideoConnected()) {
    cam.captureLoop(wsClient);
  }
#endif

  if (wsClient.isControlConnected()) {
    display_set_connection("WS OK");
  } else if (WiFi.status() == WL_CONNECTED) {
    display_set_connection("WS...");
  }
}
