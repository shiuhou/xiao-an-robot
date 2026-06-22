#include "display.h"
#include "config.h"
#include "protocol.h"

#if MERGETEST_ENABLE_DISPLAY && MERGETEST_DISPLAY_FACE240

#include "face240_display.h"

void display_init() {
  face240_init();
}

void display_emotion(const char* emotion_tag, int intensity) {
  face240_emotion(emotion_tag, intensity);
}

void display_set_connection(const char* status) {
  (void)status;
}

void display_set_camera(const char* status) {
  (void)status;
}

void display_set_motion(const char* status) {
  (void)status;
}

void display_show_boot_neutral() {
  face240_emotion(Expression::NEUTRAL, 5);
}

void display_tick() {
  face240_tick();
}

#elif MERGETEST_ENABLE_DISPLAY

#include <TFT_eSPI.h>
#include <string.h>

namespace {

TFT_eSPI tft;

constexpr int16_t SCREEN_W = 128;
constexpr int16_t SCREEN_H = 160;
constexpr int16_t HEADER_H = 20;
constexpr int16_t FACE_TOP = 24;
constexpr int16_t FACE_H = 84;
constexpr int16_t STATUS_TOP = 112;
constexpr int16_t STATUS_ROW_H = 15;

DisplayStatus currentStatus = {"BOOT", "CAM OFF", "IDLE"};
const char* currentExpression = Expression::NEUTRAL;
int currentIntensity = 5;
bool initialized = false;

bool sameToken(const char* lhs, const char* rhs) {
  return lhs && rhs && strcmp(lhs, rhs) == 0;
}

const char* normalizeExpression(const char* expr) {
  if (!expr || !expr[0]) return Expression::NEUTRAL;
  if (sameToken(expr, Expression::IDLE)) return Expression::NEUTRAL;
  if (sameToken(expr, Expression::LISTENING)) return Expression::THINKING;
  if (sameToken(expr, Expression::ERROR)) return Expression::SURPRISED;
  return expr;
}

int clampIntensity(int value) {
  if (value < 1) return 1;
  if (value > 10) return 10;
  return value;
}

uint16_t connectionColor() {
  if (sameToken(currentStatus.connection, "WS OK") || sameToken(currentStatus.connection, "ONLINE")) {
    return TFT_GREEN;
  }
  if (sameToken(currentStatus.connection, "WIFI...") || sameToken(currentStatus.connection, "WS...")) {
    return TFT_YELLOW;
  }
  return TFT_RED;
}

uint16_t cameraColor() {
  if (sameToken(currentStatus.camera, "CAM OK")) return TFT_CYAN;
  if (sameToken(currentStatus.camera, "CAM ERR")) return TFT_RED;
  return TFT_DARKGREY;
}

uint16_t motionColor() {
  if (sameToken(currentStatus.motion, "IDLE") || sameToken(currentStatus.motion, "STOP")) return TFT_GREEN;
  return TFT_ORANGE;
}

void drawLabelValue(int16_t y, const char* label, const char* value, uint16_t color) {
  tft.fillRect(0, y, SCREEN_W, STATUS_ROW_H, TFT_BLACK);
  tft.setTextDatum(TL_DATUM);
  tft.setTextSize(1);
  tft.setTextColor(TFT_DARKGREY, TFT_BLACK);
  tft.drawString(label, 4, y + 3, 1);
  tft.setTextColor(color, TFT_BLACK);
  tft.drawString(value ? value : "-", 44, y + 3, 1);
}

void drawHeader() {
  tft.fillRect(0, 0, SCREEN_W, HEADER_H, TFT_BLACK);
  tft.drawFastHLine(0, HEADER_H - 1, SCREEN_W, TFT_DARKGREY);
  tft.fillCircle(8, 9, 4, connectionColor());
  tft.setTextColor(TFT_WHITE, TFT_BLACK);
  tft.drawString("XIAO-AN", 18, 5, 1);
  tft.setTextColor(connectionColor(), TFT_BLACK);
  tft.drawRightString(currentStatus.connection ? currentStatus.connection : "-", SCREEN_W - 4, 5, 1);
}

void drawEyesNeutral(int16_t eyeY, int16_t eyeH, uint16_t color) {
  tft.fillRoundRect(30, eyeY, 20, eyeH, 6, color);
  tft.fillRoundRect(78, eyeY, 20, eyeH, 6, color);
}

void drawMouthSmile(uint16_t color) {
  tft.drawLine(48, 86, 56, 94, color);
  tft.drawLine(56, 94, 72, 94, color);
  tft.drawLine(72, 94, 80, 86, color);
}

void drawMouthFlat(uint16_t color) {
  tft.drawFastHLine(48, 91, 32, color);
}

void drawMouthSad(uint16_t color) {
  tft.drawLine(48, 95, 56, 87, color);
  tft.drawLine(56, 87, 72, 87, color);
  tft.drawLine(72, 87, 80, 95, color);
}

void drawExpression() {
  const char* expr = normalizeExpression(currentExpression);
  const int eyeH = 18 + clampIntensity(currentIntensity);
  tft.fillRect(0, FACE_TOP, SCREEN_W, FACE_H, TFT_BLACK);

  uint16_t faceColor = TFT_SKYBLUE;
  if (sameToken(expr, Expression::HAPPY)) faceColor = TFT_GREEN;
  else if (sameToken(expr, Expression::SAD) || sameToken(expr, Expression::TIRED)) faceColor = TFT_BLUE;
  else if (sameToken(expr, Expression::CARING)) faceColor = TFT_MAGENTA;
  else if (sameToken(expr, Expression::THINKING)) faceColor = TFT_YELLOW;
  else if (sameToken(expr, Expression::SPEAKING)) faceColor = TFT_CYAN;
  else if (sameToken(expr, Expression::SURPRISED)) faceColor = TFT_ORANGE;
  else if (sameToken(expr, Expression::SLEEPING)) faceColor = TFT_DARKGREY;

  if (sameToken(expr, Expression::SLEEPING)) {
    tft.drawFastHLine(28, 60, 24, faceColor);
    tft.drawFastHLine(76, 60, 24, faceColor);
    drawMouthFlat(faceColor);
  } else if (sameToken(expr, Expression::SURPRISED)) {
    tft.drawCircle(40, 60, 10, faceColor);
    tft.drawCircle(88, 60, 10, faceColor);
    tft.fillCircle(64, 92, 8, faceColor);
  } else if (sameToken(expr, Expression::TIRED)) {
    tft.drawFastHLine(28, 60, 24, faceColor);
    tft.drawFastHLine(76, 60, 24, faceColor);
    drawMouthSad(faceColor);
  } else if (sameToken(expr, Expression::SAD)) {
    drawEyesNeutral(50, eyeH, faceColor);
    drawMouthSad(faceColor);
  } else if (sameToken(expr, Expression::THINKING)) {
    drawEyesNeutral(48, eyeH, faceColor);
    tft.fillCircle(84, 36, 3, faceColor);
    drawMouthFlat(faceColor);
  } else if (sameToken(expr, Expression::SPEAKING)) {
    drawEyesNeutral(46, eyeH, faceColor);
    tft.drawRoundRect(48, 84, 32, 16, 4, faceColor);
  } else {
    drawEyesNeutral(46, eyeH, faceColor);
    if (sameToken(expr, Expression::HAPPY) || sameToken(expr, Expression::CARING)) {
      drawMouthSmile(faceColor);
    } else {
      drawMouthFlat(faceColor);
    }
  }

  tft.setTextDatum(MC_DATUM);
  tft.setTextColor(faceColor, TFT_BLACK);
  tft.drawString(expr, SCREEN_W / 2, 106, 1);
}

void render() {
  if (!initialized) return;
  drawHeader();
  drawExpression();
  drawLabelValue(STATUS_TOP, "CONN", currentStatus.connection, connectionColor());
  drawLabelValue(STATUS_TOP + STATUS_ROW_H, "CAM", currentStatus.camera, cameraColor());
  drawLabelValue(STATUS_TOP + STATUS_ROW_H * 2, "MOVE", currentStatus.motion, motionColor());
  tft.drawRect(0, 0, SCREEN_W, SCREEN_H, TFT_DARKGREY);
}

}  // namespace

void display_init() {
  tft.init();
  tft.setRotation(0);
  tft.fillScreen(TFT_BLACK);
  initialized = true;
  display_show_boot_neutral();
}

void display_emotion(const char* emotion_tag, int intensity) {
  currentExpression = emotion_tag ? emotion_tag : Expression::NEUTRAL;
  currentIntensity = clampIntensity(intensity);
  render();
}

void display_set_connection(const char* status) {
  currentStatus.connection = status ? status : "-";
  render();
}

void display_set_camera(const char* status) {
  currentStatus.camera = status ? status : "-";
  render();
}

void display_set_motion(const char* status) {
  currentStatus.motion = status ? status : "-";
  render();
}

void display_show_boot_neutral() {
  currentStatus.connection = "BOOT";
  currentStatus.camera = "CAM OFF";
  currentStatus.motion = "IDLE";
  currentExpression = Expression::NEUTRAL;
  currentIntensity = 5;
  render();
}

void display_tick() {}

#else

void display_init() {}
void display_emotion(const char*, int) {}
void display_set_connection(const char*) {}
void display_set_camera(const char*) {}
void display_set_motion(const char*) {}
void display_show_boot_neutral() {}
void display_tick() {}

#endif
