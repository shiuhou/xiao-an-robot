#include <Arduino.h>

#include "board_pins.h"
#include "feature_flags.h"
#include "protocol.h"
#include "peripherals/speaker.h"

#ifndef SPEAKER_SAMPLE_RATE
#define SPEAKER_SAMPLE_RATE 16000
#endif

static constexpr uint32_t STARTUP_DELAY_MS = 1500;

static void printWiring() {
    Serial.println();
    Serial.println("[SpeakerTest] MAX98357A wiring:");
    Serial.println("[SpeakerTest] VIN -> 5V or 3V3, GND -> common GND");
    Serial.printf("[SpeakerTest] BCLK -> GPIO%d, LRC/WS -> GPIO%d, DIN -> GPIO%d\n",
                  SPEAKER_I2S_BCLK,
                  SPEAKER_I2S_LRC,
                  SPEAKER_I2S_DIN);
}

void setup() {
    Serial.begin(115200);
    delay(STARTUP_DELAY_MS);

    Serial.println("[SpeakerTest] Xiao-An MAX98357A via peripherals/speaker");
    Serial.printf("[SpeakerTest] sample_rate=%d\n", SPEAKER_SAMPLE_RATE);
    printWiring();

    if (!speaker_init()) {
        Serial.println("[SpeakerTest][ERR] speaker_init failed");
        while (true) {
            delay(1000);
        }
    }

    Serial.println("[SpeakerTest] Init OK. Cycling local sounds.");
}

void loop() {
    speaker_play_local(LocalSound::CARE_01);
    delay(500);
    speaker_play_local(LocalSound::WAKE_01);
    delay(500);
    speaker_play_local(LocalSound::ALARM_01);
    delay(2000);
}
