#include "face240_display.h"
#include "protocol.h"
#include "debug_log.h"
#include <string.h>

#include <Arduino.h>
#include <SPI.h>
#include <math.h>

#ifndef TFT_MOSI
#define TFT_MOSI 11
#endif
#ifndef TFT_MISO
#define TFT_MISO -1
#endif
#ifndef TFT_SCLK
#define TFT_SCLK 12
#endif
#ifndef TFT_CS
#define TFT_CS 10
#endif
#ifndef TFT_DC
#define TFT_DC 9
#endif
#ifndef TFT_RST
#define TFT_RST 14
#endif
#ifndef TFT_BL
#define TFT_BL 21
#endif
#ifndef TFT_BACKLIGHT_ON
#define TFT_BACKLIGHT_ON HIGH
#endif

static constexpr int16_t TFT_W = 320;
static constexpr int16_t TFT_H = 240;
static constexpr size_t FRAMEBUFFER_BYTES = static_cast<size_t>(TFT_W) * TFT_H * 2;
static constexpr uint32_t SERIAL_WAIT_MS = 2500;
static constexpr uint32_t SPI_HZ = 80000000;
static constexpr uint32_t FRAME_MS = 16;

// Only the inner expression area is redrawn each frame. The full screen remains
// the black mask style from the reference image: no robot shell, no antenna.
static constexpr int16_t ACTIVE_X = 24;
static constexpr int16_t ACTIVE_Y = 28;
static constexpr int16_t ACTIVE_W = 272;
static constexpr int16_t ACTIVE_H = 184;

static constexpr uint8_t ST7789_MADCTL_LANDSCAPE = 0x60;
static constexpr uint8_t ST7789_COLOR_ORDER = 0x00;
static constexpr bool INVERT_COLORS = false;

static constexpr uint16_t rgb565(uint8_t r, uint8_t g, uint8_t b) {
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3);
}

// Dark mask + soft glowing icon colors.
static constexpr uint16_t C_BG = rgb565(0, 7, 13);
static constexpr uint16_t C_CYAN = rgb565(126, 255, 242);
static constexpr uint16_t C_CYAN_GLOW = rgb565(8, 62, 72);
static constexpr uint16_t C_CYAN_GLOW2 = rgb565(3, 30, 38);
static constexpr uint16_t C_RED = rgb565(255, 58, 68);
static constexpr uint16_t C_RED_GLOW = rgb565(86, 10, 18);
static constexpr uint16_t C_RED_GLOW2 = rgb565(35, 3, 8);
static constexpr uint16_t C_YELLOW = rgb565(255, 229, 55);
static constexpr uint16_t C_YELLOW_GLOW = rgb565(94, 76, 10);
static constexpr uint16_t C_YELLOW_GLOW2 = rgb565(38, 28, 4);

static uint8_t frameBuffer[FRAMEBUFFER_BYTES];

enum FaceExpression : uint8_t {
    FACE_HAPPY = 0,     // 1: two cyan dot eyes + happy mouth
    FACE_SAD,           // 2: droopy eyes + frown
    FACE_SURPRISED,     // 3: dot eyes + round mouth + eyebrows
    FACE_ANGRY,         // 4: red slanted eyes + frown
    FACE_CONTENT,       // 5: closed smiling eyes + smile
    FACE_WINK,          // 6: one dot eye + '<' wink + smile
    FACE_DOTS,          // 7: red loading dots
    FACE_QUESTION,      // 8: yellow question mark
    FACE_ALERT,         // 9: red exclamation mark
    FACE_COUNT,
};

enum EyeMode : uint8_t {
    EYE_DOT,
    EYE_CLOSED_SMILE,
    EYE_DROOP,
    EYE_SLANT_DOWN_RIGHT,
    EYE_SLANT_DOWN_LEFT,
    EYE_CHEVRON_LEFT,
    EYE_HIDDEN,
};

enum MouthMode : uint8_t {
    MOUTH_SMILE,
    MOUTH_FROWN,
    MOUTH_ROUND,
    MOUTH_HIDDEN,
};

struct EyeShape {
    float cx;
    float cy;
    float w;
    float h;
    EyeMode mode;
};

struct MouthShape {
    float cx;
    float cy;
    float w;
    float h;
    MouthMode mode;
};

struct FacePose {
    EyeShape left;
    EyeShape right;
    MouthShape mouth;
    uint16_t color;
    uint16_t glow;
    uint16_t glow2;
    bool symbolOnly;
    bool eyebrows;
};

