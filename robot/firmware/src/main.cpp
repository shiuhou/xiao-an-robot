/**
 * main.cpp
 * --------
 * Entry point for Xiao An robot firmware (ESP32-S3)
 * Initializes all modules and runs the main loop.
 *
 * Author: 施宇灏
 */

#include <Arduino.h>
#include <WiFi.h>
#include "ws_client.h"
#include "motor_ctrl.h"
#include "servo_ctrl.h"
#include "display.h"
#include "mic_stream.h"
#include "cam_stream.h"
#include "protocol.h"

// TODO: Move credentials to NVS or a config file not committed to git
#define WIFI_SSID     "YOUR_WIFI_SSID"
#define WIFI_PASSWORD "YOUR_WIFI_PASSWORD"
#define BASE_STATION_IP   "192.168.1.100"
#define BASE_STATION_PORT 8765

WSClient      wsClient;
MotorController motor;
ServoController servo;
DisplayController display;
MicStream     mic;
CamStream     cam;

void onControlMessage(const String& type, JsonObject payload) {
    // TODO: Route incoming messages to the correct handler
    Serial.printf("[main] Received: %s\n", type.c_str());

    if (type == MsgType::DISPLAY_EXPRESSION) {
        // TODO: display.setExpression(payload["expression"]);
    } else if (type == MsgType::MOTION_EXECUTE) {
        // TODO: motor.execute(payload["action"], payload["params"]);
    } else if (type == MsgType::AUDIO_PLAY_TTS) {
        // TODO: fetch mp3 from payload["audio_url"] and play
    } else if (type == MsgType::AUDIO_PLAY_LOCAL) {
        // TODO: play local sound file payload["sound"]
    } else if (type == MsgType::SYSTEM_SHUTDOWN) {
        ESP.restart();
    }
}

void connectWiFi() {
    Serial.printf("[WiFi] Connecting to %s", WIFI_SSID);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }
    Serial.printf("\n[WiFi] Connected. IP: %s\n", WiFi.localIP().toString().c_str());
}

void setup() {
    Serial.begin(115200);
    delay(1000);
    Serial.println("[main] Xiao An Robot starting...");

    connectWiFi();

    // TODO: motor.begin();
    // TODO: servo.begin();
    // TODO: display.begin();
    // TODO: mic.begin();
    // TODO: cam.begin();

    wsClient.begin(BASE_STATION_IP, BASE_STATION_PORT, onControlMessage);
    Serial.println("[main] Setup complete.");
}

void loop() {
    wsClient.loop();

    // TODO: mic.streamLoop();  -- send audio frames to base station
    // TODO: cam.captureLoop(); -- send video frames every 5s
}
