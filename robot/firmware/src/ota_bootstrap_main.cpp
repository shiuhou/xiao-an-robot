/**
 * Stable WiFi OTA bootstrap.
 *
 * Use this env as a recovery/upload bridge while integrated peripherals are
 * still being brought up. It avoids camera, mic, speaker, WebSocket, and face
 * init so ArduinoOTA can stay alive reliably.
 */

#include <Arduino.h>
#include <WiFi.h>

#include "debug_log.h"
#include "motor_ctrl.h"
#include "ota_update.h"

#if __has_include("config.local.h")
#include "config.local.h"
#endif

#ifndef WIFI_SSID
#define WIFI_SSID "YOUR_WIFI_SSID"
#endif
#ifndef WIFI_PASSWORD
#define WIFI_PASSWORD "YOUR_WIFI_PASSWORD"
#endif
#ifndef OTA_HOSTNAME
#define OTA_HOSTNAME "xiao-an-esp32"
#endif
#ifndef OTA_BOOT_BUILD_ID
#define OTA_BOOT_BUILD_ID "ota-bootstrap-diagnostic"
#endif

namespace {
uint32_t lastStatusMs = 0;
uint32_t lastReconnectMs = 0;

void holdMotorPinsLow() {
    const int8_t pins[] = {PIN_MOTOR_L_IN1, PIN_MOTOR_L_IN2, PIN_MOTOR_R_IN1, PIN_MOTOR_R_IN2};
    for (int8_t pin : pins) {
        if (pin >= 0) {
            pinMode(pin, OUTPUT);
            digitalWrite(pin, LOW);
        }
    }
}

void connectWiFi() {
    WiFi.mode(WIFI_STA);
    WiFi.setSleep(false);

    LOGI("OTA_BOOT", "Scanning WiFi networks");
    const int networkCount = WiFi.scanNetworks(false, true);
    bool foundTarget = false;
    if (networkCount <= 0) {
        LOGW("OTA_BOOT", "No WiFi networks found");
    } else {
        LOGI("OTA_BOOT", "Found %d WiFi networks", networkCount);
        for (int i = 0; i < networkCount; ++i) {
            const String ssid = WiFi.SSID(i);
            if (ssid == WIFI_SSID) {
                foundTarget = true;
                LOGI("OTA_BOOT",
                     "Target SSID found: %s RSSI=%d channel=%d",
                     ssid.c_str(),
                     WiFi.RSSI(i),
                     WiFi.channel(i));
            }
        }
    }
    if (!foundTarget) {
        LOGW("OTA_BOOT", "Target SSID not seen: %s", WIFI_SSID);
    }

    WiFi.disconnect(false);
    delay(100);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    lastReconnectMs = millis();

    LOGI("OTA_BOOT", "Connecting SSID=%s", WIFI_SSID);
    const uint32_t start = millis();
    while (WiFi.status() != WL_CONNECTED && millis() - start < 30000) {
        delay(500);
        Serial.print(".");
    }
    Serial.println();

    if (WiFi.status() != WL_CONNECTED) {
        LOGE("OTA_BOOT", "WiFi connect timeout status=%d", WiFi.status());
        return;
    }

    LOGI("OTA_BOOT",
         "WiFi connected IP=%s RSSI=%d",
         WiFi.localIP().toString().c_str(),
         WiFi.RSSI());
}
}  // namespace

void setup() {
    holdMotorPinsLow();

    Serial.begin(115200);
    delay(1000);
    LOGI("OTA_BOOT", "Xiao An OTA bootstrap starting build=%s", OTA_BOOT_BUILD_ID);

    connectWiFi();
    ota_set_on_start([]() {
        holdMotorPinsLow();
        LOGW("OTA_BOOT", "OTA update accepted; motors held low");
    });
    ota_begin(OTA_HOSTNAME);
}

void loop() {
    if (WiFi.status() != WL_CONNECTED) {
        if (millis() - lastReconnectMs > 10000) {
            lastReconnectMs = millis();
            LOGW("OTA_BOOT", "WiFi disconnected status=%d; retry begin()", WiFi.status());
            WiFi.disconnect(false);
            delay(20);
            WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
        }
    }

    ota_loop();

    if (millis() - lastStatusMs > 5000) {
        lastStatusMs = millis();
        LOGI("OTA_BOOT",
             "alive build=%s ip=%s rssi=%d",
             OTA_BOOT_BUILD_ID,
             WiFi.localIP().toString().c_str(),
             WiFi.RSSI());
    }

    delay(5);
}
