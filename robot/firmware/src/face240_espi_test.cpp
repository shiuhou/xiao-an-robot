#include <Arduino.h>
#include <TFT_eSPI.h>

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

static constexpr int16_t SCREEN_W = 320;
static constexpr int16_t SCREEN_H = 240;
static constexpr uint32_t FRAME_MS = 33;
static constexpr uint32_t EXPRESSION_MS = 3200;
static constexpr int16_t EYE_CENTER_Y = 95;
static constexpr int16_t NORMAL_MOUTH_Y = 155;

static TFT_eSPI tft;
static TFT_eSprite face(&tft);

static uint16_t C_BG;
static uint16_t C_CYAN;
static uint16_t C_CYAN_DIM;
static uint16_t C_CYAN_DARK;
static uint16_t C_WHITE_BLUE;

static FaceExpression currentExpression = FACE_NORMAL;
static uint32_t lastFrameMs = 0;
static uint32_t expressionStartMs = 0;
static bool sleepStarEnabled = true;

static const FaceStyle FACE_STYLES[FACE_COUNT] = {
    {EYE_PILL,      MOUTH_SMALL_SMILE, 32, 60, EYE_CENTER_Y - 30, 72, NORMAL_MOUTH_Y,     false},
    {EYE_HAPPY_ARC, MOUTH_SMILE,       62, 40, EYE_CENTER_Y - 18, 64, NORMAL_MOUTH_Y + 2, true},
    {EYE_ANGRY,     MOUTH_FLAT,        42, 58, EYE_CENTER_Y - 29, 68, NORMAL_MOUTH_Y,     true},
    {EYE_TIRED,     MOUTH_FLAT,        66, 42, EYE_CENTER_Y - 15, 58, NORMAL_MOUTH_Y,     false},
    {EYE_THINKING,  MOUTH_O,           34, 60, EYE_CENTER_Y - 30, 70, NORMAL_MOUTH_Y + 4, true},
    {EYE_PILL,      MOUTH_WAVE,        34, 62, EYE_CENTER_Y - 31, 70, NORMAL_MOUTH_Y + 2, false},
    {EYE_THINKING,  MOUTH_ERROR_WAVE,  34, 62, EYE_CENTER_Y - 31, 72, NORMAL_MOUTH_Y + 3, true},
    {EYE_SLEEP_ARC, MOUTH_SLEEP,       72, 30, EYE_CENTER_Y - 8,  72, NORMAL_MOUTH_Y + 8, true},
};

static void setExpression(FaceExpression expression) {
    currentExpression = expression;
    expressionStartMs = millis();
}

static uint16_t mix565(uint16_t a, uint16_t b, uint8_t amountB) {
    const uint8_t amountA = 255 - amountB;
    const uint8_t ar = ((a >> 11) & 0x1F) << 3;
    const uint8_t ag = ((a >> 5) & 0x3F) << 2;
    const uint8_t ab = (a & 0x1F) << 3;
    const uint8_t br = ((b >> 11) & 0x1F) << 3;
    const uint8_t bg = ((b >> 5) & 0x3F) << 2;
    const uint8_t bb = (b & 0x1F) << 3;
    return tft.color565((ar * amountA + br * amountB) / 255,
                        (ag * amountA + bg * amountB) / 255,
                        (ab * amountA + bb * amountB) / 255);
}

static void drawThickLine(int16_t x0, int16_t y0, int16_t x1, int16_t y1, int16_t thickness, uint16_t color) {
    const int16_t dx = abs(x1 - x0);
    const int16_t sx = x0 < x1 ? 1 : -1;
    const int16_t dy = -abs(y1 - y0);
    const int16_t sy = y0 < y1 ? 1 : -1;
    int16_t err = dx + dy;
    const int16_t r = max<int16_t>(1, thickness / 2);

    while (true) {
        face.fillCircle(x0, y0, r, color);
        if (x0 == x1 && y0 == y1) {
            break;
        }
        const int16_t e2 = 2 * err;
        if (e2 >= dy) {
            err += dy;
            x0 += sx;
        }
        if (e2 <= dx) {
            err += dx;
            y0 += sy;
        }
    }
}

static void drawThickArc(int16_t cx, int16_t cy, int16_t radius, int16_t startDeg, int16_t endDeg, int16_t thickness, uint16_t color) {
    int16_t lastX = 0;
    int16_t lastY = 0;
    bool hasLast = false;
    for (int16_t deg = startDeg; deg <= endDeg; deg += 3) {
        const float rad = deg * DEG_TO_RAD;
        const int16_t x = cx + cosf(rad) * radius;
        const int16_t y = cy + sinf(rad) * radius;
        if (hasLast) {
            drawThickLine(lastX, lastY, x, y, thickness, color);
        }
        lastX = x;
        lastY = y;
        hasLast = true;
    }
}

