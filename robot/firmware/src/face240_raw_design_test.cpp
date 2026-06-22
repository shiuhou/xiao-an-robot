#include <Arduino.h>
#include <SPI.h>

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
static constexpr uint32_t SERIAL_WAIT_MS = 1800;
static constexpr uint32_t SPI_HZ = 40000000;
static constexpr uint32_t FRAME_MS = 18;
static constexpr uint32_t EXPRESSION_MS = 3300;
static constexpr int16_t FACE_X0 = 36;
static constexpr int16_t FACE_Y0 = 38;
static constexpr int16_t FACE_W = 248;
static constexpr int16_t FACE_H = 162;

// This is the raw ST7789 setup that already works on the user's red 2.4" module.
static constexpr uint8_t ST7789_MADCTL_LANDSCAPE = 0x60;
static constexpr uint8_t ST7789_COLOR_ORDER = 0x00;
static constexpr bool INVERT_COLORS = false;

static constexpr uint16_t C_BG = 0x0000;
static constexpr uint16_t C_CYAN = 0x07FF;
static constexpr uint16_t C_CYAN_GLOW = 0x0357;
static constexpr uint16_t C_CYAN_DIM = 0x01AC;
static constexpr uint16_t C_WHITE_BLUE = 0xBF9F;

static uint8_t lineBuffer[TFT_W * 2];

struct DirtyRect {
    int16_t x;
    int16_t y;
    int16_t w;
    int16_t h;
};

static constexpr uint8_t MAX_DIRTY_RECTS = 10;

enum FaceExpression : uint8_t {
    FACE_NORMAL,
    FACE_HAPPY,
    FACE_ANGRY,
    FACE_TIRED,
    FACE_THINKING,
    FACE_SPEAKING,
    FACE_ERROR,
    FACE_SLEEP,
    FACE_COUNT
};

enum EyeType : uint8_t {
    EYE_PILL,
    EYE_HAPPY_ARC,
    EYE_ANGRY,
    EYE_TIRED,
    EYE_THINKING,
    EYE_SLEEP_ARC
};

enum MouthType : uint8_t {
    MOUTH_SMALL_SMILE,
    MOUTH_SMILE,
    MOUTH_FLAT,
    MOUTH_O,
    MOUTH_WAVE,
    MOUTH_ERROR_WAVE,
    MOUTH_SLEEP
};

struct FaceStyle {
    EyeType eyeType;
    MouthType mouthType;
    int16_t eyeW;
    int16_t eyeH;
    int16_t eyeY;
    int16_t eyeGap;
    int16_t mouthY;
    bool extraEffect;
};

static const FaceStyle FACE_STYLES[FACE_COUNT] = {
    {EYE_PILL,      MOUTH_SMALL_SMILE, 32, 60, 65, 72, 155, false},
    {EYE_HAPPY_ARC, MOUTH_SMILE,       62, 40, 77, 64, 157, true},
    {EYE_ANGRY,     MOUTH_FLAT,        42, 58, 66, 68, 155, true},
    {EYE_TIRED,     MOUTH_FLAT,        66, 42, 80, 58, 155, false},
    {EYE_THINKING,  MOUTH_O,           34, 60, 65, 70, 159, true},
    {EYE_PILL,      MOUTH_WAVE,        34, 62, 64, 70, 157, false},
    {EYE_THINKING,  MOUTH_ERROR_WAVE,  34, 62, 64, 72, 158, true},
    {EYE_SLEEP_ARC, MOUTH_SLEEP,       72, 30, 87, 72, 163, true},
};

static FaceExpression currentExpression = FACE_NORMAL;
static uint32_t expressionStartMs = 0;
static uint32_t lastFrameMs = 0;
static bool sleepStarEnabled = true;
static float animEyeW = 32;
static float animEyeH = 60;
static float animEyeY = 65;
static float animEyeGap = 72;
static float animMouthY = 155;
static float gazeX = 0;
static float gazeY = 0;
static float targetGazeX = 0;
static float targetGazeY = 0;
static uint32_t nextGazeMs = 0;
static uint32_t nextBlinkMs = 0;
static uint32_t blinkStartMs = 0;
static bool blinking = false;
static DirtyRect lastDynamicRects[MAX_DIRTY_RECTS];
static uint8_t lastDynamicRectCount = 0;
static bool fullFaceRefreshPending = false;
static uint32_t fpsWindowStartMs = 0;
static uint16_t fpsFrameCount = 0;
static uint32_t fpsPixelCount = 0;