static FaceExpression expression = FACE_HAPPY;
static FacePose currentPose;
static FacePose targetPose;
static uint32_t carouselStartMs = 0;
static uint32_t expressionStartMs = 0;
static uint32_t lastFrameMs = 0;
static uint32_t fpsWindowMs = 0;
static uint16_t fpsFrames = 0;
static bool autoCarousel = false;
static bool poseInitialized = false;

static int16_t i16min(int16_t a, int16_t b) { return a < b ? a : b; }
static int16_t i16max(int16_t a, int16_t b) { return a > b ? a : b; }
static int32_t i32max(int32_t a, int32_t b) { return a > b ? a : b; }
static float fapproach(float current, float target, float amount) {
    return current + (target - current) * amount;
}

static void waitForSerialWindow() {
    const uint32_t start = millis();
    while (!Serial && millis() - start < SERIAL_WAIT_MS) {
        delay(10);
    }
}

static void selectDisplay() {
    digitalWrite(TFT_CS, LOW);
    SPI.beginTransaction(SPISettings(SPI_HZ, MSBFIRST, SPI_MODE0));
}

static void unselectDisplay() {
    SPI.endTransaction();
    digitalWrite(TFT_CS, HIGH);
}

static void writeCommand(uint8_t command) {
    digitalWrite(TFT_DC, LOW);
    selectDisplay();
    SPI.transfer(command);
    unselectDisplay();
}

static void writeData8(uint8_t data) {
    digitalWrite(TFT_DC, HIGH);
    selectDisplay();
    SPI.transfer(data);
    unselectDisplay();
}

static void writeData16Raw(uint16_t data) {
    SPI.transfer(data >> 8);
    SPI.transfer(data & 0xFF);
}

static void setAddressWindow(uint16_t x0, uint16_t y0, uint16_t x1, uint16_t y1) {
    writeCommand(0x2A);
    digitalWrite(TFT_DC, HIGH);
    selectDisplay();
    writeData16Raw(x0);
    writeData16Raw(x1);
    unselectDisplay();

    writeCommand(0x2B);
    digitalWrite(TFT_DC, HIGH);
    selectDisplay();
    writeData16Raw(y0);
    writeData16Raw(y1);
    unselectDisplay();

    writeCommand(0x2C);
}

static void fillScreenRaw(uint16_t color) {
    setAddressWindow(0, 0, TFT_W - 1, TFT_H - 1);
    digitalWrite(TFT_DC, HIGH);
    selectDisplay();
    for (uint32_t i = 0; i < static_cast<uint32_t>(TFT_W) * TFT_H; ++i) {
        writeData16Raw(color);
    }
    unselectDisplay();
}

static void initDisplayRaw() {
    Serial.println("[FACE240] ST7789 raw init start");

    pinMode(TFT_CS, OUTPUT);
    pinMode(TFT_DC, OUTPUT);
    pinMode(TFT_RST, OUTPUT);
    pinMode(TFT_BL, OUTPUT);
    digitalWrite(TFT_CS, HIGH);
    digitalWrite(TFT_DC, HIGH);
    digitalWrite(TFT_BL, TFT_BACKLIGHT_ON);

    SPI.begin(TFT_SCLK, TFT_MISO, TFT_MOSI, TFT_CS);

    digitalWrite(TFT_RST, HIGH);
    delay(20);
    digitalWrite(TFT_RST, LOW);
    delay(30);
    digitalWrite(TFT_RST, HIGH);
    delay(150);

    writeCommand(0x01);
    delay(150);
    writeCommand(0x11);
    delay(150);
    writeCommand(0x3A);
    writeData8(0x55); // RGB565
    writeCommand(0x36);
    writeData8(ST7789_MADCTL_LANDSCAPE | ST7789_COLOR_ORDER);
    writeCommand(INVERT_COLORS ? 0x21 : 0x20);
    writeCommand(0x13);
    delay(20);
    writeCommand(0x29);
    delay(120);

    fillScreenRaw(C_BG);
    Serial.println("[FACE240] ST7789 raw init done");
}

static int16_t iround(float value) {
    return static_cast<int16_t>(value >= 0.0f ? value + 0.5f : value - 0.5f);
}

static int16_t intSqrt(int32_t v) {
    int16_t r = 0;
    while (static_cast<int32_t>(r + 1) * (r + 1) <= v) {
        ++r;
    }
    return r;
}

