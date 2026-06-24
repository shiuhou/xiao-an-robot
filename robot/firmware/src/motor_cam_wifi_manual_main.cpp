#include <Arduino.h>
#include <WebServer.h>
#include <WiFi.h>

#include "esp_camera.h"
#include "esp_http_server.h"
#include "motor_ctrl.h"
#include "board_pins.h"

namespace {

constexpr const char* WIFI_SSID = "XiaoAn-Motor";
constexpr const char* WIFI_PASSWORD = "12345678";

constexpr int MOTOR_SPEED_MIN = 40;
constexpr int MOTOR_SPEED_MAX = 180;
constexpr int MOTOR_SPEED_STEP = 10;
constexpr int MOTOR_SPEED_DEFAULT = 110;
constexpr uint32_t MOTOR_DEADMAN_MS = 350;

constexpr int JPEG_QUALITY_VGA = 10;
constexpr int JPEG_QUALITY_QVGA = 12;
constexpr uint8_t CAMERA_FB_COUNT = 2;
constexpr uint32_t STREAM_MIN_FRAME_MS_VGA = 100;

WebServer server(80);
httpd_handle_t streamHttpd = nullptr;
MotorController motor;
SemaphoreHandle_t cameraMutex = nullptr;

int motorSpeed = MOTOR_SPEED_DEFAULT;
uint32_t motorHoldUntilMs = 0;
bool motorActive = false;
bool cameraReady = false;
char lastCommand = 'x';
const char* cameraMode = "qvga320";
uint16_t cameraWidth = 320;
uint16_t cameraHeight = 240;
volatile bool pendingModeSwitch = false;
char pendingModeName[12] = {};

const char* STREAM_CONTENT_TYPE = "multipart/x-mixed-replace; boundary=frame";
const char* STREAM_BOUNDARY = "\r\n--frame\r\n";
const char* STREAM_PART = "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

// ESP32 only serves MJPEG. Vision/QR/face runs on PC or base station.
const char INDEX_HTML[] PROGMEM = R"HTML(
<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1,user-scalable=no">
  <title>Xiao-An Cam Motor</title>
  <style>
    * { box-sizing: border-box; touch-action: manipulation; }
    body {
      margin: 0;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #101418;
      color: #f3f5f7;
      min-height: 100vh;
    }
    main { width: min(720px, 96vw); margin: 0 auto; padding: 10px 0 18px; }
    h1 { font-size: 20px; margin: 6px 0 8px; }
    .hint { color: #8a939c; font-size: 13px; margin: 0 0 8px; }
    .video {
      width: 100%;
      aspect-ratio: 4 / 3;
      background: #050608;
      border: 1px solid #303842;
      border-radius: 8px;
      overflow: hidden;
    }
    .video img { width: 100%; height: 100%; object-fit: contain; display: block; }
    .status {
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 8px;
      margin: 10px 0;
      color: #b8c0c8;
      font-size: 14px;
    }
    .pad {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 10px;
    }
    button {
      border: 0;
      border-radius: 8px;
      min-height: 72px;
      font-size: 24px;
      font-weight: 700;
      color: #f7fafc;
      background: #2f3944;
      box-shadow: inset 0 -3px 0 rgba(0,0,0,.25);
    }
    button:active, button.active { background: #2f7dd1; }
    .stop { background: #a12f2f; }
    .mode { min-height: 46px; font-size: 14px; }
  </style>
</head>
<body>
<main>
  <h1>Xiao-An Camera + Motor</h1>
  <p class="hint">MJPEG on :81/stream. Mode switch auto-reloads in ~2s.</p>
  <div class="video"><img id="stream" alt="camera stream"></div>
  <div class="status">
    <div>Command: <span id="cmd">x</span></div>
    <div>Speed: <span id="speed">110</span></div>
    <div>Cam: <span id="cam">qvga320</span></div>
    <div>Size: <span id="size">320x240</span></div>
  </div>
  <section class="pad">
    <button class="mode" data-mode="vga">VGA 640</button>
    <button data-cmd="w">W</button>
    <button class="mode" data-mode="fast">QVGA 320</button>
    <button data-cmd="a">A</button>
    <button data-cmd="x" class="stop">X</button>
    <button data-cmd="d">D</button>
    <button data-cmd="-">-</button>
    <button data-cmd="s">S</button>
    <button data-cmd="+">+</button>
  </section>
</main>
<script>
const cmdEl = document.getElementById("cmd");
const speedEl = document.getElementById("speed");
const camEl = document.getElementById("cam");
const sizeEl = document.getElementById("size");
const stream = document.getElementById("stream");
let timer = null;
let activeButton = null;
let fallbackTimer = null;

function startStream() {
  if (fallbackTimer) clearInterval(fallbackTimer);
  fallbackTimer = null;
  stream.src = `http://${location.hostname}:81/stream?t=${Date.now()}`;
  setTimeout(() => {
    if (!stream.complete || stream.naturalWidth === 0) {
      stream.src = `/jpg?t=${Date.now()}`;
    }
  }, 2500);
}

async function send(c) {
  try {
    const response = await fetch(`/cmd?c=${encodeURIComponent(c)}`, { cache: "no-store" });
    const data = await response.json();
    cmdEl.textContent = data.command;
    speedEl.textContent = data.speed;
  } catch (error) {
    cmdEl.textContent = "offline";
  }
}

async function refreshStatus() {
  try {
    const response = await fetch("/status", { cache: "no-store" });
    const data = await response.json();
    cmdEl.textContent = data.command;
    speedEl.textContent = data.speed;
    camEl.textContent = data.camera_mode || camEl.textContent;
    if (data.camera_width && data.camera_height) {
      sizeEl.textContent = `${data.camera_width}x${data.camera_height}`;
    }
  } catch (error) {
    cmdEl.textContent = "offline";
  }
}

async function setMode(mode) {
  if (sessionStorage.getItem("modeSwitch") === "1") return;
  sessionStorage.setItem("modeSwitch", "1");
  camEl.textContent = "switching";
  stream.src = "";
  fetch(`/cam/mode?m=${mode}`, { cache: "no-store" }).catch(() => {});
  setTimeout(() => {
    sessionStorage.removeItem("modeSwitch");
    window.location.replace(window.location.pathname);
  }, 2200);
}

function start(button) {
  stop(false);
  activeButton = button;
  activeButton.classList.add("active");
  const c = button.dataset.cmd;
  send(c);
  if ("wasd".includes(c)) {
    timer = setInterval(() => send(c), 120);
  }
}

function stop(sendStop = true) {
  if (timer) clearInterval(timer);
  timer = null;
  if (activeButton) activeButton.classList.remove("active");
  activeButton = null;
  if (sendStop) send("x");
}

document.querySelectorAll("button[data-cmd]").forEach((button) => {
  button.addEventListener("pointerdown", (event) => {
    event.preventDefault();
    start(button);
  });
  button.addEventListener("pointerup", () => stop(true));
  button.addEventListener("pointercancel", () => stop(true));
  button.addEventListener("pointerleave", () => stop(true));
});

document.querySelectorAll("button[data-mode]").forEach((button) => {
  button.addEventListener("click", () => setMode(button.dataset.mode));
});

send("x");
startStream();
setInterval(refreshStatus, 3000);
</script>
</body>
</html>
)HTML";

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

void stopMotor(const char* reason);

void serviceClientsAndMotor() {
    server.handleClient();
    if (motorActive && static_cast<int32_t>(millis() - motorHoldUntilMs) >= 0) {
        stopMotor("deadman timeout");
    }
}

void sendJpegResponse(const uint8_t* buf, size_t len) {
    server.sendHeader("Cache-Control", "no-store");
    server.setContentLength(len);
    server.send(200, "image/jpeg", "");
    WiFiClient client = server.client();
    client.write(buf, len);
}

camera_fb_t* acquireFrame(uint8_t attempts = 3,
                          uint32_t delayMs = 30,
                          uint32_t mutexTimeoutMs = 1200,
                          bool serviceHttp = true) {
    if (!cameraReady || !cameraMutex) {
        return nullptr;
    }

    if (xSemaphoreTake(cameraMutex, pdMS_TO_TICKS(mutexTimeoutMs)) != pdTRUE) {
        return nullptr;
    }

    for (uint8_t attempt = 1; attempt <= attempts; ++attempt) {
        camera_fb_t* fb = esp_camera_fb_get();
        if (fb) {
            return fb;
        }
        if (serviceHttp) {
            serviceClientsAndMotor();
            delay(delayMs);
        } else {
            vTaskDelay(pdMS_TO_TICKS(delayMs));
        }
    }

    xSemaphoreGive(cameraMutex);
    return nullptr;
}

void releaseFrame(camera_fb_t* fb) {
    if (fb) {
        esp_camera_fb_return(fb);
    }
    if (cameraMutex) {
        xSemaphoreGive(cameraMutex);
    }
}

void tuneCameraSensor(sensor_t* sensor) {
    if (!sensor) {
        return;
    }

    sensor->set_brightness(sensor, 1);
    sensor->set_contrast(sensor, 0);
    sensor->set_saturation(sensor, 0);
    sensor->set_sharpness(sensor, 0);
    sensor->set_whitebal(sensor, 1);
    sensor->set_awb_gain(sensor, 1);
    sensor->set_exposure_ctrl(sensor, 1);
    sensor->set_gain_ctrl(sensor, 1);
    sensor->set_aec2(sensor, 1);
    sensor->set_ae_level(sensor, 1);
    sensor->set_gainceiling(sensor, GAINCEILING_8X);
    sensor->set_lenc(sensor, 1);
    sensor->set_dcw(sensor, 1);
}

void fillCameraConfig(camera_config_t* config, framesize_t frameSize, int quality) {
    *config = {};
    config->ledc_channel = LEDC_CHANNEL_7;
    config->ledc_timer = LEDC_TIMER_1;
    config->pin_d0 = CAM_PIN_D0;
    config->pin_d1 = CAM_PIN_D1;
    config->pin_d2 = CAM_PIN_D2;
    config->pin_d3 = CAM_PIN_D3;
    config->pin_d4 = CAM_PIN_D4;
    config->pin_d5 = CAM_PIN_D5;
    config->pin_d6 = CAM_PIN_D6;
    config->pin_d7 = CAM_PIN_D7;
    config->pin_xclk = CAM_PIN_XCLK;
    config->pin_pclk = CAM_PIN_PCLK;
    config->pin_vsync = CAM_PIN_VSYNC;
    config->pin_href = CAM_PIN_HREF;
    config->pin_sccb_sda = CAM_PIN_SIOD;
    config->pin_sccb_scl = CAM_PIN_SIOC;
    config->pin_pwdn = CAM_PIN_PWDN;
    config->pin_reset = CAM_PIN_RESET;
    config->xclk_freq_hz = 10000000;
    config->pixel_format = PIXFORMAT_JPEG;
    config->frame_size = frameSize;
    config->jpeg_quality = quality;
    config->fb_count = CAMERA_FB_COUNT;
    config->fb_location = CAMERA_FB_IN_PSRAM;
    config->grab_mode = CAMERA_GRAB_LATEST;
    config->sccb_i2c_port = 1;
}

void stopStreamServer();
void startStreamServer();

void waitBrief(uint32_t waitMs) {
    const uint32_t start = millis();
    while (millis() - start < waitMs) {
        if (motorActive && static_cast<int32_t>(millis() - motorHoldUntilMs) >= 0) {
            stopMotor("deadman timeout");
        }
        delay(10);
    }
}

void stopStreamServer() {
    if (streamHttpd) {
        httpd_stop(streamHttpd);
        streamHttpd = nullptr;
        Serial.println("[MotorCam] stream server stopped");
    }
    waitBrief(300);
}

bool applyCameraProfile(framesize_t frameSize, int quality, const char* name, uint16_t width, uint16_t height) {
    if (!cameraMutex) {
        return false;
    }

    stopStreamServer();

    if (xSemaphoreTake(cameraMutex, pdMS_TO_TICKS(5000)) != pdTRUE) {
        Serial.println("[MotorCam] camera mode switch mutex timeout");
        startStreamServer();
        return false;
    }

    if (cameraReady) {
        esp_camera_deinit();
        cameraReady = false;
    }

    camera_config_t config = {};
    fillCameraConfig(&config, frameSize, quality);
    esp_err_t err = esp_camera_init(&config);
    sensor_t* sensor = esp_camera_sensor_get();

    if (err != ESP_OK) {
        Serial.printf("[MotorCam][ERROR] camera reinit failed err=0x%x\n", err);
        esp_camera_deinit();
        fillCameraConfig(&config, FRAMESIZE_QVGA, JPEG_QUALITY_QVGA);
        err = esp_camera_init(&config);
        sensor = esp_camera_sensor_get();
        if (err != ESP_OK) {
            xSemaphoreGive(cameraMutex);
            startStreamServer();
            return false;
        }
        cameraMode = "qvga320";
        cameraWidth = 320;
        cameraHeight = 240;
    } else {
        cameraMode = name;
        cameraWidth = width;
        cameraHeight = height;
    }

    if (sensor) {
        tuneCameraSensor(sensor);
    }

    cameraReady = true;
    xSemaphoreGive(cameraMutex);

    waitBrief(150);
    startStreamServer();
    Serial.printf("[MotorCam] camera mode=%s %ux%u\n", cameraMode, cameraWidth, cameraHeight);
    return true;
}

bool setCameraMode(const char* mode) {
    if (strcmp(mode, "fast") == 0 || strcmp(mode, "qvga") == 0) {
        return applyCameraProfile(FRAMESIZE_QVGA, JPEG_QUALITY_QVGA, "qvga320", 320, 240);
    }

    return applyCameraProfile(FRAMESIZE_VGA, JPEG_QUALITY_VGA, "vga640", 640, 480);
}

bool initCamera() {
    if (xSemaphoreTake(cameraMutex, pdMS_TO_TICKS(3000)) != pdTRUE) {
        return false;
    }

    camera_config_t config = {};
    fillCameraConfig(&config, FRAMESIZE_QVGA, JPEG_QUALITY_QVGA);

    esp_err_t err = esp_camera_init(&config);
    if (err != ESP_OK) {
        Serial.printf("[MotorCam][ERROR] camera init failed err=0x%x\n", err);
        esp_camera_deinit();
        xSemaphoreGive(cameraMutex);
        return false;
    }

    sensor_t* sensor = esp_camera_sensor_get();
    if (sensor) {
        sensor->set_framesize(sensor, FRAMESIZE_QVGA);
        sensor->set_quality(sensor, JPEG_QUALITY_QVGA);
        tuneCameraSensor(sensor);
    }

    cameraReady = true;
    cameraMode = "qvga320";
    cameraWidth = 320;
    cameraHeight = 240;
    xSemaphoreGive(cameraMutex);
    Serial.println("[MotorCam] camera ready: JPEG QVGA 320x240 q=12");
    return true;
}

void stopMotor(const char* reason) {
    if (motorActive) {
        Serial.printf("[MotorCam] stop: %s\n", reason);
    }
    motor.stop();
    motorActive = false;
    lastCommand = 'x';
}

void driveCommand(char command) {
    lastCommand = command;

    switch (command) {
        case 'w':
            motor.forward(motorSpeed);
            motorActive = true;
            motorHoldUntilMs = millis() + MOTOR_DEADMAN_MS;
            break;
        case 's':
            motor.backward(motorSpeed);
            motorActive = true;
            motorHoldUntilMs = millis() + MOTOR_DEADMAN_MS;
            break;
        case 'a':
            motor.turnLeft(motorSpeed);
            motorActive = true;
            motorHoldUntilMs = millis() + MOTOR_DEADMAN_MS;
            break;
        case 'd':
            motor.turnRight(motorSpeed);
            motorActive = true;
            motorHoldUntilMs = millis() + MOTOR_DEADMAN_MS;
            break;
        case '+':
            motorSpeed = min(motorSpeed + MOTOR_SPEED_STEP, MOTOR_SPEED_MAX);
            break;
        case '-':
            motorSpeed = max(motorSpeed - MOTOR_SPEED_STEP, MOTOR_SPEED_MIN);
            break;
        default:
            stopMotor("command stop");
            break;
    }
}

void sendStatus() {
    String response = "{";
    response += "\"command\":\"";
    response += lastCommand;
    response += "\",\"speed\":";
    response += motorSpeed;
    response += ",\"active\":";
    response += motorActive ? "true" : "false";
    response += ",\"camera_ready\":";
    response += cameraReady ? "true" : "false";
    response += ",\"camera_mode\":\"";
    response += cameraMode;
    response += "\",\"camera_width\":";
    response += cameraWidth;
    response += ",\"camera_height\":";
    response += cameraHeight;
    response += "}";
    server.send(200, "application/json", response);
}

void handleCommand() {
    if (!server.hasArg("c") || server.arg("c").length() == 0) {
        server.send(400, "application/json", "{\"error\":\"missing command\"}");
        return;
    }

    const char command = static_cast<char>(tolower(server.arg("c")[0]));
    if (command == '=' || command == '+') {
        driveCommand('+');
    } else {
        driveCommand(command);
    }
    sendStatus();
}

void handleCameraMode() {
    const String mode = server.hasArg("m") ? server.arg("m") : "vga";
    mode.toCharArray(pendingModeName, sizeof(pendingModeName));
    pendingModeSwitch = true;
    server.send(200, "application/json", "{\"ok\":true,\"pending\":true}");
}

void processPendingModeSwitch() {
    if (!pendingModeSwitch) {
        return;
    }

    pendingModeSwitch = false;
    setCameraMode(pendingModeName);
}

void handleJpg() {
    camera_fb_t* fb = acquireFrame(3, 30);
    if (!fb || fb->format != PIXFORMAT_JPEG || fb->len == 0) {
        releaseFrame(fb);
        server.send(503, "text/plain", "camera unavailable");
        return;
    }

    if (fb->width > 0) {
        cameraWidth = fb->width;
    }
    if (fb->height > 0) {
        cameraHeight = fb->height;
    }

    sendJpegResponse(fb->buf, fb->len);
    releaseFrame(fb);
}

void handleNotFound() {
    stopMotor("http 404");
    server.send(404, "text/plain", "Not found");
}

esp_err_t streamHandler(httpd_req_t* req) {
    esp_err_t res = httpd_resp_set_type(req, STREAM_CONTENT_TYPE);
    if (res != ESP_OK) {
        return res;
    }

    httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
    httpd_resp_set_hdr(req, "Cache-Control", "no-store");
    httpd_resp_set_hdr(req, "X-Framerate", "60");

    char partBuf[64];
    uint32_t frameCount = 0;
    uint32_t fpsWindowStart = millis();
    uint32_t lastSentMs = 0;

    while (true) {
        const uint32_t minFrameMs = cameraWidth > 400 ? STREAM_MIN_FRAME_MS_VGA : 0;
        const uint32_t nowMs = millis();
        if (minFrameMs > 0 && nowMs - lastSentMs < minFrameMs) {
            vTaskDelay(pdMS_TO_TICKS(5));
            continue;
        }

        camera_fb_t* fb = acquireFrame(3, 20, 800, false);
        if (!fb) {
            vTaskDelay(pdMS_TO_TICKS(30));
            continue;
        }

        if (fb->format != PIXFORMAT_JPEG || fb->len == 0) {
            releaseFrame(fb);
            vTaskDelay(pdMS_TO_TICKS(30));
            continue;
        }

        if (fb->width > 0) {
            cameraWidth = fb->width;
        }
        if (fb->height > 0) {
            cameraHeight = fb->height;
        }

        res = httpd_resp_send_chunk(req, STREAM_BOUNDARY, strlen(STREAM_BOUNDARY));
        if (res == ESP_OK) {
            const size_t hLen = snprintf(partBuf,
                                         sizeof(partBuf),
                                         STREAM_PART,
                                         static_cast<unsigned>(fb->len));
            res = httpd_resp_send_chunk(req, partBuf, hLen);
        }
        if (res == ESP_OK) {
            res = httpd_resp_send_chunk(req,
                                        reinterpret_cast<const char*>(fb->buf),
                                        fb->len);
        }

        releaseFrame(fb);

        if (res != ESP_OK) {
            break;
        }

        lastSentMs = millis();
        ++frameCount;
        const uint32_t now = millis();
        if (now - fpsWindowStart >= 5000) {
            const float fps = frameCount * 1000.0f / static_cast<float>(now - fpsWindowStart);
            Serial.printf("[MotorCam] stream fps=%.1f %ux%u\n", fps, cameraWidth, cameraHeight);
            frameCount = 0;
            fpsWindowStart = now;
        }
    }

    return res;
}

void startStreamServer() {
    if (streamHttpd) {
        return;
    }

    httpd_config_t streamConfig = HTTPD_DEFAULT_CONFIG();
    streamConfig.server_port = 81;
    streamConfig.ctrl_port = 32769;
    streamConfig.stack_size = 10240;
    streamConfig.lru_purge_enable = true;
    streamConfig.max_open_sockets = 2;
    streamConfig.recv_wait_timeout = 10;
    streamConfig.send_wait_timeout = 10;
    streamConfig.core_id = 1;

    httpd_uri_t streamUri = {};
    streamUri.uri = "/stream";
    streamUri.method = HTTP_GET;
    streamUri.handler = streamHandler;
    streamUri.user_ctx = nullptr;

    if (httpd_start(&streamHttpd, &streamConfig) == ESP_OK) {
        httpd_register_uri_handler(streamHttpd, &streamUri);
        Serial.println("[MotorCam] stream server ready: http://192.168.4.1:81/stream");
    } else {
        Serial.println("[MotorCam][ERROR] failed to start stream server");
    }
}

}  // namespace

void setup() {
    holdMotorPinsLowBeforeSerial();

    Serial.begin(115200);
    Serial.setDebugOutput(false);
    delay(1000);
    Serial.println("[MotorCam] Xiao-An WiFi camera + motor bring-up");
    Serial.println("[MotorCam] MJPEG preview only. Face/QR runs on PC or base station.");
    Serial.println("[MotorCam] Wheels must be lifted before testing.");

    cameraMutex = xSemaphoreCreateMutex();
    initCamera();

    motor.begin();
    motor.stop();

    WiFi.mode(WIFI_AP);
    WiFi.setSleep(false);
    WiFi.softAPConfig(IPAddress(192, 168, 4, 1),
                      IPAddress(192, 168, 4, 1),
                      IPAddress(255, 255, 255, 0));
    const bool apStarted = WiFi.softAP(WIFI_SSID, WIFI_PASSWORD, 1, false, 3);
    Serial.printf("[MotorCam] AP %s: ssid=%s password=%s ip=%s\n",
                  apStarted ? "started" : "failed",
                  WIFI_SSID,
                  WIFI_PASSWORD,
                  WiFi.softAPIP().toString().c_str());

    server.on("/", HTTP_GET, []() {
        server.send_P(200, "text/html", INDEX_HTML);
    });
    server.on("/cmd", HTTP_GET, handleCommand);
    server.on("/status", HTTP_GET, sendStatus);
    server.on("/jpg", HTTP_GET, handleJpg);
    server.on("/cam/mode", HTTP_GET, handleCameraMode);
    server.onNotFound(handleNotFound);
    server.begin();

    startStreamServer();
    Serial.println("[MotorCam] Open http://192.168.4.1 after joining XiaoAn-Motor.");
    Serial.println("[MotorCam] PC preview: python robot/firmware/tools/wifi_camera_viewer.py");
}

void loop() {
    server.handleClient();
    processPendingModeSwitch();

    if (motorActive &&
        static_cast<int32_t>(millis() - motorHoldUntilMs) >= 0) {
        stopMotor("deadman timeout");
    }

    yield();
}
