#include "speaker.h"
#include "config.h"
#include "protocol.h"
#include "debug_log.h"

#if MERGETEST_ENABLE_SPEAKER

#include <driver/i2s.h>
#include <freertos/FreeRTOS.h>
#include <freertos/task.h>
#include <cstring>

namespace {

constexpr i2s_port_t SPEAKER_I2S_PORT = I2S_NUM_1;
constexpr size_t FRAMES_PER_BUFFER = 128;
constexpr int SPEAKER_AMPLITUDE = 2400;
constexpr TickType_t SPEAKER_WRITE_TIMEOUT_TICKS = pdMS_TO_TICKS(50);

int16_t stereoBuffer[FRAMES_PER_BUFFER * 2];
bool gReady = false;
volatile bool gPlaying = false;
TaskHandle_t gTaskHandle = nullptr;
char gTaskSound[32] = {};
char gTaskText[96] = {};

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

void releaseSpeakerI2S() {
  if (!gReady) {
    return;
  }
  i2s_zero_dma_buffer(SPEAKER_I2S_PORT);
  i2s_driver_uninstall(SPEAKER_I2S_PORT);
  gReady = false;
}

bool ensureSpeakerReady() {
  if (gReady) {
    return true;
  }
  return speaker_init();
}

bool writeFrames(const int16_t* samples, uint32_t frames) {
  const size_t bytesToWrite = frames * 2 * sizeof(int16_t);
  size_t bytesWritten = 0;
  const esp_err_t err = i2s_write(
      SPEAKER_I2S_PORT,
      samples,
      bytesToWrite,
      &bytesWritten,
      SPEAKER_WRITE_TIMEOUT_TICKS);
  yield();
  if (err != ESP_OK || bytesWritten != bytesToWrite) {
    LOGE(
        "Speaker",
        "I2S write failed err=%d bytes=%u/%u",
        static_cast<int>(err),
        static_cast<unsigned>(bytesWritten),
        static_cast<unsigned>(bytesToWrite));
    return false;
  }
  return true;
}

bool writeSilence(uint32_t durationMs) {
  memset(stereoBuffer, 0, sizeof(stereoBuffer));
  const uint32_t totalFrames = static_cast<uint32_t>(
      static_cast<uint64_t>(MERGETEST_SPEAKER_SAMPLE_RATE) * durationMs / 1000);
  uint32_t framesWritten = 0;
  while (framesWritten < totalFrames) {
    const uint32_t chunk = min<uint32_t>(FRAMES_PER_BUFFER, totalFrames - framesWritten);
    if (!writeFrames(stereoBuffer, chunk)) {
      return false;
    }
    framesWritten += chunk;
  }
  return true;
}

bool playTone(uint32_t frequencyHz, uint32_t durationMs, int amplitude = SPEAKER_AMPLITUDE) {
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
    if (!writeFrames(stereoBuffer, chunk)) {
      return false;
    }
    framesWritten += chunk;
  }
  return true;
}

bool playCareChime() {
  return playTone(440, 180, SPEAKER_AMPLITUDE) &&
         playTone(554, 180, SPEAKER_AMPLITUDE) &&
         playTone(659, 260, SPEAKER_AMPLITUDE) &&
         writeSilence(80);
}

bool playAlarmBeeps() {
  for (int i = 0; i < 3; ++i) {
    if (!playTone(880, 120, SPEAKER_AMPLITUDE) || !writeSilence(80)) {
      return false;
    }
  }
  return true;
}

bool playWakeChime() {
  return playTone(523, 120, SPEAKER_AMPLITUDE) &&
         playTone(659, 120, SPEAKER_AMPLITUDE) &&
         playTone(784, 180, SPEAKER_AMPLITUDE) &&
         playTone(988, 220, SPEAKER_AMPLITUDE);
}

bool playLocalBlocking(const char* sound) {
  bool ok = false;
  if (strcmp(sound, LocalSound::CARE_01) == 0 || strcmp(sound, "wakeup_chime") == 0) {
    ok = ensureSpeakerReady() && playCareChime();
  } else if (strcmp(sound, LocalSound::ALARM_01) == 0 || strcmp(sound, "error_beep") == 0) {
    ok = ensureSpeakerReady() && playAlarmBeeps();
  } else if (strcmp(sound, LocalSound::WAKE_01) == 0 || strcmp(sound, "success_ding") == 0) {
    ok = ensureSpeakerReady() && playWakeChime();
  }
  releaseSpeakerI2S();
  return ok;
}