static void fillBuffer(uint16_t color) {
    const uint8_t hi = color >> 8;
    const uint8_t lo = color & 0xFF;
    for (size_t i = 0; i < FRAMEBUFFER_BYTES; i += 2) {
        frameBuffer[i] = hi;
        frameBuffer[i + 1] = lo;
    }
}

static void fillRectBuffer(int16_t x, int16_t y, int16_t w, int16_t h, uint16_t color) {
    if (w <= 0 || h <= 0 || x >= TFT_W || y >= TFT_H || x + w <= 0 || y + h <= 0) {
        return;
    }
    if (x < 0) { w += x; x = 0; }
    if (y < 0) { h += y; y = 0; }
    if (x + w > TFT_W) { w = TFT_W - x; }
    if (y + h > TFT_H) { h = TFT_H - y; }

    const uint8_t hi = color >> 8;
    const uint8_t lo = color & 0xFF;
    for (int16_t row = 0; row < h; ++row) {
        size_t idx = (static_cast<size_t>(y + row) * TFT_W + x) * 2;
        for (int16_t col = 0; col < w; ++col) {
            frameBuffer[idx++] = hi;
            frameBuffer[idx++] = lo;
        }
    }
}

static void fillCircleBuffer(int16_t cx, int16_t cy, int16_t r, uint16_t color) {
    if (r <= 0) {
        return;
    }
    const int32_t rr = static_cast<int32_t>(r) * r;
    for (int16_t y = -r; y <= r; ++y) {
        const int16_t span = intSqrt(rr - static_cast<int32_t>(y) * y);
        fillRectBuffer(cx - span, cy + y, span * 2 + 1, 1, color);
    }
}

static void fillRoundRectBuffer(int16_t x, int16_t y, int16_t w, int16_t h,
                                int16_t r, uint16_t color) {
    if (w <= 0 || h <= 0) {
        return;
    }
    r = i16max(0, i16min(r, i16min(w / 2, h / 2)));
    if (r == 0) {
        fillRectBuffer(x, y, w, h, color);
        return;
    }

    const int32_t rr = static_cast<int32_t>(r) * r;
    for (int16_t row = 0; row < h; ++row) {
        int16_t inset = 0;
        if (row < r) {
            const int16_t dy = r - row;
            inset = r - intSqrt(i32max(0, rr - static_cast<int32_t>(dy) * dy));
        } else if (row >= h - r) {
            const int16_t dy = row - (h - r - 1);
            inset = r - intSqrt(i32max(0, rr - static_cast<int32_t>(dy) * dy));
        }
        fillRectBuffer(x + inset, y + row, w - inset * 2, 1, color);
    }
}

static void pushFrameBuffer() {
    setAddressWindow(0, 0, TFT_W - 1, TFT_H - 1);
    digitalWrite(TFT_DC, HIGH);
    selectDisplay();
    SPI.writeBytes(frameBuffer, FRAMEBUFFER_BYTES);
    unselectDisplay();
}

static void pushFrameRegion(int16_t x, int16_t y, int16_t w, int16_t h) {
    if (w <= 0 || h <= 0 || x >= TFT_W || y >= TFT_H || x + w <= 0 || y + h <= 0) {
        return;
    }
    if (x < 0) { w += x; x = 0; }
    if (y < 0) { h += y; y = 0; }
    if (x + w > TFT_W) { w = TFT_W - x; }
    if (y + h > TFT_H) { h = TFT_H - y; }

    setAddressWindow(x, y, x + w - 1, y + h - 1);
    digitalWrite(TFT_DC, HIGH);
    selectDisplay();
    const size_t rowBytes = static_cast<size_t>(w) * 2;
    for (int16_t row = 0; row < h; ++row) {
        const size_t offset = (static_cast<size_t>(y + row) * TFT_W + x) * 2;
        SPI.writeBytes(frameBuffer + offset, rowBytes);
    }
    unselectDisplay();
}

static void drawLineThick(int16_t x0, int16_t y0, int16_t x1, int16_t y1,
                          int16_t thickness, uint16_t color) {
    const int16_t dx = x1 - x0;
    const int16_t dy = y1 - y0;
    const int16_t steps = i16max(abs(dx), abs(dy));
    const int16_t r = i16max(1, thickness / 2);
    for (int16_t i = 0; i <= steps; ++i) {
        const int16_t x = x0 + static_cast<int32_t>(dx) * i / i16max(1, steps);
        const int16_t y = y0 + static_cast<int32_t>(dy) * i / i16max(1, steps);
        fillCircleBuffer(x, y, r, color);
    }
}

