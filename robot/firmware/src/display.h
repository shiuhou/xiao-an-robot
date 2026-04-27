#ifndef DISPLAY_H
#define DISPLAY_H

// TODO: Define display control structures and functions
// - display_init(): Initialize TFT display
// - display_emotion(emotion_tag, intensity): Display emotion animation
// - display_text(message, x, y): Display text on screen
// - display_battery(level): Show battery level
// - display_status_icon(type): Show connection/status icons
// - display_clear(): Clear the screen

void display_init();
void display_emotion(const char* emotion_tag, int intensity);
void display_text(const char* message, int x, int y);
void display_battery(int level);
void display_status_icon(int type);
void display_clear();

#endif // DISPLAY_H
