#include <Arduino.h>

#if MERGETEST_SPEAKER_AUTO_TTS_DIAG

#include "speaker.h"

namespace {

constexpr uint32_t FIRST_PLAY_DELAY_MS = 1200;
constexpr uint32_t REPLAY_DELAY_MS = 4500;

uint32_t lastPlayMs = 0;
bool firstPlayDone = false;

void playPhrase() {
  Serial.println("[SpeakerAuto] play_tts I can speak now.");
  const bool queued = speaker_play_tts_mock("I can speak now.");
  Serial.printf("[SpeakerAuto] queued=%s\n", queued ? "true" : "false");
  lastPlayMs = millis();
  firstPlayDone = true;
}

}  // namespace

void setup() {
  Serial.begin(115200);
  delay(FIRST_PLAY_DELAY_MS);
  Serial.println("[SpeakerAuto] boot");
  playPhrase();
}

void loop() {
  SpeakerPlaybackResult result{};
  if (speaker_take_tts_playback_result(&result)) {
    Serial.printf(
        "[SpeakerAuto] playback_done ok=%s bytes=%lu duration_ms=%lu\n",
        result.ok ? "true" : "false",
        static_cast<unsigned long>(result.bytes_written),
        static_cast<unsigned long>(result.duration_ms));
  }

  if (firstPlayDone && millis() - lastPlayMs > REPLAY_DELAY_MS) {
    playPhrase();
  }
  delay(20);
}

#endif  // MERGETEST_SPEAKER_AUTO_TTS_DIAG