static void drawArc(int16_t cx, int16_t cy, int16_t radius, float startRad,
                    float endRad, int16_t thickness, uint16_t color) {
    const int16_t segments = 38;
    int16_t px = cx + iround(cosf(startRad) * radius);
    int16_t py = cy + iround(sinf(startRad) * radius);
    for (int16_t i = 1; i <= segments; ++i) {
        const float a = startRad + (endRad - startRad) * i / segments;
        const int16_t x = cx + iround(cosf(a) * radius);
        const int16_t y = cy + iround(sinf(a) * radius);
        drawLineThick(px, py, x, y, thickness, color);
        px = x;
        py = y;
    }
}

static void drawGlowRoundRectCentered(int16_t cx, int16_t cy, int16_t w, int16_t h,
                                      uint16_t glow2, uint16_t glow, uint16_t color) {
    w = i16max(2, w);
    h = i16max(2, h);
    const int16_t r = i16max(1, i16min(w, h) / 2);
    fillRoundRectBuffer(cx - w / 2 - 10, cy - h / 2 - 10, w + 20, h + 20, r + 10, glow2);
    fillRoundRectBuffer(cx - w / 2 - 5, cy - h / 2 - 5, w + 10, h + 10, r + 5, glow);
    fillRoundRectBuffer(cx - w / 2, cy - h / 2, w, h, r, color);
}

static void drawGlowCircle(int16_t cx, int16_t cy, int16_t r,
                           uint16_t glow2, uint16_t glow, uint16_t color) {
    fillCircleBuffer(cx, cy, r + 11, glow2);
    fillCircleBuffer(cx, cy, r + 6, glow);
    fillCircleBuffer(cx, cy, r, color);
}

static void drawGlowingArc(int16_t cx, int16_t cy, int16_t radius, float startRad,
                           float endRad, int16_t thickness, uint16_t glow2,
                           uint16_t glow, uint16_t color) {
    drawArc(cx, cy, radius + 1, startRad, endRad, thickness + 13, glow2);
    drawArc(cx, cy, radius, startRad, endRad, thickness + 7, glow);
    drawArc(cx, cy, radius, startRad, endRad, thickness, color);
}

static void drawGlowingLine(int16_t x0, int16_t y0, int16_t x1, int16_t y1,
                            int16_t thickness, uint16_t glow2, uint16_t glow,
                            uint16_t color) {
    drawLineThick(x0, y0, x1, y1, thickness + 12, glow2);
    drawLineThick(x0, y0, x1, y1, thickness + 6, glow);
    drawLineThick(x0, y0, x1, y1, thickness, color);
}

static void clearActiveArea() {
    fillRectBuffer(ACTIVE_X, ACTIVE_Y, ACTIVE_W, ACTIVE_H, C_BG);
}

static EyeShape makeEye(float cx, float cy, float w, float h, EyeMode mode) {
    EyeShape e{cx, cy, w, h, mode};
    return e;
}

static MouthShape makeMouth(float cx, float cy, float w, float h, MouthMode mode) {
    MouthShape m{cx, cy, w, h, mode};
    return m;
}

