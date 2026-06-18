#include <Arduino.h>
#include <SPI.h>

#include "monthly_salary_meow_frames.h"

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

static constexpr int TFT_W = 128;
static constexpr int TFT_H = 160;
static constexpr uint32_t SERIAL_WAIT_MS = 3000;
static constexpr uint32_t PRE_TFT_DIAG_MS = 3000;
static constexpr uint32_t SPI_HZ = 8000000;
static constexpr uint8_t MADCTL_RGB_ORDER = 0x00; // RGB order.
static constexpr bool INVERT_COLORS = false;

static constexpr uint16_t BLACK = 0x0000;
static constexpr uint16_t BLUE = 0x001F;
static constexpr uint16_t RED = 0xF800;
static constexpr uint16_t GREEN = 0x07E0;
static constexpr uint16_t CYAN = 0x07FF;
static constexpr uint16_t YELLOW = 0xFFE0;
static constexpr uint16_t WHITE = 0xFFFF;
static constexpr uint16_t ORANGE = 0xFD20;
static constexpr uint16_t PINK = 0xF81F;
static constexpr uint16_t DARK_NAVY = 0x0007;
static constexpr uint16_t MOON = 0xFFF6;
static constexpr uint16_t CAT = 0xBDF7;
static constexpr uint16_t CAT_SHADOW = 0x8410;

static void waitForSerialWindow() {
    const uint32_t start = millis();
    while (!Serial && millis() - start < SERIAL_WAIT_MS) {
        delay(10);
    }
}