bool playTtsBlocking(const char* textPreview) {
  if (!ensureSpeakerReady()) {
    return false;
  }
  const size_t len = textPreview ? strlen(textPreview) : 0;
  const uint32_t ms = static_cast<uint32_t>(min<size_t>(3000, 600 + len * 80));
  LOGI("Speaker", "tts mock %u ms preview=%s", ms, textPreview ? textPreview : "");
  const bool ok = playTone(520, ms / 3, 2800) &&
                  playTone(620, ms / 3, 2800) &&
                  playTone(720, ms / 3, 2800);
  releaseSpeakerI2S();
  return ok;
}

void speakerTask(void*) {
  char sound[sizeof(gTaskSound)] = {};
  strncpy(sound, gTaskSound, sizeof(sound) - 1);
  vTaskDelay(pdMS_TO_TICKS(100));
  const bool ok = playLocalBlocking(sound);
  LOGI("Speaker", "play_local done %s ok=%s", sound, ok ? "true" : "false");
  gPlaying = false;
  gTaskHandle = nullptr;
  vTaskDelete(nullptr);
}

void speakerTtsTask(void*) {
  char text[sizeof(gTaskText)] = {};
  strncpy(text, gTaskText, sizeof(text) - 1);
  vTaskDelay(pdMS_TO_TICKS(100));
  const bool ok = playTtsBlocking(text);
  LOGI("Speaker", "tts mock done ok=%s", ok ? "true" : "false");
  gPlaying = false;
  gTaskHandle = nullptr;
  vTaskDelete(nullptr);
}

bool startPlaybackTask(const char* sound) {
  if (gPlaying) {
    LOGW("Speaker", "play_local busy");
    return false;
  }

  strncpy(gTaskSound, sound, sizeof(gTaskSound) - 1);
  gTaskSound[sizeof(gTaskSound) - 1] = '\0';
  gPlaying = true;
  const BaseType_t created = xTaskCreate(
      speakerTask,
      "speaker_play",
      4096,
      nullptr,
      1,
      &gTaskHandle);
  if (created != pdPASS) {
    gPlaying = false;
    gTaskHandle = nullptr;
    LOGE("Speaker", "play_local task create failed");
    return false;
  }
  return true;
}

bool startTtsTask(const char* textPreview) {
  if (gPlaying) {
    LOGW("Speaker", "tts mock busy");
    return false;
  }

  strncpy(gTaskText, textPreview ? textPreview : "", sizeof(gTaskText) - 1);
  gTaskText[sizeof(gTaskText) - 1] = '\0';
  gPlaying = true;
  const BaseType_t created = xTaskCreate(
      speakerTtsTask,
      "speaker_tts",
      4096,
      nullptr,
      1,
      &gTaskHandle);
  if (created != pdPASS) {
    gPlaying = false;
    gTaskHandle = nullptr;
    LOGE("Speaker", "tts mock task create failed");
    return false;
  }
  return true;
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
  if (!sound) {
    return false;
  }

  LOGI("Speaker", "play_local %s", sound);
  if (strcmp(sound, LocalSound::CARE_01) == 0 || strcmp(sound, "wakeup_chime") == 0) {
  } else if (strcmp(sound, LocalSound::ALARM_01) == 0 || strcmp(sound, "error_beep") == 0) {
  } else if (strcmp(sound, LocalSound::WAKE_01) == 0 || strcmp(sound, "success_ding") == 0) {
  } else {
    LOGW("Speaker", "unsupported local sound %s", sound);
    return false;
  }

  return startPlaybackTask(sound);
}

bool speaker_play_tts_mock(const char* textPreview) {
  return startTtsTask(textPreview);
}

void speaker_stop() {
  gPlaying = false;
  if (gReady) {
    writeSilence(50);
    releaseSpeakerI2S();
  }
}

#else

bool speaker_init() { return false; }
bool speaker_play_local(const char*) { return false; }
bool speaker_play_tts_mock(const char*) { return false; }
void speaker_stop() {}

#endif
