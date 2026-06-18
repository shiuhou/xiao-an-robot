#include <Arduino.h>
#include "esp_camera.h"
#include "motor_ctrl.h"

// USB Serial visual-servo firmware.
//
// Protocol:
//   PC -> ESP32: 'F' requests one JPEG frame.
//   ESP32 -> PC: "XAN1" + uint32 little-endian JPEG length + JPEG bytes.
//   PC -> ESP32: a/d/w/s/x requests one short motor pulse or stop.
//
// QR detection stays on the PC. This keeps ESP32-S3 work limited to camera I/O
// and motor actuation, which is much easier to debug during first bring-up.

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

#ifndef QR_SERVO_SERIAL_BAUD
#define QR_SERVO_SERIAL_BAUD 2000000
#endif

#ifndef QR_SERVO_TURN_SPEED
#define QR_SERVO_TURN_SPEED 100
#endif

#ifndef QR_SERVO_FORWARD_SPEED
#define QR_SERVO_FORWARD_SPEED 90
#endif

#ifndef QR_SERVO_BACKWARD_SPEED
#define QR_SERVO_BACKWARD_SPEED 80
#endif

#ifndef QR_SERVO_PULSE_MS
#define QR_SERVO_PULSE_MS 80
#endif

#ifndef QR_SERVO_MAX_PULSE_MS
#define QR_SERVO_MAX_PULSE_MS 120
#endif

static constexpr uint8_t MAGIC[4] = {'X', 'A', 'N', '1'};
static constexpr uint8_t FRAME_REQUEST = 'F';
static constexpr uint32_t BOOT_DELAY_MS = 1500;
static constexpr uint32_t COMMAND_GAP_MS = 20;

MotorController motor;

static void holdMotorPinsLow() {
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

static bool initCamera() {
    camera_config_t config = {};
    config.ledc_channel = LEDC_CHANNEL_7;
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

    const esp_err_t err = esp_camera_init(&config);
    if (err != ESP_OK) {
        Serial.printf("[QRServo][ERROR] camera init failed err=0x%x\n", err);
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

    Serial.println("[QRServo] camera ready: JPEG QVGA 320x240");
    return true;
}

static void sendJpegFrame(const uint8_t *jpgBuf, size_t jpgLen) {
    const uint8_t lenBytes[4] = {
        static_cast<uint8_t>(jpgLen & 0xFF),
        static_cast<uint8_t>((jpgLen >> 8) & 0xFF),
        static_cast<uint8_t>((jpgLen >> 16) & 0xFF),
        static_cast<uint8_t>((jpgLen >> 24) & 0xFF),
    };

    Serial.write(MAGIC, sizeof(MAGIC));
    Serial.write(lenBytes, sizeof(lenBytes));
    Serial.write(jpgBuf, jpgLen);
}

static void captureAndSendFrame() {
    camera_fb_t *fb = esp_camera_fb_get();
    if (!fb) {
        Serial.println("[QRServo][WARN] capture failed");
        delay(20);
        return;
    }

    if (fb->format == PIXFORMAT_JPEG && fb->len > 0) {
        sendJpegFrame(fb->buf, fb->len);
    } else {
        Serial.println("[QRServo][WARN] captured frame is not JPEG");
    }
    esp_camera_fb_return(fb);
}

static void motorPulse(char command) {
    const uint32_t pulseMs = min<uint32_t>(QR_SERVO_PULSE_MS, QR_SERVO_MAX_PULSE_MS);

    if (command == 'a' || command == 'A') {
        Serial.printf("[QRServo][MOVE] left speed=%d pulse_ms=%lu\n",
                      QR_SERVO_TURN_SPEED,
                      static_cast<unsigned long>(pulseMs));
        motor.turnLeft(QR_SERVO_TURN_SPEED);
    } else if (command == 'd' || command == 'D') {
        Serial.printf("[QRServo][MOVE] right speed=%d pulse_ms=%lu\n",
                      QR_SERVO_TURN_SPEED,
                      static_cast<unsigned long>(pulseMs));
        motor.turnRight(QR_SERVO_TURN_SPEED);
    } else if (command == 'w' || command == 'W') {
        Serial.printf("[QRServo][MOVE] forward speed=%d pulse_ms=%lu\n",
                      QR_SERVO_FORWARD_SPEED,
                      static_cast<unsigned long>(pulseMs));
        motor.forward(QR_SERVO_FORWARD_SPEED);
    } else if (command == 's' || command == 'S') {
        Serial.printf("[QRServo][MOVE] backward speed=%d pulse_ms=%lu\n",
                      QR_SERVO_BACKWARD_SPEED,
                      static_cast<unsigned long>(pulseMs));
        motor.backward(QR_SERVO_BACKWARD_SPEED);
    } else {
        return;
    }

    delay(pulseMs);
    motor.stop();
    Serial.println("[QRServo][STOP] pulse complete");
    delay(COMMAND_GAP_MS);
}

static void printHelp() {
    Serial.println("[QRServo] commands:");
    Serial.println("[QRServo]   F=request JPEG frame");
    Serial.println("[QRServo]   a/d=left/right pulse, w/s=forward/backward pulse, x=stop");
    Serial.println("[QRServo] PC script should own the serial port during visual servoing.");
}

static void handleCommand(char command) {
    if (command == '\r' || command == '\n') {
        return;
    }

    if (command == FRAME_REQUEST) {
        captureAndSendFrame();
        return;
    }

    if (command == 'a' || command == 'A' ||
        command == 'd' || command == 'D' ||
        command == 'w' || command == 'W' ||
        command == 's' || command == 'S') {
        motorPulse(command);
        return;
    }

    if (command == 'x' || command == 'X' || command == ' ') {
        motor.stop();
        Serial.println("[QRServo][STOP] command stop");
        return;
    }

    if (command == '?' || command == 'h' || command == 'H') {
        printHelp();
        return;
    }

    Serial.printf("[QRServo][WARN] unknown command '%c'\n", command);
}

void setup() {
    holdMotorPinsLow();

    Serial.begin(QR_SERVO_SERIAL_BAUD);
    Serial.setDebugOutput(false);
    delay(BOOT_DELAY_MS);

    Serial.println();
    Serial.println("[QRServo] Xiao-An QR visual servo serial bridge");
    Serial.printf("[QRServo] baud=%d turn_speed=%d forward_speed=%d backward_speed=%d pulse_ms=%d\n",
                  QR_SERVO_SERIAL_BAUD,
                  QR_SERVO_TURN_SPEED,
                  QR_SERVO_FORWARD_SPEED,
                  QR_SERVO_BACKWARD_SPEED,
                  QR_SERVO_PULSE_MS);

    motor.begin();
    motor.stop();

    if (!initCamera()) {
        motor.stop();
        Serial.println("[QRServo][ERROR] stopped: camera init failed");
        return;
    }

    printHelp();
}

void loop() {
    if (Serial.available() <= 0) {
        delay(1);
        return;
    }

    const char command = static_cast<char>(Serial.read());
    handleCommand(command);
}
