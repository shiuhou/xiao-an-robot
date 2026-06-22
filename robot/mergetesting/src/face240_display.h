#pragma once
// face240_display.h — 2.4" ST7789 九表情（提取自 robot_face_9expr_merged_optimized.cpp）

#include <Arduino.h>

void face240_init();
void face240_emotion(const char* emotion_tag, int intensity = 5);
void face240_tick();