static void setLinePixel(int16_t localX, uint16_t color) {
    lineBuffer[localX * 2] = color >> 8;
    lineBuffer[localX * 2 + 1] = color & 0xFF;
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
    Serial.println("[FACE240_RAW] ST7789 raw init start");

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

    writeCommand(0x01); // Software reset
    delay(150);
    writeCommand(0x11); // Sleep out
    delay(150);
    writeCommand(0x3A); // RGB565
    writeData8(0x55);
    writeCommand(0x36); // Memory access control
    writeData8(ST7789_MADCTL_LANDSCAPE | ST7789_COLOR_ORDER);
    writeCommand(INVERT_COLORS ? 0x21 : 0x20);
    writeCommand(0x13); // Normal display mode
    delay(20);
    writeCommand(0x29); // Display on
    delay(120);

    fillScreenRaw(C_BG);
    Serial.println("[FACE240_RAW] ST7789 raw init done");
}

static bool inHorizontalCapsule(int16_t px, int16_t py, int16_t x, int16_t y, int16_t w, int16_t h) {
    if (w <= 0 || h <= 0) {
        return false;
    }
    const int16_t r = h / 2;
    if (px >= x + r && px < x + w - r && py >= y && py < y + h) {
        return true;
    }
    const int16_t cy = y + r;
    const int16_t lcx = x + r;
    const int16_t rcx = x + w - r - 1;
    const int32_t ldx = px - lcx;
    const int32_t rdx = px - rcx;
    const int32_t dy = py - cy;
    return (ldx * ldx + dy * dy <= r * r) || (rdx * rdx + dy * dy <= r * r);
}

static bool inVerticalCapsule(int16_t px, int16_t py, int16_t x, int16_t y, int16_t w, int16_t h) {
    if (w <= 0 || h <= 0) {
        return false;
    }
    const int16_t r = w / 2;
    if (px >= x && px < x + w && py >= y + r && py < y + h - r) {
        return true;
    }
    const int16_t cx = x + r;
    const int16_t tcy = y + r;
    const int16_t bcy = y + h - r - 1;
    const int32_t dx = px - cx;
    const int32_t tdy = py - tcy;
    const int32_t bdy = py - bcy;
    return (dx * dx + tdy * tdy <= r * r) || (dx * dx + bdy * bdy <= r * r);
}

static bool inPill(int16_t px, int16_t py, int16_t cx, int16_t y, int16_t w, int16_t h) {
    return inVerticalCapsule(px, py, cx - w / 2, y, w, h);
}

static bool nearRingArc(int16_t px, int16_t py, int16_t cx, int16_t cy,
                        int16_t radius, int16_t stroke, bool lowerHalf) {
    if (lowerHalf && py < cy) {
        return false;
    }
    if (!lowerHalf && py > cy) {
        return false;
    }
    const int32_t dx = px - cx;
    const int32_t dy = py - cy;
    const int32_t d2 = dx * dx + dy * dy;
    const int32_t r2 = static_cast<int32_t>(radius) * radius;
    return abs(d2 - r2) <= static_cast<int32_t>(radius) * stroke;
}

static bool nearLineSegment(int16_t px, int16_t py, int16_t x0, int16_t y0,
                            int16_t x1, int16_t y1, int16_t thickness) {
    const int64_t dx = x1 - x0;
    const int64_t dy = y1 - y0;
    const int64_t len2 = dx * dx + dy * dy;
    if (len2 == 0) {
        return false;
    }

    int64_t t = ((px - x0) * dx + (py - y0) * dy) * 1024 / len2;
    if (t < 0) {
        t = 0;
    } else if (t > 1024) {
        t = 1024;
    }
    const int64_t cx = static_cast<int64_t>(x0) * 1024 + dx * t;
    const int64_t cy = static_cast<int64_t>(y0) * 1024 + dy * t;
    const int64_t ex = static_cast<int64_t>(px) * 1024 - cx;
    const int64_t ey = static_cast<int64_t>(py) * 1024 - cy;
    const int64_t limit = static_cast<int64_t>(thickness) * 512;
    return ex * ex + ey * ey <= limit * limit;
}

static bool inFourPointStar(int16_t px, int16_t py, int16_t cx, int16_t cy, int16_t r) {
    const int16_t dx = abs(px - cx);
    const int16_t dy = abs(py - cy);
    return (dx + dy <= r && (dx <= 5 || dy <= 5)) ||
           (dx + dy <= r / 2 + 3);
}

