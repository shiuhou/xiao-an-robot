#include <Arduino.h>
#include "esp_camera.h"
#include "motor_ctrl.h"

// Keep Face Center test
//
// Minimal camera -> motor demo for hardware validation. This is not a real
// face detector. It looks for a stable skin-colored blob in QQVGA RGB565 frames
// and nudges the chassis left/right until the blob is near the image center.

// GOOUUU ESP32-S3-CAM v1.5 camera pin map.
#define CAM_PIN_PWDN -1
#define CAM_PIN_RESET -1
#define CAM_PIN_XCLK 15
#define CAM_PIN_SIOD 4
#define CAM_PIN_SIOC 5

#define CAM_PIN_D0 11
#define CAM_PIN_D1 9
#define CAM_PIN_D2 8
#define CAM_PIN_D3 10
#define CAM_PIN_D4 12
#define CAM_PIN_D5 18
#define CAM_PIN_D6 17
#define CAM_PIN_D7 16

#define CAM_PIN_VSYNC 6
#define CAM_PIN_HREF 7
#define CAM_PIN_PCLK 13

#ifndef KEEPFACE_MIN_PIXELS
#define KEEPFACE_MIN_PIXELS 80
#endif

#ifndef KEEPFACE_MIN_WIDTH_PX
#define KEEPFACE_MIN_WIDTH_PX 18
#endif

#ifndef KEEPFACE_MIN_HEIGHT_PX
#define KEEPFACE_MIN_HEIGHT_PX 24
#endif

#ifndef KEEPFACE_CENTER_DEADBAND_PX
#define KEEPFACE_CENTER_DEADBAND_PX 16
#endif

#ifndef KEEPFACE_TURN_SPEED
#define KEEPFACE_TURN_SPEED 105
#endif

#ifndef KEEPFACE_TURN_PULSE_MS
#define KEEPFACE_TURN_PULSE_MS 65
#endif

#ifndef KEEPFACE_SEARCH_PULSE_MS
#define KEEPFACE_SEARCH_PULSE_MS 55
#endif

static constexpr int FRAME_WIDTH = 160;
static constexpr uint32_t LOOP_DELAY_MS = 170;
static constexpr uint32_t SEARCH_INTERVAL_MS = 1300;
static constexpr uint32_t MAX_MOTION_PULSE_MS = 90;
static constexpr uint32_t CAMERA_FAIL_SAFE_MS = 1200;
static constexpr uint32_t TARGET_LOST_SAFE_MS = 3500;
static constexpr uint32_t STATUS_INTERVAL_MS = 1000;

MotorController motor;
static bool motorIsStopped = true;

struct FaceEstimate {
    bool seen = false;
    bool candidate = false;
    int centerX = FRAME_WIDTH / 2;
    int pixels = 0;
    int minX = FRAME_WIDTH;
    int maxX = 0;
    int minY = 120;
    int maxY = 0;
    int width = 0;
    int height = 0;
    int error = 0;
};

static bool isSkinLike(uint8_t r, uint8_t g, uint8_t b) {
    const int maxC = max((int)r, max((int)g, (int)b));
    const int minC = min((int)r, min((int)g, (int)b));

    // Conservative RGB gate for indoor skin-like regions. It deliberately
    // rejects very dark pixels and flat warm backgrounds.
    return r >= 58 &&
           g >= 32 &&
           b >= 18 &&
           r > g &&
           g >= b &&
           (r - g) >= 6 &&
           (r - b) >= 22 &&
           (maxC - minC) >= 24;
}

