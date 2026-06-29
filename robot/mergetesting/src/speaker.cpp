#include "speaker.h"
#include "config.h"
#include "protocol.h"
#include "debug_log.h"

#if MERGETEST_ENABLE_SPEAKER

#include <driver/i2s.h>
#include <freertos/FreeRTOS.h>
#include <freertos/queue.h>
#include <freertos/task.h>
#include <cstdint>
#include <cstdlib>
#include <cstring>

#ifndef MERGETEST_SPEAKER_PCM_DRAIN_ONLY
#define MERGETEST_SPEAKER_PCM_DRAIN_ONLY 0
#endif
#ifndef MERGETEST_SPEAKER_TTS_EMBEDDED_PHRASE
#define MERGETEST_SPEAKER_TTS_EMBEDDED_PHRASE 0
#endif
#ifndef EMBEDDED_TTS_GAIN
#define EMBEDDED_TTS_GAIN 1
#endif

#if MERGETEST_SPEAKER_TTS_EMBEDDED_PHRASE
#include "embedded_tts_phrase.h"
#endif

namespace {

constexpr i2s_port_t SPEAKER_I2S_PORT = I2S_NUM_1;
constexpr size_t FRAMES_PER_BUFFER = 128;
constexpr size_t PCM_PLAYBACK_FRAMES_PER_BUFFER = 128;
constexpr size_t PCM_QUEUE_DEPTH = 8;
constexpr int SPEAKER_AMPLITUDE = 2400;
constexpr TickType_t SPEAKER_WRITE_TIMEOUT_TICKS = pdMS_TO_TICKS(50);
constexpr TickType_t PCM_WRITE_TIMEOUT_TICKS = pdMS_TO_TICKS(20);
constexpr TickType_t PCM_QUEUE_SEND_TIMEOUT_TICKS = pdMS_TO_TICKS(10);
constexpr TickType_t PCM_QUEUE_RECEIVE_TIMEOUT_TICKS = pdMS_TO_TICKS(100);
constexpr int16_t PCM_LEADING_TRIM_THRESHOLD = 16;

struct PcmStreamJob {
  uint8_t* data;
  size_t len;
  bool end;
};

struct TtsBlockingResult {
  bool ok;
  uint32_t bytesWritten;
};

bool writeMonoPcmS16Le(
    const uint8_t* pcm,
    size_t len,
    TickType_t timeoutTicks,
    int gain = 1,
    uint32_t* bytesWritten = nullptr);
void finishPcmPlayback();

int16_t stereoBuffer[FRAMES_PER_BUFFER * 2];
bool gReady = false;
volatile bool gPlaying = false;
volatile bool gPcmStreaming = false;
TaskHandle_t gTaskHandle = nullptr;
TaskHandle_t gPcmTaskHandle = nullptr;
QueueHandle_t gPcmQueue = nullptr;
size_t gPcmBufferLen = 0;
char gTaskSound[32] = {};
char gTaskText[96] = {};
portMUX_TYPE gPlaybackResultMux = portMUX_INITIALIZER_UNLOCKED;
bool gTtsPlaybackResultPending = false;
SpeakerPlaybackResult gTtsPlaybackResult{};

void storeTtsPlaybackResult(bool ok, uint32_t bytesWritten, uint32_t durationMs) {
  portENTER_CRITICAL(&gPlaybackResultMux);
  gTtsPlaybackResult.ok = ok;
  gTtsPlaybackResult.bytes_written = bytesWritten;
  gTtsPlaybackResult.duration_ms = durationMs;
  gTtsPlaybackResultPending = true;
  portEXIT_CRITICAL(&gPlaybackResultMux);
}

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

bool writeFramesWithTimeout(const int16_t* samples, uint32_t frames, TickType_t timeoutTicks) {
  const size_t bytesToWrite = frames * 2 * sizeof(int16_t);
  size_t bytesWritten = 0;
  const esp_err_t err = i2s_write(
      SPEAKER_I2S_PORT,
      samples,
      bytesToWrite,
      &bytesWritten,
      timeoutTicks);
  vTaskDelay(1);
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

bool writeFrames(const int16_t* samples, uint32_t frames) {
  return writeFramesWithTimeout(samples, frames, SPEAKER_WRITE_TIMEOUT_TICKS);
}

int16_t readPcmS16Le(const uint8_t* pcm, size_t frameIndex) {
  const size_t byteIndex = frameIndex * sizeof(int16_t);
  return static_cast<int16_t>(
      static_cast<uint16_t>(pcm[byteIndex]) |
      (static_cast<uint16_t>(pcm[byteIndex + 1]) << 8));
}

int16_t scalePcmSample(int16_t sample, int gain) {
  if (gain <= 1) {
    return sample;
  }
  const int32_t scaled = static_cast<int32_t>(sample) * gain;
  if (scaled > INT16_MAX) {
    return INT16_MAX;
  }
  if (scaled < INT16_MIN) {
    return INT16_MIN;
  }
  return static_cast<int16_t>(scaled);
}

size_t countLeadingQuietPcmFrames(const uint8_t* pcm, size_t frames) {
  size_t offset = 0;
  while (offset < frames && abs(readPcmS16Le(pcm, offset)) <= PCM_LEADING_TRIM_THRESHOLD) {
    ++offset;
  }
  return offset;
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

TtsBlockingResult playTtsBlocking(const char* textPreview) {
  if (!ensureSpeakerReady()) {
    return {false, 0};
  }

#if MERGETEST_SPEAKER_TTS_EMBEDDED_PHRASE
  if (EmbeddedTtsPhrase::SAMPLE_RATE != MERGETEST_SPEAKER_SAMPLE_RATE) {
    LOGE(
        "Speaker",
        "embedded tts sample_rate mismatch embedded=%lu expected=%u",
        static_cast<unsigned long>(EmbeddedTtsPhrase::SAMPLE_RATE),
        MERGETEST_SPEAKER_SAMPLE_RATE);
    releaseSpeakerI2S();
    return {false, 0};
  }

  LOGI(
      "Speaker",
      "tts embedded phrase bytes=%u text=%s preview=%s",
      static_cast<unsigned>(EmbeddedTtsPhrase::PCM_LEN),
      EmbeddedTtsPhrase::TEXT,
      textPreview ? textPreview : "");
  uint32_t bytesWritten = 0;
  const bool ok = writeMonoPcmS16Le(
      EmbeddedTtsPhrase::PCM,
      EmbeddedTtsPhrase::PCM_LEN,
      SPEAKER_WRITE_TIMEOUT_TICKS,
      EMBEDDED_TTS_GAIN,
      &bytesWritten);
  LOGI("Speaker", "tts embedded pcm write done ok=%s", ok ? "true" : "false");
  finishPcmPlayback();
  LOGI("Speaker", "tts embedded pcm finish done");
  releaseSpeakerI2S();
  LOGI("Speaker", "tts embedded i2s released");
  return {ok, bytesWritten};
#else
  const size_t len = textPreview ? strlen(textPreview) : 0;
  const uint32_t ms = static_cast<uint32_t>(min<size_t>(3000, 600 + len * 80));
  LOGI("Speaker", "tts mock %u ms preview=%s", ms, textPreview ? textPreview : "");
  const bool ok = playTone(520, ms / 3, 2800) &&
                  playTone(620, ms / 3, 2800) &&
                  playTone(720, ms / 3, 2800);
  releaseSpeakerI2S();
  return {ok, 0};
#endif
}

bool writeMonoPcmS16Le(
    const uint8_t* pcm,
    size_t len,
    TickType_t timeoutTicks,
    int gain,
    uint32_t* bytesWritten) {
  if (!pcm || len < 2) {
    return true;
  }

  const size_t frames = len / sizeof(int16_t);
  LOGI(
      "Speaker",
      "pcm mono write start bytes=%u frames=%u timeout_ticks=%u",
      static_cast<unsigned>(len),
      static_cast<unsigned>(frames),
      static_cast<unsigned>(timeoutTicks));
  size_t offset = countLeadingQuietPcmFrames(pcm, frames);
  if (offset >= frames) {
    LOGW("Speaker", "pcm mono all frames quiet, skip write frames=%u", static_cast<unsigned>(frames));
    return true;
  }
  if (offset > 0) {
    LOGI("Speaker", "pcm mono skipped leading quiet frames=%u", static_cast<unsigned>(offset));
  }
  while (offset < frames) {
    const uint32_t chunk = min<uint32_t>(PCM_PLAYBACK_FRAMES_PER_BUFFER, frames - offset);
    for (uint32_t i = 0; i < chunk; ++i) {
      const int16_t sample = scalePcmSample(readPcmS16Le(pcm, offset + i), gain);
      stereoBuffer[i * 2] = sample;
      stereoBuffer[i * 2 + 1] = sample;
    }
    if (!writeFramesWithTimeout(stereoBuffer, chunk, timeoutTicks)) {
      LOGE("Speaker", "pcm mono write failed offset=%u", static_cast<unsigned>(offset));
      return false;
    }
    if (bytesWritten) {
      *bytesWritten += chunk * 2U * sizeof(int16_t);
    }
    offset += chunk;
    if ((offset % 4096) == 0 || offset >= frames) {
      LOGI(
          "Speaker",
          "pcm mono write progress frames=%u/%u",
          static_cast<unsigned>(offset),
          static_cast<unsigned>(frames));
    }
  }
  LOGI("Speaker", "pcm mono write complete frames=%u", static_cast<unsigned>(frames));
  return true;
}

void resetPcmBuffer() {
  gPcmBufferLen = 0;
}

void finishPcmPlayback() {
  if (!gReady) {
    return;
  }
  LOGI("Speaker", "pcm finish zero dma start");
  i2s_zero_dma_buffer(SPEAKER_I2S_PORT);
  LOGI("Speaker", "pcm finish zero dma done");
  vTaskDelay(pdMS_TO_TICKS(20));
}

void freePcmJob(PcmStreamJob& job) {
  if (job.data) {
    free(job.data);
    job.data = nullptr;
  }
  job.len = 0;
}

void closePcmQueue() {
  QueueHandle_t queue = gPcmQueue;
  gPcmQueue = nullptr;
  if (queue) {
    vQueueDelete(queue);
  }
}

bool enqueuePcmChunk(const uint8_t* pcm, size_t len) {
  if (!gPcmQueue || !pcm || len == 0) {
    return false;
  }

  PcmStreamJob job{};
  job.data = static_cast<uint8_t*>(malloc(len));
  if (!job.data) {
    LOGE("Speaker", "pcm chunk alloc failed len=%u", static_cast<unsigned>(len));
    return false;
  }
  memcpy(job.data, pcm, len);
  job.len = len;

  if (xQueueSend(gPcmQueue, &job, PCM_QUEUE_SEND_TIMEOUT_TICKS) != pdPASS) {
    freePcmJob(job);
    LOGW("Speaker", "pcm queue full len=%u", static_cast<unsigned>(len));
    return false;
  }
  return true;
}

bool enqueuePcmEnd() {
  if (!gPcmQueue) {
    return false;
  }
  PcmStreamJob job{};
  job.end = true;
  return xQueueSend(gPcmQueue, &job, PCM_QUEUE_SEND_TIMEOUT_TICKS) == pdPASS;
}

void pcmStreamTask(void* arg) {
  (void)arg;
  bool ok = true;
  size_t playedBytes = 0;

  while (true) {
    PcmStreamJob job{};
    if (xQueueReceive(gPcmQueue, &job, PCM_QUEUE_RECEIVE_TIMEOUT_TICKS) != pdPASS) {
      if (!gPcmStreaming) {
        break;
      }
      continue;
    }

    if (job.end) {
      break;
    }

    if (job.data && job.len > 0) {
      ok = writeMonoPcmS16Le(job.data, job.len, PCM_WRITE_TIMEOUT_TICKS) && ok;
      playedBytes += job.len;
    }
    freePcmJob(job);
  }

  finishPcmPlayback();
  closePcmQueue();
  resetPcmBuffer();
  gPcmStreaming = false;
  gPlaying = false;
  gPcmTaskHandle = nullptr;
  LOGI("Speaker", "pcm stream task done ok=%s played_bytes=%u", ok ? "true" : "false", static_cast<unsigned>(playedBytes));
  vTaskDelete(nullptr);
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
  const uint32_t startedMs = millis();
  const TtsBlockingResult result = playTtsBlocking(text);
  const uint32_t durationMs = millis() - startedMs;
  storeTtsPlaybackResult(result.ok, result.bytesWritten, durationMs);
  LOGI(
      "Speaker",
      "tts playback done ok=%s bytes_written=%lu duration_ms=%lu",
      result.ok ? "true" : "false",
      static_cast<unsigned long>(result.bytesWritten),
      static_cast<unsigned long>(durationMs));
  gPlaying = false;
  gTaskHandle = nullptr;
  vTaskDelete(nullptr);
}

bool startPlaybackTask(const char* sound) {
  if (gPlaying || gPcmStreaming) {
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
  if (gPlaying || gPcmStreaming) {
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

bool speaker_take_tts_playback_result(SpeakerPlaybackResult* result) {
  if (!result) {
    return false;
  }
  portENTER_CRITICAL(&gPlaybackResultMux);
  if (!gTtsPlaybackResultPending) {
    portEXIT_CRITICAL(&gPlaybackResultMux);
    return false;
  }
  *result = gTtsPlaybackResult;
  gTtsPlaybackResultPending = false;
  portEXIT_CRITICAL(&gPlaybackResultMux);
  return true;
}

bool speaker_begin_pcm_stream(uint32_t sampleRate, uint8_t channels) {
  if (gPcmStreaming) {
    return true;
  }
  if (gPlaying) {
    LOGW("Speaker", "pcm stream busy");
    return false;
  }
  if (channels != 1 || sampleRate != MERGETEST_SPEAKER_SAMPLE_RATE) {
    LOGW(
        "Speaker",
        "unsupported pcm stream format sample_rate=%lu channels=%u",
        static_cast<unsigned long>(sampleRate),
        static_cast<unsigned>(channels));
    return false;
  }

  resetPcmBuffer();

#if !MERGETEST_SPEAKER_PCM_DRAIN_ONLY
  if (!ensureSpeakerReady()) {
    LOGE("Speaker", "pcm stream speaker init failed");
    return false;
  }
  gPcmQueue = xQueueCreate(PCM_QUEUE_DEPTH, sizeof(PcmStreamJob));
  if (!gPcmQueue) {
    LOGE("Speaker", "pcm queue create failed");
    return false;
  }
#endif

  gPcmStreaming = true;
  gPlaying = true;

#if !MERGETEST_SPEAKER_PCM_DRAIN_ONLY
  const BaseType_t created = xTaskCreate(
      pcmStreamTask,
      "speaker_pcm",
      4096,
      nullptr,
      1,
      &gPcmTaskHandle);
  if (created != pdPASS) {
    closePcmQueue();
    gPcmStreaming = false;
    gPlaying = false;
    LOGE("Speaker", "pcm stream task create failed");
    return false;
  }
#endif

  LOGI(
      "Speaker",
      "pcm stream begin sample_rate=%lu channels=%u drain_only=%u",
      static_cast<unsigned long>(sampleRate),
      channels,
      static_cast<unsigned>(MERGETEST_SPEAKER_PCM_DRAIN_ONLY));
  return true;
}

bool speaker_write_pcm_chunk(const uint8_t* pcm, size_t len) {
  if (!gPcmStreaming) {
    return false;
  }
  if (!pcm || len == 0) {
    return true;
  }

  gPcmBufferLen += len;

#if MERGETEST_SPEAKER_PCM_DRAIN_ONLY
  return true;
#else
  return enqueuePcmChunk(pcm, len);
#endif
}

void speaker_end_pcm_stream() {
  if (!gPcmStreaming) {
    return;
  }
  gPcmStreaming = false;
  LOGI("Speaker", "pcm stream end streamed_bytes=%u", static_cast<unsigned>(gPcmBufferLen));

#if MERGETEST_SPEAKER_PCM_DRAIN_ONLY
  resetPcmBuffer();
  gPlaying = false;
#else
  if (!enqueuePcmEnd()) {
    finishPcmPlayback();
    closePcmQueue();
    resetPcmBuffer();
    gPlaying = false;
  }
#endif
}

void speaker_stop() {
  gPlaying = false;
  if (gPcmStreaming) {
    gPcmStreaming = false;
    resetPcmBuffer();
    finishPcmPlayback();
    closePcmQueue();
    return;
  }
  if (gReady) {
    writeSilence(50);
    releaseSpeakerI2S();
  }
}

#else

bool speaker_init() { return false; }
bool speaker_play_local(const char*) { return false; }
bool speaker_play_tts_mock(const char*) { return false; }
bool speaker_take_tts_playback_result(SpeakerPlaybackResult*) { return false; }
bool speaker_begin_pcm_stream(uint32_t, uint8_t) { return false; }
bool speaker_write_pcm_chunk(const uint8_t*, size_t) { return false; }
void speaker_end_pcm_stream() {}
void speaker_stop() {}

#endif
