#include <Arduino.h>
#include <WiFi.h>
#include "esp_camera.h"
#include "esp_http_server.h"
#include "img_converters.h"

#define AP_SSID "xiao-an-red"
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

static constexpr int SAMPLE_STEP = 2;
static constexpr int MASK_WIDTH = 320 / SAMPLE_STEP;
static constexpr int MASK_HEIGHT = 240 / SAMPLE_STEP;
static constexpr int MASK_CELLS = MASK_WIDTH * MASK_HEIGHT;
static constexpr int MIN_RED_PIXELS = 70;
static constexpr int MIN_BOX_SIZE_PX = 10;
static constexpr int MAX_BOX_WIDTH_PX = 150;
static constexpr int MAX_BOX_HEIGHT_PX = 150;
static constexpr int BOX_PAD_PX = 2;
static constexpr uint8_t JPEG_QUALITY = 80;

static bool redMask[MASK_CELLS];
static bool visitedMask[MASK_CELLS];
static uint16_t floodQueue[MASK_CELLS];

static httpd_handle_t page_httpd = nullptr;
static httpd_handle_t stream_httpd = nullptr;

static const char *STREAM_CONTENT_TYPE = "multipart/x-mixed-replace; boundary=frame";
static const char *STREAM_BOUNDARY = "\r\n--frame\r\n";
static const char *STREAM_PART = "Content-Type: image/jpeg\r\nContent-Length: %u\r\n\r\n";

struct TrackBox {
    bool found = false;
    int xMin = 0;
    int yMin = 0;
    int xMax = 0;
    int yMax = 0;
    int centerX = 0;
    int centerY = 0;
    int pixels = 0;
    int dx = 0;
    int dy = 0;
};

static uint16_t rgb565At(const camera_fb_t *fb, int x, int y) {
    const size_t idx = ((size_t)y * fb->width + x) * 2;
    return ((uint16_t)fb->buf[idx] << 8) | fb->buf[idx + 1];
}

static void setRgb565At(camera_fb_t *fb, int x, int y, uint16_t color) {
    if (x < 0 || y < 0 || x >= fb->width || y >= fb->height) {
        return;
    }
    const size_t idx = ((size_t)y * fb->width + x) * 2;
    fb->buf[idx] = color >> 8;
    fb->buf[idx + 1] = color & 0xFF;
}

static bool isRedPixel(uint16_t p) {
    const uint8_t r = ((p >> 11) & 0x1F) << 3;
    const uint8_t g = ((p >> 5) & 0x3F) << 2;
    const uint8_t b = (p & 0x1F) << 3;

    const int maxC = max((int)r, max((int)g, (int)b));
    const int minC = min((int)r, min((int)g, (int)b));

    // Stricter saturated-red gate. This rejects most skin tones and weak red
    // shadows, so the box follows the object instead of the whole hand.
    return r > 140 &&
           g < 85 &&
           b < 85 &&
           (maxC - minC) > 80 &&
           r > (g + 70) &&
           r > (b + 65);
}

