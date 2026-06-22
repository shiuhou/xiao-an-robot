#pragma once

#include <Arduino.h>

bool speaker_init();
bool speaker_play_local(const char* sound);
bool speaker_play_tts_mock(const char* textPreview);
void speaker_stop();