static FacePose poseForExpression(FaceExpression face) {
    FacePose p{};
    p.left = makeEye(106, 94, 28, 28, EYE_DOT);
    p.right = makeEye(214, 94, 28, 28, EYE_DOT);
    p.mouth = makeMouth(160, 121, 54, 28, MOUTH_SMILE);
    p.color = C_CYAN;
    p.glow = C_CYAN_GLOW;
    p.glow2 = C_CYAN_GLOW2;
    p.symbolOnly = false;
    p.eyebrows = false;

    switch (face) {
        case FACE_HAPPY:
            p.left = makeEye(106, 93, 28, 28, EYE_DOT);
            p.right = makeEye(214, 93, 28, 28, EYE_DOT);
            p.mouth = makeMouth(160, 120, 58, 30, MOUTH_SMILE);
            break;
        case FACE_SAD:
            p.left = makeEye(111, 91, 48, 24, EYE_DROOP);
            p.right = makeEye(209, 91, 48, 24, EYE_DROOP);
            p.mouth = makeMouth(160, 143, 52, 22, MOUTH_FROWN);
            break;
        case FACE_SURPRISED:
            p.left = makeEye(106, 99, 26, 26, EYE_DOT);
            p.right = makeEye(214, 99, 26, 26, EYE_DOT);
            p.mouth = makeMouth(160, 132, 26, 26, MOUTH_ROUND);
            p.eyebrows = true;
            break;
        case FACE_ANGRY:
            p.left = makeEye(105, 93, 54, 30, EYE_SLANT_DOWN_RIGHT);
            p.right = makeEye(215, 93, 54, 30, EYE_SLANT_DOWN_LEFT);
            p.mouth = makeMouth(160, 144, 52, 22, MOUTH_FROWN);
            p.color = C_RED;
            p.glow = C_RED_GLOW;
            p.glow2 = C_RED_GLOW2;
            break;
        case FACE_CONTENT:
            p.left = makeEye(109, 101, 40, 22, EYE_CLOSED_SMILE);
            p.right = makeEye(211, 101, 40, 22, EYE_CLOSED_SMILE);
            p.mouth = makeMouth(160, 130, 46, 20, MOUTH_SMILE);
            break;
        case FACE_WINK:
            p.left = makeEye(108, 100, 24, 24, EYE_DOT);
            p.right = makeEye(210, 100, 52, 36, EYE_CHEVRON_LEFT);
            p.mouth = makeMouth(160, 130, 42, 18, MOUTH_SMILE);
            break;
        case FACE_DOTS:
        case FACE_QUESTION:
        case FACE_ALERT:
            p.left = makeEye(160, 100, 2, 2, EYE_HIDDEN);
            p.right = makeEye(160, 100, 2, 2, EYE_HIDDEN);
            p.mouth = makeMouth(160, 130, 2, 2, MOUTH_HIDDEN);
            p.symbolOnly = true;
            if (face == FACE_DOTS || face == FACE_ALERT) {
                p.color = C_RED;
                p.glow = C_RED_GLOW;
                p.glow2 = C_RED_GLOW2;
            } else {
                p.color = C_YELLOW;
                p.glow = C_YELLOW_GLOW;
                p.glow2 = C_YELLOW_GLOW2;
            }
            break;
        default:
            break;
    }
    return p;
}

static void copyPoseImmediate(const FacePose &p) {
    currentPose = p;
    targetPose = p;
    poseInitialized = true;
}

static void setPoseTarget(FaceExpression face, bool immediate) {
    targetPose = poseForExpression(face);
    if (immediate || !poseInitialized) {
        copyPoseImmediate(targetPose);
    } else {
        // Color and discrete shape modes switch immediately; size/position still morph.
        currentPose.color = targetPose.color;
        currentPose.glow = targetPose.glow;
        currentPose.glow2 = targetPose.glow2;
        currentPose.symbolOnly = targetPose.symbolOnly;
        currentPose.eyebrows = targetPose.eyebrows;
        currentPose.left.mode = targetPose.left.mode;
        currentPose.right.mode = targetPose.right.mode;
        currentPose.mouth.mode = targetPose.mouth.mode;
    }
}

static void updatePoseMorph() {
    constexpr float eyeEase = 0.22f;
    constexpr float mouthEase = 0.24f;

    currentPose.left.cx = fapproach(currentPose.left.cx, targetPose.left.cx, eyeEase);
    currentPose.left.cy = fapproach(currentPose.left.cy, targetPose.left.cy, eyeEase);
    currentPose.left.w = fapproach(currentPose.left.w, targetPose.left.w, eyeEase);
    currentPose.left.h = fapproach(currentPose.left.h, targetPose.left.h, eyeEase);
    currentPose.right.cx = fapproach(currentPose.right.cx, targetPose.right.cx, eyeEase);
    currentPose.right.cy = fapproach(currentPose.right.cy, targetPose.right.cy, eyeEase);
    currentPose.right.w = fapproach(currentPose.right.w, targetPose.right.w, eyeEase);
    currentPose.right.h = fapproach(currentPose.right.h, targetPose.right.h, eyeEase);

    currentPose.mouth.cx = fapproach(currentPose.mouth.cx, targetPose.mouth.cx, mouthEase);
    currentPose.mouth.cy = fapproach(currentPose.mouth.cy, targetPose.mouth.cy, mouthEase);
    currentPose.mouth.w = fapproach(currentPose.mouth.w, targetPose.mouth.w, mouthEase);
    currentPose.mouth.h = fapproach(currentPose.mouth.h, targetPose.mouth.h, mouthEase);
}