static TrackBox findRedObject(const camera_fb_t *fb) {
    TrackBox box;
    if (!fb || fb->format != PIXFORMAT_RGB565 || fb->len < 2) {
        return box;
    }

    memset(redMask, 0, sizeof(redMask));
    memset(visitedMask, 0, sizeof(visitedMask));

    const int maskW = min((int)fb->width / SAMPLE_STEP, MASK_WIDTH);
    const int maskH = min((int)fb->height / SAMPLE_STEP, MASK_HEIGHT);

    for (int my = 0; my < maskH; ++my) {
        for (int mx = 0; mx < maskW; ++mx) {
            const int x = mx * SAMPLE_STEP;
            const int y = my * SAMPLE_STEP;
            redMask[my * MASK_WIDTH + mx] = isRedPixel(rgb565At(fb, x, y));
        }
    }

    int bestCount = 0;
    int bestXMin = 0;
    int bestYMin = 0;
    int bestXMax = 0;
    int bestYMax = 0;

    for (int sy = 0; sy < maskH; ++sy) {
        for (int sx = 0; sx < maskW; ++sx) {
            const int startIdx = sy * MASK_WIDTH + sx;
            if (!redMask[startIdx] || visitedMask[startIdx]) {
                continue;
            }

            int head = 0;
            int tail = 0;
            int count = 0;
            int xMin = sx;
            int yMin = sy;
            int xMax = sx;
            int yMax = sy;

            visitedMask[startIdx] = true;
            floodQueue[tail++] = startIdx;

            while (head < tail) {
                const int idx = floodQueue[head++];
                const int x = idx % MASK_WIDTH;
                const int y = idx / MASK_WIDTH;
                count++;
                xMin = min(xMin, x);
                yMin = min(yMin, y);
                xMax = max(xMax, x);
                yMax = max(yMax, y);

                const int nx[4] = {x - 1, x + 1, x, x};
                const int ny[4] = {y, y, y - 1, y + 1};
                for (int i = 0; i < 4; ++i) {
                    if (nx[i] < 0 || ny[i] < 0 || nx[i] >= maskW || ny[i] >= maskH) {
                        continue;
                    }
                    const int nIdx = ny[i] * MASK_WIDTH + nx[i];
                    if (!redMask[nIdx] || visitedMask[nIdx]) {
                        continue;
                    }
                    visitedMask[nIdx] = true;
                    floodQueue[tail++] = nIdx;
                }
            }

            if (count > bestCount) {
                bestCount = count;
                bestXMin = xMin;
                bestYMin = yMin;
                bestXMax = xMax;
                bestYMax = yMax;
            }
        }
    }

    const int xMin = bestXMin * SAMPLE_STEP;
    const int yMin = bestYMin * SAMPLE_STEP;
    const int xMax = min((int)fb->width - 1, bestXMax * SAMPLE_STEP + SAMPLE_STEP - 1);
    const int yMax = min((int)fb->height - 1, bestYMax * SAMPLE_STEP + SAMPLE_STEP - 1);
    const int width = xMax - xMin + 1;
    const int height = yMax - yMin + 1;

    if (bestCount < MIN_RED_PIXELS ||
        width < MIN_BOX_SIZE_PX ||
        height < MIN_BOX_SIZE_PX ||
        width > MAX_BOX_WIDTH_PX ||
        height > MAX_BOX_HEIGHT_PX) {
        return box;
    }

    box.found = true;
    box.xMin = max(0, xMin - BOX_PAD_PX);
    box.yMin = max(0, yMin - BOX_PAD_PX);
    box.xMax = min((int)fb->width - 1, xMax + BOX_PAD_PX);
    box.yMax = min((int)fb->height - 1, yMax + BOX_PAD_PX);
    box.centerX = (box.xMin + box.xMax) / 2;
    box.centerY = (box.yMin + box.yMax) / 2;
    box.pixels = bestCount;
    box.dx = box.centerX - ((int)fb->width / 2);
    box.dy = box.centerY - ((int)fb->height / 2);
    return box;
}

