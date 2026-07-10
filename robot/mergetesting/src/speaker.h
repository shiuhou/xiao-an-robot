#pragma once

#include <Arduino.h>

struct SpeakerPlaybackResult {
  bool ok = false;
  uint32_t bytes_written = 0;
  uint32_t duration_ms = 0;
  uint32_t buffered_bytes = 0;
  const char* playback_mode = "unknown";
};

bool speaker_init();
bool speaker_play_local(const char* sound);
bool speaker_play_tts_mock(const char* textPreview);
bool speaker_take_tts_playback_result(SpeakerPlaybackResult* result);
const char* speaker_last_error_detail();
bool speaker_pcm_stream_active();
uint32_t speaker_pcm_stream_age_ms();
bool speaker_abort_pcm_stream(const char* reason);
bool speaker_begin_pcm_stream(uint32_t sampleRate, uint8_t channels, bool bufferedStream);
bool speaker_write_pcm_chunk(const uint8_t* pcm, size_t len);
void speaker_end_pcm_stream();
void speaker_stop();
