#include <Arduino.h>
#include <WiFi.h>
#include "esp_camera.h"
#include "esp_http_server.h"

#define AP_SSID "xiao-an-cam"
#define AP_PASSWORD "12345678"

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

static httpd_handle_t stream_httpd = nullptr;
static httpd_handle_t page_httpd = nullptr;

static const char *STREAM_CONTENT_TYPE = "multipart/x-mixed-replace; boundary=frame";
static const char *STREAM_BOUNDARY = "\r\n--frame\r\n";
static const char *STREAM_PART = "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

static camera_fb_t *captureFrame(uint8_t attempts = 5, uint32_t delayMs = 200) {
    for (uint8_t attempt = 1; attempt <= attempts; ++attempt) {
        camera_fb_t *fb = esp_camera_fb_get();
        if (fb) {
            return fb;
        }
        Serial.printf("Camera capture failed, attempt %u/%u\n", attempt, attempts);
        delay(delayMs);
    }
    return nullptr;
}

static esp_err_t indexHandler(httpd_req_t *req) {
    const char html[] =
        "<!doctype html>"
        "<html>"
        "<head>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        "<title>GOOUUU ESP32-S3-CAM</title>"
        "<style>"
        "body{margin:0;background:#111;color:#eee;font-family:Arial,sans-serif;text-align:center;}"
        "main{padding:20px;}"
        "img{width:100%;max-width:960px;height:auto;background:#000;}"
        "a{color:#7dd3fc;}"
        "</style>"
        "</head>"
        "<body>"
        "<main>"
        "<h1>GOOUUU ESP32-S3-CAM</h1>"
        "<p><a id='streamLink' href='#'>Open MJPEG stream</a></p>"
        "<img id='stream' alt='MJPEG stream'>"
        "</main>"
        "<script>"
        "const streamUrl='http://'+location.hostname+':81/stream';"
        "document.getElementById('streamLink').href=streamUrl;"
        "document.getElementById('stream').src=streamUrl;"
        "</script>"
        "</body>"
        "</html>";

    httpd_resp_set_type(req, "text/html");
    httpd_resp_set_hdr(req, "Cache-Control", "no-store");
    return httpd_resp_send(req, html, HTTPD_RESP_USE_STRLEN);
}

static esp_err_t streamHandler(httpd_req_t *req) {
    esp_err_t res = httpd_resp_set_type(req, STREAM_CONTENT_TYPE);
    if (res != ESP_OK) {
        return res;
    }

    httpd_resp_set_hdr(req, "Access-Control-Allow-Origin", "*");
    httpd_resp_set_hdr(req, "Cache-Control", "no-store");

    char part_buf[64];

    while (true) {
        camera_fb_t *fb = captureFrame(5, 100);
        if (!fb) {
            Serial.println("Camera stream capture failed after retries");
            return ESP_FAIL;
        }

        if (fb->format != PIXFORMAT_JPEG) {
            Serial.println("Captured frame is not JPEG");
            esp_camera_fb_return(fb);
            return ESP_FAIL;
        }

        res = httpd_resp_send_chunk(req, STREAM_BOUNDARY, strlen(STREAM_BOUNDARY));
        if (res == ESP_OK) {
            size_t hlen = snprintf(part_buf, sizeof(part_buf), STREAM_PART, fb->len);
            res = httpd_resp_send_chunk(req, part_buf, hlen);
        }
        if (res == ESP_OK) {
            res = httpd_resp_send_chunk(req, reinterpret_cast<const char *>(fb->buf), fb->len);
        }

        esp_camera_fb_return(fb);

        if (res != ESP_OK) {
            break;
        }

        delay(1);
    }

    return res;
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
    config.jpeg_quality = 10;
    config.fb_count = 2;
    config.fb_location = CAMERA_FB_IN_PSRAM;
    config.grab_mode = CAMERA_GRAB_WHEN_EMPTY;
    config.sccb_i2c_port = 1;

    esp_err_t err = esp_camera_init(&config);
    if (err != ESP_OK) {
        Serial.printf("Camera init failed with error 0x%x\n", err);
        return false;
    }

    sensor_t *sensor = esp_camera_sensor_get();
    if (sensor) {
        sensor->set_framesize(sensor, FRAMESIZE_QVGA);
        sensor->set_quality(sensor, 10);
    }

    return true;
}

static void captureSelfTest() {
    Serial.println("Camera capture self-test...");
    delay(1000);

    for (uint8_t i = 1; i <= 5; ++i) {
        camera_fb_t *fb = captureFrame(1, 0);
        if (!fb) {
            Serial.printf("Self-test frame %u: failed\n", i);
            delay(300);
            continue;
        }

        Serial.printf("Self-test frame %u: %ux%u len=%u format=%d\n",
                      i,
                      fb->width,
                      fb->height,
                      fb->len,
                      fb->format);
        esp_camera_fb_return(fb);
        delay(300);
    }
}

static void startAccessPoint() {
  WiFi.mode(WIFI_AP);
  WiFi.setSleep(false);
  WiFi.softAPConfig(IPAddress(192, 168, 4, 1),
                    IPAddress(192, 168, 4, 1),
                    IPAddress(255, 255, 255, 0));
  WiFi.softAP(AP_SSID, AP_PASSWORD, 6, false, 1);
  Serial.printf("AP SSID: %s\n", AP_SSID);
  Serial.printf("AP password: %s\n", AP_PASSWORD);
  Serial.print("AP IP: ");
  Serial.println(WiFi.softAPIP());
}

static void startCameraServer() {
    httpd_config_t page_config = HTTPD_DEFAULT_CONFIG();
    page_config.server_port = 80;
    page_config.ctrl_port = 32768;

    httpd_uri_t index_uri = {};
    index_uri.uri = "/";
    index_uri.method = HTTP_GET;
    index_uri.handler = indexHandler;
    index_uri.user_ctx = nullptr;

    if (httpd_start(&page_httpd, &page_config) == ESP_OK) {
        httpd_register_uri_handler(page_httpd, &index_uri);
    } else {
        Serial.println("Failed to start page HTTP server");
        return;
    }

    httpd_config_t stream_config = HTTPD_DEFAULT_CONFIG();
    stream_config.server_port = 81;
    stream_config.ctrl_port = 32769;

    httpd_uri_t stream_uri = {};
    stream_uri.uri = "/stream";
    stream_uri.method = HTTP_GET;
    stream_uri.handler = streamHandler;
    stream_uri.user_ctx = nullptr;

    if (httpd_start(&stream_httpd, &stream_config) == ESP_OK) {
        httpd_register_uri_handler(stream_httpd, &stream_uri);
    } else {
        Serial.println("Failed to start stream HTTP server");
    }
}

void setup() {
    Serial.begin(115200);
    delay(1000);
    Serial.println();
    Serial.println("GOOUUU ESP32-S3-CAM MJPEG stream test");

    if (!initCamera()) {
        Serial.println("Camera setup stopped");
        return;
    }

    captureSelfTest();

  startAccessPoint();
  startCameraServer();

  IPAddress ip = WiFi.softAPIP();
    Serial.println("HTTP page:");
    Serial.printf("  http://%s/\n", ip.toString().c_str());
    Serial.println("MJPEG stream:");
    Serial.printf("  http://%s:81/stream\n", ip.toString().c_str());
}

void loop() {
    delay(10000);
}