static float easeToward(float current, float target, float amount) {
    return current + (target - current) * amount;
}

static float blinkScale(uint32_t now) {
    if (!blinking && now >= nextBlinkMs) {
        blinking = true;
        blinkStartMs = now;
    }
    if (!blinking) {
        return 1.0f;
    }

    const uint32_t elapsed = now - blinkStartMs;
    if (elapsed >= 190) {
        blinking = false;
        nextBlinkMs = now + random(1500, 4200);
        return 1.0f;
    }
    if (elapsed < 95) {
        return 1.0f - (elapsed / 95.0f) * 0.88f;
    }
    return 0.12f + ((elapsed - 95) / 95.0f) * 0.88f;
}

static void updateIdleGaze(uint32_t now) {
    if (now < nextGazeMs) {
        return;
    }

    const int8_t choices[][2] = {
        {0, 0}, {-10, -4}, {12, -3}, {-8, 5}, {10, 5}, {0, -6}
    };
    const uint8_t idx = random(0, sizeof(choices) / sizeof(choices[0]));
    targetGazeX = choices[idx][0];
    targetGazeY = choices[idx][1];
    nextGazeMs = now + random(850, 2100);
}

static FaceStyle animatedStyle(uint32_t now) {
    FaceStyle style = FACE_STYLES[currentExpression];
    const uint32_t frameTime = now - expressionStartMs;
    const float phase = frameTime / 1000.0f;
    const float breathe = sinf(phase * 2.6f) * 2.0f;

    updateIdleGaze(now);
    gazeX = easeToward(gazeX, targetGazeX, 0.18f);
    gazeY = easeToward(gazeY, targetGazeY, 0.18f);

    float targetEyeW = style.eyeW;
    float targetEyeH = style.eyeH;
    float targetEyeY = style.eyeY + breathe;
    float targetGap = style.eyeGap;
    float targetMouthY = style.mouthY + breathe * 0.7f;

    if (style.eyeType == EYE_PILL || style.eyeType == EYE_THINKING || currentExpression == FACE_SPEAKING) {
        targetEyeH *= blinkScale(now);
        targetEyeY += (style.eyeH - targetEyeH) * 0.48f;
    }

    if (currentExpression == FACE_HAPPY) {
        targetEyeY += sinf(phase * 6.0f) * 1.5f;
        targetMouthY += sinf(phase * 5.5f) * 1.0f;
    } else if (currentExpression == FACE_SPEAKING) {
        targetEyeW += sinf(phase * 8.0f) * 1.2f;
        targetMouthY += sinf(phase * 9.0f) * 1.8f;
    } else if (currentExpression == FACE_ERROR) {
        targetEyeY += ((frameTime / 90) % 2 == 0) ? -2 : 2;
        targetGap += ((frameTime / 130) % 2 == 0) ? 3 : -2;
    } else if (currentExpression == FACE_SLEEP) {
        targetEyeY += sinf(phase * 1.2f) * 2.2f;
    }

    animEyeW = easeToward(animEyeW, targetEyeW, 0.24f);
    animEyeH = easeToward(animEyeH, max<float>(5, targetEyeH), 0.32f);
    animEyeY = easeToward(animEyeY, targetEyeY, 0.26f);
    animEyeGap = easeToward(animEyeGap, targetGap, 0.22f);
    animMouthY = easeToward(animMouthY, targetMouthY, 0.28f);

    style.eyeW = static_cast<int16_t>(animEyeW);
    style.eyeH = static_cast<int16_t>(animEyeH);
    style.eyeY = static_cast<int16_t>(animEyeY);
    style.eyeGap = static_cast<int16_t>(animEyeGap);
    style.mouthY = static_cast<int16_t>(animMouthY);
    return style;
}