static FaceEstimate estimateFaceCenter(camera_fb_t *fb) {
    FaceEstimate estimate;
    if (!fb || fb->format != PIXFORMAT_RGB565 || fb->len < 2) {
        return estimate;
    }

    uint32_t weightedX = 0;
    uint32_t count = 0;
    const uint16_t width = fb->width;
    const uint16_t height = fb->height;
    const uint8_t *buf = fb->buf;

    // Sample every second pixel to keep the loop fast on ESP32-S3.
    for (uint16_t y = 0; y < height; y += 2) {
        for (uint16_t x = 0; x < width; x += 2) {
            const size_t idx = ((size_t)y * width + x) * 2;
            if (idx + 1 >= fb->len) {
                continue;
            }

            const uint16_t p = ((uint16_t)buf[idx] << 8) | buf[idx + 1];
            const uint8_t r = ((p >> 11) & 0x1F) << 3;
            const uint8_t g = ((p >> 5) & 0x3F) << 2;
            const uint8_t b = (p & 0x1F) << 3;

            if (isSkinLike(r, g, b)) {
                weightedX += x;
                count++;
                estimate.minX = min(estimate.minX, (int)x);
                estimate.maxX = max(estimate.maxX, (int)x);
                estimate.minY = min(estimate.minY, (int)y);
                estimate.maxY = max(estimate.maxY, (int)y);
            }
        }
    }

    estimate.pixels = (int)count;
    estimate.candidate = count >= KEEPFACE_MIN_PIXELS;
    if (count > 0) {
        estimate.centerX = (int)(weightedX / count);
        estimate.width = estimate.maxX - estimate.minX + 1;
        estimate.height = estimate.maxY - estimate.minY + 1;
    }

    estimate.seen = estimate.candidate &&
                    estimate.width >= KEEPFACE_MIN_WIDTH_PX &&
                    estimate.height >= KEEPFACE_MIN_HEIGHT_PX;
    estimate.error = estimate.centerX - ((int)width / 2);
    return estimate;
}

static camera_fb_t *captureFrame(uint8_t attempts = 3) {
    for (uint8_t attempt = 1; attempt <= attempts; ++attempt) {
        camera_fb_t *fb = esp_camera_fb_get();
        if (fb) {
            return fb;
        }
        Serial.printf("[KeepFace][WARN] capture failed attempt=%u/%u\n", attempt, attempts);
        delay(80);
    }
    return nullptr;
}

static bool initCamera() {
    camera_config_t config = {};
    config.ledc_channel = LEDC_CHANNEL_7;  // avoid motor PWM channels 0-3
    config.ledc_timer = LEDC_TIMER_1;
    config.pin_d0 = CAM_PIN_D0;
    config.pin_d1 = CAM_PIN_D1;
    config.pin_d2 = CAM_PIN_D2;
    config.pin_d3 = CAM_PIN_D3;
    config.pin_d4 = CAM_PIN_D4;
    config.pin_d5 = CAM_PIN_D5;
    config.pin_d6 = CAM_PIN_D6;
    config.pin_d7 = CAM_PIN_D7;
    config.pin_xclk = CAM_PIN_XCLK;
    config.pin_pclk = CAM_PIN_PCLK;
    config.pin_vsync = CAM_PIN_VSYNC;
    config.pin_href = CAM_PIN_HREF;
    config.pin_sccb_sda = CAM_PIN_SIOD;
    config.pin_sccb_scl = CAM_PIN_SIOC;
    config.pin_pwdn = CAM_PIN_PWDN;
    config.pin_reset = CAM_PIN_RESET;
    config.xclk_freq_hz = 10000000;
    config.pixel_format = PIXFORMAT_RGB565;
    config.frame_size = FRAMESIZE_QQVGA;
    config.fb_count = 1;
    config.fb_location = CAMERA_FB_IN_PSRAM;
    config.grab_mode = CAMERA_GRAB_LATEST;
    config.sccb_i2c_port = 1;

    esp_err_t err = esp_camera_init(&config);
    if (err != ESP_OK) {
        Serial.printf("[KeepFace][ERROR] camera init failed err=0x%x\n", err);
        return false;
    }

    sensor_t *sensor = esp_camera_sensor_get();
    if (sensor) {
        sensor->set_framesize(sensor, FRAMESIZE_QQVGA);
        sensor->set_brightness(sensor, 0);
        sensor->set_saturation(sensor, 0);
        sensor->set_whitebal(sensor, 1);
        sensor->set_awb_gain(sensor, 1);
    }

    Serial.printf("[KeepFace] camera ready format=RGB565 frame=QQVGA width=%d height=%d\n",
                  FRAME_WIDTH,
                  120);
    return true;
}

static void safeStop(const char *reason) {
    if (!motorIsStopped) {
        motor.stop();
        motorIsStopped = true;
        Serial.printf("[KeepFace][STOP] reason=%s\n", reason);
    }
}

static void pulseTurn(bool left, uint32_t ms, const char *reason) {
    const uint32_t pulseMs = min(ms, MAX_MOTION_PULSE_MS);
    Serial.printf("[KeepFace][MOVE] dir=%s speed=%d pulse_ms=%lu reason=%s\n",
                  left ? "left" : "right",
                  KEEPFACE_TURN_SPEED,
                  static_cast<unsigned long>(pulseMs),
                  reason);
    if (left) {
        motor.turnLeft(KEEPFACE_TURN_SPEED);
    } else {
        motor.turnRight(KEEPFACE_TURN_SPEED);
    }
    motorIsStopped = false;
    delay(pulseMs);
    safeStop("pulse complete");
}

