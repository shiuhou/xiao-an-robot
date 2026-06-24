#include "cam_stream.h"
#include "board_pins.h"
#include "feature_flags.h"
#include "esp_camera.h"

#if ENABLE_WS_INTEGRATED
#include "ws_client.h"
#include "debug_log.h"
#endif

void CamStream::begin() {
    if (_active) {
        return;
    }

    Serial.println("[Cam] Initializing GOOUUU ESP32-S3-CAM OV2640...");
    Serial.printf("[Cam] PSRAM: %s\n", psramFound() ? "yes" : "no");

    camera_config_t config = {};
    config.ledc_channel = LEDC_CHANNEL_1;
    config.ledc_timer   = LEDC_TIMER_1;
    config.pin_d0       = CAM_PIN_D0;
    config.pin_d1       = CAM_PIN_D1;
    config.pin_d2       = CAM_PIN_D2;
    config.pin_d3       = CAM_PIN_D3;
    config.pin_d4       = CAM_PIN_D4;
    config.pin_d5       = CAM_PIN_D5;
    config.pin_d6       = CAM_PIN_D6;
    config.pin_d7       = CAM_PIN_D7;
    config.pin_xclk     = CAM_PIN_XCLK;
    config.pin_pclk     = CAM_PIN_PCLK;
    config.pin_vsync    = CAM_PIN_VSYNC;
    config.pin_href     = CAM_PIN_HREF;
    config.pin_sccb_sda = CAM_PIN_SIOD;
    config.pin_sccb_scl = CAM_PIN_SIOC;
    config.pin_pwdn     = CAM_PIN_PWDN;
    config.pin_reset    = CAM_PIN_RESET;
    config.xclk_freq_hz = 10000000;
    config.pixel_format = PIXFORMAT_JPEG;
    config.frame_size   = FRAMESIZE_QVGA;
    config.jpeg_quality = 10;
    config.fb_count     = psramFound() ? 2 : 1;
    config.fb_location  = psramFound() ? CAMERA_FB_IN_PSRAM : CAMERA_FB_IN_DRAM;
    config.grab_mode    = CAMERA_GRAB_WHEN_EMPTY;
    config.sccb_i2c_port = 1;

    esp_err_t err = esp_camera_init(&config);
    if (err != ESP_OK) {
        Serial.printf("[Cam] esp_camera_init failed: 0x%x\n", err);
        esp_camera_deinit();
        _active = false;
        return;
    }

    sensor_t* sensor = esp_camera_sensor_get();
    if (sensor) {
        sensor->set_framesize(sensor, FRAMESIZE_QVGA);
        sensor->set_quality(sensor, 10);
    }

    _active = true;
    _lastCapture = 0;
    _captureOk = 0;
    _captureFail = 0;
#if ENABLE_WS_INTEGRATED
    _frameId = 0;
#endif
    Serial.println("[Cam] Camera ready.");
}

#if ENABLE_WS_INTEGRATED

void CamStream::captureLoop(WSClient& ws) {
    if (!_active || !ws.isVideoConnected()) {
        return;
    }

    const uint32_t now = millis();
    if (now - _lastCapture < CAPTURE_INTERVAL_MS) {
        return;
    }
    _lastCapture = now;

    camera_fb_t* fb = esp_camera_fb_get();
    if (!fb || fb->format != PIXFORMAT_JPEG) {
        ++_captureFail;
        if (fb) {
            esp_camera_fb_return(fb);
        }
        LOGE("Cam", "capture fail count=%lu", static_cast<unsigned long>(_captureFail));
        return;
    }

    ++_captureOk;
    ++_frameId;
    const uint16_t width = fb->width ? fb->width : 320;
    const uint16_t height = fb->height ? fb->height : 240;

    ws.sendVideoFrameMeta(_frameId, width, height);
    if (!ws.sendVideoBinary(fb->buf, fb->len, millis() / 1000)) {
        LOGW("Cam", "video binary send failed, fallback base64");
        ws.sendVideoFrameBase64(fb->buf, fb->len, _frameId, width, height);
    }

    LOGI("Cam", "frame #%lu %ux%u len=%u ok=%lu",
         static_cast<unsigned long>(_frameId), width, height, fb->len,
         static_cast<unsigned long>(_captureOk));
    esp_camera_fb_return(fb);
}

#else

void CamStream::captureLoop() {
    if (!_active) {
        return;
    }

    uint32_t now = millis();
    if (now - _lastCapture < CAPTURE_INTERVAL_MS) {
        return;
    }
    _lastCapture = now;

    camera_fb_t* fb = esp_camera_fb_get();
    if (!fb) {
        ++_captureFail;
        Serial.printf("[Cam] Capture failed. ok=%lu fail=%lu\n",
                      static_cast<unsigned long>(_captureOk),
                      static_cast<unsigned long>(_captureFail));
        return;
    }

    ++_captureOk;
    Serial.printf("[Cam] Frame %lu: %ux%u len=%u format=%d\n",
                  static_cast<unsigned long>(_captureOk),
                  fb->width,
                  fb->height,
                  fb->len,
                  fb->format);

    esp_camera_fb_return(fb);
}

#endif

bool CamStream::isActive() {
    return _active;
}
