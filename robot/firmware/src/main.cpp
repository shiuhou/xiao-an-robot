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

WSClient        wsClient;
MotorController motor;
ServoController servo;
MicStream       mic;
CamStream       cam;

void onControlMessage(const String& type, JsonObject payload) {
    Serial.printf("[main] Dispatch: %s\n", type.c_str());

    if (type == MsgType::SYSTEM_WELCOME) {
        Serial.println("[main] Session started with base station");

    } else if (type == MsgType::DISPLAY_EXPRESSION) {
        const char* expr      = payload["expression"] | Expression::IDLE;
        int         intensity = payload["intensity"]  | 5;
        display_emotion(expr, intensity);

    } else if (type == MsgType::MOTION_EXECUTE) {
        const char* action = payload["action"] | MotionAction::STOP;
        float       param  = payload["param"]  | 0.0f;

        // servo actions: head tilt, ear wiggle, nod
        if (strcmp(action, MotionAction::TILT_HEAD) == 0) {
            servo.setHeadTilt((int)param);
        } else if (strcmp(action, MotionAction::WIGGLE_EARS) == 0) {
            servo.wiggleEars((int)param > 0 ? (int)param : 3);
        } else if (strcmp(action, MotionAction::NOD_HEAD) == 0) {
            servo.nodHead((int)param > 0 ? (int)param : 2);
        } else {
            // motor actions: move, turn, stop
            motor.execute(action, param);
        }

    } else if (type == MsgType::AUDIO_PLAY_TTS) {
        // TODO: download payload["audio_url"] and feed to I2S DAC
        Serial.printf("[TTS] Play: %s\n", (const char*)(payload["audio_url"] | ""));

    } else if (type == MsgType::AUDIO_PLAY_LOCAL) {
        // TODO: play sound file from SPIFFS/LittleFS
        Serial.printf("[Audio] Local: %s\n", (const char*)(payload["sound"] | ""));

    } else if (type == MsgType::CONFIG_UPDATE) {
        // TODO: persist updated fields to NVS
        Serial.println("[main] Config update received");

    } else if (type == MsgType::SYSTEM_SHUTDOWN) {
        Serial.println("[main] Shutdown requested — restarting");
        delay(100);
        ESP.restart();

    } else {
        Serial.printf("[main] Unknown message type: %s\n", type.c_str());
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

    motor.begin();
    servo.begin();
    display_init();
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