static void drawGlowPill(int16_t cx, int16_t y, int16_t w, int16_t h, uint16_t coreColor) {
    for (int8_t i = 3; i >= 1; --i) {
        const uint16_t glow = i == 3 ? C_CYAN_DARK : (i == 2 ? C_CYAN_DIM : mix565(C_BG, C_CYAN, 90));
        face.fillRoundRect(cx - w / 2 - i * 5, y - i * 5, w + i * 10, h + i * 10,
                           (w + i * 10) / 2, glow);
    }
    face.fillRoundRect(cx - w / 2, y, w, h, w / 2, coreColor);
}

static void drawGlowArc(int16_t cx, int16_t cy, int16_t r, int16_t startDeg, int16_t endDeg, int16_t thickness, uint16_t coreColor) {
    drawThickArc(cx, cy, r, startDeg, endDeg, thickness + 12, C_CYAN_DARK);
    drawThickArc(cx, cy, r, startDeg, endDeg, thickness + 6, C_CYAN_DIM);
    drawThickArc(cx, cy, r, startDeg, endDeg, thickness, coreColor);
}

static void drawEyePair(const FaceStyle &style, uint32_t frameTime) {
    const int16_t totalW = style.eyeW * 2 + style.eyeGap;
    const int16_t leftCx = (SCREEN_W - totalW) / 2 + style.eyeW / 2;
    const int16_t rightCx = leftCx + style.eyeW + style.eyeGap;
    const int16_t y = style.eyeY;

    switch (style.eyeType) {
        case EYE_PILL:
            drawGlowPill(leftCx, y, style.eyeW, style.eyeH, C_CYAN);
            drawGlowPill(rightCx, y, style.eyeW, style.eyeH, C_CYAN);
            break;

        case EYE_HAPPY_ARC:
            drawGlowArc(leftCx, y + 36, 28, 205, 335, 10, C_WHITE_BLUE);
            drawGlowArc(rightCx, y + 36, 28, 205, 335, 10, C_WHITE_BLUE);
            break;

        case EYE_ANGRY:
            drawGlowPill(leftCx, y + 7, style.eyeW, style.eyeH, C_CYAN);
            drawGlowPill(rightCx, y + 7, style.eyeW, style.eyeH, C_CYAN);
            drawThickLine(leftCx - 30, y - 2, leftCx + 28, y + 16, 8, C_CYAN);
            drawThickLine(rightCx + 30, y - 2, rightCx - 28, y + 16, 8, C_CYAN);
            break;

        case EYE_TIRED:
            drawGlowPill(leftCx, y + 11, style.eyeW, style.eyeH, C_WHITE_BLUE);
            drawGlowPill(rightCx, y + 11, style.eyeW, style.eyeH, C_WHITE_BLUE);
            face.fillRect(leftCx - style.eyeW / 2 - 10, y - 2, style.eyeW + 20, 26, C_BG);
            face.fillRect(rightCx - style.eyeW / 2 - 10, y - 2, style.eyeW + 20, 26, C_BG);
            drawThickLine(leftCx - 34, y + 10, leftCx + 34, y + 8, 5, C_WHITE_BLUE);
            drawThickLine(rightCx - 34, y + 8, rightCx + 34, y + 10, 5, C_WHITE_BLUE);
            break;

        case EYE_THINKING:
            drawGlowPill(leftCx, y, style.eyeW, style.eyeH, C_CYAN);
            drawGlowPill(rightCx + 3, y - 3, max<int16_t>(22, style.eyeW - 10), max<int16_t>(38, style.eyeH - 8),
                         currentExpression == FACE_ERROR ? C_WHITE_BLUE : C_WHITE_BLUE);
            if (currentExpression == FACE_ERROR) {
                face.fillRect(rightCx - 2, y + 12, 15, 8, C_BG);
                face.fillRect(rightCx + 9, y + 31, 12, 7, C_BG);
            }
            break;

        case EYE_SLEEP_ARC:
            drawGlowArc(leftCx, y + 28, 32, 25, 155, 7, C_WHITE_BLUE);
            drawGlowArc(rightCx, y + 28, 32, 25, 155, 7, C_WHITE_BLUE);
            break;
    }

    if (currentExpression == FACE_SPEAKING && ((frameTime / 160) % 2 == 0)) {
        face.fillCircle(leftCx - 46, y + 44, 4, C_CYAN);
        face.fillCircle(rightCx + 46, y + 44, 4, C_CYAN);
    }
}

