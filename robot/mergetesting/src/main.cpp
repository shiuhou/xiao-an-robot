/**
 * Thin Arduino entrypoint for the DK-2500/base-station integration firmware.
 *
 * Runtime wiring lives in app/mergetesting_app.cpp. Reusable behavior lives in
 * services/ so /control, /video, and /audio can evolve without turning this
 * file back into a one-off bring-up script.
 */

#include <Arduino.h>
#include "app/mergetesting_app.h"

MergetestingApp app;

void setup() {
  app.setup();
}

void loop() {
  app.loop();
}
