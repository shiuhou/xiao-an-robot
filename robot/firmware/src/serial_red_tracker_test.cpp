#include <Arduino.h>
#include "esp_camera.h"

// USB Serial JPEG camera stream.
//
// Protocol:
//   PC sends one byte: 'F'
//   magic: 4 bytes "XAN1"
//   size : 4 bytes little-endian JPEG length
//   body : JPEG bytes
//
// Red-object tracking and overlay are done on the PC viewer side. Keeping the
// OV2640 in native JPEG mode avoids the colored noise seen with RGB565 capture.

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

// Keep the DRV8833 inputs quiet in this camera-only test.
// These match robot/firmware/src/motor_ctrl.h but are repeated here to avoid
// linking motor control code into the serial camera firmware.
#define MOTOR_PIN_L_IN1 1
#define MOTOR_PIN_L_IN2 2
#define MOTOR_PIN_R_IN1 47
#define MOTOR_PIN_R_IN2 38

static constexpr uint32_t SERIAL_BAUD = 2000000;
static constexpr uint8_t MAGIC[4] = {'X', 'A', 'N', '1'};
static constexpr uint8_t FRAME_REQUEST = 'F';

static void holdMotorsOff() {
    pinMode(MOTOR_PIN_L_IN1, OUTPUT);
    pinMode(MOTOR_PIN_L_IN2, OUTPUT);
    pinMode(MOTOR_PIN_R_IN1, OUTPUT);
    pinMode(MOTOR_PIN_R_IN2, OUTPUT);

    digitalWrite(MOTOR_PIN_L_IN1, LOW);
    digitalWrite(MOTOR_PIN_L_IN2, LOW);
    digitalWrite(MOTOR_PIN_R_IN1, LOW);
    digitalWrite(MOTOR_PIN_R_IN2, LOW);
}

static bool initCamera() {
    camera_config_t config = {};
    config.ledc_channel = LEDC_CHANNEL_1;
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
    config.pixel_format = PIXFORMAT_JPEG;
    config.frame_size = FRAMESIZE_QVGA;
    config.jpeg_quality = 12;
    config.fb_count = 2;
    config.fb_location = CAMERA_FB_IN_PSRAM;
    config.grab_mode = CAMERA_GRAB_LATEST;
    config.sccb_i2c_port = 1;

    esp_err_t err = esp_camera_init(&config);
    if (err != ESP_OK) {
        return false;
    }

    sensor_t *sensor = esp_camera_sensor_get();
    if (sensor) {
        sensor->set_framesize(sensor, FRAMESIZE_QVGA);
        sensor->set_quality(sensor, 12);
        sensor->set_brightness(sensor, 0);
        sensor->set_saturation(sensor, 0);
        sensor->set_whitebal(sensor, 1);
        sensor->set_awb_gain(sensor, 1);
    }
    return true;
}

static void sendJpegFrame(const uint8_t *jpgBuf, size_t jpgLen) {
    uint8_t lenBytes[4] = {
        (uint8_t)(jpgLen & 0xFF),
        (uint8_t)((jpgLen >> 8) & 0xFF),
        (uint8_t)((jpgLen >> 16) & 0xFF),
        (uint8_t)((jpgLen >> 24) & 0xFF),
    };
    Serial.write(MAGIC, sizeof(MAGIC));
    Serial.write(lenBytes, sizeof(lenBytes));
    Serial.write(jpgBuf, jpgLen);
}

void setup() {
    holdMotorsOff();

    Serial.begin(SERIAL_BAUD);
    Serial.setDebugOutput(false);
    delay(1500);

    holdMotorsOff();

    if (!initCamera()) {
        while (true) {
            holdMotorsOff();
            delay(1000);
        }
    }
}

void loop() {
    holdMotorsOff();

    if (!Serial.available()) {
        delay(1);
        return;
    }

    const int request = Serial.read();
    if (request != FRAME_REQUEST) {
        return;
    }

    camera_fb_t *fb = esp_camera_fb_get();
    if (!fb) {
        delay(100);
        return;
    }

    if (fb->format == PIXFORMAT_JPEG && fb->len > 0) {
        sendJpegFrame(fb->buf, fb->len);
    }
    esp_camera_fb_return(fb);
}