static void drawMouth(const FaceStyle &style, uint32_t frameTime) {
    const int16_t cy = style.mouthY;
    switch (style.mouthType) {
        case MOUTH_SMALL_SMILE:
            drawGlowArc(160, cy - 12, 18, 45, 135, 5, C_CYAN);
            break;
        case MOUTH_SMILE:
            drawGlowArc(160, cy - 18, 24, 35, 145, 7, C_CYAN);
            break;
        case MOUTH_FLAT:
            drawThickLine(144, cy, 176, cy, 7, C_CYAN);
            break;
        case MOUTH_O:
            face.fillCircle(160, cy, 15, C_CYAN_DIM);
            face.fillCircle(160, cy, 9, C_BG);
            break;
        case MOUTH_WAVE: {
            const int16_t amp = 8 + (frameTime / 100) % 4 * 3;
            int16_t lastX = 124;
            int16_t lastY = cy;
            for (int16_t x = 132; x <= 196; x += 8) {
                const int16_t idx = (x - 124) / 8;
                const int16_t y = cy + ((idx % 2 == 0) ? -amp : amp);
                drawThickLine(lastX, lastY, x, y, 5, C_CYAN);
                lastX = x;
                lastY = y;
            }
            break;
        }
        case MOUTH_ERROR_WAVE: {
            int16_t lastX = 136;
            int16_t lastY = cy;
            for (int16_t x = 144; x <= 184; x += 8) {
                const int16_t y = cy + (((x / 8 + frameTime / 130) % 2 == 0) ? -4 : 4);
                drawThickLine(lastX, lastY, x, y, 4, C_WHITE_BLUE);
                lastX = x;
                lastY = y;
            }
            break;
        }
        case MOUTH_SLEEP:
            drawThickLine(150, cy, 170, cy, 7, C_CYAN);
            break;
    }
}

static void drawStar(int16_t cx, int16_t cy, int16_t r, uint16_t color) {
    face.fillTriangle(cx, cy - r, cx - 5, cy - 4, cx + 5, cy - 4, color);
    face.fillTriangle(cx, cy + r, cx - 5, cy + 4, cx + 5, cy + 4, color);
    face.fillTriangle(cx - r, cy, cx - 4, cy - 5, cx - 4, cy + 5, color);
    face.fillTriangle(cx + r, cy, cx + 4, cy - 5, cx + 4, cy + 5, color);
}

static void drawExtraEffects(const FaceStyle &style, uint32_t frameTime) {
    if (!style.extraEffect) {
        return;
    }

    if (currentExpression == FACE_THINKING) {
        face.fillCircle(216, 68, 7, C_CYAN);
    } else if (currentExpression == FACE_ERROR) {
        const int16_t shift = (frameTime / 120) % 3;
        drawThickLine(66, 64 + shift, 96, 64 + shift, 3, C_CYAN_DIM);
        drawThickLine(232, 53, 264, 53, 3, C_CYAN);
        drawThickLine(262, 75 + shift, 282, 75 + shift, 2, C_WHITE_BLUE);
        drawThickLine(62, 176, 92, 176, 3, C_CYAN);
        drawThickLine(250, 174, 278, 174, 2, C_CYAN_DIM);
    } else if (currentExpression == FACE_SLEEP && sleepStarEnabled) {
        drawStar(242, 158, 18, C_WHITE_BLUE);
    }
}

static void drawFaceFrame(uint32_t now) {
    const FaceStyle &style = FACE_STYLES[currentExpression];
    const uint32_t frameTime = now - expressionStartMs;
    face.fillSprite(C_BG);
    drawEyePair(style, frameTime);
    drawMouth(style, frameTime);
    drawExtraEffects(style, frameTime);
    face.pushSprite(0, 0);
}

static void runPanelSelfTest() {
    Serial.println("[FACE240_ESPI] Panel self-test: red green blue black");
    tft.fillScreen(TFT_RED);
    delay(250);
    tft.fillScreen(TFT_GREEN);
    delay(250);
    tft.fillScreen(TFT_BLUE);
    delay(250);
    tft.fillScreen(TFT_BLACK);
    delay(250);
}

void setup() {
    Serial.begin(115200);
    delay(300);
    Serial.println();
    Serial.println("[FACE240_ESPI] ST7789 TFT_eSPI sprite face test");

    tft.init();
    tft.setRotation(1);
    tft.invertDisplay(false);
    runPanelSelfTest();
    tft.fillScreen(TFT_BLACK);

    C_BG = tft.color565(0, 0, 0);
    C_CYAN = tft.color565(70, 255, 245);
    C_CYAN_DIM = tft.color565(0, 105, 120);
    C_CYAN_DARK = tft.color565(0, 34, 48);
    C_WHITE_BLUE = tft.color565(190, 242, 255);

    face.setColorDepth(16);
    if (face.createSprite(SCREEN_W, SCREEN_H) == nullptr) {
        Serial.println("[FACE240_ESPI] Sprite allocation failed");
        tft.fillScreen(TFT_RED);
        while (true) {
            delay(1000);
        }
    }

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
        Serial.printf("[FACE240_ESPI] expression=%u\n", static_cast<unsigned>(currentExpression));
    }

    drawFaceFrame(now);
}
