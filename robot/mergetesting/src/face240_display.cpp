#include "face240_display.h"
#include "protocol.h"
#include "debug_log.h"
#include <string.h>

#include <Arduino.h>
#include <SPI.h>
#include <math.h>

#include "hardware_pins.h"
static constexpr int16_t TFT_W = 320;
static constexpr int16_t TFT_H = 240;
static constexpr size_t FRAMEBUFFER_BYTES = static_cast<size_t>(TFT_W) * TFT_H * 2;
static constexpr uint32_t SERIAL_WAIT_MS = 2500;
static constexpr uint32_t SPI_HZ = 80000000;
static constexpr uint32_t FRAME_MS = 16;

static constexpr int16_t MARGIN_X = 16;
static constexpr int16_t MARGIN_Y = 16;
static constexpr int16_t MARGIN_W = 288;
static constexpr int16_t MARGIN_H = 208;

static constexpr uint8_t ST7789_MADCTL_LANDSCAPE = 0x60;
static constexpr uint8_t ST7789_COLOR_ORDER = 0x00;
static constexpr bool INVERT_COLORS = false;

static constexpr uint16_t rgb565(uint8_t r, uint8_t g, uint8_t b) {
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3);
}

static constexpr uint16_t C_BG = rgb565(0, 7, 13);
static constexpr uint16_t C_CYAN = rgb565(126, 255, 242);
static constexpr uint16_t C_CYAN_SOFT = rgb565(176, 236, 255);
static constexpr uint16_t C_RED = rgb565(255, 58, 68);
static constexpr uint16_t C_YELLOW = rgb565(255, 229, 55);

/** Full-screen face layout (~1.12x, centered on 320x240). */
static constexpr int16_t FACE_CX = 160;
static constexpr int16_t FACE_CY = 118;
static constexpr int16_t EYE_CX_L = 84;
static constexpr int16_t EYE_CX_R = 236;
static constexpr int16_t EYE_CY = 100;
static constexpr int16_t EYE_W_DEF = 74;
static constexpr int16_t EYE_H_DEF = 65;
static constexpr int16_t MOUTH_CY = 181;
static constexpr int16_t BROW_CY = 66;
static constexpr int16_t ARC_SEGMENTS = 64;
static constexpr int16_t STROKE_MOUTH = 11;
static constexpr int16_t STROKE_BROW = 9;
static constexpr int16_t STROKE_RING = 11;

static uint8_t frameBuffer[FRAMEBUFFER_BYTES];

enum FaceExpression : uint8_t {
    FACE_HAPPY = 0,
    FACE_SAD,
    FACE_SURPRISED,
    FACE_ANGRY,
    FACE_CONTENT,
    FACE_WINK,
    FACE_DOTS,
    FACE_QUESTION,
    FACE_ALERT,
    FACE_COUNT,
};

enum EyeMode : uint8_t {
    EYE_PILL,
    EYE_SQUINT,
    EYE_DROOP,
    EYE_SLANT_RIGHT,
    EYE_SLANT_LEFT,
    EYE_CHEVRON,
    EYE_HIDDEN,
};

enum MouthMode : uint8_t {
    MOUTH_SMILE,
    MOUTH_SMILE_WIDE,
    MOUTH_FROWN,
    MOUTH_ROUND,
    MOUTH_BOWL,
    MOUTH_HIDDEN,
};

enum LidMode : uint8_t {
    LID_NONE,
    LID_TIRED,
    LID_ANGRY,
    LID_HAPPY,
};

struct EyeShape {
    float cx;
    float cy;
    float w;
    float h;
    EyeMode mode;
    LidMode lid;
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
    bool symbolOnly;
    bool eyebrows;
};

/** Kept for structural tests and legacy callers. */
struct EyeBox {
    float x;
    float y;
    float w;
    float h;
    float r;
};

static FaceExpression expression = FACE_HAPPY;
static FacePose currentPose;
static FacePose targetPose;
static bool poseInitialized = false;
static bool autoCarousel = false;
static bool fullScreenPush = true;
static uint8_t lowFpsStreak = 0;

static uint32_t carouselStartMs = 0;
static uint32_t expressionStartMs = 0;
static uint32_t lastFrameMs = 0;
static uint32_t fpsWindowMs = 0;
static uint16_t fpsFrames = 0;

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
    digitalWrite(TFT_CS, HIGH);
    digitalWrite(TFT_DC, HIGH);
    if (TFT_BL >= 0) {
        pinMode(TFT_BL, OUTPUT);
        digitalWrite(TFT_BL, TFT_BACKLIGHT_ON);
    }

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
    writeData8(0x55);
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