static bool inEye(const FaceStyle &style, int16_t px, int16_t py, bool glowLayer, bool coreLayer) {
    const int16_t totalW = style.eyeW * 2 + style.eyeGap;
    const int16_t leftCx = (TFT_W - totalW) / 2 + style.eyeW / 2 + static_cast<int16_t>(gazeX);
    const int16_t rightCx = leftCx + style.eyeW + style.eyeGap;
    const int16_t y = style.eyeY + static_cast<int16_t>(gazeY);
    const int16_t grow = glowLayer ? 8 : 0;
    const int16_t shrink = coreLayer ? 4 : 0;

    switch (style.eyeType) {
        case EYE_PILL:
            return inPill(px, py, leftCx, y - grow + shrink, style.eyeW + grow * 2 - shrink * 2, style.eyeH + grow * 2 - shrink) ||
                   inPill(px, py, rightCx, y - grow + shrink, style.eyeW + grow * 2 - shrink * 2, style.eyeH + grow * 2 - shrink);

        case EYE_HAPPY_ARC:
            return nearRingArc(px, py, leftCx, y + 36, 28, glowLayer ? 20 : (coreLayer ? 7 : 12), false) ||
                   nearRingArc(px, py, rightCx, y + 36, 28, glowLayer ? 20 : (coreLayer ? 7 : 12), false);

        case EYE_ANGRY: {
            const bool eyes = inPill(px, py, leftCx, y + 7 - grow + shrink, style.eyeW + grow * 2 - shrink * 2, style.eyeH + grow * 2 - shrink) ||
                              inPill(px, py, rightCx, y + 7 - grow + shrink, style.eyeW + grow * 2 - shrink * 2, style.eyeH + grow * 2 - shrink);
            const int16_t lineW = glowLayer ? 13 : (coreLayer ? 5 : 8);
            const bool brows = nearLineSegment(px, py, leftCx - 30, y - 2, leftCx + 28, y + 16, lineW) ||
                               nearLineSegment(px, py, rightCx + 30, y - 2, rightCx - 28, y + 16, lineW);
            return eyes || brows;
        }

        case EYE_TIRED: {
            const bool lowerPill = (inPill(px, py, leftCx, y + 11 - grow, style.eyeW + grow * 2, style.eyeH + grow) ||
                                    inPill(px, py, rightCx, y + 11 - grow, style.eyeW + grow * 2, style.eyeH + grow)) &&
                                   py > y + 20;
            const int16_t lineW = glowLayer ? 12 : (coreLayer ? 4 : 7);
            const bool lids = nearLineSegment(px, py, leftCx - 34, y + 10, leftCx + 34, y + 8, lineW) ||
                              nearLineSegment(px, py, rightCx - 34, y + 8, rightCx + 34, y + 10, lineW);
            return lowerPill || lids;
        }

        case EYE_THINKING: {
            const bool left = inPill(px, py, leftCx, y - grow + shrink, style.eyeW + grow * 2 - shrink * 2, style.eyeH + grow * 2 - shrink);
            const int16_t rw = max<int16_t>(22, style.eyeW - 10);
            const int16_t rh = max<int16_t>(38, style.eyeH - 8);
            const bool right = inPill(px, py, rightCx + 3, y - 3 - grow + shrink, rw + grow * 2 - shrink * 2, rh + grow * 2 - shrink);
            bool cut = false;
            if (currentExpression == FACE_ERROR) {
                cut = (px >= rightCx - 2 && px <= rightCx + 13 && py >= y + 12 && py <= y + 20) ||
                      (px >= rightCx + 9 && px <= rightCx + 21 && py >= y + 31 && py <= y + 38);
            }
            return (left || right) && !cut;
        }

        case EYE_SLEEP_ARC:
            return nearRingArc(px, py, leftCx, y + 28, 32, glowLayer ? 18 : (coreLayer ? 6 : 9), true) ||
                   nearRingArc(px, py, rightCx, y + 28, 32, glowLayer ? 18 : (coreLayer ? 6 : 9), true);
    }
    return false;
}

