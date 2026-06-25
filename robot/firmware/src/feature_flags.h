#pragma once
/**
 * Compile-time feature gates for main firmware integration.
 * Set via platformio.ini build_flags (-DENABLE_WS_VIDEO=1).
 */

#ifndef ENABLE_WS_VIDEO
#define ENABLE_WS_VIDEO 0
#endif

#ifndef ENABLE_WS_AUDIO
#define ENABLE_WS_AUDIO 0
#endif

#ifndef ENABLE_FACE240
#define ENABLE_FACE240 0
#endif

#ifndef ENABLE_SPEAKER
#define ENABLE_SPEAKER 0
#endif

#ifndef ENABLE_WS_INTEGRATED
#define ENABLE_WS_INTEGRATED 0
#endif

#ifndef ENABLE_ARDUINO_OTA
#define ENABLE_ARDUINO_OTA 0
#endif

#if ENABLE_WS_INTEGRATED
#ifndef ENABLE_WS_VIDEO
#define ENABLE_WS_VIDEO 1
#endif
#ifndef ENABLE_WS_AUDIO
#define ENABLE_WS_AUDIO 1
#endif
#endif
