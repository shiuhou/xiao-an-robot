#pragma once

#include <Arduino.h>
#include "protocol.h"

class RobotState {
public:
  const char* expression() const;
  const char* motion() const;
  const char* camera() const;

  bool isBusy() const;
  bool isDocked() const;
  bool isWifiConnected() const;
  bool isControlConnected() const;
  bool isVideoConnected() const;
  bool isAudioConnected() const;

  void setExpression(const char* expression);
  void setMotion(const char* motion);
  void setCamera(const char* camera);
  void setCameraReady(bool ready);
  void setCameraOff();
  void setBusy(bool busy);
  void setDocked(bool docked);
  void setWifiConnected(bool connected);
  void setControlConnected(bool connected);
  void setVideoConnected(bool connected);
  void setAudioConnected(bool connected);

private:
  String _expression = Expression::NEUTRAL;
  String _motion = "idle";
  String _camera = "cam_off";
  bool _busy = false;
  bool _docked = false;
  bool _wifiConnected = false;
  bool _controlConnected = false;
  bool _videoConnected = false;
  bool _audioConnected = false;
};
