#include "feature_flags.h"
#include "ota_update.h"

#if ENABLE_ARDUINO_OTA

#include <ArduinoOTA.h>

#include "debug_log.h"

#ifndef OTA_PASSWORD
#define OTA_PASSWORD ""
#endif

namespace {
OtaStartCallback gOnStart = nullptr;
}

void ota_set_on_start(OtaStartCallback callback) {
    gOnStart = callback;
}

void ota_begin(const char* hostname) {
    ArduinoOTA.setHostname(hostname);

    const char* password = OTA_PASSWORD;
    if (password != nullptr && password[0] != '\0') {
        ArduinoOTA.setPassword(password);
    }

    ArduinoOTA.onStart([]() {
        LOGW("OTA", "Update starting");
        if (gOnStart != nullptr) {
            gOnStart();
        }
    });
    ArduinoOTA.onEnd([]() {
        LOGI("OTA", "Update complete; rebooting");
    });
    ArduinoOTA.onProgress([](unsigned int progress, unsigned int total) {
        if (total == 0) {
            return;
        }
        LOGI("OTA", "Progress %u%%", (progress * 100U) / total);
    });
    ArduinoOTA.onError([](ota_error_t error) {
        LOGE("OTA", "Error %u", static_cast<unsigned int>(error));
    });

    ArduinoOTA.begin();
    LOGI("OTA",
         "Ready hostname=%s auth=%s",
         hostname,
         (password != nullptr && password[0] != '\0') ? "enabled" : "disabled");
}

void ota_loop() {
    ArduinoOTA.handle();
}

#endif