static const uint8_t *glyphFor(char c) {
    static const uint8_t GLYPH_SPACE[5] = {0, 0, 0, 0, 0};
    static const uint8_t GLYPH_0[5] = {0b111, 0b101, 0b101, 0b101, 0b111};
    static const uint8_t GLYPH_1[5] = {0b010, 0b110, 0b010, 0b010, 0b111};
    static const uint8_t GLYPH_2[5] = {0b111, 0b001, 0b111, 0b100, 0b111};
    static const uint8_t GLYPH_3[5] = {0b111, 0b001, 0b111, 0b001, 0b111};
    static const uint8_t GLYPH_4[5] = {0b101, 0b101, 0b111, 0b001, 0b001};
    static const uint8_t GLYPH_5[5] = {0b111, 0b100, 0b111, 0b001, 0b111};
    static const uint8_t GLYPH_6[5] = {0b111, 0b100, 0b111, 0b101, 0b111};
    static const uint8_t GLYPH_7[5] = {0b111, 0b001, 0b010, 0b010, 0b010};
    static const uint8_t GLYPH_8[5] = {0b111, 0b101, 0b111, 0b101, 0b111};
    static const uint8_t GLYPH_9[5] = {0b111, 0b101, 0b111, 0b001, 0b111};
    static const uint8_t GLYPH_X[5] = {0b101, 0b101, 0b010, 0b101, 0b101};
    static const uint8_t GLYPH_Y[5] = {0b101, 0b101, 0b010, 0b010, 0b010};
    static const uint8_t GLYPH_D[5] = {0b110, 0b101, 0b101, 0b101, 0b110};
    static const uint8_t GLYPH_E[5] = {0b111, 0b100, 0b111, 0b100, 0b111};
    static const uint8_t GLYPH_N[5] = {0b101, 0b111, 0b111, 0b111, 0b101};
    static const uint8_t GLYPH_O[5] = {0b111, 0b101, 0b101, 0b101, 0b111};
    static const uint8_t GLYPH_R[5] = {0b110, 0b101, 0b110, 0b101, 0b101};
    static const uint8_t GLYPH_COLON[5] = {0b000, 0b010, 0b000, 0b010, 0b000};
    static const uint8_t GLYPH_MINUS[5] = {0b000, 0b000, 0b111, 0b000, 0b000};
    static const uint8_t GLYPH_PLUS[5] = {0b000, 0b010, 0b111, 0b010, 0b000};

    switch (c) {
        case '0': return GLYPH_0;
        case '1': return GLYPH_1;
        case '2': return GLYPH_2;
        case '3': return GLYPH_3;
        case '4': return GLYPH_4;
        case '5': return GLYPH_5;
        case '6': return GLYPH_6;
        case '7': return GLYPH_7;
        case '8': return GLYPH_8;
        case '9': return GLYPH_9;
        case 'X': return GLYPH_X;
        case 'Y': return GLYPH_Y;
        case 'D': return GLYPH_D;
        case 'E': return GLYPH_E;
        case 'N': return GLYPH_N;
        case 'O': return GLYPH_O;
        case 'R': return GLYPH_R;
        case ':': return GLYPH_COLON;
        case '-': return GLYPH_MINUS;
        case '+': return GLYPH_PLUS;
        default: return GLYPH_SPACE;
    }
}

static void fillRect(camera_fb_t *fb, int x, int y, int w, int h, uint16_t color) {
    for (int py = y; py < y + h; ++py) {
        for (int px = x; px < x + w; ++px) {
            setRgb565At(fb, px, py, color);
        }
    }
}

static void drawChar(camera_fb_t *fb, int x, int y, char c, uint16_t color, int scale = 2) {
    const uint8_t *glyph = glyphFor(c);
    for (int row = 0; row < 5; ++row) {
        for (int col = 0; col < 3; ++col) {
            if (glyph[row] & (1 << (2 - col))) {
                fillRect(fb, x + col * scale, y + row * scale, scale, scale, color);
            }
        }
    }
}

static void drawText(camera_fb_t *fb, int x, int y, const char *text, uint16_t color) {
    while (*text) {
        drawChar(fb, x, y, *text, color);
        x += 8;
        ++text;
    }
}

static void drawStatusText(camera_fb_t *fb, const TrackBox &box) {
    static constexpr uint16_t BLACK = 0x0000;
    static constexpr uint16_t WHITE = 0xFFFF;
    char line1[24];
    char line2[24];

    fillRect(fb, 4, 4, 140, 32, BLACK);
    if (!box.found) {
        drawText(fb, 8, 10, "NO RED", WHITE);
        return;
    }

    snprintf(line1, sizeof(line1), "X:%03d Y:%03d", box.centerX, box.centerY);
    snprintf(line2, sizeof(line2), "DX:%+04d DY:%+04d", box.dx, box.dy);
    drawText(fb, 8, 8, line1, WHITE);
    drawText(fb, 8, 22, line2, WHITE);
}