static float blinkScale(uint32_t now, bool enabled) {
    if (!enabled) {
        return 1.0f;
    }
    const uint32_t phase = now % 3900UL;
    if (phase > 130UL) {
        return 1.0f;
    }
    const uint32_t d = phase < 65UL ? phase : 130UL - phase;
    return 1.0f - static_cast<float>(d) * 0.90f / 65.0f;
}

static void drawEye(const EyeShape &e, uint32_t now, uint16_t glow2,
                    uint16_t glow, uint16_t color) {
    if (e.mode == EYE_HIDDEN) {
        return;
    }

    const int16_t idleX = iround(sinf(now / 1450.0f) * 1.1f);
    const int16_t idleY = iround(sinf(now / 1700.0f) * 0.8f);
    const int16_t cx = iround(e.cx) + idleX;
    const int16_t cy = iround(e.cy) + idleY;

    switch (e.mode) {
        case EYE_DOT: {
            const bool allowBlink = !currentPose.symbolOnly && expression != FACE_SURPRISED;
            const float blink = blinkScale(now, allowBlink);
            const int16_t w = i16max(4, iround(e.w));
            const int16_t h = i16max(3, iround(e.h * blink));
            drawGlowRoundRectCentered(cx, cy, w, h, glow2, glow, color);
            break;
        }
        case EYE_CLOSED_SMILE: {
            const int16_t radius = i16max(18, iround(e.w * 0.52f));
            const int16_t thickness = i16max(6, iround(e.h * 0.34f));
            drawGlowingArc(cx, cy + iround(e.h * 0.25f), radius, PI * 1.12f, PI * 1.88f,
                           thickness, glow2, glow, color);
            break;
        }
        case EYE_DROOP: {
            const int16_t radius = i16max(20, iround(e.w * 0.50f));
            const int16_t thickness = i16max(8, iround(e.h * 0.42f));
            drawGlowingArc(cx, cy - iround(e.h * 0.15f), radius, PI * 0.10f, PI * 0.90f,
                           thickness, glow2, glow, color);
            break;
        }
        case EYE_SLANT_DOWN_RIGHT: {
            const int16_t halfW = iround(e.w * 0.45f);
            const int16_t halfH = iround(e.h * 0.35f);
            drawGlowingLine(cx - halfW, cy - halfH, cx + halfW, cy + halfH,
                            i16max(11, iround(e.h * 0.48f)), glow2, glow, color);
            break;
        }
        case EYE_SLANT_DOWN_LEFT: {
            const int16_t halfW = iround(e.w * 0.45f);
            const int16_t halfH = iround(e.h * 0.35f);
            drawGlowingLine(cx + halfW, cy - halfH, cx - halfW, cy + halfH,
                            i16max(11, iround(e.h * 0.48f)), glow2, glow, color);
            break;
        }
        case EYE_CHEVRON_LEFT: {
            const int16_t halfW = iround(e.w * 0.45f);
            const int16_t halfH = iround(e.h * 0.50f);
            // Reference image uses a '<' shape on the right side: vertex on the left,
            // two open arms extending to the right.
            drawGlowingLine(cx + halfW, cy - halfH, cx - halfW, cy, 7, glow2, glow, color);
            drawGlowingLine(cx + halfW, cy + halfH, cx - halfW, cy, 7, glow2, glow, color);
            break;
        }
        default:
            break;
    }
}

static void drawMouth(const MouthShape &m, uint32_t now, uint16_t glow2,
                      uint16_t glow, uint16_t color) {
    if (m.mode == MOUTH_HIDDEN) {
        return;
    }
    const int16_t cx = iround(m.cx);
    const int16_t cy = iround(m.cy + sinf(now / 1000.0f) * 0.6f);
    const int16_t w = i16max(4, iround(m.w));
    const int16_t h = i16max(4, iround(m.h));

    switch (m.mode) {
        case MOUTH_SMILE: {
            drawGlowingArc(cx, cy - h / 2, i16max(16, w / 2), PI * 0.18f, PI * 0.82f,
                           i16max(6, h / 2), glow2, glow, color);
            break;
        }
        case MOUTH_FROWN: {
            drawGlowingArc(cx, cy + h / 2, i16max(16, w / 2), PI * 1.15f, PI * 1.85f,
                           i16max(7, h / 2), glow2, glow, color);
            break;
        }
        case MOUTH_ROUND: {
            drawGlowRoundRectCentered(cx, cy, w, h, glow2, glow, color);
            break;
        }
        default:
            break;
    }
}