static bool inMouth(const FaceStyle &style, int16_t px, int16_t py, uint32_t frameTime,
                    bool glowLayer, bool coreLayer) {
    const int16_t y = style.mouthY;
    const int16_t lineW = glowLayer ? 13 : (coreLayer ? 5 : 8);
    switch (style.mouthType) {
        case MOUTH_SMALL_SMILE:
            return nearRingArc(px, py, 160, y - 12, 18, lineW, true);
        case MOUTH_SMILE:
            return nearRingArc(px, py, 160, y - 18, 24, lineW, true);
        case MOUTH_FLAT:
            return nearLineSegment(px, py, 144, y, 176, y, lineW);
        case MOUTH_O: {
            const int32_t dx = px - 160;
            const int32_t dy = py - y;
            const int32_t d2 = dx * dx + dy * dy;
            const int16_t outer = glowLayer ? 20 : 15;
            const int16_t inner = coreLayer ? 9 : 7;
            return d2 <= outer * outer && d2 >= inner * inner;
        }
        case MOUTH_WAVE: {
            const int16_t amp = 8 + ((frameTime / 100) % 4) * 3;
            int16_t lastX = 124;
            int16_t lastY = y;
            for (int16_t x = 132; x <= 196; x += 8) {
                const int16_t idx = (x - 124) / 8;
                const int16_t yy = y + ((idx % 2 == 0) ? -amp : amp);
                if (nearLineSegment(px, py, lastX, lastY, x, yy, lineW)) {
                    return true;
                }
                lastX = x;
                lastY = yy;
            }
            return false;
        }
        case MOUTH_ERROR_WAVE: {
            int16_t lastX = 136;
            int16_t lastY = y;
            for (int16_t x = 144; x <= 184; x += 8) {
                const int16_t yy = y + (((x / 8 + frameTime / 130) % 2 == 0) ? -4 : 4);
                if (nearLineSegment(px, py, lastX, lastY, x, yy, lineW)) {
                    return true;
                }
                lastX = x;
                lastY = yy;
            }
            return false;
        }
        case MOUTH_SLEEP:
            return nearLineSegment(px, py, 150, y, 170, y, lineW);
    }
    return false;
}

static bool inExtraEffect(int16_t px, int16_t py, uint32_t frameTime, bool coreLayer) {
    if (currentExpression == FACE_THINKING) {
        const int16_t dx = px - 216;
        const int16_t dy = py - 68;
        const int16_t r = coreLayer ? 7 : 12;
        return dx * dx + dy * dy <= r * r;
    }
    if (currentExpression == FACE_ERROR) {
        const int16_t shift = (frameTime / 120) % 3;
        const int16_t w = coreLayer ? 3 : 7;
        return nearLineSegment(px, py, 66, 64 + shift, 96, 64 + shift, w) ||
               nearLineSegment(px, py, 232, 53, 264, 53, w) ||
               nearLineSegment(px, py, 262, 75 + shift, 282, 75 + shift, w) ||
               nearLineSegment(px, py, 62, 176, 92, 176, w) ||
               nearLineSegment(px, py, 250, 174, 278, 174, w);
    }
    if (currentExpression == FACE_SLEEP && sleepStarEnabled) {
        return inFourPointStar(px, py, 242, 158, coreLayer ? 17 : 23);
    }
    return false;
}

static uint16_t pixelColorFor(int16_t px, int16_t py, const FaceStyle &style, uint32_t frameTime) {
    uint16_t color = C_BG;

    if (inEye(style, px, py, true, false) ||
        inMouth(style, px, py, frameTime, true, false) ||
        inExtraEffect(px, py, frameTime, false)) {
        color = C_CYAN_DIM;
    }
    if (inEye(style, px, py, false, false) ||
        inMouth(style, px, py, frameTime, false, false)) {
        color = C_CYAN_GLOW;
    }
    if (inEye(style, px, py, false, true) ||
        inMouth(style, px, py, frameTime, false, true) ||
        inExtraEffect(px, py, frameTime, true)) {
        color = (currentExpression == FACE_HAPPY || currentExpression == FACE_TIRED ||
                 currentExpression == FACE_ERROR || currentExpression == FACE_SLEEP)
                    ? C_WHITE_BLUE
                    : C_CYAN;
    }

    return color;
}

static int16_t rectRight(const DirtyRect &rect) {
    return rect.x + rect.w;
}

static int16_t rectBottom(const DirtyRect &rect) {
    return rect.y + rect.h;
}

static DirtyRect expandedRect(DirtyRect rect, int16_t pad) {
    rect.x -= pad;
    rect.y -= pad;
    rect.w += pad * 2;
    rect.h += pad * 2;
    return rect;
}

static bool clipToFace(DirtyRect &rect) {
    const int16_t x0 = max<int16_t>(rect.x, FACE_X0);
    const int16_t y0 = max<int16_t>(rect.y, FACE_Y0);
    const int16_t x1 = min<int16_t>(rectRight(rect), FACE_X0 + FACE_W);
    const int16_t y1 = min<int16_t>(rectBottom(rect), FACE_Y0 + FACE_H);
    rect.x = x0;
    rect.y = y0;
    rect.w = x1 - x0;
    rect.h = y1 - y0;
    return rect.w > 0 && rect.h > 0;
}

