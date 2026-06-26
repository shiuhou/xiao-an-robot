#include "app/mergetesting_app.h"

#include <Arduino.h>
#include <WiFi.h>
#include <cstdio>
#if ENABLE_ARDUINO_OTA
#include <ArduinoOTA.h>
#endif

#include "config.h"
#include "debug_log.h"
#include "display.h"
#include "hardware_pins.h"
#include "speaker.h"

MergetestingApp::MergetestingApp()
    : _status(_wsClient, _state),
      _motion(_motor, _state, _status),
      _router(_wsClient, _state, _status, _motion) {}

void MergetestingApp::holdMotorPinsLowBeforeSerial() {
  const int8_t pins[] = {PIN_MOTOR_L_IN1, PIN_MOTOR_L_IN2, PIN_MOTOR_R_IN1, PIN_MOTOR_R_IN2};
  for (int8_t pin : pins) {
    pinMode(pin, OUTPUT);
    digitalWrite(pin, LOW);
  }
}

void MergetestingApp::setupOtaIfReady() {
#if ENABLE_ARDUINO_OTA
  if (_otaStarted || WiFi.status() != WL_CONNECTED) {
    return;
  }

  ArduinoOTA.setHostname(OTA_HOSTNAME);
  if (OTA_PASSWORD[0] != '\0') {
    ArduinoOTA.setPassword(OTA_PASSWORD);
  }
  ArduinoOTA.onStart([this]() {
    holdMotorPinsLowBeforeSerial();
    LOGW("OTA", "Update starting; motors held low");
  });
  ArduinoOTA.onEnd([]() {
    LOGI("OTA", "Update complete; rebooting");
  });
  ArduinoOTA.onProgress([](unsigned int progress, unsigned int total) {
    if (total > 0) {
      LOGI("OTA", "Progress %u%%", (progress * 100U) / total);
    }
  });
  ArduinoOTA.onError([](ota_error_t error) {
    LOGE("OTA", "Error %u", static_cast<unsigned int>(error));
  });
  ArduinoOTA.begin();
  _otaStarted = true;
  LOGI("OTA",
       "Ready hostname=%s auth=%s",
       OTA_HOSTNAME,
       OTA_PASSWORD[0] != '\0' ? "enabled" : "disabled");
#endif
}

void MergetestingApp::pollOta() {
#if ENABLE_ARDUINO_OTA
  setupOtaIfReady();
  if (_otaStarted) {
    ArduinoOTA.handle();
  }
#endif
}

void MergetestingApp::connectWiFi() {
  display_set_connection("WIFI...");
  WiFi.mode(WIFI_STA);
  WiFi.begin(MERGETEST_WIFI_SSID, MERGETEST_WIFI_PASSWORD);

  const uint32_t start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 30000) {
    delay(500);
    Serial.print(".");
  }

  if (WiFi.status() != WL_CONNECTED) {
    _state.setWifiConnected(false);
    LOGE("WiFi", "Connect timeout");
    display_set_connection("WIFI ERR");
    return;
  }

  _state.setWifiConnected(true);
  LOGI("WiFi", "Connected IP=%s RSSI=%d", WiFi.localIP().toString().c_str(), WiFi.RSSI());
  display_set_connection("WIFI OK");
}

void MergetestingApp::maintainWiFi() {
  const bool connected = WiFi.status() == WL_CONNECTED;
  _state.setWifiConnected(connected);

  if (!connected) {
    display_set_connection("WIFI...");
    WiFi.reconnect();
  }
}

void MergetestingApp::pollSerialMockAsr() {
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
    _wsClient.sendAsrTranscriptMock(line.substring(5).c_str());
    return;
  }

  if (line.startsWith("expr ")) {
    String expr = line.substring(5);
    display_emotion(expr.c_str(), 5);
    _state.setExpression(expr.c_str());
    _status.sendCurrent();
    LOGI("Main", "serial test expression=%s", expr.c_str());
    return;
  }
  if (line.startsWith("motion ")) {
    String action = line.substring(7);
    JsonDocument doc;
    JsonObject payload = doc.to<JsonObject>();
    payload["action"] = action;
    _motion.execute(payload);
    LOGI("Main", "serial test motion=%s", action.c_str());
    return;
  }
