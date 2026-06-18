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

String currentExpression = Expression::IDLE;
String currentMotion     = "idle";
String currentCamera     = "cam_off";

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
    if (strcmp(action, MotionAction::TILT_HEAD) == 0) {
        return params["angle_deg"] | params["angle"] | 0.0f;
    }
    if (strcmp(action, MotionAction::WIGGLE_EARS) == 0 ||
        strcmp(action, MotionAction::NOD_HEAD) == 0) {
        return params["count"] | 0.0f;
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
    const int8_t motorPins[] = {
        PIN_MOTOR_L_IN1,
        PIN_MOTOR_L_IN2,
        PIN_MOTOR_R_IN1,
        PIN_MOTOR_R_IN2,
    };

    for (int8_t pin : motorPins) {
        if (pin >= 0) {
            pinMode(pin, OUTPUT);
            digitalWrite(pin, LOW);
        }
    }
}

void onControlMessage(const String& type, JsonObject payload) {
    Serial.printf("[main] Dispatch: %s\n", type.c_str());

    if (type == MsgType::SYSTEM_WELCOME) {
        Serial.println("[main] Session started with base station");
        sendCurrentStatus();

    } else if (type == MsgType::DISPLAY_EXPRESSION) {
        const char* expr      = payload["expression"] | Expression::IDLE;
        int         intensity = payload["intensity"]  | 5;
        display_emotion(expr, intensity);
        currentExpression = expr;
        sendCurrentStatus();

    } else if (type == MsgType::MOTION_EXECUTE) {
        const char* action   = payload["action"] | MotionAction::STOP;
        const char* actionId = payload["action_id"] | "";
        float       param    = motionParamFromPayload(payload, action);

        currentMotion = action;
        sendCurrentStatus();

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

        currentMotion = "idle";
        wsClient.sendMotionCompleted(
            actionId,
            "success",
            finalPositionForAction(action),
            true);
        sendCurrentStatus();

    } else if (type == MsgType::AUDIO_PLAY_TTS) {
        // TODO: download payload["audio_url"] and feed to I2S DAC
        Serial.printf("[TTS] Play: %s\n", (const char*)(payload["audio_url"] | ""));
        wsClient.sendError(
            ErrorCode::AUDIO_UNSUPPORTED,
            "info",
            "audio.play_tts received but I2S TTS playback is not implemented yet");

    } else if (type == MsgType::AUDIO_PLAY_LOCAL) {
        // TODO: play sound file from SPIFFS/LittleFS
        Serial.printf("[Audio] Local: %s\n", (const char*)(payload["sound"] | ""));
        wsClient.sendError(
            ErrorCode::AUDIO_UNSUPPORTED,
            "info",
            "audio.play_local received but local audio playback is not implemented yet");

    } else if (type == MsgType::CONFIG_UPDATE) {
        // TODO: persist updated fields to NVS
        Serial.println("[main] Config update received");

    } else if (type == MsgType::SYSTEM_SHUTDOWN) {
        Serial.println("[main] Shutdown requested — restarting");
        delay(100);
        ESP.restart();

    } else {
        Serial.printf("[main] Unknown message type: %s\n", type.c_str());
        wsClient.sendError(
            ErrorCode::UNSUPPORTED_COMMAND,
            "warning",
            type.c_str());
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
    holdMotorPinsLowBeforeSerial();

    Serial.begin(115200);
    delay(1000);
    Serial.println("[main] Xiao An Robot starting...");

    connectWiFi();

    motor.begin();
    servo.begin();
    display_init();
    // TODO: mic.begin();
    // TODO: cam.begin();
    currentCamera = cam.isActive() ? "cam_ok" : "cam_off";

    wsClient.begin(BASE_STATION_IP, BASE_STATION_PORT, onControlMessage);
    Serial.println("[main] Setup complete.");
}

void loop() {
    wsClient.loop();

    // TODO: mic.streamLoop();  -- send audio frames to base station
    // TODO: cam.captureLoop(); -- send video frames every 5s
}