static void drawBox(camera_fb_t *fb, const TrackBox &box) {
    if (!box.found) {
        return;
    }

    static constexpr uint16_t GREEN = 0x07E0;
    static constexpr uint16_t WHITE = 0xFFFF;
    for (int t = 0; t < 3; ++t) {
        for (int x = box.xMin; x <= box.xMax; ++x) {
            setRgb565At(fb, x, box.yMin + t, GREEN);
            setRgb565At(fb, x, box.yMax - t, GREEN);
        }
        for (int y = box.yMin; y <= box.yMax; ++y) {
            setRgb565At(fb, box.xMin + t, y, GREEN);
            setRgb565At(fb, box.xMax - t, y, GREEN);
        }
    }

    for (int d = -5; d <= 5; ++d) {
        setRgb565At(fb, box.centerX + d, box.centerY, WHITE);
        setRgb565At(fb, box.centerX, box.centerY + d, WHITE);
    }
}

static camera_fb_t *captureFrame(uint8_t attempts = 4, uint32_t delayMs = 80) {
    for (uint8_t attempt = 1; attempt <= attempts; ++attempt) {
        camera_fb_t *fb = esp_camera_fb_get();
        if (fb) {
            return fb;
        }
        Serial.printf("[RedTracker] capture failed, attempt %u/%u\n", attempt, attempts);
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
        "<title>Xiao-An Red Tracker</title>"
        "<style>"
        "body{margin:0;background:#101010;color:#eee;font-family:Arial,sans-serif;text-align:center;}"
        "main{padding:18px;}"
        "img{width:100%;max-width:960px;height:auto;background:#000;image-rendering:auto;}"
        "p{color:#bbb;}"
        "a{color:#7dd3fc;}"
        "</style>"
        "</head>"
        "<body>"
        "<main>"
        "<h1>Red Circle Tracker</h1>"
        "<p>Put a red circle in view. Green box means target found.</p>"
        "<p><a id='streamLink' href='#'>Open stream</a></p>"
        "<img id='stream' alt='red tracker stream'>"
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

    char partBuf[72];
    uint32_t frameCount = 0;

    while (true) {
        camera_fb_t *fb = captureFrame();
        if (!fb) {
            Serial.println("[RedTracker] stream capture failed");
            return ESP_FAIL;
        }

        TrackBox box = findRedObject(fb);
        drawBox(fb, box);
        drawStatusText(fb, box);

        if (++frameCount % 15 == 0) {
            if (box.found) {
                Serial.printf("[RedTracker] found pixels=%d box=(%d,%d)-(%d,%d) center=(%d,%d)\n",
                              box.pixels,
                              box.xMin,
                              box.yMin,
                              box.xMax,
                              box.yMax,
                              box.centerX,
                              box.centerY);
            } else {
                Serial.println("[RedTracker] no red target");
            }
        }

        uint8_t *jpgBuf = nullptr;
        size_t jpgLen = 0;
        bool converted = fmt2jpg(fb->buf,
                                 fb->len,
                                 fb->width,
                                 fb->height,
                                 fb->format,
                                 JPEG_QUALITY,
                                 &jpgBuf,
                                 &jpgLen);
        esp_camera_fb_return(fb);

        if (!converted || !jpgBuf || jpgLen == 0) {
            if (jpgBuf) {
                free(jpgBuf);
            }
            Serial.println("[RedTracker] RGB565 to JPEG failed");
            return ESP_FAIL;
        }

        res = httpd_resp_send_chunk(req, STREAM_BOUNDARY, strlen(STREAM_BOUNDARY));
        if (res == ESP_OK) {
            const size_t hLen = snprintf(partBuf, sizeof(partBuf), STREAM_PART, jpgLen);
            res = httpd_resp_send_chunk(req, partBuf, hLen);
        }
        if (res == ESP_OK) {
            res = httpd_resp_send_chunk(req, reinterpret_cast<const char *>(jpgBuf), jpgLen);
        }

        free(jpgBuf);

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
    config.pixel_format = PIXFORMAT_RGB565;
    config.frame_size = FRAMESIZE_QVGA;
    config.fb_count = 2;
    config.fb_location = CAMERA_FB_IN_PSRAM;
    config.grab_mode = CAMERA_GRAB_LATEST;
    config.sccb_i2c_port = 1;

    esp_err_t err = esp_camera_init(&config);
    if (err != ESP_OK) {
        Serial.printf("[RedTracker] camera init failed: 0x%x\n", err);
        return false;
    }

    sensor_t *sensor = esp_camera_sensor_get();
    if (sensor) {
        sensor->set_framesize(sensor, FRAMESIZE_QVGA);
        sensor->set_brightness(sensor, 0);
        sensor->set_saturation(sensor, 1);
        sensor->set_whitebal(sensor, 1);
        sensor->set_awb_gain(sensor, 1);
    }

    Serial.println("[RedTracker] camera ready: RGB565 QVGA");
    return true;
}

static void startAccessPoint() {
    WiFi.mode(WIFI_AP);
    WiFi.setSleep(false);
    WiFi.softAPConfig(IPAddress(192, 168, 4, 1),
                      IPAddress(192, 168, 4, 1),
                      IPAddress(255, 255, 255, 0));
    WiFi.softAP(AP_SSID, AP_PASSWORD, 6, false, 1);
    Serial.printf("[RedTracker] AP SSID: %s\n", AP_SSID);
    Serial.printf("[RedTracker] AP password: %s\n", AP_PASSWORD);
    Serial.print("[RedTracker] AP IP: ");
    Serial.println(WiFi.softAPIP());
}

static void startCameraServer() {
    httpd_config_t pageConfig = HTTPD_DEFAULT_CONFIG();
    pageConfig.server_port = 80;
    pageConfig.ctrl_port = 32768;

    httpd_uri_t indexUri = {};
    indexUri.uri = "/";
    indexUri.method = HTTP_GET;
    indexUri.handler = indexHandler;
    indexUri.user_ctx = nullptr;

    if (httpd_start(&page_httpd, &pageConfig) == ESP_OK) {
        httpd_register_uri_handler(page_httpd, &indexUri);
    } else {
        Serial.println("[RedTracker] failed to start page HTTP server");
        return;
    }

    httpd_config_t streamConfig = HTTPD_DEFAULT_CONFIG();
    streamConfig.server_port = 81;
    streamConfig.ctrl_port = 32769;

    httpd_uri_t streamUri = {};
    streamUri.uri = "/stream";
    streamUri.method = HTTP_GET;
    streamUri.handler = streamHandler;
    streamUri.user_ctx = nullptr;

    if (httpd_start(&stream_httpd, &streamConfig) == ESP_OK) {
        httpd_register_uri_handler(stream_httpd, &streamUri);
    } else {
        Serial.println("[RedTracker] failed to start stream HTTP server");
    }
}

void setup() {
    Serial.begin(115200);
    delay(1000);
    Serial.println();
    Serial.println("[RedTracker] red circle visual tracking test");
    Serial.println("[RedTracker] motors are not used in this test");

    if (!initCamera()) {
        Serial.println("[RedTracker] stopped: camera init failed");
        return;
    }

    startAccessPoint();
    startCameraServer();

    IPAddress ip = WiFi.softAPIP();
    Serial.println("[RedTracker] HTTP page:");
    Serial.printf("  http://%s/\n", ip.toString().c_str());
    Serial.println("[RedTracker] MJPEG stream:");
    Serial.printf("  http://%s:81/stream\n", ip.toString().c_str());
}

void loop() {
    delay(10000);
}