static void runPreTftDiagnostics() {
    pinMode(TFT_BL, OUTPUT);

    const uint32_t start = millis();
    uint32_t lastPrint = 0;
    bool backlightOn = false;

    while (millis() - start < PRE_TFT_DIAG_MS) {
        const uint32_t now = millis();
        if (now - lastPrint >= 500) {
            lastPrint = now;
            backlightOn = !backlightOn;
            digitalWrite(TFT_BL, backlightOn ? TFT_BACKLIGHT_ON : !TFT_BACKLIGHT_ON);
            Serial.printf("[TFT] pre-init heartbeat uptime=%lu ms bl=%d\n",
                          static_cast<unsigned long>(now),
                          backlightOn ? 1 : 0);
        }
        delay(10);
    }

    digitalWrite(TFT_BL, TFT_BACKLIGHT_ON);
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

static void writeData16(uint16_t data) {
    digitalWrite(TFT_DC, HIGH);
    SPI.transfer(data >> 8);
    SPI.transfer(data & 0xFF);
}

static void setAddressWindow(uint8_t x0, uint8_t y0, uint8_t x1, uint8_t y1) {
    writeCommand(0x2A);
    digitalWrite(TFT_DC, HIGH);
    selectDisplay();
    writeData16(x0);
    writeData16(x1);
    unselectDisplay();

    writeCommand(0x2B);
    digitalWrite(TFT_DC, HIGH);
    selectDisplay();
    writeData16(y0);
    writeData16(y1);
    unselectDisplay();

    writeCommand(0x2C);
}

static void fillRect(int x, int y, int w, int h, uint16_t color) {
    if (x < 0 || y < 0 || w <= 0 || h <= 0 || x >= TFT_W || y >= TFT_H) {
        return;
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
    for (int32_t i = 0; i < static_cast<int32_t>(w) * h; ++i) {
        writeData16(color);
    }
    unselectDisplay();
}

static void drawPixelSafe(int x, int y, uint16_t color) {
    fillRect(x, y, 1, 1, color);
}

static void fillScreen(uint16_t color) {
    fillRect(0, 0, TFT_W, TFT_H, color);
}

static void drawCircle(int cx, int cy, int radius, uint16_t color) {
    for (int y = -radius; y <= radius; ++y) {
        for (int x = -radius; x <= radius; ++x) {
            if (x * x + y * y <= radius * radius) {
                drawPixelSafe(cx + x, cy + y, color);
            }
        }
    }
}

static void drawLine(int x0, int y0, int x1, int y1, uint16_t color, int thickness = 1) {
    const int dx = abs(x1 - x0);
    const int sx = x0 < x1 ? 1 : -1;
    const int dy = -abs(y1 - y0);
    const int sy = y0 < y1 ? 1 : -1;
    int err = dx + dy;

    while (true) {
        fillRect(x0 - thickness / 2, y0 - thickness / 2, thickness, thickness, color);
        if (x0 == x1 && y0 == y1) {
            break;
        }
        const int e2 = 2 * err;
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

static const uint8_t *glyphFor(char c) {
    static const uint8_t blank[5] = {0, 0, 0, 0, 0};
    static const uint8_t dash[5] = {0x08, 0x08, 0x08, 0x08, 0x08};
    static const uint8_t glyphs[][5] = {
        {0x7C, 0x12, 0x11, 0x12, 0x7C}, // A
        {0x7F, 0x49, 0x49, 0x49, 0x36}, // B
        {0x3E, 0x41, 0x41, 0x41, 0x22}, // C
        {0x7F, 0x41, 0x41, 0x22, 0x1C}, // D
        {0x7F, 0x49, 0x49, 0x49, 0x41}, // E
        {0x7F, 0x09, 0x09, 0x09, 0x01}, // F
        {0x3E, 0x41, 0x49, 0x49, 0x7A}, // G
        {0x7F, 0x08, 0x08, 0x08, 0x7F}, // H
        {0x00, 0x41, 0x7F, 0x41, 0x00}, // I
        {0x20, 0x40, 0x41, 0x3F, 0x01}, // J
        {0x7F, 0x08, 0x14, 0x22, 0x41}, // K
        {0x7F, 0x40, 0x40, 0x40, 0x40}, // L
        {0x7F, 0x02, 0x0C, 0x02, 0x7F}, // M
        {0x7F, 0x04, 0x08, 0x10, 0x7F}, // N
        {0x3E, 0x41, 0x41, 0x41, 0x3E}, // O
        {0x7F, 0x09, 0x09, 0x09, 0x06}, // P
        {0x3E, 0x41, 0x51, 0x21, 0x5E}, // Q
        {0x7F, 0x09, 0x19, 0x29, 0x46}, // R
        {0x46, 0x49, 0x49, 0x49, 0x31}, // S
        {0x01, 0x01, 0x7F, 0x01, 0x01}, // T
        {0x3F, 0x40, 0x40, 0x40, 0x3F}, // U
        {0x1F, 0x20, 0x40, 0x20, 0x1F}, // V
        {0x7F, 0x20, 0x18, 0x20, 0x7F}, // W
        {0x63, 0x14, 0x08, 0x14, 0x63}, // X
        {0x07, 0x08, 0x70, 0x08, 0x07}, // Y
        {0x61, 0x51, 0x49, 0x45, 0x43}, // Z
    };
    static const uint8_t nums[][5] = {
        {0x3E, 0x51, 0x49, 0x45, 0x3E}, // 0
        {0x00, 0x42, 0x7F, 0x40, 0x00}, // 1
        {0x42, 0x61, 0x51, 0x49, 0x46}, // 2
        {0x21, 0x41, 0x45, 0x4B, 0x31}, // 3
        {0x18, 0x14, 0x12, 0x7F, 0x10}, // 4
        {0x27, 0x45, 0x45, 0x45, 0x39}, // 5
        {0x3C, 0x4A, 0x49, 0x49, 0x30}, // 6
        {0x01, 0x71, 0x09, 0x05, 0x03}, // 7
        {0x36, 0x49, 0x49, 0x49, 0x36}, // 8
        {0x06, 0x49, 0x49, 0x29, 0x1E}, // 9
    };

    if (c == ' ') {
        return blank;
    }
    if (c == '-') {
        return dash;
    }
    if (c >= 'a' && c <= 'z') {
        c = c - 'a' + 'A';
    }
    if (c >= 'A' && c <= 'Z') {
        return glyphs[c - 'A'];
    }
    if (c >= '0' && c <= '9') {
        return nums[c - '0'];
    }
    return blank;
}

static void drawChar(int x, int y, char c, uint16_t fg, uint16_t bg, int scale) {
    const uint8_t *glyph = glyphFor(c);
    for (int col = 0; col < 5; ++col) {
        for (int row = 0; row < 7; ++row) {
            const bool on = glyph[col] & (1 << row);
            fillRect(x + col * scale, y + row * scale, scale, scale, on ? fg : bg);
        }
    }
}

static void drawText(int x, int y, const char *text, uint16_t fg, uint16_t bg, int scale) {
    while (*text) {
        drawChar(x, y, *text, fg, bg, scale);
        x += 6 * scale;
        ++text;
    }
}

static void initDisplayRaw() {
    Serial.println("[TFT] Raw ST7735 init start");

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
    delay(20);
    digitalWrite(TFT_RST, HIGH);
    delay(120);

    writeCommand(0x01); // Software reset
    delay(150);
    writeCommand(0x11); // Sleep out
    delay(150);
    writeCommand(0x3A); // RGB565
    writeData8(0x05);
    writeCommand(0x36); // Memory access control
    writeData8(MADCTL_RGB_ORDER);
    writeCommand(INVERT_COLORS ? 0x21 : 0x20); // Display inversion on/off
    writeCommand(0x13); // Normal display mode
    delay(10);
    writeCommand(0x29); // Display on
    delay(100);

    Serial.println("[TFT] Raw ST7735 init done");
}

static void showTextPage() {
    fillScreen(BLACK);
    fillRect(0, 0, TFT_W, 1, WHITE);
    fillRect(0, TFT_H - 1, TFT_W, 1, WHITE);
    fillRect(0, 0, 1, TFT_H, WHITE);
    fillRect(TFT_W - 1, 0, 1, TFT_H, WHITE);
    drawText(22, 22, "XIAO-AN", CYAN, BLACK, 2);
    drawText(28, 54, "TFT OK", GREEN, BLACK, 2);
    drawText(20, 86, "128 X 160", YELLOW, BLACK, 1);
    drawText(34, 112, "ST7735", ORANGE, BLACK, 2);
    Serial.println("[TFT] Text page");
}

static void showColorBars() {
    fillRect(0, 0, 32, TFT_H, RED);
    fillRect(32, 0, 32, TFT_H, GREEN);
    fillRect(64, 0, 32, TFT_H, BLUE);
    fillRect(96, 0, 32, TFT_H, WHITE);
    drawText(24, 74, "BARS", BLACK, WHITE, 2);
    Serial.println("[TFT] Color bars");
}

static void drawDanceBackground(uint16_t accent) {
    fillScreen(DARK_NAVY);
    drawCircle(18, 18, 11, MOON);
    drawCircle(22, 15, 11, DARK_NAVY);
    fillRect(0, 129, TFT_W, 31, BLACK);
    fillRect(0, 126, TFT_W, 3, accent);

    for (int x = 10; x < TFT_W; x += 24) {
        fillRect(x, 136, 9, 2, CAT_SHADOW);
    }

    drawText(20, 6, "MOON CAT", WHITE, DARK_NAVY, 1);
}

static void drawCatFrame(int frame) {
    const int sway = frame == 1 ? -5 : frame == 3 ? 5 : 0;
    const int bounce = frame == 0 || frame == 2 ? 0 : -4;
    const int cx = 64 + sway;
    const int headY = 47 + bounce;
    const int bodyY = 78 + bounce;

    const int leftArmUp = frame == 0 || frame == 1;
    const int rightArmUp = frame == 0 || frame == 3;
    const int leftLegOut = frame == 1 || frame == 2;
    const int rightLegOut = frame == 2 || frame == 3;

    drawCircle(cx, headY, 18, CAT);
    fillRect(cx - 15, headY - 23, 9, 13, CAT);
    fillRect(cx + 6, headY - 23, 9, 13, CAT);
    fillRect(cx - 12, headY - 20, 4, 6, PINK);
    fillRect(cx + 8, headY - 20, 4, 6, PINK);

    drawCircle(cx - 7, headY - 3, 2, BLACK);
    drawCircle(cx + 7, headY - 3, 2, BLACK);
    drawLine(cx - 4, headY + 5, cx, headY + 8, BLACK, 1);
    drawLine(cx + 4, headY + 5, cx, headY + 8, BLACK, 1);
    drawLine(cx - 13, headY + 3, cx - 24, headY, CAT, 1);
    drawLine(cx + 13, headY + 3, cx + 24, headY, CAT, 1);

    fillRect(cx - 16, bodyY - 12, 32, 32, CAT);
    fillRect(cx - 10, bodyY - 4, 20, 5, WHITE);
    drawText(cx - 9, bodyY + 5, "PAY", BLACK, CAT, 1);

    drawLine(cx - 14, bodyY - 5,
             cx - 34, bodyY + (leftArmUp ? -24 : 8),
             CAT, 5);
    drawLine(cx + 14, bodyY - 5,
             cx + 34, bodyY + (rightArmUp ? -24 : 8),
             CAT, 5);
    drawCircle(cx - 34, bodyY + (leftArmUp ? -24 : 8), 4, CAT);
    drawCircle(cx + 34, bodyY + (rightArmUp ? -24 : 8), 4, CAT);

    drawLine(cx - 9, bodyY + 20,
             cx - (leftLegOut ? 24 : 8), bodyY + 43,
             CAT, 5);
    drawLine(cx + 9, bodyY + 20,
             cx + (rightLegOut ? 24 : 8), bodyY + 43,
             CAT, 5);

    const int tailDir = frame < 2 ? 1 : -1;
    drawLine(cx + 15, bodyY + 8, cx + 32 * tailDir, bodyY + 2, CAT, 4);
    drawLine(cx + 32 * tailDir, bodyY + 2, cx + 38 * tailDir, bodyY - 12, CAT, 4);
}

static void showMoonSalaryCatDance() {
    const uint16_t accents[] = {CYAN, PINK, YELLOW, GREEN};

    for (uint8_t i = 0; i < 24; ++i) {
        const uint8_t frame = i % 4;
        drawDanceBackground(accents[frame]);
        drawCatFrame(frame);
        drawText(19, 143, "SALARY CAT", WHITE, BLACK, 1);
        Serial.printf("[TFT] Moon salary cat dance frame=%u uptime=%lu ms\n",
                      frame,
                      static_cast<unsigned long>(millis()));
        delay(180);
    }
}

static bool meowFramePixelOn(const uint8_t *frame, int x, int y) {
    const uint16_t byteIndex = (y / 8) * GIF_FW + x;
    return (frame[byteIndex] & (1 << (y % 8))) != 0;
}

static void drawMeowFrame2x(const uint8_t *frame, int dstX, int dstY, uint16_t fg, uint16_t bg) {
    static constexpr int SCALE = 2;
    static constexpr int DRAW_W = GIF_FW * SCALE;
    static constexpr int DRAW_H = GIF_FH * SCALE;

    setAddressWindow(dstX, dstY, dstX + DRAW_W - 1, dstY + DRAW_H - 1);
    digitalWrite(TFT_DC, HIGH);
    selectDisplay();

    for (int sy = 0; sy < GIF_FH; ++sy) {
        for (int yRepeat = 0; yRepeat < SCALE; ++yRepeat) {
            for (int sx = 0; sx < GIF_FW; ++sx) {
                const uint16_t color = meowFramePixelOn(frame, sx, sy) ? fg : bg;
                writeData16(color);
                writeData16(color);
            }
        }
    }

    unselectDisplay();
}

static void showMonthlySalaryMeowFrames() {
    fillScreen(BLACK);
    drawText(7, 4, "SALARY MEOW", YELLOW, BLACK, 1);
    drawText(25, 148, "GITEE GIF", CYAN, BLACK, 1);

    for (uint8_t frameIndex = 0; frameIndex < GIF_FRAMES; ++frameIndex) {
        drawMeowFrame2x(gif_frames[frameIndex], 0, 16, WHITE, BLACK);

        Serial.printf("[TFT] Monthly salary meow frame=%u/%u uptime=%lu ms\n",
                      static_cast<unsigned>(frameIndex + 1),
                      static_cast<unsigned>(GIF_FRAMES),
                      static_cast<unsigned long>(millis()));

        delay(max<uint16_t>(25, gif_delays[frameIndex] * 3));
    }
}

void setup() {
    Serial.begin(115200);
    waitForSerialWindow();
    Serial.println();
    Serial.println("[TFT] 1.8 inch ST7735 raw SPI test");
    Serial.println("[TFT] Pins: SCLK=12 MOSI=11 CS=10 DC=9 RST=14 BL=21");
    Serial.println("[TFT] This build bypasses TFT_eSPI to avoid tft.init() crashes.");

    runPreTftDiagnostics();
    initDisplayRaw();
}

void loop() {
    showMonthlySalaryMeowFrames();
}
