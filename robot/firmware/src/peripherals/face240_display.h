#pragma once

#include <Arduino.h>

void face240_init();
void face240_emotion(const char* emotion_tag, int intensity = 5);
void face240_tick();