static void drawSurpriseEyebrows(uint32_t now) {
    const int16_t wobble = iround(sinf(now / 620.0f) * 1.5f);
    drawGlowingArc(108, 73 + wobble, 22, PI * 1.20f, PI * 1.80f, 5,
                   C_CYAN_GLOW2, C_CYAN_GLOW, C_CYAN);
    drawGlowingArc(212, 73 + wobble, 22, PI * 1.20f, PI * 1.80f, 5,
                   C_CYAN_GLOW2, C_CYAN_GLOW, C_CYAN);
}

static void drawSymbolDots(uint32_t now) {
    const uint32_t t = now - expressionStartMs;
    const uint8_t active = (t / 280UL) % 3UL;
    for (uint8_t i = 0; i < 3; ++i) {
        const int16_t r = (i == active) ? 9 : 7;
        drawGlowCircle(112 + i * 48, 112, r, C_RED_GLOW2, C_RED_GLOW, C_RED);
    }
}

static void drawSymbolQuestion(uint32_t now) {
    const uint32_t t = now - expressionStartMs;
    const int16_t pulse = iround(sinf(t / 420.0f) * 1.5f);
    drawGlowingArc(156, 83, 33 + pulse, PI * 1.13f, PI * 2.12f, 9,
                   C_YELLOW_GLOW2, C_YELLOW_GLOW, C_YELLOW);
    drawGlowingLine(176, 100, 158, 132, 8,
                    C_YELLOW_GLOW2, C_YELLOW_GLOW, C_YELLOW);
    drawGlowCircle(160, 164, 8 + (pulse > 0 ? 1 : 0),
                   C_YELLOW_GLOW2, C_YELLOW_GLOW, C_YELLOW);
}

static void drawSymbolAlert(uint32_t now) {
    const uint32_t t = now - expressionStartMs;
    const int16_t pulse = iround(sinf(t / 220.0f) * 1.5f);
    drawGlowRoundRectCentered(160, 95, 14 + pulse, 76, C_RED_GLOW2, C_RED_GLOW, C_RED);
    drawGlowCircle(160, 162, 9 + (pulse > 0 ? 1 : 0), C_RED_GLOW2, C_RED_GLOW, C_RED);
}

static void setExpression(FaceExpression next, bool manual) {
    if (next >= FACE_COUNT) {
        return;
    }
    expression = next;
    expressionStartMs = millis();
    setPoseTarget(expression, false);
    if (manual) {
        autoCarousel = false;
        Serial.printf("[FACE240] manual face=%u auto=off\n", static_cast<unsigned>(expression + 1));
    }
}

static void updateExpressionTarget(uint32_t now) {
    if (!autoCarousel) {
        return;
    }
    const FaceExpression next = static_cast<FaceExpression>(((now - carouselStartMs) / 3000UL) % FACE_COUNT);
    if (next != expression) {
        setExpression(next, false);
    }
}

static void handleSerialInput() {
    while (Serial.available() > 0) {
        const char ch = static_cast<char>(Serial.read());
        if (ch >= '1' && ch <= '9') {
            setExpression(static_cast<FaceExpression>(ch - '1'), true);
        } else if (ch == '0' || ch == 'h' || ch == 'H') {
            setExpression(FACE_HAPPY, true);
        } else if (ch == 's' || ch == 'S') {
            setExpression(FACE_SAD, true);
        } else if (ch == 'o' || ch == 'O') {
            setExpression(FACE_SURPRISED, true);
        } else if (ch == 'a' || ch == 'A') {
            setExpression(FACE_ANGRY, true);
        } else if (ch == 'c' || ch == 'C') {
            setExpression(FACE_CONTENT, true);
        } else if (ch == 'w' || ch == 'W') {
            setExpression(FACE_WINK, true);
        } else if (ch == 'd' || ch == 'D') {
            setExpression(FACE_DOTS, true);
        } else if (ch == 'q' || ch == 'Q' || ch == '?') {
            setExpression(FACE_QUESTION, true);
        } else if (ch == '!' || ch == 'e' || ch == 'E') {
            setExpression(FACE_ALERT, true);
        } else if (ch == 'm' || ch == 'M') {
            autoCarousel = !autoCarousel;
            carouselStartMs = millis();
            Serial.printf("[FACE240] autoCarousel=%s\n", autoCarousel ? "on" : "off");
        }
    }
}