static bool rectsTouch(const DirtyRect &a, const DirtyRect &b) {
    return a.x <= rectRight(b) + 2 && rectRight(a) + 2 >= b.x &&
           a.y <= rectBottom(b) + 2 && rectBottom(a) + 2 >= b.y;
}

static DirtyRect unionRect(const DirtyRect &a, const DirtyRect &b) {
    const int16_t x0 = min<int16_t>(a.x, b.x);
    const int16_t y0 = min<int16_t>(a.y, b.y);
    const int16_t x1 = max<int16_t>(rectRight(a), rectRight(b));
    const int16_t y1 = max<int16_t>(rectBottom(a), rectBottom(b));
    return {x0, y0, static_cast<int16_t>(x1 - x0), static_cast<int16_t>(y1 - y0)};
}

static void markFullFaceRefresh() {
    fullFaceRefreshPending = true;
}

static void addDirtyRect(DirtyRect *dirtyRects, uint8_t &dirtyRectCount, DirtyRect rect) {
    if (!clipToFace(rect)) {
        return;
    }

    for (uint8_t i = 0; i < dirtyRectCount; ++i) {
        if (rectsTouch(dirtyRects[i], rect)) {
            dirtyRects[i] = unionRect(dirtyRects[i], rect);
            clipToFace(dirtyRects[i]);
            return;
        }
    }

    if (dirtyRectCount >= MAX_DIRTY_RECTS) {
        dirtyRectCount = 1;
        dirtyRects[0] = {FACE_X0, FACE_Y0, FACE_W, FACE_H};
        return;
    }

    dirtyRects[dirtyRectCount++] = rect;
}

static void addCenteredRect(DirtyRect *rects, uint8_t &count,
                            int16_t cx, int16_t cy, int16_t w, int16_t h) {
    addDirtyRect(rects, count, {static_cast<int16_t>(cx - w / 2),
                                static_cast<int16_t>(cy - h / 2),
                                w,
                                h});
}

static uint8_t buildDynamicRects(const FaceStyle &style, uint32_t frameTime, DirtyRect *rects) {
    uint8_t count = 0;
    const int16_t totalW = style.eyeW * 2 + style.eyeGap;
    const int16_t leftCx = (TFT_W - totalW) / 2 + style.eyeW / 2 + static_cast<int16_t>(gazeX);
    const int16_t rightCx = leftCx + style.eyeW + style.eyeGap;
    const int16_t eyeY = style.eyeY + static_cast<int16_t>(gazeY);

    int16_t eyeDirtyW = max<int16_t>(92, style.eyeW + 58);
    int16_t eyeDirtyH = max<int16_t>(92, style.eyeH + 54);
    int16_t eyeCenterY = eyeY + style.eyeH / 2;
    if (style.eyeType == EYE_HAPPY_ARC || style.eyeType == EYE_SLEEP_ARC || style.eyeType == EYE_TIRED) {
        eyeDirtyW = max<int16_t>(110, style.eyeW + 70);
        eyeDirtyH = 126;
        eyeCenterY = eyeY + 38;
    } else if (style.eyeType == EYE_ANGRY) {
        eyeDirtyW = max<int16_t>(112, style.eyeW + 74);
        eyeDirtyH = max<int16_t>(108, style.eyeH + 60);
        eyeCenterY = eyeY + 34;
    }
    addCenteredRect(rects, count, leftCx, eyeCenterY, eyeDirtyW, eyeDirtyH);
    addCenteredRect(rects, count, rightCx, eyeCenterY, eyeDirtyW, eyeDirtyH);

    int16_t mouthW = 118;
    int16_t mouthH = 82;
    if (style.mouthType == MOUTH_WAVE) {
        mouthW = 132;
        mouthH = 96;
    } else if (style.mouthType == MOUTH_O) {
        mouthW = 70;
        mouthH = 70;
    }
    addCenteredRect(rects, count, 160, style.mouthY, mouthW, mouthH);

    if (currentExpression == FACE_THINKING) {
        addCenteredRect(rects, count, 216, 68, 42, 42);
    } else if (currentExpression == FACE_ERROR) {
        const int16_t shift = (frameTime / 120) % 3;
        addDirtyRect(rects, count, expandedRect({58, static_cast<int16_t>(48 + shift), 232, 136}, 10));
    } else if (currentExpression == FACE_SLEEP && sleepStarEnabled) {
        addCenteredRect(rects, count, 242, 158, 64, 64);
    }

    return count;
}