static void handleFaceEstimate(const FaceEstimate &face) {
    static uint32_t lastSearchMs = 0;
    static uint32_t lastSeenMs = 0;
    static uint32_t lastStatusMs = 0;
    static bool searchLeft = true;

    const uint32_t now = millis();

    if (!face.seen) {
        safeStop(face.candidate ? "weak candidate rejected" : "target not found");

        if (now - lastStatusMs >= STATUS_INTERVAL_MS) {
            Serial.printf("[KeepFace][SCAN] seen=0 candidate=%d pixels=%d box=%dx%d center_x=%d thresholds pixels>=%d box>=%dx%d\n",
                          face.candidate ? 1 : 0,
                          face.pixels,
                          face.width,
                          face.height,
                          face.centerX,
                          KEEPFACE_MIN_PIXELS,
                          KEEPFACE_MIN_WIDTH_PX,
                          KEEPFACE_MIN_HEIGHT_PX);
            lastStatusMs = now;
        }

        if (lastSeenMs != 0 && now - lastSeenMs > TARGET_LOST_SAFE_MS) {
            lastSeenMs = 0;
            Serial.println("[KeepFace][SAFE] target lost for >3.5s, search resumes slowly");
        }

        if (now - lastSearchMs >= SEARCH_INTERVAL_MS) {
            Serial.printf("[KeepFace][SEARCH] dir=%s pulse_ms=%d\n",
                          searchLeft ? "left" : "right",
                          KEEPFACE_SEARCH_PULSE_MS);
            if (searchLeft) {
                pulseTurn(true, KEEPFACE_SEARCH_PULSE_MS, "search");
            } else {
                pulseTurn(false, KEEPFACE_SEARCH_PULSE_MS, "search");
            }
            searchLeft = !searchLeft;
            lastSearchMs = millis();
        }
        return;
    }

    lastSeenMs = now;
    Serial.printf("[KeepFace][TRACK] seen=1 pixels=%d box=%dx%d x=%d..%d center_x=%d error=%d deadband=%d\n",
                  face.pixels,
                  face.width,
                  face.height,
                  face.minX,
                  face.maxX,
                  face.centerX,
                  face.error,
                  KEEPFACE_CENTER_DEADBAND_PX);

    if (abs(face.error) <= KEEPFACE_CENTER_DEADBAND_PX) {
        safeStop("centered");
    } else if (face.error < 0) {
        pulseTurn(true, KEEPFACE_TURN_PULSE_MS, "target left");
    } else {
        pulseTurn(false, KEEPFACE_TURN_PULSE_MS, "target right");
    }
}

void setup() {
    Serial.begin(115200);
    delay(1000);
    Serial.println();
    Serial.println("[KeepFace] keep face center test");
    Serial.printf("[KeepFace] config min_pixels=%d min_box=%dx%d deadband=%d turn_speed=%d turn_pulse_ms=%d search_pulse_ms=%d\n",
                  KEEPFACE_MIN_PIXELS,
                  KEEPFACE_MIN_WIDTH_PX,
                  KEEPFACE_MIN_HEIGHT_PX,
                  KEEPFACE_CENTER_DEADBAND_PX,
                  KEEPFACE_TURN_SPEED,
                  KEEPFACE_TURN_PULSE_MS,
                  KEEPFACE_SEARCH_PULSE_MS);

    motor.begin();

    if (!initCamera()) {
        safeStop("camera init failed");
        return;
    }

    Serial.println("[KeepFace] ready: put a face-like region in front of the camera");
}

void loop() {
    static uint32_t lastGoodFrameMs = 0;

    camera_fb_t *fb = captureFrame();
    if (!fb) {
        if (lastGoodFrameMs == 0 || millis() - lastGoodFrameMs >= CAMERA_FAIL_SAFE_MS) {
            safeStop("camera capture unavailable");
        }
        delay(LOOP_DELAY_MS);
        return;
    }

    lastGoodFrameMs = millis();
    FaceEstimate face = estimateFaceCenter(fb);
    esp_camera_fb_return(fb);

    handleFaceEstimate(face);
    delay(LOOP_DELAY_MS);
}
