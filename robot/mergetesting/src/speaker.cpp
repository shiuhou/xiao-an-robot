#include "speaker.h"
#include "config.h"
#include "protocol.h"
#include "debug_log.h"

#if MERGETEST_ENABLE_SPEAKER

#include <driver/i2s.h>
#include <cstring>

namespace {

constexpr i2s_port_t SPEAKER_I2S_PORT = I2S_NUM_1;
constexpr size_t FRAMES_PER_BUFFER = 128;
constexpr int SPEAKER_AMPLITUDE = 4500;

int16_t stereoBuffer[FRAMES_PER_BUFFER * 2];
bool gReady = false;

bool installSpeakerI2S() {
  const i2s_config_t config = {
      .mode = static_cast<i2s_mode_t>(I2S_MODE_MASTER | I2S_MODE_TX),
      .sample_rate = MERGETEST_SPEAKER_SAMPLE_RATE,
      .bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT,
      .channel_format = I2S_CHANNEL_FMT_RIGHT_LEFT,
      .communication_format = I2S_COMM_FORMAT_STAND_I2S,
      .intr_alloc_flags = ESP_INTR_FLAG_LEVEL1,
      .dma_buf_count = 6,
      .dma_buf_len = 256,
      .use_apll = false,
      .tx_desc_auto_clear = true,
  };

  const i2s_pin_config_t pins = {
      .bck_io_num = MERGETEST_SPEAKER_BCLK,
      .ws_io_num = MERGETEST_SPEAKER_LRC,
      .data_out_num = MERGETEST_SPEAKER_DIN,
      .data_in_num = I2S_PIN_NO_CHANGE,
  };

  if (i2s_driver_install(SPEAKER_I2S_PORT, &config, 0, nullptr) != ESP_OK) {
    return false;
  }
  if (i2s_set_pin(SPEAKER_I2S_PORT, &pins) != ESP_OK) {
    i2s_driver_uninstall(SPEAKER_I2S_PORT);
    return false;
  }
  i2s_zero_dma_buffer(SPEAKER_I2S_PORT);
  return true;
}

void writeSilence(uint32_t durationMs) {
  memset(stereoBuffer, 0, sizeof(stereoBuffer));
  const uint32_t totalFrames = static_cast<uint32_t>(
      static_cast<uint64_t>(MERGETEST_SPEAKER_SAMPLE_RATE) * durationMs / 1000);
  uint32_t framesWritten = 0;
  while (framesWritten < totalFrames) {
    const uint32_t chunk = min<uint32_t>(FRAMES_PER_BUFFER, totalFrames - framesWritten);
    size_t bytesWritten = 0;
    i2s_write(SPEAKER_I2S_PORT, stereoBuffer, chunk * 2 * sizeof(int16_t), &bytesWritten, portMAX_DELAY);
    framesWritten += chunk;
  }
}

void playTone(uint32_t frequencyHz, uint32_t durationMs, int amplitude = SPEAKER_AMPLITUDE) {
  const uint32_t totalFrames = static_cast<uint32_t>(
      static_cast<uint64_t>(MERGETEST_SPEAKER_SAMPLE_RATE) * durationMs / 1000);
  uint32_t framesWritten = 0;
  uint32_t phase = 0;
  const uint32_t phaseStep = static_cast<uint32_t>(
      (static_cast<uint64_t>(frequencyHz) << 32) / MERGETEST_SPEAKER_SAMPLE_RATE);

  while (framesWritten < totalFrames) {
    const uint32_t chunk = min<uint32_t>(FRAMES_PER_BUFFER, totalFrames - framesWritten);
    for (uint32_t i = 0; i < chunk; ++i) {
      phase += phaseStep;
      const int16_t sample = (phase & 0x80000000UL) ? amplitude : static_cast<int16_t>(-amplitude);
      stereoBuffer[i * 2] = sample;
      stereoBuffer[i * 2 + 1] = sample;
    }
    size_t bytesWritten = 0;
    i2s_write(SPEAKER_I2S_PORT, stereoBuffer, chunk * 2 * sizeof(int16_t), &bytesWritten, portMAX_DELAY);
    framesWritten += chunk;
  }
}

void playCareChime() {
  playTone(440, 180, 3500);
  playTone(554, 180, 3500);
  playTone(659, 260, 3500);
  writeSilence(80);
}

void playAlarmBeeps() {
  for (int i = 0; i < 3; ++i) {
    playTone(880, 120, 4000);
    writeSilence(80);
  }
}

void playWakeChime() {
  playTone(523, 120, 3800);
  playTone(659, 120, 3800);
  playTone(784, 180, 3800);
  playTone(988, 220, 3800);
}

}  // namespace

bool speaker_init() {
  gReady = installSpeakerI2S();
  if (gReady) {
    LOGI("Speaker", "I2S ready");
  } else {
    LOGE("Speaker", "I2S init failed");
  }
  return gReady;
}

bool speaker_play_local(const char* sound) {
  if (!gReady || !sound) {
    return false;
  }

  LOGI("Speaker", "play_local %s", sound);
  if (strcmp(sound, LocalSound::CARE_01) == 0 || strcmp(sound, "wakeup_chime") == 0) {
    playCareChime();
    return true;
  }
  if (strcmp(sound, LocalSound::ALARM_01) == 0 || strcmp(sound, "error_beep") == 0) {
    playAlarmBeeps();
    return true;
  }
  if (strcmp(sound, LocalSound::WAKE_01) == 0 || strcmp(sound, "success_ding") == 0) {
    playWakeChime();
    return true;
  }

  playTone(660, 200);
  return true;
}

bool speaker_play_tts_mock(const char* textPreview) {
  if (!gReady) {
    return false;
  }
  const size_t len = textPreview ? strlen(textPreview) : 0;
  const uint32_t ms = static_cast<uint32_t>(min<size_t>(3000, 600 + len * 80));
  LOGI("Speaker", "tts mock %u ms preview=%s", ms, textPreview ? textPreview : "");
  playTone(520, ms / 3, 2800);
  playTone(620, ms / 3, 2800);
  playTone(720, ms / 3, 2800);
  return true;
}

void speaker_stop() {
  if (gReady) {
    writeSilence(50);
  }
}

#else

bool speaker_init() { return false; }
bool speaker_play_local(const char*) { return false; }
bool speaker_play_tts_mock(const char*) { return false; }
void speaker_stop() {}

#endif
