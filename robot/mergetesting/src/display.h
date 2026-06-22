#ifndef DISPLAY_H
#define DISPLAY_H

#include <Arduino.h>

struct DisplayStatus {
  const char* connection;
  const char* camera;
  const char* motion;
};

void display_init();
void display_emotion(const char* emotion_tag, int intensity = 5);
void display_set_connection(const char* status);
void display_set_camera(const char* status);
void display_set_motion(const char* status);
void display_show_boot_neutral();
void display_tick();

#endif