static void swapInt16(int16_t &a, int16_t &b) {
    const int16_t tmp = a;
    a = b;
    b = tmp;
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
    if (x < 0) {
        w += x;
        x = 0;
    }
    if (y < 0) {
        h += y;
        y = 0;
    }
    if (x + w > TFT_W) {
        w = TFT_W - x;
    }
    if (y + h > TFT_H) {
        h = TFT_H - y;
    }

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

/** Filled bottom semicircle: flat top at topY, curved bottom at topY + r. */
static void fillBottomSemicircle(int16_t cx, int16_t topY, int16_t r, uint16_t color) {
    if (r <= 0) {
        return;
    }
    const int32_t rr = static_cast<int32_t>(r) * r;
    for (int16_t y = 0; y <= r; ++y) {
        const int16_t span = intSqrt(rr - static_cast<int32_t>(y) * y);
        fillRectBuffer(cx - span, topY + y, span * 2 + 1, 1, color);
    }
}

static void fillRoundRectBuffer(int16_t x, int16_t y, int16_t w, int16_t h, int16_t r,
                                uint16_t color) {
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

static void fillTriangleBuffer(int16_t x0, int16_t y0, int16_t x1, int16_t y1, int16_t x2,
                               int16_t y2, uint16_t color) {
    if (y0 > y1) {
        swapInt16(y0, y1);
        swapInt16(x0, x1);
    }
    if (y1 > y2) {
        swapInt16(y1, y2);
        swapInt16(x1, x2);
    }
    if (y0 > y1) {
        swapInt16(y0, y1);
        swapInt16(x0, x1);
    }

    const int32_t totalHeight = y2 - y0;
    if (totalHeight == 0) {
        return;
    }
    for (int16_t y = y0; y <= y2; ++y) {
        const bool secondHalf = y > y1 || y1 == y0;
        const int32_t segmentHeight = secondHalf ? y2 - y1 : y1 - y0;
        if (segmentHeight == 0) {
            continue;
        }
        const float alpha = static_cast<float>(y - y0) / totalHeight;
        const float beta = secondHalf ? static_cast<float>(y - y1) / segmentHeight
                                      : static_cast<float>(y - y0) / segmentHeight;
        int16_t ax = x0 + iround((x2 - x0) * alpha);
        int16_t bx = secondHalf ? x1 + iround((x2 - x1) * beta)
                                : x0 + iround((x1 - x0) * beta);
        if (ax > bx) {
            swapInt16(ax, bx);
        }
        fillRectBuffer(ax, y, bx - ax + 1, 1, color);
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
    if (x < 0) {
        w += x;
        x = 0;
    }
    if (y < 0) {
        h += y;
        y = 0;
    }
    if (x + w > TFT_W) {
        w = TFT_W - x;
    }
    if (y + h > TFT_H) {
        h = TFT_H - y;
    }

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

static void pushRoboEyesFrame() {
    if (fullScreenPush) {
        pushFrameBuffer();
    } else {
        pushFrameRegion(MARGIN_X, MARGIN_Y, MARGIN_W, MARGIN_H);
    }
}

static void drawLineThick(int16_t x0, int16_t y0, int16_t x1, int16_t y1, int16_t thickness,
                          uint16_t color) {
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

static void drawArc(int16_t cx, int16_t cy, int16_t radius, float startRad, float endRad,
                    int16_t thickness, uint16_t color) {
    int16_t px = cx + iround(cosf(startRad) * radius);
    int16_t py = cy + iround(sinf(startRad) * radius);
    for (int16_t i = 1; i <= ARC_SEGMENTS; ++i) {
        const float a = startRad + (endRad - startRad) * i / ARC_SEGMENTS;
        const int16_t x = cx + iround(cosf(a) * radius);
        const int16_t y = cy + iround(sinf(a) * radius);
        drawLineThick(px, py, x, y, thickness, color);
        px = x;
        py = y;
    }
}

static void drawRoundRing(int16_t cx, int16_t cy, int16_t outerR, int16_t thickness,
                          uint16_t color) {
    fillCircleBuffer(cx, cy, outerR, color);
    if (outerR > thickness) {
        fillCircleBuffer(cx, cy, outerR - thickness, C_BG);
    }
}

static void clearDrawArea() {
    if (fullScreenPush) {
        fillBuffer(C_BG);
    } else {
        fillRectBuffer(MARGIN_X, MARGIN_Y, MARGIN_W, MARGIN_H, C_BG);
    }
}

static EyeShape makeEye(float cx, float cy, float w, float h, EyeMode mode, LidMode lid) {
    return EyeShape{cx, cy, w, h, mode, lid};
}

static MouthShape makeMouth(float cx, float cy, float w, float h, MouthMode mode) {
    return MouthShape{cx, cy, w, h, mode};
}

static FacePose poseForExpression(FaceExpression face) {
    FacePose p{};
    p.color = C_CYAN_SOFT;
    p.symbolOnly = false;
    p.eyebrows = false;
    p.left = makeEye(EYE_CX_L, EYE_CY, EYE_W_DEF, EYE_H_DEF, EYE_PILL, LID_NONE);
    p.right = makeEye(EYE_CX_R, EYE_CY, EYE_W_DEF, EYE_H_DEF, EYE_PILL, LID_NONE);
    p.mouth = makeMouth(FACE_CX, MOUTH_CY - 8, 48, 24, MOUTH_SMILE);

    switch (face) {
        case FACE_HAPPY:
            p.color = C_CYAN_SOFT;
            p.mouth = makeMouth(FACE_CX, MOUTH_CY, 85, 43, MOUTH_BOWL);
            break;
        case FACE_SAD:
            p.left.lid = LID_TIRED;
            p.right.lid = LID_TIRED;
            p.mouth = makeMouth(FACE_CX, MOUTH_CY, 56, 25, MOUTH_FROWN);
            break;
        case FACE_SURPRISED:
            p.left.h = EYE_H_DEF + 4;
            p.right.h = EYE_H_DEF + 4;
            p.mouth = makeMouth(FACE_CX, MOUTH_CY - 4, 40, 40, MOUTH_ROUND);
            p.eyebrows = true;
            break;
        case FACE_ANGRY:
            p.left.lid = LID_ANGRY;
            p.right.lid = LID_ANGRY;
            p.mouth = makeMouth(FACE_CX, MOUTH_CY + 2, 54, 25, MOUTH_FROWN);
            p.color = C_RED;
            break;
        case FACE_CONTENT:
            p.left.lid = LID_HAPPY;
            p.right.lid = LID_HAPPY;
            p.mouth = makeMouth(FACE_CX, MOUTH_CY - 6, 65, 27, MOUTH_SMILE_WIDE);
            break;
        case FACE_WINK:
            p.right.w = 65;
            p.right.h = 11;
            p.mouth = makeMouth(FACE_CX, MOUTH_CY - 4, 52, 25, MOUTH_SMILE);
            break;
        case FACE_DOTS:
        case FACE_QUESTION:
        case FACE_ALERT:
            p.left = makeEye(FACE_CX, FACE_CY, 2, 2, EYE_HIDDEN, LID_NONE);
            p.right = makeEye(FACE_CX, FACE_CY, 2, 2, EYE_HIDDEN, LID_NONE);
            p.mouth = makeMouth(FACE_CX, FACE_CY, 2, 2, MOUTH_HIDDEN);
            p.symbolOnly = true;
            p.color = (face == FACE_QUESTION) ? C_YELLOW : C_RED;
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
        return;
    }
    currentPose.color = targetPose.color;
    currentPose.symbolOnly = targetPose.symbolOnly;
    currentPose.eyebrows = targetPose.eyebrows;
    currentPose.left.mode = targetPose.left.mode;
    currentPose.left.lid = targetPose.left.lid;
    currentPose.right.mode = targetPose.right.mode;
    currentPose.right.lid = targetPose.right.lid;
    currentPose.mouth.mode = targetPose.mouth.mode;
}

static void updatePoseMorph() {
    constexpr float kEye = 0.24f;
    constexpr float kMouth = 0.26f;

    currentPose.left.cx = fapproach(currentPose.left.cx, targetPose.left.cx, kEye);
    currentPose.left.cy = fapproach(currentPose.left.cy, targetPose.left.cy, kEye);
    currentPose.left.w = fapproach(currentPose.left.w, targetPose.left.w, kEye);
    currentPose.left.h = fapproach(currentPose.left.h, targetPose.left.h, kEye);
    currentPose.right.cx = fapproach(currentPose.right.cx, targetPose.right.cx, kEye);
    currentPose.right.cy = fapproach(currentPose.right.cy, targetPose.right.cy, kEye);
    currentPose.right.w = fapproach(currentPose.right.w, targetPose.right.w, kEye);
    currentPose.right.h = fapproach(currentPose.right.h, targetPose.right.h, kEye);

    currentPose.mouth.cx = fapproach(currentPose.mouth.cx, targetPose.mouth.cx, kMouth);
    currentPose.mouth.cy = fapproach(currentPose.mouth.cy, targetPose.mouth.cy, kMouth);
    currentPose.mouth.w = fapproach(currentPose.mouth.w, targetPose.mouth.w, kMouth);
    currentPose.mouth.h = fapproach(currentPose.mouth.h, targetPose.mouth.h, kMouth);
}

static float blinkScale(uint32_t now, bool enabled) {
    if (!enabled) {
        return 1.0f;
    }
    const uint32_t phase = now % 3800UL;
    if (phase > 120UL) {
        return 1.0f;
    }
    const uint32_t d = phase < 60UL ? phase : 120UL - phase;
    return max<float>(0.08f, 1.0f - static_cast<float>(d) * 0.92f / 60.0f);
}

static void applyRoboLids(int16_t x, int16_t y, int16_t w, int16_t h, LidMode lid, bool leftEye) {
    if (lid == LID_NONE || h <= 2) {
        return;
    }
    const int16_t lidH = max<int16_t>(2, h / 2);
    if (lid == LID_TIRED) {
        if (leftEye) {
            fillTriangleBuffer(x, y - 1, x + w, y - 1, x, y + lidH - 1, C_BG);
        } else {
            fillTriangleBuffer(x, y - 1, x + w, y - 1, x + w, y + lidH - 1, C_BG);
        }
    } else if (lid == LID_ANGRY) {
        if (leftEye) {
            fillTriangleBuffer(x, y - 1, x + w, y - 1, x + w, y + lidH - 1, C_BG);
        } else {
            fillTriangleBuffer(x, y - 1, x + w, y - 1, x, y + lidH - 1, C_BG);
        }
    } else if (lid == LID_HAPPY) {
        fillRoundRectBuffer(x - 1, y + h - lidH + 1, w + 2, h, h / 2, C_BG);
    }
}

static void drawPillEye(int16_t cx, int16_t cy, int16_t w, int16_t h, uint16_t color, LidMode lid,
                        bool leftEye) {
    const int16_t r = i16max(2, i16min(w, h) / 2);
    const int16_t x = cx - w / 2;
    const int16_t y = cy - h / 2;
    fillRoundRectBuffer(x, y, w, h, r, color);
    applyRoboLids(x, y, w, h, lid, leftEye);
}

static void applyExprIdle(FaceExpression face, uint32_t now, bool leftEye, int16_t &idleX,
                          int16_t &idleY) {
    switch (face) {
        case FACE_HAPPY:
            idleX += iround(sinf(now / 2000.0f) * 1.2f);
            idleY += iround(cosf(now / 2400.0f) * 0.8f);
            break;
        case FACE_SAD:
            idleY += iround(sinf(now / 2200.0f) * 2.2f) + 1;
            break;
        case FACE_SURPRISED:
            idleX += iround(sinf(now / 520.0f) * 0.8f);
            idleY += iround(sinf(now / 680.0f) * 1.4f);
            break;
        case FACE_ANGRY:
            idleX += iround(sinf(now / 85.0f) * 2.4f);
            idleY += iround(sinf(now / 120.0f) * 0.6f);
            break;
        case FACE_CONTENT:
            idleX += iround(sinf(now / 2800.0f) * 2.0f);
            idleY += iround(cosf(now / 3200.0f) * 0.6f);
            break;
        case FACE_WINK:
            if (leftEye) {
                idleX += iround(sinf(now / 1100.0f) * 1.0f);
            }
            break;
        default:
            break;
    }
}

static void drawEyeShape(const EyeShape &e, uint32_t now, uint16_t color, bool leftEye) {
    if (e.mode == EYE_HIDDEN) {
        return;
    }

    int16_t idleX = iround(sinf(now / 1600.0f) * 1.5f);
    int16_t idleY = iround(sinf(now / 1900.0f) * 1.0f);
    applyExprIdle(expression, now, leftEye, idleX, idleY);
    const int16_t cx = iround(e.cx) + idleX;
    const int16_t cy = iround(e.cy) + idleY;

    if (e.mode != EYE_PILL) {
        return;
    }

    const bool isWinkClosed = expression == FACE_WINK && !leftEye;
    const bool allowBlink =
        !currentPose.symbolOnly && expression != FACE_SURPRISED && !isWinkClosed;
    const float blink = blinkScale(now, allowBlink);
    int16_t w = i16max(6, iround(e.w));
    int16_t h = i16max(isWinkClosed ? 6 : 8, iround(e.h * (isWinkClosed ? 1.0f : blink)));
    const int16_t fullH = i16max(6, iround(e.h));
    const int16_t drawCy = cy + (fullH - h) / 2;
    const LidMode lid = isWinkClosed ? LID_NONE : e.lid;
    drawPillEye(cx, drawCy, w, h, color, lid, leftEye);
}

static void drawMouthShape(const MouthShape &m, uint32_t now, uint16_t color) {
    if (m.mode == MOUTH_HIDDEN) {
        return;
    }
    float cx = m.cx;
    float cy = m.cy;
    float w = m.w;
    float h = m.h;

    switch (expression) {
        case FACE_HAPPY:
            if (m.mode == MOUTH_BOWL) {
                cy += sinf(now / 900.0f) * 1.5f;
                w += sinf(now / 1200.0f) * 1.2f;
            }
            break;
        case FACE_SAD:
            if (m.mode == MOUTH_FROWN) {
                cy += sinf(now / 1800.0f) * 1.0f;
            }
            break;
        case FACE_SURPRISED:
            if (m.mode == MOUTH_ROUND) {
                w += sinf(now / 420.0f) * 2.0f;
                h += sinf(now / 420.0f) * 2.0f;
            }
            break;
        case FACE_ANGRY:
            if (m.mode == MOUTH_FROWN) {
                cx += sinf(now / 90.0f) * 1.8f;
            }
            break;
        case FACE_CONTENT:
            if (m.mode == MOUTH_SMILE_WIDE) {
                w += sinf(now / 1400.0f) * 1.5f;
            }
            break;
        case FACE_WINK:
            if (m.mode == MOUTH_SMILE) {
                cy += sinf(now / 700.0f) * 1.0f;
            }
            break;
        default:
            break;
    }

    const int16_t icx = iround(cx);
    const int16_t icy = iround(cy);
    const int16_t iw = i16max(4, iround(w));
    const int16_t ih = i16max(4, iround(h));

    switch (m.mode) {
        case MOUTH_SMILE:
            drawArc(icx, icy - ih / 3, i16max(22, iw / 2), PI * 0.20f, PI * 0.80f,
                    STROKE_MOUTH - 1, color);
            break;
        case MOUTH_SMILE_WIDE:
            drawArc(icx, icy - ih / 3, i16max(31, iw / 2), PI * 0.18f, PI * 0.82f, STROKE_MOUTH,
                    color);
            break;
        case MOUTH_FROWN:
            drawArc(icx, icy + ih / 3, i16max(25, iw / 2), PI * 1.17f, PI * 1.83f, STROKE_MOUTH,
                    color);
            break;
        case MOUTH_ROUND:
            drawRoundRing(icx, icy, i16max(18, iw / 2), STROKE_RING, color);
            break;
        case MOUTH_BOWL: {
            const int16_t r = i16max(12, iw / 2);
            const int16_t bottomY = icy;
            const int16_t topY = bottomY - r;
            fillBottomSemicircle(icx, topY, r, color);
            break;
        }
        default:
            break;
    }
}

static void drawSurpriseBrows(uint32_t now) {
    const int16_t wobble = iround(sinf(now / 520.0f) * 1.8f);
    drawArc(EYE_CX_L, BROW_CY + wobble, 27, PI * 1.22f, PI * 1.78f, STROKE_BROW, C_CYAN_SOFT);
    drawArc(EYE_CX_R, BROW_CY + wobble, 27, PI * 1.22f, PI * 1.78f, STROKE_BROW, C_CYAN_SOFT);
}

static void drawSymbolDots(uint32_t now) {
    const uint32_t t = now - expressionStartMs;
    const uint8_t active = (t / 300UL) % 3UL;
    for (uint8_t i = 0; i < 3; ++i) {
        const int16_t r = (i == active) ? 17 : 12;
        fillCircleBuffer(88 + i * 72, FACE_CY + 10, r, C_RED);
    }
}

static void drawSymbolQuestion(uint32_t now) {
    const uint32_t t = now - expressionStartMs;
    const int16_t pulse = iround(sinf(t / 450.0f) * 0.8f);
    const int16_t stroke = 16;
    const int16_t sx = FACE_CX;
    const int16_t cy = 76;
    const int16_t r = 45 + pulse / 2;
    const float a0 = PI;
    const float a1 = a0 + PI * 1.5f;

    drawArc(sx, cy, r, a0, a1, stroke, C_YELLOW);
    drawLineThick(sx, cy + r, sx, 162, stroke, C_YELLOW);

    const int16_t dotR = 13 + (pulse > 0 ? 1 : 0);
    fillCircleBuffer(sx, 186, dotR, C_YELLOW);
}

static void drawSymbolAlert(uint32_t now) {
    const uint32_t t = now - expressionStartMs;
    const int16_t pulse = iround(sinf(t / 240.0f) * 2.5f);
    fillRoundRectBuffer(FACE_CX - 16 - pulse / 2, 58, 32 + pulse, 118, 16, C_RED);
    fillCircleBuffer(FACE_CX, 192, 18 + (pulse > 0 ? 1 : 0), C_RED);
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
        Serial.printf("[FACE240] manual face=%u push=%s\n",
                      static_cast<unsigned>(expression + 1),
                      fullScreenPush ? "full" : "margin");
    }
}

static void handleSerialInput() {
    while (Serial.available() > 0) {
        const char ch = static_cast<char>(Serial.read());
        if (ch >= '1' && ch <= '9') {
            setExpression(static_cast<FaceExpression>(ch - '1'), true);
        } else if (ch == 'm' || ch == 'M') {
            autoCarousel = !autoCarousel;
            carouselStartMs = millis();
            Serial.printf("[FACE240] autoCarousel=%s\n", autoCarousel ? "on" : "off");
        } else if (ch == 'f' || ch == 'F') {
            fullScreenPush = !fullScreenPush;
            lowFpsStreak = 0;
            Serial.printf("[FACE240] push mode=%s\n", fullScreenPush ? "full" : "margin");
        }
    }
}

static void updateRoboEyesTargets(uint32_t now) {
    if (!autoCarousel) {
        return;
    }
    const FaceExpression next =
        static_cast<FaceExpression>(((now - carouselStartMs) / 3500UL) % FACE_COUNT);
    if (next != expression) {
        setExpression(next, false);
    }
}

static void renderRoboEyesFrame(uint32_t now) {
    clearDrawArea();
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
        drawSurpriseBrows(now);
    }
    drawEyeShape(currentPose.left, now, currentPose.color, true);
    drawEyeShape(currentPose.right, now, currentPose.color, false);
    drawMouthShape(currentPose.mouth, now, currentPose.color);
}

static void drawRoboEye(const EyeBox &box, bool rightSide) {
    (void)rightSide;
    fillRoundRectBuffer(iround(box.x), iround(box.y), iround(box.w), iround(box.h),
                        iround(box.r), C_CYAN);
}

static void reportFps(uint32_t now) {
    ++fpsFrames;
    if (now - fpsWindowMs < 1000) {
        return;
    }

    if (fullScreenPush) {
        if (fpsFrames < 26) {
            ++lowFpsStreak;
        } else {
            lowFpsStreak = 0;
        }
        if (lowFpsStreak >= 2) {
            fullScreenPush = false;
            lowFpsStreak = 0;
            Serial.println("[FACE240] fps low -> auto margin push (send F to retry full)");
        }
    }

    Serial.printf("[FACE240] fps=%u face=%u push=%s auto=%u heap=%u\n",
                  fpsFrames,
                  static_cast<unsigned>(expression + 1),
                  fullScreenPush ? "full" : "margin",
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
    LOGI("Face240", "RoboEyes hybrid synced from firmware face240_roboeyes_test");
    LOGI("Face240", "Pins SCLK=%d MOSI=%d CS=%d DC=%d RST=%d BL=%d",
         TFT_SCLK, TFT_MOSI, TFT_CS, TFT_DC, TFT_RST, TFT_BL);

    randomSeed(static_cast<uint32_t>(esp_random()));
    if (TFT_BL >= 0) {
        pinMode(TFT_BL, OUTPUT);
        digitalWrite(TFT_BL, TFT_BACKLIGHT_ON);
    }
    initDisplayRaw();

    const uint32_t now = millis();
    carouselStartMs = now;
    expressionStartMs = now;
    fpsWindowMs = now;
    copyPoseImmediate(poseForExpression(FACE_CONTENT));
    fillBuffer(C_BG);
    pushFrameBuffer();
    LOGI("Face240", "ST7789 RoboEyes renderer ready");
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

    updateRoboEyesTargets(now);
    renderRoboEyesFrame(now);
    pushRoboEyesFrame();
    reportFps(now);
}