// External-style wrapper for later touch / voice / OpenClaw state-machine calls.
// Example: showRobotFace(FACE_WINK);
static void showRobotFace(FaceExpression face) {
    setExpression(face, true);
}

static void renderExpressionFrame(uint32_t now) {
    clearActiveArea();
    updatePoseMorph();

    if (expression == FACE_DOTS) {
        drawSymbolDots(now);
        return;
    }
    if (expression == FACE_QUESTION) {
        drawSymbolQuestion(now);
        return;
    }
    if (expression == FACE_ALERT) {
        drawSymbolAlert(now);
        return;
    }

    if (currentPose.eyebrows) {
        drawSurpriseEyebrows(now);
    }
    drawEye(currentPose.left, now, currentPose.glow2, currentPose.glow, currentPose.color);
    drawEye(currentPose.right, now, currentPose.glow2, currentPose.glow, currentPose.color);
    drawMouth(currentPose.mouth, now, currentPose.glow2, currentPose.glow, currentPose.color);
}

static void reportFps(uint32_t now) {
    ++fpsFrames;
    if (now - fpsWindowMs < 1000) {
        return;
    }
    Serial.printf("[FACE240] fps=%u face=%u auto=%u heap=%u\n",
                  fpsFrames,
                  static_cast<unsigned>(expression + 1),
                  static_cast<unsigned>(autoCarousel),
                  static_cast<unsigned>(ESP.getFreeHeap()));
    fpsFrames = 0;
    fpsWindowMs = now;
}

static FaceExpression protocolToFace(const char* tag) {
  if (!tag || !tag[0]) {
    return FACE_CONTENT;
  }
  if (strcmp(tag, Expression::HAPPY) == 0) return FACE_HAPPY;
  if (strcmp(tag, Expression::SAD) == 0) return FACE_SAD;
  if (strcmp(tag, Expression::CARING) == 0) return FACE_WINK;
  if (strcmp(tag, Expression::TIRED) == 0) return FACE_SAD;
  if (strcmp(tag, Expression::THINKING) == 0 || strcmp(tag, Expression::LISTENING) == 0) {
    return FACE_QUESTION;
  }
  if (strcmp(tag, Expression::SPEAKING) == 0) return FACE_HAPPY;
  if (strcmp(tag, Expression::SURPRISED) == 0) return FACE_SURPRISED;
  if (strcmp(tag, Expression::SLEEPING) == 0) return FACE_CONTENT;
  if (strcmp(tag, Expression::ERROR) == 0) return FACE_ALERT;
  if (strcmp(tag, Expression::NEUTRAL) == 0 || strcmp(tag, Expression::IDLE) == 0) {
    return FACE_CONTENT;
  }
  return FACE_CONTENT;
}

void face240_init() {
    Serial.begin(115200);
    waitForSerialWindow();
    Serial.println();
    Serial.println("[FACE240] merged 9 inner expressions - no shell");
    Serial.println("[FACE240] Serial: 1-9 select expression, m toggles auto carousel");
    Serial.println("[FACE240] Pins: SCLK=12 MOSI=11 CS=10 DC=9 RST=14 BL=21");

    randomSeed(static_cast<uint32_t>(esp_random()));
    pinMode(TFT_BL, OUTPUT);
    digitalWrite(TFT_BL, TFT_BACKLIGHT_ON);
    initDisplayRaw();

    const uint32_t now = millis();
    carouselStartMs = now;
    expressionStartMs = now;
    fpsWindowMs = now;
  copyPoseImmediate(poseForExpression(FACE_CONTENT));
  fillBuffer(C_BG);
  pushFrameBuffer();
  LOGI("Face240", "ST7789 9-expression renderer ready");
}

void face240_emotion(const char* emotion_tag, int /*intensity*/) {
  setExpression(protocolToFace(emotion_tag), true);
}

void face240_tick() {
    const uint32_t now = millis();
    handleSerialInput();

    if (now - lastFrameMs < FRAME_MS) {
        delay(1);
        return;
    }
    lastFrameMs = now;

    updateExpressionTarget(now);
    renderExpressionFrame(now);
    pushFrameRegion(ACTIVE_X, ACTIVE_Y, ACTIVE_W, ACTIVE_H);
    reportFps(now);
}
