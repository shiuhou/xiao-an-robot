#include "cam_stream.h"
#include "esp_camera.h"

// GOOUUU ESP32-S3-CAM v1.5 / OV2640 pin map.
// These pins are reserved for the camera.
constexpr int CAM_PIN_PWDN  = -1;
constexpr int CAM_PIN_RESET = -1;
constexpr int CAM_PIN_XCLK  = 15;
constexpr int CAM_PIN_SIOD  = 4;
constexpr int CAM_PIN_SIOC  = 5;

constexpr int CAM_PIN_D0 = 11;
constexpr int CAM_PIN_D1 = 9;
constexpr int CAM_PIN_D2 = 8;
constexpr int CAM_PIN_D3 = 10;
constexpr int CAM_PIN_D4 = 12;
constexpr int CAM_PIN_D5 = 18;
constexpr int CAM_PIN_D6 = 17;
constexpr int CAM_PIN_D7 = 16;

constexpr int CAM_PIN_VSYNC = 6;
constexpr int CAM_PIN_HREF  = 7;
constexpr int CAM_PIN_PCLK  = 13;

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
    Serial.println("[Cam] Camera ready.");
}

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

bool CamStream::isActive() {
    return _active;
}
