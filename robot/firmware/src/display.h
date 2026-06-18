#ifndef DISPLAY_H
#define DISPLAY_H

#include <Arduino.h>

// Minimal 128x160 TFT bring-up UI.
// Keep this module independent from camera streaming: it only renders a small
// status dashboard and simple vector expressions.
struct DisplayStatus {
    const char* connection;
    const char* camera;
    const char* motion;
};

void display_init();
void display_emotion(const char* emotion_tag, int intensity);
void display_set_connection(const char* status);
void display_set_camera(const char* status);
void display_set_motion(const char* status);
void display_show_test_screen();
void display_render_status(const DisplayStatus& status);
void display_text(const char* message, int x, int y);
void display_battery(int level);
void display_status_icon(int type);
void display_clear();

#endif // DISPLAY_H