#if MERGETEST_ENABLE_MOTOR
  if (line.startsWith("motor raw ")) {
    int lIn1 = 0;
    int lIn2 = 0;
    int rIn1 = 0;
    int rIn2 = 0;
    uint32_t durationMs = 800;
    sscanf(
        line.c_str() + 10,
        "%d %d %d %d %lu",
        &lIn1,
        &lIn2,
        &rIn1,
        &rIn2,
        &durationMs);
    _motor.debugDriveRaw(lIn1, lIn2, rIn1, rIn2, durationMs);
    LOGI("Main", "serial motor raw %d %d %d %d %lu", lIn1, lIn2, rIn1, rIn2, durationMs);
    return;
  }
  if (line.startsWith("motor fwd ")) {
    const int speed = line.substring(10).toInt();
    _motor.forward(speed > 0 ? speed : MOTOR_MIN_BENCH_DUTY);
    LOGI("Main", "serial motor fwd speed=%d", speed);
    return;
  }
  if (line.startsWith("motor back ")) {
    const int speed = line.substring(11).toInt();
    _motor.backward(speed > 0 ? speed : MOTOR_MIN_BENCH_DUTY);
    LOGI("Main", "serial motor back speed=%d", speed);
    return;
  }
  if (line == "motor stop") {
    _motor.stop();
    LOGI("Main", "serial motor stop");
    return;
  }
#endif
  if (line.startsWith("sound ")) {
    String sound = line.substring(6);
    speaker_play_local(sound.c_str());
    LOGI("Main", "serial test sound=%s", sound.c_str());
  }
#endif
}

void MergetestingApp::updateTransportState() {
  _state.setControlConnected(_wsClient.isControlConnected());
  _state.setVideoConnected(_wsClient.isVideoConnected());
  _state.setAudioConnected(_wsClient.isAudioConnected());
}

void MergetestingApp::setup() {
  holdMotorPinsLowBeforeSerial();
  Serial.begin(115200);
  delay(1000);
  LOGI("Main", "Xiao An merge-testing firmware %s", MERGETEST_FIRMWARE_VERSION);
#if MERGETEST_ENABLE_MOTOR
  LOGI("Main", "Motor driver enabled (MERGETEST_ENABLE_MOTOR=1)");
#else
  LOGW("Main", "Motor driver DISABLED — burn mergetesting_motor_only for motion H");
#endif

#if MERGETEST_DISABLE_IDLE_WDT
  disableCore0WDT();
  LOGW("WDT", "Core0 idle WDT disabled for control-only bring-up");
#endif

#if MERGETEST_ENABLE_DISPLAY
  display_init();
#else
  display_show_boot_neutral();
#endif

  connectWiFi();
  setupOtaIfReady();

#if MERGETEST_ENABLE_MOTOR
  _motor.begin();
#endif

#if MERGETEST_ENABLE_MIC
  _mic.begin();
#endif

#if MERGETEST_ENABLE_CAMERA
  _cam.begin();
  _state.setCameraReady(_cam.isActive());
  display_set_camera(_cam.isActive() ? "CAM OK" : "CAM ERR");
#if MERGETEST_ENABLE_MOTOR
  if (_cam.isActive()) {
    _motor.begin();
    LOGI("Motor", "Re-init after camera — esp_camera uses LEDC timer 1 for XCLK");
  }
#endif
#else
  _state.setCameraOff();
#endif

  _wsClient.setBusyProvider([this]() {
    return _state.isBusy();
  });
  _wsClient.begin(
      MERGETEST_BASE_STATION_IP,
      MERGETEST_BASE_STATION_PORT,
      [this](const String& type, JsonObject payload) {
        _router.handle(type, payload);
      });

  LOGI("Main", "Setup complete device_id=%s -> ws://%s:%u",
       MERGETEST_DEVICE_ID, MERGETEST_BASE_STATION_IP, MERGETEST_BASE_STATION_PORT);
}

void MergetestingApp::loop() {
  maintainWiFi();
  pollOta();
  _wsClient.loop();
  _motion.loop();
  updateTransportState();
  display_tick();
  pollSerialMockAsr();

#if MERGETEST_ENABLE_MIC
  if (_wsClient.isAudioConnected()) {
    _mic.streamLoop(_wsClient);
  }
#endif

#if MERGETEST_ENABLE_CAMERA
  if (_wsClient.isVideoConnected()) {
    _cam.captureLoop(_wsClient);
  }
#endif

  if (_wsClient.isControlConnected()) {
    display_set_connection("WS OK");
  } else if (WiFi.status() == WL_CONNECTED) {
    display_set_connection("WS...");
  }

  delay(5);
}