static void drawRectRegion(DirtyRect rect, const FaceStyle &style, uint32_t frameTime) {
    if (!clipToFace(rect)) {
        return;
    }

    setAddressWindow(rect.x, rect.y, rect.x + rect.w - 1, rect.y + rect.h - 1);
    digitalWrite(TFT_DC, HIGH);
    selectDisplay();
    for (int16_t py = rect.y; py < rect.y + rect.h; ++py) {
        for (int16_t px = rect.x; px < rect.x + rect.w; ++px) {
            setLinePixel(px - rect.x, pixelColorFor(px, py, style, frameTime));
        }
        SPI.writeBytes(lineBuffer, rect.w * 2);
    }
    unselectDisplay();
    fpsPixelCount += static_cast<uint32_t>(rect.w) * rect.h;
}

static void drawDirtyFaceFrame(uint32_t now) {
    const FaceStyle style = animatedStyle(now);
    const uint32_t frameTime = now - expressionStartMs;
    DirtyRect dirtyRects[MAX_DIRTY_RECTS];
    uint8_t dirtyRectCount = 0;

    DirtyRect currentDynamicRects[MAX_DIRTY_RECTS];
    const uint8_t currentDynamicRectCount = buildDynamicRects(style, frameTime, currentDynamicRects);

    if (fullFaceRefreshPending) {
        addDirtyRect(dirtyRects, dirtyRectCount, {FACE_X0, FACE_Y0, FACE_W, FACE_H});
        fullFaceRefreshPending = false;
    } else {
        for (uint8_t i = 0; i < lastDynamicRectCount; ++i) {
            addDirtyRect(dirtyRects, dirtyRectCount, lastDynamicRects[i]);
        }
        for (uint8_t i = 0; i < currentDynamicRectCount; ++i) {
            addDirtyRect(dirtyRects, dirtyRectCount, currentDynamicRects[i]);
        }
    }

    for (uint8_t i = 0; i < dirtyRectCount; ++i) {
        drawRectRegion(dirtyRects[i], style, frameTime);
    }

    lastDynamicRectCount = currentDynamicRectCount;
    for (uint8_t i = 0; i < currentDynamicRectCount; ++i) {
        lastDynamicRects[i] = currentDynamicRects[i];
    }

    fpsFrameCount++;
    if (fpsWindowStartMs == 0) {
        fpsWindowStartMs = now;
    } else if (now - fpsWindowStartMs >= 2500) {
        Serial.printf("[FACE240_RAW] fps=%u avg_pixels=%lu rects=%u expr=%u\n",
                      static_cast<unsigned>(fpsFrameCount * 1000UL / (now - fpsWindowStartMs)),
                      fpsFrameCount ? fpsPixelCount / fpsFrameCount : 0,
                      static_cast<unsigned>(dirtyRectCount),
                      static_cast<unsigned>(currentExpression));
        fpsWindowStartMs = now;
        fpsFrameCount = 0;
        fpsPixelCount = 0;
    }
}

static void setExpression(FaceExpression expression) {
    currentExpression = expression;
    expressionStartMs = millis();
    nextGazeMs = expressionStartMs + 250;
    if (nextBlinkMs < expressionStartMs + 600) {
        nextBlinkMs = expressionStartMs + 600;
    }
    Serial.printf("[FACE240_RAW] expression=%u\n", static_cast<unsigned>(expression));
}

void setup() {
    Serial.begin(115200);
    waitForSerialWindow();
    Serial.println();
    Serial.println("[FACE240_RAW] 8-expression ST7789 robot face");
    Serial.println("[FACE240_RAW] Pins: SCLK=12 MOSI=11 CS=10 DC=9 RST=14 BL=21");

    initDisplayRaw();
    randomSeed(static_cast<uint32_t>(esp_random()));
    nextBlinkMs = millis() + 900;
    nextGazeMs = millis() + 300;
    setExpression(FACE_NORMAL);
}

void loop() {
    const uint32_t now = millis();
    if (now - lastFrameMs < FRAME_MS) {
        delay(1);
        return;
    }
    lastFrameMs = now;

    if (now - expressionStartMs > EXPRESSION_MS) {
        setExpression(static_cast<FaceExpression>((currentExpression + 1) % FACE_COUNT));
    }

    drawDirtyFaceFrame(now);
}
